"""iperf3 throughput testing via subprocess."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any, Callable, Dict, Optional

from core.host_sanitize import normalize_diagnostic_host

_MAX_CAPTURE_CHARS = 2_000_000


def iperf3_available() -> bool:
    return shutil.which("iperf3") is not None


def run_iperf3(
    server: str,
    duration: int = 10,
    reverse: bool = False,
    udp: bool = False,
    on_line: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Run iperf3 client against *server*.
    reverse=True measures download (server→client).
    Returns parsed JSON results or raw output.
    """
    out: Dict[str, Any] = {"ok": False, "json": None, "raw": "", "server": server}
    if not iperf3_available():
        out["raw"] = "iperf3 not found. Install with: brew install iperf3"
        return out

    norm = normalize_diagnostic_host(server.strip())
    if not norm:
        out["raw"] = "Invalid server hostname or IP."
        return out
    out["server"] = norm

    cmd = ["iperf3", "-c", norm, "-t", str(duration), "-J"]
    if reverse:
        cmd.append("-R")
    if udp:
        cmd.extend(["-u", "-b", "0"])

    proc: subprocess.Popen[str] | None = None
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        stdout_parts: list[str] = []
        captured = 0
        truncated = False
        if proc.stdout:
            for line in proc.stdout:
                stdout_parts.append(line)
                captured += len(line)
                if on_line:
                    on_line(line.rstrip())
                if captured >= _MAX_CAPTURE_CHARS:
                    truncated = True
                    break
        assert proc is not None
        if truncated:
            proc.kill()
            try:
                proc.wait(timeout=5.0)
            except Exception:
                pass
            raw = "".join(stdout_parts)
            raw = (raw + "\n[output truncated]") if raw.strip() else "[output truncated]"
        else:
            try:
                proc.wait(timeout=float(duration) + 30.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=5.0)
                except Exception:
                    pass
            raw = "".join(stdout_parts)
        stderr = ""
        if proc.stderr:
            try:
                stderr = proc.stderr.read()
            except Exception:
                stderr = ""
        if not raw.strip() and stderr:
            raw = stderr
        out["raw"] = raw

        if raw.strip().startswith("{"):
            data = json.loads(raw)
            out["json"] = data
            out["ok"] = True
    except json.JSONDecodeError as e:
        out["raw"] = f"JSON parse error: {e}"
    except Exception as e:
        out["raw"] = str(e)
    return out


def summarize_result(data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract key metrics from iperf3 JSON result."""
    summary: Dict[str, Any] = {
        "bits_per_second": None,
        "mbps": None,
        "retransmits": None,
        "jitter_ms": None,
        "lost_percent": None,
        "duration_s": None,
    }
    j = data.get("json")
    if not isinstance(j, dict):
        return summary

    end = j.get("end", {})

    # TCP
    tcp_sent = end.get("sum_sent", {})
    tcp_recv = end.get("sum_received", {})

    if tcp_recv.get("bits_per_second"):
        bps = tcp_recv["bits_per_second"]
    elif tcp_sent.get("bits_per_second"):
        bps = tcp_sent["bits_per_second"]
    else:
        bps = None

    if bps is not None:
        summary["bits_per_second"] = bps
        summary["mbps"] = bps / 1_000_000

    summary["retransmits"] = tcp_sent.get("retransmits")
    summary["duration_s"] = tcp_sent.get("seconds") or tcp_recv.get("seconds")

    # UDP
    udp_sum = end.get("sum", {})
    if udp_sum.get("jitter_ms") is not None:
        summary["jitter_ms"] = udp_sum["jitter_ms"]
    if udp_sum.get("lost_percent") is not None:
        summary["lost_percent"] = udp_sum["lost_percent"]
    if udp_sum.get("bits_per_second") and bps is None:
        bps = udp_sum["bits_per_second"]
        summary["bits_per_second"] = bps
        summary["mbps"] = bps / 1_000_000

    return summary
