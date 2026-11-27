import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const extDir = path.resolve(__dirname, "..");

function humanJitter(min, max) {
  return Math.floor(min + Math.random() * (max - min + 1));
}

// Long-hold hysteresis reel tension controller (30% <-> 80% with per-cycle jitter & zero-loss guard)
class MockMancingReelController {
  constructor(modeNatural = true, zeroLossGuard = true) {
    this.modeNatural = modeNatural;
    this.zeroLossGuard = zeroLossGuard;
    this.isPulling = false;
    this.reelCoolingDown = false;
    this.strikeTriggered = false;
    this.baseMaxTension = 80;
    this.baseMinTension = 30;
    this.reelTargetMax = this.rollReelMax();
    this.reelTargetMin = this.rollReelMin();
  }

  rollReelMax() {
    if (!this.zeroLossGuard) return 84;
    return this.baseMaxTension + (this.modeNatural ? humanJitter(-2, 2) : 0);
  }

  rollReelMin() {
    return this.baseMinTension + (this.modeNatural ? humanJitter(-2, 2) : 0);
  }

  resetReelCycle() {
    this.reelCoolingDown = false;
    this.reelTargetMax = this.rollReelMax();
    this.reelTargetMin = this.rollReelMin();
  }

  evaluateTension(tensionPct, isDanger, isHoldingDom = this.isPulling) {
    const hitCeiling = (this.zeroLossGuard && isDanger) || tensionPct >= this.reelTargetMax;
    if (hitCeiling) {
      if (!this.reelCoolingDown) {
        this.reelCoolingDown = true;
        this.reelTargetMin = this.rollReelMin();
      }
      this.isPulling = false;
      return "RELEASE";
    }
    if (this.reelCoolingDown) {
      const safeToHold = !(this.zeroLossGuard && isDanger);
      if (safeToHold && tensionPct <= this.reelTargetMin) {
        this.reelCoolingDown = false;
        this.reelTargetMax = this.rollReelMax();
        this.isPulling = true;
        return "PULL";
      }
      this.isPulling = false;
      return "COOLDOWN_RELEASE";
    }
    if (!this.isPulling || !isHoldingDom) {
      this.isPulling = true;
      return "PULL";
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
  await t.test("Long-hold hysteresis releases at ceiling/danger and stays released until ~30%", () => {
    const ctrl = new MockMancingReelController(false, true);
    assert.equal(ctrl.reelTargetMax, 80);
    assert.equal(ctrl.reelTargetMin, 30);

    // Starts pulling smoothly from 30% -> 80%
    assert.equal(ctrl.evaluateTension(40, false, false), "PULL");
    assert.equal(ctrl.isPulling, true);
    assert.equal(ctrl.evaluateTension(70, false, true), "MAINTAIN");

    // Hits ceiling (80%) -> enters cooldown and releases
    assert.equal(ctrl.evaluateTension(80, false, true), "RELEASE");
    assert.equal(ctrl.isPulling, false);
    assert.equal(ctrl.reelCoolingDown, true);

    // Must NOT immediately re-grab at 79% or 55% during cooldown (fixes 40ms press/release spam)
    assert.equal(ctrl.evaluateTension(79, false, false), "COOLDOWN_RELEASE");
    assert.equal(ctrl.evaluateTension(55, false, false), "COOLDOWN_RELEASE");
    assert.equal(ctrl.isPulling, false);

    // Drops to <= 30% -> exits cooldown and begins next long hold
    assert.equal(ctrl.evaluateTension(30, false, false), "PULL");
    assert.equal(ctrl.isPulling, true);
    assert.equal(ctrl.reelCoolingDown, false);

    // Danger flag (data-merah) at 65% immediately triggers release & cooldown
    assert.equal(ctrl.evaluateTension(65, true, true), "RELEASE");
    assert.equal(ctrl.isPulling, false);
    assert.equal(ctrl.reelCoolingDown, true);

    // Reset clears cooldown for next fish
    ctrl.resetReelCycle();
    assert.equal(ctrl.reelCoolingDown, false);
  });

  await t.test("Long-hold hysteresis re-presses if DOM drops data-tahan mid-hold, and respects Zero-Loss OFF ceiling (84%)", () => {
    const ctrl = new MockMancingReelController(false, true);
    ctrl.isPulling = true;
    ctrl.reelCoolingDown = false;

    // Mid-hold at 50%, DOM dropped data-tahan -> re-presses without spamming
    assert.equal(ctrl.evaluateTension(50, false, false), "PULL");
    assert.equal(ctrl.isPulling, true);

    // Zero-Loss OFF uses 84% ceiling
    const loose = new MockMancingReelController(false, false);
    assert.equal(loose.reelTargetMax, 84);
    assert.equal(loose.evaluateTension(82, true, true), "PULL");
    assert.equal(loose.evaluateTension(84, false, true), "RELEASE");
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

  await t.test("Smart tension hysteresis handles slack recovery without 40ms spam", () => {
    function evaluateHysteresisTick({ isRed, tension, reelTargetMax, reelTargetMin, reelCoolingDown, isHoldingDom }) {
      if (isRed || tension >= reelTargetMax) {
        return { action: "RELEASE", reelCoolingDown: true };
      }
      if (reelCoolingDown) {
        if (!isRed && tension <= reelTargetMin) {
          return { action: "HOLD", reelCoolingDown: false };
        }
        return { action: "RELEASE", reelCoolingDown: true };
      }
      if (!isHoldingDom) {
        return { action: "HOLD", reelCoolingDown: false };
      }
      return { action: "MAINTAIN", reelCoolingDown: false };
    }

    assert.deepEqual(
      evaluateHysteresisTick({ isRed: true, tension: 70, reelTargetMax: 80, reelTargetMin: 30, reelCoolingDown: false, isHoldingDom: true }),
      { action: "RELEASE", reelCoolingDown: true }
    );
    assert.deepEqual(
      evaluateHysteresisTick({ isRed: false, tension: 78, reelTargetMax: 80, reelTargetMin: 30, reelCoolingDown: true, isHoldingDom: false }),
      { action: "RELEASE", reelCoolingDown: true }
    );
    assert.deepEqual(
      evaluateHysteresisTick({ isRed: false, tension: 28, reelTargetMax: 80, reelTargetMin: 30, reelCoolingDown: true, isHoldingDom: false }),
      { action: "HOLD", reelCoolingDown: false }
    );
    assert.deepEqual(
      evaluateHysteresisTick({ isRed: false, tension: 50, reelTargetMax: 80, reelTargetMin: 30, reelCoolingDown: false, isHoldingDom: false }),
      { action: "HOLD", reelCoolingDown: false }
    );
    assert.deepEqual(
      evaluateHysteresisTick({ isRed: false, tension: 65, reelTargetMax: 80, reelTargetMin: 30, reelCoolingDown: false, isHoldingDom: true }),
      { action: "MAINTAIN", reelCoolingDown: false }
    );
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

  await t.test("Proportional steering, turning-only stuck guard, smart braking, and polarity self-correction", () => {
    function createSteerState() {
      return {
        lastRecordedShipH: null,
        shipHStuckCount: 0,
        lastCommandedBelok: 0,
        lastAbsHeadingDiff: null,
        wrongTurnStreak: 0,
        navTurnSign: 1
      };
    }

    function stepSteering(state, { targetHeading, shipH, dist, synced = true }) {
      let diff = (targetHeading - shipH + Math.PI) % (2 * Math.PI);
      if (diff < 0) diff += 2 * Math.PI;
      diff -= Math.PI;
      const absDiff = Math.abs(diff);

      if (absDiff > 0.04 && (Math.abs(state.lastCommandedBelok) > 0.15 || state.shipHStuckCount > 25)) {
        if (state.lastRecordedShipH !== null && Math.abs(shipH - state.lastRecordedShipH) < 0.0008) {
          state.shipHStuckCount++;
        } else {
          state.shipHStuckCount = 0;
          state.lastRecordedShipH = shipH;
        }
        if (Math.abs(state.lastCommandedBelok) > 0.15 && state.lastAbsHeadingDiff !== null && absDiff > 0.35 && absDiff < 2.6) {
          if (absDiff > state.lastAbsHeadingDiff + 0.005) {
            state.wrongTurnStreak++;
            if (state.wrongTurnStreak >= 8) {
              state.navTurnSign *= -1;
              state.wrongTurnStreak = 0;
            }
          } else if (absDiff < state.lastAbsHeadingDiff - 0.003) {
            state.wrongTurnStreak = 0;
          }
        }
      } else {
        state.shipHStuckCount = 0;
        state.wrongTurnStreak = 0;
        state.lastRecordedShipH = shipH;
      }
      state.lastAbsHeadingDiff = absDiff;

      let belok = 0;
      if (synced && state.shipHStuckCount <= 25 && absDiff > 0.04) {
        const rawTurn = Math.max(-1, Math.min(1, diff / 0.45));
        belok = rawTurn * state.navTurnSign;
      }

      let gas = 1.0;
      if (absDiff > 1.05) gas = 0.15;
      else if (absDiff > 0.45) gas = 0.55;
      else if (dist < 25) gas = Math.max(0.25, Math.min(1, dist / 25));

      state.lastCommandedBelok = belok;
      return { gas, belok };
    }

    // 1. Sailing straight for 50 ticks with constant shipH must NEVER trip stuck guard!
    const straightState = createSteerState();
    for (let i = 0; i < 50; i++) {
      const out = stepSteering(straightState, { targetHeading: Math.PI, shipH: Math.PI, dist: 100 });
      assert.equal(out.belok, 0);
      assert.equal(out.gas, 1.0);
    }
    assert.equal(straightState.shipHStuckCount, 0);
    // Subsequent turn still responds immediately
    const afterStraight = stepSteering(straightState, { targetHeading: Math.PI - 0.3, shipH: Math.PI, dist: 100 });
    assert.ok(afterStraight.belok < -0.5, "Must steer normally after sailing straight");

    // 2. Sharp turn (> 1.05 rad) slows gas to 0.15 to avoid orbiting; close approach (< 25m) decelerates
    const turnState = createSteerState();
    const sharp = stepSteering(turnState, { targetHeading: 0, shipH: 1.5, dist: 80 });
    assert.equal(sharp.gas, 0.15);
    const close = stepSteering(createSteerState(), { targetHeading: 0, shipH: 0.01, dist: 10 });
    assert.equal(close.belok, 0);
    assert.equal(close.gas, 0.4);

    // 3. Polarity auto-correction flips navTurnSign after 8 diverging ticks while actively turning
    const wrongState = createSteerState();
    wrongState.lastCommandedBelok = 1;
    let h = 1.0;
    for (let i = 0; i < 10; i++) {
      stepSteering(wrongState, { targetHeading: 1.8, shipH: h, dist: 100 });
      h -= 0.05; // heading drifting away from 1.8 despite turn command
    }
    assert.equal(wrongState.navTurnSign, -1);

    // 4. Stuck guard triggers only when actively turning and heading stays frozen (> 25 ticks)
    const frozenState = createSteerState();
    let lastOut = { belok: 1, gas: 1 };
    for (let i = 0; i < 28; i++) {
      lastOut = stepSteering(frozenState, { targetHeading: 2.5, shipH: 1.5, dist: 100 });
    }
    assert.equal(lastOut.belok, 0, "Frozen heading during active turn eventually zeroes belok");
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

  await t.test("Celup deep-sea arrival stops immediately on 5/5 sonar bars or inner core (not outer 3-4 bar rim)", () => {
    function shouldStopAtSpot({ dist, radius, sonarDepth, sonarCrowd, sonarBars, minDepth = 30, maxDepth = null, optimalDepth = 32, spotIsRamai = true }) {
      const inDepthRange = sonarDepth >= minDepth && (maxDepth == null || sonarDepth <= maxDepth);
      const coreRadius = Math.min(8, Math.max(5, (radius || 30) * 0.25));
      const reachedFiveBars = typeof sonarBars === "number" && sonarBars >= 5 && inDepthRange;
      const reachedSpotCore = dist <= coreRadius && inDepthRange;
      const reachedLumayanFallback = !spotIsRamai && sonarCrowd === "Lumayan" && inDepthRange;
      const reachedOptimalDepth = !spotIsRamai && sonarDepth >= optimalDepth && inDepthRange && sonarCrowd !== "Sepi";
      return reachedFiveBars || reachedSpotCore || reachedLumayanFallback || reachedOptimalDepth;
    }

    // Outer rim of Ramai spot (dist=20m, only 3 bars) -> keep sailing toward core/5-bar zone!
    assert.equal(shouldStopAtSpot({ dist: 20, radius: 30, sonarDepth: 33, sonarCrowd: "Ramai", sonarBars: 3 }), false);

    // Hits 5/5 sonar bars even at 18m from dead center -> stop immediately!
    assert.equal(shouldStopAtSpot({ dist: 18, radius: 30, sonarDepth: 33, sonarCrowd: "Ramai", sonarBars: 5 }), true);

    // 5/5 bars in too-shallow water (12m < 30m) -> do NOT stop
    assert.equal(shouldStopAtSpot({ dist: 10, radius: 30, sonarDepth: 12, sonarCrowd: "Ramai", sonarBars: 5 }), false);

    // Spot caps at 4 bars -> stops once inside inner core (<= 7.5m for r=30)
    assert.equal(shouldStopAtSpot({ dist: 7, radius: 30, sonarDepth: 32, sonarCrowd: "Ramai", sonarBars: 4 }), true);

    // Shallow ternak-ikan target (minDepth=2, maxDepth=10): rejects 32m deep water even with 5/5 bars
    assert.equal(
      shouldStopAtSpot({ dist: 5, radius: 30, sonarDepth: 32, sonarCrowd: "Ramai", sonarBars: 5, minDepth: 2, maxDepth: 10 }),
      false
    );
    assert.equal(
      shouldStopAtSpot({ dist: 12, radius: 30, sonarDepth: 6, sonarCrowd: "Ramai", sonarBars: 5, minDepth: 2, maxDepth: 10 }),
      true
    );
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

    // Batching: collect min(10, sisaSlot) umpan-ikan before switching and sailing to >=30m
    function shouldSwitchToUmpanIkan({ strategiUmpan, equipped, umpanIkanStok, sisaSlot }) {
      if (strategiUmpan !== "ternak-ikan" || equipped !== "umpan-cacing") return false;
      const batchTarget = Math.min(10, Math.max(1, sisaSlot));
      return umpanIkanStok >= batchTarget;
    }

    assert.equal(shouldSwitchToUmpanIkan({ strategiUmpan: "ternak-ikan", equipped: "umpan-cacing", umpanIkanStok: 5, sisaSlot: 20 }), false);
    assert.equal(shouldSwitchToUmpanIkan({ strategiUmpan: "ternak-ikan", equipped: "umpan-cacing", umpanIkanStok: 10, sisaSlot: 20 }), true);
    assert.equal(shouldSwitchToUmpanIkan({ strategiUmpan: "ternak-ikan", equipped: "umpan-cacing", umpanIkanStok: 3, sisaSlot: 3 }), true);

    // Area ranking: Tier 4 (5-bar >= 0.78 + meetsDepth) beats Tier 3 (Ramai >= 0.45 + meetsDepth)
    const RAMAI_MIN_KAYA = 0.45;
    const FIVE_BAR_MIN_KAYA = 0.78;
    function rankAreas(spots, minDepth, maxDepth = null) {
      return spots
        .map(s => {
          const meetsDepth = s.depth >= minDepth && (maxDepth === null || s.depth <= maxDepth);
          const isRamai = s.kaya >= RAMAI_MIN_KAYA;
          const isFiveBar = s.kaya >= FIVE_BAR_MIN_KAYA;
          const tier = (meetsDepth && isFiveBar) ? 4 : (meetsDepth && isRamai) ? 3 : meetsDepth ? 2 : isRamai ? 1 : 0;
          const score = (tier * 1000) + (s.kaya * 600) + (s.depth >= 30 ? 120 : s.depth) - (s.dist * 0.08);
          return { ...s, tier, score };
        })
        .sort((a, b) => b.score - a.score);
    }

    const ranked = rankAreas([
      { id: "shallow_5bar", depth: 10, kaya: 0.90, dist: 50 },
      { id: "deep_lumayan", depth: 33, kaya: 0.35, dist: 200 },
      { id: "deep_ramai", depth: 32, kaya: 0.55, dist: 150 },
      { id: "deep_5bar", depth: 34, kaya: 0.85, dist: 450 }
    ], 30);
    assert.equal(ranked[0].id, "deep_5bar");
    assert.equal(ranked[0].tier, 4);
    assert.equal(ranked[1].id, "deep_ramai");
    assert.equal(ranked[1].tier, 3);

    // Default selectiveRelease OFF: medium fish (< 1.00 koin) is saved instead of released; opt-in ON releases it
    function decideTernakLoot({ isSmallFish, sellPrice, sisaTas, hasUmpanIkanBtn, selectiveRelease = false, hasSafeReserve = true }) {
      if (isSmallFish && hasUmpanIkanBtn) return "JADIKAN_UMPAN";
      if (sellPrice >= 1.00) return "JUAL";
      if (selectiveRelease && sellPrice < 1.00 && hasSafeReserve) return "LEPAS";
      if (sisaTas > 0) return "SIMPAN";
      return "JUAL_TAS_PENUH";
    }
    assert.equal(decideTernakLoot({ isSmallFish: false, sellPrice: 0.83, sisaTas: 15, hasUmpanIkanBtn: false, selectiveRelease: false }), "SIMPAN");
    assert.equal(decideTernakLoot({ isSmallFish: false, sellPrice: 0.83, sisaTas: 15, hasUmpanIkanBtn: false, selectiveRelease: true }), "LEPAS");
    assert.equal(decideTernakLoot({ isSmallFish: true, sellPrice: 0.42, sisaTas: 15, hasUmpanIkanBtn: true }), "JADIKAN_UMPAN");
  });

  await t.test("Bait-loss accounting, deduplication, consecutive trash, and makan profit correction", () => {
    const roundCoin = (v) => Math.round((Number(v) || 0) * 100) / 100;
    const costOf = (t) => (t === "umpan-ikan" ? 0 : t === "umpan-cumi" ? 0.5 : t === "umpan-udang" ? 0.3 : 0.2);

    const stats = { catches: 0, losses: 0, totalLoss: 0, totalProfit: 0, history: [] };
    let lastLossKey = null;
    let lastLossTime = 0;

    function recordLoss({ id = "", reason = "dimakan", umpan = "umpan-cumi" }, now) {
      const dedupKey = id ? `${id}:${reason}` : `${reason}:${Math.floor(now / 2500)}`;
      if (dedupKey === lastLossKey || now - lastLossTime < 2200) return false;
      lastLossKey = dedupKey;
      lastLossTime = now;
      const cost = costOf(umpan);
      stats.losses++;
      stats.totalLoss = roundCoin(stats.totalLoss + cost);
      stats.totalProfit = roundCoin(stats.totalProfit - cost);
      stats.history.unshift({ reason, profit: -cost, isLoss: true });
      return true;
    }

    // First API loss recorded (-0.50), phase-transition fallback 450ms later deduplicated
    assert.equal(recordLoss({ id: "c1", reason: "dimakan", umpan: "umpan-cumi" }, 10000), true);
    assert.equal(recordLoss({ id: "", reason: "dimakan", umpan: "umpan-cumi" }, 10450), false);
    assert.equal(stats.losses, 1);
    assert.equal(stats.totalProfit, -0.5);

    // Consecutive identical trash catches both deduct baitCost once lastCatchId resets after loot click
    let lastCatchId = null;
    for (let i = 0; i < 2; i++) {
      const key = "Sandal jepit-172 g";
      assert.notEqual(lastCatchId, key);
      lastCatchId = key;
      stats.losses++;
      stats.totalLoss = roundCoin(stats.totalLoss + 0.5);
      stats.totalProfit = roundCoin(stats.totalProfit - 0.5);
      lastCatchId = null; // reset on click
    }
    assert.equal(stats.losses, 3);
    assert.equal(stats.totalLoss, 1.5);
    assert.equal(stats.totalProfit, -1.5);

    // Eating a caught fish ("makan") corrects initial +sellPrice - baitCost down to -baitCost
    const sellPrice = 0.85;
    const baitCost = 0.50;
    stats.totalProfit = roundCoin(stats.totalProfit + (sellPrice - baitCost)); // +0.35 tentative
    stats.totalProfit = roundCoin(stats.totalProfit - sellPrice); // makan correction -> -0.50 net
    assert.equal(stats.totalProfit, -2.0);
  });

  await t.test("Last-bait (1 -> 0) grace window waits before stopping or switching owned bait", () => {
    function handleZeroBait({ now, lastCelupTime, strategiUmpan, autoUmpanIkan, autoUmpan, owned }) {
      if (lastCelupTime > 0 && now - lastCelupTime < 3000) {
        return { action: "WAIT_LAST_CAST" };
      }
      if (strategiUmpan === "ternak-ikan") {
        if (owned["umpan-ikan"] > 0) return { action: "SWITCH_OWNED", bait: "umpan-ikan" };
        if (owned["umpan-cacing"] > 0) return { action: "SWITCH_OWNED", bait: "umpan-cacing" };
      } else if (autoUmpanIkan && owned["umpan-ikan"] > 0) {
        return { action: "SWITCH_OWNED", bait: "umpan-ikan" };
      }
      if (autoUmpan) return { action: "AUTO_BUY" };
      return { action: "STOP_NO_BAIT" };
    }

    // 900ms after casting last bait -> wait so cast finishes!
    assert.deepEqual(
      handleZeroBait({ now: 5900, lastCelupTime: 5000, strategiUmpan: "cumi", autoUmpanIkan: true, autoUmpan: false, owned: {} }),
      { action: "WAIT_LAST_CAST" }
    );
    // After 3s grace window with owned umpan-ikan -> free switch even when autoUmpan is OFF
    assert.deepEqual(
      handleZeroBait({ now: 9000, lastCelupTime: 5000, strategiUmpan: "cumi", autoUmpanIkan: true, autoUmpan: false, owned: { "umpan-ikan": 3 } }),
      { action: "SWITCH_OWNED", bait: "umpan-ikan" }
    );
    // After 3s grace window with no owned bait & autoUmpan OFF -> stop safely
    assert.deepEqual(
      handleZeroBait({ now: 9000, lastCelupTime: 5000, strategiUmpan: "cumi", autoUmpanIkan: true, autoUmpan: false, owned: {} }),
      { action: "STOP_NO_BAIT" }
    );
    // After 3s grace window with no owned bait & opt-in autoUmpan ON -> buy
    assert.deepEqual(
      handleZeroBait({ now: 9000, lastCelupTime: 5000, strategiUmpan: "cumi", autoUmpanIkan: true, autoUmpan: true, owned: {} }),
      { action: "AUTO_BUY" }
    );
  });

  await t.test("mancing.js defaults keep Auto Beli Umpan, Auto Upgrade, and Selektif Lepas OFF & opt-in", () => {
    const src = fs.readFileSync(path.join(extDir, "mancing.js"), "utf-8");

    assert.match(src, /selectiveRelease:\s*false\b/, "selectiveRelease must default to false");
    assert.match(src, /autoUmpan:\s*false\b/, "autoUmpan must default to false");
    assert.match(src, /autoUpgrade:\s*false\b/, "autoUpgrade must default to false");
    assert.match(src, /baseMinTension:\s*30\b/, "baseMinTension must default to 30 for long-hold hysteresis");

    // All 3 checkboxes must exist in HUD without `checked` attribute
    assert.match(src, /<input type="checkbox" id="ks-opt-auto-umpan"(?![^>]*\bchecked\b)/);
    assert.match(src, /<input type="checkbox" id="ks-opt-auto-upgrade"(?![^>]*\bchecked\b)/);
    assert.match(src, /<input type="checkbox" id="ks-opt-selective-release"(?![^>]*\bchecked\b)/);

    // Strategy dropdown onchange must NOT force selectiveRelease = true
    const dropdownBlock = src.match(/getElementById\("ks-opt-strategi-umpan"\)\.onchange\s*=\s*\(e\)\s*=>\s*\{[\s\S]*?\};/);
    assert.ok(dropdownBlock, "strategy dropdown onchange handler must exist");
    assert.doesNotMatch(dropdownBlock[0], /selectiveRelease\s*=\s*true/, "dropdown must never force selectiveRelease = true");
  });

  await t.test("inject.js: passive /api/pancing fetch observer, hasSetInput, and analog setInput vs keys isolation", async () => {
    const listeners = {};
    const baitLostEvents = [];
    const mancingUpdates = [];
    const fetchHandlers = [];

    const win = {
      console: { log() {}, warn() {}, error() {} },
      performance: { now: () => 1000 },
      CustomEvent: class { constructor(type, init) { this.type = type; this.detail = init && init.detail; } },
      setTimeout: () => 1,
      clearTimeout: () => {},
      setInterval: () => 1,
      clearInterval: () => {},
      addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
      removeEventListener() {},
      dispatchEvent(ev) { for (const fn of (listeners[ev.type] || []).slice()) fn(ev); return true; },
      location: { href: "https://www.kampungsebelah.com/mancing" },
      document: { hidden: false, visibilityState: "visible", hasFocus: () => true, addEventListener() {}, querySelector: () => null },
      fetch: (url, init) => {
        const next = fetchHandlers.shift();
        const payload = next ? next(url, init) : {};
        const makeRes = () => ({ ok: true, clone: () => makeRes(), json: () => Promise.resolve(payload) });
        return Promise.resolve(makeRes());
      }
    };
    win.window = win;
    win.globalThis = win;

    const ctx = vm.createContext(win);
    vm.runInContext(fs.readFileSync(path.join(extDir, "inject.js"), "utf-8"), ctx, { filename: "inject.js" });

    win.addEventListener("ks_mancing_bait_lost", (e) => baitLostEvents.push(e.detail));
    win.addEventListener("ks_mancing_data_update", (e) => mancingUpdates.push(e.detail));

    // 1. POST /api/pancing responses: dimakan, tarik fail, batal emit events; tarik dapat does NOT
    fetchHandlers.push(
      () => ({ dimakan: "Umpan dimakan ikan kecil", lemparan: { id: "L1", umpan: "umpan-cumi" } }),
      () => ({ hasil: "putus", lemparan: { id: "L2", umpan: "umpan-cumi" } }),
      () => ({ hasil: "dapat", ikan: { nama: "Kuwe" }, lemparan: { id: "L3", umpan: "umpan-cumi" } }),
      () => ({ ok: true })
    );

    await win.fetch("/api/pancing", { method: "POST", body: JSON.stringify({ aksi: "lempar", umpan: "umpan-cumi" }) });
    await win.fetch("/api/pancing", { method: "POST", body: JSON.stringify({ aksi: "tarik", id: "L2", berhasil: false }) });
    await win.fetch("/api/pancing", { method: "POST", body: JSON.stringify({ aksi: "tarik", id: "L3", berhasil: true }) });
    await win.fetch("/api/pancing", { method: "POST", body: JSON.stringify({ aksi: "batal", id: "L4" }) });
    await new Promise((r) => setTimeout(r, 10));

    assert.equal(baitLostEvents.length, 3);
    assert.deepEqual(baitLostEvents.map((e) => e.reason), ["dimakan", "putus", "batal"]);
    assert.equal(baitLostEvents[0].umpan, "umpan-cumi");

    // 2. ks_mancing_steer with setInput clamps values and clears mInst.keys
    const setInputCalls = [];
    const keysWithSetInput = new Set(["w", "a", "d"]);
    win.__KS_MANCING_INSTANCE = {
      setInput: (v) => setInputCalls.push({ gas: v.gas, belok: v.belok }),
      keys: keysWithSetInput
    };
    win.dispatchEvent(new win.CustomEvent("ks_mancing_steer", { detail: { gas: 1.5, belok: -1.8 } }));
    assert.deepEqual(setInputCalls, [{ gas: 1, belok: -1 }]);
    assert.equal(keysWithSetInput.size, 0, "keys must be cleared when analog setInput is used");

    // 3. ks_mancing_steer without setInput falls back to mInst.keys
    const keysFallback = new Set();
    win.__KS_MANCING_INSTANCE = { keys: keysFallback };
    win.dispatchEvent(new win.CustomEvent("ks_mancing_steer", { detail: { gas: 0.8, belok: 0.4 } }));
    assert.equal(keysFallback.has("w"), true);
    assert.equal(keysFallback.has("a"), true);
    assert.equal(keysFallback.has("d"), false);

    // 4. posisi() hook attaches __KS_MANCING_INSTANCE and reports hasSetInput (assigned property triggers Object.prototype.posisi setter)
    const shipObj = vm.runInContext(`(() => {
      const o = { perahu: true, titik: [], setInput() {} };
      o.posisi = function () { return { x: 10, z: -200, h: 3.14, laju: 2 }; };
      return o;
    })()`, ctx);
    shipObj.posisi();
    assert.equal(win.__KS_MANCING_INSTANCE, shipObj);
    assert.equal(mancingUpdates.at(-1).hasSetInput, true);
  });
});
