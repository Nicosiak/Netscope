# NetScope — Claude Code Context

> Read this file first. It contains everything needed to work on this repo without exploring the codebase.

## What this is

macOS-only WiFi/network diagnostics **web app**. Python 3.11+ · FastAPI + WebSocket · PyWebView (native window) · CoreWLAN (PyObjC). Binds to `127.0.0.1:8765` only — no remote service. Version: see `VERSION` file.

Entry point: `web/main.py` → spawns uvicorn → opens PyWebView window (or print URL for browser).

**Run without long shell commands:** `make run` from repo root (uses `.venv`); `make stop` kills whatever is on port 8765. In Cursor/VS Code: **Terminal → Run Task… → NetScope: Run** (default build task), or **Run and Debug → NetScope (web/main.py)** for breakpoints.

### Claude Code skills (not `.agents/`)

Claude Code CLI loads skills only from **`~/.claude/skills/<name>/SKILL.md`** (all projects) or **this repo’s `.claude/skills/<name>/SKILL.md`** (project-only). It does **not** read `.agents/skills/`.

This repo includes **`frontend-design`** under `.claude/skills/frontend-design/`. Invoke with **`/frontend-design`** in Claude Code. If you add a new top-level `~/.claude/skills` directory, restart the CLI once so it starts watching it.

---

## Exact file map

```
collectors/
  wifi_collector.py       CoreWLAN metrics (RSSI, SNR, PHY, channel, band); scutil SSID/BSSID fallback
  ping_collector.py       PingSampler class (Tk-era, unused by web); stats_from_rtt_history() used by tests
  ping_collector.py:17    stats_from_rtt_history() — mirrors web/backend/ping_stats.py (intentional, keep in sync)
  iperf_collector.py      iperf3 subprocess; iperf3_available(), run_iperf3(), summarize_result()
  dns_collector.py        compare_servers() — parallel dig calls (system, 8.8.8.8, 1.1.1.1, 9.9.9.9)
  speed_collector.py      run_network_quality(max_runtime_sec?), extract_metrics(), summarize() — networkQuality
  traceroute_collector.py traceroute(), nonblank_traceroute_lines()
  interface_collector.py  snapshot() — ifconfig + networksetup + route
  network_info_collector.py  fetch() — gateway, DNS, proxy, public IP, Wi-Fi details; vendor cached by OUI
  nmap_collector.py       run_nmap(), nmap_available(), nmap_version_line(), preset_ids() — bounded argv + `-oX -` parse
  _subprocess.py          run_merged_safe() — shared subprocess helper with timeout

core/
  alerts.py               AlertEngine, DEFAULT_RULES, alert_engine singleton — evaluated in payload.build()
  storage.py              SQLite session snapshots under ~/.netscope/; thread-safe queue writer
                          Tables: sessions (id, customer_name, customer_address, notes, tags, started_at, ended_at)
                                  snapshots (session_id, kind, ts, data JSON)
                          kinds: "stability" (every 5–15 s), "spike" (immediate on spike, throttled 5 s)
  sanitize.py             sanitize_property() — no injection
  host_sanitize.py        normalize_diagnostic_host() — validates user-supplied targets
  session.py              Session dataclass; TAGS = ["ISP Issue","Hardware","Placement","Interference","Resolved"]
  version.py              read_version() reads VERSION file

analysis/
  thresholds.py           RSSI/SNR/ping classification + color maps; band_from_channel_number()
  recommendations.py      human-readable tips from WiFi metrics

web/
  main.py                 uvicorn launcher + PyWebView window
  backend/
    server.py             FastAPI app, WebSocket /ws, all API routes (including session routes)
    payload.py            build() — unified JSON dict ~250ms tick; WiFi cache 400ms TTL (lock-protected)
                          Also auto-logs stability/spike snapshots when a session is active (see Session logging)
    ping_worker.py        background 1Hz ICMP thread; writes to state.ping
    state.py              PingState + RssiState + SessionState thread-safe singletons (ping, rssi, session)
                          SessionState tracks active session ID + snapshot/event throttle timestamps
    ping_stats.py         stats_from_rtt_history() — mirrors collectors/ping_collector.py
                          p95 uses nearest-rank: sv[min(ceil(0.95*n)-1, n-1)]
  frontend/
    index.html            SPA template; all CSS vars; alert-banner; session pill slot + modal HTML
    app.js                Tabs: Signal, Tools, Info, Security + boot; calls nsSession.initSession() on boot
    utils.js              Shared constants (BAR_COUNT, colors), color helpers (signalColor etc.), DOM helpers ($, setText, show, hide)
    ws.js                 WebSocket connect/reconnect; onData() dispatcher → signal.js, ping.js, scan.js, session.js globals
    signal.js             Signal tab: RSSI canvas chart (60fps rAF loop), updateSignalTab(), alert banner
    ping.js               Ping tab: Chart.js line chart, loss tick strip, log, updatePingModule(), applyTarget(), togglePause()
    scan.js               Scan tab: nearby networks table, channel congestion bars, runScan(); exposes lastConnChannel + lastApName globals
    netinfo.js            Info + Security tabs: loadNetInfo() → /api/network/info; `syncSecurityTab()` mirrors last payload to Security; netInfoLoaded global
    security.js           Security tab: nmap preset UI + POST `/api/nmap` (uses `window.nsTools.setRunning` for ping-chart banner)
    session.js            Customer session UI: window.nsSession.{initSession, onPayload}
                          Titlebar pill (NO SESSION / active name+timer), modal (create/active/history/review views)
                          Review: stability + spike rows merged by ts; rssi_avg10 as primary RSSI; phy_speed column
    traceroute.js         Traceroute path panel: `renderTracerouteModule()` (layout from traceroute_netscope_theme.html; NetScope CSS vars)
    tools.js              Tools tab: `window.nsTools`, DNS, speed, iperf, traceroute panel (`renderTracerouteModule`), interfaces; global `loadInterfaces` / `ifacesLoaded` for app.js
    vendor/               Chart.js 4.4.0 (downloaded by setup_venv.sh, gitignored — not in repo)

tests/                    pytest; conftest.py has fixtures; validate_all.py = optional macOS live check
```

---

## Data flow

```
CoreWLAN → wifi_collector.fetch_current_connection()
icmplib  → ping_worker._loop() → state.ping.record(rtt)
                                       ↓
                            payload.build() every 250ms
                                       │
                                       ├─→ server.py /ws WebSocket
                                       │         ↓
                                       │   ws.js onData(d) → signal.js / ping.js / scan.js / session.js
                                       │
                                       └─→ session snapshot (if active)
                                               stability: every 5 s (anomaly) or 15 s (clean)
                                               spike:     immediate on spike, throttled 5 s
                                               both saved to ~/.netscope/sessions.db
```

Alert engine evaluated inside `payload.build()` — result sent as `d.alerts {level, messages}` in every WebSocket tick. Banner shown in `index.html#alert-banner`.

**Snapshot alert evaluation** uses `rssi_avg10` + `avg_ms` (not instantaneous rtt) to avoid false-positive warning rows from single-probe spikes. Live banner uses instantaneous rtt for real-time responsiveness.

---

## Thread safety rules

- WiFi cache in `payload.py`: single lock covers check + fetch + write (no TOCTOU)
- Ping state: `state.PingState` lock covers all reads and writes
- Session state: `state.SessionState` lock covers session ID + both throttle timestamps
- SQLite writes: queue thread in `storage.py`
- Never touch DOM/CTk from a thread — not applicable (web-only, JS handles DOM)

---

## API routes (server.py)

| Method | Path | Handler |
|--------|------|---------|
| GET | / | index.html |
| WS | /ws | 250ms live feed (payload.build); includes `session_id` field |
| POST | /api/ping/target | set ping target, clears history |
| GET | /api/network/info | network_info_collector.fetch() |
| POST | /api/wan/check | traceroute -m 5 + ping 8.8.8.8 in parallel; finds ISP edge hop, WAN segment latency, loss% |
| GET | /api/wifi/scan | nearby networks + channel |
| POST | /api/dns | body `{ host, record_type?: A|AAAA }` → `compare_servers` (parallel dig) |
| POST | /api/speed | JSON body optional `{ max_seconds?: 20–90 }` → `run_network_quality`; response `{ summary, json, metrics }` |
| POST | /api/traceroute | traceroute_collector.traceroute |
| GET | /api/interfaces | interface_collector.snapshot |
| POST | /api/iperf | iperf_collector.run_iperf3 (check iperf3_available BEFORE executor) |
| GET | /api/nmap/version | nmap availability + first line of `nmap --version` |
| POST | /api/nmap | nmap_collector.run_nmap (presets: quick/services/safe_scripts/vuln/discovery/ssl/udp_top) |
| **POST** | **/api/sessions** | create session + set as active; body `{ customer_name, customer_address?, notes? }` |
| **GET** | **/api/sessions** | list last 100 sessions with snapshot_count each |
| **GET** | **/api/sessions/active** | current active session or `{ session: null }` |
| **POST** | **/api/sessions/{id}/end** | end session + clear active state |
| **PATCH** | **/api/sessions/{id}** | update notes and/or tags; body `{ notes?, tags? }` |
| **GET** | **/api/sessions/{id}/snapshots** | stability + spike snapshots merged and sorted by ts; each has `kind` field |
| **GET** | **/api/sessions/{id}/summary** | aggregate stats: rssi/ping/loss min·max·avg, alert counts, spike_event_count |

---

## Coding rules

- **Subprocess**: always `timeout=`, args as list (no `shell=True`), `shutil.which()` before optional tools (`networkQuality`, `iperf3`, `nmap`)
- **CoreWLAN**: SSID/BSSID can be `None` without Location Services — treat as WARN not FAIL
- **Layers**: UI only in `web/frontend/`. Data/API in `web/backend/` + `collectors/` + `core/` + `analysis/`. Keep them separate.
- **Don't summarize** the task back, suggest follow-ups, or over-explain. Just do the work.
- **Smallest change** that solves the problem. No unrequested refactors or comments.
- Only `ruff check` files you touched. Run `pytest tests/` only when asked or when changing test layout.
- No new frontend fields until the WebSocket payload includes them.

---

## Theme (hex only in frontend/)

- BG: `#0a0c0f` · Surface: `#0d1117` · Border: `#1a2030` · Font: JetBrains Mono
- Green `#22c55e` · Amber `#f59e0b` · Red `#ef4444` · Sky `#38bdf8` · Muted `#64748b`

---

## Dependencies

Runtime: `pyobjc-framework-CoreWLAN`, `icmplib`, `fastapi`, `uvicorn[standard]`, `websockets`, `pywebview`
Dev: `pytest`, `pytest-cov`, `hypothesis`, `ruff`, `bandit`
macOS CLI (not packaged): `ping`, `dig`, `traceroute`, `networkQuality` (12+), `iperf3` (brew), `ifconfig`, `networksetup`, `scutil`, `route`, `netstat`

---

## Known intentional duplication

`web/backend/ping_stats.py` mirrors `collectors/ping_collector.stats_from_rtt_history` — avoids icmplib import at payload module load. If you change one, change the other. Tests in `tests/test_ping_collector.py` cross-check them.
