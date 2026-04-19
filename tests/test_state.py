"""Tests for thread-safe state singletons: SessionState throttles and RssiState averaging."""

from __future__ import annotations

import time

import pytest

from web.backend.state import RssiState, SessionState


# ── SessionState ──────────────────────────────────────────────────────────────

class TestSessionStateThrottles:
    def test_no_session_never_snapshots(self) -> None:
        s = SessionState()
        assert not s.should_snapshot()
        assert not s.should_event_snapshot()

    def test_first_snapshot_fires_immediately(self) -> None:
        s = SessionState()
        s.set("abc")
        assert s.should_snapshot(interval=15.0)

    def test_first_event_fires_immediately(self) -> None:
        s = SessionState()
        s.set("abc")
        assert s.should_event_snapshot(min_gap=5.0)

    def test_snapshot_throttled_after_mark(self) -> None:
        s = SessionState()
        s.set("abc")
        s.mark_snapshot()
        assert not s.should_snapshot(interval=15.0)

    def test_event_throttled_after_mark(self) -> None:
        s = SessionState()
        s.set("abc")
        s.mark_event_snapshot()
        assert not s.should_event_snapshot(min_gap=5.0)

    def test_snapshot_fires_after_interval(self) -> None:
        s = SessionState()
        s.set("abc")
        s.mark_snapshot()
        assert not s.should_snapshot(interval=0.01)
        time.sleep(0.02)
        assert s.should_snapshot(interval=0.01)

    def test_event_fires_after_gap(self) -> None:
        s = SessionState()
        s.set("abc")
        s.mark_event_snapshot()
        assert not s.should_event_snapshot(min_gap=0.01)
        time.sleep(0.02)
        assert s.should_event_snapshot(min_gap=0.01)

    def test_set_resets_throttles(self) -> None:
        s = SessionState()
        s.set("abc")
        s.mark_snapshot()
        s.mark_event_snapshot()
        # Both throttled
        assert not s.should_snapshot(interval=15.0)
        assert not s.should_event_snapshot(min_gap=5.0)
        # New session resets both throttles
        s.set("xyz")
        assert s.should_snapshot(interval=15.0)
        assert s.should_event_snapshot(min_gap=5.0)

    def test_set_none_clears_active_session(self) -> None:
        s = SessionState()
        s.set("abc")
        s.set(None)
        assert s.get() is None
        assert not s.should_snapshot()
        assert not s.should_event_snapshot()


# ── RssiState ─────────────────────────────────────────────────────────────────

class TestRssiState:
    def test_empty_returns_none(self) -> None:
        r = RssiState()
        avg10, stddev = r.stats()
        assert avg10 is None
        assert stddev is None

    def test_single_value_no_stddev(self) -> None:
        r = RssiState()
        r.record(-65)
        avg10, stddev = r.stats()
        assert avg10 == -65.0
        assert stddev is None

    def test_avg10_uses_last_ten(self) -> None:
        r = RssiState(maxlen=20)
        for _ in range(5):
            r.record(-80)
        for _ in range(10):
            r.record(-60)
        avg10, _ = r.stats()
        assert avg10 == -60.0

    def test_none_values_excluded_from_avg(self) -> None:
        r = RssiState()
        r.record(-70)
        r.record(None)
        r.record(-80)
        avg10, _ = r.stats()
        assert avg10 == pytest.approx(-75.0, abs=0.2)

    def test_all_none_returns_none(self) -> None:
        r = RssiState()
        r.record(None)
        r.record(None)
        avg10, stddev = r.stats()
        assert avg10 is None
        assert stddev is None

    def test_stddev_uniform_signal(self) -> None:
        r = RssiState()
        for _ in range(5):
            r.record(-65)
        _, stddev = r.stats()
        assert stddev == 0.0
