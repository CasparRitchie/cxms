(function () {
  const filterControls = Array.from(document.querySelectorAll('.sew-filter-control'));
  filterControls.forEach(function (control) {
    const search = control.querySelector('[data-filter-search]');
    const options = Array.from(control.querySelectorAll('fieldset label'));
    const summaryState = control.querySelector('summary b');
    const checkboxes = Array.from(control.querySelectorAll('input[type="checkbox"]'));
    function renderFilterSelection() {
      const selectedCount = checkboxes.filter(function (checkbox) { return checkbox.checked; }).length;
      control.classList.toggle('has-selection', selectedCount > 0);
      if (summaryState) summaryState.textContent = selectedCount ? selectedCount + ' selected' : 'All';
    }
    control.addEventListener('toggle', function () {
      if (!control.open) return;
      filterControls.forEach(function (other) { if (other !== control) other.open = false; });
      if (search) search.focus();
    });
    if (search) {
      search.addEventListener('input', function () {
        const query = search.value.trim().toLocaleLowerCase();
        options.forEach(function (option) {
          option.hidden = Boolean(query) && !option.textContent.trim().toLocaleLowerCase().includes(query);
        });
      });
    }
    checkboxes.forEach(function (checkbox) { checkbox.addEventListener('change', renderFilterSelection); });
    renderFilterSelection();
  });
  document.addEventListener('click', function (event) {
    if (event.target.closest('.sew-filter-control')) return;
    filterControls.forEach(function (control) { control.open = false; });
  });
}());
