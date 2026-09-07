(() => {
  const preview = document.querySelector("[data-publication-preview]");
  const status = document.querySelector("[data-preview-page-status]");
  if (!preview || !status) return;

  let resizeTimer;
  const renderPageGuides = () => {
    preview.querySelectorAll("[data-preview-page-guide]").forEach((guide) => guide.remove());
    preview.style.removeProperty("min-height");
    if (preview.getBoundingClientRect().width < 700) {
      status.classList.remove("is-warning");
      status.textContent = "Page-length estimate is available at tablet or desktop width.";
      return;
    }
    const pageHeight = preview.getBoundingClientRect().width * (297 / 210);
    const pageCount = Math.max(1, Math.ceil(preview.scrollHeight / pageHeight));
    for (let page = 1; page < pageCount; page += 1) {
      const guide = document.createElement("div");
      guide.className = "sew-preview-page-guide";
      guide.dataset.previewPageGuide = "";
      guide.style.top = `${pageHeight * page}px`;
      guide.innerHTML = `<span>Page ${page + 1}</span>`;
      preview.appendChild(guide);
    }
    preview.style.minHeight = `${pageCount * pageHeight}px`;
    status.classList.toggle("is-warning", pageCount > 2);
    status.textContent = pageCount > 2
      ? `Estimated length: ${pageCount} pages. Consider shortening this stat sheet.`
      : `Estimated length: ${pageCount} page${pageCount === 1 ? "" : "s"}.`;
  };

  window.addEventListener("load", renderPageGuides);
  window.addEventListener("resize", () => {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(renderPageGuides, 120);
  });
})();
