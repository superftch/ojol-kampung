// KampungSebelah - Diving Shell Opener (v1.0.0)
// Mesin status murni (tanpa DOM) untuk membuka kerang dengan benar dan memastikan hasilnya.
//
// Bukti dari bundle game (1j_v3n6k6p7js.js dan konfigurasi diving, 24-25 Nov 2026):
//   - Tombol "Buka kerang" hanya ada bila kerangDekat() != null, yaitu jarak game ke kerang
//     < jangkau_m (3.2) dengan titik kerang = (x, kerang.y + 0.3, z).
//   - Klik tombol: animasi buka_detik (3 s) lalu POST /api/diving {aksi:"kerang"}. Animasi
//     batal bila pemain menjauh lebih dari jangkau_m + 1.6.
//   - Server menolak buka bila terlalu cepat setelah kerang sebelumnya; game lalu menandai
//     hasil "gagal" dan kerang tetap belum dibuka.
//   - bukaKerang() dipanggil langsung hanya memutar animasi, tanpa POST. Itu bukan membuka.
// Karena itu "tiba" harus diukur dengan rumus jarak game, dan "terbuka" hanya sah bila
// kerang.dibuka benar-benar menjadi true.

(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  if (typeof globalThis !== "undefined") {
    globalThis.__KS_DIVING_OPEN = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  const CFG = {
    jangkau: 3.2,            // jangkau_m game
    arriveDist: 2.7,         // jarak game yang dianggap tiba (margin 0.5 m dari jangkau)
    inRangeDist: 3.05,       // masih boleh klik bila jarak game di bawah ini
    buttonWaitMs: 2500,      // tunggu tombol muncul setelah tiba
    openTimeoutMs: 12000,    // dari klik sampai kerang.dibuka (3 s animasi + POST)
    failGraceMs: 800,        // tombol tidak sibuk lagi tapi belum terbuka: gagal setelah ini
    noBusyMs: 2000,          // klik tidak membuat tombol sibuk: dianggap diabaikan
    maxAttempts: 3,
    maxReapproach: 6,
    retryDelay: [3500, 6500], // tunggu sebelum klik ulang (server menolak bila terlalu cepat)
    settle: [400, 2200]       // jeda setelah tiba sebelum klik (ms)
  };

  function range(rng, [a, b]) { return a + (b - a) * Math.pow(rng(), 1.6); }

  /** Jarak 3D persis seperti kerangDekat() di game. */
  function gameDistance(p, k, item) {
    return Math.hypot(k.x - p.x, item.y + 0.3 - p.y, k.z - p.z);
  }

  /**
   * Target untuk navigator agar jarak 3D-nya sama dengan jarak game.
   * Navigator memakai titik y = -(d + 0.35); game memakai item.y + 0.3.
   */
  function toNavTarget(target, item) {
    if (!item || typeof item.y !== "number") return target;
    return Object.assign({}, target, { d: -item.y - 0.65 });
  }

  function createOpener(opts) {
    const o = opts || {};
    const rng = typeof o.rng === "function" ? o.rng : Math.random;
    const cfg = Object.assign({}, CFG, o.cfg || {});
    let s = null;

    function begin(now, index) {
      s = {
        index, state: "settle", enteredAt: now,
        settleUntil: now + range(rng, cfg.settle),
        attempts: 0, reapproach: 0,
        clickedAt: 0, sawBusy: false, notBusySince: 0,
        done: false
      };
    }

    function reapproach(now, reason) {
      s.reapproach++;
      if (s.reapproach > cfg.maxReapproach) return fail("unreachable", reason);
      s.state = "settle";
      s.enteredAt = now;
      s.settleUntil = now + range(rng, cfg.settle);
      return { type: "reapproach", reason };
    }

    function fail(reason, detail) {
      s.done = true;
      return { type: "fail", reason, detail };
    }

    function attemptFailed(now, why) {
      if (s.attempts >= cfg.maxAttempts) return fail("open_failed", why);
      s.state = "backoff";
      s.enteredAt = now;
      s.settleUntil = now + range(rng, cfg.retryDelay) * s.attempts;
      return { type: "wait", reason: "backoff:" + why };
    }

    /**
     * Dipanggil tiap tick (~50 ms) selama fase buka.
     * env: { dist: jarak game ke kerang, buttonReady: bool, busy: bool, opened: bool }
     * Hasil: { type: "wait" | "click" | "reapproach" | "success" | "fail", reason? }
     */
    function tick(now, env) {
      if (!s) throw new Error("begin() belum dipanggil");
      if (s.done) return { type: "wait", reason: "done" };

      // Sah hanya bila game sendiri menandai kerang terbuka.
      if (env.opened) {
        s.done = true;
        return { type: "success", attempts: s.attempts };
      }

      if (s.state === "opening") {
        if (env.busy) { s.sawBusy = true; s.notBusySince = 0; }
        else if (!s.notBusySince) s.notBusySince = now;
        if (now - s.clickedAt > cfg.openTimeoutMs) return attemptFailed(now, "timeout");
        if (!s.sawBusy && now - s.clickedAt > cfg.noBusyMs) return attemptFailed(now, "click_ignored");
        if (s.sawBusy && s.notBusySince && now - s.notBusySince > cfg.failGraceMs) {
          return attemptFailed(now, "rejected");
        }
        return { type: "wait", reason: "opening" };
      }

      if (env.dist > cfg.inRangeDist) return reapproach(now, "out_of_range");

      if (s.state === "settle" || s.state === "backoff") {
        if (now < s.settleUntil) return { type: "wait", reason: s.state };
        s.state = "ready";
        s.enteredAt = now;
      }

      if (s.state === "ready") {
        if (!env.buttonReady) {
          if (now - s.enteredAt > cfg.buttonWaitMs) return reapproach(now, "no_button");
          return { type: "wait", reason: "button" };
        }
        s.state = "opening";
        s.attempts++;
        s.clickedAt = now;
        s.sawBusy = false;
        s.notBusySince = 0;
        return { type: "click", attempt: s.attempts };
      }

      return { type: "wait", reason: s.state };
    }

    // Dipanggil saat pemain tiba lagi setelah aksi "reapproach". Hitungan percobaan dan
    // pendekatan ulang dipertahankan, supaya kerang yang tidak bisa dibuka tetap berakhir.
    function resume(now) {
      if (!s || s.done) return;
      s.state = "settle";
      s.enteredAt = now;
      s.settleUntil = now + range(rng, cfg.settle);
    }

    return {
      begin, tick, resume,
      get state() { return s; }
    };
  }

  return { CFG, createOpener, gameDistance, toNavTarget };
});
