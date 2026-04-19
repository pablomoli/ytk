"""AI enrichment of YouTube video content via Claude Haiku."""

from __future__ import annotations

import anthropic
from pydantic import BaseModel


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


_SYSTEM = """\
You are a detailed research assistant helping someone who already watches a lot of YouTube videos \
build a personal reference library. The person watches the videos themselves — your job is to make \
them retrievable and searchable later. Think: "six months from now, they remember something \
specific happened in this video and want to find it fast."

You will receive a transcript and metadata for a video. Return a JSON object with these fields:

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
not "concurrency explanation").\
"""

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def enrich(
    transcript: str,
    metadata: dict,
    visual_blocks: list[dict] | None = None,
) -> Enrichment:
    """
    Send transcript + metadata to Claude Haiku and return structured enrichment.
    Uses prompt caching on the system prompt (stable across all calls).
    When visual_blocks are provided, user content becomes a list interleaving
    text and image blocks for a single-pass multimodal enrichment call.
    """
    client = _get_client()

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

    if visual_blocks:
        user_content: str | list = [{"type": "text", "text": text_block}] + visual_blocks
        system_text = (
            _SYSTEM
            + "\nYou may also receive images or video frames — incorporate what you observe "
            "in them into your analysis."
        )
    else:
        user_content = text_block
        system_text = _SYSTEM

    response = client.messages.parse(
        model="claude-haiku-4-5",
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": system_text,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_content}],
        output_format=Enrichment,
    )

    return response.parsed_output


def _fmt_ts(seconds: int | float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
