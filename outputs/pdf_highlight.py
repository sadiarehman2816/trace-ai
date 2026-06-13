"""
TRACE-AI — PDF Highlight Viewer

Renders a single PDF page as an image with the evidence sentence highlighted,
so a researcher can click a finding and SEE the exact quote in its original
context on the page.

Only applies to PDF sources (DOCX/CSV/TXT/URL have no fixed page layout).

Main entry point:
    render_highlighted_page(pdf_path, page_number, quote) -> PNG bytes | None
"""

import io
import re
import fitz  # PyMuPDF


def _normalize(text: str) -> str:
    """Collapse whitespace for fuzzy matching against PDF text."""
    return re.sub(r"\s+", " ", text).strip()


def _find_quote_rects(page, quote: str):
    """
    Tries several strategies to locate the quote on the page and returns a list
    of fitz.Rect areas to highlight.

      1. Exact search of the whole quote.
      2. Search of a long distinctive sub-phrase (first ~8 words).
      3. Word-span fallback: highlight the region spanning the quote's words.
    """
    quote_norm = _normalize(quote)
    if not quote_norm:
        return []

    # Strategy 1 — full-quote search (PyMuPDF handles minor spacing)
    rects = page.search_for(quote_norm, quads=False)
    if rects:
        return rects

    # Strategy 2 — distinctive opening sub-phrase
    words = quote_norm.split()
    if len(words) > 6:
        sub = " ".join(words[:8])
        rects = page.search_for(sub, quads=False)
        if rects:
            return rects

    # Strategy 3 — try a middle chunk (handles headers/footers splitting text)
    if len(words) > 10:
        mid = " ".join(words[3:11])
        rects = page.search_for(mid, quads=False)
        if rects:
            return rects

    # Strategy 4 — shorter leading phrase
    if len(words) >= 4:
        rects = page.search_for(" ".join(words[:4]), quads=False)
        if rects:
            return rects

    return []


def render_highlighted_page(pdf_path: str, page_number: int, quote: str,
                            zoom: float = 2.0) -> bytes | None:
    """
    Returns PNG bytes of the given (1-based) PDF page with `quote` highlighted.
    Returns None if the file can't be opened or the page is out of range.
    Highlighting is best-effort: if the exact quote isn't found, the page is
    still rendered (without a highlight) so the user can read it.
    """
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return None

    page_index = page_number - 1
    if page_index < 0 or page_index >= len(doc):
        doc.close()
        return None

    page = doc[page_index]

    # Draw highlights over any located rects
    rects = _find_quote_rects(page, quote)
    for rect in rects:
        annot = page.add_highlight_annot(rect)
        annot.set_colors(stroke=(1, 0.92, 0.23))  # yellow
        annot.update()

    # Render page to PNG at the requested zoom (sharper text)
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix)
    png_bytes = pix.tobytes("png")

    doc.close()
    return png_bytes


def quote_found_on_page(pdf_path: str, page_number: int, quote: str) -> bool:
    """Quick check: is the quote (or a distinctive part) locatable on the page?"""
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return False
    page_index = page_number - 1
    if page_index < 0 or page_index >= len(doc):
        doc.close()
        return False
    page = doc[page_index]
    found = bool(_find_quote_rects(page, quote))
    doc.close()
    return found
