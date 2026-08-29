"""Join trusted population + trusted PNI doses into the refined coverage metric.

Métrica: cobertura_vacinal_pct = (doses_aplicadas_no_ano / populacao) * 100

Limitação documentada (decisão de escopo)
------------------------------------------------------------------
"Doses aplicadas" não é o mesmo que "pessoas vacinadas": vacinas com
esquema multidose (ex.: 2ª dose, reforço) fazem uma mesma pessoa contar
mais de uma vez no numerador. Sem um identificador único de paciente
consolidado por dose no dataset agregado, tratamos a métrica como
"doses aplicadas por 100 habitantes" — um proxy de intensidade de
vacinação, não de cobertura populacional no sentido estrito (% de pessoas
imunizadas). Isso deve ficar explícito em qualquer gráfico/relatório da
Etapa 2, e é uma reavaliação natural para a Etapa 3 caso os dados
permitam separar por dose (ex.: filtrar só "1ª Dose"/dose única).
"""

import argparse
import io
import os

import boto3
import pandas as pd
from botocore.client import Config

from src.config import MINIO_ACCESS_KEY, MINIO_ENDPOINT, MINIO_SECRET_KEY

BUCKET_TRUSTED = os.getenv("MINIO_TRUSTED_BUCKET", "trusted")
BUCKET_REFINED = os.getenv("MINIO_REFINED_BUCKET", "refined")


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
    )


def load_parquet(s3, bucket: str, key: str) -> pd.DataFrame:
    obj = s3.get_object(Bucket=bucket, Key=key)
    return pd.read_parquet(io.BytesIO(obj["Body"].read()))


def build_coverage(ano: int) -> pd.DataFrame:
    s3 = get_s3_client()

    populacao = load_parquet(
        s3, BUCKET_TRUSTED, f"ibge/populacao/ano={ano}/populacao_municipios.parquet"
    )
    doses = load_parquet(
        s3, BUCKET_TRUSTED, f"pni/ano={ano}/doses_aplicadas_consolidado.parquet"
    )

    doses_por_municipio = (
        doses.groupby("codigo_municipio")["doses_aplicadas"].sum().reset_index()
    )

    # O PNI/DATASUS usa o código de município de 6 dígitos (sem o dígito
    # verificador do IBGE); o IBGE usa 7 dígitos. Confirmado contra os dados
    # reais: cruzar direto por `codigo_municipio` não casava nada (os dois
    # "pareciam" ter 7 dígitos, mas eram sistemas de código diferentes —
    # `clean_pni.py` zero-preenchia o código de 6 dígitos do DATASUS até 7,
    # o que nunca corresponde ao código IBGE real). Os 6 primeiros dígitos
    # do código IBGE identificam o mesmo município que o código DATASUS; o
    # 7º dígito do IBGE é só um dígito verificador, não informação adicional
    # — truncar para 6 dígitos não perde nada para fins de cruzamento. Ver
    # `docs/decisoes_limpeza.md`.
    populacao = populacao.copy()
    populacao["codigo_municipio_datasus"] = populacao["codigo_municipio"].str[:6]

    coverage = populacao.merge(
        doses_por_municipio,
        left_on="codigo_municipio_datasus",
        right_on="codigo_municipio",
        how="left",
        suffixes=("", "_pni"),
    )
    coverage = coverage.drop(columns=["codigo_municipio_datasus", "codigo_municipio_pni"], errors="ignore")
    coverage["doses_aplicadas"] = coverage["doses_aplicadas"].fillna(0).astype("int64")

    # Municípios com população no IBGE mas nenhuma dose registrada no PNI
    # para o ano: mantemos a linha (cobertura = 0%) em vez de descartar —
    # "sem dado de vacinação" é, em si, um sinal relevante para o objetivo
    # do projeto (identificar áreas com baixa cobertura).
    sem_dados_pni = coverage["doses_aplicadas"].eq(0).sum()

    coverage["cobertura_doses_por_100_habitantes"] = (
        coverage["doses_aplicadas"] / coverage["populacao"] * 100
    ).round(2)

    outliers_baixos = coverage.nsmallest(10, "cobertura_doses_por_100_habitantes")
    outliers_altos = coverage.nlargest(10, "cobertura_doses_por_100_habitantes")

    print(f"[INFO] {len(coverage)} municípios no dataset refinado")
    print(f"[INFO] {sem_dados_pni} municípios sem nenhuma dose registrada no PNI para {ano}")
    print("\n[INFO] 10 municípios com menor cobertura (doses/100 hab.):")
    print(outliers_baixos[["codigo_municipio", "municipio", "populacao", "doses_aplicadas", "cobertura_doses_por_100_habitantes"]])
    print("\n[INFO] 10 municípios com maior cobertura (doses/100 hab.) — checar se são polos regionais:")
    print(outliers_altos[["codigo_municipio", "municipio", "populacao", "doses_aplicadas", "cobertura_doses_por_100_habitantes"]])

    buffer = io.BytesIO()
    coverage.to_parquet(buffer, index=False)
    buffer.seek(0)
    refined_key = f"cobertura_vacinal/ano={ano}/cobertura_municipios.parquet"
    s3.upload_fileobj(buffer, BUCKET_REFINED, refined_key)
    print(f"\n[OK] Dataset refinado enviado para s3://{BUCKET_REFINED}/{refined_key}")

    return coverage


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Constrói a métrica de cobertura vacinal por município (trusted -> refined)"
    )
    parser.add_argument("--ano", type=int, default=2025)
    build_coverage(parser.parse_args().ano)
