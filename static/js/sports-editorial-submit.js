(() => {
  const list = document.querySelector("[data-stats-list]");
  if (!list) return;
  let activeEditor = null;

  const labels = { stat: "Statistic", section: "Sub-heading", heading: "Sub-heading" };
  const syncBlock = (row) => {
    const clone = row.querySelector("[data-editor]").cloneNode(true);
    clone.querySelectorAll("[data-entity-ref]").forEach((tag) => tag.replaceWith(document.createTextNode(tag.textContent)));
    row.querySelector("[data-content-input]").value = clone.innerHTML;
  };
  const renumber = () => {
    const counts = { stat: 0, section: 0, heading: 0 };
    list.querySelectorAll("[data-content-block]").forEach((row) => {
      const kind = row.dataset.type === "heading" ? "section" : row.dataset.type;
      counts[kind] += 1;
      row.querySelector("[data-block-label]").textContent = `${labels[row.dataset.type]} ${counts[kind]}`;
      syncBlock(row);
    });
  };
  const makeRow = (type) => {
    const blockId = crypto.randomUUID();
    const row = document.createElement("div");
    row.className = "sew-stat-input";
    row.draggable = false;
    row.dataset.contentBlock = "";
    row.dataset.type = type;
    const entityControl = type === "stat" ? `<div class="sew-entity-autocomplete" data-entity-control data-field-name="entity_ids_${blockId}" data-mention-prefix="entity_mention_${blockId}_"><span class="sew-cell-label">Linked</span><div class="sew-selected-entities" data-selected-entities></div><div class="sew-entity-results" data-entity-results hidden></div></div>` : "";
    row.innerHTML = `<span class="sew-drag" title="Drag to reorder" draggable="true">⋮⋮</span><div><label><span data-block-label>${labels[type]}</span><div class="sew-working-editor"><div class="sew-mini-toolbar" aria-label="Formatting"><button type="button" data-format="bold" aria-label="Bold"><strong>B</strong></button><button type="button" data-format="italic" aria-label="Italic"><em>I</em></button></div><div class="sew-rich-editor" contenteditable="true" role="textbox" aria-multiline="true" spellcheck="true" data-editor data-placeholder="Enter ${labels[type].toLowerCase()}"></div></div><input type="hidden" name="content_id" value="${blockId}"><input type="hidden" name="content_type" value="${type}"><input type="hidden" name="content_html" data-content-input></label>${entityControl}</div><button type="button" class="sew-remove" data-remove-stat aria-label="Remove block">×</button>`;
    return row;
  };

  const emptyPlaceholder = list.querySelector("input[name='content_id'][value='']")?.closest("[data-content-block]");
  if (emptyPlaceholder) emptyPlaceholder.replaceWith(makeRow("stat"));

  document.querySelectorAll("[data-add-block]").forEach((button) => button.addEventListener("click", () => {
    const row = makeRow(button.dataset.addBlock);
    list.appendChild(row);
    row.querySelector("[data-editor]").focus();
    renumber();
  }));
  list.addEventListener("focusin", (event) => { if (event.target.matches("[data-editor]")) activeEditor = event.target; });
  list.addEventListener("input", (event) => { if (event.target.matches("[data-editor]")) syncBlock(event.target.closest("[data-content-block]")); });
  list.addEventListener("paste", (event) => {
    if (!event.target.matches("[data-editor]")) return;
    event.preventDefault();
    document.execCommand("insertText", false, event.clipboardData.getData("text/plain"));
  });
  list.addEventListener("click", (event) => {
    if (!event.target.matches("[data-remove-stat]")) return;
    if (list.children.length === 1) list.querySelector("[data-editor]").innerHTML = "";
    else event.target.closest("[data-content-block]").remove();
    renumber();
  });
  list.addEventListener("mousedown", (event) => {
    const button = event.target.closest("[data-format]");
    if (!button) return;
    event.preventDefault();
    if (!activeEditor) return;
    activeEditor.focus();
    document.execCommand(button.dataset.format, false);
    syncBlock(activeEditor.closest("[data-content-block]"));
  });
  const form = document.querySelector(".sew-form");
  let explicitSubmission = false;
  form.addEventListener("click", (event) => {
    if (event.target.closest("button[type='submit']")) explicitSubmission = true;
  });
  form.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.target.matches("textarea, [contenteditable='true'], [data-entity-search], button[type='submit'], select")) return;
    event.preventDefault();
  });
  form.addEventListener("submit", (event) => {
    if (!explicitSubmission) {
      event.preventDefault();
      return;
    }
    renumber();
    form.querySelectorAll("button[type='submit']").forEach((button) => { button.disabled = true; });
  });

  let dragged;
  list.addEventListener("dragstart", (event) => {
    const handle = event.target.closest(".sew-drag");
    dragged = handle?.closest("[data-content-block]");
    if (!dragged) event.preventDefault();
  });
  list.addEventListener("dragover", (event) => {
    if (!dragged) return;
    event.preventDefault();
    const target = event.target.closest("[data-content-block]");
    if (target && target !== dragged) {
      const box = target.getBoundingClientRect();
      list.insertBefore(dragged, event.clientY < box.top + box.height / 2 ? target : target.nextSibling);
    }
  });
  list.addEventListener("dragend", () => {
    dragged = null;
    renumber();
  });
  renumber();
})();
