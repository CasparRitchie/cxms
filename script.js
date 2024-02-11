document.addEventListener('DOMContentLoaded', function () {
    let currentIdx = 0;
    const items = document.querySelectorAll('.carousel-item');
    const total = items.length;

    function showItem(idx) {
        items.forEach((item, i) => {
            item.style.display = i === idx ? 'block' : 'none';
        });
    }

    document.getElementById('prev').addEventListener('click', () => {
        if (currentIdx > 0) {
            currentIdx -= 1;
        } else {
            currentIdx = total - 1;
        }
        showItem(currentIdx);
    });

    document.getElementById('next').addEventListener('click', () => {
        if (currentIdx < total - 1) {
            currentIdx += 1;
        } else {
            currentIdx = 0;
        }
        showItem(currentIdx);
    });

    showItem(currentIdx); // Initialize carousel to show the first item
});
