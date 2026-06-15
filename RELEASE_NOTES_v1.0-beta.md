# TRACE-AI v1.0-beta — Release Notes

**Status:** Pre-release (External Reviewer / Research Beta), following the
validation phase. This is **not** a final or "stable v1.0" version — it exists to
gather external review before v1.0 proper.
**Philosophy:** No Evidence = No Claim.

**Suggested GitHub Release title:** *TRACE-AI v1.0-beta — External Review Release*

## What this release is

TRACE-AI v1.0-beta is the first beta of the evidence-gated research-integrity
engine after a dedicated validation phase. No new features were added in this
phase. The focus was stability, real-document testing, and fixing correctness
bugs with the smallest possible changes.

## Fixed in this release

- **Footnote-marker leak (HIGH).** Bracketed numeric citation markers such as
  `[1]` and `[12]` are now stripped from evidence text. Previously a footnote
  pointer could appear inside a finding.
- **Contradiction false negative (HIGH).** The contradiction detector now
  recognises the past tense "rose" (and other common directional verbs), so a
  document that says a metric "rose to 5.8%" in one place and "fell to 4.9%" in
  another is correctly flagged as CONFLICTING EVIDENCE rather than silently
  reported as partially supported.
- **Section-header gluing (recurring).** Standard section headers (Abstract,
  Results, Discussion, Conclusion, etc.) glued to the following sentence by PDF
  newline loss are now separated, without over-splitting normal prose.

Both fixes are lexicon/regex-level changes. No architecture, confidence formula,
module name, HYBRID behaviour, or API was changed. Backward compatibility is
preserved.

## Validation summary

Four documents modelled on real report styles (academic paper, government
statistics, a contradictory regional review, and a welfare-policy document) were
run through the actual pipeline. Results, failures, severities, and
recommendations are recorded in `testing/test_log.md`.

Outcome: evidence hygiene, verification, and contradiction detection hold up on
realistic, messy input. Definitions are correctly down-weighted and not promoted
to findings.

## Known limitation

- **Mixed-case title / chart-label gluing.** When PDF text extraction drops the
  newline after a mixed-case title or a chart-label row (non-standard-header
  text), that text can prepend to the first sentence of a span. ALL-CAPS
  headings, chart-axis number runs, and standard section headers are all
  separated; this residual case remains. It is cosmetic, does not produce false
  findings, and a general fix is deferred because an over-aggressive splitter
  would risk breaking valid prose.

## Tests

`python3 -m tests.run_all` → ALL TEST MODULES PASSED. Three new regression tests
cover the fixes above.

## Readiness recommendation

**Recommended: ready for external reviewers as v1.0-beta.** All critical (HIGH)
and recurring issues found during validation are fixed and test-covered. The one
remaining known issue is cosmetic and documented. See `READINESS_v1.0-beta.md`
for the full assessment and suggested reviewer framing.

The next phase (HYBRID themes, API, etc.) remains out of scope and on separate
branches, per the project's governance.

## Release assets

- **Screenshots:** `docs/screenshots/` (captured from the running app).
- **Demo video:** `docs/demo/trace-ai-demo.mp4` (or an external link).
- **Archive + DOI (optional):** a Zenodo archive and citable DOI can be minted
  by enabling Zenodo for the repository and publishing this release. See
  `RELEASE_GUIDE_v1.0-beta.md` for step-by-step instructions.
