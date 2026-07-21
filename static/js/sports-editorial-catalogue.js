(() => {
  const form = document.querySelector('[data-catalogue-refresh]');
  if (!form) return;
  const status = document.querySelector('[data-refresh-status]');
  const button = form.querySelector('button[type="submit"]');
  const labels = { events: 'Events', athletes: 'Athletes and countries', competitions: 'Competitions' };

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    button.disabled = true;
    const messages = [];
    try {
      for (const step of ['events', 'athletes', 'competitions']) {
        status.textContent = `Refreshing ${labels[step]}…`;
        const response = await fetch(form.dataset.refreshUrl.replace('STEP', step), {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: new URLSearchParams(new FormData(form)),
        });
        const result = await response.json();
        if (!response.ok || !result.ok) throw new Error(result.error || `${labels[step]} refresh failed.`);
        messages.push(result.message);
      }
      status.textContent = `Complete — ${messages.join(' ')}`;
      window.setTimeout(() => window.location.reload(), 1800);
    } catch (error) {
      status.textContent = `Refresh stopped: ${error.message} Completed earlier steps have been retained.`;
      button.disabled = false;
    }
  });
})();
