import pytest

from callops.models import Severity
from callops.qos import THRESHOLDS, compute_mos


def test_mos_perfect_network_is_near_max() -> None:
    assert compute_mos(rtt_ms=20, jitter_ms=1, loss_pct=0) == pytest.approx(4.4, abs=0.05)


def test_mos_degrades_with_loss_and_delay() -> None:
    good = compute_mos(60, 5, 0.2)
    lossy = compute_mos(60, 5, 8)
    slow = compute_mos(800, 5, 0.2)
    assert good > lossy and good > slow
    assert lossy < 3.6


def test_mos_is_clamped() -> None:
    assert 1.0 <= compute_mos(5000, 500, 100) <= 4.5


@pytest.mark.parametrize(
    ("metric", "value", "expected"),
    [
        ("packet_loss_pct", 0.5, Severity.OK),
        ("packet_loss_pct", 2.0, Severity.WARNING),
        ("packet_loss_pct", 6.0, Severity.CRITICAL),
        ("rtt_ms", 350, Severity.WARNING),
        ("mos", 4.2, Severity.OK),
        ("mos", 3.5, Severity.WARNING),
        ("mos", 2.9, Severity.CRITICAL),
    ],
)
def test_threshold_classification(metric: str, value: float, expected: Severity) -> None:
    assert THRESHOLDS[metric].classify(value) == expected
