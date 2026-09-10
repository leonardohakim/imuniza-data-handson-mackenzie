"""Download the CNES (estabelecimentos de saúde) national snapshot into MinIO.

Estabelecimentos de saúde por município — proxy de infraestrutura de saúde,
avaliado como feature nova depois de confirmar (via
`investigar_cnes_schema.py`, rodado contra a fonte real) que:

- o arquivo CSV é pequeno o suficiente para baixar de uma vez (~54MB
  zipado, 635.786 estabelecimentos, 5.585 municípios distintos);
- o código de município (coluna `CO_IBGE`, apesar do nome) vem sempre no
  padrão **DATASUS de 6 dígitos**, não no padrão IBGE de 7 dígitos usado
  por população/PIB/área — confirmado contra os 635.786 registros reais
  (100% com exatamente 6 caracteres). É cruzado em `build_coverage.py`
  pela mesma chave truncada já usada para o PNI (`codigo_municipio_datasus`).

Assim como área territorial (ver `download_area.py`), este é um snapshot
único (o cadastro "atual" de estabelecimentos), não uma série histórica
por ano — por isso este script não recebe `--ano` e sempre grava no
mesmo caminho em `raw`. Ver `docs/decisoes_limpeza.md`.

Mesmo portal CKAN do PNI (`dadosabertos.saude.gov.br`) — reaproveita
`list_resources`/`download_to_temp`/`get_s3_client` de `download_pni.py`
em vez de duplicar essa lógica. O dataset tem 3 recursos (mesmo conteúdo
em CSV/JSON/XML); pegamos especificamente o CSV.
"""

import argparse
import os

from src.ingestion.download_pni import download_to_temp, get_s3_client, list_resources, upload_file

BUCKET_RAW = os.getenv("MINIO_RAW_BUCKET", "raw")
DATASET_SLUG = "cnes-cadastro-nacional-de-estabelecimentos-de-saude"


def selecionar_recurso_csv(resources: list[dict]) -> dict:
    """Os 3 recursos do CNES têm o mesmo `name`/`format` reportado pelo CKAN
    (todos aparecem como "CNES Estabelecimentos" | CSV) — só a URL diferencia
    CSV de JSON/XML, daí filtrar pelo sufixo em vez de `format`."""
    for resource in resources:
        url = resource.get("url", "")
        if url.lower().endswith("_csv.zip"):
            return resource
    raise RuntimeError(
        f"Nenhum recurso CSV encontrado para '{DATASET_SLUG}' "
        f"({len(resources)} recursos no total, nenhum terminava em _csv.zip)"
    )


def download_and_upload() -> None:
    s3 = get_s3_client()
    resources = list_resources(DATASET_SLUG)
    print(f"[{DATASET_SLUG}] {len(resources)} recursos encontrados")

    recurso = selecionar_recurso_csv(resources)
    url = recurso["url"]
    print(f"  baixando: {recurso.get('name')} -> {url}")

    temporary_path = None
    try:
        temporary_path, sha256, size = download_to_temp(url)
        key = "cnes/cnes_estabelecimentos.zip"
        upload_file(s3, temporary_path, BUCKET_RAW, key)
        print(f"  [OK] enviado para s3://{BUCKET_RAW}/{key} ({size} bytes, sha256={sha256})")
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Baixa o CNES (estabelecimentos de saúde, snapshot nacional) para o MinIO"
    )
    parser.parse_args()  # sem --ano de propósito, ver docstring do módulo
    download_and_upload()
