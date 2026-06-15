# TRACE-AI — Evidence Pipeline

This document traces exactly what happens to a document, step by step, from
upload to a verified finding. Every value below reflects the actual code in
`config/thresholds.py` and `core/`. Golden Rule: **No Evidence = No Claim.**

## Overview

```
document(s)
  → chunking            (core/chunking.py)
  → evidence hygiene    (core/quality_filter.py)
  → indexing + retrieval(core/retrieval.py)
  → span selection      (models/adversarial_review.py — deterministic)
  → span scoring        (core/scoring.py)
  → adversarial review  (models/adversarial_review.py — deterministic)
  → contradiction scan  (core/contradiction.py)
  → confidence + status (core/scoring.py, core/verification.py)
  → finding + audit trail
```

## Step 1 — Chunking (`core/chunking.py`)

The document is read page by page. Page numbers are assigned by code, not by a
model, so a finding's page reference can never be hallucinated. Each page is
split into chunks, then into sentence spans.

Two robustness measures run here:
- **Garbage detection** skips chunks that are PDF internals or binary noise
  (scanned / malformed PDFs).
- **Glued-boundary recovery** (`_split_glued_boundaries`) separates headings and
  chart-axis lines that PDF text extraction glued onto the next sentence, so a
  real finding isn't lost inside noise.

## Step 2 — Evidence hygiene (`core/quality_filter.py`)

Each sentence span is cleaned and filtered before it can ever become evidence:

- **Metadata stripping** — inline references (Figure 1.9, Annex Table 1.6,
  Appendix B) are removed; if a reference sits at the end of a sentence with
  ≥4 words before it, the sentence is truncated there; Source:/Note:/Base:
  clauses are dropped.
- **Fragment rejection** — spans shorter than `MIN_SPAN_WORDS` (4), bare numeric
  fragments ("14 private renters"), or verbless fragments are rejected.
- **Chart / OCR noise rejection** — spans that are >40% numbers, axis-number
  runs, or repeated-percentage noise are rejected.
- **Metadata-only spans** — if cleaning leaves nothing, the span is dropped.

This is applied both at span creation and again at retrieval output, so no
metadata can reach scoring.

## Step 3 — Indexing & retrieval (`core/retrieval.py`)

All clean spans are vectorised with TF-IDF (chosen so the tool runs fully
offline). For each theme, the cosine-most-similar spans are retrieved:
`RETRIEVAL_TOP_K = 5`, above a relevance floor. If nothing clears the floor, the
theme is reported INSUFFICIENT EVIDENCE — the tool says "not addressed in the
document" rather than guessing.

## Step 4 — Hard Evidence Lock (`models/adversarial_review.select_spans`)

Selection happens ONLY from the closed candidate set returned by retrieval. The
engine cannot invent text, span IDs, or page numbers. Selection is rule-based
(keyword overlap); the LLM is never used here, even in HYBRID mode.

## Step 5 — Span scoring (`core/scoring.span_score`)

```
span_score = 0.40·semantic + 0.30·lexical + 0.30·rank
```

Tiers (from `config/thresholds.py`):
- `SPAN_STRONG_THRESHOLD = 0.55` → strong
- `SPAN_WEAK_THRESHOLD = 0.40` → weak; below → discarded

Definitions are context, not findings, so a span typed as a Definition is scored
×`DEFINITION_SCORE_FACTOR` (0.60) and hard-capped just below the "Strong" badge —
a definition can never read as Strong Evidence.

## Step 6 — Adversarial review (`models/adversarial_review.adversarial_review`)

Each surviving span faces three fixed yes/no questions:
- **Q1** — does the span directly support the theme?
- **Q2** — does the claim over-interpret the span?
- **Q3** — is the original context preserved?

The answers map deterministically to Pass / Weak / Reject. This is rule-based and
reproducible; the LLM is never used here.

## Step 7 — Contradiction scan (`core/contradiction.py`)

Validated spans are checked for opposing polarity (one says a metric rose,
another that it fell). If found → CONFLICTING EVIDENCE.

## Step 8 — Confidence & status

Confidence (`core/scoring.confidence_score`) is computed from the validated
spans (see `confidence_scoring.md` for the full formula). The rule engine
(`core/verification.final_status`) maps the result to one of six statuses. AI
never sets the status.

## Step 9 — Finding + audit trail

The finding carries: status, confidence (with breakdown), each evidence span
(with type label, strength badge, clean source label, and the Q1/Q2/Q3 result),
and a stage-by-stage audit trail so every decision can be traced end to end.

## Six statuses

🟢 VERIFIED · 🟡 PARTIALLY SUPPORTED · 🟠 WEAK EVIDENCE ·
🔍 INSUFFICIENT EVIDENCE · 🔴 BLOCKED · ⚡ CONFLICTING EVIDENCE
