# imuniza-data-handson-mackenzie
Projeto desenvolvido para a disciplina de Hands-on Engenharia de Dados aplicada à Saúde Pública.

# ImunizaData

[![Testes](https://github.com/leonardohakim/imuniza-data-handson-mackenzie/actions/workflows/tests.yml/badge.svg)](https://github.com/leonardohakim/imuniza-data-handson-mackenzie/actions/workflows/tests.yml)

Projeto desenvolvido para a disciplina de **Hands-on**, Engenharia de Dados aplicada à Saúde Pública.

## Integrantes

| Nome | RA | GitHub |
|---|---|---|
| Leonardo Domingues Machado da Silva | 10735382 | [@leonardohakim](https://github.com/leonardohakim) |
| Gabriel Cardoso Silva | 10733004 | |
| Gabriela Addesso Ruvolo | 10735412 | |

## Objetivo do Projeto

Utilizar engenharia de dados e análise de dados públicos para identificar municípios e grupos populacionais com baixa cobertura vacinal, permitindo priorizar ações de vacinação no âmbito do SUS (Sistema Único de Saúde).

A proposta busca transformar dados públicos, hoje dispersos e pouco explorados, em informação acionável para gestores de saúde pública, apoiando decisões sobre onde e para quem direcionar campanhas de imunização.

Descrição detalhada do problema (o que já sabemos, o que ainda não
sabemos, e as perguntas que o projeto se propõe a responder, sem entrar na
solução técnica) em
[`docs/entendimento_problema.md`](docs/entendimento_problema.md).

## Fontes de Dados

- **DATASUS / TabNet (SI-PNI)**: Sistema de Informações do Programa Nacional de Imunizações
- **OpenDataSUS**: bases granulares de doses aplicadas por município, período e faixa etária (PNI), e cadastro de estabelecimentos de saúde (CNES)
- **IBGE / SIDRA**: dados demográficos e socioeconômicos por município (população, PIB per capita, área territorial/densidade demográfica); ver `docs/decisoes_limpeza.md` sobre por que renda/IDH foram descartados em favor do PIB
- **IBGE (lista oficial de faixa de fronteira, Lei 6.634/1979)**: edição 2024, com 588 municípios que intersectam a faixa, dos quais **511 têm a sede dentro dela** — é esse o critério usado como feature (`fronteira = 1`), ver `docs/decisoes_limpeza.md`, seção 12
- **SNIS (saneamento básico), via Base dos Dados**: indicadores de atendimento de água e esgoto por município (ano de referência 2022, o mais completo do painel) — ver `docs/decisoes_limpeza.md`, seção 13

Por que cada fonte foi escolhida (e o que foi avaliado e descartado), o
recorte geográfico (nacional) e temporal (ano completo de 2025), a
verificabilidade de cada fonte, e os aspectos legais/éticos (LGPD) e
vieses potenciais considerados, estão detalhados em
[`docs/criterios_selecao_dados.md`](docs/criterios_selecao_dados.md).

## Arquitetura do Pipeline

![Diagrama de arquitetura do pipeline ImunizaData: fontes externas (IBGE/SIDRA, OpenDataSUS), ingestão, camadas raw/trusted/refined no MinIO, limpeza, cruzamento e análise exploratória, com as caixas de infraestrutura (docker-compose/MinIO) e qualidade (pytest/CI)](docs/arquitetura_pipeline.svg)

Todos os componentes do pipeline e as tecnologias envolvidas em cada etapa
(fontes externas, ingestão, camadas de dado, limpeza, cruzamento, análise,
infraestrutura e qualidade/CI) estão detalhados no diagrama acima
(`docs/arquitetura_pipeline.svg`).

## Estrutura do Projeto

Os dados não ficam em pastas locais: vivem em três buckets do MinIO
(subida via `docker-compose.yml`), seguindo a convenção raw → trusted →
refined:

```
imuniza-data-handson-mackenzie/
├── docs/
│   ├── entendimento_problema.md # Etapa 1: problema detalhado e perguntas de pesquisa
│   ├── criterios_selecao_dados.md # Etapa 2: por que cada fonte foi escolhida, escopo geo/temporal
│   ├── analise_exploratoria.md # Etapa 2: gráficos da EDA com narrativa e achados explicados
│   ├── arquitetura_pipeline.svg # Diagrama de arquitetura (componentes e tecnologias)
│   ├── dicionario_dados.md     # Schema de cada camada (raw/trusted/refined)
│   ├── decisoes_limpeza.md     # Decisões de limpeza documentadas e justificadas
│   ├── decisoes_modelagem.md   # Etapa 3: alvo, algoritmos, split, métricas, limitações
│   ├── resultados_modelagem.md # Etapa 3: gráficos da modelagem com narrativa e achados explicados
│   ├── evidencia_execucao.md   # Prova de execução real do pipeline ponta a ponta
│   └── guia_setup_etapa2.md    # Passo a passo de reprodução, com troubleshooting
├── notebooks/                  # Notebooks de exploracao, prototipagem e modelagem
├── src/
│   ├── config.py                # Configuração de acesso ao MinIO
│   ├── validate_setup.py        # Healthcheck do MinIO e das fontes externas
│   ├── ingestion/                # Etapa 1: coleta (fontes -> bucket "raw")
│   │   ├── download_ibge.py
│   │   ├── download_pib.py
│   │   ├── download_area.py    # área territorial (IBGE/SIDRA); não particionado por --ano, ver docs/decisoes_limpeza.md
│   │   ├── download_cnes.py    # estabelecimentos de saúde (CNES); tb não particionado por --ano
│   │   ├── download_fronteira.py # lista oficial de faixa de fronteira (IBGE, 2024); tb não particionado por --ano
│   │   ├── download_snis.py    # saneamento básico (SNIS, via Base dos Dados); painel histórico completo
│   │   ├── download_pni.py     # opcional — ver nota no "Como Executar"
│   │   └── inspect_pni.py
│   └── cleaning/                  # Etapa 2: limpeza (bucket "raw" -> "trusted" -> "refined")
│       ├── clean_ibge.py
│       ├── clean_pib.py
│       ├── clean_area.py
│       ├── clean_cnes.py
│       ├── clean_fronteira.py
│       ├── clean_snis.py       # filtra o ano de referência (2022) e separa água (obrigatória) de esgoto (informativo)
│       ├── clean_pni.py
│       └── build_coverage.py
│   └── inference/                 # Etapa 3: inferência em lote (refined -> priorização)
│       └── predict.py            # aplica o modelo e grava o ranking de municípios prioritários
├── tests/                        # Testes automatizados (pytest)
├── reports/                     # Gráficos e relatórios gerados pelos notebooks
├── docker-compose.yml            # MinIO local (buckets raw / trusted / refined)
└── README.md
```

## Metodologia

### Etapa 1: Ingestão de Dados
Coleta programática de dados de vacinação (SI-PNI/OpenDataSUS) e dados demográficos e de infraestrutura (IBGE/SIDRA, CNES, SNIS), gravados na camada raw exatamente como a fonte entrega, sem transformação. A única exceção é o PNI: por restrição de disco, cada mês é baixado, limpo e descartado sem passar por `raw` (ver `docs/decisoes_limpeza.md`, seção 2) — na camada trusted ele fica agregado por **município × mês × vacina**, granularidade suficiente para a métrica de cobertura e que já elimina o dado individual de paciente. Automação via Python (`pandas`, `requests`, `boto3`).

### Etapa 2: Análise Exploratória e Limpeza
Padronização dos códigos de município (IBGE, 7 dígitos), tratamento de valores ausentes e inconsistências, e construção da métrica central de cobertura vacinal (doses aplicadas / população residente × 100, ou seja, **doses por 100 habitantes** — é um proxy de intensidade de vacinação, não o percentual de pessoas imunizadas, já que uma mesma pessoa recebe várias doses por ano). Identificação de outliers e análise de correlação com variáveis socioeconômicas. Os gráficos gerados pelo notebook e as conclusões da EDA (distribuição da cobertura, ranking por UF, relação com população e PIB per capita, sazonalidade) estão documentados com texto explicativo em [`docs/analise_exploratoria.md`](docs/analise_exploratoria.md), em vez de ficarem soltos na pasta `reports/`.

### Etapa 3: Aplicação de ML e Treinamento de Modelos
- **Classificação** de risco de baixa cobertura (alvo: abaixo do 1º quartil nacional) com três modelos comparados — Regressão Logística, Random Forest e XGBoost — com ajuste de hiperparâmetros (`GridSearchCV`) e tratamento explícito do desbalanceamento de classes (um quarto modelo, KNN, foi testado e removido da comparação final por não aceitar o mesmo tratamento de classes desbalanceadas — ver `docs/decisoes_modelagem.md`, seção 4)
- Features: população, PIB per capita, fronteira (lista oficial IBGE), região, estabelecimentos de saúde (CNES), densidade demográfica (IBGE/SIDRA) e saneamento básico/água (SNIS) — as três últimas entram automaticamente quando disponíveis no dataset refinado, ver `docs/decisoes_modelagem.md`, seção 1
- **Enquadramento complementar de regressão** (alvo contínuo, mesma divisão treino/validação/teste) para rankear municípios por urgência dentro do grupo de risco — ver `docs/decisoes_modelagem.md`, seção 7
- **Clusterização** (K-Means, k escolhido por silhouette score) para segmentar municípios por perfil de cobertura e características socioeconômicas
- Matriz de comparação de modelos, matriz de confusão, curva ROC, importância de features e checagem de overfitting (treino vs. validação) — narrativa completa dos gráficos em [`docs/resultados_modelagem.md`](docs/resultados_modelagem.md)
- **Random Forest e XGBoost tratados como equivalentes na regressão**, não um vencedor único: o modelo com menor RMSE trocou entre as duas últimas reexecuções por uma margem cada vez menor (0,11 → 0,05), evidência de que a diferença está dentro do ruído amostral, não de uma vantagem real de um algoritmo sobre o outro — decisão registrada com a justificativa completa em `docs/decisoes_modelagem.md`, seção 10
- **Pipeline de inferência em lote** (`src/inference/predict.py`): aplica o modelo ao dataset refinado e grava em `refined/priorizacao/` o ranking de municípios por probabilidade de baixa cobertura — a pergunta de negócio respondida em forma de lista acionável, sem intervenção manual
- Escopo **transversal** (um único ano, 2025), não temporal — ver `docs/decisoes_modelagem.md` sobre por que "prever risco futuro" exigiria um segundo ano de dados que ainda não temos

## Tecnologias

| Camada | Tecnologias |
|---|---|
| Linguagem e análise | Python 3, pandas, numpy, scipy |
| Machine learning | scikit-learn (pipelines, `GridSearchCV`, K-Means), XGBoost |
| Visualização | Matplotlib, Seaborn |
| Notebooks | Jupyter |
| Ingestão | requests (APIs SIDRA/CKAN), stream-unzip (ZIPs do PNI em streaming), xlrd (planilha do IBGE) |
| Armazenamento | MinIO (compatível com API S3), acessado via boto3; arquivos em Parquet (pyarrow) |
| Infraestrutura | Docker Compose (sobe o MinIO local com os buckets raw/trusted/refined) |
| Qualidade | pytest (87 testes das funções puras), GitHub Actions (CI a cada push/PR) |

## Como Executar

```bash
git clone https://github.com/leonardohakim/imuniza-data-handson-mackenzie.git
cd imuniza-data-handson-mackenzie
pip install -r requirements.txt
docker-compose up -d          # sobe o MinIO local (portas 9000/9001)
python -m src.validate_setup  # confere MinIO + fontes externas, cria os buckets
```

### Etapa 1: Ingestão (bucket `raw`)

```bash
python -m src.ingestion.download_ibge --ano 2025
python -m src.ingestion.download_pib --ano 2023   # PIB municipal (variável socioeconômica); série vai até 2023
python -m src.ingestion.download_area            # área territorial (IBGE/SIDRA); sem --ano de propósito, ver docs/decisoes_limpeza.md
python -m src.ingestion.download_cnes             # estabelecimentos de saúde (CNES); tb sem --ano de propósito
python -m src.ingestion.download_fronteira        # lista oficial de faixa de fronteira (IBGE, 2024); tb sem --ano de propósito
python -m src.ingestion.download_snis             # saneamento básico (SNIS, via Base dos Dados); baixa o painel histórico completo
python -m src.ingestion.inspect_pni --ano 2025 --mes 1   # confirma o schema real antes de limpar
```

O PNI (doses aplicadas) **não** passa por `download_pni.py` aqui — ver a
Etapa 2 abaixo, ele é baixado direto da fonte pelo próprio `clean_pni.py`,
sem gravar em `raw`.

### Etapa 2: Limpeza e Análise Exploratória (buckets `trusted` / `refined`)

```bash
python -m src.cleaning.clean_ibge --ano 2025
python -m src.cleaning.clean_pib --ano 2023
python -m src.cleaning.clean_area                  # área territorial/densidade demográfica; sem --ano de propósito
python -m src.cleaning.clean_cnes                  # estabelecimentos de saúde; tb sem --ano de propósito
python -m src.cleaning.clean_fronteira              # lista oficial de faixa de fronteira; tb sem --ano de propósito
python -m src.cleaning.clean_snis                   # saneamento básico; filtra o ano de referência (2022) internamente
python -m src.cleaning.clean_pni --ano 2025
python -m src.cleaning.build_coverage --ano 2025   # cruza PIB, área/densidade, CNES, fronteira e saneamento automaticamente (--ano-pib, default 2023)
jupyter notebook notebooks/02_analise_exploratoria.ipynb
```

`clean_pni.py --ano 2025` baixa **e** limpa os 12 meses do PNI num único
comando, direto da fonte (OpenDataSUS), mês a mês, sem nunca gravar o ZIP
bruto em `raw` — baixar os 12 meses inteiros para `raw` primeiro já
esgotou o disco do Codespace numa tentativa anterior (ver
`docs/decisoes_limpeza.md`, seção 2). `download_pni.py` continua
disponível, mas é opcional: só faz sentido se você quiser arquivar os
ZIPs brutos em `raw` de propósito (ex.: auditoria) — nesse caso, rode-o
antes e use `clean_pni.py --ano 2025 --from-raw` para reaproveitar o que
foi arquivado em vez de baixar de novo.

**Atenção:** `build_coverage.py` usa o mesmo `--ano` para localizar tanto a
população quanto as doses no `trusted` (`ibge/populacao/ano={ano}/...` e
`pni/ano={ano}/...`). Rode `clean_ibge` sempre com o **mesmo** `--ano`
passado a `build_coverage` — usar anos diferentes faz `build_coverage` ler
uma partição de população desatualizada ou inexistente, sem erro nenhum
visível na hora. Foi exatamente esse desalinhamento que causou um bug real
nesta sessão (ver `docs/decisoes_limpeza.md`, seção 8).

Guia passo a passo completo (do zero até o final da Etapa 2, com solução
de problemas comuns) em
[`docs/guia_setup_etapa2.md`](docs/guia_setup_etapa2.md).

### Etapa 3: Construção de Modelos

```bash
jupyter notebook notebooks/03_construcao_modelos.ipynb   # treino, comparação de modelos e avaliação
python -m src.inference.predict --ano 2025 --top 20      # inferência em lote: gera a priorização
```

O notebook depende só do `refined/cobertura_vacinal` já gerado pela Etapa 2
(mesmos comandos acima). Decisões de alvo, algoritmos, split e limitações em
[`docs/decisoes_modelagem.md`](docs/decisoes_modelagem.md).

`src/inference/predict.py` é o fluxo automatizado que aplica o modelo:
treina no ano de referência, pontua o ano alvo e grava
`refined/priorizacao/ano={ano}/priorizacao_municipios.parquet` (mais um
`.csv` e um relatório de execução). Com um único ano processado, treino e
pontuação usam o mesmo ano e a saída é uma **priorização transversal**, não
uma previsão — quando houver um segundo ano, `--ano-referencia 2025 --ano
2026` já faz o fluxo temporal sem mudança de código. A saída é um **ranking
por probabilidade**, não um rótulo binário, porque o modelo (F1 ≈ 0,40) é
útil para ordenar, não para decidir sozinho.

Decisões de limpeza (o quê e por quê) estão documentadas em
[`docs/decisoes_limpeza.md`](docs/decisoes_limpeza.md); o schema de cada
camada de dado está em [`docs/dicionario_dados.md`](docs/dicionario_dados.md).
Evidência de que o pipeline roda de ponta a ponta contra dado real
(volumes processados, testes, notebook executado, histórico de commits)
está em [`docs/evidencia_execucao.md`](docs/evidencia_execucao.md).

Os nomes de coluna do CSV do PNI usados em `src/cleaning/clean_pni.py` já
foram **confirmados contra o schema real** da fonte (`co_municipio_paciente`,
`dt_vacina`, `sg_imunobiologico`, `co_dose_vacina`, `nu_idade_paciente` — ver
`docs/dicionario_dados.md`). Os nomes hipotéticos usados antes de termos
acesso aos dados continuam como fallback em `COLUMN_CANDIDATES`, caso o
schema mude entre anos; `inspect_pni.py` permite reconferir a qualquer
momento.

### Testes

```bash
pip install pytest
python -m pytest tests/ -v
```

São **87 testes**, rodando automaticamente a cada `push`/`pull request` nas
branches `main` e `etapa-*` (ex.: `etapa-2`) via GitHub Actions
(`.github/workflows/tests.yml`), sem dependência de MinIO ou rede: cobrem
apenas as funções puras de limpeza, cruzamento e inferência (ver decisão de
arquitetura em `docs/decisoes_limpeza.md`).

## Licença

Projeto acadêmico desenvolvido para fins educacionais.
