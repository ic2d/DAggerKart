"""Gera results/README.md (tabelas) e o gráfico results/times-{light,dark}.png a partir de
results/races.csv. O GitHub mostra o README da pasta results/ formatado ao abri-la.

  python -m nk.report
"""
import statistics
from collections import defaultdict

from . import results

MODELS = [("pilotnet", "PilotNet"), ("transformer", "Transformer")]
COURSE_NAMES = {"LR": "Luigi Raceway", "CM": "Choco Mountain", "MMF": "Moo Moo Farm", "MR": "Mario Raceway",
                "KTB": "Koopa Troopa Beach", "KD": "Kalimari Desert", "TT": "Toad's Turnpike",
                "FS": "Frappe Snowland", "WS": "Wario Stadium", "SL": "Sherbet Land", "RRy": "Royal Raceway",
                "BC": "Bowser's Castle", "DK": "D.K.'s Jungle Parkway", "YV": "Yoshi Valley",
                "BB": "Banshee Boardwalk", "RRd": "Rainbow Road"}

# Paleta validada (scripts/validate_palette.js da skill de visualização): slots 1 e 2 da paleta
# categórica de referência, com passos próprios para o fundo escuro.
THEMES = {
    "light": {"surface": "#fcfcfb", "ink": "#0b0b0b", "ink2": "#52514e", "grid": "#e4e3de",
              "band": "#e8e7e2", "series": {"pilotnet": "#2a78d6", "transformer": "#eb6834"}},
    "dark": {"surface": "#1a1a19", "ink": "#f0efec", "ink2": "#c3c2b7", "grid": "#33332f",
             "band": "#383835", "series": {"pilotnet": "#3987e5", "transformer": "#d95926"}},
}


def fmt(x, nd=2):
    return ("%.*f" % (nd, x)).replace(".", ",")


class Group:
    """Corridas de uma mesma configuração (pista, modelo, run, iteração...)."""

    def __init__(self, rows):
        self.rows = rows
        self.n = len(rows)
        self.times = [float(r["tempo_s"]) for r in rows if r["resultado"] == "finished"]
        self.done = len(self.times)

    @property
    def all_done(self):
        return self.n > 0 and self.done == self.n

    @property
    def mean(self):
        return statistics.mean(self.times) if self.times else None

    @property
    def best(self):
        return min(self.times) if self.times else None

    @property
    def worst(self):
        return max(self.times) if self.times else None

    def completions(self):
        return "%d/%d" % (self.done, self.n)

    def stuck_laps(self):
        laps = [float(r["voltas"]) for r in self.rows if r["resultado"] != "finished"]
        return ("presa em ~%s volta" % fmt(statistics.mean(laps), 2)) if laps else ""


def is_main(r):
    """Configuração padrão das comparações: checkpoint de melhor validação, direção pela média."""
    return r["checkpoint"] in ("", "model") and r["selecao"] in ("", "media") and not r["nota"]


def index_v2(rows):
    evals = defaultdict(list)     # (pista, modelo, iteração) -> corridas
    experts = defaultdict(list)   # pista -> corridas do especialista
    for r in rows:
        if r["dados"] != "v2":
            continue
        if r["tipo"] == "especialista":
            experts[r["pista"]].append(r)
        elif is_main(r):
            evals[(r["pista"], r["modelo"], int(r["iteracao"]))].append(r)
    return evals, experts


def best_after_dagger(evals, course, model):
    """Menor tempo médio entre as iterações de DAgger (>= 1) em que todas as corridas terminaram."""
    cands = [(Group(v).mean, it) for (c, m, it), v in evals.items()
             if c == course and m == model and it >= 1 and Group(v).all_done]
    return min(cands) if cands else (None, None)


def chart(evals, experts, courses, path, theme):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t = THEMES[theme]
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "text.color": t["ink"],
                         "axes.labelcolor": t["ink2"], "xtick.color": t["ink2"], "ytick.color": t["ink2"]})
    fig, axes = plt.subplots(1, len(courses), figsize=(4.2 * len(courses), 3.9), dpi=150, squeeze=False)
    fig.patch.set_facecolor(t["surface"])
    for ax, course in zip(axes[0], courses):
        ax.set_facecolor(t["surface"])
        exp = Group(experts.get(course, []))
        its = sorted({it for (c, m, it) in evals if c == course})
        # Eixo: iterações com todas as corridas completas + faixa do especialista; o resto vai para a borda.
        ref = [Group(v).mean for (c, m, it), v in evals.items() if c == course and Group(v).all_done and it >= 1]
        ref += exp.times
        lo, hi = min(ref) - 2.5, max(ref) + 3.5
        if exp.times:  # identificada pela legenda (um rótulo dentro da faixa colidia com as linhas)
            ax.axhspan(min(exp.times), max(exp.times), color=t["band"], lw=0, zorder=0)
        for k, (model, label) in enumerate(MODELS):
            color = t["series"][model]
            xs, ys = [], []
            for it in its:
                g = Group(evals.get((course, model, it), []))
                if g.n == 0:
                    continue
                if g.all_done and g.mean <= hi:
                    xs.append(it)
                    ys.append(g.mean)
                    continue
                # fora do padrão: não completou tudo, ou tempo fora da escala -> marcador vazado na borda
                y = hi - (0.03 + 0.08 * k) * (hi - lo)
                ax.plot([it], [y], marker="o", ms=7, mfc=t["surface"], mec=color, mew=2, zorder=4, clip_on=False)
                txt = g.completions() if not g.all_done else "%s s" % fmt(g.mean, 0)
                ax.annotate(txt, (it, y), textcoords="offset points", xytext=(7, -3), fontsize=8, color=t["ink2"])
            ax.plot(xs, ys, color=color, lw=2, marker="o", ms=7, mec=t["surface"], mew=1.5, zorder=3)
            if xs:
                ax.annotate(label, (xs[-1], ys[-1]), textcoords="offset points", xytext=(8, 0),
                            fontsize=9, color=t["ink"], va="center")
        ax.set_ylim(lo, hi)
        ax.set_xlim(its[0] - 0.3, its[-1] + 0.95)
        ax.set_xticks(its)
        ax.set_xticklabels(["it0\nimitação" if i == 0 else "it%d" % i for i in its])
        ax.set_title(COURSE_NAMES.get(course, course), color=t["ink"], fontsize=11, loc="left")
        ax.grid(axis="y", color=t["grid"], lw=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(t["grid"])
        ax.tick_params(length=0)
    axes[0][0].set_ylabel("tempo médio da corrida (s)")
    handles = [plt.Line2D([], [], color=t["series"][m], lw=2, marker="o", ms=7, label=l) for m, l in MODELS]
    handles.append(plt.Rectangle((0, 0), 1, 1, color=t["band"], label="faixa do especialista"))
    handles.append(plt.Line2D([], [], ls="", marker="o", ms=7, mfc=t["surface"], mec=t["ink2"], mew=2,
                              label="não completou todas / fora da escala"))
    fig.legend(handles=handles, loc="upper center", ncol=4, frameon=False, fontsize=9,
               bbox_to_anchor=(0.5, 1.0), labelcolor=t["ink"])
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(path, facecolor=t["surface"])
    plt.close(fig)


def main():
    rows = results.read()
    evals, experts = index_v2(rows)
    courses = [c for c in ["LR", "CM", "MMF", "MR"] + sorted({c for c, _, _ in evals})
               if any(k[0] == c for k in evals)]
    courses = list(dict.fromkeys(courses))
    out = []
    w = out.append

    w("# Resultados\n")
    w("Gerado por `python -m nk.report` a partir de [`races.csv`](races.csv) (uma linha por corrida). "
      "Não edite este arquivo à mão.\n")
    w("Cada configuração foi testada com a rede **jogando sozinha** (3 corridas de 3 voltas, Time Trial, "
      "Mario). *Iteração 0* = só imitação do especialista; *1-3* = iterações de DAgger. Tempos em segundos "
      "de jogo; *completas* = corridas que terminaram as 3 voltas.\n")

    if courses:
        w("## Resumo\n")
        w("| Pista | Especialista | PilotNet só imitação | PilotNet após DAgger | Transformer só imitação | "
          "Transformer após DAgger | Mais rápido |")
        w("|---|---|---|---|---|---|---|")
        for c in courses:
            exp = Group(experts.get(c, []))
            cells = [COURSE_NAMES.get(c, c),
                     "%s–%s s" % (fmt(min(exp.times), 1), fmt(max(exp.times), 1)) if exp.times else "—"]
            bests = {}
            for model, _ in MODELS:
                g0 = Group(evals.get((c, model, 0), []))
                cells.append("%s completas" % g0.completions() if g0.n else "—")
                mean, it = best_after_dagger(evals, c, model)
                bests[model] = mean
                cells.append("%s s (it%d)" % (fmt(mean, 1), it) if mean else "—")
            valid = {m: v for m, v in bests.items() if v}
            if len(valid) == 2:
                (m1, v1), (m2, v2) = sorted(valid.items(), key=lambda kv: kv[1])
                name = dict(MODELS)[m1]
                cells.append("empate" if v2 - v1 < 1.0 else "%s (−%s s)" % (name, fmt(v2 - v1, 1)))
            else:
                cells.append("—")
            w("| " + " | ".join(cells) + " |")
        w("\n*Após DAgger* = a melhor média entre as iterações 1-3 em que as 3 corridas terminaram. "
          "*Empate* = diferença menor que 1 s.\n")

        for theme in ("light", "dark"):
            chart(evals, experts, courses, results.RESULTS_DIR / ("times-%s.png" % theme), theme)
        w("<picture>\n  <source media=\"(prefers-color-scheme: dark)\" srcset=\"times-dark.png\">\n"
          "  <img alt=\"Tempo médio por iteração em cada pista, PilotNet e Transformer, com a faixa de tempo do "
          "especialista\" src=\"times-light.png\">\n</picture>\n")

    for c in courses:
        w("## %s\n" % COURSE_NAMES.get(c, c))
        exp = Group(experts.get(c, []))
        if exp.n:
            w("Especialista: %s corridas completas, %s s (média %s s).\n" % (
                exp.completions(), " · ".join(fmt(x, 1) for x in sorted(exp.times)), fmt(exp.mean, 1)))
        w("| Iteração | PilotNet: completas | média | melhor | Transformer: completas | média | melhor |")
        w("|---|---|---|---|---|---|---|")
        for it in sorted({i for (cc, m, i) in evals if cc == c}):
            cells = ["it%d%s" % (it, " (só imitação)" if it == 0 else "")]
            for model, _ in MODELS:
                g = Group(evals.get((c, model, it), []))
                if not g.n:
                    cells += ["—", "—", "—"]
                    continue
                cells.append(g.completions() + ("" if g.all_done else " (%s)" % g.stuck_laps()))
                cells.append(fmt(g.mean) if g.times else "—")
                cells.append(fmt(g.best) if g.times else "—")
            w("| " + " | ".join(cells) + " |")
        w("")

    # pistas só com especialista (ex.: abandonadas)
    for c in sorted(experts):
        if c in courses:
            continue
        exp = Group(experts[c])
        notes = {r["nota"] for r in experts[c] if r["nota"]}
        w("## %s (sem comparação)\n" % COURSE_NAMES.get(c, c))
        w("Especialista: %s corridas completas. %s\n" % (exp.completions(), " ".join(sorted(notes))))
        w("| Corrida | Resultado | Voltas | Tempo (s) |\n|---|---|---|---|")
        for r in experts[c]:
            w("| %s | %s | %s | %s |" % (r["corrida"], r["resultado"], fmt(float(r["voltas"])),
                                        fmt(float(r["tempo_s"]))))
        w("")

    v1 = [r for r in rows if r["dados"] == "v1" and r["tipo"] == "avaliacao"]
    if v1:
        w("## Histórico: dados v1 (com o bug do frame extra)\n")
        w("Antes da correção da coleta, cada decisão do especialista tinha 1 frame extra sem nenhum botão, "
          "e as redes treinadas assim travavam ao jogar sozinhas. Ver o README principal.\n")
        w("| Data | Modelo | Run | Iteração | Checkpoint | Direção | Completas | Média | Observação |")
        w("|---|---|---|---|---|---|---|---|---|")
        groups = defaultdict(list)
        for r in v1:
            groups[(r["data"], r["modelo"], r["run"], r["iteracao"], r["checkpoint"], r["selecao"], r["nota"])].append(r)
        for (d, m, run, it, ck, sel, note), g in groups.items():
            gg = Group(g)
            w("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                d, dict(MODELS).get(m, m), run, it, ck, sel,
                gg.completions() + ("" if gg.all_done else " (%s)" % gg.stuck_laps()),
                fmt(gg.mean) if gg.times else "—", note))
        w("")

    path = results.RESULTS_DIR / "README.md"
    path.write_text("\n".join(out), encoding="utf-8", newline="\n")
    print("gerado:", path)


if __name__ == "__main__":
    main()
