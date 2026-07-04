"""Citation checker (core/citation_checker.py). — DEPRECATED

DEPRECATED: superseded by the `verification/` package (external verification
pipeline v2.0), which checks every reference against six external scholarly
sources. This module remains fully functional for backward compatibility
(its self-test still passes) but nothing imports it now except by choice.
Use:  from verification import verify_document

Extracts references from a PDF, verifies DOIs via Crossref, and checks
whether in-text citations match the reference list.

CHANGES IN THIS VERSION (vs. the original backup):

  1. extract_references() — REPLACED the blank-line-only split with
     structure-aware paragraph/block segmentation that also handles
     reference lists with NO blank lines between entries (very common in
     PDF text extraction), using a year-gated reference-start detector so
     multi-author lists ("Smith, J., Johnson, A., Brown, C. (2021)...")
     don't get mis-split mid-list.

  2. Each reference now gets a weighted CONFIDENCE SCORE and a 3-level
     STATUS (accept / needs_review / reject) instead of the old crude
     "if len(ref) < 20: skip" filter — see score_reference_likelihood()
     and decide_status() below.

  3. NEW: in-text citations are now actually CROSS-CHECKED against the
     reference list (the original docstring promised this; the original
     code never did it — extract_intext_citations() and extract_references()
     were computed but never compared). match_intext_to_references() closes
     that gap, using normalized author+year matching so "Smith, 2020" and
     "Smith, J. (2020)" are recognised as the same work despite different
     formatting.

  4. DOI verification via Crossref is UNCHANGED — verify_doi() still works
     exactly as before.

Public function names and the core dict fields (index, text, doi, verified,
title_found, status) are kept the same as the original, with additive new
fields (confidence, matched_intext) so nothing downstream that already
consumes this module's output should break.
"""

import re
import requests

CROSSREF_API = "https://api.crossref.org/works/"
TIMEOUT = 8


# ---------------------------------------------------------------------------
# STAGE 1 — Structure-aware reference segmentation
# (replaces the old blank-line-only split)
# ---------------------------------------------------------------------------

_YEAR_PATTERN = re.compile(r"\((?:19|20)\d{2}[a-z]?\)|\b(?:19|20)\d{2}[a-z]?\b")
_NUMBERED_MARKER = re.compile(r"^\s*(\[\d{1,3}\]|\d{1,3}\.)\s+")
_AUTHOR_SURNAME = re.compile(r"^\s*[A-Z][a-zA-Z\-']+,\s*[A-Z]\.")


def _looks_like_org_start(line: str) -> bool:
    """
    Checks the text BEFORE the first digit/parenthesis on the line for an
    organisational-author shape. Unlike a full-line match, this also
    catches the common case where the org name and the rest of the
    citation share one line, e.g. "OECD (2023b). Taxing Wages 2023...",
    not just a standalone org-name-only line.
    """
    prefix = re.split(r"[\(\d]", line, maxsplit=1)[0].strip()
    if not prefix:
        return False
    words = prefix.split()
    if 1 <= len(words) <= 8:
        cap_words = [w for w in words if w[:1].isupper()]
        if len(cap_words) / len(words) >= 0.8:
            return True
    return False


def _is_reference_start_line(line: str) -> bool:
    if not line.strip():
        return False
    if _NUMBERED_MARKER.match(line):
        return True
    if _AUTHOR_SURNAME.match(line):
        return True
    if _looks_like_org_start(line):
        return True
    return False


def _split_on_reference_starts(paragraph: str) -> list[str]:
    """
    Splits a block of text into multiple reference entries using a
    YEAR-GATED boundary rule: a line only starts a NEW reference if the
    previous reference has already closed out with its own "(YYYY)" —
    this is what correctly keeps a wrapped multi-author list together
    ("Smith, J., Johnson, A., Brown, C. (2021)...") instead of splitting
    it the moment a second "Surname, Initial" pattern appears.
    """
    lines = paragraph.split("\n")
    if len(lines) <= 1:
        return [paragraph]

    boundaries = [0]
    seen_year_since_boundary = bool(_YEAR_PATTERN.search(lines[0]))

    for i in range(1, len(lines)):
        line = lines[i]
        if _is_reference_start_line(line) and seen_year_since_boundary:
            boundaries.append(i)
            seen_year_since_boundary = False
        if _YEAR_PATTERN.search(line):
            seen_year_since_boundary = True

    if len(boundaries) <= 1:
        return [paragraph]

    boundaries.append(len(lines))
    return ["\n".join(lines[boundaries[i]:boundaries[i + 1]])
            for i in range(len(boundaries) - 1)]


def _segment_reference_section(ref_section: str) -> list[str]:
    """
    Two-level segmentation:
      1. Split on blank lines first (the common case).
      2. Within EACH resulting block, also run the year-gated reference-start
         splitter — this is what fixes the "no blank lines at all" case,
         since a no-blank-line reference section arrives here as ONE giant
         block from step 1, which step 2 then breaks apart correctly.
    """
    raw_paragraphs = re.split(r"\n\s*\n+", ref_section)
    raw_paragraphs = [p for p in raw_paragraphs if p.strip()]

    blocks = []
    for para in raw_paragraphs:
        blocks.extend(_split_on_reference_starts(para))

    return [re.sub(r"\s+", " ", b).strip() for b in blocks if b.strip()]


# ---------------------------------------------------------------------------
# STAGE 2 — Weighted confidence scoring (replaces the "len(ref) < 20" filter)
# ---------------------------------------------------------------------------

_DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[^\s\"<>]+", re.IGNORECASE)
_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
_VOLUME_ISSUE_PATTERN = re.compile(r"\b\d{1,4}\s*\(\s*\d{1,3}\s*\)")
_PAGES_PATTERN = re.compile(r"\b\d{1,4}\s*[-\u2013]\s*\d{1,4}\b")
_AUTHOR_LIST_PATTERN = re.compile(r"[A-Z][a-zA-Z\-']+,\s*[A-Z]\.(\s*[A-Z]\.)?")
# Word-stem based (catches "Publisher"/"Publishing"/"Publication" together,
# not just the exact word "publisher" — the old substring check missed
# "OECD Publishing", under-scoring common government/NGO report citations).
_PUBLISHER_KEYWORD_PATTERN = re.compile(
    r"\bjournal\b|\bpress\b|\buniversity\b|\bpublish\w*\b|\bproceedings\b|"
    r"\bconference\b|\bedition\b|\bed\.|\bvol\.|\bpp\.|retrieved from|"
    r"available at|in press|advance online",
    re.IGNORECASE,
)
# "City: Publisher." — the standard structural marker for books/reports
# (as opposed to journal articles), common in OECD/WHO/UN/government-style
# organisational references that otherwise carry few other citation signals.
_CITY_PUBLISHER_PATTERN = re.compile(r"\b[A-Z][a-zA-Z]+:\s*[A-Z]")
_NARRATIVE_VERB_PHRASE = re.compile(
    r"\bwe (found|show|present|argue|conclude|observed|report|examine)\b|"
    r"\bthis (study|paper|report|article) (shows|demonstrates|finds|argues|presents)\b|"
    r"\bresults? (indicate|suggest|show)\b|\bour (analysis|findings|results)\b|"
    r"\bin this (paper|study)\b",
    re.IGNORECASE,
)

_FEATURE_WEIGHTS = {
    "has_year": 2.0, "has_doi": 2.5, "has_url": 1.0, "has_volume_issue": 1.5,
    "has_pages": 1.5, "has_publisher_keyword": 1.5, "starts_with_author_or_org": 2.0,
    "has_city_publisher": 1.5,
}
_MAX_AUTHOR_BONUS = 2.0
_MAX_SCORE = sum(_FEATURE_WEIGHTS.values()) + _MAX_AUTHOR_BONUS


def _starts_with_author_or_org(block: str) -> bool:
    if _AUTHOR_SURNAME.match(block):
        return True
    prefix = re.split(r"[\(\d]", block, maxsplit=1)[0].strip()
    if not prefix:
        return False
    words = prefix.split()
    if 1 <= len(words) <= 8:
        cap_words = [w for w in words if w[:1].isupper()]
        if len(cap_words) / len(words) >= 0.8:
            return True
    return False


def score_reference_likelihood(block: str) -> tuple[float, dict]:
    """Returns (confidence in [0, 1], feature breakdown) for a candidate block."""
    features = {
        "has_year": bool(_YEAR_PATTERN.search(block)),
        "has_doi": bool(_DOI_PATTERN.search(block)),
        "has_url": bool(_URL_PATTERN.search(block)),
        "has_volume_issue": bool(_VOLUME_ISSUE_PATTERN.search(block)),
        "has_pages": bool(_PAGES_PATTERN.search(block)),
        "has_publisher_keyword": bool(_PUBLISHER_KEYWORD_PATTERN.search(block)),
        "has_city_publisher": bool(_CITY_PUBLISHER_PATTERN.search(block)),
        "author_count": len(_AUTHOR_LIST_PATTERN.findall(block)),
        "starts_with_author_or_org": _starts_with_author_or_org(block),
        "has_narrative_verb_phrase": bool(_NARRATIVE_VERB_PHRASE.search(block)),
        "period_count": block.count("."),
        "length": len(block),
    }

    raw = sum(weight for key, weight in _FEATURE_WEIGHTS.items() if features.get(key))
    raw += min(features["author_count"] * 0.5, _MAX_AUTHOR_BONUS)

    length_penalty = 0.5 if features["length"] < 25 else (0.3 if features["length"] > 600 else 0.0)

    negative_penalty = 0.0
    if features["has_narrative_verb_phrase"]:
        negative_penalty += 2.0
    if features["period_count"] < 2:
        negative_penalty += 0.5

    confidence = max(0.0, min(1.0, (raw / _MAX_SCORE) - length_penalty - negative_penalty))
    return confidence, features


# 3-level decision thresholds (see citation_decision.py for the standalone
# version of this design — accept / needs_review / reject instead of a
# binary keep/discard cutoff).
ACCEPT_THRESHOLD = 0.70
REVIEW_THRESHOLD = 0.40


def decide_status(confidence: float) -> str:
    if confidence >= ACCEPT_THRESHOLD:
        return "accept"
    if confidence >= REVIEW_THRESHOLD:
        return "needs_review"
    return "reject"


def extract_references(text: str) -> list[dict]:
    """Extract reference entries from document text."""
    ref_section = ""
    patterns = [
        r"(?:References|REFERENCES|Bibliography|BIBLIOGRAPHY)\s*\n(.*?)(?:\n\n\n|\Z)",
        r"(?:References|REFERENCES)\s*\n(.*?)(?=\n[A-Z][a-z]+ [A-Z]|\Z)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.DOTALL)
        if m:
            ref_section = m.group(1)
            break

    if not ref_section:
        ref_section = text[-3000:]  # fallback: last 3000 chars

    blocks = _segment_reference_section(ref_section)

    parsed = []
    i = 0
    for block in blocks:
        if not _YEAR_PATTERN.search(block):
            continue  # cheap pre-filter: a reference must at least have a year

        confidence, features = score_reference_likelihood(block)
        status_from_score = decide_status(confidence)
        if status_from_score == "reject":
            continue  # confidently not a reference — drop, same as old "len < 20" did

        doi = extract_doi(block)
        i += 1
        parsed.append({
            "index": i,
            "text": block[:300],
            "doi": doi,
            "verified": None,
            "title_found": None,
            "status": "pending",            # overwritten below by DOI verification
            "confidence": round(confidence, 3),
            "extraction_status": status_from_score,  # "accept" or "needs_review"
        })

    return parsed[:50]  # max 50 refs


def extract_doi(text: str) -> str | None:
    """Extract DOI from reference text."""
    patterns = [
        r"https?://doi\.org/(10\.\S+)",
        r"doi:\s*(10\.\S+)",
        r"DOI:\s*(10\.\S+)",
        r"\b(10\.\d{4,}/\S+)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            doi = m.group(1).rstrip(".")
            return doi
    return None


def verify_doi(doi: str) -> dict:
    """Verify a DOI via Crossref API."""
    try:
        url = CROSSREF_API + requests.utils.quote(doi, safe="")
        r = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": "TRACE-AI/1.0"})
        if r.status_code == 200:
            data = r.json().get("message", {})
            title = data.get("title", [""])[0] if data.get("title") else ""
            year = ""
            if data.get("published"):
                parts = data["published"].get("date-parts", [[""]])
                year = str(parts[0][0]) if parts and parts[0] else ""
            return {"found": True, "title": title, "year": year}
        else:
            return {"found": False, "title": "", "year": ""}
    except Exception:
        return {"found": None, "title": "", "year": ""}


def extract_intext_citations(text: str) -> list[str]:
    """Extract in-text citations (Author, Year format)."""
    patterns = [
        r"\(([A-Z][a-z]+(?:\s+(?:and|&)\s+[A-Z][a-z]+)?,?\s+\d{4}[a-z]?(?:;\s*[A-Z][a-z]+[^)]*\d{4}[a-z]?)*)\)",
        r"\(([A-Z][a-z]+ et al\.?,?\s+\d{4}[a-z]?)\)",
    ]
    citations = set()
    for pat in patterns:
        for m in re.finditer(pat, text):
            citations.add(m.group(1).strip())
    return sorted(citations)


# ---------------------------------------------------------------------------
# NEW: in-text <-> reference-list cross-check (the docstring's original
# promise — extract_intext_citations() and extract_references() were both
# computed in the old run_citation_check() but never actually compared).
# ---------------------------------------------------------------------------

def _intext_key(citation: str) -> tuple[str, str]:
    """Normalizes 'Smith, 2020' / 'Smith et al., 2020' / 'Smith & Jones, 2020'
    down to (first_surname_lower, year) for matching against reference keys."""
    year_m = re.search(r"(\d{4}[a-z]?)", citation)
    year = year_m.group(1).lower() if year_m else ""
    surname_m = re.match(r"\s*([A-Z][a-z]+)", citation)
    surname = surname_m.group(1).lower() if surname_m else ""
    return surname, year


def _reference_key(ref_text: str) -> tuple[str, str]:
    """Same (surname, year) normalization, applied to a parsed reference's
    full text — this is the shared key both sides are matched on."""
    year_m = _YEAR_PATTERN.search(ref_text)
    year = re.sub(r"[()]", "", year_m.group(0)).lower() if year_m else ""

    surname = ""
    m = _AUTHOR_SURNAME.match(ref_text)
    if m:
        surname = re.match(r"\s*([A-Za-z\-']+)", ref_text).group(1).lower()
    elif _looks_like_org_start(ref_text):
        prefix = re.split(r"[\(\d]", ref_text, maxsplit=1)[0].strip()
        if prefix:
            surname = prefix.split()[0].lower()
    return surname, year


def match_intext_to_references(intext_citations: list[str], references: list[dict]) -> dict:
    """
    Cross-checks in-text citations against the parsed reference list using
    normalized (surname, year) keys, so "Smith, 2020" matches a reference
    formatted as "Smith, J. (2020)..." despite the different formatting —
    a plain set() intersection on raw strings would miss this every time.
    """
    ref_keys = {_reference_key(r["text"]) for r in references}

    matched, unmatched = [], []
    for citation in intext_citations:
        key = _intext_key(citation)
        if key in ref_keys and key != ("", ""):
            matched.append(citation)
        else:
            unmatched.append(citation)

    return {"matched": matched, "unmatched": unmatched}


def run_citation_check(text: str, pdf_path: str = None) -> dict:
    """Run full citation check on document text."""
    references = extract_references(text)
    intext = extract_intext_citations(text)
    crosscheck = match_intext_to_references(intext, references)

    verified_count = 0
    not_found_count = 0
    no_doi_count = 0

    for ref in references:
        if ref["doi"]:
            result = verify_doi(ref["doi"])
            ref["verified"] = result["found"]
            ref["title_found"] = result["title"]
            ref["year_found"] = result.get("year", "")
            if result["found"] is True:
                ref["status"] = "verified"
                verified_count += 1
            elif result["found"] is False:
                ref["status"] = "not_found"
                not_found_count += 1
            else:
                ref["status"] = "error"
        else:
            ref["status"] = "no_doi"
            no_doi_count += 1

    return {
        "references": references,
        "intext_citations": intext,
        "intext_matched": crosscheck["matched"],
        "intext_unmatched": crosscheck["unmatched"],
        "summary": {
            "total_refs": len(references),
            "with_doi": len([r for r in references if r["doi"]]),
            "verified": verified_count,
            "not_found": not_found_count,
            "no_doi": no_doi_count,
            "total_intext": len(intext),
            "intext_matched": len(crosscheck["matched"]),
            "intext_unmatched": len(crosscheck["unmatched"]),
            "needs_review": len([r for r in references if r.get("extraction_status") == "needs_review"]),
        }
    }


# ---------------------------------------------------------------------------
# Self-test (run directly: `python core/citation_checker.py`)
# No network calls — exercises extract_references / extract_intext_citations /
# match_intext_to_references only. verify_doi() hits the live Crossref API
# and is intentionally NOT covered here.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sample_doc = """
This paper discusses tax policy (Smith, 2021) and inequality (OECD, 2023b).
Some other work (Brown et al., 2021) also covers this area, as does Doe (2019).
We found that this combination of factors significantly improved outcomes,
as our analysis shows in the section below.

References

Smith, J., Johnson, A., Williams, B., Brown, C., Taylor, D., Anderson, M.
(2021). A long-author-list study of citation extraction failures.
Journal of Applied Linguistics, 14(2), 110-134.
Brown, C. (2021). An unrelated short reference, no blank line before it. Journal Z, 3(4), 21-30.
OECD (2023b). Taxing Wages 2023. Paris: OECD Publishing.

This is just a body-text paragraph mentioning the year 2020 in passing,
with no other reference-like features at all.
"""

    print("=== extract_references() ===")
    refs = extract_references(sample_doc)
    for r in refs:
        print(f"[{r['confidence']:.2f}] {r['extraction_status']:>13} | {r['text']}")

    # No-blank-line references (Smith / Brown / OECD all run together) must
    # be split into THREE separate entries, not glued into one or dropped.
    assert len(refs) == 3, f"FAIL: expected 3 references, got {len(refs)}"
    print(f"PASS: 3 distinct references extracted from a no-blank-line reference list\n")

    smith_ref = next(r for r in refs if r["text"].startswith("Smith"))
    assert "Anderson, M." in smith_ref["text"], \
        "FAIL: multi-author list was split incorrectly"
    print("PASS: multi-line, multi-author reference kept as ONE block")

    oecd_ref = next((r for r in refs if r["text"].startswith("OECD")), None)
    assert oecd_ref is not None, "FAIL: short organisational reference (OECD) was dropped"
    print("PASS: short organisational/government reference (OECD) not dropped\n")

    print("=== extract_intext_citations() + match_intext_to_references() ===")
    intext = extract_intext_citations(sample_doc)
    print("In-text citations found:", intext)
    cross = match_intext_to_references(intext, refs)
    print("Matched:", cross["matched"])
    print("Unmatched:", cross["unmatched"])

    assert "Smith, 2021" in cross["matched"], \
        "FAIL: 'Smith, 2021' should match the Smith et al. reference"
    assert "Brown et al., 2021" in cross["matched"], \
        "FAIL: 'Brown et al., 2021' should match the Brown reference"
    print("PASS: in-text citations correctly cross-matched against the reference list "
          "(this check did not exist in the original file)\n")

    print("All regression checks passed.")
