document.addEventListener('DOMContentLoaded', function () {
  let currentIdx = 0;
  const items = document.querySelectorAll('.carousel-item');
  const total = items.length;

  let lastScrollY = window.scrollY;
  const siteHeader = document.querySelector(".site-header");

  window.addEventListener("scroll", () => {
    if (!siteHeader) return;

    const currentScrollY = window.scrollY;
    const scrollingUp = currentScrollY < lastScrollY;
    const scrollingDown = currentScrollY > lastScrollY;

    if (currentScrollY < 20) {
      siteHeader.classList.add("is-visible");
    } else if (scrollingUp) {
      siteHeader.classList.add("is-visible");
    } else if (scrollingDown) {
      siteHeader.classList.remove("is-visible");
    }

    lastScrollY = currentScrollY;
  });

  function showItem(idx) {
    items.forEach((item, i) => {
      item.style.display = i === idx ? 'block' : 'none';
    });
  }

  const prevButton = document.getElementById('prev');
  if (prevButton) {
    prevButton.addEventListener('click', () => {
      currentIdx = currentIdx > 0 ? currentIdx - 1 : total - 1;
      showItem(currentIdx);
    });
  }

  const nextButton = document.getElementById('next');
  if (nextButton) {
    nextButton.addEventListener('click', () => {
      currentIdx = currentIdx < total - 1 ? currentIdx + 1 : 0;
      showItem(currentIdx);
    });
  }

  showItem(currentIdx);
});
