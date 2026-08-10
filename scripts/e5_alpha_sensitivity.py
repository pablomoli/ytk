"""E5 — does alpha still matter once the signal is medium-corrected?

alpha=7 (ytk/config.py, w = 1 + alpha*r) was fitted 2026-07-05 by 5-fold
held-out-save retrieval — the same confounded target E2 unmasked as a medium
label, a defect eval_profile.py's own docstring recorded the day it shipped.
The honest refit is still blocked: the vault has no within-source contrast
(7 YouTube saves against 350 passives; zero saved-source passives), so no
target derived from r can be de-confounded on today's corpus. E5 asks the
narrower, answerable question: sweep alpha over {0,1,3,7,15,31} in two arms —

    raw       w = 1 + alpha*r          (medium_controlled: false)
    adjusted  w = 1 + alpha*r'         (r' = signals.intake_adjusted_levels)

— on the frozen 2026-08-08 snapshot with recency decay and day-batch
dampening held fixed, and measure how far the portrait's between-theme
accounting (rank, share, top-5, media composition) moves relative to the
shipped alpha=7 reference. Chance scale: E4's medium-preserving
within-source shuffle null, run per arm, one label vector per shuffle across
the whole sweep. Raw alpha=7 must reproduce the snapshot's stored theme
weights before anything else is read.

    uv run --with matplotlib python scripts/e5_alpha_sensitivity.py
    uv run --with matplotlib python scripts/e5_alpha_sensitivity.py --figs-only

Analysis lands in docs/assets/27-alpha-sensitivity/e5-alpha-sensitivity.json;
--figs-only re-renders the figures from it without touching Chroma.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
OUTDIR = REPO / "docs" / "assets" / "27-alpha-sensitivity"
SNAPSHOT = Path.home() / ".ytk" / "interest" / "latest.json"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from e4_medium_signal import kendall_tau, ranks_desc, spearman_rho, theme_shares

ALPHAS = [0.0, 1.0, 3.0, 7.0, 15.0, 31.0]
REF = 7.0
N_SHUFFLES = 1000
TOP_N = 5


def _akey(a: float) -> str:
    return str(int(a))


def gather() -> dict:
    from ytk import signals
    from ytk.config import load_config
    from ytk.store import get_all_videos, get_content_memories

    snap = json.loads(SNAPSHOT.read_text())
    themes = snap["themes"]
    k = len(themes)
    assert float(snap["alpha"]) == REF, "snapshot alpha must be the reference"
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
    src_arr = np.asarray(sources)

    r_raw = np.asarray(levels, dtype=float)
    r_adj = np.asarray(adj, dtype=float)
    base = np.asarray([signals.recency_factor(ts, now, half_life) for ts in captured]) * np.asarray(
        signals.day_batch_factors(captured)
    )
    arms = {"raw": r_raw, "adjusted": r_adj}

    shares = {
        arm: {_akey(a): theme_shares((1.0 + a * rv) * base, theme_of, k) for a in ALPHAS}
        for arm, rv in arms.items()
    }
    rank = {arm: {a: ranks_desc(s) for a, s in per.items()} for arm, per in shares.items()}
    top = {
        arm: {a: set(np.argsort(-s)[:TOP_N].tolist()) for a, s in per.items()}
        for arm, per in shares.items()
    }

    # Gate: raw alpha=7 must land on the snapshot's stored weights.
    stored = np.asarray([t["weight"] for t in themes])
    max_diff = float(np.max(np.abs(np.round(shares["raw"][_akey(REF)], 4) - stored)))
    validation = {
        "max_abs_share_diff_vs_snapshot": max_diff,
        "stored_signal_counts": {int(kk): v for kk, v in snap["signal_counts"].items()},
        "recomputed_signal_counts": dict(Counter(levels)),
        "adjusted_signal_counts": dict(Counter(adj)),
        "missing_note_ids": missing,
        "n_notes": len(notes),
    }

    ref = _akey(REF)
    observed = {}
    for arm, per in shares.items():
        ref_top = top[arm][ref]
        ref_rank = rank[arm][ref]
        ref_top_idx = np.argsort(-per[ref])[:TOP_N]
        obs = {}
        for a in per:
            obs[a] = {
                "tau_vs_ref": kendall_tau(per[ref], per[a]),
                "spearman_vs_ref": spearman_rho(per[ref], per[a]),
                "dshare_max_vs_ref": float(np.max(np.abs(per[a] - per[ref]))),
                "top5_churn_vs_ref": TOP_N - len(ref_top & top[arm][a]),
                "head_max_rank_move": int(
                    np.max(np.abs(rank[arm][a][ref_top_idx] - ref_rank[ref_top_idx]))
                ),
            }
        observed[arm] = {
            "per_alpha": obs,
            "tau_extremes": kendall_tau(per[_akey(ALPHAS[0])], per[_akey(ALPHAS[-1])]),
        }
    cross_arm_tau = {a: kendall_tau(shares["raw"][a], shares["adjusted"][a]) for a in shares["raw"]}

    # Medium composition: fraction of the top-5 themes' weight paid by YouTube.
    yt_top5_frac = {}
    for arm, rv in arms.items():
        yt_top5_frac[arm] = {}
        for a in ALPHAS:
            w = (1.0 + a * rv) * base
            top_idx = np.argsort(-shares[arm][_akey(a)])[:TOP_N]
            m = np.isin(theme_of, top_idx)
            yt_top5_frac[arm][_akey(a)] = float(w[m & (src_arr == "youtube")].sum() / w[m].sum())

    # Null: shuffle r within each source (medium tie kept), one label vector
    # per shuffle across the whole sweep, so movement is placement-random but
    # per-source marginals — and therefore the medium's lever — are preserved.
    rng = np.random.default_rng(0)
    nulls = {}
    for arm, rv in arms.items():
        acc = {a: {"tau": [], "dmax": [], "churn": []} for a in shares[arm]}
        ext = []
        for _ in range(N_SHUFFLES):
            r_s = rv.copy()
            for s in set(sources):
                m = src_arr == s
                r_s[m] = rng.permutation(r_s[m])
            s_per = {a: theme_shares((1.0 + float(a) * r_s) * base, theme_of, k) for a in ALPHAS}
            s_ref = s_per[REF]
            s_ref_top = set(np.argsort(-s_ref)[:TOP_N].tolist())
            for a, s_s in s_per.items():
                ak = _akey(a)
                acc[ak]["tau"].append(kendall_tau(s_ref, s_s))
                acc[ak]["dmax"].append(float(np.max(np.abs(s_s - s_ref))))
                acc[ak]["churn"].append(
                    TOP_N - len(s_ref_top & set(np.argsort(-s_s)[:TOP_N].tolist()))
                )
            ext.append(kendall_tau(s_per[ALPHAS[0]], s_per[ALPHAS[-1]]))
        per_alpha = {}
        for a, d in acc.items():
            tau_d = np.asarray(d["tau"])
            dmax_d = np.asarray(d["dmax"])
            churn_d = np.asarray(d["churn"])
            o = observed[arm]["per_alpha"][a]
            per_alpha[a] = {
                "tau_mean": float(tau_d.mean()),
                "tau_p05": float(np.percentile(tau_d, 5)),
                "tau_p50": float(np.percentile(tau_d, 50)),
                "tau_p95": float(np.percentile(tau_d, 95)),
                "dshare_max_p95": float(np.percentile(dmax_d, 95)),
                "top5_churn_p95": float(np.percentile(churn_d, 95)),
                # empirical p: chance moves the ranking at least as far as alpha does
                "p_tau_le_obs": float(np.mean(tau_d <= o["tau_vs_ref"])),
                "p_dshare_ge_obs": float(np.mean(dmax_d >= o["dshare_max_vs_ref"])),
                "p_churn_ge_obs": float(np.mean(churn_d >= o["top5_churn_vs_ref"])),
            }
        ext_d = np.asarray(ext)
        nulls[arm] = {
            "per_alpha": per_alpha,
            "tau_extremes_mean": float(ext_d.mean()),
            "tau_extremes_p05": float(np.percentile(ext_d, 5)),
            "p_tau_extremes_le_obs": float(np.mean(ext_d <= observed[arm]["tau_extremes"])),
        }

    theme_rows = []
    for t_idx, t in enumerate(themes):
        m = theme_of == t_idx
        theme_rows.append(
            {
                "id": t["id"],
                "label": t["label"],
                "n_notes": int(m.sum()),
                "share": {
                    arm: {a: float(per[a][t_idx]) for a in per} for arm, per in shares.items()
                },
                "rank": {arm: {a: int(rk[a][t_idx]) for a in rk} for arm, rk in rank.items()},
                "yt_weight_frac_ref": {
                    arm: float(
                        ((1.0 + REF * rv) * base)[m & (src_arr == "youtube")].sum()
                        / ((1.0 + REF * rv) * base)[m].sum()
                    )
                    for arm, rv in arms.items()
                },
            }
        )

    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True
    ).stdout.strip()
    return {
        "meta": {
            "snapshot_generated_at": snap["generated_at"],
            "alphas": ALPHAS,
            "ref_alpha": REF,
            "half_life_days": half_life,
            "k": k,
            "n_shuffles": N_SHUFFLES,
            "commit": sha,
        },
        "validation": validation,
        "observed": observed,
        "cross_arm_tau": cross_arm_tau,
        "yt_top5_frac": yt_top5_frac,
        "top5": {
            arm: {a: [themes[i]["id"] for i in sorted(idx)] for a, idx in per.items()}
            for arm, per in top.items()
        },
        "nulls": nulls,
        "themes": theme_rows,
    }


# --- figures ----------------------------------------------------------------
ALPHA_LABELS = ["0", "1", "3", "7\n(shipped)", "15", "31"]


def _save(fig, name: str) -> None:
    from plot_assets import BG, DPI, frame_panels

    frame_panels(fig)
    out = OUTDIR / name
    fig.savefig(out, dpi=DPI, facecolor=BG)
    print(f"wrote {out.relative_to(REPO)}  ({out.stat().st_size // 1024}KB)")
    import matplotlib.pyplot as plt

    plt.close(fig)


def fig01(out: dict) -> None:
    from plot_assets import (
        BLUE,
        DIM,
        GOLD,
        MARGIN,
        MUTED,
        TEXT,
        figure,
        panel_title,
        style_axes,
        verdict,
    )

    akeys = [_akey(a) for a in ALPHAS]
    x = np.arange(len(ALPHAS))
    obs_adj = out["observed"]["adjusted"]
    null_adj = out["nulls"]["adjusted"]
    fig, top = figure(
        15,
        7.8,
        1,
        "alpha's remaining lever",
        "Rank agreement with the shipped alpha=7, before and after the medium correction",
        f"{out['validation']['n_notes']} notes, {out['meta']['k']} themes, frozen snapshot "
        f"{out['meta']['snapshot_generated_at'][:10]}  ·  {out['meta']['n_shuffles']} "
        f"within-source shuffles per arm  ·  corrected tau(0,31) "
        f"{obs_adj['tau_extremes']:.3f} vs null p5 {null_adj['tau_extremes_p05']:.3f} "
        f"(p {null_adj['p_tau_extremes_le_obs']:.3f})  ·  {out['meta']['commit']}",
    )
    gs = fig.add_gridspec(
        1, 2, left=0.075, right=1 - MARGIN - 0.01, top=top, bottom=0.15, wspace=0.18
    )
    panels = [("raw", "raw r (medium_controlled: false)", BLUE), ("adjusted", "corrected r", GOLD)]
    for i, (arm, name, color) in enumerate(panels):
        ax = fig.add_subplot(gs[i])
        per = out["nulls"][arm]["per_alpha"]
        lo = [per[a]["tau_p05"] for a in akeys]
        hi = [per[a]["tau_p95"] for a in akeys]
        ax.fill_between(x, lo, hi, color=DIM, zorder=1, label="shuffle null p5-p95")
        tau = [out["observed"][arm]["per_alpha"][a]["tau_vs_ref"] for a in akeys]
        ax.plot(x, tau, color=color, linewidth=2.2, zorder=3)
        ax.scatter(x, tau, color=color, s=26, zorder=4)
        for j, a in enumerate(akeys):
            p = per[a]["p_tau_le_obs"]
            if p < 0.05 and a != _akey(REF):
                ax.text(
                    x[j],
                    tau[j] - 0.035,
                    f"p {p:.3f}".lstrip("0"),
                    color=TEXT,
                    fontsize=7.5,
                    ha="center",
                    va="top",
                )
        ax.set_xticks(x, ALPHA_LABELS)
        ax.set_ylim(0.38, 1.03)
        style_axes(ax)
        ax.set_xlabel("alpha")
        if i == 0:
            ax.set_ylabel("Kendall tau vs the alpha=7 ranking")
        else:
            ax.set_yticklabels([])
        panel_title(
            ax,
            f"{name} — observed sweep vs its within-source shuffle band (dim)",
            width=58,
        )
        ax.text(
            0.03,
            0.045,
            "band: how far 1000 random within-medium placements\nof the same signal values move the ranking",
            color=MUTED,
            fontsize=7.5,
            transform=ax.transAxes,
        )
    verdict(
        fig,
        "the knob outlived its confound: at alpha<=1 the corrected ranking moves past 99.5% of shuffles",
    )
    _save(fig, "01-tau-vs-alpha-two-arms.png")


def fig02(out: dict) -> None:
    from e4_medium_signal import _short
    from plot_assets import (
        BLUE,
        CYAN,
        FRAME,
        GOLD,
        MARGIN,
        MUTED,
        RED,
        TEXT,
        figure,
        panel_title,
        style_axes,
        verdict,
    )

    akeys = [_akey(a) for a in ALPHAS]
    x = np.arange(len(ALPHAS))
    themes = out["themes"]
    k = len(themes)
    ref = _akey(REF)
    invariant = [
        t["label"] for t in themes if all(t["rank"]["adjusted"][a] <= TOP_N for a in akeys)
    ]
    fig, top = figure(
        15,
        9.8,
        2,
        "what alpha buys after the correction",
        "Theme rank across the corrected sweep, and which medium pays the top-5",
        f"corrected arm: top-5 slots surviving the whole sweep: {len(invariant)} of {TOP_N} "
        f"({', '.join(invariant)})  ·  YouTube's share of top-5 weight, raw arm: "
        f"{out['yt_top5_frac']['raw']['0']:.2f} -> {out['yt_top5_frac']['raw']['31']:.2f}  ·  "
        f"corrected arm: {min(out['yt_top5_frac']['adjusted'].values()):.2f}-"
        f"{max(out['yt_top5_frac']['adjusted'].values()):.2f} flat  ·  {out['meta']['commit']}",
    )
    gs = fig.add_gridspec(
        1,
        2,
        width_ratios=[1.3, 1.0],
        left=0.21,
        right=1 - MARGIN - 0.015,
        top=top,
        bottom=0.10,
        wspace=0.26,
    )

    ax = fig.add_subplot(gs[0])
    ax.set_facecolor("#000000")
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xlim(-0.06, len(ALPHAS) - 1 + 0.30)
    ax.set_ylim(k + 0.6, 0.4)
    ax.set_xticks(x, ALPHA_LABELS, color=TEXT, fontsize=9)
    ax.set_yticks([])
    ax.tick_params(length=0)
    ax.axvline(3, color=FRAME, linewidth=1.0, zorder=1)
    ax.axhline(TOP_N + 0.5, color=RED, linewidth=0.9, linestyle="--", alpha=0.8, zorder=2)
    for t in themes:
        rr = [t["rank"]["adjusted"][a] for a in akeys]
        in_ref_top = t["rank"]["adjusted"][ref] <= TOP_N
        ever_top = any(r <= TOP_N for r in rr)
        color = GOLD if in_ref_top else (CYAN if ever_top else MUTED)
        lw = 2.2 if in_ref_top else (1.8 if ever_top else 1.0)
        ax.plot(x, rr, color=color, linewidth=lw, alpha=0.9, zorder=3)
        ax.scatter(x, rr, color=color, s=16, zorder=4)
        ax.text(
            -0.10,
            rr[0],
            f"{_short(t['label'])}  {rr[0]:>2}",
            color=TEXT if ever_top else MUTED,
            fontsize=8.2,
            ha="right",
            va="center",
            clip_on=False,
        )
        ax.text(
            len(ALPHAS) - 1 + 0.10,
            rr[-1],
            f"{rr[-1]:>2}",
            color=MUTED,
            fontsize=8.2,
            ha="left",
            va="center",
        )
    panel_title(
        ax,
        "corrected arm: rank per alpha; gold = top-5 at the shipped alpha, cyan = enters the "
        "top-5 elsewhere in the sweep; red dashes = the top-5 the profile page shows",
        width=86,
    )

    ax = fig.add_subplot(gs[1])
    base_frac = out["yt_top5_frac"]["raw"]["0"]
    ax.axhline(base_frac, color=MUTED, linewidth=0.9, linestyle=":", alpha=0.8)
    ax.text(
        4.95,
        base_frac - 0.018,
        "unweighted corpus",
        color=MUTED,
        fontsize=7.5,
        ha="right",
        va="top",
    )
    for arm, color, name in [("raw", BLUE, "raw r"), ("adjusted", GOLD, "corrected r")]:
        vals = [out["yt_top5_frac"][arm][a] for a in akeys]
        ax.plot(x, vals, color=color, linewidth=2.2, zorder=3)
        ax.scatter(x, vals, color=color, s=26, zorder=4)
    ax.text(2.15, 0.30, "raw r", color=BLUE, fontsize=8.5, ha="left", va="bottom")
    ax.text(2.0, 0.82, "corrected r", color=GOLD, fontsize=8.5, ha="center", va="bottom")
    ax.set_xticks(x, ALPHA_LABELS)
    ax.set_ylim(0, 0.88)
    style_axes(ax)
    ax.set_xlabel("alpha")
    ax.set_ylabel("YouTube's fraction of top-5 theme weight")
    panel_title(
        ax,
        "who pays the head of the portrait: raw alpha hands the top-5 to the "
        "saved media; corrected alpha does not",
        width=64,
    )
    verdict(fig, "alpha picks 4 of the 5 top themes — but after the correction, not by medium")
    _save(fig, "02-head-composition-across-alpha.png")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--figs-only", action="store_true")
    args = ap.parse_args()

    OUTDIR.mkdir(parents=True, exist_ok=True)
    path = OUTDIR / "e5-alpha-sensitivity.json"
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
        f"{v['recomputed_signal_counts']}, adjusted {v['adjusted_signal_counts']}, "
        f"missing {len(v['missing_note_ids'])}"
    )
    for arm in ("raw", "adjusted"):
        o = out["observed"][arm]
        print(
            f"{arm}: tau_vs_ref "
            + " ".join(f"{a}:{d['tau_vs_ref']:.3f}" for a, d in o["per_alpha"].items())
            + f"  extremes(0,31) {o['tau_extremes']:.3f}"
        )
        n = out["nulls"][arm]
        print(
            f"{arm} null: tau_p05 "
            + " ".join(f"{a}:{d['tau_p05']:.3f}" for a, d in n["per_alpha"].items())
            + f"  p_ext_le_obs {n['p_tau_extremes_le_obs']:.3f}"
        )
    print("cross-arm tau:", {a: round(t, 3) for a, t in out["cross_arm_tau"].items()})
    print("yt top5 frac:", json.dumps(out["yt_top5_frac"], indent=1))

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
