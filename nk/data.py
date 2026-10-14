"""Episódios gravados e o carregador de sequências para o treino.

Cada episódio é um .npz em data/<pista>/<modo>/ com, por passo de decisão t:
  frames         (T, H, W, 3) uint8   imagem que o agente viu
  action         (T,) float32         direção executada
  expert_scores  (T, n_bins) float32  nota do especialista para cada direção (NaN se não avaliou)
  state          (T, 6) float32       progress, velocity, x, y, z, timer
e `meta` (JSON) com pista, modo, savestate, decision_frames, bins e política usada.
"""
import json
import time
import uuid
from pathlib import Path

import numpy as np

from . import game, paths


class EpisodeWriter:
    def __init__(self, meta):
        self.meta = dict(meta)
        self.frames, self.actions, self.scores, self.states = [], [], [], []

    def add(self, frame, action, scores, state):
        self.frames.append(frame)
        self.actions.append(action)
        self.scores.append(scores if scores is not None else np.full(len(game.STEER_BINS), np.nan, np.float32))
        self.states.append(state.vector())

    def __len__(self):
        return len(self.frames)

    def save(self, course, mode, data_dir=paths.DATA_DIR, **extra_meta):
        folder = Path(data_dir) / course / mode
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / ("%s-%s.npz" % (time.strftime("%Y%m%d-%H%M%S"), uuid.uuid4().hex[:6]))
        meta = dict(self.meta, course=course, mode=mode, steps=len(self), **extra_meta)
        np.savez_compressed(path, frames=np.stack(self.frames), action=np.asarray(self.actions, np.float32),
                            expert_scores=np.stack(self.scores).astype(np.float32),
                            state=np.stack(self.states).astype(np.float32), meta=json.dumps(meta))
        return path


def load_episode(path):
    with np.load(path) as z:
        ep = {k: z[k] for k in ("frames", "action", "expert_scores", "state")}
        ep["meta"] = json.loads(str(z["meta"]))
    ep["path"] = str(path)
    return ep


def find_episodes(data_dir=paths.DATA_DIR, courses=None):
    files = sorted(Path(data_dir).glob("*/*/*.npz"))
    if courses:
        wanted = {c.lower() for c in courses}
        files = [f for f in files if f.parent.parent.name.lower() in wanted]
    return files


def soft_targets(scores, temperature):
    """Notas do especialista -> distribuição sobre as ações (softmax com temperatura).
    Linhas sem avaliação (NaN) viram NaN e são ignoradas no treino."""
    s = scores - np.nanmax(scores, axis=-1, keepdims=True)
    p = np.exp(s / temperature)
    return p / p.sum(axis=-1, keepdims=True)


class SequenceDataset:
    """Todos os episódios na memória (de preferência na GPU) e amostragem de janelas contínuas de
    `seq_len` passos. Cada janela supervisiona todas as posições (o modelo temporal é causal)."""

    def __init__(self, episodes, seq_len, temperature, device):
        import torch
        self.seq_len, self.device = seq_len, device
        frames, targets, valid, starts = [], [], [], []
        offset = 0
        for ep in episodes:
            n = len(ep["action"])
            if n < seq_len:
                continue
            frames.append(ep["frames"])
            t = soft_targets(ep["expert_scores"], temperature)
            valid.append(~np.isnan(t).any(axis=1))
            targets.append(np.nan_to_num(t))
            starts.append(offset + np.arange(n - seq_len + 1))
            offset += n
        if not frames:
            raise ValueError("nenhum episódio com pelo menos %d passos" % seq_len)
        self.frames = torch.from_numpy(np.concatenate(frames)).to(device)            # (N, H, W, 3) uint8
        self.targets = torch.from_numpy(np.concatenate(targets)).float().to(device)  # (N, bins)
        self.valid = torch.from_numpy(np.concatenate(valid)).to(device)              # (N,)
        self.starts = torch.from_numpy(np.concatenate(starts)).to(device)            # janelas válidas
        self.offsets = torch.arange(seq_len, device=device)

    def __len__(self):
        return len(self.starts)

    def batches(self, batch_size, shuffle=True):
        import torch
        order = torch.randperm(len(self.starts), device=self.device) if shuffle else \
            torch.arange(len(self.starts), device=self.device)
        for i in range(0, len(order), batch_size):
            idx = self.starts[order[i:i + batch_size]][:, None] + self.offsets  # (B, T)
            yield self.frames[idx], self.targets[idx], self.valid[idx]
