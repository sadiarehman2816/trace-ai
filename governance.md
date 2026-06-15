# TRACE-AI — Governance

This document records the principles that govern how TRACE-AI is built and
changed. It exists so that the tool's behaviour stays trustworthy over time, not
just at one moment.

## Purpose

TRACE-AI is a research-integrity platform: it analyses documents against themes
and returns only findings traceable to verified source text, with honest,
explainable confidence. It is not a chatbot or a summariser. The primary
objective is **trust, traceability, and evidence verification** — reliability
over sophistication.

## Core principles

1. **No Evidence = No Claim.** Nothing is asserted without a supporting,
   traceable span.
2. **AI may suggest; the rule engine decides.** Deterministic code makes every
   verification decision. AI never sets a status, score, or confidence.
3. **Explainability over cleverness.** Every finding ships with a confidence
   breakdown and a stage-by-stage audit trail.
4. **Honesty in labels.** A moderate-confidence finding is reported as partially
   supported, never verified.
5. **Stability before new capabilities.** The deterministic core is frozen and
   protected by tests; new work happens on branches.

## The HYBRID trust boundary

When an API key is set, the LLM is permitted to do exactly one thing: synthesise
clean, abstract theme *names* from keyword clusters. It is hard-locked out of:

- selecting which evidence supports a claim,
- assigning or modifying confidence,
- modifying span scores,
- overriding verification / adversarial review or setting status.

This boundary is enforced in `models/adversarial_review.py` (selection and
review ignore any client) and verified by `tests/test_verification.py`, which
fails if the LLM is ever reachable from verification.

## Change control

- **`main` is stable.** Never commit experimental work directly to `main`.
- **Branches per workstream** (e.g. `hybrid-themes`, `reference-checker`).
- **Thresholds live in one place** (`config/thresholds.py`). Confidence formulas
  are not changed silently — a change requires a CHANGELOG entry and a reason.
- **Tests gate changes.** `python3 -m tests.run_all` must pass before a commit.
- **Architecture and module names are stable.** Renames and refactors are avoided
  unless explicitly agreed.
- **Nothing is removed without asking.** Existing functionality is preserved
  unless its removal is explicitly approved.

## Tagged releases

Stable points are tagged (e.g. `v0.8-core-stable`, `v0.8.2`) so the project can
always return to a known-good state.

## Out of scope (for now)

No login, payments, database, user accounts, or enterprise features until
explicitly prioritised. The focus stays on the evidence-verification core.
