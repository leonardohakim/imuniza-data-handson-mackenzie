"""Clean o painel de saneamento básico (SNIS, via Base dos Dados) e promove
o ano de referência escolhido para a camada trusted.

Diferente das demais fontes deste pipeline, o raw aqui é um **painel
histórico** (1995-2022, ~119 mil linhas). A limpeza filtra para um único
ano de referência (`ANO_REFERENCIA`, ver abaixo) antes de seguir com o
resto do tratamento — nenhum outro módulo de limpeza deste projeto recebe
`--ano` para SNIS pelo mesmo motivo de área/CNES/fronteira: é tratado como
um snapshot, não uma série reprocessada por ano do dataset refinado.

Escolha do ano de referência (2022)
------------------------------------------------------------------
O SNIS foi descontinuado em 2023 (substituído pelo SINISA, sem dado
histórico público ainda — ver `download_snis.py`). Entre os últimos anos
disponíveis, 2022 é o mais completo: verificado nesta sessão via fetch real
do painel inteiro, contagem de município com indicador de água não-nulo por
ano — 2022: 5.424/5.425; 2021: 5.312/5.313; 2020: 5.337/5.338 (e cobertura
caindo mais em anos anteriores). Por isso 2022 é o ano fixo usado aqui, não
o "ano mais recente disponível por município" (que exigiria uma lógica de
seleção por linha, não usada em nenhuma outra fonte deste projeto).

Por que só o indicador de água vira feature de modelagem
------------------------------------------------------------------
O SNIS também publica indicadores de esgotamento sanitário (coleta e
tratamento de esgoto), mas eles têm completude bem pior — mesmo em 2022,
só ~53% dos municípios têm os dois indicadores preenchidos, contra ~99,9%
do indicador de água entre os municípios com pelo menos uma linha no ano.
Seguindo a mesma decisão de "descartar, não imputar" já usada em todo o
projeto (nunca fabricar um valor para preencher uma lacuna), incluir esgoto
como feature obrigatória descartaria quase metade do dataset de modelagem —
um custo desproporcional ao ganho. Decisão: os indicadores de esgoto ficam
na camada trusted (para referência/exploração futura), mas **não** viram
`colunas_obrigatorias` nem entram no conjunto de features do notebook 03 —
ver `docs/decisoes_limpeza.md`, seção 13, e `docs/decisoes_modelagem.md`,
seção 1. O indicador de água, por sua vez, tem completude alta o bastante
(~97% dos municípios do projeto, ver `docs/decisoes_modelagem.md`) para
seguir o mesmo critério das demais features obrigatórias (PIB/área/CNES):
descartar as poucas linhas sem o dado, não imputar.
"""

import argparse
import gzip
import io
import os
from dataclasses import dataclass, field

import boto3
import pandas as pd
from botocore.client import Config

from src.config import MINIO_ACCESS_KEY, MINIO_ENDPOINT, MINIO_SECRET_KEY

BUCKET_RAW = os.getenv("MINIO_RAW_BUCKET", "raw")
BUCKET_TRUSTED = os.getenv("MINIO_TRUSTED_BUCKET", "trusted")

RAW_KEY = "basedosdados/snis/municipio_agua_esgoto.csv.gz"
TRUSTED_KEY = "saneamento/snis/saneamento_municipios.parquet"

# Ano de referência fixo — ver docstring do módulo.
ANO_REFERENCIA = "2022"

RENAME_MAP = {
    "id_municipio": "codigo_municipio",
    "ano": "ano_referencia_saneamento",
    "indice_atendimento_total_agua": "pct_atendimento_agua",
    "indice_coleta_esgoto": "pct_coleta_esgoto",
    "indice_tratamento_esgoto": "pct_tratamento_esgoto",
}

COLUNAS_ORIGEM = list(RENAME_MAP.keys())


@dataclass
class CleaningReport:
    linhas_lidas: int = 0
    linhas_ano_referencia: int = 0
    codigo_municipio_invalido: int = 0
    linhas_agua_ausente: int = 0
    duplicatas_removidas: int = 0
    linhas_finais: int = 0
    municipios_com_coleta_esgoto: int = 0
    municipios_com_tratamento_esgoto: int = 0
    notas: list = field(default_factory=list)

    def to_text(self) -> str:
        linhas = [
            "Relatório de limpeza — saneamento básico (SNIS, via Base dos Dados)",
            "=" * 40,
            f"Ano de referência: {ANO_REFERENCIA}",
            f"Linhas lidas do raw (painel histórico completo): {self.linhas_lidas}",
            f"Linhas do ano de referência: {self.linhas_ano_referencia}",
            f"Linhas com código de município inválido (!= 7 dígitos) removidas: {self.codigo_municipio_invalido}",
            f"Linhas sem indicador de água (descartadas, não imputadas): {self.linhas_agua_ausente}",
            f"Duplicatas (mesmo código de município) removidas: {self.duplicatas_removidas}",
            f"Linhas finais na camada trusted: {self.linhas_finais}",
            f"Desses, com indicador de coleta de esgoto preenchido: {self.municipios_com_coleta_esgoto}",
            f"Desses, com indicador de tratamento de esgoto preenchido: {self.municipios_com_tratamento_esgoto}",
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


def clean_snis_dataframe(raw_df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
    """Aplica todas as decisões de limpeza a um DataFrame bruto do painel
    SNIS (uma linha por município x ano). Função pura (sem I/O) para ser
    testável isoladamente — ver `tests/test_clean_snis.py`."""
    report = CleaningReport(linhas_lidas=len(raw_df))
    df = raw_df.copy()

    # 1) Filtra para o ano de referência fixo — ver docstring do módulo.
    df["ano"] = df["ano"].astype(str).str.strip()
    df = df.loc[df["ano"] == ANO_REFERENCIA].copy()
    report.linhas_ano_referencia = len(df)

    colunas_presentes_origem = [c for c in COLUNAS_ORIGEM if c in df.columns]
    df = df[colunas_presentes_origem].rename(columns=RENAME_MAP)

    for coluna in ("pct_atendimento_agua", "pct_coleta_esgoto", "pct_tratamento_esgoto"):
        if coluna in df.columns:
            df[coluna] = pd.to_numeric(df[coluna], errors="coerce")

    # 2) Código de município: já vem no formato de 7 dígitos do IBGE na Base
    #    dos Dados, mas validamos do mesmo jeito que as demais fontes.
    df["codigo_municipio"] = df["codigo_municipio"].astype(str).str.strip()
    codigo_valido = df["codigo_municipio"].str.match(r"^\d{7}$")
    report.codigo_municipio_invalido = int((~codigo_valido).sum())
    df = df.loc[codigo_valido].copy()

    # 3) Indicador de água ausente/inválido: descartar, não imputar — mesmo
    #    critério já usado para PIB/área (ver docstring do módulo sobre por
    #    que esse critério não se aplica da mesma forma ao esgoto).
    agua_ausente = df["pct_atendimento_agua"].isna()
    report.linhas_agua_ausente = int(agua_ausente.sum())
    df = df.loc[~agua_ausente].copy()

    # 4) Remove duplicatas exatas de município (não esperado após o filtro
    #    de ano, mas protege contra o painel trazer mais de uma linha por
    #    município no mesmo ano).
    duplicadas = df.duplicated(subset=["codigo_municipio"])
    report.duplicatas_removidas = int(duplicadas.sum())
    df = df.loc[~duplicadas].copy()

    colunas_finais = [
        "codigo_municipio",
        "ano_referencia_saneamento",
        "pct_atendimento_agua",
        "pct_coleta_esgoto",
        "pct_tratamento_esgoto",
    ]
    colunas_presentes = [c for c in colunas_finais if c in df.columns]
    df = df[colunas_presentes].sort_values("codigo_municipio").reset_index(drop=True)

    report.linhas_finais = len(df)
    if "pct_coleta_esgoto" in df.columns:
        report.municipios_com_coleta_esgoto = int(df["pct_coleta_esgoto"].notna().sum())
    if "pct_tratamento_esgoto" in df.columns:
        report.municipios_com_tratamento_esgoto = int(df["pct_tratamento_esgoto"].notna().sum())

    return df, report


def clean_and_upload() -> CleaningReport:
    s3 = get_s3_client()
    obj = s3.get_object(Bucket=BUCKET_RAW, Key=RAW_KEY)
    raw_bytes = obj["Body"].read()
    with gzip.GzipFile(fileobj=io.BytesIO(raw_bytes)) as gz:
        raw_df = pd.read_csv(gz, dtype=str)

    clean_df, report = clean_snis_dataframe(raw_df)

    buffer = io.BytesIO()
    clean_df.to_parquet(buffer, index=False)
    buffer.seek(0)
    s3.upload_fileobj(buffer, BUCKET_TRUSTED, TRUSTED_KEY)

    report_key = "saneamento/snis/_cleaning_report.txt"
    s3.put_object(Bucket=BUCKET_TRUSTED, Key=report_key, Body=report.to_text().encode("utf-8"))

    print(f"[OK] {report.linhas_finais} municípios enviados para s3://{BUCKET_TRUSTED}/{TRUSTED_KEY}")
    print(report.to_text())
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Limpa o painel de saneamento (SNIS, raw -> trusted) no MinIO"
    )
    parser.parse_args()  # sem --ano de propósito, ver docstring do módulo
    clean_and_upload()
