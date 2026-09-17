(() => {
  const form = document.querySelector("[data-review-form]");
  const picker = form?.querySelector("[data-review-calendar-picker]");
  const optionsElement = document.querySelector("#sports-editorial-review-calendar-options");
  const choicesElement = document.querySelector("#sports-editorial-core-choice-options");
  if (!form || !picker || !optionsElement || !choicesElement) return;

  const events = JSON.parse(optionsElement.textContent);
  const choices = JSON.parse(choicesElement.textContent);
  const search = picker.querySelector("[data-calendar-search]");
  const selectedId = picker.querySelector("[data-calendar-event]");
  const results = picker.querySelector("[data-calendar-results]");
  const message = picker.querySelector("[data-calendar-message]");
  const idDisplay = form.querySelector("[data-client-event-id]");
  const sport = form.querySelector("[data-core-sport]");
  const competition = form.querySelector("[data-core-competition]");
  const eventName = form.querySelector("[data-core-event]");
  const gender = form.querySelector("[data-core-gender]");
  const season = form.querySelector("[data-core-season]");
  const choicePickers = new Map();
  let activeIndex = -1;

  const selectedValues = (select) => [...select.selectedOptions].map((option) => option.value).filter(Boolean);
  const choicePickerLabel = (select) => select === eventName ? "Event" : "Gender";
  const updateChoicePickerSummary = (select) => {
    const picker = choicePickers.get(select);
    if (!picker) return;
    const labels = [...select.selectedOptions]
      .filter((option) => option.value)
      .map((option) => option.textContent.trim());
    picker.trigger.textContent = labels.join(", ") || `Choose ${choicePickerLabel(select)}`;
  };
  const refreshChoicePicker = (select) => {
    let picker = choicePickers.get(select);
    if (!picker) {
      const wrapper = document.createElement("div");
      wrapper.className = "sew-core-choice-picker";
      wrapper.hidden = true;
      const trigger = document.createElement("button");
      trigger.type = "button";
      trigger.className = "sew-core-choice-trigger";
      trigger.setAttribute("aria-expanded", "false");
      const panel = document.createElement("div");
      panel.className = "sew-core-choice-options";
      panel.hidden = true;
      trigger.addEventListener("click", () => {
        const opening = panel.hidden;
        document.querySelectorAll(".sew-core-choice-options:not([hidden])").forEach((other) => { other.hidden = true; });
        document.querySelectorAll(".sew-core-choice-trigger[aria-expanded='true']").forEach((other) => { other.setAttribute("aria-expanded", "false"); });
        panel.hidden = !opening;
        trigger.setAttribute("aria-expanded", String(opening));
      });
      wrapper.append(trigger, panel);
      select.after(wrapper);
      picker = { wrapper, trigger, panel };
      choicePickers.set(select, picker);
    }

    const enabled = select.multiple;
    select.hidden = enabled;
    select.closest(".sew-core-choice-field")?.classList.toggle("is-choice-picker", enabled);
    picker.wrapper.hidden = !enabled;
    if (!enabled) return;

    picker.panel.replaceChildren();
    [...select.options].filter((option) => option.value).forEach((option) => {
      const row = document.createElement("label");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = option.selected;
      checkbox.addEventListener("change", () => {
        option.selected = checkbox.checked;
        updateChoicePickerSummary(select);
        select.dispatchEvent(new Event("change", { bubbles: true }));
      });
      row.append(checkbox, document.createTextNode(option.textContent));
      picker.panel.appendChild(row);
    });
    const done = document.createElement("button");
    done.type = "button";
    done.className = "sew-button sew-button--primary sew-core-choice-done";
    done.textContent = "Done";
    done.addEventListener("click", () => {
      picker.panel.hidden = true;
      picker.trigger.setAttribute("aria-expanded", "false");
      picker.trigger.focus();
    });
    picker.panel.appendChild(done);
    updateChoicePickerSummary(select);
  };
  const replaceOptions = (select, values, emptyLabel, selected = []) => {
    const options = [new Option(emptyLabel, "")];
    values.forEach((value) => options.push(new Option(value.label || value, value.value || value)));
    select.replaceChildren(...options);
    const wanted = Array.isArray(selected) ? selected : String(selected || "").split("|||").filter(Boolean);
    [...select.options].forEach((option) => { option.selected = wanted.includes(option.value); });
    refreshChoicePicker(select);
  };

  const updateGenders = () => {
    const key = `${sport.value}|||${competition.value}`;
    const chosenEvents = selectedValues(eventName);
    const selectedEvents = (choices.events[key] || []).filter((choice) => chosenEvents.includes(choice.value));
    const codes = selectedEvents.length ? selectedEvents.map((choice) => choice.genders).join("") : (choices.genders[key] || []).join("");
    const labels = { M: "Men", W: "Women", X: "Mixed" };
    const previous = gender.dataset.selected || selectedValues(gender);
    replaceOptions(gender, ["M", "W", "X"].filter((code) => codes.includes(code)).map((code) => ({ value: code, label: labels[code] })), "Choose Gender", previous);
    gender.dataset.selected = "";
  };

  sport.addEventListener("change", () => {
    replaceOptions(competition, choices.competitions[sport.value] || [], "Choose Competition");
    replaceOptions(eventName, [], "None available");
    const capabilities = choices.sport_capabilities[sport.value] || {};
    eventName.multiple = Boolean(capabilities.multiple_events);
    gender.multiple = Boolean(capabilities.multiple_genders);
    refreshChoicePicker(eventName);
    refreshChoicePicker(gender);
    updateGenders();
  });
  competition.addEventListener("change", () => {
    const key = `${sport.value}|||${competition.value}`;
    const values = choices.events[key] || [];
    const capabilities = choices.sport_capabilities[sport.value] || {};
    eventName.multiple = Boolean(capabilities.multiple_events);
    gender.multiple = Boolean(capabilities.multiple_genders);
    replaceOptions(eventName, values, values.length ? "None" : "None available", eventName.dataset.selected || selectedValues(eventName));
    eventName.dataset.selected = "";
    eventName.required = values.length > 0;
    refreshChoicePicker(eventName);
    refreshChoicePicker(gender);
    updateGenders();
  });
  eventName.addEventListener("change", updateGenders);

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
    matches.forEach((item, index) => {
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
  const initialCapabilities = choices.sport_capabilities[sport.value] || {};
  eventName.multiple = Boolean(initialCapabilities.multiple_events);
  gender.multiple = Boolean(initialCapabilities.multiple_genders);
  refreshChoicePicker(eventName);
  refreshChoicePicker(gender);
  document.addEventListener("click", (event) => {
    if (event.target.closest(".sew-core-choice-picker")) return;
    choicePickers.forEach((picker) => {
      picker.panel.hidden = true;
      picker.trigger.setAttribute("aria-expanded", "false");
    });
  });
})();
