"""Section 53 measurement: do this repo's syntax trees obey branching laws?

Parses every Python file under ytk/ and every TS/TSX file under web/src with
tree-sitter, keeps named nodes only, and measures per file:

  Strahler orders and Horton's bifurcation and length ratios per order
  subtree-size rank-size slope (OLS) and discrete power-law MLE exponent
  leaf fraction, mean fan-out, max depth
  the node-type histogram (the file's genome)

The null is a uniform random plane tree with the identical out-degree multiset
(cycle-lemma construction). It keeps fan-out exactly and
randomizes everything the grammar imposes: which children sit under which
parents, depth, subtree sizes, Strahler structure.

uv run --extra dev python scripts/measure_syntax_laws.py
Writes docs/assets/53-syntax-laws/measured.json.
"""

from __future__ import annotations

import json
import math
import random
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import tree_sitter_python
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "assets" / "53-syntax-laws" / "measured.json"
NULL_DRAWS = 20
SEED = 53

PY = Language(tree_sitter_python.language())
TS = Language(tree_sitter_typescript.language_typescript())
TSX = Language(tree_sitter_typescript.language_tsx())


def corpus() -> list[tuple[Path, str]]:
    files: list[tuple[Path, str]] = []
    for p in sorted((ROOT / "ytk").rglob("*.py")):
        files.append((p, "python"))
    for p in sorted((ROOT / "web" / "src").rglob("*.ts*")):
        if ".test." in p.name or p.name.endswith(".gen.ts") or p.suffix not in {".ts", ".tsx"}:
            continue
        files.append((p, "tsx" if p.suffix == ".tsx" else "typescript"))
    return files


def parser_for(lang: str) -> Parser:
    return Parser({"python": PY, "typescript": TS, "tsx": TSX}[lang])


# A tree is a flat parent array over named nodes in preorder: parent[0] = -1.
def flatten(root: Node) -> tuple[list[int], list[str]]:
    parent: list[int] = []
    types: list[str] = []
    stack: list[tuple[Node, int]] = [(root, -1)]
    while stack:
        node, par = stack.pop()
        idx = len(parent)
        parent.append(par)
        types.append(node.type)
        for child in reversed(node.named_children):
            stack.append((child, idx))
    return parent, types


def children_of(parent: list[int]) -> list[list[int]]:
    kids: list[list[int]] = [[] for _ in parent]
    for i, p in enumerate(parent):
        if p >= 0:
            kids[p].append(i)
    return kids


def measure(parent: list[int]) -> dict:
    """Every law-facing quantity of one tree, from its parent array alone."""
    n = len(parent)
    kids = children_of(parent)
    size = [1] * n
    depth = [0] * n
    order = [1] * n
    # Preorder means parents precede children, so one reverse pass fills
    # sizes and orders bottom-up and one forward pass fills depths top-down.
    for i in range(1, n):
        depth[i] = depth[parent[i]] + 1
    for i in range(n - 1, 0, -1):
        size[parent[i]] += size[i]
    for i in range(n - 1, -1, -1):
        if kids[i]:
            best = max(order[k] for k in kids[i])
            ties = sum(1 for k in kids[i] if order[k] == best)
            order[i] = best + 1 if ties >= 2 else best
    top = order[0]
    # Horton segments: a maximal chain of equal order is one stream; its
    # length is its node count.
    seg_len: dict[int, list[int]] = {k: [] for k in range(1, top + 1)}
    for i in range(n):
        p = parent[i]
        if p < 0 or order[p] != order[i]:
            # Segment head: walk down the same-order child while unique.
            length, cur = 1, i
            while True:
                same = [k for k in kids[cur] if order[k] == order[cur]]
                if len(same) != 1:
                    break
                cur = same[0]
                length += 1
            seg_len[order[i]].append(length)
    n_k = [len(seg_len[k]) for k in range(1, top + 1)]
    l_k = [sum(seg_len[k]) / len(seg_len[k]) for k in range(1, top + 1)]
    r_b = [n_k[k] / n_k[k + 1] for k in range(top - 1)]
    r_l = [l_k[k + 1] / l_k[k] for k in range(top - 1)]
    internal = [s for s in size if s >= 2]
    leaves = n - len(internal)
    fanout = [len(k) for k in kids if k]
    return {
        "n": n,
        "leaves": leaves,
        "leaf_frac": leaves / n,
        "fanout_mean": sum(fanout) / len(fanout) if fanout else 0.0,
        "max_depth": max(depth),
        "strahler": top,
        "n_k": n_k,
        "l_k": l_k,
        "r_b": r_b,
        "r_l": r_l,
        "zipf_slope": rank_size_slope(internal),
        "alpha_mle": powerlaw_alpha(internal, xmin=2),
        "sizes": internal,
    }


def rank_size_slope(sizes: list[int]) -> float:
    if len(sizes) < 3:
        return float("nan")
    ys = sorted(sizes, reverse=True)
    xs = [math.log(r + 1) for r in range(len(ys))]
    ly = [math.log(v) for v in ys]
    mx, my = sum(xs) / len(xs), sum(ly) / len(ly)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ly))
    den = sum((x - mx) ** 2 for x in xs)
    return num / den


def powerlaw_alpha(sizes: list[int], xmin: int) -> float:
    """Discrete power-law tail exponent, Clauset's approximate MLE."""
    tail = [s for s in sizes if s >= xmin]
    if len(tail) < 3:
        return float("nan")
    return 1.0 + len(tail) / sum(math.log(s / (xmin - 0.5)) for s in tail)


def random_tree_same_degrees(parent: list[int], rng: random.Random) -> list[int]:
    """Uniform random plane tree with the identical out-degree multiset.

    Cycle lemma: for degrees summing to n - 1 exactly one rotation of any
    ordering has a Lukasiewicz path (running sum of degree - 1) that first
    hits -1 at the final step; that rotation is a valid preorder."""
    degrees = [len(k) for k in children_of(parent)]
    rng.shuffle(degrees)
    run, low, cut = 0, 0, 0
    for i, d in enumerate(degrees):
        run += d - 1
        if run < low:
            low, cut = run, i + 1
    seq = degrees[cut:] + degrees[:cut]
    out = [-1]
    stack = [(0, seq[0])]
    for d in seq[1:]:
        while stack and stack[-1][1] == 0:
            stack.pop()
        par, remaining = stack[-1]
        stack[-1] = (par, remaining - 1)
        out.append(par)
        stack.append((len(out) - 1, d))
    assert len(out) == len(parent)
    return out


def summarize_null(parent: list[int], rng: random.Random) -> dict:
    draws = [measure(random_tree_same_degrees(parent, rng)) for _ in range(NULL_DRAWS)]
    keys = ["leaf_frac", "max_depth", "strahler", "zipf_slope", "alpha_mle"]
    out: dict = {k: [d[k] for d in draws] for k in keys}
    # Horton ratios by order, padded with NaN where a draw's tree is
    # shallower than the deepest one.
    longest = max(len(d["r_b"]) for d in draws)
    for key in ("r_b", "r_l"):
        out[key] = [
            [d[key][k] if k < len(d[key]) else float("nan") for d in draws] for k in range(longest)
        ]
    out["n_k"] = [d["n_k"] for d in draws]
    return out


def git_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()


def main() -> None:
    rng = random.Random(SEED)
    rows = []
    t0 = time.time()
    genome_vocab: Counter[str] = Counter()
    for path, lang in corpus():
        src = path.read_bytes()
        root = parser_for(lang).parse(src).root_node
        parent, types = flatten(root)
        if len(parent) < 20:
            continue
        m = measure(parent)
        sizes = m.pop("sizes")
        genome = Counter(types)
        genome_vocab.update(genome)
        rows.append(
            {
                "file": str(path.relative_to(ROOT)),
                "lang": lang,
                "lines": src.count(b"\n") + 1,
                "has_error": root.has_error,
                **m,
                "size_hist": Counter(sizes).most_common(),
                "genome": dict(genome),
                "null": summarize_null(parent, rng),
            }
        )
        print(
            f"{path.relative_to(ROOT)!s:55} {lang:10} n={m['n']:6d} leaf={m['leaf_frac']:.2f} "
            f"S={m['strahler']} R_B={[round(x, 1) for x in m['r_b']]} zipf={m['zipf_slope']:.2f}",
            file=sys.stderr,
        )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "commit": git_sha(),
                "null_draws": NULL_DRAWS,
                "seed": SEED,
                "elapsed_s": round(time.time() - t0, 1),
                "vocab": dict(genome_vocab.most_common()),
                "files": rows,
            }
        )
    )
    print(
        f"wrote {OUT.relative_to(ROOT)} files={len(rows)} vocab={len(genome_vocab)} in {time.time() - t0:.1f}s",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
