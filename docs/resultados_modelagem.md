# Resultados da Modelagem (Etapa 3)

Este documento reúne, com texto explicativo, os gráficos gerados pelo
notebook [`notebooks/03_construcao_modelos.ipynb`](../notebooks/03_construcao_modelos.ipynb)
e salvos em `reports/` — mesmo espírito de
[`docs/analise_exploratoria.md`](analise_exploratoria.md) (Etapa 2): cada
gráfico vem acompanhado do porquê de ter sido gerado, do que mostra, e do
que isso significa para o objetivo do projeto. As decisões técnicas por
trás de cada escolha (alvo, split, algoritmos, métricas) estão
documentadas com a justificativa completa em
[`docs/decisoes_modelagem.md`](decisoes_modelagem.md); aqui o foco é
interpretar o que os números e gráficos realmente mostram.

## 1. Comparação de modelos de classificação

A pergunta desta seção é "qual dos algoritmos testados classifica melhor
o risco de baixa cobertura, e por quê?". Comparamos três modelos no
conjunto de **validação** (o teste ainda não foi usado neste ponto — ver
`docs/decisoes_modelagem.md`, seção 3, sobre por que o teste é reservado
para o final):

| Modelo | F1 validação | Accuracy | Precision | Recall | ROC-AUC |
|---|---|---|---|---|---|
| **Random Forest** (melhor) | **0,435** | 0,614 | 0,343 | 0,593 | 0,629 |
| XGBoost | 0,426 | 0,596 | 0,331 | 0,598 | 0,624 |
| Regressão Logística | 0,415 | 0,534 | 0,303 | 0,660 | 0,593 |

**Leitura:** Random Forest venceu por F1, com margem pequena sobre o
XGBoost (0,435 vs. 0,426) — o suficiente para justificar o uso de um
modelo mais robusto a não-linearidade, mas pequeno o bastante para não
descartar o XGBoost como alternativa próxima. A Regressão Logística fica
em 3º (0,415), mas com um trade-off bem diferente entre precisão e
recall: prioriza recall (0,660, o maior dos três) às custas de precisão
(0,303, a menor); Random Forest e XGBoost são mais conservadores (recall
~0,59, precisão ~0,33-0,34) — para o caso de negócio de priorizar
campanhas, recall alto tem mais valor prático (deixar de identificar um
município de risco custa mais do que investigar um que não precisava), o
que mantém a Regressão Logística como alternativa legítima, mesmo em
3º lugar por F1, se o gestor de saúde pública priorizar não deixar
nenhum município de risco de fora em vez de precisão. Estes números
refletem a versão do dataset com a lista oficial de fronteira do IBGE e
densidade demográfica já integradas — ver `docs/decisoes_modelagem.md`,
seção 9, para a comparação com a rodada anterior (antes dessas duas
features).

**Nota sobre o KNN:** uma versão anterior deste notebook também testou
KNN. Ele foi removido da comparação final — não por preferência
metodológica, mas porque a comparação com ele era estruturalmente
desigual (`KNeighborsClassifier` do scikit-learn não aceita o parâmetro
`class_weight`, então, ao contrário dos três modelos acima, nunca recebeu
o mesmo tratamento de desbalanceamento de classes) e, mesmo assim, teve o
pior F1 de validação (0,188) com o padrão clássico de um modelo
enviesado para a classe majoritária — maior acurácia (0,690) e, ao mesmo
tempo, menor recall (0,144) da comparação. Justificativa completa em
`docs/decisoes_modelagem.md`, seção 4.

## 2. Avaliação do modelo escolhido no teste

![Matriz de confusão e curva ROC — Random Forest](../reports/matriz_confusao_roc.png)

Depois de escolher o Random Forest com base só na validação, ele é
avaliado **uma única vez** no conjunto de teste (836 municípios) — a
estimativa final e não-viesada de desempenho.

**O que o gráfico mostra:** a matriz de confusão à esquerda tem 385
verdadeiros negativos, 242 falsos positivos, 102 falsos negativos e 107
verdadeiros positivos. A curva ROC à direita fica visivelmente próxima da
diagonal (que representaria um classificador aleatório), com AUC = 0,58.

**Leitura:** desses números, F1 = 0,384 e ROC-AUC = 0,584 no teste —
um pouco abaixo da validação (0,435 e 0,629), mas dentro do que se
espera de flutuação amostral num teste de 836 municípios (o gap
treino/validação do próprio Random Forest é pequeno, 0,452 vs. 0,435 —
ver `docs/decisoes_modelagem.md`, seção 9 — o que não sugere overfitting
relevante). Em termos de negócio: o recall de 107/(107+102) ≈ 0,51
significa que o modelo identifica pouco mais da metade dos municípios
realmente de baixa cobertura — bem acima de um sorteio aleatório (que
pegaria ~25%, a proporção da classe), mesmo sem ser um preditor forte. A
precisão de 107/(107+242) ≈ 0,31 mostra o outro lado: de cada 10
municípios que o modelo aponta como risco, cerca de 3 de fato são — os
outros 7 seriam investigados à toa. Isso é o que caracteriza esta
ferramenta como um apoio à priorização, não um veredito automático.

## 3. Importância de features

![Importância de features — Random Forest](../reports/importancia_features.png)

Depois de saber que o modelo funciona (ainda que modestamente), a
pergunta natural é "o que ele está usando para decidir?".

**O que o gráfico mostra:** `log_pib_per_capita` lidera a importância
(~0,23), seguido de `log_estabelecimentos_saude_sus_por_100k_hab` (CNES,
~0,20), `log_populacao` (~0,175) e `log_densidade_hab_km2` (área/SIDRA,
~0,16); `cat_regiao_Sul` vem depois (~0,09) e, com contribuição bem
menor, `bin_fronteira` (~0,03) — quase empatado com a dummy de região
menos relevante.

**Leitura:** dois achados aqui, um mantido e um novo. O mantido é o
CNES: correlação de Pearson fraca com a cobertura isoladamente (0,089,
ver `docs/decisoes_modelagem.md`, seção 1), mas 2º lugar na importância
do Random Forest — não é contraditório, correlação mede só relação
linear univariada, e a árvore captura interações que a correlação
simples não enxerga (`docs/decisoes_modelagem.md`, seção 8). O achado
novo é sobre a fronteira: com a aproximação por UF (versão anterior
deste documento), `bin_fronteira` aparecia em 4º lugar (~0,13); com a
lista oficial do IBGE, caiu para o penúltimo lugar (~0,03). A queda não
significa que a fronteira deixou de importar — significa que a
aproximação por UF estava inflando esse sinal ao confundi-lo com o
efeito de pertencer a certos estados inteiros, não com a fronteira em
si. Densidade demográfica, por outro lado, entra como sinal novo
genuíno, direto na 4ª posição. Análise completa (incluindo o padrão
oposto observado na regressão, seção 5 abaixo) em
`docs/decisoes_modelagem.md`, seção 9.

## 4. Clusterização — quantos perfis de município existem?

![Método do cotovelo e silhouette score](../reports/cotovelo_silhueta.png)

Além de classificar risco, o projeto também segmenta municípios por
perfil (população, PIB per capita e cobertura) — um problema
não-supervisionado, sem alvo. A primeira decisão é quantos grupos (*k*)
usar.

**O que o gráfico mostra:** a inércia (esquerda) cai suavemente do k=2 ao
k=7, sem um "cotovelo" visualmente óbvio — por isso a decisão não se
apoiou só nessa curva. O silhouette score (direita) tem um pico claro em
k=3 (≈0,261), caindo depois disso.

**Leitura:** k=3 foi escolhido pelo critério mais objetivo dos dois — o
método do cotovelo aqui seria ambíguo por inspeção visual, mas o
silhouette score deixa claro que 3 grupos é onde cada município fica mais
bem encaixado no seu cluster em relação aos vizinhos (ver justificativa
completa em `docs/decisoes_modelagem.md`, seção 6).

![Clusters de municípios](../reports/clusters.png)

**O que o gráfico mostra:** os três clusters plotados por PIB per capita
(escala log) vs. cobertura — visualmente, a separação entre eles não é
óbvia neste plano 2D (o KMeans usa três dimensões: população, PIB per
capita e cobertura, todas em log), mas os números por trás contam uma
história clara:

| Cluster | Municípios | Cobertura média | População mediana | PIB per capita médio | % fronteira |
|---|---|---|---|---|---|
| 0 | 2.278 | 75,57 | 11.551,5 | R$ 18.797,41 | 3% |
| 1 | 1.198 | 80,99 | 52.338,0 | R$ 57.686,47 | 8% |
| 2 | 2.094 | **95,61** (maior) | **5.709,0** (menor) | R$ 50.354,93 | 17% |

**Leitura:** o Cluster 0 — maior grupo, menor cobertura média (75,6),
população mediana pequena (11.551 hab.) e PIB per capita mais baixo dos
três (R$ 18.797) — é o candidato natural a prioridade em campanhas de
imunização. O Cluster 2, de maior cobertura média (95,6), é também o de
**menor população mediana** (5.709 hab.) entre os três, e o de maior
percentual de municípios de fronteira (17%, ainda o dobro do Cluster 1 e
mais de cinco vezes o Cluster 0). Os percentuais de fronteira acima já
refletem a lista oficial do IBGE (588 municípios), bem mais baixos do
que uma versão anterior deste documento reportava com a aproximação por
UF (13%/36%/48%) — a aproximação superestimava fronteira por marcar
estados inteiros, não municípios específicos. A leitura qualitativa se
mantém, só menos dramática: isso é um sinal de alerta, não uma boa
notícia sem ressalvas — a seção 5 do notebook 02 já mostrou que
municípios pequenos têm a métrica de cobertura mais volátil (poucas
doses mudam bastante o percentual), e a seção 4 mostrou o efeito de
fronteira inflando cobertura por atendimento a não-residentes. A
cobertura mais alta deste cluster provavelmente é, em parte, esse duplo
efeito — não necessariamente melhor acesso real à vacinação. Tratar o
Cluster 2 como "referência de boa cobertura" sem essa ressalva seria uma
leitura ingênua dos dados.

## 5. Enquadramento complementar: regressão da cobertura contínua

A classificação (seções 1-2) responde uma pergunta binária — "este
município está entre os piores 25% do país?" — que descarta informação
por construção: dois municípios abaixo do corte, um levemente e outro
extremamente, recebem o mesmo rótulo. A regressão prevê a cobertura
contínua diretamente, para desempatar a ordem dentro do grupo de risco
(justificativa completa em `docs/decisoes_modelagem.md`, seção 7).

Comparação na validação (mesmo split da classificação):

| Modelo | RMSE validação | R² validação | Tempo de treino |
|---|---|---|---|
| **XGBoost** (melhor) | **54,04** | 0,038 | 13,7s |
| Random Forest | 54,15 | 0,034 | 57,5s |
| Ridge (linear) | 54,71 | 0,014 | 0,3s |

**Leitura:** diferente de uma versão anterior deste documento — quando os
três modelos empatavam tecnicamente e o Ridge vencia por uma margem
irrelevante —, com a fronteira oficial e a densidade demográfica
integradas o empate se desfez: XGBoost e Random Forest (os dois modelos
em árvore) ficam próximos entre si e claramente à frente do Ridge, numa
diferença (0,67 de RMSE) grande o bastante para não ser só ruído
amostral. Isso é, em si, um achado: os modelos em árvore passaram a
capturar interação/não-linearidade que o modelo linear não alcança —
decisão completa e justificativa por modelo em
`docs/decisoes_modelagem.md`, seções 9 e 10.

No teste, o modelo agora vencedor (XGBoost) chegou a RMSE = 15,25,
MAE = 11,77 e **R² = 0,128** — mais que o dobro do R² de teste do Ridge
na rodada anterior (0,062). É o primeiro ganho de poder preditivo real
observado neste projeto que não é atribuível a ruído de amostragem.

![Importância de features — XGBoost (regressão)](../reports/importancia_features_regressao.png)

**O que o gráfico mostra:** para o XGBoost, a "importância" é a
contribuição de cada feature nas divisões das árvores. `cat_regiao_Centro-Oeste`
(≈0,185) e `bin_fronteira` (≈0,18) lideram, seguidos por
`log_densidade_hab_km2` (≈0,10) e `cat_regiao_Sul` (≈0,10);
`log_populacao` e `log_pib_per_capita` ficam no meio (≈0,09 e ≈0,085);
`log_estabelecimentos_saude_sus_por_100k_hab` (CNES) é a numérica menos
importante (≈0,07).

**Leitura:** aqui a fronteira **continua** entre as features mais fortes
— mesmo usando a lista oficial do IBGE, não a aproximação por UF. Isso
contrasta com a classificação (seção 3), onde a fronteira oficial caiu
para quase irrelevante. A leitura registrada em
`docs/decisoes_modelagem.md`, seção 9: a fronteira tem pouco poder para
prever **em qual quartil** de cobertura um município cai, mas pesa
bastante para prever a **magnitude exata** da cobertura — consistente
com o efeito "caravana da vacina" (municípios de fronteira puxando a
cobertura para valores muito altos, não só acima/abaixo de um corte).
Os dois resultados não se contradizem: medem coisas diferentes.

![Previsto vs. real e resíduos — XGBoost](../reports/regressao_previsto_vs_real.png)

**O que o gráfico mostra:** à esquerda, cobertura prevista vs. real no
teste — os pontos previstos ficam concentrados numa faixa mais ampla que
antes (~60-140), mas ainda longe de acompanhar toda a variação real do
eixo x (que vai de ~40 a ~190). À direita, os resíduos (real − previsto)
espalhados sem um padrão sistemático óbvio em torno de zero, incluindo
alguns pontos acima de 40-60 de resíduo.

**Leitura:** o modelo ainda erra bastante em valor absoluto, mas passou
a acompanhar mais da variação real do que a versão com o Ridge — visível
tanto na faixa mais ampla de valores previstos quanto no R² de teste
(0,128, o dobro do anterior). Os resíduos não mostram um padrão
sistemático (por exemplo, um funil ou uma curva), o que é uma checagem
de saúde importante: o modelo erra de forma consistente em magnitude,
não de um jeito que sugira uma variável relevante ficou de fora de forma
estruturada — a limitação segue sendo volume/variedade de features
(seis sinais), não um bug ou uma feature crítica ausente.

## 6. Síntese

Os seis gráficos deste documento contam a mesma história por ângulos
diferentes: o pipeline funciona, os modelos são honestos sobre suas
limitações, e nenhum sinal isolado "domina, de longe" — PIB per capita e
CNES lideram a importância na classificação; fronteira e região lideram
na regressão. A troca da fronteira aproximada por UF pela lista oficial
do IBGE foi o achado metodológico mais importante desta rodada: revelou
que parte do sinal de fronteira visto antes era artefato de uma medição
grosseira, não um efeito real tão forte quanto parecia — ao mesmo tempo
em que confirmou, com dado preciso, que a fronteira genuinamente importa
para a **magnitude** da cobertura (regressão), mesmo não importando tanto
para separar os piores 25% (classificação). A regressão também deixou de
ser um empate técnico de três modelos: XGBoost passou a vencer com folga
suficiente para virar a recomendação principal, dobrando o R² de teste do
Ridge. As decisões que vieram desses achados (alvo binário por quartil,
seis features, clusterização em 3 grupos, regressão como complemento e
recomendação de modelo) estão registradas com a justificativa completa
em [`docs/decisoes_modelagem.md`](decisoes_modelagem.md), assim como as
limitações conhecidas e os próximos passos priorizados pela equipe.
