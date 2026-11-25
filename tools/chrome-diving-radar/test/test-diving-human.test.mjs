import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
await import(path.resolve(__dirname, "../diving-human.js"));
await import(path.resolve(__dirname, "../diving-avoid.js"));
const H = globalThis.__KS_DIVING_HUMAN;
const avoid = globalThis.__KS_DIVING_AVOID;

// Pembangkit acak berbenih supaya tes bisa diulang.
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

function shell(i, x, z, d, kategori) {
  return { i, x, z, d, kategori };
}

const player = { x: 0, z: 0, d: 20 };

test("pickNext: hanya memilih dari 3 kerang utama terdekat", () => {
  const h = H.createHuman({ rng: seeded(1), cfg: { shallowMin: 0, shallowMax: 0 } });
  const primary = [];
  for (let i = 0; i < 20; i++) primary.push(shell(i, i * 10, 0, 20, "biasa"));
  const seen = new Set();
  for (let n = 0; n < 300; n++) seen.add(h.pickNext({ primary, shallow: [], player, now: n }).i);
  assert.deepEqual([...seen].sort((a, b) => a - b), [0, 1, 2]);
});

test("pickNext: terdekat paling sering tapi tidak selalu", () => {
  const h = H.createHuman({ rng: seeded(2), cfg: { shallowMin: 0, shallowMax: 0 } });
  const primary = [shell(0, 5, 0, 20, "biasa"), shell(1, 30, 0, 20, "biasa"), shell(2, 60, 0, 20, "biasa")];
  const c = [0, 0, 0];
  for (let n = 0; n < 1000; n++) c[h.pickNext({ primary, shallow: [], player, now: n }).i]++;
  assert.ok(c[0] > c[1] && c[1] > c[2], `urutan peluang salah: ${c}`);
  assert.ok(c[1] + c[2] > 200, "harus sering bukan yang terdekat");
});

test("pickNext: kandidat utama kosong mengembalikan null, bukan kerang dangkal", () => {
  const h = H.createHuman({ rng: seeded(3) });
  const shallow = [shell(9, 3, 0, 5, "kosong")];
  assert.equal(h.pickNext({ primary: [], shallow, player, now: 1 }), null);
});

test("pickNext: 1-2 kerang dangkal per sesi, urutan acak, tidak lebih", () => {
  const counts = new Set();
  for (let seed = 1; seed <= 60; seed++) {
    const h = H.createHuman({ rng: seeded(seed) });
    const primary = [];
    for (let i = 0; i < 30; i++) primary.push(shell(i, 10 + i * 8, 0, 25, "biasa"));
    const shallow = [shell(100, 4, 0, 5, "kosong"), shell(101, 9, 0, 6, "kosong"), shell(102, 14, 0, 7, "kosong")];
    let picked = 0;
    const left = primary.slice();
    const sh = shallow.slice();
    for (let n = 0; n < 25; n++) {
      const k = h.pickNext({ primary: left, shallow: sh, player, now: n });
      assert.ok(k);
      if (k.kategori === "kosong") {
        picked++;
        sh.splice(sh.findIndex(s => s.i === k.i), 1);
      } else {
        left.splice(left.findIndex(s => s.i === k.i), 1);
      }
    }
    assert.ok(picked >= 1 && picked <= 2, `seed ${seed}: ${picked} kerang dangkal`);
    counts.add(picked);
  }
  assert.equal(counts.size, 2, "kedua jumlah (1 dan 2) harus muncul");
});

test("pickNext: sesi baru setelah diam lama mengocok ulang jatah dangkal", () => {
  const h = H.createHuman({ rng: seeded(5) });
  const primary = [shell(0, 5, 0, 25, "biasa"), shell(1, 9, 0, 25, "biasa")];
  const shallow = [shell(9, 3, 0, 5, "kosong")];
  h.pickNext({ primary, shallow, player, now: 0 });
  const first = h.session.startedAt;
  h.pickNext({ primary, shallow, player, now: 60 * 60 * 1000 });
  assert.notEqual(h.session.startedAt, first);
});

test("jeda: nilai acak di dalam rentang dan bervariasi", () => {
  const h = H.createHuman({ rng: seeded(7) });
  const arr = new Set(), gap = new Set();
  for (let i = 0; i < 200; i++) {
    const a = h.arrivalDelayMs(), g = h.chainGapMs();
    assert.ok(a >= H.CFG.arrivalDelay[0] && a <= H.CFG.arrivalDelay[1]);
    assert.ok(g >= H.CFG.chainGap[0] && g <= H.CFG.chainGap[1]);
    arr.add(a); gap.add(g);
  }
  assert.ok(arr.size > 50 && gap.size > 50);
});

test("motion: tidak calm -> arah navigator dipakai apa adanya, tanpa jeda", () => {
  const h = H.createHuman({ rng: seeded(8) });
  const m = h.createMotion();
  m.step({ now: 0, desiredYaw: 0, calm: true, canPause: true, nearTarget: false });
  for (let t = 50; t < 60000; t += 50) {
    const yaw = (t / 1000) % 3;
    const r = m.step({ now: t, desiredYaw: yaw, calm: false, canPause: false, nearTarget: false });
    assert.equal(r.yaw, yaw);
    assert.equal(r.startPause, false);
  }
});

test("motion: calm -> belok dibatasi lajunya, goyangan kecil, ada jeda berkala", () => {
  const h = H.createHuman({ rng: seeded(9) });
  const m = h.createMotion();
  let prev = null, pauses = 0, maxDev = 0, t = 0;
  while (t < 120000) {
    t += 50;
    if (m.paused(t)) {
      const y = m.hold(t);
      assert.ok(Number.isFinite(y));
      continue;
    }
    const r = m.step({ now: t, desiredYaw: 1, calm: true, canPause: true, nearTarget: false });
    if (r.startPause) { pauses++; continue; }
    if (prev !== null) {
      const d = Math.abs(H.wrapAngle(r.yaw - prev));
      assert.ok(d <= H.CFG.turnRate * 0.25 + 1e-9, `belok terlalu cepat: ${d}`);
    }
    prev = r.yaw;
    if (t > 5000) maxDev = Math.max(maxDev, Math.abs(H.wrapAngle(r.yaw - 1)));
  }
  assert.ok(pauses >= 3, `jeda terlalu jarang: ${pauses}`);
  // Simpangan terbesar = goyangan + menoleh saat jeda (lalu kembali dengan laju terbatas).
  assert.ok(maxDev <= H.CFG.wanderAmp + H.CFG.pauseLook + 1e-6, `simpangan terlalu besar: ${maxDev}`);
  assert.ok(maxDev > 0.01, "harus ada goyangan");
});

test("motion: dekat kerang tidak ada jeda dan tidak bergoyang", () => {
  const h = H.createHuman({ rng: seeded(10) });
  const m = h.createMotion();
  m.step({ now: 0, desiredYaw: 2, calm: true, canPause: true, nearTarget: true });
  for (let t = 50; t < 90000; t += 50) {
    const r = m.step({ now: t, desiredYaw: 2, calm: true, canPause: true, nearTarget: true });
    assert.equal(r.startPause, false);
    assert.ok(Math.abs(r.yaw - 2) < 1e-9);
  }
});

test("motion: tab latar belakang tidak langsung memicu jeda", () => {
  const h = H.createHuman({ rng: seeded(11) });
  const m = h.createMotion();
  // performance.now() di game tidak pernah 0, jadi mulai dari 1000.
  m.step({ now: 1000, desiredYaw: 0, calm: true, canPause: true, nearTarget: false });
  const r = m.step({ now: 600000, desiredYaw: 0, calm: true, canPause: true, nearTarget: false });
  assert.equal(r.startPause, false);
});

// Integrasi dengan navigator: jeda manusia tidak boleh dianggap nyangkut atau tanpa kemajuan.
function runWithHumanPauses(seed) {
  const nav = avoid.createNavigator();
  const h = H.createHuman({ rng: seeded(seed), cfg: { pauseEvery: [1000, 2000], pauseLen: [1500, 3000] } });
  const motion = h.createMotion();
  const target = { i: 0, x: 0, z: 400, d: 0 };
  const pos = { x: 0, y: -0.35, z: 0 };
  let t = 1000, yaw = 0, reason = null, pauseTicks = 0;
  const speed = 0.35; // meter per tick
  while (t < 1000 + 300000 && !reason) {
    t += 50;
    const dist = Math.hypot(target.x - pos.x, target.z - pos.z);
    if (dist <= 2.8) { reason = "arrived"; break; }
    if (motion.paused(t)) {
      nav.hold(t);
      yaw = motion.hold(t);
      pauseTicks++;
      continue;
    }
    const out = nav.step({ now: t, pos: { ...pos }, target, rocks: [], pitch: 0, surfaceY: 0, floorFn: () => -200 });
    if (out.stop) { reason = out.stop; break; }
    const mv = motion.step({ now: t, desiredYaw: out.yaw, calm: true, canPause: true, nearTarget: dist < 6 });
    if (mv.startPause) { nav.hold(t); pauseTicks++; continue; }
    yaw = mv.yaw;
    pos.x += Math.sin(yaw) * speed * (out.gerak.y || 0);
    pos.z += Math.cos(yaw) * speed * (out.gerak.y || 0);
  }
  return { reason, pauseTicks, level: nav.state.stuckLevel };
}

test("navigator + jeda manusia: sampai tanpa stuck atau no_progress", () => {
  for (let seed = 1; seed <= 25; seed++) {
    const r = runWithHumanPauses(seed);
    assert.equal(r.reason, "arrived", `seed ${seed}: berhenti ${r.reason}`);
    assert.ok(r.pauseTicks > 0, `seed ${seed}: tidak ada jeda`);
  }
});
