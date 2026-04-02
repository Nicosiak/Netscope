"""RSSI and ping thresholds for color coding and advice."""

from __future__ import annotations

from enum import Enum
from typing import Tuple


class SignalQuality(str, Enum):
    EXCELLENT = "Excellent"
    GOOD = "Good"
    FAIR = "Fair"
    POOR = "Poor"
    UNKNOWN = "Unknown"


RSSI_EXCELLENT = -55
RSSI_GOOD = -67
RSSI_FAIR = -75


def classify_rssi(rssi_dbm: int | None) -> SignalQuality:
    if rssi_dbm is None:
        return SignalQuality.UNKNOWN
    if rssi_dbm >= RSSI_EXCELLENT:
        return SignalQuality.EXCELLENT
    if rssi_dbm >= RSSI_GOOD:
        return SignalQuality.GOOD
    if rssi_dbm >= RSSI_FAIR:
        return SignalQuality.FAIR
    return SignalQuality.POOR


def rssi_color_hex(quality: SignalQuality) -> str:
    return {
        SignalQuality.EXCELLENT: "#22c55e",
        SignalQuality.GOOD: "#3b82f6",
        SignalQuality.FAIR: "#eab308",
        SignalQuality.POOR: "#ef4444",
        SignalQuality.UNKNOWN: "#6b7280",
    }[quality]


PING_GOOD_MS = 20
PING_WARN_MS = 80


def classify_ping_ms(rtt_ms: float | None) -> Tuple[str, str]:
    """Return (label, hex color)."""
    if rtt_ms is None:
        return "—", "#6b7280"
    if rtt_ms < PING_GOOD_MS:
        return "Good", "#22c55e"
    if rtt_ms < PING_WARN_MS:
        return "OK", "#eab308"
    return "High", "#ef4444"


def band_from_channel_number(channel: int | None) -> str | None:
    if channel is None:
        return None
    if 1 <= channel <= 14:
        return "2.4 GHz"
    if 32 <= channel <= 177:
        return "5 GHz"
    if channel > 190:
        return "6 GHz"
    return None
