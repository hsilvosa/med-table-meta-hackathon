// Shared by the 3D room (main.js) and the camera page (camera.js): draw what the live scan found, and read the staged answer of /scan.
// Nothing here identifies a medicine. The boxes come from the server, which runs the same decoder and checks as the planner.

const GREEN = '#22c55e', AMBER = '#f59e0b', INK = '#10151a';

// Draw the boxes on `canvas` (already sized to the picture it covers). `srcWidth` is the width in pixels of the frame the server looked at.
// `state` = { boxes, nocode, born: Map }. Returns true while a box is still settling (the caller redraws on the next animation frame).
export function drawScan(canvas, srcWidth, state, noCodeText, fontPx = 13) {
  const g = canvas.getContext('2d'), k = canvas.width / srcWidth;
  g.clearRect(0, 0, canvas.width, canvas.height);
  g.font = `700 ${fontPx}px "Atkinson Hyperlegible", system-ui, sans-serif`; g.textBaseline = 'bottom';
  const bar = Math.round(fontPx * 1.6), now = performance.now();
  const pill = (x, y, w, h, color) => { g.fillStyle = color; g.beginPath(); g.roundRect ? g.roundRect(x, y, w, h, 5) : g.rect(x, y, w, h); g.fill(); };
  let animating = false;
  const taken = [];        // labels already drawn: a label that would cover one moves below its box, then further down, so every name stays readable
  const place = (x, y, w, h, below) => {
    const hits = (yy) => taken.some(r => x < r[0] + r[2] && x + w > r[0] && yy < r[1] + r[3] && yy + h > r[1]);
    let yy = y;
    if (hits(yy)) yy = below;
    while (hits(yy) && yy < canvas.height) yy += h + 2;
    taken.push([x, yy, w, h]);
    return yy;
  };
  for (const code of state.boxes) {
    const [x0, y0, x1, y1] = code.bbox;
    const id = `${Math.round((x0 + x1) / 160)},${Math.round((y0 + y1) / 160)}`;      // the same code keeps its id between stages (cells of 80 px)
    if (!state.born.has(id)) state.born.set(id, now);
    const age = now - state.born.get(id), pop = Math.max(0, 1 - age / 350);         // a box that has just been found starts big and settles in 0.35 s
    if (pop > 0) animating = true;
    const cx = (x0 + x1) / 2 * k, cy = (y0 + y1) / 2 * k, half = (Math.max((x1 - x0) * k, (y1 - y0) * k, 18) / 2 + 4) * (1 + 0.8 * pop);      // never smaller than a fingertip
    const ok = code.status === 'verified', color = ok ? GREEN : AMBER;
    g.lineWidth = 3 + 3 * pop; g.strokeStyle = color; g.beginPath(); g.roundRect ? g.roundRect(cx - half, cy - half, half * 2, half * 2, 6) : g.rect(cx - half, cy - half, half * 2, half * 2); g.stroke();
    const label = ok ? 'Recognised: ' + (code.name || '').split(' ')[0].toLowerCase().replace(/^./, s => s.toUpperCase()) + (code.expired ? ' (EXPIRED)' : '') : 'Not verified';
    const w = g.measureText(label).width + 14, lx = Math.min(Math.max(cx - half, 0), Math.max(canvas.width - w, 0));     // kept inside the picture
    const ly = Math.max(place(lx, cy - half - bar, w, bar, cy + half), 0);
    pill(lx, ly, w, bar, color);
    g.fillStyle = INK; g.fillText(label, lx + 7, ly + bar - 4);
  }
  for (const [x0, y0, x1, y1] of state.nocode) {      // a pack was seen here and no code was read from it
    const left = x0 * k, top = y0 * k, wide = (x1 - x0) * k, high = (y1 - y0) * k;
    g.lineWidth = 3; g.strokeStyle = AMBER; g.setLineDash([9, 6]); g.strokeRect(left, top, wide, high); g.setLineDash([]);
    const w = g.measureText(noCodeText).width + 14;
    const lx = Math.min(Math.max(left, 0), Math.max(canvas.width - w, 0)), ly = place(lx, top > bar + 3 ? top - bar : top + high, w, bar, top + high);
    pill(lx, ly, w, bar, AMBER); g.fillStyle = INK; g.fillText(noCodeText, lx + 7, ly + bar - 4);
  }
  return animating;
}

// Read the answer of /scan: one JSON line per stage, sent as soon as it is ready. `onStage(stage)` is called for each;
// `aborted()` is checked before each one: when it is true the rest is dropped (the camera moved, the boxes would be in the wrong place).
export async function readStages(reply, onStage, aborted) {
  const reader = reply.body.getReader(), decoder = new TextDecoder();
  let pending = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return true;
    pending += decoder.decode(value, { stream: true });
    const lines = pending.split(String.fromCharCode(10)); pending = lines.pop();
    for (const line of lines.filter(Boolean)) {
      if (aborted()) { reader.cancel(); return false; }
      onStage(JSON.parse(line));
    }
  }
}
