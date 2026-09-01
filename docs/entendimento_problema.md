# Entendimento do Problema (Etapa 1)

## O problema

O Brasil tem um dos maiores programas públicos de imunização do mundo (o
PNI, Programa Nacional de Imunizações), mas a cobertura vacinal não é
uniforme entre os mais de 5.500 municípios do país. Municípios com
cobertura baixa ficam mais vulneráveis ao ressurgimento de doenças que já
estavam sob controle (como sarampo e coqueluche), e a decisão de para onde
direcionar campanhas de reforço, mutirões e recursos de logística (mais
doses, mais agentes de saúde, mais pontos de vacinação) depende de saber
**quais municípios estão com cobertura baixa agora**, não apenas de uma
percepção geral de que "a cobertura vem caindo no Brasil".

O problema não é falta de dado: DATASUS/OpenDataSUS publica os registros de
doses aplicadas, e o IBGE publica população e indicadores socioeconômicos
por município — ambos públicos e gratuitos. O problema é que esses dados
**vivem em sistemas separados, em formatos e granularidades diferentes, sem
nenhum recorte pronto que combine "doses aplicadas por município" com
"população daquele município" e produza uma métrica direta e comparável
entre municípios**. Um gestor de saúde pública que queira essa resposta
hoje precisaria baixar e cruzar essas bases manualmente — algo inviável na
prática dado o volume (dezenas de milhões de registros de doses só em
2025) e a necessidade de repetir esse cruzamento periodicamente, à medida
que novos dados chegam.

## Por que isso importa

Priorizar mal onde investir esforço de vacinação tem custo direto: recursos
limitados (doses, equipes, verba de campanha) aplicados em municípios que
já têm cobertura adequada, enquanto municípios realmente vulneráveis
continuam sem prioridade — não por decisão consciente, mas por falta de
visibilidade do problema. Um levantamento sistemático, atualizável e
comparável entre municípios é o primeiro passo para que essa priorização
seja feita com base em dado, não em suposição.

## O que sabemos e o que ainda não sabemos hoje

**Sabemos:**
- Que os dados brutos de doses aplicadas (PNI/OpenDataSUS) e de população
  (IBGE/SIDRA) existem, são públicos e são atualizados periodicamente.
- Que a granularidade de ambos permite, em tese, calcular uma métrica de
  cobertura por município.

**Não sabemos (e é isso que o projeto busca responder):**
- Quais municípios brasileiros estão hoje com cobertura vacinal abaixo do
  esperado, de forma comparável entre eles.
- Se essa baixa cobertura se concentra em determinadas regiões (UFs) ou
  está espalhada de forma mais homogênea pelo país.
- Se características do município (porte populacional, nível
  socioeconômico) ajudam a explicar por que a cobertura varia tanto entre
  eles — o que ajudaria a antecipar, e não só reagir a, situações de risco.

## Perguntas que o projeto pretende responder

1. Quais municípios brasileiros apresentam cobertura vacinal (doses
   aplicadas por 100 habitantes) abaixo da mediana nacional, e como essa
   cobertura se distribui entre as Unidades da Federação?
2. Existe relação entre a cobertura vacinal de um município e o porte da
   sua população (municípios pequenos vs. grandes)?
3. Existe relação entre a cobertura vacinal e o nível socioeconômico do
   município (aproximado pelo PIB per capita)?
4. Quais municípios se destacam como valores extremos — muito acima ou
   muito abaixo do restante — e o que essas exceções podem indicar (por
   exemplo, um polo regional de vacinação que atende municípios vizinhos,
   versus um município com real dificuldade de acesso)?
5. *(Direção para a Etapa 3, fora do escopo desta fase)* É possível
   segmentar ou prever, a partir de características demográficas e
   socioeconômicas, quais municípios têm maior risco de baixa cobertura no
   próximo ciclo?

## Fora de escopo nesta etapa

Esta fase é sobre **entender e delimitar o problema**, não sobre como
resolvê-lo tecnicamente. As decisões de quais fontes de dado usar, como
elas serão coletadas, limpas e armazenadas, e quais ferramentas
implementam isso, estão documentadas separadamente em
[`docs/criterios_selecao_dados.md`](criterios_selecao_dados.md) (Etapa 2:
critérios de seleção) e [`docs/decisoes_limpeza.md`](decisoes_limpeza.md)
(Etapa 2: pré-processamento) — a arquitetura completa da solução está no
diagrama em [`docs/arquitetura_pipeline.svg`](arquitetura_pipeline.svg).

## Equipe

| Nome | RA |
|---|---|
| Leonardo Domingues Machado da Silva | 10735382 |
| Gabriel Cardoso Silva | 10733004 |
| Gabriela Addesso Ruvolo | 10735412 |
