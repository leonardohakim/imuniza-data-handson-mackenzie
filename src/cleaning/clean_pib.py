"""Clean the raw IBGE municipal GDP (PIB) CSV and promote it to the trusted layer.

Mesma decisão de limpeza da linha de metadados do SIDRA documentada em
`clean_ibge.py` (a API retorna uma linha de rótulos como primeiro elemento
do array JSON quando chamada sem `/h/n`; ela é descartada aqui, não na
ingestão, para preservar a raw como veio da fonte).

Mesma estrutura de três dimensões da Tabela 6579 (população): D1 Município,
D2 Variável (aqui sempre `37`, "PIB a preços correntes", porque a tabela
expõe várias variáveis — participações percentuais etc. — mas só pedimos a
37 na ingestão), D3 Ano de referência. (Uma versão anterior deste docstring
dizia que a Tabela 6579 não tinha a dimensão de Variável e que D2 já era o
ano lá — isso estava errado, e foi exatamente o bug corrigido em
`clean_ibge.py`; ver `docs/decisoes_limpeza.md`, seção 8.)
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
    "D2C": "variavel_codigo",
    "D2N": "variavel_nome",
    "D3C": "ano",
    "D3N": "ano_nome",
    "V": "pib_mil_reais",
    "MC": "unidade_medida_codigo",
    "MN": "unidade_medida",
    "NN": "nivel_territorial",
}


@dataclass
class CleaningReport:
    linhas_lidas: int = 0
    linha_metadados_removida: bool = False
    linhas_pib_invalido: int = 0
    duplicatas_removidas: int = 0
    codigo_municipio_invalido: int = 0
    linhas_finais: int = 0
    notas: list = field(default_factory=list)

    def to_text(self) -> str:
        linhas = [
            "Relatório de limpeza — PIB municipal IBGE",
            "=" * 40,
            f"Linhas lidas do raw: {self.linhas_lidas}",
            f"Linha de metadados SIDRA removida: {'sim' if self.linha_metadados_removida else 'não'}",
            f"Linhas com PIB não numérico removidas: {self.linhas_pib_invalido}",
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


def clean_pib_dataframe(raw_df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
    """Aplica as decisões de limpeza ao dataframe bruto de PIB do SIDRA.

    Função pura (sem I/O), no mesmo espírito de `clean_population_dataframe`
    em `clean_ibge.py` — testável isoladamente (ver `tests/test_clean_pib.py`).
    """
    report = CleaningReport(linhas_lidas=len(raw_df))
    df = raw_df.copy()

    # 1) Remove a linha de metadados do SIDRA (ver docstring do módulo).
    valor_numerico = pd.to_numeric(df["V"], errors="coerce")
    linha_metadados = valor_numerico.isna() & df["V"].astype(str).str.contains(
        "[A-Za-z]", regex=True, na=False
    )
    if linha_metadados.any():
        report.linha_metadados_removida = True
        df = df.loc[~linha_metadados].copy()
        valor_numerico = valor_numerico.loc[~linha_metadados]

    df = df.rename(columns=RENAME_MAP)
    df["pib_mil_reais"] = pd.to_numeric(df["pib_mil_reais"], errors="coerce")

    # 2) Descarta (não imputa) municípios com PIB ausente/inválido — mesma
    #    justificativa da população: um valor fabricado distorceria
    #    diretamente qualquer análise de correlação feita com essa coluna.
    pib_invalido = df["pib_mil_reais"].isna()
    report.linhas_pib_invalido = int(pib_invalido.sum())
    df = df.loc[~pib_invalido].copy()

    # 3) Padroniza o código do município para 7 dígitos (padrão IBGE) —
    #    mesmo formato usado em `clean_ibge.py`, para permitir cruzamento
    #    direto com a população sem a conversão de 6/7 dígitos que o PNI
    #    exige (o PIB já vem do próprio IBGE, mesmo sistema de código).
    df["codigo_municipio"] = df["codigo_municipio"].astype(str).str.strip()
    codigo_valido = df["codigo_municipio"].str.match(r"^\d{7}$")
    report.codigo_municipio_invalido = int((~codigo_valido).sum())
    df = df.loc[codigo_valido].copy()

    # 4) Remove duplicatas exatas de município (mantém a primeira ocorrência).
    duplicadas = df.duplicated(subset=["codigo_municipio"])
    report.duplicatas_removidas = int(duplicadas.sum())
    df = df.loc[~duplicadas].copy()

    df["pib_mil_reais"] = df["pib_mil_reais"].astype("float64")
    colunas_finais = ["codigo_municipio", "municipio", "ano", "pib_mil_reais"]
    colunas_presentes = [coluna for coluna in colunas_finais if coluna in df.columns]
    df = df[colunas_presentes].sort_values("codigo_municipio").reset_index(drop=True)

    report.linhas_finais = len(df)
    return df, report


def clean_and_upload(ano: int) -> CleaningReport:
    s3 = get_s3_client()
    raw_key = f"ibge/pib/ano={ano}/pib_municipios.csv"
    obj = s3.get_object(Bucket=BUCKET_RAW, Key=raw_key)
    raw_df = pd.read_csv(io.BytesIO(obj["Body"].read()), dtype=str)

    clean_df, report = clean_pib_dataframe(raw_df)

    trusted_key = f"ibge/pib/ano={ano}/pib_municipios.parquet"
    buffer = io.BytesIO()
    clean_df.to_parquet(buffer, index=False)
    buffer.seek(0)
    s3.upload_fileobj(buffer, BUCKET_TRUSTED, trusted_key)

    report_key = f"ibge/pib/ano={ano}/_cleaning_report.txt"
    s3.put_object(Bucket=BUCKET_TRUSTED, Key=report_key, Body=report.to_text().encode("utf-8"))

    print(f"[OK] {report.linhas_finais} municípios enviados para s3://{BUCKET_TRUSTED}/{trusted_key}")
    print(report.to_text())
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Limpa o PIB municipal (raw -> trusted) no MinIO")
    parser.add_argument("--ano", type=int, default=2023)
    clean_and_upload(parser.parse_args().ano)
