"""verification/reference_normalizer.py — Stage 2.

Parses each raw bibliography entry into structured fields: authors, title,
journal/conference/publisher, year, volume, issue, pages, DOI, URL, arXiv id,
reference number, a type guess, and an extraction confidence.

External matching needs structured fields to compare against database records;
regex-only DOI checking can't do that.
"""

from __future__ import annotations

import re
from typing import Optional

from .models import NormalizedReference

_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s\"'<>,;]+)", re.IGNORECASE)
_URL = re.compile(r"\bhttps?://[^\s\"'<>)\]]+", re.IGNORECASE)
_ARXIV = re.compile(r"\barXiv:\s*(\d{4}\.\d{4,5}(?:v\d+)?)", re.IGNORECASE)
_YEAR = re.compile(r"\(((?:19|20)\d{2})[a-z]?\)|\b((?:19|20)\d{2})[a-z]?\b")
_REF_NUMBER = re.compile(r"^\s*(?:\[(\d{1,3})\]|(\d{1,3})\.)\s+")
_VOL_ISSUE_PAGES = re.compile(r"\b(\d{1,4})\s*\((\d{1,4})\)\s*,?\s*(?:pp?\.\s*)?(\d+\s*[\-–]\s*\d+)")
_PAGES_ONLY = re.compile(r"\b(?:pp?\.\s*)(\d+\s*[\-–]\s*\d+)")
_AUTHOR_TOKEN = re.compile(r"([A-Z][a-zA-Z\-']+),\s*((?:[A-Z]\.\s*)+|[A-Z][a-z]+)")

_CONFERENCE_HINTS = re.compile(r"\b(proceedings|conference|symposium|workshop)\b", re.IGNORECASE)
_BOOK_HINTS = re.compile(r"\b(press|publish|publications?|books?|edition|ed\.)\b", re.IGNORECASE)
_REPORT_HINTS = re.compile(r"\b(report|working paper|white paper|technical)\b", re.IGNORECASE)


def _clean_doi(doi: str) -> str:
    return doi.rstrip(".,;)")


def _extract_authors(head: str) -> list[str]:
    """head = the part of the entry before the year."""
    authors = []
    for surname, initials in _AUTHOR_TOKEN.findall(head):
        authors.append(f"{surname}, {initials.strip()}")
        if len(authors) >= 25:
            break
    if not authors:
        # Organisational author: "World Health Organization."
        org = re.match(r"^\s*([A-Z][A-Za-z&,\-' ]{3,80}?)\.\s", head)
        if org:
            authors = [org.group(1).strip()]
    return authors


def _extract_title(entry: str, year_end: int) -> Optional[str]:
    """Title = text after the (year). up to the next sentence-ending period.

    APA: Author, A. (2020). Title of the work. Journal, 1(2), 3-4.
    """
    tail = entry[year_end:].lstrip(" .:—-")
    if not tail:
        return None
    # Stop at ". " followed by an uppercase letter or at " Retrieved"/" http"
    m = re.search(r"[.?!](?=\s+[A-Z(])|\s+(?=Retrieved\b)|\s+(?=https?://)", tail)
    title = tail[: m.start()] if m else tail
    title = title.strip(" .\"'“”")
    if len(title) < 4:
        return None
    return title[:300]


def _extract_container(entry: str, title: Optional[str], year_end: int) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (journal, conference, publisher) — at most one meaningfully set."""
    tail = entry[year_end:]
    if title:
        pos = tail.find(title)
        if pos >= 0:
            tail = tail[pos + len(title):]
    # Bug fix (from v2.0 build log): lstrip punctuation BEFORE container matching —
    # a trailing '". ' from the title otherwise hides the journal name.
    tail = tail.lstrip(" .\"'“”:,")

    if _CONFERENCE_HINTS.search(entry):
        m = re.match(r"(?:In\s+)?([A-Z][^.,\d]{5,120})", tail)
        return None, (m.group(1).strip() if m else None), None

    # Journal: capitalised phrase ending before volume(issue) or a comma+digits
    m = re.match(r"(?:In\s+)?([A-Z][A-Za-z&:\-' ]{3,120}?)\s*,\s*\d", tail)
    if m:
        return m.group(1).strip(), None, None
    m = re.match(r"([A-Z][A-Za-z&:\-' ]{3,120}?)\.\s", tail)
    if m and _BOOK_HINTS.search(tail[:200]):
        return None, None, m.group(1).strip()
    if m:
        return m.group(1).strip(), None, None
    return None, None, None


def _guess_type(entry: str, journal, conference, publisher, arxiv_id) -> str:
    if arxiv_id:
        return "preprint"
    if conference or _CONFERENCE_HINTS.search(entry):
        return "conference"
    if _REPORT_HINTS.search(entry):
        return "report"
    if publisher or (_BOOK_HINTS.search(entry) and not journal):
        return "book"
    if _URL.search(entry) and not journal and not _DOI.search(entry):
        return "web"
    return "article"


def normalize(raw: str, index: int) -> NormalizedReference:
    entry = re.sub(r"\s+", " ", raw).strip()
    ref = NormalizedReference(index=index, raw_text=entry)

    num = _REF_NUMBER.match(entry)
    if num:
        ref.ref_number = int(num.group(1) or num.group(2))
        entry_body = entry[num.end():]
    else:
        entry_body = entry

    doi = _DOI.search(entry_body)
    if doi:
        ref.doi = _clean_doi(doi.group(1))
    arx = _ARXIV.search(entry_body)
    if arx:
        ref.arxiv_id = arx.group(1)
    url = _URL.search(entry_body)
    if url and (not ref.doi or ref.doi not in url.group(0)):
        ref.url = url.group(0).rstrip(".,;)")

    year_match = _YEAR.search(entry_body)
    if year_match:
        ref.year = int(year_match.group(1) or year_match.group(2))
        head = entry_body[: year_match.start()]
        year_end = year_match.end()
    else:
        head = entry_body[:120]
        year_end = 0

    ref.authors = _extract_authors(head)
    ref.title = _extract_title(entry_body, year_end) if year_match else None
    ref.journal, ref.conference, ref.publisher = _extract_container(entry_body, ref.title, year_end)

    vip = _VOL_ISSUE_PAGES.search(entry_body)
    if vip:
        ref.volume, ref.issue, ref.pages = vip.group(1), vip.group(2), re.sub(r"\s", "", vip.group(3))
    else:
        pg = _PAGES_ONLY.search(entry_body)
        if pg:
            ref.pages = re.sub(r"\s", "", pg.group(1))

    ref.type_guess = _guess_type(entry_body, ref.journal, ref.conference, ref.publisher, ref.arxiv_id)

    # Extraction confidence: proportion of core fields we managed to parse.
    got = sum([
        bool(ref.authors) * 2,
        bool(ref.title) * 2,
        bool(ref.year) * 2,
        bool(ref.journal or ref.conference or ref.publisher),
        bool(ref.doi or ref.url or ref.arxiv_id),
    ])
    ref.extraction_confidence = round(got / 8, 2)
    return ref


def normalize_all(raw_entries: list[str]) -> list[NormalizedReference]:
    return [normalize(raw, i + 1) for i, raw in enumerate(raw_entries)]
