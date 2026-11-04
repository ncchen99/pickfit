// Props for the finale (the maker at the other end of the thread, the Next plan, the end card).
// Everything here is built once; the scene poses it from t.

import * as THREE from 'three';
import { gsap } from 'gsap';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { canvasTexture } from '../../kit/stage.js';
import { paperCard, text, drawTape, drawSeam, cardPath, cornerPx } from '../../kit/props.js';
import { site, fonts, fitz as FC } from '../../kit/tokens.js';

// ---- time helpers -------------------------------------------------------------------------

export const E = {
  out: gsap.parseEase('expo.out'),
  io: gsap.parseEase('power3.inOut'),
  sine: gsap.parseEase('sine.inOut'),
  p2out: gsap.parseEase('power2.out'),
  p2io: gsap.parseEase('power2.inOut'),
  back: gsap.parseEase('back.out(1.6)'),
};
export const clamp01 = (v) => Math.min(1, Math.max(0, v));
export const prog = (t, a, b, e = E.io) => e(clamp01((t - a) / (b - a)));
export const lerp = (a, b, v) => a + (b - a) * v;

export function rng(seed) {
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let x = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    x = (x + Math.imul(x ^ (x >>> 7), 61 | x)) ^ x;
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
}

// Fade a whole object (dims an older layer, or brings a new one in).
export function setOpacity(obj, v) {
  obj.visible = v > 0.003;
  obj.traverse((o) => {
    if (!o.material) return;
    const mats = Array.isArray(o.material) ? o.material : [o.material];
    for (const m of mats) {
      if (m.userData.base === undefined) m.userData.base = m.opacity;
      if (!m.userData.alwaysTransparent) {
        const want = v < 0.999;
        if (m.transparent !== want) { m.transparent = want; m.needsUpdate = true; }
      }
      m.opacity = m.userData.base * v;
    }
  });
}

export function noShadows(obj) {
  obj.traverse((o) => { if (o.isMesh) { o.castShadow = false; o.receiveShadow = false; } });
  return obj;
}

// ---- canvas helpers -----------------------------------------------------------------------

const measureCtx = document.createElement('canvas').getContext('2d');
export function measure(str, { size = 40, weight = 400, family = fonts.sans, tracking = 0 } = {}) {
  measureCtx.font = `${weight} ${size}px ${family}`;
  if ('letterSpacing' in measureCtx) measureCtx.letterSpacing = `${tracking}px`;
  return measureCtx.measureText(str);
}

export function rrect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function bar(ctx, x, y, w, h, color) {
  ctx.fillStyle = color;
  rrect(ctx, x, y, w, h, h / 2);
  ctx.fill();
}

// A small green tick, as the site's pass mark.
export function drawTick(ctx, x, y, s, color = site.pass, width = null) {
  ctx.strokeStyle = color;
  ctx.lineWidth = width ?? s * 0.18;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.beginPath();
  ctx.moveTo(x - s * 0.42, y + s * 0.02);
  ctx.lineTo(x - s * 0.12, y + s * 0.32);
  ctx.lineTo(x + s * 0.45, y - s * 0.3);
  ctx.stroke();
}

// A flat print on a surface (words printed on the paper or on a card): unlit ink, no depth write.
export function decal(w, h, draw, { ppu = 400, scale = 2 } = {}) {
  const pw = Math.round(w * ppu), ph = Math.round(h * ppu);
  const tex = canvasTexture(pw, ph, (ctx) => draw(ctx, pw, ph), { scale });
  const mat = new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false, toneMapped: false, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4 });
  mat.userData.alwaysTransparent = true;
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(w, h), mat);
  mesh.renderOrder = 2;
  mesh.userData = { pw, ph, tex };
  return mesh;
}

// ---- source tags --------------------------------------------------------------------------

// A plain paper tag with a punched hole, standing on a hinge at its bottom edge (pop-up book).
export function sourceTag(label, { size = 60, h = 0.42, ppu = 360 } = {}) {
  const tw = measure(label, { size, weight: 500 }).width;
  const w = (tw + 120) / ppu;
  const card = paperCard({ w, h, color: site.raised, edge: site.rule, edgeWidth: 3, ppu, draw: (ctx, pw, ph) => {
    ctx.fillStyle = site.room;
    ctx.strokeStyle = site.lineCtl;
    ctx.lineWidth = 3;
    ctx.beginPath(); ctx.arc(38, ph / 2, 11, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    text(ctx, label, 72, ph / 2 + size * 0.36, { size, weight: 500, color: site.ink });
  } });
  card.position.y = h / 2;
  const pivot = new THREE.Group();
  pivot.add(card);
  return { pivot, card, w, h };
}

// ---- the maker's corner -------------------------------------------------------------------

function clayMat(color = '#FBFAF6') {
  return new THREE.MeshPhysicalMaterial({ color, roughness: 0.74, metalness: 0, sheen: 0.12, sheenRoughness: 0.8, sheenColor: new THREE.Color('#ffffff') });
}
function rbox(w, h, d, mat, r = 0.02) {
  const m = new THREE.Mesh(new RoundedBoxGeometry(w, h, d, 3, Math.min(r, w / 2.01, h / 2.01, d / 2.01)), mat);
  m.castShadow = true;
  m.receiveShadow = true;
  return m;
}

// A small clay workbench with an empty chair pulled out: someone works here (nobody is drawn).
export function workbench() {
  const g = new THREE.Group();
  const mat = clayMat('#FCFBF7');
  const top = rbox(1.7, 0.07, 0.78, mat, 0.03);
  top.position.y = 0.76;
  g.add(top);
  for (const [x, z] of [[-0.78, -0.33], [0.78, -0.33], [-0.78, 0.33], [0.78, 0.33]]) {
    const leg = rbox(0.06, 0.74, 0.06, mat, 0.02);
    leg.position.set(x, 0.37, z);
    g.add(leg);
  }
  // a closed laptop and a mug
  const lap = rbox(0.56, 0.03, 0.38, clayMat('#EEEFEA'), 0.012);
  lap.position.set(-0.25, 0.81, 0.02);
  lap.rotation.y = 0.12;
  g.add(lap);
  const mug = new THREE.Mesh(new THREE.CylinderGeometry(0.065, 0.06, 0.13, 24), mat);
  mug.position.set(0.48, 0.86, 0.08);
  mug.castShadow = true;
  const handle = new THREE.Mesh(new THREE.TorusGeometry(0.035, 0.011, 8, 16), mat);
  handle.position.set(0.55, 0.86, 0.08);
  handle.castShadow = true;
  g.add(mug, handle);

  const chair = new THREE.Group();
  const seat = rbox(0.5, 0.05, 0.48, mat, 0.02);
  seat.position.y = 0.46;
  const back = rbox(0.5, 0.48, 0.05, mat, 0.02);
  back.position.set(0, 0.72, -0.23);
  chair.add(seat, back);
  for (const [x, z] of [[-0.21, -0.2], [0.21, -0.2], [-0.21, 0.2], [0.21, 0.2]]) {
    const leg = rbox(0.045, 0.44, 0.045, mat, 0.015);
    leg.position.set(x, 0.22, z);
    chair.add(leg);
  }
  g.add(chair);
  return { group: g, chair };
}

// The maker's card: the public repo and its release list (public information only).
export function makerCard({ url, releases }) {
  const w = 2.9, h = 1.62;
  const card = paperCard({ w, h, color: site.raised, edge: site.rule, edgeWidth: 4, ppu: 360, draw: (ctx, pw, ph) => {
    // a small repo glyph: a book outline
    ctx.strokeStyle = site.ink2; ctx.lineWidth = 4; ctx.lineJoin = 'round';
    rrect(ctx, 40, 40, 34, 44, 4); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(48, 40); ctx.lineTo(48, 84); ctx.stroke();
    text(ctx, url, 92, 76, { size: 46, weight: 500, family: fonts.mono, color: site.ink });
    ctx.fillStyle = site.rule; ctx.fillRect(40, 116, pw - 80, 3);
    text(ctx, 'Releases', 40, 178, { size: 32, weight: 600, color: site.ink3 });
    releases.forEach((v, i) => {
      const y = 250 + i * 72;
      // a release tag glyph
      ctx.fillStyle = site.sunk; ctx.strokeStyle = site.lineCtl; ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(44, y - 30); ctx.lineTo(74, y - 30); ctx.lineTo(90, y - 15); ctx.lineTo(74, y); ctx.lineTo(44, y); ctx.closePath();
      ctx.fill(); ctx.stroke();
      text(ctx, v, 112, y - 2, { size: 40, weight: i === 0 ? 600 : 400, family: fonts.mono, color: i === 0 ? site.ink : site.ink2 });
      bar(ctx, 330, y - 22, (pw - 380) * (0.62 - i * 0.13), 14, '#ECEDE7');
    });
    text(ctx, '…', 112, 250 + releases.length * 72 - 14, { size: 40, color: site.ink3 });
  } });
  return { card, w, h };
}

// ---- the Next plan ------------------------------------------------------------------------

// The label that says this part is the plan: dashed outline = not built yet.
export function nextTag() {
  const w = 2.25, h = 0.66;
  let sub = '';
  const draw = (ctx, pw, ph) => {
    ctx.fillStyle = site.raised; ctx.fillRect(0, 0, pw, ph);
    ctx.setLineDash([16, 12]);
    ctx.strokeStyle = site.ink3; ctx.lineWidth = 4;
    cardPath(ctx, pw, ph, 0, cornerPx(360, 6), 6); ctx.stroke();
    ctx.setLineDash([]);
    text(ctx, 'Next', 40, 104, { size: 92, weight: 700, family: fonts.display, color: site.ink });
    // a small arrow after the word
    const nw = measure('Next', { size: 92, weight: 700, family: fonts.display }).width;
    ctx.strokeStyle = site.ink; ctx.lineWidth = 7; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    const ax = 40 + nw + 30, ay = 74;
    ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(ax + 52, ay); ctx.moveTo(ax + 32, ay - 20); ctx.lineTo(ax + 52, ay); ctx.lineTo(ax + 32, ay + 20); ctx.stroke();
    text(ctx, sub, 42, 186, { size: 40, weight: 500, color: site.ink2 });
  };
  const card = paperCard({ w, h, color: site.raised, ppu: 360, draw });
  noShadows(card);
  return {
    card, w, h,
    setSub(s) { if (s !== sub) { sub = s; card.userData.redraw(draw); } },
  };
}

// The call a maker's agent sends: printed like your request (white, ink outline, cut corner).
export function submitCard() {
  const w = 3.5, h = 0.9;
  const card = paperCard({ w, h, cut: 0.12, edge: site.fitzLine, edgeWidth: 7, ppu: 360, draw: (ctx, pw, ph) => {
    text(ctx, 'From your agent', 40, 92, { size: 32, weight: 600, color: site.ink3 });
    const x = 40 + text(ctx, 'submit_software', 40, 190, { size: 50, weight: 700, family: fonts.mono, color: site.ink });
    text(ctx, 'github.com/you/your-app', x + 34, 190, { size: 50, weight: 400, family: fonts.mono, color: site.ink2 });
  } });
  return { card, w, h };
}

// The same card's other side once it has passed: a ticket, with a match meter (the tape).
export function appTicket() {
  const w = 3.5, h = 0.9, ppu = 360;
  const MX = 700, TY = 124, TH = 34;
  const card = paperCard({ w, h, color: site.raised, edge: site.rule, edgeWidth: 4, ppu, draw: (ctx, pw, ph) => {
    text(ctx, 'your-app', 40, 104, { size: 66, weight: 700, family: fonts.display, color: site.ink });
    text(ctx, 'github.com/you/your-app', 42, 158, { size: 30, family: fonts.mono, color: site.ink3 });
    text(ctx, 'match', MX, 100, { size: 30, weight: 600, color: site.ink3 });
    drawTape(ctx, MX, TY, pw - MX - 50, TH);
  } });
  const meter = { x0: MX / ppu - w / 2, y: h / 2 - (TY + TH / 2) / ppu, w: (w * ppu - MX - 50) / ppu, h: TH / ppu };
  return { card, w, h, meter, seamY: h / 2 - 222 / ppu };
}

// A station on the test line: an icon printed on a small square of paper, grey until it lights.
const ICONS = {
  sieve(ctx, s, c) {
    const cx = s / 2, cy = s * 0.44, r = s * 0.3;
    ctx.save();
    ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI); ctx.closePath(); ctx.clip();
    ctx.strokeStyle = c; ctx.lineWidth = s * 0.018;
    for (let k = -6; k <= 6; k++) {
      ctx.beginPath(); ctx.moveTo(cx + k * s * 0.05 - r, cy); ctx.lineTo(cx + k * s * 0.05 + r, cy + 2 * r); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(cx + k * s * 0.05 + r, cy); ctx.lineTo(cx + k * s * 0.05 - r, cy + 2 * r); ctx.stroke();
    }
    ctx.restore();
    ctx.strokeStyle = c; ctx.lineWidth = s * 0.04; ctx.lineCap = 'round';
    ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(cx - r - s * 0.03, cy); ctx.lineTo(cx + r + s * 0.03, cy); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(cx + r + s * 0.03, cy); ctx.lineTo(cx + r + s * 0.15, cy - s * 0.08); ctx.stroke();
    ctx.fillStyle = c;
    for (const [dx, dy] of [[-0.06, 0.82], [0.03, 0.88], [0.1, 0.8]]) { ctx.beginPath(); ctx.arc(cx + dx * s, dy * s, s * 0.018, 0, Math.PI * 2); ctx.fill(); }
  },
  readme(ctx, s, c) {
    const x = s * 0.27, y = s * 0.16, w = s * 0.46, h = s * 0.62, f = s * 0.12;
    ctx.strokeStyle = c; ctx.lineWidth = s * 0.035; ctx.lineJoin = 'round';
    ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + w - f, y); ctx.lineTo(x + w, y + f); ctx.lineTo(x + w, y + h); ctx.lineTo(x, y + h); ctx.closePath(); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x + w - f, y); ctx.lineTo(x + w - f, y + f); ctx.lineTo(x + w, y + f); ctx.stroke();
    ctx.fillStyle = c;
    ctx.font = `700 ${s * 0.085}px ${fonts.mono}`; ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
    if ('letterSpacing' in ctx) ctx.letterSpacing = '0px';
    ctx.fillText('README', x + s * 0.05, y + s * 0.2);
    for (let i = 0; i < 4; i++) ctx.fillRect(x + s * 0.05, y + s * 0.3 + i * s * 0.075, w * (i === 3 ? 0.45 : 0.78), s * 0.025);
  },
  sandbox(ctx, s, c) {
    const x = s * 0.18, y = s * 0.22, w = s * 0.64, h = s * 0.52;
    ctx.strokeStyle = c; ctx.lineWidth = s * 0.035; ctx.lineJoin = 'round';
    rrect(ctx, x, y, w, h, s * 0.04); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x, y + s * 0.11); ctx.lineTo(x + w, y + s * 0.11); ctx.stroke();
    ctx.fillStyle = c;
    for (let i = 0; i < 3; i++) { ctx.beginPath(); ctx.arc(x + s * 0.06 + i * s * 0.055, y + s * 0.055, s * 0.017, 0, Math.PI * 2); ctx.fill(); }
    // a small app box inside
    ctx.lineWidth = s * 0.03;
    ctx.strokeRect(x + w / 2 - s * 0.09, y + s * 0.2, s * 0.18, s * 0.16);
    ctx.beginPath(); ctx.moveTo(x + w / 2 - s * 0.09, y + s * 0.26); ctx.lineTo(x + w / 2 + s * 0.09, y + s * 0.26); ctx.stroke();
  },
  check(ctx, s, c, lit) {
    ctx.strokeStyle = lit ? site.pass : c; ctx.lineWidth = s * 0.04;
    ctx.beginPath(); ctx.arc(s / 2, s * 0.47, s * 0.27, 0, Math.PI * 2); ctx.stroke();
    drawTick(ctx, s / 2, s * 0.47, s * 0.3, lit ? site.pass : c, s * 0.05);
  },
};

export function station(kind) {
  const w = 0.66;
  const draw = (lit) => (ctx, pw, ph) => {
    ctx.fillStyle = site.raised; ctx.fillRect(0, 0, pw, ph);
    ICONS[kind](ctx, pw, lit ? site.ink : '#B9BAB3', lit);
    if (lit && kind !== 'check') {
      ctx.fillStyle = site.pass;
      ctx.beginPath(); ctx.arc(pw - 40, 40, 22, 0, Math.PI * 2); ctx.fill();
      drawTick(ctx, pw - 40, 40, 22, '#FFFFFF', 5);
    }
    ctx.strokeStyle = lit ? site.lineCtl : site.rule; ctx.lineWidth = 3; cardPath(ctx, pw, ph, 0, cornerPx(360, 1.5), 1.5); ctx.stroke();
  };
  const card = paperCard({ w, h: w, color: site.raised, ppu: 360, draw: draw(false) });
  const base = card.userData.tex;
  const pw = card.userData.pw;
  const litTex = canvasTexture(pw, pw, draw(true));
  let state = false;
  return {
    card, w,
    setLit(v) { if (v !== state) { state = v; card.material[0].map = v ? litTex : base; } },
  };
}

// A report slip coming back from an agent: words right-aligned so they show when filed behind
// the ticket's edge like an index tab.
export function slip(label) {
  const w = 1.25, h = 0.28;
  const card = paperCard({ w, h, color: site.raised, edge: site.rule, edgeWidth: 3, ppu: 360, draw: (ctx, pw, ph) => {
    const tw = measure(label, { size: 38, weight: 500 }).width;
    drawTick(ctx, pw - 44, ph / 2, 28);
    text(ctx, label, pw - 80 - tw, ph / 2 + 13, { size: 38, weight: 500, color: site.ink });
  } });
  return { card, w, h };
}

// A small paper tag that tells the real time, as the corner clock in the recordings: a face
// with a ticking second hand, and the time in mono whose colon blinks while it runs.
export function clockTag(label) {
  const size = 50;
  const tw = measure(label, { size, weight: 600, family: fonts.mono }).width;
  const ppu = 360, h = 0.42;
  const w = (tw + 170) / ppu;
  const r = 0.115; // clock face radius, units
  const [hh, mm] = label.split(/[: ]/).map(Number);
  const draw = (colon) => (ctx, pw, ph) => {
    const cx = 34 + r * ppu, cy = ph / 2, R = r * ppu;
    ctx.strokeStyle = site.ink; ctx.lineWidth = 4;
    ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.stroke();
    ctx.fillStyle = site.ink3;
    for (let i = 0; i < 12; i++) { const a = (i / 12) * Math.PI * 2; ctx.fillRect(cx + Math.sin(a) * R * 0.78 - 1.5, cy - Math.cos(a) * R * 0.78 - 1.5, 3, 3); }
    ctx.lineCap = 'round'; ctx.strokeStyle = site.ink;
    const ha = (((hh % 12) + mm / 60) / 12) * Math.PI * 2, ma = (mm / 60) * Math.PI * 2;
    ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx + Math.sin(ha) * R * 0.5, cy - Math.cos(ha) * R * 0.5); ctx.stroke();
    ctx.lineWidth = 4; ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx + Math.sin(ma) * R * 0.75, cy - Math.cos(ma) * R * 0.75); ctx.stroke();
    const x0 = 34 + 2 * R + 30, y0 = ph / 2 + size * 0.36, o = { size, weight: 600, family: fonts.mono, color: site.ink };
    const k = label.indexOf(':');
    if (colon || k < 0) { text(ctx, label, x0, y0, o); return; }
    const a = text(ctx, label.slice(0, k), x0, y0, o);
    const c = measure(':', { size, weight: 600, family: fonts.mono }).width;
    text(ctx, label.slice(k + 1), x0 + a + c, y0, o);
  };
  const card = paperCard({ w, h, color: site.raised, edge: site.rule, edgeWidth: 3, ppu, draw: draw(true) });
  const on = card.userData.tex;
  const off = canvasTexture(card.userData.pw, card.userData.ph, (ctx, pw, ph) => {
    ctx.fillStyle = site.raised; ctx.fillRect(0, 0, pw, ph);
    draw(false)(ctx, pw, ph);
    ctx.strokeStyle = site.rule; ctx.lineWidth = 3; cardPath(ctx, pw, ph, 0, cornerPx(ppu, 1.5), 1.5); ctx.stroke();
  });
  let colonOn = true;
  // the second hand, a thin ink needle over the printed face
  const hand = new THREE.Mesh(new THREE.BoxGeometry(0.008, r * 0.92, 0.004), new THREE.MeshStandardMaterial({ color: site.ink2, roughness: 0.5 }));
  hand.geometry.translate(0, r * 0.36, 0);
  const pin = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, 0.006, 16), new THREE.MeshStandardMaterial({ color: site.ink, roughness: 0.5 }));
  pin.rotation.x = Math.PI / 2;
  const hub = new THREE.Group();
  hub.position.set(-w / 2 + (34 / ppu) + r, 0, 0.009);
  hub.add(hand, pin);
  card.add(hub);
  return {
    card, w, h, hand,
    setColon(v) { if (v !== colonOn) { colonOn = v; card.material[0].map = v ? on : off; } },
  };
}

// ---- the screens --------------------------------------------------------------------------

// A clean stand-in for a recording frame: a light window, a few grey lines, and a label.
export function placeholderScreen(kind) {
  return canvasTexture(960, 600, (ctx, w, h) => {
    ctx.fillStyle = '#FBFBF9'; ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = '#EEEFEA'; ctx.fillRect(0, 0, w, 44);
    ctx.fillStyle = '#D6D7D1';
    for (let i = 0; i < 3; i++) { ctx.beginPath(); ctx.arc(24 + i * 20, 22, 6, 0, Math.PI * 2); ctx.fill(); }
    text(ctx, kind, w / 2, 29, { size: 18, weight: 600, family: fonts.mono, color: site.ink3, align: 'center' });
    if (kind === 'agent') {
      ctx.fillStyle = '#ECEDE7'; rrect(ctx, w - 470, 84, 410, 64, 18); ctx.fill();
      bar(ctx, w - 440, 108, 300, 14, '#D3D4CE');
      const rows = [0.8, 0.92, 0.7, 0, 0.86, 0.6, 0, 0.9, 0.75, 0.5];
      rows.forEach((v, i) => { if (v) bar(ctx, 70, 196 + i * 30, (w - 260) * v, 13, '#DEDFD9'); });
      ctx.strokeStyle = '#DEDFD9'; ctx.lineWidth = 2; rrect(ctx, 60, h - 92, w - 120, 56, 16); ctx.stroke();
      bar(ctx, 84, h - 70, 220, 12, '#E6E7E1');
    } else {
      ctx.strokeStyle = '#DEDFD9'; ctx.lineWidth = 2; rrect(ctx, 70, 80, w - 140, 58, 6); ctx.stroke();
      bar(ctx, 92, 103, 330, 13, '#D3D4CE');
      ctx.fillStyle = '#F1F6E2'; rrect(ctx, 70, 168, w - 140, 170, 6); ctx.fill();
      ctx.strokeStyle = '#CDD7AB'; ctx.stroke();
      bar(ctx, 96, 196, 260, 22, '#C9D2A9');
      for (let i = 0; i < 3; i++) bar(ctx, 96, 246 + i * 26, (w - 260) * (0.82 - i * 0.12), 11, '#DCE3C4');
      for (let i = 0; i < 4; i++) { bar(ctx, 70, 372 + i * 50, 200, 14, '#DEDFD9'); bar(ctx, 300, 374 + i * 50, (w - 400) * (0.7 - i * 0.1), 10, '#E8E9E3'); }
    }
  });
}

export async function screenTexture(path, kind) {
  try {
    const res = await fetch(path, { cache: 'no-store' });
    if (!res.ok) throw new Error('missing');
    const img = new Image();
    img.src = URL.createObjectURL(await res.blob());
    await img.decode();
    const tex = new THREE.Texture(img);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = 8;
    tex.generateMipmaps = true;
    tex.minFilter = THREE.LinearMipmapLinearFilter;
    tex.needsUpdate = true;
    return tex;
  } catch {
    return placeholderScreen(kind);
  }
}

// ---- Fitz extras --------------------------------------------------------------------------

// Happy closed eyes (the recommending pose's ^ ^), swapped in for a happy blink.
export function happyEyes(fz) {
  const mat = new THREE.MeshStandardMaterial({ color: FC.ink, roughness: 0.45 });
  const arcs = fz.parts.eyes.map((e) => {
    const m = new THREE.Mesh(new THREE.TorusGeometry(0.05, 0.0135, 10, 28, Math.PI), mat);
    m.position.copy(e.position);
    m.quaternion.copy(e.quaternion);
    m.translateY(-0.022);
    m.translateZ(0.006);
    m.scale.set(1, 0.95, 0.6);
    m.visible = false;
    e.parent.add(m);
    return m;
  });
  return (on) => fz.parts.eyes.forEach((e, i) => { e.visible = !on; arcs[i].visible = on; });
}
