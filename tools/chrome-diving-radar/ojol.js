// KampungSebelah - Auto-Ojol Pro Content Script (v2.1.0)
// Khusus Mode Kendarai: Pemilihan Order Tarif Tertinggi (Max Omzet), Tanpa Batas 12 Jam,
// Auto-Solver SVG Captcha (2-Digit Instan), Proteksi 409 Penumpang Turun, & Full Loop Otomatis

(function (root, factory) {
  const exportsObj = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = exportsObj;
  }
  if (root) {
    root.__KS_OJOL_ENGINE__ = exportsObj;
  }
})(typeof globalThis !== "undefined" ? globalThis : (typeof window !== "undefined" ? window : this), function () {
  console.log("[AutoOjol] Content script v2.1.0 loaded - Mode Kendarai Engine ready");

  // Template bank bawaan untuk solver captcha polyline 2 angka
  const SEED_TEMPLATES = {
    "8": [
      [
        [[0.053, 0.0], [0.898, 0.056], [1.0, 1.0], [0.079, 0.98], [0.0, 0.01]],
        [[0.0, 0.0], [0.078, 1.0], [1.0, 0.931], [0.944, 0.005]]
      ]
    ],
    "0": [[[[0.05, 0.0], [0.94, 0.003], [1.0, 0.945], [0.14, 1.0], [0.0, 0.003]]]],
    "5": [[[[0.91, 0.03], [0.0, 0.0], [0.05, 0.41], [0.95, 0.45], [1.0, 0.96], [0.07, 1.0]]]],
    "3": [[[[0.0, 0.0], [0.93, 0.01], [0.39, 0.47], [1.0, 0.58], [0.93, 1.0], [0.0, 0.97]]]],
    "2": [[[[0.0, 0.16], [0.25, 0.0], [0.89, 0.05], [0.91, 0.50], [0.09, 1.0], [1.0, 0.99]]]],
    "6": [[[[1.0, 0.0], [0.05, 0.4], [0.0, 1.0], [1.0, 1.0], [1.0, 0.48], [0.05, 0.49]]]],
    "7": [[[[0.0, 0.0], [1.0, 0.01], [0.22, 1.0]]]],
    "9": [
      [[[1.0, 0.62], [0.35, 0.63], [0.33, 0.16], [1.0, 0.13], [0.93, 0.63], [0.0, 1.0]]],
      [[[90.4, 26.7], [70.5, 26.8], [69.8, 12.2], [92.2, 11.3], [89.7, 29.0], [68.8, 41.6]]]
    ]
  };

  // ==========================================
  // 1. CAPTCHA SOLVER MODULE (SVG & Polyline)
  // ==========================================

  function resample(points, count = 24) {
    if (points.length < 2) {
      const out = [];
      for (let i = 0; i < count; i++) {
        out.push(points[0] ? [points[0][0], points[0][1]] : [0, 0]);
      }
      return out;
    }
    const lengths = [0.0];
    for (let i = 0; i < points.length - 1; i++) {
      const [x1, y1] = points[i];
      const [x2, y2] = points[i + 1];
      lengths.push(lengths[lengths.length - 1] + Math.hypot(x2 - x1, y2 - y1));
    }
    const total = lengths[lengths.length - 1] || 1.0;
    const out = [];
    for (let step = 0; step < count; step++) {
      const target = (total * step) / (count - 1);
      let index = 0;
      for (let i = 0; i < lengths.length; i++) {
        if (lengths[i] >= target) {
          index = i;
          break;
        }
      }
      index = Math.max(0, Math.min(points.length - 2, index));
      const span = lengths[index + 1] - lengths[index] || 1.0;
      const ratio = Math.min(1.0, Math.max(0.0, (target - lengths[index]) / span));
      const [x1, y1] = points[index];
      const [x2, y2] = points[index + 1];
      out.push([x1 + (x2 - x1) * ratio, y1 + (y2 - y1) * ratio]);
    }
    return out;
  }

  function normalizeGlyph(glyph) {
    const xs = [];
    const ys = [];
    for (const stroke of glyph) {
      for (const [x, y] of stroke) {
        xs.push(x);
        ys.push(y);
      }
    }
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const width = maxX - minX || 1.0;
    const height = maxY - minY || 1.0;
    return glyph.map(stroke =>
      resample(stroke.map(([x, y]) => [(x - minX) / width, (y - minY) / height]))
    );
  }

  function strokeDistance(a, b) {
    const count = a.length;
    if (b.length !== count) return 1.0;
    let best = 1.0;
    for (let shift = 0; shift < count; shift++) {
      const shifted = b.slice(shift).concat(b.slice(0, shift));
      let sum = 0;
      for (let i = 0; i < count; i++) {
        sum += Math.hypot(a[i][0] - shifted[i][0], a[i][1] - shifted[i][1]);
      }
      const cost = sum / count;
      if (cost < best) best = cost;
    }
    return best;
  }

  function shapeDistance(a, b) {
    if (a.length !== b.length) return 1.0;
    const remaining = b.slice();
    let total = 0.0;
    for (const stroke of a) {
      let minCost = Infinity;
      let minIdx = -1;
      for (let i = 0; i < remaining.length; i++) {
        const other = remaining[i];
        const cost = Math.min(strokeDistance(stroke, other), strokeDistance(other, stroke));
        if (cost < minCost) {
          minCost = cost;
          minIdx = i;
        }
      }
      total += minCost / 2;
      remaining.splice(minIdx, 1);
    }
    return total / a.length;
  }

  function extractGlyphs(svgText) {
    const polyMatches = [];
    const regex = /<polyline[^>]*points="([^"]+)"/g;
    let match;
    while ((match = regex.exec(svgText)) !== null) {
      const rawPts = match[1].trim().split(/\s+/);
      const pts = [];
      for (const p of rawPts) {
        const [x, y] = p.split(",").map(Number);
        if (!isNaN(x) && !isNaN(y)) {
          pts.push([x, y]);
        }
      }
      if (pts.length > 0) {
        polyMatches.push(pts);
      }
    }
    if (polyMatches.length === 0) {
      throw new Error("SVG cek tidak berisi polyline digit");
    }

    polyMatches.sort((a, b) => {
      const minA = Math.min(...a.map(p => p[0]));
      const minB = Math.min(...b.map(p => p[0]));
      return minA - minB;
    });

    const glyphs = [];
    for (const pts of polyMatches) {
      const left = Math.min(...pts.map(p => p[0]));
      if (glyphs.length > 0) {
        const lastGlyph = glyphs[glyphs.length - 1];
        const maxLastX = Math.max(...lastGlyph.flatMap(s => s.map(p => p[0])));
        if (left - maxLastX > 14) {
          glyphs.push([pts]);
        } else {
          lastGlyph.push(pts);
        }
      } else {
        glyphs.push([pts]);
      }
    }
    return glyphs;
  }

  function solvePolylineCaptcha(svgText, templateBank = SEED_TEMPLATES) {
    const glyphs = extractGlyphs(svgText);
    const result = [];
    const SWITCH_THRESHOLD = 0.16;

    for (const glyph of glyphs) {
      const normalized = normalizeGlyph(glyph);
      const xs = glyph.flatMap(s => s.map(p => p[0]));
      const ys = glyph.flatMap(s => s.map(p => p[1]));

      let bestDigit = null;
      let bestCost = SWITCH_THRESHOLD;

      const closed = normalized.length > 0 && normalized[0].length > 1
        ? Math.hypot(
            normalized[0][0][0] - normalized[0][normalized[0].length - 1][0],
            normalized[0][0][1] - normalized[0][normalized[0].length - 1][1]
          ) < 0.15
        : true;

      for (const [digit, variants] of Object.entries(templateBank)) {
        if (digit === "0" && !closed) continue;
        for (const shape of variants) {
          const normShape = normalizeGlyph(shape);
          const cost = shapeDistance(normalized, normShape);
          if (cost < bestCost) {
            bestDigit = digit;
            bestCost = cost;
          }
        }
      }

      if (bestDigit === null && glyph.length === 1) {
        const w = (Math.max(...xs) - Math.min(...xs));
        const h = (Math.max(...ys) - Math.min(...ys)) || 1.0;
        if (w / h < 0.5) {
          bestDigit = "1";
        }
      }

      if (bestDigit === null) {
        throw new Error("Glyph cek belum dikenali: " + JSON.stringify(normalized));
      }
      result.push(bestDigit);
    }
    return result.join("");
  }

  // ==========================================
  // 2. ORDER EVALUATION & DECISION ENGINE
  // ==========================================

  function parseOrderCardText(text) {
    let fareMilli = 0;
    const fareMatch = text.match(/([\d.,]+)\s*koin/i);
    if (fareMatch) {
      const rawStr = fareMatch[1].trim();
      const num = parseFloat(rawStr.replace(",", "."));
      if (!isNaN(num)) {
        if (num < 100) {
          fareMilli = Math.round(num * 1000);
        } else {
          fareMilli = Math.round(num);
        }
      }
    }

    let distance = 0;
    const distMatch = text.match(/(\d+)\s*petak/i);
    if (distMatch) {
      distance = parseInt(distMatch[1], 10) || 0;
    }

    const isWarga = /pesanan\s*warga|warga/i.test(text);
    return { fareMilli, distance, isWarga };
  }

  function evaluateOrders(orders, config = { strategy: "time_efficiency", preferWarga: true, maxDistance: 30 }) {
    if (!Array.isArray(orders) || orders.length === 0) {
      return null;
    }

    const strategy = config.strategy || "time_efficiency";
    const maxDist = config.maxDistance || 30;

    const scored = orders.map((order, index) => {
      const fare = typeof order.fareMilli === "number" ? order.fareMilli : (order.fare || 0);
      const dist = Math.max(1, typeof order.distance === "number" ? order.distance : (order.dist || 1));
      const isWarga = !!order.warga || !!order.isWarga;

      // Rasio koin per petak jarak tempuh (Price to Distance)
      const ratePerDist = fare / dist;

      // Estimasi waktu tempuh realistis: base overhead 15s (ambil + jemput + turun) + 4.5s per petak
      const estimatedSeconds = 15 + dist * 4.5;
      const koinPerSecond = fare / estimatedSeconds;

      // Skor efisiensi waktu dengan preferensi pesanan warga (15% bonus)
      const wargaBonus = (config.preferWarga && isWarga) ? 1.15 : 1.0;
      const timeScore = koinPerSecond * wargaBonus;
      const isTooFar = dist > maxDist;

      return {
        order,
        index,
        fare,
        dist,
        isWarga,
        ratePerDist,
        koinPerSecond,
        timeScore,
        isTooFar
      };
    });

    if (strategy === "max_fare") {
      scored.sort((a, b) => {
        if (a.isTooFar !== b.isTooFar) {
          return a.isTooFar ? 1 : -1;
        }
        if (b.fare !== a.fare) {
          return b.fare - a.fare;
        }
        if (config.preferWarga && a.isWarga !== b.isWarga) {
          return a.isWarga ? -1 : 1;
        }
        return a.dist - b.dist;
      });
    } else {
      // Default: "time_efficiency" (Price to Distance paling worth it dengan waktu)
      scored.sort((a, b) => {
        // 1. Singkirkan order yang terlalu jauh (>30 petak) jika ada alternatif wajar
        if (a.isTooFar !== b.isTooFar) {
          return a.isTooFar ? 1 : -1;
        }
        // 2. Pilih skor efisiensi waktu (koin per detik) tertinggi
        if (Math.abs(b.timeScore - a.timeScore) > 0.05) {
          return b.timeScore - a.timeScore;
        }
        // 3. Jika skor waktu seimbang, pilih price to distance (koin per petak) tertinggi
        if (Math.abs(b.ratePerDist - a.ratePerDist) > 0.1) {
          return b.ratePerDist - a.ratePerDist;
        }
        // 4. Jika masih seimbang, prioritaskan pesanan warga
        if (config.preferWarga && a.isWarga !== b.isWarga) {
          return a.isWarga ? -1 : 1;
        }
        return a.dist - b.dist;
      });
    }

    return scored[0]?.order || null;
  }

  // ==========================================
  // 3. DRAGGABLE HUD MATH & POSITION CLAMP
  // ==========================================

  function computeClampedPosition(elemX, elemY, deltaX, deltaY, elemW, elemH, winW, winH) {
    const newX = elemX + deltaX;
    const newY = elemY + deltaY;
    const maxLeft = Math.max(0, winW - elemW);
    const maxTop = Math.max(0, winH - elemH);
    const clampX = Math.max(0, Math.min(newX, maxLeft));
    const clampY = Math.max(0, Math.min(newY, maxTop));
    return { left: clampX, top: clampY };
  }

  function restoreClampedPosition(savedPos, elemW, elemH, winW, winH) {
    if (!savedPos || typeof savedPos.left !== "number" || typeof savedPos.top !== "number") {
      return null;
    }
    const maxLeft = Math.max(0, winW - elemW);
    const maxTop = Math.max(0, winH - elemH);
    const clampX = Math.max(0, Math.min(savedPos.left, maxLeft));
    const clampY = Math.max(0, Math.min(savedPos.top, maxTop));
    return { left: clampX, top: clampY };
  }

  // Human jitter helper
  function humanJitter(min, max) {
    return Math.floor(min + Math.random() * (max - min + 1));
  }

  // ==========================================
  // 3. NAVIGATION & DRIVING AUTOPILOT MATH
  // ==========================================

  function calculateBearing(curX, curY, targetX, targetY) {
    const dx = targetX - curX;
    const dy = targetY - curY;
    return Math.atan2(dx, dy);
  }

  function findActiveSegment(pts, curX, curY, hintSeg = 0) {
    if (!Array.isArray(pts) || pts.length < 2) return { seg: 0, off: 0 };
    let bestSeg = Math.max(0, Math.min(hintSeg, pts.length - 2));
    let minOff = 1e9;
    for (let i = 0; i < pts.length - 1; i++) {
      const pA = pts[i];
      const pB = pts[i + 1];
      const ux = pB.x - pA.x;
      const uy = pB.y - pA.y;
      const lenSq = ux * ux + uy * uy;
      const t = lenSq ? Math.max(0, Math.min(1, ((curX - pA.x) * ux + (curY - pA.y) * uy) / lenSq)) : 0;
      const projX = pA.x + ux * t;
      const projY = pA.y + uy * t;
      const off = Math.hypot(curX - projX, curY - projY);
      if (off < minOff - 1e-4) {
        minOff = off;
        bestSeg = i;
      }
    }
    return { seg: bestSeg, off: minOff };
  }

  function getNextCheckpoint(pts, curX, curY, hintSeg = 0, reachRadius = 0.45) {
    if (!Array.isArray(pts) || pts.length === 0) return null;
    if (pts.length === 1) return { checkpoint: pts[0], seg: 0, pA: pts[0], pB: pts[0], reachedEnd: true };

    const { seg: activeSeg } = findActiveSegment(pts, curX, curY, hintSeg);
    let targetSeg = activeSeg;
    let checkpoint = pts[targetSeg + 1];

    // Jika checkpoint tikungan saat ini sudah tercapai (radius <= 0.45) dan masih ada checkpoint berikutnya
    const distToCheckpoint = Math.hypot(checkpoint.x - curX, checkpoint.y - curY);
    if (distToCheckpoint <= reachRadius && targetSeg + 1 < pts.length - 1) {
      targetSeg += 1;
      checkpoint = pts[targetSeg + 1];
    }

    return {
      pA: pts[targetSeg],
      pB: checkpoint,
      checkpoint,
      seg: targetSeg,
      reachedEnd: targetSeg >= pts.length - 2 && distToCheckpoint <= reachRadius
    };
  }

  function calculateRoadSteering(pA, pB, curX, curY) {
    if (!pA || !pB) return { aimX: curX, aimY: curY, bearing: 0, roadAxis: "none", dx: 0, dy: 0 };

    const isVertical = Math.abs(pB.x - pA.x) < 0.1;
    const isHorizontal = Math.abs(pB.y - pA.y) < 0.1;

    let aimX = pB.x;
    let aimY = pB.y;
    let roadAxis = "free";

    if (isVertical) {
      roadAxis = "vertical";
      // Kunci arah X tepat di tengah jalan vertikal
      aimX = pB.x;
      aimY = pB.y;
    } else if (isHorizontal) {
      roadAxis = "horizontal";
      // Kunci arah Y tepat di tengah jalan horizontal
      aimX = pB.x;
      aimY = pB.y;
    }

    const dx = aimX - curX;
    const dy = aimY - curY;
    const bearing = Math.atan2(dx, dy);

    return { aimX, aimY, bearing, roadAxis, dx, dy };
  }

  function findLookaheadWaypoint(pts, curX, curY, startSeg = 0, minDistance = 1.5) {
    if (!Array.isArray(pts) || pts.length === 0) return null;
    const seg = Math.max(0, Math.min(startSeg, pts.length - 1));
    for (let idx = seg; idx < pts.length; idx++) {
      const pt = pts[idx];
      const d = Math.hypot(pt.x - curX, pt.y - curY);
      if (d >= minDistance) {
        return pt;
      }
    }
    return pts[pts.length - 1];
  }

  function isArrivalReached(curX, curY, targetX, targetY, threshold = 1.4) {
    const dist = Math.hypot(targetX - curX, targetY - curY);
    return dist <= threshold;
  }

  function calculateAntiStuckNudge(dx, dy, step = 0.35, roadAxis = "free") {
    if (roadAxis === "vertical") {
      return { nudgeX: 0, nudgeY: Math.sign(dy || 1) * step };
    }
    if (roadAxis === "horizontal") {
      return { nudgeX: Math.sign(dx || 1) * step, nudgeY: 0 };
    }
    const len = Math.hypot(dx, dy) || 1;
    return {
      nudgeX: (dx / len) * step,
      nudgeY: (dy / len) * step
    };
  }

  function determineKemudiAction(params = {}) {
    const {
      walkNavTurn = null,
      gpsBannerText = "",
      kemudiGoOn = false,
      kemudiGoDisabled = false,
      isTunggu = false,
      hasKemudiPutar = false,
      hasKemudiKiri = false,
      hasKemudiKanan = false,
      hasKemudiGo = false,
      now = Date.now(),
      lastPutarTime = 0,
      lastTurnTime = 0,
      lastGoTime = 0
    } = params;

    const bannerStr = typeof gpsBannerText === "string" ? gpsBannerText : "";
    const isPutar = walkNavTurn === "putar" || bannerStr.includes("Putar balik") || bannerStr.includes("di belakangmu");
    const isTurnKiri = walkNavTurn === "kiri" || bannerStr.includes("Belok kiri");
    const isTurnKanan = walkNavTurn === "kanan" || bannerStr.includes("Belok kanan");

    const distMatch = bannerStr.match(/dalam\s+(\d+)\s+petak/i);
    const turnPetak = distMatch ? parseInt(distMatch[1], 10) : null;

    // Belok kiri/kanan hanya dieksekusi saat di simpang (isTunggu), jarak <= 1 petak, atau tanpa info jarak
    const isTurnKiriNow = isTurnKiri && (isTunggu || turnPetak === null || turnPetak <= 1);
    const isTurnKananNow = isTurnKanan && (isTunggu || turnPetak === null || turnPetak <= 1);

    // Kebutuhan manuver arah (putar balik atau belok di simpang)
    const needsTurn = isPutar || isTurnKiriNow || isTurnKananNow || isTunggu;

    // 0. STOP DULU JIKA SEDANG JALAN:
    // Game KampungSebelah tidak mengeksekusi belok/putar saat speed > 0 (jalan aktif).
    // Tombol 'Berhenti' (kemudi-go saat kemudiGoOn aktif) harus diklik dulu untuk menghentikan motor,
    // baru kemudian tombol belok/putar dapat dieksekusi pada tick berikutnya saat berhenti.
    if (needsTurn && kemudiGoOn && !kemudiGoDisabled && hasKemudiGo && (now - lastGoTime > 600)) {
      return { action: "stop_for_turn", reason: "Hentikan kemudi jalan aktif agar tombol belok/putar dapat dieksekusi" };
    }

    // 1. PRIORITAS UTAMA: Putar Balik jika arah rute berlawanan / di belakang (wajib interaksi)
    if (isPutar && hasKemudiPutar && (now - lastPutarTime > 1000)) {
      return { action: "putar", reason: "U-turn required: Arah tujuan di belakangmu" };
    }

    // 2. PRIORITAS KEDUA: Belok Kiri di persimpangan jalan (wajib interaksi)
    if (isTurnKiriNow && hasKemudiKiri && (now - lastTurnTime > 800)) {
      return { action: "kiri", reason: "Belok kiri sesuai petunjuk rute / persimpangan" };
    }

    // 3. PRIORITAS KETIGA: Belok Kanan di persimpangan jalan (wajib interaksi)
    if (isTurnKananNow && hasKemudiKanan && (now - lastTurnTime > 800)) {
      return { action: "kanan", reason: "Belok kanan sesuai petunjuk rute / persimpangan" };
    }

    // 4. Jika sedang di persimpangan menunggu pemilihan arah (n.tunggu = true / Pilih arah)
    if (isTunggu && (now - lastTurnTime > 800)) {
      if (hasKemudiKiri && isTurnKiri) return { action: "kiri", reason: "Pilih arah kiri di simpang" };
      if (hasKemudiKanan && isTurnKanan) return { action: "kanan", reason: "Pilih arah kanan di simpang" };
      if (hasKemudiKiri) return { action: "kiri", reason: "Pilih arah kiri di simpang" };
      if (hasKemudiKanan) return { action: "kanan", reason: "Pilih arah kanan di simpang" };
    }

    // 5. PRIORITAS KEEMPAT: Mulai jalan (Jalan / Ikut jalan sendiri) CUKUP 1 KALI saat diam/berhenti
    // Jangan klik jika sedang melaju (kemudiGoOn), atau tombol disabled (tunggu simpang), atau sedang perlu belok/putar
    if (hasKemudiGo && !kemudiGoDisabled && !kemudiGoOn && !isTunggu && !isPutar && !isTurnKiriNow && !isTurnKananNow && (now - lastGoTime > 2000)) {
      return { action: "jalan", reason: "Mengaktifkan kemudi jalan otomatis (cukup 1x klik)" };
    }

    return { action: "idle", reason: "Sedang berjalan atau tidak ada aksi kemudi baru" };
  }

  // ==========================================
  // 4. AUTO-KEBUTUHAN REFILL MODULE & SHOP DB
  // ==========================================

  const DEFAULT_SHOPS = {
    fuel: [
      { id: "914b6bb0-6684-4037-93bc-423810875eae", name: "SPBU Kampung Sebelah", item: "isi-pertalite" },
      { id: "2106025d-77ac-4a49-8520-8d84740ef17f", name: "SPBU Utara 1", item: "isi-pertalite" },
      { id: "8d1714a7-f9e0-4f38-b5a2-dcc0e2834c08", name: "SPBU Utara 2", item: "isi-pertalite" }
    ],
    condition: [
      { id: "b2400595-7b5b-4571-aa2e-bcff27a04d9f", name: "Bengke spesialis motor", item: "servis-motor" },
      { id: "4f1f6929-8ea1-4209-ab30-523b314efe11", name: "Akademis.ai Motor", item: "servis-motor" },
      { id: "78545bac-51dd-4898-bedc-33e33cc5820c", name: "Bengkel motor Gotei", item: "servis-motor" }
    ],
    data: [
      { id: "bdda0310-4488-418f-a479-9710a10e2d96", name: "Somadun Cell", item: "pulsa" },
      { id: "a162273d-6832-4223-a2b9-409d6c291291", name: "Akademis.ai Konter", item: "pulsa" },
      { id: "dffbbddb-37f7-4e2d-9d22-f91af809c2ab", name: "TOPUP CELL", item: "pulsa" }
    ]
  };

  function evaluateKebutuhanRefill(bars, config = {}) {
    if (!bars) return null;
    const minFuel = typeof config.minBensin === "number" ? config.minBensin : 20;
    const minCond = typeof config.minKondisi === "number" ? config.minKondisi : 25;
    const minData = typeof config.minKuota === "number" ? config.minKuota : 16;

    const fuel = typeof bars.bensin === "number" ? bars.bensin : (bars.fuel ?? 100);
    const cond = typeof bars.kendaraan === "number" ? bars.kendaraan : (bars.condition ?? 100);
    const data = typeof bars.kuota === "number" ? bars.kuota : (bars.data ?? 100);

    const needs = [];
    if (fuel <= minFuel) {
      needs.push({
        resource: "fuel",
        name: "bensin",
        current: fuel,
        threshold: minFuel,
        priority: (minFuel - fuel) + 10
      });
    }
    if (cond <= minCond) {
      needs.push({
        resource: "condition",
        name: "kondisi",
        current: cond,
        threshold: minCond,
        priority: (minCond - cond) + 8
      });
    }
    if (data <= minData) {
      needs.push({
        resource: "data",
        name: "kuota",
        current: data,
        threshold: minData,
        priority: (minData - data) + 12
      });
    }

    if (needs.length === 0) return null;
    needs.sort((a, b) => b.priority - a.priority);
    return needs[0];
  }

  async function buyShopItem(resource, shopList = DEFAULT_SHOPS) {
    const candidates = shopList[resource] || [];
    for (const shop of candidates) {
      try {
        const res = await fetch(`/api/shops/${shop.id}/buy`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({
            item: shop.item,
            requestId: (typeof crypto !== "undefined" && crypto.randomUUID) ? crypto.randomUUID() : `req_${Date.now()}`
          })
        });
        if (res.ok) {
          return { success: true, shop: shop.name, item: shop.item };
        }
        const data = await res.json().catch(() => ({}));
        if (res.status === 400 || res.status === 404) continue;
        return { success: false, error: data?.error || res.statusText };
      } catch (err) {
        // Abaikan error jaringan antar toko, coba kandidat selanjutnya
      }
    }
    return { success: false, error: "Tidak ada toko yang tersedia" };
  }

  // ==========================================
  // 5. BROWSER EXTENSION RUNTIME & HUD UI
  // ==========================================

  if (typeof window !== "undefined" && typeof document !== "undefined") {
    // Pastikan hanya aktif di halaman game utama (bukan /diving atau /mancing)
    function isOjolEligiblePage() {
      const p = window.location.pathname;
      return !p.startsWith("/diving") && !p.startsWith("/mancing");
    }

    if (!isOjolEligiblePage()) {
      return {
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
      };
    }

    const ojolConfig = {
      autoOjol: false,
      mode: "kendara",             // Versi Ekstensi: Khusus Mode Kendarai (3D Jalan Sendiri & Tanpa Batas 14 Jam)
      strategy: "time_efficiency", // Paling worth it dengan waktu (Price to Distance ROI)
      preferWarga: true,
      autoKebutuhan: true,        // Otomatis beli bensin, bengkel, & kuota saat kritis
      minBensin: 20,              // Refill jika bensin <= 20%
      minKondisi: 25,             // Servis jika kondisi <= 25%
      minKuota: 16,               // Topup jika kuota <= 16%
      autoSolveCaptcha: true,
      humanJitter: true,
      antiCekKilat: true,         // Proteksi anti-bot cek_kilat (tunda > 2.5 detik)
      retry409Seconds: 9,
      maxDistance: 30,            // Filter order jarak ekstrem (>30 petak) agar tidak terjebak timer lama
      maxNarikMenitHarian: 840    // Kuota harian dinaikkan ke 14 jam (840 menit)
    };

    const ojolStats = {
      ordersCompleted: 0,
      totalEarnedKoin: 0,
      lastFare: 0,
      lastRoute: "-",
      phase: "IDLE", // IDLE, SEARCHING, SELECTING, DRIVING, ARRIVED, CLAIMING, COOLDOWN
      statusMessage: "Siap narik kendara (Tanpa Batas 14 Jam & Auto-Kebutuhan)",
      bars: {
        bensin: 100,
        kondisi: 100,
        kuota: 100
      },
      narikMenit: 0,
      narikMaksMenit: 840,
      logs: []
    };

    let lastKebutuhanCheckTime = 0;

    async function fetchOjolBars() {
      try {
        const res = await fetch("/api/ojol", { credentials: "same-origin" });
        if (!res.ok) return null;
        const data = await res.json();
        if (data && data.bars) {
          ojolStats.bars = {
            bensin: typeof data.bars.bensin === "number" ? data.bars.bensin : 100,
            kondisi: typeof data.bars.kendaraan === "number" ? data.bars.kendaraan : 100,
            kuota: typeof data.bars.kuota === "number" ? data.bars.kuota : 100
          };
          if (typeof data.narikMenit === "number") {
            ojolStats.narikMenit = data.narikMenit;
          }
          if (typeof data.narikMaksMenit === "number") {
            ojolStats.narikMaksMenit = data.narikMaksMenit;
          }
          return ojolStats.bars;
        }
      } catch (err) {
        // Abaikan fetch error
      }
      return null;
    }

    async function checkAndRefillKebutuhan(forceCheck = false) {
      const now = Date.now();
      if (!forceCheck && (now - lastKebutuhanCheckTime < 20000)) {
        return false;
      }
      lastKebutuhanCheckTime = now;

      const bars = await fetchOjolBars();
      if (!bars) return false;
      updateHUDView();

      if (!ojolConfig.autoKebutuhan) return false;

      const needed = evaluateKebutuhanRefill(bars, ojolConfig);
      if (!needed) return false;

      const labelMap = {
        fuel: "⛽ Mengisi Bensin di SPBU...",
        condition: "🔧 Servis Mesin di Bengkel...",
        data: "📶 Membeli Kuota di Konter..."
      };
      addLog(labelMap[needed.resource] || `🛒 Membeli kebutuhan ${needed.name}...`);
      ojolStats.statusMessage = `🛒 Mengisi ${needed.name}...`;
      updateHUDView();

      const result = await buyShopItem(needed.resource);
      if (result.success) {
        addLog(`✅ Berhasil isi ${needed.name} di ${result.shop}!`);
        await fetchOjolBars();
        updateHUDView();
        await new Promise(r => setTimeout(r, humanJitter(600, 1000)));
        return true;
      } else {
        addLog(`⚠️ Gagal isi ${needed.name}: ${result.error}`);
        return false;
      }
    }

    function addLog(msg) {
      const time = new Date().toLocaleTimeString("id-ID", { hour12: false });
      ojolStats.logs.unshift(`[${time}] ${msg}`);
      if (ojolStats.logs.length > 15) ojolStats.logs.pop();
      updateHUDLogView();
    }

    // Restore saved settings
    try {
      const savedConfig = localStorage.getItem("ks_ojol_config");
      if (savedConfig) {
        Object.assign(ojolConfig, JSON.parse(savedConfig));
      }
      const savedStats = localStorage.getItem("ks_ojol_stats");
      if (savedStats) {
        const parsed = JSON.parse(savedStats);
        ojolStats.ordersCompleted = parsed.ordersCompleted || 0;
        ojolStats.totalEarnedKoin = parsed.totalEarnedKoin || 0;
      }
    } catch (_) {}

    function saveSettings() {
      try {
        localStorage.setItem("ks_ojol_config", JSON.stringify(ojolConfig));
        localStorage.setItem("ks_ojol_stats", JSON.stringify({
          ordersCompleted: ojolStats.ordersCompleted,
          totalEarnedKoin: ojolStats.totalEarnedKoin
        }));
      } catch (_) {}
    }

    let hudElement = null;
    let isProcessing = false;
    let lastActionTime = 0;
    let retry409Until = 0;
    let cooldownUntil = 0;
    let arrivedDetectedAt = 0;
    let liveNavData = null;
    let isAutopilotDriving = false;
    let lastPutarTime = 0;
    let lastTurnTime = 0;
    let lastGoTime = 0;

    if (typeof window !== "undefined") {
      window.addEventListener("ks_ojol_nav_tick", (e) => {
        liveNavData = e.detail || null;
      });

      window.addEventListener("ks_ojol_autopilot_status", (e) => {
        const d = e.detail;
        isAutopilotDriving = !!d?.active;
      });
    }

    function setAutopilot(active) {
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("ks_ojol_autopilot_command", {
          detail: { action: active ? "start" : "stop" }
        }));
      }
    }

    function createHUD() {
      if (document.getElementById("ks-ojol-hud")) return;

      const hud = document.createElement("div");
      hud.id = "ks-ojol-hud";
      hud.style.cssText = `
        position: fixed;
        bottom: 24px;
        right: 24px;
        width: 310px;
        background: rgba(11, 19, 41, 0.94);
        backdrop-filter: blur(14px);
        -webkit-backdrop-filter: blur(14px);
        border: 1px solid rgba(255, 255, 255, 0.12);
        box-shadow: 0 12px 36px rgba(0, 0, 0, 0.5);
        border-radius: 12px;
        color: #e2e8f0;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        font-size: 12px;
        z-index: 999999;
        overflow: hidden;
        user-select: none;
        transition: transform 0.2s ease, opacity 0.2s ease;
      `;

      hud.innerHTML = `
        <div id="ks-ojol-header" style="
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 10px 14px;
          background: rgba(255, 255, 255, 0.05);
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
          cursor: grab;
        ">
          <div style="display: flex; align-items: center; gap: 8px; font-weight: bold; font-size: 13px; color: #38bdf8;">
            <span style="font-size: 14px; color: #94a3b8; cursor: grab;">⠿</span>
            <span>🏍️ Auto-Ojol Kendara (3D)</span>
          </div>
          <div style="display: flex; align-items: center; gap: 6px;">
            <span id="ks-ojol-badge-status" style="
              font-size: 10px;
              padding: 2px 6px;
              border-radius: 4px;
              font-weight: bold;
              background: #334155;
              color: #94a3b8;
            ">OFF</span>
            <button id="ks-ojol-toggle-min" style="
              background: transparent;
              border: none;
              color: #94a3b8;
              font-size: 14px;
              cursor: pointer;
              padding: 0 4px;
            ">_</button>
          </div>
        </div>

        <div id="ks-ojol-body" style="padding: 12px 14px;">
          <!-- Feature Card: Khusus Mode Kendarai 3D -->
          <div style="
            background: linear-gradient(135deg, rgba(2, 132, 199, 0.16), rgba(15, 23, 42, 0.5));
            border: 1px solid rgba(2, 132, 199, 0.4);
            border-radius: 8px;
            padding: 9px 11px;
            margin-bottom: 10px;
            font-size: 11px;
            color: #bae6fd;
            line-height: 1.45;
          ">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 5px;">
              <b style="color: #38bdf8; font-size: 12px;">🏍️ Mode Kendarai 3D</b>
              <span style="background: rgba(16, 185, 129, 0.25); color: #34d399; font-size: 10px; font-weight: bold; padding: 1px 6px; border-radius: 4px;">Tanpa Batas Kuota</span>
            </div>
            • 🎮 Autopilot WASD, Rute 3D & Simpang Belok/Putar<br>
            • ♾️ Bebas Limit Kuota Narik (<code style="color:#7dd3fc;">kendara.tanpaBatas: true</code>)<br>
            • ⛽ Auto-Kebutuhan Otomatis (SPBU, Bengkel, Kuota)<br>
            • 🛡️ Proteksi Anti-Cek Kilat (&gt;2.5s) & Auto-Solve SVG
          </div>

          <!-- Kebutuhan Meters Card with Auto-Refill -->
          <div style="
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 8px;
            padding: 8px 10px;
            margin-bottom: 10px;
          ">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
              <span style="font-weight: bold; font-size: 11px; color: #cbd5e1;">📊 Kebutuhan Ojol</span>
              <label style="display: flex; align-items: center; gap: 4px; font-size: 10px; color: #38bdf8; cursor: pointer;">
                <input type="checkbox" id="ks-ojol-chk-auto-kebutuhan" style="cursor: pointer; margin: 0;" />
                <span>Auto-Beli</span>
              </label>
            </div>
            <!-- Bensin Bar -->
            <div style="margin-bottom: 6px;">
              <div style="display: flex; justify-content: space-between; font-size: 10px; margin-bottom: 2px;">
                <span style="color: #94a3b8;">⛽ Bensin</span>
                <span id="ks-ojol-val-bensin" style="font-weight: bold; color: #10b981;">--%</span>
              </div>
              <div style="width: 100%; height: 5px; background: rgba(255,255,255,0.08); border-radius: 3px; overflow: hidden;">
                <div id="ks-ojol-bar-bensin" style="width: 0%; height: 100%; background: #10b981; transition: width 0.3s;"></div>
              </div>
            </div>
            <!-- Kondisi Bar -->
            <div style="margin-bottom: 6px;">
              <div style="display: flex; justify-content: space-between; font-size: 10px; margin-bottom: 2px;">
                <span style="color: #94a3b8;">🔧 Kondisi Mesin</span>
                <span id="ks-ojol-val-kondisi" style="font-weight: bold; color: #10b981;">--%</span>
              </div>
              <div style="width: 100%; height: 5px; background: rgba(255,255,255,0.08); border-radius: 3px; overflow: hidden;">
                <div id="ks-ojol-bar-kondisi" style="width: 0%; height: 100%; background: #10b981; transition: width 0.3s;"></div>
              </div>
            </div>
            <!-- Kuota Bar -->
            <div>
              <div style="display: flex; justify-content: space-between; font-size: 10px; margin-bottom: 2px;">
                <span style="color: #94a3b8;">📶 Kuota HP</span>
                <span id="ks-ojol-val-kuota" style="font-weight: bold; color: #10b981;">--%</span>
              </div>
              <div style="width: 100%; height: 5px; background: rgba(255,255,255,0.08); border-radius: 3px; overflow: hidden;">
                <div id="ks-ojol-bar-kuota" style="width: 0%; height: 100%; background: #10b981; transition: width 0.3s;"></div>
              </div>
            </div>
          </div>

          <!-- Main Status Indicator -->
          <div style="margin-bottom: 10px;">
            <div style="font-size: 11px; color: #94a3b8; margin-bottom: 3px;">Status Bot:</div>
            <div id="ks-ojol-status-text" style="
              font-weight: bold;
              color: #f8fafc;
              font-size: 12px;
              background: rgba(0, 0, 0, 0.3);
              padding: 6px 8px;
              border-radius: 6px;
              border: 1px solid rgba(255, 255, 255, 0.05);
            ">Siap narik ojol</div>
          </div>

          <!-- Live Stats Grid -->
          <div style="
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            margin-bottom: 12px;
          ">
            <div style="background: rgba(255, 255, 255, 0.04); padding: 8px; border-radius: 6px; border: 1px solid rgba(255, 255, 255, 0.06);">
              <div style="font-size: 10px; color: #94a3b8;">Order Selesai</div>
              <div id="ks-ojol-stat-count" style="font-size: 16px; font-weight: bold; color: #38bdf8;">0</div>
            </div>
            <div style="background: rgba(255, 255, 255, 0.04); padding: 8px; border-radius: 6px; border: 1px solid rgba(255, 255, 255, 0.06);">
              <div style="font-size: 10px; color: #94a3b8;">Total Omzet</div>
              <div id="ks-ojol-stat-koin" style="font-size: 16px; font-weight: bold; color: #fbbf24;">+0.0 🪙</div>
            </div>
          </div>

          <!-- Last Order Info -->
          <div style="font-size: 11px; color: #94a3b8; margin-bottom: 12px;">
            Rute Terakhir: <span id="ks-ojol-last-route" style="color: #cbd5e1;">-</span>
          </div>

          <!-- Toggle / Action Button -->
          <button id="ks-ojol-btn-start" style="
            width: 100%;
            padding: 10px;
            border-radius: 6px;
            border: none;
            font-weight: bold;
            font-size: 13px;
            cursor: pointer;
            background: linear-gradient(135deg, #0284c7, #0369a1);
            color: #fff;
            margin-bottom: 8px;
            box-shadow: 0 2px 8px rgba(2, 132, 199, 0.3);
            transition: all 0.15s ease;
          ">▶ MULAI AUTO-OJOL</button>

          <button id="ks-ojol-btn-open-panel" style="
            width: 100%;
            padding: 7px;
            border-radius: 6px;
            border: 1px solid rgba(255, 255, 255, 0.15);
            background: rgba(255, 255, 255, 0.05);
            color: #cbd5e1;
            font-size: 11px;
            font-weight: 500;
            cursor: pointer;
            margin-bottom: 6px;
          ">🛵 Buka Lembar Ojol (Kerja › Ojol)</button>

          <a href="http://localhost:6080" target="_blank" id="ks-ojol-btn-web-dashboard" style="
            display: block;
            text-align: center;
            width: 100%;
            padding: 7px;
            box-sizing: border-box;
            border-radius: 6px;
            border: 1px solid rgba(59, 130, 246, 0.4);
            background: linear-gradient(135deg, rgba(30, 58, 138, 0.8), rgba(59, 130, 246, 0.8));
            color: #ffffff;
            font-size: 11px;
            font-weight: 600;
            text-decoration: none;
            cursor: pointer;
            margin-bottom: 10px;
          ">⚙️ Buka Web Dashboard (Auto Kebutuhan)</a>

          <!-- Log stream -->
          <div style="font-size: 10px; color: #64748b; margin-bottom: 4px; font-weight: bold;">LOG AKTIVITAS:</div>
          <div id="ks-ojol-log-list" style="
            height: 65px;
            overflow-y: auto;
            background: rgba(0, 0, 0, 0.35);
            border-radius: 4px;
            padding: 4px 6px;
            font-family: monospace;
            font-size: 10px;
            color: #94a3b8;
            line-height: 1.35;
          ">
            <div>[Sistem] Auto-Ojol siap.</div>
          </div>
        </div>
      `;

      document.body.appendChild(hud);
      hudElement = hud;

      // Make Draggable
      setupDraggable(hud, document.getElementById("ks-ojol-header"), "ks_hud_pos_ojol");

      // Setup Event Listeners
      const btnStart = document.getElementById("ks-ojol-btn-start");
      btnStart.onclick = () => {
        toggleAutoOjol();
      };

      const btnOpenPanel = document.getElementById("ks-ojol-btn-open-panel");
      btnOpenPanel.onclick = () => {
        openOjolSheet();
      };

      const chkAutoKebutuhan = document.getElementById("ks-ojol-chk-auto-kebutuhan");
      if (chkAutoKebutuhan) {
        chkAutoKebutuhan.onchange = (e) => {
          ojolConfig.autoKebutuhan = !!e.target.checked;
          saveSettings();
          addLog(`🛒 Auto-Kebutuhan ${ojolConfig.autoKebutuhan ? "diaktifkan (Auto SPBU, Bengkel, Kuota)" : "dinonaktifkan"}`);
          updateHUDView();
        };
      }

      let minimized = false;
      const toggleMin = document.getElementById("ks-ojol-toggle-min");
      toggleMin.onclick = () => {
        minimized = !minimized;
        document.getElementById("ks-ojol-body").style.display = minimized ? "none" : "block";
        toggleMin.textContent = minimized ? "□" : "_";
      };

      fetchOjolBars();
      updateHUDView();
    }

    function setupDraggable(elem, handle, storageKey) {
      if (!elem || !handle) return;

      // Restore position
      if (storageKey) {
        try {
          const raw = localStorage.getItem(storageKey);
          if (raw) {
            const saved = JSON.parse(raw);
            const winW = window.innerWidth || 1024;
            const winH = window.innerHeight || 768;
            const pos = restoreClampedPosition(saved, 310, 360, winW, winH);
            if (pos) {
              elem.style.left = `${pos.left}px`;
              elem.style.top = `${pos.top}px`;
              elem.style.right = "auto";
              elem.style.bottom = "auto";
            }
          }
        } catch (_) {}
      }

      let isDragging = false;
      let startX = 0, startY = 0;
      let initX = 0, initY = 0;

      handle.addEventListener("dblclick", () => {
        if (storageKey) {
          try { localStorage.removeItem(storageKey); } catch (_) {}
        }
        elem.style.left = "";
        elem.style.top = "";
        elem.style.right = "24px";
        elem.style.bottom = "24px";
      });

      handle.addEventListener("pointerdown", (e) => {
        if (e.target.closest("button, input, select")) return;
        if (e.button !== 0) return;

        isDragging = true;
        startX = e.clientX;
        startY = e.clientY;

        const rect = elem.getBoundingClientRect();
        initX = rect.left;
        initY = rect.top;

        try { handle.setPointerCapture(e.pointerId); } catch (_) {}
        handle.style.cursor = "grabbing";
      });

      window.addEventListener("pointermove", (e) => {
        if (!isDragging) return;
        const deltaX = e.clientX - startX;
        const deltaY = e.clientY - startY;

        const winW = window.innerWidth || 1024;
        const winH = window.innerHeight || 768;
        const rect = elem.getBoundingClientRect();

        const pos = computeClampedPosition(initX, initY, deltaX, deltaY, rect.width, rect.height, winW, winH);
        elem.style.left = `${pos.left}px`;
        elem.style.top = `${pos.top}px`;
        elem.style.right = "auto";
        elem.style.bottom = "auto";
      });

      const stopDrag = () => {
        if (!isDragging) return;
        isDragging = false;
        handle.style.cursor = "grab";
        if (storageKey) {
          const rect = elem.getBoundingClientRect();
          try {
            localStorage.setItem(storageKey, JSON.stringify({ left: rect.left, top: rect.top }));
          } catch (_) {}
        }
      };

      window.addEventListener("pointerup", stopDrag);
      window.addEventListener("pointercancel", stopDrag);
    }

    function toggleAutoOjol(forceState) {
      const next = typeof forceState === "boolean" ? forceState : !ojolConfig.autoOjol;
      ojolConfig.autoOjol = next;
      saveSettings();

      if (next) {
        addLog("▶ Auto-Ojol diaktifkan (Mode Otomatis)");
        ojolStats.statusMessage = "Mencari order / mengecek perjalanan...";
      } else {
        setAutopilot(false);
        addLog("⏹ Auto-Ojol dinonaktifkan");
        ojolStats.statusMessage = "Nonaktif";
      }
      updateHUDView();
    }

    function updateHUDView() {
      const badge = document.getElementById("ks-ojol-badge-status");
      const btnStart = document.getElementById("ks-ojol-btn-start");
      const statusText = document.getElementById("ks-ojol-status-text");
      const statCount = document.getElementById("ks-ojol-stat-count");
      const statKoin = document.getElementById("ks-ojol-stat-koin");
      const lastRoute = document.getElementById("ks-ojol-last-route");

      if (!badge || !btnStart) return;

      const chkAutoKebutuhan = document.getElementById("ks-ojol-chk-auto-kebutuhan");
      if (chkAutoKebutuhan) {
        chkAutoKebutuhan.checked = !!ojolConfig.autoKebutuhan;
      }

      function updateMeter(valElemId, barElemId, val, criticalThreshold, warningThreshold) {
        const valElem = document.getElementById(valElemId);
        const barElem = document.getElementById(barElemId);
        if (!valElem || !barElem) return;
        if (typeof val !== "number" || isNaN(val)) {
          valElem.textContent = "--%";
          barElem.style.width = "0%";
          return;
        }
        const clamped = Math.max(0, Math.min(100, Math.round(val)));
        valElem.textContent = `${clamped}%`;
        barElem.style.width = `${clamped}%`;

        let color = "#10b981";
        if (clamped <= criticalThreshold) {
          color = "#ef4444";
        } else if (clamped <= warningThreshold) {
          color = "#f59e0b";
        }
        valElem.style.color = color;
        barElem.style.background = color;
      }

      const bars = ojolStats.bars || {};
      updateMeter("ks-ojol-val-bensin", "ks-ojol-bar-bensin", bars.bensin, ojolConfig.minBensin || 20, 35);
      updateMeter("ks-ojol-val-kondisi", "ks-ojol-bar-kondisi", bars.kondisi, ojolConfig.minKondisi || 25, 40);
      updateMeter("ks-ojol-val-kuota", "ks-ojol-bar-kuota", bars.kuota, ojolConfig.minKuota || 16, 30);

      if (ojolConfig.autoOjol) {
        badge.textContent = "ON";
        badge.style.background = "#059669";
        badge.style.color = "#ecfdf5";

        btnStart.textContent = "⏹ HENTIKAN AUTO-OJOL";
        btnStart.style.background = "linear-gradient(135deg, #dc2626, #991b1b)";
        btnStart.style.boxShadow = "0 2px 8px rgba(220, 38, 38, 0.3)";
      } else {
        badge.textContent = "OFF";
        badge.style.background = "#334155";
        badge.style.color = "#94a3b8";

        btnStart.textContent = "▶ MULAI AUTO-OJOL";
        btnStart.style.background = "linear-gradient(135deg, #0284c7, #0369a1)";
        btnStart.style.boxShadow = "0 2px 8px rgba(2, 132, 199, 0.3)";
      }

      statusText.textContent = ojolStats.statusMessage;
      statCount.textContent = `${ojolStats.ordersCompleted}`;
      statKoin.textContent = `+${(ojolStats.totalEarnedKoin / 1000).toFixed(1)} 🪙`;
      lastRoute.textContent = ojolStats.lastRoute || "-";
    }

    function updateHUDLogView() {
      const logList = document.getElementById("ks-ojol-log-list");
      if (!logList) return;
      logList.innerHTML = ojolStats.logs.map(l => `<div>${l}</div>`).join("");
    }

    // Helper: Buka sheet kerja atau ojol
    function openOjolSheet() {
      // Coba klik tombol "Terima ongkos" jika sudah sampai
      const terimaBtn = document.querySelector('[data-testid="ojol-kendara-terima"]');
      if (terimaBtn && terimaBtn.offsetParent !== null) {
        dispatchHumanClick(terimaBtn);
        return;
      }

      // Coba klik ikon ojol di sheet kerja jika terbuka
      const ojolIkon = document.querySelector('[data-testid="ojol-ikon"]');
      if (ojolIkon && ojolIkon.offsetParent !== null) {
        dispatchHumanClick(ojolIkon);
        return;
      }

      // Coba klik menu "Kerja" di navigasi bawah
      const menuBar = document.querySelector('[aria-label="Menu permainan"]');
      if (menuBar) {
        const buttons = Array.from(menuBar.querySelectorAll("button, [role='button'], a"));
        const kerjaBtn = buttons.find(b => b.textContent && b.textContent.includes("Kerja"));
        if (kerjaBtn) {
          dispatchHumanClick(kerjaBtn);
          setTimeout(() => {
            const ikon = document.querySelector('[data-testid="ojol-ikon"]');
            if (ikon) dispatchHumanClick(ikon);
          }, 450);
          return;
        }
      }
    }

    // Helper: Native human click event with real non-zero coordinates
    function dispatchHumanClick(element) {
      if (!element || element.disabled) return;
      const rect = element.getBoundingClientRect();
      const x = rect.left + rect.width * (0.3 + Math.random() * 0.4);
      const y = rect.top + rect.height * (0.3 + Math.random() * 0.4);

      const opts = { bubbles: true, cancelable: true, clientX: x, clientY: y, view: window };
      element.dispatchEvent(new PointerEvent("pointerdown", opts));
      element.dispatchEvent(new MouseEvent("mousedown", opts));
      element.dispatchEvent(new PointerEvent("pointerup", opts));
      element.dispatchEvent(new MouseEvent("mouseup", opts));
      element.dispatchEvent(new MouseEvent("click", opts));
    }

    // Helper: Isi input dengan trigger React Synthetic Events
    function setNativeInputValue(input, value) {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;
      if (setter) {
        setter.call(input, value);
      } else {
        input.value = value;
      }
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }

    // ==========================================
    // 5. MAIN AUTOMATION TICK & LOGIC LOOP
    // ==========================================

    async function tickAutoOjol() {
      if (!ojolConfig.autoOjol) return;
      if (isProcessing) return;

      const now = Date.now();
      if (now < retry409Until) {
        const rem = Math.ceil((retry409Until - now) / 1000);
        ojolStats.statusMessage = `⏳ Penumpang sedang turun... coba lagi dalam ${rem}s`;
        updateHUDView();
        return;
      }

      if (now < cooldownUntil) {
        const rem = Math.ceil((cooldownUntil - now) / 1000);
        ojolStats.statusMessage = `⏳ Jeda istirahat alami... ${rem}s`;
        updateHUDView();
        return;
      }

      isProcessing = true;
      try {
        await executeOjolStep();
      } catch (err) {
        console.warn("[AutoOjol] Step error:", err);
      } finally {
        isProcessing = false;
        updateHUDView();
      }
    }

    async function executeOjolStep() {
      // 0. Auto-Kebutuhan: Periksa dan isi bensin, bengkel, atau kuota secara otomatis
      if (ojolConfig.autoKebutuhan) {
        const refilled = await checkAndRefillKebutuhan();
        if (refilled) return;
      }

      // 1. Cek tombol HUD "Terima ongkos" saat tiba di tujuan
      const floatingTerimaBtn = document.querySelector('[data-testid="ojol-kendara-terima"]');
      if (floatingTerimaBtn && floatingTerimaBtn.offsetParent !== null) {
        setAutopilot(false);
        if (!arrivedDetectedAt) arrivedDetectedAt = Date.now();
        ojolStats.phase = "ARRIVED";
        ojolStats.statusMessage = "📍 Sampai di tujuan! Membuka klaim ongkos...";
        addLog("📍 Tiba di tujuan. Membuka klaim ongkos...");
        dispatchHumanClick(floatingTerimaBtn);
        await new Promise(r => setTimeout(r, humanJitter(450, 750)));
        return;
      }

      // 2. Cek apakah ada order aktif di panel Ojol
      const allButtons = Array.from(document.querySelectorAll("button"));
      const ojolCekInput = document.querySelector('[data-testid="ojol-cek"]');
      const captchaImg = document.querySelector('img[src*="/api/ojol/cek"]');
      const ojolLanjutBtn = document.querySelector('[data-testid="ojol-lanjut"]');
      const ojolTungguBtn = document.querySelector('[data-testid="ojol-tunggu"]') || allButtons.find(b => b.textContent && b.textContent.includes("Tunggu"));
      const ojolTungguTurunMsg = document.querySelector('[data-testid="ojol-tunggu-turun"]') || Array.from(document.querySelectorAll("div, p, span")).find(el => el.textContent && el.textContent.includes("Penumpang sedang turun"));

      // 2a-0. Jika sedang menunggu timer resmi penumpang turun (durasi minimal server)
      if (ojolTungguBtn || ojolTungguTurunMsg) {
        setAutopilot(false);
        ojolStats.phase = "WAITING_TURUN";
        const remMatch = (ojolTungguBtn?.textContent || "").match(/(\d+:\d+|\d+)/);
        const remStr = remMatch ? remMatch[0] : "";
        ojolStats.statusMessage = remStr
          ? `⏳ Menunggu penumpang turun (${remStr})...`
          : "⏳ Menunggu durasi minimal perjalanan selesai...";
        return;
      }

      // 2a. Selesaikan Captcha Cek Pengemudi jika muncul
      if (captchaImg && ojolCekInput && (!ojolCekInput.value || ojolCekInput.value.length < 2)) {
        setAutopilot(false);
        ojolStats.phase = "SOLVING_CAPTCHA";
        ojolStats.statusMessage = "🔐 Memecahkan kode cek SVG 2 angka...";
        addLog("🔐 Memecahkan kode verifikasi cek SVG...");

        try {
          const res = await fetch(captchaImg.src, { credentials: "same-origin" });
          const svgText = await res.text();
          const kode = solvePolylineCaptcha(svgText);

          if (kode && kode.length === 2) {
            setNativeInputValue(ojolCekInput, kode);
            addLog(`✅ Kode cek terpecahkan: ${kode}`);
            await new Promise(r => setTimeout(r, humanJitter(250, 400)));
          }
        } catch (e) {
          console.warn("[AutoOjol] Gagal memecahkan captcha:", e);
          addLog("⚠️ Gagal memecahkan captcha, me-refresh gambar...");
          // Klik tombol muat ulang gambar jika ada
          const refreshBtn = captchaImg.parentElement?.querySelector("button");
          if (refreshBtn) dispatchHumanClick(refreshBtn);
          return;
        }
      }

      // 2b. Cek tombol "✅ Sampai! Terima ongkos"
      const terimaOngkosBtn = allButtons.find(b =>
        b.textContent && (b.textContent.includes("Terima ongkos") || b.textContent.includes("Sampai!"))
      );

      if (terimaOngkosBtn && !terimaOngkosBtn.disabled && terimaOngkosBtn.offsetParent !== null) {
        setAutopilot(false);
        if (!arrivedDetectedAt) arrivedDetectedAt = Date.now();

        // Aturan Anti-Bot Cek Kilat (Update 21-22 Nov 2026):
        // Pengemudi yang terima ongkos < 2.5s setelah sampai akan memicu verifikasi di SETIAP order.
        // Tunda minimal >= 2.8s sejak terdeteksi sampai.
        if (ojolConfig.antiCekKilat) {
          const elapsed = Date.now() - arrivedDetectedAt;
          if (elapsed < 2800) {
            const waitMs = (2800 - elapsed) + humanJitter(200, 500);
            ojolStats.statusMessage = `🛡️ Proteksi Anti-Cek Kilat (>2.5s)...`;
            await new Promise(r => setTimeout(r, waitMs));
          }
        }

        ojolStats.phase = "CLAIMING";
        ojolStats.statusMessage = "💰 Mencairkan ongkos ojol...";
        addLog("💰 Mengklik Terima ongkos...");
        dispatchHumanClick(terimaOngkosBtn);

        // Amati apakah muncul penolakan 409 "Penumpang sedang turun"
        await new Promise(r => setTimeout(r, 900));

        const alerts = Array.from(document.querySelectorAll("[role='alert'], p, div"));
        const has409 = alerts.some(el => el.textContent && (el.textContent.includes("turun") || el.textContent.includes("409")));

        if (has409) {
          retry409Until = Date.now() + (ojolConfig.retry409Seconds * 1000);
          addLog(`⏳ Penumpang sedang turun (turun_detik 8). Menunggu ${ojolConfig.retry409Seconds}s...`);
          return;
        }

        // Sukses klaim ongkos
        arrivedDetectedAt = 0;
        ojolStats.ordersCompleted++;
        ojolStats.totalEarnedKoin += (ojolStats.lastFare || 3000);
        saveSettings();
        addLog(`🎉 Ongkos berhasil diterima! Total: ${ojolStats.ordersCompleted} order.`);

        // Cooldown sebelum mencari order berikutnya
        cooldownUntil = Date.now() + humanJitter(2200, 3800);
        return;
      }

      // 2c. Jika tombol "Lanjut menyetir" muncul, klik untuk lanjut
      if (ojolLanjutBtn && !ojolLanjutBtn.disabled && ojolLanjutBtn.offsetParent !== null) {
        ojolStats.phase = "DRIVING";
        ojolStats.statusMessage = "🚗 Melanjutkan menyetir di peta...";
        addLog("🚗 Melanjutkan menyetir ke tujuan...");
        dispatchHumanClick(ojolLanjutBtn);
        setAutopilot(true);
        await new Promise(r => setTimeout(r, 600));
        return;
      }

      // 2d. Cek apakah sedang dalam Mode Kendarai di peta 3D desa
      const hasWalk3DCanvas = !!document.querySelector("canvas");
      const hasSelesaiJalanBtn = allButtons.some(b => b.textContent && b.textContent.includes("Selesai jalan-jalan"));
      const walkNav = document.querySelector('[data-testid="walk-nav"]');
      const kemudiGo = document.querySelector('[data-testid="kemudi-go"]') || allButtons.find(b => b.textContent && (b.textContent.includes("Ikut jalan") || b.textContent.includes("Berhenti") || b.textContent.includes("Jalan")));
      const kemudiPutar = document.querySelector('[data-testid="kemudi-putar"]') || allButtons.find(b => b.textContent && b.textContent.trim().toLowerCase().includes("putar"));
      const kemudiKiri = document.querySelector('[data-testid="kemudi-kiri"]') || allButtons.find(b => b.textContent && b.textContent.trim().toLowerCase().includes("kiri"));
      const kemudiKanan = document.querySelector('[data-testid="kemudi-kanan"]') || allButtons.find(b => b.textContent && b.textContent.trim().toLowerCase().includes("kanan"));
      const gpsBanner = Array.from(document.querySelectorAll("div, p, span, button")).find(el => {
        const txt = el.textContent || "";
        return (txt.includes("Jemput:") || txt.includes("Antar:") || txt.includes("Putar balik") || txt.includes("Belok kiri") || txt.includes("Belok kanan")) && (txt.includes("petak") || txt.includes("sisa"));
      });
      const hasActiveRoute = !!(liveNavData && liveNavData.hasRoute) || !!gpsBanner || !!walkNav || !!kemudiGo;
      const isSheetOpen = !!(document.querySelector('[data-testid="ojol-pilihan"]') || document.querySelector('[data-testid="ojol-cari"]') || document.querySelector('[data-testid="ojol-mode"]'));

      if (hasWalk3DCanvas && (hasSelesaiJalanBtn || hasActiveRoute) && !isSheetOpen) {
        // Cek interaksi arah / persimpangan rute ("Pilih arah")
        const isTunggu = Array.from(document.querySelectorAll("div, span, p, button")).some(el => {
          const t = el.textContent || "";
          return t.includes("Pilih arah") || t.includes("Ketuk \u2190 atau \u2192");
        });
        const bannerText = (gpsBanner?.textContent || "").trim();
        const kemudiGoOn = !!(kemudiGo && kemudiGo.textContent && (kemudiGo.textContent.includes("Berhenti") || kemudiGo.getAttribute("data-active") === "true"));
        const kemudiGoDisabled = !!(kemudiGo && kemudiGo.disabled);

        const decision = determineKemudiAction({
          walkNavTurn: walkNav?.getAttribute("data-turn") || null,
          gpsBannerText: bannerText,
          kemudiGoOn,
          kemudiGoDisabled,
          isTunggu,
          hasKemudiPutar: !!kemudiPutar,
          hasKemudiKiri: !!kemudiKiri,
          hasKemudiKanan: !!kemudiKanan,
          hasKemudiGo: !!kemudiGo,
          now: Date.now(),
          lastPutarTime,
          lastTurnTime,
          lastGoTime
        });

        if (decision.action === "stop_for_turn" && kemudiGo) {
          dispatchHumanClick(kemudiGo);
          lastGoTime = Date.now();
          addLog("🛑 Berhenti sejenak untuk persiapan belok/putar...");
          await new Promise(r => setTimeout(r, humanJitter(400, 600)));
          return;
        }

        if (decision.action === "kiri" && kemudiKiri) {
          dispatchHumanClick(kemudiKiri);
          lastTurnTime = Date.now();
          addLog("↩️ Memilih arah belok kiri di persimpangan jalan");
          await new Promise(r => setTimeout(r, humanJitter(400, 600)));
          return;
        }

        if (decision.action === "kanan" && kemudiKanan) {
          dispatchHumanClick(kemudiKanan);
          lastTurnTime = Date.now();
          addLog("↪️ Memilih arah belok kanan di persimpangan jalan");
          await new Promise(r => setTimeout(r, humanJitter(400, 600)));
          return;
        }

        if (decision.action === "putar" && kemudiPutar) {
          dispatchHumanClick(kemudiPutar);
          lastPutarTime = Date.now();
          addLog("🔄 Memutar balik arah kendaraan");
          await new Promise(r => setTimeout(r, humanJitter(400, 600)));
          return;
        }

        if (decision.action === "jalan" && kemudiGo) {
          dispatchHumanClick(kemudiGo);
          lastGoTime = Date.now();
          addLog("▶️ Mengaktifkan kemudi jalan");
          await new Promise(r => setTimeout(r, humanJitter(400, 600)));
          return;
        }

        ojolStats.phase = "DRIVING";
        setAutopilot(true);

        const sisa = liveNavData && typeof liveNavData.distToFinal === "number"
          ? `(sisa ${Math.round(liveNavData.distToFinal)} petak)`
          : gpsBanner ? `(${gpsBanner.textContent.trim().split("·")[1]?.trim() || "mengikuti rute"})` : "";

        ojolStats.statusMessage = `🏍️ Mengemudi WASD ke tujuan ${sisa}...`;
        return;
      }

      // 2e. Jika ada perjalanan yang sedang berlangsung (Mode Otomatis progress bar)
      const progressBars = document.querySelectorAll('[role="progressbar"]');
      if (progressBars.length > 0) {
        ojolStats.phase = "DRIVING";
        ojolStats.statusMessage = "🚗 Sedang dalam perjalanan (Menjemput / Mengantar)...";
        return;
      }

      // 3. Jika IDLE: Matikan kemudi autopilot jika masih aktif
      setAutopilot(false);

      // 3. Jika IDLE: Periksa apakah lembar Ojol terbuka
      const modeContainer = document.querySelector('[data-testid="ojol-mode"]');
      const cariBtn = document.querySelector('[data-testid="ojol-cari"]');
      const pilihanContainer = document.querySelector('[data-testid="ojol-pilihan"]');

      if (!modeContainer && !cariBtn && !pilihanContainer) {
        // Sheet ojol belum terbuka, buka otomatis
        openOjolSheet();
        await new Promise(r => setTimeout(r, 650));
        return;
      }

      // 3a. Pastikan mode "Kendarai" dipilih (Versi Ekstensi Khusus Kendarai)
      if (modeContainer) {
        const modeBtns = Array.from(modeContainer.querySelectorAll("button"));
        const targetBtn = modeBtns.find(b => b.textContent && b.textContent.includes("Kendarai"));
        if (targetBtn && targetBtn.getAttribute("aria-pressed") !== "true") {
          addLog("🎯 Memilih mode 'Kendarai' (Narik Tanpa Batas 14 Jam)");
          dispatchHumanClick(targetBtn);
          await new Promise(r => setTimeout(r, humanJitter(300, 500)));
          return;
        }
      }

      // 3b. Pilih order terbaik dari tawaran yang tersedia
      if (pilihanContainer) {
        const items = Array.from(pilihanContainer.querySelectorAll('[data-testid="ojol-pilihan-item"]'));
        if (items.length > 0) {
          ojolStats.phase = "SELECTING";
          ojolStats.statusMessage = `📋 Menilai ${items.length} tawaran order...`;

          const parsedOrders = items.map((item, idx) => {
            const parsed = parseOrderCardText(item.textContent || "");
            const btn = item.querySelector("button");
            return {
              elem: item,
              button: btn,
              fareMilli: parsed.fareMilli,
              distance: parsed.distance,
              warga: parsed.isWarga,
              index: idx,
              text: item.textContent
            };
          });

          const best = evaluateOrders(parsedOrders, {
            strategy: ojolConfig.strategy || "time_efficiency",
            preferWarga: ojolConfig.preferWarga,
            maxDistance: ojolConfig.maxDistance || 30
          });
          if (best && best.button && !best.button.disabled) {
            ojolStats.lastFare = best.fareMilli;
            const mPerPetak = Math.round(best.fareMilli / Math.max(1, best.distance));
            ojolStats.lastRoute = `${(best.fareMilli / 1000).toFixed(1)} koin (${best.distance} petak · ${mPerPetak} m/petak)${best.warga ? " · Warga" : ""}`;
            addLog(`⚡ Memilih order worth it: ${(best.fareMilli / 1000).toFixed(1)} koin (${best.distance} petak · ${mPerPetak} m/petak)${best.warga ? " [Warga]" : ""}`);
            dispatchHumanClick(best.button);
            await new Promise(r => setTimeout(r, humanJitter(600, 900)));
            return;
          }
        }
      }

      // 3c. Jika siap cari order: Klik "📲 Cari order"
      if (cariBtn && !cariBtn.disabled && cariBtn.offsetParent !== null) {
        const btnText = cariBtn.textContent || "";
        if (btnText.includes("Cari order") || btnText.includes("📲")) {
          ojolStats.phase = "SEARCHING";
          ojolStats.statusMessage = "🔍 Meminta tawaran order baru...";
          addLog("📲 Mencari order ojol (Mode Kendarai)...");
          dispatchHumanClick(cariBtn);
          await new Promise(r => setTimeout(r, humanJitter(700, 1100)));
          return;
        }
      }
    }

    // Inisialisasi saat DOM siap
    function init() {
      createHUD();
      setInterval(tickAutoOjol, 550);
    }

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", init);
    } else {
      init();
    }
  }

  return {
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
  };
});
