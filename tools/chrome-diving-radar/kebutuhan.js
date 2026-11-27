// KampungSebelah - Auto-Kebutuhan Pro Content Script (v1.0.0)
// Otomatisasi Kebutuhan Karakter (Makan, Kesehatan, Fisik, Rekreasi, Kebersihan, WC, Penampilan, Rumah)
// dan Kebutuhan Ojol (Bensin/SPBU, Kondisi Mesin/Bengkel, Kuota HP/Konter)

(function (root, factory) {
  const exportsObj = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = exportsObj;
  }
  if (root) {
    root.__KS_KEBUTUHAN_ENGINE__ = exportsObj;
  }
})(typeof globalThis !== "undefined" ? globalThis : (typeof window !== "undefined" ? window : this), function () {
  console.log("[AutoKebutuhan] Content script v1.0.0 loaded");

  // ==========================================
  // 1. CONSTANTS, SHOPS & FACILITIES CATALOG
  // ==========================================

  const CHARACTER_NEEDS = [
    "makan",
    "kesehatan",
    "fisik",
    "rekreasi",
    "kebersihan",
    "wc",
    "penampilan",
    "rumah"
  ];

  const OJOL_NEEDS = ["bensin", "kendaraan", "kuota"];
  const ALL_NEEDS = [...CHARACTER_NEEDS, ...OJOL_NEEDS];

  const NEED_META = {
    makan: { label: "Makan", icon: "🍚", group: "karakter" },
    kesehatan: { label: "Kesehatan", icon: "💊", group: "karakter" },
    fisik: { label: "Fisik", icon: "💪", group: "karakter" },
    rekreasi: { label: "Rekreasi", icon: "🎡", group: "karakter" },
    kebersihan: { label: "Kebersihan", icon: "🚿", group: "karakter" },
    wc: { label: "WC", icon: "🚽", group: "karakter" },
    penampilan: { label: "Penampilan", icon: "💇", group: "karakter" },
    rumah: { label: "Rumah", icon: "🏠", group: "karakter" },
    bensin: { label: "Bensin", icon: "⛽", group: "ojol" },
    kendaraan: { label: "Mesin", icon: "🔧", group: "ojol" },
    kuota: { label: "Kuota HP", icon: "📶", group: "ojol" }
  };

  const DEFAULT_THRESHOLDS = {
    makan: 50,
    kesehatan: 50,
    fisik: 45,
    rekreasi: 50,
    kebersihan: 50,
    wc: 50,
    penampilan: 50,
    rumah: 50,
    bensin: 20,
    kendaraan: 25,
    kuota: 16
  };

  const OJOL_SHOPS = {
    kendaraan: [
      { id: "4f1f6929-8ea1-4209-ab30-523b314efe11", name: "Akademis.ai Motor", item: "servis-motor" }
    ],
    kuota: [
      { id: "a162273d-6832-4223-a2b9-409d6c291291", name: "Akademis.ai Konter", item: "pulsa" }
    ]
  };

  const SPPG_FACILITIES_BY_VILLAGE = {
    "desa-utara": [
      "04f36c8b-f2a6-4d24-945c-a0b62540cb56",
      "a8d496e4-9d2d-46b8-860a-a54ea73d253d"
    ],
    "kampung-sebelah": [
      "c30281d2-de01-4fdc-a7a2-20aa039112a0",
      "e21259ea-3a4e-4d16-8287-dbb1d989e6bf",
      "f4b29614-e075-4af6-9962-f37853e71958"
    ],
    "pulau-seberang": [
      "a2c2d43b-d560-4a0d-a393-aa6ae71877b9"
    ]
  };

  const HEALTH_FACILITIES_BY_VILLAGE = {
    "desa-utara": [
      "2ff500f4-fe31-438b-be99-801eb4e6b363",
      "dbc8fb79-43d3-4b75-b3ab-dac2d0c17b10",
      "66c40451-aba1-4b58-92e3-e58a18e1e02a"
    ],
    "kampung-sebelah": [
      "c00b9433-b7a8-4ad9-874e-b4f50001723d",
      "c2b33dec-a385-4076-8733-5729a1ac3e5c",
      "0c04898c-20b1-434b-8c96-ebafef082aee"
    ],
    "pulau-seberang": [
      "48b978dd-c139-4ac6-a4d9-f178dd010882",
      "eaa4fb55-489c-4b81-9cbf-cd4b110d260f"
    ]
  };

  const BPJS_KANTOR_BY_VILLAGE = {
    "desa-utara": "5149bd70-4b0b-4b4e-be2e-839b7099f8dc",
    "kampung-sebelah": "592934a3-27b0-44ab-bb00-5c2cf53bfcb6",
    "pulau-seberang": "c9d1635a-a08b-4c33-9e0f-27bd50b17fd6"
  };

  const GYM_FACILITIES_BY_VILLAGE = {
    "desa-utara": [
      "296dc278-b765-4caf-9349-469385d6fc03",
      "d645f8b3-b82f-4172-ba39-7b5f116dd6ba"
    ],
    "kampung-sebelah": [],
    "pulau-seberang": []
  };

  const RECREATION_FACILITIES_BY_VILLAGE = {
    "desa-utara": [
      "763067a5-755d-4b76-8ce8-1049f895bbe7",
      "c7927aee-ef62-4552-8666-1f564c0300b4",
      "9ba191a6-5803-48b7-87a8-f0397b800ca7",
      "37e255ac-1c00-4755-9a27-1a9967a2534f",
      "2c7bcbc1-c55e-4e43-bbb5-ca1a5993f8b6"
    ],
    "kampung-sebelah": [
      "62106435-e70f-4ac2-9514-c3be0c0057e0",
      "a1fee99c-4812-49dd-b02a-8c4be0b3f855",
      "dc0d53d2-7b96-49cc-b174-6feadeee1cc7",
      "e16c7ea8-aabe-436e-b7cf-3c39fd3fd104",
      "975d3496-1e13-4413-b7e1-6033922f115c",
      "14d8dc53-f28a-466a-81ab-2e612f744917"
    ],
    "pulau-seberang": [
      "bd9cf9f9-2789-4e29-acc4-e7fb0e0e8ca3",
      "1919456a-3011-43df-8e5a-7242ef4bb2c3",
      "020e81d0-dcbb-46c3-ab5a-ef58c33c5942"
    ]
  };

  const NEED_SHOPS_BY_VILLAGE = {
    "desa-utara": {
      makan: [
        { id: "e42f8d13-2911-4d21-b499-e608f43dedaf", name: "Akademis.ai Warung Jajan", category: "kios" },
        { id: "88b0c25a-1297-4c41-88b1-4c7df5e887e0", name: "Akademis.ai Pecel Lele & Ayam", category: "lamongan" }
      ],
      kesehatan: [
        { id: "cc73f5cd-2f05-4e9f-867e-19445c2065b3", name: "Akademis.ai Farma", category: "toko-obat" }
      ],
      rekreasi: [
        { id: "e42f8d13-2911-4d21-b499-e608f43dedaf", name: "Akademis.ai Warung Jajan", category: "kios" },
        { id: "88b0c25a-1297-4c41-88b1-4c7df5e887e0", name: "Akademis.ai Pecel Lele & Ayam", category: "lamongan" }
      ],
      penampilan: [
        { id: "f55d08f3-b0dd-46b9-83bd-b8fb46be542f", name: "Akademis.ai Barbershop", category: "barbershop" },
        { id: "18fc7ea7-bf68-4eb5-a9e0-f3c434323e4d", name: "Akademis.ai - Barbershop", category: "barbershop" }
      ],
      rumah: [
        { id: "7c4c0d5f-dab6-435b-a958-3a85354647c4", name: "Akademis.ai Bangunan", category: "toko-bangunan" }
      ]
    },
    "kampung-sebelah": {
      penampilan: [
        { id: "beca69c4-7bd2-4624-8a97-150654d28914", name: "Akademis.ai - Pangkas Rambut", category: "barbershop" }
      ]
    }
  };

  const FOOD_SHOP_CATEGORIES = [
    "coffee-shop",
    "kedai-kopi",
    "kios",
    "lamongan",
    "minimarket",
    "restoran",
    "rumah-makan",
    "warung",
    "warung-sembako",
    "warnet"
  ];

  const NEED_SHOP_CATEGORIES = {
    makan: FOOD_SHOP_CATEGORIES,
    kesehatan: [...FOOD_SHOP_CATEGORIES, "toko-obat"],
    rekreasi: FOOD_SHOP_CATEGORIES,
    penampilan: ["barbershop"],
    rumah: ["toko-bangunan"]
  };

  const FALLBACK_ITEM_EFFECTS = {
    "paku-semen": { rumah: 25 },
    "cat-tembok": { rumah: 40 },
    "pasir": { rumah: 15 },
    "bata": { rumah: 20 },
    "pipa": { rumah: 20 },
    "pipa-paralon": { rumah: 20 }
  };

  const NAMPAN_TARGET_GROUPS = ["pokok", "lauk", "sayur", "buah", "susu"];
  const NAMPAN_ITEM_GROUPS = {
    nasi: "pokok", jagung: "pokok", kentang: "pokok", ubi: "pokok", singkong: "pokok",
    ikan: "lauk", telur: "lauk", tempe: "lauk", tahu: "lauk", ayam: "lauk", daging: "lauk",
    bayam: "sayur", brokoli: "sayur", wortel: "sayur", kangkung: "sayur", sawi: "sayur",
    pisang: "buah", jeruk: "buah", apel: "buah", pepaya: "buah", semangka: "buah",
    susu: "susu",
    gorengan: null, "es-sirup": null, permen: null, "mi-instan": null
  };

  // ==========================================
  // 2. PURE PARSERS, EVALUATORS & SOLVERS
  // ==========================================

  function parseKebutuhanResponse(payload) {
    if (!payload || typeof payload !== "object") {
      return { asleep: false, needs: {}, bersih: {}, kondisi: {} };
    }
    const needs = {};
    if (Array.isArray(payload.needs)) {
      for (const row of payload.needs) {
        if (row && typeof row.id === "string" && typeof row.value === "number") {
          needs[row.id] = row.value;
        }
      }
    }
    for (const key of CHARACTER_NEEDS) {
      if (typeof needs[key] !== "number" && typeof payload[key] === "number") {
        needs[key] = payload[key];
      }
    }
    return {
      asleep: Boolean(payload.asleep),
      needs,
      bersih: payload.bersih && typeof payload.bersih === "object" ? payload.bersih : {},
      kondisi: payload.kondisi && typeof payload.kondisi === "object" ? payload.kondisi : {}
    };
  }

  function parseOjolBarsResponse(payload) {
    if (!payload || typeof payload !== "object") {
      return { enabled: false, mitra: false, vehicle: "motor", trip: null, bars: {} };
    }
    const bars = payload.bars || {};
    return {
      enabled: payload.enabled === true,
      mitra: payload.mitra === true,
      vehicle: payload.vehicle || "motor",
      trip: payload.trip || null,
      bars: {
        bensin: typeof bars.bensin === "number" ? bars.bensin : null,
        kendaraan: typeof bars.kendaraan === "number" ? bars.kendaraan : null,
        kuota: typeof bars.kuota === "number" ? bars.kuota : null
      }
    };
  }

  function getThresholdForNeed(needKey, config = {}) {
    if (config.thresholds && typeof config.thresholds[needKey] === "number") {
      return config.thresholds[needKey];
    }
    if (OJOL_NEEDS.includes(needKey)) {
      return DEFAULT_THRESHOLDS[needKey];
    }
    if (typeof config.defaultCharThreshold === "number") {
      return config.defaultCharThreshold;
    }
    return DEFAULT_THRESHOLDS[needKey] ?? 50;
  }

  function evaluateAllKebutuhan(charData, ojolData, config = {}) {
    if (charData?.asleep) return [];

    const candidates = [];
    const enabledNeeds = config.enabledNeeds || {};
    const autoOjolNeeds = config.autoOjolNeeds !== false;

    // 1. Kebutuhan Ojol (prioritas tinggi jika menjadi mitra & tidak sedang trip)
    if (autoOjolNeeds && ojolData && !ojolData.trip && ojolData.bars) {
      const ojolWeights = { kuota: 14, bensin: 12, kendaraan: 10 };
      for (const key of OJOL_NEEDS) {
        if (enabledNeeds[key] === false) continue;
        const val = ojolData.bars[key];
        if (typeof val !== "number") continue;
        const threshold = getThresholdForNeed(key, config);
        if (val <= threshold) {
          candidates.push({
            group: "ojol",
            resource: key,
            name: NEED_META[key].label,
            current: val,
            threshold,
            priority: (threshold - val) + (ojolWeights[key] || 10)
          });
        }
      }
    }

    // 2. Kebutuhan Karakter
    const charNeeds = charData?.needs || {};
    const kondisi = charData?.kondisi || {};
    const charWeights = {
      wc: 9,
      kebersihan: 8,
      makan: 7,
      kesehatan: 7,
      fisik: 5,
      rekreasi: 4,
      penampilan: 3,
      rumah: 2
    };

    for (const key of CHARACTER_NEEDS) {
      if (enabledNeeds[key] === false) continue;
      const val = charNeeds[key];
      const threshold = getThresholdForNeed(key, config);
      const forcedByCondition =
        (key === "wc" && kondisi.kebelet === true) ||
        (key === "kebersihan" && kondisi.bau === true);

      if ((typeof val === "number" && val < threshold) || forcedByCondition) {
        const effectiveVal = typeof val === "number" ? val : 0;
        candidates.push({
          group: "karakter",
          resource: key,
          name: NEED_META[key].label,
          current: effectiveVal,
          threshold,
          forcedByCondition,
          priority: (forcedByCondition ? 20 : 0) + (threshold - effectiveVal) + (charWeights[key] || 1)
        });
      }
    }

    candidates.sort((a, b) => b.priority - a.priority);
    return candidates;
  }

  function solveNampanPicks(items, pickCount = 5) {
    const list = (Array.isArray(items) ? items : []).map(it => {
      if (it && typeof it === "object") {
        const id = String(it.id);
        return { id, group: it.group !== undefined ? it.group : NAMPAN_ITEM_GROUPS[id] };
      }
      const id = String(it);
      return { id, group: NAMPAN_ITEM_GROUPS[id] };
    });

    const picks = [];
    for (const target of NAMPAN_TARGET_GROUPS) {
      if (picks.length >= pickCount) break;
      const found = list.find(x => x.group === target && !picks.includes(x.id));
      if (found) picks.push(found.id);
    }
    if (picks.length < pickCount) {
      for (const x of list) {
        if (picks.length >= pickCount) break;
        if (x.group !== null && x.group !== undefined && !picks.includes(x.id)) {
          picks.push(x.id);
        }
      }
    }
    if (picks.length < pickCount) {
      for (const x of list) {
        if (picks.length >= pickCount) break;
        if (!picks.includes(x.id)) picks.push(x.id);
      }
    }
    return picks;
  }

  function solveFotoShots(periods, leadMs = 600) {
    return (Array.isArray(periods) ? periods : []).map(p => Math.round(leadMs + p * 0.25));
  }

  function solveGymHolds(reps) {
    return (Array.isArray(reps) ? reps : []).map(r => {
      const fill = typeof r?.fill === "number" ? r.fill : 1400;
      const center = typeof r?.center === "number" ? r.center : 0.7;
      return Math.round(fill * center);
    });
  }

  function extractItemEffects(item, needKey) {
    if (item?.rasa?.isi && typeof item.rasa.isi === "object") {
      return item.rasa.isi;
    }
    if (item?.effects && typeof item.effects === "object") {
      return item.effects;
    }
    if (item?.kebutuhan && typeof item.kebutuhan === "object") {
      return item.kebutuhan;
    }
    const itemId = String(item?.id || item?.item || "").toLowerCase();
    if (FALLBACK_ITEM_EFFECTS[itemId]) {
      return FALLBACK_ITEM_EFFECTS[itemId];
    }
    if (typeof item?.gain === "number" && needKey) {
      return { [needKey]: item.gain };
    }
    return {};
  }

  function pickBestShopItem(menu, needKey, currentValue = 0, options = {}) {
    if (!Array.isArray(menu) || menu.length === 0) return null;
    const maxPriceMilli = typeof options.maxPriceMilli === "number" ? options.maxPriceMilli : Infinity;
    const room = Math.max(1, 100 - currentValue);

    const valid = [];
    for (const item of menu) {
      if (!item || item.enabled === false) continue;
      if (typeof item.stock === "number" && item.stock <= 0) continue;
      const priceMilli = typeof item.priceMilli === "number" ? item.priceMilli : null;
      if (priceMilli === null || priceMilli < 0 || priceMilli > maxPriceMilli) continue;

      // Untuk barang non-rumah, harus langsung dipakai (service / eaten / rasa)
      const isDirect = Boolean(item.service || item.eaten || item.rasa?.isi || needKey === "rumah");
      if (!isDirect) continue;

      const effects = extractItemEffects(item, needKey);
      const gain = typeof effects[needKey] === "number" ? effects[needKey] : 0;
      if (gain <= 0) continue;

      const usableGain = Math.min(gain, room);
      const costPerPoint = priceMilli / usableGain;
      valid.push({
        item,
        id: item.id || item.item,
        name: item.name || item.nama || item.id,
        priceMilli,
        gain,
        costPerPoint
      });
    }

    if (valid.length === 0) return null;
    valid.sort((a, b) => {
      if (Math.abs(a.costPerPoint - b.costPerPoint) > 0.001) {
        return a.costPerPoint - b.costPerPoint;
      }
      return a.priceMilli - b.priceMilli;
    });
    return valid[0];
  }

  function makeRequestId() {
    if (typeof crypto !== "undefined" && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return `req_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  }

  // ==========================================
  // 3. API EXECUTORS (SAME-ORIGIN FETCH)
  // ==========================================

  async function apiGet(url) {
    const res = await fetch(url, { credentials: "same-origin" });
    const data = await res.json().catch(() => null);
    return { ok: res.ok, status: res.status, data };
  }

  async function apiPost(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(body)
    });
    const data = await res.json().catch(() => null);
    return { ok: res.ok, status: res.status, data };
  }

  async function getHomeAndDirectory() {
    const [meRes, destRes] = await Promise.all([
      apiGet("/api/game/me"),
      apiGet("/api/tujuan")
    ]);
    const home = meRes.ok ? meRes.data?.home || {} : {};
    const balanceMilli = meRes.ok && typeof meRes.data?.balanceMilli === "number" ? meRes.data.balanceMilli : 0;
    const usaha = destRes.ok && Array.isArray(destRes.data?.usaha) ? destRes.data.usaha : [];
    return { home, balanceMilli, usaha };
  }

  function sortByDistanceFromHome(list, home) {
    const refX = home?.x ?? 0;
    const refY = home?.y ?? 0;
    return [...list].sort((a, b) => {
      const da = ((a.x ?? 0) - refX) ** 2 + ((a.y ?? 0) - refY) ** 2;
      const db = ((b.x ?? 0) - refX) ** 2 + ((b.y ?? 0) - refY) ** 2;
      return da - db;
    });
  }

  async function refillSpbuViaApi(activeVehicle = "motor") {
    const kendRes = await apiGet("/api/kendaraan");
    if (!kendRes.ok) return { success: false, error: "Gagal membaca kendaraan" };
    const vehicles = Array.isArray(kendRes.data?.items) ? kendRes.data.items : [];
    const isCar = activeVehicle === "mobil";
    const vehicle = vehicles.find(v => (isCar ? v.family === "mobil" : v.family === "motor")) || vehicles[0];
    if (!vehicle?.kode) return { success: false, error: "Kendaraan Ojol belum terdaftar" };

    const { home, usaha } = await getHomeAndDirectory();
    const spbus = sortByDistanceFromHome(
      usaha.filter(u => u.item === "spbu-pertamina"),
      home
    );
    if (spbus.length === 0) return { success: false, error: "Tidak ada SPBU di peta" };

    const spbu = spbus[0];
    const plotId = spbu.plotId;

    const datangRes = await apiPost(`/api/spbu/${plotId}`, {
      aksi: "datang",
      kode: vehicle.kode,
      dorong: false,
      x: spbu.x,
      y: spbu.y
    });
    if (!datangRes.ok) {
      return { success: false, error: datangRes.data?.error || `Gagal hadir di SPBU (${datangRes.status})` };
    }

    const isiRes = await apiPost(`/api/spbu/${plotId}`, {
      aksi: "isi",
      jumlah: "penuh",
      x: spbu.x,
      y: spbu.y,
      requestId: makeRequestId()
    });

    try {
      await apiPost(`/api/spbu/${plotId}`, { aksi: "pamit" });
    } catch {}

    if (isiRes.ok) {
      return { success: true, detail: `${spbu.name || "SPBU"} (${isiRes.data?.item || "isi-bensin"})` };
    }
    return { success: false, error: isiRes.data?.error || `Gagal isi bensin (${isiRes.status})` };
  }

  async function fulfillOjolNeed(resource, activeVehicle = "motor") {
    if (resource === "bensin") {
      return await refillSpbuViaApi(activeVehicle);
    }

    const fixed = OJOL_SHOPS[resource] || [];
    for (const shop of fixed) {
      const res = await apiPost(`/api/shops/${shop.id}/buy`, {
        item: shop.item,
        requestId: makeRequestId()
      });
      if (res.ok) return { success: true, detail: `${shop.name} (${shop.item})` };
      if (res.status !== 400 && res.status !== 404) {
        return { success: false, error: res.data?.error || `HTTP ${res.status}` };
      }
    }

    const { home, usaha } = await getHomeAndDirectory();
    const categoryItem = resource === "kendaraan" ? "bengkel-motor" : "konter-pulsa";
    const buyItem = resource === "kendaraan" ? "servis-motor" : "pulsa";
    const matching = sortByDistanceFromHome(
      usaha.filter(u => u.item === categoryItem),
      home
    );

    for (const shop of matching) {
      const shopId = shop.businessId || shop.plotId;
      const res = await apiPost(`/api/shops/${shopId}/buy`, {
        item: buyItem,
        requestId: makeRequestId()
      });
      if (res.ok) return { success: true, detail: `${shop.name || shopId} (${buyItem})` };
    }

    return { success: false, error: `Tidak ada toko ${resource} yang tersedia` };
  }

  async function completeFacilityKegiatan(facilityId) {
    const keg = await apiGet(`/api/facilities/${facilityId}/kegiatan`);
    if (!keg.ok || !keg.data?.available) return null;
    const { visitId, kind, plan = {} } = keg.data;

    if (kind === "tensi") {
      const stops = (plan.periods || []).map(p => Math.round(p * 0.25));
      return await apiPost(`/api/facilities/${facilityId}/kegiatan`, { visitId, stops });
    }
    if (kind === "detak") {
      const taps = (plan.beats || []).map(b => Math.round(b));
      return await apiPost(`/api/facilities/${facilityId}/kegiatan`, { visitId, taps });
    }
    if (kind === "nampan") {
      const picks = solveNampanPicks(plan.items || []);
      return await apiPost(`/api/facilities/${facilityId}/kegiatan`, { visitId, picks });
    }
    if (kind === "foto") {
      const shots = solveFotoShots(plan.periods || []);
      return await apiPost(`/api/facilities/${facilityId}/kegiatan`, { visitId, shots });
    }
    return null;
  }

  async function tryCooldownFacility(facilityIds, label) {
    for (const id of facilityIds) {
      const det = await apiGet(`/api/facilities/${id}`);
      if (!det.ok || !det.data) continue;
      const d = det.data;
      if (d.state !== "DONE" || !d.service?.open || d.nextAt || d.myVisitUntil) continue;
      const useRes = await apiPost(`/api/facilities/${id}/use`, { requestId: makeRequestId() });
      if (useRes.ok) {
        await completeFacilityKegiatan(id).catch(() => null);
        return { success: true, detail: d.title || label };
      }
    }
    return null;
  }

  async function buyFromNeedShops(needKey, currentValue, village, home, usaha, maxPriceMilli) {
    const fixedShops = NEED_SHOPS_BY_VILLAGE[village]?.[needKey] || [];
    const allowedCategories = new Set(NEED_SHOP_CATEGORIES[needKey] || []);
    const dirShops = sortByDistanceFromHome(
      usaha.filter(u => allowedCategories.has(u.item)),
      home
    ).map(u => ({
      id: u.businessId || u.plotId,
      name: u.name || u.plotId,
      category: u.item
    }));

    const seen = new Set();
    const candidates = [];
    for (const s of [...fixedShops, ...dirShops]) {
      if (!s.id || seen.has(s.id)) continue;
      seen.add(s.id);
      candidates.push(s);
    }

    for (const shop of candidates) {
      const shopRes = await apiGet(`/api/shops/${shop.id}`);
      if (!shopRes.ok || !shopRes.data || shopRes.data.open === false || shopRes.data.mine) continue;
      const menu = shopRes.data.menu || shopRes.data.items || [];
      const best = pickBestShopItem(menu, needKey, currentValue, { maxPriceMilli });
      if (!best) continue;

      const buyRes = await apiPost(`/api/shops/${shop.id}/buy`, {
        item: best.id,
        requestId: makeRequestId()
      });
      if (buyRes.ok) {
        return { success: true, detail: `${shop.name} (${best.name})` };
      }
    }
    return null;
  }

  async function fulfillCharacterNeed(needKey, currentValue, charData, config = {}) {
    // 1. WC & Kebersihan (Kamar mandi rumah - gratis)
    if (needKey === "wc") {
      const res = await apiPost("/api/rumah/kamar-mandi", { aksi: "wc" });
      if (res.ok) return { success: true, detail: "Kamar mandi (WC)" };
      return { success: false, error: res.data?.error || "Gagal ke WC" };
    }

    if (needKey === "kebersihan") {
      const bersih = charData?.bersih || {};
      const mandiUsed = bersih.mandi ?? 0;
      const mandiMaks = bersih.mandiMaks ?? 2;
      const sikatUsed = bersih.sikat ?? 0;
      const sikatMaks = bersih.sikatMaks ?? 3;

      let aksi = "cuci";
      if (mandiUsed < mandiMaks) aksi = "mandi";
      else if (sikatUsed < sikatMaks) aksi = "sikat";

      let res = await apiPost("/api/rumah/kamar-mandi", { aksi });
      if (!res.ok && res.data?.error && /sabun|pasta/i.test(res.data.error)) {
        const beliItem = aksi === "mandi" ? "sabun" : "pasta";
        await apiPost("/api/rumah/kamar-mandi", { beli: beliItem, requestId: makeRequestId() });
        res = await apiPost("/api/rumah/kamar-mandi", { aksi });
      }
      if (res.ok) return { success: true, detail: `Kamar mandi (${aksi})` };
      return { success: false, error: res.data?.error || `Gagal ${aksi}` };
    }

    const { home, balanceMilli, usaha } = await getHomeAndDirectory();
    const village = home?.desa || "desa-utara";
    const minBalanceMilli = (config.minBalanceKoin ?? 5) * 1000;
    const maxPriceMilli = Math.max(0, balanceMilli - minBalanceMilli);

    // 2. Fisik: Prioritas Minigame Angkat Beban gratis -> Gym desa berbayar
    if (needKey === "fisik") {
      const gymIds = [...(GYM_FACILITIES_BY_VILLAGE[village] || [])];
      if (gymIds.length === 0) {
        const tempatRes = await apiGet("/api/kebutuhan?tempat=fisik");
        if (tempatRes.ok && Array.isArray(tempatRes.data?.places)) {
          for (const p of tempatRes.data.places) {
            if (p.kind === "fasum" && p.id && !gymIds.includes(p.id)) gymIds.push(p.id);
          }
        }
      }

      for (const gid of gymIds) {
        const mg = await apiGet(`/api/minigame?projectId=${gid}&game=gym`);
        if (mg.ok && mg.data?.playsLeft > 0) {
          const startRes = await apiPost("/api/minigame", {
            action: "start",
            projectId: gid,
            requestId: makeRequestId(),
            game: "gym"
          });
          if (startRes.ok && startRes.data?.playId) {
            const reps = startRes.data?.plan?.reps || startRes.data?.plan || [];
            const holds = solveGymHolds(reps);
            const waitMs = holds.reduce((a, b) => a + b, 0) + Math.max(0, holds.length - 1) * 1100;
            if (waitMs > 0) {
              await new Promise(r => setTimeout(r, Math.min(waitMs, 15000)));
            }
            const finRes = await apiPost("/api/minigame", {
              action: "finish",
              playId: startRes.data.playId,
              holds
            });
            if (finRes.ok && !finRes.data?.detail?.invalid) {
              return { success: true, detail: "Gym Minigame (Angkat Beban)" };
            }
          }
        }
      }

      if (maxPriceMilli >= 2000) {
        const gymPaid = await tryCooldownFacility(gymIds, "Gym Desa");
        if (gymPaid) return gymPaid;
      }
      return { success: false, error: "Gym cooldown / minigame habis" };
    }

    // 3. Kesehatan: Prioritas BPJS Gratis -> Toko Obat
    if (needKey === "kesehatan") {
      const bpjsRes = await apiGet("/api/bpjs");
      if (bpjsRes.ok && bpjsRes.data) {
        let gratisSisa = bpjsRes.data.gratisSisa ?? 0;
        const kartu = bpjsRes.data.kartu;
        const iuranMilli = bpjsRes.data.rules?.iuranMilli ?? 5000;
        if ((!kartu || !kartu.aktif || kartu.sisaHari <= 0) && BPJS_KANTOR_BY_VILLAGE[village] && maxPriceMilli >= iuranMilli) {
          await apiPost("/api/bpjs/bayar", {
            projectId: BPJS_KANTOR_BY_VILLAGE[village],
            requestId: makeRequestId()
          });
          const recheck = await apiGet("/api/bpjs");
          if (recheck.ok) gratisSisa = recheck.data?.gratisSisa ?? 0;
        }
        if (gratisSisa > 0) {
          const healthRes = await tryCooldownFacility(HEALTH_FACILITIES_BY_VILLAGE[village] || [], "Puskesmas/RS (BPJS)");
          if (healthRes) return healthRes;
        }
      }
    }

    // 4. Makan: Prioritas SPPG Gratis
    if (needKey === "makan") {
      const sppgRes = await tryCooldownFacility(SPPG_FACILITIES_BY_VILLAGE[village] || [], "SPPG Makan Bergizi");
      if (sppgRes) return sppgRes;
    }

    // 5. Rekreasi: Prioritas Alun-alun / Taman Desa Gratis
    if (needKey === "rekreasi") {
      const recRes = await tryCooldownFacility(RECREATION_FACILITIES_BY_VILLAGE[village] || [], "Taman/Alun-alun");
      if (recRes) return recRes;
    }

    // 6. Fallback ke Toko (Makan, Kesehatan, Rekreasi, Penampilan, Rumah)
    if (NEED_SHOP_CATEGORIES[needKey]) {
      const shopRes = await buyFromNeedShops(needKey, currentValue, village, home, usaha, maxPriceMilli);
      if (shopRes) return shopRes;
    }

    return { success: false, error: `Tidak ada layanan/toko tersedia untuk ${needKey}` };
  }

  // ==========================================
  // 4. BROWSER EXTENSION RUNTIME & HUD UI
  // ==========================================

  if (typeof window !== "undefined" && typeof document !== "undefined") {
    function isEligiblePage() {
      const p = window.location.pathname;
      return !p.startsWith("/diving") && !p.startsWith("/mancing") && !p.startsWith("/berburu");
    }

    if (!isEligiblePage()) {
      return {
        CHARACTER_NEEDS,
        OJOL_NEEDS,
        ALL_NEEDS,
        DEFAULT_THRESHOLDS,
        parseKebutuhanResponse,
        parseOjolBarsResponse,
        evaluateAllKebutuhan,
        solveNampanPicks,
        solveFotoShots,
        solveGymHolds,
        pickBestShopItem
      };
    }

    const kebConfig = {
      enabled: false,
      autoOjolNeeds: true,
      defaultCharThreshold: 50,
      minBalanceKoin: 5,
      enabledNeeds: {
        makan: true,
        kesehatan: true,
        fisik: true,
        rekreasi: true,
        kebersihan: true,
        wc: true,
        penampilan: true,
        rumah: true,
        bensin: true,
        kendaraan: true,
        kuota: true
      }
    };

    const kebStats = {
      asleep: false,
      needs: {},
      ojolBars: { bensin: null, kendaraan: null, kuota: null },
      vehicle: "motor",
      trip: null,
      statusMessage: "Siap pantau kebutuhan karakter & ojol",
      logs: []
    };

    let isProcessing = false;
    let pollTimer = null;

    function saveSettings() {
      try {
        localStorage.setItem("ks_kebutuhan_config", JSON.stringify(kebConfig));
      } catch {}
    }

    try {
      const saved = localStorage.getItem("ks_kebutuhan_config");
      if (saved) {
        const parsed = JSON.parse(saved);
        Object.assign(kebConfig, parsed);
        kebConfig.enabledNeeds = { ...kebConfig.enabledNeeds, ...(parsed.enabledNeeds || {}) };
      }
    } catch {}

    function addLog(msg) {
      const time = new Date().toLocaleTimeString("id-ID", { hour12: false });
      kebStats.logs.unshift(`[${time}] ${msg}`);
      if (kebStats.logs.length > 20) kebStats.logs.pop();
      const logList = document.getElementById("ks-keb-log-list");
      if (logList) {
        logList.innerHTML = kebStats.logs.map(l => `<div>${l}</div>`).join("");
      }
    }

    async function refreshStatus() {
      const [kebRes, ojolRes] = await Promise.all([
        apiGet("/api/kebutuhan"),
        apiGet("/api/ojol")
      ]);
      const charData = kebRes.ok ? parseKebutuhanResponse(kebRes.data) : null;
      const ojolData = ojolRes.ok ? parseOjolBarsResponse(ojolRes.data) : null;

      if (charData) {
        kebStats.asleep = charData.asleep;
        kebStats.needs = charData.needs;
        kebStats.charData = charData;
      }
      if (ojolData) {
        kebStats.ojolBars = ojolData.bars;
        kebStats.vehicle = ojolData.vehicle;
        kebStats.trip = ojolData.trip;
        kebStats.ojolData = ojolData;
      }
      updateHUDView();
      return { charData, ojolData };
    }

    async function runNeedCycle(forceRun = false) {
      if (isProcessing) return;
      if (!forceRun && !kebConfig.enabled) return;

      isProcessing = true;
      try {
        const { charData, ojolData } = await refreshStatus();
        if (charData?.asleep) {
          kebStats.statusMessage = "😴 Karakter sedang tidur (jeda otomatis)";
          updateHUDView();
          return;
        }

        const queue = evaluateAllKebutuhan(charData, ojolData, kebConfig);
        if (queue.length === 0) {
          kebStats.statusMessage = "✅ Semua kebutuhan aman";
          updateHUDView();
          return;
        }

        const target = queue[0];
        kebStats.statusMessage = `⏳ Memenuhi ${target.name} (${target.current}%)...`;
        addLog(`⏳ Memproses ${target.name} (${target.current}% <= ${target.threshold}%)`);
        updateHUDView();

        let result;
        if (target.group === "ojol") {
          result = await fulfillOjolNeed(target.resource, kebStats.vehicle);
        } else {
          result = await fulfillCharacterNeed(target.resource, target.current, charData, kebConfig);
        }

        if (result.success) {
          addLog(`✅ ${target.name} terpenuhi: ${result.detail}`);
          kebStats.statusMessage = `✅ ${target.name} terpenuhi`;
          await refreshStatus();
        } else {
          addLog(`⚠️ ${target.name}: ${result.error}`);
          kebStats.statusMessage = `⚠️ ${target.name}: ${result.error}`;
        }
      } catch (err) {
        addLog(`❌ Error: ${err.message || err}`);
      } finally {
        isProcessing = false;
        updateHUDView();
      }
    }

    function setupDraggable(elem, handle, storageKey) {
      if (storageKey) {
        try {
          const raw = localStorage.getItem(storageKey);
          if (raw) {
            const pos = JSON.parse(raw);
            if (typeof pos.left === "number" && typeof pos.top === "number") {
              elem.style.left = `${Math.max(8, Math.min(window.innerWidth - 260, pos.left))}px`;
              elem.style.top = `${Math.max(8, Math.min(window.innerHeight - 100, pos.top))}px`;
              elem.style.right = "auto";
            }
          }
        } catch {}
      }
      let dragging = false, startX = 0, startY = 0, origLeft = 0, origTop = 0;
      handle.onmousedown = (e) => {
        if (e.target.closest("button, input, select")) return;
        dragging = true;
        const rect = elem.getBoundingClientRect();
        origLeft = rect.left;
        origTop = rect.top;
        startX = e.clientX;
        startY = e.clientY;
        elem.style.right = "auto";
        e.preventDefault();
      };
      window.addEventListener("mousemove", (e) => {
        if (!dragging) return;
        const left = Math.max(8, Math.min(window.innerWidth - elem.offsetWidth - 8, origLeft + (e.clientX - startX)));
        const top = Math.max(8, Math.min(window.innerHeight - 60, origTop + (e.clientY - startY)));
        elem.style.left = `${left}px`;
        elem.style.top = `${top}px`;
      });
      window.addEventListener("mouseup", () => {
        if (!dragging) return;
        dragging = false;
        if (storageKey) {
          const rect = elem.getBoundingClientRect();
          try {
            localStorage.setItem(storageKey, JSON.stringify({ left: rect.left, top: rect.top }));
          } catch {}
        }
      });
    }

    function renderMeterRows(keys) {
      return keys.map(k => {
        const meta = NEED_META[k];
        return `
          <div style="display:flex;align-items:center;gap:6px;margin-bottom:5px;">
            <input type="checkbox" id="ks-keb-chk-${k}" style="margin:0;cursor:pointer;" />
            <span style="width:82px;font-size:10px;color:#cbd5e1;white-space:nowrap;">${meta.icon} ${meta.label}</span>
            <div style="flex:1;height:6px;background:rgba(255,255,255,0.08);border-radius:3px;overflow:hidden;">
              <div id="ks-keb-bar-${k}" style="width:0%;height:100%;background:#10b981;transition:width 0.3s;"></div>
            </div>
            <span id="ks-keb-val-${k}" style="width:30px;text-align:right;font-size:10px;font-weight:bold;color:#10b981;">--%</span>
          </div>
        `;
      }).join("");
    }

    function updateHUDView() {
      const badge = document.getElementById("ks-keb-badge");
      const btnStart = document.getElementById("ks-keb-btn-start");
      const statusText = document.getElementById("ks-keb-status");
      if (!badge || !btnStart) return;

      badge.textContent = kebConfig.enabled ? "ON" : "OFF";
      badge.style.background = kebConfig.enabled ? "#059669" : "#334155";
      badge.style.color = kebConfig.enabled ? "#ecfdf5" : "#94a3b8";

      btnStart.textContent = kebConfig.enabled ? "⏹ HENTIKAN AUTO-KEBUTUHAN" : "▶ MULAI AUTO-KEBUTUHAN";
      btnStart.style.background = kebConfig.enabled
        ? "linear-gradient(135deg, #dc2626, #991b1b)"
        : "linear-gradient(135deg, #059669, #047857)";

      if (statusText) statusText.textContent = kebStats.statusMessage;

      for (const k of ALL_NEEDS) {
        const chk = document.getElementById(`ks-keb-chk-${k}`);
        if (chk) chk.checked = kebConfig.enabledNeeds[k] !== false;

        const val = OJOL_NEEDS.includes(k) ? kebStats.ojolBars[k] : kebStats.needs[k];
        const valEl = document.getElementById(`ks-keb-val-${k}`);
        const barEl = document.getElementById(`ks-keb-bar-${k}`);
        if (!valEl || !barEl) continue;

        if (typeof val !== "number") {
          valEl.textContent = "--%";
          barEl.style.width = "0%";
          continue;
        }
        const clamped = Math.max(0, Math.min(100, Math.round(val)));
        const thr = getThresholdForNeed(k, kebConfig);
        const color = clamped <= thr ? "#ef4444" : (clamped <= thr + 15 ? "#f59e0b" : "#10b981");
        valEl.textContent = `${clamped}%`;
        valEl.style.color = color;
        barEl.style.width = `${clamped}%`;
        barEl.style.background = color;
      }
    }

    function createHUD() {
      if (document.getElementById("ks-kebutuhan-hud")) return;

      const hud = document.createElement("div");
      hud.id = "ks-kebutuhan-hud";
      hud.style.cssText = `
        position: fixed;
        top: 80px;
        right: 290px;
        width: 268px;
        background: rgba(15, 23, 42, 0.94);
        backdrop-filter: blur(8px);
        border: 1px solid rgba(16, 185, 129, 0.4);
        border-radius: 10px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.55);
        color: #f8fafc;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        font-size: 12px;
        z-index: 999998;
        display: none;
        overflow: hidden;
      `;

      hud.innerHTML = `
        <div id="ks-keb-header" style="
          display:flex;justify-content:space-between;align-items:center;
          padding:8px 10px;background:rgba(16,185,129,0.16);
          border-bottom:1px solid rgba(16,185,129,0.25);cursor:move;user-select:none;
        ">
          <div style="display:flex;align-items:center;gap:6px;font-weight:bold;color:#34d399;">
            <span>🧼 Auto-Kebutuhan</span>
            <span id="ks-keb-badge" style="font-size:10px;padding:1px 6px;border-radius:4px;background:#334155;color:#94a3b8;">OFF</span>
          </div>
          <div style="display:flex;gap:4px;">
            <button id="ks-keb-min" style="background:none;border:none;color:#94a3b8;cursor:pointer;font-weight:bold;">_</button>
            <button id="ks-keb-close" style="background:none;border:none;color:#94a3b8;cursor:pointer;font-weight:bold;">×</button>
          </div>
        </div>
        <div id="ks-keb-body" style="padding:10px;">
          <div style="font-size:10px;font-weight:bold;color:#38bdf8;margin-bottom:4px;">🚗 KEBUTUHAN OJOL</div>
          <div style="background:rgba(255,255,255,0.04);border-radius:6px;padding:6px 8px;margin-bottom:8px;">
            ${renderMeterRows(OJOL_NEEDS)}
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
            <span style="font-size:10px;font-weight:bold;color:#34d399;">🧍 KEBUTUHAN KARAKTER</span>
            <label style="font-size:10px;color:#94a3b8;">
              Min: <input id="ks-keb-thr" type="number" min="10" max="95" value="${kebConfig.defaultCharThreshold}" style="width:36px;background:#0f172a;color:#f8fafc;border:1px solid #334155;border-radius:4px;padding:1px 3px;font-size:10px;" />%
            </label>
          </div>
          <div style="background:rgba(255,255,255,0.04);border-radius:6px;padding:6px 8px;margin-bottom:8px;">
            ${renderMeterRows(CHARACTER_NEEDS)}
          </div>
          <div id="ks-keb-status" style="font-size:11px;background:rgba(0,0,0,0.3);padding:5px 7px;border-radius:5px;margin-bottom:8px;color:#e2e8f0;">
            Siap pantau kebutuhan
          </div>
          <div style="display:flex;gap:6px;margin-bottom:8px;">
            <button id="ks-keb-btn-start" style="flex:1;padding:8px;border:none;border-radius:6px;font-weight:bold;font-size:11px;color:#fff;cursor:pointer;background:linear-gradient(135deg,#059669,#047857);">
              ▶ MULAI AUTO-KEBUTUHAN
            </button>
            <button id="ks-keb-btn-now" title="Cek & Penuhi Sekarang" style="padding:8px 10px;border:1px solid rgba(255,255,255,0.15);border-radius:6px;background:rgba(255,255,255,0.06);color:#f8fafc;font-size:11px;cursor:pointer;">
              🔄
            </button>
          </div>
          <div id="ks-keb-log-list" style="height:56px;overflow-y:auto;background:rgba(0,0,0,0.35);border-radius:4px;padding:4px 6px;font-family:monospace;font-size:10px;color:#94a3b8;line-height:1.35;">
            <div>[Sistem] Auto-Kebutuhan siap.</div>
          </div>
        </div>
      `;

      document.body.appendChild(hud);
      setupDraggable(hud, document.getElementById("ks-keb-header"), "ks_hud_pos_kebutuhan");

      for (const k of ALL_NEEDS) {
        const chk = document.getElementById(`ks-keb-chk-${k}`);
        if (chk) {
          chk.onchange = (e) => {
            kebConfig.enabledNeeds[k] = !!e.target.checked;
            saveSettings();
          };
        }
      }

      const thrInput = document.getElementById("ks-keb-thr");
      if (thrInput) {
        thrInput.onchange = (e) => {
          const v = Math.max(10, Math.min(95, Number(e.target.value) || 50));
          kebConfig.defaultCharThreshold = v;
          thrInput.value = String(v);
          saveSettings();
          updateHUDView();
        };
      }

      document.getElementById("ks-keb-btn-start").onclick = () => {
        kebConfig.enabled = !kebConfig.enabled;
        saveSettings();
        addLog(kebConfig.enabled ? "▶ Auto-Kebutuhan diaktifkan" : "⏹ Auto-Kebutuhan dihentikan");
        updateHUDView();
        if (kebConfig.enabled) runNeedCycle(true);
      };

      document.getElementById("ks-keb-btn-now").onclick = () => {
        runNeedCycle(true);
      };

      let minimized = false;
      const minBtn = document.getElementById("ks-keb-min");
      minBtn.onclick = () => {
        minimized = !minimized;
        document.getElementById("ks-keb-body").style.display = minimized ? "none" : "block";
        minBtn.textContent = minimized ? "□" : "_";
      };

      const applyVisibility = (visible) => {
        hud.style.display = visible ? "block" : "none";
        if (visible) refreshStatus();
      };

      if (typeof chrome !== "undefined" && chrome.storage?.local) {
        chrome.storage.local.get(["ks_kebutuhan_hud_visible"], (res) => {
          applyVisibility(Boolean(res?.ks_kebutuhan_hud_visible));
        });
        chrome.storage.onChanged.addListener((changes, area) => {
          if (area === "local" && changes.ks_kebutuhan_hud_visible) {
            applyVisibility(Boolean(changes.ks_kebutuhan_hud_visible.newValue));
          }
        });
      }

      document.getElementById("ks-keb-close").onclick = () => {
        applyVisibility(false);
        if (typeof chrome !== "undefined" && chrome.storage?.local) {
          chrome.storage.local.set({ ks_kebutuhan_hud_visible: false });
        }
      };

      updateHUDView();
    }

    function init() {
      createHUD();
      if (pollTimer) clearInterval(pollTimer);
      pollTimer = setInterval(() => {
        if (kebConfig.enabled) {
          runNeedCycle(false);
        }
      }, 15000);
    }

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", init);
    } else {
      init();
    }

    return {
      CHARACTER_NEEDS,
      OJOL_NEEDS,
      ALL_NEEDS,
      DEFAULT_THRESHOLDS,
      parseKebutuhanResponse,
      parseOjolBarsResponse,
      evaluateAllKebutuhan,
      solveNampanPicks,
      solveFotoShots,
      solveGymHolds,
      pickBestShopItem,
      fulfillOjolNeed,
      fulfillCharacterNeed
    };
  }

  return {
    CHARACTER_NEEDS,
    OJOL_NEEDS,
    ALL_NEEDS,
    DEFAULT_THRESHOLDS,
    parseKebutuhanResponse,
    parseOjolBarsResponse,
    evaluateAllKebutuhan,
    solveNampanPicks,
    solveFotoShots,
    solveGymHolds,
    pickBestShopItem
  };
});
