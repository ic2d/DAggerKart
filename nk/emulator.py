"""Controle do Mupen64 a partir do Python.

    with Emulator() as emu:
        emu.load_file(STATES_DIR / "GP" / "LR.st")
        st = emu.run([(30, game.A, 0, 0)])     # acelera reto por 30 frames
        img = emu.frame()                       # imagem atual do jogo

O emulador é aberto com lua/agent.lua, que executa um comando por vez; enquanto ele espera, o jogo
fica parado (lockstep). Vários emuladores podem rodar em paralelo, cada um com o seu pipe.
"""
import os
import subprocess
import time
import uuid
from pathlib import Path

from . import capture, paths
from .game import GameState

SPEED_NORMAL, SPEED_FAST, SPEED_ULTRA = 0, 1, 2

FRAME_SIZE = (128, 96)  # (largura, altura) das imagens entregues por frame()


class EmulatorError(RuntimeError):
    pass


class Emulator:
    def __init__(self, rom=paths.ROM, exe=paths.MUPEN_EXE, frame_size=FRAME_SIZE, start_timeout=60):
        self.rom, self.exe, self.frame_size = rom, exe, frame_size
        self.start_timeout = start_timeout
        self.proc = self.pipe = self.cap = None
        self._speed = None

    # ---------- ciclo de vida ----------

    def start(self):
        from .pipes import PipeServer
        if self.exe == paths.MUPEN_EXE and self.rom == paths.ROM:
            paths.check()
        name = "nk-" + uuid.uuid4().hex[:8]
        self.pipe = PipeServer(name)
        env = dict(os.environ, NK_PIPE=name)
        args = [str(self.exe), "--rom", str(self.rom), "--lua", str(paths.AGENT_LUA)]
        self.proc = subprocess.Popen(args, cwd=str(self.exe.parent), env=env)
        try:
            self.pipe.accept(self.start_timeout)
            hello = self.pipe.readline()
            if not hello.startswith("HELLO"):
                raise EmulatorError("resposta inesperada do agent.lua: " + hello)
            self._wait_window()
        except BaseException:
            self.close()
            raise
        self._speed = None
        return self

    def _wait_window(self):
        deadline = time.time() + self.start_timeout
        while time.time() < deadline:
            hwnd = capture.find_game_window(self.proc.pid)
            if hwnd:
                self.cap = capture.WindowCapture(hwnd)
                return
            time.sleep(0.2)
        raise EmulatorError("a janela do jogo não apareceu")

    def close(self):
        if self.pipe is not None:
            try:
                if self.pipe.writer is not None:
                    self.pipe.request("QUIT")
            except Exception:
                pass
            self.pipe.close()
            self.pipe = None
        if self.cap is not None:
            self.cap.close()
            self.cap = None
        if self.proc is not None:
            # Mata o processo em vez de fechar: o Mupen pode abrir diálogos ao sair e salvaria a config.
            if self.proc.poll() is None:
                self.proc.kill()
                self.proc.wait(10)
            self.proc = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.close()

    # ---------- comandos ----------

    def command(self, line):
        reply = self.pipe.request(line)
        if reply.startswith("ERR"):
            raise EmulatorError(reply[4:])
        return reply[3:] if reply.startswith("OK ") else ""

    def state(self):
        return GameState.parse(self.command("STATE"))

    def run(self, segments, save=None):
        """Executa uma sequência de inputs: [(frames, buttons, x, y), ...]. Retorna o estado no fim.
        `save` = slot para salvar o estado no último frame. Use isso em vez de save(): um SAVE avulso
        faz o jogo andar 1 frame a mais, o que muda o ritmo do jogo."""
        parts = []
        for n, buttons, x, y in segments:
            if n > 0:
                parts.append("%d %d %d %d" % (n, buttons, x, y))
        if not parts:
            return self.state()
        if save:
            parts.append("SAVE " + save)
        return GameState.parse(self.command("RUN " + " ".join(parts)))

    def speed(self, mode):
        if mode != self._speed:
            self.command("SPEED %d" % mode)
            self._speed = mode

    def save(self, slot):
        self.command("SAVE " + slot)

    def load(self, slot):
        self.command("LOAD " + slot)

    def free(self, slot):
        self.command("FREE " + slot)

    # Caminhos sempre absolutos: o Mupen roda com a pasta dele como diretório atual.
    def save_file(self, path):
        self.command("SAVEFILE " + str(Path(path).resolve()))

    def load_file(self, path):
        path = Path(path).resolve()
        if not path.is_file():  # o Mupen mostraria um diálogo de erro e ficaria parado nele
            raise FileNotFoundError(path)
        self.command("LOADFILE " + str(path))

    def frame(self):
        """Imagem RGB atual do jogo, (altura, largura, 3) uint8. Só é atual se os últimos frames
        rodaram em SPEED_NORMAL (em fast/ultra o Mupen pula a renderização)."""
        return self.cap.grab(self.frame_size)
