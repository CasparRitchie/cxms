document.addEventListener('DOMContentLoaded', function () {
  var esc = function (v) { return String(v).replace(/[&<>"']/g, function (c) { return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]; }); };
  var state = { confidence: {}, weaknesses: [] };
  try { state = Object.assign(state, JSON.parse(localStorage.getItem('gcseHistoryGermanyV5') || '{}')); } catch (e) {}
  var save = function () { localStorage.setItem('gcseHistoryGermanyV5', JSON.stringify(state)); };

  var questionTypes = [
    {id:'describe', name:'Describe two features', marks:4, time:5, needs:['two separate accurate features','supporting detail']},
    {id:'ways', name:'In what ways… Explain', marks:8, time:10, needs:['two developed ways','precise evidence','explained link to the question']},
    {id:'interpretation', name:'How convincing is this interpretation?', marks:8, time:10, needs:['interpretation view','contextual knowledge','evaluation','overall judgement']},
    {id:'essay', name:'How far do you agree?', marks:16, time:20, needs:['supporting argument','alternative argument','precise evidence','comparative judgement']}
  ];

  fetch('/static/data/gcse-history/germany-1890-1945.json?v=1').then(function (r) {
    if (!r.ok) throw new Error('Knowledge store could not be loaded');
    return r.json();
  }).then(init).catch(function (err) {
    document.getElementById('feedback-panel').innerHTML = '<div class="empty-state"><strong>Knowledge store error</strong><p>' + esc(err.message) + '</p></div>';
  });

  function init(course) {
    var subtopics = [];
    course.parts.forEach(function (part) { part.subtopics.forEach(function (s) { s.partTitle = part.title; subtopics.push(s); }); });

    renderCourse(course);
    renderKnowledgeLibrary(course, subtopics);
    renderQuestionCoach();
    preparePractice(course, subtopics);
    renderRevision(subtopics);

    document.getElementById('topic-search').addEventListener('input', function () { renderKnowledgeLibrary(course, subtopics); });
    document.getElementById('topic-group-filter').innerHTML = '<option value="all">All Germany sections</option>' + course.parts.map(function (p) { return '<option value="' + p.id + '">' + esc(p.title) + '</option>'; }).join('');
    document.getElementById('topic-group-filter').addEventListener('change', function () { renderKnowledgeLibrary(course, subtopics); });
  }

  function renderCourse(course) {
    document.getElementById('course-builder').innerHTML = '<article class="card knowledge-hero"><span class="badge">Teacher-feedback prototype</span><h3>' + esc(course.title) + '</h3><p>This first content-rich module contains ' + course.parts.reduce(function (n,p) { return n + p.subtopics.length; },0) + ' detailed subtopics, key facts and misconception checks.</p>' + course.parts.map(function (p) { return '<div class="course-part"><strong>' + esc(p.title) + '</strong><p>' + esc(p.overview) + '</p></div>'; }).join('') + '</article>';
    document.getElementById('course-overview').innerHTML = '<h3>What the assessment can now check</h3><div class="course-overview-grid"><div class="course-tile"><strong>Historical accuracy</strong><small>Known misconceptions and corrections</small></div><div class="course-tile"><strong>Relevant knowledge</strong><small>Named facts, people, dates and policies</small></div><div class="course-tile"><strong>Explanation</strong><small>Cause, consequence and significance</small></div><div class="course-tile"><strong>Exam technique</strong><small>Requirements for the chosen question</small></div></div>';
  }

  function renderKnowledgeLibrary(course, subtopics) {
    var q = document.getElementById('topic-search').value.toLowerCase();
    var filter = document.getElementById('topic-group-filter').value;
    var shown = subtopics.filter(function (s) {
      var part = course.parts.find(function (p) { return p.title === s.partTitle; });
      var text = [s.title,s.summary].concat(s.keyFacts,s.keywords).join(' ').toLowerCase();
      return (filter === 'all' || (part && part.id === filter)) && text.indexOf(q) !== -1;
    });
    document.getElementById('topic-grid').innerHTML = shown.map(function (s) {
      return '<article class="topic-card"><span class="badge">' + esc(s.partTitle) + '</span><h3>' + esc(s.title) + '</h3><p>' + esc(s.summary) + '</p><details><summary>Key knowledge</summary><ul>' + s.keyFacts.map(function (f) { return '<li>' + esc(f) + '</li>'; }).join('') + '</ul></details><details><summary>Key vocabulary</summary><p>' + esc(s.keywords.join(' · ')) + '</p></details>' + (s.misconceptions.length ? '<details><summary>Common misconceptions</summary><ul>' + s.misconceptions.map(function (m) { return '<li>' + esc(m.correction) + '</li>'; }).join('') + '</ul></details>' : '') + '</article>';
    }).join('') || '<p>No matching knowledge.</p>';
  }

  function renderQuestionCoach(activeId) {
    var active = questionTypes.find(function (x) { return x.id === activeId; }) || questionTypes[0];
    var list = document.getElementById('question-list');
    list.innerHTML = questionTypes.map(function (x) { return '<button type="button" class="question-button ' + (x.id === active.id ? 'active' : '') + '" data-id="' + x.id + '"><strong>' + esc(x.name) + '</strong><br><small>' + x.marks + ' marks · ' + x.time + ' mins</small></button>'; }).join('');
    list.querySelectorAll('button').forEach(function (b) { b.addEventListener('click', function () { renderQuestionCoach(b.dataset.id); }); });
    document.getElementById('question-guide').innerHTML = '<span class="mark-pill">' + active.marks + ' marks · about ' + active.time + ' mins</span><h3>' + esc(active.name) + '</h3><p>The feedback checks both historical content and whether the response meets these requirements.</p><div class="guide-box"><h4>What the examiner needs</h4><ul>' + active.needs.map(function (n) { return '<li>' + esc(n) + '</li>'; }).join('') + '</ul></div>';
  }

  function preparePractice(course, subtopics) {
    var form = document.getElementById('practice-form');
    var topicLabel = document.getElementById('practice-topic').closest('label');
    topicLabel.innerHTML = 'Knowledge focus<select id="practice-topic"></select>';
    var select = document.getElementById('practice-topic');
    select.innerHTML = subtopics.map(function (s) { return '<option value="' + s.id + '">' + esc(s.title) + '</option>'; }).join('');
    document.getElementById('practice-question').innerHTML = questionTypes.map(function (q) { return '<option value="' + q.id + '">' + esc(q.name) + ' (' + q.marks + ')</option>'; }).join('');
    var preview = document.createElement('div'); preview.id = 'knowledge-preview'; preview.className = 'guide-box';
    form.insertBefore(preview, document.querySelector('.prompt-actions'));
    function update() { generateQuestion(subtopics); renderKnowledgePreview(subtopics); }
    select.addEventListener('change', update); document.getElementById('practice-question').addEventListener('change', update);
    document.getElementById('generate-question').addEventListener('click', function () { generateQuestion(subtopics); });
    document.getElementById('practice-form').addEventListener('submit', function (e) { e.preventDefault(); assess(subtopics); });
    var answer = document.getElementById('student-answer');
    answer.addEventListener('input', function () { var t = answer.value.trim(); document.getElementById('word-count').textContent = (t ? t.split(/\s+/).length : 0) + ' words'; });
    update();
  }

  function getSubtopic(subtopics) { return subtopics.find(function (s) { return s.id === document.getElementById('practice-topic').value; }); }
  function getQuestionType() { return questionTypes.find(function (q) { return q.id === document.getElementById('practice-question').value; }); }
  function renderKnowledgePreview(subtopics) {
    var s = getSubtopic(subtopics); if (!s) return;
    document.getElementById('knowledge-preview').innerHTML = '<h4>Knowledge this question may draw on</h4><p>' + esc(s.summary) + '</p><small>' + esc(s.keywords.join(' · ')) + '</small>';
  }
  function generateQuestion(subtopics) {
    var s = getSubtopic(subtopics), q = getQuestionType(); if (!s || !q) return;
    var prompts = {
      describe:'Describe two features of ' + s.title + '.',
      ways:'In what ways did ' + s.title + ' affect Germany? Explain your answer.',
      interpretation:'How convincing is an interpretation that ' + s.title + ' was the key development in Germany during this period?',
      essay:'“' + s.title + ' was the most important reason for change in Germany.” How far do you agree?'
    };
    document.getElementById('practice-prompt').value = prompts[q.id];
    document.getElementById('target-time').textContent = 'Target: ' + q.time + ' minutes';
  }

  function assess(subtopics) {
    var s = getSubtopic(subtopics), q = getQuestionType();
    var answer = document.getElementById('student-answer').value.trim();
    if (!answer) { document.getElementById('feedback-panel').innerHTML = '<div class="empty-state"><strong>Write an answer first</strong></div>'; return; }
    var lower = answer.toLowerCase();
    var matchedFacts = s.keyFacts.filter(function (fact) {
      var tokens = fact.toLowerCase().replace(/[^a-z0-9 ]/g,'').split(/\s+/).filter(function (x) { return x.length > 4; });
      return tokens.filter(function (x) { return lower.indexOf(x) !== -1; }).length >= Math.min(2, tokens.length);
    });
    var keywordHits = s.keywords.filter(function (k) { return lower.indexOf(k.toLowerCase()) !== -1; });
    var corrections = [];
    s.misconceptions.forEach(function (m) { if (m.triggers.some(function (t) { return lower.indexOf(t.toLowerCase()) !== -1; })) corrections.push(m.correction); });
    var explanationHits = (lower.match(/because|therefore|this meant|as a result|which led|consequently/g) || []).length;
    var balance = /however|although|on the other hand|whereas|overall|ultimately/.test(lower);
    var strengths = [];
    if (matchedFacts.length) strengths.push('You used knowledge that matches the content store: ' + matchedFacts.slice(0,2).join(' '));
    if (keywordHits.length >= 2) strengths.push('You used relevant specialist vocabulary: ' + keywordHits.slice(0,5).join(', ') + '.');
    if (explanationHits >= 2) strengths.push('You repeatedly explained why the evidence mattered.');
    var priorities = [];
    if (!matchedFacts.length) priorities.push('Add precise knowledge from this subtopic rather than relying on general statements.');
    if (explanationHits < 2) priorities.push('Explain the link between each fact and the exact question.');
    if ((q.id === 'essay' || q.id === 'interpretation') && !balance) priorities.push('Test an alternative view and finish with a comparative judgement.');
    if (q.id === 'describe' && !/first|one|second|another/.test(lower)) priorities.push('Make the two required features unmistakably separate.');
    var omitted = s.keyFacts.filter(function (f) { return matchedFacts.indexOf(f) === -1; }).slice(0,3);
    state.weaknesses = [s.title + ': ' + (corrections[0] || priorities[0] || 'deepen precise knowledge')].concat(state.weaknesses).slice(0,8); save();
    document.getElementById('feedback-panel').innerHTML = '<h3>Grounded teacher-style feedback</h3><p><strong>Historical accuracy and knowledge</strong> are assessed separately from answer structure.</p>' + (corrections.length ? '<div class="feedback-section correction-box"><h4>Corrections</h4><ul>' + corrections.map(function (x) { return '<li><strong>This needs correcting:</strong> ' + esc(x) + '</li>'; }).join('') + '</ul></div>' : '<div class="feedback-section"><h4>No stored misconception detected</h4><p>This does not guarantee every claim is correct, but no known misconception rule was triggered.</p></div>') + '<div class="feedback-section"><h4>What is working</h4><ul>' + (strengths.length ? strengths : ['You have made a useful attempt that can now be developed.']).map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul></div><div class="feedback-section"><h4>Improve next</h4><ol>' + priorities.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ol></div><div class="feedback-section"><h4>Relevant knowledge you could add</h4><ul>' + omitted.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul></div><div class="feedback-section"><p><strong>Current limitation:</strong> this is grounded rule-based feedback, not yet a full AI examiner. It can correct stored misconceptions and identify missing expected knowledge, but cannot reliably verify every possible sentence.</p></div>';
    renderRevision(subtopics);
  }

  function renderRevision(subtopics) {
    document.getElementById('confidence-list').innerHTML = subtopics.map(function (s) { var score = state.confidence[s.id] || 3; return '<div class="confidence-row"><span>' + esc(s.title) + '</span><div class="confidence-buttons">' + [1,2,3,4,5].map(function (n) { return '<button type="button" data-topic="' + s.id + '" data-score="' + n + '" class="' + (score===n?'active':'') + '">' + n + '</button>'; }).join('') + '</div></div>'; }).join('');
    document.querySelectorAll('.confidence-buttons button').forEach(function (b) { b.addEventListener('click', function () { state.confidence[b.dataset.topic] = Number(b.dataset.score); save(); renderRevision(subtopics); }); });
    var rec = state.weaknesses.length ? state.weaknesses : ['Complete a Germany practice answer to generate a targeted recommendation.'];
    document.getElementById('revision-recommendations').innerHTML = rec.map(function (x,i) { return '<div class="recommendation"><strong>' + (i+1) + '. ' + esc(x) + '</strong><p>Review the relevant knowledge card, then rewrite one paragraph using corrected evidence.</p></div>'; }).join('');
  }
});