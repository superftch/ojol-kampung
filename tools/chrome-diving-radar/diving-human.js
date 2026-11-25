// KampungSebelah - Diving Human-like Behaviour (v1.0.0)
// Modul murni (tanpa DOM) agar Auto-Pilot Diving tidak bergerak seperti mesin:
//   - pilihan kerang berikutnya: tidak selalu yang terdekat, plus 1-2 kerang dangkal
//     (pasti kosong) per sesi pada urutan acak,
//   - jeda acak sebelum membuka kerang dan antar kerang,
//   - arah renang yang bergoyang halus, belok berkecepatan terbatas, berhenti sebentar
//     sambil menoleh.
// Tujuannya meniru pola, bukan menjamin lolos deteksi: apa yang diperiksa server belum
// terbukti. Perilaku keselamatan (hindari batu, anti-nyangkut) tidak diubah: motion
// hanya aktif saat jalur tenang (calm), dan menyerahkan arah apa adanya saat menghindar.

(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  if (typeof globalThis !== "undefined") {
    globalThis.__KS_DIVING_HUMAN = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  const CFG = {
    topWeights: [0.6, 0.25, 0.15], // peluang memilih kerang terdekat ke-1, ke-2, ke-3
    shallowMin: 1,                 // jumlah kerang dangkal per sesi
    shallowMax: 2,
    shallowAfterMin: 0,            // jumlah kerang utama sebelum tiap kerang dangkal
    shallowAfterMax: 6,
    sessionIdleMs: 35 * 60 * 1000, // diam selama ini = sesi baru
    arrivalDelay: [400, 2200],     // jeda setelah tiba sebelum membuka kerang (ms)
    chainGap: [2500, 7000],        // jeda setelah membuka sampai menuju kerang berikut (ms)
    pauseEvery: [8000, 25000],     // jarak antar jeda di jalan (ms)
    pauseLen: [600, 2200],         // lama jeda di jalan (ms)
    pauseLook: 0.6,                // simpangan menoleh saat jeda (rad)
    lookRate: 1.2,                 // laju menoleh saat jeda (rad/detik)
    wanderAmp: 0.1,                // simpangan arah renang (rad)
    turnRate: 3.0,                 // batas laju belok saat jalur tenang (rad/detik)
    nearTargetDist: 6              // di bawah jarak ini tanpa goyang/jeda
  };

  function wrapAngle(a) {
    while (a > Math.PI) a -= 2 * Math.PI;
    while (a <= -Math.PI) a += 2 * Math.PI;
    return a;
  }

  function range(rng, a, b) { return a + rng() * (b - a); }
  function int(rng, a, b) { return a + Math.floor(rng() * (b - a + 1)); }
  // Condong ke nilai kecil: lebih sering cepat, sesekali lama (seperti manusia).
  function skewed(rng, [a, b]) { return a + (b - a) * Math.pow(rng(), 1.6); }

  function dist3(player, k) {
    return Math.hypot(k.x - player.x, k.z - player.z, k.d - player.d);
  }

  function createHuman(opts) {
    const o = opts || {};
    const rng = typeof o.rng === "function" ? o.rng : Math.random;
    const cfg = Object.assign({}, CFG, o.cfg || {});

    let session = null;

    function newSession(now) {
      session = {
        startedAt: now,
        lastAt: now,
        shallowLeft: int(rng, cfg.shallowMin, cfg.shallowMax),
        nextShallowAfter: int(rng, cfg.shallowAfterMin, cfg.shallowAfterMax),
        mainSince: 0
      };
    }

    function nearest(list, player) {
      let best = null, bestD = Infinity;
      for (const k of list) {
        const d = dist3(player, k);
        if (d < bestD) { bestD = d; best = k; }
      }
      return best;
    }

    /**
     * @param {{primary: Array, shallow: Array, player: {x,z,d}, now?: number}} inp
     *   primary: kandidat utama (sudah disaring mode); shallow: kerang dangkal yang belum dibuka.
     * @returns kerang terpilih atau null bila kandidat utama habis.
     */
    function pickNext(inp) {
      const now = typeof inp.now === "number" ? inp.now : Date.now();
      const primary = Array.isArray(inp.primary) ? inp.primary : [];
      const shallow = Array.isArray(inp.shallow) ? inp.shallow : [];
      const player = inp.player;

      if (!session || now - session.lastAt > cfg.sessionIdleMs) newSession(now);
      session.lastAt = now;

      if (primary.length === 0) return null;

      if (session.shallowLeft > 0 && shallow.length > 0 && session.mainSince >= session.nextShallowAfter) {
        session.shallowLeft--;
        session.mainSince = 0;
        session.nextShallowAfter = int(rng, cfg.shallowAfterMin, cfg.shallowAfterMax);
        return nearest(shallow, player);
      }

      const sorted = primary.slice().sort((a, b) => dist3(player, a) - dist3(player, b));
      const n = Math.min(sorted.length, cfg.topWeights.length);
      let total = 0;
      for (let i = 0; i < n; i++) total += cfg.topWeights[i];
      let r = rng() * total;
      let idx = n - 1;
      for (let i = 0; i < n; i++) {
        r -= cfg.topWeights[i];
        if (r <= 0) { idx = i; break; }
      }
      session.mainSince++;
      return sorted[idx];
    }

    function arrivalDelayMs() { return Math.round(skewed(rng, cfg.arrivalDelay)); }
    function chainGapMs() { return Math.round(skewed(rng, cfg.chainGap)); }

    /**
     * Gerak renang yang tidak mekanis. Dipanggil tiap tick auto-pilot (~50 ms).
     * Alur per tick: bila `paused(now)`, panggil `hold(now)` lalu diam; selain itu panggil
     * `step()` dengan arah yang diinginkan navigator.
     */
    function createMotion() {
      const st = {
        yaw: null, last: 0,
        nextPauseAt: 0, pauseUntil: 0, look: 0,
        p1: rng() * 6.28, p2: rng() * 6.28, f1: range(rng, 1400, 2200), f2: range(rng, 3600, 5200)
      };

      function paused(now) { return now < st.pauseUntil; }

      function hold(now) {
        const dt = st.last ? Math.min(0.25, (now - st.last) / 1000) : 0;
        st.last = now;
        const lim = cfg.lookRate * dt;
        const diff = wrapAngle(st.look - st.yaw);
        st.yaw = wrapAngle(st.yaw + Math.max(-lim, Math.min(lim, diff)));
        return st.yaw;
      }

      /**
       * @param {{now:number, desiredYaw:number, calm:boolean, canPause:boolean, nearTarget:boolean}} inp
       * @returns {{yaw:number, startPause:boolean}}
       */
      function step(inp) {
        const { now, desiredYaw } = inp;
        const gapped = st.last && now - st.last > 500; // tab latar belakang: jangan langsung jeda
        if (st.yaw === null) {
          st.yaw = desiredYaw;
          st.nextPauseAt = now + skewed(rng, cfg.pauseEvery);
        }
        if (gapped) {
          st.pauseUntil = 0;
          st.nextPauseAt = Math.max(st.nextPauseAt, now + skewed(rng, cfg.pauseEvery));
        }
        const dt = st.last ? Math.min(0.25, (now - st.last) / 1000) : 0;
        st.last = now;

        // Menghindar, memulihkan, atau dekat batu: arah persis dari navigator, tanpa batas belok.
        if (!inp.calm) {
          st.yaw = desiredYaw;
          return { yaw: st.yaw, startPause: false };
        }

        if (inp.canPause && !inp.nearTarget && now >= st.nextPauseAt) {
          st.pauseUntil = now + skewed(rng, cfg.pauseLen);
          st.look = wrapAngle(st.yaw + range(rng, -cfg.pauseLook, cfg.pauseLook));
          st.nextPauseAt = st.pauseUntil + skewed(rng, cfg.pauseEvery);
          return { yaw: st.yaw, startPause: true };
        }

        const wander = inp.nearTarget ? 0 : cfg.wanderAmp * (
          0.6 * Math.sin(now / st.f1 + st.p1) + 0.4 * Math.sin(now / st.f2 + st.p2)
        );
        const diff = wrapAngle(desiredYaw + wander - st.yaw);
        const lim = cfg.turnRate * dt;
        st.yaw = wrapAngle(st.yaw + Math.max(-lim, Math.min(lim, diff)));
        return { yaw: st.yaw, startPause: false };
      }

      return { step, hold, paused, get state() { return st; } };
    }

    return {
      pickNext, arrivalDelayMs, chainGapMs, createMotion,
      resetSession() { session = null; },
      get session() { return session; }
    };
  }

  return { CFG, createHuman, wrapAngle };
});
