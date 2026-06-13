"""
TRACE-AI — Results Screen (ui/results_screen.py)

Pure presentation: renders one finding card (status, confidence, evidence with
type + strength badges, audit trail, confidence breakdown, inline PDF viewer).
No business logic here — all decisions arrive pre-computed in the finding dict.
"""

import streamlit as st
import streamlit.components.v1 as components

from config.feature_flags import is_enabled

STATUS_STYLE = {
    "VERIFIED": ("🟢", "#1b7f3b", "#e7f6ec"),
    "PARTIALLY SUPPORTED": ("🟡", "#9a6700", "#fff8e1"),
    "WEAK EVIDENCE": ("🟠", "#b5651d", "#fff3e6"),
    "INSUFFICIENT EVIDENCE": ("🔍", "#5a5a5a", "#f0f0f0"),
    "BLOCKED": ("🔴", "#b32424", "#fdecec"),
    "CONFLICTING EVIDENCE": ("⚡", "#6f42c1", "#f3effb"),
}


def render_finding(f: dict, pdf_path_map: dict = None):
    """Render one finding card (status, evidence, badges, audit trail, PDF viewer)."""
    pdf_path_map = pdf_path_map or {}
    icon, color, bg = STATUS_STYLE.get(f["status"], ("•", "#333", "#eee"))
    conf = f["confidence"]

    band = conf.get("band", "None")
    pct = conf.get("percent", round(conf.get("score", 0) * 100))
    conf_label = f"{band} · {pct}%"
    if conf.get("partial_strength"):
        conf_label += f" · {conf['partial_strength']}"

    st.markdown(
        f"<div style='background:{bg};padding:14px 16px;border-radius:10px;border-left:5px solid {color}'>"
        f"<b style='font-size:1.05rem'>{f['theme']}</b><br>"
        f"<span style='color:{color};font-weight:600'>{icon} {f['status']}</span>"
        f" &nbsp;·&nbsp; Confidence: <b>{conf_label}</b></div>",
        unsafe_allow_html=True,
    )

    if f.get("reason"):
        st.caption(f["reason"])

    for ev_idx, ev in enumerate(f.get("evidence", [])):
        strength = ev.get("strength", {})
        badge = f"{strength.get('emoji','')} {strength.get('label','')}".strip()
        etype = ev.get("evidence_type", {})
        type_badge = f"{etype.get('emoji','')} {etype.get('label','')}".strip()
        src_label = ev.get("source_label") or ev.get("source_document", "")
        st.markdown(
            f"> {ev['span_text']}  \n"
            f"{type_badge} · **{badge}** · 📄 {src_label} · "
            f"audit {ev['adversarial_result']} "
            f"(Q1 {ev['adversarial']['q1']}, Q2 {ev['adversarial']['q2']}, Q3 {ev['adversarial']['q3']})"
        )

        # Inline PDF highlight viewer (single-click toggle, stays in place)
        src_doc = ev.get("source_document")
        if is_enabled("pdf_highlight") and src_doc in pdf_path_map:
            view_key = f"show_pdf_{f['theme']}_{ev_idx}".replace(" ", "_")
            st.session_state.setdefault(view_key, False)
            label = ("🔽 Hide PDF" if st.session_state[view_key]
                     else f"🔍 View in PDF (page {ev['page_number']})")
            if st.button(label, key=f"btn_{view_key}"):
                st.session_state[view_key] = not st.session_state[view_key]

            if st.session_state[view_key]:
                anchor = f"pdfview_{view_key}"
                st.markdown(f"<div id='{anchor}'></div>", unsafe_allow_html=True)
                components.html(
                    f"<script>const e=window.parent.document.getElementById('{anchor}');"
                    f"if(e){{e.scrollIntoView({{behavior:'smooth',block:'center'}});}}</script>",
                    height=0,
                )
                try:
                    from outputs.pdf_highlight import render_highlighted_page, quote_found_on_page
                    png = render_highlighted_page(pdf_path_map[src_doc], ev["page_number"], ev["span_text"])
                    if png:
                        if not quote_found_on_page(pdf_path_map[src_doc], ev["page_number"], ev["span_text"]):
                            st.info("Showing the page. The exact sentence couldn't be auto-located "
                                    "for highlighting, but the quote is on this page.")
                        st.image(png, width="stretch")
                    else:
                        st.warning("Could not render this PDF page.")
                except Exception as e:
                    st.warning(f"Viewer error: {e}")

    if f.get("audit_trail"):
        with st.expander("Audit trail (how this decision was reached)"):
            for stg in f["audit_trail"]:
                mark = "✅" if stg["outcome"] == "pass" else "❌"
                st.markdown(f"**{mark} {stg['stage']}**  \n{stg['detail']}")

    if conf.get("breakdown"):
        with st.expander("Confidence score breakdown"):
            bd = conf["breakdown"]
            st.markdown(
                f"**Total confidence: {conf.get('score', 0)} ({pct}%)**  \n"
                f"= semantic {bd.get('semantic', 0)} + lexical {bd.get('lexical', 0)} "
                f"+ consistency {bd.get('consistency', 0)} + span-count {bd.get('span_count', 0)} "
                f"+ source-diversity {bd.get('source_diversity', 0)}"
            )
    st.write("")
