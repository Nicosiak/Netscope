"""DNS checks using dig, including multi-server comparison."""

from __future__ import annotations

import re
import subprocess
from typing import Any, Dict, List, Optional


def dig_query(domain: str = "google.com", server: Optional[str] = None) -> Dict[str, Any]:
    out: Dict[str, Any] = {"domain": domain, "server_queried": server, "raw": "", "query_time_ms": None, "server": None}
    cmd = ["dig"]
    if server:
        cmd.append(f"@{server}")
    cmd += [domain, "+stats"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        raw = (p.stdout or "") + (p.stderr or "")
        out["raw"] = raw
        m = re.search(r";\s*SERVER:\s*([^\#]+)", raw)
        if m:
            out["server"] = m.group(1).strip()
        m2 = re.search(r"Query time:\s*(\d+)\s*msec", raw, re.IGNORECASE)
        if m2:
            out["query_time_ms"] = int(m2.group(1))
    except Exception as e:
        out["raw"] = str(e)
    return out


def compare_servers(domain: str = "google.com") -> List[Dict[str, Any]]:
    """Query multiple DNS servers and return results for comparison."""
    servers = [
        (None, "System DNS"),
        ("8.8.8.8", "Google (8.8.8.8)"),
        ("1.1.1.1", "Cloudflare (1.1.1.1)"),
        ("9.9.9.9", "Quad9 (9.9.9.9)"),
    ]
    results = []
    for srv, label in servers:
        res = dig_query(domain, server=srv)
        res["label"] = label
        results.append(res)
    return results
