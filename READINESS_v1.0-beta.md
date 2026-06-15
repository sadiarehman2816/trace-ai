# TRACE-AI v1.0-beta — Readiness Report

**Prepared by:** QA / release management (validation phase)
**Question:** Is TRACE-AI ready for external reviewers as v1.0-beta?
**Short answer:** Yes — recommended for external reviewers, with one documented
cosmetic limitation.

## Method

The deterministic core was tested against seven documents modelled on the report
styles the tool is built for (English Housing Survey, ONS, NHS workforce,
academic paper, statutory homelessness statistics, a contradictory regional
review, and a welfare-policy document). Every result was verified against actual
pipeline output, not assumed. Full per-document records are in
`testing/test_log.md`.

## Issues found, by class

### Critical (HIGH) — all fixed and covered by tests
1. Lost finding from chart-axis gluing — fixed in v0.8.2.
2. Footnote-marker (`[1]`) metadata leak — fixed.
3. Contradiction false negative (past-tense "rose" not recognised) — fixed.

All three are correctness issues. The contradiction fix is the most important
for a research-integrity tool: without it, a document that contradicted itself
could be reported as merely partially supported.

### Recurring — fixed this phase
4. Header/label gluing appeared in 4 of 7 documents. ALL-CAPS headings,
   chart-axis runs, and now standard section headers (Abstract, Results,
   Discussion, …) are all separated. Each fix is narrow and guarded against
   over-splitting normal prose.

### Cosmetic / by-design — documented, not fixed
- Mixed-case *title* lines and chart *label rows* (non-standard-header text) can
  still prepend to a span's first sentence. Cosmetic; never produces a false
  finding. A general fix is deliberately avoided because it would risk splitting
  valid prose — a worse outcome than the cosmetic issue.
- Definitions are not promoted to findings (e.g. "Universal Credit is a
  means-tested benefit…" does not surface as a VERIFIED finding). This is correct
  under "No Evidence = No Claim".

## Regression status

`python3 -m tests.run_all` → ALL TEST MODULES PASSED, before and after every fix.
New regression tests: `test_footnote_markers_stripped`,
`test_contradiction_detects_rose_vs_fell`, `test_glued_section_header_is_split`.

## Scope discipline (what was NOT changed)

No new features, no architecture changes, no module renames, no confidence-formula
changes, no HYBRID, no external APIs. All fixes were lexicon/regex-level and
backward compatible.

## Recommendation

**TRACE-AI is ready for external reviewers as v1.0-beta.**

- All critical (HIGH) and recurring issues are fixed and test-covered.
- No remaining issue produces a false finding; the residual item is cosmetic and
  documented.
- Reviewers should be told two things up front: (a) the mixed-case title/label
  cosmetic limitation, and (b) that HYBRID/LLM theme synthesis is intentionally
  out of scope for this beta (the engine runs deterministically, offline).

## Suggested framing for reviewers

> TRACE-AI v1.0-beta is a deterministic, evidence-gated document-analysis engine.
> Every finding is traceable to verified source text, with an explainable
> confidence score and a stage-by-stage audit trail. Evidence verification is
> deterministic; AI assistance, where used, does not replace the evidence rules.
> Please test with your own documents and report any case where a finding is not
> supported by the quoted evidence, or where evidence is mis-cleaned.
