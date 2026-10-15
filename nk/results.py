"""Registro de resultados: results/races.csv tem uma linha por corrida (avaliações das redes e
corridas do especialista). O relatório results/README.md é gerado a partir dele por nk.report."""
import csv
import re
import time
from pathlib import Path

from . import paths

RESULTS_DIR = paths.ROOT / "results"
RACES_CSV = RESULTS_DIR / "races.csv"

# data: AAAA-MM-DD · pista: sigla (LR, CM, ...) · dados: versão da coleta (v1 = com o bug do frame
# extra, v2 = corrigida) · tipo: avaliacao | especialista · modelo: pilotnet | transformer |
# especialista · run: pasta em runs/ · iteracao: iteração do DAgger (0 = só imitação) ·
# checkpoint: model (melhor validação) | last · selecao: media | greedy · corrida: nº da corrida ·
# resultado: finished | stuck | timeout · voltas: progresso final (0 a 3) · tempo_s: cronômetro do
# jogo no fim · decisao_ms: tempo médio de decisão da rede · nota: observações
FIELDS = ["data", "pista", "dados", "tipo", "modelo", "run", "iteracao", "checkpoint", "selecao",
          "corrida", "resultado", "voltas", "tempo_s", "decisao_ms", "nota"]

DATA_VERSION = "v2"  # coleta atual (savestate dentro do RUN, sem frame extra)


def append(rows, path=RACES_CSV):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, FIELDS)
        if new:
            w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in FIELDS})


def read(path=RACES_CSV):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def describe_checkpoint(ckpt_path):
    """runs/<run>/it<N>/model.pt -> (run, iteracao, checkpoint)."""
    p = Path(ckpt_path)
    m = re.fullmatch(r"it(\d+)", p.parent.name)
    if m:
        return p.parent.parent.name, int(m.group(1)), p.stem
    return p.parent.name, "", p.stem


def today():
    return time.strftime("%Y-%m-%d")
