"""Constantes do Mario Kart 64 e do controle."""
from dataclasses import dataclass

import numpy as np

COURSES = ["MR", "CM", "BC", "BB", "YV", "FS", "KTB", "RRy", "LR", "MMF", "TT", "KD", "SL", "RRd", "WS",
           "BF", "SS", "DD", "DK", "BD", "TC"]
COURSE_NAMES = ["Mario Raceway", "Choco Mountain", "Bowser's Castle", "Banshee Boardwalk", "Yoshi Valley",
                "Frappe Snowland", "Koopa Troopa Beach", "Royal Raceway", "Luigi Raceway", "Moo Moo Farm",
                "Toad's Turnpike", "Kalimari Desert", "Sherbet Land", "Rainbow Road", "Wario Stadium",
                "Block Fort", "Skyscraper", "Double Deck", "D.K.'s Jungle Parkway", "Big Donut", "TC"]
MODES = ["GP", "TT", "VS", "BT"]

# Máscara de botões do agent.lua (mesma ordem de BUTTONS lá).
A, B, Z, R, L, START, C_UP, C_DOWN, C_LEFT, C_RIGHT, D_UP, D_DOWN, D_LEFT, D_RIGHT = (1 << i for i in range(14))

LAPS = 3
FPS = 30  # o MK64 lê o controle a 30 Hz (input frames)

# Ações de direção: steer em [-1, 1], discretizado. O especialista escolhe entre esses valores e a
# rede classifica entre eles.
STEER_BINS = np.linspace(-1.0, 1.0, 11).astype(np.float32)


def steer_to_joystick(steer):
    """Steer [-1, 1] -> eixo X do analógico (-128..127), com o remapeamento não linear do NeuralKart
    original (a resposta do kart ao analógico não é linear). 0 continua 0."""
    steer = float(np.clip(steer, -1.0, 1.0))
    if steer == 0.0:
        return 0
    mapped = np.sign(steer) * np.sqrt(abs(steer) * 0.24 + 0.01)
    return int(np.floor(-128 + (mapped + 1) / 2 * 255))


@dataclass
class GameState:
    progress: float     # voltas completadas (0..3, fracionário); a corrida acaba em 3
    velocity: float
    x: float
    y: float
    z: float
    timer: float        # tempo de corrida (s)
    course: int
    mode: int
    input_frame: int
    vi_frame: int

    FIELDS = 10

    @classmethod
    def parse(cls, text):
        v = text.split()
        return cls(float(v[0]), float(v[1]), float(v[2]), float(v[3]), float(v[4]), float(v[5]),
                   int(v[6]), int(v[7]), int(v[8]), int(v[9]))

    @property
    def course_code(self):
        return COURSES[self.course] if self.course < len(COURSES) else str(self.course)

    @property
    def mode_code(self):
        return MODES[self.mode] if self.mode < len(MODES) else str(self.mode)

    @property
    def finished(self):
        return self.progress >= LAPS

    def vector(self):
        return np.array([self.progress, self.velocity, self.x, self.y, self.z, self.timer], np.float32)
