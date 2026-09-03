(() => {
  const list = document.querySelector("[data-stats-list]");
  if (!list) return;
  let activeEditor = null;

  const labels = { stat: "Statistic", section: "Sub-heading", heading: "Sub-heading" };
  const shortLabels = { stat: "Stat", section: "Head", heading: "Head" };
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
      row.querySelector("[data-block-label]").textContent = `${shortLabels[row.dataset.type]} ${counts[kind]}`;
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
    const entityControl = type === "stat" ? `<div class="sew-entity-autocomplete sew-entity-autocomplete--inline-only" data-entity-control data-field-name="entity_ids_${blockId}" data-mention-prefix="entity_mention_${blockId}_"><div class="sew-selected-entities" data-selected-entities hidden></div><div class="sew-entity-suggestions" data-entity-suggestions aria-live="polite"></div><div class="sew-entity-results" data-entity-results hidden></div></div>` : "";
    row.innerHTML = `
  <span
    class="sew-drag"
    title="Drag to reorder"
    draggable="true"
  >
    ⋮⋮
  </span>

  <div>
    <div class="sew-stat-field">
      <span data-block-label>${shortLabels[type]}</span>

      <div class="sew-working-editor">
        <div
          class="sew-mini-toolbar"
          aria-label="Formatting"
        >
          <button
            type="button"
            data-format="bold"
            aria-label="Bold"
          >
            <strong>B</strong>
          </button>

          <button
            type="button"
            data-format="italic"
            aria-label="Italic"
          >
            <em>I</em>
          </button>

          ${type === "stat" ? `<button type="button" data-link-entity aria-label="Add entity link" title="Add entity link"><span aria-hidden="true">🔗</span></button>` : ""}
        </div>

        <div
          class="sew-rich-editor"
          contenteditable="true"
          role="textbox"
          aria-multiline="true"
          aria-label="${labels[type]}"
          spellcheck="true"
          data-editor
          data-placeholder="Enter ${labels[type].toLowerCase()}"
        ></div>
      </div>

      <input
        type="hidden"
        name="content_id"
        value="${blockId}"
      >

      <input
        type="hidden"
        name="content_type"
        value="${type}"
      >

      <input
        type="hidden"
        name="content_html"
        data-content-input
      >
    </div>

    ${type === "stat" ? `<button class="sew-button sew-button--small sew-stat-link-check" type="button" data-check-block-entities aria-expanded="false">Check links</button>` : ""}
    ${entityControl}
  </div>

  <button
    type="button"
    class="sew-remove"
    data-remove-stat
    aria-label="Remove block"
  >
    ×
  </button>
`;
    return row;
  };

  const emptyPlaceholder = list.querySelector("input[name='content_id'][value='']")?.closest("[data-content-block]");
  if (emptyPlaceholder) emptyPlaceholder.replaceWith(makeRow("stat"));

  document.querySelectorAll("[data-add-block]").forEach((button) => button.addEventListener("click", () => {
    const row = makeRow(button.dataset.addBlock);
    list.appendChild(row);
    row.dispatchEvent(new CustomEvent("sports-editorial:block-added", { bubbles: true }));
    row.querySelector("[data-editor]").focus();
    renumber();
  }));
  list.addEventListener("focusin", (event) => { if (event.target.matches("[data-editor]")) activeEditor = event.target; });
  list.addEventListener("pointerdown", (event) => {
  const editor = event.target.closest("[data-editor]");

  if (!editor || !editor.isContentEditable) return;

  activeEditor = editor;
});
  list.addEventListener("input", (event) => { if (event.target.matches("[data-editor]")) syncBlock(event.target.closest("[data-content-block]")); });
  list.addEventListener("paste", (event) => {
    if (!event.target.matches("[data-editor]")) return;
    event.preventDefault();
    document.execCommand("insertText", false, event.clipboardData.getData("text/plain"));
  });
  list.addEventListener("click", (event) => {
    if (!event.target.matches("[data-remove-stat]")) return;
    const block = event.target.closest("[data-content-block]");
    if (
      block.dataset.type === "stat" &&
      !window.confirm("Remove this statistic from the stat sheet?")
    ) return;
    if (list.children.length === 1) block.querySelector("[data-editor]").innerHTML = "";
    else block.remove();
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
  let formSubmitting = false;
  form.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.target.matches("textarea, [contenteditable='true'], [data-entity-lookup], button[type='submit'], select")) return;
    event.preventDefault();
  });
  form.addEventListener("submit", (event) => {
    if (!event.submitter || formSubmitting) {
      event.preventDefault();
      return;
    }
    formSubmitting = true;
    renumber();
    form.querySelectorAll("button[type='submit']").forEach((button) => {
      // The activated button must remain enabled until the browser constructs
      // the request, otherwise its name/value (for example action=submit) is
      // omitted and Submit for sub edit is indistinguishable from Save.
      if (button !== event.submitter) button.disabled = true;
    });
    event.submitter.setAttribute("aria-disabled", "true");
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
