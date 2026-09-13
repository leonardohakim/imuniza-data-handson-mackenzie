# Critérios de Seleção dos Dados (Etapa 2)

Este documento explica **por que** cada fonte de dado foi escolhida (e o
que foi descartado), e qual o recorte geográfico e temporal do projeto.
Para o **schema** de cada dataset, ver
[`docs/dicionario_dados.md`](dicionario_dados.md); para as decisões de
**limpeza** de cada um, ver [`docs/decisoes_limpeza.md`](decisoes_limpeza.md).

## Escopo geográfico: nacional, todos os municípios

O projeto cobre **todos os municípios do Brasil**, sem recorte por região.
Uma versão inicial do pipeline cogitou restringir a coleta à região
Sudeste para reduzir volume de dado, mas essa ideia foi descartada: o
objetivo do projeto é apoiar priorização de ações de vacinação a nível
nacional (SUS), e um recorte regional esconderia exatamente os municípios
de outras regiões que mais precisam de atenção. O problema de volume que
motivou a ideia original foi resolvido de outra forma — processamento em
streaming (ver `docs/decisoes_limpeza.md`, seção 2) — preservando a
abrangência nacional.

## Escopo temporal

- **Doses aplicadas (PNI)**: ano completo de **2025** (jan-dez, 12 meses).
  Um ano completo evita que meses sazonais (ex.: campanhas específicas)
  distorçam a comparação entre municípios.
- **População (IBGE)**: estimativa mais recente disponível na API SIDRA no
  momento da coleta, referente ao mesmo ano da cobertura (2025), para que
  numerador (doses) e denominador (população) sejam do mesmo período.
- **PIB per capita (IBGE)**: 2023, o ano mais recente disponível na série
  do IBGE (dado municipal de PIB sempre sai com defasagem de cerca de 2
  anos; não existe "PIB de 2025" publicado). Essa defasagem é uma
  limitação conhecida e documentada — ver `docs/decisoes_limpeza.md`,
  seção 3.
- **Área territorial (IBGE) e CNES**: sem recorte por `--ano` de propósito
  — nenhuma das duas fontes é uma série histórica nesta pipeline. Área
  territorial muda muito pouco ano a ano (o IBGE/SIDRA expõe uma medição
  vigente, não uma série anual comparável às demais); o CNES é consultado
  como cadastro **atual** de estabelecimentos (snapshot), não uma série
  histórica. Justificativa completa em `docs/decisoes_limpeza.md`, seções
  10 e 11.

## Fontes avaliadas e escolhidas

### Doses aplicadas (variável-alvo)

- **Escolhida**: SI-PNI, via portal OpenDataSUS
  (`https://dadosabertos.saude.gov.br`, dataset "doses aplicadas pelo
  Programa Nacional de Imunizações"), acessado programaticamente pela API
  CKAN do portal (`.../api/3/action/package_show`).
- **Por que**: é a fonte primária, oficial, do próprio programa de
  vacinação, com granularidade de município, mês e tipo de dose —
  necessária para a métrica que o projeto propõe.
- **Alternativa considerada e descartada**: o TabNet/DATASUS (citado no
  README como fonte de referência) expõe os mesmos dados, mas via
  interface de tabulação manual (web), sem uma API estável para coleta
  programática e reprodutível em lote para todos os municípios do país;
  o OpenDataSUS expõe o mesmo dado subjacente em arquivos baixáveis por
  API, o que é o que uma coleta automatizada e reprodutível exige.

### População (denominador da métrica)

- **Escolhida**: IBGE/SIDRA, Tabela 6579 (população residente estimada),
  API `https://apisidra.ibge.gov.br/values/t/6579/n6/all/v/9324/p/{ano}`.
- **Por que**: fonte oficial do Censo/estimativas populacionais do IBGE,
  com granularidade municipal e API pública documentada.

### Variável socioeconômica

- **Escolhida**: PIB per capita municipal, calculado a partir do PIB total
  (IBGE/SIDRA, Tabela 5938, variável 37), API
  `https://apisidra.ibge.gov.br/values/t/5938/n6/all/v/37/p/{ano}`.
- **Alternativas avaliadas e descartadas**:
  - **Renda per capita (PNAD Contínua)**: os dados mais recentes por essa
    métrica só existem a nível Brasil/UF, não de município — não permite
    cruzar com a cobertura por município.
  - **IDH municipal (IDHM)**: só existe calculado para 2010 (Atlas do
    Desenvolvimento Humano/PNUD), sem atualização desde o Censo 2022;
    cruzar cobertura de 2025 com um indicador de 15 anos atrás foi
    considerado defasado demais para uma conclusão confiável.
  - **Tabela 6784 do SIDRA** (aparenta ser "PIB dos Municípios" pelo
    nome): a API rejeita consulta por município nessa tabela — ela só
    existe a nível Brasil. Confirmado consultando `/metadados` da tabela
    antes de escrever qualquer código de ingestão.
  - Justificativa completa (incluindo por que calcular per capita
    manualmente em vez de usar uma variável pronta) em
    `docs/decisoes_limpeza.md`, seção 3.

### Área territorial e densidade demográfica (feature adicional)

- **Escolhida**: IBGE/SIDRA, Tabela 4714 (área territorial), mesma API do
  restante do IBGE usado no projeto (`apisidra.ibge.gov.br`).
- **Por que**: densidade demográfica (calculada a partir da área e da
  própria população do dataset) é um sinal geográfico adicional que pode
  ajudar a explicar parte da variação de cobertura não capturada por
  população/PIB isoladamente — mesma lógica de enriquecimento de features
  já aplicada ao CNES, abaixo.
- **Alternativa considerada e descartada**: usar a densidade que a própria
  Tabela 4714 já traz pronta, em vez de recalcular — descartada porque
  aquela densidade usa a população de um ano de referência diferente do
  usado no resto do projeto (2025); recalcular a partir da população já
  presente no dataset mantém as duas variáveis (população e densidade)
  consistentes entre si. Justificativa completa em
  `docs/decisoes_limpeza.md`, seção 10.
- **Histórico de disponibilidade (resolvido)**: esta fonte chegou a
  enfrentar bloqueio de rede (WAF/F5 do lado do provedor) no ambiente de
  desenvolvimento, intermitente e depois persistente, e por um período o
  projeto rodou sem a feature — a ingestão é condicional justamente por
  isso (ver `docs/decisoes_modelagem.md`, seção 1). O dado foi obtido
  posteriormente e **área/densidade está materializada no `refined` e em
  uso como feature**: `log_densidade_hab_km2` tem correlação de -0,104 com
  a cobertura e aparece em 4º lugar na importância do Random Forest
  (~0,14). A degradação graciosa continua no código como robustez, não
  como estado atual.

### Estabelecimentos de saúde — CNES (feature adicional)

- **Escolhida**: CNES (Cadastro Nacional de Estabelecimentos de Saúde),
  via portal OpenDataSUS (mesma API CKAN já usada para o PNI), dataset
  `cnes-cadastro-nacional-de-estabelecimentos-de-saude`.
- **Por que**: acesso a infraestrutura de saúde é uma hipótese direta de
  fator associado à cobertura vacinal (mais pontos de atendimento
  ambulatorial SUS, mais fácil vacinar) — não coberta por nenhuma das
  três fontes originais (PNI, população, PIB). Reaproveita a mesma
  infraestrutura de coleta já validada para o PNI (`list_resources`,
  `download_to_temp`, cliente MinIO), sem duplicar lógica.
- **Por que não entrou desde a Etapa 1/2 original**: só foi identificada
  como fonte relevante depois da modelagem inicial, ao revisar as
  limitações registradas em `docs/decisoes_modelagem.md` (poucas
  features) — adicionada nesta sessão como parte do esforço de melhorar o
  trabalho além do mínimo, não porque a fonte não existisse antes.
- Schema real inspecionado contra a fonte (`investigar_cnes_schema.py`)
  antes de escrever qualquer código de ingestão — mesmo princípio já
  aplicado ao PNI/PIB/área. Justificativa completa (formato do arquivo,
  filtro de atendimento ambulatorial SUS, código de município de 6
  dígitos) em `docs/decisoes_limpeza.md`, seção 11.

### Faixa de fronteira — IBGE, Lei 6.634/1979 (feature adicional)

- **Escolhida**: planilha oficial "Municípios da Faixa de Fronteira e
  Cidades-Gêmeas" (IBGE, edição 2024), publicada no GeoFTP de organização
  do território.
- **Por que**: a análise exploratória (notebook 02, seção 3) mostrou que os
  municípios de cobertura extrema são polos de fronteira que atendem
  não residentes — foi o achado geográfico mais forte da Etapa 2, mais
  marcante que qualquer variável socioeconômica. Até então esse sinal
  entrava no modelo como uma **aproximação grosseira por UF** (11 estados
  inteiros marcados como "fronteira"), que contamina com o mesmo valor
  municípios a centenas de quilômetros da linha divisória. A lista oficial
  substitui essa aproximação por um sinal municipal preciso.
- **Critério adotado**: `fronteira = 1` quando a **sede** do município está
  dentro da faixa (`FAIXA_SEDE = "sim"`), não quando o território apenas
  intersecta a faixa. São **511 municípios** com sede na faixa, de 588 que
  a intersectam. Justificativa completa em `docs/decisoes_limpeza.md`,
  seção 12.
- **Ressalva de coleta**: o GeoFTP bloqueou (WAF) as requisições feitas a
  partir do ambiente de nuvem; o arquivo foi baixado por uma rede sem o
  bloqueio e enviado ao bucket `raw`. O script
  (`download_fronteira.py`) continua sendo a forma reprodutível de obter o
  dado quando a rede permite — mesma situação já vivida com a área
  territorial.

### Saneamento básico — SNIS, via Base dos Dados (feature adicional)

- **Escolhida**: tabela `br_mdr_snis.municipio_agua_esgoto` do SNIS
  (Sistema Nacional de Informações sobre Saneamento, Ministério das
  Cidades), acessada pela **Base dos Dados**, ano de referência **2022**.
- **Por que**: saneamento é um proxy de infraestrutura urbana básica e de
  presença do Estado no município — uma hipótese plausível de fator
  associado ao acesso a serviços de saúde, e de natureza diferente das
  features que já tínhamos (demografia, renda, rede de saúde, geografia).
- **Por que só o indicador de água**: coleta e tratamento de esgoto têm
  completude de apenas ~53% mesmo no ano mais completo; exigi-los
  descartaria quase metade do dataset. Ficam disponíveis no `refined` para
  análise futura, fora do conjunto de features — ver
  `docs/decisoes_limpeza.md`, seção 13.
- **Por que via Base dos Dados e não direto do SNIS**: o painel oficial do
  SNIS não expõe uma API tabular estável para download programático; a
  Base dos Dados republica a mesma série em formato consultável e versionado.
  É a **única fonte do projeto que passa por um intermediário** — uma
  organização da sociedade civil, não um órgão federal —, o que é uma
  dependência a mais na cadeia de proveniência e está registrado aqui de
  propósito.
- **Custo assumido**: o indicador de água não cobre todos os municípios;
  aplicando o critério "descartar, não imputar" do projeto, **146
  municípios saem do conjunto de modelagem** (5.571 → 5.424). Foi o maior
  descarte do projeto, e foi considerado aceitável (~2,6%) porque imputar
  um percentual de saneamento fabricaria justamente o tipo de dado que a
  feature pretende medir.

## Verificabilidade das fontes

Seis das sete fontes são **APIs/portais públicos de órgãos oficiais do
governo federal** (Ministério da Saúde / DATASUS e IBGE), sem custo e sem
autenticação, com URLs exatas fixadas no código de ingestão
(`src/ingestion/download_ibge.py`, `download_pib.py`, `download_pni.py`,
`download_area.py`, `download_cnes.py`, `download_fronteira.py`) — qualquer
pessoa pode acessar as mesmas URLs e obter os mesmos dados brutos que o
projeto usa, o que torna a coleta auditável e reprodutível por terceiros.

A sétima, o SNIS (`download_snis.py`), é dado público de um órgão federal
(Ministério das Cidades) mas acessado **através da Base dos Dados**, um
intermediário — a URL fixada no código aponta para lá, não para o painel do
SNIS. A proveniência continua verificável, mas com um elo a mais.

## Aspectos legais, éticos e vieses potenciais

### LGPD e privacidade

As sete fontes usadas são **dados públicos de órgãos oficiais**
(DATASUS/OpenDataSUS, IBGE e SNIS/Ministério das Cidades — este último via
Base dos Dados), disponibilizados sob política de dados abertos exatamente
para uso público e reprodutível — não é feita nenhuma coleta de dado de
fonte privada ou restrita. Área territorial (medição geográfica), faixa de
fronteira (classificação territorial), saneamento (indicador agregado por
município) e CNES (cadastro de **estabelecimentos**, não de pessoas) não
levantam questão de dado pessoal — a unidade de registro em todos já é o
estabelecimento/município, não o indivíduo. Ainda assim, o PNI nasce como
registro individual (uma linha por dose aplicada, potencialmente
identificável por paciente na fonte original), o que traz uma
responsabilidade de tratamento mesmo sendo dado público:

- **Nenhum dado de nível de paciente é persistido em nenhuma camada do
  projeto.** `clean_pni.py` processa o CSV do PNI em streaming e agrega
  para `município × mês (× vacina)` **dentro do mesmo passo de limpeza**,
  antes de gravar qualquer coisa em `trusted` (ver
  `docs/decisoes_limpeza.md`, seção 2, decisão "Agregar para município ×
  mês... já na limpeza, em vez de manter uma linha por dose") — as linhas
  individuais existem só de forma efêmera, em memória, durante o
  processamento de cada bloco de 100 mil linhas, e nunca chegam a ser
  gravadas no MinIO.
- **Nenhum campo diretamente identificador da fonte é sequer lido** para
  além do necessário para agregar (código de município do paciente, data
  da dose, tipo de imunobiológico) — nome, CPF, data de nascimento e
  qualquer outro campo de identificação pessoal presentes no CSV bruto do
  PNI não são lidos nem armazenados pelo pipeline.
- **Não há cruzamento com nenhuma outra base que permita reidentificar
  indivíduos**: o cruzamento final (`build_coverage.py`) é feito por
  código de município, não por pessoa, contra população e PIB (IBGE), área
  territorial (IBGE), faixa de fronteira (IBGE), CNES (DataSUS) e
  saneamento (SNIS) — todas já agregadas por município na própria fonte.
- Por operar exclusivamente com agregados por município (nunca por
  indivíduo) e nunca persistir granularidade de paciente, o projeto evita,
  por desenho, o tipo de dado que a LGPD mais protege (dado pessoal, e
  potencialmente dado pessoal sensível no caso de dado de saúde) — a
  privacidade aqui não depende de uma política declarada à parte, mas da
  própria arquitetura do pipeline (raw → trusted já nasce agregado).

### Viés (bias)

Vieses conhecidos e como cada um foi tratado ou permanece como limitação
documentada:

- **Viés de subnotificação**: municípios com sistemas de informação mais
  fracos podem registrar doses aplicadas com atraso ou de forma
  incompleta no PNI. Uma cobertura aparentemente baixa pode refletir
  **qualidade de registro**, não vacinação real mais baixa — essa é uma
  limitação conhecida da métrica (`doses_aplicadas_por_100_habitantes` é
  um proxy, não uma medição direta e infalível de imunização), citada
  também em `docs/decisoes_limpeza.md`, seção 4.
- **Viés de concentração geográfica (cidade-polo)**: mitigado por
  desenho, não só documentado — o cruzamento usa o município de
  **residência do paciente** (`co_municipio_paciente`), não o de
  **atendimento** (`co_municipio_estabelecimento`), justamente para não
  inflar artificialmente a cobertura de municípios-polo com grandes
  unidades de saúde às custas de municípios vizinhos menores (ver
  `docs/decisoes_limpeza.md`, seção 2).
- **Viés de supressão de sinal real**: valores extremos (outliers) não são
  removidos automaticamente, só sinalizados (`outlier_iqr`) — remover um
  valor extremo sem investigar poderia apagar exatamente o tipo de caso
  (bom ou ruim) que o projeto quer identificar para priorização.
- **Viés de proxy socioeconômico único**: o projeto usa apenas PIB per
  capita como variável socioeconômica (ver seção "Fontes avaliadas e
  escolhidas" acima); é uma aproximação, não uma medida completa de
  vulnerabilidade social — um município pode ter PIB per capita alto e
  ainda assim desigualdade interna relevante que essa única variável não
  captura. Essa limitação deve ser considerada ao interpretar qualquer
  correlação cobertura × PIB na análise exploratória. O mesmo viés se
  propaga para a Etapa 3: `log_pib_per_capita` é usada como feature dos
  modelos de classificação, então qualquer viés desse proxy também limita
  a interpretação dos coeficientes/importâncias de feature — ver
  `docs/decisoes_modelagem.md`, seção 11.
- **Viés de proxy de acesso à saúde único (CNES)**: `qtd_estabelecimentos_saude_sus`
  conta estabelecimentos com atendimento ambulatorial SUS, mas não
  distingue capacidade real (tamanho, equipe, se de fato aplica vacina)
  nem distância efetiva até o paciente — um município pode ter vários
  estabelecimentos pequenos e ainda assim baixa capacidade de vacinação,
  ou poucos estabelecimentos mas de grande porte. É um proxy de
  infraestrutura, não uma medida direta de capacidade vacinal. Achado real
  registrado em `docs/decisoes_modelagem.md`, seção 11: a feature carrega
  sinal relevante no modelo (2ª maior importância no Random Forest) apesar
  dessa limitação.
- **Viés de imprecisão geográfica (densidade)**: `densidade_hab_km2` é
  uma média municipal — não captura concentração populacional desigual
  dentro do próprio município (uma cidade grande com zona rural extensa e
  pouco povoada tem densidade média baixa mesmo com bolsões densamente
  povoados). A feature está em uso (4ª maior importância), com essa
  ressalva de interpretação.
- **Viés de cobertura do indicador de saneamento**: o SNIS depende de os
  prestadores de serviço **reportarem** os dados, e municípios menores ou
  com serviço menos estruturado são justamente os que mais faltam no
  painel. Como o critério do projeto é descartar quem não tem o dado, os
  146 municípios excluídos não são um sorteio aleatório — tendem a ser os
  de infraestrutura mais frágil, exatamente o perfil de interesse. É um
  viés de seleção que reduz levemente a representatividade do conjunto de
  modelagem e deve ser levado em conta ao ler os resultados.
- **Viés de recorte territorial (fronteira)**: a feature marca se a *sede*
  do município está na faixa, o que é um recorte binário de um fenômeno
  contínuo (distância até a linha divisória). Dois municípios de fronteira
  a 10km e a 145km da divisa recebem o mesmo valor.

## Critérios de inclusão/exclusão de registros

Aplicados já na etapa de limpeza (não na coleta — a coleta traz o dado
bruto completo, sem filtrar nada previamente); documentados com
justificativa individual em `docs/decisoes_limpeza.md`. Resumo:

- Município é descartado da análise se **não tiver população registrada**
  no IBGE (a população é o denominador da métrica central; não é
  imputada — ver `docs/decisoes_limpeza.md`, seção 1).
- Registro de dose é descartado se **não tiver código de município válido
  ou data de aplicação válida** (não é possível alocá-lo a um
  município/mês sem esses dois campos).
- Município-mês **não é descartado** por ter um valor de cobertura muito
  alto ou muito baixo (outlier): é sinalizado (`outlier_iqr`) para
  investigação na análise exploratória, e não removido — um valor extremo
  pode ser sinal real (ex.: polo regional de vacinação), não erro de
  dado.
- Linha de área territorial é descartada se o valor vier vazio ou não
  numérico (sigilo estatístico do IBGE); linha de CNES é descartada se o
  código de município não vier no padrão de 6 dígitos esperado. Em ambos
  os casos, município sem essa informação fica com a coluna em `NaN` no
  refinado, não com um valor imputado — ver `docs/decisoes_limpeza.md`,
  seções 10 e 11.
- Linha de faixa de fronteira é descartada se `FAIXA_SEDE` vier indefinida
  (2 linhas no arquivo real) — não se supõe "sim" nem "não". Aqui, e **só
  aqui**, a ausência do município na tabela vira `0` em vez de `NaN`: a
  fonte é uma lista positiva completa, então não aparecer nela já é a
  resposta "não é de fronteira" (seção 12).
- **Município sem o indicador de atendimento de água (SNIS) é descartado
  do conjunto de modelagem**, não imputado: são **146 municípios**, o
  maior descarte do projeto (5.571 → **5.424**, ~2,6%). A alternativa
  seria inventar um percentual de saneamento para quem não reporta — ver
  o viés de cobertura registrado acima e `docs/decisoes_limpeza.md`,
  seção 13.

### Efeito acumulado dos descartes na base de modelagem

| Passo | Municípios |
|---|---|
| Dataset refinado completo | 5.571 |
| − sem PIB / população / cobertura / CNES | −1 |
| − sem indicador de água (SNIS) | −146 |
| **Base final de modelagem** | **5.424** |

Essa base de 5.424 é a que alimenta o split 70/15/15 da Etapa 3
(3.796 / 814 / 814).
