"""
TRACE-AI — Human-Readable Labels (core/labels.py)

Turns raw scores and sources into things a researcher reads instantly:
  - evidence strength badge (Strong / Moderate / Weak)
  - clean source label ("Government Report (gov.uk) · Page 14")
  - partial-support strength (Weak / Moderate / Strong partial)

Pure presentation-logic helpers; thresholds come from config.
"""

import re
from config.thresholds import STRENGTH_STRONG, STRENGTH_MODERATE


def evidence_strength(span_score_value: float) -> dict:
    """Maps a per-span score to a Strong/Moderate/Weak badge."""
    if span_score_value >= STRENGTH_STRONG:
        return {"label": "Strong Evidence", "emoji": "🟢", "level": "strong"}
    if span_score_value >= STRENGTH_MODERATE:
        return {"label": "Moderate Evidence", "emoji": "🟡", "level": "moderate"}
    return {"label": "Weak Evidence", "emoji": "🔴", "level": "weak"}


def clean_source_label(source: str, page_number=None) -> str:
    """Turns a long filename or URL into a short, readable source label."""
    if not source:
        return "Unknown source"

    label = source
    if source.lower().startswith(("http://", "https://")):
        m = re.search(r"https?://([^/]+)", source)
        domain = m.group(1).replace("www.", "") if m else source
        if "gov.uk" in domain:
            label = f"Government Report ({domain})"
        elif domain.endswith((".ac.uk", ".edu")):
            label = f"Academic Source ({domain})"
        elif domain.endswith(".org") or "nhs" in domain:
            label = f"Organisation ({domain})"
        else:
            label = f"Web Source ({domain})"
    else:
        stem = re.sub(r"\.[A-Za-z0-9]+$", "", source)
        stem = re.sub(r"[_\-]+", " ", stem).strip()
        label = stem if stem else source

    if page_number is not None:
        label = f"{label} · Page {page_number}"
    return label


def partial_strength(confidence_score_value: float, validated_spans: list[dict]) -> str:
    """Grades how strong a PARTIALLY SUPPORTED finding is."""
    pass_count = sum(1 for s in validated_spans if s.get("adversarial_result") == "Pass")
    if confidence_score_value >= 0.50 and pass_count >= 1:
        return "Strong partial"
    if confidence_score_value >= 0.38:
        return "Moderate partial"
    return "Weak partial"
