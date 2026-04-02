"""Unit tests for analysis.thresholds (no network, no CoreWLAN)."""

from __future__ import annotations

from analysis.thresholds import (
    SignalQuality,
    band_from_channel_number,
    classify_ping_ms,
    classify_rssi,
)


def test_classify_rssi_buckets() -> None:
    assert classify_rssi(None) == SignalQuality.UNKNOWN
    assert classify_rssi(-40) == SignalQuality.EXCELLENT
    assert classify_rssi(-60) == SignalQuality.GOOD
    assert classify_rssi(-70) == SignalQuality.FAIR
    assert classify_rssi(-80) == SignalQuality.POOR


def test_classify_ping_ms() -> None:
    assert classify_ping_ms(None)[0] == "—"
    label, _ = classify_ping_ms(5.0)
    assert label == "Good"
    assert classify_ping_ms(50.0)[0] == "OK"
    assert classify_ping_ms(100.0)[0] == "High"


def test_band_from_channel_number() -> None:
    assert band_from_channel_number(None) is None
    assert band_from_channel_number(1) == "2.4 GHz"
    assert band_from_channel_number(14) == "2.4 GHz"
    assert band_from_channel_number(36) == "5 GHz"
    assert band_from_channel_number(149) == "5 GHz"
    assert band_from_channel_number(191) == "6 GHz"
    assert band_from_channel_number(15) is None
