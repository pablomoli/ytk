"""E31 — theme planets: refit vs slice, and a Sudarsky-inspired visual taxonomy.

Toward #78, via #176. The E29/E30 pipeline takes any set of vectors; this
harness applies it to the top themes twice — slicing the superplanet's stored
c3 versus refitting UMAP-3D on the subset alone — and scores both with the
E29 machinery. Visual identity per planet is derived, not assigned: activity
maps to a Sudarsky albedo class (I-V, astro-ph/9910504), cohesion to
saturation, size to n^(1/3); Batalha 2018's caution (arXiv:1807.08453) is
honored by never letting color carry the taxonomy alone.

    uv run --with matplotlib,scipy,scikit-learn,umap-learn python \
        scripts/e31_theme_planets.py planets
    ...                              figures
    ...                              assets
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e30_coastlines as e30
from plot_assets import (
    BG,
    DIM,
    DPI,
    PANEL,
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
from ytk.spheremap import OCCL_DEG, fibonacci, radial, spread

MAP = Path(os.path.expanduser("~/.ytk/map.json"))
CACHE = Path(os.path.expanduser("~/.ytk/e31-planets.json"))
ASSETS = REPO / "docs" / "assets" / "31-theme-planets"

TOP_N = 5
ACTIVE_DAYS = 90

# Sudarsky albedo classes, translated: activity share of dated notes in the
# last ACTIVE_DAYS decides the class; each class carries a land ramp
# (dark -> hue) and a display name. Thresholds are stated, not fitted.
CLASSES = [
    ("V", 0.50, "silicate glow", "#ffb08a"),
    ("IV", 0.30, "alkali dark", "#8a5a3a"),
    ("III", 0.15, "clear rayleigh", "#5a8cff"),
    ("II", 0.05, "water cloud", "#cfe0f0"),
    ("I", 0.00, "ammonia bands", "#e0cfa0"),
]


def sha() -> str:
    r = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True
    )
    return r.stdout.strip() or "unknown"


def classify(activity: float) -> tuple[str, str, str]:
    for name, floor, label, hue in CLASSES:
        if activity >= floor:
            return name, label, hue
    return CLASSES[-1][0], CLASSES[-1][2], CLASSES[-1][3]


def load() -> dict:
    import build_map

    data = json.loads(MAP.read_text())
    cpts = [p for p in data["points"] if "c3" in p]
    vecs, meta, _docs = build_map.load_points()
    try:
        cidx = build_map._content_alignment(data["points"], meta, build_map.CONTENT_CATS)
        sub = np.asarray(vecs)[cidx]
        keep = np.ones(len(cpts), dtype=bool)
    except SystemExit as exc:
        # the store grows between rebuilds; url-matching is fine for a
        # measurement (E29 precedent), never for shipping positions
        print(f"index alignment failed ({exc}); url-matching instead")
        by_url = {m["url"]: v for m, v in zip(meta, vecs) if m.get("url")}
        rows = [by_url.get(p.get("u")) for p in cpts]
        keep = np.array([r is not None for r in rows])
        if keep.mean() < 0.95:
            raise SystemExit("url match rate under 95% — rebuild the map first") from exc
        print(f"url-matched {int(keep.sum())}/{len(cpts)}")
        sub = np.asarray([r for r in rows if r is not None])
        cpts = [p for p, k in zip(cpts, keep) if k]
    return {
        "c3": np.asarray([p["c3"] for p in cpts]),
        "themes": np.asarray([p.get("th", -1) for p in cpts]),
        "dates": [p.get("d") or None for p in cpts],
        "labels": [g["label"] for g in data["content"]["groups"]],
        "vecs": sub,
        "params": data["content"]["params"],
    }


def refit_c3(vecs: np.ndarray, params: dict) -> np.ndarray:
    import umap  # type: ignore[import-not-found]

    nn = int(min(params.get("n_neighbors", 30), max(5, len(vecs) - 2)))
    return umap.UMAP(  # type: ignore[attr-defined]
        n_neighbors=nn,
        min_dist=float(params.get("min_dist", 0.05)),
        n_components=3,
        metric="cosine",
        random_state=42,
    ).fit_transform(vecs)


def trust(vecs: np.ndarray, pos: np.ndarray) -> float:
    from sklearn.manifold import trustworthiness

    nn = min(15, max(1, len(pos) // 2 - 1))
    return float(trustworthiness(vecs, pos, n_neighbors=nn, metric="cosine"))


def geography(pos: np.ndarray) -> dict:
    """E30 machinery at this planet's own calibration: the lattice pole at
    its n sets the coast radius, so small worlds get chunky coasts."""
    probes = fibonacci(e30.N_PROBES)
    r_deg = e30.ocean_radius(fibonacci(len(pos)))
    ll, tt, xyz = e30.grid()
    dist, _theme = e30.fields(xyz, pos, np.zeros(len(pos), dtype=int))
    land = dist < r_deg
    comp = e30.continents(land)
    return {
        "coast_deg": r_deg,
        "land_frac": float((np.cos(tt) * land).sum() / np.cos(tt).sum()),
        "n_continents": int(comp.max()),
        "ocean_frac": float(
            (np.degrees(np.arccos(np.clip(probes @ pos.T, -1, 1).max(axis=1))) > r_deg).mean()
        ),
        "dist": dist,
        "ll": ll,
        "tt": tt,
    }


def build_planets(d: dict) -> list[dict]:
    ids, counts = np.unique(d["themes"][d["themes"] >= 0], return_counts=True)
    top = ids[np.argsort(counts)[::-1][:TOP_N]]
    today = datetime.date.today()
    out = []
    for t in top:
        m = d["themes"] == t
        vecs = d["vecs"][m]
        n = int(m.sum())
        dates = [x for x, keep in zip(d["dates"], m) if keep and x]
        recent = sum(
            1 for x in dates if (today - datetime.date.fromisoformat(x)).days <= ACTIVE_DAYS
        )
        activity = recent / len(dates) if dates else 0.0
        vn = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
        cent = vn.mean(axis=0)
        cent /= np.linalg.norm(cent)
        cos = vn @ cent
        cls, cls_label, hue = classify(activity)
        planet = {
            "theme": int(t),
            "label": d["labels"][t],
            "n": n,
            "activity": activity,
            "date_coverage": len(dates) / n,
            "cohesion": float(cos.mean()),
            "cloudiness": float(cos.std()),
            "cls": cls,
            "cls_label": cls_label,
            "hue": hue,
            "radius": float(n ** (1 / 3)),
        }
        print(f"planet {d['labels'][t]!r}: n={n} activity={activity:.2f} class {cls}")
        for arm, pos3 in (("slice", d["c3"][m]), ("refit", refit_c3(vecs, d["params"]))):
            pos = spread(radial(np.asarray(pos3, dtype=float)))
            geo = geography(pos)
            planet[arm] = {
                "trust": trust(vecs, pos),
                "occluded": float(
                    (
                        np.degrees(
                            np.arccos(
                                np.clip(pos @ pos.T - 2 * np.eye(len(pos)), -1, 1).max(axis=1)
                            )
                        )
                        < OCCL_DEG
                    ).mean()
                ),
                "coast_deg": geo["coast_deg"],
                "land_frac": geo["land_frac"],
                "n_continents": geo["n_continents"],
                "ocean_frac": geo["ocean_frac"],
                "pos": np.round(pos, 4).tolist(),
            }
            print(
                f"  {arm}: trust={planet[arm]['trust']:.4f} occl={planet[arm]['occluded']:.1%} "
                f"land={planet[arm]['land_frac']:.0%} continents={planet[arm]['n_continents']}"
            )
        out.append(planet)
    return out


# --- figures ---------------------------------------------------------------


def fig_refit_vs_slice(planets: list[dict], out: Path, number: int = 1) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, top = figure(
        15.2,
        7.6,
        number,
        "E31 · theme planets",
        "Refit or slice: does each theme deserve its own survey?",
        meta=(
            f"top {len(planets)} themes by members · slice = subset of the superplanet c3 · "
            f"refit = UMAP-3D on the subset alone (seed 42) · both arms spread to visibility · "
            f"commit {sha()}"
        ),
    )
    gs = fig.add_gridspec(1, 2, left=0.06, right=0.96, top=top, bottom=0.09, wspace=0.28)
    ax = fig.add_subplot(gs[0, 0])
    style_axes(ax)
    for p in planets:
        a, b = p["slice"]["trust"], p["refit"]["trust"]
        color = p["hue"]
        ax.plot([0, 1], [a, b], color=color, lw=1.6, alpha=0.9)
        ax.scatter([0, 1], [a, b], color=color, s=40, zorder=5)
        ax.annotate(
            p["label"], (1.03, b), color=color, fontsize=8.5, va="center", annotation_clip=False
        )
    ax.set_xticks([0, 1], ["slice", "refit"])
    ax.set_xlim(-0.15, 1.9)
    ax.set_ylabel("trustworthiness (subset vectors)")
    panel_title(ax, "fidelity per planet, same notes, two surveys")
    ax2 = fig.add_subplot(gs[0, 1])
    style_axes(ax2)
    for p in planets:
        ax2.scatter(
            p["slice"]["land_frac"], p["refit"]["land_frac"], color=p["hue"], s=44, zorder=5
        )
    lim = [0, max(max(p["slice"]["land_frac"], p["refit"]["land_frac"]) for p in planets) * 1.2]
    ax2.plot(lim, lim, color=DIM, lw=1.0)
    ax2.set_xlabel("land fraction, slice")
    ax2.set_ylabel("land fraction, refit")
    panel_title(ax2, "geography: does the survey change the amount of land?")
    best = max(planets, key=lambda p: p["refit"]["trust"] - p["slice"]["trust"])
    dmean = float(np.mean([p["refit"]["trust"] - p["slice"]["trust"] for p in planets]))
    verdict(
        fig,
        f"mean trust delta refit-slice {dmean:+.4f} · largest {best['refit']['trust'] - best['slice']['trust']:+.4f}",
    )
    frame_panels(fig)
    fig.savefig(out, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print(f"wrote {out}")


def fig_gallery(planets: list[dict], arm: str, out: Path, number: int = 2) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt

    fig, top = figure(
        16.4,
        5.3,
        number,
        "E31 · theme planets",
        "The gallery: five worlds, classed by activity, colored by their physics",
        meta=(
            "class from activity share of last 90 days (Sudarsky I-V translation) · "
            "saturation carries cohesion (normalized across the population) · "
            f"panel width carries n^(1/3) · arm: {arm} · commit {sha()}"
        ),
    )
    # the size channel is rendered, not just annotated: cell width ∝ radius
    gs = fig.add_gridspec(
        1,
        len(planets),
        left=0.03,
        right=0.97,
        top=top,
        bottom=0.10,
        wspace=0.08,
        width_ratios=[p["radius"] for p in planets],
    )
    cohs = [p["cohesion"] for p in planets]
    lo, hi = min(cohs), max(cohs)
    for i, p in enumerate(planets):
        pos = np.asarray(p[arm]["pos"])
        r_deg = p[arm]["coast_deg"]
        ll, tt, xyz = e30.grid()
        dist, _ = e30.fields(xyz, pos, np.zeros(len(pos), dtype=int))
        ax = e30._moll(fig, gs[0, i])
        base = np.asarray(mcolors.to_rgb(p["hue"]))
        # cohesion -> saturation, spread over the population so the channel
        # separates planets even when the class does not (Batalha's caution)
        sat = 0.3 + 0.7 * ((p["cohesion"] - lo) / (hi - lo) if hi > lo else 1.0)
        hue = base * sat + np.asarray(mcolors.to_rgb(DIM)) * (1 - sat)
        ramp = mcolors.LinearSegmentedColormap.from_list(
            f"cls{i}", [mcolors.to_rgb(PANEL), tuple(hue * 0.35), tuple(np.clip(hue, 0, 1))]
        )
        near = punch(np.clip(1.0 - dist / (2.5 * r_deg), 0, 1))
        ax.pcolormesh(ll, tt, near, cmap=ramp, vmin=0, vmax=1, shading="auto", rasterized=True)
        ax.contour(ll, tt, dist, levels=[r_deg], colors=[TEXT], linewidths=0.7, alpha=0.8)
        panel_title(
            ax,
            f"{p['label']}\n{p['cls']} · n={p['n']} · active {p['activity']:.0%}",
            width=30,
        )
    verdict(fig, " · ".join(f"{p['cls']}: {p['label'].split(' &')[0]}" for p in planets))
    frame_panels(fig)
    fig.savefig(out, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print(f"wrote {out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["planets", "figures", "assets"])
    ap.add_argument("--out", default=os.environ.get("CLAUDE_JOB_DIR", "/tmp") + "/tmp")
    args = ap.parse_args()
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    if args.stage == "planets" or not CACHE.exists():
        planets = build_planets(load())
        CACHE.write_text(json.dumps(planets))
        print(f"cached {len(planets)} planets -> {CACHE}")
        if args.stage == "planets":
            return
    planets = json.loads(CACHE.read_text())

    if args.stage == "figures":
        fig_refit_vs_slice(planets, outdir / "e31-cp1-refit-vs-slice.png")
        fig_gallery(planets, "refit", outdir / "e31-cp2-gallery.png")
        return

    if args.stage == "assets":
        ASSETS.mkdir(parents=True, exist_ok=True)
        fig_refit_vs_slice(planets, ASSETS / "01-refit-vs-slice.png", number=1)
        fig_gallery(planets, "refit", ASSETS / "02-the-gallery.png", number=2)
        (ASSETS / "planets.json").write_text(json.dumps(planets, indent=1))
        print(f"wrote {ASSETS / 'planets.json'}")


if __name__ == "__main__":
    main()
