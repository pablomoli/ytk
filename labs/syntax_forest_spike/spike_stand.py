"""Rung 4 spike (#217), parked 2026-09-14: lay out a stand of files under the section 53 rules, with git facts.

Throwaway by design: nothing here is imported by the package. Regenerate the page with build.py.
"""

import json
import math
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import numpy as np
from measure_syntax_laws import ROOT, children_of, corpus, flatten, parser_for

GOLDEN = math.radians(137.507764)
TILT = math.radians(30)
FORK = math.radians(24)
UP = np.array([0.0, 1.0, 0.0])
TROPISM = 0.24


def basis(d):
    a = UP if abs(d @ UP) < 0.9 else np.array([1.0, 0.0, 0.0])
    u = np.cross(d, a)
    u /= np.linalg.norm(u)
    return u, np.cross(d, u)


def layout(parent):
    n = len(parent)
    kids = children_of(parent)
    order = [1] * n
    leaves = [0] * n
    depth = [0] * n
    for i in range(1, n):
        depth[i] = depth[parent[i]] + 1
    for i in range(n - 1, -1, -1):
        if not kids[i]:
            leaves[i] = 1
        if i:
            leaves[parent[i]] += leaves[i]
        if kids[i]:
            best = max(order[k] for k in kids[i])
            ties = sum(order[k] == best for k in kids[i])
            order[i] = best + 1 if ties >= 2 else best
    radius = [0.06 * math.sqrt(max(leaves[i], 1)) for i in range(n)]
    length = [0.55 * (0.75 + 0.25 * order[i]) for i in range(n)]
    start = [None] * n
    end = [None] * n
    dirs = [None] * n
    start[0] = np.zeros(3)
    dirs[0] = UP.copy()
    end[0] = start[0] + dirs[0] * length[0]
    for i in range(n):
        ch = kids[i]
        if not ch:
            continue
        d = dirs[i]
        u, v = basis(d)
        m = len(ch)
        for j, c in enumerate(ch):
            if m == 1:
                az = (i * 0.61803) % 1.0 * 2 * math.pi
                tilt = math.radians(4)
            elif m == 2:
                az = (0.0 if j == 0 else math.pi) + (i % 7) * 0.15
                tilt = FORK
            else:
                az = j * GOLDEN + i * 0.3
                tilt = TILT * (0.8 + 0.2 * min(m, 8) / 8)
            nd = math.cos(tilt) * d + math.sin(tilt) * (math.cos(az) * u + math.sin(az) * v)
            nd = nd + TROPISM * UP
            nd /= np.linalg.norm(nd)
            dirs[c] = nd
            start[c] = end[i]
            end[c] = start[c] + nd * length[c]
    segs = [
        [round(float(x), 2) for x in (*start[i], *end[i])]
        + [
            round(radius[i], 3),
            order[i],
            int(not kids[i]),
            depth[i],
            round(radius[parent[i]] if parent[i] >= 0 else radius[i] * 1.15, 3),
        ]
        for i in range(n)
    ]
    return segs, max(depth), order[0], leaves[0]


def git_facts(rel):
    out = subprocess.run(
        ["git", "log", "--follow", "--format=%ct", "--", rel],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout.split()
    if not out:
        return {"commits": 0, "first": None, "last": None}
    ts = [int(x) for x in out]
    return {"commits": len(ts), "first": min(ts), "last": max(ts)}


# corpus + import fan-in
files = corpus()
texts = {p: p.read_text(errors="ignore") for p, _ in files}
stems = {}
for p, lang in files:
    stems[p] = p.stem if p.stem != "__init__" else p.parent.name
fanin = Counter()
for p, lang in files:
    t = texts[p]
    for q, ql in files:
        if q == p:
            continue
        s = stems[q]
        if lang == "python" and ql == "python":
            if re.search(
                rf"(from\s+\.{0, 2}[\w.]*\b{re.escape(s)}\b\s+import|import\s+[\w.]*\b{re.escape(s)}\b)",
                t,
            ):
                fanin[q] += 1
        elif (
            lang != "python"
            and ql != "python"
            and re.search(rf"from\s+['\"][^'\"]*\/{re.escape(s)}['\"]", t)
        ):
            fanin[q] += 1

trees = []
for p, lang in files:
    parent, types = flatten(parser_for(lang).parse(p.read_bytes()).root_node)
    n = len(parent)
    if not (200 <= n <= 5000):
        continue
    rel = str(p.relative_to(ROOT))
    trees.append((rel, lang, parent))
# group by directory, keep the stand under ~70k nodes
trees.sort(key=lambda t: (str(Path(t[0]).parent), -len(t[2])))
budget = {"python": 36000, "web": 34000}
keep = []
for rel, lang, parent in trees:
    k = "python" if lang == "python" else "web"
    if budget[k] - len(parent) < 0:
        continue
    budget[k] -= len(parent)
    keep.append((rel, lang, parent))
out = []
for rel, lang, parent in keep:
    segs, depth, S, leaves = layout(parent)
    g = git_facts(rel)
    out.append(
        {
            "file": rel,
            "dir": str(Path(rel).parent),
            "lang": lang,
            "n": len(parent),
            "depth": depth,
            "strahler": S,
            "leaves": leaves,
            "fanin": fanin[ROOT / rel],
            **g,
            "segments": segs,
        }
    )
Path(sys.argv[1]).write_text(json.dumps(out, separators=(",", ":")))
print("trees", len(out), "nodes", sum(t["n"] for t in out), "dirs", Counter(t["dir"] for t in out))
print("fanin top", sorted(((t["fanin"], t["file"]) for t in out), reverse=True)[:6])
print("commits top", sorted(((t["commits"], t["file"]) for t in out), reverse=True)[:4])
