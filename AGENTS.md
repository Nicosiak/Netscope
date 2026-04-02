# NetScope — Agent Guidelines

## Project Overview

macOS desktop WiFi & network diagnostics tool. Python + customtkinter + CoreWLAN + matplotlib.
Dark-themed UI inspired by Ubiquiti WiFiman. Runs locally, no server, no database.

## Architecture

```
main.py              → Entry point, sys.path setup
ui/app.py            → CTk main window, tab routing, status bar, thread wiring
ui/theme.py          → All colors, chart styling (WiFiman dark palette)
ui/tabs/wifi_tab.py  → Signal tab: PHY bar, RSSI chart, AP card, speed factors, channel chart, networks
ui/tabs/ping_tab.py  → Ping tab: target selector, RTT chart, stat cards
ui/tabs/diagnostics_tab.py → DNS comparison, speed test, iperf3, traceroute, interfaces
collectors/          → Background data collection (threads), each returns plain dicts
analysis/            → Thresholds, color classification, recommendation engine
tests/               → validate_all.py cross-checks collectors against system CLI
```

## Key Patterns

- **Thread safety**: Collectors run in daemon threads. UI updates ONLY via `root.after(0, callback)` (the `queue_fn` pattern). Never touch CTk widgets from a background thread.
- **Data flow**: Collector → dict → queue_fn → tab.on_data(dict). All data is plain Python dicts, no ORM or models.
- **Theme**: All colors come from `ui/theme.py`. Never hardcode hex colors in tab files — import from theme.
- **Charts**: matplotlib with `FigureCanvasTkAgg`. Always call `theme.style_figure(fig)` after creating axes. Use `draw_idle()` not `draw()`.
- **Status bar caching**: `app.py` uses `_sb_set()` to avoid flicker — only reconfigures labels when value changes.

## Rules

- Always dark mode (`ctk.set_appearance_mode("Dark")`)
- CoreWLAN requires Location Services — handle None gracefully for SSID/BSSID
- Filter hidden networks (null SSID) from display, show count separately
- `networkQuality` and `iperf3` may not be installed — check with `shutil.which()` and disable UI gracefully
- All subprocess calls must have timeouts
- Keep charts small — the app should not require excessive scrolling
- Run `python -m py_compile` on changed files before considering work done
- Run `tests/validate_all.py` to verify collectors against real system data
