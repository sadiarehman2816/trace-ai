"""TRACE-AI external verification pipeline v2.0.

Every reference is independently verified against six external scholarly
sources (Crossref, OpenAlex, Semantic Scholar, PubMed, arXiv, doi.org).
The uploaded document is treated as input only.

Public API:
    verify_document(text, ...)        -> VerificationReport (sync, Streamlit-safe)
    verify_document_async(text, ...)  -> VerificationReport
    to_json(report)                   -> str
    to_html(report, document_name)    -> str
"""

from .pipeline import verify_document, verify_document_async
from .verification_report import to_html, to_json

__all__ = ["verify_document", "verify_document_async", "to_json", "to_html"]
__version__ = "2.0.0"
