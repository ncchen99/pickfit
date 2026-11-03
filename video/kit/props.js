// Things in the fitting room: paper cards (your request, Fitz's answer, tickets), the measuring
// tape, the running stitch, and a floating screen for real recordings.

import * as THREE from 'three';
import { canvasTexture } from './stage.js';
import { site, fonts } from './tokens.js';

// A card outline: 4px-style rounded corners, and optionally the cut top-right corner of the
// two conversation surfaces (your request, Fitz's answer).
function cardShape(w, h, cut, r = 0.035) {
  const s = new THREE.Shape();
  const x0 = -w / 2, y0 = -h / 2, x1 = w / 2, y1 = h / 2;
  s.moveTo(x0 + r, y0);
  s.lineTo(x1 - r, y0);
  s.quadraticCurveTo(x1, y0, x1, y0 + r);
  if (cut) {
    s.lineTo(x1, y1 - cut);
    s.lineTo(x1 - cut, y1);
  } else {
    s.lineTo(x1, y1 - r);
    s.quadraticCurveTo(x1, y1, x1 - r, y1);
  }
  s.lineTo(x0 + r, y1);
  s.quadraticCurveTo(x0, y1, x0, y1 - r);
  s.lineTo(x0, y0 + r);
  s.quadraticCurveTo(x0, y0, x0 + r, y0);
  return s;
}

// Canvas path of the same outline, in pixels (for borders printed on the face).
export function cardPath(ctx, w, h, cut, r = 7, inset = 0) {
  const x0 = inset, y0 = inset, x1 = w - inset, y1 = h - inset;
  ctx.beginPath();
  ctx.moveTo(x0 + r, y0);
  if (cut) {
    ctx.lineTo(x1 - cut, y0);
    ctx.lineTo(x1, y0 + cut);
  } else {
    ctx.lineTo(x1 - r, y0);
    ctx.quadraticCurveTo(x1, y0, x1, y0 + r);
  }
  ctx.lineTo(x1, y1 - r);
  ctx.quadraticCurveTo(x1, y1, x1 - r, y1);
  ctx.lineTo(x0 + r, y1);
  ctx.quadraticCurveTo(x0, y1, x0, y1 - r);
  ctx.lineTo(x0, y0 + r);
  ctx.quadraticCurveTo(x0, y0, x0 + r, y0);
  ctx.closePath();
}

// A paper card standing up (face toward +z). draw(ctx, pw, ph) prints on its face, where
// pw x ph is the face in pixels (ppu pixels per unit).
export function paperCard({ w = 3, h = 1, depth = 0.025, cut = 0, color = site.raised, edge = null, edgeWidth = 4, draw = null, ppu = 360 } = {}) {
  const shape = cardShape(w, h, cut ? cut : 0);
  const geo = new THREE.ExtrudeGeometry(shape, { depth, bevelEnabled: true, bevelThickness: 0.004, bevelSize: 0.004, bevelSegments: 2, curveSegments: 6 });
  // face UVs span the card
  const pos = geo.attributes.position, uv = geo.attributes.uv;
  for (let i = 0; i < pos.count; i++) uv.setXY(i, (pos.getX(i) + w / 2) / w, (pos.getY(i) + h / 2) / h);
  geo.translate(0, 0, -depth);
  const pw = Math.round(w * ppu), ph = Math.round(h * ppu);
  const cutPx = cut * ppu;
  const tex = canvasTexture(pw, ph, (ctx) => {
    ctx.fillStyle = color; ctx.fillRect(0, 0, pw, ph);
    if (draw) draw(ctx, pw, ph);
    if (edge) { ctx.strokeStyle = edge; ctx.lineWidth = edgeWidth; cardPath(ctx, pw, ph, cutPx, 7, edgeWidth / 2); ctx.stroke(); }
  });
  const face = new THREE.MeshStandardMaterial({ map: tex, roughness: 0.92, metalness: 0 });
  const side = new THREE.MeshStandardMaterial({ color, roughness: 0.92 });
  const mesh = new THREE.Mesh(geo, [face, side]);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  mesh.userData = { tex, pw, ph, redraw: (fn) => tex.userData.redraw((ctx) => { ctx.fillStyle = color; ctx.fillRect(0, 0, pw, ph); fn(ctx, pw, ph); if (edge) { ctx.strokeStyle = edge; ctx.lineWidth = edgeWidth; cardPath(ctx, pw, ph, cutPx, 7, edgeWidth / 2); ctx.stroke(); } }) };
  return mesh;
}

// Text helpers for printing on cards.
export function text(ctx, str, x, y, { size = 40, weight = 400, family = fonts.sans, color = site.ink, align = 'left', baseline = 'alphabetic', tracking = 0 } = {}) {
  ctx.font = `${weight} ${size}px ${family}`;
  ctx.fillStyle = color;
  ctx.textAlign = align;
  ctx.textBaseline = baseline;
  if ('letterSpacing' in ctx) ctx.letterSpacing = `${tracking}px`;
  ctx.fillText(str, x, y);
  return ctx.measureText(str).width;
}

// The measuring tape printed flat: yellow with ink ticks, as under the request field.
export function drawTape(ctx, x, y, w, h, { ticks = true, color = site.tape, tick = site.tapeInk } = {}) {
  ctx.fillStyle = color; ctx.fillRect(x, y, w, h);
  if (!ticks) return;
  ctx.fillStyle = tick;
  const step = h * 0.55;
  for (let i = 0, px = x + step / 2; px < x + w; i++, px += step) ctx.fillRect(px, y, Math.max(1.5, h * 0.06), i % 5 === 0 ? h * 0.55 : h * 0.3);
}

// The running stitch printed flat (the seam on a verified ticket).
export function drawSeam(ctx, x, y, w, { len = 22, gap = 14, width = 5, color = site.stitch } = {}) {
  ctx.strokeStyle = color; ctx.lineWidth = width; ctx.lineCap = 'round';
  ctx.beginPath();
  for (let px = x; px < x + w - len / 2; px += len + gap) { ctx.moveTo(px, y); ctx.lineTo(Math.min(px + len, x + w), y); }
  ctx.stroke();
}

// The measurement sheet: label, dotted leader, value.
export function drawMeasure(ctx, rows, x, y, w, { size = 26, gap = 46, valueColor = site.ink } = {}) {
  rows.forEach(([label, value, tone], i) => {
    const yy = y + i * gap;
    const lw = text(ctx, label, x, yy, { size, color: site.ink3 });
    ctx.font = `500 ${size}px ${fonts.sans}`;
    const vw = ctx.measureText(value).width;
    ctx.fillStyle = site.lineCtl;
    for (let px = x + lw + 12; px < x + w - vw - 12; px += 9) ctx.fillRect(px, yy - 3, 3, 3);
    text(ctx, value, x + w, yy, { size, weight: 500, align: 'right', color: tone || valueColor });
  });
}

// A running stitch in 3D along a curve: short thread capsules, the gaps are where it goes under.
// progress 0..1 sews it in from the start.
export function stitchThread(curve, { stitch = 0.09, gap = 0.06, radius = 0.011, color = site.stitch } = {}) {
  const length = curve.getLength();
  const n = Math.floor(length / (stitch + gap));
  const geo = new THREE.CapsuleGeometry(radius, stitch - 2 * radius, 4, 8);
  geo.rotateZ(Math.PI / 2); // along +x
  const mat = new THREE.MeshPhysicalMaterial({ color, roughness: 0.55, sheen: 0.6, sheenColor: new THREE.Color('#ffd9c8') });
  const mesh = new THREE.InstancedMesh(geo, mat, n);
  mesh.castShadow = true;
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3(1, 1, 1), x = new THREE.Vector3(1, 0, 0);
  const mats = [];
  for (let i = 0; i < n; i++) {
    const u = ((i * (stitch + gap)) + stitch / 2) / length;
    const p = curve.getPointAt(u), t = curve.getTangentAt(u);
    q.setFromUnitVectors(x, t);
    m.compose(p, q, s);
    mats.push(m.clone());
    mesh.setMatrixAt(i, m);
  }
  mesh.userData.progress = (v) => {
    const shown = Math.round(n * Math.min(1, Math.max(0, v)));
    mesh.count = shown;
  };
  return mesh;
}

// A floating screen for a real recording: a dark-framed slab whose face shows a texture
// (an image sequence or a video frame drawn in by the scene).
export function screenPanel({ w = 3.2, h = 1.8, bezel = 0.03, depth = 0.04 } = {}) {
  const grp = new THREE.Group();
  const back = new THREE.Mesh(new THREE.BoxGeometry(w + bezel * 2, h + bezel * 2, depth), new THREE.MeshStandardMaterial({ color: '#1b1c19', roughness: 0.6 }));
  back.position.z = -depth / 2;
  back.castShadow = true;
  const face = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: '#ffffff', toneMapped: false }));
  face.position.z = 0.001;
  grp.add(back, face);
  grp.userData.face = face;
  return grp;
}
