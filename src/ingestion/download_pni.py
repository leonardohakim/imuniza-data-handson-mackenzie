"""Download PNI CSV resources from CKAN directly into MinIO raw storage."""

import hashlib
import os
import re
import argparse
import tempfile
import unicodedata
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse

import boto3
import requests
from botocore.client import Config

from src.config import MINIO_ACCESS_KEY, MINIO_ENDPOINT, MINIO_SECRET_KEY


CKAN_BASE = "https://dadosabertos.saude.gov.br/api/3/action/package_show"
DATASET_PAGE = "https://dadosabertos.saude.gov.br/dataset/{dataset_slug}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

BUCKET_RAW = os.getenv("MINIO_RAW_BUCKET", "bronze")
MONTH_ORDER = {
    "janeiro": 1,
    "fevereiro": 2,
    "março": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
    )


def list_resources(dataset_slug: str) -> list[dict]:
    try:
        response = requests.get(CKAN_BASE, params={"id": dataset_slug}, headers=HEADERS, timeout=60)
        if response.ok:
            payload = response.json()
            if not payload.get("success"):
                raise RuntimeError(f"CKAN respondeu erro para {dataset_slug}: {payload}")
            return payload["result"]["resources"]
    except requests.RequestException:
        print(f"[AVISO] Falha na API CKAN para {dataset_slug}. Tentando scraping da página...")

    return list_resources_from_page(dataset_slug)


def list_resources_from_page(dataset_slug: str) -> list[dict]:
    page_url = DATASET_PAGE.format(dataset_slug=dataset_slug)
    page = requests.get(page_url, headers=HEADERS, timeout=60)
    page.raise_for_status()

    resource_paths = dict.fromkeys(
        re.findall(r'href="(/dataset/[^"/]+/resource/[a-f0-9-]+)"', page.text)
    )
    resources = []
    for resource_path in resource_paths:
        resource_page = requests.get(urljoin(page_url, resource_path), headers=HEADERS, timeout=60)
        resource_page.raise_for_status()
        csv_url_match = re.search(
            r"https?://[^\"<> ]+\.(?:zip|csv)(?:\?[^\"<> ]*)?",
            resource_page.text,
            flags=re.IGNORECASE,
        )
        if not csv_url_match:
            continue

        title_match = re.search(r'<h1[^>]*>(.*?)</h1>', resource_page.text, flags=re.S)
        name = re.sub(r"<[^>]+>", "", title_match.group(1)).strip() if title_match else resource_path.rsplit("/", 1)[-1]
        resources.append(
            {
                "name": unescape(name),
                "format": "CSV",
                "url": unescape(csv_url_match.group(0)),
            }
        )
    return resources


def selecionar_csv_mensal(resources: list[dict]) -> list[dict]:
    """Select and order only the 12 monthly CSV resources from a dataset."""
    selected = [
        resource
        for resource in resources
        if (resource.get("format") or "").upper() == "CSV"
        and "/PNI/csv/" in resource.get("url", "")
    ]
    return sorted(
        selected,
        key=lambda resource: next(
            (number for month, number in MONTH_ORDER.items() if month in resource.get("name", "").lower()),
            99,
        ),
    )


def download_to_temp(url: str) -> tuple[Path, str, int]:
    """Stream a resource to disk while calculating its SHA-256 hash."""
    hasher = hashlib.sha256()
    temporary_file = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    temporary_path = Path(temporary_file.name)
    size = 0

    try:
        with temporary_file:
            with requests.get(url, stream=True, headers=HEADERS, timeout=300) as response:
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=8 * 1024 * 1024):
                    if not chunk:
                        continue
                    temporary_file.write(chunk)
                    hasher.update(chunk)
                    size += len(chunk)
        return temporary_path, hasher.hexdigest(), size
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def upload_file(s3, path: Path, bucket: str, key: str) -> None:
    """Upload a local file using boto3 multipart transfer when necessary."""
    s3.upload_file(str(path), bucket, key)


def download_and_upload(dataset_slug: str, ano: int) -> None:
    s3 = get_s3_client()
    resources = list_resources(dataset_slug)
    print(f"[{dataset_slug}] {len(resources)} recursos encontrados")

    for resource in selecionar_csv_mensal(resources):
        url = resource.get("url")
        file_format = (resource.get("format") or "").upper()
        name = resource.get("name", "sem_nome")

        if file_format != "CSV" or not url:
            continue

        print(f"  baixando: {name} -> {url}")
        temporary_path = None
        try:
            temporary_path, sha256, size = download_to_temp(url)
            safe_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
            safe_name = re.sub(r"[^a-zA-Z0-9]+", "_", safe_name).strip("_").lower()
            extension = os.path.splitext(urlparse(url).path)[1] or ".csv"
            key = f"pni/ano={ano}/{safe_name}{extension}"
            upload_file(s3, temporary_path, BUCKET_RAW, key)
            print(
                f"  [OK] enviado para s3://{BUCKET_RAW}/{key} "
                f"({size} bytes, sha256={sha256})"
            )
        except Exception as error:
            print(f"  [FALHOU] {name}: {error}")
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Baixa os CSVs mensais do PNI para o MinIO")
    parser.add_argument("--ano", type=int, default=2024)
    parser.add_argument("--dataset-slug")
    args = parser.parse_args()
    dataset_slug = args.dataset_slug or (
        "doses-aplicadas-pelo-programa-de-nacional-de-imunizacoes-pni-"
        f"{args.ano}"
    )
    download_and_upload(dataset_slug=dataset_slug, ano=args.ano)