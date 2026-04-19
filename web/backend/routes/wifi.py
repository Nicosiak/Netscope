"""Wi-Fi and ping routes."""

from __future__ import annotations

import asyncio
import re
import subprocess
from typing import Any, Dict, Optional

from fastapi import APIRouter

from web.backend.helpers import sanitize_host
from web.backend.models import PingTargetBody
from web.backend.state import ping as ping_state

router = APIRouter()


@router.post("/api/ping/target")
async def set_ping_target(body: PingTargetBody) -> Dict[str, str]:
    host = sanitize_host(body.host)
    ping_state.set_target(host)
    return {"target": host}


@router.post("/api/ping/pause")
async def toggle_ping_pause() -> Dict[str, bool]:
    paused = ping_state.toggle_pause()
    return {"paused": paused}


@router.get("/api/network/gateway")
async def get_gateway() -> Dict[str, Any]:
    def _run() -> Dict[str, Any]:
        try:
            out = subprocess.check_output(
                ["route", "-n", "get", "default"], text=True, timeout=3, stderr=subprocess.DEVNULL
            )
            m = re.search(r"gateway:\s+(\S+)", out)
            return {"gateway": m.group(1) if m else None}
        except Exception:
            return {"gateway": None}
    return await asyncio.get_running_loop().run_in_executor(None, _run)


@router.get("/api/wifi/scan")
async def wifi_scan() -> Any:
    def _run() -> Any:
        from collectors.wifi_collector import (
            _SEC_NAMES,
            fetch_current_connection,
            fetch_nearby_networks,
            sort_networks_by_rssi,
        )
        networks = fetch_nearby_networks()
        conn = fetch_current_connection()
        conn_ch = conn.get("channel")
        if conn_ch is not None and not any(n.get("channel") == conn_ch for n in networks):
            raw_sec = conn.get("security")
            sec_label: Optional[str] = None
            if raw_sec is not None:
                try:
                    sec_label = _SEC_NAMES.get(int(raw_sec), str(raw_sec))
                except (ValueError, TypeError):
                    sec_label = str(raw_sec) if raw_sec else None
            networks.append({
                "ssid": conn.get("ssid"),
                "bssid": conn.get("bssid"),
                "rssi_dbm": conn.get("rssi_dbm"),
                "channel": conn_ch,
                "channel_width": conn.get("channel_width"),
                "band": conn.get("band"),
                "phy_mode": conn.get("phy_mode"),
                "security": sec_label,
            })
        return {"networks": sort_networks_by_rssi(networks)}

    return await asyncio.get_running_loop().run_in_executor(None, _run)
