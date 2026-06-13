"""PDF input loader. Uses core.chunking for true page-numbered extraction."""

from core.chunking import preprocess_pdf


def load_pdf(path: str, doc_tag=None) -> dict:
    """Load a PDF file into the normalized chunk/span index (true page numbers)."""
    return preprocess_pdf(path, doc_tag=doc_tag)
