// KampungSebelah - Sepak Bola / Futsal Main World Injector
// Mengaitkan langsung ke instance Stadion 3D & Input Controller pada [data-testid="futsal-layar"]
// Bekerja untuk Mode Latihan (FutsalLatihan) maupun Mode Live Liga/Tantangan/Uji Coba (FutsalLive).

(function () {
  console.log("[FutsalInject] Main world injector initialized");

  let cachedStadium = null;
  let cachedInput = null;
  let lastState = null;
  let wasActive = false;

  function isStadiumInstance(obj) {
    return (
      obj &&
      typeof obj === "object" &&
      typeof obj.arahLayar === "function" &&
      typeof obj.render === "function" &&
      obj.scene &&
      obj.camera
    );
  }

  function isInputRef(obj) {
    return (
      obj &&
      typeof obj === "object" &&
      typeof obj.jx === "number" &&
      typeof obj.jy === "number" &&
      obj.kunci instanceof Set
    );
  }

  function wrapStadium(stadium) {
    if (!stadium || stadium.__ks_futsal_wrapped) return;
    stadium.__ks_futsal_wrapped = true;
    const origRender = stadium.render.bind(stadium);
    stadium.render = function (state, dt) {
      if (state && state.bola && Array.isArray(state.pemain)) {
        lastState = state;
      }
      return origRender(state, dt);
    };
  }

  function scanFutsalFiber() {
    const el = document.querySelector('[data-testid="futsal-layar"]');
    if (!el) {
      cachedStadium = null;
      cachedInput = null;
      lastState = null;
      return false;
    }

    if (isStadiumInstance(cachedStadium) && isInputRef(cachedInput)) {
      return true;
    }

    try {
      const key = Object.keys(el).find(
        (k) => k.startsWith("__reactFiber$") || k.startsWith("__reactInternalInstance$")
      );
      if (!key) return false;

      let fiber = el[key];
      let depth = 0;
      while (fiber && depth++ < 35) {
        let hook = fiber.memoizedState;
        while (hook) {
          const s = hook.memoizedState;
          if (s && typeof s === "object" && "current" in s && s.current) {
            if (isStadiumInstance(s.current)) {
              cachedStadium = s.current;
              wrapStadium(cachedStadium);
            } else if (isInputRef(s.current)) {
              cachedInput = s.current;
            }
          }
          hook = hook.next;
        }
        if (cachedStadium && cachedInput) break;
        fiber = fiber.return;
      }
    } catch (err) {
      console.warn("[FutsalInject] Fiber scan error:", err);
    }

    return Boolean(cachedStadium);
  }

  function buildSnapshot() {
    const active = scanFutsalFiber();
    if (!active || !lastState) {
      return { active: false };
    }

    let arahLayar = { kananX: 1, kananZ: 0, atasX: 0, atasZ: -1 };
    try {
      if (cachedStadium && typeof cachedStadium.arahLayar === "function") {
        arahLayar = cachedStadium.arahLayar();
      }
    } catch (_) {}

    const myId = typeof cachedStadium?.opts?.sayaId === "number" ? cachedStadium.opts.sayaId : 1;

    return {
      active: true,
      myId,
      hasInput: Boolean(cachedInput),
      arahLayar,
      skor: Array.isArray(lastState.skor) ? [...lastState.skor] : [0, 0],
      sisa: typeof lastState.sisa === "number" ? lastState.sisa : 0,
      fase: lastState.fase || "main",
      faseT: typeof lastState.faseT === "number" ? lastState.faseT : 0,
      bola: lastState.bola
        ? {
            x: lastState.bola.x,
            y: lastState.bola.y,
            z: lastState.bola.z,
            vx: lastState.bola.vx,
            vz: lastState.bola.vz,
            pemilik: lastState.bola.pemilik,
            sentuh: lastState.bola.sentuh
          }
        : null,
      pemain: Array.isArray(lastState.pemain)
        ? lastState.pemain.map((p) => ({
            id: p.id,
            tim: p.tim,
            kiper: Boolean(p.kiper),
            manusia: Boolean(p.manusia),
            x: p.x,
            z: p.z,
            vx: p.vx,
            vz: p.vz,
            arah: p.arah,
            stamina: typeof p.stamina === "number" ? p.stamina : 1,
            tahan: typeof p.tahan === "number" ? p.tahan : 0,
            rebutT: typeof p.rebutT === "number" ? p.rebutT : 0,
            huyungT: typeof p.huyungT === "number" ? p.huyungT : 0
          }))
        : []
    };
  }

  window.addEventListener("ks_futsal_cmd", (e) => {
    const cmd = e.detail || {};
    if (!cachedInput) scanFutsalFiber();
    if (!cachedInput) return;

    if (cmd.action === "input") {
      cachedInput.jx = typeof cmd.jx === "number" ? cmd.jx : 0;
      cachedInput.jy = typeof cmd.jy === "number" ? cmd.jy : 0;
      cachedInput.kencang = Boolean(cmd.kencang);
      cachedInput.tendang = Boolean(cmd.tendang);
      cachedInput.jenis = cmd.jenis || null;
    } else if (cmd.action === "release") {
      cachedInput.jx = 0;
      cachedInput.jy = 0;
      cachedInput.kencang = false;
      cachedInput.tendang = false;
      cachedInput.jenis = null;
    }
  });

  setInterval(() => {
    const snap = buildSnapshot();
    if (snap.active || wasActive) {
      wasActive = snap.active;
      window.__KS_FUTSAL_STATE = snap;
      window.dispatchEvent(new CustomEvent("ks_futsal_state", { detail: snap }));
    }
  }, 50);
})();
