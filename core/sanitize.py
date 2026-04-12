"""Data sanitization — validates collector output before it hits the UI."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

RSSI_MIN, RSSI_MAX = -120, 0
RTT_MIN_MS, RTT_MAX_MS = 0.1, 9999.0
LOSS_MIN, LOSS_MAX = 0.0, 100.0
SPEED_MIN_MBPS = 0.0
CHANNEL_MIN, CHANNEL_MAX = 1, 200

WIFI_STALE_S = 6.0
PING_STALE_S = 4.0


def sanitize_rssi(rssi: Any) -> Optional[int]:
    if rssi is None:
        return None
    try:
        v = int(rssi)
        return v if RSSI_MIN <= v <= RSSI_MAX else None
    except (TypeError, ValueError):
        return None


def sanitize_rtt(rtt_ms: Any) -> Optional[float]:
    if rtt_ms is None:
        return None
    try:
        v = float(rtt_ms)
        return v if RTT_MIN_MS <= v <= RTT_MAX_MS else None
    except (TypeError, ValueError):
        return None


def sanitize_loss(loss_pct: Any) -> float:
    try:
        v = float(loss_pct)
        return max(LOSS_MIN, min(LOSS_MAX, v))
    except (TypeError, ValueError):
        return 0.0


def sanitize_wifi(conn: Dict[str, Any], ts: Optional[float] = None) -> Dict[str, Any]:
    now = time.time()
    age = (now - ts) if ts is not None else 0.0
    stale = age > WIFI_STALE_S

    cleaned = dict(conn)
    cleaned["rssi_dbm"] = sanitize_rssi(conn.get("rssi_dbm"))
    cleaned["noise_dbm"] = sanitize_rssi(conn.get("noise_dbm"))

    valid = cleaned["rssi_dbm"] is not None or conn.get("ssid") is not None
    cleaned["_valid"] = valid
    cleaned["_stale"] = stale
    cleaned["_ts"] = ts if ts is not None else now
    return cleaned


def sanitize_ping(payload: Dict[str, Any]) -> Dict[str, Any]:
    now = time.time()
    raw_ts = payload.get("ts")
    stale = (now - float(raw_ts)) > PING_STALE_S if raw_ts is not None else False

    cleaned = dict(payload)
    cleaned["rtt_ms"] = sanitize_rtt(payload.get("rtt_ms"))
    cleaned["min_ms"] = sanitize_rtt(payload.get("min_ms"))
    cleaned["max_ms"] = sanitize_rtt(payload.get("max_ms"))
    cleaned["avg_ms"] = sanitize_rtt(payload.get("avg_ms"))
    cleaned["jitter_ms"] = sanitize_rtt(payload.get("jitter_ms"))
    cleaned["loss_pct"] = sanitize_loss(payload.get("loss_pct", 0))

    hist = payload.get("history_ms") or []
    cleaned["history_ms"] = [sanitize_rtt(v) for v in hist]

    cleaned["_valid"] = True
    cleaned["_stale"] = stale
    return cleaned
