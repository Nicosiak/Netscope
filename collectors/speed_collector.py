"""networkQuality -c (JSON) macOS 12+."""

from __future__ import annotations

import json
import shutil
from typing import Any, Dict, Optional

from core.subproc import run_text

_MAX_RUNTIME_CLAMP = (20, 90)


def network_quality_available() -> bool:
    return shutil.which("networkQuality") is not None


def _clamp_max_runtime(sec: int) -> int:
    lo, hi = _MAX_RUNTIME_CLAMP
    return max(lo, min(hi, int(sec)))


def extract_metrics(data: Dict[str, Any]) -> Dict[str, Any]:
    """Stable UI fields from a ``run_network_quality`` result dict.

    Keys use ``.get`` for optional / version-varying JSON from ``networkQuality``.
    """
    out: Dict[str, Any] = {
        "dl_mbps": None,
        "ul_mbps": None,
        "responsiveness_rpm": None,
        "base_rtt_ms": None,
        "ul_responsiveness_rpm": None,
        "interface_name": None,
        "start_date": None,
        "end_date": None,
    }
    if not data.get("ok") or not isinstance(data.get("json"), dict):
        return out
    j = data["json"]

    dl = j.get("dl_throughput")
    ul = j.get("ul_throughput")
    if isinstance(dl, (int, float)):
        out["dl_mbps"] = float(dl) / 1_000_000
    if isinstance(ul, (int, float)):
        out["ul_mbps"] = float(ul) / 1_000_000

    resp = j.get("responsiveness")
    if isinstance(resp, (int, float)):
        out["responsiveness_rpm"] = float(resp)

    rtt = j.get("base_rtt")
    if isinstance(rtt, (int, float)):
        out["base_rtt_ms"] = float(rtt)

    ul_resp = j.get("ul_responsiveness")
    if ul_resp is None:
        ul_resp = j.get("upload_responsiveness")
    if isinstance(ul_resp, (int, float)):
        out["ul_responsiveness_rpm"] = float(ul_resp)

    iface = j.get("interface_name") or j.get("interface")
    if isinstance(iface, str) and iface.strip():
        out["interface_name"] = iface.strip()

    for key, out_key in (("start_date", "start_date"), ("end_date", "end_date")):
        v = j.get(key)
        if isinstance(v, str) and v.strip():
            out[out_key] = v.strip()

    return out


def run_network_quality(max_runtime_sec: Optional[int] = None) -> Dict[str, Any]:
    out: Dict[str, Any] = {"ok": False, "json": None, "raw": ""}
    if not network_quality_available():
        out["raw"] = "networkQuality not found (requires macOS 12+)."
        return out

    argv = ["networkQuality", "-c"]
    timeout = 120.0
    if max_runtime_sec is not None:
        m = _clamp_max_runtime(max_runtime_sec)
        argv.extend(["-M", str(m)])
        timeout = float(max(45, min(m + 35, 150)))

    stdout = ""
    try:
        proc = run_text(argv, timeout=timeout)
        stdout = (proc.stdout or "").strip()
        out["raw"] = stdout
        if stdout:
            out["json"] = json.loads(stdout)
            out["ok"] = True
    except json.JSONDecodeError as e:
        out["raw"] = f"Could not parse JSON: {e}\n{stdout[:500]}"
    except Exception as e:
        out["raw"] = str(e)
    return out


def summarize(data: Dict[str, Any]) -> str:
    if not data.get("ok") or not isinstance(data.get("json"), dict):
        return data.get("raw") or "No data."
    j = data["json"]
    lines = []
    m = extract_metrics(data)
    if m.get("interface_name"):
        lines.append(f"Interface: {m['interface_name']}")
    # Keys vary slightly by macOS version
    for key, label in (
        ("dl_throughput", "Download (Mbps)"),
        ("ul_throughput", "Upload (Mbps)"),
        ("responsiveness", "Responsiveness (RPM)"),
        ("base_rtt", "Idle latency (ms)"),
    ):
        if key in j:
            val = j[key]
            if key.endswith("throughput") and isinstance(val, (int, float)):
                lines.append(f"{label}: {val / 1_000_000:.1f}")
            else:
                lines.append(f"{label}: {val}")
    return "\n".join(lines) if lines else json.dumps(j, indent=2)
