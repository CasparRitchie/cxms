(() => {
  'use strict';
  const root = document.documentElement;
  const preview = document.body.dataset.preview === 'true';
  const storageScope = document.body.dataset.storageScope || 'preview';
  const favouriteKey = storageScope === 'preview' ? 'sammytv:favourites' : `sammytv:favourites:${storageScope}`;
  const read = (key, fallback) => { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } };
  const notify = message => { const notice = document.querySelector('#notice'); notice.textContent = message; notice.hidden = false; setTimeout(() => { notice.hidden = true; }, 3500); };
  const write = (key, value) => { try { localStorage.setItem(key, JSON.stringify(value)); } catch { notify('Browser storage unavailable. Changes last for this page only.'); } };
  root.dataset.theme = read('sammytv:theme', 'dark') === 'light' ? 'light' : 'dark';
  document.querySelector('.theme')?.addEventListener('click', () => { root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark'; write('sammytv:theme', root.dataset.theme); });
  document.querySelector('.menu')?.addEventListener('click', event => { const closed = document.body.classList.toggle('sidebar-closed'); event.currentTarget.setAttribute('aria-expanded', String(!closed)); });
  const saved = read(favouriteKey, []);
  const favourites = new Set(Array.isArray(saved) ? saved.filter(id => typeof id === 'string') : []);
  const params = new URLSearchParams(location.search);
  const chips = [...document.querySelectorAll('[data-category]')];
  let category = params.get('category') || 'All';
  if (!chips.some(chip => chip.dataset.category === category)) category = 'All';
  // Private catalogue search is performed on the server, including descriptions.
  const query = preview ? (params.get('q') || '').trim().toLowerCase() : '';
  const filter = () => {
    let count = 0;
    document.querySelectorAll('.card').forEach(card => {
      const favouriteOnly = category === 'Favourites' || document.body.dataset.section === 'favourites';
      const match = (category === 'All' || category === 'Favourites' || JSON.parse(card.dataset.categories).includes(category)) && (!favouriteOnly || favourites.has(card.dataset.id)) && card.dataset.search.includes(query);
      card.hidden = !match;
      if (match) count++;
    });
    chips.forEach(chip => chip.setAttribute('aria-pressed', String(chip.dataset.category === category)));
    const empty = document.querySelector('.empty-results');
    if (empty) empty.hidden = count > 0;
    document.querySelectorAll('.favourite').forEach(button => { const selected = favourites.has(button.dataset.id); button.setAttribute('aria-pressed', String(selected)); button.textContent = button.classList.contains('save') ? (selected ? '♥' : '♡') : (selected ? '♥ Saved' : '♡ Favourite'); });
  };
  chips.forEach(chip => chip.addEventListener('click', () => {
    category = chip.dataset.category;
    if (preview) {
      filter();
    } else {
      const destination = new URL(location.href);
      destination.searchParams.set('category', category);
      destination.searchParams.delete('page');
      location.assign(destination.href);
    }
  }));
  document.querySelectorAll('.favourite').forEach(button => button.addEventListener('click', () => { const id = button.dataset.id; favourites.has(id) ? favourites.delete(id) : favourites.add(id); write(favouriteKey, [...favourites]); filter(); }));
  document.querySelector('.load-player')?.addEventListener('click', async event => {
    const button = event.currentTarget;
    const status = document.querySelector('#playback-status');
    button.disabled = true;
    status.textContent = 'Checking this video…';
    try {
      const response = await fetch(button.dataset.playbackUrl, { credentials: 'same-origin', cache: 'no-store' });
      if (response.status === 410) {
        const problem = await response.json();
        if (problem.error === 'camera_offline') {
          status.textContent = 'This camera is offline or unavailable. Please try again later.';
          button.disabled = false;
          return;
        }
      }
      if (!response.ok) throw new Error('Playback unavailable');
      const data = await response.json();
      const url = new URL(data.embed_url);
      if (url.origin !== 'https://www.youtube-nocookie.com' || !/^\/embed\/[A-Za-z0-9_-]{11}$/.test(url.pathname) || url.searchParams.get('autoplay') !== '0') {
        throw new Error('Invalid player URL');
      }
      const frame = document.createElement('iframe');
      frame.title = 'YouTube video player';
      frame.src = url.href;
      frame.allow = 'encrypted-media; picture-in-picture; fullscreen';
      frame.allowFullscreen = true;
      frame.referrerPolicy = 'strict-origin-when-cross-origin';
      document.querySelector('.player-message').replaceWith(frame);
      status.textContent = 'YouTube player loaded. Playback controls and links are provided by YouTube.';
    } catch {
      status.textContent = 'This video cannot be opened right now. It may have been removed from your collection. Please ask a parent.';
      button.disabled = false;
    }
  });
  document.querySelector('.fullscreen')?.addEventListener('click', async () => { try { const player = document.querySelector('#player'); if (document.fullscreenElement) await document.exitFullscreen(); else if (player.requestFullscreen) await player.requestFullscreen(); else notify('Full screen is not supported by this browser.'); } catch { notify('Full screen could not be opened.'); } });
  filter();
})();
