"""E29 — the continent frontier (issue #175).

Radial and lattice are two poles: continents with heavy occlusion versus full
visibility with no geography. Each stage renders a checkpoint figure; the
assets stage re-renders the keepers into docs/assets/29-planet-continents/.

    uv run --with matplotlib,scikit-learn,scipy python scripts/e29_continent_frontier.py data
    ... transforms
    ... frontier
    ... assets

Positions and metrics cache in ~/.ytk/e29-cache.npz / e29-metrics.json;
stages reuse the cache so a re-render never recomputes the sweeps.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_assets import (
    BG,
    BLUE,
    CYAN,
    DIM,
    DPI,
    GOLD,
    MUTED,
    PANEL,
    PURPLE,
    RED,
    figure,
    fit3d,
    frame_panels,
    panel_title,
    style_axes,
    verdict,
)

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from ytk.spheremap import fibonacci

MAP = Path(os.path.expanduser("~/.ytk/map.json"))
CACHE = Path(os.path.expanduser("~/.ytk/e29-cache.npz"))
METRICS = Path(os.path.expanduser("~/.ytk/e29-metrics.json"))
ASSETS = REPO / "docs" / "assets" / "29-planet-continents"

# Render truth, not the equal-area formula: tiles draw as squares of
# half-extent 0.055 at radius 1 (web/src/lib/orb/scene.ts:20). Nearer than
# one half-width, the neighbour hides more than half the tile.
TILE_HALF = 0.055
OCCL = float(np.arctan(TILE_HALF))
OCCL_DEG = float(np.degrees(OCCL))

SEED = 29
B_ITERS = [10, 40, 160, 640]
C_KS = [2, 4, 8, 16]
N_SHUFFLES = 500
N_PROBES = 8192


def sha() -> str:
    r = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True
    )
    return r.stdout.strip() or "unknown"


# --- data ------------------------------------------------------------------


def load_block() -> dict:
    data = json.loads(MAP.read_text())
    sp = data["content"]["sphere"]
    out = {
        "radial": np.asarray(sp["radial"], dtype=float),
        "haversine": np.asarray(sp["haversine"], dtype=float) if sp["haversine"] else None,
        "lattice": np.asarray(sp["lattice"], dtype=float),
        "scores": sp["scores"],
    }
    cpts = [p for p in data["points"] if "c3" in p]
    if len(cpts) != len(out["radial"]):
        raise SystemExit(
            f"sphere block has {len(out['radial'])} rows but map has {len(cpts)} "
            "content points — rerun build_map --attach-sphere first"
        )
    out["themes"] = np.asarray([p.get("th", -1) for p in cpts])
    # stored positions are rounded to 4 decimals; renormalize before geodesics
    for k in ("radial", "haversine", "lattice"):
        if out[k] is not None:
            out[k] = out[k] / np.linalg.norm(out[k], axis=1, keepdims=True)
    return out


def load_vecs() -> tuple[np.ndarray, np.ndarray] | None:
    """Store vectors for trustworthiness. Index alignment first; when the store
    has drifted from map.json, fall back to url-matching the content points —
    good enough for a measurement, never for shipping positions. None only if
    the match rate drops below 95%."""
    import build_map

    points = json.loads(MAP.read_text())["points"]
    vecs, meta, _docs = build_map.load_points()
    try:
        cidx = build_map._content_alignment(points, meta, build_map.CONTENT_CATS)
        full = np.asarray(vecs)[cidx]
        return full, np.ones(len(full), dtype=bool)
    except SystemExit as exc:
        print(f"index alignment failed ({exc}); url-matching instead")
    by_url = {m["url"]: v for m, v in zip(meta, vecs) if m.get("url")}
    cpts = [p for p in points if "c3" in p]
    rows = [by_url.get(p.get("u")) for p in cpts]
    mask = np.array([r is not None for r in rows])
    print(f"url-matched {int(mask.sum())}/{len(cpts)} content points to store vectors")
    if mask.mean() < 0.95:
        print("trustworthiness axis skipped: match rate under 95%")
        return None
    # rank metric: imputing unmatched rows would pollute neighbourhoods,
    # so trustworthiness is measured on the matched subset only
    return np.asarray([r for r in rows if r is not None]), mask


# --- geometry --------------------------------------------------------------


def nn_deg(pos: np.ndarray) -> np.ndarray:
    dots = np.clip(pos @ pos.T, -1.0, 1.0)
    np.fill_diagonal(dots, -1.0)
    return np.degrees(np.arccos(dots.max(axis=1)))


def occluded_frac(pos: np.ndarray) -> float:
    return float((nn_deg(pos) < OCCL_DEG).mean())


def probe_dist_deg(pos: np.ndarray, probes: np.ndarray) -> np.ndarray:
    dots = np.clip(probes @ pos.T, -1.0, 1.0)
    return np.degrees(np.arccos(dots.max(axis=1)))


def ocean_radius(lattice: np.ndarray, probes: np.ndarray) -> float:
    """The uniform pole defines zero ocean: at n=587 even equal spacing leaves
    gaps wider than a tile, so raw not-covered area would call the lattice 56%
    ocean. Ocean is emptiness beyond what uniform spacing already leaves."""
    return float(np.quantile(probe_dist_deg(lattice, probes), 0.99))


def ocean_frac(pos: np.ndarray, probes: np.ndarray, r_deg: float) -> float:
    return float((probe_dist_deg(pos, probes) > r_deg).mean())


def theme_silhouette(pos: np.ndarray, themes: np.ndarray) -> float:
    from sklearn.metrics import silhouette_score

    mask = themes >= 0
    d = np.arccos(np.clip(pos[mask] @ pos[mask].T, -1.0, 1.0))
    np.fill_diagonal(d, 0.0)
    return float(silhouette_score(d, themes[mask], metric="precomputed"))


def silhouette_null(pos: np.ndarray, themes: np.ndarray, n: int = N_SHUFFLES) -> np.ndarray:
    from sklearn.metrics import silhouette_score

    mask = themes >= 0
    d = np.arccos(np.clip(pos[mask] @ pos[mask].T, -1.0, 1.0))
    np.fill_diagonal(d, 0.0)
    rng = np.random.default_rng(SEED)
    labels = themes[mask]
    out = np.empty(n)
    for i in range(n):
        out[i] = silhouette_score(d, rng.permutation(labels), metric="precomputed")
    return out


def anchor_rho(pos: np.ndarray, ref: np.ndarray, themes: np.ndarray) -> float:
    """Do the landmasses stay where the compass put them: rank correlation of
    pairwise theme-centroid geodesics against raw radial."""
    from scipy.stats import spearmanr

    ids = sorted(t for t in set(themes.tolist()) if t >= 0)

    def cents(p: np.ndarray) -> np.ndarray:
        c = np.stack([p[themes == t].mean(axis=0) for t in ids])
        return c / np.linalg.norm(c, axis=1, keepdims=True)

    iu = np.triu_indices(len(ids), k=1)
    a = np.arccos(np.clip(cents(pos) @ cents(pos).T, -1, 1))[iu]
    b = np.arccos(np.clip(cents(ref) @ cents(ref).T, -1, 1))[iu]
    return float(spearmanr(a, b).statistic)


def trust(vm: tuple[np.ndarray, np.ndarray] | None, pos: np.ndarray) -> float | None:
    if vm is None:
        return None
    from sklearn.manifold import trustworthiness

    vecs, mask = vm
    p = pos[mask]
    nn = min(15, max(1, len(p) // 2 - 1))
    return float(trustworthiness(vecs, p, n_neighbors=nn, metric="cosine"))


# --- transforms ------------------------------------------------------------


def repulse(
    pos: np.ndarray, iters: int, target: float = 1.15 * OCCL, step: float = 0.35
) -> np.ndarray:
    """Arm B: fixed-iteration tangent repulsion. The seeded jitter exists only
    to break exactly-coincident bearings, where the tangent is undefined."""
    rng = np.random.default_rng(SEED)
    p = pos + rng.normal(0.0, 1e-4, pos.shape)
    p /= np.linalg.norm(p, axis=1, keepdims=True)
    for _ in range(iters):
        dots = np.clip(p @ p.T, -1.0, 1.0)
        ang = np.arccos(dots)
        w = np.where(ang < target, (target - ang) / target, 0.0)
        np.fill_diagonal(w, 0.0)
        if not w.any():
            break
        # tangent at i pointing away from j: p_i*cos(ang) - p_j, norm sin(ang)
        t = p[:, None, :] * dots[:, :, None] - p[None, :, :]
        t /= np.maximum(np.sqrt(1.0 - dots * dots), 1e-9)[:, :, None]
        p = p + step * OCCL * (w[:, :, None] * t).sum(axis=1)
        p /= np.linalg.norm(p, axis=1, keepdims=True)
    return p


def slot_assign(pos: np.ndarray, k: int) -> np.ndarray:
    """Arm C: assign to a k-times-oversampled fibonacci lattice, minimizing
    total geodesic displacement. Distinct slots bound the packing; empty
    slots are the ocean."""
    from scipy.optimize import linear_sum_assignment

    slots = fibonacci(k * len(pos))
    cost = np.arccos(np.clip(pos @ slots.T, -1.0, 1.0))
    rows, cols = linear_sum_assignment(cost)
    out = np.empty_like(pos)
    out[rows] = slots[cols]
    return out


def all_arms(block: dict) -> dict[str, np.ndarray]:
    arms: dict[str, np.ndarray] = {"radial": block["radial"], "lattice": block["lattice"]}
    if block["haversine"] is not None:
        arms["haversine"] = block["haversine"]
    for it in B_ITERS:
        print(f"  repulse radial iters={it}")
        arms[f"B-rep{it}"] = repulse(block["radial"], it)
    for k in C_KS:
        print(f"  slots radial k={k}")
        arms[f"C-k{k}"] = slot_assign(block["radial"], k)
    if block["haversine"] is not None:
        for it in B_ITERS:
            print(f"  repulse haversine iters={it}")
            arms[f"DB-rep{it}"] = repulse(block["haversine"], it)
        for k in C_KS:
            print(f"  slots haversine k={k}")
            arms[f"DC-k{k}"] = slot_assign(block["haversine"], k)
    return arms


# --- figures ---------------------------------------------------------------


def sphere_panel(ax, pos: np.ndarray, buried: np.ndarray) -> None:
    ax.scatter(*pos[~buried].T, c=GOLD, s=6, alpha=0.85, linewidths=0)
    ax.scatter(*pos[buried].T, c=RED, s=6, alpha=0.75, linewidths=0)
    fit3d(ax, pos, zoom=1.55)


def fig_poles(block: dict, out: Path, number: int = 1) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    layouts = [("radial", GOLD), ("haversine", BLUE), ("lattice", CYAN)]
    layouts = [(n, c) for n, c in layouts if block.get(n) is not None]
    n = len(block["radial"])
    fig, top = figure(
        16.4,
        7.4,
        number,
        "E29 · the continent frontier",
        "The planet as shipped: what the render threshold buries in each layout",
        meta=(
            f"n={n} content tiles · tile half-extent {TILE_HALF} "
            f"(scene.ts) · buried below {OCCL_DEG:.2f}° separation · "
            f"commit {sha()}"
        ),
    )
    gs = fig.add_gridspec(1, 4, left=0.035, right=0.965, top=top, bottom=0.075, wspace=0.16)
    occl = {}
    for i, (name, color) in enumerate(layouts):
        pos = block[name]
        sep = nn_deg(pos)
        buried = sep < OCCL_DEG
        occl[name] = float(buried.mean())
        ax = fig.add_subplot(gs[0, i], projection="3d", facecolor=PANEL)
        sphere_panel(ax, pos, buried)
        panel_title(ax, f"{name} — {buried.mean():.0%} buried")
    ax = fig.add_subplot(gs[0, len(layouts)])
    style_axes(ax)
    xmax = 12.0
    tails = []
    for name, color in layouts:
        sep = np.sort(nn_deg(block[name]))
        ax.plot(sep, np.arange(1, len(sep) + 1) / len(sep), color=color, lw=1.8)
        # label on the curve at its median crossing, clear of the other curves
        xm = float(np.quantile(sep, 0.55))
        ax.text(xm + 0.25, 0.55, name, color=color, fontsize=9, va="bottom")
        if sep[-1] > xmax:
            tails.append((name, color, sep[-1]))
    for i, (name, color, tail) in enumerate(tails):
        ax.text(
            xmax - 0.2,
            0.10 + 0.06 * i,
            f"{name} tail to {tail:.0f}°",
            color=color,
            fontsize=8,
            ha="right",
        )
    ax.axvline(OCCL_DEG, color=RED, lw=1.2)
    ax.text(
        OCCL_DEG,
        0.02,
        f" half-tile {OCCL_DEG:.1f}°",
        color=RED,
        fontsize=9,
        rotation=90,
        va="bottom",
    )
    ax.set_xlabel("nearest-neighbour separation (deg)")
    ax.set_ylabel("fraction of tiles")
    ax.set_xlim(0, xmax)
    panel_title(ax, "separation CDF vs the render threshold")
    verdict(fig, f"{occl['radial']:.0%} of the radial planet is more than half hidden")
    frame_panels(fig)
    fig.savefig(out, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print(f"wrote {out}")


def fig_gallery(
    block: dict, arms: dict, probes: np.ndarray, r_deg: float, out: Path, number: int = 2
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = [
        ("C — slot assignment on radial, k sweep", [f"C-k{k}" for k in C_KS]),
        ("B — tangent repulsion on radial, iteration sweep", [f"B-rep{i}" for i in B_ITERS]),
        ("D — slot assignment on haversine, k sweep", [f"DC-k{k}" for k in C_KS]),
    ]
    rows = [(t, names) for t, names in rows if all(n in arms for n in names)]
    fig, top = figure(
        15.2,
        4.6 + 3.6 * len(rows),
        number,
        "E29 · the continent frontier",
        "The mechanisms: what each knob buys in visibility and costs in ocean",
        meta=(
            f"gold visible · red buried (sep < {OCCL_DEG:.2f}°) · "
            f"ocean = sphere area farther than {r_deg:.1f}° from any tile "
            f"(p99 of the uniform pole's gaps) · commit {sha()}"
        ),
    )
    gs = fig.add_gridspec(
        len(rows), 4, left=0.035, right=0.965, top=top, bottom=0.045, wspace=0.14, hspace=0.30
    )
    for r, (rtitle, names) in enumerate(rows):
        for c, name in enumerate(names):
            pos = arms[name]
            buried = nn_deg(pos) < OCCL_DEG
            ax = fig.add_subplot(gs[r, c], projection="3d", facecolor=PANEL)
            sphere_panel(ax, pos, buried)
            knob = name.split("-")[-1]
            panel_title(
                ax,
                f"{knob}: {buried.mean():.0%} buried · ocean {ocean_frac(pos, probes, r_deg):.0%}",
                width=34,
            )
        fig.text(
            0.035,
            gs[r, 0].get_position(fig).y1 + 0.030,
            rtitle,
            color=MUTED,
            fontsize=10,
        )
    verdict(
        fig,
        f"poles: radial ocean {ocean_frac(block['radial'], probes, r_deg):.0%} "
        f"at {occluded_frac(block['radial']):.0%} buried · "
        f"lattice ocean {ocean_frac(block['lattice'], probes, r_deg):.0%} at 0%",
    )
    frame_panels(fig)
    fig.savefig(out, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print(f"wrote {out}")


def fig_frontier(metrics: dict, null: np.ndarray, out: Path, number: int = 3) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, top = figure(
        15.2,
        8.6,
        number,
        "E29 · the continent frontier",
        "Visibility against geography: every arm priced on the same two axes",
        meta=(
            f"x: tiles buried at the render threshold · y: ocean fraction · "
            f"silhouette null: {len(null)} theme shuffles · commit {sha()}"
        ),
    )
    gs = fig.add_gridspec(1, 3, left=0.035, right=0.965, top=top, bottom=0.085, wspace=0.24)
    ax = fig.add_subplot(gs[0, :2])
    style_axes(ax)
    paths = [
        ("C-k", C_KS, BLUE, "slots on radial"),
        ("B-rep", B_ITERS, GOLD, "repulsion on radial"),
        ("DC-k", C_KS, CYAN, "slots on haversine"),
        ("DB-rep", B_ITERS, PURPLE, "repulsion on haversine"),
    ]
    for prefix, knobs, color, label in paths:
        pts = [
            (metrics[f"{prefix}{k}"]["occluded"], metrics[f"{prefix}{k}"]["ocean"])
            for k in knobs
            if f"{prefix}{k}" in metrics
        ]
        if not pts:
            continue
        xs, ys = zip(*pts)
        ax.plot(xs, ys, color=color, lw=1.4, alpha=0.8)
        ax.scatter(xs, ys, color=color, s=34, zorder=5)
        ax.annotate(
            label,
            (xs[-1], ys[-1]),
            color=color,
            fontsize=9,
            xytext=(6, 4),
            textcoords="offset points",
        )
    for pole in ("radial", "haversine", "lattice"):
        if pole not in metrics:
            continue
        m = metrics[pole]
        ax.scatter([m["occluded"]], [m["ocean"]], color=DIM, s=70, zorder=4)
        ax.annotate(
            pole,
            (m["occluded"], m["ocean"]),
            color=MUTED,
            fontsize=9,
            xytext=(6, -10),
            textcoords="offset points",
        )
    ax.axhline(metrics["radial"]["ocean"] / 2, color=RED, lw=1.0, ls="--")
    ax.text(
        0.99,
        metrics["radial"]["ocean"] / 2,
        "half of radial's ocean ",
        color=RED,
        fontsize=9,
        ha="right",
        va="bottom",
    )
    ax.set_xlabel("fraction of tiles buried (sep < half-tile)")
    ax.set_ylabel("ocean fraction")
    panel_title(ax, "the frontier: lower-left is lattice-land, upper-right is buried continents")

    ax2 = fig.add_subplot(gs[0, 2])
    style_axes(ax2)
    names = [k for k in metrics if not k.startswith("DB")]
    sils = [metrics[k]["silhouette"] for k in names]
    ax2.hist(null, bins=40, color=DIM, orientation="horizontal", density=True)
    for k, s in zip(names, sils):
        color = (
            GOLD
            if k.startswith("B")
            else BLUE
            if k.startswith("C")
            else CYAN
            if k.startswith("DC")
            else MUTED
        )
        ax2.axhline(s, color=color, lw=1.0, alpha=0.8)
    for pole in ("radial", "lattice"):
        ax2.text(
            0.97,
            metrics[pole]["silhouette"],
            pole,
            color=MUTED,
            fontsize=8.5,
            ha="right",
            va="bottom",
            transform=ax2.get_yaxis_transform(),
        )
    ax2.set_ylabel("theme silhouette (geodesic)")
    ax2.set_xlabel("shuffle-null density")
    panel_title(ax2, "coherence: every arm vs the shuffled-theme null", width=34)
    best = metrics.get("B-rep40")
    if best:
        verdict(
            fig,
            f"repulsion-40 on radial: 0% buried, ocean {best['ocean']:.0%}, anchor {best['anchor_rho']:.3f}",
        )
    frame_panels(fig)
    fig.savefig(out, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print(f"wrote {out}")


# --- stages ----------------------------------------------------------------


def compute_metrics(
    arms: dict, block: dict, vecs: np.ndarray | None, probes: np.ndarray, r_deg: float
) -> dict:
    metrics = {}
    for name, pos in arms.items():
        print(f"  metrics {name}")
        metrics[name] = {
            "occluded": occluded_frac(pos),
            "ocean": ocean_frac(pos, probes, r_deg),
            "silhouette": theme_silhouette(pos, block["themes"]),
            "anchor_rho": anchor_rho(pos, block["radial"], block["themes"]),
            "trustworthiness": trust(vecs, pos),
        }
    return metrics


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["data", "transforms", "frontier", "assets"])
    ap.add_argument("--out", default=os.environ.get("CLAUDE_JOB_DIR", "/tmp") + "/tmp")
    args = ap.parse_args()
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    block = load_block()
    probes = fibonacci(N_PROBES)
    r_deg = ocean_radius(block["lattice"], probes)
    print(f"{len(block['radial'])} tiles, occlusion {OCCL_DEG:.3f}°, ocean radius {r_deg:.3f}°")

    if args.stage == "data":
        for name in ("radial", "haversine", "lattice"):
            if block.get(name) is None:
                continue
            pos = block[name]
            print(
                f"  {name}: occluded {occluded_frac(pos):.1%} "
                f"ocean {ocean_frac(pos, probes, r_deg):.1%} "
                f"sil {theme_silhouette(pos, block['themes']):.3f}"
            )
        fig_poles(block, outdir / "e29-cp1-poles.png")
        return

    if args.stage == "transforms":
        arms = all_arms(block)
        np.savez_compressed(CACHE, **arms)
        print(f"cached {len(arms)} layouts -> {CACHE}")
        fig_gallery(block, arms, probes, r_deg, outdir / "e29-cp2-mechanisms.png")
        return

    arms = dict(np.load(CACHE)) if CACHE.exists() else all_arms(block)

    if args.stage == "frontier":
        vecs = load_vecs()
        metrics = compute_metrics(arms, block, vecs, probes, r_deg)
        null = silhouette_null(block["radial"], block["themes"])
        METRICS.write_text(json.dumps({"metrics": metrics, "null": null.tolist()}, indent=1))
        print(f"cached metrics -> {METRICS}")
        fig_frontier(metrics, null, outdir / "e29-cp3-frontier.png")
        # pre-registered verdict (issue #175)
        floor = metrics["radial"]["ocean"] / 2
        null_hi = float(np.quantile(null, 0.999))
        winners = [
            k
            for k, m in metrics.items()
            if k not in ("radial", "haversine", "lattice")
            and m["occluded"] == 0.0
            and m["ocean"] >= floor
            and m["silhouette"] > null_hi
        ]
        print(f"pre-registered winners (occl=0, ocean>={floor:.1%}, sil>null): {winners or 'none'}")
        return

    if args.stage == "assets":
        ASSETS.mkdir(parents=True, exist_ok=True)
        saved = json.loads(METRICS.read_text())
        fig_poles(block, ASSETS / "01-the-buried-planet.png", number=1)
        fig_gallery(block, arms, probes, r_deg, ASSETS / "02-the-mechanisms.png", number=2)
        fig_frontier(
            saved["metrics"], np.asarray(saved["null"]), ASSETS / "03-the-frontier.png", number=3
        )


if __name__ == "__main__":
    main()
