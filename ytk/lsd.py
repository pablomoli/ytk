"""`ytk lsd` — orthogonal idea generation over the vault's source notes.

Not the interest-profile drift in `synthesis.render_drift`. This is Garry
Tan's "LSD mode": sample note pairs that are far apart in the centred
embedding space, let a model combine them, rank the combinations. The
sampler is pure array code so the experiment measures the production path.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, cast

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel

Vec = npt.NDArray[np.float32]

# ORTHO is the bottom TAIL_PCT of the background-pair null, the mirror of
# NEAR's top-K_NEAR neighbours. A Boltzmann tilt at T = background std moves
# the median only 0.64 std (C1), so the tail rule is what makes a distinct pool.
TAIL_PCT = 10.0
K_NEAR = 10
POOLS = ("ortho", "near", "rand")
KINDS = ("build", "post")
# Journal notes are iMessage digests, not sources to combine.
SOURCE_KINDS = ("youtube", "instagram", "web", "tiktok", "pinterest")
TEXT_LIMIT = 1500
JUDGE_BATCH = 10
DECK_TOP = 5
DECK_EXTRA = 5

LSD_HOME = Path(os.environ.get("YTK_LSD_HOME", os.path.expanduser("~/.ytk/lsd")))


@dataclass
class Note:
    id: str
    kind: str
    title: str
    text: str


@dataclass
class Pair:
    pool: str
    i: int
    j: int
    cos_raw: float
    cos_c: float


@dataclass
class Candidate:
    id: str
    pair_index: int
    kind: str  # build | post
    title: str
    body: str
    judge: float | None = None
    novelty_nearest: float | None = None
    novelty_parents: float | None = None
    corpus_cos: float | None = None
    # v3 scaffolding (trail, bridge, consequence, question), shown after rating.
    extra: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())


@dataclass
class Run:
    run_id: str
    seed: int
    n_notes: int
    mean_norm: float
    tail: float  # centred-cosine ceiling for ORTHO, p{TAIL_PCT} of the background
    background_std: float
    notes: list[Note]
    pairs: list[Pair]
    candidates: list[Candidate] = field(default_factory=lambda: list[Candidate]())


# ---------------------------------------------------------------- loading


_SECTION = re.compile(
    r"^## (Thesis|Insights|Summary)\s*\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL
)
_FRONT = re.compile(r"\A---\n(.*?)\n---", re.DOTALL)
_TITLE = re.compile(r"^title:\s*(.+)$", re.MULTILINE)


def note_text_from_markdown(md: str) -> tuple[str, str]:
    """(title, thesis + insights) from a vault note; summary is the fallback."""
    front = _FRONT.match(md)
    m = _TITLE.search(front.group(1)) if front else None
    title = m.group(1).strip().strip("\"'") if m else ""
    parts = {name: body.strip() for name, body in _SECTION.findall(md)}
    text = "\n".join(p for p in (parts.get("Thesis"), parts.get("Insights")) if p)
    if not text:
        text = parts.get("Summary", "")
    return title, text[:TEXT_LIMIT]


def _rows(got: Any) -> list[tuple[str, list[float], dict[str, Any], str]]:
    """Chroma's typed-optional get() result as plain rows."""
    d = cast(dict[str, Any], got)
    ids = cast(list[str], d["ids"])
    embs = cast(list[Any], d["embeddings"])
    metas = cast(list[dict[str, Any]], d["metadatas"] or [{} for _ in ids])
    docs = cast(list[str | None], d.get("documents") or [None for _ in ids])
    return [
        (i, [float(x) for x in cast(Sequence[float], e)], m, dc or "")
        for i, e, m, dc in zip(ids, embs, metas, docs, strict=True)
    ]


def load_notes() -> tuple[list[Note], Vec]:
    """Every source note with a vector: youtube docs plus note_sources_* memories."""
    from ytk import store

    notes: list[Note] = []
    vecs: list[list[float]] = []

    videos = store._videos_collection()  # pyright: ignore[reportPrivateUsage]
    for vid, emb, meta, doc in _rows(videos.get(include=["embeddings", "metadatas", "documents"])):
        thesis = store.meta_str(meta, "thesis")
        summary = store.meta_str(meta, "summary")
        text = "\n".join(p for p in (thesis, summary) if p) or doc
        notes.append(Note(vid, "youtube", store.meta_str(meta, "title") or vid, text[:TEXT_LIMIT]))
        vecs.append(emb)

    memories = store._memories_collection()  # pyright: ignore[reportPrivateUsage]
    for mid, emb, meta, _ in _rows(memories.get(include=["embeddings", "metadatas"])):
        if not mid.startswith("note_sources_"):
            continue
        kind = mid.split("_")[2]
        if kind not in SOURCE_KINDS:
            continue
        path = store.meta_str(meta, "source_path")
        try:
            md = Path(path).read_text()
        except OSError:
            continue
        title, text = note_text_from_markdown(md)
        if not text:
            continue
        notes.append(Note(mid, kind, title or Path(path).stem, text))
        vecs.append(emb)

    mat = np.asarray(vecs, dtype=np.float32)
    mat /= np.linalg.norm(mat, axis=1, keepdims=True)
    return notes, mat


def centre(X: Vec) -> tuple[Vec, float]:
    """Unit vectors with the shared direction removed, and |mean| before removal."""
    mu = X.mean(axis=0)
    Xc = X - mu
    Xc /= np.linalg.norm(Xc, axis=1, keepdims=True)
    return Xc.astype(np.float32), float(np.linalg.norm(mu))


# ---------------------------------------------------------------- sampling


def _ints(rng: np.random.Generator, high: int, n: int) -> npt.NDArray[np.int64]:
    return np.asarray(rng.integers(0, high, n), dtype=np.int64)  # pyright: ignore[reportUnknownMemberType]


def _int(rng: np.random.Generator, high: int) -> int:
    return int(rng.integers(0, high))  # pyright: ignore[reportUnknownMemberType]


def background_cosines(
    Xc: Vec, rng: np.random.Generator, n: int = 200_000
) -> npt.NDArray[np.float64]:
    """Centred cosine of n uniform random pairs (i != j)."""
    i = _ints(rng, len(Xc), n)
    j = _ints(rng, len(Xc), n)
    keep = i != j
    prod = cast(npt.NDArray[np.float32], np.einsum("ij,ij->i", Xc[i[keep]], Xc[j[keep]]))  # pyright: ignore[reportUnknownMemberType]
    return prod.astype(np.float64)


def tilt_acceptance(
    cos_c: npt.ArrayLike, floor: float, temperature: float
) -> npt.NDArray[np.float64]:
    """Rejection weights for a Boltzmann tilt exp(-cos_c / T), normalised so the
    floor (the lowest background cosine) is accepted with probability 1.
    Disclosed on C1, not used by the sampler."""
    return np.exp(-(np.asarray(cos_c, dtype=np.float64) - floor) / temperature)


def sample_pairs(
    X: Vec,
    Xc: Vec,
    pool: str,
    n: int,
    rng: np.random.Generator,
    tail: float,
    k_near: int = K_NEAR,
) -> list[Pair]:
    """n pairs for one pool. The base draw is uniform in every pool so hubs can
    only enter through NEAR's neighbour step, never through the sampler.
    ORTHO keeps a uniform pair only when its centred cosine is under `tail`."""
    m = len(Xc)
    pairs: list[Pair] = []
    neighbours: npt.NDArray[np.intp] | None = None
    if pool == "near":
        S = Xc @ Xc.T
        np.fill_diagonal(S, -np.inf)
        neighbours = np.argpartition(-S, k_near, axis=1)[:, :k_near]
    seen: set[tuple[int, int]] = set()
    while len(pairs) < n:
        i = _int(rng, m)
        if neighbours is not None:
            j = int(neighbours[i][_int(rng, k_near)])
        else:
            j = _int(rng, m)
        if i == j or (min(i, j), max(i, j)) in seen:
            continue
        cos_c = float(Xc[i] @ Xc[j])
        if pool == "ortho" and cos_c > tail:
            continue
        seen.add((min(i, j), max(i, j)))
        pairs.append(Pair(pool, i, j, float(X[i] @ X[j]), cos_c))
    return pairs


def new_run(seed: int, n_per_pool: int = 100, run_id: str | None = None) -> Run:
    notes, X = load_notes()
    Xc, mean_norm = centre(X)
    rng = np.random.default_rng(seed)
    bg = background_cosines(Xc, rng)
    tail = float(np.percentile(bg, TAIL_PCT))
    pairs: list[Pair] = []
    for pool in POOLS:
        pairs.extend(sample_pairs(X, Xc, pool, n_per_pool, rng, tail))
    return Run(
        run_id=run_id or time.strftime("%Y%m%d-%H%M%S"),
        seed=seed,
        n_notes=len(notes),
        mean_norm=mean_norm,
        tail=tail,
        background_std=float(bg.std()),
        notes=notes,
        pairs=pairs,
    )


# ---------------------------------------------------------------- generation


class BuildIdea(BaseModel):
    title: str
    pitch: str
    first_experiment: str


class PostIdea(BaseModel):
    hook: str
    angle: str


class PairIdeas(BaseModel):
    build: BuildIdea
    post: PostIdea


Structured = Callable[[str, str, type[Any]], Any]

GEN_SYSTEM = """You combine two notes from one person's knowledge vault into new ideas.
The person is a software engineer who builds tools, runs measured experiments,
and writes about what they find. Produce exactly two things from the pair:

build: one concrete project, experiment, or tool that only makes sense because
BOTH notes exist. title (under 10 words), pitch (2-3 sentences naming the
specific mechanism), first_experiment (the first thing to measure, one
sentence, with what would count as a result).

post: one angle for a written piece or video that joins the two notes.
hook (one sentence a reader would stop on), angle (2 sentences on what the
piece argues and why the two notes together make it possible).

Do not summarise either note. Do not pick one note and ignore the other.
Return only the JSON object."""


def _note_block(label: str, note: Note) -> str:
    return f"### {label}: {note.title}\n{note.text}"


def gen_prompt(run: Run, pair: Pair) -> str:
    a, b = run.notes[pair.i], run.notes[pair.j]
    return f"{_note_block('Note A', a)}\n\n{_note_block('Note B', b)}"


def _default_structured(system: str, user: str, result: type[Any]) -> Any:
    from ytk.sdk import structured

    return structured(system, user, result, max_tokens=1200)


def generate_pair(run: Run, index: int, call: Structured = _default_structured) -> list[Candidate]:
    pair = run.pairs[index]
    ideas = cast(PairIdeas, call(GEN_SYSTEM, gen_prompt(run, pair), PairIdeas))
    return [
        Candidate(
            id=f"{run.run_id}-{index}-build",
            pair_index=index,
            kind="build",
            title=ideas.build.title,
            body=f"{ideas.build.pitch}\n\nFirst experiment: {ideas.build.first_experiment}",
        ),
        Candidate(
            id=f"{run.run_id}-{index}-post",
            pair_index=index,
            kind="post",
            title=ideas.post.hook,
            body=ideas.post.angle,
        ),
    ]


def generate(
    run: Run,
    call: Structured = _default_structured,
    checkpoint: Callable[[Run], object] | None = None,
    log: Callable[[str], object] = print,
) -> Run:
    """Fill candidates for every pair that has none; resumable after a crash."""
    done = {c.pair_index for c in run.candidates}
    todo = [i for i in range(len(run.pairs)) if i not in done]
    for n, index in enumerate(todo, 1):
        try:
            run.candidates.extend(generate_pair(run, index, call))
        except Exception as exc:  # one bad pair must not sink an overnight run
            log(f"pair {index} failed: {exc}")
            continue
        if checkpoint is not None:
            checkpoint(run)
        log(f"generated {n}/{len(todo)} (pair {index}, {run.pairs[index].pool})")
    return run


# ---------------------------------------------------------------- judging


class JudgeScore(BaseModel):
    id: str
    score: int


class JudgeScores(BaseModel):
    scores: list[JudgeScore]


JUDGE_SYSTEM = """You score candidate ideas for coherence, 1 to 5. You see only the idea, never
its sources. Score each independently on one question: does this hold together
as ONE specific, actionable thing a person could start on this week?

5: one clear mechanism, specific enough to start, the first step is obvious.
4: clear and specific, one vague joint.
3: sensible but generic; could have been written without any particular source.
2: two things stapled together, or a restatement of something everyone knows.
1: incoherent, contradictory, or empty.

Return only the JSON object with one score per id, in the order given."""


def judge_prompt(batch: list[Candidate]) -> str:
    return "\n\n".join(f"id: {c.id}\nkind: {c.kind}\ntitle: {c.title}\n{c.body}" for c in batch)


def judge(
    run: Run,
    rng: np.random.Generator,
    call: Structured = _default_structured,
    batch_size: int = JUDGE_BATCH,
    log: Callable[[str], object] = print,
) -> Run:
    """Score every unscored candidate in shuffled batches, so no batch is one pool."""
    todo = [c for c in run.candidates if c.judge is None]
    order = rng.permutation(len(todo))
    by_id = {c.id: c for c in todo}
    for start in range(0, len(todo), batch_size):
        batch = [todo[int(k)] for k in order[start : start + batch_size]]
        try:
            scored = cast(JudgeScores, call(JUDGE_SYSTEM, judge_prompt(batch), JudgeScores))
        except Exception as exc:
            log(f"judge batch at {start} failed: {exc}")
            continue
        for s in scored.scores:
            if s.id in by_id:
                by_id[s.id].judge = float(min(5, max(1, s.score)))
        log(f"judged {min(start + batch_size, len(todo))}/{len(todo)}")
    return run


# ---------------------------------------------------------------- novelty


def _embed_documents(texts: list[str]) -> Vec:
    from ytk import store

    ef = cast(Callable[[list[str]], Any], store._get_ef())  # pyright: ignore[reportPrivateUsage]
    out = np.asarray(ef(texts), dtype=np.float32)
    out /= np.linalg.norm(out, axis=1, keepdims=True)
    return out


def novelty(run: Run, X: Vec, embed: Callable[[list[str]], Vec] = _embed_documents) -> Run:
    """Per candidate: centred cosine to its nearest non-parent note, to its
    parents' midpoint, and raw cosine to the corpus mean (the cone)."""
    if not run.candidates:
        return run
    mu = X.mean(axis=0)
    mu_hat = mu / np.linalg.norm(mu)
    Xc, _ = centre(X)
    C = embed([f"{c.title}\n{c.body}" for c in run.candidates])
    Cc = C - mu
    Cc /= np.linalg.norm(Cc, axis=1, keepdims=True)
    sims = Cc @ Xc.T
    for row, c in enumerate(run.candidates):
        pair = run.pairs[c.pair_index]
        mid = Xc[pair.i] + Xc[pair.j]
        mid /= np.linalg.norm(mid)
        s = sims[row].copy()
        s[[pair.i, pair.j]] = -np.inf
        c.novelty_nearest = float(s.max())
        c.novelty_parents = float(Cc[row] @ mid)
        c.corpus_cos = float(C[row] @ mu_hat)
    return run


# ---------------------------------------------------------------- deck


def build_deck(
    run: Run, rng: np.random.Generator, top: int = DECK_TOP, extra: int = DECK_EXTRA
) -> list[dict[str, Any]]:
    """Per kind and pool: the judge's top-`top` plus `extra` uniform draws from
    the rest, shuffled. Pool labels stay in the run file; the deck never
    carries them, and the scorer is the only join."""
    cards: list[dict[str, Any]] = []
    kinds = sorted({c.kind for c in run.candidates}) or list(KINDS)
    for kind in kinds:
        for pool in POOLS:
            scored = [
                c
                for c in run.candidates
                if c.kind == kind and c.judge is not None and run.pairs[c.pair_index].pool == pool
            ]
            scored.sort(key=lambda c: (-(c.judge or 0.0), c.id))
            head, rest = scored[:top], scored[top:]
            picks: list[Candidate] = []
            if rest:
                idx = rng.choice(len(rest), size=min(extra, len(rest)), replace=False)
                picks = [rest[int(k)] for k in idx]
            for c in head + picks:
                pair = run.pairs[c.pair_index]
                a, b = run.notes[pair.i], run.notes[pair.j]
                cards.append(
                    {
                        "id": c.id,
                        "kind": c.kind,
                        "title": c.title,
                        "body": c.body,
                        "parents": [{"id": a.id, "title": a.title}, {"id": b.id, "title": b.title}],
                        "extra": c.extra,
                    }
                )
    order = rng.permutation(len(cards))
    return [cards[int(k)] for k in order]


# ---------------------------------------------------------------- persistence


def run_path(run_id: str) -> Path:
    return LSD_HOME / "runs" / f"{run_id}.json"


def save_run(run: Run) -> Path:
    path = run_path(run.run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(asdict(run), indent=1))
    tmp.replace(path)
    return path


def load_run(run_id: str) -> Run:
    d = cast(dict[str, Any], json.loads(run_path(run_id).read_text()))
    return Run(
        run_id=d["run_id"],
        seed=d["seed"],
        n_notes=d["n_notes"],
        mean_norm=d["mean_norm"],
        tail=d["tail"],
        background_std=d["background_std"],
        notes=[Note(**n) for n in cast(list[dict[str, Any]], d["notes"])],
        pairs=[Pair(**p) for p in cast(list[dict[str, Any]], d["pairs"])],
        candidates=[Candidate(**c) for c in cast(list[dict[str, Any]], d.get("candidates", []))],
    )


# ---------------------------------------------------------------- scoring


YES = 4.0  # owner score at or above this counts as "would build / would publish"
G1_MIN_HITS = 3
G2_MIN_RHO = 0.30


@dataclass
class Rating:
    run_id: str
    candidate_id: str
    score: float
    note: str = ""
    ts: str = ""


def ratings_path() -> Path:
    return LSD_HOME / "ratings.jsonl"


def append_rating(rating: Rating) -> None:
    path = ratings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(asdict(rating)) + "\n")


def load_ratings(run_id: str) -> dict[str, float]:
    """candidate id -> latest owner score for one run."""
    path = ratings_path()
    if not path.exists():
        return {}
    out: dict[str, float] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        d = cast(dict[str, Any], json.loads(line))
        if d.get("run_id") == run_id:
            out[str(d["candidate_id"])] = float(d["score"])
    return out


def _ranks(a: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Average ranks, ties shared."""
    order = np.argsort(a, kind="stable")
    ranks = np.empty(len(a), dtype=np.float64)
    ranks[order] = np.arange(1, len(a) + 1, dtype=np.float64)
    for v in np.unique(a):
        m = a == v
        if m.sum() > 1:
            ranks[m] = ranks[m].mean()
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    xa, ya = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
    if len(xa) < 3 or xa.std() == 0 or ya.std() == 0:
        return 0.0
    return float(np.corrcoef(_ranks(xa), _ranks(ya))[0, 1])


def judge_top(run: Run, kind: str, pool: str, top: int = DECK_TOP) -> list[Candidate]:
    scored = [
        c
        for c in run.candidates
        if c.kind == kind and c.judge is not None and run.pairs[c.pair_index].pool == pool
    ]
    scored.sort(key=lambda c: (-(c.judge or 0.0), c.id))
    return scored[:top]


def gates(
    run: Run, ratings: dict[str, float], rng: np.random.Generator, permutations: int = 2000
) -> dict[str, Any]:
    """G1 and G2 against the registered bars, plus the disclosed readouts.
    Only this function ever joins a rating to a pool label."""
    hits: dict[str, dict[str, int]] = {}
    rated_top: dict[str, dict[str, int]] = {}
    for kind in KINDS:
        hits[kind], rated_top[kind] = {}, {}
        for pool in POOLS:
            ids = [c.id for c in judge_top(run, kind, pool)]
            got = [ratings[i] for i in ids if i in ratings]
            hits[kind][pool] = sum(s >= YES for s in got)
            rated_top[kind][pool] = len(got)
    g1_kinds = [
        k for k in KINDS if hits[k]["ortho"] >= G1_MIN_HITS and hits[k]["ortho"] > hits[k]["near"]
    ]
    by_id = {c.id: c for c in run.candidates}
    pairs = [
        (by_id[i].judge or 0.0, s)
        for i, s in ratings.items()
        if i in by_id and by_id[i].judge is not None
    ]
    jx = [p[0] for p in pairs]
    oy = [p[1] for p in pairs]
    rho = spearman(jx, oy)
    null = (
        np.array([spearman(jx, list(rng.permutation(oy))) for _ in range(permutations)])
        if pairs
        else np.zeros(1)
    )
    pool_mean: dict[str, dict[str, float | None]] = {}
    for kind in KINDS:
        pool_mean[kind] = {}
        for pool in POOLS:
            got = [
                s
                for i, s in ratings.items()
                if i in by_id
                and by_id[i].kind == kind
                and run.pairs[by_id[i].pair_index].pool == pool
            ]
            pool_mean[kind][pool] = float(np.mean(got)) if got else None
    return {
        "rated": len(ratings),
        "hits_top": hits,
        "rated_top": rated_top,
        "g1_pass": bool(g1_kinds),
        "g1_kinds": g1_kinds,
        "rho": rho,
        "rho_null_p95": float(np.percentile(null, 95)),
        "rho_p": float(np.mean(null >= rho)) if pairs else 1.0,
        "g2_pass": rho >= G2_MIN_RHO,
        "owner_mean_by_pool": pool_mean,
    }


# ---------------------------------------------------------------- hub


def list_runs() -> list[dict[str, Any]]:
    """Runs with a written deck, newest first, with rating progress."""
    out: list[dict[str, Any]] = []
    runs_dir = LSD_HOME / "runs"
    if not runs_dir.exists():
        return out
    for deck_file in sorted(runs_dir.glob("*-deck.json"), reverse=True):
        run_id = deck_file.name.removesuffix("-deck.json")
        deck = cast(list[dict[str, Any]], json.loads(deck_file.read_text()))
        rated = load_ratings(run_id)
        out.append(
            {
                "run_id": run_id,
                "cards": len(deck),
                "rated": sum(1 for c in deck if c["id"] in rated),
            }
        )
    return out


def deck_for(run_id: str) -> dict[str, Any]:
    """The blind deck plus the owner's ratings so far. Cards never carry pools."""
    deck_file = run_path(run_id).with_name(f"{run_id}-deck.json")
    if not deck_file.exists():
        raise FileNotFoundError(run_id)
    deck = cast(list[dict[str, Any]], json.loads(deck_file.read_text()))
    return {"run_id": run_id, "cards": deck, "ratings": load_ratings(run_id)}


# ---------------------------------------------------------------- rung 0.5: newness


class WhatIf(BaseModel):
    title: str
    body: str


class PairIdeasV2(BaseModel):
    build: BuildIdea
    post: PostIdea
    whatif: WhatIf


# Phrases the first run repeated across hundreds of ideas (the 3-gram table in
# docs/assets/53-lsd/README.md). Banned by name so the second run cannot lean on them.
BANNED_PHRASES = (
    "the piece argues",
    "first experiment",
    "a tool that",
    "Note A",
    "Note B",
    "measure whether",
)

GEN_SYSTEM_V2 = """You are given two texts, A and B, from one person's reading. Do not summarise
them, do not name them, do not say "A" or "B". Take the MECHANISM of one (how
it works, its moving parts, its rule) and run it inside the WORLD of the other,
then push the result into a domain that neither text lives in. The result
should feel strange first and inevitable second. Concrete nouns, no hedging,
no lists of options. Produce three things:

build: something that could exist. title (under 8 words, no colon), pitch
(2-3 sentences: what it is and the one mechanism it runs on),
first_experiment (one sentence: the smallest thing that would show it works
or fails).

post: an angle for a piece. hook (one sentence, no dash characters, not a
question), angle (2 sentences: the claim, and the leap that makes it).

whatif: the unreasonable version. title (a what-if in under 12 words), body
(3-4 sentences following it all the way, as if it were already true).

Forbidden phrases: "the piece argues", "first experiment", "a tool that",
"Note A", "Note B", "measure whether", "in this piece". Return only the JSON
object."""

SONNET = "claude-sonnet-5"


def gen_prompt_v2(run: Run, pair: Pair) -> str:
    a, b = run.notes[pair.i], run.notes[pair.j]
    return f"### A\n{a.text}\n\n### B\n{b.text}"


def structured_with_model(model: str | None) -> Structured:
    def call(system: str, user: str, result: type[Any]) -> Any:
        from ytk.sdk import structured

        if model is None:
            return structured(system, user, result, max_tokens=1400)
        return structured(system, user, result, model=model, max_tokens=1400)

    return call


def generate_pair_v2(
    run: Run,
    index: int,
    call: Structured,
    sample: int = 0,
) -> list[Candidate]:
    pair = run.pairs[index]
    ideas = cast(PairIdeasV2, call(GEN_SYSTEM_V2, gen_prompt_v2(run, pair), PairIdeasV2))
    suffix = f"-s{sample}"
    return [
        Candidate(
            id=f"{run.run_id}-{index}-build{suffix}",
            pair_index=index,
            kind="build",
            title=ideas.build.title,
            body=f"{ideas.build.pitch}\n\n{ideas.build.first_experiment}",
        ),
        Candidate(
            id=f"{run.run_id}-{index}-post{suffix}",
            pair_index=index,
            kind="post",
            title=ideas.post.hook,
            body=ideas.post.angle,
        ),
        Candidate(
            id=f"{run.run_id}-{index}-whatif{suffix}",
            pair_index=index,
            kind="whatif",
            title=ideas.whatif.title,
            body=ideas.whatif.body,
        ),
    ]


def generate_v2(
    run: Run,
    call: Structured,
    samples: int = 1,
    checkpoint: Callable[[Run], object] | None = None,
    log: Callable[[str], object] = print,
) -> Run:
    """Like generate(), with `samples` draws per pair, all kept in the run and
    tagged by sample index; selection happens later, on embeddings."""
    have: set[tuple[int, int]] = set()
    for c in run.candidates:
        s = int(c.id.rsplit("-s", 1)[1]) if "-s" in c.id else 0
        have.add((c.pair_index, s))
    todo = [(i, s) for i in range(len(run.pairs)) for s in range(samples) if (i, s) not in have]
    for n, (index, s) in enumerate(todo, 1):
        try:
            run.candidates.extend(generate_pair_v2(run, index, call, sample=s))
        except Exception as exc:
            log(f"pair {index} sample {s} failed: {exc}")
            continue
        if checkpoint is not None:
            checkpoint(run)
        log(f"generated {n}/{len(todo)} (pair {index} s{s}, {run.pairs[index].pool})")
    return run


def select_farthest(run: Run, C: Vec, mu: Vec) -> list[int]:
    """Temperature by selection. Per (pair, kind), keep the sample whose worst
    similarity — to the corpus mean or to any idea already kept — is lowest.
    Returns kept candidate row indices, in pair order."""
    groups: dict[tuple[int, str], list[int]] = {}
    for row, c in enumerate(run.candidates):
        groups.setdefault((c.pair_index, c.kind), []).append(row)
    mu_hat = (mu / np.linalg.norm(mu)).astype(np.float32)
    kept: list[int] = []
    for key in sorted(groups):
        rows = groups[key]
        scores: list[float] = []
        for r in rows:
            worst = float(C[r] @ mu_hat)
            if kept:
                worst = max(worst, float((C[kept] @ C[r]).max()))
            scores.append(worst)
        kept.append(rows[int(np.argmin(scores))])
    return kept


def newness(
    run: Run,
    rows: Sequence[int],
    C: Vec,
    X: Vec,
    exclude_parents: bool = True,
) -> dict[str, Any]:
    """N1 spread, N2 voice, N3 distance, and the text stats, over `rows` of
    the run's candidates. Medians, plus per-kind medians."""
    if not rows:
        return {}
    mu = X.mean(axis=0)
    mu_hat = mu / np.linalg.norm(mu)
    Xc, _ = centre(X)
    sub = C[list(rows)]
    subc = sub - mu
    subc /= np.linalg.norm(subc, axis=1, keepdims=True)
    S = subc @ subc.T
    np.fill_diagonal(S, -np.inf)
    n1: npt.NDArray[np.float64] = (S.max(axis=1) if len(rows) > 1 else np.zeros(1)).astype(
        np.float64
    )
    n2: npt.NDArray[np.float32] = sub @ mu_hat
    sims = subc @ Xc.T
    n3 = np.empty(len(rows))
    for k, r in enumerate(rows):
        s = sims[k].copy()
        if exclude_parents:
            pair = run.pairs[run.candidates[r].pair_index]
            s[[pair.i, pair.j]] = -np.inf
        n3[k] = s.max()
    n4 = np.empty(len(rows))
    for k, r in enumerate(rows):
        pair = run.pairs[run.candidates[r].pair_index]
        n4[k] = max(float(subc[k] @ Xc[pair.i]), float(subc[k] @ Xc[pair.j]))
    cands = [run.candidates[r] for r in rows]
    posts = [c.title for c in cands if c.kind == "post"]
    leak = sum(
        1
        for c in cands
        if re.search(r"\bNote [AB]\b", c.body) or re.search(r"\bNote [AB]\b", c.title)
    )
    banned = sum(1 for c in cands for ph in BANNED_PHRASES[:3] if ph in c.body.lower())
    kinds = sorted({c.kind for c in cands})
    per_kind: dict[str, dict[str, float]] = {}
    for kind in kinds:
        ks = [k for k, c in enumerate(cands) if c.kind == kind]
        per_kind[kind] = {
            "n1": float(np.median([float(n1[k]) for k in ks])),
            "n2": float(np.median([float(n2[k]) for k in ks])),
            "n3": float(np.median([float(n3[k]) for k in ks])),
            "n4": float(np.median([float(n4[k]) for k in ks])),
        }
    per_pool: dict[str, dict[str, float]] = {}
    for pool in sorted({run.pairs[c.pair_index].pool for c in cands}):
        ks = [k for k, c in enumerate(cands) if run.pairs[c.pair_index].pool == pool]
        per_pool[pool] = {
            "n3": float(np.median([float(n3[k]) for k in ks])),
            "n4": float(np.median([float(n4[k]) for k in ks])),
        }
    return {
        "n": len(rows),
        "n1": float(np.median(n1)),
        "n2": float(np.median(n2)),
        "n3": float(np.median(n3)),
        "n4": float(np.median(n4)),
        "per_pool": per_pool,
        "leak": leak,
        "banned": banned,
        "em_dash_hooks": (sum("—" in t for t in posts) / len(posts)) if posts else 0.0,
        "per_kind": per_kind,
    }


# ---------------------------------------------------------------- rung 0.5: latents


LATENT_FEATURES = Path(__file__).resolve().parents[1] / "experiments" / "sae_qwen" / "features.json"
LATENT_SAE = Path(os.path.expanduser("~/.ytk/atlas_sae.npz"))


def load_latents(
    features_path: Path = LATENT_FEATURES, sae_path: Path = LATENT_SAE
) -> tuple[list[Note], Vec]:
    """Named native latents as pseudo-notes (name, rationale, exemplar titles)
    with their unit decoder rows as vectors."""
    import ast

    d = cast(dict[str, Any], json.loads(features_path.read_text()))
    feats = cast(list[dict[str, Any]], d["features"])
    z = np.load(sae_path)
    W = np.asarray(z["W_dec"], dtype=np.float32)
    notes: list[Note] = []
    vecs: list[Vec] = []
    for f in feats:
        idx = int(f["feature"])
        name = str(f.get("name", "")).strip()
        if not name:
            continue
        ex_raw = f.get("exemplars", [])
        ex = cast(
            list[dict[str, Any]], ast.literal_eval(ex_raw) if isinstance(ex_raw, str) else ex_raw
        )
        titles: list[str] = []
        for e in ex:
            t = str(e.get("title", "")).strip()
            if t and t not in titles:
                titles.append(t)
            if len(titles) == 5:
                break
        text = f"{name}. {str(f.get('name_rationale', '')).strip()}\nSeen in: " + "; ".join(titles)
        notes.append(Note(f"latent-{idx}", "latent", name, text[:TEXT_LIMIT]))
        vecs.append(W[idx] / np.linalg.norm(W[idx]))
    return notes, np.stack(vecs)


def latent_run(seed: int, n: int, run_id: str) -> Run:
    """A run whose 'notes' are latents; ORTHO is the bottom TAIL_PCT of
    decoder cosine among named-latent pairs. Decoder rows carry no cone, so
    centring is skipped and cos_c == cos_raw."""
    notes, W = load_latents()
    rng = np.random.default_rng(seed)
    bg = background_cosines(W, rng, 50_000)
    tail = float(np.percentile(bg, TAIL_PCT))
    pairs = sample_pairs(W, W, "ortho", n, rng, tail)
    return Run(
        run_id=run_id,
        seed=seed,
        n_notes=len(notes),
        mean_norm=float(np.linalg.norm(W.mean(axis=0))),
        tail=tail,
        background_std=float(bg.std()),
        notes=notes,
        pairs=pairs,
    )


N1_BAR, N2_BAR, N3_BAR, N4_BAR = 0.39, 0.51, 0.33, 0.39


def rank_compare(
    run: Run, rows: Sequence[int], C: Vec, X: Vec, top: int = DECK_TOP
) -> dict[str, Any]:
    """A4: judge-first top-`top` per kind vs novelty-first (ideas under all
    three per-idea bars, then judge). Reports how many of each top set clear
    the bars and how large the novel pool is."""
    mu = X.mean(axis=0)
    mu_hat = mu / np.linalg.norm(mu)
    Xc, _ = centre(X)
    sub = C[list(rows)]
    subc = sub - mu
    subc /= np.linalg.norm(subc, axis=1, keepdims=True)
    S = subc @ subc.T
    np.fill_diagonal(S, -np.inf)
    n1 = S.max(axis=1)
    n2 = sub @ mu_hat
    sims = subc @ Xc.T
    n3 = np.empty(len(rows))
    for k, r in enumerate(rows):
        pair = run.pairs[run.candidates[r].pair_index]
        s = sims[k].copy()
        s[[pair.i, pair.j]] = -np.inf
        n3[k] = s.max()
    passes = (n1 <= N1_BAR) & (n2 <= N2_BAR) & (n3 <= N3_BAR)
    out: dict[str, Any] = {"novel_pool": int(passes.sum()), "n": len(rows)}
    for kind in sorted({run.candidates[r].kind for r in rows}):
        ks = [k for k, r in enumerate(rows) if run.candidates[r].kind == kind]
        by_judge = sorted(ks, key=lambda k: -(run.candidates[rows[k]].judge or 0.0))[:top]
        novel = [k for k in ks if passes[k]]
        by_novel = sorted(novel, key=lambda k: -(run.candidates[rows[k]].judge or 0.0))[:top]
        out[kind] = {
            "judge_first_pass": int(sum(passes[k] for k in by_judge)),
            "novelty_first_size": len(by_novel),
            "judge_first_ids": [run.candidates[rows[k]].id for k in by_judge],
            "novelty_first_ids": [run.candidates[rows[k]].id for k in by_novel],
        }
    return out


# ---------------------------------------------------------------- rung 0.6: the cross product


class Third(BaseModel):
    name: str
    definition: str
    properties: list[str]


class CrossProduct(BaseModel):
    trail: list[str]
    bridge: str
    third: Third
    consequence: str
    question: str


GEN_SYSTEM_V3 = """You are given two texts, A and B. Your job is to find their cross product: a
THIRD concept that is perpendicular to both, that exists only where they
meet, and that neither text contains. Not a blend, not a summary, not one
restated in the other's words. If a reader who knows A and B could have
written it, it is not new enough.

First, think loosely. trail: ten short free-association steps, alternating
from A and from B, each step a noun phrase that drifts one hop further from
its source (5-12 words each). Let them wander into sensation, physics, ritual,
biology, games, geometry, whatever. Do not steer toward a conclusion.

Then, from where the trails cross:

bridge: the one structural sense in which A and B are the same shape, with the
mapping explicit (this in A is that in B), two sentences.

third: name (a new term, 1-4 words, not a phrase from either text), definition
(one sentence a stranger could use), properties (exactly three, each a concrete
thing that would be true of it).

consequence: what breaks, in something the reader currently believes, if the
third concept is real. Two sentences.

question: the question that neither text could ask alone, one sentence, ending
in a question mark.

Never name the texts, never write "A" or "B" outside the trail, no dash
characters, no hedging, no lists of alternatives. Return only the JSON object."""


def gen_prompt_v3(run: Run, pair: Pair) -> str:
    a, b = run.notes[pair.i], run.notes[pair.j]
    return f"### A\n{a.text}\n\n### B\n{b.text}"


def generate_pair_v3(run: Run, index: int, call: Structured, sample: int = 0) -> list[Candidate]:
    pair = run.pairs[index]
    cp = cast(CrossProduct, call(GEN_SYSTEM_V3, gen_prompt_v3(run, pair), CrossProduct))
    props = "\n".join(f"- {x}" for x in cp.third.properties[:3])
    return [
        Candidate(
            id=f"{run.run_id}-{index}-third-s{sample}",
            pair_index=index,
            kind="third",
            title=cp.third.name,
            body=f"{cp.third.definition}\n\n{props}",
            extra={
                "trail": cp.trail[:12],
                "bridge": cp.bridge,
                "consequence": cp.consequence,
                "question": cp.question,
            },
        )
    ]


def generate_v3(
    run: Run,
    call: Structured,
    samples: int = 1,
    checkpoint: Callable[[Run], object] | None = None,
    log: Callable[[str], object] = print,
) -> Run:
    have = {(c.pair_index, int(c.id.rsplit("-s", 1)[1])) for c in run.candidates if "-s" in c.id}
    todo = [(i, s) for i in range(len(run.pairs)) for s in range(samples) if (i, s) not in have]
    for n, (index, s) in enumerate(todo, 1):
        try:
            run.candidates.extend(generate_pair_v3(run, index, call, sample=s))
        except Exception as exc:
            log(f"pair {index} sample {s} failed: {exc}")
            continue
        if checkpoint is not None:
            checkpoint(run)
        log(f"generated {n}/{len(todo)} (pair {index} s{s}, {run.pairs[index].pool})")
    return run
