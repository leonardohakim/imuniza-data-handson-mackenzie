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
- Linhas sem código de município válido (6 dígitos — código DATASUS/SUS,
  sem o dígito verificador que o IBGE usa) são descartadas: sem município
  não há como juntar com a população do IBGE nem calcular cobertura. O
  cruzamento com o IBGE (7 dígitos) é feito truncando o código do IBGE
  para 6 dígitos em `build_coverage.py` — ver `docs/decisoes_limpeza.md`.
- Linhas sem data de aplicação válida são descartadas: não dá para agregar
  por mês sem data.
- Duplicatas exatas (mesma linha completa) são removidas — indicam erro de
  extração/join na fonte, não doses reais adicionais.
- Município-mês com contagem de doses fora de [Q1 - 3*IQR, Q3 + 3*IQR] (IQR
  calculado sobre todos os municípios daquele mês) é sinalizado como
  outlier em uma coluna `outlier_iqr`, mas **não é removido** — pode ser um
  polo regional de vacinação (concentra aplicação de municípios vizinhos) e
  merecer investigação na Etapa 2, não descarte automático.

Por que o processamento é em streaming (chunks), não em memória
------------------------------------------------------------------
Os CSVs mensais do PNI são nacionais e grandes (o de abril/2025, por
exemplo, tem ~4GB comprimido — descompactado e carregado como DataFrame
facilmente passa de 15-20GB). Isso não cabe na RAM de uma máquina comum
(nem do Codespace usado para desenvolver isso, que tem 7.8GB). Em vez de
baixar o ZIP inteiro e ler o CSV inteiro de uma vez, este módulo:
1. Lê o objeto do MinIO em blocos pequenos (streaming do S3, via
   `botocore`'s `StreamingBody`), nunca materializando o ZIP inteiro em
   memória ou disco.
2. Descompacta o ZIP também em streaming, com a biblioteca `stream-unzip`
   (que não precisa "seekar" no arquivo, ao contrário do `zipfile` padrão).
3. Lê o CSV descomprimido em pedaços (`chunksize` do pandas) em vez de um
   DataFrame único, limpando e agregando cada pedaço antes de descartá-lo.

Limitação documentada: a remoção de duplicatas exatas (linha completa
repetida) só enxerga duplicatas dentro do mesmo pedaço (chunk), não no
arquivo inteiro — um duplicado que caia em pedaços diferentes não é
detectado. Isso é um trade-off aceito para conseguir processar arquivos
maiores que a RAM disponível; duplicatas exatas tendem a ser raras e, na
prática, adjacentes no arquivo de origem (mesma exportação), então a maior
parte ainda cai no mesmo pedaço.
"""

import argparse
import io
import os
from dataclasses import dataclass, field
from pathlib import Path

import boto3
import pandas as pd
from botocore.client import Config
from stream_unzip import stream_unzip

from src.config import MINIO_ACCESS_KEY, MINIO_ENDPOINT, MINIO_SECRET_KEY

BUCKET_RAW = os.getenv("MINIO_RAW_BUCKET", "raw")
BUCKET_TRUSTED = os.getenv("MINIO_TRUSTED_BUCKET", "trusted")

# Quantas linhas o pandas lê por vez. ~100k linhas de um CSV largo (30+
# colunas de texto) fica na casa de algumas centenas de MB — seguro para
# uma máquina com poucos GB de RAM livre.
CHUNK_SIZE = 100_000
# Tamanho do bloco de bytes lido do S3/MinIO por vez (streaming).
S3_READ_CHUNK_SIZE = 8 * 1024 * 1024

# Ordem de prioridade dos candidatos para cada campo que precisamos.
# Ajuste aqui se `inspect_pni.py` mostrar nomes diferentes dos previstos.
COLUMN_CANDIDATES: dict[str, list[str]] = {
    # Confirmado contra o schema real do PNI (colunas listadas pelo erro de
    # resolução ao rodar contra os dados reais em ago/2026) — mantemos os
    # nomes hipotéticos antigos como fallback, sem custo.
    "codigo_municipio": [
        # Preferimos o município de RESIDÊNCIA do paciente (não o do
        # estabelecimento onde a dose foi aplicada): a métrica de cobertura
        # usa como denominador a população residente (IBGE), então o
        # numerador (doses) precisa ser contado no mesmo critério —
        # doses aplicadas em pacientes de fora do município inflariam a
        # cobertura de municípios-polo (ex.: cidades com grandes hospitais)
        # e subestimariam a de municípios vizinhos.
        "co_municipio_paciente",
        "co_municipio_estabelecimento",
        "paciente_endereco_coibgemunicipio",
        "estabelecimento_municipio_codigo",
        "co_municipio",
        "codigo_municipio",
        "municipio_ibge",
    ],
    "data_aplicacao": [
        "dt_vacina",
        "vacina_dataaplicacao",
        "data_aplicacao",
        "dt_aplicacao",
    ],
    "vacina_nome": [
        # Não há coluna com o nome por extenso da vacina no dataset real;
        # `sg_imunobiologico` (sigla do imunobiológico, ex.: "COVID19",
        # "BCG") é o campo mais próximo do que precisamos para relatórios
        # e agregações por tipo de vacina.
        "sg_imunobiologico",
        "vacina_nome",
        "vacina_descricao",
        "no_vacina",
    ],
    "dose": [
        "co_dose_vacina",
        "ds_tipo_dose",
        "vacina_descricao_dose",
        "dose",
        "no_dose",
    ],
    "paciente_idade": [
        "nu_idade_paciente",
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


class _StreamUnzipReader(io.RawIOBase):
    """Adapta o gerador de bytes descomprimidos do stream_unzip para um
    objeto file-like que o pandas consegue ler incrementalmente."""

    def __init__(self, chunks):
        self._chunks = chunks
        self._buffer = b""

    def readable(self) -> bool:
        return True

    def readinto(self, b) -> int:
        while not self._buffer:
            try:
                self._buffer = next(self._chunks)
            except StopIteration:
                return 0
        n = min(len(b), len(self._buffer))
        b[:n] = self._buffer[:n]
        self._buffer = self._buffer[n:]
        return n


def _s3_object_byte_chunks(s3, bucket: str, key: str, chunk_size: int = S3_READ_CHUNK_SIZE):
    """Lê um objeto do MinIO/S3 em blocos, sem carregar tudo na memória."""
    body = s3.get_object(Bucket=bucket, Key=key)["Body"]
    while True:
        chunk = body.read(chunk_size)
        if not chunk:
            break
        yield chunk


def _resolve_columns(sample_df: pd.DataFrame) -> dict:
    resolved = {
        field_name: resolve_column(sample_df, field_name)
        for field_name in ("codigo_municipio", "data_aplicacao", "vacina_nome")
    }
    for field_name in ("dose", "paciente_idade"):
        try:
            resolved[field_name] = resolve_column(sample_df, field_name)
        except KeyError:
            resolved[field_name] = None
    return resolved


def _clean_and_aggregate_chunk(chunk: pd.DataFrame, resolved: dict, report: CleaningReport) -> pd.DataFrame:
    """Limpa um pedaço (chunk) do CSV e devolve já agregado por município/mês."""
    report.linhas_lidas += len(chunk)
    df = chunk.rename(columns={
        original: logical for logical, original in resolved.items() if original is not None
    })

    # `co_municipio_paciente` traz o código de município do DATASUS/SUS, que
    # tem 6 dígitos — NÃO o código IBGE de 7 dígitos (o 7º dígito do IBGE é
    # só um dígito verificador, que o DATASUS não usa). Confirmado contra os
    # dados reais: preencher com zfill(7) aqui (suposição da hipótese
    # original, escrita sem acesso aos dados) juntava um zero à esquerda a
    # um código de 6 dígitos, produzindo algo que parecia um código IBGE
    # válido mas nunca batia com nenhum município real no cruzamento com a
    # população — todo o dataset refinado saía com 0 doses. Ver decisão
    # correspondente em `docs/decisoes_limpeza.md`.
    df["codigo_municipio"] = (
        df["codigo_municipio"].astype(str).str.extract(r"(\d+)", expand=False).str.zfill(6)
    )
    municipio_invalido = ~df["codigo_municipio"].str.match(r"^\d{6}$", na=False)
    report.municipio_invalido += int(municipio_invalido.sum())
    df = df.loc[~municipio_invalido]

    df["data_aplicacao"] = parse_application_dates(df["data_aplicacao"])
    data_invalida = df["data_aplicacao"].isna()
    report.data_invalida += int(data_invalida.sum())
    df = df.loc[~data_invalida]

    # Duplicatas exatas: só detectadas dentro do próprio chunk (ver
    # docstring do módulo — trade-off necessário para processar em
    # streaming arquivos maiores que a RAM disponível).
    duplicadas = df.duplicated()
    report.duplicatas_removidas += int(duplicadas.sum())
    df = df.loc[~duplicadas]

    report.linhas_finais += len(df)

    df = df.copy()
    df["ano_mes"] = df["data_aplicacao"].dt.to_period("M").astype(str)
    aggregation_keys = ["codigo_municipio", "ano_mes"]
    if resolved.get("vacina_nome"):
        aggregation_keys.append("vacina_nome")

    return df.groupby(aggregation_keys, dropna=False).size().reset_index(name="doses_aplicadas")


def _combine_partial_aggregates(partial_aggregates: list[pd.DataFrame], resolved: dict) -> tuple[pd.DataFrame, int]:
    """Soma as agregações parciais de cada chunk e calcula outliers no total do mês."""
    aggregation_keys = ["codigo_municipio", "ano_mes"]
    if resolved.get("vacina_nome"):
        aggregation_keys.append("vacina_nome")

    combined = pd.concat(partial_aggregates, ignore_index=True)
    aggregated = (
        combined.groupby(aggregation_keys, dropna=False)["doses_aplicadas"].sum().reset_index()
    )

    monthly_totals = aggregated.groupby(["codigo_municipio", "ano_mes"])["doses_aplicadas"].sum().reset_index()
    q1, q3 = monthly_totals["doses_aplicadas"].quantile([0.25, 0.75])
    iqr = q3 - q1
    lower_bound, upper_bound = q1 - 3 * iqr, q3 + 3 * iqr
    monthly_totals["outlier_iqr"] = ~monthly_totals["doses_aplicadas"].between(lower_bound, upper_bound)
    outlier_count = int(monthly_totals["outlier_iqr"].sum())

    aggregated = aggregated.merge(
        monthly_totals[["codigo_municipio", "ano_mes", "outlier_iqr"]],
        on=["codigo_municipio", "ano_mes"],
        how="left",
    )
    return aggregated, outlier_count


def _iter_csv_chunks_from_zip(byte_chunks):
    """Descompacta um ZIP em streaming e devolve um iterador de DataFrames
    (chunks) do primeiro membro .csv encontrado dentro dele."""
    for file_name, _file_size, unzipped_chunks in stream_unzip(byte_chunks):
        name = file_name.decode("utf-8", errors="replace")
        if name.lower().endswith(".csv"):
            reader = io.BufferedReader(_StreamUnzipReader(unzipped_chunks), buffer_size=1024 * 1024)
            yield from pd.read_csv(
                reader, sep=";", encoding="latin1", dtype=str, low_memory=False, chunksize=CHUNK_SIZE
            )
            return
        # Membro que não nos interessa: precisa ser drenado (a API do
        # stream_unzip exige consumir cada membro antes de passar ao próximo).
        for _ in unzipped_chunks:
            pass
    raise RuntimeError("Nenhum CSV encontrado dentro do ZIP do PNI")


def clean_month_stream(csv_chunk_iter, source_name: str) -> tuple[pd.DataFrame, CleaningReport]:
    """Limpa e agrega um arquivo mensal do PNI, lendo-o em pedaços (streaming)."""
    report = CleaningReport(arquivo=source_name)
    resolved: dict | None = None
    partial_aggregates: list[pd.DataFrame] = []

    for chunk in csv_chunk_iter:
        if resolved is None:
            resolved = _resolve_columns(chunk)
            report.colunas_resolvidas = resolved
        partial_aggregates.append(_clean_and_aggregate_chunk(chunk, resolved, report))

    if resolved is None or not partial_aggregates:
        raise RuntimeError(f"{source_name}: arquivo vazio, nada para limpar")

    aggregated, outlier_count = _combine_partial_aggregates(partial_aggregates, resolved)
    report.municipios_mes_outliers = outlier_count
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

        print(f"[limpando] {key} (streaming, {obj['Size'] / 1e9:.2f} GB no raw)")

        if key.lower().endswith(".zip"):
            byte_chunks = _s3_object_byte_chunks(s3, BUCKET_RAW, key)
            csv_chunk_iter = _iter_csv_chunks_from_zip(byte_chunks)
        else:
            body = s3.get_object(Bucket=BUCKET_RAW, Key=key)["Body"]
            csv_chunk_iter = pd.read_csv(
                body, sep=";", encoding="latin1", dtype=str, low_memory=False, chunksize=CHUNK_SIZE
            )

        try:
            cleaned_df, report = clean_month_stream(csv_chunk_iter, source_name=Path(key).name)
        except KeyError as error:
            print(f"  [FALHOU] {key}: {error}")
            continue
        except RuntimeError as error:
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
