"""Cria savestates de largada navegando pelos menus do jogo (a partir do boot).

  python -m nk.make_state --mode TT --course LR MMF KTB     # Time Trial (qualquer pista)
  python -m nk.make_state --mode TT --all                   # as 16 pistas de corrida
  python -m nk.make_state --mode GP --course LR             # Mario GP 50cc (primeira pista de cada copa)

Salva em states/<modo>/<pista>.st, no primeiro frame em que o cronômetro da corrida anda.
Time Trial é o melhor modo para treinar: sem adversários e sem itens aleatórios.
"""
import argparse

from . import game, paths
from .emulator import Emulator, SPEED_FAST, SPEED_NORMAL

CUPS = [["LR", "MMF", "KTB", "KD"],      # Mushroom
        ["TT", "FS", "CM", "MR"],        # Flower
        ["WS", "SL", "RRy", "BC"],       # Star
        ["DK", "YV", "BB", "RRd"]]       # Special
RACE_COURSES = [c for cup in CUPS for c in cup]


def locate(course):
    for cup, courses in enumerate(CUPS):
        if course in courses:
            return cup, courses.index(course)
    raise ValueError("pista desconhecida: %s (opções: %s)" % (course, ", ".join(RACE_COURSES)))


class Menu:
    def __init__(self, emu):
        self.emu = emu

    def wait(self, frames):
        return self.emu.run([(frames, 0, 0, 0)])

    def press(self, button, after=20):
        return self.emu.run([(2, button, 0, 0), (after, 0, 0, 0)])


def make_state(emu, mode, course):
    cup, index = locate(course)
    if mode == "GP" and index != 0:
        raise ValueError("no Mario GP só dá para começar na primeira pista de cada copa (%s)"
                         % ", ".join(c[0] for c in CUPS))
    target = game.COURSES.index(course)
    m = Menu(emu)
    emu.speed(SPEED_FAST)
    m.wait(300)                       # logos até a tela de título
    emu.speed(SPEED_NORMAL)
    m.press(game.START)               # título -> GAME SELECT
    m.press(game.A)                   # 1P GAME
    if mode == "TT":
        m.press(game.D_DOWN, 10)      # T.TRIALS
        m.press(game.A)
        m.press(game.A)               # BEGIN
        m.press(game.A, 30)           # aviso "no controller pak" / OK
    else:
        m.press(game.A)               # MARIO GP
        m.press(game.A)               # 50cc
        m.press(game.A, 30)           # OK?
    m.press(game.A)                   # personagem (Mario)
    m.press(game.A, 30)               # OK?
    for _ in range(cup):
        m.press(game.D_RIGHT, 10)
    m.press(game.A)                   # copa
    if mode == "TT":
        for _ in range(index):
            m.press(game.D_DOWN, 10)
    state = m.wait(5)
    if state.course != target:
        raise RuntimeError("cursor na pista %s, esperado %s" % (state.course_code, course))
    if mode == "TT":
        m.press(game.A)               # pista
    m.press(game.A)                   # OK?

    # Espera carregar e a largada: o cronômetro zera no carregamento e começa a andar no "GO".
    seen_zero = False
    for _ in range(3000):
        state = emu.run([(1, 0, 0, 0)])
        if state.course == target and state.timer == 0:
            seen_zero = True
        if seen_zero and state.timer > 0:
            break
    else:
        raise RuntimeError("a corrida não começou")
    if state.mode_code != mode:
        raise RuntimeError("modo %s, esperado %s" % (state.mode_code, mode))
    path = paths.STATES_DIR / mode / (course + ".st")
    path.parent.mkdir(parents=True, exist_ok=True)
    emu.save_file(path)
    return path, state


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", choices=["TT", "GP"], default="TT")
    p.add_argument("--course", nargs="*", default=[])
    p.add_argument("--all", action="store_true", help="todas as pistas de corrida")
    args = p.parse_args()
    courses = RACE_COURSES if args.all else args.course
    if not courses:
        p.error("informe --course ou --all")
    for course in courses:
        with Emulator() as emu:  # um boot por pista: mais simples e robusto que voltar pelos menus
            path, state = make_state(emu, args.mode, course)
            print("%s %s -> %s (progress %.4f, timer %.2f)" % (args.mode, course, path, state.progress, state.timer),
                  flush=True)


if __name__ == "__main__":
    main()
