document.addEventListener('DOMContentLoaded', function () {
  var courseUrl = '/static/data/gcse-history/germany-1890-1945.json?v=1';

  fetch(courseUrl).then(function (response) {
    if (!response.ok) return null;
    return response.json();
  }).then(function (course) {
    if (!course) return;
    var byTitle = {};
    course.parts.forEach(function (part) {
      part.subtopics.forEach(function (subtopic) {
        if (subtopic.retrievalQuestions && subtopic.retrievalQuestions.length) byTitle[subtopic.title] = subtopic;
      });
    });

    function enhanceCards() {
      var cards = document.querySelectorAll('#topic-grid .topic-card');
      if (!cards.length) return false;
      cards.forEach(function (card) {
        if (card.dataset.guideEnhanced === 'true') return;
        var heading = card.querySelector('h3');
        if (!heading) return;
        var subtopic = byTitle[heading.textContent.trim()];
        if (!subtopic) return;

        var recall = document.createElement('details');
        recall.className = 'guide-quick-recall';
        recall.innerHTML = '<summary>⚡ Quick recall</summary><ol>' + subtopic.retrievalQuestions.map(function (q) {
          return '<li>' + escapeHtml(q) + '</li>';
        }).join('') + '</ol>';
        card.appendChild(recall);

        if (subtopic.examLinks && subtopic.examLinks.length) {
          var exam = document.createElement('details');
          exam.className = 'guide-exam-link';
          exam.innerHTML = '<summary>🎯 Exam connection</summary><ul>' + subtopic.examLinks.map(function (tip) {
            return '<li>' + escapeHtml(tip) + '</li>';
          }).join('') + '</ul>';
          card.appendChild(exam);
        }
        card.dataset.guideEnhanced = 'true';
      });
      return true;
    }

    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, function (c) {
        return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c];
      });
    }

    if (enhanceCards()) return;
    var observer = new MutationObserver(function () {
      if (enhanceCards()) observer.disconnect();
    });
    observer.observe(document.getElementById('topic-grid'), { childList: true, subtree: true });
  }).catch(function () {});
});