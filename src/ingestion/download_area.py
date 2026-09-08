"""Download municipal territorial area from IBGE SIDRA into MinIO.

Área territorial (km²) é, na prática, um atributo estático do município —
ao contrário de população, PIB ou doses aplicadas, não faz sentido reprocessar
por `--ano`: a Tabela 4714 do SIDRA só é atualizada quando o IBGE recalcula os
limites municipais (Censo), não a cada coleta anual do projeto. Por isso este
script não recebe `--ano` e grava sempre no mesmo caminho em `raw`
(`ibge/area/area_municipios.csv`), sem partição de ano — decisão documentada
em `docs/decisoes_limpeza.md`.

Usamos a Tabela 4714 (não a 1301, também avaliada): a 4714 traz a área de
referência mais recente (Censo 2022) contra a 1301, que só tem área de 2010 —
ver `investigar_features_novas.py` para a comparação real que confirmou isso.
Pedimos só a variável 6318 ("Área da unidade territorial", em km²), não a
população nem a densidade que a própria tabela também oferece: a população
desta tabela é do Censo 2022, um ano diferente do que o resto do pipeline usa
(2025) — melhor recalcular densidade em `build_coverage.py` a partir da
população já coletada (mesma fonte/ano que o resto do dataset) do que misturar
dois anos de população diferentes numa métrica derivada.
"""

import argparse
import csv
import io
import os

import boto3
import requests
from botocore.client import Config

from src.config import MINIO_ACCESS_KEY, MINIO_ENDPOINT, MINIO_SECRET_KEY

# Tabela 4714, variável 6318 (Área da unidade territorial, km²), todos os
# municípios (n6/all), período mais recente disponível (p/last -> Censo 2022
# no momento em que isso foi confirmado contra a API real).
SIDRA_URL = "https://apisidra.ibge.gov.br/values/t/4714/n6/all/v/6318/p/last"
BUCKET_RAW = os.getenv("MINIO_RAW_BUCKET", "raw")


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
    )


def download_area() -> tuple[io.BytesIO, int]:
    response = requests.get(SIDRA_URL, timeout=60)
    response.raise_for_status()
    rows = response.json()
    if not rows:
        raise RuntimeError("IBGE não retornou dados de área territorial")

    headers = rows[0].keys()
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)
    return io.BytesIO(buffer.getvalue().encode("utf-8")), len(rows) - 1


def download_and_upload() -> None:
    buffer, row_count = download_area()
    key = "ibge/area/area_municipios.csv"
    get_s3_client().upload_fileobj(buffer, BUCKET_RAW, key)
    print(f"[OK] {row_count} municípios enviados para s3://{BUCKET_RAW}/{key}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Baixa área territorial municipal (IBGE/SIDRA) para o MinIO"
    )
    parser.parse_args()  # sem --ano de propósito, ver docstring do módulo
    download_and_upload()
