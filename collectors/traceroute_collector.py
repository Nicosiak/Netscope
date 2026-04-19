"""Traceroute via system binary — parse, row deltas, segment/ASN enrichment."""

from __future__ import annotations

import ipaddress
import re
import subprocess
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Any, Dict, List, Optional, Tuple

from collectors._subprocess import merged_output, run_text
from core.host_sanitize import normalize_diagnostic_host

_HOP_PREFIX = re.compile(r"^(\d+)\s+(.*)$")
# Strip trailing RTT tokens (digits or "<1 ms" style) before parsing host field.
_TRAILING_MS = re.compile(r"(\s+(?:<\s*)?[\d.]+\s*ms)+\s*$", re.IGNORECASE)
_MS_TOKEN = re.compile(r"(?:<\s*)?([\d.]+)\s*ms", re.IGNORECASE)
_HEADER = re.compile(
    r"traceroute to\s+(.+?)\s+\(([^)]*)\),\s*(\d+)\s+hops max,\s*(\d+)\s+byte",
    re.IGNORECASE,
)
_NAME_IN_PARENS = re.compile(r"^(.+?)\s+\(([^)]+)\)\s*$")
_MAX_HOPS_FLAG = 32
# Probes per hop from ``traceroute -q``; ``packet_loss_pct`` = no-reply probes / total.
_PROBE_COUNT = 3

# ASNs commonly seen at path end / DNS targets (Team Cymru first field is numeric)
_CLOUD_ASNS = frozenset({15169, 13335, 20940, 16550, 36459})
_STAR_ONLY = re.compile(r"^[\s*]+$")


def nonblank_traceroute_lines(raw: str) -> List[str]:
    return [ln.rstrip() for ln in raw.splitlines() if ln.strip()]


def _parse_ipv4(s: str) -> Optional[str]:
    s = s.strip()
    try:
        ipaddress.IPv4Address(s)
        return s
    except ValueError:
        return None


def _parse_ip_any(s: str) -> Optional[str]:
    s = s.strip()
    for fn in (ipaddress.IPv4Address, ipaddress.IPv6Address):
        try:
            return str(fn(s))  # type: ignore[arg-type]
        except ValueError:
            continue
    return None


def _is_private_ip(ip: Optional[str]) -> bool:
    if not ip:
        return False
    try:
        a = ipaddress.ip_address(ip)
        return bool(a.is_private or a.is_loopback or a.is_link_local)
    except ValueError:
        return False


def parse_traceroute_hop_line(line: str) -> Optional[Dict[str, Any]]:
    """Parse one stdout line from macOS/BSD ``traceroute`` into structured data."""
    s = line.strip()
    if not s or s.lower().startswith("traceroute to"):
        return None
    m = _HOP_PREFIX.match(s)
    if not m:
        return None
    ttl = int(m.group(1))
    rest = m.group(2).strip()
    times = [float(mg.group(1)) for mg in _MS_TOKEN.finditer(rest)]
    rtt_ms = times[0] if times else None
    probe_reply_count = len(times)
    host_field = _TRAILING_MS.sub("", rest).strip()
    if not host_field:
        host_field = "*"

    ip: Optional[str] = None
    hostname: Optional[str] = None

    if _STAR_ONLY.match(host_field) and "*" in host_field:
        ip = None
        hostname = None
        host = host_field
    else:
        nm = _NAME_IN_PARENS.match(host_field)
        if nm:
            hostname = nm.group(1).strip()
            inner = nm.group(2).strip()
            ip = _parse_ip_any(inner) or inner
            host = host_field
        else:
            ip_try = _parse_ip_any(host_field)
            if ip_try:
                ip = ip_try
                host = host_field
            else:
                host = host_field
                ip = None
                hostname = host_field if host_field != "*" else None

    return {
        "ttl": ttl,
        "host": host,
        "ip": ip,
        "hostname": hostname,
        "rtt_ms": rtt_ms,
        "probe_reply_count": probe_reply_count,
        "line": s.strip(),
    }


def parse_traceroute_hops(lines: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for ln in lines:
        row = parse_traceroute_hop_line(ln)
        if row:
            out.append(row)
    return out


def parse_traceroute_header(first_line: str) -> Optional[Dict[str, str]]:
    """Parse the first line of macOS/BSD ``traceroute`` stdout."""
    m = _HEADER.match(first_line.strip())
    if not m:
        return None
    return {
        "query": m.group(1).strip(),
        "resolved": m.group(2).strip(),
        "max_hops_cli": m.group(3).strip(),
        "packet_bytes": m.group(4).strip(),
    }


def enrich_hops_row_delta(hops: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Consecutive-row RTT delta (reference mock), null when either side lacks RTT."""
    out: List[Dict[str, Any]] = []
    for i, h in enumerate(hops):
        row = dict(h)
        if i == 0:
            row["delta_row_ms"] = None
        else:
            pr = hops[i - 1].get("rtt_ms")
            cr = h.get("rtt_ms")
            if pr is not None and cr is not None:
                row["delta_row_ms"] = round(float(cr) - float(pr), 3)
            else:
                row["delta_row_ms"] = None
        out.append(row)
    return out


def _dig_txt(domain: str, *, timeout: float = 2.0) -> str:
    try:
        p = run_text(["dig", "+short", "TXT", domain, "@8.8.8.8"], timeout=timeout)
        return merged_output(p).strip()
    except Exception:
        return ""


def _dig_ptr(ip: str, *, timeout: float = 1.8) -> str:
    if not _parse_ipv4(ip):
        return ""
    try:
        p = run_text(["dig", "+short", "-x", ip, "@8.8.8.8"], timeout=timeout)
        lines = [ln.strip().strip(".") for ln in merged_output(p).splitlines() if ln.strip()]
        return lines[0] if lines else ""
    except Exception:
        return ""


def _cymru_txt_for_ipv4(ip: str) -> str:
    if not _parse_ipv4(ip):
        return ""
    rev = ".".join(reversed(ip.split(".")))
    return _dig_txt(f"{rev}.origin.asn.cymru.com", timeout=2.0)


def parse_cymru_txt(txt: str) -> Tuple[str, str]:
    """Parse first quoted Team Cymru TXT record into (asn_label, org-ish)."""
    raw = txt.strip()
    if not raw:
        return "—", "Unknown"
    line = raw.splitlines()[0].strip().strip('"')
    parts = [p.strip() for p in line.split("|")]
    if not parts or not parts[0]:
        return "—", "Unknown"
    asn0 = parts[0]
    asn = "AS" + asn0 if asn0.isdigit() else asn0
    org = parts[1] if len(parts) > 1 else "Unknown"
    return asn, org


def _asn_int(asn_label: str) -> Optional[int]:
    s = asn_label.upper().replace("AS", "").strip()
    if s.isdigit():
        return int(s)
    return None


def enrich_hops_network(
    hops: List[Dict[str, Any]],
    target: str,
    *,
    budget_s: float = 10.0,
) -> Dict[str, Any]:
    """
    PTR + Team Cymru (IPv4) in parallel under ``budget_s`` seconds; assign ``asn``, ``org``,
    ``segment``; fill ``hostname`` from PTR when missing.
    """
    extra: Dict[str, Any] = {"destination_name": ""}
    t0 = time.monotonic()

    def job_cymru(ip: str) -> Tuple[str, Tuple[str, str]]:
        return ip, parse_cymru_txt(_cymru_txt_for_ipv4(ip))

    def job_ptr(ip: str) -> Tuple[str, str]:
        return ip, _dig_ptr(ip)

    cymru_ips: List[str] = []
    ptr_ips: List[str] = []
    for h in hops:
        ip = h.get("ip")
        if not ip:
            continue
        if _parse_ipv4(ip) and ip not in cymru_ips:
            cymru_ips.append(ip)
        if _parse_ipv4(ip) and not (h.get("hostname") or "").strip():
            if ip not in ptr_ips:
                ptr_ips.append(ip)

    cymru_map: Dict[str, Tuple[str, str]] = {}
    ptr_map: Dict[str, str] = {}

    tasks: List[Tuple[str, str]] = list(
        {("cymru", ip) for ip in cymru_ips} | {("ptr", ip) for ip in ptr_ips}
    )

    if tasks:
        with ThreadPoolExecutor(max_workers=10) as ex:
            fut_map = {}
            for kind, ip in tasks:
                if kind == "cymru":
                    fut_map[ex.submit(job_cymru, ip)] = ("cymru", ip)
                else:
                    fut_map[ex.submit(job_ptr, ip)] = ("ptr", ip)

            pending = set(fut_map.keys())
            while pending and (time.monotonic() - t0) < budget_s:
                wait_timeout = min(0.75, budget_s - (time.monotonic() - t0))
                if wait_timeout <= 0:
                    break
                done, pending = wait(pending, timeout=wait_timeout, return_when=FIRST_COMPLETED)
                for fu in done:
                    kind, ip = fut_map.pop(fu, ("", ""))
                    try:
                        if kind == "cymru":
                            ipk, pair = fu.result()
                            cymru_map[ipk] = pair
                        else:
                            ipk, name = fu.result()
                            if name:
                                ptr_map[ipk] = name
                    except Exception:
                        pass

    # destination PTR (best effort, quick)
    tgt = _parse_ip_any(target) or target
    if _parse_ipv4(tgt):
        extra["destination_name"] = _dig_ptr(tgt, timeout=1.5) or ""

    first_public_idx: Optional[int] = None
    first_public_asn: Optional[int] = None
    for i, h in enumerate(hops):
        ip = h.get("ip")
        if h.get("rtt_ms") is None or not ip:
            continue
        if not _is_private_ip(ip):
            first_public_idx = i
            asn_s, _ = cymru_map.get(ip, ("—", "Unknown"))
            first_public_asn = _asn_int(asn_s)
            break

    last_reply_i: Optional[int] = None
    for i in range(len(hops) - 1, -1, -1):
        if hops[i].get("rtt_ms") is not None:
            last_reply_i = i
            break

    for idx, h in enumerate(hops):
        ip = h.get("ip")
        asn, org = "—", "Unknown"
        if ip and _parse_ipv4(ip):
            asn, org = cymru_map.get(ip, ("—", "Unknown"))
        h["asn"] = asn
        h["org"] = org

        if not (h.get("hostname") or "").strip() and ip and ip in ptr_map:
            h["hostname"] = ptr_map[ip]

        seg = "null"
        if h.get("rtt_ms") is None or not ip:
            seg = "null"
        elif _is_private_ip(ip):
            seg = "lan"
        else:
            ai = _asn_int(asn)
            org_u = org.upper()
            is_cloud = (
                (ai is not None and ai in _CLOUD_ASNS)
                or "GOOGLE" in org_u
                or "CLOUDFLARE" in org_u
            )
            is_last_reply = last_reply_i is not None and idx == last_reply_i
            if is_cloud or is_last_reply:
                seg = "cloud"
            elif first_public_idx is not None:
                if idx == first_public_idx:
                    seg = "isp"
                elif first_public_asn is not None and ai == first_public_asn:
                    seg = "isp"
                else:
                    seg = "transit"
            else:
                seg = "transit"
        h["segment"] = seg

    return extra


def _traceroute_meta(
    host: str,
    raw: str,
    hops: List[Dict[str, Any]],
    elapsed_ms: float,
    destination_name: str = "",
) -> Dict[str, Any]:
    first_line = raw.splitlines()[0].strip() if raw.strip() else ""
    header = parse_traceroute_header(first_line)
    replied = sum(1 for h in hops if h.get("rtt_ms") is not None)
    timeouts = sum(1 for h in hops if h.get("rtt_ms") is None)
    probes_sent = len(hops) * _PROBE_COUNT if hops else 0
    probes_replied = 0
    for h in hops:
        n = h.get("probe_reply_count")
        if isinstance(n, int) and n >= 0:
            probes_replied += min(n, _PROBE_COUNT)
        else:
            probes_replied += 1 if h.get("rtt_ms") is not None else 0
    if probes_sent > 0:
        loss_pct = round(100.0 * (probes_sent - probes_replied) / probes_sent, 1)
    else:
        loss_pct = 0.0
    last = hops[-1] if hops else None
    last_reply: Optional[Dict[str, Any]] = None
    for h in reversed(hops):
        if h.get("rtt_ms") is not None:
            last_reply = h
            break
    rtts = [float(h["rtt_ms"]) for h in hops if h.get("rtt_ms") is not None]
    max_rtt = round(max(rtts), 3) if rtts else None

    meta: Dict[str, Any] = {
        "target": host,
        "elapsed_ms": round(elapsed_ms, 1),
        "header": header,
        "hops_count": len(hops),
        "replied_count": replied,
        "timeout_count": timeouts,
        "probes_sent": probes_sent,
        "probes_replied": probes_replied,
        "probe_count_per_hop": _PROBE_COUNT,
        "max_hops_limit": _MAX_HOPS_FLAG,
        "method": "UDP",
        "destination_name": destination_name or "",
        "packet_loss_pct": loss_pct,
        "max_rtt_ms": max_rtt,
    }
    if last:
        meta["last_row_ttl"] = last.get("ttl")
        meta["last_row_host"] = last.get("host")
    if last_reply:
        meta["last_reply_ttl"] = last_reply.get("ttl")
        meta["last_reply_host"] = last_reply.get("host")
        lr = last_reply.get("rtt_ms")
        meta["last_reply_rtt_ms"] = lr
        meta["dest_rtt_ms"] = lr
    return meta


def traceroute(host: str = "8.8.8.8") -> Dict[str, Any]:
    """
    UDP traceroute (hostnames when resolver returns them). macOS typically
    does not require sudo. Uses ``-q`` matching ``_PROBE_COUNT`` probes per hop;
    ``meta.packet_loss_pct`` is the share of those probes with no RTT in the
    output (not end-to-end traffic loss; silent routers count as no reply).
    """
    h = normalize_diagnostic_host(host.strip())
    if not h:
        return {
            "host": host,
            "raw": "Invalid host.",
            "lines": [],
            "hops": [],
            "meta": {"target": host, "elapsed_ms": 0.0, "hops_count": 0},
        }

    result: Dict[str, Any] = {"host": h, "raw": "", "lines": [], "hops": [], "meta": {}}
    try:
        t0 = time.monotonic()
        p = run_text(
            [
                "traceroute",
                "-q",
                str(_PROBE_COUNT),
                "-w",
                "2",
                "-m",
                str(_MAX_HOPS_FLAG),
                h,
            ],
            timeout=120.0,
        )
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        raw = p.stdout or ""
        if not raw.strip() and p.stderr:
            raw = p.stderr
        result["raw"] = raw
        lines = nonblank_traceroute_lines(raw)
        result["lines"] = lines
        hops = enrich_hops_row_delta(parse_traceroute_hops(lines))
        extra = enrich_hops_network(hops, h, budget_s=10.0)
        result["hops"] = hops
        meta = _traceroute_meta(h, raw, hops, elapsed_ms, destination_name=extra.get("destination_name", ""))
        result["meta"] = meta
    except subprocess.TimeoutExpired:
        result["raw"] = "Traceroute timed out."
        result["meta"] = {"target": h, "elapsed_ms": 0.0, "hops_count": 0, "timeout": True}
    except FileNotFoundError:
        result["raw"] = "traceroute not found on PATH."
        result["meta"] = {"target": h, "elapsed_ms": 0.0, "hops_count": 0}
    except Exception as e:
        result["raw"] = str(e)
        result["meta"] = {"target": h, "elapsed_ms": 0.0, "hops_count": 0}
    return result
