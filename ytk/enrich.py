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

from pydantic import BaseModel

from .sdk import run_structured


class KeyMoment(BaseModel):
    timestamp: str
    description: str


class Enrichment(BaseModel):
    thesis: str
    summary: str
    key_concepts: list[str]
    insights: list[str]
    interest_tags: list[str]
    key_moments: list[KeyMoment]


_YT_SYSTEM = """\
You are a detailed research assistant helping someone who already watches a lot of YouTube videos \
build a personal reference library. The person watches the videos themselves — your job is to make \
them retrievable and searchable later. Think: "six months from now, they remember something \
specific happened in this video and want to find it fast."

You will receive a transcript and metadata for a video, and optionally file paths to extracted \
frames. Return a JSON object matching the provided schema.

thesis
  One precise sentence capturing what the video actually does or argues. For tutorials and demos, \
name the specific thing being built, configured, or demonstrated. For opinion/essay videos, state \
the actual position. Never use the word "explores". Never be vague about the subject matter.

summary
  3–5 sentences of commentary written for someone who watched it and wants a sharp reminder of \
what happened and why it mattered. Include the specific approach taken, any tools or techniques \
demonstrated, and anything that stood out as unexpected or particularly well done. Name things \
concretely — tools, commands, libraries, techniques — not just topics. \
Never start with "The video" or "In this video".

key_concepts
  Terms, tools, commands, APIs, or techniques that appear in the video and are worth knowing. \
For each: write the name, then a colon, then one sentence explaining exactly how it was used \
in this video — not a general definition. Prioritize things someone might ask about later \
("how did they use X?"). Max 8 items.

insights
  2–3 specific things worth remembering: a surprising technique, a non-obvious tradeoff the \
speaker called out, a gotcha demonstrated, or an approach that differed from the conventional way. \
Each should be a complete sentence a person could act on or reference. Not trivia.

interest_tags
  Flat list of topic labels (e.g. "geospatial", "go", "creative-coding", "machine-learning"). \
Lowercase, hyphenated. 3–8 tags.

key_moments
  Up to 8 moments a viewer might want to jump back to. Use MM:SS timestamps when inferable from \
chapters or transcript position. Descriptions should be specific enough to find the moment from memory — \
name the thing being done, not just the topic ("sets up the watcher goroutine with a done channel" \
not "concurrency explanation").

If frame paths are provided, read a frame with the Read tool ONLY when the transcript around that \
timestamp references something visual you cannot resolve from text alone (a diagram, a UI state, \
code on screen, a specific tool being demonstrated). Skip frames that would only confirm what the \
transcript already states clearly. Do not read every frame.\
"""


_INSTAGRAM_SYSTEM = """\
You are a research assistant helping someone build a personal reference library from social media content.
You will receive an Instagram post: a caption (the text of the post) and file paths to one or more \
carousel slide images.

IMPORTANT: The images are carousel slides — they contain text, screenshots, code, or design examples that \
are the primary content of the post. Read EVERY slide with the Read tool. Read every word visible in every \
slide carefully. Treat the slide content as at least as important as the caption.

Return a JSON object matching the provided schema.

thesis
  One precise sentence capturing what this post teaches or argues. Name the specific subject, technique, \
or framework being described. Never be vague.

summary
  3–5 sentences covering both the caption argument and the content of each slide. Be concrete: name tools, \
commands, frameworks, and specific techniques mentioned anywhere in the post or slides.

key_concepts
  Terms, tools, commands, or techniques from the caption or slides worth remembering. For each: name, \
colon, one sentence on how it appears in this post. Max 8 items.

insights
  2–3 specific things worth remembering: a non-obvious tip, a workflow described in the slides, \
an approach worth trying. Each should be a complete, actionable sentence.

interest_tags
  Flat list of topic labels. Lowercase, hyphenated. 3–8 tags.

key_moments
  Leave empty ([]). Instagram posts have no timestamps.\
"""


_TIKTOK_SYSTEM = """\
You are a research assistant helping someone build a personal reference library from short-form video.
You will receive metadata, the post caption, an optional Whisper-derived transcript, and file paths to \
several frames sampled from the video.

IMPORTANT: TikToks are visual-first and very short (often under 60 seconds). The transcript may be sparse, \
inaccurate, or mostly background music. Read EVERY provided frame with the Read tool — the on-screen text, \
UI, code, app shown, hand gestures, or product demonstrated is usually the actual content. Treat the caption \
and transcript as supplementary context, not the source of truth.

Return a JSON object matching the provided schema.

thesis
  One precise sentence naming what is shown or argued. For demos and tutorials, name the specific thing \
demonstrated (the app, technique, product, hack). Never be vague. Never use "explores".

summary
  3-5 sentences describing what actually happens in the video — what the creator does, shows, or says. \
Name tools, apps, products, and techniques concretely. Mention any on-screen text or UI shown in the frames. \
Never start with "The video" or "In this TikTok".

key_concepts
  Tools, apps, techniques, or products that appear in the video. For each: name, colon, one sentence on \
how it appears here. Max 8.

insights
  2-3 specific takeaways: a non-obvious tip shown, a surprising technique, an unexpected detail. Each a \
complete actionable sentence. Not trivia.

interest_tags
  Flat list of topic labels. Lowercase, hyphenated. 3-8 tags.

key_moments
  Leave empty ([]) unless the transcript provides clear timestamped beats worth jumping to. TikToks are \
short enough that key_moments are usually unnecessary.\
"""


_SCHEMA = Enrichment.model_json_schema()


def _note_block(user_note: str) -> str:
    """Steering section injected when the user attached a thought at ingest.

    The user's note is top-down attention: it biases what the summary, key
    concepts, and tags emphasize, without replacing the content analysis.
    """
    if not user_note.strip():
        return ""
    return (
        "\nThe user saved this with their own note. Treat it as the reason this "
        "content matters to them; steer the summary, key concepts, insights, and "
        "tags toward that angle:\n"
        f"{user_note.strip()}\n"
    )


def enrich(
    transcript: str,
    metadata: dict,
    visual_blocks: list[dict] | None = None,
    user_note: str = "",
) -> Enrichment:
    """Enrich a YouTube transcript via Claude Code (Agent SDK)."""
    chapters_text = ""
    if metadata.get("chapters"):
        lines = [f"  {_fmt_ts(ch['start_time'])} — {ch['title']}" for ch in metadata["chapters"]]
        chapters_text = "\nChapters:\n" + "\n".join(lines)

    text_block = f"""\
Title: {metadata.get("title", "")}
Uploader: {metadata.get("uploader", "")}
Duration: {metadata.get("duration", 0)}s
Tags: {", ".join(metadata.get("tags", [])[:10])}{chapters_text}

Transcript:
{transcript}
"""
    text_block += _note_block(user_note)

    with _staged_images(visual_blocks) as (frame_dir, frame_paths):
        if frame_paths:
            frames_listing = "\n".join(f"  {p}" for p in frame_paths)
            prompt = (
                f"{text_block}\n\n"
                f"Extracted frames (read selectively per the system prompt):\n{frames_listing}\n"
            )
        else:
            prompt = text_block

        add_dirs = [frame_dir] if frame_dir else []
        data = run_structured(_YT_SYSTEM, prompt, _SCHEMA, add_dirs=add_dirs)
        return Enrichment.model_validate(data)


def enrich_tiktok(
    post: dict,
    transcript: str,
    visual_blocks: list[dict] | None = None,
    user_note: str = "",
) -> Enrichment:
    """Enrich a TikTok with a visual-first, short-form-aware prompt.

    `post` is a dict with title, description, username, duration, music.
    """
    transcript_block = (
        f"Whisper transcript (may be inaccurate or sparse):\n{transcript}"
        if transcript.strip() else "Whisper transcript: (none — likely no speech or music-only)"
    )
    music_line = f"Music: {post['music']}\n" if post.get("music") else ""
    text_block = (
        f"Author: @{post.get('username', '')}\n"
        f"Title: {post.get('title', '')}\n"
        f"Duration: {post.get('duration', 0)}s\n"
        f"{music_line}"
        f"\nCaption / description:\n{post.get('description', '')}\n\n"
        f"{transcript_block}\n"
    )
    text_block += _note_block(user_note)

    with _staged_images(visual_blocks) as (frame_dir, frame_paths):
        frames_listing = "\n".join(f"  {p}" for p in frame_paths) if frame_paths else "  (none)"
        prompt = f"{text_block}\nExtracted frames (read EVERY one):\n{frames_listing}\n"
        add_dirs = [frame_dir] if frame_dir else []
        data = run_structured(_TIKTOK_SYSTEM, prompt, _SCHEMA, add_dirs=add_dirs)
        return Enrichment.model_validate(data)


def enrich_instagram(
    caption: str,
    username: str,
    slide_count: int,
    visual_blocks: list[dict],
    user_note: str = "",
) -> Enrichment:
    """Enrich an Instagram post with a carousel-aware prompt."""
    text_block = f"""\
Author: @{username}
Slide count: {slide_count}

Caption:
{caption}
"""
    text_block += _note_block(user_note)

    with _staged_images(visual_blocks) as (frame_dir, frame_paths):
        frames_listing = "\n".join(f"  {p}" for p in frame_paths) if frame_paths else "  (none)"
        prompt = (
            f"{text_block}\n\n"
            f"Carousel slides (read EVERY one):\n{frames_listing}\n"
        )
        add_dirs = [frame_dir] if frame_dir else []
        data = run_structured(_INSTAGRAM_SYSTEM, prompt, _SCHEMA, add_dirs=add_dirs)
        return Enrichment.model_validate(data)


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
