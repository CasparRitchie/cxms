(function () {
  var nativeFetch = window.fetch.bind(window);
  var COURSE_URL = '/static/data/gcse-history/germany-1890-1945.json';
  var GUIDE_URL = '/static/data/gcse-history/germany-guide-pages-1-10.json?v=1';
  var ENRICHMENT_URL = '/static/data/gcse-history/germany-guide-enrichment.json?v=1';

  function addUnique(target, additions) {
    var seen = {};
    return (target || []).concat(additions || []).filter(function (item) {
      var key = typeof item === 'string' ? item.toLowerCase() : JSON.stringify(item);
      if (seen[key]) return false;
      seen[key] = true;
      return true;
    });
  }

  function mergeCourse(course, guide, enrichment) {
    var enhancements = (guide && guide.subtopicEnhancements) || {};
    var expanded = (enrichment && enrichment.topics) || {};
    course.parts.forEach(function (part) {
      part.subtopics.forEach(function (subtopic) {
        var extra = enhancements[subtopic.id] || {};
        var more = expanded[subtopic.id] || {};
        subtopic.keyFacts = addUnique(subtopic.keyFacts, (extra.extraFacts || []).concat(more.keyFacts || []));
        subtopic.keywords = addUnique(subtopic.keywords, (extra.extraKeywords || []).concat(more.keywords || []));
        subtopic.misconceptions = addUnique(subtopic.misconceptions, (extra.extraMisconceptions || []).concat(more.misconceptions || []));
        subtopic.retrievalQuestions = addUnique(subtopic.retrievalQuestions, (extra.retrievalQuestions || []).concat(more.retrievalQuestions || []));
        subtopic.examLinks = addUnique(subtopic.examLinks, (extra.examLinks || []).concat(more.examLinks || []));
        if (extra.extraFacts || more.keyFacts) subtopic.guideEnriched = true;
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
        return response.ok ? response.json() : {};
      }),
      nativeFetch(ENRICHMENT_URL).then(function (response) {
        return response.ok ? response.json() : {};
      })
    ]).then(function (results) {
      var merged = mergeCourse(results[0], results[1], results[2]);
      return new Response(JSON.stringify(merged), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      });
    });
  };
})();