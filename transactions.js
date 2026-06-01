'use strict';

// ── Shared setup ─────────────────────────────────────────────────────────────
const API_BASE_URL = (() => {
    if (location.hostname === 'localhost' || location.hostname === '127.0.0.1') return 'http://localhost:8000';
    const forced = localStorage.getItem('API_BASE_URL');
    return forced || location.origin;
})();

function getToken() { return localStorage.getItem('AUTH_TOKEN') || ''; }

async function apiFetch(path, opts = {}) {
    const token = getToken();
    const res = await fetch(API_BASE_URL + path, {
        ...opts,
        headers: { ...(opts.headers || {}), 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    if (!res.ok) throw new Error(`API ${res.status}`);
    return res.json();
}

function fmtCurrency(v) {
    const n = parseFloat(v) || 0;
    return '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// ── Nav dropdown ─────────────────────────────────────────────────────────────
function setupNav() {
    const hamburger = document.querySelector('#nav-hamburger');
    const menu = document.querySelector('#nav-menu');
    if (!hamburger || !menu) return;
    hamburger.addEventListener('click', () => { menu.hidden = !menu.hidden; });
    document.addEventListener('click', (e) => {
        if (!hamburger.contains(e.target) && !menu.contains(e.target)) menu.hidden = true;
    });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') menu.hidden = true; });

    // Theme
    const saved = localStorage.getItem('ra_theme');
    if (saved === 'light') document.documentElement.classList.add('light-mode');
}

// ── Auth guard ───────────────────────────────────────────────────────────────
async function requireAuth() {
    const token = getToken();
    if (!token) { location.href = 'index.html'; return false; }
    return true;
}

// ── Period helpers ────────────────────────────────────────────────────────────
function getPeriodBounds(period) {
    const now = new Date();
    let curStart, curEnd, prevStart, prevEnd, labels, intervalFn;

    if (period === 'weekly') {
        const day = now.getDay();
        const mon = new Date(now); mon.setHours(0,0,0,0);
        mon.setDate(now.getDate() - ((day + 6) % 7));
        curStart = mon; curEnd = new Date();
        prevStart = new Date(mon); prevStart.setDate(mon.getDate() - 7);
        prevEnd = new Date(mon); prevEnd.setMilliseconds(-1);
        labels = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
        intervalFn = d => ((new Date(d).getDay() + 6) % 7);
    } else if (period === 'monthly') {
        curStart = new Date(now.getFullYear(), now.getMonth(), 1);
        curEnd = new Date();
        prevStart = new Date(now.getFullYear(), now.getMonth() - 1, 1);
        prevEnd = new Date(now.getFullYear(), now.getMonth(), 0, 23, 59, 59);
        const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
        const weeks = Math.ceil(daysInMonth / 7);
        labels = Array.from({length: weeks}, (_, i) => `Wk ${i+1}`);
        intervalFn = d => Math.min(Math.floor((new Date(d).getDate() - 1) / 7), labels.length - 1);
    } else {
        curStart = new Date(now.getFullYear(), 0, 1);
        curEnd = new Date();
        prevStart = new Date(now.getFullYear() - 1, 0, 1);
        prevEnd = new Date(now.getFullYear() - 1, 11, 31, 23, 59, 59);
        labels = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
        intervalFn = d => new Date(d).getMonth();
    }
    return { curStart, curEnd, prevStart, prevEnd, labels, intervalFn };
}

function computePeriod(txs, start, end, labels, fn) {
    const buckets = new Array(labels.length).fill(0);
    let total = 0, count = 0;
    txs.forEach(tx => {
        const d = new Date(tx.date);
        if (d >= start && d <= end) {
            const amt = parseFloat(tx.amount) || 0;
            const idx = fn(d);
            if (idx >= 0 && idx < buckets.length) buckets[idx] += amt;
            total += amt; count++;
        }
    });
    return { buckets, total, count };
}

// ── Bar chart ─────────────────────────────────────────────────────────────────
function drawBarChart(labels, cur, prev) {
    const canvas = document.querySelector('#spend-bar-chart');
    const emptyEl = document.querySelector('#spend-chart-empty');
    if (!canvas) return;
    const hasData = cur.some(v => v > 0);
    if (emptyEl) emptyEl.hidden = hasData;
    canvas.style.display = hasData ? 'block' : 'none';
    if (!hasData) return;

    const dpr = window.devicePixelRatio || 1;
    const W = canvas.parentElement.clientWidth - 48 || 600;
    const H = 220;
    canvas.width = W * dpr; canvas.height = H * dpr;
    canvas.style.width = W + 'px'; canvas.style.height = H + 'px';

    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, W, H);

    const isLight = document.documentElement.classList.contains('light-mode');
    const textC = isLight ? 'rgba(0,0,0,0.4)' : 'rgba(255,255,255,0.35)';
    const gridC = isLight ? 'rgba(0,0,0,0.06)' : 'rgba(255,255,255,0.05)';
    const barC = isLight ? 'rgba(20,20,20,0.82)' : 'rgba(217,246,103,0.88)';
    const prevC = isLight ? 'rgba(0,0,0,0.1)' : 'rgba(255,255,255,0.1)';

    const padL = 54, padR = 16, padT = 16, padB = 36;
    const cW = W - padL - padR, cH = H - padT - padB;
    const maxVal = Math.max(...cur, ...prev, 1);
    const gW = cW / labels.length;
    const bW = Math.max(4, gW * 0.38);
    const pW = Math.max(3, gW * 0.28);

    for (let i = 0; i <= 4; i++) {
        const y = padT + (cH / 4) * i;
        ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y);
        ctx.strokeStyle = gridC; ctx.lineWidth = 1; ctx.stroke();
        const val = maxVal * (1 - i / 4);
        ctx.fillStyle = textC; ctx.font = '10px IBM Plex Mono, monospace';
        ctx.textAlign = 'right';
        ctx.fillText(val >= 1000 ? '$' + (val/1000).toFixed(1) + 'k' : '$' + Math.round(val), padL - 6, y + 4);
    }

    for (let i = 0; i < labels.length; i++) {
        const cx = padL + (i + 0.5) * gW;
        if (prev[i] > 0) {
            const ph = (prev[i] / maxVal) * cH;
            const px = cx - (bW + 4) / 2 - pW / 2;
            ctx.fillStyle = prevC;
            ctx.beginPath();
            if (ctx.roundRect) ctx.roundRect(px, padT + cH - ph, pW, ph, [3,3,0,0]);
            else ctx.rect(px, padT + cH - ph, pW, ph);
            ctx.fill();
        }
        if (cur[i] > 0) {
            const bh = (cur[i] / maxVal) * cH;
            ctx.fillStyle = barC;
            ctx.beginPath();
            if (ctx.roundRect) ctx.roundRect(cx - bW/2, padT + cH - bh, bW, bh, [4,4,0,0]);
            else ctx.rect(cx - bW/2, padT + cH - bh, bW, bh);
            ctx.fill();
        }
        ctx.fillStyle = textC; ctx.font = '10px IBM Plex Sans, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(labels[i], cx, H - padB + 16);
    }

    // Legend
    ctx.fillStyle = barC; ctx.fillRect(padL, H - 14, 10, 6);
    ctx.fillStyle = textC; ctx.font = '10px IBM Plex Sans,sans-serif'; ctx.textAlign = 'left';
    ctx.fillText('Current', padL + 14, H - 8);
    ctx.fillStyle = prevC; ctx.fillRect(padL + 80, H - 14, 10, 6);
    ctx.fillStyle = textC; ctx.fillText('Previous', padL + 94, H - 8);
}

// ── Stats ─────────────────────────────────────────────────────────────────────
function updateStats(period, cur, prev) {
    const labels = { weekly: ['This week','Last week'], monthly: ['This month','Last month'], annually: ['This year','Last year'] };
    document.querySelector('#spend-current-label').textContent = labels[period][0];
    document.querySelector('#spend-prev-label').textContent = labels[period][1];
    document.querySelector('#spend-current-total').textContent = fmtCurrency(cur.total);
    document.querySelector('#spend-prev-total').textContent = fmtCurrency(prev.total);
    document.querySelector('#spend-current-count').textContent = cur.count + ' transaction' + (cur.count !== 1 ? 's' : '');
    document.querySelector('#spend-prev-count').textContent = prev.count + ' transaction' + (prev.count !== 1 ? 's' : '');

    const changeEl = document.querySelector('#spend-change');
    const descEl = document.querySelector('#spend-change-desc');
    if (prev.total === 0 && cur.total === 0) {
        changeEl.textContent = '—'; changeEl.className = 'spend-stat-value';
        descEl.textContent = 'no data yet';
    } else if (prev.total === 0) {
        changeEl.textContent = 'New'; changeEl.className = 'spend-stat-value spend-stat-positive';
        descEl.textContent = 'first period with data';
    } else {
        const pct = ((cur.total - prev.total) / prev.total) * 100;
        changeEl.textContent = (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%';
        changeEl.className = 'spend-stat-value ' + (pct > 0 ? 'spend-stat-negative' : 'spend-stat-positive');
        descEl.textContent = 'vs previous ' + period.replace('ly','').replace('ually','al');
    }
}

// ── Top vendors ───────────────────────────────────────────────────────────────
function updateVendors(period, txs, bounds) {
    const list = document.querySelector('#spend-vendors-list');
    const title = document.querySelector('#spend-vendors-title');
    const periodLabel = { weekly: 'this week', monthly: 'this month', annually: 'this year' }[period];
    if (title) title.textContent = `Top vendors ${periodLabel}`;

    const map = {};
    txs.forEach(tx => {
        const d = new Date(tx.date);
        if (d >= bounds.curStart && d <= bounds.curEnd) {
            const v = tx.vendor || 'Unknown';
            if (!map[v]) map[v] = { total: 0, count: 0 };
            map[v].total += parseFloat(tx.amount) || 0;
            map[v].count++;
        }
    });
    const sorted = Object.entries(map).sort((a,b) => b[1].total - a[1].total).slice(0, 8);

    if (!sorted.length) {
        list.innerHTML = '<div style="color:var(--text-faint);font-size:0.85rem;">No transactions this period.</div>';
        return;
    }
    const maxAmt = sorted[0][1].total;
    list.innerHTML = sorted.map(([vendor, data], i) => {
        const pct = maxAmt > 0 ? (data.total / maxAmt * 100) : 0;
        return `<div class="spend-vendor-row">
            <div class="spend-vendor-rank">${i+1}</div>
            <div class="spend-vendor-bar-wrap">
                <div class="spend-vendor-name">${vendor.replace(/</g,'&lt;')}</div>
                <div class="spend-vendor-bar"><div class="spend-vendor-bar-fill" style="width:${pct.toFixed(1)}%"></div></div>
            </div>
            <div class="spend-vendor-amount">${fmtCurrency(data.total)}</div>
            <div class="spend-vendor-count">${data.count}x</div>
        </div>`;
    }).join('');
}

// ── Pie chart ─────────────────────────────────────────────────────────────────
const PIE_COLORS = ['#ef4444','#f97316','#f59e0b','#84cc16','#10b981','#14b8a6','#06b6d4','#0ea5e9','#6366f1','#8b5cf6','#d946ef','#ec4899'];

function buildPieChart(txs, groupBy) {
    const canvas = document.querySelector('#csv-chart');
    const legend = document.querySelector('#csv-legend');
    if (!canvas) return;

    const map = {};
    txs.forEach(tx => {
        const key = groupBy === 'category' ? (tx.category || 'Uncategorized') : (tx.vendor || 'Unknown');
        map[key] = (map[key] || 0) + (parseFloat(tx.amount) || 0);
    });
    const entries = Object.entries(map).sort((a,b) => b[1] - a[1]).slice(0, 12);
    const total = entries.reduce((s,[,v]) => s + v, 0);
    if (!total) return;

    const dpr = window.devicePixelRatio || 1;
    const S = 280;
    canvas.width = S * dpr; canvas.height = S * dpr;
    canvas.style.width = S + 'px'; canvas.style.height = S + 'px';
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, S, S);

    const cx = S/2, cy = S/2, r = S * 0.42;
    let angle = -Math.PI / 2;
    entries.forEach(([, val], i) => {
        const slice = (val / total) * 2 * Math.PI;
        ctx.beginPath(); ctx.moveTo(cx, cy);
        ctx.arc(cx, cy, r, angle, angle + slice);
        ctx.closePath(); ctx.fillStyle = PIE_COLORS[i % PIE_COLORS.length];
        ctx.fill();
        angle += slice;
    });

    if (legend) {
        legend.innerHTML = entries.map(([key, val], i) =>
            `<div class="csv-legend-item">
                <span class="csv-legend-dot" style="background:${PIE_COLORS[i % PIE_COLORS.length]}"></span>
                <span class="csv-legend-label">${key.replace(/</g,'&lt;')}</span>
                <span class="csv-legend-value">${fmtCurrency(val)}</span>
            </div>`
        ).join('');
    }
}

// ── Main render ───────────────────────────────────────────────────────────────
let allTx = [];
let currentPeriod = 'monthly';

function renderPeriod(period) {
    currentPeriod = period;
    const bounds = getPeriodBounds(period);
    const cur = computePeriod(allTx, bounds.curStart, bounds.curEnd, bounds.labels, bounds.intervalFn);
    const prev = computePeriod(allTx, bounds.prevStart, bounds.prevEnd, bounds.labels, bounds.intervalFn);

    updateStats(period, cur, prev);
    drawBarChart(bounds.labels, cur.buckets, prev.buckets);
    updateVendors(period, allTx, bounds);

    document.querySelectorAll('.spend-tab').forEach(btn =>
        btn.classList.toggle('spend-tab-active', btn.dataset.period === period)
    );
}

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    setupNav();

    // Show user label if signed in
    try {
        const token = getToken();
        if (token) {
            const payload = JSON.parse(atob(token.split('.')[1]));
            const label = document.querySelector('#nav-user-label');
            if (label && payload.email) label.textContent = payload.email;
        }
    } catch(e) {}

    // Logout
    const logoutBtn = document.querySelector('#nav-logout-btn');
    if (logoutBtn) {
        logoutBtn.hidden = false;
        logoutBtn.addEventListener('click', () => {
            localStorage.removeItem('AUTH_TOKEN');
            location.href = 'index.html';
        });
    }

    // Period tabs
    document.querySelectorAll('.spend-tab').forEach(btn =>
        btn.addEventListener('click', () => renderPeriod(btn.dataset.period))
    );

    // Pie chart build
    const buildBtn = document.querySelector('#csv-build');
    if (buildBtn) buildBtn.addEventListener('click', () => {
        const g = document.querySelector('#csv-group')?.value || 'vendor';
        buildPieChart(allTx, g);
    });

    // Load transactions
    const loadingEl = document.querySelector('#tx-loading');
    const contentEl = document.querySelector('#tx-content');
    const emptyEl = document.querySelector('#tx-empty');

    if (loadingEl) loadingEl.hidden = true;

    if (getToken()) {
        try {
            const data = await apiFetch('/api/transactions');
            allTx = (data.transactions || []).filter(t => parseFloat(t.amount) > 0);
        } catch(err) {
            console.error(err);
        }
    }

    if (allTx.length === 0) {
        if (emptyEl) emptyEl.hidden = false;
        return;
    }

    if (contentEl) contentEl.hidden = false;
    renderPeriod('monthly');
    buildPieChart(allTx, 'vendor');
});
