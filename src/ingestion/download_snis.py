"""Download do painel de saneamento básico (SNIS) via Base dos Dados para o MinIO.

O SNIS (Sistema Nacional de Informações sobre Saneamento) foi descontinuado
em 2023 e substituído pelo SINISA, cujo portal oficial (gov.br) ainda não
disponibiliza dado histórico para download direto (só páginas de cadastro/
contato no momento em que este script foi escrito). A fonte usada aqui é o
projeto **Base dos Dados** (https://basedosdados.org), que republica a série
histórica completa do SNIS (1995-2022) já limpa e com `id_municipio` no
formato de 7 dígitos do IBGE — tabela `br_mdr_snis.municipio_agua_esgoto`
("Serviços de Água e Esgoto nos Municípios").

Diferente das demais fontes deste pipeline, este é o **painel histórico
inteiro** (todos os anos, ~119 mil linhas), não um arquivo já filtrado por
ano — a filtragem para o ano de referência usado neste projeto (2022, o mais
completo da série, ver `clean_snis.py`) acontece na limpeza, não aqui, mesmo
princípio de "raw nunca é reescrita" usado no resto do pipeline.

A Base dos Dados expõe um endpoint de download direto (sem necessidade de
conta Google Cloud/BigQuery nem autenticação) que devolve um CSV comprimido
em gzip; este script só baixa os bytes brutos e grava no `raw`, sem nenhum
parsing.

Nota operacional: o ambiente de nuvem usado nesta sessão não conseguiu
alcançar `basedosdados.org` (a chamada retornou erro de proxy/túnel, não uma
página de bloqueio explícita como o WAF do GeoFTP do IBGE — ver
`download_area.py`/`download_fronteira.py`). Não foi possível confirmar se
essa restrição também vale para outras redes; se este script falhar com erro
de conexão, o mesmo workaround já usado para fronteira/área se aplica: baixar
o arquivo por fora (ex.: navegador) e subir manualmente para o bucket `raw`
na chave `RAW_KEY` abaixo antes de rodar `clean_snis.py`.
"""

import io
import os

import boto3
import requests
from botocore.client import Config

from src.config import MINIO_ACCESS_KEY, MINIO_ENDPOINT, MINIO_SECRET_KEY

# Endpoint de download direto da tabela br_mdr_snis.municipio_agua_esgoto
# (Serviços de Água e Esgoto nos Municípios), confirmado funcionando nesta
# sessão via fetch de navegador: devolve um CSV.gz com Content-Disposition
# "attachment; filename=br_mdr_snis_municipio_agua_esgoto.csv.gz".
SNIS_URL = "https://basedosdados.org/api/tables/downloadTable?p=YnJfbWRyX3NuaXM=&q=bXVuaWNpcGlvX2FndWFfZXNnb3Rv&d=dHJ1ZQ==&s=ZnJlZQ=="

BUCKET_RAW = os.getenv("MINIO_RAW_BUCKET", "raw")
RAW_KEY = "basedosdados/snis/municipio_agua_esgoto.csv.gz"


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
    )


def download_snis() -> io.BytesIO:
    response = requests.get(SNIS_URL, timeout=120)
    response.raise_for_status()
    if not response.content:
        raise RuntimeError("Base dos Dados não retornou conteúdo para a tabela de SNIS")
    return io.BytesIO(response.content)


def download_and_upload() -> None:
    buffer = download_snis()
    get_s3_client().upload_fileobj(buffer, BUCKET_RAW, RAW_KEY)
    print(f"[OK] Painel de saneamento (SNIS) enviado para s3://{BUCKET_RAW}/{RAW_KEY}")


if __name__ == "__main__":
    download_and_upload()
