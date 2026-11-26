import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
await import(path.resolve(__dirname, "../berburu.js"));
const berburu = globalThis.__KS_BERBURU_MODULE;

test("Berburu Radar & Sniper Engine", async (t) => {
  await t.test("evaluateBagProfit computes 3 babi + 2 ayam net profit accurately", () => {
    const bag = ["babi-hutan", "babi-hutan", "babi-hutan", "ayam-hutan", "ayam-hutan"];
    const res = berburu.evaluateBagProfit(bag, 5, true);
    assert.equal(res.jumlah, 5);
    assert.equal(res.omzetKoin, 29);
    assert.equal(res.biayaIzin, 5);
    assert.equal(res.biayaPeluru, 0.5);
    assert.equal(res.netProfit, 23.5);
    assert.equal(res.totalPorsi, 13);
  });

  await t.test("evaluateBagProfit shows loss when hunting only hama (tupai/tikus) with izin", () => {
    const bag = ["tupai-kelapa", "tupai-kelapa", "tikus-sawah", "tikus-sawah", "tikus-sawah"];
    const res = berburu.evaluateBagProfit(bag, 5, true);
    assert.equal(res.omzetKoin, 3.4);
    assert.equal(res.netProfit, -2.1);
    assert.equal(res.totalPorsi, 0);
  });

  await t.test("selectBestTarget prioritizes charging boar, then clear LOS high-ROI target", () => {
    const animals = [
      { i: 1, jenis: "ayam-hutan", dist: 15, hidup: true, los: true, energiSampai: 0.9, energiKepala: 0.3, keadaan: "tenang" },
      { i: 2, jenis: "babi-hutan", dist: 35, hidup: true, los: true, energiSampai: 0.7, energiKepala: 0.5, keadaan: "tenang" },
      { i: 3, jenis: "babi-hutan", dist: 12, hidup: true, los: false, energiSampai: 0.95, energiKepala: 0.5, keadaan: "tenang" }
    ];
    const best = berburu.selectBestTarget(animals, "high-roi");
    assert.equal(best.i, 2);

    const withCharging = [
      ...animals,
      { i: 4, jenis: "babi-hutan", dist: 20, hidup: true, los: false, energiSampai: 0.8, energiKepala: 0.5, keadaan: "seruduk" }
    ];
    const urgent = berburu.selectBestTarget(withCharging, "high-roi");
    assert.equal(urgent.i, 4);
  });

  await t.test("canAutoShoot enforces safety, scope, cocking, ammo, LOS, and lethal energy", () => {
    const baseSnap = {
      ready: true,
      me: { v: 0 },
      state: { jatuh: false, kokang: null, peluru: 10, teropong: true, bidik: 0.99 }
    };
    const goodTarget = { i: 1, hidup: true, los: true, energiSampai: 0.75, energiKepala: 0.5 };
    assert.equal(berburu.canAutoShoot(baseSnap, goodTarget), true);

    assert.equal(berburu.canAutoShoot({ ...baseSnap, state: { ...baseSnap.state, kokang: 1 } }, goodTarget), false);
    assert.equal(berburu.canAutoShoot({ ...baseSnap, state: { ...baseSnap.state, peluru: 0 } }, goodTarget), false);
    assert.equal(berburu.canAutoShoot({ ...baseSnap, state: { ...baseSnap.state, teropong: false } }, goodTarget), false);
    assert.equal(berburu.canAutoShoot({ ...baseSnap, me: { v: 1.5 } }, goodTarget), false);
    assert.equal(berburu.canAutoShoot(baseSnap, { ...goodTarget, los: false }), false);
    assert.equal(berburu.canAutoShoot(baseSnap, { ...goodTarget, energiSampai: 0.4 }), false);
  });

  await t.test("computeRelativeDirection formats angles into readable Indonesian compass cues", () => {
    assert.equal(berburu.computeRelativeDirection(0), "⬆ Depan");
    assert.equal(berburu.computeRelativeDirection(Math.PI), "⬇ Belakang");
    assert.ok(berburu.computeRelativeDirection(Math.PI / 4).startsWith("⬅ Kiri"));
    assert.ok(berburu.computeRelativeDirection(-Math.PI / 4).startsWith("➡ Kanan"));
  });

  await t.test("clampHudPos keeps HUD inside viewport boundaries", () => {
    const clamped = berburu.clampHudPos(-50, 900, 320, 400, 1280, 720);
    assert.equal(clamped.x, 8);
    assert.equal(clamped.y, 312);
  });

  await t.test("decideAutoHuntAction orchestrates dodge, ambil, corpse walk, aim_shoot, and approach", () => {
    const baseState = { jatuh: false, ambil: null, peluru: 10, kokang: null, teropong: true };
    const snapWalk = {
      ready: true,
      state: baseState,
      animals: [{ i: 1, jenis: "babi-hutan", nama: "Babi hutan", x: 50, z: 60, dist: 70, hidup: true, los: false, energiSampai: 0.4, energiKepala: 0.5, keadaan: "tenang" }]
    };
    const d1 = berburu.decideAutoHuntAction(snapWalk, "high-roi");
    assert.equal(d1.type, "walk");
    assert.equal(d1.walkOpts.run, true);
    assert.equal(d1.walkOpts.crouch, false);

    const snapStealth = {
      ready: true,
      state: baseState,
      animals: [{ i: 1, jenis: "babi-hutan", nama: "Babi hutan", x: 35, z: 35, dist: 42, hidup: true, los: false, energiSampai: 0.7, energiKepala: 0.5, keadaan: "tenang" }]
    };
    const dStealth = berburu.decideAutoHuntAction(snapStealth, "high-roi");
    assert.equal(dStealth.type, "walk");
    assert.equal(dStealth.walkOpts.crouch, true);
    assert.equal(dStealth.walkOpts.run, false);

    const snapNonTargetNear = {
      ready: true,
      state: baseState,
      animals: [
        { i: 1, jenis: "ayam-hutan", nama: "Ayam hutan", x: 10, z: 10, dist: 15, hidup: true, los: true, energiSampai: 0.9, energiKepala: 0.3, keadaan: "tenang" },
        { i: 2, jenis: "babi-hutan", nama: "Babi hutan", x: 50, z: 60, dist: 72, hidup: true, los: false, energiSampai: 0.4, energiKepala: 0.5, keadaan: "tenang" }
      ]
    };
    const dSprintIgnoreAyam = berburu.decideAutoHuntAction(snapNonTargetNear, "babi");
    assert.equal(dSprintIgnoreAyam.type, "walk");
    assert.equal(dSprintIgnoreAyam.walkOpts.run, true);
    assert.equal(dSprintIgnoreAyam.walkOpts.crouch, false);

    const snapShoot = {
      ready: true,
      state: baseState,
      animals: [{ i: 1, jenis: "babi-hutan", nama: "Babi hutan", x: 20, z: 20, dist: 28, hidup: true, los: true, energiSampai: 0.85, energiKepala: 0.5, keadaan: "tenang" }]
    };
    const d2 = berburu.decideAutoHuntAction(snapShoot, "high-roi");
    assert.equal(d2.type, "aim_shoot");

    const snapCorpse = {
      ready: true,
      state: baseState,
      animals: [{ i: 1, jenis: "babi-hutan", nama: "Babi hutan", x: 20, z: 20, dist: 12, hidup: false, keadaan: "mati" }]
    };
    const d3 = berburu.decideAutoHuntAction(snapCorpse, "high-roi");
    assert.equal(d3.type, "walk");
    assert.equal(d3.walkOpts.stopRadius, 1.6);

    const snapAmbil = {
      ready: true,
      state: { ...baseState, ambil: { i: 1, nama: "Babi hutan" } },
      animals: []
    };
    const d4 = berburu.decideAutoHuntAction(snapAmbil, "high-roi");
    assert.equal(d4.type, "ambil");
  });
});
