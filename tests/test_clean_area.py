"""Testes de `src/cleaning/clean_area.py`.

`clean_area_dataframe` é uma função pura (sem I/O), testada com DataFrames
sintéticos que reproduzem o formato real da API SIDRA (Tabela 4714) — o
fixture de São Paulo abaixo usa os valores reais devolvidos pela API,
confirmados rodando `investigar_features_novas.py` contra a fonte real.
"""

import pandas as pd

from src.cleaning.clean_area import clean_area_dataframe


def _linha_metadados_sidra():
    """Mesma linha de rótulos que a API SIDRA devolve como primeiro elemento
    do array (ver docstring de clean_area.py e clean_ibge.py)."""
    return {
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


def _linha_municipio(codigo="3550308", nome="São Paulo (SP)", area="1521.202", ano="2022"):
    # Valores reais de São Paulo, confirmados contra a API (tabela 4714,
    # variável 6318 "Área da unidade territorial").
    return {
        "NC": "6",
        "NN": "Município",
        "MC": "26",
        "MN": "Quilômetros quadrados",
        "V": area,
        "D1C": codigo,
        "D1N": nome,
        "D2C": "6318",
        "D2N": "Área da unidade territorial",
        "D3C": ano,
        "D3N": ano,
    }


def test_remove_linha_de_metadados_sidra():
    raw = pd.DataFrame([_linha_metadados_sidra(), _linha_municipio()])
    clean_df, report = clean_area_dataframe(raw)
    assert report.linha_metadados_removida is True
    assert len(clean_df) == 1


def test_sem_linha_de_metadados_nao_remove_nada_a_mais():
    raw = pd.DataFrame([_linha_municipio(), _linha_municipio(codigo="1100015", nome="Alta Floresta D'Oeste", area="7067.025")])
    clean_df, report = clean_area_dataframe(raw)
    assert report.linha_metadados_removida is False
    assert len(clean_df) == 2


def test_area_e_convertida_para_numerico_com_valor_real():
    raw = pd.DataFrame([_linha_metadados_sidra(), _linha_municipio()])
    clean_df, _ = clean_area_dataframe(raw)
    linha = clean_df.set_index("codigo_municipio").loc["3550308"]
    assert abs(linha["area_km2"] - 1521.202) < 1e-6
    assert linha["ano_referencia_area"] == "2022"


def test_descarta_area_ausente_sem_imputar():
    raw = pd.DataFrame([
        _linha_metadados_sidra(),
        _linha_municipio(),
        _linha_municipio(codigo="1100015", nome="Alta Floresta D'Oeste", area="-"),  # sigilo/indisponível
    ])
    clean_df, report = clean_area_dataframe(raw)
    assert report.linhas_area_invalida == 1
    assert len(clean_df) == 1
    assert "1100015" not in set(clean_df["codigo_municipio"])


def test_descarta_codigo_municipio_fora_do_padrao_7_digitos():
    raw = pd.DataFrame([
        _linha_metadados_sidra(),
        _linha_municipio(),
        _linha_municipio(codigo="12345", nome="codigo invalido"),
    ])
    clean_df, report = clean_area_dataframe(raw)
    assert report.codigo_municipio_invalido == 1
    assert len(clean_df) == 1


def test_remove_duplicatas_mantendo_primeira_ocorrencia():
    raw = pd.DataFrame([
        _linha_metadados_sidra(),
        _linha_municipio(area="1521.202"),
        _linha_municipio(area="9999.999"),  # duplicata do mesmo município
    ])
    clean_df, report = clean_area_dataframe(raw)
    assert report.duplicatas_removidas == 1
    assert len(clean_df) == 1
    assert clean_df.iloc[0]["area_km2"] == 1521.202


def test_colunas_finais_e_tipos():
    raw = pd.DataFrame([_linha_metadados_sidra(), _linha_municipio()])
    clean_df, _ = clean_area_dataframe(raw)
    assert list(clean_df.columns) == ["codigo_municipio", "municipio", "area_km2", "ano_referencia_area"]
    assert clean_df["area_km2"].dtype.kind == "f"
