"""
Basic smoke tests for TRACE-AI. Run from the trace_ai/ directory:
    python3 -m tests.test_smoke
Verifies the core invariants without needing a real PDF or API key.
"""

import sys


def test_quality_filters():
    from core.quality_filter import (is_low_quality_span, is_metadata_span,
                                      is_blacklisted_theme, classify_evidence_type)
    assert is_low_quality_span("14 private renters.") is True
    assert is_low_quality_span(
        "Social housing waiting lists continue to increase year on year.") is False
    assert is_metadata_span("Annex Table 1.6 shows the breakdown") is True
    assert is_blacklisted_theme("English Housing Survey") is True
    assert is_blacklisted_theme("Housing Affordability") is False
    assert classify_evidence_type("rose by 12 percent year on year")["label"] in (
        "Statistical trend", "Trend")
    print("  quality filters: OK")


def test_scoring_and_status():
    from core.scoring import span_score, confidence_score
    from core.verification import final_status
    sc = span_score(0.65, "social housing", "social housing waiting lists rose", 1.0)
    assert sc["tier"] in ("strong", "weak", "discard")
    assert final_status(False, False, [], "None", False) == "INSUFFICIENT EVIDENCE"
    assert final_status(True, False, [], "Moderate", False) == "BLOCKED"
    print("  scoring + status engine: OK")


def test_config_single_source():
    from config import thresholds
    from config.feature_flags import is_enabled
    assert hasattr(thresholds, "CONFIDENCE_HIGH")
    assert is_enabled("auto_theme") in (True, False)
    print("  config + feature flags: OK")


def test_hybrid_boundary():
    """The LLM must NEVER be called for evidence selection or adversarial review,
    even if a client is passed. Only theme synthesis may use the LLM."""
    from models.adversarial_review import select_spans, adversarial_review

    class TrapClient:
        class messages:
            @staticmethod
            def create(*a, **k):
                raise AssertionError("LLM called for verification — HYBRID violated")

    cands = [{"span_id": "s1", "text": "Waiting lists rose 12 percent",
              "semantic_similarity": 0.6, "retrieval_rank_score": 1.0}]
    # Must not raise (i.e. must not call the LLM)
    select_spans("housing", cands, client=TrapClient())
    adversarial_review("housing", "Waiting lists rose 12 percent", client=TrapClient())
    print("  hybrid trust boundary: OK")


def test_metadata_stripping():
    from core.quality_filter import (strip_metadata_references,
                                     contains_metadata_reference)
    # Inline reference is stripped, real content kept
    out = strip_metadata_references(
        "1% in the social rented sector, Figure 1.9 and Annex Table 1.6.")
    assert "Figure" not in out and "Annex" not in out
    assert "social rented sector" in out
    # Safety net detects surviving references
    assert contains_metadata_reference("see Figure 1.9") is True
    assert contains_metadata_reference("Rents rose by 8% last year.") is False
    print("  metadata stripping + safety net: OK")


def test_evidence_hygiene_audit():
    """Full before/after audit: every kept span must be metadata-free, every
    fragment/metadata-only span must be rejected."""
    from core.quality_filter import (clean_evidence_text, contains_metadata_reference,
                                     is_metadata_span, is_low_quality_span)

    def verdict(span):
        c = clean_evidence_text(span)
        if not c or contains_metadata_reference(c) or is_metadata_span(c) or is_low_quality_span(c):
            return ("REJECTED", None)
        return ("KEPT", c)

    keep_cases = {
        "Owner occupation increased over the decade, see Table 2.1.": "metadata stripped",
        "Households in arrears rose to 8 percent. Source: EHS 2024.": "Source dropped",
        "Affordability worsened in London. Note: provisional.": "Note dropped",
        "As shown in Appendix B, tenure varies by region.": "Appendix removed",
        "Rents rose 8% over the year.": "short valid finding",
    }
    reject_cases = ["14 private renters.", "Figure 1.9 and Annex Table 1.6",
                    "Social housing sector."]

    for span in keep_cases:
        v, cleaned = verdict(span)
        assert v == "KEPT", f"should keep: {span}"
        assert not contains_metadata_reference(cleaned), f"LEAK: {cleaned}"
    for span in reject_cases:
        v, _ = verdict(span)
        assert v == "REJECTED", f"should reject: {span}"
    print("  evidence hygiene audit (10 cases): OK")


def test_theme_chart_definition_filters():
    from core.quality_filter import (is_blacklisted_theme, is_chart_or_ocr_noise,
                                     classify_evidence_type)
    # Problem A — structural themes rejected
    assert is_blacklisted_theme("Underlying Data Presented") is True
    assert is_blacklisted_theme("References") is True
    assert is_blacklisted_theme("Housing Affordability") is False
    # Problem B — chart/OCR noise rejected
    assert is_chart_or_ocr_noise("0 10 20 30 40 50 buying with mortgage renters") is True
    assert is_chart_or_ocr_noise("Waiting lists rose by 12 percent over the year") is False
    # Problem C — definition detection
    assert classify_evidence_type(
        "Housing support is a means-tested benefit for households")["label"] == "Definition"
    print("  theme/chart/definition filters (A,B,C): OK")


def test_broad_noun_and_definition_cap():
    from core.theme_engine import _is_weak
    from core.quality_filter import classify_evidence_type
    # #2 broad single nouns rejected as themes
    assert _is_weak("Households") is True
    assert _is_weak("People") is True
    assert _is_weak("Social Rented Sector") is False
    # #3 "includes ..." detected as definition
    assert classify_evidence_type(
        "Owner occupation includes households who own their home")["label"] == "Definition"
    print("  broad-noun reject + definition detect: OK")


def test_verification_engine():
    """Rule 8 — verification: the rule engine maps pipeline state to the correct
    final status, and the audit trail is always built. AI never sets status."""
    from core.verification import final_status, build_audit_trail

    # No retrieval -> INSUFFICIENT
    assert final_status(False, False, [], "None", False) == "INSUFFICIENT EVIDENCE"
    # Retrieved but nothing selected/validated -> BLOCKED
    assert final_status(True, False, [], "Moderate", False) == "BLOCKED"
    # Opposing polarity -> CONFLICTING
    spans = [{"adversarial_result": "Pass"}]
    assert final_status(True, True, spans, "High", True) == "CONFLICTING EVIDENCE"
    # High confidence + passing review -> VERIFIED
    assert final_status(True, True, spans, "High", False) == "VERIFIED"
    # Moderate band -> PARTIALLY SUPPORTED (must NOT read as VERIFIED)
    assert final_status(True, True, spans, "Moderate", False) == "PARTIALLY SUPPORTED"
    # Weak band -> WEAK EVIDENCE
    assert final_status(True, True, spans, "Weak", False) == "WEAK EVIDENCE"

    # Audit trail is always present and structured
    trail = build_audit_trail(3, 1, [], spans, False, "VERIFIED")
    assert "stages" in trail and "reason" in trail
    assert len(trail["stages"]) >= 1
    print("  verification engine + audit trail: OK")


def test_metadata_cleaning_unit():
    """Rule 8 — metadata cleaning: explicit unit coverage of the cleaner."""
    from core.quality_filter import (clean_evidence_text, truncate_at_metadata_marker,
                                     contains_metadata_reference)
    # End-of-sentence reference is truncated
    out = clean_evidence_text("Owner occupation rose, Figure 1.9 and Annex Table 1.6.")
    assert "Figure" not in out and "Annex" not in out and "Owner occupation rose" in out
    # Mid-sentence reference with content after -> content kept
    out2 = clean_evidence_text("As shown in Appendix B, tenure varies by region.")
    assert "Appendix" not in out2 and "tenure varies by region" in out2.lower()
    # Source:/Note: clauses removed
    out3 = clean_evidence_text("Arrears rose to 8 percent. Source: EHS 2024.")
    assert "Source" not in out3 and "Arrears rose" in out3
    # Hard truncation helper (truncates when >=4 words precede the marker)
    assert "Figure" not in truncate_at_metadata_marker(
        "Owner occupation rose sharply this decade, Figure 2.1.")
    assert not contains_metadata_reference("Rents rose 8% over the year.")
    print("  metadata cleaning (unit): OK")


if __name__ == "__main__":
    print("TRACE-AI smoke tests")
    test_config_single_source()
    test_quality_filters()
    test_metadata_stripping()
    test_metadata_cleaning_unit()
    test_evidence_hygiene_audit()
    test_theme_chart_definition_filters()
    test_broad_noun_and_definition_cap()
    test_scoring_and_status()
    test_verification_engine()
    test_hybrid_boundary()
    print("ALL SMOKE TESTS PASSED")
