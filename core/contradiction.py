"""
TRACE-AI — Contradiction Detection (core/contradiction.py)

Detects when validated spans for the same theme convey opposing conclusions
(e.g. one says a metric rose, another says it fell). Pure rule-engine code.

Why this exists: a research-integrity tool must flag internal disagreement
rather than silently averaging it away — that's a CONFLICTING EVIDENCE finding.
"""

import re

# Explainable polarity lexicon. Kept deliberately simple and auditable.
POSITIVE_TERMS = {
    "increase", "increased", "increases", "increasing", "rise", "rises", "rising",
    "grew", "grow", "growth", "growing", "improved", "improve", "improvement",
    "higher", "more", "expand", "expanded", "up", "gain", "gained", "exceed",
    "exceeds", "exceeded",
}
NEGATIVE_TERMS = {
    "decrease", "decreased", "decreases", "decreasing", "fall", "falls", "fell",
    "falling", "decline", "declined", "declining", "reduced", "reduce", "reduction",
    "lower", "less", "fewer", "shrank", "shrink", "down", "drop", "dropped",
    "worsened", "worsen", "deteriorate", "stable", "stabilise", "stabilize",
    "unchanged",
}


def polarity(text: str) -> str:
    """Returns 'positive', 'negative', or 'neutral' for a span's direction."""
    words = set(re.findall(r"[a-z]+", text.lower()))
    pos = len(words & POSITIVE_TERMS)
    neg = len(words & NEGATIVE_TERMS)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def detect_contradiction(validated_spans: list[dict]) -> bool:
    """True if validated spans carry opposing polarity for the same theme."""
    polarities = {polarity(s["text"]) for s in validated_spans}
    return "positive" in polarities and "negative" in polarities
