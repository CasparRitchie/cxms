(() => {
  const form = document.querySelector("[data-edit-lock-form]");
  if (!form) return;

  const token = form.elements.lock_token?.value;
  const heartbeatUrl = form.dataset.lockHeartbeatUrl;
  const releaseUrl = form.dataset.lockReleaseUrl;
  const closeUrl = form.dataset.closeUrl;
  const closeDialog = form.querySelector("[data-close-dialog]");
  const autosaveStatus = form.querySelector("[data-autosave-status]");
  const timeoutMs = Number(form.dataset.lockTimeout || 3600) * 1000;
  const warningAfterMs = 45 * 60 * 1000;
  let lastHeartbeat = 0;
  let lastActivity = 0;
  let expiresAt = Date.now() + timeoutMs;
  let lost = false;
  let dirty = false;
  let submitting = false;
  let releaseRequested = false;
  let expiryWarning;
  let autosaveTimer;
  let autosaveController;
  let autosaveRunning = false;
  let autosaveAgain = false;
  let changeRevision = 0;

  const setAutosaveStatus = (message, state = "") => {
    if (!autosaveStatus) return;
    autosaveStatus.textContent = message;
    autosaveStatus.dataset.state = state;
  };

  const setReadOnly = (message) => {
    if (lost) return;
    lost = true;
    clearTimeout(autosaveTimer);
    autosaveController?.abort();
    setAutosaveStatus("Editing lock lost — changes not saved", "error");
    form.querySelectorAll("button[type='submit'], input, textarea, select").forEach((control) => {
      if (control.type !== "hidden") control.disabled = true;
    });
    form.querySelectorAll("[contenteditable='true']").forEach((editor) => { editor.contentEditable = "false"; });
    const alert = document.createElement("section");
    alert.className = "sew-lock-warning";
    alert.setAttribute("role", "alert");
    alert.append(document.createTextNode(
      `${message} Your unsaved text remains visible in this browser but cannot overwrite the current saved version. `
    ));
    const reload = document.createElement("a");
    reload.className = "sew-button sew-button--primary";
    reload.href = window.location.href;
    reload.textContent = "Reload saved sheet and continue";
    alert.appendChild(reload);
    form.before(alert);
  };

  const heartbeat = async () => {
    if (lost || !token || !heartbeatUrl || Date.now() - lastHeartbeat < 60000) return;
    lastHeartbeat = Date.now();
    try {
      const response = await fetch(heartbeatUrl, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({lock_token: token}),
      });
      const payload = await response.json();
      if (!response.ok) {
        setReadOnly(payload.error || "Your editing lock is no longer valid.");
        return;
      }
      expiresAt = Date.parse(payload.lock.expires_at) || Date.now() + timeoutMs;
      expiryWarning?.remove();
      expiryWarning = null;
    } catch (_error) {
      // Connectivity may recover; save and release remain server-authoritative.
    }
  };

  const scheduleAutosave = (delay = 5000) => {
    if (!form.hasAttribute("data-autosave-form") || lost || submitting || !dirty) return;
    clearTimeout(autosaveTimer);
    setAutosaveStatus("Unsaved changes", "pending");
    autosaveTimer = setTimeout(() => autosave(), delay);
  };

  const autosave = async () => {
    clearTimeout(autosaveTimer);
    if (lost || submitting || !dirty) return;
    if (autosaveRunning) {
      autosaveAgain = true;
      return;
    }
    autosaveRunning = true;
    autosaveAgain = false;
    const savingRevision = changeRevision;
    setAutosaveStatus("Saving…", "saving");
    const body = new FormData(form);
    body.set("autosave", "1");
    body.delete("action");
    body.delete("status");
    body.delete("save_action");
    autosaveController = new AbortController();
    try {
      const response = await fetch(form.action || window.location.href, {
        method: "POST",
        body,
        headers: {Accept: "application/json", "X-Requested-With": "XMLHttpRequest"},
        signal: autosaveController.signal,
      });
      const payload = await response.json().catch(() => ({}));
      if (response.status === 409) {
        setReadOnly(payload.error || "Your editing lock is no longer valid.");
        return;
      }
      if (!response.ok || !payload.ok) {
        setAutosaveStatus(payload.error || "Autosave failed — changes remain in this browser", "error");
        return;
      }
      if (changeRevision === savingRevision) {
        dirty = false;
        setAutosaveStatus("All changes saved", "saved");
      } else {
        setAutosaveStatus("Unsaved changes", "pending");
        autosaveAgain = true;
      }
      if (payload.lock?.expires_at) {
        expiresAt = Date.parse(payload.lock.expires_at) || expiresAt;
      }
    } catch (error) {
      if (error.name !== "AbortError") {
        setAutosaveStatus("Offline — changes not yet saved", "error");
      }
    } finally {
      autosaveRunning = false;
      autosaveController = null;
      if (autosaveAgain && !lost && !submitting) scheduleAutosave(800);
    }
  };

  const release = async (keepalive = false) => {
    if (!token || !releaseUrl || releaseRequested) return;
    releaseRequested = true;
    const body = new FormData();
    body.append("lock_token", token);
    if (keepalive && navigator.sendBeacon) {
      navigator.sendBeacon(releaseUrl, body);
      return;
    }
    try {
      await fetch(releaseUrl, {method: "POST", body, keepalive});
    } catch (_error) {
      // Supervisor force-unlock is the recovery path when delivery fails.
    }
  };

  const markDirty = (event) => {
    if (event.target.closest("[data-close-dialog]")) return;
    if (event.target.closest("[data-entity-results], [data-entity-suggestions], [data-link-review]")) return;
    dirty = true;
    changeRevision += 1;
    lastActivity = Date.now();
    heartbeat();
    scheduleAutosave();
  };
  form.addEventListener("input", markDirty);
  form.addEventListener("change", markDirty);
  form.addEventListener("pointerdown", () => {
    lastActivity = Date.now();
    heartbeat();
  });
  form.addEventListener("click", (event) => {
    if (event.target.closest("[data-toggle-accepted], [data-accept-all], [data-remove-review-block], [data-add-review-block], [data-remove-stat], [data-add-block], [data-remove-entity]")) {
      dirty = true;
      changeRevision += 1;
      lastActivity = Date.now();
      heartbeat();
      scheduleAutosave(1200);
    }
  });
  form.addEventListener("focusout", (event) => {
    if (!dirty || event.target.closest("[data-entity-results], [data-entity-suggestions]")) return;
    scheduleAutosave(800);
  });
  form.addEventListener("keydown", (event) => {
    if (event.key !== "Tab") {
      lastActivity = Date.now();
      heartbeat();
    }
  });
  form.addEventListener("submit", () => {
    submitting = true;
    dirty = false;
    clearTimeout(autosaveTimer);
    autosaveController?.abort();
  });

  window.addEventListener("beforeunload", (event) => {
    if (!dirty || submitting) return;
    event.preventDefault();
    event.returnValue = "";
  });
  window.addEventListener("pagehide", () => {
    if (!submitting) release(true);
  });

  form.querySelector("[data-close-editor]")?.addEventListener("click", async (event) => {
    event.preventDefault();
    if (dirty) {
      closeDialog?.showModal();
      return;
    }
    await release();
    window.location.assign(closeUrl);
  });
  closeDialog?.querySelector("[data-cancel-close]")?.addEventListener("click", () => closeDialog.close());
  closeDialog?.querySelector("[data-discard-close]")?.addEventListener("click", async () => {
    dirty = false;
    closeDialog.close();
    await release();
    window.location.assign(closeUrl);
  });
  closeDialog?.querySelector("[data-save-close]")?.addEventListener("click", () => {
    const action = form.querySelector("button[name='action'][value='draft']");
    let saveClose = form.querySelector("button[name='save_action'][value='close']");
    if (!saveClose) {
      saveClose = document.createElement("button");
      saveClose.type = "submit";
      saveClose.name = "save_action";
      saveClose.value = "close";
      saveClose.hidden = true;
      form.appendChild(saveClose);
    }
    if (action) {
      const marker = document.createElement("input");
      marker.type = "hidden";
      marker.name = "action";
      marker.value = "draft";
      form.appendChild(marker);
    }
    closeDialog.close();
    saveClose.click();
  });

  document.querySelectorAll("[data-date-picker]").forEach((picker) => {
    const display = picker.parentElement?.querySelector("input[type='text']");
    if (!display) return;
    picker.addEventListener("change", () => {
      if (!picker.value) return;
      const [year, month, day] = picker.value.split("-").map(Number);
      display.value = new Intl.DateTimeFormat("en-GB", {
        day: "2-digit", month: "short", year: "numeric", timeZone: "UTC",
      }).format(new Date(Date.UTC(year, month - 1, day))).replace(/ /g, "-");
      display.dispatchEvent(new Event("input", {bubbles: true}));
    });
  });

  setInterval(() => {
    const now = Date.now();
    if (lastActivity && now - lastActivity <= 65000) heartbeat();
    const remaining = expiresAt - now;
    if (remaining <= 0) {
      const timeoutMinutes = Math.round(timeoutMs / 60000);
      setReadOnly(`Your editing lock has expired after ${timeoutMinutes} minutes of inactivity.`);
    } else if (remaining <= timeoutMs - warningAfterMs && !expiryWarning) {
      expiryWarning = document.createElement("p");
      expiryWarning.className = "sew-lock-expiry-warning";
      expiryWarning.setAttribute("role", "status");
      expiryWarning.textContent = `You have been inactive for 45 minutes. Interact with the sheet to keep editing; otherwise the lock will be released after ${Math.round(timeoutMs / 60000)} minutes.`;
      form.before(expiryWarning);
    }
  }, 30000);
})();
