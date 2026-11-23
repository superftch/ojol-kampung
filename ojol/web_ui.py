"""Embedded Web UI for Kampung Ojol Automation."""

import html
import json


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
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
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
</head>
<body>
    <div class="card">
        <div class="logo">
            <div class="logo-icon">🛵</div>
            <h1>Kampung Ojol Automation</h1>
            <p>Panel Kontrol Otomasi Multi-Akun</p>
        </div>

        {f'<div class="alert alert-danger">{escaped_error}</div>' if escaped_error else ""}
        {f'<div class="alert alert-success">{escaped_success}</div>' if escaped_success else ""}

        {
        '''
        <div class="tabs">
            <div class="tab active" onclick="switchTab('tab-password')">Username & Password</div>
            <div class="tab" onclick="switchTab('tab-telegram')">Telegram</div>
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
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
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
</head>
<body>
    <div class="card">
        <div class="logo">
            <div class="logo-icon">🛵</div>
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
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
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
</head>
<body>
    <div class="card">
        <div class="logo">
            <div class="logo-icon">🔐</div>
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


def dashboard_html(user: dict, bot_username: str = "") -> str:
    user_json = json.dumps(user)

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard · Kampung Ojol Automation</title>
    <style>
        :root {{
            --bg: #0b1120;
            --surface: #1e293b;
            --surface-hover: #293548;
            --border: #334155;
            --text: #f8fafc;
            --text-muted: #94a3b8;
            --primary: #3b82f6;
            --primary-hover: #2563eb;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --purple: #8b5cf6;
            --radius: 12px;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        body {{
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }}
        /* Header */
        header {{
            background: var(--surface);
            border-bottom: 1px solid var(--border);
            padding: 14px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            position: sticky;
            top: 0;
            z-index: 100;
        }}
        .brand {{ display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: 18px; }}
        .header-actions {{ display: flex; align-items: center; gap: 16px; }}
        .account-select-wrap {{ display: flex; align-items: center; gap: 8px; }}
        select.account-select {{
            background: #0f172a;
            color: var(--text);
            border: 1px solid var(--border);
            padding: 8px 12px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 500;
            outline: none;
            cursor: pointer;
        }}
        .user-badge {{
            display: flex;
            align-items: center;
            gap: 8px;
            background: #0f172a;
            border: 1px solid var(--border);
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 13px;
        }}
        .tg-status {{
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
        }}
        .tg-status.connected {{ background: var(--success); box-shadow: 0 0 6px var(--success); }}
        .tg-status.disconnected {{ background: var(--text-muted); }}

        /* Navigation Tabs */
        nav.nav-tabs {{
            background: var(--surface);
            border-bottom: 1px solid var(--border);
            padding: 0 24px;
            display: flex;
            gap: 8px;
            overflow-x: auto;
        }}
        .nav-btn {{
            padding: 14px 18px;
            font-size: 14px;
            font-weight: 600;
            color: var(--text-muted);
            background: none;
            border: none;
            border-bottom: 3px solid transparent;
            cursor: pointer;
            transition: all 0.2s;
            white-space: nowrap;
        }}
        .nav-btn:hover {{ color: var(--text); }}
        .nav-btn.active {{ color: var(--primary); border-bottom-color: var(--primary); }}

        /* Container */
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 24px 16px;
            width: 100%;
            flex: 1;
        }}
        .tab-panel {{ display: none; }}
        .tab-panel.active {{ display: block; }}

        /* Status Hero Card */
        .hero-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 24px;
            margin-bottom: 24px;
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 20px;
        }}
        .hero-info {{ display: flex; align-items: center; gap: 16px; }}
        .status-pulse {{
            width: 52px;
            height: 52px;
            border-radius: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 26px;
            background: #0f172a;
            border: 1px solid var(--border);
        }}
        .hero-details h2 {{ font-size: 20px; font-weight: 700; margin-bottom: 4px; }}
        .hero-details p {{ font-size: 14px; color: var(--text-muted); }}
        .hero-stats {{ display: flex; gap: 24px; }}
        .stat-item {{ text-align: right; }}
        .stat-label {{ font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }}
        .stat-val {{ font-size: 20px; font-weight: 700; color: var(--text); margin-top: 2px; }}

        /* Unified Control Toolbar */
        .control-toolbar {{
            background: linear-gradient(180deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.8) 100%);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 12px 18px;
            margin-bottom: 24px;
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
        }}
        .toolbar-group-wrap {{
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 20px;
        }}
        .control-group {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .control-group-title {{
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-muted);
            white-space: nowrap;
        }}
        .btn-segment-group {{
            display: inline-flex;
            background: #0b1120;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 8px;
            padding: 3px;
            gap: 3px;
        }}
        .btn-segment-group .btn {{
            padding: 7px 15px;
            font-size: 13px;
            font-weight: 600;
            border-radius: 6px;
            border: 1px solid transparent;
            background: transparent;
            color: var(--text-muted);
            transition: all 0.15s ease;
        }}
        .btn-segment-group .btn:hover:not(:disabled) {{
            color: var(--text);
            background: rgba(255, 255, 255, 0.07);
        }}
        .btn-segment-group .btn.active-run {{
            background: var(--primary) !important;
            color: #ffffff !important;
            box-shadow: 0 1px 4px rgba(59, 130, 246, 0.4);
        }}
        .btn-segment-group .btn.active-stop {{
            background: #ef4444 !important;
            color: #ffffff !important;
            box-shadow: 0 1px 4px rgba(239, 68, 68, 0.4);
        }}
        .btn-segment-group .btn.active-needs {{
            background: var(--purple) !important;
            color: #ffffff !important;
            box-shadow: 0 1px 4px rgba(139, 92, 246, 0.4);
        }}
        .toolbar-utilities {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .btn-utility {{
            padding: 8px 14px;
            font-size: 13px;
            font-weight: 500;
            background: #1e293b;
            color: var(--text);
            border: 1px solid var(--border);
            border-radius: 8px;
            transition: all 0.15s ease;
        }}
        .btn-utility:hover:not(:disabled) {{
            background: #293548;
            border-color: #475569;
        }}
        .action-bar {{
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            margin-bottom: 24px;
        }}
        .btn {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            padding: 10px 18px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            border: 1px solid transparent;
            cursor: pointer;
            transition: all 0.15s ease-in-out;
            text-decoration: none;
            user-select: none;
            position: relative;
        }}
        .btn:active:not(:disabled) {{
            transform: scale(0.98);
        }}
        .btn:disabled, .btn[disabled] {{
            opacity: 0.55 !important;
            cursor: not-allowed !important;
            pointer-events: none !important;
            filter: grayscale(25%);
        }}
        .btn-loading {{
            opacity: 0.85 !important;
            cursor: wait !important;
            pointer-events: none !important;
        }}
        .btn-spinner {{
            width: 15px;
            height: 15px;
            border: 2px solid rgba(255, 255, 255, 0.35);
            border-top-color: #ffffff;
            border-radius: 50%;
            animation: btn-spin 0.65s linear infinite;
            display: inline-block;
            vertical-align: middle;
            flex-shrink: 0;
        }}
        @keyframes btn-spin {{
            to {{ transform: rotate(360deg); }}
        }}
        .btn-primary {{ background: var(--primary); color: white; }}
        .btn-primary:hover {{ background: var(--primary-hover); }}
        .btn-success {{ background: var(--success); color: white; }}
        .btn-success:hover {{ background: #059669; }}
        .btn-danger {{ background: var(--danger); color: white; }}
        .btn-danger:hover {{ background: #dc2626; }}
        .btn-secondary {{ background: #334155; color: var(--text); border-color: rgba(255, 255, 255, 0.08); }}
        .btn-secondary:hover {{ background: #475569; }}
        .btn-purple {{ background: var(--purple); color: white; }}
        .btn-purple:hover {{ background: #7c3aed; }}

        /* Non-blocking Toast Notification */
        .toast-container {{
            position: fixed;
            bottom: 24px;
            right: 24px;
            z-index: 9999;
            display: flex;
            flex-direction: column;
            gap: 10px;
            max-width: 380px;
            pointer-events: none;
        }}
        .toast {{
            background: #1e293b;
            color: #f8fafc;
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 12px 18px;
            font-size: 13px;
            font-weight: 500;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.5);
            display: flex;
            align-items: center;
            gap: 10px;
            pointer-events: auto;
            transform: translateY(20px);
            opacity: 0;
            transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
        }}
        .toast.toast-show {{
            transform: translateY(0);
            opacity: 1;
        }}
        .toast-success {{
            border-left: 4px solid var(--success);
        }}
        .toast-error {{
            border-left: 4px solid var(--danger);
        }}
        .toast-info {{
            border-left: 4px solid var(--primary);
        }}

        /* Fleet Summary Section */
        .fleet-box {{
            background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 20px 24px;
            margin-bottom: 24px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
        }}
        .fleet-header {{
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            margin-bottom: 16px;
            padding-bottom: 14px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.07);
        }}
        .fleet-title-wrap {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .fleet-icon {{
            width: 42px;
            height: 42px;
            border-radius: 12px;
            background: rgba(59, 130, 246, 0.15);
            border: 1px solid rgba(59, 130, 246, 0.3);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 22px;
        }}
        .fleet-title {{
            font-size: 17px;
            font-weight: 700;
            color: var(--text);
        }}
        .fleet-subtitle {{
            font-size: 13px;
            color: var(--text-muted);
        }}
        .fleet-badges {{
            display: flex;
            gap: 8px;
            align-items: center;
            flex-wrap: wrap;
        }}
        .fleet-badge {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            background: rgba(15, 23, 42, 0.8);
            border: 1px solid var(--border);
            color: var(--text-muted);
        }}
        .fleet-badge.badge-running {{
            background: rgba(16, 185, 129, 0.15);
            border-color: rgba(16, 185, 129, 0.3);
            color: #34d399;
        }}

        .fleet-stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 12px;
            margin-bottom: 18px;
        }}
        .fleet-stat-card {{
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 10px;
            padding: 14px 16px;
            display: flex;
            flex-direction: column;
            gap: 4px;
            transition: border-color 0.2s;
        }}
        .fleet-stat-card:hover {{
            border-color: rgba(255, 255, 255, 0.15);
        }}
        .fleet-stat-label {{
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-muted);
        }}
        .fleet-stat-val {{
            font-size: 20px;
            font-weight: 700;
            color: var(--text);
        }}
        .fleet-stat-val.text-amber {{ color: #fbbf24; }}
        .fleet-stat-val.text-green {{ color: #34d399; }}
        .fleet-stat-val.text-blue {{ color: #38bdf8; }}

        .fleet-accounts-title {{
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-muted);
            margin-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .fleet-cards-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
            gap: 12px;
        }}
        .account-fleet-card {{
            background: rgba(15, 23, 42, 0.7);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 14px;
            cursor: pointer;
            transition: all 0.2s ease;
            position: relative;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            gap: 10px;
        }}
        .account-fleet-card:hover {{
            border-color: #64748b;
            transform: translateY(-2px);
        }}
        .account-fleet-card.is-active-account {{
            border-color: var(--primary);
            background: rgba(59, 130, 246, 0.08);
            box-shadow: 0 0 0 1px var(--primary);
        }}
        .afc-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .afc-name-wrap {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-weight: 700;
            font-size: 15px;
            color: var(--text);
        }}
        .afc-tag {{
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
            padding: 2px 7px;
            border-radius: 10px;
            background: rgba(59, 130, 246, 0.2);
            color: #60a5fa;
            border: 1px solid rgba(59, 130, 246, 0.4);
        }}
        .afc-status {{
            font-size: 12px;
            color: var(--text-muted);
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .afc-metrics {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: rgba(0, 0, 0, 0.25);
            border-radius: 6px;
            padding: 8px 10px;
            font-size: 12px;
        }}
        .afc-metric-item {{
            display: flex;
            flex-direction: column;
        }}
        .afc-metric-item .m-lbl {{ font-size: 10px; color: var(--text-muted); }}
        .afc-metric-item .m-val {{ font-weight: 700; color: var(--text); }}

        .active-account-divider {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin: 28px 0 16px 0;
        }}
        .active-account-divider .line {{
            flex: 1;
            height: 1px;
            background: var(--border);
        }}
        .active-account-divider .banner-tag {{
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 0.5px;
            text-transform: uppercase;
            color: #38bdf8;
            background: rgba(56, 189, 248, 0.1);
            border: 1px solid rgba(56, 189, 248, 0.25);
            padding: 6px 16px;
            border-radius: 20px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        /* Grid */
        .grid-2 {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 24px;
            margin-bottom: 24px;
        }}
        .grid-4 {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 20px;
        }}
        .card-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 1px solid var(--border);
        }}
        .card-title {{ font-size: 16px; font-weight: 700; display: flex; align-items: center; gap: 8px; }}

        /* Progress Bars / Gauges */
        .meter-row {{ margin-bottom: 14px; }}
        .meter-label {{ display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 6px; }}
        .meter-name {{ color: var(--text); font-weight: 500; display: flex; align-items: center; gap: 6px; }}
        .meter-val {{ font-weight: 700; }}
        .meter-bar {{
            height: 10px;
            background: #0f172a;
            border-radius: 5px;
            overflow: hidden;
            position: relative;
        }}
        .meter-fill {{
            height: 100%;
            border-radius: 5px;
            transition: width 0.4s ease;
        }}
        .fill-green {{ background: var(--success); }}
        .fill-orange {{ background: var(--warning); }}
        .fill-red {{ background: var(--danger); }}

        /* Toggle Switches */
        .toggle-item {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }}
        .toggle-item:last-child {{ border-bottom: none; }}
        .toggle-info {{ display: flex; flex-direction: column; }}
        .toggle-title {{ font-size: 14px; font-weight: 600; }}
        .toggle-desc {{ font-size: 12px; color: var(--text-muted); }}
        .switch {{
            position: relative;
            display: inline-block;
            width: 44px;
            height: 24px;
        }}
        .switch input {{ opacity: 0; width: 0; height: 0; }}
        .slider {{
            position: absolute;
            cursor: pointer;
            top: 0; left: 0; right: 0; bottom: 0;
            background-color: #334155;
            transition: .3s;
            border-radius: 24px;
        }}
        .slider:before {{
            position: absolute;
            content: "";
            height: 18px;
            width: 18px;
            left: 3px;
            bottom: 3px;
            background-color: white;
            transition: .3s;
            border-radius: 50%;
        }}
        input:checked + .slider {{ background-color: var(--primary); }}
        input:checked + .slider:before {{ transform: translateX(20px); }}

        /* Log Feed */
        .log-box {{
            background: #090d16;
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 14px;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            font-size: 12px;
            color: #38bdf8;
            max-height: 220px;
            overflow-y: auto;
            white-space: pre-wrap;
            line-height: 1.6;
        }}

        /* Table */
        table.data-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }}
        table.data-table th, table.data-table td {{
            padding: 12px 14px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }}
        table.data-table th {{
            color: var(--text-muted);
            font-size: 12px;
            text-transform: uppercase;
            font-weight: 600;
        }}
        table.data-table tr:hover {{ background: rgba(255, 255, 255, 0.02); }}

        /* Modal */
        .modal {{
            display: none;
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0, 0, 0, 0.75);
            backdrop-filter: blur(4px);
            z-index: 1000;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .modal.open {{ display: flex; }}
        .modal-content {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            max-width: 500px;
            width: 100%;
            padding: 24px;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
        }}
        .modal-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 16px;
        }}
        .modal-header h3 {{ font-size: 18px; font-weight: 700; }}
        .close-btn {{ background: none; border: none; color: var(--text-muted); font-size: 20px; cursor: pointer; }}
        textarea.cookie-box {{
            width: 100%;
            height: 120px;
            background: #0f172a;
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text);
            padding: 10px;
            font-family: monospace;
            font-size: 12px;
            outline: none;
            margin-bottom: 16px;
            resize: vertical;
        }}
    </style>
</head>
<body>
    <header>
        <div class="brand">
            <span>🛵</span>
            <span>Kampung Ojol</span>
        </div>
        <div class="header-actions">
            <div class="account-select-wrap">
                <select id="accountDropdown" class="account-select" onchange="switchAccount(this.value)">
                    <option value="">Memuat akun...</option>
                </select>
                <button class="btn btn-secondary" style="padding: 6px 10px; font-size: 12px;" onclick="openModal('addAccountModal')">+ Akun</button>
            </div>
            <div class="user-badge" title="Web Dashboard • Online">
                <span class="tg-status connected"></span>
                <span id="navUsername">{html.escape(user.get("username", "User"))}</span>
            </div>
            <button class="btn btn-secondary" style="padding: 6px 12px; font-size: 12px;" onclick="logout()">Keluar</button>
        </div>
    </header>

    <nav class="nav-tabs">
        <button class="nav-btn active" onclick="showTab('tab-dashboard')">📊 Dashboard</button>
        <button class="nav-btn" onclick="showTab('tab-auto')">⚙️ Auto & Kebutuhan</button>
        <button class="nav-btn" onclick="showTab('tab-accounts')">👥 Akun Saya</button>
        <button class="nav-btn" onclick="showTab('tab-notifications')">🔔 Notifikasi <span id="notifBadge" style="display:none; background:var(--danger); color:white; font-size:10px; padding:2px 6px; border-radius:10px; margin-left:4px;">0</span></button>
        <button id="adminTabBtn" class="nav-btn" style="display: {"block" if user.get("role") == "admin" else "none"};" onclick="showTab('tab-admin')">🛡️ Admin Panel</button>
    </nav>

    <div class="container">
        <!-- TAB 1: DASHBOARD -->
        <div id="tab-dashboard" class="tab-panel active">
            <!-- Warning Banner: Kuota Narik Otomatis Habis (Beralih ke Extension Mode Kendarai) -->
            <div id="limitNoticeCard" style="display: none; background: linear-gradient(135deg, rgba(239, 68, 68, 0.18), rgba(245, 158, 11, 0.18)); border: 1px solid rgba(245, 158, 11, 0.5); border-radius: var(--radius); padding: 18px 20px; margin-bottom: 24px; box-shadow: 0 4px 16px rgba(245, 158, 11, 0.1);">
                <div style="display: flex; align-items: flex-start; gap: 14px;">
                    <div style="font-size: 32px; line-height: 1;">⚠️</div>
                    <div style="flex: 1;">
                        <h3 style="font-size: 16px; font-weight: 700; color: #fbbf24; margin-bottom: 4px;">
                            Batas Narik Mode Otomatis Hari Ini Tercapai (Maksimal 14 Jam / 840 Menit)
                        </h3>
                        <p style="font-size: 13px; color: #cbd5e1; line-height: 1.5; margin-bottom: 12px;">
                            Kuota narik harian Mode Otomatis akun ini telah mencapai batas maksimal (14 jam). Server game melarang order otomatis baru hingga reset jam 00:00 WIB.<br>
                            <b>Namun Anda tetap bisa narik TANPA BATAS dengan beralih ke Mode Kendarai</b> (<code style="background:rgba(0,0,0,0.3); padding:2px 5px; border-radius:4px; color:#38bdf8;">kendara.tanpaBatas: true</code>) menggunakan <b>Ekstensi Chrome KampungSebelah Helper</b>!
                        </p>
                        <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                            <a href="/api/extension/download" class="btn btn-warning" style="background:#f59e0b; color:#0f172a; font-weight:700;">📦 Download Extension (.ZIP)</a>
                            <button class="btn btn-secondary" onclick="openModal('extensionModal')">📖 Panduan Pasang Extension</button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Onboarding Card: Belum Ada Akun (Langsung Import Cookie) -->
            <div id="onboardingCard" style="display: none; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 32px 28px; margin-bottom: 24px;">
                <div style="max-width: 780px; margin: 0 auto;">
                    <div style="display: flex; align-items: flex-start; gap: 16px; margin-bottom: 18px;">
                        <div style="width: 48px; height: 48px; border-radius: 12px; background: rgba(59, 130, 246, 0.12); border: 1px solid rgba(59, 130, 246, 0.3); display: flex; align-items: center; justify-content: center; font-size: 24px; flex-shrink: 0;">🛵</div>
                        <div>
                            <h2 style="font-size: 19px; font-weight: 700; color: #f8fafc; letter-spacing: -0.01em; margin-bottom: 4px;">
                                Hubungkan Akun KampungSebelah
                            </h2>
                            <p style="font-size: 13px; color: var(--text-muted); line-height: 1.5;">
                                Belum ada akun game yang terhubung. Masukkan cookie sesi peramban game Anda di bawah untuk mengaktifkan otomatisasi order di background.
                            </p>
                        </div>
                    </div>

                    <!-- Inline Import Cookie Form -->
                    <div style="background: #0f172a; border: 1px solid var(--border); border-radius: 10px; padding: 20px; margin-bottom: 22px;">
                        <div style="margin-bottom: 14px;">
                            <label style="display: block; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; color: #94a3b8; margin-bottom: 6px;">
                                Nama Akun (Otomatis Sesuai Nickname Game)
                            </label>
                            <input type="text" id="onboardingAccountName" placeholder="Otomatis memakai Nickname karakter game (kosongkan saja)" style="width: 100%; padding: 10px 14px; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; color: var(--text); font-size: 13px; outline: none;">
                        </div>

                        <div style="margin-bottom: 16px;">
                            <label style="display: block; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; color: #94a3b8; margin-bottom: 6px;">
                                Cookie Sesi Game (Nilai vtW... atau Format Utuh)
                            </label>
                            <textarea id="onboardingCookieInput" rows="4" placeholder="Tempel cookie KampungSebelah di sini (contoh: vtW1tcmp4qCDI9cxOfOjr0YSykpDHKfS...)" style="width: 100%; padding: 12px 14px; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; color: #38bdf8; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 13px; outline: none; resize: vertical; line-height: 1.5;"></textarea>
                        </div>

                        <div style="display: flex; justify-content: flex-end; gap: 12px; align-items: center; flex-wrap: wrap;">
                            <span id="onboardingLoadingText" style="display: none; font-size: 13px; color: #fbbf24;">
                                ⏳ Memverifikasi cookie dengan server KampungSebelah...
                            </span>
                            <button id="btnOnboardingSubmit" class="btn btn-primary" onclick="submitOnboardingCookie()" style="padding: 10px 22px; font-weight: 600; font-size: 14px;">
                                🚀 Hubungkan Akun & Mulai
                            </button>
                        </div>
                    </div>

                    <!-- 3 Langkah Cepat -->
                    <div style="border-top: 1px solid var(--border); padding-top: 18px;">
                        <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); margin-bottom: 12px;">
                            Cara Mengambil Cookie dari Browser (3 Langkah Mudah)
                        </div>
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px;">
                            <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px;">
                                <div style="font-size: 11px; font-weight: 700; color: #38bdf8; margin-bottom: 4px;">1. BUKA GAME</div>
                                <p style="font-size: 12px; color: #94a3b8; line-height: 1.4; margin: 0;">
                                    Buka <code style="color:#e2e8f0; font-size: 11px;">kampungsebelah.com</code> di browser dan pastikan sudah masuk sampai desa tampil.
                                </p>
                            </div>
                            <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px;">
                                <div style="font-size: 11px; font-weight: 700; color: #38bdf8; margin-bottom: 4px;">2. TEKAN F12</div>
                                <p style="font-size: 12px; color: #94a3b8; line-height: 1.4; margin: 0;">
                                    Buka tab <b>Application</b> (Chrome) atau <b>Storage</b> (Firefox) &gt; <b>Cookies</b> &gt; cari nilai <code style="color:#e2e8f0; font-size: 11px;">vtW...</code>.
                                </p>
                            </div>
                            <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px;">
                                <div style="font-size: 11px; font-weight: 700; color: #38bdf8; margin-bottom: 4px;">3. SALIN & TEMPEL</div>
                                <p style="font-size: 12px; color: #94a3b8; line-height: 1.4; margin: 0;">
                                    Salin nilainya, tempelkan di kotak di atas, lalu klik <b>Hubungkan Akun & Mulai</b>.
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Active Dashboard Section (Tampil saat akun sudah terhubung) -->
            <div id="activeDashboardSection">
                <!-- TOP SECTION: Summary All Accounts (Armada) -->
                <div class="fleet-box">
                    <div class="fleet-header">
                        <div class="fleet-title-wrap">
                            <div class="fleet-icon">🌐</div>
                            <div>
                                <div class="fleet-title">Ringkasan Semua Akun (Armada)</div>
                                <div class="fleet-subtitle">Total koin, trip, dan status operasional seluruh akun game Anda</div>
                            </div>
                        </div>
                        <div class="fleet-badges">
                            <span id="fleetRunningBadge" class="fleet-badge badge-running">⚡ 0 Worker Aktif</span>
                            <span id="fleetTotalAccountsBadge" class="fleet-badge">👥 0 Akun</span>
                        </div>
                    </div>

                    <!-- Fleet KPI Cards -->
                    <div class="fleet-stats-grid">
                        <div class="fleet-stat-card">
                            <div class="fleet-stat-label">💰 Saldo Gabungan</div>
                            <div id="fleetTotalWallet" class="fleet-stat-val text-amber">- koin</div>
                        </div>
                        <div class="fleet-stat-card">
                            <div class="fleet-stat-label">📈 Penghasilan Hari Ini</div>
                            <div id="fleetTotalIncome" class="fleet-stat-val text-green">+0 koin</div>
                        </div>
                        <div class="fleet-stat-card">
                            <div class="fleet-stat-label">🛵 Trip Gabungan Hari Ini</div>
                            <div id="fleetTotalTrips" class="fleet-stat-val text-blue">0 Trip</div>
                        </div>
                        <div class="fleet-stat-card">
                            <div class="fleet-stat-label">👥 Total Armada Akun</div>
                            <div id="fleetCountAccounts" class="fleet-stat-val">-</div>
                        </div>
                        <div class="fleet-stat-card">
                            <div class="fleet-stat-label">⚡ Worker Berjalan</div>
                            <div id="fleetCountWorkers" class="fleet-stat-val text-green">-</div>
                        </div>
                    </div>

                    <!-- Accounts Cards Grid / Switcher -->
                    <div class="fleet-accounts-title">
                        <span>Pilih & Pantau Akun:</span>
                        <span style="font-weight: normal; text-transform: none; color: #94a3b8; font-size: 11px;">Klik kartu untuk beralih kontrol akun</span>
                    </div>
                    <div id="fleetAccountsGrid" class="fleet-cards-grid">
                        <!-- Populated dynamically via JS -->
                    </div>
                </div>

                <!-- Visual Divider to Active Account Detail & Control -->
                <div class="active-account-divider">
                    <div class="line"></div>
                    <div class="banner-tag">
                        <span>🛵 DETAIL & KONTROL AKUN AKTIF:</span>
                        <strong id="activeAccountBannerName" style="color: #fff;">-</strong>
                    </div>
                    <div class="line"></div>
                </div>

            <!-- Hero Status Card -->
            <div class="hero-card">
                <div class="hero-info">
                    <div id="statusIcon" class="status-pulse">⚪</div>
                    <div class="hero-details">
                        <h2 id="statusTitle">Memuat status...</h2>
                        <p id="statusSubtitle">Menghubungkan ke controller akun</p>
                    </div>
                </div>
                <div class="hero-stats">
                    <div class="stat-item">
                        <div class="stat-label">Saldo Koin</div>
                        <div id="walletVal" class="stat-val">-</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Trip Hari Ini</div>
                        <div id="tripsVal" class="stat-val">-</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">⏱️ Sisa Waktu / Countdown</div>
                        <div id="countdownVal" class="stat-val" style="color: #38bdf8;">-</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">Presence Online</div>
                        <div id="presenceVal" class="stat-val">-</div>
                    </div>
                </div>
            </div>

            <!-- Unified Control Toolbar -->
            <div class="control-toolbar">
                <div class="toolbar-group-wrap">
                    <!-- Ojol Order Automation -->
                    <div class="control-group">
                        <span class="control-group-title">🛵 Order Ojol</span>
                        <div class="btn-segment-group">
                            <button id="btnRunOjol" class="btn" onclick="controlAction('run')">▶️ Jalankan</button>
                            <button id="btnStopOjol" class="btn" onclick="controlAction('stop')">⏹️ Hentikan</button>
                        </div>
                    </div>

                    <!-- Character Needs Automation -->
                    <div class="control-group">
                        <span class="control-group-title">🍲 Kebutuhan</span>
                        <div class="btn-segment-group">
                            <button id="btnRunNeeds" class="btn" onclick="controlAction('run-needs')">🔄 Jalankan</button>
                            <button id="btnStopNeeds" class="btn" onclick="controlAction('stop-needs')">⏹️ Hentikan</button>
                        </div>
                    </div>
                </div>

                <!-- Right Utility Actions -->
                <div class="toolbar-utilities">
                    <button class="btn btn-utility" onclick="openModal('cookieModal')" title="Perbarui cookie game">🍪 Ganti Cookie</button>
                    <button id="btnRefreshDash" class="btn btn-utility" onclick="manualRefreshDashboard()" title="Segarkan status dashboard">🔄 Refresh</button>
                </div>
            </div>

            <!-- Grid: Kendaraan & Kebutuhan -->
            <div class="grid-2">
                <!-- Card 1: Resource Kendaraan -->
                <div class="card">
                    <div class="card-header">
                        <div class="card-title">🛵 Resource Kendaraan & Kuota</div>
                    </div>
                    <div class="meter-row">
                        <div class="meter-label">
                            <span class="meter-name">⛽ Bensin</span>
                            <span id="fuelText" class="meter-val">-</span>
                        </div>
                        <div class="meter-bar"><div id="fuelBar" class="meter-fill fill-green" style="width: 0%;"></div></div>
                    </div>
                    <div class="meter-row">
                        <div class="meter-label">
                            <span class="meter-name">🔧 Kondisi Mesin</span>
                            <span id="condText" class="meter-val">-</span>
                        </div>
                        <div class="meter-bar"><div id="condBar" class="meter-fill fill-green" style="width: 0%;"></div></div>
                    </div>
                    <div class="meter-row">
                        <div class="meter-label">
                            <span class="meter-name">📶 Kuota HP</span>
                            <span id="dataText" class="meter-val">-</span>
                        </div>
                        <div class="meter-bar"><div id="dataBar" class="meter-fill fill-green" style="width: 0%;"></div></div>
                    </div>
                </div>

                <!-- Card 2: Kebutuhan Karakter -->
                <div class="card">
                    <div class="card-header">
                        <div class="card-title">🍲 Kebutuhan Karakter</div>
                    </div>
                    <div class="meter-row">
                        <div class="meter-label">
                            <span class="meter-name">🍲 Makan</span>
                            <span id="makanText" class="meter-val">-</span>
                        </div>
                        <div class="meter-bar"><div id="makanBar" class="meter-fill fill-green" style="width: 0%;"></div></div>
                    </div>
                    <div class="meter-row">
                        <div class="meter-label">
                            <span class="meter-name">❤️ Kesehatan</span>
                            <span id="kesehatanText" class="meter-val">-</span>
                        </div>
                        <div class="meter-bar"><div id="kesehatanBar" class="meter-fill fill-green" style="width: 0%;"></div></div>
                    </div>
                    <div class="meter-row">
                        <div class="meter-label">
                            <span class="meter-name">🥊 Fisik / Gym</span>
                            <span id="fisikText" class="meter-val">-</span>
                        </div>
                        <div class="meter-bar"><div id="fisikBar" class="meter-fill fill-green" style="width: 0%;"></div></div>
                    </div>
                    <div class="meter-row">
                        <div class="meter-label">
                            <span class="meter-name">🎡 Rekreasi</span>
                            <span id="rekreasiText" class="meter-val">-</span>
                        </div>
                        <div class="meter-bar"><div id="rekreasiBar" class="meter-fill fill-green" style="width: 0%;"></div></div>
                    </div>
                    <div class="meter-row">
                        <div class="meter-label">
                            <span class="meter-name">🧼 Kebersihan</span>
                            <span id="kebersihanText" class="meter-val">-</span>
                        </div>
                        <div class="meter-bar"><div id="kebersihanBar" class="meter-fill fill-green" style="width: 0%;"></div></div>
                    </div>
                    <div class="meter-row">
                        <div class="meter-label">
                            <span class="meter-name">🚽 Buang Air (WC)</span>
                            <span id="wcText" class="meter-val">-</span>
                        </div>
                        <div class="meter-bar"><div id="wcBar" class="meter-fill fill-green" style="width: 0%;"></div></div>
                    </div>
                    <div class="meter-row">
                        <div class="meter-label">
                            <span class="meter-name">✂️ Penampilan</span>
                            <span id="penampilanText" class="meter-val">-</span>
                        </div>
                        <div class="meter-bar"><div id="penampilanBar" class="meter-fill fill-green" style="width: 0%;"></div></div>
                    </div>
                    <div class="meter-row">
                        <div class="meter-label">
                            <span class="meter-name">🏠 Kondisi Rumah</span>
                            <span id="rumahText" class="meter-val">-</span>
                        </div>
                        <div class="meter-bar"><div id="rumahBar" class="meter-fill fill-green" style="width: 0%;"></div></div>
                    </div>
                </div>

                <!-- Card 3: Extension & Mode Kendarai Info -->
                <div class="card" style="grid-column: 1 / -1; border-color: rgba(59, 130, 246, 0.4); background: linear-gradient(135deg, rgba(30, 58, 138, 0.15), rgba(15, 23, 42, 0.8));">
                    <div class="card-header">
                        <div class="card-title">🧩 Ekstensi Chrome (Mode Kendarai Tanpa Batas 14 Jam & Radar)</div>
                        <span style="background: rgba(16, 185, 129, 0.2); color: #34d399; font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 6px;">v2.2.0 Siap Pakai</span>
                    </div>
                    <p style="font-size: 13px; color: var(--text-muted); line-height: 1.6; margin-bottom: 14px;">
                        Saat limit harian 14 jam (840 menit) di Mode Otomatis habis, Anda bisa melanjutkan narik order <b>TANPA BATAS</b> dengan menggunakan <b>Mode Kendarai</b> via Ekstensi Chrome resmi KampungSebelah Helper. Ekstensi ini juga dilengkapi dengan <b>Auto-Beli Kebutuhan</b> (Bensin SPBU, Bengkel, Kuota), <b>Anti-Cek Kilat (&gt;2.5s)</b>, <b>Radar Pusaka TPU Mbah Rukmi</b>, dan <b>Auto-Mancing Pro</b>.
                    </p>
                    <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                        <a href="/api/extension/download" class="btn btn-primary">📦 Download File ZIP Ekstensi</a>
                        <button class="btn btn-secondary" onclick="openModal('extensionModal')">📖 Lihat Tutorial Pemasangan</button>
                    </div>
                </div>
            </div>

            <!-- Activity Log Card -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">📜 Log Aktivitas & Status</div>
                    <button class="btn btn-secondary" style="padding: 4px 8px; font-size: 11px;" onclick="refreshDashboard()">Refresh Log</button>
                </div>
                <div id="logConsole" class="log-box">Memuat aktivitas terbaru...</div>
            </div>
            </div> <!-- end #activeDashboardSection -->
        </div>

        <!-- TAB 2: AUTO & KEBUTUHAN -->
        <div id="tab-auto" class="tab-panel">
            <div class="grid-2">
                <div class="card">
                    <div class="card-header">
                        <div class="card-title">⚡ Mode Ojol Web: Otomatis (Background Server)</div>
                        <span style="background: rgba(16, 185, 129, 0.2); color: #34d399; font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 6px;">Aktif (Paling Stabil)</span>
                    </div>
                    <p style="font-size: 13px; color: var(--text-muted); line-height: 1.5; margin-bottom: 12px;">
                        Web Dashboard khusus menjalankan <b>Mode Otomatis</b> di latar belakang server (hemat daya, bebas macet 3D, durasi & omzet optimal). Kuota narik: <b>14 jam / hari (840 menit)</b>.
                    </p>
                    <div style="background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.25); border-radius: 8px; padding: 10px 12px; font-size: 12px; color: #cbd5e1;">
                        <b style="color: #fbbf24;">Ingin Mode Kendarai (Tanpa Batas 14 Jam)?</b><br>
                        Mode Kendarai dijalankan khusus via <b>Ekstensi Chrome</b> yang langsung menyetir di browser Anda.<br>
                        <div style="margin-top: 8px; display: flex; gap: 8px; flex-wrap: wrap;">
                            <a href="/api/extension/download" class="btn btn-warning" style="font-size: 11px; padding: 5px 10px; background:#f59e0b; color:#0f172a; font-weight:700;">📦 Download Ekstensi (.ZIP)</a>
                            <button class="btn btn-secondary" style="font-size: 11px; padding: 5px 10px;" onclick="openModal('extensionModal')">📖 Tutorial Pasang</button>
                        </div>
                    </div>
                    <input type="checkbox" id="modeOjolToggle" style="display: none;">
                </div>

                <div class="card">
                    <div class="card-header"><div class="card-title">📚 Auto Belajar (Study)</div></div>
                    <div class="toggle-item">
                        <div class="toggle-info">
                            <span class="toggle-title">📖 Auto Perpustakaan (Gratis)</span>
                            <span class="toggle-desc">Menjalankan kuis belajar gratis di perpustakaan secara otomatis</span>
                        </div>
                        <label class="switch">
                            <input type="checkbox" id="autoPerpusToggle" onchange="toggleAuto('perpus', this.checked)">
                            <span class="slider"></span>
                        </label>
                    </div>
                    <div class="toggle-item">
                        <div class="toggle-info">
                            <span class="toggle-title">🎓 Auto Kuliah (Berbayar)</span>
                            <span class="toggle-desc">Mengikuti kuliah otomatis di kampus (biaya koin) hingga level maksimal</span>
                        </div>
                        <label class="switch">
                            <input type="checkbox" id="autoKuliahToggle" onchange="toggleAuto('kuliah', this.checked)">
                            <span class="slider"></span>
                        </label>
                    </div>
                    <div class="toggle-item">
                        <div class="toggle-info">
                            <span class="toggle-title">🔄 Rotasi Otomatis Saat Max</span>
                            <span class="toggle-desc">Beralih ke bidang lain jika bidang saat ini sudah mencapai level maksimum</span>
                        </div>
                        <label class="switch">
                            <input type="checkbox" id="studyRotateToggle" onchange="toggleAuto('auto_subject', this.checked)">
                            <span class="slider"></span>
                        </label>
                    </div>
                    <div style="margin-top: 14px;">
                        <label style="font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 6px;">Pilih Bidang Belajar:</label>
                        <select id="studySubjectSelect" class="account-select" style="width: 100%;" onchange="setStudySubject(this.value)">
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
                <div class="card-header"><div class="card-title">🍲 Pengaturan Auto Kebutuhan</div></div>
                <div class="toggle-item">
                    <div class="toggle-info">
                        <span class="toggle-title">Auto Makan</span>
                        <span class="toggle-desc">Membeli makanan paling bernilai saat lapar</span>
                    </div>
                    <label class="switch"><input type="checkbox" id="autoMakan" onchange="toggleAuto('makan', this.checked)"><span class="slider"></span></label>
                </div>
                <div class="toggle-item">
                    <div class="toggle-info">
                        <span class="toggle-title">Auto Kesehatan (BPJS)</span>
                        <span class="toggle-desc">Periksa kesehatan & aktivasi BPJS jika kesehatan turun</span>
                    </div>
                    <label class="switch"><input type="checkbox" id="autoKesehatan" onchange="toggleAuto('kesehatan', this.checked)"><span class="slider"></span></label>
                </div>
                <div class="toggle-item">
                    <div class="toggle-info">
                        <span class="toggle-title">Auto Fisik (Gym)</span>
                        <span class="toggle-desc">Latihan fisik di gym saat stamina mencukupi</span>
                    </div>
                    <label class="switch"><input type="checkbox" id="autoFisik" onchange="toggleAuto('fisik', this.checked)"><span class="slider"></span></label>
                </div>
                <div class="toggle-item">
                    <div class="toggle-info">
                        <span class="toggle-title">Auto Rekreasi</span>
                        <span class="toggle-desc">Piknik atau liburan saat rekreasi rendah</span>
                    </div>
                    <label class="switch"><input type="checkbox" id="autoRekreasi" onchange="toggleAuto('rekreasi', this.checked)"><span class="slider"></span></label>
                </div>
                <div class="toggle-item">
                    <div class="toggle-info">
                        <span class="toggle-title">Auto Kebersihan (Mandi / Laundry)</span>
                        <span class="toggle-desc">Menjaga kebersihan tubuh dan pakaian</span>
                    </div>
                    <label class="switch"><input type="checkbox" id="autoKebersihan" onchange="toggleAuto('kebersihan', this.checked)"><span class="slider"></span></label>
                </div>
                <div class="toggle-item">
                    <div class="toggle-info">
                        <span class="toggle-title">Auto Buang Air (WC)</span>
                        <span class="toggle-desc">Buang air di toilet umum saat kebelet</span>
                    </div>
                    <label class="switch"><input type="checkbox" id="autoWc" onchange="toggleAuto('wc', this.checked)"><span class="slider"></span></label>
                </div>
                <div class="toggle-item">
                    <div class="toggle-info">
                        <span class="toggle-title">Auto Penampilan</span>
                        <span class="toggle-desc">Pangkas rambut dan rapikan penampilan</span>
                    </div>
                    <label class="switch"><input type="checkbox" id="autoPenampilan" onchange="toggleAuto('penampilan', this.checked)"><span class="slider"></span></label>
                </div>
                <div class="toggle-item">
                    <div class="toggle-info">
                        <span class="toggle-title">Auto Kondisi Rumah</span>
                        <span class="toggle-desc">Perbaiki dan rawat kondisi rumah</span>
                    </div>
                    <label class="switch"><input type="checkbox" id="autoRumah" onchange="toggleAuto('rumah', this.checked)"><span class="slider"></span></label>
                </div>
                <div class="toggle-item">
                    <div class="toggle-info">
                        <span class="toggle-title">Auto Kebun (Garden)</span>
                        <span class="toggle-desc">Siram, pupuk, dan panen tanaman kebun secara otomatis</span>
                    </div>
                    <label class="switch"><input type="checkbox" id="autoGarden" onchange="toggleAuto('kebun', this.checked)"><span class="slider"></span></label>
                </div>
            </div>
        </div>

        <!-- TAB 3: AKUN SAYA -->
        <div id="tab-accounts" class="tab-panel">
            <div class="card" style="margin-bottom: 24px;">
                <div class="card-header">
                    <div class="card-title">👥 Daftar Akun Game Saya</div>
                    <button class="btn btn-primary" onclick="openModal('addAccountModal')">+ Tambah Akun</button>
                </div>
                <div style="overflow-x: auto;">
                    <table class="data-table">
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
            <div class="card" style="max-width: 800px; margin: 0 auto;">
                <div class="card-header">
                    <div class="card-title">🔔 Feed Notifikasi Akun</div>
                    <div style="display: flex; gap: 8px;">
                        <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 12px;" onclick="loadNotifications()">Segarkan</button>
                        <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 12px;" onclick="markAllNotificationsRead()">Tandai Semua Dibaca</button>
                    </div>
                </div>
                <div id="notificationsList" style="display: flex; flex-direction: column; gap: 10px; margin-top: 14px;">
                    <div style="text-align: center; color: var(--text-muted); padding: 24px;">Memuat notifikasi...</div>
                </div>
            </div>
        </div>

        <!-- TAB 5: ADMIN PANEL -->
        <div id="tab-admin" class="tab-panel">
            <div class="card" style="margin-bottom: 24px;">
                <div class="card-header">
                    <div class="card-title">⏳ Pengajuan Pendaftaran Tertunda (Pending Approval)</div>
                    <button class="btn btn-secondary" style="padding: 4px 8px; font-size: 11px;" onclick="loadAdminData()">Refresh</button>
                </div>
                <div style="overflow-x: auto;">
                    <table class="data-table">
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
                    <div class="card-title">👥 Manajemen Seluruh Pengguna</div>
                </div>
                <div style="overflow-x: auto;">
                    <table class="data-table">
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
                        <div class="card-title">⚙️ Pengaturan Global & Konfigurasi Sistem</div>
                        <div style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">
                            Kelola semua konfigurasi server, batas akun, otomatisasi, dan integrasi tanpa edit .env
                        </div>
                    </div>
                    <button class="btn btn-primary" onclick="saveAdminSettings()" style="font-weight: 600;">💾 Simpan Pengaturan</button>
                </div>

                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-top: 16px;">
                    <!-- Bagian 1: Otomatisasi & Game Play -->
                    <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid var(--border); border-radius: 10px; padding: 18px;">
                        <h4 style="font-size: 14px; font-weight: 700; color: #f8fafc; margin-bottom: 14px; display: flex; align-items: center; gap: 8px;">
                            <span>🎮</span> Otomatisasi & Kebutuhan
                        </h4>
                        
                        <div style="margin-bottom: 12px;">
                            <label style="font-size: 12px; color: #94a3b8; display: block; margin-bottom: 4px;">Ambang Batas Kebutuhan (% Default)</label>
                            <input type="number" id="setting_threshold" min="10" max="100" style="width: 100%; padding: 8px 10px; background: #0f172a; border: 1px solid var(--border); border-radius: 6px; color: var(--text);">
                            <span style="font-size: 11px; color: var(--text-muted);">Bot memulihkan kebutuhan saat nilai turun di bawah persentase ini.</span>
                        </div>

                        <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <div style="font-size: 13px; font-weight: 600;">Smart Thresholds</div>
                                <div style="font-size: 11px; color: var(--text-muted);">Gunakan batas pintar per kebutuhan</div>
                            </div>
                            <label class="switch"><input type="checkbox" id="setting_smart_thresholds"><span class="slider"></span></label>
                        </div>

                        <div style="margin-bottom: 12px;">
                            <label style="font-size: 12px; color: #94a3b8; display: block; margin-bottom: 4px;">Cadangan Sumber Daya (%)</label>
                            <input type="number" id="setting_resource_reserve_percent" min="0" max="50" style="width: 100%; padding: 8px 10px; background: #0f172a; border: 1px solid var(--border); border-radius: 6px; color: var(--text);">
                        </div>

                        <div style="margin-bottom: 12px;">
                            <label style="font-size: 12px; color: #94a3b8; display: block; margin-bottom: 4px;">Saldo Koin Minimal (Cadangan)</label>
                            <input type="number" step="0.1" id="setting_min_balance" min="0" style="width: 100%; padding: 8px 10px; background: #0f172a; border: 1px solid var(--border); border-radius: 6px; color: var(--text);">
                            <span style="font-size: 11px; color: var(--text-muted);">Koin minimal yang disisihkan sebelum belanja/kuliah.</span>
                        </div>

                        <div style="margin-bottom: 12px;">
                            <label style="font-size: 12px; color: #94a3b8; display: block; margin-bottom: 4px;">Interval Cek Polling Status (Detik)</label>
                            <input type="number" id="setting_idle_poll_seconds" min="3" max="60" style="width: 100%; padding: 8px 10px; background: #0f172a; border: 1px solid var(--border); border-radius: 6px; color: var(--text);">
                        </div>

                        <div style="margin-bottom: 12px;">
                            <label style="font-size: 12px; color: #94a3b8; display: block; margin-bottom: 4px;">Mode Ojol Default</label>
                            <select id="setting_ojol_mode" class="account-select" style="width: 100%;">
                                <option value="otomatis">Otomatis (HTTP Background Bot)</option>
                                <option value="kendara">Kendara (Manual / Ekstensi Chrome)</option>
                            </select>
                        </div>
                    </div>

                    <!-- Bagian 2: Batasan Shift & Kuota Akun -->
                    <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid var(--border); border-radius: 10px; padding: 18px;">
                        <h4 style="font-size: 14px; font-weight: 700; color: #f8fafc; margin-bottom: 14px; display: flex; align-items: center; gap: 8px;">
                            <span>⏱️</span> Batasan Shift & Kuota Akun
                        </h4>

                        <div style="margin-bottom: 12px;">
                            <label style="font-size: 12px; color: #94a3b8; display: block; margin-bottom: 4px;">Maksimal Pengeluaran Koin (Opsional)</label>
                            <input type="number" step="0.1" id="setting_max_spend" placeholder="Kosong = Tanpa batas" style="width: 100%; padding: 8px 10px; background: #0f172a; border: 1px solid var(--border); border-radius: 6px; color: var(--text);">
                        </div>

                        <div style="margin-bottom: 12px;">
                            <label style="font-size: 12px; color: #94a3b8; display: block; margin-bottom: 4px;">Batas Jumlah Order per Shift (Opsional)</label>
                            <input type="number" id="setting_max_jobs" placeholder="Kosong = Tanpa batas" style="width: 100%; padding: 8px 10px; background: #0f172a; border: 1px solid var(--border); border-radius: 6px; color: var(--text);">
                        </div>

                        <div style="margin-bottom: 12px;">
                            <label style="font-size: 12px; color: #94a3b8; display: block; margin-bottom: 4px;">Batas Durasi Shift (Menit, Opsional)</label>
                            <input type="number" id="setting_max_minutes" placeholder="Kosong = Tanpa batas" style="width: 100%; padding: 8px 10px; background: #0f172a; border: 1px solid var(--border); border-radius: 6px; color: var(--text);">
                        </div>

                        <div style="margin-bottom: 12px;">
                            <label style="font-size: 12px; color: #94a3b8; display: block; margin-bottom: 4px;">Maksimal Akun Game per User</label>
                            <input type="number" id="setting_max_accounts_per_user" min="1" max="100" style="width: 100%; padding: 8px 10px; background: #0f172a; border: 1px solid var(--border); border-radius: 6px; color: var(--text);">
                        </div>

                        <div style="margin-bottom: 12px;">
                            <label style="font-size: 12px; color: #94a3b8; display: block; margin-bottom: 4px;">Maksimal Worker Aktif Bersamaan</label>
                            <input type="number" id="setting_max_active_workers" min="1" max="100" style="width: 100%; padding: 8px 10px; background: #0f172a; border: 1px solid var(--border); border-radius: 6px; color: var(--text);">
                        </div>

                        <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <div style="font-size: 13px; font-weight: 600;">Auto-Start Worker</div>
                                <div style="font-size: 11px; color: var(--text-muted);">Otomatis mulai akun saat server startup</div>
                            </div>
                            <label class="switch"><input type="checkbox" id="setting_auto_start"><span class="slider"></span></label>
                        </div>
                    </div>

                    <!-- Bagian 3: Domain, Jaringan & Integrasi -->
                    <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid var(--border); border-radius: 10px; padding: 18px;">
                        <h4 style="font-size: 14px; font-weight: 700; color: #f8fafc; margin-bottom: 14px; display: flex; align-items: center; gap: 8px;">
                            <span>🌐</span> Domain & Integrasi
                        </h4>

                        <div style="margin-bottom: 12px;">
                            <label style="font-size: 12px; color: #94a3b8; display: block; margin-bottom: 4px;">Domain Publik Dashboard (URL)</label>
                            <input type="text" id="setting_login_public_url" placeholder="https://ojol.jnck.pl" style="width: 100%; padding: 8px 10px; background: #0f172a; border: 1px solid var(--border); border-radius: 6px; color: var(--text);">
                            <span style="font-size: 11px; color: var(--text-muted);">Alamat URL publik dashboard untuk akses dan redirect.</span>
                        </div>

                        <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <div style="font-size: 13px; font-weight: 600;">Cloudflare Tunnel Bawaan</div>
                                <div style="font-size: 11px; color: var(--text-muted);">Aktifkan jika tanpa reverse proxy Nginx/Caddy</div>
                            </div>
                            <label class="switch"><input type="checkbox" id="setting_tunnel_enabled"><span class="slider"></span></label>
                        </div>

                        <div style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <div style="font-size: 13px; font-weight: 600;">Integrasi Telegram Bot</div>
                                <div style="font-size: 11px; color: var(--text-muted);">Aktifkan jika ingin bot Telegram tetap hidup</div>
                            </div>
                            <label class="switch"><input type="checkbox" id="setting_telegram_enabled"><span class="slider"></span></label>
                        </div>

                        <div style="margin-bottom: 12px;">
                            <label style="font-size: 12px; color: #94a3b8; display: block; margin-bottom: 4px;">Telegram Bot Token</label>
                            <input type="password" id="setting_telegram_bot_token" placeholder="Token dari @BotFather" style="width: 100%; padding: 8px 10px; background: #0f172a; border: 1px solid var(--border); border-radius: 6px; color: var(--text);">
                        </div>

                        <div style="margin-bottom: 12px;">
                            <label style="font-size: 12px; color: #94a3b8; display: block; margin-bottom: 4px;">Admin Telegram Chat ID</label>
                            <input type="number" id="setting_telegram_chat_id" placeholder="Contoh: 811190245" style="width: 100%; padding: 8px 10px; background: #0f172a; border: 1px solid var(--border); border-radius: 6px; color: var(--text);">
                        </div>
                    </div>
                </div>

                <div style="margin-top: 20px; display: flex; justify-content: flex-end; border-top: 1px solid var(--border); padding-top: 16px;">
                    <button class="btn btn-primary" onclick="saveAdminSettings()" style="padding: 10px 24px; font-size: 14px; font-weight: 700;">💾 Simpan & Terapkan Pengaturan</button>
                </div>
            </div>
        </div>
    </div>

    <!-- MODAL: Import Cookie -->
    <div id="cookieModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>🍪 Import Cookie Sesi Game</h3>
                <button class="close-btn" onclick="closeModal('cookieModal')">&times;</button>
            </div>
            <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 12px; line-height: 1.5;">
                Tempel cookie sesi KampungSebelah (format string cookie atau JSON sesi) di bawah ini:
            </p>
            <textarea id="cookieInput" class="cookie-box" placeholder="vtW1tcmp4qCDI9cxOfOjr... atau JSON cookie"></textarea>
            <div style="display: flex; justify-content: flex-end; gap: 10px;">
                <button class="btn btn-secondary" onclick="closeModal('cookieModal')">Batal</button>
                <button class="btn btn-primary" onclick="submitCookie()">Impor Sekarang</button>
            </div>
        </div>
    </div>

    <!-- MODAL: Tambah Akun -->
    <div id="addAccountModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>➕ Tambah Akun Game Baru</h3>
                <button class="close-btn" onclick="closeModal('addAccountModal')">&times;</button>
            </div>
            <div style="margin-bottom: 16px;">
                <label style="font-size: 13px; color: var(--text-muted); display: block; margin-bottom: 6px;">Nama Akun (Opsional)</label>
                <input type="text" id="newAccountName" placeholder="Contoh: Akun 2 (otomatis mengikuti game)" style="width: 100%; padding: 10px; background: #0f172a; border: 1px solid var(--border); border-radius: 8px; color: var(--text); outline: none;">
            </div>
            <div style="display: flex; justify-content: flex-end; gap: 10px;">
                <button class="btn btn-secondary" onclick="closeModal('addAccountModal')">Batal</button>
                <button class="btn btn-primary" onclick="submitCreateAccount()">Buat Akun</button>
            </div>
        </div>
    </div>

    <!-- MODAL: Panduan Ekstensi Chrome & Mode Kendarai -->
    <div id="extensionModal" class="modal">
        <div class="modal-content" style="max-width: 640px;">
            <div class="modal-header">
                <h3>🧩 Panduan Pasang Ekstensi Chrome (Mode Kendarai)</h3>
                <button class="close-btn" onclick="closeModal('extensionModal')">&times;</button>
            </div>
            <div style="font-size: 13px; color: #cbd5e1; line-height: 1.6; max-height: 65vh; overflow-y: auto; padding-right: 6px;">
                <div style="background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 8px; padding: 12px; margin-bottom: 16px;">
                    <b style="color: #fbbf24;">💡 Mengapa Mode Kendarai via Ekstensi?</b><br>
                    Aturan server game KampungSebelah membatasi Mode Otomatis maksimal <b>14 jam / hari (840 menit)</b>. Setelah kuota habis, order otomatis akan terkunci. Tetapi di <b>Mode Kendarai</b>, game mengizinkan pengemudi narik <b>tanpa batas jam</b> (<code style="background:rgba(0,0,0,0.3); padding:1px 4px; border-radius:4px; color:#38bdf8;">kendara.tanpaBatas: true</code>).
                </div>

                <div style="margin-bottom: 14px; background: rgba(255,255,255,0.03); padding: 12px; border-radius: 8px; border: 1px solid var(--border);">
                    <b style="color: #38bdf8; font-size: 14px;">1️⃣ Langkah 1: Download & Ekstrak File ZIP</b>
                    <p style="margin-top: 4px; color: #94a3b8;">
                        Klik tombol <b>Download Extension (.ZIP)</b> di bawah. Setelah terunduh, klik kanan file <code style="color:#e2e8f0;">kampungsebelah-extension.zip</code> lalu pilih <b>Extract All / Ekstrak di Sini</b> ke folder komputer Anda.
                    </p>
                </div>

                <div style="margin-bottom: 14px; background: rgba(255,255,255,0.03); padding: 12px; border-radius: 8px; border: 1px solid var(--border);">
                    <b style="color: #38bdf8; font-size: 14px;">2️⃣ Langkah 2: Buka Menu Extensions di Browser</b>
                    <p style="margin-top: 4px; color: #94a3b8;">
                        Buka Google Chrome (atau browser berbasis Chromium seperti Brave, Edge, Opera), buka tab baru, lalu ketik pada address bar:<br>
                        <code style="display:inline-block; margin-top:4px; padding:4px 10px; background:#0f172a; border:1px solid var(--border); border-radius:6px; color:#38bdf8; font-weight:bold;">chrome://extensions</code>
                    </p>
                </div>

                <div style="margin-bottom: 14px; background: rgba(255,255,255,0.03); padding: 12px; border-radius: 8px; border: 1px solid var(--border);">
                    <b style="color: #38bdf8; font-size: 14px;">3️⃣ Langkah 3: Aktifkan Developer Mode (Mode Pengembang)</b>
                    <p style="margin-top: 4px; color: #94a3b8;">
                        Di pojok kanan atas halaman ekstensi, aktifkan toggle switch <b>Developer mode</b> (Mode Pengembang).
                    </p>
                </div>

                <div style="margin-bottom: 14px; background: rgba(255,255,255,0.03); padding: 12px; border-radius: 8px; border: 1px solid var(--border);">
                    <b style="color: #38bdf8; font-size: 14px;">4️⃣ Langkah 4: Muat Folder Ekstensi (Load Unpacked)</b>
                    <p style="margin-top: 4px; color: #94a3b8;">
                        Klik tombol <b>Load unpacked</b> (Muat yang belum dibongkar) di pojok kiri atas, lalu arahkan dan pilih folder <code style="color:#e2e8f0;">kampungsebelah-extension</code> hasil ekstrak tadi. Ekstensi langsung terpasang dan aktif!
                    </p>
                </div>

                <div style="margin-bottom: 10px; background: rgba(255,255,255,0.03); padding: 12px; border-radius: 8px; border: 1px solid var(--border);">
                    <b style="color: #38bdf8; font-size: 14px;">5️⃣ Langkah 5: Buka Game & Mulai Narik Mode Kendarai</b>
                    <p style="margin-top: 4px; color: #94a3b8;">
                        Buka website game <a href="https://www.kampungsebelah.com" target="_blank" style="color:#38bdf8; text-decoration:underline;">https://www.kampungsebelah.com</a>. Panel <b>Auto-Ojol Pro</b> akan otomatis muncul di pojok kanan bawah:<br>
                        • Pilih tab <b>[🏍️ Kendarai]</b>.<br>
                        • Centang checkbox <b>[x] Auto-Beli</b> agar bensin, servis motor, dan kuota HP otomatis terisi saat kritis.<br>
                        • Klik <b>▶ MULAI AUTO-OJOL</b>. Ekstensi akan mencari order dengan tarif terbaik, menyetir 3D otomatis, memecahkan captcha cek SVG, dan mencairkan ongkos!
                    </p>
                </div>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 16px; border-top: 1px solid var(--border); padding-top: 12px;">
                <a href="/api/extension/download" class="btn btn-warning" style="background:#f59e0b; color:#0f172a; font-weight:700;">📦 Download Extension (.ZIP)</a>
                <button class="btn btn-secondary" onclick="closeModal('extensionModal')">Tutup</button>
            </div>
        </div>
    </div>

    <script>
        const currentUser = {user_json};
        let dashboardData = null;

        function showTab(tabId) {{
            document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
            const targetBtn = Array.from(document.querySelectorAll('.nav-btn')).find(b => b.getAttribute('onclick') && b.getAttribute('onclick').includes(tabId));
            if (targetBtn) targetBtn.classList.add('active');
            const panel = document.getElementById(tabId);
            if (panel) panel.classList.add('active');

            if (tabId === 'tab-accounts') loadAccounts();
            if (tabId === 'tab-notifications') loadNotifications();
            if (tabId === 'tab-admin') loadAdminData();
        }}

        function openModal(id) {{
            document.getElementById(id).classList.add('open');
        }}

        function closeModal(id) {{
            document.getElementById(id).classList.remove('open');
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
                    const text = (n.text || '').replace(/\\n/g, '<br>');
                    return `
                    <div style="background: ${{bg}}; border: 1px solid ${{border}}; border-radius: 8px; padding: 14px; position: relative;">
                        <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 6px; display: flex; justify-content: space-between;">
                            <span>${{n.time || ''}} ${{n.error_id ? '• ID: ' + n.error_id : ''}}</span>
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

        function startLiveStream() {{
            if (!window.EventSource) return;
            try {{
                const source = new EventSource('/api/dashboard/stream');
                source.onmessage = function(event) {{
                    try {{
                        const data = JSON.parse(event.data);
                        dashboardData = data;
                        renderDashboard(data);
                    }} catch (e) {{}}
                }};
                source.onerror = function() {{
                    source.close();
                    setTimeout(startLiveStream, 5000);
                }};
            }} catch (e) {{}}
        }}

        async function refreshDashboard() {{
            try {{
                const res = await fetch('/api/dashboard');
                if (res.status === 401) {{
                    window.location.href = '/login';
                    return;
                }}
                const data = await res.json();
                dashboardData = data;
                renderDashboard(data);
            }} catch (e) {{
                console.error('Error fetching dashboard:', e);
            }}
        }}

        function renderDashboard(data) {{
            // Toggle Onboarding Card vs Active Dashboard Section
            const hasAccounts = Boolean(data.account || (data.accounts && data.accounts.length > 0));
            const onboardingCard = document.getElementById('onboardingCard');
            const activeDashboard = document.getElementById('activeDashboardSection');
            if (onboardingCard) {{
                onboardingCard.style.display = hasAccounts ? 'none' : 'block';
            }}
            if (activeDashboard) {{
                activeDashboard.style.display = hasAccounts ? 'block' : 'none';
            }}

            // Populate account selector
            const sel = document.getElementById('accountDropdown');
            sel.innerHTML = '';
            if (data.accounts && data.accounts.length) {{
                data.accounts.forEach(acc => {{
                    const opt = document.createElement('option');
                    opt.value = acc.id;
                    opt.textContent = acc.name + (acc.is_selected ? ' (Aktif)' : '');
                    if (acc.is_selected) opt.selected = true;
                    sel.appendChild(opt);
                }});
            }} else {{
                sel.innerHTML = '<option value="">Belum ada akun</option>';
            }}

            // Render All Accounts Summary (Armada)
            const sumAll = data.all_accounts_summary || {{}};
            const totalW = document.getElementById('fleetTotalWallet');
            if (totalW) totalW.innerText = (sumAll.total_wallet || '0') + ' koin';
            const totalInc = document.getElementById('fleetTotalIncome');
            if (totalInc) totalInc.innerText = '+' + (sumAll.total_income || '0') + ' koin';
            const totalTr = document.getElementById('fleetTotalTrips');
            if (totalTr) totalTr.innerText = (sumAll.total_trips || 0) + ' Trip';
            const cntAcc = document.getElementById('fleetCountAccounts');
            if (cntAcc) cntAcc.innerText = (sumAll.total_accounts || 0) + ' Akun';
            const cntWrk = document.getElementById('fleetCountWorkers');
            if (cntWrk) cntWrk.innerText = (sumAll.active_workers || 0) + ' / ' + (sumAll.total_accounts || 0) + ' Berjalan';
            const runBdg = document.getElementById('fleetRunningBadge');
            if (runBdg) runBdg.innerText = '⚡ ' + (sumAll.active_workers || 0) + ' Worker Aktif';
            const totBdg = document.getElementById('fleetTotalAccountsBadge');
            if (totBdg) totBdg.innerText = '👥 ' + (sumAll.total_accounts || 0) + ' Akun';

            // Active Account Banner Name
            const bannerName = document.getElementById('activeAccountBannerName');
            if (bannerName) bannerName.innerText = data.account ? data.account.name : '-';

            // Render Fleet Account Cards Grid
            const gridElem = document.getElementById('fleetAccountsGrid');
            if (gridElem) {{
                gridElem.innerHTML = '';
                if (data.accounts && data.accounts.length) {{
                    data.accounts.forEach(acc => {{
                        const isSel = !!acc.is_selected;
                        const card = document.createElement('div');
                        card.className = 'account-fleet-card' + (isSel ? ' is-active-account' : '');
                        card.onclick = () => switchAccount(acc.id);

                        const statusText = acc.status_text || (acc.is_running ? 'Aktif' : 'Standby');
                        const statusIcon = acc.icon || (acc.is_running ? '🟢' : '⚪');
                        const walletStr = acc.wallet ? (acc.wallet + ' koin') : '-';
                        const tripsStr = (acc.trips !== undefined && acc.trips !== null) ? acc.trips : '0';
                        const incomeStr = acc.today_income ? ('+' + acc.today_income + ' koin') : '-';

                        card.innerHTML = `
                            <div>
                                <div class="afc-header">
                                    <div class="afc-name-wrap">
                                        <span>${{statusIcon}}</span>
                                        <span>${{acc.name}}</span>
                                    </div>
                                    ${{isSel ? '<span class="afc-tag">● Aktif</span>' : '<span style="font-size:11px; color:#38bdf8; text-decoration:underline;">Pilih Akun Ini</span>'}}
                                </div>
                                <div class="afc-status" style="margin-top:6px;">
                                    ${{statusText}}
                                </div>
                            </div>
                            <div class="afc-metrics">
                                <div class="afc-metric-item">
                                    <span class="m-lbl">SALDO</span>
                                    <span class="m-val" style="color:#fbbf24;">${{walletStr}}</span>
                                </div>
                                <div class="afc-metric-item">
                                    <span class="m-lbl">TRIP</span>
                                    <span class="m-val">${{tripsStr}}</span>
                                </div>
                                <div class="afc-metric-item">
                                    <span class="m-lbl">HARI INI</span>
                                    <span class="m-val" style="color:#34d399;">${{incomeStr}}</span>
                                </div>
                            </div>
                        `;
                        gridElem.appendChild(card);
                    }});
                }} else {{
                    gridElem.innerHTML = '<div style="color:var(--text-muted); font-size:13px; grid-column:1/-1;">Belum ada akun yang terdaftar.</div>';
                }}
            }}

            const sum = data.summary || {{}};
            const snap = data.snapshot || {{}};
            document.getElementById('statusIcon').innerText = sum.icon || '⚪';
            document.getElementById('statusTitle').innerText = sum.status_text || 'Berhenti';
            document.getElementById('statusSubtitle').innerText = data.account ? ('Akun: ' + data.account.name) : 'Silakan pilih/tambah akun game';
            document.getElementById('walletVal').innerText = sum.wallet ? (sum.wallet + ' koin') : '-';
            document.getElementById('tripsVal').innerText = (sum.trips !== undefined && sum.trips !== null) ? sum.trips : '-';
            document.getElementById('presenceVal').innerText = sum.online ? '🟢 Online' : '⚪ Offline';

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
                    cdElem.innerText = '🔍 Mencari order...';
                }} else if (currentPhase === 'sleeping') {{
                    cdElem.innerText = '🌙 Karakter tidur';
                }} else if (currentRemainingSeconds === 0) {{
                    cdElem.innerText = 'Tiba / Selesai';
                }} else {{
                    cdElem.innerText = '-';
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
                    (snap && snap.ojol_hours_left !== null && snap.ojol_hours_left <= 0) ||
                    (sum && sum.status_text && (sum.status_text.includes('Batas narik') || sum.status_text.includes('14 jam') || sum.status_text.includes('8 jam')))
                );
                limitCard.style.display = isLimit ? 'block' : 'none';
            }}

            // Meters
            updateMeter('fuel', (sum && sum.fuel !== undefined) ? sum.fuel : (snap ? snap.fuel : null));
            updateMeter('cond', (sum && sum.condition !== undefined) ? sum.condition : (snap ? snap.condition : null));
            updateMeter('data', (sum && sum.data !== undefined) ? sum.data : (snap ? snap.data : null));

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

            // Update active state in control toolbar buttons
            const isWorkerActive = Boolean(sum.active);
            const curPhase = sum.phase || (snap ? snap.phase : '');

            const btnRun = document.getElementById('btnRunOjol');
            const btnStop = document.getElementById('btnStopOjol');
            const btnRunN = document.getElementById('btnRunNeeds');
            const btnStopN = document.getElementById('btnStopNeeds');

            if (btnRun && btnStop) {{
                if (isWorkerActive && (curPhase === 'delivering' || curPhase === 'searching' || curPhase === 'sleeping' || curPhase === 'standby')) {{
                    btnRun.classList.add('active-run');
                    btnStop.classList.remove('active-stop');
                }} else if (!isWorkerActive) {{
                    btnRun.classList.remove('active-run');
                    btnStop.classList.add('active-stop');
                }} else {{
                    btnRun.classList.remove('active-run');
                    btnStop.classList.remove('active-stop');
                }}
            }}

            if (btnRunN && btnStopN) {{
                if (isWorkerActive && curPhase === 'idle') {{
                    btnRunN.classList.add('active-needs');
                    btnStopN.classList.remove('active-stop');
                }} else if (!isWorkerActive) {{
                    btnRunN.classList.remove('active-needs');
                    btnStopN.classList.remove('active-stop');
                }} else {{
                    btnRunN.classList.remove('active-needs');
                    btnStopN.classList.remove('active-stop');
                }}
            }}

            // Logs
            const logBox = document.getElementById('logConsole');
            if (data.logs && data.logs.length) {{
                logBox.innerText = data.logs.join('\\n');
                logBox.scrollTop = logBox.scrollHeight;
            }} else {{
                logBox.innerText = 'Belum ada log aktivitas.';
            }}
        }}

        function updateMeter(id, val) {{
            const txt = document.getElementById(id + 'Text');
            const bar = document.getElementById(id + 'Bar');
            if (!txt || !bar) return;
            if (val === undefined || val === null) {{
                txt.innerText = '-';
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
                container.className = 'toast-container';
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

        let isActionPending = false;

        async function controlAction(cmd) {{
            if (isActionPending) return;
            isActionPending = true;

            const btnMap = {{
                'run': document.getElementById('btnRunOjol'),
                'stop': document.getElementById('btnStopOjol'),
                'run-needs': document.getElementById('btnRunNeeds'),
                'stop-needs': document.getElementById('btnStopNeeds')
            }};

            const targetBtn = btnMap[cmd];
            let origHtml = '';
            if (targetBtn) {{
                origHtml = targetBtn.innerHTML;
                targetBtn.classList.add('btn-loading');
                targetBtn.innerHTML = '<span class="btn-spinner"></span> Sedang memproses...';
            }}

            // Disable all buttons in control-toolbar to prevent spam
            const allActionBtns = document.querySelectorAll('.control-toolbar .btn, .action-bar .btn');
            allActionBtns.forEach(b => {{
                b.disabled = true;
            }});

            try {{
                const res = await fetch('/api/control/' + cmd, {{ method: 'POST' }});
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || data.message || 'Gagal menjalankan aksi');
                const cmdTitles = {{
                    'run': 'Ojol berhasil dijalankan',
                    'stop': 'Ojol berhasil dihentikan',
                    'run-needs': 'Kebutuhan berhasil dijalankan',
                    'stop-needs': 'Kebutuhan berhasil dihentikan'
                }};
                showToast('✅ ' + (cmdTitles[cmd] || 'Aksi berhasil diproses'), 'success');
                await refreshDashboard();
            }} catch (e) {{
                showToast('⚠️ Aksi gagal: ' + e.message, 'error');
            }} finally {{
                if (targetBtn && origHtml) {{
                    targetBtn.classList.remove('btn-loading');
                    targetBtn.innerHTML = origHtml;
                }}
                allActionBtns.forEach(b => {{
                    b.disabled = false;
                }});
                isActionPending = false;
            }}
        }}

        async function manualRefreshDashboard() {{
            const btn = document.getElementById('btnRefreshDash');
            if (btn) {{
                btn.disabled = true;
                btn.innerHTML = '<span class="btn-spinner"></span> Memuat...';
            }}
            try {{
                await refreshDashboard();
                showToast('🔄 Status dashboard diperbarui', 'info');
            }} catch (e) {{
                showToast('⚠️ Gagal refresh: ' + e.message, 'error');
            }} finally {{
                if (btn) {{
                    btn.disabled = false;
                    btn.innerHTML = '🔄 Refresh';
                }}
            }}
        }}

        async function toggleAuto(flag, enabled) {{
            try {{
                const res = await fetch('/api/control/toggle-auto', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ flag, enabled }})
                }});
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || data.message || 'Gagal mengubah pengaturan Auto');
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
                const res = await fetch('/api/control/mode-ojol', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ mode }})
                }});
                if (!res.ok) throw new Error('Gagal mengubah mode ojol');
                showToast('Mode ojol: ' + (isKendara ? 'Kendara (Manual)' : 'Otomatis'), 'info');
                await refreshDashboard();
            }} catch (e) {{
                showToast('⚠️ Gagal: ' + e.message, 'error');
            }}
        }}

        async function setStudySubject(subject) {{
            try {{
                const res = await fetch('/api/control/study-subject', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ subject }})
                }});
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || data.message || 'Gagal mengubah bidang belajar');
                showToast('Bidang belajar: ' + subject.toUpperCase(), 'info');
                await refreshDashboard();
            }} catch (e) {{
                showToast('⚠️ Gagal: ' + e.message, 'error');
                await refreshDashboard();
            }}
        }}

        async function switchAccount(accountId) {{
            if (!accountId) return;
            try {{
                const res = await fetch('/api/accounts/select', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ account_id: accountId }})
                }});
                if (!res.ok) throw new Error('Gagal mengganti akun');
                showToast('✅ Akun aktif dialihkan', 'success');
                await refreshDashboard();
            }} catch (e) {{
                showToast('⚠️ Gagal mengganti akun: ' + e.message, 'error');
            }}
        }}

        async function submitCreateAccount() {{
            const name = document.getElementById('newAccountName').value.trim();
            try {{
                const res = await fetch('/api/accounts/create', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ name: name || undefined }})
                }});
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Gagal membuat akun');
                closeModal('addAccountModal');
                document.getElementById('newAccountName').value = '';
                refreshDashboard();
                loadAccounts();
                alert('Akun baru berhasil dibuat! Buka Import Cookie untuk menghubungkan sesi game.');
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
                const res = await fetch('/api/control/import-cookie', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ name, cookie }})
                }});
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Gagal mengimpor cookie');
                alert(data.message || '✅ Akun berhasil dihubungkan dan cookie terverifikasi!');
                const inp = document.getElementById('onboardingCookieInput');
                if (inp) inp.value = '';
                await refreshDashboard();
                await loadAccounts();
            }} catch (e) {{
                alert('Gagal menghubungkan akun: ' + e.message);
            }} finally {{
                if (btn) btn.disabled = false;
                if (loading) loading.style.display = 'none';
            }}
        }}

        async function submitCookie() {{
            const cookie = document.getElementById('cookieInput').value.trim();
            if (!cookie) return alert('Silakan tempel cookie terlebih dahulu.');
            try {{
                const res = await fetch('/api/control/import-cookie', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ cookie }})
                }});
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Gagal mengimpor cookie');
                closeModal('cookieModal');
                document.getElementById('cookieInput').value = '';
                alert('✅ Cookie berhasil diimpor dan terverifikasi!');
                refreshDashboard();
            }} catch (e) {{
                alert('Import gagal: ' + e.message);
            }}
        }}

        async function loadAccounts() {{
            try {{
                const res = await fetch('/api/accounts');
                const data = await res.json();
                const tbody = document.getElementById('accountsTableBody');
                tbody.innerHTML = '';
                if (!data.accounts || !data.accounts.length) {{
                    tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">Belum ada akun. Klik + Tambah Akun di atas.</td></tr>';
                    return;
                }}
                data.accounts.forEach(acc => {{
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td><strong>${{acc.name}}</strong> ${{acc.is_selected ? '<span style="color: var(--primary); font-size: 11px;">(Aktif)</span>' : ''}}</td>
                        <td>${{acc.has_cookie ? '<span style="color: var(--success);">✅ Terhubung</span>' : '<span style="color: var(--danger);">❌ Belum ada</span>'}}</td>
                        <td>${{acc.is_running ? '<span style="color: var(--success);">🟢 Berjalan</span>' : '<span style="color: var(--text-muted);">⚪ Berhenti</span>'}}</td>
                        <td>${{acc.archived ? '<span style="color: var(--warning);">Diarsipkan</span>' : 'Aktif'}}</td>
                        <td>
                            ${{!acc.is_selected ? `<button class="btn btn-secondary" style="padding: 4px 8px; font-size: 11px;" onclick="switchAccount('${{acc.id}}')">Pilih</button>` : ''}}
                            <button class="btn btn-secondary" style="padding: 4px 8px; font-size: 11px;" onclick="promptRename('${{acc.id}}', '${{acc.name}}')">Ubah Nama</button>
                            <button class="btn btn-secondary" style="padding: 4px 8px; font-size: 11px;" onclick="toggleArchive('${{acc.id}}', ${{!acc.archived}})">${{acc.archived ? 'Pulihkan' : 'Arsipkan'}}</button>
                        </td>
                    `;
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
                            <td>#${{p.id}}</td>
                            <td><strong>${{p.username}}</strong></td>
                            <td>${{p.name || '-'}}</td>
                            <td>${{p.telegram_id || '-'}}</td>
                            <td>${{dt}}</td>
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
                        <td>#${{u.id}}</td>
                        <td><strong>${{u.username}}</strong></td>
                        <td>${{u.name || '-'}}</td>
                        <td>${{u.telegram_id || '-'}}</td>
                        <td><span style="padding: 2px 6px; border-radius: 4px; background: ${{u.role === 'admin' ? 'rgba(59, 130, 246, 0.2)' : 'rgba(255, 255, 255, 0.05)'}}; color: ${{u.role === 'admin' ? 'var(--primary)' : 'inherit'}};">${{u.role}}</span></td>
                        <td><span style="color: ${{u.status === 'approved' ? 'var(--success)' : u.status === 'pending' ? 'var(--warning)' : 'var(--danger)'}};">${{u.status}}</span></td>
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

        // Initial setup
        loadNotifications();
        refreshDashboard();
        startLiveStream();
        setInterval(refreshDashboard, 5000);
    </script>
</body>
</html>
"""
