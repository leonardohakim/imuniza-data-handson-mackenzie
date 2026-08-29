"""Download municipal GDP (PIB) estimates from IBGE SIDRA into MinIO.

Mesmo padrão de `download_ibge.py` (população), usando a Tabela 5938 do
SIDRA em vez da 6579. A 5938 foi escolhida depois de testar outras
candidatas contra a API real:

- Tabela 6784 (que parecia ser "PIB dos Municípios" pelo nome) só aceita
  consulta a nível Brasil (N1) — API retorna erro explícito
  "Parâmetro N6 (Nível territorial) incompatível com a tabela" ao tentar
  por município.
- Tabela 5938 aceita N6 (município) e tem a variável 37 ("Produto Interno
  Bruto a preços correntes", em Mil Reais), com série anual de 2002 a 2023
  confirmada via `/metadados`.

Essa tabela não traz PIB per capita pronto: calculamos dividindo pelo dado
de população já coletado, em `src/cleaning/build_coverage.py` (ver decisão
em `docs/decisoes_limpeza.md`).
"""

import argparse
import csv
import io
import os

import boto3
import requests
from botocore.client import Config

from src.config import MINIO_ACCESS_KEY, MINIO_ENDPOINT, MINIO_SECRET_KEY


SIDRA_URL = "https://apisidra.ibge.gov.br/values/t/5938/n6/all/v/37/p/{year}"
BUCKET_RAW = os.getenv("MINIO_RAW_BUCKET", "raw")


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
    )


def download_pib(year: int) -> tuple[io.BytesIO, int]:
    response = requests.get(SIDRA_URL.format(year=year), timeout=60)
    response.raise_for_status()
    rows = response.json()
    if not rows:
        raise RuntimeError(f"IBGE não retornou dados de PIB para {year}")

    headers = rows[0].keys()
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)
    return io.BytesIO(buffer.getvalue().encode("utf-8")), len(rows) - 1


def download_and_upload(year: int) -> None:
    buffer, row_count = download_pib(year)
    key = f"ibge/pib/ano={year}/pib_municipios.csv"
    get_s3_client().upload_fileobj(buffer, BUCKET_RAW, key)
    print(f"[OK] {row_count} municípios enviados para s3://{BUCKET_RAW}/{key}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Baixa PIB municipal do IBGE para o MinIO")
    parser.add_argument(
        "--ano",
        type=int,
        default=2023,
        help="Ano de referência (série disponível: 2002-2023, dado sai com ~2 anos de atraso)",
    )
    download_and_upload(parser.parse_args().ano)
