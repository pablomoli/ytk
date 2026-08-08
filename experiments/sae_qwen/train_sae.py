"""Top-k sparse autoencoder trained directly on the production Qwen v2 space.

Gao et al. 2024 formulation: pre-encoder bias, ReLU->TopK latents, untied
decoder with unit-norm columns, AuxK loss to revive dead latents.

    uv run --with torch python experiments/sae_qwen/train_sae.py --sweep
    uv run --with torch python experiments/sae_qwen/train_sae.py --dict 4096 --k 32 --seed 0
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
CKPT = HERE / "checkpoints"

DEAD_STEPS = 500  # latent unseen for this many steps counts as dead for AuxK
AUX_K = 256
AUX_COEF = 1 / 32
EVAL_EVERY = 250  # val recon peaks near step 2000 then decays (n=15k); keep the best


class TopKSAE(nn.Module):
    def __init__(self, d_in: int, d_sae: int, k: int):
        super().__init__()
        self.k = k
        self.d_sae = d_sae
        self.b_pre = nn.Parameter(torch.zeros(d_in))
        self.enc = nn.Linear(d_in, d_sae, bias=True)
        self.W_dec = nn.Parameter(torch.empty(d_sae, d_in))
        nn.init.kaiming_uniform_(self.W_dec, a=5**0.5)
        self.normalize_decoder()
        with torch.no_grad():
            self.enc.weight.copy_(self.W_dec.clone())
            self.enc.bias.zero_()

    @torch.no_grad()
    def normalize_decoder(self):
        self.W_dec.div_(self.W_dec.norm(dim=1, keepdim=True).clamp_min(1e-8))

    def pre_acts(self, x):
        return torch.relu(self.enc(x - self.b_pre))

    def topk(self, pre, k):
        vals, idx = pre.topk(k, dim=-1)
        z = torch.zeros_like(pre)
        return z.scatter_(-1, idx, vals), idx

    def decode(self, z):
        return z @ self.W_dec + self.b_pre

    def forward(self, x):
        pre = self.pre_acts(x)
        z, idx = self.topk(pre, self.k)
        return self.decode(z), pre, z, idx


def load_data(seed: int, val_frac: float = 0.10):
    X = np.load(DATA / "vectors.npz")["X"]
    rows = [json.loads(line) for line in (DATA / "rows.jsonl").read_text().splitlines()]
    keys = np.array([r["note_key"] for r in rows])
    uniq = np.array(sorted(set(keys.tolist())))
    rng = np.random.default_rng(1000 + seed)
    held = set(rng.permutation(uniq)[: round(val_frac * len(uniq))].tolist())
    val_mask = np.array([k in held for k in keys])
    return X, rows, ~val_mask, val_mask


def metrics(model, X, device, batch=4096):
    model.eval()
    cos, fvu_num, fvu_den, l0 = [], 0.0, 0.0, []
    fired = torch.zeros(model.d_sae, dtype=torch.bool, device=device)
    with torch.no_grad():
        mu = torch.as_tensor(X, device=device).mean(0)
        for i in range(0, len(X), batch):
            x = torch.as_tensor(X[i : i + batch], device=device)
            xh, _, z, _ = model(x)
            cos.append(torch.cosine_similarity(x, xh, dim=-1).cpu())
            fvu_num += ((x - xh) ** 2).sum().item()
            fvu_den += ((x - mu) ** 2).sum().item()
            l0.append((z > 0).sum(-1).float().cpu())
            fired |= (z > 0).any(0)
    return {
        "recon_cos": float(torch.cat(cos).mean()),
        "fvu": fvu_num / fvu_den,
        "l0": float(torch.cat(l0).mean()),
        "alive_frac": float(fired.float().mean()),
    }


def train(
    d_sae: int,
    k: int,
    seed: int,
    steps: int,
    device: str,
    restrict: bool,
    bs: int = 1024,
    quiet=False,
    split_seed: int | None = None,
):
    torch.manual_seed(seed)
    X, rows, tr, va = load_data(seed if split_seed is None else split_seed)
    if restrict:
        keep = np.array([r["in_dist"] for r in rows])
        tr = tr & keep
    Xtr = torch.as_tensor(X[tr], device=device)
    Xva = X[va]
    Xva_in = X[va & np.array([r["in_dist"] for r in rows])]
    Xva_out = X[va & ~np.array([r["in_dist"] for r in rows])]

    model = TopKSAE(X.shape[1], d_sae, k).to(device)
    with torch.no_grad():
        model.b_pre.copy_(Xtr.mean(0))
    opt = torch.optim.Adam(model.parameters(), lr=3e-4, betas=(0.9, 0.999), eps=1e-8)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / 500))
    last_fired = torch.zeros(d_sae, dtype=torch.long, device=device)
    g = torch.Generator(device="cpu").manual_seed(seed)
    n = len(Xtr)
    order = torch.randint(0, n, (steps, bs), generator=g).to(device)
    t0 = time.time()
    dead_any = False
    curve: list[tuple[int, float]] = []
    best: tuple[float, int, dict] = (-1.0, 0, {})
    for step in range(steps):
        model.train()
        x = Xtr[order[step]]
        xh, pre, z, _ = model(x)
        resid = x - xh
        loss = (resid**2).sum(-1).mean()

        if step > DEAD_STEPS and step % 25 == 0:
            dead_any = bool(((step - last_fired) > DEAD_STEPS).any().item())
        if dead_any:
            dead = (step - last_fired) > DEAD_STEPS
            kaux = AUX_K
            masked = pre.masked_fill(~dead, 0.0)
            zaux, _ = model.topk(masked, kaux)
            raux = zaux @ model.W_dec
            loss = loss + AUX_COEF * ((resid.detach() - raux) ** 2).sum(-1).mean()

        opt.zero_grad(set_to_none=True)
        loss.backward()
        # remove the gradient component parallel to each unit-norm decoder row
        with torch.no_grad():
            gd = model.W_dec.grad
            gd -= (gd * model.W_dec).sum(-1, keepdim=True) * model.W_dec
        opt.step()
        sched.step()
        model.normalize_decoder()
        with torch.no_grad():
            last_fired[(z > 0).any(0)] = step
        if (step + 1) % EVAL_EVERY == 0:
            m = metrics(model, Xva, device)
            curve.append((step + 1, m["recon_cos"]))
            if m["recon_cos"] > best[0]:
                best = (
                    m["recon_cos"],
                    step + 1,
                    {k_: v.detach().clone() for k_, v in model.state_dict().items()},
                )
            if not quiet:
                print(f"  step {step + 1:6d} loss {loss.item():.4f} val_cos {m['recon_cos']:.4f}")

    model.load_state_dict(best[2])
    out = {
        "d_sae": d_sae,
        "k": k,
        "seed": seed,
        "steps": steps,
        "best_step": best[1],
        "batch": bs,
        "curve": curve,
        "restrict": restrict,
        "n_train": int(tr.sum()),
        "n_val": int(va.sum()),
        "secs": round(time.time() - t0, 1),
        "val": metrics(model, Xva, device),
        "train": metrics(model, X[tr], device),
        "val_in_dist": metrics(model, Xva_in, device) if len(Xva_in) else None,
        "val_out_dist": metrics(model, Xva_out, device) if len(Xva_out) else None,
        "dead_frac_on_train": 1.0 - metrics(model, X[tr], device)["alive_frac"],
    }
    return model, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--dict", type=int, default=4096)
    ap.add_argument("--k", type=int, default=32)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--steps", type=int, default=6000)
    ap.add_argument("--batch", type=int, default=1024)
    ap.add_argument("--restrict", action="store_true")
    ap.add_argument("--device", default="mps")
    ap.add_argument("--tag", default="sweep")
    ap.add_argument("--prefix", default="sae")
    ap.add_argument("--split-seed", type=int, default=None)
    a = ap.parse_args()

    CKPT.mkdir(exist_ok=True)
    combos = [(d, k) for d in (2048, 4096) for k in (16, 32)] if a.sweep else [(a.dict, a.k)]
    seeds = range(a.seeds) if a.sweep else [a.seed]
    results = []
    for d, k in combos:
        for s in seeds:
            print(f"== dict={d} k={k} seed={s} restrict={a.restrict}")
            model, out = train(
                d,
                k,
                s,
                a.steps,
                a.device,
                a.restrict,
                bs=a.batch,
                quiet=True,
                split_seed=a.split_seed,
            )
            print("  ", json.dumps(out["val"]), "dead", round(out["dead_frac_on_train"], 4))
            results.append(out)
            torch.save(
                {"state": model.state_dict(), "cfg": {"d_sae": d, "k": k, "seed": s}},
                CKPT / f"{a.prefix}_d{d}_k{k}_s{s}{'_restrict' if a.restrict else ''}.pt",
            )
    (HERE / f"results_{a.tag}.json").write_text(json.dumps(results, indent=1))
    print("wrote", HERE / f"results_{a.tag}.json")


if __name__ == "__main__":
    main()
