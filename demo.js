const API_BASE_URL = (() => {
    const host = window.location.hostname;
    const isLocalHost = host === 'localhost' || host === '127.0.0.1' || host === '::1';
    const search = new URLSearchParams(window.location.search);
    const remoteDefault = window.DEFAULT_REMOTE_API_BASE_URL || 'https://autotax-xwly.onrender.com';

    function normalizeApiBaseUrl(value) {
        try {
            const parsed = new URL(String(value || ''), window.location.href);
            if (!/^https?:$/.test(parsed.protocol)) return null;
            if (!isLocalHost && (parsed.hostname === 'localhost' || parsed.hostname === '127.0.0.1' || parsed.hostname === '::1')) {
                return null;
            }
            return parsed.origin;
        } catch (error) {
            return null;
        }
    }

    function isLocalApiUrl(value) {
        try {
            const parsed = new URL(String(value || ''), window.location.href);
            return parsed.hostname === 'localhost' || parsed.hostname === '127.0.0.1' || parsed.hostname === '::1';
        } catch (error) {
            return false;
        }
    }

    const forced = normalizeApiBaseUrl(localStorage.getItem('API_BASE_URL'));
    const allowLocalApi = search.get('useLocalApi') === '1';

    if (isLocalHost) {
        if (allowLocalApi && forced) {
            return forced;
        }
        if (forced && !isLocalApiUrl(forced)) {
            return forced;
        }
        return remoteDefault;
    }
    return forced || remoteDefault;
})();

function buildAuthHeaders() {
    const headers = {};
    const token = localStorage.getItem('AUTH_TOKEN');
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    return headers;
}

async function loadDemoEmails() {
    const grid = document.querySelector('#demo-grid');
    if (!grid) return;
    try {
        const response = await fetch(`${API_BASE_URL}/api/demo-emails`, {
            cache: 'no-store',
            headers: buildAuthHeaders()
        });
        const emails = await response.json();
        grid.innerHTML = '';
        if (!emails.length) {
            grid.innerHTML = '<div class="demo-empty">No demo emails yet. Run Demo Sync first.</div>';
            return;
        }
        emails.forEach(email => {
            const card = document.createElement('div');
            card.className = 'demo-card';
            card.innerHTML = `
                <div class="demo-card-header">
                    <span class="demo-subject">${email.subject || 'Demo Receipt'}</span>
                    <span class="demo-date">${email.date || ''}</span>
                </div>
                <div class="demo-from">${email.from || ''}</div>
                <div class="demo-body">${email.body || ''}</div>
            `;
            grid.appendChild(card);
        });
    } catch (error) {
        grid.innerHTML = '<div class="demo-empty">Failed to load demo emails.</div>';
    }
}

document.addEventListener('DOMContentLoaded', loadDemoEmails);
