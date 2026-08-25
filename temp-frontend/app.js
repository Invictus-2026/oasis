/* SpillTrace temp-frontend — talks to backend/app/api/upload.py's
 * POST /api/detect/upload. No build step, no framework: file input ->
 * FormData -> fetch -> draw circles on a canvas over the uploaded image. */

const fileInput = document.getElementById("file");
const methodSelect = document.getElementById("method");
const gsdInput = document.getElementById("gsd");
const backendInput = document.getElementById("backend");
const runButton = document.getElementById("run");
const statusEl = document.getElementById("status");
const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");
const emptyHint = document.getElementById("emptyHint");
const resultsEl = document.getElementById("results");
const totalsEl = document.getElementById("totals");
const regionListEl = document.getElementById("regionList");
const lookalikeListEl = document.getElementById("lookalikeList");
const processingListEl = document.getElementById("processingList");
const notesEl = document.getElementById("notes");

const MAX_CANVAS_WIDTH = 820;

let currentImage = null; // HTMLImageElement, natural size
let currentScale = 1;    // canvas px per original-image px

function setStatus(text, kind) {
  statusEl.textContent = text;
  statusEl.className = kind || "";
}

function drawBaseImage() {
  if (!currentImage) return;
  const scale = Math.min(1, MAX_CANVAS_WIDTH / currentImage.naturalWidth);
  currentScale = scale;
  canvas.width = Math.round(currentImage.naturalWidth * scale);
  canvas.height = Math.round(currentImage.naturalHeight * scale);
  ctx.drawImage(currentImage, 0, 0, canvas.width, canvas.height);
}

fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  if (!file) return;
  const url = URL.createObjectURL(file);
  const img = new Image();
  img.onload = () => {
    currentImage = img;
    emptyHint.hidden = true;
    drawBaseImage();
    runButton.disabled = false;
    resultsEl.hidden = true;
    setStatus(`${file.name} — ${img.naturalWidth}×${img.naturalHeight}px`);
    URL.revokeObjectURL(url);
  };
  img.onerror = () => setStatus("Could not load that image file.", "err");
  img.src = url;
});

function drawRegion(region, color, dashed) {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  if (dashed) ctx.setLineDash([6, 4]);

  // contour polygon, scaled into canvas space
  const pts = region.contour;
  if (pts.length >= 2) {
    ctx.beginPath();
    ctx.moveTo(pts[0][0] * currentScale, pts[0][1] * currentScale);
    for (let i = 1; i < pts.length; i++) {
      ctx.lineTo(pts[i][0] * currentScale, pts[i][1] * currentScale);
    }
    ctx.closePath();
    ctx.stroke();
  }

  // enclosing circle, as a softer secondary border
  ctx.globalAlpha = 0.55;
  ctx.beginPath();
  ctx.arc(
    region.circle.cx * currentScale,
    region.circle.cy * currentScale,
    region.circle.radius * currentScale,
    0, Math.PI * 2
  );
  ctx.stroke();
  ctx.restore();
}

function fmt(n, digits = 2) {
  return Number(n).toLocaleString(undefined, { maximumFractionDigits: digits });
}

function statCard(label, value) {
  const div = document.createElement("div");
  div.className = "stat";
  div.innerHTML = `<div class="label">${label}</div><div class="value">${value}</div>`;
  return div;
}

function regionCard(region, isLookalike) {
  const div = document.createElement("div");
  div.className = "region-card" + (isLookalike ? " lookalike" : "");
  div.innerHTML = `
    <div class="headline">
      <span>${isLookalike ? "Look-alike" : "Oil region"}</span>
      <span>conf ${fmt(region.confidence, 2)}</span>
    </div>
    <div class="reason">${region.reason}</div>
    <div class="metrics">
      <span>area <b>${fmt(region.area_km2, 4)} km²</b></span>
      <span>contrast <b>${fmt(region.contrast_db, 1)} dB</b></span>
      <span>thickness <b>${fmt(region.thickness_um, 1)} µm</b></span>
      <span>volume <b>${fmt(region.volume_liters, 0)} L</b></span>
      <span>(<b>${fmt(region.volume_barrels, 1)}</b> bbl)</span>
    </div>
  `;
  return div;
}

function renderResults(data) {
  drawBaseImage();
  data.oil_regions.forEach((r) => drawRegion(r, "#f2a93c", false));
  data.rejected_lookalikes.forEach((r) => drawRegion(r, "#8aa0c9", true));

  totalsEl.innerHTML = "";
  totalsEl.appendChild(statCard("Oil regions", data.oil_regions.length));
  totalsEl.appendChild(statCard("Total area", `${fmt(data.total_area_km2, 4)} km²`));
  totalsEl.appendChild(statCard("Est. volume (L)", fmt(data.total_volume_liters, 0)));
  totalsEl.appendChild(statCard("Est. volume (bbl)", fmt(data.total_volume_barrels, 1)));

  regionListEl.innerHTML = "";
  if (data.oil_regions.length === 0) {
    regionListEl.innerHTML = '<p class="empty-note">No oil-like regions detected.</p>';
  } else {
    data.oil_regions.forEach((r) => regionListEl.appendChild(regionCard(r, false)));
  }

  lookalikeListEl.innerHTML = "";
  if (data.rejected_lookalikes.length === 0) {
    lookalikeListEl.innerHTML = '<p class="empty-note">None rejected.</p>';
  } else {
    data.rejected_lookalikes.forEach((r) => lookalikeListEl.appendChild(regionCard(r, true)));
  }

  processingListEl.innerHTML = "";
  data.processing.forEach((step) => {
    const li = document.createElement("li");
    li.textContent = `${step.name} — ${step.duration_ms}ms${step.detail ? " (" + step.detail + ")" : ""}`;
    processingListEl.appendChild(li);
  });

  notesEl.textContent = data.notes;
  resultsEl.hidden = false;
}

runButton.addEventListener("click", async () => {
  const file = fileInput.files[0];
  if (!file) return;

  const backend = backendInput.value.replace(/\/$/, "");
  const form = new FormData();
  form.append("file", file);
  form.append("method", methodSelect.value);
  form.append("gsd_m", gsdInput.value);

  runButton.disabled = true;
  setStatus("Running detection…");

  try {
    const resp = await fetch(`${backend}/api/detect/upload`, { method: "POST", body: form });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }
    const data = await resp.json();
    renderResults(data);
    setStatus(`Done — ${data.oil_regions.length} oil region(s) found.`, "ok");
  } catch (e) {
    setStatus(`Failed: ${e.message}. Is the backend running at ${backend}?`, "err");
  } finally {
    runButton.disabled = false;
  }
});
