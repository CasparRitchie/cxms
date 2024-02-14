document.addEventListener('DOMContentLoaded', function () {
  let currentIdx = 0;
  const items = document.querySelectorAll('.carousel-item');
  const total = items.length;

  function showItem(idx) {
      items.forEach((item, i) => {
          if (i === idx) {
              item.classList.add('active');
          } else {
              item.classList.remove('active');
          }
      });
  }

  document.getElementById('prev').addEventListener('click', () => {
      currentIdx = (currentIdx - 1 + total) % total;
      showItem(currentIdx);
  });

  document.getElementById('next').addEventListener('click', () => {
      currentIdx = (currentIdx + 1) % total;
      showItem(currentIdx);
  });

  showItem(currentIdx); // Initialize carousel to show the first item
});
