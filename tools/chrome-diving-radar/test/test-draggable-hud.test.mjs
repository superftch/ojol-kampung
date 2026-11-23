import test from "node:test";
import assert from "node:assert/strict";

// Pure logic unit testing of Draggable HUD positioning, boundary clamping, and persistence
function computeClampedPosition(elemX, elemY, deltaX, deltaY, elemW, elemH, winW, winH) {
  const newX = elemX + deltaX;
  const newY = elemY + deltaY;
  const maxLeft = Math.max(0, winW - elemW);
  const maxTop = Math.max(0, winH - elemH);
  const clampX = Math.max(0, Math.min(newX, maxLeft));
  const clampY = Math.max(0, Math.min(newY, maxTop));
  return { left: clampX, top: clampY };
}

function restoreClampedPosition(savedPos, elemW, elemH, winW, winH) {
  if (!savedPos || typeof savedPos.left !== "number" || typeof savedPos.top !== "number") {
    return null;
  }
  const maxLeft = Math.max(0, winW - elemW);
  const maxTop = Math.max(0, winH - elemH);
  const clampX = Math.max(0, Math.min(savedPos.left, maxLeft));
  const clampY = Math.max(0, Math.min(savedPos.top, maxTop));
  return { left: clampX, top: clampY };
}

test("Draggable HUD - Free Move, Boundary Clamping & Persistence", async (t) => {
  await t.test("Clamps HUD within viewport when dragged inside boundaries", () => {
    const pos = computeClampedPosition(100, 100, 50, 75, 300, 400, 1920, 1080);
    assert.equal(pos.left, 150);
    assert.equal(pos.top, 175);
  });

  await t.test("Prevents HUD from going beyond left and top borders (negative coordinates)", () => {
    const pos = computeClampedPosition(50, 50, -200, -150, 330, 500, 1920, 1080);
    assert.equal(pos.left, 0, "Left should be clamped to 0");
    assert.equal(pos.top, 0, "Top should be clamped to 0");
  });

  await t.test("Prevents HUD from going beyond right and bottom screen edges", () => {
    // winW: 1000, winH: 800, elemW: 300, elemH: 200 => maxLeft: 700, maxTop: 600
    const pos = computeClampedPosition(600, 500, 300, 300, 300, 200, 1000, 800);
    assert.equal(pos.left, 700, "Left should not exceed winW - elemW (700)");
    assert.equal(pos.top, 600, "Top should not exceed winH - elemH (600)");
  });

  await t.test("Restores and clamps saved position from localStorage within screen bounds", () => {
    const mockStorage = {
      ks_hud_pos_diving_radar: JSON.stringify({ left: 1600, top: 40 }),
      ks_hud_pos_compass: JSON.stringify({ left: 500, top: 20 }),
      ks_hud_pos_mancing: JSON.stringify({ left: 3000, top: 2000 }) // Out of bounds
    };

    const radarPos = restoreClampedPosition(
      JSON.parse(mockStorage.ks_hud_pos_diving_radar),
      330, 500, 1920, 1080
    );
    assert.ok(radarPos);
    assert.equal(radarPos.left, 1590, "Clamped to max 1920 - 330 = 1590");
    assert.equal(radarPos.top, 40);

    const compassPos = restoreClampedPosition(
      JSON.parse(mockStorage.ks_hud_pos_compass),
      350, 55, 1920, 1080
    );
    assert.ok(compassPos);
    assert.equal(compassPos.left, 500);
    assert.equal(compassPos.top, 20);

    // Out-of-bounds pos gets clamped to max available screen coordinates
    const mancingPos = restoreClampedPosition(
      JSON.parse(mockStorage.ks_hud_pos_mancing),
      290, 450, 1920, 1080
    );
    assert.ok(mancingPos);
    assert.equal(mancingPos.left, 1920 - 290);
    assert.equal(mancingPos.top, 1080 - 450);
  });

  await t.test("Handles window resize by re-clamping position if window becomes smaller", () => {
    let currentPos = { left: 1500, top: 800 };
    // User resizes window from 1920x1080 to 1280x720
    const elemW = 330;
    const elemH = 400;
    const resizedWinW = 1280;
    const resizedWinH = 720;

    const maxLeft = Math.max(0, resizedWinW - elemW); // 950
    const maxTop = Math.max(0, resizedWinH - elemH);   // 320

    const clampedX = Math.max(0, Math.min(currentPos.left, maxLeft));
    const clampedY = Math.max(0, Math.min(currentPos.top, maxTop));

    assert.equal(clampedX, 950);
    assert.equal(clampedY, 320);
  });

  await t.test("Drag threshold suppresses accidental clicks when moved > 3px", () => {
    function shouldTriggerDrag(deltaX, deltaY) {
      return Math.hypot(deltaX, deltaY) > 3;
    }

    assert.equal(shouldTriggerDrag(1, 1), false, "Small micro movement <= 3px should not trigger drag");
    assert.equal(shouldTriggerDrag(2, 2), false, "hypot(2,2) = 2.82 <= 3px");
    assert.equal(shouldTriggerDrag(4, 0), true, "4px delta should trigger drag");
    assert.equal(shouldTriggerDrag(0, 5), true, "5px delta should trigger drag");
  });

  await t.test("Interactive elements filter prevents dragging buttons, inputs, and selects", () => {
    function isInteractiveTag(tagName) {
      const interactive = ["BUTTON", "INPUT", "SELECT", "TEXTAREA", "A"];
      return interactive.includes(tagName.toUpperCase());
    }

    assert.equal(isInteractiveTag("BUTTON"), true);
    assert.equal(isInteractiveTag("INPUT"), true);
    assert.equal(isInteractiveTag("DIV"), false);
    assert.equal(isInteractiveTag("SPAN"), false);
  });
});
