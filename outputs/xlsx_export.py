"""Excel export (outputs/xlsx_export.py)."""

import io


def to_xlsx(findings: list) -> bytes:
    """Render findings to an Excel .xlsx byte string (one row per evidence span)."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "TRACE-AI Findings"
    ws.append(["Theme", "Status", "Confidence Band", "Confidence %",
               "Partial Strength", "Reason",
               "Evidence", "Evidence Type", "Source Document", "Page",
               "Span Score", "Audit Result"])
    for f in findings:
        c = f["confidence"]
        pct = c.get("percent", round(c.get("score", 0) * 100))
        partial = c.get("partial_strength", "")
        reason = f.get("reason", "")
        if f.get("evidence"):
            for ev in f["evidence"]:
                etype = ev.get("evidence_type", {}).get("label", "")
                ws.append([f["theme"], f["status"], c["band"], pct, partial, reason,
                           ev["span_text"], etype, ev.get("source_document", ""),
                           ev["page_number"], ev["span_score"], ev["adversarial_result"]])
        else:
            ws.append([f["theme"], f["status"], c["band"], pct, partial, reason,
                       "", "", "", "", "", ""])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
