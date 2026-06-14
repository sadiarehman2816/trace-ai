# TRACE-AI — Test Log (Stability Phase)

Philosophy: **No Evidence = No Claim.** Goal: stability before new capabilities.
Scope of changes in this phase: evidence hygiene / robustness only. No new
features, no architecture changes, no HYBRID, no external APIs.

Every claim below was verified by running the actual pipeline on the document.

---

## Test session — synthetic government-report documents

Three documents were generated to mimic the formatting of real reports Amin
works with (English Housing Survey, ONS, NHS workforce): mixed headers,
footnotes, inline figure/table references, chart-axis text, definitions, and
Source:/Note: lines.

### Document: `ehs_report.pdf` (English Housing Survey style)

- **What worked:**
  - "Social renters arrears" → VERIFIED (64%), clean evidence, inline
    "(Figure 1.9 and Annex Table 1.6)" correctly stripped.
  - Definition ("Housing support is a means-tested benefit…") correctly
    down-weighted / not surfaced as Strong.
  - No metadata leaked into any evidence span.
- **What failed (before fix):**
  - "First time buyers" → INSUFFICIENT EVIDENCE, even though the document
    clearly states "first time buyers increased to 761,000".
- **Severity:** HIGH (a real, clearly-stated finding was lost).
- **Root cause:** PDF text extraction dropped the newline between a chart-axis
  line ("0 10 20 30 … social rented") and the following sentence, gluing them.
  The glued span was then (correctly) rejected as chart/OCR noise — taking the
  valid finding down with it.
- **Fix:** `_split_glued_boundaries()` in `core/chunking.py` inserts a sentence
  boundary after a chart-axis number run (and after ALL-CAPS headings) so the
  finding is separated from the noise. Smallest-possible change; no other file
  touched.
- **After fix:** "First time buyers" → VERIFIED (64%) with clean evidence.
- **Recommendation:** Fixed and covered by a regression test
  (`test_glued_chart_axis_is_split`).

### Document: `ons_report.pdf` (ONS Cost of Living style)

- **What worked:**
  - "Household income" → PARTIALLY SUPPORTED (53%): "Real household disposable
    income fell by 1.3% in 2024." — "see Table 3.2" stripped correctly.
  - "Energy bills" → PARTIALLY SUPPORTED (53%), clean.
  - Definition of "household" correctly handled.
  - No metadata leaks.
- **What failed:** Nothing material.
- **Severity:** LOW.
- **Recommendation:** No change needed.

### Document: `nhs_report.pdf` (NHS workforce style)

- **What worked:**
  - "Burnout" → WEAK EVIDENCE (31%): "Burnout was cited by 43% of respondents…"
  - "See Appendix C…" reference correctly stripped.
  - No metadata leaks.
- **What failed (before fix):**
  - The ALL-CAPS heading "NHS WORKFORCE STATISTICS" was glued to the first
    finding ("Staff vacancies rose."), polluting the evidence text.
- **Severity:** MEDIUM (evidence readability; could mislead a reader about what
  the source span actually says).
- **Root cause:** Same PDF newline-loss issue — an ALL-CAPS heading with no
  terminal punctuation glued to the next sentence.
- **Fix:** Same `_split_glued_boundaries()` change (ALL-CAPS-heading branch).
- **After fix:** Heading is its own span; "Staff vacancies rose." stands alone
  (and, being only 3 words, is filtered as too-thin — acceptable; the
  substantive "The vacancy rate reached 9.2% in Q4." is retained).
- **Recommendation:** Fixed and covered by a regression test
  (`test_glued_header_is_split`).

---

## Known remaining edge case (not yet fixed — logged, low risk)

- **Mixed-case document titles** (e.g. "English Housing Survey 2024-25 Headline
  Report Chapter 1: Tenure trends") can still glue to the first body sentence
  when there is no terminal punctuation and the title is not ALL-CAPS.
- **Severity:** LOW–MEDIUM. It only affects the very first span of a document,
  and the substantive content is still present and correctly scored; the title
  text is just prepended.
- **Why not fixed now:** A general mixed-case heading splitter risks
  over-splitting normal prose (false positives), which would be worse than the
  cosmetic issue it solves. Deferred deliberately until a safe heuristic is
  found. Recorded here rather than silently changed.

---

## Regression status

- Full suite (`python3 -m tests.run_all`): ALL TEST MODULES PASSED, before and
  after the fix.
- Two new regression tests added in `tests/test_metadata.py`:
  `test_glued_header_is_split`, `test_glued_chart_axis_is_split`.

## Summary

| Document        | Result      | Highest severity issue | Status |
|-----------------|-------------|------------------------|--------|
| ehs_report.pdf  | pass (fixed)| HIGH (lost finding)    | Fixed  |
| ons_report.pdf  | pass        | LOW                    | OK     |
| nhs_report.pdf  | pass (fixed)| MEDIUM (header glue)   | Fixed  |

Net change this phase: one targeted robustness fix in `core/chunking.py`
(sentence-boundary recovery for PDF newline loss), plus two regression tests.
No architecture, confidence formula, module name, or feature was changed.
