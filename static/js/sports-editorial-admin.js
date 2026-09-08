document.querySelectorAll("[data-confirm-button]").forEach((button) => {
  button.addEventListener("click", (event) => {
    if (!window.confirm(button.dataset.confirmButton)) event.preventDefault();
  });
});
