"""WiFi metrics via CoreWLAN (PyObjC). macOS only."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, List, Optional

try:
    import CoreWLAN
except ImportError:  # pragma: no cover
    CoreWLAN = None  # type: ignore

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
    4: "802.11n", 5: "802.11ac", 6: "802.11ax",
    # macOS 15+ may use bitflags; map known values
    16: "802.11n", 32: "802.11ac", 64: "802.11ax",
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


def _security_label(net: Any) -> str:
    try:
        mode = net.securityType()
        if mode is None:
            return "—"
        fn = getattr(CoreWLAN, "stringForSecurityMode_", None)
        if callable(fn):
            return str(fn(mode))
        return str(mode)
    except Exception:
        return "—"


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
                "band": None,
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
                ch, band = _channel_info(net.wlanChannel())
                row["channel"] = ch
                row["band"] = band
            except Exception:
                pass
            row["security"] = _security_label(net)
            networks.append(row)
    except Exception:
        return networks

    networks.sort(key=lambda x: (x.get("rssi_dbm") or -999), reverse=True)
    return networks


class WiFiPoller:
    """Background poller; invokes callback on main thread via queue_fn (e.g. root.after)."""

    def __init__(
        self,
        interval_s: float = 2.0,
        queue_fn: Optional[Callable[[Callable[[], None]], None]] = None,
    ) -> None:
        self.interval_s = interval_s
        self.queue_fn = queue_fn or (lambda f: f())
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def snapshot(self) -> Dict[str, Any]:
        conn = fetch_current_connection()
        nets = fetch_nearby_networks()
        return {"connection": conn, "networks": nets, "ts": time.time()}

    def _loop(self) -> None:
        while not self._stop.is_set():
            data = self.snapshot()

            def push(d: Dict[str, Any] = data) -> None:
                if self.on_data:
                    self.on_data(d)

            try:
                self.queue_fn(push)
            except Exception:
                pass
            self._stop.wait(self.interval_s)

    on_data: Optional[Callable[[Dict[str, Any]], None]] = None

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
