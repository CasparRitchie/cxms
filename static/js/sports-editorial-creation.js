(() => {
  const form = document.querySelector("[data-creation-form]");
  if (!form) return;
  const options = JSON.parse(document.querySelector("#sports-editorial-creation-options").textContent);
  const sport = form.querySelector("[data-sport]");
  const competition = form.querySelector("[data-competition]");
  const eventName = form.querySelector("[data-event]");
  const calendar = form.querySelector("[data-calendar-event]");
  const clientEventId = form.querySelector("[data-client-event-id]");
  const createButton = form.querySelector("[data-create-button]");
  let explicitSubmission = false;

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
    Array.from(calendar.options).forEach((option, index) => {
      if (!index) return;
      option.hidden = option.dataset.sport !== sport.value
        || option.dataset.competition !== competition.value
        || option.dataset.season !== season;
    });
    const selected = calendar.selectedOptions[0];
    if (selected && selected.hidden) calendar.value = "";
    clientEventId.value = calendar.value || "";
  };
  sport.addEventListener("change", () => { competition.value = ""; eventName.value = ""; updateCompetitions(); });
  competition.addEventListener("change", () => { eventName.value = ""; updateEvents(); });
  form.elements.season_code.addEventListener("input", updateCalendar);
  calendar.addEventListener("change", updateCalendar);
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
