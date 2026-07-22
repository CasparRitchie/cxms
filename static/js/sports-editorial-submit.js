(() => {
  const list = document.querySelector("[data-stats-list]");
  if (!list) return;
  let activeEditor = null;

  const labels = { stat: "Statistic", section: "Sub-heading", heading: "Sub-heading" };
  const syncBlock = (row) => {
    row.querySelector("[data-content-input]").value = row.querySelector("[data-editor]").innerHTML;
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
    row.draggable = true;
    row.dataset.contentBlock = "";
    row.dataset.type = type;
    const entityControl = type === "stat" ? `<div class="sew-entity-autocomplete" data-entity-control data-field-name="entity_ids_${blockId}" data-mention-prefix="entity_mention_${blockId}_"><span class="sew-cell-label">Entity links</span><div class="sew-selected-entities" data-selected-entities></div><div class="sew-entity-search-row"><select data-entity-type><option value="athlete">Athlete</option><option value="country">Country</option><option value="event">Event</option><option value="competition">Competition</option></select><input type="search" data-entity-search placeholder="Find entity"><div class="sew-entity-results" data-entity-results hidden></div></div></div>` : "";
    row.innerHTML = `<span class="sew-drag" title="Drag to reorder">⋮⋮</span><div><label><span data-block-label>${labels[type]}</span><div class="sew-rich-editor" contenteditable="true" role="textbox" aria-multiline="true" data-editor data-placeholder="Enter ${labels[type].toLowerCase()}"></div><input type="hidden" name="content_id" value="${blockId}"><input type="hidden" name="content_type" value="${type}"><input type="hidden" name="content_html" data-content-input></label>${entityControl}</div><button type="button" class="sew-remove" data-remove-stat aria-label="Remove block">×</button>`;
    return row;
  };

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
  document.querySelectorAll("[data-format]").forEach((button) => button.addEventListener("mousedown", (event) => {
    event.preventDefault();
    if (!activeEditor) return;
    activeEditor.focus();
    document.execCommand(button.dataset.format, false);
    syncBlock(activeEditor.closest("[data-content-block]"));
  }));
  document.querySelector(".sew-form").addEventListener("submit", renumber);

  let dragged;
  list.addEventListener("dragstart", (event) => { dragged = event.target.closest("[data-content-block]"); });
  list.addEventListener("dragover", (event) => {
    event.preventDefault();
    const target = event.target.closest("[data-content-block]");
    if (target && target !== dragged) {
      const box = target.getBoundingClientRect();
      list.insertBefore(dragged, event.clientY < box.top + box.height / 2 ? target : target.nextSibling);
    }
  });
  list.addEventListener("dragend", renumber);
  renumber();
})();
