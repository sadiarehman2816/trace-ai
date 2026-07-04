"""verification/reference_extractor.py — Stage 1.

Locates the bibliography (last References/Bibliography heading, trims trailing
Appendix), segments entries (numbered-marker split OR year-gated split),
extracts in-text citations (author-year parenthetical, narrative Smith (2020),
numbered [1] / [2-5]) and document stats.

The year-gated segmentation is carried over from the proven core
citation_checker; the _JOURNAL_TAIL guard prevents a wrapped line like
"Health Economics Review, 8(1), 21-30." being mistaken for a new
organisational-author reference.
"""

from __future__ import annotations

import re
from typing import Optional

from .models import DocumentStats

_HEADING = re.compile(
    r"^\s*(?:\d+\.?\s*)?(references|bibliography|works\s+cited|reference\s+list)\s*:?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_APPENDIX = re.compile(r"^\s*(appendix(\s+[A-Z0-9])?|annex(\s+[A-Z0-9])?)\b.*$", re.IGNORECASE | re.MULTILINE)

# Unicode-aware name pieces (accents, hyphens, apostrophes: Rodríguez-Clare, O'Neil).
_U = r"A-Za-zÀ-ÖØ-öø-ÿ"
_NAME = rf"[A-ZÀ-Ö][{_U}'’\-]+"

_YEAR = re.compile(r"\((?:19|20)\d{2}[a-z]?\)|\b(?:19|20)\d{2}[a-z]?\b")
_NUMBERED_MARKER = re.compile(r"^\s*(?:\[(\d{1,3})\]|(\d{1,3})\.)\s+")
# APA:     "Surname, F." / "Surname, First"
# Chicago: "Surname, First. 1998." (year without parentheses, right after the name)
_AUTHOR_SURNAME = re.compile(rf"^\s*{_NAME},\s*(?:[A-Z]\.|[A-Z][{_U}]+)")
_CHICAGO_START = re.compile(rf"^\s*{_NAME},\s+[A-Z][{_U}.\- ]+?\.?\s+(?:18|19|20)\d{{2}}[a-z]?\.")
_ORG_START = re.compile(rf"^\s*[A-ZÀ-Ö][{_U}&,\.\-' ]{{3,60}}\.\s")

# Running-head / page-header noise: mostly UPPERCASE line, no lowercase title.
# Real references are mixed-case; running heads look like
# "1542 THE AMERICAN ECONOMIC REVIEW JUNE 2018".
def _is_running_head(entry: str) -> bool:
    letters = [c for c in entry if c.isalpha()]
    if not letters:
        return True
    upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    return upper_ratio > 0.6

# Journal-tail guard: a continuation line like "Health Economics Review, 8(1), 21-30."
# must not be treated as a new organisational-author reference start.
_JOURNAL_TAIL = re.compile(
    r"^\s*[A-Z][A-Za-z&\-' ]+(?:\s[A-Z&][A-Za-z&\-' ]+)*,\s*\d+\s*(?:\(\d+[\-–]?\d*\))?\s*,?\s*(?:pp?\.\s*)?\d+\s*[\-–]\s*\d+\.?\s*$"
)


# ---------------------------------------------------------------------------
# Bibliography location
# ---------------------------------------------------------------------------

def locate_bibliography(text: str) -> Optional[str]:
    """Return the bibliography block, or None. Uses the LAST heading match
    (a References heading may also appear in a table of contents) and trims a
    trailing Appendix section."""
    matches = list(_HEADING.finditer(text))
    if not matches:
        return None
    start = matches[-1].end()
    block = text[start:]
    appendix = _APPENDIX.search(block)
    if appendix and appendix.start() > 200:   # don't trim if "Appendix" appears immediately (false positive)
        block = block[: appendix.start()]
    return block.strip() or None


# ---------------------------------------------------------------------------
# Entry segmentation
# ---------------------------------------------------------------------------

def _is_reference_start(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if _JOURNAL_TAIL.match(stripped):
        return False
    # Chicago author-date: "Surname, First. 1998. ..." — a strong, unambiguous start.
    if _CHICAGO_START.match(stripped):
        return True
    if _AUTHOR_SURNAME.match(stripped) and _YEAR.search(stripped):
        return True
    if _ORG_START.match(stripped) and _YEAR.search(stripped):
        return True
    return False


def segment_references(block: str) -> list[str]:
    """Split a bibliography block into individual entries.

    Numbered style ([1] / 1.) wins if enough lines carry markers; otherwise
    fall back to year-gated author/org start detection with continuation-line
    merging (handles PDF extractions with no blank lines between entries).
    """
    lines = [ln for ln in block.splitlines()]
    marker_lines = sum(1 for ln in lines if _NUMBERED_MARKER.match(ln))
    nonempty = sum(1 for ln in lines if ln.strip())

    entries: list[str] = []

    if nonempty and marker_lines >= max(2, nonempty // 4):
        current: list[str] = []
        for ln in lines:
            if _NUMBERED_MARKER.match(ln):
                if current:
                    entries.append(" ".join(current).strip())
                current = [ln.strip()]
            elif ln.strip():
                current.append(ln.strip())
        if current:
            entries.append(" ".join(current).strip())
    else:
        current = []
        for ln in lines:
            stripped = ln.strip()
            if not stripped:
                if current:
                    entries.append(" ".join(current).strip())
                    current = []
                continue
            if _is_reference_start(stripped) and current:
                entries.append(" ".join(current).strip())
                current = [stripped]
            else:
                current.append(stripped)
        if current:
            entries.append(" ".join(current).strip())

    # Drop obvious non-entries: too short, no year, or running-head/page-header noise.
    return [
        e for e in entries
        if len(e) >= 25 and _YEAR.search(e) and not _is_running_head(e)
    ]


# ---------------------------------------------------------------------------
# In-text citations
# ---------------------------------------------------------------------------

# An author group before a year: "Smith", "Smith and Jones", "Autor, Levy,
# and Murnane", "Acemoglu et al." — connectors ordered longest-first so
# ", and " is preferred over a bare ", ".
_CONNECTOR = r"(?:,\s+and\s+|,\s+&\s+|\s+and\s+|\s+&\s+|,\s+)"
_AUTHOR_GROUP = rf"{_NAME}(?:{_CONNECTOR}{_NAME})*(?:\s+et\s+al\.?)?"

# Narrative: "Autor, Levy, and Murnane (2003)"
_NARRATIVE = re.compile(rf"({_AUTHOR_GROUP})\s*\(((?:19|20)\d{{2}}[a-z]?)\)")
# Parenthetical inner content carrying a year (Chicago "... 2012" or APA "..., 2012")
_PAREN_CITATION = re.compile(r"\(([^()]{0,200}?(?:19|20)\d{2}[a-z]?[^()]{0,40})\)")
_NUMERIC_CITATION = re.compile(r"\[(\d{1,3}(?:\s*[-–,]\s*\d{1,3})*)\]")

_ET_AL = re.compile(r"\bet\s+al\.?", re.IGNORECASE)


def first_surname(author_group: str) -> str:
    """Return the normalised FIRST-author surname from an in-text author group.

    'Autor, Levy, and Murnane' -> 'autor'
    'Acemoglu, Gancia, and Zilibotti' -> 'acemoglu'
    'Rodríguez-Clare' -> 'rodríguez-clare'  (hyphen kept — one surname)
    'Smith & Jones' -> 'smith'
    """
    g = _ET_AL.sub("", author_group).strip(" ,.&")
    # First chunk before the first connector.
    first = re.split(_CONNECTOR, g, maxsplit=1)[0].strip()
    # In-text groups use bare surnames; drop any stray given-initials.
    first = re.sub(r"\b[A-Z]\.", "", first).strip(" ,.")
    # Strip a possessive: "Roy's (1951)" -> "Roy".
    first = re.sub(r"[’']s\b", "", first)
    return first.lower()


def extract_intext_citations(body_text: str) -> list[dict]:
    """Return in-text citations: author-year (narrative + parenthetical) and
    numbered ([1], [2-5], [1,3]). The 'author' field always holds the FIRST
    author's surname group; 'lead' holds its normalised surname for matching."""
    cites: list[dict] = []
    seen: set[tuple] = set()

    def add_author_year(group: str, year: str, raw: str):
        lead = first_surname(group)
        if not lead:
            return
        base_year = re.sub(r"[a-z]$", "", year)
        key = ("ay", lead, base_year)
        if key in seen:
            return
        seen.add(key)
        cites.append({
            "style": "author_year", "author": group.strip(),
            "lead": lead, "year": year, "raw": raw,
        })

    for m in _NARRATIVE.finditer(body_text):
        add_author_year(m.group(1), m.group(2), m.group(0))

    for m in _PAREN_CITATION.finditer(body_text):
        inner = m.group(1)
        for part in re.split(r";", inner):        # (Smith 2020; Jones 2021)
            ym = re.search(r"(?:19|20)\d{2}[a-z]?", part)
            if not ym:
                continue
            author_part = part[: ym.start()].strip(" ,.&")
            gm = re.search(rf"({_AUTHOR_GROUP})\s*$", author_part)
            if not gm:
                continue
            add_author_year(gm.group(1), ym.group(0), part.strip())

    for m in _NUMERIC_CITATION.finditer(body_text):
        for num in _expand_numeric(m.group(1)):
            key = ("n", num)
            if key not in seen:
                seen.add(key)
                cites.append({"style": "numbered", "number": num, "raw": m.group(0)})

    return cites


def _expand_numeric(spec: str) -> list[int]:
    out: list[int] = []
    for chunk in re.split(r",", spec):
        chunk = chunk.strip()
        rng = re.match(r"(\d+)\s*[-–]\s*(\d+)$", chunk)
        if rng:
            a, b = int(rng.group(1)), int(rng.group(2))
            if b >= a and (b - a) <= 50:
                out.extend(range(a, b + 1))
        elif chunk.isdigit():
            out.append(int(chunk))
    return out


# ---------------------------------------------------------------------------
# Document stats
# ---------------------------------------------------------------------------

def document_stats(text: str, pages: int = 0) -> DocumentStats:
    words = len(re.findall(r"\b\w+\b", text))
    figures = len(set(re.findall(r"\b[Ff]igure\s+(\d+)", text)))
    tables = len(set(re.findall(r"\b[Tt]able\s+(\d+)", text)))
    return DocumentStats(pages=pages, words=words, figures=figures, tables=tables)


# ---------------------------------------------------------------------------
# Combined entry point
# ---------------------------------------------------------------------------

# Typographic characters common in PDFs, folded to ASCII so every downstream
# stage (segmentation, author parsing, matching) sees one consistent form.
# Fixes e.g. "O’Neil" (U+2019) parsing to surname "Neil".
_TYPOGRAPHIC = {
    "\u2019": "'", "\u2018": "'", "\u02bc": "'",
    "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "-", "\u2212": "-",
    "\u00a0": " ", "\u2009": " ", "\u200a": " ", "\ufeff": "",
}
_TYPO_RE = re.compile("|".join(map(re.escape, _TYPOGRAPHIC)))


def normalize_typography(text: str) -> str:
    return _TYPO_RE.sub(lambda m: _TYPOGRAPHIC[m.group(0)], text)


def extract(text: str, pages: int = 0) -> tuple[list[str], list[dict], DocumentStats]:
    """Return (raw reference entries, in-text citations, doc stats).

    References come from the deterministic zone detector's ``references`` zone
    (single source of truth), which structurally excludes running heads,
    metadata and body text from the bibliography. If the zone detector finds
    no references zone (unusual formatting), we fall back to the legacy
    heading-based locator so behaviour never degrades.
    """
    text = normalize_typography(text)

    from . import zone_detector as zd
    zoned = zd.detect_zones(text)
    ref_block = zd.zone_text(zoned, "references").strip()
    # In-text citations must never be read from the references zone, otherwise
    # bibliography entries masquerade as citations. Use body only.
    body = zd.zone_text(zoned, "body")

    if ref_block:
        refs = segment_references(ref_block)
    else:
        # Fallback: legacy locator (keeps older/odd layouts working).
        bib = locate_bibliography(text)
        refs = segment_references(bib) if bib else []
        if not body:
            body = text[: text.rfind(bib)] if bib and text.rfind(bib) > 0 else text

    if not body:                     # ensure in-text extraction always has something
        body = text

    cites = extract_intext_citations(body)
    stats = document_stats(text, pages)
    stats.reference_count = len(refs)
    stats.intext_citation_count = len(cites)
    return refs, cites, stats
