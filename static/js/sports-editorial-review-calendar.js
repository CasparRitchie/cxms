(() => {
  const form = document.querySelector("[data-review-form]");
  const picker = form?.querySelector("[data-review-calendar-picker]");
  const optionsElement = document.querySelector("#sports-editorial-review-calendar-options");
  if (!form || !picker || !optionsElement) return;

  const events = JSON.parse(optionsElement.textContent);
  const search = picker.querySelector("[data-calendar-search]");
  const selectedId = picker.querySelector("[data-calendar-event]");
  const results = picker.querySelector("[data-calendar-results]");
  const message = picker.querySelector("[data-calendar-message]");
  const idDisplay = form.querySelector("[data-client-event-id]");
  const sport = form.querySelector("[data-core-sport]");
  const competition = form.querySelector("[data-core-competition]");
  const season = form.querySelector("[data-core-season]");
  let activeIndex = -1;

  const compatible = () => events.filter((item) => (
    item.sport === sport.value
    && item.competition === competition.value.trim()
    && String(item.season_code) === season.value.trim()
  ));

  const close = () => {
    results.hidden = true;
    search.setAttribute("aria-expanded", "false");
    search.removeAttribute("aria-activedescendant");
    activeIndex = -1;
  };

  const clearSelection = (clearSearch = false) => {
    selectedId.value = "";
    idDisplay.textContent = "—";
    if (clearSearch) search.value = "";
  };

  const choose = (item) => {
    selectedId.value = item.canonical_id;
    search.value = item.location;
    idDisplay.textContent = item.canonical_id;
    message.textContent = `Selected ${item.label}`;
    close();
    search.dispatchEvent(new Event("change", { bubbles: true }));
  };

  const setActive = (index) => {
    const buttons = [...results.querySelectorAll("button[role='option']")];
    if (!buttons.length) return;
    activeIndex = (index + buttons.length) % buttons.length;
    buttons.forEach((button, buttonIndex) => {
      const active = buttonIndex === activeIndex;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-selected", String(active));
    });
    const active = buttons[activeIndex];
    search.setAttribute("aria-activedescendant", active.id);
    active.scrollIntoView({ block: "nearest" });
  };

  const render = () => {
    if (document.activeElement !== search) return;
    const available = compatible();
    const query = search.value.trim().toLocaleLowerCase();
    const matches = available.filter((item) => !query || item.search_text.toLocaleLowerCase().includes(query));
    results.replaceChildren();
    activeIndex = -1;
    if (!sport.value || !competition.value.trim() || !/^\d{4}$/.test(season.value.trim())) {
      message.textContent = "Choose Sport, Competition and a four-digit Season, then search Location.";
      close();
      return;
    }
    if (!available.length) {
      message.textContent = "No locally stored FIS calendar events are available for these choices.";
      close();
      return;
    }
    matches.slice(0, 50).forEach((item, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.id = `review-calendar-event-option-${index}`;
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", "false");
      button.textContent = item.label;
      button.addEventListener("mousedown", (event) => event.preventDefault());
      button.addEventListener("click", () => choose(item));
      results.appendChild(button);
    });
    if (!matches.length) {
      const empty = document.createElement("p");
      empty.textContent = "No matching compatible calendar events.";
      results.appendChild(empty);
    }
    message.textContent = `${available.length} compatible local calendar event${available.length === 1 ? "" : "s"} available.`;
    results.hidden = false;
    search.setAttribute("aria-expanded", "true");
  };

  search.addEventListener("focus", render);
  search.addEventListener("input", () => { clearSelection(false); render(); });
  search.addEventListener("blur", close);
  search.addEventListener("keydown", (event) => {
    const buttons = [...results.querySelectorAll("button[role='option']")];
    if (event.key === "ArrowDown" && buttons.length) {
      event.preventDefault(); setActive(activeIndex + 1);
    } else if (event.key === "ArrowUp" && buttons.length) {
      event.preventDefault(); setActive(activeIndex <= 0 ? buttons.length - 1 : activeIndex - 1);
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (activeIndex >= 0) buttons[activeIndex].click();
    } else if (event.key === "Escape") {
      event.preventDefault(); close();
    }
  });
  [sport, competition, season].forEach((control) => control.addEventListener("input", () => {
    const selected = events.find((item) => item.canonical_id === selectedId.value);
    if (selected && !compatible().includes(selected)) clearSelection(true);
    render();
  }));
})();
