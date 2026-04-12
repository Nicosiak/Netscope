# NetScope — architecture & security

**Release:** v1.0.0 (`VERSION` at repo root, `CHANGELOG.md`). **Setup and features:** [README.md](../README.md) · **Agent / coding rules:** [AGENTS.md](../AGENTS.md) · **In-depth guide (diagrams):** [PROJECT_DEEP_DIVE.md](PROJECT_DEEP_DIVE.md)

---

## What this app is

macOS-only **local web app**: FastAPI + WebSocket on `127.0.0.1`, UI in `web/frontend/`, optional **PyWebView** window or any browser. Live Wi‑Fi via **CoreWLAN**; ping via **icmplib** or system **`ping`**; diagnostics use **`dig`**, **`networkQuality`**, **`iperf3`**, **`traceroute`**, **`ifconfig`** / **`networksetup`** where present.

**Out of scope:** remote hosting, multi-user server, Windows/Linux at runtime (CoreWLAN + macOS CLI assumptions).

---

## Layout (where code lives)

| Area | Role |
|------|------|
| `collectors/` | Dict-shaped reads from CoreWLAN + subprocess tools; timeouts everywhere. |
| `core/` | Sanitize, SQLite sessions (`~/.netscope/`), alerts, health bus, host validation. |
| `analysis/` | Thresholds and recommendation strings — pure logic, no I/O. |
| `web/backend/server.py` | FastAPI, WebSocket ~250 ms tick, tool APIs. |
| `web/backend/payload.py` | Builds one unified JSON blob per tick for the UI. |
| `web/backend/ping_worker.py` | ~1 Hz ICMP thread → `state.ping`. |
| `web/backend/ping_stats.py` | Copy of RTT stats helper so `payload` does not import `icmplib` via `ping_collector`; keep in sync with `collectors/ping_collector.py`. |
| `web/frontend/` | `index.html` + `app.js` — all theme hex here. |
| `web/main.py` | Spawns uvicorn, opens PyWebView. |
| `tests/` | pytest + optional `validate_all.py` on real macOS. |

---

## Data flow

```
web/main.py
  └─ uvicorn web.backend.server:app
        ├─ GET /, /static/     → SPA
        ├─ WebSocket /ws       → payload.build() each tick
        │      ├─ wifi_collector, interface_collector, …
        │      ├─ state.ping   ← ping_worker
        │      └─ state.rssi
        └─ POST/GET …/api/*    → on-demand tools (DNS, speed, iperf, …)
```

Collectors never touch the DOM. The browser only consumes JSON.

---

## Design choices (short)

1. **Dicts** between layers — easy to log and test.  
2. **Wi‑Fi cache (~400 ms TTL)** — avoids hammering CoreWLAN at WebSocket rate.  
3. **SQLite writer thread** — bounded snapshots; large JSON writes skipped.  
4. **Ping fallback** — system `ping` if `icmplib` missing or fails.  
5. **`host_sanitize`** on user-supplied targets before traceroute / iperf / ping APIs.

---

## Security

NetScope is a **local web app** on your Mac. It does not ship a public remote API or multi-user server.

### Threat model (short)

- **Local user:** trusted operator; SQLite and any export paths use normal user permissions.  
- **Network:** tools contact DNS, HTTP, or LAN hosts you choose or that are fixed for benchmarks (e.g. public DNS, speed endpoints).  
- **Supply chain:** install dependencies from PyPI; pin versions where practical.

### Mitigations in this repo

- **Subprocesses:** argument lists, not `shell=True`, for user-controlled hosts. **`core.host_sanitize.normalize_diagnostic_host`** before traceroute, iperf, and ping target changes.  
- **SQLite:** parameterized queries in `core/storage.py`.  
- **iperf3:** output capped (~2M chars); process killed on timeout / overflow.  
- **Session snapshots:** JSON over **1 MB** is not written (skipped, stderr notice).  
- **Exports:** paths from the OS file dialog; content from local app state.

### What we do not claim

ICMP and path diagnostics are not a proof of end-to-end security.

### Review habit

After dependency bumps, run **`pip audit`** on critical issues. CI runs **pytest**, **ruff**, **compileall**, and **bandit** on Python.
