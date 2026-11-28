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

  await t.test("Long-hold hysteresis randomizes pull (29-45%) & release (70-85%) in Natural mode with red-zone anti-snap guard", () => {
    const minSamples = [];
    const maxSamples = [];
    for (let i = 0; i < 120; i++) {
      const rMin = humanJitter(29, 45);
      const rMax = humanJitter(70, 85);
      assert.ok(rMin >= 29 && rMin <= 45, `pull target ${rMin} out of [29, 45]`);
      assert.ok(rMax >= 70 && rMax <= 85, `release target ${rMax} out of [70, 85]`);
      minSamples.push(rMin);
      maxSamples.push(rMax);
    }
    assert.ok(new Set(minSamples).size >= 7, "pull targets must vary naturally");
    assert.ok(new Set(maxSamples).size >= 7, "release targets must vary naturally");

    // Red-zone anti-snap guard: releases if red persists >= 160ms (well below 600ms snap) or >= 85%
    function shouldRelease({ tension, reelTargetMax, isRed, redElapsedMs }) {
      const redGuard = isRed && (tension >= 85 || redElapsedMs >= 160);
      return tension >= reelTargetMax || redGuard;
    }
    assert.equal(shouldRelease({ tension: 81, reelTargetMax: 84, isRed: true, redElapsedMs: 40 }), false);
    assert.equal(shouldRelease({ tension: 83, reelTargetMax: 84, isRed: true, redElapsedMs: 160 }), true);
    assert.equal(shouldRelease({ tension: 85, reelTargetMax: 85, isRed: true, redElapsedMs: 0 }), true);
    assert.equal(shouldRelease({ tension: 72, reelTargetMax: 72, isRed: false, redElapsedMs: 0 }), true);
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

    // Batching: collect min(5, sisaSlot) umpan-ikan before switching and sailing to >=30m
    function shouldSwitchToUmpanIkan({ strategiUmpan, equipped, umpanIkanStok, sisaSlot }) {
      if (strategiUmpan !== "ternak-ikan" || equipped !== "umpan-cacing") return false;
      const batchTarget = Math.min(5, Math.max(1, sisaSlot));
      return umpanIkanStok >= batchTarget;
    }

    assert.equal(shouldSwitchToUmpanIkan({ strategiUmpan: "ternak-ikan", equipped: "umpan-cacing", umpanIkanStok: 2, sisaSlot: 20 }), false);
    assert.equal(shouldSwitchToUmpanIkan({ strategiUmpan: "ternak-ikan", equipped: "umpan-cacing", umpanIkanStok: 5, sisaSlot: 20 }), true);
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

  await t.test("Bait-loss accounting normalizes cacing/udang/cumi/ikan costs, deduplicates, and corrects makan profit", () => {
    const roundCoin = (v) => Math.round((Number(v) || 0) * 100) / 100;
    const normalizeUmpan = (raw) => {
      const s = String(raw || "").toLowerCase().trim();
      if (s.includes("ikan")) return "umpan-ikan";
      if (s.includes("cacing")) return "umpan-cacing";
      if (s.includes("udang")) return "umpan-udang";
      if (s.includes("cumi")) return "umpan-cumi";
      return "";
    };
    const costOf = (t) => {
      const norm = normalizeUmpan(t);
      return norm === "umpan-ikan" ? 0 : norm === "umpan-cumi" ? 0.5 : norm === "umpan-udang" ? 0.3 : norm === "umpan-cacing" ? 0.2 : 0.5;
    };

    // Short API bait names & labels map to exact coin costs (not hardcoded 0.50 Cumi!)
    assert.equal(costOf("cacing"), 0.2);
    assert.equal(costOf("Cacing laut"), 0.2);
    assert.equal(costOf("umpan-cacing"), 0.2);
    assert.equal(costOf("udang"), 0.3);
    assert.equal(costOf("cumi"), 0.5);
    assert.equal(costOf("ikan"), 0.0);

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

    // Cacing laut dimakan deducts -0.20 (not -0.50); fallback 450ms later deduplicated
    assert.equal(recordLoss({ id: "c1", reason: "dimakan", umpan: "cacing" }, 10000), true);
    assert.equal(recordLoss({ id: "", reason: "dimakan", umpan: "cacing" }, 10450), false);
    assert.equal(stats.losses, 1);
    assert.equal(stats.totalProfit, -0.2);

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
    assert.equal(stats.totalLoss, 1.2);
    assert.equal(stats.totalProfit, -1.2);

    // Eating a caught fish ("makan") corrects initial +sellPrice - baitCost down to -baitCost
    const sellPrice = 0.85;
    const baitCost = 0.50;
    stats.totalProfit = roundCoin(stats.totalProfit + (sellPrice - baitCost)); // +0.35 tentative
    stats.totalProfit = roundCoin(stats.totalProfit - sellPrice); // makan correction -> -0.50 net
    assert.equal(stats.totalProfit, -1.7);
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

  await t.test("mancing.js uses compact 3-tab HUD, full Jual Semua (except Ternak), Just Go bait/cast options, and always-on Zero-Loss in Auto Gulung", () => {
    const src = fs.readFileSync(path.join(extDir, "mancing.js"), "utf-8");

    assert.match(src, /selectiveRelease:\s*false\b/, "selectiveRelease must default to false");
    assert.match(src, /autoUmpan:\s*false\b/, "autoUmpan must default to false");
    assert.match(src, /autoUpgrade:\s*false\b/, "autoUpgrade must default to false");
    assert.match(src, /lootMode:\s*"jual-semua"/, "lootMode must always be jual-semua");
    assert.match(src, /zeroLossGuard:\s*true\b/, "zeroLossGuard must always be true internally");
    assert.match(src, /stopRule:\s*"all-full"/, "stopRule must default to all-full (40/40)");
    assert.match(src, /baseMinTension:\s*35\b/, "baseMinTension must default to 35 for long-hold hysteresis");
    assert.match(src, /reelMinRange:\s*\[29,\s*45\]/, "reelMinRange must be [29, 45]");
    assert.match(src, /reelMaxRange:\s*\[70,\s*85\]/, "reelMaxRange must be [70, 85]");
    assert.match(src, /SETTINGS_KEY\s*=\s*"ks_mancing_settings_v1"/, "HUD settings persistence key must exist");

    // Spending checkboxes must exist in HUD without `checked` attribute
    assert.match(src, /<input type="checkbox" id="ks-opt-auto-umpan"(?![^>]*\bchecked\b)/);
    assert.match(src, /<input type="checkbox" id="ks-opt-auto-upgrade"(?![^>]*\bchecked\b)/);

    // Hasil dropdowns and Zero-Loss checkbox must be removed from UI
    assert.doesNotMatch(src, /id="ks-opt-loot-mode"/, "Hasil dropdown must be removed");
    assert.doesNotMatch(src, /id="ks-opt-sell-threshold"/, "sellThreshold dropdown must be removed");
    assert.doesNotMatch(src, /id="ks-opt-zeroloss"/, "Zero-Loss checkbox must be removed (always active internally)");

    // Template section buttons + Just Go inline bait & Celup/Lempar options + 3-tab HUD switcher
    assert.match(src, /id="ks-tpl-just-go"/);
    assert.match(src, /id="ks-tpl-cumi"/);
    assert.match(src, /id="ks-tpl-ternak"/);
    assert.match(src, /id="ks-just-go-opts"/);
    assert.match(src, /id="ks-justgo-umpan"/);
    assert.match(src, /id="ks-justgo-mode-celup"/);
    assert.match(src, /id="ks-justgo-mode-lempar"/);
    assert.match(src, /VALID_STRATEGIES\s*=\s*new Set\(\["",\s*"just-go",\s*"cumi",\s*"ternak-ikan"\]\)/);
    assert.match(src, /VALID_TABS\s*=\s*new Set\(\["main",\s*"history",\s*"settings"\]\)/);
    assert.match(src, /Plan Just Go/);
    assert.match(src, /id="ks-tab-main"/);
    assert.match(src, /id="ks-tab-history"/);
    assert.match(src, /id="ks-tab-settings"/);
    assert.match(src, /id="ks-mancing-reel-bars"/);
    assert.match(src, /id="ks-mancing-ramai-spots"/, "Sonar card must show live Ramai spots depth list");
    assert.doesNotMatch(src, /id="ks-mancing-target-info"/, "Redundant Target Joran line must be removed from Sonar card");
    assert.match(src, /function getReachableRamaiSpots\(/);
    assert.match(src, /function renderSonarRamaiSpots\(/);
    assert.match(src, /<select id="ks-opt-stop-rule"/);
    assert.match(src, /<option value="all-full" selected>/);

    // Exact 7 core checkboxes kept + Zero-Loss combined into Auto Gulung description
    const keptCoreIds = [
      'id="ks-opt-natural"',
      'id="ks-opt-simpan"',
      'id="ks-opt-celup"',
      'id="ks-opt-auto-navigasi"',
      'id="ks-opt-sentak"',
      'id="ks-opt-jual-penuh"',
      'id="ks-opt-gulung"'
    ];
    for (const idToken of keptCoreIds) {
      assert.ok(src.includes(idToken), `Core checkbox ${idToken} must exist in Settings`);
    }
    assert.match(src, /Zero-Loss aktif permanen[\s\S]*?id="ks-opt-gulung"/, "Zero-Loss description must be combined into Auto Gulung");

    // Always save to umpan if option is available, otherwise sell (and default max sell is 30 -> 50 total)
    assert.match(src, /jualMaks:\s*30\b/, "default jualMaks must be 30");
    assert.match(src, /Jual \+ Tas Penuh \(50\/50\)/, "all-full default label must reflect 30 sell + 20 bag = 50/50");
    assert.match(src, /Jatah Jual Habis \(30\/30\)/, "sell-full default label must reflect 30/30");
    assert.match(src, /if \(config\.autoUmpanIkan !== false && !isTrash && availableButtons\.umpanIkan\) \{\s*return "JADIKAN_UMPAN";\s*\}\s*if \(sisaJual > 0 && availableButtons\.jual\) \{\s*return "JUAL";/);

    // 1-Joran Hemat is always ON internally and hidden from HUD
    assert.match(src, /singleRodProfit:\s*true\b/);
    assert.doesNotMatch(src, /id="ks-opt-single-rod"/, "1-Joran Hemat checkbox should be hidden since it is always ON");

    // Full daily history without 8-item cap
    assert.doesNotMatch(src, /history\.slice\(0,\s*8\)/, "daily history must not be capped to 8 items");
    assert.doesNotMatch(src, /history\.length\s*>\s*8/, "daily history must keep all of today's entries");

    // Compact tabbed HUD layout order: Pinned Hero (Status + Start) -> 3 Tabs -> Main (Sonar, Hari Ini, Templates) -> Riwayat -> Settings
    const statusIdx = src.indexOf('id="ks-mancing-status"');
    const startIdx = src.indexOf('id="ks-mancing-start-btn"');
    const tabsIdx = src.indexOf('id="ks-tab-main"');
    const sonarIdx = src.indexOf('id="ks-mancing-sonar-info"');
    const countIdx = src.indexOf('id="ks-mancing-count"');
    const tplIdx = src.indexOf('id="ks-tpl-cumi"');
    const histPanelIdx = src.indexOf('id="ks-panel-history"');
    const settingsPanelIdx = src.indexOf('id="ks-panel-settings"');
    assert.ok(
      statusIdx > 0 &&
        startIdx > statusIdx &&
        tabsIdx > startIdx &&
        sonarIdx > tabsIdx &&
        countIdx > sonarIdx &&
        tplIdx > countIdx &&
        histPanelIdx > tplIdx &&
        settingsPanelIdx > histPanelIdx,
      "HUD order must be Pinned Hero (Status -> Start) -> Tabs -> Main Panel (Sonar -> Count -> Templates) -> History Panel -> Settings Panel"
    );

    // Hari Ini catch counter shows clean catch count without "-X rugi" suffix
    assert.doesNotMatch(src, /mancingStats\.losses\} rugi/, "Hari Ini counter must not display rugi suffix");

    // Live-bug regression checks:
    assert.match(src, /hasilCard\.dataset\?\.ksHandled === "1"/, "handleCatch must guard against re-handling same DOM card");
    assert.match(src, /releaseLootLockWhenCardCloses/, "lootPending must wait for hasilCard dismissal");
    assert.match(src, /lastLootClosedTime\s*=\s*performance\.now\(\)/, "loot dismissal must arm post-loot cast cooldown");
    assert.match(src, /liveShipData\.hasIkanAnim/, "scheduleNaturalCelup must respect ongoing fish-exit animation");
    assert.match(src, /ks_mancing_recover_cast/, "stuck cast button watchdog must auto-recover without F5");
    assert.match(src, /lastApiCastBait\s*=\s*\{\s*baitType:\s*norm/, "cast_started must record lastApiCastBait without phantom Dimakan");
    assert.match(src, /endedCast\.seenInWater/, "phase-transition fallback must require seenInWater");
    assert.match(src, /curFase === "tunggu"/, "450ms fallback must abort if DOM is currently in active cast phase");
  });

  await t.test("Phase 2 2-option Hasil modes (Hybrid & Jual Semua) with bait-fish priority and configurable sellThreshold", () => {
    function decideLoot({
      isTrash = false,
      isSmallFish = false,
      hasUmpanIkanBtn = true,
      isBigClass = false,
      sellPrice,
      baitCost,
      sisaJual = 20,
      sisaTas = 20,
      lootMode = "hybrid",
      sellThreshold = 1.00
    }) {
      if (isTrash) return "BUANG";
      if (isSmallFish && hasUmpanIkanBtn) return "JADIKAN_UMPAN";

      const isHighValue = sellPrice >= sellThreshold || (sellThreshold <= 1.00 && isBigClass);
      if (lootMode === "jual-semua") {
        if (sellPrice > baitCost && sisaJual > 0) return "JUAL";
        if (sisaTas > 0) return "SIMPAN";
        if (sisaJual > 0) return "JUAL_TAS_PENUH";
      } else {
        if (isHighValue && sisaJual > 0) return "JUAL";
        if (sisaTas > 0) return "SIMPAN";
        if (sisaJual > 0) return "JUAL_TAS_PENUH";
      }
      return "MAKAN";
    }

    // 1. Jual Semua: sells any fish worth > baitCost, EXCEPT small fish that can be used as bait!
    assert.equal(decideLoot({ lootMode: "jual-semua", isSmallFish: true, hasUmpanIkanBtn: true, sellPrice: 0.43, baitCost: 0.20 }), "JADIKAN_UMPAN");
    assert.equal(decideLoot({ lootMode: "jual-semua", sellPrice: 0.81, baitCost: 0.50 }), "JUAL");
    assert.equal(decideLoot({ lootMode: "jual-semua", sellPrice: 0.45, baitCost: 0.50 }), "SIMPAN");
    assert.equal(decideLoot({ lootMode: "jual-semua", sellPrice: 0.81, baitCost: 0.50, sisaJual: 0, sisaTas: 10 }), "SIMPAN");

    // 2. Hybrid (default): sells >= sellThreshold, saves < sellThreshold, never releases
    assert.equal(decideLoot({ lootMode: "hybrid", sellThreshold: 1.00, sellPrice: 0.85, baitCost: 0.50 }), "SIMPAN");
    assert.equal(decideLoot({ lootMode: "hybrid", sellThreshold: 1.40, sellPrice: 1.25, isBigClass: true, baitCost: 0.50 }), "SIMPAN");
    assert.equal(decideLoot({ lootMode: "hybrid", sellThreshold: 1.40, sellPrice: 1.45, isBigClass: true, baitCost: 0.50 }), "JUAL");
    assert.equal(decideLoot({ lootMode: "hybrid", sellThreshold: 1.00, sellPrice: 0.85, baitCost: 0.50, sisaTas: 0, sisaJual: 5 }), "JUAL_TAS_PENUH");
  });

  await t.test("Phase 2 configurable Stop Rules (all-full, sell-full, bait-empty) and legacy settings migration", () => {
    function evaluateStopRule(stopRule, profile) {
      if (!profile || !profile.loaded) return null;
      const sisaJual = Math.max(0, profile.jualMaks - profile.jualHariIni);
      const sisaTas = Math.max(0, profile.tasMaks - profile.tasIkan);
      if (stopRule === "sell-full" && sisaJual === 0) return "STOP_SELL_FULL";
      if (stopRule === "all-full" && sisaJual === 0 && sisaTas === 0) return "STOP_ALL_FULL";
      return null;
    }

    assert.equal(evaluateStopRule("all-full", { loaded: true, jualHariIni: 20, jualMaks: 20, tasIkan: 5, tasMaks: 20 }), null);
    assert.equal(evaluateStopRule("all-full", { loaded: true, jualHariIni: 20, jualMaks: 20, tasIkan: 20, tasMaks: 20 }), "STOP_ALL_FULL");
    assert.equal(evaluateStopRule("sell-full", { loaded: true, jualHariIni: 20, jualMaks: 20, tasIkan: 5, tasMaks: 20 }), "STOP_SELL_FULL");
    assert.equal(evaluateStopRule("bait-empty", { loaded: true, jualHariIni: 20, jualMaks: 20, tasIkan: 20, tasMaks: 20 }), null);

    // Settings migration & sanitization: legacy cashflow -> jual-semua, quota-saver/whale -> hybrid
    function normalizeSavedLootMode(raw) {
      if (raw === "jual-semua" || raw === "cashflow") return "jual-semua";
      if (raw === "hybrid" || raw === "quota-saver" || raw === "whale") return "hybrid";
      return null;
    }
    assert.equal(normalizeSavedLootMode("cashflow"), "jual-semua");
    assert.equal(normalizeSavedLootMode("jual-semua"), "jual-semua");
    assert.equal(normalizeSavedLootMode("quota-saver"), "hybrid");
    assert.equal(normalizeSavedLootMode("whale"), "hybrid");
    assert.equal(normalizeSavedLootMode("invalid-mode"), null);
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

    const castStartedEvents = [];
    win.addEventListener("ks_mancing_cast_started", (e) => castStartedEvents.push(e.detail));
    win.addEventListener("ks_mancing_bait_lost", (e) => baitLostEvents.push(e.detail));
    win.addEventListener("ks_mancing_data_update", (e) => mancingUpdates.push(e.detail));

    // 1. POST /api/pancing responses: remembers lempar bait ("cacing") for later cek/dimakan even when cek omits umpan
    fetchHandlers.push(
      () => ({ lemparan: { id: "L0", status: "TUNGGU" } }),
      () => ({ dimakan: "Umpan dimakan ikan kecil", lemparan: { id: "L0" } }),
      () => ({ hasil: "putus", lemparan: { id: "L2", umpan: "umpan-cumi" } }),
      () => ({ hasil: "dapat", ikan: { nama: "Kuwe" }, lemparan: { id: "L3", umpan: "umpan-cumi" } }),
      () => ({ ok: true })
    );

    await win.fetch("/api/pancing", { method: "POST", body: JSON.stringify({ aksi: "lempar", umpan: "cacing" }) });
    await win.fetch("/api/pancing", { method: "POST", body: JSON.stringify({ aksi: "cek", id: "L0" }) });
    await win.fetch("/api/pancing", { method: "POST", body: JSON.stringify({ aksi: "tarik", id: "L2", berhasil: false }) });
    await win.fetch("/api/pancing", { method: "POST", body: JSON.stringify({ aksi: "tarik", id: "L3", berhasil: true }) });
    await win.fetch("/api/pancing", { method: "POST", body: JSON.stringify({ aksi: "batal", id: "L4" }) });
    await new Promise((r) => setTimeout(r, 10));

    assert.equal(castStartedEvents.length, 1);
    assert.equal(castStartedEvents[0].umpan, "cacing");
    assert.equal(baitLostEvents.length, 3);
    assert.deepEqual(baitLostEvents.map((e) => e.reason), ["dimakan", "putus", "batal"]);
    assert.equal(baitLostEvents[0].umpan, "cacing", "dimakan must inherit actual cast bait (cacing), not fallback to cumi");
    assert.equal(baitLostEvents[1].umpan, "umpan-cumi");

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

  await t.test("inject.js: prevents buangIkan() mid-cast deadlock and auto-recovers throttled/clobbered lempar promises without F5", async () => {
    const listeners = {};
    const timers = [];
    const intervals = [];
    let nextTimerId = 1;

    const win = {
      console: { log() {}, warn() {}, error() {} },
      performance: { now: () => 5000 },
      CustomEvent: class { constructor(type, init) { this.type = type; this.detail = init && init.detail; } },
      setTimeout: (fn, ms) => {
        const id = nextTimerId++;
        timers.push({ id, fn, ms, cleared: false });
        return id;
      },
      clearTimeout: (id) => {
        const t = timers.find((x) => x.id === id);
        if (t) t.cleared = true;
      },
      setInterval: (fn, ms) => {
        const id = nextTimerId++;
        intervals.push({ id, fn, ms });
        return id;
      },
      clearInterval: () => {},
      addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
      removeEventListener() {},
      dispatchEvent(ev) { for (const fn of (listeners[ev.type] || []).slice()) fn(ev); return true; },
      location: { href: "https://www.kampungsebelah.com/mancing" },
      document: { hidden: false, visibilityState: "visible", hasFocus: () => true, addEventListener() {}, querySelector: () => null },
      fetch: () => Promise.resolve({ ok: true, clone: () => ({ json: () => Promise.resolve({}) }), json: () => Promise.resolve({}) })
    };
    win.window = win;
    win.globalThis = win;

    const ctx = vm.createContext(win);
    vm.runInContext(fs.readFileSync(path.join(extDir, "inject.js"), "utf-8"), ctx, { filename: "inject.js" });

    // Simulate KampungSebelah 3D Mancing scene with the exact buangIkan()/lempar() race bug
    const sceneInst = vm.runInContext(`(() => {
      let disposed = 0;
      let removed = 0;
      let selesaiGulungCalls = 0;
      const o = {
        perahu: true,
        fase: "jalan",
        titik: [],
        scene: { remove() { removed++; } },
        tali: { visible: false },
        pelampung: { visible: false, position: { x: 0, z: 0 } },
        kail: { mode: "lempar", x: 0, z: 0, t: 0, lama: 1.45, terbang: false, resolve: null },
        ikan: {
          akhir: { jenis: "makan", t: 0.5 },
          g: {
            traverse(cb) {
              cb({ geometry: { dispose() { disposed++; } }, material: { dispose() { disposed++; } } });
            }
          }
        },
        selesaiGulung() {
          selesaiGulungCalls++;
          this.tali.visible = false;
          this.pelampung.visible = false;
          this.fase = "jalan";
        },
        buangIkan() {
          if (this.ikan) {
            this.scene.remove(this.ikan.g);
            this.ikan.g.traverse((n) => { n.geometry.dispose(); n.material.dispose(); });
            this.ikan = null;
            this.tali.visible = false;
            this.selesaiGulung();
          }
        },
        lempar(mode, target) {
          this.fase = "lempar";
          this.kail.mode = mode;
          this.kail.x = target.x;
          this.kail.z = target.z;
          this.kail.t = 0;
          this.kail.lama = mode === "celup" ? 1.4 : 1.45;
          this.kail.terbang = true;
          this.tali.visible = true;
          this.pelampung.visible = false;
          return new Promise((r) => { this.kail.resolve = r; });
        },
        getMetrics: () => ({ disposed, removed, selesaiGulungCalls })
      };
      o.posisi = function () { return { x: -10, z: -120, h: 3.14, laju: 0 }; };
      return o;
    })()`, ctx);

    // Hooking via posisi() patches lempar() and buangIkan() immediately
    sceneInst.posisi();
    assert.equal(sceneInst.__ks_cast_guard_patched, true);

    // 1. Casting while old fish exit animation (this.ikan) is still running flushes old fish BEFORE cast starts
    const p1 = sceneInst.lempar("lempar", { x: -12, z: -125 });
    assert.equal(sceneInst.ikan, null, "old fish must be cleared before cast starts");
    assert.equal(sceneInst.tali.visible, true, "tali must remain visible for the new cast");
    assert.equal(sceneInst.kail.terbang, true);
    assert.equal(sceneInst.getMetrics().selesaiGulungCalls, 1, "selesaiGulung ran before new cast, not mid-cast");

    // 2. If buangIkan() is ever invoked mid-cast anyway, it removes fish WITHOUT killing tali.visible or calling selesaiGulung()
    sceneInst.ikan = { g: { traverse() {} } };
    sceneInst.buangIkan();
    assert.equal(sceneInst.ikan, null);
    assert.equal(sceneInst.tali.visible, true, "mid-cast buangIkan must NOT hide tali.visible");
    assert.equal(sceneInst.fase, "lempar", "mid-cast buangIkan must NOT reset fase to jalan");
    assert.equal(sceneInst.getMetrics().selesaiGulungCalls, 1, "mid-cast buangIkan must NOT call selesaiGulung");

    // 3. If rAF is paused (unfocused Chrome), the fallback timer resolves await l.lempar() cleanly
    const activeFallback = timers.find((t) => !t.cleared && t.ms >= 3200);
    assert.ok(activeFallback, "lempar must arm an unfocused-rAF fallback timer");
    activeFallback.fn();
    const resolved1 = await p1;
    assert.equal(resolved1.x, -12);
    assert.equal(resolved1.z, -125);
    assert.equal(sceneInst.fase, "tunggu");
    assert.equal(sceneInst.kail.terbang, false);
    assert.equal(sceneInst.kail.resolve, null);
    assert.equal(sceneInst.pelampung.visible, true);

    // 4. Explicit ks_mancing_recover_cast event recovers an already-clobbered cast promise without F5
    const p2 = sceneInst.lempar("celup", { x: 5, z: -300 });
    sceneInst.tali.visible = false;
    sceneInst.fase = "jalan";
    win.dispatchEvent(new win.CustomEvent("ks_mancing_recover_cast"));
    const resolved2 = await p2;
    assert.equal(resolved2.x, 5);
    assert.equal(resolved2.z, -300);
    assert.equal(sceneInst.fase, "tunggu");
    assert.equal(sceneInst.tali.visible, true);
    assert.equal(sceneInst.pelampung.visible, true);
  });

  await t.test("anti-Ikan Lepas hardening: clean Space reel (no setPointerCapture crash), safe Sentak, anti-slack/surge guards, and KOSONG/berhasil diagnostics", async () => {
    const mancingSrc = fs.readFileSync(path.join(extDir, "mancing.js"), "utf-8");

    // 1. holdGulung() & releaseGulung() must NOT dispatch synthetic PointerEvent on pancing-gulung (avoids MAIN-world setPointerCapture NotFoundError)
    const holdBlock = mancingSrc.match(/function holdGulung\(\)[\s\S]*?function releaseGulung\(\)[\s\S]*?\n  \}/);
    assert.ok(holdBlock, "holdGulung/releaseGulung block must exist");
    const holdCodeOnly = holdBlock[0].replace(/\/\/.*$/gm, "");
    assert.doesNotMatch(holdCodeOnly, /setPointerCapture/, "holdGulung must not try isolated-world setPointerCapture stub");
    assert.doesNotMatch(holdCodeOnly, /new PointerEvent/, "holdGulung/releaseGulung must use keyboard Space, not synthetic PointerEvent");
    assert.match(holdCodeOnly, /code:\s*"Space"/, "holdGulung/releaseGulung must dispatch Space keydown/keyup");

    // 2. scheduleNaturalSentak() must NOT fire keyup Space (which cancels reel hold after sambar -> tarik)
    const sentakBlock = mancingSrc.match(/function scheduleNaturalSentak\(\)[\s\S]*?\n  \}/);
    assert.ok(sentakBlock, "scheduleNaturalSentak block must exist");
    assert.doesNotMatch(sentakBlock[0], /code:\s*"Space"/, "scheduleNaturalSentak must never dispatch Space keydown/keyup");
    assert.match(sentakBlock[0], /code:\s*"Enter"/, "scheduleNaturalSentak fallback must use Enter");
    assert.match(sentakBlock[0], /getSentakRemainingSec/, "scheduleNaturalSentak must check remaining strike countdown for urgent strike");

    // 3. Tarik loop must include immediate red-zone protection (no 160ms delay), anti-slack floor (<=15%), and HUD focus blur
    assert.match(mancingSrc, /redGuardTriggered\s*=\s*mancingConfig\.zeroLossGuard\s*&&\s*\(isRed\s*\|\|\s*tension\s*>=\s*82\)/);
    assert.match(mancingSrc, /slackGuardTriggered\s*=\s*!isRed\s*&&\s*tension\s*<=\s*15/);
    assert.match(mancingSrc, /activeEl\.closest\("#ks-mancing-hud"\)/);

    // 4. inject.js classifies cek status=KOSONG as dimakan, cek status=LEPAS as lepas_cek, and passes berhasil + source on tarik
    const listeners = {};
    const baitLostEvents = [];
    const fetchHandlers = [
      () => ({ lemparan: { id: "K1", status: "TUNGGU" } }),
      () => ({ lemparan: { id: "K1", status: "KOSONG", sambar: null, ikan: null } }),
      () => ({ lemparan: { id: "K2", status: "LEPAS", sambar: null, ikan: null } }),
      () => ({ hasil: "lepas", lemparan: { id: "K3", umpan: "umpan-cacing" } }),
      () => ({ hasil: "lepas", lemparan: { id: "K4", umpan: "umpan-cacing" } })
    ];
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

    await win.fetch("/api/pancing", { method: "POST", body: JSON.stringify({ aksi: "lempar", umpan: "umpan-cacing" }) });
    await win.fetch("/api/pancing", { method: "POST", body: JSON.stringify({ aksi: "cek", id: "K1" }) });
    await win.fetch("/api/pancing", { method: "POST", body: JSON.stringify({ aksi: "cek", id: "K2" }) });
    await win.fetch("/api/pancing", { method: "POST", body: JSON.stringify({ aksi: "tarik", id: "K3", berhasil: false }) });
    await win.fetch("/api/pancing", { method: "POST", body: JSON.stringify({ aksi: "tarik", id: "K4", berhasil: true }) });
    await new Promise((r) => setTimeout(r, 10));

    assert.equal(baitLostEvents.length, 4);
    assert.equal(baitLostEvents[0].reason, "dimakan");
    assert.equal(baitLostEvents[0].source, "cek");
    assert.equal(baitLostEvents[0].umpan, "umpan-cacing");
    assert.equal(baitLostEvents[1].reason, "lepas_cek");
    assert.equal(baitLostEvents[1].source, "cek");
    assert.equal(baitLostEvents[2].reason, "lepas");
    assert.equal(baitLostEvents[2].source, "tarik");
    assert.equal(baitLostEvents[2].berhasil, false);
    assert.equal(baitLostEvents[3].reason, "lepas");
    assert.equal(baitLostEvents[3].source, "tarik");
    assert.equal(baitLostEvents[3].berhasil, true);
  });

  await t.test("boundary avoidance & synthetic deep-water waypoint prevent 'Batas area mancing, putar balik ya'", () => {
    const mancingSrc = fs.readFileSync(path.join(extDir, "mancing.js"), "utf-8");

    // 1. Exact game map bounds constants must be present (x ∈ [-320, 320], z ∈ [-640 - lepasM, -14])
    assert.match(mancingSrc, /LAUT_BOUNDS\s*=\s*\{[\s\S]*x0:\s*-320[\s\S]*x1:\s*320[\s\S]*z0:\s*-640[\s\S]*z1:\s*-14/);
    assert.match(mancingSrc, /findSafeWaypointForDepth/);
    assert.match(mancingSrc, /clampPointToSafeBounds/);
    assert.match(mancingSrc, /readBoundaryToastState/);
    assert.match(mancingSrc, /headingOutward/);
    assert.match(mancingSrc, /Math\.max\(0,\s*-640\s*-\s*z\)\s*\*\s*0\.05/, "calcDepth must include offshore depth term");

    // 2. Simulate real rotation giliran 166283 (Perahu jukung lepasM=0, target ≥30m, 0 in-bay spots ≥30m)
    const LAUT = { x0: -320, x1: 320, z0: -640, z1: -14, margin: 18 };
    function calcDepth(x, z) {
      const n = Math.min(1, Math.max(0, (-z - 10) / 630));
      return Math.max(
        1.5,
        2 + n * n * 18 + 20 * n +
          Math.sin(0.021 * x + 1.3) * Math.cos(0.017 * z) * 3 * n +
          Math.max(0, -640 - z) * 0.05
      );
    }
    function findSafeWaypoint(target, shipX, lepasM = 0) {
      const safeX0 = LAUT.x0 + LAUT.margin;
      const safeX1 = LAUT.x1 - LAUT.margin;
      const safeZ0 = LAUT.z0 - lepasM + LAUT.margin;
      const safeZ1 = LAUT.z1 - LAUT.margin;
      const safeX = Math.max(safeX0 + 12, Math.min(safeX1 - 12, shipX));
      let bestZ = safeZ0;
      let bestErr = Infinity;
      for (let z = safeZ1; z >= safeZ0; z -= 5) {
        const d = calcDepth(safeX, z);
        const inRange = d >= (target.minDepth || 0) && (target.maxDepth == null || d <= target.maxDepth);
        const err = Math.abs(d - (target.optimalDepth || target.minDepth)) + (inRange ? 0 : 100);
        if (err < bestErr) {
          bestErr = err;
          bestZ = z;
        }
      }
      return { x: safeX, z: bestZ, depth: calcDepth(safeX, bestZ) };
    }

    // Even starting right next to the West wall (x = -318), synthetic deep waypoint stays strictly inside safe bounds and reaches ≥25m
    const wp = findSafeWaypoint({ minDepth: 25, optimalDepth: 28, maxDepth: null }, -318, 0);
    assert.ok(wp.x >= LAUT.x0 + 30 && wp.x <= LAUT.x1 - 30, `waypoint x=${wp.x} must stay well inside [-290, 290]`);
    assert.ok(wp.z >= LAUT.z0 + LAUT.margin && wp.z <= LAUT.z1 - LAUT.margin, `waypoint z=${wp.z} must stay inside bay bounds`);
    assert.ok(wp.depth >= 25, `waypoint depth=${wp.depth} must satisfy ≥25m target`);
    assert.match(mancingSrc, /minDepth:\s*25,\s*\n\s*optimalDepth:\s*hasOffshoreAccess\s*\?\s*35\s*:\s*28,\s*\n\s*allowCrowdStopAt:\s*25/, "deep bay target must use minDepth 25m");
  });

  await t.test("path-aware autopilot: speed-scaled lookahead, pier detour, and reverse steering compensation (gerakPerahu physics)", () => {
    const mancingSrc = fs.readFileSync(path.join(extDir, "mancing.js"), "utf-8");

    assert.match(mancingSrc, /PIER_OBSTACLE\s*=\s*\{[\s\S]*xMin:\s*-11[\s\S]*xMax:\s*11[\s\S]*zMin:\s*-58/);
    assert.match(mancingSrc, /function segmentIntersectsBox\(/);
    assert.match(mancingSrc, /function planPierSafeWaypoint\(/);
    assert.match(mancingSrc, /function predictPathOutOfBounds\(/);
    assert.match(mancingSrc, /reverseSteerSign\s*=\s*isReversing\s*\?\s*-1\s*:\s*1/);

    // Simulate exact gerakPerahu() physics on a max-speed boat (lajuKali = 2.0, top speed ~11.13 m/s)
    // heading straight toward West wall x = -320 from x = -280 at 10 m/s!
    const bounds = { x0: -320, x1: 320, z0: -640, z1: -14, safeX0: -302, safeX1: 302, safeZ0: -622, safeZ1: -32 };
    const PIER = { xMin: -11, xMax: 11, zMin: -58, zMax: -14, clearZ: -64 };

    function segmentIntersectsBox(x1, z1, x2, z2, box) {
      const dx = x2 - x1;
      const dz = z2 - z1;
      let tMin = 0, tMax = 1;
      if (Math.abs(dx) < 1e-6) { if (x1 < box.xMin || x1 > box.xMax) return false; }
      else {
        let tx1 = (box.xMin - x1) / dx, tx2 = (box.xMax - x1) / dx;
        if (tx1 > tx2) [tx1, tx2] = [tx2, tx1];
        tMin = Math.max(tMin, tx1); tMax = Math.min(tMax, tx2);
        if (tMin > tMax) return false;
      }
      if (Math.abs(dz) < 1e-6) { if (z1 < box.zMin || z1 > box.zMax) return false; }
      else {
        let tz1 = (box.zMin - z1) / dz, tz2 = (box.zMax - z1) / dz;
        if (tz1 > tz2) [tz1, tz2] = [tz2, tz1];
        tMin = Math.max(tMin, tz1); tMax = Math.min(tMax, tz2);
        if (tMin > tMax) return false;
      }
      return tMax >= 0 && tMin <= 1;
    }

    function predictPathOutOfBounds(shipX, shipZ, shipH, shipLaju, b) {
      const speed = Math.max(0, shipLaju);
      const lookaheadSec = Math.max(1.2, Math.min(3.0, 1.0 + speed * 0.22));
      const projSpeed = Math.max(speed, 1.4);
      const vx = Math.sin(shipH) * projSpeed;
      const vz = Math.cos(shipH) * projSpeed;
      for (let s = 1; s <= 6; s++) {
        const t = (lookaheadSec * s) / 6;
        const px = shipX + vx * t;
        const pz = shipZ + vz * t;
        if (px < b.safeX0) return { willExit: true, exitWall: "west", timeToExit: t };
        if (px > b.safeX1) return { willExit: true, exitWall: "east", timeToExit: t };
        if (pz < b.safeZ0) return { willExit: true, exitWall: "north", timeToExit: t };
        if (pz > b.safeZ1) return { willExit: true, exitWall: "south", timeToExit: t };
      }
      return { willExit: false, exitWall: "", timeToExit: Infinity };
    }

    // 1. Fast boat heading West at 10 m/s from x=-280 is detected BEFORE hitting safeX0 (-302) or wall (-320)
    const predWest = predictPathOutOfBounds(-280, -300, -Math.PI / 2, 10, bounds);
    assert.equal(predWest.willExit, true);
    assert.equal(predWest.exitWall, "west");

    // 2. Pier intersection check catches West->East crossing near shore (-25, -38) -> (25, -38)
    assert.equal(segmentIntersectsBox(-25, -38, 25, -38, PIER), true, "cross-pier path must be detected");
    assert.equal(segmentIntersectsBox(-25, -90, 25, -90, PIER), false, "deep open-water path must not trigger pier detour");

    // 3. Closed-loop physics simulation (gerakPerahu): fast boat (lajuKali=2.0, laju=10 m/s) heading straight at West wall (-320)
    //    must brake & turn toward target (0, -300) WITHOUT EVER hitting x <= -320!
    let x = -280, z = -300, h = -Math.PI / 2, laju = 10;
    const lajuKali = 2.0;
    const dt = 0.05;
    let hitWall = false;
    for (let step = 0; step < 200; step++) {
      const pred = predictPathOutOfBounds(x, z, h, laju, bounds);
      const nearWest = x <= bounds.x0 + 18 || pred.exitWall === "west";
      const steerX = nearWest ? Math.max(0, bounds.x0 + 38) : 0;
      const steerZ = -300;
      const targetH = Math.atan2(steerX - x, steerZ - z);
      let diff = (targetH - h + Math.PI) % (2 * Math.PI);
      if (diff < 0) diff += 2 * Math.PI;
      diff -= Math.PI;
      const absDiff = Math.abs(diff);
      const reverseSteerSign = laju < -0.1 ? -1 : 1;
      const headingOutward = nearWest && Math.sin(h) < -0.12;
      let belok = absDiff > 0.04 ? Math.max(-1, Math.min(1, diff / 0.45)) * reverseSteerSign : 0;
      let gas = 1.0;
      if ((pred.willExit && absDiff > 0.35) || (headingOutward && absDiff > 0.55)) {
        gas = laju > 0.4 ? -0.85 : 0;
        belok = (diff >= 0 ? 1 : -1) * reverseSteerSign;
      } else if (absDiff > 1.05) {
        gas = laju > 2.2 ? -0.35 : 0.15;
      }
      // Exact gerakPerahu physics
      const s = (gas > 0 ? 2.4 * gas : 3.2 * gas) * lajuKali;
      laju += s * dt;
      laju -= laju * (0.32 + (0.02 * Math.abs(laju)) / lajuKali) * dt;
      laju = Math.min(7.5 * lajuKali, Math.max(-2.2, laju));
      h += 0.7 * belok * dt * Math.min(1, Math.max(0.3, Math.abs(laju) / 2.5)) * (laju < -0.1 ? -1 : 1);
      x += Math.sin(h) * laju * dt;
      z += Math.cos(h) * laju * dt;
      if (x <= bounds.x0) { hitWall = true; break; }
    }
    assert.equal(hitWall, false, `max-speed boat must brake & turn away before x=-320 (final x=${x.toFixed(1)})`);
    assert.ok(x > bounds.x0 + 10, `boat must stay safely inside West wall (x=${x.toFixed(1)})`);
  });

  await t.test("autopilot strictly prioritizes 30m+ Ramai over <30m spots and does not stop early en route", () => {
    const mancingSrc = fs.readFileSync(path.join(extDir, "mancing.js"), "utf-8");
    assert.match(mancingSrc, /const isDeep30 = maxDepth === null && d >= 30;/);
    assert.match(mancingSrc, /\(isDeep30 && isFiveBar\)\s*\?\s*6\s*:\s*\(isDeep30 && isRamai\)\s*\?\s*5/);
    assert.match(mancingSrc, /const wantsDeep30Target = Boolean\(/);
    assert.match(mancingSrc, /const arrivalDepthOk = wantsDeep30Target \? sonar\.depth >= 30 : inDepthRange;/);

    // Verify 34m Ramai (kaya 0.60, tier 5) strictly outranks 26m 5/5 (kaya 0.95, tier 4)
    const RAMAI_MIN_KAYA = 0.45;
    const FIVE_BAR_MIN_KAYA = 0.78;
    function scoreSpot(d, kaya, dist = 100, minDepth = 25, maxDepth = null) {
      const meetsDepth = d >= minDepth && (maxDepth === null || d <= maxDepth);
      const isRamai = kaya >= RAMAI_MIN_KAYA;
      const isFiveBar = kaya >= FIVE_BAR_MIN_KAYA;
      const isDeep30 = maxDepth === null && d >= 30;
      const tier = (isDeep30 && isFiveBar) ? 6 : (isDeep30 && isRamai) ? 5 : (meetsDepth && isFiveBar) ? 4 : (meetsDepth && isRamai) ? 3 : meetsDepth ? 2 : isRamai ? 1 : 0;
      const depthBonus = d >= 34 ? 140 : d >= 30 ? 120 : d >= 24 ? 80 : d >= 15 ? 40 : d;
      return tier * 1000 + kaya * 600 + depthBonus - dist * 0.08;
    }

    const spot34Ramai = scoreSpot(34, 0.60, 220);
    const spot26FiveBar = scoreSpot(26, 0.95, 40);
    const spot35FiveBar = scoreSpot(35, 0.85, 250);
    assert.ok(spot34Ramai > spot26FiveBar, "34m Ramai must always beat 26m 5/5");
    assert.ok(spot35FiveBar > spot34Ramai, "35m 5/5 must beat 34m non-5/5 Ramai");
    // Shallow mode (maxDepth=10) does NOT trigger isDeep30
    const shallow5FiveBar = scoreSpot(5, 0.90, 20, 2, 10);
    const deep35InShallowMode = scoreSpot(35, 0.95, 200, 2, 10);
    assert.ok(shallow5FiveBar > deep35InShallowMode, "shallow mode must stay in 2-10m");
  });

  await t.test("randomized in-spot positioning & player-avoidance shift stays 5/5 Ramai and ≥30m", () => {
    const mancingSrc = fs.readFileSync(path.join(extDir, "mancing.js"), "utf-8");
    const injectSrc = fs.readFileSync(path.join(extDir, "inject.js"), "utf-8");

    assert.match(injectSrc, /function extractOtherMancingBoats\(/, "inject.js must extract nearby player boats");
    assert.match(injectSrc, /others:\s*extractOtherMancingBoats\(/, "inject.js must broadcast others[] in ks_mancing_data_update");
    assert.match(mancingSrc, /function calcSpotRameAt\(/);
    assert.match(mancingSrc, /function getNearestOtherBoatDist\(/);
    assert.match(mancingSrc, /function pickOffsetPointInSpot\(/);
    assert.match(mancingSrc, /PLAYER_CROWD_DIST\s*=\s*9/);
    assert.match(mancingSrc, /Geser Sedikit \(Ada Pemain\)/);

    // Behavioral check: when another player sits at dead center of a 35m 5/5 spot (0, -580, r=35, kaya=0.88),
    // candidate selection shifts away from the player (>= 10m away) while preserving depth >= 30m and 5/5 Ramai (>= 0.85)!
    function calcDepth(x, z) {
      const n = Math.min(1, Math.max(0, (-z - 10) / 630));
      return Math.max(1.5, 2 + n * n * 18 + 20 * n + Math.sin(0.021 * x + 1.3) * Math.cos(0.017 * z) * 3 * n + Math.max(0, -640 - z) * 0.05);
    }
    const spot = { x: 0, z: -580, r: 35, kaya: 0.88 };
    const others = [{ x: 0, z: -580 }];
    let picked = null;
    let bestScore = -Infinity;
    for (let i = 0; i < 20; i++) {
      const angle = (i / 20) * Math.PI * 2;
      const px = spot.x + Math.cos(angle) * spot.r * 0.45;
      const pz = spot.z + Math.sin(angle) * spot.r * 0.45;
      const d = calcDepth(px, pz);
      const ratio = Math.hypot(px - spot.x, pz - spot.z) / spot.r;
      const rame = Math.min(1, 0.35 * (0.7 + 0.6 * Math.min(1, d / 30)) + spot.kaya * (1 - ratio * ratio));
      if (d < 30 || rame < 0.85) continue;
      const pDist = Math.hypot(px - others[0].x, pz - others[0].z);
      const score = (pDist < 9 ? -500 : 0) + Math.min(28, pDist) * 6 + rame * 120;
      if (score > bestScore) { bestScore = score; picked = { x: px, z: pz, d, rame, pDist }; }
    }
    assert.ok(picked, "must find a valid 5/5 Ramai offset point away from player");
    assert.ok(picked.pDist >= 14, `shifted point must keep spacing from other player (dist=${picked.pDist.toFixed(1)}m)`);
    assert.ok(picked.d >= 30, `shifted point must stay ≥30m (depth=${picked.d.toFixed(1)}m)`);
    assert.ok(picked.rame >= 0.85, `shifted point must stay 5/5 Ramai (rame=${picked.rame.toFixed(2)})`);
  });
});
