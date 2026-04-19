"""Diagnostic tool routes: DNS, speed, traceroute, iperf, nmap, WAN check."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException

from web.backend.helpers import sanitize_host
from web.backend.models import DiagHost, DnsCompareBody, IperfBody, NmapScanBody, SpeedTestBody

router = APIRouter()


@router.post("/api/wan/check")
async def wan_check() -> Dict[str, Any]:
    def _run() -> Dict[str, Any]:
        import ipaddress
        import re
        import subprocess
        from concurrent.futures import ThreadPoolExecutor

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
            from core.subproc import run_text
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
        wan_up: Optional[bool] = None
        if ping_loss is not None and ping_loss < 100:
            wan_up = True
        elif ping_loss == 100:
            wan_up = False

        hops_out = [
            {"ttl": h.get("ttl"), "ip": h.get("ip"), "hostname": h.get("hostname"), "rtt_ms": h.get("rtt_ms")}
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


@router.post("/api/dns")
async def run_dns(body: DnsCompareBody) -> Any:
    host = sanitize_host(body.host.strip() or "google.com")

    def _run() -> Any:
        from collectors import dns_collector
        return {
            "results": dns_collector.compare_servers(host, body.record_type),
            "record_type": body.record_type,
        }

    return await asyncio.get_running_loop().run_in_executor(None, _run)


@router.post("/api/speed")
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


@router.post("/api/traceroute")
async def run_traceroute(body: DiagHost) -> Any:
    host = sanitize_host(body.host)

    def _run() -> Any:
        from collectors import traceroute_collector
        return traceroute_collector.traceroute(host)

    return await asyncio.get_running_loop().run_in_executor(None, _run)


@router.post("/api/iperf")
async def run_iperf(body: IperfBody) -> Any:
    host = sanitize_host(body.host)
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


@router.get("/api/nmap/version")
async def nmap_version_info() -> Dict[str, Any]:
    def _run() -> Dict[str, Any]:
        from collectors import nmap_collector
        return {
            "available": nmap_collector.nmap_available(),
            "version": nmap_collector.nmap_version_line(),
        }

    return await asyncio.get_running_loop().run_in_executor(None, _run)


@router.post("/api/nmap")
async def run_nmap_scan(body: NmapScanBody) -> Any:
    import logging
    host = sanitize_host(body.host.strip() or "127.0.0.1")
    logging.getLogger(__name__).info("nmap scan preset=%s target=%s", body.preset, host)

    def _run() -> Any:
        from collectors import nmap_collector
        return nmap_collector.run_nmap(host, body.preset)

    return await asyncio.get_running_loop().run_in_executor(None, _run)
