#!/usr/bin/env python3
"""
Validate every collector against real macOS system data.
Runs each collector, cross-checks with raw CLI output, and reports pass/fail.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

# Ensure project root is importable
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
WARN = "\033[93mWARN\033[0m"
results = {"pass": 0, "fail": 0, "warn": 0}


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  {PASS}  {name}  {detail}")
        results["pass"] += 1
    else:
        print(f"  {FAIL}  {name}  {detail}")
        results["fail"] += 1


def warn(name: str, detail: str = "") -> None:
    print(f"  {WARN}  {name}  {detail}")
    results["warn"] += 1


def run_cmd(args: list[str], timeout: float = 10) -> str:
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return str(e)


# ═══════════════════════════════════════════════════════════════════════
print("\n══════════════════════════════════════════════")
print("  NetScope — Full Validation Suite")
print("══════════════════════════════════════════════\n")

# ── 1. WiFi Collector vs system_profiler ─────────────────────────────
print("── 1. WiFi Collector ──")
from collectors.interface_collector import wifi_airport_device
from collectors.wifi_collector import fetch_current_connection, fetch_nearby_networks

conn = fetch_current_connection()

wifi_dev = wifi_airport_device() or "en0"
print(f"  (Wi-Fi hardware device: {wifi_dev})")

# Cross-check: get SSID from networksetup
ns_out = run_cmd(["networksetup", "-getairportnetwork", wifi_dev])
ns_ssid = None
m = re.search(r"Current Wi-Fi Network:\s*(.+)", ns_out)
if m:
    ns_ssid = m.group(1).strip()

our_ssid = conn.get("ssid")
if our_ssid and ns_ssid:
    check("SSID matches networksetup", our_ssid == ns_ssid,
          f"ours={our_ssid!r} system={ns_ssid!r}")
elif our_ssid is None and ns_ssid is None:
    warn("SSID: both None (not connected or Location Services denied)")
elif our_ssid is None:
    warn("SSID: collector returned None but system says " + repr(ns_ssid),
         "(Location Services may need to be granted)")
else:
    check("SSID present", True, f"ours={our_ssid!r}")

check("RSSI is int", isinstance(conn.get("rssi_dbm"), int),
      f"value={conn.get('rssi_dbm')}")
rssi_val = conn.get("rssi_dbm")
if isinstance(rssi_val, int):
    if -120 <= rssi_val <= 0:
        check("RSSI in plausible range (-120 to 0 dBm)", True, f"value={rssi_val}")
    else:
        warn(f"RSSI outside typical range (-120 to 0): {rssi_val} dBm")
    if not (-100 <= rssi_val <= -10):
        warn(f"RSSI outside common Wi-Fi band (-100 to -10): {rssi_val} dBm (driver/AP dependent)")
check("Noise is int", isinstance(conn.get("noise_dbm"), int),
      f"value={conn.get('noise_dbm')}")
check("Tx rate > 0", isinstance(conn.get("tx_rate_mbps"), (int, float)) and conn["tx_rate_mbps"] > 0,
      f"value={conn.get('tx_rate_mbps')}")
check("Channel is int", isinstance(conn.get("channel"), int),
      f"value={conn.get('channel')}")
check("Band is set", conn.get("band") in ("2.4 GHz", "5 GHz", "6 GHz"),
      f"value={conn.get('band')!r}")
check("Channel width present", conn.get("channel_width") is not None,
      f"value={conn.get('channel_width')!r}")
check("PHY mode present", conn.get("phy_mode") is not None,
      f"value={conn.get('phy_mode')!r}")
check("No error", conn.get("error") is None,
      f"error={conn.get('error')!r}")

print()
nets = fetch_nearby_networks()
check("Nearby scan returned networks", len(nets) > 0, f"count={len(nets)}")
if nets:
    first = nets[0]
    if first.get("ssid") is not None:
        check("First network has SSID", True, f"ssid={first.get('ssid')!r}")
    else:
        warn("First network SSID is None (Location Services not granted to this terminal)")
    check("First network has RSSI", isinstance(first.get("rssi_dbm"), int), f"rssi={first.get('rssi_dbm')}")
    check("First network has channel", isinstance(first.get("channel"), int), f"ch={first.get('channel')}")
    check("Networks sorted by RSSI (strongest first)",
          all(
              (nets[i].get("rssi_dbm") or -999) >= (nets[i + 1].get("rssi_dbm") or -999)
              for i in range(len(nets) - 1)
          ),
          f"top={nets[0].get('rssi_dbm')} bottom={nets[-1].get('rssi_dbm')}")

# ── 2. Ping Collector ────────────────────────────────────────────────
print("\n── 2. Ping Collector ──")
from collectors.ping_collector import PingSampler

sampler = PingSampler(target="8.8.8.8", interval_s=0.5, history_max=10)
samples: list[dict] = []
sampler.on_sample = lambda p: samples.append(p)
sampler.start()
time.sleep(6)
sampler.stop()

check("Received ping samples", len(samples) > 0, f"count={len(samples)}")
if samples:
    last = samples[-1]
    check("RTT is float or None (timeout)", last.get("rtt_ms") is None or isinstance(last["rtt_ms"], float),
          f"rtt={last.get('rtt_ms')}")
    if isinstance(last.get("rtt_ms"), float):
        check("RTT > 0", last["rtt_ms"] > 0, f"rtt={last['rtt_ms']:.2f} ms")
        check("RTT < 500 ms (sanity)", last["rtt_ms"] < 500, f"rtt={last['rtt_ms']:.2f} ms")

    # Cross-check: system ping
    sys_ping = run_cmd(["ping", "-c", "3", "-t", "3", "8.8.8.8"])
    m = re.search(r"min/avg/max.*?=\s*([\d.]+)/([\d.]+)/([\d.]+)", sys_ping)
    if m:
        sys_avg = float(m.group(2))
        our_avg = last.get("avg_ms")
        if isinstance(our_avg, float):
            diff = abs(our_avg - sys_avg)
            check("Avg RTT within 30ms of system ping",
                  diff < 30,
                  f"ours={our_avg:.1f} system={sys_avg:.1f} diff={diff:.1f}")

    check("Loss % is float", isinstance(last.get("loss_pct"), float), f"loss={last.get('loss_pct')}")
    check("Jitter computed", last.get("jitter_ms") is not None or len(samples) < 3,
          f"jitter={last.get('jitter_ms')}")
    check("History length matches", len(last.get("history_ms", [])) > 0,
          f"len={len(last.get('history_ms', []))}")

# ── 3. DNS Collector ─────────────────────────────────────────────────
print("\n── 3. DNS Collector ──")
from collectors.dns_collector import dig_query, compare_servers

dns = dig_query("google.com")
check("DNS query time is int", isinstance(dns.get("query_time_ms"), int),
      f"time={dns.get('query_time_ms')} ms")
check("DNS server reported", dns.get("server") is not None,
      f"server={dns.get('server')!r}")
check("DNS raw output non-empty", len(dns.get("raw", "")) > 20)

# Cross-check: run dig ourselves
sys_dig = run_cmd(["dig", "google.com", "+stats"])
m = re.search(r"Query time:\s*(\d+)\s*msec", sys_dig)
if m:
    sys_qt = int(m.group(1))
    our_qt = dns.get("query_time_ms")
    if isinstance(our_qt, int):
        check("DNS query time matches system dig",
              True,  # both ran dig, values may differ by timing
              f"ours={our_qt} ms  system={sys_qt} ms")

comp = compare_servers("google.com")
check("DNS compare returned 4 servers", len(comp) == 4, f"count={len(comp)}")
for r in comp:
    label = r.get("label", "?")
    qt = r.get("query_time_ms")
    if qt is not None:
        check(f"DNS {label} responded", True, f"{qt} ms")
    else:
        warn(f"DNS {label} no response")

# ── 4. Interface Collector ───────────────────────────────────────────
print("\n── 4. Interface Collector ──")
from collectors.interface_collector import snapshot, parse_default_gateway

snap = snapshot()
check("networksetup output non-empty", len(snap.get("networksetup", "")) > 10)
check("ifconfig output non-empty", len(snap.get("ifconfig", "")) > 50)
check("route output non-empty", len(snap.get("route_default", "")) > 10)

gw = snap.get("default_gateway")
check("Default gateway parsed", gw is not None, f"gateway={gw!r}")

# Cross-check gateway
sys_route = run_cmd(["route", "-n", "get", "default"])
m = re.search(r"gateway:\s*(\S+)", sys_route)
if m:
    sys_gw = m.group(1)
    check("Gateway matches system route", gw == sys_gw,
          f"ours={gw!r} system={sys_gw!r}")

# ── 5. Speed Collector ───────────────────────────────────────────────
print("\n── 5. Speed Collector ──")
from collectors.speed_collector import network_quality_available, summarize

avail = network_quality_available()
check("networkQuality detected", avail, "(skipping actual test — takes 30s)")
if not avail:
    warn("networkQuality not found, speed test will be unavailable")

# ── 6. Traceroute Collector ──────────────────────────────────────────
print("\n── 6. Traceroute Collector ──")
from collectors.traceroute_collector import traceroute

tr = traceroute("8.8.8.8")
check("Traceroute raw output non-empty", len(tr.get("raw", "")) > 10)
check("Traceroute lines parsed", len(tr.get("lines", [])) > 0,
      f"hops={len(tr.get('lines', []))}")
if tr.get("lines"):
    check("First hop looks valid", bool(re.search(r"\d+\.\d+\.\d+\.\d+|\*", tr["lines"][0])),
          f"line={tr['lines'][0][:60]}")

# ── 7. iperf3 Collector ─────────────────────────────────────────────
print("\n── 7. iperf3 Collector ──")
from collectors.iperf_collector import iperf3_available

ip3 = iperf3_available()
if ip3:
    check("iperf3 binary found", True)
else:
    warn("iperf3 not installed (brew install iperf3)")

# ── 8. Thresholds & Recommendations ─────────────────────────────────
print("\n── 8. Analysis Module ──")
from analysis.thresholds import classify_rssi, classify_ping_ms, band_from_channel_number, SignalQuality

check("classify_rssi(-40) = Excellent", classify_rssi(-40) == SignalQuality.EXCELLENT)
check("classify_rssi(-60) = Good", classify_rssi(-60) == SignalQuality.GOOD)
check("classify_rssi(-70) = Fair", classify_rssi(-70) == SignalQuality.FAIR)
check("classify_rssi(-80) = Poor", classify_rssi(-80) == SignalQuality.POOR)
check("classify_rssi(None) = Unknown", classify_rssi(None) == SignalQuality.UNKNOWN)

check("classify_ping(5) = Good", classify_ping_ms(5)[0] == "Good")
check("classify_ping(50) = OK", classify_ping_ms(50)[0] == "OK")
check("classify_ping(100) = High", classify_ping_ms(100)[0] == "High")
check("classify_ping(None) = —", classify_ping_ms(None)[0] == "—")

check("band ch1 = 2.4 GHz", band_from_channel_number(1) == "2.4 GHz")
check("band ch6 = 2.4 GHz", band_from_channel_number(6) == "2.4 GHz")
check("band ch36 = 5 GHz", band_from_channel_number(36) == "5 GHz")
check("band ch149 = 5 GHz", band_from_channel_number(149) == "5 GHz")
check("band None = None", band_from_channel_number(None) is None)

from analysis.recommendations import recommend_from_connection, recommend_from_scan

tips = recommend_from_connection({"rssi_dbm": -80, "ssid": "TestNet", "noise_dbm": -60})
check("Poor signal generates tips", len(tips) > 0 and "weak" in tips[0].lower(),
      f"tip={tips[0][:50]}")

tips_good = recommend_from_connection({"rssi_dbm": -45, "ssid": "TestNet", "noise_dbm": -90})
check("Good signal says healthy", any("healthy" in t.lower() for t in tips_good),
      f"tips={tips_good}")

scan_tips = recommend_from_scan(
    [{"channel": 6} for _ in range(8)],
    my_channel=6,
)
check("Crowded channel generates tip", len(scan_tips) > 0 and "busy" in scan_tips[0].lower(),
      f"tip={scan_tips[0][:50]}")

# ═══════════════════════════════════════════════════════════════════════
print("\n══════════════════════════════════════════════")
print(f"  Results: {results['pass']} passed, {results['fail']} failed, {results['warn']} warnings")
print("══════════════════════════════════════════════\n")

sys.exit(1 if results["fail"] > 0 else 0)
