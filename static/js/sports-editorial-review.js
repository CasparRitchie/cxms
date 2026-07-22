(() => {
  const initialiseReviewBlock = (block) => {
    if (block.dataset.reviewInitialised) return;
    block.dataset.reviewInitialised = "true";
    const editor = block.querySelector("[data-review-editor]");
    const input = block.querySelector("[data-review-input]");
    // Sub-headings do not have a publication editor. Leave them rendered and
    // continue initialising entity controls on the statistic blocks below.
    if (!editor || !input) return;
    const original = block.querySelector(".sew-original .sew-rendered-content");
    const normaliseText = (value) => value.replace(/\s+/g, " ").trim();
    const normaliseMarkup = (value) => value.replace(/\s+/g, " ").replace(/> </g, "><").trim();
    const tokenise = (value) => normaliseText(value).match(/\S+\s*/g) || [];
    const renderDiff = (before, after) => {
      const oldTokens = tokenise(before);
      const newTokens = tokenise(after);
      const rows = Array.from({length: oldTokens.length + 1}, () => Array(newTokens.length + 1).fill(0));
      for (let oldIndex = oldTokens.length - 1; oldIndex >= 0; oldIndex -= 1) {
        for (let newIndex = newTokens.length - 1; newIndex >= 0; newIndex -= 1) {
          rows[oldIndex][newIndex] = normaliseText(oldTokens[oldIndex]) === normaliseText(newTokens[newIndex])
            ? rows[oldIndex + 1][newIndex + 1] + 1
            : Math.max(rows[oldIndex + 1][newIndex], rows[oldIndex][newIndex + 1]);
        }
      }
      const fragment = document.createDocumentFragment();
      let oldIndex = 0;
      let newIndex = 0;
      while (oldIndex < oldTokens.length || newIndex < newTokens.length) {
        if (oldIndex < oldTokens.length && newIndex < newTokens.length && normaliseText(oldTokens[oldIndex]) === normaliseText(newTokens[newIndex])) {
          fragment.append(document.createTextNode(newTokens[newIndex]));
          oldIndex += 1;
          newIndex += 1;
        } else if (newIndex < newTokens.length && (oldIndex === oldTokens.length || rows[oldIndex][newIndex + 1] >= rows[oldIndex + 1][newIndex])) {
          const added = document.createElement("ins");
          added.textContent = newTokens[newIndex];
          added.title = "Added wording";
          fragment.append(added);
          newIndex += 1;
        } else {
          const removed = document.createElement("del");
          removed.textContent = oldTokens[oldIndex];
          removed.title = "Removed wording";
          fragment.append(removed);
          oldIndex += 1;
        }
      }
      return fragment;
    };
    const updateChangedState = () => {
      if (!original) return;
      let badge = block.querySelector("[data-change-badge]");
      if (!badge) {
        badge = document.createElement("span");
        badge.className = "sew-change-badge";
        badge.dataset.changeBadge = "";
        badge.textContent = "Changed";
        block.querySelector("header")?.appendChild(badge);
      }
      const originalMarkup = normaliseMarkup(original.innerHTML);
      const currentMarkup = normaliseMarkup(editor.innerHTML);
      const changed = originalMarkup !== currentMarkup;
      block.classList.toggle("has-changes", changed);
      badge.hidden = !changed;
      let diff = block.querySelector("[data-change-diff]");
      if (!diff) {
        diff = document.createElement("div");
        diff.className = "sew-change-diff";
        diff.dataset.changeDiff = "";
        diff.setAttribute("aria-live", "polite");
        original.closest(".sew-original")?.appendChild(diff);
      }
      diff.hidden = !changed;
      diff.replaceChildren();
      if (!changed) return;
      const label = document.createElement("strong");
      label.textContent = "Exact wording changes: ";
      diff.appendChild(label);
      if (normaliseText(original.textContent) === normaliseText(editor.textContent)) {
        diff.append(document.createTextNode("Formatting changed; wording is unchanged."));
      } else {
        diff.appendChild(renderDiff(original.textContent, editor.textContent));
      }
    };
    const sync = () => { input.value = editor.innerHTML; updateChangedState(); };
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
    updateChangedState();
  };
  document.querySelectorAll("[data-review-block]").forEach(initialiseReviewBlock);

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
      chip.dataset.canonicalId = entity.canonical_id || "";
      chip.dataset.entityUrl = entity.canonical_url || "";
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
  document.addEventListener("click", (event) => {
    const toggle = event.target.closest("[data-toggle-accepted]");
    if (toggle) {
      const block = toggle.closest("[data-review-block]");
      const invalid = [...block.querySelectorAll("[data-entity-id]")].filter((chip) => !chip.dataset.canonicalId);
      if (block.dataset.accepted !== "1" && invalid.length) { window.alert("Fix entity links without canonical FIS IDs before accepting this statistic."); return; }
      setAccepted(block, block.dataset.accepted !== "1");
    }
    const remove = event.target.closest("[data-remove-review-block]");
    if (remove && window.confirm("Remove this block from the stat sheet?")) {
      remove.closest("[data-review-block]").remove();
      renumberReviewBlocks();
    }
  });
  document.querySelector("[data-accept-all]")?.addEventListener("click", () => {
    const invalid = [...document.querySelectorAll("[data-review-block][data-block-type='stat'] [data-entity-id]")].filter((chip) => !chip.dataset.canonicalId);
    if (invalid.length) { window.alert(`${invalid.length} entity links need a canonical FIS ID before the statistics can be accepted.`); return; }
    if (!window.confirm("Validate entity links, then accept and lock every statistic?")) return;
    document.querySelectorAll("[data-review-block][data-block-type='stat']").forEach((block) => setAccepted(block, true));
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

  const reviewList = document.querySelector("[data-review-list]");
  const renumberReviewBlocks = () => {
    const counts = {stat: 0, section: 0};
    reviewList?.querySelectorAll("[data-review-block]").forEach((block) => {
      counts[block.dataset.blockType] += 1;
      block.querySelector("[data-review-label]").textContent = `${block.dataset.blockType === "section" ? "Sub-heading" : "Statistic"} ${counts[block.dataset.blockType]}`;
    });
  };
  const makeReviewBlock = (type) => {
    const id = crypto.randomUUID();
    const block = document.createElement("article");
    block.className = `sew-stat-card sew-stat-card--${type}${type === "stat" ? " needs-review" : ""}`;
    block.dataset.reviewBlock = "";
    block.dataset.blockType = type;
    block.dataset.accepted = "0";
    block.draggable = true;
    const entities = type === "stat" ? `<div class="sew-entity-autocomplete" data-entity-control data-field-name="entity_ids_${id}" data-mention-prefix="entity_mention_${id}_"><span class="sew-cell-label">Entity links</span><div class="sew-selected-entities" data-selected-entities></div><div class="sew-entity-search-row"><select data-entity-type><option value="athlete">Athlete</option><option value="country">Country</option><option value="event">Event</option><option value="competition">Competition</option></select><input type="search" data-entity-search placeholder="Find entity"><div class="sew-entity-results" data-entity-results hidden></div></div></div>` : "";
    const accept = type === "stat" ? `<input type="hidden" name="accepted_${id}" value="0" data-accepted-input><button class="sew-button sew-button--primary" type="button" data-toggle-accepted>Accept and lock</button>` : "";
    block.innerHTML = `<header><span><span class="sew-drag" title="Drag to reorder">⋮⋮</span> <span data-review-label></span></span><span class="sew-validation" data-review-status>${type === "section" ? "Sub-heading · editable" : "Needs review"}</span></header><input type="hidden" name="content_id" value="${id}"><input type="hidden" name="content_type" value="${type}"><div class="sew-working-editor"><div class="sew-mini-toolbar"><button type="button" data-review-format="bold"><strong>B</strong></button><button type="button" data-review-format="italic"><em>I</em></button></div><div class="sew-rich-editor" contenteditable="true" role="textbox" aria-label="${type === "section" ? "Sub-heading" : "Statistic"} wording" data-review-editor></div><textarea name="edited_text_${id}" hidden data-review-input data-content-input></textarea></div><details class="sew-original"><summary>View original researcher wording</summary><div class="sew-rendered-content"></div></details>${entities}<div class="sew-review-actions"><button class="sew-button sew-button--danger" type="button" data-remove-review-block>Remove</button>${accept}</div>`;
    return block;
  };
  document.querySelectorAll("[data-add-review-block]").forEach((button) => button.addEventListener("click", () => {
    const block = makeReviewBlock(button.dataset.addReviewBlock);
    document.querySelector("[data-review-empty]")?.remove();
    reviewList.appendChild(block);
    initialiseReviewBlock(block);
    block.querySelectorAll("[data-entity-control]").forEach(initialiseEntityControl);
    renumberReviewBlocks();
    block.querySelector("[data-review-editor]").focus();
  }));
  let draggedReviewBlock;
  reviewList?.addEventListener("dragstart", (event) => { draggedReviewBlock = event.target.closest("[data-review-block]"); });
  reviewList?.addEventListener("dragover", (event) => {
    event.preventDefault();
    const target = event.target.closest("[data-review-block]");
    if (target && target !== draggedReviewBlock) {
      const box = target.getBoundingClientRect();
      reviewList.insertBefore(draggedReviewBlock, event.clientY < box.top + box.height / 2 ? target : target.nextSibling);
    }
  });
  reviewList?.addEventListener("dragend", renumberReviewBlocks);
  document.querySelector("[data-review-form]")?.addEventListener("submit", renumberReviewBlocks);
  renumberReviewBlocks();
})();
