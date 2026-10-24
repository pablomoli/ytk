"""House rules for the writer: the owner's recurring corrections, and a lint.

HOUSE_RULES is appended to the enricher's role text (never the grader's; the
grader keeps judging against the rubric). Each rule pairs a sentence the
owner or the grader rejected on a real draft with what was asked for
instead. `lint` checks the mechanical subset of the rules on a draft with
no model call; `scripts/replay_writer_lint.py` measures it on stored drafts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .enricher import EnrichmentV2

HOUSE_RULES = """\

House rules
  The owner's own corrections to past drafts, frequent enough to be rules. Each \
pairs a sentence that was rejected with what was asked for instead.

1. Open on the claim. The first words of the thesis, of the summary and of each \
insight are the claim, never the medium or the author: not "The reel", "The video", \
"The clip shows", "The piece is", "The page is", "The episode traces", "A creator \
recaps", "The reel argues that".
   Rejected: "The reel is a build log for reaction_cam.py".
   Asked for: lead with what was built or argued, then who and where.

2. The argument, not the running order. The summary says what is argued or shown \
and what holds it up. It does not walk the source in sequence ("opens with", "then \
pivots", "first... second... third", "the back half is", "he closes by").
   Rejected: "The reel opens with a Google logo over a 3D fly brain... then pivots... \
He closes by...".
   Asked for: "A complete synapse-level wiring diagram now exists for one animal, \
built by slicing, imaging, machine tracing and human proofreading; the same approach \
does not scale to a human brain, and a lower-resolution clinical version already \
runs on living patients."

3. Cite the unit that shows it. Open a frame before citing it, and cite the frame \
where the thing is visible; a talking-head frame cannot carry a claim about code, a \
chart or a sign. Each claim gets its own unit: two things on two frames are two cites.
   Rejected: "survey sheet with checkboxes and a sperm doodle [frame:010]" (frame:010 \
is a talking-head shot). Asked for: "[frame:015]", the frame that shows the sheet.
   A key moment's timestamp is the line where the thing happens, never the chapter \
marker or a neighbouring line. Rejected: "0:20 booth wide shot". Asked for: "0:16", \
where the booth is on screen.

4. Say only what the frame shows; mark the rest as inference. Copy on-screen text \
exactly and describe what is visible, nothing more. Anything past that (the venue, \
the room, how it was made, the stack, the intent) is marked in the sentence: \
"inferred from the frames", "a guess".
   Rejected: "played live at an outdoor night market gig"; "'view' folder" for an \
explorer row that reads "venv"; "an anime-style shock sprite" for a cartoon fox in \
shirt and tie. Asked for: "a crowd under string lights and a lighting truss \
[frame:001]; the venue is not named".
   Tile captions on the contact sheet (an id and "t=0s") are added by the capture \
tooling and are not on-screen text.

5. A visual piece gets its look described. For a reel, a render or a title sequence, \
describe composition, motion, palette, texture and pacing, cite the units, and mark \
it as inference from frames.
   Asked for: "near-black maroon field, amber-to-white hairline threads edge to edge, \
one luminous knot centered (inferred from the sheet)". A piece that is a static \
talking head says so in evidence_gaps.

6. Outside knowledge is not the writer's to add. Every name, affiliation, date and \
number comes from the packet.
   Rejected: "SciShow's Joe Hansen", "the Mars-sized body", "survived until ~4,000 \
years ago", "FDA-cleared" where the record says only "cleared".
   When the owner supplies something from outside the record (in a take or a \
finding), keep it, label it in the sentence as the owner's ("identified by the \
owner; the video says only 'this paper'"), list it in evidence_gaps, and keep it out \
of the thesis.

7. Who said it. In an interview, attribute each position to the person who says it \
in the transcript; the host's point is not the guest's. When speaker turns are \
unclear, say so in evidence_gaps.

8. Name a gap exactly. evidence_gaps says what was not seen and where: "the \
transcript stops at 1:14:19; the last hour, including the prevention chapter, was \
never seen"; "no frames; the on-screen demos are described from speech only"; "no \
voiceover; the argument is in the caption". Chapter titles are not content: never \
write claims or key moments for a stretch the transcript does not reach. When the \
speech-to-text is garbled, trust the on-screen text: "the caption reads 86 billion; \
the transcript heard 'million'".

9. Concepts in the packet's words. Name a concept with the words the source uses, \
then gloss it. Rejected: "Binary encoding". Asked for: "Light switches / strings of \
one or zero". A tool or project name alone ("Claude", "SuperEar") is not a concept.

10. Insights are what to do, not the concepts again. Cover the key concepts and \
read each insight: if it only names a concept again, replace it.
    Rejected: concept "Service workers: enable caching and offline support", insight \
"Service workers work on any regular website, not just installed PWAs".

11. Answer the whole take. Every question in the owner's take gets an answer. When \
the take rests on a wrong premise, say so plainly ("your take guessed the egg's \
block to polyspermy; the reel is about semen displacement"). Never borrow the take's \
wording as a description of the source. No praise of the source or of the owner.

12. Tags: three to eight, from the vocabulary; never two near-synonyms side by side \
("education" with "learning", "ai" with "ai-agents"); never a tag the packet does \
not support.

13. Voice. No emojis. No analogies to programming languages; an everyday image, one \
per explanation, is fine. Never mention a grader, a rubric or an earlier round in \
the note. Prose fields hold prose, never JSON or markup.\
"""


@dataclass(frozen=True)
class LintHit:
    rule: str
    detail: str
    where: str

    def finding(self) -> dict[str, str]:
        """Shaped like a grader bounce so the writer reads both the same way."""
        return {"check": f"house rule: {self.rule}", "detail": self.detail, "where": self.where}


_MEDIUM = (
    "video|reel|clip|piece|page|episode|essay|article|post|talk|podcast|interview|"
    "carousel|thread|tiktok|lecture|creator|author|speaker"
)
# "The X is/opens/argues..." or "A creator recaps": the medium as grammatical subject.
_MEDIUM_OPENING = re.compile(
    rf"^\s*(?:in this\b|(?:the|this|a|an)\s+(?:\w+[- ])?(?:{_MEDIUM})s?\b(?![-'’]))",
    re.IGNORECASE,
)
_BANNED = ("explores", "delves", "dives into", "journey", "landscape")
_SEQUENCE = re.compile(
    r"\b(?:opens (?:with|by|on)|starts (?:with|by|from)|then (?:pivots|moves|turns|shows)|"
    r"moves on|closes (?:with|by|on)|ends (?:with|by|on)|the (?:back|second|first) half|"
    r"walks through|first,|second,|third,|finally,)",
    re.IGNORECASE,
)
_LEAK = re.compile(
    r"\bgrader (?:flagged|asked|requested|noted)|\brubric\b|"
    r"\b(?:previous|last|earlier) (?:round|draft|attempt)\b|"
    r"</?(?:parameter|invoke|thesis|summary|insights|key_concepts)\b",
    re.IGNORECASE,
)
_SENTENCE_END = re.compile(r"(?<!\be\.g)(?<!\bi\.e)(?<!\bvs)(?<!\bet al)[.!?](?=\s+[A-Z\"'(])")
_FRAME_CITE = re.compile(r"\[(?:frame:\d{3}|sheet)\]")
_TIME_CITE = re.compile(r"\[t:\d+\]")
# Claims past what a frame can show: setting, provenance, technique, intent.
_BEYOND_VISIBLE = re.compile(
    r"\b(?:venue|bedroom|kitchen|studio|market|street|park|stage|gig|shot in|filmed|"
    r"made (?:with|in)|rendered (?:with|in)|built (?:with|in)|technique|"
    r"to make|meant to|intended|deliberate)\b",
    re.IGNORECASE,
)
_MARKED = re.compile(
    r"\binfer|\bguess|\bappears?\b|\blooks like|\bseems?\b|\blikely\b|\bprobably\b|"
    r"\bsuggest|\bnot (?:named|stated|shown)",
    re.IGNORECASE,
)
_NEAR_SYNONYMS = (frozenset({"education", "learning"}),)
SUMMARY_MAX_SENTENCES = 5
# Rules the curator feeds back before the grader reads the draft. The others
# missed or misfired on the stored-draft replay (docs/design/linking/README.md).
WIRED = frozenset({"open on the claim", "prose only, no process"})


def _sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_END.split(text) if s.strip()]


def _opening(draft: EnrichmentV2) -> list[LintHit]:
    fields = [("thesis", draft.thesis), ("summary", draft.summary)]
    fields += [(f"insights[{i}]", s) for i, s in enumerate(draft.insights)]
    out: list[LintHit] = []
    for where, text in fields:
        m = _MEDIUM_OPENING.match(text)
        if m:
            out.append(
                LintHit(
                    "open on the claim",
                    f'opens on the medium ("{m.group(0).strip()}") instead of the claim',
                    where,
                )
            )
    return out


def _banned(draft: EnrichmentV2) -> list[LintHit]:
    fields = [("thesis", draft.thesis), ("summary", draft.summary)]
    fields += [("take_response", draft.take_response or "")]
    fields += [(f"insights[{i}]", s) for i, s in enumerate(draft.insights)]
    fields += [(f"key_concepts[{i}]", s) for i, s in enumerate(draft.key_concepts)]
    out: list[LintHit] = []
    for where, text in fields:
        hits = [w for w in _BANNED if re.search(rf"\b{w}\b", text, re.IGNORECASE)]
        if hits:
            out.append(LintHit("banned words", ", ".join(hits), where))
    return out


def _running_order(draft: EnrichmentV2) -> list[LintHit]:
    markers = {m.group(0).lower() for m in _SEQUENCE.finditer(draft.summary)}
    if len(markers) >= 2:
        shown = ", ".join(sorted(markers))
        return [
            LintHit("the argument, not the running order", f"sequence words: {shown}", "summary")
        ]
    return []


def _summary_length(draft: EnrichmentV2) -> list[LintHit]:
    n = len(_sentences(draft.summary))
    if n > SUMMARY_MAX_SENTENCES:
        return [LintHit("summary length", f"{n} sentences; three to five", "summary")]
    return []


def _frame_inference(draft: EnrichmentV2) -> list[LintHit]:
    fields = [("summary", s) for s in _sentences(draft.summary)]
    fields += [(f"key_concepts[{i}]", s) for i, s in enumerate(draft.key_concepts)]
    out: list[LintHit] = []
    for where, text in fields:
        if not _FRAME_CITE.search(text) or _TIME_CITE.search(text):
            continue
        beyond = _BEYOND_VISIBLE.search(text)
        if beyond and not _MARKED.search(text):
            out.append(
                LintHit(
                    "mark inference from frames",
                    f'cites only frames and claims "{beyond.group(0)}" with no inference marker',
                    where,
                )
            )
    return out


def _tags(draft: EnrichmentV2) -> list[LintHit]:
    # {kind}-rec tags are derived in code from recommendations, not chosen.
    tags = {t for t in draft.interest_tags if not t.endswith("-rec")}
    pairs: list[str] = []
    for t in sorted(tags):
        wider = [o for o in tags if o != t and t in o.split("-")]
        pairs += [f"{t} with {o}" for o in sorted(wider)]
    pairs += [" with ".join(sorted(s)) for s in _NEAR_SYNONYMS if s <= tags]
    if pairs:
        return [LintHit("near-synonym tags", "; ".join(pairs), "interest_tags")]
    return []


def _leaks(draft: EnrichmentV2) -> list[LintHit]:
    fields = [("thesis", draft.thesis), ("summary", draft.summary)]
    fields += [("take_response", draft.take_response or "")]
    fields += [(f"insights[{i}]", s) for i, s in enumerate(draft.insights)]
    fields += [(f"new_tags[{i}]", t.reason) for i, t in enumerate(draft.new_tags)]
    out: list[LintHit] = []
    for where, text in fields:
        m = _LEAK.search(text)
        if m or text.lstrip().startswith("{"):
            found = m.group(0) if m else "{"
            out.append(LintHit("prose only, no process", f'contains "{found}"', where))
    return out


def lint(draft: EnrichmentV2) -> list[LintHit]:
    """Every mechanical house rule, no model call. An empty list is clean."""
    return [
        *_opening(draft),
        *_banned(draft),
        *_running_order(draft),
        *_summary_length(draft),
        *_frame_inference(draft),
        *_tags(draft),
        *_leaks(draft),
    ]
