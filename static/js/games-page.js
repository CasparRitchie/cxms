document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initCountryGame();
  initPopulationGame();
  initCapitalGame();
  enhanceGameFrame("sudoku-frame");
  enhanceGameFrame("sudoblocku-frame");
});

function initTabs() {
  const buttons = Array.from(document.querySelectorAll(".tab-btn"));
  const tabs = Array.from(document.querySelectorAll(".game-tab"));

  function showTab(name) {
    tabs.forEach((tab) => {
      tab.style.display = tab.dataset.game === name ? "block" : "none";
    });

    buttons.forEach((button) => {
      button.setAttribute("aria-selected", String(button.dataset.target === name));
    });

    try {
      history.replaceState(null, "", "#" + name);
    } catch (error) {
      console.warn("Could not update hash", error);
    }
  }

  buttons.forEach((button) => {
    button.addEventListener("click", () => showTab(button.dataset.target));
  });

  const hash = (window.location.hash || "").replace("#", "");
  const validNames = new Set(buttons.map((button) => button.dataset.target));

  if (validNames.has(hash)) {
    showTab(hash);
  } else {
    showTab("country");
  }
}

function notify(message) {
  window.alert(message);
}

/* =========================
   COUNTRY GAME
========================= */

let countryScore = 0;
let countryStreak = 0;
let currentCountry = "";

function initCountryGame() {
  loadNewCountry();
}

function loadNewCountry() {
  fetch("/games/country-data")
    .then((response) => {
      if (!response.ok) {
        throw new Error("Could not load country data");
      }
      return response.json();
    })
    .then((data) => {
      const country = data.correct_country;
      currentCountry = country.name;

      const countryImg = document.getElementById("country-outline");
      countryImg.src = country.outline;
      countryImg.alt = country.name;

      const optionsContainer = document.getElementById("options-container");
      optionsContainer.innerHTML = "";

      data.options.forEach((option) => {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = option;
        button.addEventListener("click", () => submitCountryAnswer(option));
        optionsContainer.appendChild(button);
      });
    })
    .catch((error) => {
      console.error("Error fetching country data:", error);
    });
}

function submitCountryAnswer(selectedCountry) {
  if (selectedCountry === currentCountry) {
    notify("Correct!");
    countryScore += 1;
    countryStreak += 1;
  } else {
    notify(`Incorrect, the correct country was ${currentCountry}.`);
    countryStreak = 0;
  }

  document.getElementById("score-value").textContent = String(countryScore);
  document.getElementById("streak-value").textContent = String(countryStreak);

  loadNewCountry();
}

/* =========================
   POPULATION GAME
========================= */

let populationScore = 0;
let populationStreak = 0;
let populationData = [];

function initPopulationGame() {
  fetch("/static/js/country-data.json")
    .then((response) => {
      if (!response.ok) {
        throw new Error("Could not load population data");
      }
      return response.json();
    })
    .then((data) => {
      populationData = Array.isArray(data) ? data.filter(isValidPopulationCountry) : [];
      loadNewPopulationChallenge();
    })
    .catch((error) => {
      console.error("Error loading population data:", error);
    });
}

function isValidPopulationCountry(country) {
  return (
    country &&
    typeof country.country === "string" &&
    country.country.trim() !== "" &&
    typeof country.image_path === "string" &&
    country.image_path.trim() !== "" &&
    Number.isFinite(Number(country["2023 population"]))
  );
}

function loadNewPopulationChallenge() {
  if (populationData.length < 2) return;

  const firstIndex = getRandomIndex(populationData.length);
  let secondIndex = getRandomIndex(populationData.length);

  while (secondIndex === firstIndex) {
    secondIndex = getRandomIndex(populationData.length);
  }

  const countryA = populationData[firstIndex];
  const countryB = populationData[secondIndex];

  updatePopulationOption(
    "country1",
    countryA.country,
    normalizeImagePath(countryA.image_path)
  );
  updatePopulationOption(
    "country2",
    countryB.country,
    normalizeImagePath(countryB.image_path)
  );

  document.getElementById("country1-btn").onclick = () =>
    submitPopulationAnswer(countryA, countryB);
  document.getElementById("country2-btn").onclick = () =>
    submitPopulationAnswer(countryB, countryA);
}

function updatePopulationOption(prefix, name, imagePath) {
  const img = document.getElementById(`${prefix}-img`);
  const label = document.getElementById(`${prefix}-name`);

  img.src = imagePath;
  img.alt = name;
  label.textContent = name;
}

function submitPopulationAnswer(selectedCountry, otherCountry) {
  const selectedPopulation = Number(selectedCountry["2023 population"]);
  const otherPopulation = Number(otherCountry["2023 population"]);

  if (selectedPopulation > otherPopulation) {
    notify("Correct!");
    populationScore += 1;
    populationStreak += 1;
  } else {
    notify(`Incorrect. ${otherCountry.country} has the larger population.`);
    populationStreak = 0;
  }

  document.getElementById("population-score-value").textContent = String(populationScore);
  document.getElementById("population-streak-value").textContent = String(populationStreak);

  loadNewPopulationChallenge();
}

/* =========================
   CAPITAL GAME
========================= */

let capitalScore = 0;
let capitalStreak = 0;
let capitalsData = [];

function initCapitalGame() {
  fetch("/static/data/capitals.json")
    .then((response) => {
      if (!response.ok) {
        throw new Error("Could not load capitals data");
      }
      return response.json();
    })
    .then((data) => {
      capitalsData = Array.isArray(data) ? data.filter(isValidCapitalEntry) : [];
      loadNewCapitalChallenge();
    })
    .catch((error) => {
      console.error("Error loading capitals data:", error);
    });
}

function isValidCapitalEntry(entry) {
  return (
    entry &&
    typeof entry.country === "string" &&
    entry.country.trim() !== "" &&
    typeof entry.capital === "string" &&
    entry.capital.trim() !== ""
  );
}

function loadNewCapitalChallenge() {
  if (capitalsData.length < 4) return;

  const correctIndex = getRandomIndex(capitalsData.length);
  const correctEntry = capitalsData[correctIndex];

  const options = [correctEntry.capital];

  while (options.length < 4) {
    const candidate = capitalsData[getRandomIndex(capitalsData.length)].capital;
    if (!options.includes(candidate)) {
      options.push(candidate);
    }
  }

  shuffleInPlace(options);

  document.getElementById("capital-country-name").textContent = correctEntry.country;

  const optionsContainer = document.getElementById("capital-options-container");
  optionsContainer.innerHTML = "";

  options.forEach((capital) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = capital;
    button.addEventListener("click", () => submitCapitalAnswer(capital, correctEntry));
    optionsContainer.appendChild(button);
  });
}

function submitCapitalAnswer(selectedCapital, correctEntry) {
  if (selectedCapital === correctEntry.capital) {
    notify("Correct!");
    capitalScore += 1;
    capitalStreak += 1;
  } else {
    notify(
      `Incorrect. The capital of ${correctEntry.country} is ${correctEntry.capital}.`
    );
    capitalStreak = 0;
  }

  document.getElementById("capital-score-value").textContent = String(capitalScore);
  document.getElementById("capital-streak-value").textContent = String(capitalStreak);

  loadNewCapitalChallenge();
}

/* =========================
   IFRAME ENHANCEMENTS
========================= */

function enhanceGameFrame(frameId) {
  const iframe = document.getElementById(frameId);
  if (!iframe) return;

  iframe.addEventListener("load", () => {
    try {
      const doc = iframe.contentDocument || iframe.contentWindow.document;
      if (!doc) return;

      const style = doc.createElement("style");

      if (frameId === "sudoku-frame") {
        style.textContent = `
          html, body, #root {
            height: 100%;
            min-height: 100%;
            margin: 0;
            background: #000000;
            color: #ffffff;
          }

          body {
            overflow: hidden;
            font-family: Arial, sans-serif;
          }

          #root {
            height: 100%;
          }

          .app {
            height: 100%;
            width: 100%;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: flex-start;
            padding: 12px;
            background: #000000;
            color: #ffffff;
          }

          .topbar,
          .footer,
          .footer-row,
          .info,
          h1, h2, h3, p, span, div, label {
            color: #ffffff !important;
          }

          button,
          select {
            background: #111827 !important;
            color: #ffffff !important;
            border: 1px solid rgba(255,255,255,0.12) !important;
            border-radius: 10px !important;
          }

          .board {
            width: min(78vw, calc(100vh - 250px), 640px) !important;
            height: min(78vw, calc(100vh - 250px), 640px) !important;
            margin: 0 auto !important;
            background: #0f172a !important;
            border: 2px solid rgba(255,255,255,0.2) !important;
            border-radius: 14px !important;
            overflow: hidden !important;
          }

          .cell {
            background: #1f2937 !important;
            color: #ffffff !important;
            border: 1px solid rgba(255,255,255,0.06) !important;
            font-size: clamp(14px, 2.2vw, 28px) !important;
          }

          .cell.prefilled {
            background: #263445 !important;
            color: #ffffff !important;
            font-weight: 700 !important;
          }

          .cell.selected {
            outline: 2px solid #7c3aed !important;
            outline-offset: -2px !important;
          }

          .notes {
            color: #cbd5e1 !important;
          }

          @media (max-width: 700px) {
            .board {
              width: min(94vw, calc(100vh - 270px)) !important;
              height: min(94vw, calc(100vh - 270px)) !important;
            }

            .cell {
              font-size: clamp(12px, 4vw, 22px) !important;
            }
          }
        `;
      } else if (frameId === "sudoblocku-frame") {
        style.textContent = `
          html, body, #root {
            height: 100%;
            min-height: 100%;
            margin: 0;
            background: #000000;
            color: #ffffff;
          }

          body {
            overflow: auto;
          }
        `;
      } else {
        style.textContent = `
          html, body, #root {
            height: 100%;
            min-height: 100%;
            margin: 0;
          }

          body {
            overflow: auto;
          }
        `;
      }

      doc.head.appendChild(style);
    } catch (error) {
      console.log("Could not enhance iframe:", frameId, error);
    }
  });
}

/* =========================
   HELPERS
========================= */

function normalizeImagePath(path) {
  if (!path) return "";
  return path.startsWith("/") ? path : `/${path}`;
}

function getRandomIndex(length) {
  return Math.floor(Math.random() * length);
}

function shuffleInPlace(array) {
  for (let i = array.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [array[i], array[j]] = [array[j], array[i]];
  }
  return array;
}
