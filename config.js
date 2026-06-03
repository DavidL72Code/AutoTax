// Shared runtime configuration for all pages.
// Single source of truth for the API base URL — do not hardcode it elsewhere.
window.DEFAULT_REMOTE_API_BASE_URL = 'https://autotax-xwly.onrender.com';

window.API_BASE_URL = (() => {
    const host = window.location.hostname;
    const isLocalHost = host === 'localhost' || host === '127.0.0.1' || host === '::1';

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

    if (isLocalHost) {
        return normalizeApiBaseUrl(localStorage.getItem('API_BASE_URL')) || 'http://localhost:8000';
    }
    return normalizeApiBaseUrl(localStorage.getItem('API_BASE_URL')) || window.DEFAULT_REMOTE_API_BASE_URL;
})();
