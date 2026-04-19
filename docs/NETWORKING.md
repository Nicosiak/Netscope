# Networking — engineer’s notepad (WIP)

**Purpose:** Capture **what we’re missing**, **what should change**, and **how tools must work together** so readings stay honest. This is a **working notebook**, not a second [INVENTORY.md](INVENTORY.md) or [CLAUDE.md](../CLAUDE.md). Code paths and APIs live there; **ship work** goes to [BACKLOG.md](BACKLOG.md) when you commit to it.

---

## How the tools should compose (accurate picture)

Nothing here is a single “health score.” You triangulate:

| Signal | What it actually tests | Trust it when… | Doubt it when… |
|--------|------------------------|----------------|----------------|
| **Wi‑Fi (CoreWLAN)** | Association, AP identity, channel, RSSI/SNR-ish | Loss/jitter lines up with **moving rooms** or **channel/congestion** | Internet fine on Ethernet but awful on Wi‑Fi |
| **Ping (icmplib + system fallback)** | ICMP echo, ~1 Hz trend | Stable RTT + low loss while reproducing the issue | Apps still fail — ICMP may be allowed while TCP isn’t, or deprioritized |
| **DNS (`dig`)** | Resolver path you asked | Names resolve consistently across **system vs 8.8.8.8 vs 1.1.1.1** | Browser breaks but `dig` works — **stub / VPN / filter** not same as `dig` |
| **Traceroute** | Path shape, per-hop delay | Delay jumps at one hop **and** ping to same target matches | Lots of `*` — may be **ICMP blocked**, not dead link |
| **Nmap (presets)** | TCP reachability / banners on chosen host | Confirms **port closed vs filtered** after ping/DNS sane | Run only with **permission**; not a substitute for Wi‑Fi stats |

**Rule:** Corroborate. Wi‑Fi good + DNS good + ping bad → think **path/ISP/filter**. Wi‑Fi bad + ping bad everywhere → fix **RF or AP** first.

---

## Features / coverage we’re light on (candidates to add or document)

Use this list to drive ideas; tick items into **BACKLOG** when you’re ready to build.

- **Band / PHY honesty** — 2.4 vs 5 vs **6 GHz**, channel width, 802.11 generation: only if macOS exposes it reliably; otherwise **say we don’t know** in UI.
- **Stub resolver vs `dig`** — “What Safari uses” vs what `dig` hits; big for **house calls**.
- **TCP or TLS timing** — ping OK but **HTTPS slow**; optional small probe (curl timing, etc.) if you want app-layer truth.
- **Gateway-first workflow** — one-click ping/trace to **default gateway** vs arbitrary target.
- **MTU / PMTUD hints** — weird “some sites load” patterns.
- **IPv6 parity** — ping6/trace6/dig **AAAA** paths consistent with IPv4 story.
- **DNS record types** — if UI promises MX/TXT, backend must match (today A/AAA-ish paths need audit).
- **nmap / UDP** — privilege and **stderr** messaging when OS blocks behavior.

---

## Should change / verify (engineering notes)

- **Align copy with reality** — Any label that implies “Wi‑Fi standard” or “full path diagnosis” without data = fix wording or add data.
- **Two ping implementations** — `ping_worker` (icmplib + `ping`) vs legacy `PingSampler` path; ensure **one story** in UI/docs.
- **Alerts vs `analysis/thresholds`** — same cutoffs everywhere or explain the difference (see BACKLOG).
- **Session snapshots** — know what **targets** are stored; redact or warn if customers are sensitive.

---

## On-site sequence (quick)

1. Reproduce on **Wi‑Fi**, then **Ethernet** if possible.  
2. Signal + ping **while moving** (RF vs backhaul).  
3. DNS compare (system vs public).  
4. Traceroute + ping to **same** host when isolating path.  
5. Nmap only after explain + consent.

Jot: SSID/BSSID, channel, DNS server, ping target, time.

---

## Agents

Treat this file as **product + measurement intent**. Implement from [BACKLOG.md](BACKLOG.md); find modules in [INVENTORY.md](INVENTORY.md) / [CLAUDE.md](../CLAUDE.md). When you add a collector or metric, update **this notepad** if it changes how tools **compose** or what we **don’t** claim.
