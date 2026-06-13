"""
URL input loader (inputs/url_loader.py).

Fetches a web page and extracts readable text. Requires internet access
(works on the user's machine).
"""

import re
from inputs.base import build_index_from_pages, safe_tag, chunk_by_size


def load_url(url: str, doc_tag=None) -> dict:
    """Fetch a web page and extract readable text into the normalized index."""
    import requests

    source_name = url
    doc_tag = doc_tag or safe_tag(re.sub(r"https?://", "", url))

    resp = requests.get(url, timeout=20, headers={"User-Agent": "TRACE-AI/0.1"})
    resp.raise_for_status()

    text = _html_to_text(resp.text)
    pages = chunk_by_size(text, 3000)
    return build_index_from_pages(pages, source_name, doc_tag)


def _html_to_text(html: str) -> str:
    """Lightweight HTML -> text. Prefers BeautifulSoup if available."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
    except Exception:
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)
