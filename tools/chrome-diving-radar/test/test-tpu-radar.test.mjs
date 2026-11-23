import { describe, it } from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const tpuModulePath = path.resolve(__dirname, "../tpu.js");

// Import modul tpu.js via dynamic ESM import
await import(tpuModulePath);
const tpu = globalThis.__KS_TPU_MODULE;

describe("TPU & Pusaka Mbah Rukmi Radar Engine", () => {
  it("BENDA_TPU contains exactly 12 official objects (7 inside, 5 outside)", () => {
    assert.strictEqual(tpu.BENDA_TPU.length, 12);
    const inside = tpu.BENDA_TPU.filter(b => !b.luar);
    const outside = tpu.BENDA_TPU.filter(b => b.luar);
    assert.strictEqual(inside.length, 7, "Inside house must be 7 objects");
    assert.strictEqual(outside.length, 5, "Outside yard must be 5 objects");

    const expectedInsideIds = ["dipan", "lemari", "peti", "tungku", "gentong", "meja", "bale"];
    const expectedOutsideIds = ["tong", "kayu", "kandang", "lesung", "sumur"];

    for (const id of expectedInsideIds) {
      assert.ok(inside.some(b => b.id === id), `Missing inside object: ${id}`);
    }
    for (const id of expectedOutsideIds) {
      assert.ok(outside.some(b => b.id === id), `Missing outside object: ${id}`);
    }
  });

  it("Bounding boxes and interaction coordinates match game module specs", () => {
    const sumur = tpu.BENDA_TPU.find(b => b.id === "sumur");
    assert.ok(sumur);
    assert.strictEqual(sumur.kotak.x0, 38.55);
    assert.strictEqual(sumur.kotak.x1, 40.45);
    assert.strictEqual(sumur.kotak.y0, 20.55);
    assert.strictEqual(sumur.kotak.y1, 22.45);

    const lemari = tpu.BENDA_TPU.find(b => b.id === "lemari");
    assert.ok(lemari);
    assert.strictEqual(lemari.kotak.x0, 49.55);
    assert.strictEqual(lemari.kotak.x1, 50.3);
  });

  it("distanceToBox accurately computes distance to interactable bounding box", () => {
    const box = { x0: 10, y0: 10, x1: 20, y1: 20 };
    // Inside box
    assert.strictEqual(tpu.distanceToBox(15, 15, box), 0);
    // Directly 2 units above
    assert.strictEqual(tpu.distanceToBox(15, 8, box), 2);
    // Directly 3 units to the right
    assert.strictEqual(tpu.distanceToBox(23, 15, box), 3);
    // Diagonal distance (3, 4 -> 5)
    assert.strictEqual(tpu.distanceToBox(23, 24, box), 5);
  });

  it("checkJamAngker identifies Jam Angker (23:00 - 03:00 WIB) accurately", () => {
    // 23:30 WIB -> Jam Angker
    const d2330 = new Date("2026-11-23T16:30:00Z"); // 16:30 UTC = 23:30 WIB
    const res2330 = tpu.checkJamAngker(d2330);
    assert.strictEqual(res2330.hour, 23);
    assert.strictEqual(res2330.min, 30);
    assert.strictEqual(res2330.isAngker, true);

    // 01:15 WIB -> Jam Angker
    const d0115 = new Date("2026-11-23T18:15:00Z"); // 18:15 UTC = 01:15 WIB
    const res0115 = tpu.checkJamAngker(d0115);
    assert.strictEqual(res0115.hour, 1);
    assert.strictEqual(res0115.isAngker, true);

    // 14:00 WIB -> Bukan Jam Angker
    const d1400 = new Date("2026-11-23T07:00:00Z"); // 07:00 UTC = 14:00 WIB
    const res1400 = tpu.checkJamAngker(d1400);
    assert.strictEqual(res1400.hour, 14);
    assert.strictEqual(res1400.isAngker, false);

    // 22:59 WIB -> Bukan Jam Angker (belum mulai)
    const d2259 = new Date("2026-11-23T15:59:00Z"); // 15:59 UTC = 22:59 WIB
    const res2259 = tpu.checkJamAngker(d2259);
    assert.strictEqual(res2259.hour, 22);
    assert.strictEqual(res2259.isAngker, false);
  });

  it("getOptimalSearchRoute prioritizes logical traversal progression", () => {
    const unsearched = ["gentong", "sumur", "dipan", "tong"];
    const route = tpu.getOptimalSearchRoute([...unsearched]);
    // sumur is first in outside yard, then tong, then dipan, then gentong (inside back kitchen)
    assert.deepStrictEqual(route, ["sumur", "tong", "dipan", "gentong"]);
  });
});
