# Decisões de Limpeza e Pré-Processamento — Etapa 2

Registro das decisões tomadas na limpeza (raw → trusted → refined), com a
justificativa de cada uma — pedido explícito do professor no material da
disciplina ("cada decisão deve ser documentada e justificada, ajudará na
reprodutibilidade e na rastreabilidade").

## 1. Dados de população (IBGE)

| Decisão | Justificativa |
|---|---|
| Remover a linha de metadados/rótulos que a API SIDRA inclui como primeira linha do CSV bruto | A API retorna por padrão (`/h/y`) uma linha com descrições dos campos (ex.: `V = "Valor"`) antes dos dados reais; sem removê-la, ela seria lida como um "município" com população não numérica, quebrando o cálculo de cobertura. Identificada comparando o raw com a documentação da API SIDRA. |
| Descartar (não imputar) municípios com população ausente/sigilosa (marcadores como `-`) | População é o denominador da métrica de cobertura vacinal. Uma imputação (média, mediana etc.) inventaria um denominador que não existe e distorceria diretamente o resultado — preferimos excluir o município da análise a apresentar um número fabricado. |
| Descartar códigos de município que não têm exatamente 7 dígitos numéricos | Padrão IBGE é sempre 7 dígitos; qualquer coisa fora disso indica erro de fonte e impediria o `join` com os dados do PNI. |
| Remover duplicatas por código de município (mantendo a primeira ocorrência) | A API não deveria retornar o mesmo município duas vezes para o mesmo ano; quando ocorre, é tratado como erro de coleta, não como dois registros válidos. |

## 2. Dados de doses aplicadas (PNI)

| Decisão | Justificativa |
|---|---|
| Processar cada arquivo mensal em streaming (blocos/chunks), nunca carregando o ZIP nem o CSV inteiros em memória | Os arquivos do PNI são nacionais e grandes (abril/2025 tem ~4GB comprimido; descompactado passa de 15-20GB) — isso não cabe na RAM disponível (confirmado na prática: o processo foi encerrado por falta de memória ao tentar carregar o arquivo inteiro). A solução foi ler o objeto do MinIO em blocos, descompactar o ZIP também em streaming (biblioteca `stream-unzip`, que não precisa acessar o fim do arquivo como o `zipfile` padrão) e processar o CSV em pedaços de 100 mil linhas por vez, agregando cada pedaço antes de descartá-lo. |
| Restringir o escopo a 2025 e aos meses que couberam no disco do ambiente (jan-jun + ago), documentando os meses ausentes | O disco disponível no ambiente de desenvolvimento (32GB) esgotou ao tentar baixar os 12 meses nacionais completos de 2025 (cada mês entre 1,4GB e 5GB). Essa é a mesma restrição de escopo que o commit original da Etapa 1 já pretendia resolver (região Sudeste) mas não chegou a implementar no código. Dado o prazo da entrega, optamos por manter o dado nacional (mais representativo) e reduzir o número de meses, em vez de filtrar por região — jul, set, out, nov e dez/2025 ficam de fora desta rodada. |
| Resolver nomes de coluna dinamicamente (por lista de candidatos), em vez de fixar nomes | Não tínhamos os dados reais em mãos para confirmar o schema exato ao escrever o pipeline (ver `inspect_pni.py` da Etapa 1, criado exatamente por essa incerteza). Fixar nomes errados quebraria o pipeline silenciosamente ou praticamente às cegas; o resolver falha de forma explícita e lista as colunas disponíveis quando não encontra um candidato. **Confirmado contra os dados reais** (rodando `clean_pni.py` no Codespace): o schema real usa `dt_vacina` (data), `sg_imunobiologico` (nome/sigla da vacina), `co_dose_vacina`/`ds_tipo_dose` (dose) e `co_municipio_paciente`/`co_municipio_estabelecimento` (município) — nenhum dos nomes hipotéticos originais batia exatamente; `COLUMN_CANDIDATES` foi atualizado com os nomes reais como primeira opção, mantendo os antigos como fallback. |
| Usar `co_municipio_paciente` (residência do paciente), não `co_municipio_estabelecimento` (onde a dose foi aplicada), como código de município | A população do IBGE (denominador da cobertura) é contada por residência. Se o numerador (doses) usasse o município do estabelecimento, cidades-polo com grandes hospitais/UBS que atendem pacientes de fora inflariam artificialmente sua cobertura, e os municípios vizinhos que enviam pacientes para lá apareceriam com cobertura subestimada — o oposto do que os dois realmente têm. |
| Descartar linhas sem código de município válido (7 dígitos) | Sem município não é possível agregar por município nem cruzar com a população do IBGE — a linha não é utilizável para o objetivo do projeto. |
| Descartar linhas sem data de aplicação válida | A agregação é por mês; uma linha sem data não pode ser alocada a um período. |
| Detectar o formato da data por amostra (`%Y-%m-%d` vs `%d/%m/%Y` etc.) em vez de usar heurística `dayfirst` | `dayfirst=True/False` do pandas resolve a ambiguidade só parcialmente e pode inverter dia e mês silenciosamente quando o formato real do dado é o oposto do assumido — isso foi detectado durante o desenvolvimento (teste com datas ISO `2025-01-05` sendo lidas como 1º de maio). Testar qual formato explícito casa com mais valores da amostra evita esse erro silencioso. |
| Remover duplicatas exatas (linha inteira repetida), mas só dentro do mesmo bloco de streaming (chunk de 100 mil linhas) | Indicam erro de extração/join na fonte (mesmo registro exportado duas vezes), não doses reais adicionais — mantê-las infla artificialmente a contagem de doses. Limitação aceita: como o arquivo é processado em streaming (ver decisão acima), uma duplicata cujas duas ocorrências caiam em blocos diferentes não é detectada. Trade-off necessário para processar arquivos maiores que a RAM disponível; duplicatas exatas tendem a ser raras e, quando ocorrem, tendem a estar próximas no arquivo de origem. |
| Agregar para `município × mês (× vacina)` já na limpeza, em vez de manter uma linha por dose | Reduz drasticamente o volume de dados (o objetivo do projeto é município, não paciente individual) e evita manter dado de nível de paciente além do necessário. |
| Sinalizar município-mês fora de `[Q1 − 3·IQR, Q3 + 3·IQR]` como outlier, **sem remover** | Um valor muito alto pode ser um polo regional de vacinação (município que atende vizinhos) — informação relevante para o objetivo do projeto (priorizar ações), não ruído a descartar. A decisão de remover ou não fica para a análise exploratória, com a coluna `outlier_iqr` disponível para essa investigação. |

## 3. Métrica de cobertura vacinal (refined)

| Decisão | Justificativa |
|---|---|
| Métrica é "doses aplicadas por 100 habitantes", não "% de pessoas vacinadas" | O dataset agregado não separa por dose (1ª, 2ª, reforço) de forma confiável em todos os casos, então uma pessoa com 2 doses conta 2x no numerador. Chamar isso de "cobertura populacional" seria impreciso; documentamos a métrica como um proxy de intensidade de vacinação. Reavaliar na Etapa 3 se for possível filtrar por "1ª dose"/dose única. |
| Manter municípios com população no IBGE mas 0 doses no PNI (em vez de excluir) | "Sem dado de vacinação" é, em si, um sinal relevante para o objetivo do projeto (identificar áreas de baixa cobertura para priorizar ações) — excluir esses municípios esconderia exatamente o que o projeto quer encontrar. **Atenção ao interpretar**: com o escopo reduzido a jan-jun + ago/2025 (ver decisão de escopo acima), "0 doses" pode significar apenas "sem dose nos meses coletados", não necessariamente "sem vacinação no ano todo" — deixar isso explícito em qualquer gráfico/conclusão da EDA. |

## Pendências conhecidas / próximos passos

- Faltam jul, set, out, nov e dez/2025 no dataset de doses do PNI — o
  disco do ambiente de desenvolvimento esgotou ao tentar baixar o ano
  completo (arquivos nacionais de 1,4GB a 5GB por mês). Se der para
  liberar mais disco (Codespace com máquina maior, ou rodar localmente
  com mais espaço), completar o ano deixa a métrica de cobertura mais
  representativa.
- As fontes de renda/IDH (IBGE/SIDRA) citadas no README como variável
  socioeconômica ainda não têm um script de ingestão — só população foi
  coletada até aqui. Precisa de uma decisão: adicionar a coleta (outra
  tabela SIDRA) antes da análise de correlação, ou ajustar o escopo da
  Etapa 2 para cobertura vs. população/densidade apenas.
- Este documento e `docs/dicionario_dados.md` foram inicialmente escritos
  sem acesso aos dados reais do PNI (rede bloqueada no ambiente usado para
  desenvolver o pipeline). Já validamos o schema real rodando `clean_pni.py`
  contra os dados baixados no Codespace e ajustamos `COLUMN_CANDIDATES`
  (ver decisão acima); falta ainda atualizar `docs/dicionario_dados.md` com
  os nomes de coluna reais do PNI (hoje ele documenta só os nomes
  hipotéticos originais).
