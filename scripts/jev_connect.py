"""Section 56: the connect slot. Collect the candidate pairs the linker has
judged, then score four decision arms against blind grades and the owner's
rulings. Registration in docs/assets/56-jev-connect-slot/README.md.

    uv run python scripts/jev_connect.py pairs      # ledger -> pairs.json
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTDIR = ROOT / "docs" / "assets" / "56-jev-connect-slot"
PAIRS = OUTDIR / "pairs.json"
LEDGER = Path(os.path.expanduser("~/.ytk/ledger.db"))


def _dotenv(key: str) -> str | None:
    env = ROOT / ".env"
    if not env.exists():
        return None
    for line in env.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"')
    return None


def vault_root() -> Path:
    return Path(os.environ.get("OBSIDIAN_VAULT_PATH") or _dotenv("OBSIDIAN_VAULT_PATH") or "")


def section(text: str, heading: str) -> str:
    m = re.search(rf"^## {re.escape(heading)}\s*\n(.*?)(?=^## |\Z)", text, re.DOTALL | re.MULTILINE)
    return m.group(1).strip() if m else ""


def frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    out: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"')
    return out


def note_index(brain: Path) -> dict[str, Path]:
    """Stem -> path over the vault's content notes. Obsidian resolves a
    wikilink vault-wide, so a stem is the link's identity."""
    out: dict[str, Path] = {}
    for p in brain.rglob("*.md"):
        out.setdefault(p.stem, p)
    return out


def _find_by_url(brain: Path, url: str, idx: dict[str, Path]) -> Path | None:
    for p in idx.values():
        head = p.read_text(errors="ignore")[:600]
        if url in head:
            return p
    return None


def collect_pairs() -> dict:
    brain = vault_root() / "second-brain"
    idx = note_index(brain)
    conn = sqlite3.connect(f"file:{LEDGER}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    snap = {
        r["item_id"]: r["after_ref"]
        for r in conn.execute("SELECT item_id, after_ref FROM snapshots ORDER BY id")
    }
    takes = {
        r["item_id"]: r["text"]
        for r in conn.execute("SELECT item_id, text FROM takes WHERE kind='intent' ORDER BY id")
    }
    applied: dict[int, set[str]] = {}
    for r in conn.execute("SELECT item_id, detail FROM activity WHERE action='connect-apply'"):
        d = json.loads(r["detail"] or "{}")
        applied.setdefault(r["item_id"], set()).update(
            link["target"] for link in d.get("links", [])
        )
    rulings = {
        r["item_id"]: (r["choice"], r["text"])
        for r in conn.execute(
            "SELECT a.item_id, n.choice, n.text FROM asks a JOIN answers n ON n.ask_id=a.id WHERE a.kind='connections'"
        )
    }

    items: list[dict] = []
    for r in conn.execute(
        "SELECT a.id, a.item_id, a.at, a.reason, a.detail, a.model, a.tokens, a.duration_ms, i.title, i.url, i.source "
        "FROM activity a JOIN items i ON i.id=a.item_id WHERE a.action='connect' AND a.detail IS NOT NULL ORDER BY a.id"
    ):
        d = json.loads(r["detail"])
        links = {link["target"]: link for link in d.get("links", [])}
        cands = d.get("candidates") or [{"target": t, "via": None, "cosine": None} for t in links]
        if not cands:
            continue
        path = (
            Path(snap[r["item_id"]]) if r["item_id"] in snap else _find_by_url(brain, r["url"], idx)
        )
        text = path.read_text(errors="ignore") if path and path.exists() else ""
        fm = frontmatter(text)
        ruling = rulings.get(r["item_id"])
        pairs = []
        for c in cands:
            tpath = idx.get(c["target"])
            ttext = tpath.read_text(errors="ignore") if tpath else ""
            argued = c["target"] in links
            if ruling is None:
                owner = "pending"
            elif not argued:
                owner = "not proposed"
            else:
                owner = "approved" if c["target"] in applied.get(r["item_id"], set()) else "struck"
            pairs.append(
                {
                    "target": c["target"],
                    "target_title": frontmatter(ttext).get("title")
                    or (links.get(c["target"]) or {}).get("target_title")
                    or c["target"],
                    "target_path": str(tpath.relative_to(vault_root())) if tpath else None,
                    "target_thesis": section(ttext, "Thesis"),
                    "via": c.get("via"),
                    "cosine_logged": c.get("cosine"),
                    "shipped": "argued" if argued else "declined",
                    "argument": (links.get(c["target"]) or {}).get("argument"),
                    "owner": owner,
                }
            )
        items.append(
            {
                "item_id": r["item_id"],
                "at": r["at"],
                "title": r["title"],
                "source": r["source"],
                "url": r["url"],
                "note_path": str(path.relative_to(vault_root())) if path else None,
                "thesis": section(text, "Thesis") or fm.get("title", ""),
                "summary": section(text, "Summary"),
                "take": takes.get(r["item_id"]),
                "ruling": ruling[0] if ruling else None,
                "ruling_text": ruling[1] if ruling else None,
                "shipped_model": r["model"],
                "shipped_tokens": r["tokens"],
                "shipped_ms": r["duration_ms"],
                "declined_known": "candidates" in d,
                "pairs": pairs,
            }
        )
    return {"items": items}


def body(rel: str | None) -> str:
    """A note as a blind reader or a decision arm sees it: everything above
    the raw transcript, with the Connections section and every wikilink
    removed so a link already written cannot leak the answer."""
    if not rel:
        return ""
    text = (vault_root() / rel).read_text(errors="ignore")
    text = re.split(r"^## Transcript", text, flags=re.MULTILINE)[0]
    text = re.sub(r"^## Connections\s*\n.*?(?=^## |\Z)", "", text, flags=re.DOTALL | re.MULTILINE)
    text = re.sub(r"!?\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", lambda m: m.group(2) or m.group(1), text)
    return text.strip()


def add_cosines(data: dict) -> dict:
    """Note-to-note cosine from today's store vectors, one ruler for every
    pair. The logged cosine was query-to-target and exists for 39 pairs only."""
    import numpy as np

    sys.path.insert(0, str(ROOT))
    from ytk import store

    cache: dict[str, np.ndarray | None] = {}

    def vec(rel: str | None) -> np.ndarray | None:
        if rel is None:
            return None
        if rel not in cache:
            # YouTube notes are indexed by video id in the videos collection, not by path.
            head = (vault_root() / rel).read_text(errors="ignore")[:600]
            m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", head)
            v = store.note_vector(
                source_path=str(vault_root() / rel), video_id=m.group(1) if m else None
            )
            cache[rel] = None if v is None else np.asarray(v, dtype=float)
        return cache[rel]

    missing = 0
    for it in data["items"]:
        a = vec(it["note_path"])
        for p in it["pairs"]:
            b = vec(p["target_path"])
            if a is None or b is None:
                p["cosine_today"] = None
                missing += 1
            else:
                p["cosine_today"] = round(float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b))), 4)
    data["cosine_missing"] = missing
    return data


def write_sheets(data: dict, outdir: Path, seed: int = 56, chunk: int = 9) -> None:
    """Blind judge sheets: pairs in a seeded shuffle, both notes' bodies,
    no shipped decision, no ruling, no cosine. Each reader gets the same
    order so grades align by pair id."""
    import random

    pairs = [(it, p) for it in data["items"] for p in it["pairs"]]
    order = list(range(len(pairs)))
    random.Random(seed).shuffle(order)
    outdir.mkdir(parents=True, exist_ok=True)
    for f in outdir.glob("chunk-*.md"):
        f.unlink()
    key = []
    for ci in range(0, len(order), chunk):
        lines = []
        for k in order[ci : ci + chunk]:
            it, p = pairs[k]
            pid = f"P{k:02d}"
            key.append({"pid": pid, "item_id": it["item_id"], "target": p["target"]})
            lines += [
                f"# {pid}",
                "",
                f"## NEW NOTE: {it['title']}",
                "",
                body(it["note_path"]),
                "",
                f"## CANDIDATE: {p['target_title']}",
                "",
                body(p["target_path"]),
                "",
                "---",
                "",
            ]
        (outdir / f"chunk-{ci // chunk:02d}.md").write_text("\n".join(lines))
    (outdir / "key.json").write_text(json.dumps(key, indent=1))
    print(f"sheets: {len(pairs)} pairs in {(len(order) + chunk - 1) // chunk} chunks at {outdir}")


def _plot_imports():
    sys.path.insert(0, str(ROOT / "scripts"))
    import plot_assets as pa

    pa.use_house_font()
    return pa


def commit_sha() -> str:
    import subprocess

    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT
    ).stdout.strip()


OWNER_COLOR = {"approved": "GOLD", "struck": "RED", "pending": "BLUE"}


def draw01(data: dict) -> Path:
    """The record before any arm: every pair the linker has seen, by today's
    note-to-note cosine, coloured by what shipped and what the owner ruled."""
    import numpy as np

    pa = _plot_imports()
    items = sorted(data["items"], key=lambda it: it["at"])
    rows = [(i, it, p) for i, it in enumerate(items) for p in it["pairs"]]
    n_pairs = len(rows)
    argued = [p["cosine_today"] for _, _, p in rows if p["shipped"] == "argued"]
    declined = [p["cosine_today"] for _, _, p in rows if p["shipped"] == "declined"]
    owner = {k: [p["cosine_today"] for _, _, p in rows if p["owner"] == k] for k in OWNER_COLOR}
    ruled = len(owner["approved"]) + len(owner["struck"])

    fig, top = pa.figure(
        16,
        10,
        1,
        "section 56 · the connect slot · the record before any arm",
        "Every candidate the linker has argued or declined, placed by how close the two notes sit today",
        meta=(
            f"{len(items)} items, {n_pairs} candidate pairs from the ledger's connect rows · shipped decision: "
            f"claude-sonnet-5 via the Agent SDK, adaptive thinking (probe: 0 to 117 thinking tokens per call) · "
            f"argued {len(argued)}, declined {len(declined)} (declined identities logged since 2026-10-24) · owner: "
            f"approved {len(owner['approved'])}, struck {len(owner['struck'])}, pending {len(owner['pending'])} · "
            f"cosine: note vector to note vector in today's store · commit {commit_sha()}"
        ),
    )
    color = {"GOLD": pa.GOLD, "RED": pa.RED, "BLUE": pa.BLUE}
    xlo, xhi = 0.30, 0.95
    gutter = 0.02  # row labels live inside the panel, left of this rule, so the frame holds them
    bottom = 0.075
    h = top - bottom - 0.03

    ax = fig.add_axes([pa.MARGIN + 0.015, bottom, 0.62, h])
    pa.style_axes(ax)
    for i, it in enumerate(items):
        ax.plot([xlo, xhi], [i, i], color=pa.FRAME, lw=0.6, zorder=1)
        ax.text(
            gutter + 0.005,
            i,
            f"{it['at'][5:10]}  {it['title'][:44]}",
            color=pa.TEXT,
            fontsize=8.4,
            va="center",
            ha="left",
        )
    ax.plot([xlo, xlo], [-0.5, len(items) - 0.5], color=pa.FRAME, lw=1.0, zorder=2)
    for i, _it, p in rows:
        x = p["cosine_today"]
        if p["shipped"] == "declined":
            ax.scatter(x, i, s=70, facecolors="none", edgecolors=pa.MUTED, lw=1.3, zorder=3)
        else:
            ax.scatter(x, i, s=80, color=color[OWNER_COLOR[p["owner"]]], zorder=4)
    ax.set_yticks([])
    ax.set_xlim(gutter, xhi)
    ax.set_xticks([0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9])
    ax.set_ylim(len(items) - 0.5, -0.5)
    ax.set_xlabel(
        "cosine between the new note and the candidate (today's vectors)",
        color=pa.MUTED,
        fontsize=9,
    )
    ax.tick_params(axis="x", colors=pa.MUTED, labelsize=8.5)
    pa.panel_title(
        ax,
        "one row per landed note, one mark per candidate · filled = argued (gold approved, red struck, blue awaiting ruling) · hollow = declined",
        width=80,
    )

    ax2 = fig.add_axes([pa.MARGIN + 0.675, bottom, 1 - 2 * pa.MARGIN - 0.675, h])
    pa.style_axes(ax2)
    strips = [
        ("argued by Sonnet", argued, pa.TEXT, True),
        ("declined by Sonnet", declined, pa.MUTED, False),
        ("approved by owner", owner["approved"], pa.GOLD, True),
        ("struck by owner", owner["struck"], pa.RED, True),
        ("awaiting ruling", owner["pending"], pa.BLUE, True),
    ]
    rng = np.random.default_rng(56)
    for k, (label, xs, col, filled) in enumerate(strips):
        y = k + rng.uniform(-0.22, 0.22, len(xs))
        if filled:
            ax2.scatter(xs, y, s=46, color=col, alpha=0.85, zorder=3)
        else:
            ax2.scatter(xs, y, s=46, facecolors="none", edgecolors=col, lw=1.2, zorder=3)
        med = float(np.median(xs))
        ax2.plot([med, med], [k - 0.42, k + 0.42], color=col, lw=2.4, zorder=4)
        ax2.text(
            xhi - 0.012,
            k - 0.36,
            f"n={len(xs)}  median {med:.2f}",
            color=col,
            fontsize=8.5,
            ha="right",
            va="center",
        )
        ax2.text(xlo + 0.012, k - 0.36, label, color=col, fontsize=9.2, ha="left", va="center")
    ax2.set_yticks([])
    ax2.set_xlim(xlo, xhi)
    ax2.set_ylim(len(strips) - 0.5, -0.5)
    ax2.set_xlabel("same cosine axis", color=pa.MUTED, fontsize=9)
    ax2.tick_params(axis="x", colors=pa.MUTED, labelsize=8.5)
    pa.panel_title(
        ax2,
        "the same marks pooled: does similarity alone explain who got argued, and who got kept?",
        width=52,
    )

    pa.verdict(
        fig,
        f"{len(argued)}/{n_pairs} argued, {len(owner['approved'])}/{ruled} kept by the owner; "
        f"declined and argued overlap on cosine (medians {np.median(declined):.2f} vs {np.median(argued):.2f}), so the decision is not a threshold",
    )
    pa.frame_panels(fig)
    out = OUTDIR / "01-the-record.png"
    fig.savefig(out, dpi=pa.DPI, facecolor=pa.BG)
    return out


def summarise(data: dict) -> None:
    pairs = [(it, p) for it in data["items"] for p in it["pairs"]]
    n_items = len(data["items"])
    shipped = {"argued": 0, "declined": 0}
    owner: dict[str, int] = {}
    missing_target = missing_note = 0
    for it, p in pairs:
        shipped[p["shipped"]] += 1
        owner[p["owner"]] = owner.get(p["owner"], 0) + 1
        missing_target += p["target_path"] is None
        missing_note += it["note_path"] is None
    print(f"items {n_items}  pairs {len(pairs)}  shipped {shipped}  owner {owner}")
    print(f"targets without a note today {missing_target}; items without a note {missing_note}")
    for it in data["items"]:
        print(
            f"  {it['item_id']:>4} {it['at'][:10]} {len(it['pairs'])} cands "
            f"{sum(p['shipped'] == 'argued' for p in it['pairs'])} argued  ruling={it['ruling']}  "
            f"note={'ok' if it['note_path'] else 'MISSING'}  thesis={'ok' if it['thesis'] else 'MISSING'}  {it['title'][:50]}"
        )


SONNET_ARMS = OUTDIR / "sonnet-arms.json"
JEV_ARMS = OUTDIR / "jev-arms.json"
# Registered arm settings; thinking is the SDK's `thinking` option, effort its `effort`.
SONNET_CONFIGS: dict[str, dict] = {
    "A1": {},
    "A2": {"thinking": {"type": "disabled"}},
    "A3": {"thinking": {"type": "enabled", "budget_tokens": 16000}, "effort": "high"},
}
CONCURRENCY = 4
SPLIT_CHARS = 80_000
STABILITY_N = 20
SEED = 56
ASK = "Should `new_note` carry a link to `candidates.{k}`?"
ASK_TRUE = (
    "A reader of the new note would want the candidate: the same specific thing, event, paper, "
    "person or claim, or a claim that directly extends or contradicts it."
)
ASK_FALSE = "The same broad topic only, a passing mention, or nothing related."


def pair_key(item: dict, p: dict) -> str:
    return f"{item['item_id']}:{p['target']}"


def shipped_prompt(item: dict) -> str:
    """The user prompt exactly as `ytk.connect._argue` builds it; a candidate
    whose matched-on field the ledger did not log says so."""
    lines = [f"New note thesis: {item['thesis']}", f"Summary: {item['summary']}"]
    if item["take"] and item["take"].strip():
        lines.append(f"Owner's take: {item['take'].strip()}")
    lines += ["", "Candidates:"]
    for i, p in enumerate(item["pairs"], start=1):
        via = p["via"] or "not logged"
        lines.append(
            f"{i}. target={p['target']} · {p['target_title']} · matched on: {via} · thesis: {p['target_thesis']}"
        )
    return "\n".join(lines)


async def _sonnet_one(item: dict, arm: str, cfg: dict, sem) -> dict:
    import time

    from claude_agent_sdk import ClaudeSDKClient, ResultMessage

    from ytk import sdk
    from ytk.connect import _ARGUE_SCHEMA, _ARGUE_SYSTEM, CONNECT_MODEL

    async with sem:
        opts = sdk._build_options(_ARGUE_SYSTEM, _ARGUE_SCHEMA, [], 4, CONNECT_MODEL)
        for k, v in cfg.items():
            setattr(opts, k, v)
        t0 = time.perf_counter()
        async with ClaudeSDKClient(options=opts) as client:
            await client.query(shipped_prompt(item))
            async for msg in client.receive_response():
                if isinstance(msg, ResultMessage):
                    usage = msg.usage or {}
                    out = msg.structured_output or {}
                    targets = {p["target"] for p in item["pairs"]}
                    links = [link for link in out.get("links", []) if link.get("target") in targets]
                    return {
                        "arm": arm,
                        "item_id": item["item_id"],
                        "yes": sorted({link["target"] for link in links}),
                        "arguments": {link["target"]: link.get("argument") for link in links},
                        "wall_s": round(time.perf_counter() - t0, 2),
                        "api_ms": getattr(msg, "duration_api_ms", None),
                        "output_tokens": usage.get("output_tokens"),
                        "thinking_tokens": (usage.get("output_tokens_details") or {}).get(
                            "thinking_tokens"
                        ),
                        "is_error": bool(msg.is_error),
                    }
    raise RuntimeError(f"no result for item {item['item_id']} arm {arm}")


def run_sonnet_arms(data: dict) -> None:
    import asyncio

    sys.path.insert(0, str(ROOT))
    partial = OUTDIR / "sonnet-arms.partial.jsonl"
    done: set[tuple[str, int]] = set()
    rows: list[dict] = []
    if partial.exists():
        for line in partial.read_text().splitlines():
            r = json.loads(line)
            rows.append(r)
            done.add((r["arm"], r["item_id"]))

    async def main() -> None:
        sem = asyncio.Semaphore(CONCURRENCY)
        tasks = [
            _sonnet_one(it, arm, cfg, sem)
            for arm, cfg in SONNET_CONFIGS.items()
            for it in data["items"]
            if (arm, it["item_id"]) not in done
        ]
        with partial.open("a") as fh:
            for coro in asyncio.as_completed(tasks):
                r = await coro
                rows.append(r)
                fh.write(json.dumps(r) + "\n")
                fh.flush()
                print(
                    f"{r['arm']} item {r['item_id']}: yes {len(r['yes'])}  think {r['thinking_tokens']}  {r['wall_s']} s",
                    flush=True,
                )

    asyncio.run(main())
    SONNET_ARMS.write_text(json.dumps({"configs": SONNET_CONFIGS, "rows": rows}, indent=1))
    print(f"sonnet arms: {len(rows)} rows -> {SONNET_ARMS}")


def _jev_requests(item: dict, level: str) -> list[tuple[dict, dict]]:
    """(state, questions) for one landed note at one information level.
    Nouls are independent, so a request over SPLIT_CHARS splits by candidate."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from jev_client import noul

    if level == "J1":
        new = {"title": item["title"], "body": body(item["note_path"])}
        cands = {
            f"c{i:02d}": {"title": p["target_title"], "body": body(p["target_path"])}
            for i, p in enumerate(item["pairs"], start=1)
        }
    else:
        new = {"title": item["title"], "thesis": item["thesis"], "summary": item["summary"]}
        cands = {
            f"c{i:02d}": {"title": p["target_title"], "thesis": p["target_thesis"]}
            for i, p in enumerate(item["pairs"], start=1)
        }
    keys = list(cands)
    groups = [keys]
    while any(
        len(json.dumps({"new_note": new, "candidates": {k: cands[k] for k in g}})) > SPLIT_CHARS
        for g in groups
    ):
        groups = [
            h
            for g in groups
            for h in ((g[: len(g) // 2], g[len(g) // 2 :]) if len(g) > 1 else (g,))
        ]
        if all(len(g) == 1 for g in groups):
            break
    out = []
    for g in groups:
        state = {"new_note": new, "candidates": {k: cands[k] for k in g}}
        questions = {k: noul(ASK.format(k=k), ASK_TRUE, ASK_FALSE) for k in g}
        out.append((state, questions))
    return out


def _jev_item(item: dict, level: str, tag: str) -> dict:
    sys.path.insert(0, str(ROOT / "scripts"))
    from jev_client import system_one

    probs: dict[str, float] = {}
    wall = 0.0
    tokens = 0
    n_req = 0
    for state, questions in _jev_requests(item, level):
        reply = system_one(state, questions, tag=tag)
        wall += reply.latency_s
        tokens += reply.input_tokens or 0
        n_req += 1
        for k, ans in reply.answers.items():
            probs[k] = float(ans["noul"])
    keys = [f"c{i:02d}" for i in range(1, len(item["pairs"]) + 1)]
    return {
        "item_id": item["item_id"],
        "p": {pair_key(item, p): probs[k] for k, p in zip(keys, item["pairs"], strict=True)},
        "wall_s": round(wall, 3),
        "input_tokens": tokens,
        "requests": n_req,
    }


def run_jev_arms(data: dict) -> None:
    import random

    out: dict = {"J1": [], "J2": [], "stability": []}
    for level in ("J1", "J2"):
        for it in data["items"]:
            r = _jev_item(it, level, tag=f"jev56-{level.lower()}")
            out[level].append(r)
            print(
                f"{level} item {it['item_id']}: {r['requests']} req  {r['input_tokens']} tok  {r['wall_s']} s",
                flush=True,
            )
    # Stability: 20 pairs drawn by seed, their landed notes re-sent once at J1.
    pairs = [(it, p) for it in data["items"] for p in it["pairs"]]
    chosen = random.Random(SEED).sample(range(len(pairs)), STABILITY_N)
    chosen_keys = {pair_key(*pairs[i]) for i in chosen}
    first = {k: v for r in out["J1"] for k, v in r["p"].items()}
    for it in data["items"]:
        keys = [pair_key(it, p) for p in it["pairs"] if pair_key(it, p) in chosen_keys]
        if not keys:
            continue
        r = _jev_item(it, "J1", tag="jev56-stab")
        for k in keys:
            out["stability"].append({"key": k, "p1": first[k], "p2": r["p"][k]})
    JEV_ARMS.write_text(json.dumps(out, indent=1))
    flips = sum((a["p1"] >= 0.5) != (a["p2"] >= 0.5) for a in out["stability"])
    print(
        f"jev arms -> {JEV_ARMS}; stability decisions unchanged {STABILITY_N - flips}/{STABILITY_N}"
    )


SCORES = OUTDIR / "scores.json"
JUDGED = OUTDIR / "judged-pairs.json"
N_BOOT = 1000
BARS = {
    "B1_margin_pairs": 4,
    "B1_interval_floor": -0.05,
    "B2_approved": 37,
    "B2_struck": 2,
    "B4_wall_s": 1.0,
    "stability": 19,
}


def _auc(scores: list[float], truth: list[bool]) -> float:
    """Rank AUC: P(score of a positive > score of a negative), ties half."""
    pos = [s for s, t in zip(scores, truth, strict=True) if t]
    neg = [s for s, t in zip(scores, truth, strict=True) if not t]
    if not pos or not neg:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def merge_judges(judge_dir: Path) -> dict:
    key = {k["pid"]: k for k in json.loads((judge_dir / "key.json").read_text())}
    readers = {}
    for f in sorted(judge_dir.glob("judge-*.json")):
        readers[f.stem[-1]] = json.loads(f.read_text())
    out = {}
    for pid, k in key.items():
        grades = {r: int(g[pid]["grade"]) for r, g in readers.items() if pid in g}
        whys = {r: g[pid].get("why") for r, g in readers.items() if pid in g}
        gs = sorted(grades.values())
        out[f"{k['item_id']}:{k['target']}"] = {
            "pid": pid,
            "grades": grades,
            "why": whys,
            "median": gs[len(gs) // 2] if gs else None,
        }
    return {"readers": sorted(readers), "pairs": out}


def _agreement(judged: dict) -> dict:
    import itertools

    readers = judged["readers"]
    out = {}
    for a, b in itertools.combinations(readers, 2):
        both = [
            (v["grades"][a], v["grades"][b])
            for v in judged["pairs"].values()
            if a in v["grades"] and b in v["grades"]
        ]
        out[f"{a}{b}"] = {
            "n": len(both),
            "exact": round(sum(x == y for x, y in both) / len(both), 3),
            "within1": round(sum(abs(x - y) <= 1 for x, y in both) / len(both), 3),
        }
    return out


def score() -> dict:
    import random

    import numpy as np

    data = json.loads(PAIRS.read_text())
    jev = json.loads(JEV_ARMS.read_text())
    sonnet = json.loads(SONNET_ARMS.read_text())
    judged = json.loads(JUDGED.read_text())
    rows = [(it, p, pair_key(it, p)) for it in data["items"] for p in it["pairs"]]
    keys = [k for _, _, k in rows]
    truth = [judged["pairs"][k]["median"] >= 2 for k in keys]
    grade = [judged["pairs"][k]["median"] for k in keys]
    cosine = [p["cosine_today"] for _, p, _ in rows]
    P = {lvl: {k: v for r in jev[lvl] for k, v in r["p"].items()} for lvl in ("J1", "J2")}
    yes_by_arm: dict[str, dict[str, bool]] = {
        "A0": {k: p["shipped"] == "argued" for _, p, k in rows}
    }
    for arm in SONNET_CONFIGS:
        yes = {}
        for r in sonnet["rows"]:
            if r["arm"] != arm:
                continue
            it = next(i for i in data["items"] if i["item_id"] == r["item_id"])
            for p in it["pairs"]:
                yes[pair_key(it, p)] = p["target"] in r["yes"]
        yes_by_arm[arm] = yes
    for lvl in ("J1", "J2"):
        yes_by_arm[lvl] = {k: P[lvl][k] >= 0.5 for k in keys}

    def metrics(yes: dict[str, bool]) -> dict:
        y = [yes[k] for k in keys]
        tp = sum(a and b for a, b in zip(y, truth, strict=True))
        fp = sum(a and not b for a, b in zip(y, truth, strict=True))
        fn = sum(b and not a for a, b in zip(y, truth, strict=True))
        acc = sum(a == b for a, b in zip(y, truth, strict=True)) / len(keys)
        prec = tp / (tp + fp) if tp + fp else float("nan")
        rec = tp / (tp + fn) if tp + fn else float("nan")
        approved = [yes[k] for _, p, k in rows if p["owner"] == "approved"]
        struck = [not yes[k] for _, p, k in rows if p["owner"] == "struck"]
        return {
            "yes": sum(y),
            "accuracy": round(acc, 4),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0,
            "approved_kept": sum(approved),
            "struck_dropped": sum(struck),
            "agree_with_shipped": sum(yes[k] == yes_by_arm["A0"][k] for k in keys),
        }

    arms = {arm: metrics(yes) for arm, yes in yes_by_arm.items()}
    for lvl in ("J1", "J2"):
        arms[lvl]["auc"] = round(_auc([P[lvl][k] for k in keys], truth), 4)
        walls = [r["wall_s"] for r in jev[lvl]]
        arms[lvl]["wall_median_s"] = round(float(np.median(walls)), 3)
        arms[lvl]["wall_max_s"] = round(max(walls), 3)
        arms[lvl]["input_tokens"] = sum(r["input_tokens"] for r in jev[lvl])
    for arm in SONNET_CONFIGS:
        rs = [r for r in sonnet["rows"] if r["arm"] == arm]
        think = [r["thinking_tokens"] or 0 for r in rs]
        arms[arm]["thinking_tokens_median"] = float(np.median(think))
        arms[arm]["thinking_tokens_total"] = int(sum(think))
        arms[arm]["api_ms_median"] = float(np.median([r["api_ms"] or 0 for r in rs]))
        arms[arm]["wall_median_s"] = float(np.median([r["wall_s"] for r in rs]))
        arms[arm]["errors"] = sum(r["is_error"] for r in rs)

    # Nulls. Cosine rule: best accuracy threshold, fitted on the answers (optimistic).
    best = max(
        (
            (sum((c >= t) == tr for c, tr in zip(cosine, truth, strict=True)) / len(keys), t)
            for t in sorted(set(cosine))
        ),
        key=lambda x: x[0],
    )
    cos_null = {
        "threshold": best[1],
        "accuracy": round(best[0], 4),
        "auc": round(_auc(cosine, truth), 4),
    }
    rng = random.Random(SEED)
    rate_null = {}
    for arm, m in arms.items():
        rate = m["yes"] / len(keys)
        accs = []
        for _ in range(N_BOOT):
            draw = [rng.random() < rate for _ in keys]
            accs.append(sum(a == b for a, b in zip(draw, truth, strict=True)) / len(keys))
        accs.sort()
        rate_null[arm] = {
            "rate": round(rate, 3),
            "p95": round(accs[int(0.95 * N_BOOT)], 4),
            "mean": round(sum(accs) / N_BOOT, 4),
            "p05": round(accs[int(0.05 * N_BOOT)], 4),
        }

    # Paired bootstrap over pairs on per-pair correctness differences and on AUC.
    def correct(arm: str) -> list[int]:
        return [int(yes_by_arm[arm][k] == t) for k, t in zip(keys, truth, strict=True)]

    def boot_diff(a: list[int], b: list[int]) -> dict:
        r = random.Random(SEED)
        n = len(a)
        diffs = []
        for _ in range(N_BOOT):
            idx = [r.randrange(n) for _ in range(n)]
            diffs.append(sum(a[i] - b[i] for i in idx) / n)
        diffs.sort()
        return {
            "mean": round(sum(diffs) / N_BOOT, 4),
            "lo": round(diffs[int(0.025 * N_BOOT)], 4),
            "hi": round(diffs[int(0.975 * N_BOOT)], 4),
        }

    paired = {
        "J1_minus_A1": boot_diff(correct("J1"), correct("A1")),
        "J2_minus_A1": boot_diff(correct("J2"), correct("A1")),
        "A1_minus_A2": boot_diff(correct("A1"), correct("A2")),
        "A3_minus_A2": boot_diff(correct("A3"), correct("A2")),
    }
    r = random.Random(SEED)
    auc_diffs = []
    j1 = [P["J1"][k] for k in keys]
    for _ in range(N_BOOT):
        idx = [r.randrange(len(keys)) for _ in range(len(keys))]
        tr = [truth[i] for i in idx]
        auc_diffs.append(_auc([j1[i] for i in idx], tr) - _auc([cosine[i] for i in idx], tr))
    auc_diffs = [x for x in auc_diffs if x == x]
    auc_diffs.sort()
    paired["auc_J1_minus_cosine"] = {
        "mean": round(sum(auc_diffs) / len(auc_diffs), 4),
        "lo": round(auc_diffs[int(0.025 * len(auc_diffs))], 4),
        "hi": round(auc_diffs[int(0.975 * len(auc_diffs))], 4),
    }

    flips = sum((a["p1"] >= 0.5) != (a["p2"] >= 0.5) for a in jev["stability"])
    stability = {
        "n": len(jev["stability"]),
        "unchanged": len(jev["stability"]) - flips,
        "dp_median": round(float(np.median([abs(a["p1"] - a["p2"]) for a in jev["stability"]])), 4),
        "dp_max": round(max(abs(a["p1"] - a["p2"]) for a in jev["stability"]), 4),
    }

    j1m, a1m = arms["J1"], arms["A1"]
    verdict = {
        "B1": (j1m["accuracy"] * len(keys) >= a1m["accuracy"] * len(keys) - BARS["B1_margin_pairs"])
        and paired["J1_minus_A1"]["hi"] >= BARS["B1_interval_floor"],
        "B2": j1m["approved_kept"] >= BARS["B2_approved"]
        and j1m["struck_dropped"] >= BARS["B2_struck"],
        "B3": paired["auc_J1_minus_cosine"]["lo"] > 0 and j1m["accuracy"] > rate_null["J1"]["p95"],
        "B4": j1m["wall_median_s"] <= BARS["B4_wall_s"],
        "stability": stability["unchanged"] >= BARS["stability"],
    }
    verdict["pass"] = all(verdict.values())
    # Post hoc, not registered: the J1 threshold that would have kept the most approved links at B2's bar.
    approved_p = sorted(P["J1"][k] for _, p, k in rows if p["owner"] == "approved")
    post_hoc = {
        "threshold_keeping_37_approved": approved_p[len(approved_p) - BARS["B2_approved"]]
        if len(approved_p) >= BARS["B2_approved"]
        else None
    }
    if post_hoc["threshold_keeping_37_approved"] is not None:
        t = post_hoc["threshold_keeping_37_approved"]
        y = {k: P["J1"][k] >= t for k in keys}
        post_hoc["accuracy_at_that_threshold"] = metrics(y)["accuracy"]
        post_hoc["struck_dropped_at_that_threshold"] = metrics(y)["struck_dropped"]

    out = {
        "n_pairs": len(keys),
        "link_worthy": sum(truth),
        "grade_counts": {g: grade.count(g) for g in range(4)},
        "reader_agreement": _agreement(judged),
        "arms": arms,
        "cosine_null": cos_null,
        "rate_null": rate_null,
        "paired": paired,
        "stability": stability,
        "bars": BARS,
        "verdict": verdict,
        "post_hoc": post_hoc,
        "commit": commit_sha(),
    }
    SCORES.write_text(json.dumps(out, indent=1))
    return out


ARM_LABEL = {
    "A0": "A0 shipped record",
    "A1": "A1 Sonnet, adaptive thinking",
    "A2": "A2 Sonnet, thinking off",
    "A3": "A3 Sonnet, thinking forced",
    "J1": "J1 Jev Noul, both bodies",
    "J2": "J2 Jev Noul, thesis level",
}


def draw02() -> Path:
    import numpy as np

    pa = _plot_imports()
    data = json.loads(PAIRS.read_text())
    jev = json.loads(JEV_ARMS.read_text())
    judged = json.loads(JUDGED.read_text())
    s = json.loads(SCORES.read_text())
    rows = [(it, p, pair_key(it, p)) for it in data["items"] for p in it["pairs"]]
    P1 = {k: v for r in jev["J1"] for k, v in r["p"].items()}
    v = s["verdict"]
    j1, a1 = s["arms"]["J1"], s["arms"]["A1"]
    fig, top = pa.figure(
        16,
        10,
        2,
        "section 56 · the connect slot · result",
        "Jev's probability on every pair against three blind readers, and six arms against the same ruler",
        meta=(
            f"{s['n_pairs']} pairs, {s['link_worthy']} link-worthy (median grade >= 2 of three readers; grades "
            + ", ".join(f"{g}: {n}" for g, n in s["grade_counts"].items())
            + ") · reader agreement within one grade "
            + ", ".join(f"{k} {a['within1']:.2f}" for k, a in s["reader_agreement"].items())
            + f" · J1 accuracy {j1['accuracy']:.3f} vs A1 {a1['accuracy']:.3f}, paired diff [{s['paired']['J1_minus_A1']['lo']:+.3f}, {s['paired']['J1_minus_A1']['hi']:+.3f}] · "
            f"J1 AUC {j1['auc']:.3f} vs cosine {s['cosine_null']['auc']:.3f} · J1 kept {j1['approved_kept']}/39 approved, dropped {j1['struck_dropped']}/3 struck · "
            f"median {j1['wall_median_s']:.2f} s per landed note · stability {s['stability']['unchanged']}/{s['stability']['n']} · jev-1.14.0 · commit {s['commit']}"
        ),
    )
    bottom = 0.075
    h = top - bottom - 0.03
    color = {"approved": pa.GOLD, "struck": pa.RED, "pending": pa.BLUE}
    rng = np.random.default_rng(SEED)

    ax = fig.add_axes([pa.MARGIN + 0.015, bottom, 0.40, h])
    pa.style_axes(ax)
    for g in range(4):
        ax.plot([0, 1], [g, g], color=pa.FRAME, lw=0.6, zorder=1)
    for _it, p, k in rows:
        g = judged["pairs"][k]["median"] + rng.uniform(-0.28, 0.28)
        x = P1[k]
        if p["shipped"] == "declined":
            ax.scatter(x, g, s=74, facecolors="none", edgecolors=pa.MUTED, lw=1.3, zorder=3)
        else:
            ax.scatter(x, g, s=84, color=color[p["owner"]], zorder=4)
    ax.axvline(0.5, color=pa.RED, lw=1.6, zorder=5)
    ax.text(
        0.505, 3.42, "registered threshold 0.5", color=pa.RED, fontsize=8.5, ha="left", va="center"
    )
    ax.axhline(1.5, color=pa.DIM, lw=1.0, ls="--", zorder=2)
    ax.text(0.99, 1.5, "link-worthy above", color=pa.MUTED, fontsize=8.5, ha="right", va="bottom")
    ph = s["post_hoc"].get("threshold_keeping_37_approved")
    if ph is not None:
        ax.axvline(ph, color=pa.DIM, lw=1.4, ls="--", zorder=2)
        ax.text(
            ph + 0.005,
            -0.42,
            f"post hoc, not registered: {ph:.2f} keeps 37/39",
            color=pa.MUTED,
            fontsize=8.3,
            ha="left",
            va="center",
        )
    for g, lab in enumerate(["0 unrelated", "1 topic only", "2 worth a link", "3 same thing"]):
        ax.text(0.005, g + 0.36, lab, color=pa.TEXT, fontsize=9, ha="left", va="center")
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.5, 3.6)
    ax.set_yticks([])
    ax.set_xlabel(
        "J1: P(the new note should carry the link), both bodies in the state",
        color=pa.MUTED,
        fontsize=9,
    )
    ax.tick_params(axis="x", colors=pa.MUTED, labelsize=8.5)
    pa.panel_title(
        ax,
        "every pair: Jev's probability against the readers' median grade · filled = argued by the shipped model (gold approved, red struck, blue pending) · hollow = declined",
        width=70,
    )

    arms = ["A0", "A1", "A2", "A3", "J1", "J2"]
    ax2 = fig.add_axes([pa.MARGIN + 0.47, bottom, 0.26, h])
    pa.style_axes(ax2)
    for i, arm in enumerate(arms):
        m = s["arms"][arm]
        nl = s["rate_null"][arm]
        ax2.barh(i, nl["p95"] - nl["p05"], left=nl["p05"], height=0.62, color=pa.DIM, zorder=2)
        col = pa.GOLD if arm.startswith("J") else pa.TEXT
        ax2.scatter(m["accuracy"], i, s=150, color=col, zorder=5, edgecolors=pa.BG, lw=0.8)
        ax2.text(0.305, i - 0.36, ARM_LABEL[arm], color=col, fontsize=9, ha="left", va="center")
        ax2.text(
            0.995, i + 0.02, f"{m['accuracy']:.3f}", color=col, fontsize=9, ha="right", va="center"
        )
    ax2.axvline(s["cosine_null"]["accuracy"], color=pa.DIM, lw=1.4, ls="--", zorder=3)
    ax2.text(
        s["cosine_null"]["accuracy"] + 0.006,
        len(arms) - 0.55,
        f"best cosine rule {s['cosine_null']['accuracy']:.2f}",
        color=pa.MUTED,
        fontsize=8.3,
        ha="left",
        va="center",
    )
    ax2.axvline(a1["accuracy"], color=pa.TEXT, lw=0.8, zorder=3)
    ax2.set_xlim(0.3, 1.0)
    ax2.set_ylim(len(arms) - 0.4, -0.7)
    ax2.set_yticks([])
    ax2.set_xlabel(
        "accuracy against the blind ruler (link-worthy yes/no)", color=pa.MUTED, fontsize=9
    )
    ax2.tick_params(axis="x", colors=pa.MUTED, labelsize=8.5)
    pa.panel_title(
        ax2,
        "six arms on one ruler · grey band = that arm's yes-rate drawn at random, 5th to 95th · dashed = best cosine threshold, fitted on the answers",
        width=52,
    )

    ax3 = fig.add_axes([pa.MARGIN + 0.775, bottom, 1 - 2 * pa.MARGIN - 0.775, h])
    pa.style_axes(ax3)
    for i, arm in enumerate(arms):
        m = s["arms"][arm]
        col = pa.GOLD if arm.startswith("J") else pa.TEXT
        ax3.barh(
            i,
            m["approved_kept"],
            height=0.62,
            color=col,
            alpha=0.9 if arm.startswith("J") else 0.55,
            zorder=3,
        )
        ax3.text(0.6, i - 0.36, ARM_LABEL[arm], color=col, fontsize=9, ha="left", va="center")
        inside = m["approved_kept"] >= 20
        ax3.text(
            m["approved_kept"] - 0.6 if inside else m["approved_kept"] + 0.6,
            i + 0.02,
            f"{m['approved_kept']}/39 kept, struck {m['struck_dropped']}/3",
            color=pa.BG if inside else col,
            fontsize=8.5,
            ha="right" if inside else "left",
            va="center",
            zorder=6,
        )
    ax3.axvline(BARS["B2_approved"], color=pa.RED, lw=1.6, zorder=5)
    ax3.text(
        BARS["B2_approved"] - 0.5,
        len(arms) - 0.55,
        f"B2 bar {BARS['B2_approved']}",
        color=pa.RED,
        fontsize=8.5,
        ha="right",
        va="center",
    )
    ax3.set_xlim(0, 40)
    ax3.set_ylim(len(arms) - 0.4, -0.7)
    ax3.set_yticks([])
    ax3.set_xlabel("owner-approved links the arm keeps (of 39)", color=pa.MUTED, fontsize=9)
    ax3.tick_params(axis="x", colors=pa.MUTED, labelsize=8.5)
    pa.panel_title(ax3, "the owner's ruler: approved links that survive each arm", width=40)

    failed = [b for b in ("B1", "B2", "B3", "B4", "stability") if not v[b]]
    pa.verdict(
        fig,
        (
            "registered pass: Jev takes the decision"
            if v["pass"]
            else f"registered loss on {', '.join(failed)}"
        )
        + f" · J1 yes {j1['yes']}/81 vs shipped 66/81; AUC {j1['auc']:.2f} vs cosine {s['cosine_null']['auc']:.2f}",
    )
    pa.frame_panels(fig)
    out = OUTDIR / "02-arms-on-one-ruler.png"
    fig.savefig(out, dpi=pa.DPI, facecolor=pa.BG)
    return out


def draw03() -> Path:
    """The thinking question: tokens actually spent per call, and whether the
    three Sonnet arms decide differently on the same pairs."""
    import numpy as np

    pa = _plot_imports()
    data = json.loads(PAIRS.read_text())
    sonnet = json.loads(SONNET_ARMS.read_text())
    judged = json.loads(JUDGED.read_text())
    s = json.loads(SCORES.read_text())
    rows = [(it, p, pair_key(it, p)) for it in data["items"] for p in it["pairs"]]
    truth = {k: judged["pairs"][k]["median"] >= 2 for _, _, k in rows}
    yes: dict[str, dict[str, bool]] = {}
    for arm in SONNET_CONFIGS:
        yes[arm] = {}
        for r in sonnet["rows"]:
            if r["arm"] != arm:
                continue
            it = next(i for i in data["items"] if i["item_id"] == r["item_id"])
            for p in it["pairs"]:
                yes[arm][pair_key(it, p)] = p["target"] in r["yes"]
    arms = ["A1", "A2", "A3"]
    fig, top = pa.figure(
        16,
        7.5,
        3,
        "section 56 · the connect slot · the thinking question",
        "Does letting Sonnet think change which candidates it links? Tokens spent per call, and the decisions compared pair by pair",
        meta=(
            "same prompt, same 29 landed notes, three SDK thinking settings · "
            + " · ".join(
                f"{ARM_LABEL[a]}: median {s['arms'][a]['thinking_tokens_median']:.0f} thinking tokens, accuracy {s['arms'][a]['accuracy']:.3f}"
                for a in arms
            )
            + f" · paired accuracy A3 - A2 [{s['paired']['A3_minus_A2']['lo']:+.3f}, {s['paired']['A3_minus_A2']['hi']:+.3f}], A1 - A2 [{s['paired']['A1_minus_A2']['lo']:+.3f}, {s['paired']['A1_minus_A2']['hi']:+.3f}] · commit {s['commit']}"
        ),
    )
    bottom = 0.11
    h = top - bottom - 0.03
    rng = np.random.default_rng(SEED)
    cols = {"A1": pa.TEXT, "A2": pa.CYAN, "A3": pa.PURPLE}

    ax = fig.add_axes([pa.MARGIN + 0.015, bottom, 0.42, h])
    pa.style_axes(ax)
    xmax = max((r["thinking_tokens"] or 0) for r in sonnet["rows"]) * 1.08 + 50
    for i, arm in enumerate(arms):
        tk = [(r["thinking_tokens"] or 0) for r in sonnet["rows"] if r["arm"] == arm]
        y = i + rng.uniform(-0.25, 0.25, len(tk))
        ax.scatter(tk, y, s=60, color=cols[arm], alpha=0.85, zorder=3)
        med = float(np.median(tk))
        ax.plot([med, med], [i - 0.28, i + 0.28], color=cols[arm], lw=2.4, zorder=4)
        ax.text(
            xmax * 0.99,
            i - 0.42,
            f"median {med:.0f}, max {max(tk)}",
            color=cols[arm],
            fontsize=8.5,
            ha="right",
            va="center",
        )
        ax.text(
            xmax * 0.01,
            i - 0.42,
            ARM_LABEL[arm],
            color=cols[arm],
            fontsize=9.2,
            ha="left",
            va="center",
        )
    ax.set_xlim(0, xmax)
    ax.set_ylim(len(arms) - 0.5, -0.6)
    ax.set_yticks([])
    ax.set_xlabel(
        "thinking tokens the model actually used, per connect call", color=pa.MUTED, fontsize=9
    )
    ax.tick_params(axis="x", colors=pa.MUTED, labelsize=8.5)
    pa.panel_title(ax, "what thinking cost: one mark per landed note", width=50)

    ax2 = fig.add_axes([pa.MARGIN + 0.48, bottom, 1 - 2 * pa.MARGIN - 0.48, h])
    pa.style_axes(ax2)
    keys = [k for _, _, k in rows]
    order = sorted(keys, key=lambda k: (truth[k], sum(yes[a][k] for a in arms)))
    for i, arm in enumerate(arms):
        for j, k in enumerate(order):
            y_ = yes[arm][k]
            right = y_ == truth[k]
            ax2.add_patch(
                __import__("matplotlib.patches", fromlist=["Rectangle"]).Rectangle(
                    (j, i),
                    1,
                    1,
                    facecolor=(cols[arm] if y_ else pa.PANEL),
                    edgecolor=(pa.FRAME if right else pa.RED),
                    lw=0.9 if right else 1.4,
                    alpha=0.9 if y_ else 1.0,
                )
            )
        ax2.text(
            -0.8, i + 0.5, ARM_LABEL[arm], color=cols[arm], fontsize=9, ha="right", va="center"
        )
    split = sum(not truth[k] for k in order)
    ax2.axvline(split, color=pa.MUTED, lw=1.2, ls="--")
    ax2.text(
        split / 2,
        len(arms) + 0.35,
        f"readers: not link-worthy ({split})",
        color=pa.MUTED,
        fontsize=8.8,
        ha="center",
        va="center",
    )
    ax2.text(
        split + (len(order) - split) / 2,
        len(arms) + 0.35,
        f"readers: link-worthy ({len(order) - split})",
        color=pa.MUTED,
        fontsize=8.8,
        ha="center",
        va="center",
    )
    disagree = sum(len({yes[a][k] for a in arms}) > 1 for k in keys)
    ax2.text(
        len(order) / 2,
        -0.55,
        f"pairs where the three settings disagree: {disagree} of {len(keys)}",
        color=pa.TEXT,
        fontsize=9.5,
        ha="center",
        va="center",
    )
    ax2.set_xlim(-14, len(order))
    ax2.set_ylim(len(arms) + 0.7, -1.0)
    ax2.set_xticks([])
    ax2.set_yticks([])
    pa.panel_title(
        ax2,
        "the same 81 pairs under each setting · filled = linked · red edge = disagrees with the readers",
        width=60,
    )

    pa.verdict(
        fig,
        f"three settings disagree on {disagree}/81 pairs; A3 - A2 accuracy interval [{s['paired']['A3_minus_A2']['lo']:+.2f}, {s['paired']['A3_minus_A2']['hi']:+.2f}]",
    )
    pa.frame_panels(fig)
    out = OUTDIR / "03-the-thinking-question.png"
    fig.savefig(out, dpi=pa.DPI, facecolor=pa.BG)
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "pairs"
    if cmd == "fig02":
        print(draw02())
    elif cmd == "fig03":
        print(draw03())
    elif cmd == "judged":
        JUDGED.write_text(json.dumps(merge_judges(Path(sys.argv[2])), indent=1))
        j = json.loads(JUDGED.read_text())
        print("readers", j["readers"], "pairs", len(j["pairs"]), "agreement", _agreement(j))
    elif cmd == "score":
        s = score()
        print(
            json.dumps(
                {
                    k: s[k]
                    for k in (
                        "link_worthy",
                        "grade_counts",
                        "reader_agreement",
                        "cosine_null",
                        "stability",
                        "verdict",
                        "post_hoc",
                    )
                },
                indent=1,
            )
        )
        for arm, m in s["arms"].items():
            print(
                arm,
                {
                    k: m[k]
                    for k in (
                        "yes",
                        "accuracy",
                        "precision",
                        "recall",
                        "f1",
                        "approved_kept",
                        "struck_dropped",
                    )
                    if k in m
                },
                m.get("auc"),
                m.get("thinking_tokens_median"),
            )
        print("paired", s["paired"])
    elif cmd == "sonnet":
        run_sonnet_arms(json.loads(PAIRS.read_text()))
    elif cmd == "jev":
        run_jev_arms(json.loads(PAIRS.read_text()))
    if cmd == "pairs":
        OUTDIR.mkdir(parents=True, exist_ok=True)
        data = add_cosines(collect_pairs())
        PAIRS.write_text(json.dumps(data, indent=1, ensure_ascii=False))
        summarise(data)
        print("cosine missing:", data["cosine_missing"])
    elif cmd == "fig01":
        print(draw01(json.loads(PAIRS.read_text())))
    elif cmd == "sheets":
        write_sheets(json.loads(PAIRS.read_text()), Path(sys.argv[2]))
