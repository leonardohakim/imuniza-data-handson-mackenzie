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
