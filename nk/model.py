"""Política com transformers.

  imagem (96x128) -> stem convolucional -> 6x8 = 48 tokens
                  -> transformer espacial (+ token CLS) -> 1 vetor por frame
  sequência de frames -> transformer temporal causal -> logits sobre STEER_BINS em cada passo

O stem convolucional faz o papel do "patchify" de um ViT, mas com indução local, o que funciona
melhor com poucos dados. O transformer temporal dá ao modelo noção de movimento e velocidade.
"""
from dataclasses import asdict, dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F

from . import game


@dataclass
class PolicyConfig:
    height: int = 96
    width: int = 128
    dim: int = 192
    heads: int = 4
    spatial_layers: int = 2
    temporal_layers: int = 4
    seq_len: int = 16          # contexto máximo (passos de decisão)
    dropout: float = 0.1
    n_bins: int = len(game.STEER_BINS)


def _encoder_layer(cfg):
    return nn.TransformerEncoderLayer(cfg.dim, cfg.heads, 4 * cfg.dim, cfg.dropout, activation="gelu",
                                      batch_first=True, norm_first=True)


class FrameEncoder(nn.Module):
    def __init__(self, cfg):
        super().__init__()
        d = cfg.dim

        def block(cin, cout, k):
            return nn.Sequential(nn.Conv2d(cin, cout, k, 2, k // 2), nn.GroupNorm(8, cout), nn.GELU())

        self.stem = nn.Sequential(block(3, 32, 5), block(32, 64, 3), block(64, 128, 3),
                                  nn.Conv2d(128, d, 3, 2, 1))
        n_tokens = (cfg.height // 16) * (cfg.width // 16)
        self.pos = nn.Parameter(torch.zeros(1, n_tokens + 1, d))
        self.cls = nn.Parameter(torch.zeros(1, 1, d))
        nn.init.trunc_normal_(self.pos, std=0.02)
        nn.init.trunc_normal_(self.cls, std=0.02)
        self.transformer = nn.TransformerEncoder(_encoder_layer(cfg), cfg.spatial_layers, enable_nested_tensor=False)
        self.norm = nn.LayerNorm(d)

    def forward(self, x):                      # x: (N, 3, H, W) float
        t = self.stem(x).flatten(2).transpose(1, 2)              # (N, tokens, d)
        t = torch.cat([self.cls.expand(len(t), -1, -1), t], 1) + self.pos
        return self.norm(self.transformer(t)[:, 0])               # (N, d)


class Policy(nn.Module):
    def __init__(self, cfg=PolicyConfig()):
        super().__init__()
        self.cfg = cfg
        self.encoder = FrameEncoder(cfg)
        self.time_pos = nn.Parameter(torch.zeros(1, cfg.seq_len, cfg.dim))
        nn.init.trunc_normal_(self.time_pos, std=0.02)
        self.temporal = nn.TransformerEncoder(_encoder_layer(cfg), cfg.temporal_layers, enable_nested_tensor=False)
        self.head = nn.Sequential(nn.LayerNorm(cfg.dim), nn.Linear(cfg.dim, cfg.n_bins))
        self.register_buffer("bins", torch.tensor(game.STEER_BINS), persistent=False)

    @staticmethod
    def preprocess(frames):
        """uint8 (..., H, W, 3) -> float (..., 3, H, W) em [-1, 1]."""
        return frames.permute(*range(frames.dim() - 3), -1, -3, -2).float().div(127.5).sub(1.0)

    def encode(self, frames):
        """frames uint8 (B, T, H, W, 3) -> embeddings (B, T, d)."""
        b, t = frames.shape[:2]
        x = self.preprocess(frames.reshape(b * t, *frames.shape[2:]))
        return self.encoder(x).reshape(b, t, -1)

    def temporal_logits(self, emb):
        """embeddings (B, T, d) -> logits (B, T, n_bins); a posição t só vê os passos <= t."""
        t = emb.shape[1]
        mask = nn.Transformer.generate_square_subsequent_mask(t, device=emb.device, dtype=emb.dtype)
        # Posição k sempre corresponde a "k frames de contexto antes", igual no treino e no uso.
        h = self.temporal(emb + self.time_pos[:, :t], mask=mask, is_causal=True)
        return self.head(h)

    def forward(self, frames):
        return self.temporal_logits(self.encode(frames))

    # ----- interface comum às políticas (usada por train, collect e play) -----

    kind = "transformer"
    is_temporal = True

    def steer(self, out, greedy=False):
        """saída do modelo (..., n_bins) -> direção (...)."""
        if greedy:
            return self.bins[out.argmax(-1)]
        return (F.softmax(out.float(), -1) * self.bins).sum(-1)

    def loss(self, out, targets, valid):
        """Entropia cruzada contra os alvos suaves (softmax das notas do especialista)."""
        loss = -(targets * F.log_softmax(out.float(), -1)).sum(-1)
        return (loss * valid).sum() / valid.sum().clamp(min=1)

    def checkpoint(self, **extra):
        return {"kind": self.kind, "config": asdict(self.cfg), "state_dict": self.state_dict(), **extra}


class NativeBatchNorm2d(nn.BatchNorm2d):
    """BatchNorm2d usando o kernel nativo do PyTorch em vez do MIOpen: no ROCm 7.2.1 para Windows o
    MIOpen compila o BatchNorm em tempo de execução e falha ('type_traits' file not found)."""

    def forward(self, x):
        with torch.backends.cudnn.flags(enabled=False):
            return super().forward(x)


@dataclass
class PilotNetConfig:
    height: int = 66
    width: int = 200
    keep_prob: float = 0.6
    seq_len: int = 1


class PilotNet(nn.Module):
    """A CNN do projeto original (create_model do train.py em Keras), a PilotNet da NVIDIA:
    BatchNorm + 5 convoluções (24, 36, 48 com 5x5/2; 64, 64 com 3x3), densas 1164-100-50-10 com
    dropout e 1 saída softsign (direção em [-1, 1]), treinada com a perda euclidiana.
    Vê um frame por vez (sem contexto temporal), como no original."""

    kind = "pilotnet"
    is_temporal = False

    def __init__(self, cfg=PilotNetConfig()):
        super().__init__()
        self.cfg = cfg
        drop = 1 - cfg.keep_prob

        def conv(cin, cout, k, stride):
            return [NativeBatchNorm2d(cin), nn.Conv2d(cin, cout, k, stride), nn.ReLU()]

        self.convs = nn.Sequential(*conv(3, 24, 5, 2), *conv(24, 36, 5, 2), *conv(36, 48, 5, 2),
                                   *conv(48, 64, 3, 1), *conv(64, 64, 3, 1), nn.Flatten())
        with torch.no_grad():
            n = self.convs(torch.zeros(1, 3, cfg.height, cfg.width)).shape[1]  # 1152 em 66x200
        self.dense = nn.Sequential(nn.Linear(n, 1164), nn.ReLU(), nn.Dropout(drop),
                                   nn.Linear(1164, 100), nn.ReLU(), nn.Dropout(drop),
                                   nn.Linear(100, 50), nn.ReLU(), nn.Dropout(drop),
                                   nn.Linear(50, 10), nn.ReLU(), nn.Dropout(drop),
                                   nn.Linear(10, 1), nn.Softsign())
        self.register_buffer("bins", torch.tensor(game.STEER_BINS), persistent=False)

    def forward(self, frames):
        """frames (B, T, H, W, 3) uint8/float [0, 255] -> (B, T, 1). Cada frame é independente."""
        b, t = frames.shape[:2]
        x = frames.reshape(b * t, *frames.shape[2:]).permute(0, 3, 1, 2).float()
        # Como no original: imagem redimensionada para 200x66, valores brutos normalizados pelo BatchNorm.
        x = F.interpolate(x, size=(self.cfg.height, self.cfg.width), mode="bilinear", align_corners=False)
        return self.dense(self.convs(x)).reshape(b, t, 1)

    def steer(self, out, greedy=False):
        return out[..., 0].float()

    def loss(self, out, targets, valid):
        """Perda euclidiana do original (|direção prevista - direção do especialista|), usando como
        alvo a melhor ação do especialista."""
        target = self.bins[targets.argmax(-1)]
        loss = (out[..., 0].float() - target).abs()
        return (loss * valid).sum() / valid.sum().clamp(min=1)

    def checkpoint(self, **extra):
        return {"kind": self.kind, "config": asdict(self.cfg), "state_dict": self.state_dict(), **extra}


ARCHITECTURES = {"transformer": (Policy, PolicyConfig), "pilotnet": (PilotNet, PilotNetConfig)}


def build_policy(arch, **config):
    cls, cfg_cls = ARCHITECTURES[arch]
    return cls(cfg_cls(**config))


def load_policy(ckpt, map_location="cpu"):
    """Carrega qualquer política salva por train.py. Retorna (modelo, checkpoint)."""
    if not isinstance(ckpt, dict):
        ckpt = torch.load(ckpt, map_location=map_location, weights_only=False)
    cls, cfg_cls = ARCHITECTURES[ckpt.get("kind", "transformer")]
    model = cls(cfg_cls(**ckpt["config"]))
    model.load_state_dict(ckpt["state_dict"])
    return model, ckpt


class PolicyRunner:
    """Usa uma política em tempo real. Para o transformer guarda os embeddings dos últimos frames,
    então cada passo só codifica o frame novo e roda o transformer temporal sobre o contexto."""

    def __init__(self, model, device="cpu", greedy=False):
        self.model = model.to(device).eval()
        self.device, self.greedy = device, greedy
        self.reset()

    def reset(self):
        self.context = []

    @torch.no_grad()
    def act(self, frame):
        """frame uint8 (H, W, 3) numpy -> (direção, saída bruta do modelo)."""
        f = torch.from_numpy(frame).to(self.device)[None, None]
        if self.model.is_temporal:
            self.context.append(self.model.encode(f)[:, 0])
            self.context = self.context[-self.model.cfg.seq_len:]
            out = self.model.temporal_logits(torch.stack(self.context, 1))[0, -1]
        else:
            out = self.model(f)[0, -1]
        return float(self.model.steer(out, self.greedy)), out.float().cpu().numpy()
