import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
await import(path.resolve(__dirname, "../diving-route.js"));
const R = globalThis.__KS_DIVING_ROUTE;

function shell(i, x, z, d, kategori) {
  return { i, x, z, d, kategori };
}

const startPos = { x: 0, z: -26, d: 0.9 };

test("diving-route: mode 'langka' hanya memilih kerang 300 dan mengoptimalkan rute", () => {
  const shells = [
    shell(1, 0, -50, 20, "biasa"),
    shell(2, 200, -450, 45, "langka"),
    shell(3, 10, -400, 42, "langka"),
    shell(4, 15, -410, 44, "langka"),
    shell(5, 5, -30, 6, "kosong")
  ];
  const res = R.planRoute({ mode: "langka", startPos, shells });
  assert.equal(res.order.length, 3);
  assert.ok(res.order.every((k) => k.kategori === "langka"));
  // Dari z=-26, harus ke cluster (10,-400) & (15,-410) dulu sebelum ke (200,-450)
  assert.equal(res.order[2].i, 2);
});

test("diving-route: mode 'prioritas_300' mendahulukan semua kerang 300 sebelum kerang 100", () => {
  const shells = [
    shell(1, 0, -60, 22, "biasa"),     // dekat start, tapi 100 koin
    shell(2, 20, -450, 45, "langka"),  // jauh, tapi 300 koin
    shell(3, 30, -440, 46, "langka"),  // 300 koin
    shell(4, 35, -420, 25, "biasa"),   // 100 koin dekat cluster langka
    shell(5, 0, -35, 8, "kosong")      // kosong tidak boleh ikut
  ];
  const res = R.planRoute({ mode: "prioritas_300", startPos, shells });
  assert.equal(res.order.length, 4);
  assert.equal(res.order[0].kategori, "langka");
  assert.equal(res.order[1].kategori, "langka");
  assert.equal(res.order[2].kategori, "biasa");
  assert.equal(res.order[3].kategori, "biasa");
  // Setelah selesai di area langka (~z=-440..450), kerang biasa terdekat adalah #4 (-420), baru #1 (-60)
  assert.equal(res.order[2].i, 4);
  assert.equal(res.order[3].i, 1);
});

test("diving-route: mode 'potensial' mengambil 100 & 300 dengan jarak total <= greedy", () => {
  const shells = [
    shell(1, 0, -100, 22, "biasa"),
    shell(2, 100, -100, 24, "biasa"),
    shell(3, 100, -300, 42, "langka"),
    shell(4, 0, -300, 44, "langka"),
    shell(5, 5, -40, 5, "kosong")
  ];
  const res = R.planRoute({ mode: "potensial", startPos, shells });
  assert.equal(res.order.length, 4);
  assert.ok(res.order.every((k) => k.kategori === "biasa" || k.kategori === "langka"));
  // Bandingkan dengan urutan buruk [1, 3, 2, 4] (menyilang diagonal)
  const badDist = R.pathDistance(startPos, [shells[0], shells[2], shells[1], shells[3]]);
  assert.ok(res.totalDist < badDist, `totalDist (${res.totalDist}) harus lebih pendek dari rute silang (${badDist})`);
});

test("diving-route: mode 'all' mengikutkan semua kategori termasuk kosong", () => {
  const shells = [
    shell(1, 0, -40, 6, "kosong"),
    shell(2, 0, -120, 22, "biasa"),
    shell(3, 0, -420, 45, "langka")
  ];
  const res = R.planRoute({ mode: "all", startPos, shells });
  assert.deepEqual(res.order.map((k) => k.i), [1, 2, 3]);
});
