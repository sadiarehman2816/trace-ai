"""
TRACE-AI v0.1 — Step 1-2: Embedding Index + Grounded Retrieval
Pure code, no AI.

This step:
  1. Loads the Step 0 output (chunk/span index with page numbers).
  2. Builds a TF-IDF vector space over all spans (offline, deterministic,
     explainable — no external model downloads required).
  3. For a given theme, retrieves the Top-K most similar spans by cosine
     similarity, along with their rank position (used later in Step 4's
     weighted scoring).

Design note:
  TF-IDF is used instead of a transformer embedding model because this
  environment has no access to model-download endpoints (e.g. huggingface.co).
  TF-IDF cosine similarity is a legitimate, fully-explainable "semantic
  similarity" proxy and keeps the pipeline deterministic and offline.
  This module's interface (TraceIndex.retrieve_top_k) is the seam where a
  transformer embedding model could be swapped in later without changing
  any downstream step.
"""

import json
import sys
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class TraceIndex:
    def __init__(self, index_json: dict):
        """
        index_json: the dict produced by step0_preprocess.py
        """
        self.source_document = index_json["source_document"]
        self.chunks = index_json["chunks"]

        # Flatten all spans into a single list with back-references
        # to their chunk and page, for fast lookup later.
        self.spans = []          # list of dicts: span_id, text, chunk_id, page_number
        self.span_id_to_index = {}  # span_id -> position in self.spans

        for chunk in self.chunks:
            chunk_source = chunk.get("source_document", index_json.get("source_document"))
            for span in chunk["spans"]:
                idx = len(self.spans)
                self.spans.append({
                    "span_id": span["span_id"],
                    "text": span["text"],
                    "chunk_id": chunk["chunk_id"],
                    "page_number": chunk["page_number"],
                    "source_document": chunk_source,
                })
                self.span_id_to_index[span["span_id"]] = idx

        self.vectorizer = None
        self.span_vectors = None
        self._build_vector_space()

    def _build_vector_space(self):
        """
        Fits a TF-IDF vectorizer over all span texts in this document.
        If there are zero spans, the index is left empty (handled at retrieval time).
        """
        if not self.spans:
            return

        texts = [s["text"] for s in self.spans]

        # Bigrams included to capture short phrase matches (e.g. "waiting lists")
        self.vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words="english",
            ngram_range=(1, 2),
            min_df=1,
        )
        self.span_vectors = self.vectorizer.fit_transform(texts)

    def get_span_by_id(self, span_id: str) -> dict | None:
        """Return the stored span dict for a given span_id, or None if not found."""
        idx = self.span_id_to_index.get(span_id)
        if idx is None:
            return None
        return self.spans[idx]

    def retrieve_top_k(self, theme: str, k: int = None, min_score: float = None) -> list[dict]:
        """
        Returns the Top-K spans most similar to `theme`, ranked by cosine
        similarity (descending). Each result includes:
          - span_id, text, chunk_id, page_number
          - semantic_similarity (cosine score, 0-1)
          - retrieval_rank (1 = most relevant, k = least relevant of the returned set)
          - retrieval_rank_score (linear scale: rank 1 -> 1.0, rank k -> 0.2,
            matching Step 4's weighting scheme)

        If no spans meet `min_score`, returns an empty list
        (this is the "INSUFFICIENT EVIDENCE, terminal" trigger downstream).
        """
        from config.thresholds import RETRIEVAL_TOP_K, RETRIEVAL_MIN_SCORE
        if k is None:
            k = RETRIEVAL_TOP_K
        if min_score is None:
            min_score = RETRIEVAL_MIN_SCORE

        if self.vectorizer is None or self.span_vectors is None:
            return []

        theme_vector = self.vectorizer.transform([theme])
        similarities = cosine_similarity(theme_vector, self.span_vectors)[0]

        # Pair each span with its similarity score, sort descending
        scored = list(enumerate(similarities))
        scored.sort(key=lambda pair: pair[1], reverse=True)

        # Import here to avoid a hard dependency if the filter module is absent
        try:
            from core.quality_filter import (is_metadata_span, is_low_quality_span,
                                              contains_metadata_reference)
        except Exception:
            is_metadata_span = lambda _t: False
            is_low_quality_span = lambda _t: False
            contains_metadata_reference = lambda _t: False

        results = []
        for span_idx, score in scored:
            if score < min_score:
                continue
            span = self.spans[span_idx]

            # Evidence hygiene — CLEAN FIRST (split sentences, drop Source:/Note:,
            # truncate metadata clauses), THEN evaluate quality on the cleaned
            # text. Cleaning before filtering means a valid finding glued to a
            # metadata clause (e.g. "X rose. Source: ...") is kept, not discarded.
            try:
                from core.quality_filter import clean_evidence_text, is_chart_or_ocr_noise
                clean_text = clean_evidence_text(span["text"])
            except Exception:
                clean_text = span["text"]
                is_chart_or_ocr_noise = lambda _t: False

            # Reject if nothing useful survived, still metadata/fragment, or
            # chart-axis / OCR noise (Problem B).
            if (not clean_text
                    or contains_metadata_reference(clean_text)
                    or is_metadata_span(clean_text)
                    or is_low_quality_span(clean_text)
                    or is_chart_or_ocr_noise(clean_text)):
                continue

            results.append({
                "span_id": span["span_id"],
                "text": clean_text,
                "chunk_id": span["chunk_id"],
                "page_number": span["page_number"],
                "source_document": span["source_document"],
                "semantic_similarity": round(float(score), 4),
            })
            if len(results) >= k:
                break

        # Assign rank position and rank-based score (1.0 -> 0.2 linear over k slots)
        n = len(results)
        for i, r in enumerate(results):
            rank = i + 1  # 1-based
            if k > 1:
                rank_score = 1.0 - (rank - 1) * (0.8 / (k - 1))
            else:
                rank_score = 1.0
            r["retrieval_rank"] = rank
            r["retrieval_rank_score"] = round(rank_score, 4)

        return results


def build_index_from_file(index_json_path: str) -> TraceIndex:
    """Convenience: load a source file and return a ready TraceIndex."""
    with open(index_json_path, "r", encoding="utf-8") as f:
        index_json = json.load(f)
    return TraceIndex(index_json)


def main():
    """
    CLI test mode:
      python3 step1_2_retrieval.py <index.json> "<theme text>" [top_k]
    Prints the retrieved spans for manual inspection.
    """
    if len(sys.argv) < 3:
        print('Usage: python3 step1_2_retrieval.py <index.json> "<theme text>" [top_k]')
        sys.exit(1)

    index_path = sys.argv[1]
    theme = sys.argv[2]
    top_k = int(sys.argv[3]) if len(sys.argv) > 3 else 5

    trace_index = build_index_from_file(index_path)
    results = trace_index.retrieve_top_k(theme, k=top_k)

    if not results:
        print(f"Theme: {theme}")
        print("-> No spans met the relevance threshold. (INSUFFICIENT EVIDENCE, terminal)")
        return

    print(f"Theme: {theme}")
    print(f"Top {len(results)} spans:")
    for r in results:
        print(f"  [{r['retrieval_rank']}] {r['span_id']} (page {r['page_number']}) "
              f"sim={r['semantic_similarity']} rank_score={r['retrieval_rank_score']}")
        print(f"      {r['text']}")


if __name__ == "__main__":
    main()
