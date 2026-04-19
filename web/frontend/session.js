/* NetScope — Customer session management UI */
"use strict";

(function () {

// ── State ────────────────────────────────────────────────────────
let _active = null;          // session dict or null
let _durationTimer = null;
let _view = "none";          // "none" | "create" | "active" | "history" | "review"
let _reviewId = null;

// ── DOM refs (populated in initSession) ─────────────────────────
let pill, modal, overlay;

// ── Public API ───────────────────────────────────────────────────
window.nsSession = {
  initSession,
  onPayload,
};

// ── Boot ─────────────────────────────────────────────────────────
function initSession() {
  pill    = $("ns-session-pill");
  modal   = $("ns-session-modal");
  overlay = $("ns-session-overlay");
  if (!pill || !modal) return;

  overlay.addEventListener("click", closeModal);
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeModal(); });

  fetch("/api/sessions/active")
    .then(r => r.json())
    .then(d => {
      if (d.session) _setActive(d.session);
      else _renderPill();
    })
    .catch(() => _renderPill());
}

// ── WebSocket payload handler ────────────────────────────────────
function onPayload(d) {
  // If the server has a session but we don't know about it, re-fetch
  if (d.session_id && (!_active || _active.id !== d.session_id)) {
    fetch("/api/sessions/active")
      .then(r => r.json())
      .then(j => { if (j.session) _setActive(j.session); })
      .catch(() => {});
  }
  // If server cleared session but we think one is active
  if (!d.session_id && _active && _active.is_active) {
    _active = null;
    _renderPill();
  }
}

// ── Pill rendering ────────────────────────────────────────────────
function _renderPill() {
  if (!pill) return;
  if (_active && _active.is_active) {
    const dur = _fmtDuration(_active.started_at);
    pill.innerHTML =
      `<button class="ns-pill ns-pill--active" id="ns-pill-btn">` +
      `<span class="ns-pill-dot"></span>` +
      `<span class="ns-pill-name">${_esc(_active.customer_name)}</span>` +
      `<span class="ns-pill-dur" id="ns-pill-dur">${dur}</span>` +
      `</button>`;
    if (_durationTimer) clearInterval(_durationTimer);
    _durationTimer = setInterval(() => {
      const el = $("ns-pill-dur");
      if (el && _active) el.textContent = _fmtDuration(_active.started_at);
    }, 1000);
  } else {
    if (_durationTimer) { clearInterval(_durationTimer); _durationTimer = null; }
    pill.innerHTML =
      `<button class="ns-pill ns-pill--none" id="ns-pill-btn">NO SESSION</button>`;
  }
  const btn = $("ns-pill-btn");
  if (btn) btn.addEventListener("click", openModal);
}

function _setActive(sess) {
  _active = sess;
  _renderPill();
}

// ── Modal open / close ───────────────────────────────────────────
function openModal() {
  if (!modal) return;
  overlay.classList.remove("ns-hidden");
  modal.classList.remove("ns-hidden");
  if (_active && _active.is_active) _showActiveView();
  else _showCreateView();
}

function closeModal() {
  if (!modal) return;
  modal.classList.add("ns-hidden");
  overlay.classList.add("ns-hidden");
  _view = "none";
}

// ── Create view ──────────────────────────────────────────────────
function _showCreateView() {
  _view = "create";
  modal.innerHTML = `
    <div class="ns-modal-card">
      <div class="ns-modal-header">
        <span class="ns-modal-title">New Session</span>
        <button class="ns-modal-close" onclick="window.nsSession._closeModal()">✕</button>
      </div>
      <div class="ns-modal-body">
        <div class="ns-field">
          <label class="ns-label">Customer Name <span style="color:var(--red)">*</span></label>
          <input class="input" id="ns-name-input" type="text" placeholder="e.g. John Smith" autocomplete="off" />
        </div>
        <div class="ns-field">
          <label class="ns-label">Address / Location</label>
          <input class="input" id="ns-addr-input" type="text" placeholder="e.g. 123 Main St" autocomplete="off" />
        </div>
        <div class="ns-field">
          <label class="ns-label">Notes</label>
          <textarea class="input ns-textarea" id="ns-notes-input" placeholder="Issue description, router make/model…" rows="3"></textarea>
        </div>
        <div class="ns-modal-actions">
          <button class="btn btn-ghost" onclick="window.nsSession._closeModal()">Cancel</button>
          <button class="btn btn-primary" id="ns-start-btn">Start Session</button>
        </div>
      </div>
      <div class="ns-modal-footer">
        <button class="ns-link" id="ns-history-link">View past sessions →</button>
      </div>
    </div>`;
  const nameEl = $("ns-name-input");
  if (nameEl) nameEl.focus();
  $("ns-start-btn").addEventListener("click", _startSession);
  $("ns-name-input").addEventListener("keydown", e => { if (e.key === "Enter") _startSession(); });
  $("ns-history-link").addEventListener("click", _showHistoryView);
}

function _startSession() {
  const name = ($("ns-name-input") || {}).value.trim();
  if (!name) { ($("ns-name-input") || {}).focus(); return; }
  const addr  = ($("ns-addr-input")  || {}).value.trim();
  const notes = ($("ns-notes-input") || {}).value.trim();
  $("ns-start-btn").disabled = true;
  fetch("/api/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ customer_name: name, customer_address: addr, notes }),
  })
    .then(r => r.json())
    .then(d => {
      _setActive(d.session);
      closeModal();
    })
    .catch(() => { if ($("ns-start-btn")) $("ns-start-btn").disabled = false; });
}

// ── Active session view ──────────────────────────────────────────
function _showActiveView() {
  _view = "active";
  if (!_active) return;
  const tagsHtml = ["ISP Issue", "Hardware", "Placement", "Interference", "Resolved"]
    .map(t => {
      const on = (_active.tags || []).includes(t);
      return `<button class="ns-tag${on ? " ns-tag--on" : ""}" data-tag="${_esc(t)}">${_esc(t)}</button>`;
    }).join("");

  modal.innerHTML = `
    <div class="ns-modal-card">
      <div class="ns-modal-header">
        <div>
          <div class="ns-modal-title">${_esc(_active.customer_name)}</div>
          ${_active.customer_address ? `<div class="ns-modal-sub">${_esc(_active.customer_address)}</div>` : ""}
        </div>
        <button class="ns-modal-close" onclick="window.nsSession._closeModal()">✕</button>
      </div>
      <div class="ns-modal-body">
        <div class="ns-active-dur">
          <span class="ns-dur-lbl">Duration</span>
          <span class="ns-dur-val" id="ns-modal-dur">${_fmtDuration(_active.started_at)}</span>
        </div>
        <div class="ns-field">
          <label class="ns-label">Notes</label>
          <textarea class="input ns-textarea" id="ns-active-notes" rows="3">${_esc(_active.notes || "")}</textarea>
        </div>
        <div class="ns-field">
          <label class="ns-label">Tags</label>
          <div class="ns-tags" id="ns-tag-row">${tagsHtml}</div>
        </div>
        <div class="ns-modal-actions">
          <button class="btn ns-btn-end" id="ns-end-btn">End Session</button>
          <button class="btn btn-ghost" onclick="window.nsSession._closeModal()">Close</button>
        </div>
      </div>
      <div class="ns-modal-footer">
        <button class="ns-link" id="ns-history-link2">View past sessions →</button>
      </div>
    </div>`;

  // Duration tick
  const tick = setInterval(() => {
    const el = $("ns-modal-dur");
    if (el && _active) el.textContent = _fmtDuration(_active.started_at);
    else clearInterval(tick);
  }, 1000);

  // Notes auto-save on blur
  $("ns-active-notes").addEventListener("blur", () => {
    const notes = $("ns-active-notes").value;
    if (_active) {
      fetch(`/api/sessions/${_active.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes }),
      }).catch(() => {});
      _active.notes = notes;
    }
  });

  // Tag toggles
  $("ns-tag-row").addEventListener("click", e => {
    const btn = e.target.closest(".ns-tag");
    if (!btn || !_active) return;
    const tag = btn.dataset.tag;
    const tags = [...(_active.tags || [])];
    const idx = tags.indexOf(tag);
    if (idx >= 0) tags.splice(idx, 1); else tags.push(tag);
    _active.tags = tags;
    fetch(`/api/sessions/${_active.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tags }),
    }).catch(() => {});
    btn.classList.toggle("ns-tag--on", idx < 0);
  });

  $("ns-end-btn").addEventListener("click", _endSession);
  $("ns-history-link2").addEventListener("click", _showHistoryView);
}

function _endSession() {
  if (!_active) return;
  fetch(`/api/sessions/${_active.id}/end`, { method: "POST" })
    .then(() => {
      _active = null;
      _renderPill();
      closeModal();
    })
    .catch(() => {});
}

// ── History view ─────────────────────────────────────────────────
function _showHistoryView() {
  _view = "history";
  modal.innerHTML = `
    <div class="ns-modal-card ns-modal-card--wide">
      <div class="ns-modal-header">
        <span class="ns-modal-title">Past Sessions</span>
        <button class="ns-modal-close" onclick="window.nsSession._closeModal()">✕</button>
      </div>
      <div class="ns-modal-body ns-modal-body--scroll" id="ns-history-body">
        <div style="color:var(--text-muted);font-size:12px;padding:12px 0">Loading…</div>
      </div>
    </div>`;
  fetch("/api/sessions")
    .then(r => r.json())
    .then(d => _renderHistoryList(d.sessions || []))
    .catch(() => {
      const b = $("ns-history-body");
      if (b) b.innerHTML = `<div style="color:var(--red);font-size:12px">Failed to load sessions.</div>`;
    });
}

function _renderHistoryList(sessions) {
  const body = $("ns-history-body");
  if (!body) return;
  if (!sessions.length) {
    body.innerHTML = `<div style="color:var(--text-muted);font-size:12px;padding:12px 0">No past sessions found.</div>`;
    return;
  }
  const rows = sessions.map(s => {
    const date = new Date(s.started_at * 1000).toLocaleDateString("en-US", {month:"short", day:"numeric", year:"numeric"});
    const dur  = _fmtDurationSec(s.duration_s);
    const status = s.is_active
      ? `<span style="color:var(--green);font-size:10px">● ACTIVE</span>`
      : `<span style="color:var(--text-dim);font-size:10px">ended</span>`;
    return `<tr class="ns-hist-row" data-id="${_esc(s.id)}">
      <td>${_esc(s.customer_name || "—")}</td>
      <td>${_esc(s.customer_address || "—")}</td>
      <td>${date}</td>
      <td>${dur}</td>
      <td style="color:var(--text-muted)">${s.snapshot_count || 0}</td>
      <td>${status}</td>
    </tr>`;
  }).join("");
  body.innerHTML = `
    <table class="ns-hist-table">
      <thead>
        <tr>
          <th>Customer</th><th>Address</th><th>Date</th>
          <th>Duration</th><th>Snapshots</th><th>Status</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
  body.querySelectorAll(".ns-hist-row").forEach(row => {
    row.addEventListener("click", () => _showReviewView(row.dataset.id));
  });
}

// ── Review view ──────────────────────────────────────────────────
function _showReviewView(sessionId) {
  _view = "review";
  _reviewId = sessionId;
  modal.innerHTML = `
    <div class="ns-modal-card ns-modal-card--wide">
      <div class="ns-modal-header">
        <button class="ns-link" id="ns-back-btn">← Back</button>
        <span class="ns-modal-title" id="ns-review-title">Loading…</span>
        <button class="ns-modal-close" onclick="window.nsSession._closeModal()">✕</button>
      </div>
      <div class="ns-modal-body ns-modal-body--scroll" id="ns-review-body">
        <div style="color:var(--text-muted);font-size:12px;padding:12px 0">Loading…</div>
      </div>
    </div>`;
  $("ns-back-btn").addEventListener("click", _showHistoryView);

  Promise.all([
    fetch(`/api/sessions/${sessionId}/summary`).then(r => r.json()),
    fetch(`/api/sessions/${sessionId}/snapshots`).then(r => r.json()),
  ]).then(([summary, snapsData]) => {
    _renderReview(summary, snapsData.snapshots || []);
  }).catch(() => {
    const b = $("ns-review-body");
    if (b) b.innerHTML = `<div style="color:var(--red);font-size:12px">Failed to load session data.</div>`;
  });
}

function _renderReview(summary, snaps) {
  const title = $("ns-review-title");
  if (title) title.textContent = summary.customer_name || "Session Review";
  const body = $("ns-review-body");
  if (!body) return;

  const startDate = summary.started_at
    ? new Date(summary.started_at * 1000).toLocaleString()
    : "—";
  const endDate = summary.ended_at
    ? new Date(summary.ended_at * 1000).toLocaleString()
    : "Active";

  const spikes = summary.spike_event_count || 0;
  const statsHtml = `
    <div class="ns-review-stats">
      ${_statTile("Avg RSSI", summary.rssi && summary.rssi.avg != null ? summary.rssi.avg + " dBm" : "—", summary.rssi && summary.rssi.avg != null ? _rssiColor(summary.rssi.avg) : "")}
      ${_statTile("Max Loss", summary.loss && summary.loss.max != null ? summary.loss.max + "%" : "—", summary.loss && summary.loss.max > 5 ? "var(--red)" : summary.loss && summary.loss.max > 1 ? "var(--amber)" : "")}
      ${_statTile("Avg Ping", summary.ping && summary.ping.avg != null ? summary.ping.avg + " ms" : "—", "")}
      ${_statTile("Spikes / Alerts", `${spikes} spikes · ${summary.alerts.critical || 0}c ${summary.alerts.warning || 0}w`, spikes > 0 || (summary.alerts && summary.alerts.critical > 0) ? "var(--amber)" : "")}
    </div>`;

  const metaHtml = `
    <div class="ns-review-meta">
      ${summary.customer_address ? `<span>${_esc(summary.customer_address)}</span>` : ""}
      <span>${startDate} → ${endDate}</span>
      <span>${summary.snapshot_count} stability snapshots · ${spikes} spike events</span>
    </div>`;

  let timelineHtml = `<div style="color:var(--text-muted);font-size:12px;padding:12px 0">No snapshots recorded yet.</div>`;
  if (snaps.length) {
    const rows = snaps.map(s => {
      const isSpike = s.kind === "spike";
      const level = (s.alerts || {}).level || "ok";
      // Spike event rows get their own class; stability rows get alert-level class
      const rowClass = isSpike
        ? "ns-tl-spike"
        : level === "critical" ? "ns-tl-crit" : level === "warning" ? "ns-tl-warn" : "";

      const t = new Date(s.ts * 1000).toLocaleTimeString("en-US", {hour:"2-digit", minute:"2-digit", second:"2-digit"});
      const msgs = ((s.alerts || {}).messages || []).join("; ");

      // Use rssi_avg10 (2.5 s smoothed) as primary RSSI; fall back to signal
      const rssiVal = s.rssi_avg10 != null ? s.rssi_avg10 : s.signal;
      const rssiStr = rssiVal != null ? rssiVal + " dBm" : "—";

      const kindBadge = isSpike
        ? `<span class="ns-tl-kind-badge ns-tl-kind-spike">spike</span>`
        : `<span class="ns-tl-kind-badge">—</span>`;

      const spikeRtt = isSpike && s.spike_rtt_ms != null
        ? ` (${s.spike_rtt_ms} ms)` : "";

      const alertColor = level === "critical" ? "var(--red)" : level === "warning" ? "var(--amber)" : "var(--text-dim)";

      return `<tr class="${rowClass}">
        <td>${t}</td>
        <td>${kindBadge}</td>
        <td style="color:${_rssiColor(rssiVal)}">${rssiStr}</td>
        <td>${s.snr != null ? s.snr + " dB" : "—"}</td>
        <td>${s.phy_speed != null ? s.phy_speed + " Mbps" : "—"}</td>
        <td>${s.avg_ms != null ? s.avg_ms + " ms" : "—"}</td>
        <td>${s.p95_ms != null ? s.p95_ms + " ms" : "—"}</td>
        <td>${s.loss != null ? s.loss + "%" : "—"}</td>
        <td>${s.jitter_ms != null ? s.jitter_ms + " ms" : "—"}</td>
        <td style="font-size:10px;color:${alertColor}">${msgs ? msgs + spikeRtt : spikeRtt || "—"}</td>
      </tr>`;
    }).join("");
    timelineHtml = `
      <div class="ns-tl-scroll">
        <table class="ns-tl-table">
          <thead>
            <tr>
              <th>Time</th><th>Type</th><th>RSSI (avg)</th><th>SNR</th>
              <th>PHY Mbps</th><th>Avg Ping</th><th>P95</th>
              <th>Loss</th><th>Jitter</th><th>Notes</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  body.innerHTML = metaHtml + statsHtml + timelineHtml;
}

function _statTile(label, value, color) {
  return `<div class="ns-stat-tile">
    <div class="ns-stat-lbl">${label}</div>
    <div class="ns-stat-val" ${color ? `style="color:${color}"` : ""}>${value}</div>
  </div>`;
}

// ── Helpers ──────────────────────────────────────────────────────
function _fmtDuration(startedAt) {
  const secs = Math.floor(Date.now() / 1000 - startedAt);
  return _fmtDurationSec(secs);
}
function _fmtDurationSec(secs) {
  if (secs < 0) secs = 0;
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) return `${h}h ${String(m).padStart(2,"0")}m`;
  if (m > 0) return `${m}m ${String(s).padStart(2,"0")}s`;
  return `${s}s`;
}
function _rssiColor(v) {
  if (v == null) return "";
  if (v >= -70) return "var(--green)";
  if (v >= -80) return "var(--amber)";
  return "var(--red)";
}
function _esc(s) {
  return String(s || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

// Exposed for inline event handlers
window.nsSession._closeModal = closeModal;

document.addEventListener("ws:data", e => onPayload(e.detail));

})();
