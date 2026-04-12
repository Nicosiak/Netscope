# Changelog

All notable changes to NetScope are documented here. The version in the root [`VERSION`](VERSION) file is the canonical release identifier.

## [1.0.0] — 2026-04-12

First **stable v1** release of the **web-first** product: local FastAPI + WebSocket UI on macOS (PyWebView or browser), live CoreWLAN metrics, continuous ping (icmplib with system `ping` fallback), and diagnostics (DNS, speed, iperf3, traceroute, interfaces).

### Highlights

- **Web stack:** `web/backend` (FastAPI, payload, ping worker, state) and `web/frontend` (single-page app, canvas RSSI, Chart.js ping tools).
- **Shared libraries:** `collectors/`, `core/`, `analysis/` at repository root for collectors and business logic.
- **Quality:** pytest suite, Ruff, optional `tests/validate_all.py` on real macOS hardware.

Release tag: **`v1.0.0`** (`git show v1.0.0`).
