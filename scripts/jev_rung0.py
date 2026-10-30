"""Section 53, rung 0: does Jev's brightness land on the note the agent opened?

28 real agent searches from the retrieval log (22 where a served hit was then
opened, 6 bare-id lookups). Round one gives Jev the 200-character snippet the
MCP tool gives the agent; round two gives it the full stored document, the
text the embedder ranked, in one request carrying every question type.

    uv run python scripts/jev_rung0.py collect    # searches + 84 API calls
    uv run python scripts/jev_rung0.py collect2   # stored text, 56 API calls
    uv run --with matplotlib python scripts/jev_rung0.py draw    # fig 01, sidecar only
    uv run --with matplotlib python scripts/jev_rung0.py draw2   # fig 02, sidecar only
"""

from __future__ import annotations

import json
import statistics
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/ on path

ROOT = Path(__file__).resolve().parents[1]
OUTDIR = ROOT / "docs" / "assets" / "53-jev-second-look"
CASES = OUTDIR / "cases.json"
SIDECAR = OUTDIR / "rung0.json"
SIDECAR2 = OUTDIR / "rung0b.json"
TOP = 20
# Served snippet length in store.search_all: the bytes a searcher sees.
EXCERPT = 200

ASK_NOUL = "Is `candidates.{k}` the note someone who searched for `query` would open?"
NOUL_TRUE = "Its title or excerpt covers the specific thing `query` names, not only its topic."
NOUL_FALSE = "Only a related topic, a different item, or no connection to `query`."
NOUL_TRUE2 = "Its title or text covers the specific thing `query` names, not only its topic."
ASK_ANY = "Does any note in `candidates` hold what `query` asks for?"
ASK_BEST = "Which candidate holds what `query` asks for?"
NONE_DESC = "No candidate holds it."


def commit_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()


def stamp(model: str, **extra) -> dict:
    return {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": commit_sha(),
        "model": model,
        "top": TOP,
        **extra,
    }


def collect() -> None:
    import jev_client as jev

    from ytk import store

    cases = json.loads(CASES.read_text())
    rows = []
    for c in cases:
        hits = store.search_all(c["query"], n=TOP, rerank=False, actor="probe")
        cands = [
            {
                "key": f"c{i:02d}",
                "doc_id": h.doc_id,
                "type": h.type,
                "title": h.title[:120],
                "excerpt": h.excerpt[:EXCERPT],
                "distance": round(h.distance, 4),
            }
            for i, h in enumerate(hits, 1)
        ]
        state = {
            "query": c["query"],
            "candidates": {x["key"]: {"title": x["title"], "excerpt": x["excerpt"]} for x in cands},
        }
        qs = {x["key"]: jev.noul(ASK_NOUL.format(k=x["key"]), NOUL_TRUE, NOUL_FALSE) for x in cands}
        qs["any"] = jev.noul(ASK_ANY)
        a = jev.system_one(state, qs, tag="rung0-noul")

        crit = {x["key"]: x["title"][:100] for x in cands}
        b = jev.system_one(
            state, {"best": jev.choice(ASK_BEST, {**crit, "none": NONE_DESC})}, tag="rung0-choice"
        )
        rev = dict(reversed(list(crit.items())))
        r = jev.system_one(
            state,
            {"best": jev.choice(ASK_BEST, {"none": NONE_DESC, **rev})},
            tag="rung0-choice-rev",
        )

        opened = c.get("opened_doc_id")
        rank_today = next((i for i, x in enumerate(cands, 1) if x["doc_id"] == opened), None)
        present = served = None
        if c["group"] == "id-lookup":
            needle = (
                c["query"].split()[2]
                if c["query"].startswith("TikTok item")
                else c["query"].split()[-1]
            )
            served = any(needle in x["doc_id"] for x in cands)
            present = bool(store._videos_collection().get(ids=[needle])["ids"])
        rows.append(
            {
                **c,
                "candidates": cands,
                "opened_rank_today": rank_today,
                "in_store": present,
                "served_today": served,
                "noul": [a.answers[x["key"]]["noul"] for x in cands],
                "any": a.answers["any"]["noul"],
                "choice": b.answers["best"]["probabilities"],
                "choice_rev": r.answers["best"]["probabilities"],
                "winner": b.answers["best"]["choice"],
                "winner_rev": r.answers["best"]["choice"],
                "usage": [a.input_tokens, b.input_tokens, r.input_tokens],
                "latency_s": [a.latency_s, b.latency_s, r.latency_s],
                "model": a.model,
            }
        )
        print(
            f"{c['group']:9} rank then {c.get('rank_then', '-'):>2} today {rank_today!s:>4} "
            f"| any {a.answers['any']['noul']:.2f} best {b.answers['best']['choice']}/{r.answers['best']['choice']} "
            f"| {c['query'][:50]}"
        )
    SIDECAR.write_text(
        json.dumps(
            {
                **stamp(
                    rows[0]["model"],
                    excerpt_chars=EXCERPT,
                    questions={
                        "noul": ASK_NOUL,
                        "noul_true": NOUL_TRUE,
                        "noul_false": NOUL_FALSE,
                        "any": ASK_ANY,
                        "best": ASK_BEST,
                    },
                ),
                "rows": rows,
            },
            indent=1,
        )
    )
    print(f"wrote {SIDECAR.relative_to(ROOT)}")


def stored_text(store, cand: dict) -> str:
    """The document Chroma embedded for this hit: what the ranking actually saw."""
    col = store._videos_collection() if cand["type"] == "video" else store._memories_collection()
    got = col.get(ids=[cand["doc_id"]], include=["documents"])
    if not got["ids"]:
        got = col.get(where={"doc_id": cand["doc_id"]}, include=["documents"], limit=5)
    return "\n".join(got["documents"])


def collect2() -> None:
    """Round two: the same served candidates as round one, full stored text,
    every question in one request (Nouls, any, Choice); reversed Choice apart."""
    import jev_client as jev

    from ytk import store

    base = json.loads(SIDECAR.read_text())
    rows = []
    for r0 in base["rows"]:
        cands = r0["candidates"]
        texts = {x["key"]: stored_text(store, x) for x in cands}
        state = {
            "query": r0["query"],
            "candidates": {x["key"]: {"title": x["title"], "text": texts[x["key"]]} for x in cands},
        }
        crit = {x["key"]: x["title"][:100] for x in cands}
        qs = {
            x["key"]: jev.noul(ASK_NOUL.format(k=x["key"]), NOUL_TRUE2, NOUL_FALSE) for x in cands
        }
        qs["any"] = jev.noul(ASK_ANY)
        qs["best"] = jev.choice(ASK_BEST, {**crit, "none": NONE_DESC})
        a = jev.system_one(state, qs, tag="rung0b-all")
        rev = dict(reversed(list(crit.items())))
        r = jev.system_one(
            state,
            {"best": jev.choice(ASK_BEST, {"none": NONE_DESC, **rev})},
            tag="rung0b-choice-rev",
        )
        rows.append(
            {
                **{
                    k: r0[k]
                    for k in (
                        "case",
                        "group",
                        "query",
                        "opened_rank_today",
                        "in_store",
                        "served_today",
                    )
                },
                "text_chars": [len(texts[x["key"]]) for x in cands],
                "noul": [a.answers[x["key"]]["noul"] for x in cands],
                "any": a.answers["any"]["noul"],
                "choice": a.answers["best"]["probabilities"],
                "choice_rev": r.answers["best"]["probabilities"],
                "winner": a.answers["best"]["choice"],
                "winner_rev": r.answers["best"]["choice"],
                "usage": [a.input_tokens, r.input_tokens],
                "latency_s": [a.latency_s, r.latency_s],
                "model": a.model,
            }
        )
        print(
            f"{r0['group']:9} today {r0['opened_rank_today']!s:>4} | any {a.answers['any']['noul']:.2f} "
            f"best {a.answers['best']['choice']}/{r.answers['best']['choice']} | {a.input_tokens:>6} tok "
            f"{a.latency_s * 1000:.0f} ms | {r0['query'][:44]}"
        )
    SIDECAR2.write_text(
        json.dumps(
            {
                **stamp(
                    rows[0]["model"],
                    context="full stored document (what Chroma embedded)",
                    questions={
                        "noul": ASK_NOUL,
                        "noul_true": NOUL_TRUE2,
                        "noul_false": NOUL_FALSE,
                        "any": ASK_ANY,
                        "best": ASK_BEST,
                    },
                ),
                "rows": rows,
            },
            indent=1,
        )
    )
    print(f"wrote {SIDECAR2.relative_to(ROOT)}")


# --- drawing ------------------------------------------------------------------


def order_rows(rows: list[dict]) -> tuple[list[dict], int]:
    """Reorder to reveal: opened rows by where the opened note sits today, so
    the outlined cells form a staircase; id rows below, absent first."""
    opened = sorted(
        [r for r in rows if r["group"] == "opened"],
        key=lambda r: (r["opened_rank_today"] is None, r["opened_rank_today"] or 99),
    )
    ids = sorted([r for r in rows if r["group"] == "id-lookup"], key=lambda r: r["in_store"])
    return opened + ids, len(opened)


def grid(order: list[dict], field: str) -> np.ndarray:

    m = np.full((len(order), TOP), np.nan)
    for i, r in enumerate(order):
        if field == "noul":
            vals = r["noul"]
        else:
            vals = [r["choice"].get(f"c{j:02d}", 0.0) for j in range(1, len(r["noul"]) + 1)]
        m[i, : len(vals)] = vals
    return m


def strip_of(order: list[dict]) -> np.ndarray:

    return np.array(
        [
            [
                r["any"],
                r["choice"].get("none", 0.0),
                r["choice_rev"].get("none", 0.0),
                float(r["winner"] == r["winner_rev"]),
            ]
            for r in order
        ]
    )


def counts(order: list[dict], mats: dict[str, np.ndarray]) -> dict[str, str]:
    """Per-arm: in how many opened rows is the brightest cell the opened note."""

    hit = [(i, r) for i, r in enumerate(order) if r["group"] == "opened" and r["opened_rank_today"]]
    out = {}
    for name, m in mats.items():
        k = sum(int(np.nanargmax(m[i]) + 1 == r["opened_rank_today"]) for i, r in hit)
        out[name] = f"{k}/{len(hit)}"
    out["rank1"] = f"{sum(r['opened_rank_today'] == 1 for _, r in hit)}/{len(hit)}"
    absent = [r for r in order if r["group"] == "id-lookup" and not r["in_store"]]
    unserved = [
        r for r in order if r["group"] == "id-lookup" and r["in_store"] and not r["served_today"]
    ]
    out["none_absent"] = f"{sum(r['winner'] == 'none' for r in absent)}/{len(absent)}"
    out["none_unserved"] = f"{sum(r['winner'] == 'none' for r in unserved)}/{len(unserved)}"
    return out


def draw_grids(
    *,
    number: int,
    title: str,
    meta: str,
    order: list[dict],
    n_opened: int,
    panels: list[tuple[str, np.ndarray]],
    strip: np.ndarray,
    verdict_text: str,
    out_name: str,
    w: float,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib.patches import Rectangle
    from plot_assets import (
        BG,
        CYAN,
        DIM,
        DPI,
        FRAME,
        MARGIN,
        MUTED,
        figure,
        frame_panels,
        panel_title,
        punch,
        saturated_magma,
        style_axes,
        verdict,
    )

    n = len(order)
    cmap = saturated_magma()
    h = 12.4
    fig, top = figure(w, h, number, "jev, second look", title, meta=meta)
    labels = [r["query"][:44] + ("…" if len(r["query"]) > 44 else "") for r in order]
    bottom, key_h = 0.105, 0.03
    height = top - bottom - 0.05
    label_w = 2.75 / w  # inches of query label, as a figure fraction
    x0 = MARGIN + label_w
    gap = 0.012
    strip_w = 0.9 / w
    grid_w = (1 - MARGIN - x0 - strip_w - gap * len(panels)) / len(panels)
    specs = [(t, m, TOP, grid_w) for t, m in panels] + [
        ("any · none · none r · same", strip, 4, strip_w)
    ]
    for j, (ptitle, mat, cols, width) in enumerate(specs):
        ax = fig.add_axes([x0, bottom, width, height])
        style_axes(ax)
        ax.imshow(
            punch(np.nan_to_num(mat, nan=0.0)),
            cmap=cmap,
            vmin=0,
            vmax=1,
            aspect="auto",
            interpolation="nearest",
            extent=(0.5, cols + 0.5, n + 0.5, 0.5),
        )
        if cols == TOP:
            for i, r in enumerate(order):
                rk = r["opened_rank_today"]
                if rk:
                    ax.add_patch(
                        Rectangle(
                            (rk - 0.5, i + 0.5), 1, 1, fill=False, edgecolor=CYAN, linewidth=1.6
                        )
                    )
                elif r["group"] == "opened":
                    ax.plot(cols + 0.35, i + 1, marker="<", color=CYAN, markersize=5, clip_on=False)
                for col in range(len(r["noul"]), cols):
                    ax.add_patch(
                        Rectangle((col + 0.5, i + 0.5), 1, 1, facecolor=DIM, edgecolor="none")
                    )
            ax.set_xticks(range(1, cols + 1))
            ax.set_xticklabels(
                [str(t) if t in (1, 5, 10, 15, 20) else "" for t in range(1, cols + 1)]
            )
            ax.set_xlabel("served rank today", color=MUTED)
        else:
            ax.set_xticks([1, 2, 3, 4])
            ax.set_xticklabels(["any", "none", "none r", "same"], rotation=90)
        ax.axhline(n_opened + 0.5, color=FRAME, linewidth=1.2)
        ax.set_yticks(range(1, n + 1))
        ax.set_yticklabels(labels if j == 0 else [])
        ax.tick_params(length=0)
        panel_title(ax, ptitle, width=max(22, int(width * w * 7.2)))
        x0 += width + gap

    # Key: the colour scale drawn through the same punch() lift the cells use,
    # so the bar is honest about what each brightness means.
    cax = fig.add_axes([MARGIN + label_w, 0.045, 1.6 / w, key_h * 0.5])
    cax._is_colorbar = True
    ramp = np.linspace(0, 1, 256)
    cax.imshow(punch(ramp)[None, :], cmap=cmap, vmin=0, vmax=1, aspect="auto", extent=(0, 1, 0, 1))
    cax.set_yticks([])
    cax.set_xticks([0, 0.5, 1])
    cax.tick_params(colors=MUTED, labelsize=8, length=2)
    for s in cax.spines.values():
        s.set_color(FRAME)
    fig.text(MARGIN + label_w, 0.045 + key_h * 0.5 + 0.006, "cell: P(yes)", color=MUTED, fontsize=9)
    fig.text(
        MARGIN + label_w + 1.9 / w,
        0.05,
        "cyan outline: the note the agent opened after this search    "
        "grey cell: fewer than 20 candidates served    "
        "same: served and reversed Choice agree on the winner (1) or not (0)",
        color=MUTED,
        fontsize=9,
        va="center",
    )
    verdict(fig, verdict_text)
    frame_panels(fig)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / out_name
    fig.savefig(out, dpi=DPI, facecolor=BG)
    print(f"wrote {out.relative_to(ROOT)}  ({out.stat().st_size // 1024}KB)")


def draw() -> None:
    data = json.loads(SIDECAR.read_text())
    order, n_opened = order_rows(data["rows"])
    noul, pick = grid(order, "noul"), grid(order, "choice")
    c = counts(order, {"noul": noul, "choice": pick})
    tokens = sum(sum(r["usage"]) for r in data["rows"])
    lat = statistics.median(t for r in data["rows"] for t in r["latency_s"])
    n_ids = len(order) - n_opened
    draw_grids(
        number=1,
        title="Where Jev's brightness lands, against where the agent clicked",
        meta=(
            f"{n_opened} searches with an opened hit, {n_ids} bare-id lookups | one row per search, "
            f"columns = served rank today | Jev sees the {data['excerpt_chars']}-char snippet the MCP tool "
            f"shows the agent | {data['model']}, {len(data['rows']) * 3} requests, {tokens:,} input tokens, "
            f"median {lat * 1000:.0f} ms | {data['commit']} {data['generated'][:10]}"
        ),
        order=order,
        n_opened=n_opened,
        panels=[
            ("One Noul per candidate: is this the note the searcher would open?", noul),
            ("One Choice over all candidates plus none: which holds it?", pick),
        ],
        strip=strip_of(order),
        verdict_text=(
            f"Noul brightest on the opened note {c['noul']} · served rank 1 had it {c['rank1']} · "
            f"Choice top candidate {c['choice']} · none on absent ids {c['none_absent']}, "
            f"on in-store-unserved {c['none_unserved']}"
        ),
        out_name="01-second-look.png",
        w=17.0,
    )


def draw2() -> None:

    base = json.loads(SIDECAR.read_text())
    data = json.loads(SIDECAR2.read_text())
    order, n_opened = order_rows(data["rows"])
    by_case = {r["case"]: r for r in base["rows"]}
    order_base = [by_case[r["case"]] for r in order]
    noul0 = grid(order_base, "noul")
    noul, pick = grid(order, "noul"), grid(order, "choice")
    # The Choice's abstention as a row-wide gate on the Noul's per-candidate scale.
    gate = np.array([1 - r["choice"].get("none", 0.0) for r in order])[:, None]
    gated = noul * gate
    c = counts(order, {"noul0": noul0, "noul": noul, "choice": pick, "gated": gated})
    tokens = sum(sum(r["usage"]) for r in data["rows"])
    lat = statistics.median(r["latency_s"][0] for r in data["rows"])
    chars = [t for r in data["rows"] for t in r["text_chars"]]
    draw_grids(
        number=2,
        title="The same searches, Jev reading the text the embedder ranked",
        meta=(
            f"{n_opened} searches with an opened hit, {len(order) - n_opened} bare-id lookups | columns = served "
            f"rank today | left panel repeats figure 01's snippet run; the other three read the full stored "
            f"document (median {int(statistics.median(chars)):,} chars, max {max(chars):,}) with every question "
            f"in one request | gated = Noul x (1 - P(none)) | {data['model']}, {len(data['rows']) * 2} requests, "
            f"{tokens:,} input tokens, median {lat * 1000:.0f} ms per combined request | "
            f"{data['commit']} {data['generated'][:10]}"
        ),
        order=order,
        n_opened=n_opened,
        panels=[
            ("Noul, 200-char snippet (figure 01)", noul0),
            ("Noul, full stored text", noul),
            ("Choice plus none, full stored text", pick),
            ("Noul gated by the Choice's 1 - P(none)", gated),
        ],
        strip=strip_of(order),
        verdict_text=(
            f"brightest on the opened note: snippet Noul {c['noul0']} -> stored Noul {c['noul']} · Choice top candidate "
            f"{c['choice']} · gated {c['gated']} · rank 1 {c['rank1']} · none on absent ids {c['none_absent']}"
        ),
        out_name="02-stored-text.png",
        w=22.0,
    )


if __name__ == "__main__":
    {"collect": collect, "collect2": collect2, "draw": draw, "draw2": draw2}[sys.argv[1]]()
