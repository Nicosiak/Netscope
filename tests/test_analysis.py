"""Tests for analysis.thresholds and analysis.recommendations."""

from __future__ import annotations

import pytest

from analysis.recommendations import recommend_from_connection, recommend_from_scan
from analysis.thresholds import (
    SignalQuality,
    band_from_channel_number,
    classify_ping_ms,
    classify_rssi,
)

# ── Thresholds ────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "rssi,expected",
    [
        (None, SignalQuality.UNKNOWN),
        (-50, SignalQuality.EXCELLENT),
        (-68, SignalQuality.GOOD),
        (-72, SignalQuality.FAIR),
        (-80, SignalQuality.FAIR),
        (-81, SignalQuality.POOR),
    ],
)
def test_classify_rssi_buckets(rssi: int | None, expected: SignalQuality) -> None:
    assert classify_rssi(rssi) == expected


@pytest.mark.parametrize(
    "ping_ms,expected_label",
    [
        (None, "—"),
        (5.0, "Good"),
        (50.0, "OK"),
        (110.0, "High"),
        (120.0, "High"),
    ],
)
def test_classify_ping_ms(ping_ms: float | None, expected_label: str) -> None:
    assert classify_ping_ms(ping_ms)[0] == expected_label


@pytest.mark.parametrize(
    "channel,expected_band",
    [
        (None, None),
        (1, "2.4 GHz"),
        (14, "2.4 GHz"),
        (36, "5 GHz"),
        (149, "5 GHz"),
        (191, "6 GHz"),
        (15, None),
    ],
)
def test_band_from_channel_number(channel: int | None, expected_band: str | None) -> None:
    assert band_from_channel_number(channel) == expected_band


# ── Recommendations ───────────────────────────────────────────────────

def test_recommend_poor_signal_mentions_weak() -> None:
    tips = recommend_from_connection({"rssi_dbm": -82, "ssid": "TestNet", "noise_dbm": -90})
    assert tips and ("weak" in tips[0].lower() or "below" in tips[0].lower())


def test_recommend_good_signal_healthy() -> None:
    tips = recommend_from_connection({"rssi_dbm": -45, "ssid": "TestNet", "noise_dbm": -90})
    assert any("healthy" in t.lower() for t in tips)


def test_recommend_low_snr() -> None:
    tips = recommend_from_connection({"rssi_dbm": -70, "ssid": "X", "noise_dbm": -50})
    assert any("snr" in t.lower() for t in tips)


def test_recommend_from_scan_crowded() -> None:
    rows = [{"channel": 6} for _ in range(8)]
    tips = recommend_from_scan(rows, my_channel=6)
    assert tips and "busy" in tips[0].lower()


def test_recommend_from_scan_no_channel_returns_empty() -> None:
    assert recommend_from_scan([{"channel": 1}], my_channel=None) == []
