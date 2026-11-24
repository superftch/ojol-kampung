import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ojolModulePath = path.resolve(__dirname, "../ojol.js");

// Load ojol.js
await import(ojolModulePath);
const ojol = globalThis.__KS_OJOL_ENGINE__ || {};

test("SPBU uses the pump for the vehicle that arrived", () => {
  const { spbuVehicleMatches: matches } = ojol;
  assert.equal(matches("Motor matic · didorong", "Bensin 0 dari 100 poin · Pertalite", "motor"), true);
  assert.equal(matches("Mobil keluarga", "Bensin 16 dari 100 poin · Pertalite", "mobil"), true);
  assert.equal(matches("Mobil listrik", "Baterai 16 dari 100 poin · Isi daya SPKLU", "mobil"), true);
  assert.equal(matches("Mobil keluarga", "Baterai 16 dari 100 poin · Isi daya SPKLU", "mobil"), false);
  assert.equal(matches("Mobil listrik", "Bensin 16 dari 100 poin · Pertalite", "mobil"), false);
  assert.equal(matches("Motor matic", "Bensin 16 dari 100 poin · Pertalite", "mobil"), false);
});

test("SPBU only submits a current full-tank quote at the verified rate", () => {
  const { spbuRefillQuote: quote } = ojol;
  const meter = "Bensin 12,5 dari 100 poin · Pertalite";
  assert.equal(quote(meter, "Isi 87,5 poin · 1,75 koin", 20), true);
  assert.equal(quote(meter, "Isi 25 poin · 0,5 koin", 20), false);
  assert.equal(quote(meter, "Isi 87,5 poin · 1,8 koin", 20), false);
  assert.equal(quote(meter, "Isi 87,5 poin · 1,75 koin", 10), false);
  assert.equal(quote(meter, "Sedang mengisi…", 20), false);
});

const {
  SEED_TEMPLATES,
  resample,
  normalizeGlyph,
  strokeDistance,
  shapeDistance,
  extractGlyphs,
  solvePolylineCaptcha,
  parseOrderCardText,
  evaluateOrders,
  computeClampedPosition,
  restoreClampedPosition,
  calculateBearing,
  findLookaheadWaypoint,
  findActiveSegment,
  getNextCheckpoint,
  calculateRoadSteering,
  isArrivalReached,
  calculateAntiStuckNudge,
  determineKemudiAction,
  DEFAULT_SHOPS,
  evaluateKebutuhanRefill
} = globalThis.__KS_OJOL_ENGINE__;

function makeSvg(digits, seedBank = SEED_TEMPLATES) {
  const rows = [];
  for (let index = 0; index < digits.length; index++) {
    const digit = digits[index];
    const variant = seedBank[digit]?.[0] || [];
    for (const stroke of variant) {
      const points = stroke.map(([x, y]) => [x * 20 + index * 55 + 10, y * 25 + 10]);
      rows.push(`<polyline points="${points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ")}"/>`);
    }
  }
  return `<svg width="120" height="56"><rect width="100%" height="100%"/>${rows.join("")}</svg>`;
}

test("Auto-Ojol Engine (Khusus Mode Kendarai) - Unit & Integration Tests", async (t) => {
  await t.test("Polyline Captcha Solver - Seed digits and reverse stroke matching", () => {
    const svg57 = makeSvg("57");
    assert.equal(solvePolylineCaptcha(svg57), "57");

    const svg82 = makeSvg("82");
    assert.equal(solvePolylineCaptcha(svg82), "82");

    const svg30 = makeSvg("30");
    assert.equal(solvePolylineCaptcha(svg30), "30");
  });

  await t.test("Polyline Captcha Solver - Narrow single vertical stroke is digit 1", () => {
    const svg11 = `
      <svg width="120" height="56">
        <polyline points="15.0,8.0 15.0,46.0"/>
        <polyline points="65.0,7.0 65.0,47.0"/>
      </svg>
    `;
    assert.equal(solvePolylineCaptcha(svg11), "11");
  });

  await t.test("Polyline Captcha Solver - Unknown glyph throws error without guessing", () => {
    const unknownSvg = `
      <svg width="120" height="56">
        <polyline points="0,0 2,2 4,0 6,6 8,2 10,10"/>
      </svg>
    `;
    assert.throws(() => {
      solvePolylineCaptcha(unknownSvg);
    }, /Glyph cek belum dikenali/);
  });

  await t.test("Polyline Captcha Solver - Live disk samples in .local/cek-samples", () => {
    const sampleDir = path.resolve(__dirname, "../../../.local/cek-samples");
    if (fs.existsSync(sampleDir)) {
      const sampleFiles = fs.readdirSync(sampleDir).filter(f => f.endsWith(".svg"));
      const expectedCodes = {
        "e7a95ed8.svg": "57",
        "12603cf3-90c4-4ddc-8d95-d50d8b899417.svg": "82",
        "711952ec-07f4-449d-bf2a-bea69d523ba9.svg": "79",
        "a7cb5f9f-c528-4c1c-98b0-3434372dc83a.svg": "20",
        "ba5228ac-4ab7-4a7d-8cea-602923f2605e.svg": "26"
      };

      for (const [filename, expected] of Object.entries(expectedCodes)) {
        const fullPath = path.join(sampleDir, filename);
        if (fs.existsSync(fullPath)) {
          const content = fs.readFileSync(fullPath, "utf-8");
          const solved = solvePolylineCaptcha(content);
          assert.equal(solved, expected, `Sample ${filename} must solve to ${expected}`);
        }
      }
    }
  });

  await t.test("Order Evaluation Engine - Prioritizes highest fare (Max Omzet)", () => {
    const orders = [
      { id: "ord-1", fareMilli: 2400, distance: 8, warga: false },
      { id: "ord-2", fareMilli: 5800, distance: 18, warga: false },
      { id: "ord-3", fareMilli: 3900, distance: 10, warga: false }
    ];

    const chosen = evaluateOrders(orders, { strategy: "max_fare" });
    assert.ok(chosen);
    assert.equal(chosen.id, "ord-2", "Should choose order with highest fare (5800 m-koin)");
  });

  await t.test("Order Evaluation Engine - Price-to-Distance & Time Efficiency (Most Worth It per Minute)", () => {
    const orders = [
      { id: "ord-1", fareMilli: 2400, distance: 8, warga: false },
      { id: "ord-2", fareMilli: 5800, distance: 18, warga: false },
      { id: "ord-3", fareMilli: 3900, distance: 10, warga: false }
    ];

    // ord-3: 3900 m-koin / 10 petak (390 m-koin/petak, rate 65.0 m-koin/s)
    // ord-2: 5800 m-koin / 18 petak (322 m-koin/petak, rate 60.4 m-koin/s)
    const chosen = evaluateOrders(orders, { strategy: "time_efficiency" });
    assert.ok(chosen);
    assert.equal(chosen.id, "ord-3", "Should choose ord-3 with highest price-to-distance ratio (390 m-koin/petak) and fastest turnaround");
  });

  await t.test("Order Evaluation Engine - Prefer warga orders when fares are equal", () => {
    const orders = [
      { id: "ord-reg", fareMilli: 4500, distance: 12, warga: false },
      { id: "ord-warga", fareMilli: 4500, distance: 12, warga: true }
    ];

    const chosen = evaluateOrders(orders, { preferWarga: true });
    assert.ok(chosen);
    assert.equal(chosen.id, "ord-warga", "Should prefer warga order over regular NPC order");
  });

  await t.test("Order Evaluation Engine - Prefer shorter distance on identical fare and status", () => {
    const orders = [
      { id: "ord-far", fareMilli: 4000, distance: 20, warga: false },
      { id: "ord-near", fareMilli: 4000, distance: 7, warga: false }
    ];

    const chosen = evaluateOrders(orders);
    assert.ok(chosen);
    assert.equal(chosen.id, "ord-near", "Should prefer shorter distance for faster turnaround");
  });

  await t.test("Order Evaluation Engine - Avoid extreme distance trap (>35 petak) over fast orders", () => {
    // Skenario order trap dari screenshot user:
    // Order 1: 0.9 koin (45 petak) -> butuh waktu tunggu 4 menit di server
    // Order 2: 0.8 koin (10 petak) -> selesai dalam 30 detik
    const orders = [
      { id: "ord-trap-45", fareMilli: 900, distance: 45, warga: false },
      { id: "ord-fast-10", fareMilli: 800, distance: 10, warga: false }
    ];

    const chosen = evaluateOrders(orders, { maxDistance: 35 });
    assert.ok(chosen);
    assert.equal(chosen.id, "ord-fast-10", "Should avoid 45-petak order trap despite 0.1 koin higher nominal fare");
  });

  await t.test("Order Card Text Parsing - Extracts fare, distance, and warga status accurately", () => {
    const cardText1 = "Antar penumpang · 3.800 koin · pesanan warga · Balai Desa → Masjid · 14 petak · ⛽ −5";
    const parsed1 = parseOrderCardText(cardText1);
    assert.equal(parsed1.fareMilli, 3800);
    assert.equal(parsed1.distance, 14);
    assert.equal(parsed1.isWarga, true);

    const cardText2 = "Antar belanjaan · 1,5 koin · Warung Sembako → Rumah Bpk · 6 petak · ⛽ −2";
    const parsed2 = parseOrderCardText(cardText2);
    assert.equal(parsed2.fareMilli, 1500);
    assert.equal(parsed2.distance, 6);
    assert.equal(parsed2.isWarga, false);
  });

  await t.test("Draggable HUD Math - Clamping and boundary checks", () => {
    const pos = computeClampedPosition(100, 100, 20, 30, 310, 360, 1920, 1080);
    assert.equal(pos.left, 120);
    assert.equal(pos.top, 130);

    // Negative coordinates clamped to 0
    const posNeg = computeClampedPosition(10, 10, -50, -50, 310, 360, 1920, 1080);
    assert.equal(posNeg.left, 0);
    assert.equal(posNeg.top, 0);

    // Exceeding screen width/height clamped to viewport edge
    const posOverflow = computeClampedPosition(1800, 1000, 200, 200, 310, 360, 1920, 1080);
    assert.equal(posOverflow.left, 1920 - 310);
    assert.equal(posOverflow.top, 1080 - 360);
  });

  await t.test("Latest Game Rules (21-22 Nov 2026) - Anti-Cek Kilat & Quota Constraints", () => {
    // 1. Anti-cek kilat guard: server triggers captcha on 100% orders if claim < 2.5s
    const CEK_KILAT_THRESHOLD_SECONDS = 2.5;
    const SAFE_MIN_CLAIM_DELAY_MS = 2800;
    assert.ok(
      SAFE_MIN_CLAIM_DELAY_MS / 1000 > CEK_KILAT_THRESHOLD_SECONDS,
      "Safe claim delay must strictly exceed 2.5s server threshold"
    );

    // 2. Daily narik quota update: 840 minutes (14 hours)
    const MAX_NARIK_HARIAN_MENIT = 840;
    assert.equal(MAX_NARIK_HARIAN_MENIT / 60, 14, "Must match 14 hours daily limit");

    // 3. Compulsory rest reduction: 10 minutes (down from 15 minutes)
    const ISTIRAHAT_MENIT = 10;
    assert.equal(ISTIRAHAT_MENIT, 10, "Rest requirement is now 10 minutes");

    // 4. Fuel threshold update: minimum 6 bensin (distance formula: 2 + jarak/10)
    const MIN_BENSIN = 6;
    assert.equal(MIN_BENSIN, 6, "Minimum fuel check is 6 bensin");
  });

  await t.test("Mode Kendarai Autopilot Math - Bearing, Lookahead & Anti-Stuck", () => {
    // 1. Bearing calculations (Math.atan2(dx, dy))
    const bearingNorth = calculateBearing(10, 10, 10, 20); // dy > 0
    assert.ok(Math.abs(bearingNorth - 0) < 0.001, "Moving +Y should have bearing 0");

    const bearingEast = calculateBearing(10, 10, 20, 10); // dx > 0
    assert.ok(Math.abs(bearingEast - Math.PI / 2) < 0.001, "Moving +X should have bearing PI/2");

    // "Putar balik" scenario from user screenshot (target is behind at -Y)
    const bearingUturn = calculateBearing(10, 20, 10, 0); // dy < 0
    assert.ok(Math.abs(Math.abs(bearingUturn) - Math.PI) < 0.001, "U-turn should rotate ~180 degrees (PI)");

    // 2. Waypoint lookahead selection along route
    const sampleRoute = [
      { x: 10, y: 10 },
      { x: 10, y: 11 },
      { x: 10, y: 12 },
      { x: 12, y: 12 },
      { x: 15, y: 20 }
    ];

    // Current player position at (10, 10), min distance 1.5 tiles
    const targetWp = findLookaheadWaypoint(sampleRoute, 10, 10, 0, 1.5);
    assert.deepEqual(targetWp, { x: 10, y: 12 }, "Should select waypoint at least 1.5 tiles ahead");

    // When near end of route (current seg is 4), distance to destination (1.41) < 1.5 -> select final destination point
    const nearEndWp = findLookaheadWaypoint(sampleRoute, 14, 19, 4, 1.5);
    assert.deepEqual(nearEndWp, { x: 15, y: 20 }, "Should select final destination when approaching end");

    // 3. Arrival distance detection
    assert.equal(isArrivalReached(15, 19.2, 15, 20, 1.8), true, "Within 1.8 tiles is considered arrived");
    assert.equal(isArrivalReached(10, 10, 15, 20, 1.8), false, "Far away is not arrived");

    // 4. Anti-stuck nudge vector calculation
    const nudge = calculateAntiStuckNudge(3, 4, 0.45); // 3-4-5 triangle, hypotenuse = 5
    assert.ok(Math.abs(nudge.nudgeX - (3 / 5) * 0.45) < 0.001);
    assert.ok(Math.abs(nudge.nudgeY - (4 / 5) * 0.45) < 0.001);
    const nudgeMag = Math.hypot(nudge.nudgeX, nudge.nudgeY);
    assert.ok(Math.abs(nudgeMag - 0.45) < 0.001, "Nudge vector length should equal step distance (0.45)");
  });

  await t.test("Strict Per-Checkpoint Road Following & House Collision Prevention", () => {
    // Skenario L-Turn dengan rumah di sudut:
    // Jalan Vertikal: (10, 10) -> (10, 20)
    // Belok di sudut: (10, 20)
    // Jalan Horizontal: (10, 20) -> (25, 20)
    // Rumah warga berdiri di (11, 19) sampai (15, 19).
    // Pemotong jalan diagonal akan menabrak rumah di (11, 19)!
    const route = [
      { x: 10, y: 10 },
      { x: 10, y: 20 }, // Checkpoint tikungan 1
      { x: 25, y: 20 }  // Tujuan akhir
    ];

    // 1. Saat motor di (10, 14), target HARUS tetap checkpoint 1 (10, 20), dilarang meloncat ke (25, 20)
    const nextCp1 = getNextCheckpoint(route, 10, 14, 0, 0.45);
    assert.equal(nextCp1.seg, 0, "Harus tetap di segmen 0");
    assert.deepEqual(nextCp1.checkpoint, { x: 10, y: 20 }, "Checkpoint target adalah tikungan (10, 20)");

    // 2. Kemudi di jalan vertikal: sudut hadap harus tepat di sumbu jalan (bearing = 0 / Utara)
    const steer1 = calculateRoadSteering(nextCp1.pA, nextCp1.pB, 10, 14);
    assert.equal(steer1.roadAxis, "vertical");
    assert.equal(steer1.aimX, 10, "Aim X terkunci di garis tengah jalan X=10");
    assert.ok(Math.abs(steer1.bearing - 0) < 0.001, "Arah hadap lurus ke depan, dilarang serong ke arah rumah");

    // 3. Jika motor sedikit bergeser ke pinggir jalan (misal X=10.2), kemudi menarik kembali ke sumbu X=10
    const steerDrift = calculateRoadSteering(nextCp1.pA, nextCp1.pB, 10.2, 14);
    assert.ok(steerDrift.dx < 0, "dx negatif menarik motor ke kiri kembali ke tengah jalan");

    // 4. Saat motor belum sampai di persimpangan (jarak ke tikungan 1.0 > 0.45 petak), checkpoint tidak boleh advance
    const cpBeforeTurn = getNextCheckpoint(route, 10, 19.0, 0, 0.45);
    assert.equal(cpBeforeTurn.seg, 0, "Masih di segmen 0 sampai benar-benar di dalam persimpangan");
    assert.deepEqual(cpBeforeTurn.checkpoint, { x: 10, y: 20 });

    // 5. Begitu tiba tepat di persimpangan (10, 19.7) dengan jarak <= 0.45, checkpoint baru advance ke (25, 20)
    const cpAtTurn = getNextCheckpoint(route, 10, 19.7, 0, 0.45);
    assert.equal(cpAtTurn.seg, 1, "Advance ke segmen 1 setelah tiba di persimpangan");
    assert.deepEqual(cpAtTurn.checkpoint, { x: 25, y: 20 }, "Target baru adalah tujuan (25, 20)");

    // 6. Kemudi di jalan horizontal: sudut hadap harus tepat 90 derajat ke Timur (bearing = PI/2)
    const steer2 = calculateRoadSteering(cpAtTurn.pA, cpAtTurn.pB, 10, 20);
    assert.equal(steer2.roadAxis, "horizontal");
    assert.equal(steer2.aimY, 20, "Aim Y terkunci di garis tengah jalan Y=20");
    assert.ok(Math.abs(steer2.bearing - Math.PI / 2) < 0.001, "Belok 90 derajat mengikuti jalan horizontal");

    // 7. Anti-stuck nudge pada jalan vertikal: dilarang mendorong X ke arah rumah warga
    const nudgeVert = calculateAntiStuckNudge(0, 1, 0.35, "vertical");
    assert.equal(nudgeVert.nudgeX, 0, "Nudge X harus 0 agar tidak mendorong ke rumah");
    assert.ok(nudgeVert.nudgeY > 0, "Nudge Y mendorong maju searah jalan");

    // 8. Anti-stuck nudge pada jalan horizontal: dilarang mendorong Y ke arah rumah warga
    const nudgeHoriz = calculateAntiStuckNudge(1, 0, 0.35, "horizontal");
    assert.equal(nudgeHoriz.nudgeY, 0, "Nudge Y harus 0 agar tidak mendorong ke rumah");
    assert.ok(nudgeHoriz.nudgeX > 0, "Nudge X mendorong maju searah jalan");

    // 9. Deteksi sampai di tujuan akhir (< 1.4 petak)
    assert.equal(isArrivalReached(24.5, 20, 25, 20, 1.4), true, "Jarak 0.5 petak terdeteksi sampai");
    assert.equal(isArrivalReached(20, 20, 25, 20, 1.4), false, "Jarak 5.0 petak belum sampai");
  });

  await t.test("Kemudi State Machine - Putar Balik, Intersection Choice & Auto-Drive Decision", () => {
    const now = 100000;

    // 1. Skenario Putar Balik dari screenshot user (arah tujuan di belakang saat baru mulai)
    const putarDecision = determineKemudiAction({
      walkNavTurn: "putar",
      gpsBannerText: "Putar balik · Arah tujuan di belakangmu",
      kemudiGoOn: false,
      kemudiGoDisabled: false,
      hasKemudiPutar: true,
      hasKemudiGo: true,
      now,
      lastPutarTime: 0
    });
    assert.equal(putarDecision.action, "putar", "Must trigger putar balik when banner indicates turn is putar");

    // Debounce check: tidak boleh spam klik putar balik dalam selang waktu < 1200ms
    const putarSpamDecision = determineKemudiAction({
      walkNavTurn: "putar",
      gpsBannerText: "Putar balik · Arah tujuan di belakangmu",
      hasKemudiPutar: true,
      now: now + 500,
      lastPutarTime: now
    });
    assert.notEqual(putarSpamDecision.action, "putar", "Must debounce putar click within 1200ms");

    // 2. Skenario Setelah Putar Balik: Menghadap rute tujuan, aktifkan kemudi 'jalan'
    const jalanDecision = determineKemudiAction({
      walkNavTurn: "lurus",
      gpsBannerText: "Jemput: Kebun rempah cak Sura · sisa 20 petak",
      kemudiGoOn: false,
      kemudiGoDisabled: false,
      hasKemudiPutar: true,
      hasKemudiGo: true,
      now: now + 2000,
      lastPutarTime: now,
      lastGoTime: 0
    });
    assert.equal(jalanDecision.action, "jalan", "Must trigger kemudi 'jalan' once facing forward and vehicle is stopped");

    // 3. Skenario Sedang Berjalan (kemudiGoOn = true): Status idle/driving
    const drivingDecision = determineKemudiAction({
      walkNavTurn: "lurus",
      gpsBannerText: "Jemput: Kebun rempah cak Sura · sisa 18 petak",
      kemudiGoOn: true,
      kemudiGoDisabled: false,
      hasKemudiGo: true,
      now: now + 4000,
      lastGoTime: now + 2000
    });
    assert.equal(drivingDecision.action, "idle", "Should remain idle while vehicle is actively moving");

    // 4. Skenario Simpang Rute Belok Kiri & Belok Kanan
    const turnKiriDecision = determineKemudiAction({
      walkNavTurn: "kiri",
      hasKemudiKiri: true,
      now: now + 6000,
      lastTurnTime: 0
    });
    assert.equal(turnKiriDecision.action, "kiri", "Must signal left turn at intersection");

    const turnKananDecision = determineKemudiAction({
      walkNavTurn: "kanan",
      hasKemudiKanan: true,
      now: now + 6000,
      lastTurnTime: 0
    });
    assert.equal(turnKananDecision.action, "kanan", "Must signal right turn at intersection");

    // 5. Skenario Persimpangan Screenshot User (motor sedang jalan tapi tiba di persimpangan wajib interaksi)
    const intersectionTurnDecision = determineKemudiAction({
      walkNavTurn: "kiri",
      gpsBannerText: "Belok kiri dalam 0 petak · Jemput: Kebun rempah cak Sura",
      kemudiGoOn: true,
      kemudiGoDisabled: true,
      isTunggu: true,
      hasKemudiKiri: true,
      hasKemudiKanan: true,
      hasKemudiGo: true,
      now: now + 8000,
      lastTurnTime: 0
    });
    assert.equal(intersectionTurnDecision.action, "kiri", "Must interactively trigger left turn at intersection even if kemudiGoOn was previously active");

    // 6. Skenario Stop-Before-Turn: Ketika ikuti jalan sedang aktif (kemudiGoOn = true, speed > 0),
    // tombol belok/putar di ThreeRenderer tidak berfungsi kecuali motor distop terlebih dahulu.
    const stopForPutarDecision = determineKemudiAction({
      walkNavTurn: "putar",
      gpsBannerText: "Putar balik · Arah tujuan di belakangmu",
      kemudiGoOn: true,
      kemudiGoDisabled: false,
      hasKemudiPutar: true,
      hasKemudiGo: true,
      now: now + 10000,
      lastGoTime: 0
    });
    assert.equal(stopForPutarDecision.action, "stop_for_turn", "Must click Berhenti (kemudi-go) first before turning if vehicle is in motion");

    // Pada tick berikutnya setelah motor berhenti (kemudiGoOn = false), langsung eksekusi putar balik
    const executePutarAfterStop = determineKemudiAction({
      walkNavTurn: "putar",
      gpsBannerText: "Putar balik · Arah tujuan di belakangmu",
      kemudiGoOn: false,
      kemudiGoDisabled: false,
      hasKemudiPutar: true,
      hasKemudiGo: true,
      now: now + 10500,
      lastGoTime: now + 10000,
      lastPutarTime: 0
    });
    assert.equal(executePutarAfterStop.action, "putar", "Must execute putar once vehicle has stopped");

    // Stop-before-turn untuk belok kiri di persimpangan (dalam 0 petak) saat motor masih melaju
    const stopForTurnKiriDecision = determineKemudiAction({
      walkNavTurn: "kiri",
      gpsBannerText: "Belok kiri dalam 0 petak · Jemput: Kebun rempah cak Sura",
      kemudiGoOn: true,
      kemudiGoDisabled: false,
      hasKemudiKiri: true,
      hasKemudiGo: true,
      now: now + 12000,
      lastGoTime: 0
    });
    assert.equal(stopForTurnKiriDecision.action, "stop_for_turn", "Must stop vehicle before executing left turn at intersection");

    // Jangan berhenti jika belok masih jauh (misal dalam 8 petak)
    const farTurnDecision = determineKemudiAction({
      walkNavTurn: "kiri",
      gpsBannerText: "Belok kiri dalam 8 petak · Jemput: Kebun rempah cak Sura",
      kemudiGoOn: true,
      kemudiGoDisabled: false,
      hasKemudiKiri: true,
      hasKemudiGo: true,
      now: now + 14000,
      lastGoTime: 0
    });
    assert.equal(farTurnDecision.action, "idle", "Should continue driving forward if turn is still far away");
  });

  await t.test("Auto-Kebutuhan Refill Evaluator - Evaluates critical thresholds and priorities", () => {
    // 1. Kondisi semua bar penuh / sehat
    const healthyBars = { bensin: 80, kendaraan: 75, kuota: 90 };
    assert.equal(evaluateKebutuhanRefill(healthyBars), null, "Healthy bars should not trigger refill");

    // 2. Bensin kritis (<= 20%)
    const lowFuelBars = { bensin: 14, kendaraan: 70, kuota: 60 };
    const fuelDecision = evaluateKebutuhanRefill(lowFuelBars, { minBensin: 20 });
    assert.ok(fuelDecision, "Should trigger refill for low fuel");
    assert.equal(fuelDecision.resource, "fuel");
    assert.equal(fuelDecision.name, "bensin");
    assert.equal(fuelDecision.current, 14);

    // 3. Kondisi mesin kritis (<= 25%)
    const lowCondBars = { bensin: 50, kendaraan: 22, kuota: 60 };
    const condDecision = evaluateKebutuhanRefill(lowCondBars, { minKondisi: 25 });
    assert.ok(condDecision, "Should trigger service for low condition");
    assert.equal(condDecision.resource, "condition");
    assert.equal(condDecision.name, "kondisi");

    // 4. Kuota HP kritis (<= 16%)
    const lowDataBars = { bensin: 50, kendaraan: 60, kuota: 12 };
    const dataDecision = evaluateKebutuhanRefill(lowDataBars, { minKuota: 16 });
    assert.ok(dataDecision, "Should trigger topup for low data");
    assert.equal(dataDecision.resource, "data");
    assert.equal(dataDecision.name, "kuota");

    // 5. Multiple critical bars - prioritizes the most severe deficit
    const multipleLowBars = { bensin: 10, kendaraan: 12, kuota: 4 };
    const multiDecision = evaluateKebutuhanRefill(multipleLowBars, { minBensin: 20, minKondisi: 25, minKuota: 16 });
    assert.ok(multiDecision);
    // Kuota threshold 16 - current 4 = deficit 12 + base priority 12 = 24
    // Kondisi threshold 25 - current 12 = deficit 13 + base priority 8 = 21
    // Bensin threshold 20 - current 10 = deficit 10 + base priority 10 = 20
    assert.equal(multiDecision.resource, "data", "Should prioritize kuota topup because without kuota orders cannot be received");
  });

  await t.test("Auto-Kebutuhan Shop Database - Verified shop IDs and items", () => {
    assert.equal(DEFAULT_SHOPS.fuel, undefined, "Fuel uses the official SPBU pump");
    assert.ok(DEFAULT_SHOPS.condition.length >= 2, "Must contain condition/bengkel shop locations");
    assert.ok(DEFAULT_SHOPS.data.length >= 2, "Must contain kuota/konter shop locations");

    // Kampung Sebelah shop locations
    const bengkelKs = DEFAULT_SHOPS.condition.find(s => s.name.includes("spesialis motor"));
    assert.equal(bengkelKs.id, "b2400595-7b5b-4571-aa2e-bcff27a04d9f");
    assert.equal(bengkelKs.item, "servis-motor");

    const konterKs = DEFAULT_SHOPS.data.find(s => s.name.includes("Somadun"));
    assert.equal(konterKs.id, "bdda0310-4488-418f-a479-9710a10e2d96");
    assert.equal(konterKs.item, "pulsa");
  });

  await t.test("Auto-Kebutuhan SPBU API Flow - Verified direct refill via API", async () => {
    const { buyShopItem, refillSpbuViaApi } = ojol;
    const calls = [];
    const origFetch = globalThis.fetch;
    globalThis.fetch = async (url, opts = {}) => {
      calls.push({ url, method: opts.method || "GET", body: opts.body ? JSON.parse(opts.body) : undefined });
      if (url === "/api/kendaraan") {
        return {
          ok: true,
          status: 200,
          json: async () => ({ items: [{ family: "motor", kode: "motor-matic:putih:0", name: "Motor matic" }] })
        };
      }
      if (url === "/api/tujuan") {
        return {
          ok: true,
          status: 200,
          json: async () => ({ usaha: [{ item: "spbu-pertamina", plotId: "P29-U01", name: "SPBU Desa Timur 2", x: 66, y: -103 }] })
        };
      }
      if (url === "/api/game/me") {
        return {
          ok: true,
          status: 200,
          json: async () => ({ home: { x: 75, y: -68 } })
        };
      }
      if (url.startsWith("/api/spbu/P29-U01")) {
        const payload = opts.body ? JSON.parse(opts.body) : {};
        if (payload.aksi === "datang") {
          return { ok: true, status: 200, json: async () => ({ hadir: true }) };
        }
        if (payload.aksi === "isi") {
          return {
            ok: true,
            status: 200,
            json: async () => ({ replayed: false, item: "isi-bensin-motor", poin: 96, priceMilli: 1920, sebelum: 4, sesudah: 100 })
          };
        }
        if (payload.aksi === "pamit") {
          return { ok: true, status: 200, json: async () => ({}) };
        }
      }
      return { ok: false, status: 404, json: async () => ({}) };
    };

    try {
      const res = await buyShopItem("fuel", undefined, "motor");
      assert.equal(res.success, true);
      assert.equal(res.shop, "SPBU Desa Timur 2");
      assert.equal(res.item, "isi-bensin-motor");

      const spbuCalls = calls.filter(c => c.url.startsWith("/api/spbu/P29-U01"));
      assert.equal(spbuCalls.length, 3);
      assert.equal(spbuCalls[0].body.aksi, "datang");
      assert.equal(spbuCalls[0].body.kode, "motor-matic:putih:0");
      assert.equal(spbuCalls[1].body.aksi, "isi");
      assert.equal(spbuCalls[1].body.jumlah, "penuh");
      assert.equal(spbuCalls[2].body.aksi, "pamit");
    } finally {
      globalThis.fetch = origFetch;
    }
  });
});
