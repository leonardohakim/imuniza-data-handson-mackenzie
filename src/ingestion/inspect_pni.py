"""Inspect PNI CSV columns without extracting the ZIP or loading it fully."""

import argparse
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import requests

from src.ingestion.download_pni import list_resources, selecionar_csv_mensal


def inspecionar_colunas(url: str, n_linhas: int = 5) -> None:
    """Print ZIP members, CSV columns, and a small sample of rows."""
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as temporary_file:
            temporary_path = Path(temporary_file.name)
            with requests.get(url, stream=True, timeout=300) as response:
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=8 * 1024 * 1024):
                    if chunk:
                        temporary_file.write(chunk)
            temporary_file.flush()

        with zipfile.ZipFile(temporary_path) as archive:
            members = archive.namelist()
            print("Arquivos dentro do zip:", members)
            csv_members = [member for member in members if member.lower().endswith(".csv")]
            if not csv_members:
                raise RuntimeError("Nenhum CSV encontrado dentro do ZIP")

            with archive.open(csv_members[0]) as csv_file:
                sample = pd.read_csv(
                    csv_file,
                    sep=";",
                    nrows=n_linhas,
                    encoding="latin1",
                )
                print("\nColunas encontradas:")
                for column in sample.columns:
                    print(" -", column)
                print("\nAmostra:")
                print(sample)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inspeciona um CSV mensal do PNI")
    parser.add_argument("--ano", type=int, default=2025)
    parser.add_argument("--mes", type=int, default=1)
    parser.add_argument("--linhas", type=int, default=5)
    args = parser.parse_args()

    resources = list_resources(
        "doses-aplicadas-pelo-programa-de-nacional-de-imunizacoes-pni-"
        f"{args.ano}"
    )
    selected = selecionar_csv_mensal(resources)
    if not 1 <= args.mes <= len(selected):
        raise SystemExit(f"Mês inválido: {args.mes}. Recursos disponíveis: {len(selected)}")
    inspecionar_colunas(selected[args.mes - 1]["url"], n_linhas=args.linhas)