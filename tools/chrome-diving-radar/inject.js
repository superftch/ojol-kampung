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

    if (!window.__KS_SCENE_INSTANCE || !window.__KS_MANCING_INSTANCE || !window.__KS_VILLAGE_INSTANCE) {
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

  // 3d. Direct Stick & Geledah Handler untuk TPU & Rumah Mbah Rukmi
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
    autoChain: true
  };

  window.addEventListener("ks_autopilot_command", (e) => {
    const cmd = e.detail;
    if (cmd.action === "start") {
      autopilot.active = true;
      autopilot.target = cmd.target;
      autopilot.autoOpen = cmd.autoOpen !== false;
      autopilot.autoChain = cmd.autoChain !== false;
      console.log("[DivingAutopilot] Start towards kerang #", cmd.target.i);
      window.dispatchEvent(new CustomEvent("ks_autopilot_status", {
        detail: { active: true, target: cmd.target }
      }));
    } else if (cmd.action === "stop") {
      stopAutopilot("manual_stop");
    }
  });

  function stopAutopilot(reason = "stopped") {
    if (!autopilot.active) return;
    autopilot.active = false;
    const lastTarget = autopilot.target;
    autopilot.target = null;

    if (window.__KS_SCENE_INSTANCE) {
      try {
        window.__KS_SCENE_INSTANCE.setGerak(0, 0);
        window.__KS_SCENE_INSTANCE.setTegak(0);
      } catch (e) {}
    }

    console.log("[DivingAutopilot] Stopped:", reason);
    window.dispatchEvent(new CustomEvent("ks_autopilot_status", {
      detail: { active: false, reason, target: lastTarget }
    }));
  }

  // Keyboard cancel
  window.addEventListener("keydown", (e) => {
    if (autopilot.active && ["KeyW", "KeyA", "KeyS", "KeyD", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Space"].includes(e.code)) {
      stopAutopilot("user_input");
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

  function triggerOpenShell(target) {
    console.log("[DivingAutopilot] Arrived at kerang #", target.i, "- opening...");

    if (window.__KS_SCENE_INSTANCE) {
      try {
        window.__KS_SCENE_INSTANCE.setGerak(0, 0);
        window.__KS_SCENE_INSTANCE.setTegak(0);
      } catch (e) {}
    }

    setTimeout(() => {
      const btn = document.querySelector('[data-testid="diving-kerang"]');
      if (btn && !btn.disabled) {
        btn.click();
      } else if (window.__KS_SCENE_INSTANCE && typeof window.__KS_SCENE_INSTANCE.bukaKerang === "function") {
        window.__KS_SCENE_INSTANCE.bukaKerang(target.i);
      }

      window.dispatchEvent(new CustomEvent("ks_shell_opened_auto", {
        detail: {
          kerang: target,
          autoChain: autopilot.autoChain
        }
      }));
    }, 300);
  }

  // Loop Navigasi Auto-Pilot (50ms)
  setInterval(() => {
    if (!autopilot.active || !autopilot.target || !window.__KS_SCENE_INSTANCE) return;

    try {
      const sc = window.__KS_SCENE_INSTANCE;
      if (!sc.p) return;

      const px = sc.p.x;
      const pz = sc.p.z;
      const py = sc.p.y;
      const pd = Math.max(0, -py - 0.35);

      const target = autopilot.target;
      const dx = target.x - px;
      const dz = target.z - pz;
      const dd = target.d - pd;
      const distXZ = Math.hypot(dx, dz);
      const dist3D = Math.hypot(distXZ, dd);

      // Jangkauan buka kerang aman: <= 2.8 meter
      if (dist3D <= 2.8) {
        const reachedTarget = target;
        stopAutopilot("arrived");

        if (autopilot.autoOpen) {
          triggerOpenShell(reachedTarget);
        }
        return;
      }

      // 1. Arahkan hadap pemain dan yaw kamera langsung ke kerang target
      const targetBearing = Math.atan2(dx, dz);
      sc.yaw = targetBearing;
      sc.hadap = targetBearing;

      // 2. Berenang maju
      sc.setGerak(0, 1);

      // 3. Atur kedalaman renang
      if (dd > 1.0) {
        sc.setTegak(-1); // turun lebih dalam
      } else if (dd < -1.0) {
        sc.setTegak(1);  // naik lebih cetek
      } else {
        sc.setTegak(0);
      }

      // 4. Highlight mesh kerang target agar selalu kelihatan dan berkilau di Three.js!
      if (Array.isArray(sc.kerang) && sc.kerang[target.i]) {
        const item = sc.kerang[target.i];
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
