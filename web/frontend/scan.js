/* NetScope — scan tab: nearby networks + channel congestion */
"use strict";

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

document.addEventListener("ws:data", e => {
  const d = e.detail;
  const newCh = d.channel ? parseInt(d.channel, 10) : null;
  if (newCh !== lastConnChannel) lastConnChannel = newCh;
  if (d.ap_name) lastApName = d.ap_name;
});
