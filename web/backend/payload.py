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
seq              int               Increments on each new ping measurement
spike            bool              True when RTT > 2× baseline EMA
baseline_ms      float | None      Slow EMA of RTT (alpha=0.05); spike-resistant
loss             float             Packet-loss % (0.0 when no history)
min_ms           float | None      Min RTT over history
avg_ms           float | None      Mean RTT over history
p50_ms           float | None      Median RTT (spike-resistant typical latency)
p95_ms           float | None      95th-percentile RTT (outlier severity)
max_ms           float | None      Max RTT over history
jitter_ms        float | None      Inter-arrival MAD (RFC 3393-style)
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
alerts           dict              {level: str, messages: list[str]}
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional

from web.backend.state import ping as ping_state
from web.backend.state import rssi as rssi_state
from web.backend.state import session as session_state

# ── WiFi connection cache (400 ms TTL) ───────────────────────────
_wifi_lock   = threading.Lock()
_wifi_ts: float = 0.0
_wifi_cache: Dict[str, Any] = {}
_WIFI_TTL = 0.4  # seconds

# ── Baseline EMA for spike detection (alpha=0.05 ≈ 20-sample smoother) ──
_ema_lock  = threading.Lock()
_ema_value: Optional[float] = None
_EMA_ALPHA = 0.05


def _update_ema(rtt: Optional[float]) -> Optional[float]:
    global _ema_value
    if rtt is None:
        return _ema_value
    with _ema_lock:
        if _ema_value is None:
            _ema_value = rtt
        else:
            _ema_value = _EMA_ALPHA * rtt + (1.0 - _EMA_ALPHA) * _ema_value
        return _ema_value


def reset_baseline() -> None:
    """Reset spike-detection EMA — call on target change so a new host's
    normal latency doesn't get compared against the previous host's baseline."""
    global _ema_value
    with _ema_lock:
        _ema_value = None


def _get_wifi() -> Dict[str, Any]:
    global _wifi_ts, _wifi_cache
    with _wifi_lock:
        now = time.monotonic()
        if now - _wifi_ts < _WIFI_TTL and _wifi_cache:
            return _wifi_cache
        from collectors.wifi_collector import fetch_current_connection
        fresh = fetch_current_connection()
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
    from core.alerts import alert_engine
    from web.backend.ping_stats import stats_from_rtt_history

    # ── Wi-Fi (cached to avoid hammering CoreWLAN at 4 Hz) ─────
    conn = _get_wifi()
    rssi_dbm: Optional[int] = conn.get("rssi_dbm")
    noise_dbm: Optional[int] = conn.get("noise_dbm")

    has_link = bool(conn.get("ssid")) or (isinstance(rssi_dbm, int) and rssi_dbm != 0)
    connected = has_link and not conn.get("error")

    rssi_state.record(rssi_dbm if isinstance(rssi_dbm, int) else None)
    avg10, stddev = rssi_state.stats()

    snr: Optional[int] = (
        (rssi_dbm - noise_dbm)
        if isinstance(rssi_dbm, int) and isinstance(noise_dbm, int)
        else None
    )

    rate = conn.get("tx_rate_mbps")
    phy_speed = int(rate) if isinstance(rate, (int, float)) and rate is not None else None

    # ── Ping ───────────────────────────────────────────────────
    rtt, hist, target, seq = ping_state.snapshot()
    stats = stats_from_rtt_history(hist)

    # ── Spike detection ────────────────────────────────────────
    baseline = _update_ema(rtt)
    valid_count = sum(1 for x in hist if x is not None)
    spike = bool(
        rtt is not None
        and baseline is not None
        and valid_count >= 10
        and rtt > baseline * 2.0
        and rtt > 20.0  # ignore sub-20ms noise regardless
    )

    # ── Alerts ─────────────────────────────────────────────────
    alert_state = alert_engine.evaluate(
        rssi=float(rssi_dbm) if isinstance(rssi_dbm, int) else None,
        ping_ms=rtt,
        loss_pct=float(stats.get("loss_pct") or 0.0),
    )

    alerts_dict = {
        "level":    alert_state.level.value,
        "messages": alert_state.messages,
    }

    data: Dict[str, Any] = {
        "connected": connected,
        # Signal
        "signal": rssi_dbm,
        "rssi_avg10": avg10,
        "rssi_stddev20": stddev,
        "snr": snr,
        "phy_speed": phy_speed,
        # Ping
        "ping":        _r1(rtt),
        "seq":         seq,
        "spike":       spike,
        "baseline_ms": _r1(baseline),
        "loss":        round(float(stats.get("loss_pct") or 0.0), 1),
        "min_ms":      _r1(stats.get("min_ms")),
        "avg_ms":      _r1(stats.get("avg_ms")),
        "p50_ms":      _r1(stats.get("p50_ms")),
        "p95_ms":      _r1(stats.get("p95_ms")),
        "max_ms":      _r1(stats.get("max_ms")),
        "jitter_ms":   _r1(stats.get("jitter_ms")),
        # AP info
        "ap_name": conn.get("ssid"),
        "bssid":   conn.get("bssid"),
        "channel": str(conn.get("channel")) if conn.get("channel") is not None else None,
        "band":    conn.get("band"),
        "phy_mode":  conn.get("phy_mode"),
        "wifi_gen":  _wifi_gen_label(conn.get("phy_mode")),
        "width":     conn.get("channel_width"),
        # Meta
        "ping_target":  target,
        "ping_history": hist,
        "paused":       ping_state.is_paused(),
        "ts":           time.time(),
        # Alerts
        "alerts": alerts_dict,
        # Session
        "session_id": session_state.get(),
    }

    if session_state.get() is not None:
        from core.storage import storage as _storage

        # Shared helper: build a snapshot dict with stable (rolling-average) alerts.
        # The live alert uses instantaneous rtt for UI responsiveness; snapshot alerts
        # use avg_ms + rssi_avg10 so a single-probe spike doesn't create a false-positive
        # warning row in the session review.
        def _make_snap_fields(kind: str) -> Dict[str, Any]:
            snap_rssi = avg10 if avg10 is not None else (
                float(rssi_dbm) if isinstance(rssi_dbm, int) else None
            )
            snap_alert = alert_engine.evaluate(
                rssi=snap_rssi,
                ping_ms=float(data["avg_ms"]) if data.get("avg_ms") is not None else None,
                loss_pct=float(stats.get("loss_pct") or 0.0),
            )
            fields: Dict[str, Any] = {k: data[k] for k in (
                "signal", "snr", "rssi_avg10", "rssi_stddev20",
                "phy_speed", "ping", "avg_ms", "p95_ms", "loss",
                "jitter_ms", "spike", "baseline_ms",
                "ap_name", "bssid", "channel", "band", "phy_mode",
            ) if k in data}
            fields["alerts"] = {
                "level": snap_alert.level.value,
                "messages": snap_alert.messages,
            }
            if kind == "spike":
                fields["spike_rtt_ms"] = _r1(rtt)
            return fields

        # ── Stability snapshot: every 5 s during anomalies, 15 s when clean ──
        # Tighter cadence during degraded conditions catches short transients.
        snap_interval = 5.0 if alert_state.level.value != "ok" else 15.0
        if session_state.should_snapshot(interval=snap_interval):
            _storage.save_snapshot(
                session_state.get(),  # type: ignore[arg-type]
                "stability",
                _make_snap_fields("stability"),
            )
            session_state.mark_snapshot()

        # ── Spike event snapshot: immediate write when a spike fires ──
        # Captured independently of the stability cadence so a spike that lands
        # between two 15 s windows is never silently dropped. Throttled to once
        # per 5 s so a sustained spike doesn't flood the table.
        if spike and session_state.should_event_snapshot():
            _storage.save_snapshot(
                session_state.get(),  # type: ignore[arg-type]
                "spike",
                _make_snap_fields("spike"),
            )
            session_state.mark_event_snapshot()

    return data
