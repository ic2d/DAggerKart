"""Especialista por busca: a partir do estado atual, testa cada direção de STEER_BINS (segura por
`steer_frames` e depois vai reto por `forward_frames`) usando savestates em UltraFastForward, e dá
uma nota para cada uma. É o "professor" que a rede imita.

Diferente do SearchAI original, devolve a nota de todas as ações (não só a melhor): o treino usa
isso como alvo suave.
"""
import numpy as np

from . import game
from .emulator import SPEED_NORMAL, SPEED_ULTRA

ROOT_SLOT = "expert_root"


class SearchExpert:
    def __init__(self, emu, bins=game.STEER_BINS, steer_frames=15, forward_frames=30,
                 velocity_weight=0.1):
        self.emu, self.bins = emu, bins
        self.steer_frames, self.forward_frames = steer_frames, forward_frames
        self.velocity_weight = velocity_weight

    def scores(self, root_saved=False):
        """Nota de cada ação em `bins`. Deixa o emulador exatamente no estado em que estava.

        O estado atual precisa estar salvo em ROOT_SLOT pelo último comando (env.step(..., save=ROOT_SLOT)),
        porque um SAVE avulso faria o jogo andar 1 frame a mais. Sem isso (`root_saved=False`) ele
        salva mesmo assim, mas o jogo avança 1 frame (com o último input) antes da busca."""
        emu = self.emu
        start = emu.state()
        if not root_saved:
            emu.save(ROOT_SLOT)
        emu.speed(SPEED_ULTRA)
        scores = np.empty(len(self.bins), np.float32)
        for i, steer in enumerate(self.bins):
            emu.load(ROOT_SLOT)
            end = emu.run([(self.steer_frames, game.A, game.steer_to_joystick(steer), 0),
                           (self.forward_frames, game.A, 0, 0)])
            if end.progress > start.progress:
                scores[i] = end.progress + self.velocity_weight * end.velocity
            else:  # não avançou (bateu, ficou preso ou andou para trás)
                scores[i] = end.progress - game.LAPS
        emu.load(ROOT_SLOT)
        emu.speed(SPEED_NORMAL)
        return scores

    def best(self, scores):
        """Melhor ação; em empate, a de menor |steer| (dirigir mais reto)."""
        top = np.flatnonzero(scores >= scores.max() - 1e-9)
        return float(self.bins[top[np.argmin(np.abs(self.bins[top]))]])
