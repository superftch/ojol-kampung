// KampungSebelah - Diving Rock Avoidance Planner (v1.1.0)
// Perencana arah murni (tanpa DOM) untuk Auto-Pilot Diving agar tidak nyangkut di batu besar.
//
// Dasar (temuan statis dari bundle client 1j_v3n6k6p7js.js, 24 Nov 2026):
//   - Tabrakan pemain hanya dihitung terhadap `scene.dunia.batuBesar`: bola {x, y, z, r}.
//   - Pemain didorong keluar radial bila jarak < r + 0.45. Berenang lurus ke pusat bola
//     membuat dorongan keluar sama besar dengan laju maju, sehingga karakter diam di tempat.
//   - Dasar laut tidak memblokir: y pemain hanya dijepit ke `tinggi(x, z) + 0.55`.
//   - Penempatan dekor batu (bangunHiasan) tidak menghindari posisi kerang, jadi sebuah
//     kerang bisa berada di dalam atau tepat di balik bola batu.
// Asumsi yang belum diukur live: rasio laju naik/turun terhadap laju horizontal (`vRatio`).

(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  if (typeof globalThis !== "undefined") {
    globalThis.__KS_DIVING_AVOID = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  const PLAYER_R = 0.45; // sama dengan konstanta tabrakan game (r + 0.45)

  const DEFAULTS = {
    margin: 1.0,        // jarak aman ekstra di luar permukaan tabrakan (meter)
    lookahead: 14,      // panjang jalur yang diperiksa (meter)
    step: 0.7,          // langkah simulasi (meter)
    vRatio: 0.45,       // asumsi: laju vertikal (tegak=±1) / laju horizontal
    surfaceY: -0.15,    // batas atas posisi pemain (pen.apung)
    floorClear: 0.55,   // pemain dijepit ke tinggi dasar + 0.55
    holdBonus: 0.9,     // bobot hysteresis agar tidak bolak-balik
    arriveR: 2.8,       // jarak 3D ke kerang yang dihitung tiba
    wpMargin: 0.3,      // jarak aman titik berdiri dekat kerang dari permukaan tabrakan
    offsets: [0, 0.25, -0.25, 0.5, -0.5, 0.8, -0.8, 1.1, -1.1, 1.5, -1.5, 2.0, -2.0]
  };

  function wrapAngle(a) {
    while (a > Math.PI) a -= 2 * Math.PI;
    while (a <= -Math.PI) a += 2 * Math.PI;
    return a;
  }

  function dist3(ax, ay, az, b) {
    return Math.hypot(ax - b.x, ay - b.y, az - b.z);
  }

  function mergeOpts(opts) {
    const cfg = Object.assign({}, DEFAULTS);
    for (const k of Object.keys(opts || {})) {
      if (opts[k] !== undefined) cfg[k] = opts[k];
    }
    return cfg;
  }

  // Kecepatan melayang vertikal akibat pitch kamera (rumus gerakPemain di game).
  function pitchDrift(pitch) {
    const a = Math.sin((pitch || 0) + 0.18);
    const m = Math.abs(a) < 0.12 ? 0 : a - 0.12 * Math.sign(a);
    const d = Math.sqrt(Math.max(0.15, 1 - m * m));
    return m / d;
  }

  function baseTegak(pos, target, band) {
    const b = typeof band === "number" ? band : 1.0;
    const dd = target.y - pos.y; // y dunia: lebih besar = lebih dangkal
    if (dd < -b) return -1;      // target lebih dalam -> turun
    if (dd > b) return 1;        // target lebih dangkal -> naik
    return 0;
  }

  // Simulasikan jalur. Hasil: { clear, steps, minClear, endDist }
  function simulate(pos, yaw, tegak, rocks, thresholds, target, cfg, drift, floorFn) {
    const steps = cfg.nSteps;
    const sx = Math.sin(yaw) * cfg.step;
    const sz = Math.cos(yaw) * cfg.step;
    const vy = (tegak * cfg.vRatio + drift) * cfg.step;
    let x = pos.x, y = pos.y, z = pos.z;
    let minClear = Infinity;
    for (let k = 1; k <= steps; k++) {
      x += sx; z += sz; y += vy;
      if (y > cfg.surfaceY) y = cfg.surfaceY;
      if (floorFn) {
        const f = floorFn(x, z) + cfg.floorClear;
        if (y < f) y = f;
      }
      for (let i = 0; i < rocks.length; i++) {
        const r = rocks[i];
        const d = Math.hypot(x - r.x, y - r.y, z - r.z);
        const clear = d - thresholds[i];
        if (clear < minClear) minClear = clear;
        if (clear < 0) {
          return { clear: false, steps: k - 1, minClear, endDist: Infinity };
        }
      }
    }
    const endDist = target ? Math.hypot(target.x - x, target.z - z, (target.y - y) * 0.5) : 0;
    return { clear: true, steps, minClear, endDist };
  }

  /**
   * @param {{x,y,z}} pos    posisi pemain (sc.p)
   * @param {{x,y,z}} target titik tuju dalam y dunia (kerang atau waypoint)
   * @param {Array<{x,y,z,r}>} rocks sc.dunia.batuBesar
   * @param {object} [opts]  { pitch, prevOffset, floorFn, ...DEFAULTS }
   * @returns {{yaw, tegak, offset, avoiding, blocked, rock}}
   */
  function planSteering(pos, target, rocks, opts) {
    const cfg = mergeOpts(opts);
    const bearing = Math.atan2(target.x - pos.x, target.z - pos.z);
    const distXZ = Math.hypot(target.x - pos.x, target.z - pos.z);
    const prevOffset = cfg.prevOffset || 0;
    const t0 = baseTegak(pos, target, cfg.vBand);
    const drift = pitchDrift(cfg.pitch);

    const reach = Math.max(2, Math.min(cfg.lookahead, distXZ + 0.3));
    cfg.nSteps = Math.max(3, Math.ceil(reach / cfg.step));

    // Saring batu yang mungkin terkena.
    const near = [];
    const thresholds = [];
    let nearest = null;
    let nearestD = Infinity;
    const list = Array.isArray(rocks) ? rocks : [];
    for (let i = 0; i < list.length; i++) {
      const r = list[i];
      if (!r || typeof r.x !== "number") continue;
      const safe = r.r + PLAYER_R + cfg.margin;
      const hd = Math.hypot(r.x - pos.x, r.z - pos.z);
      if (hd > reach + safe + 2) continue;
      const d0 = dist3(pos.x, pos.y, pos.z, r);
      // Sudah di dalam zona aman: jangan hitung sebagai tabrakan kecuali makin mendekat.
      near.push(r);
      thresholds.push(d0 >= safe + 0.05 ? safe : Math.max(r.r + PLAYER_R, d0 - 0.05));
      if (d0 < nearestD) { nearestD = d0; nearest = r; }
    }

    if (near.length === 0) {
      return { yaw: wrapAngle(bearing), tegak: t0, offset: 0, avoiding: false, blocked: false, rock: null };
    }

    const tegakOptions = [t0];
    for (const t of [1, -1, 0]) if (!tegakOptions.includes(t)) tegakOptions.push(t);

    let best = null;
    let fallback = null;
    for (const o of cfg.offsets) {
      for (let ti = 0; ti < tegakOptions.length; ti++) {
        const tegak = tegakOptions[ti];
        const yaw = wrapAngle(bearing + o);
        const sim = simulate(pos, yaw, tegak, near, thresholds, target, cfg, drift, cfg.floorFn);
        if (sim.clear) {
          const cost =
            Math.abs(o) * 1.0 +
            Math.abs(o - prevOffset) * cfg.holdBonus * (prevOffset !== 0 ? 1 : 0) +
            (ti === 0 ? 0 : 0.35 + 0.1 * ti) +
            0.02 * sim.endDist;
          if (!best || cost < best.cost) best = { cost, yaw, tegak, offset: o };
        } else {
          const score = sim.steps + Math.max(0, sim.minClear) * 0.1 - Math.abs(o) * 0.05;
          if (!fallback || score > fallback.score) fallback = { score, yaw, tegak, offset: o };
        }
      }
    }

    const chosen = best || fallback;
    return {
      yaw: chosen.yaw,
      tegak: chosen.tegak,
      offset: chosen.offset,
      avoiding: chosen.offset !== 0 || chosen.tegak !== t0,
      blocked: !best,
      rock: nearest
    };
  }

  /**
   * Titik berdiri dekat kerang yang bebas dari zona batu. Kerang bisa berada di dalam
   * atau tepat di balik bola batu, sehingga mengarah ke kerang itu sendiri membuat
   * pemain berputar tanpa pernah tiba. Mengembalikan null bila kerang tidak terhalang
   * batu manapun, atau bila tidak ada titik yang layak.
   */
  function findApproachPoint(pos, target, rocks, opts) {
    const cfg = mergeOpts(opts);
    const list = (Array.isArray(rocks) ? rocks : []).filter(r => r && typeof r.x === "number");
    const around = list.filter(
      r => dist3(target.x, target.y, target.z, r) < r.r + PLAYER_R + cfg.wpMargin + cfg.arriveR
    );
    if (around.length === 0) return null;

    const rings = [0.8, 1.3, 1.8, 2.2, 2.5, cfg.arriveR - 0.1];
    const elevs = [0, 0.4, -0.4, 0.8, -0.8, 1.2, -1.2];
    const AZ = 24;
    // Margin normal dulu; bila tidak ada titik layak (kerang menempel dalam di batu),
    // coba margin nyaris nol: berdiri tepat di permukaan tabrakan masih dalam jangkauan buka.
    for (const margin of [cfg.wpMargin, 0.05]) {
      let best = null;
      for (const rho of rings) {
        for (const el of elevs) {
          for (let k = 0; k < AZ; k++) {
            const az = (k / AZ) * 2 * Math.PI;
            const q = {
              x: target.x + rho * Math.cos(el) * Math.sin(az),
              y: target.y + rho * Math.sin(el),
              z: target.z + rho * Math.cos(el) * Math.cos(az)
            };
            if (q.y > cfg.surfaceY) continue;
            if (cfg.floorFn && q.y < cfg.floorFn(q.x, q.z) + cfg.floorClear) continue;
            let ok = true;
            for (const r of list) {
              if (dist3(q.x, q.y, q.z, r) < r.r + PLAYER_R + margin) { ok = false; break; }
            }
            if (!ok) continue;
            const cost = dist3(q.x, q.y, q.z, pos) + rho * 1.5;
            if (!best || cost < best.cost) best = { cost, x: q.x, y: q.y, z: q.z };
          }
        }
      }
      if (best) return { x: best.x, y: best.y, z: best.z };
    }
    return null;
  }

  const NAV = {
    arriveR: 2.8,
    wpMargin: 0.3,
    nearMargin: 0.3,       // margin dekat target atau saat melonggar
    nearDist: 8,           // di bawah jarak ini margin diperkecil
    stuckWindowMs: 700,
    stuckMinMove: 0.35,
    stuckMaxLevel: 5,      // batas tingkat pemulihan (tidak menghentikan auto-pilot)
    gapMs: 500,            // jeda antar tick di atas ini dianggap tab di latar belakang
    noProgressMs: 12000,    // tidak mendekat >= noProgressGain selama ini -> naik tingkat pelonggaran
    noProgressGain: 1.0,
    maxRelax: 3
  };

  /**
   * Navigator berstatus untuk satu sesi auto-pilot: waypoint, deteksi nyangkut,
   * pemulihan, dan watchdog kemajuan. `step()` dipanggil tiap tick (50 ms).
   * Hasil: { yaw, tegak, gerak: {x,y}, mode, stop }
   *   mode: none | avoid | blocked | recover | direct
   *   stop: null | "no_progress" (hanya bila target tidak mendekat lama)
   * Tingkat pelonggaran (relax): 0 normal, 1 margin kecil, 2 berenang lurus (tabrakan
   * game hanya menggeser pemain di permukaan batu), 3 berhenti "no_progress".
   */
  function createNavigator(userCfg) {
    const nc = Object.assign({}, NAV, userCfg || {});
    let st;
    function reset() {
      st = {
        targetId: null, wp: undefined,
        prevOffset: 0,
        sampleAt: 0, sx: 0, sy: 0, sz: 0,
        lastStepAt: 0,
        stuckLevel: 0, recoverUntil: 0, recoverStart: 0, recoverSide: 1,
        bestDist: Infinity, bestAt: 0, relax: 0
      };
    }
    reset();

    function step(inp) {
      const { now, pos, target, rocks } = inp;
      const tp = { x: target.x, y: -(target.d + 0.35), z: target.z };
      const dist3d = dist3(pos.x, pos.y, pos.z, tp);
      const bearing = Math.atan2(tp.x - pos.x, tp.z - pos.z);
      // Dekat target pita kedalaman dipersempit: pita 1 m + titik berdiri 2.7 m bisa
      // membuat jarak 3D tetap > 2.8 m dan karakter diam di luar jangkauan buka.
      const vBand = dist3d < nc.nearDist ? 0.3 : 1.0;
      const t0 = baseTegak(pos, tp, vBand);
      const planOpts = {
        vBand,
        pitch: inp.pitch, surfaceY: inp.surfaceY, floorFn: inp.floorFn,
        arriveR: nc.arriveR, wpMargin: nc.wpMargin
      };

      if (st.targetId !== target.i) {
        reset();
        st.targetId = target.i;
      }

      // Jeda panjang antar tick = tab di latar belakang (timer ditahan, game berhenti
      // menggerakkan karakter). Posisi yang diam saat itu bukan nyangkut: ukur ulang.
      if (st.lastStepAt && now - st.lastStepAt > nc.gapMs) {
        st.sampleAt = 0;
        st.bestAt = 0;
        st.recoverUntil = 0;
      }
      st.lastStepAt = now;

      // Watchdog kemajuan: tidak mendekat -> longgarkan, akhirnya berhenti (oksigen terbatas).
      if (st.bestAt === 0 || dist3d < st.bestDist - nc.noProgressGain) {
        st.bestDist = dist3d; st.bestAt = now;
      } else if (now - st.bestAt > nc.noProgressMs) {
        st.relax++;
        st.bestAt = now; st.bestDist = dist3d;
        st.wp = undefined;
        if (st.relax >= nc.maxRelax) {
          return { yaw: bearing, tegak: 0, gerak: { x: 0, y: 0 }, mode: "none", stop: "no_progress", relax: st.relax };
        }
      }

      // Pemulihan terjadwal setelah nyangkut.
      if (now < st.recoverUntil) {
        const back = now - st.recoverStart < 500;
        st.sampleAt = 0;
        return {
          yaw: bearing,
          tegak: st.stuckLevel >= 2 ? 1 : t0,
          gerak: { x: back ? 0 : st.recoverSide, y: back ? -1 : 0.6 },
          mode: "recover", stop: null, relax: st.relax
        };
      }

      // Deteksi nyangkut.
      if (st.sampleAt === 0) {
        st.sampleAt = now; st.sx = pos.x; st.sy = pos.y; st.sz = pos.z;
      } else if (now - st.sampleAt >= nc.stuckWindowMs) {
        const moved = Math.hypot(pos.x - st.sx, pos.y - st.sy, pos.z - st.sz);
        if (moved < nc.stuckMinMove) {
          // Tidak pernah berhenti sendiri karena nyangkut: pemulihan makin lama dan
          // berganti sisi. Yang berhenti hanya watchdog kemajuan (target mustahil).
          st.stuckLevel = Math.min(st.stuckLevel + 1, nc.stuckMaxLevel);
          st.recoverSide = st.recoverSide > 0 ? -1 : 1;
          st.prevOffset = st.recoverSide * 0.8;
          st.recoverStart = now;
          st.recoverUntil = now + 1400 + 400 * (st.stuckLevel - 1);
        } else {
          st.stuckLevel = 0;
        }
        st.sampleAt = now; st.sx = pos.x; st.sy = pos.y; st.sz = pos.z;
      }

      const list = Array.isArray(rocks) ? rocks : [];
      if (list.length === 0 || st.relax >= 2) {
        return {
          yaw: bearing, tegak: t0, gerak: { x: 0, y: 1 },
          mode: list.length ? "direct" : "none", stop: null, relax: st.relax
        };
      }

      // Waypoint di luar zona batu bila kerang terkurung batu (dihitung sekali per target).
      if (st.wp === undefined) {
        st.wp = findApproachPoint(pos, tp, list, planOpts);
      }
      const aim = st.wp || tp;
      const distAim = dist3(pos.x, pos.y, pos.z, aim);
      const margin = st.relax >= 1 || distAim < nc.nearDist ? nc.nearMargin : DEFAULTS.margin;
      const plan = planSteering(pos, aim, list, Object.assign({}, planOpts, {
        prevOffset: st.prevOffset, margin
      }));
      st.prevOffset = plan.offset;
      return {
        yaw: plan.yaw, tegak: plan.tegak, gerak: { x: 0, y: 1 },
        mode: plan.blocked ? "blocked" : (plan.avoiding ? "avoid" : "none"), stop: null,
        waypoint: st.wp || null, relax: st.relax
      };
    }

    // Dipanggil tiap tick saat karakter sengaja diam (jeda "manusia"): posisi yang tidak
    // berubah bukan nyangkut, dan waktu jeda tidak dihitung sebagai tanpa kemajuan.
    function hold(now) {
      if (st.lastStepAt && st.bestAt) st.bestAt += Math.max(0, now - st.lastStepAt);
      st.lastStepAt = now;
      st.sampleAt = 0;
    }

    return { step, hold, reset, get state() { return st; } };
  }

  return {
    PLAYER_R, DEFAULTS, NAV,
    planSteering, findApproachPoint, createNavigator, pitchDrift, wrapAngle
  };
});
