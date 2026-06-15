# TRACE-AI — Confidence Scoring

This document explains exactly how TRACE-AI computes the confidence score and
how that score maps to a status. Every value reflects `config/thresholds.py` and
`core/scoring.py`. The design goal is **explainability**: a researcher should be
able to see why a finding scored what it did.

## The formula

For a theme's validated spans, a raw weighted score is computed:

```
raw = 0.40·semantic
    + 0.25·lexical
    + 0.20·consistency
    + 0.08·span_count
    + 0.07·source_diversity
```

The raw score is then calibrated and clamped to [0, 1]:

```
confidence = min(raw × 1.35, 1.0)
```

Each component is stored in the finding's `breakdown`, so the UI can show the
exact contribution of every term.

## What each component means

- **semantic (0.40)** — the average cosine similarity of the validated spans to
  the theme. The strongest signal: does the text actually match the theme?
- **lexical (0.25)** — average content-word overlap between theme and spans. A
  cross-check on semantic similarity.
- **consistency (0.20)** — directional agreement among spans. If spans disagree
  in polarity (one up, one down), consistency is penalised. Strong agreement
  across multiple spans scores highest.
- **span_count (0.08)** — a modest bonus for having more than one supporting
  span (corroboration), capped so it can't dominate.
- **source_diversity (0.07)** — a bonus when evidence is drawn from more than one
  document (cross-source corroboration). Zero for a single source.

## Why the calibration factor (×1.35)

TF-IDF semantic/lexical similarities rarely exceed ~0.7 even for excellent
matches, so the un-calibrated raw score would never reach the higher bands. The
factor stretches the realistic TF-IDF range onto the full 0–100% research scale,
so the band thresholds below are meaningful. It is a fixed, documented constant —
not a per-document tweak.

## Confidence bands → status

| Confidence | Band     | Status |
|-----------:|----------|--------|
| ≥ 0.75     | High     | VERIFIED (with a passing adversarial review) |
| ≥ 0.60     | Medium   | VERIFIED (with a passing adversarial review) |
| ≥ 0.45     | Moderate | PARTIALLY SUPPORTED |
| ≥ 0.25     | Weak     | WEAK EVIDENCE |
| < 0.25     | Very Low | BLOCKED |

Two statuses are decided outside the bands:
- **INSUFFICIENT EVIDENCE** — no candidate span cleared the retrieval floor.
- **CONFLICTING EVIDENCE** — validated spans support opposing conclusions.

A key design rule: a **Moderate** confidence (45–59%) is reported as
PARTIALLY SUPPORTED, never VERIFIED. Reading a 50%-confidence finding as
"verified" would mislead a researcher; the bands enforce honesty.

## Per-span strength badge (separate from confidence)

Confidence is per-theme. Each individual evidence span also carries a strength
badge based on its own `span_score`:

| Span score | Badge |
|-----------:|-------|
| ≥ 0.60 | 🟢 Strong Evidence |
| ≥ 0.45 | 🟡 Moderate Evidence |
| < 0.45 | 🔴 Weak Evidence |

Definitions are capped below the Strong threshold, so a definition never shows a
Strong badge.

## What the LLM does NOT touch

Confidence and status are computed entirely by deterministic code. In HYBRID
mode the LLM may only propose theme *names* — it can never assign confidence,
change a score, or override a status. This boundary is enforced in code and
covered by a test (`tests/test_verification.py`).
