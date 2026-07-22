(() => {
  document.querySelectorAll("[data-review-block]").forEach((block) => {
    const editor = block.querySelector("[data-review-editor]");
    const input = block.querySelector("[data-review-input]");
    // Sub-headings do not have a publication editor. Leave them rendered and
    // continue initialising entity controls on the statistic blocks below.
    if (!editor || !input) return;
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

  const initialiseEntityControl = (control) => {
    if (control.dataset.entityInitialised) return;
    control.dataset.entityInitialised = "true";
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
      const mentionLabel = document.createElement("label");
      mentionLabel.append(document.createTextNode("Words to link "));
      const mention = document.createElement("input");
      mention.name = `${control.dataset.mentionPrefix}${entity.id}`;
      mention.placeholder = "Attachment only";
      const reviewBlock = control.closest("[data-review-block], [data-content-block]");
      const editor = reviewBlock?.querySelector("[data-review-editor], [data-editor]");
      const original = reviewBlock?.querySelector(".sew-rendered-content");
      const publicationText = editor?.innerText || original?.innerText || "";
      mention.value = publicationText.includes(entity.name) ? entity.name : "";
      mentionLabel.appendChild(mention);
      chip.append(entityType, mentionLabel, remove, input);
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
  };
  document.querySelectorAll("[data-entity-control]").forEach(initialiseEntityControl);
  new MutationObserver((mutations) => mutations.forEach((mutation) => mutation.addedNodes.forEach((node) => {
    if (!(node instanceof Element)) return;
    if (node.matches("[data-entity-control]")) initialiseEntityControl(node);
    node.querySelectorAll?.("[data-entity-control]").forEach(initialiseEntityControl);
  }))).observe(document.body, {childList: true, subtree: true});
  document.querySelectorAll("form[data-confirm]").forEach((form) => form.addEventListener("submit", (event) => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  }));

  const setAccepted = (block, accepted) => {
    const input = block.querySelector("[data-accepted-input]");
    const toggle = block.querySelector("[data-toggle-accepted]");
    const editor = block.querySelector("[data-review-editor]");
    if (!input || !toggle || !editor) return;
    input.value = accepted ? "1" : "0";
    block.dataset.accepted = accepted ? "1" : "0";
    block.classList.toggle("is-accepted", accepted);
    block.classList.toggle("needs-review", !accepted);
    editor.contentEditable = accepted ? "false" : "true";
    block.querySelector("[data-review-status]").textContent = accepted ? "Accepted · locked" : "Needs review";
    toggle.textContent = accepted ? "Unlock" : "Accept and lock";
    toggle.classList.toggle("sew-button--danger", accepted);
    toggle.classList.toggle("sew-button--primary", !accepted);
    block.querySelectorAll("[data-review-format], [data-remove-entity], [data-entity-type], [data-entity-search]").forEach((control) => { control.disabled = accepted; });
    block.querySelectorAll("[data-entity-id] label input").forEach((control) => { control.readOnly = accepted; });
  };
  document.querySelectorAll("[data-toggle-accepted]").forEach((button) => button.addEventListener("click", () => {
    const block = button.closest("[data-review-block]");
    setAccepted(block, block.dataset.accepted !== "1");
  }));
  document.querySelector("[data-accept-all]")?.addEventListener("click", () => {
    if (!window.confirm("Accept and lock every statistic and sub-heading?")) return;
    document.querySelectorAll("[data-review-block]").forEach((block) => setAccepted(block, true));
  });
  document.querySelector("[data-check-entities]")?.addEventListener("click", () => {
    const chips = [...document.querySelectorAll("[data-entity-id]")];
    const invalid = chips.filter((chip) => !chip.dataset.canonicalId);
    const links = [...new Set(chips.map((chip) => chip.dataset.entityUrl).filter(Boolean))];
    links.forEach((url) => window.open(url, "_blank", "noopener"));
    window.alert(`${chips.length - invalid.length} entity links have canonical IDs. ${invalid.length} need attention.${links.length ? ` Opened ${links.length} source pages.` : ""}`);
  });
  document.querySelectorAll("[data-confirm-button]").forEach((button) => button.addEventListener("click", (event) => {
    if (!window.confirm(button.dataset.confirmButton)) event.preventDefault();
  }));
})();
