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
| `D2C` / `D2N` | Código / nome da **variável** (sempre `9324`, "População residente estimada"): é a variável fixada na própria URL da requisição (`v/9324`) |
| `D3C` / `D3N` | Código / nome do **ano de referência** (ex.: `2024`/`2024`) |

**A primeira linha de dados deste CSV não é um município**: é a linha de
rótulos que a API SIDRA retorna por padrão (`/h/y`) antes dos dados reais.
Ver `src/cleaning/clean_ibge.py` para o tratamento.

**Mesma estrutura de três dimensões da Tabela 5938/PIB** (D1 Município, D2
Variável, D3 Ano). Na camada `trusted`, a coluna `ano` é preenchida a
partir do parâmetro `--ano` da própria ingestão/limpeza (mesmo critério já
usado para particionar os dados no MinIO, `ano={ano}/...`), não lida de
D3C — embora os dois sempre coincidam na prática. Ver decisão em
`docs/decisoes_limpeza.md` (bug real encontrado e corrigido: uma versão
anterior lia `ano` de **D2C**, a variável, que sempre valia `9324`, em vez
de D3C, o ano).

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

### `raw/pni/ano={ano}/<nome_do_arquivo>.zip` (opcional)

CSV mensal de doses aplicadas do PNI (formato original do OpenDataSUS: `;`
como separador, encoding `latin1`), um arquivo por mês, dentro de um ZIP.
**Diferente das outras camadas `raw` acima, esta não é populada pelo fluxo
padrão**: `clean_pni.py` (sem `--from-raw`) baixa cada mês direto da fonte
para um temporário local e nunca grava aqui — ver `docs/decisoes_limpeza.md`
(seção 2). Só existe se alguém rodar `download_pni.py` deliberadamente
(ex.: para arquivar os ZIPs brutos).

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

### `raw/ibge/area/area_municipios.csv`

Resposta bruta da API SIDRA (`/values/t/4714/n6/all/v/6318/p/last`), tabela
4714 (população residente, área territorial e densidade demográfica),
variável 6318 (área territorial, km²), nível município. **Sem partição por
ano** (diferente das outras fontes IBGE): área territorial é um atributo
estático do município, não reprocessado por `--ano` — ver
`docs/decisoes_limpeza.md`.

| Coluna | Descrição |
|---|---|
| `V` | Valor da área territorial (km²) |
| `D1C` / `D1N` | Código IBGE (7 dígitos) / nome do município |
| `D3C` / `D3N` | Ano de referência da medição (Censo mais recente disponível na tabela — 2022 no momento em que foi confirmado contra a API real) |

Mesma linha de metadados do SIDRA no início do array (ver seção de
população acima); tratamento em `src/cleaning/clean_area.py`.

### `raw/cnes/cnes_estabelecimentos.zip`

Arquivo ZIP como veio direto do portal CKAN (`dadosabertos.saude.gov.br`),
recurso "CNES Estabelecimentos" em formato CSV — snapshot nacional atual
do Cadastro Nacional de Estabelecimentos de Saúde. **Sem partição por
ano** (mesmo critério da área territorial): é o cadastro "atual", não uma
série histórica reprocessada por `--ano` — ver `docs/decisoes_limpeza.md`.
Contém 1 CSV interno (`cnes_estabelecimentos.csv`, separador `;`,
encoding `latin1`, 36 colunas, confirmado contra a fonte real via
`investigar_cnes_schema.py`); só as colunas abaixo são usadas pela
limpeza:

| Coluna | Descrição |
|---|---|
| `CO_CNES` | Código do estabelecimento (chave para contagem) |
| `CO_IBGE` | Código do município — **apesar do nome, vem no padrão DATASUS de 6 dígitos**, não os 7 dígitos do IBGE (confirmado: 635.786 de 635.786 registros reais com exatamente 6 caracteres) |
| `CO_AMBULATORIAL_SUS` | `"SIM"`/`"NAO"` — se o estabelecimento tem atendimento ambulatorial pelo SUS |

Tratamento em `src/cleaning/clean_cnes.py`.

### `raw/ibge/fronteira/municipios_faixa_fronteira.xls`

Planilha do IBGE "Municípios da Faixa de Fronteira e Cidades-Gêmeas",
edição 2024, baixada do GeoFTP (organização do território). **Sem partição
por ano** (mesmo critério de área e CNES: é um snapshot, não série
histórica). Gravada exatamente como veio, sem parsing — a limpeza acontece
em `clean_fronteira.py`. Aba usada: `Faixa de Fronteira - Município 2024`.

| Coluna | Descrição |
|---|---|
| `CD_MUN` | Código IBGE do município (7 dígitos) |
| `NM_MUN` | Nome do município |
| `SIGLA_UF` | UF |
| `FAIXA_SEDE` | `"sim"`/`"não"` — se a **sede** do município está dentro da faixa de 150km da linha divisória (Lei 6.634/1979) |

**Uma linha por município que intersecta a faixa por área** (~590 no
total), não uma linha por "município de fronteira": a distinção importa e
está detalhada em `docs/decisoes_limpeza.md`, seção 12. Das 588 linhas que
sobram após a limpeza, **511 têm `FAIXA_SEDE = "sim"`** — esse é o critério
adotado para `fronteira = 1`.

### `raw/basedosdados/snis/municipio_agua_esgoto.csv.gz`

Tabela `br_mdr_snis.municipio_agua_esgoto` baixada da **Base dos Dados**
(intermediário que republica o SNIS do Ministério das Cidades em formato
tabular), em CSV comprimido. Traz a série histórica completa; o filtro do
ano de referência (2022) acontece na limpeza, não na ingestão. Colunas
usadas (nomes originais da Base dos Dados):

| Coluna | Descrição |
|---|---|
| `id_municipio` | Código IBGE do município (7 dígitos) |
| `ano` | Ano de referência do indicador |
| `indice_atendimento_total_agua` | % da população atendida por rede de água |
| `indice_coleta_esgoto` | % com coleta de esgoto |
| `indice_tratamento_esgoto` | % com tratamento de esgoto |

Tratamento em `src/cleaning/clean_snis.py`.

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

### `trusted/ibge/area/area_municipios.parquet`

| Coluna | Tipo | Descrição |
|---|---|---|
| `codigo_municipio` | string (7 dígitos) | Código IBGE do município |
| `municipio` | string | Nome do município (UF) |
| `area_km2` | float64 | Área territorial em km² |
| `ano_referencia_area` | string | Ano da medição de área (não é o mesmo `ano` do resto do dataset refinado — ver nota na camada `raw` acima) |

Também é gravado `_cleaning_report.txt` na mesma pasta, mesmo formato dos
outros relatórios de limpeza.

### `trusted/cnes/cnes_estabelecimentos_por_municipio.parquet`

Já agregado por município (o raw é 1 linha por estabelecimento; aqui é
1 linha por município):

| Coluna | Tipo | Descrição |
|---|---|---|
| `codigo_municipio` | string (**6 dígitos**, DATASUS/SUS) | Mesmo padrão do PNI, não os 7 dígitos do IBGE — ver nota na camada `raw` acima |
| `qtd_estabelecimentos_saude` | int64 | Total de estabelecimentos de saúde cadastrados no município |
| `qtd_estabelecimentos_saude_sus` | int64 | Subconjunto com atendimento ambulatorial SUS (`CO_AMBULATORIAL_SUS = "SIM"`) — proxy mais próximo de capacidade de vacinação do que o total bruto |

Também é gravado `_cleaning_report.txt` na mesma pasta, mesmo formato dos
outros relatórios de limpeza.

### `trusted/ibge/fronteira/municipios_faixa_fronteira.parquet`

| Coluna | Tipo | Descrição |
|---|---|---|
| `codigo_municipio` | string (7 dígitos) | Código IBGE do município |
| `municipio` | string | Nome do município |
| `uf` | string | Sigla da UF |
| `fronteira` | int (0/1) | `1` se `FAIXA_SEDE == "sim"` (sede dentro da faixa); `0` se o município apenas intersecta a faixa por área |

**588 linhas** (590 do raw menos 2 com `FAIXA_SEDE` indefinida), das quais
**511 com `fronteira = 1`**. Municípios ausentes desta tabela não são dado
faltante: por construção da fonte (lista positiva completa), não tocam a
faixa — viram `fronteira = 0` no cruzamento. Também é gravado
`_cleaning_report.txt`, que separa explicitamente as duas contagens
(`linhas_finais` vs. `municipios_com_sede_na_faixa`).

### `trusted/saneamento/snis/saneamento_municipios.parquet`

Já filtrado para o ano de referência 2022 (o mais completo do painel):

| Coluna | Tipo | Descrição |
|---|---|---|
| `codigo_municipio` | string (7 dígitos) | Código IBGE do município |
| `ano` | string | Sempre `2022` nesta camada |
| `pct_atendimento_agua` | float | % da população atendida por rede de água — **única usada como feature** |
| `pct_coleta_esgoto` | float | % com coleta de esgoto — completude de só ~53%, fica disponível mas fora do modelo |
| `pct_tratamento_esgoto` | float | % com tratamento de esgoto — mesma ressalva do anterior |

Ver `docs/decisoes_limpeza.md`, seção 13, para por que esgoto não entra no
conjunto de features. Também é gravado `_cleaning_report.txt`.

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
| `area_km2` | float (opcional) | Área territorial do município (IBGE/SIDRA, ver `docs/decisoes_limpeza.md`); `NaN`/coluna ausente se `clean_area.py` ainda não rodou |
| `densidade_hab_km2` | float (opcional) | `populacao / area_km2`, calculado em `build_coverage.py` a partir da população do próprio dataset (não da densidade que a Tabela 4714 já traz, que usa população de outro ano — ver `src/cleaning/build_coverage.py`); mesma condição de ausência da coluna acima |
| `qtd_estabelecimentos_saude` | float (opcional) | Total de estabelecimentos de saúde cadastrados no CNES (ver `docs/decisoes_limpeza.md`); cruzado pelo código de 6 dígitos DATASUS (mesma chave das doses), não pelo `codigo_municipio` de 7 dígitos; `NaN`/coluna ausente se `clean_cnes.py` ainda não rodou |
| `qtd_estabelecimentos_saude_sus` | float (opcional) | Subconjunto de `qtd_estabelecimentos_saude` com atendimento ambulatorial SUS; mesma condição de ausência da coluna acima |
| `fronteira` | int 0/1 (opcional) | `1` se a sede do município está na faixa de fronteira (lista oficial IBGE 2024, ver trusted acima). **Única coluna em que ausência vira `0` e não `NaN`**, porque a fonte é uma lista positiva completa; coluna ausente se `clean_fronteira.py` ainda não rodou |
| `pct_atendimento_agua` | float (opcional) | % da população atendida por rede de água (SNIS 2022); `NaN` quando o município não tem o indicador — e nesse caso ele é **descartado** da modelagem, não imputado |
| `pct_coleta_esgoto` | float (opcional) | % com coleta de esgoto (SNIS 2022); disponível para análise, fora do conjunto de features |
| `pct_tratamento_esgoto` | float (opcional) | % com tratamento de esgoto (SNIS 2022); mesma condição da anterior |

### `refined/priorizacao/ano={ano}/priorizacao_municipios.parquet` (e `.csv`)

Saída do pipeline de inferência em lote (`src/inference/predict.py`): uma
linha por município pontuado, ordenada da maior para a menor probabilidade
de baixa cobertura.

| Coluna | Tipo | Descrição |
|---|---|---|
| `codigo_municipio` | string (7 dígitos) | Código IBGE do município |
| `municipio` / `uf` / `regiao` | string | Identificação e recorte geográfico |
| `populacao` | int64 | População residente estimada |
| `cobertura_doses_por_100_habitantes` | float | Cobertura observada no ano pontuado |
| `probabilidade_baixa_cobertura` | float (0-1) | Saída do Random Forest — **é o campo principal**, usado para ordenar |
| `ranking_prioridade` | int | Posição no ranking (1 = maior probabilidade) |
| `faixa_prioridade` | string | Leitura auxiliar por decil: `muito alta` (10% do topo), `alta`, `média`, `baixa` — não é um veredito, ver docstring de `predict.py` |

Ao lado é gravado `_inference_report.txt`, com o ano de treino, o ano
pontuado, os descartes, o corte do alvo e as features usadas.

## Camada de modelagem (Etapa 3, derivada em notebook — não persistida no MinIO)

Colunas calculadas em `notebooks/03_construcao_modelos.ipynb` a partir do
`refined/cobertura_vacinal`, só em memória (não gravadas em nenhum bucket).
Justificativa de cada uma em `docs/decisoes_modelagem.md`.

| Coluna | Tipo | Descrição |
|---|---|---|
| `uf` | string | Sigla da UF, extraída de `municipio` (`"Nome - UF"`) |
| `fronteira` | int (0/1) | Vem pronta do `refined` (lista oficial do IBGE, sede na faixa). Só quando essa coluna não existe o notebook cai no **fallback** de aproximação por UF (as 11 UFs da faixa: AC, AP, AM, MT, MS, PA, PR, RS, RO, RR, SC) — ver `docs/decisoes_modelagem.md`, seção 1 |
| `regiao` | string | Macrorregião (Norte/Nordeste/Centro-Oeste/Sudeste/Sul), derivada da UF |
| `log_populacao` | float | `log1p(populacao)` |
| `log_pib_per_capita` | float | `log1p(pib_per_capita_reais)` |
| `estabelecimentos_saude_sus_por_100k_hab` | float | `qtd_estabelecimentos_saude_sus / populacao * 100.000` — normaliza o CNES pelo porte do município, que de outro modo seria quase redundante com `log_populacao` |
| `log_estabelecimentos_saude_sus_por_100k_hab` | float | `log1p` da coluna acima — é essa que entra como feature |
| `log_densidade_hab_km2` | float (condicional) | `log1p(densidade_hab_km2)`; só existe se área/densidade estiver no `refined` |
| `pct_atendimento_agua` | float (condicional) | Entra como feature **sem transformação** (já é percentual); só existe se o SNIS estiver no `refined`, e municípios sem o indicador são descartados |
| `baixa_cobertura` | int (0/1) | Alvo de classificação: `1` se `cobertura_doses_por_100_habitantes` está abaixo do 1º quartil do conjunto de modelagem (73,25 doses/100 hab. na execução atual) |
| `cluster` | int | Rótulo do K-Means (segmentação por perfil), não usado como feature de classificação |

As mesmas colunas são reconstruídas, com a mesma lógica condicional, por
`preparar_features()` em `src/inference/predict.py` — para que a inferência
em lote use exatamente o conjunto de features que foi medido no notebook.
