"""
TRACE-AI — Verification & Decision Engine (core/verification.py)

This is where the RULE ENGINE decides the final status. AI components (span
selection, adversarial review) only *suggest*; the final VERIFIED / PARTIALLY
SUPPORTED / WEAK EVIDENCE / BLOCKED / CONFLICTING / INSUFFICIENT decision is made
here by deterministic rules (DO #10, DON'T #4).

Also builds the stage-by-stage audit trail (DON'T #9: never remove audit trails)
so every decision is fully traceable.
"""

from config.thresholds import (
    SPAN_STRONG_THRESHOLD, SPAN_WEAK_THRESHOLD, RETRIEVAL_MIN_SCORE,
)


# --- Step 9: Final status (rule engine decides) ----------------------------
def final_status(retrieved_any: bool,
                 selected_any: bool,
                 validated_spans: list[dict],
                 confidence_band: str,
                 contradiction: bool) -> str:
    """
    Maps the full pipeline state to one of six statuses. A confidence band of
    Moderate must NOT read as VERIFIED — that was a credibility bug; these rules
    enforce the research-grade mapping.
    """
    if not retrieved_any:
        return "INSUFFICIENT EVIDENCE"

    if not selected_any or not validated_spans:
        return "BLOCKED"

    if contradiction:
        return "CONFLICTING EVIDENCE"

    has_pass = any(s.get("adversarial_result") == "Pass" for s in validated_spans)

    # High / Medium  -> VERIFIED        (>= 60%, with a passing adversarial review)
    # Moderate       -> PARTIALLY SUPPORTED (45-59%)
    # Weak           -> WEAK EVIDENCE    (25-44%)
    # Very Low       -> BLOCKED          (< 25%)
    if confidence_band in ("High", "Medium") and has_pass:
        return "VERIFIED"
    if confidence_band == "Moderate":
        return "PARTIALLY SUPPORTED"
    if confidence_band == "Weak":
        return "WEAK EVIDENCE"
    if confidence_band == "Very Low":
        return "BLOCKED"

    # High/Medium confidence but only a Weak adversarial result -> partial
    return "PARTIALLY SUPPORTED"


# --- Audit trail (full traceability) ---------------------------------------
def build_audit_trail(retrieved_count: int,
                      selected_count: int,
                      scored_spans: list[dict],
                      validated_spans: list[dict],
                      contradiction: bool,
                      status: str) -> dict:
    """
    Builds a stage-by-stage, auditable explanation of how a theme reached its
    final status. Returns {stages: [...], reason: "..."}.
    """
    stages = []

    stages.append({
        "stage": "1 · Evidence retrieval",
        "outcome": "pass" if retrieved_count > 0 else "fail",
        "detail": (f"{retrieved_count} candidate span(s) above relevance floor "
                   f"({RETRIEVAL_MIN_SCORE})") if retrieved_count > 0
                  else "No spans met the relevance floor — theme not addressed in the document(s).",
    })
    if retrieved_count == 0:
        return {"stages": stages,
                "reason": "INSUFFICIENT EVIDENCE — the theme is not addressed anywhere in the uploaded document(s)."}

    stages.append({
        "stage": "2 · Span selection (Hard Evidence Lock)",
        "outcome": "pass" if selected_count > 0 else "fail",
        "detail": (f"{selected_count} span(s) selected from the closed candidate set."
                   if selected_count > 0
                   else "No candidate span was selected as supporting the theme."),
    })
    if selected_count == 0:
        return {"stages": stages,
                "reason": "BLOCKED — candidates were retrieved, but none were selected as genuinely supporting the theme."}

    discarded = [s for s in scored_spans if s.get("tier") == "discard"]
    kept_by_score = [s for s in scored_spans if s.get("tier") != "discard"]
    score_detail_bits = [f"{s['span_id']}: {s['final_score']} ({s['tier']})" for s in scored_spans]
    stages.append({
        "stage": "3 · Weighted scoring",
        "outcome": "pass" if kept_by_score else "fail",
        "detail": "; ".join(score_detail_bits) +
                  f"  ·  thresholds: strong ≥ {SPAN_STRONG_THRESHOLD}, weak ≥ {SPAN_WEAK_THRESHOLD}",
    })

    reviewed = [s for s in scored_spans if "adversarial_result" in s]
    rejected = [s for s in reviewed if s["adversarial_result"] == "Reject"]
    adv_bits = []
    for s in reviewed:
        a = s.get("adversarial", {})
        adv_bits.append(
            f"{s['span_id']}: {s['adversarial_result']} "
            f"(Q1 {a.get('q1','?')}, Q2 {a.get('q2','?')}, Q3 {a.get('q3','?')})"
        )
    if reviewed:
        stages.append({
            "stage": "4 · Adversarial review",
            "outcome": "pass" if validated_spans else "fail",
            "detail": "; ".join(adv_bits) if adv_bits else "n/a",
        })

    if validated_spans:
        stages.append({
            "stage": "5 · Contradiction scan",
            "outcome": "fail" if contradiction else "pass",
            "detail": ("Opposing conclusions detected across validated spans."
                       if contradiction else "No contradictions among validated spans."),
        })

    # Tailored reason line
    if status == "BLOCKED":
        causes = []
        if discarded:
            lowest = min(s["final_score"] for s in discarded)
            causes.append(f"semantic/score too low (lowest {lowest} < {SPAN_WEAK_THRESHOLD} weak floor)")
        if rejected:
            q_fail = []
            for s in rejected:
                a = s.get("adversarial", {})
                if a.get("q1") == "NO":
                    q_fail.append("Q1 (no direct support)")
                elif a.get("q2") == "YES":
                    q_fail.append("Q2 (over-interpretation)")
                elif a.get("q3") == "NO":
                    q_fail.append("Q3 (context not preserved)")
            if q_fail:
                causes.append("adversarial review failed: " + ", ".join(sorted(set(q_fail))))
            else:
                causes.append("adversarial review rejected the evidence")
        if not causes:
            causes.append("selected evidence did not pass verification")
        reason = "BLOCKED — " + "; ".join(causes) + "."
    elif status == "CONFLICTING EVIDENCE":
        reason = "CONFLICTING EVIDENCE — validated spans support opposing conclusions for this theme."
    elif status == "VERIFIED":
        reason = "VERIFIED — at least one span passed all checks with sufficient confidence."
    elif status == "PARTIALLY SUPPORTED":
        reason = "PARTIALLY SUPPORTED — evidence exists but is weak or low-confidence."
    elif status == "WEAK EVIDENCE":
        reason = "WEAK EVIDENCE — some relevant evidence, but weak and low-confidence."
    else:
        reason = status

    return {"stages": stages, "reason": reason}
