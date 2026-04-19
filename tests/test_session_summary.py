"""Tests for session summary aggregation (core.session_summary) and storage lifecycle."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

from core.session import Session
from core.session_summary import summarize_snapshots
from core.storage import SessionStorage


class TestSummaryAggregation:
    def test_empty_snapshots(self) -> None:
        result = summarize_snapshots([])
        assert result["snapshot_count"] == 0
        assert result["rssi"] == {}
        assert result["ping"] == {}

    def test_rssi_avg10_preferred_over_signal(self) -> None:
        snaps = [
            {"rssi_avg10": -60, "signal": -75, "avg_ms": 10.0, "loss": 0.0},
            {"rssi_avg10": -62, "signal": -77, "avg_ms": 12.0, "loss": 0.0},
        ]
        result = summarize_snapshots(snaps)
        assert result["rssi"]["avg"] == pytest.approx(-61.0, abs=0.2)

    def test_signal_fallback_when_no_avg10(self) -> None:
        snaps = [{"signal": -70, "avg_ms": 15.0, "loss": 0.0}]
        result = summarize_snapshots(snaps)
        assert result["rssi"]["min"] == -70.0
        assert result["rssi"]["max"] == -70.0

    def test_mixed_avg10_and_signal_fallback(self) -> None:
        snaps = [
            {"rssi_avg10": -60, "signal": -75},
            {"signal": -80},
        ]
        result = summarize_snapshots(snaps)
        assert result["rssi"]["min"] == -80.0
        assert result["rssi"]["max"] == -60.0

    def test_ping_min_max_avg(self) -> None:
        snaps = [{"avg_ms": v} for v in [10.0, 20.0, 30.0]]
        result = summarize_snapshots(snaps)
        assert result["ping"]["min"] == 10.0
        assert result["ping"]["max"] == 30.0
        assert result["ping"]["avg"] == 20.0

    def test_loss_aggregation(self) -> None:
        snaps = [{"loss": 0.0}, {"loss": 5.0}, {"loss": 10.0}]
        result = summarize_snapshots(snaps)
        assert result["loss"]["min"] == 0.0
        assert result["loss"]["max"] == 10.0
        assert result["loss"]["avg"] == pytest.approx(5.0, abs=0.1)

    def test_alert_counts(self) -> None:
        snaps = [
            {"alerts": {"level": "warning"}},
            {"alerts": {"level": "critical"}},
            {"alerts": {"level": "warning"}},
            {"alerts": {"level": "ok"}},
            {},
        ]
        result = summarize_snapshots(snaps)
        assert result["alerts"]["warning"] == 2
        assert result["alerts"]["critical"] == 1

    def test_spike_event_count(self) -> None:
        snaps = [{"avg_ms": 10.0}]
        result = summarize_snapshots(snaps, spike_events=[{}, {}, {}])
        assert result["spike_event_count"] == 3

    def test_none_fields_excluded_from_aggregation(self) -> None:
        snaps = [
            {"avg_ms": None, "loss": None, "rssi_avg10": None, "signal": None},
            {"avg_ms": 20.0, "loss": 2.0, "rssi_avg10": -65},
        ]
        result = summarize_snapshots(snaps)
        assert result["ping"]["avg"] == 20.0
        assert result["rssi"]["avg"] == -65.0
        assert result["loss"]["avg"] == 2.0


class TestStorageSessionLifecycle:
    def test_end_session_sets_ended_at(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            db = str(Path(d) / "sessions.db")
            st = SessionStorage(db_path=db)
            sess = Session(customer_name="Lifecycle Co")
            st.save_session(sess)
            before = time.time()
            st.end_session(sess.id)

            deadline = time.monotonic() + 3.0
            row = None
            while time.monotonic() < deadline:
                time.sleep(0.05)
                if st._conn:
                    cur = st._conn.execute("SELECT ended_at FROM sessions WHERE id=?", (sess.id,))
                    row = cur.fetchone()
                    if row and row[0] is not None:
                        break

            st.close()
            assert row is not None
            assert row[0] >= before

    def test_update_tags_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            db = str(Path(d) / "sessions.db")
            st = SessionStorage(db_path=db)
            sess = Session(customer_name="Tags Co")
            st.save_session(sess)
            st.update_tags(sess.id, ["ISP Issue", "Resolved"])

            deadline = time.monotonic() + 3.0
            row = None
            while time.monotonic() < deadline:
                time.sleep(0.05)
                if st._conn:
                    cur = st._conn.execute("SELECT tags FROM sessions WHERE id=?", (sess.id,))
                    row = cur.fetchone()
                    if row and row[0]:
                        break

            st.close()
            assert row is not None
            assert set(row[0].split(",")) == {"ISP Issue", "Resolved"}

    def test_update_notes_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            db = str(Path(d) / "sessions.db")
            st = SessionStorage(db_path=db)
            sess = Session(customer_name="Notes Co")
            st.save_session(sess)
            st.update_notes(sess.id, "Follow up needed")

            deadline = time.monotonic() + 3.0
            row = None
            while time.monotonic() < deadline:
                time.sleep(0.05)
                if st._conn:
                    cur = st._conn.execute("SELECT notes FROM sessions WHERE id=?", (sess.id,))
                    row = cur.fetchone()
                    if row and row[0]:
                        break

            st.close()
            assert row is not None
            assert row[0] == "Follow up needed"

    def test_snapshot_blob_size_guard(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            db = str(Path(d) / "sessions.db")
            st = SessionStorage(db_path=db)
            sess = Session(customer_name="Blob Co")
            st.save_session(sess)
            oversized = {"data": "x" * 1_100_000}
            st.save_snapshot(sess.id, "stability", oversized)

            time.sleep(0.2)
            rows = st.get_snapshots(sess.id, "stability")
            st.close()
            assert rows == []
