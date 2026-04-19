/* NetScope — tools tab: shared banner + DNS, speed, iperf, traceroute panel, interfaces */
"use strict";

// ── Shared: activity banner + busy buttons ─────────────────────────────
window.nsTools = (function () {
  const toolMessages = {
    speed: { msg: "Speed test running — latency will be affected", color: "#ef4444" },
    iperf: { msg: "iperf3 running — bandwidth saturated", color: "#ef4444" },
    dns: { msg: "DNS test running — brief latency variance normal", color: "#f59e0b" },
    traceroute: { msg: "Traceroute running — extra probes on the wire", color: "#f59e0b" },
    nmap: { msg: "nmap scan running — many probes on the wire", color: "#f59e0b" },
  };
  const activeTools = new Set();

  function updateToolBanner() {
    const el = document.getElementById("tool-activity");
    if (!el) return;
    for (const id of ["speed", "iperf", "dns", "traceroute", "nmap"]) {
      if (activeTools.has(id)) {
        const { msg, color } = toolMessages[id];
        el.textContent = "⚠ " + msg;
        el.style.color = color;
        el.style.display = "";
        return;
      }
    }
    el.style.display = "none";
  }

  function setRunning(btn, running, defaultLabel, toolId) {
    if (!btn) return;
    btn.disabled = running;
    btn.textContent = running ? "Running…" : defaultLabel;
    if (toolId) {
      if (running) activeTools.add(toolId);
      else activeTools.delete(toolId);
      updateToolBanner();
    }
  }

  function addActiveTool(id) {
    activeTools.add(id);
    updateToolBanner();
  }

  function removeActiveTool(id) {
    activeTools.delete(id);
    updateToolBanner();
  }

  return { setRunning, addActiveTool, removeActiveTool, updateToolBanner };
})();

const { setRunning, addActiveTool, removeActiveTool } = window.nsTools;

// ── WAN Link Check ────────────────────────────────────────────────────
(function initWanCheckTool() {
  const runBtn = $("wan-run-btn");
  const statusRow = $("wan-status-row");
  const badge = $("wan-badge");
  const gwLabel = $("wan-gw-label");
  const tiles = $("wan-tiles");
  const hopsEl = $("wan-hops");
  const rawDetails = $("wan-raw-details");
  const rawPre = $("wan-raw");
  const resultEl = $("wan-result");
  const wanLoss = $("wan-loss");
  const wanAvg = $("wan-avg");
  const wanIspRtt = $("wan-isp-rtt");
  const wanSegment = $("wan-segment");
  if (!runBtn) return;

  function wanRttColor(ms) {
    if (ms == null) return MUTED;
    if (ms <= 30) return GREEN;
    if (ms <= 80) return AMBER;
    return RED;
  }

  function setBadge(up) {
    if (!badge) return;
    badge.className = "wan-badge";
    if (up === true)  { badge.classList.add("wan-badge-up");      badge.textContent = "WAN UP"; }
    else if (up === false) { badge.classList.add("wan-badge-down"); badge.textContent = "WAN DOWN"; }
    else              { badge.classList.add("wan-badge-unknown"); badge.textContent = "INDETERMINATE"; }
  }

  runBtn.addEventListener("click", () => {
    setRunning(runBtn, true, "Run Test");
    if (badge) { badge.className = "wan-badge wan-badge-checking"; badge.textContent = "CHECKING…"; }
    if (statusRow) show(statusRow);
    if (gwLabel) gwLabel.textContent = "";
    hide(tiles);
    if (hopsEl) { hide(hopsEl); hopsEl.textContent = ""; }
    if (rawDetails) rawDetails.style.display = "none";
    if (resultEl) resultEl.textContent = "";

    fetch("/api/wan/check", { method: "POST" })
      .then(r => r.json())
      .then(data => {
        if (data.error) {
          if (resultEl) resultEl.textContent = "Error: " + data.error;
          setBadge(null);
          return;
        }

        setBadge(data.wan_up);
        if (gwLabel && data.gateway) gwLabel.textContent = "Gateway: " + data.gateway;

        setText(wanLoss, data.ping_loss_pct != null ? data.ping_loss_pct.toFixed(0) + "%" : "—", lossColor(data.ping_loss_pct));
        setText(wanAvg, data.ping_avg_ms != null ? data.ping_avg_ms.toFixed(1) + " ms" : "—", wanRttColor(data.ping_avg_ms));
        setText(wanIspRtt, data.isp_edge_rtt_ms != null ? data.isp_edge_rtt_ms.toFixed(1) + " ms" : "silent", data.isp_edge_rtt_ms != null ? wanRttColor(data.isp_edge_rtt_ms) : MUTED);
        setText(wanSegment, data.wan_segment_ms != null ? data.wan_segment_ms.toFixed(1) + " ms" : "—", data.wan_segment_ms != null ? wanRttColor(data.wan_segment_ms) : MUTED);
        show(tiles);

        if (hopsEl && data.hops && data.hops.length) {
          hopsEl.textContent = "";
          const ispIp = data.isp_edge_ip;
          data.hops.forEach(h => {
            const row = document.createElement("div");
            row.className = "wan-hop-row";
            const num = document.createElement("span");
            num.className = "wan-hop-num";
            num.textContent = h.ttl != null ? h.ttl : "?";
            const host = document.createElement("span");
            const isIsp = h.ip && h.ip === ispIp;
            host.className = "wan-hop-host" + (isIsp ? " wan-hop-isp" : "");
            host.textContent = h.hostname || h.ip || "* * *";
            if (h.ip && h.hostname) host.title = h.ip;
            const rtt = document.createElement("span");
            rtt.className = "wan-hop-rtt";
            rtt.style.color = wanRttColor(h.rtt_ms);
            rtt.textContent = h.rtt_ms != null ? h.rtt_ms.toFixed(1) + " ms" : "* * *";
            row.appendChild(num);
            row.appendChild(host);
            row.appendChild(rtt);
            hopsEl.appendChild(row);
          });
          show(hopsEl);
        }

        if (rawDetails && rawPre && data.raw_trace) {
          rawPre.textContent = data.raw_trace;
          rawDetails.style.display = "";
        }
      })
      .catch(e => {
        if (resultEl) resultEl.textContent = "Error: " + e;
        setBadge(null);
      })
      .finally(() => setRunning(runBtn, false, "Run Test"));
  });
})();

// ── DNS ───────────────────────────────────────────────────────────────
(function initDnsTool() {
  const dnsRunBtn = $("dns-run-btn");
  const dnsHostInput = $("dns-host-input");
  const dnsRecordType = $("dns-record-type");
  const dnsBars = $("dns-bars");
  const dnsResult = $("dns-result");
  if (!dnsRunBtn || !dnsHostInput || !dnsBars || !dnsResult) return;

  function formatAnswers(r) {
    const ans = r.answers;
    if (Array.isArray(ans) && ans.length) {
      return ans.map(a => `${a.type} ${a.data}`.trim()).join(", ");
    }
    if (r.answer_count === 0) return "(NOERROR, 0 answers)";
    if (r.answer_count != null) return `(ANSWER: ${r.answer_count})`;
    return "—";
  }

  dnsRunBtn.addEventListener("click", () => {
    const host = dnsHostInput.value.trim() || "google.com";
    const recordType = dnsRecordType && dnsRecordType.value === "AAAA" ? "AAAA" : "A";
    setRunning(dnsRunBtn, true, "Run Test", "dns");
    hide(dnsBars);
    dnsResult.textContent = "";

    fetch("/api/dns", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ host, record_type: recordType }),
    })
      .then(r => r.json())
      .then(data => {
        const results = data.results || [];
        if (!results.length) {
          dnsResult.textContent = "No results.";
          return;
        }
        const maxMs = Math.max(1, ...results.map(r => r.query_time_ms || 0));
        dnsBars.textContent = "";
        results.forEach(r => {
          const ms = r.query_time_ms;
          const fraction = ms != null ? Math.max(0.02, ms / maxMs) : 0;
          const color = ms == null ? MUTED : ms <= 30 ? GREEN : ms <= 80 ? AMBER : RED;
          const row = document.createElement("div");
          row.className = "dns-bar-row";
          const lbl = document.createElement("span");
          lbl.className = "dns-bar-lbl";
          lbl.textContent = r.label || r.server_queried || "System";
          const track = document.createElement("div");
          track.className = "dns-bar-track";
          const fill = document.createElement("div");
          fill.className = "dns-bar-fill";
          fill.style.width = fraction * 100 + "%";
          fill.style.background = color;
          track.appendChild(fill);
          const val = document.createElement("span");
          val.className = "dns-bar-val";
          val.style.color = color;
          val.textContent = ms != null ? ms + " ms" : "timeout";
          row.appendChild(lbl);
          row.appendChild(track);
          row.appendChild(val);
          dnsBars.appendChild(row);
        });
        show(dnsBars);
        const hdr = `Type ${data.record_type || recordType} · ${host}`;
        const lines = [hdr, ""].concat(
          results.map(r => {
            const t = r.query_time_ms != null ? r.query_time_ms + " ms" : "timeout";
            const rr = formatAnswers(r);
            return `${(r.label || "").padEnd(22)} ${t.padStart(8)}  ${rr}`;
          }),
        );
        dnsResult.textContent = lines.join("\n");
      })
      .catch(e => {
        dnsResult.textContent = "Error: " + e;
      })
      .finally(() => setRunning(dnsRunBtn, false, "Run Test", "dns"));
  });
})();

// ── Speed (networkQuality) ────────────────────────────────────────────
(function initSpeedTool() {
  const speedRunBtn = $("speed-run-btn");
  const speedMaxInput = $("speed-max-sec");
  const speedTiles = $("speed-tiles");
  const speedBars = $("speed-bars");
  const speedMeta = $("speed-meta");
  const speedRunRow = $("speed-run-row");
  const speedRunElapsed = $("speed-run-elapsed");
  const speedResult = $("speed-result");
  const speedJsonDetails = $("speed-json-details");
  const speedJsonPre = $("speed-json-pre");
  const spDl = $("sp-dl");
  const spUl = $("sp-ul");
  const spRpm = $("sp-rpm");
  const spRtt = $("sp-rtt");
  if (!speedRunBtn || !speedTiles || !speedResult || !spDl || !spUl || !spRpm || !spRtt) return;

  /** RPM from networkQuality: higher is better. */
  function speedRpmColor(rpm) {
    if (rpm == null || Number.isNaN(rpm)) return MUTED;
    if (rpm >= 400) return GREEN;
    if (rpm >= 200) return AMBER;
    return RED;
  }
  /** Base RTT (ms): lower is better. */
  function speedRttColor(ms) {
    if (ms == null || Number.isNaN(ms)) return MUTED;
    if (ms <= 40) return GREEN;
    if (ms <= 80) return AMBER;
    return RED;
  }

  function buildSpeedRequestBody() {
    const raw = speedMaxInput && speedMaxInput.value.trim();
    if (!raw) return {};
    const n = Number(raw);
    if (!Number.isFinite(n)) return {};
    const r = Math.round(n);
    if (r < 20 || r > 90) {
      return {
        invalid: true,
        msg: "Max runtime must be between 20 and 90 seconds, or leave empty for the default (full) run.",
      };
    }
    return { max_seconds: r };
  }

  function renderSpeedBars(dlMbps, ulMbps) {
    if (!speedBars) return;
    speedBars.textContent = "";
    if (dlMbps == null && ulMbps == null) {
      hide(speedBars);
      return;
    }
    const dl = dlMbps != null && !Number.isNaN(dlMbps) ? dlMbps : 0;
    const ul = ulMbps != null && !Number.isNaN(ulMbps) ? ulMbps : 0;
    const max = Math.max(dl, ul, 0.01);
    show(speedBars);
    [
      { lab: "Download", mbps: dlMbps, bps: dl },
      { lab: "Upload", mbps: ulMbps, bps: ul },
    ].forEach(({ lab, mbps, bps }) => {
      const fraction = mbps != null && !Number.isNaN(mbps) ? Math.max(0.02, bps / max) : 0;
      const color = lab === "Download" ? GREEN : SKY;
      const row = document.createElement("div");
      row.className = "dns-bar-row";
      const lbl = document.createElement("span");
      lbl.className = "dns-bar-lbl";
      lbl.textContent = lab;
      const track = document.createElement("div");
      track.className = "dns-bar-track";
      const fill = document.createElement("div");
      fill.className = "dns-bar-fill";
      fill.style.width = fraction * 100 + "%";
      fill.style.background = color;
      track.appendChild(fill);
      const vspan = document.createElement("span");
      vspan.className = "dns-bar-val";
      vspan.style.color = color;
      vspan.textContent = mbps != null && !Number.isNaN(mbps) ? mbps.toFixed(1) + " Mbps" : "—";
      row.appendChild(lbl);
      row.appendChild(track);
      row.appendChild(vspan);
      speedBars.appendChild(row);
    });
  }

  speedRunBtn.addEventListener("click", () => {
    const req = buildSpeedRequestBody();
    if (req.invalid) {
      speedResult.textContent = req.msg;
      return;
    }

    setRunning(speedRunBtn, true, "Run Test", "speed");
    hide(speedTiles);
    hide(speedBars);
    if (speedMeta) hide(speedMeta);
    if (speedJsonDetails) {
      speedJsonDetails.style.display = "none";
      speedJsonDetails.open = false;
    }
    if (speedJsonPre) speedJsonPre.textContent = "";
    speedResult.textContent = "";

    if (speedRunRow) {
      speedRunRow.style.display = "";
      speedRunRow.setAttribute("aria-hidden", "false");
    }
    if (speedRunElapsed) speedRunElapsed.textContent = "0.0 s";
    const t0 = performance.now();
    const tick = setInterval(() => {
      if (speedRunElapsed) speedRunElapsed.textContent = ((performance.now() - t0) / 1000).toFixed(1) + " s";
    }, 200);

    fetch("/api/speed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    })
      .then(r => {
        if (!r.ok) return r.text().then(t => Promise.reject(new Error(t || r.statusText)));
        return r.json();
      })
      .then(data => {
        speedResult.textContent = data.summary || "";
        const m = data.metrics;
        const j = data.json || {};
        const useMetrics =
          m &&
          (m.dl_mbps != null ||
            m.ul_mbps != null ||
            m.responsiveness_rpm != null ||
            m.base_rtt_ms != null);

        let dlMbps = null;
        let ulMbps = null;

        if (useMetrics) {
          if (m.dl_mbps != null) dlMbps = m.dl_mbps;
          if (m.ul_mbps != null) ulMbps = m.ul_mbps;
          setText(spDl, dlMbps != null ? dlMbps.toFixed(1) + " Mbps" : "—", SKY);
          setText(spUl, ulMbps != null ? ulMbps.toFixed(1) + " Mbps" : "—", SKY);
          setText(
            spRpm,
            m.responsiveness_rpm != null ? String(Math.round(m.responsiveness_rpm)) : "—",
            speedRpmColor(m.responsiveness_rpm),
          );
          setText(
            spRtt,
            m.base_rtt_ms != null ? m.base_rtt_ms + " ms" : "—",
            speedRttColor(m.base_rtt_ms),
          );
        } else if (j && Object.keys(j).length) {
          const dl = j.dl_throughput;
          const ul = j.ul_throughput;
          if (dl != null) dlMbps = dl / 1e6;
          if (ul != null) ulMbps = ul / 1e6;
          setText(spDl, dl != null ? (dl / 1e6).toFixed(1) + " Mbps" : "—", SKY);
          setText(spUl, ul != null ? (ul / 1e6).toFixed(1) + " Mbps" : "—", SKY);
          setText(spRpm, j.responsiveness != null ? String(j.responsiveness) : "—", speedRpmColor(Number(j.responsiveness)));
          setText(spRtt, j.base_rtt != null ? j.base_rtt + " ms" : "—", speedRttColor(Number(j.base_rtt)));
        }

        const iface = (m && m.interface_name) || (j && j.interface_name) || (j && j.interface);
        const startD = m && m.start_date;
        const endD = m && m.end_date;
        if (speedMeta) {
          if (iface || startD || endD) {
            const parts = [];
            if (iface) parts.push(String(iface));
            if (startD) parts.push("start: " + startD);
            if (endD) parts.push("end: " + endD);
            speedMeta.textContent = parts.join(" · ");
            show(speedMeta);
          } else {
            hide(speedMeta);
          }
        }

        if (j && Object.keys(j).length) {
          show(speedTiles);
          renderSpeedBars(dlMbps, ulMbps);
          if (speedJsonPre && speedJsonDetails) {
            speedJsonPre.textContent = JSON.stringify(j, null, 2);
            speedJsonDetails.style.display = "";
          }
        } else {
          renderSpeedBars(null, null);
        }
      })
      .catch(e => {
        speedResult.textContent = "Error: " + e;
        if (speedJsonDetails) speedJsonDetails.style.display = "none";
      })
      .finally(() => {
        clearInterval(tick);
        if (speedRunRow) {
          hide(speedRunRow);
          speedRunRow.setAttribute("aria-hidden", "true");
        }
        setRunning(speedRunBtn, false, "Run Test", "speed");
      });
  });
})();

// ── iperf3 ────────────────────────────────────────────────────────────
(function initIperfTool() {
  const iperfDlBtn = $("iperf-dl-btn");
  const iperfUlBtn = $("iperf-ul-btn");
  const iperfHost = $("iperf-host");
  const iperfTiles = $("iperf-tiles");
  const iperfResult = $("iperf-result");
  const ipMbps = $("ip-mbps");
  const ipRetx = $("ip-retx");
  const ipDur = $("ip-dur");
  if (!iperfDlBtn || !iperfUlBtn || !iperfHost || !iperfTiles || !iperfResult || !ipMbps || !ipRetx || !ipDur)
    return;

  function runIperf(direction) {
    const host = iperfHost.value.trim();
    if (!host) {
      iperfResult.textContent = "Enter a server hostname or IP.";
      return;
    }
    [iperfDlBtn, iperfUlBtn].forEach(b => {
      b.disabled = true;
    });
    iperfDlBtn.textContent = direction === "download" ? "Running…" : "Download";
    iperfUlBtn.textContent = direction === "upload" ? "Running…" : "Upload";
    addActiveTool("iperf");
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
        setText(
          ipMbps,
          mbps != null ? mbps.toFixed(1) + " Mbps" : "—",
          mbps != null ? (mbps >= 100 ? GREEN : mbps >= 25 ? AMBER : RED) : MUTED,
        );
        setText(ipRetx, data.retransmits != null ? data.retransmits : "—");
        setText(ipDur, data.duration_s != null ? data.duration_s.toFixed(1) + " s" : "—");
        show(iperfTiles);
        iperfResult.textContent = data.raw || "";
      })
      .catch(e => {
        iperfResult.textContent = "Error: " + e;
      })
      .finally(() => {
        [iperfDlBtn, iperfUlBtn].forEach(b => {
          b.disabled = false;
        });
        iperfDlBtn.textContent = "Download";
        iperfUlBtn.textContent = "Upload";
        removeActiveTool("iperf");
      });
  }

  iperfDlBtn.addEventListener("click", () => runIperf("download"));
  iperfUlBtn.addEventListener("click", () => runIperf("upload"));
})();

// ── Traceroute panel ─────────────────────────────────────────────────
(function initTraceroutePanel() {
  const traceRunBtn = $("trace-run-btn");
  const traceHost = $("trace-host");
  const traceResult = $("trace-result");
  const traceHopsWrap = $("trace-hops-wrap");
  const traceRawDetails = $("trace-raw-details");
  const tracePillGateway = $("trace-pill-gateway");

  let traceLastRaw = "";

  function traceClearPillActive() {
    document.querySelectorAll("#trace-module .tr-ref-pill").forEach(p => p.classList.remove("tr-ref-pill-active"));
  }

  function traceSyncPillActive() {
    if (!traceHost) return;
    const v = traceHost.value.trim();
    traceClearPillActive();
    if (!v) return;
    const gw = tracePillGateway;
    if (gw && gw.dataset.traceGateway && gw.dataset.traceGateway === v) {
      gw.classList.add("tr-ref-pill-active");
      return;
    }
    document.querySelectorAll("#trace-module .tr-ref-pill[data-trace-host]").forEach(p => {
      if (p.dataset.traceHost === v) p.classList.add("tr-ref-pill-active");
    });
  }

  function traceRefreshIdlePanel() {
    if (!traceRunBtn || traceRunBtn.disabled) return;
    if (typeof renderTracerouteModule !== "function" || !traceHopsWrap) return;
    renderTracerouteModule(
      traceHopsWrap,
      { hops: [], meta: { target: traceHost.value.trim() || "8.8.8.8" } },
      { hostInput: traceHost, mode: "idle" },
    );
    traceSyncPillActive();
  }

  function traceQuickSetTrace(host) {
    if (!traceHost) return;
    traceHost.value = host;
    traceRefreshIdlePanel();
  }

  function tracePillGatewayClick() {
    const btn = tracePillGateway;
    if (!btn || !traceHost) return;
    btn.disabled = true;
    fetch("/api/network/gateway")
      .then(r => r.json())
      .then(d => {
        btn.disabled = false;
        if (d.gateway) {
          btn.dataset.traceGateway = String(d.gateway);
          traceHost.value = String(d.gateway);
          traceRefreshIdlePanel();
        }
      })
      .catch(() => {
        btn.disabled = false;
      });
  }

  function traceSetLive(on) {
    document.querySelectorAll(".tr-ref-badge").forEach(el => {
      el.classList.toggle("tr-ref-badge-live", !!on);
    });
  }

  function _detailToText(detail) {
    if (detail == null) return "";
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail.map(e => (e && (e.msg || e.message)) || "").filter(Boolean).join("; ");
    }
    return String(detail);
  }

  function applyTraceResponse(data, opts) {
    opts = opts || {};
    let raw = "";
    if (data && data.raw != null) raw = String(data.raw);
    else if (data && data.error != null) raw = String(data.error);
    else if (data && data.detail != null) raw = _detailToText(data.detail);
    const hops = data && Array.isArray(data.hops) ? data.hops : [];
    traceLastRaw = raw;
    if (traceResult) traceResult.textContent = raw || "No output.";
    if (typeof renderTracerouteModule === "function" && traceHopsWrap) {
      renderTracerouteModule(traceHopsWrap, data, Object.assign({ hostInput: traceHost }, opts));
      traceSyncPillActive();
    } else if (traceHopsWrap) {
      hide(traceHopsWrap);
    }
    if (traceRawDetails) traceRawDetails.open = hops.length === 0 && raw.trim().length > 0;
  }

  function runTraceroute() {
    if (!traceHost) return;
    const host = traceHost.value.trim() || "8.8.8.8";
    traceSetLive(true);
    setRunning(traceRunBtn, true, "Run", "traceroute");
    traceLastRaw = "";
    if (typeof renderTracerouteModule === "function" && traceHopsWrap) {
      renderTracerouteModule(
        traceHopsWrap,
        { hops: [], meta: { target: host }, raw: "" },
        { hostInput: traceHost, mode: "running" },
      );
    }
    if (traceResult) traceResult.textContent = "Tracing to " + host + "…";
    if (traceRawDetails) traceRawDetails.open = true;

    fetch("/api/traceroute", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ host }),
    })
      .then(async r => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) {
          const msg = _detailToText(data.detail) || r.statusText || "Request failed (" + r.status + ")";
          applyTraceResponse({ raw: msg, hops: [] }, { httpOk: false });
          return;
        }
        applyTraceResponse(data, { httpOk: true });
      })
      .finally(() => {
        setRunning(traceRunBtn, false, "Run", "traceroute");
        traceSetLive(false);
      });
  }

  if (traceRunBtn) traceRunBtn.addEventListener("click", runTraceroute);
  if (traceHost) {
    traceHost.addEventListener("keydown", e => {
      if (e.key === "Enter") {
        e.preventDefault();
        runTraceroute();
      }
    });
    traceHost.addEventListener("input", () => {
      traceClearPillActive();
    });
  }
  if (tracePillGateway) tracePillGateway.addEventListener("click", tracePillGatewayClick);
  document.querySelectorAll("#trace-module .tr-ref-pill[data-trace-host]").forEach(p => {
    p.addEventListener("click", () => traceQuickSetTrace(p.dataset.traceHost || ""));
  });
  if (traceHopsWrap && typeof renderTracerouteModule === "function") {
    renderTracerouteModule(traceHopsWrap, { hops: [], meta: {} }, { hostInput: traceHost, mode: "idle" });
    traceSyncPillActive();
  }
})();

// ── Interfaces (globals for app.js) ───────────────────────────────────
var ifacesLoaded = false;

function loadInterfaces() {
  const ifaceRunBtn = $("iface-run-btn");
  const ifaceResult = $("iface-result");
  if (!ifaceRunBtn || !ifaceResult) return;
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
        const ifaces = data.ifconfig.split(/\n(?=\w)/);
        const active = ifaces.filter(s => s.includes("status: active") || s.startsWith("en") || s.startsWith("utun0"));
        parts.push("\n── Active Interfaces ──\n" + active.slice(0, 6).join("\n\n").trim());
      }
      ifaceResult.textContent = parts.join("\n").trim() || "No data.";
    })
    .catch(e => {
      ifaceResult.textContent = "Error: " + e;
    })
    .finally(() => setRunning(ifaceRunBtn, false, "Refresh"));
}

(function initInterfacesTool() {
  const ifaceRunBtn = $("iface-run-btn");
  if (ifaceRunBtn) ifaceRunBtn.addEventListener("click", loadInterfaces);
})();
