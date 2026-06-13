# TRACE-AI — Trustworthy Research Analysis and Citation Engine

**Golden Rule: No Evidence = No Claim.**

TRACE-AI is a research-integrity platform, not a chatbot and not a summarisation
tool. It analyses research documents against themes and returns only findings
traceable to verified source text, with honest, explainable confidence labels.
The primary objective is trust, traceability, and evidence verification —
reliability over sophistication.

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
