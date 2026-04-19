/* NetScope — Security tab: nmap scan UI (uses window.nsTools from tools.js) */
"use strict";

(function () {
  const runBtn = $("sec-nmap-run");
  const hostInput = $("sec-nmap-host");
  const gwBtn = $("sec-nmap-gateway");
  const clearBtn = $("sec-nmap-clear");
  const copyBtn = $("sec-nmap-copy");
  const saveBtn = $("sec-nmap-save");
  const outPre = $("nmap-result");
  const outWrap = document.querySelector("#tab-security .sec-nmap-out");
  const statusEl = $("sec-nmap-status");
  const hintEl = $("sec-nmap-preset-hint");
  const versionEl = $("sec-nmap-version");
  const summaryEl = $("sec-nmap-summary");
  const pills = document.querySelectorAll(".sec-nmap-pill");
  const { setRunning } = window.nsTools || {};

  const PRESET_HINTS = {
    quick: "Quick: top 50 TCP ports, no ping probe (-Pn). Fast baseline.",
    services: "Adds version detection (-sV) on 80 top ports — medium runtime.",
    safe_scripts: "Adds NSE scripts in the safe category — broader than Quick.",
    vuln: "Runs NSE vuln category on 80 top ports — slow, noisy; use only where permitted.",
    discovery: "Host discovery only (-sn). ICMP/ARP behaviour varies by OS; no port scan.",
    ssl: "TCP 443 with ssl-cert and ssl-enum-ciphers — TLS inspection only.",
    udp_top: "UDP top 20 ports — may require root on some systems; confirm before running.",
  };

  /** Presets that require an explicit browser confirm before POST. */
  const HEAVY_PRESETS = new Set(["vuln", "udp_top"]);

  let preset = "quick";
  let lastRaw = "";
  let lastFilenameBase = "nmap";

  function syncPillUi() {
    pills.forEach(p => {
      p.classList.toggle("active", p.dataset.nmapPreset === preset);
    });
    if (hintEl) hintEl.textContent = PRESET_HINTS[preset] || "";
  }

  pills.forEach(p => {
    p.addEventListener("click", () => {
      const next = p.dataset.nmapPreset;
      if (next) {
        preset = next;
        syncPillUi();
      }
    });
  });
  syncPillUi();

  function clearSummary() {
    if (!summaryEl) return;
    summaryEl.textContent = "";
    summaryEl.classList.remove("has-rows");
  }

  function renderScanSummary(scan) {
    if (!summaryEl) return;
    summaryEl.textContent = "";
    summaryEl.classList.remove("has-rows");
    if (!scan || typeof scan !== "object") return;

    if (scan.parse_error) {
      const p = document.createElement("p");
      p.style.padding = "8px 10px";
      p.style.color = "var(--text-muted)";
      p.textContent = "Could not parse XML summary (" + String(scan.parse_error) + ").";
      summaryEl.appendChild(p);
      summaryEl.classList.add("has-rows");
      return;
    }

    const ports = scan.ports && scan.ports.length ? scan.ports : null;
    if (ports) {
      const tbl = document.createElement("table");
      const thead = document.createElement("thead");
      const hr = document.createElement("tr");
      ["Host", "Port", "Proto", "Service", "Product"].forEach(label => {
        const th = document.createElement("th");
        th.textContent = label;
        hr.appendChild(th);
      });
      thead.appendChild(hr);
      tbl.appendChild(thead);
      const tb = document.createElement("tbody");
      ports.forEach(row => {
        const tr = document.createElement("tr");
        [row.host, row.port, row.protocol, row.service, row.product].forEach(cell => {
          const td = document.createElement("td");
          td.textContent = cell != null ? String(cell) : "";
          tr.appendChild(td);
        });
        tb.appendChild(tr);
      });
      tbl.appendChild(tb);
      summaryEl.appendChild(tbl);
      summaryEl.classList.add("has-rows");
      return;
    }

    const hosts = scan.hosts && scan.hosts.length ? scan.hosts : null;
    if (hosts) {
      const tbl = document.createElement("table");
      const thead = document.createElement("thead");
      const hr = document.createElement("tr");
      ["Address", "Type", "Status", "Names"].forEach(label => {
        const th = document.createElement("th");
        th.textContent = label;
        hr.appendChild(th);
      });
      thead.appendChild(hr);
      tbl.appendChild(thead);
      const tb = document.createElement("tbody");
      hosts.forEach(h => {
        const tr = document.createElement("tr");
        const addr0 = h.addresses && h.addresses[0] ? h.addresses[0].addr : "";
        const typ = h.addresses && h.addresses[0] ? h.addresses[0].type : "";
        const st = h.status || "";
        const names = (h.names || []).join(", ");
        [addr0, typ, st, names].forEach(cell => {
          const td = document.createElement("td");
          td.textContent = cell != null ? String(cell) : "";
          tr.appendChild(td);
        });
        tb.appendChild(tr);
      });
      tbl.appendChild(tb);
      summaryEl.appendChild(tbl);
      summaryEl.classList.add("has-rows");
    }
  }

  function loadNmapVersion() {
    if (!versionEl) return;
    fetch("/api/nmap/version")
      .then(r => r.json())
      .then(d => {
        if (d.available && d.version) versionEl.textContent = d.version;
        else if (d.available === false) versionEl.textContent = "nmap not found on PATH (brew install nmap)";
        else versionEl.textContent = "";
      })
      .catch(() => {
        versionEl.textContent = "";
      });
  }
  loadNmapVersion();

  if (gwBtn && hostInput) {
    gwBtn.addEventListener("click", () => {
      gwBtn.disabled = true;
      fetch("/api/network/gateway")
        .then(r => r.json())
        .then(d => {
          if (d.gateway) hostInput.value = String(d.gateway);
          else if (statusEl) statusEl.textContent = "No default gateway found.";
        })
        .catch(() => {
          if (statusEl) statusEl.textContent = "Could not read gateway.";
        })
        .finally(() => {
          gwBtn.disabled = false;
        });
    });
  }

  function clearOutput() {
    if (outPre) outPre.textContent = "";
    clearSummary();
    lastRaw = "";
    if (statusEl) statusEl.textContent = "";
  }

  if (clearBtn) clearBtn.addEventListener("click", clearOutput);

  if (copyBtn) {
    copyBtn.addEventListener("click", () => {
      const t = (outPre && outPre.textContent) || lastRaw || "";
      if (!t) return;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(t).catch(() => {});
      }
    });
  }

  if (saveBtn) {
    saveBtn.addEventListener("click", () => {
      const t = (outPre && outPre.textContent) || lastRaw || "";
      if (!t) return;
      const blob = new Blob([t], { type: "text/plain;charset=utf-8" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${lastFilenameBase.replace(/[^a-zA-Z0-9._-]+/g, "_")}.txt`;
      a.click();
      URL.revokeObjectURL(a.href);
    });
  }

  function runNmap() {
    if (!runBtn || !hostInput || !outPre) return;
    const host = hostInput.value.trim() || "127.0.0.1";

    if (HEAVY_PRESETS.has(preset)) {
      const ok = window.confirm(
        preset === "vuln"
          ? "This preset runs NSE vuln scripts and is noisy. Only continue on hosts you are explicitly allowed to test."
          : "UDP scanning can be intrusive and may require root on some systems. Only continue on hosts you are explicitly allowed to test."
      );
      if (!ok) return;
    }

    outPre.textContent = "";
    clearSummary();
    if (statusEl) statusEl.textContent = "Running nmap…";

    const sr = typeof setRunning === "function" ? setRunning : () => {};
    sr(runBtn, true, "Run scan", "nmap");

    fetch("/api/nmap", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ host, preset }),
    })
      .then(async r => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) {
          const det = data.detail;
          const msg = Array.isArray(det)
            ? det.map(e => e.msg || e.message).filter(Boolean).join("; ")
            : typeof det === "string"
              ? det
              : r.statusText || "Request failed";
          outPre.textContent = msg;
          if (statusEl) statusEl.textContent = "Request error.";
          return;
        }
        if (data.available === false) {
          outPre.textContent = data.error || "nmap not installed.";
          if (statusEl) statusEl.textContent = "Install: brew install nmap";
          return;
        }
        if (data.error && !data.raw) {
          outPre.textContent = data.error;
        } else {
          outPre.textContent = data.raw != null && data.raw !== "" ? data.raw : "(no stderr output)";
        }
        lastRaw = outPre.textContent || "";
        lastFilenameBase = `nmap-${data.target || host}-${data.preset || preset}`;
        renderScanSummary(data.scan);

        const ec = data.exit_code;
        const okScan = data.ok === true;
        const ms = data.duration_ms;
        const argv = Array.isArray(data.argv) ? data.argv.join(" ") : "";
        const argvShort = argv.length > 140 ? argv.slice(0, 137) + "…" : argv;
        if (statusEl) {
          let line =
            "Exit " +
            (ec != null ? ec : "?") +
            (ms != null ? " · " + ms + " ms" : "") +
            (okScan ? " · finished" : " · finished with warnings/errors — see output");
          if (argvShort) line += "\n" + argvShort;
          statusEl.textContent = line;
        }
        if (outWrap) outWrap.scrollTop = 0;
      })
      .catch(e => {
        outPre.textContent = "Error: " + e;
        if (statusEl) statusEl.textContent = "Network error.";
      })
      .finally(() => {
        sr(runBtn, false, "Run scan", "nmap");
      });
  }

  if (runBtn) runBtn.addEventListener("click", runNmap);
  if (hostInput) {
    hostInput.addEventListener("keydown", e => {
      if (e.key === "Enter") {
        e.preventDefault();
        runNmap();
      }
    });
  }
})();
