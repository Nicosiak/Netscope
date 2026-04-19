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
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from core.session import TAGS, Session
from core.storage import storage as _storage
from core.version import read_version
from web.backend import payload as _payload
from web.backend import ping_worker
from web.backend.state import ping as ping_state
from web.backend.state import session as _session_state

log = logging.getLogger(__name__)
_APP_VERSION = read_version()

_FRONTEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
_INDEX_HTML = os.path.join(_FRONTEND, "index.html")

# Computed once per process — restart uvicorn to pick up new frontend mtimes.
_bundle_ver_cache: Optional[str] = None


def _frontend_js_bundle_ver() -> str:
    """Cache-bust query param when index or any frontend *.js changes (any depth)."""
    global _bundle_ver_cache
    if _bundle_ver_cache is not None:
        return _bundle_ver_cache
    try:
        mt = int(os.path.getmtime(_INDEX_HTML))
    except OSError:
        _bundle_ver_cache = "0"
        return _bundle_ver_cache
    try:
        for dirpath, _dirnames, filenames in os.walk(_FRONTEND):
            for name in filenames:
                if name.endswith(".js"):
                    p = os.path.join(dirpath, name)
                    if os.path.isfile(p):
                        mt = max(mt, int(os.path.getmtime(p)))
    except OSError:
        pass
    _bundle_ver_cache = str(mt)
    return _bundle_ver_cache


# ── Middleware: avoid stale JS/CSS in embedded WebView / browser cache ─

class _NoCacheStaticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/static/") and path.endswith((".js", ".css")):
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
        return response


# ── Lifespan: start/stop background workers ───────────────────────

def _warm_wifi_sync() -> None:
    """First CoreWLAN / Wi-Fi import can be slow; run off the accept path."""
    try:
        from collectors.wifi_collector import fetch_current_connection

        fetch_current_connection()
    except Exception:
        log.debug("Wi-Fi warm-up skipped", exc_info=True)


async def _warm_wifi_collector() -> None:
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _warm_wifi_sync)
    except Exception:
        log.debug("Wi-Fi warm-up task failed", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    ping_worker.ensure_running()
    asyncio.create_task(_warm_wifi_collector())
    log.info("NetScope v%s web backend started", _APP_VERSION)
    yield
    ping_worker.stop()
    log.info("NetScope v%s web backend stopped", _APP_VERSION)


app = FastAPI(
    title="NetScope",
    version=_APP_VERSION,
    lifespan=lifespan,
)
app.add_middleware(_NoCacheStaticMiddleware)
app.mount("/static", StaticFiles(directory=_FRONTEND), name="static")


# ── Static serving ─────────────────────────────────────────────────

@app.get("/")
async def index() -> HTMLResponse:
    try:
        raw = Path(_INDEX_HTML).read_text(encoding="utf-8")
    except OSError:
        return HTMLResponse(
            "<!DOCTYPE html><html><body>Missing index.html</body></html>",
            status_code=500,
        )
    body = raw.replace("__STATIC_V__", _frontend_js_bundle_ver())
    return HTMLResponse(
        body,
        headers={"Cache-Control": "no-store, max-age=0"},
    )


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


class DnsCompareBody(BaseModel):
    """Multi-resolver DNS compare: hostname + A or AAAA."""

    host: str = "google.com"
    record_type: Literal["A", "AAAA"] = "A"

    @field_validator("host")
    @classmethod
    def host_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("host must not be empty")
        return v.strip()


class IperfBody(BaseModel):
    host: str
    direction: Literal["download", "upload"] = "download"

    @field_validator("host")
    @classmethod
    def host_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("host must not be empty")
        return v.strip()


class SpeedTestBody(BaseModel):
    """Optional cap on networkQuality wall time (seconds, 20–90). Omitted = full default run."""

    max_seconds: Optional[int] = Field(default=None, ge=20, le=90)


class NmapScanBody(BaseModel):
    """Bounded nmap presets; target must be a host you are allowed to scan."""

    host: str = "127.0.0.1"
    preset: Literal[
        "quick",
        "services",
        "safe_scripts",
        "vuln",
        "discovery",
        "ssl",
        "udp_top",
    ] = "quick"


class SessionCreateBody(BaseModel):
    customer_name: str
    customer_address: str = ""
    notes: str = ""


class SessionPatchBody(BaseModel):
    notes: Optional[str] = None
    tags: Optional[List[str]] = None


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


@app.post("/api/ping/pause")
async def toggle_ping_pause() -> Dict[str, bool]:
    paused = ping_state.toggle_pause()
    return {"paused": paused}


@app.get("/api/network/gateway")
async def get_gateway() -> Dict[str, Any]:
    def _run() -> Dict[str, Any]:
        import re
        import subprocess
        try:
            out = subprocess.check_output(
                ["route", "-n", "get", "default"], text=True, timeout=3, stderr=subprocess.DEVNULL
            )
            m = re.search(r"gateway:\s+(\S+)", out)
            return {"gateway": m.group(1) if m else None}
        except Exception:
            return {"gateway": None}
    return await asyncio.get_running_loop().run_in_executor(None, _run)


@app.post("/api/wan/check")
async def wan_check() -> Dict[str, Any]:
    def _run() -> Dict[str, Any]:
        import ipaddress
        import re
        import subprocess
        from concurrent.futures import ThreadPoolExecutor

        # Get default gateway
        gateway: Optional[str] = None
        try:
            route_out = subprocess.check_output(
                ["route", "-n", "get", "default"], text=True, timeout=3, stderr=subprocess.DEVNULL
            )
            gm = re.search(r"gateway:\s+(\S+)", route_out)
            gateway = gm.group(1) if gm else None
        except Exception:
            pass

        target = "8.8.8.8"

        def _run_trace() -> Dict[str, Any]:
            from collectors._subprocess import run_text
            from collectors.traceroute_collector import nonblank_traceroute_lines, parse_traceroute_hops
            try:
                p = run_text(
                    ["traceroute", "-q", "3", "-w", "1", "-m", "5", target],
                    timeout=30.0,
                )
                raw = p.stdout or ""
                hops = parse_traceroute_hops(nonblank_traceroute_lines(raw))
                return {"hops": hops, "raw": raw}
            except Exception as e:
                return {"hops": [], "raw": str(e)}

        def _run_ping() -> Dict[str, Any]:
            try:
                r = subprocess.run(
                    ["ping", "-c", "10", "-i", "0.5", target],
                    capture_output=True, text=True, timeout=20,
                )
                raw = r.stdout
            except Exception as e:
                return {"loss_pct": None, "avg_ms": None, "raw": str(e)}
            lm = re.search(r"([\d.]+)%\s+packet loss", raw)
            rm = re.search(r"min/avg/max/stddev\s*=\s*([\d.]+)/([\d.]+)/([\d.]+)", raw)
            return {
                "loss_pct": float(lm.group(1)) if lm else None,
                "avg_ms": float(rm.group(2)) if rm else None,
                "raw": raw,
            }

        with ThreadPoolExecutor(max_workers=2) as ex:
            tf = ex.submit(_run_trace)
            pf = ex.submit(_run_ping)
            trace = tf.result(timeout=35)
            ping = pf.result(timeout=25)

        def _is_private(ip: str) -> bool:
            try:
                a = ipaddress.ip_address(ip)
                return bool(a.is_private or a.is_loopback or a.is_link_local)
            except ValueError:
                return False

        hops = trace.get("hops", [])
        gateway_hop: Optional[Dict[str, Any]] = None
        isp_edge_hop: Optional[Dict[str, Any]] = None
        for h in hops:
            ip = h.get("ip")
            if not ip:
                continue
            if _is_private(ip):
                if gateway_hop is None and h.get("rtt_ms") is not None:
                    gateway_hop = h
            else:
                if isp_edge_hop is None:
                    isp_edge_hop = h

        gw_rtt = gateway_hop.get("rtt_ms") if gateway_hop else None
        isp_rtt = isp_edge_hop.get("rtt_ms") if isp_edge_hop else None
        wan_segment_ms: Optional[float] = None
        if gw_rtt is not None and isp_rtt is not None:
            wan_segment_ms = round(isp_rtt - gw_rtt, 2)

        ping_loss = ping.get("loss_pct")
        if ping_loss is not None and ping_loss < 100:
            wan_up: Optional[bool] = True
        elif ping_loss == 100:
            wan_up = False
        else:
            wan_up = None

        hops_out = [
            {
                "ttl": h.get("ttl"),
                "ip": h.get("ip"),
                "hostname": h.get("hostname"),
                "rtt_ms": h.get("rtt_ms"),
            }
            for h in hops[:5]
        ]

        return {
            "gateway": gateway,
            "target": target,
            "wan_up": wan_up,
            "gateway_rtt_ms": gw_rtt,
            "isp_edge_ip": isp_edge_hop.get("ip") if isp_edge_hop else None,
            "isp_edge_hostname": isp_edge_hop.get("hostname") if isp_edge_hop else None,
            "isp_edge_rtt_ms": isp_rtt,
            "wan_segment_ms": wan_segment_ms,
            "ping_loss_pct": ping_loss,
            "ping_avg_ms": ping.get("avg_ms"),
            "hops": hops_out,
            "raw_trace": trace.get("raw", ""),
        }

    return await asyncio.get_running_loop().run_in_executor(None, _run)


# ── Network info ───────────────────────────────────────────────────

@app.get("/api/network/info")
async def network_info() -> Any:
    from collectors import network_info_collector
    return await asyncio.get_running_loop().run_in_executor(None, network_info_collector.fetch)


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
async def run_dns(body: DnsCompareBody) -> Any:
    host = _sanitize(body.host.strip() or "google.com")

    def _run() -> Any:
        from collectors import dns_collector
        return {
            "results": dns_collector.compare_servers(host, body.record_type),
            "record_type": body.record_type,
        }

    return await asyncio.get_running_loop().run_in_executor(None, _run)


# ── Speed test ─────────────────────────────────────────────────────

@app.post("/api/speed")
async def run_speed(body: SpeedTestBody = Body(default_factory=SpeedTestBody)) -> Any:
    def _run() -> Any:
        from collectors import speed_collector
        data = speed_collector.run_network_quality(max_runtime_sec=body.max_seconds)
        return {
            "summary": speed_collector.summarize(data),
            "json": data.get("json"),
            "metrics": speed_collector.extract_metrics(data),
        }

    return await asyncio.get_running_loop().run_in_executor(None, _run)


# ── Traceroute ─────────────────────────────────────────────────────

@app.post("/api/traceroute")
async def run_traceroute(body: DiagHost) -> Any:
    host = _sanitize(body.host)

    def _run() -> Any:
        from collectors import traceroute_collector
        return traceroute_collector.traceroute(host)

    return await asyncio.get_running_loop().run_in_executor(None, _run)


# ── nmap (optional CLI) ─────────────────────────────────────────────

@app.get("/api/nmap/version")
async def nmap_version_info() -> Dict[str, Any]:
    def _run() -> Dict[str, Any]:
        from collectors import nmap_collector

        return {
            "available": nmap_collector.nmap_available(),
            "version": nmap_collector.nmap_version_line(),
        }

    return await asyncio.get_running_loop().run_in_executor(None, _run)


@app.post("/api/nmap")
async def run_nmap_scan(body: NmapScanBody) -> Any:
    host = _sanitize(body.host.strip() or "127.0.0.1")
    log.info("nmap scan preset=%s target=%s", body.preset, host)

    def _run() -> Any:
        from collectors import nmap_collector
        return nmap_collector.run_nmap(host, body.preset)

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
    from collectors import iperf_collector
    if not iperf_collector.iperf3_available():
        raise HTTPException(status_code=503, detail="iperf3 not found — install with: brew install iperf3")
    reverse = body.direction == "download"

    def _run() -> Any:
        data = iperf_collector.run_iperf3(host, duration=10, reverse=reverse)
        result = iperf_collector.summarize_result(data)
        result["raw"] = data.get("raw", "")
        result["ok"] = data.get("ok", False)
        return result

    return await asyncio.get_running_loop().run_in_executor(None, _run)


# ── Customer sessions ───────────────────────────────────────────────

def _session_to_dict(s: Session) -> Dict[str, Any]:
    return {
        "id": s.id,
        "customer_name": s.customer_name,
        "customer_address": s.customer_address,
        "notes": s.notes,
        "tags": s.tags,
        "started_at": s.started_at,
        "ended_at": s.ended_at,
        "is_active": s.is_active,
        "duration_s": round(s.duration_s, 1),
    }


@app.post("/api/sessions")
async def create_session(body: SessionCreateBody) -> Dict[str, Any]:
    s = Session(
        customer_name=body.customer_name.strip(),
        customer_address=body.customer_address.strip(),
        notes=body.notes.strip(),
    )
    _storage.save_session(s)
    _session_state.set(s.id)
    return {"session": _session_to_dict(s)}


@app.get("/api/sessions")
async def list_sessions() -> Dict[str, Any]:
    def _run() -> Dict[str, Any]:
        if not _storage._conn:
            return {"sessions": []}
        cur = _storage._conn.execute(
            "SELECT s.id, s.customer_name, s.customer_address, s.notes, s.tags, "
            "s.started_at, s.ended_at, COUNT(sn.id) AS snapshot_count "
            "FROM sessions s "
            "LEFT JOIN snapshots sn ON sn.session_id = s.id AND sn.kind = 'stability' "
            "GROUP BY s.id ORDER BY s.started_at DESC LIMIT 100"
        )
        rows = []
        for r in cur.fetchall():
            s = Session.from_dict({
                "id": r[0], "customer_name": r[1], "customer_address": r[2],
                "notes": r[3], "tags": r[4], "started_at": r[5], "ended_at": r[6],
            })
            d = _session_to_dict(s)
            d["snapshot_count"] = r[7]
            rows.append(d)
        return {"sessions": rows}
    return await asyncio.get_running_loop().run_in_executor(None, _run)


@app.get("/api/sessions/active")
async def get_active_session() -> Dict[str, Any]:
    sid = _session_state.get()
    if not sid:
        return {"session": None}
    def _run() -> Dict[str, Any]:
        if not _storage._conn:
            return {"session": None}
        cur = _storage._conn.execute(
            "SELECT id, customer_name, customer_address, notes, tags, started_at, ended_at "
            "FROM sessions WHERE id = ?", (sid,)
        )
        row = cur.fetchone()
        if not row:
            return {"session": None}
        keys = ["id", "customer_name", "customer_address", "notes", "tags", "started_at", "ended_at"]
        s = Session.from_dict(dict(zip(keys, row)))
        return {"session": _session_to_dict(s)}
    return await asyncio.get_running_loop().run_in_executor(None, _run)


@app.post("/api/sessions/{session_id}/end")
async def end_session(session_id: str) -> Dict[str, Any]:
    _storage.end_session(session_id)
    if _session_state.get() == session_id:
        _session_state.set(None)
    return {"ok": True}


@app.patch("/api/sessions/{session_id}")
async def patch_session(session_id: str, body: SessionPatchBody) -> Dict[str, Any]:
    if body.notes is not None:
        _storage.update_notes(session_id, body.notes)
    if body.tags is not None:
        valid = [t for t in body.tags if t in TAGS]
        _storage.update_tags(session_id, valid)
    return {"ok": True}


@app.get("/api/sessions/{session_id}/snapshots")
async def get_session_snapshots(session_id: str) -> Dict[str, Any]:
    def _run() -> Dict[str, Any]:
        stability = _storage.get_snapshots(session_id, "stability")
        for s in stability:
            s["kind"] = "stability"
        spikes = _storage.get_snapshots(session_id, "spike")
        for s in spikes:
            s["kind"] = "spike"
        merged = sorted(stability + spikes, key=lambda x: x["ts"])
        return {"snapshots": merged}
    return await asyncio.get_running_loop().run_in_executor(None, _run)


@app.get("/api/sessions/{session_id}/summary")
async def get_session_summary(session_id: str) -> Dict[str, Any]:
    def _run() -> Dict[str, Any]:
        snaps = _storage.get_snapshots(session_id, "stability")
        spike_events = _storage.get_snapshots(session_id, "spike")

        if not snaps:
            return {
                "snapshot_count": 0, "spike_event_count": len(spike_events),
                "rssi": {}, "ping": {}, "loss": {}, "alerts": {},
            }

        # Prefer rssi_avg10 (2.5 s smoothed) over raw signal to reduce
        # multipath bounce in the summary stats; fall back to signal if absent.
        rssi_vals = [
            s["rssi_avg10"] if s.get("rssi_avg10") is not None else s["signal"]
            for s in snaps
            if s.get("rssi_avg10") is not None or s.get("signal") is not None
        ]
        ping_vals = [s["avg_ms"] for s in snaps if s.get("avg_ms") is not None]
        loss_vals = [s["loss"] for s in snaps if s.get("loss") is not None]
        warn_count = sum(1 for s in snaps if s.get("alerts", {}).get("level") == "warning")
        crit_count = sum(1 for s in snaps if s.get("alerts", {}).get("level") == "critical")

        def _agg(vals: list) -> Dict[str, Any]:
            if not vals:
                return {}
            return {
                "min": round(min(vals), 1),
                "max": round(max(vals), 1),
                "avg": round(sum(vals) / len(vals), 1),
            }

        sess_row: Dict[str, Any] = {}
        if _storage._conn:
            cur = _storage._conn.execute(
                "SELECT customer_name, customer_address, started_at, ended_at FROM sessions WHERE id=?",
                (session_id,),
            )
            row = cur.fetchone()
            if row:
                sess_row = {
                    "customer_name": row[0], "customer_address": row[1],
                    "started_at": row[2], "ended_at": row[3],
                }

        return {
            "snapshot_count": len(snaps),
            "spike_event_count": len(spike_events),
            "rssi": _agg(rssi_vals),
            "ping": _agg(ping_vals),
            "loss": _agg(loss_vals),
            "alerts": {"warning": warn_count, "critical": crit_count},
            **sess_row,
        }
    return await asyncio.get_running_loop().run_in_executor(None, _run)
