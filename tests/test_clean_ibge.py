"""Testes de `src/cleaning/clean_ibge.py`.

`clean_population_dataframe` é uma função pura (sem I/O), então testamos
diretamente com DataFrames sintéticos que reproduzem o formato real da API
SIDRA — sem precisar de MinIO nem rede.
"""

import pandas as pd

from src.cleaning.clean_ibge import clean_population_dataframe


def _linha_metadados_sidra():
    """A API SIDRA retorna essa linha de rótulos como primeiro elemento do
    array quando chamada sem `/h/n` — ver docstring de clean_ibge.py."""
    return {
        "D1C": "Município (Código)",
        "D1N": "Município",
        "D2C": "Ano (Código)",
        "D2N": "Ano",
        "V": "Valor",
        "MC": "Unidade de Medida (Código)",
        "MN": "Unidade de Medida",
        "NN": "Nível Territorial",
    }


def _linha_municipio(codigo="1100015", nome="Alta Floresta D'Oeste", ano="2024", populacao="22787"):
    return {
        "D1C": codigo,
        "D1N": nome,
        "D2C": ano,
        "D2N": ano,
        "V": populacao,
        "MC": "45",
        "MN": "Pessoas",
        "NN": "Município",
    }


def test_remove_linha_de_metadados_sidra():
    raw = pd.DataFrame([_linha_metadados_sidra(), _linha_municipio()])

    clean_df, report = clean_population_dataframe(raw)

    assert report.linha_metadados_removida is True
    assert len(clean_df) == 1
    assert clean_df.iloc[0]["codigo_municipio"] == "1100015"


def test_sem_linha_de_metadados_nao_remove_nada_a_mais():
    # Regressão: se por algum motivo a API não mandar a linha de metadados,
    # o pipeline não pode remover municípios de verdade por engano.
    raw = pd.DataFrame([_linha_municipio("1100015"), _linha_municipio("1100023", "Ariquemes")])

    clean_df, report = clean_population_dataframe(raw)

    assert report.linha_metadados_removida is False
    assert len(clean_df) == 2


def test_descarta_populacao_ausente_sem_imputar():
    raw = pd.DataFrame([
        _linha_municipio("1100015", populacao="22787"),
        _linha_municipio("1100023", "Ariquemes", populacao="-"),  # sigilo/ausente
    ])

    clean_df, report = clean_population_dataframe(raw)

    assert report.linhas_populacao_invalida == 1
    assert len(clean_df) == 1
    assert clean_df.iloc[0]["codigo_municipio"] == "1100015"
    # população não pode ter sido preenchida com média/mediana/zero
    assert "1100023" not in clean_df["codigo_municipio"].values


def test_descarta_codigo_municipio_fora_do_padrao_7_digitos():
    raw = pd.DataFrame([
        _linha_municipio("1100015"),
        _linha_municipio("11000155"),  # 8 dígitos, formato errado
        _linha_municipio("ABC1234"),  # não numérico
    ])

    clean_df, report = clean_population_dataframe(raw)

    assert report.codigo_municipio_invalido == 2
    assert len(clean_df) == 1
    assert clean_df.iloc[0]["codigo_municipio"] == "1100015"


def test_remove_duplicatas_mantendo_primeira_ocorrencia():
    raw = pd.DataFrame([
        _linha_municipio("1100015", populacao="22787"),
        _linha_municipio("1100015", populacao="99999"),  # duplicata, valor diferente
    ])

    clean_df, report = clean_population_dataframe(raw)

    assert report.duplicatas_removidas == 1
    assert len(clean_df) == 1
    assert clean_df.iloc[0]["populacao"] == 22787  # mantém a primeira


def test_populacao_final_e_inteira_e_ordenada_por_codigo():
    raw = pd.DataFrame([
        _linha_municipio("1100023", "Ariquemes", populacao="109170"),
        _linha_municipio("1100015", "Alta Floresta D'Oeste", populacao="22787"),
    ])

    clean_df, report = clean_population_dataframe(raw)

    assert clean_df["populacao"].dtype == "int64"
    assert list(clean_df["codigo_municipio"]) == ["1100015", "1100023"]
    assert report.linhas_finais == 2
