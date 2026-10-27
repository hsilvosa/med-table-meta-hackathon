// A room with three tables of medicines (flat 2D cut-outs from the official CIMA photos with a generated Data Matrix sticker).
// Walk around in first person, take out a virtual phone and photograph a table; the photo goes to the local server
// (scripts/serve_world.py), which saves it with the ground truth, ready for the app (app.py) or for experiments/eval_photos.py.
import * as THREE from 'three';

const PHONE = { w: 4000, h: 3000, hfov: 71 };                      // a 12 MP phone main camera, 4:3
const PHONE_VFOV = 2 * Math.atan(Math.tan(THREE.MathUtils.degToRad(PHONE.hfov) / 2) * PHONE.h / PHONE.w) * 180 / Math.PI;
const FRAME_FRACTION = 0.86;                                         // the viewfinder takes this share of the window height
const EYE_MIN = 0.9, EYE_MAX = 1.9;

const world = await (await fetch('world/world.json')).json();
const canvas = document.getElementById('c');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
const scene = new THREE.Scene();
scene.background = new THREE.Color(0xcfd8dc);
const camera = new THREE.PerspectiveCamera(70, 1, 0.02, 40);
camera.rotation.order = 'YXZ';
const phoneCam = new THREE.PerspectiveCamera(PHONE_VFOV, PHONE.w / PHONE.h, 0.02, 40);
const loader = new THREE.TextureLoader();
const maxAniso = renderer.capabilities.getMaxAnisotropy();

function tex(url, srgb = true) {
  const t = loader.load('world/' + url);
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = maxAniso;
  return t;
}
function canvasTexture(size, draw, repeat) {
  const c = document.createElement('canvas'); c.width = c.height = size;
  draw(c.getContext('2d'), size);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace; t.wrapS = t.wrapT = THREE.RepeatWrapping; t.anisotropy = maxAniso;
  if (repeat) t.repeat.set(...repeat);
  return t;
}
function wood(ctx, s, base = '#9a6a3a', plank = 8) {
  ctx.fillStyle = base; ctx.fillRect(0, 0, s, s);
  for (let i = 0; i < plank; i++) {
    ctx.fillStyle = `rgba(0,0,0,${0.03 + (i % 3) * 0.03})`; ctx.fillRect(i * s / plank, 0, s / plank, s);
    ctx.fillStyle = 'rgba(0,0,0,.35)'; ctx.fillRect(i * s / plank, 0, 2, s);
  }
  for (let k = 0; k < 900; k++) {
    ctx.strokeStyle = `rgba(${60 + Math.random() * 40},${35 + Math.random() * 30},20,${Math.random() * 0.12})`;
    const x = Math.random() * s; ctx.beginPath(); ctx.moveTo(x, 0); ctx.bezierCurveTo(x + 6, s / 3, x - 6, 2 * s / 3, x + 2, s); ctx.stroke();
  }
}
function blobTexture() {
  return canvasTexture(128, (ctx, s) => {
    const g = ctx.createRadialGradient(s / 2, s / 2, 4, s / 2, s / 2, s / 2);
    g.addColorStop(0, 'rgba(0,0,0,.55)'); g.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = g; ctx.fillRect(0, 0, s, s);
  });
}

// ---- room -----------------------------------------------------------------------------------------------------------
const R = world.room;
const floorTex = canvasTexture(512, (c, s) => wood(c, s, '#b58a5a', 6), [R.w / 1.4, R.d / 1.4]);
const floor = new THREE.Mesh(new THREE.PlaneGeometry(R.w, R.d), new THREE.MeshStandardMaterial({ map: floorTex, roughness: 0.55 }));
floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; scene.add(floor);
const wallMat = new THREE.MeshStandardMaterial({ color: 0xeee9df, roughness: 0.95 });
function wall(w, h, x, y, z, ry) { const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), wallMat); m.position.set(x, y, z); m.rotation.y = ry; m.receiveShadow = true; scene.add(m); return m; }
wall(R.w, R.h, 0, R.h / 2, -R.d / 2, 0); wall(R.w, R.h, 0, R.h / 2, R.d / 2, Math.PI);
wall(R.d, R.h, -R.w / 2, R.h / 2, 0, Math.PI / 2); wall(R.d, R.h, R.w / 2, R.h / 2, 0, -Math.PI / 2);
const ceiling = new THREE.Mesh(new THREE.PlaneGeometry(R.w, R.d), new THREE.MeshStandardMaterial({ color: 0xf4f1ea, roughness: 1 }));
ceiling.rotation.x = Math.PI / 2; ceiling.position.y = R.h; scene.add(ceiling);
const win = new THREE.Mesh(new THREE.PlaneGeometry(2.4, 1.3), new THREE.MeshBasicMaterial({ color: 0xf3fbff }));
win.position.set(-1.2, 1.55, -R.d / 2 + 0.01); scene.add(win);
const frameMat = new THREE.MeshStandardMaterial({ color: 0xf5f5f5 });
for (const [w, h, x, y] of [[2.5, 0.06, 0, 0.65], [2.5, 0.06, 0, -0.65], [0.06, 1.32, -1.2, 0], [0.06, 1.32, 1.2, 0], [0.04, 1.3, 0, 0]]) {
  const f = new THREE.Mesh(new THREE.BoxGeometry(w, h, 0.05), frameMat); f.position.set(-1.2 + x, 1.55 + y, -R.d / 2 + 0.03); scene.add(f);
}
const rug = new THREE.Mesh(new THREE.PlaneGeometry(6.4, 2.8), new THREE.MeshStandardMaterial({ color: 0x5f6f80, roughness: 1 }));
rug.rotation.x = -Math.PI / 2; rug.position.set(0, 0.004, -0.6); scene.add(rug);
const shelf = new THREE.Mesh(new THREE.BoxGeometry(1.6, 1.9, 0.35), new THREE.MeshStandardMaterial({ color: 0x8a7458, roughness: 0.8 }));
shelf.position.set(R.w / 2 - 0.3, 0.95, 1.2); shelf.castShadow = true; scene.add(shelf);

scene.add(new THREE.HemisphereLight(0xffffff, 0xb9a58c, 0.85));
const sun = new THREE.DirectionalLight(0xfff0dd, 0.9);
sun.position.set(-3, 3.5, -2.5); sun.target.position.set(0, 0, -1); sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048); Object.assign(sun.shadow.camera, { left: -6, right: 6, top: 5, bottom: -5, near: 0.5, far: 14 });
scene.add(sun, sun.target);

// ---- tables and medicines -------------------------------------------------------------------------------------------
const tableWood = canvasTexture(512, (c, s) => wood(c, s, '#c79a64', 5), [1.5, 1]);
const tableMat = new THREE.MeshStandardMaterial({ map: tableWood, roughness: 0.45 });
const legMat = new THREE.MeshStandardMaterial({ color: 0x4d4d4d, roughness: 0.6 });
const blobTex = blobTexture();
const pickables = [];                       // meshes a ray can hit (to decide whether a label is visible from the phone)
const labelMeshes = [];                     // { mesh, item, table, modules }
const boxEntries = [];                      // boxes without a label
let stack = 0;

for (const t of world.tables) {
  const top = new THREE.Mesh(new THREE.BoxGeometry(t.w, 0.04, t.d), tableMat);
  top.position.set(t.x, t.h - 0.02, t.z); top.castShadow = top.receiveShadow = true; scene.add(top);
  for (const [dx, dz] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) {
    const leg = new THREE.Mesh(new THREE.BoxGeometry(0.05, t.h - 0.04, 0.05), legMat);
    leg.position.set(t.x + dx * (t.w / 2 - 0.06), (t.h - 0.04) / 2, t.z + dz * (t.d / 2 - 0.06)); leg.castShadow = true; scene.add(leg);
  }
  const lamp = new THREE.SpotLight(0xfff3e0, 3.2, 7, 1.1, 0.9, 1.2);
  lamp.position.set(t.x, R.h - 0.2, t.z + 0.4); lamp.target.position.set(t.x, t.h, t.z); scene.add(lamp, lamp.target);

  for (const item of t.items) {
    const group = new THREE.Group();
    stack += 1;
    group.position.set(t.x + item.x, t.h + 0.0015 + (item.kind === 'sheet' ? 0 : 0.0002 * (stack % 9)), t.z + item.z);
    group.rotation.y = item.rot;
    const map = tex(item.tex);
    const mat = new THREE.MeshStandardMaterial({ map, transparent: item.kind !== 'sheet', alphaTest: item.kind === 'sheet' ? 0 : 0.4, roughness: item.kind === 'pill' ? 0.4 : 0.7 });
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(item.w, item.h), mat);
    mesh.rotation.x = -Math.PI / 2; mesh.position.y = 0.0006; mesh.receiveShadow = true;
    const blob = new THREE.Mesh(new THREE.PlaneGeometry(item.w * 1.25, item.h * 1.25), new THREE.MeshBasicMaterial({ map: blobTex, transparent: true, depthWrite: false }));
    blob.rotation.x = -Math.PI / 2; blob.position.y = 0.0001; blob.renderOrder = -1;
    group.add(blob, mesh); pickables.push(mesh);
    if (item.kind === 'box' && item.label) {
      const lt = tex(item.label.tex);
      const sticker = new THREE.Mesh(new THREE.PlaneGeometry(item.label.size, item.label.size),
        new THREE.MeshStandardMaterial({ map: lt, roughness: 0.35, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }));
      sticker.rotation.x = -Math.PI / 2;
      sticker.position.set((item.label.u - 0.5) * item.w, 0.0012, (item.label.v - 0.5) * item.h);
      group.add(sticker); pickables.push(sticker);
      labelMeshes.push({ mesh: sticker, item, table: t });
    } else if (item.kind === 'box') {
      boxEntries.push({ mesh, item, table: t });
    }
    scene.add(group);
  }
}

// ---- player ---------------------------------------------------------------------------------------------------------
const player = { x: world.start.x, z: world.start.z, eye: 1.6, yaw: world.start.yaw, pitch: -0.05 };
let phoneMode = false, lean = false, locked = false, dragging = false;
const keys = new Set();

function applyCamera() {
  camera.position.set(player.x, player.eye, player.z);
  camera.rotation.set(player.pitch, player.yaw, 0);
}
function resize() {
  const w = innerWidth, h = innerHeight;
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2)); renderer.setSize(w, h, false);
  camera.aspect = w / h;
  const frameH = h * FRAME_FRACTION;
  const frameW = Math.min(frameH * PHONE.w / PHONE.h, w * 0.96);
  const frame = document.getElementById('frame');
  frame.style.height = `${frameW * PHONE.h / PHONE.w}px`; frame.style.width = `${frameW}px`;
  const usedH = frameW * PHONE.h / PHONE.w;
  // in phone mode the viewfinder rectangle must show exactly the phone's vertical field of view
  camera.fov = phoneMode ? 2 * Math.atan(Math.tan(THREE.MathUtils.degToRad(PHONE_VFOV) / 2) * h / usedH) * 180 / Math.PI : 70;
  camera.updateProjectionMatrix();
}
addEventListener('resize', resize);

function blocked(x, z) {
  if (Math.abs(x) > R.w / 2 - 0.3 || Math.abs(z) > R.d / 2 - 0.3) return true;
  if (lean) return false;
  return world.tables.some(t => Math.abs(x - t.x) < t.w / 2 + 0.28 && Math.abs(z - t.z) < t.d / 2 + 0.28)
    || (Math.abs(x - (R.w / 2 - 0.3)) < 0.95 && Math.abs(z - 1.2) < 0.45);
}
function move(dt) {
  const speed = (keys.has('ShiftLeft') ? 3 : 1.5) * (lean || phoneMode ? 0.5 : 1) * dt;
  const f = (keys.has('KeyW') ? 1 : 0) - (keys.has('KeyS') ? 1 : 0), s = (keys.has('KeyD') ? 1 : 0) - (keys.has('KeyA') ? 1 : 0);
  const dx = (-Math.sin(player.yaw) * f + Math.cos(player.yaw) * s) * speed, dz = (-Math.cos(player.yaw) * f - Math.sin(player.yaw) * s) * speed;
  if (!blocked(player.x + dx, player.z)) player.x += dx;
  if (!blocked(player.x, player.z + dz)) player.z += dz;
  const v = (keys.has('KeyR') ? 1 : 0) - (keys.has('KeyF') ? 1 : 0);
  player.eye = THREE.MathUtils.clamp(player.eye + v * dt * 0.7, EYE_MIN, EYE_MAX);
}

addEventListener('keydown', e => {
  keys.add(e.code);
  if (e.code === 'KeyP') { phoneMode = !phoneMode; resize(); document.getElementById('frame').style.display = phoneMode ? 'block' : 'none'; document.getElementById('cross').style.display = phoneMode ? 'none' : 'block'; }
  if (e.code === 'KeyX') { lean = !lean; toast(lean ? 'Inclinado sobre la mesa: ya no chocas con ella' : 'Colisión con las mesas activada'); }
  if (e.code === 'KeyH') document.getElementById('help').style.display = document.getElementById('help').style.display === 'none' ? 'block' : 'none';
  if (e.code === 'Space') { e.preventDefault(); shoot(); }
  const n = ['Digit1', 'Digit2', 'Digit3'].indexOf(e.code);
  if (n >= 0 && world.tables[n]) goTo(world.tables[n], e.shiftKey);
});
addEventListener('keyup', e => keys.delete(e.code));
canvas.addEventListener('click', () => { if (!locked) canvas.requestPointerLock?.(); });
document.addEventListener('pointerlockchange', () => { locked = document.pointerLockElement === canvas; });
canvas.addEventListener('mousedown', () => { dragging = true; });
addEventListener('mouseup', () => { dragging = false; });
addEventListener('mousemove', e => {
  if (!locked && !dragging) return;
  const k = phoneMode ? 0.0012 : 0.0022;
  player.yaw -= e.movementX * k; player.pitch = THREE.MathUtils.clamp(player.pitch - e.movementY * k, -1.55, 1.55);
});

function goTo(table, above) {
  if (above) {
    table.spot = ((table.spot ?? -1) + 1) % 2;           // a 50 cm photo covers about 0.7 x 0.5 m: left half, then right half
    lean = true; Object.assign(player, { x: table.x + (table.spot ? 0.26 : -0.26), z: table.z + 0.02, eye: table.h + 0.5, yaw: 0, pitch: -Math.PI / 2 + 0.02 }); phoneMode = true;
    toast(`${table.name}: móvil a 50 cm sobre la mitad ${table.spot ? 'derecha' : 'izquierda'} (repite para cambiar de mitad)`); }
  else { lean = false; Object.assign(player, { x: table.x, z: table.z + table.d / 2 + 0.9, eye: 1.5, yaw: 0, pitch: -0.55 }); toast(`${table.name}`); }
  document.getElementById('frame').style.display = phoneMode ? 'block' : 'none'; document.getElementById('cross').style.display = phoneMode ? 'none' : 'block';
  resize();
}

// ---- HUD ------------------------------------------------------------------------------------------------------------
function toast(msg, ms = 3200) {
  const el = document.getElementById('toast'); el.textContent = msg; el.style.opacity = 1;
  clearTimeout(toast.t); toast.t = setTimeout(() => { el.style.opacity = 0; }, ms);
}
document.getElementById('help').innerHTML = '<b>Sala 3D: tres mesas con medicamentos</b><br>Clic: capturar el ratón · Esc: soltarlo<br>W A S D: moverse (Mayús: rápido) · ratón: mirar<br>R / F: subir / bajar los ojos<br>X: inclinarse sobre la mesa (sin colisión)<br>1 2 3: ir a la mesa · Mayús + 1 2 3: móvil a 50 cm sobre ella<br>P: sacar el móvil · Espacio: hacer la foto<br>H: ocultar esta ayuda';
function nearestTable() {
  let best = null, dist = 1e9;
  for (const t of world.tables) {
    const dx = Math.max(Math.abs(player.x - t.x) - t.w / 2, 0), dz = Math.max(Math.abs(player.z - t.z) - t.d / 2, 0), dy = player.eye - t.h;
    const d = Math.hypot(dx, dz, dy);
    if (d < dist) { dist = d; best = t; }
  }
  return { table: best, dist };
}
function hud() {
  const { table, dist } = nearestTable();
  document.getElementById('info').innerHTML = `${table.name}: ${(dist * 100).toFixed(0)} cm de la mesa<br>${phoneMode ? 'móvil' : 'vista normal'}`;
  const hint = document.getElementById('hint');
  hint.style.display = phoneMode ? 'block' : 'none';
  hint.textContent = dist > 0.55 ? `Acércate a 50 cm o menos para que el código se lea (ahora ${(dist * 100).toFixed(0)} cm)` : 'Distancia buena. Espacio para hacer la foto';
}

// ---- photo ----------------------------------------------------------------------------------------------------------
const raycaster = new THREE.Raycaster();
const alphaCache = new Map();
// A cut-out is a rectangle with transparent corners: a ray must ignore the transparent pixels, or a box would 'hide' a label next to it.
function alphaAt(mesh, uv) {
  const img = mesh.material.map?.image;
  if (!img || !img.width || !mesh.material.transparent || !uv) return 1;
  let a = alphaCache.get(img);
  if (!a) {
    const c = document.createElement('canvas'); c.width = Math.min(img.width, 256); c.height = Math.min(img.height, 256);
    const g = c.getContext('2d', { willReadFrequently: true }); g.drawImage(img, 0, 0, c.width, c.height); a = { c, g }; alphaCache.set(img, a);
  }
  const x = Math.min(a.c.width - 1, Math.max(0, Math.floor(uv.x * a.c.width))), y = Math.min(a.c.height - 1, Math.max(0, Math.floor((1 - uv.y) * a.c.height)));
  return a.g.getImageData(x, y, 1, 1).data[3] / 255;
}
function firstOpaqueHit(origin, target) {
  raycaster.set(origin, target.clone().sub(origin).normalize());
  return raycaster.intersectObjects(pickables, false).find(h => alphaAt(h.object, h.uv) >= 0.4) ?? null;
}
function project(v) {
  const p = v.clone().applyMatrix4(phoneCam.matrixWorldInverse);
  const behind = p.z >= 0;
  const n = v.clone().project(phoneCam);
  return { x: (n.x * 0.5 + 0.5) * PHONE.w, y: (1 - (n.y * 0.5 + 0.5)) * PHONE.h, behind };
}
// Share of four sample points inside a plane that the camera sees (aiming at the exact centre can slip between the two triangles of the quad).
function visibleShare(mesh, w, h, origin) {
  let n = 0;
  for (const [fx, fy] of [[-0.25, -0.25], [0.25, -0.25], [-0.25, 0.25], [0.25, 0.25]]) {
    const hit = firstOpaqueHit(origin, mesh.localToWorld(new THREE.Vector3(fx * w, fy * h, 0)));
    if (hit && hit.object === mesh) n++;
  }
  return n / 4;
}
function truthForPhoto() {
  const out = { labels: [], boxes_without_code: [] };
  const inFrame = p => !p.behind && p.x > 0 && p.x < PHONE.w && p.y > 0 && p.y < PHONE.h;
  const origin = phoneCam.position.clone();
  for (const e of labelMeshes) {
    const c = e.mesh.getWorldPosition(new THREE.Vector3());
    const right = new THREE.Vector3(1, 0, 0).applyQuaternion(e.mesh.getWorldQuaternion(new THREE.Quaternion())).multiplyScalar(e.item.label.size / 2);
    const fwd = new THREE.Vector3(0, 1, 0).applyQuaternion(e.mesh.getWorldQuaternion(new THREE.Quaternion()));   // plane normal (rotated -90 deg about x, so +z local = up)
    const corners = [c.clone().add(right), c.clone().sub(right)].map(project);
    const centre = project(c);
    if (!inFrame(centre) || !corners.every(inFrame)) continue;
    if (visibleShare(e.mesh, e.item.label.size, e.item.label.size, origin) < 0.75) continue;   // something else is on top of it
    const widthPx = Math.hypot(corners[0].x - corners[1].x, corners[0].y - corners[1].y);
    const modules = (e.mesh.material.map.image?.width ?? 448) / 16;      // symbol plus its 2-module quiet zone on each side
    out.labels.push({ cn7: e.item.cn7, text: e.item.label.text, name: e.item.name, case: e.item.case, nregistro: e.item.nregistro,
      px: [Math.round(centre.x), Math.round(centre.y)], px_per_module: +(widthPx / modules).toFixed(2) });
  }
  for (const e of boxEntries) {
    const c = e.mesh.getWorldPosition(new THREE.Vector3());
    const p = project(c);
    if (!inFrame(p)) continue;
    if (visibleShare(e.mesh, e.item.w * 0.5, e.item.h * 0.5, origin) >= 0.5) out.boxes_without_code.push({ cn: e.item.cn, name: e.item.name, nregistro: e.item.nregistro, px: [Math.round(p.x), Math.round(p.y)] });
  }
  return out;
}
let shooting = false;
async function shoot(options = {}) {
  if (shooting) return null;
  shooting = true;
  try {
    applyCamera();                                   // the render loop pauses in hidden tabs: always read the player's pose
    const effects = options.effects ?? document.getElementById('effects').checked;
    const size = renderer.getSize(new THREE.Vector2()), ratio = renderer.getPixelRatio();
    phoneCam.position.copy(camera.position); phoneCam.quaternion.copy(camera.quaternion);
    phoneCam.updateMatrixWorld(true); phoneCam.updateProjectionMatrix();
    renderer.setPixelRatio(1); renderer.setSize(PHONE.w, PHONE.h, false);
    renderer.render(scene, phoneCam);
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.93));
    renderer.setPixelRatio(ratio); renderer.setSize(size.x, size.y, false);
    const { table, dist } = nearestTable();
    const truth = { ...truthForPhoto(), table: table.id, distance_m: +dist.toFixed(3), effects, today: world.today,
      pose: { x: player.x, y: player.eye, z: player.z, yaw: player.yaw, pitch: player.pitch }, size: [PHONE.w, PHONE.h] };
    const reply = await fetch('/photo', { method: 'POST', body: blob, headers: { 'Content-Type': 'image/jpeg', 'X-Truth': encodeURIComponent(JSON.stringify(truth)), 'X-Effects': effects ? '1' : '0' } });
    const saved = await reply.json();
    toast(`Foto guardada (${truth.labels.length} códigos a la vista): ${saved.name}. Ya está lista en la app.`, 5000);
    return { ...saved, truth };
  } catch (error) {
    toast(`No se pudo guardar la foto: ${error}`, 6000);
    return null;
  } finally {
    shooting = false;
  }
}

// ---- loop -----------------------------------------------------------------------------------------------------------
let last = performance.now();
function frame(now) {
  const dt = Math.min((now - last) / 1000, 0.1); last = now;
  move(dt); applyCamera(); hud();
  renderer.render(scene, camera);
  requestAnimationFrame(frame);
}
resize(); document.getElementById('frame').style.display = 'none'; applyCamera();
requestAnimationFrame(frame);
toast('Pulsa H para ocultar la ayuda. Clic para mirar con el ratón.', 4500);

window.__world = {
  world, shoot, THREE, camera, phoneCam, pickables, labelMeshes, raycaster,
  // A batch of photos from random viewpoints above the tables (seeded): heights [min, max] metres above the table top, tilt up to maxTilt degrees.
  async batch(n, seed = 1, opts = {}) {
    let s = seed;
    const rnd = () => { s |= 0; s = s + 0x6D2B79F5 | 0; let t = Math.imul(s ^ s >>> 15, 1 | s); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
    const [hmin, hmax] = opts.heights ?? [0.3, 0.9];
    const results = [];
    for (let i = 0; i < n; i++) {
      const t = world.tables[Math.floor(rnd() * world.tables.length)];
      const h = hmin + rnd() * (hmax - hmin), tilt = rnd() * THREE.MathUtils.degToRad(opts.maxTilt ?? 25);
      Object.assign(player, { x: t.x + (rnd() - 0.5) * 0.7, z: t.z + (rnd() - 0.5) * 0.3, eye: t.h + h, yaw: rnd() * Math.PI * 2, pitch: -Math.PI / 2 + tilt });
      lean = true; phoneMode = true;
      const r = await shoot({ effects: opts.effects ?? true });
      if (r) results.push({ name: r.name, h: +h.toFixed(2), tilt: +(tilt * 180 / Math.PI).toFixed(1), labels: r.truth.labels.length });
    }
    return results;
  },
  syncPhone() { applyCamera(); phoneCam.position.copy(camera.position); phoneCam.quaternion.copy(camera.quaternion); phoneCam.updateMatrixWorld(true); phoneCam.updateProjectionMatrix(); },
  truth() { this.syncPhone(); return truthForPhoto(); },
  why(cn7) {   // debugging: why is this label (not) counted as in view from the current pose?
    this.syncPhone();
    const e = labelMeshes.find(l => l.item.cn7 === cn7); if (!e) return 'no such label';
    const c = e.mesh.getWorldPosition(new THREE.Vector3()); const p = project(c);
    const hit = firstOpaqueHit(phoneCam.position, c);
    const kind = o => o === e.mesh ? 'itself' : (o ? (labelMeshes.find(l => l.mesh === o) ? 'other sticker' : 'cutout ' + (o.material.map.image?.src.split('/').pop())) : 'nothing');
    const right = new THREE.Vector3(1, 0, 0).applyQuaternion(e.mesh.getWorldQuaternion(new THREE.Quaternion())).multiplyScalar(e.item.label.size / 2);
    const cs = [c.clone().add(right), c.clone().sub(right)].map(project);
    return JSON.stringify({ centre: [Math.round(p.x), Math.round(p.y)], behind: p.behind, corners: cs.map(q => [Math.round(q.x), Math.round(q.y)]), firstHit: kind(hit?.object), name: e.item.name.slice(0, 24) });
  },
  project(x, y, z) { this.syncPhone(); const p = project(new THREE.Vector3(x, y, z)); return [p.x, p.y, p.behind]; },
  setPose(x, y, z, yaw, pitch, phone = true) { Object.assign(player, { x, z, eye: y, yaw, pitch }); lean = true; phoneMode = phone; document.getElementById('frame').style.display = phone ? 'block' : 'none'; resize(); applyCamera(); },
};
