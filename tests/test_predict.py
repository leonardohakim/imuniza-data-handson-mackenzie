"""Testes de `src/inference/predict.py`.

Mesmo princípio dos testes de limpeza: só as funções puras (`preparar_features`,
`definir_alvo`, `construir_modelo`, `gerar_priorizacao`) são exercitadas, com um
DataFrame sintético no formato do `refined/cobertura_vacinal`. Nada aqui toca
MinIO nem rede — `executar()` (a única função com I/O) fica de fora, igual ao
que já é feito com `clean_and_upload` nos outros módulos.
"""

import numpy as np
import pandas as pd
import pytest

from src.inference.predict import (
    construir_modelo,
    definir_alvo,
    gerar_priorizacao,
    preparar_features,
)


def _municipios(n=60, com_agua=True, com_densidade=True, com_fronteira=True):
    """Gera um refined sintético com as colunas que o pipeline real produz."""
    rng = np.random.default_rng(42)
    ufs = ["RO", "SP", "RS", "BA", "GO"]
    dados = {
        "codigo_municipio": [f"{1100000 + i}" for i in range(n)],
        "municipio": [f"Municipio {i} - {ufs[i % len(ufs)]}" for i in range(n)],
        "ano": ["2025"] * n,
        "populacao": rng.integers(1_000, 500_000, n),
        "doses_aplicadas": rng.integers(500, 400_000, n),
        "cobertura_doses_por_100_habitantes": rng.uniform(20, 160, n),
        "pib_per_capita_reais": rng.uniform(8_000, 90_000, n),
        "qtd_estabelecimentos_saude_sus": rng.integers(1, 90, n),
    }
    if com_densidade:
        dados["densidade_hab_km2"] = rng.uniform(1, 3_000, n)
    if com_agua:
        dados["pct_atendimento_agua"] = rng.uniform(30, 100, n)
    if com_fronteira:
        dados["fronteira"] = (rng.random(n) < 0.1).astype(int)
    return pd.DataFrame(dados)


def test_features_condicionais_entram_quando_as_colunas_existem():
    dados, features, report = preparar_features(_municipios())
    assert "log_densidade_hab_km2" in features
    assert "pct_atendimento_agua" in features
    assert report.municipios_pontuados == 60
    assert "regiao" in report.features_usadas


def test_features_condicionais_ficam_de_fora_quando_as_colunas_faltam():
    # Mesmo comportamento condicional do notebook 03: sem a coluna no refined,
    # o pipeline segue sem a feature em vez de quebrar.
    dados, features, _ = preparar_features(
        _municipios(com_agua=False, com_densidade=False)
    )
    assert "log_densidade_hab_km2" not in features
    assert "pct_atendimento_agua" not in features
    assert "log_populacao" in features


def test_sem_lista_oficial_cai_no_fallback_por_uf():
    dados, _, report = preparar_features(_municipios(com_fronteira=False))
    # RO e RS estão entre as 11 UFs da faixa; SP, BA e GO não.
    assert dados.loc[dados["uf"] == "RO", "fronteira"].eq(1).all()
    assert dados.loc[dados["uf"] == "SP", "fronteira"].eq(0).all()
    assert any("aproximação por UF" in nota for nota in report.notas)


def test_municipio_sem_coluna_obrigatoria_e_descartado_nao_imputado():
    df = _municipios(n=10)
    df.loc[0, "pib_per_capita_reais"] = np.nan
    dados, _, report = preparar_features(df)
    assert report.descartados_colunas_obrigatorias == 1
    assert len(dados) == 9
    assert dados["pib_per_capita_reais"].notna().all()


def test_municipio_sem_agua_e_descartado_nao_imputado():
    df = _municipios(n=10)
    df.loc[[0, 1], "pct_atendimento_agua"] = np.nan
    dados, _, report = preparar_features(df)
    assert report.descartados_sem_agua == 2
    assert len(dados) == 8


def test_uf_desconhecida_levanta_erro_em_vez_de_gerar_regiao_nula():
    df = _municipios(n=5)
    df.loc[0, "municipio"] = "Municipio X - ZZ"
    with pytest.raises(ValueError, match="UF sem região mapeada"):
        preparar_features(df)


def test_alvo_usa_primeiro_quartil_do_proprio_conjunto():
    dados, _, _ = preparar_features(_municipios())
    alvo, corte = definir_alvo(dados)
    assert corte == pytest.approx(
        dados["cobertura_doses_por_100_habitantes"].quantile(0.25)
    )
    # Por construção do quartil, ~25% dos municípios ficam marcados.
    assert 0.2 <= alvo.mean() <= 0.3
    abaixo = dados["cobertura_doses_por_100_habitantes"] < corte
    assert alvo.eq(abaixo.astype(int)).all()


def test_priorizacao_sai_ordenada_e_com_ranking_sem_buraco():
    dados, features, _ = preparar_features(_municipios())
    alvo, _ = definir_alvo(dados)
    modelo = construir_modelo(features)
    modelo.fit(dados[features + ["regiao"]], alvo)

    saida = gerar_priorizacao(modelo, dados, features)

    assert len(saida) == len(dados)
    assert saida["probabilidade_baixa_cobertura"].is_monotonic_decreasing
    assert saida["ranking_prioridade"].tolist() == list(range(1, len(saida) + 1))
    assert saida["probabilidade_baixa_cobertura"].between(0, 1).all()
    assert saida["faixa_prioridade"].iloc[0] == "muito alta"
    assert set(saida.columns) >= {
        "codigo_municipio",
        "municipio",
        "uf",
        "probabilidade_baixa_cobertura",
        "ranking_prioridade",
        "faixa_prioridade",
    }


def test_priorizacao_preserva_o_municipio_certo_em_cada_linha():
    # Guarda contra o bug clássico de reordenar a saída e desalinhar as colunas
    # (usar .values de um DataFrame já ordenado de forma diferente).
    dados, features, _ = preparar_features(_municipios())
    alvo, _ = definir_alvo(dados)
    modelo = construir_modelo(features)
    modelo.fit(dados[features + ["regiao"]], alvo)

    saida = gerar_priorizacao(modelo, dados, features)
    esperado = dados.set_index("codigo_municipio")["cobertura_doses_por_100_habitantes"]
    for _, linha in saida.head(10).iterrows():
        assert linha["cobertura_doses_por_100_habitantes"] == pytest.approx(
            esperado[linha["codigo_municipio"]]
        )
