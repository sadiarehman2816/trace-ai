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

---

# Validation Phase — Session 2 (QA for v1.0-beta)

Role: QA engineer / release manager. Four synthetic documents modelled on real
report styles Amin works with (academic paper, gov statistics, contradictory
regional review, welfare policy). Each run through the actual pipeline; every
claim below verified against pipeline output.

## Document: `academic.pdf` (journal-paper style)

- **What worked:** "private renters wellbeing" → PARTIALLY SUPPORTED (59%);
  statistical claim with "p < 0.05" retrieved cleanly; "social renters" →
  WEAK EVIDENCE correctly (the doc says "no significant difference").
- **What failed:** Section header "Results" glued to the first finding
  ("Results Private renters scored..."). "age effects" → INSUFFICIENT (the
  "aged 25-34" sentence wasn't retrieved for that theme phrasing).
- **Severity:** MEDIUM (header glue — cosmetic/readability); LOW (theme-phrasing
  retrieval miss).
- **Recommendation:** Header glue is the known mixed-case-heading edge case (see
  prior log) — deferred deliberately. No fix this session.

## Document: `govstats.pdf` (statutory homelessness stats)

- **What worked:** "homelessness duty" → PARTIALLY SUPPORTED with the 79,840 /
  6% statistic; "end of tenancy" and "households with children" both retrieved
  the correct sentences.
- **What failed:** **Bracketed footnote marker "[1]" leaked into evidence**
  ("...previous year [1]."). Also a chart-axis label row
  ("London South East East") glued to one finding.
- **Severity:** HIGH (metadata leak — a footnote pointer presented as content).
- **Root cause:** the metadata cleaner stripped Figure/Annex/Source/Appendix but
  had no rule for bracketed numeric citation markers `[1]`, `[12]`.
- **Fix:** added one regex in `strip_metadata_references` to remove `[\d]`
  footnote markers. Smallest possible change; no other file touched.
- **After fix:** "[1]" no longer appears in evidence; normal numbers/ranges
  ("between 10 and 20 percent") unaffected.
- **Recommendation:** Fixed; covered by `test_footnote_markers_stripped`.

## Document: `contradict.pdf` (opposing claims, same metric)

- **What worked (after fix):** "North East unemployment" → CONFLICTING EVIDENCE;
  "manufacturing output" → VERIFIED.
- **What failed (before fix):** The same metric "rose to 5.8%" vs "fell to 4.9%"
  was reported as PARTIALLY SUPPORTED instead of CONFLICTING — a **false
  negative on contradiction**, the most serious failure mode for a
  research-integrity tool (it would silently average a real disagreement).
- **Severity:** HIGH.
- **Root cause:** the polarity lexicon listed "rise/rises/rising" but **not the
  past tense "rose"** — the single most common way a report states an increase —
  so the rising span read as neutral and no contradiction was detected.
- **Fix:** added common missing directional verbs to the polarity lexicon
  (positive: rose, climbed, soared, jumped, surged, doubled; negative: dipped,
  slipped, plunged, sank, halved). Lexicon-only change; detector logic untouched.
- **After fix:** "rose vs fell" correctly flagged CONFLICTING.
- **Recommendation:** Fixed; covered by `test_contradiction_detects_rose_vs_fell`.

## Document: `policy.pdf` (welfare policy, definition-heavy)

- **What worked:** definition "Universal Credit is a means-tested benefit..."
  correctly down-weighted (not surfaced as a Strong finding); "sanctions" →
  WEAK EVIDENCE on "sanctions rose sharply".
- **What failed:** "Universal Credit" and "claimant definition" → BLOCKED (0%),
  i.e. no finding surfaced even though descriptive text exists.
- **Severity:** LOW. This is arguably **correct** behaviour: a definition is not
  a research finding under "No Evidence = No Claim". Logged for awareness, not
  fixed (fixing it would risk promoting definitions into findings — against the
  design).
- **Recommendation:** No change. Behaviour is consistent with the philosophy.

## Recurring issues identified

1. **Header / chart-label gluing on mixed-case lines** appeared in 2 of 4 docs.
   The ALL-CAPS and chart-axis cases are already handled; mixed-case titles
   remain the open edge case. Deferred (a general mixed-case splitter risks
   over-splitting real prose). Tracked as the single known limitation.
2. **Metadata-marker coverage** — footnote `[n]` was the one missing class;
   now fixed.

## Fixes applied this session (both smallest-possible, no refactor)

| Bug | Severity | File touched | Test |
|-----|----------|--------------|------|
| Footnote `[1]` leak | HIGH | core/quality_filter.py | test_footnote_markers_stripped |
| "rose" not flagged in contradiction | HIGH | core/contradiction.py | test_contradiction_detects_rose_vs_fell |

No architecture, confidence formula, module name, HYBRID, or API was changed.
Full suite: ALL TEST MODULES PASSED before and after.

## v1.0-beta readiness

- Core verification, evidence hygiene, and contradiction detection now hold up
  on realistic, messy documents.
- Two HIGH-severity correctness bugs found and fixed with minimal changes.
- One known limitation remains (mixed-case header gluing) — cosmetic, does not
  produce false findings, and is documented.
- **Recommendation: READY for v1.0-beta**, with the mixed-case header gluing
  noted as a known issue to address in a future targeted change (not a blocker).

---

# Validation Phase — Session 3 (log review + recurring-bug fix)

Role: QA / release manager. Task: review this log, classify issues as recurring,
critical, or cosmetic, and fix only recurring + critical problems.

## Classification of all issues found to date (7 documents across sessions)

**Recurring** (seen in multiple documents):
- *Header / label gluing* — appeared in 4 of 7 docs (ehs chart-axis, nhs
  ALL-CAPS, academic "Results"/"Abstract", govstats title + label row). The
  ALL-CAPS and chart-axis variants were already fixed; the **section-header
  variant** (a standard header word glued to the next sentence) was the part
  still recurring → fixed this session.

**Critical** (HIGH severity, all already fixed and tested):
- Lost finding via chart-axis gluing (v0.8.2).
- Footnote `[1]` metadata leak (session 2).
- Contradiction false negative on "rose" (session 2).

**Cosmetic / low** (no fix — logged):
- Mixed-case *title* lines and chart *label rows* (e.g. "Statutory Homelessness
  Statistics 2024 ...", "London South East East ...") can still prepend to the
  first sentence. These are not standard header words, so a safe whitelist can't
  catch them, and a general splitter would over-split real prose. They do not
  create false findings (the substantive content is retained and scored).
- "Universal Credit" / "claimant definition" → BLOCKED: arguably correct, a
  definition is not a finding.
- Occasional theme-phrasing retrieval miss (LOW).

## Fix applied this session (recurring, smallest-possible)

- **Section-header gluing** (`core/chunking.py`): `_split_glued_boundaries` now
  also separates an explicit whitelist of standard section/report headers
  (Abstract, Introduction, Background, Methods, Results, Findings, Discussion,
  Conclusion, Summary, References, Acknowledgements, Overview, Executive Summary)
  when glued to the following capitalised sentence. Restricted to the whitelist
  and to start-of-text/after-sentence positions, so normal prose beginning with
  such a word ("Results from the survey were consistent.") is never over-split.
  No other file, no architecture, no formula touched.
- Covered by `test_glued_section_header_is_split` (includes over-split guards).

## Regression status

`python3 -m tests.run_all` → ALL TEST MODULES PASSED, before and after.

## Updated readiness

All recurring and critical issues are now fixed and covered by tests. The only
remaining items are genuinely cosmetic (mixed-case title/label prepend) or
by-design (definitions not promoted to findings). No issue produces a false
finding. **Recommendation: ready for external reviewers as v1.0-beta.**
