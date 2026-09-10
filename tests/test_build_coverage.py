"""Testes de `src/cleaning/build_coverage.py`.

O primeiro teste (`test_cruzamento_ibge_x_datasus_...`) é uma regressão
direta de um bug real: o código de município do PNI/DATASUS tem 6 dígitos e
o do IBGE tem 7 — cruzar direto sem truncar fazia TODO o dataset de
cobertura sair zerado (o merge nunca casava nenhum município), mesmo com
mais de 1 milhão de linhas de doses já processadas. Ver
`docs/decisoes_limpeza.md`, seção 3.
"""

import pandas as pd

from src.cleaning.build_coverage import compute_coverage, doses_sem_municipio_correspondente

# Códigos DATASUS (6 dígitos) correspondentes aos municípios de _populacao():
# "1100015" (Alta Floresta D'Oeste) -> "110001"; "3550308" (São Paulo) -> "355030".


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


# --- doses sem município correspondente (achado na auditoria) ------------

def test_doses_sem_municipio_correspondente_detecta_codigo_sem_match():
    # Bug real encontrado nesta auditoria: compute_coverage faz um LEFT JOIN
    # a partir da população, então uma linha de doses com código inválido/sem
    # correspondência é descartada silenciosamente pelo merge, sem contagem
    # nem aviso nenhum — diferente do caso "município sem dose" (sem_dados_pni),
    # que é contado explicitamente.
    doses = pd.DataFrame({
        "codigo_municipio": ["110001", "999999"],  # "999999" não existe na população
        "doses_aplicadas": [10, 50],
    })

    municipios_sem_match, doses_perdidas = doses_sem_municipio_correspondente(_populacao(), doses)

    assert municipios_sem_match == 1
    assert doses_perdidas == 50


# --- área territorial / densidade demográfica (opcional) -----------------

def test_sem_area_nao_adiciona_colunas_de_area():
    coverage = compute_coverage(_populacao(), _doses_minimas(), area=None)

    assert "area_km2" not in coverage.columns
    assert "densidade_hab_km2" not in coverage.columns


def test_densidade_e_calculada_a_partir_da_populacao_do_proprio_dataset():
    # Alta Floresta D'Oeste: população 22.787 (ver _populacao()).
    area = pd.DataFrame({
        "codigo_municipio": ["1100015"],
        "area_km2": [7067.025],
    })

    coverage = compute_coverage(_populacao(), _doses_minimas(), area=area)

    alta_floresta = coverage.set_index("codigo_municipio").loc["1100015"]
    assert alta_floresta["area_km2"] == 7067.025
    assert alta_floresta["densidade_hab_km2"] == round(22787 / 7067.025, 2)


def test_municipio_sem_area_fica_com_nan_nao_com_zero():
    # Mesma decisão de "não imputar" já usada para PIB.
    area = pd.DataFrame({
        "codigo_municipio": ["1100015"],
        "area_km2": [7067.025],
    })

    coverage = compute_coverage(_populacao(), _doses_minimas(), area=area)

    ariquemes = coverage.set_index("codigo_municipio").loc["1100023"]
    assert pd.isna(ariquemes["area_km2"])
    assert pd.isna(ariquemes["densidade_hab_km2"])


def test_doses_sem_municipio_correspondente_zero_quando_tudo_bate():
    municipios_sem_match, doses_perdidas = doses_sem_municipio_correspondente(
        _populacao(), _doses_minimas()
    )

    assert municipios_sem_match == 0
    assert doses_perdidas == 0


# --- CNES (estabelecimentos de saúde, opcional) ---------------------------

def test_sem_cnes_nao_adiciona_colunas_de_cnes():
    coverage = compute_coverage(_populacao(), _doses_minimas(), cnes=None)

    assert "qtd_estabelecimentos_saude" not in coverage.columns
    assert "qtd_estabelecimentos_saude_sus" not in coverage.columns


def test_cnes_e_cruzado_pelo_codigo_datasus_de_6_digitos_nao_pelo_ibge():
    # Mesmo cruzamento truncado já usado para as doses (PNI) — CNES também
    # usa o código de 6 dígitos do DATASUS, não os 7 do IBGE.
    cnes = pd.DataFrame({
        "codigo_municipio": ["110001", "355030"],
        "qtd_estabelecimentos_saude": [12, 4500],
        "qtd_estabelecimentos_saude_sus": [8, 900],
    })

    coverage = compute_coverage(_populacao(), _doses_minimas(), cnes=cnes)

    alta_floresta = coverage.set_index("codigo_municipio").loc["1100015"]
    sao_paulo = coverage.set_index("codigo_municipio").loc["3550308"]
    assert alta_floresta["qtd_estabelecimentos_saude"] == 12
    assert alta_floresta["qtd_estabelecimentos_saude_sus"] == 8
    assert sao_paulo["qtd_estabelecimentos_saude"] == 4500
    assert "codigo_municipio_datasus" not in coverage.columns  # coluna auxiliar não vaza pro resultado


def test_municipio_sem_cnes_fica_com_nan_nao_com_zero():
    # Mesma decisão de "não imputar" já usada para PIB/área: ausência de
    # dado no CNES não vira 0 estabelecimentos fabricado.
    cnes = pd.DataFrame({
        "codigo_municipio": ["110001"],
        "qtd_estabelecimentos_saude": [12],
        "qtd_estabelecimentos_saude_sus": [8],
    })

    coverage = compute_coverage(_populacao(), _doses_minimas(), cnes=cnes)

    ariquemes = coverage.set_index("codigo_municipio").loc["1100023"]
    assert pd.isna(ariquemes["qtd_estabelecimentos_saude"])
    assert pd.isna(ariquemes["qtd_estabelecimentos_saude_sus"])


def test_codigo_municipio_datasus_nao_vaza_mesmo_sem_area_nem_cnes():
    # codigo_municipio_datasus agora só é descartado no fim de
    # compute_coverage (precisa sobreviver até o merge opcional do CNES) —
    # checagem de que continua não vazando quando nem área nem CNES são
    # passados.
    coverage = compute_coverage(_populacao(), _doses_minimas())
    assert "codigo_municipio_datasus" not in coverage.columns


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
