"""SessionStorage snapshot roundtrip (uses temp DB, not ~/.netscope)."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from core.session import Session
from core.storage import SessionStorage


def test_get_snapshots_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as d:
        db = str(Path(d) / "test_sessions.db")
        st = SessionStorage(db_path=db)
        sess = Session(customer_name="TestCo")
        st.save_session(sess)
        st.save_snapshot(sess.id, "wifi", {"rssi_dbm": -65, "channel": 36})
        st.save_snapshot(sess.id, "wifi", {"rssi_dbm": -70, "channel": 36})
        st.save_snapshot(sess.id, "ping", {"rtt_ms": 12.5})

        deadline = time.monotonic() + 3.0
        wifi_rows: list = []
        ping_rows: list = []
        while time.monotonic() < deadline and (len(wifi_rows) < 2 or len(ping_rows) < 1):
            time.sleep(0.05)
            wifi_rows = st.get_snapshots(sess.id, "wifi")
            ping_rows = st.get_snapshots(sess.id, "ping")

        st.close()

        assert len(wifi_rows) == 2
        assert wifi_rows[0]["rssi_dbm"] == -65
        assert wifi_rows[1]["rssi_dbm"] == -70
        assert all("ts" in r for r in wifi_rows)

        assert len(ping_rows) == 1
        assert ping_rows[0]["rtt_ms"] == 12.5


def test_get_snapshots_empty() -> None:
    with tempfile.TemporaryDirectory() as d:
        db = str(Path(d) / "empty.db")
        st = SessionStorage(db_path=db)
        sess = Session()
        rows = st.get_snapshots(sess.id, "wifi")
        st.close()
        assert rows == []


def test_session_storage_close_idempotent() -> None:
    with tempfile.TemporaryDirectory() as d:
        db = str(Path(d) / "close.db")
        st = SessionStorage(db_path=db)
        st.close()
        st.close()
