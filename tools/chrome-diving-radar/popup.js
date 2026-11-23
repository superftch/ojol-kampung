document.getElementById("btn-open-ojol").onclick = () => {
  chrome.tabs.create({ url: "https://www.kampungsebelah.com/?narik=1" });
};

document.getElementById("btn-open-diving").onclick = () => {
  chrome.tabs.create({ url: "https://www.kampungsebelah.com/diving" });
};

document.getElementById("btn-open-mancing").onclick = () => {
  chrome.tabs.create({ url: "https://www.kampungsebelah.com/mancing" });
};

document.getElementById("btn-open-tpu").onclick = () => {
  chrome.tabs.create({ url: "https://www.kampungsebelah.com/?tpu=1" });
};
