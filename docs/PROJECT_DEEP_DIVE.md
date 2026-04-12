# NetScope — in-depth project guide

This document explains **how NetScope is put together**: processes, threads, network paths, and how data moves from macOS and Python to your screen. For a shorter map and security notes, see [OVERVIEW.md](OVERVIEW.md). For setup and features, see [README.md](../README.md).

**Visuals** below use [Mermaid](https://mermaid.js.org/) diagrams. They render on GitHub, in GitLab, in many IDEs (including VS Code / Cursor with a Mermaid preview), and on [mermaid.live](https://mermaid.live) if you paste the fenced blocks.

---

## 1. What NetScope is (one paragraph)

NetScope is a **macOS-only** diagnostics tool that combines:

- **Live Wi‑Fi telemetry** from Apple’s **CoreWLAN** (signal, noise, PHY, channel, scan list).
- A **continuous ICMP latency** stream to a configurable target (default `8.8.8.8`), using **icmplib** when available and the system **`ping`** binary as fallback.
- **On-demand tools**: DNS comparison (`dig`), `networkQuality`, `iperf3`, `traceroute`, and interface snapshots (`networksetup`, `route`, `ifconfig`).

The UI is a **single-page web app** (HTML/CSS/JavaScript) served by **FastAPI** on `127.0.0.1`. You can use an embedded **PyWebView** window or any browser — same origin, same WebSocket.

---

## 2. System context

Who talks to whom, at a high level:

```mermaid
flowchart TB
    subgraph User["Operator (this Mac)"]
        W[PyWebView window\nor Safari / Chrome]
    end

    subgraph Process["Python process"]
        U[uvicorn\nFastAPI]
        PW[ping_worker\n~1 Hz thread]
    end

    subgraph OS["macOS"]
        CW[CoreWLAN\nWi‑Fi APIs]
        CL[CoreLocation\noptional SSID context]
        ICMP[System ICMP / ping]
        CLI[dig, traceroute,\nnetworkQuality, iperf3,\nnetworksetup, ifconfig, route]
    end

    subgraph Net["Network (LAN / Internet)"]
        AP[Wi‑Fi access point]
        Targets[DNS resolvers,\n8.8.8.8, user hosts]
    end

    W <-->|"HTTP + WebSocket\n127.0.0.1:8765"| U
    U --> CW
    U --> CL
    PW --> ICMP
    U --> CLI
    CW <--> AP
    ICMP --> Targets
    CLI --> Targets
```

**Important:** Nothing in this design is meant to be exposed to the public internet. The server binds to **localhost** only.

---

## 3. Processes and entry points

When you run `python web/main.py`:

```mermaid
flowchart LR
    subgraph Launcher["web/main.py"]
        M[main]
    end

    subgraph Child["Subprocess"]
        V["python -m uvicorn\nweb.backend.server:app\n--host 127.0.0.1 --port 8765"]
    end

    M -->|spawn| V
    M -->|optional| WV[pywebview.create_window\nloads http://127.0.0.1:8765]
```

- **Parent:** starts uvicorn, waits ~1.5s, opens PyWebView (or prints “open in browser” if `webview` is missing), then on exit **terminates** the child process.
- **Child:** runs the real FastAPI app: static files, WebSocket, REST-style `/api/*` routes, lifespan hooks.

```mermaid
sequenceDiagram
    participant Main as web/main.py
    participant UV as uvicorn child
    participant PV as PyWebView

    Main->>UV: Popen(…)
    UV-->>Main: listening :8765
    Main->>PV: create_window + start
    Note over PV: User closes window
    Main->>UV: terminate + wait
```

---

## 4. Backend lifecycle (FastAPI `lifespan`)

On **startup**, the server starts the **ping worker** once. On **shutdown**, it stops that thread cleanly.

```mermaid
stateDiagram-v2
    [*] --> Starting: uvicorn loads app
    Starting --> Running: ping_worker.ensure_running()
    Running --> Stopping: shutdown signal
    Stopping --> [*]: ping_worker.stop()
```

---

## 5. Two traffic patterns: live stream vs on-demand tools

### 5.1 Live WebSocket stream (~4 Hz)

The Signal tab (and shared metrics) consume a **single JSON object** pushed about **every 250 ms** on `WebSocket /ws`. Each tick, the server runs `payload.build()` in a **thread-pool executor** (so brief blocking work does not stall the asyncio event loop), then `send_json`.

```mermaid
sequenceDiagram
    participant B as Browser / WebView
    participant WS as FastAPI /ws
    participant EX as Thread pool
    participant P as payload.build
    participant Wi as wifi_collector\n+ 400ms cache
    participant PS as ping_state\nRssiState
    participant C as core.sanitize\netc.

    loop every 250 ms
        WS->>EX: run_in_executor(build)
        EX->>P: build()
        P->>Wi: fetch_current_connection
        P->>PS: snapshot / stats
        P->>C: sanitize fields
        EX-->>WS: dict
        WS->>B: send_json
    end
```

**Wi‑Fi cache:** Inside `payload.py`, CoreWLAN is not called on every tick. A **~400 ms TTL** cache avoids hitting the driver at 4 Hz while still feeling “live”.

**Ping rate mismatch:** The **ping worker** runs at **~1 Hz** and appends to `PingState`. The WebSocket runs at **~4 Hz** and **reads** the latest RTT and rolling history. The chart therefore updates smoothly even though probes are once per second.

### 5.2 On-demand HTTP APIs

Tools (DNS, speed, traceroute, iperf, interfaces, Wi‑Fi scan, network info) use **POST/GET** under `/api/...`. The front end calls `fetch()` when you open a tab or click an action — **not** over the WebSocket.

```mermaid
flowchart LR
    subgraph FE["web/frontend/app.js"]
        F[fetch /api/...]
    end

    subgraph BE["web/backend/server.py"]
        R[Route handler]
        S["_sanitize(host)\nhost_sanitize"]
        Col[collectors/*]
    end

    FE --> R
    R --> S
    R --> Col
```

Every body that carries a **host** goes through **`core.host_sanitize.normalize_diagnostic_host`** (via `_sanitize` in `server.py`). Invalid hosts return **HTTP 400** before any subprocess runs.

---

## 6. Layered architecture (code modules)

```mermaid
flowchart TB
    subgraph Presentation["Presentation"]
        HTML["index.html\nlayout + theme CSS"]
        JS["app.js\nWebSocket client,\nDOM, canvas RSSI,\nChart.js ping"]
    end

    subgraph WebBackend["web/backend"]
        SRV["server.py\nroutes + /ws"]
        PLD["payload.py\nbuild unified dict"]
        ST["state.py\nPingState, RssiState"]
        PW["ping_worker.py\nICMP thread"]
    end

    subgraph Shared["Shared libraries (repo root)"]
        COL["collectors/*"]
        COR["core/*"]
        ANA["analysis/*"]
        PST["ping_stats.py\nRTT stats copy"]
    end

    HTML --> JS
    JS <-->|WS + fetch| SRV
    SRV --> PLD
    SRV --> COL
    PLD --> COL
    PLD --> ST
    PLD --> PST
    PW --> ST
    PLD --> COR
    SRV --> COR
```

**Why `ping_stats.py` exists:** `collectors/ping_collector.py` imports **icmplib** at module import time. The WebSocket payload builder must stay import-safe if someone runs without icmplib, so **`web/backend/ping_stats.py`** duplicates the pure **`stats_from_rtt_history`** function. **Tests** assert both implementations stay identical.

---

## 7. Ping pipeline (detail)

```mermaid
flowchart TD
    T[ping_worker loop\n~1 s period]
    T --> A{icmplib\navailable?}
    A -->|yes| B[icmplib.ping\ncount=1, timeout=1.5s]
    A -->|no or error| C[subprocess:\nping -c 1 …]
    B --> D{rtt known?}
    D -->|no| C
    D -->|yes| E[ping_state.record]
    C --> E
    E --> F[deque history\nmax 80 samples]
```

`PingState` is fully **lock-protected**: the worker **writes**; `payload.build()` **reads** a snapshot `(current_rtt, history, target)` under the same lock.

---

## 8. Front-end update loop (conceptual)

```mermaid
flowchart LR
    WS[WebSocket\nonmessage]
    D[JSON payload]
    U[update DOM:\nmetrics, bars, text]
    R[rssiHistory push\nrequestAnimationFrame\ncanvas draw]
    P[updatePingModule\nChart.js]

    WS --> D
    D --> U
    D --> R
    D --> P
```

- **RSSI:** rolling samples in JS; canvas redraw throttled with **`requestAnimationFrame`** for smooth animation without blocking the main thread.
- **Ping chart (Tools):** Chart.js is configured with **`animation: false`** so each tick replaces data without easing “fake” motion.

---

## 9. Repository layout (text tree)

```
netscope/
├── collectors/          # WiFi, ping sampler, DNS, interfaces, speed, traceroute, iperf, …
├── core/                # sanitize, storage, session, alerts, health_bus, host_sanitize
├── analysis/            # thresholds, recommendations (no I/O)
├── web/
│   ├── main.py          # uvicorn subprocess + PyWebView
│   ├── backend/
│   │   ├── server.py    # FastAPI, /ws, /api/*
│   │   ├── payload.py   # 250 ms unified dict
│   │   ├── state.py     # PingState, RssiState
│   │   ├── ping_worker.py
│   │   └── ping_stats.py
│   └── frontend/
│       ├── index.html
│       └── app.js
├── tests/               # pytest + validate_all.py (live Mac)
├── docs/                # OVERVIEW.md, this file
├── requirements.txt
└── README.md
```

---

## 10. HTTP surface (quick reference)

| Method | Path | Role |
|--------|------|------|
| GET | `/` | Serves `index.html` |
| — | `/static/*` | JS, assets from `web/frontend/` |
| WS | `/ws` | Live ~250 ms JSON |
| POST | `/api/ping/target` | Change ICMP target (validated host) |
| GET | `/api/network/info` | Consolidated network / public IP style info |
| GET | `/api/wifi/scan` | Nearby APs (CoreWLAN) |
| POST | `/api/dns` | DNS comparison |
| POST | `/api/speed` | `networkQuality` |
| POST | `/api/traceroute` | Traceroute |
| GET | `/api/interfaces` | Interface / gateway snapshot |
| POST | `/api/iperf` | iperf3 run |

---

## 11. Payload contract (WebSocket)

The authoritative field list and types live in the **docstring** at the top of `web/backend/payload.py`. In words:

- **Wi‑Fi:** `connected`, `signal`, SNR, PHY speed/mode/width, channel, band, SSID/BSSID (may be null), Wi‑Fi generation label.
- **Ping:** `ping`, `loss`, min/max/avg/jitter, `ping_target`, `ping_history` for charts.
- **RSSI smoothing:** `rssi_avg10`, `rssi_stddev20` derived in payload from `RssiState`.
- **Meta:** `ts` (Unix time).

The front end should treat **missing or null** fields as “unknown” — especially after removing Location permission, SSID/BSSID often disappear while RSSI may still update.

---

## 12. Threading and concurrency (mental model)

```mermaid
flowchart TB
    subgraph Asyncio["asyncio event loop"]
        H[HTTP handlers]
        W[WebSocket loop\nsleep 0.25s]
    end

    subgraph Threads["Other threads"]
        EX[Default executor\npayload.build]
        PW[ping_worker daemon]
        SQ[SQLite writer\nin core.storage]
    end

    W -->|run_in_executor| EX
    PW --> PS[(PingState)]
    EX --> PS
    EX --> Wi[(WiFi cache)]
```

Rule of thumb: **no collector should assume it runs on the main thread**, but **all CoreWLAN and subprocess use from `payload.build()` is serialized per executor task**, and ping writes are serialized by `PingState`’s lock.

---

## 13. Testing strategy

| Layer | How |
|--------|-----|
| Pure logic | `analysis/`, `core/sanitize`, `ping_stats` ↔ `ping_collector` stats — **pytest** with mocks / Hypothesis |
| Collectors | Mocked subprocess output in tests |
| Full stack on a Mac | `python tests/validate_all.py` — live Wi‑Fi, ping, dig, route, etc. |
| CI | GitHub Actions: **pytest**, **ruff**, **compileall**, **bandit** |

---

## 14. Further reading

- [OVERVIEW.md](OVERVIEW.md) — condensed architecture + **security** section  
- [AGENTS.md](../AGENTS.md) — rules for contributors and automated agents  
- [README.md](../README.md) — install, run, feature list  

---

*NetScope **v1.0.0** — web-only layout (no legacy Tk desktop).*
