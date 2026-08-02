# pyright: basic
# Not strict-clean yet (#122). Delete these two lines once the module
"""Second-loop re-enrichment (#98): a reflection re-steers an ingested note.

The rewrite is surgical, never generative: enrichment sections are replaced
in place and every other byte of the note survives. A heading that fails to
match leaves its old text standing — the only acceptable failure mode on a
vault where notes accumulate manual edits after ingest.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .enrich import Enrichment, enrich_content

# Field -> headings seen in the corpus. YouTube notes say Commentary, web and
# reddit notes say Summary; matching a set keeps one rewriter valid for both.
_SECTION_HEADINGS: dict[str, tuple[str, ...]] = {
    "thesis": ("Thesis",),
    "summary": ("Commentary", "Summary"),
    "key_concepts": ("Key Concepts",),
    "insights": ("Insights",),
    "key_moments": ("Key Moments",),
}

# Path segment under sources/ -> SOURCE_BIAS key. Anything unlisted enriches
# with the web bias: it is the least platform-opinionated system prompt.
_SOURCE_BIAS_KEY = {
    "youtube": "youtube",
    "tiktok": "tiktok",
    "instagram": "instagram",
    "web": "web",
}

_REFLECTION_NOTE = (
    "This is a REFLECTION pass on content the user saved earlier. They were "
    "asked: {question}\nThey answered: {answer}\n"
    "The answer states why this content is in their knowledge base; treat it "
    "as the user note described above."
)


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter block including both --- fences, body)."""
    m = re.match(r"\A(---\n.*?\n---\n)", text, re.DOTALL)
    if not m:
        raise ValueError("note has no frontmatter")
    return m.group(1), text[m.end() :]


def _section_span(body: str, headings: tuple[str, ...]) -> tuple[int, int, str] | None:
    """Locate one enrichment section: (body_start, body_end, heading)."""
    for heading in headings:
        m = re.search(rf"^## {re.escape(heading)}\n", body, re.MULTILINE)
        if not m:
            continue
        start = m.end()
        nxt = re.compile(r"^(?:## |<details>)", re.MULTILINE).search(body, start)
        return start, nxt.start() if nxt else len(body), heading
    return None


def _rendered(field: str, enrichment: Enrichment) -> str:
    if field == "thesis":
        return enrichment.thesis + "\n\n"
    if field == "summary":
        return enrichment.summary + "\n\n"
    if field == "key_concepts":
        return "\n".join(f"- {c}" for c in enrichment.key_concepts) + "\n\n"
    if field == "insights":
        return "\n".join(f"- {i}" for i in enrichment.insights) + "\n\n"
    return (
        "\n".join(f"- **{m.timestamp}** — {m.description}" for m in enrichment.key_moments) + "\n\n"
    )


def rewrite_sections(body: str, enrichment: Enrichment) -> str:
    """Replace each enrichment section present in the note; touch nothing else.

    Sections are replaced back-to-front so earlier spans stay valid. A field
    the note never had is not added: old notes keep their shape.
    """
    spans: list[tuple[int, int, str]] = []
    for field, headings in _SECTION_HEADINGS.items():
        found = _section_span(body, headings)
        if found:
            spans.append((found[0], found[1], field))
    for start, end, field in sorted(spans, reverse=True):
        body = body[:start] + _rendered(field, enrichment) + body[end:]
    return body


def _merge_tags(frontmatter: str, new_tags: list[str]) -> str:
    """Union new interest tags into the yaml tag list. Additive: enrichment
    steered by a reflection may narrow its tag choices, and that must never
    erase tags an earlier pass earned."""
    m = re.search(r"^tags:\n((?:  - .+\n)+)", frontmatter, re.MULTILINE)
    if not m:
        return frontmatter
    existing = re.findall(r"  - (.+)", m.group(1))
    # Enrichment.interest_tags are already normalized + alias-resolved at birth
    merged = list(dict.fromkeys(existing + list(new_tags)))
    block = "tags:\n" + "\n".join(f"  - {t}" for t in merged) + "\n"
    return frontmatter[: m.start()] + block + frontmatter[m.end(1) :]


def _yaml_quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'


def stamp_reflection(frontmatter: str, question: str, answer: str, today: str) -> str:
    """Add reflection keys before the closing fence. Re-reflection replaces
    the previous stamp (latest reflection wins in frontmatter; the body keeps
    every ## Reflection section verbatim)."""
    fm = re.sub(r"^reflect(ed|ion_\w+):.*\n", "", frontmatter, flags=re.MULTILINE)
    stamp = (
        f"reflected: true\n"
        f"reflection_question: {_yaml_quote(question)}\n"
        f"reflection_answer: {_yaml_quote(answer)}\n"
        f"reflection_date: {today}\n"
    )
    return fm[:-4] + stamp + "---\n"


def append_reflection_section(body: str, question: str, answer: str, today: str) -> str:
    """Verbatim record, inserted before the raw-source tail (description /
    transcript details) when present so it stays in the readable half."""
    section = f"## Reflection\n**{today} — {question}**\n\n{answer}\n\n"
    tail = re.search(r"^(?:## Description\b|## Transcript\b|<details>)", body, re.MULTILINE)
    if tail:
        return body[: tail.start()] + section + body[tail.start() :]
    return body.rstrip() + "\n\n" + section


def _content_block(meta: dict[str, str], body: str) -> str:
    """Rebuild an enrichment content block from what the note itself holds.

    The transcript (when the note kept one) is the source text; otherwise the
    note's readable half stands in — weaker grounding, stated honestly in the
    prompt so the model does not invent specifics beyond it.
    """
    transcript = ""
    m = re.search(r"<details>.*?</summary>\n(.*?)</details>", body, re.DOTALL)
    if m:
        transcript = m.group(1).strip()
    if transcript:
        source_text = f"Transcript:\n{transcript}"
    else:
        readable = re.split(r"^<details>", body, flags=re.MULTILINE)[0]
        source_text = (
            "No raw transcript is stored; the existing note (below) is the only "
            f"source text. Do not invent specifics beyond it.\n{readable.strip()}"
        )
    return (
        f"Title: {meta.get('title', '')}\n"
        f"Uploader: {meta.get('uploader') or meta.get('author', '')}\n"
        f"{source_text}\n"
    )


def _read_meta(frontmatter: str) -> dict[str, str]:
    return {k: v.strip() for k, v in re.findall(r"^(\w+): (.+)$", frontmatter, re.MULTILINE)}


def _reembed(
    rel_path: str,
    note_path: Path,
    meta: dict[str, str],
    enrichment: Enrichment,
    reflection: str = "",
) -> None:
    from . import store

    if "sources/youtube/" in rel_path:
        try:
            from .transcript import _video_id

            if store.update_video_enrichment(
                _video_id(meta.get("url", "")), enrichment, reflection=reflection
            ):
                return
        except ValueError:
            pass
        # fall through when the url or index entry is missing
    doc_id = None
    try:
        from .vault import content_note_doc_id

        doc_id = content_note_doc_id(note_path)
    except Exception:
        pass
    if doc_id:
        body = store.strip_frontmatter(note_path.read_text(encoding="utf-8"))
        store.upsert_doc(
            doc_id,
            body,
            {
                "doc_id": doc_id,
                "tags": ", ".join(enrichment.interest_tags),
                "source_path": str(note_path),
                "reflected": True,
            },
        )


def append_why_i_save(question: str, answer: str, title: str, today: str) -> None:
    """The stated-intent corpus for profile synthesis. Best-effort: the note
    already holds the reflection."""
    from .vault import read_note, write_raw

    rel = "second-brain/me/why-i-save.md"
    entry = f"- **{today}** · {title} — *{question}* — {answer}\n"
    try:
        existing = read_note(rel).rstrip() + "\n"
    except (FileNotFoundError, OSError):
        existing = "# Why I save\n\n"
    try:
        write_raw(rel, existing + entry)
    except OSError:
        pass


def reflect_note(rel_path: str, question: str, answer: str) -> Path:
    """Run the second loop on one ingested note.

    rel_path is vault-root-relative (`second-brain/sources/...`), the shape
    every hub card already carries. Returns the rewritten note's path.
    """
    from .vault import read_note, write_raw

    if not answer.strip():
        raise ValueError("reflection answer is empty")
    text = read_note(rel_path)
    frontmatter, body = _split_frontmatter(text)
    meta = _read_meta(frontmatter)
    today = f"{datetime.now():%Y-%m-%d}"

    source_key = "web"
    parts = Path(rel_path).parts
    if "sources" in parts:
        source_key = _SOURCE_BIAS_KEY.get(parts[parts.index("sources") + 1], "web")

    enrichment = enrich_content(
        _content_block(meta, body),
        source_key,
        user_note=_REFLECTION_NOTE.format(question=question.strip(), answer=answer.strip()),
    )

    new_body = rewrite_sections(body, enrichment)
    new_body = append_reflection_section(new_body, question.strip(), answer.strip(), today)
    new_fm = _merge_tags(frontmatter, enrichment.interest_tags)
    new_fm = stamp_reflection(new_fm, question.strip(), answer.strip(), today)

    note_path = write_raw(rel_path, new_fm + new_body)

    _reembed(rel_path, note_path, meta, enrichment, reflection=answer.strip())
    append_why_i_save(question.strip(), answer.strip(), meta.get("title", rel_path), today)
    return note_path
