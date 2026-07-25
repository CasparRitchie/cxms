(() => {
  const form = document.querySelector("[data-edit-lock-form]");
  if (!form) return;
  const token = form.elements.lock_token?.value;
  const timeoutMs = Number(form.dataset.lockTimeout || 900) * 1000;
  const heartbeatUrl = form.dataset.lockHeartbeatUrl;
  let lastHeartbeat = Date.now();
  let expiresAt = Date.now() + timeoutMs;
  let lost = false;
  let warning;

  const setReadOnly = (message) => {
    if (lost) return;
    lost = true;
    form.querySelectorAll("button[type='submit'], input, textarea, select").forEach((control) => {
      if (control.type !== "hidden") control.disabled = true;
    });
    form.querySelectorAll("[contenteditable='true']").forEach((editor) => { editor.contentEditable = "false"; });
    const alert = document.createElement("section");
    alert.className = "sew-lock-warning";
    alert.setAttribute("role", "alert");
    alert.textContent = `${message} Your unsaved text remains visible in this browser but cannot overwrite the current saved version.`;
    form.before(alert);
  };

  const heartbeat = async () => {
    if (lost || !token || Date.now() - lastHeartbeat < 60000) return;
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
      expiresAt = Date.parse(payload.lock.expires_at);
      warning?.remove();
      warning = null;
    } catch (_error) {
      // Connectivity may recover; the server remains authoritative on save.
    }
  };

  ["input", "change", "pointerdown", "keydown"].forEach((name) => {
    form.addEventListener(name, (event) => {
      if (name === "keydown" && event.key === "Tab") return;
      heartbeat();
    });
  });
  setInterval(() => {
    const remaining = expiresAt - Date.now();
    if (remaining <= 0) {
      setReadOnly("Your editing lock has expired.");
    } else if (remaining <= 120000 && !warning) {
      warning = document.createElement("p");
      warning.className = "sew-lock-expiry-warning";
      warning.setAttribute("role", "status");
      warning.textContent = "Your editing lock will expire soon. Interact with the sheet to keep editing.";
      form.before(warning);
    }
  }, 30000);
})();
