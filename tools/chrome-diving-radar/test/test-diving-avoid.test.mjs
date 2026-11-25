import { describe, it } from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
await import(path.resolve(__dirname, "../diving-avoid.js"));
const avoid = globalThis.__KS_DIVING_AVOID;

const SPEED = 4;      // m/s, asumsi uji
const V_RATIO = 0.45; // sama dengan asumsi perencana
const DT = 0.05;

// Fisika tabrakan sama dengan gerakPemain di bundle game: dorong radial keluar bola r + 0.45.
function pushOut(p, rocks) {
  for (const a of rocks) {
    const t = p.x - a.x, s = p.y - a.y, e = p.z - a.z;
    const i = a.r + 0.45;
    if (Math.abs(t) > i || Math.abs(e) > i) continue;
    const n = Math.hypot(t, s, e);
    if (n < i && n > 0.001) {
      const k = (i - n) / n;
      p.x += t * k; p.y += s * k; p.z += e * k;
    }
  }
}

function swim({ start, target, rocks, useAvoid, maxSec = 90 }) {
  const p = { ...start };
  let prevOffset = 0;
  let maxStillSec = 0, stillFor = 0;
  let touched = 0;
  for (let t = 0; t < maxSec; t += DT) {
    if (Math.hypot(target.x - p.x, target.y - p.y, target.z - p.z) <= 2.8) {
      return { arrived: true, t, maxStillSec, touched, p };
    }
    let yaw = Math.atan2(target.x - p.x, target.z - p.z);
    let tegak = target.y - p.y < -1 ? -1 : target.y - p.y > 1 ? 1 : 0;
    if (useAvoid) {
      const plan = avoid.planSteering(p, target, rocks, { prevOffset });
      yaw = plan.yaw; tegak = plan.tegak; prevOffset = plan.offset;
    }
    const before = { ...p };
    p.x += Math.sin(yaw) * SPEED * DT;
    p.z += Math.cos(yaw) * SPEED * DT;
    p.y += tegak * SPEED * V_RATIO * DT;
    p.y = Math.min(p.y, -0.15);
    const pre = { ...p };
    pushOut(p, rocks);
    if (Math.hypot(p.x - pre.x, p.y - pre.y, p.z - pre.z) > 1e-6) touched++;
    const moved = Math.hypot(p.x - before.x, p.y - before.y, p.z - before.z);
    if (moved < 0.02) { stillFor += DT; maxStillSec = Math.max(maxStillSec, stillFor); } else stillFor = 0;
  }
  return { arrived: false, t: maxSec, maxStillSec, touched, p };
}

describe("Diving rock avoidance planner", () => {
  it("tanpa batu: arah lurus ke target dan tidak menandai menghindar", () => {
    const plan = avoid.planSteering(
      { x: 0, y: -10, z: 0 }, { x: 0, y: -10, z: 50 }, []
    );
    assert.ok(Math.abs(plan.yaw) < 1e-9);
    assert.equal(plan.avoiding, false);
    assert.equal(plan.blocked, false);
  });

  it("baseline: berenang lurus ke batu besar tepat di jalur membuat karakter diam", () => {
    const rocks = [{ x: 0, y: -10, z: 20, r: 3.6 }];
    const res = swim({
      start: { x: 0, y: -10, z: 0 }, target: { x: 0, y: -10, z: 60 }, rocks, useAvoid: false, maxSec: 20
    });
    assert.equal(res.arrived, false);
    assert.ok(res.maxStillSec > 5, `harus nyangkut lama, hanya ${res.maxStillSec}s`);
  });

  it("dengan perencana: memutari batu besar tepat di jalur dan sampai", () => {
    const rocks = [{ x: 0, y: -10, z: 20, r: 3.6 }];
    const res = swim({
      start: { x: 0, y: -10, z: 0 }, target: { x: 0, y: -10, z: 60 }, rocks, useAvoid: true
    });
    assert.equal(res.arrived, true);
    assert.ok(res.maxStillSec < 0.5, `terlalu lama diam: ${res.maxStillSec}s`);
    assert.equal(res.touched, 0, "tidak boleh menyentuh permukaan tabrakan");
  });

  it("dengan perencana: batu sedikit di samping jalur tetap dihindari tanpa menyentuh", () => {
    const rocks = [{ x: 1.5, y: -12, z: 25, r: 2.4 }];
    const res = swim({
      start: { x: 0, y: -12, z: 0 }, target: { x: 0, y: -12, z: 70 }, rocks, useAvoid: true
    });
    assert.equal(res.arrived, true);
    assert.equal(res.touched, 0);
  });

  it("dengan perencana: deretan batu seperti gerbang gua tetap dilewati", () => {
    const rocks = [
      { x: -6, y: -10, z: 20, r: 3.4 },
      { x: 0, y: -10, z: 22, r: 3.6 },
      { x: 6.5, y: -10, z: 20, r: 3.2 },
      { x: 12, y: -10, z: 21, r: 3.0 }
    ];
    const res = swim({
      start: { x: 0, y: -10, z: 0 }, target: { x: 2, y: -10, z: 60 }, rocks, useAvoid: true
    });
    assert.equal(res.arrived, true, `tidak sampai, posisi akhir ${JSON.stringify(res.p)}`);
    assert.ok(res.maxStillSec < 1, `terlalu lama diam: ${res.maxStillSec}s`);
  });

  it("dengan perencana: dinding batu lebar memaksa lewat atas atau samping, bukan menabrak", () => {
    const rocks = [];
    for (let x = -18; x <= 18; x += 4) rocks.push({ x, y: -9, z: 20, r: 2.6 });
    const res = swim({
      start: { x: 0, y: -9, z: 0 }, target: { x: 0, y: -9, z: 60 }, rocks, useAvoid: true
    });
    assert.equal(res.arrived, true, `tidak sampai, posisi akhir ${JSON.stringify(res.p)}`);
    assert.ok(res.maxStillSec < 1);
  });

  it("batu di dekat target: tetap bisa sampai ke jangkauan buka kerang", () => {
    const rocks = [{ x: 3, y: -12, z: 28, r: 3.0 }];
    const res = swim({
      start: { x: 0, y: -12, z: 0 }, target: { x: 0, y: -12, z: 30 }, rocks, useAvoid: true
    });
    assert.equal(res.arrived, true);
  });

  it("y target lebih dalam: tegak tetap turun saat jalur kosong", () => {
    const plan = avoid.planSteering(
      { x: 0, y: -5, z: 0 }, { x: 0, y: -25, z: 40 },
      [{ x: 100, y: -5, z: 100, r: 3 }]
    );
    assert.equal(plan.tegak, -1);
    assert.equal(plan.avoiding, false);
  });

  it("opsi undefined tidak menimpa default perencana", () => {
    const plan = avoid.planSteering(
      { x: 0, y: -10, z: 0 }, { x: 0, y: -10, z: 40 },
      [{ x: 0, y: -10, z: 15, r: 3 }],
      { surfaceY: undefined, floorFn: undefined }
    );
    assert.ok(Number.isFinite(plan.yaw));
    assert.equal(plan.avoiding, true);
  });

  it("dasar laut dipakai sebagai batas bawah saat mempertimbangkan lewat bawah batu", () => {
    const rocks = [{ x: 0, y: -10, z: 15, r: 3 }];
    const plan = avoid.planSteering(
      { x: 0, y: -10, z: 0 }, { x: 0, y: -10, z: 40 }, rocks,
      { floorFn: () => -10.2 }
    );
    assert.ok(plan.avoiding);
    assert.ok(Math.abs(plan.offset) > 0 || plan.tegak === 1);
  });
});

// Simulasi penuh dengan navigator berstatus (waypoint, pemulihan, watchdog).
function swimNav({ start, target, rocks, maxSec = 120 }) {
  const nav = avoid.createNavigator();
  const p = { ...start };
  const tgt = { i: 1, x: target.x, z: target.z, d: -(target.y) - 0.35 };
  let stop = null, still = 0, maxStill = 0;
  for (let t = 0; t < maxSec; t += DT) {
    if (Math.hypot(target.x - p.x, target.y - p.y, target.z - p.z) <= 2.8) {
      return { arrived: true, t, stop, maxStill, p };
    }
    const out = nav.step({ now: t * 1000 + 1, pos: p, target: tgt, rocks, pitch: 0 });
    if (out.stop) { stop = out.stop; return { arrived: false, t, stop, maxStill, p }; }
    const before = { ...p };
    // gerak.y = maju; gerak.x = geser samping (tegak lurus yaw)
    p.x += (Math.sin(out.yaw) * out.gerak.y + Math.cos(out.yaw) * out.gerak.x) * SPEED * DT;
    p.z += (Math.cos(out.yaw) * out.gerak.y - Math.sin(out.yaw) * out.gerak.x) * SPEED * DT;
    p.y += out.tegak * SPEED * V_RATIO * DT;
    p.y = Math.min(p.y, -0.15);
    pushOut(p, rocks);
    const moved = Math.hypot(p.x - before.x, p.y - before.y, p.z - before.z);
    if (moved < 0.02) { still += DT; maxStill = Math.max(maxStill, still); } else still = 0;
  }
  return { arrived: false, t: maxSec, stop, maxStill, p };
}

describe("Diving navigator (kerang tersembunyi di batu)", () => {
  it("kerang agak masuk ke dalam batu (masih terjangkau dari permukaan): sampai", () => {
    // Permukaan tabrakan 4.05 m dari pusat; kerang 1.5 m dari pusat -> 2.55 m < 2.8 m.
    for (const dz of [-1.5, 1.5]) {
      const rocks = [{ x: 0, y: -12, z: 30, r: 3.6 }];
      const res = swimNav({
        start: { x: 0, y: -12, z: 0 }, target: { x: 0, y: -12, z: 30 + dz }, rocks
      });
      assert.equal(res.arrived, true, `dz=${dz} tidak sampai (stop=${res.stop}) di ${JSON.stringify(res.p)}`);
      assert.ok(res.t < 40, `dz=${dz} terlalu lama: ${res.t}s`);
    }
  });

  it("kerang di pusat batu besar (mustahil dijangkau): berhenti dengan alasan, bukan berputar terus", () => {
    const rocks = [{ x: 0, y: -12, z: 30, r: 3.6 }];
    const res = swimNav({
      start: { x: 0, y: -12, z: 0 }, target: { x: 0, y: -12, z: 30 }, rocks
    });
    assert.equal(res.arrived, false);
    assert.equal(res.stop, "no_progress");
    assert.ok(res.t < 60, `berhenti terlalu lama: ${res.t}s`);
  });

  it("kerang di balik batu, dikelilingi batu lain: tetap sampai", () => {
    const rocks = [
      { x: 0, y: -12, z: 30, r: 3.0 },
      { x: -4.5, y: -12, z: 30, r: 2.6 },
      { x: 4.5, y: -12, z: 30, r: 2.6 },
      { x: 0, y: -12, z: 34.5, r: 2.4 }
    ];
    const res = swimNav({
      start: { x: 0, y: -12, z: 0 }, target: { x: 0, y: -12, z: 33 }, rocks
    });
    assert.equal(res.arrived, true, `tidak sampai (stop=${res.stop}) di ${JSON.stringify(res.p)}`);
  });

  it("kerang menempel di permukaan batu: sampai tanpa berputar lama", () => {
    const rocks = [{ x: 0, y: -12, z: 30, r: 3.6 }];
    const res = swimNav({
      start: { x: 0, y: -12, z: 0 }, target: { x: 0, y: -12, z: 33.4 }, rocks
    });
    assert.equal(res.arrived, true, `tidak sampai (stop=${res.stop}) di ${JSON.stringify(res.p)}`);
    assert.ok(res.t < 40);
  });

  it("tidak mungkin dicapai: berhenti dengan alasan, tidak berputar selamanya", () => {
    const rocks = [];
    for (let a = 0; a < 12; a++) {
      const ang = (a / 12) * 2 * Math.PI;
      for (const dy of [-4, 0, 4]) {
        rocks.push({ x: 8 * Math.sin(ang), y: -20 + dy, z: 40 + 8 * Math.cos(ang), r: 4 });
      }
    }
    rocks.push({ x: 0, y: -26, z: 40, r: 5 }, { x: 0, y: -13, z: 40, r: 5 });
    const res = swimNav({
      start: { x: 0, y: -20, z: 0 }, target: { x: 0, y: -20, z: 40 }, rocks, maxSec: 180
    });
    if (!res.arrived) {
      assert.ok(res.stop === "stuck" || res.stop === "no_progress", `harus berhenti, stop=${res.stop}`);
    }
  });

  it("nyangkut: pemulihan terjadwal lalu berhenti bila posisi tak berubah", () => {
    const nav = avoid.createNavigator();
    const tgt = { i: 2, x: 0, z: 40, d: 10 };
    const pos = { x: 0, y: -10.35, z: 0 };
    let stop = null, recovered = false;
    for (let t = 0; t < 60000 && !stop; t += 50) {
      const out = nav.step({ now: t + 1, pos, target: tgt, rocks: [] });
      if (out.mode === "recover") recovered = true;
      stop = out.stop;
    }
    assert.equal(recovered, true);
    assert.ok(stop === "stuck" || stop === "no_progress");
  });

  it("ganti target mereset status navigator", () => {
    const nav = avoid.createNavigator();
    const pos = { x: 0, y: -10, z: 0 };
    nav.step({ now: 1, pos, target: { i: 1, x: 0, z: 30, d: 9.65 }, rocks: [] });
    nav.step({ now: 900, pos, target: { i: 1, x: 0, z: 30, d: 9.65 }, rocks: [] });
    assert.ok(nav.state.stuckLevel >= 1);
    nav.step({ now: 950, pos, target: { i: 2, x: 5, z: 30, d: 9.65 }, rocks: [] });
    assert.equal(nav.state.stuckLevel, 0);
  });
});
