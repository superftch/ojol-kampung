#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const extDir = path.resolve(__dirname, "..");
const envTestingPath = path.resolve(extDir, ".env.testing");

console.log("=================================================");
console.log("  KampungSebelah Extension Test Runner (Isolated)");
console.log("=================================================");

// 1. Verify dedicated extension .env.testing exists and load it
if (!fs.existsSync(envTestingPath)) {
  console.error("❌ ERROR: .env.testing not found in extension directory:", envTestingPath);
  console.error("Please copy .env.testing.example to .env.testing before running tests.");
  process.exit(1);
}

const envContent = fs.readFileSync(envTestingPath, "utf-8");
const envVars = {};
for (const line of envContent.split("\n")) {
  const trimmed = line.trim();
  if (trimmed && !trimmed.startsWith("#") && trimmed.includes("=")) {
    const [k, ...v] = trimmed.split("=");
    envVars[k.trim()] = v.join("=").trim();
  }
}

console.log("✅ Loaded extension test env:", {
  EXTENSION_TEST_ENV: envVars.EXTENSION_TEST_ENV || "unknown",
  TEST_DATE_WIB: envVars.TEST_DATE_WIB || "unknown",
  SHELL_COUNT_EXPECTED: envVars.SHELL_COUNT_EXPECTED || "unknown"
});

// 2. Discover test files in test/
const testFiles = fs.readdirSync(__dirname)
  .filter(f => f.endsWith(".test.mjs"))
  .map(f => path.resolve(__dirname, f));

console.log(`📋 Running ${testFiles.length} isolated test suites...`);

// 3. Execute node --test
const child = spawn(process.execPath, ["--test", ...testFiles], {
  cwd: extDir,
  env: {
    ...process.env,
    ...envVars,
    NODE_ENV: "test"
  },
  stdio: "inherit"
});

child.on("close", (code) => {
  if (code === 0) {
    console.log("\n🎉 All Extension Tests Passed Successfully! (100% Isolated)");
  } else {
    console.error(`\n❌ Extension Tests Failed with exit code ${code}`);
  }
  process.exit(code);
});
