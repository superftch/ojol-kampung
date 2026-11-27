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
    smartProfit: true,           // Dipertahankan untuk kompatibilitas internal (dikendalikan lewat lootMode + stopRule)
    lootMode: "hybrid",          // "hybrid" (Jual Mahal, Simpan Murah) | "jual-semua" (Jual semua > modal umpan)
    sellThreshold: 1.00,         // Batas jual langsung koin untuk mode Hybrid: 1.00 | 1.20 | 1.40
    stopRule: "all-full",        // "all-full" (40/40) | "sell-full" (20/20) | "bait-empty" (sampai umpan habis)
    selectiveRelease: false,     // Selalu OFF (tidak buang/lepas ikan ke laut)
    templateCustom: false,       // True bila pengguna mengubah Settings setelah memilih Template
    settingsCollapsed: false,    // Status lipat panel Settings di HUD
    autoJaring: true,            // Otomatis tebar jaring untuk dapat umpan gratis harian
    autoLampu: true,             // Otomatis nyalakan lampu kapal saat malam (18.30 - 04.30) agar ikan lebih ramai
    singleRodProfit: true,       // Selalu ON: pertahankan 1 joran (1 umpan/celup) agar tidak boros umpan 2x-3x
    autoJualTasPenuh: true,      // Jika tas ikan penuh, otomatis jual agar tangkapan tidak sia-sia
    autoJualSampah: true,        // Otomatis buang/jual sampah laut (Sandal jepit, dll)
    autoUmpan: false,            // Opt-in (OFF default): otomatis beli umpan (Cumi / Udang / Cacing) saat stok 0
    autoUmpanIkan: true,         // Jadikan ikan kecil sebagai umpan-ikan (besar 2.3x) & prioritaskan pakai stoknya
    autoUpgrade: false,          // Opt-in (OFF default): otomatis beli upgrade joran & pendingin bernilai tinggi
    autoNavigasi: true,          // Otomatis arahkan & kemudikan kapal ke kedalaman paling worth it sesuai umpan & joran
    preferredUmpan: "umpan-cumi", // "umpan-cumi" (Paling Cuan) / "umpan-udang" (Hemat Modal) / "umpan-cacing" (Ternak Umpan Ikan)
    strategiUmpan: "",           // Template aktif: "just-go" | "cumi" | "ternak-ikan"
    baseMaxTension: 80,          // % batas atas default saat mode Natural mati (saat Natural ON acak 70-85%)
    baseMinTension: 35,          // % batas bawah default saat mode Natural mati (saat Natural ON acak 29-45%)
    reelMinRange: [29, 45],      // Rentang acak mulai gulung (mode Natural)
    reelMaxRange: [70, 85]       // Rentang acak lepas gulung (mode Natural, tetap dilindungi anti-putus)
  };

  const DAILY_STATS_KEY = "ks_mancing_daily_stats";
  const SETTINGS_KEY = "ks_mancing_settings_v1";
  const VALID_STRATEGIES = new Set(["", "just-go", "cumi", "ternak-ikan"]);
  const VALID_LOOT_MODES = new Set(["hybrid", "jual-semua"]);
  const VALID_SELL_THRESHOLDS = new Set([1.0, 1.2, 1.4]);
  const VALID_STOP_RULES = new Set(["all-full", "sell-full", "bait-empty"]);

  const MANCING_TEMPLATES = {
    "just-go": {
      strategiUmpan: "just-go",
      lootMode: "hybrid",
      sellThreshold: 1.00,
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
      lootMode: "hybrid",
      sellThreshold: 1.00,
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
      lootMode: "hybrid",
      sellThreshold: 1.00,
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

  function normalizeSavedLootMode(raw) {
    if (raw === "jual-semua" || raw === "cashflow") return "jual-semua";
    if (raw === "hybrid" || raw === "quota-saver" || raw === "whale") return "hybrid";
    return null;
  }

  function loadMancingSettings() {
    try {
      const raw = localStorage.getItem(SETTINGS_KEY);
      if (!raw) return;
      const saved = JSON.parse(raw);
      if (!saved || typeof saved !== "object") return;

      if (typeof saved.strategiUmpan === "string" && VALID_STRATEGIES.has(saved.strategiUmpan)) {
        mancingConfig.strategiUmpan = saved.strategiUmpan;
        if (saved.strategiUmpan === "ternak-ikan") mancingConfig.preferredUmpan = "umpan-cacing";
        else if (saved.strategiUmpan === "cumi") mancingConfig.preferredUmpan = "umpan-cumi";
      }
      const normLoot = normalizeSavedLootMode(saved.lootMode);
      if (normLoot) {
        mancingConfig.lootMode = normLoot;
      }
      mancingConfig.selectiveRelease = false;
      if (typeof saved.sellThreshold === "number" && VALID_SELL_THRESHOLDS.has(saved.sellThreshold)) {
        mancingConfig.sellThreshold = saved.sellThreshold;
      }
      if (typeof saved.stopRule === "string" && VALID_STOP_RULES.has(saved.stopRule)) {
        mancingConfig.stopRule = saved.stopRule;
      }

      const boolKeys = [
        "modeNatural", "zeroLossGuard", "autoCelup", "autoSentak", "autoGulung",
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
        lootMode: mancingConfig.lootMode,
        sellThreshold: mancingConfig.sellThreshold,
        stopRule: mancingConfig.stopRule,
        templateCustom: mancingConfig.templateCustom,
        settingsCollapsed: mancingConfig.settingsCollapsed,
        modeNatural: mancingConfig.modeNatural,
        zeroLossGuard: mancingConfig.zeroLossGuard,
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
    if (btn) {
      const isHolding = btn.hasAttribute("data-tahan");
      if (isHolding && isGulungActive) return;
      isGulungActive = true;

      const rect = btn.getBoundingClientRect();
      const cx = rect.left + rect.width / 2 + humanJitter(-8, 8);
      const cy = rect.top + rect.height / 2 + humanJitter(-4, 4);

      // Proteksi dummy setPointerCapture agar synthetic event tidak memicu DOMException InvalidPointerId
      const origCapture = btn.setPointerCapture;
      try {
        btn.setPointerCapture = () => {};
        btn.dispatchEvent(new PointerEvent("pointerdown", {
          bubbles: true,
          cancelable: true,
          pointerId: 0,
          clientX: cx,
          clientY: cy,
          pointerType: "mouse"
        }));
      } catch (e) {
      } finally {
        if (origCapture) btn.setPointerCapture = origCapture;
      }
    } else {
      isGulungActive = true;
    }
    window.dispatchEvent(new KeyboardEvent("keydown", { code: "Space", key: " ", bubbles: true }));
  }

  function releaseGulung() {
    const btn = document.querySelector('[data-testid="pancing-gulung"]');
    const isHoldingDom = !!(btn && btn.hasAttribute("data-tahan"));
    if (!isGulungActive && !isHoldingDom) return;
    isGulungActive = false;
    if (btn) {
      btn.dispatchEvent(new PointerEvent("pointerup", { bubbles: true, pointerId: 0, pointerType: "mouse" }));
      btn.dispatchEvent(new PointerEvent("pointercancel", { bubbles: true, pointerId: 0, pointerType: "mouse" }));
    }
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

  // Sentak Sambaran Alami: refleks manusia 220ms - 380ms (aman dari batas 10s game)
  function scheduleNaturalSentak() {
    if (strikePending) return;
    strikePending = true;

    const delay = mancingConfig.modeNatural ? humanJitter(220, 380) : 40;

    setTimeout(() => {
      const btnSentak = document.querySelector('[data-testid="pancing-sentak"]');
      if (btnSentak) {
        naturalClick(btnSentak);
      }
      window.dispatchEvent(new KeyboardEvent("keydown", { code: "Space", key: " ", bubbles: true }));

      setTimeout(() => {
        window.dispatchEvent(new KeyboardEvent("keyup", { code: "Space", key: " ", bubbles: true }));
        strikePending = false;
      }, mancingConfig.modeNatural ? humanJitter(70, 140) : 50);
    }, delay);
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

  function recordBaitLoss({ id = "", reason = "dimakan", message = "", umpan = "" } = {}) {
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
    const reasonKey = String(reason || "dimakan").toLowerCase();

    let name = "Umpan Dimakan";
    let action = "Dimakan";
    if (reasonKey.includes("putus")) {
      name = "Tali Putus";
      action = "Putus";
    } else if (reasonKey.includes("lepas") || reasonKey.includes("gagal")) {
      name = "Ikan Lepas";
      action = "Lepas";
    } else if (reasonKey.includes("batal")) {
      name = "Tarik Kail";
      action = "Batal";
    } else if (message && typeof message === "string" && message.length <= 28) {
      name = message;
    }

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

    // Ikan yang bisa dijadikan umpan-ikan selalu diprioritaskan (baik pada mode Jual Semua maupun Hybrid)
    if (config.autoUmpanIkan && !isTrash && availableButtons.umpanIkan) {
      return "JADIKAN_UMPAN";
    }

    const lootMode = config.lootMode === "jual-semua" ? "jual-semua" : "hybrid";
    const threshold = typeof config.sellThreshold === "number" && config.sellThreshold > 0
      ? config.sellThreshold
      : 1.00;
    const isHighValue = sellPrice >= threshold || (threshold <= 1.00 && Boolean(isBigClass));

    if (lootMode === "jual-semua") {
      // Jual Semua: jual semua ikan yang nilainya > modal umpan (kecuali ikan kecil yg sudah jadi umpan)
      if ((config.autoJual || sellPrice > baitCost) && sisaJual > 0 && availableButtons.jual) {
        return "JUAL";
      }
      if (config.autoSimpan && sisaTas > 0 && availableButtons.simpan) {
        return "SIMPAN";
      }
      if (config.autoJualTasPenuh && sisaJual > 0 && availableButtons.jual) {
        return "JUAL_TAS_PENUH";
      }
    } else {
      // Hybrid (default): jual ikan mahal (>= threshold), simpan ikan murah (< threshold) ke tas, jual jika tas penuh
      if ((config.autoJual || isHighValue) && sisaJual > 0 && availableButtons.jual) {
        return "JUAL";
      }
      if (config.autoSimpan && sisaTas > 0 && availableButtons.simpan) {
        return "SIMPAN";
      }
      if (config.autoJualTasPenuh && sisaJual > 0 && availableButtons.jual) {
        return "JUAL_TAS_PENUH";
      }
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

    // 1. Umpan Ikan Hidup (2.3x), Umpan Cumi (1.7x), atau Joran Samudra: Target Ikan Raksasa
    if (hasSamudra || isIkanHidup || isCumi) {
      const targetFish = hasOffshoreAccess
        ? "Kuwe GT, Barakuda, Tuna/Marlin (Laut Lepas)"
        : "Kuwe GT (≥30m) & Barakuda (≥24m)";
      return {
        minDepth: 30,
        optimalDepth: hasOffshoreAccess ? 35 : 32,
        allowCrowdStopAt: 30,
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
    jualMaks: 20,
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
          pancingProfile.jualMaks = data.jual.maks ?? 20;
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

  function calcDepth(x, z) {
    let n = Math.min(1, Math.max(0, (-z - 10) / 630));
    return Math.max(1.5, 2 + n * n * 18 + 20 * n + Math.sin(0.021 * x + 1.3) * Math.cos(0.017 * z) * 3 * n);
  }

  // Batas resmi game untuk status "Ramai": rame >= 0.45 (5 bar penuh sekitar >= 0.78)
  const RAMAI_MIN_KAYA = 0.45;
  const FIVE_BAR_MIN_KAYA = 0.78;

  function rankFishingAreas(spots, shipX, shipZ, target = null) {
    if (!spots || spots.length === 0) return [];

    const activeTarget = target || getTargetDepth();
    const minDepth = activeTarget.minDepth || 0;
    const maxDepth = activeTarget.maxDepth ?? null;
    const minReachableZ = -640 - Math.max(0, pancingProfile.lepasM || 0);
    const reachableSpots = spots.filter(
      s => s.z >= minReachableZ && s.z <= -8 && s.x >= -315 && s.x <= 315
    );
    const pool = reachableSpots.length > 0 ? reachableSpots : spots;

    const ranked = pool.map(s => {
      const d = calcDepth(s.x, s.z);
      const dist = Math.hypot(s.x - shipX, s.z - shipZ);
      const meetsDepth = d >= minDepth && (maxDepth === null || d <= maxDepth);
      const isRamai = (s.kaya || 0) >= RAMAI_MIN_KAYA;
      const isFiveBar = (s.kaya || 0) >= FIVE_BAR_MIN_KAYA;
      const tier = (meetsDepth && isFiveBar) ? 4 : (meetsDepth && isRamai) ? 3 : meetsDepth ? 2 : isRamai ? 1 : 0;
      const depthBonus = maxDepth !== null
        ? Math.max(0, 60 - Math.abs(d - (activeTarget.optimalDepth || 5)) * 8)
        : (d >= 34 ? 140 : d >= 30 ? 120 : d >= 24 ? 80 : d >= 15 ? 40 : d);
      const score = (tier * 1000) + ((s.kaya || 0) * 600) + depthBonus - (dist * 0.08);
      return { ...s, depth: d, dist, tier, isRamai, isFiveBar, meetsDepth, score };
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

  function startAutopilotToSpot(spot, shipX, shipZ, shipH) {
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

    const dx = spot.x - shipX;
    const dz = spot.z - shipZ;
    const dist = Math.hypot(dx, dz);

    const targetHeading = Math.atan2(dx, dz);
    let diff = (targetHeading - shipH + Math.PI) % (2 * Math.PI);
    if (diff < 0) diff += 2 * Math.PI;
    diff -= Math.PI;
    const absDiff = Math.abs(diff);

    // Deteksi heading macet HANYA saat kita aktif memerintahkan belok (bukan saat melaju lurus!)
    if (absDiff > 0.04 && (Math.abs(lastCommandedBelok) > 0.15 || shipHStuckCount > 25)) {
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
      // Kemudi proporsional dengan deadband ketat 0.04 rad (~2.3 derajat)
      if (absDiff > 0.04) {
        const rawTurn = Math.max(-1, Math.min(1, diff / 0.45));
        belok = rawTurn * navTurnSign;
      }
    }

    // Kontrol kecepatan cerdas: pelan saat berputar tajam atau mendekati pusat spot agar tidak kebablasan/berputar-putar
    let gas = 1.0;
    if (absDiff > 1.05) {
      gas = 0.15;
    } else if (absDiff > 0.45) {
      gas = 0.55;
    } else if (dist < 25) {
      gas = Math.max(0.25, Math.min(1, dist / 25));
    }

    steerShip(gas, belok);

    const degOff = Math.round((absDiff * 180) / Math.PI);
    updateStatusMsg(
      "🧭 Menuju Spot Ramai...",
      `Jarak ${Math.round(dist)}m · Arah ${degOff}° (${(spot.kaya * 100).toFixed(0)}% kaya, ${Math.round(spot.depth)}m)`,
      "#00e5ff"
    );
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

      // Prioritaskan umpan milik sendiri (gratis / sudah punya stok > 0) sebelum membeli baru
      const equippedNow = getEquippedUmpanType();
      const targetPrefCheck = isTernakMode
        ? "umpan-cacing"
        : isJustGoMode
        ? (["umpan-cumi", "umpan-udang", "umpan-cacing"].includes(equippedNow) ? equippedNow : "umpan-cumi")
        : mancingConfig.preferredUmpan;
      const defaultOwnedOrder = isJustGoMode
        ? [
            ...(mancingConfig.autoUmpanIkan ? ["umpan-ikan"] : []),
            "umpan-cumi",
            "umpan-udang",
            "umpan-cacing"
          ]
        : allowBuy
        ? [
            ...(mancingConfig.autoUmpanIkan ? ["umpan-ikan"] : []),
            ...(isTernakMode ? ["umpan-cacing"] : [targetPrefCheck, "umpan-cumi", "umpan-udang", "umpan-cacing"])
          ]
        : isTernakMode
        ? ["umpan-ikan", "umpan-cacing"]
        : ["umpan-ikan"];
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
              detail: "Stok umpan habis & Auto Beli Umpan mati. Aktifkan Auto Beli Umpan atau beli manual di toko lalu klik Mulai.",
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
        const sisaJual = pancingProfile.loaded ? Math.max(0, pancingProfile.jualMaks - pancingProfile.jualHariIni) : 20;
        const sisaSlot = pancingProfile.loaded
          ? sisaJual + Math.max(0, pancingProfile.tasMaks - pancingProfile.tasIkan)
          : 40;
        const remainingTargetSlots = mancingConfig.stopRule === "sell-full" ? sisaJual : sisaSlot;
        const lowCoinPack5 = pancingProfile.loaded && pancingProfile.saldoKoin < 5.0;
        const preferPack5 = (mancingConfig.stopRule !== "bait-empty" && remainingTargetSlots > 0 && remainingTargetSlots <= 5) || lowCoinPack5;
        if (preferPack5 && btn5) naturalClick(btn5);
        else if (btn10) naturalClick(btn10);
        else if (btn5) naturalClick(btn5);

        // Step 3: Klik tombol beli umpan target
        setTimeout(() => {
          const btnBeliCumi = sheetToko.querySelector('[data-testid="pancing-beli-cumi"], [data-testid="pancing-beli-umpan-cumi"]');
          const btnBeliUdang = sheetToko.querySelector('[data-testid="pancing-beli-udang"], [data-testid="pancing-beli-umpan-udang"]');
          const btnBeliCacing = sheetToko.querySelector('[data-testid="pancing-beli-cacing"], [data-testid="pancing-beli-umpan-cacing"]');

          let targetBeli = null;
          let namaUmpan = "Umpan Cumi";
          let targetPilihId = "cumi";
          const targetPref = isTernakMode
            ? "umpan-cacing"
            : isJustGoMode
            ? targetPrefCheck
            : mancingConfig.preferredUmpan;

          if (targetPref === "umpan-cacing" && btnBeliCacing && !btnBeliCacing.disabled) {
            targetBeli = btnBeliCacing;
            namaUmpan = isJustGoMode ? "Cacing Laut" : "Cacing Laut (Ternak Umpan Ikan)";
            targetPilihId = "cacing";
          } else if (targetPref === "umpan-udang" && btnBeliUdang && !btnBeliUdang.disabled) {
            targetBeli = btnBeliUdang;
            namaUmpan = "Umpan Udang (Hemat Modal)";
            targetPilihId = "udang";
          } else if (targetPref === "umpan-cumi" && btnBeliCumi && !btnBeliCumi.disabled) {
            targetBeli = btnBeliCumi;
            namaUmpan = "Umpan Cumi (Profit Max)";
            targetPilihId = "cumi";
          } else if (btnBeliUdang && !btnBeliUdang.disabled) {
            targetBeli = btnBeliUdang;
            namaUmpan = "Umpan Udang (Hemat Modal)";
            targetPilihId = "udang";
          } else if (btnBeliCumi && !btnBeliCumi.disabled) {
            targetBeli = btnBeliCumi;
            namaUmpan = "Umpan Cumi";
            targetPilihId = "cumi";
          } else if (btnBeliCacing && !btnBeliCacing.disabled) {
            targetBeli = btnBeliCacing;
            namaUmpan = "Cacing Laut";
            targetPilihId = "cacing";
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
        updateStatusMsg("ℹ️ Jatah Jual Habis (20/20)", `Tas: ${pancingProfile.tasIkan}/${pancingProfile.tasMaks}. Sisa ikan disimpan di tas untuk besok.`, "#f59e0b");
      } else if (sisaTas === 0) {
        updateStatusMsg("⚠️ Tas Penuh (20/20)!", `Sisa kuota jual BUMDes: ${sisaJual} ekor. Ikan akan langsung dijual.`, "#eab308");
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

  // UI HUD Auto-Mancing Pro
  function createMancingHUD() {
    if (document.getElementById("ks-mancing-hud")) return;

    const hud = document.createElement("div");
    hud.id = "ks-mancing-hud";
    hud.style.cssText = `
      position: fixed;
      top: 12px;
      right: 12px;
      width: 310px;
      max-height: calc(100vh - 24px);
      display: flex;
      flex-direction: column;
      background: rgba(11, 19, 43, 0.94);
      border: 1px solid rgba(0, 229, 255, 0.45);
      border-radius: 12px;
      color: #e2e8f0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      font-size: 11px;
      z-index: 999999;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.55), 0 0 16px rgba(0, 229, 255, 0.25);
      backdrop-filter: blur(12px);
      overflow: hidden;
      transition: all 0.2s ease;
    `;

    hud.innerHTML = `
      <div id="ks-mancing-header" style="background: rgba(0, 229, 255, 0.15); padding: 8px 12px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(0, 229, 255, 0.25); cursor: grab; user-select: none; flex-shrink: 0;">
        <div style="font-weight: bold; color: #00e5ff; display: flex; align-items: center; gap: 6px; font-size: 12px;">
          <span style="opacity: 0.7; font-size: 13px;" title="Geser Posisi HUD (Klik & Geser Bebas)">⠿</span>
          <span>🎣 Auto-Mancing Pro (Natural)</span>
        </div>
        <div style="display: flex; align-items: center; gap: 4px;">
          <button id="ks-mancing-mini-win" title="Buka di Mini Window (460×680)" style="background: rgba(13, 148, 136, 0.35); border: 1px solid rgba(45, 212, 191, 0.45); color: #5eead4; cursor: pointer; font-size: 11px; font-weight: bold; padding: 2px 6px; border-radius: 5px;">📌</button>
          <button id="ks-mancing-toggle" style="background: none; border: none; color: #90caf9; cursor: pointer; font-size: 14px; font-weight: bold; padding: 2px 6px;">_</button>
        </div>
      </div>

      <div id="ks-mancing-content" style="padding: 9px 10px; overflow-y: auto; flex: 1;">
        <!-- Live Sonar & Target (Paling Atas) -->
        <div style="background: rgba(14, 165, 233, 0.12); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 6px; padding: 5px 8px; margin-bottom: 7px; font-size: 10.5px;">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span style="color: #38bdf8;">📡 Sonar:</span>
            <b id="ks-mancing-sonar-info" style="color: #4ade80;">Membaca...</b>
          </div>
          <div id="ks-mancing-target-info" style="font-size: 10px; color: #cbd5e1; margin-top: 1px;">
            🎯 Target: Membaca...
          </div>
        </div>

        <!-- Status Box -->
        <div style="background: rgba(15, 23, 42, 0.75); border: 1px solid rgba(56, 189, 248, 0.35); border-radius: 7px; padding: 7px 9px; margin-bottom: 7px;">
          <div id="ks-mancing-status" style="font-size: 12px; font-weight: bold; color: #38bdf8;">
            ⚪ Siap Memancing
          </div>
          <div id="ks-mancing-detail" style="font-size: 10px; color: #94a3b8; margin-top: 2px;">
            Tekan tombol Mulai di bawah untuk otomatisasi
          </div>
          <div id="ks-mancing-plan" style="font-size: 10px; color: #cbd5e1; margin-top: 5px; padding-top: 4px; border-top: 1px solid rgba(56, 189, 248, 0.2); line-height: 1.35;">
            📋 Plan: Menunggu status...
          </div>
        </div>

        <!-- Profil Statistik Harian Game -->
        <div style="background: rgba(15, 23, 42, 0.85); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 7px; padding: 7px 8px; margin-bottom: 7px; font-size: 10.5px;">
          <div style="display: flex; justify-content: space-between; margin-bottom: 2px;">
            <span style="color: #94a3b8;">🎣 Celup / Tas / Jual:</span>
            <span><b id="ks-stat-hari-ini" style="color: #38bdf8;">...</b> · <b id="ks-stat-tas" style="color: #4ade80;">...</b> · <b id="ks-stat-jual" style="color: #fbbf24;">...</b></span>
          </div>
          <div style="display: flex; justify-content: space-between; margin-bottom: 2px;">
            <span style="color: #94a3b8;">🪙 Koin &amp; Joran:</span>
            <span><b id="ks-stat-saldo" style="color: #f1f5f9;">...</b> · <b id="ks-stat-joran" style="color: #c084fc;">...</b></span>
          </div>
          <div style="display: flex; justify-content: space-between; margin-bottom: 2px;">
            <span style="color: #94a3b8;">🪱 Umpan:</span>
            <b id="ks-stat-umpan" style="color: #fde047;">Memuat...</b>
          </div>
          <div style="display: flex; justify-content: space-between; margin-bottom: 2px;">
            <span style="color: #94a3b8;">⛵ Kapal:</span>
            <b id="ks-stat-kapal" style="color: #67e8f9;">Memuat...</b>
          </div>
          <div style="display: flex; justify-content: space-between;">
            <span style="color: #94a3b8;">🧰 Fitur Kapal:</span>
            <b id="ks-stat-fitur-kapal" style="color: #cbd5e1;">Memuat...</b>
          </div>
        </div>

        <!-- Stats Tangkapan & Profit Hari Ini -->
        <div style="background: rgba(255, 255, 255, 0.05); border-radius: 6px; padding: 6px 8px; margin-bottom: 7px; font-size: 10.5px;">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span>Hari Ini: <b id="ks-mancing-count" style="color: #4ade80;">0 ekor</b></span>
            <span id="ks-mancing-profit" style="color: #4ade80; font-weight: bold;">💰 Laba Hari Ini: +0.00 koin</span>
          </div>
          <div id="ks-mancing-last" style="font-size: 10px; color: #cbd5e1; margin-top: 5px; padding-top: 4px; border-top: 1px solid rgba(255,255,255,0.08);">
            <div style="color: #94a3b8; font-weight: 600;">Riwayat Hari Ini: -</div>
          </div>
        </div>

        <!-- Tombol Utama Start / Stop (Di Bawah Bagian Hari Ini) -->
        <button id="ks-mancing-start-btn" style="
          width: 100%;
          padding: 8px;
          background: linear-gradient(90deg, #16a34a, #22c55e);
          border: none;
          color: white;
          border-radius: 7px;
          cursor: pointer;
          font-size: 12px;
          font-weight: 800;
          margin-bottom: 7px;
          box-shadow: 0 4px 12px rgba(22, 163, 74, 0.35);
          transition: all 0.15s ease;
        ">
          ▶️ Mulai Auto Mancing Natural
        </button>

        <!-- Section 1: Template (1-Klik Preset) -->
        <div style="background: rgba(168, 85, 247, 0.12); border: 1px solid rgba(168, 85, 247, 0.35); border-radius: 6px; padding: 6px 8px; margin-bottom: 7px; font-size: 10.5px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
            <span style="font-weight: bold; color: #c084fc;">🎯 Template:</span>
            <span id="ks-tpl-badge" style="font-size: 9.5px; color: #94a3b8;">Pilih preset</span>
          </div>
          <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px;">
            <button type="button" id="ks-tpl-just-go" data-template="just-go" title="Preset Just Go: langsung mancing pakai umpan apa saja yang sedang terpasang (Cacing / Udang / Cumi / Ikan) tanpa ganti-ganti umpan." style="padding: 5px 4px; border-radius: 5px; border: 1px solid rgba(192, 132, 252, 0.35); background: rgba(15, 23, 42, 0.85); color: #e2e8f0; font-size: 10px; font-weight: bold; cursor: pointer; white-space: nowrap;">
              🚀 Just Go
            </button>
            <button type="button" id="ks-tpl-cumi" data-template="cumi" title="Preset Langsung Cumi: langsung ke laut dalam ≥30m (Celup), otomatis atur Settings." style="padding: 5px 4px; border-radius: 5px; border: 1px solid rgba(192, 132, 252, 0.35); background: rgba(15, 23, 42, 0.85); color: #e2e8f0; font-size: 10px; font-weight: bold; cursor: pointer; white-space: nowrap;">
              🦑 Cumi
            </button>
            <button type="button" id="ks-tpl-ternak" data-template="ternak-ikan" title="Preset Ternak Umpan: Cacing di dangkal (2–10m) kumpul 5 umpan-ikan (2.3×), lalu Celup di ≥30m." style="padding: 5px 4px; border-radius: 5px; border: 1px solid rgba(192, 132, 252, 0.35); background: rgba(15, 23, 42, 0.85); color: #e2e8f0; font-size: 10px; font-weight: bold; cursor: pointer; white-space: nowrap;">
              🐟 Ternak
            </button>
          </div>
          <div id="ks-tpl-desc" style="font-size: 9.5px; color: #cbd5e1; margin-top: 4px; line-height: 1.3;">
            Pilih template di atas untuk langsung mengisi Settings.
          </div>
        </div>

        <!-- Section 2: Settings (Terpisah & Bisa Dilipat) -->
        <div style="background: rgba(15, 23, 42, 0.65); border: 1px solid rgba(56, 189, 248, 0.28); border-radius: 6px; padding: 6px 8px; margin-bottom: 6px; font-size: 10.5px;">
          <div id="ks-settings-toggle" style="display: flex; justify-content: space-between; align-items: center; cursor: pointer; user-select: none;">
            <span style="font-weight: bold; color: #38bdf8;">⚙️ Settings</span>
            <span id="ks-settings-chevron" style="color: #94a3b8; font-size: 11px;">▾</span>
          </div>

          <div id="ks-settings-body" style="margin-top: 6px;">
            <!-- Dropdown Hasil & Stop -->
            <div style="display: flex; align-items: center; gap: 5px; margin-bottom: 5px;">
              <span style="color: #94a3b8; width: 34px; flex-shrink: 0; font-size: 10px;">Hasil</span>
              <select id="ks-opt-loot-mode" title="Hybrid: jual ikan mahal (>= batas) & simpan yang murah. Jual Semua: jual semua ikan bernilai > modal umpan (kecuali ikan kecil yang bisa jadi umpan)." style="flex: 1; min-width: 0; padding: 3.5px 5px; border-radius: 5px; border: 1px solid rgba(56, 189, 248, 0.4); background: rgba(15, 23, 42, 0.9); color: #e2e8f0; font-size: 10px; cursor: pointer;">
                <option value="hybrid" selected>⚖️ Hybrid (Jual Mahal, Simpan Murah)</option>
                <option value="jual-semua">💵 Jual Semua (&gt; Modal Umpan)</option>
              </select>
              <select id="ks-opt-sell-threshold" title="Batas minimal harga ikan untuk langsung dijual pada mode Hybrid." style="width: 62px; flex-shrink: 0; padding: 3.5px 4px; border-radius: 5px; border: 1px solid rgba(56, 189, 248, 0.4); background: rgba(15, 23, 42, 0.9); color: #fde68a; font-size: 10px; cursor: pointer;">
                <option value="1.00" selected>≥ 1.00</option>
                <option value="1.20">≥ 1.20</option>
                <option value="1.40">≥ 1.40</option>
              </select>
            </div>
            <div style="display: flex; align-items: center; gap: 5px; margin-bottom: 5px;">
              <span style="color: #94a3b8; width: 34px; flex-shrink: 0; font-size: 10px;">Stop</span>
              <select id="ks-opt-stop-rule" title="Tentukan kapan Auto-Mancing berhenti otomatis." style="flex: 1; padding: 3.5px 5px; border-radius: 5px; border: 1px solid rgba(56, 189, 248, 0.4); background: rgba(15, 23, 42, 0.9); color: #cbd5e1; font-size: 10px; cursor: pointer;">
                <option value="all-full" selected>🏆 Jual + Tas Penuh (40/40)</option>
                <option value="sell-full">💰 Jatah Jual Habis (20/20)</option>
                <option value="bait-empty">🪱 Umpan Habis</option>
              </select>
            </div>
            <div id="ks-settings-summary" style="font-size: 9.5px; color: #94a3b8; margin-bottom: 6px; line-height: 1.3;">
              ↳ Ikan ≥1.00 dijual, &lt;1.00 disimpan ke tas.
            </div>

            <!-- Checkboxes (Urutan Kiri: Natural, Auto Celup, Auto Sentak, Auto Gulung | Kanan: Zero-Loss, Auto Simpan, Autopilot, Jual/Sampah) -->
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px 6px; font-size: 10.5px; color: #cbd5e1;">
              <label title="Berlaku di semua aksi: Celup (jeda 2.2–3.8s), Sentak (220–380ms), Gulung (acak 29–45% ⇄ 70–85%), Loot (1.4–2.5s), dan koordinat klik acak." style="display: flex; align-items: center; gap: 4px; cursor: pointer;">
                <input type="checkbox" id="ks-opt-natural" checked style="cursor: pointer;">
                <span>🌿 Natural</span>
              </label>
              <label title="Proteksi anti-putus &amp; anti-lepas: lepas cepat di zona merah (<0.6s batas putus) dan tahan ulang otomatis jika gulungan terlepas di tengah tarikan (29–45% ⇄ 70–85%)." style="display: flex; align-items: center; gap: 4px; cursor: pointer;">
                <input type="checkbox" id="ks-opt-zeroloss" checked style="cursor: pointer;">
                <span>🛡️ Zero-Loss</span>
              </label>
              <label title="Otomatis menurunkan kail (Celup di laut dalam, atau Lempar saat mode Cacing dangkal)." style="display: flex; align-items: center; gap: 4px; cursor: pointer;">
                <input type="checkbox" id="ks-opt-celup" checked style="cursor: pointer;">
                <span>⬇️ Auto Celup</span>
              </label>
              <label title="Izinkan menyimpan ikan ke Tas saat tidak langsung dijual (mis. ikan di bawah batas jual atau setelah kuota jual 20/20 habis)." style="display: flex; align-items: center; gap: 4px; cursor: pointer;">
                <input type="checkbox" id="ks-opt-simpan" checked style="cursor: pointer;">
                <span>🎒 Auto Simpan</span>
              </label>
              <label title="Otomatis menyentak kail begitu ikan menyambar (jauh di bawah batas waktu 10 detik server)." style="display: flex; align-items: center; gap: 4px; cursor: pointer;">
                <input type="checkbox" id="ks-opt-sentak" checked style="cursor: pointer;">
                <span>⚡ Auto Sentak</span>
              </label>
              <label title="Otomatis mengemudikan kapal ke spot Ramai (target 5/5 bar) dengan kedalaman terbaik sesuai batas kapal &amp; joran." style="display: flex; align-items: center; gap: 4px; cursor: pointer;">
                <input type="checkbox" id="ks-opt-auto-navigasi" checked style="cursor: pointer;">
                <span>🧭 Autopilot</span>
              </label>
              <label title="Otomatis menggulung dan melepas gulungan secara tahan-panjang (29–45% ⇄ 70–85% pada Mode Natural)." style="display: flex; align-items: center; gap: 4px; cursor: pointer;">
                <input type="checkbox" id="ks-opt-gulung" checked style="cursor: pointer;">
                <span>🔄 Auto Gulung</span>
              </label>
              <label title="Otomatis buang sampah laut (Sandal jepit) dan jual ikan jika tas penuh saat kuota jual masih ada." style="display: flex; align-items: center; gap: 4px; cursor: pointer;">
                <input type="checkbox" id="ks-opt-jual-penuh" checked style="cursor: pointer;">
                <span>🪙 Jual/Sampah</span>
              </label>
            </div>

            <!-- Opt-in Belanja & Fitur Kapal -->
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px 6px; margin-top: 6px; padding-top: 5px; border-top: 1px solid rgba(255,255,255,0.08); font-size: 10px; color: #cbd5e1;">
              <label title="Opt-in (default mati): otomatis membeli umpan di toko saat seluruh stok umpan habis. Ganti antar umpan milik sendiri tetap jalan walau mati." style="display: flex; align-items: center; gap: 4px; cursor: pointer;">
                <input type="checkbox" id="ks-opt-auto-umpan" style="cursor: pointer;">
                <span style="color: #fde68a;">🛒 Auto Umpan</span>
              </label>
              <label title="Opt-in (default mati): otomatis membeli upgrade Joran terbaik (Samudra → Tonda → Karang) dan Kotak Pendingin (+slot tas) saat koin cukup." style="display: flex; align-items: center; gap: 4px; cursor: pointer;">
                <input type="checkbox" id="ks-opt-auto-upgrade" style="cursor: pointer;">
                <span style="color: #f3e8ff;">🎣 Auto Upgrade</span>
              </label>
              <label id="ks-opt-jaring-lampu-wrap" title="Otomatis tebar Jaring untuk umpan gratis harian &amp; nyalakan Lampu Kapal saat malam (18.30–04.30)." style="grid-column: 1 / -1; display: flex; align-items: center; gap: 4px; cursor: pointer;">
                <input type="checkbox" id="ks-opt-jaring-lampu" checked style="cursor: pointer;">
                <span style="color: #86efac;">🕸️ Auto Jaring &amp; Lampu Malam</span>
              </label>
            </div>
          </div>
        </div>

        <div style="font-size: 9.5px; color: #64748b; text-align: center; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 4px;">
          Tekan <b>Esc</b> kapan saja untuk membatalkan
        </div>
      </div>
    `;

    document.body.appendChild(hud);

    makeDraggable(hud, {
      handle: document.getElementById("ks-mancing-header"),
      storageKey: "ks_hud_pos_mancing"
    });

    let minimized = false;
    document.getElementById("ks-mancing-toggle").onclick = () => {
      minimized = !minimized;
      document.getElementById("ks-mancing-content").style.display = minimized ? "none" : "block";
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

      setVal("ks-opt-loot-mode", mancingConfig.lootMode);
      setVal("ks-opt-sell-threshold", mancingConfig.sellThreshold.toFixed(2));
      setVal("ks-opt-stop-rule", mancingConfig.stopRule);

      setChk("ks-opt-natural", mancingConfig.modeNatural);
      setChk("ks-opt-zeroloss", mancingConfig.zeroLossGuard);
      setChk("ks-opt-auto-umpan", mancingConfig.autoUmpan);
      setChk("ks-opt-auto-upgrade", mancingConfig.autoUpgrade);
      setChk("ks-opt-jaring-lampu", mancingConfig.autoJaring || mancingConfig.autoLampu);
      setChk("ks-opt-auto-navigasi", mancingConfig.autoNavigasi);
      setChk("ks-opt-celup", mancingConfig.autoCelup);
      setChk("ks-opt-sentak", mancingConfig.autoSentak);
      setChk("ks-opt-gulung", mancingConfig.autoGulung);
      setChk("ks-opt-simpan", mancingConfig.autoSimpan);
      setChk("ks-opt-jual-penuh", mancingConfig.autoJualTasPenuh || mancingConfig.autoJualSampah);

      const settingsBody = document.getElementById("ks-settings-body");
      const chevron = document.getElementById("ks-settings-chevron");
      if (settingsBody) settingsBody.style.display = mancingConfig.settingsCollapsed ? "none" : "block";
      if (chevron) chevron.textContent = mancingConfig.settingsCollapsed ? "▸" : "▾";
    }

    function applyTemplatePreset(templateKey) {
      const preset = MANCING_TEMPLATES[templateKey];
      if (!preset) return;
      Object.assign(mancingConfig, preset);
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
    document.getElementById("ks-settings-toggle").onclick = () => {
      mancingConfig.settingsCollapsed = !mancingConfig.settingsCollapsed;
      syncHudControlsFromConfig();
      saveMancingSettings();
    };

    document.getElementById("ks-opt-natural").onchange = (e) => {
      mancingConfig.modeNatural = e.target.checked;
      markSettingsCustomized();
    };
    document.getElementById("ks-opt-zeroloss").onchange = (e) => {
      mancingConfig.zeroLossGuard = e.target.checked;
      markSettingsCustomized();
    };
    document.getElementById("ks-opt-loot-mode").onchange = (e) => {
      if (VALID_LOOT_MODES.has(e.target.value)) {
        mancingConfig.lootMode = e.target.value;
        markSettingsCustomized();
      }
    };
    document.getElementById("ks-opt-sell-threshold").onchange = (e) => {
      const parsed = parseFloat(e.target.value);
      if (VALID_SELL_THRESHOLDS.has(parsed)) {
        mancingConfig.sellThreshold = parsed;
        markSettingsCustomized();
      }
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
    const targetInfoEl = document.getElementById("ks-mancing-target-info");

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
        const jaringText = pancingProfile.hasJaring
          ? `Jaring ${pancingProfile.jaringSisa}/${pancingProfile.jaringHarian}`
          : "Tanpa Jaring";
        const lampuText = pancingProfile.hasLampu ? "Lampu Ada" : "Tanpa Lampu";
        statFiturKapalEl.textContent = `${jaringText} · ${lampuText}`;
        statFiturKapalEl.style.color = (pancingProfile.hasJaring || pancingProfile.hasLampu) ? "#4ade80" : "#94a3b8";
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

    if (sonarInfoEl && targetInfoEl) {
      const sonar = getSonarData();
      const target = getTargetDepth();
      sonarInfoEl.textContent = formatSonarText(sonar);
      targetInfoEl.textContent = `🎯 Target (${pancingProfile.joranNama}): ≥${target.minDepth}m (${target.targetFish})`;
    }

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
        const thresholdUnused =
          input.id === "ks-opt-sell-threshold" &&
          mancingConfig.lootMode === "jual-semua";
        const locked = !pancingProfile.loaded || noBoatSupport || thresholdUnused;
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
        el.style.background = active ? "rgba(168, 85, 247, 0.35)" : "rgba(15, 23, 42, 0.85)";
        el.style.borderColor = active
          ? "#c084fc"
          : (!mancingConfig.strategiUmpan ? "#f59e0b" : "rgba(192, 132, 252, 0.3)");
        el.style.color = active ? "#ffffff" : "#cbd5e1";
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
          tplDesc.textContent = "↳ Langsung gas pakai umpan apa saja yg terpasang (Cacing / Udang / Cumi / Ikan).";
        } else if (mancingConfig.strategiUmpan === "cumi") {
          tplDesc.textContent = "↳ Langsung pakai Cumi ke laut dalam ≥30m (Celup · 1.7×).";
        } else if (mancingConfig.strategiUmpan === "ternak-ikan") {
          tplDesc.textContent = "↳ Cacing dangkal (2–10m) ➔ kumpul 5 umpan-ikan ➔ ≥30m (2.3×).";
        } else {
          tplDesc.textContent = "Pilih template di atas untuk langsung mengisi Settings.";
        }
      }

      const summaryEl = document.getElementById("ks-settings-summary");
      if (summaryEl) {
        const lootText = mancingConfig.lootMode === "jual-semua"
          ? "Ikan > modal umpan dijual (kecuali ikan kecil jadi umpan)"
          : `Ikan ≥${mancingConfig.sellThreshold.toFixed(2)} dijual, <${mancingConfig.sellThreshold.toFixed(2)} disimpan`;
        const stopText = mancingConfig.stopRule === "sell-full"
          ? "stop 20/20 jual"
          : mancingConfig.stopRule === "bait-empty"
          ? "lanjut sampai umpan habis"
          : "stop 40/40 penuh";
        summaryEl.textContent = `↳ ${lootText} · ${stopText}.`;
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

    const todayCatches = pancingProfile.loaded
      ? Math.max(pancingProfile.dapat || 0, mancingStats.catches)
      : mancingStats.catches;
    if (countEl) {
      countEl.textContent = `${todayCatches} ekor`;
    }
    if (lastEl) {
      if (mancingStats.history.length > 0) {
        const itemsHtml = mancingStats.history.map((entry) => {
          if (typeof entry === "string") {
            return `<li style="margin: 2px 0; color: #e2e8f0;">${escapeHtml(entry)}</li>`;
          }
          if (entry && entry.text) {
            return `<li style="margin: 2px 0; color: #e2e8f0;">${escapeHtml(entry.text)}</li>`;
          }
          const profitVal = typeof entry.profit === "number" ? entry.profit : 0;
          const profitColor = profitVal >= 0 ? "#4ade80" : "#f87171";
          const profitSign = profitVal >= 0 ? "+" : "";
          const sellVal = typeof entry.sellPrice === "number" ? entry.sellPrice.toFixed(2) : "0.00";
          const weightPart = entry.weight ? ` <span style="color:#94a3b8;">(${escapeHtml(entry.weight)})</span>` : "";
          const badgeStyle = entry.isLoss
            ? "background:rgba(239,68,68,0.22);color:#fca5a5;"
            : "background:rgba(56,189,248,0.18);color:#7dd3fc;";
          const actionPart = entry.action
            ? ` <span style="${badgeStyle}padding:0 4px;border-radius:3px;font-size:9px;">${escapeHtml(entry.action)}</span>`
            : "";
          return `<li style="margin: 2px 0; line-height: 1.35; color: #f1f5f9;"><b>${escapeHtml(entry.name || "Ikan")}</b>${weightPart} · <span style="color:#fbbf24;">${sellVal}</span> · <b style="color:${profitColor};">${profitSign}${profitVal.toFixed(2)}</b>${actionPart}</li>`;
        }).join("");
        lastEl.innerHTML =
          `<div style="color: #94a3b8; font-weight: 600; margin-bottom: 2px;">🐟 Riwayat Hari Ini (${mancingStats.history.length}):</div>` +
          `<ul style="margin: 0; padding-left: 15px; max-height: 120px; overflow-y: auto; list-style-type: disc;">${itemsHtml}</ul>`;
      } else {
        lastEl.innerHTML = `<div style="color: #94a3b8; font-weight: 600;">Riwayat Hari Ini: -</div>`;
      }
    }

    const profitEl = document.getElementById("ks-mancing-profit");
    if (profitEl) {
      const p = mancingStats.totalProfit;
      const sign = p >= 0 ? "+" : "";
      profitEl.textContent = `💰 Laba Hari Ini: ${sign}${p.toFixed(2)} koin`;
      profitEl.style.color = p >= 0 ? "#4ade80" : "#f87171";
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

    const lootStepLabel = mancingConfig.lootMode === "jual-semua"
      ? "Jual Semua"
      : `Jual ≥${mancingConfig.sellThreshold.toFixed(2)}`;

    if (mancingConfig.strategiUmpan === "just-go") {
      const activeName = getUmpanShortName(equipped);
      const g1Done = stok > 0;
      const g2Done = g1Done && sonar.depth >= target.minDepth && sonar.crowd !== "Sepi";
      const activeJustGo = !g1Done ? 1 : !g2Done ? 2 : 3;
      const markG = (n, done) => (done ? "✅" : activeJustGo === n ? "▶️" : "⚪");

      planEl.innerHTML =
        `<div><b>📋 Plan Just Go (${escapeHtml(activeName)}):</b></div>` +
        `<div>${markG(1, g1Done)} 1. Umpan Aktif (${Math.max(0, stok)}) · ${markG(2, g2Done)} 2. Ke ≥${target.minDepth}m (5/5) · ${markG(3, false)} 3. Celup &amp; ${lootStepLabel}</div>`;
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
        `<div>${mark(3, s3Done)} 3. Ke ≥30m (5/5) · ${mark(4, false)} 4. Celup 2.3× &amp; ${lootStepLabel}</div>`;
      return;
    }

    const c1Done = stok > 0;
    const c2Done = c1Done && sonar.depth >= target.minDepth && sonar.crowd !== "Sepi";
    const activeCumi = !c1Done ? 1 : !c2Done ? 2 : 3;
    const markC = (n, done) => (done ? "✅" : activeCumi === n ? "▶️" : "⚪");

    planEl.innerHTML =
      `<div><b>📋 Plan Langsung Cumi:</b></div>` +
      `<div>${markC(1, c1Done)} 1. Siap Cumi · ${markC(2, c2Done)} 2. Ke ≥30m (5/5) · ${markC(3, false)} 3. Celup &amp; ${lootStepLabel}</div>`;
  }

  function updateStatusMsg(title, detail, color = "#38bdf8") {
    const statusEl = document.getElementById("ks-mancing-status");
    const detailEl = document.getElementById("ks-mancing-detail");
    if (statusEl) {
      statusEl.textContent = title;
      statusEl.style.color = color;
    }
    if (detailEl && detail) {
      detailEl.textContent = detail;
    }
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
      }
    } else if (hasilCard || fase === "dapat") {
      if (activeCastState) {
        activeCastState.caught = true;
        activeCastState.closed = true;
      }
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
              ? "gagal"
              : "dimakan";
          recordBaitLoss({ reason, umpan: endedCast.baitType });
        }, 450);
      }
    }

    if (!mancingConfig.autoMancing) return;

    // 1. Fase Tangkapan Selesai (Hasil Ikan)
    if (hasilCard || fase === "dapat") {
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
      stopAutopilot();
      if (mancingConfig.autoGulung) {
        const barTali = document.querySelector('[data-testid="pancing-bar-tali"]');
        const barIkan = document.querySelector('[data-testid="pancing-bar-ikan"]');
        const isRed = barTali ? barTali.hasAttribute("data-merah") : false;
        const isYellow = barTali ? barTali.hasAttribute("data-kuning") : false;
        const tension = barTali ? parseFloat(barTali.style.width) || 0 : 0;
        const progress = barIkan ? parseFloat(barIkan.style.width) || 0 : 0;

        // Hysteresis Long-Hold (Zero-Loss bawaan):
        // Tarik acak di 29-45% -> Lepas acak di 70-85% (aman anti-putus: lepas segera bila zona merah > 160ms atau >= 85%)
        const nowReel = performance.now();
        if (isRed) {
          if (!redDangerSince) redDangerSince = nowReel;
        } else {
          redDangerSince = 0;
        }
        const redGuardTriggered = mancingConfig.zeroLossGuard && isRed && (tension >= 85 || (nowReel - redDangerSince) >= 160);
        const hitCeiling = tension >= reelTargetMax || redGuardTriggered;
        if (hitCeiling) {
          if (!reelCoolingDown) {
            reelCoolingDown = true;
            reelTargetMin = rollReelMin();
          }
          releaseGulung();
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
          // Sedang dalam fase tahan panjang (menuju reelTargetMax): pastikan tombol tetap tertahan
          const btnGulung = document.querySelector('[data-testid="pancing-gulung"]');
          const isHolding = !!(btnGulung && btnGulung.hasAttribute("data-tahan"));
          if (!isGulungActive || (mancingConfig.zeroLossGuard && !isHolding)) {
            holdGulung();
          }
        }

        const color = isRed ? "#ef4444" : isYellow ? "#eab308" : "#22c55e";
        const stateText = isRed
          ? "(BAHAYA: Melepas)"
          : reelCoolingDown
          ? `(Melepas ➔ ${reelTargetMin}%)`
          : `(Tahan Panjang ➔ ${reelTargetMax}%)`;
        updateStatusMsg(
          `🔄 Adu Tarik: Ikan ${progress.toFixed(0)}%`,
          `Tegangan: ${tension.toFixed(0)}% ${stateText}`,
          color
        );
      }
      return;
    }

    // 4. Fase Jalan / Diam (Siap Menurunkan Kail / Celup)
    if (fase === "jalan" || fase === "diam") {
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

        // Prioritaskan ganti gratis ke umpan MILIK SENDIRI dulu:
        const umpanIkanStok = getOwnedBaitStock("umpan-ikan");
        const cacingStok = getOwnedBaitStock("umpan-cacing");
        if (mancingConfig.strategiUmpan === "just-go") {
          const ownedPriority = [
            ...(mancingConfig.autoUmpanIkan ? ["umpan-ikan"] : []),
            "umpan-cumi",
            "umpan-udang",
            "umpan-cacing"
          ];
          const nextOwned = ownedPriority.find((id) => getOwnedBaitStock(id) > 0);
          if (nextOwned) {
            scheduleSwitchOwnedBait(nextOwned);
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
        } else if (mancingConfig.autoUmpanIkan && umpanIkanStok > 0) {
          scheduleSwitchOwnedBait("umpan-ikan");
          return;
        }

        if (mancingConfig.autoUmpan) {
          scheduleAutoBuyUmpan();
          return;
        }

        toggleAutoMancing(false, {
          title: "⚠️ Umpan Habis!",
          detail: "Umpan terakhir selesai & stok 0. Aktifkan Auto Beli Umpan atau beli manual di toko lalu klik Mulai.",
          color: "#f59e0b"
        });
        return;
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
          updateStatusMsg("🐟 Batch Umpan Siap!", `${umpanIkanStok} umpan-ikan terkumpul — ganti umpan & berlayar ke ≥30m...`, "#22c55e");
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

        if (bestSpot && liveShipData.synced) {
          const dx = bestSpot.x - liveShipData.x;
          const dz = bestSpot.z - liveShipData.z;
          const dist = Math.hypot(dx, dz);

          // Prioritas utama: langsung berhenti begitu Sonar mencapai 5/5 bar (tidak perlu paksa dead center).
          // Jika spot terbaik tidak bisa 5 bar (mis. kaya < 0.78), tetap melaju menuju inti spot (~5-8m dari pusat)
          // agar dapat sinyal tertinggi tanpa berhenti prematur di pinggiran Ramai (3-4 bar).
          const coreRadius = Math.min(8, Math.max(5, (bestSpot.r || 30) * 0.25));
          const reachedFiveBars = typeof sonar.bars === "number" && sonar.bars >= 5 && inDepthRange;
          const reachedSpotCore = dist <= coreRadius && inDepthRange;
          const reachedLumayanFallback = !bestSpot.isRamai && sonar.crowd === "Lumayan" && inDepthRange;
          const reachedOptimalDepth =
            !bestSpot.isRamai &&
            sonar.depth >= target.optimalDepth &&
            (target.maxDepth == null || sonar.depth <= target.maxDepth) &&
            sonar.crowd !== "Sepi";

          if (!reachedFiveBars && !reachedSpotCore && !reachedLumayanFallback && !reachedOptimalDepth) {
            startAutopilotToSpot(bestSpot, liveShipData.x, liveShipData.z, liveShipData.h);
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
                : `Inti Spot Dicapai: ${formatSonarText(sonar)}!`
            );
            return;
          }
        } else {
          // Fallback navigasi jika telemetri/titik belum sinkron
          if (!inDepthRange && sonar.depth < target.minDepth) {
            if (!isNavigating) {
              isNavigating = true;
              navStartTime = performance.now();
            }
            steerShip(1, 0);
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
      const targetCastBtn = useLemparForTernak ? findLemparButton() : findCelupButton();
      if (targetCastBtn && !isCelupButtonReady(targetCastBtn)) {
        const nowDisabled = performance.now();
        if (!castButtonDisabledSince) castButtonDisabledSince = nowDisabled;
        const disabledMs = nowDisabled - castButtonDisabledSince;
        const btnName = useLemparForTernak ? "Lempar" : "Celup";
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
        useLemparForTernak ? "🎣 Lempar Cacing (Cari Ikan Kecil)..." : "⬇️ Menurunkan Kail (Celup)...",
        useLemparForTernak ? "Mencari ikan kecil untuk umpan-ikan 2.3×..." : "Jeda alami mencelupkan kail ke laut dalam...",
        "#38bdf8"
      );
      if (mancingConfig.autoCelup) {
        scheduleNaturalCelup(useLemparForTernak);
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
