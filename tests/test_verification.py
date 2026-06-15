"""
Tests for the verification engine (core/verification.py) and the HYBRID trust
boundary (models/adversarial_review.py).

The rule engine maps pipeline state to a final status; AI never decides status.

Run:  python3 -m tests.test_verification
"""

from core.verification import final_status, build_audit_trail


def test_no_retrieval_is_insufficient():
    """No candidates -> INSUFFICIENT EVIDENCE (says 'not addressed')."""
    assert final_status(False, False, [], "None", False) == "INSUFFICIENT EVIDENCE"


def test_retrieved_but_unvalidated_is_blocked():
    """Retrieved but nothing validated -> BLOCKED."""
    assert final_status(True, False, [], "Moderate", False) == "BLOCKED"


def test_opposing_polarity_is_conflicting():
    """Contradiction among validated spans -> CONFLICTING EVIDENCE."""
    spans = [{"adversarial_result": "Pass"}]
    assert final_status(True, True, spans, "High", True) == "CONFLICTING EVIDENCE"


def test_high_confidence_is_verified():
    """High band + passing review -> VERIFIED."""
    spans = [{"adversarial_result": "Pass"}]
    assert final_status(True, True, spans, "High", False) == "VERIFIED"


def test_moderate_is_partial_not_verified():
    """Moderate band must read as PARTIALLY SUPPORTED, never VERIFIED."""
    spans = [{"adversarial_result": "Pass"}]
    assert final_status(True, True, spans, "Moderate", False) == "PARTIALLY SUPPORTED"


def test_weak_band_is_weak_evidence():
    """Weak band -> WEAK EVIDENCE."""
    spans = [{"adversarial_result": "Pass"}]
    assert final_status(True, True, spans, "Weak", False) == "WEAK EVIDENCE"


def test_audit_trail_always_built():
    """Every decision produces a structured audit trail with a reason."""
    spans = [{"adversarial_result": "Pass"}]
    trail = build_audit_trail(3, 1, [], spans, False, "VERIFIED")
    assert "stages" in trail and "reason" in trail
    assert len(trail["stages"]) >= 1


def test_hybrid_boundary_no_llm_in_verification():
    """The LLM is NEVER called for evidence selection or adversarial review,
    even if a client is passed in. A trap client raises if ever invoked."""
    from models.adversarial_review import select_spans, adversarial_review

    class TrapClient:
        class messages:
            @staticmethod
            def create(*a, **k):
                raise AssertionError("LLM called for verification — HYBRID violated")

    cands = [{"span_id": "s1", "text": "Waiting lists rose 12 percent",
              "semantic_similarity": 0.6, "retrieval_rank_score": 1.0}]
    # Must not raise (i.e. must not touch the LLM)
    select_spans("housing", cands, client=TrapClient())
    adversarial_review("housing", "Waiting lists rose 12 percent", client=TrapClient())


def test_contradiction_detects_rose_vs_fell():
    """QA Bug 3: 'rose' (past tense) must register as a positive direction so a
    'rose vs fell' pair is flagged as contradictory, not silently averaged."""
    from core.contradiction import polarity, detect_contradiction
    assert polarity("the unemployment rate rose to 5.8% in Q3") == "positive"
    assert polarity("the unemployment rate fell to 4.9% by year end") == "negative"
    assert detect_contradiction([
        {"text": "the rate rose to 5.8% in Q3"},
        {"text": "the rate fell to 4.9% by year end"},
    ]) is True


ALL = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    for t in ALL:
        t()
        print(f"  {t.__name__}: OK")
    print("test_verification: ALL PASSED")
