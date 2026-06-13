"""
TRACE-AI — Pipeline Orchestrator (core/pipeline.py)

Wires the modules together for one analysis run. The orchestrator coordinates;
it contains no business rules of its own. AI components only suggest; the rule
engine (core.verification) decides the final status (DO #10, DON'T #4).

Flow per theme:
  retrieve (core.retrieval) -> select [AI] (models.adversarial_review)
  -> score (core.scoring) -> quality/type (core.quality_filter)
  -> adversarial [AI] -> contradiction (core.contradiction)
  -> confidence (core.scoring) -> status + audit (core.verification)
"""

from core.retrieval import TraceIndex
from inputs.loader import load_source, load_multiple
from core.theme_engine import discover_themes
from core.scoring import span_score, confidence_score
from core.contradiction import detect_contradiction
from core.verification import final_status, build_audit_trail
from core.labels import evidence_strength, clean_source_label, partial_strength
from models.adversarial_review import _get_client, select_spans, adversarial_review

from config.thresholds import RETRIEVAL_TOP_K, DEFINITION_SCORE_FACTOR
from config.feature_flags import is_enabled

try:
    from core.quality_filter import classify_evidence_type as _classify_type
except Exception:
    def _classify_type(text, source=""):
        """Fallback evidence-type classifier used if quality_filter is unavailable."""
        return {"label": "General statement", "emoji": "📝"}


def analyse_theme(theme: str, trace_index: TraceIndex, client) -> dict:
    """Runs the full per-theme pipeline and returns the finding record."""

    candidates = trace_index.retrieve_top_k(theme, k=RETRIEVAL_TOP_K)
    retrieved_any = len(candidates) > 0

    if not retrieved_any:
        trail = build_audit_trail(0, 0, [], [], False, "INSUFFICIENT EVIDENCE")
        return {
            "theme": theme,
            "status": "INSUFFICIENT EVIDENCE",
            "confidence": {"band": "None", "score": 0.0, "percent": 0,
                           "breakdown": {"semantic": 0.0, "lexical": 0.0,
                                         "consistency": 0.0, "span_count": 0.0,
                                         "source_diversity": 0.0}},
            "evidence": [],
            "source_document": trace_index.source_document,
            "reason": trail["reason"],
            "audit_trail": trail["stages"],
        }

    # Deterministic span selection (Hard Evidence Lock). HYBRID MODE: the LLM
    # client is deliberately NOT passed here — evidence selection must never be
    # influenced by an AI. select_spans uses rule-based keyword overlap only.
    selected_ids = select_spans(theme, candidates, client=None)
    selected_any = len(selected_ids) > 0
    cand_by_id = {c["span_id"]: c for c in candidates}

    scored_spans = []
    validated_spans = []

    for sid in selected_ids:
        cand = cand_by_id.get(sid)
        if cand is None:
            continue

        sc = span_score(
            semantic_similarity=cand["semantic_similarity"],
            theme=theme,
            span_text=cand["text"],
            retrieval_rank_score=cand["retrieval_rank_score"],
        )

        # Definition down-weighting (Problem C): definitions are context, not
        # findings. Apply ×0.60 AND hard-cap the score just below the "Strong
        # Evidence" badge threshold, so a definition can NEVER read as Strong.
        etype = _classify_type(cand["text"], cand.get("source_document", ""))
        if is_enabled("definition_downweight") and etype.get("label") == "Definition":
            from config.thresholds import STRENGTH_STRONG
            sc["final_score"] = round(sc["final_score"] * DEFINITION_SCORE_FACTOR, 4)
            # Hard cap: keep strictly below the Strong badge cut-point.
            sc["final_score"] = min(sc["final_score"], STRENGTH_STRONG - 0.01)
            if sc["final_score"] < 0.40:
                sc["tier"] = "discard"
            else:
                sc["tier"] = "weak"

        record_span = {
            "span_id": sid, "text": cand["text"], "page_number": cand["page_number"],
            "source_document": cand.get("source_document"),
            "final_score": sc["final_score"], "tier": sc["tier"],
            "breakdown": sc["breakdown"],
        }

        if sc["tier"] == "discard":
            scored_spans.append(record_span)
            continue

        # Deterministic adversarial review. HYBRID MODE: client NOT passed —
        # the support/over-interpretation/context judgement stays rule-based.
        review = adversarial_review(theme, cand["text"], client=None)
        record_span["adversarial"] = {"q1": review["q1"], "q2": review["q2"], "q3": review["q3"]}
        record_span["adversarial_result"] = review["result"]
        scored_spans.append(record_span)

        if review["result"] == "Reject":
            continue

        validated_spans.append({
            "span_id": sid, "text": cand["text"], "page_number": cand["page_number"],
            "source_document": cand.get("source_document"),
            "span_score": sc["final_score"], "tier": sc["tier"],
            "breakdown": sc["breakdown"],
            "adversarial": record_span["adversarial"],
            "adversarial_result": review["result"],
        })

    contradiction = detect_contradiction(validated_spans) if validated_spans else False

    distinct_sources = len({v["source_document"] for v in validated_spans if v.get("source_document")})
    distinct_sources = max(distinct_sources, 1)
    conf = confidence_score(validated_spans, source_count=distinct_sources)
    conf["percent"] = round(conf["score"] * 100)

    status = final_status(
        retrieved_any=retrieved_any, selected_any=selected_any,
        validated_spans=validated_spans, confidence_band=conf["band"],
        contradiction=contradiction,
    )

    if status == "PARTIALLY SUPPORTED":
        conf["partial_strength"] = partial_strength(conf["score"], validated_spans)

    trail = build_audit_trail(
        retrieved_count=len(candidates), selected_count=len(selected_ids),
        scored_spans=scored_spans, validated_spans=validated_spans,
        contradiction=contradiction, status=status,
    )

    return {
        "theme": theme,
        "status": status,
        "confidence": conf,
        "evidence": [
            {
                "span_text": v["text"],
                "page_number": v["page_number"],
                "source_document": v.get("source_document"),
                "source_label": clean_source_label(v.get("source_document"), v["page_number"]),
                "span_score": v["span_score"],
                "strength": evidence_strength(v["span_score"]),
                "evidence_type": _classify_type(v["text"], v.get("source_document", "")),
                "score_breakdown": v["breakdown"],
                "adversarial": v["adversarial"],
                "adversarial_result": v["adversarial_result"],
            }
            for v in validated_spans
        ],
        "source_document": trace_index.source_document,
        "reason": trail["reason"],
        "audit_trail": trail["stages"],
    }


def run_pipeline(sources, themes=None, auto_discover=False) -> dict:
    """Loads sources (single or pooled), optionally discovers themes, analyses."""
    client = _get_client()
    # HYBRID MODE: a live client only enables LLM theme synthesis. All
    # verification (selection, scoring, adversarial review, confidence,
    # contradiction, status) stays deterministic regardless.
    mode = "HYBRID (LLM themes + deterministic engine)" if client else "MOCK (fully deterministic)"

    if isinstance(sources, str):
        sources = [sources]

    index_json = load_source(sources[0]) if len(sources) == 1 else load_multiple(sources)
    trace_index = TraceIndex(index_json)

    discovered = []
    if (auto_discover or not themes) and is_enabled("auto_theme"):
        discovered = discover_themes(index_json, client=client)
        if not themes:
            themes = discovered

    results = [analyse_theme(theme, trace_index, client) for theme in (themes or [])]

    return {
        "trace_ai_version": "0.6",
        "mode": mode,
        "source_document": index_json["source_document"],
        "document_count": index_json.get("document_count", 1),
        "chunk_count": index_json["chunk_count"],
        "themes_analysed": len(themes or []),
        "discovered_themes": discovered,
        "findings": results,
    }
