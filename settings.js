'use strict';

const API_BASE_URL = (() => {
    if (location.hostname === 'localhost' || location.hostname === '127.0.0.1') return 'http://localhost:8000';
    const forced = localStorage.getItem('API_BASE_URL');
    return forced || location.origin;
})();

function getToken() { return localStorage.getItem('AUTH_TOKEN') || ''; }

let _firebaseAuth = null;
let _firebaseReadyPromise = null;

async function _initFirebase() {
    if (_firebaseReadyPromise) return _firebaseReadyPromise;
    _firebaseReadyPromise = (async () => {
        try {
            const res = await fetch(API_BASE_URL + '/api/public-config', { cache: 'no-store' });
            if (!res.ok) return;
            const cfg = await res.json().catch(() => null);
            const fb = cfg?.firebase;
            if (!fb?.apiKey || !window.firebase) return;
            if (!window.firebase.apps.length) window.firebase.initializeApp(fb);
            _firebaseAuth = window.firebase.auth();
            await new Promise(resolve => {
                const unsub = _firebaseAuth.onAuthStateChanged(user => { unsub(); resolve(user); });
            });
        } catch(e) {}
    })();
    return _firebaseReadyPromise;
}

async function getFreshToken() {
    await _initFirebase();
    try {
        if (_firebaseAuth?.currentUser) {
            const token = await _firebaseAuth.currentUser.getIdToken(/* forceRefresh */ true);
            localStorage.setItem('AUTH_TOKEN', token);
            return token;
        }
    } catch(e) {}
    return getToken();
}

async function apiFetch(path, opts = {}) {
    const token = await getFreshToken();
    const res = await fetch(API_BASE_URL + path, {
        ...opts,
        headers: { ...(opts.headers || {}), 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `API ${res.status}`);
    }
    return res.json();
}

const BUDGET_KEY = 'MONTHLY_BUDGET_TARGET';
const PAGE_SIZE_KEY = 'TABLE_PAGE_SIZE';

// ── Nav dropdown ──────────────────────────────────────────────────────────────
function setupNav() {
    const hamburger = document.querySelector('#nav-hamburger');
    const menu = document.querySelector('#nav-menu');
    if (!hamburger || !menu) return;
    hamburger.addEventListener('click', () => { menu.hidden = !menu.hidden; });
    document.addEventListener('click', e => {
        if (!hamburger.contains(e.target) && !menu.contains(e.target)) menu.hidden = true;
    });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') menu.hidden = true; });
}

// ── Theme ─────────────────────────────────────────────────────────────────────
function applyTheme(theme) {
    document.documentElement.classList.toggle('light-mode', theme === 'light');
    document.querySelector('#theme-dark-btn')?.classList.toggle('theme-toggle-active', theme === 'dark');
    document.querySelector('#theme-light-btn')?.classList.toggle('theme-toggle-active', theme === 'light');
    try { localStorage.setItem('ra_theme', theme); } catch(e) {}
}

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    setupNav();

    // Auth guard
    if (!getToken()) { location.href = 'index.html'; return; }

    // Apply saved theme
    try {
        const saved = localStorage.getItem('ra_theme');
        applyTheme(saved === 'light' ? 'light' : 'dark');
    } catch(e) {}

    // Theme buttons
    document.querySelector('#theme-dark-btn')?.addEventListener('click', () => applyTheme('dark'));
    document.querySelector('#theme-light-btn')?.addEventListener('click', () => applyTheme('light'));

    // Language
    const langSel = document.querySelector('#lang-select');
    if (langSel) {
        try { langSel.value = localStorage.getItem('ra_lang') || 'en'; } catch(e) {}
        langSel.addEventListener('change', () => {
            try { localStorage.setItem('ra_lang', langSel.value); } catch(e) {}
            if (langSel.value !== 'en') {
                showFeedback('budget-feedback', 'Language preference saved. Full translations coming soon.', false);
            }
        });
    }

    // Page size
    const pageSizeSel = document.querySelector('#page-size-select');
    if (pageSizeSel) {
        try { pageSizeSel.value = localStorage.getItem(PAGE_SIZE_KEY) || '25'; } catch(e) {}
        pageSizeSel.addEventListener('change', () => {
            try { localStorage.setItem(PAGE_SIZE_KEY, pageSizeSel.value); } catch(e) {}
        });
    }

    // Budget
    const budgetInput = document.querySelector('#budget-input');
    const budgetFeedback = document.querySelector('#budget-feedback');
    if (budgetInput) {
        try { budgetInput.value = localStorage.getItem(BUDGET_KEY) || ''; } catch(e) {}
    }
    document.querySelector('#budget-save-btn')?.addEventListener('click', () => {
        const val = parseFloat(budgetInput?.value);
        if (!isNaN(val) && val > 0) {
            try { localStorage.setItem(BUDGET_KEY, String(Math.round(val))); } catch(e) {}
            showFeedback('budget-feedback', '✓ Budget saved', false);
        } else {
            showFeedback('budget-feedback', 'Enter a valid amount', true);
        }
    });
    document.querySelector('#budget-auto-btn')?.addEventListener('click', () => {
        try { localStorage.removeItem(BUDGET_KEY); } catch(e) {}
        if (budgetInput) budgetInput.value = '';
        showFeedback('budget-feedback', '✓ Budget set to auto', false);
    });

    // Account email
    try {
        const token = getToken();
        if (token) {
            const payload = JSON.parse(atob(token.split('.')[1]));
            const emailEl = document.querySelector('#account-email');
            if (emailEl && payload.email) emailEl.textContent = payload.email;
            const labelEl = document.querySelector('#nav-user-label');
            if (labelEl && payload.email) labelEl.textContent = payload.email;
        }
    } catch(e) {}

    // Gmail status
    try {
        const data = await apiFetch('/api/gmail-status');
        const statusEl = document.querySelector('#gmail-status-text');
        const connectBtn = document.querySelector('#gmail-connect-btn');
        if (statusEl) statusEl.textContent = data.connected ? `Connected (${data.email || 'Gmail'})` : 'Not connected';
        if (connectBtn) connectBtn.textContent = data.connected ? 'Reconnect' : 'Connect';
    } catch(e) {
        const statusEl = document.querySelector('#gmail-status-text');
        if (statusEl) statusEl.textContent = 'Unable to check status';
    }

    // Gmail connect
    document.querySelector('#gmail-connect-btn')?.addEventListener('click', async () => {
        try {
            const data = await apiFetch('/api/google/auth-url');
            if (data.auth_url) window.open(data.auth_url, '_blank');
        } catch(e) { alert('Could not get Gmail auth URL.'); }
    });

    // Sign out
    document.querySelector('#signout-btn')?.addEventListener('click', () => {
        localStorage.removeItem('AUTH_TOKEN');
        location.href = 'index.html';
    });

    // Export CSV
    document.querySelector('#export-btn')?.addEventListener('click', async () => {
        try {
            const data = await apiFetch('/api/transactions');
            const txs = data.transactions || [];
            if (!txs.length) { alert('No transactions to export.'); return; }
            const headers = ['Date','Vendor','Amount','Tax','Category','Payment Method'];
            const rows = txs.map(t => [
                t.date ? new Date(t.date).toLocaleDateString() : '',
                `"${(t.vendor||'').replace(/"/g,'""')}"`,
                t.amount || '',
                t.tax || '',
                `"${(t.category||'').replace(/"/g,'""')}"`,
                `"${(t.payment_method||'').replace(/"/g,'""')}"`,
            ].join(','));
            const csv = [headers.join(','), ...rows].join('\n');
            const blob = new Blob([csv], { type: 'text/csv' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url; a.download = 'receipts.csv';
            document.body.appendChild(a); a.click();
            document.body.removeChild(a); URL.revokeObjectURL(url);
        } catch(e) { alert('Export failed. Please try again.'); }
    });

    // Clear all
    document.querySelector('#clear-btn')?.addEventListener('click', async () => {
        if (!confirm('Delete all transactions? This cannot be undone.')) return;
        try {
            await apiFetch('/api/transactions/clear', { method: 'DELETE' });
            showFeedback('budget-feedback', '✓ All transactions cleared', false);
        } catch(e) { alert('Clear failed. Please try again.'); }
    });
});

function showFeedback(elId, msg, isError) {
    const el = document.querySelector('#' + elId);
    if (!el) return;
    el.textContent = msg;
    el.style.color = isError ? 'var(--accent-red)' : 'var(--accent-green)';
    setTimeout(() => { el.textContent = ''; }, 3000);
}
