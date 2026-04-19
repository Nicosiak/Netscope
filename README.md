# NetScope

**Version:** see repo root [`VERSION`](VERSION). **History:** `git log` and tags.

**This file:** user-facing overview, setup, run, and testing. **Agent / editor rules:** [AGENTS.md](AGENTS.md). **Short path index (good first open for AI):** [docs/INVENTORY.md](docs/INVENTORY.md). **Full file map (Claude Code):** [CLAUDE.md](CLAUDE.md). **Architecture & security:** [docs/OVERVIEW.md](docs/OVERVIEW.md). **In-depth (diagrams, data flow):** [docs/PROJECT_DEEP_DIVE.md](docs/PROJECT_DEEP_DIVE.md). **Internal backlog:** [docs/BACKLOG.md](docs/BACKLOG.md).

macOS WiFi signal analyzer and network diagnostics tool. PyWebView + FastAPI web UI. Dark-themed, inspired by Ubiquiti WiFiman.

## Features

**Signal Tab**
- Real-time RSSI chart (rolling window)
- PHY summary: signal, mode (802.11ax/ac/n), band, channel width, link speed
- Connected AP card with BSSID, SNR, security
- Channel congestion chart (2.4 GHz + 5 GHz)
- Nearby networks table

**Ping Tab**
- Continuous ICMP ping (Google, Cloudflare, custom targets)
- Live RTT chart with loss markers and packet log
- Stats: current, min, avg, max, jitter, packet loss %

**Diagnostics Tab**
- DNS comparison: system DNS vs Google vs Cloudflare vs Quad9 with bar chart
- Speed test via `networkQuality` (macOS 12+)
- LAN throughput via `iperf3` (download + upload)
- Traceroute with hop table
- Network interface info (IP, gateway, DNS, ifconfig)

**Info Tab**
- Public IP, gateway, DNS servers, Wi-Fi identity, addressing details

**Security Tab**
- Optional **`nmap`**-based presets (local scans only; bounded CLI — see collectors / backend routes)

## Requirements

- macOS 12+ with **Python 3.12 or 3.13** recommended (3.11+ supported)
- Location Services recommended (for SSID/BSSID visibility)
- Optional: `brew install iperf3` for LAN throughput testing

## Setup

**Do not** `pip install` into **Homebrew's** `python3` — macOS will reject it (**PEP 668: externally-managed-environment**). Always use the project **venv** below (or `./scripts/setup_venv.sh`).

```bash
./scripts/setup_venv.sh
# or manually:
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

For development (pytest, coverage), also: `pip install -r requirements-dev.txt`.

## Run

From repo root (after **Setup**), simplest:

```bash
make run
```

Uses `.venv` via `scripts/run_app.sh`. Stop the app or free port **8765**:

```bash
make stop
```

Manual equivalent:

```bash
source .venv/bin/activate
python web/main.py
```

Opens a native PyWebView window at `http://127.0.0.1:8765`. If pywebview is not installed, open that URL in your browser and stop the server from the terminal (**Ctrl+C**).

## Test (local quality loop)

Install dev dependencies first (`requirements-dev.txt`: pytest, ruff, bandit, coverage, Hypothesis).

| Command | What it runs |
|--------|----------------|
| **CI equivalent (fast)** | `python -m pytest tests/ -q` |
| **Collectors vs real CLI** | On macOS: `python tests/validate_all.py` |

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt
ruff check web tests collectors core analysis
python -m compileall -q web tests collectors core analysis
pytest tests/ -q
```

Quick subset (analysis + DNS):

```bash
pytest tests/test_analysis.py tests/test_dns_collector.py -q
```

Full integration validation against this Mac (Wi-Fi, ping, dig, route, etc.):

```bash
python tests/validate_all.py
```

## Tech Stack

- **Web UI**: FastAPI + PyWebView (native window on macOS)
- **WiFi data**: CoreWLAN via PyObjC
- **Ping**: icmplib (unprivileged ICMP) with system `ping` fallback
- **CLI tools**: dig, traceroute, networkQuality, iperf3, ifconfig, networksetup
