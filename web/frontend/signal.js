/* NetScope — signal tab: RSSI canvas chart + DOM updates */
"use strict";

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
const alertBanner    = $("alert-banner");

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

function bumpRssiHistoryFromPayload(d) {
  rssiHistory.shift();
  rssiHistory.push(d.signal);
  updateRssiBars();
}

function drawRssiBars() {
  const tab = window.__netscopeCurrentTab || "signal";
  if (document.hidden || tab !== "signal") return;

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

  // Dot-grid overlay
  ctx.fillStyle = "rgba(26,37,53,0.3)";
  for (let gx = 0; gx < cW; gx += 24)
    for (let gy = PAD_T; gy < PAD_T + cH; gy += 24)
      ctx.fillRect(gx, gy, 1, 1);

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

  // Reference line at −70 dBm (good/fair threshold)
  const refY = yOf(-70);
  if (refY > PAD_T && refY < PAD_T + cH) {
    ctx.save();
    ctx.strokeStyle = "rgba(34,197,94,0.2)";
    ctx.setLineDash([4, 6]);
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(0, refY); ctx.lineTo(cW, refY); ctx.stroke();
    ctx.restore();
  }

  // "dBm" unit label
  ctx.fillStyle = "#334155";
  ctx.fillText("dBm", cW + 5, h - 3);
  ctx.restore();

  // ── Line + area ───────────────────────────────────────────────
  const N      = rssiHistory.length;
  const stepX  = cW / Math.max(N - 1, 1);
  let latest = null;
  for (let i = N - 1; i >= 0; i--) {
    if (rssiHistory[i] != null) { latest = rssiHistory[i]; break; }
  }
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
  ctx.strokeStyle = lc; ctx.shadowColor = lc; ctx.shadowBlur = 6;
  seg = [];
  for (const p of pts) { if (p) seg.push(p); else { drawSegment(seg, "line"); seg = []; } }
  drawSegment(seg, "line");

  // Dot on latest point
  const last = pts[N - 1];
  if (last) {
    ctx.shadowBlur = 12; ctx.fillStyle = lc;
    ctx.beginPath(); ctx.arc(last.x, last.y, 4, 0, Math.PI * 2); ctx.fill();
  }
  ctx.restore();

  requestAnimationFrame(drawRssiBars);
}

window.__netscopeStartRssiLoop = function netscopeStartRssiLoop() {
  const tab = window.__netscopeCurrentTab || "signal";
  if (!document.hidden && tab === "signal") requestAnimationFrame(drawRssiBars);
};

document.addEventListener("visibilitychange", () => {
  if (!document.hidden && (window.__netscopeCurrentTab || "signal") === "signal") {
    window.__netscopeStartRssiLoop();
  }
});

// ── Signal tab update (called from ws.js onData) ─────────────────

function updateSignalTab(d) {
  const tab = window.__netscopeCurrentTab || "signal";
  if (tab !== "signal" || document.hidden) {
    bumpRssiHistoryFromPayload(d);
    return;
  }

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
  bumpRssiHistoryFromPayload(d);

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

  const isSpike = d.spike === true;
  const pc = isSpike ? "#f97316" : pingColor(d.ping);
  setText(sidePing, d.ping != null ? d.ping + (isSpike ? " !" : "") + " ms" : "—", pc);
  setText(sideAvg, d.p50_ms != null ? d.p50_ms + " ms" : "—", pingColor(d.p50_ms));
  setText(sideJitter, d.jitter_ms != null ? d.jitter_ms + " ms" : "—", MUTED);
  setText(sideLoss, d.loss != null ? d.loss + "%" : "—", lossColor(d.loss));

  // Alert banner
  const al = d.alerts;
  if (al && al.level !== "ok" && al.messages && al.messages.length) {
    const color = al.level === "critical" ? RED : AMBER;
    alertBanner.style.display = "";
    alertBanner.style.background = color + "18";
    alertBanner.style.color = color;
    alertBanner.style.borderColor = color + "44";
    alertBanner.textContent = al.messages[0];
  } else {
    alertBanner.style.display = "none";
  }
}

// Kick off RSSI canvas loop (stops automatically when another tab is active)
window.__netscopeStartRssiLoop();

document.addEventListener("ws:data", e => updateSignalTab(e.detail));
