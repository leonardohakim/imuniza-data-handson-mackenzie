# imuniza-data-handson-mackenzie
Projeto desenvolvido para a disciplina de Hands-on Engenharia de Dados aplicada à Saúde Pública.

ImunizaData

Projeto desenvolvido para a disciplina de Hands-on  Engenharia de Dados aplicada à Saúde Pública.

Integrantes
Nome	RA	GitHub
Leonardo Domingues Machado da Silva	10735382	@leonardohakim
Gabriel Cardoso Silva	10733004	
Gabriela Addesso Ruvolo	10735412	
Objetivo do Projeto

Utilizar engenharia de dados e análise de dados públicos para identificar municípios e grupos populacionais com baixa cobertura vacinal, permitindo priorizar ações de vacinação no âmbito do SUS (Sistema Único de Saúde).

A proposta busca transformar dados públicos, hoje dispersos e pouco explorados, em informação acionável para gestores de saúde pública — apoiando decisões sobre onde e para quem direcionar campanhas de imunização.

Fontes de Dados
DATASUS / TabNet (SI-PNI) — Sistema de Informações do Programa Nacional de Imunizações
OpenDataSUS — bases granulares de doses aplicadas por município, período e faixa etária
IBGE / SIDRA — dados demográficos e socioeconômicos por município (população, renda, IDH)
Estrutura do Projeto
handson-eng-dados-sus/


├── data/
│   ├── raw/            # Dados brutos, sem transformação
│   ├── processed/       # Dados limpos e padronizados
│   └── external/         # Dados auxiliares (IBGE, malhas geográficas etc.)
├── notebooks/          # Notebooks de exploração e prototipagem
├── src/
│   ├── ingestion/        # Scripts de coleta/extração de dados
│   ├── cleaning/          # Scripts de limpeza e padronização
│   └── models/            # Treinamento e avaliação de modelos de ML
├── reports/              # Análises, gráficos e relatórios finais
└── README.md

Metodologia
Etapa 1 — Ingestão de Dados

Coleta programática de dados de vacinação (SI-PNI/OpenDataSUS) e dados demográficos (IBGE/SIDRA), armazenados em camada raw preservando a granularidade original (município, mês/ano, tipo de vacina, faixa etária). Automação via Python (pandas, requests).

Etapa 2 — Análise Exploratória e Limpeza

Padronização dos códigos de município (IBGE, 7 dígitos), tratamento de valores ausentes e inconsistências, e construção da métrica central de cobertura vacinal (doses aplicadas / população-alvo). Identificação de outliers e análise de correlação com variáveis socioeconômicas.

Etapa 3 — Aplicação de ML e Treinamento de Modelos
Clusterização (K-Means/DBSCAN) para segmentar municípios por perfil de cobertura vacinal e características socioeconômicas
Classificação (Random Forest/XGBoost) para prever risco de baixa cobertura vacinal futura
Análise de importância de features para identificar fatores associados à baixa cobertura
Tecnologias
Python (pandas, numpy, scikit-learn, requests)
Jupyter Notebook
Matplotlib / Seaborn / Plotly
Como Executar
bash
git clone https://github.com/leonardohakim/handson-eng-dados-sus.git
cd handson-eng-dados-sus
pip install -r requirements.txt
Licença

Projeto acadêmico desenvolvido para fins educacionais.
