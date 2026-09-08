"""Clean the raw IBGE territorial area CSV and promote it to the trusted layer.

Mesmo padrão de limpeza de `clean_ibge.py` (a API SIDRA devolve uma linha de
metadados como primeiro elemento do array JSON, que `download_area.py` grava
tal como veio — a limpeza acontece aqui, não na ingestão, mesmo princípio de
"raw nunca é reescrita" já usado no resto do pipeline). Ver
`docs/decisoes_limpeza.md`.

Diferença em relação a `clean_ibge.py`: não recebe `--ano` (área territorial
não é reprocessada por ano — ver `download_area.py`); o "ano" que aparece nos
dados é o de referência da própria medição do IBGE (D3C, ex.: "2022", ano do
Censo mais recente disponível na Tabela 4714), gravado como
`ano_referencia_area` para deixar claro que não é o mesmo `ano` usado no
resto do dataset refinado (2025).
"""

import argparse
import io
import os
from dataclasses import dataclass, field

import boto3
import pandas as pd
from botocore.client import Config

from src.config import MINIO_ACCESS_KEY, MINIO_ENDPOINT, MINIO_SECRET_KEY

BUCKET_RAW = os.getenv("MINIO_RAW_BUCKET", "raw")
BUCKET_TRUSTED = os.getenv("MINIO_TRUSTED_BUCKET", "trusted")

RENAME_MAP = {
    "D1C": "codigo_municipio",
    "D1N": "municipio",
    "D3C": "ano_referencia_area",
    "V": "area_km2",
}


@dataclass
class CleaningReport:
    linhas_lidas: int = 0
    linha_metadados_removida: bool = False
    linhas_area_invalida: int = 0
    duplicatas_removidas: int = 0
    codigo_municipio_invalido: int = 0
    linhas_finais: int = 0
    notas: list = field(default_factory=list)

    def to_text(self) -> str:
        linhas = [
            "Relatório de limpeza — área territorial IBGE",
            "=" * 40,
            f"Linhas lidas do raw: {self.linhas_lidas}",
            f"Linha de metadados SIDRA removida: {'sim' if self.linha_metadados_removida else 'não'}",
            f"Linhas com área não numérica removidas: {self.linhas_area_invalida}",
            f"Linhas com código de município inválido (!= 7 dígitos) removidas: {self.codigo_municipio_invalido}",
            f"Duplicatas (mesmo código de município) removidas: {self.duplicatas_removidas}",
            f"Linhas finais na camada trusted: {self.linhas_finais}",
        ]
        linhas.extend(f"- {nota}" for nota in self.notas)
        return "\n".join(linhas)


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
    )


def clean_area_dataframe(raw_df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
    """Apply all cleaning decisions to a raw SIDRA territorial-area dataframe."""
    report = CleaningReport(linhas_lidas=len(raw_df))
    df = raw_df.copy()

    # 1) Remove a linha de metadados do SIDRA (mesmo padrão de clean_ibge.py).
    valor_numerico = pd.to_numeric(df["V"], errors="coerce")
    linha_metadados = valor_numerico.isna() & df["V"].astype(str).str.contains(
        "[A-Za-z]", regex=True, na=False
    )
    if linha_metadados.any():
        report.linha_metadados_removida = True
        df = df.loc[~linha_metadados].copy()
        valor_numerico = valor_numerico.loc[~linha_metadados]

    df = df.rename(columns=RENAME_MAP)
    df["area_km2"] = pd.to_numeric(df["area_km2"], errors="coerce")

    # 2) Área ausente/inválida: descartar, não imputar — mesma decisão já
    #    tomada para população em clean_ibge.py, pelo mesmo motivo (uma área
    #    fabricada distorceria diretamente a densidade calculada depois em
    #    build_coverage.py).
    area_invalida = df["area_km2"].isna()
    report.linhas_area_invalida = int(area_invalida.sum())
    df = df.loc[~area_invalida].copy()

    # 3) Padroniza o código do município para 7 dígitos (padrão IBGE).
    df["codigo_municipio"] = df["codigo_municipio"].astype(str).str.strip()
    codigo_valido = df["codigo_municipio"].str.match(r"^\d{7}$")
    report.codigo_municipio_invalido = int((~codigo_valido).sum())
    df = df.loc[codigo_valido].copy()

    # 4) Remove duplicatas exatas de município.
    duplicadas = df.duplicated(subset=["codigo_municipio"])
    report.duplicatas_removidas = int(duplicadas.sum())
    df = df.loc[~duplicadas].copy()

    colunas_finais = ["codigo_municipio", "municipio", "area_km2", "ano_referencia_area"]
    colunas_presentes = [coluna for coluna in colunas_finais if coluna in df.columns]
    df = df[colunas_presentes].sort_values("codigo_municipio").reset_index(drop=True)

    report.linhas_finais = len(df)
    return df, report


def clean_and_upload() -> CleaningReport:
    s3 = get_s3_client()
    raw_key = "ibge/area/area_municipios.csv"
    obj = s3.get_object(Bucket=BUCKET_RAW, Key=raw_key)
    raw_df = pd.read_csv(io.BytesIO(obj["Body"].read()), dtype=str)

    clean_df, report = clean_area_dataframe(raw_df)

    trusted_key = "ibge/area/area_municipios.parquet"
    buffer = io.BytesIO()
    clean_df.to_parquet(buffer, index=False)
    buffer.seek(0)
    s3.upload_fileobj(buffer, BUCKET_TRUSTED, trusted_key)

    report_key = "ibge/area/_cleaning_report.txt"
    s3.put_object(Bucket=BUCKET_TRUSTED, Key=report_key, Body=report.to_text().encode("utf-8"))

    print(f"[OK] {report.linhas_finais} municípios enviados para s3://{BUCKET_TRUSTED}/{trusted_key}")
    print(report.to_text())
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Limpa a área territorial municipal (raw -> trusted) no MinIO"
    )
    parser.parse_args()  # sem --ano de propósito, ver docstring do módulo
    clean_and_upload()
