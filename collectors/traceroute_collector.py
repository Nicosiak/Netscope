"""Traceroute via system binary."""

from __future__ import annotations

import subprocess
from typing import Any, Dict


def traceroute(host: str = "8.8.8.8") -> Dict[str, Any]:
    """
    UDP traceroute, numeric hops. macOS typically does not require sudo.
    """
    result: Dict[str, Any] = {"host": host, "raw": "", "lines": []}
    try:
        p = subprocess.run(
            ["traceroute", "-n", "-q", "1", "-w", "2", host],
            capture_output=True,
            text=True,
            timeout=120,
        )
        raw = p.stdout or ""
        if not raw.strip() and p.stderr:
            raw = p.stderr
        result["raw"] = raw
        result["lines"] = [ln.rstrip() for ln in raw.splitlines() if ln.strip()]
    except subprocess.TimeoutExpired:
        result["raw"] = "Traceroute timed out."
    except FileNotFoundError:
        result["raw"] = "traceroute not found on PATH."
    except Exception as e:
        result["raw"] = str(e)
    return result
