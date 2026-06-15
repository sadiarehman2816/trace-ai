# Changelog

All notable changes to TRACE-AI. This project follows a "deterministic core,
semantic features on branches" model.

## v0.8.2 — Stability phase (evidence hygiene / robustness)

### Documentation
- Completed the documentation set: added `evidence_pipeline.md`,
  `confidence_scoring.md`, `governance.md`, `CONTRIBUTING.md`, `CITATION.cff`,
  and a `LICENSE`. All content derived from the actual code.
- Licence set to **Apache 2.0** (permissive, with patent grant); added `NOTICE`
  (copyright + IASRD attribution), `AUTHORS.md`, and `LEGAL_PACK.md` (IP
  ownership, governance, charity compliance, UK GDPR, and publication framework —
  authors own the IP, IASRD partner only).

### Fixed
- **PDF newline-loss sentence gluing** (`core/chunking.py`): PDF text extraction
  often drops the newline between a heading or chart-axis line and the following
  sentence, gluing them into one span. This caused a valid finding glued to a
  chart-axis run to be rejected as chart noise (HIGH severity — lost a real
  finding), and ALL-CAPS headings to pollute evidence text (MEDIUM). Added
  `_split_glued_boundaries()` to recover the sentence boundary. Smallest-possible
  change; no other module, no confidence formula, no feature affected.

### Tests
- Added `tests/test_metadata.py::test_glued_header_is_split` and
  `test_glued_chart_axis_is_split` regression tests.
- Added `testing/test_log.md` documenting the stability test session
  (per-document: what worked, what failed, severity, recommendation).

## v0.8 — Core stable (frozen)

### Architecture
- Refactored into a modular platform: `config/`, `core/`, `inputs/`, `models/`,
  `outputs/`, `ui/`, `tests/`.
- Centralised all thresholds in `config/thresholds.py` (no hardcoded values).
- Feature flags in `config/feature_flags.py`.
- AI components isolated from the deterministic engine.
- HYBRID trust boundary: the LLM is permitted only for theme synthesis and can
  never select evidence, score, review, or set status.

### Evidence hygiene
- Metadata cleaning: strips inline references (Figure 1.9, Annex Table 1.6),
  truncates at the first metadata marker when content precedes it, and drops
  Source:/Note:/Base: clauses.
- Chart / OCR noise filter: rejects number-heavy, axis-like, or verbless spans.
- Definition filter: definitions are detected, down-weighted (×0.60), and capped
  below "Strong Evidence".
- Fragment + broad-noun rejection: bare fragments ("14 private renters") and
  single broad nouns ("Households") are rejected.

### Verification
- Six-status system with explainable confidence and a stage-by-stage audit
  trail. Moderate confidence reads as PARTIALLY SUPPORTED, never VERIFIED.

### Documentation & tests
- Added README features section, `architecture.md`, `roadmap.md`, `CHANGELOG.md`.
- Docstrings on every source function.
- Dedicated test modules: `test_metadata.py`, `test_chart_noise.py`,
  `test_definition_filter.py`, `test_verification.py`, plus `test_smoke.py` and
  a `run_all.py` runner. Coverage: metadata cleaning, chart/definition filters,
  broad-noun rejection, the verification engine, and the HYBRID trust boundary.

## Earlier (pre-v0.8)

- Initial evidence-gated pipeline, multi-format input, theme discovery,
  evidence strength badges, PDF highlight viewer, and JSON/Excel/Word exports.
