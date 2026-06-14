# Changelog

All notable changes to TRACE-AI. This project follows a "deterministic core,
semantic features on branches" model.

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
