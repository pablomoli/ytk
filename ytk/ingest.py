"""Web content ingestion — fetch and extract readable text from any URL."""

from __future__ import annotations

from dataclasses import dataclass

import anthropic
import trafilatura

from .enrich import Enrichment

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


_SYSTEM_WEB = """\
You are a research assistant helping build a personal knowledge library from web articles.
Return a JSON object with these fields:

thesis: One precise sentence capturing the article's main argument or finding. Never vague.

summary: 3-5 sentences for someone who wants a sharp reminder. Name specific tools,
  techniques, data, or findings concretely — not just topics.

key_concepts: Terms, tools, or techniques worth knowing. Format each as "name: how it was
  used or argued in this article". Max 8 items.

insights: 2-3 specific, actionable things worth remembering — non-obvious tradeoffs,
  surprising findings, or techniques that differ from conventional wisdom.

interest_tags: 3-8 lowercase hyphenated topic labels (e.g. "machine-learning", "go", "geospatial").

key_moments: Return an empty list [].
"""


@dataclass
class WebContent:
    url: str
    title: str
    author: str
    date: str
    text: str


def fetch_web(url: str) -> WebContent:
    """Fetch and extract readable text from a URL using trafilatura."""
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        raise ValueError(f"Could not fetch URL: {url}")

    metadata = trafilatura.extract_metadata(downloaded)
    text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)

    if not text:
        raise ValueError(f"Could not extract readable text from: {url}")

    return WebContent(
        url=url,
        title=metadata.title if metadata and metadata.title else url,
        author=metadata.author if metadata and metadata.author else "",
        date=metadata.date if metadata and metadata.date else "",
        text=text,
    )


def enrich_web(content: WebContent) -> Enrichment:
    """Summarize web article content using Claude Haiku. key_moments is always []."""
    client = _get_client()
    user_content = (
        f"Title: {content.title}\nAuthor: {content.author}\n"
        f"Date: {content.date}\nURL: {content.url}\n\n"
        f"Article:\n{content.text[:20_000]}"
    )

    response = client.messages.parse(
        model="claude-haiku-4-5",
        max_tokens=2048,
        system=[{"type": "text", "text": _SYSTEM_WEB, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_content}],
        output_format=Enrichment,
    )
    result = response.parsed_output
    result.key_moments = []
    return result
