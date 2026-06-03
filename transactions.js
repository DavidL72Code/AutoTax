'use strict';

// ── Shared setup ─────────────────────────────────────────────────────────────
const API_BASE_URL = window.API_BASE_URL;

let _firebaseAuth = null;
let _firebaseReadyPromise = null;

function _initFirebase() {
    if (_firebaseReadyPromise) return _firebaseReadyPromise;
    _firebaseReadyPromise = (async () => {
        try {
            const res = await fetch(API_BASE_URL + '/api/config');
            const cfg = await res.json();
            const fb = cfg && cfg.firebase;
            if (!fb || !fb.apiKey || !window.firebase) return;
            if (!window.firebase.apps.length) window.firebase.initializeApp(fb);
            _firebaseAuth = window.firebase.auth();
            await new Promise(resolve => {
                let resolved = false;
                _firebaseAuth.onIdTokenChanged(async user => {
                    if (user) {
                        try {
                            const token = await user.getIdToken();
                            localStorage.setItem('AUTH_TOKEN', token);
                        } catch(e) {}
                    }
                    // Never remove the token — the backend JWT is still valid even if Firebase has no session
                    if (!resolved) { resolved = true; resolve(); }
                });
            });
        } catch(e) {}
    })();
    return _firebaseReadyPromise;
}

async function getToken() {
    await _initFirebase();
    if (_firebaseAuth && _firebaseAuth.currentUser) {
        try {
            const token = await _firebaseAuth.currentUser.getIdToken();
            localStorage.setItem('AUTH_TOKEN', token);
            return token;
        } catch(e) {}
    }
    return localStorage.getItem('AUTH_TOKEN') || '';
}

async function apiFetch(path, opts = {}) {
    const token = await getToken();
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

function getCategoryForVendor(vendor) {
    const v = (vendor || '').toLowerCase();
    if (v.includes('amazon')) return 'Shopping';
    if (v.includes('uber') && (v.includes('eat') || v.includes('eats'))) return 'Food Delivery';
    if (v.includes('doordash') || v.includes('grubhub') || v.includes('postmates') || v.includes('door dash')) return 'Food Delivery';
    if (v.includes('uber') || v.includes('lyft')) return 'Transport';
    if (v.includes('starbucks') || v.includes('coffee') || v.includes('dunkin')) return 'Coffee';
    if (v.includes('netflix') || v.includes('spotify') || v.includes('hulu') || v.includes('disney') || v.includes('apple music') || v.includes('youtube premium')) return 'Subscriptions';
    if (v.includes('walmart') || v.includes('target') || v.includes('costco')) return 'Shopping';
    if (v.includes('best buy') || v.includes('bestbuy')) return 'Electronics';
    if (v.includes('paypal') || v.includes('venmo') || v.includes('stripe')) return 'Finance';
    if (v.includes('whole foods') || v.includes('trader joe') || v.includes('kroger') || v.includes('safeway') || v.includes('grocery')) return 'Groceries';
    if (v.includes('shell') || v.includes('chevron') || v.includes('bp ') || v.includes('exxon') || v.includes(' gas')) return 'Gas';
    if (v.includes('cvs') || v.includes('walgreens') || v.includes('pharmacy')) return 'Health';
    if (v.includes('hotel') || v.includes('airbnb') || v.includes('marriott') || v.includes('hilton')) return 'Travel';
    if (v.includes('delta') || v.includes('united air') || v.includes('southwest') || v.includes('american airlines')) return 'Travel';
    return 'Other';
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
function parseIsoDateParts(dateStr) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(dateStr || ''));
    if (!match) return null;
    return { year: Number(match[1]), month: Number(match[2]), day: Number(match[3]) };
}

function isoDateToUtcDate(isoDate) {
    const parts = parseIsoDateParts(isoDate);
    if (!parts) return null;
    return new Date(Date.UTC(parts.year, parts.month - 1, parts.day, 12, 0, 0));
}

function dateToIsoUtc(date) {
    return date instanceof Date && !Number.isNaN(date.getTime()) ? date.toISOString().slice(0, 10) : '';
}

function getTodayIsoDate() {
    return new Intl.DateTimeFormat('en-CA', {
        timeZone: 'America/New_York',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
    }).format(new Date());
}

function addDaysIso(isoDate, days) {
    const date = isoDateToUtcDate(isoDate);
    if (!date) return '';
    date.setUTCDate(date.getUTCDate() + days);
    return dateToIsoUtc(date);
}

function diffDaysInclusive(startIso, endIso) {
    const start = isoDateToUtcDate(startIso);
    const end = isoDateToUtcDate(endIso);
    if (!start || !end) return 0;
    return Math.round((end.getTime() - start.getTime()) / 86400000) + 1;
}

function startOfWeekUtc(date) {
    const copy = new Date(date.getTime());
    const day = copy.getUTCDay();
    const diff = day === 0 ? -6 : 1 - day;
    copy.setUTCDate(copy.getUTCDate() + diff);
    return copy;
}

function formatDateRangeLabel(startIso, endIso, mode) {
    const startDate = isoDateToUtcDate(startIso);
    const endDate = isoDateToUtcDate(endIso);
    if (!startDate || !endDate) return 'Selected period';

    if (mode === 'month') {
        return new Intl.DateTimeFormat('en-US', { month: 'long', year: 'numeric', timeZone: 'America/New_York' }).format(startDate);
    }
    if (mode === 'year') {
        return String(startDate.getUTCFullYear());
    }

    const startLabel = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', timeZone: 'America/New_York' }).format(startDate);
    const endLabel = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'America/New_York' }).format(endDate);
    return `${startLabel} - ${endLabel}`;
}

function getPeriodRange(mode, startIso, endIso) {
    const fallbackIso = getTodayIsoDate();
    const safeStartIso = startIso || fallbackIso;
    const safeEndIso = endIso || safeStartIso;
    const startDate = isoDateToUtcDate(safeStartIso) || isoDateToUtcDate(fallbackIso);
    const endDate = isoDateToUtcDate(safeEndIso) || startDate;

    if (mode === 'custom') {
        const normalizedStart = startDate <= endDate ? startDate : endDate;
        const normalizedEnd = startDate <= endDate ? endDate : startDate;
        const normalizedStartIso = dateToIsoUtc(normalizedStart);
        const normalizedEndIso = dateToIsoUtc(normalizedEnd);
        const spanDays = diffDaysInclusive(normalizedStartIso, normalizedEndIso);
        return {
            mode,
            startIso: normalizedStartIso,
            endIso: normalizedEndIso,
            previousStartIso: addDaysIso(normalizedStartIso, -spanDays),
            previousEndIso: addDaysIso(normalizedStartIso, -1),
            label: formatDateRangeLabel(normalizedStartIso, normalizedEndIso),
            comparisonLabel: `previous ${spanDays}-day period`
        };
    }

    let rangeStart = new Date(startDate.getTime());
    let rangeEnd = new Date(startDate.getTime());

    if (mode === 'week') {
        rangeStart = startOfWeekUtc(startDate);
        rangeEnd = new Date(rangeStart.getTime());
        rangeEnd.setUTCDate(rangeEnd.getUTCDate() + 6);
    } else if (mode === 'year') {
        rangeStart = new Date(Date.UTC(startDate.getUTCFullYear(), 0, 1, 12, 0, 0));
        rangeEnd = new Date(Date.UTC(startDate.getUTCFullYear(), 11, 31, 12, 0, 0));
    } else {
        rangeStart = new Date(Date.UTC(startDate.getUTCFullYear(), startDate.getUTCMonth(), 1, 12, 0, 0));
        rangeEnd = new Date(Date.UTC(startDate.getUTCFullYear(), startDate.getUTCMonth() + 1, 0, 12, 0, 0));
        mode = 'month';
    }

    const rangeStartIso = dateToIsoUtc(rangeStart);
    const rangeEndIso = dateToIsoUtc(rangeEnd);
    const spanDays = diffDaysInclusive(rangeStartIso, rangeEndIso);

    return {
        mode,
        startIso: rangeStartIso,
        endIso: rangeEndIso,
        previousStartIso: addDaysIso(rangeStartIso, -spanDays),
        previousEndIso: addDaysIso(rangeStartIso, -1),
        label: formatDateRangeLabel(rangeStartIso, rangeEndIso, mode),
        comparisonLabel: mode === 'week' ? 'previous week' : mode === 'year' ? 'previous year' : 'previous month'
    };
}

function filterTransactionsByRange(txs, startIso, endIso) {
    const start = isoDateToUtcDate(startIso);
    const end = isoDateToUtcDate(endIso);
    if (!start || !end) return [];
    return txs.filter(tx => {
        const date = new Date(tx.date);
        return !Number.isNaN(date.getTime()) && date >= start && date <= end;
    });
}

function getChartBuckets(range) {
    if (range.mode === 'week') {
        return {
            labels: ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'],
            intervalFn: d => (d.getUTCDay() + 6) % 7
        };
    }
    if (range.mode === 'year') {
        return {
            labels: ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],
            intervalFn: d => d.getUTCMonth()
        };
    }

    if (range.mode === 'custom') {
        const span = diffDaysInclusive(range.startIso, range.endIso);
        if (span <= 14) {
            const labels = [];
            for (let i = 0; i < span; i++) {
                const iso = addDaysIso(range.startIso, i);
                const date = isoDateToUtcDate(iso);
                labels.push(new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', timeZone: 'America/New_York' }).format(date));
            }
            return {
                labels,
                intervalFn: d => Math.max(0, Math.round((Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), 12, 0, 0) - isoDateToUtcDate(range.startIso).getTime()) / 86400000))
            };
        }

        const weeks = Math.ceil(span / 7);
        return {
            labels: Array.from({ length: weeks }, (_, i) => `Wk ${i + 1}`),
            intervalFn: d => Math.min(weeks - 1, Math.floor(Math.max(0, Math.round((Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), 12, 0, 0) - isoDateToUtcDate(range.startIso).getTime()) / 86400000)) / 7))
        };
    }

    const startDate = isoDateToUtcDate(range.startIso);
    const endDate = isoDateToUtcDate(range.endIso);
    const daysInMonth = endDate && startDate ? endDate.getUTCDate() : 31;
    const weeks = Math.ceil(daysInMonth / 7);
    return {
        labels: Array.from({ length: weeks }, (_, i) => `Wk ${i + 1}`),
        intervalFn: d => Math.min(weeks - 1, Math.floor((d.getUTCDate() - 1) / 7))
    };
}

function computePeriod(txs, range, labels, fn) {
    const filtered = filterTransactionsByRange(txs, range.startIso, range.endIso);
    const buckets = new Array(labels.length).fill(0);
    let total = 0;
    filtered.forEach(tx => {
        const date = new Date(tx.date);
        const amt = parseFloat(tx.amount) || 0;
        const idx = fn(date);
        if (idx >= 0 && idx < buckets.length) buckets[idx] += amt;
        total += amt;
    });
    return { filtered, buckets, total, count: filtered.length };
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
function updateStats(range, cur, prev) {
    const currentLabel = range.label;
    const previousLabel = range.comparisonLabel === 'previous week'
        ? 'Previous week'
        : range.comparisonLabel === 'previous year'
            ? 'Previous year'
            : range.comparisonLabel === 'previous month'
                ? 'Previous month'
                : 'Previous period';
    document.querySelector('#spend-current-label').textContent = currentLabel;
    document.querySelector('#spend-prev-label').textContent = previousLabel;
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
        descEl.textContent = 'vs ' + range.comparisonLabel;
    }
}

// ── Top vendors ───────────────────────────────────────────────────────────────
function updateVendors(range, txs) {
    const list = document.querySelector('#spend-vendors-list');
    const title = document.querySelector('#spend-vendors-title');
    if (title) title.textContent = `Top vendors for ${range.label}`;

    const map = {};
    txs.forEach(tx => {
        const v = tx.vendor || 'Unknown';
        if (!map[v]) map[v] = { total: 0, count: 0 };
        map[v].total += parseFloat(tx.amount) || 0;
        map[v].count++;
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
        const key = groupBy === 'category' ? (tx.category || getCategoryForVendor(tx.vendor)) : (tx.vendor || 'Unknown');
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
let currentPeriodMode = 'month';
let currentStartIso = '';
let currentEndIso = '';
let currentPeriodTransactions = [];

function updatePeriodControls() {
    document.querySelectorAll('[data-period-mode]').forEach(btn => {
        const isActive = btn.dataset.periodMode === currentPeriodMode;
        btn.classList.toggle('date-filter-active', isActive);
        btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    });
    const endInput = document.querySelector('#period-end-date');
    if (endInput) endInput.disabled = currentPeriodMode !== 'custom';
    const summary = document.querySelector('#period-summary');
    if (summary) {
        const range = getPeriodRange(currentPeriodMode, currentStartIso, currentEndIso);
        summary.textContent = `Showing ${range.label} compared with the ${range.comparisonLabel}.`;
    }
}

function renderPeriod(mode = currentPeriodMode, startIso = currentStartIso, endIso = currentEndIso) {
    currentPeriodMode = mode;
    const range = getPeriodRange(mode, startIso, endIso);
    currentStartIso = range.startIso;
    currentEndIso = range.endIso;

    const startInput = document.querySelector('#period-start-date');
    const endInput = document.querySelector('#period-end-date');
    if (startInput) startInput.value = currentStartIso;
    if (endInput) endInput.value = currentEndIso;
    updatePeriodControls();

    const currentBuckets = getChartBuckets(range);
    const previousRange = {
        ...range,
        startIso: range.previousStartIso,
        endIso: range.previousEndIso
    };
    const previousBuckets = getChartBuckets(previousRange);
    const cur = computePeriod(allTx, range, currentBuckets.labels, currentBuckets.intervalFn);
    const prev = computePeriod(allTx, previousRange, previousBuckets.labels, previousBuckets.intervalFn);
    currentPeriodTransactions = cur.filtered;

    updateStats(range, cur, prev);
    drawBarChart(currentBuckets.labels, cur.buckets, prev.buckets);
    updateVendors(range, currentPeriodTransactions);
    buildPieChart(currentPeriodTransactions, document.querySelector('#csv-group')?.value || 'vendor');
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

    // Period controls
    document.querySelectorAll('[data-period-mode]').forEach(btn =>
        btn.addEventListener('click', () => renderPeriod(btn.dataset.periodMode, currentStartIso, currentEndIso))
    );
    const periodStartInput = document.querySelector('#period-start-date');
    const periodEndInput = document.querySelector('#period-end-date');
    const periodCurrentBtn = document.querySelector('#period-current-btn');
    if (periodStartInput) {
        periodStartInput.addEventListener('change', () => {
            const seed = periodStartInput.value || getTodayIsoDate();
            const endSeed = currentPeriodMode === 'custom' ? (periodEndInput?.value || seed) : seed;
            renderPeriod(currentPeriodMode, seed, endSeed);
        });
    }
    if (periodEndInput) {
        periodEndInput.addEventListener('change', () => {
            const seedStart = periodStartInput?.value || currentStartIso || getTodayIsoDate();
            const seedEnd = periodEndInput.value || seedStart;
            renderPeriod(currentPeriodMode, seedStart, seedEnd);
        });
    }
    if (periodCurrentBtn) {
        periodCurrentBtn.addEventListener('click', () => {
            const today = getTodayIsoDate();
            renderPeriod(currentPeriodMode, today, today);
        });
    }

    // Pie chart build
    const buildBtn = document.querySelector('#csv-build');
    if (buildBtn) buildBtn.addEventListener('click', () => {
        const g = document.querySelector('#csv-group')?.value || 'vendor';
        buildPieChart(currentPeriodTransactions, g);
    });

    // Load transactions
    const loadingEl = document.querySelector('#tx-loading');
    const contentEl = document.querySelector('#tx-content');
    const emptyEl = document.querySelector('#tx-empty');

    try {
        const data = await apiFetch('/api/transactions');
        allTx = (Array.isArray(data) ? data : (data.transactions || [])).filter(t => parseFloat(t.amount) > 0);
    } catch(err) {
        console.error('Failed to load transactions:', err);
    }

    if (loadingEl) loadingEl.hidden = true;

    if (allTx.length === 0) {
        if (emptyEl) emptyEl.hidden = false;
        return;
    }

    if (contentEl) contentEl.hidden = false;
    const today = getTodayIsoDate();
    renderPeriod('month', today, today);
});
