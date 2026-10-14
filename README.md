# NeuralKart

IA que joga **Mario Kart 64** no emulador **Mupen64-rr-lua**. Uma rede neural olha a tela e decide
a direção do kart. Ela aprende imitando um **especialista de busca**, que testa cada direção possível
usando savestates e escolhe a melhor, e depois é refinada com **DAgger**.

Dois modelos estão disponíveis: um **transformer** espaço-temporal (padrão) e a **PilotNet**, a CNN
da NVIDIA usada no projeto original.

> **Plataforma:** só Windows 10 (1903+) ou 11, 64 bits. O Mupen64-rr-lua é Windows-only e a captura
> de tela usa a API Windows Graphics Capture.

---

## Sumário

1. [Tutorial: do zero até a IA jogando](#tutorial-do-zero-até-a-ia-jogando)
2. [Comandos](#comandos)
3. [Como tudo funciona](#como-tudo-funciona)
4. [Resultados](#resultados)
5. [Solução de problemas](#solução-de-problemas)

---

## Tutorial: do zero até a IA jogando

### O que você precisa ter

| | |
|---|---|
| Sistema | Windows 10 (versão 1903 ou mais nova) ou Windows 11, 64 bits |
| GPU (recomendado) | AMD Radeon RX 6000/7000/9000 com ROCm, ou NVIDIA com CUDA. Sem GPU funciona, mas o treino fica lento |
| Espaço em disco | ~3 GB (Python + PyTorch) + ~35 MB por corrida coletada |
| ROM | Uma cópia sua de **Mario Kart 64 (USA)** (`.n64`, `.z64` ou `.v64`). **A ROM não vem com o projeto** |

### Passo 1 — Baixar o projeto

Instale o [Git para Windows](https://git-scm.com/download/win) e clone o repositório:

```bash
git clone <url-deste-repositório> NeuralKart
cd NeuralKart
```

### Passo 2 — Baixar o emulador (Mupen64-rr-lua 1.5)

1. Baixe o pacote x64 em <https://mupen64.com>, botão *Download 64-bit for Windows*
   (link direto: <https://github.com/mupen64/repack/archive/refs/heads/stable-windows-x64.zip>).
2. Extraia numa pasta qualquer, por exemplo `C:\Emuladores\Mupen`. Dentro dela deve existir
   `mupen64.exe`.

### Passo 3 — Baixar o plugin de vídeo GLideN64

O plugin de vídeo que vem embutido no Mupen 1.5 (TAS Video) **trava com o Mario Kart** em
fast-forward e depois de muitos savestates, que é exatamente o que o projeto faz. Use o GLideN64:

1. Abra <https://github.com/gonetz/GLideN64/releases/tag/github-actions>.
2. Baixe **`GLideN64-...-Windows-PJ64Legacy-WTL-x64.zip`**.
   - Precisa ser a build **PJ64Legacy** e **x64**. A build "Project64" trava ao abrir o jogo no
     Mupen, que usa a versão antiga da especificação de plugins.
3. Extraia `GLideN64.dll` e `GLideN64.custom.ini` para a pasta `plugin` do Mupen
   (`C:\Emuladores\Mupen\plugin\`; crie a pasta se não existir).

### Passo 4 — Configurar o Mupen

1. Abra o `mupen64.exe`.
2. Vá em **Options > Settings > Plugins** e escolha **GLideN64** em *Video*. Deixe Audio, Input e
   RSP nos plugins padrão ("TAS ...").
3. Abra a ROM (*File > Load ROM*) e confira se o jogo aparece. Feche o Mupen normalmente, para ele
   salvar a configuração.

### Passo 5 — Instalar o Python 3.12

O PyTorch com ROCm para Windows só existe para Python **3.12**, então use essa versão mesmo que
você tenha outra instalada (elas convivem sem problema).

- Pelo [gerenciador de instalação do Python](https://www.python.org/downloads/windows/):
  ```bash
  py install 3.12
  ```
- Ou baixe o instalador do 3.12 em <https://www.python.org/downloads/release/python-31210/>.

Crie o ambiente virtual dentro da pasta do projeto:

```bash
py -V:3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
```

### Passo 6 — Instalar o PyTorch (escolha conforme a sua GPU)

**AMD (ROCm para Windows).** Precisa do driver AMD Adrenalin **26.2.2 ou mais novo**. Comandos do
[guia oficial da AMD](https://rocm.docs.amd.com/projects/radeon-ryzen/en/latest/docs/install/installrad/windows/install-pytorch.html)
(versões de quando o projeto foi feito; confira no guia se há mais novas):

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

**Sem GPU (só CPU):**

```bash
.venv\Scripts\python.exe -m pip install torch torchvision
```

Confira se a GPU foi reconhecida (deve imprimir `True` e o nome da placa; com CPU imprime `False`):

```bash
.venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"
```

> Na AMD o PyTorch também usa a API "cuda" (`torch.cuda`), então o código é o mesmo para as duas.

### Passo 7 — Instalar as outras dependências

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Passo 8 — Dizer ao projeto onde estão o emulador e a ROM

Copie `config.example.json` para `config.json` (esse arquivo não vai para o git) e ajuste os
caminhos:

```json
{
  "mupen_exe": "C:/Emuladores/Mupen/mupen64.exe",
  "rom": "C:/Emuladores/ROMs/Mario Kart 64 (USA).n64"
}
```

Alternativa: variáveis de ambiente `NK_MUPEN_EXE` e `NK_ROM`.

### Passo 9 — Testar

Daqui em diante, todos os comandos rodam **dentro da pasta do projeto**, com o Python do ambiente
virtual. O Mupen abre e fecha sozinho; não precisa abrir manualmente.

1. Os savestates de largada das 16 pistas já vêm em `states/TT/`. Se eles não carregarem (por
   exemplo, com uma ROM de versão diferente), recrie-os, o que leva ~1 min por pista:
   ```bash
   .venv\Scripts\python.exe -m nk.make_state --mode TT --all
   ```
2. Colete uma corrida curta com o especialista (deve abrir o jogo e o kart sair dirigindo):
   ```bash
   .venv\Scripts\python.exe -m nk.collect --states states\TT\LR.st --max-seconds 20
   ```
   Isso grava um arquivo em `data/LR/TT/`.

Se isso funcionou, está tudo pronto. Siga para [Comandos](#comandos).

---

## Comandos

```bash
# 1. coletar com o especialista (6 emuladores em paralelo, 1 corrida cada, só na Luigi Raceway)
.venv\Scripts\python.exe -m nk.collect --states states\TT\LR.st --workers 6 --episodes 1

# 2. treinar (transformer, o padrão, ou a CNN do projeto original)
.venv\Scripts\python.exe -m nk.train --out runs\lr_v1 --epochs 40
.venv\Scripts\python.exe -m nk.train --out runs\lr_pilot\it0 --arch pilotnet --epochs 30

# 3. ver a rede jogar (abre o jogo na tela)
.venv\Scripts\python.exe -m nk.play --policy runs\lr_v1\model.pt --state states\TT\LR.st --episodes 2

# DAgger: ciclos de coleta com a rede dirigindo + retreino (aqui continuando da iteração 0)
.venv\Scripts\python.exe -m nk.dagger --name lr_pilot --arch pilotnet --start 1 --iterations 4 --workers 6 --states states\TT\LR.st

# criar savestates de largada (Time Trial: qualquer pista; GP: 1ª pista de cada copa)
.venv\Scripts\python.exe -m nk.make_state --mode TT --course LR MMF
```

Opções úteis:

| Comando | Opção | Para quê |
|---|---|---|
| `collect` | `--workers N` | emuladores em paralelo (até ~1 por núcleo livre da CPU) |
| `collect` | `--states ...` | savestates de largada; sem a opção, alterna entre todos de `states/TT` |
| `collect` | `--policy X --beta B` | DAgger: a rede dirige com prob. 1-B e o especialista anota |
| `collect` | `--max-seconds S` | encerra cada corrida depois de S segundos de jogo |
| `train` | `--arch pilotnet` | usa a CNN original em vez do transformer |
| `train` | `--init X` | continua o treino a partir de um checkpoint |
| `play` | `--greedy` | usa a direção mais provável em vez da média ponderada |

Cada treino salva em `runs/<nome>/`: `model.pt` (melhor validação), `last.pt` (última época) e
`log.jsonl` (métricas por época). `data/` e `runs/` não vão para o git (são grandes).

**Tempo:** o especialista leva ~2 s por decisão (10 decisões por segundo de jogo), então uma corrida
de 3 voltas na Luigi Raceway (~1000 decisões) leva ~30-45 min por emulador. O treino é rápido: ~37 s
por época no transformer e ~3 s na PilotNet (RX 7600 XT).

---

## Como tudo funciona

### Visão geral

```
 Python (nk/)                                         Mupen64 (1 ou vários em paralelo)
 ┌────────────────────────────────┐   named pipes    ┌───────────────────────────┐
 │ collect / play / make_state    │ ── comandos ───▶ │ lua/agent.lua             │
 │   RaceEnv, SearchExpert        │ ◀─ estado ────── │   RUN, SAVE/LOAD, SPEED,  │
 │   Emulator ─ WindowCapture ────┼── imagem (WGC) ──│   STATE, LOADFILE ...     │
 │ train (PyTorch na GPU)         │                  └───────────────────────────┘
 └────────────────────────────────┘
```

1. **O Python abre o Mupen sozinho** (`nk/emulator.py`), passando a ROM e o script `lua/agent.lua`
   pela linha de comando. Cada emulador recebe um nome de pipe próprio (variável `NK_PIPE`), então
   dá para rodar vários ao mesmo tempo.
2. **O Lua é só um controle remoto.** O `agent.lua` espera um comando, executa e responde uma linha
   com o estado do jogo lido da memória (progresso na pista, velocidade, posição, cronômetro, pista,
   modo). Enquanto ele espera, o jogo fica parado: Python e jogo andam juntos, quadro a quadro
   (*lockstep*), e tudo é determinístico.
3. **A imagem vem da janela**, capturada pelo Python com Windows Graphics Capture (`nk/capture.py`)
   e reduzida para 128×96.
4. **O ambiente de corrida** (`nk/env.py`) carrega um savestate de largada e, a cada **3 frames
   (10 decisões por segundo)**, aplica a direção escolhida, sempre acelerando. O episódio acaba
   quando a corrida termina (3 voltas), quando o kart fica 10 s sem avançar ("preso") ou depois de
   5 minutos.
5. **O especialista** (`nk/expert.py`) salva o estado atual, testa as 11 direções possíveis (de -1
   a +1) em UltraFastForward, cada uma virando por 15 frames e depois indo reto por 30, e dá uma
   nota para cada (progresso + 0,1 × velocidade; quem não avança leva nota muito baixa). Depois volta
   ao estado salvo.
6. **A coleta** (`nk/collect.py`) grava, a cada decisão, a imagem, a direção executada, as notas
   das 11 direções e a telemetria. Para variar os dados, de vez em quando injeta uma direção
   aleatória por alguns passos. Cada corrida vira um `data/<pista>/<modo>/*.npz`.
7. **O treino** (`nk/train.py`) carrega todos os episódios direto na memória da GPU e treina a rede
   para reproduzir as escolhas do especialista, com aumento de dados (pequenos deslocamentos e
   brilho/contraste) e validação separada por corrida.
8. **O DAgger** (`nk/dagger.py`) repete coleta e treino, mas a partir da 2ª rodada **quem dirige é
   a rede** (com probabilidade 1-β, sendo β = 0,5, 0,25, 0,125...), enquanto o especialista anota a
   resposta certa em cada passo. Assim a rede aprende a sair de situações em que ela mesma se mete,
   que nunca aparecem quando só o especialista dirige. Se a rede fica 3 s sem avançar, o
   especialista assume por 2 s para tirar o kart dali, e a coleta cobre a pista inteira.
9. **Jogar** (`nk/play.py`): a rede dirige sozinha e o script mostra o resultado de cada corrida.

### Os modelos (`nk/model.py`)

Escolhidos com `--arch` no treino; o tipo fica salvo no checkpoint.

| | **transformer** (padrão) | **pilotnet** (CNN do projeto original) |
|---|---|---|
| Entrada | os últimos 16 frames (1,6 s) | 1 frame, redimensionado para 200×66 |
| Arquitetura | stem convolucional → 48 tokens por frame → transformer espacial (token CLS) → transformer temporal causal | BatchNorm + 5 convoluções (24, 36, 48 de 5×5/2; 64, 64 de 3×3) + densas 1164-100-50-10, dropout 0,4 |
| Saída | probabilidade de cada uma das 11 direções; usa a média (ou a mais provável, com `--greedy`) | 1 valor com softsign (direção em [-1, 1]) |
| Perda | entropia cruzada contra **alvos suaves** (softmax das notas do especialista) | perda "euclidiana" do original contra a melhor direção do especialista |
| Parâmetros | 3,0 M | 1,6 M |

O transformer temporal dá à rede noção de movimento e velocidade, que um frame isolado não tem. Os
alvos suaves ensinam também quais curvas são "quase tão boas" quanto a melhor.

### Pistas

`states/TT/<pista>.st` são as largadas das 16 pistas em **Time Trial** (sem adversários nem itens
aleatórios), criadas por `nk/make_state.py`, que navega os menus apertando botões e confere a pista
pela memória. `states/GP/LR.st` é a Luigi Raceway em Mario GP 50cc.

Siglas: LR, MMF, KTB, KD (Mushroom) · TT, FS, CM, MR (Flower) · WS, SL, RRy, BC (Star) ·
DK, YV, BB, RRd (Special).

### Arquivos

| | |
|---|---|
| `lua/agent.lua` | controle remoto (protocolo de comandos documentado no topo do arquivo) |
| `lua/mk.lua` | corrotina + proxy da API do Mupen, savestates |
| `lua/ipc.lua` | named pipes via `io.open` |
| `nk/paths.py` | caminhos (lê `config.json`) |
| `nk/emulator.py` | abre o Mupen e envia comandos |
| `nk/capture.py` | captura da janela (Windows Graphics Capture) |
| `nk/pipes.py` | servidor de named pipes |
| `nk/game.py` | constantes do jogo, botões, conversão direção → analógico, `GameState` |
| `nk/env.py` | ambiente de corrida |
| `nk/expert.py` | especialista por busca |
| `nk/data.py` | formato dos episódios e carregador de sequências |
| `nk/model.py` | transformer, PilotNet e `PolicyRunner` (uso em tempo real) |
| `nk/collect.py`, `train.py`, `play.py`, `dagger.py`, `make_state.py` | comandos |

---

## Resultados

Todos na Luigi Raceway, Time Trial.

**Imitação pura (13/10/2026):** 6 corridas do especialista (~6000 decisões); 5 completaram as 3
voltas em 132-137 s de jogo.

| Modelo | Erro médio de direção (validação) | Jogando sozinho |
|---|---|---|
| transformer (melhor época) | 0,087 | preso em ~0,51-0,55 volta; numa tentativa chegou a 2,59 voltas |
| transformer (última época, com e sem `--greedy`) | 0,089 | preso em ~0,51-0,54 volta |
| pilotnet | 0,143 | preso em ~0,45-0,47 volta |

Nas curvas fechadas o especialista pede direção total (+1,0) e a rede vira bem menos (~+0,1), bate
na parede e fica raspando nela, porque nunca viu essa situação nos dados. É o problema clássico da
imitação pura, que o DAgger ataca.

**DAgger com a PilotNet (14/10/2026):** 3 iterações a partir da PilotNet acima, 6 corridas por
iteração, com a rede dirigindo 50%, 75% e 87,5% do tempo (`runs/lr_pilot/it1..it3`). Total: 24
corridas, ~24 mil decisões anotadas.

| Iteração | Corridas completas na coleta | Erro de validação | Jogando sozinha |
|---|---|---|---|
| it0 (só imitação) | 5/6 (especialista dirigindo) | 0,143 | presa em ~0,46 volta |
| it1 (rede 50%) | 4/6 | 0,124 | presa em ~0,52 volta |
| it2 (rede 75%) | 4/6 | 0,112 | — |
| it3 (rede 87,5%) | 5/6, sem nenhum resgate | 0,114 | **3/3 corridas completas, 125,15 s** |

**A rede final completa a corrida sozinha e é mais rápida que o próprio especialista** (132-137 s):
o especialista só testa ações curtas e às vezes hesita, enquanto a rede aprendeu um traçado mais
limpo.

```bash
.venv\Scripts\python.exe -m nk.play --policy runs\lr_pilot\it3\model.pt --state states\TT\LR.st --episodes 3
```

As corridas que ficaram presas durante a coleta pararam sempre no mesmo ponto (0,52 de uma volta):
de frente para a parede, nem o especialista consegue sair, porque nenhuma das ações dá ré.

**Próximos passos:** incluir ré/freio nas ações (o kart preso de frente para a parede não tem como
sair só acelerando); ajuste fino por aprendizado por reforço (PPO) a partir da rede imitada, com
recompensa de progresso na pista; treinar em várias pistas.

---

## Solução de problemas

| Sintoma | Causa e solução |
|---|---|
| Mupen mostra "An error has occured" e trava, ou a pista fica preta | Está usando o plugin TAS Video. Selecione o **GLideN64** (Passo 4) |
| Mupen fecha logo ao abrir o jogo com o GLideN64 | Build errada: use a **PJ64Legacy-WTL-x64** (Passo 3) |
| Diálogo "Video Unknown Microcode" | Só aparece com o TAS Video; com ele escolha F3DEX. O GLideN64 não pergunta |
| "Failed to load ... .st" | Savestate de outra versão da ROM: recrie com `nk.make_state` (Passo 9) |
| `FileNotFoundError: Mupen não encontrado` / `ROM não encontrada` | Ajuste o `config.json` (Passo 8) |
| "o agent.lua não conectou" | O Mupen não abriu o script: confira se o caminho do projeto existe e se outra cópia do Mupen está travada num diálogo |
| `miopenStatusUnknownError` / `'type_traits' file not found` (AMD) | Bug do MIOpen no ROCm para Windows; a PilotNet já usa o BatchNorm nativo do PyTorch. Se aparecer em outra camada, me avise |
| Aviso `offload-arch.exe ... Unknown command line argument` (AMD) | Inofensivo; acontece quando o caminho do projeto tem espaços |
| Acentos estranhos no terminal (`Ã©`) | Só exibição: rode `chcp 65001` antes ou defina `PYTHONIOENCODING=utf-8` |
| Os resultados variam entre execuções | A captura de tela não é sincronizada ao frame exato; a rede pode ver um frame de diferença |

### Detalhes técnicos do Mupen 1.5 (para quem for mexer no código)

- A API Lua do Mupen trava se chamada de dentro de uma corrotina (ele identifica o script pelo
  `lua_State`); `lua/mk.lua` repassa as chamadas para o thread principal.
- Nenhuma função Lua devolve a imagem do jogo (`emu.screenshot` depende do plugin; `wgui.loadscreen`
  usa GDI e não pega OpenGL); `PrintWindow` também não serve, porque o Lua bloqueia a thread de
  interface do Mupen enquanto espera o Python. Por isso a captura usa Windows Graphics Capture.
- O Mupen bloqueia `os.execute` fora do "Trusted Mode"; nada no Lua precisa dele.
- Caminhos passados ao Mupen precisam ser absolutos (ele roda na pasta dele); `Emulator.load_file`
  já converte e confere se o arquivo existe.
- O MK64 lê o controle a **30 Hz**; todos os "frames" aqui são input frames.
