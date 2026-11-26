// KampungSebelah - Diving Shark Escape (v1.0.0)
// Mesin status murni (tanpa DOM) agar auto-pilot kabur dari hiu sebelum tertangkap.
//
// Bukti dari bundle game (1j_v3n6k6p7js.js, gerakHiu/keadaan) dan konfigurasi server, 26 Nov 2026:
//   - Hiu berpatroli tiap 8 menit selama 70-100 detik. 8 detik pertama ("awas") hiu belum memburu.
//   - Hiu memburu pemain hanya bila kedalaman (-y) > aman_m (6 m) dan jarak < lihat_m (45 m).
//     Di atas 6 m pemain tidak pernah menjadi target, dan hiu tidak bisa naik di atas -6 m.
//   - Laju hiu 2.5 m/s, 4.4 m/s saat menyergap. Laju renang pemain turun sampai 0.55x di kedalaman,
//     jadi hiu tidak bisa dikalahkan secara horizontal. Satu-satunya jalan aman: naik ke < 6 m.
//   - Indikator merah di HUD game ([data-testid="diving-hiu"][data-bahaya]) menyala bila
//     memburu, atau (tidak awas dan jarak < 45 m), dan pemain belum di zona aman.
// Kebijakan: begitu ada hiu dalam radius waspada (atau indikator merah menyala), naik penuh sambil
// menjauh dari hiu sampai kedalaman aman, tunggu di sana sampai hiu pergi, lalu lanjut.

(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  if (typeof globalThis !== "undefined") {
    globalThis.__KS_DIVING_SHARK = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  const CFG = {
    amanM: 6.0,            // aman_m game: -y di bawah ini = zona aman
    safeTo: 4.5,           // naik sampai -y <= ini (margin 1.5 m dari batas aman)
    holdLow: 3.0,          // saat bersembunyi, jaga -y di antara holdLow..holdHigh
    holdHigh: 5.0,
    engageDist: 70,        // waspada bila hiu lebih dekat dari ini (game memutar suara di 70 m)
    releaseDist: 100,      // lanjut hanya bila hiu lebih jauh dari ini (histeresis)
    releaseDelay: [1500, 4000], // jeda acak setelah aman sebelum lanjut (ms)
    maxHideMs: 150000      // patroli maks. 100 detik: jangan bersembunyi selamanya
  };

  /**
   * Penilaian ancaman.
   * hiu: null | { p:{x,y,z}, awas, memburu, sergap }  (null = tidak ada hiu aktif)
   * domDanger: indikator merah di HUD game menyala
   */
  function threat(pos, hiu, domDanger, cfg) {
    if (domDanger) return { on: true, dist: hiu ? dist3(pos, hiu.p) : null };
    if (!hiu) return { on: false, dist: null };
    const dist = dist3(pos, hiu.p);
    return { on: !!hiu.memburu || dist < cfg.engageDist, dist };
  }

  function dist3(a, b) {
    return Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);
  }

  function createShark(opts) {
    const o = opts || {};
    const rng = typeof o.rng === "function" ? o.rng : Math.random;
    const cfg = Object.assign({}, CFG, o.cfg || {});
    let st = { mode: "clear", since: 0, releaseAt: 0, fleeCount: 0, lastDist: null };

    function reset() {
      st = { mode: "clear", since: 0, releaseAt: 0, fleeCount: 0, lastDist: null };
    }

    /**
     * Dipanggil tiap tick. Hasil:
     *  { mode: "clear"|"flee"|"hide", event?: "flee_start"|"safe"|"resume"|"hide_timeout",
     *    awayYaw: number|null, dist: number|null }
     * mode "clear" berarti auto-pilot boleh berjalan normal.
     */
    function assess(inp) {
      const { now, pos, hiu, domDanger } = inp;
      const depth = -pos.y; // sama dengan penghitungan game: aman bila < amanM
      const th = threat(pos, hiu || null, !!domDanger, cfg);
      st.lastDist = th.dist;
      let awayYaw = null;
      if (hiu && hiu.p && (Math.abs(pos.x - hiu.p.x) > 0.05 || Math.abs(pos.z - hiu.p.z) > 0.05)) {
        awayYaw = Math.atan2(pos.x - hiu.p.x, pos.z - hiu.p.z);
      }
      let event;

      // Ancaman hilang hanya bila hiu pergi atau cukup jauh (histeresis), dan indikator mati.
      const calm = !domDanger && (!hiu || (!hiu.memburu && th.dist > cfg.releaseDist));

      if (st.mode === "clear") {
        if (th.on) {
          st.fleeCount++;
          st.since = now;
          if (depth > cfg.safeTo) {
            st.mode = "flee";
            event = "flee_start";
          } else {
            st.mode = "hide";
            st.releaseAt = 0;
            event = "safe";
          }
        }
      } else if (st.mode === "flee") {
        if (depth <= cfg.safeTo) {
          st.mode = "hide";
          st.releaseAt = 0;
          event = "safe";
        } else if (!hiu && !domDanger) {
          // Hiu sudah pergi saat kabur: tidak perlu naik terus.
          st.mode = "clear";
          event = "resume";
        }
      } else if (st.mode === "hide") {
        if (now - st.since > cfg.maxHideMs) {
          st.mode = "clear";
          event = "hide_timeout";
        } else if (!calm) {
          st.releaseAt = 0;
        } else if (!st.releaseAt) {
          const [a, b] = cfg.releaseDelay;
          st.releaseAt = now + a + (b - a) * rng();
        } else if (now >= st.releaseAt) {
          st.mode = "clear";
          event = "resume";
        }
        // Terdorong turun (arus, bobot) saat bersembunyi: kabur lagi bila hiu masih mengancam.
        if (st.mode === "hide" && depth > cfg.amanM && th.on) {
          st.mode = "flee";
          event = "flee_start";
        }
      }

      return { mode: st.mode, event, awayYaw, dist: th.dist, depth };
    }

    /** Masukan kemudi: naik penuh dan menjauh saat kabur, jaga kedalaman saat bersembunyi. */
    function steer(res) {
      if (res.mode === "flee") {
        return { tegak: 1, move: res.awayYaw !== null };
      }
      if (res.mode === "hide") {
        const d = res.depth;
        const tegak = d > cfg.holdHigh ? 1 : d < cfg.holdLow ? -1 : 0;
        return { tegak, move: false };
      }
      return null;
    }

    return {
      assess, steer, reset,
      get state() { return st; }
    };
  }

  return { CFG, createShark, threat };
});
