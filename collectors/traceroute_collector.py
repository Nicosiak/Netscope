"""Traceroute via system binary."""

from __future__ import annotations

import subprocess
from typing import Any, Dict, List

from collectors._subprocess import run_text
from core.host_sanitize import normalize_diagnostic_host


def nonblank_traceroute_lines(raw: str) -> List[str]:
    return [ln.rstrip() for ln in raw.splitlines() if ln.strip()]


def traceroute(host: str = "8.8.8.8") -> Dict[str, Any]:
    """
    UDP traceroute, numeric hops. macOS typically does not require sudo.
    """
    h = normalize_diagnostic_host(host.strip())
    if not h:
        return {"host": host, "raw": "Invalid host.", "lines": []}

    result: Dict[str, Any] = {"host": h, "raw": "", "lines": []}
    try:
        p = run_text(["traceroute", "-n", "-q", "1", "-w", "2", h], timeout=120.0)
        raw = p.stdout or ""
        if not raw.strip() and p.stderr:
            raw = p.stderr
        result["raw"] = raw
        result["lines"] = nonblank_traceroute_lines(raw)
    except subprocess.TimeoutExpired:
        result["raw"] = "Traceroute timed out."
    except FileNotFoundError:
        result["raw"] = "traceroute not found on PATH."
    except Exception as e:
        result["raw"] = str(e)
    return result
