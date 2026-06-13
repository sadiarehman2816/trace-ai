"""
TRACE-AI — Centralised Thresholds (config/thresholds.py)

SINGLE SOURCE OF TRUTH for every tunable number in the system. No threshold
should be hardcoded anywhere else in the codebase (DO #3, DON'T #2).

Why centralised: thresholds are calibration decisions that affect trust and
must be auditable and adjustable in one place. When the embedding backend
changes (e.g. TF-IDF -> transformer), only this file needs re-tuning.
"""

# --- Span score tiers (Step 4: weighted span score) ------------------------
# Calibrated to the current TF-IDF scoring distribution. Genuine top matches
# score ~0.55-0.75; off-topic spans ~0.20-0.40.
SPAN_STRONG_THRESHOLD = 0.55   # >= this -> strong evidence
SPAN_WEAK_THRESHOLD = 0.40     # >= this -> weak; below -> discarded

# Weighted span-score component weights (must sum to 1.0)
SPAN_WEIGHT_SEMANTIC = 0.40
SPAN_WEIGHT_LEXICAL = 0.30
SPAN_WEIGHT_RANK = 0.30

# --- Confidence bands (Step 7) — research-grade scale -----------------------
# Why these cut-points: a finding below 60% should NOT read as "VERIFIED" to a
# researcher. 44%-VERIFIED was a credibility bug; these bands fix it.
CONFIDENCE_HIGH = 0.75      # VERIFIED (High)
CONFIDENCE_MEDIUM = 0.60    # VERIFIED (Medium)
CONFIDENCE_MODERATE = 0.45  # PARTIALLY SUPPORTED
CONFIDENCE_WEAK = 0.25      # WEAK EVIDENCE; below -> BLOCKED

# Confidence component weights
CONF_WEIGHT_SEMANTIC = 0.40
CONF_WEIGHT_LEXICAL = 0.25
CONF_WEIGHT_CONSISTENCY = 0.20
CONF_WEIGHT_SPAN_COUNT = 0.08
CONF_WEIGHT_SOURCE_DIVERSITY = 0.07

# Calibration stretch: TF-IDF semantic/lexical rarely exceed ~0.7, so the raw
# weighted score is stretched onto the full 0-1 research scale.
CONFIDENCE_CALIBRATION_FACTOR = 1.35

# --- Evidence strength badge cut-points (per-span) --------------------------
STRENGTH_STRONG = 0.60     # green
STRENGTH_MODERATE = 0.45   # amber; below -> red (weak)

# --- Retrieval ------------------------------------------------------------
RETRIEVAL_TOP_K = 5
RETRIEVAL_MIN_SCORE = 0.05  # below this cosine score -> not a candidate

# --- Evidence quality filter ----------------------------------------------
MIN_SPAN_WORDS = 4          # spans shorter than this are rejected as fragments.
                            # 4 keeps valid short findings ("Affordability
                            # worsened in London") while cutting "14 private
                            # renters" (3 words). The verb + numeric-fragment
                            # checks catch most fragments regardless of length.

# --- Definition down-weighting --------------------------------------------
# Definitions carry less analytical value than findings, so their span score is
# multiplied by this factor (AI may suggest type; the rule engine applies it).
DEFINITION_SCORE_FACTOR = 0.60  # definitions are context, not findings — score
                                # heavily down-weighted and capped below "Strong"

# --- Theme discovery ------------------------------------------------------
THEME_TOP_N_RAW = 12        # raw candidates before synthesis
THEME_FINAL_COUNT = 6       # themes shortlisted
THEME_MERGE_THRESHOLD = 0.45  # Jaccard overlap to merge near-duplicate themes
