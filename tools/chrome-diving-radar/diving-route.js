// KampungSebelah - Diving Optimal Route Planner (v1.0.0)
// Modul murni (tanpa DOM) untuk menghitung rute kerang paling optimal (Nearest-Neighbor + 2-opt)
// berdasarkan mode yang dipilih:
//   - "langka"        : hanya kerang 300 koin (>= 40m)
//   - "prioritas_300" : semua kerang potensi (100 & 300), tapi semua kerang 300 didahulukan
//   - "potensial"     : semua kerang potensi terdekat (100 & 300 optimal 1 sesi)
//   - "all"           : semua kerang terdekat (termasuk dangkal/kosong)

(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  if (typeof globalThis !== "undefined") {
    globalThis.__KS_DIVING_ROUTE = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  function dist3(a, b) {
    const ad = typeof a.d === "number" ? a.d : (typeof a.kedalaman === "number" ? a.kedalaman : 0);
    const bd = typeof b.d === "number" ? b.d : (typeof b.kedalaman === "number" ? b.kedalaman : 0);
    return Math.hypot((a.x || 0) - (b.x || 0), (a.z || 0) - (b.z || 0), ad - bd);
  }

  function pathDistance(startPos, tour) {
    if (!tour || tour.length === 0) return 0;
    let total = dist3(startPos, tour[0]);
    for (let i = 0; i < tour.length - 1; i++) {
      total += dist3(tour[i], tour[i + 1]);
    }
    return total;
  }

  function nearestNeighbor(startPos, shells, firstIdx) {
    const n = shells.length;
    const used = new Uint8Array(n);
    const tour = [];
    let cur = startPos;

    if (typeof firstIdx === "number" && firstIdx >= 0 && firstIdx < n) {
      used[firstIdx] = 1;
      tour.push(shells[firstIdx]);
      cur = shells[firstIdx];
    }

    while (tour.length < n) {
      let bestIdx = -1;
      let bestDist = Infinity;
      for (let i = 0; i < n; i++) {
        if (used[i]) continue;
        const d = dist3(cur, shells[i]);
        if (d < bestDist) {
          bestDist = d;
          bestIdx = i;
        }
      }
      if (bestIdx === -1) break;
      used[bestIdx] = 1;
      tour.push(shells[bestIdx]);
      cur = shells[bestIdx];
    }
    return tour;
  }

  // Open-ended 2-opt: memperbaiki urutan tur dengan membalik segmen [i..j] jika memperpendek total jarak.
  function twoOpt(startPos, initialTour, maxPasses = 120) {
    const tour = initialTour.slice();
    const n = tour.length;
    if (n <= 2) return tour;

    for (let pass = 0; pass < maxPasses; pass++) {
      let improved = false;
      for (let i = 0; i < n - 1; i++) {
        const prev = i === 0 ? startPos : tour[i - 1];
        for (let j = i + 1; j < n; j++) {
          const next = j + 1 < n ? tour[j + 1] : null;
          const before = dist3(prev, tour[i]) + (next ? dist3(tour[j], next) : 0);
          const after = dist3(prev, tour[j]) + (next ? dist3(tour[i], next) : 0);
          if (after < before - 1e-6) {
            let l = i;
            let r = j;
            while (l < r) {
              const tmp = tour[l];
              tour[l] = tour[r];
              tour[r] = tmp;
              l++;
              r--;
            }
            improved = true;
          }
        }
      }
      if (!improved) break;
    }
    return tour;
  }

  function solveTSP(startPos, shells) {
    if (!Array.isArray(shells) || shells.length === 0) {
      return { order: [], totalDist: 0 };
    }
    if (shells.length === 1) {
      return { order: [shells[0]], totalDist: dist3(startPos, shells[0]) };
    }

    // Coba mulai dari beberapa kandidat terdekat ke startPos agar tidak terjebak greedy lokal.
    const ranked = shells
      .map((s, idx) => ({ idx, d: dist3(startPos, s) }))
      .sort((a, b) => a.d - b.d);
    const seeds = ranked.slice(0, Math.min(4, ranked.length)).map((r) => r.idx);

    let bestOrder = null;
    let bestDist = Infinity;
    for (const seedIdx of seeds) {
      const nn = nearestNeighbor(startPos, shells, seedIdx);
      const opt = twoOpt(startPos, nn);
      const d = pathDistance(startPos, opt);
      if (d < bestDist) {
        bestDist = d;
        bestOrder = opt;
      }
    }

    return { order: bestOrder || [], totalDist: bestDist };
  }

  /**
   * Hitung rute kerang paling optimal sesuai mode.
   * @param {{ mode: string, startPos: {x:number, z:number, d?:number, kedalaman?:number}, shells: Array }} opts
   * @returns {{ mode: string, order: Array, totalDist: number }}
   */
  function planRoute(opts) {
    const o = opts || {};
    const mode = o.mode || "langka";
    const startPos = o.startPos || { x: 0, z: -26, d: 0.9 };
    const shells = Array.isArray(o.shells) ? o.shells : [];

    if (mode === "langka") {
      const langka = shells.filter((k) => k.kategori === "langka");
      const res = solveTSP(startPos, langka);
      return { mode, order: res.order, totalDist: res.totalDist };
    }

    if (mode === "prioritas_300") {
      const langka = shells.filter((k) => k.kategori === "langka");
      const biasa = shells.filter((k) => k.kategori === "biasa");
      const r1 = solveTSP(startPos, langka);
      const midPos = r1.order.length > 0 ? r1.order[r1.order.length - 1] : startPos;
      const r2 = solveTSP(midPos, biasa);
      return {
        mode,
        order: r1.order.concat(r2.order),
        totalDist: r1.totalDist + r2.totalDist
      };
    }

    if (mode === "potensial") {
      const pot = shells.filter((k) => k.kategori === "biasa" || k.kategori === "langka");
      const res = solveTSP(startPos, pot);
      return { mode, order: res.order, totalDist: res.totalDist };
    }

    // "all": semua kerang terdekat
    const res = solveTSP(startPos, shells);
    return { mode: "all", order: res.order, totalDist: res.totalDist };
  }

  return { dist3, pathDistance, solveTSP, planRoute };
});
