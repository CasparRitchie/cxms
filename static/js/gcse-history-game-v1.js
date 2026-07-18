document.addEventListener('DOMContentLoaded', function () {
  var app = document.getElementById('history-app');
  if (!app) return;

  var STORAGE_KEY = 'gcseHistoryGameV1';
  var game = { xp: 0, streak: 1, lastVisit: '', completed: {}, achievements: [], mythIndex: 0, mythCorrect: 0 };
  try {
    var saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
    if (saved && typeof saved === 'object') game = Object.assign(game, saved);
  } catch (e) {}

  var today = new Date();
  var todayKey = today.toISOString().slice(0, 10);
  if (game.lastVisit !== todayKey) {
    if (game.lastVisit) {
      var previous = new Date(game.lastVisit + 'T00:00:00');
      var days = Math.round((today - previous) / 86400000);
      game.streak = days === 1 ? (game.streak || 0) + 1 : 1;
    } else game.streak = 1;
    game.lastVisit = todayKey;
  }

  var levels = [
    { name: 'History Rookie', min: 0 },
    { name: 'Archive Explorer', min: 250 },
    { name: 'Timeline Detective', min: 600 },
    { name: 'Evidence Expert', min: 1100 },
    { name: 'Time Guardian', min: 1800 }
  ];

  var myths = [
    { statement: 'Hitler was elected Chancellor directly by the German people.', answer: false, explanation: 'Hitler was appointed Chancellor by President Hindenburg on 30 January 1933.' },
    { statement: 'The Nazis never won a majority in a free Reichstag election.', answer: true, explanation: 'They became the largest party, but did not win more than half the vote in a free Reichstag election.' },
    { statement: 'The Kapp Putsch collapsed after a general strike.', answer: true, explanation: 'Workers refused to cooperate with the putsch and the general strike helped bring it down.' },
    { statement: 'The Dawes Plan cancelled German reparations.', answer: false, explanation: 'It reorganised payments and brought US loans; it did not abolish reparations.' },
    { statement: 'The Enabling Act allowed Hitler to make laws without the Reichstag.', answer: true, explanation: 'Passed on 23 March 1933, it was central to destroying parliamentary democracy.' },
    { statement: 'The Gestapo had enough agents to watch every German constantly.', answer: false, explanation: 'The Gestapo was feared but depended heavily on reports and denunciations from the public.' }
  ];

  var missions = [
    { id: 'choose-course', title: 'Build your course', detail: 'Choose your four AQA modules.', xp: 50 },
    { id: 'open-knowledge', title: 'Open the archive', detail: 'Explore a detailed Germany knowledge card.', xp: 40 },
    { id: 'myth-three', title: 'Mythbuster rookie', detail: 'Answer three Mythbusters correctly.', xp: 100 },
    { id: 'submit-answer', title: 'Face the examiner', detail: 'Submit a practice answer for feedback.', xp: 150 },
    { id: 'repair-timeline', title: 'Repair the timeline', detail: 'Trigger and learn from a factual correction.', xp: 125 }
  ];

  function save() { localStorage.setItem(STORAGE_KEY, JSON.stringify(game)); }
  function levelForXp() {
    var current = levels[0];
    levels.forEach(function (level) { if (game.xp >= level.min) current = level; });
    return current;
  }
  function nextLevel() {
    for (var i = 0; i < levels.length; i += 1) if (levels[i].min > game.xp) return levels[i];
    return null;
  }
  function complete(id) {
    if (game.completed[id]) return;
    var mission = missions.find(function (item) { return item.id === id; });
    game.completed[id] = true;
    game.xp += mission ? mission.xp : 25;
    if (mission) toast('Mission complete: ' + mission.title + ' +' + mission.xp + ' XP');
    checkAchievements();
    save();
    renderHud();
    renderMissions();
  }
  function checkAchievements() {
    var possible = [
      { id: 'first-steps', when: Object.keys(game.completed).length >= 1, label: 'First Steps' },
      { id: 'mythbuster', when: game.mythCorrect >= 3, label: 'Mythbuster' },
      { id: 'scholar', when: game.xp >= 500, label: 'Rising Historian' },
      { id: 'streak-three', when: game.streak >= 3, label: '3-Day Streak' }
    ];
    possible.forEach(function (item) {
      if (item.when && game.achievements.indexOf(item.id) === -1) {
        game.achievements.push(item.id);
        toast('Achievement unlocked: ' + item.label);
      }
    });
  }
  function toast(message) {
    var box = document.createElement('div');
    box.className = 'history-game-toast';
    box.textContent = message;
    document.body.appendChild(box);
    requestAnimationFrame(function () { box.classList.add('show'); });
    setTimeout(function () { box.classList.remove('show'); setTimeout(function () { box.remove(); }, 300); }, 2600);
  }

  var hud = document.createElement('section');
  hud.className = 'history-game-hud';
  hud.innerHTML = '<div><span class="game-label">YOUR HISTORIAN</span><strong id="game-level"></strong></div><div class="game-xp-wrap"><div class="game-xp-track"><span id="game-xp-bar"></span></div><small id="game-xp-copy"></small></div><div class="game-stat"><strong id="game-streak"></strong><span>day streak</span></div><button type="button" id="game-missions-button">View missions</button>';
  app.insertBefore(hud, app.querySelector('.history-tabs'));

  var missionPanel = document.createElement('section');
  missionPanel.className = 'history-game-panel card';
  missionPanel.id = 'history-game-missions';
  missionPanel.hidden = true;
  hud.insertAdjacentElement('afterend', missionPanel);

  var mythPanel = document.createElement('section');
  mythPanel.className = 'mythbuster-card card';
  mythPanel.innerHTML = '<div class="myth-header"><div><span class="game-label">60-SECOND CHALLENGE</span><h3>🔥 History Mythbusters</h3></div><strong id="myth-score"></strong></div><p id="myth-statement" class="myth-statement"></p><div class="myth-actions"><button type="button" data-answer="true">TRUE</button><button type="button" data-answer="false">FALSE</button></div><div id="myth-result" class="myth-result" aria-live="polite"></div>';
  var coursePanel = document.getElementById('course-panel');
  coursePanel.insertBefore(mythPanel, coursePanel.querySelector('.course-builder'));

  function renderHud() {
    var level = levelForXp();
    var next = nextLevel();
    document.getElementById('game-level').textContent = level.name + ' · ' + game.xp + ' XP';
    document.getElementById('game-streak').textContent = '🔥 ' + game.streak;
    var start = level.min;
    var end = next ? next.min : Math.max(game.xp, start + 500);
    var pct = Math.max(0, Math.min(100, ((game.xp - start) / (end - start)) * 100));
    document.getElementById('game-xp-bar').style.width = pct + '%';
    document.getElementById('game-xp-copy').textContent = next ? (next.min - game.xp) + ' XP to ' + next.name : 'Maximum rank reached';
  }
  function renderMissions() {
    missionPanel.innerHTML = '<div class="mission-heading"><div><span class="game-label">CAMPAIGN MODE</span><h3>Your missions</h3></div><button type="button" id="close-missions">Close</button></div><div class="mission-grid">' + missions.map(function (mission) {
      var done = !!game.completed[mission.id];
      return '<article class="mission ' + (done ? 'done' : '') + '"><span>' + (done ? '✓' : '○') + '</span><div><strong>' + mission.title + '</strong><p>' + mission.detail + '</p></div><b>+' + mission.xp + ' XP</b></article>';
    }).join('') + '</div>';
    document.getElementById('close-missions').addEventListener('click', function () { missionPanel.hidden = true; });
  }
  function renderMyth() {
    var myth = myths[game.mythIndex % myths.length];
    document.getElementById('myth-statement').textContent = myth.statement;
    document.getElementById('myth-score').textContent = game.mythCorrect + ' correct';
    document.getElementById('myth-result').innerHTML = '';
    mythPanel.querySelectorAll('.myth-actions button').forEach(function (button) { button.disabled = false; });
  }

  document.getElementById('game-missions-button').addEventListener('click', function () {
    missionPanel.hidden = !missionPanel.hidden;
    if (!missionPanel.hidden) renderMissions();
  });

  mythPanel.querySelectorAll('.myth-actions button').forEach(function (button) {
    button.addEventListener('click', function () {
      var myth = myths[game.mythIndex % myths.length];
      var chosen = button.dataset.answer === 'true';
      var correct = chosen === myth.answer;
      mythPanel.querySelectorAll('.myth-actions button').forEach(function (item) { item.disabled = true; });
      document.getElementById('myth-result').innerHTML = '<strong>' + (correct ? '✅ Correct! +25 XP' : '🚨 Timeline alert!') + '</strong><p>' + myth.explanation + '</p><button type="button" id="next-myth">Next challenge</button>';
      if (correct) { game.mythCorrect += 1; game.xp += 25; }
      if (game.mythCorrect >= 3) complete('myth-three');
      checkAchievements(); save(); renderHud();
      document.getElementById('next-myth').addEventListener('click', function () { game.mythIndex += 1; save(); renderMyth(); });
    });
  });

  document.querySelectorAll('#course-builder input[type="radio"]').forEach(function (input) {
    input.addEventListener('change', function () { complete('choose-course'); });
  });
  document.addEventListener('toggle', function (event) {
    if (event.target.matches('.topic-card details') && event.target.open) complete('open-knowledge');
  }, true);

  var form = document.getElementById('practice-form');
  if (form) form.addEventListener('submit', function () {
    var answer = document.getElementById('student-answer');
    if (answer && answer.value.trim()) complete('submit-answer');
  });

  var feedback = document.getElementById('feedback-panel');
  if (feedback && window.MutationObserver) {
    new MutationObserver(function () {
      var text = feedback.textContent.toLowerCase();
      if (text.indexOf('correction') !== -1 || text.indexOf('historical error') !== -1 || text.indexOf('timeline alert') !== -1) {
        complete('repair-timeline');
        feedback.classList.add('timeline-repair-active');
      }
    }).observe(feedback, { childList: true, subtree: true });
  }

  renderHud(); renderMissions(); renderMyth(); checkAchievements(); save();
});