"""Unit tests for analysis.recommendations."""

from __future__ import annotations

from analysis.recommendations import recommend_from_connection, recommend_from_scan


def test_recommend_poor_signal_mentions_weak() -> None:
    tips = recommend_from_connection({"rssi_dbm": -80, "ssid": "TestNet", "noise_dbm": -90})
    assert tips and "weak" in tips[0].lower()


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


def test_recommend_from_scan_empty_when_no_channel() -> None:
    assert recommend_from_scan([{"channel": 1}], my_channel=None) == []
