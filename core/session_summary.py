"""Session snapshot aggregation — pure functions used by the summary API route and tests."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _agg(vals: List[Any]) -> Dict[str, Any]:
    if not vals:
        return {}
    return {
        "min": round(min(vals), 1),
        "max": round(max(vals), 1),
        "avg": round(sum(vals) / len(vals), 1),
    }


def summarize_snapshots(
    snaps: List[Dict[str, Any]],
    spike_events: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Aggregate stability snapshots into summary stats for the session review UI.

    Prefers ``rssi_avg10`` (2.5 s smoothed) over raw ``signal`` to reduce
    multipath bounce in RSSI stats; falls back to ``signal`` when absent.
    """
    spike_events = spike_events or []

    if not snaps:
        return {
            "snapshot_count": 0,
            "spike_event_count": len(spike_events),
            "rssi": {}, "ping": {}, "loss": {}, "alerts": {},
        }

    rssi_vals = [
        s["rssi_avg10"] if s.get("rssi_avg10") is not None else s["signal"]
        for s in snaps
        if s.get("rssi_avg10") is not None or s.get("signal") is not None
    ]
    ping_vals = [s["avg_ms"] for s in snaps if s.get("avg_ms") is not None]
    loss_vals = [s["loss"] for s in snaps if s.get("loss") is not None]
    warn_count = sum(1 for s in snaps if s.get("alerts", {}).get("level") == "warning")
    crit_count = sum(1 for s in snaps if s.get("alerts", {}).get("level") == "critical")

    return {
        "snapshot_count": len(snaps),
        "spike_event_count": len(spike_events),
        "rssi": _agg(rssi_vals),
        "ping": _agg(ping_vals),
        "loss": _agg(loss_vals),
        "alerts": {"warning": warn_count, "critical": crit_count},
    }
