"""
Tests for chart-axis / OCR noise rejection (core/quality_filter.py).

Run:  python3 -m tests.test_chart_noise
"""

from core.quality_filter import is_chart_or_ocr_noise


def test_chart_axis_sequence_rejected():
    """A run of axis numbers mixed with labels is noise, not a sentence."""
    assert is_chart_or_ocr_noise(
        "0 10 20 30 40 50 buying with mortgage private renters") is True


def test_pure_number_run_rejected():
    """Repeated/consecutive numbers (axis ticks) are noise."""
    assert is_chart_or_ocr_noise("40 40 40 35 30 owner occupied") is True


def test_number_heavy_no_verb_rejected():
    """A number-dominated string with no verb is not a finding."""
    assert is_chart_or_ocr_noise("12 18 24 30 households region area") is True


def test_real_statistical_finding_kept():
    """A genuine statistical sentence (numbers + verb) is NOT noise."""
    assert is_chart_or_ocr_noise(
        "Social housing waiting lists rose by 12 percent over the year") is False


def test_real_prose_kept():
    """Plain prose with no numbers is never flagged as noise."""
    assert is_chart_or_ocr_noise(
        "Owner occupation increased steadily across the decade") is False


ALL = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    for t in ALL:
        t()
        print(f"  {t.__name__}: OK")
    print("test_chart_noise: ALL PASSED")
