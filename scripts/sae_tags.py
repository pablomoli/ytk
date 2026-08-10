#!/usr/bin/env python
"""18.4 — tag regions as differential feature sets (pre-registered).

Per tag: mean fingerprint (per-note mass shares) minus corpus mean, scored
as z against a tag-shuffle null (labels permuted across notes, per tag
size). Registered: top features topically coherent for >= 7 of the 10
largest tags (judged per tag, set-wise, in 18-sae-fingerprints/README.md); quantitative
companion: pairwise tag feature-set Jaccard correlates with Qwen centroid
cosine at r >= 0.4. Control: shuffled labels kill the differential.
Kill: fewer than 4 of 10 tags coherent.

    analyze -> tag-regions.json
    plot    -> 03-tag-regions.png, 04-tag-geometry.png

    uv run --with matplotlib python scripts/sae_tags.py
"""

from __future__ import annotations

import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_assets import (
    BLUE,
    CYAN,
    DPI,
    GOLD,
    MARGIN,
    MUTED,
    RED,
    TICK_SIZE,
    figure,
    frame_panels,
    panel_title,
    style_axes,
)

OUTDIR = Path(__file__).resolve().parents[1] / "docs" / "assets" / "18-sae-fingerprints"
GROWTH = OUTDIR.parent / "17-corpus-growth"
MODEL_ID = "gemma-2-2b"
LAYER = "20-gemmascope-res-16k"
SEED = 20260805
N_TAGS = 10
TOP_F = 8  # differential features shown per tag
SET_F = 15  # set size for the registered Jaccard companion (18-sae-fingerprints/README.md)
NULL_DRAWS = 200


def save(fig, name: str) -> None:
    frame_panels(fig)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor="#08080a")
    print(f"wrote {out.relative_to(OUTDIR.parents[2])}  ({out.stat().st_size // 1024}KB)")
    plt.close(fig)


def fetch_names(indices: list[int]) -> dict[int, str]:
    out: dict[int, str] = {}
    for start in range(0, len(indices), 90):
        body = [
            {"modelId": MODEL_ID, "layer": LAYER, "index": int(i)}
            for i in indices[start : start + 90]
        ]
        req = urllib.request.Request(
            "https://www.neuronpedia.org/api/features",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            for f in json.loads(resp.read()):
                exps = f.get("explanations") or []
                out[int(f["index"])] = exps[0].get("description", "(none)") if exps else "(none)"
    return out


def load():
    data = np.load(OUTDIR / "fingerprints.npz")
    S = data["sum"].astype(np.float32)
    F = S / (S.sum(axis=1, keepdims=True) + 1e-9)  # per-note mass shares
    meta = json.loads((GROWTH / "tags-fresh.json").read_text())
    X = np.load(GROWTH / "vectors-fresh.npz")["X"].astype(np.float32)
    return F, meta["labels"], X


def analyze() -> dict:
    F, labels, X = load()
    rng = np.random.default_rng(SEED)
    counts = Counter(t for ts in labels for t in ts)
    tags = [t for t, _ in counts.most_common(N_TAGS)]
    corpus_mean = F.mean(axis=0)

    per_tag = {}
    null_cache: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for tag in tags:
        idx = [i for i, ts in enumerate(labels) if tag in ts]
        k = len(idx)
        if k not in null_cache:
            draws = np.stack(
                [
                    F[rng.choice(len(F), size=k, replace=False)].mean(axis=0) - corpus_mean
                    for _ in range(NULL_DRAWS)
                ]
            )
            null_cache[k] = (draws.mean(axis=0), draws.std(axis=0) + 1e-12)
        mu0, sd0 = null_cache[k]
        diff = F[idx].mean(axis=0) - corpus_mean
        z = (diff - mu0) / sd0
        top = np.argsort(-z)[:TOP_F]
        per_tag[tag] = {
            "n": k,
            "set15": [int(i) for i in np.argsort(-z)[:SET_F]],
            "top": [
                {"index": int(i), "z": round(float(z[i]), 1), "share": float(F[idx, i].mean())}
                for i in top
            ],
            "n_sig": int((z > 4).sum()),
            "max_null_z": None,  # filled below from the shuffle check
        }

    # control: shuffled labels for the largest tag — how big do z's get by chance
    k = per_tag[tags[0]]["n"]
    null_z_max = []
    for _ in range(50):
        idx = rng.choice(len(F), size=k, replace=False)
        mu0, sd0 = null_cache[k]
        z = (F[idx].mean(axis=0) - corpus_mean - mu0) / sd0
        null_z_max.append(float(z.max()))
    for tag in tags:
        per_tag[tag]["max_null_z"] = round(float(np.percentile(null_z_max, 95)), 1)

    # geometry companion: per-pair Jaccard of top-F sets vs Qwen centroid cosine
    cents = {}
    for tag in tags:
        idx = [i for i, ts in enumerate(labels) if tag in ts]
        c = X[idx].mean(axis=0)
        cents[tag] = c / (np.linalg.norm(c) + 1e-12)
    sets = {t: set(per_tag[t]["set15"]) for t in tags}
    pairs = []
    for a in range(len(tags)):
        for b in range(a + 1, len(tags)):
            ta, tb = tags[a], tags[b]
            jac = len(sets[ta] & sets[tb]) / len(sets[ta] | sets[tb])
            cos = float(cents[ta] @ cents[tb])
            pairs.append({"a": ta, "b": tb, "jaccard": round(jac, 4), "cos": round(cos, 4)})
    jr = np.array([p["jaccard"] for p in pairs])
    cr = np.array([p["cos"] for p in pairs])
    r = float(np.corrcoef(jr, cr)[0, 1])

    names = fetch_names(sorted({f["index"] for t in tags for f in per_tag[t]["top"]}))
    for t in tags:
        for f in per_tag[t]["top"]:
            f["name"] = names.get(f["index"], "(unfetched)")

    out = {
        "seed": SEED,
        "null_draws": NULL_DRAWS,
        "tags": tags,
        "per_tag": per_tag,
        "pairs": pairs,
        "jaccard_cos_r": round(r, 3),
        "null_z_p95": round(float(np.percentile(null_z_max, 95)), 1),
    }
    (OUTDIR / "tag-regions.json").write_text(json.dumps(out, indent=1))
    print(f"jaccard-vs-cosine r = {r:.3f}  (registered >= 0.4)")
    print(f"null max-z p95 = {out['null_z_p95']}")
    for t in tags:
        top = per_tag[t]["top"][:3]
        print(
            f"  {t:16s} n={per_tag[t]['n']:<4} "
            + " | ".join(f"{f['name'][:34]} (z{f['z']:.0f})" for f in top)
        )
    return out


def plot() -> None:
    r = json.loads((OUTDIR / "tag-regions.json").read_text())
    tags = r["tags"]

    fig, top = figure(
        16.5,
        10.0,
        3,
        "sae fingerprints",
        "Ten tags, each with its own vocabulary of features",
        f"top {TOP_F} differential features per tag, z against tag-shuffle null "
        f"({r['null_draws']} draws, size-matched)  ·  chance p95 max-z = {r['null_z_p95']}  ·  "
        "names are auto-explanations: hypotheses, read as sets",
    )
    gs = fig.add_gridspec(
        2,
        5,
        left=0.055,
        right=1 - MARGIN - 0.01,
        top=top,
        bottom=0.10,
        hspace=0.62,
        wspace=0.14,
    )
    for k, tag in enumerate(tags):
        ax = fig.add_subplot(gs[k // 5, k % 5])
        feats = r["per_tag"][tag]["top"]
        zs = [f["z"] for f in feats][::-1]
        names = [f["name"][:34] for f in feats][::-1]
        y = np.arange(len(feats))
        ax.barh(y, zs, height=0.62, color=GOLD, alpha=0.9)
        ax.axvline(r["null_z_p95"], color=RED, linewidth=1.0, linestyle="--")
        for yi, name in zip(y, names):
            ax.text(0.25, yi, name, va="center", ha="left", color="#08080a", fontsize=6.2)
        ax.set_yticks([])
        ax.tick_params(axis="x", labelsize=7)
        style_axes(ax)
        panel_title(ax, f"{tag}  ·  {r['per_tag'][tag]['n']} notes", width=30)
        if k >= 5:
            ax.set_xlabel("differential z", fontsize=8)
    fig.text(
        MARGIN,
        0.035,
        "Every tag's differential features tower over the shuffle null (red dashes). Reading the"
        " sets, not single names: each panel should smell like its tag — that judgment, per tag,"
        " is recorded in 18-sae-fingerprints/README.md.",
        color=MUTED,
        fontsize=9.5,
    )
    save(fig, "03-tag-regions.png")

    fig, top = figure(
        16.5,
        6.8,
        4,
        "sae fingerprints",
        "Two spaces, one map: tags that sit together share feature vocabulary",
        f"45 tag pairs  ·  x = Qwen centroid cosine, y = Jaccard of top-{SET_F} feature sets "
        f"(quantized at fifteenths)  ·  "
        f"r = {r['jaccard_cos_r']} (registered >= 0.4)",
    )
    gs = fig.add_gridspec(1, 1, left=0.30, right=0.70, top=top, bottom=0.19)
    ax = fig.add_subplot(gs[0])
    jr = [p["jaccard"] for p in r["pairs"]]
    cr = [p["cos"] for p in r["pairs"]]
    from collections import Counter as _C

    multiplicity = _C(zip(cr, jr))
    ax.scatter(cr, jr, s=34, c=GOLD, alpha=0.75, linewidths=0)
    for (cx, jy), m in multiplicity.items():
        if m > 1:
            ax.annotate(
                f"x{m}",
                (cx, jy),
                textcoords="offset points",
                xytext=(0, 7),
                color=MUTED,
                fontsize=6.6,
                ha="center",
            )
    hi = sorted(r["pairs"], key=lambda p: -(p["jaccard"] + p["cos"]))[:4]
    lo = sorted(r["pairs"], key=lambda p: p["cos"])[:2]
    for p in hi + lo:
        ax.annotate(
            f"{p['a']} + {p['b']}",
            (p["cos"], p["jaccard"]),
            textcoords="offset points",
            xytext=(7, 4),
            color=CYAN,
            fontsize=7.6,
        )
    m, b = np.polyfit(cr, jr, 1)
    xs = np.linspace(min(cr), max(cr), 20)
    ax.plot(
        xs,
        np.clip(m * xs + b, 0, None),
        color=BLUE,
        linewidth=1.4,
        linestyle="--",
        label="least squares (clipped at 0)",
    )
    leg = ax.legend(frameon=False, fontsize=TICK_SIZE, loc="upper left")
    for t in leg.get_texts():
        t.set_color(MUTED)
    style_axes(ax)
    ax.set_xlabel("tag centroid cosine (Qwen space)")
    ax.set_ylabel("feature-set Jaccard (SAE space)")
    panel_title(ax, "geometry agreement across encoders", width=44)
    save(fig, "04-tag-geometry.png")


if __name__ == "__main__":
    analyze()
    plot()
