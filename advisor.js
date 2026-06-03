'use strict';

const API_BASE_URL = window.API_BASE_URL;
const FALLBACK_API_BASE_URL = window.DEFAULT_REMOTE_API_BASE_URL || 'https://autotax-xwly.onrender.com';

let _firebaseAuth = null;
let _firebaseReadyPromise = null;

function openLoginFallback() {
    const shouldRedirect = window.confirm('Your session may have expired. Go back to the home page to log in again?');
    if (shouldRedirect) {
        window.location.href = 'index.html';
    }
}

function setupThemeFromStorage() {
    const saved = localStorage.getItem('ra_theme');
    if (saved === 'light') document.documentElement.classList.add('light-mode');
}

function mapNetworkError(err) {
    const message = String(err && err.message ? err.message : err || '');
    if (message.includes('Failed to fetch')) {
        return 'Could not reach the server. Check your connection or API URL and try again.';
    }
    if (message.includes('401')) {
        return 'Your session expired. Please log in again.';
    }
    if (message.includes('503')) {
        return 'The AI service is temporarily unavailable. Please try again in a moment.';
    }
    return message || 'Request failed.';
}

function parseJwtPayload(token) {
    try {
        return JSON.parse(atob(String(token).split('.')[1]));
    } catch (error) {
        return null;
    }
}

function isTokenExpired(token) {
    const payload = parseJwtPayload(token);
    if (!payload || !payload.exp) return false;
    return Date.now() >= (Number(payload.exp) * 1000);
}

function hasUsableFirebaseConfig(cfg) {
    return Boolean(cfg && cfg.apiKey && cfg.authDomain && cfg.projectId && cfg.appId);
}

async function _initFirebase() {
    if (_firebaseReadyPromise) return _firebaseReadyPromise;
    _firebaseReadyPromise = (async () => {
        try {
            const res = await fetchWithApiFallback('/api/public-config', { cache: 'no-store' });
            if (!res.ok) return;
            const cfg = await res.json().catch(() => ({}));
            const fb = cfg && cfg.firebase;
            if (!hasUsableFirebaseConfig(fb) || !window.firebase) return;
            if (!window.firebase.apps.length) window.firebase.initializeApp(fb);
            _firebaseAuth = window.firebase.auth();
            await new Promise(resolve => {
                let resolved = false;
                _firebaseAuth.onIdTokenChanged(async user => {
                    if (user) {
                        try {
                            const token = await user.getIdToken();
                            localStorage.setItem('AUTH_TOKEN', token);
                        } catch (e) {}
                    }
                    if (!resolved) {
                        resolved = true;
                        resolve();
                    }
                });
            });
        } catch (e) {}
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
        } catch (e) {}
    }
    const token = localStorage.getItem('AUTH_TOKEN') || '';
    return isTokenExpired(token) ? '' : token;
}

async function apiFetch(path, opts = {}) {
    const token = await getToken();
    const res = await fetchWithApiFallback(path, {
        ...opts,
        headers: { ...(opts.headers || {}), 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        if (res.status === 401) {
            localStorage.removeItem('AUTH_TOKEN');
        }
        throw new Error(body.detail || `API ${res.status}`);
    }
    return res.json();
}

async function fetchWithApiFallback(path, opts = {}) {
    const candidates = [API_BASE_URL];
    if (FALLBACK_API_BASE_URL && FALLBACK_API_BASE_URL !== API_BASE_URL) {
        candidates.push(FALLBACK_API_BASE_URL);
    }

    let lastError = null;
    for (const baseUrl of candidates) {
        try {
            const response = await fetch(baseUrl + path, opts);
            if (baseUrl !== API_BASE_URL && response.ok) {
                try { localStorage.setItem('API_BASE_URL', baseUrl); } catch (error) {}
            }
            return response;
        } catch (error) {
            lastError = error;
        }
    }
    throw lastError || new Error('Failed to fetch');
}

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
    setupThemeFromStorage();
}

// ── Markdown-lite renderer ────────────────────────────────────────────────────
function renderMarkdown(text) {
    return text
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        .replace(/^#{1,3} (.+)$/gm, '<strong>$1</strong>')
        .replace(/^[-•] (.+)$/gm, '<li>$1</li>')
        .replace(/(<li>.*<\/li>(\n|$))+/g, m => '<ul>' + m + '</ul>')
        .replace(/\n\n/g, '</p><p>')
        .replace(/\n/g, '<br>')
        .replace(/^(.+)$/, '<p>$1</p>');
}

// ── Chat state ────────────────────────────────────────────────────────────────
let chatHistory = [];
let isThinking = false;

function appendMessage(role, content, isThinkingEl = false) {
    const chatWindow = document.querySelector('#chat-window');
    const prompts = document.querySelector('#chat-prompts');
    if (prompts && !prompts.hidden) prompts.hidden = true;

    const wrap = document.createElement('div');
    wrap.className = `chat-message chat-message-${role === 'user' ? 'user' : 'ai'}`;

    const avatar = document.createElement('div');
    avatar.className = `chat-avatar chat-avatar-${role === 'user' ? 'user' : 'ai'}`;
    avatar.textContent = role === 'user' ? 'You' : 'RA';

    const bubble = document.createElement('div');
    bubble.className = `chat-bubble chat-bubble-${role === 'user' ? 'user' : 'ai'}`;

    if (isThinkingEl) {
        bubble.innerHTML = '<div class="chat-thinking"><span></span><span></span><span></span></div>';
        wrap.dataset.thinking = 'true';
    } else {
        bubble.innerHTML = role === 'user'
            ? content.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>')
            : renderMarkdown(content);
    }

    wrap.appendChild(avatar);
    wrap.appendChild(bubble);
    chatWindow.appendChild(wrap);
    chatWindow.scrollTop = chatWindow.scrollHeight;
    return wrap;
}

function removeThinking() {
    document.querySelector('[data-thinking="true"]')?.remove();
}

// ── Send message ──────────────────────────────────────────────────────────────
async function sendMessage(text) {
    text = text.trim();
    if (!text || isThinking) return;
    isThinking = true;

    const sendBtn = document.querySelector('#chat-send');
    const inputEl = document.querySelector('#chat-input');
    if (sendBtn) sendBtn.disabled = true;
    if (inputEl) { inputEl.value = ''; inputEl.style.height = '44px'; }

    appendMessage('user', text);
    chatHistory.push({ role: 'user', content: text });

    const thinkingEl = appendMessage('assistant', '', true);

    try {
        const data = await apiFetch('/api/advisor/chat', {
            method: 'POST',
            body: JSON.stringify({ message: text, history: chatHistory.slice(-16) }),
        });

        removeThinking();
        const response = data.response || 'Sorry, I could not generate a response.';
        appendMessage('assistant', response);
        chatHistory.push({ role: 'assistant', content: response });
    } catch(err) {
        removeThinking();
        const errMsg = `Something went wrong: ${mapNetworkError(err)}`;
        appendMessage('assistant', errMsg);
        if (String(err.message || '').includes('401')) {
            openLoginFallback();
        }
    } finally {
        isThinking = false;
        if (sendBtn) sendBtn.disabled = false;
        if (inputEl) inputEl.focus();
    }
}

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    setupNav();

    // User label if signed in
    try {
        const token = await getToken();
        if (token) {
            const payload = parseJwtPayload(token);
            const label = document.querySelector('#nav-user-label');
            if (label && payload && payload.email) label.textContent = payload.email;
        }
    } catch(e) {}

    // Send button
    const sendBtn = document.querySelector('#chat-send');
    const inputEl = document.querySelector('#chat-input');

    sendBtn?.addEventListener('click', () => sendMessage(inputEl?.value || ''));

    inputEl?.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage(inputEl.value);
        }
    });

    // Auto-resize textarea
    inputEl?.addEventListener('input', () => {
        inputEl.style.height = '44px';
        inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + 'px';
    });

    // Suggested prompts
    document.querySelectorAll('.chat-prompt-btn').forEach(btn => {
        btn.addEventListener('click', () => sendMessage(btn.textContent));
    });
});
