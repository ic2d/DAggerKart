"""Treino da política por imitação do especialista (alvos suaves a partir das notas da busca).

  python -m nk.train --out runs/v1 --epochs 30
  python -m nk.train --out runs/v2 --init runs/v1/model.pt     # continuar depois de mais DAgger
"""
import argparse
import json
import math
import time
import zlib
from pathlib import Path

import torch
import torch.nn.functional as F

from . import paths
from .data import SequenceDataset, find_episodes, load_episode
from .model import ARCHITECTURES, build_policy, load_policy


def augment(frames, max_shift=0.06, max_scale=0.06, color=0.15):
    """frames uint8 (B, T, H, W, 3) -> float [0, 255] com a mesma transformação em toda a sequência
    (deslocamento/zoom pequenos e brilho/contraste)."""
    b, t, h, w, _ = frames.shape
    x = frames.permute(0, 1, 4, 2, 3).reshape(b, t * 3, h, w).float()
    dev = x.device
    scale = 1 + (torch.rand(b, device=dev) * 2 - 1) * max_scale
    shift = (torch.rand(b, 2, device=dev) * 2 - 1) * max_shift
    theta = torch.zeros(b, 2, 3, device=dev)
    theta[:, 0, 0], theta[:, 1, 1] = scale, scale
    theta[:, :, 2] = shift
    grid = F.affine_grid(theta, x.shape, align_corners=False)
    x = F.grid_sample(x, grid, padding_mode="border", align_corners=False)
    gain = 1 + (torch.rand(b, 1, 1, 1, device=dev) * 2 - 1) * color
    bias = (torch.rand(b, 1, 1, 1, device=dev) * 2 - 1) * color * 64
    x = (x * gain + bias).clamp(0, 255)
    return x.reshape(b, t, 3, h, w).permute(0, 1, 3, 4, 2)


@torch.no_grad()
def evaluate(model, dataset, batch_size):
    """Perda e erro médio |direção da rede - melhor direção do especialista|; acc = acertou a mesma
    direção discreta (para modelos de regressão, a direção prevista arredondada para o bin mais próximo)."""
    model.eval()
    total, n, correct, steer_err = 0.0, 0, 0, 0.0
    for frames, targets, valid in dataset.batches(batch_size, shuffle=False):
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=frames.is_cuda):
            out = model(frames)
        v = valid.float()
        total += float(model.loss(out, targets, v)) * float(v.sum())
        n += float(v.sum())
        best = targets.argmax(-1)
        steer = model.steer(out)
        predicted_bin = (steer[..., None] - model.bins).abs().argmin(-1)
        correct += float(((predicted_bin == best).float() * v).sum())
        steer_err += float(((steer - model.bins[best]).abs() * v).sum())
    model.train()
    return {"loss": total / max(n, 1), "acc": correct / max(n, 1), "steer_mae": steer_err / max(n, 1)}


def is_validation(path, frac):
    return (zlib.crc32(Path(path).name.encode()) % 1000) / 1000 < frac


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data-dir", type=Path, default=paths.DATA_DIR)
    p.add_argument("--courses", nargs="*", help="siglas das pistas (padrão: todas)")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--init", type=Path, help="checkpoint para continuar o treino")
    p.add_argument("--arch", choices=sorted(ARCHITECTURES), default="transformer",
                   help="transformer (padrão) ou pilotnet (a CNN do projeto original)")
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--batch-size", type=int, default=None, help="padrão: 32 (transformer), 50 (pilotnet)")
    p.add_argument("--seq-len", type=int, default=16, help="contexto do transformer (a pilotnet usa 1)")
    p.add_argument("--lr", type=float, default=None, help="padrão: 3e-4 (transformer), 1e-4 (pilotnet)")
    p.add_argument("--weight-decay", type=float, default=0.05)
    p.add_argument("--temperature", type=float, default=0.01, help="temperatura dos alvos suaves")
    p.add_argument("--val-frac", type=float, default=0.15)
    p.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = p.parse_args()

    if args.init:
        model, _ = load_policy(args.init)
        args.arch = model.kind
    elif args.arch == "pilotnet":
        model = build_policy("pilotnet")
    else:
        model = build_policy("transformer", seq_len=args.seq_len)
    seq_len = model.cfg.seq_len
    pilot = args.arch == "pilotnet"
    args.batch_size = args.batch_size or (50 if pilot else 32)
    args.lr = args.lr or (1e-4 if pilot else 3e-4)

    files = find_episodes(args.data_dir, args.courses)
    if not files:
        raise SystemExit("nenhum episódio em %s" % args.data_dir)
    episodes = [load_episode(f) for f in files]
    val_eps = [e for e in episodes if is_validation(e["path"], args.val_frac)]
    train_eps = [e for e in episodes if not is_validation(e["path"], args.val_frac)]
    if not val_eps:  # poucos episódios: separa o último
        val_eps, train_eps = train_eps[-1:], train_eps[:-1] or train_eps
    print("episódios: %d treino (%d passos), %d validação (%d passos)" % (
        len(train_eps), sum(len(e["action"]) for e in train_eps),
        len(val_eps), sum(len(e["action"]) for e in val_eps)))

    train_ds = SequenceDataset(train_eps, seq_len, args.temperature, args.device)
    val_ds = SequenceDataset(val_eps, seq_len, args.temperature, args.device)

    model.to(args.device).train()
    print("modelo: %s, %.2fM parâmetros" % (args.arch, sum(p.numel() for p in model.parameters()) / 1e6))

    decay = [p for n, p in model.named_parameters() if p.dim() >= 2 and "pos" not in n and "cls" not in n]
    no_decay = [p for n, p in model.named_parameters() if not (p.dim() >= 2 and "pos" not in n and "cls" not in n)]
    opt = torch.optim.AdamW([{"params": decay, "weight_decay": args.weight_decay},
                             {"params": no_decay, "weight_decay": 0.0}], lr=args.lr, betas=(0.9, 0.95))
    steps_per_epoch = math.ceil(len(train_ds) / args.batch_size)
    total_steps, warmup = args.epochs * steps_per_epoch, min(500, steps_per_epoch * 2)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1, (s + 1) / warmup) *
                                              0.5 * (1 + math.cos(math.pi * min(1, s / total_steps))))

    args.out.mkdir(parents=True, exist_ok=True)
    log = open(args.out / "log.jsonl", "a")
    best = float("inf")
    for epoch in range(1, args.epochs + 1):
        t0, running, count = time.time(), 0.0, 0
        for frames, targets, valid in train_ds.batches(args.batch_size):
            x = augment(frames)
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=x.is_cuda):
                out = model(x)
            loss = model.loss(out, targets, valid.float())
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            running, count = running + float(loss), count + 1
        val = evaluate(model, val_ds, args.batch_size * 2)
        row = {"epoch": epoch, "train_loss": running / max(count, 1), **{"val_" + k: v for k, v in val.items()},
               "lr": sched.get_last_lr()[0], "seconds": time.time() - t0}
        print("época %3d  treino %.4f  val %.4f  acc %.3f  erro steer %.3f  (%.0fs)" % (
            epoch, row["train_loss"], val["loss"], val["acc"], val["steer_mae"], row["seconds"]), flush=True)
        log.write(json.dumps(row) + "\n")
        log.flush()
        ckpt = model.checkpoint(epoch=epoch, val=val, args={k: str(v) for k, v in vars(args).items()})
        torch.save(ckpt, args.out / "last.pt")
        if val["loss"] < best:
            best = val["loss"]
            torch.save(ckpt, args.out / "model.pt")
    print("melhor val loss %.4f -> %s" % (best, args.out / "model.pt"))


if __name__ == "__main__":
    main()
