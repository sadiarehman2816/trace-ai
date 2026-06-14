"""
Tests for definition detection and down-weighting (Problem C).

Definitions are context, not findings: they are detected, scored ×0.60, and
must never reach "Strong Evidence".

Run:  python3 -m tests.test_definition_filter
"""

from core.quality_filter import classify_evidence_type
from config.thresholds import DEFINITION_SCORE_FACTOR, STRENGTH_STRONG


def test_is_a_definition_detected():
    """'X is a means-tested benefit' is a definition."""
    assert classify_evidence_type(
        "Housing support is a means-tested benefit for households")["label"] == "Definition"


def test_includes_definition_detected():
    """'X includes households who...' is a definition, not a finding."""
    assert classify_evidence_type(
        "Owner occupation includes households who own their home")["label"] == "Definition"


def test_statistical_finding_not_definition():
    """A real statistical sentence is not classified as a definition."""
    label = classify_evidence_type(
        "Social housing waiting lists rose by 12 percent over the year")["label"]
    assert label != "Definition"


def test_definition_factor_is_aggressive():
    """The configured definition down-weight is <= 0.60."""
    assert DEFINITION_SCORE_FACTOR <= 0.60


def test_definition_capped_below_strong():
    """End-to-end: a definition never surfaces as 'Strong Evidence'."""
    import fitz, os, tempfile
    path = os.path.join(tempfile.gettempdir(), "trace_def_test.pdf")
    doc = fitz.open()
    doc.new_page().insert_textbox(
        fitz.Rect(40, 40, 560, 760),
        "Report. Owner occupation includes households who own their home "
        "outright or with a mortgage across all regions of England today.",
        fontsize=11)
    doc.save(path)
    doc.close()
    try:
        from core.pipeline import run_pipeline
        out = run_pipeline([path], themes=["Owner occupation"])
        for f in out["findings"]:
            for ev in f.get("evidence", []):
                assert ev["strength"]["label"] != "Strong Evidence"
    finally:
        os.remove(path)


ALL = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    for t in ALL:
        t()
        print(f"  {t.__name__}: OK")
    print("test_definition_filter: ALL PASSED")
