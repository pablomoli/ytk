"""E6 — the honest ladder: record playlist intent and re-ask E5's question.

Section 27 measured alpha doing real, unjustified work on the medium-corrected
signal and declared the refit data-blocked. The owner then supplied the missing
fact: the ytk playlist is curated — "I only add to that playlist to surface it
to my notes" — so playlist membership IS the deliberate-save signal YouTube was
assumed not to have. Joined against the vault (2026-08-10): 322 of 358 YouTube
notes are playlist members the ladder scored r=0. E6 adds the honest arm —

    raw       classify() only               (pre-section-28 production)
    adjusted  intake-adjusted raw           (E4's correction, now retired)
    honest    raw + playlist membership     (r = max(r, 1) for cached ids)

— and reruns the E5 sweep: alpha over {0,1,3,7,15,31}, frozen 2026-08-08
snapshot, fixed decay*batch base, within-source shuffle null (1000, seed 0)
for the honest arm. Raw alpha=7 must reproduce the snapshot's stored weights.
The honest arm is what production computes after this section's ladder change;
the script derives raw by stripping the playlist lift so the gate still runs.

    uv run --with matplotlib python scripts/e6_honest_ladder.py
    uv run --with matplotlib python scripts/e6_honest_ladder.py --figs-only

Analysis lands in docs/assets/28-honest-ladder/e6-honest-ladder.json;
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
OUTDIR = REPO / "docs" / "assets" / "28-honest-ladder"
SNAPSHOT = Path.home() / ".ytk" / "interest" / "latest.json"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from e4_medium_signal import _short, kendall_tau, ranks_desc, spearman_rho, theme_shares

ALPHAS = [0.0, 1.0, 3.0, 7.0, 15.0, 31.0]
REF = 7.0
N_SHUFFLES = 1000
TOP_N = 5
ARM_ORDER = ("raw", "adjusted", "honest")


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

    honest = signals.signal_levels(notes)  # production ladder, playlist-aware
    sources = [n["source"] for n in notes]
    # Fail before writing anything: a stalled vault scan yields all-zero levels
    # and a poisoned sidecar (this script's first run, 2026-08-10).
    signals.assert_signal_coverage(honest, sources)
    src_arr = np.asarray(sources)
    pids = signals.playlist_ids()
    assert pids, "playlist cache missing — run ytk sync first"
    # Strip the playlist lift: classify() alone never yields r=1 for youtube,
    # so any youtube r=1 is the cache's doing.
    raw = [0 if (s == "youtube" and r == 1) else r for r, s in zip(honest, sources)]
    adjusted = signals.intake_adjusted_levels(raw, sources)
    captured = [n.get("captured_at", "") for n in notes]
    base = np.asarray([signals.recency_factor(ts, now, half_life) for ts in captured]) * np.asarray(
        signals.day_batch_factors(captured)
    )
    arms = {
        "raw": np.asarray(raw, dtype=float),
        "adjusted": np.asarray(adjusted, dtype=float),
        "honest": np.asarray(honest, dtype=float),
    }

    shares = {
        arm: {_akey(a): theme_shares((1.0 + a * rv) * base, theme_of, k) for a in ALPHAS}
        for arm, rv in arms.items()
    }
    rank = {arm: {a: ranks_desc(s) for a, s in per.items()} for arm, per in shares.items()}
    top = {
        arm: {a: set(np.argsort(-s)[:TOP_N].tolist()) for a, s in per.items()}
        for arm, per in shares.items()
    }

    stored = np.asarray([t["weight"] for t in themes])
    max_diff = float(np.max(np.abs(np.round(shares["raw"][_akey(REF)], 4) - stored)))
    assert max_diff == 0.0, f"raw alpha=7 does not reproduce the snapshot (diff {max_diff})"
    validation = {
        "max_abs_share_diff_vs_snapshot": max_diff,
        "stored_signal_counts": {int(kk): v for kk, v in snap["signal_counts"].items()},
        "raw_signal_counts": dict(Counter(raw)),
        "honest_signal_counts": dict(Counter(honest)),
        "playlist_cache_size": len(pids),
        "playlist_members_in_snapshot": int(
            sum(1 for n, s in zip(notes, sources) if s == "youtube" and n["id"] in pids)
        ),
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
    cross_arm_tau_at_ref = {
        f"honest-{other}": kendall_tau(shares["honest"][ref], shares[other][ref])
        for other in ("raw", "adjusted")
    }

    yt_top5_frac = {}
    for arm, rv in arms.items():
        yt_top5_frac[arm] = {}
        for a in ALPHAS:
            w = (1.0 + a * rv) * base
            top_idx = np.argsort(-shares[arm][_akey(a)])[:TOP_N]
            m = np.isin(theme_of, top_idx)
            yt_top5_frac[arm][_akey(a)] = float(w[m & (src_arr == "youtube")].sum() / w[m].sum())

    # Null for the honest arm only: raw and adjusted are calibrated in section
    # 27 under the identical harness; recomputing them here would only restate
    # that record. One shuffled vector per draw across the whole sweep.
    rng = np.random.default_rng(0)
    rv = arms["honest"]
    acc = {_akey(a): {"tau": [], "dmax": [], "churn": []} for a in ALPHAS}
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
            acc[ak]["churn"].append(TOP_N - len(s_ref_top & set(np.argsort(-s_s)[:TOP_N].tolist())))
        ext.append(kendall_tau(s_per[ALPHAS[0]], s_per[ALPHAS[-1]]))
    per_alpha = {}
    for a, d in acc.items():
        tau_d = np.asarray(d["tau"])
        dmax_d = np.asarray(d["dmax"])
        churn_d = np.asarray(d["churn"])
        o = observed["honest"]["per_alpha"][a]
        per_alpha[a] = {
            "tau_mean": float(tau_d.mean()),
            "tau_p05": float(np.percentile(tau_d, 5)),
            "tau_p95": float(np.percentile(tau_d, 95)),
            "dshare_max_p95": float(np.percentile(dmax_d, 95)),
            "top5_churn_p95": float(np.percentile(churn_d, 95)),
            "p_tau_le_obs": float(np.mean(tau_d <= o["tau_vs_ref"])),
            "p_dshare_ge_obs": float(np.mean(dmax_d >= o["dshare_max_vs_ref"])),
            "p_churn_ge_obs": float(np.mean(churn_d >= o["top5_churn_vs_ref"])),
        }
    ext_d = np.asarray(ext)
    nulls = {
        "honest": {
            "per_alpha": per_alpha,
            "tau_extremes_mean": float(ext_d.mean()),
            "tau_extremes_p05": float(np.percentile(ext_d, 5)),
            "p_tau_extremes_le_obs": float(np.mean(ext_d <= observed["honest"]["tau_extremes"])),
        }
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
        "cross_arm_tau_at_ref": cross_arm_tau_at_ref,
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
        CYAN,
        DIM,
        GOLD,
        MARGIN,
        MUTED,
        figure,
        panel_title,
        style_axes,
        verdict,
    )

    akeys = [_akey(a) for a in ALPHAS]
    x = np.arange(len(ALPHAS))
    obs_h = out["observed"]["honest"]
    null_h = out["nulls"]["honest"]
    fig, top = figure(
        13,
        8.2,
        1,
        "the knob after honesty",
        "Rank agreement with the shipped alpha=7, once playlist intent is recorded",
        f"{out['validation']['n_notes']} notes, {out['meta']['k']} themes, frozen snapshot "
        f"{out['meta']['snapshot_generated_at'][:10]}  ·  honest r counts "
        f"{{0: {out['validation']['honest_signal_counts'].get(0, 0)}, "
        f"1: {out['validation']['honest_signal_counts'].get(1, 0)}, "
        f"2: {out['validation']['honest_signal_counts'].get(2, 0)}}}  ·  "
        f"tau(0,31): honest {obs_h['tau_extremes']:.3f} vs corrected "
        f"{out['observed']['adjusted']['tau_extremes']:.3f}, raw "
        f"{out['observed']['raw']['tau_extremes']:.3f}  ·  {out['meta']['n_shuffles']} "
        f"within-source shuffles  ·  {out['meta']['commit']}",
    )
    ax = fig.add_subplot(1, 1, 1)
    lo = [null_h["per_alpha"][a]["tau_p05"] for a in akeys]
    hi = [null_h["per_alpha"][a]["tau_p95"] for a in akeys]
    ax.fill_between(x, lo, hi, color=DIM, zorder=1)
    ax.text(
        0.03,
        0.05,
        "band: the honest arm's within-source shuffle null p5-p95\n"
        "(raw and corrected arms calibrated in section 27)",
        color=MUTED,
        fontsize=7.5,
        transform=ax.transAxes,
    )
    series = [
        ("honest", GOLD, "honest r (this section)"),
        ("adjusted", CYAN, "corrected r (E4, retired)"),
        ("raw", BLUE, "raw r (pre-E4)"),
    ]
    for arm, color, name in series:
        tau = [out["observed"][arm]["per_alpha"][a]["tau_vs_ref"] for a in akeys]
        ax.plot(x, tau, color=color, linewidth=2.2, zorder=3)
        ax.scatter(x, tau, color=color, s=26, zorder=4)
        end_y = tau[0]
        ax.text(-0.12, end_y, name, color=color, fontsize=8.5, ha="right", va="center")
    ax.set_xticks(x, ALPHA_LABELS)
    ax.set_xlim(-1.55, len(ALPHAS) - 1 + 0.25)
    ax.set_ylim(0.38, 1.03)
    style_axes(ax)
    ax.set_xlabel("alpha")
    ax.set_ylabel("Kendall tau vs the alpha=7 ranking")
    panel_title(
        ax,
        "one line per signal arm: tau(ranking at alpha, ranking at 7); flat at 1.0 = the knob "
        "does not matter",
        width=92,
    )
    verdict(
        fig, "record the intent and the knob stops mattering: tau(0,31) 0.897 vs 0.235 corrected"
    )
    fig.subplots_adjust(left=0.20, right=1 - MARGIN - 0.02, top=top - 0.02, bottom=0.11)
    _save(fig, "01-knob-after-honesty.png")


def fig02(out: dict) -> None:
    from plot_assets import (
        GOLD,
        MARGIN,
        MUTED,
        RED,
        TEXT,
        figure,
        panel_title,
        verdict,
    )

    themes = out["themes"]
    k = len(themes)
    ref = _akey(REF)
    cols = ["raw", "adjusted", "honest"]
    col_names = [
        "raw r, alpha=7\n(pre-E4 production)",
        "corrected r, alpha=7\n(shipped by E4)",
        "honest r, alpha=7\n(this section)",
    ]
    fig, top = figure(
        14,
        10.6,
        2,
        "the portrait, three ladders",
        "Theme rank under the confounded, corrected, and honest signal at the shipped alpha",
        f"YouTube pays {out['yt_top5_frac']['raw'][ref]:.2f} / "
        f"{out['yt_top5_frac']['adjusted'][ref]:.2f} / "
        f"{out['yt_top5_frac']['honest'][ref]:.2f} of the top-5 weight across the three ladders"
        f"  ·  playlist members lifted: {out['validation']['playlist_members_in_snapshot']}"
        f"  ·  {out['meta']['commit']}",
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
    ax.axhline(TOP_N + 0.5, color=RED, linewidth=0.9, linestyle="--", alpha=0.8, zorder=2)
    for t in themes:
        rr = [t["rank"][c][ref] for c in cols]
        moved = abs(rr[1] - rr[2])  # corrected -> honest: what this change does
        color = RED if moved >= 3 else (GOLD if moved >= 1 else MUTED)
        lw = 2.2 if moved >= 3 else (1.6 if moved >= 1 else 1.0)
        ax.plot(range(len(cols)), rr, color=color, linewidth=lw, alpha=0.9, zorder=3)
        ax.scatter(range(len(cols)), rr, color=color, s=18, zorder=4)
        ax.text(
            -0.055,
            rr[0],
            f"{_short(t['label'])}  {rr[0]:>2}",
            color=TEXT if moved >= 3 else MUTED,
            fontsize=8.2,
            ha="right",
            va="center",
            clip_on=False,
        )
        ax.text(
            len(cols) - 1 + 0.06,
            rr[-1],
            f"{rr[-1]:>2}",
            color=MUTED,
            fontsize=8.2,
            ha="left",
            va="center",
        )
    panel_title(
        ax,
        "one line per theme, position = rank (1 = heaviest); red = moves 3+ ranks from the "
        "corrected to the honest ladder; red dashes = the top-5 boundary",
        width=96,
    )
    verdict(
        fig, "the honest top-5 is the corrected arm's low-alpha five, with curated volume restored"
    )
    fig.subplots_adjust(left=0.26, right=1 - MARGIN - 0.02, top=top - 0.02, bottom=0.06)
    _save(fig, "02-portrait-three-ladders.png")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--figs-only", action="store_true")
    args = ap.parse_args()

    OUTDIR.mkdir(parents=True, exist_ok=True)
    path = OUTDIR / "e6-honest-ladder.json"
    if args.figs_only:
        out = json.loads(path.read_text())
    else:
        out = gather()
        path.write_text(json.dumps(out, indent=1))
        print(f"wrote {path.relative_to(REPO)}")

    v = out["validation"]
    print(
        f"validation: max|share diff| {v['max_abs_share_diff_vs_snapshot']:.5f}, "
        f"raw counts {v['raw_signal_counts']} vs stored {v['stored_signal_counts']}, "
        f"honest {v['honest_signal_counts']}, playlist members {v['playlist_members_in_snapshot']}, "
        f"missing {len(v['missing_note_ids'])}"
    )
    for arm in ARM_ORDER:
        o = out["observed"][arm]
        print(
            f"{arm}: tau_vs_ref "
            + " ".join(f"{a}:{d['tau_vs_ref']:.3f}" for a, d in o["per_alpha"].items())
            + f"  extremes(0,31) {o['tau_extremes']:.3f}"
        )
    n = out["nulls"]["honest"]
    print(
        "honest null: tau_p05 "
        + " ".join(f"{a}:{d['tau_p05']:.3f}" for a, d in n["per_alpha"].items())
        + f"  p_ext_le_obs {n['p_tau_extremes_le_obs']:.3f}"
    )
    print("cross-arm at 7:", {kk: round(vv, 3) for kk, vv in out["cross_arm_tau_at_ref"].items()})

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
