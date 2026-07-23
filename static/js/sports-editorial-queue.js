(function () {
  const filters = Array.from(document.querySelectorAll('.sew-column-filter'));

  filters.forEach(function (filter) {
    const search = filter.querySelector('.sew-column-filter-search');
    const options = Array.from(filter.querySelectorAll('.sew-column-filter-options label'));

    filter.addEventListener('toggle', function () {
      if (!filter.open) return;
      filters.forEach(function (otherFilter) {
        if (otherFilter !== filter) otherFilter.open = false;
      });
      search.focus();
    });

    search.addEventListener('input', function () {
      const query = search.value.trim().toLocaleLowerCase();
      options.forEach(function (option) {
        option.hidden = Boolean(query) && !option.textContent.trim().toLocaleLowerCase().includes(query);
      });
    });
  });

  document.querySelectorAll('.sew-queue-row[data-row-href]').forEach(function (row) {
    function openRow() {
      window.location.assign(row.dataset.rowHref);
    }

    row.addEventListener('click', function (event) {
      if (event.target.closest('a, button, input, select, textarea, summary, label, details')) return;
      if (window.getSelection && window.getSelection().toString()) return;
      openRow();
    });

    row.addEventListener('keydown', function (event) {
      if (event.target === row && (event.key === 'Enter' || event.key === ' ')) {
        event.preventDefault();
        openRow();
      }
    });
  });
}());
