"""
TRACE-AI — Loader Base Helpers (inputs/base.py)

Shared building blocks used by every per-format loader so we never duplicate
chunk/span construction (DO #8). Each loader's only job is to turn its format
into a list of 'page' texts; this module turns those into the normalized index.
"""

import os
import re

from core.chunking import split_into_chunks, split_into_sentences, _looks_like_garbage


def safe_tag(name: str) -> str:
    """Short, filesystem-safe document tag derived from a name/URL."""
    stem = os.path.splitext(os.path.basename(name))[0].lower()
    return re.sub(r"[^a-z0-9]+", "", stem)[:8] or "doc"


def build_index_from_pages(pages: list[str], source_name: str, doc_tag: str) -> dict:
    """
    Turns a list of page texts into the normalized chunk/span index that the
    whole pipeline understands. 1 list entry = 1 'page' (synthesised for formats
    without real pages). Garbage/binary chunks are skipped.
    """
    all_chunks = []
    chunk_counter = 0

    for page_index, page_text in enumerate(pages):
        page_number = page_index + 1
        if not page_text or not page_text.strip():
            continue

        for chunk_text in split_into_chunks(page_text):
            if _looks_like_garbage(chunk_text):
                continue
            chunk_counter += 1
            chunk_id = f"{doc_tag}_c{chunk_counter:04d}"
            sentences = split_into_sentences(chunk_text)
            spans = [
                {"span_id": f"{chunk_id}_s{i:02d}", "text": s}
                for i, s in enumerate(sentences, start=1)
            ]
            all_chunks.append({
                "chunk_id": chunk_id,
                "page_number": page_number,
                "source_document": source_name,
                "text": chunk_text,
                "spans": spans,
            })

    return {
        "source_document": source_name,
        "chunk_count": len(all_chunks),
        "chunks": all_chunks,
    }


def chunk_by_size(text: str, size: int = 3000) -> list[str]:
    """Splits free text into synthetic 'pages' of ~size chars on paragraph breaks."""
    paras = re.split(r"\n\s*\n", text)
    pages, buf = [], ""
    for p in paras:
        if len(buf) + len(p) + 2 <= size:
            buf = (buf + "\n\n" + p).strip()
        else:
            if buf:
                pages.append(buf)
            buf = p
    if buf:
        pages.append(buf)
    return pages or [text]
