"""
TRACE-AI — Unified Input Dispatcher (inputs/loader.py)

Single entry point that auto-detects the input type and routes to the right
per-format loader. Multiple sources are pooled into one combined index
(cross-document mode). Format availability is gated by feature flags.
"""

import os
import re

from config.feature_flags import is_enabled
from inputs.base import safe_tag
from inputs.pdf_loader import load_pdf


def load_source(source: str, doc_tag=None) -> dict:
    """Auto-detects type and returns a normalized index for one source."""
    if source.lower().startswith(("http://", "https://")):
        if not is_enabled("input_url"):
            raise ValueError("URL input is disabled.")
        from inputs.url_loader import load_url
        return load_url(source, doc_tag)

    ext = os.path.splitext(source)[1].lower()
    if ext == ".pdf":
        return load_pdf(source, doc_tag)
    if ext == ".docx":
        if not is_enabled("input_docx"):
            raise ValueError("DOCX input is disabled.")
        from inputs.docx_loader import load_docx
        return load_docx(source, doc_tag)
    if ext in (".txt", ".md", ".text"):
        from inputs.txt_loader import load_txt
        return load_txt(source, doc_tag)
    if ext in (".csv", ".tsv"):
        if not is_enabled("input_csv"):
            raise ValueError("CSV input is disabled.")
        from inputs.tabular_loader import load_tabular
        return load_tabular(source, doc_tag)
    if ext in (".xlsx", ".xls"):
        if not is_enabled("input_xlsx"):
            raise ValueError("Excel input is disabled.")
        from inputs.tabular_loader import load_tabular
        return load_tabular(source, doc_tag)

    raise ValueError(f"Unsupported input type: {source} (ext '{ext}'). "
                     "Supported: .pdf, .docx, .txt, .csv, .xlsx, or http(s) URL.")


def load_multiple(sources: list[str]) -> dict:
    """Loads several sources (any types) and pools them into ONE index."""
    combined_chunks = []
    names = []
    used_tags = set()

    for src in sources:
        base = safe_tag(re.sub(r"https?://", "", src))
        tag, n = base, 1
        while tag in used_tags:
            n += 1
            tag = f"{base}{n}"
        used_tags.add(tag)

        idx = load_source(src, doc_tag=tag)
        combined_chunks.extend(idx["chunks"])
        names.append(idx["source_document"])

    return {
        "source_document": names,
        "document_count": len(names),
        "chunk_count": len(combined_chunks),
        "chunks": combined_chunks,
    }
