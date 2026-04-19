/* NetScope — tab switching + boot */
"use strict";

// ── Tab switching ────────────────────────────────────────────────

const tabBtns = document.querySelectorAll(".tab-btn");
const tabPanels = {
  signal: $("tab-signal"),
  tools: $("tab-tools"),
  info: $("tab-info"),
  security: $("tab-security"),
};
let currentTab = "signal";
window.__netscopeCurrentTab = currentTab;

tabBtns.forEach(btn => {
  btn.addEventListener("click", () => {
    const t = btn.dataset.tab;
    if (t === currentTab) return;
    currentTab = t;
    window.__netscopeCurrentTab = t;
    tabBtns.forEach(b => b.classList.toggle("active", b.dataset.tab === t));
    Object.entries(tabPanels).forEach(([k, panel]) => {
      panel.classList.toggle("active", k === t);
    });
    if (t === "signal") {
      if (typeof updateSignalTab === "function" && window.__netscopeLastWs) {
        updateSignalTab(window.__netscopeLastWs);
      }
      if (typeof window.__netscopeStartRssiLoop === "function") {
        window.__netscopeStartRssiLoop();
      }
    }
    if (t === "info" && !netInfoLoaded) loadNetInfo();
    if (t === "security" && typeof syncSecurityTab === "function") syncSecurityTab();
    if (t === "tools" && !ifacesLoaded) { ifacesLoaded = true; loadInterfaces(); }
    if (t === "tools") {
      if (typeof window.__netscopeRefreshPing === "function") window.__netscopeRefreshPing();
      if (typeof sizePingChart === "function") {
        requestAnimationFrame(() => requestAnimationFrame(() => sizePingChart()));
      }
    }
  });
});

// ── Boot ─────────────────────────────────────────────────────────

connect();
if (window.nsSession) window.nsSession.initSession();
