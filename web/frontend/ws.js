/* NetScope — WebSocket connection + onData dispatcher */
"use strict";

let ws = null;
let reconnectTimer = null;
let reconnectDelay = 1500;
let lastPayloadTs = 0;

// Update freshness label every 500ms (Signal tab only — avoids DOM work on other tabs)
setInterval(() => {
  if ((window.__netscopeCurrentTab || "") !== "signal") return;
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
    reconnectDelay = 1500;
  };

  ws.onmessage = (ev) => {
    try { onData(JSON.parse(ev.data)); } catch (e) { console.warn("WS parse error", e); }
  };

  ws.onclose = () => scheduleReconnect();
  ws.onerror = () => { try { ws.close(); } catch (_) {} };
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => { reconnectTimer = null; connect(); }, reconnectDelay);
  reconnectDelay = Math.min(reconnectDelay * 2, 30000);
}

function onData(d) {
  window.__netscopeLastWs = d;
  updateSignalTab(d);                                              // signal.js
  if (typeof updatePingModule === "function") updatePingModule(d); // ping.js
  const newCh = d.channel ? parseInt(d.channel, 10) : null;
  if (newCh !== lastConnChannel) lastConnChannel = newCh;         // scan.js global
  if (d.ap_name) lastApName = d.ap_name;                         // scan.js global
  lastPayloadTs = d.ts ? d.ts * 1000 : Date.now();
  if (window.nsSession) window.nsSession.onPayload(d);           // session.js
}
