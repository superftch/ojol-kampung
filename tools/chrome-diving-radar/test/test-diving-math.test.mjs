import test from "node:test";
import assert from "node:assert/strict";

// FNV-1a + SplitMix32 implementation identical to KampungSebelah game engine
function makeRng(a) {
  let e = (function(a) {
    let e = 0x811c9dc5;
    for (let i = 0; i < a.length; i++) {
      e ^= a.charCodeAt(i);
      e = Math.imul(e, 0x1000193);
    }
    return e >>> 0;
  })(a) || 1;
  return () => {
    let a = Math.imul((e = (e + 0x6d2b79f5) | 0) ^ (e >>> 15), 1 | e);
    return (((a = (a + Math.imul(a ^ (a >>> 7), 61 | a)) ^ a) ^ (a >>> 14)) >>> 0) / 0x100000000;
  };
}

const LAUT = { x0: -320, x1: 320, z0: -640, z1: -6, masuk: { x: 0, z: -26 } };
const KERANG_CONFIG = { jumlah: 48, jarak_min: 18, dalam_min: 4 };
const MUTIARA_RULES = { dalam_min_biasa: 18, dalam_min_langka: 40 };

function clamp(val, min, max) {
  return Math.min(max, Math.max(min, val));
}

function smoothstep(e0, e1, x) {
  let t = clamp((x - e0) / (e1 - e0), 0, 1);
  return t * t * (3 - 2 * t);
}

const uBumps = [
  { x: -150, z: -170, r: 46, t: 7 },
  { x: 120, z: -235, r: 52, t: 11 },
  { x: -40, z: -345, r: 40, t: 13 },
  { x: 225, z: -120, r: 38, t: 5 }
];

function getDepth(x, z) {
  let t = clamp((-z - 4) / 620, 0, 1);
  let n = 1.2 + 5.5 * smoothstep(0, 0.2, t) + 28 * smoothstep(0.18, 0.74, t);
  n += Math.sin(0.031 * x + 1.7) * Math.cos(0.027 * z) * 1.5 * smoothstep(0.04, 0.3, t) +
       2.2 * Math.sin(0.011 * x - 0.013 * z) * t;
  for (let b of uBumps) {
    n -= b.t * Math.exp(-((x - b.x) ** 2 + (z - b.z) ** 2) / (b.r * b.r));
  }
  let i = smoothstep(-305, -235, x) * (1 - smoothstep(235, 305, x));
  let s = (z - (-505 + 44 * Math.sin(0.0105 * x + 0.6))) / (34 + 9 * Math.sin(0.021 * x + 2));
  return Math.max(0.9, n + 31 * Math.exp(-s * s) * i);
}

function generateKerang(hari) {
  let rng = makeRng(`diving:kerang:${hari}`);
  let list = [];
  let attempts = 0;
  while (list.length < KERANG_CONFIG.jumlah && attempts++ < 6000) {
    let x = LAUT.x0 + 22 + rng() * (LAUT.x1 - LAUT.x0 - 44);
    let z = LAUT.z0 + 22 + rng() * (LAUT.z1 - LAUT.z0 - 60);
    let d = getDepth(x, z);
    let r = rng();
    if (d < KERANG_CONFIG.dalam_min) continue;
    if (r > 0.3 + 0.7 * Math.min(1, d / 36)) continue;
    if (Math.hypot(x - LAUT.masuk.x, z - LAUT.masuk.z) < 40) continue;
    if (list.some(k => Math.hypot(k.x - x, k.z - z) < KERANG_CONFIG.jarak_min)) continue;

    let idx = list.length;
    let dRounded = Math.round(10 * d) / 10;
    let putar = Math.round(628 * rng()) / 100;
    let besar = Math.round((0.85 + 0.5 * rng()) * 100) / 100;

    let kategori = "kosong";
    let labelKategori = "Cetek (<18m) - Pasti Kosong";
    let badgeColor = "#718096";

    if (dRounded >= MUTIARA_RULES.dalam_min_langka) {
      kategori = "langka";
      labelKategori = "Palung (≥40m) - Mutiara Langka 300 Koin!";
      badgeColor = "#b794f4";
    } else if (dRounded >= MUTIARA_RULES.dalam_min_biasa) {
      kategori = "biasa";
      labelKategori = "Dalam (≥18m) - Mutiara Biasa 100 Koin";
      badgeColor = "#ecc94b";
    }

    list.push({
      i: idx,
      x: Math.round(10 * x) / 10,
      z: Math.round(10 * z) / 10,
      d: dRounded,
      putar,
      besar,
      kategori,
      labelKategori,
      badgeColor
    });
  }
  return list;
}

test("Diving Terrain & Shell Generation Math", async (t) => {
  await t.test("PRNG generates deterministic sequence", () => {
    const rng1 = makeRng("test_seed");
    const rng2 = makeRng("test_seed");
    for (let i = 0; i < 20; i++) {
      assert.equal(rng1(), rng2(), "PRNG must be 100% deterministic");
    }
  });

  await t.test("getDepth calculates reasonable bathymetry", () => {
    // Shore entrance (z = -26) should be shallow
    const depthEntrance = getDepth(0, -26);
    assert.ok(depthEntrance >= 0.9 && depthEntrance < 5, "Entrance should be shallow water");

    // Deep trench (z < -450) should be deep
    const depthTrench = getDepth(0, -500);
    assert.ok(depthTrench > 25, "Deep trench should be > 25m");
  });

  await t.test("Generates exactly 48 shells with correct bounds", () => {
    const shells = generateKerang("2026-11-23");
    assert.equal(shells.length, 48, "Must generate exactly 48 shells");

    for (const shell of shells) {
      assert.ok(shell.x >= LAUT.x0 && shell.x <= LAUT.x1, `Shell X out of bounds: ${shell.x}`);
      assert.ok(shell.z >= LAUT.z0 && shell.z <= LAUT.z1, `Shell Z out of bounds: ${shell.z}`);
      assert.ok(shell.d >= KERANG_CONFIG.dalam_min, `Shell depth too shallow: ${shell.d}`);
    }

    // Verify Kerang #0 and #21 coordinates for 2026-11-23 match game engine
    const k0 = shells[0];
    assert.equal(k0.i, 0);
    assert.equal(k0.x, -119.6);
    assert.equal(k0.z, -411.7);
    assert.equal(k0.d, 31.8);

    const k21 = shells[21];
    assert.equal(k21.i, 21);
    assert.equal(k21.x, 277.7);
    assert.equal(k21.z, -590);
    assert.equal(k21.d, 34.6);
  });

  await t.test("Shell categorization accurately flags 300 koin and 100 koin", () => {
    const shells = generateKerang("2026-11-23");
    const rare = shells.filter(s => s.kategori === "langka");
    const common = shells.filter(s => s.kategori === "biasa");
    const empty = shells.filter(s => s.kategori === "kosong");

    assert.ok(rare.length > 0, "Should have at least 1 rare 300-koin shell");
    assert.ok(common.length > 0, "Should have common 100-koin shells");
    assert.equal(rare.length + common.length + empty.length, 48);

    for (const s of rare) {
      assert.ok(s.d >= 40, "Rare shell must be at depth >= 40m");
    }
    for (const s of common) {
      assert.ok(s.d >= 18 && s.d < 40, "Common shell must be at 18m <= depth < 40m");
    }
    for (const s of empty) {
      assert.ok(s.d < 18, "Empty shell must be at depth < 18m");
    }
  });
});
