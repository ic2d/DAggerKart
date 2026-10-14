"""Caminhos do projeto. O emulador e a ROM ficam fora do repositório; configure-os em config.json
(copie config.example.json) ou pelas variáveis de ambiente NK_MUPEN_EXE e NK_ROM."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent            # raiz do repositório
AGENT_LUA = ROOT / "lua" / "agent.lua"
STATES_DIR = ROOT / "states"      # savestates (.st) de início de corrida
DATA_DIR = ROOT / "data"          # episódios gravados (.npz)
RUNS_DIR = ROOT / "runs"          # checkpoints de treino

_config = {}
if (ROOT / "config.json").is_file():
    _config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def _path(key, env, default):
    value = os.environ.get(env) or _config.get(key)
    if not value:
        return default
    p = Path(value)
    return p if p.is_absolute() else (ROOT / p).resolve()


# Padrão: layout da máquina original (Mupen e o projeto antigo ao lado da pasta do repositório).
MUPEN_EXE = _path("mupen_exe", "NK_MUPEN_EXE", ROOT.parent / "Mupen" / "mupen64.exe")
ROM = _path("rom", "NK_ROM", ROOT.parent / "Mano-Karthus-main" / "BizHawk" / "Mario Kart 64 (USA).n64")


def check():
    """Mensagens de erro claras se o emulador ou a ROM não forem encontrados."""
    problems = []
    if not MUPEN_EXE.is_file():
        problems.append("Mupen não encontrado em %s (configure 'mupen_exe' em config.json)" % MUPEN_EXE)
    if not ROM.is_file():
        problems.append("ROM não encontrada em %s (configure 'rom' em config.json)" % ROM)
    if problems:
        raise FileNotFoundError("\n".join(problems))
