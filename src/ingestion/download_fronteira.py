"""Download da lista oficial de municípios da faixa de fronteira (IBGE) para o MinIO.

Faixa de fronteira (Lei 6.634/1979): até a Etapa 3 deste projeto, o "sinal
de fronteira" usado como feature era uma aproximação grosseira por UF (11
estados inteiros marcados como "1" — ver `docs/decisoes_modelagem.md`,
seção 1). O IBGE publica a lista oficial por **município** (edição 2024,
"Municípios da Faixa de Fronteira e Cidades-Gêmeas") no GeoFTP de
organização do território — este script baixa essa planilha.

Diferente das APIs SIDRA (JSON) usadas no resto da ingestão, esta fonte é
um arquivo `.xls` estático publicado diretamente no GeoFTP, sem endpoint de
API. Por isso este script só faz `requests.get` no arquivo e grava os bytes
brutos no `raw`, sem nenhum parsing — a limpeza (extrair só as colunas
relevantes) acontece em `clean_fronteira.py`, mesmo princípio de "raw nunca
é reescrita" usado no resto do pipeline (ver `clean_ibge.py`).

Assim como área territorial (`download_area.py`) e CNES (`download_cnes.py`),
este é um snapshot sem série histórica — não recebe `--ano`.

Nota operacional: `geoftp.ibge.gov.br` bloqueou (WAF) as requisições feitas
a partir do ambiente de nuvem usado nesta sessão (mesmo bloqueio já visto
para a Tabela 4714 de área — ver `download_area.py`). O arquivo raw
efetivamente usado neste projeto foi baixado por fora deste script (rede
local, sem o bloqueio) e enviado manualmente para o bucket `raw` — ver
`docs/decisoes_limpeza.md`, seção 12. Este script continua sendo a forma
correta/reprodutível de obter o dado quando a rede permitir.
"""

import io
import os

import boto3
import requests
from botocore.client import Config

from src.config import MINIO_ACCESS_KEY, MINIO_ENDPOINT, MINIO_SECRET_KEY

# Edição 2024 (mais recente disponível no momento em que isso foi escrito).
# Aba "Faixa de Fronteira - Município 2024" traz uma linha por município que
# intersecta a faixa (~590 no total), com a coluna FAIXA_SEDE indicando se a
# sede do município está de fato dentro da faixa — ver clean_fronteira.py.
FRONTEIRA_URL = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/"
    "municipios_da_faixa_de_fronteira/2024/Mun_Faixa_de_Fronteira_Cidades_Gemeas_2024.xls"
)
BUCKET_RAW = os.getenv("MINIO_RAW_BUCKET", "raw")
RAW_KEY = "ibge/fronteira/municipios_faixa_fronteira.xls"


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
    )


def download_fronteira() -> io.BytesIO:
    response = requests.get(FRONTEIRA_URL, timeout=60)
    response.raise_for_status()
    if not response.content:
        raise RuntimeError("IBGE não retornou conteúdo para a planilha de faixa de fronteira")
    return io.BytesIO(response.content)


def download_and_upload() -> None:
    buffer = download_fronteira()
    get_s3_client().upload_fileobj(buffer, BUCKET_RAW, RAW_KEY)
    print(f"[OK] Planilha de faixa de fronteira enviada para s3://{BUCKET_RAW}/{RAW_KEY}")


if __name__ == "__main__":
    download_and_upload()
