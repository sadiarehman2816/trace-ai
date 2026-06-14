# TRACE-AI — Trustworthy Research Analysis and Citation Engine

**Golden Rule: No Evidence = No Claim.**

TRACE-AI is a research-integrity platform, not a chatbot and not a summarisation
tool. It analyses research documents against themes and returns only findings
traceable to verified source text, with honest, explainable confidence labels.
The primary objective is trust, traceability, and evidence verification —
reliability over sophistication.

## Features

- **Evidence-gated findings** — every claim is traceable to a verified source
  span; nothing is asserted without supporting text.
- **Multi-format input** — PDF, Word (.docx), text, CSV, Excel, and web URLs,
  with multiple documents pooled into one combined evidence set.
- **Automatic theme discovery** — themes emerge from the document(s); manual
  themes are also supported.
- **Deterministic verification engine** — retrieval, scoring, adversarial
  review, contradiction scan, confidence, and status are all rule-based and
  reproducible. AI never decides a status.
- **Evidence hygiene** — metadata references (Figure 1.9, Annex Table 1.6,
  Source:/Note:) are stripped; chart/OCR noise, fragments, and bare broad nouns
  are rejected; definitions are down-weighted and capped below "Strong".
- **Six-status system** with explainable confidence and a stage-by-stage audit
  trail for every finding.
- **Evidence type labels** — Statistical / Trend / Definition / Policy /
  Limitation / Quote.
- **PDF highlight viewer** — click any finding to see the exact quote
  highlighted on its source page.
- **Exports** — JSON, Excel, and Word (with audit trails).
- **HYBRID trust boundary** — the LLM is permitted only for theme-name
  synthesis; it can never select evidence, score, or set status.

## Run it

```
cd trace_ai
pip3 install -r requirements.txt
streamlit run app.py
```

Opens at http://localhost:8501. Upload a PDF / Word / CSV / Excel file or paste
URLs, choose auto-discovered or manual themes, and click Analyse.

### HYBRID mode (recommended for best theme quality)

By default TRACE-AI runs **fully deterministic** (MOCK). Setting an API key
enables **HYBRID mode**: the LLM is used for **one thing only** — turning raw
keyword clusters into clean, abstract, researcher-friendly theme names (and
renaming/merging themes). Everything else stays deterministic.

```
export ANTHROPIC_API_KEY=sk-ant-...
streamlit run app.py
```

**Trust boundary (hard-locked in code):**

The LLM may ONLY:
- generate abstract themes from the document
- rename or merge existing themes

The LLM must NEVER (and cannot, even if a client is passed):
- select which evidence supports a claim
- assign or modify confidence
- modify span scores
- override verification results / adversarial review

This boundary is enforced in `models/adversarial_review.py` (selection and
review ignore any client) and verified by `tests/test_smoke.py`
(`test_hybrid_boundary`), which fails if the LLM is ever reachable from
verification.

## Architecture (modular platform)

```
trace_ai/
  app.py                 thin Streamlit entry — UI only, no business logic
  config/
    thresholds.py        ALL tuning numbers (single source of truth)
    feature_flags.py     toggle every optional/premium capability
  core/                  deterministic engine (no AI here)
    chunking.py          PDF -> pages -> chunks -> sentence spans
    retrieval.py         TF-IDF index + Top-K grounded retrieval
    quality_filter.py    metadata/fragment rejection + evidence typing
    scoring.py           weighted span score + explainable confidence
    contradiction.py     polarity + contradiction scan
    verification.py      THE RULE ENGINE — decides final status + audit trail
    theme_engine.py      deterministic theme discovery (TF-IDF clusters)
    pipeline.py          orchestrator (coordinates; holds no rules)
  inputs/                one loader per format + dispatcher
  models/                AI-only, isolated (DO #9)
    adversarial_review.py  Claude: span selection + 3-question audit
    theme_synthesis.py     Claude: clean research-theme names (LIVE)
  outputs/               json / xlsx / docx exports + pdf_highlight viewer
  ui/                    Streamlit render components
  tests/
```

### Design principles enforced

- Business logic never lives in UI files; AI is isolated from the rule engine.
- AI may **suggest** (span choice, theme phrasing); the **rule engine decides**
  the final status. AI never assigns status directly.
- All thresholds live in `config/thresholds.py`; nothing is hardcoded elsewhere.
- Every capability is a single-responsibility module; features are flag-gated.
- Audit trails and the confidence formula are preserved and fully explainable.

## Status system

🟢 VERIFIED · 🟡 PARTIALLY SUPPORTED · 🟠 WEAK EVIDENCE ·
🔍 INSUFFICIENT EVIDENCE · 🔴 BLOCKED · ⚡ CONFLICTING EVIDENCE

## Evidence types

📊 Statistical finding · 📈 Trend · 📜 Definition (down-weighted) ·
📄 Policy statement · ⚠️ Limitation · 🗣️ Interview quote

## Documentation

- `architecture.md` — retrieval flow, verification layers, confidence system
- `roadmap.md` — version roadmap (v0.9 Hybrid Themes → v2.0 API)
- `CHANGELOG.md` — version history
- `GITHUB_SETUP.md` — repo setup and branching guide

## Tests

Research tools live or die on trust, so the engine is covered by tests:

```
python3 -m tests.run_all              # run everything
python3 -m tests.test_metadata        # metadata cleaning
python3 -m tests.test_chart_noise     # chart / OCR noise rejection
python3 -m tests.test_definition_filter  # definition detection + cap
python3 -m tests.test_verification    # rule engine + HYBRID trust boundary
```
