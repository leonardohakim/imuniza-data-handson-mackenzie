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
| Features originais: `log_populacao`, `log_pib_per_capita`, `fronteira` (binária) e `regiao` (categórica, 5 valores) | Diretamente ligadas às hipóteses registradas ao final do notebook 02: população e PIB per capita já haviam sido exploradas por correlação com a cobertura (seções 5 e 6 do notebook 02); fronteira e região vêm do padrão geográfico de outliers encontrado na seção 3 (efeito "caravana da vacina" concentrado em municípios de fronteira, sobretudo Norte). |
| `fronteira` aproximada por UF (11 estados da faixa de fronteira, Lei 6.634/1979: AC, AP, AM, MT, MS, PA, PR, RS, RO, RR, SC), não pela lista oficial de municípios | Não existe, nesta pipeline, uma fonte de dado com a lista oficial de municípios que compõem a faixa de fronteira (~588 municípios). Aproximar por UF é impreciso (um estado inteiro "contamina" com o mesmo valor municípios que na prática estão longe da fronteira), mas dá ao modelo um sinal geográfico que, sem essa fonte adicional, seria custoso demais construir agora. Ver "Limitações". |
| `regiao` (5 categorias: Norte/Nordeste/Centro-Oeste/Sudeste/Sul) em vez da UF completa (27 categorias) como feature categórica | UF completa explodiria o número de colunas do one-hot encoding (usado pela Regressão Logística e pelo KNN) e fragmentaria demais o sinal para os ~5.570 municípios disponíveis. Região preserva o padrão geográfico relevante (a diferença Norte vs. resto do país, por exemplo) com uma cardinalidade bem menor. |
| `populacao` e `pib_per_capita_reais` transformadas em log (`log1p`) antes de entrar no modelo | As duas distribuições são fortemente assimétricas (seções 2 e 6 do notebook 02); log1p aproxima uma escala mais tratável, o que ajuda sobretudo modelos sensíveis à escala/distância das features (Regressão Logística, KNN). Árvores (Random Forest, XGBoost) não precisariam disso, mas usar o mesmo conjunto de features para os quatro modelos simplifica a comparação. |
| Descartar (não imputar) municípios sem PIB per capita, população ou cobertura | Mesmo critério já usado na Etapa 2 para população (`docs/decisoes_limpeza.md`, seção 1): essas três colunas são a base de tudo que vem depois; inventar um valor para o único município sem PIB (já identificado no notebook 02, seção 6) distorceria o dataset de modelagem sem necessidade — a perda é de 1 município em ~5.570. |
| Feature nova: `log_estabelecimentos_saude_sus_por_100k_hab` (CNES, normalizado por população, não a contagem bruta) | Hipótese: acesso a infraestrutura de saúde facilita a vacinação — mesma linha de raciocínio já usada para `fronteira` (sinal geográfico de acesso). Normalizar por população (por 100 mil habitantes) evita que a feature vire um proxy quase redundante de `log_populacao` (a contagem bruta de estabelecimentos é dominada pelo tamanho do município — ver `docs/decisoes_limpeza.md`, seção 11). Usa só o subconjunto com atendimento ambulatorial SUS (`qtd_estabelecimentos_saude_sus`), não o total bruto do cadastro (que inclui estabelecimentos sem relação com vacinação, como consultórios particulares e laboratórios). |
| `qtd_estabelecimentos_saude_sus` adicionada a `colunas_obrigatorias` (município sem ela é descartado, não imputado) | Mesmo critério das demais colunas obrigatórias (acima). Na prática não descarta nenhum município hoje (CNES tem cobertura completa dos ~5.571 municípios do refinado), mas protege contra uma cobertura futura parcial do CNES sem precisar de uma decisão nova. |
| Feature condicional: `log_densidade_hab_km2` (IBGE/SIDRA) — só entra no conjunto de features se a coluna `densidade_hab_km2` já existir no `refined` | Diferente do CNES, a área territorial (fonte SIDRA) enfrentou bloqueio de rede (WAF) no ambiente usado nesta sessão, então nem sempre está disponível no momento de rodar o notebook. Uma checagem condicional (`if "densidade_hab_km2" in modelagem.columns`) deixa o notebook robusto a essa ausência temporária — roda normalmente sem a feature, e passa a incluí-la automaticamente assim que `clean_area.py`/`build_coverage.py` tiverem rodado, sem precisar editar o notebook de novo. |
| `FEATURES_ESCALAR` (lista de features que passam por `StandardScaler`) construída dinamicamente a partir de `FEATURES_NUMERICAS`, em vez de hardcoded na célula do `ColumnTransformer` | Antes da adição do CNES/área, a lista de colunas do `StandardScaler` era hardcoded (`["log_populacao", "log_pib_per_capita"]`) separadamente da lista `FEATURES_NUMERICAS` usada para montar `X` — um risco real de bug silencioso: `ColumnTransformer` descarta silenciosamente (não levanta erro) qualquer coluna de `X` que não apareça em nenhum transformador, então uma feature nova adicionada a `FEATURES_NUMERICAS` sem atualizar essa lista separada simplesmente seria ignorada pelo modelo, sem aviso nenhum. Tornar a lista dinâmica (`[f for f in FEATURES_NUMERICAS if f != "fronteira"]`) elimina essa classe de bug — vale tanto para a classificação (seção 3) quanto para a regressão (seção 7), que reaproveita a mesma lista. |
| Correlação de cada feature nova com a cobertura impressa na própria célula de construção, antes de decidir usá-la | Diferente das quatro features originais (validadas por exploração prévia no notebook 02, seções 3/5/6), CNES e área foram adicionadas depois, sem uma etapa própria de análise exploratória. Imprimir a correlação na hora da construção mantém alguma visibilidade sobre a força do sinal de cada feature nova antes dela entrar no modelo, mesmo sem repetir todo o processo de exploração do notebook 02. |

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

## 7. Enquadramento complementar: regressão da cobertura contínua

| Decisão | Justificativa |
|---|---|
| Adicionar um enquadramento de regressão (alvo `cobertura_doses_por_100_habitantes`, contínuo) como complementar à classificação — não como substituto | O alvo binário (`baixa_cobertura`, seção 2) descarta informação por construção: dois municípios abaixo do 1º quartil, um "levemente" e outro extremamente abaixo, recebem o mesmo rótulo. Um score contínuo permite **rankear** municípios por urgência dentro do próprio grupo de risco — relevante porque o orçamento de uma campanha de imunização raramente cobre todos os municípios "baixa cobertura" ao mesmo tempo. A classificação binária continua sendo a entrega principal (mais simples de comunicar a um gestor de saúde pública: "está ou não no grupo prioritário"); a regressão serve para desempatar a ordem dentro dessa lista. |
| Reaproveitar a mesma divisão treino/validação/teste da classificação (mesmos municípios em cada conjunto), em vez de um novo `train_test_split` | Evita introduzir uma segunda fonte de aleatoriedade e mantém as duas abordagens diretamente comparáveis — a diferença de resultado entre classificação e regressão passa a ser só o formato do alvo, não também uma amostragem diferente. Estratificação por `y` (usada no split original) não se aplica a um alvo contínuo, então reaproveitar o split da classificação também evita a pergunta de "como estratificar regressão". |
| Três modelos (Ridge, Random Forest, XGBoost), sem o KNN | Mesmo critério já registrado na seção 4 para a classificação: o KNN entrou no "cardápio" da disciplina para comparação, mas sem vantagem de negócio específica sobre os demais. Ridge substitui a Regressão Logística como baseline linear interpretável (é o equivalente de regressão da mesma ideia — regularização L2, coeficiente por feature); Random Forest e XGBoost mantidos pelos mesmos motivos técnicos e de negócio já documentados. |
| Métrica de seleção é RMSE (não R²) | RMSE fica na mesma unidade do alvo (doses por 100 habitantes), o que facilita julgar se o erro típico é aceitável para priorização olhando a escala real da métrica; R² é reportado ao lado como referência de quanto da variância o modelo explica em relação à média, mas não é o critério de desempate entre modelos. |
| Nenhuma expectativa de melhoria de R²/poder preditivo só por trocar classificação por regressão — registrado antes de rodar com dados reais | A limitação de fundo já documentada (seção "Limitações", abaixo) é a pobreza de features (só população, PIB per capita e um sinal geográfico aproximado), não o formato do alvo. Trocar o enquadramento não resolve a causa raiz do desempenho fraco já visto na classificação (F1 ≈ 0,39, ROC-AUC ≈ 0,58 no teste) — o valor esperado aqui é uma ferramenta de priorização mais granular, não uma correção de desempenho. Evita o risco de reportar o resultado da regressão como se fosse uma "melhoria" quando na verdade é só uma mudança de pergunta. |

## 8. Resultados observados contra dados reais (checagem pós-CNES)

A seção 7 registrou, antes de rodar contra dados reais, que não se esperava
ganho de R²/poder preditivo só por integrar o CNES ou reformular o alvo como
regressão — a causa raiz seria a pobreza de features, não o formato do alvo
ou a ausência dessa fonte específica. Esta seção fecha esse ciclo: registra
o que de fato aconteceu depois que `download_cnes`/`clean_cnes`/
`build_coverage` rodaram contra dado real e o notebook foi reexecutado
ponta a ponta com a feature `log_estabelecimentos_saude_sus_por_100k_hab`
incorporada.

**Classificação — comparação antes/depois do CNES (mesmo split, mesma
metodologia de tuning):**

| Métrica | Antes (sem CNES) | Depois (com CNES) |
|---|---|---|
| F1 validação (melhor modelo, Random Forest) | 0,452 | 0,418 |
| F1 teste | 0,390 | 0,391 |
| ROC-AUC teste | 0,582 | 0,591 |

Variação desprezível nos dois sentidos — confirma a expectativa registrada
na seção 7: o CNES não resolveu (nem piorou de forma relevante) o
desempenho agregado de classificação.

| Achado | Leitura / decisão |
|---|---|
| `log_estabelecimentos_saude_sus_por_100k_hab` (CNES) tem correlação de Pearson fraca com a cobertura (0,089, impressa na célula de construção do dataset — ver seção 1), mas aparece como a **2ª feature mais importante** no Random Forest da classificação (~0,23, atrás só de `log_pib_per_capita` e à frente de `log_populacao`) | Não é contraditório: correlação de Pearson mede só relação linear univariada; a importância de features de uma árvore captura interações não-lineares que a correlação simples não enxerga. Interpretação registrada: o CNES carrega sinal real e relevante em combinação com as outras features, mesmo sem mover o F1/ROC-AUC agregado — reforça a leitura já dada na seção 7 de que o valor do enriquecimento de features aparece mais como ferramenta de priorização/explicação do que como ganho de métrica agregada. Mantido no conjunto de features; nenhuma ação adicional necessária. |
| Na regressão, o RMSE de validação do melhor modelo (Ridge, 54,66) ficou bem mais alto que o RMSE de teste do mesmo modelo (15,81) — a princípio parece inconsistente | Investigado e explicado, não é bug: o split treino/validação/teste (seção 3) é estratificado pelo alvo **binário** da classificação (`baixa_cobertura`), não pelo alvo contínuo da regressão. `cobertura_doses_por_100_habitantes` tem cauda pesada (municípios pequenos chegam a >150-190 doses/100 hab., efeito de volatilidade já registrado no notebook 02 e na seção de clusterização do notebook 03); por acaso da amostragem, a partição de validação concentrou mais desses outliers extremos que a de teste, inflando o RMSE ali sem que haja nada de errado no código (mesma métrica, mesma função, aplicada igual nos dois conjuntos — conferido também visualmente no gráfico previsto-vs-real do teste, `reports/regressao_previsto_vs_real.png`). Registrado aqui como limitação conhecida do enquadramento de regressão (ver também "Limitações" abaixo), não corrigido nesta entrega — corrigir exigiria estratificar (ou ao menos balancear) o split também pela distribuição do alvo contínuo, o que voltaria a acoplar os dois enquadramentos e contraria a decisão da seção 7 de mantê-los comparáveis via o mesmo split simples. |

**Conclusão prática registrada**: o CNES entregou exatamente o que a seção 7
previa — não é um "fix" de desempenho, mas comprova sinal real (2º lugar em
importância) e serve como ferramenta de priorização mais granular. Dado o
retorno decrescente de continuar só enriquecendo features estáticas, a
prioridade natural do próximo ciclo de trabalho passa a ser a modelagem
temporal com um segundo ano de dados (2024) — mais alinhada ao objetivo
original do projeto (ver "Objetivo desta etapa" acima) do que mais uma
feature transversal.

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
- **Poucas features, mesmo após o enriquecimento**: população, PIB per
  capita, fronteira, região e agora CNES (seção 8) — cinco sinais no total,
  o que ainda é pouco para um F1/ROC-AUC fortes. O CNES ajudou como sinal
  de importância (seção 8), mas não resolveu a causa raiz. A sazonalidade
  mensal identificada no notebook 02 (seção 7) não entrou como feature
  porque o dataset `refined` usado aqui é anual — incorporar o mês exigiria
  remodelar o `refined` para preservar granularidade mensal por município
  (ver `docs/decisoes_limpeza.md`, seção 2). Área/densidade (SIDRA) segue
  como feature condicional (seção 1) até o bloqueio de rede daquela fonte
  ser contornado.
- **RMSE da regressão sensível a qual partição concentra os outliers de
  cobertura**: como o split é estratificado só pelo alvo binário, não pelo
  alvo contínuo (seção 8), o RMSE de validação e de teste pode divergir
  bastante entre si mesmo para o mesmo modelo, dependendo de quantos
  municípios de cobertura extrema caem em cada partição por acaso da
  amostragem — observado na prática (seção 8). Não corrigido nesta entrega.
- **Custo computacional**: Random Forest foi o modelo mais lento para
  ajustar na grade de hiperparâmetros usada; em um cenário com mais dados
  (ex.: granularidade mensal), o custo de re-treinar os quatro modelos
  cresceria de forma não-trivial — um ponto de atenção explícito do
  material da disciplina.
