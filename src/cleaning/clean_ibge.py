"""Clean the raw IBGE population CSV and promote it to the trusted layer.

Decisão de limpeza (documentada):
    A API SIDRA (`/values`), quando chamada sem o parâmetro `/h/n`, retorna por
    padrão um cabeçalho descritivo como primeiro elemento do array JSON (ex:
    {"D1C": "Município (Código)", "V": "Valor", ...}). O script de ingestão
    (`src/ingestion/download_ibge.py`) grava esse array inteiro no CSV bruto,
    então a primeira linha de dados do arquivo raw NÃO é um município — é essa
    linha de rótulos. Aqui identificamos e descartamos essa linha (a coluna
    "V" não é numérica nela) em vez de corrigir a ingestão, para preservar o
    princípio de que a camada raw nunca é reescrita — ela é o dado exatamente
    como veio da fonte, erros incluídos. A correção acontece na camada trusted.

Decisão de limpeza (documentada, bug corrigido):
    A Tabela 6579 devolve três dimensões por linha: D1 (Município), D2
    (Variável — sempre `9324`, "População residente estimada", porque a
    URL de `download_ibge.py` já fixa essa variável) e D3 (Ano de
    referência), na mesma estrutura da Tabela 5938/PIB (D1 Município, D2
    Variável, D3 Ano; ver `clean_pib.py`). Uma versão anterior deste
    arquivo mapeava **D2C** direto para a coluna "ano" (confundindo
    variável com ano), então todo o dataset ficava com "ano" = "9324" em
    vez do ano real — confirmado comparando com o CSV bruto real, onde
    D3C/D3N já trazem o ano correto (ex.: "2024"). A correção atribui a
    coluna "ano" a partir do parâmetro `--ano` da própria chamada (que
    sempre coincide com D3C, por ser o mesmo ano pedido na ingestão) em
    vez de ler D2C ou D3C do corpo da resposta — mesmo critério já usado
    para particionar os dados no MinIO (`ano={ano}/...`), evitando
    depender de mais uma suposição sobre a posição das dimensões da API.
    `RENAME_MAP` passou a nomear D2C/D2N como "variavel_codigo"/
    "variavel_nome", para não repetir a confusão. Ver
    `docs/decisoes_limpeza.md`.
"""

import argparse
import io
import os
from dataclasses import dataclass, field

import boto3
import pandas as pd
from botocore.client import Config

from src.config import MINIO_ACCESS_KEY, MINIO_ENDPOINT, MINIO_SECRET_KEY

BUCKET_RAW = os.getenv("MINIO_RAW_BUCKET", "raw")
BUCKET_TRUSTED = os.getenv("MINIO_TRUSTED_BUCKET", "trusted")

RENAME_MAP = {
    "D1C": "codigo_municipio",
    "D1N": "municipio",
    "D2C": "variavel_codigo",
    "D2N": "variavel_nome",
    "V": "populacao",
    "MC": "unidade_medida_codigo",
    "MN": "unidade_medida",
    "NN": "nivel_territorial",
}


@dataclass
class CleaningReport:
    linhas_lidas: int = 0
    linha_metadados_removida: bool = False
    linhas_populacao_invalida: int = 0
    duplicatas_removidas: int = 0
    codigo_municipio_invalido: int = 0
    linhas_finais: int = 0
    notas: list = field(default_factory=list)

    def to_text(self) -> str:
        linhas = [
            "Relatório de limpeza — população IBGE",
            "=" * 40,
            f"Linhas lidas do raw: {self.linhas_lidas}",
            f"Linha de metadados SIDRA removida: {'sim' if self.linha_metadados_removida else 'não'}",
            f"Linhas com população não numérica removidas: {self.linhas_populacao_invalida}",
            f"Linhas com código de município inválido (!= 7 dígitos) removidas: {self.codigo_municipio_invalido}",
            f"Duplicatas (mesmo código de município) removidas: {self.duplicatas_removidas}",
            f"Linhas finais na camada trusted: {self.linhas_finais}",
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


def clean_population_dataframe(raw_df: pd.DataFrame, ano: int) -> tuple[pd.DataFrame, CleaningReport]:
    """Apply all cleaning decisions to a raw SIDRA population dataframe.

    `ano` é o ano de referência pedido na ingestão (mesmo valor do `--ano` de
    `download_ibge.py`/`clean_and_upload`). Não vem do corpo da resposta da
    API: ver "Decisão de limpeza (bug corrigido)" no topo do arquivo.
    """
    report = CleaningReport(linhas_lidas=len(raw_df))
    df = raw_df.copy()

    # 1) Remove a linha de metadados do SIDRA (ver docstring do módulo).
    valor_numerico = pd.to_numeric(df["V"], errors="coerce")
    linha_metadados = valor_numerico.isna() & df["V"].astype(str).str.contains(
        "[A-Za-z]", regex=True, na=False
    )
    if linha_metadados.any():
        report.linha_metadados_removida = True
        df = df.loc[~linha_metadados].copy()
        valor_numerico = valor_numerico.loc[~linha_metadados]

    df = df.rename(columns=RENAME_MAP)
    df["populacao"] = pd.to_numeric(df["populacao"], errors="coerce")

    # 2) Trata valores ausentes/inválidos na população: SIDRA usa marcadores
    #    como "-", "..", "X" para sigilo estatístico ou dado não disponível.
    #    Decisão: descartar (não imputar), pois população é a base do
    #    denominador da métrica de cobertura vacinal — um valor imputado
    #    incorretamente aqui distorceria diretamente o resultado final.
    populacao_invalida = df["populacao"].isna()
    report.linhas_populacao_invalida = int(populacao_invalida.sum())
    df = df.loc[~populacao_invalida].copy()

    # 3) Padroniza o código do município para 7 dígitos (padrão IBGE) e
    #    descarta códigos que não têm o formato esperado.
    df["codigo_municipio"] = df["codigo_municipio"].astype(str).str.strip()
    codigo_valido = df["codigo_municipio"].str.match(r"^\d{7}$")
    report.codigo_municipio_invalido = int((~codigo_valido).sum())
    df = df.loc[codigo_valido].copy()

    # 4) Remove duplicatas exatas de município (mantém a primeira ocorrência).
    duplicadas = df.duplicated(subset=["codigo_municipio"])
    report.duplicatas_removidas = int(duplicadas.sum())
    df = df.loc[~duplicadas].copy()

    df["populacao"] = df["populacao"].astype("int64")
    df["ano"] = str(ano)
    colunas_finais = [
        "codigo_municipio",
        "municipio",
        "ano",
        "populacao",
        "unidade_medida",
        "nivel_territorial",
    ]
    colunas_presentes = [coluna for coluna in colunas_finais if coluna in df.columns]
    df = df[colunas_presentes].sort_values("codigo_municipio").reset_index(drop=True)

    report.linhas_finais = len(df)
    return df, report


def clean_and_upload(ano: int) -> CleaningReport:
    s3 = get_s3_client()
    raw_key = f"ibge/populacao/ano={ano}/populacao_municipios.csv"
    obj = s3.get_object(Bucket=BUCKET_RAW, Key=raw_key)
    raw_df = pd.read_csv(io.BytesIO(obj["Body"].read()), dtype=str)

    clean_df, report = clean_population_dataframe(raw_df, ano)

    trusted_key = f"ibge/populacao/ano={ano}/populacao_municipios.parquet"
    buffer = io.BytesIO()
    clean_df.to_parquet(buffer, index=False)
    buffer.seek(0)
    s3.upload_fileobj(buffer, BUCKET_TRUSTED, trusted_key)

    report_key = f"ibge/populacao/ano={ano}/_cleaning_report.txt"
    s3.put_object(Bucket=BUCKET_TRUSTED, Key=report_key, Body=report.to_text().encode("utf-8"))

    print(f"[OK] {report.linhas_finais} municípios enviados para s3://{BUCKET_TRUSTED}/{trusted_key}")
    print(report.to_text())
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Limpa a população municipal (raw -> trusted) no MinIO"
    )
    parser.add_argument("--ano", type=int, default=2024)
    clean_and_upload(parser.parse_args().ano)
