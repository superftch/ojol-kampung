import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
await import(path.resolve(__dirname, "../diving-open.js"));
await import(path.resolve(__dirname, "../diving-avoid.js"));
const O = globalThis.__KS_DIVING_OPEN;

function seeded(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Game palsu: tombol, animasi buka 3 detik, lalu POST yang bisa ditolak server.
function fakeGame(o = {}) {
  const g = {
    dist: o.dist ?? 2.0,
    rejectsLeft: o.rejects ?? 0,
    ignoreClicks: !!o.ignoreClicks,
    noButton: !!o.noButton,
    busy: false, opened: !!o.opened, busyUntil: 0, postOk: false,
    clicks: []
  };
  g.env = (now) => {
    if (g.busy && now >= g.busyUntil) {
      g.busy = false;
      if (g.postOk) g.opened = true;
    }
    return {
      dist: g.dist,
      busy: g.busy,
      opened: g.opened,
      buttonReady: !g.noButton && !g.busy && !g.opened && g.dist < O.CFG.jangkau
    };
  };
  g.click = (now) => {
    g.clicks.push(now);
    if (g.ignoreClicks) return;
    g.busy = true;
    g.busyUntil = now + 3300;
    if (g.rejectsLeft > 0) { g.rejectsLeft--; g.postOk = false; } else { g.postOk = true; }
  };
  return g;
}

function run(game, seed = 1, maxMs = 120000, hooks = {}) {
  const op = O.createOpener({ rng: seeded(seed) });
  let t = 1000;
  op.begin(t, 7);
  const events = [];
  let swimming = false;
  while (t < 1000 + maxMs) {
    t += 50;
    if (hooks.beforeTick) hooks.beforeTick(t, game);
    // Saat "reapproach" pemanggil berenang lagi dan tidak memanggil tick sampai tiba.
    if (swimming) {
      if (game.dist <= O.CFG.arriveDist) { swimming = false; op.resume(t); }
      continue;
    }
    const a = op.tick(t, game.env(t));
    if (a.type === "click") game.click(t);
    if (a.type === "reapproach") swimming = true;
    if (a.type !== "wait") events.push({ t, ...a });
    if (a.type === "success" || a.type === "fail") return { a, events, t, op };
  }
  return { a: null, events, t, op };
}

test("gameDistance memakai rumus kerangDekat game", () => {
  const d = O.gameDistance({ x: 0, y: -10, z: 0 }, { x: 3, z: 4 }, { y: -9.7 });
  assert.ok(Math.abs(d - Math.hypot(3, -9.7 + 0.3 + 10, 4)) < 1e-9);
});

test("toNavTarget: titik navigator sama dengan titik kerang di game", () => {
  const item = { y: -33.4 };
  const nt = O.toNavTarget({ i: 1, x: 5, z: 6, d: 33.9 }, item);
  assert.ok(Math.abs(-(nt.d + 0.35) - (item.y + 0.3)) < 1e-9);
  assert.equal(nt.i, 1);
  assert.deepEqual(O.toNavTarget({ i: 1, x: 5, z: 6, d: 33.9 }, null), { i: 1, x: 5, z: 6, d: 33.9 });
});

test("sukses di percobaan pertama: satu klik, jeda sebelum klik, sukses setelah dibuka", () => {
  const g = fakeGame();
  const r = run(g);
  assert.equal(r.a.type, "success");
  assert.equal(g.clicks.length, 1);
  assert.ok(g.clicks[0] - 1000 >= 400, "ada jeda manusia sebelum klik");
  assert.ok(r.t - g.clicks[0] >= 3300, "sukses hanya setelah game menandai terbuka");
});

test("server menolak 2 kali: klik ulang dengan jeda, sukses di percobaan ke-3", () => {
  for (let seed = 1; seed <= 20; seed++) {
    const g = fakeGame({ rejects: 2 });
    const r = run(g, seed);
    assert.equal(r.a.type, "success", `seed ${seed}`);
    assert.equal(g.clicks.length, 3);
    assert.ok(g.clicks[1] - g.clicks[0] >= 3300 + 3500 - 50, `jeda ke-2 terlalu pendek: ${g.clicks[1] - g.clicks[0]}`);
    assert.ok(g.clicks[2] - g.clicks[1] >= 3300 + 7000 - 50, `jeda ke-3 terlalu pendek: ${g.clicks[2] - g.clicks[1]}`);
  }
});

test("server selalu menolak: gagal open_failed setelah tepat 3 klik, tidak berputar", () => {
  const g = fakeGame({ rejects: 99 });
  const r = run(g);
  assert.equal(r.a.type, "fail");
  assert.equal(r.a.reason, "open_failed");
  assert.equal(g.clicks.length, 3);
});

test("klik diabaikan (tombol tidak pernah sibuk): dicoba ulang lalu gagal, tidak menggantung", () => {
  const g = fakeGame({ ignoreClicks: true });
  const r = run(g);
  assert.equal(r.a.type, "fail");
  assert.equal(r.a.reason, "open_failed");
  assert.equal(g.clicks.length, 3);
  assert.ok(r.t - 1000 < 90000);
});

test("tombol tidak pernah muncul meski dekat: minta mendekat lagi, lalu gagal unreachable", () => {
  const g = fakeGame({ noButton: true });
  const r = run(g);
  assert.equal(r.a.type, "fail");
  assert.equal(r.a.reason, "unreachable");
  assert.equal(g.clicks.length, 0);
  assert.equal(r.events.filter(e => e.type === "reapproach").length, O.CFG.maxReapproach);
});

test("di luar jangkauan: reapproach, lalu lanjut klik setelah mendekat", () => {
  const g = fakeGame({ dist: 4.5 });
  let sawReapproach = false;
  const r = run(g, 3, 120000, {
    beforeTick: (t, game) => {
      if (t > 1000 + 2000) game.dist = 2.0;
    }
  });
  sawReapproach = r.events.some(e => e.type === "reapproach");
  assert.ok(sawReapproach);
  assert.equal(r.a.type, "success");
});

test("kerang sudah terbuka di game: sukses tanpa klik", () => {
  const g = fakeGame({ opened: true });
  const r = run(g);
  assert.equal(r.a.type, "success");
  assert.equal(g.clicks.length, 0);
});

test("menjauh saat animasi: game membatalkan, mesin klik ulang setelah mendekat", () => {
  const g = fakeGame();
  const op = O.createOpener({ rng: seeded(9) });
  let t = 1000;
  op.begin(t, 1);
  let done = null, clicks = 0, drifted = false, swimming = false;
  while (t < 200000 && !done) {
    t += 50;
    if (clicks === 1 && !drifted && g.busy && t > g.clicks[0] + 1000) {
      // pemain terseret: animasi dibatalkan, POST tidak pernah terjadi
      g.dist = 6;
      g.busy = false;
      g.postOk = false;
      drifted = true;
    }
    if (drifted && g.dist > 3 && t > g.clicks[0] + 6000) g.dist = 2.2;
    if (swimming) {
      if (g.dist <= O.CFG.arriveDist) { swimming = false; op.resume(t); }
      continue;
    }
    const a = op.tick(t, g.env(t));
    if (a.type === "click") { clicks++; g.click(t); }
    if (a.type === "reapproach") swimming = true;
    if (a.type === "success" || a.type === "fail") done = a;
  }
  assert.ok(drifted);
  assert.equal(done.type, "success");
  assert.equal(clicks, 2);
});

test("sebelum begin() tick melempar galat jelas", () => {
  const op = O.createOpener();
  assert.throws(() => op.tick(0, { dist: 1 }));
});
