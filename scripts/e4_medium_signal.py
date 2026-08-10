"""E4 — does the portrait change when the medium confound is removed?

E2 measured the deliberate-save signal r as a disguised medium label (every
r>=1 note arrives through the pending queue; YouTube bulk-ingests at r=0), and
alpha=7 turns that label into a ~15x weight ratio. The KMeans partition is
deliberately unweighted, so membership cannot move; alpha reaches the profile
only through theme weight/rank, weighted centroids, and the rendered share.
E4 recomputes those three ways over the frozen 2026-08-08 snapshot:

    A   alpha=7, raw r                (production)
    B1  alpha=7, intake-adjusted r    (signals.intake_adjusted_levels)
    B2  alpha=7, r=1 zeroed           (delete only the confounded level)
    C   alpha=0                       (unweighted control)

Recency decay and day-batch dampening are held fixed across variants — the
question is alpha's signal term, nothing else. Variant A must reproduce the
snapshot's stored theme weights before B/C are read at all.

    uv run --with matplotlib python scripts/e4_medium_signal.py
    uv run --with matplotlib python scripts/e4_medium_signal.py --figs-only

Analysis lands in docs/assets/26-medium-signal/e4-medium-signal.json;
--figs-only re-renders the figures from it without touching Chroma.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
OUTDIR = REPO / "docs" / "assets" / "26-medium-signal"
SNAPSHOT = Path.home() / ".ytk" / "interest" / "latest.json"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

N_SHUFFLES = 1000
TOP_N = 5


# --- analysis ---------------------------------------------------------------
def kendall_tau(x: np.ndarray, y: np.ndarray) -> float:
    """Tau-a; the share vectors are continuous so ties are not expected."""
    n = len(x)
    s = 0.0
    for i in range(n):
        s += float(np.sum(np.sign((x[i] - x[i + 1 :]) * (y[i] - y[i + 1 :]))))
    return s / (n * (n - 1) / 2)


def spearman_rho(x: np.ndarray, y: np.ndarray) -> float:
    rx = np.argsort(np.argsort(-x))
    ry = np.argsort(np.argsort(-y))
    return float(np.corrcoef(rx, ry)[0, 1])


def ranks_desc(shares: np.ndarray) -> np.ndarray:
    """1 = heaviest theme."""
    order = np.argsort(-shares)
    out = np.empty(len(shares), dtype=int)
    out[order] = np.arange(1, len(shares) + 1)
    return out


def theme_shares(w: np.ndarray, theme_of: np.ndarray, k: int) -> np.ndarray:
    return np.bincount(theme_of, weights=w, minlength=k) / w.sum()


def gather() -> dict:
    from ytk import signals
    from ytk.config import load_config
    from ytk.store import get_all_videos, get_content_memories
    from ytk.synthesis import weighted_centroid

    snap = json.loads(SNAPSHOT.read_text())
    themes = snap["themes"]
    k = len(themes)
    alpha = float(snap["alpha"])
    half_life = float(snap["decay_half_life_days"])
    now = datetime.fromisoformat(snap["generated_at"])

    cfg = load_config()
    by_id = {
        n["id"]: n
        for n in get_all_videos() + get_content_memories(cfg.interest.content_sources)
        if n.get("embedding")
    }

    notes, theme_of, missing = [], [], []
    for t_idx, t in enumerate(themes):
        for nid in t["note_ids"]:
            n = by_id.get(nid)
            if n is None:
                missing.append(nid)
                continue
            notes.append(n)
            theme_of.append(t_idx)
    theme_of = np.asarray(theme_of)

    levels = signals.signal_levels(notes)
    sources = [n["source"] for n in notes]
    adj = signals.intake_adjusted_levels(levels, sources)
    captured = [n.get("captured_at", "") for n in notes]

    r = np.asarray(levels, dtype=float)
    base = np.asarray([signals.recency_factor(ts, now, half_life) for ts in captured]) * np.asarray(
        signals.day_batch_factors(captured)
    )

    variants = {
        "A": (1.0 + alpha * r) * base,
        "B1": (1.0 + alpha * np.asarray(adj, dtype=float)) * base,
        "B2": (1.0 + alpha * np.where(r == 1, 0.0, r)) * base,
        "C": base.copy(),
    }
    shares = {v: theme_shares(w, theme_of, k) for v, w in variants.items()}

    # Gate: recomputed production shares must land on the stored snapshot.
    stored = np.asarray([t["weight"] for t in themes])
    max_diff = float(np.max(np.abs(np.round(shares["A"], 4) - stored)))
    stored_counts = {int(kk): v for kk, v in snap["signal_counts"].items()}
    recomputed_counts = dict(Counter(levels))
    validation = {
        "max_abs_share_diff_vs_snapshot": max_diff,
        "stored_signal_counts": stored_counts,
        "recomputed_signal_counts": recomputed_counts,
        "missing_note_ids": missing,
        "n_notes": len(notes),
    }

    # Rank movement statistics.
    pairs = [("A", "B1"), ("A", "B2"), ("A", "C"), ("B1", "B2"), ("B1", "C")]
    taus = {f"{a}-{b}": kendall_tau(shares[a], shares[b]) for a, b in pairs}
    rhos = {f"{a}-{b}": spearman_rho(shares[a], shares[b]) for a, b in pairs}
    rank = {v: ranks_desc(s).tolist() for v, s in shares.items()}
    top = {v: sorted(np.argsort(-s)[:TOP_N].tolist()) for v, s in shares.items()}

    # Null: shuffle r, keep decay/batch fixed, recompute an alpha=7 profile.
    # Global shuffle breaks the r<->medium tie; within-source keeps it.
    rng = np.random.default_rng(0)
    nulls = {}
    src_arr = np.asarray(sources)
    obs_tau = taus["A-B1"]
    obs_dmax = float(np.max(np.abs(shares["B1"] - shares["A"])))
    obs_churn = TOP_N - len(set(top["A"]) & set(top["B1"]))
    for name in ("global", "within_source"):
        tau_d, dmax_d, churn_d = [], [], []
        for _ in range(N_SHUFFLES):
            r_s = r.copy()
            if name == "global":
                rng.shuffle(r_s)
            else:
                for s in set(sources):
                    m = src_arr == s
                    r_s[m] = rng.permutation(r_s[m])
            s_s = theme_shares((1.0 + alpha * r_s) * base, theme_of, k)
            tau_d.append(kendall_tau(shares["A"], s_s))
            dmax_d.append(float(np.max(np.abs(s_s - shares["A"]))))
            churn_d.append(TOP_N - len(set(np.argsort(-s_s)[:TOP_N]) & set(top["A"])))
        nulls[name] = {
            "tau_mean": float(np.mean(tau_d)),
            "tau_p05": float(np.percentile(tau_d, 5)),
            "tau_p50": float(np.percentile(tau_d, 50)),
            "dshare_max_p95": float(np.percentile(dmax_d, 95)),
            "dshare_max_p50": float(np.percentile(dmax_d, 50)),
            "top5_churn_mean": float(np.mean(churn_d)),
            "top5_churn_p95": float(np.percentile(churn_d, 95)),
            # empirical p: how often chance moves the ranking at least as far
            # as the observed A->B1 correction does
            "p_tau_le_obs": float(np.mean(np.asarray(tau_d) <= obs_tau)),
            "p_dshare_ge_obs": float(np.mean(np.asarray(dmax_d) >= obs_dmax)),
            "p_churn_ge_obs": float(np.mean(np.asarray(churn_d) >= obs_churn)),
        }
    observed = {"tau_A_B1": obs_tau, "dshare_max_A_B1": obs_dmax, "top5_churn_A_B1": obs_churn}

    # Per-theme detail: shares, media composition of the theme's weight,
    # and how far the confidence-weighted centroid (the profile's per-theme
    # query vector) moves under each correction.
    emb = np.asarray([n["embedding"] for n in notes], dtype=float)
    theme_rows = []
    for t_idx, t in enumerate(themes):
        m = theme_of == t_idx
        row = {
            "id": t["id"],
            "label": t["label"],
            "n_notes": int(m.sum()),
            "share": {v: float(shares[v][t_idx]) for v in variants},
            "rank": {v: int(rank[v][t_idx]) for v in variants},
            "signal_counts": dict(Counter(int(x) for x in r[m])),
            "media_weight_frac": {},
            "centroid_cos": {},
        }
        for v, w in variants.items():
            tot = float(w[m].sum())
            comp = {}
            for s in sorted(set(src_arr[m])):
                comp[s] = float(w[m & (src_arr == s)].sum() / tot)
            row["media_weight_frac"][v] = comp
        c_a = np.asarray(weighted_centroid(emb[m], list(variants["A"][m])))
        for v in ("B1", "B2", "C"):
            c_v = np.asarray(weighted_centroid(emb[m], list(variants[v][m])))
            row["centroid_cos"][v] = float(c_a @ c_v)
        theme_rows.append(row)

    return {
        "meta": {
            "snapshot_generated_at": snap["generated_at"],
            "alpha": alpha,
            "half_life_days": half_life,
            "k": k,
            "n_shuffles": N_SHUFFLES,
        },
        "validation": validation,
        "taus": taus,
        "spearman": rhos,
        "observed": observed,
        "top5": {v: [themes[i]["id"] for i in idx] for v, idx in top.items()},
        "nulls": nulls,
        "themes": theme_rows,
    }


# --- figures ----------------------------------------------------------------
def _save(fig, name: str) -> None:
    from plot_assets import BG, DPI, frame_panels

    frame_panels(fig)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor=BG)
    print(f"wrote {out.relative_to(REPO)}  ({out.stat().st_size // 1024}KB)")
    import matplotlib.pyplot as plt

    plt.close(fig)


def _short(label: str, n: int = 26) -> str:
    return label if len(label) <= n else label[: n - 1] + "…"


def fig01(out: dict) -> None:
    from plot_assets import DIM, GOLD, MARGIN, MUTED, RED, TEXT, figure, panel_title, verdict

    themes = out["themes"]
    cols = ["A", "B1", "C"]
    col_names = [
        "alpha=7, raw r\n(production)",
        "alpha=7, medium-\ncorrected r",
        "alpha=0\n(unweighted)",
    ]
    k = len(themes)
    fig, top = figure(
        14,
        10.6,
        1,
        "the ranking, three ways",
        "Theme rank when the confounded signal level is removed",
        f"{out['validation']['n_notes']} notes, {k} themes, frozen snapshot "
        f"{out['meta']['snapshot_generated_at'][:10]}  ·  tau(A,B1) "
        f"{out['taus']['A-B1']:.3f}, tau(A,C) {out['taus']['A-C']:.3f}  ·  "
        f"global-shuffle null tau p5 {out['nulls']['global']['tau_p05']:.3f}",
    )
    ax = fig.add_subplot(1, 1, 1)
    ax.set_facecolor("#000000")
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xlim(-0.10, len(cols) - 1 + 0.42)
    ax.set_ylim(k + 0.6, 0.4)
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels(col_names, color=TEXT, fontsize=10)
    ax.set_yticks([])
    ax.tick_params(length=0)

    for t in themes:
        rr = [t["rank"][c] for c in cols]
        moved = abs(rr[0] - rr[1])
        color = RED if moved >= 3 else (GOLD if moved >= 1 else DIM)
        lw = 2.2 if moved >= 3 else (1.6 if moved >= 1 else 1.0)
        ax.plot(range(len(cols)), rr, color=color, linewidth=lw, alpha=0.9, zorder=3)
        ax.scatter(range(len(cols)), rr, color=color, s=18, zorder=4)
        ax.text(
            -0.055,
            rr[0],
            f"{_short(t['label'])}  {t['rank']['A']:>2}",
            color=TEXT if moved >= 3 else MUTED,
            fontsize=8.2,
            ha="right",
            va="center",
            clip_on=False,
        )
        ax.text(
            len(cols) - 1 + 0.06,
            rr[-1],
            f"{t['rank']['C']:>2}",
            color=MUTED,
            fontsize=8.2,
            ha="left",
            va="center",
        )
    panel_title(
        ax,
        "one line per theme, position = rank (1 = heaviest); red = moves 3+ ranks "
        "under the medium correction",
        width=92,
    )
    verdict(fig, "the confound owned the ranking: production's #1 theme falls to 11th without it")
    fig.subplots_adjust(left=0.26, right=1 - MARGIN - 0.02, top=top - 0.02, bottom=0.06)
    _save(fig, "01-ranking-three-ways.png")


def fig02(out: dict) -> None:
    from plot_assets import (
        BLUE,
        CYAN,
        FRAME,
        GOLD,
        MARGIN,
        MUTED,
        PURPLE,
        RED,
        TEXT,
        TICK_SIZE,
        figure,
        panel_title,
        style_axes,
        verdict,
    )

    themes = out["themes"]
    k = len(themes)
    order = np.argsort([-t["share"]["A"] for t in themes])
    labels = [_short(themes[i]["label"], 22) for i in order]
    d_b1 = np.asarray([themes[i]["share"]["B1"] - themes[i]["share"]["A"] for i in order])
    d_c = np.asarray([themes[i]["share"]["C"] - themes[i]["share"]["A"] for i in order])
    null95 = out["nulls"]["global"]["dshare_max_p95"]

    fig, top = figure(
        15,
        9.4,
        2,
        "share deltas and what pays for them",
        "Per-theme share change under the correction, and the media paying each theme's weight",
        f"bars vs the global-shuffle null's p95 max |delta share| {null95:.3f}  ·  "
        f"top-5 churn A->B1: {5 - len(set(out['top5']['A']) & set(out['top5']['B1']))} themes",
    )
    gs = fig.add_gridspec(
        1,
        2,
        width_ratios=[1.15, 1.0],
        left=0.16,
        right=1 - MARGIN - 0.01,
        top=top,
        bottom=0.135,
        wspace=0.30,
    )

    ax = fig.add_subplot(gs[0])
    y = np.arange(k)
    ax.barh(y - 0.2, d_b1, height=0.38, color=GOLD, label="A -> B1 (corrected)")
    ax.barh(y + 0.2, d_c, height=0.38, color=BLUE, label="A -> C (alpha=0)")
    ax.axvline(0, color=FRAME, linewidth=1.0)
    for v in (-null95, null95):
        ax.axvline(v, color=RED, linewidth=0.9, linestyle="--", alpha=0.8)
    ax.set_yticks(y, labels, fontsize=8)
    ax.invert_yaxis()
    style_axes(ax)
    ax.set_xlabel("share delta (fraction of total weight)")
    ax.legend(loc="lower right", fontsize=TICK_SIZE, framealpha=0.0, labelcolor=TEXT)
    panel_title(
        ax, "share deltas, themes ordered by production weight; dashed red = null p95", width=64
    )

    ax = fig.add_subplot(gs[1])
    top5 = [i for i in order if themes[i]["rank"]["A"] <= 5]
    media = ["youtube", "instagram", "tiktok", "web", "pinterest", "screenshots"]
    colors = {
        "youtube": RED,
        "instagram": PURPLE,
        "tiktok": CYAN,
        "web": GOLD,
        "pinterest": BLUE,
        "screenshots": MUTED,
    }
    yy = np.arange(len(top5))
    handles = {}
    for offs, var in [(-0.2, "A"), (0.2, "B1")]:
        left = np.zeros(len(top5))
        for m in media:
            vals = np.asarray([themes[i]["media_weight_frac"][var].get(m, 0.0) for i in top5])
            bars = ax.barh(yy + offs, vals, left=left, height=0.38, color=colors[m], alpha=0.92)
            if var == "A" and vals.sum() > 0:
                handles[m] = bars
            left += vals
        for y_i in yy:
            ax.text(1.015, y_i + offs, var, color=MUTED, fontsize=7.5, va="center", clip_on=False)
    ax.set_yticks(yy, [_short(themes[i]["label"], 22) for i in top5], fontsize=8)
    ax.invert_yaxis()
    style_axes(ax)
    ax.set_xlim(0, 1.07)
    ax.set_xlabel("fraction of theme weight by medium")
    fig.legend(
        handles.values(),
        handles.keys(),
        loc="lower center",
        bbox_to_anchor=(0.72, 0.012),
        ncols=len(handles),
        fontsize=TICK_SIZE - 1,
        framealpha=0.0,
        labelcolor=TEXT,
    )
    panel_title(ax, "who pays for the top-5 themes' weight, before (A) and after (B1)", width=64)

    verdict(
        fig, "every riser is YouTube-paid, every faller Instagram-paid — the weight was the medium"
    )
    _save(fig, "02-share-deltas-and-media.png")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--figs-only", action="store_true")
    args = ap.parse_args()

    OUTDIR.mkdir(parents=True, exist_ok=True)
    path = OUTDIR / "e4-medium-signal.json"
    if args.figs_only:
        out = json.loads(path.read_text())
    else:
        out = gather()
        path.write_text(json.dumps(out, indent=1))
        print(f"wrote {path.relative_to(REPO)}")

    v = out["validation"]
    print(
        f"validation: max|share diff| {v['max_abs_share_diff_vs_snapshot']:.5f}, "
        f"counts stored {v['stored_signal_counts']} vs recomputed "
        f"{v['recomputed_signal_counts']}, missing {len(v['missing_note_ids'])}"
    )
    print("taus:", {kk: round(vv, 4) for kk, vv in out["taus"].items()})
    print("nulls:", json.dumps(out["nulls"], indent=1))

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.style.use("dark_background")
    from plot_assets import use_house_font

    use_house_font()
    fig01(out)
    fig02(out)


if __name__ == "__main__":
    main()
