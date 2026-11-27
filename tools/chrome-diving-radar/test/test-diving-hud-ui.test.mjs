import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

// Menjalankan content.js asli di vm dengan DOM tiruan dan jam palsu, lalu memicu event
// dari inject.js. Tujuannya: tombol Auto Jalan/STOP benar-benar berubah, dan tidak ada
// ReferenceError di penanganan event (mis. variabel rantai yang belum didefinisikan).

const dir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (f) => fs.readFileSync(path.join(dir, f), "utf-8");

function makeEnv(store = {}) {
  let clock = Date.UTC(2026, 10, 26, 3, 0, 0);
  let seq = 0;
  const timers = [];
  const rafs = [];
  const listeners = {};
  const ids = new Map();
  const appended = [];
  const logs = [];

  class FakeDate extends Date {
    static now() { return clock; }
  }

  class El {
    constructor(tag) {
      this.tag = tag;
      this.style = {};
      this.dataset = {};
      this._cls = new Set();
      this.classList = {
        add: (...c) => c.forEach((x) => this._cls.add(x)),
        remove: (...c) => c.forEach((x) => this._cls.delete(x)),
        contains: (c) => this._cls.has(c)
      };
      this._html = "";
      this._id = "";
      this.textContent = "";
    }
    set id(v) { this._id = v; if (v) ids.set(v, this); }
    get id() { return this._id; }
    set innerHTML(v) {
      this._html = String(v);
      for (const m of this._html.matchAll(/\sid="([^"]+)"/g)) {
        if (!ids.has(m[1])) { const c = new El("div"); c.id = m[1]; }
      }
    }
    get innerHTML() { return this._html; }
    addEventListener() {}
    removeEventListener() {}
    querySelector() { return null; }
    appendChild(c) { appended.push(c); return c; }
    remove() { if (this._id) ids.delete(this._id); }
    select() {}
    closest() { return null; }
    setPointerCapture() {}
    releasePointerCapture() {}
    getBoundingClientRect() { return { left: 0, top: 0, width: 100, height: 50 }; }
  }

  const win = {
    console: {
      log: (...a) => logs.push(["log", a.join(" ")]),
      warn: (...a) => logs.push(["warn", a.join(" ")]),
      error: (...a) => logs.push(["error", a.join(" ")])
    },
    Date: FakeDate,
    CustomEvent: class { constructor(type, init) { this.type = type; this.detail = init && init.detail; } },
    chrome: { runtime: { getURL: (f) => "chrome-extension://x/" + f } },
    localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: (k) => { delete store[k]; } },
    confirm: () => true,
    innerWidth: 1280,
    innerHeight: 800,
    location: { pathname: "/diving", href: "https://www.kampungsebelah.com/diving" },
    navigator: {},
    document: null,
    setTimeout: (fn, ms) => { const id = ++seq; timers.push({ id, at: clock + (ms || 0), fn }); return id; },
    clearTimeout: (id) => { const i = timers.findIndex((t) => t.id === id); if (i >= 0) timers.splice(i, 1); },
    setInterval: (fn, ms) => { const id = ++seq; timers.push({ id, at: clock + ms, fn, every: ms }); return id; },
    clearInterval: (id) => { const i = timers.findIndex((t) => t.id === id); if (i >= 0) timers.splice(i, 1); },
    requestAnimationFrame: (fn) => { rafs.push(fn); return rafs.length; },
    addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
    removeEventListener(type, fn) { listeners[type] = (listeners[type] || []).filter((f) => f !== fn); },
    dispatchEvent(ev) { for (const fn of (listeners[ev.type] || []).slice()) fn(ev); return true; }
  };
  win.window = win;
  win.globalThis = win;
  win.document = {
    readyState: "complete",
    body: new El("body"),
    head: new El("head"),
    documentElement: new El("html"),
    getElementById: (id) => ids.get(id) || null,
    createElement: (tag) => new El(tag),
    querySelector: () => null,
    addEventListener() {}
  };

  const ctx = vm.createContext(win);
  vm.runInContext(read("diving-human.js"), ctx);
  vm.runInContext(read("content.js"), ctx);

  function advance(ms) {
    const end = clock + ms;
    for (;;) {
      timers.sort((a, b) => a.at - b.at);
      const t = timers[0];
      if (!t || t.at > end) break;
      clock = t.at;
      if (t.every) t.at += t.every; else timers.shift();
      t.fn();
    }
    clock = end;
  }
  function frame() {
    const run = rafs.splice(0);
    for (const fn of run) fn();
  }
  const send = (type, detail) => win.dispatchEvent(new win.CustomEvent(type, { detail }));
  const commands = [];
  win.addEventListener("ks_autopilot_command", (e) => commands.push(e.detail));

  advance(900); // initAll dijadwalkan 800 ms setelah muat
  frame();

  return { win, ids, appended, logs, advance, frame, send, commands, store, get: (id) => ids.get(id) };
}

test("HUD diving: tombol Auto Jalan / STOP", async (t) => {
  await t.test("diving-open.js ikut dimuat ke halaman", () => {
    const env = makeEnv();
    const srcs = env.appended.filter((e) => e.tag === "script").map((e) => e.src);
    assert.ok(srcs.some((s) => s.endsWith("diving-open.js")), "diving-open.js harus diinjeksi: " + srcs.join(","));
    assert.ok(srcs.some((s) => s.endsWith("inject.js")));
  });

  await t.test("awal: tombol biru 'Auto Jalan', tanpa animasi", () => {
    const env = makeEnv();
    const btn = env.get("ks-hud-autopilot-btn");
    assert.ok(btn, "tombol HUD harus ada");
    assert.equal(btn.dataset.apMode, "idle");
    assert.match(btn.innerHTML, /Auto Jalan/);
    assert.ok(!btn.classList.contains("ks-ap-run"));
  });

  function startRun(env) {
    env.get("ks-filter-all").onclick();
    env.get("ks-pick-nearest").onclick();
    env.get("ks-hud-autopilot-btn").onclick({ stopPropagation() {} });
    const cmd = env.commands.at(-1);
    assert.equal(cmd.action, "start");
    env.send("ks_autopilot_status", { active: true, target: cmd.target });
    env.frame();
    return cmd.target;
  }

  await t.test("jalan: tombol merah berdenyut 'STOP', beda jelas dari idle", () => {
    const env = makeEnv();
    startRun(env);
    const btn = env.get("ks-hud-autopilot-btn");
    assert.equal(btn.dataset.apMode, "run");
    assert.match(btn.innerHTML, /STOP/);
    assert.equal(btn.style.background, "#dc2626");
    assert.ok(btn.classList.contains("ks-ap-run"));
    const radar = env.get("ks-radar-autopilot-btn");
    assert.match(radar.textContent, /Batalkan/);
    assert.equal(radar.style.background, "#dc2626");
  });

  await t.test("klik STOP: kirim stop, lalu tombol kembali ke 'Auto Jalan' dan judul memberi tahu", () => {
    const env = makeEnv();
    const target = startRun(env);
    env.get("ks-hud-autopilot-btn").onclick({ stopPropagation() {} });
    assert.equal(env.commands.at(-1).action, "stop");
    env.send("ks_autopilot_status", { active: false, reason: "manual_stop", target });
    env.frame();
    const btn = env.get("ks-hud-autopilot-btn");
    assert.equal(btn.dataset.apMode, "idle");
    assert.match(btn.innerHTML, /Auto Jalan/);
    assert.ok(!btn.classList.contains("ks-ap-run"));
    assert.match(env.get("ks-compass-title").textContent, /dihentikan manual/);
  });

  await t.test("jeda rantai: tombol kuning 'STOP (jeda)', klik membatalkan rantai", () => {
    const env = makeEnv();
    const target = startRun(env);
    env.send("ks_autopilot_status", { active: false, reason: "arrived", target });
    env.send("ks_shell_opened_auto", { kerang: target, autoChain: true, ok: true });
    env.frame();
    const btn = env.get("ks-hud-autopilot-btn");
    assert.equal(btn.dataset.apMode, "wait");
    assert.match(btn.innerHTML, /STOP \(jeda\)/);
    assert.equal(btn.style.background, "#d97706");
    assert.match(env.get("ks-compass-title").textContent, /lanjut \d+ dtk/);

    const before = env.commands.length;
    btn.onclick({ stopPropagation() {} });
    env.frame();
    assert.equal(btn.dataset.apMode, "idle");
    env.advance(15000);
    assert.equal(env.commands.length, before, "setelah dibatalkan tidak boleh ada start otomatis");
  });

  await t.test("rantai lanjut sendiri ke kerang lain setelah jeda", () => {
    const env = makeEnv();
    const target = startRun(env);
    env.send("ks_autopilot_status", { active: false, reason: "arrived", target });
    env.send("ks_shell_opened_auto", { kerang: target, autoChain: true, ok: true });
    env.advance(9000);
    const cmd = env.commands.at(-1);
    assert.equal(cmd.action, "start");
    assert.notEqual(cmd.target.i, target.i);
  });

  await t.test("kerang tak terjangkau dilewati, rantai tidak putus", () => {
    const env = makeEnv();
    const target = startRun(env);
    env.send("ks_autopilot_status", { active: false, reason: "no_progress", target });
    env.frame();
    assert.equal(env.get("ks-hud-autopilot-btn").dataset.apMode, "wait");
    env.advance(2500);
    const cmd = env.commands.at(-1);
    assert.equal(cmd.action, "start");
    assert.notEqual(cmd.target.i, target.i, "kerang yang dilewati tidak dipilih lagi");
  });

  await t.test("tidak ada ReferenceError atau error lain di konsol", () => {
    const env = makeEnv();
    const target = startRun(env);
    env.send("ks_autopilot_status", { active: false, reason: "arrived", target });
    env.send("ks_shell_opened_auto", { kerang: target, autoChain: true, ok: true });
    env.advance(9000);
    assert.deepEqual(env.logs.filter(([lvl, msg]) => lvl === "error" || /ReferenceError|is not defined/.test(msg)), []);
  });

  await t.test("hiu: judul HUD merah saat kabur, oranye saat menunggu, normal lagi setelah aman", () => {
    const env = makeEnv();
    startRun(env);
    env.send("ks_autopilot_shark", { mode: "flee", dist: 42.3, depth: 31 });
    env.frame();
    const title = env.get("ks-compass-title");
    assert.match(title.textContent, /HIU! Kabur naik/);
    assert.match(title.textContent, /42 m/);
    assert.equal(title.style.color, "#ef4444");
    env.send("ks_autopilot_shark", { mode: "hide", dist: 60, depth: 4.4 });
    env.frame();
    assert.match(title.textContent, /menunggu hiu pergi/);
    env.send("ks_autopilot_shark", { mode: "clear" });
    env.frame();
    assert.doesNotMatch(title.textContent, /hiu/i);
  });

  // Kerang yang dipilih rantai otomatis setelah kerang pertama terbuka (filter "Semua").
  function chainPick(env) {
    const target = startRun(env);
    env.send("ks_autopilot_status", { active: false, reason: "arrived", target });
    env.send("ks_shell_opened_auto", { kerang: target, autoChain: true, ok: true });
    env.advance(9000);
    const cmd = env.commands.at(-1);
    assert.equal(cmd.action, "start");
    return cmd.target.i;
  }

  await t.test("urutan kerang: default acak, kotak centang tercentang", () => {
    const env = makeEnv();
    assert.equal(env.get("ks-random-order-check").checked, true);
    assert.match(env.get("ks-random-order-hint").textContent, /Acak/);
    const picks = new Set();
    for (let n = 0; n < 40; n++) picks.add(chainPick(makeEnv()));
    assert.ok(picks.size >= 2, "mode acak harus memberi lebih dari satu pilihan, dapat: " + [...picks].join(","));
  });

  await t.test("urutan kerang: dimatikan = selalu terdekat, hasil sama tiap kali", () => {
    const picks = new Set();
    for (let n = 0; n < 25; n++) picks.add(chainPick(makeEnv({ ks_diving_random_order: "0" })));
    assert.equal(picks.size, 1, "terdekat berurutan harus deterministik, dapat: " + [...picks].join(","));
  });

  await t.test("urutan kerang: mengubah kotak centang tersimpan dan berlaku seketika", () => {
    const env = makeEnv();
    const box = env.get("ks-random-order-check");
    box.checked = false;
    box.onchange();
    assert.equal(env.store.ks_diving_random_order, "0");
    assert.match(env.get("ks-random-order-hint").textContent, /terdekat/);
    const first = chainPick(env);
    const picks = new Set([first]);
    for (let n = 0; n < 10; n++) picks.add(chainPick(makeEnv({ ks_diving_random_order: env.store.ks_diving_random_order })));
    assert.equal(picks.size, 1);
    box.checked = true;
    box.onchange();
    assert.equal(env.store.ks_diving_random_order, "1");
  });

  await t.test("urutan kerang: pengaturan tersimpan dibaca saat dimuat", () => {
    assert.equal(makeEnv({ ks_diving_random_order: "0" }).get("ks-random-order-check").checked, false);
    assert.equal(makeEnv({ ks_diving_random_order: "1" }).get("ks-random-order-check").checked, true);
  });

  await t.test("tombol Salin Log memanggil dump dan menyalin hasilnya", async () => {
    const env = makeEnv();
    let copied = null;
    env.win.navigator.clipboard = { writeText: (t) => { copied = t; return Promise.resolve(); } };
    env.win.addEventListener("ks_diving_dump", () => env.send("ks_diving_dump_result", { text: "LOG-ISI" }));
    env.get("ks-copy-log-btn").onclick();
    await Promise.resolve();
    await Promise.resolve();
    assert.equal(copied, "LOG-ISI");
    assert.match(env.get("ks-copy-log-btn").textContent, /tersalin/);
  });
});
