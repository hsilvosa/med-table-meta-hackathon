// The camera page: the live scan of the 3D room, but with the camera of the device (a webcam or a phone), or with a photo standing in for the camera.
// Frames go to /scan (scripts/serve_camera.py), which runs the same decoder and checks as the planner. The boxes are a preview; the photo is what counts.
import { drawScan, readStages } from './livescan.js';

const $ = id => document.getElementById(id);
const video = $('video'), fake = $('fake'), overlay = $('overlay'), stage = $('stage');
const MAX_FRAME_WIDTH = 4096;            // a live frame is capped here: wider only costs time
const NO_CODE_TEXT = 'No code read: move closer or add it by hand';

const state = { stream: null, source: null, facing: 'environment', wakeLock: null };   // source: the <video> or the canvas holding the stand-in photo
const live = { born: new Map(), boxes: [], nocode: [], busy: false, error: false, frameW: 1, scannedThumb: null, finished: 0, pause: 700, since: 0, prev: null };
let shooting = false, toastTimer;

function toast(text, ms = 3500) {
  const t = $('toast'); t.textContent = text; t.style.opacity = 1;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.style.opacity = 0; }, ms);
}
function setError(text) { const e = $('error'); e.style.display = text ? 'block' : 'none'; e.textContent = text || ''; }
const sourceSize = () => state.source === video ? [video.videoWidth, video.videoHeight] : state.source === fake ? [fake.width, fake.height] : [0, 0];
const ready = () => !!state.source && sourceSize()[0] > 0 && (state.source !== video || video.readyState >= 2);

// ---- layout: the overlay covers exactly the picture (the video is letter-boxed inside the stage) ---------------------------------------
function layoutOverlay() {
  const [w, h] = sourceSize();
  if (!w) return;
  const W = stage.clientWidth, H = stage.clientHeight;
  let cw = W, ch = W * h / w;
  if (ch > H) { ch = H; cw = H * w / h; }
  const left = (W - cw) / 2, top = (H - ch) / 2;
  Object.assign(overlay.style, { left: `${left}px`, top: `${top}px`, width: `${cw}px`, height: `${ch}px` });
  overlay.width = Math.round(cw); overlay.height = Math.round(ch);
  Object.assign($('sweep').style, { left: `${left}px`, width: `${cw}px` });
  $('sweep').style.setProperty('--t0', `${top}px`); $('sweep').style.setProperty('--t1', `${top + ch - 3}px`);
  redraw();
}
function redraw() { if (drawScan(overlay, live.frameW, live, NO_CODE_TEXT, 13)) requestAnimationFrame(redraw); }
new ResizeObserver(layoutOverlay).observe(stage);

// ---- starting and stopping the camera -----------------------------------------------------------------------------------------------
function showSource(which) {
  video.style.display = which === video ? 'block' : 'none';
  fake.style.display = which === fake ? 'block' : 'none';
  $('idle').style.display = which ? 'none' : 'flex';
  state.source = which;
  $('shutter').disabled = !which;
  $('step1').classList.toggle('current', !which); $('step2').classList.toggle('current', !!which); $('step3').classList.toggle('current', !!which);
  resetScan();
}
function stopCamera() {
  state.stream?.getTracks().forEach(t => t.stop()); state.stream = null; video.srcObject = null;
  state.wakeLock?.release?.().catch(() => {}); state.wakeLock = null;
}
function resetScan() { live.boxes = []; live.nocode = []; live.scannedThumb = null; live.prev = null; live.born.clear(); live.error = false; redraw(); }

function describe(error) {
  switch (error.name) {
    case 'NotAllowedError': case 'SecurityError': return 'The camera is blocked. Allow it with the camera icon in the address bar, then press Start again.';
    case 'NotFoundError': case 'DevicesNotFoundError': return 'No camera was found on this device. You can try the page with "Use a photo as the camera".';
    case 'NotReadableError': return 'The camera is in use by another program. Close it and press Start again.';
    default: return `The camera could not be opened (${error.name || error}).`;
  }
}
async function startCamera() {
  setError('');
  if (!navigator.mediaDevices?.getUserMedia) {
    setError(window.isSecureContext ? 'This browser cannot open the camera.'
      : 'A browser only gives the camera to a secure page. On this computer open http://127.0.0.1:8700/camera.html. On a phone start the server with --lan --https.');
    return;
  }
  stopCamera();
  const wanted = { video: { facingMode: { ideal: state.facing }, width: { ideal: 4096 }, height: { ideal: 3072 } }, audio: false };
  try {
    try { state.stream = await navigator.mediaDevices.getUserMedia(wanted); }
    catch (error) { if (error.name !== 'OverconstrainedError') throw error; state.stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false }); }
    video.srcObject = state.stream;
    await video.play();
    showSource(video);
    try { state.wakeLock = await navigator.wakeLock?.request('screen'); } catch { /* the screen may sleep: not important */ }
    await showCameraInfo();
    toast('Camera on. Hold still over the boxes.');
  } catch (error) { setError(describe(error)); showSource(null); updateChips(); }
}
async function showCameraInfo() {
  await new Promise(resolve => { if (video.videoWidth) resolve(); else video.addEventListener('loadedmetadata', resolve, { once: true }); });
  const [w, h] = sourceSize();
  const distance = Math.min(90, Math.max(15, Math.round(90 * w / 4000 / 5) * 5));      // scaled from the room: 90 cm for a 4000 px wide picture, in proportion for a smaller one
  $('camChip').textContent = `Camera ${w} x ${h}`; $('camChip').style.display = 'inline-block';
  $('gauge').className = ''; $('gauge').textContent = w >= 3000 ? 'Hold it about 90 cm above the boxes, or closer' : `This camera is ${w} px wide: hold it about ${distance} cm above the boxes, or closer`;
  const cameras = (await navigator.mediaDevices.enumerateDevices().catch(() => [])).filter(d => d.kind === 'videoinput');
  $('btnFlip').style.display = cameras.length > 1 ? 'block' : 'none';
  layoutOverlay();
}
async function useAPhoto(file) {
  setError('');
  try {
    const bitmap = await createImageBitmap(file);
    const s = Math.min(1, 8192 / Math.max(bitmap.width, bitmap.height));
    fake.width = Math.round(bitmap.width * s); fake.height = Math.round(bitmap.height * s);
    fake.getContext('2d').drawImage(bitmap, 0, 0, fake.width, fake.height);
    stopCamera(); showSource(fake);
    $('camChip').textContent = `Stand-in photo ${fake.width} x ${fake.height}`; $('camChip').style.display = 'inline-block';
    $('gauge').className = ''; $('gauge').textContent = 'A photo is standing in for the camera';
    $('btnFlip').style.display = 'none';
    layoutOverlay();
  } catch (error) { setError('That file could not be opened as a picture.'); }
}

// ---- frames and motion ----------------------------------------------------------------------------------------------------------------
const frameCanvas = document.createElement('canvas');
function grab(maxWidth) {
  const [w, h] = sourceSize(), s = Math.min(1, maxWidth / w);
  frameCanvas.width = Math.round(w * s); frameCanvas.height = Math.round(h * s);
  frameCanvas.getContext('2d').drawImage(state.source, 0, 0, frameCanvas.width, frameCanvas.height);
  return frameCanvas;
}
const toBlob = (canvas, quality) => new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', quality));
const thumbCanvas = Object.assign(document.createElement('canvas'), { width: 48, height: 36 });
const thumbContext = thumbCanvas.getContext('2d', { willReadFrequently: true });
function sample() {      // 48 x 36 grey picture of what the camera sees: enough to tell whether it moved
  thumbContext.drawImage(state.source, 0, 0, 48, 36);
  const data = thumbContext.getImageData(0, 0, 48, 36).data, grey = new Float32Array(48 * 36);
  for (let i = 0; i < grey.length; i++) grey[i] = 0.299 * data[4 * i] + 0.587 * data[4 * i + 1] + 0.114 * data[4 * i + 2];
  return grey;
}
function difference(a, b) { let sum = 0; for (let i = 0; i < a.length; i++) sum += Math.abs(a[i] - b[i]); return sum / a.length; }
const MOVING = 4, CHANGED = 8;           // mean difference (0 to 255) between two samples: the camera is moving / the view is no longer the scanned one

// ---- the live scan ----------------------------------------------------------------------------------------------------------------------
function updateChips() {
  const chip = $('scanChip'), show = ready() && $('live').checked;
  chip.style.display = show ? 'inline-block' : 'none';
  $('sweep').style.display = show && live.busy ? 'block' : 'none';
  if (!show) return;
  const ok = live.boxes.filter(b => b.status === 'verified').length, bad = live.boxes.length - ok, none = live.nocode.length;
  if (live.busy) chip.textContent = live.boxes.length ? `Scanning... ${live.boxes.length} found so far` : 'Scanning...';
  else if (live.error) chip.textContent = 'Live scan unavailable (photos still work)';
  else if (!live.scannedThumb) chip.textContent = 'Hold still to scan';
  else {
    const parts = [`${ok} recognised`]; if (bad) parts.push(`${bad} not verified`); if (none) parts.push(`${none} without a code read`);
    chip.textContent = live.boxes.length || none ? 'Preview: ' + parts.join(', ') : 'Preview: no codes read here';
  }
}
function tick() {
  if (!ready()) { updateChips(); return; }
  const current = sample(), now = performance.now();
  if (live.prev && difference(current, live.prev) > MOVING) live.since = now;
  live.prev = current;
  if (live.scannedThumb && difference(current, live.scannedThumb) > CHANGED) { live.boxes = []; live.nocode = []; live.scannedThumb = null; redraw(); }      // boxes of an old view would point at the wrong place
  updateChips();
  const idle = $('live').checked && !live.busy && !shooting && !document.hidden;
  if (idle && !live.scannedThumb && now - live.since >= 300 && now - live.finished >= live.pause) scanOnce(current);
}
async function scanOnce(thumbAtStart) {
  live.busy = true;
  const started = performance.now();
  try {
    const canvas = grab(MAX_FRAME_WIDTH);
    const blob = await toBlob(canvas, 0.9);
    const reply = await fetch('/scan', { method: 'POST', body: blob, headers: { 'Content-Type': 'image/jpeg' } });
    if (!reply.ok) throw new Error(`HTTP ${reply.status}`);
    live.error = false; live.scannedThumb = thumbAtStart; live.frameW = canvas.width; live.born.clear(); live.boxes = []; live.nocode = [];
    const finished = await readStages(reply, stage => { live.boxes = stage.codes; live.nocode = stage.nocode ?? []; redraw(); },
      () => difference(sample(), thumbAtStart) > CHANGED);        // the camera moved while the frame was being read
    if (!finished) { live.boxes = []; live.nocode = []; live.scannedThumb = null; redraw(); }
    else describeResult();
  } catch (error) { live.error = true; live.scannedThumb = thumbAtStart; }
  finally {
    live.busy = false; live.finished = performance.now();
    live.pause = Math.max(700, 1.5 * (live.finished - started));      // the scan never takes more than about 40 % of the computer, so it stays usable
  }
}
function describeResult() {
  const g = $('gauge'), ok = live.boxes.filter(b => b.status === 'verified').length;
  if (ok) { g.className = 'good'; g.textContent = `${ok} code${ok > 1 ? 's' : ''} recognised. Take the photo when all the boxes are marked.`; }
  else if (live.boxes.length || live.nocode.length) { g.className = 'mid'; g.textContent = 'No code recognised yet: move closer, with the printed codes facing up.'; }
  else { g.className = ''; g.textContent = 'No box seen: point the camera at the table with the boxes.'; }
}
setInterval(tick, 200);
$('live').addEventListener('change', () => { resetScan(); updateChips(); });

// ---- the photo --------------------------------------------------------------------------------------------------------------------------
async function takePhoto() {
  if (!ready() || shooting) return;
  shooting = true; $('shutter').disabled = true;
  try {
    let blob = null;
    if (state.source === video && 'ImageCapture' in window) {      // the camera's own full-size still, if the browser can take one
      try { blob = await new ImageCapture(state.stream.getVideoTracks()[0]).takePhoto(); } catch { blob = null; }
    }
    if (!blob) blob = await toBlob(grab(8192), 0.95);
    const reply = await fetch('/photo', { method: 'POST', body: blob, headers: { 'Content-Type': blob.type || 'image/jpeg' } });
    if (!reply.ok) throw new Error(`HTTP ${reply.status}`);
    toast('Photo saved. The planner is reading it.', 5000);
    openPlanner(true);
  } catch (error) { toast(`The photo could not be saved: ${error}`, 6000); }
  finally { shooting = false; $('shutter').disabled = !ready(); }
}

// ---- the planner -----------------------------------------------------------------------------------------------------------------------
const local = ['localhost', '127.0.0.1'].includes(location.hostname);
const plannerUrl = `http://${location.hostname}:8501/?room=1&embed=true&source=camera`;     // the planner has no https: it opens inside this page only when both are on this computer
if (local) { $('app').src = plannerUrl; } else { $('app').style.display = 'none'; $('applink').style.display = 'block'; $('applink2').href = plannerUrl; }
$('openApp').href = plannerUrl;
function openPlanner(open) {
  const on = open ?? !document.body.classList.contains('planner');
  document.body.classList.toggle('planner', on);
  $('btnPlanner').classList.toggle('on', on); $('btnPlanner').textContent = on ? 'Hide the planner' : 'Show the planner';
  layoutOverlay();
}

$('btnStart').addEventListener('click', startCamera);
$('btnFlip').addEventListener('click', () => { state.facing = state.facing === 'environment' ? 'user' : 'environment'; startCamera(); });
$('fakeFile').addEventListener('change', event => { if (event.target.files[0]) useAPhoto(event.target.files[0]); event.target.value = ''; });
$('shutter').addEventListener('click', takePhoto);
$('btnPlanner').addEventListener('click', () => openPlanner());
$('btnClose').addEventListener('click', () => openPlanner(false));
addEventListener('keydown', event => {
  if (event.target.matches?.('input, textarea')) return;
  if (event.code === 'Space') { event.preventDefault(); takePhoto(); }
  if (event.code === 'Tab') { event.preventDefault(); openPlanner(); }
});
window.__camera = { state, live, takePhoto, useAPhoto, scanOnce, tick };
