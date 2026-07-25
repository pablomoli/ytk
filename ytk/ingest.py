# pyright: basic
# Not strict-clean yet (#122). Delete these two lines once the module
# passes strict — the list of files carrying them only shrinks.
"""Web content ingestion — fetch and extract readable text from any URL."""

from __future__ import annotations

from dataclasses import dataclass

import trafilatura

from .enrich import Enrichment, enrich_content


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


def enrich_web(content: WebContent, user_note: str = "") -> Enrichment:
    """Summarize web article content via Claude Code. key_moments is always []."""
    content_block = (
        f"Title: {content.title}\nAuthor: {content.author}\n"
        f"Date: {content.date}\nURL: {content.url}\n\n"
        f"Article:\n{content.text[:20_000]}"
    )
    return enrich_content(content_block, "web", user_note=user_note)
