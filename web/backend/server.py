"""NetScope web backend — FastAPI routes and application lifecycle.

All mutable state lives in ``state.py``.
The background ping worker is managed by ``ping_worker.py``.
The WebSocket payload is assembled by ``payload.py``.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, Literal, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

from core.version import read_version
from web.backend import payload as _payload
from web.backend import ping_worker
from web.backend.state import ping as ping_state

log = logging.getLogger(__name__)
_APP_VERSION = read_version()

_FRONTEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
_INDEX_HTML = os.path.join(_FRONTEND, "index.html")


# ── Lifespan: start/stop background workers ───────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    ping_worker.ensure_running()
    log.info("NetScope v%s web backend started", _APP_VERSION)
    yield
    ping_worker.stop()
    log.info("NetScope v%s web backend stopped", _APP_VERSION)


app = FastAPI(
    title="NetScope",
    version=_APP_VERSION,
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=_FRONTEND), name="static")


# ── Static serving ─────────────────────────────────────────────────

@app.get("/")
async def index() -> FileResponse:
    return FileResponse(_INDEX_HTML)


# ── WebSocket live feed ────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    loop = asyncio.get_running_loop()
    try:
        while True:
            data = await loop.run_in_executor(None, _payload.build)
            await ws.send_json(data)
            await asyncio.sleep(0.25)
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("WebSocket feed error")
        try:
            await ws.close()
        except Exception:
            pass


# ── Request / response models ─────────────────────────────────────

class HostBody(BaseModel):
    host: str

    @field_validator("host")
    @classmethod
    def host_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("host must not be empty")
        return v.strip()


# Aliases kept for readability at call sites
PingTargetBody = HostBody
DiagHost = HostBody


class IperfBody(BaseModel):
    host: str
    direction: Literal["download", "upload"] = "download"

    @field_validator("host")
    @classmethod
    def host_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("host must not be empty")
        return v.strip()


# ── Helper ─────────────────────────────────────────────────────────

def _sanitize(raw_host: str) -> str:
    """Normalize and validate a user-supplied hostname/IP.

    Raises HTTP 400 if the host is invalid so every endpoint fails
    consistently before touching any subprocess.
    """
    from core.host_sanitize import normalize_diagnostic_host
    host = normalize_diagnostic_host(raw_host)
    if not host:
        raise HTTPException(status_code=400, detail="Invalid hostname or IP address")
    return host


# ── Ping target ────────────────────────────────────────────────────

@app.post("/api/ping/target")
async def set_ping_target(body: PingTargetBody) -> Dict[str, str]:
    host = _sanitize(body.host)
    ping_state.set_target(host)
    return {"target": host}


# ── Network info ───────────────────────────────────────────────────

@app.get("/api/network/info")
async def network_info() -> Any:
    def _run() -> Dict[str, Any]:
        import json as _json
        import re
        import subprocess
        import urllib.request

        info: Dict[str, Any] = {
            # Connection
            "gateway": None,
            "gateway_v6": None,
            "dns_servers": [],
            "dns_v6": [],
            "public_ip": None,
            "public_ipv6": None,
            "http_proxy": "None",
            # Wi-Fi
            "wifi_connected": False,
            "wifi_ssid": None,
            "wifi_bssid": None,
            "wifi_vendor": None,
            "wifi_security": None,
            "private_ip": None,
            "subnet_mask": None,
            "subnet_cidr": None,
            "ipv6_addresses": [],
            "mac": None,
        }

        # ── Default gateway (IPv4) ──────────────────────────────────
        iface_name = "en0"
        try:
            out = subprocess.check_output(
                ["route", "-n", "get", "default"], text=True, timeout=3, stderr=subprocess.DEVNULL
            )
            m = re.search(r"gateway:\s+(\S+)", out)
            if m:
                info["gateway"] = m.group(1)
            m = re.search(r"interface:\s+(\S+)", out)
            if m:
                iface_name = m.group(1)
        except Exception:
            pass

        # ── Default gateway (IPv6) — skip VPN tunnel interfaces ────
        try:
            out = subprocess.check_output(
                ["netstat", "-rn", "-f", "inet6"], text=True, timeout=3, stderr=subprocess.DEVNULL
            )
            for line in out.splitlines():
                parts = line.split()
                if parts and parts[0] == "default" and len(parts) >= 2:
                    gw = parts[1]
                    # Skip link-local VPN gateways (fe80::%utunN)
                    if not gw.startswith("fe80"):
                        info["gateway_v6"] = gw
                        break
        except Exception:
            pass

        # ── ifconfig: private IP, subnet, MAC, IPv6 ────────────────
        try:
            out = subprocess.check_output(
                ["ifconfig", iface_name], text=True, timeout=3, stderr=subprocess.DEVNULL
            )
            # Private IP
            m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", out)
            if m:
                info["private_ip"] = m.group(1)
            # Subnet mask
            m = re.search(r"netmask (0x[0-9a-f]+)", out)
            if m:
                n = int(m.group(1), 16)
                info["subnet_mask"] = ".".join(str((n >> (24 - 8 * i)) & 0xFF) for i in range(4))
                info["subnet_cidr"] = f"/{bin(n).count('1')}"
            # MAC
            m = re.search(r"ether ([0-9a-f:]+)", out)
            if m:
                info["mac"] = m.group(1).upper()
            # IPv6 (exclude link-local fe80::)
            ipv6s = re.findall(r"inet6 ([0-9a-f:]+)(?:%\S+)? prefixlen", out)
            info["ipv6_addresses"] = [a for a in ipv6s if not a.startswith("fe80")]
        except Exception:
            pass

        # ── DNS servers ─────────────────────────────────────────────
        try:
            out = subprocess.check_output(
                ["scutil", "--dns"], text=True, timeout=3, stderr=subprocess.DEVNULL
            )
            all_dns = list(dict.fromkeys(re.findall(r"nameserver\[\d+\] : (\S+)", out)))
            info["dns_servers"] = [s for s in all_dns if ":" not in s][:4]
            info["dns_v6"] = [s for s in all_dns if ":" in s][:4]
        except Exception:
            pass

        # ── HTTP Proxy ──────────────────────────────────────────────
        try:
            out = subprocess.check_output(
                ["scutil", "--proxy"], text=True, timeout=3, stderr=subprocess.DEVNULL
            )
            http_on  = re.search(r"HTTPEnable\s*:\s*(\d+)", out)
            https_on = re.search(r"HTTPSEnable\s*:\s*(\d+)", out)
            http_host = re.search(r"HTTPProxy\s*:\s*(\S+)", out)
            http_port = re.search(r"HTTPPort\s*:\s*(\d+)", out)
            if (http_on and http_on.group(1) == "1") or (https_on and https_on.group(1) == "1"):
                host = http_host.group(1) if http_host else "?"
                port = http_port.group(1) if http_port else ""
                info["http_proxy"] = f"{host}:{port}" if port else host
            else:
                info["http_proxy"] = "None"
        except Exception:
            pass

        # ── Wi-Fi connection info ────────────────────────────────────
        try:
            from collectors.wifi_collector import fetch_current_connection
            conn = fetch_current_connection()
            has_rssi = isinstance(conn.get("rssi_dbm"), int) and conn["rssi_dbm"] != 0
            info["wifi_connected"] = bool(conn.get("ssid")) or has_rssi
            info["wifi_ssid"]     = conn.get("ssid")
            info["wifi_bssid"]    = conn.get("bssid")
            # Decode raw security integer to label
            from collectors.wifi_collector import _SEC_NAMES  # type: ignore[attr-defined]
            raw_sec = conn.get("security")
            try:
                info["wifi_security"] = _SEC_NAMES.get(int(raw_sec), raw_sec)
            except (TypeError, ValueError):
                info["wifi_security"] = raw_sec
            if info["private_ip"] is None:
                info["private_ip"] = None  # already set above
        except Exception:
            pass

        # ── External lookups — run in parallel to avoid serial timeouts ──
        import concurrent.futures

        def _vendor(bssid_or_mac: str) -> Optional[str]:
            first_byte = int(bssid_or_mac.replace("-", ":").split(":")[0], 16)
            if first_byte & 0x02:
                return "Randomized / Local"
            try:
                oui = bssid_or_mac.replace(":", "-")[:8].upper()
                url = f"https://api.macvendors.com/{oui}"
                req = urllib.request.Request(url, headers={"User-Agent": "netscope/1.0"})
                with urllib.request.urlopen(req, timeout=4) as r:
                    return r.read().decode().strip()
            except Exception:
                return None

        def _public_ip() -> Optional[str]:
            try:
                with urllib.request.urlopen("https://api.ipify.org?format=json", timeout=5) as r:
                    return _json.loads(r.read())["ip"]
            except Exception:
                return None

        def _public_ipv6() -> Optional[str]:
            try:
                with urllib.request.urlopen("https://api6.ipify.org?format=json", timeout=5) as r:
                    return _json.loads(r.read())["ip"]
            except Exception:
                return None

        bssid = info.get("wifi_bssid") or info.get("mac")
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            f_vendor = pool.submit(_vendor, bssid) if bssid else None
            f_ip4    = pool.submit(_public_ip)
            f_ip6    = pool.submit(_public_ipv6)
            if f_vendor:
                info["wifi_vendor"] = f_vendor.result()
            info["public_ip"]   = f_ip4.result()
            info["public_ipv6"] = f_ip6.result()

        return info

    return await asyncio.get_running_loop().run_in_executor(None, _run)


# ── Wi-Fi scan ─────────────────────────────────────────────────────

@app.get("/api/wifi/scan")
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
        # Inject our own AP if the scan missed it (no entry on our channel)
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


# ── DNS ────────────────────────────────────────────────────────────

@app.post("/api/dns")
async def run_dns(body: DiagHost) -> Any:
    host = _sanitize(body.host)

    def _run() -> Any:
        from collectors import dns_collector
        return {"results": dns_collector.compare_servers(host)}

    return await asyncio.get_running_loop().run_in_executor(None, _run)


# ── Speed test ─────────────────────────────────────────────────────

@app.post("/api/speed")
async def run_speed() -> Any:
    def _run() -> Any:
        from collectors import speed_collector
        data = speed_collector.run_network_quality()
        return {"summary": speed_collector.summarize(data), "json": data.get("json")}

    return await asyncio.get_running_loop().run_in_executor(None, _run)


# ── Traceroute ─────────────────────────────────────────────────────

@app.post("/api/traceroute")
async def run_traceroute(body: DiagHost) -> Any:
    host = _sanitize(body.host)

    def _run() -> Any:
        from collectors import traceroute_collector
        return traceroute_collector.traceroute(host)

    return await asyncio.get_running_loop().run_in_executor(None, _run)


# ── Interfaces ─────────────────────────────────────────────────────

@app.get("/api/interfaces")
async def get_interfaces() -> Any:
    def _run() -> Any:
        from collectors import interface_collector
        return interface_collector.snapshot()

    return await asyncio.get_running_loop().run_in_executor(None, _run)


# ── iperf3 ─────────────────────────────────────────────────────────

@app.post("/api/iperf")
async def run_iperf(body: IperfBody) -> Any:
    host = _sanitize(body.host)
    reverse = body.direction == "download"

    def _run() -> Any:
        from collectors import iperf_collector
        if not iperf_collector.iperf3_available():
            raise HTTPException(status_code=503, detail="iperf3 not found — install with: brew install iperf3")
        data = iperf_collector.run_iperf3(host, duration=10, reverse=reverse)
        result = iperf_collector.summarize_result(data)
        result["raw"] = data.get("raw", "")
        result["ok"] = data.get("ok", False)
        return result

    return await asyncio.get_running_loop().run_in_executor(None, _run)
