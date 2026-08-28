"""Clean the raw monthly PNI dose CSVs and aggregate them into the trusted layer.

Por que a resolução de colunas é flexível (e não uma lista fixa)
------------------------------------------------------------------
O `inspect_pni.py` (Etapa 1) foi feito justamente porque não tínhamos certeza
dos nomes exatos das colunas nos CSVs do PNI antes de baixá-los — e esses
nomes podem variar entre datasets/anos do OpenDataSUS (ex.: com ou sem
prefixo `paciente_`, `estabelecimento_`, `co_` vs `codigo_`, etc.).
Em vez de hard-codar nomes que ainda não foram confirmados contra o dado
real, este módulo procura, por padrão (substring, case-insensitive), a
coluna mais provável para cada campo que precisamos. Rode
`python -m src.ingestion.inspect_pni --ano <ano> --mes <mes>` primeiro para
ver as colunas reais; se o resolver não encontrar alguma, ajuste os
candidatos em `COLUMN_CANDIDATES` abaixo — é o único lugar que precisa mudar.

Decisões de limpeza (documentadas)
------------------------------------------------------------------
- Linhas sem código de município válido (7 dígitos) são descartadas: sem
  município não há como juntar com a população do IBGE nem calcular
  cobertura.
- Linhas sem data de aplicação válida são descartadas: não dá para agregar
  por mês sem data.
- Duplicatas exatas (mesma linha completa) são removidas — indicam erro de
  extração/join na fonte, não doses reais adicionais.
- Município-mês com contagem de doses fora de [Q1 - 3*IQR, Q3 + 3*IQR] (IQR
  calculado sobre todos os municípios daquele mês) é sinalizado como
  outlier em uma coluna `outlier_iqr`, mas **não é removido** — pode ser um
  polo regional de vacinação (concentra aplicação de municípios vizinhos) e
  merecer investigação na Etapa 2, não descarte automático.
"""

import argparse
import io
import os
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import boto3
import pandas as pd
from botocore.client import Config

from src.config import MINIO_ACCESS_KEY, MINIO_ENDPOINT, MINIO_SECRET_KEY

BUCKET_RAW = os.getenv("MINIO_RAW_BUCKET", "raw")
BUCKET_TRUSTED = os.getenv("MINIO_TRUSTED_BUCKET", "trusted")

# Ordem de prioridade dos candidatos para cada campo que precisamos.
# Ajuste aqui se `inspect_pni.py` mostrar nomes diferentes dos previstos.
COLUMN_CANDIDATES: dict[str, list[str]] = {
    "codigo_municipio": [
        "paciente_endereco_coibgemunicipio",
        "estabelecimento_municipio_codigo",
        "co_municipio",
        "codigo_municipio",
        "municipio_ibge",
    ],
    "data_aplicacao": [
        "vacina_dataaplicacao",
        "data_aplicacao",
        "dt_aplicacao",
    ],
    "vacina_nome": [
        "vacina_nome",
        "vacina_descricao",
        "no_vacina",
    ],
    "dose": [
        "vacina_descricao_dose",
        "dose",
        "no_dose",
    ],
    "paciente_idade": [
        "paciente_idade",
        "idade",
    ],
}


@dataclass
class CleaningReport:
    arquivo: str = ""
    linhas_lidas: int = 0
    colunas_resolvidas: dict = field(default_factory=dict)
    municipio_invalido: int = 0
    data_invalida: int = 0
    duplicatas_removidas: int = 0
    linhas_finais: int = 0
    municipios_mes_outliers: int = 0

    def to_text(self) -> str:
        linhas = [
            f"Relatório de limpeza — PNI ({self.arquivo})",
            "=" * 40,
            f"Linhas lidas do raw: {self.linhas_lidas}",
            f"Colunas resolvidas: {self.colunas_resolvidas}",
            f"Linhas com código de município inválido removidas: {self.municipio_invalido}",
            f"Linhas com data de aplicação inválida removidas: {self.data_invalida}",
            f"Duplicatas exatas removidas: {self.duplicatas_removidas}",
            f"Linhas finais (após limpeza, antes de agregar): {self.linhas_finais}",
            f"Município-mês sinalizados como outlier (IQR): {self.municipios_mes_outliers}",
        ]
        return "\n".join(linhas)


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
    )


def resolve_column(df: pd.DataFrame, field_name: str) -> str:
    """Find the real column name for a logical field using substring match."""
    candidates = COLUMN_CANDIDATES[field_name]
    lower_columns = {column.lower(): column for column in df.columns}

    for candidate in candidates:
        if candidate.lower() in lower_columns:
            return lower_columns[candidate.lower()]

    for candidate in candidates:
        for lower_name, original_name in lower_columns.items():
            if candidate.lower() in lower_name:
                return original_name

    raise KeyError(
        f"Nenhuma coluna encontrada para '{field_name}' entre os candidatos "
        f"{candidates}. Colunas disponíveis: {list(df.columns)}. "
        "Rode inspect_pni.py e ajuste COLUMN_CANDIDATES."
    )


def parse_application_dates(raw_dates: pd.Series) -> pd.Series:
    """Parse dates without relying on dayfirst heuristics (ambiguous/unsafe).

    Detecta o formato pela amostra em vez de assumir DD/MM/YYYY ou deixar o
    pandas adivinhar: `dayfirst=True`/`False` só resolve a ambiguidade para
    casos como "05/01/2025", mas inverte dia e mês silenciosamente quando o
    formato real é o outro. Aqui testamos os formatos esperados
    explicitamente (`%Y-%m-%d` primeiro, por ser o padrão mais comum nos
    exports do DATASUS/RNDS, depois `%d/%m/%Y`) e usamos o que casar com mais
    valores da amostra.
    """
    sample = raw_dates.dropna().astype(str).head(500)
    candidate_formats = ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"]
    best_format, best_matches = None, -1
    for date_format in candidate_formats:
        matches = pd.to_datetime(sample, format=date_format, errors="coerce").notna().sum()
        if matches > best_matches:
            best_format, best_matches = date_format, matches

    if best_matches == 0:
        # Nenhum formato conhecido casou — deixa o pandas tentar de forma
        # genérica (sem dayfirst) e sinaliza no relatório via NaT explícitos.
        return pd.to_datetime(raw_dates, errors="coerce")

    return pd.to_datetime(raw_dates, format=best_format, errors="coerce")


def read_monthly_zip(zip_bytes: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        csv_members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if not csv_members:
            raise RuntimeError("Nenhum CSV encontrado dentro do ZIP do PNI")
        with archive.open(csv_members[0]) as csv_file:
            return pd.read_csv(csv_file, sep=";", encoding="latin1", dtype=str, low_memory=False)


def clean_month_dataframe(raw_df: pd.DataFrame, source_name: str) -> tuple[pd.DataFrame, CleaningReport]:
    report = CleaningReport(arquivo=source_name, linhas_lidas=len(raw_df))
    df = raw_df.copy()

    resolved = {
        field_name: resolve_column(df, field_name)
        for field_name in ("codigo_municipio", "data_aplicacao", "vacina_nome")
    }
    for field_name in ("dose", "paciente_idade"):
        try:
            resolved[field_name] = resolve_column(df, field_name)
        except KeyError:
            resolved[field_name] = None
    report.colunas_resolvidas = resolved

    df = df.rename(columns={
        original: logical for logical, original in resolved.items() if original is not None
    })

    df["codigo_municipio"] = (
        df["codigo_municipio"].astype(str).str.extract(r"(\d+)", expand=False).str.zfill(7)
    )
    municipio_invalido = ~df["codigo_municipio"].str.match(r"^\d{7}$", na=False)
    report.municipio_invalido = int(municipio_invalido.sum())
    df = df.loc[~municipio_invalido].copy()

    df["data_aplicacao"] = parse_application_dates(df["data_aplicacao"])
    data_invalida = df["data_aplicacao"].isna()
    report.data_invalida = int(data_invalida.sum())
    df = df.loc[~data_invalida].copy()

    duplicadas = df.duplicated()
    report.duplicatas_removidas = int(duplicadas.sum())
    df = df.loc[~duplicadas].copy()

    report.linhas_finais = len(df)

    df["ano_mes"] = df["data_aplicacao"].dt.to_period("M").astype(str)
    aggregation_keys = ["codigo_municipio", "ano_mes"]
    if resolved.get("vacina_nome"):
        aggregation_keys.append("vacina_nome")

    aggregated = (
        df.groupby(aggregation_keys, dropna=False)
        .size()
        .reset_index(name="doses_aplicadas")
    )

    monthly_totals = aggregated.groupby(["codigo_municipio", "ano_mes"])["doses_aplicadas"].sum().reset_index()
    q1, q3 = monthly_totals["doses_aplicadas"].quantile([0.25, 0.75])
    iqr = q3 - q1
    lower_bound, upper_bound = q1 - 3 * iqr, q3 + 3 * iqr
    monthly_totals["outlier_iqr"] = ~monthly_totals["doses_aplicadas"].between(lower_bound, upper_bound)
    report.municipios_mes_outliers = int(monthly_totals["outlier_iqr"].sum())

    aggregated = aggregated.merge(
        monthly_totals[["codigo_municipio", "ano_mes", "outlier_iqr"]],
        on=["codigo_municipio", "ano_mes"],
        how="left",
    )

    return aggregated, report


def clean_and_upload(ano: int) -> list[CleaningReport]:
    s3 = get_s3_client()
    prefix = f"pni/ano={ano}/"
    response = s3.list_objects_v2(Bucket=BUCKET_RAW, Prefix=prefix)
    objects = response.get("Contents", [])
    if not objects:
        raise RuntimeError(
            f"Nenhum objeto encontrado em s3://{BUCKET_RAW}/{prefix}. "
            "Rode download_pni.py antes de limpar."
        )

    reports = []
    aggregated_frames = []

    for obj in objects:
        key = obj["Key"]
        if not key.lower().endswith((".zip", ".csv")):
            continue

        print(f"[limpando] {key}")
        body = s3.get_object(Bucket=BUCKET_RAW, Key=key)["Body"].read()

        if key.lower().endswith(".zip"):
            raw_df = read_monthly_zip(body)
        else:
            raw_df = pd.read_csv(io.BytesIO(body), sep=";", encoding="latin1", dtype=str, low_memory=False)

        try:
            cleaned_df, report = clean_month_dataframe(raw_df, source_name=Path(key).name)
        except KeyError as error:
            print(f"  [FALHOU] {key}: {error}")
            continue

        reports.append(report)
        aggregated_frames.append(cleaned_df)

        buffer = io.BytesIO()
        cleaned_df.to_parquet(buffer, index=False)
        buffer.seek(0)
        trusted_key = f"pni/ano={ano}/{Path(key).stem}.parquet"
        s3.upload_fileobj(buffer, BUCKET_TRUSTED, trusted_key)

        report_key = f"pni/ano={ano}/_reports/{Path(key).stem}.txt"
        s3.put_object(Bucket=BUCKET_TRUSTED, Key=report_key, Body=report.to_text().encode("utf-8"))
        print(f"  [OK] {report.linhas_finais} linhas -> s3://{BUCKET_TRUSTED}/{trusted_key}")

    if aggregated_frames:
        consolidated = pd.concat(aggregated_frames, ignore_index=True)
        buffer = io.BytesIO()
        consolidated.to_parquet(buffer, index=False)
        buffer.seek(0)
        consolidated_key = f"pni/ano={ano}/doses_aplicadas_consolidado.parquet"
        s3.upload_fileobj(buffer, BUCKET_TRUSTED, consolidated_key)
        print(
            f"[OK] Consolidado do ano ({len(consolidated)} linhas) -> "
            f"s3://{BUCKET_TRUSTED}/{consolidated_key}"
        )

    return reports


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Limpa e agrega os CSVs mensais do PNI (raw -> trusted) no MinIO"
    )
    parser.add_argument("--ano", type=int, default=2025)
    reports = clean_and_upload(parser.parse_args().ano)
    for report in reports:
        print()
        print(report.to_text())
