(() => {
  const form = document.querySelector("[data-creation-form]");
  if (!form) return;
  const options = JSON.parse(document.querySelector("#sports-editorial-creation-options").textContent);
  const sport = form.querySelector("[data-sport]");
  const competition = form.querySelector("[data-competition]");
  const eventName = form.querySelector("[data-event]");
  const calendar = form.querySelector("[data-calendar-event]");
  const calendarSearch = form.querySelector("[data-calendar-search]");
  const calendarResults = form.querySelector("[data-calendar-results]");
  const calendarMessage = form.querySelector("[data-calendar-message]");
  const clientEventId = form.querySelector("[data-client-event-id]");
  const createButton = form.querySelector("[data-create-button]");
  let explicitSubmission = false;
  let activeCalendarIndex = -1;

  const formatPickerDate = (value) => {
    const [year, month, day] = value.split("-").map(Number);
    return new Intl.DateTimeFormat("en-GB", {
      day: "2-digit", month: "short", year: "numeric", timeZone: "UTC",
    }).format(new Date(Date.UTC(year, month - 1, day))).replace(/ /g, "-");
  };

  form.querySelectorAll("[data-date-picker]").forEach((picker) => {
    const display = picker.parentElement?.querySelector("input:not([type='date'])");
    if (!display) return;
    picker.addEventListener("change", () => {
      if (!picker.value) return;
      display.value = formatPickerDate(picker.value);
      display.dispatchEvent(new Event("input", { bubbles: true }));
    });
  });

  const fillSelect = (select, choices, selected) => {
    select.replaceChildren(new Option("", ""));
    choices.forEach((choice) => select.add(new Option(choice, choice)));
    select.value = choices.includes(selected) ? selected : "";
  };
  const updateEvents = () => {
    const key = `${sport.value}|${competition.value}`;
    const choices = options.events[key] || [];
    fillSelect(eventName, choices, eventName.dataset.selected || eventName.value);
    eventName.dataset.selected = "";
    form.querySelector("[data-event-message]").hidden = choices.length > 0 || !competition.value;
    updateCalendar();
  };
  const updateCompetitions = () => {
    const choices = options.competitions[sport.value] || [];
    fillSelect(competition, choices, competition.dataset.selected || competition.value);
    competition.dataset.selected = "";
    form.querySelector("[data-competition-message]").hidden = choices.length > 0 || !sport.value;
    updateEvents();
  };
  const updateCalendar = () => {
    const season = form.elements.season_code.value;
    const selected = options.calendar_events.find(
      (item) => item.canonical_id === calendar.value,
    );
    if (selected && (
      selected.sport !== sport.value
      || selected.competition !== competition.value
      || String(selected.season_code) !== season
    )) {
      calendar.value = "";
      calendarSearch.value = "";
    }
    clientEventId.value = calendar.value || "";
    renderCalendarResults();
  };

  const compatibleCalendarEvents = () => {
    const season = form.elements.season_code.value;
    return options.calendar_events.filter((item) => (
      item.sport === sport.value
      && item.competition === competition.value
      && String(item.season_code) === season
    ));
  };

  const closeCalendarResults = () => {
    calendarResults.hidden = true;
    calendarSearch.setAttribute("aria-expanded", "false");
    calendarSearch.removeAttribute("aria-activedescendant");
    activeCalendarIndex = -1;
  };

  const selectCalendarEvent = (item) => {
    calendar.value = item.canonical_id;
    calendarSearch.value = item.location;
    clientEventId.value = item.canonical_id;
    calendarMessage.textContent = `Selected ${item.label}`;
    closeCalendarResults();
  };

  const setActiveCalendarResult = (index) => {
    const buttons = [...calendarResults.querySelectorAll("button[role='option']")];
    if (!buttons.length) return;
    activeCalendarIndex = (index + buttons.length) % buttons.length;
    buttons.forEach((button, buttonIndex) => {
      const active = buttonIndex === activeCalendarIndex;
      button.setAttribute("aria-selected", String(active));
      button.classList.toggle("is-active", active);
    });
    const active = buttons[activeCalendarIndex];
    calendarSearch.setAttribute("aria-activedescendant", active.id);
    active.scrollIntoView({ block: "nearest" });
  };

  function renderCalendarResults() {
    if (!calendarSearch || document.activeElement !== calendarSearch) return;
    const available = compatibleCalendarEvents();
    const query = calendarSearch.value.trim().toLocaleLowerCase();
    const matches = available.filter((item) => (
      !query || item.search_text.toLocaleLowerCase().includes(query)
    ));
    calendarResults.replaceChildren();
    activeCalendarIndex = -1;
    if (!sport.value || !competition.value || !form.elements.season_code.value) {
      calendarMessage.textContent = "Choose Sport, Competition and Season, then search the local FIS calendar.";
      closeCalendarResults();
      return;
    }
    if (!available.length) {
      calendarMessage.textContent = "No locally stored FIS calendar events are available for these choices.";
      closeCalendarResults();
      return;
    }
    matches.slice(0, 50).forEach((item, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.id = `calendar-event-option-${index}`;
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", "false");
      button.textContent = item.label;
      button.addEventListener("mousedown", (event) => event.preventDefault());
      button.addEventListener("click", () => selectCalendarEvent(item));
      calendarResults.appendChild(button);
    });
    if (!matches.length) {
      const empty = document.createElement("p");
      empty.textContent = "No matching local calendar events.";
      calendarResults.appendChild(empty);
    }
    calendarMessage.textContent = `${available.length} compatible local calendar event${available.length === 1 ? "" : "s"} available.`;
    calendarResults.hidden = false;
    calendarSearch.setAttribute("aria-expanded", "true");
  }
  sport.addEventListener("change", () => { competition.value = ""; eventName.value = ""; updateCompetitions(); });
  competition.addEventListener("change", () => { eventName.value = ""; updateEvents(); });
  form.elements.season_code.addEventListener("input", updateCalendar);
  calendarSearch.addEventListener("focus", renderCalendarResults);
  calendarSearch.addEventListener("input", () => {
    calendar.value = "";
    clientEventId.value = "";
    renderCalendarResults();
  });
  calendarSearch.addEventListener("keydown", (event) => {
    const buttons = [...calendarResults.querySelectorAll("button[role='option']")];
    if (event.key === "ArrowDown" && buttons.length) {
      event.preventDefault();
      setActiveCalendarResult(activeCalendarIndex + 1);
    } else if (event.key === "ArrowUp" && buttons.length) {
      event.preventDefault();
      setActiveCalendarResult(activeCalendarIndex <= 0 ? buttons.length - 1 : activeCalendarIndex - 1);
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (activeCalendarIndex >= 0) buttons[activeCalendarIndex].click();
    } else if (event.key === "Escape") {
      event.preventDefault();
      closeCalendarResults();
    }
  });
  calendarSearch.addEventListener("blur", closeCalendarResults);
  form.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.target !== createButton && !event.target.matches("select, textarea, [contenteditable='true']")) {
      event.preventDefault();
    }
  });
  createButton.addEventListener("click", () => { explicitSubmission = true; });
  form.addEventListener("submit", (event) => {
    if (!explicitSubmission) {
      event.preventDefault();
      return;
    }
    if (!form.checkValidity()) {
      explicitSubmission = false;
      return;
    }
    createButton.disabled = true;
  });
  updateCompetitions();
  updateCalendar();
})();
