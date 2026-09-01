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

## Verificabilidade das fontes

Todas as três fontes são **APIs públicas de órgãos oficiais do governo
federal** (Ministério da Saúde / DATASUS e IBGE), sem custo e sem
autenticação, com URLs exatas fixadas no código de ingestão
(`src/ingestion/download_ibge.py`, `download_pib.py`, `download_pni.py`) —
qualquer pessoa pode acessar as mesmas URLs e obter os mesmos dados brutos
que o projeto usa, o que torna a coleta auditável e reprodutível por
terceiros.

## Aspectos legais, éticos e vieses potenciais

### LGPD e privacidade

As três fontes usadas são **dados públicos agregados de órgãos oficiais**
(DATASUS/OpenDataSUS e IBGE), disponibilizados sob política de dados
abertos exatamente para uso público e reprodutível — não é feita nenhuma
coleta de dado de fonte privada ou restrita. Ainda assim, o PNI nasce como
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
  código de município, não por pessoa, contra população (IBGE) e PIB
  (IBGE) — ambas já agregadas na fonte.
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
  correlação cobertura × PIB na análise exploratória.

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
