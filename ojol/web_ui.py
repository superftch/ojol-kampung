"""Embedded Web UI for Kampung Ojol Automation."""

import html
import json

BRAND_MARK = """<svg class="brand-mark" viewBox="0 0 32 32" fill="none" aria-hidden="true"><path d="M4 27h24M7 27l5-22m13 22L20 5m-4 7v4m0 5v3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="16" cy="5" r="2" fill="currentColor"/></svg>"""


def login_html(
    bot_username: str = "", error: str = "", success: str = "", default_code: str = ""
) -> str:
    escaped_error = html.escape(error) if error else ""
    escaped_success = html.escape(success) if success else ""
    escaped_code = html.escape(default_code) if default_code else ""
    telegram_widget = ""
    if bot_username:
        telegram_widget = f"""
        <div class="tg-widget-container">
            <script async src="https://telegram.org/js/telegram-widget.js?22"
                    data-telegram-login="{html.escape(bot_username)}"
                    data-size="large"
                    data-auth-url="/api/auth/telegram/callback"
                    data-request-access="write"></script>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login · Kampung Ojol Automation</title>
    <style>
        :root {{
            --bg: #0f172a;
            --card: #1e293b;
            --card-border: #334155;
            --text: #f8fafc;
            --text-muted: #94a3b8;
            --primary: #3b82f6;
            --primary-hover: #2563eb;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --radius: 12px;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: var(--bg);
            color: var(--text);
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            padding: 20px;
        }}
        .card {{
            background: var(--card);
            border: 1px solid var(--card-border);
            border-radius: var(--radius);
            width: 100%;
            max-width: 440px;
            padding: 32px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);
        }}
        .logo {{
            text-align: center;
            margin-bottom: 24px;
        }}
        .logo-icon {{ font-size: 40px; }}
        .logo h1 {{ font-size: 22px; font-weight: 700; margin-top: 8px; }}
        .logo p {{ font-size: 14px; color: var(--text-muted); margin-top: 4px; }}
        .tabs {{
            display: flex;
            border-bottom: 1px solid var(--card-border);
            margin-bottom: 24px;
        }}
        .tab {{
            flex: 1;
            padding: 12px;
            text-align: center;
            font-size: 14px;
            font-weight: 600;
            color: var(--text-muted);
            cursor: pointer;
            border-bottom: 2px solid transparent;
            transition: all 0.2s;
        }}
        .tab.active {{
            color: var(--primary);
            border-bottom-color: var(--primary);
        }}
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
        .form-group {{ margin-bottom: 16px; }}
        label {{ display: block; font-size: 13px; font-weight: 500; color: var(--text-muted); margin-bottom: 6px; }}
        input[type="text"], input[type="password"] {{
            width: 100%;
            padding: 12px 14px;
            background: #0f172a;
            border: 1px solid var(--card-border);
            border-radius: 8px;
            color: var(--text);
            font-size: 14px;
            outline: none;
            transition: border-color 0.2s;
        }}
        input[type="text"]:focus, input[type="password"]:focus {{
            border-color: var(--primary);
        }}
        .btn {{
            display: block;
            width: 100%;
            padding: 12px;
            background: var(--primary);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
            text-align: center;
            text-decoration: none;
        }}
        .btn:hover {{ background: var(--primary-hover); }}
        .btn-tg {{
            background: #229ed9;
            margin-top: 12px;
        }}
        .btn-tg:hover {{ background: #1c88bd; }}
        .alert {{
            padding: 12px;
            border-radius: 8px;
            font-size: 13px;
            margin-bottom: 16px;
        }}
        .alert-danger {{ background: rgba(239, 68, 68, 0.15); border: 1px solid var(--danger); color: #fca5a5; }}
        .alert-success {{ background: rgba(16, 185, 129, 0.15); border: 1px solid var(--success); color: #6ee7b7; }}
        .alert-info {{ background: rgba(59, 130, 246, 0.15); border: 1px solid var(--primary); color: #93c5fd; }}
        .footer-links {{ text-align: center; margin-top: 20px; font-size: 13px; color: var(--text-muted); }}
        .footer-links a {{ color: var(--primary); text-decoration: none; font-weight: 500; }}
        .footer-links a:hover {{ text-decoration: underline; }}
        .tg-box {{
            background: #0f172a;
            border: 1px solid var(--card-border);
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 16px;
            text-align: center;
        }}
        .tg-box p {{ font-size: 13px; color: var(--text-muted); margin-bottom: 12px; line-height: 1.5; }}
        .tg-box code {{ background: #1e293b; padding: 2px 6px; border-radius: 4px; color: #38bdf8; font-weight: 600; }}
        .divider {{
            display: flex;
            align-items: center;
            margin: 20px 0;
            color: var(--text-muted);
            font-size: 12px;
        }}
        .divider::before, .divider::after {{
            content: "";
            flex: 1;
            border-bottom: 1px solid var(--card-border);
        }}
        .divider span {{ padding: 0 10px; }}
        .tg-widget-container {{ display: flex; justify-content: center; margin: 12px 0; min-height: 44px; }}
    </style>
    <link rel="stylesheet" href="/ui/console.css">
</head>
<body class="auth-page">
    <div class="card">
        <div class="logo">
            {BRAND_MARK}
            <h1>Kampung Ojol Automation</h1>
            <p>Kelola akun dan aktivitas Ojol.</p>
        </div>

        {f'<div class="alert alert-danger">{escaped_error}</div>' if escaped_error else ""}
        {f'<div class="alert alert-success">{escaped_success}</div>' if escaped_success else ""}

        {
        '''
        <div class="tabs">
            <button class="tab active" type="button" onclick="switchTab('tab-password')">Username & Password</button>
            <button class="tab" type="button" onclick="switchTab('tab-telegram')">Telegram</button>
        </div>
        '''
        if bot_username
        else ""
    }

        <!-- Tab 1: Username & Password -->
        <div id="tab-password" class="tab-content active">
            <form action="/api/auth/login" method="POST">
                <div class="form-group">
                    <label for="username">Username</label>
                    <input type="text" id="username" name="username" required autocomplete="username" placeholder="Masukkan username">
                </div>
                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required autocomplete="current-password" placeholder="Masukkan password">
                </div>
                <button type="submit" class="btn">Masuk</button>
            </form>
            <div class="footer-links">
                Belum punya akun? <a href="/register">Daftar sekarang</a>
            </div>
        </div>

        {
        f'''
        <!-- Tab 2: Telegram -->
        <div id="tab-telegram" class="tab-content">
            <div class="tg-box">
                <p>Login praktis menggunakan akun Telegram Anda.</p>
                {telegram_widget}
            </div>

            <div class="divider"><span>ATAU DENGAN KODE BOT</span></div>

            <div class="tg-box">
                <p>Buka bot Telegram Anda, kirim <code>/web</code> atau <code>/login</code> untuk mendapatkan 6-digit kode login.</p>
                <form action="/api/auth/telegram-code" method="POST">
                    <div class="form-group">
                        <input type="text" name="code" value="{escaped_code}" required placeholder="Contoh: 123456" maxlength="10" style="text-align: center; font-size: 18px; letter-spacing: 4px; font-weight: bold;">
                    </div>
                    <button type="submit" class="btn btn-tg">Masuk dengan Kode</button>
                </form>
            </div>
        </div>
        '''
        if bot_username
        else ""
    }
    </div>

    <script>
        function switchTab(id) {{
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            if (id === 'tab-password') {{
                document.querySelectorAll('.tab')[0].classList.add('active');
            }} else {{
                document.querySelectorAll('.tab')[1].classList.add('active');
            }}
            document.getElementById(id).classList.add('active');
        }}

        // If code in query param, switch to telegram tab automatically
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.get('code')) {{
            switchTab('tab-telegram');
        }}
    </script>
</body>
</html>
"""


def register_html(error: str = "", success: str = "") -> str:
    escaped_error = html.escape(error) if error else ""
    escaped_success = html.escape(success) if success else ""

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Daftar Akun · Kampung Ojol Automation</title>
    <style>
        :root {{
            --bg: #0f172a;
            --card: #1e293b;
            --card-border: #334155;
            --text: #f8fafc;
            --text-muted: #94a3b8;
            --primary: #3b82f6;
            --primary-hover: #2563eb;
            --success: #10b981;
            --danger: #ef4444;
            --radius: 12px;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: var(--bg);
            color: var(--text);
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            padding: 20px;
        }}
        .card {{
            background: var(--card);
            border: 1px solid var(--card-border);
            border-radius: var(--radius);
            width: 100%;
            max-width: 440px;
            padding: 32px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);
        }}
        .logo {{ text-align: center; margin-bottom: 24px; }}
        .logo-icon {{ font-size: 40px; }}
        .logo h1 {{ font-size: 22px; font-weight: 700; margin-top: 8px; }}
        .logo p {{ font-size: 14px; color: var(--text-muted); margin-top: 4px; }}
        .form-group {{ margin-bottom: 16px; }}
        label {{ display: block; font-size: 13px; font-weight: 500; color: var(--text-muted); margin-bottom: 6px; }}
        input[type="text"], input[type="password"] {{
            width: 100%;
            padding: 12px 14px;
            background: #0f172a;
            border: 1px solid var(--card-border);
            border-radius: 8px;
            color: var(--text);
            font-size: 14px;
            outline: none;
            transition: border-color 0.2s;
        }}
        input[type="text"]:focus, input[type="password"]:focus {{
            border-color: var(--primary);
        }}
        .btn {{
            display: block;
            width: 100%;
            padding: 12px;
            background: var(--primary);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
            text-align: center;
        }}
        .btn:hover {{ background: var(--primary-hover); }}
        .alert {{
            padding: 12px;
            border-radius: 8px;
            font-size: 13px;
            margin-bottom: 16px;
        }}
        .alert-danger {{ background: rgba(239, 68, 68, 0.15); border: 1px solid var(--danger); color: #fca5a5; }}
        .alert-success {{ background: rgba(16, 185, 129, 0.15); border: 1px solid var(--success); color: #6ee7b7; }}
        .alert-info {{ background: rgba(59, 130, 246, 0.15); border: 1px solid var(--primary); color: #93c5fd; }}
        .footer-links {{ text-align: center; margin-top: 20px; font-size: 13px; color: var(--text-muted); }}
        .footer-links a {{ color: var(--primary); text-decoration: none; font-weight: 500; }}
        .footer-links a:hover {{ text-decoration: underline; }}
    </style>
    <link rel="stylesheet" href="/ui/console.css">
</head>
<body class="auth-page">
    <div class="card">
        <div class="logo">
            {BRAND_MARK}
            <h1>Daftar Akun Baru</h1>
            <p>Pendaftaran memerlukan persetujuan admin</p>
        </div>

        {f'<div class="alert alert-danger">{escaped_error}</div>' if escaped_error else ""}
        {f'<div class="alert alert-success">{escaped_success}</div>' if escaped_success else ""}

        <div class="alert alert-info">
            🛡️ <strong>Catatan:</strong> Akun baru dibuat dengan status <em>pending</em> dan dapat digunakan setelah disetujui oleh admin.
        </div>

        <form action="/api/auth/register" method="POST">
            <div class="form-group">
                <label for="username">Username</label>
                <input type="text" id="username" name="username" required autocomplete="username" placeholder="Huruf kecil, angka, underscore (3-32 kar)">
            </div>
            <div class="form-group">
                <label for="name">Nama Lengkap / Panggilan</label>
                <input type="text" id="name" name="name" required placeholder="Contoh: Budi Ojol">
            </div>
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required autocomplete="new-password" placeholder="Minimal 6 karakter">
            </div>
            <div class="form-group">
                <label for="confirm_password">Konfirmasi Password</label>
                <input type="password" id="confirm_password" name="confirm_password" required autocomplete="new-password" placeholder="Ulangi password">
            </div>
            <button type="submit" class="btn">Daftar Akun</button>
        </form>

        <div class="footer-links">
            Sudah punya akun? <a href="/login">Masuk di sini</a>
        </div>
    </div>
</body>
</html>
"""


def setup_password_html(user: dict, error: str = "") -> str:
    escaped_error = html.escape(error) if error else ""
    current_username = html.escape(user.get("username", ""))

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Lengkapi Kredensial Akun · Kampung Ojol</title>
    <style>
        :root {{
            --bg: #0f172a;
            --card: #1e293b;
            --card-border: #334155;
            --text: #f8fafc;
            --text-muted: #94a3b8;
            --primary: #3b82f6;
            --primary-hover: #2563eb;
            --success: #10b981;
            --danger: #ef4444;
            --radius: 12px;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: var(--bg);
            color: var(--text);
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            padding: 20px;
        }}
        .card {{
            background: var(--card);
            border: 1px solid var(--card-border);
            border-radius: var(--radius);
            width: 100%;
            max-width: 440px;
            padding: 32px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);
        }}
        .logo {{ text-align: center; margin-bottom: 24px; }}
        .logo-icon {{ font-size: 40px; }}
        .logo h1 {{ font-size: 22px; font-weight: 700; margin-top: 8px; }}
        .logo p {{ font-size: 14px; color: var(--text-muted); margin-top: 4px; }}
        .form-group {{ margin-bottom: 16px; }}
        label {{ display: block; font-size: 13px; font-weight: 500; color: var(--text-muted); margin-bottom: 6px; }}
        input[type="text"], input[type="password"] {{
            width: 100%;
            padding: 12px 14px;
            background: #0f172a;
            border: 1px solid var(--card-border);
            border-radius: 8px;
            color: var(--text);
            font-size: 14px;
            outline: none;
            transition: border-color 0.2s;
        }}
        input[type="text"]:focus, input[type="password"]:focus {{
            border-color: var(--primary);
        }}
        .btn {{
            display: block;
            width: 100%;
            padding: 12px;
            background: var(--primary);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
            text-align: center;
            text-decoration: none;
        }}
        .btn:hover {{ background: var(--primary-hover); }}
        .alert {{
            padding: 12px;
            border-radius: 8px;
            font-size: 13px;
            margin-bottom: 16px;
        }}
        .alert-danger {{ background: rgba(239, 68, 68, 0.15); border: 1px solid var(--danger); color: #fca5a5; }}
        .alert-info {{ background: rgba(59, 130, 246, 0.15); border: 1px solid var(--primary); color: #93c5fd; }}
    </style>
    <link rel="stylesheet" href="/ui/console.css">
</head>
<body class="auth-page">
    <div class="card">
        <div class="logo">
            {BRAND_MARK}
            <h1>Buat Akun Web Anda</h1>
            <p>Lengkapi kredensial untuk login mandiri</p>
        </div>

        {f'<div class="alert alert-danger">{escaped_error}</div>' if escaped_error else ""}

        <div class="alert alert-info">
            💬 Anda masuk menggunakan Telegram. Silakan tentukan <strong>Username</strong> dan <strong>Password</strong> agar Anda dapat login langsung dari web browser kapan saja.
        </div>

        <form action="/api/auth/setup-password" method="POST">
            <div class="form-group">
                <label for="username">Username Pilihan</label>
                <input type="text" id="username" name="username" value="{current_username}" required autocomplete="username" placeholder="3-32 karakter alfanumerik">
            </div>
            <div class="form-group">
                <label for="password">Password Baru</label>
                <input type="password" id="password" name="password" required autocomplete="new-password" placeholder="Minimal 6 karakter">
            </div>
            <div class="form-group">
                <label for="confirm_password">Ulangi Password</label>
                <input type="password" id="confirm_password" name="confirm_password" required autocomplete="new-password" placeholder="Konfirmasi password baru">
            </div>
            <button type="submit" class="btn">Simpan & Masuk ke Dashboard</button>
        </form>
    </div>
</body>
</html>
"""


def meters_html(fields):
    return "".join(
        f"""<div class="meter-row">
            <div class="meter-label">
                <span id="{key}Label">{label}</span>
                <span id="{key}Text" class="meter-val">—</span>
            </div>
            <div class="meter-bar" aria-hidden="true"><div id="{key}Bar" class="meter-fill" style="width:0"></div></div>
        </div>"""
        for key, label in fields
    )


def dashboard_html(user: dict, bot_username: str = "") -> str:
    user_json = json.dumps(user).replace("<", "\\u003c")

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard · Kampung Ojol Automation</title>
    <link rel="stylesheet" href="/ui/console.css">
</head>
<body class="app-shell">
    <header class="app-header">
        <div class="brand">
            {BRAND_MARK}
            <span>Kampung Ojol</span>
        </div>
        <div class="header-actions">
            <div class="account-select-wrap">
                <select id="accountDropdown" class="account-select" aria-label="Pilih akun game" onchange="switchAccount(this.value)">
                    <option value="">Memuat akun...</option>
                </select>
            </div>
            <div class="user-badge" title="Pengguna web">
                <span id="navUsername">{html.escape(user.get("username", "User"))}</span>
            </div>
            <button class="btn btn-secondary" style="padding: 6px 12px; font-size: 12px;" onclick="logout()">Keluar</button>
        </div>
    </header>

    <nav class="nav-tabs" aria-label="Navigasi utama">
        <button class="nav-btn active" aria-current="page" onclick="showTab('tab-dashboard')">Ringkasan</button>
        <button class="nav-btn" onclick="showTab('tab-auto')"><span class="nav-label-wide">Pengaturan Auto</span><span class="nav-label-short">Auto</span></button>
        <button class="nav-btn" onclick="showTab('tab-accounts')">Akun</button>
        <button class="nav-btn" onclick="showTab('tab-notifications')">Notifikasi <span id="notifBadge" class="nav-count" style="display: none;">0</span></button>
        <button class="nav-btn" onclick="showTab('tab-bank-angka')">Bank Angka <span id="bankReviewBadge" class="nav-count" style="display: none; background: var(--danger, #ef4444); color: white;">0</span></button>
        <button id="adminTabBtn" class="nav-btn" style="display: {
        "block" if user.get("role") == "admin" else "none"
    };" onclick="showTab('tab-admin')">Admin</button>
    </nav>

    <main class="container">
        <!-- TAB 1: DASHBOARD -->
        <div id="tab-dashboard" class="tab-panel active">

            <div class="page-title">
                <div>
                    <h1>Ringkasan armada</h1>
                    <p>Pantau akun dan kelola aktivitas Ojol.</p>
                </div>
                <div class="page-title-actions">
                    <span id="dashboardFreshness" class="freshness" role="status">Memuat dashboard…</span>
                    <button id="btnRefreshDash" class="btn btn-utility" type="button" onclick="manualRefreshDashboard()">Segarkan</button>
                </div>
            </div>

            <div id="bankReviewBanner" class="alert alert-warning" style="display: none; margin-bottom: 20px; background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.35); border-radius: 8px; padding: 14px 18px; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap;">
                <div style="display: flex; align-items: center; gap: 10px;">
                    <span style="font-size: 20px;">🚨</span>
                    <div>
                        <div style="font-weight: 700; color: var(--danger, #ef4444); font-size: 14px;">Ada <span id="bankPendingHeaderCount">0</span> angka cek belum dikenali bot!</div>
                        <div style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">Order ojol gagal memecahkan captcha angka baru. Silakan tentukan angkanya agar bot dapat melanjutkan order.</div>
                    </div>
                </div>
                <button class="btn btn-primary" type="button" onclick="showTab('tab-bank-angka')" style="padding: 6px 14px; font-size: 12px; font-weight: 700;">Review Angka Sekarang</button>
            </div>
            <section id="onboardingCard" class="card onboarding" hidden aria-labelledby="onboardingTitle">
                <h2 id="onboardingTitle" class="card-title">Hubungkan akun game</h2>
                <p class="meta">Impor cookie sesi KampungSebelah untuk mulai mengelola akun ini.</p>
                <div class="onboarding-fields">
                    <label for="onboardingAccountName">Nama akun <span class="meta">(opsional)</span></label>
                    <input id="onboardingAccountName" type="text" placeholder="Gunakan nama karakter" maxlength="40">
                    <label for="onboardingCookieInput">Cookie sesi game</label>
                    <textarea id="onboardingCookieInput" class="cookie-box" rows="4" placeholder="Tempel nilai token atau JSON cookie" spellcheck="false" autocomplete="off"></textarea>
                </div>
                <div class="actions">
                    <button id="btnOnboardingSubmit" class="btn btn-primary" type="button" onclick="submitOnboardingCookie()">Hubungkan akun</button>
                    <span id="onboardingLoadingText" class="meta" role="status" style="display: none;">Memverifikasi sesi…</span>
                </div>
            </section>
            <div id="activeDashboardSection" hidden>
                <dl class="card fleet-stats" aria-label="Ringkasan seluruh akun">
                    <div><dt>Worker berjalan</dt><dd id="fleetCountWorkers">—</dd></div>
                    <div><dt>Saldo armada</dt><dd id="fleetTotalWallet">—</dd></div>
                    <div><dt>Penghasilan hari ini</dt><dd id="fleetTotalIncome">—</dd></div>
                    <div><dt>Trip hari ini</dt><dd id="fleetTotalTrips">—</dd></div>
                </dl>

                <div class="ops-grid">
                    <div class="account-workbench">
                        <section class="card account-card" aria-labelledby="activeAccountBannerName">
                            <div class="account-header">
                                <div>
                                    <h2 id="activeAccountBannerName">Akun terpilih</h2>
                                    <p id="statusTitle">Memuat status akun…</p>
                                </div>
                                <button id="btnCookieToolbar" class="btn btn-utility" type="button" onclick="openCookieModalFor()">Cookie akun</button>
                            </div>
                            <dl class="account-metrics">
                                <div><dt>Saldo akun</dt><dd id="walletVal">—</dd></div>
                                <div><dt>Trip akun</dt><dd id="tripsVal">—</dd></div>
                                <div><dt>Aktivitas game</dt><dd id="countdownVal">—</dd><span id="presenceVal" class="meta"></span></div>
                            </dl>
                            <div class="control-toolbar" aria-label="Kontrol otomatisasi">
                                <div class="control-group">
                                    <div><span class="control-group-title">Auto Ojol</span><span id="toolbarOjolBadge" class="control-state">—</span></div>
                                    <div class="btn-segment-group">
                                        <button id="btnRunOjol" class="btn btn-primary" type="button" onclick="controlAction('run')" aria-label="Jalankan Auto Ojol">Jalankan</button>
                                        <button id="btnStopOjol" class="btn btn-stop" type="button" onclick="controlAction('stop')" aria-label="Hentikan Auto Ojol">Hentikan</button>
                                    </div>
                                </div>
                                <div class="control-group">
                                    <div><span class="control-group-title">Auto Kebutuhan</span><span id="toolbarNeedsBadge" class="control-state">—</span></div>
                                    <div class="btn-segment-group">
                                        <button id="btnRunNeeds" class="btn btn-primary" type="button" onclick="controlAction('run-needs')" aria-label="Jalankan Auto Kebutuhan">Jalankan</button>
                                        <button id="btnStopNeeds" class="btn btn-stop" type="button" onclick="controlAction('stop-needs')" aria-label="Hentikan Auto Kebutuhan">Hentikan</button>
                                    </div>
                                </div>
                            </div>
                        </section>

                        <div id="limitNoticeCard" class="notice notice-warning" hidden>
                            <strong>Batas narik harian tercapai</strong>
                            <p>Periksa sisa waktu di game sebelum mengambil order lagi.</p>
                        </div>

                        <div class="grid-2 resource-grid">
                            <section class="card vehicle-card" aria-labelledby="vehicleTitle">
                                <div class="card-header"><h2 id="vehicleTitle" class="card-title">Kendaraan & kuota</h2></div>
                                {
        meters_html((("fuel", "Bensin"), ("cond", "Kondisi mesin"), ("data", "Kuota HP")))
    }
                                <p id="spbuWaitHint" class="notice notice-warning" hidden></p>
                            </section>
                            <section class="card needs-card" aria-labelledby="needsTitle">
                                <div class="card-header">
                                    <h2 id="needsTitle" class="card-title">Kebutuhan karakter</h2>
                                    <span id="needsCardBadge" class="meta"></span>
                                </div>
                                {
        meters_html(
            (
                ("makan", "Makan"),
                ("kesehatan", "Kesehatan"),
                ("fisik", "Fisik"),
                ("rekreasi", "Rekreasi"),
                ("kebersihan", "Kebersihan"),
                ("wc", "Buang air"),
                ("penampilan", "Penampilan"),
                ("rumah", "Kondisi rumah"),
            )
        )
    }
                            </section>
                            <section class="card activity-card" aria-labelledby="activityTitle">
                                <div class="card-header"><h2 id="activityTitle" class="card-title">Aktivitas terbaru</h2></div>
                                <div id="logConsole" class="log-box">Memuat aktivitas…</div>
                            </section>
                        </div>
                    </div>
                    <aside class="fleet-rail" aria-labelledby="fleetTitle">
                        <div class="rail-header"><h2 id="fleetTitle">Akun armada</h2><span id="fleetCountAccounts">—</span></div>
                        <div id="fleetAccountsGrid" class="card fleet-list"></div>
                        <button class="btn btn-secondary" type="button" onclick="showTab('tab-accounts')">Kelola akun</button>
                    </aside>
                </div>
            </div>
        </div>

        <!-- TAB 2: AUTO & KEBUTUHAN -->
        <div id="tab-auto" class="tab-panel">
            <div class="page-title"><div><h1>Pengaturan Auto</h1><p>Pilih aktivitas untuk akun yang sedang ditampilkan.</p></div></div>
            <div class="grid-2">
                <div class="card">
                    <div class="card-header">
                        <h2 class="card-title">Mode berkendara</h2>
                    </div>
                    <p style="font-size: 13px; color: var(--text-muted); line-height: 1.5; margin-bottom: 12px;">
                        Kelola Auto Ojol dari Ringkasan. Kuota narik mengikuti aturan game.
                    </p>
                    <div style="background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.25); border-radius: 8px; padding: 10px 12px; font-size: 12px; color: var(--text-muted);">
                        <strong>Ekstensi Chrome</strong><br>
                        Gunakan ekstensi untuk mode berkendara di browser.<br>
                        <div style="margin-top: 8px; display: flex; gap: 8px; flex-wrap: wrap;">
                            <a href="/api/extension/download" class="btn btn-warning" style="font-size: 11px; padding: 5px 10px; background:#f59e0b; color:var(--bg); font-weight:700;">📦 Download Ekstensi (.ZIP)</a>
                            <button class="btn btn-secondary" style="font-size: 11px; padding: 5px 10px;" onclick="openModal('extensionModal')">📖 Tutorial Pasang</button>
                        </div>
                    </div>
                    <input type="checkbox" id="modeOjolToggle" style="display: none;">
                </div>

                <div class="card">
                    <div class="card-header"><h2 class="card-title">Auto Belajar</h2></div>
                    <div class="toggle-item">
                        <div class="toggle-info">
                            <span class="toggle-title">📖 Auto Perpustakaan (Gratis)</span>
                            <span class="toggle-desc">Menjalankan kuis belajar gratis di perpustakaan secara otomatis</span>
                        </div>
                        <label class="switch">
                            <input type="checkbox" id="autoPerpusToggle" aria-label="Auto Perpustakaan" onchange="toggleAuto('perpus', this.checked)">
                            <span class="slider"></span>
                        </label>
                    </div>
                    <div class="toggle-item">
                        <div class="toggle-info">
                            <span class="toggle-title">🎓 Auto Kuliah (Berbayar)</span>
                            <span class="toggle-desc">Mengikuti kuliah otomatis di kampus (biaya koin) hingga level maksimal</span>
                        </div>
                        <label class="switch">
                            <input type="checkbox" id="autoKuliahToggle" aria-label="Auto Kuliah" onchange="toggleAuto('kuliah', this.checked)">
                            <span class="slider"></span>
                        </label>
                    </div>
                    <div class="toggle-item">
                        <div class="toggle-info">
                            <span class="toggle-title">🔄 Rotasi Otomatis Saat Max</span>
                            <span class="toggle-desc">Beralih ke bidang lain jika bidang saat ini sudah mencapai level maksimum</span>
                        </div>
                        <label class="switch">
                            <input type="checkbox" id="studyRotateToggle" aria-label="Rotasi bidang belajar" onchange="toggleAuto('auto_subject', this.checked)">
                            <span class="slider"></span>
                        </label>
                    </div>
                    <div style="margin-top: 14px;">
                        <label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 6px;">Pilih Bidang Belajar:</label>
                        <select id="studySubjectSelect" aria-label="Bidang belajar" class="account-select" style="width: 100%;" onchange="setStudySubject(this.value)">
                            <option value="auto">🔄 Auto (Pilih Otomatis yang Belum Maks)</option>
                            <option value="dagang">🛒 Dagang</option>
                            <option value="teknik">🔧 Teknik</option>
                            <option value="administrasi">📋 Administrasi</option>
                            <option value="kesehatan">🏥 Kesehatan</option>
                            <option value="mengajar">👨‍🏫 Mengajar</option>
                            <option value="rawat">🏡 Rawat Desa</option>
                            <option value="konveksi">👕 Konveksi</option>
                            <option value="keamanan">🛡️ Keamanan</option>
                            <option value="boga">🍳 Tata Boga</option>
                            <option value="penerbangan">✈️ Penerbangan</option>
                        </select>
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="card-header"><h2 class="card-title">Kebutuhan karakter</h2></div>
                <div class="toggle-item">
                    <div class="toggle-info">
                        <span class="toggle-title">Auto Makan</span>
                        <span class="toggle-desc">Membeli makanan paling bernilai saat lapar</span>
                    </div>
                    <label class="switch"><input type="checkbox" id="autoMakan" aria-label="Auto Makan" onchange="toggleAuto('makan', this.checked)"><span class="slider"></span></label>
                </div>
                <div class="toggle-item">
                    <div class="toggle-info">
                        <span class="toggle-title">Auto Kesehatan (BPJS)</span>
                        <span class="toggle-desc">Periksa kesehatan & aktivasi BPJS jika kesehatan turun</span>
                    </div>
                    <label class="switch"><input type="checkbox" id="autoKesehatan" aria-label="Auto Kesehatan" onchange="toggleAuto('kesehatan', this.checked)"><span class="slider"></span></label>
                </div>
                <div class="toggle-item">
                    <div class="toggle-info">
                        <span class="toggle-title">Auto Fisik (Gym)</span>
                        <span class="toggle-desc">Latihan fisik di gym saat stamina mencukupi</span>
                    </div>
                    <label class="switch"><input type="checkbox" id="autoFisik" aria-label="Auto Fisik" onchange="toggleAuto('fisik', this.checked)"><span class="slider"></span></label>
                </div>
                <div class="toggle-item">
                    <div class="toggle-info">
                        <span class="toggle-title">Auto Rekreasi</span>
                        <span class="toggle-desc">Pulihkan rekreasi saat turun</span>
                    </div>
                    <label class="switch"><input type="checkbox" id="autoRekreasi" aria-label="Auto Rekreasi" onchange="toggleAuto('rekreasi', this.checked)"><span class="slider"></span></label>
                </div>
                <div class="toggle-item">
                    <div class="toggle-info">
                        <span class="toggle-title">Auto Kebersihan (Mandi / Laundry)</span>
                        <span class="toggle-desc">Menjaga kebersihan tubuh dan pakaian</span>
                    </div>
                    <label class="switch"><input type="checkbox" id="autoKebersihan" aria-label="Auto Kebersihan" onchange="toggleAuto('kebersihan', this.checked)"><span class="slider"></span></label>
                </div>
                <div class="toggle-item">
                    <div class="toggle-info">
                        <span class="toggle-title">Auto Buang Air (WC)</span>
                        <span class="toggle-desc">Gunakan kloset saat kebutuhan turun</span>
                    </div>
                    <label class="switch"><input type="checkbox" id="autoWc" aria-label="Auto Buang Air" onchange="toggleAuto('wc', this.checked)"><span class="slider"></span></label>
                </div>
                <div class="toggle-item">
                    <div class="toggle-info">
                        <span class="toggle-title">Auto Penampilan</span>
                        <span class="toggle-desc">Pangkas rambut dan rapikan penampilan</span>
                    </div>
                    <label class="switch"><input type="checkbox" id="autoPenampilan" aria-label="Auto Penampilan" onchange="toggleAuto('penampilan', this.checked)"><span class="slider"></span></label>
                </div>
                <div class="toggle-item">
                    <div class="toggle-info">
                        <span class="toggle-title">Auto Kondisi Rumah</span>
                        <span class="toggle-desc">Perbaiki dan rawat kondisi rumah</span>
                    </div>
                    <label class="switch"><input type="checkbox" id="autoRumah" aria-label="Auto Kondisi Rumah" onchange="toggleAuto('rumah', this.checked)"><span class="slider"></span></label>
                </div>
                <div class="toggle-item">
                    <div class="toggle-info">
                        <span class="toggle-title">Auto Kebun (Garden)</span>
                        <span class="toggle-desc">Siram, pupuk, dan panen tanaman kebun secara otomatis</span>
                    </div>
                    <label class="switch"><input type="checkbox" id="autoGarden" aria-label="Auto Kebun" onchange="toggleAuto('kebun', this.checked)"><span class="slider"></span></label>
                </div>
            </div>
        </div>

        <!-- TAB 3: AKUN SAYA -->
        <div id="tab-accounts" class="tab-panel">
            <div class="page-title"><div><h1>Akun game</h1><p>Hubungkan atau kelola akun armada.</p></div></div>
            <div class="card" style="margin-bottom: 24px;">
                <div class="card-header">
                    <h2 class="card-title">Daftar akun</h2>
                    <button class="btn btn-primary" onclick="openModal('addAccountModal')">+ Tambah Akun</button>
                </div>
                <div style="overflow-x: auto;">
                    <table class="data-table accounts-table">
                        <thead>
                            <tr>
                                <th>Nama Akun</th>
                                <th>Status Cookie</th>
                                <th>Worker</th>
                                <th>Status Arsip</th>
                                <th>Aksi</th>
                            </tr>
                        </thead>
                        <tbody id="accountsTableBody">
                            <tr><td colspan="5" style="text-align: center; color: var(--text-muted);">Memuat daftar akun...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- TAB 4: NOTIFIKASI -->
        <div id="tab-notifications" class="tab-panel">
            <div class="page-title"><div><h1>Notifikasi</h1><p>Pantau pesan dan peringatan aktivitas.</p></div></div>
            <div style="max-width: 900px; margin: 0 auto;">
                {
        '''
                <div class="notif-subnav" style="display: flex; gap: 10px; margin-bottom: 18px; border-bottom: 1px solid var(--border); padding-bottom: 12px;">
                    <button id="btnSubNotifUser" class="btn btn-primary" style="font-size: 13px; padding: 6px 14px;" onclick="switchNotifTab('user')">Akun terpilih</button>
                    <button id="btnSubNotifAdmin" class="btn btn-secondary" style="font-size: 13px; padding: 6px 14px;" onclick="switchNotifTab('admin')">Semua akun</button>
                </div>
                '''
        if user.get("role") == "admin"
        else ""
    }

                <!-- Panel Notifikasi Akun Pribadi -->
                <div id="panelNotifUser" class="card">
                    <div class="card-header">
                        <h2 class="card-title">Notifikasi akun terpilih</h2>
                        <div style="display: flex; gap: 8px;">
                            <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 12px;" onclick="loadNotifications()">Segarkan</button>
                            <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 12px;" onclick="markAllNotificationsRead()">Tandai Semua Dibaca</button>
                        </div>
                    </div>
                    <p style="color: var(--text-muted); font-size: 13px; margin-top: -6px; margin-bottom: 12px;">Riwayat notifikasi dan peringatan untuk akun ojol yang sedang aktif dipilih.</p>
                    <div id="notificationsList" style="display: flex; flex-direction: column; gap: 10px; margin-top: 14px;">
                        <div style="text-align: center; color: var(--text-muted); padding: 24px;">Memuat notifikasi...</div>
                    </div>
                </div>

                {
        '''
                <!-- Panel Notifikasi Khusus Admin (Semua User & Akun) -->
                <div id="panelNotifAdmin" class="card" style="display: none;">
                    <div class="card-header" style="flex-wrap: wrap; gap: 10px;">
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <div class="card-title" style="margin: 0;">🛡️ Feed Notifikasi Global (Semua Akun & User)</div>
                            <span id="adminNotifTotalBadge" style="background: rgba(59, 130, 246, 0.15); color: var(--primary); border: 1px solid rgba(59, 130, 246, 0.3); font-size: 11px; padding: 2px 8px; border-radius: 12px; font-weight: 600;">0 Notifikasi</span>
                        </div>
                        <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                            <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 12px;" onclick="loadAdminNotifications()">🔄 Refresh</button>
                            <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 12px;" onclick="markAllAdminNotificationsRead()">Tandai Semua Dibaca</button>
                        </div>
                    </div>
                    <p style="color: var(--text-muted); font-size: 13px; margin-top: -6px; margin-bottom: 12px;">Pantau seluruh notifikasi, event otomatis, dan error runtime dari seluruh user dan akun game.</p>

                    <!-- Filter Toolbar -->
                    <div style="display: flex; gap: 10px; flex-wrap: wrap; align-items: center; background: rgba(0,0,0,0.2); padding: 12px; border-radius: 8px; border: 1px solid var(--border); margin-bottom: 14px;">
                        <div style="flex: 1; min-width: 180px;">
                            <input type="text" id="searchAdminNotif" class="form-control" placeholder="🔍 Cari teks, event, ID error..." oninput="filterAdminNotifs()" style="font-size: 12px; padding: 6px 10px; width: 100%;">
                        </div>
                        <div style="min-width: 140px;">
                            <select id="filterAdminNotifUser" class="form-control" onchange="filterAdminNotifs()" style="font-size: 12px; padding: 6px 10px; width: 100%;">
                                <option value="">Semua User</option>
                            </select>
                        </div>
                        <div style="min-width: 140px;">
                            <select id="filterAdminNotifAccount" class="form-control" onchange="filterAdminNotifs()" style="font-size: 12px; padding: 6px 10px; width: 100%;">
                                <option value="">Semua Akun</option>
                            </select>
                        </div>
                        <div>
                            <label style="display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-muted); cursor: pointer; user-select: none;">
                                <input type="checkbox" id="filterAdminNotifErrorOnly" onchange="filterAdminNotifs()">
                                🚨 Hanya Error
                            </label>
                        </div>
                    </div>

                    <div id="adminNotificationsList" style="display: flex; flex-direction: column; gap: 10px;">
                        <div style="text-align: center; color: var(--text-muted); padding: 24px;">Memuat notifikasi semua akun dan user...</div>
                    </div>
                </div>
                '''
        if user.get("role") == "admin"
        else ""
    }
            </div>
        </div>

        <!-- TAB 5: ADMIN PANEL -->
        <div id="tab-admin" class="tab-panel">
            <div class="page-title"><div><h1>Administrasi</h1><p>Kelola pengguna dan pengaturan server.</p></div></div>
            <div class="card" style="margin-bottom: 24px;">
                <div class="card-header">
                    <h2 class="card-title">Pengajuan tertunda</h2>
                    <div style="display: flex; gap: 8px;">
                        <button class="btn btn-utility" style="padding: 4px 10px; font-size: 11px;" onclick="showTab('tab-notifications'); switchNotifTab('admin');" title="Lihat notifikasi global semua akun dan user">🔔 Log Notifikasi Global</button>
                        <button class="btn btn-secondary" style="padding: 4px 8px; font-size: 11px;" onclick="loadAdminData()">Refresh</button>
                    </div>
                </div>
                <div style="overflow-x: auto;">
                    <table class="data-table admin-table">
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Username</th>
                                <th>Nama</th>
                                <th>Telegram ID</th>
                                <th>Waktu Daftar</th>
                                <th>Persetujuan</th>
                            </tr>
                        </thead>
                        <tbody id="pendingTableBody">
                            <tr><td colspan="6" style="text-align: center; color: var(--text-muted);">Tidak ada pengajuan tertunda.</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <div class="card">
                <div class="card-header">
                    <h2 class="card-title">Pengguna web</h2>
                </div>
                <div style="overflow-x: auto;">
                    <table class="data-table admin-table">
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Username</th>
                                <th>Nama</th>
                                <th>Telegram ID</th>
                                <th>Role</th>
                                <th>Status</th>
                                <th>Aksi</th>
                            </tr>
                        </thead>
                        <tbody id="usersTableBody">
                            <tr><td colspan="7" style="text-align: center; color: var(--text-muted);">Memuat pengguna...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- CARD 3: PENGATURAN ADMIN & GLOBAL -->
            <div class="card" style="margin-top: 24px;">
                <div class="card-header" style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
                    <div>
                        <h2 class="card-title">Pengaturan server</h2>
                        <div style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">
                            Kelola semua konfigurasi server, batas akun, otomatisasi, dan integrasi tanpa edit .env
                        </div>
                    </div>
                    <button class="btn btn-primary" onclick="saveAdminSettings()" style="font-weight: 600;">💾 Simpan Pengaturan</button>
                </div>

                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr)); gap: 20px; margin-top: 16px;">
                    <!-- Bagian 1: Otomatisasi & Game Play -->
                    <div style="background: var(--raised); border: 1px solid var(--border); border-radius: 10px; padding: 18px;">
                        <h4 style="font-size: 14px; font-weight: 700; color: var(--text); margin-bottom: 14px; display: flex; align-items: center; gap: 8px;">
                            <span>🎮</span> Otomatisasi & Kebutuhan
                        </h4>
                        
                        <div style="margin-bottom: 12px;">
                            <label for="setting_threshold" style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">Ambang Batas Kebutuhan (% Default)</label>
                            <input type="number" id="setting_threshold" min="10" max="100" style="width: 100%; padding: 8px 10px; background: var(--bg); border: 1px solid var(--border); border-radius: 6px; color: var(--text);">
                            <span style="font-size: 11px; color: var(--text-muted);">Bot memulihkan kebutuhan saat nilai turun di bawah persentase ini.</span>
                        </div>

                        <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <div style="font-size: 13px; font-weight: 600;">Smart Thresholds</div>
                                <div style="font-size: 11px; color: var(--text-muted);">Gunakan batas pintar per kebutuhan</div>
                            </div>
                            <label class="switch"><input type="checkbox" id="setting_smart_thresholds" aria-label="Ambang pintar kebutuhan"><span class="slider"></span></label>
                        </div>

                        <div style="margin-bottom: 12px;">
                            <label for="setting_resource_reserve_percent" style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">Cadangan Sumber Daya (%)</label>
                            <input type="number" id="setting_resource_reserve_percent" min="0" max="50" style="width: 100%; padding: 8px 10px; background: var(--bg); border: 1px solid var(--border); border-radius: 6px; color: var(--text);">
                        </div>

                        <div style="margin-bottom: 12px;">
                            <label for="setting_min_balance" style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">Saldo Koin Minimal (Cadangan)</label>
                            <input type="number" step="0.1" id="setting_min_balance" min="0" style="width: 100%; padding: 8px 10px; background: var(--bg); border: 1px solid var(--border); border-radius: 6px; color: var(--text);">
                            <span style="font-size: 11px; color: var(--text-muted);">Koin minimal yang disisihkan sebelum belanja/kuliah.</span>
                        </div>

                        <div style="margin-bottom: 12px;">
                            <label for="setting_idle_poll_seconds" style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">Interval Cek Polling Status (Detik)</label>
                            <input type="number" id="setting_idle_poll_seconds" min="3" max="60" style="width: 100%; padding: 8px 10px; background: var(--bg); border: 1px solid var(--border); border-radius: 6px; color: var(--text);">
                        </div>

                        <div style="margin-bottom: 12px;">
                            <label for="setting_ojol_mode" style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">Mode Ojol Default</label>
                            <select id="setting_ojol_mode" class="account-select" style="width: 100%;">
                                <option value="otomatis">Otomatis (HTTP Background Bot)</option>
                                <option value="kendara">Kendara (Manual / Ekstensi Chrome)</option>
                            </select>
                        </div>
                    </div>

                    <!-- Bagian 2: Batasan Shift & Kuota Akun -->
                    <div style="background: var(--raised); border: 1px solid var(--border); border-radius: 10px; padding: 18px;">
                        <h4 style="font-size: 14px; font-weight: 700; color: var(--text); margin-bottom: 14px; display: flex; align-items: center; gap: 8px;">
                            <span>⏱️</span> Batasan Shift & Kuota Akun
                        </h4>

                        <div style="margin-bottom: 12px;">
                            <label for="setting_max_spend" style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">Maksimal Pengeluaran Koin (Opsional)</label>
                            <input type="number" step="0.1" id="setting_max_spend" placeholder="Kosong = Tanpa batas" style="width: 100%; padding: 8px 10px; background: var(--bg); border: 1px solid var(--border); border-radius: 6px; color: var(--text);">
                        </div>

                        <div style="margin-bottom: 12px;">
                            <label for="setting_max_jobs" style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">Batas Jumlah Order per Shift (Opsional)</label>
                            <input type="number" id="setting_max_jobs" placeholder="Kosong = Tanpa batas" style="width: 100%; padding: 8px 10px; background: var(--bg); border: 1px solid var(--border); border-radius: 6px; color: var(--text);">
                        </div>

                        <div style="margin-bottom: 12px;">
                            <label for="setting_max_minutes" style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">Batas Durasi Shift (Menit, Opsional)</label>
                            <input type="number" id="setting_max_minutes" placeholder="Kosong = Tanpa batas" style="width: 100%; padding: 8px 10px; background: var(--bg); border: 1px solid var(--border); border-radius: 6px; color: var(--text);">
                        </div>

                        <div style="margin-bottom: 12px;">
                            <label for="setting_max_accounts_per_user" style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">Maksimal Akun Game per User</label>
                            <input type="number" id="setting_max_accounts_per_user" min="1" max="100" style="width: 100%; padding: 8px 10px; background: var(--bg); border: 1px solid var(--border); border-radius: 6px; color: var(--text);">
                        </div>

                        <div style="margin-bottom: 12px;">
                            <label for="setting_max_active_workers" style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">Maksimal Worker Aktif Bersamaan</label>
                            <input type="number" id="setting_max_active_workers" min="1" max="100" style="width: 100%; padding: 8px 10px; background: var(--bg); border: 1px solid var(--border); border-radius: 6px; color: var(--text);">
                        </div>

                        <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <div style="font-size: 13px; font-weight: 600;">Auto-Start Worker</div>
                                <div style="font-size: 11px; color: var(--text-muted);">Otomatis mulai akun saat server startup</div>
                            </div>
                            <label class="switch"><input type="checkbox" id="setting_auto_start" aria-label="Jalankan otomatis saat server mulai"><span class="slider"></span></label>
                        </div>
                    </div>

                    <!-- Bagian 3: Domain, Jaringan & Integrasi -->
                    <div style="background: var(--raised); border: 1px solid var(--border); border-radius: 10px; padding: 18px;">
                        <h4 style="font-size: 14px; font-weight: 700; color: var(--text); margin-bottom: 14px; display: flex; align-items: center; gap: 8px;">
                            <span>🌐</span> Domain & Integrasi
                        </h4>

                        <div style="margin-bottom: 12px;">
                            <label for="setting_login_public_url" style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">Domain Publik Dashboard (URL)</label>
                            <input type="text" id="setting_login_public_url" placeholder="https://ojol.jnck.pl" style="width: 100%; padding: 8px 10px; background: var(--bg); border: 1px solid var(--border); border-radius: 6px; color: var(--text);">
                            <span style="font-size: 11px; color: var(--text-muted);">Alamat URL publik dashboard untuk akses dan redirect.</span>
                        </div>

                        <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <div style="font-size: 13px; font-weight: 600;">Cloudflare Tunnel Bawaan</div>
                                <div style="font-size: 11px; color: var(--text-muted);">Aktifkan jika tanpa reverse proxy Nginx/Caddy</div>
                            </div>
                            <label class="switch"><input type="checkbox" id="setting_tunnel_enabled" aria-label="Aktifkan tunnel"><span class="slider"></span></label>
                        </div>

                        <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <div style="font-size: 13px; font-weight: 600;">Integrasi Telegram Bot</div>
                                <div style="font-size: 11px; color: var(--text-muted);">Aktifkan jika ingin bot Telegram tetap hidup</div>
                            </div>
                            <label class="switch"><input type="checkbox" id="setting_telegram_enabled" aria-label="Aktifkan Telegram"><span class="slider"></span></label>
                        </div>

                        <div style="margin-bottom: 12px;">
                            <label for="setting_telegram_bot_token" style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">Telegram Bot Token</label>
                            <input type="password" id="setting_telegram_bot_token" placeholder="Token dari @BotFather" style="width: 100%; padding: 8px 10px; background: var(--bg); border: 1px solid var(--border); border-radius: 6px; color: var(--text);">
                        </div>

                        <div style="margin-bottom: 12px;">
                            <label for="setting_telegram_chat_id" style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px;">Admin Telegram Chat ID</label>
                            <input type="number" id="setting_telegram_chat_id" placeholder="Contoh: 811190245" style="width: 100%; padding: 8px 10px; background: var(--bg); border: 1px solid var(--border); border-radius: 6px; color: var(--text);">
                        </div>
                    </div>
                </div>

                <div style="margin-top: 20px; display: flex; justify-content: flex-end; border-top: 1px solid var(--border); padding-top: 16px;">
                    <button class="btn btn-primary" onclick="saveAdminSettings()" style="padding: 10px 24px; font-size: 14px; font-weight: 700;">💾 Simpan & Terapkan Pengaturan</button>
                </div>
            </div>
        </div>

        <!-- TAB 5: BANK ANGKA -->
        <div id="tab-bank-angka" class="tab-panel">
            <div class="page-title">
                <div>
                    <h1>Bank Angka Cek</h1>
                    <p>Kelola dan latih bentuk angka (glyph) verifikasi order Ojol agar captcha selalu berhasil dipecahkan.</p>
                </div>
                <div class="page-title-actions">
                    <button class="btn btn-utility" type="button" onclick="loadBankAngka()">Segarkan Bank</button>
                    <button class="btn btn-secondary" type="button" onclick="openManualGlyphModal()">+ Tambah Manual</button>
                </div>
            </div>

            <!-- Antrean Review Glyph Gagal -->
            <div class="card" style="margin-bottom: 24px;">
                <div class="card-header" style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <h2 class="card-title">🔍 Antrean Review Angka (Cek Gagal)</h2>
                        <span id="bankPendingCountBadge" class="nav-count" style="display: none; background: var(--danger, #ef4444); color: white;">0</span>
                    </div>
                    <span style="font-size: 12px; color: var(--text-muted);">Jika bot gagal mengenali angka pada order Ojol, bentuknya akan muncul di sini untuk Anda konfirmasi.</span>
                </div>
                <div id="bankPendingList" style="padding: 16px 0;">
                    <div style="text-align: center; color: var(--text-muted); padding: 32px 0;">
                        Memuat antrean review...
                    </div>
                </div>
            </div>

            <!-- Koleksi Bank Angka 0 - 9 -->
            <div class="card">
                <div class="card-header" style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                    <div>
                        <h2 class="card-title">📚 Koleksi Angka Terdaftar (Digit 0 – 9)</h2>
                        <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">Total <span id="bankTotalTemplatesCount">0</span> varian bentuk tersimpan di server.</div>
                    </div>
                </div>
                <div id="bankTemplatesGrid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; margin-top: 16px;">
                    <div style="text-align: center; color: var(--text-muted); padding: 32px 0; grid-column: 1 / -1;">
                        Memuat data bank angka...
                    </div>
                </div>
            </div>
        </div>
    </main>

    <!-- MODAL: Import Cookie -->
    <dialog id="cookieModal" class="modal" aria-labelledby="cookieModalTitle">
        <div class="modal-content">
            <div class="modal-header">
                <h3 id="cookieModalTitle">Hubungkan cookie game</h3>
                <button class="close-btn" type="button" aria-label="Tutup dialog" onclick="closeModal('cookieModal')">&times;</button>
            </div>
            <div id="cookieTargetAccountLabel" style="display: none; padding: 7px 12px; background: rgba(56, 189, 248, 0.12); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 6px; font-size: 12px; font-weight: 600; color: var(--primary); margin-bottom: 12px;"></div>
            <input type="hidden" id="cookieTargetAccountId" value="">
            <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 12px; line-height: 1.5;">
                Tempel cookie sesi KampungSebelah (format string cookie atau JSON sesi) di bawah ini:
            </p>
            <textarea id="cookieInput" class="cookie-box" placeholder="Tempel nilai token atau JSON cookie" aria-label="Cookie sesi game" aria-describedby="cookieError" spellcheck="false" autocomplete="off" autofocus></textarea>
            <p id="cookieError" class="form-error" role="alert" hidden></p>
            <div style="display: flex; justify-content: flex-end; align-items: center; gap: 10px; margin-top: 14px;">
                <span id="cookieLoadingText" style="display: none; font-size: 13px; color: var(--warning); margin-right: auto;">⏳ Memverifikasi cookie...</span>
                <button class="btn btn-secondary" onclick="closeModal('cookieModal')">Batal</button>
                <button id="btnSubmitCookie" class="btn btn-primary" onclick="submitCookie()">Impor Sekarang</button>
            </div>
        </div>
    </dialog>

    <!-- MODAL: Tambah Akun -->
    <dialog id="addAccountModal" class="modal" aria-labelledby="addAccountTitle">
        <div class="modal-content">
            <div class="modal-header">
                <h3 id="addAccountTitle">➕ Tambah Akun Game Baru</h3>
                <button class="close-btn" type="button" aria-label="Tutup dialog" onclick="closeModal('addAccountModal')">&times;</button>
            </div>
            <div style="margin-bottom: 16px;">
                <label style="font-size: 13px; color: var(--text-muted); display: block; margin-bottom: 6px;">Nama Akun (Opsional)</label>
                <input type="text" id="newAccountName" aria-label="Nama akun" maxlength="40" autofocus placeholder="Contoh: Akun 2 (otomatis mengikuti game)" style="width: 100%; padding: 10px; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; color: var(--text); outline: none;">
            </div>
            <div style="display: flex; justify-content: flex-end; gap: 10px;">
                <button class="btn btn-secondary" onclick="closeModal('addAccountModal')">Batal</button>
                <button class="btn btn-primary" onclick="submitCreateAccount()">Buat Akun</button>
            </div>
        </div>
    </dialog>

    <!-- MODAL: Panduan Ekstensi Chrome & Mode Kendarai -->
    <dialog id="extensionModal" class="modal" aria-labelledby="extensionTitle">
        <div class="modal-content" style="max-width: 640px;">
            <div class="modal-header">
                <h3 id="extensionTitle">Pasang ekstensi Chrome</h3>
                <button class="close-btn" type="button" aria-label="Tutup dialog" onclick="closeModal('extensionModal')">&times;</button>
            </div>
            <ol class="install-steps">
                <li>Unduh ZIP dan ekstrak ke folder komputer.</li>
                <li>Buka <code>chrome://extensions</code> di Chrome lalu aktifkan <strong>Developer mode</strong>.</li>
                <li>Pilih <strong>Load unpacked</strong>, lalu pilih folder <code>kampungsebelah-extension</code> hasil ekstrak.</li>
                <li>Buka KampungSebelah dan pilih tab <strong>Kendarai</strong> di panel ekstensi.</li>
            </ol>
            <div class="actions">
                <a href="/api/extension/download" class="btn btn-primary">Unduh ZIP</a>
                <button class="btn btn-utility" type="button" onclick="closeModal('extensionModal')">Tutup</button>
            </div>
        </div>
    </dialog>

    <!-- MODAL: Tambah Glyph Manual -->
    <dialog id="manualGlyphModal" class="modal" aria-labelledby="manualGlyphModalTitle">
        <div class="modal-content" style="max-width: 520px;">
            <div class="modal-header">
                <h3 id="manualGlyphModalTitle">Tambah Angka ke Bank Manual</h3>
                <button class="close-btn" type="button" aria-label="Tutup dialog" onclick="closeModal('manualGlyphModal')">&times;</button>
            </div>
            <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 14px; line-height: 1.5;">
                Pilih digit angka dan masukkan data koordinat titik stroke / JSON glyph dari log error bot.
            </p>
            <div style="margin-bottom: 14px;">
                <label style="font-size: 12px; font-weight: 600; display: block; margin-bottom: 6px;">Pilih Digit Angka (0 – 9):</label>
                <div id="manualDigitButtons" style="display: flex; gap: 6px; flex-wrap: wrap;"></div>
            </div>
            <div style="margin-bottom: 14px;">
                <label for="manualGlyphJson" style="font-size: 12px; font-weight: 600; display: block; margin-bottom: 6px;">Data Glyph JSON / Titik:</label>
                <textarea id="manualGlyphJson" class="cookie-box" rows="5" placeholder='Contoh: [[[0.86, 1.0], [0.86, 0.0], ...]]]' spellcheck="false" autocomplete="off" oninput="onManualGlyphInput()"></textarea>
            </div>
            <div id="manualGlyphPreview" style="margin-bottom: 14px; display: none;">
                <label style="font-size: 12px; font-weight: 600; display: block; margin-bottom: 6px;">Pratinjau Bentuk:</label>
                <div id="manualGlyphSvgWrap" style="display: flex; justify-content: center; background: var(--bg); padding: 12px; border-radius: 8px;"></div>
            </div>
            <div class="actions" style="display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px;">
                <button class="btn btn-secondary" type="button" onclick="closeModal('manualGlyphModal')">Batal</button>
                <button class="btn btn-primary" type="button" onclick="submitManualGlyph()">Simpan ke Bank Angka</button>
            </div>
        </div>
    </dialog>

    <script>
        const currentUser = {user_json};
        let dashboardData = null;

        function showTab(tabId) {{
            document.querySelectorAll('.nav-btn').forEach(b => b.removeAttribute('aria-current'));
            document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
            const targetBtn = Array.from(document.querySelectorAll('.nav-btn')).find(b => b.getAttribute('onclick') && b.getAttribute('onclick').includes(tabId));
            if (targetBtn) targetBtn.setAttribute('aria-current', 'page');
            const panel = document.getElementById(tabId);
            if (panel) {{
                panel.classList.add('active');
                window.scrollTo(0, 0);
            }}

            if (tabId === 'tab-accounts') loadAccounts();
            if (tabId === 'tab-notifications') {{
                if (currentNotifTab === 'admin' && typeof loadAdminNotifications === 'function') {{
                    loadAdminNotifications();
                }} else {{
                    loadNotifications();
                }}
            }}
            if (tabId === 'tab-admin') loadAdminData();
            if (tabId === 'tab-bank-angka') loadBankAngka();
        }}

        function openModal(id) {{
            const dialog = document.getElementById(id);
            if (!dialog.open) dialog.showModal();
        }}

        function closeModal(id) {{
            document.getElementById(id).close();
        }}

        async function apiFetch(url, options = {{}}) {{
            const res = await fetch(url, options);
            let data = {{}};
            try {{
                data = await res.json();
            }} catch (_) {{
                // Fallback for non-JSON response bodies (e.g. 500 Internal Server Error)
            }}
            if (!res.ok) {{
                const msg = data.detail || data.message || `HTTP ${{res.status}}: ${{res.statusText || 'Gagal memproses permintaan'}}`;
                throw new Error(msg);
            }}
            return data;
        }}

        function escapeHtml(value) {{
            const entities = {{'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}};
            return String(value ?? '').replace(/[&<>"']/g, char => entities[char]);
        }}

        function openCookieModalFor(accId = '', accName = '') {{
            const hiddenId = document.getElementById('cookieTargetAccountId');
            const label = document.getElementById('cookieTargetAccountLabel');
            const name = accName || dashboardData?.account?.name;
            hiddenId.value = accId || dashboardData?.account?.id || '';
            label.style.display = name ? 'block' : 'none';
            label.textContent = name ? 'Akun: ' + name : '';
            document.getElementById('cookieInput').value = '';
            document.getElementById('cookieError').hidden = true;
            openModal('cookieModal');
        }}

        async function loadNotifications() {{
            try {{
                const res = await fetch('/api/notifications');
                const data = await res.json();
                const list = document.getElementById('notificationsList');
                if (!data.notifications || data.notifications.length === 0) {{
                    list.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 24px;">Belum ada notifikasi akun.</div>';
                    updateBadge(0);
                    return;
                }}
                let unreadCount = 0;
                list.innerHTML = data.notifications.map(n => {{
                    if (!n.read) unreadCount++;
                    const bg = n.is_error ? 'rgba(239, 68, 68, 0.12)' : (n.read ? 'transparent' : 'rgba(59, 130, 246, 0.08)');
                    const border = n.is_error ? 'var(--danger)' : (n.read ? 'var(--border)' : 'var(--primary)');
                    const text = escapeHtml(n.text).replace(/\\n/g, '<br>');
                    return `
                    <div style="background: ${{bg}}; border: 1px solid ${{border}}; border-radius: 8px; padding: 14px; position: relative;">
                        <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 6px; display: flex; justify-content: space-between;">
                            <span>${{escapeHtml(n.time)}} ${{n.error_id ? '• ID: ' + escapeHtml(n.error_id) : ''}}</span>
                            ${{!n.read ? '<span style="background: var(--primary); color: white; border-radius: 4px; padding: 1px 6px; font-size: 10px;">BARU</span>' : ''}}
                        </div>
                        <div style="font-size: 13px; line-height: 1.5; color: var(--text);">${{text}}</div>
                    </div>
                    `;
                }}).join('');
                updateBadge(unreadCount);
            }} catch (e) {{
                console.error(e);
            }}
        }}

        async function markAllNotificationsRead() {{
            try {{
                await fetch('/api/notifications/read', {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }}, body: '{{}}' }});
                await loadNotifications();
            }} catch (e) {{
                alert('Gagal menandai notifikasi: ' + e.message);
            }}
        }}

        function updateBadge(count) {{
            const badge = document.getElementById('notifBadge');
            if (badge) {{
                if (count > 0) {{
                    badge.innerText = count;
                    badge.style.display = 'inline-block';
                }} else {{
                    badge.style.display = 'none';
                }}
            }}
        }}

        let currentNotifTab = 'user';
        let allAdminNotifications = [];

        function switchNotifTab(tab) {{
            currentNotifTab = tab;
            const pUser = document.getElementById('panelNotifUser');
            const pAdmin = document.getElementById('panelNotifAdmin');
            const bUser = document.getElementById('btnSubNotifUser');
            const bAdmin = document.getElementById('btnSubNotifAdmin');
            if (tab === 'admin') {{
                if (pUser) pUser.style.display = 'none';
                if (pAdmin) pAdmin.style.display = 'block';
                if (bUser) {{ bUser.classList.remove('btn-primary'); bUser.classList.add('btn-secondary'); }}
                if (bAdmin) {{ bAdmin.classList.remove('btn-secondary'); bAdmin.classList.add('btn-primary'); }}
                loadAdminNotifications();
            }} else {{
                if (pUser) pUser.style.display = 'block';
                if (pAdmin) pAdmin.style.display = 'none';
                if (bUser) {{ bUser.classList.remove('btn-secondary'); bUser.classList.add('btn-primary'); }}
                if (bAdmin) {{ bAdmin.classList.remove('btn-primary'); bAdmin.classList.add('btn-secondary'); }}
                loadNotifications();
            }}
        }}

        async function loadAdminNotifications() {{
            const list = document.getElementById('adminNotificationsList');
            const badge = document.getElementById('adminNotifTotalBadge');
            if (!list) return;
            try {{
                list.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 24px;">Memuat notifikasi semua akun dan user...</div>';
                const data = await apiFetch('/api/admin/notifications');
                allAdminNotifications = data.notifications || [];
                if (badge) badge.innerText = `${{allAdminNotifications.length}} Notifikasi`;
                populateAdminNotifFilters(allAdminNotifications);
                filterAdminNotifs();
            }} catch (e) {{
                list.innerHTML = `<div style="text-align: center; color: var(--danger); padding: 24px;">⚠️ Gagal memuat notifikasi: ${{escapeHtml(e.message)}}</div>`;
            }}
        }}

        function populateAdminNotifFilters(notifs) {{
            const userSelect = document.getElementById('filterAdminNotifUser');
            const accountSelect = document.getElementById('filterAdminNotifAccount');
            if (!userSelect || !accountSelect) return;

            const currentUserVal = userSelect.value;
            const currentAccountVal = accountSelect.value;

            const users = new Map();
            const accounts = new Map();

            notifs.forEach(n => {{
                if (n.user) {{
                    const uKey = n.user.user_id !== undefined && n.user.user_id !== null ? String(n.user.user_id) : (n.user.username || '');
                    const uLabel = n.user.username ? `@${{n.user.username}} (${{n.user.name || 'User'}})` : (n.user.name || `User #${{uKey}}`);
                    if (uKey && !users.has(uKey)) users.set(uKey, uLabel);
                }}
                if (n.account_id) {{
                    const aKey = String(n.account_id);
                    const aLabel = n.account_name ? `${{n.account_name}} (${{aKey.slice(0, 8)}})` : `Akun ${{aKey.slice(0, 8)}}`;
                    if (!accounts.has(aKey)) accounts.set(aKey, aLabel);
                }}
            }});

            userSelect.innerHTML = '<option value="">Semua User (' + users.size + ')</option>' +
                Array.from(users.entries()).map(([k, v]) => `<option value="${{escapeHtml(k)}}">${{escapeHtml(v)}}</option>`).join('');
            accountSelect.innerHTML = '<option value="">Semua Akun (' + accounts.size + ')</option>' +
                Array.from(accounts.entries()).map(([k, v]) => `<option value="${{escapeHtml(k)}}">${{escapeHtml(v)}}</option>`).join('');

            if (currentUserVal && users.has(currentUserVal)) userSelect.value = currentUserVal;
            if (currentAccountVal && accounts.has(currentAccountVal)) accountSelect.value = currentAccountVal;
        }}

        function filterAdminNotifs() {{
            const query = (document.getElementById('searchAdminNotif')?.value || '').toLowerCase().trim();
            const selectedUser = document.getElementById('filterAdminNotifUser')?.value || '';
            const selectedAccount = document.getElementById('filterAdminNotifAccount')?.value || '';
            const errorOnly = document.getElementById('filterAdminNotifErrorOnly')?.checked || false;

            const filtered = allAdminNotifications.filter(n => {{
                if (errorOnly && !n.is_error) return false;
                if (selectedUser) {{
                    const uKey = n.user && n.user.user_id !== undefined && n.user.user_id !== null ? String(n.user.user_id) : (n.user?.username || '');
                    if (uKey !== selectedUser) return false;
                }}
                if (selectedAccount && String(n.account_id) !== selectedAccount) {{
                    return false;
                }}
                if (query) {{
                    const text = (n.text || '').toLowerCase();
                    const event = (n.event || '').toLowerCase();
                    const errId = (n.error_id || '').toLowerCase();
                    const accName = (n.account_name || '').toLowerCase();
                    const uName = (((n.user?.name || '') + ' ' + (n.user?.username || ''))).toLowerCase();
                    if (!text.includes(query) && !event.includes(query) && !errId.includes(query) && !accName.includes(query) && !uName.includes(query)) {{
                        return false;
                    }}
                }}
                return true;
            }});

            renderAdminNotifications(filtered);
        }}

        function renderAdminNotifications(notifs) {{
            const list = document.getElementById('adminNotificationsList');
            if (!list) return;
            if (!notifs || notifs.length === 0) {{
                list.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 32px; border: 1px dashed var(--border); border-radius: 8px;">Tidak ada notifikasi yang sesuai kriteria filter.</div>';
                return;
            }}

            list.innerHTML = notifs.map(n => {{
                const isErr = !!n.is_error;
                const bg = isErr ? 'rgba(239, 68, 68, 0.08)' : (n.read ? 'rgba(255, 255, 255, 0.02)' : 'rgba(59, 130, 246, 0.06)');
                const border = isErr ? 'rgba(239, 68, 68, 0.35)' : (n.read ? 'var(--border)' : 'rgba(59, 130, 246, 0.35)');
                const text = escapeHtml(n.text).replace(/\\n/g, '<br>');
                const uLabel = n.user?.username ? `@${{n.user.username}}` : (n.user?.name || `User #${{n.owner || '?'}}`);
                const accLabel = n.account_name || (n.account_id ? `Akun ${{String(n.account_id).slice(0, 8)}}` : 'Sistem');

                return `
                <div style="background: ${{bg}}; border: 1px solid ${{border}}; border-radius: 8px; padding: 14px; display: flex; flex-direction: column; gap: 8px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; font-size: 11px;">
                        <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                            <span style="background: rgba(168, 85, 247, 0.15); color: var(--accent-ink); border: 1px solid rgba(168, 85, 247, 0.3); border-radius: 4px; padding: 2px 7px; font-weight: 600;">👤 ${{escapeHtml(uLabel)}}</span>
                            <span style="background: rgba(56, 189, 248, 0.15); color: var(--primary); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 4px; padding: 2px 7px; font-weight: 600;">🏷️ ${{escapeHtml(accLabel)}}</span>
                            ${{n.event ? `<span style="background: rgba(255, 255, 255, 0.06); color: var(--text-muted); border-radius: 4px; padding: 2px 6px;">⚡ ${{escapeHtml(n.event)}}</span>` : ''}}
                            ${{n.error_id ? `<span style="background: rgba(239, 68, 68, 0.2); color: var(--danger); border-radius: 4px; padding: 2px 6px; font-weight: 700;">🚨 ${{escapeHtml(n.error_id)}}</span>` : ''}}
                        </div>
                        <div style="color: var(--text-muted); display: flex; align-items: center; gap: 8px;">
                            <span>🕒 ${{escapeHtml(n.time)}}</span>
                            ${{!n.read ? '<span style="background: var(--primary); color: white; border-radius: 4px; padding: 1px 6px; font-size: 10px; font-weight: 600;">BARU</span>' : '<span style="color: var(--text-muted); font-size: 10px;">DIBACA</span>'}}
                        </div>
                    </div>
                    <div style="font-size: 13px; line-height: 1.5; color: var(--text);">${{text}}</div>
                </div>
                `;
            }}).join('');
        }}

        async function markAllAdminNotificationsRead() {{
            try {{
                const data = await apiFetch('/api/admin/notifications/read', {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }}, body: '{{}}' }});
                showToast(`✅ ${{data.marked_count || 0}} notifikasi berhasil ditandai dibaca`, 'success');
                await loadAdminNotifications();
                await loadNotifications();
            }} catch (e) {{
                showToast('⚠️ Gagal menandai notifikasi: ' + e.message, 'error');
            }}
        }}

        // Realtime Countdown 1-second Ticker
        let currentRemainingSeconds = null;
        let currentPhase = null;

        setInterval(() => {{
            if (currentRemainingSeconds !== null && currentRemainingSeconds > 0) {{
                currentRemainingSeconds--;
                const m = Math.floor(currentRemainingSeconds / 60);
                const s = currentRemainingSeconds % 60;
                const formatted = `${{m}}:${{s < 10 ? '0' : ''}}${{s}}`;
                const cdElem = document.getElementById('countdownVal');
                if (cdElem) cdElem.innerText = formatted;

                if (currentPhase === 'delivering') {{
                    const titleElem = document.getElementById('statusTitle');
                    if (titleElem) titleElem.innerText = `Mengantar order (${{formatted}})`;
                }}
            }} else if (currentRemainingSeconds === 0) {{
                const cdElem = document.getElementById('countdownVal');
                if (cdElem) cdElem.innerText = 'Tiba / Selesai';
            }}
        }}, 1000);

        let streamConnected = false;
        let accountOptionsKey = '';
        let accountListKey = '';
        let pendingSelection = false;
        const pendingControls = new Set();

        function applyDashboard(data) {{
            if (pendingSelection) return;
            dashboardData = data;
            renderDashboard(data);
            const freshness = document.getElementById('dashboardFreshness');
            const label = 'Status diperbarui ' +
                new Date().toLocaleTimeString('id-ID', {{ hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Jakarta' }}) + ' WIB';
            if (freshness.textContent !== label) freshness.textContent = label;
        }}

        function startLiveStream() {{
            if (!window.EventSource) return;
            const source = new EventSource('/api/dashboard/stream');
            source.onmessage = event => {{
                const data = JSON.parse(event.data);
                streamConnected = true;
                applyDashboard(data);
            }};
            source.onerror = () => {{
                streamConnected = false;
                source.close();
                setTimeout(startLiveStream, 5000);
            }};
        }}

        async function refreshDashboard() {{
            try {{
                const res = await fetch('/api/dashboard');
                if (res.status === 401) {{
                    window.location.href = '/login';
                    return false;
                }}
                if (!res.ok) throw new Error('Gagal memuat dashboard');
                applyDashboard(await res.json());
                return true;
            }} catch (e) {{
                document.getElementById('dashboardFreshness').textContent = 'Status gagal dimuat. Coba segarkan.';
                return false;
            }}
        }}

        const formatCoin = value => value == null ? '—'
            : new Intl.NumberFormat('id-ID', {{ maximumFractionDigits: 3 }}).format(Number(value)) + ' koin';

        function renderDashboard(data) {{
            const accounts = data.accounts || [];
            const selected = data.account;
            document.getElementById('onboardingCard').hidden = Boolean(selected);
            document.getElementById('activeDashboardSection').hidden = !selected;

            const selector = document.getElementById('accountDropdown');
            const optionsKey = JSON.stringify(accounts.map(acc => [acc.id, acc.name]));
            if (accountOptionsKey !== optionsKey) {{
                selector.replaceChildren(...(accounts.length
                    ? accounts.map(acc => new Option(acc.name, acc.id))
                    : [new Option('Belum ada akun', '')]));
                selector.disabled = !accounts.length;
                accountOptionsKey = optionsKey;
            }}
            if (selector.value !== (selected?.id ?? '')) selector.value = selected?.id ?? '';

            const totals = data.all_accounts_summary || {{}};
            document.getElementById('fleetTotalWallet').textContent = (totals.total_wallet ?? '0') + ' koin';
            document.getElementById('fleetTotalIncome').textContent = (totals.total_income ?? '0') + ' koin';
            document.getElementById('fleetTotalTrips').textContent = totals.total_trips ?? 0;
            document.getElementById('fleetCountAccounts').textContent = accounts.length + ' akun';
            document.getElementById('fleetCountWorkers').textContent = (totals.active_workers ?? 0) + ' dari ' + accounts.length;
            document.getElementById('activeAccountBannerName').textContent = selected?.name ?? 'Akun terpilih';
            updateBankBadge(data.pending_bank_reviews_count || 0);

            const listKey = JSON.stringify(accounts.map(acc => [acc.id, acc.name, acc.status_text, acc.is_selected, acc.wallet, acc.has_cookie]));
            if (accountListKey !== listKey) {{
                const list = document.getElementById('fleetAccountsGrid');
                const focused = list.contains(document.activeElement) ? document.activeElement.dataset.accountId : null;
                const buttons = accounts.map(acc => {{
                    const button = document.createElement('button');
                    button.type = 'button';
                    button.className = 'fleet-account';
                    button.dataset.accountId = acc.id;
                    button.setAttribute('aria-pressed', String(acc.is_selected));
                    button.innerHTML = `<span><span class="fleet-name">${{escapeHtml(acc.name)}}</span>
                        <small>${{escapeHtml(acc.status_text || 'Status belum tersedia')}}</small></span>
                        <span class="fleet-amount">${{acc.wallet == null ? '—' : escapeHtml(acc.wallet + ' koin')}}
                        <small>${{acc.is_selected ? 'Terpilih' : ''}}</small></span>`;
                    button.addEventListener('click', () => switchAccount(acc.id));
                    return button;
                }});
                list.replaceChildren(...buttons);
                if (focused) buttons.find(button => button.dataset.accountId === focused)?.focus({{ preventScroll: true }});
                accountListKey = listKey;
            }}

            const sum = data.summary || {{}};
            const snap = data.snapshot || {{}};
            document.getElementById('statusTitle').textContent = sum.status_text || 'Status belum tersedia';
            document.getElementById('walletVal').textContent = formatCoin(sum.wallet);
            document.getElementById('tripsVal').textContent = sum.trips ?? '—';
            document.getElementById('presenceVal').textContent = sum.online ? 'Online di game' : 'Offline di game';

            // Realtime Countdown State
            const oldPhase = currentPhase;
            currentPhase = sum.phase || snap.phase || null;
            const rawRem = sum.remaining_seconds != null ? sum.remaining_seconds : (snap.remaining_seconds != null ? snap.remaining_seconds : null);
            const serverSec = (rawRem !== null && !isNaN(rawRem)) ? Math.max(0, parseInt(rawRem)) : null;

            if (serverSec === null) {{
                currentRemainingSeconds = null;
            }} else if (currentRemainingSeconds === null || oldPhase !== currentPhase || Math.abs(currentRemainingSeconds - serverSec) > 3) {{
                currentRemainingSeconds = serverSec;
            }}

            const cdElem = document.getElementById('countdownVal');
            if (cdElem) {{
                if (currentRemainingSeconds !== null && currentRemainingSeconds > 0) {{
                    const m = Math.floor(currentRemainingSeconds / 60);
                    const s = currentRemainingSeconds % 60;
                    cdElem.innerText = `${{m}}:${{s < 10 ? '0' : ''}}${{s}}`;
                }} else if (currentPhase === 'searching') {{
                    cdElem.innerText = 'Mencari order…';
                }} else if (currentPhase === 'sleeping') {{
                    cdElem.innerText = 'Sedang tidur';
                }} else if (currentRemainingSeconds === 0) {{
                    cdElem.innerText = 'Tiba / Selesai';
                }} else if (currentPhase === 'idle' && sum.active) {{
                    cdElem.innerText = 'Siaga';
                }} else {{
                    cdElem.innerText = '—';
                }}
            }}

            if (currentPhase === 'delivering' && currentRemainingSeconds !== null && currentRemainingSeconds > 0) {{
                const m = Math.floor(currentRemainingSeconds / 60);
                const s = currentRemainingSeconds % 60;
                document.getElementById('statusTitle').innerText = `Mengantar order (${{m}}:${{s < 10 ? '0' : ''}}${{s}})`;
            }}

            // Notice Card if Limit is Reached
            const limitCard = document.getElementById('limitNoticeCard');
            if (limitCard) {{
                const isLimit = !!(
                    data.limit_reached ||
                    (sum && sum.shift_done) ||
                    (snap && snap.ojol_shift_done) ||
                    (snap.ojol_hours_left != null && snap.ojol_hours_left <= 0) ||
                    (sum && sum.status_text && (sum.status_text.includes('Batas narik') || sum.status_text.includes('14 jam') || sum.status_text.includes('8 jam')))
                );
                limitCard.hidden = !isLimit;
            }}

            // Meters
            updateMeter('fuel', (sum && sum.fuel !== undefined) ? sum.fuel : (snap ? snap.fuel : null));
            updateMeter('cond', (sum && sum.condition !== undefined) ? sum.condition : (snap ? snap.condition : null));
            updateMeter('data', (sum && sum.data !== undefined) ? sum.data : (snap ? snap.data : null));
            const spbuHint = document.getElementById('spbuWaitHint');
            const waitingForSpbu = snap.ojol_min_fuel != null && (snap.ojol_fuel_blocked || Number(snap.fuel) < snap.ojol_min_fuel);
            spbuHint.hidden = !waitingForSpbu;
            if (waitingForSpbu) {{
                const vehicle = snap.ojol_vehicle === 'mobil' ? 'mobil' : 'motor';
                spbuHint.textContent = 'Bawa ' + vehicle + ' yang dipakai Ojol ke SPBU dan buka pompa.';
            }}

            const needs = (snap && snap.needs) ? snap.needs : (snap || {{}});
            updateMeter('makan', needs.makan !== undefined ? needs.makan : (snap ? snap.makan : null));
            updateMeter('kesehatan', needs.kesehatan !== undefined ? needs.kesehatan : (snap ? snap.kesehatan : null));
            updateMeter('fisik', needs.fisik !== undefined ? needs.fisik : (snap ? snap.fisik : null));
            updateMeter('rekreasi', needs.rekreasi !== undefined ? needs.rekreasi : (snap ? snap.rekreasi : null));
            updateMeter('kebersihan', needs.kebersihan !== undefined ? needs.kebersihan : (snap ? snap.kebersihan : null));
            updateMeter('wc', needs.wc !== undefined ? needs.wc : (snap ? snap.wc : null));
            updateMeter('penampilan', needs.penampilan !== undefined ? needs.penampilan : (snap ? snap.penampilan : null));
            updateMeter('rumah', needs.rumah !== undefined ? needs.rumah : (snap ? snap.rumah : null));

            // Auto toggles
            const flags = data.auto_flags || {{}};
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

            if (data.study_subject && document.getElementById('studySubjectSelect')) {{
                document.getElementById('studySubjectSelect').value = data.study_subject;
            }}

            const cookie = document.getElementById('btnCookieToolbar');
            const reconnect = sum.cookie_valid === false;
            cookie.textContent = !selected?.has_cookie ? 'Hubungkan cookie' : reconnect ? 'Perbarui cookie' : 'Ganti cookie';
            cookie.classList.toggle('btn-primary', !selected?.has_cookie || reconnect);
            cookie.classList.toggle('btn-utility', Boolean(selected?.has_cookie && !reconnect));

            renderAutomationControls(data);
            const count = flags.needs_count ?? 0;
            const total = flags.total_needs ?? 8;
            document.getElementById('needsCardBadge').textContent = selected ? `${{count}} dari ${{total}} otomatis` : '—';

            // Logs
            const logBox = document.getElementById('logConsole');
            const logs = data.logs?.length ? data.logs.join('\\n') : 'Belum ada aktivitas.';
            if (logBox.textContent !== logs) logBox.textContent = logs;
        }}

        function updateMeter(id, val) {{
            const txt = document.getElementById(id + 'Text');
            const bar = document.getElementById(id + 'Bar');
            if (!txt || !bar) return;
            if (val === undefined || val === null) {{
                txt.textContent = '—';
                bar.style.width = '0%';
                return;
            }}
            txt.innerText = val + '%';
            bar.style.width = Math.max(0, Math.min(100, val)) + '%';
            if (val > 50) {{
                bar.className = 'meter-fill fill-green';
            }} else if (val > 25) {{
                bar.className = 'meter-fill fill-orange';
            }} else {{
                bar.className = 'meter-fill fill-red';
            }}
        }}

        function showToast(msg, type = 'info') {{
            let container = document.getElementById('toastContainer');
            if (!container) {{
                container = document.createElement('div');
                container.id = 'toastContainer';
                container.className = 'toast-container';\n                container.setAttribute('role', 'status');
                document.body.appendChild(container);
            }}
            const toast = document.createElement('div');
            toast.className = `toast toast-${{type}}`;
            toast.innerText = msg;
            container.appendChild(toast);

            requestAnimationFrame(() => {{
                toast.classList.add('toast-show');
            }});

            setTimeout(() => {{
                toast.classList.remove('toast-show');
                setTimeout(() => {{
                    if (toast.parentNode) toast.remove();
                }}, 300);
            }}, 3500);
        }}

        function renderAutomationControls(data) {{
            const flags = data.auto_flags || {{}};
            const sum = data.summary || {{}};
            const isSleeping = sum.phase === 'sleeping';
            for (const [feature, enabled, maintenance] of [
                ['Ojol', flags.ojol === true || flags.ojol === 'maintenance', flags.ojol === 'maintenance' || data.snapshot?.ojol_maintenance],
                ['Needs', Boolean(flags.needs_active), false],
            ]) {{
                const pending = pendingControls.has(feature);
                const active = Boolean(sum.active && enabled);
                const state = document.getElementById('toolbar' + feature + 'Badge');
                let label = 'Nonaktif';
                let tone = '';
                if (pending) label = 'Memproses…';
                else if (maintenance) {{ label = 'Dijeda untuk pemeliharaan'; tone = 'paused'; }}
                else if (active && isSleeping) {{ label = 'Dijeda saat karakter tidur'; tone = 'paused'; }}
                else if (active) {{ label = 'Sedang berjalan'; tone = 'active'; }}
                else if (enabled) label = 'Siap dijalankan';
                state.textContent = label;
                state.dataset.tone = tone;
                const canRun = Boolean(data.account && !pending && !active && !maintenance);
                const run = document.getElementById('btnRun' + feature);
                const stop = document.getElementById('btnStop' + feature);
                run.hidden = active || maintenance;
                run.disabled = !canRun;
                stop.hidden = !enabled;
                stop.disabled = !data.account || pending;
            }}
        }}

        async function controlAction(cmd) {{
            const account = dashboardData?.account;
            if (!account || pendingSelection) return;
            const feature = cmd.endsWith('-needs') ? 'Needs' : 'Ojol';
            if (pendingControls.has(feature)) return;
            if (cmd.startsWith('run') && (!account.has_cookie || dashboardData.summary?.cookie_valid === false)) {{
                openCookieModalFor(account.id, account.name);
                return;
            }}
            pendingControls.add(feature);
            renderAutomationControls(dashboardData);
            try {{
                const data = await apiFetch('/api/control/' + cmd + '?account_id=' + encodeURIComponent(account.id), {{ method: 'POST' }});
                showToast(data.message?.split('\\n\\n', 1)[0] || 'Aksi diproses', 'info');
                await refreshDashboard();
            }} catch (e) {{
                showToast('Aksi gagal: ' + e.message, 'error');
            }} finally {{
                pendingControls.delete(feature);
                if (dashboardData) renderAutomationControls(dashboardData);
            }}
        }}

        async function manualRefreshDashboard() {{
            const button = document.getElementById('btnRefreshDash');
            button.disabled = true;
            button.textContent = 'Memuat…';
            try {{
                await refreshDashboard();
            }} finally {{
                button.disabled = false;
                button.textContent = 'Segarkan';
            }}
        }}

        async function toggleAuto(flag, enabled) {{
            try {{
                const accountId = dashboardData?.account?.id;
                if (!accountId) throw new Error('Pilih akun terlebih dahulu.');
                await apiFetch('/api/control/toggle-auto?account_id=' + encodeURIComponent(accountId), {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ flag, enabled }})
                }});
                showToast('Pengaturan auto ' + flag + ': ' + (enabled ? 'Aktif' : 'Nonaktif'), 'info');
                await refreshDashboard();
            }} catch (e) {{
                showToast('⚠️ Gagal: ' + e.message, 'error');
                await refreshDashboard();
            }}
        }}

        async function toggleModeOjol(isKendara) {{
            try {{
                const mode = isKendara ? 'kendara' : 'otomatis';
                await apiFetch('/api/control/mode-ojol', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ mode }})
                }});
                showToast('Mode ojol: ' + (isKendara ? 'Kendara (Manual)' : 'Otomatis'), 'info');
                await refreshDashboard();
            }} catch (e) {{
                showToast('⚠️ Gagal: ' + e.message, 'error');
            }}
        }}

        async function setStudySubject(subject) {{
            try {{
                const accountId = dashboardData?.account?.id;
                if (!accountId) throw new Error('Pilih akun terlebih dahulu.');
                await apiFetch('/api/control/study-subject?account_id=' + encodeURIComponent(accountId), {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ subject }})
                }});
                showToast('Bidang belajar: ' + subject.toUpperCase(), 'info');
                await refreshDashboard();
            }} catch (e) {{
                showToast('⚠️ Gagal: ' + e.message, 'error');
                await refreshDashboard();
            }}
        }}

        async function switchAccount(accountId) {{
            if (!accountId || pendingSelection || dashboardData?.account?.id === accountId) return;
            pendingSelection = true;
            const selector = document.getElementById('accountDropdown');
            selector.disabled = true;
            try {{
                await apiFetch('/api/accounts/select', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ account_id: accountId }})
                }});
            }} catch (e) {{
                showToast('Gagal mengganti akun: ' + e.message, 'error');
            }} finally {{
                pendingSelection = false;
                selector.disabled = false;
                const applied = await refreshDashboard();
                if (!applied && dashboardData?.account) selector.value = dashboardData.account.id;
                if (document.getElementById('tab-accounts').classList.contains('active')) await loadAccounts();
            }}
        }}

        async function submitCreateAccount() {{
            const name = document.getElementById('newAccountName').value.trim();
            try {{
                const data = await apiFetch('/api/accounts/create', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ name: name || undefined }})
                }});
                closeModal('addAccountModal');
                document.getElementById('newAccountName').value = '';
                await refreshDashboard();
                await loadAccounts();
                const createdAcc = data.account;
                if (createdAcc) {{
                    openCookieModalFor(createdAcc.id, createdAcc.name);
                }}
            }} catch (e) {{
                alert('Error: ' + e.message);
            }}
        }}

        async function submitOnboardingCookie() {{
            const name = (document.getElementById('onboardingAccountName')?.value || '').trim();
            const cookie = (document.getElementById('onboardingCookieInput')?.value || '').trim();
            if (!cookie) return alert('Silakan tempel cookie KampungSebelah terlebih dahulu.');

            const btn = document.getElementById('btnOnboardingSubmit');
            const loading = document.getElementById('onboardingLoadingText');
            if (btn) btn.disabled = true;
            if (loading) loading.style.display = 'inline';

            try {{
                const data = await apiFetch('/api/control/import-cookie', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ name, cookie }})
                }});
                showToast(data.message || '✅ Akun berhasil dihubungkan dan cookie terverifikasi!', 'success');
                const inp = document.getElementById('onboardingCookieInput');
                if (inp) inp.value = '';
                await refreshDashboard();
                await loadAccounts();
            }} catch (e) {{
                showToast('⚠️ Gagal menghubungkan akun: ' + e.message, 'error');
            }} finally {{
                if (btn) btn.disabled = false;
                if (loading) loading.style.display = 'none';
            }}
        }}

        async function submitCookie() {{
            const cookie = document.getElementById('cookieInput').value.trim();
            const error = document.getElementById('cookieError');
            error.hidden = true;
            if (!cookie) {{
                error.textContent = 'Tempel cookie sesi terlebih dahulu.';
                error.hidden = false;
                document.getElementById('cookieInput').focus();
                return;
            }}
            const targetAccountId = (document.getElementById('cookieTargetAccountId')?.value || '').trim();
            const btn = document.getElementById('btnSubmitCookie');
            const loading = document.getElementById('cookieLoadingText');
            if (btn) btn.disabled = true;
            if (loading) loading.style.display = 'inline';

            try {{
                const payload = {{ cookie }};
                if (targetAccountId) payload.account_id = targetAccountId;
                const data = await apiFetch('/api/control/import-cookie', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(payload)
                }});
                closeModal('cookieModal');
                document.getElementById('cookieInput').value = '';
                if (document.getElementById('cookieTargetAccountId')) {{
                    document.getElementById('cookieTargetAccountId').value = '';
                }}
                showToast(data.message || '✅ Cookie berhasil diimpor dan terverifikasi!', 'success');
                await refreshDashboard();
                await loadAccounts();
            }} catch (e) {{
                error.textContent = 'Gagal mengimpor cookie: ' + e.message;
                error.hidden = false;
            }} finally {{
                if (btn) btn.disabled = false;
                if (loading) loading.style.display = 'none';
            }}
        }}

        async function loadAccounts() {{
            try {{
                const data = await apiFetch('/api/accounts');
                const tbody = document.getElementById('accountsTableBody');
                tbody.innerHTML = '';
                if (!data.accounts || !data.accounts.length) {{
                    tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">Belum ada akun. Klik + Tambah Akun di atas.</td></tr>';
                    return;
                }}
                data.accounts.forEach(acc => {{
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td><strong>${{escapeHtml(acc.name)}}</strong> ${{acc.is_selected ? '<span style="color: var(--primary); font-size: 11px;">(Aktif)</span>' : ''}}</td>
                        <td data-label="Cookie">${{acc.has_cookie ? '<span style="color: var(--success);">Terhubung</span>' : '<span style="color: var(--warning);">Belum ada</span>'}}</td>
                        <td data-label="Worker">${{acc.is_running ? '<span style="color: var(--success);">Berjalan</span>' : '<span style="color: var(--text-muted);">Berhenti</span>'}}</td>
                        <td data-label="Arsip">${{acc.archived ? '<span style="color: var(--warning);">Diarsipkan</span>' : 'Aktif'}}</td>
                        <td style="display: flex; gap: 4px; flex-wrap: wrap;">
                            ${{!acc.archived && !acc.is_selected ? `<button class="btn btn-secondary" style="padding: 4px 8px; font-size: 11px;" onclick="switchAccount('${{acc.id}}')">Pilih</button>` : ''}}
                            ${{acc.archived ? '' : `
                                <button data-action="cookie" class="btn ${{acc.has_cookie ? 'btn-secondary' : 'btn-primary'}}" style="padding: 4px 8px; font-size: 11px;">${{acc.has_cookie ? 'Ganti cookie' : 'Hubungkan cookie'}}</button>
                                <button data-action="rename" class="btn btn-secondary" style="padding: 4px 8px; font-size: 11px;">Ubah Nama</button>`}}
                            <button class="btn btn-secondary" style="padding: 4px 8px; font-size: 11px;" onclick="toggleArchive('${{acc.id}}', ${{!acc.archived}})">${{acc.archived ? 'Pulihkan' : 'Arsipkan'}}</button>
                        </td>
                    `;
                    if (!acc.archived) {{
                        tr.querySelector('[data-action="cookie"]').onclick = () => openCookieModalFor(acc.id, acc.name);
                        tr.querySelector('[data-action="rename"]').onclick = () => promptRename(acc.id, acc.name);
                    }}
                    tbody.appendChild(tr);
                }});
            }} catch (e) {{
                console.error(e);
            }}
        }}

        async function promptRename(accId, curName) {{
            const n = prompt('Masukkan nama baru untuk akun ini:', curName);
            if (!n || n === curName) return;
            try {{
                const res = await fetch('/api/accounts/rename', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ account_id: accId, name: n }})
                }});
                if (!res.ok) throw new Error('Gagal mengubah nama');
                loadAccounts();
                refreshDashboard();
            }} catch (e) {{
                alert(e.message);
            }}
        }}

        async function toggleArchive(accId, archived) {{
            try {{
                const res = await fetch('/api/accounts/archive', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ account_id: accId, archived }})
                }});
                if (!res.ok) throw new Error('Gagal update status arsip');
                loadAccounts();
                refreshDashboard();
            }} catch (e) {{
                alert(e.message);
            }}
        }}

        async function loadAdminData() {{
            try {{
                const [pRes, uRes, sRes] = await Promise.all([
                    fetch('/api/admin/pending'),
                    fetch('/api/admin/users'),
                    fetch('/api/admin/settings')
                ]);
                const pending = await pRes.json();
                const users = await uRes.json();
                const settings = await sRes.json();

                renderAdminSettings(settings);

                const pTbody = document.getElementById('pendingTableBody');
                pTbody.innerHTML = '';
                if (!pending.length) {{
                    pTbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">Tidak ada pengajuan tertunda.</td></tr>';
                }} else {{
                    pending.forEach(p => {{
                        const tr = document.createElement('tr');
                        const dt = new Date(p.created_at * 1000).toLocaleString('id-ID');
                        tr.innerHTML = `
                            <td data-label="ID">#${{p.id}}</td>
                            <td class="admin-user-name"><strong>${{escapeHtml(p.username)}}</strong></td>
                            <td data-label="Nama">${{escapeHtml(p.name || '—')}}</td>
                            <td data-label="Telegram">${{p.telegram_id || '—'}}</td>
                            <td data-label="Daftar">${{dt}}</td>
                            <td>
                                <button class="btn btn-success" style="padding: 4px 8px; font-size: 11px;" onclick="reviewUser(${{p.id}}, true)">✅ Setujui</button>
                                <button class="btn btn-danger" style="padding: 4px 8px; font-size: 11px;" onclick="reviewUser(${{p.id}}, false)">❌ Tolak</button>
                            </td>
                        `;
                        pTbody.appendChild(tr);
                    }});
                }}

                const uTbody = document.getElementById('usersTableBody');
                uTbody.innerHTML = '';
                users.forEach(u => {{
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td data-label="ID">#${{u.id}}</td>
                        <td class="admin-user-name"><strong>${{escapeHtml(u.username)}}</strong></td>
                        <td data-label="Nama">${{escapeHtml(u.name || '—')}}</td>
                        <td data-label="Telegram">${{u.telegram_id || '—'}}</td>
                        <td data-label="Peran"><span style="padding: 2px 6px; border-radius: 4px; background: ${{u.role === 'admin' ? 'rgba(59, 130, 246, 0.2)' : 'rgba(255, 255, 255, 0.05)'}}; color: ${{u.role === 'admin' ? 'var(--primary)' : 'inherit'}};">${{u.role}}</span></td>
                        <td data-label="Status"><span style="color: ${{u.status === 'approved' ? 'var(--success)' : u.status === 'pending' ? 'var(--warning)' : 'var(--danger)'}};">${{u.status}}</span></td>
                        <td>
                            ${{u.status === 'approved' ? `<button class="btn btn-danger" style="padding: 3px 6px; font-size: 10px;" onclick="reviewUser(${{u.id}}, false)">Nonaktifkan</button>` : `<button class="btn btn-success" style="padding: 3px 6px; font-size: 10px;" onclick="reviewUser(${{u.id}}, true)">Aktifkan</button>`}}
                        </td>
                    `;
                    uTbody.appendChild(tr);
                }});
            }} catch (e) {{
                console.error('Admin load error:', e);
            }}
        }}

        function renderAdminSettings(s) {{
            if (!s) return;
            const setVal = (id, val) => {{
                const el = document.getElementById(id);
                if (el) el.value = (val !== null && val !== undefined) ? val : '';
            }};
            const setChk = (id, val) => {{
                const el = document.getElementById(id);
                if (el) el.checked = !!val;
            }};

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
            setChk('setting_telegram_enabled', s.telegram_enabled);
            setVal('setting_telegram_bot_token', s.telegram_bot_token);
            setVal('setting_telegram_chat_id', s.telegram_chat_id);
        }}

        async function saveAdminSettings() {{
            const getVal = (id) => {{
                const el = document.getElementById(id);
                const v = el ? el.value.trim() : '';
                return v !== '' ? v : null;
            }};
            const getChk = (id) => {{
                const el = document.getElementById(id);
                return el ? el.checked : false;
            }};

            const payload = {{
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
                telegram_enabled: getChk('setting_telegram_enabled'),
                telegram_bot_token: getVal('setting_telegram_bot_token') || '',
                telegram_chat_id: getVal('setting_telegram_chat_id')
            }};

            try {{
                const res = await fetch('/api/admin/settings', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(payload)
                }});
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || data.message || 'Gagal menyimpan pengaturan');
                renderAdminSettings(data.settings);
                alert('✅ Pengaturan admin berhasil disimpan dan diterapkan!');
                refreshDashboard();
            }} catch (e) {{
                alert('Gagal menyimpan: ' + e.message);
            }}
        }}

        async function reviewUser(userId, approve) {{
            try {{
                const res = await fetch('/api/admin/review', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ user_id: userId, approve }})
                }});
                if (!res.ok) throw new Error('Gagal memproses review');
                loadAdminData();
            }} catch (e) {{
                alert(e.message);
            }}
        }}

        async function logout() {{
            try {{
                await fetch('/api/auth/logout', {{ method: 'POST' }});
            }} catch (e) {{}}
            window.location.href = '/login';
        }}

        // ==========================================
        // BANK ANGKA (CAPTCHA SOLVER REVIEW & TRAIN)
        // ==========================================
        const selectedReviewDigits = {{}};
        let manualSelectedDigit = '0';

        function updateBankBadge(count) {{
            const badge = document.getElementById('bankReviewBadge');
            const pendingBadge = document.getElementById('bankPendingCountBadge');
            const banner = document.getElementById('bankReviewBanner');
            const headerCount = document.getElementById('bankPendingHeaderCount');
            if (badge) {{
                if (count > 0) {{
                    badge.innerText = count;
                    badge.style.display = 'inline-block';
                }} else {{
                    badge.style.display = 'none';
                }}
            }}
            if (pendingBadge) {{
                if (count > 0) {{
                    pendingBadge.innerText = count;
                    pendingBadge.style.display = 'inline-block';
                }} else {{
                    pendingBadge.style.display = 'none';
                }}
            }}
            if (banner) {{
                if (count > 0) {{
                    banner.style.display = 'flex';
                    if (headerCount) headerCount.innerText = count;
                }} else {{
                    banner.style.display = 'none';
                }}
            }}
        }}

        function renderGlyphSvg(glyph, width = 100, height = 100, strokeColor = '#10b981') {{
            if (!glyph || !Array.isArray(glyph) || glyph.length === 0) {{
                return `<div style="width:${{width}}px;height:${{height}}px;background:#0f172a;border-radius:6px;display:flex;align-items:center;justify-content:center;color:#64748b;font-size:11px;">(kosong)</div>`;
            }}
            const pad = 12;
            const drawW = width - pad * 2;
            const drawH = height - pad * 2;
            const allPts = [];
            for (const stroke of glyph) {{
                if (Array.isArray(stroke)) {{
                    for (const pt of stroke) {{
                        if (Array.isArray(pt) && pt.length >= 2) {{
                            const x = parseFloat(pt[0]);
                            const y = parseFloat(pt[1]);
                            if (!isNaN(x) && !isNaN(y)) allPts.push([x, y]);
                        }}
                    }}
                }}
            }}
            if (allPts.length === 0) return '';
            const minX = Math.min(...allPts.map(p => p[0]));
            const maxX = Math.max(...allPts.map(p => p[0]));
            const minY = Math.min(...allPts.map(p => p[1]));
            const maxY = Math.max(...allPts.map(p => p[1]));
            const spanX = maxX - minX || 1.0;
            const spanY = maxY - minY || 1.0;

            let polylines = '';
            for (const stroke of glyph) {{
                if (!Array.isArray(stroke) || stroke.length === 0) continue;
                const ptsStr = stroke.map(pt => {{
                    const nx = (parseFloat(pt[0]) - minX) / spanX;
                    const ny = (parseFloat(pt[1]) - minY) / spanY;
                    const px = (nx * drawW + pad).toFixed(1);
                    const py = (ny * drawH + pad).toFixed(1);
                    return `${{px}},${{py}}`;
                }}).join(' ');
                polylines += `<polyline points="${{ptsStr}}" fill="none" stroke="${{strokeColor}}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>`;
            }}
            return `<svg width="${{width}}" height="${{height}}" viewBox="0 0 ${{width}} ${{height}}" style="background:#0f172a;border-radius:8px;display:block;box-shadow:inset 0 0 8px rgba(0,0,0,0.5);">${{polylines}}</svg>`;
        }}

        async function loadBankAngka() {{
            const listEl = document.getElementById('bankPendingList');
            const gridEl = document.getElementById('bankTemplatesGrid');
            try {{
                const res = await apiFetch('/api/bank-angka');
                const templates = res.templates || {{}};
                const pending = res.pending || [];
                const totalTemplates = res.total_templates || 0;

                updateBankBadge(pending.length);
                const countEl = document.getElementById('bankTotalTemplatesCount');
                if (countEl) countEl.innerText = totalTemplates;

                // 1. Render Pending Reviews
                if (pending.length === 0) {{
                    listEl.innerHTML = `
                        <div style="text-align: center; color: var(--success); padding: 36px 16px; background: rgba(16, 185, 129, 0.08); border-radius: 8px; border: 1px dashed rgba(16, 185, 129, 0.3);">
                            <div style="font-size: 28px; margin-bottom: 6px;">✅</div>
                            <div style="font-weight: 700; font-size: 15px;">Semua angka cek saat ini dikenali!</div>
                            <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">Tidak ada antrean review gagal cek polyline.</div>
                        </div>
                    `;
                }} else {{
                    listEl.innerHTML = pending.map((item, idx) => {{
                        const glyphJsonStr = escapeHtml(JSON.stringify(item.glyph));
                        const errIdStr = item.error_id ? `<span style="background: rgba(239, 68, 68, 0.18); color: var(--danger); border-radius: 4px; padding: 2px 8px; font-weight: 700; font-size: 12px;">🚨 ${{escapeHtml(item.error_id)}}</span>` : '';
                        const timeStr = item.time ? new Date(item.time).toLocaleTimeString('id-ID', {{ hour: '2-digit', minute: '2-digit', second: '2-digit' }}) : 'Baru saja';
                        const rid = escapeHtml(item.id);

                        let capturedSvgBlock = '';
                        if (item.svg_text && item.svg_text.trim().startsWith('<svg')) {{
                            let cleanSvg = item.svg_text.replace(/<svg\b([^>]*)>/i, '<svg $1 style="width: 180px; height: 84px; display: block; border-radius: 6px;">');
                            capturedSvgBlock = `
                                <div style="background: #0f172a; border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; display: flex; flex-direction: column; align-items: center; justify-content: center;">
                                    <div style="font-size: 11px; font-weight: 700; color: #38bdf8; margin-bottom: 6px; display: flex; align-items: center; gap: 4px;">
                                        <span>📸</span> GAMBAR CAPTURE GAME (2 ANGKA)
                                    </div>
                                    <div style="display: flex; align-items: center; justify-content: center; background: #f4efe2; border-radius: 6px; box-shadow: 0 2px 8px rgba(0,0,0,0.4); overflow: hidden;">
                                        ${{cleanSvg}}
                                    </div>
                                    <div style="font-size: 10px; color: var(--text-muted); margin-top: 5px;">Tangkapan layar asli dari game</div>
                                </div>
                            `;
                        }}

                        const focusGlyphBlock = `
                            <div style="background: #0f172a; border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; display: flex; flex-direction: column; align-items: center; justify-content: center;">
                                <div style="font-size: 11px; font-weight: 700; color: #f59e0b; margin-bottom: 6px; display: flex; align-items: center; gap: 4px;">
                                    <span>🎯</span> FOKUS GLYPH YANG DILATIH
                                </div>
                                <div style="display: flex; align-items: center; justify-content: center;">
                                    ${{renderGlyphSvg(item.glyph, 100, 84, '#f59e0b')}}
                                </div>
                                <div style="font-size: 10px; color: var(--text-muted); margin-top: 5px;">Pilih angka bentuk ini di bawah</div>
                            </div>
                        `;

                        return `
                            <div style="background: var(--raised); border: 1px solid var(--border); border-radius: 10px; padding: 16px; margin-bottom: 16px;">
                                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; border-bottom: 1px solid var(--border); padding-bottom: 8px;">
                                    <div style="display: flex; align-items: center; gap: 8px;">
                                        ${{errIdStr}}
                                        <span style="font-size: 12px; color: var(--text-muted);">Waktu kejadian: ${{timeStr}}</span>
                                        ${{item.trip_id ? `<span style="font-size: 11px; color: var(--text-muted); background: var(--bg); padding: 2px 6px; border-radius: 4px;">Trip: ${{escapeHtml(item.trip_id)}}</span>` : ''}}
                                    </div>
                                    <span style="font-size: 12px; color: #f59e0b; font-weight: 600;">⚠️ Bot butuh konfirmasi digit</span>
                                </div>

                                <div style="display: flex; gap: 16px; flex-wrap: wrap; align-items: center; margin-bottom: 16px;">
                                    ${{capturedSvgBlock}}
                                    ${{focusGlyphBlock}}
                                </div>

                                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; background: var(--bg); padding: 12px 14px; border-radius: 8px; border: 1px solid var(--border);">
                                    <div>
                                        <div style="font-size: 13px; font-weight: 700; color: var(--text); margin-bottom: 8px;">
                                            Tentukan angka untuk bentuk yang ditandai:
                                        </div>
                                        <div style="display: flex; gap: 6px; flex-wrap: wrap;" id="reviewDigitsWrap_${{rid}}">
                                            ${{[0,1,2,3,4,5,6,7,8,9].map(d => `
                                                <button type="button" class="btn btn-utility" style="padding: 6px 12px; font-weight: 700; font-size: 14px; min-width: 36px;" onclick="selectReviewDigit('${{rid}}', '${{d}}', this)">
                                                    ${{d}}
                                                </button>
                                            `).join('')}}
                                        </div>
                                    </div>
                                    <div style="display: flex; gap: 8px; align-items: center;">
                                        <button class="btn btn-secondary" type="button" onclick="dismissReview('${{rid}}', '${{escapeHtml(item.error_id || '')}}')" style="padding: 8px 14px; font-size: 12px;">Abaikan</button>
                                        <button class="btn btn-primary" type="button" onclick="saveReviewToBank('${{rid}}', '${{escapeHtml(item.error_id || '')}}', '${{glyphJsonStr}}')" style="padding: 8px 18px; font-size: 13px; font-weight: 700;">💾 Simpan ke Bank Angka</button>
                                    </div>
                                </div>
                            </div>
                        `;
                    }}).join('');
                }}

                // 2. Render Bank Templates (0 - 9)
                const digits = ['0','1','2','3','4','5','6','7','8','9'];
                gridEl.innerHTML = digits.map(d => {{
                    const variants = templates[d] || [];
                    const varCount = variants.length;
                    const previews = variants.map((v, vIdx) => `
                        <div style="position: relative; display: inline-block;">
                            ${{renderGlyphSvg(v, 68, 68, '#38bdf8')}}
                            <button type="button" onclick="deleteBankVariant('${{d}}', ${{vIdx}})" title="Hapus varian ini" style="position: absolute; top: -6px; right: -6px; background: rgba(239,68,68,0.9); color: white; border: none; border-radius: 50%; width: 18px; height: 18px; font-size: 10px; cursor: pointer; display: flex; align-items: center; justify-content: center; line-height: 1;">&times;</button>
                        </div>
                    `).join('');

                    return `
                        <div style="background: var(--raised); border: 1px solid var(--border); border-radius: 10px; padding: 14px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; border-bottom: 1px solid var(--border); padding-bottom: 8px;">
                                <div style="font-size: 16px; font-weight: 700; display: flex; align-items: center; gap: 6px;">
                                    <span style="font-size: 20px; color: var(--primary);">${{d}}</span>
                                    <span>Angka ${{d}}</span>
                                </div>
                                <span style="font-size: 11px; background: rgba(56, 189, 248, 0.15); color: var(--primary); padding: 2px 8px; border-radius: 12px; font-weight: 600;">${{varCount}} varian</span>
                            </div>
                            <div style="display: flex; gap: 8px; flex-wrap: wrap; min-height: 70px; align-items: center;">
                                ${{varCount > 0 ? previews : '<div style="color: var(--text-muted); font-size: 12px; font-style: italic;">Belum ada varian tersimpan</div>'}}
                            </div>
                        </div>
                    `;
                }}).join('');

            }} catch (e) {{
                listEl.innerHTML = `<div style="color: var(--danger); padding: 16px;">Gagal memuat bank angka: ${{escapeHtml(e.message)}}</div>`;
            }}
        }}

        function selectReviewDigit(reviewId, digit, btnEl) {{
            selectedReviewDigits[reviewId] = digit;
            const wrap = document.getElementById(`reviewDigitsWrap_${{reviewId}}`);
            if (wrap) {{
                wrap.querySelectorAll('button').forEach(b => {{
                    b.classList.remove('btn-primary');
                    b.classList.add('btn-utility');
                    b.style.background = '';
                    b.style.color = '';
                }});
            }}
            if (btnEl) {{
                btnEl.classList.remove('btn-utility');
                btnEl.classList.add('btn-primary');
            }}
        }}

        async function saveReviewToBank(reviewId, errorId, glyphJsonStr) {{
            const sel = selectedReviewDigits[reviewId];
            if (sel === undefined || sel === null || sel === '') {{
                alert('Silakan tentukan angka (0 - 9) untuk bentuk ini terlebih dahulu!');
                return;
            }}
            try {{
                const glyph = JSON.parse(glyphJsonStr);
                const res = await apiFetch('/api/bank-angka/save', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        digit: String(sel),
                        glyph: glyph,
                        review_id: reviewId,
                        error_id: errorId || null
                    }})
                }});
                if (res && res.ok) {{
                    alert(`✅ Bentuk berhasil disimpan ke Bank Angka sebagai digit ${{sel}}!`);
                    await loadBankAngka();
                    manualRefreshDashboard();
                }}
            }} catch (e) {{
                alert('Gagal menyimpan ke bank angka: ' + e.message);
            }}
        }}

        async function dismissReview(reviewId, errorId) {{
            if (!confirm('Abaikan review angka ini?')) return;
            try {{
                await apiFetch('/api/bank-angka/dismiss', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ review_id: reviewId, error_id: errorId || null }})
                }});
                await loadBankAngka();
                manualRefreshDashboard();
            }} catch (e) {{
                alert('Gagal mengabaikan: ' + e.message);
            }}
        }}

        async function deleteBankVariant(digit, index) {{
            if (!confirm(`Hapus varian ke-${{index + 1}} dari angka ${{digit}}?`)) return;
            try {{
                await apiFetch('/api/bank-angka/delete', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ digit: String(digit), index: index }})
                }});
                await loadBankAngka();
            }} catch (e) {{
                alert('Gagal menghapus varian: ' + e.message);
            }}
        }}

        function openManualGlyphModal() {{
            document.getElementById('manualGlyphJson').value = '';
            document.getElementById('manualGlyphPreview').style.display = 'none';
            manualSelectedDigit = '0';
            updateManualDigitButtons();
            openModal('manualGlyphModal');
        }}

        function updateManualDigitButtons() {{
            const wrap = document.getElementById('manualDigitButtons');
            if (!wrap) return;
            wrap.innerHTML = [0,1,2,3,4,5,6,7,8,9].map(d => `
                <button type="button" class="btn ${{String(d) === String(manualSelectedDigit) ? 'btn-primary' : 'btn-utility'}}" style="padding: 4px 10px; font-weight: 700; font-size: 13px;" onclick="selectManualDigit('${{d}}')">
                    ${{d}}
                </button>
            `).join('');
        }}

        function selectManualDigit(digit) {{
            manualSelectedDigit = String(digit);
            updateManualDigitButtons();
        }}

        function onManualGlyphInput() {{
            const val = document.getElementById('manualGlyphJson').value.trim();
            const preview = document.getElementById('manualGlyphPreview');
            const wrap = document.getElementById('manualGlyphSvgWrap');
            if (!val) {{
                preview.style.display = 'none';
                return;
            }}
            try {{
                const parsed = JSON.parse(val);
                if (Array.isArray(parsed)) {{
                    wrap.innerHTML = renderGlyphSvg(parsed, 120, 120, '#10b981');
                    preview.style.display = 'block';
                }}
            }} catch (_) {{
                preview.style.display = 'none';
            }}
        }}

        async function submitManualGlyph() {{
            const val = document.getElementById('manualGlyphJson').value.trim();
            if (!val) {{
                alert('Silakan masukkan data JSON glyph');
                return;
            }}
            let glyph;
            try {{
                glyph = JSON.parse(val);
                if (!Array.isArray(glyph) || glyph.length === 0) throw new Error('Format harus berupa array stroke');
            }} catch (e) {{
                alert('Format JSON glyph tidak valid: ' + e.message);
                return;
            }}
            try {{
                const res = await apiFetch('/api/bank-angka/save', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        digit: manualSelectedDigit,
                        glyph: glyph
                    }})
                }});
                if (res && res.ok) {{
                    alert(`✅ Angka ${{manualSelectedDigit}} berhasil ditambahkan ke bank!`);
                    closeModal('manualGlyphModal');
                    loadBankAngka();
                }}
            }} catch (e) {{
                alert('Gagal menyimpan: ' + e.message);
            }}
        }}

        // Initial setup
        loadNotifications();
        refreshDashboard();
        startLiveStream();
        setInterval(() => {{ if (!streamConnected) refreshDashboard(); }}, 5000);
    </script>
</body>
</html>
"""
