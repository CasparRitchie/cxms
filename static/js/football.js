const availableTeams = [
  "Argentina",
  "Brazil",
  "England",
  "France",
  "Germany",
  "Netherlands",
  "Portugal",
  "Spain",
  "Italy",
  "Belgium",
  "Croatia",
  "Uruguay",
];

const defaultPlayers = [
  {
    name: "Sammy",
    teams: ["Brazil", "Croatia", "South Korea", "Tunisia", "Côte d’Ivoire", "Cabo Verde"],
  },
  {
    name: "Louisa",
    teams: ["Portugal", "Germany", "Austria", "Egypt", "Saudi Arabia", "Haiti"],
  },
  {
    name: "Liv",
    teams: ["England", "USA", "Australia", "Scotland", "Qatar", "Ghana"],
  },
  {
    name: "Joseph",
    teams: ["Belgium", "Mexico", "Türkiye", "Canada", "Uzbekistan", "Curaçao"],
  },
  {
    name: "Dan",
    teams: ["Spain", "Morocco", "Senegal", "Norway", "South Africa", "Iraq"],
  },
  {
    name: "Helena",
    teams: ["France", "Colombia", "Ecuador", "Panama", "Jordan", "New Zealand"],
  },
  {
    name: "Claire",
    teams: ["Argentina", "Switzerland", "Iran", "Paraguay", "Georgia", "Bosnia & Herzegovina"],
  },
  {
    name: "Caspar",
    teams: ["Netherlands", "Uruguay", "Japan", "Algeria", "Sweden", "DR Congo"],
  },
].map((player) => ({
  ...player,
  points: 0,
  status: "Still alive",
}));

let fixtures = [];

async function loadFixtures() {
  try {
    const response = await fetch("/api/football/worldcup/fixtures");
    const data = await response.json();

    if (data.ok && Array.isArray(data.fixtures)) {
      fixtures = data.fixtures;
      renderLeaderboard(players);
      renderFixtures();
    }
  } catch (error) {
    console.error("Could not load World Cup fixtures", error);
  }
}

const storageKey = "cxms-football-sweepstake-v1";
const leaderboard = document.getElementById("leaderboard");
const fixturesList = document.getElementById("fixtures");
const setupForm = document.getElementById("sweepstake-form");
const participantInput = document.getElementById("participant-names");
const resetButton = document.getElementById("reset-sweepstake");
const summaryParticipants = document.getElementById("summary-participants");
const summaryTeams = document.getElementById("summary-teams");

function loadPlayers() {
  const saved = localStorage.getItem(storageKey);
  if (!saved) return defaultPlayers;

  try {
    const parsed = JSON.parse(saved);
    return Array.isArray(parsed) && parsed.length ? parsed : defaultPlayers;
  } catch (error) {
    return defaultPlayers;
  }
}

function savePlayers(players) {
  localStorage.setItem(storageKey, JSON.stringify(players));
}

function shuffle(items) {
  return [...items].sort(() => Math.random() - 0.5);
}

function buildPlayersFromNames(rawNames) {
  const names = rawNames
    .split(/\n|,/)
    .map((name) => name.trim())
    .filter(Boolean);

  const shuffledTeams = shuffle(availableTeams);

  return names.map((name, index) => ({
    name,
    team: shuffledTeams[index % shuffledTeams.length],
    points: 0,
    status: "Ready to play",
  }));
}

function renderSummary(players) {
  if (summaryParticipants) summaryParticipants.textContent = players.length;

  if (summaryTeams) {
    const allTeams = players.flatMap((player) => player.teams || []);
    summaryTeams.textContent = new Set(allTeams).size;
  }
}

function renderLeaderboard(players) {
  if (!leaderboard) return;

  leaderboard.innerHTML = [...players]
    .sort((a, b) => getPlayerPoints(b) - getPlayerPoints(a))
    .map((player, index) => `
      <article class="sweepstake-card">
        <div class="rank-badge">${index + 1}</div>
        <h3>${player.name}</h3>
        <p>${getPlayerPoints(player)} pts</p>
        <div class="team-list">
          ${player.teams.map((team) => `
            <span class="team-pill">${team} · ${getTeamPoints(team)} pts</span>
          `).join("")}
        </div>
      </article>
    `)
    .join("");
}

function getTeamOwner(teamName) {
  return players.find((player) => player.teams.includes(teamName));
}

function getFixtureOwnerLabel(fixture) {
  const homeOwner = getTeamOwner(fixture.home);
  const awayOwner = getTeamOwner(fixture.away);

  if (homeOwner && awayOwner) {
    return `${homeOwner.name} vs ${awayOwner.name}`;
  }

  if (homeOwner) {
    return `${homeOwner.name} (${fixture.home})`;
  }

  if (awayOwner) {
    return `${awayOwner.name} (${fixture.away})`;
  }

  return fixture.stage;
}

function renderFixtures() {
  if (!fixturesList) return;

  fixturesList.innerHTML = fixtures
    .map((fixture) => {
      const kickoff = new Date(fixture.kickoff).toLocaleString(undefined, {
        weekday: "short",
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      });

      const ownerLabel = getFixtureOwnerLabel(fixture);

      return `
        <div class="fixture-row">
          <div>
            <strong>${fixture.home} vs ${fixture.away}</strong>
            <p>${ownerLabel}</p>
          </div>
          <div class="fixture-date">${kickoff}</div>
        </div>
      `;
    })
    .join("");
}

function renderAll(players) {
  renderSummary(players);
  renderLeaderboard(players);
  renderFixtures();

  if (participantInput) {
    participantInput.value = players.map((player) => player.name).join("\n");
  }
}

let players = loadPlayers();
renderAll(players);
loadFixtures();

function getTeamPoints(teamName) {
  return fixtures.reduce((total, fixture) => {
    if (fixture.status !== "complete") return total;
    if (fixture.homeScore === null || fixture.awayScore === null) return total;

    const isHome = fixture.home === teamName;
    const isAway = fixture.away === teamName;

    if (!isHome && !isAway) return total;

    const teamScore = isHome ? fixture.homeScore : fixture.awayScore;
    const opponentScore = isHome ? fixture.awayScore : fixture.homeScore;

    if (teamScore > opponentScore) return total + 3;
    if (teamScore === opponentScore) return total + 1;
    return total;
  }, 0);
}

function getPlayerPoints(player) {
  return player.teams.reduce((total, team) => total + getTeamPoints(team), 0);
}

if (setupForm) {
  setupForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const nextPlayers = buildPlayersFromNames(participantInput.value);
    if (!nextPlayers.length) return;

    players = nextPlayers;
    savePlayers(players);
    renderAll(players);
  });
}

if (resetButton) {
  resetButton.addEventListener("click", () => {
    localStorage.removeItem(storageKey);
    players = defaultPlayers;
    renderAll(players);
  });
}
