"""
TRACE-AI — Scoring (core/scoring.py)

Deterministic span scoring (Step 4) and explainable confidence (Step 7).
Pure rule-engine code: no AI here (DO #9). All cut-points come from
config/thresholds.py (DO #3) so calibration lives in one auditable place.
"""

import re
from config.thresholds import (
    SPAN_STRONG_THRESHOLD, SPAN_WEAK_THRESHOLD,
    SPAN_WEIGHT_SEMANTIC, SPAN_WEIGHT_LEXICAL, SPAN_WEIGHT_RANK,
    CONF_WEIGHT_SEMANTIC, CONF_WEIGHT_LEXICAL, CONF_WEIGHT_CONSISTENCY,
    CONF_WEIGHT_SPAN_COUNT, CONF_WEIGHT_SOURCE_DIVERSITY,
    CONFIDENCE_CALIBRATION_FACTOR,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_MODERATE, CONFIDENCE_WEAK,
)
from core.contradiction import polarity as _polarity


# --- Step 4: weighted span score ------------------------------------------
def lexical_overlap(theme: str, span_text: str) -> float:
    """Jaccard-style content-word overlap between theme and span (0-1)."""
    stop = {
        "the", "a", "an", "of", "to", "in", "on", "and", "or", "for", "with",
        "is", "are", "this", "that", "by", "as", "at", "from",
    }
    t = {w for w in re.findall(r"[a-z]+", theme.lower()) if w not in stop and len(w) > 2}
    s = {w for w in re.findall(r"[a-z]+", span_text.lower()) if w not in stop and len(w) > 2}
    if not t or not s:
        return 0.0
    inter = t & s
    union = t | s
    return len(inter) / len(union) if union else 0.0


def span_score(semantic_similarity: float, theme: str, span_text: str,
               retrieval_rank_score: float) -> dict:
    """
    Weighted span score = w_sem*semantic + w_lex*lexical + w_rank*rank.
    Tier thresholds come from config (calibrated to the TF-IDF distribution).
    """
    lex = lexical_overlap(theme, span_text)
    final = (SPAN_WEIGHT_SEMANTIC * semantic_similarity
             + SPAN_WEIGHT_LEXICAL * lex
             + SPAN_WEIGHT_RANK * retrieval_rank_score)

    if final >= SPAN_STRONG_THRESHOLD:
        tier = "strong"
    elif final >= SPAN_WEAK_THRESHOLD:
        tier = "weak"
    else:
        tier = "discard"

    return {
        "final_score": round(final, 4),
        "tier": tier,
        "breakdown": {
            "semantic": round(semantic_similarity, 4),
            "lexical": round(lex, 4),
            "rank": round(retrieval_rank_score, 4),
        },
    }


# --- Step 7: explainable confidence ---------------------------------------
def confidence_score(validated_spans: list[dict], source_count: int = 1) -> dict:
    """
    Explainable confidence with a stored breakdown. Rewards cross-source
    corroboration (source-diversity bonus). Raw weighted sum is calibrated onto
    the research-grade 0-100% scale so config band thresholds are meaningful.

    Why a calibration factor: TF-IDF semantic/lexical rarely exceed ~0.7, so the
    raw score would never reach VERIFIED bands without stretching.
    """
    if not validated_spans:
        return {
            "score": 0.0, "band": "None",
            "breakdown": {"semantic": 0.0, "lexical": 0.0, "consistency": 0.0,
                          "span_count": 0.0, "source_diversity": 0.0},
        }

    n = len(validated_spans)
    avg_sem = sum(s["breakdown"]["semantic"] for s in validated_spans) / n
    avg_lex = sum(s["breakdown"]["lexical"] for s in validated_spans) / n

    # Consistency: directional agreement (no internal contradiction)
    polarities = [_polarity(s["text"]) for s in validated_spans]
    directional = [p for p in polarities if p != "neutral"]
    if len(set(directional)) > 1:
        consistency = 0.0
    elif len(directional) >= 2:
        consistency = 1.0
    elif len(directional) == 1:
        consistency = 0.7
    else:
        consistency = 0.4

    count_bonus = min((n - 1) * 0.25, 1.0)

    # Source-diversity bonus (gated by feature flag)
    from config.feature_flags import is_enabled
    if is_enabled("source_diversity_bonus"):
        if source_count >= 3:
            source_div = 1.0
        elif source_count == 2:
            source_div = 0.6
        else:
            source_div = 0.0
    else:
        source_div = 0.0

    sem_c = CONF_WEIGHT_SEMANTIC * avg_sem
    lex_c = CONF_WEIGHT_LEXICAL * avg_lex
    cons_c = CONF_WEIGHT_CONSISTENCY * consistency
    cnt_c = CONF_WEIGHT_SPAN_COUNT * count_bonus
    src_c = CONF_WEIGHT_SOURCE_DIVERSITY * source_div

    raw = sem_c + lex_c + cons_c + cnt_c + src_c
    score = min(raw * CONFIDENCE_CALIBRATION_FACTOR, 1.0)

    if score >= CONFIDENCE_HIGH:
        band = "High"
    elif score >= CONFIDENCE_MEDIUM:
        band = "Medium"
    elif score >= CONFIDENCE_MODERATE:
        band = "Moderate"
    elif score >= CONFIDENCE_WEAK:
        band = "Weak"
    else:
        band = "Very Low"

    return {
        "score": round(score, 4),
        "band": band,
        "breakdown": {
            "semantic": round(sem_c, 4),
            "lexical": round(lex_c, 4),
            "consistency": round(cons_c, 4),
            "span_count": round(cnt_c, 4),
            "source_diversity": round(src_c, 4),
        },
    }
