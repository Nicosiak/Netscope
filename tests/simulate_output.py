#!/usr/bin/env python3
"""
Simulate NetScope output — collects all data each tab would display,
prints a formatted report, and saves to report.txt.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from analysis.thresholds import classify_rssi, classify_ping_ms, rssi_color_hex, SignalQuality
from analysis.recommendations import recommend_from_connection, recommend_from_scan
from collectors.wifi_collector import fetch_current_connection, fetch_nearby_networks
from collectors.ping_collector import PingSampler
from collectors.dns_collector import compare_servers
from collectors.interface_collector import snapshot as iface_snapshot
from collectors.speed_collector import network_quality_available
from collectors.traceroute_collector import traceroute
from collectors.iperf_collector import iperf3_available

SEP = "─" * 60
DSEP = "═" * 60

lines: list[str] = []


def out(text: str = "") -> None:
    print(text)
    lines.append(text)


# ═══════════════════════════════════════════════════════════════
out(DSEP)
out("  NETSCOPE — Simulated Output Report")
out(f"  Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
out(DSEP)

# ── SIGNAL TAB ────────────────────────────────────────────────
out()
out(f"  ▸ SIGNAL TAB")
out(SEP)

conn = fetch_current_connection()
q = classify_rssi(conn.get("rssi_dbm"))

out()
out("  CONNECTION")
out(f"    Signal      {conn.get('rssi_dbm', '—')} dBm")
out(f"    PHY Mode    {conn.get('phy_mode', '—')}")
out(f"    Band        {conn.get('band', '—')}")
out(f"    Width       {conn.get('channel_width', '—')}")
out(f"    PHY Speed   {conn.get('tx_rate_mbps', '—')} Mbps")

out()
out("  CONNECTED AP")
out(f"    SSID        {conn.get('ssid') or '— (Location Services needed)'}")
out(f"    BSSID       {conn.get('bssid') or '—'}")
out(f"    RSSI        {conn.get('rssi_dbm', '—')} dBm  [{q.value}]")
noise = conn.get("noise_dbm")
rssi = conn.get("rssi_dbm")
if isinstance(rssi, int) and isinstance(noise, int):
    out(f"    SNR         {rssi - noise} dB")
else:
    out(f"    SNR         —")
out(f"    Security    {conn.get('security', '—')}")

out()
out("  WIFI SPEED FACTORS")
band = conn.get("band") or ""
ch_w = conn.get("channel_width") or ""
phy = conn.get("phy_mode") or ""
ch = conn.get("channel")

if "5" in band or "6" in band:
    spec = "Excellent" if any(w in ch_w for w in ("80", "160", "320")) else "Good"
elif "2.4" in band:
    spec = "Fair"
else:
    spec = "—"
out(f"    Spectrum         {spec:>10}    Band {band}  Width {ch_w}")

if "ax" in phy or "be" in phy:
    radio = "Excellent" if isinstance(rssi, int) and rssi >= -67 else ("Fair" if isinstance(rssi, int) and rssi < -75 else "Good")
elif "ac" in phy:
    radio = "Good"
else:
    radio = "Fair"
if isinstance(rssi, int) and rssi < -80:
    radio = "Poor"
out(f"    Radio Potential  {radio:>10}    Standard {phy}  Signal {rssi} dBm")

nets = fetch_nearby_networks()
same_ch = sum(1 for n in nets if n.get("channel") == ch) if ch else 0
if same_ch <= 2:
    ch_health = "Excellent"
elif same_ch <= 5:
    ch_health = "Good"
elif same_ch <= 8:
    ch_health = "Fair"
else:
    ch_health = "Poor"
out(f"    Channel Health   {ch_health:>10}    Channel {ch}  ({same_ch} APs)")

out()
out("  RECOMMENDATIONS")
tips = recommend_from_connection(conn) + recommend_from_scan(nets, ch if isinstance(ch, int) else None)
for t in tips:
    out(f"    • {t}")

out()
visible = [n for n in nets if n.get("ssid")]
hidden = len(nets) - len(visible)
out(f"  NEARBY NETWORKS  ({len(visible)} visible, {hidden} hidden)")
out(f"    {'Network':<28} {'Signal':>8}  {'Ch':>4}  {'Band':<8}  {'Security'}")
out(f"    {'─'*28} {'─'*8}  {'─'*4}  {'─'*8}  {'─'*16}")
for n in visible[:15]:
    ssid = str(n.get("ssid") or "")[:28]
    r = n.get("rssi_dbm")
    r_str = f"{r} dBm" if r is not None else "—"
    out(f"    {ssid:<28} {r_str:>8}  {str(n.get('channel') or '—'):>4}  {str(n.get('band') or '—'):<8}  {str(n.get('security') or '—')}")

# ── CHANNEL CONGESTION ────────────────────────────────────────
out()
out("  CHANNEL CONGESTION")
from collections import Counter
ch_24: Counter[int] = Counter()
ch_5: Counter[int] = Counter()
for n in nets:
    c = n.get("channel")
    b = n.get("band") or ""
    if c is None:
        continue
    if b.startswith("2.4") or (1 <= c <= 14):
        ch_24[c] += 1
    elif b.startswith("5") or (32 <= c <= 177):
        ch_5[c] += 1

out(f"    2.4 GHz: {dict(sorted(ch_24.items())) if ch_24 else 'No APs'}")
out(f"    5 GHz:   {dict(sorted(ch_5.items())) if ch_5 else 'No APs'}")

# ── PING TAB ─────────────────────────────────────────────────
out()
out(f"  ▸ PING TAB")
out(SEP)

out()
out("  Collecting 10 ping samples to 8.8.8.8...")
sampler = PingSampler(target="8.8.8.8", interval_s=0.5, history_max=10)
samples: list[dict] = []
sampler.on_sample = lambda p: samples.append(p)
sampler.start()
time.sleep(6)
sampler.stop()

if samples:
    last = samples[-1]
    out()
    out("  STATISTICS")
    out(f"    Target      8.8.8.8")
    out(f"    Current     {last.get('rtt_ms', '—'):.1f} ms" if isinstance(last.get("rtt_ms"), float) else f"    Current     timeout")
    out(f"    Min         {last.get('min_ms', '—'):.1f} ms" if isinstance(last.get("min_ms"), float) else f"    Min         —")
    out(f"    Avg         {last.get('avg_ms', '—'):.1f} ms" if isinstance(last.get("avg_ms"), float) else f"    Avg         —")
    out(f"    Max         {last.get('max_ms', '—'):.1f} ms" if isinstance(last.get("max_ms"), float) else f"    Max         —")
    out(f"    Jitter      {last.get('jitter_ms', '—'):.1f} ms" if isinstance(last.get("jitter_ms"), float) else f"    Jitter      —")
    out(f"    Loss        {last.get('loss_pct', 0):.1f}%")

    out()
    out("  LATENCY GRAPH (text sparkline)")
    hist = last.get("history_ms", [])
    bars = []
    for v in hist:
        if v is None:
            bars.append("X")
        elif v < 15:
            bars.append("▁")
        elif v < 30:
            bars.append("▃")
        elif v < 60:
            bars.append("▅")
        elif v < 100:
            bars.append("▇")
        else:
            bars.append("█")
    out(f"    {''.join(bars)}  ({len(hist)} samples)")

# ── DIAGNOSTICS TAB ──────────────────────────────────────────
out()
out(f"  ▸ DIAGNOSTICS TAB")
out(SEP)

out()
out("  DNS COMPARISON")
dns_results = compare_servers("google.com")
out(f"    {'Server':<28} {'Query Time':>12}")
out(f"    {'─'*28} {'─'*12}")
for r in dns_results:
    qt = r.get("query_time_ms")
    qt_str = f"{qt} ms" if qt is not None else "failed"
    out(f"    {r.get('label', '?'):<28} {qt_str:>12}")

out()
out("  SPEED TEST")
if network_quality_available():
    out("    networkQuality: available (not running — takes 30s)")
else:
    out("    networkQuality: NOT FOUND (requires macOS 12+)")

out()
out("  IPERF3")
if iperf3_available():
    out("    iperf3: installed and available")
else:
    out("    iperf3: NOT FOUND (brew install iperf3)")

out()
out("  TRACEROUTE to 8.8.8.8")
tr = traceroute("8.8.8.8")
for line in (tr.get("lines") or [])[:12]:
    out(f"    {line}")

out()
out("  INTERFACE INFO")
snap = iface_snapshot()
gw = snap.get("default_gateway")
out(f"    Default Gateway: {gw}")
# Parse key info from networksetup
ns = snap.get("networksetup", "")
for line in ns.splitlines():
    line = line.strip()
    if any(k in line for k in ("IP address", "Subnet mask", "Router", "DNS")):
        out(f"    {line}")

# ── STATUS BAR ───────────────────────────────────────────────
out()
out(SEP)
out(f"  STATUS BAR:  {conn.get('ssid') or '—'}  |  {conn.get('rssi_dbm', '—')} dBm  |  Ch {conn.get('channel', '—')} {conn.get('band', '')}  |  Ping {samples[-1].get('rtt_ms', '—'):.0f} ms  |  Loss {samples[-1].get('loss_pct', 0):.1f}%" if samples and isinstance(samples[-1].get("rtt_ms"), float) else "  STATUS BAR:  (no data)")
out(DSEP)

# Save report
report_path = os.path.join(_ROOT, "report.txt")
with open(report_path, "w") as f:
    f.write("\n".join(lines) + "\n")
out(f"\nReport saved to: {report_path}")
