# Composable Enrichment Node + Eval Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify the five `enrich_*` paths into one source-dispatched node with a user-editable tone preamble and Chain-of-Density, and build a preview-on-5-notes eval harness that gates prompt changes.

**Architecture:** One system prompt is composed from `[tone] + [base skeleton] + [source bias]`; each existing `enrich_*` function keeps its content formatting and delegates to a single `enrich_content()` node. A separate `enrich_eval` module scores a challenger config against the current champion with an Opus pairwise judge, a hand-rolled FActScore faithfulness check, and a bootstrapped win-rate, appending to a JSON ledger.

**Tech Stack:** Python, pydantic, the existing `ytk/sdk.py` wrappers (`run_structured`, `structured`), Chroma (unaffected), Click CLI, FastAPI hub.

## Global Constraints

- Preserve behavior of all five `enrich_*` public signatures; call sites (cli.py, scheduler.py, ingest.py, imessage.py) stay untouched.
- `Enrichment` pydantic schema is unchanged.
- Anthropic-only: LLM calls go through `ytk/sdk.py` (`run_structured` / `structured`); no new LLM-client dependency (rules out the `ragas` package).
- Judge model is Opus: `model="claude-opus-4-8"`. Generator stays the SDK default (Haiku).
- No emojis, no em-dashes in any user-facing string (repo rule; enforced by existing UI tests).
- recall@k is NOT used as a quality metric anywhere in this plan (ceilinged at this corpus size).
- TDD: failing test first, minimal impl, frequent commits. LLM calls are stubbed in unit tests; one opt-in integration test may hit the real path.

## File Structure

- `ytk/enrich.py` — MODIFY. Add `BASE_SKELETON`, `SOURCE_BIAS`, `_TONE_WRAPPER`, `_build_system()`, `enrich_content()`. Rewire `enrich`, `enrich_tiktok`, `enrich_instagram` to delegate. Fold `_YT_SYSTEM`/`_INSTAGRAM_SYSTEM`/`_TIKTOK_SYSTEM` content into the skeleton + bias fragments.
- `ytk/ingest.py` — MODIFY. `enrich_web` delegates; `_SYSTEM_WEB` folds into `SOURCE_BIAS["web"]`.
- `ytk/imessage.py` — MODIFY. `enrich_journal` delegates; `_SYSTEM_JOURNAL` folds into `SOURCE_BIAS["journal"]`.
- `ytk/config.py` — MODIFY. Add `HubConfig.enrich_tone: str = ""`.
- `ytk/enrich_eval.py` — CREATE. The harness: fixtures, faithfulness, judge, bootstrap, ledger, `run_eval`.
- `ytk/cli.py` — MODIFY. Add `enrich-eval` command.
- `ytk/ui/server.py` — MODIFY. Add `POST /api/enrich-preview`.
- `ytk/ui/static/settings.html` — MODIFY. Tone field + preview button.
- Tests: `tests/test_enrich_compose.py`, `tests/test_enrich_node.py`, `tests/test_enrich_cod.py`, `tests/test_enrich_tone_config.py`, `tests/test_enrich_eval.py`.

---

### Task 1: Compose the system prompt from fragments

**Files:**
- Modify: `ytk/enrich.py` (add fragments + `_build_system`; keep `_YT_SYSTEM` etc. for now)
- Test: `tests/test_enrich_compose.py`

**Interfaces:**
- Produces: `BASE_SKELETON: str`, `SOURCE_BIAS: dict[str, str]` (keys: `youtube, tiktok, instagram, web, journal`), `_TONE_WRAPPER: str`, `_build_system(source: str, tone: str = "") -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enrich_compose.py
import pytest
from ytk.enrich import BASE_SKELETON, SOURCE_BIAS, _build_system

SOURCES = ["youtube", "tiktok", "instagram", "web", "journal"]

def test_every_source_has_a_bias_fragment():
    assert set(SOURCE_BIAS) == set(SOURCES)

@pytest.mark.parametrize("source", SOURCES)
def test_build_system_includes_skeleton_and_bias(source):
    sys = _build_system(source)
    assert BASE_SKELETON in sys
    assert SOURCE_BIAS[source] in sys

def test_tone_prefaces_system_above_skeleton():
    sys = _build_system("youtube", tone="terse and technical")
    assert sys.index("terse and technical") < sys.index(BASE_SKELETON)

def test_no_tone_omits_preamble():
    assert _build_system("web") == _build_system("web", tone="   ")

def test_youtube_bias_keeps_selective_frame_reading():
    assert "ONLY when" in SOURCE_BIAS["youtube"]

def test_instagram_bias_reads_every_slide_and_empties_moments():
    assert "EVERY slide" in SOURCE_BIAS["instagram"]
    assert "empty" in SOURCE_BIAS["instagram"].lower()

def test_unknown_source_raises():
    with pytest.raises(KeyError):
        _build_system("podcast")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_enrich_compose.py -q`
Expected: FAIL with ImportError (BASE_SKELETON/SOURCE_BIAS/_build_system not defined).

- [ ] **Step 3: Write minimal implementation**

In `ytk/enrich.py`, add above the existing `enrich`:

```python
BASE_SKELETON = """\
You are a research assistant helping someone build a personal reference library. \
They consume the content themselves; your job is to make it retrievable six months later, \
when they remember something specific happened and want to find it fast. Return a JSON object \
matching the provided schema.

thesis
  One precise sentence capturing what the content actually does or argues. Name the specific thing \
  built, configured, demonstrated, or the actual position taken. Never use the word "explores". Never be vague.

summary
  3-5 sentences for someone who already consumed it and wants a sharp reminder. Name tools, commands, \
  libraries, and techniques concretely, not just topics. Never start with "The video" or "In this".

key_concepts
  Terms, tools, commands, APIs, or techniques that appear and are worth knowing. For each: the name, a \
  colon, then one sentence on how it was used HERE (not a general definition). Prioritize what someone \
  might ask about later ("how did they use X?").

insights
  2-3 specific things worth remembering: a surprising technique, a non-obvious tradeoff, a gotcha, an \
  approach that differed from convention. Each a complete, actionable sentence. Not trivia.

interest_tags
  Flat list of topic labels. Lowercase, hyphenated. 3-8 tags.

key_moments
  Moments worth jumping back to; descriptions specific enough to find from memory (name the thing being \
  done, not just the topic).\
"""

_TONE_WRAPPER = "Write in this voice, without sacrificing specificity or faithfulness:\n{tone}\n"

SOURCE_BIAS = {
    "youtube": (
        "SOURCE: a YouTube transcript plus metadata, and optionally file paths to extracted frames.\n"
        "Read a frame with the Read tool ONLY when the transcript around that timestamp references "
        "something visual you cannot resolve from text (a diagram, UI state, on-screen code). Skip frames "
        "that only confirm the transcript. Do not read every frame.\n"
        "key_moments: use MM:SS timestamps when inferable from chapters or transcript position."
    ),
    "tiktok": (
        "SOURCE: a short-form TikTok. It is visual-first and often under 60s; the transcript may be sparse, "
        "inaccurate, or mostly music. Read EVERY provided frame with the Read tool; on-screen text/UI/code/"
        "product shown is usually the real content. Treat caption and transcript as supplementary.\n"
        "key_moments: leave empty ([]) unless the transcript has clear timestamped beats."
    ),
    "instagram": (
        "SOURCE: an Instagram post: a caption plus carousel slide images. Read EVERY slide with the Read tool; "
        "read every visible word. Treat slide content as at least as important as the caption.\n"
        "key_moments: leave empty ([]). Instagram posts have no timestamps."
    ),
    "web": (
        "SOURCE: a web article (title, author, date, url, body text).\n"
        "key_moments: leave empty ([]). Articles have no timestamps."
    ),
    "journal": (
        "SOURCE: the user's own self-chat notes, a stream of thoughts/ideas/questions. Preserve the texture "
        "of their thinking; name the specific projects, tools, and ideas they mention. This is their own "
        "capture, not third-party content.\n"
        "key_moments: use \"note N\" as the timestamp field, quoting or closely paraphrasing the thought."
    ),
}

def _build_system(source: str, tone: str = "") -> str:
    bias = SOURCE_BIAS[source]  # KeyError on unknown source is intentional
    parts = []
    if tone.strip():
        parts.append(_TONE_WRAPPER.format(tone=tone.strip()))
    parts.append(BASE_SKELETON)
    parts.append(bias)
    return "\n\n".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_enrich_compose.py -q`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add ytk/enrich.py tests/test_enrich_compose.py
git commit -m "feat(enrich): compose system prompt from base skeleton + source bias + tone"
```

---

### Task 2: The `enrich_content` node; rewire the five wrappers

**Files:**
- Modify: `ytk/enrich.py` (add `enrich_content`; rewire `enrich`, `enrich_tiktok`, `enrich_instagram`)
- Modify: `ytk/ingest.py` (`enrich_web` delegates)
- Modify: `ytk/imessage.py` (`enrich_journal` delegates)
- Test: `tests/test_enrich_node.py`

**Interfaces:**
- Consumes: `_build_system` (Task 1), `_staged_images`, `run_structured`, `_note_block`, `_vocab_block` (existing).
- Produces: `enrich_content(content_block: str, source: str, *, user_note: str = "", visual_blocks: list[dict] | None = None, tone: str = "") -> Enrichment`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enrich_node.py
import ytk.enrich as e
from ytk.enrich import Enrichment

_STUB = {"thesis": "t", "summary": "s", "key_concepts": ["k: used"],
         "insights": ["i"], "interest_tags": ["go"], "key_moments": []}

def test_enrich_content_composes_system_and_returns_enrichment(monkeypatch):
    captured = {}
    def fake_run(system, user, schema, add_dirs=None, **kw):
        captured["system"] = system
        captured["user"] = user
        return _STUB
    monkeypatch.setattr(e, "run_structured", fake_run)
    out = e.enrich_content("Article body here", source="web", user_note="my angle")
    assert isinstance(out, Enrichment)
    assert e.SOURCE_BIAS["web"] in captured["system"]
    assert "Article body here" in captured["user"]
    assert "my angle" in captured["user"]  # _note_block appended

def test_enrich_wrapper_delegates_with_youtube_source(monkeypatch):
    captured = {}
    monkeypatch.setattr(e, "run_structured",
                        lambda s, u, sc, add_dirs=None, **kw: captured.update(system=s) or _STUB)
    e.enrich("the transcript", {"title": "T", "duration": 60})
    assert e.SOURCE_BIAS["youtube"] in captured["system"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_enrich_node.py -q`
Expected: FAIL (`enrich_content` not defined).

- [ ] **Step 3: Write minimal implementation**

Add `enrich_content` to `ytk/enrich.py`:

```python
def enrich_content(
    content_block: str,
    source: str,
    *,
    user_note: str = "",
    visual_blocks: list[dict] | None = None,
    tone: str = "",
) -> Enrichment:
    """Single enrichment node. Callers format their own content_block; this
    composes the system prompt for `source`, appends note + vocab to the user
    prompt, stages any images, and returns a validated Enrichment."""
    system = _build_system(source, tone)
    user = content_block + _note_block(user_note) + _vocab_block()
    with _staged_images(visual_blocks) as (frame_dir, frame_paths):
        if frame_paths:
            listing = "\n".join(f"  {p}" for p in frame_paths)
            user = f"{user}\n\nExtracted frames:\n{listing}\n"
        add_dirs = [frame_dir] if frame_dir else []
        data = run_structured(system, user, _SCHEMA, add_dirs=add_dirs)
        return Enrichment.model_validate(data)
```

Rewire `enrich` (keep its content-block build, drop the `run_structured` call):

```python
def enrich(transcript, metadata, visual_blocks=None, user_note="", tone=""):
    chapters_text = ""
    if metadata.get("chapters"):
        lines = [f"  {_fmt_ts(ch['start_time'])} — {ch['title']}" for ch in metadata["chapters"]]
        chapters_text = "\nChapters:\n" + "\n".join(lines)
    content_block = (
        f"Title: {metadata.get('title', '')}\n"
        f"Uploader: {metadata.get('uploader', '')}\n"
        f"Duration: {metadata.get('duration', 0)}s\n"
        f"Tags: {', '.join(metadata.get('tags', [])[:10])}{chapters_text}\n\n"
        f"Transcript:\n{transcript}\n"
    )
    return enrich_content(content_block, "youtube", user_note=user_note,
                          visual_blocks=visual_blocks, tone=tone)
```

Rewire `enrich_tiktok` and `enrich_instagram` identically: build their existing `text_block` as `content_block` (music line, slide count, etc. preserved), then `return enrich_content(content_block, "tiktok"/"instagram", user_note=user_note, visual_blocks=visual_blocks, tone=tone)`. In `ingest.py`, `enrich_web` builds its `content_block` and returns `enrich_content(content_block, "web", user_note=user_note)` (drop the manual `key_moments = []`; the web bias handles it). In `imessage.py`, `enrich_journal` builds the thread text as `content_block` and returns `enrich_content(content_block, "journal")`. Delete the now-unused `_YT_SYSTEM`, `_INSTAGRAM_SYSTEM`, `_TIKTOK_SYSTEM`, `_SYSTEM_WEB`, `_SYSTEM_JOURNAL`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_enrich_node.py tests/test_enrich_compose.py -q` then the full enrichment-related suite: `uv run pytest -k "enrich or instagram or tiktok or imessage or ingest" -q`
Expected: PASS; existing enrichment tests still green (behavior preserved).

- [ ] **Step 5: Commit**

```bash
git add ytk/enrich.py ytk/ingest.py ytk/imessage.py tests/test_enrich_node.py
git commit -m "feat(enrich): single enrich_content node; five wrappers delegate to it"
```

---

### Task 3: Chain-of-Density replaces the cap-of-8

**Files:**
- Modify: `ytk/enrich.py` (`BASE_SKELETON` key_concepts/key_moments guidance)
- Test: `tests/test_enrich_cod.py`

**Interfaces:**
- Consumes: `BASE_SKELETON` (Task 1). Produces: no new symbols; a behavior change in the skeleton text.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enrich_cod.py
from ytk.enrich import BASE_SKELETON

def test_no_flat_cap_of_eight():
    assert "Max 8" not in BASE_SKELETON
    assert "max 8" not in BASE_SKELETON.lower()

def test_has_densification_instruction():
    low = BASE_SKELETON.lower()
    assert "dense" in low or "densif" in low
    assert "missed" in low or "missing" in low  # the CoD "entities you left out" pass

def test_scales_to_content_length():
    assert "scale" in BASE_SKELETON.lower() or "as many as" in BASE_SKELETON.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_enrich_cod.py -q`
Expected: FAIL (skeleton still says "prioritize..." with no densification language, no cap change needed since Task 1 skeleton has no "Max 8" — adjust: Task 1 skeleton intentionally omitted the cap; this task adds the densification instruction).

- [ ] **Step 3: Write minimal implementation**

Replace the `key_concepts` paragraph in `BASE_SKELETON` with a Chain-of-Density directive:

```python
# in BASE_SKELETON, the key_concepts section becomes:
"""key_concepts
  Terms, tools, commands, APIs, or techniques that appear and are worth knowing. For each: the name, a \
  colon, then one sentence on how it was used HERE. Work in increasing density: first list the obvious \
  ones, then scan again for named specifics you missed (tools, flags, versions, people) and add them, \
  then merge into one list. Include as many as the content genuinely warrants and no filler; a long talk \
  may need 15 or more, a short clip only a few. Prioritize what someone might ask about later."""
```

Apply the same "as many as warranted, scale to length" phrasing to `key_moments`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_enrich_cod.py tests/test_enrich_compose.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ytk/enrich.py tests/test_enrich_cod.py
git commit -m "feat(enrich): Chain-of-Density key_concepts, remove the flat cap of 8"
```

---

### Task 4: Tone preamble config + wiring

**Files:**
- Modify: `ytk/config.py` (`HubConfig.enrich_tone`)
- Modify: `ytk/enrich.py` (default `tone` from config when caller omits it)
- Test: `tests/test_enrich_tone_config.py`

**Interfaces:**
- Consumes: `_build_system` (Task 1), `load_config` (existing).
- Produces: `HubConfig.enrich_tone: str`; `enrich_content` reads it when `tone == ""`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enrich_tone_config.py
import ytk.enrich as e
from ytk.config import Config

def test_config_has_enrich_tone_default_empty():
    assert Config().hub.enrich_tone == ""

def test_enrich_content_pulls_tone_from_config(monkeypatch):
    cfg = Config(); cfg.hub.enrich_tone = "terse and technical"
    monkeypatch.setattr(e, "load_config", lambda: cfg)
    captured = {}
    monkeypatch.setattr(e, "run_structured",
                        lambda s, u, sc, add_dirs=None, **kw: captured.update(system=s) or
                        {"thesis":"t","summary":"s","key_concepts":[],"insights":[],"interest_tags":[],"key_moments":[]})
    e.enrich_content("body", "web")
    assert "terse and technical" in captured["system"]

def test_explicit_tone_overrides_config(monkeypatch):
    cfg = Config(); cfg.hub.enrich_tone = "from config"
    monkeypatch.setattr(e, "load_config", lambda: cfg)
    captured = {}
    monkeypatch.setattr(e, "run_structured",
                        lambda s, u, sc, add_dirs=None, **kw: captured.update(system=s) or
                        {"thesis":"t","summary":"s","key_concepts":[],"insights":[],"interest_tags":[],"key_moments":[]})
    e.enrich_content("body", "web", tone="explicit")
    assert "explicit" in captured["system"] and "from config" not in captured["system"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_enrich_tone_config.py -q`
Expected: FAIL (`enrich_tone` missing; `load_config` not imported into enrich.py at module scope).

- [ ] **Step 3: Write minimal implementation**

In `ytk/config.py`, add to `HubConfig`:

```python
    enrich_tone: str = Field(
        default="",
        description="User voice preamble prefixed to every enrichment prompt. Shapes tone only; "
                    "anti-fluff and faithfulness rules always follow it and cannot be overridden.",
    )
```

In `ytk/enrich.py`, add `from .config import load_config` at module top, and in `enrich_content` default the tone:

```python
    if not tone:
        try:
            tone = load_config().hub.enrich_tone
        except Exception:
            tone = ""
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_enrich_tone_config.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ytk/config.py ytk/enrich.py tests/test_enrich_tone_config.py
git commit -m "feat(enrich): user-editable tone preamble via hub.enrich_tone config"
```

---

### Task 5: Harness fixtures

**Files:**
- Create: `ytk/enrich_eval.py`
- Test: `tests/test_enrich_eval.py`

**Interfaces:**
- Produces: `@dataclass Fixture(note_path: Path, source: str, transcript: str, enrichment: Enrichment)`; `load_fixtures(paths: list[Path] | None = None) -> list[Fixture]`. Default fixtures: a versioned list of 5 note paths stratified by source, stored as `FIXTURE_PATHS: list[Path]` (resolved under the vault sources dir).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enrich_eval.py
from pathlib import Path
from ytk import enrich_eval as ev

def test_load_fixtures_parses_transcript_and_enrichment(tmp_path):
    note = tmp_path / "n.md"
    note.write_text(
        "---\nurl: u\ntitle: T\n---\n## Thesis\nx\n## Commentary\ny\n"
        "## Key Concepts\n- a: b\n## Transcript\n<details>\n<summary>Raw</summary>\n\nHELLO WORLD\n</details>\n",
        encoding="utf-8")
    fx = ev.load_fixtures([note])
    assert len(fx) == 1
    assert "HELLO WORLD" in fx[0].transcript
    assert fx[0].enrichment.thesis == "x"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_enrich_eval.py::test_load_fixtures_parses_transcript_and_enrichment -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Write minimal implementation**

Create `ytk/enrich_eval.py` with `Fixture`, a markdown section parser (reuse the `## Section` regex pattern from `hub.py`/`scripts/rebuild_video_parts.py`), and `load_fixtures`. Parse `## Thesis`, `## Commentary` (fallback `## Summary`), `## Key Concepts` bullets, and the `## Transcript` details block into an `Enrichment` (key_moments/insights/tags best-effort) plus the raw transcript string. `source` inferred from the note's parent dir name.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_enrich_eval.py::test_load_fixtures_parses_transcript_and_enrichment -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ytk/enrich_eval.py tests/test_enrich_eval.py
git commit -m "feat(eval): enrichment fixtures loader"
```

---

### Task 6: Faithfulness (hand-rolled FActScore)

**Files:**
- Modify: `ytk/enrich_eval.py`
- Test: `tests/test_enrich_eval.py`

**Interfaces:**
- Consumes: `structured` from `ytk.sdk`, `Enrichment`.
- Produces: `@dataclass FaithScore(supported: int, inflated: int, unsupported: int, rate: float)` where `rate = (inflated + unsupported) / total`; `faithfulness(enrichment: Enrichment, transcript: str) -> FaithScore`. Internal pydantic `_ClaimVerdict(claim: str, label: Literal["supported","inflated","unsupported"])`, `_FaithResult(claims: list[_ClaimVerdict])`.

- [ ] **Step 1: Write the failing test**

```python
def test_faithfulness_counts_labels(monkeypatch):
    from ytk import enrich_eval as ev
    from ytk.enrich import Enrichment
    fake = ev._FaithResult(claims=[
        ev._ClaimVerdict(claim="uses wgpu", label="supported"),
        ev._ClaimVerdict(claim="builds a full OS", label="inflated"),
    ])
    monkeypatch.setattr(ev, "structured", lambda s, u, r, **kw: fake)
    enr = Enrichment(thesis="t", summary="s", key_concepts=["wgpu: gpu"],
                     insights=["builds a full OS"], interest_tags=[], key_moments=[])
    score = ev.faithfulness(enr, "transcript mentions wgpu")
    assert score.supported == 1 and score.inflated == 1
    assert score.rate == 0.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_enrich_eval.py::test_faithfulness_counts_labels -q`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Add the pydantic models and:

```python
from typing import Literal
from pydantic import BaseModel
from .sdk import structured

_FAITH_SYSTEM = ("Decompose the enrichment's key_concepts and insights into atomic factual claims. "
    "For each, judge it against the transcript: 'supported' (stated or demonstrated), 'inflated' "
    "(a kernel of truth oversold), or 'unsupported' (not in the transcript). Return every claim.")

def faithfulness(enrichment, transcript):
    body = "TRANSCRIPT:\n" + transcript[:18000] + "\n\nENRICHMENT:\n" + \
        "\n".join(enrichment.key_concepts + enrichment.insights)
    res = structured(_FAITH_SYSTEM, body, _FaithResult, model="claude-opus-4-8")
    s = sum(c.label == "supported" for c in res.claims)
    inf = sum(c.label == "inflated" for c in res.claims)
    uns = sum(c.label == "unsupported" for c in res.claims)
    total = max(1, len(res.claims))
    return FaithScore(s, inf, uns, (inf + uns) / total)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_enrich_eval.py::test_faithfulness_counts_labels -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ytk/enrich_eval.py tests/test_enrich_eval.py
git commit -m "feat(eval): hand-rolled FActScore faithfulness against the transcript"
```

---

### Task 7: Pairwise judge (Opus, order-swapped)

**Files:**
- Modify: `ytk/enrich_eval.py`
- Test: `tests/test_enrich_eval.py`

**Interfaces:**
- Consumes: `structured`, `Enrichment`.
- Produces: `@dataclass Verdict(winner: str, reasons: dict)` (`winner` in `"A"|"B"|"tie"`); `judge(a: Enrichment, b: Enrichment, transcript: str) -> Verdict`. Internal `_JudgeResult(winner: Literal["A","B","tie"], specificity: str, faithfulness: str, nonredundancy: str, retrievability: str)`. The rubric text lives in `_JUDGE_SYSTEM` verbatim from the spec's four dimensions.

- [ ] **Step 1: Write the failing test**

```python
def test_judge_counts_win_only_if_consistent_across_orders(monkeypatch):
    from ytk import enrich_eval as ev
    from ytk.enrich import Enrichment
    enr = lambda t: Enrichment(thesis=t, summary="s", key_concepts=[], insights=[],
                               interest_tags=[], key_moments=[])
    calls = []
    def fake(system, user, result, **kw):
        # first call A-then-B => "A" wins; swapped call B-then-A => "B" is the same enrichment => "A" (position2)
        calls.append(user)
        return ev._JudgeResult(winner=("A" if len(calls) == 1 else "B"),
                               specificity="x", faithfulness="x", nonredundancy="x", retrievability="x")
    monkeypatch.setattr(ev, "structured", fake)
    v = ev.judge(enr("alpha"), enr("beta"), "transcript")
    assert v.winner == "A"  # A won in order 1, and won (as position B) in swapped order 2

def test_judge_inconsistent_is_tie(monkeypatch):
    from ytk import enrich_eval as ev
    from ytk.enrich import Enrichment
    enr = Enrichment(thesis="t", summary="s", key_concepts=[], insights=[], interest_tags=[], key_moments=[])
    monkeypatch.setattr(ev, "structured",
                        lambda s, u, r, **kw: ev._JudgeResult(winner="A", specificity="",
                        faithfulness="", nonredundancy="", retrievability=""))
    # "A" both times means position-1 always wins => position bias => tie
    assert ev.judge(enr, enr, "t").winner == "tie"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_enrich_eval.py -k judge -q`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

```python
_JUDGE_SYSTEM = ("You compare two enrichments (A and B) of the same source, for a personal retrieval "
  "library. Prefer the one that better satisfies, in priority order: (1) named specificity (concrete "
  "tools, commands, APIs, papers, numbers, proper nouns; fewer abstract topic-words); (2) faithfulness "
  "(no claims beyond what the source states; break ties toward the more conservative one); (3) "
  "non-redundancy (adds information vs restating the summary); (4) retrievability (would a reader who "
  "half-remembers the content find it). Verbosity is NOT a merit. Return the winner (A, B, or tie) and "
  "one line of reasoning per dimension.")

def _one_judgment(first, second, transcript):
    body = (f"TRANSCRIPT:\n{transcript[:12000]}\n\nA:\n{first.model_dump_json()}\n\nB:\n{second.model_dump_json()}")
    return structured(_JUDGE_SYSTEM, body, _JudgeResult, model="claude-opus-4-8")

def judge(a, b, transcript):
    r1 = _one_judgment(a, b, transcript)          # A=a, B=b
    r2 = _one_judgment(b, a, transcript)          # A=b, B=a (swapped)
    # a wins iff it won in both orders (as "A" in r1, as "B" in r2)
    a_wins = r1.winner == "A" and r2.winner == "B"
    b_wins = r1.winner == "B" and r2.winner == "A"
    winner = "A" if a_wins else "B" if b_wins else "tie"
    return Verdict(winner=winner, reasons={"order1": r1.model_dump(), "order2": r2.model_dump()})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_enrich_eval.py -k judge -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ytk/enrich_eval.py tests/test_enrich_eval.py
git commit -m "feat(eval): order-swapped Opus pairwise judge with fixed rubric"
```

---

### Task 8: Bootstrap win-rate CI

**Files:**
- Modify: `ytk/enrich_eval.py`
- Test: `tests/test_enrich_eval.py`

**Interfaces:**
- Produces: `bootstrap_winrate(wins: list[float], n_resamples: int = 2000, seed: int = 0) -> tuple[float, float, float]` returning `(point, lo, hi)` at 95%. `wins` is per-note {1.0 win, 0.5 tie, 0.0 loss}. Pure (seeded); no LLM.

- [ ] **Step 1: Write the failing test**

```python
def test_bootstrap_wider_interval_at_smaller_n():
    from ytk.enrich_eval import bootstrap_winrate
    small = bootstrap_winrate([1.0, 1.0, 0.0, 1.0, 0.0])
    large = bootstrap_winrate([1.0, 1.0, 0.0, 1.0, 0.0] * 20)
    assert 0.0 <= small[1] <= small[0] <= small[2] <= 1.0
    assert (small[2] - small[1]) > (large[2] - large[1])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_enrich_eval.py -k bootstrap -q`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

```python
import random, statistics

def bootstrap_winrate(wins, n_resamples=2000, seed=0):
    if not wins:
        return (0.0, 0.0, 0.0)
    rng = random.Random(seed)
    n = len(wins)
    means = sorted(statistics.mean(rng.choice(wins) for _ in range(n)) for _ in range(n_resamples))
    lo = means[int(0.025 * n_resamples)]
    hi = means[int(0.975 * n_resamples) - 1]
    return (statistics.mean(wins), lo, hi)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_enrich_eval.py -k bootstrap -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ytk/enrich_eval.py tests/test_enrich_eval.py
git commit -m "feat(eval): seeded bootstrap CI on the win-rate"
```

---

### Task 9: Leaderboard ledger

**Files:**
- Modify: `ytk/enrich_eval.py`
- Test: `tests/test_enrich_eval.py`

**Interfaces:**
- Produces: `LEDGER_PATH = Path.home() / ".ytk" / "enrich_eval_ledger.json"`; `ledger_append(entry: dict, path: Path = LEDGER_PATH) -> None` (atomic write, tolerates missing/corrupt file, same pattern as `reels.save_state`); `ledger_read(path: Path = LEDGER_PATH) -> list[dict]`.

- [ ] **Step 1: Write the failing test**

```python
def test_ledger_round_trip_and_tolerates_empty(tmp_path):
    from ytk import enrich_eval as ev
    p = tmp_path / "ledger.json"
    ev.ledger_append({"tone": "x", "winrate": 0.6}, p)
    ev.ledger_append({"tone": "y", "winrate": 0.4}, p)
    rows = ev.ledger_read(p)
    assert [r["tone"] for r in rows] == ["x", "y"]
    p.write_text("", encoding="utf-8")  # corrupt/empty
    assert ev.ledger_read(p) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_enrich_eval.py -k ledger -q`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Mirror `reels.save_state`: read-existing-or-empty, append, write to `.tmp`, `os.replace`. `ledger_read` returns `[]` on missing/empty/corrupt.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_enrich_eval.py -k ledger -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ytk/enrich_eval.py tests/test_enrich_eval.py
git commit -m "feat(eval): atomic leaderboard ledger"
```

---

### Task 10: `run_eval` orchestrator + `ytk enrich-eval` CLI

**Files:**
- Modify: `ytk/enrich_eval.py`, `ytk/cli.py`
- Test: `tests/test_enrich_eval.py`

**Interfaces:**
- Consumes: `load_fixtures`, `enrich_content`, `judge`, `faithfulness`, `bootstrap_winrate`, `ledger_append`.
- Produces: `run_eval(challenger_tone: str, fixtures: list[Fixture] | None = None) -> dict` returning `{winrate, ci: [lo,hi], faith_delta, n, per_note: [...]}`. Champion = current config tone; challenger = `challenger_tone`. For each fixture: regenerate champion + challenger enrichment via `enrich_content(fx.transcript, fx.source, tone=...)`, judge them, score faithfulness of each; aggregate; append to ledger.

- [ ] **Step 1: Write the failing test**

```python
def test_run_eval_aggregates_and_writes_ledger(monkeypatch, tmp_path):
    from ytk import enrich_eval as ev
    from ytk.enrich import Enrichment
    fx = [ev.Fixture(note_path=tmp_path/"n.md", source="web", transcript="T",
                     enrichment=Enrichment(thesis="t", summary="s", key_concepts=[],
                     insights=[], interest_tags=[], key_moments=[]))]
    monkeypatch.setattr(ev, "enrich_content",
        lambda content, source, **kw: fx[0].enrichment)
    monkeypatch.setattr(ev, "judge",
        lambda a, b, t: ev.Verdict(winner="B", reasons={}))   # challenger (B) wins
    monkeypatch.setattr(ev, "faithfulness",
        lambda e, t: ev.FaithScore(2, 0, 0, 0.0))
    monkeypatch.setattr(ev, "LEDGER_PATH", tmp_path / "ledger.json")
    out = ev.run_eval("terse", fixtures=fx)
    assert out["n"] == 1 and out["winrate"] == 1.0
    assert ev.ledger_read(tmp_path / "ledger.json")[0]["winrate"] == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_enrich_eval.py -k run_eval -q`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Implement `run_eval`: champion tone from `load_config().hub.enrich_tone`; per fixture, generate both, map judge winner (challenger=B) to `1.0/0.5/0.0`, compute faith for each, aggregate with `bootstrap_winrate`, `faith_delta = champion_rate - challenger_rate`, append summary to ledger, return dict. Then add the CLI in `cli.py`:

```python
@cli.command(name="enrich-eval")
@click.option("--tone", required=True, help="Challenger tone preamble to test.")
def enrich_eval_cmd(tone):
    from .enrich_eval import run_eval
    r = run_eval(tone)
    click.echo(f"n={r['n']} winrate={r['winrate']:.2f} 95% CI [{r['ci'][0]:.2f}, {r['ci'][1]:.2f}] "
               f"faith_delta={r['faith_delta']:+.3f}")
    click.echo("Smoke gate only (n small); not a ship decision.")
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_enrich_eval.py -q`
Expected: PASS (all harness tests).

- [ ] **Step 5: Commit**

```bash
git add ytk/enrich_eval.py ytk/cli.py tests/test_enrich_eval.py
git commit -m "feat(eval): run_eval orchestrator and ytk enrich-eval command"
```

---

### Task 11: Settings tone field + preview endpoint

**Files:**
- Modify: `ytk/ui/server.py` (`POST /api/enrich-preview`)
- Modify: `ytk/ui/static/settings.html` (tone textarea + preview button)
- Test: `tests/test_enrich_eval.py` (endpoint), or `tests/test_settings.py`

**Interfaces:**
- Consumes: `run_eval`. Produces: `POST /api/enrich-preview {tone: str} -> {winrate, ci, faith_delta, n}`.

- [ ] **Step 1: Write the failing test**

```python
def test_enrich_preview_endpoint(client, hub, monkeypatch):
    import ytk.ui.server as srv
    monkeypatch.setattr("ytk.enrich_eval.run_eval",
        lambda tone, fixtures=None: {"winrate": 0.8, "ci": [0.4, 1.0], "faith_delta": 0.0, "n": 5})
    r = client.post("/api/enrich-preview", json={"tone": "terse"})
    assert r.status_code == 200
    assert r.json()["winrate"] == 0.8
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_enrich_eval.py -k preview -q`
Expected: FAIL (404).

- [ ] **Step 3: Write minimal implementation**

Add to `ytk/ui/server.py`:

```python
class EnrichPreviewRequest(BaseModel):
    tone: str = ""

@app.post("/api/enrich-preview")
def enrich_preview_api(req: EnrichPreviewRequest):
    from ytk.enrich_eval import run_eval
    try:
        return run_eval(req.tone)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
```

In `settings.html`, add an `enrich_tone` textarea bound to `hub.enrich_tone` (existing settings-binding pattern), plus a "Preview on 5 notes" button that POSTs to `/api/enrich-preview` and renders `winrate / CI / faith_delta` with a "smoke gate, not a ship decision" caption.

- [ ] **Step 4: Run tests + full suite**

Run: `uv run pytest -q`
Expected: PASS (all, including existing UI em-dash guard).

- [ ] **Step 5: Commit**

```bash
git add ytk/ui/server.py ytk/ui/static/settings.html tests/test_enrich_eval.py
git commit -m "feat(eval): settings tone field + preview-on-5-notes endpoint"
```

---

## Self-Review

- **Spec coverage:** node (T1-2), tone preamble sole editable layer (T1,4,11), Chain-of-Density (T3), five paths delegate (T2), Enrichment schema unchanged (T2), harness champion-vs-challenger (T10), judge Opus order-swapped (T7), FActScore (T6), bootstrap CI (T8), ledger (T9), CLI + settings preview (T10-11), recall@k excluded (never introduced), out-of-scope tracked (#46-49, not in plan). Covered.
- **Placeholder scan:** all code steps carry real code; prompt-extraction steps specify exact transformations and assert on marker substrings.
- **Type consistency:** `enrich_content` signature identical across T2/T4/T10; `Verdict.winner`, `FaithScore.rate`, `bootstrap_winrate` tuple, `run_eval` dict keys (`winrate/ci/faith_delta/n`) consistent T7-T11.
