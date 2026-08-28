# Dicionário de Dados

Este documento descreve as colunas dos datasets em cada camada do pipeline
(`raw` → `trusted` → `refined`, todos em buckets do MinIO). Ele é vivo: ao
rodar `inspect_pni.py` contra os dados reais no Codespace, confirme se os
nomes de coluna do PNI batem com o que está listado abaixo e ajuste este
arquivo (e `COLUMN_CANDIDATES` em `src/cleaning/clean_pni.py`) se algo mudou.

## Camada `raw` (dado bruto, como veio da fonte)

### `raw/ibge/populacao/ano={ano}/populacao_municipios.csv`

Resposta bruta da API SIDRA (`/values/t/6579/n6/all/v/9324/p/{ano}`), tabela
6579 (população residente estimada), nível município.

| Coluna | Descrição |
|---|---|
| `NC` / `NN` | Código / nome do nível territorial (6 = Município) |
| `MC` / `MN` | Código / nome da unidade de medida (Pessoas) |
| `V` | Valor da população estimada |
| `D1C` / `D1N` | Código IBGE (7 dígitos) / nome do município |
| `D2C` / `D2N` | Código / nome do ano de referência |

⚠️ **A primeira linha de dados deste CSV não é um município** — é a linha de
rótulos que a API SIDRA retorna por padrão (`/h/y`) antes dos dados reais.
Ver `src/cleaning/clean_ibge.py` para o tratamento.

### `raw/pni/ano={ano}/<nome_do_arquivo>.zip`

CSV mensal de doses aplicadas do PNI (formato original do OpenDataSUS: `;`
como separador, encoding `latin1`), um arquivo por mês, dentro de um ZIP.

As colunas exatas variam por ano/dataset — **confirme com
`python -m src.ingestion.inspect_pni --ano <ano> --mes <mes>`** antes de
assumir qualquer nome. Colunas esperadas (nomenclatura provável, no padrão
DATASUS/RNDS usado em outros datasets de vacinação):

| Campo lógico | Candidatos de nome de coluna |
|---|---|
| Código do município (paciente) | `paciente_endereco_coibgemunicipio`, `estabelecimento_municipio_codigo`, `co_municipio` |
| Data de aplicação da dose | `vacina_dataaplicacao`, `data_aplicacao`, `dt_aplicacao` |
| Nome/tipo da vacina | `vacina_nome`, `vacina_descricao` |
| Dose (1ª, 2ª, reforço...) | `vacina_descricao_dose`, `dose` |
| Idade do paciente | `paciente_idade` |

## Camada `trusted` (dado limpo e padronizado)

### `trusted/ibge/populacao/ano={ano}/populacao_municipios.parquet`

| Coluna | Tipo | Descrição |
|---|---|---|
| `codigo_municipio` | string (7 dígitos) | Código IBGE do município |
| `municipio` | string | Nome do município (UF) |
| `ano` | string | Ano de referência da estimativa |
| `populacao` | int64 | População estimada |
| `unidade_medida` | string | Sempre "Pessoas" |
| `nivel_territorial` | string | Sempre "Município" |

Também é gravado `_cleaning_report.txt` na mesma pasta, com a contagem de
linhas removidas e por quê (ver `docs/decisoes_limpeza.md`).

### `trusted/pni/ano={ano}/<nome_do_arquivo>.parquet` e `doses_aplicadas_consolidado.parquet`

Dado já **agregado** (uma linha do CSV bruto = uma dose aplicada; aqui já
viram contagem por grupo, para reduzir volume e proteger dado de paciente
individual):

| Coluna | Tipo | Descrição |
|---|---|---|
| `codigo_municipio` | string (7 dígitos) | Código IBGE do município |
| `ano_mes` | string (`YYYY-MM`) | Mês de aplicação |
| `vacina_nome` | string | Nome/tipo da vacina (quando a coluna existe no raw) |
| `doses_aplicadas` | int64 | Contagem de doses naquele município/mês/vacina |
| `outlier_iqr` | bool | `True` se o total do município naquele mês está fora de `[Q1 - 3·IQR, Q3 + 3·IQR]` da distribuição de todos os municípios no mês — **sinalizado, não removido** (ver decisões de limpeza) |

## Camada `refined` (pronto para análise/ML)

### `refined/cobertura_vacinal/ano={ano}/cobertura_municipios.parquet`

Uma linha por município, IBGE + PNI já cruzados:

| Coluna | Tipo | Descrição |
|---|---|---|
| `codigo_municipio` | string (7 dígitos) | Código IBGE do município |
| `municipio` | string | Nome do município |
| `ano` | string | Ano de referência |
| `populacao` | int64 | População estimada (IBGE) |
| `doses_aplicadas` | int64 | Total de doses aplicadas no ano (PNI); `0` quando não há registro |
| `cobertura_doses_por_100_habitantes` | float | `doses_aplicadas / populacao * 100` — ver limitação de interpretação em `src/cleaning/build_coverage.py` (é um proxy de intensidade de vacinação, não de % de pessoas efetivamente imunizadas, por causa de esquemas multidose) |
