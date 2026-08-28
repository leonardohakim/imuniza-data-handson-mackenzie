"""Download municipal population estimates from IBGE SIDRA into MinIO."""

import argparse
import csv
import io
import os

import boto3
import requests
from botocore.client import Config

from src.config import MINIO_ACCESS_KEY, MINIO_ENDPOINT, MINIO_SECRET_KEY


SIDRA_URL = "https://apisidra.ibge.gov.br/values/t/6579/n6/all/v/9324/p/{year}"
BUCKET_RAW = os.getenv("MINIO_RAW_BUCKET", "bronze")


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
    )


def download_population(year: int) -> tuple[io.BytesIO, int]:
    response = requests.get(SIDRA_URL.format(year=year), timeout=60)
    response.raise_for_status()
    rows = response.json()
    if not rows:
        raise RuntimeError(f"IBGE não retornou dados para {year}")

    headers = rows[0].keys()
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)
    return io.BytesIO(buffer.getvalue().encode("utf-8")), len(rows) - 1


def download_and_upload(year: int) -> None:
    buffer, row_count = download_population(year)
    key = f"ibge/populacao/ano={year}/populacao_municipios.csv"
    get_s3_client().upload_fileobj(buffer, BUCKET_RAW, key)
    print(f"[OK] {row_count} municípios enviados para s3://{BUCKET_RAW}/{key}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Baixa população municipal do IBGE para o MinIO")
    parser.add_argument("--ano", type=int, default=2024)
    download_and_upload(parser.parse_args().ano)