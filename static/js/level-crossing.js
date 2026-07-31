(() => {
  "use strict";

  const STORAGE_KEY = "chichester-crossing-observations";
  const crossings = [
    {
      id: "whyke-road",
      name: "Whyke Road",
      type: "Manually controlled barriers · CCTV monitored",
      primary: true,
      baselineDriveSeconds: 450,
      closingLeadSeconds: 95,
      clearanceSeconds: 45,
      holdGapSeconds: 120,
      minutes: [2, 8, 16, 24, 30, 32, 34, 45, 53]
    },
    {
      id: "stockbridge-road",
      name: "Stockbridge Road",
      type: "Manually controlled barriers · CCTV monitored",
      primary: false,
      baselineDriveSeconds: 510,
      closingLeadSeconds: 100,
      clearanceSeconds: 50,
      holdGapSeconds: 130,
      minutes: [4, 10, 18, 26, 31, 33, 35, 47, 55]
    },
    {
      id: "basin-road",
      name: "Basin Road",
      type: "Manually controlled barriers · CCTV monitored",
      primary: false,
      baselineDriveSeconds: 525,
      closingLeadSeconds: 100,
      clearanceSeconds: 50,
      holdGapSeconds: 130,
      minutes: [3, 9, 17, 25, 31, 33, 35, 46, 54]
    }
  ];

  const destinations = [
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

  const routeAdvice = document.getElementById("crossing-route-advice");
  const crossingGrid = document.getElementById("crossing-grid");
  const refreshButton = document.getElementById("crossing-refresh");
  const observationForm = document.getElementById("crossing-observation-form");
  const observationSelect = document.getElementById("crossing-observation-select");
  const observationNote = document.getElementById("crossing-observation-note");
  const observationResult = document.getElementById("crossing-observation-result");
  const observationCount = document.getElementById("crossing-observation-count");
  const lastUpdated = document.getElementById("crossing-last-updated");
  const modeBadge = document.querySelector(".crossing-mode-badge");
  const feedStatus = document.getElementById("crossing-feed-status");
  const feedCopy = document.getElementById("crossing-feed-copy");
  const feedArea = document.getElementById("crossing-feed-area");
  const feedCount = document.getElementById("crossing-feed-count");
  const feedUpdated = document.getElementById("crossing-feed-updated");
  const feedEvents = document.getElementById("crossing-feed-events");
  const feedEventRows = document.getElementById("crossing-feed-event-rows");

  if (!routeAdvice || !crossingGrid || !refreshButton || !observationForm) return;

  function movementsFor(crossing, now) {
    const hour = new Date(now);
    hour.setMinutes(0, 0, 0);

    return [-1, 0, 1]
      .flatMap((offset) => {
        const start = new Date(hour.getTime() + offset * 60 * 60 * 1000);
        return crossing.minutes.map((minute, index) => {
          const eta = new Date(start.getTime() + minute * 60 * 1000);
          const [destination, direction] = destinations[index % destinations.length];
          return {
            id: `demo-${crossing.id}-${eta.toISOString()}`,
            destination,
            direction,
            eta
          };
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
          ? `${active.trains.length} closely spaced trains may keep the barriers down.`
          : "A train is inside the predicted closure window.",
        eventAt: active.end,
        eventLabel: "Predicted reopening",
        waitSeconds: Math.max(0, Math.round((active.end.getTime() - now.getTime()) / 1000)),
        trains: active.trains
      };
    }

    if (next && next.start.getTime() - now.getTime() <= 180 * 1000) {
      return {
        state: "CLOSING_SOON",
        reason: "The next predicted closure begins within three minutes.",
        eventAt: next.start,
        eventLabel: "Predicted closing",
        waitSeconds: Math.max(0, Math.round((next.end.getTime() - now.getTime()) / 1000)),
        trains: next.trains
      };
    }

    return {
      state: "OPEN",
      reason: "No train is currently inside the predicted closure window.",
      eventAt: next?.start || null,
      eventLabel: "Next predicted closing",
      waitSeconds: 0,
      trains: next?.trains || []
    };
  }

  function formatTime(date) {
    if (!date) return "Not predicted";
    return new Intl.DateTimeFormat("en-GB", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit"
    }).format(date);
  }

  function formatDuration(seconds) {
    return `${Math.max(1, Math.round(seconds / 60))} min`;
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function readObservations() {
    try {
      const stored = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "[]");
      return Array.isArray(stored) ? stored : [];
    } catch (_) {
      window.localStorage.removeItem(STORAGE_KEY);
      return [];
    }
  }

  function renderObservationCount() {
    const count = readObservations().length;
    observationCount.hidden = count === 0;
    observationCount.querySelector("strong").textContent = count;
  }

  function formatFeedTime(value) {
    if (!value) return "Waiting";
    return formatTime(new Date(value));
  }

  function renderFeedStatus(feed) {
    feedArea.textContent = feed.area || "CH";
    feedCount.textContent = String(feed.messageCount || 0);
    feedUpdated.textContent = formatFeedTime(feed.lastMessageAt);
    feedStatus.className = "crossing-feed-status";

    if (feed.status === "connected") {
      feedStatus.textContent = "Connected";
      feedStatus.classList.add("crossing-feed-status--connected");
      modeBadge.textContent = "Live feed · calibrating";
      feedCopy.textContent = feed.messageCount
        ? "Receiving Chichester signalling messages. Compare these movements with the physical barriers to identify the correct berths."
        : "Connected to Network Rail and waiting for the next Chichester signalling message.";
    } else if (feed.status === "not_configured") {
      feedStatus.textContent = "Not configured";
      feedStatus.classList.add("crossing-feed-status--error");
      modeBadge.textContent = "Simulation mode";
      feedCopy.textContent = "The server cannot see the Network Rail username and password environment variables.";
    } else {
      feedStatus.textContent = "Connecting";
      modeBadge.textContent = "Simulation · connecting";
      feedCopy.textContent = feed.lastError
        ? `The live connection is retrying (${feed.lastError}). Simulation remains available.`
        : "Opening the secure Network Rail TD connection. Simulation remains available while it starts.";
    }

    const events = Array.isArray(feed.recentEvents) ? feed.recentEvents : [];
    feedEvents.hidden = events.length === 0;
    feedEventRows.innerHTML = events.map((event) => {
      const movement = [event.from, event.to].filter(Boolean).join(" → ") || "Signal update";
      return `<tr>
        <td>${escapeHtml(formatFeedTime(event.receivedAt))}</td>
        <td>${escapeHtml(event.type || "")}</td>
        <td>${escapeHtml(movement)}</td>
        <td>${escapeHtml(event.descriptor || "—")}</td>
      </tr>`;
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

  function render() {
    const now = new Date();
    const predictions = crossings.map((crossing) => ({ crossing, prediction: predict(crossing, now) }));
    const primary = predictions.find(({ crossing }) => crossing.primary);
    const viaWhyke = primary.crossing.baselineDriveSeconds + primary.prediction.waitSeconds;
    const viaA27 = 690;
    const useWhyke = viaWhyke <= viaA27;
    const saving = Math.abs(viaWhyke - viaA27);

    routeAdvice.innerHTML = `
      <p class="crossing-eyebrow">Best route into town</p>
      <h2>${useWhyke ? "Turn towards Whyke Road" : "Take the A27"}</h2>
      <p>
        ${useWhyke
          ? "The crossing route is currently estimated to be quicker."
          : "The predicted barrier wait makes the A27 quicker."}
        <strong>Estimated saving: ${formatDuration(saving)}.</strong>
      </p>
      <div class="crossing-route-comparison">
        <span>Whyke Road: ${formatDuration(viaWhyke)}</span>
        <span>A27: ${formatDuration(viaA27)}</span>
        <span>Road data: baseline</span>
      </div>`;

    crossingGrid.innerHTML = predictions.map(({ crossing, prediction }) => {
      const [label, statusClass] = stateDetails[prediction.state];
      const nextTrain = prediction.trains[0]
        ? `<span>Next train: ${escapeHtml(prediction.trains[0].destination)} · ${escapeHtml(prediction.trains[0].direction)}</span>`
        : "";
      return `
        <article class="crossing-card${crossing.primary ? " crossing-card--primary" : ""}">
          <h3>${escapeHtml(crossing.name)}</h3>
          ${crossing.primary ? '<span class="crossing-primary-tag">Closest to home</span>' : ""}
          <p class="crossing-type">${escapeHtml(crossing.type)}</p>
          <span class="crossing-status ${statusClass}">${label}</span>
          <p class="crossing-prediction-reason">${escapeHtml(prediction.reason)}</p>
          <div class="crossing-prediction-meta">
            <span>${escapeHtml(prediction.eventLabel)}: <strong>${formatTime(prediction.eventAt)}</strong></span>
            <span>Confidence: demonstration</span>
            ${nextTrain}
          </div>
        </article>`;
    }).join("");

    lastUpdated.textContent = `Updated ${formatTime(now)}`;
  }

  crossings.forEach((crossing) => {
    observationSelect.add(new Option(crossing.name, crossing.id, false, crossing.primary));
  });

  refreshButton.addEventListener("click", render);

  observationForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const submitter = event.submitter;
    if (!submitter?.value) return;

    const crossing = crossings.find(({ id }) => id === observationSelect.value);
    const observation = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
      crossingId: observationSelect.value,
      state: submitter.value,
      observedAt: new Date().toISOString(),
      note: observationNote.value.trim().slice(0, 300)
    };
    const observations = [observation, ...readObservations()].slice(0, 100);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(observations));
    observationNote.value = "";
    observationResult.textContent = `${submitter.textContent} recorded for ${crossing?.name || "the crossing"}.`;
    renderObservationCount();
  });

  renderObservationCount();
  render();
  loadFeedStatus();
  window.setInterval(render, 30000);
  window.setInterval(loadFeedStatus, 10000);
})();
