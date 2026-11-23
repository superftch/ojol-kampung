// KampungSebelah - Diving Radar & Pearl Compass Content Script (v1.8.0)
// Menggunakan Objek Kerang 3D Asli dari Game & Auto-Pilot Berenang Langsung

(function () {
  console.log("[DivingCompass] Content script v1.8.0 loaded");

  function injectMainScript() {
    try {
      const s = document.createElement("script");
      s.src = chrome.runtime.getURL("inject.js");
      s.onload = function () {
        this.remove();
      };
      (document.head || document.documentElement).appendChild(s);
    } catch (e) {
      console.warn("[DivingCompass] Injection error:", e);
    }
  }
  injectMainScript();

  const LAUT = {
    x0: -320, x1: 320, z0: -640, z1: -6, masuk: { x: 0, z: -26 }
  };
  const KERANG_CONFIG = {
    jumlah: 48, jarak_min: 18, dalam_min: 4, jangkau_m: 3.2, buka_detik: 3
  };
  const MUTIARA_RULES = {
    dalam_min_biasa: 18,
    dalam_min_langka: 40
  };

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

  function getTodayWIB() {
    let d = new Date(Date.now() + 7 * 3600 * 1000);
    return d.toISOString().slice(0, 10);
  }

  function generateKerangFallback(hari) {
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
        putar: putar,
        besar: besar,
        kategori: kategori,
        labelKategori: labelKategori,
        badgeColor: badgeColor
      });
    }
    return list;
  }

  // State
  let today = getTodayWIB();
  let allKerang = generateKerangFallback(today);
  let openedSet = new Set();
  let selectedKerang = null;
  let isAutopilotRunning = false;
  let currentFilterMode = "langka"; // "langka" (300 koin), "potensial" (100 & 300 koin), "all" (semua)

  let livePlayer = {
    x: LAUT.masuk.x,
    z: LAUT.masuk.z,
    kedalaman: 0.9,
    arah: 0,
    yaw: Math.PI,
    pitch: 0,
    valid: false,
    source: "init"
  };

  try {
    let saved = localStorage.getItem(`ks_opened_kerang_${today}`);
    if (saved) openedSet = new Set(JSON.parse(saved));
  } catch (e) {}

  function saveOpened() {
    try {
      localStorage.setItem(`ks_opened_kerang_${today}`, JSON.stringify(Array.from(openedSet)));
    } catch (e) {}
  }

  // Sinkronisasi koordinat kerang 3D fisik asli dari scene game!
  window.addEventListener("ks_real_kerang_loaded", (e) => {
    if (Array.isArray(e.detail) && e.detail.length > 0) {
      console.log("[DivingCompass] Replaced shell list with real 3D game meshes (", e.detail.length, ")");
      allKerang = e.detail;

      // Update status sudah dibuka langsung dari objek game
      allKerang.forEach(k => {
        if (k.dibuka) openedSet.add(k.i);
      });
      saveOpened();

      // Perbarui target aktif jika sedang memilih
      if (selectedKerang) {
        const updated = allKerang.find(k => k.i === selectedKerang.i);
        if (updated) selectedKerang = updated;
      }

      renderList();
    }
  });

  window.addEventListener("ks_diving_tick", (e) => {
    if (e.detail && typeof e.detail.x === "number") {
      livePlayer.x = e.detail.x;
      livePlayer.z = e.detail.z;
      livePlayer.kedalaman = e.detail.kedalaman;
      livePlayer.arah = e.detail.arah;
      livePlayer.yaw = typeof e.detail.yaw === "number" ? e.detail.yaw : e.detail.arah;
      livePlayer.valid = true;
      livePlayer.source = e.detail.source || "injected";
    }
  });

  window.addEventListener("ks_shell_opened_auto", (e) => {
    const k = e.detail.kerang;
    const shouldChain = !!e.detail.autoChain;

    if (k && typeof k.i === "number") {
      openedSet.add(k.i);
      saveOpened();
      renderList();
    }

    const titleEl = document.getElementById("ks-compass-title");
    if (titleEl) {
      titleEl.textContent = `🐚 Membuka Kerang #${k.i}...`;
      titleEl.style.color = "#fbbf24";
    }

    if (shouldChain) {
      setTimeout(() => {
        if (!isAutopilotRunning) {
          const nextTarget = getNextNearestShell();
          if (nextTarget) {
            selectKerangTarget(nextTarget);
            const autoOpen = document.getElementById("ks-auto-open-check")?.checked ?? true;
            const autoChain = document.getElementById("ks-auto-chain-check")?.checked ?? true;
            sendAutopilotCommand("start", nextTarget, autoOpen, autoChain);
          } else {
            if (titleEl) {
              titleEl.textContent = "🎉 Semua Kerang Potensial Selesai!";
              titleEl.style.color = "#22c55e";
            }
          }
        }
      }, 4200);
    }
  });

  window.addEventListener("ks_autopilot_status", (e) => {
    const st = e.detail;
    isAutopilotRunning = !!st.active;
    updateAutopilotUI(st);
  });

  function sendAutopilotCommand(action, target, autoOpen = true, autoChain = true) {
    window.dispatchEvent(new CustomEvent("ks_autopilot_command", {
      detail: { action, target, autoOpen, autoChain }
    }));
  }

  function getNextNearestShell() {
    const px = livePlayer.x, pz = livePlayer.z, pd = livePlayer.kedalaman;
    let candidates = [];

    if (currentFilterMode === "langka") {
      candidates = allKerang.filter(k => !openedSet.has(k.i) && k.kategori === "langka");
    } else if (currentFilterMode === "potensial") {
      candidates = allKerang.filter(k => !openedSet.has(k.i) && (k.kategori === "biasa" || k.kategori === "langka"));
    } else {
      candidates = allKerang.filter(k => !openedSet.has(k.i));
    }

    if (candidates.length === 0) return null;

    candidates.sort((a, b) => Math.hypot(a.x - px, a.z - pz, a.d - pd) - Math.hypot(b.x - px, b.z - pz, b.d - pd));
    return candidates[0];
  }

  // Helper: Membuat HUD dapat digeser secara bebas (Free Move / Draggable) dan posisinya disimpan
  function makeDraggable(element, options = {}) {
    const {
      handle = element,
      storageKey = null
    } = options;

    if (!element || !handle) return;

    // 1. Pulihkan posisi tersimpan dari localStorage
    if (storageKey) {
      try {
        const raw = localStorage.getItem(storageKey);
        if (raw) {
          const pos = JSON.parse(raw);
          if (typeof pos.left === "number" && typeof pos.top === "number") {
            const winW = window.innerWidth || document.documentElement.clientWidth || 1024;
            const winH = window.innerHeight || document.documentElement.clientHeight || 768;
            const w = element.offsetWidth || 280;
            const h = element.offsetHeight || 50;
            const clampX = Math.max(0, Math.min(pos.left, Math.max(0, winW - w)));
            const clampY = Math.max(0, Math.min(pos.top, Math.max(0, winH - h)));
            element.style.left = `${clampX}px`;
            element.style.top = `${clampY}px`;
            element.style.right = "auto";
            element.style.bottom = "auto";
            element.style.transform = "none";
          }
        }
      } catch (_) {}
    }

    // 2. Jaga posisi agar tidak keluar layar saat ukuran jendela browser berubah
    window.addEventListener("resize", () => {
      if (element.style.left && element.style.left !== "") {
        const rect = element.getBoundingClientRect();
        const winW = window.innerWidth || document.documentElement.clientWidth || 1024;
        const winH = window.innerHeight || document.documentElement.clientHeight || 768;
        const maxLeft = Math.max(0, winW - rect.width);
        const maxTop = Math.max(0, winH - rect.height);
        const currentLeft = parseInt(element.style.left, 10);
        const currentTop = parseInt(element.style.top, 10);
        if (!isNaN(currentLeft) && !isNaN(currentTop)) {
          const clampedX = Math.max(0, Math.min(currentLeft, maxLeft));
          const clampedY = Math.max(0, Math.min(currentTop, maxTop));
          if (clampedX !== currentLeft) element.style.left = `${clampedX}px`;
          if (clampedY !== currentTop) element.style.top = `${clampedY}px`;
        }
      }
    });

    let isDragging = false;
    let startX = 0;
    let startY = 0;
    let initialElemX = 0;
    let initialElemY = 0;
    let hasMoved = false;

    handle.style.cursor = "grab";
    handle.style.touchAction = "none";

    // Double-click pada handle untuk reset posisi ke default
    handle.addEventListener("dblclick", (e) => {
      if (e.target.closest("button, input, select, textarea, a, [data-no-drag]")) return;
      if (storageKey) {
        try {
          localStorage.removeItem(storageKey);
        } catch (_) {}
      }
      element.style.left = "";
      element.style.top = "";
      element.style.right = "";
      element.style.bottom = "";
      element.style.transform = "";
    });

    handle.addEventListener("pointerdown", (e) => {
      if (e.target.closest("button, input, select, textarea, a, [data-no-drag]")) {
        return;
      }
      if (e.button !== 0) return;

      isDragging = true;
      hasMoved = false;
      startX = e.clientX;
      startY = e.clientY;

      const rect = element.getBoundingClientRect();
      initialElemX = rect.left;
      initialElemY = rect.top;

      try {
        handle.setPointerCapture(e.pointerId);
      } catch (_) {}

      element.dataset.prevTransition = element.style.transition || "";
      element.style.transition = "none";
      handle.style.cursor = "grabbing";
      document.body.style.userSelect = "none";
    });

    handle.addEventListener("pointermove", (e) => {
      if (!isDragging) return;

      const deltaX = e.clientX - startX;
      const deltaY = e.clientY - startY;

      if (!hasMoved && Math.hypot(deltaX, deltaY) > 3) {
        hasMoved = true;
      }

      if (!hasMoved) return;

      const rect = element.getBoundingClientRect();
      const newX = initialElemX + deltaX;
      const newY = initialElemY + deltaY;

      const winW = window.innerWidth || document.documentElement.clientWidth || 1024;
      const winH = window.innerHeight || document.documentElement.clientHeight || 768;
      const maxLeft = Math.max(0, winW - rect.width);
      const maxTop = Math.max(0, winH - rect.height);

      const clampX = Math.max(0, Math.min(newX, maxLeft));
      const clampY = Math.max(0, Math.min(newY, maxTop));

      element.style.left = `${clampX}px`;
      element.style.top = `${clampY}px`;
      element.style.right = "auto";
      element.style.bottom = "auto";
      element.style.transform = "none";
    });

    function endDrag(e) {
      if (!isDragging) return;
      isDragging = false;

      try {
        handle.releasePointerCapture(e.pointerId);
      } catch (_) {}

      element.style.transition = element.dataset.prevTransition || "";
      delete element.dataset.prevTransition;
      handle.style.cursor = "grab";
      document.body.style.userSelect = "";

      if (hasMoved) {
        const rect = element.getBoundingClientRect();
        if (storageKey) {
          try {
            localStorage.setItem(storageKey, JSON.stringify({
              left: Math.round(rect.left),
              top: Math.round(rect.top)
            }));
          } catch (_) {}
        }
        const suppressClick = (ev) => {
          ev.stopPropagation();
          ev.preventDefault();
          window.removeEventListener("click", suppressClick, true);
        };
        window.addEventListener("click", suppressClick, true);
        setTimeout(() => window.removeEventListener("click", suppressClick, true), 80);
      }
    }

    handle.addEventListener("pointerup", endDrag);
    handle.addEventListener("pointercancel", endDrag);
  }

  // 4. UI: Panah Penunjuk Arah (Nav Compass HUD)
  function createCompassHUD() {
    if (document.getElementById("ks-compass-hud")) return;

    const compass = document.createElement("div");
    compass.id = "ks-compass-hud";
    compass.style.cssText = `
      position: fixed;
      top: 18px;
      left: 50%;
      transform: translateX(-50%);
      background: rgba(10, 25, 41, 0.95);
      backdrop-filter: blur(14px);
      border: 2px solid #00e5ff;
      border-radius: 50px;
      padding: 6px 18px 6px 10px;
      display: flex;
      align-items: center;
      gap: 10px;
      z-index: 99998;
      box-shadow: 0 6px 28px rgba(0, 229, 255, 0.45);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      color: #fff;
      user-select: none;
      cursor: grab;
      transition: all 0.2s ease;
    `;

    compass.innerHTML = `
      <div id="ks-compass-drag-handle" style="
        cursor: grab;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 0 2px 0 4px;
        opacity: 0.65;
        font-size: 13px;
        color: #00e5ff;
        user-select: none;
      " title="Geser HUD (Klik & Geser Bebas)">⠿</div>

      <div id="ks-arrow-box" style="
        width: 44px;
        height: 44px;
        background: radial-gradient(circle, rgba(0,229,255,0.28) 0%, rgba(0,0,0,0) 70%);
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
      ">
        <svg id="ks-arrow-svg" viewBox="0 0 24 24" width="34" height="34" style="
          fill: #00e5ff;
          filter: drop-shadow(0 0 6px #00e5ff);
          transform: rotate(0deg);
          transition: transform 0.04s linear;
        ">
          <!-- Panah Navigasi Segitiga Presisi -->
          <path d="M12 2L4.5 20.29l.71.71L12 18l6.79 3 .71-.71z"/>
        </svg>
      </div>

      <div style="display: flex; flex-direction: column; cursor: pointer;" id="ks-compass-info">
        <div style="display: flex; align-items: center; gap: 6px;">
          <span id="ks-compass-title" style="font-weight: 800; font-size: 13px; color: #38bdf8;">
            Pilih Target Kerang di Radar
          </span>
          <span id="ks-compass-badge" style="
            font-size: 10px;
            padding: 1px 6px;
            border-radius: 10px;
            background: #0284c7;
            font-weight: bold;
            display: none;
          ">TARGET</span>
        </div>
        <div style="font-size: 11px; color: #cbd5e1; display: flex; gap: 12px; margin-top: 2px;">
          <span id="ks-compass-dist">📍 Jarak: -- m</span>
          <span id="ks-compass-depth">↕ Kedalaman: -- m</span>
        </div>
      </div>

      <button id="ks-hud-autopilot-btn" style="
        background: linear-gradient(135deg, #0284c7, #06b6d4);
        color: white;
        border: none;
        border-radius: 20px;
        padding: 6px 14px;
        font-size: 11px;
        font-weight: bold;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 5px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        transition: all 0.15s ease;
      ">
        <span>🚀 Auto Jalan</span>
      </button>
    `;

    document.body.appendChild(compass);

    makeDraggable(compass, {
      handle: compass,
      storageKey: "ks_hud_pos_compass"
    });

    document.getElementById("ks-hud-autopilot-btn").onclick = (e) => {
      e.stopPropagation();
      toggleAutopilot();
    };

    document.getElementById("ks-compass-info").onclick = () => {
      const radar = document.getElementById("ks-diving-radar-hud");
      if (radar) {
        radar.style.transform = "scale(1.05)";
        setTimeout(() => radar.style.transform = "scale(1)", 180);
      }
    };
  }

  function toggleAutopilot() {
    if (isAutopilotRunning) {
      sendAutopilotCommand("stop");
    } else {
      if (!selectedKerang) {
        const next = getNextNearestShell();
        if (next) selectKerangTarget(next);
      }
      if (selectedKerang) {
        const autoOpen = document.getElementById("ks-auto-open-check")?.checked ?? true;
        const autoChain = document.getElementById("ks-auto-chain-check")?.checked ?? true;
        sendAutopilotCommand("start", selectedKerang, autoOpen, autoChain);
      }
    }
  }

  function updateAutopilotUI(st) {
    const btnHud = document.getElementById("ks-hud-autopilot-btn");
    const btnRadar = document.getElementById("ks-radar-autopilot-btn");
    const compassBox = document.getElementById("ks-compass-hud");

    if (st.active) {
      if (btnHud) {
        btnHud.style.background = "#ef4444";
        btnHud.innerHTML = "<span>⏹ STOP</span>";
      }
      if (btnRadar) {
        btnRadar.style.background = "#ef4444";
        btnRadar.textContent = "⏹ Batalkan Auto Berenang";
      }
      if (compassBox) {
        compassBox.style.boxShadow = "0 0 32px rgba(6, 182, 212, 0.85)";
      }
    } else {
      if (btnHud) {
        btnHud.style.background = "linear-gradient(135deg, #0284c7, #06b6d4)";
        btnHud.innerHTML = "<span>🚀 Auto Jalan</span>";
      }
      if (btnRadar) {
        btnRadar.style.background = "linear-gradient(90deg, #16a34a, #22c55e)";
        btnRadar.textContent = "🚀 Mulai Auto Berenang ke Sini";
      }
      if (compassBox) {
        compassBox.style.boxShadow = "0 6px 28px rgba(0, 229, 255, 0.45)";
      }
    }
  }

  // 5. Update Loop Panah Penunjuk Arah (60 FPS) dengan Rumus Game Asli
  function startCompassLoop() {
    createCompassHUD();

    const arrowSvg = document.getElementById("ks-arrow-svg");
    const titleEl = document.getElementById("ks-compass-title");
    const badgeEl = document.getElementById("ks-compass-badge");
    const distEl = document.getElementById("ks-compass-dist");
    const depthEl = document.getElementById("ks-compass-depth");
    const compassBox = document.getElementById("ks-compass-hud");

    let lastListUpdate = 0;

    function tick() {
      requestAnimationFrame(tick);

      if (!selectedKerang) {
        const stats = getPotensiStats();
        if (titleEl) {
          titleEl.textContent = stats.availablePotensi > 0 ? "Pilih Target Kerang di Radar" : "🎉 Semua Kerang Potensi Selesai!";
          titleEl.style.color = stats.availablePotensi > 0 ? "#38bdf8" : "#22c55e";
        }
        if (badgeEl) badgeEl.style.display = "none";
        if (distEl) {
          distEl.innerHTML = `✨ Potensi Sisa: <b>${stats.availablePotensi}</b> kerang`;
        }
        if (depthEl) {
          depthEl.innerHTML = `💎 300k: <b>${stats.langkaAvailable}</b> | 🟡 100k: <b>${stats.biasaAvailable}</b>`;
        }
        if (arrowSvg) {
          arrowSvg.style.transform = "rotate(0deg)";
          arrowSvg.style.fill = "#94a3b8";
          arrowSvg.style.filter = "none";
        }
        if (compassBox) {
          compassBox.style.borderColor = "rgba(255,255,255,0.2)";
          compassBox.style.boxShadow = "none";
        }
        return;
      }

      const px = livePlayer.x;
      const pz = livePlayer.z;
      const pd = livePlayer.kedalaman;
      // Gunakan yaw kamera aktual
      const playerYaw = typeof livePlayer.yaw === "number" ? livePlayer.yaw : livePlayer.arah;

      const dx = selectedKerang.x - px;
      const dz = selectedKerang.z - pz;
      const dd = selectedKerang.d - pd;

      const distXZ = Math.hypot(dx, dz);
      const dist3D = Math.hypot(distXZ, dd);

      // FORMULA ASLI TEPAT GAME KAMPUNG SEBELAH:
      // af = (yaw, targetAngle) => diff normalisasi ke [-PI, PI]
      // rotasi = -diff (dalam radian)
      const targetAngle = Math.atan2(dx, dz);
      let diff = (targetAngle - playerYaw) % (2 * Math.PI);
      if (diff > Math.PI) diff -= 2 * Math.PI;
      if (diff < -Math.PI) diff += 2 * Math.PI;

      // Rotasi CSS persis dengan orientasi viewport: -diff
      const rotasiRad = -diff;
      const deg = (rotasiRad * 180) / Math.PI;

      if (arrowSvg) {
        arrowSvg.style.transform = `rotate(${deg}deg)`;

        if (dist3D <= 3.2) {
          arrowSvg.style.fill = "#22c55e";
          arrowSvg.style.filter = "drop-shadow(0 0 10px #22c55e)";
          if (compassBox) {
            compassBox.style.borderColor = "#22c55e";
          }
        } else {
          const color = isAutopilotRunning ? "#38bdf8" : (selectedKerang.badgeColor || "#00e5ff");
          arrowSvg.style.fill = color;
          arrowSvg.style.filter = `drop-shadow(0 0 8px ${color})`;
          if (compassBox) {
            compassBox.style.borderColor = isAutopilotRunning ? "#06b6d4" : color;
          }
        }
      }

      if (titleEl) {
        if (isAutopilotRunning) {
          titleEl.textContent = `🚀 Auto Berenang ke Kerang #${selectedKerang.i}...`;
          titleEl.style.color = "#38bdf8";
        } else if (dist3D <= 3.2) {
          titleEl.textContent = `🎯 SIAP BUKA! Kerang #${selectedKerang.i}`;
          titleEl.style.color = "#22c55e";
        } else {
          titleEl.textContent = `Kerang #${selectedKerang.i} (${selectedKerang.kategori === "langka" ? "💎 300 Koin" : "🟡 100 Koin"})`;
          titleEl.style.color = selectedKerang.badgeColor || "#38bdf8";
        }
      }

      if (badgeEl) {
        badgeEl.style.display = "inline-block";
        badgeEl.textContent = isAutopilotRunning ? "AUTO" : (selectedKerang.kategori === "langka" ? "LANGKA" : "POTENSIAL");
        badgeEl.style.background = isAutopilotRunning ? "#0284c7" : (selectedKerang.badgeColor || "#0284c7");
      }

      if (distEl) {
        distEl.innerHTML = `📍 Jarak: <b>${dist3D.toFixed(1)}m</b>`;
      }

      if (depthEl) {
        if (dd > 1.2) {
          depthEl.innerHTML = `⬇ Turun: <b>${dd.toFixed(1)}m</b> (Target ${selectedKerang.d}m)`;
          depthEl.style.color = "#38bdf8";
        } else if (dd < -1.2) {
          depthEl.innerHTML = `⬆ Naik: <b>${Math.abs(dd).toFixed(1)}m</b> (Target ${selectedKerang.d}m)`;
          depthEl.style.color = "#fbbf24";
        } else {
          depthEl.innerHTML = `🎯 Kedalaman Pas (<b>${selectedKerang.d}m</b>)`;
          depthEl.style.color = "#4ade80";
        }
      }

      const now = Date.now();
      if (now - lastListUpdate > 1000) {
        lastListUpdate = now;
        updateListDistances();
      }
    }

    requestAnimationFrame(tick);
  }

  // 6. Floating Radar HUD di Pojok Kanan
  function initRadarUI() {
    if (document.getElementById("ks-diving-radar-hud")) return;

    const hud = document.createElement("div");
    hud.id = "ks-diving-radar-hud";
    hud.style.cssText = `
      position: fixed;
      top: 16px;
      right: 16px;
      width: 330px;
      max-height: 85vh;
      background: rgba(10, 25, 41, 0.94);
      backdrop-filter: blur(10px);
      border: 1px solid rgba(0, 229, 255, 0.4);
      border-radius: 12px;
      color: #fff;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      font-size: 13px;
      z-index: 99999;
      box-shadow: 0 8px 32px rgba(0,0,0,0.6);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      transition: all 0.2s ease;
    `;

    hud.innerHTML = `
      <div id="ks-radar-header" style="background: rgba(0, 229, 255, 0.15); padding: 10px 14px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(0, 229, 255, 0.2); cursor: grab; user-select: none;">
        <div style="font-weight: bold; color: #00e5ff; display: flex; align-items: center; gap: 6px;">
          <span style="opacity: 0.7; font-size: 13px;" title="Geser Posisi HUD (Klik & Geser Bebas)">⠿</span>
          <span>🧭 Radar & Auto-Pilot Diving</span>
        </div>
        <button id="ks-radar-toggle" style="background: none; border: none; color: #90caf9; cursor: pointer; font-size: 14px; font-weight: bold; padding: 2px 6px;">_</button>
      </div>

      <div id="ks-radar-content" style="padding: 10px; overflow-y: auto; flex: 1;">
        <!-- Status Hiu Realtime -->
        <div style="background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.3); padding: 8px; border-radius: 6px; margin-bottom: 8px; font-size: 11px;">
          <div style="font-weight: bold; color: #f87171; margin-bottom: 2px;">⚠️ Panduan Keamanan Hiu:</div>
          <div style="color: #fca5a5; line-height: 1.3;">
            Hiu <b>TIDAK AKAN</b> menyerang di kedalaman &lt; 6 meter. Tekan tombol kontrol keyboard kapan saja untuk membatalkan Auto-Pilot!
          </div>
        </div>

        <div style="display: flex; gap: 4px; margin-bottom: 6px;">
          <button id="ks-filter-rare" style="flex: 1.2; padding: 6px 4px; background: #7c3aed; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 11px; font-weight: bold;">💎 300 Koin</button>
          <button id="ks-filter-potensial" style="flex: 1; padding: 6px 4px; background: rgba(255,255,255,0.1); color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 11px;">🟡 100 & 300</button>
          <button id="ks-filter-all" style="flex: 0.8; padding: 6px 4px; background: rgba(255,255,255,0.1); color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 11px;">Semua</button>
        </div>

        <!-- Status Kerang Potensi Tersedia -->
        <div style="background: rgba(15, 23, 42, 0.75); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 6px; padding: 8px; margin-bottom: 8px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <div style="font-weight: bold; font-size: 11px; color: #38bdf8; display: flex; align-items: center; gap: 4px;">
              <span>✨ Potensi Tersedia:</span>
              <span id="ks-potensi-available-num" style="color: #4ade80; font-size: 12px; font-weight: 800;">--</span>
            </div>
            <button id="ks-reset-opened-btn" style="background: none; border: none; color: #94a3b8; cursor: pointer; text-decoration: underline; font-size: 10px; padding: 0;">🔄 Reset Kerang</button>
          </div>
          
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 6px;">
            <div style="background: rgba(124, 58, 237, 0.2); border: 1px solid rgba(168, 85, 247, 0.35); border-radius: 4px; padding: 5px 6px;">
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="color: #c084fc; font-weight: bold; font-size: 10px;">💎 300 Koin</span>
                <span id="ks-stat-langka-count" style="font-size: 11px; font-weight: 800; color: #f3e8ff;">-- sisa</span>
              </div>
              <div style="font-size: 9px; color: #94a3b8; margin-top: 2px;">Palung (≥40m)</div>
            </div>
            <div style="background: rgba(234, 179, 8, 0.15); border: 1px solid rgba(234, 179, 8, 0.35); border-radius: 4px; padding: 5px 6px;">
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="color: #facc15; font-weight: bold; font-size: 10px;">🟡 100 Koin</span>
                <span id="ks-stat-biasa-count" style="font-size: 11px; font-weight: 800; color: #fef08a;">-- sisa</span>
              </div>
              <div style="font-size: 9px; color: #94a3b8; margin-top: 2px;">Dalam (≥18m)</div>
            </div>
          </div>
          
          <div style="display: flex; justify-content: space-between; font-size: 10px; color: #94a3b8; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 4px;">
            <span id="ks-stat-total-opened">Sudah dibuka: 0 kerang</span>
            <span style="color: #64748b;">Cetek (&lt;18m): 100% kosong</span>
          </div>
        </div>

        <button id="ks-pick-nearest" style="width: 100%; padding: 7px; background: linear-gradient(90deg, #0284c7, #06b6d4); color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: bold; margin-bottom: 8px;">
          ⚡ Arahkan Panah ke Kerang Terdekat
        </button>

        <div id="ks-target-tracker" style="display: none; background: rgba(0, 229, 255, 0.12); border: 1px dashed #00e5ff; border-radius: 6px; padding: 10px; margin-bottom: 8px;">
          <div style="font-weight: bold; color: #38bdf8; font-size: 12px; margin-bottom: 4px;" id="ks-target-title">Target: Kerang #X</div>
          <div style="font-size: 11px; margin-bottom: 8px;" id="ks-target-coords">X: 0, Z: 0, Dalam: 0m</div>

          <div style="display: flex; flex-direction: column; gap: 4px; margin-bottom: 8px;">
            <div style="display: flex; align-items: center; gap: 6px;">
              <input type="checkbox" id="ks-auto-open-check" checked style="cursor: pointer;">
              <label for="ks-auto-open-check" style="font-size: 11px; color: #cbd5e1; cursor: pointer;">✅ <b>Otomatis buka</b> saat tiba</label>
            </div>
            <div style="display: flex; align-items: center; gap: 6px;">
              <input type="checkbox" id="ks-auto-chain-check" checked style="cursor: pointer;">
              <label for="ks-auto-chain-check" style="font-size: 11px; color: #cbd5e1; cursor: pointer;">🔁 <b>Lanjut ke kerang berikutnya</b> (Loop)</label>
            </div>
          </div>

          <button id="ks-radar-autopilot-btn" style="width: 100%; padding: 7px; background: linear-gradient(90deg, #16a34a, #22c55e); border: none; color: white; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: bold; margin-bottom: 6px;">
            🚀 Mulai Auto Berenang ke Sini
          </button>

          <button id="ks-mark-opened" style="width: 100%; padding: 5px; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); color: #cbd5e1; border-radius: 6px; cursor: pointer; font-size: 11px;">
            Tandai Sudah Dibuka Manual
          </button>
        </div>

        <div id="ks-kerang-list" style="display: flex; flex-direction: column; gap: 6px;"></div>
      </div>
    `;

    document.body.appendChild(hud);

    makeDraggable(hud, {
      handle: document.getElementById("ks-radar-header"),
      storageKey: "ks_hud_pos_diving_radar"
    });

    let minimized = false;
    document.getElementById("ks-radar-toggle").onclick = () => {
      minimized = !minimized;
      document.getElementById("ks-radar-content").style.display = minimized ? "none" : "block";
      document.getElementById("ks-radar-toggle").textContent = minimized ? "□" : "_";
    };

    function updateFilterButtons() {
      const btnRare = document.getElementById("ks-filter-rare");
      const btnPot = document.getElementById("ks-filter-potensial");
      const btnAll = document.getElementById("ks-filter-all");

      if (btnRare) btnRare.style.background = currentFilterMode === "langka" ? "#7c3aed" : "rgba(255,255,255,0.1)";
      if (btnPot) btnPot.style.background = currentFilterMode === "potensial" ? "#0284c7" : "rgba(255,255,255,0.1)";
      if (btnAll) btnAll.style.background = currentFilterMode === "all" ? "#475569" : "rgba(255,255,255,0.1)";
    }

    document.getElementById("ks-filter-rare").onclick = () => {
      currentFilterMode = "langka";
      updateFilterButtons();
      renderList();
    };

    document.getElementById("ks-filter-potensial").onclick = () => {
      currentFilterMode = "potensial";
      updateFilterButtons();
      renderList();
    };

    document.getElementById("ks-filter-all").onclick = () => {
      currentFilterMode = "all";
      updateFilterButtons();
      renderList();
    };

    document.getElementById("ks-pick-nearest").onclick = () => {
      const next = getNextNearestShell();
      if (next) selectKerangTarget(next);
    };

    const resetBtn = document.getElementById("ks-reset-opened-btn");
    if (resetBtn) {
      resetBtn.onclick = () => {
        if (confirm("Reset semua tanda kerang yang sudah dibuka untuk sesi baru?")) {
          openedSet.clear();
          saveOpened();
          renderList();
        }
      };
    }

    document.getElementById("ks-radar-autopilot-btn").onclick = () => {
      toggleAutopilot();
    };

    document.getElementById("ks-mark-opened").onclick = () => {
      if (selectedKerang) {
        openedSet.add(selectedKerang.i);
        saveOpened();
        selectedKerang = null;
        document.getElementById("ks-target-tracker").style.display = "none";
        renderList();
      }
    };

    updateFilterButtons();
    renderList();
  }

  function selectKerangTarget(k) {
    selectedKerang = k;
    const tracker = document.getElementById("ks-target-tracker");
    if (tracker) {
      tracker.style.display = "block";
      document.getElementById("ks-target-title").textContent = `Target: Kerang #${k.i} (${k.kategori === "langka" ? "💎 Langka 300 Koin" : k.kategori === "biasa" ? "🟡 Biasa 100 Koin" : "Cetek"})`;
      document.getElementById("ks-target-coords").innerHTML = `
        Koordinat: X: <b>${k.x}</b>, Z: <b>${k.z}</b> | Kedalaman: <b>${k.d}m</b>
      `;
    }
    renderList();
  }

  function getPotensiStats() {
    const langkaTotal = allKerang.filter(k => k.kategori === "langka").length;
    const langkaOpened = allKerang.filter(k => k.kategori === "langka" && openedSet.has(k.i)).length;
    const langkaAvailable = Math.max(0, langkaTotal - langkaOpened);

    const biasaTotal = allKerang.filter(k => k.kategori === "biasa").length;
    const biasaOpened = allKerang.filter(k => k.kategori === "biasa" && openedSet.has(k.i)).length;
    const biasaAvailable = Math.max(0, biasaTotal - biasaOpened);

    const totalPotensi = langkaTotal + biasaTotal;
    const openedPotensi = langkaOpened + biasaOpened;
    const availablePotensi = Math.max(0, totalPotensi - openedPotensi);
    const totalAvailable = Math.max(0, allKerang.length - openedSet.size);

    return {
      langkaTotal,
      langkaOpened,
      langkaAvailable,
      biasaTotal,
      biasaOpened,
      biasaAvailable,
      totalPotensi,
      openedPotensi,
      availablePotensi,
      totalAvailable
    };
  }

  function updatePotensiStatsUI() {
    const stats = getPotensiStats();

    const elAvail = document.getElementById("ks-potensi-available-num");
    if (elAvail) elAvail.textContent = `${stats.availablePotensi} / ${stats.totalPotensi} sisa`;

    const elLangka = document.getElementById("ks-stat-langka-count");
    if (elLangka) elLangka.textContent = `${stats.langkaAvailable} / ${stats.langkaTotal} sisa`;

    const elBiasa = document.getElementById("ks-stat-biasa-count");
    if (elBiasa) elBiasa.textContent = `${stats.biasaAvailable} / ${stats.biasaTotal} sisa`;

    const elOpened = document.getElementById("ks-stat-total-opened");
    if (elOpened) elOpened.textContent = `Sudah dibuka: ${openedSet.size} / ${allKerang.length} kerang`;

    const btnRare = document.getElementById("ks-filter-rare");
    if (btnRare) btnRare.innerHTML = `💎 300 Koin (<b>${stats.langkaAvailable}</b>)`;

    const btnPot = document.getElementById("ks-filter-potensial");
    if (btnPot) btnPot.innerHTML = `🟡 100 & 300 (<b>${stats.availablePotensi}</b>)`;

    const btnAll = document.getElementById("ks-filter-all");
    if (btnAll) btnAll.innerHTML = `Semua (<b>${stats.totalAvailable}</b>)`;
  }

  function renderList() {
    updatePotensiStatsUI();

    const listContainer = document.getElementById("ks-kerang-list");
    if (!listContainer) return;
    listContainer.innerHTML = "";

    const px = livePlayer.x;
    const pz = livePlayer.z;
    const pd = livePlayer.kedalaman;

    let filtered = allKerang.filter(k => {
      if (currentFilterMode === "langka") return k.kategori === "langka";
      if (currentFilterMode === "potensial") return k.kategori === "biasa" || k.kategori === "langka";
      return true;
    });

    filtered.sort((a, b) => {
      let openedA = openedSet.has(a.i) ? 1 : 0;
      let openedB = openedSet.has(b.i) ? 1 : 0;
      if (openedA !== openedB) return openedA - openedB;
      let distA = Math.hypot(a.x - px, a.z - pz, a.d - pd);
      let distB = Math.hypot(b.x - px, b.z - pz, b.d - pd);
      return distA - distB;
    });

    filtered.forEach(k => {
      const isOpened = openedSet.has(k.i);
      const isSelected = selectedKerang && selectedKerang.i === k.i;
      const dist = Math.hypot(k.x - px, k.z - pz, k.d - pd).toFixed(1);

      const item = document.createElement("div");
      item.id = `ks-item-${k.i}`;
      item.style.cssText = `
        padding: 8px;
        background: ${isSelected ? "rgba(0, 229, 255, 0.22)" : isOpened ? "rgba(255,255,255,0.02)" : "rgba(255,255,255,0.06)"};
        border-left: 4px solid ${isOpened ? "#475569" : k.badgeColor};
        border-radius: 4px;
        cursor: pointer;
        opacity: ${isOpened ? "0.45" : "1"};
        text-decoration: ${isOpened ? "line-through" : "none"};
      `;

      item.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px;">
          <span style="font-weight: bold; color: ${isOpened ? "#94a3b8" : k.badgeColor};">Kerang #${k.i}</span>
          <span class="ks-dist-val" style="font-size: 11px; color: #38bdf8; font-weight: bold;">📍 ${dist}m</span>
        </div>
        <div style="font-size: 11px; color: #cbd5e1;">${k.labelKategori}</div>
        <div style="font-size: 10px; color: #94a3b8;">X: ${k.x}, Z: ${k.z} (Kedalaman ${k.d}m)</div>
      `;

      item.onclick = () => selectKerangTarget(k);
      listContainer.appendChild(item);
    });
  }

  function updateListDistances() {
    const px = livePlayer.x;
    const pz = livePlayer.z;
    const pd = livePlayer.kedalaman;

    allKerang.forEach(k => {
      const el = document.getElementById(`ks-item-${k.i}`);
      if (el) {
        const distEl = el.querySelector(".ks-dist-val");
        if (distEl) {
          const dist = Math.hypot(k.x - px, k.z - pz, k.d - pd).toFixed(1);
          distEl.textContent = `📍 ${dist}m`;
        }
      }
    });
  }

  let divingInitialized = false;

  function initAll() {
    if (!window.location.pathname.startsWith("/diving")) {
      return;
    }
    if (divingInitialized && document.getElementById("ks-compass-hud")) {
      return;
    }
    divingInitialized = true;
    initRadarUI();
    startCompassLoop();
  }

  // Pantau perpindahan rute SPA (Next.js client-side navigation)
  let lastRoute = window.location.pathname;
  setInterval(() => {
    const cur = window.location.pathname;
    if (cur !== lastRoute) {
      lastRoute = cur;
      if (cur.startsWith("/diving")) {
        initAll();
      } else {
        const hud = document.getElementById("ks-diving-radar-hud");
        const cmp = document.getElementById("ks-compass-hud");
        if (hud) hud.remove();
        if (cmp) cmp.remove();
        divingInitialized = false;
      }
    }
  }, 500);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    setTimeout(initAll, 800);
  }
})();
