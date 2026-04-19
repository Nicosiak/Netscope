/* NetScope — traceroute path module (layout from traceroute_netscope_theme.html; always-visible shell + live hops). */
"use strict";

(function tracerouteModule(global) {
  /** Theme colors = traceroute_netscope_theme.html (same hex as mock) */
  const TR_ACC = "#00e5b4";

  /** Shown on column headers + bar tracks: both bars share length (hop RTT vs slowest reply this run). */
  const TITLE_SEGMENT_BAR =
    "Bar length = this hop’s RTT compared to the slowest replying hop on this trace. Fill color = path segment (LAN, ISP, transit, or cloud).";
  const TITLE_LATENCY_BAR =
    "Same bar length as Segment. Fill color = how fast this hop is in ms (green ≤30, amber ≤80, red above).";

  const SEG_STYLES = {
    lan: { node: "#1e6fff", pkt: "#1e6fff", asnBg: "#0d1e40", asnFg: "#1e6fff", bar: "#1e6fff" },
    isp: { node: "#39d353", pkt: "#39d353", asnBg: "#0b2010", asnFg: "#39d353", bar: "#39d353" },
    transit: { node: "#e5a000", pkt: "#e5a000", asnBg: "#201500", asnFg: "#e5a000", bar: "#e5a000" },
    cloud: { node: "#00e5b4", pkt: "#00e5b4", asnBg: "#002820", asnFg: "#00e5b4", bar: "#00e5b4" },
    null: { node: "#2e3f52", pkt: "#2e3f52", asnBg: "#121820", asnFg: "#2e3f52", bar: "#2e3f52" },
  };

  function _segStyle(seg) {
    return SEG_STYLES[seg] || SEG_STYLES.null;
  }

  function _rttColor(ms) {
    if (ms == null || Number.isNaN(Number(ms))) return "#2e3f52";
    const m = Number(ms);
    if (m <= 30) return "#39d353";
    if (m <= 80) return "#e5a000";
    return "#cc2200";
  }

  function _maxRttFromHops(hops) {
    const ms = hops.map(h => h.rtt_ms).filter(v => v != null && !Number.isNaN(Number(v)));
    return ms.length ? Math.max(...ms.map(Number)) : 1;
  }

  function _lastReplyIndex(hops) {
    for (let i = hops.length - 1; i >= 0; i--) {
      if (hops[i].rtt_ms != null && !Number.isNaN(Number(hops[i].rtt_ms))) return i;
    }
    return -1;
  }

  function _displayIp(hop) {
    if (hop.ip) return String(hop.ip);
    if (hop.rtt_ms == null) return "—";
    return String(hop.host || "—");
  }

  function _hostnameLine(hop) {
    if (hop.hostname && String(hop.hostname).trim()) return String(hop.hostname).trim();
    if (hop.rtt_ms == null) return "No response — filtered / ICMP off";
    return "";
  }

  function _barPct(rttMs, maxMs) {
    if (rttMs == null || maxMs <= 0) return 0;
    return Math.min(100, Math.max(3, (Number(rttMs) / maxMs) * 100));
  }

  function _rowDelta(hops, i) {
    const dr = hops[i].delta_row_ms;
    if (dr != null && !Number.isNaN(Number(dr))) return Number(dr);
    if (i <= 0) return null;
    const a = hops[i].rtt_ms;
    const b = hops[i - 1].rtt_ms;
    if (a != null && b != null) return Number(a) - Number(b);
    return null;
  }

  function _worstSpike(hops) {
    let worstD = 0;
    let worstTtl = null;
    for (let i = 1; i < hops.length; i++) {
      const d = _rowDelta(hops, i);
      if (d != null && d > worstD) {
        worstD = d;
        worstTtl = hops[i].ttl;
      }
    }
    return { d: worstD, ttl: worstTtl };
  }

  function _spikeLabel(seg) {
    if (seg === "lan") return "LAN";
    if (seg === "isp") return "ISP ingress";
    if (seg === "transit") return "transit";
    if (seg === "cloud") return "cloud / edge";
    return "path";
  }

  function _verdictChunks(hops, meta) {
    const n = hops.length;
    const dest = meta.dest_rtt_ms != null ? Number(meta.dest_rtt_ms) : null;
    const loss = meta.packet_loss_pct != null ? Number(meta.packet_loss_pct) : 0;
    const { d: worstD, ttl: worstTtl } = _worstSpike(hops);
    let worstSeg = "null";
    if (worstTtl != null) {
      const row = hops.find(h => h.ttl === worstTtl);
      if (row) worstSeg = String(row.segment || "null");
    }
    const hopWord = n === 1 ? "1 hop" : n + " hops";
    const clean = Number.isFinite(loss) && loss === 0 && worstD < 15;
    /** @type {{ text: string, accent: boolean }[]} */
    const chunks = [];
    if (clean) {
      chunks.push({ text: "Clean path", accent: false });
      chunks.push({ text: " — ", accent: false });
    }
    chunks.push({ text: hopWord, accent: true });
    if (dest != null && !Number.isNaN(dest)) {
      chunks.push({ text: " · ", accent: false });
      chunks.push({ text: `dest RTT ${dest.toFixed(2)} ms`, accent: true });
    }
    if (worstTtl != null && worstD > 0) {
      chunks.push({ text: " · ", accent: false });
      chunks.push({
        text: `largest spike TTL ${worstTtl} (+${worstD.toFixed(1)} ms, ${_spikeLabel(worstSeg)})`,
        accent: true,
      });
    }
    chunks.push({ text: " · ", accent: false });
    const ps = meta.probes_sent != null ? Number(meta.probes_sent) : NaN;
    const pr = meta.probes_replied != null ? Number(meta.probes_replied) : NaN;
    const lossStr = `${Number.isFinite(loss) ? loss : 0}% probe no-reply`;
    if (Number.isFinite(ps) && ps > 0 && Number.isFinite(pr)) {
      chunks.push({ text: `${lossStr} (${pr}/${ps})`, accent: true });
    } else {
      chunks.push({ text: lossStr, accent: true });
    }
    return chunks;
  }

  function _statBlock(label, val, unit, color, title) {
    const d = document.createElement("div");
    d.className = "tr-ref-stat";
    if (title) d.title = title;
    const l = document.createElement("div");
    l.className = "tr-ref-stat-lbl";
    l.textContent = label;
    const v = document.createElement("div");
    v.className = "tr-ref-stat-val";
    v.textContent = val;
    if (color) v.style.color = color;
    d.appendChild(l);
    d.appendChild(v);
    if (unit) {
      const u = document.createElement("div");
      u.className = "tr-ref-stat-unit";
      u.textContent = unit;
      d.appendChild(u);
    }
    return d;
  }

  function _metaKv(lab, val) {
    const b = document.createElement("div");
    b.className = "tr-ref-meta-item";
    const l = document.createElement("div");
    l.className = "tr-ref-label";
    l.textContent = lab;
    const v = document.createElement("div");
    v.className = "tr-ref-val";
    v.textContent = val;
    b.appendChild(l);
    b.appendChild(v);
    return b;
  }

  function _appendRouteHeader(hdr, target, meta) {
    const dot = document.createElement("div");
    dot.className = "tr-ref-dot";
    hdr.appendChild(dot);
    const titleCol = document.createElement("div");
    titleCol.className = "tr-ref-header-primary";
    const tLab = document.createElement("div");
    tLab.className = "tr-ref-label";
    tLab.textContent = "Target";
    const tVal = document.createElement("div");
    tVal.className = "tr-ref-title";
    tVal.textContent = target;
    titleCol.appendChild(tLab);
    titleCol.appendChild(tVal);
    hdr.appendChild(titleCol);
    const div0 = document.createElement("div");
    div0.className = "tr-ref-div";
    hdr.appendChild(div0);
    const dname = (meta.destination_name && String(meta.destination_name).trim()) || "";
    const res = meta.header && meta.header.resolved;
    hdr.appendChild(_metaKv("Destination", dname || (res ? String(res) : "—")));
    hdr.appendChild(_metaKv("Protocol", String(meta.method || "UDP")));
    hdr.appendChild(_metaKv("Max hops", String(meta.max_hops_limit != null ? meta.max_hops_limit : "32")));
    const badge = document.createElement("div");
    badge.className = "tr-ref-badge";
    badge.textContent = "LIVE";
    hdr.appendChild(badge);
  }

  function _appendColhead(wrap) {
    const colh = document.createElement("div");
    colh.className = "tr-ref-colhead";
    const cells = [
      { text: "#" },
      { text: "" },
      { text: "Host", padLeft: true },
      { text: "Segment", title: TITLE_SEGMENT_BAR },
      { text: "Latency", title: TITLE_LATENCY_BAR, padCol: true },
      { text: "ms", right: true },
      { text: "Δ", right: true },
    ];
    cells.forEach(c => {
      const s = document.createElement("span");
      s.textContent = c.text;
      if (c.title) s.title = c.title;
      if (c.padLeft) s.style.paddingLeft = "10px";
      if (c.padCol) s.style.paddingLeft = "4px";
      if (c.right) s.style.textAlign = "right";
      colh.appendChild(s);
    });
    wrap.appendChild(colh);
  }

  function _emptyMode(hops, raw, opts) {
    if (hops.length) return null;
    if (opts.mode) return opts.mode;
    if (opts.httpOk === false) return "error";
    if (opts.httpOk === true && raw.trim().length > 15) return "parse-fail";
    return "idle";
  }

  function _placeholderText(mode, raw) {
    if (mode === "running") return "Tracing route — UDP probes are in flight.";
    if (mode === "error") return raw.trim() ? raw.trim().slice(0, 400) : "Request failed.";
    if (mode === "parse-fail") {
      return "Traceroute produced text but no hop rows were parsed. Expand “Raw traceroute output” below.";
    }
    return "Path map uses the same grid as traceroute_netscope_theme.html — press Run to fill hops.";
  }

  function _emptyVerdictLine(mode) {
    if (mode === "running") return "Waiting for traceroute lines from the system binary…";
    if (mode === "error") return "Fix the host or permissions and try again.";
    if (mode === "parse-fail") return "If this persists, paste raw output into an issue — macOS traceroute format may have changed.";
    return "Destination PTR and IPv4 ASN enrichment run after the trace completes.";
  }

  function _renderEmptyShell(container, data, opts, mode) {
    const hostInput = (opts && opts.hostInput) || global.document.getElementById("trace-host");
    const meta = (data && data.meta) || {};
    let raw = "";
    if (data && data.raw != null) raw = String(data.raw);
    else if (data && data.error != null) raw = String(data.error);
    const target = String(meta.target || (hostInput && hostInput.value.trim()) || "—");

    container.textContent = "";
    container.style.display = "";

    const wrap = document.createElement("div");
    wrap.className = "tr-ref-path";

    const hdr = document.createElement("div");
    hdr.className = "tr-ref-header";
    _appendRouteHeader(hdr, target, meta);
    wrap.appendChild(hdr);

    const stats = document.createElement("div");
    stats.className = "tr-ref-stats";
    stats.appendChild(_statBlock("Hops", "—", "", undefined));
    stats.appendChild(_statBlock("Dest RTT", "—", "", undefined));
    stats.appendChild(_statBlock("Max RTT", "—", "", undefined));
    stats.appendChild(_statBlock("Probe no-reply", "—", "%", undefined));
    wrap.appendChild(stats);

    _appendColhead(wrap);

    const ph = document.createElement("div");
    ph.className = "tr-ref-placeholder";
    if (mode === "error" || mode === "parse-fail") ph.classList.add("tr-ref-ph-error");
    ph.textContent = _placeholderText(mode, raw);
    wrap.appendChild(ph);

    const ver = document.createElement("div");
    ver.className = "tr-ref-verdict";
    const sp = document.createElement("span");
    sp.className = "tr-ref-verdict-muted";
    sp.textContent = _emptyVerdictLine(mode);
    ver.appendChild(sp);
    wrap.appendChild(ver);

    container.appendChild(wrap);
  }

  /**
   * @param {HTMLElement} container — #trace-hops-wrap
   * @param {object} data — API payload { hops, meta, raw }
   * @param {{ hostInput?: HTMLInputElement, mode?: string, httpOk?: boolean }} [opts]
   */
  function renderTracerouteModule(container, data, opts) {
    opts = opts || {};
    const hostInput = opts.hostInput || global.document.getElementById("trace-host");
    const hops = data && Array.isArray(data.hops) ? data.hops : [];
    const meta = (data && data.meta) || {};
    let raw = "";
    if (data && data.raw != null) raw = String(data.raw);
    else if (data && data.error != null) raw = String(data.error);

    const mode = _emptyMode(hops, raw, opts);
    if (mode) {
      _renderEmptyShell(container, data, opts, mode);
      return;
    }

    container.textContent = "";
    container.style.display = "";

    const maxRtt = _maxRttFromHops(hops);
    const lastReplyIdx = _lastReplyIndex(hops);
    const target = String(meta.target || (hostInput && hostInput.value.trim()) || "—");

    const wrap = document.createElement("div");
    wrap.className = "tr-ref-path";

    const hdr = document.createElement("div");
    hdr.className = "tr-ref-header";
    _appendRouteHeader(hdr, target, meta);
    wrap.appendChild(hdr);

    const destRtt = meta.dest_rtt_ms != null ? Number(meta.dest_rtt_ms) : null;
    const maxR = meta.max_rtt_ms != null ? Number(meta.max_rtt_ms) : maxRtt;
    const loss = meta.packet_loss_pct != null ? Number(meta.packet_loss_pct) : 0;
    const ps = meta.probes_sent != null ? Number(meta.probes_sent) : NaN;
    const pr = meta.probes_replied != null ? Number(meta.probes_replied) : NaN;
    const probeLossTitle =
      Number.isFinite(ps) && ps > 0 && Number.isFinite(pr)
        ? `${pr} of ${ps} UDP TTL probes returned an RTT on this run. ${Number.isFinite(loss) ? loss : 0}% had no RTT in the output (includes routers that do not respond to traceroute). Not your app’s end-to-end packet loss.`
        : "";
    const stats = document.createElement("div");
    stats.className = "tr-ref-stats";
    stats.appendChild(_statBlock("Hops", String(hops.length), "", TR_ACC));
    stats.appendChild(
      _statBlock(
        "Dest RTT",
        destRtt != null && !Number.isNaN(destRtt) ? destRtt.toFixed(2) : "—",
        destRtt != null && !Number.isNaN(destRtt) ? "ms" : "",
        destRtt != null && !Number.isNaN(destRtt) ? _rttColor(destRtt) : undefined,
      ),
    );
    stats.appendChild(
      _statBlock(
        "Max RTT",
        maxR != null && !Number.isNaN(maxR) ? maxR.toFixed(2) : "—",
        maxR != null && !Number.isNaN(maxR) ? "ms" : "",
        maxR != null && !Number.isNaN(maxR) ? _rttColor(maxR) : undefined,
      ),
    );
    stats.appendChild(
      _statBlock(
        "Probe no-reply",
        String(Number.isFinite(loss) ? loss : 0),
        "%",
        loss <= 0 ? "#39d353" : loss <= 10 ? "#e5a000" : "#cc2200",
        probeLossTitle,
      ),
    );
    wrap.appendChild(stats);

    _appendColhead(wrap);

    const hopList = document.createElement("div");
    hopList.className = "tr-ref-hoplist";

    hops.forEach((hop, i) => {
      const seg = String(hop.segment || "null");
      const st = _segStyle(seg);
      const row = document.createElement("div");
      row.className = "tr-ref-hop";
      row.style.animationDelay = i * 0.05 + "s";

      const num = document.createElement("span");
      num.className = "tr-ref-hop-num";
      num.textContent = String(hop.ttl);

      const spine = document.createElement("div");
      spine.className = "tr-ref-spine-wrap";
      const node = document.createElement("div");
      node.className = "tr-ref-spine-node";
      node.style.background = st.node;
      const isLastRow = i === hops.length - 1;
      if (i === lastReplyIdx && hop.rtt_ms != null) node.style.boxShadow = "0 0 6px " + st.node;
      spine.appendChild(node);
      if (!isLastRow) {
        const line = document.createElement("div");
        line.className = "tr-ref-spine-line";
        for (let k = 0; k < 3; k++) {
          const pkt = document.createElement("div");
          pkt.className = "tr-ref-packet";
          pkt.style.background = st.pkt;
          line.appendChild(pkt);
        }
        spine.appendChild(line);
      }

      const hostCol = document.createElement("div");
      hostCol.className = "tr-ref-hostcol";
      const ipEl = document.createElement("div");
      ipEl.className = "tr-ref-ip" + (hop.rtt_ms == null ? " muted" : "");
      ipEl.textContent = _displayIp(hop);
      hostCol.appendChild(ipEl);
      const hn = _hostnameLine(hop);
      if (hn) {
        const hel = document.createElement("div");
        hel.className = "tr-ref-host";
        hel.textContent = hn;
        hostCol.appendChild(hel);
      }
      const asn = document.createElement("span");
      asn.className = "tr-ref-asn";
      asn.style.background = st.asnBg;
      asn.style.color = st.asnFg;
      if (String(st.asnFg).startsWith("#")) asn.style.borderColor = st.asnFg + "22";
      else asn.style.border = "1px solid var(--border)";
      if (String(st.asnFg).startsWith("#")) {
        asn.style.boxShadow = "inset 0 0 0 1px " + st.asnFg + "33";
      }
      asn.textContent = String(hop.asn || "—") + " · " + String(hop.org || "Unknown");
      hostCol.appendChild(asn);

      const pct = _barPct(hop.rtt_ms, maxRtt);
      const netBar = document.createElement("div");
      netBar.className = "tr-ref-netbar";
      const nt = document.createElement("div");
      nt.className = "tr-ref-bar-track";
      nt.title = TITLE_SEGMENT_BAR;
      const nf = document.createElement("div");
      nf.className = "tr-ref-bar-fill";
      nf.style.width = pct + "%";
      nf.style.background = st.bar;
      nf.style.animationDelay = i * 0.08 + "s";
      nt.appendChild(nf);
      netBar.appendChild(nt);

      const rttCol = document.createElement("div");
      rttCol.className = "tr-ref-rttcol";
      if (hop.rtt_ms != null) {
        const rt = document.createElement("div");
        rt.className = "tr-ref-bar-track";
        rt.title = TITLE_LATENCY_BAR;
        rt.style.marginTop = "4px";
        const rf = document.createElement("div");
        rf.className = "tr-ref-bar-fill";
        rf.style.width = pct + "%";
        rf.style.background = _rttColor(hop.rtt_ms);
        rf.style.animationDelay = i * 0.08 + 0.1 + "s";
        rt.appendChild(rf);
        rttCol.appendChild(rt);
      } else {
        const nr = document.createElement("div");
        nr.className = "tr-ref-noreply";
        nr.textContent = "no reply";
        rttCol.appendChild(nr);
      }

      const ms = document.createElement("div");
      ms.className = "tr-ref-ms";
      ms.style.color = hop.rtt_ms != null ? _rttColor(hop.rtt_ms) : "#2e3f52";
      ms.textContent = hop.rtt_ms != null ? Number(hop.rtt_ms).toFixed(1) : "—";

      const dlt = document.createElement("div");
      dlt.className = "tr-ref-delta";
      const dv = _rowDelta(hops, i);
      if (dv != null && !Number.isNaN(dv)) {
        dlt.textContent = (dv > 0 ? "+" : "") + dv.toFixed(1);
        if (dv > 6) dlt.style.color = "#e5a000";
        else if (dv < -4) dlt.style.color = "#1e6fff";
        else dlt.style.color = "#2e3f52";
      } else {
        dlt.textContent = "—";
      }

      row.appendChild(num);
      row.appendChild(spine);
      row.appendChild(hostCol);
      row.appendChild(netBar);
      row.appendChild(rttCol);
      row.appendChild(ms);
      row.appendChild(dlt);
      hopList.appendChild(row);
    });
    wrap.appendChild(hopList);

    const ver = document.createElement("div");
    ver.className = "tr-ref-verdict";
    _verdictChunks(hops, meta).forEach(({ text, accent }) => {
      const sp = document.createElement("span");
      sp.className = accent ? "tr-ref-verdict-accent" : "tr-ref-verdict-muted";
      sp.textContent = text;
      ver.appendChild(sp);
    });
    wrap.appendChild(ver);

    container.appendChild(wrap);

    global.requestAnimationFrame(() => {
      wrap.querySelectorAll(".tr-ref-bar-fill").forEach(el => {
        const w = el.style.width;
        el.style.width = "0";
        global.requestAnimationFrame(() => {
          el.style.width = w;
        });
      });
      try {
        container.scrollIntoView({ behavior: "smooth", block: "nearest" });
      } catch (_) {
        /* ignore */
      }
    });
  }

  global.renderTracerouteModule = renderTracerouteModule;
})(typeof window !== "undefined" ? window : globalThis);
