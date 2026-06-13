"""
CSV / Excel input loader (inputs/tabular_loader.py).

Each ROW becomes one evidence unit (chunk) — ideal for qualitative research
data such as interview quotes with categories. The row number acts as the
'page_number' so evidence stays traceable to a specific record.
"""

import os
from inputs.base import safe_tag


def load_tabular(path: str, doc_tag=None) -> dict:
    """Load a CSV/Excel file where each row is one evidence unit (row number = page)."""
    import pandas as pd

    source_name = os.path.basename(path)
    doc_tag = doc_tag or safe_tag(source_name)

    ext = os.path.splitext(path)[1].lower()
    df = pd.read_excel(path) if ext in (".xlsx", ".xls") else pd.read_csv(path)

    all_chunks = []
    columns = [str(c) for c in df.columns]

    for i, row in df.iterrows():
        parts = []
        for col in columns:
            val = row[col]
            if pd.isna(val):
                continue
            parts.append(f"{col}: {val}")
        row_text = " | ".join(parts).strip()
        if not row_text:
            continue

        chunk_id = f"{doc_tag}_r{int(i) + 1:04d}"
        spans = []
        for s_idx, col in enumerate(columns, start=1):
            val = row[col]
            if pd.isna(val):
                continue
            cell = f"{col}: {val}".strip()
            if cell:
                spans.append({"span_id": f"{chunk_id}_s{s_idx:02d}", "text": cell})
        if not spans:
            spans = [{"span_id": f"{chunk_id}_s01", "text": row_text}]

        all_chunks.append({
            "chunk_id": chunk_id,
            "page_number": int(i) + 1,
            "source_document": source_name,
            "text": row_text,
            "spans": spans,
            "record_type": "row",
        })

    return {
        "source_document": source_name,
        "chunk_count": len(all_chunks),
        "chunks": all_chunks,
    }
