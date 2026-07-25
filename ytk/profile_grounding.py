"""Standalone grounding checks for rendered interest profiles (#94)."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

from .synthesis import evidence_is_fresh


def _xml_body(text: str) -> str:
    start = text.find("<interest-profile")
    end = text.find("</interest-profile>")
    if start >= 0 and end >= start:
        return text[start : end + len("</interest-profile>")]
    return text.strip()


def check_profile_grounding_text(text: str) -> list[str]:
    """Return every grounding failure in a rendered profile document."""
    try:
        root = ElementTree.fromstring(_xml_body(text))
    except ElementTree.ParseError as exc:
        return [f"invalid profile XML: {exc}"]
    if root.tag != "interest-profile":
        return [f"expected <interest-profile>, found <{root.tag}>"]

    generated_at = root.attrib.get("generated", "")
    try:
        half_life_days = float(root.attrib["evidence-half-life-days"])
    except (KeyError, ValueError):
        return ["interest-profile lacks a valid evidence-half-life-days attribute"]

    catalog = {
        node.attrib.get("id", ""): node.attrib.get("captured-at", "")
        for node in root.findall("./evidence-catalog/evidence")
        if node.attrib.get("id")
    }
    errors: list[str] = []
    portrait_claims = root.findall("./portrait/claim")
    theme_summaries = root.findall("./themes/theme/summary")
    if not portrait_claims:
        errors.append("portrait has no claims")
    if not theme_summaries:
        errors.append("profile has no theme summaries")

    def check_refs(label: str, node: ElementTree.Element) -> list[str] | None:
        """Shared ref checks; returns the evidence ids or None on failure."""
        if not (node.text or "").strip():
            errors.append(f"{label} is empty")
        evidence_ids = node.attrib.get("evidence", "").split()
        if not evidence_ids:
            errors.append(f"{label} has no evidence refs")
            return None
        missing = [e for e in evidence_ids if e not in catalog]
        if missing:
            errors.append(f"{label} cites missing catalog ids: {missing}")
            return None
        return evidence_ids

    # Theme summaries are full-history category descriptions: they must be
    # grounded, but stale or unknown capture times do not invalidate them.
    for index, node in enumerate(theme_summaries, start=1):
        check_refs(f"theme summary {index}", node)

    # Portrait claims carry #94's bias check: at least one cited item captured
    # within the half-life, so no claim survives on stale-only evidence.
    for index, node in enumerate(portrait_claims, start=1):
        label = f"portrait claim {index}"
        evidence_ids = check_refs(label, node)
        if evidence_ids is None:
            continue
        if not any(
            evidence_is_fresh(catalog[e], generated_at, half_life_days) for e in evidence_ids
        ):
            errors.append(f"{label} has no evidence captured within the decay half-life")
    return errors


def check_profile_grounding(path: Path) -> list[str]:
    return check_profile_grounding_text(path.read_text(encoding="utf-8"))
