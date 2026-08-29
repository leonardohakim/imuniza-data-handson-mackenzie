"""Testes de `src/cleaning/clean_pni.py`.

Cobre, com dados sintéticos (sem MinIO nem rede), as três coisas que
quebraram de verdade ao rodar contra os dados reais do PNI:
1. resolução de nomes de coluna (schema não confirmável às cegas);
2. parsing de data sem a inversão silenciosa de dia/mês do `dayfirst`;
3. normalização do código de município como 6 dígitos (DATASUS), não 7
   (IBGE) — o bug que zerava toda a cobertura vacinal (ver
   `docs/decisoes_limpeza.md`, seção 2).
"""

import io
import zipfile

import pandas as pd
import pytest

from src.cleaning.clean_pni import (
    CleaningReport,
    _clean_and_aggregate_chunk,
    _iter_csv_chunks_from_zip,
    clean_month_stream,
    parse_application_dates,
    resolve_column,
)


# --- resolve_column -----------------------------------------------------

def test_resolve_column_prefere_match_exato():
    df = pd.DataFrame(columns=["dt_vacina", "co_municipio_paciente"])
    assert resolve_column(df, "data_aplicacao") == "dt_vacina"


def test_resolve_column_cai_para_substring_quando_nao_ha_match_exato():
    # nenhum candidato de "codigo_municipio" bate exatamente com
    # "co_municipio_paciente", mas "co_municipio" é substring dele.
    df = pd.DataFrame(columns=["co_municipio_paciente", "dt_vacina"])
    assert resolve_column(df, "codigo_municipio") == "co_municipio_paciente"


def test_resolve_column_falha_de_forma_explicita_com_colunas_disponiveis_na_mensagem():
    df = pd.DataFrame(columns=["coluna_completamente_diferente"])
    with pytest.raises(KeyError) as exc_info:
        resolve_column(df, "data_aplicacao")
    # a mensagem de erro precisa listar as colunas reais, pra debugar rápido
    assert "coluna_completamente_diferente" in str(exc_info.value)


# --- parse_application_dates --------------------------------------------

def test_parse_dates_iso_nao_inverte_dia_e_mes():
    # Bug real encontrado no desenvolvimento: dayfirst=True do pandas lia
    # "2025-01-05" (ISO, ano-mes-dia) como 1º de maio em vez de 5 de janeiro.
    datas = pd.Series(["2025-01-05", "2025-01-06", "2025-01-07", "2025-01-08"])
    parsed = parse_application_dates(datas)
    assert parsed.iloc[0] == pd.Timestamp("2025-01-05")
    assert parsed.iloc[0].month == 1
    assert parsed.iloc[0].day == 5


def test_parse_dates_formato_brasileiro_tambem_funciona():
    datas = pd.Series(["05/01/2025", "06/01/2025", "07/01/2025", "31/12/2025"])
    parsed = parse_application_dates(datas)
    assert parsed.iloc[0] == pd.Timestamp("2025-01-05")
    assert parsed.iloc[3] == pd.Timestamp("2025-12-31")


def test_parse_dates_invalidas_viram_nat_em_vez_de_quebrar():
    datas = pd.Series(["2025-01-05", "isso não é uma data", "2025-01-07"])
    parsed = parse_application_dates(datas)
    assert parsed.isna().sum() == 1


# --- codigo_municipio: 6 dígitos (DATASUS), não 7 (IBGE) -----------------

def _chunk_pni(codigo_municipio, data="2025-01-05", vacina="COVID19", dose="1"):
    return pd.DataFrame({
        "co_municipio_paciente": codigo_municipio,
        "dt_vacina": [data] * len(codigo_municipio),
        "sg_imunobiologico": [vacina] * len(codigo_municipio),
        "co_dose_vacina": [dose] * len(codigo_municipio),
    })


def _resolved():
    return {
        "codigo_municipio": "co_municipio_paciente",
        "data_aplicacao": "dt_vacina",
        "vacina_nome": "sg_imunobiologico",
        "dose": "co_dose_vacina",
        "paciente_idade": None,
    }


def test_codigo_municipio_datasus_de_6_digitos_e_mantido_como_6_digitos():
    # Regressão do bug: a versão anterior fazia zfill(7), transformando
    # "110001" (6 dígitos, real) em "0110001" — que nunca bate com nenhum
    # código IBGE de verdade.
    chunk = _chunk_pni(["110001"])
    report = CleaningReport(arquivo="teste")

    limpo = _clean_and_aggregate_chunk(chunk, _resolved(), report)

    assert report.municipio_invalido == 0
    assert limpo["codigo_municipio"].iloc[0] == "110001"
    assert len(limpo["codigo_municipio"].iloc[0]) == 6


def test_codigo_municipio_curto_e_completado_com_zero_a_esquerda_ate_6_digitos():
    # Alguns códigos de município legitimamente têm menos de 6 dígitos
    # quando lidos como número puro (perdem zero à esquerda no CSV).
    chunk = _chunk_pni(["1100"])
    report = CleaningReport(arquivo="teste")

    limpo = _clean_and_aggregate_chunk(chunk, _resolved(), report)

    assert limpo["codigo_municipio"].iloc[0] == "001100"


def test_codigo_municipio_com_mais_de_6_digitos_e_descartado():
    chunk = _chunk_pni(["12345678"])
    report = CleaningReport(arquivo="teste")

    limpo = _clean_and_aggregate_chunk(chunk, _resolved(), report)

    assert report.municipio_invalido == 1
    assert len(limpo) == 0


# --- clean_month_stream: agregação e outliers -----------------------------

def test_clean_month_stream_agrega_por_municipio_mes_vacina():
    # dose diferente em cada linha do chunk1 só para não serem tratadas como
    # duplicata exata entre si (dose não entra na chave de agregação).
    chunk1 = pd.DataFrame({
        "co_municipio_paciente": ["110001", "110001"],
        "dt_vacina": ["2025-01-05", "2025-01-05"],
        "sg_imunobiologico": ["COVID19", "COVID19"],
        "co_dose_vacina": ["1", "2"],
    })
    chunk2 = _chunk_pni(["110001"], data="2025-01-20")

    aggregated, report = clean_month_stream(iter([chunk1, chunk2]), source_name="teste.zip")

    assert report.linhas_lidas == 3
    linha = aggregated[aggregated["codigo_municipio"] == "110001"]
    assert linha["doses_aplicadas"].iloc[0] == 3  # as 3 doses do mês, agregadas
    assert linha["ano_mes"].iloc[0] == "2025-01"


def test_clean_month_stream_detecta_duplicata_exata_dentro_do_mesmo_chunk():
    linha = {
        "co_municipio_paciente": "110001",
        "dt_vacina": "2025-01-05",
        "sg_imunobiologico": "COVID19",
        "co_dose_vacina": "1",
    }
    chunk = pd.DataFrame([linha, linha])  # linha inteira duplicada

    aggregated, report = clean_month_stream(iter([chunk]), source_name="teste.zip")

    assert report.duplicatas_removidas == 1
    assert aggregated["doses_aplicadas"].sum() == 1


def test_clean_month_stream_levanta_erro_para_stream_vazio():
    with pytest.raises(RuntimeError):
        clean_month_stream(iter([]), source_name="vazio.zip")


# --- leitura de ZIP em streaming -------------------------------------------

def test_iter_csv_chunks_from_zip_le_csv_dentro_de_zip_em_memoria():
    csv_content = (
        "co_municipio_paciente;dt_vacina;sg_imunobiologico;co_dose_vacina\n"
        "110001;2025-01-05;COVID19;1\n"
        "355030;2025-01-06;BCG;1\n"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("dados.csv", csv_content.encode("latin1"))
    buffer.seek(0)
    zip_bytes = buffer.read()

    def byte_chunks():
        yield zip_bytes  # um chunk só, arquivo pequeno

    chunks = list(_iter_csv_chunks_from_zip(byte_chunks()))
    full_df = pd.concat(chunks, ignore_index=True)

    assert len(full_df) == 2
    assert set(full_df["co_municipio_paciente"]) == {"110001", "355030"}
