/* NetScope — ping module (self-contained) */
"use strict";

const N = 80;
let pingSeq   = 0;     // last server seq processed; 0 = none yet (seq starts at 0 before first ping)
let localSeq  = 0;     // local log row counter
let currentRtt = null; // last RTT; frozen while paused
let serverData = null; // last live payload (not updated while paused)
let uiSynced  = false; // true after first WS tick syncs pause button
let wasPaused = false; // tracks pause state to detect transitions
let chartPadLen = N;  // current left-padding length; used by scriptable pointRadius

// ── Loss tick strip ───────────────────────────────────────────────────
const lossRow = document.getElementById('loss-row');
const ticks = Array.from({length: N}, () => {
  const d = document.createElement('div');
  d.className = 'loss-tick';
  lossRow.appendChild(d);
  return d;
});

// ── Chart (starts empty — no fake null-filled history) ────────────────
const ctx = document.getElementById('pingChart').getContext('2d');
const chart = new Chart(ctx, {
  type: 'line',
  data: {
    labels: new Array(N).fill(''),
    datasets: [{
      data: new Array(N).fill(null),
      borderWidth: 1.5,
      pointRadius: (ctx) => ctx.dataIndex < chartPadLen ? 0 : 2,
      pointBorderWidth: 0,
      fill: false,
      tension: 0.3,
      spanGaps: true,
      pointBackgroundColor: new Array(N).fill('#22c55e'),
      segment: {
        borderColor: (c) => {
          const y = c.p1?.parsed?.y;
          if (y == null || Number.isNaN(y)) return '#1a2030';
          return pingColorStrict(y);
        },
      },
    }]
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: '#111418', borderColor: '#1a2030', borderWidth: 1,
        titleColor: '#64748b', bodyColor: '#e2e8f0',
        titleFont: { family: 'JetBrains Mono', size: 10 },
        bodyFont:  { family: 'JetBrains Mono', size: 11 },
        callbacks: { label: c => c.parsed.y != null ? c.parsed.y + ' ms' : 'lost' }
      }
    },
    scales: {
      x: { display: false },
      y: {
        min: 0, suggestedMax: 100,
        grid: { color: '#1a2030', drawBorder: false },
        border: { display: false },
        ticks: { color: '#334155', font: { size: 9, family: 'JetBrains Mono' }, callback: v => v + 'ms', maxTicksLimit: 5 }
      }
    }
  },
  plugins: [{
    beforeDraw(chart) {
      const { ctx, chartArea: { left, right }, scales: { y } } = chart;
      [[30, '#22c55e'], [80, '#f59e0b']].forEach(([val, color]) => {
        const yp = y.getPixelForValue(val);
        ctx.save();
        ctx.strokeStyle = color + '44';
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 4]);
        ctx.beginPath(); ctx.moveTo(left, yp); ctx.lineTo(right, yp); ctx.stroke();
        ctx.restore();
      });
    }
  }]
});

// ── Helpers ───────────────────────────────────────────────────────────
function setMetric(id, val, color) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = val != null ? val : '--';
  el.style.color = color;
}

function render(data, paused) {
  // Use server ping_history directly — fills from empty, no fake nulls
  const raw = data && Array.isArray(data.ping_history) ? data.ping_history : [];
  const nReal  = Math.min(raw.length, N);
  const padLen = N - nReal;
  const padded = new Array(padLen).fill(null).concat(raw.slice(-N));

  chartPadLen = padLen;  // scriptable pointRadius function reads this
  chart.data.datasets[0].data = padded;
  chart.data.datasets[0].pointBackgroundColor = padded.map(pingColorStrict);
  chart.update('none');

  // Loss ticks — only colour real data slots; empty prefix stays dark
  ticks.forEach((t, i) => {
    t.style.background = (i >= padLen && padded[i] === null) ? '#ef444466' : '#1a2030';
  });

  // Chart meta
  const meta = document.getElementById('ping-chart-meta');
  if (meta) {
    if (paused) {
      meta.textContent = 'paused';
      meta.style.color = '#475569';
    } else {
      meta.textContent = nReal > 0
        ? `${nReal} sample${nReal === 1 ? '' : 's'} · ~1 Hz`
        : 'waiting…';
      meta.style.color = '';
    }
  }

  // Metrics — server is authoritative
  const isSpike = data && data.spike === true;
  setMetric('m-cur',
    currentRtt != null ? (Math.round(currentRtt * 10) / 10) : null,
    isSpike ? '#f97316' : pingColorStrict(currentRtt));

  if (data) {
    const lp = data.loss != null ? data.loss : 0;
    setMetric('m-p50',  data.p50_ms != null ? data.p50_ms.toFixed(1) : null, pingColorStrict(data.p50_ms));
    setMetric('m-avg',  data.avg_ms != null ? data.avg_ms.toFixed(1) : null, pingColorStrict(data.avg_ms));
    setMetric('m-p95',  data.p95_ms != null ? data.p95_ms.toFixed(1) : null, pingColorStrict(data.p95_ms));
    setMetric('m-loss', lp.toFixed(1), lp === 0 ? '#22c55e' : lp < 2 ? '#f59e0b' : '#ef4444');
    const jit = data.jitter_ms;
    setMetric('m-jit',
      jit != null ? jit.toFixed(1) : null,
      jit != null ? (jit > 5 ? '#f59e0b' : '#22c55e') : '#64748b');
  }
}

function addLogRow(s, target, rtt) {
  const log = document.getElementById('ping-log');
  const lost = rtt === null;
  const row = document.createElement('div');
  row.className = 'log-row';
  row.innerHTML = `
    <div class="log-dot" style="background:${lost ? '#ef4444' : '#22c55e'}"></div>
    <div class="log-seq">${s}</div>
    <div class="log-target">${target}</div>
    <div class="log-rtt" style="color:${pingColorStrict(rtt)}">${rtt !== null ? rtt.toFixed(1) + ' ms' : 'lost'}</div>
  `;
  log.insertBefore(row, log.firstChild);
  while (log.children.length > 200) log.removeChild(log.lastChild);
}

function clearLog() { document.getElementById('ping-log').innerHTML = ''; localSeq = 0; }

function resetPingUI() {
  currentRtt = null;
  pingSeq    = -1;
  localSeq   = 0;
  serverData = null;
  clearLog();
  chartPadLen = N;  // all padding — scriptable radius returns 0 for everything
  chart.data.datasets[0].data = new Array(N).fill(null);
  chart.data.datasets[0].pointBackgroundColor = new Array(N).fill('#22c55e');
  chart.update('none');
  ticks.forEach(t => { t.style.background = '#1a2030'; });
  const meta = document.getElementById('ping-chart-meta');
  if (meta) { meta.textContent = 'waiting…'; meta.style.color = ''; }
  ['m-cur', 'm-p50', 'm-avg', 'm-p95', 'm-jit'].forEach(id => setMetric(id, null, '#64748b'));
  setMetric('m-loss', '0.0', '#22c55e');
}

function syncPauseUI(paused) {
  const btn = document.getElementById('ping-stop-btn');
  const dot = document.getElementById('ping-live-dot');
  if (btn) { btn.textContent = paused ? 'Start' : 'Stop'; btn.classList.toggle('stopped', paused); }
  if (dot) dot.classList.toggle('paused', paused);
}

// ── Controls ──────────────────────────────────────────────────────────
function applyTarget() {
  const host = document.getElementById('ping-input').value.trim();
  if (!host) return;
  resetPingUI();
  syncPauseUI(false);  // target change always resumes on backend
  fetch('/api/ping/target', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ host }),
  }).catch(() => {});
}

function togglePause() {
  fetch('/api/ping/pause', { method: 'POST' })
    .then(r => r.json())
    .then(d => syncPauseUI(d.paused));
}

function clearActivePill() {
  document.querySelectorAll('.ping-module .pill').forEach(p => p.classList.remove('active'));
}

function pingGateway(btn) {
  btn.disabled = true;
  fetch('/api/network/gateway')
    .then(r => r.json())
    .then(d => {
      btn.disabled = false;
      if (d.gateway) {
        btn.title = d.gateway;
        clearActivePill();
        btn.classList.add('active');
        document.getElementById('ping-input').value = d.gateway;
        applyTarget();
      }
    })
    .catch(() => { btn.disabled = false; });
}

function quickSet(host, btn) {
  clearActivePill();
  btn.classList.add('active');
  document.getElementById('ping-input').value = host;
  applyTarget();
}

// ── WS update ─────────────────────────────────────────────────────────
function updatePingModule(data) {
  const paused = data.paused === true;

  // First tick: sync pause button to actual backend state
  if (!uiSynced) {
    uiSynced = true;
    syncPauseUI(paused);
  }

  const onTools = (window.__netscopeCurrentTab || "") === "tools";
  const isNew = !paused && data.seq != null && data.seq !== pingSeq;
  if (isNew) {
    pingSeq    = data.seq;
    currentRtt = data.ping != null ? data.ping : null;
    localSeq++;
    if (onTools) {
      const target = data.ping_target || document.getElementById('ping-input').value || '8.8.8.8';
      addLogRow(localSeq, target, currentRtt);
    }
  }

  // Keep input in sync with backend target (don't override while user is typing)
  if (data.ping_target) {
    const inp = document.getElementById('ping-input');
    if (inp && document.activeElement !== inp) inp.value = data.ping_target;
  }

  if (!paused) serverData = data;

  // Only render when something actually changed:
  // new ping sample, transitioning into pause, or resuming
  const pauseTransition = paused !== wasPaused;
  wasPaused = paused;
  if ((isNew || pauseTransition) && onTools) render(serverData, paused);
}

function sizePingChart() {
  try { chart.update('none'); } catch (e) {}
}

window.__netscopeRefreshPing = function () {
  render(serverData, wasPaused);
};

render(null, false);

document.addEventListener("ws:data", e => updatePingModule(e.detail));
