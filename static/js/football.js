const sweepstakePlayers = [
  { name: "Joseph", team: "Brazil", points: 6, status: "Still alive" },
  { name: "Dan", team: "Argentina", points: 4, status: "Still alive" },
  { name: "Louise", team: "Spain", points: 3, status: "Still alive" },
  { name: "Helena", team: "Germany", points: 3, status: "Still alive" },
  { name: "Claire", team: "England", points: 5, status: "Still alive" },
  { name: "Sammy", team: "France", points: 6, status: "Still alive" },
  { name: "Liv", team: "Portugal", points: 4, status: "Still alive" },
  { name: "Caspar", team: "Netherlands", points: 2, status: "Needs a win" },
];

const fixtures = [
  { match: "England vs France", date: "Tonight · 20:00", owner: "Claire vs Sammy" },
  { match: "Brazil vs Spain", date: "Tomorrow · 17:00", owner: "Joseph vs Louise" },
  { match: "Argentina vs Netherlands", date: "Saturday · 20:00", owner: "Dan vs Caspar" },
];

const leaderboard = document.getElementById("leaderboard");
const fixturesList = document.getElementById("fixtures");

if (leaderboard) {
  leaderboard.innerHTML = sweepstakePlayers
    .sort((a, b) => b.points - a.points)
    .map((player, index) => `
      <article class="sweepstake-card">
        <h3>${index + 1}. ${player.name}</h3>
        <p>${player.status}</p>
        <span class="team-pill">${player.team} · ${player.points} pts</span>
      </article>
    `)
    .join("");
}

if (fixturesList) {
  fixturesList.innerHTML = fixtures
    .map((fixture) => `
      <div class="fixture-row">
        <div>
          <strong>${fixture.match}</strong>
          <p>${fixture.owner}</p>
        </div>
        <div class="fixture-date">${fixture.date}</div>
      </div>
    `)
    .join("");
}
