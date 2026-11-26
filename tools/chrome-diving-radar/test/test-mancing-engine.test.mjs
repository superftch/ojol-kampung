import test from "node:test";
import assert from "node:assert/strict";

function humanJitter(min, max) {
  return Math.floor(min + Math.random() * (max - min + 1));
}

// Reel tension controller logic with dynamic human jitter & zero-loss guard
class MockMancingReelController {
  constructor(modeNatural = true) {
    this.modeNatural = modeNatural;
    this.isPulling = false;
    this.strikeTriggered = false;
    this.baseMaxTension = 0.80;
    this.baseMinTension = 0.61;
  }

  evaluateTension(tension, isDanger) {
    const jitterMax = this.modeNatural ? (humanJitter(-2, 2) / 100) : 0;
    const jitterMin = this.modeNatural ? (humanJitter(-2, 2) / 100) : 0;
    const effectiveMax = this.baseMaxTension + jitterMax;
    const effectiveMin = this.baseMinTension + jitterMin;

    if (tension > effectiveMax || isDanger) {
      if (this.isPulling) {
        this.isPulling = false;
        return "RELEASE";
      }
    } else if (!isDanger && tension < effectiveMin) {
      if (!this.isPulling) {
        this.isPulling = true;
        return "PULL";
      }
    }
    return "MAINTAIN";
  }

  evaluateStrike(fase, hasStrikeButton) {
    if (fase === "sambar" || hasStrikeButton) {
      this.strikeTriggered = true;
      return true;
    }
    return false;
  }

  evaluateLootDecision(fishName, fishClass, isBagFull) {
    const isTrash = fishName.toLowerCase().includes("sandal") || fishClass.includes("sampah");
    if (isTrash) return "JUAL_SAMPAH";
    if (isBagFull) return "JUAL_TAS_PENUH";
    return "SIMPAN";
  }
}

test("Auto-Mancing Engine & Smart Tension Controller", async (t) => {
  await t.test("Reel tension releases on high tension or danger attribute (Zero-Loss Line Snap)", () => {
    const ctrl = new MockMancingReelController(true);
    ctrl.isPulling = true;

    // Normal safe tension (0.70 is in the sweet spot)
    assert.equal(ctrl.evaluateTension(0.70, false), "MAINTAIN");
    assert.equal(ctrl.isPulling, true);

    // High tension threshold exceeded (> 0.83) -> must release!
    assert.equal(ctrl.evaluateTension(0.84, false), "RELEASE");
    assert.equal(ctrl.isPulling, false);

    // If danger flag (data-merah) is true even at 0.72 -> must release immediately!
    ctrl.isPulling = true;
    assert.equal(ctrl.evaluateTension(0.72, true), "RELEASE");
    assert.equal(ctrl.isPulling, false);
  });

  await t.test("Reel tension pulls when slack (< 0.58) to prevent fish escape", () => {
    const ctrl = new MockMancingReelController(true);
    ctrl.isPulling = false;

    // Moderate slack
    assert.equal(ctrl.evaluateTension(0.68, false), "MAINTAIN");
    assert.equal(ctrl.isPulling, false);

    // Slack threshold exceeded (< 0.58) -> must pull!
    assert.equal(ctrl.evaluateTension(0.55, false), "PULL");
    assert.equal(ctrl.isPulling, true);
  });

  await t.test("Strike initiates upon sambar phase with human jitter range", () => {
    const ctrl = new MockMancingReelController(true);
    assert.equal(ctrl.evaluateStrike("tunggu", false), false);
    assert.equal(ctrl.evaluateStrike("sambar", false), true);
    assert.equal(ctrl.strikeTriggered, true);

    // Test natural jitter distribution (220ms - 380ms)
    for (let i = 0; i < 50; i++) {
      const delay = humanJitter(220, 380);
      assert.ok(delay >= 220 && delay <= 380, `Delay ${delay} out of human range`);
    }
  });

  await t.test("Zero-loss profit decision handles full bag and trash catches", () => {
    const ctrl = new MockMancingReelController(true);

    // Valuable fish with room in bag -> Simpan
    assert.equal(ctrl.evaluateLootDecision("Ikan Kakap Merah", "sedang", false), "SIMPAN");

    // Valuable fish when bag is FULL -> Auto Jual (Zero-Loss profit conversion!)
    assert.equal(ctrl.evaluateLootDecision("Ikan Tenggiri", "besar", true), "JUAL_TAS_PENUH");

    // Trash catch (Sandal jepit) -> Auto Jual sampah
    assert.equal(ctrl.evaluateLootDecision("Sandal Jepit", "sampah", false), "JUAL_SAMPAH");
  });

  await t.test("Auto-Umpan decision selects high-ROI bait and fallback", () => {
    function pickBestUmpan(cumiEnabled, udangEnabled) {
      if (cumiEnabled) return "umpan-cumi";
      if (udangEnabled) return "umpan-udang";
      return null;
    }

    assert.equal(pickBestUmpan(true, true), "umpan-cumi");
    assert.equal(pickBestUmpan(false, true), "umpan-udang");
    assert.equal(pickBestUmpan(false, false), null);
  });

  await t.test("Auto-Upgrade prioritizes highest ROI rod available", () => {
    function pickBestRodUpgrade(available) {
      if (available.includes("joran-samudra")) return "joran-samudra";
      if (available.includes("joran-tonda")) return "joran-tonda";
      if (available.includes("joran-karang")) return "joran-karang";
      return null;
    }

    assert.equal(pickBestRodUpgrade(["joran-karang", "joran-tonda"]), "joran-tonda");
    assert.equal(pickBestRodUpgrade(["joran-karang", "joran-tonda", "joran-samudra"]), "joran-samudra");
    assert.equal(pickBestRodUpgrade(["joran-karang"]), "joran-karang");
    assert.equal(pickBestRodUpgrade([]), null);
  });

  await t.test("Prevents cast when bait is 0, shop is open, or pending purchase", () => {
    function canCast({ isSheetOpen, stokUmpan, isUmpanHabisText, autoUmpanPending }) {
      if (isSheetOpen) return false;
      if (autoUmpanPending) return false;
      if (stokUmpan === 0 || isUmpanHabisText) return false;
      return true;
    }

    // Normal safe condition: shop closed, bait > 0
    assert.equal(canCast({ isSheetOpen: false, stokUmpan: 10, isUmpanHabisText: false, autoUmpanPending: false }), true);

    // Bait 0 even if button is enabled: MUST NOT CAST!
    assert.equal(canCast({ isSheetOpen: false, stokUmpan: 0, isUmpanHabisText: false, autoUmpanPending: false }), false);

    // Shop sheet open: MUST NOT CAST!
    assert.equal(canCast({ isSheetOpen: true, stokUmpan: 0, isUmpanHabisText: false, autoUmpanPending: false }), false);

    // Toast "habis. Beli dulu" active: MUST NOT CAST!
    assert.equal(canCast({ isSheetOpen: false, stokUmpan: 5, isUmpanHabisText: true, autoUmpanPending: false }), false);

    // Purchase in progress: MUST NOT CAST!
    assert.equal(canCast({ isSheetOpen: false, stokUmpan: 10, isUmpanHabisText: false, autoUmpanPending: true }), false);
  });

  await t.test("Action delay retains human jitter without rigid 1-second delay", () => {
    function getActionDelay(baseMs = 0, modeNatural = true) {
      if (modeNatural) {
        return baseMs + humanJitter(140, 280);
      }
      return baseMs || 30;
    }

    // When modeNatural is true: must be snappy (140ms - 280ms) with natural human variance
    const samples = [];
    for (let i = 0; i < 50; i++) {
      const delay = getActionDelay(0, true);
      assert.ok(delay >= 140 && delay <= 280, `Delay ${delay} should be in [140, 280]`);
      samples.push(delay);
    }
    const uniqueDelays = new Set(samples);
    assert.ok(uniqueDelays.size > 10, "Human jitter must provide diverse natural delay intervals");

    // When modeNatural is false: returns fast base delay
    assert.equal(getActionDelay(0, false), 30);
  });

  await t.test("Smart tension controller prevents slack line escape (Anti-Kendur Zero-Loss)", () => {
    function evaluateTensionControl({ isRed, tension, effectiveMax, effectiveMin, isHolding }) {
      if (isRed || tension > effectiveMax) {
        return "RELEASE";
      }
      // Proteksi anti-kendur mutlak: jika tidak menahan saat aman, atau tegangan di bawah batas bawah
      if (!isRed && (tension < effectiveMin || !isHolding)) {
        return "HOLD";
      }
      return "MAINTAIN";
    }

    // High tension / danger -> release
    assert.equal(evaluateTensionControl({ isRed: true, tension: 70, effectiveMax: 80, effectiveMin: 61, isHolding: true }), "RELEASE");
    assert.equal(evaluateTensionControl({ isRed: false, tension: 85, effectiveMax: 80, effectiveMin: 61, isHolding: true }), "RELEASE");

    // Slack danger: tension dropped to 20% while holding was dropped -> MUST HOLD IMMEDIATELY
    assert.equal(evaluateTensionControl({ isRed: false, tension: 20, effectiveMax: 80, effectiveMin: 61, isHolding: false }), "HOLD");

    // Tension below minimum threshold (e.g. 50%) -> MUST HOLD
    assert.equal(evaluateTensionControl({ isRed: false, tension: 50, effectiveMax: 80, effectiveMin: 61, isHolding: true }), "HOLD");

    // Sweet spot between 61% and 80% with hold active -> MAINTAIN
    assert.equal(evaluateTensionControl({ isRed: false, tension: 72, effectiveMax: 80, effectiveMin: 61, isHolding: true }), "MAINTAIN");
  });

  await t.test("Hotspot finder selects most crowded spot and computes steering", () => {
    function calcDepth(x, z) {
      let n = Math.min(1, Math.max(0, (-z - 10) / 630));
      return Math.max(1.5, 2 + n * n * 18 + 20 * n + Math.sin(0.021 * x + 1.3) * Math.cos(0.017 * z) * 3 * n);
    }

    function findBestCrowdedSpot(spots, shipX, shipZ) {
      const scored = spots.map(s => {
        const d = calcDepth(s.x, s.z);
        const dist = Math.hypot(s.x - shipX, s.z - shipZ);
        const depthBonus = d >= 28 ? 160 : d >= 24 ? 100 : d >= 18 ? 40 : 0;
        const score = (s.kaya * 300) + depthBonus - (dist * 0.05);
        return { ...s, depth: d, dist, score };
      });
      scored.sort((a, b) => b.score - a.score);
      return scored[0];
    }

    const testSpots = [
      { x: 0, z: -100, r: 30, kaya: 0.3 },   // Shallow (depth ~8m)
      { x: -50, z: -350, r: 40, kaya: 0.4 }, // Mid (depth ~22m)
      { x: 40, z: -520, r: 50, kaya: 0.6 }   // Deep & most crowded (depth ~34m, kaya 0.6)
    ];

    const best = findBestCrowdedSpot(testSpots, 0, -46);
    assert.equal(best.z, -520);
    assert.ok(best.depth >= 25, "Best spot must be in deep sea");
    assert.equal(best.kaya, 0.6, "Best spot must have highest kaya");

    // Steering calculation towards target (40, -520) from dock (0, -46) facing North (PI)
    const dx = best.x - 0;
    const dz = best.z - (-46);
    const targetHeading = Math.atan2(dx, dz);
    let diff = (targetHeading - Math.PI + Math.PI) % (2 * Math.PI);
    if (diff < 0) diff += 2 * Math.PI;
    diff -= Math.PI;

    // Heading diff should be close to 0 (heading north towards z=-520 with small eastward x=40)
    assert.ok(Math.abs(diff) < 0.3, "Steering diff should guide boat north-east");
  });

  await t.test("Autopilot navigates boat to worth-it depth based on equipment & bait", () => {
    function getTargetDepth({ preferredUmpan, upgrades }) {
      const isCumi = preferredUmpan === "umpan-cumi";
      const isUdang = preferredUmpan === "umpan-udang";
      const hasSamudra = upgrades.some(j => j.toLowerCase().includes("samudra"));
      const hasTonda = upgrades.some(j => j.toLowerCase().includes("tonda"));
      const hasKarang = upgrades.some(j => j.toLowerCase().includes("karang"));

      if (isCumi || hasSamudra) {
        return { minDepth: 30, optimalDepth: 32, allowCrowdStopAt: 30, targetFish: "Kuwe GT (≥30m) & Barakuda (≥24m)" };
      }
      if (hasTonda) {
        return { minDepth: 20, optimalDepth: 24, allowCrowdStopAt: 19, targetFish: "Tenggiri & Cakalang" };
      }
      if (isUdang || hasKarang) {
        return { minDepth: 15, optimalDepth: 18, allowCrowdStopAt: 14, targetFish: "Tongkol & Kerapu" };
      }
      return { minDepth: 8, optimalDepth: 12, allowCrowdStopAt: 7, targetFish: "Kakap & Bawal" };
    }

    function evaluateNavigation(sonarDepth, sonarCrowd, target) {
      if (sonarDepth < target.minDepth) {
        if (sonarDepth >= target.allowCrowdStopAt && sonarCrowd === "Ramai") {
          return "STOP_AT_CROWD";
        }
        return "NAVIGATE_DEEPER";
      }
      if (sonarDepth >= target.optimalDepth) {
        return "STOP_AT_OPTIMAL";
      }
      if (sonarDepth >= target.allowCrowdStopAt && sonarCrowd === "Ramai") {
        return "STOP_AT_CROWD";
      }
      return "READY_TO_CAST";
    }

    // 1. High-ROI Bait (Umpan Cumi) -> Target 30-32m (Kuwe GT & Barakuda)
    const targetCumi = getTargetDepth({ preferredUmpan: "umpan-cumi", upgrades: [] });
    assert.equal(targetCumi.minDepth, 30);
    assert.equal(targetCumi.optimalDepth, 32);

    // Shallow dock (3m) -> MUST NAVIGATE DEEPER
    assert.equal(evaluateNavigation(3, "Sepi", targetCumi), "NAVIGATE_DEEPER");

    // 25m with Lumayan (Kuwe GT still locked) -> MUST NAVIGATE DEEPER to most worth-it spot!
    assert.equal(evaluateNavigation(25, "Lumayan", targetCumi), "NAVIGATE_DEEPER");

    // 28m: Kuwe GT belum terbuka (syarat >= 30m) -> Tetap lanjut berlayar ke kedalaman 30m!
    assert.equal(evaluateNavigation(28, "Ramai", targetCumi), "NAVIGATE_DEEPER");

    // 30m dan Ramai -> Kuwe GT resmi terbuka, bisa berhenti dan lempar kail!
    assert.equal(evaluateNavigation(30, "Ramai", targetCumi), "STOP_AT_CROWD");

    // Deep sea (32m) -> Reached optimal depth for Kuwe GT!
    assert.equal(evaluateNavigation(32, "Sepi", targetCumi), "STOP_AT_OPTIMAL");

    // 2. Joran Tonda -> Target 20-24m
    const targetTonda = getTargetDepth({ preferredUmpan: "cacing", upgrades: ["Joran Tonda"] });
    assert.equal(targetTonda.minDepth, 20);
    assert.equal(targetTonda.optimalDepth, 24);
    assert.equal(evaluateNavigation(10, "Sepi", targetTonda), "NAVIGATE_DEEPER");
    assert.equal(evaluateNavigation(21, "Lumayan", targetTonda), "READY_TO_CAST");

    // 3. Joran Karang / Udang -> Target 15-18m
    const targetUdang = getTargetDepth({ preferredUmpan: "umpan-udang", upgrades: [] });
    assert.equal(targetUdang.minDepth, 15);
    assert.equal(evaluateNavigation(4, "Sepi", targetUdang), "NAVIGATE_DEEPER");
    assert.equal(evaluateNavigation(16, "Lumayan", targetUdang), "READY_TO_CAST");
  });

  await t.test("Anti-Spin Guard & Pulsed Micro-Steering prevents circular left-turn loop", () => {
    // Model kemudi dengan Anti-Spin Guard
    function computeSteering({ targetHeading, shipH, stuckCount }) {
      // Jika shipH macet / tidak ada update Three.js (> 10 tick), kemudi dipaksa netral 0 (maju lurus ke laut)
      if (stuckCount > 10) {
        return { gas: 1, belok: 0, reason: "ANTI_SPIN_GUARD" };
      }

      let diff = (targetHeading - shipH + Math.PI) % (2 * Math.PI);
      if (diff < 0) diff += 2 * Math.PI;
      diff -= Math.PI;

      // Deadband 0.15 rad (~8.5 derajat)
      if (Math.abs(diff) <= 0.15) {
        return { gas: 1, belok: 0, reason: "ALIGNED" };
      }
      return { gas: 1, belok: diff > 0 ? 1 : -1, reason: diff > 0 ? "TURN_LEFT_PULSE" : "TURN_RIGHT_PULSE" };
    }

    // Kasus 1: Heading normal, target di kiri -> Belok kiri pulse
    const steerNormal = computeSteering({ targetHeading: 2.8, shipH: 2.2, stuckCount: 0 });
    assert.equal(steerNormal.belok, 1);
    assert.equal(steerNormal.reason, "TURN_LEFT_PULSE");

    // Kasus 2: Target sudah sejajar dalam toleransi deadband (0.10 rad) -> Kemudi netral lurus
    const steerAligned = computeSteering({ targetHeading: 3.14, shipH: 3.20, stuckCount: 0 });
    assert.equal(steerAligned.belok, 0);
    assert.equal(steerAligned.reason, "ALIGNED");

    // Kasus 3: Bug yang dialami user sebelumnya (heading macet di 3.14 selama navigasi)
    // Tanpa guard, belok kiri dipencet terus -> Kapal muter-muter.
    // Dengan Anti-Spin Guard, saat stuckCount > 10, kemudi otomatis netral 0!
    const steerStuck = computeSteering({ targetHeading: 1.5, shipH: 3.14, stuckCount: 15 });
    assert.equal(steerStuck.belok, 0);
    assert.equal(steerStuck.gas, 1);
    assert.equal(steerStuck.reason, "ANTI_SPIN_GUARD");
  });

  await t.test("Auto-Umpan selectors match KampungSebelah real shop testids (cumi, udang, cacing)", () => {
    // Simulasi DOM Toko Umpan KampungSebelah
    const mockTokoDOM = {
      elements: {
        "pancing-beli-cumi": { disabled: false, id: "cumi", name: "Potongan cumi" },
        "pancing-beli-udang": { disabled: false, id: "udang", name: "Udang hidup" },
        "pancing-beli-cacing": { disabled: false, id: "cacing", name: "Cacing laut" },
        "pancing-pilih-cumi": { id: "cumi" },
        "pancing-pilih-udang": { id: "udang" },
        "pancing-pilih-cacing": { id: "cacing" }
      },
      querySelector(selector) {
        for (const [key, val] of Object.entries(this.elements)) {
          if (selector.includes(`"${key}"`) || selector.includes(`pancing-beli-${val.id}`) || selector.includes(`pancing-pilih-${val.id}`)) {
            return val;
          }
        }
        return null;
      }
    };

    function resolveBaitTarget(sheet, preferred) {
      const btnBeliCumi = sheet.querySelector('[data-testid="pancing-beli-cumi"], [data-testid="pancing-beli-umpan-cumi"]');
      const btnBeliUdang = sheet.querySelector('[data-testid="pancing-beli-udang"], [data-testid="pancing-beli-umpan-udang"]');

      let targetBeli = null;
      let targetPilihId = "cumi";

      if (preferred === "umpan-cumi" && btnBeliCumi && !btnBeliCumi.disabled) {
        targetBeli = btnBeliCumi;
        targetPilihId = "cumi";
      } else if (btnBeliUdang && !btnBeliUdang.disabled) {
        targetBeli = btnBeliUdang;
        targetPilihId = "udang";
      }
      const btnPilih = sheet.querySelector(`[data-testid="pancing-pilih-${targetPilihId}"]`);
      return { targetBeli, targetPilihId, btnPilih };
    }

    const resCumi = resolveBaitTarget(mockTokoDOM, "umpan-cumi");
    assert.ok(resCumi.targetBeli, "Tombol beli cumi harus ditemukan");
    assert.equal(resCumi.targetPilihId, "cumi");
    assert.ok(resCumi.btnPilih, "Tombol pilih cumi harus ditemukan");

    const resUdang = resolveBaitTarget(mockTokoDOM, "umpan-udang");
    assert.ok(resUdang.targetBeli, "Tombol beli udang harus ditemukan");
    assert.equal(resUdang.targetPilihId, "udang");
    assert.ok(resUdang.btnPilih, "Tombol pilih udang harus ditemukan");
  });

  await t.test("Fish price & profit calculation for Kakap 870g with Umpan Cumi", () => {
    function calcFishPrice(fishName, fishClass, fishWeight) {
      let gram = 0;
      const gMatch = fishWeight.match(/([\d,\.]+)\s*g/i);
      if (gMatch) gram = parseFloat(gMatch[1].replace(",", "."));

      const nameLower = fishName.toLowerCase();
      const classLower = fishClass.toLowerCase();

      let baseMilli = 400;
      let minGram = 100, maxGram = 300;

      if (classLower.includes("sedang") || nameLower.includes("kakap")) {
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

    // Kakap 870g
    const sellPrice = calcFishPrice("Kakap merah", "sedang", "870 g");
    assert.equal(sellPrice, 0.836 || Math.round(800 * (1 + ((870-300)/(2200-300))*0.15))/1000);
    assert.ok(sellPrice >= 0.82 && sellPrice <= 0.85, `Harga jual ${sellPrice} sesuai rentang kelas sedang`);

    // Umpan cumi (0.50 koin)
    const baitCostCumi = 0.50;
    const profitCumi = sellPrice - baitCostCumi;
    assert.ok(profitCumi >= 0.32 && profitCumi <= 0.35, `Profit cumi ${profitCumi} harus positif`);

    // Umpan udang (0.30 koin)
    const baitCostUdang = 0.30;
    const profitUdang = sellPrice - baitCostUdang;
    assert.ok(profitUdang >= 0.52 && profitUdang <= 0.55, `Profit udang ${profitUdang} harus lebih besar dari cumi`);
  });

  await t.test("Daily fishing profile sync & quota automation decisions", () => {
    const mockApiResponse = {
      hariIni: { lempar: 18, dapat: 14 },
      jual: { hariIni: 16, maks: 20 },
      tas: { ikan: 7, maks: 20 },
      saldoMilli: 42500,
      titik: [{ x: 50, z: -180, r: 40, kaya: 0.8 }]
    };

    function parseProfile(data) {
      return {
        lempar: data.hariIni?.lempar ?? 0,
        dapat: data.hariIni?.dapat ?? 0,
        jualHariIni: data.jual?.hariIni ?? 0,
        jualMaks: data.jual?.maks ?? 20,
        sisaJual: Math.max(0, (data.jual?.maks ?? 20) - (data.jual?.hariIni ?? 0)),
        tasIkan: data.tas?.ikan ?? 0,
        tasMaks: data.tas?.maks ?? 20,
        sisaTas: Math.max(0, (data.tas?.maks ?? 20) - (data.tas?.ikan ?? 0)),
        saldoKoin: (data.saldoMilli ?? 0) / 1000
      };
    }

    const p = parseProfile(mockApiResponse);
    assert.equal(p.lempar, 18);
    assert.equal(p.dapat, 14);
    assert.equal(p.jualHariIni, 16);
    assert.equal(p.sisaJual, 4);
    assert.equal(p.tasIkan, 7);
    assert.equal(p.sisaTas, 13);
    assert.equal(p.saldoKoin, 42.5);

    function decideLootAction({ sisaJual, sisaTas, autoSimpan, autoJual, autoJualTasPenuh }) {
      if (autoJual && sisaJual > 0) return "JUAL_BUMDES";
      if (autoSimpan && sisaTas > 0) return "SIMPAN_TAS";
      if (autoJualTasPenuh && sisaJual > 0) return "JUAL_BUMDES_KARENA_TAS_PENUH";
      if (sisaJual === 0 && sisaTas === 0) return "MAKAN_IKAN";
      return "SIMPAN_TAS";
    }

    assert.equal(decideLootAction({ sisaJual: 4, sisaTas: 13, autoSimpan: true, autoJual: false, autoJualTasPenuh: true }), "SIMPAN_TAS");
    assert.equal(decideLootAction({ sisaJual: 4, sisaTas: 0, autoSimpan: true, autoJual: false, autoJualTasPenuh: true }), "JUAL_BUMDES_KARENA_TAS_PENUH");
    assert.equal(decideLootAction({ sisaJual: 0, sisaTas: 0, autoSimpan: true, autoJual: false, autoJualTasPenuh: true }), "MAKAN_IKAN");
  });

  await t.test("Celup mode button resolution, readiness check, and lootPending guard", () => {
    function findCelupButton(buttons) {
      const byTestId = buttons.find((b) => b.testId === "pancing-celup");
      if (byTestId) return byTestId;
      return buttons.find((b) => !b.inHud && /\bcelup\b/i.test(b.text || "")) || null;
    }

    function isCelupButtonReady(btn) {
      return !!(btn && !btn.disabled && !btn.ariaBusy);
    }

    // Never pick Lempar even if Celup has no testid yet
    const fallbackButtons = [
      { testId: "pancing-lempar", text: "Lempar", disabled: false, ariaBusy: null, inHud: false },
      { testId: null, text: "Celup", disabled: false, ariaBusy: null, inHud: false },
      { testId: null, text: "Auto Celup", disabled: false, ariaBusy: null, inHud: true }
    ];
    const picked = findCelupButton(fallbackButtons);
    assert.equal(picked.text, "Celup");
    assert.equal(picked.inHud, false);
    assert.equal(isCelupButtonReady(picked), true);

    // Reject busy or disabled Celup button
    assert.equal(isCelupButtonReady({ disabled: true, ariaBusy: null }), false);
    assert.equal(isCelupButtonReady({ disabled: false, ariaBusy: "celup" }), false);
    assert.equal(isCelupButtonReady({ disabled: false, ariaBusy: "true" }), false);

    // Must block Celup while lootPending is active
    function canProceedToCelup({ isSheetOpen, lootPending, autoUmpanPending, autoUpgradePending }) {
      return !(isSheetOpen || lootPending || autoUmpanPending || autoUpgradePending);
    }
    assert.equal(canProceedToCelup({ isSheetOpen: false, lootPending: true, autoUmpanPending: false, autoUpgradePending: false }), false);
    assert.equal(canProceedToCelup({ isSheetOpen: false, lootPending: false, autoUmpanPending: false, autoUpgradePending: false }), true);
  });

  await t.test("Celup deep-sea spot selection prioritizes >=30m and re-navigates when crowd turns Sepi", () => {
    function calcDepth(x, z) {
      let n = Math.min(1, Math.max(0, (-z - 10) / 630));
      return Math.max(1.5, 2 + n * n * 18 + 20 * n + Math.sin(0.021 * x + 1.3) * Math.cos(0.017 * z) * 3 * n);
    }

    function scoreSpot(s, shipX, shipZ) {
      const d = calcDepth(s.x, s.z);
      const dist = Math.hypot(s.x - shipX, s.z - shipZ);
      const depthBonus = d >= 30 ? 220 : d >= 28 ? 150 : d >= 24 ? 100 : d >= 18 ? 40 : 0;
      return { ...s, depth: d, dist, score: (s.kaya * 300) + depthBonus - (dist * 0.05) };
    }

    const spots = [
      scoreSpot({ x: 0, z: -495, r: 30, kaya: 0.5 }, 0, -46), // ~28m
      scoreSpot({ x: 0, z: -560, r: 30, kaya: 0.5 }, 0, -46)  // >= 30m
    ];
    spots.sort((a, b) => b.score - a.score);
    assert.ok(spots[0].depth >= 30, `Deep >=30m spot must beat ~28m spot (got ${spots[0].depth.toFixed(2)}m)`);

    // Re-navigate when sonar turns Sepi even if depth >= optimalDepth (32m)
    const minDepth = 30;
    const optimalDepth = 32;
    const allowCrowdStopAt = 30;
    function shouldStopAtSpot({ dist, radius, sonarDepth, sonarCrowd }) {
      const reachedSpotRadius = dist <= Math.max(16, (radius || 30) * 0.65) && sonarDepth >= minDepth;
      const reachedCrowdSonar = (sonarCrowd === "Ramai" || (sonarCrowd === "Lumayan" && sonarDepth >= 22)) && sonarDepth >= allowCrowdStopAt;
      const reachedOptimalDepth = sonarDepth >= optimalDepth && sonarCrowd !== "Sepi";
      return reachedSpotRadius || reachedCrowdSonar || reachedOptimalDepth;
    }

    assert.equal(shouldStopAtSpot({ dist: 47, radius: 30, sonarDepth: 33, sonarCrowd: "Sepi" }), false);
    assert.equal(shouldStopAtSpot({ dist: 10, radius: 30, sonarDepth: 30, sonarCrowd: "Ramai" }), true);
    assert.equal(shouldStopAtSpot({ dist: 10, radius: 30, sonarDepth: 12, sonarCrowd: "Ramai" }), false);
  });

  await t.test("Trash catch ('SAMPAH LAUT' / 'Buang ke tempat sampah') and 40-slot Smart Profit strategy (20 sell + 20 bag)", () => {
    function detectTrash({ fishName, fishClass, cardText, buttons }) {
      const hasBuang = buttons.some((b) => /\bbuang\b/i.test(b.text || "") || b.testId === "pancing-buang");
      return (
        fishName.toLowerCase().includes("sandal") ||
        fishClass.toLowerCase().includes("sampah") ||
        cardText.toLowerCase().includes("sampah laut") ||
        hasBuang
      );
    }

    assert.equal(
      detectTrash({
        fishName: "Sandal jepit",
        fishClass: "",
        cardText: "SAMPAH LAUT Sandal jepit 172 g Buang ke tempat sampah",
        buttons: [{ text: "Pamer di obrolan" }, { text: "Buang ke tempat sampah" }]
      }),
      true
    );

    function decideSmartLoot({ isTrash, sellPrice, sisaJual, sisaTas, smartProfit = true, autoSimpan = true, autoJualTasPenuh = true }) {
      if (isTrash) return "BUANG";
      const isHighValue = sellPrice >= 1.40;
      if (smartProfit) {
        if (isHighValue && sisaJual > 0) return "JUAL";
        if (autoSimpan && sisaTas > 0) return "SIMPAN";
        if (autoJualTasPenuh && sisaJual > 0) return "JUAL_TAS_PENUH";
        return "MAKAN";
      }
      return autoSimpan && sisaTas > 0 ? "SIMPAN" : "JUAL";
    }

    // 1. Trash -> BUANG
    assert.equal(decideSmartLoot({ isTrash: true, sellPrice: 0, sisaJual: 20, sisaTas: 20 }), "BUANG");

    // 2. High-value fish (>= 1.40) while sell quota available -> JUAL immediately
    assert.equal(decideSmartLoot({ isTrash: false, sellPrice: 2.50, sisaJual: 20, sisaTas: 20 }), "JUAL");

    // 3. Cheap/medium fish (< 1.40) while bag has room -> SIMPAN to preserve 20 sell quota for big fish
    assert.equal(decideSmartLoot({ isTrash: false, sellPrice: 0.80, sisaJual: 20, sisaTas: 20 }), "SIMPAN");

    // 4. Cheap/medium fish when bag is full (sisaTas=0) and sell quota remains -> JUAL_TAS_PENUH (Zero-Loss)
    assert.equal(decideSmartLoot({ isTrash: false, sellPrice: 0.80, sisaJual: 5, sisaTas: 0 }), "JUAL_TAS_PENUH");

    // 5. High-value fish after 20/20 daily sells used (sisaJual=0), bag still has room -> SIMPAN for tomorrow
    assert.equal(decideSmartLoot({ isTrash: false, sellPrice: 3.40, sisaJual: 0, sisaTas: 12 }), "SIMPAN");

    // 6. Stop guard before next Celup when all 40 slots (20 sell + 20 bag) are full
    function shouldStopForFullQuota(sisaJual, sisaTas, smartProfit) {
      return smartProfit && sisaJual === 0 && sisaTas === 0;
    }
    assert.equal(shouldStopForFullQuota(0, 0, true), true);
    assert.equal(shouldStopForFullQuota(0, 1, true), false);
    assert.equal(shouldStopForFullQuota(1, 0, true), false);
  });

  await t.test("Max Cuan selective release, night lamp window, and bait-saving guards", () => {
    function decideSmartLootAction({
      isTrash,
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

      const isHighValue = sellPrice >= 1.00;
      const isLowValue = sellPrice < 1.00;
      const sisaTotal = sisaJual + sisaTas;
      const hasSafeReserve = saldoKoin >= 5.0 || stokUmpan >= 5;

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
      }
      return availableButtons.makan ? "MAKAN" : "NONE";
    }

    const baseConfig = {
      smartProfit: true,
      selectiveRelease: true,
      autoJualSampah: true,
      autoJual: false,
      autoSimpan: true,
      autoJualTasPenuh: true
    };
    const allBtns = { buang: true, jual: true, simpan: true, makan: true, lepas: true };

    // 1. Ikan kecil (0.40 koin) with safe coins -> LEPAS to save slot for >=1.40 fish
    assert.equal(
      decideSmartLootAction({
        isTrash: false, sellPrice: 0.40, baitCost: 0.50, sisaJual: 20, sisaTas: 20,
        saldoKoin: 25, stokUmpan: 10, config: baseConfig, availableButtons: allBtns
      }),
      "LEPAS"
    );

    // 2. Ikan sedang (0.85 koin) with low coins & low bait -> SIMPAN (safe fallback, no risk of running dry)
    assert.equal(
      decideSmartLootAction({
        isTrash: false, sellPrice: 0.85, baitCost: 0.50, sisaJual: 20, sisaTas: 20,
        saldoKoin: 1.5, stokUmpan: 2, config: baseConfig, availableButtons: allBtns
      }),
      "SIMPAN"
    );

    // 3. Ikan besar/raksasa (1.23 koin Lemadang or 2.65 koin Kuwe) with sell quota -> JUAL immediately (never wait for bag full!)
    assert.equal(
      decideSmartLootAction({
        isTrash: false, sellPrice: 1.23, baitCost: 0.50, sisaJual: 20, sisaTas: 20,
        saldoKoin: 25, stokUmpan: 10, config: baseConfig, availableButtons: allBtns
      }),
      "JUAL"
    );
    assert.equal(
      decideSmartLootAction({
        isTrash: false, sellPrice: 2.65, baitCost: 0.50, sisaJual: 12, sisaTas: 20,
        saldoKoin: 25, stokUmpan: 10, config: baseConfig, availableButtons: allBtns
      }),
      "JUAL"
    );

    // 4. Last 2 slots of the day -> keep/sell instead of releasing
    assert.equal(
      decideSmartLootAction({
        isTrash: false, sellPrice: 0.85, baitCost: 0.50, sisaJual: 1, sisaTas: 1,
        saldoKoin: 25, stokUmpan: 10, config: baseConfig, availableButtons: allBtns
      }),
      "SIMPAN"
    );

    // 5. Night hour detection for lamp (18.30 - 04.30)
    function isNightHour(text) {
      const lower = text.toLowerCase();
      if (lower.includes("malam")) return true;
      const m = lower.match(/(\d{1,2})\.(\d{2})/);
      if (!m) return false;
      const mins = parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
      return mins >= 1110 || mins < 270;
    }

    assert.equal(isNightHour("Malam 21.15"), true);
    assert.equal(isNightHour("Subuh 04.10"), true);
    assert.equal(isNightHour("Sore 18.45"), true);
    assert.equal(isNightHour("Siang 13.00"), false);
  });

  await t.test("Pre-fetch gate locks features until /api/pancing status is loaded", () => {
    function getHudControlState({ loaded, loading, loadError, autoMancing }) {
      const checkboxesDisabled = !loaded;
      if (!loaded) {
        if (loading) return { checkboxesDisabled, startDisabled: true, action: "WAIT" };
        if (loadError) return { checkboxesDisabled, startDisabled: false, action: "RETRY_FETCH" };
        return { checkboxesDisabled, startDisabled: true, action: "WAIT" };
      }
      return { checkboxesDisabled: false, startDisabled: false, action: autoMancing ? "STOP" : "START" };
    }

    assert.deepEqual(getHudControlState({ loaded: false, loading: true, loadError: null, autoMancing: false }), {
      checkboxesDisabled: true,
      startDisabled: true,
      action: "WAIT"
    });
    assert.deepEqual(getHudControlState({ loaded: false, loading: false, loadError: "HTTP 500", autoMancing: false }), {
      checkboxesDisabled: true,
      startDisabled: false,
      action: "RETRY_FETCH"
    });
    assert.deepEqual(getHudControlState({ loaded: true, loading: false, loadError: null, autoMancing: false }), {
      checkboxesDisabled: false,
      startDisabled: false,
      action: "START"
    });
  });

  await t.test("Boat lepasM range filter and rod/boat capability parsing", () => {
    function parseCapabilities(data) {
      const aktifKapal = Array.isArray(data.kapal?.daftar)
        ? data.kapal.daftar.find(k => k.dipakai)
        : null;
      const joranDipakai = data.joranDipakai || data.joran?.find(j => j.dipakai)?.id || "joran-bambu";
      return {
        kapalNama: aktifKapal?.nama || "Perahu jukung",
        lepasM: typeof data.kapal?.lepasM === "number" ? data.kapal.lepasM : (aktifKapal?.lepasM ?? 0),
        hasJaring: !!data.jaring,
        hasLampu: !!(data.kapal?.lampu ?? aktifKapal?.lampu),
        joranId: joranDipakai
      };
    }

    const starterCap = parseCapabilities({
      kapal: { lepasM: 0, lampu: false, daftar: [{ nama: "Perahu jukung", dipakai: true, lepasM: 0 }] },
      jaring: null,
      joran: [{ id: "joran-bambu", dipakai: true }]
    });
    assert.equal(starterCap.kapalNama, "Perahu jukung");
    assert.equal(starterCap.lepasM, 0);
    assert.equal(starterCap.hasJaring, false);
    assert.equal(starterCap.hasLampu, false);
    assert.equal(starterCap.joranId, "joran-bambu");

    // Starter boat (lepasM=0) must filter out offshore spot beyond bay boundary (z < -640)
    const spots = [
      { x: 0, z: -560, kaya: 0.5 },
      { x: 0, z: -900, kaya: 0.9 }
    ];
    const minReachableZ = -640 - starterCap.lepasM;
    const reachable = spots.filter(s => s.z >= minReachableZ);
    assert.equal(reachable.length, 1);
    assert.equal(reachable[0].z, -560);
  });

  await t.test("Small fish converts to umpan-ikan (2.3x big fish) when autoUmpanIkan is enabled", () => {
    function decideSmallFishAction({ autoUmpanIkan, isSmallFish, hasUmpanIkanBtn, hasLepasBtn }) {
      if (autoUmpanIkan && isSmallFish && hasUmpanIkanBtn) return "JADIKAN_UMPAN";
      if (isSmallFish && hasLepasBtn) return "LEPAS";
      return "SIMPAN";
    }

    assert.equal(
      decideSmallFishAction({ autoUmpanIkan: true, isSmallFish: true, hasUmpanIkanBtn: true, hasLepasBtn: true }),
      "JADIKAN_UMPAN"
    );
    assert.equal(
      decideSmallFishAction({ autoUmpanIkan: false, isSmallFish: true, hasUmpanIkanBtn: true, hasLepasBtn: true }),
      "LEPAS"
    );
    assert.equal(
      decideSmallFishAction({ autoUmpanIkan: true, isSmallFish: true, hasUmpanIkanBtn: false, hasLepasBtn: true }),
      "LEPAS"
    );
  });

  await t.test("Bait strategy switch toggles Cumi (deep Celup) vs Ternak Umpan Ikan (Cacing shallow Lempar)", () => {
    function resolveStrategyMode(strategiUmpan, equippedUmpan) {
      const targetPref = strategiUmpan === "ternak-ikan" ? "umpan-cacing" : "umpan-cumi";
      const useLempar = strategiUmpan === "ternak-ikan" && equippedUmpan === "umpan-cacing";
      const minDepth = useLempar ? 2 : 30;
      return { targetPref, useLempar, minDepth };
    }

    assert.deepEqual(resolveStrategyMode("cumi", "umpan-cumi"), {
      targetPref: "umpan-cumi",
      useLempar: false,
      minDepth: 30
    });
    assert.deepEqual(resolveStrategyMode("ternak-ikan", "umpan-cacing"), {
      targetPref: "umpan-cacing",
      useLempar: true,
      minDepth: 2
    });
    assert.deepEqual(resolveStrategyMode("ternak-ikan", "umpan-ikan"), {
      targetPref: "umpan-cacing",
      useLempar: false,
      minDepth: 30
    });

    function canStartWithStrategy({ loaded, strategiUmpan }) {
      if (!loaded) return { startDisabled: true, reason: "LOADING" };
      if (!strategiUmpan) return { startDisabled: true, reason: "PICK_STRATEGY" };
      return { startDisabled: false, reason: "READY" };
    }
    assert.deepEqual(canStartWithStrategy({ loaded: true, strategiUmpan: "" }), {
      startDisabled: true,
      reason: "PICK_STRATEGY"
    });
    assert.deepEqual(canStartWithStrategy({ loaded: true, strategiUmpan: "ternak-ikan" }), {
      startDisabled: false,
      reason: "READY"
    });

    // Skip buying bait if active bait or any existing bait stock > 0
    function decideShopOrSail({ activeStok, umpanList, targetPref }) {
      if (activeStok > 0) return { action: "SAIL_NO_BUY", equip: null };
      const ikan = umpanList.find(u => u.id === "umpan-ikan");
      if (ikan && ikan.stok > 0) return { action: "EQUIP_EXISTING", equip: "umpan-ikan" };
      const pref = umpanList.find(u => u.id === targetPref);
      if (pref && pref.stok > 0) return { action: "EQUIP_EXISTING", equip: targetPref };
      const any = umpanList.find(u => u.stok > 0);
      if (any) return { action: "EQUIP_EXISTING", equip: any.id };
      return { action: "BUY_NEW", equip: targetPref };
    }

    assert.equal(
      decideShopOrSail({ activeStok: 5, umpanList: [{ id: "umpan-cumi", stok: 5 }], targetPref: "umpan-cumi" }).action,
      "SAIL_NO_BUY"
    );
    assert.deepEqual(
      decideShopOrSail({ activeStok: 0, umpanList: [{ id: "umpan-cacing", stok: 4 }, { id: "umpan-cumi", stok: 0 }], targetPref: "umpan-cumi" }),
      { action: "EQUIP_EXISTING", equip: "umpan-cacing" }
    );
    assert.deepEqual(
      decideShopOrSail({ activeStok: 0, umpanList: [{ id: "umpan-cumi", stok: 0 }], targetPref: "umpan-cumi" }),
      { action: "BUY_NEW", equip: "umpan-cumi" }
    );

    // Batching: collect min(5, sisaSlot) umpan-ikan before switching and sailing to >=30m
    function shouldSwitchToUmpanIkan({ strategiUmpan, equipped, umpanIkanStok, sisaSlot }) {
      if (strategiUmpan !== "ternak-ikan" || equipped !== "umpan-cacing") return false;
      const batchTarget = Math.min(5, Math.max(1, sisaSlot));
      return umpanIkanStok >= batchTarget;
    }

    assert.equal(shouldSwitchToUmpanIkan({ strategiUmpan: "ternak-ikan", equipped: "umpan-cacing", umpanIkanStok: 2, sisaSlot: 20 }), false);
    assert.equal(shouldSwitchToUmpanIkan({ strategiUmpan: "ternak-ikan", equipped: "umpan-cacing", umpanIkanStok: 5, sisaSlot: 20 }), true);
    assert.equal(shouldSwitchToUmpanIkan({ strategiUmpan: "ternak-ikan", equipped: "umpan-cacing", umpanIkanStok: 3, sisaSlot: 3 }), true);

    // Area ranking: Tier 3 (depth >= minDepth AND kaya >= 0.45 Ramai) beats shallow Ramai or deep Lumayan
    const RAMAI_MIN_KAYA = 0.45;
    function rankAreas(spots, minDepth) {
      return spots
        .map(s => {
          const meetsDepth = s.depth >= minDepth;
          const isRamai = s.kaya >= RAMAI_MIN_KAYA;
          const tier = (meetsDepth && isRamai) ? 3 : meetsDepth ? 2 : isRamai ? 1 : 0;
          const score = (tier * 1000) + (s.kaya * 400) + (s.depth >= 30 ? 120 : s.depth) - (s.dist * 0.05);
          return { ...s, tier, score };
        })
        .sort((a, b) => b.score - a.score);
    }

    const ranked = rankAreas([
      { id: "shallow_ramai", depth: 10, kaya: 0.90, dist: 50 },
      { id: "deep_lumayan", depth: 33, kaya: 0.35, dist: 200 },
      { id: "deep_ramai", depth: 32, kaya: 0.55, dist: 450 }
    ], 30);
    assert.equal(ranked[0].id, "deep_ramai");
    assert.equal(ranked[0].tier, 3);
    assert.equal(ranked[1].id, "deep_lumayan");

    // In ternak-ikan mode too: small fish -> JADIKAN_UMPAN, medium (< 1.00 koin) -> LEPAS (if safe reserve), >= 1.00 -> JUAL
    function decideTernakLoot({ isSmallFish, sellPrice, sisaTas, hasUmpanIkanBtn, hasSafeReserve = true }) {
      if (isSmallFish && hasUmpanIkanBtn) return "JADIKAN_UMPAN";
      if (sellPrice >= 1.00) return "JUAL";
      if (sellPrice < 1.00 && hasSafeReserve) return "LEPAS";
      if (sisaTas > 0) return "SIMPAN";
      return "JUAL_TAS_PENUH";
    }
    assert.equal(decideTernakLoot({ isSmallFish: false, sellPrice: 0.83, sisaTas: 15, hasUmpanIkanBtn: false }), "LEPAS");
    assert.equal(decideTernakLoot({ isSmallFish: true, sellPrice: 0.42, sisaTas: 15, hasUmpanIkanBtn: true }), "JADIKAN_UMPAN");
  });
});
