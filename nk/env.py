"""Ambiente de corrida: o agente decide a direção a cada `decision_frames` frames e sempre acelera.

    env = RaceEnv(emu)
    obs = env.reset(STATES_DIR / "GP" / "LR.st")
    while not env.done:
        obs = env.step(steer)
"""
from dataclasses import dataclass

import numpy as np

from . import game
from .emulator import SPEED_NORMAL


@dataclass
class Observation:
    frame: np.ndarray       # (H, W, 3) uint8 RGB
    state: game.GameState


class RaceEnv:
    def __init__(self, emu, decision_frames=3, stuck_seconds=10.0, max_seconds=300.0):
        self.emu = emu
        self.decision_frames = decision_frames
        self.stuck_steps = int(stuck_seconds * game.FPS / decision_frames)
        self.max_steps = int(max_seconds * game.FPS / decision_frames)
        self.done, self.reason = False, None

    def reset(self, state_file, warmup_frames=2):
        self.emu.speed(SPEED_NORMAL)
        self.emu.load_file(state_file)
        # Alguns frames em velocidade normal para a janela mostrar o estado carregado.
        state = self.emu.run([(warmup_frames, game.A, 0, 0)])
        self.steps, self.best_progress, self.best_step = 0, state.progress, 0
        self.done, self.reason = False, None
        self.obs = Observation(self.emu.frame(), state)
        return self.obs

    def step(self, steer):
        self.emu.speed(SPEED_NORMAL)
        state = self.emu.run([(self.decision_frames, game.A, game.steer_to_joystick(steer), 0)])
        self.steps += 1
        if state.progress > self.best_progress + 1e-3:
            self.best_progress, self.best_step = state.progress, self.steps
        if state.finished:
            self.done, self.reason = True, "finished"
        elif self.steps - self.best_step > self.stuck_steps:
            self.done, self.reason = True, "stuck"
        elif self.steps >= self.max_steps:
            self.done, self.reason = True, "timeout"
        self.obs = Observation(self.emu.frame(), state)
        return self.obs
