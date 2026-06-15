# TRACE-AI v1.0-beta — External Review Release Guide

> **This is a pre-release, not a final version.** Refer to it as the
> *External Reviewer Release* / *Validation (Research) Beta* — not "final" or
> "stable v1.0". Its purpose is to gather external review before a v1.0 proper.

A step-by-step guide to publishing the v1.0-beta release. Items marked **[you]**
must be done by a person with the running app / accounts — they cannot be
generated automatically, because they involve real screenshots, a real screen
recording, and your own GitHub/Zenodo accounts.

Status check before releasing: `python3 -m tests.run_all` must print
`ALL TEST MODULES PASSED`, and `READINESS_v1.0-beta.md` should recommend release.

---

## 1. Tag and GitHub Release

If not already tagged:

```
git tag -a v1.0-beta -m "v1.0-beta: validated, ready for external reviewers"
git push origin v1.0-beta
```

Then on GitHub:
1. Repo → **Releases** → **Draft a new release**.
2. Choose the tag `v1.0-beta`.
3. Title: `TRACE-AI v1.0-beta — External Review Release`.
4. Description: paste the contents of `RELEASE_NOTES_v1.0-beta.md`.
5. Tick **"This is a pre-release"** (it's a beta).
6. Attach the screenshots and demo video (sections 2–3) if you have them.
7. Publish.

---

## 2. Screenshots **[you]**

Run the app and capture real screens (do not fake these):

```
streamlit run app.py
```

Capture (save into `docs/screenshots/`):
- **01_upload.png** — the upload screen with a document selected.
- **02_themes.png** — discovered/entered themes.
- **03_verified.png** — a VERIFIED finding showing evidence + confidence.
- **04_audit_trail.png** — a finding's expanded audit trail (the stage-by-stage
  reasoning).
- **05_conflicting.png** — a CONFLICTING EVIDENCE example (if available). Use a
  document with opposing claims, e.g. "rose to 5.8%" vs "fell to 4.9%".
- **06_pdf_highlight.png** — the PDF viewer with an evidence span highlighted.

Tip: use a real public report (e.g. an English Housing Survey PDF) so the
screenshots are representative.

---

## 3. Demo video **[you]**

A 60–90 second screen recording (QuickTime on Mac: File → New Screen Recording).
Suggested flow:

1. (0–10s) Upload a document; show themes appearing.
2. (10–30s) Open a VERIFIED finding; point out the quoted evidence and the
   confidence score.
3. (30–45s) Expand the audit trail — emphasise that evidence verification is
   deterministic, and AI assistance, where used, does not replace the evidence
   rules.
4. (45–60s) Show a CONFLICTING EVIDENCE finding — the tool flags disagreement
   rather than averaging it.
5. (60–75s) Click an evidence span to show it highlighted on the source page.
6. (75–90s) Close on the Golden Rule: "No Evidence = No Claim."

Save as `docs/demo/trace-ai-demo.mp4` and/or upload to YouTube/Loom and link it
in the release notes and README.

---

## 4. Zenodo archive + DOI **[you, optional but recommended]**

Zenodo gives the release a permanent archive and a citable DOI.

1. Go to https://zenodo.org and sign in with GitHub.
2. **Settings → GitHub** → find `sadiarehman2816/trace-ai` → toggle it **ON**.
3. Back on GitHub, publish (or re-publish) the `v1.0-beta` release.
   Zenodo automatically archives it and mints a DOI.
4. Copy the DOI badge/markdown from Zenodo into the README (top) and update
   `CITATION.cff` — set both the version and the DOI, e.g.:

   ```
   version: v1.0-beta
   doi: 10.xxxx/zenodo.xxxxx
   ```

Note: Zenodo issues a version DOI for each release plus a "concept DOI" that
always points to the latest — cite the concept DOI in papers.

---

## 5. After release

- Update README with the DOI badge and a link to the demo video.
- Tell external reviewers the two caveats from `READINESS_v1.0-beta.md`:
  the mixed-case title/label cosmetic limitation, and that HYBRID/LLM theme
  synthesis is intentionally out of scope for this beta.
- Keep new work on branches (`hybrid-themes`, etc.) — `main` stays releasable.

---

## Recommended release order

1. `python3 -m tests.run_all` (must pass)
2. `git tag -a v1.0-beta -m "v1.0-beta"` then `git push origin v1.0-beta`
3. GitHub Release — marked **Pre-release**
4. Share with external reviewers
5. Zenodo DOI (optional)
6. README DOI badge (optional)
7. Continue HYBRID and other work on separate branches; `main` stays releasable

## Checklist

- [ ] `tests.run_all` passes
- [ ] `v1.0-beta` tag pushed
- [ ] GitHub Release drafted with release notes, marked pre-release
- [ ] Screenshots captured into `docs/screenshots/`
- [ ] Demo video recorded into `docs/demo/` (or linked)
- [ ] Release published
- [ ] (optional) Zenodo enabled and DOI minted
- [ ] (optional) README updated with DOI badge + demo link
