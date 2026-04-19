/* NetScope — info tab: network information */
"use strict";

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
const secRefresh  = $("sec-refresh-btn");
const secProxy    = $("sec-proxy");
const secPubV4    = $("sec-public-v4");
const secPubV6    = $("sec-public-v6");
const secWifiSec  = $("sec-wifi-security");
const secWifiSsid = $("sec-wifi-ssid");
const secWifiBss  = $("sec-wifi-bssid");
const secDnsV4    = $("sec-dns-v4");

let netInfoLoaded = false;
/** Last successful `/api/network/info` payload — drives Security tab without extra fetch when possible */
let _lastNetInfo = null;

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

function _paintWifiSecurityBadge(el, sec) {
  if (!el) return;
  const secRow = el.closest(".info-row");
  if (!sec) {
    el.innerHTML = "";
    if (secRow) secRow.style.display = "none";
    return;
  }
  if (secRow) secRow.style.display = "";
  const bc = sec.includes("WPA3")
    ? GREEN
    : sec.includes("WPA")
      ? SKY
      : sec === "Open"
        ? AMBER
        : "var(--text-slate)";
  el.innerHTML = `<span class="info-badge" style="background:${bc}22;color:${bc}">${sec}</span>`;
}

function paintSecurityTab() {
  const d = _lastNetInfo;
  if (!d) return;
  niSet(secProxy, d.http_proxy === "None" ? null : d.http_proxy);
  niSet(secPubV4, d.public_ip, { color: SKY });
  niSet(secPubV6, d.public_ipv6, { color: SKY, hideEmpty: true });
  niSet(secDnsV4, d.dns_servers?.length ? d.dns_servers.join(",  ") : null);

  niSet(secWifiSsid, d.wifi_ssid);
  niSet(secWifiBss, d.wifi_bssid, { hideEmpty: true });
  _paintWifiSecurityBadge(secWifiSec, d.wifi_security);
}

function syncSecurityTab() {
  if (_lastNetInfo) paintSecurityTab();
  else loadNetInfo();
}

globalThis.syncSecurityTab = syncSecurityTab;

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

      if (niSecurity) _paintWifiSecurityBadge(niSecurity, d.wifi_security);

      // ── Addressing ──────────────────────────────────────────────
      niSet(niPrivate, d.private_ip);
      niSet(niSubnet,  d.subnet_mask ? `${d.subnet_mask}  (${d.subnet_cidr})` : null, { hideEmpty: true });
      niSet(niIpv6,    d.ipv6_addresses?.length ? d.ipv6_addresses[0] : null, { hideEmpty: true });
      niSet(niMac,     d.mac);

      // Hide section titles that have no visible rows
      document.querySelectorAll("#tab-info .card").forEach(niPruneSections);

      _lastNetInfo = d;
      paintSecurityTab();
    })
    .catch(() => {
      if (niPublic) { niPublic.textContent = "Error"; niPublic.style.color = AMBER; }
    })
    .finally(() => { niLoading.style.display = "none"; });
}

niRefresh.addEventListener("click", () => {
  netInfoLoaded = false;
  loadNetInfo();
});
if (secRefresh) secRefresh.addEventListener("click", () => loadNetInfo());
