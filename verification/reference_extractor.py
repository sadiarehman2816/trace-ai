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

_YEAR = re.compile(r"\((?:19|20)\d{2}[a-z]?\)|\b(?:19|20)\d{2}[a-z]?\b")
_NUMBERED_MARKER = re.compile(r"^\s*(?:\[(\d{1,3})\]|(\d{1,3})\.)\s+")
_AUTHOR_SURNAME = re.compile(r"^\s*[A-Z][a-zA-Z\-']+,\s*(?:[A-Z]\.|[A-Z][a-z]+)")
_ORG_START = re.compile(r"^\s*[A-Z][A-Za-z&,\.\-' ]{3,60}\.\s")

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

    # Drop obvious non-entries (page headers, stray numbers)
    return [e for e in entries if len(e) >= 25 and _YEAR.search(e)]


# ---------------------------------------------------------------------------
# In-text citations
# ---------------------------------------------------------------------------

_PAREN_CITATION = re.compile(
    r"\(([^()]{0,120}?(?:19|20)\d{2}[a-z]?[^()]{0,40})\)"
)
_NARRATIVE = re.compile(
    r"\b([A-Z][a-zA-Z\-']+(?:\s+(?:and|&)\s+[A-Z][a-zA-Z\-']+)?(?:\s+et\s+al\.?)?)\s*\(((?:19|20)\d{2}[a-z]?)\)"
)
_NUMERIC_CITATION = re.compile(r"\[(\d{1,3}(?:\s*[-–,]\s*\d{1,3})*)\]")


def extract_intext_citations(body_text: str) -> list[dict]:
    """Return in-text citations: author-year (parenthetical + narrative) and
    numbered ([1], [2-5], [1,3])."""
    cites: list[dict] = []
    seen: set[tuple] = set()

    for m in _NARRATIVE.finditer(body_text):
        author, year = m.group(1), m.group(2)
        key = ("ay", author.lower().replace("et al", "").strip(" ."), year)
        if key not in seen:
            seen.add(key)
            cites.append({"style": "author_year", "author": author, "year": year, "raw": m.group(0)})

    for m in _PAREN_CITATION.finditer(body_text):
        inner = m.group(1)
        # Split multi-citation parentheses: (Smith, 2020; Jones, 2021)
        for part in re.split(r";", inner):
            ym = re.search(r"(?:19|20)\d{2}[a-z]?", part)
            if not ym:
                continue
            author_part = part[: ym.start()].strip(" ,.&")
            author_match = re.search(r"([A-Z][a-zA-Z\-']+(?:\s+(?:and|&)\s+[A-Z][a-zA-Z\-']+)?(?:\s+et\s+al\.?)?)\s*$", author_part)
            if not author_match:
                continue
            author = author_match.group(1)
            year = ym.group(0)
            key = ("ay", author.lower().replace("et al", "").strip(" ."), year)
            if key not in seen:
                seen.add(key)
                cites.append({"style": "author_year", "author": author, "year": year, "raw": part.strip()})

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

def extract(text: str, pages: int = 0) -> tuple[list[str], list[dict], DocumentStats]:
    """Return (raw reference entries, in-text citations, doc stats)."""
    bib = locate_bibliography(text)
    refs = segment_references(bib) if bib else []
    body = text[: text.rfind(bib)] if bib and text.rfind(bib) > 0 else text
    cites = extract_intext_citations(body)
    stats = document_stats(text, pages)
    stats.reference_count = len(refs)
    stats.intext_citation_count = len(cites)
    return refs, cites, stats
