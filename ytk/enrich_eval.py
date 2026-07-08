"""Fixtures loader for the enrichment eval harness.

Parses a vault note's markdown into its stored raw transcript (ground truth)
plus its existing Enrichment, so later harness tasks can score a challenger
enrichment against the transcript and compare it to the champion note.
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from .config import load_config
from .enrich import Enrichment, KeyMoment, enrich_content
from .sdk import structured

_SEC_RE = re.compile(
    r"^## (Thesis|Commentary|Summary|Key Concepts|Insights|Key Moments|Transcript)\n(.*?)(?=^## |\Z)",
    re.MULTILINE | re.DOTALL,
)
_DETAILS_RE = re.compile(r"<details>\s*<summary>[^<]*</summary>\s*(.*?)</details>", re.DOTALL)
_MOMENT_RE = re.compile(r"^- \*\*([^*]+)\*\*\s*[—-]\s*(.+)$", re.MULTILINE)
_CONCEPT_RE = re.compile(r"^- \s*(.+?):\s*(.+)$")

# Default fixture set: resolved under the vault sources dir when available.
# Left empty here since the vault path is machine-specific; callers should
# pass explicit paths, or populate this list once a stable stratified sample
# of notes is chosen.
FIXTURE_PATHS: list[Path] = []

LEDGER_PATH = Path.home() / ".ytk" / "enrich_eval_ledger.json"


@dataclass
class Fixture:
    note_path: Path
    source: str
    transcript: str
    enrichment: Enrichment


def _sections(text: str) -> dict[str, str]:
    return {name: body.strip() for name, body in _SEC_RE.findall(text)}


def _bullets(body: str) -> list[str]:
    return [ln[2:].strip() for ln in body.splitlines() if ln.startswith("- ")]


def _concepts(body: str) -> list[str]:
    out = []
    for ln in _bullets(body):
        m = _CONCEPT_RE.match(f"- {ln}")
        out.append(f"{m.group(1)}: {m.group(2)}" if m else ln)
    return out


def _key_moments(body: str) -> list[KeyMoment]:
    return [
        KeyMoment(timestamp=ts.strip(), description=desc.strip())
        for ts, desc in _MOMENT_RE.findall(body)
    ]


def _transcript(body: str) -> str:
    m = _DETAILS_RE.search(body)
    return m.group(1).strip() if m else body.strip()


def _infer_source(note_path: Path) -> str:
    return note_path.parent.name


def _parse_note(note_path: Path) -> Fixture:
    text = note_path.read_text(encoding="utf-8")
    sec = _sections(text)

    thesis = sec.get("Thesis", "")
    summary = sec.get("Commentary", sec.get("Summary", ""))
    key_concepts = _concepts(sec.get("Key Concepts", ""))
    insights = _bullets(sec.get("Insights", ""))
    key_moments = _key_moments(sec.get("Key Moments", ""))
    transcript = _transcript(sec.get("Transcript", ""))

    enrichment = Enrichment(
        thesis=thesis,
        summary=summary,
        key_concepts=key_concepts,
        insights=insights,
        interest_tags=[],
        key_moments=key_moments,
    )

    return Fixture(
        note_path=note_path,
        source=_infer_source(note_path),
        transcript=transcript,
        enrichment=enrichment,
    )


def load_fixtures(paths: list[Path] | None = None) -> list[Fixture]:
    if paths is None:
        paths = FIXTURE_PATHS
    return [_parse_note(Path(p)) for p in paths]


class _ClaimVerdict(BaseModel):
    claim: str
    label: Literal["supported", "inflated", "unsupported"]


class _FaithResult(BaseModel):
    claims: list[_ClaimVerdict]


@dataclass
class FaithScore:
    supported: int
    inflated: int
    unsupported: int
    rate: float


_FAITH_SYSTEM = (
    "Decompose the enrichment's key_concepts and insights into atomic factual claims. "
    "For each, judge it against the transcript: 'supported' (stated or demonstrated), 'inflated' "
    "(a kernel of truth oversold), or 'unsupported' (not in the transcript). Return every claim."
)


# The judge/faithfulness user prompt is capped by structured() at this many
# chars (tail-truncated). The scored artifact (enrichment / A / B) always goes
# FIRST and the transcript is budgeted into what remains, so only the transcript
# tail can ever be trimmed, never the content being evaluated.
_MAX_INPUT_CHARS = 40_000
_TRANSCRIPT_SEP = "\n\nTRANSCRIPT:\n"


def _fit_body(scored_block: str, transcript: str, limit: int = _MAX_INPUT_CHARS) -> str:
    """Assemble scored_block + transcript within `limit`, never truncating scored_block."""
    budget = max(0, limit - len(scored_block) - len(_TRANSCRIPT_SEP))
    return scored_block + _TRANSCRIPT_SEP + transcript[:budget]


def faithfulness(enrichment: Enrichment, transcript: str) -> FaithScore:
    scored_block = "ENRICHMENT:\n" + "\n".join(enrichment.key_concepts + enrichment.insights)
    body = _fit_body(scored_block, transcript)
    res = structured(_FAITH_SYSTEM, body, _FaithResult, model="claude-opus-4-8", max_input_chars=_MAX_INPUT_CHARS)
    supported = sum(c.label == "supported" for c in res.claims)
    inflated = sum(c.label == "inflated" for c in res.claims)
    unsupported = sum(c.label == "unsupported" for c in res.claims)
    total = max(1, len(res.claims))
    return FaithScore(supported, inflated, unsupported, (inflated + unsupported) / total)


class _JudgeResult(BaseModel):
    winner: Literal["A", "B", "tie"]
    specificity: str
    faithfulness: str
    nonredundancy: str
    retrievability: str


@dataclass
class Verdict:
    winner: str
    reasons: dict


_JUDGE_SYSTEM = (
    "You compare two enrichments (A and B) of the same source, for a personal retrieval "
    "library. Prefer the one that better satisfies, in priority order: (1) named specificity (concrete "
    "tools, commands, APIs, papers, numbers, proper nouns; fewer abstract topic-words); (2) faithfulness "
    "(no claims beyond what the source states; break ties toward the more conservative one); (3) "
    "non-redundancy (adds information vs restating the summary); (4) retrievability (would a reader who "
    "half-remembers the content find it). Verbosity is NOT a merit. Return the winner (A, B, or tie) and "
    "one line of reasoning per dimension."
)


def _one_judgment(first: Enrichment, second: Enrichment, transcript: str) -> _JudgeResult:
    scored_block = f"A:\n{first.model_dump_json()}\n\nB:\n{second.model_dump_json()}"
    body = _fit_body(scored_block, transcript)
    return structured(_JUDGE_SYSTEM, body, _JudgeResult, model="claude-opus-4-8", max_input_chars=_MAX_INPUT_CHARS)


def judge(a: Enrichment, b: Enrichment, transcript: str) -> Verdict:
    r1 = _one_judgment(a, b, transcript)  # A=a, B=b
    r2 = _one_judgment(b, a, transcript)  # A=b, B=a (swapped)
    a_wins = r1.winner == "A" and r2.winner == "B"
    b_wins = r1.winner == "B" and r2.winner == "A"
    winner = "A" if a_wins else "B" if b_wins else "tie"
    return Verdict(winner=winner, reasons={"order1": r1.model_dump(), "order2": r2.model_dump()})


def ledger_read(path: Path = LEDGER_PATH) -> list[dict]:
    """Load the ledger, tolerating a missing/empty/corrupt file.

    Returns an empty list if the file doesn't exist, is empty, or contains
    invalid JSON.
    """
    try:
        if path.exists() and path.stat().st_size > 0:
            return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError, OSError):
        pass
    return []


def ledger_append(entry: dict, path: Path = LEDGER_PATH) -> None:
    """Append an entry to the ledger atomically.

    Reads the existing ledger (or []), appends the entry, and writes to a
    temp file then os.replace()s it into place for atomicity.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = ledger_read(path)
    entries.append(entry)
    data = json.dumps(entries, indent=2)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(data, encoding="utf-8")
    os.replace(tmp, path)


def bootstrap_winrate(wins: list[float], n_resamples: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    """Compute seeded bootstrap confidence interval on win-rate.

    Args:
        wins: Per-note scores {1.0 win, 0.5 tie, 0.0 loss}.
        n_resamples: Number of bootstrap resamples.
        seed: Random seed for determinism.

    Returns:
        (point, lo, hi) at 95% confidence level.
        Returns (0.0, 0.0, 0.0) for empty input.
    """
    if not wins:
        return (0.0, 0.0, 0.0)
    rng = random.Random(seed)
    n = len(wins)
    means = sorted(statistics.mean(rng.choice(wins) for _ in range(n)) for _ in range(n_resamples))
    lo = means[int(0.025 * n_resamples)]
    hi = means[int(0.975 * n_resamples) - 1]
    return (statistics.mean(wins), lo, hi)


def _default_fixtures(max_notes: int = 5) -> list[Fixture]:
    """Build a small stratified fixture sample from the vault's ingested notes.

    Globs `sources/*/*.md` under the vault second-brain path, skipping the
    thumbnails/frames asset dirs, and picks up to `max_notes` notes spread
    across sources (at least one per source seen, when available).
    """
    try:
        from .vault import _get_brain_path

        brain = _get_brain_path()
    except Exception as exc:
        logging.getLogger(__name__).warning("default fixture resolution failed: %s", exc)
        return []

    sources_dir = brain / "sources"
    if not sources_dir.is_dir():
        return []

    by_source: dict[str, list[Path]] = {}
    for note_path in sorted(sources_dir.glob("*/*.md")):
        source = note_path.parent.name
        if source in ("thumbnails", "frames"):
            continue
        by_source.setdefault(source, []).append(note_path)

    if not by_source:
        return []

    picked: list[Path] = []
    sources = sorted(by_source)
    idx = 0
    while len(picked) < max_notes and any(by_source[s] for s in sources):
        source = sources[idx % len(sources)]
        if by_source[source]:
            picked.append(by_source[source].pop(0))
        idx += 1

    try:
        return load_fixtures(picked)
    except Exception as exc:
        logging.getLogger(__name__).warning("default fixture resolution failed: %s", exc)
        return []


def run_eval(challenger_tone: str, fixtures: list["Fixture"] | None = None) -> dict:
    """Run the champion-vs-challenger enrichment eval across a fixture set.

    Champion tone comes from `load_config().hub.enrich_tone`. For each
    fixture, both champion and challenger enrichments are regenerated from
    the fixture's transcript, judged against each other, and scored for
    faithfulness. Results are aggregated with a bootstrap win-rate CI and
    appended to the ledger.
    """
    if fixtures is None:
        fixtures = _default_fixtures()
    if not fixtures:
        raise ValueError("no fixtures available for run_eval; pass fixtures explicitly")

    champion_tone = load_config().hub.enrich_tone

    wins: list[float] = []
    champion_faith_rates: list[float] = []
    challenger_faith_rates: list[float] = []
    per_note: list[dict] = []

    for fx in fixtures:
        champion_enr = enrich_content(fx.transcript, fx.source, tone=champion_tone)
        challenger_enr = enrich_content(fx.transcript, fx.source, tone=challenger_tone)

        verdict = judge(champion_enr, challenger_enr, fx.transcript)
        win = {"B": 1.0, "A": 0.0, "tie": 0.5}[verdict.winner]
        wins.append(win)

        champion_faith = faithfulness(champion_enr, fx.transcript)
        challenger_faith = faithfulness(challenger_enr, fx.transcript)
        champion_faith_rates.append(champion_faith.rate)
        challenger_faith_rates.append(challenger_faith.rate)

        per_note.append({
            "note_path": str(fx.note_path),
            "source": fx.source,
            "winner": verdict.winner,
            "champion_faith_rate": champion_faith.rate,
            "challenger_faith_rate": challenger_faith.rate,
        })

    point, lo, hi = bootstrap_winrate(wins)
    faith_delta = statistics.mean(champion_faith_rates) - statistics.mean(challenger_faith_rates)

    result = {
        "winrate": point,
        "ci": [lo, hi],
        "faith_delta": faith_delta,
        "n": len(fixtures),
        "per_note": per_note,
    }

    ledger_append({
        "champion_tone": champion_tone,
        "challenger_tone": challenger_tone,
        "winrate": result["winrate"],
        "ci": result["ci"],
        "faith_delta": result["faith_delta"],
        "n": result["n"],
    }, LEDGER_PATH)

    return result
