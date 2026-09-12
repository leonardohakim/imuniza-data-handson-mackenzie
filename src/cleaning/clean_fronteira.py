"""Clean a planilha bruta de faixa de fronteira e promove para a camada trusted.

Mesmo padrão de `clean_area.py`: a fonte bruta (`download_fronteira.py`) é
gravada tal como veio do IBGE, sem parsing — a limpeza acontece aqui.

A planilha original (aba "Faixa de Fronteira - Município 2024") tem uma
linha por município que **intersecta** a faixa de fronteira por área
(~590 no total, confirmado contra o arquivo real), não uma linha por
"município oficialmente de fronteira". A coluna `FAIXA_SEDE` ("sim"/"não")
é que indica se a **sede** do município está de fato dentro da faixa —
esse é o critério usado tradicionalmente para dizer que um município "é"
de fronteira (a Lei 6.634/1979 define a faixa a partir de 150km da linha
divisória; um município cuja sede cai fora dessa faixa mas cujo território
apenas toca a borda não é, na prática, tratado como "município de
fronteira" pelos órgãos federais). Por isso `fronteira = 1` aqui é
`FAIXA_SEDE == "sim"`, não "toca a faixa de alguma forma" — ver
`docs/decisoes_limpeza.md`, seção 12.

Municípios que não aparecem nesta planilha (a grande maioria do país) não
são "dado ausente" — são, por construção, município que não intersecta a
faixa de fronteira de forma alguma, logo `fronteira = 0`. Essa é uma
decisão diferente da já tomada para PIB/área/CNES (onde ausência = lacuna,
tratada com `NaN`, não `0`): aqui a fonte é uma lista positiva completa
("todo município na faixa aparece aqui"), então ausência é, ela mesma, a
resposta "não". O preenchimento com `0` para quem não está nesta tabela
acontece no merge, em `build_coverage.py` — este módulo só limpa as linhas
que de fato existem na planilha.
"""

import io
import os
from dataclasses import dataclass, field

import boto3
import pandas as pd
from botocore.client import Config

from src.config import MINIO_ACCESS_KEY, MINIO_ENDPOINT, MINIO_SECRET_KEY

BUCKET_RAW = os.getenv("MINIO_RAW_BUCKET", "raw")
BUCKET_TRUSTED = os.getenv("MINIO_TRUSTED_BUCKET", "trusted")

RAW_KEY = "ibge/fronteira/municipios_faixa_fronteira.xls"
TRUSTED_KEY = "ibge/fronteira/municipios_faixa_fronteira.parquet"
SHEET_NAME = "Faixa de Fronteira - Município 2024"

RENAME_MAP = {
    "CD_MUN": "codigo_municipio",
    "NM_MUN": "municipio",
    "SIGLA_UF": "uf",
}


@dataclass
class CleaningReport:
    linhas_lidas: int = 0
    linhas_faixa_sede_indefinida: int = 0
    codigo_municipio_invalido: int = 0
    duplicatas_removidas: int = 0
    linhas_finais: int = 0
    municipios_com_sede_na_faixa: int = 0
    notas: list = field(default_factory=list)

    def to_text(self) -> str:
        linhas = [
            "Relatório de limpeza — faixa de fronteira (IBGE)",
            "=" * 40,
            f"Linhas lidas do raw (municípios que intersectam a faixa por área): {self.linhas_lidas}",
            f"Linhas com FAIXA_SEDE indefinida (sem 'sim'/'não') removidas: {self.linhas_faixa_sede_indefinida}",
            f"Linhas com código de município inválido (!= 7 dígitos) removidas: {self.codigo_municipio_invalido}",
            f"Duplicatas (mesmo código de município) removidas: {self.duplicatas_removidas}",
            f"Linhas finais na camada trusted: {self.linhas_finais}",
            f"Desses, com sede efetivamente na faixa (fronteira=1): {self.municipios_com_sede_na_faixa}",
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


def clean_fronteira_dataframe(raw_df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
    """Aplica as decisões de limpeza a um DataFrame bruto no formato da aba
    'Faixa de Fronteira - Município 2024' (ver docstring do módulo)."""
    report = CleaningReport(linhas_lidas=len(raw_df))
    df = raw_df.copy()

    # 1) FAIXA_SEDE indefinida (nem "sim" nem "não"): descartar, não supor.
    #    Confirmado contra o arquivo real que existem 2 linhas assim (município
    #    que toca a faixa por área mas sem essa determinação preenchida).
    faixa_sede_valida = df["FAIXA_SEDE"].isin(["sim", "não"])
    report.linhas_faixa_sede_indefinida = int((~faixa_sede_valida).sum())
    df = df.loc[faixa_sede_valida].copy()

    df["fronteira"] = (df["FAIXA_SEDE"] == "sim").astype(int)
    df = df.rename(columns=RENAME_MAP)

    # 2) Padroniza o código do município para 7 dígitos (padrão IBGE) — mesmo
    #    critério de clean_area.py/clean_ibge.py.
    df["codigo_municipio"] = df["codigo_municipio"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    codigo_valido = df["codigo_municipio"].str.match(r"^\d{7}$")
    report.codigo_municipio_invalido = int((~codigo_valido).sum())
    df = df.loc[codigo_valido].copy()

    # 3) Remove duplicatas exatas de município.
    duplicadas = df.duplicated(subset=["codigo_municipio"])
    report.duplicatas_removidas = int(duplicadas.sum())
    df = df.loc[~duplicadas].copy()

    colunas_finais = ["codigo_municipio", "municipio", "uf", "fronteira"]
    colunas_presentes = [coluna for coluna in colunas_finais if coluna in df.columns]
    df = df[colunas_presentes].sort_values("codigo_municipio").reset_index(drop=True)

    report.linhas_finais = len(df)
    report.municipios_com_sede_na_faixa = int(df["fronteira"].sum())
    return df, report


def clean_and_upload() -> CleaningReport:
    s3 = get_s3_client()
    obj = s3.get_object(Bucket=BUCKET_RAW, Key=RAW_KEY)
    raw_bytes = io.BytesIO(obj["Body"].read())
    raw_df = pd.read_excel(raw_bytes, sheet_name=SHEET_NAME, dtype=str)

    clean_df, report = clean_fronteira_dataframe(raw_df)

    buffer = io.BytesIO()
    clean_df.to_parquet(buffer, index=False)
    buffer.seek(0)
    s3.upload_fileobj(buffer, BUCKET_TRUSTED, TRUSTED_KEY)

    report_key = "ibge/fronteira/_cleaning_report.txt"
    s3.put_object(Bucket=BUCKET_TRUSTED, Key=report_key, Body=report.to_text().encode("utf-8"))

    print(f"[OK] {report.linhas_finais} municípios enviados para s3://{BUCKET_TRUSTED}/{TRUSTED_KEY}")
    print(report.to_text())
    return report


if __name__ == "__main__":
    clean_and_upload()
