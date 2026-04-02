"""networkQuality -c (JSON) macOS 12+."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any, Dict


def network_quality_available() -> bool:
    return shutil.which("networkQuality") is not None


def run_network_quality() -> Dict[str, Any]:
    out: Dict[str, Any] = {"ok": False, "json": None, "raw": ""}
    if not network_quality_available():
        out["raw"] = "networkQuality not found (requires macOS 12+)."
        return out
    stdout = ""
    try:
        proc = subprocess.run(
            ["networkQuality", "-c"],
            capture_output=True,
            text=True,
            timeout=120,
        )
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
