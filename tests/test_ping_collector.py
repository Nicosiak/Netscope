"""Unit tests for ping statistics helpers (collector and web backend copy).

Jitter is inter-arrival MAD (mean absolute deviation of consecutive RTT pairs,
resetting across loss events) — NOT population stddev.
"""

from __future__ import annotations

import pytest

from collectors.ping_collector import stats_from_rtt_history
from web.backend.ping_stats import stats_from_rtt_history as web_stats


def test_stats_empty_history() -> None:
    s = stats_from_rtt_history([])
    assert s["min_ms"] is None
    assert s["max_ms"] is None
    assert s["avg_ms"] is None
    assert s["p50_ms"] is None
    assert s["p95_ms"] is None
    assert s["jitter_ms"] is None
    assert s["loss_pct"] == 0.0


def test_stats_all_loss() -> None:
    s = stats_from_rtt_history([None, None, None])
    assert s["loss_pct"] == 100.0
    assert s["min_ms"] is None
    assert s["jitter_ms"] is None


def test_stats_all_success() -> None:
    s = stats_from_rtt_history([10.0, 20.0, 30.0])
    assert s["loss_pct"] == 0.0
    assert s["min_ms"] == 10.0
    assert s["max_ms"] == 30.0
    assert s["avg_ms"] == pytest.approx(20.0)
    # p50: median of [10, 20, 30] = 20
    assert s["p50_ms"] == pytest.approx(20.0)
    # p95: nearest-rank ceil(0.95*3)-1 = ceil(2.85)-1 = 2 → sv[2] = 30
    assert s["p95_ms"] == pytest.approx(30.0)
    # Jitter: inter-arrival MAD — |20-10| + |30-20| / 2 = 10.0
    assert s["jitter_ms"] == pytest.approx(10.0)


def test_stats_p95_not_max_for_large_n() -> None:
    # For n=20, the old formula gave sv[19] (max); nearest-rank gives sv[18].
    # p95 should not equal max when the sample is large enough.
    hist = [float(i) for i in range(1, 21)]  # [1.0 .. 20.0], sorted
    s = stats_from_rtt_history(hist)
    # ceil(0.95 * 20) - 1 = ceil(19.0) - 1 = 18 → sv[18] = 19.0, not 20.0
    assert s["p95_ms"] == pytest.approx(19.0)
    assert s["max_ms"] == pytest.approx(20.0)


def test_stats_single_sample_no_jitter() -> None:
    s = stats_from_rtt_history([5.0])
    assert s["jitter_ms"] is None
    assert s["p50_ms"] == pytest.approx(5.0)
    assert s["p95_ms"] == pytest.approx(5.0)


def test_stats_jitter_two_samples() -> None:
    # inter-arrival MAD: |9-5| / 1 = 4.0
    s = stats_from_rtt_history([5.0, 9.0])
    assert s["jitter_ms"] == pytest.approx(4.0)


def test_stats_jitter_resets_across_loss() -> None:
    # [10, None, 30] — the gap between 10 and 30 spans a loss event.
    # The pair (10→30) must NOT be counted; only consecutive non-loss pairs count.
    # No consecutive valid pairs → jitter is None.
    s = stats_from_rtt_history([10.0, None, 30.0])
    assert s["jitter_ms"] is None
    assert s["loss_pct"] == pytest.approx(100.0 / 3.0)


def test_stats_jitter_with_valid_pairs_and_gaps() -> None:
    # [10, 20, None, 30, 40]
    # Valid pairs: (10→20) diff=10, (30→40) diff=10; gap resets across None.
    # MAD = (10 + 10) / 2 = 10.0
    s = stats_from_rtt_history([10.0, 20.0, None, 30.0, 40.0])
    assert s["jitter_ms"] == pytest.approx(10.0)


def test_stats_p50_even_count() -> None:
    # median of [10, 20] = (10+20)/2 = 15
    s = stats_from_rtt_history([10.0, 20.0])
    assert s["p50_ms"] == pytest.approx(15.0)


def test_stats_mixed_loss() -> None:
    s = stats_from_rtt_history([10.0, None, 10.0])
    assert s["loss_pct"] == pytest.approx(100.0 / 3.0)
    assert s["min_ms"] == 10.0
    assert s["avg_ms"] == 10.0


def test_web_ping_stats_matches_collector() -> None:
    """web/backend/ping_stats must produce identical output to collectors/ping_collector."""
    cases = [
        [],
        [None, None],
        [10.0, 20.0, 30.0],
        [10.0, None, 10.0],
        [5.0, 9.0],
        [10.0, 20.0, None, 30.0, 40.0],
    ]
    for hist in cases:
        assert web_stats(hist) == stats_from_rtt_history(hist), f"mismatch for {hist}"
