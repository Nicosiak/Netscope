"""WiFi metrics via CoreWLAN (PyObjC). macOS only."""

from __future__ import annotations

import plistlib
import re
import subprocess
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import CoreWLAN
except ImportError:  # pragma: no cover
    CoreWLAN = None  # type: ignore


def _ssid_from_scutil(iface_name: str = "en0") -> Tuple[Optional[str], Optional[str]]:
    """Fallback SSID/BSSID reader via scutil CachedScanRecord.

    CoreWLAN hides ssid()/bssid() on macOS 12+ without Location Services.
    scutil reads the kernel-cached scan record which is not gated by location.
    Returns (ssid, bssid) or (None, None) on any failure.
    """
    try:
        out = subprocess.check_output(
            ["scutil"],
            input=f"show State:/Network/Interface/{iface_name}/AirPort\n".encode(),
            timeout=2,
            stderr=subprocess.DEVNULL,
        )
        m = re.search(r"CachedScanRecord : <data> (0x[0-9a-f]+)", out.decode())
        if not m:
            return None, None
        data = bytes.fromhex(m.group(1)[2:])
        pl = plistlib.loads(data)
        objs = pl["$objects"]

        def res(x: Any) -> Any:
            return objs[x.data] if isinstance(x, plistlib.UID) else x

        root = res(pl["$top"]["root"])
        keys = [res(k) for k in root["NS.keys"]]
        vals = [res(v) for v in root["NS.objects"]]
        d = dict(zip(keys, vals))
        ssid = d.get("SSID_STR") or None
        bssid = d.get("BSSID") or None
        return ssid, bssid
    except Exception:
        return None, None

from analysis.thresholds import band_from_channel_number


def _iface() -> Any:
    if CoreWLAN is None:
        return None
    client = CoreWLAN.CWWiFiClient.sharedWiFiClient()
    if client is None:
        return CoreWLAN.CWInterface.interface()
    iface = client.interface()
    if iface is None:
        iface = CoreWLAN.CWInterface.interface()
    return iface


def _channel_info(wlan_channel: Any) -> tuple[Optional[int], Optional[str]]:
    if wlan_channel is None:
        return None, None
    try:
        ch = int(wlan_channel.channelNumber())
    except Exception:
        ch = None
    band = None
    try:
        b = wlan_channel.channelBand()
        # kCWChannelBand2GHz, etc.
        if b == CoreWLAN.kCWChannelBand2GHz:
            band = "2.4 GHz"
        elif b == CoreWLAN.kCWChannelBand5GHz:
            band = "5 GHz"
        elif b == CoreWLAN.kCWChannelBand6GHz:
            band = "6 GHz"
    except Exception:
        band = band_from_channel_number(ch)
    if band is None and ch is not None:
        band = band_from_channel_number(ch)
    return ch, band


_PHY_NAMES = {
    0: "None",
    1: "802.11a", 2: "802.11b", 3: "802.11g",
    4: "802.11n", 5: "802.11ac", 6: "802.11ax", 7: "802.11be",
    # macOS 15+ may use bitflags; map known values
    16: "802.11n", 32: "802.11ac", 64: "802.11ax", 128: "802.11be",
}

_WIDTH_NAMES = {0: "20 MHz", 1: "40 MHz", 2: "80 MHz", 3: "160 MHz", 4: "320 MHz"}


def _phy_mode_str(iface: Any) -> Optional[str]:
    try:
        mode = iface.activePHYMode()
        if mode is None:
            return None
        m = int(mode)
        return _PHY_NAMES.get(m, f"mode({m})")
    except Exception:
        return None


def _channel_width_str(wlan_channel: Any) -> Optional[str]:
    if wlan_channel is None:
        return None
    try:
        w = int(wlan_channel.channelWidth())
        return _WIDTH_NAMES.get(w, f"{w}")
    except Exception:
        return None


_SEC_NAMES: dict[int, str] = {
    0: "Open",
    1: "WEP",
    2: "WPA",
    3: "WPA",
    4: "WPA2",
    5: "WPA2",
    6: "WPA Ent.",
    7: "WPA Ent.",
    8: "WPA2 Ent.",
    9: "WPA2 Ent.",
    10: "WPA3",
    11: "WPA3",
    12: "WPA2/3",
    13: "WEP",
}


def _security_label(net: Any) -> str:
    """Return a human-readable security label for a CWNetwork object."""
    try:
        mode = net.strongestSupportedSecurity()
        if mode is not None:
            return _SEC_NAMES.get(int(mode), "WPA2")
    except Exception:
        pass
    try:
        mode = net.securityType()
        if mode is not None:
            return _SEC_NAMES.get(int(mode), "?")
    except Exception:
        pass
    return "?"


def sort_networks_by_rssi(networks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Strongest RSSI first; missing RSSI sorts last."""
    return sorted(networks, key=lambda x: (x.get("rssi_dbm") or -999), reverse=True)


def fetch_current_connection() -> Dict[str, Any]:
    """Snapshot of the interface associated with Wi-Fi."""
    out: Dict[str, Any] = {
        "ssid": None,
        "bssid": None,
        "rssi_dbm": None,
        "noise_dbm": None,
        "tx_rate_mbps": None,
        "channel": None,
        "channel_width": None,
        "band": None,
        "phy_mode": None,
        "security": None,
        "error": None,
    }
    if CoreWLAN is None:
        out["error"] = "CoreWLAN not available (install pyobjc-framework-CoreWLAN on macOS)"
        return out

    iface = _iface()
    if iface is None:
        out["error"] = "No Wi-Fi interface found"
        return out

    try:
        out["ssid"] = iface.ssid()
    except Exception:
        pass
    try:
        out["bssid"] = iface.bssid()
    except Exception:
        pass

    # macOS 12+ hides ssid()/bssid() without Location Services — fall back to scutil
    if out["ssid"] is None or out["bssid"] is None:
        iface_name = "en0"
        try:
            iface_name = str(iface.interfaceName()) or "en0"
        except Exception:
            pass
        fb_ssid, fb_bssid = _ssid_from_scutil(iface_name)
        if out["ssid"] is None:
            out["ssid"] = fb_ssid
        if out["bssid"] is None:
            out["bssid"] = fb_bssid
    try:
        rssi = iface.rssiValue()
        if rssi is not None:
            out["rssi_dbm"] = int(rssi)
    except Exception:
        pass
    try:
        noise = iface.noiseMeasurement()
        if noise is not None:
            out["noise_dbm"] = int(noise)
    except Exception:
        pass
    try:
        rate = iface.transmitRate()
        if rate is not None:
            out["tx_rate_mbps"] = float(rate)
    except Exception:
        pass
    try:
        wlan_ch = iface.wlanChannel()
        ch, band = _channel_info(wlan_ch)
        out["channel"] = ch
        out["band"] = band
        out["channel_width"] = _channel_width_str(wlan_ch)
    except Exception:
        pass
    try:
        out["phy_mode"] = _phy_mode_str(iface)
    except Exception:
        pass
    try:
        iface_sec = iface.security()
        if iface_sec is not None:
            fn = getattr(CoreWLAN, "stringForSecurityMode_", None)
            out["security"] = str(fn(iface_sec)) if callable(fn) else str(iface_sec)
    except Exception:
        pass

    return out


def fetch_nearby_networks() -> List[Dict[str, Any]]:
    if CoreWLAN is None:
        return []
    iface = _iface()
    if iface is None:
        return []

    networks: List[Dict[str, Any]] = []
    try:
        result, err = iface.scanForNetworksWithName_error_(None, None)
        if err is not None:
            return networks
        if result is None:
            return networks
        for net in result:
            row: Dict[str, Any] = {
                "ssid": None,
                "bssid": None,
                "rssi_dbm": None,
                "channel": None,
                "channel_width": None,
                "band": None,
                "phy_mode": None,
                "security": None,
            }
            try:
                row["ssid"] = net.ssid()
            except Exception:
                pass
            try:
                row["bssid"] = net.bssid()
            except Exception:
                pass
            try:
                r = net.rssiValue()
                if r is not None:
                    row["rssi_dbm"] = int(r)
            except Exception:
                pass
            try:
                wlan_ch = net.wlanChannel()
                ch, band = _channel_info(wlan_ch)
                row["channel"] = ch
                row["band"] = band
                row["channel_width"] = _channel_width_str(wlan_ch)
            except Exception:
                pass
            try:
                phy = net.phyMode()
                if phy is not None:
                    row["phy_mode"] = _PHY_NAMES.get(int(phy))
            except Exception:
                pass
            # phyMode() is unreliable on scan results — derive from scanRecord IEs
            if row["phy_mode"] is None:
                try:
                    sr = net.scanRecord()
                    if sr:
                        if sr.get("HE_CAP") is not None:
                            row["phy_mode"] = "802.11ax"
                        elif sr.get("VHT_CAPS") is not None:
                            row["phy_mode"] = "802.11ac"
                        elif sr.get("HT_CAPS_IE") is not None:
                            row["phy_mode"] = "802.11n"
                except Exception:
                    pass
            row["security"] = _security_label(net)
            networks.append(row)
    except Exception:
        return networks

    return sort_networks_by_rssi(networks)


class WiFiPoller:
    """Background poller; invokes callback on main thread via queue_fn (e.g. root.after).

    Connection metrics refresh every ``interval_s``. Nearby scan runs at most every
    ``scan_interval_s`` (scan is the expensive CoreWLAN path).
    """

    def __init__(
        self,
        interval_s: float = 2.0,
        scan_interval_s: float = 15.0,
        queue_fn: Optional[Callable[[Callable[[], None]], None]] = None,
    ) -> None:
        self.interval_s = interval_s
        self.scan_interval_s = max(2.0, float(scan_interval_s))
        self.queue_fn = queue_fn or (lambda f: f())
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.on_data: Optional[Callable[[Dict[str, Any]], None]] = None

    def snapshot(self) -> Dict[str, Any]:
        """Full sample (connection + fresh scan); use for one-off reads, not the poller loop."""
        conn = fetch_current_connection()
        nets = fetch_nearby_networks()
        return {"connection": conn, "networks": nets, "ts": time.time()}

    def _loop(self) -> None:
        last_networks: List[Dict[str, Any]] = []
        last_scan_ts = 0.0
        while not self._stop.is_set():
            try:
                now = time.time()
                conn = fetch_current_connection()
                if last_scan_ts == 0.0 or (now - last_scan_ts) >= self.scan_interval_s:
                    last_networks = fetch_nearby_networks()
                    last_scan_ts = now
                data: Dict[str, Any] = {"connection": conn, "networks": last_networks, "ts": now}
            except Exception:
                last_scan_ts = 0.0
                self._stop.wait(self.interval_s)
                continue

            def push(d: Dict[str, Any] = data) -> None:
                cb = self.on_data
                if cb:
                    cb(d)

            try:
                self.queue_fn(push)
            except Exception:
                pass
            self._stop.wait(self.interval_s)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval_s + 1)
