let cursor = null;
let loading = false;

let selectedImg = new Image();
selectedImg.crossOrigin = "anonymous";

const canvas = document.getElementById("previewCanvas");
const ctx = canvas.getContext("2d", { willReadFrequently: true });

const scarySlider = document.getElementById("scarySlider");
const darkSlider = document.getElementById("darkSlider");
const glitchSlider = document.getElementById("glitchSlider");

function clamp01(x) { return Math.max(0, Math.min(1, x)); }

function applyTransforms() {
  if (!selectedImg.complete || !selectedImg.naturalWidth) return;

  canvas.style.display = "block";

  // Fit image into canvas
  const cw = canvas.width, ch = canvas.height;
  ctx.clearRect(0, 0, cw, ch);

  // draw centered, contain
  const iw = selectedImg.naturalWidth;
  const ih = selectedImg.naturalHeight;
  const scale = Math.min(cw / iw, ch / ih);
  const dw = Math.floor(iw * scale);
  const dh = Math.floor(ih * scale);
  const dx = Math.floor((cw - dw) / 2);
  const dy = Math.floor((ch - dh) / 2);

  ctx.drawImage(selectedImg, dx, dy, dw, dh);

  const imgData = ctx.getImageData(0, 0, cw, ch);
  const d = imgData.data;

  // sliders 0..1
  const scary = (parseInt(scarySlider.value, 10) / 100); // 0 friendly -> 1 scary
  const dark  = (parseInt(darkSlider.value, 10) / 100);  // 0 light -> 1 dark
  const glitch = (parseInt(glitchSlider.value, 10) / 100);

  // map: friendly = brighten + warm + soften
  // scary = darken + contrast + slight red + vignette + noise
  const brightnessAdj = (0.20 * (0.5 - dark)) + (0.15 * (0.5 - scary)); // +/- small
  const contrastAdj   = 1.0 + (0.9 * (scary - 0.5));                   // scary increases contrast
  const warmthAdj     = (0.20 * (0.5 - scary));                        // friendly warmer

  // per-pixel
  for (let i = 0; i < d.length; i += 4) {
    let r = d[i] / 255;
    let g = d[i+1] / 255;
    let b = d[i+2] / 255;

    // brightness
    r = clamp01(r + brightnessAdj);
    g = clamp01(g + brightnessAdj);
    b = clamp01(b + brightnessAdj);

    // contrast around mid grey
    r = clamp01((r - 0.5) * contrastAdj + 0.5);
    g = clamp01((g - 0.5) * contrastAdj + 0.5);
    b = clamp01((b - 0.5) * contrastAdj + 0.5);

    // warmth (friendly)
    r = clamp01(r + warmthAdj);
    b = clamp01(b - warmthAdj * 0.6);

    // scary red bias (subtle)
    r = clamp01(r + 0.08 * (scary));

    d[i]   = Math.round(r * 255);
    d[i+1] = Math.round(g * 255);
    d[i+2] = Math.round(b * 255);
  }

  ctx.putImageData(imgData, 0, 0);

  // vignette (scary/dark)
  const vignette = clamp01(0.6 * scary + 0.7 * dark);
  if (vignette > 0.01) {
    const grd = ctx.createRadialGradient(cw/2, ch/2, Math.min(cw,ch)*0.2, cw/2, ch/2, Math.min(cw,ch)*0.7);
    grd.addColorStop(0, `rgba(0,0,0,0)`);
    grd.addColorStop(1, `rgba(0,0,0,${0.55*vignette})`);
    ctx.fillStyle = grd;
    ctx.fillRect(0,0,cw,ch);
  }

  // glitch overlay (RGB split + scanlines)
  if (glitch > 0.01) {
    // scanlines
    ctx.fillStyle = `rgba(0,0,0,${0.10*glitch})`;
    for (let y=0; y<ch; y+=3) ctx.fillRect(0, y, cw, 1);

    // RGB split by re-drawing image slightly offset
    const off = Math.floor(8 * glitch);
    ctx.globalCompositeOperation = "screen";
    ctx.drawImage(canvas, -off, 0);
    ctx.drawImage(canvas, off, 0);
    ctx.globalCompositeOperation = "source-over";
  }
}

function attachPreviewToImage(url) {
  selectedImg.onload = applyTransforms;
  selectedImg.src = url;
}

// --- existing paging fetch, now supports filter ---
let scaryFilter = { min: 0.0, max: 1.0 };

async function loadMore(reset=false) {
  if (loading) return;
  loading = true;

  if (reset) {
    cursor = null;
    document.getElementById("gallery").innerHTML = "";
  }

  const res = await fetch("/api/sammy/images", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      limit: 40,
      cursor,
      scary_min: scaryFilter.min,
      scary_max: scaryFilter.max,
    }),
  });

  const data = await res.json();
  if (!res.ok || data.error) {
    console.error(data);
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
    el.style.cursor = "pointer";
    el.title = `Scary: ${(img.scary_score ?? 0.5).toFixed(2)}`;
    el.addEventListener("click", () => attachPreviewToImage(img.url));
    gallery.appendChild(el);
  });

  cursor = data.cursor;
  loading = false;

  const btn = document.getElementById("load-more");
  btn.style.display = cursor ? "block" : "none";
}

document.addEventListener("DOMContentLoaded", () => {
  // transform sliders
  [scarySlider, darkSlider, glitchSlider].forEach(s => s.addEventListener("input", applyTransforms));

  // filter slider: use scarySlider too? better to add a separate filter slider (recommended)
  // For now you can keep filter separate (see note below).

  loadMore(false);
  document.getElementById("load-more").addEventListener("click", () => loadMore(false));
});
