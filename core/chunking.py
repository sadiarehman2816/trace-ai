"""
TRACE-AI v0.1 — Step 0: PDF Pre-Processing
Pure code, no AI. Output is the foundation index for all later steps.

Produces JSON:
{
  "source_document": "filename.pdf",
  "chunks": [
    {
      "chunk_id": "c0001",
      "page_number": 1,
      "text": "full paragraph text...",
      "spans": [
        {"span_id": "c0001_s01", "text": "First sentence."},
        {"span_id": "c0001_s02", "text": "Second sentence."}
      ]
    },
    ...
  ]
}
"""

import fitz  # PyMuPDF
import re
import json
import sys
import os


def _looks_like_garbage(text: str) -> bool:
    """
    Returns True if a chunk looks like PDF internals or binary noise rather than
    readable prose. Catches output from scanned/encrypted/malformed PDFs where
    text extraction yields object streams instead of words.
    """
    if not text or len(text) < 10:
        return True

    lowered = text.lower()
    pdf_markers = ("endobj", "endstream", "flatedecode", "/type", "/filter",
                   "/contents", "structparents", "xref", "startxref")
    marker_hits = sum(1 for m in pdf_markers if m in lowered)
    if marker_hits >= 2:
        return True

    printable_letters = sum(1 for c in text if c.isalpha() or c.isspace())
    if printable_letters / len(text) < 0.55:
        return True

    if text.count("\ufffd") >= 3:
        return True

    return False


def _split_glued_boundaries(text: str) -> str:
    """
    PDF text extraction often drops the newline between a heading / chart-axis
    line and the body sentence, gluing them together (e.g.
    "NHS WORKFORCE STATISTICS Staff vacancies rose." or
    "0 10 20 30 owner occupied ... The number of first time buyers ...").

    This inserts a sentence boundary ('. ') at those glue points so the splitter
    can separate them. It is conservative: it only fires on clear ALL-CAPS-header
    -> Capitalised-word, or chart-axis-number-run -> Capitalised-word patterns.
    Bug fix only; does not change chunking architecture.
    """
    # 1) ALL-CAPS header (3+ caps words) immediately followed by a normal
    #    Capitalised word that starts a sentence.
    text = re.sub(
        r'\b((?:[A-Z][A-Z&]+\s+){2,}[A-Z][A-Z&]+)\s+(?=[A-Z][a-z])',
        r'\1. ', text)

    # 2) A run of >=4 axis-style numbers, optionally followed by short labels,
    #    then a Capitalised sentence start.
    text = re.sub(
        r'((?:\b\d{1,3}\b[ ]+){4,}(?:[a-z][a-z ]+?)?)(?=[A-Z][a-z])',
        r'\1. ', text)

    # 3) A known section-header word glued to the following body sentence (PDF
    #    newline loss), either at the start of the text or right after a sentence
    #    end. Limited to an explicit whitelist of standard report/paper headers so
    #    normal prose is never over-split. Handles the recurring
    #    "Results Private renters..." / "Abstract This study..." case.
    text = re.sub(
        r'(^|(?<=[.!?])\s)'
        r'(Abstract|Introduction|Background|Methods?|Methodology|Results?|'
        r'Findings|Discussion|Conclusions?|Summary|References|Acknowledgements?|'
        r'Overview|Executive Summary)\s+(?=[A-Z][a-z])',
        r'\1\2. ', text)

    return text


def split_into_sentences(text: str) -> list[str]:
    """
    Lightweight sentence splitter.
    Splits on '.', '!', '?' followed by whitespace + capital/number,
    but avoids splitting on common abbreviations and decimals. Also separates
    headings / chart-axis lines that PDF extraction glued to the next sentence.
    """
    text = text.strip()
    if not text:
        return []

    # Separate glued heading / chart-axis boundaries first (PDF newline loss).
    text = _split_glued_boundaries(text)

    # Protect common abbreviations / decimal numbers from being split points
    protected = re.sub(r'\b(e\.g|i\.e|etc|vs|Mr|Mrs|Dr|No|Fig|Ref)\.', r'\1<DOT>', text)
    protected = re.sub(r'(\d)\.(\d)', r'\1<DOT>\2', protected)

    # Split on sentence-ending punctuation followed by space + capital letter or digit or end of string
    raw_sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9"\'])', protected)

    sentences = []
    for s in raw_sentences:
        s = s.replace('<DOT>', '.').strip()
        if s:
            sentences.append(s)
    return sentences


def split_into_chunks(page_text: str, max_chunk_chars: int = 800, min_chunk_chars: int = 200) -> list[str]:
    """
    Splits page text into chunks of bounded size, on sentence boundaries.

    Note: PyMuPDF's plain-text extraction often emits a single '\\n' for both
    line-wraps AND paragraph breaks, so blank-line paragraph detection is
    unreliable across PDF generators. Instead, the whole page text is treated
    as a continuous stream, normalized, split into sentences, and grouped into
    chunks of roughly max_chunk_chars — never truncating a sentence mid-way.

    True double-newline paragraph breaks (where present) are preserved as
    strong split points and force a new chunk to start.
    """
    # Use double-newlines (where they DO exist) as forced paragraph breaks
    paragraphs = re.split(r'\n\s*\n+', page_text)

    chunks = []
    current = ""

    for para in paragraphs:
        # Collapse all internal whitespace/newlines (line-wraps) to single spaces
        normalized = re.sub(r'\s+', ' ', para).strip()
        if not normalized:
            continue

        sentences = split_into_sentences(normalized)

        for sent in sentences:
            if not current:
                current = sent
            elif len(current) + len(sent) + 1 <= max_chunk_chars:
                current = current + " " + sent
            else:
                chunks.append(current)
                current = sent

        # At a real paragraph break, flush the current chunk if it's
        # already a reasonable size, to keep paragraph boundaries meaningful
        if current and len(current) >= min_chunk_chars:
            chunks.append(current)
            current = ""

    if current:
        chunks.append(current)

    return chunks


def preprocess_multiple(pdf_paths: list[str]) -> dict:
    """
    Pools several PDFs into ONE combined index (Tareeqa 1 — combined pool).
    Each document gets a unique doc_tag so chunk/span IDs never collide, and
    every chunk carries its own source_document so evidence remains traceable
    to the right file and page.
    """
    combined_chunks = []
    sources = []
    used_tags = set()

    for path in pdf_paths:
        source_name = os.path.basename(path)
        stem = os.path.splitext(source_name)[0].lower()
        base_tag = re.sub(r"[^a-z0-9]+", "", stem)[:8] or "doc"

        # Ensure tag uniqueness across the pool
        tag = base_tag
        n = 1
        while tag in used_tags:
            n += 1
            tag = f"{base_tag}{n}"
        used_tags.add(tag)

        result = preprocess_pdf(path, doc_tag=tag)
        combined_chunks.extend(result["chunks"])
        sources.append(source_name)

    return {
        "source_document": sources,            # list when pooled
        "document_count": len(sources),
        "chunk_count": len(combined_chunks),
        "chunks": combined_chunks,
    }


def preprocess_pdf(pdf_path: str, doc_tag: str | None = None) -> dict:
    """
    Main entry point: extracts text page-by-page, builds chunk/span index.

    doc_tag: short identifier prefixed to chunk/span IDs to keep them unique
             when several documents are pooled into one index. If not given,
             it is derived from the filename.
    """
    doc = fitz.open(pdf_path)
    source_name = os.path.basename(pdf_path)

    if doc_tag is None:
        # Short, filesystem-safe tag from the filename stem (e.g. "homes_eng")
        stem = os.path.splitext(source_name)[0].lower()
        doc_tag = re.sub(r"[^a-z0-9]+", "", stem)[:8] or "doc"

    all_chunks = []
    chunk_counter = 0

    for page_index in range(len(doc)):
        page = doc[page_index]
        page_number = page_index + 1  # human-readable, 1-based
        page_text = page.get_text("text")

        if not page_text or not page_text.strip():
            continue  # skip empty pages (e.g. scanned images without OCR)

        page_chunks = split_into_chunks(page_text)

        for chunk_text in page_chunks:
            # Skip chunks that are clearly PDF internals / binary garbage rather
            # than readable text (happens with some scanned or malformed PDFs).
            if _looks_like_garbage(chunk_text):
                continue

            chunk_counter += 1
            # Prefix chunk_id with a short doc tag so IDs stay unique when
            # multiple documents are pooled into one index.
            chunk_id = f"{doc_tag}_c{chunk_counter:04d}"

            # Sentence split BEFORE validation, then strip inline metadata
            # references (Figure 1.9, Annex Table 1.6, etc.) from each sentence
            # so 'fake authority' noise never enters retrieval/scoring/themes.
            from core.quality_filter import clean_evidence_text
            sentences = split_into_sentences(chunk_text)
            spans = []
            s_idx = 0
            for sentence in sentences:
                cleaned = clean_evidence_text(sentence)
                # Drop spans that were ONLY a metadata reference (now empty/stub)
                if not cleaned or len(cleaned.strip(" .")) < 3:
                    continue
                s_idx += 1
                spans.append({
                    "span_id": f"{chunk_id}_s{s_idx:02d}",
                    "text": cleaned,
                })

            all_chunks.append({
                "chunk_id": chunk_id,
                "page_number": page_number,
                "source_document": source_name,   # carried on every chunk
                "text": chunk_text,
                "spans": spans
            })

    doc.close()

    return {
        "source_document": source_name,
        "chunk_count": len(all_chunks),
        "chunks": all_chunks
    }


def main():
    """CLI helper: preprocess a PDF given as argv[1] and optionally write the
    resulting chunk/span index JSON to argv[2]. Used for manual debugging."""
    if len(sys.argv) < 2:
        print("Usage: python step0_preprocess.py <path_to_pdf> [output_json_path]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    if not os.path.exists(pdf_path):
        print(f"Error: file not found: {pdf_path}")
        sys.exit(1)

    result = preprocess_pdf(pdf_path)

    if output_path is None:
        base = os.path.splitext(os.path.basename(pdf_path))[0]
        output_path = f"{base}_index.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    total_spans = sum(len(c["spans"]) for c in result["chunks"])
    print(f"Done. {result['chunk_count']} chunks, {total_spans} spans extracted.")
    print(f"Output written to: {output_path}")


if __name__ == "__main__":
    main()
