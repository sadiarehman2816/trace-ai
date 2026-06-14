# TRACE-AI — Architecture

This document describes how TRACE-AI turns a document into verified findings.
The guiding principle throughout: **AI may suggest; the rule engine decides.**

## Module map

```
config/   thresholds.py        single source of truth for every tunable number
          feature_flags.py     on/off switches incl. the HYBRID trust boundary
core/     chunking.py          PDF -> pages -> chunks -> sentence spans
          retrieval.py         TF-IDF index + Top-K grounded retrieval
          quality_filter.py    metadata stripping, noise/fragment rejection, typing
          scoring.py           weighted span score + explainable confidence
          contradiction.py     polarity + contradiction scan
          verification.py      THE RULE ENGINE — final status + audit trail
          theme_engine.py      deterministic theme discovery (keyword clusters)
          pipeline.py          orchestrator (coordinates; holds no rules)
inputs/   per-format loaders + dispatcher
models/   adversarial_review.py (AI-capable), theme_synthesis.py (LLM, HYBRID)
outputs/  json / xlsx / docx exports + pdf_highlight viewer
ui/       Streamlit render components (no business logic)
```

## Retrieval flow

1. **Chunking** (`core/chunking.py`)
   PDF is read page by page (code-assigned page numbers — no AI, so no
   hallucinated pages). Each page is split into chunks, then into sentence
   spans. Every span is cleaned of metadata references at creation.

2. **Indexing** (`core/retrieval.py`)
   All spans are vectorised with TF-IDF. (TF-IDF is used instead of transformer
   embeddings so the tool runs fully offline; `retrieve_top_k` is the seam where
   a transformer backend could later be swapped in.)

3. **Top-K retrieval**
   For each theme, the cosine-most-similar spans are retrieved (default K = 5),
   above a relevance floor. If nothing clears the floor, the theme is reported
   as INSUFFICIENT EVIDENCE — the tool says "not addressed" rather than guessing.

4. **Evidence hygiene at output**
   Each retrieved span is cleaned (sentence-split, metadata truncated, Source:/
   Note: dropped) and then re-checked. Metadata pointers, chart/OCR noise,
   fragments, and bare broad nouns are rejected before scoring.

## Verification layers

A retrieved span passes through these deterministic layers in order:

1. **Hard Evidence Lock** (`models/adversarial_review.select_spans`)
   Selection is made ONLY from the closed candidate set — the engine cannot
   invent text, IDs, or pages. (Selection is rule-based; the LLM is never used
   here, even in HYBRID mode.)

2. **Weighted span score** (`core/scoring.span_score`)
   `score = 0.40·semantic + 0.30·lexical + 0.30·rank`, then tiered
   strong / weak / discard against config thresholds. Definitions are
   down-weighted (×0.60) and capped below the "Strong" badge.

3. **Adversarial review** (`models/adversarial_review.adversarial_review`)
   Three fixed yes/no questions — Q1 direct support, Q2 over-interpretation,
   Q3 context preserved — mapped deterministically to Pass / Weak / Reject.
   (Rule-based; the LLM is never used here.)

4. **Contradiction scan** (`core/contradiction.py`)
   Validated spans are checked for opposing polarity (one says a metric rose,
   another that it fell) → CONFLICTING EVIDENCE.

5. **Final status** (`core/verification.final_status`)
   The rule engine maps the full state to one of six statuses. AI never sets
   status. A Moderate confidence band is PARTIALLY SUPPORTED, never VERIFIED.

6. **Audit trail** (`core/verification.build_audit_trail`)
   Every stage records a pass/fail with a human-readable reason, so any decision
   can be traced end to end.

## Confidence system

`core/scoring.confidence_score` produces an explainable score with a stored
breakdown:

```
confidence = 0.40·semantic + 0.25·lexical + 0.20·consistency
           + 0.08·span_count + 0.07·source_diversity     (then calibrated ×1.35)
```

- **semantic / lexical** — average match quality of validated spans.
- **consistency** — directional agreement (penalised if spans disagree).
- **span_count** — modest bonus for corroborating spans.
- **source_diversity** — bonus when evidence spans multiple documents.
- **calibration factor** — stretches the TF-IDF range onto the research-grade
  0–100% scale so the band thresholds are meaningful.

Bands → statuses:

| Confidence band | Status                |
|-----------------|-----------------------|
| High / Medium (≥60%) + passing review | VERIFIED |
| Moderate (45–59%) | PARTIALLY SUPPORTED |
| Weak (25–44%)     | WEAK EVIDENCE       |
| Very Low (<25%)   | BLOCKED             |
| no candidates     | INSUFFICIENT EVIDENCE |
| opposing polarity | CONFLICTING EVIDENCE |

## HYBRID trust boundary

In HYBRID mode (API key set), the LLM is permitted to do exactly one thing:
synthesise clean, abstract theme names from keyword clusters
(`models/theme_synthesis.py`). It can NEVER select evidence, score, run
adversarial review, set confidence, or override verification — these are
hard-locked to deterministic code and protected by a smoke test.
