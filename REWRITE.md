# Repository Rewrite

## Objective

Modernize and incrementally rewrite the `ojol-automation` Python web application into a clean, maintainable, typed, feature-based modular monolith on the `rewrite` branch while preserving business behavior, the web and worker contracts, SQLite/runtime data integrity, and KampungSebelah browser-header rules (`OjolHttpApi.browser_headers(...)`).

## Current Architecture

Observed from repository inventory (`main` @ `e249147`):

- **Runtime & Stack**: Python 3.12 (`pyproject.toml`, `uv.lock`), FastAPI + Uvicorn, `httpx`, `pydantic>=2`, `python-dotenv`, SQLite. Dev tooling: `pytest`, `pytest-asyncio`, `ruff` (no static type checker configured yet).
- **Entry Points**:
  - `ojol.control` (`app` container): FastAPI dashboard/API + cookie import + `MultiAccountService`/`ControlService` + optional `cloudflared` tunnel + optional Telegram poller.
  - `ojol.worker_service` (`worker` container): Unix socket (`worker.sock`) + file command queue (`worker-commands/`) supervising per-account worker subprocesses (`python main.py ... run --live`).
  - `ojol.telegram_login_bot` (`telegram-bot` optional container): Telegram login code generator.
  - `main.py` / `ojol.cli` (`ojol.app`): CLI commands (`run`, `start`, `stop`, `status`, `inspect`, `doctor`, `reconcile`, `history`, `profit`, `dashboard`, `online`, `list-accounts`, `cleanup-scan`).
- **Persistence**:
  - `accounts.sqlite3`: `users`, `accounts`, `settings`, `access_requests`, `web_users`, `web_sessions`, `telegram_link_codes`, `telegram_login_codes`.
  - `viewer-access.sqlite3`: one-time import tickets/sessions/CSRF (`LoginAccess`).
  - `history.sqlite3`: per-account `runs`, `actions`, `events`, `cashflows` (`Journal`).
  - Private runtime JSON files (`http-session.json`, `browser-identity.json`, `game-profile.json`, `status.json`, `game-sync.json`, `online-status.json`, `auto-settings.json`, `maintenance.json`, `notifications/*.json`, `cek-reviews/*.json`, `errors/*.json`).
- **Key Structural Issues**:
  - God modules: `ojol/web_ui.py` (2,905L), `ojol/http_api.py` (2,531L), `ojol/web_api.py` (1,764L), `ojol/control.py` (1,706L), `ojol/management.py` (1,687L), `ojol/controller.py` (961L), `ojol/svg_captcha_solver.py` (837L).
  - Circular dependencies masked by local/deferred imports: `control <-> management`, `control <-> web_api`, `control <-> cli`, `cli <-> session_transfer`, `controller <-> study`, `auto_settings -> study -> auto_settings`, `accounts -> web_auth`.
  - Route handlers in `web_api.py` embedded inside one giant `register_web_routes` closure with inline SQLite queries, synchronous file I/O inside the 2s SSE stream, and worker orchestration inside HTTP handlers.
  - Legacy compatibility shim in `ojol/ui.py` wrapping `OjolHttpApi` in MCP-era `SimpleNamespace(run_async=...)` tools.
  - 90 `except Exception:` blocks across `ojol/` (several silently swallowing exceptions).

## Target Architecture

Feature-based modular monolith inside `ojol/` with the existing container and CLI entry points (`main.py`, `ojol.control`, `ojol.worker_service`, `ojol.telegram_login_bot`, `ojol.cli`).

1. **Core Foundations** (`config`, `models`, `locks`, `storage`, `formatting`): zero dependencies on feature modules.
2. **Accounts & Auth** (`accounts`, `web_auth`, `login_access`, `identity`): SQLite registry, web sessions/users, import tickets, game profile cache.
3. **Journal & Finance** (`journal`, `finance`, `reconciliation`, dashboard/ledger query services).
4. **Game Integration & Domain Logic** (`http_api`, `game_parsers`, `game_wallet`, `planner`, `study`, `garden`, `gym`, `diving`, `cleanup`, `recreation`, `sppg`, `captcha`).
5. **Worker Runtime** (`worker_service`, `app`, `controller`, `maintenance`, `auto_settings`, `session_transfer`).
6. **Control Plane & Notifications** (`control_service`, `management`, `notices`, `notifications`).
7. **Web Transport & UI** (`web/` FastAPI routers, dependencies, and HTML/JS/CSS templates and assets).

## Architectural Decisions

- **Preserve entry points & runtime storage format**: Dockerfiles, compose services, SQLite schemas, and private JSON state layouts stay compatible across rewrite milestones.
- **Zero new runtime dependencies for Web UI**: Extract `web_ui.py` HTML/CSS/JS into static/template files rendered with standard Python (`html.escape`, JSON script embedding) rather than adding `jinja2`.
- **Incremental vertical slices with compatibility shims**: Keep temporary thin re-exports during intermediate milestones so existing callers and tests stay green until all dependents migrate, then remove obsolete shims.
- **WAF header preservation**: `OjolHttpApi.browser_headers(...)` and per-account `browser-identity.json` remain mandatory for every KampungSebelah request.

## Module Inventory

- [x] Repository inventory & roadmap (`REWRITE.md`)
- [x] Core foundations (`locks`, `storage`, `formatting`, `config`, `models`) & cycle removal *(Milestone 1)*
- [x] Accounts & Web Auth decoupling (`accounts`, `web_auth`, `login_access`, `identity`) *(lazy `Accounts.web` + `web/deps.py`)*
- [x] Web transport (`web_api` → `ojol/web/` routers, dependencies, read-only dashboard queries, bank-angka service) *(Milestone 2)*
- [x] Web UI extraction (`web_ui` -> `ojol/web/templates/*.html` + `ojol/ui_assets/{auth.css,dashboard.js}`) *(Milestone 2)*
- [x] Control & Management decoupling (`control`, `management`, tunnel, presence, Telegram) *(Milestone 3: `status_presenter.py`, `telegram_menus.py`, unified `_start_worker`)*
- [x] Game HTTP parsing and wallet history extraction, plus direct HTTP calls from `HttpUI` *(Milestone 4)*
- [x] Captcha matcher and template bank separation (`captcha`, `svg_captcha_solver`) *(Milestone 4)*
- [x] Shared fleet notification discovery and login-code redaction (`notifications`, `telegram_login_bot`) *(Milestone 5)*
- [x] Worker IPC, reconciliation diagnostics, and legacy journal backfill *(Milestone 5)*
- [x] Local full Python suite, Ruff lint and formatting, and dashboard JavaScript syntax
- [x] Repository-wide type checking with `ty`
- [x] Web-only authentication, admin controls, reports, and in-app notifications

## Compatibility Requirements

- Preserve existing web, SSE, and account-scoped cookie-import contracts. Four Telegram sign-in and linking routes were retired.
- Preserve worker CLI subcommands (`main.py` / `ojol.cli`). Daily operations use the dashboard.
- Existing SQLite databases (`accounts.sqlite3`, `viewer-access.sqlite3`, `history.sqlite3`) and runtime JSON files.
- KampungSebelah browser header mimicry (`OjolHttpApi.browser_headers(...)` and `browser-identity.json`).

## Verification

### Baseline (`main` @ `e249147`)
- `uv run ruff check .`: passed (`All checks passed!`).
- `uv run python scripts/test.py --web`: 264 passed in 3.48s.
- `uv run python scripts/test.py --all`: 773 passed, 1 failed in 160.78s (`tests/test_http.py::test_spbu_worker_auto_refills_at_spbu` -> `AttributeError: 'dict' object has no attribute 'effects'` at `tests/test_http.py:738`).

### Milestone 1 (`rewrite` branch)
- Extracted leaf modules `ojol/locks.py`, `ojol/storage.py`, `ojol/formatting.py`; moved `STUDY_LABELS`, `AUTO_SUBJECT`, `SUBJECTS`, and `StopRequested` to `ojol/models.py`; made `Accounts.web` a `@cached_property`; eliminated 5 circular/unnecessary dependency edges (`auto_settings <-> study`, `controller <-> study`, `cli <-> control`, `cli <-> session_transfer`, `web_api -> management`).
- `uv run ruff check .`: passed (`All checks passed!`).
- `uv run ruff format --check` on all 20 Milestone 1 Python files + `tests/test_core_utils.py`: passed (`already formatted`).
- Python module import smoke check across `cli`, `control`, `management`, `worker_service`, `web_api`, `http_api`, `controller`, `study`, `accounts`, `web_auth`, `locks`, `storage`, `formatting`: passed (`IMPORTS_OK`).
- `uv run python scripts/test.py --web`: **264 passed** in 3.30s.
- `uv run python scripts/test.py tests/test_core_utils.py`: **3 passed** in 0.01s.
- `uv run python scripts/test.py tests/test_study.py tests/test_runtime.py tests/test_reconciliation.py tests/test_online_presence.py tests/test_finance.py`: **172 passed** in 113.34s.

### Milestone 2 (`rewrite` branch)
- Decomposed `ojol/web_api.py` (1,764L) and `ojol/control.py` HTTP routes into `ojol/web/` (`app.py`, `deps.py`, `dashboard_queries.py`, `bank_angka_service.py`, `routers/{auth,dashboard,accounts,control,notifications,admin,bank_angka,cookie_import}.py`), breaking the `control <-> web_api` cycle.
- Switched dashboard & SSE profit/expense/study aggregation to read-only SQLite queries (`?mode=ro`) via `asyncio.to_thread`, eliminating repeated `Journal.backfill_cashflows()` writes on every 2s SSE tick.
- Extracted `ojol/web_ui.py` (2,905L -> 150L) into `ojol/web/templates/*.html`, `ojol/ui_assets/auth.css`, and `ojol/ui_assets/dashboard.js` (syntax-verified with `node --check`).
- `uv run ruff check .`: passed (`All checks passed!`).
- `uv run ruff format --check` on `ojol/web`, `ojol/web_api.py`, `ojol/web_ui.py`, `ojol/control.py`, `tests/test_web.py`: passed.
- `uv run python scripts/test.py --web`: **264 passed** in 3.60s.

### Milestone 3 (`rewrite` branch)
- Extracted shared runtime status inspection, snapshot merging, profit formatting, and status reports from `ojol/control.py` into `ojol/status_presenter.py`, eliminating 3 duplicated implementations (`status`, `status_kebutuhan`, `summary`).
- Consolidated `run` and `run_kebutuhan` subprocess/IPC launching in `ojol/control.py` into `_start_worker`.
- Extracted pure Telegram menu/dashboard presentation builders from `ojol/management.py` into `ojol/telegram_menus.py`.
- `uv run ruff check .` and `uv run ruff format --check` on `ojol/status_presenter.py`, `ojol/control.py`, `ojol/telegram_menus.py`, `ojol/management.py`: passed.
- `uv run python scripts/test.py --web`: **264 passed** in 3.63s; targeted control/tunnel/production/house_visits/autostart/online_presence/accounts/web run: **258 passed** in 3.28s.

### Milestone 4 (`rewrite` branch)

- Extracted snapshot and effect parsing into `ojol/game_parsers.py`, wallet pagination into `ojol/game_wallet.py`, and cookie parsing into `ojol/cookies.py`. `OjolHttpApi` still owns request validation and stateful game operations.
- Removed the legacy MCP tool dispatcher from `HttpUI`. The controller keeps typed adapter methods, cancellation while awaiting snapshots and job actions, and a single request ID for each journaled purchase.
- Split the captcha matcher from template and review persistence in `ojol/captcha/`. `ojol.svg_captcha_solver` retains its import path for callers.
- The earlier SPBU failure was already resolved in the starting checkout at `425a277`. The isolated baseline on `rewrite` passed all **777 tests**, including the SPBU refill test. The focused HTTP run after the `HttpUI` change passed **11 tests**.

### Milestone 5 (`rewrite` branch)

- Reused one directory scan for listing and marking fleet notifications. Covered registered, archived, disk-only, control-user, and root scopes. Telegram login codes are excluded from delivery logs.
- Ran the existing journal backfill at web startup so legacy purchases appear in read-only dashboard queries. Added a regression test for a journal that predates `cashflows` and verified repeated startup does not duplicate entries.
- Published worker IPC request and response files atomically and exercised the real file fallback in the suite. Added diagnostics to controller recovery paths and typed reconciliation entry points.
- Compared the routers to `425a277` and confirmed all **53 HTTP method/path pairs** match. An AST scan found no direct two-way imports among top-level `ojol` modules, including deferred imports.
- `.venv/bin/python scripts/test.py --all` with a clean shell environment and verified `.env.testing` passed **778 tests** in 157.47s. Ruff lint and formatting, `git diff --check`, and `node --check ojol/ui_assets/dashboard.js` passed.

### Web-only completion

- Removed the Telegram runtime, bot/web authentication endpoints, settings, and Compose services. Legacy database ownership keys are preserved. An operator can recover web credentials for an existing approved user without changing account ownership.
- Added web maintenance controls, per-user account limits, dated reports, and house scans. Added regression coverage for ownership migration and for revocation of web sessions and account import tickets.
- Split the server entry point from `ControlService`. An AST dependency scan found no cycles across 61 modules. The web route comparison retained 49 method/path pairs, retired four Telegram endpoints, and added five web operations.
- The full suite passed **685 tests** with verified `.env.testing`. `ty` passed for the application, scripts, entry point, and tests. Ruff, dashboard JavaScript syntax, and the Docker test build with 175 isolated tests also passed.
- Browser Harness verified registration, login, game-account creation, live dashboard SSE, and maintenance on/off on a local Uvicorn instance with a standalone worker. The worker responded to IPC ping. The smoke environment used `.env.testing` and an isolated browser profile.

### Main synchronization and feature folders

- Merged `origin/main` at `51717a4`. Kept the split adapter, directory fallback and catalog revalidation, and the automatic-mode order selection from main. The same 54 web-only routes and deployed module commands remain available.
- Moved the implementation into `app/core`, `app/modules`, `app/integrations`, and `app/web`. Grouped the test suite under `tests/unit` and `tests/integration`. Existing SQLite data paths and schema remain in use.
- Added the requested Ruff, pytest and strict mypy settings. Ruff passed for the application and test scope. The CI type checker `ty` passed. The separate strict mypy audit returned 1,234 diagnostics across 54 files.
- The isolated Python suite passed 690 tests, the extension suite passed 62 tests, and the Docker test target passed 176 tests. See [the architecture guide](docs/architecture.md#struktur-kode) for the folder map.

## Known Risks

- `OjolHttpApi` still owns shop, trip, and facility workflows. Fleet supervision and tunnel lifecycle remain in the existing control services. The web routers retain existing form and JSON parsing contracts.
- Verification used isolated runtime data. Game integration against real accounts and production deployment remain outside the verified scope.

## Current Blockers

None.
