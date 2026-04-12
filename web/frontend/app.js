/* NetScope web — WebSocket client + DOM updates + tools */
"use strict";

const BAR_COUNT = 80;
const RSSI_MIN = -90;
const RSSI_MAX = -30;

const GREEN = "#22c55e";
const AMBER = "#f59e0b";
const RED   = "#ef4444";
const MUTED = "#64748b";
const SKY   = "#38bdf8";

// ── Color helpers ────────────────────────────────────────────────

function signalColor(dbm) {
  if (dbm == null) return MUTED;
  if (dbm >= -70) return GREEN;
  if (dbm >= -80) return AMBER;
  return RED;
}
function pingColor(ms) {
  if (ms == null) return MUTED;
  if (ms <= 30) return GREEN;
  if (ms <= 80) return AMBER;
  return RED;
}
function lossColor(pct) {
  if (pct == null) return MUTED;
  if (pct <= 1) return GREEN;
  if (pct <= 5) return AMBER;
  return RED;
}
function snrColor(snr) {
  if (snr == null) return MUTED;
  if (snr >= 25) return GREEN;
  if (snr >= 15) return AMBER;
  return RED;
}
function qualityWord(dbm) {
  if (dbm == null) return "—";
  if (dbm >= -67) return "Excellent";
  if (dbm >= -70) return "Good";
  if (dbm >= -80) return "Fair";
  return "Poor";
}

// ── DOM helpers ──────────────────────────────────────────────────

const $ = (id) => document.getElementById(id);
function setText(el, text, color) {
  if (!el) return;
  el.textContent = text;
  if (color !== undefined) el.style.color = color;
}
function show(el) { el.style.display = ""; }
function hide(el) { el.style.display = "none"; }

// ── Tab switching ────────────────────────────────────────────────

const tabBtns = document.querySelectorAll(".tab-btn");
const tabPanels = { signal: $("tab-signal"), tools: $("tab-tools"), info: $("tab-info") };
let currentTab = "signal";

tabBtns.forEach(btn => {
  btn.addEventListener("click", () => {
    const t = btn.dataset.tab;
    if (t === currentTab) return;
    currentTab = t;
    tabBtns.forEach(b => b.classList.toggle("active", b.dataset.tab === t));
    Object.entries(tabPanels).forEach(([k, panel]) => {
      panel.classList.toggle("active", k === t);
    });
    if (t === "info" && !netInfoLoaded) loadNetInfo();
    if (t === "tools" && !ifacesLoaded) { ifacesLoaded = true; loadInterfaces(); }
    if (t === "tools" && typeof sizePingChart === "function") {
      requestAnimationFrame(() => requestAnimationFrame(() => sizePingChart()));
    }
  });
});

// ── Signal tab DOM refs ──────────────────────────────────────────

const connDot     = $("conn-dot");
const connText    = $("conn-text");
const apName      = $("ap-name");
const chVal       = $("ch-val");
const bandVal     = $("band-val");
const phyVal      = $("phy-val");
const wifiGen     = $("wifi-gen");
const widthVal    = $("width-val");

const mSignal     = $("m-signal");
const mSnr        = $("m-snr");
const mPhy        = $("m-phy");
const mPing       = $("m-ping");
const mLoss       = $("m-loss");

const chartFreshness = $("chart-freshness");

const sideAp      = $("side-ap");
const sideBssid   = $("side-bssid");
const sqSignalBar  = $("sq-signal-bar");
const sqSignalVal  = $("sq-signal-val");
const sqSnrBar     = $("sq-snr-bar");
const sqSnrVal     = $("sq-snr-val");
const sqStability  = $("sq-stability");
const sqStddev     = $("sq-stddev");
const sidePing    = $("side-ping");
const sideAvg     = $("side-avg");
const sideJitter  = $("side-jitter");
const sideLoss    = $("side-loss");

// ── RSSI line chart (canvas, 60 fps) ────────────────────────────

const rssiHistory = new Array(BAR_COUNT).fill(null);
const rssiBarCanvas = $("rssi-bars-canvas");
const rssiBarCtx    = rssiBarCanvas.getContext("2d");

// Hex color → rgba string with given alpha
function hexAlpha(hex, a) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${a})`;
}

// Dynamic scale — auto-fits to the last 20 samples, 10 dBm minimum window
const RSSI_SCALE_PAD = 2;
const RSSI_MIN_RANGE = 10;
let scaleMin = RSSI_MIN, scaleMax = RSSI_MAX;
let targetScaleMin = RSSI_MIN, targetScaleMax = RSSI_MAX;

function computeTargetScale() {
  const vals = rssiHistory.slice(-20).filter(v => v != null);
  if (!vals.length) { targetScaleMin = RSSI_MIN; targetScaleMax = RSSI_MAX; return; }
  const lo    = Math.min(...vals) - RSSI_SCALE_PAD;
  const hi    = Math.max(...vals) + RSSI_SCALE_PAD;
  const range = Math.max(hi - lo, RSSI_MIN_RANGE);
  const mid   = (lo + hi) / 2;
  targetScaleMin = Math.floor(mid - range / 2);
  targetScaleMax = Math.ceil(mid  + range / 2);
}

function updateRssiBars() { computeTargetScale(); }

function drawRssiBars() {
  requestAnimationFrame(drawRssiBars);
  if (document.hidden || currentTab !== "signal") return;

  const w = rssiBarCanvas.offsetWidth  || 600;
  const h = rssiBarCanvas.offsetHeight || 200;
  if (rssiBarCanvas.width !== w || rssiBarCanvas.height !== h) {
    rssiBarCanvas.width = w; rssiBarCanvas.height = h;
    scaleMin = targetScaleMin; scaleMax = targetScaleMax;
  }

  // Animate scale
  scaleMin += (targetScaleMin - scaleMin) * 0.1;
  scaleMax += (targetScaleMax - scaleMax) * 0.1;

  const ctx   = rssiBarCtx;
  const AXIS_R = 40;   // right margin for Y-axis labels
  const PAD_T  = 6;
  const PAD_B  = 16;   // room for "dBm" unit label
  const cW     = w - AXIS_R;
  const cH     = h - PAD_T - PAD_B;
  const range  = (scaleMax - scaleMin) || 1;
  const yOf    = dbm => PAD_T + cH - ((dbm - scaleMin) / range) * cH;

  ctx.clearRect(0, 0, w, h);

  // ── Grid ──────────────────────────────────────────────────────
  const tickStep  = range <= 15 ? 2 : range <= 30 ? 5 : 10;
  const firstTick = Math.ceil(scaleMin / tickStep) * tickStep;

  ctx.save();
  ctx.font = "9px 'JetBrains Mono', monospace";
  ctx.textAlign = "left";

  for (let v = firstTick; v <= scaleMax; v += tickStep) {
    const y = yOf(v);
    ctx.strokeStyle = "#1a2030"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(cW, y); ctx.stroke();
    ctx.fillStyle = "#475569";
    ctx.fillText(v, cW + 5, y + 3);
  }

  // Three vertical dividers
  ctx.strokeStyle = "#1a2030";
  for (const f of [0.25, 0.5, 0.75]) {
    const x = f * cW;
    ctx.beginPath(); ctx.moveTo(x, PAD_T); ctx.lineTo(x, PAD_T + cH); ctx.stroke();
  }

  // "dBm" unit label
  ctx.fillStyle = "#334155";
  ctx.fillText("dBm", cW + 5, h - 3);
  ctx.restore();

  // ── Line + area ───────────────────────────────────────────────
  const N      = rssiHistory.length;
  const stepX  = cW / Math.max(N - 1, 1);
  const latest = [...rssiHistory].reverse().find(v => v != null);
  const lc     = signalColor(latest);

  const pts = rssiHistory.map((v, i) =>
    v != null ? { x: i * stepX, y: yOf(v) } : null
  );

  function drawSegment(seg, mode) {
    if (seg.length < 2) return;
    if (mode === "area") {
      const grad = ctx.createLinearGradient(0, PAD_T, 0, PAD_T + cH);
      grad.addColorStop(0, hexAlpha(lc, 0.2));
      grad.addColorStop(1, hexAlpha(lc, 0.01));
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.moveTo(seg[0].x, PAD_T + cH);
      seg.forEach(p => ctx.lineTo(p.x, p.y));
      ctx.lineTo(seg[seg.length - 1].x, PAD_T + cH);
      ctx.closePath();
      ctx.fill();
    } else {
      ctx.beginPath();
      ctx.moveTo(seg[0].x, seg[0].y);
      seg.slice(1).forEach(p => ctx.lineTo(p.x, p.y));
      ctx.stroke();
    }
  }

  // Area fill pass
  let seg = [];
  for (const p of pts) { if (p) seg.push(p); else { drawSegment(seg, "area"); seg = []; } }
  drawSegment(seg, "area");

  // Line pass
  ctx.save();
  ctx.lineWidth = 1.5; ctx.lineJoin = "round"; ctx.lineCap = "round";
  ctx.strokeStyle = lc; ctx.shadowColor = lc; ctx.shadowBlur = 3;
  seg = [];
  for (const p of pts) { if (p) seg.push(p); else { drawSegment(seg, "line"); seg = []; } }
  drawSegment(seg, "line");

  // Dot on latest point
  const last = pts[N - 1];
  if (last) {
    ctx.shadowBlur = 8; ctx.fillStyle = lc;
    ctx.beginPath(); ctx.arc(last.x, last.y, 3, 0, Math.PI * 2); ctx.fill();
  }
  ctx.restore();
}

// Kick off the 60fps render loop
drawRssiBars();

// ── WebSocket + data handler ─────────────────────────────────────

let ws = null;
let reconnectTimer = null;
let lastPayloadTs = 0;

// Update freshness label every 500ms
setInterval(() => {
  if (!lastPayloadTs) return;
  const age = (Date.now() - lastPayloadTs) / 1000;
  chartFreshness.textContent = age < 1 ? "live" : `last update ${age.toFixed(1)}s ago`;
  chartFreshness.style.color = age > 3 ? "#ef4444" : "#334155";

}, 500);

function connect() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(proto + "//" + location.host + "/ws");

  ws.onopen = () => {
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
  };

  ws.onmessage = (ev) => {
    try { onData(JSON.parse(ev.data)); } catch (e) { console.warn("WS parse error", e); }
  };

  ws.onclose = () => scheduleReconnect();
  ws.onerror = () => { try { ws.close(); } catch (_) {} };
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => { reconnectTimer = null; connect(); }, 1500);
}

function onData(d) {
  const c = d.connected;

  // Status bar (always visible)
  connDot.className = "dot " + (c ? "green" : "grey");
  setText(connText, c ? "Connected" : "No Signal");
  setText(apName, c ? (d.ap_name || "—") : "—");
  setText(chVal, d.channel || "—");
  setText(bandVal, d.band || "—");
  setText(phyVal, d.phy_mode || "—");
  wifiGen.textContent = d.wifi_gen || "";
  wifiGen.style.display = d.wifi_gen ? "" : "none";
  setText(widthVal, d.width || "—");

  // Metric strip
  const sig = d.signal;
  const sc = signalColor(sig);
  setText(mSignal, sig != null ? sig : "—", sc);
  setText(mSnr, d.snr != null ? d.snr : "—", snrColor(d.snr));
  setText(mPhy, d.phy_speed != null ? d.phy_speed : "—", SKY);
  setText(mPing, d.ping != null ? d.ping : "—", pingColor(d.ping));
  setText(mLoss, d.loss != null ? d.loss : "—", lossColor(d.loss));

  // Signal tab chart
  const qw = qualityWord(sig);


  rssiHistory.shift();
  rssiHistory.push(sig);
  updateRssiBars();

  // Signal side panel
  setText(sideAp, c ? (d.ap_name || "—") : "—");
  setText(sideBssid, c ? (d.bssid || "—") : "—");

  const sigFrac = sig != null ? Math.max(0, Math.min(1, (sig - RSSI_MIN) / (RSSI_MAX - RSSI_MIN))) : 0;
  sqSignalBar.style.width = (sigFrac * 100) + "%";
  sqSignalBar.style.background = sc;
  setText(sqSignalVal, sig != null ? sig + " dBm" : "—", sc);

  const snrC = snrColor(d.snr);
  const snrFrac = d.snr != null ? Math.max(0, Math.min(1, d.snr / 40)) : 0;
  sqSnrBar.style.width = (snrFrac * 100) + "%";
  sqSnrBar.style.background = snrC;
  setText(sqSnrVal, d.snr != null ? d.snr + " dB" : "—", snrC);

  // Stability badge
  const sd = d.rssi_stddev20;
  if (sd != null) {
    const [word, color] = sd < 2 ? ["Stable", GREEN] : sd < 5 ? ["Variable", AMBER] : ["Unstable", RED];
    setText(sqStability, word, color);
    setText(sqStddev, "±" + sd + " dBm", MUTED);
  } else {
    setText(sqStability, "—", MUTED);
    setText(sqStddev, "—", MUTED);
  }

  const pc = pingColor(d.ping);
  setText(sidePing, d.ping != null ? d.ping + " ms" : "—", pc);
  setText(sideAvg, d.avg_ms != null ? d.avg_ms + " ms" : "—", pingColor(d.avg_ms));
  setText(sideJitter, d.jitter_ms != null ? d.jitter_ms + " ms" : "—", MUTED);
  setText(sideLoss, d.loss != null ? d.loss + "%" : "—", lossColor(d.loss));

  if (typeof updatePingModule === "function") {
    updatePingModule({ ping: d.ping, loss: d.loss, jitter_ms: d.jitter_ms, ping_target: d.ping_target });
  }

  // Track connected channel + AP name for congestion/scan highlighting
  const newCh = d.channel ? parseInt(d.channel, 10) : null;
  if (newCh !== lastConnChannel) lastConnChannel = newCh;
  if (d.ap_name) lastApName = d.ap_name;

  // Record server timestamp for freshness indicator
  lastPayloadTs = d.ts ? d.ts * 1000 : Date.now();
}

// ── Diagnostics ──────────────────────────────────────────────────

function setRunning(btn, running, defaultLabel) {
  btn.disabled = running;
  btn.textContent = running ? "Running…" : defaultLabel;
}

// DNS
const dnsRunBtn    = $("dns-run-btn");
const dnsHostInput = $("dns-host-input");
const dnsBars      = $("dns-bars");
const dnsResult    = $("dns-result");

dnsRunBtn.addEventListener("click", () => {
  const host = dnsHostInput.value.trim() || "google.com";
  setRunning(dnsRunBtn, true, "Run Test");
  hide(dnsBars);
  dnsResult.textContent = "";

  fetch("/api/dns", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ host }),
  })
    .then(r => r.json())
    .then(data => {
      const results = data.results || [];
      if (!results.length) {
        dnsResult.textContent = "No results.";
        return;
      }
      // Build bar chart
      const maxMs = Math.max(1, ...results.map(r => r.query_time_ms || 0));
      dnsBars.innerHTML = "";
      results.forEach(r => {
        const ms = r.query_time_ms;
        const fraction = ms != null ? Math.max(0.02, ms / maxMs) : 0;
        const color = ms == null ? MUTED : ms <= 30 ? GREEN : ms <= 80 ? AMBER : RED;
        const row = document.createElement("div");
        row.className = "dns-bar-row";
        row.innerHTML = `
          <span class="dns-bar-lbl">${r.label || r.server_queried || "System"}</span>
          <div class="dns-bar-track"><div class="dns-bar-fill" style="width:${fraction * 100}%;background:${color}"></div></div>
          <span class="dns-bar-val" style="color:${color}">${ms != null ? ms + " ms" : "timeout"}</span>
        `;
        dnsBars.appendChild(row);
      });
      show(dnsBars);
      // Raw summary
      const lines = results.map(r =>
        `${(r.label || "").padEnd(22)} ${r.query_time_ms != null ? r.query_time_ms + " ms" : "timeout"}`
      ).join("\n");
      dnsResult.textContent = lines;
    })
    .catch(e => { dnsResult.textContent = "Error: " + e; })
    .finally(() => setRunning(dnsRunBtn, false, "Run Test"));
});

// Speed
const speedRunBtn = $("speed-run-btn");
const speedTiles  = $("speed-tiles");
const speedResult = $("speed-result");
const spDl = $("sp-dl"), spUl = $("sp-ul"), spRpm = $("sp-rpm"), spRtt = $("sp-rtt");

speedRunBtn.addEventListener("click", () => {
  setRunning(speedRunBtn, true, "Run Test");
  hide(speedTiles);
  speedResult.textContent = "Running networkQuality… this takes ~30 s";

  fetch("/api/speed", { method: "POST" })
    .then(r => r.json())
    .then(data => {
      speedResult.textContent = data.summary || "";
      const j = data.json || {};
      if (j && Object.keys(j).length) {
        const dl = j.dl_throughput;
        const ul = j.ul_throughput;
        setText(spDl, dl != null ? (dl / 1e6).toFixed(1) + " Mbps" : "—", SKY);
        setText(spUl, ul != null ? (ul / 1e6).toFixed(1) + " Mbps" : "—", SKY);
        setText(spRpm, j.responsiveness != null ? j.responsiveness : "—");
        setText(spRtt, j.base_rtt != null ? j.base_rtt + " ms" : "—");
        show(speedTiles);
      }
    })
    .catch(e => { speedResult.textContent = "Error: " + e; })
    .finally(() => setRunning(speedRunBtn, false, "Run Test"));
});

// iperf
const iperfDlBtn  = $("iperf-dl-btn");
const iperfUlBtn  = $("iperf-ul-btn");
const iperfHost   = $("iperf-host");
const iperfTiles  = $("iperf-tiles");
const iperfResult = $("iperf-result");
const ipMbps = $("ip-mbps"), ipRetx = $("ip-retx"), ipDur = $("ip-dur");

function runIperf(direction) {
  const host = iperfHost.value.trim();
  if (!host) { iperfResult.textContent = "Enter a server hostname or IP."; return; }
  [iperfDlBtn, iperfUlBtn].forEach(b => b.disabled = true);
  iperfDlBtn.textContent = direction === "download" ? "Running…" : "Download";
  iperfUlBtn.textContent = direction === "upload" ? "Running…" : "Upload";
  hide(iperfTiles);
  iperfResult.textContent = "Running iperf3 for 10 s…";

  fetch("/api/iperf", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ host, direction }),
  })
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        iperfResult.textContent = data.error;
        return;
      }
      const mbps = data.mbps;
      setText(ipMbps, mbps != null ? mbps.toFixed(1) + " Mbps" : "—", mbps != null ? (mbps >= 100 ? GREEN : mbps >= 25 ? AMBER : RED) : MUTED);
      setText(ipRetx, data.retransmits != null ? data.retransmits : "—");
      setText(ipDur, data.duration_s != null ? data.duration_s.toFixed(1) + " s" : "—");
      show(iperfTiles);
      iperfResult.textContent = data.raw || "";
    })
    .catch(e => { iperfResult.textContent = "Error: " + e; })
    .finally(() => {
      [iperfDlBtn, iperfUlBtn].forEach(b => b.disabled = false);
      iperfDlBtn.textContent = "Download";
      iperfUlBtn.textContent = "Upload";
    });
}

iperfDlBtn.addEventListener("click", () => runIperf("download"));
iperfUlBtn.addEventListener("click", () => runIperf("upload"));

// Traceroute
const traceRunBtn  = $("trace-run-btn");
const traceHost    = $("trace-host");
const traceResult  = $("trace-result");

traceRunBtn.addEventListener("click", () => {
  const host = traceHost.value.trim() || "8.8.8.8";
  setRunning(traceRunBtn, true, "Run");
  traceResult.textContent = "Tracing to " + host + "…";

  fetch("/api/traceroute", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ host }),
  })
    .then(r => r.json())
    .then(data => {
      traceResult.textContent = data.raw || data.error || "No output.";
    })
    .catch(e => { traceResult.textContent = "Error: " + e; })
    .finally(() => setRunning(traceRunBtn, false, "Run"));
});

// Interfaces
const ifaceRunBtn = $("iface-run-btn");
const ifaceResult = $("iface-result");

let ifacesLoaded = false;

function loadInterfaces() {
  setRunning(ifaceRunBtn, true, "Refresh");
  ifaceResult.textContent = "Loading…";

  fetch("/api/interfaces")
    .then(r => r.json())
    .then(data => {
      const parts = [];
      if (data.default_gateway) parts.push("Default gateway: " + data.default_gateway + "\n");
      if (data.networksetup) parts.push("── Wi-Fi / Ethernet ──\n" + data.networksetup.trim());
      if (data.route_default) parts.push("\n── Default Route ──\n" + data.route_default.trim());
      if (data.ifconfig) {
        // Summarize ifconfig to just active interfaces (skip loopback long output)
        const ifaces = data.ifconfig.split(/\n(?=\w)/);
        const active = ifaces.filter(s => s.includes("status: active") || s.startsWith("en") || s.startsWith("utun0"));
        parts.push("\n── Active Interfaces ──\n" + (active.slice(0, 6).join("\n\n")).trim());
      }
      ifaceResult.textContent = parts.join("\n").trim() || "No data.";
    })
    .catch(e => { ifaceResult.textContent = "Error: " + e; })
    .finally(() => setRunning(ifaceRunBtn, false, "Refresh"));
}

ifaceRunBtn.addEventListener("click", loadInterfaces);

// ── Nearby Networks + Channel Congestion ─────────────────────────

const scanBtn      = $("scan-btn");
const scanTbody    = $("scan-tbody");
const scanNetCount = $("scan-net-count");
const chBars24     = $("ch-bars-24");
const chBars5      = $("ch-bars-5");
const chApCount    = $("ch-ap-count");

let lastConnChannel = null; // updated from WS data for congestion highlighting
let lastApName = null;      // connected AP name (SSID) for nearby network labelling

function secColor(sec) {
  if (!sec) return MUTED;
  if (sec.includes("WPA3")) return GREEN;
  if (sec.includes("WPA2") || sec.includes("WPA")) return SKY;
  if (sec.includes("WEP")) return AMBER;
  return MUTED;
}

function renderChannelBars(container, counts, myChannel) {
  if (!counts || Object.keys(counts).length === 0) {
    container.innerHTML = `<span style="font-size:10px;color:var(--text-muted)">No APs</span>`;
    return;
  }
  const maxCount = Math.max(...Object.values(counts));
  const sorted = Object.keys(counts).map(Number).sort((a, b) => a - b);
  container.innerHTML = "";
  sorted.forEach(ch => {
    const count = counts[ch];
    const isMine = ch === myChannel;
    const frac = Math.max(0.04, count / maxCount);
    const barColor = isMine ? SKY : "#334155";
    const row = document.createElement("div");
    row.className = "ch-bar-row";
    row.innerHTML = `
      <span class="ch-bar-num${isMine ? " mine" : ""}">${ch}</span>
      <div class="ch-bar-track"><div class="ch-bar-fill" style="width:${frac * 100}%;background:${barColor}"></div></div>
      <span class="ch-bar-count" style="color:${barColor}">${count}</span>
    `;
    container.appendChild(row);
  });
}

function renderScanResults(networks, myChannel) {
  const counts24 = {}, counts5 = {};
  let totalAps = 0;

  if (!networks || networks.length === 0) {
    scanTbody.innerHTML = `<tr><td colspan="6" class="scan-empty">No networks found</td></tr>`;
    scanNetCount.textContent = "";
    chBars24.innerHTML = `<span style="font-size:10px;color:var(--text-muted)">No APs</span>`;
    chBars5.innerHTML  = `<span style="font-size:10px;color:var(--text-muted)">No APs</span>`;
    chApCount.textContent = "";
    return;
  }

  // Build channel counts
  networks.forEach(n => {
    const ch = n.channel;
    const band = n.band || "";
    if (ch == null) return;
    totalAps++;
    if (band.startsWith("2.4") || (ch >= 1 && ch <= 14)) {
      counts24[ch] = (counts24[ch] || 0) + 1;
    } else if (band.startsWith("5") || (ch >= 32 && ch <= 177)) {
      counts5[ch] = (counts5[ch] || 0) + 1;
    }
  });

  // Channel bars
  renderChannelBars(chBars24, counts24, myChannel);
  renderChannelBars(chBars5, counts5, myChannel);
  chApCount.textContent = totalAps + " APs scanned";
  scanNetCount.textContent = networks.length + " networks";

  // Scan table
  scanTbody.innerHTML = "";
  networks.forEach(n => {
    const sig    = n.rssi_dbm;
    const sc     = signalColor(sig);
    const isMine = n.channel === myChannel && myChannel != null;
    const tr     = document.createElement("tr");
    if (isMine) tr.className = "connected-row";

    // SSID: show connected AP name on the matched row, otherwise dim "hidden"
    const ssidHtml = isMine && lastApName
      ? `<span style="color:var(--text-body);font-weight:600">${lastApName}</span>`
      : `<span style="color:var(--text-dim);font-style:italic">hidden</span>`;

    // Signal bar + value
    const barPct = sig != null ? Math.max(0, Math.min(100, ((sig + 100) / 70) * 100)) : 0;
    const sigHtml = sig != null
      ? `<span style="color:${sc};font-weight:700">${sig}</span><span style="color:var(--text-dim);font-size:9px"> dBm</span>
         <div style="height:3px;width:52px;background:var(--border);border-radius:2px;margin-top:3px">
           <div style="height:3px;width:${barPct}%;background:${sc};border-radius:2px"></div>
         </div>`
      : "—";

    // Channel + width
    const chHtml = n.channel != null
      ? `${n.channel}${n.channel_width ? `<span style="color:var(--text-dim);font-size:9px"> ${n.channel_width}</span>` : ""}`
      : "—";

    // Band color
    const bandColor = n.band && n.band.startsWith("5") ? SKY
                    : n.band && n.band.startsWith("6") ? "#a78bfa"
                    : "var(--text-muted)";

    // PHY mode — strip "802.11" prefix for brevity
    const phyShort = n.phy_mode ? n.phy_mode.replace("802.11", "") : "—";

    tr.innerHTML = `
      <td>${ssidHtml}</td>
      <td>${sigHtml}</td>
      <td style="color:var(--text-slate)">${chHtml}</td>
      <td style="color:${bandColor}">${n.band || "—"}</td>
      <td style="color:var(--text-slate);font-size:10px">${phyShort}</td>
      <td style="color:${secColor(n.security)}">${n.security || "—"}</td>
    `;
    scanTbody.appendChild(tr);
  });
}

function runScan() {
  scanBtn.disabled = true;
  scanBtn.textContent = "Scanning…";

  fetch("/api/wifi/scan")
    .then(r => r.json())
    .then(data => renderScanResults(data.networks || [], lastConnChannel))
    .catch(() => {
      scanTbody.innerHTML = `<tr><td colspan="6" class="scan-empty">Scan failed</td></tr>`;
    })
    .finally(() => {
      scanBtn.disabled = false;
      scanBtn.textContent = "Scan";
    });
}

scanBtn.addEventListener("click", runScan);

// Auto-scan once on page load after WS connects (give it 1.5s to settle)
setTimeout(runScan, 1500);
// Re-scan every 60 seconds automatically
setInterval(runScan, 60_000);

// ── Network Info ─────────────────────────────────────────────────

const niGateway   = $("ni-gateway");
const niDns       = $("ni-dns");
const niPublic    = $("ni-public");
const niLoading   = $("ni-public-loading");
const niGatewayV6 = $("ni-gateway-v6");
const niDnsV6     = $("ni-dns-v6");
const niPublicV6  = $("ni-public-v6");
const niProxy     = $("ni-proxy");
const niConnected = $("ni-connected");
const niConnDot   = $("ni-conn-dot");
const niSsid      = $("ni-ssid");
const niBssid     = $("ni-bssid");
const niVendor    = $("ni-vendor");
const niSecurity  = $("ni-security");
const niPrivate   = $("ni-private");
const niSubnet    = $("ni-subnet");
const niIpv6      = $("ni-ipv6");
const niMac       = $("ni-mac");
const niRefresh   = $("netinfo-refresh-btn");

let netInfoLoaded = false;

// Set an info-val element: real value gets body color, nullish gets dim+italic.
// Pass { hideEmpty: true } to collapse the parent .info-row when value is absent.
function niSet(el, v, opts = {}) {
  if (!el) return;
  const empty = v == null || v === "" || v === "N/A";
  el.textContent = empty ? "N/A" : v;
  el.classList.toggle("dim", empty);
  if (opts.color && !empty) el.style.color = opts.color;
  else el.style.color = "";
  if (opts.hideEmpty) {
    const row = el.closest(".info-row");
    if (row) row.style.display = empty ? "none" : "";
  }
}

// After all niSet calls, hide any .info-section-title whose following rows are all hidden
function niPruneSections(card) {
  if (!card) return;
  card.querySelectorAll(".info-section-title").forEach(title => {
    let sib = title.nextElementSibling;
    let hasVisible = false;
    while (sib && !sib.classList.contains("info-section-title")) {
      if (sib.style.display !== "none") { hasVisible = true; break; }
      sib = sib.nextElementSibling;
    }
    title.style.display = hasVisible ? "" : "none";
  });
}

function loadNetInfo() {
  netInfoLoaded = true;
  niLoading.style.display = "inline";
  const allVals = [niGateway, niDns, niPublic, niGatewayV6, niDnsV6, niPublicV6,
    niProxy, niConnected, niSsid, niBssid, niVendor, niPrivate, niSubnet, niIpv6, niMac];
  allVals.forEach(el => { if (el) { el.textContent = "—"; el.classList.remove("dim"); } });

  fetch("/api/network/info")
    .then(r => r.json())
    .then(d => {
      // ── Connection ──────────────────────────────────────────────
      niSet(niGateway,   d.gateway);
      niSet(niDns,       d.dns_servers?.length ? d.dns_servers.join(",  ") : null);
      niSet(niPublic,    d.public_ip,   { color: SKY });
      niSet(niGatewayV6, d.gateway_v6,  { hideEmpty: true });
      niSet(niDnsV6,     d.dns_v6?.length ? d.dns_v6.join(",  ") : null, { hideEmpty: true });
      niSet(niPublicV6,  d.public_ipv6, { color: SKY, hideEmpty: true });
      niSet(niProxy,     d.http_proxy === "None" ? null : d.http_proxy, { hideEmpty: true });

      // ── Wi-Fi status ────────────────────────────────────────────
      const conn = d.wifi_connected;
      niConnected.textContent = conn ? "Yes" : "No";
      niConnected.className   = `info-val ${conn ? "green" : "dim"}`;
      niConnDot.style.background = conn ? GREEN : "var(--text-dim)";

      niSet(niSsid,   d.wifi_ssid);
      niSet(niBssid,  d.wifi_bssid,  { hideEmpty: true });
      niSet(niVendor, d.wifi_vendor, { hideEmpty: true });

      // Security badge — hide row if no security info
      const sec = d.wifi_security;
      if (niSecurity) {
        const secRow = niSecurity.closest(".info-row");
        if (!sec) {
          niSecurity.innerHTML = "";
          if (secRow) secRow.style.display = "none";
        } else {
          if (secRow) secRow.style.display = "";
          const bc = sec.includes("WPA3") ? GREEN
                   : sec.includes("WPA") ? SKY
                   : sec === "Open" ? AMBER : "var(--text-slate)";
          niSecurity.innerHTML =
            `<span class="info-badge" style="background:${bc}22;color:${bc}">${sec}</span>`;
        }
      }

      // ── Addressing ──────────────────────────────────────────────
      niSet(niPrivate, d.private_ip);
      niSet(niSubnet,  d.subnet_mask ? `${d.subnet_mask}  (${d.subnet_cidr})` : null, { hideEmpty: true });
      niSet(niIpv6,    d.ipv6_addresses?.length ? d.ipv6_addresses[0] : null, { hideEmpty: true });
      niSet(niMac,     d.mac);

      // Hide section titles that have no visible rows
      document.querySelectorAll("#tab-info .card").forEach(niPruneSections);
    })
    .catch(() => {
      if (niPublic) { niPublic.textContent = "Error"; niPublic.style.color = AMBER; }
    })
    .finally(() => { niLoading.style.display = "none"; });
}

niRefresh.addEventListener("click", () => { netInfoLoaded = false; loadNetInfo(); });

// ── Boot ─────────────────────────────────────────────────────────

connect();
