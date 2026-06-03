// Shared runtime configuration for all pages.
// Single source of truth for the API base URL — do not hardcode it elsewhere.
window.DEFAULT_REMOTE_API_BASE_URL = 'https://autotax-xwly.onrender.com';

window.API_BASE_URL = (() => {
    const host = window.location.hostname;
    const isLocalHost = host === 'localhost' || host === '127.0.0.1' || host === '::1';
    const search = new URLSearchParams(window.location.search);

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
        return window.DEFAULT_REMOTE_API_BASE_URL;
    }
    return forced || window.DEFAULT_REMOTE_API_BASE_URL;
})();
