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

## Fontes de Dados

- **DATASUS / TabNet (SI-PNI)**: Sistema de Informações do Programa Nacional de Imunizações
- **OpenDataSUS**: bases granulares de doses aplicadas por município, período e faixa etária
- **IBGE / SIDRA**: dados demográficos e socioeconômicos por município (população, PIB per capita); ver `docs/decisoes_limpeza.md` sobre por que renda/IDH foram descartados em favor do PIB

## Estrutura do Projeto

Os dados não ficam em pastas locais: vivem em três buckets do MinIO
(subida via `docker-compose.yml`), seguindo a convenção raw → trusted →
refined:

```
imuniza-data-handson-mackenzie/
├── docs/
│   ├── dicionario_dados.md     # Schema de cada camada (raw/trusted/refined)
│   └── decisoes_limpeza.md     # Decisões de limpeza documentadas e justificadas
├── notebooks/                  # Notebooks de exploracao e prototipagem
├── src/
│   ├── config.py                # Configuração de acesso ao MinIO
│   ├── validate_setup.py        # Healthcheck do MinIO e das fontes externas
│   ├── ingestion/                # Etapa 1: coleta (fontes -> bucket "raw")
│   │   ├── download_ibge.py
│   │   ├── download_pib.py
│   │   ├── download_pni.py
│   │   └── inspect_pni.py
│   └── cleaning/                  # Etapa 2: limpeza (bucket "raw" -> "trusted" -> "refined")
│       ├── clean_ibge.py
│       ├── clean_pib.py
│       ├── clean_pni.py
│       └── build_coverage.py
├── tests/                        # Testes automatizados (pytest)
├── reports/                     # Gráficos e relatórios gerados pelos notebooks
├── docker-compose.yml            # MinIO local (buckets raw / trusted / refined)
└── README.md
```

## Metodologia

### Etapa 1: Ingestão de Dados
Coleta programática de dados de vacinação (SI-PNI/OpenDataSUS) e dados demográficos (IBGE/SIDRA), armazenados em camada raw preservando a granularidade original (município, mês/ano, tipo de vacina, faixa etária). Automação via Python (`pandas`, `requests`).

### Etapa 2: Análise Exploratória e Limpeza
Padronização dos códigos de município (IBGE, 7 dígitos), tratamento de valores ausentes e inconsistências, e construção da métrica central de cobertura vacinal (doses aplicadas / população-alvo). Identificação de outliers e análise de correlação com variáveis socioeconômicas.

### Etapa 3: Aplicação de ML e Treinamento de Modelos
- **Clusterização** (K-Means/DBSCAN) para segmentar municípios por perfil de cobertura vacinal e características socioeconômicas
- **Classificação** (Random Forest/XGBoost) para prever risco de baixa cobertura vacinal futura
- Análise de importância de features para identificar fatores associados à baixa cobertura

## Tecnologias

- Python (pandas, numpy, scikit-learn, requests)
- Jupyter Notebook
- Matplotlib / Seaborn / Plotly

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
python -m src.ingestion.download_ibge --ano 2024
python -m src.ingestion.download_pib --ano 2023   # PIB municipal (variável socioeconômica); série vai até 2023
python -m src.ingestion.download_pni --ano 2025
python -m src.ingestion.inspect_pni --ano 2025 --mes 1   # confirma o schema real antes de limpar
```

### Etapa 2: Limpeza e Análise Exploratória (buckets `trusted` / `refined`)

```bash
python -m src.cleaning.clean_ibge --ano 2024
python -m src.cleaning.clean_pib --ano 2023
python -m src.cleaning.clean_pni --ano 2025
python -m src.cleaning.build_coverage --ano 2025   # cruza PIB de 2023 automaticamente (--ano-pib, default 2023)
jupyter notebook notebooks/02_analise_exploratoria.ipynb
```

Decisões de limpeza (o quê e por quê) estão documentadas em
[`docs/decisoes_limpeza.md`](docs/decisoes_limpeza.md); o schema de cada
camada de dado está em [`docs/dicionario_dados.md`](docs/dicionario_dados.md).

Os nomes de coluna do CSV do PNI usados em `src/cleaning/clean_pni.py`
foram definidos sem acesso aos dados reais (ambiente de desenvolvimento sem
rede liberada para o DATASUS). Rode `inspect_pni.py` primeiro e ajuste
`COLUMN_CANDIDATES` nesse arquivo se os nomes reais divergirem.

### Testes

```bash
pip install pytest
python -m pytest tests/ -v
```

Os testes rodam automaticamente a cada `push`/`pull request` na branch `main`
via GitHub Actions (`.github/workflows/tests.yml`), sem dependência de MinIO
ou rede: cobrem apenas as funções puras de limpeza e cruzamento de dados
(ver decisão de arquitetura em `docs/decisoes_limpeza.md`).

## Licença

Projeto acadêmico desenvolvido para fins educacionais.
