"""
TRACE-AI — Streamlit Entry Point (app.py)

UI ONLY. Contains no verification, scoring, or business logic (DO #1, DON'T #3).
Everything substantive is imported from the modular packages:
  inputs/   loading      core/   engine      models/  AI      outputs/ exports

TRACE-AI is a research-integrity platform — trust, traceability, evidence
verification. Reliability over sophistication.
"""

import os
import tempfile
import streamlit as st

from core.pipeline import analyse_theme
from core.retrieval import TraceIndex
from core.theme_engine import discover_themes
from inputs.loader import load_source, load_multiple
from models.adversarial_review import _get_client
from outputs.json_export import to_json
from outputs.xlsx_export import to_xlsx
from outputs.docx_export import to_docx
from config.feature_flags import is_enabled
from ui.results_screen import render_finding

st.set_page_config(page_title="TRACE-AI", page_icon="🔍", layout="wide")

st.title("🔍 TRACE-AI")
st.caption("Evidence-Based Research Intelligence  ·  **Golden Rule: No Evidence = No Claim**  ·  "
           "TRACE-AI Community · build v1.0-beta · metadata-clean + chart/definition filters ACTIVE")

mode = ("HYBRID — LLM theme synthesis + deterministic verification"
        if os.environ.get("ANTHROPIC_API_KEY")
        else "MOCK — fully deterministic (offline)")
st.info(f"Engine mode: **{mode}**  ·  Upload PDF / Word / CSV / Excel or paste URLs.  ·  "
        f"All evidence selection, scoring & verification is deterministic. "
        f"The LLM only proposes clean theme names.")

# ---- Screen 1: inputs ----
st.subheader("1 · Add research document(s)")
accepted = ["pdf"]
if is_enabled("input_docx"): accepted.append("docx")
accepted += ["txt", "md"]
if is_enabled("input_csv"): accepted.append("csv")
if is_enabled("input_xlsx"): accepted += ["xlsx", "xls"]

uploaded = st.file_uploader(
    "Upload one or more files — pooled into one combined evidence set.",
    type=accepted, accept_multiple_files=True,
)

urls = []
if is_enabled("input_url"):
    urls_text = st.text_area(
        "…or paste web links (one URL per line) to read pages directly",
        value="", height=70, placeholder="https://example.gov.uk/housing-report")
    urls = [u.strip() for u in urls_text.splitlines()
            if u.strip().startswith(("http://", "https://"))]

# ---- Screen 2: themes ----
st.subheader("2 · Themes")
auto_discover = True
manual_themes = []
if is_enabled("auto_theme"):
    theme_mode = st.radio("How should themes be decided?",
                          ["Auto-discover from documents (recommended)",
                           "Enter themes manually"], index=0)
    auto_discover = theme_mode.startswith("Auto")
else:
    auto_discover = False

if not auto_discover:
    default_themes = "Housing Affordability\nSocial housing waiting lists\nRough sleeping\nMental Health Impact"
    themes_text = st.text_area("One theme per line", value=default_themes, height=140)
    manual_themes = [t.strip() for t in themes_text.splitlines() if t.strip()]
else:
    st.caption("TRACE-AI will read the document(s) and propose themes automatically — "
               "themes emerge from the data.")

can_run = (bool(uploaded) or bool(urls)) and (auto_discover or manual_themes)
analyse = st.button("Analyse", type="primary", disabled=not can_run)


def run(uploaded_files, url_list, manual_theme_list, auto):
    """Run the full analysis for uploaded files/URLs and return the result dict for the UI."""
    tmp_paths, pdf_path_map = [], {}
    session_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads_storage")
    os.makedirs(session_dir, exist_ok=True)
    for uf in uploaded_files or []:
        nice_path = os.path.join(session_dir, uf.name)
        with open(nice_path, "wb") as out:
            out.write(uf.getbuffer())
        tmp_paths.append(nice_path)
        if os.path.splitext(uf.name)[1].lower() == ".pdf":
            pdf_path_map[uf.name] = nice_path

    sources = tmp_paths + list(url_list or [])
    steps = ["Reading documents…", "Discovering themes…", "Retrieving evidence…",
             "Adversarial review…", "Scoring confidence…"]
    prog = st.progress(0, text=steps[0])

    index_json = load_source(sources[0]) if len(sources) == 1 else load_multiple(sources)
    prog.progress(25, text=steps[1])

    trace_index = TraceIndex(index_json)
    client = _get_client()

    discovered = []
    if (auto or not manual_theme_list) and is_enabled("auto_theme"):
        discovered = discover_themes(index_json, client=client)
        theme_list = discovered if (auto or not manual_theme_list) else manual_theme_list
    else:
        theme_list = manual_theme_list
    prog.progress(40, text=steps[2])

    findings = []
    n = max(len(theme_list), 1)
    for i, theme in enumerate(theme_list):
        findings.append(analyse_theme(theme, trace_index, client))
        prog.progress(40 + int(55 * (i + 1) / n), text=steps[3])
    prog.progress(100, text=steps[4])

    return {
        "trace_ai_version": "0.6", "mode": "HYBRID" if client else "MOCK",
        "source_document": index_json["source_document"],
        "document_count": index_json.get("document_count", 1),
        "chunk_count": index_json["chunk_count"],
        "themes_analysed": len(theme_list),
        "discovered_themes": discovered, "findings": findings,
        "pdf_path_map": pdf_path_map,
    }


if analyse and can_run:
    st.session_state["result"] = run(uploaded, urls, manual_themes, auto_discover)

if "result" in st.session_state:
    result = st.session_state["result"]
    findings = result["findings"]

    if result.get("discovered_themes"):
        st.divider()
        st.subheader("Auto-discovered themes")
        st.caption("These themes were generated from the document(s) — themes emerge from the data.")
        st.write(" · ".join(result["discovered_themes"]))

    st.divider()
    st.subheader("3 · Verified & Supported Findings")
    shown = [f for f in findings if f["status"] in
             ("VERIFIED", "PARTIALLY SUPPORTED", "WEAK EVIDENCE", "CONFLICTING EVIDENCE")]
    if shown:
        for f in shown:
            render_finding(f, result.get("pdf_path_map", {}))
    else:
        st.write("No supported findings.")

    st.subheader("4 · Blocked & Insufficient")
    st.info("ℹ️ These themes were automatically detected but could not be verified — either the document does not contain sufficient evidence for them, or they may be metadata (e.g. journal names, copyright text) rather than research topics. No action needed.")
    blocked = [f for f in findings if f["status"] in ("BLOCKED", "INSUFFICIENT EVIDENCE")]
    if blocked:
        for f in blocked:
            render_finding(f, result.get("pdf_path_map", {}))
    else:
        st.write("None.")

    st.divider()
    st.subheader("Export")
    c1, c2, c3, c4 = st.columns(4)
    if is_enabled("export_json"):
        c1.download_button("Export JSON", to_json(result),
                           file_name="trace_ai_findings.json", mime="application/json")
    if is_enabled("export_xlsx"):
        c2.download_button("Export Excel", to_xlsx(findings),
                           file_name="trace_ai_findings.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if is_enabled("export_pdf"):
        from outputs.pdf_export import to_pdf
        c4.download_button("Export PDF (Full)", to_pdf(findings, result["source_document"], public_mode=False),
                          file_name="trace_ai_report_full.pdf", mime="application/pdf")
        c4.download_button("Export PDF (Public)", to_pdf(findings, result["source_document"], public_mode=True), file_name="trace_ai_report_public.pdf", mime="application/pdf")
    if is_enabled("export_docx"):
        c3.download_button("Export Word", to_docx(findings, result["source_document"]),
                           file_name="trace_ai_findings.docx",
                           mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


# Citation Checker — external verification pipeline v2.0
if is_enabled("citation_checker") and st.session_state.get("result"):
    st.divider()
    st.subheader("5 · External Reference Verification")
    st.caption("Every reference is checked independently against Crossref, OpenAlex, "
               "Semantic Scholar, PubMed, arXiv and doi.org. The document is input only.")

    opt_col1, opt_col2 = st.columns(2)
    opt_urls = opt_col1.checkbox("Check plain URLs (HEAD requests — adds latency)",
                                 value=is_enabled("verify_urls"))
    opt_claims = opt_col2.checkbox("Claim spot-checks (experimental, conservative)",
                                   value=is_enabled("claim_verification"))

    # If the uploaded file set changed since the last verification, drop the
    # stale report so the previous document's references don't linger.
    _sig = tuple(sorted(uf.name for uf in (uploaded or [])))
    if st.session_state.get("_verif_sig") != _sig:
        st.session_state.pop("verification_report", None)
        st.session_state["_verif_sig"] = _sig

    if st.button("Run External Verification"):
        import fitz
        full_text, page_count = "", 0

        # Read the CURRENTLY uploaded files directly — never the cached
        # pdf_path_map from the theme analysis (that path can be stale and
        # would make every new upload show the previous document's references).
        current_files = uploaded or []
        used_current = False
        for uf in current_files:
            if uf.name.lower().endswith(".pdf"):
                used_current = True
                data = uf.getvalue()
                with fitz.open(stream=data, filetype="pdf") as doc:
                    page_count += doc.page_count
                    for page in doc:
                        full_text += page.get_text() + "\n\n"

        # Fallback: if the uploader is empty this run (e.g. only the theme
        # analysis was run earlier), use its freshly-saved paths.
        if not used_current:
            src_map = st.session_state.get("result", {}).get("pdf_path_map", {})
            for tag, path in (src_map.items() if isinstance(src_map, dict) else []):
                if path and path.endswith(".pdf"):
                    with fitz.open(path) as doc:
                        page_count += doc.page_count
                        for page in doc:
                            full_text += page.get_text() + "\n\n"
        if not full_text:
            st.warning("Could not extract text for reference verification.")
        else:
            from verification import verify_document
            prog = st.progress(0.0, text="Verifying references against external sources…")

            def _update(done, total):
                prog.progress(done / max(total, 1),
                              text=f"Verifying references… {done}/{total}")

            report = verify_document(full_text, pages=page_count,
                                     check_urls=opt_urls, check_claims=opt_claims,
                                     progress=_update)
            prog.empty()
            st.session_state["verification_report"] = report

    report = st.session_state.get("verification_report")
    if report:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Overall quality", f"{report.overall_quality}")
        m2.metric("References (50%)", f"{report.reference_quality}")
        m3.metric("Citations (30%)", f"{report.citation_quality}")
        m4.metric("Evidence (20%)", f"{report.evidence_quality}")

        st.markdown("#### Recommendations")
        for rec in report.recommendations:
            (st.error if rec.startswith("URGENT") else st.info)(rec)

        _ICON = {"verified": "✅", "likely_verified": "🟢", "ambiguous_match": "🟠",
                 "not_externally_verified": "🟤", "not_checked": "⚪"}
        _LABEL = {"verified": "verified", "likely_verified": "likely verified",
                  "ambiguous_match": "ambiguous match",
                  "not_externally_verified": "not externally verified",
                  "not_checked": "not checked"}
        st.markdown("#### References")
        st.caption("Every reference below was extracted from the uploaded document. "
                   "External records are shown for comparison only — they are never added to your bibliography.")
        for vr in report.references:
            ref = vr.reference
            icon = _ICON.get(vr.verdict, "⚪")
            label = _LABEL.get(vr.verdict, vr.verdict.replace('_', ' '))
            with st.expander(f"{icon} {ref.index}. {ref.raw_text[:90]}…  "
                             f"[{label} · {vr.confidence:.2f}]"):
                prov = vr.provenance
                st.markdown(
                    f"**Source of reference:** {prov['source']}  \n"
                    f"**External verification:** {prov['external_verification']}  \n"
                    f"**Relationship:** {prov['relationship']}"
                )
                if vr.match.record:
                    rec = vr.match.record
                    st.write(f"**External record (for comparison):** {rec.title}")
                    st.write(f"{', '.join(rec.authors[:4])}"
                             f"{' et al.' if len(rec.authors) > 4 else ''} ({rec.year}) — *{rec.journal or '—'}*")
                    st.write(f"via `{rec.source}` · strategy: `{vr.match.strategy}` "
                             f"· score {vr.match.score:.2f}")
                    if rec.doi:
                        st.write(f"DOI: [{rec.doi}](https://doi.org/{rec.doi})")
                st.write(f"Providers tried: {', '.join(dict.fromkeys(vr.providers_tried)) or '—'}")
                if vr.issues:
                    st.warning("Issues: " + ", ".join(vr.issues))
                st.write(f"**Recommendation:** {vr.recommendation}")

        cons = report.consistency
        st.markdown("#### In-text ↔ bibliography consistency")
        cons_lines = []
        if cons.cited_not_listed:
            cons_lines.append(f"Cited but not listed: {', '.join(cons.cited_not_listed)}")
        if cons.listed_not_cited:
            cons_lines.append(f"Listed but never cited (ref #): {cons.listed_not_cited}")
        if cons.duplicates:
            cons_lines.append(f"Duplicate groups: {cons.duplicates}")
        if cons.numbering_gaps:
            cons_lines.append(f"Numbering gaps: {cons.numbering_gaps}")
        if cons.numbering_overshoots:
            cons_lines.append(f"Numbering overshoots: {cons.numbering_overshoots}")
        if cons.year_mismatches:
            cons_lines.append(f"Year mismatches: {'; '.join(cons.year_mismatches)}")
        if cons.formatting_issues:
            cons_lines.append("; ".join(cons.formatting_issues))
        if cons_lines:
            for line in cons_lines:
                st.warning(line)
        else:
            st.success("No consistency issues detected.")

        if report.claims:
            st.markdown("#### Claim spot-checks")
            st.caption("Metadata search proves relevant literature exists, not that it agrees — human decides.")
            for c in report.claims:
                st.write(f"- *{c.sentence[:200]}…* → **{c.verdict}**")

        d1, d2 = st.columns(2)
        from verification import to_json as verification_to_json, to_html as verification_to_html
        d1.download_button("Download JSON report", verification_to_json(report),
                           file_name="trace_ai_verification.json", mime="application/json")
        d2.download_button("Download HTML report (print-to-PDF)",
                           verification_to_html(report, "uploaded document"),
                           file_name="trace_ai_verification.html", mime="text/html")
