"""verification/verification_report.py — Stage 6.

Quality scores (reference 50% + citation 30% + evidence 20%), recommendations
(unverified references flagged first, in neutral language), full JSON export, and a self-contained
HTML report (print-to-PDF friendly).
"""

from __future__ import annotations

import dataclasses
import html
import json
from datetime import datetime, timezone

from .models import (
    ClaimResult,
    ConsistencyReport,
    DocumentStats,
    VerificationReport,
    VerifiedReference,
)

_VERDICT_POINTS = {
    "verified": 1.0,
    "likely_verified": 0.8,
    "not_checked": 0.5,             # neutral — verification incomplete, not a negative signal
    "ambiguous_match": 0.4,
    "not_externally_verified": 0.2, # absence in indexes (NOT "fake") — mild signal only
}

_VERDICT_COLORS = {
    "verified": "#1a7f37",
    "likely_verified": "#4c9a2a",
    "ambiguous_match": "#b58900",
    "not_externally_verified": "#c0562b",   # amber-red, NOT alarm red — absence ≠ fake
    "not_checked": "#6a737d",
}


def build_report(
    stats: DocumentStats,
    references: list[VerifiedReference],
    consistency: ConsistencyReport,
    claims: list[ClaimResult],
) -> VerificationReport:
    report = VerificationReport(
        stats=stats, references=references, consistency=consistency, claims=claims,
    )

    # Reference quality (50%)
    if references:
        report.reference_quality = round(
            100 * sum(_VERDICT_POINTS.get(r.verdict, 0.0) for r in references) / len(references), 1
        )
    # Citation quality (30%)
    penalties = (
        len(consistency.cited_not_listed) * 6
        + len(consistency.year_mismatches) * 4
        + len(consistency.duplicates) * 5
        + len(consistency.numbering_gaps) * 3
        + len(consistency.numbering_overshoots) * 6
        + len(consistency.formatting_issues) * 2
        + min(len(consistency.listed_not_cited), 5) * 1
    )
    report.citation_quality = round(max(0.0, 100.0 - penalties), 1)
    # Evidence quality (20%)
    if claims:
        pts = {"Supported": 1.0, "Partially Supported": 0.6, "No Evidence Found": 0.3, "Contradicted": 0.0}
        report.evidence_quality = round(100 * sum(pts.get(c.verdict, 0.3) for c in claims) / len(claims), 1)
    else:
        report.evidence_quality = report.reference_quality   # neutral: don't punish for a disabled stage

    report.overall_quality = round(
        0.5 * report.reference_quality + 0.3 * report.citation_quality + 0.2 * report.evidence_quality, 1
    )

    # Recommendations — unverified references flagged first (neutral language)
    unverified_ext = [r for r in references if r.verdict == "not_externally_verified"]
    if unverified_ext:
        nums = ", ".join(f"#{r.reference.index}" for r in unverified_ext)
        report.recommendations.append(
            f"{len(unverified_ext)} reference(s) had no matching record in the external sources searched "
            f"({nums}). Absence from these indexes is not by itself a problem — verify manually "
            f"(books and grey literature are often unindexed)."
        )
    ambiguous = [r for r in references if r.verdict == "ambiguous_match"]
    if ambiguous:
        report.recommendations.append(
            f"{len(ambiguous)} reference(s) had a possible external match with insufficient "
            f"confidence — manual review recommended."
        )
    doi_broken = [r for r in references if "doi_does_not_resolve" in r.issues or "doi_mismatch" in r.issues]
    if doi_broken:
        report.recommendations.append(f"{len(doi_broken)} reference(s) have DOI problems (non-resolving or mismatched).")
    if consistency.cited_not_listed:
        report.recommendations.append(
            f"{len(consistency.cited_not_listed)} in-text citation(s) have no bibliography entry."
        )
    if consistency.duplicates:
        report.recommendations.append(f"{len(consistency.duplicates)} duplicate reference group(s) detected.")
    if consistency.year_mismatches:
        report.recommendations.append(f"{len(consistency.year_mismatches)} author-year mismatch(es) between text and bibliography.")
    if not report.recommendations:
        report.recommendations.append("No critical issues detected. Spot-check 'likely verified' entries before publication.")

    return report


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

def to_json(report: VerificationReport) -> str:
    payload = dataclasses.asdict(report)
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    payload["tool"] = "TRACE-AI external verification pipeline v2.0"
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)


def _esc(s) -> str:
    return html.escape(str(s)) if s is not None else "—"


def to_html(report: VerificationReport, document_name: str = "document") -> str:
    rows = []
    for vr in report.references:
        ref, m = vr.reference, vr.match
        rec = m.record
        color = _VERDICT_COLORS.get(vr.verdict, "#6a737d")
        doi_html = (
            f'<a href="https://doi.org/{_esc(ref.doi)}">{_esc(ref.doi)}</a>' if ref.doi else "—"
        )
        matched_html = "—"
        if rec:
            matched_html = (
                f"<b>{_esc(rec.title)}</b><br>{_esc(', '.join(rec.authors[:4]))}"
                f"{' et al.' if len(rec.authors) > 4 else ''} ({_esc(rec.year)})<br>"
                f"<i>{_esc(rec.journal)}</i> · via {_esc(rec.source)}"
                f"{' · strategy: ' + _esc(m.strategy) if m.strategy else ''}"
            )
        prov = vr.provenance
        prov_html = (
            f"<b>Source:</b> {_esc(prov['source'])}<br>"
            f"<b>External:</b> {_esc(prov['external_verification'])}<br>"
            f"<b>Relationship:</b> {_esc(prov['relationship'])}"
        )
        rows.append(f"""
        <tr>
          <td>{ref.index}</td>
          <td class="raw">{_esc(ref.raw_text[:400])}</td>
          <td>{matched_html}</td>
          <td>{prov_html}</td>
          <td style="color:{color};font-weight:600">{_esc(vr.verdict.replace('_', ' '))}<br>
              <span class="conf">{vr.confidence:.2f}</span></td>
          <td>{doi_html}</td>
          <td>{_esc(', '.join(vr.issues)) if vr.issues else '—'}</td>
          <td>{_esc(vr.recommendation)}</td>
        </tr>""")

    cons = report.consistency
    cons_items = []
    for label, values in [
        ("Cited but not listed", cons.cited_not_listed),
        ("Listed but never cited (ref #)", cons.listed_not_cited),
        ("Duplicate groups (ref #)", [" & ".join(map(str, g)) for g in cons.duplicates]),
        ("Numbering gaps", cons.numbering_gaps),
        ("Numbering overshoots", cons.numbering_overshoots),
        ("Author-year mismatches", cons.year_mismatches),
        ("Formatting issues", cons.formatting_issues),
    ]:
        if values:
            cons_items.append(f"<li><b>{_esc(label)}:</b> {_esc('; '.join(map(str, values)))}</li>")
    cons_html = "<ul>" + "".join(cons_items) + "</ul>" if cons_items else "<p>No consistency issues detected.</p>"

    claims_html = ""
    if report.claims:
        claim_rows = "".join(
            f"<tr><td>{_esc(c.sentence[:300])}</td><td>{_esc(c.verdict)}</td>"
            f"<td>{'<br>'.join(_esc(e.title) for e in c.evidence[:3]) or '—'}</td></tr>"
            for c in report.claims
        )
        claims_html = f"""
        <h2>Claim spot-checks (conservative — human decides)</h2>
        <table><thead><tr><th>Claim</th><th>Verdict</th><th>Related literature found</th></tr></thead>
        <tbody>{claim_rows}</tbody></table>"""

    recs = "".join(f"<li>{_esc(r)}</li>" for r in report.recommendations)

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>TRACE-AI Verification Report — {_esc(document_name)}</title>
<style>
  body {{ font-family: Georgia, 'Times New Roman', serif; margin: 2rem auto; max-width: 1100px; color: #24292e; }}
  h1 {{ border-bottom: 3px solid #24292e; padding-bottom: .3rem; }}
  .scores {{ display: flex; gap: 1.5rem; margin: 1rem 0; }}
  .score {{ border: 1px solid #d1d5da; border-radius: 8px; padding: .8rem 1.2rem; text-align: center; }}
  .score b {{ font-size: 1.6rem; display: block; }}
  table {{ border-collapse: collapse; width: 100%; font-size: .85rem; margin: 1rem 0; }}
  th, td {{ border: 1px solid #d1d5da; padding: .45rem .6rem; vertical-align: top; text-align: left; }}
  th {{ background: #f6f8fa; }}
  .raw {{ font-family: 'Courier New', monospace; font-size: .78rem; max-width: 300px; }}
  .conf {{ font-weight: 400; color: #6a737d; font-size: .78rem; }}
  @media print {{ body {{ margin: 0.5cm; }} }}
</style></head><body>
<h1>TRACE-AI External Verification Report</h1>
<p><b>Document:</b> {_esc(document_name)} · <b>Generated:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
· <b>Pipeline:</b> v2.0 (Crossref · OpenAlex · Semantic Scholar · PubMed · arXiv · doi.org)</p>
<div class="scores">
  <div class="score"><b>{report.overall_quality}</b>Overall</div>
  <div class="score"><b>{report.reference_quality}</b>References (50%)</div>
  <div class="score"><b>{report.citation_quality}</b>Citations (30%)</div>
  <div class="score"><b>{report.evidence_quality}</b>Evidence (20%)</div>
</div>
<h2>Recommendations</h2><ol>{recs}</ol>
<h2>Document statistics</h2>
<p>{report.stats.pages or '—'} pages · {report.stats.words:,} words · {report.stats.figures} figures ·
{report.stats.tables} tables · {report.stats.reference_count} references ·
{report.stats.intext_citation_count} in-text citations</p>
<h2>Reference verification</h2>
<table><thead><tr><th>#</th><th>Extracted reference</th><th>Matched external record</th>
<th>Provenance</th><th>Verdict</th><th>DOI</th><th>Issues</th><th>Recommendation</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<h2>In-text ↔ bibliography consistency</h2>
{cons_html}
{claims_html}
<p style="color:#6a737d;font-size:.8rem">Verdicts are produced by TRACE-AI's deterministic rule engine.
'Not externally verified' means no acceptable record was found in the sources searched — it is NOT a claim that the
reference is fabricated. External records are shown for comparison only and are never added to the bibliography.
Final judgement rests with a human reviewer.</p>
</body></html>"""
