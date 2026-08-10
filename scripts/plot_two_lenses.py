"""Two lenses on one corpus — Qwen themes vs Gemma SAE-feature clusters.

Profiles the same 532 notes twice: once with the production Qwen partition
(today's interest snapshot), once by clustering the section-18 SAE
fingerprints (gemma-2-2b + gemma-scope, sum pooling) with the same choose_k
and seeded KMeans. Figures land in docs/assets/22-two-lenses/.

    uv run python scripts/plot_two_lenses.py

Neuronpedia auto-names are cached in feature-names.json next to the figures;
delete it to refetch. Auto-names are unprobed hypotheses (18.x caveat) and
are marked with * wherever rendered.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
SAE = REPO / "docs" / "assets" / "18-sae-fingerprints"
OUTDIR = REPO / "docs" / "assets" / "22-two-lenses"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from plot_assets import (
    BG,
    BLUE,
    CYAN,
    DIM,
    DPI,
    FRAME,
    GOLD,
    MARGIN,
    MUTED,
    PANEL,
    RED,
    TEXT,
    TICK_SIZE,
    figure,
    frame_panels,
    panel_title,
    saturated_magma,
    style_axes,
    verdict,
)

MAX_CHARS = 2000  # sae_batch.py:32 — sha window of the manifest


# --- pipeline ---------------------------------------------------------------
def align():
    """Match fingerprint rows to today's themed notes via note_texts() keying."""
    from ytk import store
    from ytk.config import load_config

    manifest = json.loads((SAE / "manifest.json").read_text())["notes"]
    F = np.load(SAE / "fingerprints.npz")["sum"].astype(np.float32)
    snapshot = json.loads(Path(os.path.expanduser("~/.ytk/interest/latest.json")).read_text())
    theme_of = {nid: th["label"] for th in snapshot["themes"] for nid in th["note_ids"]}

    cfg = load_config()
    key_map = {}
    vids = store._videos_collection().get(include=["documents", "metadatas"])
    for doc, meta in zip(vids["documents"], vids["metadatas"]):
        key = str(meta.get("title", meta.get("video_id", "")))[:80]
        key_map[key] = (str(meta.get("video_id", "")), doc or "", "youtube/web")
    mem = store._memories_collection().get(include=["documents", "metadatas"])
    for doc, meta, cid in zip(mem["documents"], mem["metadatas"], mem["ids"]):
        path = str(meta.get("source_path", ""))
        if path:
            src = "instagram" if "/instagram/" in path else "youtube/web"
            key_map[Path(path).stem[:80]] = (cid, doc or "", src)

    rows, ids, names, srcs, labels = [], [], [], [], []
    drift = 0
    for r in manifest:
        if r.get("skipped"):
            continue
        hit = key_map.get(r["name"])
        if hit is None:
            continue
        cid, text, src = hit
        if cid not in theme_of:
            continue
        sha = hashlib.sha256(text[:MAX_CHARS].encode()).hexdigest()[:12]
        drift += sha != r["sha256"]
        rows.append(r["i"])
        ids.append(cid)
        names.append(r["name"])
        srcs.append(src)
        labels.append(theme_of[cid])

    emb_of = {}
    for n in list(store.get_all_videos()) + list(
        store.get_content_memories(cfg.interest.content_sources)
    ):
        if n.get("embedding") is not None:
            emb_of[n["id"]] = np.asarray(n["embedding"], dtype=np.float32)
    Q = np.stack([emb_of[i] for i in ids])
    print(
        f"aligned {len(rows)} notes ({drift} content-drifted) of "
        f"{len(theme_of)} themed / {sum(not r.get('skipped') for r in manifest)} fingerprinted"
    )
    return F[rows], Q, ids, names, srcs, labels, snapshot


def gemma_space(F):
    """log-compress, remove the corpus voice (cone), cosine-normalize."""
    L = np.log1p(F)
    X = L - L.mean(0, keepdims=True)
    return X / np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-9), L


def feature_names(clusters):
    """Cached 18.x token-probed names + Neuronpedia auto-names for the gaps."""
    cached: dict[int, dict] = {}

    def harvest(obj):
        if isinstance(obj, dict):
            if "index" in obj and "name" in obj and obj["name"]:
                try:
                    cached.setdefault(int(obj["index"]), {"name": str(obj["name"]).strip()})
                except (TypeError, ValueError):
                    pass
            for v in obj.values():
                harvest(v)
        elif isinstance(obj, list):
            for v in obj:
                harvest(v)

    for f in ["tag-regions.json", "cone-features.json", "road-diffs.json"]:
        harvest(json.loads((SAE / f).read_text()))

    cache_path = OUTDIR / "feature-names.json"
    if cache_path.exists():
        for k, v in json.loads(cache_path.read_text()).items():
            cached.setdefault(int(k), {"name": v, "auto": True})
    else:
        import time
        import urllib.request

        want = sorted(
            {
                f["index"]
                for cl in clusters
                for f in cl["top_features"][:6]
                if int(f["index"]) not in cached
            }
        )
        fetched = {}
        for i in range(0, len(want), 40):
            body = json.dumps(
                [
                    {"modelId": "gemma-2-2b", "layer": "20-gemmascope-res-16k", "index": str(ix)}
                    for ix in want[i : i + 40]
                ]
            ).encode()
            req = urllib.request.Request(
                "https://www.neuronpedia.org/api/features",
                data=body,
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    for row in json.loads(r.read()):
                        expl = row.get("explanations") or []
                        if expl:
                            fetched[int(row["index"])] = str(expl[0].get("description", "")).strip()
            except Exception as e:  # keep going; names are decoration, not data
                print("neuronpedia chunk failed:", e)
            time.sleep(1.0)
        cache_path.write_text(json.dumps({str(k): v for k, v in fetched.items()}))
        for k, v in fetched.items():
            cached.setdefault(k, {"name": v, "auto": True})
    return cached


def build(recompute_scores=True):
    from sklearn.metrics import adjusted_rand_score

    from ytk.config import load_config
    from ytk.synthesis import choose_k, cluster_embeddings

    OUTDIR.mkdir(exist_ok=True)
    F, Q, ids, names, srcs, qwen_theme, snapshot = align()
    X, L = gemma_space(F)
    cfg = load_config()
    k = choose_k(len(ids), cfg.interest)

    glab = np.array(cluster_embeddings(X, k))
    qorder = sorted(set(qwen_theme))
    qlab = np.array([qorder.index(t) for t in qwen_theme])

    Qn = Q / np.linalg.norm(Q, axis=1, keepdims=True)
    relab = np.array(cluster_embeddings(Qn, k))
    ceiling = adjusted_rand_score(relab, qlab)
    cross = adjusted_rand_score(glab, qlab)
    rng = np.random.default_rng(0)
    null = float(np.mean([adjusted_rand_score(rng.permutation(glab), qlab) for _ in range(200)]))

    tri = rng.integers(0, len(ids), size=(20000, 3))
    tri = tri[(tri[:, 0] != tri[:, 1]) & (tri[:, 0] != tri[:, 2]) & (tri[:, 1] != tri[:, 2])]
    a, b, c = tri.T
    qp = np.einsum("ij,ij->i", Qn[a], Qn[b]) > np.einsum("ij,ij->i", Qn[a], Qn[c])
    gp = np.einsum("ij,ij->i", X[a], X[b]) > np.einsum("ij,ij->i", X[a], X[c])
    triplet = float((qp == gp).mean())

    sd = L.std(0) + 1e-9
    clusters = []
    for ci in range(k):
        inside = glab == ci
        z = (L[inside].mean(0) - L[~inside].mean(0)) / sd
        top = np.argsort(-z)[:8]
        clusters.append(
            {
                "cluster": ci,
                "n": int(inside.sum()),
                "top_features": [{"index": int(i), "z": round(float(z[i]), 2)} for i in top],
                "instagram": int(sum(srcs[j] == "instagram" for j in np.where(inside)[0])),
            }
        )
    fname = feature_names(clusters)
    for cl in clusters:
        for f in cl["top_features"]:
            rec = fname.get(f["index"])
            f["name"] = rec["name"] if rec else None
            f["auto"] = bool(rec and rec.get("auto"))

    def purity(labels):
        tot = 0
        for c_ in set(labels):
            idx = np.where(labels == c_)[0]
            tot += Counter(srcs[j] for j in idx).most_common(1)[0][1]
        return tot / len(labels)

    scores = []
    for f in sorted(Path(os.path.expanduser("~/.ytk/interest")).glob("snapshot-*.json")):
        d = json.loads(f.read_text())
        ps = d.get("profile_score") or {}
        if ps.get("score") is not None:
            scores.append(
                {
                    "ts": f.name[9:24],
                    "n": d["note_count"],
                    "score": ps["score"],
                    "delta": ps.get("delta"),
                }
            )

    return {
        "ids": ids,
        "names": names,
        "srcs": srcs,
        "qwen_theme": qwen_theme,
        "qorder": qorder,
        "qlab": qlab,
        "glab": glab,
        "k": k,
        "clusters": clusters,
        "stats": {
            "ari_null": null,
            "ari_cross": cross,
            "ari_ceiling": ceiling,
            "triplet": triplet,
            "purity_gemma": purity(glab),
            "purity_qwen": purity(qlab),
            "purity_base": Counter(srcs).most_common(1)[0][1] / len(srcs),
        },
        "scores": scores,
        "snapshot_at": snapshot["generated_at"][:10],
    }


# --- terse hand labels, derived from the top differential features ----------
# (full feature lists live in two-lenses.json; * marks auto-name provenance)
CLUSTER_LABELS = {
    9: "CLI & SSH vocabulary",
    12: "web markup & data fields",
    13: "boilerplate & tables",
    15: "economics & labor terms",
    4: "politics, law & contest",
    1: "product & craft attributes",
    7: "writing & demographics",
    10: "math notation",
    6: "medicine & geometry terms",
    11: "legal & corporate phrasing",
    5: "graphics code (Unity, shaders)",
    2: "code & JSON structures",
    8: "ML training terms",
    3: "citations & identity",
    0: "cell biology & ecology",
    14: "hardware & product specs",
}


def short(t, n=30):
    return t if len(t) <= n else t[: n - 1] + "…"


def hdr_fix(fig):
    """This render env falls back past CMU widths — nudge the kicker clear
    of the FIGURE NN stamp."""
    fig.texts[1].set_x(MARGIN + 0.092)


def dark_legend(ax, handles, loc="lower right"):
    leg = ax.legend(
        handles=handles,
        loc=loc,
        fontsize=9,
        facecolor=PANEL,
        edgecolor=FRAME,
        labelcolor=TEXT,
        framealpha=1.0,
        borderpad=0.7,
    )
    leg.set_zorder(6)
    return leg


# --- figures ----------------------------------------------------------------
def fig01(d):
    fig, top = figure(
        12.6,
        8.6,
        1,
        "two lenses, one corpus",
        "The same 532 notes, profiled by topic (Qwen) and by voice (Gemma SAE)",
        meta=f"snapshot {d['snapshot_at']} · fingerprints frozen at 568 notes · "
        f"identical choose_k + seeded KMeans · source purity {d['stats']['purity_qwen']:.2f} vs "
        f"{d['stats']['purity_gemma']:.2f} (baseline {d['stats']['purity_base']:.2f})",
    )
    hdr_fix(fig)
    axL = fig.add_axes([0.165, 0.10, 0.30, top - 0.17])
    axR = fig.add_axes([0.665, 0.10, 0.30, top - 0.17])

    qc = Counter(d["qwen_theme"])
    order = [t for t, _ in qc.most_common()]
    ig_by_theme = {
        t: sum(1 for j, th in enumerate(d["qwen_theme"]) if th == t and d["srcs"][j] == "instagram")
        for t in order
    }
    y = np.arange(len(order))[::-1]
    for yi, t in zip(y, order):
        n, ig = qc[t], ig_by_theme[t]
        axL.barh(yi, n - ig, left=0, height=0.62, color=GOLD, edgecolor="none")
        axL.barh(yi, ig, left=n - ig, height=0.62, color=DIM, edgecolor=GOLD, linewidth=0.4)
        axL.text(n + 1.5, yi, str(n), color=MUTED, fontsize=TICK_SIZE, va="center")
    axL.set_yticks(y, [short(t, 27) for t in order])
    panel_title(axL, "Qwen — what the notes are about")

    cls = sorted(d["clusters"], key=lambda c: -c["n"])
    y = np.arange(len(cls))[::-1]
    for yi, cl in zip(y, cls):
        n, ig = cl["n"], cl["instagram"]
        axR.barh(yi, n - ig, left=0, height=0.62, color=BLUE, edgecolor="none")
        axR.barh(yi, ig, left=n - ig, height=0.62, color=DIM, edgecolor=BLUE, linewidth=0.4)
        axR.text(n + 1.5, yi, str(n), color=MUTED, fontsize=TICK_SIZE, va="center")
    axR.set_yticks(y, [short(CLUSTER_LABELS[c["cluster"]], 27) for c in cls])
    panel_title(axR, "Gemma SAE — how the notes speak")

    from matplotlib.patches import Patch

    for ax, hue in ((axL, GOLD), (axR, BLUE)):
        style_axes(ax)
        ax.set_xlabel("notes", fontsize=TICK_SIZE)
        ax.set_xlim(0, 72)
        dark_legend(
            ax,
            [
                Patch(facecolor=hue, label="YouTube / web"),
                Patch(facecolor=DIM, edgecolor=hue, linewidth=0.6, label="Instagram"),
            ],
        )
    fig.text(
        MARGIN,
        0.032,
        "gemma labels condense top differential SAE features; auto-names are unprobed hypotheses (18.x)",
        color=MUTED,
        fontsize=8.5,
    )
    verdict(
        fig, "VERDICT: Qwen groups by topic, the SAE lens by voice — source purity 0.72 vs 0.95"
    )
    return fig, "01-two-profiles.png"


def fig02(d):
    fig, top = figure(
        12.6,
        8.2,
        2,
        "where the lenses disagree",
        "Each topic theme, redistributed across the voice clusters",
        meta="cells row-normalized within each theme · % marks the theme's largest destination · "
        "532 notes, k=17 themes x k=16 clusters",
    )
    qc = Counter(d["qwen_theme"])
    rows = [t for t, _ in qc.most_common()]
    cls = sorted(d["clusters"], key=lambda c: -c["n"])
    cols = [c["cluster"] for c in cls]

    M = np.zeros((len(rows), len(cols)))
    for j, th in enumerate(d["qwen_theme"]):
        M[rows.index(th), cols.index(int(d["glab"][j]))] += 1
    R = M / M.sum(1, keepdims=True)

    hdr_fix(fig)
    ax = fig.add_axes([MARGIN + 0.165, 0.235, 0.70, top - 0.30])
    im = ax.imshow(R, cmap=saturated_magma(), vmin=0, vmax=1, aspect="auto")
    ax.set_yticks(range(len(rows)), [short(t, 34) for t in rows])
    ax.set_xticks(
        range(len(cols)),
        [short(CLUSTER_LABELS[c], 24) for c in cols],
        rotation=38,
        ha="right",
    )
    style_axes(ax)
    ax.tick_params(length=0)
    for i in range(len(rows)):
        j = int(np.argmax(R[i]))
        v = R[i, j]
        ax.text(
            j,
            i,
            f"{v:.0%}",
            ha="center",
            va="center",
            fontsize=8,
            color=PANEL if v > 0.55 else TEXT,
        )
    cax = fig.add_axes([MARGIN + 0.905, 0.235, 0.014, top - 0.30])
    cb = fig.colorbar(im, cax=cax)
    cb.set_label("share of the theme's notes", color=MUTED, fontsize=9)
    cb.ax.tick_params(colors=MUTED, labelsize=8)
    cb.outline.set_edgecolor(FRAME)
    cax._is_colorbar = True

    fig.text(
        MARGIN,
        0.032,
        "a bright off-diagonal row = a topic fractured by register; a column collecting many rows = a "
        "voice shared across topics",
        color=MUTED,
        fontsize=8.5,
    )
    verdict(
        fig,
        "VERDICT: themes fracture by register — neither partition is recoverable from the other",
    )
    return fig, "02-mapping-matrix.png"


def fig03(d):
    stats = d["stats"]
    fig, top = figure(
        12.6,
        5.6,
        3,
        "how far apart are the views",
        "Partition agreement against its measured ceiling, and raw geometry agreement",
        meta="ceiling = Qwen re-clustered on the same 532 notes at k=16 vs its own production themes · "
        "same seeded KMeans everywhere",
    )
    hdr_fix(fig)
    from matplotlib.lines import Line2D

    axa = fig.add_axes([MARGIN + 0.13, 0.16, 0.36, top - 0.24])
    ladder = [
        ("shuffled null", stats["ari_null"], DIM),
        ("Gemma vs themes", stats["ari_cross"], BLUE),
        ("Qwen recluster\nvs themes (ceiling)", stats["ari_ceiling"], GOLD),
    ]
    yb = np.arange(len(ladder))
    axa.barh(yb, [v for _, v, _ in ladder], color=[c for *_, c in ladder], height=0.52)
    for yi, (_, v, _) in zip(yb, ladder):
        axa.text(v + 0.008, yi, f"{v:.2f}", color=TEXT, fontsize=9.5, va="center")
    axa.set_yticks(yb, [n for n, *_ in ladder])
    axa.set_xlim(0, 0.42)
    style_axes(axa)
    axa.set_xlabel("adjusted Rand index", fontsize=TICK_SIZE)
    panel_title(axa, "partition agreement — who groups with whom")

    axt = fig.add_axes([MARGIN + 0.60, 0.16, 0.335, top - 0.24])
    axt.barh([0], [stats["triplet"]], color=CYAN, height=0.42)
    axt.text(
        stats["triplet"] + 0.012,
        0,
        f"{stats['triplet']:.3f}",
        color=TEXT,
        fontsize=9.5,
        va="center",
    )
    axt.axvline(0.5, color=RED, linewidth=1.2, linestyle="--")
    axt.axvline(1.0, color=MUTED, linewidth=1.0, linestyle=":")
    axt.set_yticks([0], ["Qwen vs Gemma"])
    axt.set_xlim(0.4, 1.05)
    axt.set_ylim(-0.9, 0.9)
    style_axes(axt)
    axt.set_xlabel("triplet agreement", fontsize=TICK_SIZE)
    panel_title(axt, "geometry agreement — who is nearer to whom")
    dark_legend(
        axt,
        [
            Line2D([], [], color=RED, linewidth=1.2, linestyle="--", label="chance (0.5)"),
            Line2D(
                [], [], color=MUTED, linewidth=1.0, linestyle=":", label="identical spaces (1.0)"
            ),
        ],
        loc="upper right",
    )
    fig.text(
        MARGIN,
        0.045,
        "the views share well-above-chance structure, and the ceiling itself is low — this corpus is gradients, not "
        "clusters. Asset 25 later showed removing 25 RANDOM directions lands ARI in 0.31-0.48, so 0.335 is one draw "
        "from a wide band: read the gap as a direction, never as a percentage of ceiling",
        color=MUTED,
        fontsize=8.5,
    )
    verdict(
        fig,
        "VERDICT: real shared structure (triplet 0.644); the 0.335 ARI ceiling is soft — see asset 25",
    )
    return fig, "03-agreement.png"


def fig04(d):
    runs = d["scores"]
    fig, top = figure(
        12.6,
        6.8,
        4,
        "the referee's noise floor",
        "One frozen eval cohort, thirteen profile runs — the score that moves without the corpus",
        meta="all runs share fingerprint b2574824… (8 positives / 24 negatives) · "
        "labeling is the only varying stage · spread 0.220, same-corpus quartet 0.191",
    )
    hdr_fix(fig)
    ax = fig.add_axes([MARGIN + 0.045, 0.14, 0.925 - MARGIN, top - 0.20])
    xs = np.arange(len(runs))
    ys = [r["score"] for r in runs]
    lo, hi = min(ys), max(ys)
    ax.axhspan(lo, hi, color=DIM, alpha=0.35, zorder=0)
    quartet = [i for i, r in enumerate(runs) if r["n"] == 280]
    ax.plot(xs, ys, color=MUTED, linewidth=1.2, zorder=2)
    ax.scatter(xs, ys, s=42, color=GOLD, zorder=3)
    ax.scatter(
        [xs[i] for i in quartet],
        [ys[i] for i in quartet],
        s=68,
        facecolor=RED,
        edgecolor=TEXT,
        linewidth=0.6,
        zorder=4,
    )
    ax.scatter([xs[-1]], [ys[-1]], s=68, facecolor=CYAN, edgecolor=TEXT, linewidth=0.6, zorder=4)
    q0, q1 = min(quartet), max(quartet)
    ax.annotate(
        "same 280 notes, same afternoon — spread 0.191",
        xy=((q0 + q1) / 2, min(ys[i] for i in quartet) - 0.012),
        xytext=((q0 + q1) / 2 - 1.1, lo - 0.035),
        color=RED,
        fontsize=9.5,
        ha="center",
        arrowprops={"arrowstyle": "-", "color": RED, "linewidth": 0.8},
    )
    ax.annotate(
        f"today · 604 notes · “+{runs[-1]['delta']:.3f}”",
        xy=(xs[-1], ys[-1]),
        xytext=(xs[-1] - 1.6, ys[-1] + 0.055),
        color=CYAN,
        fontsize=9.5,
        arrowprops={"arrowstyle": "-", "color": CYAN, "linewidth": 0.8},
    )
    ax.set_xticks(
        xs,
        [f"{r['ts'][4:6]}/{r['ts'][6:8]}\nn={r['n']}" for r in runs],
        fontsize=8,
    )
    ax.set_ylabel("multi-positive nDCG (SigLIP referee)", fontsize=TICK_SIZE)
    ax.set_ylim(lo - 0.06, hi + 0.075)
    style_axes(ax)
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    mk = lambda c, label: Line2D(
        [],
        [],
        marker="o",
        linestyle="none",
        markersize=8,
        markerfacecolor=c,
        markeredgecolor=TEXT,
        markeredgewidth=0.6,
        label=label,
    )
    dark_legend(
        ax,
        [
            mk(GOLD, "profile run"),
            mk(RED, "same-corpus quartet (n=280)"),
            mk(CYAN, "today's snapshot"),
            Patch(facecolor=DIM, alpha=0.35, label="observed range (0.517–0.737)"),
        ],
        loc="upper left",
    )
    verdict(fig, "VERDICT: ~0.19 labeling noise — single-run profile-score deltas are never signal")
    return fig, "04-noise-floor.png"


def main():
    d = build()
    print(json.dumps(d["stats"], indent=1))
    (OUTDIR / "two-lenses.json").write_text(
        json.dumps(
            {
                "stats": d["stats"],
                "k": d["k"],
                "clusters": d["clusters"],
                "cluster_labels": CLUSTER_LABELS,
                "scores": d["scores"],
                "n_notes": len(d["ids"]),
            },
            indent=1,
        )
    )
    for f in (fig01, fig02, fig03, fig04):
        fig, name = f(d)
        frame_panels(fig)
        out = OUTDIR / name
        fig.savefig(out, dpi=DPI, facecolor=BG)
        print(f"wrote {out.relative_to(REPO)}  ({out.stat().st_size // 1024}KB)")
        plt.close(fig)


if __name__ == "__main__":
    main()
