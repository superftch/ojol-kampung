import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

// Menjalankan inject.js asli di vm dengan scene game palsu, lalu menguji alur kabur dari hiu
// lewat loop 50 ms yang sebenarnya (bukan hanya mesin statusnya).

const dir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (f) => fs.readFileSync(path.join(dir, f), "utf-8");

function makeWorld({ depth = 30, shellDist = 80 } = {}) {
  let clock = 1000;
  let seq = 0;
  const timers = [];
  const listeners = {};
  const logs = [];
  let domDanger = false;

  const sc = {
    p: { x: 0, y: -depth, z: 0 },
    yaw: 0, hadap: 0, pitch: 0, v: { x: 0, y: 0, z: 0 },
    kunci: false, tertangkap: false, permukaan: false, membuka: null,
    kerang: [{ y: -(depth + 0.5), dibuka: false, k: { i: 0, x: 0, z: shellDist, d: depth + 0.15 } }],
    dunia: { batuBesar: [], tinggi: () => -80 },
    pen: { apung: -0.35 },
    hiuS: { aktif: false, pergi: 0, p: { x: 0, y: -depth, z: 0 }, awas: false, memburu: false, sergap: 0 },
    input: { x: 0, y: 0, tegak: 0 },
    setGerak(x, y) { this.input.x = x; this.input.y = y; },
    setTegak(t) { this.input.tegak = t; },
    lastYawSet: null
  };

  const win = {
    console: { log() {}, warn: (...a) => logs.push(a.join(" ")), error: (...a) => logs.push("E:" + a.join(" ")) },
    performance: { now: () => clock },
    CustomEvent: class { constructor(type, init) { this.type = type; this.detail = init && init.detail; } },
    setTimeout: (fn, ms) => { const id = ++seq; timers.push({ id, at: clock + (ms || 0), fn }); return id; },
    clearTimeout: () => {},
    setInterval: (fn, ms) => { const id = ++seq; timers.push({ id, at: clock + ms, fn, every: ms }); return id; },
    clearInterval: () => {},
    addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
    removeEventListener() {},
    dispatchEvent(ev) { for (const fn of (listeners[ev.type] || []).slice()) fn(ev); return true; },
    location: { href: "https://www.kampungsebelah.com/diving" },
    document: {
      hidden: false, visibilityState: "visible",
      hasFocus: () => true,
      addEventListener() {},
      querySelector: (sel) => (/data-bahaya/.test(sel) && domDanger ? { hasAttribute: () => false } : null)
    }
  };
  win.window = win;
  win.globalThis = win;
  const ctx = vm.createContext(win);
  for (const f of ["diving-avoid.js", "diving-human.js", "diving-open.js", "diving-shark.js", "inject.js"]) {
    vm.runInContext(read(f), ctx, { filename: f });
  }
  win.__KS_SCENE_INSTANCE = sc;

  const statuses = [];
  const sharkEvents = [];
  win.addEventListener("ks_autopilot_status", (e) => statuses.push(e.detail));
  win.addEventListener("ks_autopilot_shark", (e) => sharkEvents.push(e.detail));

  // Fisika sangat sederhana: naik 2.4 m/s, maju searah yaw 3.4 * 0.7 m/s.
  function physics(dt) {
    sc.p.y = Math.min(-0.35, Math.max(-79, sc.p.y + sc.input.tegak * 2.4 * dt));
    const sp = 3.4 * 0.7 * Math.max(0, sc.input.y);
    sc.p.x += Math.sin(sc.yaw) * sp * dt;
    sc.p.z += Math.cos(sc.yaw) * sp * dt;
  }

  function advance(ms) {
    const end = clock + ms;
    for (;;) {
      timers.sort((a, b) => a.at - b.at);
      const t = timers[0];
      if (!t || t.at > end) break;
      const step = t.at - clock;
      clock = t.at;
      if (step > 0) physics(step / 1000);
      if (t.every) t.at += t.every; else timers.shift();
      t.fn();
    }
    physics((end - clock) / 1000);
    clock = end;
  }

  const send = (type, detail) => win.dispatchEvent(new win.CustomEvent(type, { detail }));
  const start = (extra) => send("ks_autopilot_command", Object.assign({
    action: "start",
    target: { i: 0, x: 0, z: shellDist, d: depth + 0.15, kategori: "langka" },
    autoOpen: true, autoChain: false
  }, extra));

  return {
    sc, win, logs, advance, start, send, statuses, sharkEvents,
    setShark(s) { Object.assign(sc.hiuS, s); },
    setDom(v) { domDanger = v; },
    get now() { return clock; }
  };
}

test("inject.js: kabur dari hiu", async (t) => {
  await t.test("tanpa hiu: berenang ke kerang seperti biasa", () => {
    const w = makeWorld();
    w.start();
    w.advance(1500);
    assert.ok(w.sc.input.y > 0, "maju ke kerang");
    assert.ok(w.sc.p.z > 0.5, "bergerak ke arah kerang");
  });

  await t.test("hiu muncul 60 m di belakang: naik penuh dan menjauh, lalu sembunyi di zona aman", () => {
    const w = makeWorld({ depth: 30, shellDist: 80 });
    w.start();
    w.advance(500);
    // hiu di -z (belakang), kerang di +z (depan): menjauh dari hiu = maju ke +z
    w.setShark({ aktif: true, p: { x: 0, y: -30, z: -60 }, memburu: false, awas: false });
    w.advance(300);
    assert.equal(w.sc.input.tegak, 1, "naik penuh");
    assert.ok(w.sharkEvents.some((e) => e.mode === "flee"), JSON.stringify(w.sharkEvents));
    // naik 2.4 m/s: dari 30 m ke 4.5 m butuh ~11 detik
    w.advance(12000);
    assert.ok(-w.sc.p.y <= 5.0, "sudah di zona aman, y=" + w.sc.p.y);
    assert.ok(w.sharkEvents.some((e) => e.mode === "hide"));
    assert.equal(w.sc.input.y, 0, "diam saat bersembunyi");
    // hiu pergi: lanjut ke kerang setelah jeda
    w.setShark({ aktif: false });
    w.advance(6000);
    assert.ok(w.sharkEvents.at(-1).mode === "clear", JSON.stringify(w.sharkEvents.at(-1)));
    w.advance(1500);
    assert.ok(w.sc.input.y > 0, "lanjut berenang");
    assert.ok(w.statuses.every((s) => s.active !== false), "auto-pilot tidak berhenti selama kabur");
  });

  await t.test("kabur menjauh dari hiu: arah berlawanan dengan hiu", () => {
    const w = makeWorld({ depth: 30, shellDist: 80 });
    w.start();
    w.advance(200);
    w.setShark({ aktif: true, p: { x: 40, y: -30, z: 0 }, memburu: true });
    w.advance(300);
    // hiu di +x: menjauh berarti yaw menuju -x (sin(yaw) < 0)
    assert.ok(Math.sin(w.sc.yaw) < -0.5, "yaw=" + w.sc.yaw);
    assert.equal(w.sc.input.tegak, 1);
  });

  await t.test("indikator merah di HUD game (tanpa data hiuS) juga memicu kabur", () => {
    const w = makeWorld();
    w.start();
    w.advance(200);
    w.setDom(true);
    w.advance(200);
    assert.equal(w.sc.input.tegak, 1);
    assert.ok(w.sharkEvents.some((e) => e.mode === "flee"));
  });

  await t.test("hiu jauh (150 m): tidak mengganggu", () => {
    const w = makeWorld();
    w.start();
    w.advance(200);
    w.setShark({ aktif: true, p: { x: 0, y: -30, z: -150 } });
    w.advance(500);
    assert.notEqual(w.sc.input.tegak, 1, "tidak naik penuh");
    assert.ok(!w.sharkEvents.some((e) => e.mode === "flee"));
  });

  await t.test("hiu sedang pergi (pergi > 0): diabaikan", () => {
    const w = makeWorld();
    w.start();
    w.advance(200);
    w.setShark({ aktif: true, pergi: 5, p: { x: 0, y: -30, z: -20 } });
    w.advance(500);
    assert.ok(!w.sharkEvents.some((e) => e.mode === "flee"));
  });

  await t.test("penjaga saat jeda rantai: setelah 'tiba', hiu tetap membuat kabur", () => {
    const w = makeWorld({ depth: 30, shellDist: 0.2 });
    w.start({ autoOpen: false, autoChain: true });
    w.advance(300);
    assert.equal(w.statuses.at(-1).active, false, "auto-pilot berhenti karena tiba");
    assert.equal(w.statuses.at(-1).reason, "arrived");
    w.setShark({ aktif: true, p: { x: 0, y: -30, z: -40 }, memburu: true });
    w.advance(300);
    assert.equal(w.sc.input.tegak, 1, "tetap kabur walau auto-pilot sedang jeda");
  });

  await t.test("berhenti manual: tidak ada penjaga hiu (kendali kembali ke pemain)", () => {
    const w = makeWorld();
    w.start();
    w.advance(200);
    w.send("ks_autopilot_command", { action: "stop" });
    w.sc.setTegak(0);
    w.setShark({ aktif: true, p: { x: 0, y: -30, z: -40 }, memburu: true });
    w.advance(500);
    assert.equal(w.sc.input.tegak, 0);
  });

  await t.test("tidak ada error di log selama skenario", () => {
    const w = makeWorld();
    w.start();
    w.advance(300);
    w.setShark({ aktif: true, p: { x: 0, y: -30, z: -50 }, memburu: true });
    w.advance(15000);
    w.setShark({ aktif: false });
    w.advance(8000);
    assert.deepEqual(w.logs.filter((l) => /Error|E:/.test(l)), []);
  });
});
