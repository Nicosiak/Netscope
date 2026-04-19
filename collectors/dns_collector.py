"""DNS checks using dig, including multi-server comparison."""

from __future__ import annotations

import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from core.subproc import merged_output, run_text

_ANSWER_COUNT_RE = re.compile(r",\s*ANSWER:\s*(\d+),", re.IGNORECASE)


def dig_available() -> bool:
    return shutil.which("dig") is not None


def _parse_answer_count(raw: str) -> Optional[int]:
    m = _ANSWER_COUNT_RE.search(raw)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _parse_answer_records(raw: str) -> List[Dict[str, str]]:
    """Parse ``;; ANSWER SECTION:`` RRs (A, AAAA, CNAME, …)."""
    records: List[Dict[str, str]] = []
    lines = raw.splitlines()
    in_section = False
    for line in lines:
        if ";; ANSWER SECTION:" in line:
            in_section = True
            continue
        if in_section:
            ls = line.strip()
            if ls.startswith(";;"):
                break
            if not ls or ls.startswith(";"):
                continue
            parts = line.split()
            if len(parts) < 5 or parts[2] != "IN":
                continue
            rtype = parts[3]
            if rtype not in ("A", "AAAA", "CNAME", "TXT", "PTR", "MX", "NS", "SOA"):
                continue
            records.append(
                {
                    "name": parts[0].rstrip("."),
                    "ttl": parts[1],
                    "type": rtype,
                    "data": " ".join(parts[4:]),
                }
            )
    return records


def dig_query(
    domain: str = "google.com",
    server: Optional[str] = None,
    record_type: str = "A",
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "domain": domain,
        "server_queried": server,
        "record_type": (record_type or "A").upper(),
        "raw": "",
        "query_time_ms": None,
        "server": None,
        "answers": [],
        "answer_count": None,
        "dig_available": dig_available(),
    }
    if not out["dig_available"]:
        out["raw"] = "dig not found on PATH (install Xcode CLT or bind-utils)."
        return out

    qtype = "AAAA" if out["record_type"] == "AAAA" else "A"
    cmd = [
        "dig",
        "+time=2",
        "+tries=1",
        "+retry=0",
    ]
    if server:
        cmd.append(f"@{server}")
    cmd += [domain, qtype, "+noall", "+answer", "+comments", "+stats"]
    try:
        p = run_text(cmd, timeout=10.0)
        raw = merged_output(p)
        out["raw"] = raw
        m = re.search(r";\s*SERVER:\s*([^\#]+)", raw)
        if m:
            out["server"] = m.group(1).strip()
        m2 = re.search(r"Query time:\s*(\d+)\s*msec", raw, re.IGNORECASE)
        if m2:
            out["query_time_ms"] = int(m2.group(1))
        out["answer_count"] = _parse_answer_count(raw)
        out["answers"] = _parse_answer_records(raw)
    except Exception as e:
        out["raw"] = str(e)
    return out


def compare_servers(domain: str = "google.com", record_type: str = "A") -> List[Dict[str, Any]]:
    """Query multiple DNS servers in parallel and return results for comparison."""
    servers: List[tuple[Optional[str], str]] = [
        (None, "System DNS"),
        ("8.8.8.8", "Google (8.8.8.8)"),
        ("1.1.1.1", "Cloudflare (1.1.1.1)"),
        ("9.9.9.9", "Quad9 (9.9.9.9)"),
    ]

    def _one(pair: tuple[Optional[str], str]) -> Dict[str, Any]:
        srv, label = pair
        res = dig_query(domain, server=srv, record_type=record_type)
        res["label"] = label
        return res

    with ThreadPoolExecutor(max_workers=len(servers)) as pool:
        return list(pool.map(_one, servers))
