(() => {
  const help = {
    category: ["Which category?", "Choose the closest match. If you are unsure, choose ‘Not sure’ so it is easy to review later."],
    "amount-sale": ["Gross sale amount", "Enter the full invoice value before CIS is deducted. Example: for a £1,000 invoice where £200 CIS is held back, enter £1,000."],
    "amount-purchase": ["Amount paid", "Enter the total business cost shown on the receipt or supplier invoice."],
    cis: ["CIS deducted", "Enter the amount the contractor held back under CIS. Example: if the invoice was £1,000 and you received £800, enter £200."],
    received: ["Amount received", "Enter what reached your bank or what you received in cash after any CIS deduction."],
  };
  const dialog = document.querySelector(".tl-help-dialog");
  if (!dialog) return;
  let trigger = null;
  document.querySelectorAll(".tl-help").forEach((button) => button.addEventListener("click", () => {
    trigger = button;
    const content = help[button.dataset.help];
    dialog.querySelector("h2").textContent = content[0];
    dialog.querySelector("p").textContent = content[1];
    button.setAttribute("aria-expanded", "true");
    dialog.showModal();
  }));
  const close = () => { dialog.close(); if (trigger) { trigger.setAttribute("aria-expanded", "false"); trigger.focus(); } };
  dialog.querySelector(".tl-help-dialog__close").addEventListener("click", close);
  dialog.addEventListener("click", (event) => { if (event.target === dialog) close(); });
  dialog.addEventListener("close", () => { if (trigger) trigger.setAttribute("aria-expanded", "false"); });
})();
