(() => {
  document.querySelectorAll("[data-review-block]").forEach((block) => {
    const editor = block.querySelector("[data-review-editor]");
    const input = block.querySelector("[data-review-input]");
    const sync = () => { input.value = editor.innerHTML; };
    editor.addEventListener("input", sync);
    editor.addEventListener("paste", (event) => {
      event.preventDefault();
      document.execCommand("insertText", false, event.clipboardData.getData("text/plain"));
      sync();
    });
    block.querySelectorAll("[data-review-format]").forEach((button) => button.addEventListener("mousedown", (event) => {
      event.preventDefault();
      editor.focus();
      document.execCommand(button.dataset.reviewFormat, false);
      sync();
    }));
  });

  document.querySelectorAll("[data-entity-control]").forEach((control) => {
    const search = control.querySelector("[data-entity-search]");
    const type = control.querySelector("[data-entity-type]");
    const results = control.querySelector("[data-entity-results]");
    const selected = control.querySelector("[data-selected-entities]");
    let timer;

    const addEntity = (entity) => {
      if (selected.querySelector(`[data-entity-id="${entity.id}"]`)) return;
      const chip = document.createElement("span");
      chip.className = "sew-entity-chip";
      chip.dataset.entityId = entity.id;
      chip.append(document.createTextNode(`${entity.name} `));
      const entityType = document.createElement("small");
      entityType.textContent = entity.type;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.dataset.removeEntity = "";
      remove.setAttribute("aria-label", `Remove ${entity.name}`);
      remove.textContent = "×";
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = control.dataset.fieldName;
      input.value = entity.id;
      chip.append(entityType, remove, input);
      selected.appendChild(chip);
      search.value = "";
      results.hidden = true;
    };
    const runSearch = async () => {
      const query = search.value.trim();
      if (query.length < 2) { results.hidden = true; return; }
      results.innerHTML = '<span class="sew-entity-loading">Searching…</span>';
      results.hidden = false;
      try {
        const response = await fetch(`/workspace/sports-editorial/entities/search?q=${encodeURIComponent(query)}&type=${encodeURIComponent(type.value)}`);
        const payload = await response.json();
        results.innerHTML = "";
        if (!payload.results.length) results.innerHTML = '<span class="sew-entity-loading">No matches. Add it below.</span>';
        payload.results.forEach((entity) => {
          const button = document.createElement("button");
          button.type = "button";
          button.textContent = `${entity.name}${entity.country_code ? ` · ${entity.country_code}` : ""}${entity.canonical_id ? ` · ${entity.canonical_id}` : ""}`;
          button.addEventListener("click", () => addEntity(entity));
          results.appendChild(button);
        });
      } catch (_error) {
        results.innerHTML = '<span class="sew-entity-loading">Search is temporarily unavailable.</span>';
      }
    };
    search.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(runSearch, 250); });
    type.addEventListener("change", runSearch);
    selected.addEventListener("click", (event) => { if (event.target.matches("[data-remove-entity]")) event.target.closest("[data-entity-id]").remove(); });
  });
})();
