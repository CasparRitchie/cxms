(function () {
  const viewSwitcher = document.querySelector('[data-queue-view-switcher]');
  if (viewSwitcher) {
    const storageKey = 'cxms-sports-editorial-queue-view';
    let preferredView = '';
    try { preferredView = localStorage.getItem(storageKey) || ''; } catch (error) { preferredView = ''; }
    const currentView = viewSwitcher.dataset.currentView;
    if (currentView === 'standard' && preferredView === 'enhanced') {
      window.location.replace(viewSwitcher.dataset.enhancedUrl);
      return;
    }
    viewSwitcher.querySelectorAll('[data-queue-view]').forEach(function (link) {
      link.addEventListener('click', function () {
        try { localStorage.setItem(storageKey, link.dataset.queueView); } catch (error) { /* Preference remains session-only. */ }
      });
    });
  }

  const filterControls = Array.from(document.querySelectorAll('.sew-filter-control'));
  filterControls.forEach(function (control) {
    const search = control.querySelector('[data-filter-search]');
    const options = Array.from(control.querySelectorAll('fieldset label'));
    control.addEventListener('toggle', function () {
      if (!control.open) return;
      filterControls.forEach(function (other) { if (other !== control) other.open = false; });
      search.focus();
    });
    search.addEventListener('input', function () {
      const query = search.value.trim().toLocaleLowerCase();
      options.forEach(function (option) {
        option.hidden = Boolean(query) && !option.textContent.trim().toLocaleLowerCase().includes(query);
      });
    });
  });

  document.querySelectorAll('.sew-column-headings a[data-add-sort-url]').forEach(function (link) {
    link.addEventListener('click', function (event) {
      if (!event.shiftKey) return;
      event.preventDefault();
      window.location.assign(link.dataset.addSortUrl);
    });
  });

  const rows = Array.from(document.querySelectorAll('.sew-queue-row[data-submission-id][tabindex]'));
  if (!rows.length) return;

  const selected = new Set();
  const count = document.querySelector('[data-selected-count]');
  const clearButton = document.querySelector('[data-clear-selection]');
  const allocationButtons = Array.from(document.querySelectorAll('[data-open-allocation]'));
  let anchorIndex = null;
  let dragging = false;
  let dragStartIndex = null;
  let dragBase = new Set();
  let additiveDrag = false;

  function renderSelection() {
    rows.forEach(function (row) {
      const isSelected = selected.has(row.dataset.submissionId);
      row.classList.toggle('is-selected', isSelected);
      row.setAttribute('aria-selected', isSelected ? 'true' : 'false');
      const checkbox = row.querySelector('[data-row-select]');
      if (checkbox) checkbox.checked = isSelected;
    });
    count.textContent = String(selected.size);
    clearButton.disabled = selected.size === 0;
    allocationButtons.forEach(function (button) { button.disabled = selected.size === 0; });
  }

  function addRange(start, end, targetSet) {
    const first = Math.min(start, end);
    const last = Math.max(start, end);
    for (let index = first; index <= last; index += 1) targetSet.add(rows[index].dataset.submissionId);
  }

  function selectFromPointer(index, event) {
    if (event.shiftKey && anchorIndex !== null) {
      if (!(event.ctrlKey || event.metaKey)) selected.clear();
      addRange(anchorIndex, index, selected);
    } else if (event.ctrlKey || event.metaKey) {
      const id = rows[index].dataset.submissionId;
      if (selected.has(id)) selected.delete(id);
      else selected.add(id);
      anchorIndex = index;
    } else {
      selected.clear();
      selected.add(rows[index].dataset.submissionId);
      anchorIndex = index;
    }
    renderSelection();
  }

  rows.forEach(function (row, index) {
    const checkbox = row.querySelector('[data-row-select]');
    if (checkbox) {
      checkbox.addEventListener('change', function (event) {
        if (checkbox.checked) selected.add(row.dataset.submissionId);
        else selected.delete(row.dataset.submissionId);
        anchorIndex = index;
        event.stopPropagation();
        renderSelection();
      });
    }
    row.addEventListener('mousedown', function (event) {
      if (event.button !== 0 || event.target.closest('a, button, input, select, textarea')) return;
      event.preventDefault();
      selectFromPointer(index, event);
      dragging = true;
      dragStartIndex = index;
      dragBase = new Set(selected);
      additiveDrag = event.ctrlKey || event.metaKey;
    });
    row.addEventListener('mouseenter', function () {
      if (!dragging) return;
      selected.clear();
      if (additiveDrag) dragBase.forEach(function (id) { selected.add(id); });
      addRange(dragStartIndex, index, selected);
      renderSelection();
    });
    row.addEventListener('keydown', function (event) {
      if (event.key !== ' ') return;
      event.preventDefault();
      selectFromPointer(index, event);
    });
  });
  document.addEventListener('mouseup', function () { dragging = false; });

  document.querySelector('[data-select-all]').addEventListener('click', function () {
    rows.forEach(function (row) { selected.add(row.dataset.submissionId); });
    if (rows.length) anchorIndex = 0;
    renderSelection();
  });
  clearButton.addEventListener('click', function () {
    selected.clear();
    anchorIndex = null;
    renderSelection();
  });

  const dialogs = Array.from(document.querySelectorAll('[data-allocation-dialog]'));
  function closeDialog(dialog) {
    if (typeof dialog.close === 'function') dialog.close();
    else dialog.removeAttribute('open');
  }
  allocationButtons.forEach(function (button) {
    button.addEventListener('click', function () {
      const dialog = document.querySelector(`[data-allocation-dialog="${button.dataset.openAllocation}"]`);
      dialog.querySelector('[data-dialog-selection-count]').textContent = String(selected.size);
      const form = dialog.querySelector('form');
      form.querySelectorAll('[data-selected-submission]').forEach(function (input) { input.remove(); });
      selected.forEach(function (id) {
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'submission_id';
        input.value = id;
        input.dataset.selectedSubmission = '';
        form.appendChild(input);
      });
      if (typeof dialog.showModal === 'function') dialog.showModal();
      else dialog.setAttribute('open', '');
      dialog.querySelector('select').focus();
    });
  });
  dialogs.forEach(function (dialog) {
    dialog.querySelectorAll('[data-close-allocation]').forEach(function (button) {
      button.addEventListener('click', function () { closeDialog(dialog); });
    });
    dialog.addEventListener('click', function (event) {
      if (event.target === dialog) closeDialog(dialog);
    });
  });

  renderSelection();
}());
