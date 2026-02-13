const API_BASE_URL = 'https://autotax-xwly.onrender.com';

async function loadDemoEmails() {
    const grid = document.querySelector('#demo-grid');
    if (!grid) return;
    try {
        const response = await fetch(`${API_BASE_URL}/api/demo-emails`, { cache: 'no-store' });
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
