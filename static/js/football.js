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
    name: "Henela",
    teams: ["France", "Colombia", "Ecuador", "Panama", "Jordan", "New Zealand"],
  },
  {
    name: "Claire",
    teams: ["Argentina", "Switzerland", "Iran", "Paraguay", "Czechia", "Bosnia & Herzegovina"],
  },
  {
    name: "Caspar",
    teams: ["Netherlands", "Uruguay", "Japan", "Algeria", "Sweden", "DR Congo"],
  },
].map((player) => ({
  ...player,
  status: "Still alive",
}));

let fixtures = [];

const teamAliases = {
  "Czech Republic": "Czechia",
  "Bosnia-Herzegovina": "Bosnia & Herzegovina",
  "Bosnia and Herzegovina": "Bosnia & Herzegovina",
  "Cape Verde": "Cabo Verde",
  "Ivory Coast": "Côte d’Ivoire",
  "Curacao": "Curaçao",
  "Turkey": "Türkiye",
};

function normaliseTeamName(teamName) {
  return teamAliases[teamName] || teamName;
}

async function loadFixtures() {
  try {
    const response = await fetch("/api/football/worldcup/fixtures");
    const data = await response.json();

    if (data.ok && Array.isArray(data.fixtures)) {
      fixtures = data.fixtures;
      renderAll(players);
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
const raceChart = document.getElementById("race-chart");
const teamSummary = document.getElementById("team-summary");
const playerFormTable = document.getElementById("player-form-table");
const timezoneLabel = document.getElementById("timezone-label");

function loadPlayers() {
  const saved = localStorage.getItem(storageKey);
  if (!saved) return defaultPlayers;

  try {
    const parsed = JSON.parse(saved);

    if (!Array.isArray(parsed) || !parsed.length) {
      return defaultPlayers;
    }

    const hasOldOneTeamFormat = parsed.some((player) => !Array.isArray(player.teams));

    return hasOldOneTeamFormat ? defaultPlayers : parsed;
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
    teams: [shuffledTeams[index % shuffledTeams.length]],
    status: "Ready to play",
  }));
}

function formatMatchScore(fixture) {
  if (fixture.status !== "complete") return "vs";
  return `${fixture.homeScore}–${fixture.awayScore}`;
}

function getFixtureSortTime(fixture) {
  return new Date(fixture.kickoff).getTime();
}

function renderSummary(players) {
  if (summaryParticipants) summaryParticipants.textContent = players.length;

  if (summaryTeams) {
    const allTeams = players.flatMap((player) => player.teams || []);
    summaryTeams.textContent = new Set(allTeams).size;
  }
}

function getTeamStats(teamName) {
  const normalisedTeam = normaliseTeamName(teamName);

  return fixtures.reduce(
    (stats, fixture) => {
      if (fixture.status !== "complete") return stats;
      if (fixture.homeScore === null || fixture.awayScore === null) return stats;

      const homeTeam = normaliseTeamName(fixture.home);
      const awayTeam = normaliseTeamName(fixture.away);

      const isHome = homeTeam === normalisedTeam;
      const isAway = awayTeam === normalisedTeam;

      if (!isHome && !isAway) return stats;

      const goalsFor = isHome ? fixture.homeScore : fixture.awayScore;
      const goalsAgainst = isHome ? fixture.awayScore : fixture.homeScore;

      stats.played += 1;
      stats.goalsFor += goalsFor;
      stats.goalsAgainst += goalsAgainst;

      if (goalsFor > goalsAgainst) stats.wins += 1;
      else if (goalsFor === goalsAgainst) stats.draws += 1;
      else stats.losses += 1;

      return stats;
    },
    {
      played: 0,
      wins: 0,
      draws: 0,
      losses: 0,
      goalsFor: 0,
      goalsAgainst: 0,
    }
  );
}

function getPlayerStats(player) {
  const stats = player.teams.reduce(
    (totals, team) => {
      const teamStats = getTeamStats(team);

      totals.played += teamStats.played;
      totals.wins += teamStats.wins;
      totals.draws += teamStats.draws;
      totals.losses += teamStats.losses;
      totals.goalsFor += teamStats.goalsFor;
      totals.goalsAgainst += teamStats.goalsAgainst;

      return totals;
    },
    {
      played: 0,
      wins: 0,
      draws: 0,
      losses: 0,
      goalsFor: 0,
      goalsAgainst: 0,
    }
  );

  stats.goalDifference = stats.goalsFor - stats.goalsAgainst;
  stats.points = stats.wins * 3 + stats.draws;

  return stats;
}

function renderLeaderboard(players) {
  if (!leaderboard) return;

  const rows = [...players]
    .map((player) => ({
      player,
      stats: getPlayerStats(player),
    }))
    .sort((a, b) =>
      b.stats.points - a.stats.points ||
      b.stats.goalDifference - a.stats.goalDifference ||
      b.stats.goalsFor - a.stats.goalsFor
    );

  leaderboard.innerHTML = `
    <div class="sweepstake-table">
      <div class="sweepstake-table-row sweepstake-table-header">
        <span>Player</span>
        <span>Played</span>
        <span>Won</span>
        <span>Drawn</span>
        <span>Lost</span>
        <span>Goals Scored</span>
        <span>Goals Against</span>
        <span>Goal Difference</span>
        <span>Points</span>
      </div>

      ${rows.map(({ player, stats }, index) => `
        <div class="sweepstake-table-row">
          <span><strong>${index + 1}. ${player.name}</strong></span>
          <span>${stats.played}</span>
          <span>${stats.wins}</span>
          <span>${stats.draws}</span>
          <span>${stats.losses}</span>
          <span>${stats.goalsFor}</span>
          <span>${stats.goalsAgainst}</span>
          <span>${stats.goalDifference > 0 ? "+" : ""}${stats.goalDifference}</span>
          <span><strong>${stats.points}</strong></span>
        </div>
      `).join("")}
    </div>
  `;
}

function getTeamOwner(teamName) {
  const normalisedTeam = normaliseTeamName(teamName);

  return players.find((player) =>
    player.teams.some((team) => normaliseTeamName(team) === normalisedTeam)
  );
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

function getTeamForm(teamName) {
  const normalisedTeam = normaliseTeamName(teamName);

  return fixtures
    .filter((fixture) => {
      if (fixture.status !== "complete") return false;
      return (
        normaliseTeamName(fixture.home) === normalisedTeam ||
        normaliseTeamName(fixture.away) === normalisedTeam
      );
    })
    .map((fixture) => {
      const isHome = normaliseTeamName(fixture.home) === normalisedTeam;
      const goalsFor = isHome ? fixture.homeScore : fixture.awayScore;
      const goalsAgainst = isHome ? fixture.awayScore : fixture.homeScore;

      if (goalsFor > goalsAgainst) return "W";
      if (goalsFor === goalsAgainst) return "D";
      return "L";
    });
}

function renderFormDots(teamName) {
  const form = getTeamForm(teamName);

  if (!form.length) {
    return `<span class="form-dot form-empty" title="Not played yet">–</span>`;
  }

  return form
    .map((result) => {
      const className =
        result === "W" ? "form-win" :
        result === "D" ? "form-draw" :
        "form-loss";

      return `<span class="form-dot ${className}" title="${result}">${result}</span>`;
    })
    .join("");
}

function renderTeamSummary(players) {
  if (!teamSummary) return;

  const ordered = [...players].sort((a, b) =>
    getPlayerPoints(b) - getPlayerPoints(a)
  );

  teamSummary.innerHTML = ordered.map((player, index) => `
    <article class="sweepstake-card">
      <div class="rank-badge">${index + 1}</div>
      <h3>${player.name}</h3>
      <p><strong>${getPlayerPoints(player)} pts</strong></p>

      <div class="team-summary-list">
        ${player.teams.map((team) => `
          <div class="team-summary-row">
            <span class="team-summary-name">${team}</span>
            <span class="team-summary-form">${renderFormDots(team)}</span>
            <strong>${getTeamPoints(team)} pts</strong>
          </div>
        `).join("")}
      </div>
    </article>
  `).join("");
}

function buildRaceSnapshots(players) {
  const completedFixtures = [...fixtures]
    .filter((fixture) => fixture.status === "complete")
    .sort((a, b) => getFixtureSortTime(a) - getFixtureSortTime(b));

  const snapshots = [
    {
      label: "Start",
      fixtureSet: [],
    },
    ...completedFixtures.map((fixture, index) => ({
      label: `${index + 1}. ${fixture.home} ${fixture.homeScore}–${fixture.awayScore} ${fixture.away}`,
      shortLabel: `${index + 1}`,
      fixtureSet: completedFixtures.slice(0, index + 1),
      fixture,
    })),
  ];

  return snapshots.map((snapshot) => ({
    ...snapshot,
    standings: players
      .map((player) => {
        const stats = getPlayerStatsForFixtures(player, snapshot.fixtureSet);

        return {
          name: player.name,
          points: stats.points,
          stats,
        };
      })
      .sort((a, b) =>
        b.points - a.points ||
        b.stats.goalDifference - a.stats.goalDifference ||
        b.stats.goalsFor - a.stats.goalsFor
      ),
  }));
}

function getTeamStatsForFixtures(teamName, fixtureSet) {
  const normalisedTeam = normaliseTeamName(teamName);

  return fixtureSet.reduce(
    (stats, fixture) => {
      if (fixture.status !== "complete") return stats;
      if (fixture.homeScore === null || fixture.awayScore === null) return stats;

      const homeTeam = normaliseTeamName(fixture.home);
      const awayTeam = normaliseTeamName(fixture.away);

      const isHome = homeTeam === normalisedTeam;
      const isAway = awayTeam === normalisedTeam;

      if (!isHome && !isAway) return stats;

      const goalsFor = isHome ? fixture.homeScore : fixture.awayScore;
      const goalsAgainst = isHome ? fixture.awayScore : fixture.homeScore;

      stats.played += 1;
      stats.goalsFor += goalsFor;
      stats.goalsAgainst += goalsAgainst;

      if (goalsFor > goalsAgainst) stats.wins += 1;
      else if (goalsFor === goalsAgainst) stats.draws += 1;
      else stats.losses += 1;

      return stats;
    },
    {
      played: 0,
      wins: 0,
      draws: 0,
      losses: 0,
      goalsFor: 0,
      goalsAgainst: 0,
    }
  );
}

function getPlayerStatsForFixtures(player, fixtureSet) {
  const stats = player.teams.reduce(
    (totals, team) => {
      const teamStats = getTeamStatsForFixtures(team, fixtureSet);

      totals.played += teamStats.played;
      totals.wins += teamStats.wins;
      totals.draws += teamStats.draws;
      totals.losses += teamStats.losses;
      totals.goalsFor += teamStats.goalsFor;
      totals.goalsAgainst += teamStats.goalsAgainst;

      return totals;
    },
    {
      played: 0,
      wins: 0,
      draws: 0,
      losses: 0,
      goalsFor: 0,
      goalsAgainst: 0,
    }
  );

  stats.goalDifference = stats.goalsFor - stats.goalsAgainst;
  stats.points = stats.wins * 3 + stats.draws;

  return stats;
}

function renderRaceChart(players) {
  if (!raceChart) return;

  const snapshots = buildRaceSnapshots(players);

  if (snapshots.length <= 1) {
    raceChart.innerHTML = `
      <div class="race-empty">
        Race chart will appear once completed scores are added.
      </div>
    `;
    return;
  }

  const width = 1000;
  const height = 420;
  const padding = { top: 28, right: 150, bottom: 70, left: 52 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;

  const maxPoints = Math.max(
    1,
    ...snapshots.flatMap((snapshot) =>
      snapshot.standings.map((standing) => standing.points)
    )
  );

  const playerNames = players.map((player) => player.name);
  const playerIndex = Object.fromEntries(
    playerNames.map((name, index) => [name, index])
  );

  const xForIndex = (index) =>
    padding.left + (index / (snapshots.length - 1)) * plotWidth;

  const yForPoints = (points) =>
    padding.top + plotHeight - (points / maxPoints) * plotHeight;

  const lines = playerNames.map((name) => {
    const points = snapshots.map((snapshot, index) => {
      const standing = snapshot.standings.find((item) => item.name === name);
      return `${xForIndex(index)},${yForPoints(standing?.points || 0)}`;
    }).join(" ");

    const lastStanding = snapshots[snapshots.length - 1].standings.find(
      (item) => item.name === name
    );

    const lastX = xForIndex(snapshots.length - 1);
    const lastY = yForPoints(lastStanding?.points || 0);

    return `
      <polyline class="race-line race-line-${playerIndex[name] % 8}" points="${points}" />
      <text class="race-label" x="${lastX + 10}" y="${lastY + 4}">${name}</text>
    `;
  }).join("");

  const tickCount = Math.min(maxPoints, 6);
  const yTicks = Array.from({ length: tickCount + 1 }, (_, index) => {
    const value = Math.round((maxPoints / tickCount) * index);
    const y = yForPoints(value);

    return `
      <line class="race-grid-line" x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" />
      <text class="race-axis-label" x="${padding.left - 12}" y="${y + 4}" text-anchor="end">${value}</text>
    `;
  }).join("");

  const xTicks = snapshots
    .filter((snapshot, index) =>
      index === 0 || index === snapshots.length - 1 || index % 4 === 0
    )
    .map((snapshot) => {
      const index = snapshots.indexOf(snapshot);
      const x = xForIndex(index);

      return `
        <line class="race-grid-line" x1="${x}" y1="${padding.top}" x2="${x}" y2="${height - padding.bottom}" />
        <text class="race-axis-label" x="${x}" y="${height - padding.bottom + 24}" text-anchor="middle">${snapshot.shortLabel || "Start"}</text>
      `;
    }).join("");

  const latest = snapshots[snapshots.length - 1];
  const leader = latest.standings[0];

  const latestMatch = latest.fixture
    ? `${latest.fixture.home} ${latest.fixture.homeScore}–${latest.fixture.awayScore} ${latest.fixture.away}`
    : "Start";

  raceChart.innerHTML = `
    <div class="race-chart-summary">
      <div>
        <span class="small-label">Current leader</span>
        <h3>${leader.name} · ${leader.points} pts</h3>
      </div>
      <div>
        <span class="small-label">Latest result included</span>
        <p>${latestMatch}</p>
      </div>
    </div>

    <div class="race-chart-scroll">
      <svg class="race-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Sweepstake race chart">
        ${yTicks}
        ${xTicks}
        <line class="race-axis" x1="${padding.left}" y1="${height - padding.bottom}" x2="${width - padding.right}" y2="${height - padding.bottom}" />
        <line class="race-axis" x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${height - padding.bottom}" />
        ${lines}
        <text class="race-axis-title" x="${padding.left}" y="${height - 20}">Completed match number</text>
        <text class="race-axis-title" x="18" y="${padding.top}" transform="rotate(-90 18 ${padding.top})">Points</text>
      </svg>
    </div>
  `;
}

function renderPlayerFormTable(players) {
  if (!playerFormTable) return;

  const completedFixtures = [...fixtures]
    .filter((fixture) => fixture.status === "complete")
    .sort((a, b) => getFixtureSortTime(a) - getFixtureSortTime(b));

  playerFormTable.innerHTML = `
    <div class="player-form-table">
      ${players.map((player) => {
        const playerResults = completedFixtures.flatMap((fixture) => {
          const results = [];

          const ownsHome = player.teams.some(
            (team) => normaliseTeamName(team) === normaliseTeamName(fixture.home)
          );

          const ownsAway = player.teams.some(
            (team) => normaliseTeamName(team) === normaliseTeamName(fixture.away)
          );

          if (ownsHome) {
            const result =
              fixture.homeScore > fixture.awayScore ? "W" :
              fixture.homeScore === fixture.awayScore ? "D" :
              "L";

            results.push({
              result,
              team: fixture.home,
              fixture,
            });
          }

          if (ownsAway) {
            const result =
              fixture.awayScore > fixture.homeScore ? "W" :
              fixture.awayScore === fixture.homeScore ? "D" :
              "L";

            results.push({
              result,
              team: fixture.away,
              fixture,
            });
          }

          return results;
        });

        return `
          <div class="player-form-row">
            <strong>${player.name}</strong>

            <div class="player-form-dots">
              ${playerResults.map(({ result, team, fixture }) => {
                const className =
                  result === "W" ? "form-win" :
                  result === "D" ? "form-draw" :
                  "form-loss";

                return `
                  <span
                    class="form-dot ${className}"
                    title="${player.name}: ${team} ${result} (${fixture.home} ${fixture.homeScore}–${fixture.awayScore} ${fixture.away})"
                  >
                    ${result}
                  </span>
                `;
              }).join("")}
            </div>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function renderTimezoneLabel() {
  if (!timezoneLabel) return;

  const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;

  // Europe/Paris -> Paris
  // America/New_York -> New York
  const city = timeZone.split("/").pop().replace(/_/g, " ");

  // Get BST / CEST / EDT etc.
  const abbreviation = new Intl.DateTimeFormat("en", {
    timeZone,
    timeZoneName: "short",
  })
    .formatToParts(new Date())
    .find(part => part.type === "timeZoneName")?.value || "";

  timezoneLabel.textContent =
    `Times shown in your local timezone (${city}${abbreviation ? ` • ${abbreviation}` : ""})`;
}

function renderFixtures() {
  if (!fixturesList) return;

  const sortedFixtures = [...fixtures].sort(
    (a, b) => getFixtureSortTime(a) - getFixtureSortTime(b)
  );

  fixturesList.innerHTML = `
    <div class="fixture-table">
      ${sortedFixtures.map((fixture) => {
        const kickoff = new Date(fixture.kickoff).toLocaleString(undefined, {
          weekday: "short",
          day: "numeric",
          month: "short",
          hour: "2-digit",
          minute: "2-digit",
        });

        const ownerLabel = getFixtureOwnerLabel(fixture);
        const score = fixture.status === "complete"
          ? `${fixture.homeScore}–${fixture.awayScore}`
          : "vs";

        return `
          <div class="fixture-table-row ${fixture.status === "complete" ? "is-complete" : ""}">
            <div>
              <strong>${fixture.home}</strong>
              <span class="fixture-owner">${getTeamOwner(fixture.home)?.name || "Unowned"}</span>
            </div>

            <div class="fixture-score">${score}</div>

            <div>
              <strong>${fixture.away}</strong>
              <span class="fixture-owner">${getTeamOwner(fixture.away)?.name || "Unowned"}</span>
            </div>

            <div class="fixture-meta">
              <span>${fixture.stage}</span>
              <span>${kickoff}</span>
              <span>${ownerLabel}</span>
            </div>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function renderAll(players) {
  renderSummary(players);
  renderLeaderboard(players);
  renderRaceChart(players);
  renderTeamSummary(players);
  renderFixtures();
  renderTimezoneLabel();

  if (participantInput) {
    participantInput.value = players.map((player) => player.name).join("\n");
  }
}

let players = loadPlayers();
renderAll(players);
loadFixtures();

function getTeamPoints(teamName) {
  const normalisedTeam = normaliseTeamName(teamName);

  return fixtures.reduce((total, fixture) => {
    if (fixture.status !== "complete") return total;
    if (fixture.homeScore === null || fixture.awayScore === null) return total;

    const homeTeam = normaliseTeamName(fixture.home);
    const awayTeam = normaliseTeamName(fixture.away);

    const isHome = homeTeam === normalisedTeam;
    const isAway = awayTeam === normalisedTeam;

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
