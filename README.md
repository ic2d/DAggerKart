# DAggerKart

IA que joga **Mario Kart 64** no emulador **Mupen64-rr-lua**. Uma rede neural olha a tela e decide a
direção do kart. Ela aprende imitando um **especialista de busca** (que testa cada direção com
savestates e escolhe a melhor) e é refinada com **DAgger**. Dois modelos: um **transformer**
espaço-temporal e a **PilotNet**, a CNN da NVIDIA usada no projeto que deu origem a este.

> **Plataforma:** só Windows 10 (1903+) ou 11, 64 bits. O Mupen64-rr-lua é Windows-only e a captura
> de tela usa a API Windows Graphics Capture.

## Sumário

1. [Instalação](#instalação)
2. [Uso](#uso)
3. [Como funciona](#como-funciona)
4. [Resultados](#resultados)
5. [TO DO](#to-do)
6. [Solução de problemas](#solução-de-problemas)

---

## Instalação

| Requisito | |
|---|---|
| Sistema | Windows 10 (1903+) ou 11, 64 bits |
| GPU (recomendado) | AMD Radeon RX 6000/7000/9000 com ROCm, ou NVIDIA com CUDA. Sem GPU funciona, mas o treino fica lento |
| Disco | ~3 GB (Python + PyTorch) + ~35 MB por corrida coletada |
| ROM | Uma cópia sua de **Mario Kart 64 (USA)** (`.n64`, `.z64` ou `.v64`). **Não vem com o projeto** |

### 1. Projeto

Com o [Git para Windows](https://git-scm.com/download/win):

```bash
git clone https://github.com/andryll/DAggerKart.git
cd DAggerKart
```

### 2. Emulador (Mupen64-rr-lua 1.5)

Baixe o pacote x64 em <https://mupen64.com> (*Download 64-bit for Windows*; link direto:
<https://github.com/mupen64/repack/archive/refs/heads/stable-windows-x64.zip>) e extraia numa pasta,
por exemplo `C:\Emuladores\Mupen` (deve conter `mupen64.exe`).

### 3. Plugin de vídeo GLideN64

O plugin embutido no Mupen 1.5 (TAS Video) **trava com o Mario Kart** em fast-forward e depois de
muitos savestates, que é exatamente o que o projeto faz.

1. Em <https://github.com/gonetz/GLideN64/releases/tag/github-actions>, baixe
   **`GLideN64-...-Windows-PJ64Legacy-WTL-x64.zip`**. Precisa ser a build **PJ64Legacy x64**: a
   "Project64" trava ao abrir o jogo, porque o Mupen usa a versão antiga da especificação de plugins.
2. Extraia `GLideN64.dll` e `GLideN64.custom.ini` para a pasta `plugin` do Mupen (crie se não existir).

### 4. Configurar o Mupen

1. Abra o `mupen64.exe`, vá em **Options > Settings > Plugins** e escolha **GLideN64** em *Video*
   (Audio, Input e RSP ficam nos padrões "TAS ...").
2. Abra a ROM (*File > Load ROM*), confira se o jogo aparece e feche o Mupen normalmente (para ele
   salvar a configuração).
3. Desligue a verificação de atualizações: com o Mupen fechado, edite
   `%LOCALAPPDATA%\mupen64-rr-lua\config.json` e troque `"automatic_update_checking": 1` por `0`.
   Senão cada emulador aberto pela coleta mostra uma janela de atualização. O projeto foi validado na
   versão 1.5.0-5; não atualize sem testar.

### 5. Python 3.12

O PyTorch com ROCm para Windows só existe para Python **3.12** (ele convive com outras versões).
Instale com `py install 3.12` ([gerenciador de instalação do Python](https://www.python.org/downloads/windows/))
ou pelo [instalador](https://www.python.org/downloads/release/python-31210/), e crie o ambiente
virtual dentro da pasta do projeto:

```bash
py -V:3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
```

### 6. PyTorch (conforme a GPU)

**AMD (ROCm para Windows)**, com o driver Adrenalin **26.2.2 ou mais novo**. Versões do
[guia oficial da AMD](https://rocm.docs.amd.com/projects/radeon-ryzen/en/latest/docs/install/installrad/windows/install-pytorch.html)
na época do projeto (confira se há mais novas):

```bash
.venv\Scripts\python.exe -m pip install --no-cache-dir https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/rocm_sdk_core-7.2.1-py3-none-win_amd64.whl https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/rocm_sdk_devel-7.2.1-py3-none-win_amd64.whl https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/rocm_sdk_libraries_custom-7.2.1-py3-none-win_amd64.whl https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/rocm-7.2.1.tar.gz
```
```bash
.venv\Scripts\python.exe -m pip install --no-cache-dir https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/torch-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/torchaudio-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/torchvision-0.24.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl
```

**NVIDIA (CUDA):**

```bash
.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
```

**Só CPU:**

```bash
.venv\Scripts\python.exe -m pip install torch torchvision
```

Confira (deve imprimir `True` e o nome da placa; na AMD o PyTorch também usa a API `torch.cuda`):

```bash
.venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"
```

### 7. Outras dependências

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 8. Caminhos do emulador e da ROM

Copie `config.example.json` para `config.json` (fica fora do git) e ajuste:

```json
{
  "mupen_exe": "C:/Emuladores/Mupen/mupen64.exe",
  "rom": "C:/Emuladores/ROMs/Mario Kart 64 (USA).n64"
}
```

(Ou use as variáveis de ambiente `NK_MUPEN_EXE` e `NK_ROM`.)

### 9. Testar

Todos os comandos rodam dentro da pasta do projeto, com o Python do ambiente virtual; o Mupen abre e
fecha sozinho. Colete uma corrida curta com o especialista (deve abrir o jogo e o kart sair
dirigindo; grava um arquivo em `data/LR/TT/`):

```bash
.venv\Scripts\python.exe -m nk.collect --states states\TT\LR.st --max-seconds 20
```

Os savestates de largada das 16 pistas já vêm em `states/TT/`. Se não carregarem (por exemplo, com
outra versão da ROM), recrie-os (~1 min por pista):

```bash
.venv\Scripts\python.exe -m nk.make_state --mode TT --all
```

---

## Uso

O jeito mais simples é a **comparação completa numa pista**: corridas do especialista, DAgger dos
dois modelos a partir dos mesmos dados e teste de cada iteração jogando sozinha. Tudo é anotado em
`results/races.csv`:

```bash
.venv\Scripts\python.exe -m nk.compare MMF                # ~5-8 h; --shutdown desliga o PC no fim
.venv\Scripts\python.exe -m nk.report                     # atualiza results/README.md e o gráfico
```

Ou passo a passo:

```bash
# coletar com o especialista (6 emuladores em paralelo, 1 corrida cada)
.venv\Scripts\python.exe -m nk.collect --states states\TT\LR.st --workers 6 --episodes 1

# treinar (transformer é o padrão; --arch pilotnet para a CNN)
.venv\Scripts\python.exe -m nk.train --out runs\lr\it0 --epochs 30

# DAgger a partir da iteração 0 já treinada (coleta com a rede dirigindo + retreino)
.venv\Scripts\python.exe -m nk.dagger --name lr --start 1 --iterations 4 --workers 6 --states states\TT\LR.st

# ver a rede jogar (abre o jogo na tela)
.venv\Scripts\python.exe -m nk.play --policy runs\lr\it3\model.pt --state states\TT\LR.st --episodes 3
```

| Comando | Opção | Para quê |
|---|---|---|
| `collect` | `--workers N` | emuladores em paralelo (até ~1 por núcleo livre da CPU) |
| `collect` | `--states ...` | savestates de largada; sem a opção, alterna entre todos de `states/TT` |
| `collect` | `--policy X --beta B` | DAgger: a rede dirige com prob. 1-B e o especialista anota |
| `collect` | `--max-seconds S` | encerra cada corrida depois de S segundos de jogo |
| `train` | `--arch pilotnet` | usa a CNN em vez do transformer |
| `train` / `dagger` | `--init X` / `--start N` | continua de um checkpoint / de uma iteração |
| `play` | `--greedy` | usa a direção mais provável em vez da média ponderada |
| `play` | `--record` | anota cada corrida em `results/races.csv` |
| `make_state` | `--course LR MMF` | cria largadas só dessas pistas |

Cada treino salva em `runs/<nome>/`: `model.pt` (melhor validação), `last.pt` (última época) e
`log.jsonl` (métricas). `data/` e `runs/` ficam fora do git. O especialista domina o tempo: ~2 s por
decisão, 10 decisões por segundo de jogo.

---

## Como funciona

```
 Python (nk/)                                         Mupen64 (1 ou vários em paralelo)
 ┌────────────────────────────────┐   named pipes    ┌───────────────────────────┐
 │ collect / play / make_state    │ ── comandos ───▶ │ lua/agent.lua             │
 │   RaceEnv, SearchExpert        │ ◀─ estado ────── │   RUN, SAVE/LOAD, SPEED,  │
 │   Emulator ─ WindowCapture ────┼── imagem (WGC) ──│   STATE, LOADFILE ...     │
 │ train (PyTorch na GPU)         │                  └───────────────────────────┘
 └────────────────────────────────┘
```

1. **O Python abre o Mupen** (`nk/emulator.py`) com a ROM e o script `lua/agent.lua`. Cada emulador
   tem seu próprio par de named pipes, então dá para rodar vários ao mesmo tempo.
2. **O Lua é só um controle remoto**: executa um comando (rodar N frames com um input,
   salvar/carregar estado, mudar velocidade) e responde com o estado do jogo lido da memória
   (progresso, velocidade, posição, cronômetro). Enquanto espera, o jogo fica parado: Python e jogo
   andam em *lockstep* e tudo é determinístico.
3. **A imagem vem da janela**, capturada com Windows Graphics Capture (`nk/capture.py`) e reduzida
   para 128×96.
4. **O ambiente** (`nk/env.py`) carrega uma largada e, a cada 3 frames (10 decisões por segundo),
   aplica a direção escolhida, sempre acelerando. A corrida acaba ao completar 3 voltas, se o kart
   ficar 10 s sem avançar ("preso") ou depois de 5 minutos.
5. **O especialista** (`nk/expert.py`) testa as 11 direções (de -1 a +1) a partir do estado atual,
   em UltraFastForward: cada uma vira por 15 frames e depois vai reto por 30. A nota é progresso +
   0,1 × velocidade (quem não avança leva nota muito baixa).
6. **A coleta** (`nk/collect.py`) grava, a cada decisão, a imagem, a direção executada, as notas das
   11 direções e a telemetria (`data/<pista>/<modo>/*.npz`), com perturbações aleatórias ocasionais
   para variar os estados.
7. **O treino** (`nk/train.py`) põe todos os episódios na memória da GPU e treina a rede para
   reproduzir o especialista, com aumento de dados e validação separada por corrida.
8. **O DAgger** (`nk/dagger.py`) repete coleta e treino com **a rede dirigindo** (prob. 1-β, com
   β = 0,5, 0,25, 0,125) e o especialista anotando a resposta certa em cada passo. Assim a rede
   aprende a sair das situações em que ela mesma se mete. Se ela fica 3 s sem avançar, o especialista
   assume por 2 s para a coleta cobrir a pista inteira.

### Modelos (`nk/model.py`)

| | **transformer** (padrão) | **pilotnet** |
|---|---|---|
| Entrada | os últimos 16 frames (1,6 s) | 1 frame, redimensionado para 200×66 |
| Arquitetura | stem convolucional → 48 tokens por frame → transformer espacial (token CLS) → transformer temporal causal | BatchNorm + 5 convoluções (24, 36, 48 de 5×5/2; 64, 64 de 3×3) + densas 1164-100-50-10, dropout 0,4 |
| Saída | probabilidade de cada uma das 11 direções (usa a média; a mais provável com `--greedy`) | 1 valor com softsign (direção em [-1, 1]) |
| Perda | entropia cruzada contra **alvos suaves** (softmax das notas do especialista) | perda "euclidiana" contra a melhor direção do especialista |
| Parâmetros | 3,0 M | 1,6 M |

### Pistas

`states/TT/<pista>.st` são as largadas das 16 pistas em **Time Trial** (sem adversários nem itens),
criadas por `nk/make_state.py`, que navega os menus e confere a pista pela memória. Siglas: LR, MMF,
KTB, KD (Mushroom) · TT, FS, CM, MR (Flower) · WS, SL, RRy, BC (Star) · DK, YV, BB, RRd (Special).

### Estrutura

```
lua/        agent.lua (controle remoto), mk.lua (corrotina + savestates), ipc.lua (pipes)
nk/         emulator, capture, pipes, game, env, expert, data, model, results, paths
            comandos: collect, train, dagger, play, compare, report, make_state
states/     largadas (.st)
results/    races.csv (todas as corridas) e o relatório gerado
```

---

## Resultados

**Todos os resultados ficam em [`results/`](results/)**: [`races.csv`](results/races.csv) tem uma
linha por corrida (avaliações das redes e corridas do especialista, desde o primeiro teste; o GitHub
mostra como tabela pesquisável), e [`results/README.md`](results/README.md) traz as tabelas por pista
e o gráfico abaixo, **gerados a partir do CSV** por `nk.report`.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="results/times-dark.png">
  <img alt="Tempo médio por iteração em cada pista, PilotNet e Transformer, com a faixa de tempo do especialista" src="results/times-light.png">
</picture>

Protocolo (`nk.compare`): 6 corridas do especialista; para cada modelo, 3 iterações de DAgger a
partir dos mesmos dados (6 corridas por iteração); cada iteração testada jogando sozinha 3 vezes.

**Conclusões até agora** (Luigi Raceway, Choco Mountain e Moo Moo Farm):

- **Nenhum modelo vence sempre.** Depois do DAgger, o transformer é ~2,8 s mais rápido na Choco
  Mountain, a PilotNet ~2 s mais rápida na Moo Moo Farm, e empatam na Luigi Raceway. Os dois
  terminam no nível do especialista ou abaixo dele.
- **Só imitação é instável** (o transformer completou em 2 de 3 pistas, a PilotNet em 1 de 3);
  **uma iteração de DAgger bastou** para os dois completarem todas as corridas.
- A **PilotNet é bem mais barata**: treina ~10x mais rápido e decide em ~2 ms (transformer ~5 ms).
- A **Mario Raceway** ficou sem comparação: o especialista sai da pista e para de frente para muros,
  e sem marcha a ré não consegue sair.

**Bug do frame extra (corrigido):** nas primeiras coletas, cada savestate salvo para o especialista
fazia o jogo andar 1 frame sem nenhum botão. Os dados ficavam num ritmo de jogo mais lento que o do
`play`, e as redes treinadas assim travavam numa curva fechada. Esses resultados aparecem como
`dados = v1` no CSV; a correção (`RUN ... SAVE slot`, que salva no último frame do comando) gerou os
dados `v2`.

---

## TO DO

- [ ] **Testar todas as pistas** (faltam 13 das 16).
  - [ ] Marcha a ré / freio nas ações, para pistas com muros perto da estrada (Mario Raceway).
  - [ ] Um modelo treinado em várias pistas, testado em pistas que ele não viu.
- [ ] **Implementar novos modelos.** Basta criar a classe em `nk/model.py` e registrá-la em
  `ARCHITECTURES`; falta generalizar `nk/train.py` e `nk/dagger.py`, que ainda escolhem entre
  "pilotnet" e "transformer" de forma fixa.
- [ ] **Diminuir o tempo de execução?** Uma comparação leva ~5-8 h, quase todo no especialista.
  Ideias: avaliar as direções em paralelo ou usar menos direções, horizonte de busca menor, decidir
  a cada mais frames na coleta, menos épocas no ajuste fino do transformer.
- [ ] **Implementar aprendizado por reforço (RL):** PPO partindo da rede imitada, com recompensa de
  progresso na pista e penalidade de KL para não se afastar demais dela no começo.

---

## Solução de problemas

| Sintoma | Causa e solução |
|---|---|
| "An error has occured" no Mupen, ou pista preta | Plugin TAS Video em uso: selecione o **GLideN64** (Instalação, passo 4) |
| Mupen fecha ao abrir o jogo com o GLideN64 | Build errada: use a **PJ64Legacy-WTL-x64** (passo 3) |
| Janela de atualização em cada emulador | Desligue a verificação de atualizações (passo 4) |
| Diálogo "Video Unknown Microcode" | Só com o TAS Video (escolha F3DEX); o GLideN64 não pergunta |
| "Failed to load ... .st" | Savestate de outra versão da ROM: recrie com `nk.make_state` (passo 9) |
| `Mupen não encontrado` / `ROM não encontrada` | Ajuste o `config.json` (passo 8) |
| "o agent.lua não conectou" | O Mupen não abriu o script: confira se outra cópia do Mupen está parada num diálogo |
| `miopenStatusUnknownError` / `'type_traits' file not found` (AMD) | Bug do MIOpen no ROCm para Windows; a PilotNet já usa o BatchNorm nativo do PyTorch para evitá-lo |
| Aviso `offload-arch.exe ... Unknown command line argument` (AMD) | Inofensivo; acontece quando o caminho do projeto tem espaços |
| Acentos estranhos no terminal (`Ã©`) | Só exibição: `chcp 65001` ou `PYTHONIOENCODING=utf-8` |
| Resultados variam um pouco entre execuções | A captura de tela não é sincronizada ao frame exato |

**Notas técnicas do Mupen 1.5** (para quem mexer no código):

- A API Lua trava se chamada de dentro de uma corrotina; `lua/mk.lua` repassa as chamadas para o
  thread principal.
- Nenhuma função Lua devolve a imagem do jogo, e `PrintWindow` trava (o Lua bloqueia a thread de
  interface do Mupen enquanto espera o Python); por isso a captura usa Windows Graphics Capture.
- Um `SAVE` avulso faz o jogo andar 1 frame; para salvar sem alterar o ritmo use `RUN ... SAVE slot`.
- O Mupen bloqueia `os.execute` fora do "Trusted Mode", e caminhos passados a ele precisam ser
  absolutos (ele roda na própria pasta).
- O MK64 lê o controle a **30 Hz**; todos os "frames" aqui são input frames.
