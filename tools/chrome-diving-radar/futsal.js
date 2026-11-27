// KampungSebelah - Sepak Bola / Futsal Radar & Auto-Pilot
// Fitur: Radar Lapangan 2D Live, Auto-Dribble, Auto-Oper, Auto-Tembak (Anti-Melambung), & Auto-Rebut.

(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  if (typeof globalThis !== "undefined") {
    globalThis.__KS_FUTSAL_MODULE = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const FIELD = {
    length: 40,
    width: 20,
    halfLength: 20,
    halfWidth: 10,
    goalHalfWidth: 1.5,
    redRingSeconds: 0.85,
    maxSafeChargeSeconds: 0.58
  };

  function clamp(val, min, max) {
    return Math.min(max, Math.max(min, val));
  }

  /**
   * Mengonversi vektor arah dunia (wx, wz) ke koordinat joystick relatif kamera (jx, jy).
   * Invers dari: x = kananX * jx - atasX * jy, z = kananZ * jx - atasZ * jy
   */
  function worldDirToJoystick(wx, wz, arahLayar, magnitude = 0.85) {
    const len = Math.hypot(wx, wz);
    if (len < 1e-6) return { jx: 0, jy: 0 };
    const nx = wx / len;
    const nz = wz / len;
    const cam = arahLayar || { kananX: 1, kananZ: 0, atasX: 0, atasZ: -1 };
    const rawJx = nx * cam.kananX + nz * cam.kananZ;
    const rawJy = -(nx * cam.atasX + nz * cam.atasZ);
    const jLen = Math.hypot(rawJx, rawJy) || 1;
    return {
      jx: Math.round(((rawJx / jLen) * magnitude) * 1000) / 1000 || 0,
      jy: Math.round(((rawJy / jLen) * magnitude) * 1000) / 1000 || 0
    };
  }

  function pickBestGoalTarget(state, myTeam) {
    const targetGoalX = myTeam === 0 ? FIELD.halfLength : -FIELD.halfLength;
    const oppGk = (state.pemain || []).find((p) => p.tim !== myTeam && p.kiper);
    if (!oppGk) {
      return { x: targetGoalX, z: 1.2 };
    }
    // Arahkan tembakan ke sudut tiang gawang (±1.2m) yang paling jauh dari kiper lawan
    const candidates = [-1.2, 1.2];
    let bestZ = 1.2;
    let bestDist = -1;
    for (const cz of candidates) {
      const d = Math.abs(cz - oppGk.z);
      if (d > bestDist) {
        bestDist = d;
        bestZ = cz;
      }
    }
    return { x: targetGoalX, z: bestZ };
  }

  /**
   * Mengecek apakah jalur tembakan dari pemain ke titik gawang (goalX, targetZ) bebas dari halangan
   * pemain lain (baik kawan maupun lawan, kecuali kiper).
   */
  function isShotLaneClear(state, me, goalX, targetZ, blockRadius = 0.75) {
    const sx = goalX - me.x;
    const sz = targetZ - me.z;
    const segLenSq = sx * sx + sz * sz;
    if (segLenSq < 1e-6) return true;

    for (const p of state.pemain || []) {
      if (p.id === me.id || p.kiper) continue;
      const px = p.x - me.x;
      const pz = p.z - me.z;
      const t = (px * sx + pz * sz) / segLenSq;
      if (t <= 0.04 || t >= 1.0) continue;
      const projX = me.x + t * sx;
      const projZ = me.z + t * sz;
      const distToLine = Math.hypot(p.x - projX, p.z - projZ);
      if (distToLine < blockRadius) {
        return false;
      }
    }
    return true;
  }

  /**
   * Menghitung vektor arah bidik yang mengompensasi bantu_bidik (28°) dari game.
   * Jika langsung mengarah ke sudut gawang (±1.2m), bantu_bidik menarik tembakan ke tengah gawang.
   * Dengan menggeser sudut bidik ~24-28° dari pusat gawang ke sisi sudut yang dipilih, tembakan benar-benar mengarah ke pojok gawang.
   */
  function computeCornerAimDir(ballX, ballZ, goalX, desiredZ, aimOffsetDeg = 26) {
    const gx = goalX - ballX;
    const gz = -ballZ;
    const centerAngle = Math.atan2(gz, gx);
    const signZ = desiredZ >= 0 ? 1 : -1;
    const aimOffsetRad = (aimOffsetDeg * Math.PI) / 180;
    const angle = centerAngle + signZ * Math.sign(gx || 1) * aimOffsetRad;
    return {
      dx: Math.cos(angle),
      dz: Math.sin(angle)
    };
  }

  /**
   * Memilih variasi tembakan berdasarkan jarak, posisi & gerak kiper lawan, serta stamina:
   * - Jarak dekat (<= 5.5m): Quick Low Driven (cepat sebelum kiper bereaksi)
   * - Jarak menengah (5.5 - 9.5m): Placed Curve / Wrong-Foot jika kiper bergerak
   * - Jarak jauh (> 9.5m): Power Top-Corner (tinggi > 1.55m melewati jangkauan terjun kiper)
   */
  function selectShotVariation(state, me, distToGoal, goalTarget, options = {}) {
    const myTeam = me.tim;
    const oppGk = (state.pemain || []).find((p) => p.tim !== myTeam && p.kiper);
    const rng = typeof options.rng === "function" ? options.rng : Math.random;
    const jitterDeg = (rng() - 0.5) * 4; // ±2° variasi alami
    const jitterMs = Math.round((rng() - 0.5) * 60);

    let targetZ = goalTarget.z;
    // Wrong-foot: jika kiper sedang bergerak cepat ke satu sisi, tembak ke sisi sebaliknya
    if (oppGk && Math.abs(oppGk.vz || 0) > 0.9) {
      targetZ = oppGk.vz > 0 ? -1.25 : 1.25;
    }

    if (distToGoal <= 5.5) {
      if (distToGoal < 3.8) {
        return {
          shotType: "Quick Tap",
          targetZ,
          aimOffsetDeg: clamp(27 + jitterDeg, 24, 29),
          chargeMs: clamp(210 + Math.round(distToGoal * 14) + jitterMs, 180, 280)
        };
      }
      // 3.8m - 5.5m: pakai Top-Shelf (speed > 18 m/s & tinggi > 1.55m) agar tidak bisa ditangkap kiper
      return {
        shotType: "Top Shelf",
        targetZ,
        aimOffsetDeg: clamp(26.5 + jitterDeg, 24, 29),
        chargeMs: clamp(430 + Math.round((distToGoal - 3.8) * 35) + jitterMs, 390, 520)
      };
    }

    if (distToGoal <= 9.5) {
      const isPower = rng() > 0.35 && (me.stamina ?? 1) > 0.45;
      return {
        shotType: isPower ? "Top Corner" : "Placed",
        targetZ,
        aimOffsetDeg: clamp((isPower ? 26 : 27.5) + jitterDeg, 23, 29),
        chargeMs: clamp((isPower ? 570 : 440) + jitterMs, 380, 640)
      };
    }

    // Jarak jauh: power shot tinggi melewati diving kiper (tinggi_terjun 1.55m), tetap aman < 850ms red ring
    const maxSafe = (me.stamina ?? 1) > 0.65 ? 710 : 580;
    return {
      shotType: "Power Rocket",
      targetZ,
      aimOffsetDeg: clamp(25.5 + jitterDeg, 23, 28),
      chargeMs: clamp(Math.round(520 + distToGoal * 12) + jitterMs, 480, maxSafe)
    };
  }

  function findOpenTeammate(state, me, attackDir) {
    const players = state.pemain || [];
    const teammates = players.filter((p) => p.tim === me.tim && p.id !== me.id && !p.kiper);
    const opponents = players.filter((p) => p.tim !== me.tim);

    let best = null;
    let bestScore = -Infinity;
    for (const mate of teammates) {
      const forwardGain = (mate.x - me.x) * attackDir;
      if (forwardGain < -2.0) continue; // hindari oper ke belakang jauh
      let minOppDist = Infinity;
      for (const opp of opponents) {
        const d = Math.hypot(opp.x - mate.x, opp.z - mate.z);
        if (d < minOppDist) minOppDist = d;
      }
      const distToMate = Math.hypot(mate.x - me.x, mate.z - me.z);
      if (distToMate < 2.0 || distToMate > 18.0) continue;

      const score = forwardGain * 1.4 + minOppDist * 2.0 - distToMate * 0.25;
      if (score > bestScore) {
        bestScore = score;
        best = mate;
      }
    }
    return best;
  }

  function computeFutsalDecision(state, myId, options = {}) {
    const idle = {
      role: "idle",
      actionLabel: "Menunggu bola",
      moveX: 0,
      moveZ: 0,
      kencang: false,
      kick: null,
      chargeMs: 0,
      targetX: 0,
      targetZ: 0
    };

    if (!state || !state.bola || !Array.isArray(state.pemain) || myId < 0) {
      return idle;
    }

    const me = state.pemain.find((p) => p.id === myId) || state.pemain[myId];
    if (!me) return idle;

    if (state.fase === "gol") {
      const dxCenter = -me.x;
      const dzCenter = -me.z;
      const distCenter = Math.hypot(dxCenter, dzCenter);
      if (distCenter > 0.8) {
        return {
          role: "reset",
          actionLabel: "⚽ GOL! Kembali ke tengah",
          moveX: dxCenter,
          moveZ: dzCenter,
          kencang: false,
          kick: null,
          chargeMs: 0,
          targetX: 0,
          targetZ: 0
        };
      }
      return { ...idle, actionLabel: "⚽ GOL! Siap kickoff" };
    }

    if (state.fase !== "main") {
      return { ...idle, actionLabel: `Fase: ${state.fase || "-"}` };
    }

    const myTeam = me.tim;
    const attackDir = myTeam === 0 ? 1 : -1;
    const bola = state.bola;
    const opponents = state.pemain.filter((p) => p.tim !== myTeam);

    let nearestOpp = null;
    let nearestOppDist = Infinity;
    for (const opp of opponents) {
      const d = Math.hypot(opp.x - me.x, opp.z - me.z);
      if (d < nearestOppDist) {
        nearestOppDist = d;
        nearestOpp = opp;
      }
    }

    const style = options.style ?? "solo"; // "solo" (individualis gocek) | "team"

    // 1. Saya sedang memegang bola
    if (bola.pemilik === me.id) {
      const goalTarget = pickBestGoalTarget(state, myTeam);
      const dxGoal = goalTarget.x - me.x;
      const dzGoal = goalTarget.z - me.z;
      const distToGoal = Math.hypot(dxGoal, dzGoal);

      // Cek peluang tembak ke gawang: prioritaskan masuk sangat dekat (<= 7.5m), atau tembak darurat (<= 9.0m) jika ditekan rapat
      const closeShootRange = options.shootRange ?? 7.5;
      const pressureShootRange = options.pressureShootRange ?? 9.0;
      const inGoodAngle = Math.abs(me.z) < 7.0 || distToGoal < 7.5;
      const shouldShoot =
        inGoodAngle &&
        (distToGoal <= closeShootRange || (distToGoal <= pressureShootRange && nearestOppDist < 1.25));
      if (shouldShoot) {
        const shot = selectShotVariation(state, me, distToGoal, goalTarget, options);
        let chosenZ = shot.targetZ;
        let laneClear = isShotLaneClear(state, me, goalTarget.x, chosenZ);
        if (!laneClear) {
          const altZ = -chosenZ;
          if (isShotLaneClear(state, me, goalTarget.x, altZ)) {
            chosenZ = altZ;
            laneClear = true;
          }
        }
        if (laneClear || distToGoal <= 3.6) {
          const cornerAim = computeCornerAimDir(bola.x, bola.z, goalTarget.x, chosenZ, shot.aimOffsetDeg);
          return {
            role: "shoot",
            actionLabel: `🎯 ${shot.shotType} (${distToGoal.toFixed(1)}m)`,
            shotType: shot.shotType,
            distToGoal: Math.round(distToGoal * 10) / 10,
            moveX: cornerAim.dx,
            moveZ: cornerAim.dz,
            kencang: false,
            kick: "tembak",
            chargeMs: shot.chargeMs,
            targetX: goalTarget.x,
            targetZ: chosenZ
          };
        }
      }

      // Mode tim: oper jika ditekan lawan; Mode solo (individualis): tidak oper, langsung gocek!
      if (style === "team" && nearestOppDist < 2.4) {
        const mate = findOpenTeammate(state, me, attackDir);
        if (mate) {
          const leadX = clamp(mate.x + (mate.vx || 0) * 0.25, -FIELD.halfLength + 1, FIELD.halfLength - 1);
          const leadZ = clamp(mate.z + (mate.vz || 0) * 0.25, -FIELD.halfWidth + 1, FIELD.halfWidth - 1);
          return {
            role: "pass",
            actionLabel: "⚡ Oper ke kawan",
            moveX: leadX - me.x,
            moveZ: leadZ - me.z,
            kencang: false,
            kick: "oper",
            chargeMs: 120,
            targetX: leadX,
            targetZ: leadZ
          };
        }
      }

      // Giring & gocek-gocek musuh menuju gawang
      const goalDirX = dxGoal / (distToGoal || 1);
      const goalDirZ = dzGoal / (distToGoal || 1);
      let moveX = goalDirX;
      let moveZ = goalDirZ;
      let actionLabel = "🏃 Giring ke gawang";
      let isJuking = false;

      if (nearestOpp && nearestOppDist < 4.4) {
        // Vektor dari saya ke lawan terdekat
        const toOppX = nearestOpp.x - me.x;
        const toOppZ = nearestOpp.z - me.z;
        const toOppLen = Math.hypot(toOppX, toOppZ) || 1;
        const oppForwardDot = (toOppX / toOppLen) * goalDirX + (toOppZ / toOppLen) * goalDirZ;

        // Jika lawan berada di depan/samping jalur menuju gawang, lakukan gocekan menyamping + maju
        if (oppForwardDot > -0.2) {
          isJuking = true;
          actionLabel = `⚡ Gocek lawan (${nearestOppDist.toFixed(1)}m)`;
          // Dua kandidat arah tegak lurus terhadap arah ke lawan
          const perpAx = -toOppZ / toOppLen;
          const perpAz = toOppX / toOppLen;
          const perpBx = -perpAx;
          const perpBz = -perpAz;

          // Pilih sisi yang paling aman dari garis tepi lapangan & paling jauh dari lawan lain
          const scoreSide = (px, pz) => {
            const testX = me.x + (goalDirX * 0.6 + px * 1.1) * 2.5;
            const testZ = me.z + (goalDirZ * 0.6 + pz * 1.1) * 2.5;
            let score = 0;
            if (Math.abs(testZ) > FIELD.halfWidth - 1.3) score -= 10;
            if (Math.abs(testX) > FIELD.halfLength - 1.0) score -= 6;
            for (const opp of opponents) {
              score += Math.min(5, Math.hypot(testX - opp.x, testZ - opp.z));
            }
            // Sedikit preferensi maju ke arah gawang
            score += (testX - me.x) * attackDir * 0.8;
            return score;
          };

          const useA = scoreSide(perpAx, perpAz) >= scoreSide(perpBx, perpBz);
          const jukeX = useA ? perpAx : perpBx;
          const jukeZ = useA ? perpAz : perpBz;

          const urgency = clamp((4.4 - nearestOppDist) / 4.4, 0.25, 1.0);
          moveX = goalDirX * 0.75 + jukeX * (0.95 + urgency * 0.65);
          moveZ = goalDirZ * 0.75 + jukeZ * (0.95 + urgency * 0.65);
        } else {
          // Lawan di belakang -> dorong menjauh sedikit & sprint ke gawang
          const awayX = me.x - nearestOpp.x;
          const awayZ = me.z - nearestOpp.z;
          const awayLen = Math.hypot(awayX, awayZ) || 1;
          const weight = ((4.4 - nearestOppDist) / 4.4) * 0.55;
          moveX += (awayX / awayLen) * weight;
          moveZ += (awayZ / awayLen) * weight;
        }
      }

      // Jaga agar tidak keluar garis samping/belakang
      if (Math.abs(me.z) > FIELD.halfWidth - 1.4) {
        moveZ -= Math.sign(me.z) * 1.1;
      }

      const canSprintAttack =
        me.stamina > 0.36 &&
        ((isJuking && nearestOppDist < 3.4) || (nearestOppDist > 3.2 && distToGoal < 10.5 && me.stamina > 0.52));

      return {
        role: isJuking ? "juke" : "dribble",
        actionLabel,
        moveX,
        moveZ,
        kencang: canSprintAttack,
        kick: null,
        chargeMs: 0,
        targetX: goalTarget.x,
        targetZ: goalTarget.z
      };
    }

    // 2. Kawan sedang memegang bola -> cari ruang kosong di depan
    const owner =
      bola.pemilik >= 0
        ? state.pemain.find((p) => p.id === bola.pemilik) || state.pemain[bola.pemilik]
        : null;

    if (owner && owner.tim === myTeam) {
      const supportX = clamp(owner.x + attackDir * 6.5, -FIELD.halfLength + 2.5, FIELD.halfLength - 2.5);
      const supportZ = owner.z >= 0 ? -4.5 : 4.5;
      const dx = supportX - me.x;
      const dz = supportZ - me.z;
      const dist = Math.hypot(dx, dz);
      return {
        role: "support",
        actionLabel: "📍 Cari ruang kosong",
        moveX: dist > 0.8 ? dx : attackDir,
        moveZ: dist > 0.8 ? dz : 0,
        kencang: false,
        kick: null,
        chargeMs: 0,
        targetX: supportX,
        targetZ: supportZ
      };
    }

    // 3. Bola dipegang kiper lawan -> jangan rebut, jaga jarak & bersiap potong lemparan
    if (owner && owner.tim !== myTeam && owner.kiper) {
      const waitX = clamp(owner.x - attackDir * 5.5, -FIELD.halfLength + 3, FIELD.halfLength - 3);
      const waitZ = owner.z >= 0 ? -2.0 : 2.0;
      const dxWait = waitX - me.x;
      const dzWait = waitZ - me.z;
      const distWait = Math.hypot(dxWait, dzWait);
      return {
        role: "contain",
        actionLabel: "🧤 Kiper pegang bola (siap potong)",
        moveX: distWait > 0.6 ? dxWait : 0,
        moveZ: distWait > 0.6 ? dzWait : 0,
        kencang: false,
        kick: null,
        chargeMs: 0,
        targetX: waitX,
        targetZ: waitZ
      };
    }

    // 4. Bola bebas atau dikuasai pemain lapangan lawan -> kejar & rebut (hindari tekel dari belakang)
    let targetX = clamp(bola.x + (bola.vx || 0) * 0.22, -FIELD.halfLength + 0.5, FIELD.halfLength - 0.5);
    let targetZ = clamp(bola.z + (bola.vz || 0) * 0.22, -FIELD.halfWidth + 0.5, FIELD.halfWidth - 0.5);
    const distToBall = Math.hypot(bola.x - me.x, bola.z - me.z);

    let isBehindOwner = false;
    if (owner && owner.tim !== myTeam && typeof owner.arah === "number") {
      const angleFromOwnerToMe = Math.atan2(me.z - owner.z, me.x - owner.x);
      let diff = (angleFromOwnerToMe - owner.arah) % (2 * Math.PI);
      if (diff > Math.PI) diff -= 2 * Math.PI;
      if (diff < -Math.PI) diff += 2 * Math.PI;
      isBehindOwner = Math.cos(diff) < -0.35;

      // Jika kita di belakang pembawa bola, lari memotong jauh ke depan (arah gawang kita / arah gerak lawan) agar berhadapan langsung
      if (isBehindOwner) {
        const ownGoalX = myTeam === 0 ? -FIELD.halfLength : FIELD.halfLength;
        const toGoalX = ownGoalX - bola.x;
        const toGoalZ = -bola.z;
        const toGoalLen = Math.hypot(toGoalX, toGoalZ) || 1;
        const leadDirX = Math.hypot(owner.vx || 0, owner.vz || 0) > 1.0 ? (owner.vx / Math.hypot(owner.vx, owner.vz)) * 0.5 + (toGoalX / toGoalLen) * 0.5 : Math.cos(owner.arah) * 0.5 + (toGoalX / toGoalLen) * 0.5;
        const leadDirZ = Math.hypot(owner.vx || 0, owner.vz || 0) > 1.0 ? (owner.vz / Math.hypot(owner.vx, owner.vz)) * 0.5 + (toGoalZ / toGoalLen) * 0.5 : Math.sin(owner.arah) * 0.5 + (toGoalZ / toGoalLen) * 0.5;
        const leadLen = Math.hypot(leadDirX, leadDirZ) || 1;
        const sideSign = (me.z - owner.z) >= 0 ? 1 : -1;
        const perpX = -(leadDirZ / leadLen) * sideSign;
        const perpZ = (leadDirX / leadLen) * sideSign;
        targetX = clamp(bola.x + (leadDirX / leadLen) * 3.2 + perpX * 1.1, -FIELD.halfLength + 0.5, FIELD.halfLength - 0.5);
        targetZ = clamp(bola.z + (leadDirZ / leadLen) * 3.2 + perpZ * 1.1, -FIELD.halfWidth + 0.5, FIELD.halfWidth - 0.5);
      }
    }

    const dxBall = targetX - me.x;
    const dzBall = targetZ - me.z;

    // Jarak rebut <= 0.85m saat di depan/samping pembawa bola (cos >= -0.1) agar tidak kena stun & penalti dari belakang
    let isInFrontOrSide = true;
    if (owner && owner.tim !== myTeam && typeof owner.arah === "number") {
      const angleFromOwnerToMe = Math.atan2(me.z - owner.z, me.x - owner.x);
      let diff = (angleFromOwnerToMe - owner.arah) % (2 * Math.PI);
      if (diff > Math.PI) diff -= 2 * Math.PI;
      if (diff < -Math.PI) diff += 2 * Math.PI;
      isInFrontOrSide = Math.cos(diff) >= -0.1;
    }

    const canTackle =
      owner &&
      owner.tim !== myTeam &&
      distToBall <= 0.85 &&
      isInFrontOrSide &&
      (me.rebutT || 0) <= 0 &&
      (me.huyungT || 0) <= 0;

    if (canTackle) {
      const leadBallX = bola.x + (owner.vx || 0) * 0.16;
      const leadBallZ = bola.z + (owner.vz || 0) * 0.16;
      return {
        role: "tackle",
        actionLabel: "🦶 Rebut bola!",
        moveX: leadBallX - me.x,
        moveZ: leadBallZ - me.z,
        kencang: true,
        kick: "oper",
        chargeMs: 120,
        targetX: leadBallX,
        targetZ: leadBallZ
      };
    }

    const ownGoalX = myTeam === 0 ? -FIELD.halfLength : FIELD.halfLength;
    const dangerDefense = Math.abs(bola.x - ownGoalX) < 13.5;
    const canSprintChase =
      (dangerDefense && me.stamina > 0.25) ||
      (isBehindOwner && me.stamina > 0.36) ||
      (!owner && distToBall > 2.2 && me.stamina > 0.42);

    return {
      role: "chase",
      actionLabel: owner ? (isBehindOwner ? "🏃 Potong jalur lawan" : "🛡️ Tekan lawan") : "⚽ Kejar bola",
      moveX: dxBall,
      moveZ: dzBall,
      kencang: canSprintChase,
      kick: null,
      chargeMs: 0,
      targetX,
      targetZ
    };
  }

  // Jalankan UI & loop hanya di browser content-script
  if (typeof window !== "undefined" && typeof document !== "undefined" && typeof chrome !== "undefined" && chrome.runtime) {
    (function initBrowserContent() {
      if (window.__KS_FUTSAL_CONTENT_INIT) return;
      window.__KS_FUTSAL_CONTENT_INIT = true;

      try {
        const s = document.createElement("script");
        s.src = chrome.runtime.getURL("futsal-inject.js");
        s.onload = function () {
          this.remove();
        };
        (document.head || document.documentElement).appendChild(s);
      } catch (e) {
        console.warn("[Futsal] Inject error:", e);
      }

      let hud = null;
      let radarCanvas = null;
      let statusEl = null;
      let scoreEl = null;
      let staminaBarEl = null;
      let btnToggle = null;
      let modeSelect = null;
      let debugBoxEl = null;
      let debugTextEl = null;
      let btnCopyDebug = null;
      let autoEnabled = false;
      let mode = "solo"; // "solo" | "team" | "radar"
      let lastState = null;

      function createMatchStats() {
        return {
          startedAt: Date.now(),
          myTeam: 0,
          skor: [0, 0],
          shots: 0,
          goals: 0,
          gkSaves: 0,
          shotDistSum: 0,
          shotMinDist: null,
          shotMaxDist: null,
          shotTypes: {},
          tackles: 0,
          tacklesWon: 0,
          stuns: 0,
          jukes: 0,
          possessionTicks: 0,
          totalTicks: 0,
          lastShotAt: 0,
          lastTackleAt: 0,
          prevHuyung: 0,
          prevSkor: [0, 0],
          prevGkHold: false,
          prevPemilik: -1,
          shownAfterMatch: false
        };
      }

      let matchStats = createMatchStats();

      function formatDebugSummary(s) {
        const avgDist = s.shots > 0 ? (s.shotDistSum / s.shots).toFixed(1) : "-";
        const possPct = s.totalTicks > 0 ? Math.round((s.possessionTicks / s.totalTicks) * 100) : 0;
        const convPct = s.shots > 0 ? Math.round((s.goals / s.shots) * 100) : 0;
        const tacklePct = s.tackles > 0 ? Math.round((s.tacklesWon / s.tackles) * 100) : 0;
        return {
          skor: `${s.skor[0]}-${s.skor[1]}`,
          shots: s.shots,
          goals: s.goals,
          conversionPct: convPct,
          gkSaves: s.gkSaves,
          avgShotDistM: avgDist === "-" ? null : Number(avgDist),
          shotRangeM: s.shots > 0 ? `${s.shotMinDist}..${s.shotMaxDist}` : null,
          shotTypes: s.shotTypes,
          tackles: s.tackles,
          tacklesWon: s.tacklesWon,
          tackleWinPct: tacklePct,
          stuns: s.stuns,
          jukes: s.jukes,
          possessionPct: possPct
        };
      }

      function renderDebugBox(show) {
        if (!debugBoxEl || !debugTextEl) return;
        if (!show) {
          debugBoxEl.style.display = "none";
          return;
        }
        const sum = formatDebugSummary(matchStats);
        debugTextEl.textContent = [
          `Skor: ${sum.skor} | Penguasaan: ${sum.possessionPct}%`,
          `Shoot: ${sum.shots} (Gol: ${sum.goals} / ${sum.conversionPct}%, Tepis: ${sum.gkSaves})`,
          `Jarak Shoot: rata2 ${sum.avgShotDistM ?? "-"}m (${sum.shotRangeM ?? "-"})`,
          `Tekel: ${sum.tacklesWon}/${sum.tackles} (${sum.tackleWinPct}%) | Stun: ${sum.stuns} | Gocek: ${sum.jukes}`
        ].join("\n");
        debugBoxEl.style.display = "block";
      }

      let kickState = {
        active: false,
        kind: null,
        releaseAt: 0,
        cooldownUntil: 0
      };

      function sendCmd(detail) {
        window.dispatchEvent(new CustomEvent("ks_futsal_cmd", { detail }));
      }

      function setAutoEnabled(next) {
        autoEnabled = Boolean(next);
        if (!autoEnabled) {
          kickState.active = false;
          sendCmd({ action: "release" });
        }
        if (btnToggle) {
          btnToggle.textContent = autoEnabled ? "⏹️ STOP Auto-Main [F]" : "⚽ MULAI Auto-Main [F]";
          btnToggle.style.background = autoEnabled ? "#dc2626" : "#16a34a";
        }
      }

      function makeDraggable(panel, handle) {
        const saved = localStorage.getItem("ks_futsal_hud_pos");
        if (saved) {
          try {
            const p = JSON.parse(saved);
            if (typeof p.left === "number" && typeof p.top === "number") {
              panel.style.left = `${p.left}px`;
              panel.style.top = `${p.top}px`;
              panel.style.right = "auto";
            }
          } catch (_) {}
        }

        let dragging = false;
        let ox = 0;
        let oy = 0;
        handle.addEventListener("pointerdown", (e) => {
          if (e.target.closest("button, select")) return;
          dragging = true;
          const r = panel.getBoundingClientRect();
          ox = e.clientX - r.left;
          oy = e.clientY - r.top;
          handle.setPointerCapture?.(e.pointerId);
        });
        window.addEventListener("pointermove", (e) => {
          if (!dragging) return;
          const left = clamp(e.clientX - ox, 4, window.innerWidth - panel.offsetWidth - 4);
          const top = clamp(e.clientY - oy, 4, window.innerHeight - panel.offsetHeight - 4);
          panel.style.left = `${left}px`;
          panel.style.top = `${top}px`;
          panel.style.right = "auto";
        });
        window.addEventListener("pointerup", () => {
          if (!dragging) return;
          dragging = false;
          const r = panel.getBoundingClientRect();
          localStorage.setItem("ks_futsal_hud_pos", JSON.stringify({ left: Math.round(r.left), top: Math.round(r.top) }));
        });
      }

      function ensureHud() {
        if (hud) return hud;
        hud = document.createElement("div");
        hud.id = "ks-futsal-hud";
        hud.style.cssText = [
          "position:fixed",
          "top:68px",
          "right:14px",
          "width:244px",
          "z-index:2147483640",
          "background:rgba(10,18,34,0.86)",
          "backdrop-filter:blur(10px)",
          "border:1px solid rgba(56,189,248,0.35)",
          "border-radius:12px",
          "padding:10px",
          "color:#e2e8f0",
          "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif",
          "font-size:12px",
          "box-shadow:0 10px 28px rgba(0,0,0,0.45)",
          "display:none",
          "user-select:none"
        ].join(";");

        const header = document.createElement("div");
        header.style.cssText = "display:flex;align-items:center;justify-content:space-between;cursor:move;margin-bottom:8px;";
        header.innerHTML = `<strong style="color:#4ade80;font-size:13px;">⚽ Sepak Bola Pro</strong><span style="font-size:10px;color:#94a3b8;">[F] Toggle</span>`;
        hud.appendChild(header);

        scoreEl = document.createElement("div");
        scoreEl.style.cssText = "display:flex;justify-content:space-between;font-weight:700;margin-bottom:6px;font-size:12px;color:#f8fafc;";
        scoreEl.textContent = "Skor 0 - 0 · 0:00";
        hud.appendChild(scoreEl);

        radarCanvas = document.createElement("canvas");
        radarCanvas.width = 220;
        radarCanvas.height = 114;
        radarCanvas.style.cssText = "width:100%;height:auto;border-radius:6px;border:1px solid rgba(255,255,255,0.18);display:block;margin-bottom:8px;background:#14532d;";
        hud.appendChild(radarCanvas);

        const stamWrap = document.createElement("div");
        stamWrap.style.cssText = "height:5px;background:rgba(255,255,255,0.14);border-radius:99px;overflow:hidden;margin-bottom:6px;";
        staminaBarEl = document.createElement("div");
        staminaBarEl.style.cssText = "height:100%;width:100%;background:#22c55e;transition:width 80ms linear;";
        stamWrap.appendChild(staminaBarEl);
        hud.appendChild(stamWrap);

        statusEl = document.createElement("div");
        statusEl.style.cssText = "font-size:11px;color:#cbd5e1;margin-bottom:8px;min-height:16px;";
        statusEl.textContent = "Siap bermain";
        hud.appendChild(statusEl);

        modeSelect = document.createElement("select");
        modeSelect.style.cssText = "width:100%;margin-bottom:7px;padding:5px 7px;border-radius:6px;background:#1e293b;color:#f8fafc;border:1px solid rgba(255,255,255,0.18);font-size:11px;";
        modeSelect.innerHTML = `<option value="solo">⚡ Mode: Solo Gocek (Individualis)</option><option value="team">🤝 Mode: Tim (Oper & Tembak)</option><option value="radar">👁️ Mode: Radar Saja</option>`;
        modeSelect.onchange = () => {
          mode = modeSelect.value;
          if (mode === "radar" && autoEnabled) setAutoEnabled(false);
        };
        hud.appendChild(modeSelect);

        btnToggle = document.createElement("button");
        btnToggle.type = "button";
        btnToggle.style.cssText = "width:100%;padding:7px;border:none;border-radius:7px;font-weight:700;color:#fff;cursor:pointer;background:#16a34a;font-size:12px;";
        btnToggle.textContent = "⚽ MULAI Auto-Main [F]";
        btnToggle.onclick = () => {
          if (mode === "radar") {
            mode = "solo";
            modeSelect.value = "solo";
          }
          setAutoEnabled(!autoEnabled);
        };
        hud.appendChild(btnToggle);

        debugBoxEl = document.createElement("div");
        debugBoxEl.style.cssText = "display:none;margin-top:8px;padding:7px;border-radius:7px;background:rgba(15,23,42,0.9);border:1px solid rgba(250,204,21,0.35);font-size:10.5px;line-height:1.45;color:#fef08a;";
        debugTextEl = document.createElement("pre");
        debugTextEl.style.cssText = "margin:0 0 6px;white-space:pre-wrap;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:10px;color:#e2e8f0;";
        btnCopyDebug = document.createElement("button");
        btnCopyDebug.type = "button";
        btnCopyDebug.style.cssText = "width:100%;padding:5px;border:none;border-radius:5px;background:#334155;color:#f8fafc;cursor:pointer;font-size:10.5px;font-weight:600;";
        btnCopyDebug.textContent = "📋 Salin Debug Statistik";
        btnCopyDebug.onclick = () => {
          const payload = JSON.stringify(formatDebugSummary(matchStats), null, 2);
          navigator.clipboard?.writeText(payload).catch(() => {});
          btnCopyDebug.textContent = "✅ Tersalin!";
          setTimeout(() => {
            if (btnCopyDebug) btnCopyDebug.textContent = "📋 Salin Debug Statistik";
          }, 1500);
        };
        debugBoxEl.appendChild(debugTextEl);
        debugBoxEl.appendChild(btnCopyDebug);
        hud.appendChild(debugBoxEl);

        document.body.appendChild(hud);
        makeDraggable(hud, header);
        return hud;
      }

      function drawRadar(state) {
        if (!radarCanvas || !state) return;
        const ctx = radarCanvas.getContext("2d");
        const W = radarCanvas.width;
        const H = radarCanvas.height;
        const pad = 6;
        const pw = W - pad * 2;
        const ph = H - pad * 2;

        const toPx = (x, z) => ({
          px: pad + ((x + FIELD.halfLength) / FIELD.length) * pw,
          py: pad + ((z + FIELD.halfWidth) / FIELD.width) * ph
        });

        ctx.clearRect(0, 0, W, H);
        ctx.fillStyle = "#166534";
        ctx.fillRect(0, 0, W, H);

        // Garis lapangan
        ctx.strokeStyle = "rgba(255,255,255,0.55)";
        ctx.lineWidth = 1;
        ctx.strokeRect(pad, pad, pw, ph);
        ctx.beginPath();
        ctx.moveTo(W / 2, pad);
        ctx.lineTo(W / 2, H - pad);
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(W / 2, H / 2, 16, 0, Math.PI * 2);
        ctx.stroke();

        // Gawang kiri & kanan
        const gTop = pad + ((FIELD.halfWidth - FIELD.goalHalfWidth) / FIELD.width) * ph;
        const gH = ((FIELD.goalHalfWidth * 2) / FIELD.width) * ph;
        ctx.fillStyle = "rgba(255,255,255,0.75)";
        ctx.fillRect(pad - 3, gTop, 3, gH);
        ctx.fillRect(W - pad, gTop, 3, gH);

        const me = (state.pemain || []).find((p) => p.id === state.myId) || state.pemain?.[state.myId];
        const myTeam = me ? me.tim : 0;

        for (const p of state.pemain || []) {
          const { px, py } = toPx(p.x, p.z);
          const isMe = p.id === (me ? me.id : state.myId);
          ctx.beginPath();
          ctx.arc(px, py, isMe ? 4.5 : 3.3, 0, Math.PI * 2);
          ctx.fillStyle = isMe ? "#facc15" : p.tim === myTeam ? "#38bdf8" : "#f87171";
          ctx.fill();
          if (isMe) {
            ctx.strokeStyle = "#ffffff";
            ctx.lineWidth = 1.2;
            ctx.stroke();
          }
        }

        if (state.bola) {
          const { px, py } = toPx(state.bola.x, state.bola.z);
          ctx.beginPath();
          ctx.arc(px, py, 3, 0, Math.PI * 2);
          ctx.fillStyle = "#ffffff";
          ctx.fill();
          ctx.strokeStyle = "#0f172a";
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      }

      window.addEventListener("keydown", (e) => {
        if (e.target instanceof HTMLElement && e.target.closest("input, textarea, select, [contenteditable]")) return;
        if (e.key.toLowerCase() === "f" && lastState?.active) {
          e.preventDefault();
          if (mode === "radar") {
            mode = "solo";
            if (modeSelect) modeSelect.value = "solo";
          }
          setAutoEnabled(!autoEnabled);
        }
      });

      window.addEventListener("ks_futsal_state", (e) => {
        const state = e.detail;
        lastState = state;
        const el = ensureHud();

        if (!state || !state.active) {
          el.style.display = "none";
          if (autoEnabled) setAutoEnabled(false);
          return;
        }

        el.style.display = "block";
        const mins = Math.floor((state.sisa || 0) / 60);
        const secs = String(Math.floor((state.sisa || 0) % 60)).padStart(2, "0");
        scoreEl.textContent = `Skor ${state.skor?.[0] ?? 0} - ${state.skor?.[1] ?? 0} · ${mins}:${secs}`;

        const me = (state.pemain || []).find((p) => p.id === state.myId) || state.pemain?.[state.myId];
        if (me && staminaBarEl) {
          const pct = Math.round(clamp(me.stamina ?? 1, 0, 1) * 100);
          staminaBarEl.style.width = `${pct}%`;
          staminaBarEl.style.background = pct < 30 ? "#ef4444" : "#22c55e";
        }

        // Reset statistik jika match baru dimulai ulang
        if (state.fase === "siap" && matchStats.shownAfterMatch) {
          matchStats = createMatchStats();
          renderDebugBox(false);
        }

        if (me && state.bola) {
          const nowMs = Date.now();
          matchStats.myTeam = me.tim;
          matchStats.skor = Array.isArray(state.skor) ? [...state.skor] : [0, 0];

          if (state.fase === "main") {
            matchStats.totalTicks++;
            if (state.bola.pemilik === me.id) matchStats.possessionTicks++;
          }

          if ((me.huyungT || 0) > 0 && matchStats.prevHuyung <= 0) {
            matchStats.stuns++;
          }
          matchStats.prevHuyung = me.huyungT || 0;

          if ((matchStats.skor[me.tim] || 0) > (matchStats.prevSkor[me.tim] || 0) && nowMs - matchStats.lastShotAt < 4500) {
            matchStats.goals++;
          }
          matchStats.prevSkor = [...matchStats.skor];

          const owner = state.bola.pemilik >= 0 ? (state.pemain || []).find((p) => p.id === state.bola.pemilik) : null;
          const gkHold = Boolean(owner && owner.kiper && owner.tim !== me.tim);
          if (gkHold && !matchStats.prevGkHold && nowMs - matchStats.lastShotAt < 3500) {
            matchStats.gkSaves++;
          }
          matchStats.prevGkHold = gkHold;

          const prevOwnerObj = matchStats.prevPemilik >= 0 ? (state.pemain || []).find((p) => p.id === matchStats.prevPemilik) : null;
          const wasOppOwner = Boolean(prevOwnerObj && prevOwnerObj.tim !== me.tim);
          if (wasOppOwner && (state.bola.pemilik === -1 || state.bola.pemilik === me.id) && nowMs - matchStats.lastTackleAt < 700) {
            matchStats.tacklesWon++;
          }
          matchStats.prevPemilik = state.bola.pemilik;
        }

        const selesaiModal = document.querySelector('[data-testid="futsal-selesai"]');
        if (state.fase === "selesai" || selesaiModal) {
          if (!matchStats.shownAfterMatch) {
            matchStats.shownAfterMatch = true;
            console.log("[FutsalDebug]", formatDebugSummary(matchStats));
          }
          renderDebugBox(true);
        } else if (state.fase === "main" && matchStats.shownAfterMatch) {
          matchStats = createMatchStats();
          renderDebugBox(false);
        }

        drawRadar(state);

        const decision = computeFutsalDecision(state, state.myId, { style: mode === "team" ? "team" : "solo" });
        if (!autoEnabled || mode === "radar") {
          statusEl.textContent = `Saran: ${decision.actionLabel}`;
          return;
        }

        statusEl.textContent = decision.actionLabel;
        const now = performance.now();
        if (decision.role === "idle") {
          if (kickState.active) kickState.active = false;
          sendCmd({ action: "release" });
          return;
        }
        const joy = worldDirToJoystick(decision.moveX, decision.moveZ, state.arahLayar, 0.85);

        // Kelola fase tahan & lepas tendangan/operan
        if (kickState.active) {
          if (now >= kickState.releaseAt) {
            const wasTackle = kickState.role === "tackle";
            kickState.active = false;
            kickState.cooldownUntil = now + (wasTackle ? 950 : 240);
            sendCmd({ action: "input", jx: joy.jx, jy: joy.jy, kencang: false, tendang: false, jenis: null });
          } else {
            sendCmd({ action: "input", jx: joy.jx, jy: joy.jy, kencang: false, tendang: true, jenis: kickState.kind });
          }
          return;
        }

        if (decision.kick && now >= kickState.cooldownUntil) {
          const nowMs = Date.now();
          if (decision.role === "shoot") {
            matchStats.shots++;
            matchStats.lastShotAt = nowMs;
            const d = decision.distToGoal || 0;
            matchStats.shotDistSum += d;
            matchStats.shotMinDist = matchStats.shotMinDist === null ? d : Math.min(matchStats.shotMinDist, d);
            matchStats.shotMaxDist = matchStats.shotMaxDist === null ? d : Math.max(matchStats.shotMaxDist, d);
            const st = decision.shotType || "Unknown";
            matchStats.shotTypes[st] = (matchStats.shotTypes[st] || 0) + 1;
          } else if (decision.role === "tackle") {
            matchStats.tackles++;
            matchStats.lastTackleAt = nowMs;
          }
          kickState.active = true;
          kickState.role = decision.role;
          kickState.kind = decision.kick;
          kickState.releaseAt = now + (decision.chargeMs || 140);
          sendCmd({ action: "input", jx: joy.jx, jy: joy.jy, kencang: false, tendang: true, jenis: decision.kick });
          return;
        }

        if (decision.role === "juke" && matchStats.totalTicks % 15 === 0) {
          matchStats.jukes++;
        }

        sendCmd({
          action: "input",
          jx: joy.jx,
          jy: joy.jy,
          kencang: Boolean(decision.kencang),
          tendang: false,
          jenis: null
        });
      });
    })();
  }

  return {
    FIELD,
    worldDirToJoystick,
    pickBestGoalTarget,
    isShotLaneClear,
    computeCornerAimDir,
    selectShotVariation,
    findOpenTeammate,
    computeFutsalDecision
  };
});
