(function () {
  const storageKey = 'cxms-sports-editorial-theme';
  const root = document.documentElement;
  const toggle = document.querySelector('.sew-theme-toggle');

  if (!toggle) return;

  function render(theme) {
    const isLight = theme === 'light';
    root.dataset.sewTheme = theme;
    toggle.setAttribute('aria-pressed', String(isLight));
    toggle.setAttribute('aria-label', `Switch to ${isLight ? 'dark' : 'light'} mode`);
    toggle.querySelector('.sew-theme-toggle__icon').textContent = isLight ? '☾' : '☀';
    toggle.querySelector('.sew-theme-toggle__label').textContent = isLight ? 'Dark' : 'Light';
  }

  render(root.dataset.sewTheme || 'dark');
  toggle.addEventListener('click', function () {
    const theme = root.dataset.sewTheme === 'light' ? 'dark' : 'light';
    localStorage.setItem(storageKey, theme);
    render(theme);
  });
}());
