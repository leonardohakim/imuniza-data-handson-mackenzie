"""Reprocessa o PNI 2025 mes a mes SEM guardar os ZIPs brutos no MinIO.

Cada mes e baixado para um arquivo temporario local (em /tmp, que tem bastante
espaco livre no Codespace), limpo via os mesmos modulos de clean_pni.py
(codigo_municipio corrigido para 6 digitos), o parquet do mes e enviado
para a camada trusted, e o arquivo temporario e apagado antes do proximo mes.
Isso evita o pico de ~18.5GB que baixar tudo de uma vez pro bucket "raw"
causaria (o /workspaces so tem ~19GB livres agora).

No final, le os 7 parquets mensais ja corrigidos em trusted e escreve o
consolidado do ano.

Rodar de dentro da raiz do repo: python3 reprocessar_pni_2025.py
"""

import io
import os
import re
import unicodedata

import pandas as pd

from src.cleaning.clean_pni import (
    BUCKET_TRUSTED,
    _iter_csv_chunks_from_zip,
    clean_month_stream,
    get_s3_client,
)
from src.ingestion.download_pni import (
    download_to_temp,
    list_resources,
    selecionar_csv_mensal,
)

ANO = 2025
DATASET_SLUG = f"doses-aplicadas-pelo-programa-de-nacional-de-imunizacoes-pni-{ANO}"


def local_byte_chunks(path, chunk_size=8 * 1024 * 1024):
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield chunk


def safe_stem(name: str) -> str:
    safe = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "_", safe).strip("_").lower()


def main():
    s3 = get_s3_client()
    resources = selecionar_csv_mensal(list_resources(DATASET_SLUG))
    print(f"[info] {len(resources)} meses encontrados para {ANO}")

    ok, falhou = [], []

    for resource in resources:
        name = resource.get("name", "sem_nome")
        url = resource.get("url")
        stem = safe_stem(name)
        print(f"\n[mes] {name}")

        temp_path = None
        try:
            print("  baixando (temporario local)...")
            temp_path, sha256, size = download_to_temp(url)
            print(f"  baixado: {size / 1e9:.2f} GB")

            csv_chunk_iter = _iter_csv_chunks_from_zip(local_byte_chunks(temp_path))
            cleaned_df, report = clean_month_stream(csv_chunk_iter, source_name=f"{stem}.zip")

            buffer = io.BytesIO()
            cleaned_df.to_parquet(buffer, index=False)
            buffer.seek(0)
            trusted_key = f"pni/ano={ANO}/{stem}.parquet"
            s3.upload_fileobj(buffer, BUCKET_TRUSTED, trusted_key)

            report_key = f"pni/ano={ANO}/_reports/{stem}.txt"
            s3.put_object(Bucket=BUCKET_TRUSTED, Key=report_key, Body=report.to_text().encode("utf-8"))

            print(f"  [OK] {report.linhas_finais} linhas -> s3://{BUCKET_TRUSTED}/{trusted_key}")
            ok.append(stem)
        except Exception as error:
            print(f"  [FALHOU] {name}: {error}")
            falhou.append(name)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    print(f"\n[info] {len(ok)} meses OK, {len(falhou)} falharam: {falhou}")

    if not ok:
        print("[erro] nenhum mes processado com sucesso, sem nada para consolidar.")
        return

    print("\n[consolidando] lendo os parquets mensais da trusted...")
    frames = []
    for stem in ok:
        key = f"pni/ano={ANO}/{stem}.parquet"
        obj = s3.get_object(Bucket=BUCKET_TRUSTED, Key=key)
        frames.append(pd.read_parquet(io.BytesIO(obj["Body"].read())))

    consolidated = pd.concat(frames, ignore_index=True)
    buffer = io.BytesIO()
    consolidated.to_parquet(buffer, index=False)
    buffer.seek(0)
    consolidated_key = f"pni/ano={ANO}/doses_aplicadas_consolidado.parquet"
    s3.upload_fileobj(buffer, BUCKET_TRUSTED, consolidated_key)
    print(f"[OK] Consolidado do ano ({len(consolidated)} linhas) -> s3://{BUCKET_TRUSTED}/{consolidated_key}")


if __name__ == "__main__":
    main()
