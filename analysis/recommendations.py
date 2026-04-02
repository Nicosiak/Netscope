"""Auto-generated advice from WiFi measurements."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from analysis.thresholds import SignalQuality, classify_rssi


def recommend_from_connection(data: Dict[str, Any]) -> List[str]:
    """Produce human-readable tips from current connection dict."""
    tips: List[str] = []
    rssi = data.get("rssi_dbm")
    quality = classify_rssi(rssi)
    ssid = data.get("ssid") or "this network"

    if quality == SignalQuality.POOR:
        tips.append(
            f"Signal to {ssid} is weak ({rssi} dBm). Move closer to the access point "
            "or switch to 5 GHz if available."
        )
    elif quality == SignalQuality.FAIR:
        tips.append(
            f"Signal is usable but marginal ({rssi} dBm). Video calls and gaming may stutter."
        )

    noise = data.get("noise_dbm")
    if isinstance(rssi, int) and isinstance(noise, int):
        snr = rssi - noise
        if snr < 25:
            tips.append(
                f"Low SNR (~{snr} dB). Channel noise ({noise} dBm) is high — "
                "check for interference or crowded channels."
            )

    rate = data.get("tx_rate_mbps")
    if isinstance(rate, (int, float)) and rate < 50 and quality != SignalQuality.EXCELLENT:
        tips.append(
            f"Link rate is modest ({rate:.0f} Mbps). Poor RSSI or busy spectrum may limit throughput."
        )

    if not tips:
        tips.append("Link looks healthy for typical use. Keep monitoring during peak usage.")

    return tips


def recommend_from_scan(network_rows: List[Dict[str, Any]], my_channel: Optional[int]) -> List[str]:
    """Suggest channel actions from nearby AP list."""
    tips: List[str] = []
    if my_channel is None or not network_rows:
        return tips

    same_channel = sum(1 for r in network_rows if r.get("channel") == my_channel)
    if same_channel >= 4:
        tips.append(
            f"Channel {my_channel} is busy ({same_channel} APs visible). "
            "Consider a clearer channel on the router."
        )

    # Count APs on 2.4 vs 5
    n24 = sum(1 for r in network_rows if (r.get("band") or "").startswith("2.4"))
    n5 = sum(1 for r in network_rows if (r.get("band") or "").startswith("5"))
    if n24 > n5 * 2 and n24 > 6:
        tips.append("2.4 GHz is crowded. Prefer 5 GHz for capacity if clients support it.")

    return tips
