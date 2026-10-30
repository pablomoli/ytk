"""Section 53, figure 06: Jev against graded relevance, with a shuffle null.

Blind readers graded every served candidate 0-3 from its full stored text
(`judged-relevance.json`, judged_by recorded). Each ranking arm is scored by
nDCG@20 against those grades and by the grade of the note it puts first.

    uv run python scripts/jev_judge_score.py merge <judge-*.json ...>
    uv run --with matplotlib python scripts/jev_judge_score.py draw
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/ on path
from jev_rung0 import OUTDIR, ROOT, SIDECAR, SIDECAR2, commit_sha, order_rows

JUDGED = OUTDIR / "judged-relevance.json"
N_NULL = 1000
SEED = 53


def merge(paths: list[str]) -> None:
    out = []
    for p in paths:
        for row in json.loads(Path(p).read_text()):
            grades = {int(k): int(v) for k, v in row["grades"].items()}
            assert len(grades) == 20, (p, row["case"])
            out.append(
                {
                    "case": row["case"],
                    "grades": [grades[i] for i in range(1, 21)],
                    "best": [int(b) for b in row.get("best", [])],
                    "none": bool(row.get("none", False)),
                    "reason": row.get("reason", ""),
                    "judge": Path(p).stem,
                }
            )
    out.sort(key=lambda r: r["case"])
    JUDGED.write_text(
        json.dumps(
            {
                "generated": datetime.now(UTC).isoformat(timespec="seconds"),
                "commit": commit_sha(),
                "judged_by": "three blind Claude readers (session model), full stored text, no marks",
                "scale": {
                    "3": "holds it",
                    "2": "part of it or buried",
                    "1": "adjacent topic",
                    "0": "unrelated",
                },
                "rows": out,
            },
            indent=1,
        )
    )
    print(f"wrote {JUDGED.relative_to(ROOT)}: {len(out)} cases")


def ndcg(order_idx: np.ndarray, grades: np.ndarray, k: int = 20) -> float:
    gains = (2.0 ** grades[order_idx[:k]] - 1) / np.log2(np.arange(2, k + 2))
    ideal = (2.0 ** np.sort(grades)[::-1][:k] - 1) / np.log2(np.arange(2, k + 2))
    return float(gains.sum() / ideal.sum()) if ideal.sum() > 0 else np.nan


def arms(r0: dict, r2: dict, grades: np.ndarray) -> dict[str, np.ndarray]:
    """Each arm as an ordering of the 20 served candidates (indices)."""
    served = np.arange(20)
    n0 = np.argsort(-np.array(r0["noul"]), kind="stable")
    n2 = np.argsort(-np.array(r2["noul"]), kind="stable")
    c0 = np.argsort(
        -np.array([r0["choice"].get(f"c{j:02d}", 0.0) for j in range(1, 21)]), kind="stable"
    )
    c2 = np.argsort(
        -np.array([r2["choice"].get(f"c{j:02d}", 0.0) for j in range(1, 21)]), kind="stable"
    )
    return {
        "served": served,
        "noul snippet": n0,
        "noul text": n2,
        "choice snippet": c0,
        "choice text": c2,
    }


def draw() -> None:
    import matplotlib

    matplotlib.use("Agg")
    from plot_assets import (
        BG,
        BLUE,
        DIM,
        DPI,
        GOLD,
        MARGIN,
        RED,
        TEXT,
        figure,
        frame_panels,
        panel_title,
        style_axes,
        verdict,
    )

    base = json.loads(SIDECAR.read_text())
    text = json.loads(SIDECAR2.read_text())
    judged = json.loads(JUDGED.read_text())
    g_by = {r["case"]: np.array(r["grades"]) for r in judged["rows"]}
    order, _ = order_rows([r for r in base["rows"] if r["case"] in g_by])
    t_by = {r["case"]: r for r in text["rows"]}

    names = ["served", "noul snippet", "noul text", "choice snippet", "choice text"]
    scores = {n: [] for n in names}
    top_grade = {n: [] for n in names}
    click_grade = []
    rng = np.random.default_rng(SEED)
    null = []
    for r in order:
        g = g_by[r["case"]]
        a = arms(r, t_by[r["case"]], g)
        for n in names:
            scores[n].append(ndcg(a[n], g))
            top_grade[n].append(int(g[a[n][0]]))
        click_grade.append(int(g[r["opened_rank_today"] - 1]))
        null.append([ndcg(rng.permutation(20), g) for _ in range(N_NULL)])
    null = np.array(null)  # rows x N_NULL
    null_mean = np.nanmean(null, axis=0)  # distribution of the mean nDCG under random order
    means = {n: float(np.nanmean(scores[n])) for n in names}
    paired = {}
    for n in names[1:]:
        d = np.array(scores[n]) - np.array(scores["served"])
        boots = [rng.choice(d, len(d), replace=True).mean() for _ in range(N_NULL)]
        paired[n] = {
            "wins": int((d > 1e-9).sum()),
            "ties": int((np.abs(d) <= 1e-9).sum()),
            "losses": int((d < -1e-9).sum()),
            "mean": float(d.mean()),
            "lo": float(np.quantile(boots, 0.025)),
            "hi": float(np.quantile(boots, 0.975)),
        }

    n_rows = len(order)
    labels = [r["query"][:40] + ("…" if len(r["query"]) > 40 else "") for r in order]
    fig, top = figure(
        17,
        10.5,
        6,
        "jev, second look",
        "Against graded relevance: what each ranking puts first, and how it scores",
        meta=(
            f"{n_rows} searches, 20 candidates each, graded 0-3 by {judged['judged_by']} | left: grade of the note each "
            f"arm ranks first (arrow: the note the agent clicked, coloured by its grade) | right: mean nDCG@20 per arm, grey: {N_NULL} "
            f"random orderings of the same candidates (mean over rows), red: ideal | means "
            + ", ".join(f"{n} {means[n]:.3f}" for n in names)
            + f" | null {null_mean.mean():.3f} +/- {null_mean.std():.3f} | per-row against served, wins/ties/losses and "
            f"bootstrap 95% on the mean gain: "
            + "; ".join(
                f"{n} {paired[n]['wins']}/{paired[n]['ties']}/{paired[n]['losses']} {paired[n]['mean']:+.3f} "
                f"[{paired[n]['lo']:+.3f}, {paired[n]['hi']:+.3f}]"
                for n in names[1:]
            )
            + f" | {base['model']} {judged['commit']}"
        ),
    )
    bottom = 0.09
    h = top - bottom - 0.05
    ax = fig.add_axes([MARGIN + 0.17, bottom, 0.36, h])
    style_axes(ax)
    grade_cmap = {0: DIM, 1: "#5a2a5e", 2: "#c9405a", 3: GOLD}
    for i in range(n_rows):
        for j, n in enumerate(names):
            ax.add_patch(
                matplotlib.patches.Rectangle(
                    (j, i), 1, 1, facecolor=grade_cmap[top_grade[n][i]], edgecolor=BG, linewidth=0.8
                )
            )
        ax.plot(
            len(names) + 0.4,
            i + 0.5,
            marker="<",
            color=grade_cmap[click_grade[i]],
            markersize=7,
            clip_on=False,
        )
    ax.set_xlim(0, len(names))
    ax.set_ylim(n_rows, 0)
    ax.set_xticks(np.arange(len(names)) + 0.5)
    ax.set_xticklabels(names, rotation=30, ha="right")
    ax.set_yticks(np.arange(n_rows) + 0.5)
    ax.set_yticklabels(labels)
    ax.tick_params(length=0)
    panel_title(
        ax,
        "Grade of the first-ranked note per arm (gold 3, red 2, purple 1, grey 0); arrow: the clicked note",
        width=64,
    )

    ax2 = fig.add_axes([MARGIN + 0.60, bottom, 0.33, h])
    style_axes(ax2)
    ax2.hist(null_mean, bins=40, color=DIM, orientation="horizontal", edgecolor="none")
    xmax = ax2.get_xlim()[1]
    for j, n in enumerate(names):
        col = {
            "served": TEXT,
            "noul snippet": GOLD,
            "noul text": GOLD,
            "choice snippet": BLUE,
            "choice text": BLUE,
        }[n]
        ax2.axhline(
            means[n],
            color=col,
            linewidth=1.4,
            linestyle="-" if "text" in n or n == "served" else ":",
        )
        # the two snippet arms sit 0.001 apart: one label above its line, one below
        above = n != "choice snippet"
        ax2.text(
            xmax * 0.98,
            means[n] + (0.004 if above else -0.004),
            f"{n} {means[n]:.3f}",
            color=col,
            fontsize=9,
            ha="right",
            va="bottom" if above else "top",
        )
    ax2.axhline(1.0, color=RED, linewidth=1.0)
    ax2.text(xmax * 0.98, 1.004, "ideal 1.000", color=RED, fontsize=9, ha="right", va="bottom")
    ax2.set_ylim(min(0.3, null_mean.min() - 0.02), 1.03)
    ax2.set_ylabel("mean nDCG@20 over the searches")
    ax2.set_xlabel(f"random orderings ({N_NULL})")
    panel_title(
        ax2,
        "Mean nDCG@20 per arm against the shuffle null (dotted: snippet, solid: stored text)",
        width=60,
    )

    top3 = {n: sum(g == 3 for g in top_grade[n]) for n in names}
    verdict(
        fig,
        f"first-ranked note holds it (grade 3): served {top3['served']}/{n_rows} · noul {top3['noul snippet']}→{top3['noul text']} · "
        f"choice {top3['choice snippet']}→{top3['choice text']} · click {sum(g == 3 for g in click_grade)} · "
        f"nDCG served {means['served']:.2f}, noul text {means['noul text']:.2f} (beats served in "
        f"{paired['noul text']['wins']}/{n_rows} rows), null {null_mean.mean():.2f}".replace(
            "→", "->"
        ),
    )
    frame_panels(fig)
    out = OUTDIR / "06-graded.png"
    fig.savefig(out, dpi=DPI, facecolor=BG)
    print(f"wrote {out.relative_to(ROOT)}  ({out.stat().st_size // 1024}KB)")
    for n in names:
        print(
            f"{n:16} nDCG {means[n]:.3f}  top-1 grade 3: {top3[n]}/{n_rows}  grade>=2: {sum(g >= 2 for g in top_grade[n])}"
        )
    print(
        f"{'click':16} top-1 grade 3: {sum(g == 3 for g in click_grade)}/{n_rows}  grade>=2: {sum(g >= 2 for g in click_grade)}"
    )
    print(
        f"null mean {null_mean.mean():.3f} sd {null_mean.std():.3f}; p95 {np.quantile(null_mean, 0.95):.3f}"
    )
    for n in names[1:]:
        q = paired[n]
        print(
            f"{n:16} vs served: wins {q['wins']} ties {q['ties']} losses {q['losses']}  "
            f"mean {q['mean']:+.3f} [{q['lo']:+.3f}, {q['hi']:+.3f}]"
        )


if __name__ == "__main__":
    if sys.argv[1] == "merge":
        merge(sys.argv[2:])
    else:
        draw()
