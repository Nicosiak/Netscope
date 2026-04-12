"""WebSocket payload builder.

``build()`` is called from a thread-pool executor every 250 ms and must
be safe for concurrent calls.  All mutable state is accessed through the
thread-safe singletons in ``state``.

Payload schema
--------------
Field            Type              Notes
---------------  ----------------  ------------------------------------
connected        bool              True when Wi-Fi link is up
signal           int | None        RSSI in dBm
rssi_avg10       float | None      Mean of last 10 non-null RSSI samples
rssi_stddev20    float | None      Population std-dev over history window
snr              int | None        signal − noise_floor (dBm)
phy_speed        int | None        Tx rate in Mbps; 0 is a valid value
ping             float | None      Latest RTT in ms
loss             float             Packet-loss % (0.0 when no history)
min_ms           float | None      Min RTT over history
max_ms           float | None      Max RTT over history
avg_ms           float | None      Mean RTT over history
jitter_ms        float | None      Mean deviation over history
ap_name          str | None        SSID (may be None without Location Services)
bssid            str | None        AP MAC address
channel          str | None        Wi-Fi channel number as string
band             str | None        "2.4 GHz" / "5 GHz" / "6 GHz"
phy_mode         str | None        e.g. "802.11ax"
wifi_gen         str               "Wi-Fi 6" etc., or "" if unknown
width            str | None        Channel width, e.g. "80 MHz"
ping_target      str               Current ping destination
ping_history     list[float|None]  Raw RTT history for chart (80 entries)
ts               float             Unix timestamp of this payload
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional

from web.backend.state import ping as ping_state
from web.backend.state import rssi as rssi_state

# ── WiFi connection cache (400 ms TTL) ───────────────────────────
_wifi_lock   = threading.Lock()
_wifi_ts: float = 0.0
_wifi_cache: Dict[str, Any] = {}
_WIFI_TTL = 0.4  # seconds


def _get_wifi() -> Dict[str, Any]:
    global _wifi_ts, _wifi_cache
    now = time.monotonic()
    with _wifi_lock:
        if now - _wifi_ts < _WIFI_TTL and _wifi_cache:
            return _wifi_cache
    from collectors.wifi_collector import fetch_current_connection
    fresh = fetch_current_connection()
    with _wifi_lock:
        _wifi_cache = fresh
        _wifi_ts = time.monotonic()
    return fresh


def _wifi_gen_label(phy_mode: Optional[str]) -> str:
    m = (phy_mode or "").lower()
    if "802.11be" in m or "11be" in m:
        return "Wi-Fi 7"
    if "802.11ax" in m or "11ax" in m:
        return "Wi-Fi 6"
    if "802.11ac" in m or "11ac" in m:
        return "Wi-Fi 5"
    if "802.11n" in m or "11n" in m:
        return "Wi-Fi 4"
    return ""


def _r1(v: Any) -> Optional[float]:
    """Round to 1 decimal place; return None for None or non-numeric input."""
    if v is None:
        return None
    try:
        return round(float(v), 1)
    except (TypeError, ValueError):
        return None


def build() -> Dict[str, Any]:
    """Collect all live data and return a single serialisable dictionary."""
    from web.backend.ping_stats import stats_from_rtt_history

    # ── Wi-Fi (cached to avoid hammering CoreWLAN at 4 Hz) ─────
    conn = _get_wifi()
    rssi_dbm: Optional[int] = conn.get("rssi_dbm")
    noise_dbm: Optional[int] = conn.get("noise_dbm")

    # connected: need at least a non-zero RSSI or a known SSID, with no error
    has_link = bool(conn.get("ssid")) or (isinstance(rssi_dbm, int) and rssi_dbm != 0)
    connected = has_link and not conn.get("error")

    # Update RSSI rolling stats (safe: RssiState is internally locked)
    rssi_state.record(rssi_dbm if isinstance(rssi_dbm, int) else None)
    avg10, stddev = rssi_state.stats()

    snr: Optional[int] = (
        (rssi_dbm - noise_dbm)
        if isinstance(rssi_dbm, int) and isinstance(noise_dbm, int)
        else None
    )

    rate = conn.get("tx_rate_mbps")
    # Treat 0 Mbps as valid (link negotiated at zero), only exclude None
    phy_speed = int(rate) if isinstance(rate, (int, float)) and rate is not None else None

    # ── Ping ───────────────────────────────────────────────────
    rtt, hist, target = ping_state.snapshot()
    stats = stats_from_rtt_history(hist)

    return {
        "connected": connected,
        # Signal
        "signal": rssi_dbm,
        "rssi_avg10": avg10,
        "rssi_stddev20": stddev,
        "snr": snr,
        "phy_speed": phy_speed,
        # Ping
        "ping": _r1(rtt),
        "loss": round(float(stats.get("loss_pct") or 0.0), 1),
        "min_ms": _r1(stats.get("min_ms")),
        "max_ms": _r1(stats.get("max_ms")),
        "avg_ms": _r1(stats.get("avg_ms")),
        "jitter_ms": _r1(stats.get("jitter_ms")),
        # AP info
        "ap_name": conn.get("ssid"),
        "bssid": conn.get("bssid"),
        "channel": str(conn.get("channel")) if conn.get("channel") is not None else None,
        "band": conn.get("band"),
        "phy_mode": conn.get("phy_mode"),
        "wifi_gen": _wifi_gen_label(conn.get("phy_mode")),
        "width": conn.get("channel_width"),
        # Meta
        "ping_target": target,
        "ping_history": hist,
        "ts": time.time(),
    }
