# Decisões de Modelagem (Etapa 3)

Registro das decisões técnicas e de negócio tomadas na construção dos
modelos de `notebooks/03_construcao_modelos.ipynb`, no mesmo espírito de
`docs/decisoes_limpeza.md` (Etapa 2): cada escolha existe para servir ao
objetivo do projeto — apoiar a priorização de campanhas de imunização
(`docs/entendimento_problema.md`) — e fica documentada com a justificativa,
não só a decisão em si, porque o material da disciplina cobra
explicitamente essa rastreabilidade ("cruzar" solução, objetivo e problema;
justificar algoritmo, split e métricas tanto técnica quanto comercialmente).

## Objetivo desta etapa e por que não é "previsão de futuro"

O README e `docs/entendimento_problema.md` (pergunta 5) descrevem o
objetivo original como prever risco de baixa cobertura **futura**/"no
próximo ciclo" — uma previsão temporal genuína, que exigiria treinar com
features de um ano para prever o resultado do ano seguinte. Só temos um
ano de dado processado (2025): PNI, IBGE e PIB não têm um segundo ano
passando pela pipeline. Um modelo treinado e avaliado inteiramente dentro
de 2025 não é, de fato, um modelo preditivo de futuro — é um modelo
transversal (cross-sectional).

| Decisão | Justificativa |
|---|---|
| Reformular o objetivo desta etapa para "classificar o perfil de risco atual dos municípios", em vez de "prever risco futuro" | Alegar previsão temporal sem um segundo ano de dados para validar seria uma afirmação que os dados não sustentam — o mesmo tipo de cuidado já aplicado na Etapa 2 ao não chamar a métrica de cobertura de "% de pessoas vacinadas" sem poder confirmar isso. A alternativa (buscar um segundo ano de PNI/IBGE/PIB antes de modelar) foi considerada e descartada por ora: exigiria reprocessar a Etapa 1/2 inteira para outro ano, ver "Limitações" abaixo. |

## 1. Construção do dataset de features

| Decisão | Justificativa |
|---|---|
| Features: `log_populacao`, `log_pib_per_capita`, `fronteira` (binária) e `regiao` (categórica, 5 valores) | Diretamente ligadas às hipóteses registradas ao final do notebook 02: população e PIB per capita já haviam sido exploradas por correlação com a cobertura (seções 5 e 6 do notebook 02); fronteira e região vêm do padrão geográfico de outliers encontrado na seção 3 (efeito "caravana da vacina" concentrado em municípios de fronteira, sobretudo Norte). |
| `fronteira` aproximada por UF (11 estados da faixa de fronteira, Lei 6.634/1979: AC, AP, AM, MT, MS, PA, PR, RS, RO, RR, SC), não pela lista oficial de municípios | Não existe, nesta pipeline, uma fonte de dado com a lista oficial de municípios que compõem a faixa de fronteira (~588 municípios). Aproximar por UF é impreciso (um estado inteiro "contamina" com o mesmo valor municípios que na prática estão longe da fronteira), mas dá ao modelo um sinal geográfico que, sem essa fonte adicional, seria custoso demais construir agora. Ver "Limitações". |
| `regiao` (5 categorias: Norte/Nordeste/Centro-Oeste/Sudeste/Sul) em vez da UF completa (27 categorias) como feature categórica | UF completa explodiria o número de colunas do one-hot encoding (usado pela Regressão Logística e pelo KNN) e fragmentaria demais o sinal para os ~5.570 municípios disponíveis. Região preserva o padrão geográfico relevante (a diferença Norte vs. resto do país, por exemplo) com uma cardinalidade bem menor. |
| `populacao` e `pib_per_capita_reais` transformadas em log (`log1p`) antes de entrar no modelo | As duas distribuições são fortemente assimétricas (seções 2 e 6 do notebook 02); log1p aproxima uma escala mais tratável, o que ajuda sobretudo modelos sensíveis à escala/distância das features (Regressão Logística, KNN). Árvores (Random Forest, XGBoost) não precisariam disso, mas usar o mesmo conjunto de features para os quatro modelos simplifica a comparação. |
| Descartar (não imputar) municípios sem PIB per capita, população ou cobertura | Mesmo critério já usado na Etapa 2 para população (`docs/decisoes_limpeza.md`, seção 1): essas três colunas são a base de tudo que vem depois; inventar um valor para o único município sem PIB (já identificado no notebook 02, seção 6) distorceria o dataset de modelagem sem necessidade — a perda é de 1 município em ~5.570. |

## 2. Definição do alvo (`baixa_cobertura`)

| Decisão | Justificativa |
|---|---|
| Alvo binário: `baixa_cobertura = 1` se a cobertura do município está abaixo do 1º quartil (25%) nacional | A métrica de cobertura (doses por 100 habitantes) tem outliers extremos (assimetria ~34, ver notebook 02 seção 2) e não é diretamente comparável a um padrão clínico fixo, como o limiar de ~95% de imunidade coletiva da OMS — usar um corte clínico alegaria uma calibração que os dados não sustentam. Um corte estatístico relativo (quartil) é mais defensável e não depende de nenhuma suposição sobre a escala absoluta da métrica. |
| Quartil calculado sobre a distribuição nacional completa (todos os municípios do dataset de modelagem), não por UF/região | O objetivo de negócio é priorização nacional de campanhas (`docs/entendimento_problema.md`); um corte por UF esconderia municípios que são "baixa cobertura" na escala do país mas médios dentro do seu estado. |
| Desbalanceamento (~25% positivos/75% negativos) tratado no treinamento (seção 3), não neutralizado na definição do alvo | Usar a mediana (corte 50/50) em vez do quartil eliminaria o desbalanceamento "de graça", mas mudaria o significado do alvo para algo bem mais frouxo que "baixa cobertura" (metade dos municípios do país não é, intuitivamente, uma minoria de risco). Preferimos manter o alvo fiel à ideia de "os piores 25%" e lidar com o desbalanceamento como o problema técnico que ele é. |

## 3. Divisão treino / validação / teste

| Decisão | Justificativa |
|---|---|
| Holdout de três vias: 70% treino / 15% validação / 15% teste, estratificado pelo alvo | Com ~5.500 municípios, o volume é grande o suficiente para um holdout de três vias em vez de depender só de k-fold. Estratificação (`stratify=y`) garante que os ~25% de `baixa_cobertura` fiquem representados na mesma proporção nos três conjuntos — sem isso, o desbalanceamento poderia deixar a validação ou o teste com uma proporção bem diferente só por acaso da amostragem, distorcendo qualquer métrica calculada ali. |
| Teste usado uma única vez, só depois de modelo e hiperparâmetros já escolhidos com treino + validação | Avaliar repetidamente no teste e ajustar decisões a partir disso vazaria informação do teste para o processo de escolha, inflando artificialmente a métrica final — exatamente o erro que a documentação explícita da estratégia de split busca prevenir. |
| 5-fold cross-validation dentro do conjunto de treino para o tuning de hiperparâmetros (`GridSearchCV`), em vez de usar só a validação simples | Com apenas ~3.900 municípios de treino, uma única divisão treino/validação para tuning teria uma variância maior (a "sorte" de quais municípios caem em cada fold afetaria mais o resultado); 5-fold reduz essa variância ao testar cada combinação de hiperparâmetros em 5 partições diferentes do treino antes de decidir. |

## 4. Escolha dos algoritmos (justificativa técnica e de negócio)

| Modelo | Justificativa técnica | Justificativa de negócio |
|---|---|---|
| **Regressão Logística** | Baseline linear, rápido de treinar, cada coeficiente é diretamente interpretável (efeito em log-odds de cada feature). Serve de referência: se um modelo mais complexo não superar isso por margem clara, a complexidade não se paga. | Um gestor de saúde pública consegue entender e questionar diretamente "por que este município foi marcado como risco" — importante quando o resultado embasa decisão sobre onde investir recursos escassos. |
| **KNN** | Não-paramétrico, decide pela vizinhança nas features (após padronização); simples de implementar, mas sensível ao hiperparâmetro *k* e à maldição da dimensionalidade. | Modelo do "cardápio" da disciplina incluído para comparação; sem uma vantagem de negócio específica sobre os demais — serve principalmente como contraponto de comparação e para explicitar o trade-off de explicabilidade (ver seção 8 do notebook). |
| **Random Forest** | Ensemble de árvores, mais robusto a relações não-lineares e a outliers do que a Regressão Logística (relevante dado o quão extrema é a distribuição de cobertura); importância de features nativa. | Ainda dá para explicar uma decisão em termos de "quais fatores pesaram mais" (importância de features), mesmo sem o detalhe de coeficiente por variável da Regressão Logística. |
| **XGBoost** | Gradient boosting, tipicamente o mais forte dos quatro em dados tabulares como este. Maior custo computacional de treinamento/tuning e interpretabilidade mais indireta que Random Forest — os pontos de atenção que o material da disciplina associa a esse tipo de modelo. | Só vale o custo computacional extra se o ganho de desempenho sobre os modelos mais simples for relevante (ver a leitura automática da matriz de comparação, seção 4 do notebook) — do contrário, um modelo mais simples e mais barato de manter é a escolha de negócio mais defensável. |

## 5. Tratamento do desbalanceamento de classes

| Decisão | Justificativa |
|---|---|
| `class_weight="balanced"` (Regressão Logística, KNN via ponderação não aplicável — ver nota, Random Forest) e `scale_pos_weight` equivalente (XGBoost), em vez de reamostragem (undersampling/SMOTE) | Como `baixa_cobertura` é ~25% por construção (seção 2), um modelo ingênuo que sempre prevê "não é baixa cobertura" teria ~75% de acurácia e zero utilidade prática. Ponderar a classe minoritária no próprio treinamento é a abordagem mais simples e não exige criar municípios sintéticos (reamostragem) nem descartar dados reais (undersampling); listada como possível melhoria futura. |
| Métrica de seleção de modelo e de tuning é F1 (não acurácia) | Acurácia é enganosa sob desbalanceamento (ver acima); F1 pondera precisão e recall, os dois lados do erro que importam aqui: falso positivo (gastar recurso de campanha num município que não precisava) e falso negativo (deixar de priorizar um município que precisava). |

## 6. Métricas de avaliação

| Decisão | Justificativa |
|---|---|
| Accuracy, precision, recall, F1 e ROC-AUC reportados lado a lado na matriz de comparação (não só F1) | O material da disciplina lista esse conjunto como o padrão para problemas de classificação; reportar todas dá visibilidade sobre trade-offs que F1 sozinho esconde (ex.: um modelo pode ter F1 parecido com outro mas com precision/recall bem diferentes). |
| Silhouette score (não só inércia/método do cotovelo) para escolher o número de clusters do K-Means | O método do cotovelo é uma inspeção visual sujeita a interpretação subjetiva de onde fica o "cotovelo"; o silhouette score dá um critério numérico objetivo (quão bem cada ponto se encaixa no seu cluster vs. nos vizinhos) para desempatar entre valores de k próximos. |

## Limitações conhecidas / próximos passos

- **Escopo transversal, não temporal**: falta um segundo ano de dados
  (PNI, IBGE e PIB) processados pela pipeline para treinar em ano N e
  validar em N+1 — a versão mais fiel ao objetivo original do projeto.
  Rodar `download_pni`/`clean_pni` etc. para outro ano (ex.: 2024) é o
  caminho natural, mas fica fora do escopo desta entrega pelo tempo que
  levaria reprocessar Etapa 1/2 inteira para um segundo ano.
- **Fronteira aproximada por UF**: a lista oficial de municípios da faixa
  de fronteira (Lei 6.634/1979) daria um sinal geográfico bem mais preciso
  que o estado inteiro; não incorporada por falta de uma fonte de dado
  pronta para essa lista nesta pipeline.
- **Desbalanceamento tratado só por peso de classe**: técnicas de
  reamostragem (ex.: SMOTE) são uma melhoria possível, a testar com
  cautela para não gerar municípios sintéticos pouco realistas.
- **Poucas features**: só três variáveis numéricas de fato (população,
  PIB per capita, fronteira) além da região. A sazonalidade mensal
  identificada no notebook 02 (seção 7) não entrou como feature porque o
  dataset `refined` usado aqui é anual — incorporar o mês exigiria
  remodelar o `refined` para preservar granularidade mensal por município
  (ver `docs/decisoes_limpeza.md`, seção 2).
- **Custo computacional**: Random Forest foi o modelo mais lento para
  ajustar na grade de hiperparâmetros usada; em um cenário com mais dados
  (ex.: granularidade mensal), o custo de re-treinar os quatro modelos
  cresceria de forma não-trivial — um ponto de atenção explícito do
  material da disciplina.
