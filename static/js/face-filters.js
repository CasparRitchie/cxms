const MEDIAPIPE_VERSION = "0.10.22-rc.20250304";
const MEDIAPIPE_ROOT = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${MEDIAPIPE_VERSION}`;
const FACE_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";
const OUTER_LIP_LANDMARKS = [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 375, 321, 405, 314, 17, 84, 181, 91, 146];

const app = document.querySelector("[data-face-filter-app]");

if (app) {
  const ui = {
    video: app.querySelector("[data-camera]"),
    canvas: app.querySelector("[data-output]"),
    placeholder: app.querySelector("[data-placeholder]"),
    start: app.querySelector("[data-start-camera]"),
    stop: app.querySelector("[data-stop-camera]"),
    flip: app.querySelector("[data-flip-camera]"),
    record: app.querySelector("[data-record]"),
    status: app.querySelector("[data-status]"),
    liveBadge: app.querySelector("[data-live-badge]"),
    timer: app.querySelector("[data-timer]"),
    filterName: app.querySelector("[data-filter-name]"),
    filterList: app.querySelector("[data-filter-list]"),
    result: app.querySelector("[data-result]"),
    playback: app.querySelector("[data-playback]"),
    download: app.querySelector("[data-download]"),
    discard: app.querySelector("[data-discard]"),
  };
  const context = ui.canvas.getContext("2d", { alpha: false, desynchronized: true });
  const state = {
    stream: null, landmarker: null, landmarks: null, animationId: 0,
    facingMode: "user", activeFilter: "none", lastVideoTime: -1,
    recorder: null, chunks: [], resultUrl: "", startedAt: 0, timerId: 0,
  };

  const FILTERS = {
    none: { label: "No filter", draw() {} },
    "big-eyes": { label: "Big eyes", draw: drawBigEyes },
    "wide-face": { label: "Wide face", draw: drawWideFace },
    "mega-mouth": { label: "Mega mouth", draw: drawMegaMouth },
    "tiny-mouth": { label: "Tiny mouth", draw: drawTinyMouth },
    wobble: { label: "Wobble", draw: drawWobble },
    "space-ears": { label: "Space ears", draw: drawSpaceEars },
    "hero-mask": { label: "Hero mask", draw: drawHeroMask },
    "party-hat": { label: "Party hat", draw: drawPartyHat },
  };

  ui.start.addEventListener("click", startCamera);
  ui.stop.addEventListener("click", stopCamera);
  ui.flip.addEventListener("click", flipCamera);
  ui.record.addEventListener("click", toggleRecording);
  ui.discard.addEventListener("click", discardRecording);
  ui.filterList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-filter]");
    if (!button) return;
    state.activeFilter = button.dataset.filter;
    ui.filterName.textContent = FILTERS[state.activeFilter].label;
    ui.filterList.querySelectorAll("[data-filter]").forEach((item) => {
      const selected = item === button;
      item.classList.toggle("is-active", selected);
      item.setAttribute("aria-selected", String(selected));
    });
  });
  window.addEventListener("pagehide", stopCamera);

  function setStatus(message) { ui.status.textContent = message; }

  async function startCamera() {
    if (state.stream) {
      await resumeCameraFromTap();
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      setStatus("This browser cannot open the camera. Try a recent version of Safari, Chrome, Edge, or Firefox.");
      return;
    }
    ui.start.disabled = true;
    setStatus("Waiting for camera permission…");
    try {
      state.stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: state.facingMode, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      ui.video.srcObject = state.stream;
      ui.video.muted = true;
      ui.video.setAttribute("playsinline", "");
      try {
        await ui.video.play();
      } catch (playbackError) {
        console.warn("Safari deferred camera playback", playbackError);
        ui.start.disabled = false;
        ui.start.textContent = "Tap to show camera";
        setStatus("Safari needs one more tap to show the camera.");
        return;
      }
      finishCameraStart();
    } catch (error) {
      state.stream?.getTracks().forEach((track) => track.stop());
      state.stream = null;
      ui.video.srcObject = null;
      ui.start.disabled = false;
      ui.start.textContent = "Start camera";
      if (error.name === "NotAllowedError") setStatus("Camera access was blocked. Allow camera access in your browser settings and try again.");
      else if (error.name === "NotFoundError") setStatus("No camera was found on this device.");
      else setStatus("The camera could not start. Close other camera apps and try again.");
    }
  }

  async function resumeCameraFromTap() {
    ui.start.disabled = true;
    setStatus("Starting the camera…");
    try {
      await ui.video.play();
      finishCameraStart();
    } catch (error) {
      console.warn("Camera playback still blocked", error);
      ui.start.disabled = false;
      ui.start.textContent = "Try camera again";
      setStatus("Safari is still blocking playback. Check Camera permission in Settings → Safari, then tap again.");
    }
  }

  function finishCameraStart() {
    resizeCanvas();
    ui.placeholder.hidden = true;
    ui.start.textContent = "Start camera";
    ui.record.disabled = !(window.MediaRecorder && ui.canvas.captureStream);
    ui.stop.disabled = false;
    ui.flip.disabled = false;
    setStatus("Camera ready · loading face tracking…");
    cancelAnimationFrame(state.animationId);
    renderFrame();
    initialiseLandmarker();
  }

  async function initialiseLandmarker() {
    if (state.landmarker) return;
    try {
      const vision = await import(`${MEDIAPIPE_ROOT}/vision_bundle.mjs`);
      const files = await vision.FilesetResolver.forVisionTasks(`${MEDIAPIPE_ROOT}/wasm`);
      state.landmarker = await vision.FaceLandmarker.createFromOptions(files, {
        baseOptions: { modelAssetPath: FACE_MODEL_URL, delegate: "GPU" },
        runningMode: "VIDEO", numFaces: 1,
        minFaceDetectionConfidence: 0.55,
        minFacePresenceConfidence: 0.55,
        minTrackingConfidence: 0.5,
      });
      setStatus("Face tracking ready · choose a filter");
    } catch (error) {
      console.warn("Face tracking unavailable", error);
      setStatus("Face tracking did not load. You can still record a normal video.");
    }
  }

  function resizeCanvas() {
    ui.canvas.width = ui.video.videoWidth || 1280;
    ui.canvas.height = ui.video.videoHeight || 720;
  }

  function renderFrame(now = performance.now()) {
    if (!state.stream) return;
    const { width, height } = ui.canvas;
    context.save();
    if (state.facingMode === "user") {
      context.translate(width, 0);
      context.scale(-1, 1);
    }
    context.drawImage(ui.video, 0, 0, width, height);
    context.restore();

    if (state.landmarker && ui.video.currentTime !== state.lastVideoTime) {
      state.lastVideoTime = ui.video.currentTime;
      try {
        const result = state.landmarker.detectForVideo(ui.video, now);
        state.landmarks = result.faceLandmarks?.[0] || null;
      } catch (error) {
        console.warn("Face frame skipped", error);
      }
    }
    if (state.landmarks && state.activeFilter !== "none") {
      context.save();
      if (state.facingMode === "user") {
        context.translate(width, 0);
        context.scale(-1, 1);
      }
      FILTERS[state.activeFilter].draw(context, state.landmarks, width, height, now);
      context.restore();
    }
    state.animationId = requestAnimationFrame(renderFrame);
  }

  function point(landmarks, index, width, height) {
    return { x: landmarks[index].x * width, y: landmarks[index].y * height };
  }
  function faceBox(landmarks, width, height) {
    const xs = landmarks.map((item) => item.x * width);
    const ys = landmarks.map((item) => item.y * height);
    const left = Math.min(...xs), right = Math.max(...xs), top = Math.min(...ys), bottom = Math.max(...ys);
    return { left, right, top, bottom, width: right - left, height: bottom - top, cx: (left + right) / 2, cy: (top + bottom) / 2 };
  }
  function clipEllipse(ctx, x, y, rx, ry) {
    ctx.beginPath(); ctx.ellipse(x, y, rx, ry, 0, 0, Math.PI * 2); ctx.clip();
  }
  function redrawPatch(ctx, x, y, sourceRadius, scaleX, scaleY = scaleX) {
    const diameter = sourceRadius * 2;
    ctx.drawImage(ui.video, x - sourceRadius, y - sourceRadius, diameter, diameter,
      x - sourceRadius * scaleX, y - sourceRadius * scaleY, diameter * scaleX, diameter * scaleY);
  }
  function drawBigEyes(ctx, landmarks, width, height) {
    [[33, 133], [362, 263]].forEach(([a, b]) => {
      const p1 = point(landmarks, a, width, height), p2 = point(landmarks, b, width, height);
      const x = (p1.x + p2.x) / 2, y = (p1.y + p2.y) / 2;
      const radius = Math.max(12, Math.hypot(p2.x - p1.x, p2.y - p1.y) * .8);
      ctx.save(); clipEllipse(ctx, x, y, radius * 1.5, radius * 1.35); redrawPatch(ctx, x, y, radius, 1.48); ctx.restore();
    });
  }
  function drawWideFace(ctx, landmarks, width, height) {
    const box = faceBox(landmarks, width, height), pad = box.width * .08;
    ctx.save(); clipEllipse(ctx, box.cx, box.cy, box.width * .64, box.height * .53);
    ctx.drawImage(ui.video, box.left - pad, box.top, box.width + pad * 2, box.height,
      box.left - box.width * .2, box.top, box.width * 1.4, box.height); ctx.restore();
  }
  function drawMegaMouth(ctx, landmarks, width, height) {
    const left = point(landmarks, 61, width, height), right = point(landmarks, 291, width, height);
    const top = point(landmarks, 13, width, height), bottom = point(landmarks, 14, width, height);
    const center = { x: (left.x + right.x) / 2, y: (top.y + bottom.y) / 2 };
    const mouthWidth = Math.max(1, Math.hypot(right.x - left.x, right.y - left.y));
    const axis = { x: (right.x - left.x) / mouthWidth, y: (right.y - left.y) / mouthWidth };
    const normal = { x: -axis.y, y: axis.x };
    const sourceBoundary = OUTER_LIP_LANDMARKS.map((index) => point(landmarks, index, width, height));
    const targetBoundary = sourceBoundary.map((source) => {
      const dx = source.x - center.x, dy = source.y - center.y;
      const along = dx * axis.x + dy * axis.y;
      const across = dx * normal.x + dy * normal.y;
      return {
        x: center.x + axis.x * along * 2.32 + normal.x * across * 1.34,
        y: center.y + axis.y * along * 2.32 + normal.y * across * 1.34,
      };
    });

    for (let index = 0; index < sourceBoundary.length; index += 1) {
      const next = (index + 1) % sourceBoundary.length;
      drawWarpedTriangle(
        ctx,
        [center, sourceBoundary[index], sourceBoundary[next]],
        [center, targetBoundary[index], targetBoundary[next]],
        width,
        height,
      );
    }
  }
  function drawWarpedTriangle(ctx, source, target, width, height) {
    const [s0, s1, s2] = source, [d0, d1, d2] = target;
    const determinant = s0.x * (s1.y - s2.y) + s1.x * (s2.y - s0.y) + s2.x * (s0.y - s1.y);
    if (Math.abs(determinant) < .001) return;
    const a = (d0.x * (s1.y - s2.y) + d1.x * (s2.y - s0.y) + d2.x * (s0.y - s1.y)) / determinant;
    const b = (d0.y * (s1.y - s2.y) + d1.y * (s2.y - s0.y) + d2.y * (s0.y - s1.y)) / determinant;
    const c = (d0.x * (s2.x - s1.x) + d1.x * (s0.x - s2.x) + d2.x * (s1.x - s0.x)) / determinant;
    const d = (d0.y * (s2.x - s1.x) + d1.y * (s0.x - s2.x) + d2.y * (s1.x - s0.x)) / determinant;
    const e = (d0.x * (s1.x * s2.y - s2.x * s1.y) + d1.x * (s2.x * s0.y - s0.x * s2.y) + d2.x * (s0.x * s1.y - s1.x * s0.y)) / determinant;
    const f = (d0.y * (s1.x * s2.y - s2.x * s1.y) + d1.y * (s2.x * s0.y - s0.x * s2.y) + d2.y * (s0.x * s1.y - s1.x * s0.y)) / determinant;

    ctx.save();
    ctx.beginPath();
    ctx.moveTo(d0.x, d0.y); ctx.lineTo(d1.x, d1.y); ctx.lineTo(d2.x, d2.y); ctx.closePath();
    ctx.clip();
    ctx.transform(a, b, c, d, e, f);
    ctx.drawImage(ui.video, 0, 0, width, height);
    ctx.restore();
  }
  function drawTinyMouth(ctx, landmarks, width, height) {
    const left = point(landmarks, 61, width, height), right = point(landmarks, 291, width, height);
    const top = point(landmarks, 13, width, height), bottom = point(landmarks, 14, width, height);
    const x = (left.x + right.x) / 2, y = (top.y + bottom.y) / 2;
    const rx = Math.max(18, Math.abs(right.x - left.x) * .65), ry = Math.max(12, rx * .42);
    ctx.save(); ctx.filter = "blur(7px)"; clipEllipse(ctx, x, y, rx, ry); ctx.drawImage(ui.video, x-rx, y-ry*2.2, rx*2, ry, x-rx, y-ry, rx*2, ry*2); ctx.restore();
    ctx.save(); clipEllipse(ctx, x, y, rx*.46, ry*.58); ctx.drawImage(ui.video, x-rx, y-ry, rx*2, ry*2, x-rx*.46, y-ry*.58, rx*.92, ry*1.16); ctx.restore();
  }
  function drawWobble(ctx, landmarks, width, height, now) {
    const box = faceBox(landmarks, width, height), angle = Math.sin(now / 115) * .09, dx = Math.sin(now / 85) * box.width * .05;
    ctx.save(); clipEllipse(ctx, box.cx, box.cy, box.width*.57, box.height*.54); ctx.translate(box.cx+dx, box.cy); ctx.rotate(angle);
    ctx.drawImage(ui.video, box.left, box.top, box.width, box.height, -box.width/2, -box.height/2, box.width, box.height); ctx.restore();
  }
  function drawSpaceEars(ctx, landmarks, width, height) {
    const box = faceBox(landmarks, width, height), earY = box.cy - box.height*.08;
    ctx.fillStyle="#b7ff62"; ctx.strokeStyle="#30124d"; ctx.lineWidth=Math.max(4,box.width*.018);
    [-1,1].forEach((side) => { const baseX=box.cx+side*box.width*.48, tipX=box.cx+side*box.width*.86;
      ctx.beginPath(); ctx.moveTo(baseX,earY-box.height*.16); ctx.quadraticCurveTo(tipX,earY,baseX,earY+box.height*.18); ctx.closePath(); ctx.fill(); ctx.stroke(); });
    ctx.fillStyle="rgba(255,79,154,.55)"; [-1,1].forEach((side)=>{ctx.beginPath();ctx.ellipse(box.cx+side*box.width*.61,earY,box.width*.16,box.height*.055,0,0,Math.PI*2);ctx.fill();});
  }
  function drawHeroMask(ctx, landmarks, width, height) {
    const l = point(landmarks, 33, width, height), r = point(landmarks, 263, width, height), box=faceBox(landmarks,width,height);
    const cx=(l.x+r.x)/2, cy=(l.y+r.y)/2, maskW=Math.abs(r.x-l.x)*1.42, maskH=box.height*.23;
    ctx.fillStyle="rgba(120,60,255,.82)"; ctx.strokeStyle="#43e8ff"; ctx.lineWidth=Math.max(3,box.width*.012);
    ctx.beginPath(); ctx.moveTo(cx-maskW/2,cy-maskH*.3); ctx.quadraticCurveTo(cx,cy-maskH, cx+maskW/2,cy-maskH*.3); ctx.lineTo(cx+maskW*.42,cy+maskH*.62); ctx.quadraticCurveTo(cx,cy+maskH*.2,cx-maskW*.42,cy+maskH*.62); ctx.closePath(); ctx.fill();ctx.stroke();
    [l,r].forEach((eye)=>{ctx.save();clipEllipse(ctx,eye.x,eye.y,box.width*.07,box.height*.035);ctx.drawImage(ui.video,0,0,width,height);ctx.restore();});
  }
  function drawPartyHat(ctx, landmarks, width, height) {
    const box=faceBox(landmarks,width,height), baseY=box.top+box.height*.03, hatH=box.height*.65;
    const gradient=ctx.createLinearGradient(box.cx,baseY-hatH,box.cx,baseY); gradient.addColorStop(0,"#43e8ff");gradient.addColorStop(.5,"#8a5cff");gradient.addColorStop(1,"#ff4f9a");
    ctx.fillStyle=gradient;ctx.strokeStyle="#fff";ctx.lineWidth=Math.max(3,box.width*.012);ctx.beginPath();ctx.moveTo(box.cx,baseY-hatH);ctx.lineTo(box.cx-box.width*.38,baseY);ctx.lineTo(box.cx+box.width*.38,baseY);ctx.closePath();ctx.fill();ctx.stroke();
    ctx.fillStyle="#ffe66d";ctx.beginPath();ctx.arc(box.cx,baseY-hatH,box.width*.075,0,Math.PI*2);ctx.fill();
    for(let i=0;i<5;i++){ctx.fillStyle=i%2?"#ffe66d":"#fff";ctx.beginPath();ctx.arc(box.cx+(i-2)*box.width*.12,baseY-hatH*.34-(i%2)*hatH*.18,box.width*.025,0,Math.PI*2);ctx.fill();}
  }

  async function flipCamera() {
    if (!state.stream) return;
    const wasRecording = state.recorder?.state === "recording";
    if (wasRecording) stopRecording();
    state.stream.getTracks().forEach((track) => track.stop());
    state.stream = null;
    cancelAnimationFrame(state.animationId);
    state.facingMode = state.facingMode === "user" ? "environment" : "user";
    await startCamera();
  }
  function stopCamera() {
    if (state.recorder?.state === "recording") stopRecording();
    state.stream?.getTracks().forEach((track) => track.stop());
    state.stream = null; state.landmarks = null; state.lastVideoTime = -1;
    cancelAnimationFrame(state.animationId); ui.video.srcObject = null;
    ui.placeholder.hidden = false; ui.start.disabled = false; ui.start.textContent = "Start camera"; ui.record.disabled = true; ui.stop.disabled = true; ui.flip.disabled = true;
    setStatus("Camera is off");
  }
  function preferredMimeType() {
    return ["video/mp4;codecs=h264,aac", "video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm"]
      .find((type) => MediaRecorder.isTypeSupported(type)) || "";
  }
  function toggleRecording() {
    if (state.recorder?.state === "recording") stopRecording(); else startRecording();
  }
  function startRecording() {
    if (!state.stream || !window.MediaRecorder || !ui.canvas.captureStream) return;
    discardRecording();
    const output = ui.canvas.captureStream(30);
    state.stream.getAudioTracks().forEach((track) => output.addTrack(track));
    const mimeType = preferredMimeType();
    try { state.recorder = new MediaRecorder(output, mimeType ? { mimeType, videoBitsPerSecond: 4_000_000 } : undefined); }
    catch (error) { setStatus("Recording is not supported by this browser."); return; }
    state.chunks=[];
    state.recorder.addEventListener("dataavailable", (event)=>{if(event.data.size) state.chunks.push(event.data);});
    state.recorder.addEventListener("stop", finishRecording, {once:true});
    state.recorder.addEventListener("error", ()=>setStatus("Recording stopped because the browser reported an error."));
    state.recorder.start(1000); state.startedAt=Date.now();
    ui.record.classList.add("is-recording"); ui.record.querySelector("b").textContent="Stop recording";
    ui.liveBadge.hidden=false; document.body.classList.add("is-recording"); updateTimer(); state.timerId=setInterval(updateTimer,500);
    setStatus("Recording locally · press stop when you are done");
  }
  function stopRecording() { if(state.recorder?.state==="recording") state.recorder.stop(); clearInterval(state.timerId); }
  function finishRecording() {
    const type=state.recorder.mimeType||"video/webm", blob=new Blob(state.chunks,{type});
    if(state.resultUrl) URL.revokeObjectURL(state.resultUrl); state.resultUrl=URL.createObjectURL(blob);
    ui.playback.src=state.resultUrl; ui.download.href=state.resultUrl; ui.download.download=`cxms-face-filter-${new Date().toISOString().slice(0,19).replaceAll(":","-")}.${type.includes("mp4")?"mp4":"webm"}`;
    ui.result.hidden=false; ui.result.scrollIntoView({behavior:"smooth",block:"nearest"});
    ui.record.classList.remove("is-recording");ui.record.querySelector("b").textContent="Start recording";ui.liveBadge.hidden=true;document.body.classList.remove("is-recording");
    setStatus("Video ready to preview or download");
  }
  function updateTimer(){const seconds=Math.floor((Date.now()-state.startedAt)/1000);ui.timer.textContent=`${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,"0")}`;}
  function discardRecording(){if(state.resultUrl)URL.revokeObjectURL(state.resultUrl);state.resultUrl="";ui.playback.removeAttribute("src");ui.playback.load();ui.download.removeAttribute("href");ui.result.hidden=true;}
}
