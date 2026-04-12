"""Unit tests for ping statistics helpers (collector and web backend copy)."""

from __future__ import annotations

import statistics

import pytest

from collectors.ping_collector import stats_from_rtt_history
from web.backend.ping_stats import stats_from_rtt_history as web_stats


def test_stats_empty_history() -> None:
    s = stats_from_rtt_history([])
    assert s["min_ms"] is None
    assert s["max_ms"] is None
    assert s["avg_ms"] is None
    assert s["jitter_ms"] is None
    assert s["loss_pct"] == 0.0


def test_stats_all_loss() -> None:
    s = stats_from_rtt_history([None, None, None])
    assert s["loss_pct"] == 100.0
    assert s["min_ms"] is None


def test_stats_all_success() -> None:
    s = stats_from_rtt_history([10.0, 20.0, 30.0])
    assert s["loss_pct"] == 0.0
    assert s["min_ms"] == 10.0
    assert s["max_ms"] == 30.0
    assert s["avg_ms"] == 20.0
    assert s["jitter_ms"] == pytest.approx(statistics.pstdev([10.0, 20.0, 30.0]))


def test_stats_mixed_loss() -> None:
    s = stats_from_rtt_history([10.0, None, 10.0])
    assert s["loss_pct"] == pytest.approx(100.0 / 3.0)
    assert s["min_ms"] == 10.0
    assert s["avg_ms"] == 10.0


def test_stats_jitter_requires_two_samples() -> None:
    assert stats_from_rtt_history([5.0])["jitter_ms"] is None
    s = stats_from_rtt_history([5.0, 9.0])
    assert s["jitter_ms"] == pytest.approx(2.0)


def test_web_ping_stats_matches_collector() -> None:
    """web/backend/ping_stats must produce identical output to collectors/ping_collector."""
    cases = [
        [],
        [None, None],
        [10.0, 20.0, 30.0],
        [10.0, None, 10.0],
        [5.0, 9.0],
    ]
    for hist in cases:
        assert web_stats(hist) == stats_from_rtt_history(hist), f"mismatch for {hist}"
