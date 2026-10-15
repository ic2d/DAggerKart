"""A rede joga sozinha. Mostra o resultado de cada corrida (tempo ou até onde chegou).

  python -m nk.play --policy runs/v1/model.pt --episodes 3
  python -m nk.play --policy runs/v1/model.pt --episodes 3 --record   # anota em results/races.csv
"""
import argparse
import time
from pathlib import Path

import numpy as np
import torch

from . import paths, results
from .emulator import Emulator
from .env import RaceEnv
from .model import PolicyRunner, load_policy


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--policy", type=Path, required=True)
    p.add_argument("--state", type=Path, default=paths.STATES_DIR / "TT" / "LR.st")
    p.add_argument("--episodes", type=int, default=1)
    p.add_argument("--decision-frames", type=int, default=3)
    p.add_argument("--greedy", action="store_true", help="usa a ação mais provável em vez da média")
    p.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    p.add_argument("--record", action="store_true", help="anota cada corrida em results/races.csv")
    p.add_argument("--note", default="", help="observação gravada junto (com --record)")
    args = p.parse_args()

    model, ckpt = load_policy(args.policy)
    runner = PolicyRunner(model, device=args.device, greedy=args.greedy)
    print("política: %s (época %s)" % (args.policy, ckpt.get("epoch")))
    run_name, iteration, checkpoint = results.describe_checkpoint(args.policy)
    races = []
    with Emulator() as emu:
        env = RaceEnv(emu, decision_frames=args.decision_frames)
        for i in range(args.episodes):
            obs = env.reset(args.state)
            runner.reset()
            think = []
            while not env.done:
                t = time.perf_counter()
                steer, _ = runner.act(obs.frame)
                think.append(time.perf_counter() - t)
                obs = env.step(steer)
            st = obs.state
            races.append((env.reason, st.progress, st.timer))
            print("corrida %d: %s, voltas %.2f/3, tempo %.2fs, decisão %.1f ms em média" % (
                i + 1, env.reason, st.progress, st.timer, 1000 * np.mean(think)), flush=True)
            if args.record:
                results.append([{
                    "data": results.today(), "pista": st.course_code, "dados": results.DATA_VERSION,
                    "tipo": "avaliacao", "modelo": model.kind, "run": run_name, "iteracao": iteration,
                    "checkpoint": checkpoint, "selecao": "greedy" if args.greedy else "media",
                    "corrida": i + 1, "resultado": env.reason, "voltas": "%.3f" % st.progress,
                    "tempo_s": "%.2f" % st.timer, "decisao_ms": "%.1f" % (1000 * np.mean(think)),
                    "nota": args.note}])
    done = [r for r in races if r[0] == "finished"]
    print("terminou %d/%d corridas%s" % (len(done), len(races),
          (", melhor tempo %.2fs" % min(r[2] for r in done)) if done else ""))


if __name__ == "__main__":
    main()
