import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const manifestPath = path.resolve(__dirname, "../manifest.json");

test("Manifest V3 Configuration & Schema Validation", async (t) => {
  await t.test("manifest.json exists and is valid JSON", () => {
    assert.ok(fs.existsSync(manifestPath), "manifest.json should exist");
    const raw = fs.readFileSync(manifestPath, "utf-8");
    const manifest = JSON.parse(raw);
    assert.equal(manifest.manifest_version, 3, "Must be Manifest V3");
    assert.equal(typeof manifest.name, "string");
    assert.equal(typeof manifest.version, "string");
  });

  await t.test("manifest permissions and host permissions are correct", () => {
    const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf-8"));
    assert.ok(Array.isArray(manifest.permissions), "permissions should be array");
    assert.ok(manifest.permissions.includes("storage"), "Requires storage permission");

    assert.ok(Array.isArray(manifest.host_permissions), "host_permissions should be array");
    const hasOrigin = manifest.host_permissions.some(h => h.includes("kampungsebelah.com"));
    assert.ok(hasOrigin, "Must have kampungsebelah.com in host_permissions");
  });

  await t.test("content scripts and web accessible resources files exist", () => {
    const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf-8"));
    const cs = manifest.content_scripts?.[0];
    assert.ok(cs, "Should define content_scripts");
    assert.ok(Array.isArray(cs.js), "content_scripts js should be array");

    for (const scriptFile of cs.js) {
      const fullPath = path.resolve(__dirname, "..", scriptFile);
      assert.ok(fs.existsSync(fullPath), `Content script ${scriptFile} must exist on disk`);
    }

    const war = manifest.web_accessible_resources?.[0];
    assert.ok(war, "Should define web_accessible_resources");
    for (const res of war.resources) {
      const fullPath = path.resolve(__dirname, "..", res);
      assert.ok(fs.existsSync(fullPath), `Web accessible resource ${res} must exist on disk`);
    }
  });
});
