# NetScope

macOS desktop WiFi signal analyzer and network diagnostics tool. Dark-themed UI inspired by Ubiquiti WiFiman.

## Features

**Signal Tab**
- Real-time RSSI chart (60s rolling window)
- PHY summary: signal, mode (802.11ax/ac/n), band, channel width, link speed
- Connected AP card with BSSID, SNR, security
- WiFi Speed Factors (Spectrum, Radio Potential, Channel Health)
- Channel congestion chart (2.4 GHz + 5 GHz)
- Nearby networks table (hidden SSIDs filtered, count shown)
- Auto-generated recommendations

**Ping Tab**
- Continuous ICMP ping (Google, Cloudflare, router, custom)
- Live RTT chart with loss markers
- Stats: current, min, avg, max, jitter, packet loss %

**Diagnostics Tab**
- DNS comparison: system DNS vs Google vs Cloudflare vs Quad9 with bar chart
- Speed test via `networkQuality` (macOS 12+)
- LAN throughput via `iperf3` (download + upload)
- Traceroute with hop table
- Network interface info (IP, gateway, DNS, ARP, ifconfig)

**General**
- Persistent status bar (SSID, RSSI, channel, ping, loss)
- CSV export on Signal and Ping tabs
- WiFiman-inspired dark color palette

## Requirements

- macOS 12+ with Python 3.11+
- Location Services recommended (for SSID/BSSID visibility)
- Optional: `brew install iperf3` for LAN throughput testing

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
source .venv/bin/activate
python main.py
```

## Test

Fast unit tests (no live network; safe in CI):

```bash
pytest tests/test_thresholds.py tests/test_recommendations.py tests/test_interface_collector.py tests/test_dns_collector.py -q
```

Full integration validation against this Mac (Wi‑Fi, ping, dig, route, etc.):

```bash
python tests/validate_all.py
```

Optional developer smoke script (writes `report.txt`; gitignored):

```bash
python tests/simulate_output.py
```

## Tech Stack

- **GUI**: customtkinter (dark mode)
- **WiFi data**: CoreWLAN via PyObjC
- **Ping**: icmplib (unprivileged ICMP)
- **Charts**: matplotlib + FigureCanvasTkAgg
- **CLI tools**: dig, traceroute, networkQuality, iperf3, ifconfig, networksetup
