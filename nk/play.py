"""A rede joga sozinha. Mostra o resultado de cada corrida (tempo ou até onde chegou).

  python -m nk.play --policy runs/v1/model.pt --episodes 3
"""
import argparse
import time
from pathlib import Path

import numpy as np
import torch

from . import paths
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
    args = p.parse_args()

    model, ckpt = load_policy(args.policy)
    runner = PolicyRunner(model, device=args.device, greedy=args.greedy)
    print("política: %s (época %s)" % (args.policy, ckpt.get("epoch")))
    results = []
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
            results.append((env.reason, st.progress, st.timer))
            print("corrida %d: %s, voltas %.2f/3, tempo %.2fs, decisão %.1f ms em média" % (
                i + 1, env.reason, st.progress, st.timer, 1000 * np.mean(think)), flush=True)
    done = [r for r in results if r[0] == "finished"]
    print("terminou %d/%d corridas%s" % (len(done), len(results),
          (", melhor tempo %.2fs" % min(r[2] for r in done)) if done else ""))


if __name__ == "__main__":
    main()
