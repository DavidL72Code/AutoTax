'use strict';

const API_BASE_URL = (() => {
    if (location.hostname === 'localhost' || location.hostname === '127.0.0.1') return 'http://localhost:8000';
    const forced = localStorage.getItem('API_BASE_URL');
    return forced || 'https://autotax-xwly.onrender.com';
})();

function getToken() { return localStorage.getItem('AUTH_TOKEN') || ''; }

async function apiFetch(path, opts = {}) {
    const token = getToken();
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
    const saved = localStorage.getItem('ra_theme');
    if (saved === 'light') document.documentElement.classList.add('light-mode');
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
        const errMsg = err.message.includes('503')
            ? 'The AI service is temporarily unavailable. Please try again in a moment.'
            : `Something went wrong: ${err.message}`;
        appendMessage('assistant', errMsg);
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
        const token = getToken();
        if (token) {
            const payload = JSON.parse(atob(token.split('.')[1]));
            const label = document.querySelector('#nav-user-label');
            if (label && payload.email) label.textContent = payload.email;
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
