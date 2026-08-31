"""Testes de `src/cleaning/clean_ibge.py`.

`clean_population_dataframe` é uma função pura (sem I/O), então testamos
diretamente com DataFrames sintéticos que reproduzem o formato real da API
SIDRA — sem precisar de MinIO nem rede.
"""

import pandas as pd

from src.cleaning.clean_ibge import clean_population_dataframe

# A URL de download_ibge.py já fixa a variável (v/9324) em D2; D2C não varia
# por município, é sempre o código dessa variável (9324). O ano de fato vem
# em D3 (ver clean_pib.py, mesma estrutura de 3 dimensões) — não é lido
# daqui, ver "Decisão de limpeza (bug corrigido)" no topo de clean_ibge.py.
VARIAVEL_POPULACAO_CODIGO = "9324"
VARIAVEL_POPULACAO_NOME = "População residente estimada"


def _linha_metadados_sidra():
    """A API SIDRA retorna essa linha de rótulos como primeiro elemento do
    array quando chamada sem `/h/n` — ver docstring de clean_ibge.py."""
    return {
        "D1C": "Município (Código)",
        "D1N": "Município",
        "D2C": "Variável (Código)",
        "D2N": "Variável",
        "V": "Valor",
        "MC": "Unidade de Medida (Código)",
        "MN": "Unidade de Medida",
        "NN": "Nível Territorial",
    }


def _linha_municipio(codigo="1100015", nome="Alta Floresta D'Oeste", populacao="22787"):
    # D2C/D2N não variam por município: são sempre o código/nome da variável
    # pedida na URL (9324, "População residente estimada"), não o ano.
    return {
        "D1C": codigo,
        "D1N": nome,
        "D2C": VARIAVEL_POPULACAO_CODIGO,
        "D2N": VARIAVEL_POPULACAO_NOME,
        "V": populacao,
        "MC": "45",
        "MN": "Pessoas",
        "NN": "Município",
    }


def test_remove_linha_de_metadados_sidra():
    raw = pd.DataFrame([_linha_metadados_sidra(), _linha_municipio()])

    clean_df, report = clean_population_dataframe(raw, ano=2024)

    assert report.linha_metadados_removida is True
    assert len(clean_df) == 1
    assert clean_df.iloc[0]["codigo_municipio"] == "1100015"


def test_sem_linha_de_metadados_nao_remove_nada_a_mais():
    # Regressão: se por algum motivo a API não mandar a linha de metadados,
    # o pipeline não pode remover municípios de verdade por engano.
    raw = pd.DataFrame([_linha_municipio("1100015"), _linha_municipio("1100023", "Ariquemes")])

    clean_df, report = clean_population_dataframe(raw, ano=2024)

    assert report.linha_metadados_removida is False
    assert len(clean_df) == 2


def test_descarta_populacao_ausente_sem_imputar():
    raw = pd.DataFrame([
        _linha_municipio("1100015", populacao="22787"),
        _linha_municipio("1100023", "Ariquemes", populacao="-"),  # sigilo/ausente
    ])

    clean_df, report = clean_population_dataframe(raw, ano=2024)

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

    clean_df, report = clean_population_dataframe(raw, ano=2024)

    assert report.codigo_municipio_invalido == 2
    assert len(clean_df) == 1
    assert clean_df.iloc[0]["codigo_municipio"] == "1100015"


def test_remove_duplicatas_mantendo_primeira_ocorrencia():
    raw = pd.DataFrame([
        _linha_municipio("1100015", populacao="22787"),
        _linha_municipio("1100015", populacao="99999"),  # duplicata, valor diferente
    ])

    clean_df, report = clean_population_dataframe(raw, ano=2024)

    assert report.duplicatas_removidas == 1
    assert len(clean_df) == 1
    assert clean_df.iloc[0]["populacao"] == 22787  # mantém a primeira


def test_populacao_final_e_inteira_e_ordenada_por_codigo():
    raw = pd.DataFrame([
        _linha_municipio("1100023", "Ariquemes", populacao="109170"),
        _linha_municipio("1100015", "Alta Floresta D'Oeste", populacao="22787"),
    ])

    clean_df, report = clean_population_dataframe(raw, ano=2024)

    assert clean_df["populacao"].dtype == "int64"
    assert list(clean_df["codigo_municipio"]) == ["1100015", "1100023"]
    assert report.linhas_finais == 2


def test_coluna_ano_usa_o_ano_pedido_nao_o_codigo_da_variavel_sidra():
    # Regressão do bug real: uma versão anterior mapeava D2C direto para a
    # coluna "ano", então "ano" saía sempre "9324" (o código da variável
    # população residente estimada, fixo na URL de download_ibge.py),
    # nunca o ano de fato. A coluna "ano" tem que vir do parâmetro `ano`,
    # não do corpo da resposta da API.
    raw = pd.DataFrame([_linha_municipio("1100015")])

    clean_df, _ = clean_population_dataframe(raw, ano=2024)

    assert clean_df.iloc[0]["ano"] == "2024"
    assert clean_df.iloc[0]["ano"] != VARIAVEL_POPULACAO_CODIGO
