(() => {
  const views = document.querySelectorAll('.view');
  const navLinks = document.querySelectorAll('.nav-link');

  function showView(name) {
    views.forEach(v => v.classList.toggle('active', v.id === `view-${name}`));
    navLinks.forEach(n => n.classList.toggle('active', n.dataset.view === name));
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  navLinks.forEach(btn => btn.addEventListener('click', () => showView(btn.dataset.view)));
  document.querySelectorAll('[data-go]').forEach(btn => btn.addEventListener('click', () => showView(btn.dataset.go)));

  let currentStep = 1;
  const steps = [...document.querySelectorAll('.step')];
  const panels = [...document.querySelectorAll('.form-step')];
  const prev = document.getElementById('prev-step');
  const next = document.getElementById('next-step');

  function setStep(step) {
    currentStep = Math.min(4, Math.max(1, Number(step)));
    steps.forEach(s => s.classList.toggle('active', Number(s.dataset.step) === currentStep));
    panels.forEach(p => p.classList.toggle('active', Number(p.dataset.panel) === currentStep));
    prev.style.visibility = currentStep === 1 ? 'hidden' : 'visible';
    next.style.display = currentStep === 4 ? 'none' : 'inline-block';
  }

  steps.forEach(s => s.addEventListener('click', () => setStep(s.dataset.step)));
  prev.addEventListener('click', () => setStep(currentStep - 1));
  next.addEventListener('click', () => setStep(currentStep + 1));
  setStep(1);

  const submit = document.getElementById('submit-demo');
  submit.addEventListener('click', () => {
    document.querySelector('.form-card').style.display = 'none';
    document.querySelector('.stepper').style.display = 'none';
    document.getElementById('success-card').classList.add('show');
  });

  const verifyButtons = [...document.querySelectorAll('.verify-btn')];
  const completeButton = document.getElementById('complete-checkin');
  verifyButtons.forEach(btn => btn.addEventListener('click', () => {
    btn.classList.add('done');
    btn.textContent = '✓ Vérifié';
    completeButton.disabled = !verifyButtons.every(b => b.classList.contains('done'));
  }));

  completeButton.addEventListener('click', () => {
    completeButton.textContent = '✓ Enregistrement terminé';
    completeButton.disabled = true;
    const status = document.querySelector('.detail-card .status-pill');
    status.className = 'status-pill good';
    status.textContent = 'Complet';
    const selected = document.querySelector('.arrival-row.selected .status-pill');
    selected.className = 'status-pill good';
    selected.textContent = 'Complet';
  });
})();
