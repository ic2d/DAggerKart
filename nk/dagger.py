"""Ciclo completo de treino (DAgger), rodando collect e train em sequência.

  python -m nk.dagger --name v1 --iterations 4 --workers 6

Iteração 0: o especialista dirige e a rede aprende a imitá-lo.
Iteração i: a rede da iteração anterior dirige (com prob. 1 - beta_i), o especialista anota a ação
certa em cada passo, e a rede é retreinada com todos os dados. Isso ensina a rede a se recuperar dos
próprios erros, algo que só imitar o especialista não ensina.
"""
import argparse
import subprocess
import sys

from . import paths


def run(cmd):
    print("\n$ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--name", required=True, help="pasta em runs/")
    p.add_argument("--iterations", type=int, default=4)
    p.add_argument("--start", type=int, default=0, help="iteração inicial (para retomar)")
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--episodes", type=int, default=1, help="episódios por worker em cada iteração")
    p.add_argument("--first-episodes", type=int, default=3, help="episódios por worker na iteração 0")
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--finetune-epochs", type=int, default=12)
    p.add_argument("--beta-decay", type=float, default=0.5, help="beta_i = beta_decay ** i")
    p.add_argument("--arch", default="transformer", help="transformer ou pilotnet (CNN do projeto original)")
    p.add_argument("--states", nargs="*", help="savestates (padrão: todos em states/TT)")
    p.add_argument("--skip-first-collect", action="store_true",
                   help="na iteração 0, treina com os dados que já estão em data/ sem coletar mais")
    args = p.parse_args()

    py = sys.executable
    base = paths.RUNS_DIR / args.name
    states = ["--states", *args.states] if args.states else []
    for it in range(args.start, args.iterations):
        out = base / ("it%d" % it)
        if it == 0:
            if not args.skip_first_collect:
                run([py, "-m", "nk.collect", "--workers", str(args.workers), "--episodes", str(args.first_episodes),
                     *states])
            run([py, "-m", "nk.train", "--out", str(out), "--epochs", str(args.epochs), "--arch", args.arch])
        else:
            prev = base / ("it%d" % (it - 1)) / "model.pt"
            beta = args.beta_decay ** it
            run([py, "-m", "nk.collect", "--workers", str(args.workers), "--episodes", str(args.episodes),
                 "--policy", str(prev), "--beta", "%.3f" % beta, *states])
            # Continua do modelo anterior com lr menor (metade do padrão da arquitetura).
            lr = "5e-5" if args.arch == "pilotnet" else "1.5e-4"
            run([py, "-m", "nk.train", "--out", str(out), "--init", str(prev), "--epochs", str(args.finetune_epochs),
                 "--lr", lr])
    print("\npronto: %s" % (base / ("it%d" % (args.iterations - 1)) / "model.pt"))


if __name__ == "__main__":
    main()
