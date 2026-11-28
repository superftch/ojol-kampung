// KampungSebelah - Auto-Mancing Pro Content Script (v2.0.0)
// Fitur: Gerakan Natural Manusiawi (Human-like Jitter & Rhythm), Zero-Loss Reel Guard (Anti-Putus & Anti-Lepas), Auto-Loot Profit Optimizer

(function () {
  console.log("[AutoMancing] Content script v2.0.0 loaded - Natural Human Mode & Zero-Loss Engine ready");

  function isMancingPage() {
    return window.location.pathname.startsWith("/mancing");
  }

  // Konfigurasi & State
  const mancingConfig = {
    autoMancing: false,
    modeNatural: true,       // Gerakan natural manusiawi: refleks acak, micro-jitter, jeda observasi
    zeroLossGuard: true,     // Proteksi anti-putus & anti-lepas tali 100%
    autoCelup: true,         // Mode Celup: kail lurus ke bawah untuk ikan besar di laut dalam
    autoSentak: true,
    autoGulung: true,
    autoSimpan: true,
    autoJual: false,
    smartProfit: true,           // Dipertahankan untuk kompatibilitas internal
    lootMode: "jual-semua",      // Jadikan umpan bila tersedia, selain itu Jual Semua
    stopRule: "all-full",        // "all-full" (50/50) | "sell-full" (30/30) | "bait-empty" (sampai umpan habis)
    selectiveRelease: false,     // Selalu OFF (tidak buang/lepas ikan ke laut)
    templateCustom: false,       // True bila pengguna mengubah Settings setelah memilih Template
    settingsCollapsed: false,    // Dipertahankan untuk kompatibilitas backward
    activeTab: "main",           // Tab HUD aktif: "main" | "history" | "settings"
    justGoUmpan: "umpan-cumi",   // Pilihan umpan untuk template Just Go: cacing | udang | cumi | ikan
    justGoCastMode: "celup",     // Pilihan gaya lempar untuk template Just Go: "celup" | "lempar"
    autoJaring: true,            // Otomatis tebar jaring untuk dapat umpan gratis harian
    autoLampu: true,             // Otomatis nyalakan lampu kapal saat malam (18.30 - 04.30) agar ikan lebih ramai
    singleRodProfit: true,       // Selalu ON: pertahankan 1 joran (1 umpan/celup) agar tidak boros umpan 2x-3x
    autoJualTasPenuh: true,      // Jika tas ikan penuh, otomatis jual agar tangkapan tidak sia-sia
    autoJualSampah: true,        // Otomatis buang/jual sampah laut (Sandal jepit, dll)
    autoUmpan: false,            // Opt-in (OFF default): otomatis beli umpan terpilih saat stok 0 (kecuali Ternak selalu Cacing)
    autoUmpanIkan: true,         // Selalu jadikan umpan-ikan (2.3x) bila tombol tersedia, selain itu jual
    autoUpgrade: false,          // Opt-in (OFF default): otomatis beli upgrade joran & pendingin bernilai tinggi
    autoNavigasi: true,          // Otomatis arahkan & kemudikan kapal ke kedalaman paling worth it sesuai umpan & joran
    preferredUmpan: "umpan-cumi", // "umpan-cumi" / "umpan-udang" / "umpan-cacing" / "umpan-ikan"
    strategiUmpan: "",           // Template aktif: "just-go" | "cumi" | "ternak-ikan"
    baseMaxTension: 80,          // % batas atas default saat mode Natural mati (saat Natural ON acak 70-85%)
    baseMinTension: 35,          // % batas bawah default saat mode Natural mati (saat Natural ON acak 29-45%)
    reelMinRange: [29, 45],      // Rentang acak mulai gulung (mode Natural)
    reelMaxRange: [70, 85]       // Rentang acak lepas gulung (mode Natural, tetap dilindungi anti-putus)
  };

  const DAILY_STATS_KEY = "ks_mancing_daily_stats";
  const SETTINGS_KEY = "ks_mancing_settings_v1";
  const VALID_STRATEGIES = new Set(["", "just-go", "cumi", "ternak-ikan"]);
  const VALID_JUSTGO_UMPAN = new Set(["umpan-cacing", "umpan-udang", "umpan-cumi", "umpan-ikan"]);
  const VALID_CAST_MODES = new Set(["celup", "lempar"]);
  const VALID_STOP_RULES = new Set(["all-full", "sell-full", "bait-empty"]);
  const VALID_TABS = new Set(["main", "history", "settings"]);

  const MANCING_TEMPLATES = {
    "just-go": {
      strategiUmpan: "just-go",
      lootMode: "jual-semua",
      autoUmpanIkan: true,
      stopRule: "all-full",
      modeNatural: true,
      zeroLossGuard: true,
      autoCelup: true,
      autoSentak: true,
      autoGulung: true,
      autoSimpan: true,
      autoNavigasi: true,
      autoJualTasPenuh: true,
      autoJualSampah: true,
      autoUmpan: false,
      autoUpgrade: false
    },
    cumi: {
      strategiUmpan: "cumi",
      preferredUmpan: "umpan-cumi",
      lootMode: "jual-semua",
      autoUmpanIkan: true,
      stopRule: "all-full",
      modeNatural: true,
      zeroLossGuard: true,
      autoCelup: true,
      autoSentak: true,
      autoGulung: true,
      autoSimpan: true,
      autoNavigasi: true,
      autoJualTasPenuh: true,
      autoJualSampah: true,
      autoUmpan: false,
      autoUpgrade: false
    },
    "ternak-ikan": {
      strategiUmpan: "ternak-ikan",
      preferredUmpan: "umpan-cacing",
      lootMode: "jual-semua",
      autoUmpanIkan: true,
      stopRule: "all-full",
      modeNatural: true,
      zeroLossGuard: true,
      autoCelup: true,
      autoSentak: true,
      autoGulung: true,
      autoSimpan: true,
      autoNavigasi: true,
      autoJualTasPenuh: true,
      autoJualSampah: true,
      autoUmpan: false,
      autoUpgrade: false
    }
  };

  function getActiveSelectedBait() {
    if (mancingConfig.strategiUmpan === "ternak-ikan") return "umpan-cacing";
    if (mancingConfig.strategiUmpan === "cumi") return "umpan-cumi";
    if (mancingConfig.strategiUmpan === "just-go") {
      return VALID_JUSTGO_UMPAN.has(mancingConfig.justGoUmpan)
        ? mancingConfig.justGoUmpan
        : "umpan-cumi";
    }
    return mancingConfig.preferredUmpan || "umpan-cumi";
  }

  function loadMancingSettings() {
    try {
      const raw = localStorage.getItem(SETTINGS_KEY);
      if (!raw) return;
      const saved = JSON.parse(raw);
      if (!saved || typeof saved !== "object") return;

      if (typeof saved.justGoUmpan === "string" && VALID_JUSTGO_UMPAN.has(saved.justGoUmpan)) {
        mancingConfig.justGoUmpan = saved.justGoUmpan;
      }
      if (typeof saved.justGoCastMode === "string" && VALID_CAST_MODES.has(saved.justGoCastMode)) {
        mancingConfig.justGoCastMode = saved.justGoCastMode;
      }
      if (typeof saved.strategiUmpan === "string" && VALID_STRATEGIES.has(saved.strategiUmpan)) {
        mancingConfig.strategiUmpan = saved.strategiUmpan;
        if (saved.strategiUmpan === "ternak-ikan") {
          mancingConfig.preferredUmpan = "umpan-cacing";
        } else if (saved.strategiUmpan === "cumi") {
          mancingConfig.preferredUmpan = "umpan-cumi";
        } else if (saved.strategiUmpan === "just-go") {
          mancingConfig.preferredUmpan = mancingConfig.justGoUmpan;
        }
      }
      // Selalu prioritaskan jadikan umpan bila opsi tersedia, selain itu Jual Semua + Zero-Loss aktif permanen
      mancingConfig.autoUmpanIkan = true;
      mancingConfig.lootMode = "jual-semua";
      mancingConfig.zeroLossGuard = true;
      mancingConfig.selectiveRelease = false;
      if (typeof saved.stopRule === "string" && VALID_STOP_RULES.has(saved.stopRule)) {
        mancingConfig.stopRule = saved.stopRule;
      }
      if (typeof saved.activeTab === "string" && VALID_TABS.has(saved.activeTab)) {
        mancingConfig.activeTab = saved.activeTab;
      }

      const boolKeys = [
        "modeNatural", "autoCelup", "autoSentak", "autoGulung",
        "autoSimpan", "autoJualTasPenuh", "autoJualSampah",
        "autoJaring", "autoLampu", "autoNavigasi", "autoUmpan", "autoUpgrade",
        "templateCustom", "settingsCollapsed"
      ];
      for (const key of boolKeys) {
        if (typeof saved[key] === "boolean") mancingConfig[key] = saved[key];
      }
    } catch (_) {}
  }

  function saveMancingSettings() {
    try {
      localStorage.setItem(SETTINGS_KEY, JSON.stringify({
        strategiUmpan: mancingConfig.strategiUmpan,
        justGoUmpan: mancingConfig.justGoUmpan,
        justGoCastMode: mancingConfig.justGoCastMode,
        lootMode: "jual-semua",
        stopRule: mancingConfig.stopRule,
        templateCustom: mancingConfig.templateCustom,
        settingsCollapsed: mancingConfig.settingsCollapsed,
        activeTab: mancingConfig.activeTab,
        modeNatural: mancingConfig.modeNatural,
        zeroLossGuard: true,
        autoCelup: mancingConfig.autoCelup,
        autoSentak: mancingConfig.autoSentak,
        autoGulung: mancingConfig.autoGulung,
        autoSimpan: mancingConfig.autoSimpan,
        autoJualTasPenuh: mancingConfig.autoJualTasPenuh,
        autoJualSampah: mancingConfig.autoJualSampah,
        autoJaring: mancingConfig.autoJaring,
        autoLampu: mancingConfig.autoLampu,
        autoNavigasi: mancingConfig.autoNavigasi,
        autoUmpan: mancingConfig.autoUmpan,
        autoUpgrade: mancingConfig.autoUpgrade
      }));
    } catch (_) {}
  }

  loadMancingSettings();

  function getTodayWibKey() {
    const wib = new Date(Date.now() + 7 * 3600 * 1000);
    return wib.toISOString().slice(0, 10);
  }

  const mancingStats = {
    catches: 0,
    released: 0,
    losses: 0,
    totalLoss: 0,
    jaringUsed: 0,
    totalProfit: 0,
    lastFish: null,
    history: [],
    umpanDibeli: 0,
    upgradeTerpasang: []
  };

  function roundCoin(v) {
    return Math.round((Number(v) || 0) * 100) / 100;
  }

  function escapeHtml(str) {
    return String(str ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function loadDailyMancingStats() {
    try {
      const raw = localStorage.getItem(DAILY_STATS_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw);
      if (parsed && parsed.date === getTodayWibKey()) {
        if (typeof parsed.catches === "number") mancingStats.catches = parsed.catches;
        if (typeof parsed.losses === "number") mancingStats.losses = parsed.losses;
        if (typeof parsed.totalLoss === "number") mancingStats.totalLoss = roundCoin(parsed.totalLoss);
        if (typeof parsed.totalProfit === "number") mancingStats.totalProfit = roundCoin(parsed.totalProfit);
        if (typeof parsed.lastFish === "string") mancingStats.lastFish = parsed.lastFish;
        if (Array.isArray(parsed.history)) {
          mancingStats.history = parsed.history;
        } else if (typeof parsed.lastFish === "string" && parsed.lastFish) {
          mancingStats.history = [{ text: parsed.lastFish }];
        }
      }
    } catch (_) {}
  }

  function saveDailyMancingStats() {
    try {
      localStorage.setItem(DAILY_STATS_KEY, JSON.stringify({
        date: getTodayWibKey(),
        catches: mancingStats.catches,
        losses: mancingStats.losses,
        totalLoss: roundCoin(mancingStats.totalLoss),
        totalProfit: roundCoin(mancingStats.totalProfit),
        lastFish: mancingStats.lastFish,
        history: mancingStats.history
      }));
    } catch (_) {}
  }

  loadDailyMancingStats();

  let isGulungActive = false;
  let reelCoolingDown = false;
  let reelTargetMax = mancingConfig.baseMaxTension;
  let reelTargetMin = mancingConfig.baseMinTension;
  let redDangerSince = 0;
  let isNavigating = false;
  let navStartTime = 0;
  let lastCelupTime = 0;
  let lastLootClosedTime = 0;
  let postLootCooldownMs = 0;
  let castButtonDisabledSince = 0;
  let lastCastRecoveryAttempt = 0;
  let lastCatchId = null;
  let strikePending = false;
  let castPending = false;
  let lootPending = false;
  let autoUmpanPending = false;
  let autoUpgradePending = false;
  let lastUpgradeCheckTime = 0;
  let lastJaringTime = 0;
  let lastLampuCheckTime = 0;
  let lastKailCheckTime = 0;
  const upgradeFailedMap = {};

  // Helper: Bilangan acak natural dalam rentang [min, max]
  function humanJitter(min, max) {
    return Math.floor(min + Math.random() * (max - min + 1));
  }

  // Helper: Jeda aksi per langkah dengan human jitter alami (tanpa delay kaku 1 detik, refleks manusia 140ms - 280ms)
  function getActionDelay(baseMs = 0) {
    if (mancingConfig.modeNatural) {
      return baseMs + humanJitter(140, 280);
    }
    return baseMs || 30;
  }

  // Helper: Klik natural manusia dengan koordinat pointer acak di dalam tombol
  function naturalClick(element, callback) {
    if (!element || element.disabled) {
      if (typeof callback === "function") callback(false);
      return;
    }

    const rect = element.getBoundingClientRect();
    const padX = Math.max(3, rect.width * 0.15);
    const padY = Math.max(3, rect.height * 0.15);
    const clientX = rect.left + padX + Math.random() * (rect.width - 2 * padX);
    const clientY = rect.top + padY + Math.random() * (rect.height - 2 * padY);

    const eventInit = {
      bubbles: true,
      cancelable: true,
      view: window,
      clientX: Math.round(clientX),
      clientY: Math.round(clientY),
      pointerType: "mouse"
    };

    element.dispatchEvent(new PointerEvent("pointerover", eventInit));
    element.dispatchEvent(new PointerEvent("pointerenter", eventInit));
    element.dispatchEvent(new PointerEvent("pointerdown", { ...eventInit, buttons: 1, pressure: 0.5 }));

    // Jeda tekan tombol manusiawi (65ms - 135ms)
    setTimeout(() => {
      element.dispatchEvent(new PointerEvent("pointerup", { ...eventInit, buttons: 0, pressure: 0 }));
      element.dispatchEvent(new MouseEvent("click", eventInit));
      if (typeof callback === "function") callback(true);
    }, humanJitter(65, 135));
  }

  function holdGulung() {
    const btn = document.querySelector('[data-testid="pancing-gulung"]');
    const isHolding = !!(btn && btn.hasAttribute("data-tahan"));
    if (isHolding && isGulungActive) return;
    isGulungActive = true;
    // Gunakan keyboard Space langsung di window (native handler game: "Space" === t.code && "tarik" === R.current).
    // Hindari synthetic PointerEvent pada pancing-gulung karena onPointerDown memanggil setPointerCapture()
    // di MAIN world yang melempar NotFoundError sebelum a5.current = true.
    window.dispatchEvent(new KeyboardEvent("keydown", { code: "Space", key: " ", bubbles: true }));
  }

  function releaseGulung() {
    const btn = document.querySelector('[data-testid="pancing-gulung"]');
    const isHoldingDom = !!(btn && btn.hasAttribute("data-tahan"));
    if (!isGulungActive && !isHoldingDom) return;
    isGulungActive = false;
    window.dispatchEvent(new KeyboardEvent("keyup", { code: "Space", key: " ", bubbles: true }));
  }

  function rollReelMax() {
    if (!mancingConfig.modeNatural) return mancingConfig.baseMaxTension;
    const [lo, hi] = mancingConfig.reelMaxRange || [70, 85];
    return humanJitter(lo, hi);
  }

  function rollReelMin() {
    if (!mancingConfig.modeNatural) return mancingConfig.baseMinTension;
    const [lo, hi] = mancingConfig.reelMinRange || [29, 45];
    return humanJitter(lo, hi);
  }

  function resetReelCycle() {
    reelCoolingDown = false;
    redDangerSince = 0;
    reelTargetMax = rollReelMax();
    reelTargetMin = rollReelMin();
  }

  function getSentakRemainingSec(btnSentak) {
    if (!btnSentak) return null;
    const m = (btnSentak.textContent || "").match(/([\d.,]+)\s*dtk/i);
    if (!m) return null;
    const val = parseFloat(m[1].replace(",", "."));
    return Number.isFinite(val) ? val : null;
  }

  // Sentak Sambaran Alami: refleks manusia 220ms - 380ms (segera tanpa delay bila sisa waktu <= 3 detik).
  // JANGAN kirim keyup Space setelah sentak karena fase langsung pindah ke "tarik" dan keyup Space
  // akan membatalkan gulungan (a5.current = false). Gunakan klik tombol atau fallback Enter.
  function scheduleNaturalSentak() {
    if (strikePending) return;
    strikePending = true;

    const initialBtn = document.querySelector('[data-testid="pancing-sentak"]');
    const remSec = getSentakRemainingSec(initialBtn);
    const urgent = remSec !== null && remSec <= 3.0;
    const delay = urgent ? 0 : (mancingConfig.modeNatural ? humanJitter(220, 380) : 40);

    const doStrike = () => {
      const btnSentak = document.querySelector('[data-testid="pancing-sentak"]');
      if (btnSentak && !btnSentak.disabled) {
        naturalClick(btnSentak, () => {
          strikePending = false;
        });
      } else {
        window.dispatchEvent(new KeyboardEvent("keydown", { code: "Enter", key: "Enter", bubbles: true }));
        setTimeout(() => {
          window.dispatchEvent(new KeyboardEvent("keyup", { code: "Enter", key: "Enter", bubbles: true }));
          strikePending = false;
        }, mancingConfig.modeNatural ? humanJitter(50, 90) : 30);
      }
    };

    if (delay <= 0) {
      doStrike();
    } else {
      setTimeout(doStrike, delay);
    }
  }

  // Cari tombol Celup (prioritas testid resmi, fallback pencocokan teks tombol di area pancing)
  function findCelupButton() {
    const byTestId = document.querySelector('[data-testid="pancing-celup"]');
    if (byTestId) return byTestId;

    const scope = document.querySelector('[data-testid="pancing"]') || document;
    const buttons = Array.from(scope.querySelectorAll("button"));
    return buttons.find((b) => {
      if (b.closest("#ks-mancing-hud")) return false;
      const txt = (b.textContent || "").trim();
      return /\bcelup\b/i.test(txt);
    }) || null;
  }

  function findLemparButton() {
    const byTestId = document.querySelector('[data-testid="pancing-lempar"]');
    if (byTestId) return byTestId;

    const scope = document.querySelector('[data-testid="pancing"]') || document;
    const buttons = Array.from(scope.querySelectorAll("button"));
    return buttons.find((b) => {
      if (b.closest("#ks-mancing-hud")) return false;
      const txt = (b.textContent || "").trim();
      return /\blempar\b/i.test(txt);
    }) || null;
  }

  function isCelupButtonReady(btn) {
    return !!(btn && !btn.disabled && !btn.getAttribute("aria-busy"));
  }

  // Celup / Lempar Kail Alami (jeda 2.2s - 3.8s + jeda aman pasca-tutup kartu ikan)
  function scheduleNaturalCelup(useLempar = false) {
    if (castPending) return;
    const now = performance.now();
    const cooldown = mancingConfig.modeNatural ? humanJitter(2200, 3800) : 1200;
    if (now - lastCelupTime < cooldown) return;
    if (lastLootClosedTime > 0 && now - lastLootClosedTime < postLootCooldownMs) return;
    if (liveShipData.hasIkanAnim && lastLootClosedTime > 0 && now - lastLootClosedTime < 3000) return;

    const btnCast = useLempar ? findLemparButton() : findCelupButton();
    if (!isCelupButtonReady(btnCast)) return;

    castPending = true;
    lastCelupTime = now;

    setTimeout(() => {
      const btn = useLempar ? findLemparButton() : findCelupButton();
      if (isCelupButtonReady(btn)) {
        lastCelupTime = performance.now();
        naturalClick(btn, () => {
          setTimeout(() => {
            castPending = false;
          }, 800);
        });
      } else {
        castPending = false;
      }
    }, mancingConfig.modeNatural ? humanJitter(160, 360) : 30);
  }

  function normalizeUmpanType(raw) {
    const s = String(raw || "").toLowerCase().trim();
    if (!s) return "";
    if (s.includes("ikan")) return "umpan-ikan";
    if (s.includes("cacing")) return "umpan-cacing";
    if (s.includes("udang")) return "umpan-udang";
    if (s.includes("cumi")) return "umpan-cumi";
    return "";
  }

  function getEquippedUmpanType() {
    const btnUmpan = document.querySelector('[data-testid="pancing-umpan"]');
    const label = [
      btnUmpan?.textContent || "",
      btnUmpan?.getAttribute("aria-label") || "",
      btnUmpan?.getAttribute("title") || ""
    ].join(" ");
    const normalized = normalizeUmpanType(label);
    if (normalized) return normalized;
    return mancingConfig.preferredUmpan;
  }

  function getUmpanCostByType(active) {
    const norm = normalizeUmpanType(active);
    if (norm === "umpan-ikan") return 0.00;
    if (norm === "umpan-cumi") return 0.50;
    if (norm === "umpan-udang") return 0.30;
    if (norm === "umpan-cacing") return 0.20;
    return 0.50;
  }

  function getUmpanShortName(active) {
    const norm = normalizeUmpanType(active);
    if (norm === "umpan-ikan") return "Ikan";
    if (norm === "umpan-cumi") return "Cumi";
    if (norm === "umpan-udang") return "Udang";
    if (norm === "umpan-cacing") return "Cacing";
    return "Umpan";
  }

  function getActiveUmpanCost() {
    return getUmpanCostByType(getEquippedUmpanType());
  }

  function getOwnedBaitStock(baitId) {
    if (getEquippedUmpanType() === baitId) {
      const domStok = getUmpanStok();
      if (domStok >= 0) return domStok;
    }
    return pancingProfile.umpanList?.find(u => u.id === baitId)?.stok ?? 0;
  }

  function getTernakBatchTarget() {
    if (!pancingProfile.loaded) return 5;
    const sisaJual = Math.max(0, pancingProfile.jualMaks - pancingProfile.jualHariIni);
    const sisaTas = Math.max(0, pancingProfile.tasMaks - pancingProfile.tasIkan);
    const sisaTarget = mancingConfig.stopRule === "sell-full"
      ? Math.max(1, sisaJual)
      : Math.max(1, sisaJual + sisaTas);
    return Math.min(5, sisaTarget);
  }

  let activeCastState = null;
  let lastApiCastBait = null;
  let lastRecordedLossKey = null;
  let lastRecordedLossTime = 0;
  let wasHiddenDuringCast = false;

  document.addEventListener("visibilitychange", () => {
    if (document.hidden && activeCastState && !activeCastState.closed) {
      wasHiddenDuringCast = true;
    }
  });

  function readGameNoticeText() {
    const scope = document.querySelector('[data-testid="pancing"]');
    if (!scope) return "";
    const text = (scope.textContent || "").toLowerCase();
    if (text.includes("talinya putus")) return "putus";
    if (text.includes("terlalu kendur")) return "kendur";
    if (text.includes("terlambat menyentak")) return "telat_sentak";
    if (text.includes("ikannya sudah lepas")) return "lepas_cek";
    if (text.includes("lepas di saat terakhir")) return "lepas_server";
    if (text.includes("umpan habis dimakan")) return "dimakan";
    return "";
  }

  function recordBaitLoss({ id = "", reason = "dimakan", message = "", umpan = "", source = "", berhasil = undefined } = {}) {
    const now = performance.now();
    const dedupKey = id ? `${id}:${reason}` : `${reason}:${Math.floor(now / 2500)}`;
    if (dedupKey === lastRecordedLossKey || (now - lastRecordedLossTime < 2200)) {
      return;
    }
    lastRecordedLossKey = dedupKey;
    lastRecordedLossTime = now;

    if (activeCastState) {
      activeCastState.lossRecorded = true;
    }

    const baitType = normalizeUmpanType(umpan) || activeCastState?.baitType || getEquippedUmpanType();
    const baitCost = getUmpanCostByType(baitType);
    const baitLabel = getUmpanShortName(baitType);
    const noticeHint = readGameNoticeText();
    const reasonKey = String(reason || "dimakan").toLowerCase();
    const hiddenHint = wasHiddenDuringCast || document.hidden;

    let name = "Umpan Dimakan";
    let action = "Dimakan";
    if (reasonKey.includes("putus") || noticeHint === "putus") {
      name = "Tali Putus";
      action = "Putus";
    } else if (noticeHint === "kendur" || reasonKey.includes("kendur")) {
      name = "Ikan Lepas (Kendur)";
      action = "Lepas";
    } else if (noticeHint === "telat_sentak" || reasonKey.includes("telat")) {
      name = hiddenHint ? "Ikan Lepas (Tab Tidur)" : "Ikan Lepas (Telat Sentak)";
      action = "Lepas";
    } else if (noticeHint === "lepas_cek" || reasonKey === "lepas_cek" || (source === "cek" && reasonKey !== "dimakan" && reasonKey !== "kosong")) {
      name = hiddenHint ? "Ikan Lepas (Tab Tidur)" : "Ikan Lepas (Cek Telat)";
      action = "Lepas";
    } else if (noticeHint === "lepas_server" || (source === "tarik" && berhasil === true)) {
      name = "Ikan Lepas (Server)";
      action = "Lepas";
    } else if (reasonKey.includes("lepas") || reasonKey.includes("gagal")) {
      name = hiddenHint ? "Ikan Lepas (Tab Tidur)" : "Ikan Lepas";
      action = "Lepas";
    } else if (reasonKey.includes("batal")) {
      name = "Tarik Kail";
      action = "Batal";
    } else if (message && typeof message === "string" && message.length <= 28) {
      name = message;
    }

    wasHiddenDuringCast = false;

    const lossProfit = -baitCost;
    mancingStats.losses++;
    mancingStats.totalLoss = roundCoin(mancingStats.totalLoss + baitCost);
    mancingStats.totalProfit = roundCoin(mancingStats.totalProfit + lossProfit);
    mancingStats.lastFish = `${name} (${baitLabel}) ➔ Profit: ${lossProfit.toFixed(2)} koin`;
    mancingStats.history.unshift({
      name,
      weight: baitLabel,
      sellPrice: 0,
      profit: lossProfit,
      action,
      isLoss: true
    });
    saveDailyMancingStats();
    updateMancingUI();
  }

  window.addEventListener("ks_mancing_cast_started", (e) => {
    if (!isMancingPage()) return;
    const norm = normalizeUmpanType(e.detail?.umpan);
    if (!norm) return;
    // Simpan jenis umpan lemparan terbaru tanpa membuka activeCastState sebelum DOM masuk fase tunggu/sambar/tarik
    // (mencegah false positive "Umpan Dimakan" bila tick 40ms berjalan sebelum React mengubah data-fase)
    lastApiCastBait = { baitType: norm, at: performance.now() };
    if (activeCastState && !activeCastState.closed) {
      activeCastState.baitType = norm;
    }
  });

  window.addEventListener("ks_mancing_bait_lost", (e) => {
    if (!isMancingPage()) return;
    recordBaitLoss(e.detail || {});
  });

  function calcFishPrice(hasilCard, fishName, fishClass, fishWeight) {
    if (hasilCard) {
      const text = hasilCard.textContent || "";
      const m = text.match(/Dijual:\s*([\d,\.]+)\s*koin/i);
      if (m) {
        const p = parseFloat(m[1].replace(",", "."));
        if (!isNaN(p) && p > 0) return p;
      }
      const btnJual = hasilCard.querySelector('[data-testid="pancing-jual"]');
      if (btnJual) {
        const jm = (btnJual.textContent || "").match(/\+\s*([\d,\.]+)/);
        if (jm) {
          const p = parseFloat(jm[1].replace(",", "."));
          if (!isNaN(p) && p > 0) return p;
        }
      }
    }

    let gram = 0;
    if (fishWeight) {
      const gMatch = fishWeight.match(/([\d,\.]+)\s*g/i);
      const kgMatch = fishWeight.match(/([\d,\.]+)\s*kg/i);
      if (gMatch) gram = parseFloat(gMatch[1].replace(",", "."));
      else if (kgMatch) gram = parseFloat(kgMatch[1].replace(",", ".")) * 1000;
    }

    const nameLower = (fishName || "").toLowerCase();
    const classLower = (fishClass || "").toLowerCase();

    if (nameLower.includes("sandal") || classLower.includes("sampah")) return 0;

    // Ikan laut lepas spesifik
    if (nameLower.includes("tuna")) {
      const t = Math.min(1, Math.max(0, (gram - 15000) / 45000));
      return (2400 + t * 1600) / 1000;
    }
    if (nameLower.includes("layaran")) {
      const t = Math.min(1, Math.max(0, (gram - 20000) / 35000));
      return (2700 + t * 1800) / 1000;
    }
    if (nameLower.includes("marlin")) {
      const t = Math.min(1, Math.max(0, (gram - 40000) / 80000));
      return (3400 + t * 2200) / 1000;
    }

    // Standar per kelas (+15% max scaling menurut berat di kelasnya)
    let baseMilli = 400; // kecil
    let minGram = 100, maxGram = 300;

    if (classLower.includes("raksasa") || nameLower.includes("barakuda") || nameLower.includes("kuwe")) {
      baseMilli = 2500;
      minGram = 5000;
      maxGram = 32000;
    } else if (classLower.includes("besar") || nameLower.includes("kerapu") || nameLower.includes("tongkol") || nameLower.includes("tenggiri") || nameLower.includes("cakalang") || nameLower.includes("lemadang")) {
      baseMilli = 1400;
      minGram = 1200;
      maxGram = 9000;
    } else if (classLower.includes("sedang") || nameLower.includes("kakap") || nameLower.includes("baronang") || nameLower.includes("bawal")) {
      baseMilli = 800;
      minGram = 300;
      maxGram = 2200;
    }

    let bonusRatio = 0;
    if (gram > minGram && maxGram > minGram) {
      const progress = Math.min(1, Math.max(0, (gram - minGram) / (maxGram - minGram)));
      bonusRatio = progress * 0.15;
    }
    return Math.round(baseMilli * (1 + bonusRatio)) / 1000;
  }

  function findCatchButton(hasilCard, testIds, textRegex) {
    const roots = hasilCard ? [hasilCard, document] : [document];
    for (const root of roots) {
      for (const sel of testIds) {
        const el = root.querySelector(sel);
        if (el && !el.closest("#ks-mancing-hud")) return el;
      }
    }
    for (const root of roots) {
      const buttons = Array.from(root.querySelectorAll("button"));
      const match = buttons.find((b) => {
        if (b.closest("#ks-mancing-hud")) return false;
        return textRegex.test((b.textContent || "").trim());
      });
      if (match) return match;
    }
    return null;
  }

  function isTrashCatch(hasilCard, fishName, fishClass) {
    const nameLower = (fishName || "").toLowerCase();
    const classLower = (fishClass || "").toLowerCase();
    const cardText = (hasilCard?.textContent || "").toLowerCase();
    const hasBuangInCard = !!(
      hasilCard &&
      (hasilCard.querySelector('[data-testid="pancing-buang"], [data-testid="pancing-buang-sampah"]') ||
        Array.from(hasilCard.querySelectorAll("button")).some(b => /\bbuang\b/i.test((b.textContent || "").trim())))
    );
    return (
      nameLower.includes("sandal") ||
      classLower.includes("sampah") ||
      cardText.includes("sampah laut") ||
      hasBuangInCard
    );
  }

  function decideSmartLootAction({
    isTrash,
    isSmallFish,
    isBigClass,
    sellPrice,
    baitCost,
    sisaJual,
    sisaTas,
    config,
    availableButtons
  }) {
    if (isTrash && config.autoJualSampah) {
      if (availableButtons.buang) return "BUANG";
      if (availableButtons.jual) return "JUAL_SAMPAH";
    }

    // Prioritaskan jadikan umpan-ikan (2.3x) bila opsi tersedia di kartu hasil; jika tidak tersedia, langsung jual!
    if (config.autoUmpanIkan !== false && !isTrash && availableButtons.umpanIkan) {
      return "JADIKAN_UMPAN";
    }

    if (sisaJual > 0 && availableButtons.jual) {
      return "JUAL";
    }
    if (config.autoSimpan && sisaTas > 0 && availableButtons.simpan) {
      return "SIMPAN";
    }
    if (config.autoJualTasPenuh && sisaJual > 0 && availableButtons.jual) {
      return "JUAL_TAS_PENUH";
    }

    if (availableButtons.makan) return "MAKAN";
    if (availableButtons.lepas) return "LEPAS";
    return "NONE";
  }

  function evaluateStopRule(stopRule, profile) {
    if (!profile || !profile.loaded) return null;
    const sisaJual = Math.max(0, profile.jualMaks - profile.jualHariIni);
    const sisaTas = Math.max(0, profile.tasMaks - profile.tasIkan);
    const totalSlot = profile.jualMaks + profile.tasMaks;

    if (stopRule === "sell-full" && sisaJual === 0) {
      return {
        title: `💰 Kuota Jual ${profile.jualMaks}/${profile.jualMaks} Penuh!`,
        detail: `Target jual harian tercapai (Tas: ${profile.tasIkan}/${profile.tasMaks}). Ubah Aturan Stop jika ingin lanjut isi tas.`,
        color: "#22c55e"
      };
    }
    if (stopRule === "all-full" && sisaJual === 0 && sisaTas === 0) {
      return {
        title: `🏆 Target ${totalSlot}/${totalSlot} Tercapai!`,
        detail: `${profile.jualMaks}/${profile.jualMaks} terjual & ${profile.tasMaks}/${profile.tasMaks} tas penuh. Berhenti otomatis agar hemat umpan.`,
        color: "#22c55e"
      };
    }
    return null;
  }

  // Penanganan Hasil Tangkapan (Zero-Loss & Max Cuan Selective 40+ Slot)
  function handleCatch(hasilCard) {
    if (lootPending || !hasilCard || hasilCard.dataset?.ksHandled === "1") return;

    // Tunggu kartu hasil siap (data-siap) agar tidak mengklik tombol yang masih disabled
    const btnBuangInit = findCatchButton(hasilCard, ['[data-testid="pancing-buang"]', '[data-testid="pancing-buang-sampah"]'], /\bbuang\b/i);
    const btnSimpanInit = findCatchButton(hasilCard, ['[data-testid="pancing-simpan"]'], /\bsimpan\b/i);
    const btnJualInit = findCatchButton(hasilCard, ['[data-testid="pancing-jual"]'], /\bjual\b/i);
    const btnLepasInit = findCatchButton(hasilCard, ['[data-testid="pancing-lepas"]'], /\blepas\b/i);
    const anyReadyBtn = [btnBuangInit, btnSimpanInit, btnJualInit, btnLepasInit].some(b => b && !b.disabled);
    if (!hasilCard.hasAttribute("data-siap") && !anyReadyBtn) {
      return;
    }

    const fishNameEl = hasilCard.querySelector('[class*="judulBesar"], .O26Avq_judulBesar');
    const fishWeightEl = hasilCard.querySelector('[class*="berat"], .O26Avq_berat');
    const fishClassEl = hasilCard.querySelector('[class*="kelas"], .O26Avq_kelas');
    const fishName = fishNameEl ? fishNameEl.textContent.trim() : "Ikan";
    const fishWeight = fishWeightEl ? fishWeightEl.textContent.trim() : "";
    const fishClass = fishClassEl ? fishClassEl.textContent.trim().toLowerCase() : "";
    const key = `${fishName}-${fishWeight}`;

    const isTrash = isTrashCatch(hasilCard, fishName, fishClass);
    const sellPrice = isTrash ? 0 : calcFishPrice(hasilCard, fishName, fishClass, fishWeight);
    const activeBaitType =
      activeCastState?.baitType ||
      (lastApiCastBait && performance.now() - lastApiCastBait.at < 180000 ? lastApiCastBait.baitType : "") ||
      getEquippedUmpanType();
    const baitCost = getUmpanCostByType(activeBaitType);
    const profit = roundCoin(sellPrice - baitCost);
    const profitSign = profit >= 0 ? "+" : "";
    const profitText = `${profitSign}${profit.toFixed(2)} koin`;

    // Pasang badge profit langsung di sebelah/dalam kartu ikan
    let profitBadge = hasilCard.querySelector('#ks-hasil-profit-badge');
    if (!profitBadge) {
      profitBadge = document.createElement('div');
      profitBadge.id = 'ks-hasil-profit-badge';
      profitBadge.style.cssText = `
        margin-top: 6px;
        margin-bottom: 6px;
        padding: 6px 10px;
        border-radius: 8px;
        font-size: 11px;
        font-weight: bold;
        text-align: center;
        background: ${profit >= 0 ? 'rgba(34, 197, 94, 0.22)' : 'rgba(239, 68, 68, 0.22)'};
        border: 1px solid ${profit >= 0 ? '#22c55e' : '#ef4444'};
        color: ${profit >= 0 ? '#4ade80' : '#f87171'};
      `;
      const anchor = hasilCard.querySelector('[class*="kecil"]') || hasilCard.firstChild;
      if (anchor && anchor.parentNode) {
        anchor.parentNode.insertBefore(profitBadge, anchor.nextSibling);
      } else {
        hasilCard.appendChild(profitBadge);
      }
    }
    profitBadge.innerHTML = `💰 Jual: <b>${sellPrice.toFixed(2)} koin</b> | Umpan: <b>${baitCost.toFixed(2)}</b> ➔ Laba: <b style="color: ${profit >= 0 ? '#86efac' : '#fca5a5'};">${profitText}</b>`;

    // Tandai kartu DOM ini agar tidak pernah tercatat 2x saat POST /api/pancing { aksi: "habiskan" } sedang in-flight
    if (hasilCard.dataset) hasilCard.dataset.ksHandled = "1";

    if (hasilCard.dataset?.ksRecorded !== "1" && lastCatchId !== key) {
      if (hasilCard.dataset) hasilCard.dataset.ksRecorded = "1";
      lastCatchId = key;
      if (activeCastState) activeCastState.caught = true;
      if (!isTrash) {
        mancingStats.catches++;
      } else {
        mancingStats.losses++;
        mancingStats.totalLoss = roundCoin(mancingStats.totalLoss + baitCost);
      }
      mancingStats.totalProfit = roundCoin(mancingStats.totalProfit + profit);
      mancingStats.lastFish = `${fishName} (${fishWeight}) ➔ Profit: ${profitText} (Jual: ${sellPrice.toFixed(2)} koin)`;
      mancingStats.history.unshift({
        name: fishName,
        weight: fishWeight,
        sellPrice,
        profit,
        action: "",
        isLoss: isTrash || profit < 0
      });
      saveDailyMancingStats();
      updateMancingUI();
    }

    lootPending = true;
    // Jeda observasi manusiawi membaca kartu ikan: 1.4s - 2.5s
    const readDelay = mancingConfig.modeNatural ? humanJitter(1400, 2500) : 500;

    function releaseLootLockWhenCardCloses(cardEl, clickedOk) {
      if (!clickedOk) {
        if (cardEl.dataset) delete cardEl.dataset.ksHandled;
        lootPending = false;
        return;
      }
      const startedWait = performance.now();
      const pollDismiss = () => {
        const curCard = document.querySelector('[data-testid="pancing-hasil"]');
        const cardGone = !cardEl.isConnected || curCard !== cardEl;
        if (cardGone || performance.now() - startedWait >= 1800) {
          lastCatchId = null;
          lastLootClosedTime = performance.now();
          postLootCooldownMs = mancingConfig.modeNatural ? humanJitter(1600, 2600) : 1100;
          lootPending = false;
          return;
        }
        setTimeout(pollDismiss, 100);
      };
      setTimeout(pollDismiss, 120);
    }

    function executeLootClick(btn, actionType, statusTitle, statusDetail, color, actionBadge = "") {
      if (statusTitle) updateStatusMsg(statusTitle, statusDetail, color || "#38bdf8");
      naturalClick(btn, (clicked) => {
        if (clicked) {
          const latest = mancingStats.history[0];
          const labelMap = {
            jual: "Jual",
            simpan: "Simpan",
            lepas: "Lepas",
            buang: "Buang",
            makan: "Makan",
            umpan: "Umpan"
          };
          const resolvedBadge = actionBadge || labelMap[actionType] || "";
          if (actionType === "jual") {
            pancingProfile.jualHariIni = Math.min(pancingProfile.jualMaks, pancingProfile.jualHariIni + 1);
          } else if (actionType === "simpan") {
            pancingProfile.tasIkan = Math.min(pancingProfile.tasMaks, pancingProfile.tasIkan + 1);
          } else if (actionType === "lepas" || actionType === "makan") {
            if (actionType === "lepas") mancingStats.released++;
            // Karena tidak dijual/disimpan (dilepas, dimakan, atau jadi umpan), koreksi laba menjadi -baitCost saja
            mancingStats.totalProfit = roundCoin(mancingStats.totalProfit - sellPrice);
            if (resolvedBadge !== "Umpan" && baitCost > 0) {
              mancingStats.losses++;
              mancingStats.totalLoss = roundCoin(mancingStats.totalLoss + baitCost);
            }
            if (latest && typeof latest === "object") {
              latest.profit = -baitCost;
              if (resolvedBadge !== "Umpan") latest.isLoss = true;
            }
            if (resolvedBadge === "Umpan" && Array.isArray(pancingProfile.umpanList)) {
              const entryIkan = pancingProfile.umpanList.find(u => u.id === "umpan-ikan");
              if (entryIkan) entryIkan.stok = (entryIkan.stok || 0) + 1;
            }
          }
          if (latest && typeof latest === "object" && resolvedBadge) {
            latest.action = resolvedBadge;
          }
          saveDailyMancingStats();
          updateMancingUI();
        }
        releaseLootLockWhenCardCloses(hasilCard, clicked);
        setTimeout(() => fetchPancingData(true), 1200);
      });
    }

    setTimeout(() => {
      const btnBuang = findCatchButton(hasilCard, ['[data-testid="pancing-buang"]', '[data-testid="pancing-buang-sampah"]'], /\bbuang\b/i);
      const btnSimpan = findCatchButton(hasilCard, ['[data-testid="pancing-simpan"]'], /\bsimpan\b/i);
      const btnJual = findCatchButton(hasilCard, ['[data-testid="pancing-jual"]'], /\bjual\b/i);
      const btnMakan = findCatchButton(hasilCard, ['[data-testid="pancing-makan"]'], /\bmakan\b/i);
      const btnLepas = findCatchButton(hasilCard, ['[data-testid="pancing-lepas"]'], /\blepas\b/i);
      const btnUmpanIkan = findCatchButton(
        hasilCard,
        ['[data-testid="pancing-umpan-ikan"]', '[data-testid="pancing-jadikan-umpan"]'],
        /jadikan\s*umpan|buat\s*umpan|umpan\s*hidup/i
      );

      const sisaJual = Math.max(0, pancingProfile.jualMaks - pancingProfile.jualHariIni);
      const sisaTas = Math.max(0, pancingProfile.tasMaks - pancingProfile.tasIkan);
      const stokUmpan = getUmpanStok();
      const nameLower = fishName.toLowerCase();
      const isBigClass =
        fishClass.includes("besar") ||
        fishClass.includes("raksasa") ||
        ["kerapu", "tongkol", "tenggiri", "cakalang", "lemadang", "barakuda", "kuwe", "tuna", "layaran", "marlin"].some(k => nameLower.includes(k));
      const isSmallFish = !isTrash && !isBigClass && (fishClass.includes("kecil") || sellPrice < 0.70);

      const decision = decideSmartLootAction({
        isTrash,
        isSmallFish,
        isBigClass,
        sellPrice,
        baitCost,
        baitType: activeBaitType,
        sisaJual,
        sisaTas,
        saldoKoin: pancingProfile.saldoKoin,
        stokUmpan,
        config: mancingConfig,
        availableButtons: {
          buang: !!(btnBuang && !btnBuang.disabled),
          jual: !!(btnJual && !btnJual.disabled),
          simpan: !!(btnSimpan && !btnSimpan.disabled),
          makan: !!(btnMakan && !btnMakan.disabled),
          lepas: !!(btnLepas && !btnLepas.disabled),
          umpanIkan: !!(btnUmpanIkan && !btnUmpanIkan.disabled)
        }
      });

      if (decision === "JADIKAN_UMPAN") {
        executeLootClick(
          btnUmpanIkan,
          "lepas",
          "🐟 Jadi Umpan Hidup!",
          `${fishName} dijadikan umpan-ikan (2.3× ikan besar)`,
          "#22c55e",
          "Umpan"
        );
        return;
      }

      if (decision === "BUANG") {
        executeLootClick(btnBuang, "buang", "🗑️ Sampah Laut", `Membuang ${fishName} ke tempat sampah`, "#94a3b8");
        return;
      }
      if (decision === "JUAL_SAMPAH") {
        executeLootClick(btnJual, "buang", "🗑️ Sampah Laut", `Menjual ${fishName} otomatis`, "#94a3b8");
        return;
      }
      if (decision === "LEPAS") {
        executeLootClick(
          btnLepas,
          "lepas",
          "💎 Selektif Max Cuan",
          `Lepas ${fishName} (${sellPrice.toFixed(2)} koin) agar slot diisi ikan mahal`,
          "#c084fc"
        );
        return;
      }
      if (decision === "JUAL") {
        executeLootClick(
          btnJual,
          "jual",
          "💰 Jual Ikan Mahal",
          `${fishName} (${sellPrice.toFixed(2)} koin) · Sisa jual ${Math.max(0, sisaJual - 1)}/${pancingProfile.jualMaks}`,
          "#22c55e"
        );
        return;
      }
      if (decision === "SIMPAN") {
        const reason = sisaJual === 0 ? "Jatah jual habis, simpan untuk besok" : "Hemat kuota jual untuk ikan besar";
        executeLootClick(btnSimpan, "simpan", "🎒 Simpan ke Tas", `${fishName} · ${reason}`, "#38bdf8");
        return;
      }
      if (decision === "JUAL_TAS_PENUH") {
        executeLootClick(btnJual, "jual", "🎒 Tas Penuh!", `Menjual ${fishName} (Zero-Loss)`, "#eab308");
        return;
      }
      if (decision === "MAKAN") {
        executeLootClick(btnMakan, "makan", "🍽️ Makan Ikan", `Memakan ${fishName} (+Makan)`, "#38bdf8");
        return;
      }

      // Jika semua tombol aksi nonaktif/tidak ditemukan -> tunggu dengan jeda aman agar tidak spam klik
      updateStatusMsg("⚠️ Aksi Tangkapan Tertahan", "Tombol buang/simpan/jual tidak tersedia", "#ef4444");
      setTimeout(() => {
        lootPending = false;
      }, 3000);
    }, readDelay);
  }

  // Keyboard cancel
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && mancingConfig.autoMancing) {
      toggleAutoMancing(false);
    }
  });

  // Helper: Cek apakah ada jendela modal/sheet game yang sedang terbuka
  function isSheetOpen() {
    return !!(
      document.querySelector('[data-testid="pancing-toko"]') ||
      document.querySelector('[data-testid="pancing-kapal"]') ||
      document.querySelector('[data-testid="pancing-tas"]') ||
      document.querySelector('[data-testid="pancing-kru"]') ||
      document.querySelector('[class*="sheet"], ._06TmsW_sheet, .O26Avq_sheet')
    );
  }

  // Helper: Baca jumlah sisa stok umpan dari tombol chip HUD
  function getUmpanStok() {
    const btnUmpan = document.querySelector('[data-testid="pancing-umpan"]');
    if (!btnUmpan) return -1;
    const bEl = btnUmpan.querySelector("b");
    if (bEl) {
      const val = parseInt(bEl.textContent.trim(), 10);
      return isNaN(val) ? 0 : val;
    }
    const text = btnUmpan.textContent.trim();
    const match = text.match(/(\d+)\s*$/);
    return match ? parseInt(match[1], 10) : 0;
  }

  function countLitSonarBars(sonarEl) {
    if (!sonarEl) return null;

    const aria = sonarEl.getAttribute("aria-label") || "";
    const ariaBarMatch = aria.match(/(\d)\s*\/\s*5/);
    if (ariaBarMatch) return parseInt(ariaBarMatch[1], 10);

    let barNodes = null;
    const svgRects = sonarEl.querySelectorAll("svg rect");
    if (svgRects.length === 5) {
      barNodes = Array.from(svgRects);
    } else {
      const containers = [sonarEl, ...Array.from(sonarEl.querySelectorAll("*"))];
      for (const el of containers) {
        if (el.children.length === 5) {
          const kids = Array.from(el.children);
          if (kids.every(k => (k.textContent || "").trim() === "")) {
            barNodes = kids;
            break;
          }
        }
      }
    }

    if (!barNodes || barNodes.length !== 5) return null;

    // 1. Cek atribut/class aktif eksplisit (misal data-nyala / data-aktif)
    const explicitAttrCount = barNodes.filter(b =>
      b.hasAttribute("data-nyala") ||
      b.hasAttribute("data-aktif") ||
      b.hasAttribute("data-on") ||
      b.getAttribute("aria-current") === "true"
    ).length;
    if (explicitAttrCount > 0) return explicitAttrCount;

    // 2. Fallback: ukur kecerahan warna & opacity tiap bar (bar menyala jauh lebih terang)
    let litCount = 0;
    for (const bar of barNodes) {
      try {
        const cs = window.getComputedStyle(bar);
        const opacity = parseFloat(cs.opacity);
        const op = Number.isFinite(opacity) ? opacity : 1;
        const colorStr = bar.tagName.toLowerCase() === "rect"
          ? (cs.fill || cs.backgroundColor || "")
          : (cs.backgroundColor || cs.fill || "");
        const m = colorStr.match(/rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)(?:\s*[,/]\s*([\d.]+))?\s*\)/i);
        if (!m) continue;
        const r = parseFloat(m[1]);
        const g = parseFloat(m[2]);
        const b = parseFloat(m[3]);
        const a = m[4] !== undefined ? parseFloat(m[4]) : 1;
        const brightness = (0.299 * r + 0.587 * g + 0.114 * b) * a * op;
        if (brightness >= 115) litCount++;
      } catch (_) {}
    }
    return litCount;
  }

  // Helper: Ambil data Sonar dari HUD game (kedalaman meter, keramaian, & jumlah bar 0-5)
  function getSonarData() {
    const sonarEl = document.querySelector('[data-testid="pancing-sonar"]');
    if (!sonarEl) return { depth: 0, crowd: "unknown", bars: null, raw: "" };

    const aria = sonarEl.getAttribute("aria-label") || "";
    const text = sonarEl.textContent || "";

    let depth = 0;
    const matchAria = aria.match(/Kedalaman\s*(\d+)/i);
    if (matchAria) {
      depth = parseInt(matchAria[1], 10);
    } else {
      const matchText = text.match(/(\d+)\s*m/i);
      if (matchText) depth = parseInt(matchText[1], 10);
    }

    let crowd = "Sepi";
    if (aria.toLowerCase().includes("ramai") || text.includes("Ramai")) crowd = "Ramai";
    else if (aria.toLowerCase().includes("lumayan") || text.includes("Lumayan")) crowd = "Lumayan";

    const bars = countLitSonarBars(sonarEl);
    return { depth, crowd, bars, raw: aria || text };
  }

  function formatSonarText(sonar) {
    if (!sonar || sonar.depth <= 0) return "-";
    const barSuffix = typeof sonar.bars === "number" ? ` · ${sonar.bars}/5` : "";
    return `${sonar.depth}m (${sonar.crowd}${barSuffix})`;
  }

  // Helper: Tentukan target kedalaman & ikan paling bernilai sesuai joran aktif, kapal (lepasM), dan umpan
  function getTargetDepth() {
    const activeUmpan = getEquippedUmpanType();
    const isIkanHidup = activeUmpan === "umpan-ikan";
    const isCumi = activeUmpan === "umpan-cumi";
    const isUdang = activeUmpan === "umpan-udang";
    const joranKey = (pancingProfile.joranId || "").toLowerCase();
    const hasOffshoreAccess = (pancingProfile.lepasM || 0) > 0;

    const hasSamudra = joranKey.includes("samudra") || mancingStats.upgradeTerpasang.some(j => j.toLowerCase().includes("samudra"));
    const hasTonda = joranKey.includes("tonda") || mancingStats.upgradeTerpasang.some(j => j.toLowerCase().includes("tonda"));
    const hasKarang = joranKey.includes("karang") || mancingStats.upgradeTerpasang.some(j => j.toLowerCase().includes("karang"));

    // 0. Mode Ternak Umpan Ikan dengan Cacing: tetap di dangkal agar ikan kecil cepat didapat
    if (mancingConfig.strategiUmpan === "ternak-ikan" && activeUmpan === "umpan-cacing") {
      return {
        minDepth: 2,
        maxDepth: 10,
        optimalDepth: 5,
        allowCrowdStopAt: 2,
        targetFish: "Ikan Kecil (Jadi Umpan 2.3×)",
        reason: "Ternak Umpan Ikan (Cacing di Dangkal)"
      };
    }

    // 0b. Mode Just Go + Lempar + Cacing: cukup di perairan dangkal/menengah
    if (mancingConfig.strategiUmpan === "just-go" && mancingConfig.justGoCastMode === "lempar" && activeUmpan === "umpan-cacing") {
      return {
        minDepth: 2,
        maxDepth: 15,
        optimalDepth: 8,
        allowCrowdStopAt: 2,
        targetFish: "Ikan Kecil–Sedang (Lempar)",
        reason: "Just Go · Cacing Lempar"
      };
    }

    // 1. Umpan Ikan Hidup (2.3x), Umpan Cumi (1.7x), atau Joran Samudra: Target Ikan Raksasa
    if (hasSamudra || isIkanHidup || isCumi) {
      const targetFish = hasOffshoreAccess
        ? "Kuwe GT, Barakuda, Tuna/Marlin (Laut Lepas)"
        : "Barakuda (≥24m) & Kuwe GT (≥30m)";
      return {
        minDepth: 25,
        optimalDepth: hasOffshoreAccess ? 35 : 28,
        allowCrowdStopAt: 25,
        targetFish,
        reason: isIkanHidup
          ? "Umpan Ikan Hidup (2.3x Ikan Besar)"
          : hasSamudra
          ? "Joran Samudra (2x Ikan Raksasa)"
          : "Umpan Cumi (Target Termahal Teluk)"
      };
    }

    // 2. Joran Tonda: Target Ikan Cepat (Tenggiri 20m, Cakalang 18m)
    if (hasTonda) {
      return {
        minDepth: 20,
        optimalDepth: 24,
        allowCrowdStopAt: 19,
        targetFish: "Tenggiri & Cakalang",
        reason: "Joran Tonda (1.8x Ikan Cepat)"
      };
    }

    // 3. Joran Karang / Umpan Udang: Target Ikan Sedang/Besar (Tongkol 15m, Kerapu 12m)
    if (hasKarang || isUdang) {
      return {
        minDepth: 15,
        optimalDepth: 18,
        allowCrowdStopAt: 14,
        targetFish: "Tongkol & Kerapu",
        reason: hasKarang ? "Joran Karang (1.8x Ikan Karang)" : "Umpan Udang"
      };
    }

    // 4. Joran Bambu + Umpan Cacing: Target Pemula (Kakap 8m, Bawal 6m)
    return {
      minDepth: 8,
      optimalDepth: 12,
      allowCrowdStopAt: 7,
      targetFish: "Kakap & Bawal",
      reason: "Joran Bambu & Cacing (Target Pemula)"
    };
  }

  let liveShipData = {
    x: 0,
    z: -46,
    h: Math.PI,
    laju: 0,
    titik: [],
    others: [],
    synced: false,
    hasSetInput: false,
    hasIkanAnim: false,
    lastUpdate: 0
  };
  window.addEventListener("ks_mancing_data_update", (e) => {
    if (e.detail) {
      const hasCoords =
        typeof e.detail.x === "number" && Number.isFinite(e.detail.x) &&
        typeof e.detail.z === "number" && Number.isFinite(e.detail.z) &&
        typeof e.detail.h === "number" && Number.isFinite(e.detail.h);
      liveShipData = {
        ...liveShipData,
        ...e.detail,
        synced: liveShipData.synced || hasCoords,
        lastUpdate: performance.now()
      };
      if (Array.isArray(e.detail.titik) && e.detail.titik.length > 0) {
        cachedTitik = e.detail.titik;
        renderSonarRamaiSpots();
      }
    }
  });

  let cachedTitik = [];
  let lastTitikFetchTime = 0;
  let currentTargetSpot = null;

  // Profil Statistik Harian Mancing (Lemparan, Ikan di Tas, Jatah Jual BUMDes, Koin)
  const pancingProfile = {
    lempar: 0,
    dapat: 0,
    tasIkan: 0,
    tasMaks: 20,
    jualHariIni: 0,
    jualMaks: 30,
    saldoKoin: 0,
    kapalNama: "Perahu jukung",
    lepasM: 0,
    hasJaring: false,
    jaringSisa: 0,
    jaringHarian: 0,
    hasLampu: false,
    joranId: "joran-bambu",
    joranNama: "Joran Bambu",
    umpanList: [],
    lastSync: 0,
    loaded: false,
    loading: false,
    loadError: null
  };

  async function fetchPancingData(force = false) {
    if (!force && pancingProfile.loaded && (performance.now() - pancingProfile.lastSync < 20000)) {
      return pancingProfile;
    }
    pancingProfile.loading = true;
    pancingProfile.loadError = null;
    updateMancingUI();
    try {
      const res = await fetch("/api/pancing");
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const data = await res.json();
      if (data) {
        if (data.hariIni) {
          pancingProfile.lempar = data.hariIni.lempar ?? 0;
          pancingProfile.dapat = data.hariIni.dapat ?? 0;
        }
        if (data.jual) {
          pancingProfile.jualHariIni = data.jual.hariIni ?? 0;
          pancingProfile.jualMaks = data.jual.maks ?? 30;
        }
        if (data.tas) {
          pancingProfile.tasIkan = data.tas.ikan ?? 0;
          pancingProfile.tasMaks = data.tas.maks ?? 20;
        }
        if (typeof data.saldoMilli === "number") {
          pancingProfile.saldoKoin = data.saldoMilli / 1000;
        }
        if (data.kapal) {
          const aktifKapal = Array.isArray(data.kapal.daftar)
            ? data.kapal.daftar.find(k => k.dipakai)
            : null;
          pancingProfile.kapalNama = aktifKapal?.nama || pancingProfile.kapalNama;
          pancingProfile.lepasM = typeof data.kapal.lepasM === "number"
            ? data.kapal.lepasM
            : (aktifKapal?.lepasM ?? 0);
          pancingProfile.hasLampu = !!(data.kapal.lampu ?? aktifKapal?.lampu);
        }
        pancingProfile.hasJaring = !!data.jaring;
        pancingProfile.jaringSisa = data.jaring?.sisa ?? 0;
        pancingProfile.jaringHarian = data.jaring?.harian ?? 0;
        if (Array.isArray(data.umpan)) {
          pancingProfile.umpanList = data.umpan;
        }

        let savedJoran = null;
        try {
          savedJoran = localStorage.getItem("ks-pancing-joran");
        } catch (_) {}

        let resolvedJoran = null;
        if (Array.isArray(data.joran)) {
          resolvedJoran =
            data.joran.find(j => j.dipakai) ||
            (savedJoran ? data.joran.find(j => j.id === savedJoran && j.punya) : null) ||
            data.joran.find(j => j.punya) ||
            data.joran[0] ||
            null;
        }
        if (typeof data.joranDipakai === "string" && data.joranDipakai) {
          pancingProfile.joranId = data.joranDipakai;
          pancingProfile.joranNama = resolvedJoran?.nama || data.joranDipakai;
        } else if (resolvedJoran) {
          pancingProfile.joranId = resolvedJoran.id || "joran-bambu";
          pancingProfile.joranNama = resolvedJoran.nama || resolvedJoran.id || "Joran Bambu";
        }
        if (pancingProfile.joranId && !mancingStats.upgradeTerpasang.includes(pancingProfile.joranId)) {
          mancingStats.upgradeTerpasang.push(pancingProfile.joranId);
        }
        if (Array.isArray(data.titik) && data.titik.length > 0) {
          cachedTitik = data.titik;
          lastTitikFetchTime = performance.now();
        }
        pancingProfile.lastSync = performance.now();
        pancingProfile.loaded = true;
        pancingProfile.loading = false;
        pancingProfile.loadError = null;
        updateMancingUI();
      }
    } catch (e) {
      pancingProfile.loading = false;
      pancingProfile.loadError = e?.message || "Gagal mengambil status mancing";
      console.warn("[AutoMancing] Gagal sinkronisasi data profil pancing:", e);
      updateMancingUI();
    }
    return pancingProfile;
  }

  async function fetchSpots(forceRefresh = false) {
    const age = performance.now() - lastTitikFetchTime;
    const ttl = forceRefresh ? 15000 : 180000;
    if (cachedTitik.length > 0 && age < ttl) {
      return cachedTitik;
    }
    await fetchPancingData(true);
    return cachedTitik;
  }

  // Batas resmi area laut & dermaga game (1218nyygvbivb.js module 40572 & 1pdmk46o3mrj6.js module 122624)
  const LAUT_BOUNDS = {
    x0: -320,
    x1: 320,
    z0: -640,
    z1: -14,
    margin: 18
  };

  // Kolisi dermaga asli game: |x| < 4.4 && z > -50 (diberi buffer aman 11m / -58m untuk radius belok kapal)
  const PIER_OBSTACLE = {
    xMin: -11,
    xMax: 11,
    zMin: -58,
    zMax: -14,
    clearZ: -64
  };

  function getBoatSafeBounds(lepasM = pancingProfile.lepasM || 0) {
    const northWall = LAUT_BOUNDS.z0 - Math.max(0, lepasM || 0);
    const m = LAUT_BOUNDS.margin;
    return {
      x0: LAUT_BOUNDS.x0,
      x1: LAUT_BOUNDS.x1,
      z0: northWall,
      z1: LAUT_BOUNDS.z1,
      safeX0: LAUT_BOUNDS.x0 + m,
      safeX1: LAUT_BOUNDS.x1 - m,
      safeZ0: northWall + m,
      safeZ1: LAUT_BOUNDS.z1 - m
    };
  }

  function clampPointToSafeBounds(x, z, lepasM = pancingProfile.lepasM || 0) {
    const b = getBoatSafeBounds(lepasM);
    return {
      x: Math.max(b.safeX0, Math.min(b.safeX1, x)),
      z: Math.max(b.safeZ0, Math.min(b.safeZ1, z))
    };
  }

  // Uji apakah segmen garis (x1,z1)->(x2,z2) memotong kotak rintangan (algoritma Slab 2D)
  function segmentIntersectsBox(x1, z1, x2, z2, box) {
    const dx = x2 - x1;
    const dz = z2 - z1;
    let tMin = 0;
    let tMax = 1;

    if (Math.abs(dx) < 1e-6) {
      if (x1 < box.xMin || x1 > box.xMax) return false;
    } else {
      let tx1 = (box.xMin - x1) / dx;
      let tx2 = (box.xMax - x1) / dx;
      if (tx1 > tx2) [tx1, tx2] = [tx2, tx1];
      tMin = Math.max(tMin, tx1);
      tMax = Math.min(tMax, tx2);
      if (tMin > tMax) return false;
    }

    if (Math.abs(dz) < 1e-6) {
      if (z1 < box.zMin || z1 > box.zMax) return false;
    } else {
      let tz1 = (box.zMin - z1) / dz;
      let tz2 = (box.zMax - z1) / dz;
      if (tz1 > tz2) [tz1, tz2] = [tz2, tz1];
      tMin = Math.max(tMin, tz1);
      tMax = Math.min(tMax, tz2);
      if (tMin > tMax) return false;
    }

    return tMax >= 0 && tMin <= 1;
  }

  // Hindari dermaga (|x| < 4.4 && z > -50) dengan waypoint belok aman di utara dermaga bila jalur lurus memotongnya
  function planPierSafeWaypoint(shipX, shipZ, targetX, targetZ, bounds) {
    const inPierZone = shipX > PIER_OBSTACLE.xMin && shipX < PIER_OBSTACLE.xMax && shipZ > PIER_OBSTACLE.zMin;
    const crossesPier = segmentIntersectsBox(shipX, shipZ, targetX, targetZ, PIER_OBSTACLE);
    if (!inPierZone && !crossesPier) {
      return { x: targetX, z: targetZ, detouringPier: false };
    }
    const sideX = shipX < 0 ? PIER_OBSTACLE.xMin - 4 : PIER_OBSTACLE.xMax + 4;
    const safeClearZ = Math.max(bounds.safeZ0, PIER_OBSTACLE.clearZ);
    // Jika masih di sisi kiri/kanan dermaga (z > zMin), keluar dulu ke utara dermaga di sisi yang sama
    if (shipZ > PIER_OBSTACLE.zMin + 2) {
      return {
        x: Math.max(bounds.safeX0, Math.min(bounds.safeX1, sideX)),
        z: safeClearZ,
        detouringPier: true
      };
    }
    return {
      x: Math.max(bounds.safeX0, Math.min(bounds.safeX1, targetX < 0 ? PIER_OBSTACLE.xMin - 4 : PIER_OBSTACLE.xMax + 4)),
      z: safeClearZ,
      detouringPier: true
    };
  }

  // Prediksi jalur ke depan berdasarkan kecepatan aktual (laju) & haluan (h) untuk mendeteksi lintasan keluar batas lebih awal
  function predictPathOutOfBounds(shipX, shipZ, shipH, shipLaju, bounds) {
    const speed = Math.max(0, Number(shipLaju) || 0);
    const lookaheadSec = Math.max(1.2, Math.min(3.0, 1.0 + speed * 0.22));
    const projSpeed = Math.max(speed, 1.4);
    const vx = Math.sin(shipH) * projSpeed;
    const vz = Math.cos(shipH) * projSpeed;

    let willExit = false;
    let exitWall = "";
    let timeToExit = Infinity;
    const steps = 6;
    for (let s = 1; s <= steps; s++) {
      const t = (lookaheadSec * s) / steps;
      const px = shipX + vx * t;
      const pz = shipZ + vz * t;
      if (px < bounds.safeX0) { willExit = true; exitWall = "west"; timeToExit = t; break; }
      if (px > bounds.safeX1) { willExit = true; exitWall = "east"; timeToExit = t; break; }
      if (pz < bounds.safeZ0) { willExit = true; exitWall = "north"; timeToExit = t; break; }
      if (pz > bounds.safeZ1) { willExit = true; exitWall = "south"; timeToExit = t; break; }
    }
    return { willExit, exitWall, timeToExit, lookaheadSec };
  }

  function calcDepth(x, z) {
    const n = Math.min(1, Math.max(0, (-z - 10) / 630));
    return Math.max(
      1.5,
      2 + n * n * 18 + 20 * n +
        Math.sin(0.021 * x + 1.3) * Math.cos(0.017 * z) * 3 * n +
        Math.max(0, -640 - z) * 0.05
    );
  }

  function findSafeWaypointForDepth(target, shipX, lepasM = pancingProfile.lepasM || 0) {
    const b = getBoatSafeBounds(lepasM);
    const desiredDepth = target.optimalDepth || target.minDepth || 12;
    const safeX = Math.max(b.safeX0 + 12, Math.min(b.safeX1 - 12, Number.isFinite(shipX) ? shipX : 0));
    let bestZ = b.safeZ0;
    let bestErr = Infinity;
    for (let z = b.safeZ1; z >= b.safeZ0; z -= 5) {
      const d = calcDepth(safeX, z);
      const inRange =
        d >= (target.minDepth || 0) &&
        (target.maxDepth == null || d <= target.maxDepth);
      const err = Math.abs(d - desiredDepth) + (inRange ? 0 : 100);
      if (err < bestErr) {
        bestErr = err;
        bestZ = z;
      }
    }
    const depth = calcDepth(safeX, bestZ);
    return {
      id: "synthetic-depth-waypoint",
      x: safeX,
      z: bestZ,
      r: 20,
      kaya: 0.45,
      depth,
      isRamai: false,
      isFiveBar: false,
      meetsDepth: depth >= (target.minDepth || 0) && (target.maxDepth == null || depth <= target.maxDepth),
      isSyntheticDepthPoint: true
    };
  }

  // Hitung daftar seluruh spot Ramai yang bisa dijangkau kapal saat ini, urut dari terdalam ke terdangkal
  function getReachableRamaiSpots(spots, lepasM = pancingProfile.lepasM || 0) {
    if (!Array.isArray(spots) || spots.length === 0) return [];
    const bounds = getBoatSafeBounds(lepasM);
    const reachable = spots.filter(
      (s) =>
        s &&
        typeof s.x === "number" &&
        typeof s.z === "number" &&
        s.z >= bounds.z0 &&
        s.z <= bounds.z1 &&
        s.x >= bounds.x0 &&
        s.x <= bounds.x1
    );

    const list = reachable
      .map((s) => {
        const depth = calcDepth(s.x, s.z);
        let rame = 0.35 * (0.7 + 0.6 * Math.min(1, depth / 30));
        for (const o of spots) {
          if (!o || typeof o.x !== "number" || typeof o.z !== "number") continue;
          const r = o.r || 30;
          const d = Math.hypot(o.x - s.x, o.z - s.z) / r;
          if (d >= 1) continue;
          rame += (o.kaya || 0) * (1 - d * d);
        }
        rame = Math.min(1, rame);
        const kaya = s.kaya || 0;
        const isRamai = kaya >= RAMAI_MIN_KAYA || rame >= 0.65;
        const isFiveBar = kaya >= FIVE_BAR_MIN_KAYA || rame >= 0.85;
        const bars = isFiveBar ? 5 : Math.max(1, Math.min(5, Math.round(rame * 5)));
        return {
          ...s,
          depth,
          depthM: Math.round(depth),
          kaya,
          rame,
          bars,
          isRamai,
          isFiveBar
        };
      })
      .filter((s) => s.isRamai);

    list.sort((a, b) => (b.depth - a.depth) || (b.rame - a.rame));
    return list;
  }

  let lastRamaiSpotsSig = "";

  function renderSonarRamaiSpots() {
    const el = document.getElementById("ks-mancing-ramai-spots");
    if (!el) return;

    const spots = cachedTitik.length > 0 ? cachedTitik : liveShipData.titik;
    if (!pancingProfile.loaded && (!spots || spots.length === 0)) {
      el.innerHTML = `<span style="color: #94a3b8;">🗺️ Spot Ramai: Memuat peta...</span>`;
      lastRamaiSpotsSig = "";
      return;
    }

    const ramaiSpots = getReachableRamaiSpots(spots, pancingProfile.lepasM || 0);
    const sig = ramaiSpots.map((s) => `${s.depthM}:${s.bars}:${Math.round(s.kaya * 100)}`).join("|") + `@${pancingProfile.lepasM || 0}`;
    if (sig === lastRamaiSpotsSig && el.dataset?.ksRendered === "1") return;
    lastRamaiSpotsSig = sig;
    if (el.dataset) el.dataset.ksRendered = "1";

    if (ramaiSpots.length === 0) {
      el.innerHTML = `<span style="color: #94a3b8;">🗺️ Spot Ramai: <b style="color: #f59e0b;">Tidak ada di jangkauan kapal</b></span>`;
      return;
    }

    const chipsHtml = ramaiSpots.map((s, idx) => {
      const isDeep = s.depthM >= 25;
      const isDeepest = idx === 0;
      const distTxt = liveShipData.synced
        ? ` · jarak ${Math.round(Math.hypot(s.x - liveShipData.x, s.z - liveShipData.z))}m`
        : "";
      const tip = `${s.depthM}m · ${s.bars}/5 bar (${Math.round(s.kaya * 100)}% kaya)${distTxt}`;
      const bg = isDeepest && isDeep
        ? "rgba(34, 197, 94, 0.22)"
        : isDeep
        ? "rgba(0, 229, 255, 0.16)"
        : "rgba(148, 163, 184, 0.14)";
      const border = isDeepest && isDeep
        ? "rgba(74, 222, 128, 0.55)"
        : isDeep
        ? "rgba(0, 229, 255, 0.4)"
        : "rgba(148, 163, 184, 0.28)";
      const color = isDeepest && isDeep
        ? "#86efac"
        : isDeep
        ? "#67e8f9"
        : "#cbd5e1";
      const barTag = s.bars >= 5 ? " · 5/5" : "";
      return `<span title="${escapeHtml(tip)}" style="display:inline-flex;align-items:center;padding:1px 5px;border-radius:4px;background:${bg};border:1px solid ${border};color:${color};font-size:9.2px;font-weight:700;line-height:1.35;">${s.depthM}m${barTag}</span>`;
    }).join("");

    el.innerHTML =
      `<div style="display:flex;align-items:flex-start;gap:4px;flex-wrap:wrap;">` +
        `<span style="color:#94a3b8;font-size:9.3px;font-weight:700;padding-top:1px;flex-shrink:0;">🗺️ Ramai:</span>` +
        `<div style="display:flex;flex-wrap:wrap;gap:3px;flex:1;min-width:0;">${chipsHtml}</div>` +
      `</div>`;
  }

  // Hitung kepadatan (rame) & kedalaman persis seperti rumus game (1218nyygvbivb.js module 816407)
  function calcSpotRameAt(px, pz, spots) {
    const depth = calcDepth(px, pz);
    let rame = 0.35 * (0.7 + 0.6 * Math.min(1, depth / 30));
    if (Array.isArray(spots)) {
      for (const o of spots) {
        if (!o || typeof o.x !== "number" || typeof o.z !== "number") continue;
        const r = o.r || 30;
        const ratio = Math.hypot(o.x - px, o.z - pz) / r;
        if (ratio >= 1) continue;
        rame += (o.kaya || 0) * (1 - ratio * ratio);
      }
    }
    return { depth, rame: Math.min(1, rame) };
  }

  function getNearestOtherBoatDist(px, pz, others = liveShipData.others) {
    if (!Array.isArray(others) || others.length === 0) return Infinity;
    let best = Infinity;
    for (const o of others) {
      if (!o || typeof o.x !== "number" || typeof o.z !== "number") continue;
      const d = Math.hypot(o.x - px, o.z - pz);
      if (d < best) best = d;
    }
    return best;
  }

  let spotOffsetLock = null; // { key, x, z, pickedAt }
  let lastPlayerNudgeAt = 0;
  const PLAYER_CROWD_DIST = 9;     // Jarak < 9m dianggap terlalu dempet dengan pemain lain
  const PLAYER_SAFE_DIST = 15;     // Target jarak aman dari pemain lain saat geser posisi
  const PLAYER_NUDGE_COOLDOWN_MS = 15000;

  function getSpotLockKey(spot) {
    if (!spot) return "";
    return spot.id !== undefined ? String(spot.id) : `${Math.round(spot.x)}:${Math.round(spot.z)}`;
  }

  // Pilih titik posisi agak acak di dalam zona spot yang tetap mempertahankan tier kedalaman & kepadatan (5/5 Ramai),
  // sekaligus menjauh sedikit dari posisi perahu pemain lain bila ada yang berdekatan.
  function pickOffsetPointInSpot(spot, spots, otherBoats, target, bounds, { forceRepick = false, rng = Math.random } = {}) {
    if (!spot) return null;
    const key = getSpotLockKey(spot);
    const others = Array.isArray(otherBoats) ? otherBoats : [];

    if (!forceRepick && spotOffsetLock && spotOffsetLock.key === key) {
      const lockedDist = getNearestOtherBoatDist(spotOffsetLock.x, spotOffsetLock.z, others);
      if (lockedDist >= PLAYER_CROWD_DIST) {
        return { x: spotOffsetLock.x, z: spotOffsetLock.z, movedForPlayer: false };
      }
    }

    const basePt = clampPointToSafeBounds(spot.x, spot.z, pancingProfile.lepasM || 0);
    if (spot.isSyntheticDepthPoint) {
      const jitterX = (rng() - 0.5) * 40;
      const jitterZ = (rng() - 0.5) * 16;
      const pt = clampPointToSafeBounds(basePt.x + jitterX, basePt.z + jitterZ, pancingProfile.lepasM || 0);
      spotOffsetLock = { key, x: pt.x, z: pt.z, pickedAt: performance.now() };
      return { x: pt.x, z: pt.z, movedForPlayer: false };
    }

    const centerEval = calcSpotRameAt(basePt.x, basePt.z, spots);
    const radius = Math.max(12, spot.r || 30);
    const wantsDeep30 = target && target.maxDepth == null && centerEval.depth >= 30;
    const reqMinDepth = wantsDeep30 ? 30 : (target?.minDepth || 0);
    const reqMaxDepth = target?.maxDepth ?? null;
    // Pertahankan 5/5 Ramai bila pusat spot 5/5, atau tetap Ramai
    const minRame = centerEval.rame >= 0.85
      ? Math.min(0.85, centerEval.rame - 0.03)
      : Math.max(0.65, centerEval.rame - 0.05);

    const candidates = [{ x: basePt.x, z: basePt.z, rame: centerEval.rame, depth: centerEval.depth }];
    const sampleCount = 20;
    for (let i = 0; i < sampleCount; i++) {
      const angle = (i / sampleCount) * Math.PI * 2 + rng() * 0.35;
      const frac = 0.16 + rng() * 0.46; // 16%–62% dari radius spot
      const rawX = spot.x + Math.cos(angle) * radius * frac;
      const rawZ = spot.z + Math.sin(angle) * radius * frac;
      const pt = clampPointToSafeBounds(rawX, rawZ, pancingProfile.lepasM || 0);
      if (pt.x < bounds.safeX0 || pt.x > bounds.safeX1 || pt.z < bounds.safeZ0 || pt.z > bounds.safeZ1) continue;
      const ev = calcSpotRameAt(pt.x, pt.z, spots);
      if (ev.depth < reqMinDepth) continue;
      if (reqMaxDepth != null && ev.depth > reqMaxDepth) continue;
      if (ev.rame < minRame) continue;
      candidates.push({ x: pt.x, z: pt.z, rame: ev.rame, depth: ev.depth });
    }

    let best = candidates[0];
    let bestScore = -Infinity;
    for (const c of candidates) {
      const playerDist = getNearestOtherBoatDist(c.x, c.z, others);
      const crowdPenalty = playerDist < PLAYER_CROWD_DIST ? -500 : (playerDist < PLAYER_SAFE_DIST ? -120 : 0);
      const spacingBonus = Math.min(28, Number.isFinite(playerDist) ? playerDist : 28) * 6;
      const rameBonus = c.rame * 120;
      const randomJitter = rng() * 34; // Variasi posisi natural di dalam tier yang sama
      const score = crowdPenalty + spacingBonus + rameBonus + randomJitter;
      if (score > bestScore) {
        bestScore = score;
        best = c;
      }
    }

    const movedForPlayer = forceRepick && others.length > 0;
    spotOffsetLock = { key, x: best.x, z: best.z, pickedAt: performance.now() };
    return { x: best.x, z: best.z, movedForPlayer };
  }

  // Batas resmi game untuk status "Ramai": rame >= 0.45 (5 bar penuh sekitar >= 0.78)
  const RAMAI_MIN_KAYA = 0.45;
  const FIVE_BAR_MIN_KAYA = 0.78;

  function rankFishingAreas(spots, shipX, shipZ, target = null) {
    if (!spots || spots.length === 0) return [];

    const activeTarget = target || getTargetDepth();
    const minDepth = activeTarget.minDepth || 0;
    const maxDepth = activeTarget.maxDepth ?? null;
    const bounds = getBoatSafeBounds(pancingProfile.lepasM || 0);
    const reachableSpots = spots.filter(
      s => s.z >= bounds.z0 && s.z <= bounds.z1 && s.x >= bounds.x0 && s.x <= bounds.x1
    );
    const pool = reachableSpots.length > 0 ? reachableSpots : [];
    if (pool.length === 0) return [];

    const ranked = pool.map(s => {
      const d = calcDepth(s.x, s.z);
      const dist = Math.hypot(s.x - shipX, s.z - shipZ);
      const meetsDepth = d >= minDepth && (maxDepth === null || d <= maxDepth);
      const isRamai = (s.kaya || 0) >= RAMAI_MIN_KAYA;
      const isFiveBar = (s.kaya || 0) >= FIVE_BAR_MIN_KAYA;
      // Untuk target laut dalam (tanpa maxDepth), SELALU prioritaskan spot 30m+ Ramai di atas spot <30m
      const isDeep30 = maxDepth === null && d >= 30;
      const tier = (isDeep30 && isFiveBar)
        ? 6
        : (isDeep30 && isRamai)
        ? 5
        : (meetsDepth && isFiveBar)
        ? 4
        : (meetsDepth && isRamai)
        ? 3
        : meetsDepth
        ? 2
        : isRamai
        ? 1
        : 0;
      const depthBonus = maxDepth !== null
        ? Math.max(0, 60 - Math.abs(d - (activeTarget.optimalDepth || 5)) * 8)
        : (d >= 34 ? 140 : d >= 30 ? 120 : d >= 24 ? 80 : d >= 15 ? 40 : d);
      const score = (tier * 1000) + ((s.kaya || 0) * 600) + depthBonus - (dist * 0.08);
      return { ...s, depth: d, dist, tier, isRamai, isFiveBar, isDeep30, meetsDepth, score };
    });

    ranked.sort((a, b) => b.score - a.score);
    return ranked;
  }

  function findBestCrowdedSpot(spots, shipX, shipZ, target = null) {
    const ranked = rankFishingAreas(spots, shipX, shipZ, target);
    if (ranked.length === 0) return null;

    // Spot Lock (Hysteresis): pertahankan spot target yang sedang dituju agar kapal tidak zig-zag
    if (isNavigating && currentTargetSpot) {
      const locked = ranked.find(s =>
        (currentTargetSpot.id !== undefined && s.id === currentTargetSpot.id) ||
        Math.hypot(s.x - currentTargetSpot.x, s.z - currentTargetSpot.z) < 6
      );
      const best = ranked[0];
      if (locked && locked.tier >= best.tier && (best.score - locked.score) < 120) {
        return locked;
      }
    }
    return ranked[0];
  }

  let activeTurnPulseTimer = null;
  let lastRecordedShipH = null;
  let shipHStuckCount = 0;
  let lastCommandedBelok = 0;
  let lastAbsHeadingDiff = null;
  let wrongTurnStreak = 0;
  let navTurnSign = 1;
  let kbGasDown = false;

  function releaseKeyboardSteer() {
    if (activeTurnPulseTimer) {
      clearTimeout(activeTurnPulseTimer);
      activeTurnPulseTimer = null;
    }
    if (kbGasDown) {
      kbGasDown = false;
      window.dispatchEvent(new KeyboardEvent("keyup", { code: "KeyW", key: "w", bubbles: true }));
      window.dispatchEvent(new KeyboardEvent("keyup", { code: "ArrowUp", key: "ArrowUp", bubbles: true }));
    }
    window.dispatchEvent(new KeyboardEvent("keyup", { code: "KeyA", key: "a", bubbles: true }));
    window.dispatchEvent(new KeyboardEvent("keyup", { code: "KeyD", key: "d", bubbles: true }));
    window.dispatchEvent(new KeyboardEvent("keyup", { code: "ArrowLeft", key: "ArrowLeft", bubbles: true }));
    window.dispatchEvent(new KeyboardEvent("keyup", { code: "ArrowRight", key: "ArrowRight", bubbles: true }));
  }

  function steerShip(gas, belok) {
    const g = Math.max(-1, Math.min(1, gas || 0));
    const b = Math.max(-1, Math.min(1, belok || 0));
    lastCommandedBelok = b;

    // 1. Direct analog engine steering via inject.js (halus & presisi tanpa konflik keyboard)
    window.dispatchEvent(new CustomEvent("ks_mancing_steer", {
      detail: { gas: g, belok: b }
    }));

    if (liveShipData.hasSetInput) {
      if (kbGasDown || activeTurnPulseTimer) {
        releaseKeyboardSteer();
      }
      return;
    }

    // 2. Fallback keyboard jika setInput belum tersedia
    if (g > 0.1) {
      if (!kbGasDown) {
        kbGasDown = true;
        window.dispatchEvent(new KeyboardEvent("keydown", { code: "KeyW", key: "w", bubbles: true }));
        window.dispatchEvent(new KeyboardEvent("keydown", { code: "ArrowUp", key: "ArrowUp", bubbles: true }));
      }
    } else if (kbGasDown) {
      kbGasDown = false;
      window.dispatchEvent(new KeyboardEvent("keyup", { code: "KeyW", key: "w", bubbles: true }));
      window.dispatchEvent(new KeyboardEvent("keyup", { code: "ArrowUp", key: "ArrowUp", bubbles: true }));
    }

    if (activeTurnPulseTimer) {
      clearTimeout(activeTurnPulseTimer);
      activeTurnPulseTimer = null;
    }

    if (Math.abs(b) < 0.05) {
      window.dispatchEvent(new KeyboardEvent("keyup", { code: "KeyA", key: "a", bubbles: true }));
      window.dispatchEvent(new KeyboardEvent("keyup", { code: "KeyD", key: "d", bubbles: true }));
    } else {
      const pulseMs = Math.round(45 + Math.min(1, Math.abs(b)) * 75);
      const activeKey = b > 0 ? { code: "KeyA", key: "a" } : { code: "KeyD", key: "d" };
      const otherKey = b > 0 ? { code: "KeyD", key: "d" } : { code: "KeyA", key: "a" };
      window.dispatchEvent(new KeyboardEvent("keyup", { ...otherKey, bubbles: true }));
      window.dispatchEvent(new KeyboardEvent("keydown", { ...activeKey, bubbles: true }));
      activeTurnPulseTimer = setTimeout(() => {
        window.dispatchEvent(new KeyboardEvent("keyup", { ...activeKey, bubbles: true }));
        window.dispatchEvent(new CustomEvent("ks_mancing_steer", {
          detail: { gas: g, belok: 0 }
        }));
        activeTurnPulseTimer = null;
      }, pulseMs);
    }
  }

  function readBoundaryToastState() {
    const scope = document.querySelector('[data-testid="pancing"]');
    if (!scope) return "";
    const text = (scope.textContent || "").toLowerCase();
    if (text.includes("batas kapalmu")) return "north_ship_limit";
    if (text.includes("batas area mancing") || text.includes("putar balik")) return "area_limit";
    return "";
  }

  function startAutopilotToSpot(spot, shipX, shipZ, shipH, shipLaju = liveShipData.laju || 0) {
    if (!isNavigating) {
      isNavigating = true;
      navStartTime = performance.now();
      lastRecordedShipH = shipH;
      shipHStuckCount = 0;
      lastCommandedBelok = 0;
      lastAbsHeadingDiff = null;
      wrongTurnStreak = 0;
    }
    currentTargetSpot = spot;

    const bounds = getBoatSafeBounds(pancingProfile.lepasM || 0);
    const clampedTarget = clampPointToSafeBounds(spot.x, spot.z, pancingProfile.lepasM || 0);
    const pierRoute = planPierSafeWaypoint(shipX, shipZ, clampedTarget.x, clampedTarget.z, bounds);
    const pathPred = predictPathOutOfBounds(shipX, shipZ, shipH, shipLaju, bounds);

    // Active Boundary Guard: cegah perahu menabrak batas x = ±320, z = -14, atau z = -640 - lepasM
    const nearWest = shipX <= bounds.x0 + 18 || pathPred.exitWall === "west";
    const nearEast = shipX >= bounds.x1 - 18 || pathPred.exitWall === "east";
    const nearNorth = shipZ <= bounds.z0 + 18 || pathPred.exitWall === "north";
    const nearSouth = shipZ >= bounds.z1 - 18 || pathPred.exitWall === "south";
    const nearAnyWall = nearWest || nearEast || nearNorth || nearSouth;

    let steerTargetX = pierRoute.x;
    let steerTargetZ = pierRoute.z;
    if (nearWest && steerTargetX < bounds.x0 + 38) steerTargetX = bounds.x0 + 38;
    if (nearEast && steerTargetX > bounds.x1 - 38) steerTargetX = bounds.x1 - 38;
    if (nearNorth && steerTargetZ < bounds.z0 + 38) steerTargetZ = bounds.z0 + 38;
    if (nearSouth && steerTargetZ > bounds.z1 - 38) steerTargetZ = bounds.z1 - 38;

    const dx = steerTargetX - shipX;
    const dz = steerTargetZ - shipZ;
    const dist = Math.hypot(clampedTarget.x - shipX, clampedTarget.z - shipZ);

    const targetHeading = Math.atan2(dx, dz);
    let diff = (targetHeading - shipH + Math.PI) % (2 * Math.PI);
    if (diff < 0) diff += 2 * Math.PI;
    diff -= Math.PI;
    const absDiff = Math.abs(diff);

    // Cek apakah haluan perahu sedang mengarah keluar ke dinding batas terdekat
    const vx = Math.sin(shipH);
    const vz = Math.cos(shipH);
    const headingOutward =
      (nearWest && vx < -0.12) ||
      (nearEast && vx > 0.12) ||
      (nearNorth && vz < -0.12) ||
      (nearSouth && vz > 0.12);
    const touchingWall =
      shipX <= bounds.x0 + 6 ||
      shipX >= bounds.x1 - 6 ||
      shipZ <= bounds.z0 + 6 ||
      shipZ >= bounds.z1 - 6;

    // Di fisika gerakPerahu() game: saat laju < -0.1, arah belok terbalik (* -1).
    // Jangan jalankan auto-flip polaritas saat mundur agar navTurnSign tidak korup.
    const isReversing = shipLaju < -0.1;
    const reverseSteerSign = isReversing ? -1 : 1;

    // Deteksi heading macet HANYA saat kita aktif memerintahkan belok maju/diam (bukan saat melaju lurus atau mundur)
    if (!isReversing && absDiff > 0.04 && (Math.abs(lastCommandedBelok) > 0.15 || shipHStuckCount > 25)) {
      if (lastRecordedShipH !== null && Math.abs(shipH - lastRecordedShipH) < 0.0008) {
        shipHStuckCount++;
      } else {
        shipHStuckCount = 0;
        lastRecordedShipH = shipH;
      }
      // Auto-koreksi arah belok jika sudut malah menjauh secara konsisten (polaritas terbalik)
      if (Math.abs(lastCommandedBelok) > 0.15 && lastAbsHeadingDiff !== null && absDiff > 0.35 && absDiff < 2.6) {
        if (absDiff > lastAbsHeadingDiff + 0.005) {
          wrongTurnStreak++;
          if (wrongTurnStreak >= 8) {
            navTurnSign *= -1;
            wrongTurnStreak = 0;
          }
        } else if (absDiff < lastAbsHeadingDiff - 0.003) {
          wrongTurnStreak = 0;
        }
      }
    } else {
      shipHStuckCount = 0;
      wrongTurnStreak = 0;
      lastRecordedShipH = shipH;
    }
    lastAbsHeadingDiff = absDiff;

    let belok = 0;
    if (liveShipData.synced && shipHStuckCount <= 25) {
      // Kemudi proporsional dengan deadband ketat 0.04 rad (~2.3 derajat) + kompensasi arah saat mundur
      if (absDiff > 0.04) {
        const rawTurn = Math.max(-1, Math.min(1, diff / 0.45));
        belok = rawTurn * navTurnSign * reverseSteerSign;
      }
    }

    // Kontrol kecepatan + pengereman aktif berbasis fisika gerakPerahu():
    // - Rem aktif (gas < 0 saat laju > 0.35) jauh lebih cepat menghentikan laju kapal kencang (-3.2*lajuKali)
    // - Kapal bisa berputar di tempat saat gas = 0 (turn rate 0.21 rad/s) tanpa terbawa arus ke dinding batas
    let gas = 1.0;
    if (headingOutward && touchingWall) {
      gas = shipLaju > 0.25 ? -1.0 : -0.45;
      belok = (diff >= 0 ? 1 : -1) * navTurnSign * reverseSteerSign;
    } else if ((pathPred.willExit && absDiff > 0.35) || (headingOutward && absDiff > 0.55)) {
      gas = shipLaju > 0.4 ? -0.85 : 0;
      belok = (diff >= 0 ? 1 : -1) * navTurnSign * reverseSteerSign;
    } else if (nearAnyWall && absDiff > 1.05) {
      gas = shipLaju > 0.8 ? -0.5 : 0;
    } else if (absDiff > 1.05) {
      gas = shipLaju > 2.2 ? -0.35 : 0.15;
    } else if (absDiff > 0.45) {
      gas = 0.55;
    } else if (dist < 25) {
      gas = Math.max(0.25, Math.min(1, dist / 25));
    }

    steerShip(gas, belok);

    const degOff = Math.round((absDiff * 180) / Math.PI);
    const label = pierRoute.detouringPier
      ? "⚓ Menghindari Dermaga..."
      : (pathPred.willExit || (nearAnyWall && headingOutward))
      ? "↩️ Menghindari Batas Area..."
      : spot.isSyntheticDepthPoint
      ? `🧭 Menuju Kedalaman ${Math.round(spot.depth)}m...`
      : "🧭 Menuju Spot Ramai...";
    const detail = pierRoute.detouringPier
      ? `Memutar aman di utara dermaga · Arah ${degOff}°`
      : spot.isSyntheticDepthPoint
      ? `Jarak ${Math.round(dist)}m · Arah ${degOff}° (air terbuka ${Math.round(spot.depth)}m, aman batas)`
      : `Jarak ${Math.round(dist)}m · Arah ${degOff}° (${(spot.kaya * 100).toFixed(0)}% kaya, ${Math.round(spot.depth)}m)`;
    updateStatusMsg(label, detail, "#00e5ff");
  }

  function stopAutopilot(reasonMsg) {
    if (isNavigating) {
      isNavigating = false;
      currentTargetSpot = null;
      shipHStuckCount = 0;
      lastCommandedBelok = 0;
      lastAbsHeadingDiff = null;
      wrongTurnStreak = 0;
      releaseKeyboardSteer();
      steerShip(0, 0);
      if (reasonMsg) {
        updateStatusMsg("🎯 Tiba di Spot Ramai!", reasonMsg, "#22c55e");
      }
    }
  }

  // 1. Ganti Umpan Milik Sendiri & (Opt-in) Auto Beli Umpan saat habis
  function scheduleBaitShopAction({ preferredBaitId = null, allowBuy = false } = {}) {
    if (autoUmpanPending) return;
    autoUmpanPending = true;

    updateStatusMsg(
      allowBuy ? "🛒 Cek / Beli Umpan..." : "🪱 Ganti Umpan...",
      allowBuy ? "Membuka toko umpan..." : "Membuka daftar umpan milikmu...",
      "#38bdf8"
    );

    function proceedInShop(sheetToko) {
      function readShopBaitStok(id) {
        const shortId = id.replace("umpan-", "");
        const btnPilih = sheetToko.querySelector(`[data-testid="pancing-pilih-${id}"], [data-testid="pancing-pilih-${shortId}"]`);
        const txt = (btnPilih?.textContent || "").toLowerCase();
        const m = txt.match(/punya\s*(\d+)/i);
        const apiStok = pancingProfile.umpanList?.find(u => u.id === id)?.stok ?? 0;
        const stok = m ? parseInt(m[1], 10) : apiStok;
        return { btnPilih, stok, shortId };
      }

      function equipExistingBait(btnPilih, label) {
        updateStatusMsg("🪱 Pakai Umpan Tersedia!", `Memasang ${label} tanpa beli baru...`, "#22c55e");
        naturalClick(btnPilih);
        setTimeout(() => {
          const btnTutup = sheetToko.querySelector('button[aria-label="Tutup"], button[class*="tutup"]');
          if (btnTutup) naturalClick(btnTutup);
          setTimeout(() => {
            autoUmpanPending = false;
            fetchPancingData(true);
            updateMancingUI();
          }, getActionDelay(0));
        }, getActionDelay(0));
      }

      const isTernakMode = mancingConfig.strategiUmpan === "ternak-ikan";
      const isJustGoMode = mancingConfig.strategiUmpan === "just-go";
      const labelMap = {
        "umpan-ikan": "Ikan Kecil Hidup",
        "umpan-cacing": "Cacing Laut",
        "umpan-cumi": "Potongan Cumi",
        "umpan-udang": "Udang Hidup"
      };

      // Prioritaskan umpan terpilih yang sudah dimiliki sebelum membeli baru
      const selectedBait = preferredBaitId || getActiveSelectedBait();
      const defaultOwnedOrder = isJustGoMode
        ? [selectedBait]
        : isTernakMode
        ? (allowBuy ? ["umpan-cacing"] : ["umpan-ikan", "umpan-cacing"])
        : [selectedBait];
      const checkOrder = [
        ...(preferredBaitId ? [preferredBaitId] : []),
        ...defaultOwnedOrder
      ].filter((v, idx, arr) => v && arr.indexOf(v) === idx);

      for (const baitId of checkOrder) {
        const info = readShopBaitStok(baitId);
        if (info.btnPilih && !info.btnPilih.disabled && info.stok > 0) {
          equipExistingBait(info.btnPilih, `${labelMap[baitId] || baitId} (${info.stok})`);
          return;
        }
      }

      // Jika auto-beli dimatikan -> tutup toko & berhenti aman (TIDAK pernah membeli)
      if (!allowBuy || !mancingConfig.autoUmpan) {
        setTimeout(() => {
          const btnTutup = sheetToko.querySelector('button[aria-label="Tutup"], button[class*="tutup"]');
          if (btnTutup) naturalClick(btnTutup);
          setTimeout(() => {
            autoUmpanPending = false;
            toggleAutoMancing(false, {
              title: "⚠️ Umpan Habis!",
              detail: `Stok ${labelMap[selectedBait] || "umpan"} habis & Auto Umpan mati. Aktifkan Auto Umpan atau beli manual di toko.`,
              color: "#f59e0b"
            });
          }, getActionDelay(0));
        }, getActionDelay(0));
        return;
      }

      // Umpan ikan tidak tersedia dibeli di toko (hanya dari hasil ternak)
      const targetPref = isTernakMode ? "umpan-cacing" : selectedBait;
      if (targetPref === "umpan-ikan") {
        setTimeout(() => {
          const btnTutup = sheetToko.querySelector('button[aria-label="Tutup"], button[class*="tutup"]');
          if (btnTutup) naturalClick(btnTutup);
          setTimeout(() => {
            autoUmpanPending = false;
            toggleAutoMancing(false, {
              title: "⚠️ Stok Umpan Ikan Habis!",
              detail: "Ikan Kecil Hidup tidak bisa dibeli di toko. Pilih Cacing/Udang/Cumi di Just Go atau gunakan template Ternak.",
              color: "#f59e0b"
            });
          }, getActionDelay(0));
        }, getActionDelay(0));
        return;
      }

      // Step 2 (Opt-in Auto Beli Umpan): Pilih paket jumlah (5 jika sisa slot <= 5 atau saldo < 5, selain itu 10)
      setTimeout(() => {
        const qtyButtons = Array.from(sheetToko.querySelectorAll('button[role="radio"]'));
        const btn10 = qtyButtons.find(b => b.textContent.trim() === "10");
        const btn5 = qtyButtons.find(b => b.textContent.trim() === "5");
        const sisaJual = pancingProfile.loaded ? Math.max(0, pancingProfile.jualMaks - pancingProfile.jualHariIni) : 30;
        const sisaSlot = pancingProfile.loaded
          ? sisaJual + Math.max(0, pancingProfile.tasMaks - pancingProfile.tasIkan)
          : 50;
        const remainingTargetSlots = mancingConfig.stopRule === "sell-full" ? sisaJual : sisaSlot;
        const lowCoinPack5 = pancingProfile.loaded && pancingProfile.saldoKoin < 5.0;
        const preferPack5 = (mancingConfig.stopRule !== "bait-empty" && remainingTargetSlots > 0 && remainingTargetSlots <= 5) || lowCoinPack5;
        if (preferPack5 && btn5) naturalClick(btn5);
        else if (btn10) naturalClick(btn10);
        else if (btn5) naturalClick(btn5);

        // Step 3: Klik tombol beli umpan yang dipilih (kecuali Ternak selalu beli Cacing Laut)
        setTimeout(() => {
          const btnBeliCumi = sheetToko.querySelector('[data-testid="pancing-beli-cumi"], [data-testid="pancing-beli-umpan-cumi"]');
          const btnBeliUdang = sheetToko.querySelector('[data-testid="pancing-beli-udang"], [data-testid="pancing-beli-umpan-udang"]');
          const btnBeliCacing = sheetToko.querySelector('[data-testid="pancing-beli-cacing"], [data-testid="pancing-beli-umpan-cacing"]');

          let targetBeli = null;
          let namaUmpan = labelMap[targetPref] || "Umpan";
          let targetPilihId = targetPref.replace("umpan-", "");

          if (targetPref === "umpan-cacing" && btnBeliCacing && !btnBeliCacing.disabled) {
            targetBeli = btnBeliCacing;
            namaUmpan = isTernakMode ? "Cacing Laut (Ternak Umpan Ikan)" : "Cacing Laut";
            targetPilihId = "cacing";
          } else if (targetPref === "umpan-udang" && btnBeliUdang && !btnBeliUdang.disabled) {
            targetBeli = btnBeliUdang;
            namaUmpan = "Udang Hidup";
            targetPilihId = "udang";
          } else if (targetPref === "umpan-cumi" && btnBeliCumi && !btnBeliCumi.disabled) {
            targetBeli = btnBeliCumi;
            namaUmpan = "Potongan Cumi";
            targetPilihId = "cumi";
          }

          if (targetBeli) {
            updateStatusMsg("🛒 Beli Umpan...", `Membeli ${namaUmpan}...`, "#22c55e");
            naturalClick(targetBeli);
            mancingStats.umpanDibeli += preferPack5 ? 5 : 10;

            // Step 4: Klik tombol pakai/pilih umpan tersebut
            setTimeout(() => {
              const btnPilih = sheetToko.querySelector(`[data-testid="pancing-pilih-${targetPilihId}"], [data-testid="pancing-pilih-umpan-${targetPilihId}"]`);
              if (btnPilih) naturalClick(btnPilih);
              updateStatusMsg("✅ Umpan Terpasang!", `${namaUmpan} siap digunakan`, "#22c55e");

              // Step 5: Tutup sheet toko umpan
              setTimeout(() => {
                const btnTutup = sheetToko.querySelector('button[aria-label="Tutup"], button[class*="tutup"]');
                if (btnTutup) naturalClick(btnTutup);

                // Step 6: Jeda alami setelah sheet tertutup sebelum lempar kail
                setTimeout(() => {
                  autoUmpanPending = false;
                  fetchPancingData(true);
                  updateMancingUI();
                }, getActionDelay(0));
              }, getActionDelay(0));
            }, getActionDelay(0));
          } else {
            // Saldo koin tidak cukup untuk beli umpan
            setTimeout(() => {
              const btnTutup = sheetToko.querySelector('button[aria-label="Tutup"], button[class*="tutup"]');
              if (btnTutup) naturalClick(btnTutup);
              setTimeout(() => {
                autoUmpanPending = false;
                toggleAutoMancing(false, {
                  title: "⚠️ Saldo Koin Kurang!",
                  detail: "Tidak cukup koin untuk beli umpan otomatis.",
                  color: "#ef4444"
                });
              }, getActionDelay(0));
            }, getActionDelay(0));
          }
        }, getActionDelay(0));
      }, getActionDelay(0));
    }

    // Step 1: Jika toko sudah terbuka, langsung proses. Jika belum, klik tombol buka toko.
    const existingSheet = document.querySelector('[data-testid="pancing-toko"]');
    if (existingSheet) {
      proceedInShop(existingSheet);
      return;
    }

    const btnBukaToko = document.querySelector('[data-testid="pancing-umpan"]');
    if (!btnBukaToko) {
      autoUmpanPending = false;
      return;
    }

    naturalClick(btnBukaToko);
    setTimeout(() => {
      const sheetToko = document.querySelector('[data-testid="pancing-toko"]');
      if (sheetToko) {
        proceedInShop(sheetToko);
      } else {
        autoUmpanPending = false;
      }
    }, getActionDelay(0));
  }

  function scheduleSwitchOwnedBait(preferredBaitId = null) {
    scheduleBaitShopAction({ preferredBaitId, allowBuy: false });
  }

  function scheduleAutoBuyUmpan(preferredBaitId = null) {
    scheduleBaitShopAction({ preferredBaitId, allowBuy: true });
  }

  // 2. Auto Upgrade Peralatan Paling Worth It (Joran & Pendingin) dengan Natural Human Jitter
  function scheduleAutoUpgrade() {
    if (autoUpgradePending || isSheetOpen()) return;
    const now = performance.now();
    // Cek upgrade berkala tiap 60 detik agar tidak mengganggu lemparan
    if (now - lastUpgradeCheckTime < 60000) return;
    lastUpgradeCheckTime = now;
    autoUpgradePending = true;

    const btnBukaKapal = document.querySelector('[data-testid="pancing-buka-kapal"]');
    if (!btnBukaKapal) {
      autoUpgradePending = false;
      return;
    }

    updateStatusMsg("⚓ Cek Upgrade...", "Membuka katalog joran...", "#a855f7");
    naturalClick(btnBukaKapal);

    // Step 1: Tunggu natural jitter hingga sheet kapal terbuka
    setTimeout(() => {
      const sheetKapal = document.querySelector('[data-testid="pancing-kapal"]');
      if (!sheetKapal) {
        autoUpgradePending = false;
        return;
      }

      // Step 2: Buka Tab Joran
      const tabJoran = sheetKapal.querySelector('[data-testid="pancing-tab-joran"]');
      if (!tabJoran) {
        const btnTutup = sheetKapal.querySelector('button[aria-label="Tutup"], button[class*="tutup"]');
        if (btnTutup) naturalClick(btnTutup);
        setTimeout(() => { autoUpgradePending = false; }, getActionDelay(0));
        return;
      }

      naturalClick(tabJoran);

      setTimeout(() => {
        // Step 3: Cari joran bernilai tinggi: Samudra (120k) -> Tonda (60k) -> Karang (30k)
        const btnBeliSamudra = sheetKapal.querySelector('[data-testid="pancing-joran-beli-joran-samudra"]');
        const btnBeliTonda = sheetKapal.querySelector('[data-testid="pancing-joran-beli-joran-tonda"]');
        const btnBeliKarang = sheetKapal.querySelector('[data-testid="pancing-joran-beli-joran-karang"]');

        let targetJoran = null;
        let namaJoran = "";
        let idJoran = "";

        if (btnBeliSamudra && !btnBeliSamudra.disabled && !upgradeFailedMap["joran-samudra"]) {
          targetJoran = btnBeliSamudra;
          namaJoran = "Joran Samudra (2x Ikan Raksasa)";
          idJoran = "joran-samudra";
        } else if (btnBeliTonda && !btnBeliTonda.disabled && !upgradeFailedMap["joran-tonda"]) {
          targetJoran = btnBeliTonda;
          namaJoran = "Joran Tonda (1.8x Ikan Cepat)";
          idJoran = "joran-tonda";
        } else if (btnBeliKarang && !btnBeliKarang.disabled && !upgradeFailedMap["joran-karang"]) {
          targetJoran = btnBeliKarang;
          namaJoran = "Joran Karang (1.8x Ikan Karang)";
          idJoran = "joran-karang";
        }

        if (targetJoran) {
          updateStatusMsg("✨ Auto-Upgrade!", `Membeli ${namaJoran}...`, "#a855f7");
          naturalClick(targetJoran);

          // Step 4: Pilih joran yang baru dibeli
          setTimeout(() => {
            const btnPilih = sheetKapal.querySelector(`[data-testid="pancing-joran-pilih-${idJoran}"]`);
            if (btnPilih && !btnPilih.disabled) {
              naturalClick(btnPilih);
              mancingStats.upgradeTerpasang.push(namaJoran);
            } else {
              // Pembelian gagal (misal koin belum cukup) -> tandai agar tidak spam coba lagi dan pakai joran terbaik
              upgradeFailedMap[idJoran] = true;
              const pilihSamudra = sheetKapal.querySelector('[data-testid="pancing-joran-pilih-joran-samudra"]');
              const pilihTonda = sheetKapal.querySelector('[data-testid="pancing-joran-pilih-joran-tonda"]');
              const pilihKarang = sheetKapal.querySelector('[data-testid="pancing-joran-pilih-joran-karang"]');

              if (pilihSamudra && !pilihSamudra.disabled) naturalClick(pilihSamudra);
              else if (pilihTonda && !pilihTonda.disabled) naturalClick(pilihTonda);
              else if (pilihKarang && !pilihKarang.disabled) naturalClick(pilihKarang);
            }

            // Step 5: Tutup sheet kapal
            setTimeout(() => {
              const btnTutup = sheetKapal.querySelector('button[aria-label="Tutup"], button[class*="tutup"]');
              if (btnTutup) naturalClick(btnTutup);
              setTimeout(() => {
                autoUpgradePending = false;
                updateMancingUI();
              }, getActionDelay(0));
            }, getActionDelay(0));
          }, getActionDelay(0));
        } else {
          // Jika joran sudah dibeli, pastikan joran terbaik yang dimiliki aktif dipakai
          const pilihSamudra = sheetKapal.querySelector('[data-testid="pancing-joran-pilih-joran-samudra"]');
          const pilihTonda = sheetKapal.querySelector('[data-testid="pancing-joran-pilih-joran-tonda"]');
          const pilihKarang = sheetKapal.querySelector('[data-testid="pancing-joran-pilih-joran-karang"]');

          if (pilihSamudra && !pilihSamudra.disabled && !pilihSamudra.getAttribute("aria-pressed")) {
            naturalClick(pilihSamudra);
          } else if (pilihTonda && !pilihTonda.disabled && !pilihTonda.getAttribute("aria-pressed")) {
            naturalClick(pilihTonda);
          } else if (pilihKarang && !pilihKarang.disabled && !pilihKarang.getAttribute("aria-pressed")) {
            naturalClick(pilihKarang);
          }

          // Cek Tab Tambahan (Pendingin: tambah kapasitas tas ikan untuk Max Cuan, sisakan minimal 10 koin untuk Umpan Cumi)
          const tabTambahan = sheetKapal.querySelector('[data-testid="pancing-tab-tambahan"]');
          const hasGoodRod = !!(
            (pilihSamudra && !pilihSamudra.disabled) ||
            (pilihTonda && !pilihTonda.disabled)
          );
          if (tabTambahan && hasGoodRod && pancingProfile.saldoKoin >= 10 && !upgradeFailedMap["pendingin"]) {
            setTimeout(() => {
              naturalClick(tabTambahan);
              setTimeout(() => {
                const btnPendingin = sheetKapal.querySelector('[data-testid="pancing-tambahan-beli-pendingin"]');
                if (btnPendingin && !btnPendingin.disabled) {
                  updateStatusMsg("❄️ Upgrade Pendingin!", "Menambah kapasitas tas ikan...", "#a855f7");
                  naturalClick(btnPendingin);
                  mancingStats.upgradeTerpasang.push("pendingin");
                }
                setTimeout(() => {
                  const btnTutup = sheetKapal.querySelector('button[aria-label="Tutup"], button[class*="tutup"]');
                  if (btnTutup) naturalClick(btnTutup);
                  setTimeout(() => {
                    autoUpgradePending = false;
                    fetchPancingData(true);
                  }, getActionDelay(0));
                }, getActionDelay(0));
              }, getActionDelay(0));
            }, getActionDelay(0));
          } else {
            // Tutup sheet kapal
            setTimeout(() => {
              const btnTutup = sheetKapal.querySelector('button[aria-label="Tutup"], button[class*="tutup"]');
              if (btnTutup) naturalClick(btnTutup);
              setTimeout(() => {
                autoUpgradePending = false;
              }, getActionDelay(0));
            }, getActionDelay(0));
          }
        }
      }, getActionDelay(0));
    }, getActionDelay(0));
  }

  let stopStatusOverride = null;

  async function toggleAutoMancing(forceState, customStopStatus = null) {
    const nextState = typeof forceState === "boolean" ? forceState : !mancingConfig.autoMancing;
    if (nextState) {
      stopStatusOverride = null;
      updateStatusMsg("🔄 Sinkronisasi Data...", "Mengambil data mancing hari ini...", "#38bdf8");
      await fetchPancingData(true);

      if (!pancingProfile.loaded) {
        mancingConfig.autoMancing = false;
        stopStatusOverride = {
          title: "⚠️ Status Mancing Belum Siap",
          detail: pancingProfile.loadError || "Gagal mengambil data /api/pancing. Muat ulang sebelum menyalakan fitur.",
          color: "#f59e0b"
        };
        updateMancingUI();
        return;
      }

      if (!mancingConfig.strategiUmpan) {
        mancingConfig.autoMancing = false;
        stopStatusOverride = {
          title: "⚠️ Pilih Strategi Dulu",
          detail: "Pilih strategi umpan di dropdown sebelum mulai memancing.",
          color: "#f59e0b"
        };
        updateMancingUI();
        return;
      }

      const sisaJual = Math.max(0, pancingProfile.jualMaks - pancingProfile.jualHariIni);
      const sisaTas = Math.max(0, pancingProfile.tasMaks - pancingProfile.tasIkan);
      const stopReason = evaluateStopRule(mancingConfig.stopRule, pancingProfile);

      if (stopReason) {
        stopStatusOverride = { ...stopReason, color: "#f59e0b" };
        mancingConfig.autoMancing = false;
        updateMancingUI();
        return;
      }

      if (sisaJual === 0) {
        updateStatusMsg(`ℹ️ Jatah Jual Habis (${pancingProfile.jualMaks}/${pancingProfile.jualMaks})`, `Tas: ${pancingProfile.tasIkan}/${pancingProfile.tasMaks}. Sisa ikan disimpan di tas untuk besok.`, "#f59e0b");
      } else if (sisaTas === 0) {
        updateStatusMsg(`⚠️ Tas Penuh (${pancingProfile.tasMaks}/${pancingProfile.tasMaks})!`, `Sisa kuota jual BUMDes: ${sisaJual} ekor. Ikan akan langsung dijual.`, "#eab308");
      } else {
        updateStatusMsg("✅ Siap Memancing!", `Hari ini: ${pancingProfile.lempar} celup. Sisa jual: ${sisaJual}, sisa tas: ${sisaTas}.`, "#22c55e");
      }
    } else {
      stopStatusOverride = customStopStatus;
      stopAutopilot();
      releaseGulung();
      resetReelCycle();
      strikePending = false;
      castPending = false;
      lootPending = false;
      autoUmpanPending = false;
      autoUpgradePending = false;
    }
    mancingConfig.autoMancing = nextState;
    updateMancingUI();
  }

  // Helper: Membuat HUD dapat digeser secara bebas (Free Move / Draggable) dan posisinya disimpan
  function makeDraggable(element, options = {}) {
    const {
      handle = element,
      storageKey = null
    } = options;

    if (!element || !handle) return;

    // 1. Pulihkan posisi tersimpan dari localStorage
    if (storageKey) {
      try {
        const raw = localStorage.getItem(storageKey);
        if (raw) {
          const pos = JSON.parse(raw);
          if (typeof pos.left === "number" && typeof pos.top === "number") {
            const winW = window.innerWidth || document.documentElement.clientWidth || 1024;
            const winH = window.innerHeight || document.documentElement.clientHeight || 768;
            const w = element.offsetWidth || 280;
            const h = element.offsetHeight || 50;
            const clampX = Math.max(0, Math.min(pos.left, Math.max(0, winW - w)));
            const clampY = Math.max(0, Math.min(pos.top, Math.max(0, winH - h)));
            element.style.left = `${clampX}px`;
            element.style.top = `${clampY}px`;
            element.style.right = "auto";
            element.style.bottom = "auto";
            element.style.transform = "none";
          }
        }
      } catch (_) {}
    }

    // 2. Jaga posisi agar tidak keluar layar saat ukuran jendela browser berubah
    window.addEventListener("resize", () => {
      if (element.style.left && element.style.left !== "") {
        const rect = element.getBoundingClientRect();
        const winW = window.innerWidth || document.documentElement.clientWidth || 1024;
        const winH = window.innerHeight || document.documentElement.clientHeight || 768;
        const maxLeft = Math.max(0, winW - rect.width);
        const maxTop = Math.max(0, winH - rect.height);
        const currentLeft = parseInt(element.style.left, 10);
        const currentTop = parseInt(element.style.top, 10);
        if (!isNaN(currentLeft) && !isNaN(currentTop)) {
          const clampedX = Math.max(0, Math.min(currentLeft, maxLeft));
          const clampedY = Math.max(0, Math.min(currentTop, maxTop));
          if (clampedX !== currentLeft) element.style.left = `${clampedX}px`;
          if (clampedY !== currentTop) element.style.top = `${clampedY}px`;
        }
      }
    });

    let isDragging = false;
    let startX = 0;
    let startY = 0;
    let initialElemX = 0;
    let initialElemY = 0;
    let hasMoved = false;

    handle.style.cursor = "grab";
    handle.style.touchAction = "none";

    // Double-click pada handle untuk reset posisi ke default
    handle.addEventListener("dblclick", (e) => {
      if (e.target.closest("button, input, select, textarea, a, [data-no-drag]")) return;
      if (storageKey) {
        try {
          localStorage.removeItem(storageKey);
        } catch (_) {}
      }
      element.style.left = "";
      element.style.top = "";
      element.style.right = "";
      element.style.bottom = "";
      element.style.transform = "";
    });

    handle.addEventListener("pointerdown", (e) => {
      if (e.target.closest("button, input, select, textarea, a, [data-no-drag]")) {
        return;
      }
      if (e.button !== 0) return;

      isDragging = true;
      hasMoved = false;
      startX = e.clientX;
      startY = e.clientY;

      const rect = element.getBoundingClientRect();
      initialElemX = rect.left;
      initialElemY = rect.top;

      try {
        handle.setPointerCapture(e.pointerId);
      } catch (_) {}

      element.dataset.prevTransition = element.style.transition || "";
      element.style.transition = "none";
      handle.style.cursor = "grabbing";
      document.body.style.userSelect = "none";
    });

    handle.addEventListener("pointermove", (e) => {
      if (!isDragging) return;

      const deltaX = e.clientX - startX;
      const deltaY = e.clientY - startY;

      if (!hasMoved && Math.hypot(deltaX, deltaY) > 3) {
        hasMoved = true;
      }

      if (!hasMoved) return;

      const rect = element.getBoundingClientRect();
      const newX = initialElemX + deltaX;
      const newY = initialElemY + deltaY;

      const winW = window.innerWidth || document.documentElement.clientWidth || 1024;
      const winH = window.innerHeight || document.documentElement.clientHeight || 768;
      const maxLeft = Math.max(0, winW - rect.width);
      const maxTop = Math.max(0, winH - rect.height);

      const clampX = Math.max(0, Math.min(newX, maxLeft));
      const clampY = Math.max(0, Math.min(newY, maxTop));

      element.style.left = `${clampX}px`;
      element.style.top = `${clampY}px`;
      element.style.right = "auto";
      element.style.bottom = "auto";
      element.style.transform = "none";
    });

    function endDrag(e) {
      if (!isDragging) return;
      isDragging = false;

      try {
        handle.releasePointerCapture(e.pointerId);
      } catch (_) {}

      element.style.transition = element.dataset.prevTransition || "";
      delete element.dataset.prevTransition;
      handle.style.cursor = "grab";
      document.body.style.userSelect = "";

      if (hasMoved) {
        const rect = element.getBoundingClientRect();
        if (storageKey) {
          try {
            localStorage.setItem(storageKey, JSON.stringify({
              left: Math.round(rect.left),
              top: Math.round(rect.top)
            }));
          } catch (_) {}
        }
        const suppressClick = (ev) => {
          ev.stopPropagation();
          ev.preventDefault();
          window.removeEventListener("click", suppressClick, true);
        };
        window.addEventListener("click", suppressClick, true);
        setTimeout(() => window.removeEventListener("click", suppressClick, true), 80);
      }
    }

    handle.addEventListener("pointerup", endDrag);
    handle.addEventListener("pointercancel", endDrag);
  }

  // UI HUD Auto-Mancing Pro (Compact Tabbed Dark Cyan Neon)
  function ensureMancingHudStyles() {
    if (document.getElementById("ks-mancing-hud-style")) return;
    const style = document.createElement("style");
    style.id = "ks-mancing-hud-style";
    style.textContent = `
      #ks-mancing-hud {
        position: fixed;
        top: 10px;
        right: 10px;
        width: 300px;
        max-height: calc(100vh - 20px);
        display: flex;
        flex-direction: column;
        background: linear-gradient(180deg, rgba(10, 18, 40, 0.96) 0%, rgba(8, 14, 32, 0.96) 100%);
        border: 1px solid rgba(0, 229, 255, 0.42);
        border-radius: 12px;
        color: #e2e8f0;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        font-size: 11px;
        z-index: 999999;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.58), 0 0 18px rgba(0, 229, 255, 0.22);
        backdrop-filter: blur(12px);
        overflow: hidden;
        transition: box-shadow 0.2s ease, border-color 0.2s ease;
        font-variant-numeric: tabular-nums;
      }
      #ks-mancing-hud * { box-sizing: border-box; }
      #ks-mancing-hud .ks-hd {
        background: linear-gradient(90deg, rgba(0, 229, 255, 0.16), rgba(14, 165, 233, 0.08));
        padding: 7px 10px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        border-bottom: 1px solid rgba(0, 229, 255, 0.22);
        cursor: grab;
        user-select: none;
        flex-shrink: 0;
      }
      #ks-mancing-hud .ks-title {
        font-weight: 800;
        color: #00e5ff;
        display: flex;
        align-items: center;
        gap: 5px;
        font-size: 11.5px;
        letter-spacing: 0.15px;
      }
      #ks-mancing-hud .ks-pill {
        font-size: 9px;
        font-weight: 700;
        padding: 1px 5px;
        border-radius: 999px;
        background: rgba(0, 229, 255, 0.16);
        border: 1px solid rgba(0, 229, 255, 0.35);
        color: #67e8f9;
      }
      #ks-mancing-hud .ks-icon-btn {
        background: rgba(15, 23, 42, 0.65);
        border: 1px solid rgba(56, 189, 248, 0.3);
        color: #93c5fd;
        cursor: pointer;
        font-size: 11px;
        font-weight: 700;
        padding: 2px 6px;
        border-radius: 6px;
        line-height: 1.2;
        transition: background 0.15s ease, border-color 0.15s ease;
      }
      #ks-mancing-hud .ks-icon-btn:hover {
        background: rgba(0, 229, 255, 0.2);
        border-color: rgba(0, 229, 255, 0.55);
      }
      #ks-mancing-hud .ks-hero {
        padding: 8px 9px 7px;
        background: rgba(15, 23, 42, 0.6);
        border-bottom: 1px solid rgba(56, 189, 248, 0.18);
        flex-shrink: 0;
      }
      #ks-mancing-hud .ks-status-card {
        background: rgba(8, 15, 34, 0.85);
        border: 1px solid rgba(56, 189, 248, 0.28);
        border-radius: 8px;
        padding: 6px 8px;
        margin-bottom: 6px;
      }
      #ks-mancing-hud .ks-bar-track {
        height: 5px;
        border-radius: 999px;
        background: rgba(148, 163, 184, 0.2);
        overflow: hidden;
      }
      #ks-mancing-hud .ks-bar-fill {
        height: 100%;
        width: 0%;
        border-radius: 999px;
        transition: width 0.08s linear, background-color 0.12s ease;
      }
      #ks-mancing-hud .ks-start-btn {
        width: 100%;
        padding: 7px 10px;
        border: none;
        color: #ffffff;
        border-radius: 8px;
        cursor: pointer;
        font-size: 11.5px;
        font-weight: 800;
        letter-spacing: 0.2px;
        transition: filter 0.15s ease, transform 0.08s ease;
      }
      #ks-mancing-hud .ks-start-btn:hover:not(:disabled) { filter: brightness(1.08); }
      #ks-mancing-hud .ks-start-btn:active:not(:disabled) { transform: scale(0.99); }
      #ks-mancing-hud .ks-tabs {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 4px;
        padding: 6px 9px;
        background: rgba(9, 15, 33, 0.72);
        border-bottom: 1px solid rgba(56, 189, 248, 0.18);
        flex-shrink: 0;
      }
      #ks-mancing-hud .ks-tab-btn {
        padding: 5px 4px;
        border-radius: 6px;
        border: 1px solid rgba(56, 189, 248, 0.18);
        background: rgba(15, 23, 42, 0.55);
        color: #94a3b8;
        font-size: 10px;
        font-weight: 700;
        cursor: pointer;
        white-space: nowrap;
        transition: all 0.15s ease;
      }
      #ks-mancing-hud .ks-tab-btn:hover {
        color: #e2e8f0;
        border-color: rgba(0, 229, 255, 0.4);
      }
      #ks-mancing-hud .ks-tab-btn[data-active="true"] {
        background: rgba(0, 229, 255, 0.18);
        border-color: rgba(0, 229, 255, 0.65);
        color: #00e5ff;
        box-shadow: 0 0 10px rgba(0, 229, 255, 0.16);
      }
      #ks-mancing-hud .ks-body {
        padding: 8px 9px;
        overflow-y: auto;
        flex: 1;
      }
      #ks-mancing-hud .ks-card {
        background: rgba(15, 23, 42, 0.76);
        border: 1px solid rgba(56, 189, 248, 0.22);
        border-radius: 8px;
        padding: 6px 8px;
        margin-bottom: 6px;
      }
      #ks-mancing-hud .ks-kpi-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 5px;
        margin-bottom: 6px;
      }
      #ks-mancing-hud .ks-kpi {
        background: rgba(15, 23, 42, 0.85);
        border: 1px solid rgba(56, 189, 248, 0.2);
        border-radius: 7px;
        padding: 5px 6px;
        text-align: center;
      }
      #ks-mancing-hud .ks-kpi-lbl {
        font-size: 9px;
        color: #94a3b8;
        display: block;
        margin-bottom: 1px;
      }
      #ks-mancing-hud .ks-kpi-val {
        font-size: 11px;
        font-weight: 800;
      }
      #ks-mancing-hud .ks-kv {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 6px;
        font-size: 10px;
        line-height: 1.45;
      }
      #ks-mancing-hud .ks-kv + .ks-kv {
        margin-top: 2px;
      }
      #ks-mancing-hud .ks-tpl-btn {
        padding: 5px 4px;
        border-radius: 6px;
        border: 1px solid rgba(56, 189, 248, 0.28);
        background: rgba(15, 23, 42, 0.85);
        color: #cbd5e1;
        font-size: 10px;
        font-weight: 700;
        cursor: pointer;
        white-space: nowrap;
        transition: all 0.14s ease;
      }
      #ks-mancing-hud .ks-tpl-btn:hover:not(:disabled) {
        border-color: rgba(0, 229, 255, 0.55);
        color: #ffffff;
      }
      #ks-mancing-hud .ks-select {
        padding: 4px 5px;
        border-radius: 6px;
        border: 1px solid rgba(56, 189, 248, 0.36);
        background: rgba(9, 15, 33, 0.92);
        color: #e2e8f0;
        font-size: 10px;
        cursor: pointer;
      }
      #ks-mancing-hud .ks-chk-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 5px 6px;
        font-size: 10px;
        color: #cbd5e1;
      }
      #ks-mancing-hud .ks-chk {
        display: flex;
        align-items: center;
        gap: 4px;
        cursor: pointer;
        padding: 2px 3px;
        border-radius: 5px;
      }
      #ks-mancing-hud .ks-chk:hover {
        background: rgba(56, 189, 248, 0.08);
      }
      #ks-mancing-hud .ks-chk input {
        margin: 0;
        accent-color: #00e5ff;
        cursor: pointer;
      }
      #ks-mancing-hud .ks-scroll::-webkit-scrollbar { width: 5px; }
      #ks-mancing-hud .ks-scroll::-webkit-scrollbar-track { background: rgba(15, 23, 42, 0.4); }
      #ks-mancing-hud .ks-scroll::-webkit-scrollbar-thumb { background: rgba(0, 229, 255, 0.32); border-radius: 999px; }
    `;
    document.head.appendChild(style);
  }

  function createMancingHUD() {
    if (document.getElementById("ks-mancing-hud")) return;
    ensureMancingHudStyles();

    const hud = document.createElement("div");
    hud.id = "ks-mancing-hud";

    hud.innerHTML = `
      <div id="ks-mancing-header" class="ks-hd">
        <div class="ks-title">
          <span style="opacity: 0.7; font-size: 12px;" title="Geser Posisi HUD (Klik &amp; Geser Bebas)">⠿</span>
          <span>🎣 Auto-Mancing</span>
          <span id="ks-mode-pill" class="ks-pill">Natural</span>
        </div>
        <div style="display: flex; align-items: center; gap: 4px;">
          <button type="button" id="ks-mancing-mini-win" class="ks-icon-btn" title="Buka di Mini Window (460×680) — jangan diminimize agar tidak putus/lepas" style="color: #5eead4; border-color: rgba(45, 212, 191, 0.45); background: rgba(13, 148, 136, 0.25);">📌</button>
          <button type="button" id="ks-mancing-toggle" class="ks-icon-btn" title="Lipat / Buka Panel">_</button>
        </div>
      </div>

      <div id="ks-mancing-content" style="display: flex; flex-direction: column; overflow: hidden; flex: 1;">
        <!-- Pinned Hero: Live Status / Tension & Start/Stop (Selalu Terlihat di Semua Tab) -->
        <div class="ks-hero">
          <div class="ks-status-card">
            <div style="display: flex; justify-content: space-between; align-items: center; gap: 6px;">
              <div id="ks-mancing-status" style="font-size: 11.5px; font-weight: 800; color: #38bdf8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                ⚪ Siap Memancing
              </div>
              <span id="ks-mancing-live-badge" style="font-size: 9px; font-weight: 700; color: #64748b; flex-shrink: 0;">IDLE</span>
            </div>
            <div id="ks-mancing-detail" style="font-size: 9.8px; color: #94a3b8; margin-top: 2px; line-height: 1.3;">
              Tekan tombol Mulai untuk otomatisasi
            </div>
            <div id="ks-mancing-reel-bars" style="display: none; margin-top: 5px; padding-top: 5px; border-top: 1px solid rgba(56, 189, 248, 0.16);">
              <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px;">
                <div>
                  <div style="display: flex; justify-content: space-between; font-size: 9px; color: #94a3b8; margin-bottom: 2px;">
                    <span>Tali</span><b id="ks-reel-tension-val" style="color: #22c55e;">0%</b>
                  </div>
                  <div class="ks-bar-track"><div id="ks-reel-tension-bar" class="ks-bar-fill" style="background: #22c55e;"></div></div>
                </div>
                <div>
                  <div style="display: flex; justify-content: space-between; font-size: 9px; color: #94a3b8; margin-bottom: 2px;">
                    <span>Ikan</span><b id="ks-reel-progress-val" style="color: #00e5ff;">0%</b>
                  </div>
                  <div class="ks-bar-track"><div id="ks-reel-progress-bar" class="ks-bar-fill" style="background: #00e5ff;"></div></div>
                </div>
              </div>
            </div>
          </div>

          <button type="button" id="ks-mancing-start-btn" class="ks-start-btn" style="background: linear-gradient(90deg, #16a34a, #22c55e); box-shadow: 0 4px 12px rgba(22, 163, 74, 0.35);">
            ▶️ Mulai Auto Mancing Natural
          </button>
        </div>

        <!-- 3-Tab Switcher: Main | Riwayat | Settings -->
        <div class="ks-tabs" role="tablist">
          <button type="button" id="ks-tab-main" data-tab="main" data-active="true" role="tab" class="ks-tab-btn">🎯 Main</button>
          <button type="button" id="ks-tab-history" data-tab="history" data-active="false" role="tab" class="ks-tab-btn">📜 Riwayat</button>
          <button type="button" id="ks-tab-settings" data-tab="settings" data-active="false" role="tab" class="ks-tab-btn">⚙️ Settings</button>
        </div>

        <!-- Tab Panels -->
        <div class="ks-body ks-scroll">
          <!-- PANEL 1: MAIN (Compact, Zero-Scroll) -->
          <div id="ks-panel-main" data-panel="main">
            <!-- 1-Click Templates -->
            <div class="ks-card" style="background: rgba(14, 165, 233, 0.08); border-color: rgba(0, 229, 255, 0.26);">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
                <span style="font-weight: 800; color: #67e8f9; font-size: 10px;">🎯 Template</span>
                <span id="ks-tpl-badge" style="font-size: 9.5px; color: #94a3b8; font-weight: 700;">Pilih preset</span>
              </div>
              <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px;">
                <button type="button" id="ks-tpl-just-go" data-template="just-go" class="ks-tpl-btn" title="Preset Just Go: pilih umpan &amp; gaya Celup/Lempar sendiri, full Jual Semua.">🚀 Just Go</button>
                <button type="button" id="ks-tpl-cumi" data-template="cumi" class="ks-tpl-btn" title="Preset Langsung Cumi: langsung ke laut dalam ≥25m (Celup), full Jual Semua.">🦑 Cumi</button>
                <button type="button" id="ks-tpl-ternak" data-template="ternak-ikan" class="ks-tpl-btn" title="Preset Ternak Umpan: Cacing di dangkal (2–10m) kumpul 5 umpan-ikan (2.3×), lalu Celup di ≥25m &amp; Jual Semua.">🐟 Ternak</button>
              </div>
              <!-- Inline Options untuk Just Go (hanya tampil saat Just Go aktif) -->
              <div id="ks-just-go-opts" style="display: none; margin-top: 6px; padding-top: 5px; border-top: 1px solid rgba(0, 229, 255, 0.16); gap: 4px; align-items: center;">
                <select id="ks-justgo-umpan" class="ks-select" title="Pilih umpan untuk mode Just Go (Auto Umpan juga membeli umpan ini)." style="flex: 1; min-width: 0;">
                  <option value="umpan-cacing">🪱 Cacing</option>
                  <option value="umpan-udang">🦐 Udang</option>
                  <option value="umpan-cumi" selected>🦑 Cumi</option>
                  <option value="umpan-ikan">🐟 Ikan</option>
                </select>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 3px; flex-shrink: 0;">
                  <button type="button" id="ks-justgo-mode-celup" data-cast-mode="celup" class="ks-tpl-btn" title="Mode Celup: turunkan kail lurus ke bawah (ikan besar di laut dalam)." style="padding: 4px 6px; font-size: 9.5px;">⬇️ Celup</button>
                  <button type="button" id="ks-justgo-mode-lempar" data-cast-mode="lempar" class="ks-tpl-btn" title="Mode Lempar: lempar kail jauh (ikan kecil–sedang)." style="padding: 4px 6px; font-size: 9.5px;">🎣 Lempar</button>
                </div>
              </div>
              <div id="ks-tpl-desc" style="font-size: 9.3px; color: #94a3b8; margin-top: 4px; line-height: 1.3;">
                Pilih template di atas untuk langsung mengisi Settings.
              </div>
            </div>

            <!-- Sonar & Plan -->
            <div class="ks-card" style="background: rgba(14, 165, 233, 0.1); border-color: rgba(0, 229, 255, 0.28);">
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="color: #38bdf8; font-weight: 700; font-size: 10px;">📡 Sonar</span>
                <b id="ks-mancing-sonar-info" style="color: #4ade80; font-size: 10.5px;">Membaca...</b>
              </div>
              <div id="ks-mancing-ramai-spots" style="font-size: 9.3px; color: #cbd5e1; margin-top: 4px;">
                🗺️ Spot Ramai: Memuat peta...
              </div>
              <div id="ks-mancing-plan" style="font-size: 9.5px; color: #cbd5e1; margin-top: 5px; padding-top: 4px; border-top: 1px solid rgba(0, 229, 255, 0.16); line-height: 1.35;">
                📋 Plan: Menunggu status...
              </div>
            </div>

            <!-- 3 Quick KPIs -->
            <div class="ks-kpi-grid">
              <div class="ks-kpi">
                <span class="ks-kpi-lbl">🎣 Celup</span>
                <span id="ks-stat-hari-ini" class="ks-kpi-val" style="color: #38bdf8;">...</span>
              </div>
              <div class="ks-kpi">
                <span class="ks-kpi-lbl">🎒 Tas</span>
                <span id="ks-stat-tas" class="ks-kpi-val" style="color: #4ade80;">...</span>
              </div>
              <div class="ks-kpi">
                <span class="ks-kpi-lbl">💰 Jual</span>
                <span id="ks-stat-jual" class="ks-kpi-val" style="color: #fbbf24;">...</span>
              </div>
            </div>

            <!-- Gear & Profit Summary -->
            <div class="ks-card" style="margin-bottom: 0;">
              <div class="ks-kv">
                <span style="color: #94a3b8;">🪙 Koin · Joran</span>
                <span style="text-align: right;"><b id="ks-stat-saldo" style="color: #f1f5f9;">...</b> · <b id="ks-stat-joran" style="color: #c084fc;">...</b></span>
              </div>
              <div class="ks-kv">
                <span style="color: #94a3b8;">🪱 Umpan</span>
                <b id="ks-stat-umpan" style="color: #fde047;">Memuat...</b>
              </div>
              <div class="ks-kv">
                <span style="color: #94a3b8;">⛵ Kapal</span>
                <b id="ks-stat-kapal" style="color: #67e8f9; text-align: right;">Memuat...</b>
              </div>
              <div id="ks-stat-fitur-row" class="ks-kv" style="display: none;">
                <span style="color: #94a3b8;">🧰 Fitur</span>
                <b id="ks-stat-fitur-kapal" style="color: #cbd5e1;">-</b>
              </div>
              <div id="ks-main-profit-row" title="Klik untuk buka tab Riwayat" style="display: flex; justify-content: space-between; align-items: center; margin-top: 5px; padding-top: 5px; border-top: 1px solid rgba(255, 255, 255, 0.08); cursor: pointer;">
                <span style="font-size: 10px; color: #cbd5e1;">Hari Ini: <b id="ks-mancing-count" style="color: #4ade80;">0 ekor</b></span>
                <span id="ks-mancing-profit" style="color: #4ade80; font-weight: 800; font-size: 10.5px;">💰 +0.00 koin</span>
              </div>
            </div>
          </div>

          <!-- PANEL 2: RIWAYAT (Full Daily Log) -->
          <div id="ks-panel-history" data-panel="history" style="display: none;">
            <div class="ks-kpi-grid">
              <div class="ks-kpi">
                <span class="ks-kpi-lbl">🐟 Dapat</span>
                <span id="ks-hist-catches" class="ks-kpi-val" style="color: #4ade80;">0</span>
              </div>
              <div class="ks-kpi">
                <span class="ks-kpi-lbl">⚠️ Gagal</span>
                <span id="ks-hist-losses" class="ks-kpi-val" style="color: #f87171;">0</span>
              </div>
              <div class="ks-kpi">
                <span class="ks-kpi-lbl">💰 Laba</span>
                <span id="ks-hist-profit" class="ks-kpi-val" style="color: #4ade80;">+0.00</span>
              </div>
            </div>
            <div id="ks-mancing-last" class="ks-card" style="margin-bottom: 0; padding: 6px 7px;">
              <div style="color: #94a3b8; font-weight: 600; font-size: 10px;">Riwayat Hari Ini: -</div>
            </div>
          </div>

          <!-- PANEL 3: SETTINGS (Clean & Always Expanded Inside Tab) -->
          <div id="ks-panel-settings" data-panel="settings" style="display: none;">
            <div class="ks-card">
              <div style="display: flex; align-items: center; gap: 5px; margin-bottom: 4px;">
                <span style="color: #94a3b8; width: 32px; flex-shrink: 0; font-size: 10px;">Stop</span>
                <select id="ks-opt-stop-rule" class="ks-select" title="Tentukan kapan Auto-Mancing berhenti otomatis." style="flex: 1;">
                  <option value="all-full" selected>🏆 Jual + Tas Penuh (50/50)</option>
                  <option value="sell-full">💰 Jatah Jual Habis (30/30)</option>
                  <option value="bait-empty">🪱 Umpan Habis</option>
                </select>
              </div>
              <div id="ks-settings-summary" style="font-size: 9.3px; color: #94a3b8; line-height: 1.3;">
                ↳ Jadikan umpan bila ada, selain itu Jual · stop 50/50 penuh.
              </div>
            </div>

            <!-- 7 Core Checkboxes (Zero-Loss selalu aktif & digabung ke deskripsi Auto Gulung) -->
            <div class="ks-card">
              <div class="ks-chk-grid">
                <label class="ks-chk" title="Berlaku di semua aksi: Celup/Lempar (jeda 2.2–3.8s), Sentak (220–380ms), Gulung (acak 29–45% ⇄ 70–85%), Loot (1.4–2.5s), dan koordinat klik acak.">
                  <input type="checkbox" id="ks-opt-natural" checked>
                  <span>🌿 Natural</span>
                </label>
                <label class="ks-chk" title="Izinkan menyimpan ikan ke Tas saat tidak langsung dijual (mis. nilai ≤ modal umpan atau setelah kuota jual habis).">
                  <input type="checkbox" id="ks-opt-simpan" checked>
                  <span>🎒 Auto Simpan</span>
                </label>
                <label class="ks-chk" title="Otomatis menurunkan/melempar kail (Celup di laut dalam, atau Lempar sesuai pilihan Just Go / Ternak).">
                  <input type="checkbox" id="ks-opt-celup" checked>
                  <span>⬇️ Auto Celup</span>
                </label>
                <label class="ks-chk" title="Otomatis mengemudikan kapal ke spot Ramai (target 5/5 bar) dengan kedalaman terbaik &amp; anti-batas area.">
                  <input type="checkbox" id="ks-opt-auto-navigasi" checked>
                  <span>🧭 Autopilot</span>
                </label>
                <label class="ks-chk" title="Otomatis menyentak kail begitu ikan menyambar (jauh di bawah batas waktu 10 detik server).">
                  <input type="checkbox" id="ks-opt-sentak" checked>
                  <span>⚡ Auto Sentak</span>
                </label>
                <label class="ks-chk" title="Otomatis buang sampah laut (Sandal jepit) dan jual ikan jika tas penuh saat kuota jual masih ada.">
                  <input type="checkbox" id="ks-opt-jual-penuh" checked>
                  <span>🪙 Jual/Sampah</span>
                </label>
                <label class="ks-chk" style="grid-column: 1 / -1;" title="Otomatis menggulung (29–45% ⇄ 70–85% pada Mode Natural) + Zero-Loss aktif permanen: lepas segera di ≥82%/zona merah (anti-putus), anti-kendur ≤15%, dan pulih otomatis bila blur melepas gulungan.">
                  <input type="checkbox" id="ks-opt-gulung" checked>
                  <span>🔄 Auto Gulung <span style="font-size: 9px; color: #67e8f9; opacity: 0.9;">(Zero-Loss aktif)</span></span>
                </label>
              </div>

              <!-- Opt-in Belanja & Fitur Kapal -->
              <div class="ks-chk-grid" style="margin-top: 6px; padding-top: 5px; border-top: 1px solid rgba(255,255,255,0.08);">
                <label id="ks-opt-auto-umpan-wrap" class="ks-chk" title="Opt-in (default mati): otomatis membeli umpan yang sedang dipilih saat stok habis (khusus mode Ternak selalu membeli Cacing Laut).">
                  <input type="checkbox" id="ks-opt-auto-umpan">
                  <span style="color: #fde68a;">🛒 Auto Umpan</span>
                </label>
                <label class="ks-chk" title="Opt-in (default mati): otomatis membeli upgrade Joran terbaik (Samudra → Tonda → Karang) dan Kotak Pendingin (+slot tas) saat koin cukup.">
                  <input type="checkbox" id="ks-opt-auto-upgrade">
                  <span style="color: #f3e8ff;">🎣 Auto Upgrade</span>
                </label>
                <label id="ks-opt-jaring-lampu-wrap" class="ks-chk" title="Otomatis tebar Jaring untuk umpan gratis harian &amp; nyalakan Lampu Kapal saat malam (18.30–04.30)." style="grid-column: 1 / -1;">
                  <input type="checkbox" id="ks-opt-jaring-lampu" checked>
                  <span style="color: #86efac;">🕸️ Auto Jaring &amp; Lampu Malam</span>
                </label>
              </div>
            </div>

            <div style="font-size: 9.2px; color: #64748b; text-align: center;">
              Tekan <b>Esc</b> kapan saja untuk berhenti · Biarkan Mini Window tetap terlihat
            </div>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(hud);

    makeDraggable(hud, {
      handle: document.getElementById("ks-mancing-header"),
      storageKey: "ks_hud_pos_mancing"
    });

    function setActiveHudTab(tabKey, persist = true) {
      const nextTab = VALID_TABS.has(tabKey) ? tabKey : "main";
      mancingConfig.activeTab = nextTab;
      ["main", "history", "settings"].forEach((key) => {
        const tabBtn = document.getElementById(`ks-tab-${key}`);
        const panel = document.getElementById(`ks-panel-${key}`);
        const isActive = key === nextTab;
        if (tabBtn) tabBtn.setAttribute("data-active", isActive ? "true" : "false");
        if (panel) panel.style.display = isActive ? "block" : "none";
      });
      if (persist) saveMancingSettings();
    }

    ["main", "history", "settings"].forEach((key) => {
      const tabBtn = document.getElementById(`ks-tab-${key}`);
      if (tabBtn) tabBtn.onclick = () => setActiveHudTab(key, true);
    });

    const mainProfitRow = document.getElementById("ks-main-profit-row");
    if (mainProfitRow) {
      mainProfitRow.onclick = () => setActiveHudTab("history", true);
    }

    let minimized = false;
    document.getElementById("ks-mancing-toggle").onclick = () => {
      minimized = !minimized;
      document.getElementById("ks-mancing-content").style.display = minimized ? "none" : "flex";
      document.getElementById("ks-mancing-toggle").textContent = minimized ? "□" : "_";
    };

    const btnMiniWin = document.getElementById("ks-mancing-mini-win");
    if (btnMiniWin) {
      btnMiniWin.onclick = () => {
        const popupWin = window.open(
          window.location.href,
          "ks-mancing-mini",
          "popup=yes,width=460,height=680,left=40,top=40"
        );
        if (!popupWin) {
          updateStatusMsg("⚠️ Popup Diblokir", "Izinkan pop-up atau klik 'Mancing Mini Window' di icon ekstensi.", "#f59e0b");
        }
      };
    }

    document.getElementById("ks-mancing-start-btn").onclick = () => {
      if (!pancingProfile.loaded) {
        if (!pancingProfile.loading) {
          fetchPancingData(true);
        }
        return;
      }
      toggleAutoMancing();
    };

    function syncHudControlsFromConfig() {
      const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.value = String(val); };
      const setChk = (id, val) => { const el = document.getElementById(id); if (el) el.checked = Boolean(val); };

      setVal("ks-opt-stop-rule", mancingConfig.stopRule);
      setVal("ks-justgo-umpan", mancingConfig.justGoUmpan);

      setChk("ks-opt-natural", mancingConfig.modeNatural);
      setChk("ks-opt-auto-umpan", mancingConfig.autoUmpan);
      setChk("ks-opt-auto-upgrade", mancingConfig.autoUpgrade);
      setChk("ks-opt-jaring-lampu", mancingConfig.autoJaring || mancingConfig.autoLampu);
      setChk("ks-opt-auto-navigasi", mancingConfig.autoNavigasi);
      setChk("ks-opt-celup", mancingConfig.autoCelup);
      setChk("ks-opt-sentak", mancingConfig.autoSentak);
      setChk("ks-opt-gulung", mancingConfig.autoGulung);
      setChk("ks-opt-simpan", mancingConfig.autoSimpan);
      setChk("ks-opt-jual-penuh", mancingConfig.autoJualTasPenuh || mancingConfig.autoJualSampah);

      const modePill = document.getElementById("ks-mode-pill");
      if (modePill) modePill.textContent = mancingConfig.modeNatural ? "Natural" : "Cepat";
      setActiveHudTab(mancingConfig.activeTab, false);
    }

    function applyTemplatePreset(templateKey) {
      const preset = MANCING_TEMPLATES[templateKey];
      if (!preset) return;
      Object.assign(mancingConfig, preset);
      if (templateKey === "just-go") {
        if (!VALID_JUSTGO_UMPAN.has(mancingConfig.justGoUmpan)) {
          mancingConfig.justGoUmpan = getEquippedUmpanType() || "umpan-cumi";
        }
        mancingConfig.preferredUmpan = mancingConfig.justGoUmpan;
      }
      mancingConfig.lootMode = "jual-semua";
      mancingConfig.zeroLossGuard = true;
      mancingConfig.selectiveRelease = false;
      mancingConfig.templateCustom = false;
      stopStatusOverride = null;
      syncHudControlsFromConfig();
      saveMancingSettings();
      updateMancingUI();
    }

    function markSettingsCustomized() {
      if (mancingConfig.strategiUmpan) {
        mancingConfig.templateCustom = true;
      }
      mancingConfig.zeroLossGuard = true;
      mancingConfig.lootMode = "jual-semua";
      const modePill = document.getElementById("ks-mode-pill");
      if (modePill) modePill.textContent = mancingConfig.modeNatural ? "Natural" : "Cepat";
      saveMancingSettings();
      updateMancingUI();
    }

    syncHudControlsFromConfig();

    document.getElementById("ks-tpl-just-go").onclick = () => {
      if (!pancingProfile.loaded) return;
      applyTemplatePreset("just-go");
    };
    document.getElementById("ks-tpl-cumi").onclick = () => {
      if (!pancingProfile.loaded) return;
      applyTemplatePreset("cumi");
    };
    document.getElementById("ks-tpl-ternak").onclick = () => {
      if (!pancingProfile.loaded) return;
      applyTemplatePreset("ternak-ikan");
    };

    const justGoUmpanSel = document.getElementById("ks-justgo-umpan");
    if (justGoUmpanSel) {
      justGoUmpanSel.onchange = (e) => {
        if (VALID_JUSTGO_UMPAN.has(e.target.value)) {
          mancingConfig.justGoUmpan = e.target.value;
          mancingConfig.preferredUmpan = e.target.value;
          stopStatusOverride = null;
          saveMancingSettings();
          updateMancingUI();
        }
      };
    }
    const btnJustGoCelup = document.getElementById("ks-justgo-mode-celup");
    if (btnJustGoCelup) {
      btnJustGoCelup.onclick = () => {
        if (!pancingProfile.loaded) return;
        mancingConfig.justGoCastMode = "celup";
        saveMancingSettings();
        updateMancingUI();
      };
    }
    const btnJustGoLempar = document.getElementById("ks-justgo-mode-lempar");
    if (btnJustGoLempar) {
      btnJustGoLempar.onclick = () => {
        if (!pancingProfile.loaded) return;
        mancingConfig.justGoCastMode = "lempar";
        saveMancingSettings();
        updateMancingUI();
      };
    }

    document.getElementById("ks-opt-natural").onchange = (e) => {
      mancingConfig.modeNatural = e.target.checked;
      markSettingsCustomized();
    };
    document.getElementById("ks-opt-stop-rule").onchange = (e) => {
      if (VALID_STOP_RULES.has(e.target.value)) {
        mancingConfig.stopRule = e.target.value;
        stopStatusOverride = null;
        markSettingsCustomized();
      }
    };
    document.getElementById("ks-opt-auto-umpan").onchange = (e) => {
      mancingConfig.autoUmpan = e.target.checked;
      markSettingsCustomized();
    };
    document.getElementById("ks-opt-auto-upgrade").onchange = (e) => {
      mancingConfig.autoUpgrade = e.target.checked;
      markSettingsCustomized();
    };
    document.getElementById("ks-opt-jaring-lampu").onchange = (e) => {
      mancingConfig.autoJaring = e.target.checked;
      mancingConfig.autoLampu = e.target.checked;
      markSettingsCustomized();
    };
    document.getElementById("ks-opt-auto-navigasi").onchange = (e) => {
      mancingConfig.autoNavigasi = e.target.checked;
      markSettingsCustomized();
    };
    document.getElementById("ks-opt-celup").onchange = (e) => {
      mancingConfig.autoCelup = e.target.checked;
      markSettingsCustomized();
    };
    document.getElementById("ks-opt-sentak").onchange = (e) => {
      mancingConfig.autoSentak = e.target.checked;
      markSettingsCustomized();
    };
    document.getElementById("ks-opt-gulung").onchange = (e) => {
      mancingConfig.autoGulung = e.target.checked;
      markSettingsCustomized();
    };
    document.getElementById("ks-opt-simpan").onchange = (e) => {
      mancingConfig.autoSimpan = e.target.checked;
      markSettingsCustomized();
    };
    document.getElementById("ks-opt-jual-penuh").onchange = (e) => {
      mancingConfig.autoJualTasPenuh = e.target.checked;
      mancingConfig.autoJualSampah = e.target.checked;
      markSettingsCustomized();
    };

    // Ambil data profil harian awal begitu HUD terpasang
    fetchPancingData(false);
  }

  function updateMancingUI() {
    const btn = document.getElementById("ks-mancing-start-btn");
    const countEl = document.getElementById("ks-mancing-count");
    const lastEl = document.getElementById("ks-mancing-last");
    const statusEl = document.getElementById("ks-mancing-status");
    const hud = document.getElementById("ks-mancing-hud");
    const sonarInfoEl = document.getElementById("ks-mancing-sonar-info");

    const statHariIniEl = document.getElementById("ks-stat-hari-ini");
    const statTasEl = document.getElementById("ks-stat-tas");
    const statJualEl = document.getElementById("ks-stat-jual");
    const statSaldoEl = document.getElementById("ks-stat-saldo");
    const statKapalEl = document.getElementById("ks-stat-kapal");
    const statFiturKapalEl = document.getElementById("ks-stat-fitur-kapal");
    const statJoranEl = document.getElementById("ks-stat-joran");
    const statUmpanEl = document.getElementById("ks-stat-umpan");

    if (pancingProfile.loaded) {
      if (statHariIniEl) {
        statHariIniEl.textContent = `${pancingProfile.lempar}`;
      }
      if (statTasEl) {
        statTasEl.textContent = `${pancingProfile.tasIkan}/${pancingProfile.tasMaks}`;
        statTasEl.style.color = pancingProfile.tasIkan >= pancingProfile.tasMaks ? "#ef4444" : "#4ade80";
      }
      if (statJualEl) {
        const sisaJual = Math.max(0, pancingProfile.jualMaks - pancingProfile.jualHariIni);
        statJualEl.textContent = `${pancingProfile.jualHariIni}/${pancingProfile.jualMaks}`;
        statJualEl.style.color = sisaJual === 0 ? "#f59e0b" : "#fbbf24";
      }
      if (statSaldoEl) {
        statSaldoEl.textContent = `${pancingProfile.saldoKoin.toFixed(2)} koin`;
      }
      if (statKapalEl) {
        const jarakText = pancingProfile.lepasM > 0 ? `+${pancingProfile.lepasM}m lepas` : "Teluk (0m lepas)";
        statKapalEl.textContent = `${pancingProfile.kapalNama} · ${jarakText}`;
      }
      if (statFiturKapalEl) {
        const fiturRow = document.getElementById("ks-stat-fitur-row");
        const hasAnyFeature = Boolean(pancingProfile.hasJaring || pancingProfile.hasLampu);
        if (fiturRow) fiturRow.style.display = hasAnyFeature ? "flex" : "none";
        const jaringText = pancingProfile.hasJaring
          ? `Jaring ${pancingProfile.jaringSisa}/${pancingProfile.jaringHarian}`
          : "";
        const lampuText = pancingProfile.hasLampu ? "Lampu Ada" : "";
        statFiturKapalEl.textContent = [jaringText, lampuText].filter(Boolean).join(" · ") || "Tanpa Fitur";
        statFiturKapalEl.style.color = hasAnyFeature ? "#4ade80" : "#94a3b8";
      }
      if (statJoranEl) {
        statJoranEl.textContent = pancingProfile.joranNama || pancingProfile.joranId;
      }
      if (statUmpanEl) {
        const activeType = getEquippedUmpanType();
        const labelMap = {
          "umpan-ikan": "Ikan Kecil Hidup",
          "umpan-cumi": "Potongan Cumi",
          "umpan-udang": "Udang Hidup",
          "umpan-cacing": "Cacing Laut"
        };
        const apiEntry = Array.isArray(pancingProfile.umpanList)
          ? pancingProfile.umpanList.find(u => u.id === activeType)
          : null;
        const domStok = getUmpanStok();
        const stok = domStok >= 0 ? domStok : (apiEntry?.stok ?? 0);
        const nama = apiEntry?.nama || labelMap[activeType] || activeType;
        statUmpanEl.textContent = `${nama} (${stok})`;
        statUmpanEl.style.color = stok <= 0 ? "#ef4444" : "#fde047";
      }
    }

    if (sonarInfoEl) {
      const sonar = getSonarData();
      sonarInfoEl.textContent = formatSonarText(sonar);
    }
    renderSonarRamaiSpots();

    renderMancingPlan();

    if (hud) {
      const jaringWrap = document.getElementById("ks-opt-jaring-lampu-wrap");
      const noBoatExtras = pancingProfile.loaded && !pancingProfile.hasJaring && !pancingProfile.hasLampu;
      if (jaringWrap) {
        jaringWrap.style.display = noBoatExtras ? "none" : "flex";
      }

      const featureInputs = hud.querySelectorAll('input[type="checkbox"], select');
      featureInputs.forEach((input) => {
        const noBoatSupport = input.id === "ks-opt-jaring-lampu" && noBoatExtras;
        const locked = !pancingProfile.loaded || noBoatSupport;
        input.disabled = locked;
        if (noBoatSupport) input.checked = false;
        if (input.parentElement) {
          if (input.tagName === "SELECT") {
            input.style.opacity = locked ? "0.55" : "1";
            input.style.cursor = locked ? "not-allowed" : "pointer";
          } else {
            input.parentElement.style.opacity = locked ? "0.55" : "1";
            input.parentElement.style.cursor = locked ? "not-allowed" : "pointer";
          }
        }
      });

      const justGoOpts = document.getElementById("ks-just-go-opts");
      if (justGoOpts) {
        justGoOpts.style.display = mancingConfig.strategiUmpan === "just-go" ? "flex" : "none";
      }
      const justGoCastButtons = [
        { el: document.getElementById("ks-justgo-mode-celup"), key: "celup" },
        { el: document.getElementById("ks-justgo-mode-lempar"), key: "lempar" }
      ];
      justGoCastButtons.forEach(({ el, key }) => {
        if (!el) return;
        const active = mancingConfig.justGoCastMode === key;
        el.disabled = !pancingProfile.loaded;
        el.style.opacity = !pancingProfile.loaded ? "0.55" : "1";
        el.style.cursor = !pancingProfile.loaded ? "not-allowed" : "pointer";
        el.style.background = active ? "rgba(0, 229, 255, 0.22)" : "rgba(15, 23, 42, 0.85)";
        el.style.borderColor = active ? "#00e5ff" : "rgba(56, 189, 248, 0.28)";
        el.style.color = active ? "#ffffff" : "#94a3b8";
      });

      const tplButtons = [
        { el: document.getElementById("ks-tpl-just-go"), key: "just-go" },
        { el: document.getElementById("ks-tpl-cumi"), key: "cumi" },
        { el: document.getElementById("ks-tpl-ternak"), key: "ternak-ikan" }
      ];
      tplButtons.forEach(({ el, key }) => {
        if (!el) return;
        const active = mancingConfig.strategiUmpan === key;
        el.disabled = !pancingProfile.loaded;
        el.style.opacity = !pancingProfile.loaded ? "0.55" : "1";
        el.style.cursor = !pancingProfile.loaded ? "not-allowed" : "pointer";
        el.style.background = active ? "rgba(0, 229, 255, 0.22)" : "rgba(15, 23, 42, 0.85)";
        el.style.borderColor = active
          ? "#00e5ff"
          : (!mancingConfig.strategiUmpan ? "#f59e0b" : "rgba(56, 189, 248, 0.28)");
        el.style.color = active ? "#ffffff" : "#cbd5e1";
        el.style.boxShadow = active ? "0 0 10px rgba(0, 229, 255, 0.18)" : "none";
      });

      const tplBadge = document.getElementById("ks-tpl-badge");
      const tplDesc = document.getElementById("ks-tpl-desc");
      if (tplBadge) {
        if (!mancingConfig.strategiUmpan) {
          tplBadge.textContent = "Wajib pilih";
          tplBadge.style.color = "#f59e0b";
        } else {
          const baseName = mancingConfig.strategiUmpan === "just-go"
            ? "Just Go"
            : mancingConfig.strategiUmpan === "cumi"
            ? "Cumi"
            : "Ternak Umpan";
          tplBadge.textContent = mancingConfig.templateCustom ? `${baseName} · Custom` : `${baseName} ✓`;
          tplBadge.style.color = mancingConfig.templateCustom ? "#fbbf24" : "#4ade80";
        }
      }
      if (tplDesc) {
        if (mancingConfig.strategiUmpan === "just-go") {
          const baitLabel = getUmpanShortName(mancingConfig.justGoUmpan);
          const castLabel = mancingConfig.justGoCastMode === "lempar" ? "Lempar" : "Celup";
          tplDesc.textContent = `↳ ${baitLabel} · ${castLabel} · Jual Semua (> modal umpan).`;
        } else if (mancingConfig.strategiUmpan === "cumi") {
          tplDesc.textContent = "↳ Langsung pakai Cumi ke ≥25m (Celup · Jual Semua).";
        } else if (mancingConfig.strategiUmpan === "ternak-ikan") {
          tplDesc.textContent = "↳ Cacing dangkal (2–10m) ➔ kumpul 5 umpan-ikan ➔ ≥25m (2.3×).";
        } else {
          tplDesc.textContent = "Pilih template di atas untuk langsung mengisi Settings.";
        }
      }

      const stopRuleSel = document.getElementById("ks-opt-stop-rule");
      const maxSell = pancingProfile.jualMaks || 30;
      const maxTotal = maxSell + (pancingProfile.tasMaks || 20);
      if (stopRuleSel) {
        const optAll = stopRuleSel.querySelector('option[value="all-full"]');
        const optSell = stopRuleSel.querySelector('option[value="sell-full"]');
        if (optAll) optAll.textContent = `🏆 Jual + Tas Penuh (${maxTotal}/${maxTotal})`;
        if (optSell) optSell.textContent = `💰 Jatah Jual Habis (${maxSell}/${maxSell})`;
      }

      const summaryEl = document.getElementById("ks-settings-summary");
      if (summaryEl) {
        const lootText = "Jadikan umpan bila ada, selain itu Jual";
        const stopText = mancingConfig.stopRule === "sell-full"
          ? `stop ${maxSell}/${maxSell} jual`
          : mancingConfig.stopRule === "bait-empty"
          ? "lanjut sampai umpan habis"
          : `stop ${maxTotal}/${maxTotal} penuh`;
        summaryEl.textContent = `↳ ${lootText} · ${stopText}.`;
      }

      const autoUmpanWrap = document.getElementById("ks-opt-auto-umpan-wrap");
      if (autoUmpanWrap) {
        const buyBaitName = mancingConfig.strategiUmpan === "ternak-ikan"
          ? "Cacing Laut"
          : getUmpanShortName(getActiveSelectedBait());
        autoUmpanWrap.title = mancingConfig.strategiUmpan === "ternak-ikan"
          ? "Opt-in (default mati): khusus mode Ternak selalu membeli Cacing Laut saat stok habis."
          : `Opt-in (default mati): otomatis membeli umpan terpilih (${buyBaitName}) saat stok habis.`;
      }
    }

    if (btn) {
      if (!pancingProfile.loaded) {
        if (pancingProfile.loading) {
          btn.disabled = true;
          btn.textContent = "⏳ Memuat Status Mancing...";
          btn.style.background = "#475569";
          btn.style.boxShadow = "none";
          btn.style.cursor = "not-allowed";
          updateStatusMsg("🔄 Mengambil Status...", "Membaca data /api/pancing sebelum fitur aktif...", "#38bdf8");
        } else if (pancingProfile.loadError) {
          btn.disabled = false;
          btn.textContent = "🔄 Muat Ulang Status Mancing";
          btn.style.background = "#d97706";
          btn.style.boxShadow = "0 4px 12px rgba(217, 119, 6, 0.35)";
          btn.style.cursor = "pointer";
          updateStatusMsg("⚠️ Gagal Memuat Status", pancingProfile.loadError, "#f59e0b");
        } else {
          btn.disabled = true;
          btn.textContent = "⏳ Menunggu Status...";
          btn.style.background = "#475569";
          btn.style.boxShadow = "none";
          btn.style.cursor = "not-allowed";
        }
      } else if (!mancingConfig.strategiUmpan && !mancingConfig.autoMancing) {
        btn.disabled = true;
        btn.textContent = "⚠️ Pilih Template Dulu";
        btn.style.background = "#475569";
        btn.style.boxShadow = "none";
        btn.style.cursor = "not-allowed";
        updateStatusMsg("⚠️ Pilih Template Mancing", "Klik template Just Go, Cumi, atau Ternak sebelum mulai.", "#f59e0b");
      } else if (mancingConfig.autoMancing) {
        btn.disabled = false;
        btn.style.cursor = "pointer";
        btn.textContent = "⏹ STOP Auto Mancing";
        btn.style.background = "#ef4444";
        btn.style.boxShadow = "0 4px 12px rgba(239, 68, 68, 0.45)";
        if (hud) hud.style.boxShadow = "0 8px 32px rgba(0, 0, 0, 0.55), 0 0 24px rgba(34, 197, 94, 0.45)";
      } else {
        btn.disabled = false;
        btn.style.cursor = "pointer";
        btn.textContent = "▶️ Mulai Auto Mancing Natural";
        btn.style.background = "linear-gradient(90deg, #16a34a, #22c55e)";
        btn.style.boxShadow = "0 4px 12px rgba(22, 163, 74, 0.35)";
        if (hud) hud.style.boxShadow = "0 8px 32px rgba(0, 0, 0, 0.55), 0 0 16px rgba(0, 229, 255, 0.25)";
        if (stopStatusOverride) {
          updateStatusMsg(stopStatusOverride.title, stopStatusOverride.detail, stopStatusOverride.color);
        } else if (statusEl) {
          updateStatusMsg("⚪ Siap Memancing", "Status terhubung. Tekan tombol Mulai untuk otomatisasi.", "#38bdf8");
        }
      }
    }

    const liveBadge = document.getElementById("ks-mancing-live-badge");
    if (liveBadge) {
      liveBadge.textContent = mancingConfig.autoMancing ? "● LIVE" : "IDLE";
      liveBadge.style.color = mancingConfig.autoMancing ? "#4ade80" : "#64748b";
    }

    const modePill = document.getElementById("ks-mode-pill");
    if (modePill) {
      modePill.textContent = mancingConfig.modeNatural ? "Natural" : "Cepat";
    }

    const tabHistBtn = document.getElementById("ks-tab-history");
    if (tabHistBtn) {
      tabHistBtn.textContent = mancingStats.history.length > 0
        ? `📜 Riwayat (${mancingStats.history.length})`
        : "📜 Riwayat";
    }
    const tabSetBtn = document.getElementById("ks-tab-settings");
    if (tabSetBtn) {
      tabSetBtn.textContent = mancingConfig.templateCustom ? "⚙️ Settings •" : "⚙️ Settings";
    }

    const todayCatches = pancingProfile.loaded
      ? Math.max(pancingProfile.dapat || 0, mancingStats.catches)
      : mancingStats.catches;
    if (countEl) {
      countEl.textContent = `${todayCatches} ekor`;
    }
    const histCatchesEl = document.getElementById("ks-hist-catches");
    if (histCatchesEl) histCatchesEl.textContent = `${todayCatches}`;
    const histLossesEl = document.getElementById("ks-hist-losses");
    if (histLossesEl) histLossesEl.textContent = `${mancingStats.losses}`;

    if (lastEl) {
      if (mancingStats.history.length > 0) {
        const itemsHtml = mancingStats.history.map((entry) => {
          if (typeof entry === "string") {
            return `<li style="margin: 3px 0; color: #e2e8f0;">${escapeHtml(entry)}</li>`;
          }
          if (entry && entry.text) {
            return `<li style="margin: 3px 0; color: #e2e8f0;">${escapeHtml(entry.text)}</li>`;
          }
          const profitVal = typeof entry.profit === "number" ? entry.profit : 0;
          const profitColor = profitVal >= 0 ? "#4ade80" : "#f87171";
          const profitSign = profitVal >= 0 ? "+" : "";
          const sellVal = typeof entry.sellPrice === "number" ? entry.sellPrice.toFixed(2) : "0.00";
          const weightPart = entry.weight ? ` <span style="color:#94a3b8;">(${escapeHtml(entry.weight)})</span>` : "";
          const badgeStyle = entry.isLoss
            ? "background:rgba(239,68,68,0.22);color:#fca5a5;"
            : "background:rgba(0,229,255,0.16);color:#67e8f9;";
          const actionPart = entry.action
            ? `<span style="${badgeStyle}padding:1px 5px;border-radius:4px;font-size:8.8px;font-weight:700;flex-shrink:0;">${escapeHtml(entry.action)}</span>`
            : "";
          return `<li style="display:flex;justify-content:space-between;align-items:center;gap:6px;padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.06);line-height:1.3;color:#f1f5f9;font-size:9.8px;">` +
            `<div style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"><b>${escapeHtml(entry.name || "Ikan")}</b>${weightPart}</div>` +
            `<div style="display:flex;align-items:center;gap:4px;flex-shrink:0;"><span style="color:#fbbf24;">${sellVal}</span><b style="color:${profitColor};">${profitSign}${profitVal.toFixed(2)}</b>${actionPart}</div>` +
          `</li>`;
        }).join("");
        lastEl.innerHTML =
          `<div style="color: #94a3b8; font-weight: 700; font-size: 9.8px; margin-bottom: 4px;">🐟 Riwayat Hari Ini (${mancingStats.history.length})</div>` +
          `<ul class="ks-scroll" style="margin: 0; padding: 0; max-height: 250px; overflow-y: auto; list-style: none;">${itemsHtml}</ul>`;
      } else {
        lastEl.innerHTML = `<div style="color: #94a3b8; font-weight: 600; font-size: 10px; text-align: center; padding: 14px 0;">Belum ada riwayat tangkapan hari ini</div>`;
      }
    }

    const profitEl = document.getElementById("ks-mancing-profit");
    const histProfitEl = document.getElementById("ks-hist-profit");
    const p = mancingStats.totalProfit;
    const sign = p >= 0 ? "+" : "";
    const pColor = p >= 0 ? "#4ade80" : "#f87171";
    if (profitEl) {
      profitEl.textContent = `💰 ${sign}${p.toFixed(2)} koin`;
      profitEl.style.color = pColor;
    }
    if (histProfitEl) {
      histProfitEl.textContent = `${sign}${p.toFixed(2)}`;
      histProfitEl.style.color = pColor;
    }
  }

  function renderMancingPlan() {
    const planEl = document.getElementById("ks-mancing-plan");
    if (!planEl) return;

    if (!pancingProfile.loaded) {
      planEl.innerHTML = "📋 <b>Plan:</b> Memuat status `/api/pancing`...";
      return;
    }

    if (!mancingConfig.strategiUmpan) {
      planEl.innerHTML = "📋 <b>Plan:</b> Pilih template (Just Go / Cumi / Ternak) dulu.";
      return;
    }

    const equipped = getEquippedUmpanType();
    const stok = getUmpanStok();
    const sonar = getSonarData();
    const target = getTargetDepth();
    const umpanIkanStok = getOwnedBaitStock("umpan-ikan");
    const batchTarget = getTernakBatchTarget();

    const lootStepLabel = "Jual Semua";

    if (mancingConfig.strategiUmpan === "just-go") {
      const selectedBait = getActiveSelectedBait();
      const activeName = getUmpanShortName(selectedBait);
      const castLabel = mancingConfig.justGoCastMode === "lempar" ? "Lempar" : "Celup";
      const g1Done = equipped === selectedBait && stok > 0;
      const g2Done = g1Done && sonar.depth >= target.minDepth && (target.maxDepth == null || sonar.depth <= target.maxDepth) && sonar.crowd !== "Sepi";
      const activeJustGo = !g1Done ? 1 : !g2Done ? 2 : 3;
      const markG = (n, done) => (done ? "✅" : activeJustGo === n ? "▶️" : "⚪");

      planEl.innerHTML =
        `<div><b>📋 Plan Just Go (${escapeHtml(activeName)} · ${castLabel}):</b></div>` +
        `<div>${markG(1, g1Done)} 1. ${escapeHtml(activeName)} (${Math.max(0, getOwnedBaitStock(selectedBait))}) · ${markG(2, g2Done)} 2. Ke ≥${target.minDepth}m (5/5) · ${markG(3, false)} 3. ${castLabel} &amp; ${lootStepLabel}</div>`;
      return;
    }

    if (mancingConfig.strategiUmpan === "ternak-ikan") {
      const s1Done = (equipped === "umpan-cacing" && stok > 0) || (equipped === "umpan-ikan" && stok > 0);
      const s2Done = (equipped === "umpan-ikan" && stok > 0) || umpanIkanStok >= batchTarget;
      const s3Done = equipped === "umpan-ikan" && sonar.depth >= target.minDepth && sonar.crowd !== "Sepi";
      const activeStep = !s1Done ? 1 : !s2Done ? 2 : !s3Done ? 3 : 4;
      const mark = (n, done) => (done ? "✅" : activeStep === n ? "▶️" : "⚪");
      const step1Label = mancingConfig.autoUmpan ? "1. Pakai/Beli Cacing" : "1. Pakai Cacing";

      planEl.innerHTML =
        `<div><b>📋 Plan Ternak Umpan:</b></div>` +
        `<div>${mark(1, s1Done)} ${step1Label} · ${mark(2, s2Done)} 2. Kumpul Ikan (${umpanIkanStok}/${batchTarget})</div>` +
        `<div>${mark(3, s3Done)} 3. Ke ≥25m (5/5) · ${mark(4, false)} 4. Celup 2.3× &amp; ${lootStepLabel}</div>`;
      return;
    }

    const c1Done = stok > 0;
    const c2Done = c1Done && sonar.depth >= target.minDepth && sonar.crowd !== "Sepi";
    const activeCumi = !c1Done ? 1 : !c2Done ? 2 : 3;
    const markC = (n, done) => (done ? "✅" : activeCumi === n ? "▶️" : "⚪");

    planEl.innerHTML =
      `<div><b>📋 Plan Langsung Cumi:</b></div>` +
      `<div>${markC(1, c1Done)} 1. Siap Cumi · ${markC(2, c2Done)} 2. Ke ≥25m (5/5) · ${markC(3, false)} 3. Celup &amp; ${lootStepLabel}</div>`;
  }

  function updateReelMiniBars(reelState = null) {
    const wrap = document.getElementById("ks-mancing-reel-bars");
    if (!wrap) return;
    if (!reelState) {
      if (wrap.style.display !== "none") wrap.style.display = "none";
      return;
    }
    if (wrap.style.display !== "block") wrap.style.display = "block";
    const tVal = Math.max(0, Math.min(100, Number(reelState.tension) || 0));
    const pVal = Math.max(0, Math.min(100, Number(reelState.progress) || 0));
    const tColor = reelState.color || "#22c55e";
    const tBar = document.getElementById("ks-reel-tension-bar");
    const tTxt = document.getElementById("ks-reel-tension-val");
    const pBar = document.getElementById("ks-reel-progress-bar");
    const pTxt = document.getElementById("ks-reel-progress-val");
    if (tBar) { tBar.style.width = `${tVal.toFixed(0)}%`; tBar.style.backgroundColor = tColor; }
    if (tTxt) { tTxt.textContent = `${tVal.toFixed(0)}%`; tTxt.style.color = tColor; }
    if (pBar) { pBar.style.width = `${pVal.toFixed(0)}%`; }
    if (pTxt) { pTxt.textContent = `${pVal.toFixed(0)}%`; }
  }

  function updateStatusMsg(title, detail, color = "#38bdf8", reelState = null) {
    const statusEl = document.getElementById("ks-mancing-status");
    const detailEl = document.getElementById("ks-mancing-detail");
    if (statusEl) {
      statusEl.textContent = title;
      statusEl.style.color = color;
    }
    if (detailEl && detail) {
      detailEl.textContent = detail;
    }
    updateReelMiniBars(reelState);
    renderMancingPlan();
  }

  function isNightHourFromChip() {
    const jamEl = document.querySelector('[data-testid="pancing-jam"]');
    if (!jamEl) return false;
    const text = (jamEl.textContent || "").toLowerCase();
    if (text.includes("malam")) return true;
    const m = text.match(/(\d{1,2})\.(\d{2})/);
    if (!m) return false;
    const mins = parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
    // Lampu kapal efektif pukul 18.30 (1110) sampai 04.30 (270)
    return mins >= 1110 || mins < 270;
  }

  function checkBoatProfitTools() {
    const now = performance.now();

    // 1. Auto-Jaring: tangkap umpan gratis bila kapal punya jaring & tidak cooldown
    if (mancingConfig.autoJaring && pancingProfile.hasJaring && now - lastJaringTime > 4000) {
      const btnJaring = document.querySelector('[data-testid="pancing-jaring"]');
      if (btnJaring && !btnJaring.disabled && !btnJaring.getAttribute("aria-busy")) {
        lastJaringTime = now;
        mancingStats.jaringUsed++;
        updateStatusMsg("🕸️ Tebar Jaring!", "Menangkap umpan gratis harian...", "#22c55e");
        naturalClick(btnJaring);
        return true;
      }
    }

    // 2. Auto-Lampu Malam: nyalakan lampu kapal saat malam jika kapal punya lampu
    if (mancingConfig.autoLampu && pancingProfile.hasLampu && now - lastLampuCheckTime > 5000) {
      lastLampuCheckTime = now;
      const btnLampu = document.querySelector('[data-testid="pancing-lampu"]');
      if (btnLampu) {
        const isNight = isNightHourFromChip();
        const isPressed = btnLampu.getAttribute("aria-pressed") === "true";
        if (isNight && !isPressed) {
          naturalClick(btnLampu);
          return true;
        }
      }
    }

    // 3. Guard 1-Joran Hemat Umpan: 2+ joran menghabiskan 2x-3x umpan per celup
    if (mancingConfig.singleRodProfit && now - lastKailCheckTime > 2000) {
      const btnKail = document.querySelector('[data-testid="pancing-kail"]');
      if (btnKail) {
        const bEl = btnKail.querySelector("b");
        const activeRods = bEl ? parseInt(bEl.textContent.trim(), 10) : 1;
        if (!isNaN(activeRods) && activeRods > 1) {
          lastKailCheckTime = now;
          naturalClick(btnKail);
          return true;
        }
      }
    }

    return false;
  }

  // Loop Eksekusi Auto-Mancing (40ms)
  setInterval(() => {
    if (!isMancingPage()) {
      const hud = document.getElementById("ks-mancing-hud");
      if (hud) hud.remove();
      return;
    }

    createMancingHUD();

    const layar = document.querySelector('[data-testid="pancing"]');
    if (!layar) return;

    const fase = layar.getAttribute("data-fase") || "jalan";
    const hasilCard = document.querySelector('[data-testid="pancing-hasil"]');

    // Passive tracker fase lemparan (fallback bila umpan dimakan / ikan lepas tanpa memunculkan kartu hasil)
    if (fase === "tunggu" || fase === "sambar" || fase === "tarik") {
      if (!activeCastState || activeCastState.closed) {
        const resolvedCastBait =
          (lastApiCastBait && performance.now() - lastApiCastBait.at < 30000 ? lastApiCastBait.baitType : "") ||
          getEquippedUmpanType();
        wasHiddenDuringCast = Boolean(document.hidden);
        activeCastState = {
          baitType: resolvedCastBait,
          lastPhase: fase,
          seenInWater: true,
          caught: false,
          lossRecorded: false,
          closed: false
        };
      } else {
        activeCastState.lastPhase = fase;
        activeCastState.seenInWater = true;
        if (document.hidden) wasHiddenDuringCast = true;
      }
    } else if (hasilCard || fase === "dapat") {
      if (activeCastState) {
        activeCastState.caught = true;
        activeCastState.closed = true;
      }
      wasHiddenDuringCast = false;
    } else if ((fase === "jalan" || fase === "diam") && activeCastState && !activeCastState.closed) {
      const endedCast = activeCastState;
      endedCast.closed = true;
      if (endedCast.seenInWater && !endedCast.caught && !endedCast.lossRecorded) {
        setTimeout(() => {
          if (endedCast.caught || endedCast.lossRecorded) return;
          if (document.querySelector('[data-testid="pancing-hasil"]')) return;
          const curFase = document.querySelector('[data-testid="pancing"]')?.getAttribute("data-fase") || "";
          if (curFase === "tunggu" || curFase === "sambar" || curFase === "tarik" || curFase === "dapat") return;
          const reason =
            endedCast.lastPhase === "tarik"
              ? "lepas"
              : endedCast.lastPhase === "sambar"
              ? "telat_sentak"
              : "dimakan";
          recordBaitLoss({ reason, umpan: endedCast.baitType });
        }, 450);
      }
    }

    if (!mancingConfig.autoMancing) return;

    // 1. Fase Tangkapan Selesai (Hasil Ikan)
    if (hasilCard || fase === "dapat") {
      strikePending = false;
      releaseGulung();
      resetReelCycle();
      stopAutopilot();
      updateStatusMsg("🎉 Ikan Tertangkap!", "Menyimpan ke tas atau menjual...", "#22c55e");
      if (hasilCard) {
        handleCatch(hasilCard);
      }
      return;
    }

    // 2. Fase Sambar (Ikan Menyambar Umpan!)
    if (fase === "sambar") {
      releaseGulung();
      resetReelCycle();
      stopAutopilot();
      updateStatusMsg("⚡ DISAMBAR!", "Menyentak kail alami...", "#f59e0b");
      if (mancingConfig.autoSentak) {
        scheduleNaturalSentak();
      }
      return;
    }

    // 3. Fase Tarik (Adu Tarik / Reel Battle)
    if (fase === "tarik") {
      strikePending = false;
      stopAutopilot();
      // Lepas fokus dari checkbox/select HUD agar focusin tidak memicu a5.current = false di game
      const activeEl = document.activeElement;
      if (activeEl && activeEl.closest && activeEl.closest("#ks-mancing-hud") && typeof activeEl.blur === "function") {
        activeEl.blur();
      }
      if (mancingConfig.autoGulung) {
        const barTali = document.querySelector('[data-testid="pancing-bar-tali"]');
        const barIkan = document.querySelector('[data-testid="pancing-bar-ikan"]');
        const btnGulung = document.querySelector('[data-testid="pancing-gulung"]');
        const isRed = barTali ? barTali.hasAttribute("data-merah") : false;
        const isYellow = barTali ? barTali.hasAttribute("data-kuning") : false;
        const isHolding = !!(btnGulung && btnGulung.hasAttribute("data-tahan"));
        const tension = barTali ? parseFloat(barTali.style.width) || 0 : 0;
        const progress = barIkan ? parseFloat(barIkan.style.width) || 0 : 0;

        // Hysteresis Long-Hold + Proteksi Anti-Putus (segera lepas di >=82% / zona merah tanpa tunggu 160ms,
        // karena surge 1.9x pada ikan sulit 5 naik 85%->100% dalam 135ms) + Proteksi Anti-Kendur (<=15% paksa gulung
        // jauh di atas batas lepas 4% selama 3.2s) + Auto-Recovery bila window.blur melepas a5.current.
        const nowReel = performance.now();
        if (isRed) {
          if (!redDangerSince) redDangerSince = nowReel;
        } else {
          redDangerSince = 0;
        }
        const effectiveMax = mancingConfig.zeroLossGuard ? Math.min(reelTargetMax, 82) : reelTargetMax;
        const redGuardTriggered = mancingConfig.zeroLossGuard && (isRed || tension >= 82);
        const slackGuardTriggered = !isRed && tension <= 15;
        const hitCeiling = tension >= effectiveMax || redGuardTriggered;

        if (hitCeiling) {
          if (!reelCoolingDown) {
            reelCoolingDown = true;
            reelTargetMin = rollReelMin();
          }
          releaseGulung();
        } else if (slackGuardTriggered) {
          // Anti-Kendur: paksa gulung ulang segera agar tidak pernah mendekati zona lepas (<4%)
          if (reelCoolingDown) {
            reelCoolingDown = false;
            reelTargetMax = rollReelMax();
          }
          if (!isGulungActive || !isHolding) {
            isGulungActive = false;
            holdGulung();
          }
        } else if (reelCoolingDown) {
          const safeToHold = !(mancingConfig.zeroLossGuard && isRed);
          if (safeToHold && tension <= reelTargetMin) {
            reelCoolingDown = false;
            reelTargetMax = rollReelMax();
            holdGulung();
          } else {
            releaseGulung();
          }
        } else {
          // Sedang dalam fase tahan panjang (menuju effectiveMax): pulihkan segera bila blur/focusin melepas data-tahan
          if (!isGulungActive || !isHolding) {
            isGulungActive = false;
            holdGulung();
          }
        }

        const color = isRed ? "#ef4444" : isYellow ? "#eab308" : "#22c55e";
        const stateText = isRed
          ? "(BAHAYA: Melepas)"
          : slackGuardTriggered
          ? "(ANTI-KENDUR: Gulung!)"
          : reelCoolingDown
          ? `(Melepas ➔ ${reelTargetMin}%)`
          : `(Tahan Panjang ➔ ${effectiveMax}%)`;
        updateStatusMsg(
          `🔄 Adu Tarik: Ikan ${progress.toFixed(0)}%`,
          `Tegangan: ${tension.toFixed(0)}% ${stateText}`,
          color,
          { tension, progress, color }
        );
      }
      return;
    }

    // 4. Fase Jalan / Diam (Siap Menurunkan Kail / Celup)
    if (fase === "jalan" || fase === "diam") {
      strikePending = false;
      releaseGulung();
      resetReelCycle();

      // 4a. Jika ada jendela sheet (toko / kapal / tas) sedang terbuka di layar, JANGAN CELUP KAIL!
      if (isSheetOpen()) {
        stopAutopilot();
        const sheetToko = document.querySelector('[data-testid="pancing-toko"]');
        if (sheetToko && !autoUmpanPending && mancingConfig.autoUmpan && getUmpanStok() <= 0) {
          scheduleAutoBuyUmpan();
        }
        return;
      }

      // 4b. Cek jika proses loot hasil, lempar kail, auto umpan, atau upgrade sedang berlangsung
      if (lootPending || castPending || autoUmpanPending || autoUpgradePending) {
        stopAutopilot();
        return;
      }

      // 4b-2. Stop Rule Guard: berhenti otomatis sesuai aturan pilihan (40/40, 20/20 Jual, atau lanjut sampai umpan habis)
      const stopReason = evaluateStopRule(mancingConfig.stopRule, pancingProfile);
      if (stopReason) {
        toggleAutoMancing(false, stopReason);
        return;
      }

      // 4b-3. Alat Profit Kapal (Jaring Umpan Gratis, Lampu Malam, 1-Joran Hemat)
      if (checkBoatProfitTools()) {
        stopAutopilot();
        return;
      }

      // 4c. Cek stok umpan aktif sebelum berlayar: kalau sudah ada umpan (> 0), jangan beli lagi!
      const stokUmpan = getUmpanStok();
      const bodyText = document.body ? document.body.innerText : "";
      const isUmpanHabis = stokUmpan === 0 || (stokUmpan < 0 && bodyText.includes("habis. Beli dulu"));

      if (isUmpanHabis) {
        // Jika umpan terakhir baru saja dilempar (<3 detik), tunggu fase berpindah ke 'tunggu' dulu
        // supaya ikan terakhir tetap diselesaikan sampai selesai (sentak -> gulung -> jual/simpan) baru berhenti.
        if (lastCelupTime > 0 && performance.now() - lastCelupTime < 3000) {
          stopAutopilot();
          updateStatusMsg("🎣 Umpan Terakhir...", "Menunggu lemparan terakhir masuk ke air...", "#38bdf8");
          return;
        }
        stopAutopilot();

        // Prioritaskan ganti gratis ke umpan terpilih yang masih dimiliki:
        const umpanIkanStok = getOwnedBaitStock("umpan-ikan");
        const cacingStok = getOwnedBaitStock("umpan-cacing");
        const selectedBait = getActiveSelectedBait();
        if (mancingConfig.strategiUmpan === "just-go") {
          if (getOwnedBaitStock(selectedBait) > 0) {
            scheduleSwitchOwnedBait(selectedBait);
            return;
          }
          if (selectedBait === "umpan-ikan") {
            toggleAutoMancing(false, {
              title: "⚠️ Stok Umpan Ikan Habis!",
              detail: "Ikan Kecil Hidup tidak bisa dibeli di toko. Pilih Cacing/Udang/Cumi di Just Go atau pakai template Ternak.",
              color: "#f59e0b"
            });
            return;
          }
        } else if (mancingConfig.strategiUmpan === "ternak-ikan") {
          if (umpanIkanStok > 0) {
            scheduleSwitchOwnedBait("umpan-ikan");
            return;
          }
          if (cacingStok > 0) {
            scheduleSwitchOwnedBait("umpan-cacing");
            return;
          }
        } else if (getOwnedBaitStock(selectedBait) > 0) {
          scheduleSwitchOwnedBait(selectedBait);
          return;
        }

        if (mancingConfig.autoUmpan) {
          scheduleAutoBuyUmpan(selectedBait);
          return;
        }

        toggleAutoMancing(false, {
          title: "⚠️ Umpan Habis!",
          detail: `Umpan terakhir selesai & stok ${getUmpanShortName(selectedBait)} 0. Aktifkan Auto Umpan atau beli manual di toko.`,
          color: "#f59e0b"
        });
        return;
      }

      // 4c-1. Sinkronisasi Umpan untuk Just Go & Cumi: pastikan umpan yang dipasang sesuai pilihan pengguna
      if (mancingConfig.strategiUmpan === "just-go" || mancingConfig.strategiUmpan === "cumi") {
        const desiredBait = getActiveSelectedBait();
        const equippedNow = getEquippedUmpanType();
        if (desiredBait && equippedNow !== desiredBait) {
          stopAutopilot();
          const desiredStok = getOwnedBaitStock(desiredBait);
          if (desiredStok > 0) {
            updateStatusMsg("🪱 Ganti Umpan Terpilih...", `Memasang ${getUmpanShortName(desiredBait)} (${desiredStok})...`, "#22c55e");
            scheduleSwitchOwnedBait(desiredBait);
          } else if (mancingConfig.autoUmpan && desiredBait !== "umpan-ikan") {
            updateStatusMsg("🛒 Beli Umpan Terpilih...", `Membeli ${getUmpanShortName(desiredBait)}...`, "#22c55e");
            scheduleAutoBuyUmpan(desiredBait);
          } else {
            toggleAutoMancing(false, {
              title: `⚠️ Stok ${getUmpanShortName(desiredBait)} Kosong!`,
              detail: desiredBait === "umpan-ikan"
                ? "Ikan Kecil Hidup kosong & tidak dijual di toko. Pilih umpan lain atau pakai template Ternak."
                : `Aktifkan Auto Umpan atau beli ${getUmpanShortName(desiredBait)} manual di toko.`,
              color: "#f59e0b"
            });
          }
          return;
        }
      }

      // 4c-2. Sinkronisasi Umpan Mode Ternak Ikan (ganti antar stok milik sendiri; beli cacing hanya jika Auto Beli Umpan aktif):
      // - Jika sedang pakai cumi/udang pada mode ternak-ikan, pindah ke umpan-ikan (jika >= batch / cacing 0) atau cacing
      // - Jika sedang pakai cacing di dangkal dan umpan-ikan sudah terkumpul >= batchTarget (5 / sisaSlot), pindah ke umpan-ikan & berlayar ke >=30m
      if (mancingConfig.strategiUmpan === "ternak-ikan" && mancingConfig.autoUmpanIkan) {
        const equippedNow = getEquippedUmpanType();
        const umpanIkanStok = getOwnedBaitStock("umpan-ikan");
        const cacingStok = getOwnedBaitStock("umpan-cacing");
        const batchTarget = getTernakBatchTarget();

        if (equippedNow !== "umpan-ikan" && equippedNow !== "umpan-cacing") {
          stopAutopilot();
          if (umpanIkanStok >= batchTarget || (cacingStok <= 0 && umpanIkanStok > 0)) {
            updateStatusMsg("🐟 Mode Ternak Umpan...", `Memasang ${umpanIkanStok} umpan-ikan milikmu...`, "#22c55e");
            scheduleSwitchOwnedBait("umpan-ikan");
          } else if (cacingStok > 0) {
            updateStatusMsg("🪱 Mode Ternak Umpan...", `Memasang Cacing Laut (${cacingStok}) untuk ternak umpan-ikan...`, "#22c55e");
            scheduleSwitchOwnedBait("umpan-cacing");
          } else if (mancingConfig.autoUmpan) {
            updateStatusMsg("🛒 Mode Ternak Umpan...", "Membeli Cacing Laut untuk ternak umpan-ikan...", "#22c55e");
            scheduleAutoBuyUmpan();
          } else {
            toggleAutoMancing(false, {
              title: "⚠️ Stok Cacing & Umpan Ikan Kosong!",
              detail: "Aktifkan Auto Beli Umpan atau beli Cacing Laut manual di toko untuk menjalankan mode Ternak Umpan Ikan.",
              color: "#f59e0b"
            });
          }
          return;
        }
        if (equippedNow === "umpan-cacing" && umpanIkanStok >= batchTarget) {
          stopAutopilot();
          updateStatusMsg("🐟 Batch Umpan Siap!", `${umpanIkanStok} umpan-ikan terkumpul — ganti umpan & berlayar ke ≥25m...`, "#22c55e");
          scheduleSwitchOwnedBait("umpan-ikan");
          return;
        }
      }

      // 4d. Cek Auto-Upgrade peralatan (Joran / Pendingin) saat idle/santai (opt-in OFF default)
      if (mancingConfig.autoUpgrade && (performance.now() - lastUpgradeCheckTime > 60000)) {
        stopAutopilot();
        scheduleAutoUpgrade();
        return;
      }

      // 4e. Autopilot Navigasi Kapal ke Spot Laut Dalam Paling Ramai (kunci akurasi mode Celup)
      if (mancingConfig.autoNavigasi) {
        const sonar = getSonarData();
        const target = getTargetDepth();

        // Segarkan tampilan sonar HUD secara live selama fase navigasi/idle
        const sonarInfoEl = document.getElementById("ks-mancing-sonar-info");
        if (sonarInfoEl) {
          sonarInfoEl.textContent = formatSonarText(sonar);
        }

        const spots = cachedTitik.length > 0 ? cachedTitik : liveShipData.titik;
        if (spots.length === 0 || (!isNavigating && sonar.crowd === "Sepi")) {
          fetchSpots(sonar.crowd === "Sepi");
        }

        const inDepthRange =
          sonar.depth >= target.minDepth &&
          (target.maxDepth == null || sonar.depth <= target.maxDepth);

        const bestSpot = findBestCrowdedSpot(spots, liveShipData.x, liveShipData.z, target);
        // Bila rotasi titik ikan saat ini tidak punya spot yang memenuhi target kedalaman (mis. tidak ada spot ≥30m di Teluk),
        // arahkan ke titik air terbuka yang aman di kedalaman target daripada berputar-putar di spot dangkal atau menabrak batas!
        const navTarget = (bestSpot && bestSpot.meetsDepth)
          ? bestSpot
          : liveShipData.synced
          ? findSafeWaypointForDepth(target, liveShipData.x, pancingProfile.lepasM || 0)
          : bestSpot;

        if (navTarget && liveShipData.synced) {
          const bounds = getBoatSafeBounds(pancingProfile.lepasM || 0);
          const offsetPt = pickOffsetPointInSpot(navTarget, spots, liveShipData.others, target, bounds);
          const safeSpotCoords = offsetPt
            ? clampPointToSafeBounds(offsetPt.x, offsetPt.z, pancingProfile.lepasM || 0)
            : clampPointToSafeBounds(navTarget.x, navTarget.z, pancingProfile.lepasM || 0);
          const dx = safeSpotCoords.x - liveShipData.x;
          const dz = safeSpotCoords.z - liveShipData.z;
          const dist = Math.hypot(dx, dz);

          // Bila target terbaik adalah spot 30m+ Ramai, jangan berhenti prematur di spot 25–29m di tengah jalan
          const wantsDeep30Target = Boolean(
            !navTarget.isSyntheticDepthPoint &&
            target.maxDepth == null &&
            navTarget.depth >= 30 &&
            navTarget.isRamai
          );
          const arrivalDepthOk = wantsDeep30Target ? sonar.depth >= 30 : inDepthRange;

          // Anti-dempet pemain lain: bila sedang idle & ada perahu pemain lain terlalu dekat (<9m),
          // geser sedikit ke titik acak lain yang masih 5/5 Ramai di dalam spot (dengan jeda 15 detik agar tidak bolak-balik).
          const nearestPlayerDist = getNearestOtherBoatDist(liveShipData.x, liveShipData.z, liveShipData.others);
          const targetPlayerDist = getNearestOtherBoatDist(safeSpotCoords.x, safeSpotCoords.z, liveShipData.others);
          const hasBetterClearSpot = targetPlayerDist > nearestPlayerDist + 2 && dist > 4;
          const tooCloseToPlayer = nearestPlayerDist < PLAYER_CROWD_DIST && hasBetterClearSpot;
          const nowNudge = performance.now();
          let nudgingForPlayer = false;
          if (nearestPlayerDist < PLAYER_CROWD_DIST && !isNavigating && nowNudge - lastPlayerNudgeAt >= PLAYER_NUDGE_COOLDOWN_MS) {
            const altPt = pickOffsetPointInSpot(navTarget, spots, liveShipData.others, target, bounds, { forceRepick: true });
            if (altPt && Math.hypot(altPt.x - liveShipData.x, altPt.z - liveShipData.z) >= 5 && getNearestOtherBoatDist(altPt.x, altPt.z, liveShipData.others) > nearestPlayerDist + 2) {
              lastPlayerNudgeAt = nowNudge;
              nudgingForPlayer = true;
            }
          }

          const navSteerSpot = { ...navTarget, x: safeSpotCoords.x, z: safeSpotCoords.z };

          // Prioritas utama: langsung berhenti begitu Sonar mencapai 5/5 bar di kedalaman target (dan tidak terlalu dempet pemain lain).
          // Jika spot terbaik tidak bisa 5 bar (mis. kaya < 0.78), tetap melaju menuju titik acak di inti spot (~5-8m)
          // agar dapat sinyal tertinggi tanpa berhenti prematur di pinggiran Ramai (3-4 bar).
          // Jika tidak ada spot di kedalaman target (synthetic waypoint), langsung berhenti begitu inDepthRange tercapai.
          const coreRadius = Math.min(8, Math.max(5, (navTarget.r || 30) * 0.25));
          const reachedFiveBars = !tooCloseToPlayer && typeof sonar.bars === "number" && sonar.bars >= 5 && arrivalDepthOk && dist <= Math.max(coreRadius + 6, 12);
          const reachedSpotCore = !tooCloseToPlayer && dist <= coreRadius && arrivalDepthOk;
          const reachedSyntheticDepth =
            !tooCloseToPlayer &&
            Boolean(navTarget.isSyntheticDepthPoint) &&
            inDepthRange &&
            sonar.crowd !== "Sepi";
          const reachedLumayanFallback = !tooCloseToPlayer && !navTarget.isRamai && sonar.crowd === "Lumayan" && inDepthRange;
          const reachedOptimalDepth =
            !tooCloseToPlayer &&
            !navTarget.isRamai &&
            sonar.depth >= target.optimalDepth &&
            (target.maxDepth == null || sonar.depth <= target.maxDepth) &&
            sonar.crowd !== "Sepi";

          if (nudgingForPlayer || (!reachedFiveBars && !reachedSpotCore && !reachedSyntheticDepth && !reachedLumayanFallback && !reachedOptimalDepth)) {
            startAutopilotToSpot(navSteerSpot, liveShipData.x, liveShipData.z, liveShipData.h, liveShipData.laju || 0);
            if (tooCloseToPlayer) {
              updateStatusMsg(
                "↔️ Geser Sedikit (Ada Pemain)...",
                `Menjauh dari perahu lain (${Math.round(nearestPlayerDist)}m) sambil tetap 5/5 Ramai...`,
                "#00e5ff"
              );
            }
            // Safety timeout guard (maks 60 detik berlayar)
            if (performance.now() - navStartTime > 60000) {
              stopAutopilot(`Spot dicapai: ${formatSonarText(sonar)}`);
            }
            return;
          }

          if (isNavigating) {
            stopAutopilot(
              reachedFiveBars
                ? `Sinyal 5/5 Penuh: ${formatSonarText(sonar)}!`
                : reachedSyntheticDepth
                ? `Kedalaman Target Tercapai: ${formatSonarText(sonar)}!`
                : `Inti Spot Dicapai: ${formatSonarText(sonar)}!`
            );
            return;
          }
        } else {
          // Fallback navigasi jika telemetri/titik belum sinkron: hormati toast batas agar tidak menabrak terus
          const boundaryToast = readBoundaryToastState();
          if (boundaryToast === "north_ship_limit") {
            stopAutopilot(`Batas laut lepas kapal tercapai (${formatSonarText(sonar)})`);
          } else if (boundaryToast === "area_limit") {
            if (!isNavigating) {
              isNavigating = true;
              navStartTime = performance.now();
            }
            steerShip(-0.25, 0.9 * navTurnSign);
            updateStatusMsg("↩️ Putar Balik dari Batas...", "Menjauh dari batas area mancing...", "#f59e0b");
            return;
          } else if (!inDepthRange && sonar.depth < target.minDepth) {
            if (!isNavigating) {
              isNavigating = true;
              navStartTime = performance.now();
            }
            steerShip(0.65, 0);
            updateStatusMsg("🧭 Menuju Laut Dalam...", `Kedalaman ${sonar.depth}m ➔ target ≥${target.minDepth}m`, "#00e5ff");
            return;
          } else if (isNavigating) {
            stopAutopilot(`Kedalaman ${sonar.depth}m (${sonar.crowd}) tercapai`);
            return;
          }
        }
      } else if (isNavigating) {
        stopAutopilot();
      }

      const useLemparForTernak =
        mancingConfig.strategiUmpan === "ternak-ikan" &&
        getEquippedUmpanType() === "umpan-cacing";
      const useLemparForJustGo =
        mancingConfig.strategiUmpan === "just-go" &&
        mancingConfig.justGoCastMode === "lempar";
      const useLempar = useLemparForTernak || useLemparForJustGo;
      const targetCastBtn = useLempar ? findLemparButton() : findCelupButton();
      if (targetCastBtn && !isCelupButtonReady(targetCastBtn)) {
        const nowDisabled = performance.now();
        if (!castButtonDisabledSince) castButtonDisabledSince = nowDisabled;
        const disabledMs = nowDisabled - castButtonDisabledSince;
        const btnName = useLempar ? "Lempar" : "Celup";
        if (disabledMs >= 5000 && nowDisabled - lastCastRecoveryAttempt >= 4000) {
          lastCastRecoveryAttempt = nowDisabled;
          window.dispatchEvent(new CustomEvent("ks_mancing_recover_cast"));
          updateStatusMsg(
            `🔧 Memulihkan ${btnName}...`,
            "Melepas animasi lempar macet otomatis tanpa refresh (F5)...",
            "#38bdf8"
          );
          return;
        }
        if (disabledMs >= 15000) {
          updateStatusMsg(
            `⚠️ Tombol ${btnName} Macet (⏳)`,
            `Tombol ${btnName} game terkunci >15 detik. Refresh halaman (F5) untuk pulihkan.`,
            "#f59e0b"
          );
          return;
        }
      } else {
        castButtonDisabledSince = 0;
      }

      updateStatusMsg(
        useLemparForTernak
          ? "🎣 Lempar Cacing (Cari Ikan Kecil)..."
          : useLemparForJustGo
          ? `🎣 Melempar Kail (${getUmpanShortName(getActiveSelectedBait())})...`
          : "⬇️ Menurunkan Kail (Celup)...",
        useLemparForTernak
          ? "Mencari ikan kecil untuk umpan-ikan 2.3×..."
          : useLemparForJustGo
          ? "Mode Just Go · Lempar kail alami..."
          : "Jeda alami mencelupkan kail ke laut dalam...",
        "#38bdf8"
      );
      if (mancingConfig.autoCelup) {
        scheduleNaturalCelup(useLempar);
      }
      return;
    }

    // 5. Fase Tunggu (Pelampung Mengapung di Air)
    if (fase === "tunggu") {
      castButtonDisabledSince = 0;
      releaseGulung();
      resetReelCycle();
      stopAutopilot();
      updateStatusMsg("⏳ Menunggu Sambaran...", "Pelampung di air, siap menyentak!", "#06b6d4");
      return;
    }
  }, 40);
})();
