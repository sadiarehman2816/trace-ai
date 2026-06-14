"""
Tests for metadata cleaning (core/quality_filter.py).

Run:  python3 -m tests.test_metadata
or:   python3 -m pytest tests/test_metadata.py
"""

from core.quality_filter import (
    clean_evidence_text, strip_metadata_references,
    truncate_at_metadata_marker, contains_metadata_reference,
)


def test_end_of_sentence_reference_truncated():
    """A reference at the end of a sentence is removed, content kept."""
    out = clean_evidence_text(
        "Owner occupation rose over the decade, Figure 1.9 and Annex Table 1.6.")
    assert "Figure" not in out
    assert "Annex" not in out
    assert "Owner occupation rose over the decade" in out


def test_mid_sentence_reference_keeps_content():
    """A reference mid-sentence is stripped but trailing real content survives."""
    out = clean_evidence_text("As shown in Appendix B, tenure varies by region.")
    assert "Appendix" not in out
    assert "tenure varies by region" in out.lower()


def test_source_and_note_clauses_dropped():
    """Source:/Note: clauses are removed, the finding is kept."""
    out = clean_evidence_text("Arrears rose to 8 percent. Source: EHS 2024.")
    assert "Source" not in out
    assert "Arrears rose" in out
    out2 = clean_evidence_text("Affordability worsened in London. Note: provisional.")
    assert "Note" not in out2
    assert "Affordability worsened" in out2


def test_metadata_only_span_becomes_empty():
    """A span that is only a reference is reduced to nothing."""
    assert clean_evidence_text("Figure 1.9 and Annex Table 1.6").strip(" .") == ""


def test_letter_only_reference_detected():
    """Appendix B / Annex A (letter, no number) are caught."""
    assert contains_metadata_reference("see Appendix B") is True
    assert contains_metadata_reference("Rents rose 8% over the year.") is False


def test_hard_truncate_helper():
    """truncate_at_metadata_marker cuts when >=4 words precede the marker."""
    out = truncate_at_metadata_marker(
        "Owner occupation rose sharply this decade, Figure 2.1.")
    assert "Figure" not in out


def test_normal_sentence_untouched():
    """A clean sentence with no metadata is returned unchanged in substance."""
    s = "Rents rose 8% over the year."
    assert clean_evidence_text(s).startswith("Rents rose 8%")


def test_glued_header_is_split():
    """Stability fix: an ALL-CAPS heading glued to a finding (PDF newline loss)
    is separated so the heading doesn't pollute the evidence span."""
    from core.chunking import split_into_sentences
    out = split_into_sentences("NHS WORKFORCE STATISTICS Staff vacancies rose. "
                               "The vacancy rate reached 9.2%.")
    # The heading must be its own span, not glued to the finding
    assert any("Staff vacancies rose" in s and "STATISTICS" not in s for s in out)


def test_glued_chart_axis_is_split():
    """Stability fix: a chart-axis number run glued to a real finding is split,
    so the finding survives instead of being rejected as chart noise."""
    from core.chunking import split_into_sentences
    out = split_into_sentences(
        "0 10 20 30 40 50 owner occupied social rented "
        "The number of first time buyers increased to 761,000.")
    assert any("first time buyers increased" in s for s in out)


ALL = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    for t in ALL:
        t()
        print(f"  {t.__name__}: OK")
    print("test_metadata: ALL PASSED")
