(function () {
  var nativeFetch = window.fetch.bind(window);
  var COURSE_URL = '/static/data/gcse-history/germany-1890-1945.json';
  var GUIDE_URL = '/static/data/gcse-history/germany-guide-pages-1-10.json?v=1';

  function mergeCourse(course, guide) {
    var enhancements = (guide && guide.subtopicEnhancements) || {};
    course.parts.forEach(function (part) {
      part.subtopics.forEach(function (subtopic) {
        var extra = enhancements[subtopic.id];
        if (!extra) return;
        subtopic.keyFacts = (subtopic.keyFacts || []).concat(extra.extraFacts || []);
        subtopic.keywords = Array.from(new Set((subtopic.keywords || []).concat(extra.extraKeywords || [])));
        subtopic.misconceptions = (subtopic.misconceptions || []).concat(extra.extraMisconceptions || []);
        subtopic.retrievalQuestions = extra.retrievalQuestions || [];
        subtopic.examLinks = extra.examLinks || [];
        subtopic.guideEnriched = true;
      });
    });
    return course;
  }

  window.fetch = function (input, init) {
    var url = typeof input === 'string' ? input : (input && input.url) || '';
    if (url.indexOf(COURSE_URL) === -1) return nativeFetch(input, init);

    return Promise.all([
      nativeFetch(input, init).then(function (response) {
        if (!response.ok) throw new Error('Base Germany knowledge store could not be loaded');
        return response.json();
      }),
      nativeFetch(GUIDE_URL).then(function (response) {
        if (!response.ok) throw new Error('Guide enrichment could not be loaded');
        return response.json();
      })
    ]).then(function (results) {
      var merged = mergeCourse(results[0], results[1]);
      return new Response(JSON.stringify(merged), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      });
    });
  };
})();