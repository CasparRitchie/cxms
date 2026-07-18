document.addEventListener('DOMContentLoaded', function () {
  var metricButtons = Array.prototype.slice.call(document.querySelectorAll('.fi-metric'));
  var pitch = document.getElementById('pitch-visual');
  var insightTitle = document.getElementById('insight-title');
  var insightCopy = document.getElementById('insight-copy');
  var platformButtons = Array.prototype.slice.call(document.querySelectorAll('.fi-platform__rail button'));
  var platformPanel = document.getElementById('platform-panel');

  var insightViews = {
    attack: {
      title: 'Create more from left-side overloads',
      copy: 'Five of the side\'s seven strongest attacks began with a regain or combination on the left. Rehearse the pattern and improve the final cutback.',
      dots: [[19, 28], [35, 65], [56, 22], [68, 55], [82, 37]]
    },
    press: {
      title: 'Trigger the press on the square pass',
      copy: 'The most successful high regains came when the front line delayed the centre-back and jumped together as the ball travelled across the back line.',
      dots: [[15, 47], [31, 30], [44, 61], [61, 41], [74, 69]]
    },
    setpieces: {
      title: 'Keep attacking the near-post zone',
      copy: 'First contact was won repeatedly from inswinging delivery. Add a second runner across the goalkeeper to convert more of those touches into shots.',
      dots: [[57, 17], [70, 24], [79, 36], [83, 52], [68, 61]]
    }
  };

  var platformViews = {
    coach: {
      label: 'Coach workspace',
      title: 'The next match, distilled.',
      copy: 'Key patterns, clips, availability and suggested training priorities in a single focused view.',
      tasks: [
        ['Opposition build-up', 'Right-back advances early; space appears behind.'],
        ['Defensive transition', 'Review three central turnovers from the last match.'],
        ['Set-piece opportunity', 'Near-post delivery produced five first contacts.']
      ]
    },
    player: {
      label: 'Player development',
      title: 'Feedback players can see.',
      copy: 'Individual objectives, clips and review notes create a visible development record throughout the season.',
      tasks: [
        ['Current objective', 'Scan before receiving under pressure.'],
        ['Evidence', 'Four clips selected from the last two matches.'],
        ['Next review', 'Coach and player check-in after Saturday.']
      ]
    },
    recruitment: {
      label: 'Recruitment intelligence',
      title: 'A shortlist built for the role.',
      copy: 'Combine observations, video and data against a shared position profile rather than collecting disconnected names.',
      tasks: [
        ['Role profile', 'Mobile number six who progresses play.'],
        ['Priority evidence', 'Receiving, counter-pressing and availability.'],
        ['Decision trail', 'Every recommendation linked to clips and notes.']
      ]
    },
    club: {
      label: 'Club performance',
      title: 'One view of growth off the pitch.',
      copy: 'Track attendance, content, sponsor delivery and commercial activity alongside the football programme.',
      tasks: [
        ['Matchday', 'Attendance and supporter conversion trend.'],
        ['Content', 'Reach, engagement and sponsor visibility.'],
        ['Commercial', 'Merchandise, campaigns and partner value.']
      ]
    }
  };

  function renderInsight(viewName) {
    var view = insightViews[viewName];
    if (!view || !pitch || !insightTitle || !insightCopy) return;

    insightTitle.textContent = view.title;
    insightCopy.textContent = view.copy;

    Array.prototype.slice.call(pitch.querySelectorAll('.fi-dot')).forEach(function (dot, index) {
      var position = view.dots[index];
      dot.style.left = position[0] + '%';
      dot.style.top = position[1] + '%';
    });
  }

  metricButtons.forEach(function (button) {
    button.addEventListener('click', function () {
      metricButtons.forEach(function (item) { item.classList.remove('is-active'); });
      button.classList.add('is-active');
      renderInsight(button.getAttribute('data-view'));
    });
  });

  function renderPlatform(viewName) {
    var view = platformViews[viewName];
    if (!view || !platformPanel) return;

    var tasks = view.tasks.map(function (task, index) {
      return '<p><i>' + (index + 1) + '</i><span><strong>' + task[0] + '</strong>' + task[1] + '</span></p>';
    }).join('');

    platformPanel.innerHTML =
      '<div>' +
        '<span class="fi-dashboard__label">' + view.label + '</span>' +
        '<h3>' + view.title + '</h3>' +
        '<p>' + view.copy + '</p>' +
      '</div>' +
      '<div class="fi-task-list">' + tasks + '</div>';
  }

  platformButtons.forEach(function (button) {
    button.addEventListener('click', function () {
      platformButtons.forEach(function (item) { item.classList.remove('is-active'); });
      button.classList.add('is-active');
      renderPlatform(button.getAttribute('data-panel'));
    });
  });
});
