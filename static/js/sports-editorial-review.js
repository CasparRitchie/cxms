(() => {
  document.querySelectorAll("[data-review-block]").forEach((block) => {
    const editor = block.querySelector("[data-review-editor]");
    const input = block.querySelector("[data-review-input]");
    const sync = () => { input.value = editor.innerHTML; };
    editor.addEventListener("input", sync);
    editor.addEventListener("paste", (event) => {
      event.preventDefault();
      document.execCommand("insertText", false, event.clipboardData.getData("text/plain"));
      sync();
    });
    block.querySelectorAll("[data-review-format]").forEach((button) => button.addEventListener("mousedown", (event) => {
      event.preventDefault();
      editor.focus();
      document.execCommand(button.dataset.reviewFormat, false);
      sync();
    }));
  });
})();
