# Auto Jaga Usaha Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto di background yang menjaga usaha milik akun (contoh 18 usaha), memilih yang paling layak, dengan ritme manusia.

**Architecture:** Satu rencana harian (WIB) disimpan ke file, dijalankan oleh state machine satu langkah per iterasi loop `Controller.run`, sama seperti `run_kerja`. Skor dan rencana adalah fungsi murni di `jaga_planner.py`. Bentuk respons server dipaku oleh fixture dari probe live tahap A, bukan tebakan.

**Tech Stack:** Python 3.12, httpx, pytest (`asyncio_mode = "auto"`), FastAPI router, `dashboard.js`.

**Spec:** `docs/superpowers/specs/2026-11-28-auto-jaga-usaha-design.md`
Bukti API: `docs/http-endpoints.md`, bagian "Bukti Jaga Usaha" dan "Observasi manual pengguna".

## Global Constraints

- Semua request lewat `OjolHttpApi` dengan header browser lengkap. Tanpa `curl` atau `httpx` mentah. (AGENTS.md)
- Menjalankan tes: `.venv/bin/python scripts/test.py <path> -q`. `pytest` langsung ditolak.
- Config server: `detak_detik` 60, `hidup_menit` 3, `maks_menit_per_hari` 240 per usaha per hari WIB, `min_menit_bonus` 60.
- Hanya satu usaha aktif sekaligus. `selesai` dulu, jeda acak, baru `mulai` usaha lain.
- Interval detak = `detakDetik` + acak 0,5 sampai 8 detik, tidak pernah di bawah `detakDetik`, tidak lebih dari 150 detik.
- Jeda 5 sampai 45 detik sebelum `mulai`. Sesi 25 sampai 70 menit. Jeda antar sesi 4 sampai 25 menit. Istirahat 15 sampai 45 menit setelah 150 sampai 180 menit beruntun.
- Target per usaha 60 sampai 75 menit, diacak. Hari malas peluang 10 sampai 15%, anggaran dipotong separuh.
- Default pengaturan: mati. Anggaran 6 jam (preset hemat 4, seimbang 6, agresif 8, maksimal 10). Minimal pelanggan kemarin 20.
- Berhenti bila: `jaga` false dari server, 3 detak gagal beruntun, `428` tak terpecahkan, usaha tutup, karakter tidur, kebutuhan di bawah batas, jam kerja kontrak, selisih menit server vs lokal janggal.
- Kirim `selesai` saat stop, cancel, shutdown.
- Tidak berinteraksi dengan Auto Ojol (spec: bukan tujuan).
- Kode dan komentar mengikuti gaya repo: komentar Indonesia, `ruff` line-length 100.

## Review Focus

1. Semua usaha tidak layak (tanpa pesaing, pelanggan kemarin di bawah batas, tutup). Harapan: tidak ada `mulai`, status "Tidak ada usaha layak", coba lagi besok.
2. Restart di tengah sesi dan server masih `jaga: true`. Harapan: lanjut detak di usaha yang sama, atau `selesai` bila sesi sudah melewati target. Tidak `mulai` ganda.
3. Detak mengembalikan `jaga: false` dengan `alasan`. Harapan: sesi berhenti, tidak ada `mulai` ulang selama 20 menit, alasan tampil di status.
4. Menit server sudah lebih dari target (atau `maksMenit` server lebih kecil dari target) saat sesi dimulai. Harapan: lewati usaha itu, tidak `mulai`.
5. `semua` kosong, field `kas7` tidak ada, atau satu usaha gagal dibaca (HTTP 500) saat menyusun rencana. Harapan: usaha itu dilewati, usaha lain tetap dinilai, tidak crash.
6. Pergantian hari WIB saat sesi berjalan. Harapan: menit lokal dan target dihitung ulang dari server, rencana lama tidak dipakai.

---

### Task 1: Adapter HTTP jaga usaha

**Files:**
- Modify: `app/integrations/kampung/http_api.py` (`request()` allowlist, cabang galat POST; method baru dekat `kantor_action`)
- Modify: `app/modules/worker/ui.py` (passthrough)
- Test: `tests/integration/test_http.py` (ikuti pola `httpx.MockTransport` di file itu)

**Interfaces:**
- Produces di `OjolHttpApi`:
  - `async def businesses_semua(self) -> dict`
  - `async def jaga_status(self, business_id: str) -> dict`
  - `async def jaga_action(self, business_id: str, aksi: Literal["mulai","detak","selesai"]) -> dict`
  - `async def business_report(self, business_id: str) -> dict`
  - `async def shop_info(self, business_id: str) -> dict`
- Produces: `HttpCoreError(category="rejected")` untuk POST jaga yang ditolak server, pesan berisi `error.message` atau `error.code` dari body.
- Produces di `ui.py`: method dengan nama sama, meneruskan ke `self.api`.

- [ ] **Step 1: Tulis tes gagal.** Nama tes dan isi:
  - `test_jaga_paths_are_allowed_with_browser_headers`: `jaga_status`, `jaga_action(..., "detak")`, `businesses_semua`, `business_report` memanggil path `/api/businesses/{uuid}/jaga`, `/api/businesses/semua`, `/api/businesses/{uuid}/report`. Setiap request membawa header `User-Agent` dari `browser_headers`.
  - `test_jaga_action_rejects_unknown_aksi_and_bad_id`: `aksi="hapus"` dan `business_id="../x"` memunculkan `HttpCoreError` dengan `category="blocked"` tanpa request keluar.
  - `test_jaga_post_rejection_keeps_server_reason`: transport membalas 409 `{"error":{"code":"KONTRAK_KERJA","message":"Sedang jam kerja"}}`; harapan `HttpCoreError`, `category == "rejected"`, `"Sedang jam kerja" in str(exc)`.
  - `test_jaga_post_428_still_goes_through_cek_manusia_path`: respons 428 non-CEK_MANUSIA tetap menghasilkan `rejected`.
- [ ] **Step 2: Jalankan, pastikan gagal.** `.venv/bin/python scripts/test.py tests/integration/test_http.py -k jaga -q` → FAIL.
- [ ] **Step 3: Implementasi.** Tambah regex allowlist `r"/api/businesses/[a-f0-9-]{36}/(?:jaga|report)"` dan path `/api/businesses/semua`; izinkan payload hanya untuk regex `.../jaga`. Validasi `aksi` di `jaga_action` sebelum `request`. Di cabang `payload is not None` dan `not response.is_success`, untuk path `.../jaga` angkat `HttpCoreError(..., category="rejected", path=path)` dengan teks galat dari body (ekstrak aman, JSON tidak valid jatuh ke `HTTP{status}`). Cabang lain tidak berubah.
- [ ] **Step 4: Jalankan tes jaga dan seluruh `tests/integration/test_http.py` dan `tests/integration/test_browser_headers.py`.** Semua PASS.
- [ ] **Step 5: Commit.** `git add app/integrations/kampung/http_api.py app/modules/worker/ui.py tests/integration/test_http.py && git commit -m "feat(http): add jaga usaha endpoints with server rejection reason"`

### Task 2: Skrip probe dan probe A (baca saja)

**Files:**
- Create: `scripts/probe_jaga.py`
- Create: `tests/fixtures/jaga/` (salinan hasil probe yang sudah disamarkan: `semua.json`, `shop.json`, `report.json`, `jaga.json`)
- Modify: `docs/http-endpoints.md` (bentuk respons nyata, status "live read-only", tanggal)

**Interfaces:**
- Produces: CLI `python scripts/probe_jaga.py read --dir <runtime_dir akun Yumika> [--limit N]`. Menulis JSON mentah ke `.local/jaga-usaha-2026-11-28/probe-a/` (diabaikan Git).

- [ ] **Step 1: Tulis skrip.** Memakai `OjolHttpApi` dari `app.integrations.kampung.http_api`. Subcommand `read`: `businesses_semua`, lalu per usaha `shop_info`, `business_report`, `jaga_status`, dengan `asyncio.sleep(random.uniform(1.5, 6.0))` antar request. Cetak ringkasan: jumlah usaha, per usaha `jenis`, `status`, pelanggan kemarin, `rivals`, bentuk `kas7`.
- [ ] **Step 2: Minta pengguna konfirmasi dir akun Yumika.** Jalankan `read`. Hanya GET.
- [ ] **Step 3: Pindahkan sampel ke `tests/fixtures/jaga/`** setelah menyamarkan id akun, nama pemain, dan angka kas yang tidak perlu. Satu usaha layak, satu tanpa pesaing, satu tutup.
- [ ] **Step 4: Perbarui `docs/http-endpoints.md`.** Ganti "temuan statis" dengan bentuk nyata: nama field `kas7`, `bahan`, `customersYesterday`, `rivals`. Beri label "live read-only, tanggal".
- [ ] **Step 5: Commit.** `git add scripts/probe_jaga.py tests/fixtures/jaga docs/http-endpoints.md && git commit -m "docs(jaga): record live read-only shapes and fixtures"`

### Task 3: Probe B dan C (mengubah state akun, butuh izin pengguna saat dijalankan)

**Files:**
- Modify: `scripts/probe_jaga.py` (subcommand `session` dan `conflict`)
- Modify: `docs/http-endpoints.md`

**Interfaces:**
- Produces: `session --business <id> --detaks N --confirm` dan `conflict --a <id> --b <id> --confirm`. Tanpa `--confirm` skrip keluar dengan pesan dan tidak mengirim POST.

- [ ] **Step 1: Tulis subcommand.** `session`: `mulai`, N kali `detak` dengan interval `60 + uniform(0.5, 8)` detik, `selesai` di `finally`. Catat `menit` tiap respons dan waktu lokal. `conflict`: `mulai` A, `mulai` B, `jaga_status` A, `selesai` B, `selesai` A di `finally`.
- [ ] **Step 2: Minta izin eksplisit pengguna** untuk B lalu C, dengan usaha yang ditunjuk pengguna. Jalankan B dulu (N=5), lalu C.
- [ ] **Step 3: Catat hasil di `docs/http-endpoints.md`:** `menit` naik +1 per detak atau per waktu nyata, kode HTTP dan pesan galat konflik, apakah usaha pertama otomatis mati, ada atau tidak `428`.
- [ ] **Step 4: Sesuaikan pemeriksaan selisih menit di Task 6** bila hasil berbeda dari asumsi (+1 per detak, naik paling cepat sesuai waktu nyata).
- [ ] **Step 5: Commit.** `git add scripts/probe_jaga.py docs/http-endpoints.md && git commit -m "docs(jaga): record live session and conflict probe results"`

### Task 4: Flag Auto dan pengaturan jaga

**Files:**
- Modify: `app/modules/worker/settings.py` (`AUTO_LABELS["jaga"] = "Auto Jaga Usaha"`; tambahkan `"jaga"` ke himpunan default-mati di `auto_flags`)
- Create: `app/modules/worker/jaga_settings.py`
- Test: `tests/unit/test_jaga_settings.py`

**Interfaces:**
- Produces di `jaga_settings.py`:
  - `JAGA_SETTINGS_FILE = "jaga-settings.json"`
  - `PRESET_JAM = {"hemat": 4.0, "seimbang": 6.0, "agresif": 8.0}`
  - `@dataclass(frozen=True) class BusinessOverride: aktif: bool = True; prioritas: int = 0; target_min: int | None = None; target_max: int | None = None; maks_menit: int | None = None`
  - `@dataclass(frozen=True) class JagaSettings: mode: Literal["terbaik","rotasi","manual"] = "terbaik"; budget_jam: float = 6.0; target_min: int = 60; target_max: int = 75; active_start: str = "06:00"; active_end: str = "23:00"; auto_pindah: bool = True; min_skor: float | None = None; min_pelanggan: int = 20; hari_malas_peluang: float = 0.12; override: dict[str, BusinessOverride] = field(default_factory=dict)`
  - `load_jaga_settings(runtime_dir: Path) -> JagaSettings` (file hilang = default; isi tidak valid = `ValueError("Pengaturan Auto Jaga tidak valid.")`)
  - `save_jaga_settings(runtime_dir: Path, settings: JagaSettings) -> None` (pakai `write_private`)

- [ ] **Step 1: Tulis tes gagal.**
  - `test_jaga_flag_defaults_off`: `auto_flags(tmp_path)["jaga"] is False`.
  - `test_defaults_match_spec`: `JagaSettings()` memiliki `budget_jam == 6.0`, `min_pelanggan == 20`, `target_min == 60`, `target_max == 75`.
  - `test_roundtrip_with_override`.
  - `test_rejects_invalid`: `budget_jam` 0, 10,5, `target_min > target_max`, `target_min < 60` tanpa override, `mode` tak dikenal, jam `"25:00"`, `hari_malas_peluang` di luar 0 sampai 0,3. Semua `ValueError`.
- [ ] **Step 2: Jalankan, gagal.** `.venv/bin/python scripts/test.py tests/unit/test_jaga_settings.py -q`
- [ ] **Step 3: Implementasi.** Validasi di `load` dan `save`. `target_min` global minimal 60 (bonus butuh 60 menit); override boleh lebih rendah.
- [ ] **Step 4: Jalankan tes baru, lalu `tests/integration/test_runtime.py`, `tests/integration/test_control.py`, `tests/unit/test_kerja.py`.** Perbaiki asersi yang menghitung jumlah flag bila ada. PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(jaga): add Auto Jaga flag and settings file"` (add semua file di atas).

### Task 5: Skor dan rencana harian (fungsi murni)

**Files:**
- Create: `app/modules/worker/jaga_planner.py`
- Test: `tests/unit/test_jaga_planner.py` (memakai fixture dari Task 2)

**Interfaces:**
- Consumes: `JagaSettings`, `BusinessOverride` (Task 4); fixture `tests/fixtures/jaga/*.json` (Task 2).
- Produces:
  - `@dataclass(frozen=True) class BusinessStat: id: str; nama: str; jenis: str; buka: bool; bahan_habis: bool; pelanggan_kemarin: int; pesaing: int; kas7_masuk_milli: int | None`
  - `parse_business_stat(semua_item: dict, shop: dict, report: dict) -> BusinessStat | None` (None bila field wajib hilang; petakan nama field dari fixture Task 2)
  - `tambahan_pelanggan(stat: BusinessStat) -> float` = `pelanggan_kemarin * 0.2 * R / (R + 1.2)`, R = `pesaing`
  - `skor(stat: BusinessStat) -> float` = tambahan pelanggan x laba per pelanggan (`kas7_masuk_milli / (7 * pelanggan_kemarin)`); bila `kas7_masuk_milli` None, skor = tambahan pelanggan
  - `layak(stat: BusinessStat, s: JagaSettings) -> bool`: buka, bahan tidak habis, `pesaing >= 1`, `pelanggan_kemarin >= s.min_pelanggan`, skor ≥ `min_skor` bila diset, override `aktif`
  - `@dataclass(frozen=True) class PlanSession: business_id: str; menit: int`
  - `@dataclass(frozen=True) class DailyPlan: date: str; malas: bool; budget_menit: int; sessions: tuple[PlanSession, ...]; targets: dict[str, int]; window: tuple[str, str]`
  - `build_daily_plan(stats: list[BusinessStat], s: JagaSettings, *, date: str, rng: random.Random, last_guarded: dict[str, str]) -> DailyPlan`
  - `detak_delay(detak_detik: int, rng: random.Random) -> float`; `pre_mulai_delay(rng) -> float`; `break_between(rng) -> float`; `long_rest(rng) -> float` (detik)
  - `load_plan(runtime_dir: Path) -> DailyPlan | None`; `save_plan(runtime_dir: Path, plan: DailyPlan) -> None` (file `jaga-plan.json`)

- [ ] **Step 1: Tulis tes gagal.**
  - `test_tambahan_pelanggan_matches_spec_example`: R=3, 26 pelanggan ≈ 3,7; 251 ≈ 36 (toleransi 0,2).
  - `test_layak_rejects_no_rivals_closed_out_of_stock_low_customers_override_off` (satu tes parametrik).
  - `test_plan_respects_budget_and_targets`: dengan seed tetap, jumlah menit sesi ≤ `budget_jam*60`; target tiap usaha di 60..75; tiap sesi 25..70.
  - `test_plan_picks_only_layak_and_prefers_high_score`: 1000 seed, usaha skor tertinggi terpilih lebih sering dari terendah, tapi tidak selalu (peluang pemilihan usaha kedua > 0).
  - `test_plan_lazy_day_halves_budget`: `hari_malas_peluang=1.0`.
  - `test_plan_mode_rotasi_prefers_least_recently_guarded` dan `test_plan_mode_manual_uses_priority_and_only_aktif`.
  - `test_plan_empty_when_no_layak`: `sessions == ()`.
  - `test_plan_splits_some_businesses_into_two_nonadjacent_sessions` (seed yang memicu 15%; dua sesi usaha sama tidak berurutan).
  - `test_detak_delay_bounds`: 10.000 sampel di `[detak+0.5, min(detak+8,150)]`. `pre_mulai_delay` di 5..45. `break_between` di 240..1500. `long_rest` di 900..2700.
  - `test_plan_roundtrip_and_new_day_discards`: `load_plan` mengembalikan plan; `date` beda tetap dimuat apa adanya (pemanggil yang membandingkan tanggal).
  - `test_parse_business_stat_from_fixtures` dan `test_parse_business_stat_missing_fields_returns_none`.
- [ ] **Step 2: Jalankan, gagal.**
- [ ] **Step 3: Implementasi.** Undian berbobot tanpa pengembalian dari `ceil(slot*1.5)` kandidat teratas, bobot = skor (minimal 1e-6). `slot = budget_menit // rata-rata target`. Penalti usaha yang `last_guarded` kemarin: bobot x0,6. Semua acak lewat `rng` yang dioper, tidak memanggil `random` global.
- [ ] **Step 4: Jalankan tes, PASS.** `ruff check app/modules/worker/jaga_planner.py` bersih.
- [ ] **Step 5: Commit.** `git commit -m "feat(jaga): add pure scoring and daily plan builder"`

### Task 6: Runner jaga usaha

**Files:**
- Create: `app/modules/gameplay/jaga_usaha.py`
- Test: `tests/unit/test_jaga_usaha.py`

**Interfaces:**
- Consumes: `OjolHttpApi`/`ui` method Task 1, `jaga_planner` Task 5, `JagaSettings` Task 4, `auto_flags`, `is_work_active_now` (`app/modules/gameplay/kerja.py`), `c.human_pause`, `c.wait`, `c.settings.threshold_for`.
- Produces:
  - `JAGA_STATUS_FILE = "jaga-status.json"`, `JAGA_JOURNAL_FILE = "jaga-journal.jsonl"`
  - `can_run_jaga(c) -> bool`: flag `jaga` aktif, fase `idle`, tanpa trip, `is_work_active_now` false, di dalam jendela aktif WIB.
  - `async def run_jaga(c) -> bool`: satu langkah per panggilan. True berarti loop controller harus `continue`.
  - `async def jaga_shutdown(c) -> None`: kirim `selesai` bila ada sesi aktif, abaikan galat, batas waktu 10 detik.
- Status file memuat: `state`, `date`, `session` (`business_id`, `target_total_menit`, `started_at`, `server_menit_start`, `last_server_menit`, `detak_gagal`, `next_detak_at`), `plan_index`, `businesses` (id, nama, skor, target, menit), `last_message`, `retry_at`.

- [ ] **Step 1: Tulis tes gagal** dengan `FakeUi` seperti `tests/unit/test_kerja.py` (monkeypatch `asyncio.sleep`, `c.wait`, `c.human_pause` sebagai no-op yang mencatat durasi). Nama tes:
  - `test_run_jaga_noop_when_flag_off_or_not_idle_or_work_hours`
  - `test_builds_plan_once_per_wib_day_and_skips_unreadable_business` (satu usaha melempar `HttpCoreError`; rencana tetap jadi)
  - `test_no_layak_business_sends_no_mulai`
  - `test_full_session_mulai_detak_selesai_stops_at_server_menit_target`: urutan panggilan persis `jaga_status`, `mulai`, `detak`xN, `selesai`; berhenti saat `menit` server ≥ target, bukan jam lokal.
  - `test_detak_interval_never_below_detak_detik_and_never_above_150`
  - `test_skips_business_when_server_menit_already_at_target_or_maks`
  - `test_detak_jaga_false_stops_session_and_blocks_restart_20_minutes`
  - `test_three_failed_detaks_send_selesai_and_back_off`
  - `test_428_unresolved_on_mulai_stops_without_retry_loop`
  - `test_restart_adopts_session_when_server_jaga_true_and_clears_when_false`
  - `test_need_below_threshold_or_sleeping_ends_session_with_selesai`
  - `test_menit_mismatch_server_gain_over_local_elapsed_stops` (nilai batas dari hasil Task 3)
  - `test_switch_business_sends_selesai_pause_then_mulai`
  - `test_wib_midnight_discards_old_plan_and_recomputes`
  - `test_jaga_shutdown_sends_selesai_and_swallows_errors`
  - `test_journal_line_written_per_session` (menit server awal/akhir, detik lokal, alasan berhenti, `pelanggan_kemarin`)
- [ ] **Step 2: Jalankan, gagal.**
- [ ] **Step 3: Implementasi `run_jaga`.** State machine dari status file: `Menyusun rencana` (baca `semua`, lalu `shop_info` dan `business_report` per usaha dengan `c.human_pause(1.5, 6.0)`, `build_daily_plan`, `save_plan`), `Menunggu`, `Jaga`, `Istirahat`, `Selesai hari ini`, `Berhenti`, `Gangguan`. Tulis niat sesi ke status file sebelum `mulai` supaya restart bisa mengadopsi. Selama sesi aktif dan detak belum jatuh tempo, `await c.wait(sisa)` lalu return True agar Auto Ojol tidak menyela. Antar sesi return False dan set `c.jaga_retry_at`. Galat `category == "auth"` dilempar ulang.
- [ ] **Step 4: Jalankan `tests/unit/test_jaga_usaha.py` dan `tests/unit/test_kerja.py`.** PASS. `ruff check` bersih.
- [ ] **Step 5: Commit.** `git commit -m "feat(jaga): add Auto Jaga Usaha runner"`

### Task 7: Sambungan ke Controller

**Files:**
- Modify: `app/modules/worker/controller.py` (setelah baris `run_kerja`, sekitar baris 1062; jalur `StopRequested`/cancel di `run`)
- Test: `tests/integration/test_runtime.py` (tambah tes)

**Interfaces:**
- Consumes: `run_jaga`, `jaga_shutdown` (Task 6).

- [ ] **Step 1: Tulis tes gagal.**
  - `test_controller_calls_run_jaga_after_kerja_when_idle`: `ui` palsu, flag `jaga` ON; `run_jaga` dipanggil, `job_action` ojol tidak dipanggil saat `run_jaga` mengembalikan True.
  - `test_stop_requested_sends_jaga_selesai`: file `STOP` ada saat sesi aktif; `jaga_shutdown` dipanggil sekali.
  - `test_flag_off_never_touches_jaga_endpoints`.
- [ ] **Step 2: Jalankan, gagal.**
- [ ] **Step 3: Implementasi.** `if self.observed_state.phase == "idle" and await run_jaga(self): continue` setelah `run_kerja`. Panggil `jaga_shutdown(self)` di jalur henti (`StopRequested`, `CancelledError`, keluar normal) lewat `try/finally` yang sudah ada atau satu yang baru di `run`, tanpa mengubah perilaku fitur lain. Tambah `jaga_retry_at = 0` di `__init__`.
- [ ] **Step 4: Jalankan `tests/integration/test_runtime.py`, `tests/integration/test_control.py`, `tests/unit`.** PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(jaga): wire Auto Jaga into controller loop and shutdown"`

### Task 8: Dashboard

**Files:**
- Modify: `app/modules/worker/schemas.py` (`JagaSettingsChange`), `app/modules/worker/router.py` (`GET`/`POST /api/control/jaga-settings`), `app/web/dashboard_queries.py` (tambah `jaga_status`, `jaga_settings` dekat `kerja_status`, baris ±747), `app/web/static/dashboard.js` (kartu "Auto Jaga Usaha", daftar fitur di ±827), `app/web/templates/dashboard.html`
- Test: `tests/integration/test_web.py`

**Interfaces:**
- Consumes: `load_jaga_settings`, `save_jaga_settings`, `JAGA_STATUS_FILE`.
- Produces: `GET /api/control/jaga-settings` mengembalikan settings dan preset. `POST` menyimpan, menolak nilai tidak valid dengan 400, dan menyentuh `WAKE`. Toggle memakai `/api/control/toggle-auto` dengan `flag: "jaga"` (sudah generik).

- [ ] **Step 1: Tulis tes gagal.** `test_jaga_settings_api_roundtrip_and_rejects_invalid`, `test_toggle_auto_jaga_default_off_then_on`, `test_dashboard_payload_includes_jaga_status`.
- [ ] **Step 2: Jalankan, gagal.** `.venv/bin/python scripts/test.py tests/integration/test_web.py -k jaga -q`
- [ ] **Step 3: Implementasi API dan payload.** Ikuti pola `set_kerja_target_api`.
- [ ] **Step 4: Implementasi kartu di `dashboard.js`.** Isi: toggle, pilihan preset (Hemat, Seimbang, Agresif) plus input jam, mode, status sesi (usaha, menit server / target), rencana hari ini, tabel usaha dengan checkbox aktif, prioritas, target min/max. Ikuti gaya kartu Kerja. Buka halaman di browser lokal dan periksa secara visual satu kali.
- [ ] **Step 5: Jalankan `tests/integration/test_web.py`.** PASS. Commit: `git commit -m "feat(web): add Auto Jaga Usaha card and settings API"`

---

## Self-review

- **Cakupan spec:** pengaturan (Task 4), skor dan rencana (5), alur harian dan humanize (5, 6), pengaman dan jurnal (6, 7), titik sentuh kode (1, 4, 6, 7, 8), verifikasi live bertahap (2, 3). Tidak ada celah.
- **Ketidakcocokan spec yang saya putuskan:** tabel pengaturan menulis jam aktif 06:00 sampai 23:00, sedangkan diskusi awal menulis jam tenang 23:30 sampai 05:30. Rencana memakai tabel spec (`active_start`/`active_end`), digeser acak ±30 menit per hari.
- **Konsistensi tipe:** `BusinessStat`, `PlanSession`, `DailyPlan`, `JagaSettings` dipakai dengan nama sama di Task 5, 6, 8.
- **Batas bukti:** semua tes unit memakai server palsu. Perilaku nyata baru terbukti setelah Task 2 dan 3, dan jaga berjam-jam belum pernah diuji live.
