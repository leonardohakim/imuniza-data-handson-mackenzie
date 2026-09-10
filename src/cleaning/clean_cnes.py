"""Clean the raw CNES (estabelecimentos de saúde) CSV and aggregate it to
one row per município in the trusted layer.

CNES não é reprocessado por `--ano`: é um snapshot nacional único do
cadastro *atual* de estabelecimentos de saúde, não uma série histórica por
ano como PNI/população/PIB — mesma decisão já tomada para área territorial
(`clean_area.py`). Ver `docs/decisoes_limpeza.md`.

O código de município do CNES (coluna `CO_IBGE`, apesar do nome) vem no
padrão **DATASUS de 6 dígitos**, não no padrão IBGE de 7 dígitos —
confirmado contra os dados reais (635.786 de 635.786 registros com
`CO_IBGE` de exatamente 6 caracteres). Por isso a coluna de saída aqui já
se chama `codigo_municipio` com 6 dígitos, no mesmo padrão que
`clean_pni.py` usa para as doses — cruzada em `build_coverage.py` pela
mesma chave truncada já usada para o PNI (`codigo_municipio_datasus`), não
pelo código de 7 dígitos do IBGE usado por população/PIB/área.
"""

import argparse
import io
import os
import zipfile
from dataclasses import dataclass, field

import boto3
import pandas as pd
from botocore.client import Config

from src.config import MINIO_ACCESS_KEY, MINIO_ENDPOINT, MINIO_SECRET_KEY

BUCKET_RAW = os.getenv("MINIO_RAW_BUCKET", "raw")
BUCKET_TRUSTED = os.getenv("MINIO_TRUSTED_BUCKET", "trusted")


@dataclass
class CleaningReport:
    estabelecimentos_lidos: int = 0
    codigo_municipio_invalido: int = 0
    municipios_finais: int = 0
    notas: list = field(default_factory=list)

    def to_text(self) -> str:
        linhas = [
            "Relatório de limpeza — CNES (estabelecimentos de saúde)",
            "=" * 40,
            f"Estabelecimentos lidos do raw: {self.estabelecimentos_lidos}",
            (
                "Estabelecimentos com código de município inválido "
                f"(!= 6 dígitos) descartados: {self.codigo_municipio_invalido}"
            ),
            f"Municípios distintos na camada trusted: {self.municipios_finais}",
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


def clean_cnes_dataframe(raw_df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
    """Agrega estabelecimentos de saúde por município (contagem total e
    contagem com atendimento ambulatorial SUS). Função pura (sem I/O) —
    ver testes em `tests/test_clean_cnes.py`."""
    report = CleaningReport(estabelecimentos_lidos=len(raw_df))
    df = raw_df.copy()

    df["codigo_municipio"] = df["CO_IBGE"].astype(str).str.strip()
    codigo_valido = df["codigo_municipio"].str.match(r"^\d{6}$")
    report.codigo_municipio_invalido = int((~codigo_valido).sum())
    df = df.loc[codigo_valido].copy()

    df["_ambulatorial_sus"] = df["CO_AMBULATORIAL_SUS"].astype(str).str.upper().eq("SIM")

    agregado = (
        df.groupby("codigo_municipio")
        .agg(
            qtd_estabelecimentos_saude=("CO_CNES", "count"),
            qtd_estabelecimentos_saude_sus=("_ambulatorial_sus", "sum"),
        )
        .reset_index()
    )
    agregado["qtd_estabelecimentos_saude_sus"] = agregado["qtd_estabelecimentos_saude_sus"].astype("int64")

    report.municipios_finais = len(agregado)
    return agregado.sort_values("codigo_municipio").reset_index(drop=True), report


def clean_and_upload() -> CleaningReport:
    s3 = get_s3_client()
    raw_key = "cnes/cnes_estabelecimentos.zip"
    obj = s3.get_object(Bucket=BUCKET_RAW, Key=raw_key)
    with zipfile.ZipFile(io.BytesIO(obj["Body"].read())) as zf:
        nome_interno = zf.namelist()[0]
        with zf.open(nome_interno) as f:
            raw_df = pd.read_csv(f, sep=";", encoding="latin1", dtype=str)

    clean_df, report = clean_cnes_dataframe(raw_df)

    trusted_key = "cnes/cnes_estabelecimentos_por_municipio.parquet"
    buffer = io.BytesIO()
    clean_df.to_parquet(buffer, index=False)
    buffer.seek(0)
    s3.upload_fileobj(buffer, BUCKET_TRUSTED, trusted_key)

    report_key = "cnes/_cleaning_report.txt"
    s3.put_object(Bucket=BUCKET_TRUSTED, Key=report_key, Body=report.to_text().encode("utf-8"))

    print(f"[OK] {report.municipios_finais} municípios enviados para s3://{BUCKET_TRUSTED}/{trusted_key}")
    print(report.to_text())
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Limpa e agrega o CNES por município (raw -> trusted) no MinIO"
    )
    parser.parse_args()  # sem --ano de propósito, ver docstring do módulo
    clean_and_upload()
