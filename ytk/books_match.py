# pyright: basic
# Not strict-clean yet (#122). Delete these two lines once the module
# passes strict — the list of files carrying them only shrinks.
"""Fuzzy text-position matcher for the audiobook progress tracker.

Standard library only (re, unicodedata, difflib, zipfile, html) so the same
module runs on the Mac CLI and inside a-Shell on iOS, where no third-party
packages are available.

Pipeline:
    raw text          flatten_epub(path)            -> one spine-ordered string
    canonical text    build_normalized(raw)         -> (norm_text, n2r)
    locate a sentence Matcher(norm_text).match(q)   -> (norm_offset, score)

``score`` is a difflib ratio in [0, 1]. Empirically a threshold of 0.60 keeps
~93% of real hits while rejecting effectively all non-matches, yielding ~98%
precision on accepted answers. Callers should refuse to act below ACCEPT_SCORE
and ask for a longer sentence when the query is short (see MIN_QUERY_WORDS).
"""

import difflib
import re
import unicodedata
import zipfile
from html.parser import HTMLParser

ACCEPT_SCORE = 0.60
MIN_QUERY_WORDS = 8


# ---------- flatten epub ----------


class TextExtractor(HTMLParser):
    SKIP = {"script", "style", "head", "title"}
    BLOCK = {"p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"}

    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip_depth += 1
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip_depth > 0:
            self.skip_depth -= 1
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.skip_depth == 0:
            self.parts.append(data)

    def text(self):
        return "".join(self.parts)


def flatten_epub(path):
    """Return the book's text as one string, spine documents concatenated in
    reading order. Spine/manifest are parsed with regex rather than ElementTree
    because EPUB namespace prefixes make the latter brittle."""
    z = zipfile.ZipFile(path)
    names = z.namelist()
    container = z.read("META-INF/container.xml").decode("utf-8", "replace")
    rootfile = re.search(r'full-path="([^"]+)"', container)
    if rootfile is None:
        raise ValueError(f"{path}: container.xml declares no rootfile full-path")
    opf_path = rootfile.group(1)
    opf_dir = opf_path.rsplit("/", 1)[0] if "/" in opf_path else ""
    opf = z.read(opf_path).decode("utf-8", "replace")

    manifest = {}
    for tag in re.findall(r"<item\b[^>]*>", opf):
        idm = re.search(r'\bid="([^"]+)"', tag)
        hm = re.search(r'\bhref="([^"]+)"', tag)
        if idm and hm:
            manifest[idm.group(1)] = hm.group(1)
    spine_ids = re.findall(r'<itemref\b[^>]*\bidref="([^"]+)"', opf)

    chunks = []
    for sid in spine_ids:
        href = manifest.get(sid)
        if not href:
            continue
        full = (opf_dir + "/" + href) if opf_dir else href
        full = full.replace("\\", "/")
        if full not in names:
            cand = [n for n in names if n.endswith(href)]
            if not cand:
                continue
            full = cand[0]
        if not full.endswith((".html", ".xhtml", ".htm")):
            continue
        html = z.read(full).decode("utf-8", "replace")
        ex = TextExtractor()
        ex.feed(html)
        chunks.append(ex.text())
    return "\n".join(chunks)


# ---------- normalize ----------


def normalize(text):
    """Fold a string to a comparison form: accents stripped, lowercased,
    quotes/dashes unified, punctuation dropped, whitespace collapsed."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"['’‘ʼ]", "'", text)
    text = re.sub(r"[“”]", '"', text)
    text = re.sub(r"[—–]", "-", text)
    text = re.sub(r"[^\w\s'-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def build_normalized(raw):
    """Normalize ``raw`` while tracking provenance.

    Returns ``(norm_text, n2r)`` where ``n2r[i]`` is the offset in ``raw`` of
    normalized character ``i`` -- so a match found in normalized space can be
    mapped back to a real position in the original text."""
    out, n2r = [], []
    prev_space = True
    for i, ch in enumerate(raw):
        d = unicodedata.normalize("NFKD", ch)
        d = "".join(c for c in d if not unicodedata.combining(c)).lower()
        d = re.sub(r"['’‘ʼ]", "'", d)
        d = re.sub(r"[“”]", '"', d)
        d = re.sub(r"[—–]", "-", d)
        d = re.sub(r"[^\w\s'-]", " ", d)
        for c in d:
            if c.isspace():
                if prev_space:
                    continue
                out.append(" ")
                n2r.append(i)
                prev_space = True
            else:
                out.append(c)
                n2r.append(i)
                prev_space = False
    while out and out[-1] == " ":
        out.pop()
        n2r.pop()
    return "".join(out), n2r


# ---------- two-stage matcher ----------

STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "if",
    "then",
    "else",
    "when",
    "of",
    "to",
    "in",
    "on",
    "at",
    "by",
    "for",
    "with",
    "without",
    "from",
    "into",
    "onto",
    "upon",
    "as",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "am",
    "do",
    "does",
    "did",
    "have",
    "has",
    "had",
    "not",
    "no",
    "nor",
    "so",
    "than",
    "that",
    "this",
    "these",
    "those",
    "it",
    "its",
    "it's",
    "he",
    "she",
    "they",
    "them",
    "his",
    "her",
    "their",
    "our",
    "your",
    "my",
    "me",
    "you",
    "i",
    "we",
    "us",
    "who",
    "whom",
    "which",
    "what",
    "whose",
    "how",
    "why",
    "where",
    "here",
    "there",
    "all",
    "any",
    "some",
    "such",
    "very",
    "too",
    "more",
    "most",
    "much",
    "many",
    "few",
    "little",
    "own",
    "same",
    "other",
    "will",
    "would",
    "shall",
    "should",
    "can",
    "could",
    "may",
    "might",
    "must",
    "i'm",
    "you're",
    "we're",
}


def tokenize(s):
    return re.findall(r"[a-z0-9']+", s)


def build_freq(norm_book):
    freq = {}
    for t in tokenize(norm_book):
        freq[t] = freq.get(t, 0) + 1
    return freq


class Matcher:
    """Two-stage locator over a normalized book string.

    Stage 1 picks the rarest content words of the query as anchors and gathers
    their positions. Stage 2 scores a query-length slice around each candidate
    with difflib and returns the best (offset, ratio)."""

    def __init__(self, norm_book, k_anchors=3, window=300, max_positions_per_anchor=60):
        self.book = norm_book
        self.freq = build_freq(norm_book)
        self.k = k_anchors
        self.window = window
        self.max_pos = max_positions_per_anchor

    def _anchor_positions(self, anchors):
        positions = []
        for a in anchors:
            for m in re.finditer(r"\b" + re.escape(a) + r"\b", self.book):
                positions.append(m.start())
                if len(positions) > self.max_pos * len(anchors):
                    break
        return sorted(set(positions))

    def match(self, query, last_offset=None):
        nq = normalize(query)
        qtokens = tokenize(nq)
        content = [t for t in qtokens if t not in STOPWORDS and len(t) > 1] or qtokens[:]
        content.sort(key=lambda t: self.freq.get(t, 0) or 1)
        anchors = content[: self.k]
        if not anchors:
            return (-1, 0.0)

        positions = self._anchor_positions(anchors) or self._anchor_positions(content[:6])
        if not positions:
            return (-1, 0.0)

        offset_into = self.window // 4
        seen, candidates = set(), []
        for p in positions:
            start = max(0, p - offset_into)
            if start in seen:
                continue
            seen.add(start)
            candidates.append(start)
        if last_offset is not None:
            candidates.sort(key=lambda s: (s < last_offset, abs(s - last_offset)))

        scan = max(self.window, len(nq) + 80)
        slice_len = len(nq) + 20
        best_off, best_score = -1, 0.0
        sm = difflib.SequenceMatcher(None)
        sm.set_seq1(nq)
        for start in candidates:
            region = self.book[start : start + scan]
            sm.set_seq2(region)
            blocks = sm.get_matching_blocks()
            local = blocks[0].b if (blocks and blocks[0].size > 0) else 0
            slice_start = start + max(0, local)
            seg = self.book[slice_start : slice_start + slice_len]
            r = difflib.SequenceMatcher(None, nq, seg).ratio()
            if r > best_score:
                best_score, best_off = r, slice_start
        return best_off, best_score
