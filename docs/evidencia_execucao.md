# Evidência de Execução do Pipeline

Este documento reúne evidências concretas de que o pipeline descrito em
`docs/arquitetura_pipeline.svg` roda de ponta a ponta contra dados reais —
não só no papel. Os números abaixo vêm de execuções reais no ambiente de
desenvolvimento (GitHub Codespaces + MinIO local via `docker-compose.yml`).

## 1. Volume de dado real processado (PNI, ano completo de 2025)

Rodando `python -m src.cleaning.clean_pni --ano 2025` (fluxo padrão: baixa
cada um dos 12 meses direto da fonte, limpa em streaming e grava só o
parquet agregado em `trusted`, sem gravar os ZIPs brutos em `raw`):

- **12 meses** processados (jan-dez/2025), nenhum mês faltando.
- **2.031.418 linhas** agregadas (município × mês) no parquet consolidado.
- **175,9 milhões de doses aplicadas** somadas em todo o ano.
- **5.571 municípios** presentes no dataset `refined` final — nenhum
  município brasileiro ficou de fora do cruzamento.

(Números também registrados em `docs/decisoes_limpeza.md`, seção
"Pendências conhecidas", junto com o histórico de como o problema de disco
que impedia processar o ano completo foi resolvido.)

## 2. Testes automatizados

37 testes automatizados (`pytest`), cobrindo as funções puras de limpeza e
cruzamento (`clean_ibge`, `clean_pib`, `clean_pni`, `build_coverage`), sem
depender de MinIO ou rede. Rodam localmente com:

```bash
python -m pytest tests/ -v
```

e automaticamente a cada `push`/pull request na branch `main`, via GitHub
Actions (`.github/workflows/tests.yml`) — o selo no topo do `README.md`
reflete o status da última execução no repositório real:
`https://github.com/leonardohakim/imuniza-data-handson-mackenzie/actions/workflows/tests.yml`.

## 3. Notebook de análise exploratória executado contra dado real

`notebooks/02_analise_exploratoria.ipynb` está commitado **com os outputs
de uma execução real** (não só o código): células rodadas contra o
`refined/cobertura_vacinal/ano=2025/cobertura_municipios.parquet` gerado
pelo pipeline, produzindo os quatro gráficos em `reports/`. Execução mais
recente (reprocessamento dos gráficos 1-3 após revisão de legibilidade):

```
$ jupyter nbconvert --to notebook --execute --inplace notebooks/02_analise_exploratoria.ipynb
[NbConvertApp] Converting notebook notebooks/02_analise_exploratoria.ipynb to notebook
[NbConvertApp] Writing 312387 bytes to notebooks/02_analise_exploratoria.ipynb

$ ls -la reports/*.png
-rw-rw-rw- 1 codespace codespace  60223 Aug 31 22:18 reports/cobertura_por_uf.png
-rw-rw-rw- 1 codespace codespace 121473 Aug 31 22:18 reports/cobertura_vs_pib_per_capita.png
-rw-rw-rw- 1 codespace codespace  53752 Aug 31 22:18 reports/cobertura_vs_populacao.png
-rw-rw-rw- 1 codespace codespace  76977 Aug 31 22:18 reports/distribuicao_cobertura.png
```

Reexecutar do zero (com o MinIO local rodando e o pipeline já materializado
até `refined`) é um único comando, sem edição manual:

```bash
jupyter nbconvert --to notebook --execute --inplace notebooks/02_analise_exploratoria.ipynb
```

## 4. Histórico real de commits do pipeline (não só um "commit único de entrega")

O histórico do repositório mostra o pipeline sendo construído, testado
contra dado real e corrigido incrementalmente — incluindo bugs reais
encontrados só ao rodar contra os dados de verdade (documentados em
`docs/decisoes_limpeza.md`), não um código nunca executado:

```
$ git log --oneline --reverse
0896f29 Initial commit
...
109f58b feat: pipeline de ingestao PNI com streaming, idempotencia e manifesto de governanca
568bddc fix: processa CSVs do PNI em streaming e corrige nomes de coluna reais
ab3d6f0 fix: corrige cruzamento codigo DATASUS (6 digitos) x IBGE (7 digitos) na cobertura
f9d889d test: adiciona suite pytest para clean_ibge, clean_pni e build_coverage
b480e3b docs: executa notebook EDA contra dados reais de 2025 e salva graficos
dc60242 feat: coleta PIB per capita municipal e cruza com cobertura vacinal
0531ed0 chore: adiciona CI (GitHub Actions) rodando pytest a cada push/PR
c8b3e80 fix: adiciona diagrama de arquitetura do pipeline e corrige bug na coluna ano da populacao IBGE
5c7d9e0 fix: reprocessa populacao ano=2025 com o codigo corrigido (build_coverage le essa particao, nao ano=2024)
e0188ed fix: incorpora reprocessar_pni_2025.py a clean_pni.py como fluxo padrao
9538b5c fix: melhora legibilidade dos graficos 1, 2 e 3 do notebook exploratorio
```

Repositório real:
`https://github.com/leonardohakim/imuniza-data-handson-mackenzie`

## 5. Como reproduzir do zero

Passo a passo completo, incluindo troubleshooting de problemas reais já
encontrados pela equipe (disco cheio, bucket com nome errado, coluna
lida errada), em
[`docs/guia_setup_etapa2.md`](guia_setup_etapa2.md). Resumo dos comandos em
[`README.md`](../README.md), seção "Como Executar".
