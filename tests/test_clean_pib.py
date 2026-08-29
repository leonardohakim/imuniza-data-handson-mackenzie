"""Testes de `src/cleaning/clean_pib.py`.

Mesma estrutura de `tests/test_clean_ibge.py` (a Tabela 5938 do PIB tem o
mesmo problema de linha de metadados do SIDRA que a Tabela 6579 de
população), mais os testes específicos do PIB: descarte de valor ausente
e o cálculo de PIB per capita feito depois em `build_coverage.py`.
"""

import pandas as pd

from src.cleaning.clean_pib import CleaningReport, clean_pib_dataframe


def _raw_pib_row(codigo_municipio="1100015", municipio="Alta Floresta D'Oeste (RO)", valor="1046343", ano="2023"):
    return {
        "NC": "6",
        "NN": "Município",
        "MC": "40",
        "MN": "Mil Reais",
        "V": valor,
        "D1C": codigo_municipio,
        "D1N": municipio,
        "D2C": "37",
        "D2N": "Produto Interno Bruto a preços correntes",
        "D3C": ano,
        "D3N": ano,
    }


def test_remove_linha_de_metadados_sidra():
    linha_metadados = {
        "NC": "Nível Territorial (Código)",
        "NN": "Nível Territorial",
        "MC": "Unidade de Medida (Código)",
        "MN": "Unidade de Medida",
        "V": "Valor",
        "D1C": "Município (Código)",
        "D1N": "Município",
        "D2C": "Variável (Código)",
        "D2N": "Variável",
        "D3C": "Ano (Código)",
        "D3N": "Ano",
    }
    raw_df = pd.DataFrame([linha_metadados, _raw_pib_row()])

    clean_df, report = clean_pib_dataframe(raw_df)

    assert report.linha_metadados_removida is True
    assert len(clean_df) == 1


def test_nao_remove_linha_valida_por_engano():
    raw_df = pd.DataFrame([_raw_pib_row(), _raw_pib_row(codigo_municipio="1100023", valor="5219156")])

    clean_df, report = clean_pib_dataframe(raw_df)

    assert report.linha_metadados_removida is False
    assert len(clean_df) == 2


def test_descarta_pib_ausente_sem_imputar():
    raw_df = pd.DataFrame([_raw_pib_row(), _raw_pib_row(codigo_municipio="1100023", valor="-")])

    clean_df, report = clean_pib_dataframe(raw_df)

    assert report.linhas_pib_invalido == 1
    assert len(clean_df) == 1


def test_valida_codigo_municipio_com_7_digitos():
    raw_df = pd.DataFrame([_raw_pib_row(), _raw_pib_row(codigo_municipio="12345", valor="999")])

    clean_df, report = clean_pib_dataframe(raw_df)

    assert report.codigo_municipio_invalido == 1
    assert len(clean_df) == 1


def test_remove_duplicatas_mantendo_primeira():
    raw_df = pd.DataFrame([_raw_pib_row(valor="1046343"), _raw_pib_row(valor="9999999")])

    clean_df, report = clean_pib_dataframe(raw_df)

    assert report.duplicatas_removidas == 1
    assert len(clean_df) == 1
    assert clean_df["pib_mil_reais"].iloc[0] == 1046343.0


def test_colunas_finais_e_tipos():
    raw_df = pd.DataFrame([_raw_pib_row()])

    clean_df, report = clean_pib_dataframe(raw_df)

    assert list(clean_df.columns) == ["codigo_municipio", "municipio", "ano", "pib_mil_reais"]
    assert clean_df["pib_mil_reais"].dtype == "float64"
    assert report.linhas_finais == 1
