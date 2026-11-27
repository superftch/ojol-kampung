// KampungSebelah - Berburu Radar & Sniper Pro (v2.4.0)
// Fitur: Radar Satwa Live + Line-of-Sight Pohon, Auto-Bidik Balistik (Gravitasi + Angin),
// Auto-Tembak Aman, Auto-Ambil, Proteksi Seruduk, & Estimator Cuan.

(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  if (typeof globalThis !== "undefined") {
    globalThis.__KS_BERBURU_MODULE = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const SATWA_ECONOMY = {
    "babi-hutan": { nama: "Babi hutan", icon: "🐗", jualKoin: 8.0, porsi: 3, kategori: "besar", prioritas: 1 },
    "ayam-hutan": { nama: "Ayam hutan", icon: "🐔", jualKoin: 2.5, porsi: 2, kategori: "sedang", prioritas: 2 },
    "tupai-kelapa": { nama: "Tupai kelapa", icon: "🐿️", jualKoin: 0.8, porsi: 0, kategori: "hama", prioritas: 3 },
    "tikus-sawah": { nama: "Tikus sawah", icon: "🐀", jualKoin: 0.6, porsi: 0, kategori: "hama", prioritas: 4 }
  };

  const BERBURU_ECONOMY = {
    senapanKoin: 50,
    izinKoin: 5,
    izinMenit: 60,
    peluruIsi: 10,
    peluruKoin: 1,
    kuotaHarianWarga: 5,
    kuotaBabiPerHutan: 3
  };

  const HUNTING_PLAN_PRESETS = {
    "max-cuan": {
      id: "max-cuan",
      label: "🔥 Max Cuan",
      babi: 3,
      ayam: 2,
      tupai: 0,
      tikus: 0,
      pakaiIzin: true,
      peluruPerSatwa: 1,
      beliSenapan: false
    },
    "babi-only": {
      id: "babi-only",
      label: "🐗 3 Babi",
      babi: 3,
      ayam: 0,
      tupai: 0,
      tikus: 0,
      pakaiIzin: true,
      peluruPerSatwa: 1,
      beliSenapan: false
    },
    "ayam-only": {
      id: "ayam-only",
      label: "🐔 5 Ayam",
      babi: 0,
      ayam: 5,
      tupai: 0,
      tikus: 0,
      pakaiIzin: true,
      peluruPerSatwa: 1,
      beliSenapan: false
    },
    "latihan": {
      id: "latihan",
      label: "🎯 Latihan",
      babi: 3,
      ayam: 2,
      tupai: 0,
      tikus: 0,
      pakaiIzin: false,
      peluruPerSatwa: 1,
      beliSenapan: false
    }
  };

  function toNonNegInt(val) {
    const n = Math.floor(Number(val));
    return Number.isFinite(n) && n > 0 ? n : 0;
  }

  function roundKoin(val) {
    return Math.round(val * 100) / 100;
  }

  function evaluateBagProfit(buruanList = [], peluruDipakai = 0, pakaiIzin = true) {
    let omzetKoin = 0;
    let totalPorsi = 0;
    const counts = { "babi-hutan": 0, "ayam-hutan": 0, "tupai-kelapa": 0, "tikus-sawah": 0 };

    for (const item of buruanList) {
      const jenis = typeof item === "string" ? item : item?.jenis;
      const eco = SATWA_ECONOMY[jenis];
      if (!eco) continue;
      omzetKoin += eco.jualKoin;
      totalPorsi += eco.porsi;
      counts[jenis] = (counts[jenis] || 0) + 1;
    }

    const biayaIzin = pakaiIzin ? BERBURU_ECONOMY.izinKoin : 0;
    const biayaPeluru = (peluruDipakai / BERBURU_ECONOMY.peluruIsi) * BERBURU_ECONOMY.peluruKoin;
    const netProfit = roundKoin(omzetKoin - biayaIzin - biayaPeluru);

    return {
      jumlah: buruanList.length,
      omzetKoin: roundKoin(omzetKoin),
      biayaIzin,
      biayaPeluru: roundKoin(biayaPeluru),
      netProfit,
      totalPorsi,
      counts
    };
  }

  function planHunting(planInput = {}) {
    const babi = toNonNegInt(planInput.babi);
    const ayam = toNonNegInt(planInput.ayam);
    const tupai = toNonNegInt(planInput.tupai);
    const tikus = toNonNegInt(planInput.tikus);
    const pakaiIzin = planInput.pakaiIzin !== false;
    const beliSenapan = Boolean(planInput.beliSenapan);
    const rawPeluruPerSatwa = Number(planInput.peluruPerSatwa);
    const peluruPerSatwa = Number.isFinite(rawPeluruPerSatwa) && rawPeluruPerSatwa > 0 ? rawPeluruPerSatwa : 1;

    const buruanList = [
      ...Array(babi).fill("babi-hutan"),
      ...Array(ayam).fill("ayam-hutan"),
      ...Array(tupai).fill("tupai-kelapa"),
      ...Array(tikus).fill("tikus-sawah")
    ];

    const totalTarget = buruanList.length;
    const estimasiPeluru = planInput.peluruDipakai != null
      ? toNonNegInt(planInput.peluruDipakai)
      : Math.ceil(totalTarget * peluruPerSatwa);

    const bagEval = evaluateBagProfit(buruanList, estimasiPeluru, pakaiIzin);
    const biayaSenapan = beliSenapan ? BERBURU_ECONOMY.senapanKoin : 0;
    const totalBiaya = roundKoin(bagEval.biayaIzin + bagEval.biayaPeluru + biayaSenapan);
    const netProfit = roundKoin(bagEval.omzetKoin - totalBiaya);
    const roiPersen = totalBiaya > 0
      ? Math.round((netProfit / totalBiaya) * 100)
      : (bagEval.omzetKoin > 0 ? 100 : 0);
    const packPeluru = estimasiPeluru > 0 ? Math.ceil(estimasiPeluru / BERBURU_ECONOMY.peluruIsi) : 0;

    let recommendedFilter = "high-roi";
    if (babi > 0 && ayam === 0 && tupai === 0 && tikus === 0) {
      recommendedFilter = "babi";
    } else if (ayam > 0 && babi === 0 && tupai === 0 && tikus === 0) {
      recommendedFilter = "ayam";
    } else if ((babi > 0 || ayam > 0) && tupai === 0 && tikus === 0) {
      recommendedFilter = "high-roi";
    } else if ((tupai > 0 || tikus > 0) && babi === 0 && ayam === 0) {
      recommendedFilter = "hama";
    } else if (totalTarget > 0) {
      recommendedFilter = "all";
    }

    const warnings = [];
    const melebihiKuotaBabi = babi > BERBURU_ECONOMY.kuotaBabiPerHutan;
    const melebihiKuotaHarian = totalTarget > BERBURU_ECONOMY.kuotaHarianWarga;
    if (totalTarget === 0) {
      warnings.push("Pilih minimal 1 satwa target.");
    }
    if (melebihiKuotaBabi) {
      warnings.push(`Maksimal ${BERBURU_ECONOMY.kuotaBabiPerHutan} Babi per hutan.`);
    }
    if (melebihiKuotaHarian) {
      warnings.push(`Total ${totalTarget} melebihi kuota harian (${BERBURU_ECONOMY.kuotaHarianWarga}).`);
    }
    if (totalTarget > 0 && netProfit < 0) {
      warnings.push("Estimasi rugi! Tambah Babi/Ayam atau matikan izin untuk latihan.");
    }

    const statusLabel = netProfit > 0 ? "UNTUNG" : netProfit < 0 ? "RUGI" : "IMPAS";

    return {
      targets: { babi, ayam, tupai, tikus },
      totalTarget,
      pakaiIzin,
      beliSenapan,
      peluruPerSatwa,
      estimasiPeluru,
      packPeluru,
      omzetKoin: bagEval.omzetKoin,
      biayaIzin: bagEval.biayaIzin,
      biayaPeluru: bagEval.biayaPeluru,
      biayaSenapan,
      totalBiaya,
      netProfit,
      roiPersen,
      totalPorsi: bagEval.totalPorsi,
      recommendedFilter,
      melebihiKuotaBabi,
      melebihiKuotaHarian,
      warnings,
      statusLabel
    };
  }

  function computeRelativeDirection(relAngleRad) {
    const deg = Math.round((relAngleRad * 180) / Math.PI);
    const absDeg = Math.abs(deg);
    if (absDeg <= 12) return "⬆ Depan";
    if (absDeg >= 165) return "⬇ Belakang";
    if (deg > 0) return `⬅ Kiri ${absDeg}°`;
    return `➡ Kanan ${absDeg}°`;
  }

  function filterAnimals(animals = [], filterMode = "high-roi") {
    return animals.filter((a) => {
      if (!a) return false;
      if (filterMode === "all") return true;
      if (filterMode === "high-roi") return a.jenis === "babi-hutan" || a.jenis === "ayam-hutan";
      if (filterMode === "babi") return a.jenis === "babi-hutan";
      if (filterMode === "ayam") return a.jenis === "ayam-hutan";
      if (filterMode === "hama") return a.jenis === "tupai-kelapa" || a.jenis === "tikus-sawah";
      return true;
    });
  }

  function selectBestTarget(animals = [], filterMode = "high-roi") {
    const filtered = filterAnimals(animals, filterMode).filter((a) => a.hidup);
    if (filtered.length === 0) return null;

    const sorted = [...filtered].sort((a, b) => {
      // 1. Prioritize charging boar immediately for safety
      if (a.keadaan === "seruduk" && b.keadaan !== "seruduk") return -1;
      if (b.keadaan === "seruduk" && a.keadaan !== "seruduk") return 1;

      // 2. Prioritize clear line-of-sight & lethal energy
      const aReady = a.los && a.energiSampai >= (a.energiKepala || 0.3) ? 1 : 0;
      const bReady = b.los && b.energiSampai >= (b.energiKepala || 0.3) ? 1 : 0;
      if (aReady !== bReady) return bReady - aReady;

      // 3. Prioritize higher value (babi > ayam > tupai > tikus), then closer distance
      const aEco = SATWA_ECONOMY[a.jenis]?.prioritas ?? 9;
      const bEco = SATWA_ECONOMY[b.jenis]?.prioritas ?? 9;
      if (aEco !== bEco) return aEco - bEco;

      return (a.dist ?? 999) - (b.dist ?? 999);
    });

    return sorted[0];
  }

  function canAutoShoot(snapshot, target) {
    if (!snapshot?.ready || !snapshot.state || !target || !target.hidup) return false;
    const st = snapshot.state;
    if (st.jatuh || st.kokang != null || (st.peluru || 0) <= 0) return false;
    if (!st.teropong || (st.bidik || 0) < 0.96 || (snapshot.me?.v || 0) > 0.08) return false;
    if (!target.los) return false;
    if (target.keadaan === "kabur" && (target.dist || 999) > 16) return false;
    if ((target.energiSampai || 0) < (target.energiKepala || 0.3)) return false;
    return true;
  }

  function clampHudPos(x, y, width, height, winW, winH) {
    const margin = 8;
    const maxX = Math.max(margin, winW - width - margin);
    const maxY = Math.max(margin, winH - height - margin);
    return {
      x: Math.min(maxX, Math.max(margin, x)),
      y: Math.min(maxY, Math.max(margin, y))
    };
  }

  function decideAutoHuntAction(snap, filterMode = "high-roi") {
    if (!snap?.ready || !snap.state) {
      return { type: "idle", reason: "Menunggu hutan 3D..." };
    }
    const st = snap.state;
    if (st.jatuh) {
      return { type: "idle", reason: "🤕 Terjatuh, menunggu pulih..." };
    }

    // 1. Dodge charging boar nearby
    const charging = (snap.animals || []).find((a) => a.keadaan === "seruduk" && a.dist < 14);
    if (charging) {
      return { type: "dodge", target: charging, reason: `⚠️ Menghindar seruduk (${charging.dist}m)` };
    }

    // 2. Loot immediately if prompt is active
    if (st.ambil) {
      return { type: "ambil", target: st.ambil, reason: `📦 Mengambil ${st.ambil.nama || "buruan"}...` };
    }

    const targetAnimals = filterAnimals(snap.animals || [], filterMode);
    const anyTargetLivingNear = targetAnimals.some((a) => a.hidup && a.dist < 58);

    // 3. Walk to nearest dead animal (sprint if far & no target living animal near; crouch if target near)
    const corpses = (snap.animals || []).filter((a) => !a.hidup).sort((a, b) => a.dist - b.dist);
    if (corpses.length > 0) {
      const c = corpses[0];
      const canRun = !anyTargetLivingNear && c.dist > 60;
      const shouldCrouch = anyTargetLivingNear || c.dist < 50;
      return {
        type: "walk",
        target: c,
        walkOpts: { x: c.x, z: c.z, stopRadius: 1.6, crouch: shouldCrouch, run: canRun },
        reason: `📦 Menuju bangkai ${c.nama} (${c.dist}m)`
      };
    }

    // 4. Select best living target
    const target = selectBestTarget(snap.animals || [], filterMode);
    if (!target) {
      return { type: "idle", reason: "🔍 Tidak ada satwa pada filter ini" };
    }

    const maxShootDist = target.jenis === "babi-hutan" ? 32 : 25;
    const notFleeingFar = target.keadaan !== "kabur" || target.dist <= 16;
    const lethalReady = target.los && (target.energiSampai || 0) >= (target.energiKepala || 0.3);
    if (lethalReady && notFleeingFar && target.dist <= maxShootDist) {
      return {
        type: "aim_shoot",
        target,
        reason: `🎯 Membidik ${target.nama} (${target.dist}m)`
      };
    }

    // 5. Walk closer to target: sprint when far (>60m & no target near), crouch quietly when <58m
    const canRun = !anyTargetLivingNear && target.dist > 60;
    const shouldCrouch = anyTargetLivingNear || target.dist < 58;
    return {
      type: "walk",
      target,
      walkOpts: {
        x: target.x,
        z: target.z,
        stopRadius: 16,
        crouch: shouldCrouch,
        run: canRun
      },
      reason: `${canRun ? "🏃 Lari" : shouldCrouch ? "🧎 Mengendap" : "🚶 Mendekati"} ${target.nama} (${target.dist}m)`
    };
  }

  // --- Browser Runtime ---
  if (typeof window !== "undefined" && typeof document !== "undefined" && window.location?.pathname?.startsWith("/berburu")) {
    console.log("[BerburuRadar] Content script v2.4.0 active on /berburu");

    function injectMainWorld() {
      try {
        const s = document.createElement("script");
        s.src = chrome.runtime.getURL("berburu-inject.js");
        s.onload = function () {
          this.remove();
        };
        (document.head || document.documentElement).appendChild(s);
      } catch (e) {
        console.warn("[BerburuRadar] Failed to inject berburu-inject.js:", e);
      }
    }
    injectMainWorld();

    const HUD_POS_KEY = "ks_berburu_hud_pos";
    const PLAN_STORAGE_KEY = "ks_berburu_plan";

    function loadSavedPlan() {
      try {
        const raw = JSON.parse(localStorage.getItem(PLAN_STORAGE_KEY) || "null");
        if (raw && typeof raw === "object") {
          return {
            babi: toNonNegInt(raw.babi ?? 3),
            ayam: toNonNegInt(raw.ayam ?? 2),
            tupai: toNonNegInt(raw.tupai ?? 0),
            tikus: toNonNegInt(raw.tikus ?? 0),
            pakaiIzin: raw.pakaiIzin !== false,
            peluruPerSatwa: Number(raw.peluruPerSatwa) > 0 ? Number(raw.peluruPerSatwa) : 1,
            beliSenapan: Boolean(raw.beliSenapan)
          };
        }
      } catch {}
      return { ...HUNTING_PLAN_PRESETS["max-cuan"] };
    }

    const initialPlanDraft = loadSavedPlan();
    const uiState = {
      filter: planHunting(initialPlanDraft).recommendedFilter || "babi",
      autoHunt: false,
      autoAim: false,
      autoShoot: false,
      autoAmbil: true,
      antiSeruduk: true,
      esp2d: false,
      chams3d: false,
      minimized: false,
      planOpen: true,
      planDraft: initialPlanDraft,
      appliedPlan: planHunting(initialPlanDraft),
      lockedId: null,
      lastShotAt: 0,
      lastAmbilAt: 0,
      ambilCooldownUntil: 0,
      lastDodgeAt: 0,
      autoStatus: "",
      snapshot: null
    };

    function sendCmd(detail) {
      window.dispatchEvent(new CustomEvent("ks_berburu_cmd", { detail }));
    }

    function clickTestId(testId) {
      const btn = document.querySelector(`[data-testid="${testId}"]`);
      if (btn && !btn.disabled) {
        btn.click();
        return true;
      }
      return false;
    }

    function createHud() {
      if (document.getElementById("ks-berburu-hud")) return;

      const hud = document.createElement("div");
      hud.id = "ks-berburu-hud";
      hud.style.cssText = [
        "position:fixed",
        "top:16px",
        "right:16px",
        "width:320px",
        "max-height:85vh",
        "overflow-y:auto",
        "z-index:2147483640",
        "background:rgba(12,18,32,0.88)",
        "backdrop-filter:blur(12px)",
        "-webkit-backdrop-filter:blur(12px)",
        "border:1px solid rgba(74,222,128,0.35)",
        "border-radius:12px",
        "color:#e2e8f0",
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif",
        "font-size:12px",
        "box-shadow:0 12px 32px rgba(0,0,0,0.45)",
        "user-select:none"
      ].join(";");

      try {
        const saved = JSON.parse(localStorage.getItem(HUD_POS_KEY) || "null");
        if (saved && typeof saved.x === "number" && typeof saved.y === "number") {
          const clamped = clampHudPos(saved.x, saved.y, 320, 420, window.innerWidth, window.innerHeight);
          hud.style.left = `${clamped.x}px`;
          hud.style.top = `${clamped.y}px`;
          hud.style.right = "auto";
        }
      } catch {}

      hud.innerHTML = `
        <div id="ks-berburu-hdr" style="display:flex;align-items:center;justify-content:space-between;padding:9px 12px;background:rgba(22,101,52,0.45);border-bottom:1px solid rgba(74,222,128,0.25);cursor:grab;border-radius:12px 12px 0 0;">
          <span style="font-weight:700;color:#4ade80;font-size:13px;">🎯 Berburu Radar & Sniper</span>
          <div style="display:flex;gap:6px;align-items:center;">
            <button id="ks-berburu-min" style="background:rgba(255,255,255,0.12);border:none;color:#e2e8f0;border-radius:5px;padding:2px 7px;cursor:pointer;font-size:11px;">—</button>
          </div>
        </div>
        <div id="ks-berburu-body" style="padding:10px 12px;display:flex;flex-direction:column;gap:8px;">
          <div id="ks-berburu-alert" style="display:none;background:rgba(220,38,38,0.85);color:#fff;padding:6px 8px;border-radius:6px;font-weight:700;text-align:center;"></div>
          <div style="display:flex;align-items:center;gap:10px;background:rgba(255,255,255,0.04);border:1px solid rgba(74,222,128,0.2);border-radius:10px;padding:7px;">
            <canvas id="ks-berburu-radar" width="116" height="116" style="flex-shrink:0;border-radius:50%;background:#06111a;border:1px solid rgba(74,222,128,0.35);"></canvas>
            <div style="flex:1;min-width:0;display:flex;flex-direction:column;gap:4px;font-size:11px;">
              <div id="ks-berburu-stats" style="display:grid;grid-template-columns:1fr 1fr;gap:3px 6px;color:#cbd5e1;">
                <span style="grid-column:span 2;">Menunggu hutan 3D...</span>
              </div>
              <div id="ks-berburu-compass" style="font-size:10px;color:#38bdf8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">🧭 Radar siap</div>
              <div id="ks-berburu-autostatus" style="font-size:10px;color:#4ade80;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">Mode: Manual</div>
            </div>
          </div>
          <div style="background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.25);border-radius:8px;padding:6px 8px;font-size:11px;line-height:1.4;color:#a7f3d0;">
            <b>💰 Cuan Resmi:</b> Babi <b>8k</b> (3 porsi) · Ayam <b>2.5k</b> (2 porsi) · Tupai <b>0.8k</b> · Tikus <b>0.6k</b>
          </div>
          <div style="background:rgba(15,23,42,0.72);border:1px solid rgba(56,189,248,0.3);border-radius:8px;overflow:hidden;">
            <button id="ks-bb-plan-toggle" style="width:100%;display:flex;align-items:center;justify-content:space-between;padding:6px 8px;background:rgba(2,132,199,0.18);border:none;color:#bae6fd;cursor:pointer;font-size:11px;font-weight:700;">
              <span>📋 Rencana &amp; Estimasi Profit</span>
              <span id="ks-bb-plan-badge" style="color:#4ade80;">+23.5k</span>
            </button>
            <div id="ks-bb-plan-body" style="padding:8px;display:flex;flex-direction:column;gap:6px;border-top:1px solid rgba(56,189,248,0.2);">
              <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:4px;">
                ${Object.values(HUNTING_PLAN_PRESETS).map((p) => `<button class="ks-bb-preset" data-preset="${p.id}" style="padding:3px 4px;border-radius:5px;border:1px solid rgba(255,255,255,0.15);background:rgba(255,255,255,0.06);color:#e2e8f0;cursor:pointer;font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${p.label}</button>`).join("")}
              </div>
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:5px;font-size:11px;">
                <label style="display:flex;align-items:center;justify-content:space-between;background:rgba(255,255,255,0.04);padding:3px 6px;border-radius:5px;">
                  <span>🐗 Babi</span>
                  <input id="ks-bb-plan-babi" type="number" min="0" max="5" value="${uiState.planDraft.babi}" style="width:38px;background:#0f172a;color:#fff;border:1px solid rgba(255,255,255,0.2);border-radius:4px;padding:1px 4px;text-align:center;font-size:11px;">
                </label>
                <label style="display:flex;align-items:center;justify-content:space-between;background:rgba(255,255,255,0.04);padding:3px 6px;border-radius:5px;">
                  <span>🐔 Ayam</span>
                  <input id="ks-bb-plan-ayam" type="number" min="0" max="5" value="${uiState.planDraft.ayam}" style="width:38px;background:#0f172a;color:#fff;border:1px solid rgba(255,255,255,0.2);border-radius:4px;padding:1px 4px;text-align:center;font-size:11px;">
                </label>
                <label style="display:flex;align-items:center;justify-content:space-between;background:rgba(255,255,255,0.04);padding:3px 6px;border-radius:5px;">
                  <span>🐿️ Tupai</span>
                  <input id="ks-bb-plan-tupai" type="number" min="0" max="5" value="${uiState.planDraft.tupai}" style="width:38px;background:#0f172a;color:#fff;border:1px solid rgba(255,255,255,0.2);border-radius:4px;padding:1px 4px;text-align:center;font-size:11px;">
                </label>
                <label style="display:flex;align-items:center;justify-content:space-between;background:rgba(255,255,255,0.04);padding:3px 6px;border-radius:5px;">
                  <span>🐀 Tikus</span>
                  <input id="ks-bb-plan-tikus" type="number" min="0" max="5" value="${uiState.planDraft.tikus}" style="width:38px;background:#0f172a;color:#fff;border:1px solid rgba(255,255,255,0.2);border-radius:4px;padding:1px 4px;text-align:center;font-size:11px;">
                </label>
              </div>
              <div style="display:flex;align-items:center;justify-content:space-between;gap:6px;font-size:10px;color:#cbd5e1;">
                <label style="display:flex;align-items:center;gap:4px;cursor:pointer;">
                  <input id="ks-bb-plan-izin" type="checkbox" ${uiState.planDraft.pakaiIzin ? "checked" : ""}>
                  <span>Izin Hutan (5k)</span>
                </label>
                <label style="display:flex;align-items:center;gap:4px;">
                  <span>Peluru/ekor:</span>
                  <select id="ks-bb-plan-peluru" style="background:#0f172a;color:#fff;border:1px solid rgba(255,255,255,0.2);border-radius:4px;padding:1px 3px;font-size:10px;">
                    <option value="1" ${uiState.planDraft.peluruPerSatwa === 1 ? "selected" : ""}>1x (Tepat)</option>
                    <option value="1.5" ${uiState.planDraft.peluruPerSatwa === 1.5 ? "selected" : ""}>1.5x (Aman)</option>
                    <option value="2" ${uiState.planDraft.peluruPerSatwa === 2 ? "selected" : ""}>2x (Cadangan)</option>
                  </select>
                </label>
              </div>
              <div id="ks-bb-plan-summary" style="background:rgba(255,255,255,0.04);border-radius:6px;padding:6px 8px;font-size:11px;line-height:1.45;"></div>
              <button id="ks-bb-plan-apply" style="width:100%;padding:5px;border-radius:6px;border:1px solid rgba(56,189,248,0.5);background:#0284c7;color:#fff;cursor:pointer;font-weight:700;font-size:11px;">✅ Terapkan Rencana &amp; Filter</button>
            </div>
          </div>
          <div style="display:flex;gap:4px;flex-wrap:wrap;">
            <button class="ks-bb-flt" data-flt="babi" style="flex:1;padding:4px 6px;border-radius:6px;border:1px solid rgba(74,222,128,0.5);background:#166534;color:#fff;cursor:pointer;font-size:11px;font-weight:600;">🐗 Babi</button>
            <button class="ks-bb-flt" data-flt="high-roi" style="padding:4px 6px;border-radius:6px;border:1px solid rgba(255,255,255,0.15);background:rgba(255,255,255,0.06);color:#cbd5e1;cursor:pointer;font-size:11px;">🔥 Babi+Ayam</button>
            <button class="ks-bb-flt" data-flt="ayam" style="padding:4px 6px;border-radius:6px;border:1px solid rgba(255,255,255,0.15);background:rgba(255,255,255,0.06);color:#cbd5e1;cursor:pointer;font-size:11px;">🐔 Ayam</button>
            <button class="ks-bb-flt" data-flt="all" style="padding:4px 6px;border-radius:6px;border:1px solid rgba(255,255,255,0.15);background:rgba(255,255,255,0.06);color:#cbd5e1;cursor:pointer;font-size:11px;">Semua</button>
          </div>
          <button id="ks-bb-autohunt" style="width:100%;padding:7px;border-radius:7px;border:1px solid rgba(74,222,128,0.5);background:rgba(22,101,52,0.35);color:#bbf7d0;cursor:pointer;font-weight:700;font-size:12px;">🤖 Auto-Jalan & Buru: OFF</button>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">
            <button id="ks-bb-autoaim" style="padding:6px;border-radius:7px;border:1px solid rgba(56,189,248,0.4);background:rgba(2,132,199,0.2);color:#bae6fd;cursor:pointer;font-weight:600;font-size:11px;">🎯 Auto-Bidik: OFF</button>
            <button id="ks-bb-autoshoot" style="padding:6px;border-radius:7px;border:1px solid rgba(248,113,113,0.4);background:rgba(185,28,28,0.2);color:#fecaca;cursor:pointer;font-weight:600;font-size:11px;">🔫 Auto-Tembak: OFF</button>
            <button id="ks-bb-autoambil" style="padding:6px;border-radius:7px;border:1px solid rgba(74,222,128,0.4);background:rgba(22,101,52,0.45);color:#bbf7d0;cursor:pointer;font-weight:600;font-size:11px;">📦 Auto-Ambil: ON</button>
            <button id="ks-bb-stopwalk" style="padding:6px;border-radius:7px;border:1px solid rgba(255,255,255,0.15);background:rgba(255,255,255,0.08);color:#e2e8f0;cursor:pointer;font-weight:600;font-size:11px;">⏹ Stop Jalan</button>
            <button id="ks-bb-esp2d" style="padding:6px;border-radius:7px;border:1px solid rgba(192,132,252,0.4);background:rgba(126,34,206,0.18);color:#e9d5ff;cursor:pointer;font-weight:600;font-size:11px;">👁️ ESP 2D: OFF</button>
            <button id="ks-bb-chams3d" style="padding:6px;border-radius:7px;border:1px solid rgba(250,204,21,0.4);background:rgba(161,98,7,0.18);color:#fef08a;cursor:pointer;font-weight:600;font-size:11px;">🩻 Chams 3D: OFF</button>
          </div>
          <div id="ks-berburu-list" style="display:flex;flex-direction:column;gap:5px;max-height:240px;overflow-y:auto;"></div>
        </div>
      `;

      document.body.appendChild(hud);

      // Drag & Drop support
      const hdr = hud.querySelector("#ks-berburu-hdr");
      let dragging = false;
      let startX = 0, startY = 0, origX = 0, origY = 0;

      hdr.addEventListener("pointerdown", (e) => {
        if (e.target.closest("button")) return;
        dragging = true;
        hdr.style.cursor = "grabbing";
        const rect = hud.getBoundingClientRect();
        startX = e.clientX;
        startY = e.clientY;
        origX = rect.left;
        origY = rect.top;
        hdr.setPointerCapture(e.pointerId);
      });
      hdr.addEventListener("pointermove", (e) => {
        if (!dragging) return;
        const clamped = clampHudPos(
          origX + (e.clientX - startX),
          origY + (e.clientY - startY),
          hud.offsetWidth,
          hud.offsetHeight,
          window.innerWidth,
          window.innerHeight
        );
        hud.style.left = `${clamped.x}px`;
        hud.style.top = `${clamped.y}px`;
        hud.style.right = "auto";
      });
      hdr.addEventListener("pointerup", () => {
        if (!dragging) return;
        dragging = false;
        hdr.style.cursor = "grab";
        const rect = hud.getBoundingClientRect();
        try {
          localStorage.setItem(HUD_POS_KEY, JSON.stringify({ x: rect.left, y: rect.top }));
        } catch {}
      });
      hdr.addEventListener("dblclick", () => {
        hud.style.left = "auto";
        hud.style.right = "16px";
        hud.style.top = "16px";
        try { localStorage.removeItem(HUD_POS_KEY); } catch {}
      });

      // Controls
      hud.querySelector("#ks-berburu-min").addEventListener("click", () => {
        uiState.minimized = !uiState.minimized;
        hud.querySelector("#ks-berburu-body").style.display = uiState.minimized ? "none" : "flex";
      });

      function syncFilterButtons() {
        hud.querySelectorAll(".ks-bb-flt").forEach((b) => {
          const active = b.dataset.flt === uiState.filter;
          b.style.background = active ? "#166534" : "rgba(255,255,255,0.06)";
          b.style.color = active ? "#fff" : "#cbd5e1";
          b.style.borderColor = active ? "rgba(74,222,128,0.5)" : "rgba(255,255,255,0.15)";
        });
      }

      function readPlanInputs() {
        uiState.planDraft = {
          babi: toNonNegInt(hud.querySelector("#ks-bb-plan-babi")?.value),
          ayam: toNonNegInt(hud.querySelector("#ks-bb-plan-ayam")?.value),
          tupai: toNonNegInt(hud.querySelector("#ks-bb-plan-tupai")?.value),
          tikus: toNonNegInt(hud.querySelector("#ks-bb-plan-tikus")?.value),
          pakaiIzin: Boolean(hud.querySelector("#ks-bb-plan-izin")?.checked),
          peluruPerSatwa: Number(hud.querySelector("#ks-bb-plan-peluru")?.value) || 1,
          beliSenapan: false
        };
      }

      function renderPlanPanel() {
        const plan = planHunting(uiState.planDraft);
        const badgeEl = hud.querySelector("#ks-bb-plan-badge");
        const summaryEl = hud.querySelector("#ks-bb-plan-summary");
        const sign = plan.netProfit > 0 ? "+" : "";
        const profitColor = plan.netProfit > 0 ? "#4ade80" : plan.netProfit < 0 ? "#f87171" : "#facc15";
        if (badgeEl) {
          badgeEl.textContent = `${sign}${plan.netProfit}k`;
          badgeEl.style.color = profitColor;
        }
        if (summaryEl) {
          const warnHtml = plan.warnings.length > 0
            ? `<div style="color:#fbbf24;font-size:10px;margin-top:3px;">⚠️ ${plan.warnings[0]}</div>`
            : "";
          summaryEl.innerHTML = `
            <div style="display:flex;justify-content:space-between;">
              <span>Target: <b>${plan.totalTarget}/${BERBURU_ECONOMY.kuotaHarianWarga}</b> (${plan.totalPorsi} porsi)</span>
              <span>Peluru: <b>${plan.estimasiPeluru}</b> (${plan.packPeluru} pack)</span>
            </div>
            <div style="display:flex;justify-content:space-between;">
              <span>Omzet: <b>${plan.omzetKoin}k</b></span>
              <span>Biaya: <b>${plan.totalBiaya}k</b> (Izin ${plan.biayaIzin}k + Plr ${plan.biayaPeluru}k)</span>
            </div>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-top:2px;padding-top:3px;border-top:1px solid rgba(255,255,255,0.08);">
              <span>Estimasi Profit:</span>
              <span style="font-weight:700;color:${profitColor};">${sign}${plan.netProfit}k (${plan.roiPersen}% ROI · ${plan.statusLabel})</span>
            </div>
            ${warnHtml}
          `;
        }
      }

      function writePlanInputs(draft) {
        const setVal = (sel, val) => {
          const el = hud.querySelector(sel);
          if (el) el.value = String(val);
        };
        setVal("#ks-bb-plan-babi", draft.babi);
        setVal("#ks-bb-plan-ayam", draft.ayam);
        setVal("#ks-bb-plan-tupai", draft.tupai);
        setVal("#ks-bb-plan-tikus", draft.tikus);
        const izinEl = hud.querySelector("#ks-bb-plan-izin");
        if (izinEl) izinEl.checked = Boolean(draft.pakaiIzin);
        setVal("#ks-bb-plan-peluru", draft.peluruPerSatwa);
      }

      hud.querySelector("#ks-bb-plan-toggle").addEventListener("click", () => {
        uiState.planOpen = !uiState.planOpen;
        hud.querySelector("#ks-bb-plan-body").style.display = uiState.planOpen ? "flex" : "none";
      });

      hud.querySelectorAll(".ks-bb-preset").forEach((btn) => {
        btn.addEventListener("click", () => {
          const preset = HUNTING_PLAN_PRESETS[btn.dataset.preset];
          if (!preset) return;
          uiState.planDraft = { ...preset };
          writePlanInputs(uiState.planDraft);
          renderPlanPanel();
        });
      });

      ["#ks-bb-plan-babi", "#ks-bb-plan-ayam", "#ks-bb-plan-tupai", "#ks-bb-plan-tikus", "#ks-bb-plan-izin", "#ks-bb-plan-peluru"].forEach((sel) => {
        hud.querySelector(sel)?.addEventListener("input", () => {
          readPlanInputs();
          renderPlanPanel();
        });
        hud.querySelector(sel)?.addEventListener("change", () => {
          readPlanInputs();
          renderPlanPanel();
        });
      });

      hud.querySelector("#ks-bb-plan-apply").addEventListener("click", () => {
        readPlanInputs();
        const plan = planHunting(uiState.planDraft);
        uiState.appliedPlan = plan;
        uiState.filter = plan.recommendedFilter;
        try {
          localStorage.setItem(PLAN_STORAGE_KEY, JSON.stringify(uiState.planDraft));
        } catch {}
        syncFilterButtons();
        sendCmd({ action: "setWallhack", filter: uiState.filter });
        const sign = plan.netProfit > 0 ? "+" : "";
        uiState.autoStatus = `📋 Rencana: ${plan.totalTarget} ekor (${sign}${plan.netProfit}k)`;
        renderPlanPanel();
        renderHud();
      });

      syncFilterButtons();
      renderPlanPanel();

      hud.querySelectorAll(".ks-bb-flt").forEach((btn) => {
        btn.addEventListener("click", () => {
          uiState.filter = btn.dataset.flt;
          syncFilterButtons();
          sendCmd({ action: "setWallhack", filter: uiState.filter });
          renderHud();
        });
      });

      const btnHunt = hud.querySelector("#ks-bb-autohunt");
      const btnAim = hud.querySelector("#ks-bb-autoaim");
      const btnShoot = hud.querySelector("#ks-bb-autoshoot");
      const btnAmbil = hud.querySelector("#ks-bb-autoambil");
      const btnStop = hud.querySelector("#ks-bb-stopwalk");
      const btnEsp2d = hud.querySelector("#ks-bb-esp2d");
      const btnChams3d = hud.querySelector("#ks-bb-chams3d");

      btnHunt.addEventListener("click", () => {
        uiState.autoHunt = !uiState.autoHunt;
        btnHunt.textContent = `🤖 Auto-Jalan & Buru: ${uiState.autoHunt ? "ON" : "OFF"}`;
        btnHunt.style.background = uiState.autoHunt ? "#16a34a" : "rgba(22,101,52,0.35)";
        btnHunt.style.color = uiState.autoHunt ? "#fff" : "#bbf7d0";
        if (!uiState.autoHunt) {
          sendCmd({ action: "stopWalk" });
          sendCmd({ action: "stopAim" });
          uiState.autoStatus = "Mode: Manual";
        }
      });

      btnAim.addEventListener("click", () => {
        uiState.autoAim = !uiState.autoAim;
        btnAim.textContent = `🎯 Auto-Bidik: ${uiState.autoAim ? "ON" : "OFF"}`;
        btnAim.style.background = uiState.autoAim ? "#0284c7" : "rgba(2,132,199,0.2)";
        if (!uiState.autoAim) {
          uiState.lockedId = null;
          sendCmd({ action: "stopAim" });
        }
      });

      btnShoot.addEventListener("click", () => {
        uiState.autoShoot = !uiState.autoShoot;
        btnShoot.textContent = `🔫 Auto-Tembak: ${uiState.autoShoot ? "ON" : "OFF"}`;
        btnShoot.style.background = uiState.autoShoot ? "#dc2626" : "rgba(185,28,28,0.2)";
      });

      btnAmbil.addEventListener("click", () => {
        uiState.autoAmbil = !uiState.autoAmbil;
        btnAmbil.textContent = `📦 Auto-Ambil: ${uiState.autoAmbil ? "ON" : "OFF"}`;
        btnAmbil.style.background = uiState.autoAmbil ? "rgba(22,101,52,0.45)" : "rgba(255,255,255,0.06)";
      });

      btnStop.addEventListener("click", () => {
        sendCmd({ action: "stopWalk" });
      });

      btnEsp2d.addEventListener("click", () => {
        uiState.esp2d = !uiState.esp2d;
        btnEsp2d.textContent = `👁️ ESP 2D: ${uiState.esp2d ? "ON" : "OFF"}`;
        btnEsp2d.style.background = uiState.esp2d ? "#7e22ce" : "rgba(126,34,206,0.18)";
        btnEsp2d.style.color = uiState.esp2d ? "#fff" : "#e9d5ff";
        sendCmd({ action: "setWallhack", esp2d: uiState.esp2d, chams3d: uiState.chams3d, filter: uiState.filter });
      });

      btnChams3d.addEventListener("click", () => {
        uiState.chams3d = !uiState.chams3d;
        btnChams3d.textContent = `🩻 Chams 3D: ${uiState.chams3d ? "ON" : "OFF"}`;
        btnChams3d.style.background = uiState.chams3d ? "#ca8a04" : "rgba(161,98,7,0.18)";
        btnChams3d.style.color = uiState.chams3d ? "#fff" : "#fef08a";
        sendCmd({ action: "setWallhack", esp2d: uiState.esp2d, chams3d: uiState.chams3d, filter: uiState.filter });
      });

      // Emergency manual override on movement keys
      window.addEventListener("keydown", (e) => {
        if (["w", "a", "s", "d"].includes(e.key.toLowerCase())) {
          if (uiState.autoHunt) {
            uiState.autoHunt = false;
            btnHunt.textContent = "🤖 Auto-Jalan & Buru: OFF";
            btnHunt.style.background = "rgba(22,101,52,0.35)";
            btnHunt.style.color = "#bbf7d0";
            uiState.autoStatus = "Dihentikan manual (WASD)";
          }
          sendCmd({ action: "stopWalk" });
        }
      });
    }

    function drawRadarCanvas(snap) {
      const canvas = document.getElementById("ks-berburu-radar");
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      const w = canvas.width;
      const h = canvas.height;
      const cx = w / 2;
      const cy = h / 2;
      const maxRange = 110;
      const rMax = w / 2 - 4;

      ctx.clearRect(0, 0, w, h);

      // Concentric radar rings
      ctx.strokeStyle = "rgba(74, 222, 128, 0.2)";
      ctx.lineWidth = 1;
      for (const frac of [0.33, 0.66, 1]) {
        ctx.beginPath();
        ctx.arc(cx, cy, rMax * frac, 0, Math.PI * 2);
        ctx.stroke();
      }
      // Crosshair lines
      ctx.beginPath();
      ctx.moveTo(cx, 4);
      ctx.lineTo(cx, h - 4);
      ctx.moveTo(4, cy);
      ctx.lineTo(w - 4, cy);
      ctx.stroke();

      // Player FOV cone (pointing UP)
      ctx.fillStyle = "rgba(74, 222, 128, 0.14)";
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, rMax, -Math.PI / 2 - 0.45, -Math.PI / 2 + 0.45);
      ctx.closePath();
      ctx.fill();

      // Player dot
      ctx.fillStyle = "#4ade80";
      ctx.beginPath();
      ctx.arc(cx, cy, 3, 0, Math.PI * 2);
      ctx.fill();

      if (!snap || !snap.ready || !Array.isArray(snap.animals)) return;

      const list = filterAnimals(snap.animals, uiState.filter);
      const corpses = snap.animals.filter((a) => !a.hidup);
      const allDots = [...list.filter((a) => a.hidup), ...corpses];

      for (const a of allDots) {
        const clampedDist = Math.min(maxRange, a.dist || 0);
        const r = (clampedDist / maxRange) * rMax;
        // relAngle > 0 means left of facing; in canvas UP is -PI/2, left is -PI/2 - relAngle
        const screenAngle = -Math.PI / 2 - (a.relAngle || 0);
        const px = cx + Math.cos(screenAngle) * r;
        const py = cy + Math.sin(screenAngle) * r;

        let color = "#94a3b8";
        if (!a.hidup) color = "#4ade80";
        else if (a.keadaan === "seruduk") color = "#ef4444";
        else if (a.jenis === "babi-hutan") color = "#c084fc";
        else if (a.jenis === "ayam-hutan") color = "#facc15";

        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(px, py, !a.hidup || a.jenis === "babi-hutan" ? 3.5 : 2.5, 0, Math.PI * 2);
        ctx.fill();

        if (uiState.lockedId === a.i) {
          ctx.strokeStyle = "#38bdf8";
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.arc(px, py, 6, 0, Math.PI * 2);
          ctx.stroke();
        }
      }
    }

    function renderHud() {
      const hud = document.getElementById("ks-berburu-hud");
      if (!hud) return;
      const snap = uiState.snapshot;
      const statsEl = hud.querySelector("#ks-berburu-stats");
      const compassEl = hud.querySelector("#ks-berburu-compass");
      const autoStatusEl = hud.querySelector("#ks-berburu-autostatus");
      const alertEl = hud.querySelector("#ks-berburu-alert");
      const listEl = hud.querySelector("#ks-berburu-list");

      drawRadarCanvas(snap);

      if (!snap || !snap.ready || !snap.state) {
        statsEl.innerHTML = `<span style="grid-column:span 2;">Masuk ke hutan buru (atau mode Latihan) untuk mengaktifkan radar.</span>`;
        if (compassEl) compassEl.textContent = "🧭 Radar menunggu hutan";
        if (autoStatusEl) autoStatusEl.textContent = uiState.autoStatus || "Mode: Menunggu";
        listEl.innerHTML = "";
        alertEl.style.display = "none";
        return;
      }

      const st = snap.state;
      const windSpeed = (snap.wind?.laju || 0).toFixed(1);
      const kokangTxt = st.kokang != null ? "⏳ Kokang" : (st.peluru > 0 ? "✅ Siap" : "❌ Habis");
      statsEl.innerHTML = `
        <div>🔫 <b>${st.peluru ?? 0}</b></div>
        <div>💨 <b>${windSpeed} m/s</b></div>
        <div>🧍 <b>${st.sikap || "-"}</b></div>
        <div>⚙️ <b>${kokangTxt}</b></div>
      `;

      const nearest = selectBestTarget(snap.animals, uiState.filter);
      if (compassEl) {
        compassEl.textContent = nearest
          ? `🧭 ${nearest.nama} (${nearest.dist}m) · ${computeRelativeDirection(nearest.relAngle || 0)}`
          : "🧭 Tidak ada satwa target";
      }
      if (autoStatusEl) {
        autoStatusEl.textContent = uiState.autoStatus || (uiState.autoHunt ? "🤖 Auto-Buru aktif" : "Mode: Manual");
      }

      const chargingBoar = snap.animals.find((a) => a.keadaan === "seruduk");
      if (chargingBoar) {
        alertEl.style.display = "block";
        alertEl.textContent = `⚠️ BABI MENYERUDUK (${chargingBoar.dist}m)! Menghindar ke samping!`;
      } else if (st.jatuh) {
        alertEl.style.display = "block";
        alertEl.textContent = "🤕 Terjatuh! Menunggu pulih...";
      } else {
        alertEl.style.display = "none";
      }

      // Show corpses first (to loot) + filtered living animals sorted by distance
      const corpses = snap.animals.filter((a) => !a.hidup);
      const living = filterAnimals(snap.animals, uiState.filter)
        .filter((a) => a.hidup)
        .sort((a, b) => a.dist - b.dist);
      const displayList = [...corpses, ...living].slice(0, 8);

      if (displayList.length === 0) {
        listEl.innerHTML = `<div style="text-align:center;color:#94a3b8;padding:8px;">Tidak ada satwa pada filter ini.</div>`;
        return;
      }

      listEl.innerHTML = displayList
        .map((a) => {
          const eco = SATWA_ECONOMY[a.jenis] || { icon: "🦌", jualKoin: 0 };
          const dir = computeRelativeDirection(a.relAngle || 0);
          const statusBadge = !a.hidup
            ? `<span style="color:#4ade80;font-weight:700;">💀 MATI</span>`
            : a.keadaan === "seruduk"
            ? `<span style="color:#f87171;font-weight:700;">⚠️ SERUDUK</span>`
            : a.keadaan === "kabur"
            ? `<span style="color:#fbbf24;">💨 Kabur</span>`
            : a.keadaan === "waspada"
            ? `<span style="color:#facc15;">👀 Waspada</span>`
            : `<span style="color:#94a3b8;">🌿 Tenang</span>`;

          const losIcon = !a.hidup
            ? "📦"
            : a.los
            ? (a.energiSampai >= a.energiKepala ? "🎯" : "⚠️ Jauh")
            : "🌲";

          return `
            <div style="display:flex;align-items:center;justify-content:space-between;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.08);border-radius:7px;padding:5px 7px;gap:6px;">
              <div style="min-width:0;flex:1;">
                <div style="font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                  ${eco.icon} ${a.nama} <span style="color:#4ade80;">(${eco.jualKoin}k)</span>
                </div>
                <div style="font-size:10px;color:#94a3b8;">
                  <b>${a.dist}m</b> · ${dir} · ${statusBadge} · ${losIcon}
                </div>
              </div>
              <div style="display:flex;gap:4px;flex-shrink:0;">
                ${a.hidup ? `<button class="ks-bb-aim-one" data-id="${a.i}" style="background:#0284c7;border:none;color:#fff;border-radius:5px;padding:4px 7px;cursor:pointer;font-size:11px;">🎯</button>` : ""}
                <button class="ks-bb-walk-one" data-x="${a.x}" data-z="${a.z}" data-dead="${!a.hidup}" style="background:#334155;border:none;color:#e2e8f0;border-radius:5px;padding:4px 7px;cursor:pointer;font-size:11px;">🚶</button>
              </div>
            </div>
          `;
        })
        .join("");

      listEl.querySelectorAll(".ks-bb-aim-one").forEach((btn) => {
        btn.addEventListener("click", () => {
          const id = Number(btn.dataset.id);
          uiState.lockedId = id;
          sendCmd({ action: "aim", satwaId: id, zona: "kepala", scope: true, breath: true });
        });
      });

      listEl.querySelectorAll(".ks-bb-walk-one").forEach((btn) => {
        btn.addEventListener("click", () => {
          const x = Number(btn.dataset.x);
          const z = Number(btn.dataset.z);
          const isDead = btn.dataset.dead === "true";
          sendCmd({ action: "walk", x, z, stopRadius: isDead ? 1.8 : 22, crouch: !isDead });
        });
      });
    }

    function isTooFastToastVisible() {
      const kabars = document.querySelectorAll('[data-testid="berburu-kabar"], [role="status"]');
      for (const el of kabars) {
        if (el.textContent && el.textContent.includes("Terlalu cepat")) return true;
      }
      return false;
    }

    function tryClickAmbil(now) {
      if (now < uiState.ambilCooldownUntil) {
        const rem = Math.ceil((uiState.ambilCooldownUntil - now) / 1000);
        uiState.autoStatus = `⏳ Jeda ambil server (${rem}d)...`;
        return false;
      }
      if (isTooFastToastVisible()) {
        uiState.ambilCooldownUntil = now + 8000;
        uiState.autoStatus = "⏳ Terlalu cepat, tunggu 8d...";
        return false;
      }
      if (now - uiState.lastAmbilAt < 5000) {
        return false;
      }
      if (clickTestId("berburu-ambil")) {
        uiState.lastAmbilAt = now;
        return true;
      }
      return false;
    }

    function runAssistTick(snap) {
      if (!snap || !snap.ready || !snap.state) return;
      const now = Date.now();

      // 0. Always dismiss "Lanjut berburu" confirmation modal if autoAmbil or autoHunt is on
      if ((uiState.autoAmbil || uiState.autoHunt) && clickTestId("berburu-lanjut")) {
        uiState.ambilCooldownUntil = now + 46000;
        return;
      }

      // 0b. Full Auto-Hunt state machine
      if (uiState.autoHunt) {
        const decision = decideAutoHuntAction(snap, uiState.filter);
        uiState.autoStatus = decision.reason;
        if (decision.target?.i != null) {
          uiState.lockedId = decision.target.i;
        }
        if (decision.type === "dodge" && now - uiState.lastDodgeAt > 1500) {
          uiState.lastDodgeAt = now;
          sendCmd({ action: "stopWalk" });
          sendCmd({ action: "dodge", dir: Math.random() < 0.5 ? 1 : -1, durationMs: 900 });
        } else if (decision.type === "ambil") {
          sendCmd({ action: "stopWalk" });
          sendCmd({ action: "stopAim" });
          tryClickAmbil(now);
        } else if (decision.type === "walk" && decision.walkOpts) {
          sendCmd({ action: "stopAim" });
          sendCmd({ action: "walk", ...decision.walkOpts });
        } else if (decision.type === "aim_shoot" && decision.target) {
          sendCmd({ action: "stopWalk" });
          sendCmd({ action: "crouch", value: true });
          sendCmd({ action: "aim", satwaId: decision.target.i, zona: "kepala", scope: true, breath: true });
          if (canAutoShoot(snap, decision.target) && now - uiState.lastShotAt > 2100) {
            if (clickTestId("berburu-tembak")) {
              uiState.lastShotAt = now;
            }
          }
        } else if (decision.type === "idle") {
          sendCmd({ action: "stopWalk" });
          sendCmd({ action: "stopAim" });
        }
        return;
      }

      // 1. Anti-Seruduk sidestep
      if (uiState.antiSeruduk) {
        const boar = snap.animals.find((a) => a.keadaan === "seruduk" && a.dist < 14);
        if (boar && now - uiState.lastDodgeAt > 1600) {
          uiState.lastDodgeAt = now;
          sendCmd({ action: "dodge", dir: Math.random() < 0.5 ? 1 : -1, durationMs: 900 });
        }
      }

      // 2. Auto-Ambil when near dead animal
      if (uiState.autoAmbil && snap.state.ambil) {
        tryClickAmbil(now);
      }

      // 3. Auto-Aim & Auto-Shoot
      if (uiState.autoAim) {
        let target = null;
        if (uiState.lockedId != null) {
          target = snap.animals.find((a) => a.i === uiState.lockedId && a.hidup);
        }
        if (!target || !target.los) {
          target = selectBestTarget(snap.animals, uiState.filter);
        }
        if (target) {
          uiState.lockedId = target.i;
          sendCmd({ action: "aim", satwaId: target.i, zona: "kepala", scope: true, breath: true });
          if (uiState.autoShoot && canAutoShoot(snap, target) && now - uiState.lastShotAt > 2100) {
            if (clickTestId("berburu-tembak")) {
              uiState.lastShotAt = now;
            }
          }
        } else {
          uiState.lockedId = null;
          sendCmd({ action: "stopAim" });
        }
      }
    }

    window.addEventListener("ks_berburu_state", (e) => {
      uiState.snapshot = e.detail;
      renderHud();
      runAssistTick(e.detail);
    });

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", createHud);
    } else {
      createHud();
    }
  }

  return {
    SATWA_ECONOMY,
    BERBURU_ECONOMY,
    HUNTING_PLAN_PRESETS,
    evaluateBagProfit,
    planHunting,
    computeRelativeDirection,
    filterAnimals,
    selectBestTarget,
    canAutoShoot,
    decideAutoHuntAction,
    clampHudPos
  };
});
