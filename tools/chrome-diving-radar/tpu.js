// KampungSebelah - TPU & Pusaka Mbah Rukmi Radar (v1.1.0)
// Fitur: HUD Radar 12 Perabot Rumah Mbah Rukmi, Live Tracker Jam Angker (23.00-03.00 WIB),
// Transparansi Probabilitas Pusaka Server (1:200), Full Auto-Geledah Rute Optimal (Mode Kilat / Jalan)

(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  if (typeof globalThis !== "undefined") {
    globalThis.__KS_TPU_MODULE = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  console.log("[TpuRadar] Modul TPU & Pusaka Mbah Rukmi Radar v1.1.0 loaded");

  // Definisi 12 Perabot Resmi KampungSebelah di TPU & Rumah Mbah Rukmi
  // Koordinat kotak & center diambil langsung dari modul game tpu-rules (id: 437156)
  // standX & standY: titik berdiri aman dengan jarak <= 1.1m (jarak_geledah resmi game)
  const BENDA_TPU = [
    // --- 7 Perabot di Dalam Rumah Mbah Rukmi ---
    {
      id: "dipan",
      nama: "Dipan kayu",
      luar: false,
      x: 44.3,
      y: 13.15,
      kotak: { x0: 43.75, y0: 12.1, x1: 44.85, y1: 14.2 },
      standX: 45.3,
      standY: 13.15,
      icon: "🛏️"
    },
    {
      id: "lemari",
      nama: "Lemari tua",
      luar: false,
      x: 49.92,
      y: 13.15,
      kotak: { x0: 49.55, y0: 12.4, x1: 50.3, y1: 13.9 },
      standX: 49.0,
      standY: 13.15,
      icon: "🚪"
    },
    {
      id: "peti",
      nama: "Peti kayu",
      luar: false,
      x: 44.35,
      y: 15.75,
      kotak: { x0: 43.8, y0: 15.3, x1: 44.9, y1: 16.2 },
      standX: 45.2,
      standY: 15.75,
      icon: "📦"
    },
    {
      id: "tungku",
      nama: "Tungku dapur",
      luar: false,
      x: 44.52,
      y: 8.8,
      kotak: { x0: 43.75, y0: 8.3, x1: 45.3, y1: 9.3 },
      standX: 45.8,
      standY: 8.8,
      icon: "🔥"
    },
    {
      id: "gentong",
      nama: "Gentong air",
      luar: false,
      x: 49.8,
      y: 8.7,
      kotak: { x0: 49.4, y0: 8.3, x1: 50.2, y1: 9.1 },
      standX: 48.8,
      standY: 8.7,
      icon: "🏺"
    },
    {
      id: "meja",
      nama: "Meja kecil",
      luar: false,
      x: 49.2,
      y: 15.6,
      kotak: { x0: 48.8, y0: 15.32, x1: 49.6, y1: 15.88 },
      standX: 48.2,
      standY: 15.6,
      icon: "🪵"
    },
    {
      id: "bale",
      nama: "Bale bambu",
      luar: false,
      x: 49.0,
      y: 17.25,
      kotak: { x0: 48.05, y0: 16.85, x1: 49.95, y1: 17.65 },
      standX: 47.5,
      standY: 17.25,
      icon: "🛖"
    },
    // --- 5 Benda di Pekarangan Luar Rumah Mbah Rukmi ---
    {
      id: "tong",
      nama: "Tong kayu",
      luar: true,
      x: 44.7,
      y: 7.45,
      kotak: { x0: 44.3, y0: 7.05, x1: 45.1, y1: 7.85 },
      standX: 44.7,
      standY: 6.5,
      icon: "🪣"
    },
    {
      id: "kayu",
      nama: "Kayu bakar",
      luar: true,
      x: 48.55,
      y: 7.47,
      kotak: { x0: 47.5, y0: 7.1, x1: 49.6, y1: 7.85 },
      standX: 48.55,
      standY: 6.5,
      icon: "🪵"
    },
    {
      id: "kandang",
      nama: "Kandang ayam",
      luar: true,
      x: 53.85,
      y: 10.4,
      kotak: { x0: 53.0, y0: 9.8, x1: 54.7, y1: 11.0 },
      standX: 52.3,
      standY: 10.4,
      icon: "🐔"
    },
    {
      id: "lesung",
      nama: "Lesung batu",
      luar: true,
      x: 52.9,
      y: 15.62,
      kotak: { x0: 52.2, y0: 15.3, x1: 53.6, y1: 15.95 },
      standX: 51.5,
      standY: 15.62,
      icon: "🪨"
    },
    {
      id: "sumur",
      nama: "Sumur tua",
      luar: true,
      x: 39.5,
      y: 21.5,
      kotak: { x0: 38.55, y0: 20.55, x1: 40.45, y1: 22.45 },
      standX: 39.5,
      standY: 20.0,
      icon: "🪣"
    }
  ];

  // Hitung jarak ke kotak interaksi benda (mengikuti rumus jarak_geledah game di modul 265409)
  function distanceToBox(px, py, kotak) {
    const dx = Math.max(kotak.x0 - px, 0, px - kotak.x1);
    const dy = Math.max(kotak.y0 - py, 0, py - kotak.y1);
    return Math.hypot(dx, dy);
  }

  // Periksa apakah waktu saat ini masuk Jam Angker (23:00 - 03:00 WIB)
  function checkJamAngker(customDate = null) {
    const now = customDate || new Date();
    const utc = now.getTime() + now.getTimezoneOffset() * 60000;
    const wib = new Date(utc + 7 * 3600000);
    const hour = wib.getHours();
    const min = wib.getMinutes();
    const isAngker = hour >= 23 || hour < 3;
    const timeStr = `${String(hour).padStart(2, "0")}:${String(min).padStart(2, "0")} WIB`;
    return { isAngker, hour, min, timeStr };
  }

  // Rute optimal penggeledahan (urutkan dari luar pekarangan hingga dalam rumah)
  function getOptimalSearchRoute(unsearchedIds = []) {
    const orderPreference = [
      "sumur", "lesung", "kandang", "tong", "kayu",
      "bale", "meja", "peti", "dipan", "lemari", "tungku", "gentong"
    ];
    return unsearchedIds.sort((a, b) => {
      const idxA = orderPreference.indexOf(a);
      const idxB = orderPreference.indexOf(b);
      return (idxA === -1 ? 99 : idxA) - (idxB === -1 ? 99 : idxB);
    });
  }

  // Hitung input virtual joystick (sx, sy) relative terhadap kamera (yaw) pemain
  // Game 3D third-person: e.h = yaw - atan2(sx, sy) -> sx = sin(yaw - targetAngle), sy = cos(yaw - targetAngle)
  function calculateStick(targetX, targetY, px, py, playerYaw) {
    const dx = targetX - px;
    const dy = targetY - py;
    const dist = Math.hypot(dx, dy);
    if (dist < 0.1) return { sx: 0, sy: 0, dist };

    const targetAngle = Math.atan2(dx, dy);
    const relAngle = playerYaw - targetAngle;
    const sx = Math.sin(relAngle);
    const sy = Math.cos(relAngle);
    return { sx, sy, dist, targetAngle };
  }

  // Waypoint navigator jalan pemakaman resmi (taat marka jalan, bypass pohon bundaran & pintu rumah)
  function getNextWaypoint(px, py, target) {
    // 1. Jalur utama dari Gerbang (y = 150.8) turun ke y = 36.0
    if (py > 102) {
      return { x: 31.5, y: 102 };
    }
    if (py > 90) {
      // Bypass pohon beringin bundaran di tengah (x: 31.5, y: 96, r: 1.7)
      if (py > 96) return { x: 34.8, y: 96 };
      return { x: 31.5, y: 90 };
    }
    if (py > 36) {
      return { x: 31.5, y: 36 };
    }
    // 2. Jalur kuno belok menuju Rumah Mbah Rukmi (y = 36 down to y = 22)
    if (py > 22) {
      if (py > 31) return { x: 36.5, y: 31 };
      if (py > 26.5) return { x: 42.0, y: 26.5 };
      if (py > 22.0) return { x: 46.2, y: 22.0 };
      return { x: 47.0, y: 18.7 };
    }

    // 3. Area pekarangan & rumah Mbah Rukmi (py <= 22)
    const playerInHouse = (px >= 43.5 && px <= 50.5 && py >= 8.0 && py <= 16.5);
    const targetInHouse = !target.luar;

    // Pemain di luar, perabot di dalam -> lewat pintu
    if (!playerInHouse && targetInHouse) {
      if (py > 17.2) return { x: 47.0, y: 17.5 }; // Depan pintu luar
      if (py > 15.8) return { x: 47.0, y: 15.5 }; // Lewat pintu masuk ke dalam
      return { x: target.standX, y: target.standY };
    }

    // Pemain di dalam, perabot di luar -> keluar lewat pintu
    if (playerInHouse && !targetInHouse) {
      if (py < 16.0) return { x: 47.0, y: 16.0 }; // Depan pintu dalam
      if (py < 18.0) return { x: 47.0, y: 18.0 }; // Keluar pintu ke teras
      return { x: target.standX, y: target.standY };
    }

    return { x: target.standX, y: target.standY };
  }

  // Status & State
  const tpuState = {
    active: false,
    autoGeledah: false,
    mode: "kilat", // "kilat" (teleport instant ke target) atau "jalan" (navigasi waypoint)
    playerX: 0,
    playerY: 0,
    playerYaw: 0,
    sudahDigeledah: new Set(),
    currentTargetId: null,
    phase: "IDLE", // IDLE, NAVIGATING, SEARCHING, DONE
    lastActionTime: 0,
    stuckCheckTime: 0,
    lastPos: { x: 0, y: 0 },
    pusakaDitemukan: null,
    logs: []
  };

  // Helper Logging ke HUD
  function addLog(msg) {
    const time = new Date().toLocaleTimeString("id-ID", { hour12: false });
    tpuState.logs.unshift(`[${time}] ${msg}`);
    if (tpuState.logs.length > 8) tpuState.logs.pop();
    renderLogs();
  }

  // Dispatch Stick Navigation ke 3D Controller
  function sendStick(turn, forward) {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("ks_tpu_set_stick", {
        detail: { turn, forward }
      }));
    }
  }

  function stopNavigation() {
    sendStick(0, 0);
  }

  // Dispatch Teleport ke 3D Controller
  function teleportTo(x, y, h = null) {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("ks_tpu_teleport", {
        detail: { x, y, h }
      }));
    }
  }

  // Listener data posisi live dari inject.js
  if (typeof window !== "undefined") {
    window.addEventListener("ks_tpu_data_update", (e) => {
      const d = e.detail || {};
      if (typeof d.x === "number" && typeof d.y === "number") {
        tpuState.playerX = d.x;
        tpuState.playerY = d.y;
        tpuState.playerYaw = typeof d.yaw === "number" ? d.yaw : 0;
        updateTpuHud();
      }
    });
  }

  // UI / HUD Controller
  let tpuHudContainer = null;

  function initTpuHud() {
    if (tpuHudContainer || typeof document === "undefined") return;

    tpuHudContainer = document.createElement("div");
    tpuHudContainer.id = "ks-tpu-hud-panel";
    tpuHudContainer.style.cssText = `
      position: fixed;
      top: 75px;
      left: 20px;
      width: 330px;
      max-height: 85vh;
      overflow-y: auto;
      background: rgba(15, 23, 42, 0.94);
      backdrop-filter: blur(12px);
      border: 1px solid rgba(139, 92, 246, 0.4);
      border-radius: 12px;
      padding: 12px;
      color: #f8fafc;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      font-size: 12px;
      z-index: 999999;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.7), 0 0 15px rgba(139, 92, 246, 0.3);
      user-select: none;
      display: none;
    `;

    // Restore saved position from localStorage
    try {
      const saved = localStorage.getItem("ks_tpu_hud_pos");
      if (saved) {
        const { left, top } = JSON.parse(saved);
        if (typeof left === "number" && typeof top === "number") {
          tpuHudContainer.style.left = `${Math.max(10, Math.min(window.innerWidth - 340, left))}px`;
          tpuHudContainer.style.top = `${Math.max(10, Math.min(window.innerHeight - 200, top))}px`;
        }
      }
      const savedMode = localStorage.getItem("ks_tpu_mode");
      if (savedMode === "jalan" || savedMode === "kilat") {
        tpuState.mode = savedMode;
      }
    } catch (e) {}

    // Rancang DOM struktur SEKALI SAJA (Anti-InnerHTML Wipeout saat Click)
    tpuHudContainer.innerHTML = `
      <div id="ks-tpu-drag-handle" style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:6px; margin-bottom:8px; cursor:move;">
        <span style="font-weight:700; color:#c084fc; font-size:13px;">👻 TPU & Pusaka Mbah Rukmi</span>
        <span id="ks-tpu-jam-badge" style="font-size:10px; background:#16a34a; padding:2px 6px; border-radius:4px; font-weight:600;">
          🟢 JAM ANGKER
        </span>
      </div>

      <!-- Info Waktu & Transparansi Pusaka -->
      <div style="background:rgba(255,255,255,0.05); border-radius:6px; padding:6px 8px; margin-bottom:8px; line-height:1.4;">
        <div style="display:flex; justify-content:space-between; margin-bottom:2px;">
          <span style="color:#94a3b8;">Waktu Server:</span>
          <span id="ks-tpu-waktu-server" style="color:#e2e8f0; font-weight:600;">--:-- WIB</span>
        </div>
        <div style="display:flex; justify-content:space-between; margin-bottom:2px;">
          <span style="color:#94a3b8;">Sisa Benda:</span>
          <span id="ks-tpu-sisa-benda" style="color:#38bdf8; font-weight:600;">12 / 12 Benda</span>
        </div>
        <div style="color:#a855f7; font-size:11px; margin-top:4px;">
          ⚡ <b>Pusaka Server RNG (1:200)</b>: Lokasi tidak ada di client/scene sebelum tombol ditekan. Semua 12 benda punya peluang sama!
        </div>
      </div>

      <!-- Tombol Kontrol Auto-Geledah & Mode -->
      <div style="display:flex; gap:6px; margin-bottom:8px;">
        <button id="ks-btn-auto-geledah" style="flex:1.2; padding:7px; border:none; border-radius:6px; font-weight:700; cursor:pointer; background:#8b5cf6; color:#fff; transition:all 0.15s ease;">
          ▶ AUTO-GELEDAH 12
        </button>
        <button id="ks-btn-mode-tpu" title="Klik untuk beralih mode Kilat (Instant Warp) atau Jalan (Navigasi Alami)" style="flex:0.9; padding:7px 8px; border:1px solid rgba(139,92,246,0.5); border-radius:6px; font-weight:600; cursor:pointer; background:rgba(139,92,246,0.18); color:#e9d5ff;">
          ⚡ Kilat
        </button>
        <button id="ks-btn-reset-tpu" title="Reset daftar periksa 12 benda" style="padding:7px 10px; border:1px solid rgba(255,255,255,0.2); border-radius:6px; background:transparent; color:#cbd5e1; cursor:pointer;">
          🔄 Reset
        </button>
      </div>

      <!-- Benda Terdekat -->
      <div style="background:rgba(139, 92, 246, 0.15); border:1px solid rgba(139,92,246,0.3); border-radius:6px; padding:6px 8px; margin-bottom:8px;">
        <div id="ks-tpu-terdekat-nama" style="font-weight:600; color:#e9d5ff; margin-bottom:2px;">📍 Terdekat: -</div>
        <div style="display:flex; justify-content:space-between; font-size:11px; color:#cbd5e1;">
          <span>Jarak: <b id="ks-tpu-terdekat-jarak">-</b> <span id="ks-tpu-siap-geledah" style="color:#4ade80; display:none;">(✅ Siap Geledah)</span></span>
          <span id="ks-tpu-terdekat-status" style="color:#facc15;">Belum Diperiksa</span>
        </div>
      </div>

      <!-- Daftar 12 Perabot & Status -->
      <div style="margin-bottom:8px;">
        <div style="font-weight:600; color:#94a3b8; font-size:11px; margin-bottom:4px;">DAFTAR 12 PERABOT:</div>
        <div id="ks-tpu-grid-benda" style="max-height:130px; overflow-y:auto; display:grid; grid-template-columns:1fr 1fr; gap:4px; font-size:11px;">
          ${BENDA_TPU.map(b => `
            <div id="ks-item-${b.id}" style="padding:3px 5px; border-radius:4px; background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.08); display:flex; justify-content:space-between; align-items:center;">
              <span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${b.icon} ${b.nama}</span>
              <span id="ks-check-${b.id}" style="font-size:10px; color:#94a3b8;">○</span>
            </div>
          `).join("")}
        </div>
      </div>

      <!-- Log Aktivitas -->
      <div style="border-top:1px solid rgba(255,255,255,0.1); padding-top:6px;">
        <div style="font-size:10px; color:#64748b; margin-bottom:2px;">LOG AKTIVITAS:</div>
        <div id="ks-tpu-log-list" style="font-family:monospace; font-size:10px; color:#cbd5e1; max-height:60px; overflow-y:auto;">
          <span style="color:#64748b;">Belum ada aktivitas</span>
        </div>
      </div>
    `;

    // Pasang Event Tombol SEKALI SAJA
    const btnAuto = tpuHudContainer.querySelector("#ks-btn-auto-geledah");
    if (btnAuto) {
      btnAuto.onclick = (e) => {
        e.preventDefault();
        e.stopPropagation();
        tpuState.autoGeledah = !tpuState.autoGeledah;
        if (tpuState.autoGeledah) {
          tpuState.phase = "IDLE";
          tpuState.currentTargetId = null;
          tpuState.stuckCheckTime = Date.now();
          tpuState.lastPos = { x: tpuState.playerX, y: tpuState.playerY };
          addLog(`▶ Auto-geledah dimulai (Mode: ${tpuState.mode.toUpperCase()})`);
        } else {
          stopNavigation();
          addLog("⏹ Auto-geledah dihentikan manual");
        }
        updateTpuHud();
      };
    }

    const btnMode = tpuHudContainer.querySelector("#ks-btn-mode-tpu");
    if (btnMode) {
      btnMode.onclick = (e) => {
        e.preventDefault();
        e.stopPropagation();
        tpuState.mode = tpuState.mode === "kilat" ? "jalan" : "kilat";
        try {
          localStorage.setItem("ks_tpu_mode", tpuState.mode);
        } catch (err) {}
        addLog(`Switched mode ke: ${tpuState.mode === "kilat" ? "⚡ KILAT (Instant Warp)" : "🚶 JALAN (Navigasi Alami)"}`);
        updateTpuHud();
      };
    }

    const btnReset = tpuHudContainer.querySelector("#ks-btn-reset-tpu");
    if (btnReset) {
      btnReset.onclick = (e) => {
        e.preventDefault();
        e.stopPropagation();
        tpuState.sudahDigeledah.clear();
        tpuState.currentTargetId = null;
        tpuState.phase = "IDLE";
        addLog("🔄 Status 12 benda di-reset");
        updateTpuHud();
      };
    }

    // Make Draggable
    setupDraggable(tpuHudContainer, "ks_tpu_hud_pos");

    document.body.appendChild(tpuHudContainer);
    updateTpuHud();
  }

  function setupDraggable(el, storageKey) {
    if (typeof window === "undefined") return;
    let isDragging = false;
    let startX = 0, startY = 0, initialLeft = 0, initialTop = 0;

    el.addEventListener("mousedown", (e) => {
      if (e.target.tagName === "BUTTON" || e.target.closest("button")) return;
      isDragging = true;
      startX = e.clientX;
      startY = e.clientY;
      const rect = el.getBoundingClientRect();
      initialLeft = rect.left;
      initialTop = rect.top;
      e.preventDefault();
    });

    window.addEventListener("mousemove", (e) => {
      if (!isDragging) return;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      let newLeft = initialLeft + dx;
      let newTop = initialTop + dy;
      newLeft = Math.max(10, Math.min(window.innerWidth - el.offsetWidth - 10, newLeft));
      newTop = Math.max(10, Math.min(window.innerHeight - el.offsetHeight - 10, newTop));
      el.style.left = `${newLeft}px`;
      el.style.top = `${newTop}px`;
    });

    window.addEventListener("mouseup", () => {
      if (isDragging) {
        isDragging = false;
        try {
          const rect = el.getBoundingClientRect();
          localStorage.setItem(storageKey, JSON.stringify({ left: rect.left, top: rect.top }));
        } catch (e) {}
      }
    });
  }

  function renderLogs() {
    if (!tpuHudContainer) return;
    const logList = tpuHudContainer.querySelector("#ks-tpu-log-list");
    if (logList) {
      if (tpuState.logs.length === 0) {
        logList.innerHTML = "<span style='color:#64748b;'>Belum ada aktivitas</span>";
      } else {
        logList.innerHTML = tpuState.logs.map(l => `<div>${l}</div>`).join("");
      }
    }
  }

  // Update elemen secara presisi tanpa mengganti innerHTML container
  function updateTpuHud() {
    if (!tpuHudContainer || typeof document === "undefined") return;

    const inTpu = !!document.querySelector('[data-testid="jelajah-tpu"]') || !!document.querySelector('[data-testid="tpu-panel"]');
    if (!inTpu) {
      tpuHudContainer.style.display = "none";
      return;
    }
    tpuHudContainer.style.display = "block";

    const jam = checkJamAngker();
    const px = tpuState.playerX;
    const py = tpuState.playerY;

    // 1. Update Jam Badge
    const jamBadge = tpuHudContainer.querySelector("#ks-tpu-jam-badge");
    if (jamBadge) {
      jamBadge.style.background = jam.isAngker ? "#16a34a" : "#dc2626";
      jamBadge.textContent = jam.isAngker ? "🟢 JAM ANGKER" : "🔴 DILUAR JAM";
    }

    // 2. Update Waktu Server & Sisa
    const waktuEl = tpuHudContainer.querySelector("#ks-tpu-waktu-server");
    if (waktuEl) waktuEl.textContent = jam.timeStr;

    const sisaCount = BENDA_TPU.length - tpuState.sudahDigeledah.size;
    const sisaEl = tpuHudContainer.querySelector("#ks-tpu-sisa-benda");
    if (sisaEl) sisaEl.textContent = `${sisaCount} / 12 Benda`;

    // 3. Update Tombol Auto & Mode
    const btnAuto = tpuHudContainer.querySelector("#ks-btn-auto-geledah");
    if (btnAuto) {
      btnAuto.style.background = tpuState.autoGeledah ? "#ef4444" : "#8b5cf6";
      btnAuto.textContent = tpuState.autoGeledah ? "⏹ STOP AUTO" : "▶ AUTO-GELEDAH 12";
    }

    const btnMode = tpuHudContainer.querySelector("#ks-btn-mode-tpu");
    if (btnMode) {
      btnMode.textContent = tpuState.mode === "kilat" ? "⚡ Kilat" : "🚶 Jalan";
    }

    // 4. Hitung Benda Terdekat
    const bendaWithDist = BENDA_TPU.map(b => {
      const dist = distanceToBox(px, py, b.kotak);
      const sudah = tpuState.sudahDigeledah.has(b.id);
      return { ...b, dist: Math.round(dist * 10) / 10, sudah };
    }).sort((a, b) => a.dist - b.dist);

    const terdekat = bendaWithDist[0] || null;

    const terdekatNama = tpuHudContainer.querySelector("#ks-tpu-terdekat-nama");
    if (terdekatNama) {
      terdekatNama.textContent = `📍 Terdekat: ${terdekat ? `${terdekat.icon} ${terdekat.nama}` : "-"}`;
    }

    const terdekatJarak = tpuHudContainer.querySelector("#ks-tpu-terdekat-jarak");
    if (terdekatJarak) {
      terdekatJarak.textContent = terdekat ? `${terdekat.dist}m` : "-";
    }

    const siapGeledah = tpuHudContainer.querySelector("#ks-tpu-siap-geledah");
    if (siapGeledah) {
      siapGeledah.style.display = (terdekat && terdekat.dist <= 1.1) ? "inline" : "none";
    }

    const terdekatStatus = tpuHudContainer.querySelector("#ks-tpu-terdekat-status");
    if (terdekatStatus) {
      if (terdekat && terdekat.sudah) {
        terdekatStatus.style.color = "#4ade80";
        terdekatStatus.textContent = "Sudah Diperiksa";
      } else {
        terdekatStatus.style.color = "#facc15";
        terdekatStatus.textContent = "Belum Diperiksa";
      }
    }

    // 5. Update Grid Checklist 12 Benda
    for (const b of BENDA_TPU) {
      const itemEl = tpuHudContainer.querySelector(`#ks-item-${b.id}`);
      const checkEl = tpuHudContainer.querySelector(`#ks-check-${b.id}`);
      if (!itemEl || !checkEl) continue;

      const sudah = tpuState.sudahDigeledah.has(b.id);
      const isTarget = tpuState.currentTargetId === b.id;

      if (isTarget) {
        itemEl.style.background = "rgba(168, 85, 247, 0.35)";
        itemEl.style.border = "1px solid #c084fc";
      } else if (sudah) {
        itemEl.style.background = "rgba(34, 197, 94, 0.15)";
        itemEl.style.border = "1px solid rgba(34,197,94,0.3)";
      } else {
        itemEl.style.background = "rgba(255,255,255,0.05)";
        itemEl.style.border = "1px solid rgba(255,255,255,0.08)";
      }

      checkEl.style.color = sudah ? "#4ade80" : "#94a3b8";
      checkEl.textContent = sudah ? "✓" : "○";
    }
  }

  // Engine Auto-Geledah Loop (dijalankan di browser)
  if (typeof window !== "undefined") {
    setInterval(() => {
      // Sync apakah TPU sedang terbuka
      const jelajahEl = document.querySelector('[data-testid="jelajah-tpu"]') || document.querySelector('[data-testid="tpu-panel"]');
      if (!jelajahEl) {
        if (tpuState.autoGeledah) {
          tpuState.autoGeledah = false;
          stopNavigation();
        }
        updateTpuHud();
        return;
      }

      // Deteksi jika benda saat ini sudah digeledah menurut tanda game
      const sudahEl = document.querySelector('[data-testid="tpu-sudah"]');
      if (sudahEl && tpuState.currentTargetId) {
        tpuState.sudahDigeledah.add(tpuState.currentTargetId);
      }

      // Periksa jika hasil geledah sedang terbuka ([data-testid="tpu-hasil-cari"])
      const hasilModal = document.querySelector('[data-testid="tpu-hasil-cari"]');
      if (hasilModal) {
        const tutupBtn = document.querySelector('[data-testid="tpu-hasil-tutup"]');
        if (tutupBtn) {
          const temuanText = hasilModal.innerText || "";
          if (temuanText.includes("Kamu menemukan")) {
            addLog("🎉 PUSAKA DITEMUKAN! Pusaka masuk tas!");
          } else {
            addLog("Hasil geledah selesai: Kosong");
          }
          if (tpuState.currentTargetId) {
            tpuState.sudahDigeledah.add(tpuState.currentTargetId);
          }
          tutupBtn.click();
          tpuState.phase = "IDLE";
          tpuState.currentTargetId = null;
          tpuState.lastActionTime = Date.now();
          updateTpuHud();
          return;
        }
      }

      // Jika sedang dalam modal menggeledah (progress bar 5 detik)
      const menggeledahModal = document.querySelector('[data-testid="tpu-menggeledah"]');
      if (menggeledahModal) {
        stopNavigation();
        tpuState.phase = "SEARCHING";
        return;
      }

      if (!tpuState.autoGeledah) {
        updateTpuHud();
        return;
      }

      // State Machine Auto-Geledah
      const now = Date.now();
      if (now - tpuState.lastActionTime < 150) return;

      const px = tpuState.playerX;
      const py = tpuState.playerY;

      // 1. Fase IDLE: Pilih target perabot berikutnya
      if (tpuState.phase === "IDLE") {
        const sisa = BENDA_TPU.filter(b => !tpuState.sudahDigeledah.has(b.id)).map(b => b.id);
        if (sisa.length === 0) {
          tpuState.autoGeledah = false;
          tpuState.phase = "DONE";
          stopNavigation();
          addLog("🏆 SEMUA 12 BENDA SELESAI DIGELEDAH!");
          updateTpuHud();
          return;
        }

        const sortedRoute = getOptimalSearchRoute(sisa);
        tpuState.currentTargetId = sortedRoute[0];
        const targetBenda = BENDA_TPU.find(b => b.id === tpuState.currentTargetId);
        addLog(`🎯 Target berikutnya: ${targetBenda.icon} ${targetBenda.nama}`);
        tpuState.phase = "NAVIGATING";
        tpuState.lastActionTime = now;
        tpuState.stuckCheckTime = now;
        tpuState.lastPos = { x: px, y: py };
        updateTpuHud();
        return;
      }

      // 2. Fase NAVIGATING: Menuju target
      if (tpuState.phase === "NAVIGATING") {
        const target = BENDA_TPU.find(b => b.id === tpuState.currentTargetId);
        if (!target) {
          tpuState.phase = "IDLE";
          return;
        }

        const dist = distanceToBox(px, py, target.kotak);
        const btnGeledah = document.querySelector('[data-testid="tpu-geledah-btn"]');

        // Jika sudah di samping benda atau tombol Geledah sudah muncul
        if (dist <= 1.15 || (btnGeledah && !btnGeledah.disabled)) {
          stopNavigation();
          tpuState.phase = "SEARCHING";

          if (btnGeledah && !btnGeledah.disabled) {
            addLog(`🔍 Tiba di ${target.nama}. Memulai geledah...`);
            btnGeledah.click();
          } else {
            addLog(`📍 Tiba di ${target.nama}. Menunggu tombol geledah...`);
          }
          tpuState.lastActionTime = now;
          updateTpuHud();
          return;
        }

        // Eksekusi Perpindahan ke Target
        if (tpuState.mode === "kilat") {
          // Mode Kilat (Instant Warp): Langsung teleport ke koordinat interaksi benda
          teleportTo(target.standX, target.standY);
          tpuState.lastActionTime = now;
        } else {
          // Mode Jalan (Navigasi Alami Waypoint)
          const nextWp = getNextWaypoint(px, py, target);
          const stick = calculateStick(nextWp.x, nextWp.y, px, py, tpuState.playerYaw);
          sendStick(stick.sx, stick.sy);

          // Proteksi Anti-Stuck: jika diam > 2.5s tidak bergeser, auto-nudge langsung ke target
          const movedDist = Math.hypot(px - tpuState.lastPos.x, py - tpuState.lastPos.y);
          if (movedDist < 0.15) {
            if (now - tpuState.stuckCheckTime > 2500) {
              addLog(`⚠️ Terhalang rintangan, auto-nudge ke samping ${target.nama}...`);
              teleportTo(target.standX, target.standY);
              tpuState.stuckCheckTime = now;
            }
          } else {
            tpuState.lastPos = { x: px, y: py };
            tpuState.stuckCheckTime = now;
          }
        }
      }
    }, 100);

    // Inisialisasi saat DOM siap
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", initTpuHud);
    } else {
      initTpuHud();
    }

    // Watcher untuk mendeteksi kapan modal TPU dibuka
    const observer = new MutationObserver(() => {
      updateTpuHud();
    });
    if (document.body) {
      observer.observe(document.body, { childList: true, subtree: true });
    }
  }

  return {
    BENDA_TPU,
    distanceToBox,
    checkJamAngker,
    getOptimalSearchRoute,
    calculateStick,
    getNextWaypoint,
    teleportTo,
    sendStick,
    stopNavigation,
    tpuState
  };
});
