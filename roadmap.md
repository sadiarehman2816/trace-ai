# TRACE-AI — Roadmap

The deterministic core is stable (v0.8). Future work is semantic and
feature-level, and happens on dedicated branches — never directly on `main`.

## v0.8 — Core stable (current, frozen)

Modular architecture, deterministic verification engine, full evidence hygiene,
HYBRID trust boundary, documentation, and tests. Tagged `v0.8-core-stable`.

## v0.9 — Hybrid Themes  (branch: `hybrid-themes`)

Enable LLM theme synthesis (API key) so themes become abstract,
researcher-grade concepts ("Housing Affordability", "Tenure Differences")
instead of keyword-level entities. The verification engine stays fully
deterministic — only theme *naming* changes. This addresses the one remaining
quality gap that TF-IDF cannot close on its own.

## v1.0 — Reference Checker  (branch: `reference-checker`)

Verify citations and references in a document: detect claims attributed to
sources, check whether the cited source actually supports them, and flag
unsupported or mis-attributed citations. A natural extension of the
evidence-gated philosophy.

## v1.1 — PDF Highlighter improvements  (branch: `pdf-highlighter`)

Strengthen the source viewer: multi-span highlighting, jump-to-page,
side-by-side evidence/source view, and better handling of scanned PDFs.

## v2.0 — API  (branch: `api`)

Expose TRACE-AI as a programmatic API so other tools and pipelines can submit
documents and themes and receive verified findings + audit trails as JSON.
Enables integration into editorial and research workflows.

## Out of scope (for now)

No login system, payments, database, user accounts, or enterprise features
until explicitly prioritised. The focus stays on trust, traceability, and
evidence verification.
