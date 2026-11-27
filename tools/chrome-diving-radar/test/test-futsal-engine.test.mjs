import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
await import(path.resolve(__dirname, "../futsal.js"));
const futsal = globalThis.__KS_FUTSAL_MODULE;

test("worldDirToJoystick maps world direction using camera basis", () => {
  // Default broadcast camera looking along -Z (atas = (0, -1), kanan = (1, 0))
  const cam = { kananX: 1, kananZ: 0, atasX: 0, atasZ: -1 };
  const right = futsal.worldDirToJoystick(1, 0, cam, 0.8);
  assert.equal(right.jx, 0.8);
  assert.equal(right.jy, 0);

  const forward = futsal.worldDirToJoystick(0, -1, cam, 0.8);
  assert.equal(forward.jx, 0);
  assert.equal(forward.jy, -0.8);

  // Rotated camera looking along +X (atas = (1, 0), kanan = (0, 1))
  const camSide = { kananX: 0, kananZ: 1, atasX: 1, atasZ: 0 };
  const attackPlusX = futsal.worldDirToJoystick(1, 0, camSide, 0.8);
  assert.equal(attackPlusX.jx, 0);
  assert.equal(attackPlusX.jy, -0.8);
});

test("computeFutsalDecision shoots at close range (<=7.5m) and dribbles closer from 9.5m when unpressed", () => {
  const farState = {
    fase: "main",
    bola: { x: 10.5, y: 0.11, z: 0, vx: 0, vz: 0, pemilik: 1 },
    pemain: [
      { id: 0, tim: 0, kiper: true, x: -19, z: 0, vx: 0, vz: 0, stamina: 1 },
      { id: 1, tim: 0, kiper: false, x: 10.5, z: 0, vx: 0, vz: 0, stamina: 1 },
      { id: 2, tim: 1, kiper: true, x: 19.2, z: 0.8, vx: 0, vz: 0, stamina: 1 }
    ]
  };
  const decFar = futsal.computeFutsalDecision(farState, 1, { rng: () => 0.5 });
  assert.equal(decFar.role, "dribble", "keeps dribbling closer instead of shooting from 9.5m");

  const closeState = {
    fase: "main",
    bola: { x: 13.5, y: 0.11, z: 0, vx: 0, vz: 0, pemilik: 1 },
    pemain: [
      { id: 0, tim: 0, kiper: true, x: -19, z: 0, vx: 0, vz: 0, stamina: 1 },
      { id: 1, tim: 0, kiper: false, x: 13.5, z: 0, vx: 0, vz: 0, stamina: 1 },
      { id: 2, tim: 1, kiper: true, x: 19.2, z: 0.8, vx: 0, vz: 0, stamina: 1 }
    ]
  };
  const dec = futsal.computeFutsalDecision(closeState, 1, { rng: () => 0.5 });
  assert.equal(dec.role, "shoot");
  assert.equal(dec.kick, "tembak");
  assert.equal(dec.targetX, 20);
  assert.equal(dec.targetZ, -1.2); // furthest corner from GK at z=0.8
  // Aim vector must be angled ~26 deg off center (-z side) to beat bantu_bidik
  assert.ok(dec.moveZ < -0.35, "shoot aim compensates ~26 deg toward open corner");
  assert.ok(dec.chargeMs >= 180 && dec.chargeMs <= 710, "chargeMs stays safely below 850ms red ring");
});

test("computeFutsalDecision switches corner or dribbles if teammate/opponent blocks shot lane", () => {
  // Teammate blocks -1.2 corner lane -> switches to +1.2 corner
  const oneBlocked = {
    fase: "main",
    bola: { x: 13, y: 0.11, z: 0, vx: 0, vz: 0, pemilik: 1 },
    pemain: [
      { id: 1, tim: 0, kiper: false, x: 13, z: 0, vx: 0, vz: 0, stamina: 1 },
      { id: 2, tim: 0, kiper: false, x: 16, z: -0.6, vx: 0, vz: 0, stamina: 1 }, // teammate in -Z lane
      { id: 3, tim: 1, kiper: true, x: 19.2, z: 0.5, vx: 0, vz: 0, stamina: 1 }
    ]
  };
  const decAlt = futsal.computeFutsalDecision(oneBlocked, 1, { rng: () => 0.5 });
  assert.equal(decAlt.role, "shoot");
  assert.equal(decAlt.targetZ, 1.2);

  // Both lanes blocked (teammate on -Z, opponent on +Z) -> juke/dribble instead of shooting
  const bothBlocked = {
    fase: "main",
    bola: { x: 13, y: 0.11, z: 0, vx: 0, vz: 0, pemilik: 1 },
    pemain: [
      { id: 1, tim: 0, kiper: false, x: 13, z: 0, vx: 0, vz: 0, stamina: 1 },
      { id: 2, tim: 0, kiper: false, x: 16, z: -0.6, vx: 0, vz: 0, stamina: 1 },
      { id: 4, tim: 1, kiper: false, x: 15.5, z: 0.6, vx: 0, vz: 0, stamina: 1 },
      { id: 3, tim: 1, kiper: true, x: 19.2, z: 0.5, vx: 0, vz: 0, stamina: 1 }
    ]
  };
  const decBlocked = futsal.computeFutsalDecision(bothBlocked, 1, { rng: () => 0.5 });
  assert.notEqual(decBlocked.role, "shoot");
  assert.equal(decBlocked.kick, null);
});

test("selectShotVariation varies shot power by distance and wrong-foots moving keeper", () => {
  const me = { id: 1, tim: 0, stamina: 0.9 };
  const tapIn = futsal.selectShotVariation(
    { pemain: [{ id: 2, tim: 1, kiper: true, z: 0.5, vz: 0 }] },
    me,
    3.2,
    { x: 20, z: -1.2 },
    { rng: () => 0.5 }
  );
  assert.equal(tapIn.shotType, "Quick Tap");
  assert.ok(tapIn.chargeMs <= 280);

  const closeTop = futsal.selectShotVariation(
    { pemain: [{ id: 2, tim: 1, kiper: true, z: 0.5, vz: 0 }] },
    me,
    4.5,
    { x: 20, z: -1.2 },
    { rng: () => 0.5 }
  );
  assert.equal(closeTop.shotType, "Top Shelf");
  assert.ok(closeTop.chargeMs >= 390 && closeTop.chargeMs <= 520);

  const long = futsal.selectShotVariation(
    { pemain: [{ id: 2, tim: 1, kiper: true, z: 0.2, vz: 1.5 }] },
    me,
    11.5,
    { x: 20, z: 1.2 },
    { rng: () => 0.5 }
  );
  assert.equal(long.shotType, "Power Rocket");
  assert.equal(long.targetZ, -1.25); // GK moving +Z (vz=1.5), wrong-foot to -Z
  assert.ok(long.chargeMs >= 480 && long.chargeMs <= 710);
});

test("computeFutsalDecision jukes past opponent in solo mode and passes in team mode", () => {
  const state = {
    fase: "main",
    bola: { x: -5, y: 0.11, z: 0, vx: 0, vz: 0, pemilik: 1 },
    pemain: [
      { id: 1, tim: 0, kiper: false, x: -5, z: 0, vx: 0, vz: 0, stamina: 1 },
      { id: 2, tim: 0, kiper: false, x: 4, z: -4, vx: 0, vz: 0, stamina: 1 },
      { id: 3, tim: 1, kiper: false, x: -3.5, z: 0.4, vx: 0, vz: 0, stamina: 1 },
      { id: 4, tim: 1, kiper: true, x: 19.2, z: 0, vx: 0, vz: 0, stamina: 1 }
    ]
  };

  // Default solo mode: refuses to pass, jukes laterally around opponent & sprints
  const decSolo = futsal.computeFutsalDecision(state, 1);
  assert.equal(decSolo.role, "juke");
  assert.equal(decSolo.kick, null);
  assert.equal(decSolo.kencang, true);
  assert.ok(Math.abs(decSolo.moveZ) > 0.5, "cuts laterally away from defender");

  // Explicit team mode: passes to open forward teammate
  const decTeam = futsal.computeFutsalDecision(state, 1, { style: "team" });
  assert.equal(decTeam.role, "pass");
  assert.equal(decTeam.kick, "oper");
  assert.equal(decTeam.targetX, 4);
  assert.equal(decTeam.targetZ, -4);
});

test("computeFutsalDecision tackles from front/side within 0.82m and flanks when behind", () => {
  const tackleState = {
    fase: "main",
    bola: { x: 2.5, y: 0.11, z: 1.0, vx: 0, vz: 0, pemilik: 3 },
    pemain: [
      { id: 1, tim: 0, kiper: false, x: 3.1, z: 1.1, vx: 0, vz: 0, stamina: 0.9, rebutT: 0, huyungT: 0 },
      { id: 3, tim: 1, kiper: false, x: 2.5, z: 1.0, vx: 0, vz: 0, arah: 0, stamina: 0.9 }
    ]
  };

  const decTackle = futsal.computeFutsalDecision(tackleState, 1);
  assert.equal(decTackle.role, "tackle");
  assert.equal(decTackle.kick, "oper");

  // Directly behind opponent facing +X (arah=0) at 0.7m -> should flank ahead, not waste tackle from behind
  const behindState = {
    fase: "main",
    bola: { x: 2.5, y: 0.11, z: 1.0, vx: 0, vz: 0, pemilik: 3 },
    pemain: [
      { id: 1, tim: 0, kiper: false, x: 1.8, z: 1.0, vx: 0, vz: 0, stamina: 0.9, rebutT: 0, huyungT: 0 },
      { id: 3, tim: 1, kiper: false, x: 2.5, z: 1.0, vx: 0, vz: 0, arah: 0, stamina: 0.9 }
    ]
  };

  const decBehind = futsal.computeFutsalDecision(behindState, 1);
  assert.equal(decBehind.role, "chase");
  assert.equal(decBehind.kick, null);
  assert.ok(decBehind.targetX > 2.5, "cuts ahead of opponent instead of chasing from behind");

  const chaseState = {
    fase: "main",
    bola: { x: 8, y: 0.11, z: 3, vx: 1, vz: 0, pemilik: -1 },
    pemain: [{ id: 1, tim: 0, kiper: false, x: 0, z: 0, vx: 0, vz: 0, stamina: 0.8 }]
  };

  const decChase = futsal.computeFutsalDecision(chaseState, 1);
  assert.equal(decChase.role, "chase");
  assert.equal(decChase.kick, null);
  assert.equal(decChase.kencang, true);
});

test("computeFutsalDecision makes support run when teammate holds ball", () => {
  const state = {
    fase: "main",
    bola: { x: 0, y: 0.11, z: 3, vx: 0, vz: 0, pemilik: 2 },
    pemain: [
      { id: 1, tim: 0, kiper: false, x: -4, z: 0, vx: 0, vz: 0, stamina: 1 },
      { id: 2, tim: 0, kiper: false, x: 0, z: 3, vx: 0, vz: 0, stamina: 1 }
    ]
  };

  const dec = futsal.computeFutsalDecision(state, 1);
  assert.equal(dec.role, "support");
  assert.equal(dec.targetX, 6.5);
  assert.equal(dec.targetZ, -4.5);
});

test("computeFutsalDecision walks to center during gol phase and stops near (0,0)", () => {
  const golFarState = {
    fase: "gol",
    bola: { x: 20.3, y: 0.2, z: 0.4, vx: 0, vz: 0, pemilik: -1 },
    pemain: [{ id: 1, tim: 0, kiper: false, x: 10, z: 3, vx: 0, vz: 0, stamina: 1 }]
  };

  const decFar = futsal.computeFutsalDecision(golFarState, 1);
  assert.equal(decFar.role, "reset");
  assert.equal(decFar.targetX, 0);
  assert.equal(decFar.targetZ, 0);
  assert.equal(decFar.moveX, -10);
  assert.equal(decFar.moveZ, -3);
  assert.equal(decFar.kencang, false);
  assert.equal(decFar.kick, null);

  const golNearState = {
    fase: "gol",
    bola: { x: 20.3, y: 0.2, z: 0.4, vx: 0, vz: 0, pemilik: -1 },
    pemain: [{ id: 1, tim: 0, kiper: false, x: 0.3, z: -0.2, vx: 0, vz: 0, stamina: 1 }]
  };

  const decNear = futsal.computeFutsalDecision(golNearState, 1);
  assert.equal(decNear.role, "idle");
  assert.equal(decNear.moveX, 0);
  assert.equal(decNear.moveZ, 0);
});

test("computeFutsalDecision does not tackle or rush when opponent keeper holds ball", () => {
  const gkHoldState = {
    fase: "main",
    bola: { x: 19.0, y: 0.8, z: 0.5, vx: 0, vz: 0, pemilik: 2 },
    pemain: [
      { id: 1, tim: 0, kiper: false, x: 18.6, z: 0.5, vx: 0, vz: 0, stamina: 1, rebutT: 0, huyungT: 0 },
      { id: 2, tim: 1, kiper: true, x: 19.2, z: 0.5, vx: 0, vz: 0, stamina: 1 }
    ]
  };

  const dec = futsal.computeFutsalDecision(gkHoldState, 1);
  assert.equal(dec.role, "contain");
  assert.equal(dec.kick, null);
  assert.ok(dec.targetX < 18, "backs off from keeper box to intercept throw");
});
