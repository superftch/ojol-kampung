// KampungSebelah Diving Radar - Main World Injector (v1.8.0)
// Mengambil langsung objek Kerang 3D asli dari Three.js Scene Game & Auto-Pilot Langsung

(function () {
  console.log("[DivingRadar] Injector v1.8.0 initializing in page context...");

  window.__KS_DIVING_DATA = {
    x: 0,
    z: -26,
    kedalaman: 0.9,
    arah: 0,
    yaw: Math.PI,
    pitch: 0,
    valid: false,
    source: "none"
  };

  let realKerangBroadcasted = false;
  let lastOpenedSignature = "";

  function broadcastRealKerang(sc) {
    if (!sc || !Array.isArray(sc.kerang) || sc.kerang.length === 0) return;

    try {
      const realList = sc.kerang.map(item => {
        const k = item.k || {};
        const d = typeof k.d === "number" ? k.d : Math.abs(item.y || 0);

        let kategori = "kosong";
        let labelKategori = "Cetek (<18m) - Pasti Kosong";
        let badgeColor = "#718096";

        if (d >= 40) {
          kategori = "langka";
          labelKategori = "Palung (≥40m) - Mutiara Langka 300 Koin!";
          badgeColor = "#b794f4";
        } else if (d >= 18) {
          kategori = "biasa";
          labelKategori = "Dalam (≥18m) - Mutiara Biasa 100 Koin";
          badgeColor = "#ecc94b";
        }

        return {
          i: k.i,
          x: Math.round((k.x ?? 0) * 10) / 10,
          z: Math.round((k.z ?? 0) * 10) / 10,
          d: Math.round(d * 10) / 10,
          y: item.y,
          dibuka: !!item.dibuka,
          kategori,
          labelKategori,
          badgeColor
        };
      });

      lastOpenedSignature = sc.kerang.map(k => k.dibuka ? "1" : "0").join("");
      window.__KS_REAL_KERANG = realList;
      window.dispatchEvent(new CustomEvent("ks_real_kerang_loaded", {
        detail: realList
      }));
      realKerangBroadcasted = true;
      console.log("[DivingRadar] Broadcasted", realList.length, "real 3D shells (opened sig:", lastOpenedSignature.replace(/0/g, "").length, ")");
    } catch (e) {
      console.warn("[DivingRadar] Failed to extract real shells:", e);
    }
  }

  function checkAndBroadcastKerang(sc) {
    if (!sc || !Array.isArray(sc.kerang) || sc.kerang.length === 0) return;
    const sig = sc.kerang.map(k => k.dibuka ? "1" : "0").join("");
    if (!realKerangBroadcasted || sig !== lastOpenedSignature) {
      broadcastRealKerang(sc);
    }
  }

  // 1. Hook Object.prototype.keadaan & Object.prototype.posisi & tandaiBuka
  try {
    Object.defineProperty(Object.prototype, "keadaan", {
      configurable: true,
      enumerable: false,
      get() {
        return this.__ks_keadaan_fn;
      },
      set(fn) {
        this.__ks_keadaan_fn = function (...args) {
          const res = fn.apply(this, args);
          try {
            window.__KS_SCENE_INSTANCE = this;
            if (res && typeof res.x === "number" && typeof res.z === "number") {
              window.__KS_DIVING_DATA.x = res.x;
              window.__KS_DIVING_DATA.z = res.z;
              window.__KS_DIVING_DATA.kedalaman = typeof res.kedalaman === "number" ? res.kedalaman : (res.d || 0);
              window.__KS_DIVING_DATA.arah = typeof res.arah === "number" ? res.arah : 0;
              window.__KS_DIVING_DATA.yaw = typeof this.yaw === "number" ? this.yaw : res.arah;
              window.__KS_DIVING_DATA.pitch = typeof this.pitch === "number" ? this.pitch : 0;
              window.__KS_DIVING_DATA.valid = true;
              window.__KS_DIVING_DATA.source = "keadaan";
            }
            if (this.kerang) {
              checkAndBroadcastKerang(this);
            }
          } catch (e) {}
          return res;
        };
      }
    });

    Object.defineProperty(Object.prototype, "posisi", {
      configurable: true,
      enumerable: false,
      get() {
        return this.__ks_posisi_fn;
      },
      set(fn) {
        this.__ks_posisi_fn = function (...args) {
          const res = fn.apply(this, args);
          try {
            window.__KS_SCENE_INSTANCE = this;
            if (res && typeof res.x === "number" && typeof res.z === "number") {
              window.__KS_DIVING_DATA.x = res.x;
              window.__KS_DIVING_DATA.z = res.z;
              window.__KS_DIVING_DATA.kedalaman = typeof res.kedalaman === "number" ? res.kedalaman : 0;
              window.__KS_DIVING_DATA.arah = typeof res.arah === "number" ? res.arah : 0;
              window.__KS_DIVING_DATA.yaw = typeof this.yaw === "number" ? this.yaw : res.arah;
              window.__KS_DIVING_DATA.pitch = typeof this.pitch === "number" ? this.pitch : 0;
              window.__KS_DIVING_DATA.valid = true;
              window.__KS_DIVING_DATA.source = "posisi";
            }
            if (typeof res.h === "number" || this.perahu) {
              const mancingData = {
                x: res.x,
                z: res.z,
                h: typeof res.h === "number" ? res.h : 0,
                laju: typeof res.laju === "number" ? res.laju : 0,
                titik: Array.isArray(this.titik) ? this.titik : []
              };
              window.__KS_MANCING_DATA = mancingData;
              window.dispatchEvent(new CustomEvent("ks_mancing_data_update", {
                detail: mancingData
              }));
            }
            if (this.kerang) {
              checkAndBroadcastKerang(this);
            }
          } catch (e) {}
          return res;
        };
      }
    });

    Object.defineProperty(Object.prototype, "tandaiBuka", {
      configurable: true,
      enumerable: false,
      get() {
        return this.__ks_tandaibuka_fn;
      },
      set(fn) {
        this.__ks_tandaibuka_fn = function (...args) {
          const res = fn.apply(this, args);
          try {
            if (this.kerang) checkAndBroadcastKerang(this);
          } catch (e) {}
          return res;
        };
      }
    });

    Object.defineProperty(Object.prototype, "hasilKerang", {
      configurable: true,
      enumerable: false,
      get() {
        return this.__ks_hasilkerang_fn;
      },
      set(fn) {
        this.__ks_hasilkerang_fn = function (...args) {
          const res = fn.apply(this, args);
          try {
            if (this.kerang) checkAndBroadcastKerang(this);
          } catch (e) {}
          return res;
        };
      }
    });

    // 1c. Hook TPU Scene (Rumah Mbah Rukmi & Cari Pusaka)
    Object.defineProperty(Object.prototype, "keadaanUsil", {
      configurable: true,
      enumerable: false,
      get() {
        return this.__ks_keadaan_usil_fn;
      },
      set(fn) {
        this.__ks_keadaan_usil_fn = function (...args) {
          const res = fn.apply(this, args);
          try {
            window.__KS_TPU_INSTANCE = this;
            if (res && typeof res.x === "number" && typeof res.y === "number") {
              const tpuData = {
                x: res.x,
                y: res.y,
                yaw: typeof res.yaw === "number" ? res.yaw : 0,
                diDalam: !!res.diDalam,
                sibuk: !!res.sibuk,
                jam: res.jam,
                terang: res.terang,
                geledahId: this.geledahId || null,
                bukaK: this.bukaK || 0
              };
              window.__KS_TPU_DATA = tpuData;
              window.dispatchEvent(new CustomEvent("ks_tpu_data_update", {
                detail: tpuData
              }));
            }
          } catch (e) {}
          return res;
        };
      }
    });

    // 1d. Hook Village 3D Map (Peta Desa & Auto-Ojol Mode Kendarai)
    Object.defineProperty(Object.prototype, "walkPose", {
      configurable: true,
      enumerable: false,
      get() {
        return this.__ks_walkpose_fn;
      },
      set(fn) {
        this.__ks_walkpose_fn = function (...args) {
          window.__KS_VILLAGE_INSTANCE = this;
          return fn.apply(this, args);
        };
      }
    });

    Object.defineProperty(Object.prototype, "setWalkNav", {
      configurable: true,
      enumerable: false,
      get() {
        return this.__ks_setwalknav_fn;
      },
      set(fn) {
        this.__ks_setwalknav_fn = function (...args) {
          window.__KS_VILLAGE_INSTANCE = this;
          return fn.apply(this, args);
        };
      }
    });

    Object.defineProperty(Object.prototype, "setKemudi", {
      configurable: true,
      enumerable: false,
      get() {
        return this.__ks_setkemudi_fn;
      },
      set(fn) {
        this.__ks_setkemudi_fn = function (...args) {
          window.__KS_VILLAGE_INSTANCE = this;
          return fn.apply(this, args);
        };
      }
    });
  } catch (e) {
    console.warn("[DivingRadar] Prototype hook error:", e);
  }

  // 2. React Fiber Scanner Fallback
  function scanReactFiber() {
    if (window.__KS_SCENE_INSTANCE && window.__KS_MANCING_INSTANCE && window.__KS_TPU_INSTANCE && window.__KS_VILLAGE_INSTANCE) return;

    try {
      const candidates = [
        document.querySelector('[data-testid="walk-kemudi"]'),
        document.querySelector('[data-testid="kemudi-go"]'),
        document.querySelector('[data-testid="kemudi-putar"]'),
        document.querySelector('[data-testid="walk-nav"]'),
        document.querySelector('div[aria-label*="Peta kampung"]'),
        document.querySelector('[data-testid="walk-card"]'),
        document.querySelector('[data-testid="pancing-canvas"]'),
        document.querySelector('[data-testid="pancing"]'),
        document.querySelector('[data-testid="pancing-sonar"]'),
        document.querySelector('[data-testid="pancing-gulung"]'),
        document.querySelector('[data-testid="pancing-celup"]'),
        document.querySelector('[data-testid="pancing-lempar"]'),
        document.querySelector('[data-testid="diving-dalam"]'),
        document.querySelector('[data-testid="diving-kerang-dekat"]'),
        document.querySelector('[data-testid="diving-oksigen"]'),
        document.querySelector('[data-testid="jelajah-tpu"]'),
        document.querySelector('[data-testid="tpu-canvas"]'),
        document.querySelector('canvas')
      ];

      for (let el of candidates) {
        if (!el) continue;
        const key = Object.keys(el).find(k => k.startsWith("__reactFiber$") || k.startsWith("__reactInternalInstance$"));
        if (!key) continue;

        let fiber = el[key];
        let depth = 0;
        while (fiber && depth++ < 40) {
          let hook = fiber.memoizedState;
          while (hook) {
            const s = hook.memoizedState;
            if (s && s.current) {
              const inst = s.current;
              // 1. Diving Scene Instance
              if (!window.__KS_SCENE_INSTANCE && inst.p && typeof inst.p.x === "number") {
                window.__KS_SCENE_INSTANCE = inst;
                window.__KS_DIVING_DATA.x = inst.p.x;
                window.__KS_DIVING_DATA.z = inst.p.z;
                window.__KS_DIVING_DATA.kedalaman = Math.max(0, -inst.p.y - 0.35);
                window.__KS_DIVING_DATA.arah = inst.hadap || 0;
                window.__KS_DIVING_DATA.yaw = typeof inst.yaw === "number" ? inst.yaw : (inst.hadap || 0);
                window.__KS_DIVING_DATA.valid = true;
                window.__KS_DIVING_DATA.source = "fiber_ref";
                broadcastRealKerang(inst);
              }
              // 2. Mancing Ship Engine (Class H) Instance
              if (!window.__KS_MANCING_INSTANCE && typeof inst.posisi === "function" && (inst.perahu || typeof inst.laju === "number" || typeof inst.h === "number")) {
                window.__KS_MANCING_INSTANCE = inst;
                const pos = inst.posisi();
                const mancingData = {
                  x: pos.x,
                  z: pos.z,
                  h: pos.h,
                  laju: pos.laju,
                  titik: Array.isArray(inst.titik) ? inst.titik : []
                };
                window.__KS_MANCING_DATA = mancingData;
                window.dispatchEvent(new CustomEvent("ks_mancing_data_update", {
                  detail: mancingData
                }));
                console.log("[DivingRadar] Mancing Ship Engine hooked successfully via Fiber!", mancingData);
              }
              // 3. TPU Scene Instance
              if (!window.__KS_TPU_INSTANCE && inst.me && typeof inst.me.x === "number") {
                window.__KS_TPU_INSTANCE = inst;
                const tpuData = {
                  x: inst.me.x,
                  y: inst.me.y,
                  yaw: typeof inst.yaw === "number" ? inst.yaw : 0,
                  geledahId: inst.geledahId || null,
                  bukaK: inst.bukaK || 0
                };
                window.__KS_TPU_DATA = tpuData;
                window.dispatchEvent(new CustomEvent("ks_tpu_data_update", {
                  detail: tpuData
                }));
                console.log("[DivingRadar] TPU Scene Instance hooked successfully via Fiber!", tpuData);
              }
              // 4. Village Scene Renderer Instance (Peta 3D Desa & Auto-Ojol Kendara)
              if (!window.__KS_VILLAGE_INSTANCE && inst && (
                typeof inst.setKemudi === "function" ||
                (inst.kind === "three" && inst.walk) ||
                (typeof inst.walkPose === "function" && inst.scene)
              )) {
                window.__KS_VILLAGE_INSTANCE = inst;
                console.log("[AutoOjol] Village 3D Scene Instance hooked via Fiber!", inst);
              }
            }
            hook = hook.next;
          }
          fiber = fiber.return;
        }
      }
    } catch (e) {}
  }

  // 3. Polling loop untuk sinkronisasi live data (50ms)
  setInterval(() => {
    // 3a. Diving scene live update
    if (window.__KS_SCENE_INSTANCE) {
      try {
        const sc = window.__KS_SCENE_INSTANCE;
        if (sc.p) {
          window.__KS_DIVING_DATA.x = sc.p.x;
          window.__KS_DIVING_DATA.z = sc.p.z;
          window.__KS_DIVING_DATA.kedalaman = Math.max(0, -sc.p.y - 0.35);
          window.__KS_DIVING_DATA.arah = typeof sc.hadap === "number" ? sc.hadap : (sc.yaw || 0);
          window.__KS_DIVING_DATA.yaw = typeof sc.yaw === "number" ? sc.yaw : (sc.hadap || 0);
          window.__KS_DIVING_DATA.valid = true;
          window.__KS_DIVING_DATA.source = "direct_scene";
        }
        if (sc.kerang) {
          checkAndBroadcastKerang(sc);
        }
      } catch (e) {}
    }

    // 3b. Mancing ship engine live update
    if (window.__KS_MANCING_INSTANCE) {
      try {
        const mInst = window.__KS_MANCING_INSTANCE;
        const pos = mInst.posisi();
        const mData = {
          x: pos.x,
          z: pos.z,
          h: pos.h,
          laju: pos.laju,
          titik: Array.isArray(mInst.titik) ? mInst.titik : (window.__KS_MANCING_DATA?.titik || [])
        };
        window.__KS_MANCING_DATA = mData;
        window.dispatchEvent(new CustomEvent("ks_mancing_data_update", {
          detail: mData
        }));
      } catch (e) {}
    }

    // 3c. TPU scene live update
    if (window.__KS_TPU_INSTANCE) {
      try {
        const tInst = window.__KS_TPU_INSTANCE;
        if (tInst.me) {
          const tpuData = {
            x: tInst.me.x,
            y: tInst.me.y,
            yaw: typeof tInst.yaw === "number" ? tInst.yaw : 0,
            geledahId: tInst.geledahId || null,
            bukaK: tInst.bukaK || 0
          };
          window.__KS_TPU_DATA = tpuData;
          window.dispatchEvent(new CustomEvent("ks_tpu_data_update", {
            detail: tpuData
          }));
        }
      } catch (e) {}
    }

    if (!window.__KS_SCENE_INSTANCE || !window.__KS_MANCING_INSTANCE || !window.__KS_TPU_INSTANCE || !window.__KS_VILLAGE_INSTANCE) {
      scanReactFiber();
    }

    window.dispatchEvent(new CustomEvent("ks_diving_tick", {
      detail: window.__KS_DIVING_DATA
    }));
  }, 50);

  // 3c. Direct Engine Steering Handler untuk Kapal Mancing
  window.addEventListener("ks_mancing_steer", (e) => {
    const { gas, belok } = e.detail || {};
    const mInst = window.__KS_MANCING_INSTANCE;
    if (mInst) {
      try {
        if (typeof mInst.setInput === "function") {
          mInst.setInput({ gas: gas || 0, belok: belok || 0 });
        }
        if (mInst.keys) {
          if (gas > 0) mInst.keys.add("w");
          else mInst.keys.delete("w");

          if (belok > 0) {
            mInst.keys.add("a");
            mInst.keys.delete("d");
          } else if (belok < 0) {
            mInst.keys.add("d");
            mInst.keys.delete("a");
          } else {
            mInst.keys.delete("a");
            mInst.keys.delete("d");
          }
        }
      } catch (err) {}
    }
  });

  // 3d. Direct Stick, Teleport & Geledah Handler untuk TPU & Rumah Mbah Rukmi
  window.addEventListener("ks_tpu_set_stick", (e) => {
    const { turn, forward } = e.detail || {};
    const tInst = window.__KS_TPU_INSTANCE;
    if (tInst) {
      try {
        if (typeof tInst.setStick === "function") {
          tInst.setStick(turn || 0, forward || 0);
        }
      } catch (err) {}
    }
  });

  window.addEventListener("ks_tpu_teleport", (e) => {
    const { x, y, h } = e.detail || {};
    const tInst = window.__KS_TPU_INSTANCE;
    if (tInst && typeof tInst.teleport === "function" && typeof x === "number" && typeof y === "number") {
      try {
        tInst.teleport(x, y, typeof h === "number" ? h : null);
      } catch (err) {}
    }
  });

  window.addEventListener("ks_tpu_geledah", (e) => {
    const { id } = e.detail || {};
    const tInst = window.__KS_TPU_INSTANCE;
    if (tInst) {
      try {
        if (typeof tInst.geledah === "function") {
          tInst.geledah(id);
        }
      } catch (err) {}
    }
  });

  // 4. Fitur Auto-Pilot Berenang & Buka Otomatis
  let autopilot = {
    active: false,
    target: null,
    autoOpen: true,
    autoChain: true,
    phase: "swim",      // swim | open
    opener: null,       // diving-open.js: mesin buka kerang untuk target aktif
    lockedSince: 0,
    lastSnapAt: 0,
    guardUntil: 0       // penjaga hiu aktif sampai waktu ini (performance.now) walau auto-pilot jeda
  };

  // ---- Log diagnostik ----
  // Buffer cincin 400 entri. Salin lewat tombol "Salin Log" di panel radar, atau
  // panggil window.__KS_DIVING_DUMP() di konsol. Snapshot dicatat saat berhenti, nyangkut,
  // tiba, klik buka, dan tiap 5 detik selama auto-pilot aktif.
  const DLOG = { buf: [], max: 400 };

  function r1(n) { return typeof n === "number" && isFinite(n) ? Math.round(n * 10) / 10 : n; }

  function dlog(type, data) {
    DLOG.buf.push(Object.assign({ t: Math.round(performance.now()), at: new Date().toISOString().slice(11, 23), type }, data || {}));
    if (DLOG.buf.length > DLOG.max) DLOG.buf.shift();
  }

  function snapshot(sc, target) {
    try {
      const p = sc.p;
      const OPEN = window.__KS_DIVING_OPEN;
      const item = target && Array.isArray(sc.kerang) ? sc.kerang[target.i] : null;
      const rocks = sc.dunia && sc.dunia.batuBesar;
      let nearRocks = [];
      if (Array.isArray(rocks)) {
        nearRocks = rocks
          .filter(r => r && typeof r.x === "number")
          .map(r => ({ gap: Math.hypot(p.x - r.x, p.y - r.y, p.z - r.z) - r.r, x: r.x, y: r.y, z: r.z, r: r.r }))
          .sort((a, b) => a.gap - b.gap)
          .slice(0, 2)
          .map(r => ({ gap: r1(r.gap), x: r1(r.x), y: r1(r.y), z: r1(r.z), r: r1(r.r) }));
      }
      const nv = navigator;
      return {
        pos: { x: r1(p.x), y: r1(p.y), z: r1(p.z) },
        yaw: r1(sc.yaw), pitch: r1(sc.pitch),
        speed: sc.v ? { h: r1(Math.hypot(sc.v.x, sc.v.z)), v: r1(sc.v.y) } : null,
        floor: sc.dunia && typeof sc.dunia.tinggi === "function" ? r1(sc.dunia.tinggi(p.x, p.z)) : null,
        flags: { kunci: !!sc.kunci, tertangkap: !!sc.tertangkap, permukaan: !!sc.permukaan, membuka: !!sc.membuka },
        page: { vis: document.visibilityState, focus: document.hasFocus() },
        target: target ? {
          i: target.i, x: r1(target.x), z: r1(target.z), d: r1(target.d),
          itemY: item ? r1(item.y) : null,
          dibuka: item ? !!item.dibuka : null,
          gameDist: OPEN && item ? r1(OPEN.gameDistance(p, target, item)) : null,
          kerangDekat: typeof sc.kerangDekat === "function" ? sc.kerangDekat() : null
        } : null,
        nav: nv ? {
          stuck: nv.state.stuckLevel, relax: nv.state.relax,
          best: r1(nv.state.bestDist), mode: lastAvoidMode
        } : null,
        phase: autopilot.phase,
        rocks: nearRocks
      };
    } catch (err) {
      return { err: String(err) };
    }
  }

  function dumpText() {
    const head = `KS Diving log | ${new Date().toISOString()} | ext 2.6.0 | ${location.href}\n`;
    return head + DLOG.buf.map(e => JSON.stringify(e)).join("\n");
  }

  window.__KS_DIVING_DUMP = dumpText;
  window.addEventListener("ks_diving_dump", () => {
    window.dispatchEvent(new CustomEvent("ks_diving_dump_result", { detail: { text: dumpText() } }));
  });

  document.addEventListener("visibilitychange", () => {
    dlog("visibility", { state: document.visibilityState, active: autopilot.active });
    console.log("[DivingAutopilot] Tab", document.visibilityState, autopilot.active ? "(auto-pilot aktif)" : "");
  });
  window.addEventListener("blur", () => dlog("blur", { active: autopilot.active }));
  window.addEventListener("focus", () => dlog("focus", { active: autopilot.active }));

  // Navigator anti-nyangkut (diving-avoid.js): hindari batu, waypoint bila kerang
  // terkurung batu, pemulihan nyangkut, dan watchdog kemajuan. Dimuat terpisah,
  // jadi dibuat saat pertama dipakai.
  let navigator = null;
  let lastAvoidMode = "none";

  function getNavigator() {
    if (!navigator && window.__KS_DIVING_AVOID) {
      navigator = window.__KS_DIVING_AVOID.createNavigator();
    }
    return navigator;
  }

  // Perilaku ala manusia (diving-human.js): goyang arah, jeda di jalan, jeda sebelum buka.
  let human = null;
  let motion = null;
  let humanizeEnabled = true;

  function getHuman() {
    if (!human && window.__KS_DIVING_HUMAN) human = window.__KS_DIVING_HUMAN.createHuman();
    return human;
  }

  window.addEventListener("ks_humanize_toggle", (e) => {
    humanizeEnabled = !!(e.detail && e.detail.enabled);
    if (!humanizeEnabled) motion = null;
  });

  function resetNav() {
    if (navigator) navigator.reset();
    motion = null;
  }

  // Jarak permukaan batu terdekat dari pemain (meter); Infinity bila tidak ada batu.
  function nearestRockGap(sc, px, py, pz) {
    const rocks = sc.dunia && sc.dunia.batuBesar;
    if (!Array.isArray(rocks)) return Infinity;
    let best = Infinity;
    for (let i = 0; i < rocks.length; i++) {
      const r = rocks[i];
      if (!r || typeof r.x !== "number") continue;
      const g = Math.hypot(px - r.x, py - r.y, pz - r.z) - r.r;
      if (g < best) best = g;
    }
    return best;
  }

  function reportAvoid(mode) {
    if (lastAvoidMode === mode) return;
    dlog("mode", { from: lastAvoidMode, to: mode });
    lastAvoidMode = mode;
    window.dispatchEvent(new CustomEvent("ks_autopilot_avoid", { detail: { mode } }));
  }

  // Kabur dari hiu (diving-shark.js). Hiu memburu hanya di kedalaman > 6 m, jadi jalan aman
  // satu-satunya adalah naik. Navigator kedua dipakai hanya untuk menghindari batu saat kabur,
  // supaya status nyangkut/kemajuan navigator utama tidak terganggu.
  let shark = null;
  let fleeNav = null;
  let lastSharkMode = "clear";

  function getShark() {
    if (!shark && window.__KS_DIVING_SHARK) shark = window.__KS_DIVING_SHARK.createShark();
    return shark;
  }

  function getFleeNav() {
    if (!fleeNav && window.__KS_DIVING_AVOID) fleeNav = window.__KS_DIVING_AVOID.createNavigator();
    return fleeNav;
  }

  function reportShark(mode, res) {
    if (lastSharkMode === mode) return;
    lastSharkMode = mode;
    window.dispatchEvent(new CustomEvent("ks_autopilot_shark", {
      detail: { mode, dist: res && res.dist, depth: res && res.depth }
    }));
  }

  // Baca hiu dari scene game (hiuS, sama dengan yang dipakai game) dan indikator merah di HUD game.
  function readShark(sc) {
    let hiu = null;
    const h = sc.hiuS;
    if (h && h.aktif && h.pergi <= 0 && h.p && typeof h.p.x === "number") {
      hiu = {
        p: { x: h.p.x, y: h.p.y, z: h.p.z },
        awas: !!h.awas, memburu: !!h.memburu, sergap: h.sergap > 0
      };
    } else if (!h && typeof sc.keadaan === "function") {
      // Cadangan bila hiuS tidak ada: keadaan().hiu hanya punya jarak dan sudut relatif kamera.
      try {
        const k = sc.keadaan();
        if (k && k.hiu && typeof k.hiu.jarak === "number") {
          const a = (typeof sc.yaw === "number" ? sc.yaw : 0) + (k.hiu.sudut || 0);
          hiu = {
            p: { x: sc.p.x + Math.sin(a) * k.hiu.jarak, y: sc.p.y, z: sc.p.z + Math.cos(a) * k.hiu.jarak },
            awas: !!k.hiu.awas, memburu: !!k.hiu.memburu, sergap: false
          };
        }
      } catch (e) {}
    }
    let domDanger = false;
    try {
      const el = document.querySelector('[data-testid="diving-hiu"][data-bahaya]');
      domDanger = !!el && !el.hasAttribute("data-aman");
    } catch (e) {}
    return { hiu, domDanger };
  }

  // Satu tick kabur/sembunyi. Hasil true bila tick ini sudah diurus (auto-pilot tidak lanjut).
  function sharkTick(sc, now) {
    const sh = getShark();
    if (!sh) return false;
    const { hiu, domDanger } = readShark(sc);
    const res = sh.assess({ now, pos: { x: sc.p.x, y: sc.p.y, z: sc.p.z }, hiu, domDanger });

    if (res.event) {
      const snapS = snapshot(sc, autopilot.target);
      dlog("shark", { event: res.event, mode: res.mode, dist: r1(res.dist), depth: r1(res.depth), domDanger, hiu: hiu ? { memburu: hiu.memburu, awas: hiu.awas, x: r1(hiu.p.x), y: r1(hiu.p.y), z: r1(hiu.p.z) } : null, snap: snapS });
      console.warn("[DivingAutopilot] Hiu:", res.event, "mode", res.mode, "jarak", r1(res.dist), "kedalaman", r1(res.depth));
      if (res.event === "flee_start") {
        const fn = getFleeNav();
        if (fn) fn.reset();
        // Jangan berhenti membuka kerang di tengah ancaman: batalkan, dekati lagi setelah aman.
        if (autopilot.phase === "open") {
          dlog("open_abort_shark", { target: autopilot.target && autopilot.target.i });
          autopilot.phase = "swim";
          autopilot.opener = null;
        }
      }
    }
    reportShark(res.mode, res);
    if (res.mode === "clear") return false;

    const nv = getNavigator();
    if (nv) nv.hold(now); // diam atau menyimpang karena hiu bukan nyangkut
    const cmd = sh.steer(res);

    if (res.mode === "flee") {
      let yaw = res.awayYaw !== null ? res.awayYaw : sc.yaw;
      let gx = 0;
      let gy = res.awayYaw !== null ? 1 : 0;
      const fn = res.awayYaw !== null ? getFleeNav() : null;
      if (fn) {
        // Titik tujuan 25 m ke arah menjauh dan dangkal; navigator hanya mengatur belokan menghindari batu.
        const p = sc.p;
        const out = fn.step({
          now,
          pos: { x: p.x, y: p.y, z: p.z },
          target: { i: -1, x: p.x + Math.sin(yaw) * 25, z: p.z + Math.cos(yaw) * 25, d: 3 },
          rocks: sc.dunia && sc.dunia.batuBesar,
          pitch: sc.pitch,
          surfaceY: sc.pen && typeof sc.pen.apung === "number" ? sc.pen.apung : undefined,
          floorFn: sc.dunia && typeof sc.dunia.tinggi === "function" ? (x, z) => sc.dunia.tinggi(x, z) : undefined
        });
        if (!out.stop) {
          yaw = out.yaw;
          gx = out.gerak.x;
          gy = out.gerak.y;
        }
      }
      if (typeof yaw === "number") {
        sc.yaw = yaw;
        sc.hadap = yaw;
      }
      sc.setGerak(gx, gy);
      sc.setTegak(cmd ? cmd.tegak : 1);
    } else {
      // Bersembunyi di zona aman: diam, jaga kedalaman 3-5 m.
      sc.setGerak(0, 0);
      sc.setTegak(cmd ? cmd.tegak : 0);
    }
    return true;
  }

  window.addEventListener("ks_autopilot_command", (e) => {
    const cmd = e.detail;
    if (cmd.action === "start") {
      if (typeof cmd.humanize === "boolean") {
        humanizeEnabled = cmd.humanize;
        if (!humanizeEnabled) motion = null;
      }
      autopilot.active = true;
      autopilot.target = cmd.target;
      autopilot.autoOpen = cmd.autoOpen !== false;
      autopilot.autoChain = cmd.autoChain !== false;
      autopilot.phase = "swim";
      autopilot.opener = null;
      autopilot.lockedSince = 0;
      autopilot.lastSnapAt = 0;
      resetNav();
      autopilot.guardUntil = 0;
      console.log("[DivingAutopilot] Start towards kerang #", cmd.target.i);
      const sc0 = window.__KS_SCENE_INSTANCE;
      dlog("start", { target: cmd.target.i, autoOpen: autopilot.autoOpen, autoChain: autopilot.autoChain, snap: sc0 && sc0.p ? snapshot(sc0, cmd.target) : null });
      window.dispatchEvent(new CustomEvent("ks_autopilot_status", {
        detail: { active: true, target: cmd.target }
      }));
    } else if (cmd.action === "stop") {
      stopAutopilot("manual_stop");
    }
  });

  function stopAutopilot(reason = "stopped", extra) {
    if (!autopilot.active) return;
    autopilot.active = false;
    const lastTarget = autopilot.target;
    autopilot.target = null;
    autopilot.phase = "swim";
    autopilot.opener = null;
    // Penjaga hiu tetap menyala selama jeda rantai, kecuali dihentikan pengguna atau dikunci game.
    const userStop = reason === "manual_stop" || reason === "user_input" || reason === "locked";
    autopilot.guardUntil = userStop ? 0 : performance.now() + 15000;
    if (userStop && shark) shark.reset();

    const sc = window.__KS_SCENE_INSTANCE;
    const snap = sc && sc.p ? snapshot(sc, lastTarget) : null;
    if (sc) {
      try {
        sc.setGerak(0, 0);
        sc.setTegak(0);
      } catch (e) {}
    }

    reportAvoid("none");
    reportShark("clear");
    dlog("stop", { reason, extra, snap });
    if (reason === "arrived") {
      console.log("[DivingAutopilot] Stopped:", reason);
    } else {
      // Alasan selain tiba selalu disertai snapshot supaya sebabnya bisa dibaca dari konsol.
      console.warn("[DivingAutopilot] Stopped:", reason, extra || "", snap ? JSON.stringify(snap) : "");
    }
    window.dispatchEvent(new CustomEvent("ks_autopilot_status", {
      detail: { active: false, reason, target: lastTarget }
    }));
  }

  // Keyboard cancel. Pintasan dengan Cmd/Ctrl/Alt (mis. Cmd+Opt+Panah untuk pindah tab)
  // bukan kemudi manual, jadi tidak membatalkan auto-pilot. Event buatan skrip
  // (isTrusted=false) juga diabaikan: hanya tombol fisik yang membatalkan.
  window.addEventListener("keydown", (e) => {
    if (!autopilot.active) return;
    if (e.metaKey || e.ctrlKey || e.altKey || !e.isTrusted) return;
    if (["KeyW", "KeyA", "KeyS", "KeyD", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Space"].includes(e.code)) {
      stopAutopilot("user_input", e.code);
    }
  });

  // Mancing Boat Steer Hook (Direct Three.js Scene Input)
  window.addEventListener("ks_mancing_steer", (e) => {
    const sc = window.__KS_SCENE_INSTANCE;
    if (!sc) return;
    const { gas, belok } = e.detail || {};
    try {
      if (typeof sc.setInput === "function") {
        sc.setInput({ gas: typeof gas === "number" ? gas : 0, belok: typeof belok === "number" ? belok : 0 });
      }
    } catch (err) {}
  });

  // Fase buka kerang. Pemain diam sampai game sendiri menandai kerang terbuka (dibuka=true),
  // klik tombol hanya bila tombol game benar-benar ada, dan kegagalan (server menolak,
  // klik diabaikan, menjauh) dicoba ulang dengan jeda. Hasil dilaporkan jujur:
  // sukses -> ks_shell_opened_auto; gagal -> stopAutopilot("open_failed"|"unreachable").
  function beginOpen(sc, target, now) {
    const OPEN = window.__KS_DIVING_OPEN;
    autopilot.phase = "open";
    if (!autopilot.opener) {
      autopilot.opener = humanizeEnabled
        ? OPEN.createOpener()
        : OPEN.createOpener({ cfg: { settle: [0, 0] } });
      autopilot.opener.begin(now, target.i);
      console.log("[DivingAutopilot] Arrived at kerang #", target.i, "- opening...");
      dlog("arrive", { target: target.i, snap: snapshot(sc, target) });
    } else {
      autopilot.opener.resume(now);
      dlog("arrive_again", { target: target.i });
    }
    try {
      sc.setGerak(0, 0);
      sc.setTegak(0);
    } catch (e) {}
  }

  function openTick(sc, target, item, gd, now) {
    const OPEN = window.__KS_DIVING_OPEN;
    const nv = getNavigator();
    if (nv) nv.hold(now);
    try {
      sc.setGerak(0, 0);
      sc.setTegak(0);
    } catch (e) {}

    const btn = document.querySelector('[data-testid="diving-kerang"]');
    const busy = !!(btn && btn.getAttribute("aria-busy") === "true");
    const act = autopilot.opener.tick(now, {
      dist: gd,
      busy,
      opened: !!(item && item.dibuka),
      buttonReady: !!(btn && !btn.disabled && !busy)
    });

    if (act.type === "wait") return;

    if (act.type === "click") {
      dlog("click", { target: target.i, attempt: act.attempt, snap: snapshot(sc, target) });
      console.log("[DivingAutopilot] Klik buka kerang #", target.i, "percobaan", act.attempt);
      btn.click();
      return;
    }

    if (act.type === "reapproach") {
      autopilot.phase = "swim";
      dlog("reapproach", { target: target.i, reason: act.reason, snap: snapshot(sc, target) });
      console.warn("[DivingAutopilot] Dekati kerang lagi:", act.reason);
      return;
    }

    if (act.type === "success") {
      const reached = autopilot.target;
      const chain = autopilot.autoChain;
      dlog("opened", { target: target.i, attempts: act.attempts });
      stopAutopilot("arrived");
      window.dispatchEvent(new CustomEvent("ks_shell_opened_auto", {
        detail: { kerang: reached, autoChain: chain, ok: true }
      }));
      return;
    }

    if (act.type === "fail") {
      stopAutopilot(act.reason, act.detail);
    }
  }

  // Loop Navigasi Auto-Pilot (50ms)
  setInterval(() => {
    // Jeda antar kerang (rantai): auto-pilot belum aktif lagi, tapi hiu tetap harus dihindari.
    if (!autopilot.active && autopilot.guardUntil > 0) {
      const sg = window.__KS_SCENE_INSTANCE;
      const nowG = performance.now();
      if (nowG > autopilot.guardUntil) {
        autopilot.guardUntil = 0;
        if (shark) shark.reset();
        reportShark("clear");
      } else if (sg && sg.p && !document.hidden && !sg.kunci && !sg.tertangkap) {
        try { sharkTick(sg, nowG); } catch (e) { console.warn("[DivingAutopilot] Error di penjaga hiu:", e); }
      }
      return;
    }
    if (!autopilot.active || !autopilot.target || !window.__KS_SCENE_INSTANCE) return;

    try {
      const sc = window.__KS_SCENE_INSTANCE;
      if (!sc.p) return;

      const now = performance.now();
      const OPEN = window.__KS_DIVING_OPEN;
      const target0 = autopilot.target;
      const item = Array.isArray(sc.kerang) ? sc.kerang[target0.i] : null;
      // Target navigator disetel agar jarak 3D-nya sama dengan jarak game (kerang.y + 0.3).
      // Tanpa ini "tiba" kita bisa meleset sampai 0.65 m dari jangkauan tombol buka (3.2 m).
      const target = OPEN && item ? OPEN.toNavTarget(target0, item) : target0;

      const px = sc.p.x;
      const pz = sc.p.z;
      const py = sc.p.y;
      const pd = Math.max(0, -py - 0.35);

      const dx = target.x - px;
      const dz = target.z - pz;
      const dd = target.d - pd;
      const distXZ = Math.hypot(dx, dz);
      const dist3D = Math.hypot(distXZ, dd);
      const gd = OPEN && item ? OPEN.gameDistance(sc.p, target0, item) : dist3D;

      // Log berkala (hanya ke buffer) untuk membaca perjalanan setelah kejadian.
      if (now - autopilot.lastSnapAt > 5000) {
        autopilot.lastSnapAt = now;
        dlog("tick", { snap: snapshot(sc, target0) });
      }

      const nvEarly = getNavigator();

      // Kerang sudah terbuka di game (mis. dibuka manual): selesai tanpa mengklik lagi.
      if (item && item.dibuka && autopilot.phase === "swim") {
        const reached = autopilot.target;
        const chain = autopilot.autoChain;
        dlog("already_open", { target: reached.i });
        stopAutopilot("arrived");
        window.dispatchEvent(new CustomEvent("ks_shell_opened_auto", {
          detail: { kerang: reached, autoChain: chain, ok: true }
        }));
        return;
      }

      // Input dikunci game (tertangkap hiu, sesi selesai): karakter memang tidak bergerak,
      // bukan nyangkut. Tahan pengukuran; berhenti hanya bila terkunci lama.
      if (sc.kunci || sc.tertangkap) {
        if (nvEarly) nvEarly.hold(now);
        if (!autopilot.lockedSince) {
          autopilot.lockedSince = now;
          dlog("locked", { kunci: !!sc.kunci, tertangkap: !!sc.tertangkap });
          console.warn("[DivingAutopilot] Game mengunci kontrol", sc.kunci ? "(kunci)" : "(tertangkap)");
        } else if (now - autopilot.lockedSince > 20000) {
          stopAutopilot("locked", sc.tertangkap ? "tertangkap" : "kunci");
        }
        return;
      }
      if (autopilot.lockedSince) {
        dlog("unlocked", { after: Math.round(now - autopilot.lockedSince) });
        autopilot.lockedSince = 0;
      }

      // Tab tersembunyi: game berhenti menggambar dan menggerakkan karakter. Posisi diam
      // saat itu bukan nyangkut, jadi pengukuran ditahan dan dilanjut saat tab kembali.
      if (document.hidden) {
        if (nvEarly) nvEarly.hold(now);
        return;
      }

      // Hiu: prioritas di atas semua (navigasi, buka kerang). Naik dan menjauh sampai aman.
      if (sharkTick(sc, now)) return;

      if (autopilot.phase === "open" && autopilot.opener) {
        openTick(sc, target0, item, gd, now);
        return;
      }

      // Tiba: jarak game <= 2.7 m (jangkauan tombol buka 3.2 m, margin 0.5 m).
      const arriveDist = OPEN ? OPEN.CFG.arriveDist : 2.8;
      if (gd <= arriveDist) {
        if (autopilot.autoOpen && OPEN) {
          beginOpen(sc, target0, now);
        } else {
          stopAutopilot("arrived");
        }
        return;
      }

      const nv = getNavigator();
      const hm = humanizeEnabled ? getHuman() : null;
      if (hm && !motion) motion = hm.createMotion();

      // Jeda "manusia" di jalan: diam sebentar sambil menoleh. Navigator diberi tahu supaya
      // diam ini tidak dihitung nyangkut atau tanpa kemajuan.
      if (nv && humanizeEnabled && motion && motion.paused(performance.now())) {
        const nowH = performance.now();
        nv.hold(nowH);
        const lookYaw = motion.hold(nowH);
        sc.yaw = lookYaw;
        sc.hadap = lookYaw;
        sc.setGerak(0, 0);
        sc.setTegak(0);
        reportAvoid("none");
        return;
      }
      if (!nv) {
        // Modul penghindar belum dimuat: berenang lurus seperti semula.
        sc.yaw = Math.atan2(dx, dz);
        sc.hadap = sc.yaw;
        sc.setGerak(0, 1);
        sc.setTegak(dd > 1.0 ? -1 : (dd < -1.0 ? 1 : 0));
        return;
      }

      // Navigator: hindari batu, waypoint bila kerang terkurung batu, pulihkan bila nyangkut.
      const out = nv.step({
        now: performance.now(),
        pos: { x: px, y: py, z: pz },
        target,
        rocks: sc.dunia && sc.dunia.batuBesar,
        pitch: sc.pitch,
        surfaceY: sc.pen && typeof sc.pen.apung === "number" ? sc.pen.apung : undefined,
        floorFn: sc.dunia && typeof sc.dunia.tinggi === "function" ? (x, z) => sc.dunia.tinggi(x, z) : undefined
      });

      if (out.stop) {
        // stopAutopilot mencatat alasan beserta snapshot ke konsol dan buffer log.
        stopAutopilot(out.stop, "relax=" + out.relax);
        return;
      }
      if (out.mode === "recover" && lastAvoidMode !== "recover") {
        const snapS = snapshot(sc, target0);
        dlog("stuck", { level: nv.state.stuckLevel, snap: snapS });
        console.warn("[DivingAutopilot] Stuck level", nv.state.stuckLevel, "- recovering", JSON.stringify(snapS));
      }

      reportAvoid(out.mode);

      // Arah ala manusia hanya saat jalur tenang: bukan menghindar/pulih, tidak ada batu
      // dalam 8 m, dan tidak sedang dalam pemulihan nyangkut. Selain itu arah navigator
      // dipakai apa adanya (perilaku keselamatan tidak diubah).
      let yaw = out.yaw;
      if (humanizeEnabled && motion) {
        const nowM = performance.now();
        const calm = (out.mode === "none" || out.mode === "direct") &&
          nv.state.stuckLevel === 0 && nowM >= nv.state.recoverUntil &&
          nearestRockGap(sc, px, py, pz) > 8;
        const mv = motion.step({
          now: nowM,
          desiredYaw: out.yaw,
          calm,
          canPause: calm,
          nearTarget: dist3D < 6
        });
        if (mv.startPause) {
          nv.hold(nowM);
          sc.setGerak(0, 0);
          sc.setTegak(0);
          return;
        }
        yaw = mv.yaw;
      }
      sc.yaw = yaw;
      sc.hadap = yaw;

      // Berenang maju + atur kedalaman
      sc.setGerak(out.gerak.x, out.gerak.y);
      sc.setTegak(out.tegak);

      // Highlight mesh kerang target agar selalu kelihatan dan berkilau di Three.js!
      if (item) {
        if (item.m && item.m.g) {
          item.m.g.visible = true; // Jangan di-cull oleh jarak
        }
        if (item.kilap) {
          item.kilap.visible = true;
        }
      }
    } catch (e) {
      console.warn("[DivingAutopilot] Error in tick:", e);
    }
  }, 50);

  // 5. Fitur Auto-Pilot Ojol Mode Kendarai (Pendekatan seperti Diving Autopilot)
  let ojolAutopilot = {
    active: false,
    lastX: null,
    lastY: null,
    stuckTicks: 0
  };

  window.addEventListener("ks_ojol_autopilot_command", (e) => {
    const cmd = e.detail || {};
    if (cmd.action === "start") {
      ojolAutopilot.active = true;
      ojolAutopilot.stuckTicks = 0;
      ojolAutopilot.lastX = null;
      ojolAutopilot.lastY = null;
      console.log("[AutoOjol] Autopilot started!");
      window.dispatchEvent(new CustomEvent("ks_ojol_autopilot_status", {
        detail: { active: true }
      }));
    } else if (cmd.action === "stop") {
      stopOjolAutopilot("manual_stop");
    }
  });

  function stopOjolAutopilot(reason = "stopped") {
    if (!ojolAutopilot.active) return;
    ojolAutopilot.active = false;
    const inst = window.__KS_VILLAGE_INSTANCE;
    if (inst) {
      try {
        if (inst.keys) inst.keys.delete("w");
        if (inst.walk && inst.walk.w) inst.walk.w.speed = 0;
        if (typeof inst.setKemudi === "function") inst.setKemudi("berhenti");
      } catch (e) {}
    }
    console.log("[AutoOjol] Autopilot stopped:", reason);
    window.dispatchEvent(new CustomEvent("ks_ojol_autopilot_status", {
      detail: { active: false, reason }
    }));
  }

  // Loop Navigasi Auto-Pilot Ojol (50ms, mengemudi WASD murni mengikuti rute jalan)
  setInterval(() => {
    if (!ojolAutopilot.active) return;

    try {
      const inst = window.__KS_VILLAGE_INSTANCE;
      if (!inst || !inst.walk || !inst.walk.w) return;

      // Matikan kemudi tile bawaan game agar tidak konflik / muter-muter
      if (inst.kemudiPakai) {
        if (typeof inst.setKemudiMode === "function") {
          try { inst.setKemudiMode(false); } catch (e) {}
        }
        inst.kemudiPakai = false;
      }
      if (inst.kemudi) inst.kemudi = null;

      const w = inst.walk.w;
      const nav = inst.nav || inst.kemudiTujuan?.nav;

      if (nav && nav.route && Array.isArray(nav.route.pts) && nav.route.pts.length > 0 && nav.route.to) {
        const pts = nav.route.pts;
        const to = nav.route.to;
        const curX = w.x;
        const curY = w.y;
        const distToFinal = Math.hypot(to.x - curX, to.y - curY);

        // Jika sampai di tujuan (< 1.4 petak - threshold resmi game t2.Y)
        if (distToFinal <= 1.4) {
          if (inst.keys) inst.keys.delete("w");
          w.speed = 0;
          window.dispatchEvent(new CustomEvent("ks_ojol_nav_tick", {
            detail: { curX, curY, distToFinal, to, arrived: true, hasRoute: true }
          }));
          return;
        }

        // 1. Cari segmen jalan terdekat di rute
        let activeSeg = 0;
        let minOff = 1e9;
        for (let i = 0; i < pts.length - 1; i++) {
          const pA = pts[i];
          const pB = pts[i + 1];
          const ux = pB.x - pA.x;
          const uy = pB.y - pA.y;
          const lenSq = ux * ux + uy * uy;
          const t = lenSq ? Math.max(0, Math.min(1, ((curX - pA.x) * ux + (curY - pA.y) * uy) / lenSq)) : 0;
          const off = Math.hypot(curX - (pA.x + ux * t), curY - (pA.y + uy * t));
          if (off < minOff - 1e-4) {
            minOff = off;
            activeSeg = i;
          }
        }

        // 2. Ikuti per checkpoint secara sekuensial (dilarang loncat/potong diagonal)
        let targetSeg = activeSeg;
        let pA = pts[targetSeg];
        let pB = pts[targetSeg + 1];
        let distToB = Math.hypot(pB.x - curX, pB.y - curY);

        // Jika sudah tiba di checkpoint tikungan (radius <= 0.5) dan masih ada checkpoint berikutnya
        if (distToB <= 0.5 && targetSeg + 1 < pts.length - 1) {
          targetSeg += 1;
          pA = pts[targetSeg];
          pB = pts[targetSeg + 1];
          distToB = Math.hypot(pB.x - curX, pB.y - curY);
        }

        // 3. Jaga posisi tetap di tengah aspal jalan (tidak menabrak rumah)
        const isVertical = Math.abs(pB.x - pA.x) < 0.1;
        const isHorizontal = Math.abs(pB.y - pA.y) < 0.1;
        let aimX = pB.x;
        let aimY = pB.y;

        if (isVertical) {
          if (Math.abs(curX - pB.x) > 0.25) {
            w.x = pB.x + Math.sign(curX - pB.x) * 0.25;
          }
        } else if (isHorizontal) {
          if (Math.abs(curY - pB.y) > 0.25) {
            w.y = pB.y + Math.sign(curY - pB.y) * 0.25;
          }
        }

        // 4. Hitung sudut kemudi dan belok halus ke arah checkpoint jalan berikutnya
        const dx = aimX - curX;
        const dy = aimY - curY;
        const targetBearing = Math.atan2(dx, dy);

        let diff = Math.atan2(Math.sin(targetBearing - w.heading), Math.cos(targetBearing - w.heading));
        const maxTurn = 0.35; // Putaran halus ~7 rad/detik
        if (Math.abs(diff) <= maxTurn) {
          w.heading = targetBearing;
        } else {
          w.heading += Math.sign(diff) * maxTurn;
        }

        if (inst.walk.obj) {
          inst.walk.obj.rotation.y = w.heading;
        }

        // Tahan tombol W untuk melaju di jalur jalan
        if (inst.keys) {
          inst.keys.add("w");
        }

        // 5. Deteksi & Penanganan Anti-Macet (Hanya dorong searah sumbu jalan)
        if (ojolAutopilot.lastX !== null && ojolAutopilot.lastY !== null) {
          const moved = Math.hypot(curX - ojolAutopilot.lastX, curY - ojolAutopilot.lastY);
          if (moved < 0.08) {
            ojolAutopilot.stuckTicks++;
            if (ojolAutopilot.stuckTicks >= 6) { // ~300ms tanpa pergerakan
              if (isVertical) {
                w.x = pB.x;
                w.y += Math.sign(dy || 1) * 0.35;
              } else if (isHorizontal) {
                w.y = pB.y;
                w.x += Math.sign(dx || 1) * 0.35;
              } else {
                const len = Math.hypot(dx, dy) || 1;
                w.x += (dx / len) * 0.35;
                w.y += (dy / len) * 0.35;
              }
              ojolAutopilot.stuckTicks = 0;
            }
          } else {
            ojolAutopilot.stuckTicks = 0;
          }
        }
        ojolAutopilot.lastX = curX;
        ojolAutopilot.lastY = curY;

        window.dispatchEvent(new CustomEvent("ks_ojol_nav_tick", {
          detail: {
            curX,
            curY,
            distToFinal,
            to,
            targetCheckpoint: pB,
            seg: targetSeg,
            totalSegments: pts.length - 1,
            arrived: false,
            hasRoute: true
          }
        }));
      } else {
        // Rute belum aktif atau sudah selesai
        if (inst.keys) inst.keys.delete("w");
        window.dispatchEvent(new CustomEvent("ks_ojol_nav_tick", {
          detail: { curX: w.x, curY: w.y, distToFinal: 0, hasRoute: false }
        }));
      }
    } catch (err) {
      console.warn("[AutoOjol] Error in navigation tick:", err);
    }
  }, 50);
})();
