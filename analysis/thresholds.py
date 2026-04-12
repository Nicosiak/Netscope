"""RSSI, SNR, and ping thresholds — aligned with Ekahau, UniFi, and 802.11ax (HE) PHY.

Design references (summarized for field use; always validate against your SLA):

* **Ekahau / WLAN design practice:** Primary coverage is often engineered for about
  **-65 dBm to -70 dBm** received; **-67 dBm** is widely cited as a healthy primary
  target for many clients. **SNR ≥ 25 dB** is a common target for reliable higher
  MCS and capacity (noise and co-channel load dependent).

* **Ubiquiti UniFi Help Center:** About **-65 dBm or better** for optimal experience,
  and **-70 dBm or better** for a generally stable connection; **Minimum RSSI** can
  be tuned to improve roaming. **2.4 GHz:** prefer **20 MHz** channel width in dense
  environments; **5 GHz:** often **40 MHz** (dense) vs **80 MHz** (lower density).

* **802.11ax (Wi‑Fi 6 / HE):** MCS indices **0–11** (BPSK through 1024-QAM); realized
  Mbps depends on MCS, channel width, spatial streams, and guard interval — see
  IEEE 802.11ax rate tables or e.g. SemFio / mcsindex.com for numeric maps.
"""

from __future__ import annotations

from enum import Enum
from typing import Tuple

# Hex color constants (inlined from former ui/theme.py — no Tk dependency)
_COLOR_EXCELLENT = "#22c55e"
_COLOR_GOOD      = "#22c55e"
_COLOR_FAIR      = "#f59e0b"
_COLOR_POOR      = "#ef4444"
_COLOR_UNKNOWN   = "#64748b"
_COLOR_PING_GOOD = "#22c55e"
_COLOR_PING_WARN = "#f59e0b"
_COLOR_PING_HIGH = "#ef4444"


class SignalQuality(str, Enum):
    EXCELLENT = "Excellent"
    GOOD = "Good"
    FAIR = "Fair"
    POOR = "Poor"
    UNKNOWN = "Unknown"


# Minimum RSSI (dBm) for each band — numerically larger = stronger signal.
RSSI_MIN_EXCELLENT = -65  # ≥ optimal primary (UniFi “recommended”, Ekahau-style targets)
RSSI_MIN_GOOD = -70      # ≥ stable for typical use (UniFi “stable connection” band)
RSSI_MIN_FAIR = -80     # ≥ marginal; below this is poor for most deployments

# Back-compat names used in older code / comments
RSSI_EXCELLENT = RSSI_MIN_EXCELLENT
RSSI_GOOD = RSSI_MIN_GOOD
RSSI_FAIR = RSSI_MIN_FAIR

# SNR (Ekahau-style design target)
SNR_TARGET_DB = 25       # aim ≥ this for robust higher MCS / capacity
SNR_USABLE_MIN_DB = 20  # below ~20 dB many real-time apps struggle

# 802.11ax HE MCS index range (single-user); for UI copy / tips only
AX_HE_MCS_MIN = 0
AX_HE_MCS_MAX = 11


def classify_rssi(rssi_dbm: int | None) -> SignalQuality:
    if rssi_dbm is None:
        return SignalQuality.UNKNOWN
    if rssi_dbm >= RSSI_MIN_EXCELLENT:
        return SignalQuality.EXCELLENT
    if rssi_dbm >= RSSI_MIN_GOOD:
        return SignalQuality.GOOD
    if rssi_dbm >= RSSI_MIN_FAIR:
        return SignalQuality.FAIR
    return SignalQuality.POOR


def rssi_color_hex(quality: SignalQuality) -> str:
    return {
        SignalQuality.EXCELLENT: _COLOR_EXCELLENT,
        SignalQuality.GOOD: _COLOR_GOOD,
        SignalQuality.FAIR: _COLOR_FAIR,
        SignalQuality.POOR: _COLOR_POOR,
        SignalQuality.UNKNOWN: _COLOR_UNKNOWN,
    }[quality]


PING_GOOD_MS = 30
PING_WARN_MS = 100


def classify_ping_ms(rtt_ms: float | None) -> Tuple[str, str]:
    if rtt_ms is None:
        return "—", _COLOR_UNKNOWN
    if rtt_ms < PING_GOOD_MS:
        return "Good", _COLOR_PING_GOOD
    if rtt_ms < PING_WARN_MS:
        return "OK", _COLOR_PING_WARN
    return "High", _COLOR_PING_HIGH


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
