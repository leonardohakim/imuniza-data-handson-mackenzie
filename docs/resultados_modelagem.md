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

| Modelo | F1 validação | Accuracy | Precision | Recall | ROC-AUC | Tempo de treino |
|---|---|---|---|---|---|---|
| **Random Forest** (melhor) | **0,446** | 0,615 | 0,349 | 0,618 | 0,661 | 26,93s |
| Regressão Logística | 0,428 | 0,531 | 0,308 | 0,701 | 0,637 | 3,19s |
| XGBoost | 0,425 | 0,604 | 0,334 | 0,583 | 0,635 | 12,41s |

**Leitura:** Random Forest venceu por F1, com margem pequena sobre a
Regressão Logística (0,446 vs. 0,428) — pequena o bastante para não
descartar a Regressão Logística como alternativa legítima, especialmente
porque ela tem o maior recall dos três (0,701, contra ~0,58-0,62 dos
outros dois): prioriza recall às custas de precisão (0,308, a menor),
o que para o caso de negócio de priorizar campanhas tem valor prático
real — deixar de identificar um município de risco custa mais do que
investigar um que não precisava. XGBoost, que vencia nesta comparação na
rodada anterior, caiu para 3º lugar nesta rodada — a ordem entre os três
modelos mudou de uma reexecução para a outra, um lembrete de que a
distância entre eles é pequena o suficiente para inverter com uma
feature nova (ver `docs/decisoes_modelagem.md`, seção 11). Estes números
já refletem a feature de saneamento (SNIS 2022, água) integrada ao
dataset — ver `docs/decisoes_modelagem.md`, seção 11, para a comparação
com a rodada anterior (antes dessa feature).

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
avaliado **uma única vez** no conjunto de teste (o dataset de modelagem
agora tem ~5.424 municípios após o `dropna` de água — ver
`docs/decisoes_modelagem.md`, seção 11) — a estimativa final e
não-viesada de desempenho.

**O que o gráfico mostra:** a matriz de confusão à esquerda tem 357
verdadeiros negativos, 254 falsos positivos, 89 falsos negativos e 114
verdadeiros positivos. A curva ROC à direita fica visivelmente próxima da
diagonal (que representaria um classificador aleatório), com AUC = 0,60.

**Leitura:** desses números, F1 = 0,399 e ROC-AUC = 0,604 no teste — um
pouco abaixo da validação (0,446 e 0,661), mas dentro do que se espera de
flutuação amostral (o gap treino/validação do próprio Random Forest é
pequeno, F1 treino 0,468 vs. validação 0,446 — ver
`docs/decisoes_modelagem.md`, seção 11 — o que não sugere overfitting
relevante). Em termos de negócio: o recall de 114/(114+89) ≈ 0,56
significa que o modelo identifica pouco mais da metade dos municípios
realmente de baixa cobertura — bem acima de um sorteio aleatório (que
pegaria ~25%, a proporção da classe), mesmo sem ser um preditor forte. A
precisão de 114/(114+254) ≈ 0,31 mostra o outro lado: de cada 10
municípios que o modelo aponta como risco, cerca de 3 de fato são — os
outros 7 seriam investigados à toa. Isso é o que caracteriza esta
ferramenta como um apoio à priorização, não um veredito automático.

## 3. Importância de features

![Importância de features — Random Forest](../reports/importancia_features.png)

Depois de saber que o modelo funciona (ainda que modestamente), a
pergunta natural é "o que ele está usando para decidir?".

**O que o gráfico mostra:** `log_pib_per_capita` lidera a importância
(~0,19), seguido de perto por
`log_estabelecimentos_saude_sus_por_100k_hab` (CNES, ~0,145) e
`log_populacao` (~0,145), depois `log_densidade_hab_km2` (área/SIDRA,
~0,14) e `pct_atendimento_agua` (SNIS, ~0,13); `cat_regiao_Sul` vem
depois (~0,10) e, com contribuição bem menor, `bin_fronteira` (~0,04) —
praticamente empatada com as dummies de região menos relevantes
(Centro-Oeste ~0,04, Nordeste ~0,035, Sudeste ~0,03).

**Leitura:** dois achados se repetem aqui, e um é novo desta rodada. O
que se repete: CNES e, agora, água (SNIS) têm correlação de Pearson
fraca ou quase nula com a cobertura isoladamente (0,090 e -0,019, ver
`docs/decisoes_modelagem.md`, seção 1), mas aparecem entre as features
mais importantes do Random Forest (2º/3º e 5º lugar) — não é
contraditório, correlação mede só relação linear univariada, e a árvore
captura interações que a correlação simples não enxerga
(`docs/decisoes_modelagem.md`, seções 8 e 11). `bin_fronteira` segue em
posição baixa (~0,04), como já acontecia com a lista oficial do IBGE
desde a rodada anterior. O achado novo desta rodada: a feature de água
entra direto em 5º lugar — à frente de fronteira e de todas as dummies
de região — mesmo tendo sido a que mais municípios descartou (146, ver
`docs/decisoes_modelagem.md`, seção 1). Análise completa (incluindo por
que o achado da rodada anterior sobre fronteira na regressão não se
repetiu nesta, seção 5 abaixo) em `docs/decisoes_modelagem.md`,
seção 11.

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
| 0 | 2.221 | 75,95 | 11.985,0 | R$ 18.672,16 | 3% |
| 1 | 2.052 | **95,13** (maior) | **5.706,0** (menor) | R$ 50.868,85 | 17% |
| 2 | 1.151 | 80,86 | 54.192,0 | R$ 58.497,68 | 8% |

(O KMeans não garante que o mesmo perfil saia sempre com o mesmo número
de cluster entre reexecuções — o que importa é o perfil, não o índice;
nesta rodada o perfil de menor cobertura saiu como cluster 0, o de maior
cobertura e menor população como cluster 1, e o de maior população como
cluster 2, na mesma ordem qualitativa das rodadas anteriores.)

**Leitura:** o Cluster 0 — maior grupo (2.221 municípios), menor
cobertura média (76,0), população mediana pequena (11.985 hab.) e PIB
per capita mais baixo dos três (R$ 18.672) — é o candidato natural a
prioridade em campanhas de imunização. O Cluster 1, de maior cobertura
média (95,1), é também o de **menor população mediana** (5.706 hab.)
entre os três, e o de maior percentual de municípios de fronteira (17%,
mais que o dobro do Cluster 2 e mais de cinco vezes o Cluster 0). O
tamanho dos clusters e os percentuais mudaram ligeiramente desde a
rodada anterior (a rodada anterior tinha 2.278/1.198/2.094 municípios
nos perfis equivalentes) — em parte por causa do dropna de água (146
municípios a menos no dataset total), não necessariamente por uma
mudança de fundo no padrão. A leitura qualitativa se mantém: isso é um
sinal de alerta, não uma boa notícia sem ressalvas — a seção 5 do
notebook 02 já mostrou que municípios pequenos têm a métrica de
cobertura mais volátil (poucas doses mudam bastante o percentual), e a
seção 4 mostrou o efeito de fronteira inflando cobertura por atendimento
a não-residentes. A cobertura mais alta deste cluster provavelmente é,
em parte, esse duplo efeito — não necessariamente melhor acesso real à
vacinação. Tratar o Cluster 1 como "referência de boa cobertura" sem
essa ressalva seria uma leitura ingênua dos dados.

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
| **Random Forest** (melhor) | **55,14** | 0,026 | 64,46s |
| XGBoost | 55,19 | 0,024 | 15,99s |
| Ridge (linear) | 55,45 | 0,015 | 0,25s |

**Leitura:** o vencedor por RMSE trocou de novo nesta rodada — na
anterior (pós-fronteira/área) o XGBoost vencia por 54,04 contra 54,15 do
Random Forest, uma diferença de 0,11; nesta rodada é o Random Forest que
vence, por uma margem ainda menor (0,05, 55,14 vs. 55,19). Como essa
margem é menor que a da rodada anterior — já classificada como "dentro
do ruído" — a leitura honesta é que os dois modelos em árvore seguem
estatisticamente equivalentes entre si para essa métrica; o que se
mantém estável é a distância de ambos para o Ridge (linear), que segue
em último (55,45) nas duas rodadas. Por isso esta rodada **não** repete
a recomendação de "XGBoost como modelo principal" da versão anterior —
a decisão revisada, com a justificativa completa, está em
`docs/decisoes_modelagem.md`, seção 10.

No teste, o Random Forest chegou a RMSE = 15,99, MAE = 11,99 e
**R² = 0,111** — próximo do R² de teste do XGBoost na rodada anterior
(0,128), não uma melhora clara. Os dois resultados, tomados juntos,
sugerem que o teto de desempenho da regressão com o conjunto de features
atual está nessa faixa (R² ≈ 0,11-0,13), com o "vencedor" específico
variando mais por qual modelo e partição do que por um ganho real de um
modelo sobre o outro.

![Importância de features — Random Forest (regressão)](../reports/importancia_features_regressao.png)

**O que o gráfico mostra:** para o Random Forest, `log_densidade_hab_km2`
(área/SIDRA, ~0,25) lidera com folga, seguida por `log_populacao`
(~0,19), `log_pib_per_capita` (~0,18),
`log_estabelecimentos_saude_sus_por_100k_hab` (CNES, ~0,145) e
`pct_atendimento_agua` (SNIS, ~0,12); `bin_fronteira` (~0,04) e as
dummies de região (~0,01-0,03) ficam por último.

**Leitura:** este gráfico contradiz um achado da rodada anterior, e vale
registrar isso às claras em vez de simplesmente substituir o número. Na
rodada pós-fronteira/área (seção 3), sob o XGBoost (então vencedor da
regressão), `bin_fronteira` aparecia em 2º lugar de importância (~0,18) —
interpretado como "a fronteira pesa mais para prever a magnitude exata
da cobertura do que para separar categorias". Agora, sob o Random
Forest (novo vencedor da regressão), a importância de fronteira caiu
para ~0,04 — praticamente empatada com sua importância baixa na
classificação (seção 3). Ou seja: **esse achado não se confirmou como
uma propriedade estável dos dados** — parece ter sido, em boa parte, um
artefato de qual modelo venceu a regressão naquela rodada, não uma
diferença real entre prever categoria e prever magnitude. Análise
completa em `docs/decisoes_modelagem.md`, seção 11.

![Previsto vs. real e resíduos — Random Forest](../reports/regressao_previsto_vs_real.png)

**O que o gráfico mostra:** à esquerda, cobertura prevista vs. real no
teste — os pontos previstos ficam concentrados numa faixa relativamente
estreita (~75-100), enquanto a cobertura real varia muito mais (de perto
de 0 a ~190, com pelo menos um outlier isolado por volta de 150-160). À
direita, os resíduos (real − previsto) espalhados sem um padrão
sistemático óbvio em torno de zero.

**Leitura:** o modelo ainda erra bastante em valor absoluto e continua
"regredindo à média" — prevendo valores numa faixa estreita mesmo para
municípios com cobertura real muito alta ou muito baixa — o que é
esperado dado o R² de teste modesto (0,111). Os resíduos não mostram um
padrão sistemático (por exemplo, um funil ou uma curva), o que é uma
checagem de saúde importante: o modelo erra de forma consistente em
magnitude, não de um jeito que sugira uma variável relevante ficou de
fora de forma estruturada — a limitação segue sendo volume/variedade de
features (sete sinais, mesmo após a adição da água), não um bug ou uma
feature crítica ausente.

## 6. Síntese

Os seis gráficos deste documento contam a mesma história por ângulos
diferentes: o pipeline funciona, os modelos são honestos sobre suas
limitações, e nenhum sinal isolado "domina, de longe" — PIB per capita,
CNES e população lideram a importância na classificação, com água (SNIS)
entrando em 5º lugar apesar de correlação isolada quase nula; densidade,
população e PIB lideram na regressão. O achado metodológico mais
importante **desta** rodada não é de desempenho agregado (que melhorou
pouco: F1 de teste +0,015, ROC-AUC de teste +0,020) — é a confirmação de
que o "vencedor" entre Random Forest e XGBoost para a regressão não é
estável: XGBoost venceu na rodada anterior por uma margem de 0,11 de
RMSE (classificada como ruído), Random Forest venceu nesta por uma
margem ainda menor, 0,05. Isso levou a uma revisão explícita da seção 10
de `docs/decisoes_modelagem.md`: em vez de recomendar um algoritmo
específico para a regressão, a recomendação passou a ser "modelo em
árvore (Random Forest ou XGBoost, equivalentes), não o Ridge" — e o
achado da rodada anterior de que "fronteira pesa mais na regressão que
na classificação" não se confirmou como propriedade estável dos dados:
era, ao que tudo indica, um artefato de qual modelo venceu a regressão
naquela rodada específica. As decisões que vieram desses achados (alvo
binário por quartil, sete features, clusterização em 3 grupos, regressão
como complemento e a recomendação revisada de modelo) estão registradas
com a justificativa completa em
[`docs/decisoes_modelagem.md`](decisoes_modelagem.md), assim como as
limitações conhecidas e os próximos passos priorizados pela equipe.
