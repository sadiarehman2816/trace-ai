"""tests/test_external_verification.py — fully offline; providers monkeypatched.

Run: python tests/test_external_verification.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from verification import citation_matcher, external_verifier, reference_extractor, reference_normalizer
from verification import verification_report
from verification.models import ExternalRecord

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

APA_DOC = """
Introduction

Care quality has been widely studied (Smith, 2020). Johnson and Lee (2019)
found significant improvements. Recent work (Brown et al., 2021; Smith, 2020)
confirms this. Taylor (2023b) extended the model. Unlisted work (Ghost, 2015)
is also cited. Figure 1 shows the trend. Table 1 and Table 2 summarise results.

References

Smith, J. (2020). Care quality in residential settings. Journal of Social
Care, 12(3), 45-67. https://doi.org/10.1234/jsc.2020.001

Johnson, A., & Lee, B. (2019). Improving outcomes in adult social care.
Health Economics Review, 8(1), 21-30.

Brown, C., Davis, D., & Evans, E. (2021). Machine learning for care planning.
Journal of Social Care, 12(3), 45-67.

Taylor, F. (2023). Extended care models. Care Research Quarterly, 5(2), 10-19.

Wilson, G. (2018). An uncited monograph on care ethics. Oxford University Press.

Appendix A

Extra material here.
"""

NUMBERED_DOC = """
Body text cites [1] and [2-3] and also [5].

References

[1] Smith, J. (2020). First numbered work. Journal A, 1(1), 1-10.
[2] Jones, K. (2019). Second numbered work. Journal B, 2(2), 11-20.
[3] Lee, M. (2021). Third numbered work. Journal C, 3(3), 21-30.
"""


# ---------------------------------------------------------------------------
# 1. Extraction
# ---------------------------------------------------------------------------

print("== Extraction ==")
refs_raw, intext, stats = reference_extractor.extract(APA_DOC)
check("APA: 5 references segmented", len(refs_raw) == 5, f"got {len(refs_raw)}")
check("APA: journal-tail guard (Johnson entry stays whole)",
      any("Health Economics Review" in r and "Johnson" in r for r in refs_raw))
check("APA: appendix trimmed", not any("Extra material" in r for r in refs_raw))
check("APA: in-text found Smith 2020",
      any(c.get("author", "").startswith("Smith") and c.get("year") == "2020" for c in intext))
check("APA: narrative Johnson and Lee (2019) found",
      any("Johnson" in c.get("author", "") and c.get("year") == "2019" for c in intext))
check("APA: suffix year 2023b captured",
      any(c.get("year") == "2023b" for c in intext))
check("APA: stats figures=1 tables=2", stats.figures == 1 and stats.tables == 2,
      f"fig={stats.figures} tab={stats.tables}")

n_raw, n_intext, _ = reference_extractor.extract(NUMBERED_DOC)
check("Numbered: 3 references segmented", len(n_raw) == 3, f"got {len(n_raw)}")
check("Numbered: [2-3] expanded", any(c.get("number") == 3 for c in n_intext))
check("Numbered: overshoot [5] captured", any(c.get("number") == 5 for c in n_intext))

# ---------------------------------------------------------------------------
# 2. Normalization
# ---------------------------------------------------------------------------

print("== Normalization ==")
refs = reference_normalizer.normalize_all(refs_raw)
smith = refs[0]
check("Smith: author parsed", smith.authors and smith.authors[0].startswith("Smith"))
check("Smith: year 2020", smith.year == 2020)
check("Smith: title parsed", smith.title == "Care quality in residential settings",
      f"got {smith.title!r}")
check("Smith: journal parsed (lstrip-punctuation fix)",
      smith.journal == "Journal of Social Care", f"got {smith.journal!r}")
check("Smith: DOI parsed", smith.doi == "10.1234/jsc.2020.001", f"got {smith.doi!r}")
check("Smith: vol/issue/pages", smith.volume == "12" and smith.issue == "3" and smith.pages == "45-67")
wilson = refs[4]
check("Wilson: book type guessed", wilson.type_guess == "book", f"got {wilson.type_guess}")
n_refs = reference_normalizer.normalize_all(n_raw)
check("Numbered: ref_number parsed", n_refs[0].ref_number == 1 and n_refs[2].ref_number == 3)

# ---------------------------------------------------------------------------
# 3. Consistency
# ---------------------------------------------------------------------------

print("== Consistency ==")
cons = citation_matcher.check_consistency(refs, intext)
check("Ghost (2015) → cited_not_listed",
      any("Ghost" in c for c in cons.cited_not_listed), str(cons.cited_not_listed))
check("Wilson (uncited) → listed_not_cited", 5 in cons.listed_not_cited, str(cons.listed_not_cited))
check("Smith/Brown duplicate titles NOT grouped (different titles)",
      not any(set(g) == {1, 3} for g in cons.duplicates))
check("2023b suffix matched to Taylor 2023 (no year_mismatch)",
      not any("Taylor" in m for m in cons.year_mismatches), str(cons.year_mismatches))

dup_refs = reference_normalizer.normalize_all([
    "Smith, J. (2020). Care quality in residential settings. Journal A, 1(1), 1-10.",
    "Smith, J. (2020). Care quality in residential setting. Journal A, 1(1), 1-10.",
])
dup_cons = citation_matcher.check_consistency(dup_refs, [])
check("Fuzzy duplicate (≥0.92) grouped", dup_cons.duplicates == [[1, 2]], str(dup_cons.duplicates))

n_cons = citation_matcher.check_consistency(n_refs, n_intext)
check("Numbering overshoot [5] vs list ending [3]",
      5 in n_cons.numbering_overshoots, str(n_cons.numbering_overshoots))

# ---------------------------------------------------------------------------
# 4. Verdicts with mocked providers
# ---------------------------------------------------------------------------

print("== Verdicts (mocked providers) ==")

GOOD = ExternalRecord(
    source="crossref", title="Care quality in residential settings",
    authors=["Smith, J."], year=2020, journal="Journal of Social Care",
    doi="10.1234/jsc.2020.001",
)


async def _mock_good(*a, **k):
    return GOOD

async def _mock_none(*a, **k):
    return None

async def _mock_empty(*a, **k):
    return []

async def _mock_resolves(*a, **k):
    return True


def run_mocked(ref, good: bool):
    import verification.crossref_client as cc
    import verification.openalex_client as oa
    import verification.semantic_scholar_client as s2
    import verification.pubmed_client as pm
    import verification.arxiv_client as ax
    import verification.doi_validator as dv

    saved = (cc.lookup_doi, cc.search_bibliographic, cc.search_title_author,
             oa.lookup_doi, oa.search_title, s2.lookup_doi, s2.search_title,
             pm.lookup_doi, pm.search, ax.lookup_id, ax.search_title, dv.resolves)
    try:
        cc.lookup_doi = _mock_good if good else _mock_none
        cc.search_bibliographic = _mock_empty
        cc.search_title_author = _mock_empty
        oa.lookup_doi = _mock_none
        oa.search_title = _mock_empty
        s2.lookup_doi = _mock_none
        s2.search_title = _mock_empty
        pm.lookup_doi = _mock_none
        pm.search = _mock_empty
        ax.lookup_id = _mock_none
        ax.search_title = _mock_empty
        dv.resolves = _mock_resolves if good else _mock_none
        return asyncio.run(external_verifier.verify_reference(None, ref))
    finally:
        (cc.lookup_doi, cc.search_bibliographic, cc.search_title_author,
         oa.lookup_doi, oa.search_title, s2.lookup_doi, s2.search_title,
         pm.lookup_doi, pm.search, ax.lookup_id, ax.search_title, dv.resolves) = saved


vr_good = run_mocked(smith, good=True)
check("Perfect Crossref match → verified", vr_good.verdict == "verified",
      f"got {vr_good.verdict} score={vr_good.match.score}")
check("Strategy recorded as doi", vr_good.match.strategy == "doi")
check("No spurious issues on clean match",
      not any(i in vr_good.issues for i in ("author_mismatch", "wrong_year")), str(vr_good.issues))

fake = reference_normalizer.normalize(
    "Fictional, A. (2022). A completely invented study of nothing. Imaginary Journal, 9(9), 1-99.", 1)
vr_bad = run_mocked(fake, good=False)
check("No record anywhere → not_externally_verified", vr_bad.verdict == "not_externally_verified",
      f"got {vr_bad.verdict}")
check("Not-found recommendation makes no fabrication claim (URGENT absent, no positive assertion)",
      "URGENT" not in (vr_bad.recommendation or "")
      and "likely fabricated" not in (vr_bad.recommendation or "").lower()
      and "is fabricated" not in (vr_bad.recommendation or "").lower())
check("Rejected near-misses leak no field issues (gating)",
      "author_mismatch" not in vr_bad.issues and "wrong_year" not in vr_bad.issues,
      str(vr_bad.issues))

# Renormalisation: DOI-less book must not be penalised for absent fields
book_rec = ExternalRecord(source="crossref", title="An uncited monograph on care ethics",
                          authors=["Wilson, G."], year=2018, publisher="Oxford University Press")
m = external_verifier.score_match(wilson, book_rec)
check("DOI-less book renormalised score high", m.score >= 0.85, f"score={m.score} fields={m.field_scores}")

mismatch_rec = ExternalRecord(source="crossref", title=smith.title, authors=["Smith, J."],
                              year=2020, journal=smith.journal, doi="10.9999/other.999")
m2 = external_verifier.score_match(smith, mismatch_rec)
check("DOI mismatch applies ×0.75 penalty", m2.score < 0.80 and m2.field_scores.get("doi") == 0.0,
      f"score={m2.score}")

# ---------------------------------------------------------------------------
# 5. Report generation
# ---------------------------------------------------------------------------

print("== Report ==")
stats.reference_count = len(refs)
report = verification_report.build_report(stats, [vr_good, vr_bad], cons, [])
check("Quality scores in range",
      0 <= report.overall_quality <= 100 and report.reference_quality == 60.0,
      f"overall={report.overall_quality} ref={report.reference_quality}")
check("Not-found refs flagged first, neutral (no positive fabrication claim)",
      "URGENT" not in report.recommendations[0]
      and "are fake" not in report.recommendations[0].lower())
js = verification_report.to_json(report)
check("JSON export parses", '"overall_quality"' in js and len(js) > 500)
html_out = verification_report.to_html(report, "test.pdf")
check("HTML export self-contained", html_out.startswith("<!DOCTYPE html") and "TRACE-AI" in html_out)
check("HTML shows not-externally-verified colour-coded", "#c0562b" in html_out)

# ---------------------------------------------------------------------------
# 6. Chicago author-date + multi-author first-surname (general fixes)
# ---------------------------------------------------------------------------

print("== Chicago author-date & multi-author ==")

CHICAGO_DOC = """
Body. As Autor, Levy, and Murnane (2003) showed, and later work
(Acemoglu, Gancia, and Zilibotti 2012; Beaudry, Green, and Sand 2016)
confirmed. See also Rodríguez-Clare (2010) and Roy's (1951) insight.

1542 THE AMERICAN ECONOMIC REVIEW JUNE 2018

References

Acemoglu, Daron, Gino Gancia, and Fabrizio Zilibotti. 2012. "Competing Engines
of Growth." Journal of Economic Theory 147 (2): 570-601.

Autor, David H., Frank Levy, and Richard J. Murnane. 2003. "The Skill Content
of Recent Technological Change." Quarterly Journal of Economics 118 (4): 1279.

Beaudry, Paul, David A. Green, and Benjamin M. Sand. 2016. "The Great Reversal."
Journal of Labor Economics 34 (S1): S199-S247.

Rodríguez-Clare, Andrés. 2010. "Offshoring in a Ricardian World." American
Economic Journal 2 (2): 227-258.

Roy, A. D. 1951. "Some Thoughts on the Distribution of Earnings." Oxford
Economic Papers 3 (2): 135-146.
"""

c_raw, c_intext, _ = reference_extractor.extract(CHICAGO_DOC)
check("Chicago: 5 references segmented (no page-header noise)", len(c_raw) == 5, f"got {len(c_raw)}")
check("Chicago: running-head '1542 THE AMERICAN...' dropped",
      not any("AMERICAN ECONOMIC REVIEW" in r for r in c_raw))
check("Chicago: Rodríguez-Clare NOT merged into previous ref",
      any(r.startswith("Rodríguez-Clare") for r in c_raw))

leads = {c.get("lead") for c in c_intext if c.get("style") == "author_year"}
check("Multi-author: first surname 'autor' (not 'murnane')", "autor" in leads and "murnane" not in leads, str(leads))
check("Multi-author: 'acemoglu' (not 'zilibotti')", "acemoglu" in leads and "zilibotti" not in leads, str(leads))
check("Accented: 'rodríguez-clare' captured (not 'clare')",
      any(l and l.replace("-", "").startswith("rodr") for l in leads) and "clare" not in leads, str(leads))
check("Possessive: Roy's -> 'roy'", "roy" in leads, str(leads))

c_refs = reference_normalizer.normalize_all(c_raw)
check("Accented ref author parsed: Rodríguez-Clare",
      any(r.authors and r.authors[0].lower().startswith("rodr") for r in c_refs))

c_cons = citation_matcher.check_consistency(c_refs, c_intext)
check("Multi-author citations NOT false 'cited-not-listed'",
      not any("Murnane" in x or "Zilibotti" in x or "Sand" in x for x in c_cons.cited_not_listed),
      str(c_cons.cited_not_listed))
check("Correctly-cited multi-author refs NOT 'listed-not-cited'",
      len(c_cons.listed_not_cited) == 0, str(c_cons.listed_not_cited))

print(f"\n{PASS} passed, {FAIL} failed")

# ---------------------------------------------------------------------------
# 7. Typographic apostrophe (U+2019) — the O'Neil contradiction bug
# ---------------------------------------------------------------------------

print("== Typographic apostrophe (O'Neil) ==")
ONEIL_DOC = (
    "Intro. Bias in algorithms (O\u2019Neil 2016). Also see Eubanks (2018).\n\n"
    "References\n\n"
    "17. Eubanks, V. (2018). Automating Inequality. New York: St. Martin\u2019s Press.\n"
    "18. O\u2019Neil, C. (2016). Weapons of Math Destruction. New York: Crown Publishing.\n"
)
o_raw, o_intext, _ = reference_extractor.extract(ONEIL_DOC)
o_refs = reference_normalizer.normalize_all(o_raw)
check("Typographic apostrophe: O'Neil surname parsed correctly (not 'Neil')",
      any(r.authors and r.authors[0].startswith("O'Neil") for r in o_refs),
      str([r.authors for r in o_refs]))
o_cons = citation_matcher.check_consistency(o_refs, o_intext)
check("O'Neil NOT falsely 'cited but not listed'",
      not any("Neil" in x for x in o_cons.cited_not_listed), str(o_cons.cited_not_listed))
check("O'Neil NOT falsely 'listed but never cited' (no contradiction)",
      len(o_cons.listed_not_cited) == 0, str(o_cons.listed_not_cited))

print(f"\n{PASS} passed, {FAIL} failed")

# ---------------------------------------------------------------------------
# 8. Zone-based extraction: no phantom refs, no embedded running heads (#5, #52)
# ---------------------------------------------------------------------------

print("== Zone-based extraction provenance ==")

# A running head sitting BETWEEN two references (a page break in the PDF) must
# never be extracted as a reference.
EMBEDDED_HEAD_DOC = (
    "Body cites Smith (2020) and Jones (2019).\n\n"
    "References\n\n"
    "Smith, J. (2020). First real reference. Journal A, 1(1), 1-10.\n"
    "1542 THE AMERICAN ECONOMIC REVIEW JUNE 2018\n"
    "Jones, K. (2019). Second real reference. Journal B, 2(2), 11-20.\n"
)
e_raw, _, _ = reference_extractor.extract(EMBEDDED_HEAD_DOC)
check("Embedded running head not extracted as reference",
      not any("AMERICAN ECONOMIC REVIEW" in r for r in e_raw), str(e_raw))
check("Both real references still extracted", len(e_raw) == 2, f"got {len(e_raw)}: {e_raw}")

# A citation-looking line that lives in the BODY (not the references section)
# must not become a bibliography entry (phantom-reference guard, #5).
PHANTOM_DOC = (
    "In the body we mention Jorna and Wagenaar (2019) in passing, but it is "
    "not in our bibliography at all.\n\n"
    "References\n\n"
    "Smith, J. (2020). The only listed work. Journal A, 1(1), 1-10.\n"
)
p_raw, p_intext, _ = reference_extractor.extract(PHANTOM_DOC)
check("Body-only citation never becomes a bibliography entry",
      not any("Jorna" in r for r in p_raw), str(p_raw))
check("Only the genuinely listed reference is extracted",
      len(p_raw) == 1 and "Smith" in p_raw[0], str(p_raw))
check("Body-only mention is still seen as an in-text citation",
      any(c.get("lead") == "jorna" for c in p_intext if c.get("style") == "author_year"),
      str([c.get("lead") for c in p_intext]))

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
