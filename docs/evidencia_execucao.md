# Evidência de Execução do Pipeline

Este documento reúne evidências concretas de que o pipeline descrito em
`docs/arquitetura_pipeline.svg` roda de ponta a ponta contra dados reais —
não só no papel. Os números abaixo vêm de execuções reais no ambiente de
desenvolvimento (GitHub Codespaces + MinIO local via `docker-compose.yml`).

## 0. Dataset bruto (raw) existe de verdade e é inspecionável

O bucket `raw` do MinIO, listado diretamente via `boto3` (mesmo cliente que
o código do projeto usa, `src/config.py`):

```
=== objetos em raw/ ===
ibge/pib/ano=2023/pib_municipios.csv  (641961 bytes)
ibge/populacao/ano=2024/populacao_municipios.csv  (572594 bytes)
ibge/populacao/ano=2025/populacao_municipios.csv  (572594 bytes)
ibge/area/area_municipios.csv
ibge/fronteira/municipios_faixa_fronteira.xls
cnes/cnes_estabelecimentos.zip
basedosdados/snis/municipio_agua_esgoto.csv.gz
```

(Os três primeiros são da listagem original, com os tamanhos conferidos na
época; os quatro seguintes correspondem às fontes adicionadas depois —
área, faixa de fronteira, CNES e saneamento —, cujas chaves estão fixadas
em `RAW_KEY` nos respectivos scripts de ingestão e documentadas em
`docs/dicionario_dados.md`.)

E o conteúdo real (primeiras linhas, sem nenhuma transformação) de um
desses arquivos brutos — exatamente como a API do SIDRA devolve, incluindo
a linha de metadados que `clean_ibge.py` precisa descartar (ver
`docs/decisoes_limpeza.md`, seção 1):

```
=== primeiras 12 linhas de raw/ibge/populacao/ano=2024/populacao_municipios.csv ===
NC,NN,MC,MN,V,D1C,D1N,D2C,D2N,D3C,D3N
Nível Territorial (Código),Nível Territorial,Unidade de Medida (Código),Unidade de Medida,Valor,Município (Código),Município,Variável (Código),Variável,Ano (Código),Ano
6,Município,45,Pessoas,22853,1100015,Alta Floresta D'Oeste - RO,9324,População residente estimada,2024,2024
6,Município,45,Pessoas,108573,1100023,Ariquemes - RO,9324,População residente estimada,2024,2024
6,Município,45,Pessoas,5690,1100031,Cabixi - RO,9324,População residente estimada,2024,2024
6,Município,45,Pessoas,97637,1100049,Cacoal - RO,9324,População residente estimada,2024,2024
```

O `raw/ibge/pib/ano=2023/pib_municipios.csv` (641.961 bytes) segue o
mesmo formato bruto da API SIDRA, documentado em
`docs/dicionario_dados.md`. O PNI **não aparece aqui de propósito** — por
padrão `clean_pni.py` não grava o ZIP bruto em `raw` (ver
`docs/decisoes_limpeza.md`, seção 2, e `docs/criterios_selecao_dados.md`);
quem quiser o ZIP bruto arquivado roda `download_pni.py` antes, o que o
gravaria aqui do mesmo jeito que IBGE/PIB.

## 1. Volume de dado real processado (PNI, ano completo de 2025)

Rodando `python -m src.cleaning.clean_pni --ano 2025` (fluxo padrão: baixa
cada um dos 12 meses direto da fonte, limpa em streaming e grava só o
parquet agregado em `trusted`, sem gravar os ZIPs brutos em `raw`):

- **12 meses** processados (jan-dez/2025), nenhum mês faltando.
- **2.031.418 linhas** no parquet consolidado, agregadas por **município ×
  mês × vacina** (as chaves de agregação em `clean_pni.py`). Não confundir
  com município × mês, que daria 5.571 × 12 = 66.852 linhas: a dimensão de
  imunobiológico é preservada na camada trusted, e só é somada no
  cruzamento.
- **175,9 milhões de doses aplicadas** somadas em todo o ano
  (175.914.300, conferido pela soma das 27 UFs no notebook 02).
- **5.571 municípios** presentes no dataset `refined` final — nenhum
  município brasileiro ficou de fora do cruzamento.

(Números também registrados em `docs/decisoes_limpeza.md`, seção
"Pendências conhecidas", junto com o histórico de como o problema de disco
que impedia processar o ano completo foi resolvido.)

## 2. Testes automatizados

**87 testes automatizados** (`pytest`), cobrindo as funções puras de
limpeza, cruzamento e inferência — `clean_ibge`, `clean_pib`, `clean_pni`,
`clean_area`, `clean_cnes`, `clean_fronteira`, `clean_snis`,
`build_coverage` e `inference.predict` —, sem depender de MinIO ou rede.
Rodam localmente com:

```bash
python -m pytest tests/ -v
```

e automaticamente a cada `push`/pull request nas branches `main` e
`etapa-*` (ex.: `etapa-2`), via GitHub Actions
(`.github/workflows/tests.yml`) — o selo no topo do `README.md` reflete o
status da última execução no repositório real:
`https://github.com/leonardohakim/imuniza-data-handson-mackenzie/actions/workflows/tests.yml`.

## 3. Notebook de análise exploratória executado contra dado real

`notebooks/02_analise_exploratoria.ipynb` está commitado **com os outputs
de uma execução real** (não só o código): células rodadas contra o
`refined/cobertura_vacinal/ano=2025/cobertura_municipios.parquet` gerado
pelo pipeline. Os dois notebooks juntos produzem os **11 gráficos** hoje
versionados em `reports/` — cinco da análise exploratória (notebook 02) e
seis da modelagem (notebook 03). Execução do notebook 02 (reprocessamento
dos gráficos 1-3 após revisão de legibilidade):

```
$ jupyter nbconvert --to notebook --execute --inplace notebooks/02_analise_exploratoria.ipynb
[NbConvertApp] Converting notebook notebooks/02_analise_exploratoria.ipynb to notebook
[NbConvertApp] Writing 312387 bytes to notebooks/02_analise_exploratoria.ipynb

$ ls -la reports/*.png
-rw-rw-rw- 1 codespace codespace  60223 Aug 31 22:18 reports/cobertura_por_uf.png
-rw-rw-rw- 1 codespace codespace 121473 Aug 31 22:18 reports/cobertura_vs_pib_per_capita.png
-rw-rw-rw- 1 codespace codespace  53752 Aug 31 22:18 reports/cobertura_vs_populacao.png
-rw-rw-rw- 1 codespace codespace  76977 Aug 31 22:18 reports/distribuicao_cobertura.png
```

Reexecutar do zero (com o MinIO local rodando e o pipeline já materializado
até `refined`) é um único comando, sem edição manual:

```bash
jupyter nbconvert --to notebook --execute --inplace notebooks/02_analise_exploratoria.ipynb
```

## 4. Histórico real de commits do pipeline (não só um "commit único de entrega")

O histórico do repositório mostra o pipeline sendo construído, testado
contra dado real e corrigido incrementalmente — incluindo bugs reais
encontrados só ao rodar contra os dados de verdade (documentados em
`docs/decisoes_limpeza.md`), não um código nunca executado:

```
$ git log --oneline --reverse
0896f29 Initial commit
...
109f58b feat: pipeline de ingestao PNI com streaming, idempotencia e manifesto de governanca
568bddc fix: processa CSVs do PNI em streaming e corrige nomes de coluna reais
ab3d6f0 fix: corrige cruzamento codigo DATASUS (6 digitos) x IBGE (7 digitos) na cobertura
f9d889d test: adiciona suite pytest para clean_ibge, clean_pni e build_coverage
b480e3b docs: executa notebook EDA contra dados reais de 2025 e salva graficos
dc60242 feat: coleta PIB per capita municipal e cruza com cobertura vacinal
0531ed0 chore: adiciona CI (GitHub Actions) rodando pytest a cada push/PR
c8b3e80 fix: adiciona diagrama de arquitetura do pipeline e corrige bug na coluna ano da populacao IBGE
5c7d9e0 fix: reprocessa populacao ano=2025 com o codigo corrigido (build_coverage le essa particao, nao ano=2024)
e0188ed fix: incorpora reprocessar_pni_2025.py a clean_pni.py como fluxo padrao
9538b5c fix: melhora legibilidade dos graficos 1, 2 e 3 do notebook exploratorio
```

Repositório real:
`https://github.com/leonardohakim/imuniza-data-handson-mackenzie`

## 5. Notebook de construção de modelos (Etapa 3) executado contra dado real

`notebooks/03_construcao_modelos.ipynb` também está commitado com os
outputs de uma execução real contra o
`refined/cobertura_vacinal/ano=2025/cobertura_municipios.parquet` gerado
pelo pipeline. Os números abaixo são os da **execução atual**, que já
inclui as sete fontes (com fronteira oficial do IBGE e saneamento/SNIS):

- **Base de modelagem**: 5.571 municípios no refined, menos 1 sem
  PIB/população/cobertura/CNES e menos 146 sem o indicador de água do
  SNIS (descartados, nunca imputados) → **5.424 municípios**.
- **Fronteira**: 511 municípios com sede na faixa oficial; **502** (9,3%)
  sobrevivem aos descartes e chegam à base de modelagem.
- **Alvo (`baixa_cobertura`)**: 1º quartil de
  `cobertura_doses_por_100_habitantes` na base de modelagem = **73,25
  doses/100 hab.**; distribuição 75%/25%.
- **Split treino/validação/teste**: **3.796 / 814 / 814** municípios
  (70/15/15, estratificado — proporção de positivos 0,250 / 0,251 / 0,249).
- **Comparação dos 3 modelos (F1 na validação, `GridSearchCV` 5-fold)**:
  Random Forest **0,446** (melhor; accuracy 0,615, precision 0,349, recall
  0,618, ROC-AUC 0,661, 26,9s de treino), Regressão Logística **0,428**
  (accuracy 0,531, recall 0,701, ROC-AUC 0,637, 3,2s — margem pequena para
  o Random Forest, vale considerar se a perda de interpretabilidade
  compensa), XGBoost **0,425** (accuracy 0,604, ROC-AUC 0,635, 12,4s). O
  KNN foi testado numa rodada anterior e **removido** da comparação final
  por não aceitar o mesmo tratamento de classes desbalanceadas dos demais
  (`class_weight`) — ver `docs/decisoes_modelagem.md`, seção 4.
- **Modelo escolhido (Random Forest) no conjunto de teste**: F1 = **0,399**,
  ROC-AUC = **0,604**; matriz de confusão 357 VN / 254 FP / 89 FN / 114 VP.
- **Checagem de overfitting** (gap F1 treino−validação): Regressão
  Logística −0,018, Random Forest 0,022 (ambos pequenos), XGBoost 0,103
  (moderado, leve indício).
- **Clusterização (K-Means, k=3 escolhido por silhouette score)**: o
  cluster de maior cobertura média (**95,13** doses/100 hab.) também é o de
  menor população mediana (**5.706** habitantes) entre os três — o notebook
  sinaliza automaticamente, quando isso acontece, que a métrica de
  cobertura é mais volátil em municípios pequenos (achado já registrado
  na seção 5 do notebook 02), então essa cobertura mais alta pode ser em
  parte esse efeito de volatilidade, não necessariamente melhor acesso
  real à vacinação.

Todas as decisões por trás desses números (definição do alvo, escolha dos
algoritmos, remoção do KNN, tratamento de desbalanceamento, métricas)
estão documentadas e justificadas em
[`docs/decisoes_modelagem.md`](decisoes_modelagem.md), e a narrativa de
cada gráfico em
[`docs/resultados_modelagem.md`](resultados_modelagem.md).

### 5.1. Evolução ao longo das rodadas e regressão complementar

O projeto passou por rodadas sucessivas de enriquecimento de features
(CNES → área/densidade → fronteira oficial → saneamento). O que se
observou, de forma consistente, é que **nenhuma delas moveu o desempenho
agregado de forma relevante**: o F1 de teste oscilou entre 0,39 e 0,40 e
o ROC-AUC entre 0,58 e 0,60 em todas elas. A leitura honesta é que o
limite não está no número de features, e sim no fato de que a cobertura
municipal depende de fatores que nenhuma dessas bases públicas captura
(gestão local, logística, adesão da população).

O achado interessante veio da **importância de features**, não do
desempenho: variáveis com correlação linear quase nula com o alvo
aparecem entre as mais importantes do Random Forest. O CNES
(`log_estabelecimentos_saude_sus_por_100k_hab`) está em **2º lugar**
(~0,147) com correlação de apenas 0,090, e o saneamento
(`pct_atendimento_agua`) em **5º** (~0,128) com correlação de −0,019.
Análise completa em `docs/decisoes_modelagem.md`, seção 11.

A mesma execução roda a seção de regressão complementar (alvo contínuo
`cobertura_doses_por_100_habitantes`, mesmo split): o **Random Forest**
venceu na validação por RMSE (55,14 doses/100 hab., R² = 0,026), com o
XGBoost a 0,055 de distância — margem pequena o suficiente para que os
dois sejam tratados como equivalentes, e não um como vencedor (seção 10
de `decisoes_modelagem.md`). No teste chegou a RMSE = 15,99, MAE = 11,99
e R² = 0,111. A diferença de RMSE entre validação (55,14) e teste (15,99)
é grande porque o split é estratificado só pelo alvo binário, não pelo
contínuo: os municípios de cobertura extrema caíram na validação —
explicação completa (não é bug) também em `docs/decisoes_modelagem.md`.

**Bug real encontrado e corrigido ao rodar contra o Codespace**: a
primeira versão do notebook configurava tanto o `GridSearchCV`
(`n_jobs=-1`) quanto os próprios estimadores `RandomForestClassifier` e
`XGBClassifier` (também `n_jobs=-1`) para paralelizar — esse paralelismo
aninhado (dois níveis de processos/threads disputando os mesmos núcleos)
travou o terminal do Codespace ao rodar `jupyter nbconvert --execute`,
pela restrição de CPU do ambiente. Corrigido fixando `n_jobs=1` nos
estimadores e mantendo o paralelismo só no `GridSearchCV`; reexecutado com
sucesso, sem travar, na tentativa seguinte. Relato completo em
`docs/decisoes_modelagem.md`, seção 4.1.

## 6. Pipeline de inferência em lote

O projeto não para no notebook de avaliação: `src/inference/predict.py` é
o fluxo automatizado que **aplica** o modelo e responde a pergunta de
negócio em forma de lista acionável.

```bash
python -m src.inference.predict --ano 2025 --top 20
```

O comando lê o `refined/cobertura_vacinal`, treina o Random Forest com os
hiperparâmetros já eleitos pela busca do notebook (sem refazer o
`GridSearchCV`, para que a inferência seja estável e auditável), pontua
cada município e grava em
`refined/priorizacao/ano=2025/` três objetos: o parquet com o ranking, um
CSV equivalente e um `_inference_report.txt` com os descartes, o corte do
alvo e as features usadas.

Duas características da saída merecem registro, porque são decisões e não
acidentes:

- **É um ranking, não um rótulo.** O campo principal é
  `probabilidade_baixa_cobertura`, com `ranking_prioridade` ao lado. Com
  F1 ≈ 0,40 e ROC-AUC ≈ 0,60, entregar uma decisão binária automática
  ("este município é de risco") seria irresponsável; ordenar para
  priorizar é o que o modelo faz bem o suficiente para ser útil.
- **É priorização, não previsão.** Com um único ano processado, treino e
  pontuação usam o mesmo ano, e o relatório de execução diz isso
  explicitamente. Quando houver um segundo ano,
  `--ano-referencia 2025 --ano 2026` transforma o mesmo comando no fluxo
  temporal sem nenhuma mudança de código.

As funções puras desse módulo (`preparar_features`, `definir_alvo`,
`construir_modelo`, `gerar_priorizacao`) são cobertas por 9 dos 87 testes
automatizados, incluindo um teste que garante que a reordenação do ranking
não desalinha as colunas do município.

## 7. Como reproduzir do zero

Passo a passo completo, incluindo troubleshooting de problemas reais já
encontrados pela equipe (disco cheio, bucket com nome errado, coluna
lida errada), em
[`docs/guia_setup_etapa2.md`](guia_setup_etapa2.md). Resumo dos comandos em
[`README.md`](../README.md), seção "Como Executar".
