// The camera page: the live scan of the 3D room, but with the camera of the device (a webcam or a phone), or with a photo standing in for the camera.
// Frames go to /scan (scripts/serve_camera.py), which runs the same decoder and checks as the planner. The frames drawn on the boxes are a preview; the photo is what counts.
// What to do next is one sentence from the server (src/medtable/advice.py), shown big, optionally read aloud.
import { drawScan, readStages } from './livescan.js';
import { initPrefs, showAdvice, forgetSpoken } from './uikit.js';

const $ = id => document.getElementById(id);
const video = $('video'), fake = $('fake'), overlay = $('overlay'), stage = $('stage');
const MAX_FRAME_WIDTH = 4096;            // a live frame is capped here: wider only costs time
const NO_CODE_TEXT = 'No code read: move closer or add it by hand';
const MAX_ATTEMPTS = 4;                  // a view that still has unread boxes is looked at again (focus settles, noise differs), at most this many times

const state = { stream: null, track: null, caps: {}, zoom: 1, torch: false, source: null, facing: 'environment', wakeLock: null };   // source: the <video> or the canvas holding the stand-in photo
const live = { born: new Map(), boxes: [], nocode: [], accum: new Map(), attempts: 0, advice: null, busy: false, error: false, frameW: 1,
               scannedThumb: null, finished: 0, pause: 700, since: 0, prev: null };
let shooting = false, toastTimer;
initPrefs();

function toast(text, ms = 5000) {
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
  $('sweep').style.setProperty('--t0', `${top}px`); $('sweep').style.setProperty('--t1', `${top + ch - 4}px`);
  redraw();
}
function labelSize() { return Math.round(Math.min(24, Math.max(14, overlay.width / 38)) * (document.documentElement.classList.contains('big') ? 1.2 : 1)); }
function redraw() { if (drawScan(overlay, live.frameW, live, NO_CODE_TEXT, labelSize())) requestAnimationFrame(redraw); }
new ResizeObserver(layoutOverlay).observe(stage);
new MutationObserver(redraw).observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });        // the text size changed

// ---- starting and stopping the camera -----------------------------------------------------------------------------------------------
function showSource(which) {
  video.style.display = which === video ? 'block' : 'none';
  fake.style.display = which === fake ? 'block' : 'none';
  $('idle').style.display = which ? 'none' : 'flex';
  state.source = which;
  $('shutter').disabled = !which;
  $('stageStart').style.display = which ? 'none' : '';
  $('stageShoot').style.display = which ? '' : 'none';
  $('step1').classList.toggle('current', !which); $('step2').classList.toggle('current', !!which);
  resetScan();
}
function stopCamera() {
  state.stream?.getTracks().forEach(t => t.stop()); state.stream = null; state.track = null; video.srcObject = null;
  state.wakeLock?.release?.().catch(() => {}); state.wakeLock = null;
  for (const id of ['btnZoomIn', 'btnZoomOut', 'btnLight']) $(id).style.display = 'none';
}
function resetScan() {
  live.boxes = []; live.nocode = []; live.accum.clear(); live.born.clear(); live.attempts = 0; live.advice = null;
  live.scannedThumb = null; live.prev = null; live.error = false; forgetSpoken(); redraw();
}

function describe(error) {
  switch (error.name) {
    case 'NotAllowedError': case 'SecurityError': return 'The camera is blocked. Click the camera icon in the address bar, choose "Allow", then press "Turn on the camera" again.';
    case 'NotFoundError': case 'DevicesNotFoundError': return 'No camera was found on this device. You can still try this page with "Use a photo instead".';
    case 'NotReadableError': return 'Another program is using the camera. Close it, then press "Turn on the camera" again.';
    default: return `The camera could not be opened (${error.name || error}). Press "Turn on the camera" to try again.`;
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
    await setupTrack();
    await showCameraInfo();
    toast('The camera is on. Hold it still over the boxes.');
  } catch (error) { setError(describe(error)); showSource(null); updateChips(); }
}
// What this camera can do beyond showing a picture: keep focusing, zoom, a light. Each button appears only when the camera offers it.
async function setupTrack() {
  state.track = state.stream?.getVideoTracks()[0] ?? null;
  state.caps = state.track?.getCapabilities?.() ?? {};
  state.zoom = state.track?.getSettings?.().zoom ?? state.caps.zoom?.min ?? 1;
  state.torch = false;
  if (state.caps.focusMode?.includes?.('continuous')) await state.track.applyConstraints({ advanced: [{ focusMode: 'continuous' }] }).catch(() => {});
  $('btnZoomIn').style.display = $('btnZoomOut').style.display = state.caps.zoom ? 'block' : 'none';
  $('btnLight').style.display = state.caps.torch ? 'block' : 'none'; $('btnLight').setAttribute('aria-pressed', 'false');
}
async function zoomBy(factor) {
  const range = state.caps.zoom; if (!range || !state.track) return;
  const z = Math.min(range.max, Math.max(range.min, state.zoom * factor));
  await state.track.applyConstraints({ advanced: [{ zoom: z }] }).catch(() => {});
  state.zoom = z; resetScan();
}
async function toggleLight() {
  if (!state.track) return;
  state.torch = !state.torch;
  await state.track.applyConstraints({ advanced: [{ torch: state.torch }] }).catch(() => { state.torch = false; });
  $('btnLight').setAttribute('aria-pressed', String(state.torch)); $('btnLight').classList.toggle('on', state.torch);
}
async function showCameraInfo() {
  await new Promise(resolve => { if (video.videoWidth) resolve(); else video.addEventListener('loadedmetadata', resolve, { once: true }); });
  const [w, h] = sourceSize();
  const distance = Math.min(90, Math.max(15, Math.round(90 * w / 4000 / 5) * 5));      // scaled from the room: 90 cm for a 4000 px wide picture, in proportion for a smaller one
  $('camChip').textContent = `Camera ${w} x ${h}`; $('camChip').style.display = 'inline-block';
  $('hint').textContent = `Put the boxes on a table with the printed codes facing up. Hold the camera about ${distance} cm above them, or closer. A green frame appears on every box that is recognised.`;
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
    $('camChip').textContent = `Photo ${fake.width} x ${fake.height}`; $('camChip').style.display = 'inline-block';
    $('btnFlip').style.display = 'none';
    layoutOverlay();
  } catch (error) { setError('That file could not be opened as a picture. Choose a JPG or PNG photo.'); }
}

// ---- frames and motion ----------------------------------------------------------------------------------------------------------------
const frameCanvas = document.createElement('canvas');
function grab(maxWidth) {
  const [w, h] = sourceSize(), s = Math.min(1, maxWidth / w);
  frameCanvas.width = Math.round(w * s); frameCanvas.height = Math.round(h * s);
  frameCanvas.getContext('2d').drawImage(state.source, 0, 0, frameCanvas.width, frameCanvas.height);
  return frameCanvas;
}
// Several frames averaged into one: the noise of a dark or grainy picture falls with the square root of their number, and that is often what separates a code that is
// read from one that is not (in a simulation, 1 of 23 codes read in a dark photo, 14 of 23 from the average of 4 frames, 16 of 23 from 8). Only while the camera stays still.
const averageCanvas = document.createElement('canvas');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function grabAveraged(maxWidth, count, stillEnough) {
  if (count <= 1) return grab(maxWidth);
  const [w, h] = sourceSize(), s = Math.min(1, maxWidth / w);
  averageCanvas.width = Math.round(w * s); averageCanvas.height = Math.round(h * s);
  const g = averageCanvas.getContext('2d');
  for (let i = 0; i < count; i++) {
    if (i) { await sleep(90); if (!stillEnough()) break; }
    g.globalAlpha = 1 / (i + 1);        // frame number i + 1 weighs 1 / (i + 1): after the loop the canvas holds the exact mean
    g.drawImage(state.source, 0, 0, averageCanvas.width, averageCanvas.height);
  }
  g.globalAlpha = 1;
  return averageCanvas;
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
  if (live.busy) chip.textContent = live.boxes.length ? `Looking... ${live.boxes.length} found so far` : 'Looking...';
  else if (live.error) chip.textContent = 'Frames are not available (photos still work)';
  else if (!live.scannedThumb) chip.textContent = 'Hold still';
  else {
    const parts = [`${ok} recognised`]; if (bad) parts.push(`${bad} not verified`); if (none) parts.push(`${none} without a code read`);
    chip.textContent = live.boxes.length || none ? parts.join(', ') : 'No codes read here';
  }
}
function refreshAdvice() {
  if (!ready()) return;
  if (!$('live').checked) { showAdvice('Frames on the boxes are switched off. You can still take the photo.', '', false); return; }
  if (live.error) showAdvice('The live preview is not available right now. You can still take the photo.', 'mid', false);
  else if (live.advice) showAdvice(live.advice.text, live.advice.level);
  else if (live.busy) showAdvice('Looking at the boxes...', '', false);
  else showAdvice('Hold the camera still over the boxes.', '', false);
}
function tick() {
  if (!ready()) { updateChips(); return; }
  const current = sample(), now = performance.now();
  if (live.prev && difference(current, live.prev) > MOVING) live.since = now;
  live.prev = current;
  if (live.scannedThumb && difference(current, live.scannedThumb) > CHANGED) { resetScan(); live.prev = current; }      // boxes of an old view would point at the wrong place
  updateChips(); refreshAdvice();
  const idle = $('live').checked && !live.busy && !shooting && !document.hidden && now - live.since >= 300;
  const again = !!live.scannedThumb && !!live.advice && live.advice.level !== 'good' && live.attempts < MAX_ATTEMPTS && now - live.finished >= 1500;
  if (idle && ((!live.scannedThumb && now - live.finished >= live.pause) || again)) scanOnce(current, again);
}
function mergeCodes(codes) {
  for (const c of codes) live.accum.set(c.raw ?? c.bbox.join(','), c);        // a code seen in an earlier look at the same view stays
  live.boxes = [...live.accum.values()];
}
const covered = ([x0, y0, x1, y1]) => live.boxes.some(c => { const cx = (c.bbox[0] + c.bbox[2]) / 2, cy = (c.bbox[1] + c.bbox[3]) / 2; return cx >= x0 && cx <= x1 && cy >= y0 && cy <= y1; });
function adviceOf(stage) {
  const a = stage.advice;
  if (!a) return null;
  if (!live.nocode.length && live.boxes.length) { const n = live.boxes.length; return { text: `${n} medicine${n === 1 ? '' : 's'} recognised. Take the photo when all your boxes are marked.`, level: 'good' }; }
  let text = a.text;
  if (a.distance === 'closer' && state.caps.zoom) text += ' You can also press "Zoom +".';
  if (a.light === 'dark' && state.caps.torch) text += ' You can also press "Light".';
  return { text, level: a.level };
}
async function scanOnce(thumbAtStart, again) {
  live.busy = true;
  const started = performance.now();
  try {
    const frames = !again ? (live.advice?.light === 'dark' ? 4 : 1) : (live.attempts <= 1 ? 4 : 8);        // a second and third look at a view average more frames
    const canvas = await grabAveraged(MAX_FRAME_WIDTH, frames, () => difference(sample(), thumbAtStart) < CHANGED);
    const blob = await toBlob(canvas, 0.9);
    const reply = await fetch('/scan', { method: 'POST', body: blob, headers: { 'Content-Type': 'image/jpeg', 'X-Thorough': again ? '1' : '0' } });
    if (!reply.ok) throw new Error(`HTTP ${reply.status}`);
    if (!again) { live.accum.clear(); live.born.clear(); live.nocode = []; live.advice = null; live.attempts = 0; }
    live.attempts += 1; live.error = false; live.scannedThumb = thumbAtStart; live.frameW = canvas.width;
    const finished = await readStages(reply, stage => {
      mergeCodes(stage.codes);
      if (stage.done) { live.nocode = (stage.nocode ?? []).filter(b => !covered(b)); live.advice = adviceOf(stage); }
      redraw();
    }, () => difference(sample(), thumbAtStart) > CHANGED);        // the camera moved while the frame was being read
    if (!finished) { resetScan(); }
  } catch (error) { live.error = true; live.scannedThumb = thumbAtStart; }
  finally {
    live.busy = false; live.finished = performance.now();
    live.pause = Math.max(700, 1.5 * (live.finished - started));      // the scan never takes more than about 40 % of the computer, so it stays usable
  }
}
setInterval(tick, 200);
$('live').addEventListener('change', () => { resetScan(); updateChips(); refreshAdvice(); });

// ---- the photo --------------------------------------------------------------------------------------------------------------------------
async function takePhoto() {
  if (!ready() || shooting) return;
  shooting = true; $('shutter').disabled = true; $('stageShoot').disabled = true;
  try {
    let blob = null;
    if (state.source === video && 'ImageCapture' in window) {      // the camera's own full-size still, if the browser can take one
      try { blob = await new ImageCapture(state.track).takePhoto(); } catch { blob = null; }
    }
    if (!blob) blob = await toBlob(grab(8192), 0.95);
    const reply = await fetch('/photo', { method: 'POST', body: blob, headers: { 'Content-Type': blob.type || 'image/jpeg' } });
    if (!reply.ok) throw new Error(`HTTP ${reply.status}`);
    toast('Photo taken. The planner is reading it now.', 6000);
    openPlanner(true);
  } catch (error) { toast(`The photo could not be saved. Please try again. (${error})`, 8000); }
  finally { shooting = false; $('shutter').disabled = !ready(); $('stageShoot').disabled = !ready(); }
}

// ---- the planner -----------------------------------------------------------------------------------------------------------------------
const local = ['localhost', '127.0.0.1'].includes(location.hostname);
const plannerUrl = `http://${location.hostname}:8501/?room=1&embed=true&source=camera`;     // the planner has no https: it opens inside this page only when both are on this computer
if (local) { $('app').src = plannerUrl; } else { $('app').style.display = 'none'; $('applink').style.display = 'block'; $('applink2').href = plannerUrl; }
$('openApp').href = plannerUrl;
function openPlanner(open) {
  const on = open ?? !document.body.classList.contains('planner');
  document.body.classList.toggle('planner', on);
  $('btnPlanner').classList.toggle('on', on); $('btnPlanner').textContent = on ? 'Hide the medicine planner' : 'Show the medicine planner';
  layoutOverlay();
}

$('btnStart').addEventListener('click', startCamera);
$('stageStart').addEventListener('click', startCamera);
$('stageShoot').addEventListener('click', takePhoto);
$('btnFlip').addEventListener('click', () => { state.facing = state.facing === 'environment' ? 'user' : 'environment'; startCamera(); });
$('fakeFile').addEventListener('change', event => { if (event.target.files[0]) useAPhoto(event.target.files[0]); event.target.value = ''; });
$('shutter').addEventListener('click', takePhoto);
$('btnZoomIn').addEventListener('click', () => zoomBy(1.4));
$('btnZoomOut').addEventListener('click', () => zoomBy(1 / 1.4));
$('btnLight').addEventListener('click', toggleLight);
$('btnPlanner').addEventListener('click', () => openPlanner());
$('btnClose').addEventListener('click', () => openPlanner(false));
addEventListener('keydown', event => {
  if (event.target.matches?.('input, textarea, button, a')) return;
  if (event.code === 'Space') { event.preventDefault(); takePhoto(); }
});
addEventListener('pagehide', stopCamera);
window.__camera = { state, live, takePhoto, useAPhoto, scanOnce, tick };
