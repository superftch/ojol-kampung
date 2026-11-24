"""HTML template renderer for Kampung Ojol Automation web pages."""

import html
import json
from collections.abc import Iterable
from functools import cache
from pathlib import Path
from typing import Any

TEMPLATES_DIR = Path(__file__).resolve().with_name("templates")
BRAND_MARK = (
    '<svg class="brand-mark" viewBox="0 0 32 32" fill="none" aria-hidden="true">'
    '<path d="M4 27h24M7 27l5-22m13 22L20 5m-4 7v4m0 5v3" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round"/><circle cx="16" cy="5" r="2" fill="currentColor"/>'
    "</svg>"
)

_ADMIN_NOTIF_SUBNAV_HTML = """
                <div class="notif-subnav" style="display: flex; gap: 10px; margin-bottom: 18px; border-bottom: 1px solid var(--border); padding-bottom: 12px;">
                    <button id="btnSubNotifUser" class="btn btn-primary" style="font-size: 13px; padding: 6px 14px;" onclick="switchNotifTab('user')">Akun terpilih</button>
                    <button id="btnSubNotifAdmin" class="btn btn-secondary" style="font-size: 13px; padding: 6px 14px;" onclick="switchNotifTab('admin')">Semua akun</button>
                </div>
"""

_ADMIN_NOTIF_PANEL_HTML = """
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
"""


@cache
def _load_template(name: str) -> str:
    return (TEMPLATES_DIR / name).read_text(encoding="utf-8")


def _render_template(name: str, replacements: dict[str, str]) -> str:
    rendered = _load_template(name)
    for key, value in replacements.items():
        rendered = rendered.replace(key, value)
    return rendered


def _alert_html(kind: str, message: str) -> str:
    if not message:
        return ""
    return f'<div class="alert alert-{kind}">{html.escape(message)}</div>'


def login_html(error: str = "", success: str = "") -> str:
    return _render_template(
        "login.html",
        {
            "__BRAND_MARK__": BRAND_MARK,
            "__ERROR_ALERT__": _alert_html("danger", error),
            "__SUCCESS_ALERT__": _alert_html("success", success),
        },
    )


def register_html(error: str = "", success: str = "") -> str:
    return _render_template(
        "register.html",
        {
            "__BRAND_MARK__": BRAND_MARK,
            "__ERROR_ALERT__": _alert_html("danger", error),
            "__SUCCESS_ALERT__": _alert_html("success", success),
        },
    )


def setup_password_html(user: dict[str, Any], error: str = "") -> str:
    return _render_template(
        "setup_password.html",
        {
            "__BRAND_MARK__": BRAND_MARK,
            "__ERROR_ALERT__": _alert_html("danger", error),
            "__CURRENT_USERNAME__": html.escape(str(user.get("username", ""))),
        },
    )


def meters_html(fields: Iterable[tuple[str, str]]) -> str:
    return "".join(
        f'<div class="meter-row">'
        f'<div class="meter-label">'
        f'<span id="{key}Label">{label}</span>'
        f'<span id="{key}Text" class="meter-val">—</span>'
        f"</div>"
        f'<div class="meter-bar" aria-hidden="true">'
        f'<div id="{key}Bar" class="meter-fill" style="width:0"></div>'
        f"</div>"
        f"</div>"
        for key, label in fields
    )


def dashboard_html(user: dict[str, Any]) -> str:
    is_admin = user.get("role") == "admin"
    user_json = json.dumps(user).replace("<", "\\u003c")
    fuel_meters = meters_html((("fuel", "Bensin"), ("cond", "Kondisi mesin"), ("data", "Kuota HP")))
    needs_meters = meters_html(
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
    return _render_template(
        "dashboard.html",
        {
            "__BRAND_MARK__": BRAND_MARK,
            "__USERNAME__": html.escape(str(user.get("username", "User"))),
            "__ADMIN_TAB_DISPLAY__": "block" if is_admin else "none",
            "__FUEL_METERS__": fuel_meters,
            "__NEEDS_METERS__": needs_meters,
            "__ADMIN_NOTIF_SUBNAV__": _ADMIN_NOTIF_SUBNAV_HTML if is_admin else "",
            "__ADMIN_NOTIF_PANEL__": _ADMIN_NOTIF_PANEL_HTML if is_admin else "",
            "__USER_JSON__": user_json,
        },
    )
