// Receipt Automation Dashboard JavaScript

// API Configuration
const API_BASE_URL = 'http://localhost:8000';

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
let demoBtn;
let demoViewBtn;
let clearBtn;

// Cached transactions and sort state (so we can re-sort without re-fetching)
let allTransactions = [];
let sortColumn = 'date';
let sortDirection = 'desc'; // 'asc' = least to greatest, 'desc' = greatest to least
let syncPollTimer = null;

document.addEventListener('DOMContentLoaded', function() {
    // Initialize DOM references
    searchInput = document.querySelector('.search-input');
    syncBtn = document.querySelector('.btn-action-primary');
    exportBtn = document.querySelector('.btn-action');
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
    demoBtn = document.querySelector('.btn-demo');
    demoViewBtn = document.querySelector('.btn-demo-view');
    clearBtn = document.querySelector('.btn-clear');
    
    // Initialize animations
    initAnimations();
    
    // Setup event listeners
    setupEventListeners();
    
    // Load real data from API
    loadDashboardData();
    
    // Auto-refresh table and stats every 10s so new syncs show up without manual refresh
    setInterval(loadDashboardData, 10000);
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
    // Search input
    if (searchInput) {
        searchInput.addEventListener('input', function(e) {
            filterTransactions(e.target.value);
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
        // Ctrl/Cmd + K for search
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            if (searchInput) searchInput.focus();
        }
        
        // Ctrl/Cmd + S for sync
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
            e.preventDefault();
            syncEmails();
        }
    });

    // CSV chart controls
    if (csvBuildBtn) {
        csvBuildBtn.addEventListener('click', function() {
            buildChartFromTable();
        });
    }

    if (demoBtn) {
        demoBtn.addEventListener('click', function() {
            runDemoSync();
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
}

// Load all dashboard data from API
async function loadDashboardData() {
    console.log('📊 Loading dashboard data from API...');
    
    try {
        // Load transactions, stats, and top vendors in parallel
        await Promise.all([
            loadTransactions(),
            loadStats(),
            loadTopVendors()
        ]);
        
        console.log('✅ Dashboard data loaded successfully');
    } catch (error) {
        console.error('❌ Error loading dashboard:', error);
        showError('Failed to load dashboard data. Make sure the API is running on http://localhost:8000');
    }
}

// Load transactions from API
async function loadTransactions() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/transactions`, { cache: 'no-store' });
        
        if (!response.ok) {
            throw new Error(`API returned ${response.status}`);
        }
        
        const transactions = await response.json();
        // Strip any zero-amount rows so the table never shows $0.00 (safety net)
        allTransactions = (transactions || []).filter(function(t) {
            const amt = Number(t.amount);
            return t.amount != null && !Number.isNaN(amt) && amt !== 0 && Math.abs(amt) >= 0.0001;
        });
        
        console.log(`📧 Loaded ${allTransactions.length} transactions`);
        
        if (tableBody) {
            renderTransactionsTable();
            updateSortArrows();
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
        const response = await fetch(`${API_BASE_URL}/api/stats`, { cache: 'no-store' });
        
        if (!response.ok) {
            throw new Error(`API returned ${response.status}`);
        }
        
        const stats = await response.json();
        
        console.log('📊 Stats loaded:', stats);
        
        // Update stat cards
        updateStatCards(stats);
        
        return stats;
    } catch (error) {
        console.error('Error loading stats:', error);
        throw error;
    }
}

// Load top vendors from API
async function loadTopVendors() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/top-vendors`, { cache: 'no-store' });
        
        if (!response.ok) {
            throw new Error(`API returned ${response.status}`);
        }
        
        const vendors = await response.json();
        
        console.log('🏪 Top vendors loaded:', vendors);
        
        // Update vendor cards
        updateVendorCards(vendors);
        
        return vendors;
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
            totalSpentValue.textContent = `$${stats.total_spent.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
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
            avgTransactionValue.textContent = `$${stats.avg_transaction.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
        }
    }
}

// Sort and render table from cached allTransactions
function renderTransactionsTable() {
    if (!tableBody) return;
    const sorted = sortTransactions([...allTransactions]);
    tableBody.innerHTML = '';
    sorted.forEach(transaction => {
        const row = createTransactionRow(transaction);
        tableBody.appendChild(row);
    });
    tableBody.querySelectorAll('.edit-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            const id = Number(this.getAttribute('data-id'));
            if (!id) return;
            const row = this.closest('tr');
            if (row) {
                openEditModal(row);
            }
        });
    });
    // Re-apply search filter if there is one
    if (searchInput && searchInput.value.trim()) {
        filterTransactions(searchInput.value.trim());
    }
}

function sortTransactions(transactions) {
    const mult = sortDirection === 'asc' ? 1 : -1;
    return transactions.sort((a, b) => {
        let va, vb;
        if (sortColumn === 'date') {
            va = new Date(a.date).getTime();
            vb = new Date(b.date).getTime();
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
    const date = new Date(transaction.date);
    const dateFormatted = date.toLocaleDateString('en-US', { month: 'short', day: '2-digit' });
    const yearFormatted = date.getFullYear();
    
    // Determine vendor icon and color
    const vendorInfo = getVendorInfo(transaction.vendor);
    
    // Determine parser badge
    const parserBadge = getParserBadge(transaction.vendor);
    
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
                    <span class="vendor-name">${transaction.vendor}</span>
                    <span class="vendor-email">${transaction.email_id.substring(0, 20)}...</span>
                </div>
            </div>
        </td>
        <td>
            <div class="amount-value">$${transaction.amount.toFixed(2)}</div>
        </td>
        <td>
            <span class="tax-value">$${(Number(transaction.tax) || 0).toFixed(2)}</span>
        </td>
        <td>
            ${parserBadge}
        </td>
        <td>
            <span class="status status-success">
                <span class="status-icon">✓</span>
                Processed
            </span>
        </td>
        <td>
            <button class="edit-btn" type="button" data-id="${transaction.id}">Edit</button>
        </td>
    `;
    
    return row;
}

// Get vendor icon and color class
function getVendorInfo(vendor) {
    const vendorLower = vendor.toLowerCase();
    
    if (vendorLower.includes('amazon')) {
        return { icon: '🛒', colorClass: 'amazon-color' };
    } else if (vendorLower.includes('uber') || vendorLower.includes('eats')) {
        return { icon: '🍕', colorClass: 'ubereats-color' };
    } else if (vendorLower.includes('starbucks')) {
        return { icon: '☕', colorClass: 'starbucks-color' };
    } else if (vendorLower.includes('best buy') || vendorLower.includes('bestbuy')) {
        return { icon: '🏬', colorClass: 'bestbuy-color' };
    } else if (vendorLower.includes('mcdonald')) {
        return { icon: '🍔', colorClass: 'mcdonalds-color' };
    } else if (vendorLower.includes('paypal')) {
        return { icon: '💳', colorClass: 'bestbuy-color' };
    } else {
        return { icon: '🏪', colorClass: 'amazon-color' };
    }
}

// Get parser badge based on vendor
function getParserBadge(vendor) {
    const vendorLower = vendor.toLowerCase();
    
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
function updateVendorCards(vendors) {
    const vendorCards = document.querySelectorAll('.vendor-card-new');
    
    // Get emoji map
    const vendorEmojis = {
        'amazon': '🛒',
        'ubereats': '🍕',
        'uber eats': '🍕',
        'starbucks': '☕',
        'best buy': '🏬',
        'bestbuy': '🏬',
        'paypal': '💳',
        'mcdonald': '🍔'
    };
    
    vendorCards.forEach((card, index) => {
        if (index >= vendors.length) {
            card.classList.add('vendor-card-empty');
            return;
        }
        card.classList.remove('vendor-card-empty');
        const vendor = vendors[index];

        // Find emoji
        let emoji = '🏪';
        for (const [key, value] of Object.entries(vendorEmojis)) {
            if (vendor.vendor.toLowerCase().includes(key)) {
                emoji = value;
                break;
            }
        }

        // Update vendor name
        const nameEl = card.querySelector('.vendor-card-name');
        if (nameEl) nameEl.textContent = vendor.vendor;

        // Update emoji
        const emojiEl = card.querySelector('.vendor-logo-large');
        if (emojiEl) emojiEl.textContent = emoji;

        // Update amount
        const amountEl = card.querySelector('.vendor-card-amount');
        if (amountEl) amountEl.textContent = `$${vendor.total.toLocaleString('en-US', {minimumFractionDigits: 2})}`;

        // Update transaction count
        const countEl = card.querySelector('.vendor-card-transactions');
        if (countEl) countEl.textContent = `${vendor.count} transaction${vendor.count !== 1 ? 's' : ''}`;
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
    
    const originalHTML = syncBtn.innerHTML;
    const previousSignature = buildTransactionSignature(allTransactions);
    
    syncBtn.innerHTML = '<span>⏳</span> Starting sync...';
    syncBtn.disabled = true;
    
    try {
        console.log('🔄 Starting email sync...');
        
        const response = await fetch(`${API_BASE_URL}/api/sync`, {
            method: 'POST',
            headers: buildAuthHeaders()
        });
        
        const result = await response.json().catch(() => ({}));
        
        if (!response.ok) {
            const detail = result.detail || (typeof result.detail === 'string' ? result.detail : `API returned ${response.status}`);
            throw new Error(detail);
        }
        
        console.log('✅ Sync started:', result);
        
        syncBtn.innerHTML = '<span>⏳</span> Syncing...';
        startSyncRefreshLoop(previousSignature, originalHTML);
        
    } catch (error) {
        console.error('❌ Sync failed:', error);
        syncBtn.innerHTML = '<span>⚠</span> Sync Failed';
        
        setTimeout(() => {
            syncBtn.innerHTML = originalHTML;
            syncBtn.disabled = false;
        }, 2000);
        
        const message = error.message || 'Email sync failed. Make sure the API is running and Gmail is configured.';
        showError(message);
    }
}

function buildAuthHeaders() {
    const headers = {};
    const key = localStorage.getItem('SYNC_API_KEY');
    if (key) {
        headers['X-API-Key'] = key;
    }
    return headers;
}

async function runDemoSync() {
    if (!demoBtn) return;
    const originalHTML = demoBtn.innerHTML;
    demoBtn.innerHTML = '<span>⏳</span> Demo...';
    demoBtn.disabled = true;
    try {
        const response = await fetch(`${API_BASE_URL}/api/demo-sync`, { method: 'POST' });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(result.detail || 'Demo sync failed');
        }
        demoBtn.innerHTML = '<span>✓</span> Demo Ready';
        await loadDashboardData();
        setTimeout(() => {
            demoBtn.innerHTML = originalHTML;
            demoBtn.disabled = false;
        }, 2000);
    } catch (error) {
        demoBtn.innerHTML = '<span>⚠</span> Failed';
        setTimeout(() => {
            demoBtn.innerHTML = originalHTML;
            demoBtn.disabled = false;
        }, 2000);
        showError(error.message || 'Demo sync failed.');
    }
}

async function clearAllTransactions() {
    if (!clearBtn) return;
    if (!confirm('Clear all transactions from the database? This cannot be undone.')) {
        return;
    }
    const originalHTML = clearBtn.innerHTML;
    clearBtn.innerHTML = '<span>⏳</span> Clearing...';
    clearBtn.disabled = true;
    try {
        const response = await fetch(`${API_BASE_URL}/api/transactions/clear`, {
            method: 'DELETE',
            headers: buildAuthHeaders()
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(result.detail || 'Clear failed');
        }
        clearBtn.innerHTML = '<span>✓</span> Cleared';
        await loadDashboardData();
        setTimeout(() => {
            clearBtn.innerHTML = originalHTML;
            clearBtn.disabled = false;
        }, 2000);
    } catch (error) {
        clearBtn.innerHTML = '<span>⚠</span> Failed';
        setTimeout(() => {
            clearBtn.innerHTML = originalHTML;
            clearBtn.disabled = false;
        }, 2000);
        showError(error.message || 'Could not clear transactions.');
    }
}

function buildTransactionSignature(transactions) {
    if (!transactions || !transactions.length) return '0:0';
    const count = transactions.length;
    const maxId = Math.max.apply(null, transactions.map(t => Number(t.id) || 0));
    return `${count}:${maxId}`;
}

function startSyncRefreshLoop(previousSignature, originalHTML) {
    if (syncPollTimer) {
        clearInterval(syncPollTimer);
        syncPollTimer = null;
    }
    const start = Date.now();
    syncPollTimer = setInterval(async () => {
        try {
            await loadDashboardData();
            const nextSignature = buildTransactionSignature(allTransactions);
            if (nextSignature !== previousSignature) {
                clearInterval(syncPollTimer);
                syncPollTimer = null;
                syncBtn.innerHTML = '<span>✓</span> Updated';
                setTimeout(() => {
                    syncBtn.innerHTML = originalHTML;
                    syncBtn.disabled = false;
                }, 1500);
                return;
            }
            if (Date.now() - start > 90000) {
                clearInterval(syncPollTimer);
                syncPollTimer = null;
                syncBtn.innerHTML = '<span>✓</span> Sync complete';
                setTimeout(() => {
                    syncBtn.innerHTML = originalHTML;
                    syncBtn.disabled = false;
                }, 1500);
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
        exportBtn.innerHTML = '<span>✓</span> Exported!';
        setTimeout(() => {
            exportBtn.innerHTML = originalText;
        }, 2000);
    }
}

function openEditModal(row) {
    if (!editModal) return;
    const id = Number(row.dataset.transactionId);
    if (!id) return;
    const tx = allTransactions.find(t => Number(t.id) === id);
    if (!tx) return;
    activeTransactionId = id;

    if (editVendorInput) editVendorInput.value = tx.vendor || '';
    if (editAmountInput) editAmountInput.value = Number(tx.amount || 0).toFixed(2);
    if (editTaxInput) editTaxInput.value = Number(tx.tax || 0).toFixed(2);
    if (editDateInput) {
        const d = new Date(tx.date);
        const yyyy = d.getFullYear();
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        const dd = String(d.getDate()).padStart(2, '0');
        editDateInput.value = `${yyyy}-${mm}-${dd}`;
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
        date: editDateInput ? editDateInput.value : undefined
    };
    try {
        const response = await fetch(`${API_BASE_URL}/api/transactions/${activeTransactionId}`, {
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
        const response = await fetch(`${API_BASE_URL}/api/transactions/${activeTransactionId}`, {
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
    console.error(message);
    
    // Create error notification
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: linear-gradient(135deg, #ef4444, #dc2626);
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 12px;
        box-shadow: 0 8px 25px rgba(239, 68, 68, 0.3);
        z-index: 10000;
        max-width: 400px;
        font-weight: 600;
    `;
    notification.textContent = `⚠️ ${message}`;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.remove();
    }, 5000);
}

// Console welcome message
console.log('%c Receipt Automation Dashboard ', 'background: #d946a6; color: white; padding: 10px; font-size: 16px; font-weight: bold;');
console.log('%c Connected to API at ' + API_BASE_URL, 'color: #9333ea; font-size: 12px;');
console.log('%c Press Ctrl+K to search, Ctrl+S to sync ', 'color: #3b82f6; font-size: 12px;');
