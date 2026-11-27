import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const kebutuhanModulePath = path.resolve(__dirname, "../kebutuhan.js");

await import(kebutuhanModulePath);
const keb = globalThis.__KS_KEBUTUHAN_ENGINE__ || {};

const {
  CHARACTER_NEEDS,
  OJOL_NEEDS,
  parseKebutuhanResponse,
  parseOjolBarsResponse,
  evaluateAllKebutuhan,
  solveNampanPicks,
  solveFotoShots,
  solveGymHolds,
  pickBestShopItem
} = keb;

test("Auto-Kebutuhan Engine (Karakter & Ojol) - Unit Tests", async (t) => {
  await t.test("parseKebutuhanResponse handles needs array and kondisi/bersih", () => {
    const parsed = parseKebutuhanResponse({
      enabled: true,
      asleep: false,
      needs: [
        { id: "makan", value: 42 },
        { id: "kesehatan", value: 88 },
        { id: "wc", value: 15 }
      ],
      bersih: { mandi: 1, mandiMaks: 2, sikat: 0, sikatMaks: 3 },
      kondisi: { bau: false, kebelet: true }
    });
    assert.equal(parsed.asleep, false);
    assert.equal(parsed.needs.makan, 42);
    assert.equal(parsed.needs.kesehatan, 88);
    assert.equal(parsed.needs.wc, 15);
    assert.equal(parsed.kondisi.kebelet, true);
    assert.equal(parsed.bersih.mandi, 1);
  });

  await t.test("evaluateAllKebutuhan returns empty when asleep", () => {
    const charData = { asleep: true, needs: { makan: 10, wc: 5 }, kondisi: { kebelet: true } };
    const ojolData = { trip: null, bars: { bensin: 5, kendaraan: 10, kuota: 5 } };
    const queue = evaluateAllKebutuhan(charData, ojolData, { autoOjolNeeds: true });
    assert.deepEqual(queue, []);
  });

  await t.test("evaluateAllKebutuhan evaluates both Ojol and Karakter needs", () => {
    const charData = {
      asleep: false,
      needs: { makan: 30, kesehatan: 90, fisik: 80, rekreasi: 80, kebersihan: 80, wc: 80, penampilan: 80, rumah: 80 },
      kondisi: { bau: false, kebelet: false }
    };
    const ojolData = {
      trip: null,
      bars: { bensin: 15, kendaraan: 80, kuota: 90 }
    };
    const queue = evaluateAllKebutuhan(charData, ojolData, {
      autoOjolNeeds: true,
      defaultCharThreshold: 50
    });
    const resources = queue.map(q => q.resource);
    assert.ok(resources.includes("bensin"), "Should include critical bensin");
    assert.ok(resources.includes("makan"), "Should include low makan");
    assert.ok(!resources.includes("kesehatan"), "Healthy kesehatan should not be included");
  });

  await t.test("evaluateAllKebutuhan skips Ojol needs during active trip", () => {
    const charData = { asleep: false, needs: { makan: 90 }, kondisi: {} };
    const ojolData = {
      trip: { id: "trip-1" },
      bars: { bensin: 10, kendaraan: 10, kuota: 10 }
    };
    const queue = evaluateAllKebutuhan(charData, ojolData, { autoOjolNeeds: true });
    assert.equal(queue.length, 0);
  });

  await t.test("evaluateAllKebutuhan forces wc/kebersihan when kebelet/bau is true", () => {
    const charData = {
      asleep: false,
      needs: { wc: 75, kebersihan: 75 },
      kondisi: { kebelet: true, bau: true }
    };
    const queue = evaluateAllKebutuhan(charData, null, { defaultCharThreshold: 50 });
    const resources = queue.map(q => q.resource);
    assert.ok(resources.includes("wc"));
    assert.ok(resources.includes("kebersihan"));
  });

  await t.test("solveNampanPicks picks balanced 5-group healthy items avoiding junk", () => {
    const items = [
      { id: "gorengan" },
      { id: "mi-instan" },
      { id: "nasi" },
      { id: "ayam" },
      { id: "bayam" },
      { id: "pisang" },
      { id: "susu" },
      { id: "es-sirup" }
    ];
    const picks = solveNampanPicks(items, 5);
    assert.equal(picks.length, 5);
    assert.deepEqual(picks, ["nasi", "ayam", "bayam", "pisang", "susu"]);
  });

  await t.test("solveFotoShots & solveGymHolds compute exact target timings", () => {
    assert.deepEqual(solveFotoShots([2000, 1600], 600), [1100, 1000]);
    assert.deepEqual(solveGymHolds([{ fill: 1000, center: 0.7 }, { fill: 1400, center: 0.5 }]), [700, 700]);
  });

  await t.test("pickBestShopItem chooses lowest cost per usable gain point", () => {
    const menu = [
      { id: "mahal", name: "Steak", priceMilli: 5000, service: true, rasa: { isi: { makan: 50 } } },
      { id: "hemat", name: "Nasi Uduk", priceMilli: 800, service: true, rasa: { isi: { makan: 40 } } },
      { id: "habis", name: "Bubur", priceMilli: 200, stock: 0, service: true, rasa: { isi: { makan: 40 } } },
      { id: "simpan", name: "Beras", priceMilli: 300, service: false, eaten: false, effects: { makan: 50 } }
    ];
    const best = pickBestShopItem(menu, "makan", 40);
    assert.ok(best);
    assert.equal(best.id, "hemat");
  });

  await t.test("parseOjolBarsResponse handles /api/ojol shape", () => {
    const ojol = parseOjolBarsResponse({
      enabled: true,
      mitra: true,
      vehicle: "mobil",
      trip: null,
      bars: { bensin: 45, kendaraan: 70, kuota: 80 }
    });
    assert.equal(ojol.vehicle, "mobil");
    assert.equal(ojol.bars.bensin, 45);
    assert.equal(ojol.bars.kendaraan, 70);
    assert.equal(ojol.bars.kuota, 80);
  });

  await t.test("CHARACTER_NEEDS and OJOL_NEEDS cover all 11 needs", () => {
    assert.equal(CHARACTER_NEEDS.length, 8);
    assert.equal(OJOL_NEEDS.length, 3);
  });
});
