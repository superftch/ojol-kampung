// KampungSebelah - TPU & Pusaka Mbah Rukmi Radar (v1.0.0)
// Fitur: HUD Radar 12 Perabot Rumah Mbah Rukmi, Live Tracker Jam Angker (23.00-03.00 WIB),
// Transparansi Probabilitas Pusaka Server (1:200), dan Full Auto-Geledah Rute Optimal

(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  if (typeof globalThis !== "undefined") {
    globalThis.__KS_TPU_MODULE = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  console.log("[TpuRadar] Modul TPU & Pusaka Mbah Rukmi Radar v1.0.0 loaded");

  // Definisi 12 Perabot Resmi KampungSebelah di TPU & Rumah Mbah Rukmi
  // Koordinat kotak & center diambil langsung dari modul game tpu-rules (id: 437156)
  const BENDA_TPU = [
    // --- 7 Perabot di Dalam Rumah Mbah Rukmi ---
    {
      id: "dipan",
      nama: "Dipan kayu",
      luar: false,
      x: 44.3,
      y: 13.15,
      kotak: { x0: 43.75, y0: 12.1, x1: 44.85, y1: 14.2 },
      icon: "🛏️"
    },
    {
      id: "lemari",
      nama: "Lemari tua",
      luar: false,
      x: 49.92,
      y: 13.15,
      kotak: { x0: 49.55, y0: 12.4, x1: 50.3, y1: 13.9 },
      icon: "🚪"
    },
    {
      id: "peti",
      nama: "Peti kayu",
      luar: false,
      x: 44.35,
      y: 15.75,
      kotak: { x0: 43.8, y0: 15.3, x1: 44.9, y1: 16.2 },
      icon: "📦"
    },
    {
      id: "tungku",
      nama: "Tungku dapur",
      luar: false,
      x: 44.52,
      y: 8.8,
      kotak: { x0: 43.75, y0: 8.3, x1: 45.3, y1: 9.3 },
      icon: "🔥"
    },
    {
      id: "gentong",
      nama: "Gentong air",
      luar: false,
      x: 49.8,
      y: 8.7,
      kotak: { x0: 49.4, y0: 8.3, x1: 50.2, y1: 9.1 },
      icon: "🏺"
    },
    {
      id: "meja",
      nama: "Meja kecil",
      luar: false,
      x: 49.2,
      y: 15.6,
      kotak: { x0: 48.8, y0: 15.32, x1: 49.6, y1: 15.88 },
      icon: "🪵"
    },
    {
      id: "bale",
      nama: "Bale bambu",
      luar: false,
      x: 49.0,
      y: 17.25,
      kotak: { x0: 48.05, y0: 16.85, x1: 49.95, y1: 17.65 },
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
      icon: "🪣"
    },
    {
      id: "kayu",
      nama: "Kayu bakar",
      luar: true,
      x: 48.55,
      y: 7.47,
      kotak: { x0: 47.5, y0: 7.1, x1: 49.6, y1: 7.85 },
      icon: "🪵"
    },
    {
      id: "kandang",
      nama: "Kandang ayam",
      luar: true,
      x: 53.85,
      y: 10.4,
      kotak: { x0: 53.0, y0: 9.8, x1: 54.7, y1: 11.0 },
      icon: "🐔"
    },
    {
      id: "lesung",
      nama: "Lesung batu",
      luar: true,
      x: 52.9,
      y: 15.62,
      kotak: { x0: 52.2, y0: 15.3, x1: 53.6, y1: 15.95 },
      icon: "🪨"
    },
    {
      id: "sumur",
      nama: "Sumur tua",
      luar: true,
      x: 39.5,
      y: 21.5,
      kotak: { x0: 38.55, y0: 20.55, x1: 40.45, y1: 22.45 },
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

  // Status & State
  const tpuState = {
    active: false,
    autoGeledah: false,
    playerX: 0,
    playerY: 0,
    playerYaw: 0,
    sudahDigeledah: new Set(),
    currentTargetId: null,
    phase: "IDLE", // IDLE, NAVIGATING, SEARCHING, COLLECTING, DONE
    lastActionTime: 0,
    pusakaDitemukan: null,
    logs: []
  };

  // Helper Logging ke HUD
  function addLog(msg) {
    const time = new Date().toLocaleTimeString("id-ID", { hour12: false });
    tpuState.logs.unshift(`[${time}] ${msg}`);
    if (tpuState.logs.length > 8) tpuState.logs.pop();
    updateTpuHud();
  }

  // Hanya jalankan listener & UI di browser
  if (typeof window !== "undefined") {
    window.addEventListener("ks_tpu_data_update", (e) => {
      const d = e.detail || {};
      if (typeof d.x === "number" && typeof d.y === "number") {
        tpuState.playerX = d.x;
        tpuState.playerY = d.y;
        tpuState.playerYaw = d.yaw || 0;
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
      width: 320px;
      max-height: 85vh;
      overflow-y: auto;
      background: rgba(15, 23, 42, 0.92);
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
          tpuHudContainer.style.left = `${Math.max(10, Math.min(window.innerWidth - 330, left))}px`;
          tpuHudContainer.style.top = `${Math.max(10, Math.min(window.innerHeight - 200, top))}px`;
        }
      }
    } catch (e) {}

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

    // Hitung jarak ke semua benda
    const bendaWithDist = BENDA_TPU.map(b => {
      const dist = distanceToBox(px, py, b.kotak);
      const sudah = tpuState.sudahDigeledah.has(b.id);
      return { ...b, dist: Math.round(dist * 10) / 10, sudah };
    }).sort((a, b) => a.dist - b.dist);

    const terdekat = bendaWithDist[0] || null;
    const belumCount = BENDA_TPU.length - tpuState.sudahDigeledah.size;

    tpuHudContainer.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:6px; margin-bottom:8px; cursor:move;">
        <span style="font-weight:700; color:#c084fc; font-size:13px;">👻 TPU & Pusaka Mbah Rukmi</span>
        <span style="font-size:10px; background:${jam.isAngker ? "#16a34a" : "#dc2626"}; padding:2px 6px; border-radius:4px; font-weight:600;">
          ${jam.isAngker ? "🟢 JAM ANGKER" : "🔴 DILUAR JAM"}
        </span>
      </div>

      <!-- Info Waktu & Transparansi Pusaka -->
      <div style="background:rgba(255,255,255,0.05); border-radius:6px; padding:6px 8px; margin-bottom:8px; line-height:1.4;">
        <div style="display:flex; justify-content:space-between; margin-bottom:2px;">
          <span style="color:#94a3b8;">Waktu Server:</span>
          <span style="color:#e2e8f0; font-weight:600;">${jam.timeStr}</span>
        </div>
        <div style="display:flex; justify-content:space-between; margin-bottom:2px;">
          <span style="color:#94a3b8;">Sisa Benda:</span>
          <span style="color:#38bdf8; font-weight:600;">${belumCount} / 12 Benda</span>
        </div>
        <div style="color:#a855f7; font-size:11px; margin-top:4px;">
          ⚡ <b>Pusaka Server RNG (1:200)</b>: Lokasi tidak ada di client/scene sebelum tombol ditekan. Semua 12 benda punya peluang sama!
        </div>
      </div>

      <!-- Tombol Kontrol Auto-Geledah -->
      <div style="display:flex; gap:6px; margin-bottom:8px;">
        <button id="ks-btn-auto-geledah" style="flex:1; padding:7px; border:none; border-radius:6px; font-weight:700; cursor:pointer; background:${tpuState.autoGeledah ? "#ef4444" : "#8b5cf6"}; color:#fff;">
          ${tpuState.autoGeledah ? "⏹ STOP AUTO" : "▶ AUTO-GELEDAH 12"}
        </button>
        <button id="ks-btn-reset-tpu" style="padding:7px 10px; border:1px solid rgba(255,255,255,0.2); border-radius:6px; background:transparent; color:#cbd5e1; cursor:pointer;">
          🔄 Reset
        </button>
      </div>

      <!-- Benda Terdekat -->
      <div style="background:rgba(139, 92, 246, 0.15); border:1px solid rgba(139,92,246,0.3); border-radius:6px; padding:6px 8px; margin-bottom:8px;">
        <div style="font-weight:600; color:#e9d5ff; margin-bottom:2px;">📍 Terdekat: ${terdekat ? `${terdekat.icon} ${terdekat.nama}` : "-"}</div>
        <div style="display:flex; justify-content:space-between; font-size:11px; color:#cbd5e1;">
          <span>Jarak: <b>${terdekat ? `${terdekat.dist}m` : "-"}</b> ${terdekat && terdekat.dist <= 1.1 ? "(✅ Siap Geledah)" : ""}</span>
          <span style="color:${terdekat && terdekat.sudah ? "#4ade80" : "#facc15"}">${terdekat && terdekat.sudah ? "Sudah Diperiksa" : "Belum Diperiksa"}</span>
        </div>
      </div>

      <!-- Daftar 12 Perabot & Status -->
      <div style="margin-bottom:8px;">
        <div style="font-weight:600; color:#94a3b8; font-size:11px; margin-bottom:4px;">DAFTAR 12 PERABOT:</div>
        <div style="max-height:130px; overflow-y:auto; display:grid; grid-template-columns:1fr 1fr; gap:4px; font-size:11px;">
          ${BENDA_TPU.map(b => {
            const sudah = tpuState.sudahDigeledah.has(b.id);
            const isTarget = tpuState.currentTargetId === b.id;
            return `
              <div style="padding:3px 5px; border-radius:4px; background:${isTarget ? "rgba(168, 85, 247, 0.3)" : sudah ? "rgba(34, 197, 94, 0.15)" : "rgba(255,255,255,0.05)"}; border:1px solid ${isTarget ? "#c084fc" : sudah ? "rgba(34,197,94,0.3)" : "rgba(255,255,255,0.08)"}; display:flex; justify-content:space-between; align-items:center;">
                <span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${b.icon} ${b.nama}</span>
                <span style="font-size:10px; color:${sudah ? "#4ade80" : "#94a3b8"};">${sudah ? "✓" : "○"}</span>
              </div>
            `;
          }).join("")}
        </div>
      </div>

      <!-- Log Aktivitas -->
      <div style="border-top:1px solid rgba(255,255,255,0.1); padding-top:6px;">
        <div style="font-size:10px; color:#64748b; margin-bottom:2px;">LOG AKTIVITAS:</div>
        <div style="font-family:monospace; font-size:10px; color:#cbd5e1; max-height:60px; overflow-y:auto;">
          ${tpuState.logs.length === 0 ? "<span style='color:#64748b;'>Belum ada aktivitas</span>" : tpuState.logs.map(l => `<div>${l}</div>`).join("")}
        </div>
      </div>
    `;

    // Pasang Event Tombol
    const btnAuto = tpuHudContainer.querySelector("#ks-btn-auto-geledah");
    if (btnAuto) {
      btnAuto.onclick = () => {
        tpuState.autoGeledah = !tpuState.autoGeledah;
        if (tpuState.autoGeledah) {
          tpuState.phase = "IDLE";
          addLog("▶ Auto-geledah dimulai");
        } else {
          stopNavigation();
          addLog("⏹ Auto-geledah dihentikan manual");
        }
        updateTpuHud();
      };
    }

    const btnReset = tpuHudContainer.querySelector("#ks-btn-reset-tpu");
    if (btnReset) {
      btnReset.onclick = () => {
        tpuState.sudahDigeledah.clear();
        tpuState.currentTargetId = null;
        tpuState.phase = "IDLE";
        addLog("🔄 Status 12 benda di-reset");
        updateTpuHud();
      };
    }
  }

  // Kontrol Gerak Karakter TPU
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

  // Engine Auto-Geledah Loop (dijalankan di browser)
  if (typeof window !== "undefined") {
    setInterval(() => {
      // Sync apakah TPU sedang terbuka
      const jelajahEl = document.querySelector('[data-testid="jelajah-tpu"]');
      if (!jelajahEl) {
        if (tpuState.autoGeledah) {
          tpuState.autoGeledah = false;
          stopNavigation();
        }
        updateTpuHud();
        return;
      }

      // Deteksi jika benda saat ini sudah digeledah menurut game
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
            addLog("🎉 PUSAKA DITEMUKAN! Membawa ke tas...");
          } else {
            addLog(`Hasil geledah selesai: Kosong`);
          }
          if (tpuState.currentTargetId) {
            tpuState.sudahDigeledah.add(tpuState.currentTargetId);
          }
          tutupBtn.click();
          tpuState.phase = "IDLE";
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
      if (now - tpuState.lastActionTime < 350) return;

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
        addLog(`🎯 Target berikutnya: ${targetBenda.nama}`);
        tpuState.phase = "NAVIGATING";
        tpuState.lastActionTime = now;
        return;
      }

      // 2. Fase NAVIGATING: Bergerak menuju target
      if (tpuState.phase === "NAVIGATING") {
        const target = BENDA_TPU.find(b => b.id === tpuState.currentTargetId);
        if (!target) {
          tpuState.phase = "IDLE";
          return;
        }

        const dist = distanceToBox(px, py, target.kotak);
        const btnGeledah = document.querySelector('[data-testid="tpu-geledah-btn"]');
        if (dist <= 1.15 || (btnGeledah && !btnGeledah.disabled)) {
          stopNavigation();
          tpuState.phase = "SEARCHING";
          addLog(`🔍 Tiba di ${target.nama}. Memulai geledah...`);

          if (btnGeledah) {
            btnGeledah.click();
          } else {
            window.dispatchEvent(new CustomEvent("ks_tpu_geledah", {
              detail: { id: target.id }
            }));
          }
          tpuState.lastActionTime = now;
          return;
        }

        const dx = target.x - px;
        const dy = target.y - py;
        const targetAngle = Math.atan2(dx, dy);

        let angleDiff = targetAngle - tpuState.playerYaw;
        while (angleDiff > Math.PI) angleDiff -= 2 * Math.PI;
        while (angleDiff < -Math.PI) angleDiff += 2 * Math.PI;

        let turn = 0;
        if (angleDiff > 0.15) turn = -1;
        else if (angleDiff < -0.15) turn = 1;

        sendStick(turn, 1);
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
    tpuState
  };
});
