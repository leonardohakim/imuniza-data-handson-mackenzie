# Guia de Setup — ImunizaData (Codespace)

Guia passo a passo para colocar o projeto de pé dentro do GitHub Codespaces,
da inicialização até o final da Etapa 2 (análise exploratória). Pensado
para qualquer pessoa da equipe rodar do zero, sem depender de contexto que
só quem já mexeu no projeto tem.

Cada bloco de comandos é independente: se travar em algum passo, o bloco
"Solução de problemas comuns" no final cobre os erros reais que já
enfrentamos nesta sessão.

## 0. Abrir o Codespace

No GitHub, dentro do repositório, botão verde **Code → Codespaces → Create
codespace on main** (ou reabra um Codespace existente na mesma aba). O
terminal já abre na raiz do projeto.

## 1. Instalar dependências

```bash
pip install -r requirements.txt
pip install pytest
```

## 2. Subir o ambiente (MinIO) e validar

```bash
docker-compose up -d
sleep 15
python -m src.validate_setup
```

O `docker-compose up` sobe o MinIO local (portas 9000/9001) e cria
automaticamente os 3 buckets (`raw`, `trusted`, `refined`) via o serviço
`createbuckets`. O `sleep 15` evita rodar o `validate_setup` antes do MinIO
terminar de subir. `validate_setup.py` confere conectividade com o MinIO e
com as fontes externas (SIDRA, OpenDataSUS); um `[FAIL]` pontual em "SUS
Dados Abertos" é um endpoint externo instável, não bloqueia o resto.

## 3. Etapa 1 — Ingestão (grava no bucket `raw`)

```bash
python -m src.ingestion.download_ibge --ano 2025
python -m src.ingestion.download_pib --ano 2023
python -m src.ingestion.inspect_pni --ano 2025 --mes 1
```

- `download_ibge`/`download_pib`: dados demográficos e econômicos do
  IBGE/SIDRA. **Use `--ano 2025` para a população** (ver nota importante no
  próximo passo — não é só um detalhe estético).
- `download_pib`: PIB municipal fica sempre ~2 anos defasado na fonte; 2023
  é o ano mais recente disponível na série do IBGE.
- `inspect_pni`: confirma os nomes reais das colunas do CSV do PNI antes de
  limpar (o schema já foi validado nesta sessão, mas é bom hábito rodar
  antes de confiar no pipeline).
- **O PNI (doses aplicadas) não passa por `download_pni.py` aqui** — ver o
  próximo passo: `clean_pni.py` já baixa e limpa o ano inteiro num único
  comando, direto da fonte, sem gravar em `raw`.

## 4. Etapa 2 — Limpeza e cruzamento (grava em `trusted`/`refined`)

```bash
python -m src.cleaning.clean_ibge --ano 2025
python -m src.cleaning.clean_pib --ano 2023
python -m src.cleaning.clean_pni --ano 2025
python -m src.cleaning.build_coverage --ano 2025
```

**Por que `clean_pni.py` sozinho basta para o PNI (sem `download_pni.py`
antes):** por padrão, `clean_pni.py --ano <ano>` baixa cada mês direto da
fonte (OpenDataSUS) para um arquivo temporário local, limpa, envia o
parquet para `trusted` e apaga o temporário antes do próximo mês — nunca
grava o ZIP bruto no bucket `raw`. Baixar os 12 meses inteiros para `raw`
primeiro (via `download_pni.py`) já esgotou o disco deste mesmo Codespace
numa tentativa anterior (~18,5GB; só 7 dos 12 meses couberam — ver
`docs/decisoes_limpeza.md`, seção 2). `download_pni.py` continua
disponível, mas só faz sentido se você quiser arquivar os ZIPs brutos em
`raw` de propósito (ex.: auditoria); nesse caso, rode-o antes e use
`clean_pni.py --ano 2025 --from-raw` para reaproveitar o que foi
arquivado em vez de baixar de novo.

**Nota importante — por que população usa `--ano 2025`, não `2024`:**
`build_coverage.py` usa o **mesmo** parâmetro `--ano` para localizar tanto
a população quanto as doses no `trusted`
(`ibge/populacao/ano={ano}/...` e `pni/ano={ano}/...`). Se você limpar a
população com `--ano 2024`, o `build_coverage --ano 2025` não vai
encontrá-la na partição que ele de fato lê (`ano=2025`). Foi exatamente
esse desalinhamento que gerou um bug real nesta sessão (a coluna `ano` do
dataset saía errada porque `build_coverage` estava lendo uma partição
antiga, não reprocessada) — ver `docs/decisoes_limpeza.md`, seção 8, para
o relato completo. Enquanto o projeto não separar os dois anos em
parâmetros distintos, use sempre o mesmo `--ano` para `clean_ibge` e
`build_coverage`.

O PIB usa um parâmetro separado (`--ano-pib`, default 2023) justamente
porque tem sua própria defasagem — `build_coverage` já lida com isso
corretamente, sem precisar de atenção extra.

## 5. Testes automatizados

```bash
python -m pytest tests/ -v
```

Esperado: **37 passed**. Os testes não dependem de MinIO nem rede (só
funções puras de limpeza/cruzamento), então rodam em menos de 2 segundos.
Também rodam automaticamente a cada `push`/`pull request` na `main` via
GitHub Actions — confira o badge no topo do README ou a aba **Actions** do
repositório.

## 6. Notebook de análise exploratória

```bash
jupyter nbconvert --to notebook --execute --inplace notebooks/02_analise_exploratoria.ipynb
```

Executa as 7 seções do notebook de ponta a ponta contra o dataset
refinado completo e regrava o próprio arquivo com os outputs atualizados
(gráficos em `reports/*.png`, tabelas, `df.head()` etc.). Se preferir
rodar interativamente em vez de via linha de comando:

```bash
jupyter notebook notebooks/02_analise_exploratoria.ipynb
```

## 7. Publicar as mudanças

```bash
git status
git add <arquivos modificados>
git commit -m "mensagem descrevendo o que mudou"
git push
```

Depois do push, confira a aba **Actions** do GitHub (deve aparecer ✅ verde
para o commit) e, se mexeu em algo que aparece no README (diagrama,
badges), dá uma olhada na página inicial do repositório para confirmar que
está renderizando certo.

## 8. Checklist final da Etapa 2

- [ ] `docker-compose up` + `validate_setup.py` sem erro (fora o endpoint externo instável)
- [ ] Ingestão dos 3 fontes concluída sem erro
- [ ] Limpeza + cruzamento concluídos, com população e cobertura na **mesma** partição de ano
- [ ] `pytest tests/ -v` → 37 passed
- [ ] CI (GitHub Actions) verde no último push
- [ ] Notebook executado de ponta a ponta sem erro
- [ ] README renderizando o diagrama de arquitetura (`docs/arquitetura_pipeline.svg`)
- [ ] `docs/decisoes_limpeza.md` e `docs/dicionario_dados.md` consistentes com o código atual

## 9. Solução de problemas comuns

**`ConnectionRefusedError [Errno 111]` ou `ConnectionResetError` ao rodar
qualquer script que acesse o MinIO** — o Codespace foi reconectado e o
container do MinIO ainda não terminou de subir. Rode:
```bash
docker ps -a
docker-compose up -d
sleep 15
```
e tente de novo.

**`git apply` trava o terminal sem retornar** — normalmente acontece
quando o comando é passado sem o nome do arquivo do patch (o `git apply`
espera receber o patch pela entrada padrão e fica esperando indefinidamente).
Sempre inclua o nome do arquivo: `git apply --check nome-do-patch.patch`,
nunca só `git apply --check` sozinho. Se travar mesmo assim, abra uma nova
aba de terminal (ícone `+`) em vez de tentar destravar a antiga.

**`error: can't open patch '...'`** — o arquivo `.patch` não está na pasta
onde você está rodando o comando (normalmente porque foi baixado no
navegador, não colocado no Codespace). Confirme com `ls *.patch` antes de
aplicar.

**Dois patches em sequência, o segundo falha com `patch does not apply`**
— geralmente porque o primeiro patch da sequência ainda não foi aplicado
(cada patch depois do primeiro espera o arquivo já modificado pelo
anterior). Aplique um de cada vez, na ordem em que foram enviados, sempre
conferindo com `git status` entre um e outro.

**`docker run ... minio/mc` reclama que `sh` não é um comando reconhecido**
— a imagem `minio/mc` já vem com `mc` como entrypoint padrão; é preciso
sobrescrever com `--entrypoint sh` antes do nome da imagem:
```bash
docker run --rm --network host --entrypoint sh minio/mc -c "comando aqui"
```

**MinIO console mostra buckets duplicados ou com nomes antigos**
(`bronze`/`silver`/`gold` além de `raw`/`trusted`/`refined`) — resíduo de
uma versão anterior do `docker-compose.yml`; o volume do MinIO é
persistente e não limpa buckets antigos sozinho. Remova com:
```bash
docker run --rm --network host --entrypoint sh minio/mc -c "
mc alias set myminio http://localhost:9000 admin minioadmin123 &&
mc rb --force myminio/bronze &&
mc rb --force myminio/silver &&
mc rb --force myminio/gold
"
```
(ajuste os nomes dos buckets antigos conforme o que aparecer no seu
console).

**Um dataset processado não reflete uma correção recente no código** —
confira em qual partição (`ano={ano}` no MinIO) o script que você rodou
realmente lê e grava, e reprocesse exatamente essa partição. Ver a nota do
passo 4 acima; é um erro fácil de cometer e difícil de perceber, porque o
comando roda sem erro nenhum.

**Disco cheio (`No space left on device`) ao processar o PNI** — quase
sempre é ter rodado `download_pni.py` para os 12 meses antes de limpar
(grava ~18,5GB permanentemente no bucket `raw`). O passo 4 acima
(`clean_pni.py --ano 2025`, sem `--from-raw`) não tem esse problema: baixa
um mês por vez para um temporário local e apaga antes do próximo. Se o
disco já encheu por causa de um `download_pni.py` anterior, `docker system
prune` e limpar o bucket `raw` (via MinIO console ou `mc rb`) costumam
liberar espaço suficiente para tentar de novo com `clean_pni.py` direto.
