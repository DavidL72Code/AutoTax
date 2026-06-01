// Receipt Automation Dashboard JavaScript

// API Configuration
const API_BASE_URL = (() => {
    const host = window.location.hostname;
    if (host === 'localhost' || host === '127.0.0.1' || host === '::1') {
        return 'http://localhost:8000';
    }
    const forced = localStorage.getItem('API_BASE_URL');
    if (forced) return forced;
    return 'https://autotax-xwly.onrender.com';
})();
const DEMO_MODE = Boolean(window.DEMO_MODE);
const MONTHLY_BUDGET_STORAGE_KEY = 'MONTHLY_BUDGET_TARGET';
let firebaseConfig = null;

// DOM Elements
let searchInput;
let syncBtn;
let exportBtn;
let tableBody;
let csvGroupSelect;
let csvChartCanvas;
let csvChartImg;
let csvLegend;
let csvBuildBtn;
let editModal;
let modalSaveBtn;
let modalCancelBtn;
let modalDeleteBtn;
let editVendorInput;
let editAmountInput;
let editTaxInput;
let editDateInput;
let activeTransactionId = null;
let demoGenerateBtn;
let demoParseBtn;
let demoViewBtn;
let clearBtn;
let demoRunLogEl;
let demoForceToggle;
let demoRunProcessedEl;
let demoRunSuccessEl;
let demoRunSkippedEl;
let demoRunFailedEl;
let loginBtn;
let signupBtn;
let connectGoogleBtn;
let heroTotalSpentEl;
let heroSummaryLineEl;
let expensePreviewListEl;
let expensePeriodLabelEl;
let expenseBudgetUsedEl;
let expenseBudgetCurrentEl;
let expenseBudgetTargetEl;
let expenseBudgetFillEl;
let expenseBudgetInputEl;
let expenseBudgetSaveBtn;
let expenseBudgetResetBtn;
let expenseBudgetNoteEl;
let heroVendorListEl;
let syncStatusTitleEl;
let syncStatusMetaEl;
let authModal;
let authCloseBtn;
let authTabLogin;
let authTabSignup;
let authFormLogin;
let authFormSignup;
let authLoginUsername;
let authLoginPassword;
let authSignupUsername;
let authSignupEmail;
let authSignupPassword;
let authGoogleBtn;
let authFeedbackEl;
let currentUser = null;
let firebaseAuth = null;
let firebaseReadyPromise = Promise.resolve();

// Cached transactions and sort state (so we can re-sort without re-fetching)
let allTransactions = [];
let sortColumn = 'date';
let sortDirection = 'desc'; // 'asc' = least to greatest, 'desc' = greatest to least
let syncPollTimer = null;
let demoParsePollTimer = null;
let activeDemoRunId = null;
let currentBudgetSpend = 0;
let latestTopVendors = [];
let activeDateFilter = 'all';
let activeSearchTerm = '';
let currentPage = 1;
let pageSize = (() => { try { return Number(localStorage.getItem('TABLE_PAGE_SIZE')) || 25; } catch(e) { return 25; } })();
let idlePollTimer = null;
let syncRunId = null;
let editCategoryInput = null;

document.addEventListener('DOMContentLoaded', function() {
    // Initialize DOM references
    searchInput = document.querySelector('.search-input');
    syncBtn = document.querySelector('#sync-emails');
    exportBtn = document.querySelector('#export-csv');
    tableBody = document.querySelector('.transactions-table tbody');
    csvGroupSelect = document.querySelector('#csv-group');
    csvChartCanvas = document.querySelector('#csv-chart');
    csvChartImg = document.querySelector('#csv-chart-img');
    csvLegend = document.querySelector('#csv-legend');
    csvBuildBtn = document.querySelector('#csv-build');
    editModal = document.querySelector('#edit-modal');
    modalSaveBtn = document.querySelector('#modal-save');
    modalCancelBtn = document.querySelector('#modal-cancel');
    modalDeleteBtn = document.querySelector('#modal-delete');
    editVendorInput = document.querySelector('#edit-vendor');
    editAmountInput = document.querySelector('#edit-amount');
    editTaxInput = document.querySelector('#edit-tax');
    editDateInput = document.querySelector('#edit-date');
    demoGenerateBtn = document.querySelector('.btn-demo-generate');
    demoParseBtn = document.querySelector('.btn-demo-parse');
    demoViewBtn = document.querySelector('.btn-demo-view');
    clearBtn = document.querySelector('.btn-clear');
    demoRunLogEl = document.querySelector('#demo-run-log');
    demoForceToggle = document.querySelector('#demo-force-reprocess');
    demoRunProcessedEl = document.querySelector('#demo-run-processed');
    demoRunSuccessEl = document.querySelector('#demo-run-success');
    demoRunSkippedEl = document.querySelector('#demo-run-skipped');
    demoRunFailedEl = document.querySelector('#demo-run-failed');
    loginBtn = document.querySelector('.btn-login');
    signupBtn = document.querySelector('.btn-signup');
    connectGoogleBtn = document.querySelector('.btn-connect-google');
    heroTotalSpentEl = document.querySelector('#hero-total-spent');
    heroSummaryLineEl = document.querySelector('#hero-summary-line');
    expensePreviewListEl = document.querySelector('#expense-preview-list');
    expensePeriodLabelEl = document.querySelector('#expense-period-label');
    expenseBudgetUsedEl = document.querySelector('#expense-budget-used');
    expenseBudgetCurrentEl = document.querySelector('#expense-budget-current');
    expenseBudgetTargetEl = document.querySelector('#expense-budget-target');
    expenseBudgetFillEl = document.querySelector('#expense-budget-fill');
    expenseBudgetInputEl = document.querySelector('#expense-budget-input');
    expenseBudgetSaveBtn = document.querySelector('#expense-budget-save');
    expenseBudgetResetBtn = document.querySelector('#expense-budget-reset');
    expenseBudgetNoteEl = document.querySelector('#expense-budget-note');
    heroVendorListEl = document.querySelector('#hero-vendor-list');
    syncStatusTitleEl = document.querySelector('#sync-status-title');
    syncStatusMetaEl = document.querySelector('#sync-status-meta');
    authModal = document.querySelector('#auth-modal');
    authCloseBtn = document.querySelector('#auth-close');
    authTabLogin = document.querySelector('#auth-tab-login');
    authTabSignup = document.querySelector('#auth-tab-signup');
    authFormLogin = document.querySelector('#auth-form-login');
    authFormSignup = document.querySelector('#auth-form-signup');
    authLoginUsername = document.querySelector('#auth-login-username');
    authLoginPassword = document.querySelector('#auth-login-password');
    authSignupUsername = document.querySelector('#auth-signup-username');
    authSignupEmail = document.querySelector('#auth-signup-email');
    authSignupPassword = document.querySelector('#auth-signup-password');
    authGoogleBtn = document.querySelector('#auth-google-btn');
    authFeedbackEl = document.querySelector('#auth-feedback');
    editCategoryInput = document.querySelector('#edit-category');

    // Sync page-size select with saved value
    const pageSizeSelectEl = document.querySelector('#page-size-select');
    if (pageSizeSelectEl) pageSizeSelectEl.value = String(pageSize);
    const settingsPageSizeEl = document.querySelector('#settings-page-size');
    if (settingsPageSizeEl) settingsPageSizeEl.value = String(pageSize);

    // Initialize animations
    initAnimations();
    
    // Setup event listeners
    setupEventListeners();
    refreshBudgetEditor();
    
    loadRuntimeConfig().then(() => {
        initializeFirebaseAuth();
        return bootstrapAuth();
    }).then(() => {
        if (DEMO_MODE || currentUser) {
            loadDashboardData();
            if (DEMO_MODE) {
                loadDemoEmails();
            }
        }
    }).catch((error) => {
        console.error('Runtime config bootstrap failed:', error);
        setAuthState(null);
    });
    
    // Smart idle poll: 30s, paused when tab is hidden
    startIdlePoll();
    document.addEventListener('visibilitychange', function() {
        if (document.hidden) {
            if (idlePollTimer) { clearInterval(idlePollTimer); idlePollTimer = null; }
        } else {
            if (currentUser) { loadDashboardData(); }
            startIdlePoll();
        }
    });
});

// Animations for elements on page load
function initAnimations() {
    const statCards = document.querySelectorAll('.stat-card-hero');
    statCards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        setTimeout(() => {
            card.style.transition = 'all 0.5s ease';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 100);
    });
}

// Setup all event listeners
function setupEventListeners() {
    // Search input — feeds unified pipeline, no DOM hiding
    if (searchInput) {
        searchInput.addEventListener('input', function(e) {
            activeSearchTerm = e.target.value;
            currentPage = 1;
            renderTransactionsTable();
        });
    }

    // Pagination
    const prevPageBtn = document.querySelector('#prev-page');
    const nextPageBtn = document.querySelector('#next-page');
    const pageSizeSelectEl = document.querySelector('#page-size-select');

    if (prevPageBtn) {
        prevPageBtn.addEventListener('click', function() {
            if (currentPage > 1) { currentPage--; renderTransactionsTable(); }
        });
    }
    if (nextPageBtn) {
        nextPageBtn.addEventListener('click', function() {
            const total = getProcessedTransactions().length;
            if (currentPage < Math.ceil(total / pageSize)) { currentPage++; renderTransactionsTable(); }
        });
    }
    if (pageSizeSelectEl) {
        pageSizeSelectEl.addEventListener('change', function() {
            pageSize = Number(this.value) || 25;
            currentPage = 1;
            try { localStorage.setItem('TABLE_PAGE_SIZE', String(pageSize)); } catch(e) {}
            const settingsPS = document.querySelector('#settings-page-size');
            if (settingsPS) settingsPS.value = String(pageSize);
            renderTransactionsTable();
        });
    }

    // Settings drawer
    const settingsToggle = document.querySelector('#settings-toggle');
    const settingsClose = document.querySelector('#settings-close');
    const settingsBackdrop = document.querySelector('#settings-backdrop');
    const settingsPageSize = document.querySelector('#settings-page-size');
    const settingsBudgetSave = document.querySelector('#settings-budget-save');
    const settingsBudgetAuto = document.querySelector('#settings-budget-auto');
    const settingsExportBtn = document.querySelector('#settings-export-btn');
    const settingsClearBtn = document.querySelector('#settings-clear-btn');
    const settingsSyncBtn = document.querySelector('#settings-sync-btn');

    if (settingsToggle) settingsToggle.addEventListener('click', openSettingsPanel);
    if (settingsClose) settingsClose.addEventListener('click', closeSettingsPanel);
    if (settingsBackdrop) settingsBackdrop.addEventListener('click', closeSettingsPanel);

    if (settingsPageSize) {
        settingsPageSize.addEventListener('change', function() {
            pageSize = Number(this.value) || 25;
            currentPage = 1;
            try { localStorage.setItem('TABLE_PAGE_SIZE', String(pageSize)); } catch(e) {}
            const mainPS = document.querySelector('#page-size-select');
            if (mainPS) mainPS.value = String(pageSize);
            renderTransactionsTable();
        });
    }
    if (settingsBudgetSave) {
        settingsBudgetSave.addEventListener('click', function() {
            const input = document.querySelector('#settings-budget-input');
            if (!input) return;
            const val = Number(input.value);
            if (Number.isFinite(val) && val > 0) {
                setStoredMonthlyBudget(val);
                updateBudgetSummary(currentBudgetSpend);
                if (expenseBudgetInputEl) expenseBudgetInputEl.value = String(val);
            }
        });
    }
    if (settingsBudgetAuto) settingsBudgetAuto.addEventListener('click', function() {
        clearStoredMonthlyBudget();
        updateBudgetSummary(currentBudgetSpend);
        const input = document.querySelector('#settings-budget-input');
        if (input) input.value = '';
    });
    if (settingsExportBtn) settingsExportBtn.addEventListener('click', exportToCSV);
    if (settingsClearBtn) settingsClearBtn.addEventListener('click', clearAllTransactions);
    if (settingsSyncBtn) settingsSyncBtn.addEventListener('click', syncEmails);

    // Receipt preview modal close
    const receiptModalClose = document.querySelector('#receipt-modal-close');
    if (receiptModalClose) {
        receiptModalClose.addEventListener('click', function() {
            const m = document.querySelector('#receipt-modal');
            if (m) { m.classList.remove('show'); m.style.display = 'none'; m.hidden = true; }
        });
    }

    // Sync button
    if (syncBtn) {
        syncBtn.addEventListener('click', function() {
            syncEmails();
        });
    }

    // Export CSV button
    if (exportBtn) {
        exportBtn.addEventListener('click', function() {
            exportToCSV();
        });
    }

    if (expenseBudgetSaveBtn) {
        expenseBudgetSaveBtn.addEventListener('click', function() {
            saveMonthlyBudget();
        });
    }

    if (expenseBudgetResetBtn) {
        expenseBudgetResetBtn.addEventListener('click', function() {
            resetMonthlyBudget();
        });
    }

    if (expenseBudgetInputEl) {
        expenseBudgetInputEl.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                saveMonthlyBudget();
            }
            if (e.key === 'Escape') {
                e.preventDefault();
                refreshBudgetEditor();
                expenseBudgetInputEl.blur();
            }
        });
    }


    // Sortable column headers
    document.querySelectorAll('.sortable').forEach(function(th) {
        th.addEventListener('click', function() {
            const col = th.getAttribute('data-sort');
            if (!col) return;
            if (sortColumn === col) {
                sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
            } else {
                sortColumn = col;
                sortDirection = col === 'date' ? 'desc' : 'asc';
            }
            updateSortArrows();
            renderTransactionsTable();
        });
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            if (searchInput) searchInput.focus();
        }
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
            e.preventDefault();
            syncEmails();
        }
        if (e.key === 'Escape') {
            const drawer = document.querySelector('#settings-drawer');
            if (drawer && !drawer.hidden) closeSettingsPanel();
        }
    });

    // CSV chart controls
    if (csvBuildBtn) {
        csvBuildBtn.addEventListener('click', function() {
            buildChartFromTable();
        });
    }

    if (demoGenerateBtn) {
        demoGenerateBtn.addEventListener('click', function() {
            runDemoGenerate();
        });
    }
    if (demoParseBtn) {
        demoParseBtn.addEventListener('click', function() {
            runDemoParse();
        });
    }
    if (clearBtn) {
        clearBtn.addEventListener('click', function() {
            clearAllTransactions();
        });
    }

    if (modalCancelBtn) {
        modalCancelBtn.addEventListener('click', closeEditModal);
    }
    if (modalSaveBtn) {
        modalSaveBtn.addEventListener('click', saveTransactionEdits);
    }
    if (modalDeleteBtn) {
        modalDeleteBtn.addEventListener('click', deleteTransaction);
    }

    if (loginBtn) {
        loginBtn.addEventListener('click', function() {
            openAuthModal('login');
        });
    }
    if (signupBtn) {
        signupBtn.addEventListener('click', function() {
            if (currentUser) {
                logoutUser();
            } else {
                openAuthModal('signup');
            }
        });
    }
    if (authCloseBtn) {
        authCloseBtn.addEventListener('click', closeAuthModal);
    }
    if (authTabLogin) {
        authTabLogin.addEventListener('click', function() { setAuthMode('login'); });
    }
    if (authTabSignup) {
        authTabSignup.addEventListener('click', function() { setAuthMode('signup'); });
    }
    if (authFormLogin) {
        authFormLogin.addEventListener('submit', function(e) {
            e.preventDefault();
            submitLogin();
        });
    }
    if (authFormSignup) {
        authFormSignup.addEventListener('submit', function(e) {
            e.preventDefault();
            submitSignup();
        });
    }
    if (authGoogleBtn) {
        authGoogleBtn.addEventListener('click', function() {
            submitGoogleAuth();
        });
    }
    if (authSignupPassword) {
        authSignupPassword.addEventListener('input', function() {
            updatePasswordRequirementState(authSignupPassword.value);
        });
    }

    if (connectGoogleBtn) {
        connectGoogleBtn.addEventListener('click', function() {
            connectGoogle();
        });
    }

    // Hero and onboarding connect Gmail buttons
    document.querySelectorAll('.btn-connect-google-hero, .btn-connect-google-onboard').forEach(function(btn) {
        btn.addEventListener('click', function() {
            connectGoogle();
        });
    });

    // Date filter buttons
    document.querySelectorAll('.date-filter-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            activeDateFilter = btn.getAttribute('data-filter') || 'all';
            document.querySelectorAll('.date-filter-btn').forEach(b => b.classList.remove('date-filter-active'));
            btn.classList.add('date-filter-active');
            renderTransactionsTable();
        });
    });

    // Duplicate warning dismiss
    const duplicateDismissBtn = document.querySelector('#duplicate-dismiss');
    if (duplicateDismissBtn) {
        duplicateDismissBtn.addEventListener('click', function() {
            const warning = document.querySelector('#duplicate-warning');
            if (warning) warning.hidden = true;
        });
    }

    // Auto-render pie chart when the insights section scrolls into view
    const csvSection = document.querySelector('#csv-insights');
    if (csvSection && typeof IntersectionObserver !== 'undefined') {
        let chartBuilt = false;
        const chartObserver = new IntersectionObserver(function(entries) {
            entries.forEach(function(entry) {
                if (entry.isIntersecting && !chartBuilt && allTransactions.length) {
                    chartBuilt = true;
                    buildChartFromTable();
                }
            });
        }, { threshold: 0.2 });
        chartObserver.observe(csvSection);
    }
}

async function loadRuntimeConfig() {
    if (firebaseConfig) {
        return firebaseConfig;
    }
    try {
        const response = await fetch(`${API_BASE_URL}/api/public-config`, { cache: 'no-store' });
        if (!response.ok) {
            throw new Error(`Config request failed with ${response.status}`);
        }
        const payload = await response.json().catch(() => ({}));
        firebaseConfig = payload && payload.firebase ? payload.firebase : null;
    } catch (error) {
        console.warn('Could not load runtime config from API:', error);
        firebaseConfig = null;
    }
    return firebaseConfig;
}

async function connectGoogle() {
    if (!await hasActiveAuthSession()) {
        handleAuthRequired();
        return;
    }
    try {
        const response = await authFetch(`${API_BASE_URL}/api/google/auth-url`, { cache: 'no-store' });
        const result = await response.json().catch(() => ({}));
        if (!response.ok || !result.auth_url) {
            throw new Error(result.detail || 'Failed to start Google OAuth');
        }
        window.location.href = result.auth_url;
    } catch (error) {
        showError(error.message || 'Could not start Google OAuth.');
    }
}

function openAuthModal(mode) {
    if (!authModal) return;
    clearAuthFeedback();
    setAuthMode(mode || 'login');
    authModal.classList.add('show');
    authModal.hidden = false;
    authModal.style.display = 'flex';
    const firstField = mode === 'signup' ? authSignupUsername : authLoginUsername;
    if (firstField) {
        setTimeout(function() {
            firstField.focus();
        }, 0);
    }
}

function closeAuthModal() {
    if (!authModal) return;
    clearAuthFeedback();
    authModal.classList.remove('show');
    authModal.hidden = true;
    authModal.style.display = 'none';
}

function setAuthMode(mode) {
    const isLogin = mode === 'login';
    clearAuthFeedback();
    if (authTabLogin) authTabLogin.classList.toggle('auth-tab-active', isLogin);
    if (authTabSignup) authTabSignup.classList.toggle('auth-tab-active', !isLogin);
    if (authFormLogin) authFormLogin.hidden = !isLogin;
    if (authFormSignup) authFormSignup.hidden = isLogin;
    const title = isLogin ? 'Login' : 'Sign up';
    const titleEl = document.querySelector('#auth-modal-title');
    if (titleEl) titleEl.textContent = title;
    if (!isLogin) {
        updatePasswordRequirementState(authSignupPassword ? authSignupPassword.value : '');
    }
}

function setAuthFeedback(message, variant = 'error') {
    if (!authFeedbackEl) {
        if (variant === 'error') {
            showError(message);
        } else {
            showSuccess(message);
        }
        return;
    }
    authFeedbackEl.hidden = !message;
    authFeedbackEl.textContent = message || '';
    authFeedbackEl.classList.toggle('auth-feedback-success', variant === 'success');
    authFeedbackEl.classList.toggle('auth-feedback-error', variant !== 'success');
}

function clearAuthFeedback() {
    if (!authFeedbackEl) return;
    authFeedbackEl.hidden = true;
    authFeedbackEl.textContent = '';
    authFeedbackEl.classList.remove('auth-feedback-success', 'auth-feedback-error');
}

function mapFirebaseAuthError(error, mode) {
    const code = error && error.code ? String(error.code) : '';
    if (code === 'auth/invalid-credential' || code === 'auth/wrong-password' || code === 'auth/user-not-found' || code === 'auth/invalid-login-credentials') {
        return mode === 'login'
            ? 'Incorrect email or password.'
            : 'We could not create your account with those details.';
    }
    if (code === 'auth/email-already-in-use') {
        return 'That email is already in use.';
    }
    if (code === 'auth/popup-closed-by-user') {
        return 'Google sign-in was canceled before it finished.';
    }
    if (code === 'auth/popup-blocked') {
        return 'Your browser blocked the Google sign-in popup.';
    }
    if (code === 'auth/unauthorized-domain') {
        return 'This site is not authorized for Google sign-in in Firebase yet.';
    }
    return error && error.message ? error.message : 'Authentication failed.';
}

function setAuthState(user) {
    currentUser = user || null;
    if (loginBtn) {
        loginBtn.textContent = currentUser ? currentUser.username : 'Log in';
    }
    if (signupBtn) {
        signupBtn.textContent = currentUser ? 'Log out' : 'Sign up';
    }
    if (currentUser) {
        setSyncStatus('Inbox sync ready', 'Run Sync Emails below to refresh your latest receipts.');
    } else {
        setSyncStatus('Secure inbox connection', 'Log in to connect Gmail and unlock live receipt sync.');
    }
}

function hasUsableFirebaseConfig() {
    if (!firebaseConfig) return false;
    return Boolean(firebaseConfig.apiKey && firebaseConfig.authDomain && firebaseConfig.projectId && firebaseConfig.appId);
}

function initializeFirebaseAuth() {
    if (!window.firebase || !hasUsableFirebaseConfig()) {
        return;
    }
    if (!window.firebase.apps.length) {
        window.firebase.initializeApp(firebaseConfig);
    }
    firebaseAuth = window.firebase.auth();
    firebaseReadyPromise = new Promise(function(resolve) {
        let resolved = false;
        firebaseAuth.onIdTokenChanged(async function(user) {
            if (user) {
                try {
                    const token = await user.getIdToken();
                    localStorage.setItem('AUTH_TOKEN', token);
                } catch (error) {
                    console.error('Failed to refresh Firebase ID token:', error);
                }
            } else {
                localStorage.removeItem('AUTH_TOKEN');
                setAuthState(null);
            }
            if (!resolved) {
                resolved = true;
                resolve();
            }
        });
    });
}

async function getAuthToken() {
    if (!DEMO_MODE) {
        await firebaseReadyPromise;
    }
    if (firebaseAuth && firebaseAuth.currentUser) {
        const token = await firebaseAuth.currentUser.getIdToken();
        localStorage.setItem('AUTH_TOKEN', token);
        return token;
    }
    return localStorage.getItem('AUTH_TOKEN');
}

async function hasActiveAuthSession() {
    return Boolean(await getAuthToken());
}

async function fetchCurrentUserProfile() {
    const response = await authFetch(`${API_BASE_URL}/api/auth/me`, { cache: 'no-store' });
    if (!response.ok) {
        const result = await response.json().catch(() => ({}));
        throw new Error(result.detail || 'Could not load account');
    }
    return response.json();
}

async function bootstrapAuth() {
    await firebaseReadyPromise;
    const token = await getAuthToken();
    if (!token) {
        setAuthState(null);
        return;
    }
    try {
        const user = await fetchCurrentUserProfile();
        setAuthState(user);
    } catch (error) {
        localStorage.removeItem('AUTH_TOKEN');
        setAuthState(null);
    }
}

async function submitLogin() {
    clearAuthFeedback();
    if (!authLoginUsername || !authLoginPassword) return;
    const email = authLoginUsername.value.trim().toLowerCase();
    const password = authLoginPassword.value;
    if (!email || !password) {
        setAuthFeedback('Enter your email and password.');
        return;
    }
    if (!firebaseAuth || !hasUsableFirebaseConfig()) {
        setAuthFeedback('Firebase Auth is not configured yet.');
        return;
    }
    try {
        await firebaseAuth.signInWithEmailAndPassword(email, password);
        const user = await fetchCurrentUserProfile();
        setAuthState(user);
        closeAuthModal();
        loadDashboardData();
    } catch (error) {
        setAuthFeedback(mapFirebaseAuthError(error, 'login'));
    }
}

async function submitSignup() {
    clearAuthFeedback();
    if (!authSignupUsername || !authSignupEmail || !authSignupPassword) return;
    const username = authSignupUsername.value.trim();
    const email = authSignupEmail.value.trim().toLowerCase();
    const password = authSignupPassword.value;
    if (!username || !email || !password) {
        setAuthFeedback('Enter a username, email, and password.');
        return;
    }
    if (!isValidEmail(email)) {
        setAuthFeedback('Enter a valid email address.');
        return;
    }
    const passwordValidation = validatePasswordStrength(password);
    if (!passwordValidation.valid) {
        setAuthFeedback(passwordValidation.message);
        return;
    }
    if (!firebaseAuth || !hasUsableFirebaseConfig()) {
        setAuthFeedback('Firebase Auth is not configured yet.');
        return;
    }
    try {
        const credential = await firebaseAuth.createUserWithEmailAndPassword(email, password);
        if (credential.user) {
            await credential.user.updateProfile({ displayName: username });
        }
        const user = await fetchCurrentUserProfile();
        setAuthState(user);
        closeAuthModal();
        showSuccess('Signed up successfully. You are now logged in.');
        loadDashboardData();
    } catch (error) {
        setAuthFeedback(mapFirebaseAuthError(error, 'signup'));
    }
}

async function submitGoogleAuth() {
    clearAuthFeedback();
    if (!firebaseAuth || !hasUsableFirebaseConfig()) {
        setAuthFeedback('Firebase Auth is not configured yet.');
        return;
    }
    const provider = new window.firebase.auth.GoogleAuthProvider();
    provider.setCustomParameters({ prompt: 'select_account' });
    try {
        await firebaseAuth.signInWithPopup(provider);
        const user = await fetchCurrentUserProfile();
        setAuthState(user);
        closeAuthModal();
        showSuccess('Signed in with Google.');
        loadDashboardData();
    } catch (error) {
        setAuthFeedback(mapFirebaseAuthError(error, 'google'));
    }
}

async function logoutUser() {
    const token = await getAuthToken();
    if (token) {
        await authFetch(`${API_BASE_URL}/api/auth/logout`, { method: 'POST' });
    }
    if (firebaseAuth) {
        await firebaseAuth.signOut();
    }
    localStorage.removeItem('AUTH_TOKEN');
    setAuthState(null);
}

// Load all dashboard data from API
async function loadDashboardData() {
    setDashboardLoading(true);
    try {
        await Promise.all([
            loadTransactions(),
            loadStats(),
            loadTopVendors()
        ]);
    } catch (error) {
        console.error('Error loading dashboard:', error);
        if (!DEMO_MODE) {
            const base = API_BASE_URL || 'the API';
            showError(`Failed to load dashboard data. Make sure the API is running at ${base}.`);
        }
    } finally {
        setDashboardLoading(false);
    }
}

// Load transactions from API
async function loadTransactions() {
    try {
        const endpoint = DEMO_MODE ? '/api/demo/transactions' : '/api/transactions';
        const response = await authFetch(`${API_BASE_URL}${endpoint}`, { cache: 'no-store' });
        
        if (!response.ok) {
            throw new Error(`API returned ${response.status}`);
        }
        
        const transactions = await response.json();
        // Strip any zero-amount rows so the table never shows $0.00 (safety net)
        allTransactions = (transactions || []).filter(function(t) {
            const amt = Number(t.amount);
            return t.amount != null && !Number.isNaN(amt) && amt !== 0 && Math.abs(amt) >= 0.0001;
        });
        
        console.log(`Loaded ${allTransactions.length} transactions`);
        
        if (tableBody) {
            renderTransactionsTable();
            updateSortArrows();
        }

        renderExpensePreview(allTransactions);
        refreshVendorInsights();
        renderSpendingTrends(allTransactions);

        // Duplicate detection
        const dupWarning = document.querySelector('#duplicate-warning');
        if (dupWarning) {
            dupWarning.hidden = !detectDuplicates(allTransactions);
        }

        return allTransactions;
    } catch (error) {
        console.error('Error loading transactions:', error);
        throw error;
    }
}

// Load statistics from API
async function loadStats() {
    try {
        const endpoint = DEMO_MODE ? '/api/demo/stats' : '/api/stats';
        const response = await authFetch(`${API_BASE_URL}${endpoint}`, { cache: 'no-store' });
        
        if (!response.ok) {
            throw new Error(`API returned ${response.status}`);
        }
        
        const stats = await response.json();
        
        console.log('Stats loaded:', stats);
        
        // Update stat cards
        updateStatCards(stats);
        updateHeroSummary(stats);
        
        return stats;
    } catch (error) {
        console.error('Error loading stats:', error);
        throw error;
    }
}

// Load top vendors from API
async function loadTopVendors() {
    try {
        const endpoint = DEMO_MODE ? '/api/demo/top-vendors' : '/api/top-vendors';
        const response = await authFetch(`${API_BASE_URL}${endpoint}`, { cache: 'no-store' });
        
        if (!response.ok) {
            throw new Error(`API returned ${response.status}`);
        }
        
        const vendors = await response.json();
        
        console.log('Top vendors loaded:', vendors);
        latestTopVendors = Array.isArray(vendors) ? vendors : [];
        
        // Update vendor cards
        refreshVendorInsights();
        
        return latestTopVendors;
    } catch (error) {
        console.error('Error loading top vendors:', error);
        throw error;
    }
}

// Update stat cards with real data
function updateStatCards(stats) {
    const statCards = document.querySelectorAll('.stat-card-hero');
    
    if (statCards.length >= 4) {
        // Total Spent
        const totalSpentValue = statCards[0].querySelector('.stat-value-large');
        if (totalSpentValue) {
            totalSpentValue.textContent = formatCurrency(stats.total_spent || 0);
        }
        
        // Total Receipts
        const totalReceiptsValue = statCards[1].querySelector('.stat-value-large');
        if (totalReceiptsValue) {
            totalReceiptsValue.textContent = stats.total_receipts;
        }
        
        // Unique Vendors
        const uniqueVendorsValue = statCards[2].querySelector('.stat-value-large');
        if (uniqueVendorsValue) {
            uniqueVendorsValue.textContent = stats.unique_vendors;
        }
        
        // Average Transaction
        const avgTransactionValue = statCards[3].querySelector('.stat-value-large');
        if (avgTransactionValue) {
            avgTransactionValue.textContent = formatCurrency(stats.avg_transaction || 0);
        }
    }
}

function updateHeroSummary(stats) {
    if (heroTotalSpentEl) {
        heroTotalSpentEl.textContent = formatCurrency(stats.total_spent || 0);
    }
    if (heroSummaryLineEl) {
        const receiptCount = Number(stats.total_receipts) || 0;
        const vendorCount = Number(stats.unique_vendors) || 0;
        const average = formatCurrency(stats.avg_transaction || 0);
        heroSummaryLineEl.textContent = `${receiptCount} receipt${receiptCount === 1 ? '' : 's'} across ${vendorCount} vendor${vendorCount === 1 ? '' : 's'}. Average ticket ${average}.`;
    }
    updateBudgetSummary(Number(stats.total_spent) || 0);
}

function renderExpensePreview(transactions) {
    if (!expensePreviewListEl) return;

    const sorted = [...(transactions || [])].sort(compareTransactionsByNewest);
    const previewItems = sorted.slice(0, 5);

    if (!previewItems.length) {
        expensePreviewListEl.innerHTML = '<div class="expense-empty">No synced receipts yet. Connect Gmail and run a sync to populate this feed.</div>';
        if (expensePeriodLabelEl) {
            expensePeriodLabelEl.textContent = formatMonthLabel();
        }
        updateBudgetSummary(0);
        return;
    }

    expensePreviewListEl.innerHTML = previewItems.map(function(transaction) {
        const vendorInfo = getVendorInfo(transaction.vendor);
        const amount = Number(transaction.amount) || 0;
        const absoluteAmount = Math.abs(amount);
        const isCredit = amount < 0;
        const amountClass = isCredit ? 'positive' : 'negative';
        const amountPrefix = isCredit ? '+' : '-';
        const meta = transaction.category
            ? `${transaction.category} • ${formatIsoDateForEasternDisplay(transaction.date).dateFormatted}`
            : `${getParserLabelText(transaction.vendor)} • ${formatIsoDateForEasternDisplay(transaction.date).dateFormatted}`;

        return `
            <div class="expense-item">
                <div class="expense-avatar">${escapeHtml(vendorInfo.icon)}</div>
                <div class="expense-copy">
                    <div class="expense-name">${escapeHtml(transaction.vendor || 'Unknown vendor')}</div>
                    <div class="expense-meta">${escapeHtml(meta)}</div>
                </div>
                <div class="expense-amount ${amountClass}">${amountPrefix}${formatCurrency(absoluteAmount)}</div>
            </div>
        `;
    }).join('');

    if (expensePeriodLabelEl) {
        expensePeriodLabelEl.textContent = formatMonthLabel(previewItems[0].date);
    }

    const totalSpend = sorted.reduce(function(sum, transaction) {
        const amount = Number(transaction.amount) || 0;
        return amount > 0 ? sum + amount : sum;
    }, 0);
    updateBudgetSummary(totalSpend);
}

function updateBudgetSummary(totalSpend) {
    const spend = Math.max(0, Number(totalSpend) || 0);
    const storedTarget = getStoredMonthlyBudget();
    const target = storedTarget || getAutomaticBudgetTarget(spend);
    const usageRatio = target > 0 ? spend / target : 0;
    const progressRatio = Math.max(0, Math.min(usageRatio, 1));
    currentBudgetSpend = spend;

    if (expenseBudgetUsedEl) {
        expenseBudgetUsedEl.textContent = `${Math.round(Math.max(usageRatio, 0) * 100)}% used`;
        expenseBudgetUsedEl.classList.toggle('budget-over', usageRatio > 1);
    }
    if (expenseBudgetCurrentEl) {
        expenseBudgetCurrentEl.textContent = formatCurrency(spend, { whole: true });
    }
    if (expenseBudgetTargetEl) {
        expenseBudgetTargetEl.textContent = formatCurrency(target, { whole: true });
    }
    if (expenseBudgetFillEl) {
        const width = spend > 0 ? Math.max(progressRatio * 100, 8) : 0;
        expenseBudgetFillEl.style.width = `${width}%`;
        expenseBudgetFillEl.classList.toggle('budget-fill-over', usageRatio > 1);
    }
    refreshBudgetEditor({ preserveInput: true });
}

function getAutomaticBudgetTarget(spend) {
    return spend > 0 ? Math.ceil((spend * 1.35) / 500) * 500 : 1500;
}

function getStoredMonthlyBudget() {
    try {
        const rawValue = localStorage.getItem(MONTHLY_BUDGET_STORAGE_KEY);
        const parsedValue = Number(rawValue);
        if (!rawValue || !Number.isFinite(parsedValue) || parsedValue <= 0) {
            return null;
        }
        return Math.round(parsedValue);
    } catch (error) {
        return null;
    }
}

function setStoredMonthlyBudget(amount) {
    try {
        localStorage.setItem(MONTHLY_BUDGET_STORAGE_KEY, String(Math.round(amount)));
    } catch (error) {
        // Ignore storage write failures and keep the dashboard usable.
    }
}

function clearStoredMonthlyBudget() {
    try {
        localStorage.removeItem(MONTHLY_BUDGET_STORAGE_KEY);
    } catch (error) {
        // Ignore storage removal failures and keep the dashboard usable.
    }
}

function refreshBudgetEditor(options = {}) {
    const preserveInput = Boolean(options.preserveInput);
    const storedTarget = getStoredMonthlyBudget();

    if (expenseBudgetInputEl) {
        const shouldPreserveValue = preserveInput && document.activeElement === expenseBudgetInputEl;
        if (!shouldPreserveValue) {
            expenseBudgetInputEl.value = storedTarget ? String(storedTarget) : '';
        }
        expenseBudgetInputEl.placeholder = String(getAutomaticBudgetTarget(currentBudgetSpend));
    }

    if (expenseBudgetNoteEl) {
        expenseBudgetNoteEl.textContent = storedTarget
            ? 'Manual budget saved on this device.'
            : 'Auto target based on current spend.';
    }
}

function saveMonthlyBudget() {
    if (!expenseBudgetInputEl) return;
    if (!expenseBudgetInputEl.reportValidity()) return;

    const nextValue = Number(expenseBudgetInputEl.value);
    if (!Number.isFinite(nextValue) || nextValue <= 0) {
        refreshBudgetEditor();
        return;
    }

    setStoredMonthlyBudget(nextValue);
    updateBudgetSummary(currentBudgetSpend);
}

function resetMonthlyBudget() {
    clearStoredMonthlyBudget();
    updateBudgetSummary(currentBudgetSpend);
}

function isValidEmail(value) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(value || '').trim());
}

function validatePasswordStrength(password) {
    const value = String(password || '');
    const checks = {
        length: value.length >= 8,
        uppercase: /[A-Z]/.test(value),
        number: /\d/.test(value),
        special: /[^A-Za-z0-9]/.test(value)
    };
    const valid = Object.values(checks).every(Boolean);
    const requirements = [];
    if (!checks.length) requirements.push('at least 8 characters');
    if (!checks.uppercase) requirements.push('1 uppercase letter');
    if (!checks.number) requirements.push('1 number');
    if (!checks.special) requirements.push('1 special character');
    return {
        valid,
        checks,
        message: valid
            ? ''
            : `Password not strong enough. It needs ${requirements.join(', ')}.`
    };
}

function updatePasswordRequirementState(password) {
    const validation = validatePasswordStrength(password);
    document.querySelectorAll('[data-password-rule]').forEach(function(rule) {
        const key = rule.getAttribute('data-password-rule');
        const satisfied = Boolean(validation.checks[key]);
        rule.classList.toggle('password-rule-valid', satisfied);
    });
}

function refreshVendorInsights() {
    const insights = buildVendorInsights(allTransactions);
    updateVendorCards(latestTopVendors, insights);
    updateHeroVendors(latestTopVendors, insights);
    updateInsightVisual(latestTopVendors, allTransactions);
}

function updateHeroVendors(vendors, insights) {
    if (!heroVendorListEl) return;
    insights = insights || {};

    const topVendors = (vendors || []).slice(0, 2);
    if (!topVendors.length) {
        heroVendorListEl.innerHTML = '<div class="hero-vendor-empty">Top merchants will appear here after your first successful sync.</div>';
        return;
    }

    heroVendorListEl.innerHTML = topVendors.map(function(vendor, index) {
        const insight = insights[normalizeVendorKey(vendor.vendor)] || null;
        const dotClass = index === 0 ? 'hero-vendor-dot' : 'hero-vendor-dot hero-vendor-dot-secondary';
        return `
            <div class="hero-vendor-item">
                <span class="${dotClass}"></span>
                <div class="hero-vendor-copy">
                    <div class="hero-vendor-name">${escapeHtml(vendor.vendor || 'Unknown vendor')}</div>
                    <div class="hero-vendor-meta">${escapeHtml(buildVendorDescriptor(vendor, insight, index))}</div>
                </div>
            </div>
        `;
    }).join('');
}

function updateInsightVisual(vendors, transactions) {
    const bars = document.querySelectorAll('.insight-bar');
    if (!bars.length) return;

    const topVendors = (vendors || []).slice(0, bars.length);
    const spendTotal = getPositiveSpendTotal(transactions);
    const maxTotal = Math.max.apply(null, [1].concat(topVendors.map(function(vendor) {
        return Math.max(Number(vendor.total) || 0, 0);
    })));

    bars.forEach(function(bar, index) {
        const vendor = topVendors[index];
        if (!vendor) {
            bar.style.height = '18%';
            bar.dataset.label = 'No data';
            bar.dataset.value = '';
            bar.title = 'No synced vendor data yet';
            bar.classList.add('insight-bar-empty');
            return;
        }

        const total = Math.max(Number(vendor.total) || 0, 0);
        const share = spendTotal > 0 ? total / spendTotal : 0;
        const height = Math.max(22, Math.round((total / maxTotal) * 100));
        bar.style.height = `${height}%`;
        bar.dataset.label = abbreviateVendorLabel(vendor.vendor);
        bar.dataset.value = `${formatCurrency(total, { whole: total >= 100 })} • ${formatPercent(share)}`;
        bar.title = `${vendor.vendor || 'Unknown vendor'}: ${formatCurrency(total)} across ${vendor.count || 0} receipt${Number(vendor.count) === 1 ? '' : 's'}`;
        bar.classList.remove('insight-bar-empty');
    });
}

function compareTransactionsByNewest(a, b) {
    return toComparableDateValue(b.date) - toComparableDateValue(a.date);
}

function toComparableDateValue(dateStr) {
    const parts = parseIsoDateParts(dateStr);
    if (parts) {
        return Date.UTC(parts.year, parts.month - 1, parts.day, 12, 0, 0);
    }
    const date = new Date(dateStr);
    return Number.isNaN(date.getTime()) ? 0 : date.getTime();
}

function formatMonthLabel(dateStr) {
    const value = dateStr ? toComparableDateValue(dateStr) : Date.now();
    const safeValue = value > 0 ? value : Date.now();
    return new Intl.DateTimeFormat('en-US', {
        month: 'long',
        year: 'numeric',
        timeZone: 'America/New_York'
    }).format(new Date(safeValue));
}

function formatCurrency(value, options = {}) {
    const whole = Boolean(options.whole);
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: whole ? 0 : 2,
        maximumFractionDigits: whole ? 0 : 2
    }).format(Number(value) || 0);
}

function getParserLabelText(vendor) {
    const vendorLower = String(vendor || '').toLowerCase();
    if (vendorLower.includes('amazon')) {
        return 'Amazon Parser';
    }
    if (vendorLower.includes('paypal')) {
        return 'PayPal Parser';
    }
    return 'Auto classified';
}

function buildVendorDescriptor(vendor, insight) {
    if (!insight) {
        const count = Number(vendor.count) || 0;
        return count
            ? `${count} receipt${count === 1 ? '' : 's'} • awaiting spend breakdown`
            : 'Awaiting spend breakdown';
    }
    const parts = [];
    if (Number.isFinite(insight.share) && insight.share > 0) {
        parts.push(`${formatPercent(insight.share)} of synced spend`);
    }
    if (Number.isFinite(insight.average) && insight.average > 0) {
        parts.push(`avg ${formatCurrency(insight.average)}`);
    }
    if (parts.length) {
        return parts.join(' • ');
    }
    return `${insight.count} receipt${insight.count === 1 ? '' : 's'}`;
}

function buildVendorCategoryLabel(vendor, insight) {
    if (insight && Number.isFinite(insight.average) && insight.average > 0) {
        return `Avg ticket ${formatCurrency(insight.average)}`;
    }
    const total = Number(vendor.total) || 0;
    return total > 0 ? `Spend ${formatCurrency(total)}` : 'Spend data unavailable';
}

function buildVendorFooterLabel(vendor, insight) {
    if (!insight) {
        const count = Number(vendor.count) || 0;
        return `${count} synced receipt${count === 1 ? '' : 's'}`;
    }
    const parts = [];
    if (Number.isFinite(insight.share) && insight.share > 0) {
        parts.push(`${formatPercent(insight.share)} of spend`);
    }
    if (insight.latestDateLabel) {
        parts.push(`last receipt ${insight.latestDateLabel}`);
    }
    return parts.join(' • ') || `${insight.count} synced receipt${insight.count === 1 ? '' : 's'}`;
}

function buildVendorInsights(transactions) {
    const summary = {};
    const spendTotal = getPositiveSpendTotal(transactions);

    (transactions || []).forEach(function(transaction) {
        const key = normalizeVendorKey(transaction.vendor);
        if (!key) return;

        if (!summary[key]) {
            summary[key] = {
                count: 0,
                positiveCount: 0,
                total: 0,
                latestDateValue: 0,
                latestDateLabel: '',
                latestAmount: 0
            };
        }

        const insight = summary[key];
        const amount = Number(transaction.amount) || 0;
        const dateValue = toComparableDateValue(transaction.date);
        insight.count += 1;

        if (amount > 0) {
            insight.total += amount;
            insight.positiveCount += 1;
        }

        if (dateValue >= insight.latestDateValue) {
            const dateDisplay = formatIsoDateForEasternDisplay(transaction.date);
            insight.latestDateValue = dateValue;
            insight.latestDateLabel = dateDisplay.dateFormatted;
            insight.latestAmount = amount;
        }
    });

    Object.keys(summary).forEach(function(key) {
        const insight = summary[key];
        insight.average = insight.positiveCount > 0 ? insight.total / insight.positiveCount : 0;
        insight.share = spendTotal > 0 ? insight.total / spendTotal : 0;
    });

    return summary;
}

function getPositiveSpendTotal(transactions) {
    return (transactions || []).reduce(function(sum, transaction) {
        const amount = Number(transaction.amount) || 0;
        return amount > 0 ? sum + amount : sum;
    }, 0);
}

function normalizeVendorKey(value) {
    return String(value || '').trim().toLowerCase();
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

function getFilteredTransactions() {
    if (activeDateFilter === 'all') return allTransactions;
    const d = new Date();
    let cutoff;
    if (activeDateFilter === '30d') {
        cutoff = new Date(d.getFullYear(), d.getMonth(), d.getDate() - 30).getTime();
    } else if (activeDateFilter === '3m') {
        cutoff = new Date(d.getFullYear(), d.getMonth() - 3, d.getDate()).getTime();
    } else if (activeDateFilter === '1y') {
        cutoff = new Date(d.getFullYear() - 1, d.getMonth(), d.getDate()).getTime();
    }
    if (!cutoff) return allTransactions;
    return allTransactions.filter(function(t) {
        return toComparableDateValue(t.date) >= cutoff;
    });
}

function detectDuplicates(transactions) {
    const seen = {};
    let hasDuplicates = false;
    (transactions || []).forEach(function(t) {
        const key = `${normalizeVendorKey(t.vendor)}|${Number(t.amount || 0).toFixed(2)}|${t.date || ''}`;
        if (seen[key]) {
            hasDuplicates = true;
        }
        seen[key] = true;
    });
    return hasDuplicates;
}

function formatPercent(value) {
    const ratio = Number(value) || 0;
    if (ratio <= 0) return '0%';
    if (ratio < 0.1) return `${ratio * 100 < 1 ? '<1' : Math.round(ratio * 100)}%`;
    return `${Math.round(ratio * 100)}%`;
}

function abbreviateVendorLabel(value) {
    const text = String(value || '').trim();
    if (!text) return 'Unknown';
    const compact = text.split(/\s+/).slice(0, 2).join(' ');
    return compact.length > 14 ? `${compact.slice(0, 13)}…` : compact;
}

function startIdlePoll() {
    if (idlePollTimer) clearInterval(idlePollTimer);
    idlePollTimer = setInterval(function() {
        if (currentUser && !syncPollTimer && !demoParsePollTimer && !document.hidden) {
            loadDashboardData();
        }
    }, 30000);
}

function getProcessedTransactions() {
    let result = getFilteredTransactions(); // date filter
    const term = activeSearchTerm.trim().toLowerCase();
    if (term) {
        result = result.filter(function(t) {
            const vendor = (t.vendor || '').toLowerCase();
            const cat = (t.category || getCategoryForVendor(t.vendor)).toLowerCase();
            const amount = String(t.amount || '');
            const date = (t.date || '').toLowerCase();
            return vendor.includes(term) || cat.includes(term) || amount.includes(term) || date.includes(term);
        });
    }
    return sortTransactions([...result]);
}

function updatePaginationUI(total, start, end, totalPages) {
    const infoEl = document.querySelector('#table-info');
    const prevBtn = document.querySelector('#prev-page');
    const nextBtn = document.querySelector('#next-page');
    const indicator = document.querySelector('#page-indicator');
    if (infoEl) infoEl.textContent = total === 0 ? 'No transactions' : `Showing ${start + 1}–${end} of ${total}`;
    if (prevBtn) prevBtn.disabled = currentPage <= 1;
    if (nextBtn) nextBtn.disabled = currentPage >= totalPages;
    if (indicator) indicator.textContent = `${currentPage} / ${totalPages}`;
}

function setDashboardLoading(loading) {
    document.querySelectorAll('.skeleton-target').forEach(function(el) {
        el.classList.toggle('skeleton-pulse', loading);
    });
}

function openSettingsPanel() {
    const drawer = document.querySelector('#settings-drawer');
    if (!drawer) return;
    // Sync budget input with stored value
    const budgetInput = document.querySelector('#settings-budget-input');
    if (budgetInput) {
        const stored = getStoredMonthlyBudget();
        budgetInput.value = stored ? String(stored) : '';
        budgetInput.placeholder = String(getAutomaticBudgetTarget(currentBudgetSpend));
    }
    // Sync Gmail status
    const gmailStatus = document.querySelector('#settings-gmail-status');
    if (gmailStatus) {
        gmailStatus.textContent = currentUser ? `Connected as ${currentUser.email || currentUser.username || 'your account'}` : 'Not connected';
    }
    drawer.hidden = false;
    drawer.setAttribute('aria-hidden', 'false');
    requestAnimationFrame(function() { drawer.classList.add('settings-open'); });
}

function closeSettingsPanel() {
    const drawer = document.querySelector('#settings-drawer');
    if (!drawer) return;
    drawer.classList.remove('settings-open');
    setTimeout(function() {
        drawer.hidden = true;
        drawer.setAttribute('aria-hidden', 'true');
    }, 300);
}

function showUndoToast(message, onUndo) {
    const existing = document.querySelector('.undo-toast');
    if (existing) existing.remove();
    const toast = document.createElement('div');
    toast.className = 'undo-toast';
    toast.innerHTML = `<span class="undo-toast-msg">${escapeHtml(message)}</span><button class="undo-toast-btn" type="button">Undo</button>`;
    document.body.appendChild(toast);
    toast.querySelector('.undo-toast-btn').addEventListener('click', function() {
        toast.remove();
        if (onUndo) onUndo();
    });
    setTimeout(function() { if (toast.parentNode) toast.remove(); }, 5200);
}

function openReceiptPreview(transaction) {
    const modal = document.querySelector('#receipt-modal');
    if (!modal) return;
    const bodyEl = document.querySelector('#receipt-body');
    const itemsEl = document.querySelector('#receipt-items');
    const titleEl = document.querySelector('#receipt-modal-title');

    if (titleEl) titleEl.textContent = `Receipt — ${transaction.vendor || 'Unknown vendor'}`;

    if (itemsEl) {
        itemsEl.hidden = true;
        itemsEl.innerHTML = '';
        if (transaction.items) {
            try {
                const items = typeof transaction.items === 'string' ? JSON.parse(transaction.items) : transaction.items;
                if (Array.isArray(items) && items.length) {
                    items.forEach(function(item) {
                        const row = document.createElement('div');
                        row.className = 'receipt-item-row';
                        const name = typeof item === 'string' ? item : (item.name || item.description || JSON.stringify(item));
                        const price = item.price != null ? formatCurrency(Number(item.price)) : '';
                        row.innerHTML = `<span class="receipt-item-name">${escapeHtml(name)}</span>${price ? `<span class="receipt-item-price">${escapeHtml(price)}</span>` : ''}`;
                        itemsEl.appendChild(row);
                    });
                    itemsEl.hidden = false;
                }
            } catch(e) {
                // items not parseable — fall through to email body
            }
        }
    }

    if (bodyEl) {
        bodyEl.textContent = transaction.email_body
            ? transaction.email_body
            : '(No email body stored for this receipt)';
    }

    modal.classList.add('show');
    modal.style.display = 'flex';
    modal.hidden = false;
}

function setSyncStatus(title, meta) {
    if (syncStatusTitleEl) {
        syncStatusTitleEl.textContent = title;
    }
    if (syncStatusMetaEl) {
        syncStatusMetaEl.textContent = meta;
    }
}

function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, function(char) {
        return ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
        })[char];
    });
}

// Render table using the unified pipeline: date filter → search → sort → paginate
function renderTransactionsTable() {
    if (!tableBody) return;

    const processed = getProcessedTransactions();
    const total = processed.length;
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    currentPage = Math.max(1, Math.min(currentPage, totalPages));

    const start = (currentPage - 1) * pageSize;
    const end = Math.min(start + pageSize, total);
    const pageItems = processed.slice(start, end);

    tableBody.innerHTML = '';
    pageItems.forEach(function(transaction) {
        tableBody.appendChild(createTransactionRow(transaction));
    });

    tableBody.querySelectorAll('.edit-btn').forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            const id = this.getAttribute('data-id');
            if (!id) return;
            const row = this.closest('tr');
            if (row) openEditModal(row);
        });
    });

    tableBody.querySelectorAll('.view-receipt-btn').forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            const id = this.getAttribute('data-id');
            if (!id) return;
            const tx = allTransactions.find(t => String(t.id) === id);
            if (tx) openReceiptPreview(tx);
        });
    });

    updatePaginationUI(total, start, end, totalPages);

    const onboardingCard = document.querySelector('#onboarding-card');
    if (onboardingCard) onboardingCard.hidden = allTransactions.length > 0;
}

function parseIsoDateParts(dateStr) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(dateStr || ''));
    if (!match) return null;
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    if (!year || month < 1 || month > 12 || day < 1 || day > 31) return null;
    return { year, month, day };
}

function formatIsoDateForEasternDisplay(dateStr) {
    const parts = parseIsoDateParts(dateStr);
    if (!parts) {
        const d = new Date(dateStr);
        return {
            dateFormatted: d.toLocaleDateString('en-US', { month: 'short', day: '2-digit' }),
            yearFormatted: d.getFullYear()
        };
    }
    // Use UTC noon to avoid day rollovers when rendering in America/New_York.
    const noonUtc = new Date(Date.UTC(parts.year, parts.month - 1, parts.day, 12, 0, 0));
    const dtf = new Intl.DateTimeFormat('en-US', {
        timeZone: 'America/New_York',
        month: 'short',
        day: '2-digit',
        year: 'numeric'
    });
    const tokens = dtf.formatToParts(noonUtc);
    const month = (tokens.find(t => t.type === 'month') || {}).value || '';
    const day = (tokens.find(t => t.type === 'day') || {}).value || '';
    const year = (tokens.find(t => t.type === 'year') || {}).value || String(parts.year);
    return {
        dateFormatted: `${month} ${day}`.trim(),
        yearFormatted: Number(year) || parts.year
    };
}

function sortTransactions(transactions) {
    const mult = sortDirection === 'asc' ? 1 : -1;
    return transactions.sort((a, b) => {
        let va, vb;
        if (sortColumn === 'date') {
            const ap = parseIsoDateParts(a.date);
            const bp = parseIsoDateParts(b.date);
            if (ap && bp) {
                va = (ap.year * 10000) + (ap.month * 100) + ap.day;
                vb = (bp.year * 10000) + (bp.month * 100) + bp.day;
            } else {
                va = new Date(a.date).getTime();
                vb = new Date(b.date).getTime();
            }
            return mult * (va - vb);
        }
        if (sortColumn === 'amount') {
            va = Number(a.amount) || 0;
            vb = Number(b.amount) || 0;
            return mult * (va - vb);
        }
        if (sortColumn === 'tax') {
            va = Number(a.tax) || 0;
            vb = Number(b.tax) || 0;
            return mult * (va - vb);
        }
        return 0;
    });
}

// Update sort arrows in header (↑ / ↓)
function updateSortArrows() {
    const arrow = sortDirection === 'asc' ? ' ↑' : ' ↓';
    document.querySelectorAll('.sortable .sort-arrow').forEach(function(span) {
        span.textContent = '';
    });
    const active = document.querySelector('.sortable[data-sort="' + sortColumn + '"] .sort-arrow');
    if (active) active.textContent = arrow;
}

// Create a table row for a transaction
function createTransactionRow(transaction) {
    const row = document.createElement('tr');
    row.classList.add('table-row');
    row.dataset.transactionId = transaction.id;
    
    // Format date
    const dateDisplay = formatIsoDateForEasternDisplay(transaction.date);
    const dateFormatted = dateDisplay.dateFormatted;
    const yearFormatted = dateDisplay.yearFormatted;
    
    // Determine vendor icon and color
    const vendorInfo = getVendorInfo(transaction.vendor);

    const vendorName = escapeHtml(transaction.vendor || 'Unknown vendor');
    const amountValue = Number(transaction.amount) || 0;
    const taxValue = Number(transaction.tax) || 0;
    const category = transaction.category || getCategoryForVendor(transaction.vendor);

    row.innerHTML = `
        <td>
            <div class="date-cell">
                <span class="date-day">${dateFormatted}</span>
                <span class="date-year">${yearFormatted}</span>
            </div>
        </td>
        <td>
            <div class="vendor-cell">
                <div class="vendor-icon-wrapper ${vendorInfo.colorClass}">
                    <span class="vendor-icon">${vendorInfo.icon}</span>
                </div>
                <div class="vendor-info">
                    <span class="vendor-name">${vendorName}</span>
                </div>
            </div>
        </td>
        <td>
            <div class="amount-value">${formatCurrency(amountValue)}</div>
        </td>
        <td>
            <span class="tax-value">${formatCurrency(taxValue)}</span>
        </td>
        <td>
            <span class="category-badge">${escapeHtml(category)}</span>
        </td>
        <td>
            <div style="display:flex;gap:6px;align-items:center;">
                <button class="edit-btn" type="button" data-id="${transaction.id}">Edit</button>
                ${transaction.email_body ? `<button class="view-receipt-btn" type="button" data-id="${transaction.id}" title="View original receipt">Receipt</button>` : ''}
            </div>
        </td>
    `;
    
    return row;
}

// Get vendor icon and color class
function getVendorInfo(vendor) {
    const name = (vendor || '').trim();
    const initials = name
        ? name.split(/\s+/).slice(0, 2).map(word => word[0]).join('').toUpperCase()
        : 'V';
    return { icon: initials, colorClass: 'amazon-color' };
}

// Get parser badge based on vendor
function getParserBadge(vendor) {
    const vendorLower = String(vendor || '').toLowerCase();
    
    if (vendorLower.includes('amazon')) {
        return `
            <span class="badge badge-amazon">
                <span class="badge-dot"></span>
                Amazon Parser
            </span>
        `;
    } else if (vendorLower.includes('paypal')) {
        return `
            <span class="badge badge-paypal">
                <span class="badge-dot"></span>
                PayPal Parser
            </span>
        `;
    } else {
        return `
            <span class="badge badge-generic">
                <span class="badge-dot"></span>
                Generic Parser
            </span>
        `;
    }
}

// Update vendor cards with real data
function updateVendorCards(vendors, insights) {
    vendors = vendors || [];
    insights = insights || {};
    const vendorCards = document.querySelectorAll('.vendor-card-new');
    const maxTotal = Math.max.apply(null, [1].concat((vendors || []).map(function(vendor) {
        return Number(vendor.total) || 0;
    })));
    
    vendorCards.forEach((card, index) => {
        if (index >= vendors.length) {
            card.classList.add('vendor-card-empty');
            return;
        }
        card.classList.remove('vendor-card-empty');
        const vendor = vendors[index];
        const insight = insights[normalizeVendorKey(vendor.vendor)] || null;
        const name = (vendor.vendor || '').trim();
        const initials = name
            ? name.split(/\s+/).slice(0, 2).map(word => word[0]).join('').toUpperCase()
            : 'V';

        // Update vendor name
        const nameEl = card.querySelector('.vendor-card-name');
        if (nameEl) nameEl.textContent = vendor.vendor;

        // Update category label
        const categoryEl = card.querySelector('.vendor-card-category');
        if (categoryEl) categoryEl.textContent = buildVendorCategoryLabel(vendor, insight);

        // Update initials
        const emojiEl = card.querySelector('.vendor-logo-large');
        if (emojiEl) emojiEl.textContent = initials;

        // Update amount
        const amountEl = card.querySelector('.vendor-card-amount');
        if (amountEl) amountEl.textContent = formatCurrency(vendor.total || 0);

        // Update transaction count
        const countEl = card.querySelector('.vendor-card-transactions');
        if (countEl) countEl.textContent = `${vendor.count} transaction${vendor.count !== 1 ? 's' : ''}`;

        const progressEl = card.querySelector('.progress-fill-new');
        if (progressEl) {
            const width = Math.max(12, Math.round(((Number(vendor.total) || 0) / maxTotal) * 100));
            progressEl.style.width = `${width}%`;
        }

        const footerEl = card.querySelector('.vendor-card-footer');
        if (footerEl) {
            footerEl.innerHTML = '';
            const footerCopy = document.createElement('span');
            footerCopy.className = index === 0 ? 'trend-up' : 'trend-neutral';
            footerCopy.textContent = buildVendorFooterLabel(vendor, insight);
            footerEl.appendChild(footerCopy);
        }
    });
}

// Filter transactions based on search
function filterTransactions(searchTerm) {
    const rows = document.querySelectorAll('.transactions-table tbody tr');
    searchTerm = searchTerm.toLowerCase();
    
    rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        if (text.includes(searchTerm)) {
            row.style.display = '';
        } else {
            row.style.display = 'none';
        }
    });
}


// Sync emails via API (sync runs in background on server; this returns right away)
async function syncEmails() {
    if (!syncBtn) return;
    if (DEMO_MODE) {
        return;
    }
    if (!await hasActiveAuthSession()) {
        handleAuthRequired();
        return;
    }
    
    const originalHTML = syncBtn.innerHTML;
    const previousSignature = buildTransactionSignature(allTransactions);

    syncBtn.textContent = 'Starting sync...';
    syncBtn.disabled = true;
    setSyncStatus('Sync requested', 'Polling Gmail for fresh receipt activity.');

    try {
        const response = await authFetch(`${API_BASE_URL}/api/sync`, { method: 'POST' });
        const result = await response.json().catch(() => ({}));

        if (!response.ok) {
            throw new Error(result.detail || `API returned ${response.status}`);
        }

        syncRunId = result.run_id || null;
        syncBtn.textContent = 'Syncing...';
        startSyncRefreshLoop(previousSignature, originalHTML);
        
    } catch (error) {
        console.error('Sync failed:', error);
        syncBtn.textContent = 'Sync Failed';
        setSyncStatus('Sync failed', error.message || 'Email sync failed.');
        
        setTimeout(() => {
            syncBtn.innerHTML = originalHTML;
            syncBtn.disabled = false;
        }, 2000);
        
        const message = error.message || 'Email sync failed. Make sure the API is running and Gmail is configured.';
        showError(message);
    }
}

async function buildAuthHeaders() {
    const headers = {};
    const token = await getAuthToken();
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    return headers;
}

function handleAuthRequired() {
    if (handleAuthRequired.lastShown && Date.now() - handleAuthRequired.lastShown < 2500) {
        return;
    }
    handleAuthRequired.lastShown = Date.now();
    showError('Please log in to view your data.');
    openAuthModal('login');
}

async function authFetch(url, options = {}) {
    const headers = Object.assign({}, options.headers || {}, await buildAuthHeaders());
    const response = await fetch(url, Object.assign({}, options, { headers }));
    if (response.status === 401) {
        handleAuthRequired();
    }
    return response;
}

function appendDemoRunLog(line) {
    if (!demoRunLogEl) return;
    const current = demoRunLogEl.textContent || '';
    demoRunLogEl.textContent = current ? `${current}\n${line}` : line;
    demoRunLogEl.scrollTop = demoRunLogEl.scrollHeight;
}

function startButtonDotAnimation(button, baseLabel) {
    if (!button) {
        return function noop() {};
    }

    let dots = 1;
    button.textContent = `${baseLabel}${'.'.repeat(dots)}`;

    const timer = setInterval(function() {
        dots = dots % 3 + 1;
        button.textContent = `${baseLabel}${'.'.repeat(dots)}`;
    }, 350);

    return function stopAnimation(nextLabel) {
        clearInterval(timer);
        if (typeof nextLabel === 'string') {
            button.textContent = nextLabel;
        }
    };
}

function renderDemoRunStatus(status) {
    if (!demoRunLogEl || !status) return;
    const skipped = status.skipped || 0;
    const header = `status=${status.status} processed=${status.processed}/${status.total} success=${status.success} skipped=${skipped} failed=${status.failed}`;
    const lines = [header].concat(status.logs || []);
    demoRunLogEl.textContent = lines.join('\n');
    demoRunLogEl.scrollTop = demoRunLogEl.scrollHeight;
    if (demoRunProcessedEl) demoRunProcessedEl.textContent = status.processed ?? 0;
    if (demoRunSuccessEl) demoRunSuccessEl.textContent = status.success ?? 0;
    if (demoRunSkippedEl) demoRunSkippedEl.textContent = skipped;
    if (demoRunFailedEl) demoRunFailedEl.textContent = status.failed ?? 0;
}

async function loadDemoEmails() {
    const grid = document.querySelector('#demo-grid');
    if (!grid) return;
    try {
        const response = await fetch(`${API_BASE_URL}/api/demo-emails`, { cache: 'no-store' });
        const emails = await response.json();
        grid.innerHTML = '';
        if (!emails.length) {
            grid.innerHTML = '<div class="demo-empty">No demo emails yet. Run Demo Generate first.</div>';
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

async function runDemoGenerate() {
    if (!demoGenerateBtn) return;
    const originalHTML = demoGenerateBtn.innerHTML;
    const stopGeneratingDots = startButtonDotAnimation(demoGenerateBtn, 'Generating');
    demoGenerateBtn.disabled = true;
    try {
        const response = await fetch(`${API_BASE_URL}/api/demo-generate`, { method: 'POST' });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(result.detail || 'Demo generation failed');
        }
        stopGeneratingDots('Demo Emails Ready');
        appendDemoRunLog(`Generated ${result.count || 0} demo emails.`);
        if (DEMO_MODE) {
            await loadDemoEmails();
        }
        setTimeout(() => {
            demoGenerateBtn.innerHTML = originalHTML;
            demoGenerateBtn.disabled = false;
        }, 1500);
    } catch (error) {
        stopGeneratingDots('Failed');
        setTimeout(() => {
            demoGenerateBtn.innerHTML = originalHTML;
            demoGenerateBtn.disabled = false;
        }, 2000);
        showError(error.message || 'Demo generation failed.');
    }
}

async function runDemoParse() {
    if (!demoParseBtn) return;
    const originalHTML = demoParseBtn.innerHTML;
    demoParseBtn.textContent = 'Starting Parse...';
    demoParseBtn.disabled = true;

    if (demoParsePollTimer) {
        clearInterval(demoParsePollTimer);
        demoParsePollTimer = null;
    }

    try {
        const forceParam = demoForceToggle && demoForceToggle.checked ? '?force_reprocess=true' : '';
        const response = await fetch(`${API_BASE_URL}/api/demo-parse${forceParam}`, { method: 'POST' });
        const result = await response.json().catch(() => ({}));
        if (!response.ok || !result.run_id) {
            throw new Error(result.detail || 'Demo parse failed to start');
        }
        activeDemoRunId = result.run_id;
        demoParseBtn.textContent = 'Parsing...';
        appendDemoRunLog(`Started demo parse run ${activeDemoRunId}.`);
        startDemoParsePolling(originalHTML);
    } catch (error) {
        demoParseBtn.textContent = 'Failed';
        setTimeout(() => {
            demoParseBtn.innerHTML = originalHTML;
            demoParseBtn.disabled = false;
        }, 2000);
        showError(error.message || 'Demo parse failed.');
    }
}

function startDemoParsePolling(originalHTML) {
    if (!activeDemoRunId) return;
    demoParsePollTimer = setInterval(async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/api/demo-parse-status?run_id=${encodeURIComponent(activeDemoRunId)}`, {
                cache: 'no-store'
            });
            const result = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(result.detail || 'Could not fetch parse status');
            }
            renderDemoRunStatus(result);
            if (result.status === 'completed' || result.status === 'failed') {
                clearInterval(demoParsePollTimer);
                demoParsePollTimer = null;
                if (result.status === 'completed') {
                    demoParseBtn.textContent = 'Parse Complete';
                    await loadDashboardData();
                    if (DEMO_MODE) {
                        await loadDemoEmails();
                    }
                } else {
                    demoParseBtn.textContent = 'Parse Failed';
                }
                setTimeout(() => {
                    if (!demoParseBtn) return;
                    demoParseBtn.innerHTML = originalHTML;
                    demoParseBtn.disabled = false;
                }, 2000);
            }
        } catch (error) {
            clearInterval(demoParsePollTimer);
            demoParsePollTimer = null;
            if (demoParseBtn) {
                demoParseBtn.textContent = 'Poll Failed';
                setTimeout(() => {
                    demoParseBtn.innerHTML = originalHTML;
                    demoParseBtn.disabled = false;
                }, 2000);
            }
            showError(error.message || 'Could not poll demo parse status.');
        }
    }, 1200);
}

let _clearUndoTimer = null;
let _clearUndoSnapshot = null;

async function clearAllTransactions() {
    if (!DEMO_MODE && !await hasActiveAuthSession()) {
        handleAuthRequired();
        return;
    }

    // Cancel any pending clear
    if (_clearUndoTimer) {
        clearTimeout(_clearUndoTimer);
        _clearUndoTimer = null;
        _clearUndoSnapshot = null;
    }

    // Snapshot and optimistically clear the UI
    _clearUndoSnapshot = [...allTransactions];
    allTransactions = [];
    renderTransactionsTable();
    renderExpensePreview([]);
    renderSpendingTrends([]);
    setSyncStatus('Cleared', 'Tap Undo within 5 seconds to restore.');

    showUndoToast('All transactions cleared.', function() {
        if (_clearUndoTimer) { clearTimeout(_clearUndoTimer); _clearUndoTimer = null; }
        allTransactions = _clearUndoSnapshot || [];
        _clearUndoSnapshot = null;
        renderTransactionsTable();
        renderExpensePreview(allTransactions);
        renderSpendingTrends(allTransactions);
        setSyncStatus('Restored', 'Transactions have been restored.');
    });

    _clearUndoTimer = setTimeout(async function() {
        _clearUndoTimer = null;
        _clearUndoSnapshot = null;
        try {
            const endpoint = DEMO_MODE ? '/api/demo/clear' : '/api/transactions/clear';
            const response = await authFetch(`${API_BASE_URL}${endpoint}`, { method: 'DELETE' });
            const result = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(result.detail || 'Clear failed');
            setSyncStatus('Transactions cleared', 'Dashboard is empty until the next sync.');
        } catch (error) {
            loadDashboardData();
            showError(error.message || 'Could not clear transactions.');
        }
    }, 5000);
}

function buildTransactionSignature(transactions) {
    if (!transactions || !transactions.length) return '0:0';
    const count = transactions.length;
    const ids = transactions.map(function(t) {
        return String(t.id || '');
    }).sort();
    return `${count}:${ids[ids.length - 1] || ''}`;
}

function startSyncRefreshLoop(previousSignature, originalHTML) {
    if (syncPollTimer) { clearInterval(syncPollTimer); syncPollTimer = null; }
    const start = Date.now();

    syncPollTimer = setInterval(async function() {
        try {
            // Poll sync status if we have a run_id
            if (syncRunId) {
                try {
                    const statusResp = await authFetch(`${API_BASE_URL}/api/sync-status?run_id=${encodeURIComponent(syncRunId)}`, { cache: 'no-store' });
                    if (statusResp.ok) {
                        const statusData = await statusResp.json().catch(() => ({}));
                        const msg = statusData.message || '';
                        if (msg) setSyncStatus('Syncing…', msg);
                        if (statusData.status === 'completed' || statusData.status === 'failed') {
                            const failed = statusData.status === 'failed';
                            syncRunId = null;
                            clearInterval(syncPollTimer);
                            syncPollTimer = null;
                            await loadDashboardData();
                            syncBtn.textContent = failed ? 'Sync failed' : 'Updated';
                            setSyncStatus(
                                failed ? 'Sync failed' : 'New receipts loaded',
                                failed ? (statusData.message || 'Sync did not complete.') : `${allTransactions.length} receipts ready.`
                            );
                            setTimeout(function() { syncBtn.innerHTML = originalHTML; syncBtn.disabled = false; }, 1800);
                            return;
                        }
                    }
                } catch(e) { /* status poll failed silently — fall back to signature poll */ }
            }

            // Fallback: check if new transactions appeared
            await loadDashboardData();
            const nextSignature = buildTransactionSignature(allTransactions);
            if (nextSignature !== previousSignature) {
                clearInterval(syncPollTimer);
                syncPollTimer = null;
                syncRunId = null;
                syncBtn.textContent = 'Updated';
                setSyncStatus('New receipts loaded', `${allTransactions.length} receipts ready.`);
                setTimeout(function() { syncBtn.innerHTML = originalHTML; syncBtn.disabled = false; }, 1500);
                return;
            }
            if (Date.now() - start > 90000) {
                clearInterval(syncPollTimer);
                syncPollTimer = null;
                syncRunId = null;
                syncBtn.textContent = 'Sync complete';
                setSyncStatus('Sync complete', 'No new receipts detected.');
                setTimeout(function() { syncBtn.innerHTML = originalHTML; syncBtn.disabled = false; }, 1500);
            }
        } catch (error) {
            console.error('Sync refresh loop failed:', error);
        }
    }, 3000);
}

async function buildChartFromTable() {
    if (!allTransactions.length) {
        await loadDashboardData();
    }
    const csv = generateCsvFromTransactions(allTransactions);
    if (!csv) {
        showError('No transactions available to chart.');
        return;
    }
    try {
        const response = await fetch(`${API_BASE_URL}/api/vendor-pie`, {
            method: 'POST',
            headers: { 'Content-Type': 'text/csv' },
            body: csv
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(result.detail || 'Chart generation failed');
        }
        if (csvChartImg && result.image_base64) {
            csvChartImg.src = `data:image/png;base64,${result.image_base64}`;
            csvChartImg.style.display = 'block';
        }
        if (csvChartCanvas) {
            csvChartCanvas.style.display = 'none';
        }
        if (csvLegend && Array.isArray(result.breakdown)) {
            const colors = Array.isArray(result.colors) && result.colors.length ? result.colors : getChartColors();
            csvLegend.innerHTML = '';
            result.breakdown.forEach((item, index) => {
                const color = colors[index % colors.length];
                const div = document.createElement('div');
                div.className = 'csv-legend-item';
                div.innerHTML = `
                    <span class="csv-legend-swatch" style="background:${color}"></span>
                    <span class="csv-legend-label">${item.vendor}</span>
                    <span class="csv-legend-meta">${item.percent.toFixed(1)}% ($${Number(item.total).toFixed(2)})</span>
                `;
                csvLegend.appendChild(div);
            });
        }
        if (!result.image_base64) {
            throw new Error('Chart image missing from server response');
        }
    } catch (error) {
        console.error(error);
        // Fallback: client-side pie chart if server fails
        const entries = computeVendorTotals(allTransactions);
        if (entries.length && csvChartCanvas) {
            csvChartCanvas.style.display = 'block';
            if (csvChartImg) csvChartImg.style.display = 'none';
            drawPieChart(csvChartCanvas, csvLegend, entries);
        } else {
            showError(error.message || 'Could not build chart.');
        }
    }
}

function computeVendorTotals(transactions) {
    const totals = {};
    (transactions || []).forEach(tx => {
        const vendor = (tx.vendor || 'Unknown').trim();
        const amount = Number(tx.amount || 0);
        if (!Number.isFinite(amount) || amount <= 0) return;
        totals[vendor] = (totals[vendor] || 0) + amount;
    });
    return Object.entries(totals).sort((a, b) => b[1] - a[1]);
}

function getChartColors() {
    return [
        '#ef4444', '#f97316', '#f59e0b', '#84cc16', '#10b981',
        '#14b8a6', '#06b6d4', '#0ea5e9', '#6366f1', '#8b5cf6',
        '#d946ef', '#ec4899'
    ];
}

function buildSpendPieChart(csvText) {
    if (!csvChartCanvas || !csvLegend) return;
    const parsed = parseCsv(csvText);
    if (!parsed.headers.length) {
        showError('CSV is empty or missing headers.');
        return;
    }
    const headerMap = {};
    parsed.headers.forEach((h, i) => {
        headerMap[h.toLowerCase()] = i;
    });
    const amountIndex = findHeaderIndex(headerMap, ['amount', 'total', 'price']);
    const vendorIndex = findHeaderIndex(headerMap, ['vendor', 'merchant', 'store']);
    const categoryIndex = findHeaderIndex(headerMap, ['category', 'type']);
    const groupBy = csvGroupSelect ? csvGroupSelect.value : 'vendor';
    const keyIndex = groupBy === 'category' && categoryIndex != null ? categoryIndex : vendorIndex;
    if (amountIndex == null || keyIndex == null) {
        showError('CSV must include Vendor and Amount columns (and Category if grouping by category).');
        return;
    }

    const totals = {};
    parsed.rows.forEach(row => {
        const rawAmount = (row[amountIndex] || '').toString();
        const amount = Number(rawAmount.replace(/[$,]/g, ''));
        if (!Number.isFinite(amount) || amount <= 0) return;
        let key = (row[keyIndex] || '').toString().trim();
        if (!key) key = 'Unknown';
        totals[key] = (totals[key] || 0) + amount;
    });

    const entries = Object.entries(totals).sort((a, b) => b[1] - a[1]);
    if (!entries.length) {
        showError('No valid spending rows found in CSV.');
        return;
    }

    drawPieChart(csvChartCanvas, csvLegend, entries);
}

function parseCsv(text) {
    const lines = text.split(/\r?\n/).filter(l => l.trim() !== '');
    if (!lines.length) return { headers: [], rows: [] };
    const headers = parseCsvLine(lines[0]).map(h => h.trim());
    const rows = lines.slice(1).map(line => parseCsvLine(line));
    return { headers, rows };
}

function parseCsvLine(line) {
    const out = [];
    let current = '';
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
        const ch = line[i];
        if (ch === '"' && line[i + 1] === '"') {
            current += '"';
            i++;
            continue;
        }
        if (ch === '"') {
            inQuotes = !inQuotes;
            continue;
        }
        if (ch === ',' && !inQuotes) {
            out.push(current);
            current = '';
            continue;
        }
        current += ch;
    }
    out.push(current);
    return out;
}

function findHeaderIndex(headerMap, candidates) {
    for (const key of candidates) {
        if (Object.prototype.hasOwnProperty.call(headerMap, key)) {
            return headerMap[key];
        }
    }
    return null;
}

function drawPieChart(canvas, legendEl, entries) {
    const ctx = canvas.getContext('2d');
    const total = entries.reduce((sum, [, value]) => sum + value, 0);
    canvas.width = 360;
    canvas.height = 360;
    const colors = [
        '#ef4444', '#f97316', '#f59e0b', '#84cc16', '#10b981',
        '#14b8a6', '#06b6d4', '#0ea5e9', '#6366f1', '#8b5cf6',
        '#d946ef', '#ec4899'
    ];

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    const radius = Math.min(centerX, centerY) - 10;
    let startAngle = -Math.PI / 2;

    entries.forEach(([label, value], index) => {
        const slice = (value / total) * Math.PI * 2;
        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.arc(centerX, centerY, radius, startAngle, startAngle + slice);
        ctx.closePath();
        ctx.fillStyle = colors[index % colors.length];
        ctx.fill();
        startAngle += slice;
    });

    legendEl.innerHTML = '';
    entries.forEach(([label, value], index) => {
        const percent = ((value / total) * 100).toFixed(1);
        const item = document.createElement('div');
        item.className = 'csv-legend-item';
        item.innerHTML = `
            <span class="csv-legend-swatch" style="background:${colors[index % colors.length]}"></span>
            <span class="csv-legend-label">${label}</span>
            <span class="csv-legend-meta">${percent}% ($${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})</span>
        `;
        legendEl.appendChild(item);
    });
}

function renderSpendingTrends(transactions) {
    const canvas = document.querySelector('#trends-chart');
    const emptyEl = document.querySelector('#trends-empty');
    if (!canvas) return;

    const monthlyTotals = {};
    (transactions || []).forEach(function(t) {
        const parts = parseIsoDateParts(t.date);
        if (!parts) return;
        const amount = Number(t.amount) || 0;
        if (amount <= 0) return;
        const key = `${parts.year}-${String(parts.month).padStart(2, '0')}`;
        monthlyTotals[key] = (monthlyTotals[key] || 0) + amount;
    });

    const entries = Object.entries(monthlyTotals).sort((a, b) => a[0].localeCompare(b[0]));

    if (!entries.length) {
        canvas.style.display = 'none';
        if (emptyEl) emptyEl.style.display = 'block';
        return;
    }

    if (emptyEl) emptyEl.style.display = 'none';
    canvas.style.display = 'block';

    const dpr = window.devicePixelRatio || 1;
    const containerWidth = canvas.parentElement ? canvas.parentElement.clientWidth - 48 : 800;
    const W = Math.max(containerWidth, 300);
    const H = 220;
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    canvas.style.width = W + 'px';
    canvas.style.height = H + 'px';

    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, W, H);

    const padL = 60, padR = 20, padT = 20, padB = 50;
    const chartW = W - padL - padR;
    const chartH = H - padT - padB;
    const maxVal = Math.max(...entries.map(e => e[1]));
    const barW = Math.max(8, Math.floor((chartW / entries.length) * 0.6));
    const gap = chartW / entries.length;

    // Y-axis grid lines
    ctx.strokeStyle = 'rgba(255,255,255,0.06)';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
        const y = padT + chartH - (chartH * i / 4);
        ctx.beginPath();
        ctx.moveTo(padL, y);
        ctx.lineTo(W - padR, y);
        ctx.stroke();
        ctx.fillStyle = 'rgba(255,255,255,0.3)';
        ctx.font = '10px IBM Plex Mono, monospace';
        ctx.textAlign = 'right';
        const label = formatCurrency(maxVal * i / 4, { whole: true });
        ctx.fillText(label, padL - 6, y + 4);
    }

    // Bars
    entries.forEach(function([key, val], i) {
        const barH = maxVal > 0 ? (val / maxVal) * chartH : 0;
        const x = padL + gap * i + (gap - barW) / 2;
        const y = padT + chartH - barH;

        const grad = ctx.createLinearGradient(0, y, 0, padT + chartH);
        grad.addColorStop(0, 'rgba(217, 246, 103, 0.9)');
        grad.addColorStop(1, 'rgba(74, 222, 128, 0.4)');
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.roundRect ? ctx.roundRect(x, y, barW, barH, [4, 4, 0, 0]) : ctx.rect(x, y, barW, barH);
        ctx.fill();

        // Month label
        const [yr, mo] = key.split('-');
        const monthLabel = new Date(Number(yr), Number(mo) - 1).toLocaleString('en-US', { month: 'short' });
        ctx.fillStyle = 'rgba(255,255,255,0.45)';
        ctx.font = '10px IBM Plex Sans, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(monthLabel, x + barW / 2, padT + chartH + 16);

        // Year label only on Jan or first bar
        if (mo === '01' || i === 0) {
            ctx.fillStyle = 'rgba(255,255,255,0.22)';
            ctx.font = '9px IBM Plex Sans, sans-serif';
            ctx.fillText(yr, x + barW / 2, padT + chartH + 28);
        }
    });
}

function generateCsvFromTransactions(transactions) {
    let csv = 'Date,Vendor,Amount,Tax,Category,Status\n';
    let hasRows = false;

    (transactions || []).forEach(tx => {
        const date = tx.date || '';
        const vendor = tx.vendor || '';
        const amount = Number(tx.amount || 0).toFixed(2);
        const tax = Number(tx.tax || 0).toFixed(2);
        const category = tx.category || '';
        const status = 'Processed';

        const rowData = [date, vendor, amount, tax, category, status].map(content => {
            const text = String(content).trim().replace(/\n/g, ' ').replace(/\s+/g, ' ');
            return text.includes(',') ? `"${text}"` : text;
        });
        csv += rowData.join(',') + '\n';
        hasRows = true;
    });

    return hasRows ? csv : '';
}

// Export transactions to CSV
function exportToCSV() {
    const csv = generateCsvFromTransactions(allTransactions);
    if (!csv) {
        showError('No transactions to export.');
        return;
    }

    // Create download link
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `transactions_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);

    // Update chart from the same CSV data
    buildSpendPieChart(csv);
    
    // Show feedback
    if (exportBtn) {
        const originalText = exportBtn.innerHTML;
        exportBtn.textContent = 'Exported';
        setTimeout(() => {
            exportBtn.innerHTML = originalText;
        }, 2000);
    }
}

function openEditModal(row) {
    if (!editModal) return;
    const id = String(row.dataset.transactionId || '');
    if (!id) return;
    const tx = allTransactions.find(t => String(t.id) === id);
    if (!tx) return;
    activeTransactionId = id;

    if (editVendorInput) editVendorInput.value = tx.vendor || '';
    if (editAmountInput) editAmountInput.value = Number(tx.amount || 0).toFixed(2);
    if (editTaxInput) editTaxInput.value = Number(tx.tax || 0).toFixed(2);
    if (editCategoryInput) editCategoryInput.value = tx.category || '';
    if (editDateInput) {
        const parts = parseIsoDateParts(tx.date);
        if (parts) {
            const mm = String(parts.month).padStart(2, '0');
            const dd = String(parts.day).padStart(2, '0');
            editDateInput.value = `${parts.year}-${mm}-${dd}`;
        } else {
            const d = new Date(tx.date);
            const yyyy = d.getFullYear();
            const mm = String(d.getMonth() + 1).padStart(2, '0');
            const dd = String(d.getDate()).padStart(2, '0');
            editDateInput.value = `${yyyy}-${mm}-${dd}`;
        }
    }

    editModal.hidden = false;
    editModal.style.display = 'flex';
    editModal.classList.add('show');
    editModal.setAttribute('aria-hidden', 'false');
}

function closeEditModal() {
    if (!editModal) return;
    editModal.classList.remove('show');
    editModal.style.display = 'none';
    editModal.hidden = true;
    editModal.setAttribute('aria-hidden', 'true');
    activeTransactionId = null;
}

async function saveTransactionEdits() {
    if (!activeTransactionId) return;
    const payload = {
        vendor: editVendorInput ? editVendorInput.value.trim() : undefined,
        amount: editAmountInput ? editAmountInput.value : undefined,
        tax: editTaxInput ? editTaxInput.value : undefined,
        date: editDateInput ? editDateInput.value : undefined,
        category: editCategoryInput ? editCategoryInput.value : undefined,
    };
    try {
        const endpoint = DEMO_MODE ? `/api/demo/transactions/${activeTransactionId}` : `/api/transactions/${activeTransactionId}`;
        const response = await (DEMO_MODE ? fetch : authFetch)(`${API_BASE_URL}${endpoint}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(result.detail || 'Update failed');
        }
        await loadDashboardData();
        closeEditModal();
    } catch (error) {
        showError(error.message || 'Could not update transaction.');
    }
}

async function deleteTransaction() {
    if (!activeTransactionId) return;
    try {
        const endpoint = DEMO_MODE ? `/api/demo/transactions/${activeTransactionId}` : `/api/transactions/${activeTransactionId}`;
        const response = await (DEMO_MODE ? fetch : authFetch)(`${API_BASE_URL}${endpoint}`, {
            method: 'DELETE'
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(result.detail || 'Delete failed');
        }
        await loadDashboardData();
        closeEditModal();
    } catch (error) {
        showError(error.message || 'Could not delete transaction.');
    }
}

// Show error message
function showError(message) {
    showNotification(message, 'error');
}

function showSuccess(message) {
    showNotification(message, 'success');
}

function showNotification(message, variant) {
    const isSuccess = variant === 'success';
    if (isSuccess) {
        console.log(message);
    } else {
        console.error(message);
    }

    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: ${isSuccess ? 'linear-gradient(135deg, #22c55e, #15803d)' : 'linear-gradient(135deg, #ef4444, #dc2626)'};
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 12px;
        box-shadow: ${isSuccess ? '0 8px 25px rgba(34, 197, 94, 0.3)' : '0 8px 25px rgba(239, 68, 68, 0.3)'};
        z-index: 10000;
        max-width: 400px;
        font-weight: 600;
    `;
    notification.textContent = `${isSuccess ? 'Success' : 'Notice'}: ${message}`;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.remove();
    }, 5000);
}

// Console welcome message
console.log('%c Receipt Automation Dashboard ', 'background: #d946a6; color: white; padding: 10px; font-size: 16px; font-weight: bold;');
console.log('%c Connected to API at ' + API_BASE_URL, 'color: #9333ea; font-size: 12px;');
console.log('%c Press Ctrl+K to search, Ctrl+S to sync ', 'color: #3b82f6; font-size: 12px;');
