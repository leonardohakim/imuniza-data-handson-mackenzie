"""Testes de `src/cleaning/clean_cnes.py`.

`clean_cnes_dataframe` é uma função pura (sem I/O), testada com DataFrames
sintéticos que reproduzem o formato real do CSV do CNES — colunas e valores
confirmados rodando `investigar_cnes_schema.py --baixar 0` contra a fonte
real (635.786 estabelecimentos, todos com `CO_IBGE` de exatamente 6
dígitos).
"""

import pandas as pd

from src.cleaning.clean_cnes import clean_cnes_dataframe


def _estabelecimento(co_cnes="1", co_ibge="355030", ambulatorial_sus="SIM"):
    # Só as colunas usadas por clean_cnes_dataframe — o CSV real tem 36.
    return {
        "CO_CNES": co_cnes,
        "CO_IBGE": co_ibge,
        "CO_AMBULATORIAL_SUS": ambulatorial_sus,
    }


def test_agrega_contagem_total_por_municipio():
    raw = pd.DataFrame([
        _estabelecimento(co_cnes="1", co_ibge="355030"),
        _estabelecimento(co_cnes="2", co_ibge="355030"),
        _estabelecimento(co_cnes="3", co_ibge="110001"),
    ])
    clean_df, report = clean_cnes_dataframe(raw)

    por_municipio = clean_df.set_index("codigo_municipio")["qtd_estabelecimentos_saude"]
    assert por_municipio["355030"] == 2
    assert por_municipio["110001"] == 1
    assert report.municipios_finais == 2


def test_conta_separadamente_estabelecimentos_com_atendimento_ambulatorial_sus():
    raw = pd.DataFrame([
        _estabelecimento(co_cnes="1", co_ibge="355030", ambulatorial_sus="SIM"),
        _estabelecimento(co_cnes="2", co_ibge="355030", ambulatorial_sus="NAO"),
        _estabelecimento(co_cnes="3", co_ibge="355030", ambulatorial_sus="SIM"),
    ])
    clean_df, _ = clean_cnes_dataframe(raw)

    sao_paulo = clean_df.set_index("codigo_municipio").loc["355030"]
    assert sao_paulo["qtd_estabelecimentos_saude"] == 3
    assert sao_paulo["qtd_estabelecimentos_saude_sus"] == 2


def test_descarta_codigo_municipio_fora_do_padrao_6_digitos():
    # Diferente de população/PIB/área (7 dígitos do IBGE), o CNES usa o
    # padrão DATASUS de 6 dígitos — mesmo critério do PNI.
    raw = pd.DataFrame([
        _estabelecimento(co_cnes="1", co_ibge="355030"),
        _estabelecimento(co_cnes="2", co_ibge="3550308"),  # 7 dígitos, não deveria acontecer no CNES real
    ])
    clean_df, report = clean_cnes_dataframe(raw)

    assert report.codigo_municipio_invalido == 1
    assert list(clean_df["codigo_municipio"]) == ["355030"]


def test_colunas_finais_e_tipos():
    raw = pd.DataFrame([_estabelecimento()])
    clean_df, _ = clean_cnes_dataframe(raw)

    assert list(clean_df.columns) == [
        "codigo_municipio",
        "qtd_estabelecimentos_saude",
        "qtd_estabelecimentos_saude_sus",
    ]
    assert clean_df["qtd_estabelecimentos_saude_sus"].dtype.kind == "i"


def test_dataframe_ordenado_por_codigo_municipio():
    raw = pd.DataFrame([
        _estabelecimento(co_cnes="1", co_ibge="355030"),
        _estabelecimento(co_cnes="2", co_ibge="110001"),
    ])
    clean_df, _ = clean_cnes_dataframe(raw)

    assert list(clean_df["codigo_municipio"]) == ["110001", "355030"]
