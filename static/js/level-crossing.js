(() => {
  "use strict";

  const STORAGE_KEY = "chichester-crossing-observations";
  const PREFERENCES_KEY = "level-crossing-monitor-preferences-v1";
  const crossings = [
    {
      id: "whyke-road",
      name: "Whyke Road",
      area: "Chichester",
      what3words: "awake.mason.melon",
      type: "Manually controlled barriers · CCTV monitored",
      closingLeadSeconds: 95,
      clearanceSeconds: 45,
      holdGapSeconds: 120,
      minutes: [2, 8, 16, 24, 30, 32, 34, 45, 53]
    },
    {
      id: "basin-road",
      name: "Basin Road",
      area: "Chichester",
      what3words: "cubs.glare.photo",
      type: "Manually controlled barriers · CCTV monitored",
      closingLeadSeconds: 100,
      clearanceSeconds: 50,
      holdGapSeconds: 130,
      minutes: [3, 9, 17, 25, 31, 33, 35, 46, 54]
    },
    {
      id: "stockbridge-road",
      name: "Stockbridge Road",
      area: "Chichester",
      what3words: "placed.bless.dance",
      type: "Manually controlled barriers · CCTV monitored",
      closingLeadSeconds: 100,
      clearanceSeconds: 50,
      holdGapSeconds: 130,
      minutes: [4, 10, 18, 26, 31, 33, 35, 47, 55]
    }
  ];

  const demoTrainDestinations = [
    ["Portsmouth & Southsea", "westbound"],
    ["London Victoria", "eastbound"],
    ["Brighton", "eastbound"],
    ["Southampton Central", "westbound"],
    ["Littlehampton", "eastbound"]
  ];

  const stateDetails = {
    OPEN: ["Open", "crossing-status--open"],
    CLOSING_SOON: ["Closing soon", "crossing-status--closing"],
    LIKELY_CLOSED: ["Likely closed", "crossing-status--closed"],
    UNKNOWN: ["Unknown", "crossing-status--unknown"]
  };
  const observationLabels = {
    OPEN: "Open",
    CLOSING: "Closing",
    CLOSED: "Closed",
    OPENING: "Opening",
    TRAIN_PASSED: "Train passed"
  };

  const elements = {
    destinationSelect: document.getElementById("crossing-destination-select"),
    destinationMeta: document.getElementById("crossing-destination-meta"),
    routeAdvice: document.getElementById("crossing-route-advice"),
    crossingGrid: document.getElementById("crossing-grid"),
    refreshButton: document.getElementById("crossing-refresh"),
    selectionSummary: document.getElementById("crossing-selection-summary"),
    selectionChips: document.getElementById("crossing-selection-chips"),
    selectionToggle: document.getElementById("crossing-selection-toggle"),
    selectionControls: document.getElementById("crossing-selection-controls"),
    selectionOptions: document.getElementById("crossing-selection-options"),
    observationForm: document.getElementById("crossing-observation-form"),
    observationSelect: document.getElementById("crossing-observation-select"),
    observationNote: document.getElementById("crossing-observation-note"),
    observationResult: document.getElementById("crossing-observation-result"),
    observationCount: document.getElementById("crossing-observation-count"),
    observationHistory: document.getElementById("crossing-observation-history"),
    observationRows: document.getElementById("crossing-observation-rows"),
    watchSelect: document.getElementById("crossing-watch-select"),
    watchStart: document.getElementById("crossing-watch-start"),
    watchActive: document.getElementById("crossing-watch-active"),
    watchName: document.getElementById("crossing-watch-name"),
    watchElapsed: document.getElementById("crossing-watch-elapsed"),
    watchTrainCount: document.getElementById("crossing-watch-train-count"),
    watchFinish: document.getElementById("crossing-watch-finish"),
    watchResult: document.getElementById("crossing-watch-result"),
    lastUpdated: document.getElementById("crossing-last-updated"),
    modeBadge: document.querySelector(".crossing-mode-badge"),
    feedStatus: document.getElementById("crossing-feed-status"),
    feedCopy: document.getElementById("crossing-feed-copy"),
    feedArea: document.getElementById("crossing-feed-area"),
    feedFrames: document.getElementById("crossing-feed-frames"),
    feedCount: document.getElementById("crossing-feed-count"),
    feedUpdated: document.getElementById("crossing-feed-updated"),
    calibrationCopy: document.getElementById("crossing-calibration-copy"),
    feedEvents: document.getElementById("crossing-feed-events"),
    feedEventRows: document.getElementById("crossing-feed-event-rows")
  };

  if (!elements.destinationSelect || !elements.routeAdvice || !elements.crossingGrid || !elements.observationForm) return;

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function readJson(key, fallback) {
    try {
      const value = JSON.parse(window.localStorage.getItem(key) || "null");
      return value === null ? fallback : value;
    } catch (_) {
      return fallback;
    }
  }

  function readPreferences() {
    const stored = readJson(PREFERENCES_KEY, {});
    const validIds = new Set(crossings.map(({ id }) => id));
    const selectedIds = Array.isArray(stored.selectedIds)
      ? stored.selectedIds.filter((id) => validIds.has(id))
      : crossings.map(({ id }) => id);
    const primaryId = selectedIds.includes(stored.primaryId)
      ? stored.primaryId
      : (selectedIds.includes("whyke-road") ? "whyke-road" : selectedIds[0] || null);
    return {
      selectedIds,
      primaryId,
      destinationId: typeof stored.destinationId === "string" ? stored.destinationId : "waitrose-chichester"
    };
  }

  let preferences = readPreferences();
  let watchSession = null;
  let journeyCatalogue = [];
  let journeyResult = null;
  let journeyLoading = false;
  let centralReports = new Map();
  let roadClosures = new Map();

  function savePreferences() {
    window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify(preferences));
  }

  function selectedCrossings() {
    return crossings.filter(({ id }) => preferences.selectedIds.includes(id));
  }

  function ensurePrimary() {
    if (!preferences.selectedIds.includes(preferences.primaryId)) {
      preferences.primaryId = preferences.selectedIds[0] || null;
    }
  }

  function displayStatusFor(crossing, now = new Date()) {
    const roadClosure = roadClosures.get(crossing.id);
    if (roadClosure?.status === "closed") {
      return { label: "Road closed", className: "closed" };
    }
    const latest = readObservations().find((observation) => {
      if (observation.crossingId !== crossing.id || observation.state === "TRAIN_PASSED") return false;
      const age = now.getTime() - new Date(observation.observedAt).getTime();
      return Number.isFinite(age) && age >= 0 && age <= 10 * 60 * 1000;
    });
    if (latest) {
      const className = latest.state === "OPEN"
        ? "open"
        : latest.state === "CLOSED" ? "closed" : "closing";
      return { label: `${observationLabels[latest.state] || latest.state} · seen`, className };
    }
    const central = centralReports.get(crossing.id);
    if (central) {
      const age = now.getTime() - new Date(central.observedAt).getTime();
      if (Number.isFinite(age) && age >= 0 && age <= 10 * 60 * 1000) {
        const className = central.state === "OPEN"
          ? "open"
          : central.state === "CLOSED" ? "closed" : "closing";
        return { label: `${observationLabels[central.state] || central.state} · reported`, className };
      }
    }
    const prediction = predict(crossing, now);
    const className = prediction.state === "OPEN"
      ? "open"
      : prediction.state === "LIKELY_CLOSED" ? "closed" : "closing";
    return { label: `${stateDetails[prediction.state][0]} · est.`, className };
  }

  function renderSelectionChips() {
    const selected = selectedCrossings();
    elements.selectionChips.innerHTML = selected.length
      ? selected.map((crossing) => {
          const status = displayStatusFor(crossing);
          return `<span class="crossing-selection-chip${crossing.id === preferences.primaryId ? " crossing-selection-chip--primary" : ""}">
            <span class="crossing-selection-chip-name">${crossing.id === preferences.primaryId ? '<span aria-label="Primary crossing">★</span>' : ""}${escapeHtml(crossing.name)}</span>
            <span class="crossing-selection-chip-state crossing-selection-chip-state--${status.className}">${escapeHtml(status.label)}</span>
          </span>`;
        }).join("")
      : '<span class="crossing-selection-empty">No crossings selected</span>';
  }

  function renderSelection() {
    ensurePrimary();
    const selected = selectedCrossings();
    elements.selectionSummary.textContent = selected.length
      ? `${selected.length} crossing${selected.length === 1 ? "" : "s"} selected. The star marks the crossing used for route advice.`
      : "No crossings selected. Choose at least one to see predictions and record observations.";
    renderSelectionChips();

    elements.selectionOptions.innerHTML = crossings.map((crossing) => {
      const selectedHere = preferences.selectedIds.includes(crossing.id);
      return `<div class="crossing-selection-option">
        <label>
          <input type="checkbox" data-crossing-select="${escapeHtml(crossing.id)}" ${selectedHere ? "checked" : ""}>
          <span><strong>${escapeHtml(crossing.name)}</strong><small>///${escapeHtml(crossing.what3words)}</small></span>
        </label>
        <label class="crossing-primary-choice">
          <input type="radio" name="primary-crossing" data-crossing-primary="${escapeHtml(crossing.id)}" ${crossing.id === preferences.primaryId ? "checked" : ""} ${selectedHere ? "" : "disabled"}>
          Primary
        </label>
      </div>`;
    }).join("");
    populateCrossingSelects();
  }

  function populateSelect(select, previousValue) {
    const selected = selectedCrossings();
    select.innerHTML = "";
    if (!selected.length) {
      select.add(new Option("Select a crossing above", ""));
      select.disabled = true;
      return;
    }
    select.disabled = false;
    selected.forEach((crossing) => select.add(new Option(crossing.name, crossing.id)));
    select.value = selected.some(({ id }) => id === previousValue)
      ? previousValue
      : (preferences.primaryId || selected[0].id);
  }

  function populateCrossingSelects() {
    populateSelect(elements.observationSelect, elements.observationSelect.value);
    populateSelect(elements.watchSelect, elements.watchSelect.value);
    elements.watchStart.disabled = !selectedCrossings().length || Boolean(watchSession);
    elements.observationForm.querySelectorAll("button[type='submit']").forEach((button) => {
      button.disabled = !selectedCrossings().length;
    });
  }

  function movementsFor(crossing, now) {
    const hour = new Date(now);
    hour.setMinutes(0, 0, 0);
    return [-1, 0, 1]
      .flatMap((offset) => {
        const start = new Date(hour.getTime() + offset * 60 * 60 * 1000);
        return crossing.minutes.map((minute, index) => {
          const eta = new Date(start.getTime() + minute * 60 * 1000);
          const [destination, direction] = demoTrainDestinations[index % demoTrainDestinations.length];
          return { id: `demo-${crossing.id}-${eta.toISOString()}`, destination, direction, eta };
        });
      })
      .filter(({ eta }) => eta >= new Date(now.getTime() - 15 * 60 * 1000))
      .sort((left, right) => left.eta.getTime() - right.eta.getTime());
  }

  function predict(crossing, now) {
    const intervals = movementsFor(crossing, now)
      .map((movement) => ({
        start: new Date(movement.eta.getTime() - crossing.closingLeadSeconds * 1000),
        end: new Date(movement.eta.getTime() + crossing.clearanceSeconds * 1000),
        trains: [movement]
      }))
      .reduce((merged, interval) => {
        const previous = merged.at(-1);
        if (previous && interval.start.getTime() <= previous.end.getTime() + crossing.holdGapSeconds * 1000) {
          previous.end = new Date(Math.max(previous.end.getTime(), interval.end.getTime()));
          previous.trains.push(...interval.trains);
        } else {
          merged.push(interval);
        }
        return merged;
      }, []);
    const active = intervals.find(({ start, end }) => start <= now && end > now);
    const next = intervals.find(({ start }) => start > now);

    if (active) {
      return {
        state: "LIKELY_CLOSED",
        reason: active.trains.length > 1
          ? `The demo pattern groups ${active.trains.length} trains here; the live feed has not confirmed that sequence.`
          : "One demo train is inside the predicted closure window; the live feed has not confirmed it.",
        eventAt: active.end,
        eventLabel: "Predicted reopening",
        waitSeconds: Math.max(0, Math.round((active.end.getTime() - now.getTime()) / 1000)),
        trains: active.trains
      };
    }
    if (next && next.start.getTime() - now.getTime() <= 180 * 1000) {
      return {
        state: "CLOSING_SOON",
        reason: "The next demo closure begins within three minutes; the live feed has not confirmed it.",
        eventAt: next.start,
        eventLabel: "Predicted closing",
        waitSeconds: Math.max(0, Math.round((next.end.getTime() - now.getTime()) / 1000)),
        trains: next.trains
      };
    }
    return {
      state: "OPEN",
      reason: "No train is currently inside the demonstration closure window.",
      eventAt: next?.start || null,
      eventLabel: "Next predicted closing",
      waitSeconds: 0,
      trains: next?.trains || []
    };
  }

  function formatTime(date) {
    if (!date) return "Not predicted";
    return new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(date);
  }

  function formatDuration(seconds) {
    if (seconds > 0 && seconds < 60) return `${Math.max(10, Math.round(seconds / 10) * 10)} sec`;
    return `${Math.max(1, Math.round(seconds / 60))} min`;
  }

  function formatDistance(metres) {
    if (!Number.isFinite(metres)) return "Distance unavailable";
    return metres < 1000 ? `${Math.round(metres / 50) * 50} m` : `${(metres / 1000).toFixed(1)} km`;
  }

  function currentDestination() {
    return journeyCatalogue.find(({ id }) => id === preferences.destinationId) || null;
  }

  function wazeUrl(destination) {
    return `https://www.waze.com/ul?${new URLSearchParams({ q: destination.wazeQuery, navigate: "yes" })}`;
  }

  function renderDestinationControl() {
    const destination = currentDestination();
    elements.destinationSelect.innerHTML = journeyCatalogue.map((item) => (
      `<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)} · ${escapeHtml(item.area)}</option>`
    )).join("");
    if (destination) elements.destinationSelect.value = destination.id;
    elements.destinationMeta.textContent = destination
      ? `${destination.arrivalNote} Destination: ///${destination.what3words}`
      : "Choose one of your saved local journeys.";
  }

  function routeCrossingWait(route, predictionsById) {
    return (route.crossedCrossings || []).reduce((total, crossingId) => (
      total + (predictionsById.get(crossingId)?.prediction.waitSeconds || 0)
    ), 0);
  }

  function routeName(route) {
    if (route.label) return route.label;
    if (route.usesA27) return "Via the A27";
    const names = (route.crossedCrossings || [])
      .map((id) => crossings.find((crossing) => crossing.id === id)?.name)
      .filter(Boolean);
    return names.length ? `Via ${names.join(" and ")}` : "Route avoiding tracked crossings";
  }

  function renderJourneyAdvice(predictions) {
    const destination = currentDestination();
    if (!destination) {
      elements.routeAdvice.innerHTML = '<p class="crossing-eyebrow">Journey recommendation</p><h2>Choose a destination</h2><p>Select one of your familiar journeys above.</p>';
      return;
    }
    if (journeyLoading) {
      elements.routeAdvice.innerHTML = `<p class="crossing-eyebrow">Journey to ${escapeHtml(destination.name)}</p><h2>Checking live road conditions…</h2><p>Comparing traffic, walking time and the selected crossings.</p>`;
      return;
    }

    const primary = predictions.find(({ crossing }) => crossing.id === preferences.primaryId);
    const wazeLink = `<a class="crossing-route-action" href="${escapeHtml(wazeUrl(destination))}" target="_blank" rel="noopener">Open destination in Waze</a>`;
    if (!journeyResult || journeyResult.status === "not_configured") {
      const status = primary ? stateDetails[primary.prediction.state][0] : "No crossing selected";
      elements.routeAdvice.innerHTML = `
        <p class="crossing-eyebrow">To ${escapeHtml(destination.name)} · crossing estimate only</p>
        <h2>${primary ? `${escapeHtml(primary.crossing.name)}: ${escapeHtml(status)}` : "Choose a crossing"}</h2>
        <p>Live road traffic is not connected yet, so this app will not guess whether this beats the A27.</p>
        <div class="crossing-route-comparison">
          <span>Crossing: ${primary ? escapeHtml(status) : "not selected"}</span>
          <span>A27: check live traffic</span>
          <span>Parking walk: ${formatDuration(destination.parkingWalkSeconds)}</span>
        </div>
        <div class="crossing-route-actions">${wazeLink}<span class="crossing-route-source">Live ETAs need a Mapbox token</span></div>`;
      return;
    }
    if (journeyResult.status !== "ready") {
      elements.routeAdvice.innerHTML = `
        <p class="crossing-eyebrow">To ${escapeHtml(destination.name)}</p>
        <h2>Live traffic is unavailable</h2>
        <p>${escapeHtml(journeyResult.message || "Try refreshing in a moment. No estimated road time has been substituted.")}</p>
        <div class="crossing-route-actions">${wazeLink}</div>`;
      return;
    }

    const predictionsById = new Map(crossings.map((crossing) => [
      crossing.id,
      { crossing, prediction: predict(crossing, new Date()) }
    ]));
    const driving = (journeyResult.routes || []).map((route) => {
      const crossingWaitSeconds = routeCrossingWait(route, predictionsById);
      return {
        ...route,
        crossingWaitSeconds,
        totalSeconds: route.durationSeconds + crossingWaitSeconds + destination.parkingWalkSeconds
      };
    }).sort((left, right) => left.totalSeconds - right.totalSeconds);
    const bestDrive = driving[0];
    const walking = journeyResult.walking;
    const walkIsBest = walking && bestDrive && walking.durationSeconds <= bestDrive.totalSeconds;
    const heading = walkIsBest ? "Walk this one" : bestDrive ? routeName(bestDrive) : "Check the route";
    const explanation = walkIsBest
      ? `Walking is currently the quickest complete journey at about ${formatDuration(walking.durationSeconds)}.`
      : bestDrive
        ? `Allow about ${formatDuration(bestDrive.totalSeconds)} including live traffic, the current crossing estimate and the final walk.`
        : "No driving route was returned.";
    const drivingRows = driving.map((route, index) => {
      const trafficDifference = route.durationSeconds - route.typicalDurationSeconds;
      const details = [
        `${formatDuration(route.durationSeconds)} live road time`,
        route.crossingWaitSeconds ? `${formatDuration(route.crossingWaitSeconds)} crossing wait` : "no predicted crossing wait",
        `${formatDuration(destination.parkingWalkSeconds)} parking walk`
      ].join(" + ");
      return `<article class="crossing-route-option${index === 0 && !walkIsBest ? " crossing-route-option--recommended" : ""}">
        <span>${escapeHtml(routeName(route))}${index === 0 && !walkIsBest ? " · best" : ""}</span>
        <strong>${formatDuration(route.totalSeconds)}</strong>
        <small>${escapeHtml(details)} · ${formatDistance(route.distanceMetres)}${trafficDifference > 60 ? ` · ${formatDuration(trafficDifference)} slower than usual` : ""}</small>
      </article>`;
    }).join("");
    const walkingRow = walking ? `<article class="crossing-route-option${walkIsBest ? " crossing-route-option--recommended" : ""}">
      <span>Walk${walkIsBest ? " · best" : ""}</span><strong>${formatDuration(walking.durationSeconds)}</strong>
      <small>${formatDistance(walking.distanceMetres)} door to destination</small>
    </article>` : "";

    elements.routeAdvice.innerHTML = `
      <p class="crossing-eyebrow">Best complete journey to ${escapeHtml(destination.name)}</p>
      <h2>${escapeHtml(heading)}</h2>
      <p>${escapeHtml(explanation)}</p>
      <div class="crossing-journey-options">${drivingRows}${walkingRow}</div>
      <div class="crossing-route-actions">${wazeLink}<span class="crossing-route-source">Live traffic · refreshed automatically</span></div>`;
  }

  async function loadJourney() {
    if (journeyLoading) return;
    const destination = currentDestination();
    if (!destination) return;
    journeyLoading = true;
    journeyResult = null;
    renderPredictions();
    try {
      const response = await fetch(`/api/level-crossing/journeys/${encodeURIComponent(destination.id)}`, { cache: "no-store" });
      if (!response.ok) throw new Error("Journey unavailable");
      journeyResult = await response.json();
    } catch (_) {
      journeyResult = { status: "unavailable", message: "Live road information could not be loaded." };
    } finally {
      journeyLoading = false;
      renderPredictions();
    }
  }

  async function loadDestinations() {
    try {
      const response = await fetch("/api/level-crossing/destinations", { cache: "no-store" });
      if (!response.ok) throw new Error("Destinations unavailable");
      const catalogue = await response.json();
      journeyCatalogue = Array.isArray(catalogue.destinations) ? catalogue.destinations : [];
      roadClosures = new Map((catalogue.roadClosures || []).map((closure) => [closure.id, closure]));
      if (!journeyCatalogue.some(({ id }) => id === preferences.destinationId)) {
        preferences.destinationId = journeyCatalogue[0]?.id || "";
        savePreferences();
      }
      renderDestinationControl();
      renderSelectionChips();
      await loadJourney();
    } catch (_) {
      elements.destinationSelect.innerHTML = '<option value="">Destinations unavailable</option>';
      elements.destinationMeta.textContent = "Refresh the page to try again.";
      journeyResult = { status: "unavailable", message: "Your saved destinations could not be loaded." };
      renderPredictions();
    }
  }

  async function loadCalibrationStatus() {
    if (!elements.calibrationCopy) return;
    try {
      const response = await fetch("/api/level-crossing/calibration-status", { cache: "no-store" });
      if (!response.ok) throw new Error("Calibration unavailable");
      const calibration = await response.json();
      centralReports = new Map((calibration.latestReports || []).map((report) => [report.crossingId, report]));
      const total = Number(calibration.totalObservations || 0);
      const reviewReady = (calibration.crossings || []).filter(({ calibrationState }) => calibrationState === "ready_to_review").length;
      elements.calibrationCopy.textContent = calibration.status === "ready"
        ? `${total} central observation${total === 1 ? "" : "s"} collected. ${reviewReady ? `${reviewReady} crossing${reviewReady === 1 ? " is" : "s are"} ready for berth review.` : "Predictor learning is not active yet; reports are building calibration evidence."}`
        : "Central observation totals are temporarily unavailable.";
      renderSelectionChips();
      renderPredictions();
    } catch (_) {
      elements.calibrationCopy.textContent = "Central observation totals are temporarily unavailable.";
    }
  }

  function formatObservationTime(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Time unavailable";
    return new Intl.DateTimeFormat("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      timeZone: "Europe/London",
      timeZoneName: "short"
    }).format(date);
  }

  function readObservations() {
    const stored = readJson(STORAGE_KEY, []);
    return Array.isArray(stored) ? stored : [];
  }

  function writeObservations(observations) {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(observations.slice(0, 200)));
  }

  function renderObservations() {
    const observations = readObservations();
    elements.observationCount.hidden = observations.length === 0;
    elements.observationCount.querySelector("strong").textContent = observations.length;
    elements.observationHistory.hidden = observations.length === 0;
    elements.observationRows.innerHTML = observations.slice(0, 20).map((observation) => {
      const crossing = crossings.find(({ id }) => id === observation.crossingId);
      const syncLabel = observation.syncedAt
        ? '<span class="crossing-observation-sync crossing-observation-sync--saved">Central copy saved</span>'
        : observation.syncEligible
          ? '<span class="crossing-observation-sync">Central sync pending</span>'
          : '<span class="crossing-observation-sync">Device only</span>';
      const note = observation.note
        ? `<span class="crossing-observation-note">${escapeHtml(observation.note)}</span>`
        : "";
      return `<li>
        <strong>${escapeHtml(crossing?.name || observation.crossingId || "Crossing")} · ${escapeHtml(observationLabels[observation.state] || observation.state || "Unknown")}</strong>
        <time datetime="${escapeHtml(observation.observedAt || "")}">${escapeHtml(formatObservationTime(observation.observedAt))}</time>
        ${note}${syncLabel}
      </li>`;
    }).join("");
  }

  function makeId(prefix) {
    const value = window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
    return `${prefix}-${value}`;
  }

  function serialisePrediction(crossing, now) {
    const prediction = predict(crossing, now);
    return {
      state: prediction.state,
      eventAt: prediction.eventAt?.toISOString() || null,
      waitSeconds: prediction.waitSeconds,
      demoTrainCount: prediction.trains.length
    };
  }

  async function syncObservation(observation) {
    if (!observation.syncEligible || observation.syncedAt) return false;
    try {
      const response = await fetch("/api/level-crossing/observations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(observation)
      });
      if (!response.ok) return false;
      const observations = readObservations();
      const saved = observations.find(({ id }) => id === observation.id);
      if (saved) {
        saved.syncedAt = new Date().toISOString();
        writeObservations(observations);
        renderObservations();
      }
      return true;
    } catch (_) {
      return false;
    }
  }

  function syncPendingObservations() {
    readObservations()
      .filter(({ syncEligible, syncedAt }) => syncEligible && !syncedAt)
      .slice(-20)
      .forEach((observation) => { void syncObservation(observation); });
  }

  function recordObservation({ crossingId, state, eventKind = "quick", sessionId = "", note = "" }) {
    const crossing = crossings.find(({ id }) => id === crossingId);
    if (!crossing || !observationLabels[state]) return null;
    const now = new Date();
    const observation = {
      id: makeId("obs"),
      crossingId,
      state,
      observedAt: now.toISOString(),
      note: String(note).trim().slice(0, 300),
      eventKind,
      sessionId,
      prediction: serialisePrediction(crossing, now),
      syncEligible: true
    };
    writeObservations([observation, ...readObservations()]);
    renderObservations();
    renderSelectionChips();
    void syncObservation(observation);
    return observation;
  }

  function renderPredictions() {
    const now = new Date();
    renderSelectionChips();
    const selected = selectedCrossings();
    const predictions = selected.map((crossing) => ({ crossing, prediction: predict(crossing, now) }));
    const primary = predictions.find(({ crossing }) => crossing.id === preferences.primaryId);

    if (!primary) {
      renderJourneyAdvice(predictions);
      elements.crossingGrid.innerHTML = '<p class="crossing-grid-empty">No crossings selected.</p>';
      elements.lastUpdated.textContent = `Updated ${formatTime(now)}`;
      return;
    }

    renderJourneyAdvice(predictions);

    elements.crossingGrid.innerHTML = predictions.map(({ crossing, prediction }) => {
      const roadClosure = roadClosures.get(crossing.id);
      const [predictedLabel, predictedStatusClass] = stateDetails[prediction.state];
      const label = roadClosure?.status === "closed" ? "Road closed" : predictedLabel;
      const statusClass = roadClosure?.status === "closed" ? "crossing-status--closed" : predictedStatusClass;
      const nextTrain = prediction.trains[0]
        ? `<span>Demo train: ${escapeHtml(prediction.trains[0].destination)} · ${escapeHtml(prediction.trains[0].direction)}</span>`
        : "";
      const reason = roadClosure?.status === "closed"
        ? roadClosure.message
        : prediction.reason;
      const predictionMeta = roadClosure?.status === "closed"
        ? "<span>Road availability overrides the barrier estimate</span>"
        : `<span>${escapeHtml(prediction.eventLabel)}: <strong>${formatTime(prediction.eventAt)}</strong></span>
          <span>Confidence: demonstration</span>${nextTrain}`;
      return `<article class="crossing-card${crossing.id === preferences.primaryId ? " crossing-card--primary" : ""}">
        <h3>${escapeHtml(crossing.name)}</h3>
        ${crossing.id === preferences.primaryId ? '<span class="crossing-primary-tag">Primary route crossing</span>' : ""}
        <p class="crossing-type">${escapeHtml(crossing.type)}<br><span>///${escapeHtml(crossing.what3words)}</span></p>
        <span class="crossing-status ${statusClass}">${label}</span>
        <p class="crossing-prediction-reason">${escapeHtml(reason)}</p>
        <div class="crossing-prediction-meta">
          ${predictionMeta}
        </div>
      </article>`;
    }).join("");
    elements.lastUpdated.textContent = `Updated ${formatTime(now)}`;
  }

  function formatFeedTime(value) {
    return value ? formatTime(new Date(value)) : "Waiting";
  }

  function renderFeedStatus(feed) {
    elements.feedArea.textContent = feed.area || "CH";
    elements.feedFrames.textContent = String(feed.frameCount || 0);
    elements.feedCount.textContent = String(feed.messageCount || 0);
    elements.feedUpdated.textContent = formatFeedTime(feed.lastMessageAt);
    elements.feedStatus.className = "crossing-feed-status";
    if (feed.status === "connected") {
      elements.feedStatus.textContent = "Connected";
      elements.feedStatus.classList.add("crossing-feed-status--connected");
      elements.modeBadge.textContent = "Live feed · calibrating";
      elements.feedCopy.textContent = feed.messageCount
        ? "Receiving Chichester signalling messages. Field observations can now be compared with nearby berth movements."
        : "Connected to Network Rail and waiting for the next Chichester signalling message.";
    } else if (feed.status === "not_configured") {
      elements.feedStatus.textContent = "Not configured";
      elements.feedStatus.classList.add("crossing-feed-status--error");
      elements.modeBadge.textContent = "Simulation mode";
      elements.feedCopy.textContent = "The server cannot see the Network Rail username and password environment variables.";
    } else {
      elements.feedStatus.textContent = "Connecting";
      elements.modeBadge.textContent = "Simulation · connecting";
      elements.feedCopy.textContent = feed.lastError
        ? `The live connection is retrying (${feed.lastError}). Simulation remains available.`
        : "Opening the Network Rail TD connection. Simulation remains available while it starts.";
    }
    const events = Array.isArray(feed.recentEvents) ? feed.recentEvents : [];
    elements.feedEvents.hidden = events.length === 0;
    elements.feedEventRows.innerHTML = events.map((event) => {
      const movement = [event.from, event.to].filter(Boolean).join(" → ") || "Signal update";
      return `<tr><td>${escapeHtml(formatFeedTime(event.receivedAt))}</td><td>${escapeHtml(event.type || "")}</td><td>${escapeHtml(movement)}</td><td>${escapeHtml(event.descriptor || "—")}</td></tr>`;
    }).join("");
  }

  async function loadFeedStatus() {
    try {
      const response = await fetch("/api/level-crossing/td-status", { cache: "no-store" });
      if (!response.ok) throw new Error("Status unavailable");
      renderFeedStatus(await response.json());
    } catch (_) {
      renderFeedStatus({ status: "connecting", area: "CH", lastError: "status endpoint unavailable" });
    }
  }

  function updateWatchElapsed() {
    if (!watchSession) return;
    const seconds = Math.max(0, Math.floor((Date.now() - watchSession.startedAt) / 1000));
    elements.watchElapsed.textContent = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
  }

  elements.selectionToggle.addEventListener("click", () => {
    const opening = elements.selectionControls.hidden;
    elements.selectionControls.hidden = !opening;
    elements.selectionToggle.setAttribute("aria-expanded", String(opening));
    elements.selectionToggle.textContent = opening ? "Done" : "Edit crossings";
  });

  elements.destinationSelect.addEventListener("change", () => {
    if (!journeyCatalogue.some(({ id }) => id === elements.destinationSelect.value)) return;
    preferences.destinationId = elements.destinationSelect.value;
    savePreferences();
    renderDestinationControl();
    void loadJourney();
  });

  elements.selectionOptions.addEventListener("change", (event) => {
    const selectId = event.target.dataset.crossingSelect;
    const primaryId = event.target.dataset.crossingPrimary;
    if (selectId) {
      preferences.selectedIds = event.target.checked
        ? [...new Set([...preferences.selectedIds, selectId])]
        : preferences.selectedIds.filter((id) => id !== selectId);
    }
    if (primaryId && event.target.checked) preferences.primaryId = primaryId;
    ensurePrimary();
    savePreferences();
    renderSelection();
    renderPredictions();
  });

  elements.refreshButton.addEventListener("click", () => {
    renderPredictions();
    void loadJourney();
    void loadFeedStatus();
    syncPendingObservations();
  });

  elements.observationForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const submitter = event.submitter;
    if (!submitter?.value || !elements.observationSelect.value) return;
    const observation = recordObservation({
      crossingId: elements.observationSelect.value,
      state: submitter.value,
      note: elements.observationNote.value
    });
    const crossing = crossings.find(({ id }) => id === observation.crossingId);
    elements.observationNote.value = "";
    elements.observationResult.textContent = `${observationLabels[observation.state]} recorded for ${crossing.name} at ${formatObservationTime(observation.observedAt)}.`;
  });

  elements.watchStart.addEventListener("click", () => {
    const crossing = crossings.find(({ id }) => id === elements.watchSelect.value);
    if (!crossing) return;
    watchSession = {
      id: makeId("session"),
      crossingId: crossing.id,
      startedAt: Date.now(),
      trainCount: 0
    };
    elements.watchActive.hidden = false;
    elements.watchStart.disabled = true;
    elements.watchSelect.disabled = true;
    elements.watchName.textContent = `Watching ${crossing.name}`;
    elements.watchTrainCount.textContent = "0";
    elements.watchResult.textContent = "Session started. Tap only when safely stationary.";
    updateWatchElapsed();
  });

  elements.watchActive.addEventListener("click", (event) => {
    const state = event.target.dataset.watchState;
    if (!watchSession || !state) return;
    const observation = recordObservation({
      crossingId: watchSession.crossingId,
      state,
      eventKind: "watch",
      sessionId: watchSession.id
    });
    if (state === "TRAIN_PASSED") {
      watchSession.trainCount += 1;
      elements.watchTrainCount.textContent = String(watchSession.trainCount);
    }
    elements.watchResult.textContent = `${observationLabels[state]} recorded at ${formatObservationTime(observation.observedAt)}.`;
  });

  elements.watchFinish.addEventListener("click", () => {
    if (!watchSession) return;
    const crossing = crossings.find(({ id }) => id === watchSession.crossingId);
    const count = watchSession.trainCount;
    watchSession = null;
    elements.watchActive.hidden = true;
    elements.watchSelect.disabled = false;
    elements.watchStart.disabled = !selectedCrossings().length;
    elements.observationResult.textContent = `${crossing.name} watch session finished with ${count} train${count === 1 ? "" : "s"} recorded.`;
  });

  renderSelection();
  renderObservations();
  renderPredictions();
  void loadDestinations();
  void loadCalibrationStatus();
  void loadFeedStatus();
  syncPendingObservations();
  window.setInterval(renderPredictions, 30000);
  window.setInterval(loadJourney, 90000);
  window.setInterval(loadCalibrationStatus, 30000);
  window.setInterval(loadFeedStatus, 10000);
  window.setInterval(updateWatchElapsed, 1000);
})();
