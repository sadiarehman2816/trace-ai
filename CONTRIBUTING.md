# Contributing to TRACE-AI

Thank you for considering a contribution. TRACE-AI is a research-integrity tool,
so contributions are held to one overriding standard: **they must not weaken the
trustworthiness of the engine.** Golden Rule: No Evidence = No Claim.

## Before you start

- Read `governance.md` (principles + the HYBRID trust boundary) and
  `architecture.md` (how the engine fits together).
- Open an issue describing the change before large work, so it can be discussed.

## Branching

- `main` is stable — never commit directly to it.
- Branch from `main` for every change:
  `git checkout main && git pull && git checkout -b my-change`
- Keep one branch per workstream (e.g. `hybrid-themes`, `reference-checker`).

## The rules that protect trust

1. **AI never decides.** Do not route evidence selection, scoring, confidence, or
   status through an LLM. The HYBRID boundary (theme naming only) is enforced in
   code and by tests — do not loosen it.
2. **No silent formula changes.** Confidence weights and thresholds live in
   `config/thresholds.py`. Any change there needs a CHANGELOG entry and a clear
   reason in the PR.
3. **Preserve behaviour.** Don't remove existing functionality without agreement.
   Keep backward compatibility.
4. **Smallest possible change.** Fix the issue without unrelated refactoring or
   module renames.
5. **Document honestly.** Never describe a feature in the docs that does not
   already exist in the code.

## Tests are required

- Run the full suite before committing:
  `python3 -m tests.run_all` → must print `ALL TEST MODULES PASSED`.
- Add a regression test for any bug you fix (see `tests/test_metadata.py` for the
  pattern).
- If you touch the engine, also test against a real document and record the
  result in `testing/test_log.md` (document, what worked, what failed, severity,
  recommendation).

## Commit messages

- Use a short, descriptive summary, e.g.
  `Stability: recover sentence boundaries lost in PDF extraction`.

## Pull request checklist

- [ ] Branched from `main`, not committing to `main` directly.
- [ ] `python3 -m tests.run_all` passes.
- [ ] New behaviour covered by a test.
- [ ] No change to confidence formulas/thresholds without a CHANGELOG note.
- [ ] HYBRID trust boundary untouched.
- [ ] Docs updated only with features that actually exist.

## Reporting issues

When filing a bug, include: the document type (PDF/DOCX/CSV/URL), the theme used,
what status/evidence you expected, what you got, and (if possible) a small sample
that reproduces it.
