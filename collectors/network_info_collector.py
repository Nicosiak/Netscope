"""Network info collector — gateway, DNS, public IP, Wi-Fi details, proxy.

Designed to be called from a thread-pool executor; all subprocess calls have
timeouts and the three external HTTP lookups run in parallel.

Vendor lookups are cached per OUI (first 3 octets of the MAC/BSSID) for the
lifetime of the process so repeated Info tab opens don't hit the external API.
"""

from __future__ import annotations

import concurrent.futures
import json as _json
import re
import subprocess
import threading
import urllib.request
from typing import Any, Dict, List, Optional

# ── Vendor cache (OUI → vendor string) ───────────────────────────────
_vendor_lock: threading.Lock = threading.Lock()
_vendor_cache: Dict[str, Optional[str]] = {}


def _lookup_vendor(bssid_or_mac: str) -> Optional[str]:
    """Return vendor name for a MAC/BSSID, cached by OUI."""
    try:
        first_byte = int(bssid_or_mac.replace("-", ":").split(":")[0], 16)
    except (ValueError, IndexError):
        return None
    if first_byte & 0x02:
        return "Randomized / Local"

    oui = bssid_or_mac.replace(":", "-")[:8].upper()
    with _vendor_lock:
        if oui in _vendor_cache:
            return _vendor_cache[oui]

    # Fetch outside the lock so concurrent callers don't serialize
    result: Optional[str] = None
    try:
        url = f"https://api.macvendors.com/{oui}"
        req = urllib.request.Request(url, headers={"User-Agent": "netscope/1.0"})
        with urllib.request.urlopen(req, timeout=4) as r:
            result = r.read().decode().strip() or None
    except Exception:
        pass

    with _vendor_lock:
        _vendor_cache[oui] = result
    return result


def _public_ip() -> Optional[str]:
    try:
        with urllib.request.urlopen("https://api.ipify.org?format=json", timeout=5) as r:
            return _json.loads(r.read())["ip"]
    except Exception:
        return None


def _public_ipv6() -> Optional[str]:
    try:
        with urllib.request.urlopen("https://api6.ipify.org?format=json", timeout=5) as r:
            return _json.loads(r.read())["ip"]
    except Exception:
        return None


def fetch() -> Dict[str, Any]:
    """Collect network info and return a serialisable dict."""
    info: Dict[str, Any] = {
        # Connection
        "gateway": None,
        "gateway_v6": None,
        "dns_servers": [],
        "dns_v6": [],
        "public_ip": None,
        "public_ipv6": None,
        "http_proxy": "None",
        # Wi-Fi
        "wifi_connected": False,
        "wifi_ssid": None,
        "wifi_bssid": None,
        "wifi_vendor": None,
        "wifi_security": None,
        "private_ip": None,
        "subnet_mask": None,
        "subnet_cidr": None,
        "ipv6_addresses": [],
        "mac": None,
    }

    # ── Default gateway (IPv4) ────────────────────────────────────
    iface_name = "en0"
    try:
        out = subprocess.check_output(
            ["route", "-n", "get", "default"], text=True, timeout=3, stderr=subprocess.DEVNULL
        )
        m = re.search(r"gateway:\s+(\S+)", out)
        if m:
            info["gateway"] = m.group(1)
        m = re.search(r"interface:\s+(\S+)", out)
        if m:
            iface_name = m.group(1)
    except Exception:
        pass

    # ── Default gateway (IPv6) — skip VPN tunnel interfaces ──────
    try:
        out = subprocess.check_output(
            ["netstat", "-rn", "-f", "inet6"], text=True, timeout=3, stderr=subprocess.DEVNULL
        )
        for line in out.splitlines():
            parts = line.split()
            if parts and parts[0] == "default" and len(parts) >= 2:
                gw = parts[1]
                if not gw.startswith("fe80"):
                    info["gateway_v6"] = gw
                    break
    except Exception:
        pass

    # ── ifconfig: private IP, subnet, MAC, IPv6 ──────────────────
    try:
        out = subprocess.check_output(
            ["ifconfig", iface_name], text=True, timeout=3, stderr=subprocess.DEVNULL
        )
        m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", out)
        if m:
            info["private_ip"] = m.group(1)
        m = re.search(r"netmask (0x[0-9a-f]+)", out)
        if m:
            n = int(m.group(1), 16)
            info["subnet_mask"] = ".".join(str((n >> (24 - 8 * i)) & 0xFF) for i in range(4))
            info["subnet_cidr"] = f"/{bin(n).count('1')}"
        m = re.search(r"ether ([0-9a-f:]+)", out)
        if m:
            info["mac"] = m.group(1).upper()
        ipv6s = re.findall(r"inet6 ([0-9a-f:]+)(?:%\S+)? prefixlen", out)
        info["ipv6_addresses"] = [a for a in ipv6s if not a.startswith("fe80")]
    except Exception:
        pass

    # ── DNS servers ───────────────────────────────────────────────
    try:
        out = subprocess.check_output(
            ["scutil", "--dns"], text=True, timeout=3, stderr=subprocess.DEVNULL
        )
        all_dns: List[str] = list(dict.fromkeys(re.findall(r"nameserver\[\d+\] : (\S+)", out)))
        info["dns_servers"] = [s for s in all_dns if ":" not in s][:4]
        info["dns_v6"] = [s for s in all_dns if ":" in s][:4]
    except Exception:
        pass

    # ── HTTP Proxy ────────────────────────────────────────────────
    try:
        out = subprocess.check_output(
            ["scutil", "--proxy"], text=True, timeout=3, stderr=subprocess.DEVNULL
        )
        http_on  = re.search(r"HTTPEnable\s*:\s*(\d+)", out)
        https_on = re.search(r"HTTPSEnable\s*:\s*(\d+)", out)
        http_host = re.search(r"HTTPProxy\s*:\s*(\S+)", out)
        http_port = re.search(r"HTTPPort\s*:\s*(\d+)", out)
        if (http_on and http_on.group(1) == "1") or (https_on and https_on.group(1) == "1"):
            proxy_host = http_host.group(1) if http_host else "?"
            port = http_port.group(1) if http_port else ""
            info["http_proxy"] = f"{proxy_host}:{port}" if port else proxy_host
        else:
            info["http_proxy"] = "None"
    except Exception:
        pass

    # ── Wi-Fi connection info ─────────────────────────────────────
    try:
        from collectors.wifi_collector import (  # type: ignore[attr-defined]
            _SEC_NAMES,
            fetch_current_connection,
        )
        conn = fetch_current_connection()
        has_rssi = isinstance(conn.get("rssi_dbm"), int) and conn["rssi_dbm"] != 0
        info["wifi_connected"] = bool(conn.get("ssid")) or has_rssi
        info["wifi_ssid"]  = conn.get("ssid")
        info["wifi_bssid"] = conn.get("bssid")
        raw_sec = conn.get("security")
        try:
            info["wifi_security"] = _SEC_NAMES.get(int(raw_sec), raw_sec)
        except (TypeError, ValueError):
            info["wifi_security"] = raw_sec
    except Exception:
        pass

    # ── External lookups (parallel) ───────────────────────────────
    bssid = info.get("wifi_bssid") or info.get("mac")
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        f_vendor = pool.submit(_lookup_vendor, bssid) if bssid else None
        f_ip4    = pool.submit(_public_ip)
        f_ip6    = pool.submit(_public_ipv6)
        if f_vendor:
            info["wifi_vendor"] = f_vendor.result()
        info["public_ip"]   = f_ip4.result()
        info["public_ipv6"] = f_ip6.result()

    return info
