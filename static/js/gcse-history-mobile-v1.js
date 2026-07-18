document.addEventListener('DOMContentLoaded', function () {
  document.body.classList.add('gcse-history-page');

  var header = document.querySelector('.site-header');
  var tabs = Array.prototype.slice.call(document.querySelectorAll('.history-tabs .tab'));
  var feedbackPanel = document.getElementById('feedback-panel');
  var practiceLayout = document.querySelector('.practice-layout');
  var lastY = window.scrollY || 0;
  var ticking = false;

  function isMobile() {
    return window.matchMedia('(max-width: 850px)').matches;
  }

  function updateHeader() {
    if (!header || !isMobile()) {
      if (header) header.classList.remove('nav-hidden');
      lastY = window.scrollY || 0;
      ticking = false;
      return;
    }

    var currentY = window.scrollY || 0;
    var delta = currentY - lastY;

    if (currentY < 24) {
      header.classList.remove('nav-hidden');
    } else if (delta > 8) {
      header.classList.add('nav-hidden');
    } else if (delta < -8) {
      header.classList.remove('nav-hidden');
    }

    lastY = currentY;
    ticking = false;
  }

  window.addEventListener('scroll', function () {
    if (!ticking) {
      window.requestAnimationFrame(updateHeader);
      ticking = true;
    }
  }, { passive: true });

  window.addEventListener('resize', updateHeader);

  function activateSavedTab() {
    var saved = localStorage.getItem('gcseHistoryActiveTab');
    var target = tabs.find(function (button) { return button.dataset.tab === saved; });
    if (target) target.click();
  }

  tabs.forEach(function (button) {
    button.addEventListener('click', function () {
      localStorage.setItem('gcseHistoryActiveTab', button.dataset.tab);
      if (isMobile()) {
        window.setTimeout(function () {
          button.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
        }, 0);
      }
    });
  });

  if (practiceLayout && feedbackPanel) {
    var toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'mobile-feedback-toggle';
    toggle.textContent = 'Show feedback';
    feedbackPanel.classList.add('mobile-collapsed');
    practiceLayout.insertBefore(toggle, feedbackPanel);

    toggle.addEventListener('click', function () {
      var collapsed = feedbackPanel.classList.toggle('mobile-collapsed');
      toggle.textContent = collapsed ? 'Show feedback' : 'Hide feedback';
      toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    });

    var observer = new MutationObserver(function () {
      if (!isMobile()) return;
      if (feedbackPanel.querySelector('.empty-state')) return;
      feedbackPanel.classList.remove('mobile-collapsed');
      toggle.textContent = 'Hide feedback';
      toggle.setAttribute('aria-expanded', 'true');
    });
    observer.observe(feedbackPanel, { childList: true, subtree: true });
  }

  activateSavedTab();
  updateHeader();
});