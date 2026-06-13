"""Word (.docx) input loader. Groups paragraphs into synthetic pages."""

import os
from inputs.base import build_index_from_pages, safe_tag


def load_docx(path: str, doc_tag=None) -> dict:
    """Load a Word .docx file, grouping paragraphs into synthetic pages."""
    from docx import Document
    source_name = os.path.basename(path)
    doc_tag = doc_tag or safe_tag(source_name)

    document = Document(path)
    paras = [p.text for p in document.paragraphs if p.text and p.text.strip()]

    # ~12 paragraphs per synthetic page keeps page_number meaningful.
    pages, buf = [], []
    for para in paras:
        buf.append(para)
        if len(buf) >= 12:
            pages.append("\n\n".join(buf))
            buf = []
    if buf:
        pages.append("\n\n".join(buf))

    return build_index_from_pages(pages or [""], source_name, doc_tag)
