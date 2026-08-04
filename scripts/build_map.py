"""Build the second-brain embedding map (issue #20), v2.

Two views over the shared gte-small text space:

- content: consumed media only (videos + sources/ notes). Painted with the
  interest profile's theme centroids — the territory they were fitted on.
- all: every embedding in the vault. The profile's themes do NOT describe
  this space (session-scraper atoms dominate it), so groups are derived from
  the data itself: HDBSCAN over a UMAP-reduced space, each cluster named by
  its c-TF-IDF terms, optionally polished into a human label by one batched
  Haiku call. Noise points render as dust.

UMAP parameters are fitted per view with --sweep (trustworthiness + group
silhouette), never eyeballed. Visual embeddings (1152-dim SigLIP) are a
different geometry and stay out per the E5 verdict; thumbnails join as hover
imagery only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

import numpy as np

from ytk import ridges, signals
from ytk.mapdomains import CONTENT_CATS as _CATS
from ytk.mapdomains import (
    UNPLACED,
    adopt_unplaced,
    bucket_labels,
    domain_labels,
    index_domains,
    load_buckets,
    notes_from_metas,
    user_path,
)

SNAPSHOT = Path(os.path.expanduser("~/.ytk/interest/latest.json"))
OUT = Path.home() / ".ytk" / "map.json"
# The garden's config, read here too — one taste axis, two consumers (#106).
BUCKETS = user_path("garden_buckets.yaml", "grove_buckets.yaml")

CONTENT_CATS = _CATS
# Absolute cosine required for theme assignment. A fixed floor makes assignment
# a property of the note instead of its batch. Null calibration is intentionally
# not used because it rejects most content despite the theme axis beating chance.
THEME_FLOOR = 0.496
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _normalize(m: np.ndarray) -> np.ndarray:
    return m / np.linalg.norm(m, axis=1, keepdims=True)


def _category(source_path: str) -> str:
    """Note category from its real vault location (both the second-brain tree
    and the pre-migration Vault/inbox/memories seed)."""
    parts = Path(source_path).parts
    if "sources" in parts:
        i = parts.index("sources")
        return parts[i + 1] if i + 1 < len(parts) - 1 else "web"
    if "memories" in parts:
        return "memory"
    if "memos" in parts:
        return "memo"
    if "projects" in parts:
        return "project-note"
    if "journal" in parts:
        return "journal"
    return "vault"


def _title(doc: str, fallback: str) -> str:
    """First real line of the note body, frontmatter and heading marks stripped."""
    text = doc or ""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4 :]
    for line in text.strip().splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line[:120]
    return fallback


def _vault_root() -> Path:
    from ytk.vault import _get_vault_path

    return _get_vault_path().resolve()


def _rel_path(source_path: str) -> str:
    """Vault-relative form of a note path (absolute paths stripped of the root)."""
    if not source_path:
        return ""
    p = Path(source_path)
    if p.is_absolute():
        try:
            return str(p.resolve().relative_to(_vault_root()))
        except ValueError:
            return ""
    return source_path


def _video_note_path(title: str) -> str:
    """Vault-relative path of a video's note. Filenames are title-derived and
    the convention shifted over time (raw title vs slug), so probe candidates
    on disk instead of trusting one scheme."""
    from ytk.vault import _slug

    base = _vault_root() / "second-brain" / "sources" / "youtube"
    for name in (_slug(title), title):
        if name and (base / f"{name}.md").exists():
            return f"second-brain/sources/youtube/{name}.md"
    return ""


def load_points() -> tuple[np.ndarray, list[dict], list[str]]:
    from ytk.store import _get_client

    client = _get_client()
    vecs: list = []
    meta: list[dict] = []
    docs: list[str] = []

    from ytk.store import epoch_collection_name

    videos = client.get_collection(epoch_collection_name("ytk_videos")).get(
        include=["embeddings", "metadatas", "documents"]
    )
    for vid, emb, m, doc in zip(
        videos["ids"], videos["embeddings"], videos["metadatas"], videos["documents"]
    ):
        if "#" in vid:  # retrieval-only part vector; one map point per video
            continue
        vecs.append(np.asarray(emb))
        docs.append(doc or "")
        d = m.get("date", "")
        meta.append(
            {
                "cat": "youtube",
                "title": m.get("title", ""),
                "url": m.get("url", ""),
                "date": f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else "",
                "video_id": m.get("video_id", ""),
                "path": "",
            }
        )

    memories = client.get_collection(epoch_collection_name("ytk_memories")).get(
        include=["embeddings", "metadatas", "documents"]
    )
    for mid, emb, m, doc in zip(
        memories["ids"], memories["embeddings"], memories["metadatas"], memories["documents"]
    ):
        if "#" in mid:  # retrieval-only part vector; one map point per note
            continue
        sp = m.get("source_path", "")
        dm = DATE_RE.search(m.get("doc_id", "") + " " + sp)
        url_m = re.search(r"^url: *(\S+)", (doc or "")[:600], re.MULTILINE)
        vecs.append(np.asarray(emb))
        docs.append(doc or "")
        # metadata first (#169): the indexer stores frontmatter title/url now;
        # the body-derived fallbacks yield embed markup for image-first notes
        meta.append(
            {
                "cat": _category(sp),
                "title": m.get("title") or _title(doc, m.get("doc_id", "")),
                "url": m.get("url") or (url_m.group(1) if url_m else ""),
                "date": dm.group(0) if dm else "",
                "video_id": "",
                "path": sp,
            }
        )

    return np.vstack(vecs), meta, docs


def assign_themes(vecs: np.ndarray, snapshot: dict) -> list[int]:
    # A re-anchored snapshot keeps dead themes for time-series identity but
    # drops their centroid (no resolvable members); skip those while keeping
    # the returned indices aligned with snapshot["themes"].
    themes = snapshot["themes"]
    valid = [i for i, t in enumerate(themes) if t.get("centroid")]
    cents = _normalize(np.array([themes[i]["centroid"] for i in valid]))
    sims = _normalize(vecs) @ cents.T
    best, conf = sims.argmax(axis=1), sims.max(axis=1)
    return [int(valid[b]) if c >= THEME_FLOOR else -1 for b, c in zip(best, conf)]


def _ctfidf_names(cluster_docs: list[str]) -> list[str]:
    """c-TF-IDF top-5 terms per cluster document blob."""
    from sklearn.feature_extraction.text import CountVectorizer

    min_df = 2 if len(cluster_docs) > 1 else 1
    vec = CountVectorizer(stop_words="english", max_features=20_000, min_df=min_df)
    tf = vec.fit_transform(cluster_docs).toarray().astype(float)
    tf = tf / tf.sum(axis=1, keepdims=True).clip(1)
    idf = np.log(1 + len(cluster_docs) / (1 + (tf > 0).sum(axis=0)))
    scores = tf * idf
    terms = np.array(vec.get_feature_names_out())
    return [", ".join(terms[np.argsort(scores[k])[::-1][:5]]) for k in range(len(cluster_docs))]


def derive_subtopics(
    vecs: np.ndarray, docs: list[str], doms: list[int], n_domains: int
) -> tuple[list[int], list[str], list[int]]:
    """HDBSCAN within each large domain. Returns (per-point global subtopic
    index or -1, subtopic term-names, owning domain per subtopic)."""
    import umap
    from sklearn.cluster import HDBSCAN

    dom_arr = np.array(doms)
    clabels = np.full(len(doms), -1, dtype=int)
    term_names: list[str] = []
    owners: list[int] = []
    for d in range(n_domains):
        idx = np.flatnonzero(dom_arr == d)
        if len(idx) < 120:
            continue
        reduced = umap.UMAP(
            n_neighbors=30,
            n_components=15,
            min_dist=0.0,
            metric="cosine",
            random_state=42,
        ).fit_transform(vecs[idx])
        # Scale cluster size with the domain while keeping small domains stable.
        local = HDBSCAN(min_cluster_size=max(20, len(idx) // 70), min_samples=5).fit_predict(
            reduced
        )
        n_local = local.max() + 1
        if n_local < 1:
            continue
        cluster_docs = [
            " ".join(docs[i] for i in idx[local == k])[:400_000] for k in range(n_local)
        ]
        base = len(term_names)
        term_names.extend(_ctfidf_names(cluster_docs))
        owners.extend([d] * n_local)
        for k in range(n_local):
            clabels[idx[local == k]] = base + k
        print(f"domain {d}: {n_local} subtopics over {len(idx)} points")
    return clabels.tolist(), term_names, owners


def assemble_all_view(
    domains_meta: list[dict],
    group_meta: list[dict],
    doms: list[int],
    clabels: list[int],
    axy: np.ndarray,
) -> dict:
    """Everything-view payload: domain and subtopic centroids over the 2D
    layout, with uniform-cap warnings (renderer arrays are fixed-size)."""
    if len(domains_meta) > 32:
        print(f"warning: {len(domains_meta)} domains exceeds the 32-domain uniform cap")
    if len(group_meta) > 96:
        print(f"warning: {len(group_meta)} subtopics exceeds the 96-subtopic uniform cap")
    return {
        "domains": group_positions(axy, doms, domains_meta),
        "groups": group_positions(axy, clabels, group_meta),
    }


def _point_key(m: dict) -> str:
    """Stable cross-build identity for a point (url, else title). Accepts both
    emitted point dicts (u/t) and load_points meta dicts (url/title)."""
    return m.get("u") or m.get("url") or m.get("t") or m.get("title") or ""


def load_previous_clusters() -> list[tuple[str, set[str], str | None]]:
    """Cluster (name, member-key set, domain label) triples from the previous
    map.json, if any. Domain label is None for pre-v2 files."""
    if not OUT.exists():
        return []
    try:
        prev = json.loads(OUT.read_text())
        groups = prev["all"]["groups"]
        domains = prev["all"].get("domains", [])

        def dom_label(g: dict) -> str | None:
            d = g.get("domain")
            return domains[d]["label"] if d is not None and d < len(domains) else None

        members: list[set[str]] = [set() for _ in groups]
        for p in prev["points"]:
            g = p.get("g", -1)
            if 0 <= g < len(members):
                members[g].add(_point_key(p))
        return [(g["label"], mem, dom_label(g)) for g, mem in zip(groups, members)]
    except Exception as exc:
        print(f"previous map unreadable ({exc}); no name anchoring")
        return []


def anchor_names(
    clabels: list[int],
    meta: list[dict],
    n_clusters: int,
    prev: list[tuple[str, set[str], str | None]],
    min_jaccard: float = 0.3,
    new_domains: list[str] | None = None,
) -> dict[int, str]:
    """Match new clusters to previous ones by member Jaccard overlap.

    Greedy best-first assignment; each old name is reused at most once.
    A name never crosses domains: candidates whose previous domain label is
    known and differs from the new cluster's domain are skipped (issue #70).
    Returns {new_cluster_index: kept_name} for matches above threshold.
    """
    if not prev:
        return {}
    arr = np.array(clabels)
    new_members = [
        {_point_key(meta[i]) for i in np.flatnonzero(arr == k)} for k in range(n_clusters)
    ]
    candidates = []
    for k, nm in enumerate(new_members):
        for j, (_, om, od) in enumerate(prev):
            if od is not None and new_domains is not None and od != new_domains[k]:
                continue
            union = len(nm | om)
            if union:
                candidates.append((len(nm & om) / union, k, j))
    anchored: dict[int, str] = {}
    used_old: set[int] = set()
    for jac, k, j in sorted(candidates, reverse=True):
        if jac < min_jaccard:
            break
        if k in anchored or j in used_old:
            continue
        anchored[k] = prev[j][0]
        used_old.add(j)
    return anchored


def polish_names(
    term_names: list[str], exemplars: list[list[str]], taken: list[str] | None = None
) -> list[str]:
    """One batched Haiku call turning c-TF-IDF term lists into short labels."""
    try:
        from pydantic import BaseModel

        from ytk import sdk

        class ClusterNames(BaseModel):
            names: list[str]

        listing = "\n".join(
            f"{i}. terms: {t} | examples: {'; '.join(e[:3])}"
            for i, (t, e) in enumerate(zip(term_names, exemplars))
        )
        avoid = (
            " These labels are already used by other clusters, do not reuse them: "
            + "; ".join(taken)
            + "."
            if taken
            else ""
        )
        result = sdk.structured(
            "Name each numbered cluster of personal knowledge-base notes with "
            "a short 2-4 word label capturing its topic. Ground each label in "
            "the terms and example titles given; do not invent topics. Return "
            f"exactly {len(term_names)} names, in order.{avoid}",
            listing,
            ClusterNames,
            max_input_chars=40_000,
        )
        if len(result.names) != len(term_names):
            raise ValueError(f"expected {len(term_names)} names, got {len(result.names)}")
        return [n.strip() for n in result.names]
    except Exception as exc:
        print(f"name polish skipped ({exc}); using term labels")
        return term_names


def score_layout(xy: np.ndarray, vecs: np.ndarray, labels: list[int]) -> dict:
    from sklearn.manifold import trustworthiness
    from sklearn.metrics import silhouette_score

    grouped = np.array(labels) >= 0
    uniq = set(np.array(labels)[grouped].tolist())
    return {
        "trustworthiness": float(trustworthiness(vecs, xy, n_neighbors=15, metric="cosine")),
        "silhouette": (
            float(silhouette_score(xy[grouped], np.array(labels)[grouped]))
            if len(uniq) > 1
            else 0.0
        ),
    }


def project(vecs: np.ndarray, n_neighbors: int, min_dist: float, dims: int = 2) -> np.ndarray:
    import umap

    return umap.UMAP(
        n_neighbors=n_neighbors,
        min_dist=min_dist,
        n_components=dims,
        metric="cosine",
        random_state=42,
    ).fit_transform(vecs)


def project3(vecs: np.ndarray, nn: int, md: float) -> np.ndarray:
    xyz = project(vecs, nn, md, dims=3)
    xyz -= xyz.mean(axis=0)
    xyz /= np.abs(xyz).max()
    return xyz


def fit_params(vecs: np.ndarray, labels: list[int], grid_nn: tuple) -> tuple[int, float]:
    results = []
    for nn in grid_nn:
        for md in (0.05, 0.1, 0.3):
            s = score_layout(project(vecs, nn, md), vecs, labels)
            results.append((nn, md, s))
            print(
                f"  nn={nn:>3} min_dist={md:.2f}  trust={s['trustworthiness']:.4f}  sil={s['silhouette']:.4f}"
            )
    best_trust = max(s["trustworthiness"] for _, _, s in results)
    ok = [r for r in results if r[2]["trustworthiness"] >= best_trust - 0.01]
    nn, md, s = max(ok, key=lambda r: r[2]["silhouette"])
    print(f"  chosen: nn={nn} min_dist={md} {s}")
    return nn, md


def layout(vecs: np.ndarray, labels: list[int], nn: int, md: float) -> tuple[np.ndarray, dict]:
    xy = project(vecs, nn, md)
    scores = score_layout(xy, vecs, labels)
    xy -= xy.mean(axis=0)
    xy /= np.abs(xy).max()
    return xy, {"n_neighbors": nn, "min_dist": md, **scores}


def group_positions(xy: np.ndarray, labels: list[int], group_meta: list[dict]) -> list[dict]:
    arr = np.array(labels)
    out = []
    for i, g in enumerate(group_meta):
        mask = arr == i
        cx, cy = xy[mask].mean(axis=0) if mask.any() else (0.0, 0.0)
        out.append({**g, "n": int(mask.sum()), "x": round(float(cx), 4), "y": round(float(cy), 4)})
    return out


def attach_terrain() -> None:
    """Compute density terrain (KDE contours + SCMS ridges, ytk/ridges.py)
    from the 2D coordinates already stored in map.json and write it back.
    Never re-runs UMAP: point positions are read, not recomputed."""
    data = json.loads(OUT.read_text())
    axy = np.array([[p["x"], p["y"]] for p in data["points"]])
    cxy = np.array([[p["cx"], p["cy"]] for p in data["points"] if "cx" in p and "cy" in p])
    print(f"terrain: all view ({len(axy)} points)")
    data["all"]["terrain"] = ridges.terrain(axy)
    print(f"terrain: content view ({len(cxy)} points)")
    data["content"]["terrain"] = ridges.terrain(cxy)
    # Filament web: SCMS ridge curves through the 3D embedding volume,
    # vertices tagged with the kernel-majority domain/theme for coloring.
    z3 = np.array([p["z3"] for p in data["points"]])
    doms = [p["dom"] for p in data["points"]]
    print(f"web: all view ({len(z3)} points)")
    data["all"]["web"] = ridges.web(z3, doms, len(data["all"]["domains"]))
    cpts = [p for p in data["points"] if "c3" in p]
    if cpts:
        c3 = np.array([p["c3"] for p in cpts])
        ths = [p.get("th", -1) for p in cpts]
        print(f"web: content view ({len(c3)} points)")
        data["content"]["web"] = ridges.web(c3, ths, len(data["content"]["groups"]))
    # Monte-Carlo fog splats of the same 3D density field the web's
    # filaments were traced through (issue #100, rungs 1-2).
    print(f"fog: all view ({len(z3)} points)")
    data["all"]["fog"] = ridges.fog(z3)
    if cpts:
        data["content"]["fog"] = ridges.fog(np.array([p["c3"] for p in cpts]), n_samples=2000)
    OUT.write_text(json.dumps(data))
    for view in ("all", "content"):
        t = data[view]["terrain"]
        print(
            f"  {view}: h={t['h']} {len(t['contours'])} contour paths, "
            f"{len(t['ridges'])} ridge polylines"
        )


def _content_alignment(points: list[dict], meta: list[dict], content_cats) -> list[int]:
    """Store rows must still match map.json rows one-to-one; the sphere pass
    is index-aligned, so any drift means a stale map — rebuild, not guess."""
    if len(points) != len(meta):
        raise SystemExit(
            f"map.json has {len(points)} points but the store has {len(meta)} — "
            "stale map; run the full build first"
        )
    for i, (p, m) in enumerate(zip(points, meta)):
        if p["t"] != m["title"]:
            raise SystemExit(
                f"map.json point {i} is {p['t']!r} but store row is "
                f"{m['title']!r} — stale map; run the full build first"
            )
    cidx = [i for i, m in enumerate(meta) if m["cat"] in content_cats]
    map_cidx = [i for i, p in enumerate(points) if "c3" in p]
    if cidx != map_cidx:
        raise SystemExit("content membership drifted since the map build — rebuild")
    return cidx


def _vault_rel(path: str) -> str | None:
    """map.json thumb paths are served at /vault-media/<rel>, mounted at the
    vault's second-brain root -- an absolute path is useless to that route."""
    if path.startswith("sources/"):
        return path
    marker = "second-brain/"
    i = path.find(marker)
    return path[i + len(marker) :] if i != -1 else None


def _frontmatter_image(path: Path) -> str | None:
    """First image_paths entry from a note's frontmatter, or None if the
    field, the frontmatter, or its closing fence is absent."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    fm = text[:end]
    lines = fm.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "image_paths:":
            for entry in lines[i + 1 :]:
                stripped = entry.strip()
                if stripped.startswith("- "):
                    return stripped[2:].strip()
                break
            return None
    return None


def attach_sphere() -> None:
    """Compute the /orb sphere layouts (ytk/spheremap.py) from the stored c3
    coordinates plus live store vectors, and attach thumbnail paths. Aligned
    by index to the existing map.json; aborts loudly on drift."""
    from ytk.spheremap import sphere_block
    from ytk.store import _get_client

    data = json.loads(OUT.read_text())
    vecs, meta, _docs = load_points()
    cidx = _content_alignment(data["points"], meta, CONTENT_CATS)
    cpts = [data["points"][i] for i in cidx]
    c3 = np.array([p["c3"] for p in cpts])
    themes = [p.get("th", -1) for p in cpts]
    nn = int(data["content"]["params"].get("n_neighbors", 30))
    md = float(data["content"]["params"].get("min_dist", 0.05))
    print(f"sphere: {len(cpts)} content points, nn={nn} min_dist={md}")
    block = sphere_block(vecs[cidx], c3, themes, n_neighbors=nn, min_dist=md)
    for name, s in block["scores"].items():
        mark = " <- chosen" if name == block["chosen"] else ""
        print(
            f"  {name}: trust={s['trustworthiness']:.4f} "
            f"meanNN={s['mean_nn_deg']:.2f}deg overlap={s['overlap']} "
            f"({100 * s['overlap_frac']:.1f}%){mark}"
        )
    data["content"]["sphere"] = block
    client = _get_client()
    thumbs = {
        m["url"]: m["image_path"]
        for m in client.get_collection("ytk_visual").get(include=["metadatas"])["metadatas"]
        if m.get("url") and m.get("image_path")
    }
    n_thumbs = 0
    n_fallback = 0
    root = _vault_root()
    for p in cpts:
        t = thumbs.get(p.get("u"))
        rel = _vault_rel(t) if t else None
        if rel:
            p["thumb"] = rel
            n_thumbs += 1
            continue
        note_rel = p.get("p")
        if not note_rel:
            continue
        img = _frontmatter_image(root / note_rel)
        if img and (root / "second-brain" / img).exists():
            p["thumb"] = img
            n_thumbs += 1
            n_fallback += 1
    print(
        f"  thumbs: {n_thumbs}/{len(cpts)} ({n_fallback} from frontmatter fallback); "
        f"sample: {[p.get('thumb') for p in cpts[:3]]}"
    )
    OUT.write_text(json.dumps(data))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true", help="fit UMAP params per view")
    ap.add_argument("--no-llm", action="store_true", help="skip Haiku label polish")
    ap.add_argument(
        "--attach-terrain",
        action="store_true",
        help="only (re)compute density terrain over the existing map.json layout",
    )
    ap.add_argument(
        "--attach-sphere",
        action="store_true",
        help="only (re)compute the /orb sphere layouts over the existing map.json",
    )
    args = ap.parse_args()
    if args.attach_terrain:
        attach_terrain()
        return
    if args.attach_sphere:
        attach_sphere()
        return

    snapshot = json.loads(SNAPSHOT.read_text())
    vecs, meta, docs = load_points()
    smap = signals.signal_map()
    from ytk.store import _get_client

    client = _get_client()
    thumbs = {
        m["url"]: m["image_path"]
        for m in client.get_collection("ytk_visual").get(include=["metadatas"])["metadatas"]
        if m.get("url") and m.get("image_path")
    }

    # --- content view: consumed media, theme-painted -----------------------
    cidx = [i for i, m in enumerate(meta) if m["cat"] in CONTENT_CATS]
    cvecs = vecs[cidx]
    cthemes = assign_themes(cvecs, snapshot)
    print(f"content view: {len(cidx)} points")
    cnn, cmd = fit_params(cvecs, cthemes, (5, 10, 15, 30)) if args.sweep else (30, 0.05)
    cxy, cparams = layout(cvecs, cthemes, cnn, cmd)
    cxyz = project3(cvecs, cnn, cmd)
    theme_meta = [{"label": t["label"], "weight": t["weight"]} for t in snapshot["themes"]]

    # --- all view: domain hierarchy + per-domain subtopics -------------------
    print(f"all view: {len(meta)} points")
    content_theme = {g: cthemes[k] for k, g in enumerate(cidx)}
    theme_names = [t["label"] for t in snapshot["themes"]]
    if BUCKETS.exists():
        cfg = load_buckets(BUCKETS)
        notes = notes_from_metas(meta, content_theme, theme_names, _rel_path)
        stale = {t for b in cfg.buckets for t in b.themes} - set(theme_names)
        if stale:
            # a profile re-synthesis renames themes and kills matchers
            # silently -- it has happened twice (2026-07-25, 2026-07-29)
            print(
                "WARNING: STALE THEME MATCHERS in grove_buckets.yaml -- these "
                f"match zero notes: {sorted(stale)}. Live themes: {sorted(theme_names)}"
            )
        labels_str = bucket_labels(notes, cfg)
        n_unplaced = sum(1 for label in labels_str if label == UNPLACED)
        labels_str = adopt_unplaced(labels_str, vecs)
        print(
            f"domains: bucket axis, {len(cfg.buckets)} buckets, "
            f"{n_unplaced} adopted by nearest-neighbour vote "
            f"({100 * n_unplaced / len(labels_str):.0f}%)"
        )
    else:
        # No bucket config: fall back to the provenance axis rather than
        # rendering an unlabelled map.
        print(f"domains: no {BUCKETS}, falling back to the provenance axis")
        labels_str = domain_labels(meta, content_theme, theme_names)
    doms, domains_meta = index_domains(labels_str)
    clabels, term_names, owners = derive_subtopics(vecs, docs, doms, len(domains_meta))
    exemplars = [
        [meta[i]["title"] for i in np.flatnonzero(np.array(clabels) == k)[:5]]
        for k in range(len(term_names))
    ]
    # Anchor names deterministically to the previous build so labels stay
    # stable across rebuilds; Haiku only names genuinely new clusters.
    anchored = anchor_names(
        clabels,
        meta,
        len(term_names),
        load_previous_clusters(),
        new_domains=[domains_meta[owners[k]]["label"] for k in range(len(term_names))],
    )
    fresh = [k for k in range(len(term_names)) if k not in anchored]
    print(f"name anchoring: {len(anchored)} kept, {len(fresh)} new")
    if fresh and not args.no_llm:
        fresh_names = polish_names(
            [f"{domains_meta[owners[k]]['label']} | {term_names[k]}" for k in fresh],
            [exemplars[k] for k in fresh],
            taken=sorted(set(anchored.values())),
        )
        for k, nm in zip(fresh, fresh_names):
            anchored[k] = nm
    names = [anchored.get(k, term_names[k]) for k in range(len(term_names))]
    ann, amd = fit_params(vecs, doms, (10, 30, 50)) if args.sweep else (50, 0.05)
    axy, aparams = layout(vecs, doms, ann, amd)
    axyz = project3(vecs, ann, amd)
    from sklearn.manifold import trustworthiness as _trust

    aparams["trustworthiness_3d"] = float(_trust(vecs, axyz, n_neighbors=15, metric="cosine"))
    cparams["trustworthiness_3d"] = float(_trust(cvecs, cxyz, n_neighbors=15, metric="cosine"))
    weights = [float((np.array(clabels) == k).sum()) / len(clabels) for k in range(len(names))]
    group_meta = [
        {"label": nm, "domain": d, "weight": w, "terms": tn}
        for nm, d, w, tn in zip(names, owners, weights, term_names)
    ]

    # --- unified point list: all-view position on every point; content
    # members additionally carry their content-view position and theme,
    # so the renderer can morph between layouts in the vertex shader
    cpos = {g: k for k, g in enumerate(cidx)}
    points = []
    for i, m in enumerate(meta):
        p = {
            "x": round(float(axy[i][0]), 4),
            "y": round(float(axy[i][1]), 4),
            "z3": [round(float(v), 4) for v in axyz[i]],
            "t": m["title"],
            "c": m["cat"],
            "u": m["url"],
            "d": m["date"],
            "g": clabels[i],
            "dom": doms[i],
            "p": _rel_path(m["path"])
            or (_video_note_path(m["title"]) if m["cat"] == "youtube" else ""),
            "r": smap.get(m["video_id"], smap.get(m["path"], 0)),
            "img": bool(thumbs.get(m["url"])),
        }
        if i in cpos:
            k = cpos[i]
            p["cx"] = round(float(cxy[k][0]), 4)
            p["cy"] = round(float(cxy[k][1]), 4)
            p["c3"] = [round(float(v), 4) for v in cxyz[k]]
            p["th"] = cthemes[k]
        points.append(p)

    OUT.write_text(
        json.dumps(
            {
                "v": 2,
                "generated": snapshot["generated_at"],
                "content": {"params": cparams, "groups": group_positions(cxy, cthemes, theme_meta)},
                "all": {
                    "params": aparams,
                    **assemble_all_view(domains_meta, group_meta, doms, clabels, axy),
                },
                "points": points,
            }
        )
    )
    print(f"wrote {OUT}: {len(points)} points, {len(cidx)} content members")
    attach_terrain()
    attach_sphere()


if __name__ == "__main__":
    main()
