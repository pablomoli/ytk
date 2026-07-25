# pyright: basic
# Not strict-clean yet (#122). Delete these two lines once the module
# passes strict — the list of files carrying them only shrinks.
"""AI enrichment of YouTube / Instagram content via the Claude Agent SDK.

Runs enrichment through Claude Code (Agent SDK) instead of the Anthropic API
directly. Uses the user's Claude Code subscription auth rather than API credits.

Images are materialized to a temporary directory and referenced by path in the
prompt; Claude Code reads them on demand via the Read tool. For YouTube videos,
the model is instructed to read frames only when the surrounding transcript is
ambiguous about a visual detail. For Instagram posts, every slide must be read.
"""

from __future__ import annotations

import base64
import shutil
import tempfile
import uuid
from pathlib import Path

from pydantic import BaseModel, field_validator, model_validator

from .config import load_config
from .sdk import run_structured


class KeyMoment(BaseModel):
    timestamp: str
    description: str


# Recommendation kinds that get their own surface + {kind}-rec tag.
REC_KINDS = ("movie", "show", "anime", "book", "manga")


class Recommendation(BaseModel):
    kind: str  # one of REC_KINDS
    title: str
    creator: str | None = None  # director / author / studio, when stated
    reason: str | None = None  # why it was recommended, when stated

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, kind: str) -> str:
        k = (kind or "").strip().lower()
        return k if k in REC_KINDS else "movie"


class Enrichment(BaseModel):
    thesis: str
    summary: str
    key_concepts: list[str]
    insights: list[str]
    interest_tags: list[str]
    key_moments: list[KeyMoment]
    recommendations: list[Recommendation] = []

    @field_validator("interest_tags")
    @classmethod
    def _canonical_tags(cls, tags: list[str]) -> list[str]:
        """Normalize and alias-resolve at birth so every downstream consumer
        (note frontmatter, Chroma metadata, filters) sees canonical tags."""
        import re

        from .config import tag_aliases

        aliases = tag_aliases()
        out: list[str] = []
        for t in tags:
            t = re.sub(r"\s+", "-", t.strip().lower())
            t = aliases.get(t, t)
            if t and t not in out:
                out.append(t)
        return out

    @model_validator(mode="after")
    def _tag_recommendations(self) -> Enrichment:
        """Derive {kind}-rec tags from recommendations deterministically.

        The tag is what a note is filtered by on the recs surface; deriving it in
        code (rather than trusting the model to also remember to tag) guarantees
        every note carrying a recommendation carries the matching tag, and that
        the two never disagree. Tags coexist with the content tags."""
        for rec in self.recommendations:
            tag = f"{rec.kind}-rec"
            if tag not in self.interest_tags:
                self.interest_tags.append(tag)
        return self


_SCHEMA = Enrichment.model_json_schema()


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
  colon, then one sentence on how it was used HERE. Work in passes to densify the list: first pass \
  identifies obvious ones, second pass scans again for named specifics you missed (tools, flags, \
  versions, people) and adds them, final pass merges into one clean list. Include as many as the \
  content genuinely warrants and no filler; a long talk may need 15 or more, a short clip only a few. \
  Prioritize what someone might ask about later.

insights
  2-3 specific things worth remembering: a surprising technique, a non-obvious tradeoff, a gotcha, an \
  approach that differed from convention. Each a complete, actionable sentence. Not trivia.

interest_tags
  Flat list of topic labels. Lowercase, hyphenated. 3-8 tags.

key_moments
  Moments worth jumping back to; descriptions specific enough to find from memory (name the thing being \
  done, not just the topic). Include as many as the content warrants; scale to length.

recommendations
  Any specific movie, TV show, anime, book, or manga that the content recommends OR discusses \
  substantively enough that the user might want to watch/read it. For each: kind (movie | show | anime \
  | book | manga), title, creator (director/author/studio if stated, else null), and reason (why it was \
  brought up, if stated, else null). Distinguish anime from live-action show, and manga from book. Use \
  the title as actually named; do not invent titles. Empty list ([]) when nothing is recommended — this \
  is the common case, do not force entries.\
"""

_TONE_WRAPPER = "Write in this voice, without sacrificing specificity or faithfulness:\n{tone}\n"

SOURCE_BIAS = {
    "youtube": (
        "SOURCE: a YouTube transcript plus metadata, and optionally file paths to extracted frames.\n"
        "Read a frame with the Read tool ONLY when the transcript around that timestamp references "
        "something visual you cannot resolve from text (a diagram, UI state, on-screen code). Skip frames "
        "that only confirm the transcript. Do not read every frame.\n"
        "The uploader's description, when present, is a mix of real signal (tool and library names, "
        "repo and doc links, chapter markers, hashtags naming the topic) and boilerplate (sponsor reads, "
        "affiliate codes, merch, socials, patreon). Mine it for named specifics the spoken transcript "
        "never spells out — correct spellings, versions, project names, URLs — and ignore the "
        "promotional filler. Never let a sponsor become a key concept, and never describe the video as "
        "being about something only the sponsor block mentions.\n"
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
    "instagram_reel": (
        "SOURCE: an Instagram reel — a short video. The provided images are sampled video frames, "
        "NOT carousel slides. Read EVERY provided frame with the Read tool; on-screen text/UI/code/product "
        "shown is often the real content. The Whisper transcript may be sparse, inaccurate, or music-only; "
        "treat transcript, on-screen text, motion context, and caption as complementary evidence.\n"
        "Separate captured evidence from inference: only name tools, stacks, or techniques that are shown "
        "or spoken. If the capture status reports missing inputs, say what is missing instead of guessing "
        "what the video probably contained.\n"
        "key_moments: use M:SS timestamps from the transcript when it has clear beats; otherwise leave empty ([])."
    ),
    "web": (
        "SOURCE: a web article (title, author, date, url, body text).\n"
        "key_moments: leave empty ([]). Articles have no timestamps."
    ),
    "reddit": (
        "SOURCE: a Reddit post from a subreddit — a title, either self-text or a link to external "
        "content, plus the top comments. The discussion is first-class: comments often carry the "
        "correction, the caveat, or the actual answer the thread is remembered for, so weigh them "
        "alongside the post itself and name specific claims made in them.\n"
        "key_moments: leave empty ([]). Reddit posts have no timestamps."
    ),
    "journal": (
        "SOURCE: the user's own self-chat notes, a stream of thoughts/ideas/questions. Preserve the texture "
        "of their thinking; name the specific projects, tools, and ideas they mention. This is their own "
        "capture, not third-party content.\n"
        'key_moments: use "note N" as the timestamp field, quoting or closely paraphrasing the thought.'
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


def _note_block(user_note: str) -> str:
    """Steering section injected when the user attached a thought at ingest.

    The user's note is top-down attention: it biases what the summary, key
    concepts, and tags emphasize, without replacing the content analysis.
    """
    if not user_note.strip():
        return ""
    return (
        "\nThe user saved this with their own note. The note is the reason this "
        "content is in their knowledge base, and it OUTRANKS the creator's own "
        "framing. When the note reframes the content (uses it for a different "
        "purpose than the creator intended), make the user's angle the organizing "
        "frame: the thesis states what the content offers FOR THE USER'S PURPOSE, "
        "the summary leads with the user's angle and treats the creator's "
        "narrative as supporting detail, and key concepts, insights, and tags are "
        "selected for usefulness to the user's stated intent. Only when the note "
        "merely reacts to the content (agreement, a memory hook) should the "
        "creator's framing lead.\nUser note:\n"
        f"{user_note.strip()}\n"
    )


DESCRIPTION_PROMPT_LIMIT = 6000


def _description_block(description: str) -> str:
    """The uploader's description, as prompt input (issue #105).

    This is the only route by which a description's meaning reaches the vector
    space: the embedded document is thesis + summary, so whatever the model
    picks up here — tool names, chapter markers, correct spellings — is
    embedded, while the raw text never is. Long tails of affiliate links and
    timestamps carry no extra signal, so the block is capped.
    """
    text = (description or "").strip()
    if not text:
        return ""
    if len(text) > DESCRIPTION_PROMPT_LIMIT:
        text = text[:DESCRIPTION_PROMPT_LIMIT] + "\n[... description truncated ...]"
    return f"\nUploader's description (mixes real signal with sponsor boilerplate):\n{text}\n"


_VOCAB_CACHE: list[str] | None = None


def tag_vocabulary() -> list[str]:
    """Canonical tag vocabulary: curated tags (config hub.tags + UI-created
    custom tags) followed by the most-used tags already indexed in Chroma.
    Cached per process so batch ingests do not rescan Chroma per item."""
    global _VOCAB_CACHE
    if _VOCAB_CACHE is None:
        from . import reels, store
        from .config import load_config

        curated = list(load_config().hub.tags)
        try:
            curated += reels.load_state(reels.STATE_PATH).custom_tags
        except Exception:
            pass
        _VOCAB_CACHE = list(dict.fromkeys([*curated, *store.top_tags(40)]))
    return _VOCAB_CACHE


def _vocab_block() -> str:
    """Vocabulary section injected into every enrichment prompt (issue #15).

    A prompt nudge, not a schema constraint: hard-constraining interest_tags
    to an enum would make genuinely new topics untaggable, which is worse
    than the spelling drift this prevents. Must never break an ingest."""
    try:
        vocab = tag_vocabulary()
    except Exception:
        return ""
    if not vocab:
        return ""
    return (
        "\nExisting tag vocabulary. Reuse an existing tag whenever one fits; "
        "coin a new tag only when none does:\n"
        f"{', '.join(vocab)}\n"
    )


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
    if not tone:
        try:
            tone = load_config().hub.enrich_tone
        except Exception:
            tone = ""
    system = _build_system(source, tone)
    user = content_block + _note_block(user_note) + _vocab_block()
    with _staged_images(visual_blocks) as (frame_dir, frame_paths):
        if frame_paths:
            listing = "\n".join(f"  {p}" for p in frame_paths)
            user = f"{user}\n\nExtracted frames:\n{listing}\n"
        add_dirs = [frame_dir] if frame_dir else []
        data = run_structured(system, user, _SCHEMA, add_dirs=add_dirs)
        return Enrichment.model_validate(data)


def enrich(
    transcript: str,
    metadata: dict,
    visual_blocks: list[dict] | None = None,
    user_note: str = "",
    tone: str = "",
) -> Enrichment:
    """Enrich a YouTube transcript via Claude Code (Agent SDK)."""
    chapters_text = ""
    if metadata.get("chapters"):
        lines = [f"  {_fmt_ts(ch['start_time'])} — {ch['title']}" for ch in metadata["chapters"]]
        chapters_text = "\nChapters:\n" + "\n".join(lines)

    content_block = f"""\
Title: {metadata.get("title", "")}
Uploader: {metadata.get("uploader", "")}
Duration: {metadata.get("duration", 0)}s
Tags: {", ".join(metadata.get("tags", [])[:10])}{chapters_text}
{_description_block(metadata.get("description", ""))}
Transcript:
{transcript}
"""
    return enrich_content(
        content_block, "youtube", user_note=user_note, visual_blocks=visual_blocks, tone=tone
    )


def enrich_tiktok(
    post: dict,
    transcript: str,
    visual_blocks: list[dict] | None = None,
    user_note: str = "",
    tone: str = "",
) -> Enrichment:
    """Enrich a TikTok with a visual-first, short-form-aware prompt.

    `post` is a dict with title, description, username, duration, music.
    """
    transcript_block = (
        f"Whisper transcript (may be inaccurate or sparse):\n{transcript}"
        if transcript.strip()
        else "Whisper transcript: (none — likely no speech or music-only)"
    )
    music_line = f"Music: {post['music']}\n" if post.get("music") else ""
    content_block = (
        f"Author: @{post.get('username', '')}\n"
        f"Title: {post.get('title', '')}\n"
        f"Duration: {post.get('duration', 0)}s\n"
        f"{music_line}"
        f"\nCaption / description:\n{post.get('description', '')}\n\n"
        f"{transcript_block}\n"
    )
    return enrich_content(
        content_block, "tiktok", user_note=user_note, visual_blocks=visual_blocks, tone=tone
    )


def enrich_instagram(
    caption: str,
    username: str,
    slide_count: int,
    visual_blocks: list[dict],
    user_note: str = "",
    tone: str = "",
) -> Enrichment:
    """Enrich an Instagram post with a carousel-aware prompt."""
    content_block = f"""\
Author: @{username}
Slide count: {slide_count}

Caption:
{caption}
"""
    return enrich_content(
        content_block, "instagram", user_note=user_note, visual_blocks=visual_blocks, tone=tone
    )


def enrich_instagram_reel(
    caption: str,
    username: str,
    duration: float | None,
    frame_count: int,
    transcript_segments: list[dict],
    transcript_status: str,
    visual_blocks: list[dict] | None = None,
    user_note: str = "",
    tone: str = "",
) -> Enrichment:
    """Enrich an Instagram reel with a video-aware prompt.

    The content block states exactly what was captured (frames, transcript)
    and what failed, so the model never concludes "no content" from a
    carousel-shaped prompt that was lying about the medium.
    """
    if transcript_status == "ok" and transcript_segments:
        lines = "\n".join(f"[{_fmt_ts(s['start'])}] {s['text']}" for s in transcript_segments)
        transcript_block = f"Whisper transcript (may be inaccurate or sparse):\n{lines}"
    elif transcript_status == "no_speech":
        transcript_block = (
            "Whisper transcript: (none — no speech detected; likely music-only or silent)"
        )
    elif transcript_status == "failed":
        transcript_block = "Whisper transcript: (unavailable — transcription failed; do not assume the video had no speech)"
    else:
        transcript_block = "Whisper transcript: (not attempted)"

    frames_line = (
        f"Sampled video frames provided: {frame_count}"
        if frame_count
        else "Sampled video frames: (none — frame extraction failed; do not assume the video was empty)"
    )
    duration_line = f"Duration: {int(duration)}s\n" if duration else ""

    content_block = (
        f"Author: @{username}\n"
        f"Media type: video reel\n"
        f"{duration_line}"
        f"{frames_line}\n"
        f"\nCaption:\n{caption}\n\n"
        f"{transcript_block}\n"
    )
    return enrich_content(
        content_block, "instagram_reel", user_note=user_note, visual_blocks=visual_blocks, tone=tone
    )


class _staged_images:
    """Context manager — writes Anthropic-format image blocks to a temp dir."""

    def __init__(self, visual_blocks: list[dict] | None):
        self.visual_blocks = visual_blocks or []
        self.dir: Path | None = None

    def __enter__(self) -> tuple[Path | None, list[Path]]:
        if not self.visual_blocks:
            return None, []
        self.dir = Path(tempfile.mkdtemp(prefix=f"ytk-enrich-{uuid.uuid4().hex[:8]}-"))
        paths: list[Path] = []
        for i, block in enumerate(self.visual_blocks):
            path = _materialize_image(block, self.dir, i)
            if path is not None:
                paths.append(path)
        return self.dir, paths

    def __exit__(self, *exc_info) -> None:
        if self.dir is not None:
            shutil.rmtree(self.dir, ignore_errors=True)


def _materialize_image(block: dict, out_dir: Path, index: int) -> Path | None:
    """Write an Anthropic API image content block to a file. Returns the path.

    Handles base64 source blocks (the common case from vision.image_blocks).
    URL source blocks are skipped — Claude Code can't Read them locally.
    """
    if block.get("type") != "image":
        return None
    source = block.get("source", {})
    if source.get("type") != "base64":
        return None
    media = source.get("media_type", "image/jpeg")
    ext = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/gif": "gif",
        "image/webp": "webp",
    }.get(media, "jpg")
    data = source.get("data")
    if not data:
        return None
    path = out_dir / f"frame-{index:02d}.{ext}"
    path.write_bytes(base64.b64decode(data))
    return path


def _fmt_ts(seconds: int | float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
