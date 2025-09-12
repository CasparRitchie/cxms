(function(){
  const btns = document.querySelectorAll('.tab-btn');
  const tabs = document.querySelectorAll('.game-tab');

  function showTab(name){
    tabs.forEach(t => {
      t.style.display = (t.dataset.game === name) ? 'block' : 'none';
    });
    btns.forEach(b => b.setAttribute('aria-selected', String(b.dataset.target === name)));

    // keep hash in URL so /games#sudoku deep links work
    try { history.replaceState(null, '', '#' + name); } catch {}
  }

  btns.forEach(b => b.addEventListener('click', () => showTab(b.dataset.target)));

  // Load from hash if present
  const hash = (location.hash || '').replace('#','');
  if (hash && [...btns].some(b => b.dataset.target === hash)) {
    showTab(hash);
  }
})();
