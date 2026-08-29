"""Testes de `src/cleaning/build_coverage.py`.

O primeiro teste (`test_cruzamento_ibge_x_datasus_...`) é uma regressão
direta de um bug real: o código de município do PNI/DATASUS tem 6 dígitos e
o do IBGE tem 7 — cruzar direto sem truncar fazia TODO o dataset de
cobertura sair zerado (o merge nunca casava nenhum município), mesmo com
mais de 1 milhão de linhas de doses já processadas. Ver
`docs/decisoes_limpeza.md`, seção 3.
"""

import pandas as pd

from src.cleaning.build_coverage import compute_coverage


def _populacao():
    return pd.DataFrame({
        "codigo_municipio": ["1100015", "1100023", "3550308"],  # 7 dígitos (IBGE)
        "municipio": ["Alta Floresta D'Oeste", "Ariquemes", "São Paulo"],
        "populacao": [22787, 109170, 12000000],
    })


def test_cruzamento_ibge_x_datasus_com_codigos_de_tamanhos_diferentes():
    doses = pd.DataFrame({
        "codigo_municipio": ["110001", "110001", "355030"],  # 6 dígitos (DATASUS)
        "doses_aplicadas": [10, 5, 999],
    })

    coverage = compute_coverage(_populacao(), doses)

    por_municipio = coverage.set_index("codigo_municipio")["doses_aplicadas"]
    assert por_municipio["1100015"] == 15  # soma de 10 + 5
    assert por_municipio["3550308"] == 999
    # o código final continua sendo o de 7 dígitos do IBGE, não o de 6
    assert set(coverage["codigo_municipio"]) == {"1100015", "1100023", "3550308"}
    assert "codigo_municipio_datasus" not in coverage.columns  # coluna auxiliar não vaza pro resultado


def test_municipio_sem_dose_fica_com_zero_nao_com_nan():
    doses = pd.DataFrame({
        "codigo_municipio": ["110001"],
        "doses_aplicadas": [10],
    })

    coverage = compute_coverage(_populacao(), doses)

    ariquemes = coverage.set_index("codigo_municipio").loc["1100023"]
    assert ariquemes["doses_aplicadas"] == 0
    assert ariquemes["cobertura_doses_por_100_habitantes"] == 0.0
    assert not coverage["doses_aplicadas"].isna().any()


def test_calculo_da_cobertura_doses_por_100_habitantes():
    doses = pd.DataFrame({
        "codigo_municipio": ["110001"],
        "doses_aplicadas": [22787],  # == população: deve dar exatamente 100
    })

    coverage = compute_coverage(_populacao(), doses)

    alta_floresta = coverage.set_index("codigo_municipio").loc["1100015"]
    assert alta_floresta["cobertura_doses_por_100_habitantes"] == 100.0


def test_soma_multiplas_linhas_de_dose_do_mesmo_municipio_antes_do_cruzamento():
    # doses_aplicadas_consolidado.parquet tem uma linha por município x mês
    # (x vacina) — o merge precisa somar tudo por município antes de cruzar
    # com a população, não pegar só a última linha.
    doses = pd.DataFrame({
        "codigo_municipio": ["110001", "110001", "110001", "355030"],
        "doses_aplicadas": [100, 200, 300, 1],
    })

    coverage = compute_coverage(_populacao(), doses)

    assert coverage.set_index("codigo_municipio").loc["1100015", "doses_aplicadas"] == 600


# --- PIB per capita (opcional) --------------------------------------------

def _doses_minimas():
    return pd.DataFrame({
        "codigo_municipio": ["110001"],
        "doses_aplicadas": [10],
    })


def test_sem_pib_nao_adiciona_colunas_de_pib():
    coverage = compute_coverage(_populacao(), _doses_minimas(), pib=None)

    assert "pib_mil_reais" not in coverage.columns
    assert "pib_per_capita_reais" not in coverage.columns


def test_pib_per_capita_e_calculado_corretamente():
    # PIB em Mil Reais; per capita = pib_mil_reais * 1000 / populacao.
    pib = pd.DataFrame({
        "codigo_municipio": ["1100015"],  # 7 dígitos, mesmo código do IBGE (sem conversão)
        "pib_mil_reais": [22787.0],  # escolhido para dar exatamente 1000/hab
    })

    coverage = compute_coverage(_populacao(), _doses_minimas(), pib=pib)

    alta_floresta = coverage.set_index("codigo_municipio").loc["1100015"]
    assert alta_floresta["pib_mil_reais"] == 22787.0
    assert alta_floresta["pib_per_capita_reais"] == 1000.0


def test_municipio_sem_pib_fica_com_nan_nao_com_zero():
    # Diferente de doses_aplicadas (onde ausência = 0, um sinal real),
    # ausência de PIB é lacuna de dado: não deve virar 0 artificialmente.
    pib = pd.DataFrame({
        "codigo_municipio": ["1100015"],
        "pib_mil_reais": [22787.0],
    })

    coverage = compute_coverage(_populacao(), _doses_minimas(), pib=pib)

    ariquemes = coverage.set_index("codigo_municipio").loc["1100023"]
    assert pd.isna(ariquemes["pib_mil_reais"])
    assert pd.isna(ariquemes["pib_per_capita_reais"])
