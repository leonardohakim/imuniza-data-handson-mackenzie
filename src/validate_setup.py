"""Validate the local MinIO setup and external data sources."""

import os
import sys
from urllib.error import URLError
from urllib.request import urlopen

import boto3
import requests
from botocore.client import Config

try:
    from src.config import MINIO_ACCESS_KEY, MINIO_ENDPOINT, MINIO_SECRET_KEY
except ModuleNotFoundError:
    from config import MINIO_ACCESS_KEY, MINIO_ENDPOINT, MINIO_SECRET_KEY


MINIO_HOST = os.getenv("MINIO_HOST", "localhost")
MINIO_API_PORT = os.getenv("MINIO_API_PORT", "9000")
MINIO_CONSOLE_PORT = os.getenv("MINIO_CONSOLE_PORT", "9001")
MINIO_BUCKETS = ("raw", "trusted", "refined")


def check_endpoint(name: str, url: str) -> bool:
    try:
        with urlopen(url, timeout=5) as response:
            status = response.status
    except (URLError, TimeoutError) as error:
        print(f"[FAIL] {name}: {error}")
        return False

    if status < 200 or status >= 400:
        print(f"[FAIL] {name}: HTTP {status}")
        return False

    print(f"[OK] {name}: HTTP {status}")
    return True


def check_minio_buckets() -> bool:
    s3 = boto3.client(
        "s3",
        endpoint_url=f"http://{MINIO_HOST}:{MINIO_API_PORT}",
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
    )

    checks_passed = True
    for bucket in MINIO_BUCKETS:
        try:
            s3.create_bucket(Bucket=bucket)
            print(f"[OK] bucket '{bucket}' criado")
        except s3.exceptions.BucketAlreadyOwnedByYou:
            print(f"[OK] bucket '{bucket}' ja existia")
        except Exception as error:
            print(f"[FAIL] bucket '{bucket}': {error}")
            checks_passed = False
    return checks_passed


def check_source(name: str, url: str) -> bool:
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as error:
        print(f"[FAIL] {name}: {error}")
        return False

    print(f"[OK] {name} respondeu {response.status_code}")
    return True


def main() -> int:
    api_url = f"http://{MINIO_HOST}:{MINIO_API_PORT}/minio/health/live"
    console_url = f"http://{MINIO_HOST}:{MINIO_CONSOLE_PORT}"

    checks_passed = [
        check_endpoint("MinIO API", api_url),
        check_endpoint("MinIO console", console_url),
        check_minio_buckets(),
        check_source(
            "SUS Dados Abertos",
            "https://dadosabertos.saude.gov.br/dataset?groups=vacinacao",
        ),
        check_source("IBGE SIDRA", "https://apisidra.ibge.gov.br"),
    ]
    return 0 if all(checks_passed) else 1


if __name__ == "__main__":
    sys.exit(main())