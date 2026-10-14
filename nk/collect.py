"""Coleta de dados com o especialista de busca, em vários emuladores em paralelo.

  # especialista dirigindo (com perturbações aleatórias para variar os estados), alternando entre
  # as pistas de states/TT
  python -m nk.collect --episodes 4 --workers 4

  # DAgger: a rede dirige (com prob. 1-beta) e o especialista anota a ação certa em todo passo
  python -m nk.collect --episodes 4 --workers 4 --policy runs/v1/model.pt --beta 0.3

Cada episódio é uma corrida completa (3 voltas) ou termina se o kart ficar preso.
"""
import argparse
import multiprocessing as mp
import time
from pathlib import Path

import numpy as np

from . import game, paths
from .data import EpisodeWriter
from .emulator import Emulator
from .env import RaceEnv
from .expert import ROOT_SLOT, SearchExpert


def collect_episode(env, expert, state_file, rng, args, runner=None, log=print):
    # Cada comando salva o estado para o especialista no próprio último frame (ROOT_SLOT): assim a
    # busca não altera o ritmo do jogo e a dinâmica é a mesma de quando a rede joga sozinha.
    obs = env.reset(state_file, save=ROOT_SLOT)
    writer = EpisodeWriter({
        # collector_version 2: estado do especialista salvo dentro do RUN (versão 1 tinha 1 frame
        # extra sem input a cada decisão, ver lua/agent.lua).
        "collector_version": 2,
        "state_file": str(state_file), "decision_frames": env.decision_frames,
        "bins": game.STEER_BINS.tolist(), "policy": args.policy, "beta": args.beta,
        "noise": args.noise, "expert": {"steer_frames": expert.steer_frames,
                                        "forward_frames": expert.forward_frames,
                                        "velocity_weight": expert.velocity_weight}})
    if runner is not None:
        runner.reset()
    noise_left, noise_action = 0, 0.0
    takeover_left, takeovers = 0, 0
    takeover_after = int(args.takeover_after * game.FPS / env.decision_frames)
    takeover_steps = int(args.takeover_seconds * game.FPS / env.decision_frames)
    t0, last_log = time.time(), time.time()
    try:
        while not env.done:
            scores = expert.scores(root_saved=True)
            action = expert.best(scores)
            if runner is not None:
                policy_action, _ = runner.act(obs.frame)  # sempre: mantém o contexto da rede em dia
                # Rede presa (sem avançar há um tempo): o especialista assume por alguns segundos para
                # tirar o kart dali, e a corrida segue cobrindo o resto da pista.
                if takeover_left == 0 and env.steps - env.best_step >= takeover_after:
                    takeover_left, takeovers = takeover_steps, takeovers + 1
                if takeover_left > 0:
                    takeover_left -= 1
                elif rng.random() >= args.beta:
                    action = policy_action
            if noise_left > 0:
                action, noise_left = noise_action, noise_left - 1
            elif rng.random() < args.noise:
                noise_action = float(rng.choice(game.STEER_BINS))
                noise_left = int(rng.integers(1, 6))
                action = noise_action
            writer.add(obs.frame, action, scores, obs.state)
            obs = env.step(action, save=ROOT_SLOT)
            if time.time() - last_log > 30:
                last_log = time.time()
                log("  passo %d, volta %.2f, %.2f s/passo%s" % (
                    len(writer), obs.state.progress + 1, (time.time() - t0) / len(writer),
                    ", %d resgates do especialista" % takeovers if runner is not None else ""))
    finally:
        reason = env.reason or "interrupted"
        st = obs.state
        path = writer.save(st.course_code, st.mode_code, data_dir=args.data_dir, end_reason=reason,
                           final_progress=st.progress, final_timer=st.timer,
                           takeovers=takeovers) if len(writer) else None
    return path, reason, st, len(writer), time.time() - t0


def worker(worker_id, args):
    log = lambda msg: print("[%d] %s" % (worker_id, msg), flush=True)
    rng = np.random.default_rng([args.seed, worker_id])
    runner = None
    if args.policy:
        import torch
        from .model import PolicyRunner, load_policy
        torch.set_num_threads(2)  # vários workers em paralelo: não disputar a CPU com os emuladores
        model, _ = load_policy(args.policy)
        runner = PolicyRunner(model, device=args.device)
    with Emulator() as emu:
        env = RaceEnv(emu, decision_frames=args.decision_frames, max_seconds=args.max_seconds)
        expert = SearchExpert(emu)
        for i in range(args.episodes):
            state_file = args.states[(worker_id + i * args.workers) % len(args.states)]
            log("episódio %d/%d: %s" % (i + 1, args.episodes, state_file.name))
            path, reason, st, steps, dt = collect_episode(env, expert, state_file, rng, args, runner, log)
            log("episódio %d/%d: %s, %d passos, voltas %.2f, tempo de jogo %.1fs, %.0fs de coleta -> %s"
                % (i + 1, args.episodes, reason, steps, st.progress, st.timer, dt, path))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--states", type=Path, nargs="*",
                   help="savestates de largada (padrão: todos em states/TT); os episódios alternam entre eles")
    p.add_argument("--episodes", type=int, default=1, help="episódios por worker")
    p.add_argument("--workers", type=int, default=1, help="emuladores em paralelo")
    p.add_argument("--policy", type=str, default=None, help="checkpoint para DAgger")
    p.add_argument("--beta", type=float, default=1.0, help="prob. de executar a ação do especialista")
    p.add_argument("--noise", type=float, default=0.03, help="prob. por passo de iniciar uma perturbação")
    p.add_argument("--takeover-after", type=float, default=3.0,
                   help="DAgger: segundos sem avançar até o especialista assumir")
    p.add_argument("--takeover-seconds", type=float, default=2.0, help="DAgger: duração do resgate")
    p.add_argument("--decision-frames", type=int, default=3)
    p.add_argument("--max-seconds", type=float, default=300.0, help="tempo de jogo máximo por episódio")
    p.add_argument("--device", default="cpu", help="dispositivo da política no DAgger")
    p.add_argument("--data-dir", type=Path, default=paths.DATA_DIR)
    p.add_argument("--seed", type=int, default=int(time.time()))
    args = p.parse_args()
    if args.policy is None:
        args.beta = 1.0
    if not args.states:
        args.states = sorted((paths.STATES_DIR / "TT").glob("*.st"))
    if not args.states:
        p.error("nenhum savestate; crie com: python -m nk.make_state --mode TT --all")
    rng = np.random.default_rng(args.seed)
    args.states = [args.states[i] for i in rng.permutation(len(args.states))]

    if args.workers == 1:
        worker(0, args)
        return
    procs = [mp.Process(target=worker, args=(i, args)) for i in range(args.workers)]
    for proc in procs:
        proc.start()
        time.sleep(3)  # abrir os emuladores um de cada vez
    for proc in procs:
        proc.join()


if __name__ == "__main__":
    main()
