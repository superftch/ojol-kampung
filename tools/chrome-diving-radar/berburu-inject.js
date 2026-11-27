// KampungSebelah Berburu Radar & Sniper - Main World Injector (v2.4.0)
// Mengaitkan langsung ke instance 3D Hutan Berburu (class A) untuk radar satwa, LOS pohon, & kalkulator balistik.

(function () {
  if (!window.location.pathname.startsWith("/berburu")) return;
  console.log("[BerburuInject] Main world injector initializing...");

  const SENAPAN = {
    laju: 270,
    redam_m: 135,
    nol_m: 25,
    gravitasi: 9.81,
    angin: 0.9,
    jangkau_m: 160
  };

  function stepBullet(p, dt, wind) {
    const speed = Math.hypot(p.vx, p.vy, p.vz);
    const drag = Math.exp((-speed * dt) / SENAPAN.redam_m);
    const vx2 = p.vx * drag + (wind.x || 0) * SENAPAN.angin * dt;
    const vy2 = p.vy * drag - SENAPAN.gravitasi * dt;
    const vz2 = p.vz * drag + (wind.z || 0) * SENAPAN.angin * dt;
    const x2 = p.x + ((p.vx + vx2) * 0.5) * dt;
    const y2 = p.y + ((p.vy + vy2) * 0.5) * dt;
    const z2 = p.z + ((p.vz + vz2) * 0.5) * dt;
    return {
      x: x2,
      y: y2,
      z: z2,
      vx: vx2,
      vy: vy2,
      vz: vz2,
      t: p.t + dt,
      jarak: p.jarak + Math.hypot(x2 - p.x, y2 - p.y, z2 - p.z)
    };
  }

  let cachedZeroOffset = null;
  function getZeroOffset() {
    if (cachedZeroOffset !== null) return cachedZeroOffset;
    let p = { x: 0, y: 0, z: 0, vx: 0, vy: 0, vz: SENAPAN.laju, t: 0, jarak: 0 };
    const dt = 1 / 480;
    while (p.z < SENAPAN.nol_m && p.t < 3) {
      const next = stepBullet(p, dt, { x: 0, z: 0 });
      if (next.z >= SENAPAN.nol_m) {
        const frac = (SENAPAN.nol_m - p.z) / (next.z - p.z);
        const drop = -(p.y + (next.y - p.y) * frac);
        cachedZeroOffset = Math.atan2(drop, SENAPAN.nol_m);
        return cachedZeroOffset;
      }
      p = next;
    }
    cachedZeroOffset = Math.atan2(-p.y, SENAPAN.nol_m);
    return cachedZeroOffset;
  }

  function simulateToHorizDist(camPos, yaw, launchPitch, targetHorizDist, wind) {
    const cosP = Math.cos(launchPitch);
    let p = {
      x: camPos.x,
      y: camPos.y,
      z: camPos.z,
      vx: Math.sin(yaw) * cosP * SENAPAN.laju,
      vy: Math.sin(launchPitch) * SENAPAN.laju,
      vz: Math.cos(yaw) * cosP * SENAPAN.laju,
      t: 0,
      jarak: 0
    };
    const dt = 1 / 300;
    while (p.t < 2.5 && p.jarak <= SENAPAN.jangkau_m) {
      const next = stepBullet(p, dt, wind);
      const hDistPrev = Math.hypot(p.x - camPos.x, p.z - camPos.z);
      const hDistNext = Math.hypot(next.x - camPos.x, next.z - camPos.z);
      if (hDistNext >= targetHorizDist) {
        const denom = Math.max(1e-6, hDistNext - hDistPrev);
        const frac = (targetHorizDist - hDistPrev) / denom;
        const ix = p.x + (next.x - p.x) * frac;
        const iy = p.y + (next.y - p.y) * frac;
        const iz = p.z + (next.z - p.z) * frac;
        const ivx = p.vx + (next.vx - p.vx) * frac;
        const ivy = p.vy + (next.vy - p.vy) * frac;
        const ivz = p.vz + (next.vz - p.vz) * frac;
        const energy = (ivx * ivx + ivy * ivy + ivz * ivz) / (SENAPAN.laju * SENAPAN.laju);
        return { x: ix, y: iy, z: iz, energy };
      }
      p = next;
    }
    return { x: p.x, y: p.y, z: p.z, energy: 0 };
  }

  function solveBallisticAim(camPos, targetPos, wind) {
    const dx = targetPos.x - camPos.x;
    const dy = targetPos.y - camPos.y;
    const dz = targetPos.z - camPos.z;
    const horizDist = Math.hypot(dx, dz);
    if (horizDist < 0.2) {
      return { yaw: 0, pitch: 0, energy: 1, horizDist };
    }
    const zero = getZeroOffset();
    let yaw = Math.atan2(dx, dz);
    let pitch = Math.atan2(dy, horizDist) - zero;
    let energy = 1;

    for (let iter = 0; iter < 5; iter++) {
      const sim = simulateToHorizDist(camPos, yaw, pitch + zero, horizDist, wind);
      energy = sim.energy;
      const simYaw = Math.atan2(sim.x - camPos.x, sim.z - camPos.z);
      const yawErr = Math.atan2(Math.sin(yaw - simYaw), Math.cos(yaw - simYaw));
      const targetYaw = Math.atan2(dx, dz);
      yaw = targetYaw + yawErr;
      const yErr = targetPos.y - sim.y;
      pitch += Math.atan2(yErr, horizDist);
    }

    return { yaw, pitch, energy, horizDist };
  }

  function isValidBerburuInstance(inst) {
    return Boolean(
      inst &&
      Array.isArray(inst.satwa) &&
      typeof inst.tembak === "function" &&
      typeof inst.keadaan === "function" &&
      inst.me &&
      inst.cam &&
      (!inst.renderer?.domElement || inst.renderer.domElement.isConnected)
    );
  }

  function scanBerburuFiber() {
    if (isValidBerburuInstance(window.__KS_BERBURU_INSTANCE)) return window.__KS_BERBURU_INSTANCE;
    window.__KS_BERBURU_INSTANCE = null;

    try {
      const candidates = [
        document.querySelector('[data-testid="berburu-canvas"]'),
        document.querySelector('[data-testid="berburu"]'),
        document.querySelector("canvas")
      ];
      for (const el of candidates) {
        if (!el) continue;
        const key = Object.keys(el).find(
          (k) => k.startsWith("__reactFiber$") || k.startsWith("__reactInternalInstance$")
        );
        if (!key) continue;

        let fiber = el[key];
        let depth = 0;
        while (fiber && depth++ < 45) {
          let hook = fiber.memoizedState;
          while (hook) {
            const s = hook.memoizedState;
            if (s && s.current && isValidBerburuInstance(s.current)) {
              window.__KS_BERBURU_INSTANCE = s.current;
              console.log("[BerburuInject] Hooked Berburu 3D instance via React Fiber!");
              return s.current;
            }
            hook = hook.next;
          }
          fiber = fiber.return;
        }
      }
    } catch (e) {
      console.warn("[BerburuInject] Fiber scan error:", e);
    }
    return null;
  }

  // Fallback prototype hook (if property is assigned directly)
  try {
    const desc = Object.getOwnPropertyDescriptor(Object.prototype, "satwa");
    if (!desc) {
      Object.defineProperty(Object.prototype, "satwa", {
        configurable: true,
        enumerable: false,
        get() {
          return this.__ks_satwa_val;
        },
        set(val) {
          this.__ks_satwa_val = val;
          if (isValidBerburuInstance(this)) {
            window.__KS_BERBURU_INSTANCE = this;
          }
        }
      });
    }
  } catch (e) {
    console.warn("[BerburuInject] Failed to hook satwa:", e);
  }

  function getWorldPos(obj) {
    if (!obj || typeof obj.getWorldPosition !== "function") return null;
    try {
      const Ctor = obj.position && obj.position.constructor;
      const v = Ctor ? new Ctor() : { x: 0, y: 0, z: 0, set() {} };
      obj.getWorldPosition(v);
      return { x: v.x, y: v.y, z: v.z };
    } catch {
      return null;
    }
  }

  function makeVecLike(camPos, x, y, z) {
    if (camPos && typeof camPos.clone === "function") {
      const v = camPos.clone();
      v.set(x, y, z);
      return v;
    }
    return { x, y, z };
  }

  function buildSnapshot() {
    const inst = scanBerburuFiber();
    if (!inst || !inst.me || !Array.isArray(inst.satwa)) {
      return { ready: false };
    }
    let state = null;
    try {
      state = inst.keadaan();
    } catch {
      return { ready: false };
    }
    const camPos = inst.cam && inst.cam.position
      ? { x: inst.cam.position.x, y: inst.cam.position.y, z: inst.cam.position.z }
      : { x: inst.me.x, y: inst.me.y + inst.me.mata, z: inst.me.z };
    const wind = (inst.L && inst.L.angin) ? {
      x: inst.L.angin.x || 0,
      z: inst.L.angin.z || 0,
      arah: inst.L.angin.arah || 0,
      laju: inst.L.angin.laju || 0
    } : { x: 0, z: 0, arah: 0, laju: 0 };

    const animals = [];
    for (const s of inst.satwa) {
      if (!s || s.keadaan === "diambil" || s.keadaan === "sembunyi") continue;
      const dx = s.x - inst.me.x;
      const dz = s.z - inst.me.z;
      const dist = Math.hypot(dx, dz);
      const bearing = Math.atan2(dx, dz);
      const relAngle = Math.atan2(Math.sin(bearing - inst.yaw), Math.cos(bearing - inst.yaw));

      let headPos = null;
      let chestPos = null;
      if (s.obj && typeof s.obj.updateMatrixWorld === "function") {
        s.obj.updateMatrixWorld(true);
      }
      if (s.m) {
        headPos = getWorldPos(s.m.kepala);
        chestPos = getWorldPos(s.m.dada);
      }
      if (!headPos) {
        headPos = { x: s.x, y: (s.y || 0) + (s.a?.tinggi || 0.4), z: s.z };
      }
      if (!chestPos) {
        chestPos = { x: s.x, y: (s.y || 0) + (s.a?.tinggi || 0.4) * 0.7, z: s.z };
      }

      let los = true;
      if (s.keadaan !== "mati" && typeof inst.potongBatang === "function" && inst.cam?.position) {
        try {
          const p0 = inst.cam.position;
          const p1 = makeVecLike(p0, headPos.x, headPos.y, headPos.z);
          los = inst.potongBatang(p0, p1) == null;
          if (los && dist > 15) {
            const perpX = Math.cos(bearing) * 0.12;
            const perpZ = -Math.sin(bearing) * 0.12;
            const p1L = makeVecLike(p0, headPos.x + perpX, headPos.y, headPos.z + perpZ);
            const p1R = makeVecLike(p0, headPos.x - perpX, headPos.y, headPos.z - perpZ);
            if (inst.potongBatang(p0, p1L) != null || inst.potongBatang(p0, p1R) != null) {
              los = false;
            }
          }
        } catch {
          los = true;
        }
      }

      const aimHead = solveBallisticAim(camPos, headPos, wind);

      animals.push({
        i: s.i,
        jenis: s.jenis,
        nama: s.a?.nama || s.jenis,
        x: Math.round(s.x * 100) / 100,
        y: Math.round((s.y || 0) * 100) / 100,
        z: Math.round(s.z * 100) / 100,
        dist: Math.round(dist * 10) / 10,
        bearing,
        relAngle,
        keadaan: s.keadaan,
        waspada: s.waspada || 0,
        hidup: s.keadaan !== "mati",
        seruduk: !!s.a?.seruduk,
        energiKepala: s.a?.energi_kepala || 0.3,
        energiSampai: Math.round(aimHead.energy * 100) / 100,
        los,
        headPos,
        chestPos
      });
    }

    return {
      ready: true,
      hutan: inst.H ? { id: inst.H.id, nama: inst.H.nama, luas_m: inst.H.luas_m, masuk: inst.H.masuk } : null,
      me: {
        x: Math.round(inst.me.x * 100) / 100,
        y: Math.round(inst.me.y * 100) / 100,
        z: Math.round(inst.me.z * 100) / 100,
        v: inst.me.v || 0,
        yaw: inst.yaw,
        pitch: inst.pitch
      },
      camPos,
      wind,
      state,
      animals
    };
  }

  let autoWalkTarget = null;
  let walkInterval = null;

  function stopWalk() {
    autoWalkTarget = null;
    if (walkInterval) {
      clearInterval(walkInterval);
      walkInterval = null;
    }
    const inst = window.__KS_BERBURU_INSTANCE;
    if (inst && inst.input) {
      inst.input.sx = 0;
      inst.input.sy = 0;
    }
    if (inst && typeof inst.setLari === "function") {
      inst.setLari(false);
    }
  }

  function pickClearWalkYaw(cur, targetYaw) {
    if (typeof cur.bebas !== "function") return targetYaw;
    const offsets = [0, 0.4, -0.4, 0.85, -0.85, 1.3, -1.3, 1.8, -1.8];
    for (const off of offsets) {
      const ang = targetYaw + off;
      const nx = cur.me.x + Math.sin(ang) * 1.1;
      const nz = cur.me.z + Math.cos(ang) * 1.1;
      if (cur.bebas(nx, nz)) return ang;
    }
    return targetYaw;
  }

  function startWalk(targetX, targetZ, stopRadius = 2.0, crouch = false, run = false) {
    const inst = window.__KS_BERBURU_INSTANCE;
    if (!inst) return;
    autoWalkTarget = { x: targetX, z: targetZ, stopRadius, crouch, run };
    if (typeof inst.setBidik === "function" && inst.mauBidik) {
      inst.setBidik(false);
    }
    if (typeof inst.setJongkok === "function" && inst.jongkok !== !!crouch) {
      inst.setJongkok(!!crouch);
    }
    if (typeof inst.setLari === "function") {
      inst.setLari(!!run && !crouch);
    }
    if (walkInterval) return;

    walkInterval = setInterval(() => {
      const cur = window.__KS_BERBURU_INSTANCE;
      if (!cur || !autoWalkTarget || cur.kunci || cur.jatuh > 0) {
        stopWalk();
        return;
      }
      const dx = autoWalkTarget.x - cur.me.x;
      const dz = autoWalkTarget.z - cur.me.z;
      const dist = Math.hypot(dx, dz);
      if (dist <= autoWalkTarget.stopRadius) {
        stopWalk();
        window.dispatchEvent(new CustomEvent("ks_berburu_walk_done", { detail: { x: cur.me.x, z: cur.me.z } }));
        return;
      }
      const desiredYaw = Math.atan2(dx, dz);
      cur.yaw = pickClearWalkYaw(cur, desiredYaw);
      cur.pitch = 0;
      if (cur.input) {
        cur.input.sx = 0;
        cur.input.sy = 1;
      }
    }, 50);
  }

  function aimAt(satwaId, zona = "kepala", openScope = true, holdBreath = true) {
    const inst = window.__KS_BERBURU_INSTANCE;
    if (!inst || !Array.isArray(inst.satwa)) return false;
    const s = inst.satwa.find(item => item.i === satwaId);
    if (!s) return false;

    if (s.obj && typeof s.obj.updateMatrixWorld === "function") {
      s.obj.updateMatrixWorld(true);
    }
    const targetObj = zona === "dada" ? s.m?.dada : s.m?.kepala;
    const targetPos = getWorldPos(targetObj) || {
      x: s.x,
      y: (s.y || 0) + (s.a?.tinggi || 0.4) * (zona === "dada" ? 0.7 : 1.0),
      z: s.z
    };

    // Lead moving target slightly based on bullet travel time
    const dist = Math.hypot(targetPos.x - inst.me.x, targetPos.z - inst.me.z);
    const flightTime = dist / SENAPAN.laju;
    const speed = s.laju || 0;
    if (speed > 0.1 && typeof s.hadap === "number") {
      targetPos.x += Math.sin(s.hadap) * speed * flightTime;
      targetPos.z += Math.cos(s.hadap) * speed * flightTime;
    }

    const camPos = inst.cam?.position
      ? { x: inst.cam.position.x, y: inst.cam.position.y, z: inst.cam.position.z }
      : { x: inst.me.x, y: inst.me.y + inst.me.mata, z: inst.me.z };
    const wind = (inst.L && inst.L.angin) ? inst.L.angin : { x: 0, z: 0 };

    const sol = solveBallisticAim(camPos, targetPos, wind);

    // Compensate for scope sway & recoil between inst.yaw/pitch and actual camera direction
    let swayYaw = 0;
    let swayPitch = 0;
    if (inst.cam && typeof inst.cam.getWorldDirection === "function") {
      try {
        const Ctor = inst.cam.position.constructor;
        const dir = new Ctor();
        inst.cam.getWorldDirection(dir);
        const camYaw = Math.atan2(dir.x, dir.z);
        const camPitch = Math.asin(Math.max(-1, Math.min(1, dir.y)));
        swayYaw = Math.atan2(Math.sin(camYaw - inst.yaw), Math.cos(camYaw - inst.yaw));
        swayPitch = camPitch - inst.pitch;
      } catch {}
    }

    inst.yaw = sol.yaw - swayYaw;
    inst.pitch = sol.pitch - swayPitch;
    if (openScope && typeof inst.setBidik === "function" && !inst.mauBidik) {
      inst.setBidik(true);
    }
    if (holdBreath && typeof inst.setTahan === "function" && inst.bidik > 0.93) {
      inst.setTahan(true);
    }
    return true;
  }

  let aimLockState = null;
  function startAimLock(satwaId, zona = "kepala", openScope = true, holdBreath = true) {
    aimLockState = { satwaId, zona, openScope, holdBreath };
  }
  function stopAimLock() {
    aimLockState = null;
  }

  // --- Wallhack: 2D ESP Overlay + 3D Chams (both default OFF) ---
  const wallhackState = {
    esp2d: false,
    chams3d: false,
    filter: "babi"
  };

  function matchesWallhackFilter(s, filterMode) {
    if (!s || s.keadaan === "diambil" || s.keadaan === "sembunyi") return false;
    if (s.keadaan === "mati") return true; // Always show corpses to loot
    if (filterMode === "all") return true;
    if (filterMode === "high-roi") return s.jenis === "babi-hutan" || s.jenis === "ayam-hutan";
    if (filterMode === "babi") return s.jenis === "babi-hutan";
    if (filterMode === "ayam") return s.jenis === "ayam-hutan";
    if (filterMode === "hama") return s.jenis === "tupai-kelapa" || s.jenis === "tikus-sawah";
    return true;
  }

  function projectWorldToScreen(inst, worldPos, width, height) {
    if (!inst?.cam || !worldPos || !inst.cam.position) return null;
    try {
      const Ctor = inst.cam.position.constructor;
      const v = new Ctor(worldPos.x, worldPos.y, worldPos.z);
      if (typeof v.project !== "function") return null;

      // Check if point is in front of camera
      if (typeof inst.cam.getWorldDirection === "function") {
        const dir = new Ctor();
        inst.cam.getWorldDirection(dir);
        const dx = worldPos.x - inst.cam.position.x;
        const dy = worldPos.y - inst.cam.position.y;
        const dz = worldPos.z - inst.cam.position.z;
        if (dx * dir.x + dy * dir.y + dz * dir.z <= 0.1) return null;
      }

      v.project(inst.cam);
      if (!Number.isFinite(v.x) || !Number.isFinite(v.y) || !Number.isFinite(v.z) || v.z > 1) {
        return null;
      }
      return {
        x: (v.x * 0.5 + 0.5) * width,
        y: (-v.y * 0.5 + 0.5) * height
      };
    } catch {
      return null;
    }
  }

  function ensureEspCanvas(targetCanvas) {
    let overlay = document.getElementById("ks-berburu-esp-overlay");
    if (!overlay) {
      overlay = document.createElement("canvas");
      overlay.id = "ks-berburu-esp-overlay";
      overlay.style.cssText = [
        "position:fixed",
        "pointer-events:none",
        "z-index:2147483639",
        "display:none"
      ].join(";");
      document.body.appendChild(overlay);
    }
    if (!targetCanvas) {
      overlay.style.display = "none";
      return null;
    }
    const rect = targetCanvas.getBoundingClientRect();
    if (rect.width < 10 || rect.height < 10) {
      overlay.style.display = "none";
      return null;
    }
    overlay.style.display = "block";
    overlay.style.left = `${rect.left}px`;
    overlay.style.top = `${rect.top}px`;
    overlay.style.width = `${rect.width}px`;
    overlay.style.height = `${rect.height}px`;
    const w = Math.round(rect.width);
    const h = Math.round(rect.height);
    if (overlay.width !== w || overlay.height !== h) {
      overlay.width = w;
      overlay.height = h;
    }
    return { overlay, w, h };
  }

  function hideEspCanvas() {
    const overlay = document.getElementById("ks-berburu-esp-overlay");
    if (overlay) {
      const ctx = overlay.getContext("2d");
      if (ctx) ctx.clearRect(0, 0, overlay.width, overlay.height);
      overlay.style.display = "none";
    }
  }

  function renderEsp2D(inst) {
    if (!wallhackState.esp2d || !inst || !inst.cam || !Array.isArray(inst.satwa)) {
      hideEspCanvas();
      return;
    }
    const targetCanvas = inst.renderer?.domElement || document.querySelector("canvas");
    const info = ensureEspCanvas(targetCanvas);
    if (!info) return;
    const { overlay, w, h } = info;
    const ctx = overlay.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, w, h);

    if (typeof inst.cam.updateMatrixWorld === "function") {
      inst.cam.updateMatrixWorld();
    }

    const snapAnimals = window.__KS_BERBURU_STATE?.animals || [];
    const losById = new Map();
    for (const a of snapAnimals) {
      losById.set(a.i, a.los);
    }

    for (const s of inst.satwa) {
      if (!matchesWallhackFilter(s, wallhackState.filter)) continue;
      if (s.obj && typeof s.obj.updateMatrixWorld === "function") {
        s.obj.updateMatrixWorld(true);
      }

      const basePos = { x: s.x, y: s.y || 0, z: s.z };
      const headPos = (s.m && getWorldPos(s.m.kepala)) || {
        x: s.x,
        y: (s.y || 0) + (s.a?.tinggi || 0.4),
        z: s.z
      };
      const topPos = { x: headPos.x, y: headPos.y + 0.25, z: headPos.z };

      const pBase = projectWorldToScreen(inst, basePos, w, h);
      const pTop = projectWorldToScreen(inst, topPos, w, h);
      const pHead = projectWorldToScreen(inst, headPos, w, h);
      if (!pBase && !pHead) continue;

      const anchor = pHead || pBase;
      const dx = s.x - inst.me.x;
      const dz = s.z - inst.me.z;
      const dist = Math.round(Math.hypot(dx, dz));
      const isDead = s.keadaan === "mati";
      const los = losById.has(s.i) ? losById.get(s.i) : true;

      let color = "#c084fc";
      if (isDead) color = "#4ade80";
      else if (s.keadaan === "seruduk") color = "#ef4444";
      else if (!los) color = "#f59e0b";
      else if (s.jenis === "babi-hutan") color = "#22d3ee";
      else if (s.jenis === "ayam-hutan") color = "#facc15";

      const boxH = pBase && pTop ? Math.max(18, Math.min(180, Math.abs(pBase.y - pTop.y) * 1.25)) : Math.max(16, Math.min(120, 900 / Math.max(4, dist)));
      const boxW = boxH * 1.15;
      const bx = anchor.x - boxW / 2;
      const by = (pTop ? pTop.y : anchor.y - boxH * 0.5);

      ctx.strokeStyle = color;
      ctx.lineWidth = isDead || s.keadaan === "seruduk" ? 2 : 1.5;
      ctx.strokeRect(bx, by, boxW, boxH);

      // Head dot
      if (pHead && !isDead) {
        ctx.fillStyle = los ? "#4ade80" : "#ef4444";
        ctx.beginPath();
        ctx.arc(pHead.x, pHead.y, 3.5, 0, Math.PI * 2);
        ctx.fill();
      }

      // Label
      const statusTxt = isDead ? "MATI" : s.keadaan === "seruduk" ? "SERUDUK!" : los ? "LOS" : "TERHALANG";
      const label = `${s.a?.nama || s.jenis} ${dist}m [${statusTxt}]`;
      ctx.font = "bold 11px -apple-system, BlinkMacSystemFont, sans-serif";
      const tw = ctx.measureText(label).width;
      const lx = anchor.x - tw / 2 - 4;
      const ly = by - 17;
      ctx.fillStyle = "rgba(6, 17, 26, 0.78)";
      ctx.fillRect(lx, ly, tw + 8, 15);
      ctx.fillStyle = color;
      ctx.fillText(label, lx + 4, ly + 11);
    }
  }

  const origObjProps = new WeakMap();
  const origMatProps = new WeakMap();
  const chamsModifiedNodes = new Set();

  function restoreChamsNode(node) {
    const objSaved = origObjProps.get(node);
    if (objSaved) {
      node.renderOrder = objSaved.renderOrder;
      node.frustumCulled = objSaved.frustumCulled;
      origObjProps.delete(node);
    }
    const mats = Array.isArray(node.material) ? node.material : [node.material];
    for (const mat of mats) {
      if (!mat) continue;
      const matSaved = origMatProps.get(mat);
      if (matSaved) {
        mat.depthTest = matSaved.depthTest;
        mat.fog = matSaved.fog;
        if (mat.emissive && matSaved.emissive && typeof mat.emissive.copy === "function") {
          mat.emissive.copy(matSaved.emissive);
        }
        if (typeof matSaved.emissiveIntensity === "number") {
          mat.emissiveIntensity = matSaved.emissiveIntensity;
        }
        mat.needsUpdate = true;
        origMatProps.delete(mat);
      }
    }
    chamsModifiedNodes.delete(node);
  }

  function applyChamsNode(node) {
    if (!node || !node.isMesh || !node.material) return;
    if (!origObjProps.has(node)) {
      origObjProps.set(node, {
        renderOrder: node.renderOrder,
        frustumCulled: node.frustumCulled
      });
    }
    node.renderOrder = 999;
    node.frustumCulled = false;

    const mats = Array.isArray(node.material) ? node.material : [node.material];
    for (const mat of mats) {
      if (!mat) continue;
      if (!origMatProps.has(mat)) {
        origMatProps.set(mat, {
          depthTest: mat.depthTest,
          fog: mat.fog,
          emissive: mat.emissive && typeof mat.emissive.clone === "function" ? mat.emissive.clone() : null,
          emissiveIntensity: mat.emissiveIntensity
        });
        mat.needsUpdate = true;
      }
      mat.depthTest = false;
      mat.fog = false;
    }
    chamsModifiedNodes.add(node);
  }

  function syncChams3D(inst) {
    if (!wallhackState.chams3d || !inst || !Array.isArray(inst.satwa)) {
      if (chamsModifiedNodes.size > 0) {
        for (const node of Array.from(chamsModifiedNodes)) {
          restoreChamsNode(node);
        }
      }
      return;
    }

    const activeNodes = new Set();
    for (const s of inst.satwa) {
      if (!s.obj || typeof s.obj.traverse !== "function") continue;
      if (!matchesWallhackFilter(s, wallhackState.filter)) continue;
      s.obj.traverse((node) => {
        if (node.isMesh && node.material) {
          activeNodes.add(node);
          applyChamsNode(node);
        }
      });
    }

    for (const node of Array.from(chamsModifiedNodes)) {
      if (!activeNodes.has(node)) {
        restoreChamsNode(node);
      }
    }
  }

  function renderFrameLoop() {
    if (aimLockState) {
      aimAt(aimLockState.satwaId, aimLockState.zona, aimLockState.openScope, aimLockState.holdBreath);
    }
    const inst = window.__KS_BERBURU_INSTANCE;
    renderEsp2D(inst);
    syncChams3D(inst);
    requestAnimationFrame(renderFrameLoop);
  }
  requestAnimationFrame(renderFrameLoop);

  window.addEventListener("ks_berburu_cmd", (e) => {
    const cmd = e.detail || {};
    if (cmd.action === "setWallhack") {
      if (typeof cmd.esp2d === "boolean") wallhackState.esp2d = cmd.esp2d;
      if (typeof cmd.chams3d === "boolean") wallhackState.chams3d = cmd.chams3d;
      if (typeof cmd.filter === "string") wallhackState.filter = cmd.filter;
      const curInst = window.__KS_BERBURU_INSTANCE;
      renderEsp2D(curInst);
      syncChams3D(curInst);
      return;
    }
    const inst = window.__KS_BERBURU_INSTANCE;
    if (!inst) return;
    switch (cmd.action) {
      case "aim":
        startAimLock(cmd.satwaId, cmd.zona || "kepala", cmd.scope !== false, cmd.breath !== false);
        aimAt(cmd.satwaId, cmd.zona || "kepala", cmd.scope !== false, cmd.breath !== false);
        break;
      case "stopAim":
        stopAimLock();
        break;
      case "walk":
        stopAimLock();
        startWalk(cmd.x, cmd.z, cmd.stopRadius ?? 2.0, !!cmd.crouch, !!cmd.run);
        break;
      case "stopWalk":
        stopWalk();
        break;
      case "crouch":
        if (typeof inst.setJongkok === "function") inst.setJongkok(!!cmd.value);
        break;
      case "scope":
        if (typeof inst.setBidik === "function") inst.setBidik(!!cmd.value);
        break;
      case "breath":
        if (typeof inst.setTahan === "function") inst.setTahan(!!cmd.value);
        break;
      case "dodge":
        // Sidestep left/right to avoid charging boar
        if (inst.input) {
          inst.input.sx = cmd.dir || 1;
          inst.input.sy = 0;
          setTimeout(() => {
            if (inst.input) inst.input.sx = 0;
          }, cmd.durationMs || 900);
        }
        break;
    }
  });

  // Broadcast live snapshot at 10Hz when on /berburu
  setInterval(() => {
    const snap = buildSnapshot();
    window.__KS_BERBURU_STATE = snap;
    window.dispatchEvent(new CustomEvent("ks_berburu_state", { detail: snap }));
  }, 100);

  window.__KS_BERBURU_SOLVER = {
    stepBullet,
    getZeroOffset,
    solveBallisticAim
  };
})();
