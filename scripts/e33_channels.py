"""E33 — channels earn their place: moons, rings, spin.

Toward #78, via #178, decorating E32's sky (docs/assets/32-galaxy). Every
channel passes its own null before it renders: moons gate on triplet
agreement between dendrograms across subsamples vs a spectrum-matched
unimodal cloud (anisotropy preserved, sub-structure destroyed); rings gate
cross-theme nearest-neighbor share against theme-label permutations; spin
gates median member age two-sided against date permutations, and pays a
pre-registered redundancy price against the class channel's activity.

Moons that pass ship an exemplar (medoid note url/title/thumb) so the build
can render the moon as imagery — the owner's contract, registered in #178.

    uv run --with matplotlib,scipy,scikit-learn,umap-learn python \
        scripts/e33_channels.py channels
    ...                         figures
    ...                         assets
"""

from __future__ import annotations

import argparse
import datetime
import itertools
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e30_coastlines as e30
import e31_theme_planets as e31
import e32_galaxy as e32
from plot_assets import (
    BG,
    DIM,
    DPI,
    GOLD,
    MUTED,
    TEXT,
    figure,
    frame_panels,
    panel_title,
    style_axes,
    verdict,
)

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from ytk.store import EMBEDDING_EPOCH

MAP = Path(os.path.expanduser("~/.ytk/map.json"))
CACHE = Path(os.path.expanduser("~/.ytk/e33-channels.json"))
ASSETS = REPO / "docs" / "assets" / "33-channels"
GALAXY = REPO / "docs" / "assets" / "32-galaxy" / "galaxy.json"

N_BOOT = 25  # subsample dendrograms per planet (20+ mandatory)
N_NULL_MOON = 50  # unimodal clouds per planet
N_TRIP = 4000  # triplets scored per subsample
N_PERM = 1000  # label/date permutations for rings and spin
KNN = 10
GATE_Q = 0.95
SPIN_REDUNDANT = 0.8  # |rho| vs activity beyond which spin repeats the hue channel


def load_members() -> dict:
    """E31's load pattern, but keeping per-note payload (url/title/thumb/date)
    for the moon exemplars. Channels are measurements and the payload is
    note-level, so the url-fallback is acceptable here; positions stay E32's."""
    import build_map

    data = json.loads(MAP.read_text())
    cpts = [p for p in data["points"] if "c3" in p]
    vecs, meta, _docs = build_map.load_points()
    try:
        cidx = build_map._content_alignment(data["points"], meta, build_map.CONTENT_CATS)
        sub = np.asarray(vecs)[cidx]
    except SystemExit as exc:
        print(f"index alignment failed ({exc}); url-matching instead")
        by_url = {m["url"]: v for m, v in zip(meta, vecs) if m.get("url")}
        rows = [by_url.get(p.get("u")) for p in cpts]
        keep = np.array([r is not None for r in rows])
        if keep.mean() < 0.95:
            raise SystemExit("url match rate under 95% — rebuild the map first") from exc
        print(f"url-matched {int(keep.sum())}/{len(cpts)}")
        sub = np.asarray([r for r in rows if r is not None])
        cpts = [p for p, k in zip(cpts, keep) if k]
    sub = np.asarray(sub, dtype=float)
    return {
        "vecs": sub / np.linalg.norm(sub, axis=1, keepdims=True),
        "themes": np.asarray([p.get("th", -1) for p in cpts]),
        "dates": [p.get("d") or None for p in cpts],
        "urls": [p.get("u", "") for p in cpts],
        "titles": [p.get("t", "") for p in cpts],
        "thumbs": [p.get("thumb", "") for p in cpts],
        "labels": [g["label"] for g in data["content"]["groups"]],
    }


# --- channel 1: moons ------------------------------------------------------


def _coph(vn: np.ndarray) -> np.ndarray:
    from scipy.cluster.hierarchy import cophenet, linkage
    from scipy.spatial.distance import pdist, squareform

    d = pdist(vn, metric="cosine")
    return squareform(cophenet(linkage(d, method="average"), d)[1])


def _triplets(m: int, rng: np.random.Generator) -> np.ndarray:
    trips = np.array(list(itertools.combinations(range(m), 3)))
    if len(trips) > N_TRIP:
        trips = trips[rng.choice(len(trips), N_TRIP, replace=False)]
    return trips


def _outliers(c: np.ndarray, trips: np.ndarray) -> np.ndarray:
    """Odd-one-out per triplet: the point outside the pair that merges first
    (smallest cophenetic distance)."""
    d_jk = c[trips[:, 1], trips[:, 2]]
    d_ik = c[trips[:, 0], trips[:, 2]]
    d_ij = c[trips[:, 0], trips[:, 1]]
    return np.argmin(np.stack([d_jk, d_ik, d_ij]), axis=0)


def moon_stability(vn: np.ndarray, seed: int) -> float:
    """Mean triplet agreement between the full dendrogram and 80% subsample
    dendrograms — hierarchy geometry, never a flat cut (E-series lesson)."""
    rng = np.random.default_rng(seed)
    n = len(vn)
    cfull = _coph(vn)
    scores = []
    for _ in range(N_BOOT):
        idx = rng.choice(n, size=max(6, int(0.8 * n)), replace=False)
        trips = _triplets(len(idx), rng)
        o_full = _outliers(cfull[np.ix_(idx, idx)], trips)
        o_sub = _outliers(_coph(vn[idx]), trips)
        scores.append(float((o_full == o_sub).mean()))
    return float(np.mean(scores))


def null_cloud(vn: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Unimodal cloud matched to the member set's mean and full covariance
    spectrum (sampled in its own eigenbasis): the cone and the anisotropy
    survive, any sub-structure does not."""
    mu = vn.mean(axis=0)
    _u, s, vt = np.linalg.svd(vn - mu, full_matrices=False)
    z = rng.normal(size=(len(vn), len(s))) * (s / np.sqrt(max(len(vn) - 1, 1)))
    y = mu + z @ vt
    return y / np.linalg.norm(y, axis=1, keepdims=True)


def moon_cut(vn: np.ndarray, seed: int) -> list[dict]:
    """Descriptive flat cut for a gated planet: k in 2..4 by co-assignment
    stability across the same subsampling; moons need >= 3 members."""
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import pdist

    rng = np.random.default_rng(seed)
    n = len(vn)
    z_full = linkage(pdist(vn, metric="cosine"), method="average")
    best_k, best_s = 2, -1.0
    for k in (2, 3, 4):
        lab_full = fcluster(z_full, k, criterion="maxclust")
        agree = []
        for _ in range(N_BOOT):
            idx = rng.choice(n, size=max(6, int(0.8 * n)), replace=False)
            lab_sub = fcluster(
                linkage(pdist(vn[idx], metric="cosine"), method="average"),
                k,
                criterion="maxclust",
            )
            a, b = lab_full[idx], lab_sub
            co_a = a[:, None] == a[None, :]
            co_b = b[:, None] == b[None, :]
            iu = np.triu_indices(len(idx), 1)
            agree.append(float((co_a[iu] == co_b[iu]).mean()))
        if np.mean(agree) > best_s:
            best_k, best_s = k, float(np.mean(agree))
    labels = fcluster(z_full, best_k, criterion="maxclust")
    sizes = {int(c): int((labels == c).sum()) for c in np.unique(labels)}
    core = max(sizes, key=lambda c: sizes[c])
    # the largest cluster is the planet's core, not a moon — a moon is a
    # minority sub-cluster with enough members to be a real object
    return sizes[core], [
        {"members": np.flatnonzero(labels == c).tolist()}
        for c in np.unique(labels)
        if c != core and (labels == c).sum() >= 3
    ]


# --- channel 2: rings ------------------------------------------------------


def ring_stats(vn: np.ndarray, themes: np.ndarray, ids: list[int], seed: int) -> dict:
    """A ring is a partner pair whose NN edge count exceeds the label
    permutation beyond the planet's own max-z null (99th) — multiplicity over
    partners handled empirically. The registered share-gate (#178) is kept and
    reported: it is inverted by construction (permutation destroys ALL
    coherence, so the null share sits near 1) and its 0/18 confirms theme
    coherence, it cannot detect rings."""
    rng = np.random.default_rng(seed)
    mask = themes >= 0
    v = vn[mask]
    th = themes[mask]
    sims = v @ v.T
    np.fill_diagonal(sims, -np.inf)
    nn = np.argsort(-sims, axis=1)[:, :KNN]
    nn_th = th[nn]
    cross = nn_th != th[:, None]

    obs = {t: float(cross[th == t].mean()) for t in ids}
    pair = {t: {int(u): int((nn_th[th == t] == u).sum()) for u in ids if u != t} for t in ids}
    perm_share = {t: [] for t in ids}
    perm_pair = {t: {int(u): [] for u in ids if u != t} for t in ids}
    for _ in range(N_PERM):
        p = th[rng.permutation(len(th))]
        p_nn = p[nn]
        for t in ids:
            m = p == t
            perm_share[t].append(float((p_nn[m] != t).mean()))
            row = p_nn[m]
            for u in ids:
                if u != t:
                    perm_pair[t][u].append(int((row == u).sum()))
    out = {}
    for t in ids:
        others = [u for u in ids if u != t]
        counts = np.asarray([perm_pair[t][u] for u in others], dtype=float)  # (17, N_PERM)
        mean = counts.mean(axis=1)
        sd = np.maximum(counts.std(axis=1), 1.0)
        z_obs = (np.asarray([pair[t][u] for u in others]) - mean) / sd
        z_perm_max = ((counts - mean[:, None]) / sd[:, None]).max(axis=0)
        bar = float(np.quantile(z_perm_max, 0.99))
        partners = sorted(
            (
                {"theme": int(u), "count": pair[t][u], "z": float(z)}
                for u, z in zip(others, z_obs)
                if z > bar
            ),
            key=lambda d: -d["z"],
        )
        band = np.asarray(perm_share[t])
        out[t] = {
            "max_z": float(z_obs.max()),
            "z_bar": bar,
            "z_null_lo": float(np.quantile(z_perm_max, 0.05)),
            "earned": bool(z_obs.max() > bar),
            "partners": partners[:3],
            "share": obs[t],
            "share_gate": {
                "share": obs[t],
                "null_hi": float(np.quantile(band, GATE_Q)),
                "earned": bool(obs[t] > np.quantile(band, GATE_Q)),
                "note": "registered gate, inverted by construction — reported, not used",
            },
        }
    return out


# --- channel 3: spin -------------------------------------------------------


def spin_stats(themes: np.ndarray, dates: list, ids: list[int], seed: int) -> dict:
    """Median member age per planet vs date permutations preserving each
    planet's dated count — the band coverage bias alone produces. Two-sided:
    fast and dormant both earn."""
    rng = np.random.default_rng(seed)
    today = datetime.date.today()
    ages = np.array(
        [(today - datetime.date.fromisoformat(d)).days if d else -1 for d in dates],
        dtype=float,
    )
    dated = ages >= 0
    out = {}
    pool = ages[dated & (themes >= 0)]
    pool_themes = themes[dated & (themes >= 0)]
    for t in ids:
        m = pool_themes == t
        k = int(m.sum())
        obs = float(np.median(pool[m])) if k else float("nan")
        meds = [
            float(np.median(pool[rng.choice(len(pool), k, replace=False)])) for _ in range(N_PERM)
        ]
        lo, hi = float(np.quantile(meds, 0.025)), float(np.quantile(meds, 0.975))
        out[t] = {
            "median_age_days": obs,
            "n_dated": k,
            "null_lo": lo,
            "null_hi": hi,
            "earned": bool(k and (obs < lo or obs > hi)),
            "side": "fast" if k and obs < lo else ("dormant" if k and obs > hi else None),
        }
    return out


# --- build -----------------------------------------------------------------


def build() -> dict:
    d = load_members()
    galaxy = json.loads(GALAXY.read_text())
    ids = [p["theme"] for p in galaxy["planets"]]
    by_theme = {p["theme"]: p for p in galaxy["planets"]}
    # channels decorate E32's sky: theme identity must match its stamped map
    for t in ids:
        if d["labels"][t] != by_theme[t]["label"]:
            raise SystemExit(
                f"theme {t} label drifted ({d['labels'][t]!r} vs {by_theme[t]['label']!r}) "
                "— galaxy.json and the map are out of step; re-run E32 first"
            )

    moons = {}
    for t in ids:
        m = np.flatnonzero(d["themes"] == t)
        vn = d["vecs"][m]
        real = moon_stability(vn, seed=33 + t)
        rng = np.random.default_rng(133 + t)
        null = [
            moon_stability(null_cloud(vn, rng), seed=233 + t * 100 + i) for i in range(N_NULL_MOON)
        ]
        hi = float(np.quantile(null, GATE_Q))
        earned = bool(real > hi)
        entry = {
            "stability": real,
            "null_hi": hi,
            "null_mean": float(np.mean(null)),
            "earned": earned,
            "core_size": None,
            "moons": [],
        }
        if earned:
            core_size, cut = moon_cut(vn, seed=333 + t)
            entry["core_size"] = core_size
            for moon in cut:
                mem = m[moon["members"]]
                sub = d["vecs"][mem]
                medoid = int(mem[np.argmax(sub @ sub.mean(axis=0))])
                entry["moons"].append(
                    {
                        "size": len(mem),
                        "exemplar": {
                            "url": d["urls"][medoid],
                            "title": d["titles"][medoid],
                            "thumb": d["thumbs"][medoid],
                        },
                    }
                )
        moons[t] = entry
        state = "no"
        if earned:
            state = (
                f"GATE, {len(entry['moons'])} moon(s), core {entry['core_size']}"
                if entry["moons"]
                else f"GATE only, core {entry['core_size']} (no discrete moon)"
            )
        print(f"moons {by_theme[t]['label']!r}: stability {real:.3f} vs null {hi:.3f} -> {state}")

    rings = ring_stats(d["vecs"], d["themes"], ids, seed=433)
    for t in ids:
        r = rings[t]
        print(
            f"rings {by_theme[t]['label']!r}: max z {r['max_z']:.1f} vs bar {r['z_bar']:.1f} "
            f"-> {'EARNED ' + str([d['labels'][p['theme']] for p in r['partners']]) if r['earned'] else 'no'}"
        )

    spin = spin_stats(d["themes"], d["dates"], ids, seed=533)
    from scipy.stats import spearmanr

    acts = [by_theme[t]["activity"] for t in ids]
    meds = [spin[t]["median_age_days"] for t in ids]
    rho = float(spearmanr(acts, meds).statistic)
    redundant = bool(abs(rho) >= SPIN_REDUNDANT)
    for t in ids:
        s = spin[t]
        print(
            f"spin {by_theme[t]['label']!r}: median {s['median_age_days']:.0f}d "
            f"band [{s['null_lo']:.0f}, {s['null_hi']:.0f}] -> "
            f"{('EARNED ' + str(s['side'])) if s['earned'] else 'no'}"
        )
    print(
        f"spin redundancy vs activity: rho {rho:.3f} -> {'REDUNDANT' if redundant else 'independent'}"
    )

    return {
        "epoch": EMBEDDING_EPOCH,
        "commit": e31.sha(),
        "galaxy_commit": galaxy["commit"],
        "planets": [
            {
                "theme": t,
                "label": by_theme[t]["label"],
                "n": by_theme[t]["n"],
                "moons": moons[t],
                "rings": rings[t],
                "spin": spin[t],
            }
            for t in ids
        ],
        "spin_redundancy_rho": rho,
        "spin_redundant": redundant,
    }


# --- figures ---------------------------------------------------------------


def _gate_panel(ax, rows, obs_key, lo_key, hi_key, ylabel):
    """Planets on x (sorted by n desc), observed dot vs DIM null band."""
    for i, r in enumerate(rows):
        lo, hi = r[lo_key], r[hi_key]
        ax.plot([i, i], [lo, hi], color=DIM, lw=5.0, solid_capstyle="butt")
        ax.scatter(
            [i],
            [r[obs_key]],
            color=GOLD if r["earned"] else MUTED,
            s=34 if r["earned"] else 18,
            zorder=5,
        )
    ax.set_xticks(range(len(rows)))
    ax.set_xticklabels(
        [r["label"].split(" &")[0][:14] for r in rows], rotation=60, ha="right", fontsize=6.5
    )
    ax.set_ylabel(ylabel)
    style_axes(ax)


def fig_gates(r: dict, out: Path, number: int = 1) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = sorted(r["planets"], key=lambda p: -p["n"])
    n_gate = sum(1 for p in rows if p["moons"]["earned"])
    n_moon = sum(1 for p in rows if p["moons"]["moons"])
    n_ring = sum(1 for p in rows if p["rings"]["earned"])
    n_spin = sum(1 for p in rows if p["spin"]["earned"])
    fig, top = figure(
        16.4,
        8.2,
        number,
        "E33 · channels",
        "The gates: each channel against its own null, planet by planet",
        meta=(
            f"{len(rows)} planets · moons: triplet stability vs {N_NULL_MOON} spectrum-matched "
            f"unimodal clouds · rings: partner NN excess (k={KNN}) vs per-planet max-z over "
            f"{N_PERM} label permutations · spin: median age vs {N_PERM} date permutations, "
            f"two-sided · DIM band = null · commit {r['commit']}"
        ),
    )
    gs = fig.add_gridspec(1, 3, left=0.05, right=0.985, top=top, bottom=0.20, wspace=0.24)

    ax = fig.add_subplot(gs[0, 0])
    _gate_panel(
        ax,
        [{**p["moons"], "label": p["label"]} for p in rows],
        "stability",
        "null_mean",
        "null_hi",
        "triplet agreement (full vs subsample)",
    )
    panel_title(
        ax, f"moons — {n_gate}/{len(rows)} pass the gate, {n_moon} bear a discrete moon", width=44
    )

    ax = fig.add_subplot(gs[0, 1])
    _gate_panel(
        ax,
        [{**p["rings"], "label": p["label"]} for p in rows],
        "max_z",
        "z_null_lo",
        "z_bar",
        "max partner excess (z) over label permutation",
    )
    panel_title(ax, f"rings — {n_ring}/{len(rows)} earned; share-gate 0/18 (inverted)", width=44)

    ax = fig.add_subplot(gs[0, 2])
    _gate_panel(
        ax,
        [{**p["spin"], "label": p["label"]} for p in rows],
        "median_age_days",
        "null_lo",
        "null_hi",
        "median member age (days)",
    )
    panel_title(
        ax,
        f"spin — {n_spin}/{len(rows)} earned; vs activity rho {r['spin_redundancy_rho']:.2f}",
        width=44,
    )
    verdict(
        fig,
        f"moons {n_moon} (geometry {n_gate}) · rings {n_ring} · spin {n_spin}"
        + (" (redundant with hue)" if r["spin_redundant"] else ""),
    )
    frame_panels(fig)
    fig.savefig(out, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print(f"wrote {out}")


def fig_decorated(r: dict, out: Path, number: int = 2) -> None:
    """E32's sky with only the earned channels drawn on top."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import patheffects as pe

    galaxy = json.loads(GALAXY.read_text())
    planets = galaxy["planets"]
    by_theme = {p["theme"]: p for p in r["planets"]}
    pos = np.asarray([p["pos"] for p in planets])
    radii = np.asarray([p["radius_deg"] for p in planets])
    e31_style = [{"cohesion": p["cohesion"], "hue": p["hue"]} for p in planets]
    colors = e32.planet_colors(e31_style)
    ll, tt, xyz = e30.grid()
    ang = np.degrees(np.arccos(np.clip(xyz.reshape(-1, 3) @ pos.T, -1, 1))).reshape(
        *xyz.shape[:2], -1
    )
    n_moon = sum(1 for p in r["planets"] if p["moons"]["moons"])
    n_ring = sum(1 for p in r["planets"] if p["rings"]["earned"])
    n_spin = sum(1 for p in r["planets"] if p["spin"]["earned"])
    fig, top = figure(
        16.0,
        8.8,
        number,
        "E33 · channels",
        "The decorated sky: only what passed its null renders",
        meta=(
            f"{len(planets)} planets · moons {n_moon} (orbit dots, exemplar-backed) · "
            f"rings {n_ring} (outline at 1.35r) · spin {n_spin} (tick pair) · "
            f"base sky = E32 arm A at K={galaxy['k_deg_per_cbrt_n']:.2f}° · commit {r['commit']}"
        ),
    )
    gs = fig.add_gridspec(1, 1, left=0.05, right=0.95, top=top, bottom=0.06)
    ax = e30._moll(fig, gs[0, 0])
    paint = np.zeros((*ang.shape[:2], 3))
    for j in np.argsort([p["n"] for p in planets]):
        a_j = ang[:, :, j]
        w = np.clip((radii[j] - a_j) / 0.5, 0, 1)[:, :, None]
        shade = e32.punch(np.clip(1.0 - a_j / radii[j], 0, 1))[:, :, None]
        paint = paint * (1 - w) + colors[j] * (0.35 + 0.65 * shade) * w
    ax.pcolormesh(ll, tt, paint, shading="auto", rasterized=True)

    def ring_points(center: np.ndarray, r_deg: float, n_pts: int = 120) -> tuple:
        ref = np.array([0.0, 0.0, 1.0]) if abs(center[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
        e1 = np.cross(center, ref)
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(center, e1)
        th = np.linspace(0, 2 * np.pi, n_pts)
        rr = np.radians(r_deg)
        pts = np.cos(rr) * center[None, :] + np.sin(rr) * (
            np.cos(th)[:, None] * e1 + np.sin(th)[:, None] * e2
        )
        lon = np.arctan2(pts[:, 1], pts[:, 0])
        lat = np.arcsin(np.clip(pts[:, 2], -1, 1))
        return lon, lat

    def draw_wrapped(lon, lat, **kw):
        brk = np.flatnonzero(np.abs(np.diff(lon)) > np.pi)
        start = 0
        for b in list(brk) + [len(lon) - 1]:
            ax.plot(lon[start : b + 1], lat[start : b + 1], **kw)
            start = b + 1

    for j, p in enumerate(planets):
        ch = by_theme[p["theme"]]
        c = pos[j] / np.linalg.norm(pos[j])
        if ch["rings"]["earned"]:
            lon, lat = ring_points(c, radii[j] * 1.35)
            draw_wrapped(lon, lat, color=TEXT, lw=0.9, alpha=0.85)
        if ch["moons"]["earned"] and ch["moons"]["moons"]:
            k = len(ch["moons"]["moons"])
            lon, lat = ring_points(c, radii[j] * 1.6, n_pts=max(k, 1) + 1)
            sizes = [m["size"] for m in ch["moons"]["moons"]]
            ax.scatter(
                lon[:k],
                lat[:k],
                s=[14 + 3.0 * s for s in sizes],
                color=colors[j],
                edgecolors=TEXT,
                linewidths=0.7,
                zorder=6,
            )
        if ch["spin"]["earned"]:
            lon0 = np.arctan2(c[1], c[0])
            lat0 = np.arcsin(np.clip(c[2], -1, 1))
            mark = "»" if ch["spin"]["side"] == "fast" else "«"
            ax.annotate(
                mark,
                (lon0, lat0),
                color=TEXT,
                fontsize=11,
                ha="center",
                va="center",
                path_effects=[pe.withStroke(linewidth=2.0, foreground=BG)],
            )
    big = np.argsort([-p["n"] for p in planets])[:6]
    for j in big:
        lon0 = np.arctan2(pos[j, 1], pos[j, 0])
        lat0 = np.arcsin(np.clip(pos[j, 2], -1, 1))
        ax.annotate(
            planets[j]["label"],
            (lon0, lat0 - np.radians(radii[j] * 1.9)),
            color=MUTED,
            fontsize=7,
            ha="center",
            va="top",
            path_effects=[pe.withStroke(linewidth=2.0, foreground=BG)],
        )
    panel_title(
        ax,
        "rings outline linked planets, moon dots carry exemplar imagery in the build, "
        "spin ticks mark planets outside their date-permutation band",
        width=110,
    )
    verdict(fig, f"earned: {n_moon} moons · {n_ring} rings · {n_spin} spin")
    frame_panels(fig)
    fig.savefig(out, dpi=DPI, facecolor=BG)
    plt.close(fig)
    print(f"wrote {out}")


# --- stages ----------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["channels", "figures", "assets"])
    ap.add_argument("--out", default=os.environ.get("CLAUDE_JOB_DIR", "/tmp") + "/tmp")
    args = ap.parse_args()
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    if args.stage == "channels" or not CACHE.exists():
        r = build()
        CACHE.write_text(json.dumps(r))
        print(f"cached -> {CACHE}")
        if args.stage == "channels":
            return
    r = json.loads(CACHE.read_text())
    r["planets"] = [
        {**p, "moons": p["moons"], "rings": p["rings"], "spin": p["spin"]} for p in r["planets"]
    ]

    if args.stage == "figures":
        fig_gates(r, outdir / "e33-cp1-gates.png")
        fig_decorated(r, outdir / "e33-cp2-decorated.png")
        return

    if args.stage == "assets":
        ASSETS.mkdir(parents=True, exist_ok=True)
        fig_gates(r, ASSETS / "01-the-gates.png", number=1)
        fig_decorated(r, ASSETS / "02-the-decorated-sky.png", number=2)
        (ASSETS / "channels.json").write_text(json.dumps(r, indent=1))
        print(f"wrote {ASSETS / 'channels.json'}")


if __name__ == "__main__":
    main()
