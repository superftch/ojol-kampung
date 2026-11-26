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
    smartProfit: true,       // Strategi 40+ slot (20 Jual + Tas): Jual ikan besar (>=1.4 koin), simpan/cadangkan sedang, stop saat penuh
    selectiveRelease: true,  // Max Cuan: lepas ikan murah (<1.0 koin) jika koin/umpan aman agar slot terisi ikan mahal
    autoJaring: true,        // Otomatis tebar jaring untuk dapat umpan gratis harian
    autoLampu: true,         // Otomatis nyalakan lampu kapal saat malam (18.30 - 04.30) agar ikan lebih ramai
    singleRodProfit: true,   // Max Cuan: pertahankan 1 joran (1 umpan/celup) agar tidak boros umpan 2x-3x
    autoJualTasPenuh: true,  // Jika tas ikan penuh, otomatis jual agar tangkapan tidak sia-sia
    autoJualSampah: true,    // Otomatis buang/jual sampah laut (Sandal jepit, dll)
    autoUmpan: true,         // Otomatis beli umpan paling worth it (Cumi / Udang) saat habis
    autoUmpanIkan: true,     // Jadikan ikan kecil sebagai umpan-ikan (besar 2.3x) & prioritaskan pakai stoknya
    autoUpgrade: true,       // Otomatis beli upgrade joran & pendingin bernilai tinggi (ROI Max)
    autoNavigasi: true,      // Otomatis arahkan & kemudikan kapal ke kedalaman paling worth it sesuai umpan & joran
    preferredUmpan: "umpan-cumi", // "umpan-cumi" (Paling Cuan) / "umpan-udang" (Hemat Modal) / "umpan-cacing" (Ternak Umpan Ikan)
    strategiUmpan: "",           // Wajib dipilih sebelum mulai: "cumi" | "ternak-ikan"
    baseMaxTension: 80,      // % max sebelum lepas gulung (batas putus game di 85%)
    baseMinTension: 61       // % min sebelum gulung kembali (batas lepas game di <8%)
  };

  const DAILY_STATS_KEY = "ks_mancing_daily_stats";

  function getTodayWibKey() {
    const wib = new Date(Date.now() + 7 * 3600 * 1000);
    return wib.toISOString().slice(0, 10);
  }

  const mancingStats = {
    catches: 0,
    released: 0,
    jaringUsed: 0,
    totalProfit: 0,
    lastFish: null,
    history: [],
    umpanDibeli: 0,
    upgradeTerpasang: []
  };

  function loadDailyMancingStats() {
    try {
      const raw = localStorage.getItem(DAILY_STATS_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw);
      if (parsed && parsed.date === getTodayWibKey()) {
        if (typeof parsed.catches === "number") mancingStats.catches = parsed.catches;
        if (typeof parsed.totalProfit === "number") mancingStats.totalProfit = parsed.totalProfit;
        if (typeof parsed.lastFish === "string") mancingStats.lastFish = parsed.lastFish;
      }
    } catch (_) {}
  }

  function saveDailyMancingStats() {
    try {
      localStorage.setItem(DAILY_STATS_KEY, JSON.stringify({
        date: getTodayWibKey(),
        catches: mancingStats.catches,
        totalProfit: mancingStats.totalProfit,
        lastFish: mancingStats.lastFish
      }));
    } catch (_) {}
  }

  loadDailyMancingStats();

  let isGulungActive = false;
  let isNavigating = false;
  let navStartTime = 0;
  let lastCelupTime = 0;
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
    if (!isGulungActive) return;
    isGulungActive = false;
    const btn = document.querySelector('[data-testid="pancing-gulung"]');
    if (btn) {
      btn.dispatchEvent(new PointerEvent("pointerup", { bubbles: true, pointerId: 0, pointerType: "mouse" }));
      btn.dispatchEvent(new PointerEvent("pointercancel", { bubbles: true, pointerId: 0, pointerType: "mouse" }));
    }
    window.dispatchEvent(new KeyboardEvent("keyup", { code: "Space", key: " ", bubbles: true }));
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
      }, humanJitter(70, 140));
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

  // Celup / Lempar Kail Alami (jeda 2.2s - 3.8s)
  function scheduleNaturalCelup(useLempar = false) {
    if (castPending) return;
    const now = performance.now();
    const cooldown = mancingConfig.modeNatural ? humanJitter(2200, 3800) : 1200;
    if (now - lastCelupTime < cooldown) return;

    const btnCast = useLempar ? findLemparButton() : findCelupButton();
    if (!isCelupButtonReady(btnCast)) return;

    castPending = true;
    lastCelupTime = now;

    setTimeout(() => {
      const btn = useLempar ? findLemparButton() : findCelupButton();
      if (isCelupButtonReady(btn)) {
        naturalClick(btn);
      }
      castPending = false;
    }, mancingConfig.modeNatural ? humanJitter(160, 360) : 30);
  }

  function getEquippedUmpanType() {
    const btnUmpan = document.querySelector('[data-testid="pancing-umpan"]');
    const label = (btnUmpan?.textContent || "").toLowerCase();
    if (label.includes("ikan")) return "umpan-ikan";
    if (label.includes("cumi")) return "umpan-cumi";
    if (label.includes("udang")) return "umpan-udang";
    if (label.includes("cacing")) return "umpan-cacing";
    return mancingConfig.preferredUmpan;
  }

  function getActiveUmpanCost() {
    const active = getEquippedUmpanType();
    if (active === "umpan-ikan") return 0.00;
    if (active === "umpan-cumi") return 0.50;
    if (active === "umpan-udang") return 0.30;
    if (active === "umpan-cacing") return 0.20;
    return 0.50;
  }

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
    saldoKoin,
    stokUmpan,
    config,
    availableButtons
  }) {
    if (isTrash && config.autoJualSampah) {
      if (availableButtons.buang) return "BUANG";
      if (availableButtons.jual) return "JUAL_SAMPAH";
    }

    if (config.autoUmpanIkan && isSmallFish && availableButtons.umpanIkan) {
      return "JADIKAN_UMPAN";
    }

    const isHighValue = Boolean(isBigClass) || sellPrice >= 1.00;
    const isLowValue = !isHighValue && sellPrice < 1.00;
    const sisaTotal = sisaJual + sisaTas;
    const hasSafeReserve = saldoKoin >= 5.0 || stokUmpan >= 5 || !pancingProfile.loaded;

    if (config.smartProfit) {
      if (config.selectiveRelease && isLowValue && hasSafeReserve && sisaTotal > 2 && availableButtons.lepas) {
        return "LEPAS";
      }

      if ((config.autoJual || isHighValue) && sisaJual > 0 && availableButtons.jual) {
        return "JUAL";
      }

      if (config.autoSimpan && sisaTas > 0 && availableButtons.simpan) {
        return "SIMPAN";
      }

      if (config.autoJualTasPenuh && sisaJual > 0 && availableButtons.jual) {
        if (config.selectiveRelease && sellPrice < baitCost && hasSafeReserve && sisaJual > 2 && availableButtons.lepas) {
          return "LEPAS";
        }
        return "JUAL_TAS_PENUH";
      }
    } else {
      if (config.autoJual && sisaJual > 0 && availableButtons.jual) return "JUAL";
      if (config.autoSimpan && sisaTas > 0 && availableButtons.simpan) return "SIMPAN";
      if (config.autoJualTasPenuh && sisaJual > 0 && availableButtons.jual) return "JUAL_TAS_PENUH";
    }

    if (availableButtons.makan) return "MAKAN";
    if (availableButtons.lepas) return "LEPAS";
    return "NONE";
  }

  // Penanganan Hasil Tangkapan (Zero-Loss & Max Cuan Selective 40+ Slot)
  function handleCatch(hasilCard) {
    if (lootPending) return;

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
    const baitCost = getActiveUmpanCost();
    const profit = sellPrice - baitCost;
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

    if (lastCatchId !== key) {
      lastCatchId = key;
      mancingStats.catches++;
      mancingStats.totalProfit += profit;
      mancingStats.lastFish = `${fishName} (${fishWeight}) ➔ Profit: ${profitText} (Jual: ${sellPrice.toFixed(2)} koin)`;
      mancingStats.history.unshift(`${fishName} (${fishWeight}) | Jual ${sellPrice.toFixed(2)} | Profit ${profitText}`);
      if (mancingStats.history.length > 5) mancingStats.history.pop();
      saveDailyMancingStats();
      updateMancingUI();
    }

    lootPending = true;
    // Jeda observasi manusiawi membaca kartu ikan: 1.4s - 2.5s
    const readDelay = mancingConfig.modeNatural ? humanJitter(1400, 2500) : 500;

    function executeLootClick(btn, actionType, statusTitle, statusDetail, color) {
      if (statusTitle) updateStatusMsg(statusTitle, statusDetail, color || "#38bdf8");
      naturalClick(btn, (clicked) => {
        if (clicked) {
          if (actionType === "jual") {
            pancingProfile.jualHariIni = Math.min(pancingProfile.jualMaks, pancingProfile.jualHariIni + 1);
          } else if (actionType === "simpan") {
            pancingProfile.tasIkan = Math.min(pancingProfile.tasMaks, pancingProfile.tasIkan + 1);
          } else if (actionType === "lepas") {
            mancingStats.released++;
            // Karena dilepas (tidak dijual/disimpan), koreksi estimasi profit hari ini agar akurat (-baitCost saja)
            mancingStats.totalProfit -= sellPrice;
            saveDailyMancingStats();
          }
          updateMancingUI();
        }
        lootPending = false;
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
          "#22c55e"
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

  // Helper: Ambil data Sonar dari HUD game (kedalaman meter & keramaian)
  function getSonarData() {
    const sonarEl = document.querySelector('[data-testid="pancing-sonar"]');
    if (!sonarEl) return { depth: 0, crowd: "unknown", raw: "" };

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

    return { depth, crowd, raw: aria || text };
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

  let liveShipData = { x: 0, z: -46, h: Math.PI, laju: 0, titik: [] };
  window.addEventListener("ks_mancing_data_update", (e) => {
    if (e.detail) {
      liveShipData = { ...liveShipData, ...e.detail };
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

  // Batas resmi game untuk status "Ramai": rame >= 0.45 (Sepi < 0.20, Lumayan < 0.45, Ramai >= 0.45)
  const RAMAI_MIN_KAYA = 0.45;

  function rankFishingAreas(spots, shipX, shipZ, target = null) {
    if (!spots || spots.length === 0) return [];

    const activeTarget = target || getTargetDepth();
    const minDepth = activeTarget.minDepth || 0;
    const minReachableZ = -640 - Math.max(0, pancingProfile.lepasM || 0);
    const reachableSpots = spots.filter(s => s.z >= minReachableZ);
    const pool = reachableSpots.length > 0 ? reachableSpots : spots;

    const ranked = pool.map(s => {
      const d = calcDepth(s.x, s.z);
      const dist = Math.hypot(s.x - shipX, s.z - shipZ);
      const meetsDepth = d >= minDepth;
      const isRamai = (s.kaya || 0) >= RAMAI_MIN_KAYA;
      const tier = (meetsDepth && isRamai) ? 3 : meetsDepth ? 2 : isRamai ? 1 : 0;
      const depthBonus = d >= 34 ? 140 : d >= 30 ? 120 : d >= 24 ? 80 : d >= 15 ? 40 : d;
      const score = (tier * 1000) + ((s.kaya || 0) * 400) + depthBonus - (dist * 0.05);
      return { ...s, depth: d, dist, tier, isRamai, meetsDepth, score };
    });

    ranked.sort((a, b) => b.score - a.score);
    return ranked;
  }

  function findBestCrowdedSpot(spots, shipX, shipZ, target = null) {
    const ranked = rankFishingAreas(spots, shipX, shipZ, target);
    return ranked.length > 0 ? ranked[0] : null;
  }

  let activeTurnPulseTimer = null;
  let lastRecordedShipH = null;
  let shipHStuckCount = 0;

  function steerShip(gas, belok) {
    // 1. Direct engine steering via inject.js (bypass simulasi keyboard)
    window.dispatchEvent(new CustomEvent("ks_mancing_steer", {
      detail: { gas: gas || 0, belok: belok || 0 }
    }));

    // 2. Keyboard fallback gas maju (W / ArrowUp)
    if (gas > 0) {
      window.dispatchEvent(new KeyboardEvent("keydown", { code: "KeyW", key: "w", bubbles: true }));
      window.dispatchEvent(new KeyboardEvent("keydown", { code: "ArrowUp", key: "ArrowUp", bubbles: true }));
    } else {
      window.dispatchEvent(new KeyboardEvent("keyup", { code: "KeyW", key: "w", bubbles: true }));
      window.dispatchEvent(new KeyboardEvent("keyup", { code: "ArrowUp", key: "ArrowUp", bubbles: true }));
    }

    // 3. Pulsed Micro-Steering (Watchdog Pulse 140ms):
    // Game Three.js memiliki akselerasi putar h += 0.7*belok*dt.
    // Menahan KeyA terus-menerus membuat kapal berputar liar (looping).
    // Gunakan ketukan kemudi (micro-tap) dengan auto-release 140ms.
    if (activeTurnPulseTimer) {
      clearTimeout(activeTurnPulseTimer);
      activeTurnPulseTimer = null;
    }

    if (belok === 0) {
      window.dispatchEvent(new KeyboardEvent("keyup", { code: "KeyA", key: "a", bubbles: true }));
      window.dispatchEvent(new KeyboardEvent("keyup", { code: "KeyD", key: "d", bubbles: true }));
      window.dispatchEvent(new KeyboardEvent("keyup", { code: "ArrowLeft", key: "ArrowLeft", bubbles: true }));
      window.dispatchEvent(new KeyboardEvent("keyup", { code: "ArrowRight", key: "ArrowRight", bubbles: true }));
    } else if (belok > 0) {
      // Belok kiri pulse
      window.dispatchEvent(new KeyboardEvent("keyup", { code: "KeyD", key: "d", bubbles: true }));
      window.dispatchEvent(new KeyboardEvent("keydown", { code: "KeyA", key: "a", bubbles: true }));
      activeTurnPulseTimer = setTimeout(() => {
        window.dispatchEvent(new KeyboardEvent("keyup", { code: "KeyA", key: "a", bubbles: true }));
        window.dispatchEvent(new CustomEvent("ks_mancing_steer", {
          detail: { gas: gas || 0, belok: 0 }
        }));
      }, 140);
    } else if (belok < 0) {
      // Belok kanan pulse
      window.dispatchEvent(new KeyboardEvent("keyup", { code: "KeyA", key: "a", bubbles: true }));
      window.dispatchEvent(new KeyboardEvent("keydown", { code: "KeyD", key: "d", bubbles: true }));
      activeTurnPulseTimer = setTimeout(() => {
        window.dispatchEvent(new KeyboardEvent("keyup", { code: "KeyD", key: "d", bubbles: true }));
        window.dispatchEvent(new CustomEvent("ks_mancing_steer", {
          detail: { gas: gas || 0, belok: 0 }
        }));
      }, 140);
    }
  }

  function startAutopilotToSpot(spot, shipX, shipZ, shipH) {
    if (!isNavigating) {
      isNavigating = true;
      navStartTime = performance.now();
      lastRecordedShipH = shipH;
      shipHStuckCount = 0;
    }
    currentTargetSpot = spot;

    // Deteksi jika data heading belum ter-update atau macet
    if (lastRecordedShipH !== null && Math.abs(shipH - lastRecordedShipH) < 0.001) {
      shipHStuckCount++;
    } else {
      shipHStuckCount = 0;
      lastRecordedShipH = shipH;
    }

    const dx = spot.x - shipX;
    const dz = spot.z - shipZ;
    const dist = Math.hypot(dx, dz);

    const targetHeading = Math.atan2(dx, dz);
    let diff = (targetHeading - shipH + Math.PI) % (2 * Math.PI);
    if (diff < 0) diff += 2 * Math.PI;
    diff -= Math.PI;

    let belok = 0;
    // Anti-Spin Guard: Jika shipH belum sinkron dari engine (> 10 tick sama),
    // jangan pernah belok kiri/kanan! Perahu di dermaga otomatis menghadap Utara (laut dalam),
    // melaju lurus adalah rute paling tepat dan stabil.
    if (shipHStuckCount > 10) {
      belok = 0;
    } else {
      // Deadband 0.15 rad (~8.5 derajat): jika sudah searah toleransi, lurus saja
      if (diff > 0.15) belok = 1;       // Belok kiri
      else if (diff < -0.15) belok = -1; // Belok kanan
    }

    steerShip(1, belok);

    updateStatusMsg(
      "🧭 Menuju Spot Ramai...",
      `Jarak ${Math.round(dist)}m (${(spot.kaya * 100).toFixed(0)}% kaya, ${Math.round(spot.depth)}m)`,
      "#00e5ff"
    );
  }

  function stopAutopilot(reasonMsg) {
    if (isNavigating) {
      isNavigating = false;
      currentTargetSpot = null;
      if (activeTurnPulseTimer) {
        clearTimeout(activeTurnPulseTimer);
        activeTurnPulseTimer = null;
      }
      steerShip(0, 0);
      if (reasonMsg) {
        updateStatusMsg("🎯 Tiba di Spot Ramai!", reasonMsg, "#22c55e");
      }
    }
  }

  // 1. Auto Beli Umpan Paling Worth It (Cumi / Udang) dengan Natural Human Jitter
  function scheduleAutoBuyUmpan() {
    if (autoUmpanPending) return;
    autoUmpanPending = true;

    updateStatusMsg("🛒 Beli Umpan...", "Membuka toko umpan...", "#38bdf8");

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
            updateMancingUI();
          }, getActionDelay(0));
        }, getActionDelay(0));
      }

      // 1. Cek stok Umpan Ikan Hidup (umpan-ikan, gratis & 2.3x ikan besar) -> pakai dulu sebelum beli
      if (mancingConfig.autoUmpanIkan) {
        const ikan = readShopBaitStok("umpan-ikan");
        if (ikan.btnPilih && !ikan.btnPilih.disabled && ikan.stok > 0) {
          equipExistingBait(ikan.btnPilih, `Ikan Kecil Hidup (${ikan.stok})`);
          return;
        }
      }

      // 2. Cek apakah umpan strategi target (atau umpan lain pada mode cumi) sudah punya stok > 0 -> pakai dulu, JANGAN BELI!
      const isTernakMode = mancingConfig.strategiUmpan === "ternak-ikan";
      const targetPrefCheck = isTernakMode
        ? "umpan-cacing"
        : mancingConfig.preferredUmpan;
      const checkOrder = (isTernakMode
        ? ["umpan-cacing"]
        : [targetPrefCheck, "umpan-cumi", "umpan-udang", "umpan-cacing"]
      ).filter((v, idx, arr) => v && arr.indexOf(v) === idx);

      for (const baitId of checkOrder) {
        const info = readShopBaitStok(baitId);
        if (info.btnPilih && !info.btnPilih.disabled && info.stok > 0) {
          equipExistingBait(info.btnPilih, `${baitId} (${info.stok})`);
          return;
        }
      }

      // Step 2: Pilih paket jumlah (pilih 5 jika sisa kuota slot tinggal <= 5 atau saldo < 5, selain itu 10)
      setTimeout(() => {
        const qtyButtons = Array.from(sheetToko.querySelectorAll('button[role="radio"]'));
        const btn10 = qtyButtons.find(b => b.textContent.trim() === "10");
        const btn5 = qtyButtons.find(b => b.textContent.trim() === "5");
        const sisaSlot = pancingProfile.loaded
          ? Math.max(0, pancingProfile.jualMaks - pancingProfile.jualHariIni) + Math.max(0, pancingProfile.tasMaks - pancingProfile.tasIkan)
          : 40;
        const lowCoinPack5 = pancingProfile.loaded && pancingProfile.saldoKoin < 5.0;
        const preferPack5 = (mancingConfig.smartProfit && sisaSlot > 0 && sisaSlot <= 5) || lowCoinPack5;
        if (preferPack5 && btn5) naturalClick(btn5);
        else if (btn10) naturalClick(btn10);
        else if (btn5) naturalClick(btn5);

        // Step 3: Klik tombol beli umpan target
        setTimeout(() => {
          // Selector resmi KampungSebelah: data-testid="pancing-beli-cumi", "pancing-beli-udang", "pancing-beli-cacing"
          const btnBeliCumi = sheetToko.querySelector('[data-testid="pancing-beli-cumi"], [data-testid="pancing-beli-umpan-cumi"]');
          const btnBeliUdang = sheetToko.querySelector('[data-testid="pancing-beli-udang"], [data-testid="pancing-beli-umpan-udang"]');
          const btnBeliCacing = sheetToko.querySelector('[data-testid="pancing-beli-cacing"], [data-testid="pancing-beli-umpan-cacing"]');

          let targetBeli = null;
          let namaUmpan = "Umpan Cumi";
          let targetPilihId = "cumi";
          const targetPref = mancingConfig.strategiUmpan === "ternak-ikan"
            ? "umpan-cacing"
            : mancingConfig.preferredUmpan;

          if (targetPref === "umpan-cacing" && btnBeliCacing && !btnBeliCacing.disabled) {
            targetBeli = btnBeliCacing;
            namaUmpan = "Cacing Laut (Ternak Umpan Ikan)";
            targetPilihId = "cacing";
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
            mancingStats.umpanDibeli += 10;

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
                  updateMancingUI();
                }, getActionDelay(0));
              }, getActionDelay(0));
            }, getActionDelay(0));
          } else {
            // Saldo koin tidak cukup untuk beli umpan
            updateStatusMsg("⚠️ Saldo Koin Kurang!", "Tidak cukup koin untuk beli umpan", "#ef4444");
            setTimeout(() => {
              const btnTutup = sheetToko.querySelector('button[aria-label="Tutup"], button[class*="tutup"]');
              if (btnTutup) naturalClick(btnTutup);
              setTimeout(() => {
                autoUmpanPending = false;
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
    // Tunggu natural jitter hingga sheet toko muncul di layar
    setTimeout(() => {
      const sheetToko = document.querySelector('[data-testid="pancing-toko"]');
      if (sheetToko) {
        proceedInShop(sheetToko);
      } else {
        autoUmpanPending = false;
      }
    }, getActionDelay(0));
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

      if (mancingConfig.smartProfit && sisaJual === 0 && sisaTas === 0) {
        stopStatusOverride = {
          title: "🏆 Kuota Harian Maksimal (40/40)!",
          detail: "20/20 terjual & 20/20 tas penuh. Nonaktifkan Smart Profit jika tetap ingin memancing.",
          color: "#f59e0b"
        };
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

        <!-- Tombol Utama Start / Stop -->
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
          <div id="ks-mancing-last" style="font-size: 10px; color: #94a3b8; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">Terakhir: -</div>
        </div>

        <!-- Live Sonar & Target -->
        <div style="background: rgba(14, 165, 233, 0.12); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 6px; padding: 5px 8px; margin-bottom: 7px; font-size: 10.5px;">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span style="color: #38bdf8;">📡 Sonar:</span>
            <b id="ks-mancing-sonar-info" style="color: #4ade80;">Membaca...</b>
          </div>
          <div id="ks-mancing-target-info" style="font-size: 10px; color: #cbd5e1; margin-top: 1px;">
            🎯 Target: Membaca...
          </div>
        </div>

        <!-- Strategi Max Profit -->
        <div style="background: rgba(168, 85, 247, 0.12); border: 1px solid rgba(168, 85, 247, 0.35); border-radius: 6px; padding: 6px 8px; margin-bottom: 7px; font-size: 10.5px;">
          <div style="font-weight: bold; color: #c084fc; font-size: 10.5px; margin-bottom: 4px;">💡 Strategi Paling Cuan (Max Profit):</div>
          <select id="ks-opt-strategi-umpan" title="Wajib pilih strategi sebelum mulai. Mengatur jenis umpan yang dibeli/dipakai, kedalaman tujuan, dan mode Lempar/Celup." style="width: 100%; margin-bottom: 5px; padding: 4px 6px; border-radius: 5px; border: 1px solid #f59e0b; background: rgba(15, 23, 42, 0.9); color: #f3e8ff; font-size: 10.5px; font-weight: bold; cursor: pointer;">
            <option value="" selected>-- Pilih Strategi Mancing --</option>
            <option value="cumi" title="Pakai Umpan Cumi (0.5 koin, 1.7x ikan besar) langsung di laut dalam ≥30m. Tercepat per jam.">🦑 Langsung Cumi (Cepat · 1.7×)</option>
            <option value="ternak-ikan" title="Pakai Cacing (0.2 koin) Lempar di dangkal untuk kumpulkan 5 umpan-ikan (2.3x ikan besar), lalu Celup di ≥30m.">🐟 Ternak Umpan Ikan (Cacing ➔ 2.3×)</option>
          </select>
          <div style="display: flex; flex-direction: column; gap: 3px;">
            <label title="Otomatis membeli upgrade Joran terbaik (Samudra → Tonda → Karang) dan Kotak Pendingin (+slot tas) saat koin cukup (sisakan min. 10 koin)." style="display: flex; align-items: center; gap: 5px; cursor: pointer;">
              <input type="checkbox" id="ks-opt-auto-upgrade" checked style="cursor: pointer;">
              <span style="color: #f3e8ff;">🎣 Auto Upgrade (Joran &amp; Pendingin)</span>
            </label>
            <label title="Otomatis tebar Jaring untuk umpan gratis harian &amp; nyalakan Lampu Kapal saat malam (18.30–04.30). Aktif jika kapal memiliki fitur tersebut." style="display: flex; align-items: center; gap: 5px; cursor: pointer;">
              <input type="checkbox" id="ks-opt-jaring-lampu" checked style="cursor: pointer;">
              <span style="color: #86efac;">🕸️ Auto Jaring Gratis &amp; Lampu Malam</span>
            </label>
            <label title="Otomatis mengemudikan kapal ke spot Ramai (≥45%) dengan kedalaman target terbaik sesuai batas kapal &amp; joran." style="display: flex; align-items: center; gap: 5px; cursor: pointer;">
              <input type="checkbox" id="ks-opt-auto-navigasi" checked style="cursor: pointer;">
              <span style="color: #67e8f9;">🧭 Autopilot Kapal (Spot Paling Worth It)</span>
            </label>
          </div>
        </div>

        <!-- Opsi Aksi & Proteksi (Grid 2 Kolom Kompak) -->
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px 6px; margin-bottom: 6px; font-size: 10.5px; color: #cbd5e1;">
          <label title="Menambahkan variasi refleks manusiawi (220–380ms sentak, 1.4–2.5s baca hasil, klik koordinat acak)." style="display: flex; align-items: center; gap: 4px; cursor: pointer;">
            <input type="checkbox" id="ks-opt-natural" checked style="cursor: pointer;">
            <span>🌿 Natural</span>
          </label>
          <label title="Menjaga tegangan tali tetap aman (78–82% lepas saat merah, 59–63% tarik + auto-hold) agar tali tidak putus dan ikan tidak lepas." style="display: flex; align-items: center; gap: 4px; cursor: pointer;">
            <input type="checkbox" id="ks-opt-zeroloss" checked style="cursor: pointer;">
            <span>🛡️ Zero-Loss</span>
          </label>
          <label title="Otomatis menurunkan kail (Celup di laut dalam, atau Lempar saat mode Cacing dangkal)." style="display: flex; align-items: center; gap: 4px; cursor: pointer;">
            <input type="checkbox" id="ks-opt-celup" checked style="cursor: pointer;">
            <span>⬇️ Auto Celup</span>
          </label>
          <label title="Otomatis menyentak kail begitu ikan menyambar (jauh di bawah batas waktu 10 detik server)." style="display: flex; align-items: center; gap: 4px; cursor: pointer;">
            <input type="checkbox" id="ks-opt-sentak" checked style="cursor: pointer;">
            <span>⚡ Auto Sentak</span>
          </label>
          <label title="Otomatis menggulung dan melepas gulungan selama fase Adu Tarik." style="display: flex; align-items: center; gap: 4px; cursor: pointer;">
            <input type="checkbox" id="ks-opt-gulung" checked style="cursor: pointer;">
            <span>🔄 Auto Gulung</span>
          </label>
          <label title="Izinkan menyimpan ikan ke Tas saat tidak langsung dijual (mis. setelah kuota jual 20/20 habis, atau saat Smart Profit mati)." style="display: flex; align-items: center; gap: 4px; cursor: pointer;">
            <input type="checkbox" id="ks-opt-simpan" checked style="cursor: pointer;">
            <span>🎒 Auto Simpan</span>
          </label>
          <label title="Optimasi kuota harian: jual langsung ikan ≥1.00 koin, lepas ikan &lt;1.00 koin, ubah ikan kecil jadi umpan-ikan, jaga 1 joran, dan berhenti otomatis saat jual+tas penuh." style="display: flex; align-items: center; gap: 4px; cursor: pointer;">
            <input type="checkbox" id="ks-opt-smart-profit" checked style="cursor: pointer;">
            <span>🧠 Smart Profit</span>
          </label>
          <label title="Otomatis buang sampah laut (Sandal jepit) dan jual ikan jika tas penuh saat kuota jual masih ada." style="display: flex; align-items: center; gap: 4px; cursor: pointer;">
            <input type="checkbox" id="ks-opt-jual-penuh" checked style="cursor: pointer;">
            <span>🪙 Jual/Sampah</span>
          </label>
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

    document.getElementById("ks-opt-natural").onchange = (e) => mancingConfig.modeNatural = e.target.checked;
    document.getElementById("ks-opt-zeroloss").onchange = (e) => mancingConfig.zeroLossGuard = e.target.checked;
    document.getElementById("ks-opt-strategi-umpan").onchange = (e) => {
      mancingConfig.strategiUmpan = e.target.value;
      if (e.target.value === "ternak-ikan") {
        mancingConfig.preferredUmpan = "umpan-cacing";
        mancingConfig.selectiveRelease = true;
      } else if (e.target.value === "cumi") {
        mancingConfig.preferredUmpan = "umpan-cumi";
        mancingConfig.selectiveRelease = true;
      }
      stopStatusOverride = null;
      updateMancingUI();
    };
    document.getElementById("ks-opt-auto-upgrade").onchange = (e) => mancingConfig.autoUpgrade = e.target.checked;
    document.getElementById("ks-opt-jaring-lampu").onchange = (e) => {
      mancingConfig.autoJaring = e.target.checked;
      mancingConfig.autoLampu = e.target.checked;
    };
    document.getElementById("ks-opt-auto-navigasi").onchange = (e) => mancingConfig.autoNavigasi = e.target.checked;
    document.getElementById("ks-opt-celup").onchange = (e) => mancingConfig.autoCelup = e.target.checked;
    document.getElementById("ks-opt-sentak").onchange = (e) => mancingConfig.autoSentak = e.target.checked;
    document.getElementById("ks-opt-gulung").onchange = (e) => mancingConfig.autoGulung = e.target.checked;
    document.getElementById("ks-opt-simpan").onchange = (e) => mancingConfig.autoSimpan = e.target.checked;
    document.getElementById("ks-opt-smart-profit").onchange = (e) => mancingConfig.smartProfit = e.target.checked;
    document.getElementById("ks-opt-jual-penuh").onchange = (e) => {
      mancingConfig.autoJualTasPenuh = e.target.checked;
      mancingConfig.autoJualSampah = e.target.checked;
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
      sonarInfoEl.textContent = sonar.depth > 0 ? `${sonar.depth}m (${sonar.crowd})` : "-";
      targetInfoEl.textContent = `🎯 Target (${pancingProfile.joranNama}): ≥${target.minDepth}m (${target.targetFish})`;
    }

    renderMancingPlan();

    if (hud) {
      const featureInputs = hud.querySelectorAll('input[type="checkbox"], select');
      featureInputs.forEach((input) => {
        const noBoatSupport =
          input.id === "ks-opt-jaring-lampu" &&
          pancingProfile.loaded &&
          !pancingProfile.hasJaring &&
          !pancingProfile.hasLampu;
        const locked = !pancingProfile.loaded || noBoatSupport;
        input.disabled = locked;
        if (noBoatSupport) input.checked = false;
        if (input.parentElement) {
          input.parentElement.style.opacity = locked ? "0.55" : "1";
          input.parentElement.style.cursor = locked ? "not-allowed" : "pointer";
        }
      });
    }

    const strategiSelect = document.getElementById("ks-opt-strategi-umpan");
    if (strategiSelect) {
      strategiSelect.style.borderColor = !mancingConfig.strategiUmpan ? "#f59e0b" : "rgba(192, 132, 252, 0.45)";
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
        btn.textContent = "⚠️ Pilih Strategi Dulu";
        btn.style.background = "#475569";
        btn.style.boxShadow = "none";
        btn.style.cursor = "not-allowed";
        updateStatusMsg("⚠️ Pilih Strategi Mancing", "Pilih strategi umpan di dropdown sebelum mulai.", "#f59e0b");
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
    if (countEl) countEl.textContent = `${todayCatches} ekor`;
    if (lastEl && mancingStats.lastFish) lastEl.textContent = `Terakhir: ${mancingStats.lastFish}`;

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
      planEl.innerHTML = "📋 <b>Plan:</b> Pilih strategi di dropdown dulu.";
      return;
    }

    const equipped = getEquippedUmpanType();
    const stok = getUmpanStok();
    const sonar = getSonarData();
    const target = getTargetDepth();
    const umpanIkanStok = pancingProfile.umpanList?.find(u => u.id === "umpan-ikan")?.stok ?? 0;
    const sisaSlot = Math.max(1, (pancingProfile.jualMaks - pancingProfile.jualHariIni) + (pancingProfile.tasMaks - pancingProfile.tasIkan));
    const batchTarget = Math.min(5, sisaSlot);

    if (mancingConfig.strategiUmpan === "ternak-ikan") {
      const s1Done = equipped === "umpan-cacing" && stok > 0 || equipped === "umpan-ikan";
      const s2Done = equipped === "umpan-ikan" || umpanIkanStok >= batchTarget;
      const s3Done = equipped === "umpan-ikan" && sonar.depth >= target.minDepth && sonar.crowd !== "Sepi";
      const activeStep = !s1Done ? 1 : !s2Done ? 2 : !s3Done ? 3 : 4;
      const mark = (n, done) => (done ? "✅" : activeStep === n ? "▶️" : "⚪");

      planEl.innerHTML =
        `<div><b>📋 Plan Ternak Umpan:</b></div>` +
        `<div>${mark(1, s1Done)} 1. Pakai/Beli Cacing · ${mark(2, s2Done)} 2. Kumpul Ikan (${umpanIkanStok}/${batchTarget})</div>` +
        `<div>${mark(3, s3Done)} 3. Ke ≥30m Ramai · ${mark(4, false)} 4. Celup 2.3× &amp; Jual ≥1k</div>`;
      return;
    }

    const c1Done = stok > 0;
    const c2Done = c1Done && sonar.depth >= target.minDepth && sonar.crowd !== "Sepi";
    const activeCumi = !c1Done ? 1 : !c2Done ? 2 : 3;
    const markC = (n, done) => (done ? "✅" : activeCumi === n ? "▶️" : "⚪");

    planEl.innerHTML =
      `<div><b>📋 Plan Langsung Cumi:</b></div>` +
      `<div>${markC(1, c1Done)} 1. Siap Cumi · ${markC(2, c2Done)} 2. Ke ≥30m Ramai · ${markC(3, false)} 3. Celup &amp; Jual ≥1k</div>`;
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
    if (mancingConfig.singleRodProfit && mancingConfig.smartProfit && now - lastKailCheckTime > 2000) {
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

    if (!mancingConfig.autoMancing) return;

    const layar = document.querySelector('[data-testid="pancing"]');
    if (!layar) return;

    const fase = layar.getAttribute("data-fase") || "jalan";
    const hasilCard = document.querySelector('[data-testid="pancing-hasil"]');

    // 1. Fase Tangkapan Selesai (Hasil Ikan)
    if (hasilCard || fase === "dapat") {
      releaseGulung();
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

        const color = isRed ? "#ef4444" : isYellow ? "#eab308" : "#22c55e";
        updateStatusMsg(
          `🔄 Adu Tarik: Ikan ${progress.toFixed(0)}%`,
          `Tegangan: ${tension.toFixed(0)}% ${isRed ? "(BAHAYA: Melepas)" : "(Aman: Menarik)"}`,
          color
        );

        // Algoritma Smart Tension Control dengan Jitter Manusiawi:
        // Zero-Loss Guard ON: batas aman ketat (78%-82% max, 59%-63% min + auto-hold jika !isHolding)
        // Zero-Loss Guard OFF: batas longgar (84% max, 40% min, tanpa auto-hold paksa)
        const jitterMax = mancingConfig.modeNatural ? humanJitter(-2, 2) : 0;
        const jitterMin = mancingConfig.modeNatural ? humanJitter(-2, 2) : 0;
        const effectiveMax = mancingConfig.zeroLossGuard
          ? mancingConfig.baseMaxTension + jitterMax
          : 84;
        const effectiveMin = mancingConfig.zeroLossGuard
          ? mancingConfig.baseMinTension + jitterMin
          : 40;

        if ((mancingConfig.zeroLossGuard && isRed) || tension > effectiveMax) {
          releaseGulung();
        } else if (!isRed) {
          // Proteksi Anti-Kendur Mutlak (Anti-Lepas 100%) saat Zero-Loss aktif
          const btnGulung = document.querySelector('[data-testid="pancing-gulung"]');
          const isHolding = btnGulung && btnGulung.hasAttribute("data-tahan");
          if (tension < effectiveMin || (mancingConfig.zeroLossGuard && !isHolding)) {
            holdGulung();
          }
        }
      }
      return;
    }

    // 4. Fase Jalan / Diam (Siap Menurunkan Kail / Celup)
    if (fase === "jalan" || fase === "diam") {
      releaseGulung();

      // 4a. Jika ada jendela sheet (toko / kapal / tas) sedang terbuka di layar, JANGAN CELUP KAIL!
      if (isSheetOpen()) {
        stopAutopilot();
        const sheetToko = document.querySelector('[data-testid="pancing-toko"]');
        if (sheetToko && !autoUmpanPending && mancingConfig.autoUmpan && getUmpanStok() <= 0) {
          scheduleAutoBuyUmpan();
        }
        return;
      }

      // 4b. Cek jika proses loot hasil, auto umpan, atau upgrade sedang berlangsung
      if (lootPending || autoUmpanPending || autoUpgradePending) {
        stopAutopilot();
        return;
      }

      // 4b-2. Smart Profit Guard: Stop otomatis saat kuota Jual + Tas penuh agar tidak rugi umpan
      if (mancingConfig.smartProfit && pancingProfile.loaded) {
        const sisaJual = Math.max(0, pancingProfile.jualMaks - pancingProfile.jualHariIni);
        const sisaTas = Math.max(0, pancingProfile.tasMaks - pancingProfile.tasIkan);
        const totalSlot = pancingProfile.jualMaks + pancingProfile.tasMaks;
        if (sisaJual === 0 && sisaTas === 0) {
          toggleAutoMancing(false, {
            title: `🏆 Target ${totalSlot}/${totalSlot} Tercapai!`,
            detail: `${pancingProfile.jualMaks}/${pancingProfile.jualMaks} terjual & ${pancingProfile.tasMaks}/${pancingProfile.tasMaks} tas penuh. Berhenti otomatis agar hemat umpan.`,
            color: "#22c55e"
          });
          return;
        }
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
        stopAutopilot();
        if (mancingConfig.autoUmpan) {
          scheduleAutoBuyUmpan();
        } else {
          updateStatusMsg("⚠️ Umpan Habis!", "Aktifkan Auto-Umpan atau beli di toko", "#ef4444");
        }
        return;
      }

      // 4c-2. Sinkronisasi Umpan Mode Ternak Ikan:
      // - Jika sedang pakai cumi/udang pada mode ternak-ikan, wajib pindah ke umpan-ikan / cacing (beli cacing jika 0)
      // - Jika sedang pakai cacing di dangkal dan umpan-ikan sudah terkumpul >= min(5, sisaSlot), pindah ke umpan-ikan & berlayar ke >=30m
      if (
        mancingConfig.strategiUmpan === "ternak-ikan" &&
        mancingConfig.autoUmpanIkan &&
        mancingConfig.autoUmpan
      ) {
        const equippedNow = getEquippedUmpanType();
        const umpanIkanStok = pancingProfile.umpanList?.find(u => u.id === "umpan-ikan")?.stok ?? 0;
        const sisaSlot = pancingProfile.loaded
          ? Math.max(1, (pancingProfile.jualMaks - pancingProfile.jualHariIni) + (pancingProfile.tasMaks - pancingProfile.tasIkan))
          : 5;
        const batchTarget = Math.min(5, sisaSlot);
        if (equippedNow !== "umpan-ikan" && equippedNow !== "umpan-cacing") {
          stopAutopilot();
          updateStatusMsg("🐟 Mode Ternak Umpan...", "Pindah dari Cumi ke Umpan Ikan / Cacing Laut...", "#22c55e");
          scheduleAutoBuyUmpan();
          return;
        }
        if (equippedNow === "umpan-cacing" && umpanIkanStok >= batchTarget) {
          stopAutopilot();
          updateStatusMsg("🐟 Batch Umpan Siap!", `${umpanIkanStok} umpan-ikan terkumpul — ganti umpan & berlayar ke ≥30m...`, "#22c55e");
          scheduleAutoBuyUmpan();
          return;
        }
      }

      // 4d. Cek Auto-Upgrade peralatan (Joran / Pendingin) saat idle/santai
      if (mancingConfig.autoUpgrade && (performance.now() - lastUpgradeCheckTime > 60000)) {
        stopAutopilot();
        scheduleAutoUpgrade();
        return;
      }

      // 4e. Autopilot Navigasi Kapal ke Spot Laut Dalam Paling Ramai (kunci akurasi mode Celup)
      if (mancingConfig.autoNavigasi) {
        const sonar = getSonarData();
        const target = getTargetDepth();
        const spots = cachedTitik.length > 0 ? cachedTitik : liveShipData.titik;
        if (spots.length === 0 || (!isNavigating && sonar.crowd === "Sepi")) {
          fetchSpots(sonar.crowd === "Sepi");
        }

        const bestSpot = findBestCrowdedSpot(spots, liveShipData.x, liveShipData.z, target);

        if (bestSpot) {
          const dx = bestSpot.x - liveShipData.x;
          const dz = bestSpot.z - liveShipData.z;
          const dist = Math.hypot(dx, dz);

          // Mode Celup menurunkan kail lurus ke bawah: pastikan kedalaman target tercapai & perairan ramai
          const reachedSpotRadius = dist <= Math.max(16, (bestSpot.r || 30) * 0.65) && sonar.depth >= target.minDepth;
          const reachedCrowdSonar = sonar.crowd === "Ramai" && sonar.depth >= target.allowCrowdStopAt;
          const reachedLumayanFallback = !bestSpot.isRamai && sonar.crowd === "Lumayan" && sonar.depth >= target.minDepth;
          const reachedOptimalDepth = !bestSpot.isRamai && sonar.depth >= target.optimalDepth && sonar.crowd !== "Sepi";

          if (!reachedSpotRadius && !reachedCrowdSonar && !reachedLumayanFallback && !reachedOptimalDepth) {
            startAutopilotToSpot(bestSpot, liveShipData.x, liveShipData.z, liveShipData.h);
            // Safety timeout guard (maks 45 detik berlayar)
            if (performance.now() - navStartTime > 45000) {
              stopAutopilot(`Spot dicapai di kedalaman ${sonar.depth}m (${sonar.crowd})`);
            }
            return;
          }

          if (isNavigating) {
            stopAutopilot(`Spot Ramai Dicapai: ${sonar.depth}m (${sonar.crowd})!`);
            return;
          }
        } else {
          // Fallback navigasi lurus ke laut dalam jika koordinat titik belum terambil
          if (sonar.depth < target.minDepth) {
            steerShip(1, 0);
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
      releaseGulung();
      stopAutopilot();
      updateStatusMsg("⏳ Menunggu Sambaran...", "Pelampung di air, siap menyentak!", "#06b6d4");
      return;
    }
  }, 40);
})();
