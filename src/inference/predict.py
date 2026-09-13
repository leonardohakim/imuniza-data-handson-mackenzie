"""Pipeline de inferência em lote: aplica o modelo de risco a um dataset
`refined` e grava uma lista priorizada de municípios.

Esta é a entrega 6 da Etapa 3 ("pipeline de inferência: fluxo automatizado
para aplicar o modelo em novos dados"). Diferente do notebook
`03_construcao_modelos.ipynb` — que **compara** algoritmos, mede e explica —
este módulo tem um único objetivo: pegar um dataset já cruzado e devolver,
de forma reprodutível e sem intervenção manual, a pergunta de negócio
respondida: *quais municípios priorizar*.

Três decisões de projeto que valem explicação:

1. **Não refaz o `GridSearchCV`.** Os hiperparâmetros usados aqui
   (`max_depth=4`, `n_estimators=200`) são exatamente os que a busca do
   notebook elegeu para o Random Forest, registrados em
   `docs/decisoes_modelagem.md`. Repetir a busca a cada inferência custaria
   ~27s por execução para chegar ao mesmo lugar, e — pior — deixaria o
   resultado da inferência dependente de uma busca que pode variar com o
   dado de entrada, quando o que se quer aqui é um comportamento estável e
   auditável. Reajustar hiperparâmetros é tarefa do notebook (treino), não
   do lote (inferência).

2. **Treina no ano de referência e pontua o ano-alvo, que por padrão são o
   mesmo ano.** O projeto tem um único ano processado (2025) — ver o escopo
   transversal em `docs/decisoes_modelagem.md`. Com `--ano-referencia`
   separado de `--ano`, o mesmo comando vira, sem nenhuma mudança de
   código, o fluxo temporal que o projeto quer quando houver um segundo ano:
   `--ano-referencia 2025 --ano 2026` treina no passado e pontua o presente.
   Enquanto isso não existe, os dois anos coincidem e o resultado é uma
   **priorização do próprio ano**, não uma previsão de futuro — o módulo
   avisa isso explicitamente na saída, para ninguém ler o parquet como
   previsão.

3. **A saída é um ranking, não um rótulo.** O modelo tem F1 ≈ 0,40 e
   ROC-AUC ≈ 0,60 no teste (`docs/resultados_modelagem.md`): é fraco como
   classificador e seria irresponsável entregar uma decisão binária
   automática ("este município é de risco"). O que ele faz bem o suficiente
   para ser útil é **ordenar** — por isso a saída principal é
   `probabilidade_baixa_cobertura` com o ranking, e a faixa de prioridade é
   uma leitura auxiliar por decis, não um veredito.

Uso:

    python -m src.inference.predict --ano 2025
    python -m src.inference.predict --ano-referencia 2025 --ano 2026 --top 100

Saída em `refined/priorizacao/ano={ano}/priorizacao_municipios.parquet`
(mais um `.csv` do mesmo conteúdo, para quem for abrir no Excel) e um
`_inference_report.txt` ao lado, no mesmo padrão dos relatórios de limpeza.
"""

import argparse
import io
import os
from dataclasses import dataclass, field

import boto3
import numpy as np
import pandas as pd
from botocore.client import Config
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.config import MINIO_ACCESS_KEY, MINIO_ENDPOINT, MINIO_SECRET_KEY

BUCKET_REFINED = os.getenv("MINIO_REFINED_BUCKET", "refined")

# Mesmas constantes do notebook 03 — mantidas idênticas de propósito: se
# divergirem, a inferência deixa de refletir o modelo que foi medido.
UFS_FRONTEIRA = {"AC", "AP", "AM", "MT", "MS", "PA", "PR", "RS", "RO", "RR", "SC"}

REGIAO_POR_UF = {
    "AC": "Norte", "AP": "Norte", "AM": "Norte", "PA": "Norte", "RO": "Norte",
    "RR": "Norte", "TO": "Norte",
    "AL": "Nordeste", "BA": "Nordeste", "CE": "Nordeste", "MA": "Nordeste",
    "PB": "Nordeste", "PE": "Nordeste", "PI": "Nordeste", "RN": "Nordeste",
    "SE": "Nordeste",
    "DF": "Centro-Oeste", "GO": "Centro-Oeste", "MT": "Centro-Oeste", "MS": "Centro-Oeste",
    "ES": "Sudeste", "MG": "Sudeste", "RJ": "Sudeste", "SP": "Sudeste",
    "PR": "Sul", "RS": "Sul", "SC": "Sul",
}

COLUNAS_OBRIGATORIAS = [
    "pib_per_capita_reais",
    "populacao",
    "cobertura_doses_por_100_habitantes",
    "qtd_estabelecimentos_saude_sus",
]

# Hiperparâmetros eleitos pelo GridSearchCV do notebook 03 (seção 4).
MELHORES_PARAMETROS_RF = {"max_depth": 4, "n_estimators": 200}


@dataclass
class InferenceReport:
    municipios_lidos: int = 0
    descartados_colunas_obrigatorias: int = 0
    descartados_sem_agua: int = 0
    municipios_pontuados: int = 0
    features_usadas: list = field(default_factory=list)
    corte_alvo: float = 0.0
    ano_referencia: int = 0
    ano_alvo: int = 0
    notas: list = field(default_factory=list)

    def to_text(self) -> str:
        linhas = [
            "Relatório de inferência — priorização de municípios",
            "=" * 52,
            f"Ano de referência (treino): {self.ano_referencia}",
            f"Ano alvo (pontuação):       {self.ano_alvo}",
            f"Municípios lidos do refined: {self.municipios_lidos}",
            f"Descartados por falta de PIB/população/cobertura/CNES: {self.descartados_colunas_obrigatorias}",
            f"Descartados por falta do indicador de água (SNIS): {self.descartados_sem_agua}",
            f"Municípios efetivamente pontuados: {self.municipios_pontuados}",
            f"Corte do alvo (1º quartil de cobertura no treino): {self.corte_alvo:.2f} doses/100 hab.",
            f"Features usadas ({len(self.features_usadas)}): {', '.join(self.features_usadas)}",
        ]
        linhas.extend(f"- {nota}" for nota in self.notas)
        return "\n".join(linhas)


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
    )


def preparar_features(df: pd.DataFrame) -> tuple[pd.DataFrame, list, InferenceReport]:
    """Reconstrói, a partir do `refined`, exatamente o conjunto de features do
    notebook 03 — incluindo as features condicionais (densidade e água), que
    só entram quando a coluna existe no dataset.

    Função pura (sem I/O): é o núcleo testável deste módulo.
    """
    report = InferenceReport(municipios_lidos=len(df))
    dados = df.dropna(subset=COLUNAS_OBRIGATORIAS).copy()
    report.descartados_colunas_obrigatorias = len(df) - len(dados)

    dados["uf"] = dados["municipio"].str.split(" - ").str[-1]

    if "fronteira" in dados.columns:
        dados["fronteira"] = dados["fronteira"].astype(int)
    else:
        # Mesmo fallback do notebook: aproximação por UF quando a lista
        # oficial do IBGE ainda não foi materializada no refined.
        dados["fronteira"] = dados["uf"].isin(UFS_FRONTEIRA).astype(int)
        report.notas.append(
            "Lista oficial de fronteira ausente no refined — usada a aproximação por UF."
        )

    dados["regiao"] = dados["uf"].map(REGIAO_POR_UF)
    if dados["regiao"].isna().any():
        ufs = sorted(dados.loc[dados["regiao"].isna(), "uf"].unique())
        raise ValueError(f"UF sem região mapeada: {ufs} — checar REGIAO_POR_UF")

    dados["log_populacao"] = np.log1p(dados["populacao"])
    dados["log_pib_per_capita"] = np.log1p(dados["pib_per_capita_reais"])
    dados["estabelecimentos_saude_sus_por_100k_hab"] = (
        dados["qtd_estabelecimentos_saude_sus"] / dados["populacao"] * 100_000
    )
    dados["log_estabelecimentos_saude_sus_por_100k_hab"] = np.log1p(
        dados["estabelecimentos_saude_sus_por_100k_hab"]
    )

    features_numericas = [
        "log_populacao",
        "log_pib_per_capita",
        "fronteira",
        "log_estabelecimentos_saude_sus_por_100k_hab",
    ]

    if "densidade_hab_km2" in dados.columns:
        dados["log_densidade_hab_km2"] = np.log1p(dados["densidade_hab_km2"])
        features_numericas.append("log_densidade_hab_km2")

    if "pct_atendimento_agua" in dados.columns:
        n_antes = len(dados)
        dados = dados.dropna(subset=["pct_atendimento_agua"]).copy()
        report.descartados_sem_agua = n_antes - len(dados)
        features_numericas.append("pct_atendimento_agua")

    report.features_usadas = features_numericas + ["regiao"]
    report.municipios_pontuados = len(dados)
    return dados, features_numericas, report


def construir_modelo(features_numericas: list) -> Pipeline:
    """Monta o mesmo pipeline (pré-processamento + Random Forest) do notebook,
    já com os hiperparâmetros eleitos pela busca registrada na Etapa 3."""
    features_escalar = [f for f in features_numericas if f != "fronteira"]
    preprocessador = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), features_escalar),
            ("bin", "passthrough", ["fronteira"]),
            ("cat", OneHotEncoder(handle_unknown="ignore"), ["regiao"]),
        ]
    )
    modelo = RandomForestClassifier(
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
        **MELHORES_PARAMETROS_RF,
    )
    return Pipeline([("preprocessador", preprocessador), ("modelo", modelo)])


def definir_alvo(dados: pd.DataFrame) -> tuple[pd.Series, float]:
    """Alvo `baixa_cobertura`: 1 se a cobertura está abaixo do 1º quartil do
    próprio conjunto (mesma definição do notebook — corte estatístico
    relativo, não um limiar clínico fixo)."""
    corte = dados["cobertura_doses_por_100_habitantes"].quantile(0.25)
    alvo = (dados["cobertura_doses_por_100_habitantes"] < corte).astype(int)
    return alvo, float(corte)


def gerar_priorizacao(modelo: Pipeline, dados: pd.DataFrame, features: list) -> pd.DataFrame:
    """Aplica o modelo já treinado e devolve a lista priorizada.

    A saída é ordenada por probabilidade de baixa cobertura (maior primeiro).
    `faixa_prioridade` é uma leitura auxiliar por decil — não um veredito:
    ver a nota 3 na docstring do módulo sobre por que a entrega é um ranking
    e não um rótulo binário.
    """
    X = dados[features + ["regiao"]]
    probabilidade = modelo.predict_proba(X)[:, 1]

    saida = pd.DataFrame(
        {
            "codigo_municipio": dados["codigo_municipio"].values,
            "municipio": dados["municipio"].values,
            "uf": dados["uf"].values,
            "regiao": dados["regiao"].values,
            "populacao": dados["populacao"].values,
            "cobertura_doses_por_100_habitantes": dados[
                "cobertura_doses_por_100_habitantes"
            ].values,
            "probabilidade_baixa_cobertura": probabilidade,
        }
    )
    saida = saida.sort_values(
        "probabilidade_baixa_cobertura", ascending=False
    ).reset_index(drop=True)
    saida["ranking_prioridade"] = np.arange(1, len(saida) + 1)

    # Decis sobre o ranking: os 10% com maior probabilidade viram "muito alta".
    # `pd.qcut` com 10 faixas resolve empates de probabilidade de forma
    # determinística pelo próprio ranking, não pelo valor.
    decil = pd.qcut(saida["ranking_prioridade"], 10, labels=False, duplicates="drop")
    faixas = {0: "muito alta", 1: "alta", 2: "alta"}
    saida["faixa_prioridade"] = [
        faixas.get(d, "média" if d < 6 else "baixa") for d in decil
    ]
    return saida


def executar(ano: int, ano_referencia: int | None = None, top: int | None = None):
    """Fluxo completo: lê o refined, treina no ano de referência, pontua o ano
    alvo e grava a priorização de volta no refined."""
    ano_referencia = ano_referencia or ano
    s3 = get_s3_client()

    def _ler(ano_alvo: int) -> pd.DataFrame:
        chave = f"cobertura_vacinal/ano={ano_alvo}/cobertura_municipios.parquet"
        obj = s3.get_object(Bucket=BUCKET_REFINED, Key=chave)
        return pd.read_parquet(io.BytesIO(obj["Body"].read()))

    dados_treino, features_treino, report_treino = preparar_features(_ler(ano_referencia))
    alvo, corte = definir_alvo(dados_treino)

    modelo = construir_modelo(features_treino)
    modelo.fit(dados_treino[features_treino + ["regiao"]], alvo)

    if ano == ano_referencia:
        dados_alvo, report = dados_treino, report_treino
    else:
        dados_alvo, features_alvo, report = preparar_features(_ler(ano))
        if features_alvo != features_treino:
            raise ValueError(
                "Conjunto de features do ano alvo difere do ano de referência "
                f"({features_alvo} vs {features_treino}) — o modelo treinado não "
                "se aplica. Rode o pipeline de limpeza para o ano alvo antes."
            )

    priorizacao = gerar_priorizacao(modelo, dados_alvo, features_treino)

    report.corte_alvo = corte
    report.ano_referencia = ano_referencia
    report.ano_alvo = ano
    if ano == ano_referencia:
        report.notas.append(
            "Ano de referência igual ao ano alvo: a saída é uma PRIORIZAÇÃO do "
            "próprio ano (recorte transversal), não uma previsão de futuro."
        )
    report.notas.append(
        "A saída é um ranking por probabilidade, não um rótulo binário: o modelo "
        "tem F1 ≈ 0,40 e ROC-AUC ≈ 0,60 no teste (ver docs/resultados_modelagem.md)."
    )

    prefixo = f"priorizacao/ano={ano}"
    buffer = io.BytesIO()
    priorizacao.to_parquet(buffer, index=False)
    buffer.seek(0)
    s3.upload_fileobj(buffer, BUCKET_REFINED, f"{prefixo}/priorizacao_municipios.parquet")

    csv_bytes = priorizacao.to_csv(index=False).encode("utf-8")
    s3.put_object(
        Bucket=BUCKET_REFINED, Key=f"{prefixo}/priorizacao_municipios.csv", Body=csv_bytes
    )
    s3.put_object(
        Bucket=BUCKET_REFINED,
        Key=f"{prefixo}/_inference_report.txt",
        Body=report.to_text().encode("utf-8"),
    )

    print(f"[OK] {len(priorizacao)} municípios priorizados em s3://{BUCKET_REFINED}/{prefixo}/")
    print(report.to_text())
    if top:
        print(f"\nTop {top} municípios por probabilidade de baixa cobertura:")
        colunas = [
            "ranking_prioridade",
            "municipio",
            "cobertura_doses_por_100_habitantes",
            "probabilidade_baixa_cobertura",
            "faixa_prioridade",
        ]
        print(priorizacao.head(top)[colunas].to_string(index=False))
    return priorizacao, report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Aplica o modelo de risco de baixa cobertura e grava a priorização."
    )
    parser.add_argument("--ano", type=int, default=2025, help="ano a ser pontuado")
    parser.add_argument(
        "--ano-referencia",
        type=int,
        default=None,
        help="ano usado para treinar (default: o mesmo de --ano)",
    )
    parser.add_argument(
        "--top", type=int, default=20, help="quantos municípios imprimir no terminal"
    )
    args = parser.parse_args()
    executar(ano=args.ano, ano_referencia=args.ano_referencia, top=args.top)
