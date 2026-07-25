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
    const editorMarkup = () => {
      const clone = editor.cloneNode(true);
      clone.querySelectorAll("[data-entity-ref]").forEach((tag) => tag.replaceWith(document.createTextNode(tag.textContent)));
      return clone.innerHTML;
    };
    const sessionStartMarkup = normaliseMarkup(editorMarkup());
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
        const headerActions = block.querySelector(".sew-card-header-actions");
        if (headerActions) headerActions.insertBefore(badge, headerActions.querySelector("[data-remove-review-block]"));
        else block.querySelector("header")?.appendChild(badge);
      }
      const currentMarkup = normaliseMarkup(editorMarkup());
      const changedThisSession = sessionStartMarkup !== currentMarkup;
      const differsFromResearcher = normaliseMarkup(original.innerHTML) !== currentMarkup;
      block.classList.toggle("has-changes", changedThisSession);
      badge.hidden = !changedThisSession;
      let diff = block.querySelector("[data-change-diff]");
      if (!diff) {
        diff = document.createElement("div");
        diff.className = "sew-change-diff";
        diff.dataset.changeDiff = "";
        diff.setAttribute("aria-live", "polite");
        original.closest(".sew-original")?.appendChild(diff);
      }
      diff.hidden = !differsFromResearcher;
      diff.replaceChildren();
      if (!differsFromResearcher) return;
      const label = document.createElement("strong");
      label.textContent = "Exact wording changes: ";
      diff.appendChild(label);
      if (normaliseText(original.textContent) === normaliseText(editor.textContent)) {
        diff.append(document.createTextNode("Formatting changed; wording is unchanged."));
      } else {
        diff.appendChild(renderDiff(original.textContent, editor.textContent));
      }
    };
    const sync = () => { input.value = editorMarkup(); updateChangedState(); };
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
    let controller;
    let nextOffset = 0;
    let activeIndex = -1;

    const entityButtons = () => [...results.querySelectorAll("[data-entity-result]")];
    const setActive = (index) => {
      const buttons = entityButtons();
      buttons.forEach((button) => {
        button.setAttribute("aria-selected", "false");
        button.tabIndex = -1;
      });
      if (!buttons.length) { activeIndex = -1; return; }
      activeIndex = Math.max(0, Math.min(index, buttons.length - 1));
      buttons[activeIndex].setAttribute("aria-selected", "true");
      buttons[activeIndex].tabIndex = 0;
      buttons[activeIndex].focus();
    };

    const editorForControl = () => control.closest("[data-review-block], [data-content-block]")
      ?.querySelector("[data-review-editor], [data-editor]");
    const unwrapMentionTags = (editor) => {
      editor.querySelectorAll("[data-entity-ref]").forEach((tag) => {
        tag.replaceWith(document.createTextNode(tag.textContent));
      });
      editor.normalize();
    };
    const findMentionTextNode = (editor, words) => {
      const walker = document.createTreeWalker(editor, NodeFilter.SHOW_TEXT);
      let node;
      while ((node = walker.nextNode())) {
        const index = node.data.indexOf(words);
        if (index >= 0) return {node, index};
      }
      return null;
    };
    const applyMentionTags = () => {
      const editor = editorForControl();
      if (!editor) return;
      unwrapMentionTags(editor);
      selected.querySelectorAll("[data-entity-id]").forEach((chip) => {
        const words = chip.querySelector("label input")?.value.trim();
        if (!words) return;
        const match = findMentionTextNode(editor, words);
        if (!match) return;
        const remainder = match.node.splitText(match.index);
        const after = remainder.splitText(words.length);
        const tag = document.createElement("span");
        tag.className = "sew-entity-text-tag";
        tag.dataset.entityRef = chip.dataset.entityId;
        tag.setAttribute("role", "link");
        tag.tabIndex = 0;
        tag.textContent = remainder.data;
        remainder.replaceWith(tag);
        after.parentNode?.normalize();
      });
    };
    const validateMentionTags = () => {
      const block = control.closest("[data-review-block], [data-content-block]");
      const editor = block?.querySelector("[data-review-editor], [data-editor]");
      if (!editor) return;
      selected.querySelectorAll("[data-entity-id]").forEach((chip) => {
        const mention = chip.querySelector("label input");
        if (mention?.value && !editor.innerText.includes(mention.value)) mention.value = "";
      });
      applyMentionTags();
    };

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
      mention.addEventListener("change", applyMentionTags);
      search.value = "";
      results.hidden = true;
      applyMentionTags();
    };
    const appendResult = (entity) => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.entityResult = "";
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", "false");
      button.tabIndex = -1;
      button.textContent = `${entity.name}${entity.country_code ? ` · ${entity.country_code}` : ""}${entity.canonical_id ? ` · ${entity.canonical_id}` : ""}`;
      button.addEventListener("click", () => addEntity(entity));
      results.appendChild(button);
    };
    const runSearch = async (append = false) => {
      const query = search.value.trim();
      if (query.length < 2) { results.hidden = true; return; }
      if (!append) {
        nextOffset = 0;
        results.innerHTML = "";
      } else {
        results.querySelector("[data-show-more]")?.remove();
        results.querySelector("[data-no-more]")?.remove();
      }
      const loading = document.createElement("span");
      loading.className = "sew-entity-loading";
      loading.textContent = append ? "Loading more…" : "Searching…";
      results.appendChild(loading);
      results.hidden = false;
      controller?.abort();
      controller = new AbortController();
      try {
        const response = await fetch(`/workspace/sports-editorial/entities/search?q=${encodeURIComponent(query)}&type=${encodeURIComponent(type.value)}&offset=${nextOffset}`, {signal: controller.signal});
        const payload = await response.json();
        loading.remove();
        if (!append && !payload.results.length) results.innerHTML = '<span class="sew-entity-loading">No matches.</span>';
        payload.results.forEach(appendResult);
        nextOffset = payload.next_offset;
        if (payload.has_more) {
          const more = document.createElement("button");
          more.type = "button";
          more.dataset.showMore = "";
          more.textContent = "Show more";
          more.addEventListener("click", () => runSearch(true));
          results.appendChild(more);
        } else if (append && payload.results.length) {
          const end = document.createElement("span");
          end.className = "sew-entity-loading";
          end.dataset.noMore = "";
          end.textContent = "No more results.";
          results.appendChild(end);
        }
      } catch (error) {
        if (error.name === "AbortError") return;
        results.innerHTML = '<span class="sew-entity-loading">Search is temporarily unavailable.</span>';
      }
    };
    search.setAttribute("aria-controls", search.getAttribute("aria-controls") || `entity-results-${crypto.randomUUID()}`);
    results.id = search.getAttribute("aria-controls");
    results.setAttribute("role", "listbox");
    search.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => runSearch(false), 250); });
    search.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown" && entityButtons().length) { event.preventDefault(); setActive(activeIndex + 1); }
      else if (event.key === "ArrowUp" && entityButtons().length) { event.preventDefault(); setActive(activeIndex <= 0 ? entityButtons().length - 1 : activeIndex - 1); }
      else if (event.key === "Enter") {
        event.preventDefault();
        if (activeIndex >= 0 && entityButtons()[activeIndex]) entityButtons()[activeIndex].click();
      } else if (event.key === "Escape") {
        event.preventDefault();
        results.hidden = true;
      }
    });
    type.addEventListener("change", () => runSearch(false));
    selected.addEventListener("click", (event) => {
      if (!event.target.matches("[data-remove-entity]")) return;
      event.target.closest("[data-entity-id]").remove();
      applyMentionTags();
    });
    editorForControl()?.addEventListener("input", validateMentionTags);
    selected.querySelectorAll("label input").forEach((input) => input.addEventListener("change", applyMentionTags));
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
    updateAcceptanceSummary();
  };
  const updateAcceptanceSummary = () => {
    const statistics = [...document.querySelectorAll("[data-review-block][data-block-type='stat']")];
    const accepted = statistics.filter((block) => block.dataset.accepted === "1").length;
    const acceptedCount = document.querySelector("[data-accepted-count]");
    const statCount = document.querySelector("[data-stat-count]");
    if (acceptedCount) acceptedCount.textContent = String(accepted);
    if (statCount) statCount.textContent = String(statistics.length);
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
      updateAcceptanceSummary();
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
    block.draggable = false;
    const entities = type === "stat" ? `<div class="sew-entity-autocomplete" data-entity-control data-field-name="entity_ids_${id}" data-mention-prefix="entity_mention_${id}_"><span class="sew-cell-label">Entity links</span><div class="sew-selected-entities" data-selected-entities></div><div class="sew-entity-search-row"><select data-entity-type><option value="athlete">Athlete</option><option value="country">Country</option><option value="event">Event</option><option value="competition">Competition</option></select><input type="search" data-entity-search placeholder="Find entity"><div class="sew-entity-results" data-entity-results hidden></div></div></div>` : "";
    const acceptedInput = type === "stat" ? `<input type="hidden" name="accepted_${id}" value="0" data-accepted-input>` : "";
    const accept = type === "stat" ? `<button class="sew-button sew-button--primary sew-button--small" type="button" data-toggle-accepted>Accept and lock</button>` : "";
    block.innerHTML = `<header><div class="sew-card-header-actions"><span class="sew-validation" data-review-status>${type === "section" ? "Sub-heading · editable" : "Needs review"}</span>${accept}<button class="sew-button sew-button--danger sew-button--small" type="button" data-remove-review-block>Remove</button></div></header><input type="hidden" name="content_id" value="${id}"><input type="hidden" name="content_type" value="${type}">${acceptedInput}<div class="sew-content-editor-row"><div class="sew-content-block-label"><span class="sew-drag" title="Drag to reorder" draggable="true">⋮⋮</span><span data-review-label></span></div><div class="sew-content-editor-body"><div class="sew-working-editor"><div class="sew-mini-toolbar"><button type="button" data-review-format="bold"><strong>B</strong></button><button type="button" data-review-format="italic"><em>I</em></button></div><div class="sew-rich-editor" contenteditable="true" role="textbox" aria-label="${type === "section" ? "Sub-heading" : "Statistic"} wording" data-review-editor></div><textarea name="edited_text_${id}" hidden data-review-input data-content-input></textarea></div><details class="sew-original"><summary>View original researcher wording</summary><div class="sew-rendered-content"></div></details>${entities}</div></div>`;
    return block;
  };
  document.querySelectorAll("[data-add-review-block]").forEach((button) => button.addEventListener("click", () => {
    const block = makeReviewBlock(button.dataset.addReviewBlock);
    document.querySelector("[data-review-empty]")?.remove();
    reviewList.appendChild(block);
    initialiseReviewBlock(block);
    block.querySelectorAll("[data-entity-control]").forEach(initialiseEntityControl);
    renumberReviewBlocks();
    updateAcceptanceSummary();
    block.querySelector("[data-review-editor]").focus();
  }));
  let draggedReviewBlock;
  reviewList?.addEventListener("dragstart", (event) => {
    const handle = event.target.closest(".sew-drag");
    draggedReviewBlock = handle?.closest("[data-review-block]");
    if (!draggedReviewBlock) event.preventDefault();
  });
  reviewList?.addEventListener("dragover", (event) => {
    if (!draggedReviewBlock) return;
    event.preventDefault();
    const target = event.target.closest("[data-review-block]");
    if (target && target !== draggedReviewBlock) {
      const box = target.getBoundingClientRect();
      reviewList.insertBefore(draggedReviewBlock, event.clientY < box.top + box.height / 2 ? target : target.nextSibling);
    }
  });
  reviewList?.addEventListener("dragend", () => {
    draggedReviewBlock = null;
    renumberReviewBlocks();
  });
  const reviewForm = document.querySelector("[data-review-form]");
  let formDirty = false;
  let formSubmitting = false;
  reviewForm?.addEventListener("input", () => { formDirty = true; });
  reviewForm?.addEventListener("change", () => { formDirty = true; });
  reviewForm?.addEventListener("click", (event) => {
    if (event.target.closest("[data-toggle-accepted], [data-accept-all], [data-remove-review-block], [data-add-review-block], [data-remove-entity]")) formDirty = true;
  });
  reviewForm?.addEventListener("submit", (event) => {
    if (!event.submitter || formSubmitting) {
      event.preventDefault();
      return;
    }
    formSubmitting = true;
    formDirty = false;
    renumberReviewBlocks();
    reviewForm.querySelectorAll("button[type='submit']").forEach((button) => {
      if (button !== event.submitter) button.disabled = true;
    });
    event.submitter.setAttribute("aria-disabled", "true");
  });
  reviewForm?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.target.matches("textarea, [contenteditable='true'], [data-entity-search], button[type='submit']")) return;
    event.preventDefault();
  });
  document.querySelector("[data-close-review]")?.addEventListener("click", (event) => {
    if (formDirty && !window.confirm("Close without saving your changes?")) event.preventDefault();
  });
  reviewList?.addEventListener("dragend", () => { formDirty = true; });
  renumberReviewBlocks();
  updateAcceptanceSummary();
})();
