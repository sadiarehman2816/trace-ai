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
           "build v0.8-core-stable · metadata-clean + chart/definition filters ACTIVE")

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
    session_dir = os.path.join(tempfile.gettempdir(), "trace_ai_uploads")
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
    blocked = [f for f in findings if f["status"] in ("BLOCKED", "INSUFFICIENT EVIDENCE")]
    if blocked:
        for f in blocked:
            render_finding(f, result.get("pdf_path_map", {}))
    else:
        st.write("None.")

    st.divider()
    st.subheader("Export")
    c1, c2, c3 = st.columns(3)
    if is_enabled("export_json"):
        c1.download_button("Export JSON", to_json(result),
                           file_name="trace_ai_findings.json", mime="application/json")
    if is_enabled("export_xlsx"):
        c2.download_button("Export Excel", to_xlsx(findings),
                           file_name="trace_ai_findings.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if is_enabled("export_docx"):
        c3.download_button("Export Word", to_docx(findings, result["source_document"]),
                           file_name="trace_ai_findings.docx",
                           mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
