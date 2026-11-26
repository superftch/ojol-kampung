import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
await import(path.resolve(__dirname, "../diving-shark.js"));
const { createShark, CFG } = globalThis.__KS_DIVING_SHARK;

const hiuAt = (x, y, z, extra) => Object.assign({ p: { x, y, z }, awas: false, memburu: false, sergap: false }, extra);
const fixedRng = (v) => () => v;

test("state machine: kabur dari hiu", async (t) => {
  await t.test("tanpa hiu: clear", () => {
    const s = createShark();
    const r = s.assess({ now: 0, pos: { x: 0, y: -30, z: 0 }, hiu: null, domDanger: false });
    assert.equal(r.mode, "clear");
    assert.equal(s.steer(r), null);
  });

  await t.test("hiu jauh (> 70 m) dan tidak memburu: tetap clear", () => {
    const s = createShark();
    const r = s.assess({ now: 0, pos: { x: 0, y: -30, z: 0 }, hiu: hiuAt(200, -30, 0), domDanger: false });
    assert.equal(r.mode, "clear");
  });

  await t.test("hiu dalam 70 m: langsung kabur naik penuh dan menjauh", () => {
    const s = createShark();
    const r = s.assess({ now: 0, pos: { x: 0, y: -30, z: 0 }, hiu: hiuAt(0, -30, 50), domDanger: false });
    assert.equal(r.mode, "flee");
    assert.equal(r.event, "flee_start");
    assert.ok(Math.abs(Math.abs(r.awayYaw) - Math.PI) < 1e-9, "menjauh dari hiu di +z berarti menghadap -z");
    assert.deepEqual(s.steer(r), { tegak: 1, move: true });
  });

  await t.test("indikator merah di HUD game saja sudah cukup untuk kabur", () => {
    const s = createShark();
    const r = s.assess({ now: 0, pos: { x: 0, y: -30, z: 0 }, hiu: null, domDanger: true });
    assert.equal(r.mode, "flee");
    assert.equal(r.awayYaw, null);
    assert.deepEqual(s.steer(r), { tegak: 1, move: false });
  });

  await t.test("hiu memburu walau jauh: kabur", () => {
    const s = createShark();
    const r = s.assess({ now: 0, pos: { x: 0, y: -30, z: 0 }, hiu: hiuAt(0, -30, 90, { memburu: true }), domDanger: false });
    assert.equal(r.mode, "flee");
  });

  await t.test("sampai kedalaman aman: sembunyi, tunggu hiu pergi, lalu lanjut", () => {
    const s = createShark({ rng: fixedRng(0) });
    s.assess({ now: 0, pos: { x: 0, y: -30, z: 0 }, hiu: hiuAt(0, -30, 50), domDanger: false });
    let r = s.assess({ now: 1000, pos: { x: 0, y: -4.4, z: 0 }, hiu: hiuAt(0, -10, 40), domDanger: false });
    assert.equal(r.mode, "hide");
    assert.equal(r.event, "safe");
    // hiu masih dekat: tetap sembunyi
    r = s.assess({ now: 5000, pos: { x: 0, y: -4.4, z: 0 }, hiu: hiuAt(0, -10, 40), domDanger: false });
    assert.equal(r.mode, "hide");
    // hiu menjauh > 100 m: hitung mundur jeda lalu lanjut
    r = s.assess({ now: 6000, pos: { x: 0, y: -4.4, z: 0 }, hiu: hiuAt(0, -10, 150), domDanger: false });
    assert.equal(r.mode, "hide");
    r = s.assess({ now: 6000 + CFG.releaseDelay[0] + 1, pos: { x: 0, y: -4.4, z: 0 }, hiu: hiuAt(0, -10, 150), domDanger: false });
    assert.equal(r.mode, "clear");
    assert.equal(r.event, "resume");
  });

  await t.test("hiu hilang dari game: lanjut setelah jeda, bukan seketika", () => {
    const s = createShark({ rng: fixedRng(1) });
    s.assess({ now: 0, pos: { x: 0, y: -3, z: 0 }, hiu: hiuAt(0, -10, 30), domDanger: false });
    assert.equal(s.state.mode, "hide");
    let r = s.assess({ now: 100, pos: { x: 0, y: -3, z: 0 }, hiu: null, domDanger: false });
    assert.equal(r.mode, "hide");
    r = s.assess({ now: 100 + CFG.releaseDelay[1] + 1, pos: { x: 0, y: -3, z: 0 }, hiu: null, domDanger: false });
    assert.equal(r.mode, "clear");
  });

  await t.test("hiu kembali mendekat saat menunggu: hitung mundur dibatalkan", () => {
    const s = createShark({ rng: fixedRng(0) });
    s.assess({ now: 0, pos: { x: 0, y: -3, z: 0 }, hiu: hiuAt(0, -10, 30), domDanger: false });
    s.assess({ now: 1000, pos: { x: 0, y: -3, z: 0 }, hiu: null, domDanger: false });
    assert.ok(s.state.releaseAt > 0);
    s.assess({ now: 1500, pos: { x: 0, y: -3, z: 0 }, hiu: hiuAt(0, -10, 40), domDanger: false });
    assert.equal(s.state.releaseAt, 0);
  });

  await t.test("bersembunyi menjaga kedalaman 3-5 m", () => {
    const s = createShark();
    s.assess({ now: 0, pos: { x: 0, y: -4, z: 0 }, hiu: hiuAt(0, -10, 30), domDanger: false });
    assert.deepEqual(s.steer({ mode: "hide", depth: 5.6 }), { tegak: 1, move: false });
    assert.deepEqual(s.steer({ mode: "hide", depth: 4.0 }), { tegak: 0, move: false });
    assert.deepEqual(s.steer({ mode: "hide", depth: 2.0 }), { tegak: -1, move: false });
  });

  await t.test("terdorong turun saat sembunyi dengan hiu dekat: kabur lagi", () => {
    const s = createShark();
    s.assess({ now: 0, pos: { x: 0, y: -4, z: 0 }, hiu: hiuAt(0, -10, 30), domDanger: false });
    const r = s.assess({ now: 500, pos: { x: 0, y: -8, z: 0 }, hiu: hiuAt(0, -10, 30), domDanger: false });
    assert.equal(r.mode, "flee");
  });

  await t.test("sembunyi tidak selamanya: lewat batas waktu, lanjut", () => {
    const s = createShark();
    s.assess({ now: 0, pos: { x: 0, y: -3, z: 0 }, hiu: hiuAt(0, -10, 30), domDanger: false });
    const r = s.assess({ now: CFG.maxHideMs + 1, pos: { x: 0, y: -3, z: 0 }, hiu: hiuAt(0, -10, 30), domDanger: false });
    assert.equal(r.mode, "clear");
    assert.equal(r.event, "hide_timeout");
  });

  await t.test("sudah di zona aman saat hiu muncul: langsung sembunyi, tidak 'kabur'", () => {
    const s = createShark();
    const r = s.assess({ now: 0, pos: { x: 0, y: -3, z: 0 }, hiu: hiuAt(0, -10, 30), domDanger: false });
    assert.equal(r.mode, "hide");
    assert.equal(r.event, "safe");
  });
});

// Simulasi pengejaran dengan aturan game: hiu memburu bila -y > 6 dan jarak < 45 m, laju 2.5 m/s,
// sergap 4.4 m/s. Laju renang pemain turun sampai 0.55x di kedalaman (GERAK_CONFIG server),
// laju naik 2.4 m/s. tangkap_m dan lama sergap tidak ada di konfigurasi yang terbaca, jadi nilai
// di bawah adalah ASUMSI dan diuji dengan margin (tangkap 3 m, sergap 2 detik tiap 4 detik).
function simulate({ depth, sharkDist, climb = 2.4, tangkap = 3, sergapOn = 2, sergapEvery = 4 }) {
  const shark = createShark({ rng: () => 0 });
  const dt = 0.05;
  const p = { x: 0, y: -depth, z: 0 };
  const h = { x: 0, y: -depth, z: sharkDist };
  let now = 0;
  let sergapT = 0;
  let nextSergap = sergapEvery;
  const firstClose = { t: null };
  for (let i = 0; i < 4000; i++) {
    now += dt * 1000;
    const hiu = { p: { ...h }, awas: false, memburu: -p.y > 6 && Math.hypot(h.x - p.x, h.y - p.y, h.z - p.z) < 45, sergap: false };
    const res = shark.assess({ now, pos: p, hiu, domDanger: false });
    const cmd = shark.steer(res);
    if (cmd) {
      const factor = 1 - 0.45 * Math.min(1, Math.max(0, (-p.y) / 40));
      if (cmd.tegak > 0) p.y += climb * dt;
      else if (cmd.tegak < 0) p.y -= climb * dt;
      if (cmd.move && res.awayYaw !== null) {
        p.x += Math.sin(res.awayYaw) * 3.4 * factor * dt;
        p.z += Math.cos(res.awayYaw) * 3.4 * factor * dt;
      }
    }
    p.y = Math.min(p.y, -0.35);
    // hiu: mengejar bila memburu
    if (hiu.memburu) {
      const dx = p.x - h.x, dy = p.y - h.y, dz = p.z - h.z;
      const d = Math.hypot(dx, dy, dz);
      if (d < 18 && now / 1000 >= nextSergap && sergapT <= 0) { sergapT = sergapOn; nextSergap = now / 1000 + sergapOn + sergapEvery; }
      let v = 2.5;
      if (sergapT > 0) { v = 4.4; sergapT -= dt; }
      const e = Math.min(d, v * dt);
      h.x += (dx / d) * e; h.y += (dy / d) * e; h.z += (dz / d) * e;
      h.y = Math.min(h.y, -6);
      const mouth = { x: h.x, y: h.y, z: h.z };
      if (-p.y > 6 && Math.hypot(mouth.x - p.x, mouth.y - p.y, mouth.z - p.z) < tangkap) return { caught: true, t: now / 1000, depth: -p.y };
    }
    if (-p.y <= 6 && res.mode === "hide") return { caught: false, t: now / 1000, depth: -p.y };
  }
  return { caught: false, t: 200, depth: -p.y };
}

test("simulasi pengejaran (aturan game, angka tangkap/sergap = asumsi)", async (t) => {
  for (const depth of [12, 25, 40, 60]) {
    await t.test(`kedalaman ${depth} m, hiu 70 m: selamat`, () => {
      const r = simulate({ depth, sharkDist: 70 });
      assert.equal(r.caught, false, JSON.stringify(r));
    });
  }
  await t.test("kedalaman 40 m, hiu 55 m: selamat", () => {
    const r = simulate({ depth: 40, sharkDist: 55 });
    assert.equal(r.caught, false, JSON.stringify(r));
  });
  await t.test("kedalaman 40 m, hiu 70 m, laju naik 30% lebih lambat dari dugaan: selamat", () => {
    const r = simulate({ depth: 40, sharkDist: 70, climb: 1.7 });
    assert.equal(r.caught, false, JSON.stringify(r));
  });
});
