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


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "pairs"
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
