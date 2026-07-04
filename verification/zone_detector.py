"""verification/zone_detector.py — TRACE-AI Zone Detector v1 (dumb provenance layer).

A deterministic classifier that labels each line of a document with a structural
zone. It NEVER deletes text, NEVER does semantic inference, and defers all
filtering decisions to downstream consumers.

Zones:  body | metadata | references | header_footer | noise
Precedence when several rules fire:  references > metadata > header_footer > noise > body
Default (all ambiguity):  body

Design rules (non-negotiable):
  A. No deletion — only labelling.
  B. Conservative noise — if unsure, NOT noise.
  C. Line-level truth — everything derives from per-line labels.
  D. Deterministic only — no embeddings, no similarity, no LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# --------------------------------------------------------------------------
# Zones & precedence
# --------------------------------------------------------------------------

ZONES = ("references", "metadata", "header_footer", "noise", "body")
_PRECEDENCE = {z: i for i, z in enumerate(ZONES)}  # lower index = higher priority


@dataclass
class ZonedLine:
    text: str
    zone: str = "body"
    confidence: float = 0.2
    signals: list[str] = field(default_factory=list)
    page_number: Optional[int] = None


# --------------------------------------------------------------------------
# Rule patterns
# --------------------------------------------------------------------------

_SECTION_HEADER = re.compile(
    r"^\s*(?:\d+\.?\s*)?(references|bibliography|works\s+cited|reference\s+list)\s*:?\s*$",
    re.IGNORECASE,
)

# metadata (any of these => metadata candidate)
_META_PATTERNS = [
    ("regex:doi", re.compile(r"(?i)\bdoi\b\s*[:\-]?\s*10\.\d{4,9}/")),
    ("regex:doi_label", re.compile(r"(?i)^\s*doi\b")),
    ("regex:issn", re.compile(r"(?i)\bissn\b")),
    ("regex:isbn", re.compile(r"(?i)\bisbn\b")),
    ("regex:received", re.compile(r"(?i)\breceived\s+\d")),
    ("regex:accepted", re.compile(r"(?i)\baccepted\s+\d")),
    ("regex:published_online", re.compile(r"(?i)\bpublished\s+online\b")),
    ("regex:copyright", re.compile(r"(?i)copyright|©")),
]

# reference-entry shape (used only to *strengthen* an already-open references section)
_REF_ENTRY_HINT = re.compile(
    r"(?:19|20)\d{2}"                                   # a year
    r"|10\.\d{4,9}/"                                    # a DOI
    r"|^\s*\[\d{1,3}\]|^\s*\d{1,3}\.\s+[A-Z]"           # numbered marker
)

# header/footer
_PAGE_NUMBER = re.compile(r"(?i)^\s*(page\s+\d+|\d+\s*/\s*\d+|\d{1,4})\s*$")
_RUNNING_HEAD_HINT = re.compile(r"[A-Z]")

# noise (very conservative)
_OCR_TRIGRAM = re.compile(r"^[A-Za-z]{1,3}\s[A-Za-z]{1,3}\s[A-Za-z]{1,3}$")
_GLYPH_JUNK = re.compile(r"^[^\w\s]{5,}$")
_REPLACEMENT_CHAR = re.compile(r"[\ufffd]|Ã©|##@@")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _caps_ratio(line: str) -> float:
    letters = [c for c in line if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if c.isupper()) / len(letters)


def _word_count(line: str) -> int:
    return len(line.split())


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------

def _split_pages(text: str, pages: Optional[list[dict]]):
    """Yield (page_number, line_index_within_page, total_lines_in_page, line)."""
    if pages:
        for p in pages:
            lines = p.get("lines") or []
            for i, ln in enumerate(lines):
                yield p.get("page_number"), i, len(lines), ln
    else:
        lines = text.split("\n")
        for i, ln in enumerate(lines):
            yield None, i, len(lines), ln


def _find_repeated_lines(all_lines: list[str], min_repeats: int = 3) -> set[str]:
    """Lines that appear identically >= min_repeats times — running-head candidates."""
    from collections import Counter
    counts = Counter(ln.strip() for ln in all_lines if ln.strip())
    return {ln for ln, c in counts.items() if c >= min_repeats and len(ln) > 0}


def detect_zones(text: str, pages: Optional[list[dict]] = None) -> list[ZonedLine]:
    """Return a ZonedLine for every line, in document order."""
    rows = list(_split_pages(text, pages))
    all_line_texts = [ln for _, _, _, ln in rows]
    repeated = _find_repeated_lines(all_line_texts)
    have_pages = bool(pages)

    result: list[ZonedLine] = []
    in_references = False

    for page_number, idx_in_page, page_len, raw_line in rows:
        line = raw_line.rstrip("\n")
        stripped = line.strip()
        candidates: list[tuple[str, float, list[str]]] = []  # (zone, confidence, signals)

        # ---- references section state ----
        if _SECTION_HEADER.match(stripped):
            in_references = True
            result.append(ZonedLine(text=line, zone="references", confidence=0.9,
                                    signals=["regex:ref_section_header"], page_number=page_number))
            continue

        # An Appendix/Annex heading closes the references section.
        if in_references and re.match(r"(?i)^\s*(appendix|annex)\b", stripped):
            in_references = False

        # ---- metadata ----
        meta_signals = [name for name, pat in _META_PATTERNS if pat.search(stripped)]
        if meta_signals:
            candidates.append(("metadata", 0.9, meta_signals))

        # ---- references (inside open section) ----
        if in_references and stripped:
            sig = ["state:in_references"]
            conf = 0.9 if _REF_ENTRY_HINT.search(stripped) else 0.6
            candidates.append(("references", conf, sig))

        # ---- header_footer ----
        hf_signals: list[str] = []
        hf_conf = 0.0
        top_or_bottom = (idx_in_page <= 1) or (idx_in_page >= page_len - 2)
        if _PAGE_NUMBER.match(stripped):
            hf_signals.append("regex:page_number")
            hf_conf = max(hf_conf, 0.9)
        if stripped and stripped in repeated:
            hf_signals.append("pos:repeat" if have_pages else "pos:pseudo_repeat")
            hf_conf = max(hf_conf, 0.6 if have_pages else 0.4)
        if (stripped and _word_count(stripped) < 12 and _caps_ratio(stripped) > 0.8
                and (top_or_bottom or not have_pages) and _RUNNING_HEAD_HINT.search(stripped)):
            hf_signals.append("heuristic:allcaps_short")
            hf_conf = max(hf_conf, 0.6)
        if hf_signals:
            candidates.append(("header_footer", hf_conf, hf_signals))

        # ---- noise (very conservative) ----
        noise_signals: list[str] = []
        if _REPLACEMENT_CHAR.search(stripped):
            noise_signals.append("regex:replacement_char")
        if _GLYPH_JUNK.match(stripped):
            noise_signals.append("regex:glyph_junk")
        if _OCR_TRIGRAM.match(stripped):
            noise_signals.append("regex:ocr_trigram")
        if noise_signals:
            # Hard rule B: only mark noise on a clear signal; keep confidence honest.
            candidates.append(("noise", 0.6, noise_signals))

        # ---- resolve by precedence ----
        if not candidates:
            result.append(ZonedLine(text=line, zone="body", confidence=0.2,
                                    signals=["default:body"], page_number=page_number))
            continue

        # Special override: inside references, references beats metadata.
        zones_present = {z for z, _, _ in candidates}
        if in_references and "references" in zones_present and "metadata" in zones_present:
            candidates = [c for c in candidates if c[0] != "metadata"]

        # Narrow override: a running head or bare page number embedded mid-
        # bibliography (page break) is structurally header_footer, not a
        # reference. Real bibliography entries are never all-caps-only nor a
        # bare page number, so this cannot swallow a genuine reference.
        if in_references and "references" in zones_present and "header_footer" in zones_present:
            hf = next(c for c in candidates if c[0] == "header_footer")
            strong_hf = any(s in ("regex:page_number", "heuristic:allcaps_short",
                                  "pos:repeat") for s in hf[2])
            if strong_hf:
                candidates = [c for c in candidates if c[0] != "references"]

        # Pick highest-precedence zone; merge its signals; bump/penalise confidence.
        best = min(candidates, key=lambda c: _PRECEDENCE[c[0]])
        zone, conf, signals = best
        agree = [c for c in candidates if c[0] == zone]
        merged_signals = sorted({s for _, _, sig in agree for s in sig})
        if len(merged_signals) > 1:
            conf = _clamp(conf + 0.1)
        elif conf <= 0.4:
            conf = _clamp(conf - 0.2)

        result.append(ZonedLine(text=line, zone=zone, confidence=round(conf, 2),
                                signals=merged_signals, page_number=page_number))

    return result


# --------------------------------------------------------------------------
# Convenience consumers
# --------------------------------------------------------------------------

def lines_in_zone(zoned: list[ZonedLine], *zones: str) -> list[str]:
    """Return the raw text of lines whose zone is in `zones`."""
    want = set(zones)
    return [z.text for z in zoned if z.zone in want]


def zone_text(zoned: list[ZonedLine], *zones: str) -> str:
    """Return lines of the given zones joined back into a text block."""
    return "\n".join(lines_in_zone(zoned, *zones))


def group_blocks(zoned: list[ZonedLine]) -> list[dict]:
    """Post-process: group contiguous same-zone lines into blocks (line indices)."""
    blocks: list[dict] = []
    for i, z in enumerate(zoned):
        if blocks and blocks[-1]["zone"] == z.zone:
            blocks[-1]["lines"].append(i)
        else:
            blocks.append({"zone": z.zone, "lines": [i]})
    return blocks


def to_dict(zoned: list[ZonedLine]) -> dict:
    """Canonical JSON-serialisable output."""
    return {
        "lines": [
            {"text": z.text, "zone": z.zone, "confidence": z.confidence,
             "signals": z.signals, "page_number": z.page_number}
            for z in zoned
        ]
    }
