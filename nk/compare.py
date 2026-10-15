"""Comparação completa numa pista: corridas do especialista -> DAgger de cada modelo (mesmos dados
iniciais) -> cada iteração jogando sozinha. Tudo é anotado em results/races.csv; depois rode
`python -m nk.report` para atualizar results/README.md.

  python -m nk.compare MMF
  python -m nk.compare CM --shutdown     # desliga o PC ao terminar (15 min de folga)

Pastas usadas: data_v2/<pista>_expert, data_v2/<pista>_<modelo>, runs/<pista>_<modelo>/it0..it3 e
o log runs/compare_<pista>.log. Se for interrompida, rodar de novo reaproveita a coleta do
especialista (mas refaz o DAgger).
"""
import argparse
import os
import shutil
import subprocess
import sys
import time

from . import paths, results

MODELS = [("pilot", "pilotnet", ["--finetune-epochs", "30"]),
          ("tf", "transformer", ["--finetune-epochs", "10", "--device", "cuda"])]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("course", help="sigla da pista (ex.: LR, CM, MMF)")
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--iterations", type=int, default=4, help="iterações (0 = só imitação)")
    p.add_argument("--eval-episodes", type=int, default=3)
    p.add_argument("--shutdown", action="store_true", help="desliga o PC ao terminar (mesmo se falhar)")
    args = p.parse_args()

    tag = args.course.lower()
    state = paths.STATES_DIR / "TT" / ("%s.st" % args.course)
    log_path = paths.RUNS_DIR / ("compare_%s.log" % tag)
    paths.RUNS_DIR.mkdir(exist_ok=True)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1", TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL="1")

    def log(msg):
        line = time.strftime("%H:%M:%S ") + msg
        print(line, flush=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def run(cmd):
        log("$ " + " ".join(cmd))
        proc = subprocess.run([sys.executable, "-W", "ignore", "-m", *cmd], cwd=paths.ROOT, env=env)
        if proc.returncode != 0:
            raise RuntimeError("falhou (código %d): %s" % (proc.returncode, " ".join(cmd)))

    def body():
        from .data import load_episode
        if not state.is_file():
            raise FileNotFoundError(state)
        log("=== comparação %s ===" % args.course)
        expert = paths.ROOT / "data_v2" / (tag + "_expert")
        if not list(expert.glob("*/*/*.npz")):
            run(["nk.collect", "--states", str(state), "--workers", str(args.workers), "--episodes", "1",
                 "--data-dir", str(expert)])
            rows = []
            for i, f in enumerate(sorted(expert.glob("*/*/*.npz")), 1):
                m = load_episode(f)["meta"]
                log("  especialista: %s, %d passos, voltas %.2f, tempo %.1fs" % (
                    m["end_reason"], m["steps"], m["final_progress"], m["final_timer"]))
                rows.append({"data": results.today(), "pista": args.course, "dados": results.DATA_VERSION,
                             "tipo": "especialista", "modelo": "especialista", "run": expert.name, "corrida": i,
                             "resultado": m["end_reason"], "voltas": "%.3f" % m["final_progress"],
                             "tempo_s": "%.2f" % m["final_timer"], "nota": "corrida de coleta (com perturbações)"})
            results.append(rows)

        for short, arch, extra in MODELS:
            name = "%s_%s" % (tag, short)
            data = paths.ROOT / "data_v2" / name
            if not data.exists():
                shutil.copytree(expert, data)
            try:
                run(["nk.dagger", "--name", name, "--arch", arch, "--iterations", str(args.iterations),
                     "--workers", str(args.workers), "--states", str(state), "--data-dir", str(data),
                     "--skip-first-collect", "--epochs", "30", *extra])
            except RuntimeError as e:
                log("ERRO no DAgger de %s: %s (avaliando o que foi treinado)" % (name, e))
            for it in range(args.iterations):
                model = paths.RUNS_DIR / name / ("it%d" % it) / "model.pt"
                if model.exists():
                    try:
                        run(["nk.play", "--policy", str(model), "--state", str(state),
                             "--episodes", str(args.eval_episodes), "--record"])
                    except RuntimeError as e:
                        log("ERRO na avaliação de %s it%d: %s" % (name, it, e))
        log("=== fim ===")

    try:
        body()
    except Exception as e:
        log("ERRO: %r" % e)
    finally:
        if args.shutdown:
            log("desligamento agendado para daqui a 15 min (cancelar: shutdown /a)")
            subprocess.run(["shutdown", "/s", "/t", "900", "/c",
                            "DAggerKart: comparação terminou. O PC desliga em 15 min (cancelar: shutdown /a)."])


if __name__ == "__main__":
    main()
