"""Property-based checks for sanitize + ping stats (Hypothesis)."""

from __future__ import annotations

import math
import time
from typing import List, Optional

from hypothesis import given
from hypothesis import strategies as st

from collectors.ping_collector import stats_from_rtt_history
from core.sanitize import (
    RSSI_MAX,
    RSSI_MIN,
    RTT_MAX_MS,
    RTT_MIN_MS,
    sanitize_loss,
    sanitize_ping,
    sanitize_rssi,
    sanitize_rtt,
    sanitize_wifi,
)

# Narrow RSSI range for faster shrinking
rssi_int = st.integers(min_value=RSSI_MIN, max_value=RSSI_MAX)
rssi_bad = st.one_of(st.none(), st.integers(max_value=RSSI_MIN - 1), st.integers(min_value=RSSI_MAX + 1))


@given(rssi_int)
def test_sanitize_rssi_roundtrip(rssi: int) -> None:
    assert sanitize_rssi(rssi) == rssi


@given(rssi_bad)
def test_sanitize_rssi_invalid_none(rssi: Optional[int]) -> None:
    assert sanitize_rssi(rssi) is None


@given(st.floats(min_value=RTT_MIN_MS, max_value=RTT_MAX_MS, allow_nan=False))
def test_sanitize_rtt_roundtrip(rtt: float) -> None:
    out = sanitize_rtt(rtt)
    assert out is not None
    assert math.isclose(out, float(rtt), rel_tol=0, abs_tol=1e-6)


@given(st.floats(min_value=-1e9, max_value=1e9, allow_nan=False))
def test_sanitize_loss_always_in_range(x: float) -> None:
    v = sanitize_loss(x)
    assert 0.0 <= v <= 100.0


@given(st.lists(st.one_of(st.none(), st.floats(0.1, 500.0, allow_nan=False)), max_size=40))
def test_stats_loss_percent_bounded(hist: List[Optional[float]]) -> None:
    s = stats_from_rtt_history(hist)
    assert 0.0 <= s["loss_pct"] <= 100.0


@given(st.floats(min_value=0.0, max_value=100.0, allow_nan=False))
def test_sanitize_ping_loss_clamp(loss: float) -> None:
    p = sanitize_ping({"loss_pct": loss, "ts": time.time()})
    assert 0.0 <= p["loss_pct"] <= 100.0


@given(
    rssi_int,
    st.floats(min_value=time.time() - 86400, max_value=time.time(), allow_nan=False),
)
def test_sanitize_wifi_stale_monotone(rssi: int, ts: float) -> None:
    """Older timestamps (smaller ts) should not be *less* stale than newer for same now."""
    c_old = sanitize_wifi({"rssi_dbm": rssi, "ssid": "x"}, ts=ts - 100.0)
    c_new = sanitize_wifi({"rssi_dbm": rssi, "ssid": "x"}, ts=ts)
    # If new is stale, old must be stale too (age is larger for old)
    if c_new["_stale"]:
        assert c_old["_stale"] is True
