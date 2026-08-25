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
    for kind in KINDS:
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
