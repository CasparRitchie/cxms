(() => {
  const list = document.querySelector("[data-stats-list]");
  const addButton = document.querySelector("[data-add-stat]");
  if (!list || !addButton) return;

  const renumber = () => {
    list.querySelectorAll(".sew-stat-input").forEach((row, index) => {
      row.querySelector("label > span").textContent = `Bullet ${index + 1}`;
    });
  };

  const makeRow = () => {
    const row = document.createElement("div");
    row.className = "sew-stat-input";
    row.draggable = true;
    row.innerHTML = '<span class="sew-drag" title="Drag to reorder">⋮⋮</span><label><span>Bullet</span><textarea name="stats" rows="3" placeholder="Enter one curated fact"></textarea></label><button type="button" class="sew-remove" data-remove-stat aria-label="Remove bullet">×</button>';
    return row;
  };

  addButton.addEventListener("click", () => {
    const row = makeRow();
    list.appendChild(row);
    row.querySelector("textarea").focus();
    renumber();
  });
  list.addEventListener("click", (event) => {
    if (!event.target.matches("[data-remove-stat]")) return;
    if (list.children.length === 1) list.querySelector("textarea").value = "";
    else event.target.closest(".sew-stat-input").remove();
    renumber();
  });
  let dragged;
  list.addEventListener("dragstart", (event) => { dragged = event.target.closest(".sew-stat-input"); });
  list.addEventListener("dragover", (event) => {
    event.preventDefault();
    const target = event.target.closest(".sew-stat-input");
    if (target && target !== dragged) {
      const box = target.getBoundingClientRect();
      list.insertBefore(dragged, event.clientY < box.top + box.height / 2 ? target : target.nextSibling);
    }
  });
  list.addEventListener("dragend", renumber);
})();
