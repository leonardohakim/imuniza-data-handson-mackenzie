# Decisões de Limpeza e Pré-Processamento (Etapa 2)

Registro das decisões tomadas na limpeza (raw → trusted → refined), com a
justificativa de cada uma:

## 1. Dados de população (IBGE)

| Decisão | Justificativa |
|---|---|
| Remover a linha de metadados/rótulos que a API SIDRA inclui como primeira linha do CSV bruto | A API retorna por padrão (`/h/y`) uma linha com descrições dos campos (ex.: `V = "Valor"`) antes dos dados reais; sem removê-la, ela seria lida como um "município" com população não numérica, quebrando o cálculo de cobertura. Identificada comparando o raw com a documentação da API SIDRA. |
| Descartar (não imputar) municípios com população ausente/sigilosa (marcadores como `-`) | População é o denominador da métrica de cobertura vacinal. Uma imputação (média, mediana etc.) inventaria um denominador que não existe e distorceria diretamente o resultado; preferimos excluir o município da análise a apresentar um número fabricado. |
| Descartar códigos de município que não têm exatamente 7 dígitos numéricos | Padrão IBGE é sempre 7 dígitos; qualquer coisa fora disso indica erro de fonte e impediria o `join` com os dados do PNI. |
| Remover duplicatas por código de município (mantendo a primeira ocorrência) | A API não deveria retornar o mesmo município duas vezes para o mesmo ano; quando ocorre, é tratado como erro de coleta, não como dois registros válidos. |

## 2. Dados de doses aplicadas (PNI)

| Decisão | Justificativa |
|---|---|
| Processar cada arquivo mensal em streaming (blocos/chunks), nunca carregando o ZIP nem o CSV inteiros em memória | Os arquivos do PNI são nacionais e grandes (abril/2025 tem ~4GB comprimido; descompactado passa de 15-20GB): isso não cabe na RAM disponível (confirmado na prática: o processo foi encerrado por falta de memória ao tentar carregar o arquivo inteiro). A solução foi ler o objeto do MinIO em blocos, descompactar o ZIP também em streaming (biblioteca `stream-unzip`, que não precisa acessar o fim do arquivo como o `zipfile` padrão) e processar o CSV em pedaços de 100 mil linhas por vez, agregando cada pedaço antes de descartá-lo. |
| Baixar, limpar e descartar cada mês individualmente (nunca manter os 12 ZIPs brutos no MinIO ao mesmo tempo), em vez de baixar o ano inteiro para `raw` antes de limpar | Tentativa inicial: baixar os 12 meses nacionais completos de 2025 para o bucket `raw` (cada mês entre 1,4GB e 5GB) esgotou o disco do ambiente (32GB) bem antes do fim do ano: só deu para baixar 7 meses (jan-jun + ago), e mesmo esses ficaram ocupando ~18,5GB desnecessariamente depois de já limpos. Solução: `reprocessar_pni_2025.py` baixa cada mês para um arquivo temporário local (fora do volume do MinIO), limpa direto dali, envia só o parquet (pequeno) para `trusted`, e apaga o temporário antes do próximo mês, nunca mais que ~5GB em disco por vez. Isso permitiu processar o **ano completo de 2025 (12 meses)**, não só os 7 que cabiam com a abordagem anterior. Essa é a mesma restrição de escopo que o commit original da Etapa 1 já pretendia resolver filtrando por região (Sudeste); preferimos resolver o problema de disco em vez de reduzir a abrangência geográfica, então o dataset final é nacional e com o ano completo. |
| Resolver nomes de coluna dinamicamente (por lista de candidatos), em vez de fixar nomes | Não tínhamos os dados reais em mãos para confirmar o schema exato ao escrever o pipeline (ver `inspect_pni.py` da Etapa 1, criado exatamente por essa incerteza). Fixar nomes errados quebraria o pipeline silenciosamente ou praticamente às cegas; o resolver falha de forma explícita e lista as colunas disponíveis quando não encontra um candidato. **Confirmado contra os dados reais** (rodando `clean_pni.py` no Codespace): o schema real usa `dt_vacina` (data), `sg_imunobiologico` (nome/sigla da vacina), `co_dose_vacina`/`ds_tipo_dose` (dose) e `co_municipio_paciente`/`co_municipio_estabelecimento` (município): nenhum dos nomes hipotéticos originais batia exatamente; `COLUMN_CANDIDATES` foi atualizado com os nomes reais como primeira opção, mantendo os antigos como fallback. |
| Usar `co_municipio_paciente` (residência do paciente), não `co_municipio_estabelecimento` (onde a dose foi aplicada), como código de município | A população do IBGE (denominador da cobertura) é contada por residência. Se o numerador (doses) usasse o município do estabelecimento, cidades-polo com grandes hospitais/UBS que atendem pacientes de fora inflariam artificialmente sua cobertura, e os municípios vizinhos que enviam pacientes para lá apareceriam com cobertura subestimada: o oposto do que os dois realmente têm. |
| Descartar linhas sem código de município válido (6 dígitos, não 7) | **Bug real encontrado ao rodar contra os dados reais**: `co_municipio_paciente` traz o código de município do DATASUS/SUS, que tem 6 dígitos (o 7º dígito do código IBGE é só um dígito verificador, que o DATASUS não usa). A primeira versão do pipeline validava/preenchia como se fosse o código IBGE de 7 dígitos, o que produzia códigos de aparência válida (ex.: `0110001`) que na verdade nunca existiam no IBGE: o cruzamento com a população saía 100% sem correspondência (todo o dataset refinado aparecia com 0 doses, mesmo já tendo processado mais de 1,1 milhão de linhas de doses). Corrigido validando 6 dígitos aqui e truncando o código IBGE (7 dígitos) para 6 na hora do cruzamento em `build_coverage.py`, sem perda de informação, já que o 7º dígito do IBGE não identifica nada além do que os 6 primeiros já identificam. |
| Descartar linhas sem data de aplicação válida | A agregação é por mês; uma linha sem data não pode ser alocada a um período. |
| Detectar o formato da data por amostra (`%Y-%m-%d` vs `%d/%m/%Y` etc.) em vez de usar heurística `dayfirst` | `dayfirst=True/False` do pandas resolve a ambiguidade só parcialmente e pode inverter dia e mês silenciosamente quando o formato real do dado é o oposto do assumido; isso foi detectado durante o desenvolvimento (teste com datas ISO `2025-01-05` sendo lidas como 1º de maio). Testar qual formato explícito casa com mais valores da amostra evita esse erro silencioso. |
| Remover duplicatas exatas (linha inteira repetida), mas só dentro do mesmo bloco de streaming (chunk de 100 mil linhas) | Indicam erro de extração/join na fonte (mesmo registro exportado duas vezes), não doses reais adicionais; mantê-las infla artificialmente a contagem de doses. Limitação aceita: como o arquivo é processado em streaming (ver decisão acima), uma duplicata cujas duas ocorrências caiam em blocos diferentes não é detectada. Trade-off necessário para processar arquivos maiores que a RAM disponível; duplicatas exatas tendem a ser raras e, quando ocorrem, tendem a estar próximas no arquivo de origem. |
| Agregar para `município × mês (× vacina)` já na limpeza, em vez de manter uma linha por dose | Reduz drasticamente o volume de dados (o objetivo do projeto é município, não paciente individual) e evita manter dado de nível de paciente além do necessário. |
| Sinalizar município-mês fora de `[Q1 − 3·IQR, Q3 + 3·IQR]` como outlier, **sem remover** | Um valor muito alto pode ser um polo regional de vacinação (município que atende vizinhos), informação relevante para o objetivo do projeto (priorizar ações), não ruído a descartar. A decisão de remover ou não fica para a análise exploratória, com a coluna `outlier_iqr` disponível para essa investigação. |

## 3. PIB municipal (IBGE): variável socioeconômica

| Decisão | Justificativa |
|---|---|
| Usar PIB per capita municipal como variável socioeconômica, em vez de renda ou IDH | Renda per capita: os dados mais recentes que o IBGE divulga por essa métrica (PNAD Contínua) só descem a nível de Brasil/UF, não de município, então não dá para cruzar com a cobertura por município. IDH municipal (IDHM): só existe calculado para 2010 (Atlas do Desenvolvimento Humano/PNUD, plataforma diferente do IBGE/SIDRA, sem atualização com o Censo 2022); cruzar cobertura de 2025 com um indicador de 15 anos atrás foi considerado defasado demais. PIB per capita municipal (Tabela 5938 do SIDRA) é oficial, municipal, e tem série anual até 2023: o mais atual dos três disponível hoje. |
| Escolher a Tabela 5938 do SIDRA, não a 6784 | A 6784 parecia ser "PIB dos Municípios" pelo nome, mas a API rejeita consulta por município nela (`Parâmetro N6 (Nível territorial) incompatível com a tabela`): ela só existe a nível Brasil. Confirmado consultando `/metadados` das duas tabelas antes de escrever qualquer código de ingestão, mesmo princípio de "inspecionar antes de assumir" já usado no PNI (`inspect_pni.py`). |
| Calcular PIB per capita manualmente (`pib_mil_reais * 1000 / populacao`), em vez de usar uma variável "per capita" pronta | A Tabela 5938 só tem PIB total (variável 37, em Mil Reais) a nível de município; as variáveis "per capita" prontas do SIDRA existem só a outros níveis territoriais. Como já temos a população (IBGE, mesma fonte) coletada, calcular o per capita nós mesmos evita depender de mais uma tabela e mantém o numerador/denominador com a mesma origem de dado. |
| Cruzar PIB e população/cobertura direto pelo código de 7 dígitos, sem a conversão de 6/7 dígitos que o PNI exige | O PIB vem do próprio IBGE (Tabela 5938), mesmo sistema de código da população; não é o código DATASUS de 6 dígitos do PNI. Aplicar a conversão aqui seria um erro (e um bug bem parecido com o que já corrigimos na seção 2, mas ao contrário: truncar um código que já está certo). |
| Usar o ano de PIB mais recente disponível (2023) para cruzar com a cobertura de 2025, em vez de exigir o mesmo ano | Dado de PIB municipal sempre sai com atraso (a série do IBGE vai só até 2023, não existe "PIB de 2025" publicado); exigir o mesmo ano deixaria essa variável sempre vazia. `build_coverage.py` recebe o ano do PIB como parâmetro separado (`--ano-pib`, default 2023) do ano da cobertura (`--ano`). Essa defasagem de ~2 anos entre as duas fontes deve ficar explícita em qualquer gráfico/relatório que use `pib_per_capita_reais`. |
| Município sem PIB no trusted fica com `NaN`, não `0`, no dataset refinado | Diferente da decisão equivalente para `doses_aplicadas` (onde `0` é um sinal real: "nenhuma dose registrada"), a ausência de PIB é lacuna de dado (ex.: município sem registro naquele ano da série), não uma economia zerada; preencher com `0` fabricaria um valor incorreto para qualquer análise de correlação feita com essa coluna. |
| `build_coverage.py` prossegue sem a coluna de PIB (em vez de falhar) quando o trusted de PIB ainda não foi processado | PIB é uma variável adicional, não uma dependência obrigatória da métrica central do projeto (cobertura vacinal). Uma equipe rodando só `clean_ibge.py` + `clean_pni.py` (sem `clean_pib.py`) ainda consegue gerar o dataset refinado principal; a coluna de PIB só aparece quando `clean_pib.py` já rodou para o `--ano-pib` pedido. |

## 4. Métrica de cobertura vacinal (refined)

| Decisão | Justificativa |
|---|---|
| Métrica é "doses aplicadas por 100 habitantes", não "% de pessoas vacinadas" | O dataset agregado não separa por dose (1ª, 2ª, reforço) de forma confiável em todos os casos, então uma pessoa com 2 doses conta 2x no numerador. Chamar isso de "cobertura populacional" seria impreciso; documentamos a métrica como um proxy de intensidade de vacinação. Reavaliar na Etapa 3 se for possível filtrar por "1ª dose"/dose única. |
| Manter municípios com população no IBGE mas 0 doses no PNI (em vez de excluir) | "Sem dado de vacinação" é, em si, um sinal relevante para o objetivo do projeto (identificar áreas de baixa cobertura para priorizar ações): excluir esses municípios esconderia exatamente o que o projeto quer encontrar. Com o ano completo de 2025 processado, isso passou a ser só uma salvaguarda teórica: nenhum dos 5.571 municípios ficou com 0 doses no resultado final. |
| Cruzar população (IBGE, 7 dígitos) e doses (DATASUS, 6 dígitos) truncando o código IBGE para 6 dígitos, em vez de comparar direto | Os dois sistemas de código não são o mesmo (ver decisão equivalente na seção 2). O código de município final na camada refined continua sendo o de 7 dígitos do IBGE (mantido por ser o identificador padrão e mais reconhecível); os 6 dígitos são usados só como chave de cruzamento, descartada depois do merge. |

## Pendências conhecidas / próximos passos

- ~~Faltam jul, set, out, nov e dez/2025~~ (**resolvido**): com
  `reprocessar_pni_2025.py` (baixa/limpa/descarta um mês por vez, sem
  guardar os ZIPs brutos no MinIO) processamos o ano completo de 2025 (12
  meses, 2.031.418 linhas agregadas, 175,9 milhões de doses). Os ZIPs
  brutos não ficam armazenados em `raw`: podem ser rebaixados a qualquer
  momento do OpenDataSUS com `python -m src.ingestion.download_pni --ano
  2025` (por mês, um de cada vez, é o que esse script já faz).
- ~~As fontes de renda/IDH (IBGE/SIDRA) citadas no README como variável
  socioeconômica ainda não têm um script de ingestão~~ (**resolvido, com
  variável ajustada**): renda per capita (PNAD Contínua) só existe a nível
  Brasil/UF, e IDH municipal só existe defasado (2010, plataforma diferente
  do IBGE/SIDRA), então nenhum dos dois serve para cruzar com cobertura por
  município em 2025. Coletamos **PIB per capita municipal** (Tabela 5938 do
  SIDRA, ano de referência 2023) como variável socioeconômica no lugar
  (`download_pib.py` + `clean_pib.py`); ver seção 3 acima para a
  justificativa completa dessa troca.
- Este documento e `docs/dicionario_dados.md` foram inicialmente escritos
  sem acesso aos dados reais do PNI (rede bloqueada no ambiente usado para
  desenvolver o pipeline). Já validamos o schema real rodando `clean_pni.py`
  contra os dados baixados no Codespace e ajustamos `COLUMN_CANDIDATES`
  (ver decisão acima); falta ainda atualizar `docs/dicionario_dados.md` com
  os nomes de coluna reais do PNI (hoje ele documenta só os nomes
  hipotéticos originais).
