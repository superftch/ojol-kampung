let dashboardData = null;

function showTab(tabId) {
    document.querySelectorAll('.nav-btn').forEach(b => b.removeAttribute('aria-current'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    const targetBtn = Array.from(document.querySelectorAll('.nav-btn')).find(b => b.getAttribute('onclick') && b.getAttribute('onclick').includes(tabId));
    if (targetBtn) targetBtn.setAttribute('aria-current', 'page');
    const panel = document.getElementById(tabId);
    if (panel) {
        panel.classList.add('active');
        window.scrollTo(0, 0);
        const navigation = targetBtn?.parentElement;
        if (navigation && navigation.scrollWidth > navigation.clientWidth) {
            targetBtn.scrollIntoView({block: 'nearest', inline: 'nearest'});
        }
    }

    if (tabId === 'tab-accounts') loadAccounts();
    if (tabId === 'tab-notifications') switchNotifTab(currentNotifTab);
    if (tabId === 'tab-admin') loadAdminData();
    if (tabId === 'tab-bank-angka') loadBankAngka();
}

function openModal(id) {
    const dialog = document.getElementById(id);
    if (!dialog.open) dialog.showModal();
}

function closeModal(id) {
    document.getElementById(id).close();
}

async function apiFetch(url, options = {}) {
    const res = await fetch(url, options);
    let data = {};
    try {
        data = await res.json();
    } catch (_) {
        // Fallback for non-JSON response bodies (e.g. 500 Internal Server Error)
    }
    if (!res.ok) {
        const msg = data.detail || data.message || `HTTP ${res.status}: ${res.statusText || 'Gagal memproses permintaan'}`;
        throw new Error(msg);
    }
    return data;
}

function escapeHtml(value) {
    const entities = {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'};
    return String(value ?? '').replace(/[&<>"']/g, char => entities[char]);
}

function openCookieModalFor(accId = '', accName = '') {
    const hiddenId = document.getElementById('cookieTargetAccountId');
    const label = document.getElementById('cookieTargetAccountLabel');
    const name = accName || dashboardData?.account?.name;
    hiddenId.value = accId || dashboardData?.account?.id || '';
    label.style.display = name ? 'block' : 'none';
    label.textContent = name ? 'Akun: ' + name : '';
    document.getElementById('cookieInput').value = '';
    document.getElementById('cookieError').hidden = true;
    openModal('cookieModal');
}

async function loadNotifications() {
    try {
        const res = await fetch('/api/notifications');
        const data = await res.json();
        const list = document.getElementById('notificationsList');
        if (!data.notifications || data.notifications.length === 0) {
            list.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 24px;">Belum ada notifikasi akun.</div>';
            updateBadge(0);
            return;
        }
        let unreadCount = 0;
        list.innerHTML = data.notifications.map(n => {
            if (!n.read) unreadCount++;
            const bg = n.is_error ? 'rgba(239, 68, 68, 0.12)' : (n.read ? 'transparent' : 'rgba(59, 130, 246, 0.08)');
            const border = n.is_error ? 'var(--danger)' : (n.read ? 'var(--border)' : 'var(--primary)');
            const text = escapeHtml(n.text).replace(/\n/g, '<br>');
            return `
            <div style="background: ${bg}; border: 1px solid ${border}; border-radius: 8px; padding: 14px; position: relative;">
                <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 6px; display: flex; justify-content: space-between;">
                    <span>${escapeHtml(n.time)} ${n.error_id ? '• ID: ' + escapeHtml(n.error_id) : ''}</span>
                    ${!n.read ? '<span style="background: var(--primary); color: white; border-radius: 4px; padding: 1px 6px; font-size: 10px;">BARU</span>' : ''}
                </div>
                <div style="font-size: 13px; line-height: 1.5; color: var(--text);">${text}</div>
            </div>
            `;
        }).join('');
        updateBadge(unreadCount);
    } catch (e) {
        console.error(e);
    }
}

async function markAllNotificationsRead() {
    try {
        await fetch('/api/notifications/read', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
        await loadNotifications();
    } catch (e) {
        alert('Gagal menandai notifikasi: ' + e.message);
    }
}

function updateBadge(count) {
    const badge = document.getElementById('notifBadge');
    if (badge) {
        if (count > 0) {
            badge.innerText = count;
            badge.style.display = 'inline-block';
        } else {
            badge.style.display = 'none';
        }
    }
}

let currentNotifTab = 'user';
let allAdminNotifications = [];

function openAdminFeed(errorsOnly = false) {
    document.getElementById('searchAdminNotif').value = '';
    document.getElementById('filterAdminNotifUser').value = '';
    document.getElementById('filterAdminNotifAccount').value = '';
    document.getElementById('filterAdminNotifErrorOnly').checked = errorsOnly;
    currentNotifTab = 'admin';
    showTab('tab-notifications');
    document.getElementById('btnSubNotifAdmin').focus();
}

function switchNotifTab(tab) {
    currentNotifTab = tab;
    const pUser = document.getElementById('panelNotifUser');
    const pAdmin = document.getElementById('panelNotifAdmin');
    const bUser = document.getElementById('btnSubNotifUser');
    const bAdmin = document.getElementById('btnSubNotifAdmin');
    if (tab === 'admin') {
        if (pUser) pUser.style.display = 'none';
        if (pAdmin) pAdmin.style.display = 'block';
        if (bUser) { bUser.classList.remove('btn-primary'); bUser.classList.add('btn-secondary'); }
        if (bAdmin) { bAdmin.classList.remove('btn-secondary'); bAdmin.classList.add('btn-primary'); }
        loadAdminNotifications();
    } else {
        if (pUser) pUser.style.display = 'block';
        if (pAdmin) pAdmin.style.display = 'none';
        if (bUser) { bUser.classList.remove('btn-secondary'); bUser.classList.add('btn-primary'); }
        if (bAdmin) { bAdmin.classList.remove('btn-primary'); bAdmin.classList.add('btn-secondary'); }
        loadNotifications();
    }
}

async function loadAdminNotifications() {
    const list = document.getElementById('adminNotificationsList');
    const badge = document.getElementById('adminNotifTotalBadge');
    if (!list) return;
    try {
        list.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 24px;">Memuat notifikasi semua akun dan user...</div>';
        const data = await apiFetch('/api/admin/notifications');
        allAdminNotifications = data.notifications || [];
        if (badge) badge.innerText = `${allAdminNotifications.length} Notifikasi`;
        populateAdminNotifFilters(allAdminNotifications);
        filterAdminNotifs();
    } catch (e) {
        list.innerHTML = `<div style="text-align: center; color: var(--danger); padding: 24px;">⚠️ Gagal memuat notifikasi: ${escapeHtml(e.message)}</div>`;
    }
}

function populateAdminNotifFilters(notifs) {
    const userSelect = document.getElementById('filterAdminNotifUser');
    const accountSelect = document.getElementById('filterAdminNotifAccount');
    if (!userSelect || !accountSelect) return;

    const currentUserVal = userSelect.value;
    const currentAccountVal = accountSelect.value;

    const users = new Map();
    const accounts = new Map();

    notifs.forEach(n => {
        if (n.user) {
            const uKey = n.user.user_id !== undefined && n.user.user_id !== null ? String(n.user.user_id) : (n.user.username || '');
            const uLabel = n.user.username ? `@${n.user.username} (${n.user.name || 'User'})` : (n.user.name || `User #${uKey}`);
            if (uKey && !users.has(uKey)) users.set(uKey, uLabel);
        }
        if (n.account_id) {
            const aKey = String(n.account_id);
            const aLabel = n.account_name ? `${n.account_name} (${aKey.slice(0, 8)})` : `Akun ${aKey.slice(0, 8)}`;
            if (!accounts.has(aKey)) accounts.set(aKey, aLabel);
        }
    });

    userSelect.innerHTML = '<option value="">Semua User (' + users.size + ')</option>' +
        Array.from(users.entries()).map(([k, v]) => `<option value="${escapeHtml(k)}">${escapeHtml(v)}</option>`).join('');
    accountSelect.innerHTML = '<option value="">Semua Akun (' + accounts.size + ')</option>' +
        Array.from(accounts.entries()).map(([k, v]) => `<option value="${escapeHtml(k)}">${escapeHtml(v)}</option>`).join('');

    if (currentUserVal && users.has(currentUserVal)) userSelect.value = currentUserVal;
    if (currentAccountVal && accounts.has(currentAccountVal)) accountSelect.value = currentAccountVal;
}

function filterAdminNotifs() {
    const query = (document.getElementById('searchAdminNotif')?.value || '').toLowerCase().trim();
    const selectedUser = document.getElementById('filterAdminNotifUser')?.value || '';
    const selectedAccount = document.getElementById('filterAdminNotifAccount')?.value || '';
    const errorOnly = document.getElementById('filterAdminNotifErrorOnly')?.checked || false;

    const filtered = allAdminNotifications.filter(n => {
        if (errorOnly && !n.is_error) return false;
        if (selectedUser) {
            const uKey = n.user && n.user.user_id !== undefined && n.user.user_id !== null ? String(n.user.user_id) : (n.user?.username || '');
            if (uKey !== selectedUser) return false;
        }
        if (selectedAccount && String(n.account_id) !== selectedAccount) {
            return false;
        }
        if (query) {
            const text = (n.text || '').toLowerCase();
            const event = (n.event || '').toLowerCase();
            const errId = (n.error_id || '').toLowerCase();
            const accName = (n.account_name || '').toLowerCase();
            const uName = (((n.user?.name || '') + ' ' + (n.user?.username || ''))).toLowerCase();
            if (!text.includes(query) && !event.includes(query) && !errId.includes(query) && !accName.includes(query) && !uName.includes(query)) {
                return false;
            }
        }
        return true;
    });

    renderAdminNotifications(filtered);
}

function renderAdminNotifications(notifs) {
    const list = document.getElementById('adminNotificationsList');
    if (!list) return;
    if (!notifs || notifs.length === 0) {
        list.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 32px; border: 1px dashed var(--border); border-radius: 8px;">Tidak ada notifikasi yang sesuai kriteria filter.</div>';
        return;
    }

    list.innerHTML = notifs.map(n => {
        const isErr = !!n.is_error;
        const bg = isErr ? 'rgba(239, 68, 68, 0.08)' : (n.read ? 'rgba(255, 255, 255, 0.02)' : 'rgba(59, 130, 246, 0.06)');
        const border = isErr ? 'rgba(239, 68, 68, 0.35)' : (n.read ? 'var(--border)' : 'rgba(59, 130, 246, 0.35)');
        const text = escapeHtml(n.text).replace(/\n/g, '<br>');
        const uLabel = n.user?.username ? `@${n.user.username}` : (n.user?.name || `User #${n.owner || '?'}`);
        const accLabel = n.account_name || (n.account_id ? `Akun ${String(n.account_id).slice(0, 8)}` : 'Sistem');

        return `
        <div style="background: ${bg}; border: 1px solid ${border}; border-radius: 8px; padding: 14px; display: flex; flex-direction: column; gap: 8px;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; font-size: 11px;">
                <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                    <span style="background: rgba(168, 85, 247, 0.15); color: var(--accent-ink); border: 1px solid rgba(168, 85, 247, 0.3); border-radius: 4px; padding: 2px 7px; font-weight: 600;">👤 ${escapeHtml(uLabel)}</span>
                    <span style="background: rgba(56, 189, 248, 0.15); color: var(--primary); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 4px; padding: 2px 7px; font-weight: 600;">🏷️ ${escapeHtml(accLabel)}</span>
                    ${n.event ? `<span style="background: rgba(255, 255, 255, 0.06); color: var(--text-muted); border-radius: 4px; padding: 2px 6px;">⚡ ${escapeHtml(n.event)}</span>` : ''}
                    ${n.error_id ? `<span style="background: rgba(239, 68, 68, 0.2); color: var(--danger); border-radius: 4px; padding: 2px 6px; font-weight: 700;">🚨 ${escapeHtml(n.error_id)}</span>` : ''}
                </div>
                <div style="color: var(--text-muted); display: flex; align-items: center; gap: 8px;">
                    <span>🕒 ${escapeHtml(n.time)}</span>
                    ${!n.read ? '<span style="background: var(--primary); color: white; border-radius: 4px; padding: 1px 6px; font-size: 10px; font-weight: 600;">BARU</span>' : '<span style="color: var(--text-muted); font-size: 10px;">DIBACA</span>'}
                </div>
            </div>
            <div style="font-size: 13px; line-height: 1.5; color: var(--text);">${text}</div>
        </div>
        `;
    }).join('');
}

async function markAllAdminNotificationsRead() {
    try {
        const data = await apiFetch('/api/admin/notifications/read', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
        showToast(`✅ ${data.marked_count || 0} notifikasi berhasil ditandai dibaca`, 'success');
        await loadAdminNotifications();
        await loadNotifications();
    } catch (e) {
        showToast('⚠️ Gagal menandai notifikasi: ' + e.message, 'error');
    }
}

// Realtime Countdown 1-second Ticker
let currentRemainingSeconds = null;
let currentPhase = null;

setInterval(() => {
    if (currentRemainingSeconds !== null && currentRemainingSeconds > 0) {
        currentRemainingSeconds--;
        const m = Math.floor(currentRemainingSeconds / 60);
        const s = currentRemainingSeconds % 60;
        const formatted = `${m}:${s < 10 ? '0' : ''}${s}`;
        const cdElem = document.getElementById('countdownVal');
        if (cdElem) cdElem.innerText = formatted;

        if (currentPhase === 'delivering') {
            const titleElem = document.getElementById('statusTitle');
            if (titleElem) titleElem.innerText = `Mengantar order (${formatted})`;
        }
    } else if (currentRemainingSeconds === 0) {
        const cdElem = document.getElementById('countdownVal');
        if (cdElem) cdElem.innerText = 'Tiba / Selesai';
    }
}, 1000);

let streamConnected = false;
let accountOptionsKey = '';
let accountListKey = '';
let pendingSelection = false;
const pendingControls = new Set();

function applyDashboard(data) {
    if (pendingSelection) return;
    dashboardData = data;
    renderDashboard(data);
    const freshness = document.getElementById('dashboardFreshness');
    const label = 'Status diperbarui ' +
        new Date().toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Jakarta' }) + ' WIB';
    if (freshness.textContent !== label) freshness.textContent = label;
}

function startLiveStream() {
    if (!window.EventSource) return;
    const source = new EventSource('/api/dashboard/stream');
    source.onmessage = event => {
        const data = JSON.parse(event.data);
        streamConnected = true;
        applyDashboard(data);
    };
    source.onerror = () => {
        streamConnected = false;
        source.close();
        setTimeout(startLiveStream, 5000);
    };
}

async function refreshDashboard() {
    try {
        const res = await fetch('/api/dashboard');
        if (res.status === 401) {
            window.location.href = '/login';
            return false;
        }
        if (!res.ok) throw new Error('Gagal memuat dashboard');
        applyDashboard(await res.json());
        return true;
    } catch (e) {
        document.getElementById('dashboardFreshness').textContent = 'Status gagal dimuat. Coba segarkan.';
        return false;
    }
}

const formatCoin = value => value == null ? '—'
    : new Intl.NumberFormat('id-ID', { maximumFractionDigits: 3 }).format(Number(value)) + ' koin';

function renderGrowthBadge(elemId, growth) {
    const el = document.getElementById(elemId);
    if (!el) return;
    if (!growth || !growth.text) {
        el.textContent = '';
        el.className = 'growth-badge';
        el.style.display = 'none';
        return;
    }
    const icon = growth.direction === 'up' ? '▲' : (growth.direction === 'down' ? '▼' : '•');
    el.textContent = `${icon} ${growth.text}`;
    el.className = `growth-badge ${growth.direction}`;
    el.style.display = 'inline-flex';
}

function renderDashboard(data) {
    const accounts = data.accounts || [];
    const selected = data.account;
    document.getElementById('onboardingCard').hidden = Boolean(selected);
    document.getElementById('activeDashboardSection').hidden = !selected;

    const selector = document.getElementById('accountDropdown');
    const optionsKey = JSON.stringify(accounts.map(acc => [acc.id, acc.name]));
    if (accountOptionsKey !== optionsKey) {
        selector.replaceChildren(...(accounts.length
            ? accounts.map(acc => new Option(acc.name, acc.id))
            : [new Option('Belum ada akun', '')]));
        selector.disabled = !accounts.length;
        accountOptionsKey = optionsKey;
    }
    if (selector.value !== (selected?.id ?? '')) selector.value = selected?.id ?? '';

    const totals = data.all_accounts_summary || {};
    document.getElementById('fleetTotalWallet').textContent = (totals.total_wallet ?? '0') + ' koin';
    document.getElementById('fleetTotalIncome').textContent = (totals.total_income ?? '0') + ' koin';
    renderGrowthBadge('fleetIncomeGrowth', totals.income_growth);
    document.getElementById('fleetTotalExpenses').textContent = (totals.total_expenses ?? '0') + ' koin';
    document.getElementById('fleetTotalNetProfit').textContent = (totals.total_net_profit ?? '0') + ' koin';
    renderGrowthBadge('fleetNetGrowth', totals.profit_growth);
    document.getElementById('fleetTotalTrips').textContent = totals.total_trips ?? 0;
    document.getElementById('fleetCountAccounts').textContent = accounts.length + ' akun';
    document.getElementById('fleetCountWorkers').textContent = (totals.active_workers ?? 0) + ' dari ' + accounts.length;
    document.getElementById('activeAccountBannerName').textContent = selected?.name ?? 'Akun terpilih';
    updateBankBadge(data.pending_bank_reviews_count || 0);

    const listKey = JSON.stringify(accounts.map(acc => [acc.id, acc.name, acc.status_text, acc.is_selected, acc.wallet, acc.has_cookie]));
    if (accountListKey !== listKey) {
        const list = document.getElementById('fleetAccountsGrid');
        const focused = list.contains(document.activeElement) ? document.activeElement.dataset.accountId : null;
        const buttons = accounts.map(acc => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'fleet-account';
            button.dataset.accountId = acc.id;
            button.setAttribute('aria-pressed', String(acc.is_selected));
            button.innerHTML = `<span><span class="fleet-name">${escapeHtml(acc.name)}</span>
                <small>${escapeHtml(acc.status_text || 'Status belum tersedia')}</small></span>
                <span class="fleet-amount">${acc.wallet == null ? '—' : escapeHtml(acc.wallet + ' koin')}
                <small>${acc.is_selected ? 'Terpilih' : ''}</small></span>`;
            button.addEventListener('click', () => switchAccount(acc.id));
            return button;
        });
        list.replaceChildren(...buttons);
        if (focused) buttons.find(button => button.dataset.accountId === focused)?.focus({ preventScroll: true });
        accountListKey = listKey;
    }

    const sum = data.summary || {};
    const snap = data.snapshot || {};
    const fin = data.finance || {};
    document.getElementById('statusTitle').textContent = sum.status_text || 'Status belum tersedia';
    document.getElementById('walletVal').textContent = formatCoin(sum.wallet);
    document.getElementById('accProfitVal').textContent = (fin.today_income ?? '0') + ' koin';
    renderGrowthBadge('accProfitGrowth', fin.income_growth);
    document.getElementById('accExpenseVal').textContent = (fin.today_expenses ?? '0') + ' koin';
    document.getElementById('accNetProfitVal').textContent = (fin.today_net_profit ?? '0') + ' koin';
    renderGrowthBadge('accNetGrowth', fin.profit_growth);
    document.getElementById('tripsVal').textContent = sum.trips ?? '—';
    document.getElementById('presenceVal').textContent = sum.online ? 'Online di game' : 'Offline di game';

    // Realtime Countdown State
    const oldPhase = currentPhase;
    currentPhase = sum.phase || snap.phase || null;
    const rawRem = sum.remaining_seconds != null ? sum.remaining_seconds : (snap.remaining_seconds != null ? snap.remaining_seconds : null);
    const serverSec = (rawRem !== null && !isNaN(rawRem)) ? Math.max(0, parseInt(rawRem)) : null;

    if (serverSec === null) {
        currentRemainingSeconds = null;
    } else if (currentRemainingSeconds === null || oldPhase !== currentPhase || Math.abs(currentRemainingSeconds - serverSec) > 3) {
        currentRemainingSeconds = serverSec;
    }

    const cdElem = document.getElementById('countdownVal');
    if (cdElem) {
        if (currentRemainingSeconds !== null && currentRemainingSeconds > 0) {
            const m = Math.floor(currentRemainingSeconds / 60);
            const s = currentRemainingSeconds % 60;
            cdElem.innerText = `${m}:${s < 10 ? '0' : ''}${s}`;
        } else if (currentPhase === 'searching') {
            cdElem.innerText = 'Mencari order…';
        } else if (currentPhase === 'sleeping') {
            cdElem.innerText = 'Sedang tidur';
        } else if (currentRemainingSeconds === 0) {
            cdElem.innerText = 'Tiba / Selesai';
        } else if (currentPhase === 'idle' && sum.active) {
            cdElem.innerText = 'Siaga';
        } else {
            cdElem.innerText = '—';
        }
    }

    if (currentPhase === 'delivering' && currentRemainingSeconds !== null && currentRemainingSeconds > 0) {
        const m = Math.floor(currentRemainingSeconds / 60);
        const s = currentRemainingSeconds % 60;
        document.getElementById('statusTitle').innerText = `Mengantar order (${m}:${s < 10 ? '0' : ''}${s})`;
    }

    // Notice Card if Limit is Reached
    const limitCard = document.getElementById('limitNoticeCard');
    if (limitCard) {
        const isLimit = !!(
            data.limit_reached ||
            (sum && sum.shift_done) ||
            (snap && snap.ojol_shift_done) ||
            (snap.ojol_hours_left != null && snap.ojol_hours_left <= 0) ||
            (sum && sum.status_text && (sum.status_text.includes('Batas narik') || sum.status_text.includes('14 jam') || sum.status_text.includes('8 jam')))
        );
        limitCard.hidden = !isLimit;
    }

    // Meters
    updateMeter('fuel', (sum && sum.fuel !== undefined) ? sum.fuel : (snap ? snap.fuel : null));
    updateMeter('cond', (sum && sum.condition !== undefined) ? sum.condition : (snap ? snap.condition : null));
    updateMeter('data', (sum && sum.data !== undefined) ? sum.data : (snap ? snap.data : null));
    const spbuHint = document.getElementById('spbuWaitHint');
    const waitingForSpbu = snap.ojol_min_fuel != null && (snap.ojol_fuel_blocked || Number(snap.fuel) < snap.ojol_min_fuel);
    spbuHint.hidden = !waitingForSpbu;
    if (waitingForSpbu) {
        const vehicle = snap.ojol_vehicle === 'mobil' ? 'mobil' : 'motor';
        spbuHint.textContent = 'Bawa ' + vehicle + ' yang dipakai Ojol ke SPBU dan buka pompa.';
    }

    const needs = (snap && snap.needs) ? snap.needs : (snap || {});
    updateMeter('makan', needs.makan !== undefined ? needs.makan : (snap ? snap.makan : null));
    updateMeter('kesehatan', needs.kesehatan !== undefined ? needs.kesehatan : (snap ? snap.kesehatan : null));
    updateMeter('fisik', needs.fisik !== undefined ? needs.fisik : (snap ? snap.fisik : null));
    updateMeter('rekreasi', needs.rekreasi !== undefined ? needs.rekreasi : (snap ? snap.rekreasi : null));
    updateMeter('kebersihan', needs.kebersihan !== undefined ? needs.kebersihan : (snap ? snap.kebersihan : null));
    updateMeter('wc', needs.wc !== undefined ? needs.wc : (snap ? snap.wc : null));
    updateMeter('penampilan', needs.penampilan !== undefined ? needs.penampilan : (snap ? snap.penampilan : null));
    updateMeter('rumah', needs.rumah !== undefined ? needs.rumah : (snap ? snap.rumah : null));

    // Auto toggles
    const flags = data.auto_flags || {};
    const ojolToggleEl = document.getElementById('autoOjolToggle');
    const ojolDescEl = document.getElementById('autoOjolDesc');
    if (ojolToggleEl) {
        const hasJob = Boolean(snap.job);
        const notMitra = snap.ojol_mitra === false;
        ojolToggleEl.checked = !!flags.ojol;
        ojolToggleEl.disabled = !selected || hasJob || notMitra;
        if (ojolDescEl) {
            if (hasJob) {
                ojolDescEl.textContent = 'Nonaktif karena akun sudah memiliki pekerjaan aktif.';
            } else if (notMitra) {
                ojolDescEl.textContent = 'Belum menjadi mitra Ojol — daftar mitra dulu di game.';
            } else {
                ojolDescEl.textContent = 'Mengambil dan mengantar order ojol otomatis sesuai kuota akun';
            }
        }
    }
    if (document.getElementById('modeOjolToggle')) document.getElementById('modeOjolToggle').checked = (data.ojol_mode === 'kendara');
    if (document.getElementById('autoPerpusToggle')) document.getElementById('autoPerpusToggle').checked = !!flags.perpus;
    if (document.getElementById('autoKuliahToggle')) document.getElementById('autoKuliahToggle').checked = !!flags.kuliah;
    if (document.getElementById('autoStudyToggle')) document.getElementById('autoStudyToggle').checked = !!(flags.perpus || flags.kuliah);
    if (document.getElementById('studyRotateToggle')) document.getElementById('studyRotateToggle').checked = (data.study_subject === 'auto');
    if (document.getElementById('autoMakan')) document.getElementById('autoMakan').checked = !!flags.makan;
    if (document.getElementById('autoKesehatan')) document.getElementById('autoKesehatan').checked = !!flags.kesehatan;
    if (document.getElementById('autoFisik')) document.getElementById('autoFisik').checked = !!flags.fisik;
    if (document.getElementById('autoRekreasi')) document.getElementById('autoRekreasi').checked = !!flags.rekreasi;
    if (document.getElementById('autoKebersihan')) document.getElementById('autoKebersihan').checked = !!flags.kebersihan;
    if (document.getElementById('autoWc')) document.getElementById('autoWc').checked = !!flags.wc;
    if (document.getElementById('autoPenampilan')) document.getElementById('autoPenampilan').checked = !!flags.penampilan;
    if (document.getElementById('autoRumah')) document.getElementById('autoRumah').checked = !!flags.rumah;
    if (document.getElementById('autoGarden')) document.getElementById('autoGarden').checked = !!(flags.kebun || flags.garden);

    if (data.study_subject && document.getElementById('studySubjectSelect')) {
        document.getElementById('studySubjectSelect').value = data.study_subject;
    }

    const kursusToggle = document.getElementById('autoKursusToggle');
    const kursusSelect = document.getElementById('kursusSubjectSelect');
    const kursusCostEl = document.getElementById('kursusCostInfo');
    if (kursusSelect) {
        kursusSelect.value = data.kursus_subject || '';
    }
    if (kursusToggle) {
        const hasKursusSubject = Boolean(data.kursus_subject);
        kursusToggle.checked = !!flags.kursus;
        kursusToggle.disabled = !selected || (!hasKursusSubject && !flags.kursus);
    }
    if (kursusCostEl) {
        const kc = data.kursus_cost || null;
        const ks = data.kursus_status || null;
        if (!data.kursus_subject) {
            kursusCostEl.textContent = 'Wajib pilih bidang kursus untuk melihat biaya & mengaktifkan.';
            kursusCostEl.style.color = '#f59e0b';
            kursusCostEl.style.display = 'block';
        } else if (kc) {
            const parts = [];
            if (kc.is_max) {
                parts.push(`${kc.label}: Sudah level maksimal (Lv ${kc.level ?? 10})`);
            } else {
                const lvl = (typeof kc.level === 'number' && typeof kc.next_level === 'number')
                    ? `Lv ${kc.level} → Lv ${kc.next_level}`
                    : '';
                const costStr = typeof kc.cost_milli === 'number' ? `${kc.cost_milli / 1000} koin` : 'cek saat jalan';
                const durStr = typeof kc.hours === 'number' ? `${kc.hours} jam` : '';
                parts.push(`${kc.label}${lvl ? ` (${lvl})` : ''} · Biaya: ${costStr}${durStr ? ` · Durasi: ${durStr}` : ''}`);
                if (kc.pending) {
                    parts.push(`Pending${kc.rush_milli ? ` (Percepat: ${kc.rush_milli / 1000} koin)` : ''}`);
                }
            }
            if (ks && ks.state) parts.push(`Status: ${ks.state}`);
            kursusCostEl.textContent = parts.join(' · ');
            kursusCostEl.style.color = 'var(--accent,#0f766e)';
            kursusCostEl.style.display = 'block';
        } else {
            kursusCostEl.textContent = '';
            kursusCostEl.style.display = 'none';
        }
    }

    const cookie = document.getElementById('btnCookieToolbar');
    const reconnect = sum.cookie_valid === false;
    cookie.textContent = !selected?.has_cookie ? 'Hubungkan cookie' : reconnect ? 'Perbarui cookie' : 'Ganti cookie';
    cookie.classList.toggle('btn-primary', !selected?.has_cookie || reconnect);
    cookie.classList.toggle('btn-utility', Boolean(selected?.has_cookie && !reconnect));

    renderAutomationControls(data);
    const count = flags.needs_count ?? 0;
    const total = flags.total_needs ?? 8;
    document.getElementById('needsCardBadge').textContent = selected ? `${count} dari ${total} otomatis` : '—';

    // Logs
    const logBox = document.getElementById('logConsole');
    const logs = data.logs?.length ? data.logs.join('\n') : 'Belum ada aktivitas.';
    if (logBox.textContent !== logs) logBox.textContent = logs;

    const hasStuck = (data.logs || []).some(l => l.includes('Aksi tertahan:') || l.includes('Rekonsiliasi Transaksi Game'));
    const stuckBanner = document.getElementById('reconcileStuckBanner');
    if (stuckBanner) stuckBanner.style.display = hasStuck ? 'flex' : 'none';
    const btnSkip = document.getElementById('btnSkipActions');
    if (btnSkip) btnSkip.style.display = hasStuck ? 'inline-block' : 'none';

    // Riwayat Pengeluaran
    const expenseList = document.getElementById('expenseList');
    const expenseBadge = document.getElementById('expenseTodayTotal');
    if (expenseBadge) {
        expenseBadge.textContent = fin.today_expenses && fin.today_expenses !== '0' ? `Total hari ini: -${fin.today_expenses} koin` : '';
    }
    if (expenseList) {
        const history = fin.expense_history || [];
        if (!history.length) {
            expenseList.innerHTML = '<div class="empty-state" style="padding: 24px; text-align: center; color: var(--text-muted); font-size: 13px;">Belum ada riwayat pengeluaran.</div>';
        } else {
            const catIcons = {
                bensin: '⛽',
                bengkel: '🔧',
                makan: '🍲',
                pulsa: '📱',
                kuota: '📱',
                kebun: '🌱',
                kuliah: '🎓',
                perpus: '📚',
            };
            expenseList.innerHTML = history.map(item => {
                const icon = catIcons[item.category] || '💸';
                const catName = escapeHtml(item.category || 'Biaya');
                const itemName = escapeHtml(item.item_name || 'Pengeluaran');
                const timeStr = escapeHtml(item.time_display || '');
                const amountStr = escapeHtml(item.amount || '0');
                return `<div class="expense-item" style="display: flex; justify-content: space-between; align-items: center; padding: 10px 12px; border-bottom: 1px solid var(--border); font-size: 13px;">
                    <div style="display: flex; align-items: center; gap: 10px; min-width: 0;">
                        <span style="font-size: 18px; flex-shrink: 0;">${icon}</span>
                        <div style="min-width: 0;">
                            <div style="font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${itemName}</div>
                            <div style="font-size: 11px; color: var(--text-muted);">${catName} • ${timeStr}</div>
                        </div>
                    </div>
                    <div style="font-weight: 700; color: #ef4444; white-space: nowrap; margin-left: 12px; font-variant-numeric: tabular-nums;">
                        -${amountStr} koin
                    </div>
                </div>`;
            }).join('');
        }
    }

    // Riwayat Belajar Lengkap
    const studyContainer = document.getElementById('studyHistoryList');
    const studyBadge = document.getElementById('studyHistoryBadge');
    const studyItems = data.study_history || [];
    if (studyBadge) {
        studyBadge.textContent = studyItems.length ? `${studyItems.length} sesi tercatat` : '';
    }
    if (studyContainer) {
        if (!studyItems.length) {
            studyContainer.innerHTML = '<div class="empty-state" style="padding: 16px; text-align: center; color: var(--text-muted); font-size: 12px;">Belum ada riwayat belajar tercatat.</div>';
        } else {
            const modeIcons = {
                perpus: '📖',
                kuliah: '🎓',
            };
            const trackIcons = {
                dagang: '🛒',
                teknik: '🔧',
                administrasi: '📋',
                kesehatan: '🏥',
                mengajar: '👨‍🏫',
                rawat: '🏡',
                konveksi: '👕',
                keamanan: '🛡️',
                boga: '🍳',
                penerbangan: '✈️',
            };
            studyContainer.innerHTML = studyItems.map(item => {
                const mIcon = modeIcons[item.mode] || '📚';
                const tIcon = trackIcons[item.track_id] || '🎯';
                const facility = escapeHtml(item.facility_name || (item.mode === 'perpus' ? 'Perpustakaan Desa' : 'Universitas'));
                const modeLabel = escapeHtml(item.mode_label || (item.mode === 'perpus' ? 'Perpustakaan' : 'Universitas'));
                const trackName = escapeHtml(item.track_name || 'Keahlian');
                const levelBadge = item.level_display ? `<span class="badge" style="font-size: 11px; padding: 1px 6px; border-radius: 4px; background: rgba(16, 185, 129, 0.12); color: #10b981; font-weight: 700;">${escapeHtml(item.level_display)}</span>` : '';
                const skillGain = escapeHtml(item.skill_gain || 'Selesai');
                const costStr = escapeHtml(item.cost || 'Gratis');
                const costColor = item.cost_num > 0 ? '#ef4444' : '#10b981';
                const timeStr = escapeHtml(item.time_display || '');
                const modeBadgeClass = item.mode === 'perpus' ? 'background: rgba(59, 130, 246, 0.12); color: #3b82f6;' : 'background: rgba(168, 85, 247, 0.12); color: #a855f7;';

                return `<div class="study-card-item" style="border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; background: rgba(255, 255, 255, 0.02); display: flex; justify-content: space-between; align-items: flex-start; gap: 10px;">
                    <div style="min-width: 0; flex: 1;">
                        <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
                            <span style="font-size: 16px;">${mIcon}</span>
                            <strong style="font-size: 13px; color: var(--text-main);">${facility}</strong>
                            <span class="badge" style="font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 4px; ${modeBadgeClass}">${modeLabel}</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 6px; margin-top: 5px; flex-wrap: wrap;">
                            <span style="font-size: 12px; font-weight: 600;">${tIcon} ${trackName}</span>
                            ${levelBadge}
                            <span style="font-size: 12px; color: #10b981; font-weight: 600;">▲ ${skillGain}</span>
                        </div>
                        <div style="font-size: 11px; color: var(--text-muted); margin-top: 4px;">
                            🕒 ${timeStr}
                        </div>
                    </div>
                    <div style="text-align: right; white-space: nowrap; flex-shrink: 0;">
                        <div style="font-size: 12px; font-weight: 700; color: ${costColor}; font-variant-numeric: tabular-nums;">
                            ${costStr}
                        </div>
                        <span class="badge" style="display: inline-block; margin-top: 4px; font-size: 10px; padding: 1px 6px; border-radius: 4px; background: rgba(16, 185, 129, 0.1); color: #10b981;">✓ ${escapeHtml(item.status || 'Selesai')}</span>
                    </div>
                </div>`;
            }).join('');
        }
    }
}

async function skipStuckActions() {
    const accId = dashboardData?.account?.id;
    const query = accId ? '?account_id=' + encodeURIComponent(accId) : '';
    if (!confirm('Lewati semua aksi transaksi yang tertahan dan jalankan bot dari kondisi game saat ini?')) return;
    try {
        const data = await apiFetch('/api/control/skip' + query, { method: 'POST' });
        showToast(data.message || 'Aksi tertahan dilewati. Bot melanjutkan aktivitas.', 'success');
        manualRefreshDashboard();
    } catch (e) {
        showToast(e.message, 'error');
    }
}

function updateMeter(id, val) {
    const txt = document.getElementById(id + 'Text');
    const bar = document.getElementById(id + 'Bar');
    if (!txt || !bar) return;
    if (val === undefined || val === null) {
        txt.textContent = '—';
        bar.style.width = '0%';
        return;
    }
    txt.innerText = val + '%';
    bar.style.width = Math.max(0, Math.min(100, val)) + '%';
    if (val > 50) {
        bar.className = 'meter-fill fill-green';
    } else if (val > 25) {
        bar.className = 'meter-fill fill-orange';
    } else {
        bar.className = 'meter-fill fill-red';
    }
}

function showToast(msg, type = 'info') {
    let container = document.getElementById('toastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toastContainer';
        container.className = 'toast-container';
        container.setAttribute('role', 'status');
        document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerText = msg;
    container.appendChild(toast);

    requestAnimationFrame(() => {
        toast.classList.add('toast-show');
    });

    setTimeout(() => {
        toast.classList.remove('toast-show');
        setTimeout(() => {
            if (toast.parentNode) toast.remove();
        }, 300);
    }, 3500);
}

function renderAutomationControls(data) {
    const flags = data.auto_flags || {};
    const sum = data.summary || {};
    const snap = data.snapshot || {};
    const isSleeping = sum.phase === 'sleeping';
    const hasJob = Boolean(snap.job);
    const isKantorJob = hasJob && (snap.job.kantor != null || ['PUBLIC', 'BUSINESS'].includes(snap.job.employerType));
    const notMitra = snap.ojol_mitra === false;
    const isNgojol = ['searching', 'delivering', 'complete'].includes(snap.phase) || Boolean(snap.trip);

    let ojolBlockedReason = '';
    if (data.account) {
        if (hasJob) ojolBlockedReason = 'Akun sudah memiliki pekerjaan aktif — Auto Ojol dinonaktifkan.';
        else if (notMitra) ojolBlockedReason = 'Belum menjadi mitra Ojol — daftar mitra dulu di game.';
    }

    const ojolRunning = Boolean(sum.active && (flags.ojol === true || flags.ojol === 'maintenance'));

    let kerjaBlockedReason = '';
    if (data.account) {
        if (!hasJob) kerjaBlockedReason = 'Belum punya pekerjaan — ambil kerja kantor dulu di game.';
        else if (!isKantorJob) kerjaBlockedReason = 'Auto Kantor hanya untuk pekerjaan kantor/fasum/usaha.';
        else if (ojolRunning) kerjaBlockedReason = 'Nonaktif saat Auto Ojol berjalan.';
        else if (isNgojol) kerjaBlockedReason = 'Nonaktif saat sedang ngojol.';
    }

    for (const [feature, enabled, maintenance, blockedReason] of [
        ['Ojol', flags.ojol === true || flags.ojol === 'maintenance', flags.ojol === 'maintenance' || snap.ojol_maintenance, ojolBlockedReason],
        ['Kerja', Boolean(flags.kerja), false, kerjaBlockedReason],
        ['Needs', Boolean(flags.needs_active), false, ''],
    ]) {
        const pending = pendingControls.has(feature);
        const active = Boolean(sum.active && enabled);
        const state = document.getElementById('toolbar' + feature + 'Badge');
        let label = 'Nonaktif';
        let tone = '';
        if (pending) label = 'Memproses…';
        else if (maintenance) { label = 'Dijeda untuk pemeliharaan'; tone = 'paused'; }
        else if (active && isSleeping) { label = 'Dijeda saat karakter tidur'; tone = 'paused'; }
        else if (active && feature === 'Kerja' && data.kerja_status?.state === 'Selesai hari ini') {
            label = 'Selesai hari ini · Lanjut besok';
            tone = 'paused';
        }
        else if (active) { label = 'Sedang berjalan'; tone = 'active'; }
        else if (enabled) label = 'Siap dijalankan';
        else if (feature === 'Ojol' && notMitra && !hasJob) label = 'Belum mitra';
        else if (feature === 'Ojol' && hasJob) label = 'Punya kerja';
        else if (feature === 'Kerja' && data.account && !hasJob) label = 'Belum kerja';
        else if (feature === 'Kerja' && data.account && !isKantorJob) label = 'Bukan kantor';
        if (state) {
            state.textContent = label;
            state.dataset.tone = tone;
        }
        const canRun = Boolean(data.account && !pending && !active && !maintenance && !blockedReason);
        const run = document.getElementById('btnRun' + feature);
        const stop = document.getElementById('btnStop' + feature);
        if (run) {
            run.hidden = active || maintenance;
            run.disabled = !canRun;
        }
        if (stop) {
            stop.hidden = !enabled;
            stop.disabled = !data.account || pending;
        }
    }

    const ojolHint = document.getElementById('toolbarOjolHint');
    if (ojolHint) {
        ojolHint.textContent = ojolBlockedReason;
        ojolHint.style.color = ojolBlockedReason ? '#f59e0b' : '';
        ojolHint.style.display = ojolBlockedReason ? 'block' : 'none';
    }

    const kerjaHint = document.getElementById('toolbarKerjaHint');
    if (kerjaHint) {
        if (kerjaBlockedReason) {
            kerjaHint.textContent = kerjaBlockedReason;
            kerjaHint.style.color = '#f59e0b';
            kerjaHint.style.display = 'block';
        } else if (hasJob) {
            const job = snap.job;
            const place = job.facility || job.business || '';
            const prof = job.profession || 'Pekerjaan aktif';
            kerjaHint.textContent = place ? `${prof} · ${place}` : prof;
            kerjaHint.style.color = '';
            kerjaHint.style.display = 'block';
        } else {
            kerjaHint.textContent = '';
            kerjaHint.style.display = 'none';
        }
    }

    const kerjaTargetInput = document.getElementById('kerjaTargetPoinInput');
    if (kerjaTargetInput && document.activeElement !== kerjaTargetInput) {
        kerjaTargetInput.value = data.kerja_target_poin != null ? String(data.kerja_target_poin) : '';
        kerjaTargetInput.disabled = !selected || !isKantorJob;
    }
    const saveKerjaTargetBtn = document.getElementById('btnSaveKerjaTarget');
    if (saveKerjaTargetBtn) {
        saveKerjaTargetBtn.disabled = !selected || !isKantorJob;
    }

    const kerjaRtEl = document.getElementById('autoKerjaRealtime');
    if (kerjaRtEl) {
        const ks = data.kerja_status || null;
        if (ks && ks.kind === 'kantor') {
            const parts = [];
            if (ks.state) parts.push(`Status: ${ks.state}`);
            if (typeof ks.lunas === 'number' && typeof ks.per_hari === 'number') {
                const lunas = Math.min(ks.lunas, ks.per_hari);
                parts.push(
                    lunas >= ks.per_hari
                        ? `Tugas: ${lunas}/${ks.per_hari} lunas`
                        : `Tugas: ${lunas}/${ks.per_hari} lunas (${ks.menuju ?? 0}/${ks.per_paket ?? 5} urusan)`
                );
            }
            if (typeof ks.sesi_absen === 'number' && typeof ks.sesi_jumlah === 'number') {
                parts.push(`Sesi absen: ${Math.min(ks.sesi_absen, ks.sesi_jumlah)}/${ks.sesi_jumlah}`);
            }
            if (typeof ks.poin === 'number' && typeof ks.target === 'number') {
                parts.push(`Kerja penuh: ${ks.poin}/${ks.target} poin`);
            }
            if (ks.last_message) parts.push(ks.last_message);
            kerjaRtEl.textContent = parts.join(' · ');
            kerjaRtEl.style.display = parts.length ? 'block' : 'none';
        } else if (snap.job && snap.job.kantor) {
            const k = snap.job.kantor;
            const target = data.kerja_target_poin ?? k.target ?? 30;
            const poin = k.poin ?? 0;
            kerjaRtEl.textContent = `Kerja penuh: ${poin}/${target} poin · Status: ${k.status || '-'}`;
            kerjaRtEl.style.display = 'block';
        } else {
            kerjaRtEl.textContent = '';
            kerjaRtEl.style.display = 'none';
        }
    }
}

async function setKerjaTargetPoin() {
    const account = dashboardData?.account;
    const input = document.getElementById('kerjaTargetPoinInput');
    if (!account || !input) return;
    const raw = input.value.trim();
    const target = raw === '' ? null : Number(raw);
    if (target !== null && (!Number.isInteger(target) || target < 1)) {
        showToast('Target poin minimal 1.', 'error');
        return;
    }
    try {
        await apiFetch('/api/control/kerja-target?account_id=' + encodeURIComponent(account.id), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target_poin: target })
        });
        showToast(target !== null ? `Target poin kantor disetel ke ${target}` : 'Target poin kantor dikembalikan ke default (30)', 'info');
        await refreshDashboard();
    } catch (e) {
        showToast('Gagal menyimpan target poin: ' + e.message, 'error');
    }
}

async function controlAction(cmd) {
    const account = dashboardData?.account;
    if (!account || pendingSelection) return;
    const feature = cmd.endsWith('-needs') ? 'Needs' : cmd.endsWith('-kerja') ? 'Kerja' : 'Ojol';
    if (pendingControls.has(feature)) return;
    if (cmd.startsWith('run') && (!account.has_cookie || dashboardData.summary?.cookie_valid === false)) {
        openCookieModalFor(account.id, account.name);
        return;
    }
    pendingControls.add(feature);
    renderAutomationControls(dashboardData);
    try {
        const data = await apiFetch('/api/control/' + cmd + '?account_id=' + encodeURIComponent(account.id), { method: 'POST' });
        showToast(data.message?.split('\n\n', 1)[0] || 'Aksi diproses', 'info');
        await refreshDashboard();
    } catch (e) {
        showToast('Aksi gagal: ' + e.message, 'error');
    } finally {
        pendingControls.delete(feature);
        if (dashboardData) renderAutomationControls(dashboardData);
    }
}

async function showAccountTool(path, options) {
    const account = dashboardData?.account;
    const output = document.getElementById('accountToolResult');
    if (!account || pendingSelection) {
        output.textContent = 'Pilih akun game terlebih dahulu.';
        return;
    }
    output.textContent = 'Memuat…';
    try {
        const data = await apiFetch('/api/control/' + path + '&account_id=' + encodeURIComponent(account.id), options);
        output.textContent = dashboardData?.account?.id === account.id ? data.message : '';
    } catch (error) {
        output.textContent = error.message;
    }
}

function loadAccountReport(event) {
    event.preventDefault();
    return showAccountTool('report?day=' + encodeURIComponent(document.getElementById('reportDay').value));
}

function scanHouse(kind) {
    return showAccountTool('house-scan?kind=' + kind, {method: 'POST'});
}

async function manualRefreshDashboard() {
    const button = document.getElementById('btnRefreshDash');
    button.disabled = true;
    button.textContent = 'Memuat…';
    try {
        await refreshDashboard();
    } finally {
        button.disabled = false;
        button.textContent = 'Segarkan';
    }
}

async function toggleAuto(flag, enabled) {
    try {
        const accountId = dashboardData?.account?.id;
        if (!accountId) throw new Error('Pilih akun terlebih dahulu.');
        await apiFetch('/api/control/toggle-auto?account_id=' + encodeURIComponent(accountId), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ flag, enabled })
        });
        showToast('Pengaturan auto ' + flag + ': ' + (enabled ? 'Aktif' : 'Nonaktif'), 'info');
        await refreshDashboard();
    } catch (e) {
        showToast('⚠️ Gagal: ' + e.message, 'error');
        await refreshDashboard();
    }
}

async function toggleModeOjol(isKendara) {
    try {
        const mode = isKendara ? 'kendara' : 'otomatis';
        await apiFetch('/api/control/mode-ojol', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode })
        });
        showToast('Mode ojol: ' + (isKendara ? 'Kendara (Manual)' : 'Otomatis'), 'info');
        await refreshDashboard();
    } catch (e) {
        showToast('⚠️ Gagal: ' + e.message, 'error');
    }
}

async function setStudySubject(subject) {
    try {
        const accountId = dashboardData?.account?.id;
        if (!accountId) throw new Error('Pilih akun terlebih dahulu.');
        await apiFetch('/api/control/study-subject?account_id=' + encodeURIComponent(accountId), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ subject })
        });
        showToast('Bidang belajar: ' + subject.toUpperCase(), 'info');
        await refreshDashboard();
    } catch (e) {
        showToast('⚠️ Gagal: ' + e.message, 'error');
        await refreshDashboard();
    }
}

async function setKursusSubject(subject) {
    try {
        const accountId = dashboardData?.account?.id;
        if (!accountId) throw new Error('Pilih akun terlebih dahulu.');
        if (!subject) throw new Error('Wajib pilih bidang kursus.');
        await apiFetch('/api/control/study-subject?account_id=' + encodeURIComponent(accountId), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ subject, mode: 'kursus' })
        });
        showToast('Bidang kursus: ' + subject.toUpperCase(), 'info');
        await refreshDashboard();
    } catch (e) {
        showToast('⚠️ Gagal: ' + e.message, 'error');
        await refreshDashboard();
    }
}

async function switchAccount(accountId) {
    if (!accountId || pendingSelection || dashboardData?.account?.id === accountId) return;
    pendingSelection = true;
    const selector = document.getElementById('accountDropdown');
    selector.disabled = true;
    try {
        await apiFetch('/api/accounts/select', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ account_id: accountId })
        });
    } catch (e) {
        showToast('Gagal mengganti akun: ' + e.message, 'error');
    } finally {
        pendingSelection = false;
        selector.disabled = false;
        const applied = await refreshDashboard();
        if (!applied && dashboardData?.account) selector.value = dashboardData.account.id;
        if (document.getElementById('tab-accounts').classList.contains('active')) await loadAccounts();
    }
}

async function submitCreateAccount() {
    const name = document.getElementById('newAccountName').value.trim();
    try {
        const data = await apiFetch('/api/accounts/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name || undefined })
        });
        closeModal('addAccountModal');
        document.getElementById('newAccountName').value = '';
        await refreshDashboard();
        await loadAccounts();
        const createdAcc = data.account;
        if (createdAcc) {
            openCookieModalFor(createdAcc.id, createdAcc.name);
        }
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

async function submitOnboardingCookie() {
    const name = (document.getElementById('onboardingAccountName')?.value || '').trim();
    const cookie = (document.getElementById('onboardingCookieInput')?.value || '').trim();
    if (!cookie) return alert('Silakan tempel cookie KampungSebelah terlebih dahulu.');

    const btn = document.getElementById('btnOnboardingSubmit');
    const loading = document.getElementById('onboardingLoadingText');
    if (btn) btn.disabled = true;
    if (loading) loading.style.display = 'inline';

    try {
        const data = await apiFetch('/api/control/import-cookie', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, cookie })
        });
        showToast(data.message || '✅ Akun berhasil dihubungkan dan cookie terverifikasi!', 'success');
        const inp = document.getElementById('onboardingCookieInput');
        if (inp) inp.value = '';
        await refreshDashboard();
        await loadAccounts();
    } catch (e) {
        showToast('⚠️ Gagal menghubungkan akun: ' + e.message, 'error');
    } finally {
        if (btn) btn.disabled = false;
        if (loading) loading.style.display = 'none';
    }
}

async function submitCookie() {
    const cookie = document.getElementById('cookieInput').value.trim();
    const error = document.getElementById('cookieError');
    error.hidden = true;
    if (!cookie) {
        error.textContent = 'Tempel cookie sesi terlebih dahulu.';
        error.hidden = false;
        document.getElementById('cookieInput').focus();
        return;
    }
    const targetAccountId = (document.getElementById('cookieTargetAccountId')?.value || '').trim();
    const btn = document.getElementById('btnSubmitCookie');
    const loading = document.getElementById('cookieLoadingText');
    if (btn) btn.disabled = true;
    if (loading) loading.style.display = 'inline';

    try {
        const payload = { cookie };
        if (targetAccountId) payload.account_id = targetAccountId;
        const data = await apiFetch('/api/control/import-cookie', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        closeModal('cookieModal');
        document.getElementById('cookieInput').value = '';
        if (document.getElementById('cookieTargetAccountId')) {
            document.getElementById('cookieTargetAccountId').value = '';
        }
        showToast(data.message || '✅ Cookie berhasil diimpor dan terverifikasi!', 'success');
        await refreshDashboard();
        await loadAccounts();
    } catch (e) {
        error.textContent = 'Gagal mengimpor cookie: ' + e.message;
        error.hidden = false;
    } finally {
        if (btn) btn.disabled = false;
        if (loading) loading.style.display = 'none';
    }
}

async function loadAccounts() {
    try {
        const data = await apiFetch('/api/accounts');
        const tbody = document.getElementById('accountsTableBody');
        tbody.innerHTML = '';
        if (!data.accounts || !data.accounts.length) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">Belum ada akun. Klik + Tambah Akun di atas.</td></tr>';
            return;
        }
        data.accounts.forEach(acc => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong>${escapeHtml(acc.name)}</strong> ${acc.is_selected ? '<span style="color: var(--primary); font-size: 11px;">(Aktif)</span>' : ''}</td>
                <td data-label="Cookie">${acc.has_cookie ? '<span style="color: var(--success);">Terhubung</span>' : '<span style="color: var(--warning);">Belum ada</span>'}</td>
                <td data-label="Worker">${acc.is_running ? '<span style="color: var(--success);">Berjalan</span>' : '<span style="color: var(--text-muted);">Berhenti</span>'}</td>
                <td data-label="Auto Ojol">${acc.auto_ojol ? '<span style="color: var(--success); font-weight: 600;">ON</span>' : '<span style="color: var(--text-muted);">OFF</span>'}</td>
                <td data-label="Arsip">${acc.archived ? '<span style="color: var(--warning);">Diarsipkan</span>' : 'Aktif'}</td>
                <td style="display: flex; gap: 4px; flex-wrap: wrap;">
                    ${!acc.archived && !acc.is_selected ? `<button class="btn btn-secondary" style="padding: 4px 8px; font-size: 11px;" onclick="switchAccount('${acc.id}')">Pilih</button>` : ''}
                    ${acc.archived ? '' : `
                        <button data-action="cookie" class="btn ${acc.has_cookie ? 'btn-secondary' : 'btn-primary'}" style="padding: 4px 8px; font-size: 11px;">${acc.has_cookie ? 'Ganti cookie' : 'Hubungkan cookie'}</button>
                        <button data-action="rename" class="btn btn-secondary" style="padding: 4px 8px; font-size: 11px;">Ubah Nama</button>`}
                    <button class="btn btn-secondary" style="padding: 4px 8px; font-size: 11px;" onclick="toggleArchive('${acc.id}', ${!acc.archived})">${acc.archived ? 'Pulihkan' : 'Arsipkan'}</button>
                </td>
            `;
            if (!acc.archived) {
                tr.querySelector('[data-action="cookie"]').onclick = () => openCookieModalFor(acc.id, acc.name);
                tr.querySelector('[data-action="rename"]').onclick = () => promptRename(acc.id, acc.name);
            }
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error(e);
    }
}

async function promptRename(accId, curName) {
    const n = prompt('Masukkan nama baru untuk akun ini:', curName);
    if (!n || n === curName) return;
    try {
        const res = await fetch('/api/accounts/rename', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ account_id: accId, name: n })
        });
        if (!res.ok) throw new Error('Gagal mengubah nama');
        loadAccounts();
        refreshDashboard();
    } catch (e) {
        alert(e.message);
    }
}

async function toggleArchive(accId, archived) {
    try {
        const res = await fetch('/api/accounts/archive', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ account_id: accId, archived })
        });
        if (!res.ok) throw new Error('Gagal update status arsip');
        loadAccounts();
        refreshDashboard();
    } catch (e) {
        alert(e.message);
    }
}

const adminNumber = new Intl.NumberFormat('id-ID');
const adminDate = new Intl.DateTimeFormat('id-ID', {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
    timeZone: 'Asia/Jakarta', timeZoneName: 'short',
});
let adminLastChecked = null;
let adminLoadVersion = 0;
let adminGameAccounts = [];
let adminGameAccountsRequest = 0;

function openAdminGameAccounts(trigger) {
    document.getElementById('adminGameAccountsSearch').value = '';
    document.getElementById('adminGameAccountsStatus').value = 'all';
    trigger?.focus();
    openModal('adminGameAccountsDialog');
    loadAdminGameAccounts();
}

async function loadAdminGameAccounts() {
    const request = ++adminGameAccountsRequest;
    const message = document.getElementById('adminGameAccountsMessage');
    const filters = document.getElementById('adminGameAccountsFilters');
    const retry = document.getElementById('adminGameAccountsRetry');
    filters.disabled = true;
    retry.hidden = true;
    message.textContent = 'Memuat akun game…';
    const list = document.getElementById('adminGameAccountsList');
    list.replaceChildren();
    try {
        const data = await apiFetch('/api/admin/accounts');
        if (request !== adminGameAccountsRequest) return;
        adminGameAccounts = data.accounts;
        filters.disabled = false;
        renderAdminGameAccounts();
    } catch (error) {
        if (request !== adminGameAccountsRequest) return;
        message.textContent = 'Daftar akun game gagal dimuat.';
        retry.hidden = false;
    }
}

function renderAdminGameAccounts() {
    const query = document.getElementById('adminGameAccountsSearch').value.trim().toLowerCase().replace(/^@/, '');
    const status = document.getElementById('adminGameAccountsStatus').value;
    const matches = adminGameAccounts.filter(account => {
        const statusMatches = status === 'all' || account.archived === (status === 'archived');
        return statusMatches && [account.name, account.id, account.owner_name, account.owner_username]
            .some(value => value?.toLowerCase().includes(query));
    });
    const message = document.getElementById('adminGameAccountsMessage');
    message.textContent = matches.length
        ? `${adminNumber.format(matches.length)} dari ${adminNumber.format(adminGameAccounts.length)} akun`
        : adminGameAccounts.length ? 'Tidak ada akun yang cocok.' : 'Belum ada akun game terdaftar.';
    document.getElementById('adminGameAccountsList').innerHTML = matches.map(account => {
        const owner = [account.owner_name, account.owner_username && `@${account.owner_username}`].filter(Boolean).join(' · ');
        const state = account.archived ? 'Diarsipkan' : 'Tidak diarsipkan';
        return `<li><div><strong>${escapeHtml(account.name)}</strong>
            <p class="meta">Pemilik ${escapeHtml(owner || 'tidak tercatat')}</p>
            <p class="meta">ID <code>${escapeHtml(account.id)}</code></p></div>
            <span class="admin-account-status${account.archived ? ' archived' : ''}">${state}</span></li>`;
    }).join('');
}

function renderAdminOverview(overview, users, pending) {
    const { accounts, workers, maintenance, notifications } = overview;
    const format = value => adminNumber.format(value);
    const setText = (id, value) => { document.getElementById(id).textContent = value; };
    const maintenanceLabels = { active: 'Aktif', scheduled: 'Terjadwal', ended: 'Selesai', off: 'Nonaktif' };
    const target = maintenance.target === 'all' ? 'Semua aktivitas' : 'Auto Ojol';
    const maintenanceStatus = maintenance.target
        ? `${maintenanceLabels[maintenance.state]} · ${target}${maintenance.manual ? ' · Jeda manual' : ''}`
        : maintenanceLabels[maintenance.state];
    const capacityFull = workers.used >= workers.limit;

    setText('adminPendingCount', format(pending.length));
    setText('adminApprovedCount', format(users.filter(user => user.status === 'approved').length));
    setText('adminUserBreakdown', `${format(users.length)} total · ${format(users.filter(user => user.status === 'rejected').length)} ditolak/nonaktif`);
    setText('adminAccountCount', format(accounts.registered));
    setText('adminArchivedCount', `${format(accounts.archived)} diarsipkan`);
    setText('adminUnreadErrors', format(notifications.unread_errors));
    setText('adminNoticeScope', `Dari ${format(notifications.reviewed)} notifikasi terbaru`);
    setText('adminWorkerCount', format(workers.used));
    setText('adminWorkerLimit', `dari ${format(workers.limit)} slot terpakai`);
    setText('adminWorkerAvailable', capacityFull
        ? 'Kapasitas worker penuh.'
        : `${format(workers.limit - workers.used)} slot masih tersedia.`);
    document.getElementById('adminWorkerFill').style.width = `${Math.min(workers.used / workers.limit, 1) * 100}%`;
    setText('adminMaintenanceSummary', maintenanceStatus);

    const recommendations = [];
    if (maintenance.state === 'active') {
        recommendations.push(['Tinjau maintenance aktif', `${target} sedang dijeda. Periksa kapan aktivitas bisa dilanjutkan.`, '<a class="admin-action" href="#admin-maintenance">Lihat jadwal</a>']);
    }
    if (notifications.unread_errors > 0) {
        recommendations.push(['Periksa error runtime', `${format(notifications.unread_errors)} error belum dibaca di log global.`, '<button class="admin-action" type="button" onclick="openAdminFeed(true)">Lihat error</button>']);
    }
    if (pending.length > 0) {
        recommendations.push(['Tinjau pendaftaran', `${format(pending.length)} pengajuan menunggu keputusan.`, '<a class="admin-action" href="#admin-pending">Buka antrean</a>']);
    }
    if (capacityFull) {
        recommendations.push(['Periksa kapasitas worker', 'Tinjau batas sebelum menjalankan worker tambahan.', '<a class="admin-action" href="#admin-server-settings">Lihat batas</a>']);
    }
    if (maintenance.state === 'scheduled') {
        recommendations.push(['Periksa jadwal maintenance', maintenance.description, '<a class="admin-action" href="#admin-maintenance">Lihat jadwal</a>']);
    }

    const priorities = document.getElementById('adminPriorities');
    priorities.innerHTML = recommendations.map(([title, description, action]) => `
        <li><div><strong>${title}</strong><p class="meta">${escapeHtml(description)}</p></div>${action}</li>
    `).join('');
    priorities.hidden = recommendations.length === 0;
    const emptyPriorities = document.getElementById('adminPrioritiesEmpty');
    emptyPriorities.textContent = 'Tidak ada tindakan yang disarankan dari data ringkasan.';
    emptyPriorities.hidden = !priorities.hidden;

    const activity = document.getElementById('adminActivity');
    activity.innerHTML = notifications.recent.map(notice => {
        const title = String(notice.text || '').split('\n', 1)[0].trim();
        const date = new Date(notice.time);
        const when = Number.isNaN(date.getTime()) ? notice.time : adminDate.format(date);
        return `<li><div class="admin-log-entry"><strong>${escapeHtml(title || 'Notifikasi')}</strong>
            <p class="meta">${notice.is_error ? '<span class="admin-error-label">Error</span> · ' : ''}${escapeHtml(notice.account_name)}</p></div>
            <span class="meta admin-log-time">${escapeHtml(when)}</span></li>`;
    }).join('');
    activity.hidden = notifications.recent.length === 0;
    const emptyActivity = document.getElementById('adminActivityEmpty');
    emptyActivity.textContent = 'Belum ada notifikasi global.';
    emptyActivity.hidden = !activity.hidden;
}

async function loadAdminData(refreshSettings = true) {
    const overview = document.getElementById('adminOverview');
    if (!overview) return;
    const version = ++adminLoadVersion;
    const freshness = document.getElementById('adminFreshness');
    const refresh = document.getElementById('adminRefresh');
    const settingsStatus = document.getElementById('adminSettingsStatus');
    overview.setAttribute('aria-busy', 'true');
    refresh.disabled = true;
    freshness.textContent = adminLastChecked ? 'Menyegarkan ringkasan…' : 'Memuat ringkasan…';

    const [fleet, users, settings] = await Promise.allSettled([
        apiFetch('/api/admin/overview'),
        apiFetch('/api/admin/users'),
        refreshSettings && apiFetch('/api/admin/settings'),
    ]);
    if (version !== adminLoadVersion) return;

    if (settings.status === 'fulfilled' && settings.value) {
        renderAdminSettings(settings.value);
        settingsStatus.hidden = true;
    } else if (settings.status === 'rejected') {
        settingsStatus.hidden = false;
    }

    const maintenanceStatus = document.getElementById('maintenanceStatus');
    if (fleet.status === 'fulfilled') {
        maintenanceStatus.textContent = fleet.value.maintenance.description || 'Nonaktif';
    } else if (!adminLastChecked) {
        maintenanceStatus.textContent = 'Gagal memuat jadwal.';
    }

    if (users.status === 'fulfilled') {
        const pending = users.value.filter(user => user.status === 'pending').reverse();
        renderAdminUsers(users.value, pending);
        if (fleet.status === 'fulfilled') {
            renderAdminOverview(fleet.value, users.value, pending);
            adminLastChecked = adminDate.format(new Date(fleet.value.checked_at));
        }
    } else {
        document.getElementById('pendingTableBody').innerHTML = '<tr><td colspan="5">Gagal memuat pengajuan. Pilih Segarkan untuk mencoba lagi.</td></tr>';
        document.getElementById('usersTableBody').innerHTML = '<tr><td colspan="6">Gagal memuat pengguna. Pilih Segarkan untuk mencoba lagi.</td></tr>';
    }
    const loaded = fleet.status === 'fulfilled' && users.status === 'fulfilled';
    freshness.textContent = loaded ? `Diperbarui ${adminLastChecked}` : adminLastChecked
        ? `Gagal menyegarkan · data ${adminLastChecked}` : 'Ringkasan gagal dimuat';
    if (!loaded && !adminLastChecked) {
        document.getElementById('adminPrioritiesEmpty').textContent = 'Rekomendasi belum tersedia.';
        document.getElementById('adminActivityEmpty').textContent = 'Aktivitas global belum tersedia.';
        document.getElementById('adminWorkerAvailable').textContent = 'Kapasitas worker belum tersedia.';
        document.getElementById('adminMaintenanceSummary').textContent = 'Status maintenance belum tersedia.';
    }
    overview.setAttribute('aria-busy', 'false');
    refresh.disabled = false;
}

function renderAdminUsers(users, pending) {
    const pTbody = document.getElementById('pendingTableBody');
    pTbody.innerHTML = '';
    if (!pending.length) {
        pTbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">Tidak ada pengajuan tertunda.</td></tr>';
    } else {
        pending.forEach(p => {
            const tr = document.createElement('tr');
            const dt = new Date(p.created_at * 1000).toLocaleString('id-ID');
            tr.innerHTML = `
                <td data-label="ID">#${p.id}</td>
                <td class="admin-user-name"><strong>${escapeHtml(p.username)}</strong></td>
                <td data-label="Nama">${escapeHtml(p.name || '—')}</td>
                <td data-label="Daftar">${dt}</td>
                <td>
                    <button class="btn btn-success" onclick="reviewUser(${p.id}, true)">Setujui</button>
                    <button class="btn btn-danger" onclick="reviewUser(${p.id}, false)">Tolak</button>
                </td>
            `;
            pTbody.appendChild(tr);
        });
    }

    const uTbody = document.getElementById('usersTableBody');
    uTbody.innerHTML = '';
    users.forEach(u => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td data-label="ID">#${u.id}</td>
            <td class="admin-user-name"><strong>${escapeHtml(u.username)}</strong></td>
            <td data-label="Nama">${escapeHtml(u.name || '—')}</td>
            <td data-label="Peran"><span style="padding: 2px 6px; border-radius: 4px; background: ${u.role === 'admin' ? 'rgba(59, 130, 246, 0.2)' : 'rgba(255, 255, 255, 0.05)'}; color: ${u.role === 'admin' ? 'var(--primary)' : 'inherit'};">${u.role}</span></td>
            <td data-label="Status"><span style="color: ${u.status === 'approved' ? 'var(--success)' : u.status === 'pending' ? 'var(--warning)' : 'var(--danger)'};">${u.status}</span></td>
            <td>
                ${u.role === 'admin' ? '' : u.status === 'approved' ? `<button class="btn btn-danger" onclick="reviewUser(${u.id}, false)">Nonaktifkan</button>` : `<button class="btn btn-success" onclick="reviewUser(${u.id}, true)">Aktifkan</button>`}
                ${u.status === 'approved' ? `<button class="btn btn-secondary" type="button" onclick="openAdminUserLimits(${u.id}, this)">Batas pengguna</button>` : ''}
                ${u.status === 'approved' && u.role !== 'admin' ? `<button class="btn btn-secondary" type="button" onclick="impersonateWebUser(${u.id}, this)">Masuk sebagai</button>` : ''}
            </td>
        `;
        uTbody.appendChild(tr);
    });
}

function renderAdminSettings(s) {
    if (!s) return;
    const setVal = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.value = (val !== null && val !== undefined) ? val : '';
    };
    const setChk = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.checked = !!val;
    };

    setVal('setting_threshold', s.threshold);
    setChk('setting_smart_thresholds', s.smart_thresholds);
    setVal('setting_resource_reserve_percent', s.resource_reserve_percent);
    setVal('setting_min_balance', s.min_balance);
    setVal('setting_max_spend', s.max_spend);
    setVal('setting_max_jobs', s.max_jobs);
    setVal('setting_max_minutes', s.max_minutes);
    setVal('setting_idle_poll_seconds', s.idle_poll_seconds);
    setVal('setting_ojol_mode', s.ojol_mode || 'otomatis');

    setVal('setting_max_accounts_per_user', s.max_accounts_per_user);
    setVal('setting_max_active_workers', s.max_active_workers);
    setChk('setting_auto_start', s.auto_start);

    setVal('setting_login_public_url', s.login_public_url);
    setChk('setting_tunnel_enabled', s.tunnel_enabled);
}

async function saveAdminSettings() {
    const getVal = (id) => {
        const el = document.getElementById(id);
        const v = el ? el.value.trim() : '';
        return v !== '' ? v : null;
    };
    const getChk = (id) => {
        const el = document.getElementById(id);
        return el ? el.checked : false;
    };

    const payload = {
        threshold: getVal('setting_threshold'),
        smart_thresholds: getChk('setting_smart_thresholds'),
        resource_reserve_percent: getVal('setting_resource_reserve_percent'),
        min_balance: getVal('setting_min_balance'),
        max_spend: getVal('setting_max_spend'),
        max_jobs: getVal('setting_max_jobs'),
        max_minutes: getVal('setting_max_minutes'),
        idle_poll_seconds: getVal('setting_idle_poll_seconds'),
        ojol_mode: getVal('setting_ojol_mode'),
        max_accounts_per_user: getVal('setting_max_accounts_per_user'),
        max_active_workers: getVal('setting_max_active_workers'),
        auto_start: getChk('setting_auto_start'),
        login_public_url: getVal('setting_login_public_url'),
        tunnel_enabled: getChk('setting_tunnel_enabled'),
    };

    try {
        const res = await fetch('/api/admin/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || data.message || 'Gagal menyimpan pengaturan');
        renderAdminSettings(data.settings);
        loadAdminData(false);
        alert('✅ Pengaturan admin berhasil disimpan dan diterapkan!');
        refreshDashboard();
    } catch (e) {
        alert('Gagal menyimpan: ' + e.message);
    }
}

async function saveMaintenance(event) {
    event.preventDefault();
    const value = id => document.getElementById(id).value;
    try {
        const data = await apiFetch('/api/admin/maintenance', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                mode: value('maintenanceMode'),
                target: value('maintenanceTarget'),
                start: value('maintenanceStart').replace('T', ' '),
                end: value('maintenanceEnd').replace('T', ' ')
            })
        });
        document.getElementById('maintenanceStatus').textContent = data.description || 'Nonaktif';
        loadAdminData(false);
        await refreshDashboard();
    } catch (error) {
        showToast(error.message, 'error');
    }
}

let adminUserLimitsState = null;
let adminUserLimitsRequest = 0;

async function openAdminUserLimits(userId, trigger) {
    const request = ++adminUserLimitsRequest;
    const form = document.getElementById('adminUserLimitsForm');
    const preview = document.getElementById('adminUserLimitsPreview');
    const username = document.getElementById('adminUserLimitsUsername');
    const message = document.getElementById('adminUserLimitsMessage');
    adminUserLimitsState = null;
    form.hidden = true;
    preview.hidden = true;
    username.textContent = '';
    message.textContent = 'Memuat pengaturan dan akun…';
    trigger?.focus();
    openModal('adminUserLimitsDialog');
    try {
        const data = await apiFetch(`/api/admin/users/${userId}/limits`);
        if (request !== adminUserLimitsRequest) return;
        adminUserLimitsState = {userId, ...data};
        const {limits, accounts} = data;
        username.textContent = `@${data.username}`;
        const account = document.getElementById('adminUserAccountLimit');
        const worker = document.getElementById('adminUserWorkerLimit');
        account.value = limits.account_override ?? '';
        worker.value = limits.worker_override ?? '';
        account.placeholder = limits.account_default;
        worker.placeholder = limits.worker_default;
        document.getElementById('adminUserLimitsAccounts').innerHTML = accounts.map(item => `
            <li><strong>${escapeHtml(item.name)}</strong>
            <span class="admin-account-status${item.running ? '' : ' archived'}">${item.running ? 'Worker berjalan' : 'Worker berhenti'}</span></li>
        `).join('');
        renderAdminUserLimitModes();
        document.getElementById('adminUserLimitsSubmit').disabled = false;
        message.textContent = '';
        form.hidden = false;
        preview.hidden = false;
    } catch (error) {
        if (request === adminUserLimitsRequest) message.textContent = error.message;
    }
}

function renderAdminUserLimitModes() {
    const account = document.getElementById('adminUserAccountLimit').value;
    const worker = document.getElementById('adminUserWorkerLimit').value;
    const {limits, accounts} = adminUserLimitsState;
    document.getElementById('adminUserAccountMode').textContent = account
        ? `Batas khusus · ${account} akun` : `Ikuti pengaturan utama · ${limits.account_default} akun`;
    const effectiveWorker = Math.min(Number(worker || limits.worker_default), limits.worker_default);
    document.getElementById('adminUserWorkerMode').textContent = worker
        ? `Batas khusus · ${effectiveWorker} worker efektif` : `Ikuti pengaturan utama · ${effectiveWorker} worker`;
    const running = accounts.filter(item => item.running).length;
    document.getElementById('adminUserLimitsUsage').textContent = accounts.length
        ? `${adminNumber.format(accounts.length)} akun · ${adminNumber.format(running)} worker berjalan`
        : 'Pengguna belum punya akun yang belum diarsipkan.';
}

async function saveAdminUserLimits(event) {
    event.preventDefault();
    const request = adminUserLimitsRequest;
    const {userId} = adminUserLimitsState;
    const account = document.getElementById('adminUserAccountLimit').value;
    const worker = document.getElementById('adminUserWorkerLimit').value;
    const submit = document.getElementById('adminUserLimitsSubmit');
    const message = document.getElementById('adminUserLimitsMessage');
    submit.disabled = true;
    try {
        await apiFetch(`/api/admin/users/${userId}/limits`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({account_limit: account ? Number(account) : null, worker_limit: worker ? Number(worker) : null})
        });
        if (request === adminUserLimitsRequest) message.textContent = 'Batas pengguna disimpan.';
    } catch (error) {
        if (request === adminUserLimitsRequest) message.textContent = error.message;
    } finally {
        if (request === adminUserLimitsRequest) submit.disabled = false;
    }
}

async function impersonateWebUser(userId, button) {
    button.disabled = true;
    try {
        await apiFetch('/api/admin/impersonate', {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({user_id: userId})
        });
        window.location.assign('/');
    } catch (error) {
        showToast(error.message, 'error');
        button.disabled = false;
    }
}

async function reviewUser(userId, approve) {
    try {
        const res = await fetch('/api/admin/review', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: userId, approve })
        });
        if (!res.ok) throw new Error('Gagal memproses review');
        loadAdminData(false);
    } catch (e) {
        alert(e.message);
    }
}

async function logout() {
    try {
        await fetch('/api/auth/logout', { method: 'POST' });
    } catch (e) {}
    window.location.href = '/login';
}

// ==========================================
// BANK ANGKA (CAPTCHA SOLVER REVIEW & TRAIN)
// ==========================================
const selectedReviewDigits = {};
const pendingGlyphsMap = {};
let manualSelectedDigit = '0';

function updateBankBadge(count) {
    const badge = document.getElementById('bankReviewBadge');
    const pendingBadge = document.getElementById('bankPendingCountBadge');
    const banner = document.getElementById('bankReviewBanner');
    const headerCount = document.getElementById('bankPendingHeaderCount');
    if (badge) {
        if (count > 0) {
            badge.innerText = count;
            badge.style.display = 'inline-block';
        } else {
            badge.style.display = 'none';
        }
    }
    if (pendingBadge) {
        if (count > 0) {
            pendingBadge.innerText = count;
            pendingBadge.style.display = 'inline-block';
        } else {
            pendingBadge.style.display = 'none';
        }
    }
    if (banner) {
        if (count > 0) {
            banner.style.display = 'flex';
            if (headerCount) headerCount.innerText = count;
        } else {
            banner.style.display = 'none';
        }
    }
}

function renderGlyphSvg(glyph, width = 100, height = 100, strokeColor = '#10b981') {
    if (!glyph || !Array.isArray(glyph) || glyph.length === 0) {
        return `<div style="width:${width}px;height:${height}px;background:#0f172a;border-radius:6px;display:flex;align-items:center;justify-content:center;color:#64748b;font-size:11px;">(kosong)</div>`;
    }
    const pad = 12;
    const drawW = width - pad * 2;
    const drawH = height - pad * 2;
    const allPts = [];
    for (const stroke of glyph) {
        if (Array.isArray(stroke)) {
            for (const pt of stroke) {
                if (Array.isArray(pt) && pt.length >= 2) {
                    const x = parseFloat(pt[0]);
                    const y = parseFloat(pt[1]);
                    if (!isNaN(x) && !isNaN(y)) allPts.push([x, y]);
                }
            }
        }
    }
    if (allPts.length === 0) return '';
    const minX = Math.min(...allPts.map(p => p[0]));
    const maxX = Math.max(...allPts.map(p => p[0]));
    const minY = Math.min(...allPts.map(p => p[1]));
    const maxY = Math.max(...allPts.map(p => p[1]));
    const spanX = maxX - minX || 1.0;
    const spanY = maxY - minY || 1.0;

    let polylines = '';
    for (const stroke of glyph) {
        if (!Array.isArray(stroke) || stroke.length === 0) continue;
        const ptsStr = stroke.map(pt => {
            const nx = (parseFloat(pt[0]) - minX) / spanX;
            const ny = (parseFloat(pt[1]) - minY) / spanY;
            const px = (nx * drawW + pad).toFixed(1);
            const py = (ny * drawH + pad).toFixed(1);
            return `${px},${py}`;
        }).join(' ');
        polylines += `<polyline points="${ptsStr}" fill="none" stroke="${strokeColor}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>`;
    }
    return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" style="background:#0f172a;border-radius:8px;display:block;box-shadow:inset 0 0 8px rgba(0,0,0,0.5);">${polylines}</svg>`;
}

async function loadBankAngka() {
    const listEl = document.getElementById('bankPendingList');
    const gridEl = document.getElementById('bankTemplatesGrid');
    try {
        const res = await apiFetch('/api/bank-angka');
        const templates = res.templates || {};
        const pending = res.pending || [];
        const totalTemplates = res.total_templates || 0;

        updateBankBadge(pending.length);
        const countEl = document.getElementById('bankTotalTemplatesCount');
        if (countEl) countEl.innerText = totalTemplates;
        const contribEl = document.getElementById('bankTotalContribCount');
        if (contribEl) contribEl.innerText = res.total_contributions || 0;

        // 1. Render Pending Reviews
        if (pending.length === 0) {
            listEl.innerHTML = `
                <div style="text-align: center; color: var(--success); padding: 36px 16px; background: rgba(16, 185, 129, 0.08); border-radius: 8px; border: 1px dashed rgba(16, 185, 129, 0.3);">
                    <div style="font-size: 28px; margin-bottom: 6px;">✅</div>
                    <div style="font-weight: 700; font-size: 15px;">Semua angka cek saat ini dikenali!</div>
                    <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">Tidak ada antrean review gagal cek polyline di seluruh armada.</div>
                </div>
            `;
        } else {
            listEl.innerHTML = pending.map((item, idx) => {
                const rid = escapeHtml(item.id);
                pendingGlyphsMap[item.id] = item.glyph;
                const errIdStr = item.error_id ? `<span style="background: rgba(239, 68, 68, 0.18); color: var(--danger); border-radius: 4px; padding: 2px 8px; font-weight: 700; font-size: 12px;">🚨 ${escapeHtml(item.error_id)}</span>` : '';
                const accStr = item.account_name ? `<span style="background: rgba(167, 139, 250, 0.18); color: #a78bfa; border-radius: 4px; padding: 2px 8px; font-weight: 700; font-size: 12px;">👤 Akun: ${escapeHtml(item.account_name)}</span>` : '';
                const timeStr = item.time ? new Date(item.time).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : 'Baru saja';

                let capturedSvgBlock = '';
                if (item.svg_text && item.svg_text.trim().startsWith('<svg')) {
                    let cleanSvg = item.svg_text.replace(/<svg([^>]*)>/i, '<svg $1 style="width: 180px; height: 84px; display: block; border-radius: 6px;">');
                    capturedSvgBlock = `
                        <div style="background: #0f172a; border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; display: flex; flex-direction: column; align-items: center; justify-content: center;">
                            <div style="font-size: 11px; font-weight: 700; color: #38bdf8; margin-bottom: 6px; display: flex; align-items: center; gap: 4px;">
                                <span>📸</span> GAMBAR CAPTURE GAME (2 ANGKA)
                            </div>
                            <div style="display: flex; align-items: center; justify-content: center; background: #f4efe2; border-radius: 6px; box-shadow: 0 2px 8px rgba(0,0,0,0.4); overflow: hidden;">
                                ${cleanSvg}
                            </div>
                            <div style="font-size: 10px; color: var(--text-muted); margin-top: 5px;">Tangkapan layar asli dari game</div>
                        </div>
                    `;
                }

                const focusGlyphBlock = `
                    <div style="background: #0f172a; border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; display: flex; flex-direction: column; align-items: center; justify-content: center;">
                        <div style="font-size: 11px; font-weight: 700; color: #f59e0b; margin-bottom: 6px; display: flex; align-items: center; gap: 4px;">
                            <span>🎯</span> FOKUS GLYPH YANG DILATIH
                        </div>
                        <div style="display: flex; align-items: center; justify-content: center;">
                            ${renderGlyphSvg(item.glyph, 100, 84, '#f59e0b')}
                        </div>
                        <div style="font-size: 10px; color: var(--text-muted); margin-top: 5px;">Pilih angka bentuk ini di bawah</div>
                    </div>
                `;

                return `
                    <div style="background: var(--raised); border: 1px solid var(--border); border-radius: 10px; padding: 16px; margin-bottom: 16px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; border-bottom: 1px solid var(--border); padding-bottom: 8px;">
                            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                                ${errIdStr}
                                ${accStr}
                                <span style="font-size: 12px; color: var(--text-muted);">Waktu kejadian: ${timeStr}</span>
                                ${item.trip_id ? `<span style="font-size: 11px; color: var(--text-muted); background: var(--bg); padding: 2px 6px; border-radius: 4px;">Trip: ${escapeHtml(item.trip_id)}</span>` : ''}
                            </div>
                            <span style="font-size: 12px; color: #f59e0b; font-weight: 600;">⚠️ Bot butuh konfirmasi digit</span>
                        </div>

                        <div style="display: flex; gap: 16px; flex-wrap: wrap; align-items: center; margin-bottom: 16px;">
                            ${capturedSvgBlock}
                            ${focusGlyphBlock}
                        </div>

                        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; background: var(--bg); padding: 12px 14px; border-radius: 8px; border: 1px solid var(--border);">
                            <div>
                                <div style="font-size: 13px; font-weight: 700; color: var(--text); margin-bottom: 8px;">
                                    Tentukan angka untuk bentuk yang ditandai:
                                </div>
                                <div style="display: flex; gap: 6px; flex-wrap: wrap;" id="reviewDigitsWrap_${rid}">
                                    ${[0,1,2,3,4,5,6,7,8,9].map(d => `
                                        <button type="button" class="btn btn-utility" style="padding: 6px 12px; font-weight: 700; font-size: 14px; min-width: 36px;" onclick="selectReviewDigit('${rid}', '${d}', this)">
                                            ${d}
                                        </button>
                                    `).join('')}
                                </div>
                            </div>
                            <div style="display: flex; gap: 8px; align-items: center;">
                                <button class="btn btn-secondary" type="button" onclick="dismissReview('${rid}', '${escapeHtml(item.error_id || '')}')" style="padding: 8px 14px; font-size: 12px;">Abaikan</button>
                                <button class="btn btn-primary" type="button" onclick="saveReviewToBank('${rid}', '${escapeHtml(item.error_id || '')}')" style="padding: 8px 18px; font-size: 13px; font-weight: 700;">💾 Simpan & Kontribusi ke Bank Angka</button>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
        }

        // 2. Render Bank Templates (0 - 9)
        const digits = ['0','1','2','3','4','5','6','7','8','9'];
        gridEl.innerHTML = digits.map(d => {
            const variants = templates[d] || [];
            const varCount = variants.length;
            const previews = variants.map((v, vIdx) => {
                const glyphData = v.glyph || v;
                const contributor = v.by ? escapeHtml(v.by) : null;
                const contribBadge = contributor
                    ? `<div style="font-size: 9px; color: #a78bfa; text-align: center; margin-top: 3px; max-width: 68px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="Dikontribusi oleh ${contributor}">👤 ${contributor}</div>`
                    : `<div style="font-size: 9px; color: var(--text-muted); text-align: center; margin-top: 3px;">🌱 Sistem</div>`;

                return `
                    <div style="position: relative; display: flex; flex-direction: column; align-items: center;">
                        <div style="position: relative; display: inline-block;">
                            ${renderGlyphSvg(glyphData, 68, 68, '#38bdf8')}
                            <button type="button" onclick="deleteBankVariant('${d}', ${vIdx})" title="Hapus varian ini" style="position: absolute; top: -6px; right: -6px; background: rgba(239,68,68,0.9); color: white; border: none; border-radius: 50%; width: 18px; height: 18px; font-size: 10px; cursor: pointer; display: flex; align-items: center; justify-content: center; line-height: 1;">&times;</button>
                        </div>
                        ${contribBadge}
                    </div>
                `;
            }).join('');

            return `
                <div style="background: var(--raised); border: 1px solid var(--border); border-radius: 10px; padding: 14px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; border-bottom: 1px solid var(--border); padding-bottom: 8px;">
                        <div style="font-size: 16px; font-weight: 700; display: flex; align-items: center; gap: 6px;">
                            <span style="font-size: 20px; color: var(--primary);">${d}</span>
                            <span>Angka ${d}</span>
                        </div>
                        <span style="font-size: 11px; background: rgba(56, 189, 248, 0.15); color: var(--primary); padding: 2px 8px; border-radius: 12px; font-weight: 600;">${varCount} varian</span>
                    </div>
                    <div style="display: flex; gap: 8px; flex-wrap: wrap; min-height: 70px; align-items: center;">
                        ${varCount > 0 ? previews : '<div style="color: var(--text-muted); font-size: 12px; font-style: italic;">Belum ada varian tersimpan</div>'}
                    </div>
                </div>
            `;
        }).join('');

    } catch (e) {
        listEl.innerHTML = `<div style="color: var(--danger); padding: 16px;">Gagal memuat bank angka: ${escapeHtml(e.message)}</div>`;
    }
}

function selectReviewDigit(reviewId, digit, btnEl) {
    selectedReviewDigits[reviewId] = digit;
    const wrap = document.getElementById(`reviewDigitsWrap_${reviewId}`);
    if (wrap) {
        wrap.querySelectorAll('button').forEach(b => {
            b.classList.remove('btn-primary');
            b.classList.add('btn-utility');
            b.style.background = '';
            b.style.color = '';
        });
    }
    if (btnEl) {
        btnEl.classList.remove('btn-utility');
        btnEl.classList.add('btn-primary');
    }
}

async function saveReviewToBank(reviewId, errorId) {
    const sel = selectedReviewDigits[reviewId];
    if (sel === undefined || sel === null || sel === '') {
        alert('Silakan tentukan angka (0 - 9) untuk bentuk ini terlebih dahulu!');
        return;
    }
    const glyph = pendingGlyphsMap[reviewId];
    if (!glyph) {
        alert('Data bentuk glyph tidak ditemukan.');
        return;
    }
    try {
        const res = await apiFetch('/api/bank-angka/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                digit: String(sel),
                glyph: glyph,
                review_id: reviewId,
                error_id: errorId || null
            })
        });
        if (res && res.ok) {
            delete selectedReviewDigits[reviewId];
            delete pendingGlyphsMap[reviewId];
            const retried = res.retried_accounts && res.retried_accounts.length > 0
                ? `
🚀 Langsung mencoba menyelesaikan order tertahan pada akun: ${res.retried_accounts.join(', ')}`
                : '';
            alert(`✅ Bentuk berhasil disimpan ke Bank Angka sebagai digit ${sel}!${retried}`);
            await loadBankAngka();
            manualRefreshDashboard();
        }
    } catch (e) {
        alert('Gagal menyimpan ke bank angka: ' + e.message);
    }
}

async function dismissReview(reviewId, errorId) {
    if (!confirm('Abaikan review angka ini?')) return;
    const glyph = pendingGlyphsMap[reviewId] || null;
    try {
        await apiFetch('/api/bank-angka/dismiss', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ review_id: reviewId, error_id: errorId || null, glyph: glyph })
        });
        delete selectedReviewDigits[reviewId];
        delete pendingGlyphsMap[reviewId];
        await loadBankAngka();
        manualRefreshDashboard();
    } catch (e) {
        alert('Gagal mengabaikan: ' + e.message);
    }
}

async function deleteBankVariant(digit, index) {
    if (!confirm(`Hapus varian ke-${index + 1} dari angka ${digit}?`)) return;
    try {
        await apiFetch('/api/bank-angka/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ digit: String(digit), index: index })
        });
        await loadBankAngka();
    } catch (e) {
        alert('Gagal menghapus varian: ' + e.message);
    }
}

function openManualGlyphModal() {
    document.getElementById('manualGlyphJson').value = '';
    document.getElementById('manualGlyphPreview').style.display = 'none';
    manualSelectedDigit = '0';
    updateManualDigitButtons();
    openModal('manualGlyphModal');
}

function updateManualDigitButtons() {
    const wrap = document.getElementById('manualDigitButtons');
    if (!wrap) return;
    wrap.innerHTML = [0,1,2,3,4,5,6,7,8,9].map(d => `
        <button type="button" class="btn ${String(d) === String(manualSelectedDigit) ? 'btn-primary' : 'btn-utility'}" style="padding: 4px 10px; font-weight: 700; font-size: 13px;" onclick="selectManualDigit('${d}')">
            ${d}
        </button>
    `).join('');
}

function selectManualDigit(digit) {
    manualSelectedDigit = String(digit);
    updateManualDigitButtons();
}

function onManualGlyphInput() {
    const val = document.getElementById('manualGlyphJson').value.trim();
    const preview = document.getElementById('manualGlyphPreview');
    const wrap = document.getElementById('manualGlyphSvgWrap');
    if (!val) {
        preview.style.display = 'none';
        return;
    }
    try {
        const parsed = JSON.parse(val);
        if (Array.isArray(parsed)) {
            wrap.innerHTML = renderGlyphSvg(parsed, 120, 120, '#10b981');
            preview.style.display = 'block';
        }
    } catch (_) {
        preview.style.display = 'none';
    }
}

async function submitManualGlyph() {
    const val = document.getElementById('manualGlyphJson').value.trim();
    if (!val) {
        alert('Silakan masukkan data JSON glyph');
        return;
    }
    let glyph;
    try {
        glyph = JSON.parse(val);
        if (!Array.isArray(glyph) || glyph.length === 0) throw new Error('Format harus berupa array stroke');
    } catch (e) {
        alert('Format JSON glyph tidak valid: ' + e.message);
        return;
    }
    try {
        const res = await apiFetch('/api/bank-angka/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                digit: manualSelectedDigit,
                glyph: glyph
            })
        });
        if (res && res.ok) {
            alert(`✅ Angka ${manualSelectedDigit} berhasil ditambahkan ke bank!`);
            closeModal('manualGlyphModal');
            loadBankAngka();
        }
    } catch (e) {
        alert('Gagal menyimpan: ' + e.message);
    }
}

let cachedExtensionInfo = null;

async function openExtensionModal() {
    openModal('extensionModal');
    try {
        const info = await apiFetch('/api/extension/info');
        cachedExtensionInfo = info;
        document.getElementById('extInfoVersion').textContent = `v${info.version}`;
        document.getElementById('extInfoId').textContent = info.extension_id;
        document.getElementById('extInfoPolicy').textContent = info.policy_value;
        document.getElementById('extMacCmd').textContent =
            `defaults write com.google.Chrome ExtensionInstallForcelist -array-add "${info.policy_value}"`;
    } catch (e) {
        document.getElementById('extInfoVersion').textContent = 'gagal memuat';
        document.getElementById('extInfoId').textContent = '-';
        document.getElementById('extInfoPolicy').textContent = e.message || 'gagal memuat';
    }
}

async function copyExtensionPolicy() {
    const text = cachedExtensionInfo?.policy_value || document.getElementById('extInfoPolicy')?.textContent || '';
    if (!text || text === 'memuat...') return;
    try {
        await navigator.clipboard.writeText(text);
        showToast('Policy string disalin ke clipboard.', 'success');
    } catch (_) {
        showToast('Salin manual dari kotak Policy.', 'info');
    }
}

// Initial setup
loadNotifications();
refreshDashboard();
startLiveStream();
setInterval(() => { if (!streamConnected) refreshDashboard(); }, 5000);
