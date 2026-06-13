"""Plain text (.txt/.md) input loader."""

import os
from inputs.base import build_index_from_pages, safe_tag, chunk_by_size


def load_txt(path: str, doc_tag=None) -> dict:
    """Load a plain-text (.txt/.md) file into the normalized index."""
    source_name = os.path.basename(path)
    doc_tag = doc_tag or safe_tag(source_name)
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    pages = text.split("\f") if "\f" in text else chunk_by_size(text, 3000)
    return build_index_from_pages(pages, source_name, doc_tag)
