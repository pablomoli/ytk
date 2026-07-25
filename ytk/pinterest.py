# pyright: basic
# Not strict-clean yet (#122). Delete these two lines once the module
# passes strict — the list of files carrying them only shrinks.
"""Pinterest pin fetcher via OpenGraph meta tags (no auth, no API app)."""

from __future__ import annotations

import html
import re
import urllib.request
from dataclasses import dataclass


@dataclass
class PinterestPin:
    url: str
    pin_id: str
    title: str
    description: str
    image_url: str


_OG_RE = re.compile(
    r'<meta\s+(?:property="og:(?P<prop1>[a-z:]+)"\s+content="(?P<c1>[^"]*)"'
    r'|content="(?P<c2>[^"]*)"\s+property="og:(?P<prop2>[a-z:]+)")',
    re.IGNORECASE,
)


def _parse_og(page: str) -> dict:
    """Extract og:title / og:description / og:image regardless of attribute order."""
    og: dict = {}
    for m in _OG_RE.finditer(page):
        prop = m.group("prop1") or m.group("prop2")
        content = m.group("c1") if m.group("c1") is not None else m.group("c2")
        og.setdefault(prop, html.unescape(content or ""))
    return {
        "title": og.get("title", ""),
        "description": og.get("description", ""),
        "image": og.get("image", ""),
    }


def _get_html(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


_PINIMG_RE = re.compile(
    r"https://i\.pinimg\.com/(?:originals|\d+x(?:/\d+)?)/[A-Za-z0-9/_-]+\.(?:jpg|jpeg|png|webp|gif)"
)


def _embedded_image(page: str) -> str:
    """Best pin image from the page's embedded JSON when og:image is absent.

    The closeup image URL repeats across the payload; CSS asset URLs appear
    once. Prefer the most frequent match, then closeup sizes over originals.
    """
    counts: dict[str, int] = {}
    for m in _PINIMG_RE.finditer(page):
        counts[m.group(0)] = counts.get(m.group(0), 0) + 1
    if not counts:
        return ""
    return max(counts, key=lambda u: (counts[u], "/736x/" in u))


def _page_title(page: str) -> str:
    m = re.search(r"<title>([^<]*)</title>", page)
    if not m:
        return ""
    return html.unescape(m.group(1)).split("|")[0].strip()


def fetch_pinterest(url: str) -> PinterestPin:
    """Fetch a pin's metadata via og tags, falling back to the embedded JSON.

    Raises ValueError when no image can be found (login-walled or removed).
    """
    m = re.search(r"/pin/(\d+)", url)
    pin_id = m.group(1) if m else re.sub(r"[^0-9A-Za-z]", "", url)[-20:]

    page = _get_html(url)
    og = _parse_og(page)
    image = og["image"] or _embedded_image(page)
    if not image:
        raise ValueError(f"No image found for pin {url!r} (login-walled or removed).")
    return PinterestPin(
        url=url,
        pin_id=pin_id,
        title=og["title"] or _page_title(page),
        description=og["description"],
        image_url=image,
    )
