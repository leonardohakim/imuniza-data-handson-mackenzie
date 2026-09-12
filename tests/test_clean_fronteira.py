"""Testes de `src/cleaning/clean_fronteira.py`.

`clean_fronteira_dataframe` é uma função pura (sem I/O), testada com um
DataFrame sintético que reproduz o formato real da aba "Faixa de Fronteira
- Município 2024" da planilha do IBGE (colunas confirmadas contra o
arquivo real baixado do GeoFTP).
"""

import pandas as pd

from src.cleaning.clean_fronteira import clean_fronteira_dataframe


def _linha(codigo="1100015", nome="Alta Floresta D'Oeste", uf="RO", faixa_sede="sim"):
    return {
        "CD_MUN": codigo,
        "NM_MUN": nome,
        "SIGLA_UF": uf,
        "FAIXA_SEDE": faixa_sede,
    }


def test_faixa_sede_sim_vira_fronteira_1():
    raw = pd.DataFrame([_linha(faixa_sede="sim")])
    clean_df, report = clean_fronteira_dataframe(raw)
    assert clean_df.loc[0, "fronteira"] == 1
    assert report.municipios_com_sede_na_faixa == 1


def test_faixa_sede_nao_vira_fronteira_0_mas_permanece_na_tabela():
    # Município que toca a faixa por área mas cuja sede está fora dela: fica
    # na tabela trusted com fronteira=0 (não é descartado) — ver docstring
    # do módulo sobre a diferença entre "tocar a faixa" e "ser de fronteira".
    raw = pd.DataFrame([_linha(codigo="1100205", nome="Porto Velho", faixa_sede="não")])
    clean_df, report = clean_fronteira_dataframe(raw)
    assert len(clean_df) == 1
    assert clean_df.loc[0, "fronteira"] == 0


def test_faixa_sede_indefinida_e_descartada():
    raw = pd.DataFrame([
        _linha(codigo="1100015", faixa_sede="sim"),
        _linha(codigo="1100031", faixa_sede=None),
    ])
    clean_df, report = clean_fronteira_dataframe(raw)
    assert report.linhas_faixa_sede_indefinida == 1
    assert len(clean_df) == 1
    assert clean_df.loc[0, "codigo_municipio"] == "1100015"


def test_codigo_municipio_invalido_e_descartado():
    raw = pd.DataFrame([
        _linha(codigo="1100015"),
        _linha(codigo="ABC123"),
    ])
    clean_df, report = clean_fronteira_dataframe(raw)
    assert report.codigo_municipio_invalido == 1
    assert len(clean_df) == 1


def test_duplicata_de_municipio_e_removida():
    raw = pd.DataFrame([
        _linha(codigo="1100015", faixa_sede="sim"),
        _linha(codigo="1100015", faixa_sede="sim"),
    ])
    clean_df, report = clean_fronteira_dataframe(raw)
    assert report.duplicatas_removidas == 1
    assert len(clean_df) == 1


def test_colunas_finais_esperadas():
    raw = pd.DataFrame([_linha()])
    clean_df, _ = clean_fronteira_dataframe(raw)
    assert list(clean_df.columns) == ["codigo_municipio", "municipio", "uf", "fronteira"]
