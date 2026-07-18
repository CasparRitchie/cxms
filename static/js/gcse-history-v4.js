document.addEventListener('DOMContentLoaded', function () {
  var groups = [
    { id: 'period', label: 'Paper 1A · Period study', options: [
      ['germany', 'Germany, 1890–1945', ['Kaiser’s Germany', 'Weimar Germany', 'Nazi Germany']],
      ['america-expansion', 'America, 1840–1895', ['Expansion west', 'Civil War', 'Reconstruction']],
      ['russia', 'Russia, 1894–1945', ['Tsardom', 'Lenin', 'Stalin']],
      ['america-opportunity', 'America, 1920–1973', ['Boom', 'Depression and New Deal', 'Civil rights']]
    ]},
    { id: 'world-depth', label: 'Paper 1B · Wider world depth', options: [
      ['interwar', 'Conflict and tension, 1918–1939', ['Peacemaking', 'League of Nations', 'Origins of WWII']],
      ['ww1', 'The First World War, 1894–1918', ['Causes', 'Stalemate', 'Ending the war']],
      ['east-west', 'East and West, 1945–1972', ['Cold War origins', 'Development', 'Transformation']],
      ['asia', 'Asia, 1950–1975', ['Korea', 'Vietnam escalation', 'Ending Vietnam']],
      ['gulf-afghanistan', 'Gulf and Afghanistan, 1990–2009', ['Gulf War', '9/11 and Afghanistan', 'Iraq War']]
    ]},
    { id: 'thematic', label: 'Paper 2A · Thematic study', options: [
      ['health', 'Britain: Health and the people', ['Medieval medicine', 'Renaissance', 'Industrial', 'Modern']],
      ['power', 'Britain: Power and the people', ['Medieval', 'Early modern', 'Reform', 'Rights']],
      ['migration', 'Britain: Migration, empires and the people', ['Settlement', 'Empire', 'Migration', 'Decolonisation']]
    ]},
    { id: 'british-depth', label: 'Paper 2B · British depth study', options: [
      ['elizabeth', 'Elizabethan England, c1568–1603', ['Court and parliament', 'Life', 'Troubles', 'Historic environment']],
      ['norman', 'Norman England, c1066–c1100', ['Conquest', 'Life', 'Church', 'Historic environment']],
      ['edward', 'Edward I, 1272–1307', ['Government', 'Life', 'War', 'Historic environment']],
      ['restoration', 'Restoration England, 1660–1685', ['Crown', 'Life', 'Trade and war', 'Historic environment']]
    ]}
  ];

  var questionTypes = [
    { id: 'describe', name: 'Describe two features', marks: 4, time: 5, structure: ['Give one accurate feature.', 'Add a supporting detail.', 'Repeat for a second feature.'] },
    { id: 'ways', name: 'In what ways… Explain', marks: 8, time: 10, structure: ['Make a clear point.', 'Add precise evidence.', 'Explain how it answers the question.', 'Repeat with a second way.'] },
    { id: 'account', name: 'Write an account', marks: 8, time: 10, structure: ['Start with the earliest development.', 'Explain how it led to the next event.', 'Continue the chain.', 'Finish with the result.'] },
    { id: 'source', name: 'How useful is this source?', marks: 8, time: 10, structure: ['Use the source content.', 'Evaluate provenance.', 'Test with contextual knowledge.', 'Reach a judgement.'] },
    { id: 'interpretation', name: 'How convincing is this interpretation?', marks: 8, time: 10, structure: ['Identify the interpretation’s view.', 'Test it with knowledge.', 'Explain a limitation.', 'Reach a judgement.'] },
    { id: 'essay', name: 'How far do you agree?', marks: 16, time: 20, structure: ['Argument supporting the statement.', 'Alternative argument.', 'Compare importance.', 'Reach a justified conclusion.'] }
  ];

  var state = { course: {}, confidence: {}, weaknesses: [] };
  try {
    var saved = JSON.parse(localStorage.getItem('gcseHistoryStateV4') || '{}');
    if (saved && typeof saved === 'object') state = Object.assign(state, saved);
  } catch (e) {}

  function save() { localStorage.setItem('gcseHistoryStateV4', JSON.stringify(state)); }
  function esc(value) { return String(value).replace(/[&<>"']/g, function (c) { return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]; }); }
  function allTopics() {
    var out = [];
    groups.forEach(function (g) {
      g.options.forEach(function (o) { out.push({ id: o[0], title: o[1], parts: o[2], group: g.id, groupLabel: g.label }); });
    });
    return out;
  }

  groups.forEach(function (g) { if (!state.course[g.id]) state.course[g.id] = g.options[0][0]; });

  function renderCourse() {
    var root = document.getElementById('course-builder');
    root.innerHTML = groups.map(function (g) {
      return '<section class="course-group card"><h3>' + esc(g.label) + '</h3><div class="course-options">' +
        g.options.map(function (o) {
          return '<label class="course-option"><input type="radio" name="' + g.id + '" value="' + o[0] + '" ' + (state.course[g.id] === o[0] ? 'checked' : '') + '><span><strong>' + esc(o[1]) + '</strong><br><small>' + esc(o[2].join(' · ')) + '</small></span></label>';
        }).join('') + '</div></section>';
    }).join('');
    root.querySelectorAll('input[type="radio"]').forEach(function (input) {
      input.addEventListener('change', function () { state.course[input.name] = input.value; save(); renderOverview(); fillPracticeTopics(); renderRevision(); });
    });
    renderOverview();
  }

  function renderOverview() {
    var topics = allTopics();
    document.getElementById('course-overview').innerHTML = '<h3>Your selected course</h3><div class="course-overview-grid">' + groups.map(function (g) {
      var t = topics.find(function (x) { return x.id === state.course[g.id]; });
      return '<div class="course-tile"><small>' + esc(g.label) + '</small><strong>' + esc(t ? t.title : 'Not selected') + '</strong></div>';
    }).join('') + '</div>';
  }

  function renderTopics() {
    var query = document.getElementById('topic-search').value.toLowerCase();
    var filter = document.getElementById('topic-group-filter').value;
    var shown = allTopics().filter(function (t) {
      return (filter === 'all' || t.group === filter) && (t.title + ' ' + t.parts.join(' ')).toLowerCase().indexOf(query) !== -1;
    });
    document.getElementById('topic-grid').innerHTML = shown.map(function (t) {
      return '<article class="topic-card"><span class="badge">' + esc(t.groupLabel) + '</span><h3>' + esc(t.title) + '</h3><p><strong>Core content:</strong> ' + esc(t.parts.join(', ')) + '.</p><details><summary>Revision focus</summary><ul><li>Learn the chronology.</li><li>Memorise named evidence and dates.</li><li>Practise causes, consequences, change and significance.</li></ul></details></article>';
    }).join('') || '<p>No matching topics.</p>';
  }

  function renderQuestions(activeId) {
    var active = questionTypes.find(function (q) { return q.id === activeId; }) || questionTypes[0];
    var list = document.getElementById('question-list');
    list.innerHTML = questionTypes.map(function (q) {
      return '<button type="button" class="question-button ' + (q.id === active.id ? 'active' : '') + '" data-id="' + q.id + '"><strong>' + esc(q.name) + '</strong><br><small>' + q.marks + ' marks · ' + q.time + ' mins</small></button>';
    }).join('');
    list.querySelectorAll('button').forEach(function (button) { button.addEventListener('click', function () { renderQuestions(button.dataset.id); }); });
    document.getElementById('question-guide').innerHTML = '<span class="mark-pill">' + active.marks + ' marks · about ' + active.time + ' mins</span><h3>' + esc(active.name) + '</h3><p>Focus on the exact command word and select evidence that directly answers the enquiry.</p><div class="guide-box"><h4>Reliable structure</h4><ol>' + active.structure.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ol></div>';
  }

  function fillPracticeTopics() {
    var topics = allTopics();
    document.getElementById('practice-topic').innerHTML = groups.map(function (g) {
      var t = topics.find(function (x) { return x.id === state.course[g.id]; });
      return t ? '<option value="' + t.id + '">' + esc(t.title) + '</option>' : '';
    }).join('');
  }

  function fillQuestionTypes() {
    document.getElementById('practice-question').innerHTML = questionTypes.map(function (q) { return '<option value="' + q.id + '">' + esc(q.name) + ' (' + q.marks + ')</option>'; }).join('');
  }

  function generateQuestion() {
    var topic = allTopics().find(function (t) { return t.id === document.getElementById('practice-topic').value; });
    var q = questionTypes.find(function (x) { return x.id === document.getElementById('practice-question').value; });
    if (!topic || !q) return;
    var part = topic.parts[Math.floor(Math.random() * topic.parts.length)];
    var prompts = {
      describe: 'Describe two features of ' + part + '.',
      ways: 'In what ways did ' + part + ' affect this period? Explain your answer.',
      account: 'Write an account of how events connected with ' + part + ' developed.',
      source: 'How useful would a source about ' + part + ' be to a historian studying ' + topic.title + '?',
      interpretation: 'How convincing is an interpretation that ' + part + ' was the key development in ' + topic.title + '?',
      essay: '“' + part + ' was the most important development in this period.” How far do you agree?'
    };
    document.getElementById('practice-prompt').value = prompts[q.id];
    document.getElementById('target-time').textContent = 'Target: ' + q.time + ' minutes';
  }

  function giveFeedback() {
    var answer = document.getElementById('student-answer').value.trim();
    var q = questionTypes.find(function (x) { return x.id === document.getElementById('practice-question').value; });
    var topic = allTopics().find(function (t) { return t.id === document.getElementById('practice-topic').value; });
    if (!answer) { document.getElementById('feedback-panel').innerHTML = '<div class="empty-state"><strong>Write an answer first</strong><p>Even a rough attempt can be improved.</p></div>'; return; }
    var words = answer.split(/\s+/).length;
    var lower = answer.toLowerCase();
    var strengths = [];
    var improvements = [];
    if (words >= q.marks * 12) strengths.push('Your answer has enough development for this mark tariff.'); else improvements.push('Develop your answer further with another explained paragraph.');
    if (/\b(18|19|20)\d{2}\b/.test(answer) || /\b(Hitler|Elizabeth|William|Stalin|Roosevelt|Nazi|League)\b/.test(answer)) strengths.push('You included specific historical evidence.'); else improvements.push('Add precise names, dates, events or policies.');
    if (/because|therefore|as a result|this meant|which led/i.test(answer)) strengths.push('You explain links between evidence and the question.'); else improvements.push('Explain why each fact matters using “because”, “therefore” or “this meant”.');
    if (q.id === 'essay' && !/however|although|on the other hand|overall|ultimately/i.test(lower)) improvements.push('Include an alternative argument and a clear overall judgement.');
    state.weaknesses = [topic.title + ': ' + improvements[0]].concat(state.weaknesses || []).slice(0, 6); save();
    document.getElementById('feedback-panel').innerHTML = '<h3>Constructive feedback</h3><p><strong>' + words + ' words</strong></p><div class="feedback-section"><h4>What is working</h4><ul>' + (strengths.length ? strengths : ['You have made a useful first attempt.']).map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul></div><div class="feedback-section"><h4>Improve next</h4><ol>' + improvements.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ol></div>';
    renderRevision();
  }

  function renderRevision() {
    var topics = allTopics();
    document.getElementById('confidence-list').innerHTML = groups.map(function (g) {
      var t = topics.find(function (x) { return x.id === state.course[g.id]; });
      var current = state.confidence[t.id] || 3;
      return '<div class="confidence-row"><span>' + esc(t.title) + '</span><div class="confidence-buttons">' + [1,2,3,4,5].map(function (n) { return '<button type="button" data-topic="' + t.id + '" data-score="' + n + '" class="' + (current === n ? 'active' : '') + '">' + n + '</button>'; }).join('') + '</div></div>';
    }).join('');
    document.querySelectorAll('.confidence-buttons button').forEach(function (button) { button.addEventListener('click', function () { state.confidence[button.dataset.topic] = Number(button.dataset.score); save(); renderRevision(); }); });
    var recommendations = (state.weaknesses && state.weaknesses.length) ? state.weaknesses : ['Complete one practice answer to generate targeted revision advice.'];
    document.getElementById('revision-recommendations').innerHTML = recommendations.map(function (x, i) { return '<div class="recommendation"><strong>' + (i + 1) + '. ' + esc(x) + '</strong><p>Use a short recall quiz, correct it, then answer one exam question.</p></div>'; }).join('');
  }

  renderCourse();
  renderTopics();
  renderQuestions();
  fillPracticeTopics();
  fillQuestionTypes();
  generateQuestion();
  renderRevision();

  document.getElementById('topic-search').addEventListener('input', renderTopics);
  document.getElementById('topic-group-filter').addEventListener('change', renderTopics);
  document.getElementById('generate-question').addEventListener('click', generateQuestion);
  document.getElementById('practice-question').addEventListener('change', generateQuestion);
  document.getElementById('practice-topic').addEventListener('change', generateQuestion);
  document.getElementById('student-answer').addEventListener('input', function () {
    var text = this.value.trim();
    document.getElementById('word-count').textContent = (text ? text.split(/\s+/).length : 0) + ' words';
  });
  document.getElementById('practice-form').addEventListener('submit', function (event) { event.preventDefault(); giveFeedback(); });
});