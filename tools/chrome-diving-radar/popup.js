const btnToggleOjol = document.getElementById("btn-toggle-ojol-hud");
function renderOjolToggle(visible) {
  if (!btnToggleOjol) return;
  btnToggleOjol.textContent = visible
    ? "🚗 Panel Auto-Ojol: Tampil (Klik untuk Hide)"
    : "🚗 Panel Auto-Ojol: Tersembunyi (Klik untuk Open)";
  btnToggleOjol.style.background = visible ? "#0284c7" : "#334155";
}

if (chrome.storage?.local) {
  chrome.storage.local.get(["ks_ojol_hud_visible"], (res) => {
    renderOjolToggle(Boolean(res?.ks_ojol_hud_visible));
  });
}

if (btnToggleOjol) {
  btnToggleOjol.onclick = () => {
    chrome.storage.local.get(["ks_ojol_hud_visible"], (res) => {
      const next = !res?.ks_ojol_hud_visible;
      chrome.storage.local.set({ ks_ojol_hud_visible: next }, () => {
        renderOjolToggle(next);
      });
    });
  };
}

document.getElementById("btn-open-ojol").onclick = () => {
  if (chrome.storage?.local) {
    chrome.storage.local.set({ ks_ojol_hud_visible: true });
  }
  chrome.tabs.create({ url: "https://www.kampungsebelah.com/?narik=1" });
};

document.getElementById("btn-open-diving").onclick = () => {
  chrome.tabs.create({ url: "https://www.kampungsebelah.com/diving" });
};

document.getElementById("btn-open-mancing").onclick = () => {
  chrome.tabs.create({ url: "https://www.kampungsebelah.com/mancing" });
};

const btnOpenMancingMini = document.getElementById("btn-open-mancing-mini");
if (btnOpenMancingMini) {
  btnOpenMancingMini.onclick = () => {
    chrome.windows.create({
      url: "https://www.kampungsebelah.com/mancing",
      type: "popup",
      width: 460,
      height: 680,
      focused: true
    });
  };
}

document.getElementById("btn-open-tpu").onclick = () => {
  chrome.tabs.create({ url: "https://www.kampungsebelah.com/?tpu=1" });
};

document.getElementById("btn-open-berburu").onclick = () => {
  chrome.tabs.create({ url: "https://www.kampungsebelah.com/berburu" });
};
