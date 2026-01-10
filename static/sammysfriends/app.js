let cursor = null;
let loading = false;

async function loadMore() {
  if (loading) return;
  loading = true;

  const res = await fetch("/api/sammy/images", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ limit: 40, cursor }),
  });

  const data = await res.json();

  if (!res.ok || data.error) {
    console.error(data);
    document.getElementById("gallery").innerText = "Failed to load images.";
    loading = false;
    return;
  }

  const gallery = document.getElementById("gallery");
  data.images.forEach((img) => {
    const el = document.createElement("img");
    el.src = img.url;
    el.alt = img.id;
    el.loading = "lazy";
    el.style.width = "140px";
    el.style.margin = "8px";
    el.style.borderRadius = "10px";
    gallery.appendChild(el);
  });

  cursor = data.cursor;
  loading = false;

  const btn = document.getElementById("load-more");
  btn.style.display = cursor ? "block" : "none";
}

document.addEventListener("DOMContentLoaded", () => {
  loadMore();
  document.getElementById("load-more").addEventListener("click", loadMore);
});
