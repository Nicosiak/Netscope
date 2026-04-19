/* NetScope — shared constants, colour helpers, DOM utilities */
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

// Strict variant for ping.js chart: RED for null, strict < comparisons
function pingColorStrict(ms) {
  if (ms == null) return '#ef4444';
  if (ms < 30)   return '#22c55e';
  if (ms < 80)   return '#f59e0b';
  return '#ef4444';
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

/** Active tab id — updated from app.js; read from signal.js for rAF / WS throttles. */
window.__netscopeCurrentTab = "signal";
