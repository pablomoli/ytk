"""E32 — the galaxy layout: a legible sky over the planets.

Toward #78, via #177. Every theme becomes a planet: position from its
members' centroid under the map's already-fitted projection (arm A, agrees
with /map by construction), radius ∝ n^(1/3), Sudarsky class from activity
(E31's taxonomy, now over the full population where classes I-III can
appear). Arm B recurses E29's tangent repulsion upward with a per-pair
target — discs clear each other at r_i + r_j. Arm C fits the sky to itself
(haversine UMAP on the centroid vectors) and pins the broken-agreement pole.

The render threshold is the disc radius itself; its floor is anchored in
render truth: the smallest planet must draw at least as large as one tile
does on /orb today (OCCL_DEG), which fixes K_min for the scale sweep.

    uv run --with matplotlib,scipy,scikit-learn,umap-learn python \
        scripts/e32_galaxy.py galaxy
    ...                       figures
    ...                       assets
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e30_coastlines as e30
import e31_theme_planets as e31
from plot_assets import (
    BG,
    BLUE,
    DIM,
    DPI,
    GOLD,
    MUTED,
    RED,
    TEXT,
    figure,
    frame_panels,
    panel_title,
    punch,
    style_axes,
    verdict,
)

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from ytk.spheremap import OCCL_DEG, fibonacci, haversine
from ytk.store import EMBEDDING_EPOCH

MAP = Path(os.path.expanduser("~/.ytk/map.json"))
CACHE = Path(os.path.expanduser("~/.ytk/e32-galaxy.json"))
ASSETS = REPO / "docs" / "assets" / "32-galaxy"

# scale sweep: radius_deg = K * n^(1/3); the upper end sits past the packing
# bound for this population (sum of cap areas reaches the whole sphere)
K_GRID = np.round(np.arange(0.25, 9.01, 0.25), 2)
OCCL_BAR = 0.05  # pre-registered: ship the cheapest arm under 5% hidden disc area
N_PROBES = 200_000
N_NULL = 2000


def load_all() -> dict:
    d = e31.load()
    groups = json.loads(MAP.read_text())["content"]["groups"]
    d["map_xy"] = np.asarray([[g["x"], g["y"]] for g in groups], dtype=float)
    return d


def all_planets(d: dict) -> list[dict]:
    """E31's per-theme properties over the full population, no surface arms."""
    today = datetime.date.today()
    out = []
    for t in sorted(int(x) for x in np.unique(d["themes"]) if x >= 0):
        m = d["themes"] == t
        vecs = d["vecs"][m]
        n = int(m.sum())
        dates = [x for x, keep in zip(d["dates"], m) if keep and x]
        recent = sum(
            1 for x in dates if (today - datetime.date.fromisoformat(x)).days <= e31.ACTIVE_DAYS
        )
        activity = recent / len(dates) if dates else 0.0
        vn = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
        cent = vn.mean(axis=0)
        cent /= np.linalg.norm(cent)
        cls, cls_label, hue = e31.classify(activity)
        out.append(
            {
                "theme": t,
                "label": d["labels"][t],
                "n": n,
                "activity": activity,
                "date_coverage": len(dates) / n,
                "cohesion": float((vn @ cent).mean()),
                "cls": cls,
                "cls_label": cls_label,
                "hue": hue,
                "cbrt": float(n ** (1 / 3)),
                "cent_c3": np.asarray(d["c3"])[m].mean(axis=0).tolist(),
                "cent_vec": cent.tolist(),
                "map_xy": d["map_xy"][t].tolist(),
            }
        )
    return out


def arm_a(planets: list[dict], c3_all: np.ndarray) -> np.ndarray:
    """Members' centroid as a direction from the content cloud's own center —
    the same origin the tile layer's radial() uses, so a planet hangs over
    its members' tiles on /orb."""
    v = np.asarray([p["cent_c3"] for p in planets]) - c3_all.mean(axis=0)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def spread_discs(
    pos: np.ndarray,
    radii: np.ndarray,
    iters: int = 300,
    step: float = 0.35,
    margin: float = 1.05,
    seed: int = 32,
) -> np.ndarray:
    """E29's tangent repulsion with a per-pair target: discs of angular radius
    r_i, r_j (radians) clear each other at r_i + r_j. Every planet moves with
    equal weight; the anchor axis prices what that costs."""
    rng = np.random.default_rng(seed)
    p = np.asarray(pos, dtype=float) + rng.normal(0.0, 1e-4, pos.shape)
    p /= np.linalg.norm(p, axis=1, keepdims=True)
    target = margin * (radii[:, None] + radii[None, :])
    for _ in range(iters):
        dots = np.clip(p @ p.T, -1.0, 1.0)
        ang = np.arccos(dots)
        w = np.where(ang < target, (target - ang) / target, 0.0)
        np.fill_diagonal(w, 0.0)
        if not w.any():
            break
        t = p[:, None, :] * dots[:, :, None] - p[None, :, :]
        t /= np.maximum(np.sqrt(1.0 - dots * dots), 1e-9)[:, :, None]
        p = p + step * ((w * target)[:, :, None] * t).sum(axis=1)
        p /= np.linalg.norm(p, axis=1, keepdims=True)
    return p


def probe_angles(pos: np.ndarray, probes: np.ndarray) -> np.ndarray:
    return np.degrees(np.arccos(np.clip(probes @ pos.T, -1.0, 1.0)))


def occlusion(ang: np.ndarray, radii_deg: np.ndarray, order: np.ndarray) -> float:
    """Hidden fraction of total disc area under a deterministic z-order
    (larger n paints on top — big planets are the landmarks). Monte-Carlo on
    fibonacci probes; big discs dominate the area weighting."""
    inside = ang < radii_deg[None, :]
    covered = np.zeros(ang.shape[0], dtype=bool)
    hidden = total = 0
    for j in order:
        col = inside[:, j]
        hidden += int((col & covered).sum())
        total += int(col.sum())
        covered |= col
    return hidden / max(total, 1)


def spearman_pairs(pos: np.ndarray, ref_xy: np.ndarray) -> float:
    from scipy.stats import spearmanr

    dots = np.clip(pos @ pos.T, -1.0, 1.0)
    iu = np.triu_indices(len(pos), 1)
    gal = np.arccos(dots)[iu]
    ref = np.linalg.norm(ref_xy[:, None, :] - ref_xy[None, :, :], axis=-1)[iu]
    return float(spearmanr(gal, ref).statistic)


def agreement_null(pos: np.ndarray, ref_xy: np.ndarray, seed: int = 32) -> np.ndarray:
    """Permute which planet owns which map centroid: the rho a sky earns with
    the geometry intact but the identity scrambled."""
    rng = np.random.default_rng(seed)
    return np.asarray(
        [spearman_pairs(pos, ref_xy[rng.permutation(len(ref_xy))]) for _ in range(N_NULL)]
    )


def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB in [0,1] -> CIELAB (D65). CIE76 distance on the result is the
    measured pairwise color separation."""
    r = np.where(rgb > 0.04045, ((rgb + 0.055) / 1.055) ** 2.4, rgb / 12.92)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = r @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack(
        [116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])],
        axis=-1,
    )


def planet_colors(planets: list[dict]) -> np.ndarray:
    """The rendered color: class hue, saturation carrying cohesion spread
    across the population (E31's gallery rule, verbatim)."""
    import matplotlib.colors as mcolors

    cohs = [p["cohesion"] for p in planets]
    lo, hi = min(cohs), max(cohs)
    out = []
    for p in planets:
        base = np.asarray(mcolors.to_rgb(p["hue"]))
        sat = 0.3 + 0.7 * ((p["cohesion"] - lo) / (hi - lo) if hi > lo else 1.0)
        out.append(np.clip(base * sat + np.asarray(mcolors.to_rgb(DIM)) * (1 - sat), 0, 1))
    return np.asarray(out)


def build(d: dict) -> dict:
    planets = all_planets(d)
    n_pl = len(planets)
    cbrt = np.asarray([p["cbrt"] for p in planets])
    order = np.argsort([-p["n"] for p in planets])  # z-order: big paints first
    map_xy = np.asarray([p["map_xy"] for p in planets])
    cent_vecs = np.asarray([p["cent_vec"] for p in planets])
    probes = fibonacci(N_PROBES)

    a = arm_a(planets, np.asarray(d["c3"]))
    ang_a = probe_angles(a, probes)
    k_min = float(OCCL_DEG / cbrt.min())

    occl_a, occl_b, anchor_disp, anchor_rho = [], [], [], []
    b_by_k: dict[float, np.ndarray] = {}
    for k in K_GRID:
        radii = k * cbrt
        occl_a.append(occlusion(ang_a, radii, order))
        b = spread_discs(a, np.radians(radii))
        b_by_k[float(k)] = b
        occl_b.append(occlusion(probe_angles(b, probes), radii, order))
        disp = np.degrees(np.arccos(np.clip((a * b).sum(axis=1), -1.0, 1.0)))
        anchor_disp.append(float((disp / radii).mean()))
        anchor_rho.append(spearman_pairs_between(a, b))
        print(
            f"K={k:5.2f}  occl A {occl_a[-1]:6.1%}  B {occl_b[-1]:6.1%}  "
            f"disp/r {anchor_disp[-1]:.3f}  rho(A,B) {anchor_rho[-1]:.4f}"
        )

    def k_star(occl: list[float]) -> float:
        ok = [float(k) for k, o in zip(K_GRID, occl) if o <= OCCL_BAR]
        # the largest contiguous-from-zero scale: past the first failure the
        # sky has already stopped being legible, whatever happens later
        out = 0.0
        for k, o in zip(K_GRID, occl):
            if o > OCCL_BAR:
                break
            out = float(k)
        return out or (ok[0] if ok else 0.0)

    ks_a, ks_b = k_star(occl_a), k_star(occl_b)
    c = haversine(cent_vecs, n_neighbors=min(30, n_pl - 2), min_dist=0.05)

    rho_a = spearman_pairs(a, map_xy)
    null = agreement_null(a, map_xy)
    null_hi = float(np.quantile(null, 0.95))
    rho_c = spearman_pairs(c, map_xy) if c is not None else None

    # pre-registered rule: cheapest arm under the occlusion bar at a scale
    # that renders every planet at least tile-sized, agreement clear of C
    arm = "A" if ks_a >= k_min else "B"
    k_ship = ks_a if arm == "A" else ks_b
    b_ship = b_by_k[min(b_by_k, key=lambda k: abs(k - k_ship))]
    rho_b = spearman_pairs(b_ship, map_xy)
    ship_pos = a if arm == "A" else b_ship
    rho_ship = rho_a if arm == "A" else rho_b
    clear = rho_ship > null_hi and (rho_c is None or rho_ship > rho_c)

    colors = planet_colors(planets)
    lab = srgb_to_lab(colors)
    de = np.linalg.norm(lab[:, None, :] - lab[None, :, :], axis=-1)
    cls = [p["cls"] for p in planets]
    iu = np.triu_indices(n_pl, 1)
    across = [float(de[i, j]) for i, j in zip(*iu) if cls[i] != cls[j]]
    within = [float(de[i, j]) for i, j in zip(*iu) if cls[i] == cls[j]]
    top5 = np.argsort([-p["n"] for p in planets])[:5]
    top5_de = [float(de[i, j]) for i in top5 for j in top5 if i < j]

    trust = {
        "A": e31.trust(cent_vecs, a),
        "B": e31.trust(cent_vecs, b_ship),
        "C": e31.trust(cent_vecs, c) if c is not None else None,
    }
    return {
        "epoch": EMBEDDING_EPOCH,
        "commit": e31.sha(),
        "n_planets": n_pl,
        "k_grid": [float(k) for k in K_GRID],
        "k_min": k_min,
        "occl_a": occl_a,
        "occl_b": occl_b,
        "anchor_disp": anchor_disp,
        "anchor_rho": anchor_rho,
        "k_star_a": ks_a,
        "k_star_b": ks_b,
        "arm": arm,
        "k_ship": float(k_ship),
        "agreement": {
            "A": rho_a,
            "B": rho_b,
            "C": rho_c,
            "null_hi": null_hi,
            "null": null.tolist(),
            "clear": bool(clear),
        },
        "trust": trust,
        "legibility": {
            "census": {c: cls.count(c) for c in ["I", "II", "III", "IV", "V"]},
            "across": across,
            "within": within,
            "top5": top5_de,
        },
        "pos": {
            "A": np.round(a, 4).tolist(),
            "B": np.round(b_ship, 4).tolist(),
            "C": np.round(c, 4).tolist() if c is not None else None,
            "ship": np.round(ship_pos, 4).tolist(),
        },
        "planets": planets,
    }


def spearman_pairs_between(a: np.ndarray, b: np.ndarray) -> float:
    from scipy.stats import spearmanr

    iu = np.triu_indices(len(a), 1)
    da = np.arccos(np.clip(a @ a.T, -1, 1))[iu]
    db = np.arccos(np.clip(b @ b.T, -1, 1))[iu]
    return float(spearmanr(da, db).statistic)


# --- figures ---------------------------------------------------------------


def fig_sky(r: dict, out: Path, number: int = 1) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import patheffects as pe

    planets = r["planets"]
    pos = np.asarray(r["pos"]["ship"])
    radii = r["k_ship"] * np.asarray([p["cbrt"] for p in planets])
    colors = planet_colors(planets)
    ll, tt, xyz = e30.grid()
    ang = np.degrees(np.arccos(np.clip(xyz.reshape(-1, 3) @ pos.T, -1, 1))).reshape(
        *xyz.shape[:2], -1
    )

    fig, top = figure(
        16.0,
        8.8,
        number,
        "E32 · the galaxy",
        "The sky: every theme a planet, placed by its members, classed by its physics",
        meta=(
            f"{len(planets)} planets · arm {r['arm']} at K={r['k_ship']:.2f}°/n^(1/3) · "
            f"occlusion {r['occl_a'][r['k_grid'].index(r['k_ship'])] if r['arm'] == 'A' else r['occl_b'][r['k_grid'].index(r['k_ship'])]:.1%} · "
            f"map agreement rho {r['agreement'][r['arm']]:.3f} (null 95th {r['agreement']['null_hi']:.3f}) · "
            f"epoch {r['epoch']} · commit {r['commit']}"
        ),
    )
    gs = fig.add_gridspec(1, 1, left=0.05, right=0.95, top=top, bottom=0.06)
    ax = e30._moll(fig, gs[0, 0])
    # paint small planets first so the z-order on paper matches the measured
    # one: larger n covers
    paint = np.zeros((*ang.shape[:2], 3))
    for j in np.argsort([p["n"] for p in planets]):
        a_j = ang[:, :, j]
        # feather one grid step wide: kills the pixel-stair rim without
        # moving the measured disc boundary
        w = np.clip((radii[j] - a_j) / 0.5, 0, 1)[:, :, None]
        shade = punch(np.clip(1.0 - a_j / radii[j], 0, 1))[:, :, None]
        paint = paint * (1 - w) + colors[j] * (0.35 + 0.65 * shade) * w
    ax.pcolormesh(ll, tt, paint, shading="auto", rasterized=True)
    lon = np.arctan2(pos[:, 1], pos[:, 0])
    lat = np.arcsin(np.clip(pos[:, 2], -1, 1))
    if r["pos"]["C"] is not None:
        cpos = np.asarray(r["pos"]["C"])
        ax.scatter(
            np.arctan2(cpos[:, 1], cpos[:, 0]),
            np.arcsin(np.clip(cpos[:, 2], -1, 1)),
            s=46,
            facecolors="none",
            edgecolors=DIM,
            linewidths=1.2,
        )
    ax.scatter(lon, lat, s=4, c=TEXT, alpha=0.9, linewidths=0)
    # the biggest planets plus every non-V world: the census is the finding
    big = set(np.argsort([-p["n"] for p in planets])[:8]) | {
        j for j, p in enumerate(planets) if p["cls"] != "V"
    }
    for j in big:
        ax.annotate(
            f"{planets[j]['label']}\n{planets[j]['cls']} · n={planets[j]['n']}",
            (lon[j], lat[j]),
            color=TEXT,
            fontsize=7.5,
            ha="center",
            va="center",
            path_effects=[pe.withStroke(linewidth=2.2, foreground=BG)],
        )
    panel_title(
        ax,
        "discs at the shipped scale, shaded to center, hue = Sudarsky class, "
        "saturation = cohesion; DIM rings mark arm C's self-fitted sky (the control)",
        width=110,
    )
    verdict(
        fig,
        f"arm {r['arm']} ships · K* A {r['k_star_a']:.2f}° / B {r['k_star_b']:.2f}° · "
        f"K_min {r['k_min']:.2f}°",
    )
    frame_panels(fig)
    fig.savefig(out, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print(f"wrote {out}")


def fig_frontier(r: dict, out: Path, number: int = 2) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ks = np.asarray(r["k_grid"])
    fig, top = figure(
        15.2,
        7.8,
        number,
        "E32 · the galaxy",
        "The frontier: how large a sky each arm affords, and what agreement it keeps",
        meta=(
            f"{r['n_planets']} planets · occlusion = hidden disc area under larger discs "
            f"({N_PROBES // 1000}k probes) · K_min: smallest planet at tile size "
            f"(OCCL {OCCL_DEG:.2f}°) · rho vs map centroids, {N_NULL} permutations · "
            f"commit {r['commit']}"
        ),
    )
    gs = fig.add_gridspec(1, 2, left=0.06, right=0.96, top=top, bottom=0.11, wspace=0.26)

    ax = fig.add_subplot(gs[0, 0])
    style_axes(ax)
    ax.plot(ks, np.asarray(r["occl_a"]) * 100, color=GOLD, lw=1.8, label="A · centroid")
    ax.plot(ks, np.asarray(r["occl_b"]) * 100, color=BLUE, lw=1.8, label="B · A + spread")
    ax.axhline(OCCL_BAR * 100, color=RED, lw=1.1, ls="--")
    ax.axvline(r["k_min"], color=MUTED, lw=1.0, ls=":")
    for kstar, color in [(r["k_star_a"], GOLD), (r["k_star_b"], BLUE)]:
        if kstar:
            ax.scatter([kstar], [OCCL_BAR * 100], color=color, s=42, zorder=5)
    ax.set_xlabel("K — disc scale (deg per n^(1/3))")
    ax.set_ylabel("occluded disc area (%)")
    ax.legend(loc="upper left", fontsize=9, framealpha=0.0, labelcolor=TEXT)
    panel_title(
        ax,
        f"occlusion vs scale — A holds to K*={r['k_star_a']:.2f}°, "
        f"B to K*={r['k_star_b']:.2f}°; dotted line = tile-size floor",
        width=60,
    )

    ax2 = fig.add_subplot(gs[0, 1])
    style_axes(ax2)
    null = np.asarray(r["agreement"]["null"])
    ax2.hist(null, bins=40, color=DIM, density=True)
    # A and B sit within 0.01 of each other: stagger heights and sides so
    # the labels never collide
    labels = [("A", GOLD, 0.92, "right"), ("B", BLUE, 0.82, "left"), ("C", RED, 0.70, "right")]
    for name, color, y, ha in labels:
        rho = r["agreement"][name]
        if rho is None:
            continue
        ax2.axvline(rho, color=color, lw=1.8)
        ax2.annotate(
            f" {name} {rho:.3f} ",
            (rho, ax2.get_ylim()[1] * y),
            color=color,
            fontsize=9,
            ha=ha,
        )
    ax2.set_xlabel("Spearman rho — sky pairwise distance vs 2D map centroids")
    ax2.set_ylabel("density")
    panel_title(
        ax2,
        "map agreement — DIM = identity-shuffled null; C is the sky fitted "
        "to itself, the broken-agreement pole",
        width=60,
    )
    verdict(
        fig,
        f"arm {r['arm']} ships at K={r['k_ship']:.2f}° · rho {r['agreement'][r['arm']]:.3f} "
        f"clear of null {r['agreement']['null_hi']:.3f}"
        + (f" and C {r['agreement']['C']:.3f}" if r["agreement"]["C"] is not None else ""),
    )
    frame_panels(fig)
    fig.savefig(out, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print(f"wrote {out}")


def fig_classes(r: dict, out: Path, number: int = 3) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    leg = r["legibility"]
    fig, top = figure(
        15.2,
        7.4,
        number,
        "E32 · the galaxy",
        "Class legibility: does the mid-tail give hue something to separate?",
        meta=(
            f"{r['n_planets']} planets · color as rendered (class hue x cohesion "
            f"saturation) · distance CIE76 in CIELAB · JND ~2.3 for large fields, "
            f"small discs need more · E31 pole: the top five's pairwise distances · "
            f"commit {r['commit']}"
        ),
    )
    gs = fig.add_gridspec(1, 2, left=0.06, right=0.96, top=top, bottom=0.12, wspace=0.26)

    ax = fig.add_subplot(gs[0, 0])
    style_axes(ax)
    census = leg["census"]
    hues = {c: h for c, _, _, h in e31.CLASSES}
    names = ["I", "II", "III", "IV", "V"]
    ax.bar(names, [census[c] for c in names], color=[hues[c] for c in names])
    ax.set_ylabel("planets")
    ax.set_xlabel("Sudarsky class (activity translation)")
    panel_title(
        ax,
        f"the census — {sum(1 for c in names if census[c])} of 5 classes present "
        f"(E31's top five degenerated to V/IV)",
        width=60,
    )

    ax2 = fig.add_subplot(gs[0, 1])
    style_axes(ax2)
    bins = np.linspace(0, max(leg["across"] + leg["within"] + [1.0]), 30)
    ax2.hist(leg["within"], bins=bins, color=DIM, label="same class (saturation only)")
    ax2.hist(leg["across"], bins=bins, color=GOLD, alpha=0.75, label="across classes (hue carries)")
    for x in leg["top5"]:
        ax2.axvline(x, color=RED, lw=0.8, alpha=0.55, ymax=0.12)
    ax2.axvline(2.3, color=RED, lw=1.1, ls="--")
    ax2.set_xlabel("pairwise color distance (CIE76)")
    ax2.set_ylabel("planet pairs")
    ax2.legend(loc="upper right", fontsize=9, framealpha=0.0, labelcolor=TEXT)
    panel_title(
        ax2,
        "rendered color distances — red ticks are the top five's pairs "
        "(the E31 degeneracy), dashed red the large-field JND",
        width=60,
    )
    across_min = min(leg["across"]) if leg["across"] else 0.0
    verdict(
        fig,
        f"{sum(1 for c in names if census[c])}/5 classes present · "
        f"min across-class dE {across_min:.1f}",
    )
    frame_panels(fig)
    fig.savefig(out, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print(f"wrote {out}")


# --- stages ----------------------------------------------------------------


def write_galaxy_json(r: dict, out: Path) -> None:
    """The frontend's input. The renderer must consume radius_deg verbatim —
    the disc radius is the galaxy's render threshold (sync constraint, same
    contract as TILE_HALF)."""
    payload = {
        "epoch": r["epoch"],
        "commit": r["commit"],
        "arm": r["arm"],
        "k_deg_per_cbrt_n": r["k_ship"],
        "k_min_deg": r["k_min"],
        "occlusion_bar": OCCL_BAR,
        "agreement_rho": r["agreement"][r["arm"]],
        "planets": [
            {
                **{
                    k: p[k]
                    for k in (
                        "theme",
                        "label",
                        "n",
                        "activity",
                        "date_coverage",
                        "cohesion",
                        "cls",
                        "cls_label",
                        "hue",
                        "map_xy",
                    )
                },
                "radius_deg": round(r["k_ship"] * p["cbrt"], 3),
                "pos": pos,
            }
            for p, pos in zip(r["planets"], r["pos"]["ship"])
        ],
    }
    out.write_text(json.dumps(payload, indent=1))
    print(f"wrote {out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["galaxy", "figures", "assets"])
    ap.add_argument("--out", default=os.environ.get("CLAUDE_JOB_DIR", "/tmp") + "/tmp")
    args = ap.parse_args()
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    if args.stage == "galaxy" or not CACHE.exists():
        r = build(load_all())
        CACHE.write_text(json.dumps(r))
        print(
            f"cached -> {CACHE}\n"
            f"K* A {r['k_star_a']:.2f}° / B {r['k_star_b']:.2f}° · K_min {r['k_min']:.2f}° · "
            f"arm {r['arm']} at K={r['k_ship']:.2f}° · "
            f"rho A {r['agreement']['A']:.3f} B {r['agreement']['B']:.3f} "
            f"C {r['agreement']['C'] if r['agreement']['C'] is not None else 'failed'} · "
            f"null_hi {r['agreement']['null_hi']:.3f} · "
            f"census {r['legibility']['census']}"
        )
        if args.stage == "galaxy":
            return
    r = json.loads(CACHE.read_text())

    if args.stage == "figures":
        fig_sky(r, outdir / "e32-cp1-sky.png")
        fig_frontier(r, outdir / "e32-cp2-frontier.png")
        fig_classes(r, outdir / "e32-cp3-classes.png")
        return

    if args.stage == "assets":
        ASSETS.mkdir(parents=True, exist_ok=True)
        fig_sky(r, ASSETS / "01-the-sky.png", number=1)
        fig_frontier(r, ASSETS / "02-the-frontier.png", number=2)
        fig_classes(r, ASSETS / "03-the-classes.png", number=3)
        write_galaxy_json(r, ASSETS / "galaxy.json")


if __name__ == "__main__":
    main()
