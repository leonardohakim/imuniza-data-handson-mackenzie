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

**A primeira linha de dados deste CSV não é um município**: é a linha de
rótulos que a API SIDRA retorna por padrão (`/h/y`) antes dos dados reais.
Ver `src/cleaning/clean_ibge.py` para o tratamento.

### `raw/ibge/pib/ano={ano}/pib_municipios.csv`

Resposta bruta da API SIDRA (`/values/t/5938/n6/all/v/37/p/{ano}`), tabela
5938 (PIB total a preços correntes, variável 37, em Mil Reais), nível
município. Ver `docs/decisoes_limpeza.md` (seção 3) para por que essa
tabela foi escolhida em vez da 6784.

| Coluna | Descrição |
|---|---|
| `NC` / `NN` | Código / nome do nível territorial (6 = Município) |
| `MC` / `MN` | Código / nome da unidade de medida (Mil Reais) |
| `V` | Valor do PIB total a preços correntes |
| `D1C` / `D1N` | Código IBGE (7 dígitos) / nome do município |
| `D2C` / `D2N` | Código / nome da variável (sempre 37, "PIB a preços correntes") |
| `D3C` / `D3N` | Código / nome do ano de referência |

**Diferença de schema em relação à tabela de população**: aqui `D2` é a
variável, não o ano (a Tabela 5938 tem várias variáveis disponíveis, mesmo
pedindo só a 37 na ingestão); o ano fica em `D3`. A primeira linha de dados
também pode vir com o mesmo problema da linha de metadados do SIDRA (ver
seção de população acima); tratamento em `src/cleaning/clean_pib.py`.

### `raw/pni/ano={ano}/<nome_do_arquivo>.zip`

CSV mensal de doses aplicadas do PNI (formato original do OpenDataSUS: `;`
como separador, encoding `latin1`), um arquivo por mês, dentro de um ZIP.

Nomes de coluna confirmados contra o schema real do PNI (rodando
`clean_pni.py`/`inspect_pni.py` contra os dados baixados no Codespace,
ago/2026). Os nomes hipotéticos usados antes de termos acesso aos dados
reais continuam como fallback em `COLUMN_CANDIDATES`
(`src/cleaning/clean_pni.py`), caso o schema mude entre anos/datasets:

| Campo lógico | Coluna real (confirmada) | Fallbacks hipotéticos |
|---|---|---|
| Código do município (paciente, residência) | `co_municipio_paciente` | `co_municipio_estabelecimento`, `paciente_endereco_coibgemunicipio`, `estabelecimento_municipio_codigo`, `co_municipio` |
| Data de aplicação da dose | `dt_vacina` | `vacina_dataaplicacao`, `data_aplicacao`, `dt_aplicacao` |
| Nome/tipo da vacina (sigla do imunobiológico) | `sg_imunobiologico` | `vacina_nome`, `vacina_descricao`, `no_vacina` |
| Dose (1ª, 2ª, reforço...) | `co_dose_vacina` | `ds_tipo_dose`, `vacina_descricao_dose`, `dose`, `no_dose` |
| Idade do paciente | `nu_idade_paciente` | `paciente_idade`, `idade` |

Usamos o município de **residência** do paciente (`co_municipio_paciente`),
não o do estabelecimento onde a dose foi aplicada: a métrica de cobertura
usa como denominador a população residente (IBGE), então o numerador
(doses) precisa seguir o mesmo critério, senão municípios-polo (com
grandes hospitais/postos) ficariam com cobertura artificialmente inflada
às custas dos municípios vizinhos.

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

### `trusted/ibge/pib/ano={ano}/pib_municipios.parquet`

| Coluna | Tipo | Descrição |
|---|---|---|
| `codigo_municipio` | string (7 dígitos) | Código IBGE do município |
| `municipio` | string | Nome do município (UF) |
| `ano` | string | Ano de referência do PIB (série IBGE: 2002-2023) |
| `pib_mil_reais` | float64 | PIB total a preços correntes, em Mil Reais |

Também é gravado `_cleaning_report.txt` na mesma pasta, no mesmo formato do
relatório de limpeza da população.

### `trusted/pni/ano={ano}/<nome_do_arquivo>.parquet` e `doses_aplicadas_consolidado.parquet`

Dado já **agregado** (uma linha do CSV bruto = uma dose aplicada; aqui já
viram contagem por grupo, para reduzir volume e proteger dado de paciente
individual):

| Coluna | Tipo | Descrição |
|---|---|---|
| `codigo_municipio` | string (**6 dígitos**, DATASUS/SUS) | Código do município no padrão DATASUS, sem o dígito verificador do IBGE. Diferente da camada `refined`, que usa o código IBGE de 7 dígitos: ver `docs/decisoes_limpeza.md` (seção 2) para por que os dois sistemas de código coexistem e como são cruzados em `build_coverage.py` |
| `ano_mes` | string (`YYYY-MM`) | Mês de aplicação |
| `vacina_nome` | string | Nome/tipo da vacina (quando a coluna existe no raw) |
| `doses_aplicadas` | int64 | Contagem de doses naquele município/mês/vacina |
| `outlier_iqr` | bool | `True` se o total do município naquele mês está fora de `[Q1 - 3·IQR, Q3 + 3·IQR]` da distribuição de todos os municípios no mês: **sinalizado, não removido** (ver decisões de limpeza) |

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
| `cobertura_doses_por_100_habitantes` | float | `doses_aplicadas / populacao * 100`; ver limitação de interpretação em `src/cleaning/build_coverage.py` (é um proxy de intensidade de vacinação, não de % de pessoas efetivamente imunizadas, por causa de esquemas multidose) |
| `pib_mil_reais` | float (opcional) | PIB total do município em Mil Reais, ano de referência 2023 (`--ano-pib`, ver `docs/decisoes_limpeza.md` seção 3); `NaN` quando o município não tem PIB no trusted, e a coluna toda fica ausente se `clean_pib.py` ainda não rodou |
| `pib_per_capita_reais` | float (opcional) | `pib_mil_reais * 1000 / populacao`, calculado em `build_coverage.py`; mesma condição de ausência da coluna acima |
