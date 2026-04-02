"""Interface and routing info via macOS CLI."""

from __future__ import annotations

import re
import subprocess
from typing import Any, Dict, List, Optional


def _run(args: List[str], timeout: float = 10.0) -> str:
    try:
        p = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return f"(error running {' '.join(args)}: {e})"


def default_wifi_service_name() -> str:
    # Prefer English "Wi-Fi" on macOS US
    for name in ("Wi-Fi", "Ethernet"):
        out = _run(["networksetup", "-listallnetworkservices"])
        if name in out:
            return name
    return "Wi-Fi"


def networksetup_info(service: Optional[str] = None) -> str:
    svc = service or default_wifi_service_name()
    return _run(["networksetup", "-getinfo", svc])


def ifconfig_all() -> str:
    return _run(["ifconfig"])


def route_default() -> str:
    return _run(["route", "-n", "get", "default"])


def arp_table() -> str:
    return _run(["arp", "-a"])


def parse_default_gateway(route_text: str) -> Optional[str]:
    m = re.search(r"^\s*gateway:\s*(\S+)", route_text, re.MULTILINE)
    if m:
        return m.group(1)
    return None


def wifi_airport_device() -> Optional[str]:
    """Return the hardware interface name (e.g. en0) for Wi-Fi / AirPort.

    Parsed from ``networksetup -listallhardwareports``. Returns None if not found.
    """
    out = _run(["networksetup", "-listallhardwareports"])
    lines = out.splitlines()
    for i, line in enumerate(lines):
        if not line.strip().startswith("Hardware Port:"):
            continue
        if not any(x in line for x in ("Wi-Fi", "AirPort", "WLAN")):
            continue
        for j in range(i + 1, min(i + 8, len(lines))):
            m = re.match(r"^\s*Device:\s*(\S+)\s*$", lines[j])
            if m:
                return m.group(1)
    return None


def snapshot() -> Dict[str, Any]:
    r_default = route_default()
    return {
        "networksetup": networksetup_info(),
        "ifconfig": ifconfig_all(),
        "route_default": r_default,
        "default_gateway": parse_default_gateway(r_default),
        "arp": arp_table(),
    }
