"""Optional ``nmap`` subprocess — bounded presets (TCP/UDP, discovery, TLS scripts).

Presets append only fixed argv tokens; the target is a single normalized host
from :func:`core.sanitize.normalize_diagnostic_host`. XML on stdout is parsed
for a small open-port summary; stderr is returned as ``raw`` for the live log.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

from core.subproc import run_text

# (extra argv after ``nmap``, timeout seconds) — ``-oX -`` and host appended in run_nmap.
_PRESETS: Dict[str, Tuple[List[str], float]] = {
    # Top ports, no ping probe (works through firewalls that drop ICMP)
    "quick": (["-sT", "-T4", "--top-ports", "50", "-Pn"], 120.0),
    "services": (["-sT", "-sV", "-T4", "--top-ports", "80", "-Pn"], 180.0),
    "safe_scripts": (
        ["-sT", "-sV", "-T4", "--top-ports", "80", "-Pn", "--script", "safe"],
        240.0,
    ),
    # NSE vuln category — noisy/slow; only run on hosts you are allowed to test.
    "vuln": (["-sT", "-sV", "-T4", "--top-ports", "80", "-Pn", "--script", "vuln"], 300.0),
    # Host discovery (ICMP/ARP behaviour varies by OS; no port scan)
    "discovery": (["-sn", "-T4", "-Pn"], 90.0),
    # TLS on 443 only — bounded scripts
    "ssl": (
        ["-sT", "-Pn", "-p", "443", "--script", "ssl-cert,ssl-enum-ciphers"],
        120.0,
    ),
    # UDP top ports — may require root on some systems; short timeout
    "udp_top": (["-sU", "-T4", "--top-ports", "20", "-Pn"], 120.0),
}

_nmap_run_lock = threading.Lock()


def nmap_available() -> bool:
    return shutil.which("nmap") is not None


def preset_ids() -> List[str]:
    return list(_PRESETS.keys())


def nmap_version_line() -> Optional[str]:
    """First line of ``nmap --version``, or None if unavailable."""
    if not nmap_available():
        return None
    try:
        proc = run_text(["nmap", "--version"], timeout=5.0)
        text = (proc.stdout or "").strip() or (proc.stderr or "").strip()
        if not text:
            return None
        return text.split("\n", 1)[0].strip()
    except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError):
        return None


def _port_scripts_text(port_el: ET.Element, max_each: int = 400) -> str:
    """Join NSE ``<script output=...>`` lines for TLS / vuln presets (truncated)."""
    parts: List[str] = []
    for script_el in port_el.findall("script"):
        sid = (script_el.get("id") or "").strip()
        out = (script_el.get("output") or "").strip().replace("\n", " ")
        if not sid:
            continue
        if len(out) > max_each:
            out = out[: max_each - 1] + "…"
        parts.append(f"{sid}: {out}" if out else sid)
    return "\n".join(parts)


def _service_and_product(
    port_el: ET.Element,
    state_el: Optional[ET.Element],
) -> tuple[str, str]:
    """Service name + product/detail line; fills gaps when ``-sV`` was not used."""
    reason = (state_el.get("reason") or "").strip() if state_el is not None else ""
    svc_el = port_el.find("service")
    script_txt = _port_scripts_text(port_el)

    if svc_el is None:
        name = "unknown"
        prod = reason or (
            script_txt or "no <service> in XML (use '+ Service versions' preset for -sV names)"
        )
        if script_txt and reason:
            prod = reason + "\n" + script_txt
        return name, prod

    name = (svc_el.get("name") or "").strip()
    if not name or name.lower() in ("unknown",):
        alt = (svc_el.get("method") or "").strip()
        name = alt if alt else "unknown"

    product = (svc_el.get("product") or "").strip()
    version = (svc_el.get("version") or "").strip()
    extrainfo = (svc_el.get("extrainfo") or "").strip()
    tunnel = (svc_el.get("tunnel") or "").strip()
    bits = [x for x in (product, version, extrainfo, tunnel) if x]
    prod = " ".join(bits)
    if not prod and reason:
        prod = reason
    if script_txt:
        prod = (prod + "\n" + script_txt).strip() if prod else script_txt
    return name, prod


def _stderr_or_summary(stderr: str, scan: Dict[str, Any], target: str) -> str:
    """Keep stderr when present; otherwise a short text summary so the UI is not empty."""
    if (stderr or "").strip():
        return stderr
    ports = scan.get("ports") or []
    if ports:
        lines = [
            f"(nmap stderr was empty — summary built from XML for {target})",
            f"Open ports: {len(ports)}",
            "",
        ]
        for p in ports:
            h = p.get("host") or "?"
            lines.append(
                f"  {h}  {p.get('protocol', '')}/{p.get('port', '')}  "
                f"{p.get('service', '')}  {p.get('product', '')}".rstrip()
            )
        lines.append("")
        lines.append("Tip: use '+ Service versions' preset for -sV names and versions.")
        return "\n".join(lines)
    hosts = scan.get("hosts") or []
    if hosts:
        lines = [
            f"(nmap stderr was empty — host summary from XML for {target})",
            "",
        ]
        for h in hosts:
            addrs = ", ".join(a.get("addr", "") for a in h.get("addresses") or [])
            st = h.get("status") or ""
            lines.append(f"  {addrs}  status={st}")
        return "\n".join(lines)
    return (
        "(nmap stderr was empty and no open ports were parsed from XML — "
        "try another preset or check target reachability.)"
    )


def _parse_nmap_xml(xml_text: str) -> Dict[str, Any]:
    """Best-effort parse of ``nmap -oX -`` output."""
    out: Dict[str, Any] = {"hosts": [], "ports": []}
    if not xml_text or not xml_text.strip():
        return out
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        out["parse_error"] = "invalid_xml"
        return out

    for host_el in root.findall("host"):
        hinfo: Dict[str, Any] = {"addresses": [], "names": [], "ports": [], "status": ""}
        st_el = host_el.find("status")
        if st_el is not None:
            hinfo["status"] = st_el.get("state", "") or ""
        for addr in host_el.findall("address"):
            hinfo["addresses"].append(
                {
                    "addr": addr.get("addr", ""),
                    "type": addr.get("addrtype", ""),
                }
            )
        hostnames = host_el.find("hostnames")
        if hostnames is not None:
            for hn in hostnames.findall("hostname"):
                name = hn.get("name")
                if name:
                    hinfo["names"].append(name)
        ports_el = host_el.find("ports")
        if ports_el is not None:
            for port_el in ports_el.findall("port"):
                state_el = port_el.find("state")
                state = state_el.get("state", "") if state_el is not None else ""
                if state != "open":
                    continue
                proto = port_el.get("protocol", "")
                portid = port_el.get("portid", "")
                svc_name, prod = _service_and_product(port_el, state_el)
                row = {
                    "protocol": proto,
                    "port": portid,
                    "state": state,
                    "service": svc_name,
                    "product": prod,
                }
                hinfo["ports"].append(row)
                out["ports"].append({**row, "host": hinfo["addresses"][0]["addr"] if hinfo["addresses"] else ""})
        if hinfo["addresses"] or hinfo["ports"] or hinfo["names"] or hinfo["status"]:
            out["hosts"].append(hinfo)
    return out


def run_nmap(host: str, preset: str) -> Dict[str, Any]:
    """
    Run a bounded ``nmap`` scan. *host* must already be normalized.

    Returns a dict suitable for JSON: ``raw`` is stderr (human progress);
    XML on stdout is parsed into ``scan`` and omitted from ``raw``.
    """
    base_err: Dict[str, Any] = {
        "duration_ms": None,
        "argv": None,
        "scan": None,
        "xml_raw": None,
    }

    if not nmap_available():
        return {
            **base_err,
            "ok": False,
            "available": False,
            "error": "nmap not found on PATH — install with: brew install nmap",
            "raw": "",
            "exit_code": None,
            "target": host,
            "preset": preset,
        }
    entry = _PRESETS.get(preset)
    if not entry:
        return {
            **base_err,
            "ok": False,
            "available": True,
            "error": f"Unknown preset: {preset!r}",
            "raw": "",
            "exit_code": None,
            "target": host,
            "preset": preset,
        }

    if not _nmap_run_lock.acquire(blocking=False):
        return {
            **base_err,
            "ok": False,
            "available": True,
            "error": "Another nmap scan is already running — wait for it to finish.",
            "raw": "",
            "exit_code": None,
            "target": host,
            "preset": preset,
        }

    extra, timeout_sec = entry
    args: List[str] = ["nmap", *extra, "-oX", "-", host]
    argv = list(args)
    t0 = time.monotonic()
    proc: Optional[subprocess.CompletedProcess[str]] = None
    try:
        try:
            proc = run_text(args, timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            duration_ms = int((time.monotonic() - t0) * 1000)
            return {
                "ok": False,
                "available": True,
                "error": f"nmap exceeded {timeout_sec:.0f}s timeout",
                "raw": f"(timeout after {timeout_sec:.0f}s)\n",
                "exit_code": -1,
                "target": host,
                "preset": preset,
                "duration_ms": duration_ms,
                "argv": argv,
                "scan": None,
                "xml_raw": None,
            }
        except FileNotFoundError:
            duration_ms = int((time.monotonic() - t0) * 1000)
            return {
                "ok": False,
                "available": False,
                "error": "nmap executable disappeared from PATH",
                "raw": "",
                "exit_code": None,
                "target": host,
                "preset": preset,
                "duration_ms": duration_ms,
                "argv": argv,
                "scan": None,
                "xml_raw": None,
            }
        duration_ms = int((time.monotonic() - t0) * 1000)
        xml_raw = (proc.stdout or "").strip()
        scan = _parse_nmap_xml(xml_raw) if xml_raw else {"hosts": [], "ports": []}
        raw = _stderr_or_summary(proc.stderr or "", scan, host)

        return {
            "ok": proc.returncode == 0,
            "available": True,
            "error": None,
            "raw": raw,
            "exit_code": proc.returncode,
            "target": host,
            "preset": preset,
            "duration_ms": duration_ms,
            "argv": argv,
            "scan": scan,
            "xml_raw": xml_raw if xml_raw else None,
        }
    finally:
        _nmap_run_lock.release()
