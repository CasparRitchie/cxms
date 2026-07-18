(() => {
  const STORAGE_KEY = "cxms-circuit-settings-v1";
  const exercises = [
    { id: "squats", name: "Squats", category: "Lower body", icon: "↕" },
    { id: "push-ups", name: "Push-ups", category: "Upper body", icon: "↔" },
    { id: "sit-ups", name: "Sit-ups", category: "Core", icon: "◒" },
    { id: "wall-sit", name: "Wall sit", category: "Lower body", icon: "▰" },
    { id: "lunges", name: "Lunges", category: "Lower body", icon: "⇆" },
    { id: "plank", name: "Plank", category: "Core", icon: "━" },
    { id: "burpees", name: "Burpees", category: "Cardio", icon: "⚡" },
    { id: "star-jumps", name: "Star jumps", category: "Cardio", icon: "✦" },
    { id: "dumbbell-curls", name: "Dumbbell curls", category: "Weights", icon: "◫" },
    { id: "shoulder-press", name: "Shoulder press", category: "Weights", icon: "↑" },
    { id: "stretching", name: "Stretching", category: "Mobility", icon: "⌁" }
  ];

  const defaultSelected = ["squats", "push-ups", "sit-ups", "wall-sit", "lunges", "plank"];
  let settings = loadSettings();
  let phases = [];
  let phaseIndex = 0;
  let phaseEndsAt = 0;
  let phaseStartedAt = 0;
  let timerId = null;
  let paused = false;
  let pausedRemainingMs = 0;
  let audioContext = null;
  let wakeLock = null;

  const $ = (id) => document.getElementById(id);
  const els = {
    builder: $("builder-view"), timer: $("timer-view"), complete: $("complete-view"),
    exerciseList: $("exercise-list"), work: $("work-duration"), rest: $("rest-duration"), prep: $("prep-duration"),
    voice: $("voice-toggle"), summaryStations: $("summary-stations"), summaryRounds: $("summary-rounds"),
    summaryIntervals: $("summary-intervals"), summaryDuration: $("summary-duration"), summaryNote: $("summary-note"),
    error: $("builder-error"), phaseLabel: $("phase-label"), roundLabel: $("round-label"),
    stationPosition: $("station-position"), currentStation: $("current-station"), timerDisplay: $("timer-display"),
    phaseProgress: $("phase-progress"), nextStation: $("next-station"), workoutProgress: $("workout-progress"),
    workoutProgressText: $("workout-progress-text"), pause: $("pause-workout"), completeSummary: $("complete-summary")
  };

  function loadSettings() {
    try {
      const stored = JSON.parse(localStorage.getItem(STORAGE_KEY));
      return { targetMinutes: 10, work: 40, rest: 20, prep: 10, voice: true, selected: defaultSelected, custom: [], ...stored };
    } catch (_) {
      return { targetMinutes: 10, work: 40, rest: 20, prep: 10, voice: true, selected: defaultSelected, custom: [] };
    }
  }

  function saveSettings() { localStorage.setItem(STORAGE_KEY, JSON.stringify(settings)); }
  function allExercises() { return [...exercises, ...settings.custom]; }
  function chosenExercises() { return allExercises().filter((exercise) => settings.selected.includes(exercise.id)); }
  function formatTime(seconds) { const value = Math.max(0, Math.ceil(seconds)); return `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`; }

  function renderExercises() {
    els.exerciseList.innerHTML = allExercises().map((exercise) => {
      const selected = settings.selected.includes(exercise.id);
      return `<label class="exercise-item${selected ? " selected" : ""}">
        <input type="checkbox" value="${exercise.id}" ${selected ? "checked" : ""}>
        <span class="exercise-icon">${exercise.icon || "+"}</span>
        <span class="exercise-copy"><strong>${escapeHtml(exercise.name)}</strong><small>${escapeHtml(exercise.category || "Custom")}</small></span>
      </label>`;
    }).join("");

    els.exerciseList.querySelectorAll("input").forEach((input) => {
      input.addEventListener("change", () => {
        settings.selected = input.checked ? [...settings.selected, input.value] : settings.selected.filter((id) => id !== input.value);
        input.closest(".exercise-item").classList.toggle("selected", input.checked);
        saveSettings(); updateSummary();
      });
    });
  }

  function calculatePlan() {
    const count = chosenExercises().length;
    if (!count) return { rounds: 0, duration: 0 };
    const perRound = count * settings.work + Math.max(0, count - 1) * settings.rest;
    const targetSeconds = settings.targetMinutes * 60;
    const rounds = Math.max(1, Math.round((targetSeconds - settings.prep) / perRound));
    const duration = settings.prep + rounds * perRound + Math.max(0, rounds - 1) * settings.rest;
    return { rounds, duration };
  }

  function updateSummary() {
    const plan = calculatePlan();
    els.summaryStations.textContent = chosenExercises().length;
    els.summaryRounds.textContent = plan.rounds;
    els.summaryIntervals.textContent = `${settings.work}s / ${settings.rest}s`;
    els.summaryDuration.textContent = formatTime(plan.duration);
    const difference = plan.duration - settings.targetMinutes * 60;
    els.summaryNote.textContent = plan.rounds ? `Uses complete rounds and finishes ${Math.abs(difference)} seconds ${difference >= 0 ? "over" : "under"} your target.` : "Choose at least one workstation to begin.";
  }

  function buildPhases() {
    const selected = chosenExercises();
    const { rounds } = calculatePlan();
    const result = [{ type: "prep", duration: settings.prep, name: "Get ready", round: 1, station: 0 }];
    for (let round = 1; round <= rounds; round += 1) {
      selected.forEach((exercise, index) => {
        result.push({ type: "work", duration: settings.work, name: exercise.name, round, station: index + 1 });
        const lastOverall = round === rounds && index === selected.length - 1;
        if (!lastOverall) result.push({ type: "rest", duration: settings.rest, name: "Rest", round, station: index + 1 });
      });
    }
    return result;
  }

  function startWorkout() {
    if (!chosenExercises().length) { els.error.textContent = "Choose at least one workstation."; return; }
    els.error.textContent = ""; phases = buildPhases(); phaseIndex = 0; paused = false;
    initAudio(); requestWakeLock();
    els.builder.hidden = true; els.complete.hidden = true; els.timer.hidden = false;
    beginPhase();
  }

  function beginPhase() {
    clearInterval(timerId);
    if (phaseIndex >= phases.length) { finishWorkout(); return; }
    const phase = phases[phaseIndex];
    phaseStartedAt = Date.now(); phaseEndsAt = phaseStartedAt + phase.duration * 1000;
    renderPhase(phase); playTone(phase.type === "work" ? 760 : phase.type === "rest" ? 480 : 620, .12);
    if (settings.voice) speak(phase.type === "work" ? phase.name : phase.type === "rest" ? `Rest. Next, ${findNextWorkName()}` : "Get ready");
    tick(); timerId = setInterval(tick, 200);
  }

  function tick() {
    const phase = phases[phaseIndex];
    const remainingMs = Math.max(0, phaseEndsAt - Date.now());
    const remaining = Math.ceil(remainingMs / 1000);
    els.timerDisplay.textContent = formatTime(remaining);
    els.phaseProgress.style.width = `${Math.min(100, ((phase.duration * 1000 - remainingMs) / (phase.duration * 1000)) * 100)}%`;
    updateOverallProgress();
    if (remaining > 0 && remaining <= 3 && !tick.lastBeep?.includes(`${phaseIndex}-${remaining}`)) {
      tick.lastBeep = `${tick.lastBeep || ""},${phaseIndex}-${remaining}`; playTone(900, .06);
    }
    if (remainingMs <= 0) { phaseIndex += 1; beginPhase(); }
  }

  function renderPhase(phase) {
    const selected = chosenExercises(); const rounds = calculatePlan().rounds;
    els.timer.dataset.phase = phase.type;
    els.phaseLabel.textContent = phase.type === "work" ? "WORK" : phase.type === "rest" ? "REST" : "GET READY";
    els.roundLabel.textContent = `Round ${Math.min(phase.round, rounds)} of ${rounds}`;
    els.stationPosition.textContent = phase.type === "prep" ? `${selected.length} stations` : `Station ${Math.min(phase.station, selected.length)} of ${selected.length}`;
    els.currentStation.textContent = phase.name;
    els.nextStation.textContent = `Next: ${findNextWorkName()}`;
  }

  function findNextWorkName() {
    for (let i = phaseIndex + 1; i < phases.length; i += 1) if (phases[i].type === "work") return phases[i].name;
    return "Finish";
  }

  function updateOverallProgress() {
    const elapsedBefore = phases.slice(0, phaseIndex).reduce((sum, phase) => sum + phase.duration, 0);
    const current = phases[phaseIndex];
    const elapsedCurrent = current ? Math.min(current.duration, (Date.now() - phaseStartedAt) / 1000) : 0;
    const total = phases.reduce((sum, phase) => sum + phase.duration, 0);
    const percentage = total ? Math.min(100, ((elapsedBefore + elapsedCurrent) / total) * 100) : 0;
    els.workoutProgress.style.width = `${percentage}%`; els.workoutProgressText.textContent = `${Math.round(percentage)}%`;
  }

  function togglePause() {
    if (!paused) {
      paused = true; pausedRemainingMs = Math.max(0, phaseEndsAt - Date.now()); clearInterval(timerId); els.pause.textContent = "Resume";
      if (window.speechSynthesis) window.speechSynthesis.cancel();
    } else {
      paused = false; phaseStartedAt = Date.now() - (phases[phaseIndex].duration * 1000 - pausedRemainingMs); phaseEndsAt = Date.now() + pausedRemainingMs;
      els.pause.textContent = "Pause"; tick(); timerId = setInterval(tick, 200);
    }
  }

  function finishWorkout() {
    clearInterval(timerId); releaseWakeLock(); playTone(980, .35); if (settings.voice) speak("Workout complete. Nice work!");
    els.timer.hidden = true; els.complete.hidden = false;
    const plan = calculatePlan(); els.completeSummary.textContent = `You completed ${plan.rounds} rounds, ${chosenExercises().length} stations and ${formatTime(plan.duration)} of circuit training.`;
  }

  function endWorkout() { clearInterval(timerId); releaseWakeLock(); els.timer.hidden = true; els.builder.hidden = false; updateSummary(); }
  function initAudio() { try { audioContext = audioContext || new (window.AudioContext || window.webkitAudioContext)(); if (audioContext.state === "suspended") audioContext.resume(); } catch (_) {} }
  function playTone(frequency, duration) { if (!audioContext) return; const oscillator = audioContext.createOscillator(); const gain = audioContext.createGain(); oscillator.frequency.value = frequency; gain.gain.setValueAtTime(.12, audioContext.currentTime); gain.gain.exponentialRampToValueAtTime(.001, audioContext.currentTime + duration); oscillator.connect(gain); gain.connect(audioContext.destination); oscillator.start(); oscillator.stop(audioContext.currentTime + duration); }
  function speak(text) { if (!("speechSynthesis" in window)) return; window.speechSynthesis.cancel(); const utterance = new SpeechSynthesisUtterance(text); utterance.rate = 1.05; window.speechSynthesis.speak(utterance); }
  async function requestWakeLock() { try { if ("wakeLock" in navigator) wakeLock = await navigator.wakeLock.request("screen"); } catch (_) {} }
  async function releaseWakeLock() { try { if (wakeLock) await wakeLock.release(); wakeLock = null; } catch (_) {} }
  function escapeHtml(value) { return value.replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char])); }

  document.querySelectorAll("[data-duration]").forEach((button) => button.addEventListener("click", () => {
    document.querySelectorAll("[data-duration]").forEach((item) => item.classList.remove("active")); button.classList.add("active"); settings.targetMinutes = Number(button.dataset.duration); saveSettings(); updateSummary();
  }));
  [els.work, els.rest, els.prep].forEach((control) => control.addEventListener("change", () => { settings.work = Number(els.work.value); settings.rest = Number(els.rest.value); settings.prep = Number(els.prep.value); saveSettings(); updateSummary(); }));
  els.voice.addEventListener("change", () => { settings.voice = els.voice.checked; saveSettings(); });
  $("custom-exercise-form").addEventListener("submit", (event) => { event.preventDefault(); const input = $("custom-exercise"); const name = input.value.trim(); if (!name) return; const item = { id: `custom-${Date.now()}`, name, category: "Custom", icon: "+" }; settings.custom.push(item); settings.selected.push(item.id); input.value = ""; saveSettings(); renderExercises(); updateSummary(); });
  $("select-all").addEventListener("click", () => { const everySelected = allExercises().every((item) => settings.selected.includes(item.id)); settings.selected = everySelected ? [] : allExercises().map((item) => item.id); saveSettings(); renderExercises(); updateSummary(); });
  $("start-workout").addEventListener("click", startWorkout);
  els.pause.addEventListener("click", togglePause);
  $("skip-phase").addEventListener("click", () => { if (paused) togglePause(); phaseIndex += 1; beginPhase(); });
  $("end-workout").addEventListener("click", endWorkout);
  $("repeat-workout").addEventListener("click", startWorkout);
  $("edit-workout").addEventListener("click", () => { els.complete.hidden = true; els.builder.hidden = false; updateSummary(); });

  settings.selected = settings.selected.filter((id) => allExercises().some((item) => item.id === id));
  document.querySelectorAll("[data-duration]").forEach((button) => button.classList.toggle("active", Number(button.dataset.duration) === settings.targetMinutes));
  els.work.value = String(settings.work); els.rest.value = String(settings.rest); els.prep.value = String(settings.prep); els.voice.checked = settings.voice;
  renderExercises(); updateSummary();
})();
