"""Advice from Wi‑Fi measurements — targets aligned with Ekahau, UniFi, and 802.11ax HE."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from analysis.thresholds import (
    AX_HE_MCS_MAX,
    AX_HE_MCS_MIN,
    RSSI_MIN_EXCELLENT,
    RSSI_MIN_FAIR,
    RSSI_MIN_GOOD,
    SNR_TARGET_DB,
    SNR_USABLE_MIN_DB,
    SignalQuality,
    classify_rssi,
)


def recommend_from_connection(data: Dict[str, Any]) -> List[str]:
    """Produce human-readable tips from current connection dict."""
    tips: List[str] = []
    rssi = data.get("rssi_dbm")
    quality = classify_rssi(rssi)
    ssid = data.get("ssid") or "this network"
    phy = str(data.get("phy_mode") or "").lower()

    if quality == SignalQuality.POOR:
        tips.append(
            f"RSSI to “{ssid}” is about {rssi} dBm (below about {RSSI_MIN_FAIR} dBm). "
            "UniFi guidance treats about −70 dBm as a practical stable floor and "
            "about −65 dBm as optimal; move closer to the AP or improve AP placement."
        )
    elif quality == SignalQuality.FAIR:
        tips.append(
            f"RSSI is about {rssi} dBm — between roughly {RSSI_MIN_GOOD} dBm (stable target) "
            f"and {RSSI_MIN_EXCELLENT} dBm (optimal). Real-time apps may be sensitive here; "
            "survey primary cells for about −65 to −70 dBm where clients actually sit."
        )

    noise = data.get("noise_dbm")
    if isinstance(rssi, int) and isinstance(noise, int):
        snr = rssi - noise
        if snr < SNR_USABLE_MIN_DB:
            tips.append(
                f"SNR is only ~{snr} dB (noise floor about {noise} dBm). Ekahau-style design "
                f"often targets about {SNR_TARGET_DB} dB SNR for robust higher MCS; reduce "
                "interference, widen channels only where UniFi density guidance allows, or "
                "improve RSSI."
            )
        elif snr < SNR_TARGET_DB:
            tips.append(
                f"SNR ~{snr} dB is usable but below a common design target of about {SNR_TARGET_DB} dB "
                "(Ekahau-style). Cleaner channels or stronger RSSI will help MCS and airtime."
            )

    rate = data.get("tx_rate_mbps")
    if isinstance(rate, (int, float)) and rate < 100 and quality != SignalQuality.EXCELLENT:
        if "ax" in phy or "11ax" in phy:
            tips.append(
                f"Negotiated PHY is about {rate:.0f} Mbps on 802.11ax — HE MCS runs about "
                f"{AX_HE_MCS_MIN}–{AX_HE_MCS_MAX}; low Mbps usually means weak RSSI/SNR, "
                "few spatial streams, narrow channel, or busy spectrum—not a single-number fault."
            )
        else:
            tips.append(
                f"Link rate is about {rate:.0f} Mbps — check RSSI/SNR and channel width; "
                "802.11ax clients can use HE MCS 0–11 when conditions allow."
            )

    band = str(data.get("band") or "")
    ch_w = str(data.get("channel_width") or "")
    if "2.4" in band and ch_w and "20" not in ch_w and "MHz" in ch_w:
        tips.append(
            "On 2.4 GHz, UniFi best practice is usually 20 MHz channel width to limit overlap; "
            "wider channels rarely help in dense environments."
        )

    if not tips:
        tips.append(
            f"RSSI/SNR look in a healthy band for typical use (targets: about ≥{RSSI_MIN_EXCELLENT} dBm "
            f"optimal, ≥{RSSI_MIN_GOOD} dBm stable; SNR often ≥{SNR_TARGET_DB} dB for headroom). "
            "Re-check under load and where clients actually roam."
        )

    return tips


def recommend_from_scan(network_rows: List[Dict[str, Any]], my_channel: Optional[int]) -> List[str]:
    """Suggest channel actions from nearby AP list."""
    tips: List[str] = []
    if my_channel is None or not network_rows:
        return tips

    same_channel = sum(1 for r in network_rows if r.get("channel") == my_channel)
    if same_channel >= 4:
        tips.append(
            f"Channel {my_channel} is busy ({same_channel} APs visible). UniFi-style practice "
            "is manual, non-overlapping 2.4 GHz plans (1/6/11) and measured 5/6 GHz reuse; "
            "survey before changing width or power."
        )

    n24 = sum(1 for r in network_rows if (r.get("band") or "").startswith("2.4"))
    n5 = sum(1 for r in network_rows if (r.get("band") or "").startswith("5"))
    if n24 > n5 * 2 and n24 > 6:
        tips.append(
            "2.4 GHz is crowded vs 5 GHz. Prefer 5/6 GHz-capable clients and band steering "
            "(UniFi) where appropriate; keep 2.4 GHz at 20 MHz in dense sites."
        )

    return tips
