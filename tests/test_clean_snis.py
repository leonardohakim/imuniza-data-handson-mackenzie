"""Testes de `src/cleaning/clean_snis.py`.

`clean_snis_dataframe` é uma função pura (sem I/O), testada com um
DataFrame sintético que reproduz o formato do painel histórico da tabela
`br_mdr_snis.municipio_agua_esgoto` (Base dos Dados): uma linha por
município x ano, com `id_municipio` já no formato de 7 dígitos do IBGE.
"""

import pandas as pd

from src.cleaning.clean_snis import ANO_REFERENCIA, clean_snis_dataframe


def _linha(codigo="1100015", ano=ANO_REFERENCIA, agua="95.5", coleta="40.0", tratamento="35.0"):
    return {
        "id_municipio": codigo,
        "ano": ano,
        "indice_atendimento_total_agua": agua,
        "indice_coleta_esgoto": coleta,
        "indice_tratamento_esgoto": tratamento,
    }


def test_filtra_apenas_o_ano_de_referencia():
    raw = pd.DataFrame([_linha(ano=ANO_REFERENCIA), _linha(codigo="1100023", ano="2015")])
    clean_df, report = clean_snis_dataframe(raw)
    assert report.linhas_ano_referencia == 1
    assert len(clean_df) == 1
    assert clean_df.loc[0, "codigo_municipio"] == "1100015"


def test_agua_ausente_e_descartada_nao_imputada():
    raw = pd.DataFrame([
        _linha(codigo="1100015", agua="95.5"),
        _linha(codigo="1100023", agua=None),
    ])
    clean_df, report = clean_snis_dataframe(raw)
    assert report.linhas_agua_ausente == 1
    assert len(clean_df) == 1
    assert clean_df.loc[0, "codigo_municipio"] == "1100015"


def test_esgoto_ausente_nao_descarta_a_linha():
    # Diferente da água: um município com água preenchida mas esgoto vazio
    # permanece na tabela trusted, com NaN em pct_coleta_esgoto/pct_tratamento_esgoto
    # — ver docstring do módulo sobre por que esgoto não segue o mesmo
    # critério "descartar, não imputar" que os demais indicadores obrigatórios.
    raw = pd.DataFrame([_linha(coleta=None, tratamento=None)])
    clean_df, report = clean_snis_dataframe(raw)
    assert len(clean_df) == 1
    assert pd.isna(clean_df.loc[0, "pct_coleta_esgoto"])
    assert pd.isna(clean_df.loc[0, "pct_tratamento_esgoto"])
    assert report.municipios_com_coleta_esgoto == 0
    assert report.municipios_com_tratamento_esgoto == 0


def test_codigo_municipio_invalido_e_descartado():
    raw = pd.DataFrame([_linha(codigo="1100015"), _linha(codigo="ABC123")])
    clean_df, report = clean_snis_dataframe(raw)
    assert report.codigo_municipio_invalido == 1
    assert len(clean_df) == 1


def test_duplicata_de_municipio_e_removida():
    raw = pd.DataFrame([_linha(codigo="1100015"), _linha(codigo="1100015")])
    clean_df, report = clean_snis_dataframe(raw)
    assert report.duplicatas_removidas == 1
    assert len(clean_df) == 1


def test_colunas_finais_esperadas():
    raw = pd.DataFrame([_linha()])
    clean_df, _ = clean_snis_dataframe(raw)
    assert list(clean_df.columns) == [
        "codigo_municipio",
        "ano_referencia_saneamento",
        "pct_atendimento_agua",
        "pct_coleta_esgoto",
        "pct_tratamento_esgoto",
    ]


def test_municipios_com_esgoto_preenchido_contados_no_relatorio():
    raw = pd.DataFrame([
        _linha(codigo="1100015", coleta="40.0", tratamento="35.0"),
        _linha(codigo="1100023", coleta=None, tratamento=None),
    ])
    _, report = clean_snis_dataframe(raw)
    assert report.municipios_com_coleta_esgoto == 1
    assert report.municipios_com_tratamento_esgoto == 1
