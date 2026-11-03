// Small paper tags stuck on the floating screens: the screen's name, the speed badge, Fitz's
// olive notes and the English captions. Sized in on-screen pixels: a tag is built at PPU pixels
// per world unit, and the scene scales it by PPU / (its screen's pixels per unit when framed),
// so a 38 px font here is 38 px in the video on every screen.
//
// The kit's paperCard rounds its corners with a fixed 0.035-unit radius, too round for tags
// this small, so tags build their own outline (same cut corner, matching printed edge).

import * as THREE from 'three';
import { canvasTexture } from '../../kit/stage.js';
import { cardPath, text } from '../../kit/props.js';
import { site, fonts } from '../../kit/tokens.js';

export const PPU = 510;
const px = (v) => v / PPU;

const mctx = document.createElement('canvas').getContext('2d');
export function measure(str, font) {
  mctx.font = font;
  if ('letterSpacing' in mctx) mctx.letterSpacing = '0px';
  return mctx.measureText(str).width;
}

// Outline centred on the origin, y up; the cut (if any) is the top-right corner.
function tagShape(w, h, r, cut) {
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

// A soft shadow printed under a tag onto the screen (a blurred card silhouette). The screen is
// unlit, so real shadows don't land on it; this gives the tag its lift.
function softShadow(wPx, hPx, rPx, blur) {
  const pad = Math.ceil(blur * 2.6);
  const W = wPx + pad * 2, H = hPx + pad * 2;
  const tex = canvasTexture(W, H, (ctx) => {
    ctx.filter = `blur(${blur}px)`;
    ctx.fillStyle = site.ink;
    ctx.save();
    ctx.translate(pad, pad);
    ctx.beginPath();
    cardPath(ctx, wPx, hPx, 0, rPx, 0);
    ctx.fill();
    ctx.restore();
  }, { scale: 1 });
  const mat = new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false, toneMapped: false, opacity: 0 });
  return new THREE.Mesh(new THREE.PlaneGeometry(px(W), px(H)), mat);
}

// A paper tag. Returns a Group with userData { w, h (world), setAlpha(a) }. Its face is at
// z = lift (in front of the screen), its shadow just above the screen face.
export function tag({ wPx, hPx, rPx = 7, cutPx = 0, color = site.raised, edge = null, edgeWidth = 2, depth = 0.007, lift = 0.012, shadow = 0.32, draw }) {
  const w = px(wPx), h = px(hPx);
  const geo = new THREE.ExtrudeGeometry(tagShape(w, h, px(rPx), px(cutPx)), { depth, bevelEnabled: false, curveSegments: 8 });
  const pos = geo.attributes.position, uv = geo.attributes.uv;
  for (let i = 0; i < pos.count; i++) uv.setXY(i, (pos.getX(i) + w / 2) / w, (pos.getY(i) + h / 2) / h);
  geo.translate(0, 0, -depth);
  const tex = canvasTexture(wPx, hPx, (ctx) => {
    ctx.fillStyle = color;
    ctx.fillRect(0, 0, wPx, hPx);
    draw(ctx, wPx, hPx);
    if (edge) {
      ctx.strokeStyle = edge;
      ctx.lineWidth = edgeWidth;
      cardPath(ctx, wPx, hPx, cutPx, rPx, edgeWidth / 2);
      ctx.stroke();
    }
  });
  const face = new THREE.MeshStandardMaterial({ map: tex, roughness: 0.92, metalness: 0 });
  const side = new THREE.MeshStandardMaterial({ color, roughness: 0.92, metalness: 0 });
  const card = new THREE.Mesh(geo, [face, side]);
  card.position.z = lift;
  const g = new THREE.Group();
  g.add(card);
  let sh = null;
  if (shadow) {
    sh = softShadow(wPx, hPx, rPx, 9);
    sh.position.set(px(5), px(-7), 0.004);
    g.add(sh);
  }
  const mats = [face, side];
  g.userData = {
    w, h, card, shadow: sh,
    setAlpha(a) {
      g.visible = a > 0.002;
      for (const m of mats) { m.transparent = a < 0.999; m.opacity = a; m.depthWrite = a >= 0.999; }
      if (sh) sh.material.opacity = shadow * a;
    },
    setClip(planes) {
      if (sh) sh.material.clippingPlanes = planes;
    },
  };
  return g;
}

// ---- the four kinds -------------------------------------------------------------------------

const CLIP_FONT = { size: 28, weight: 700, family: fonts.display };
const BADGE_FONT = { size: 34, weight: 700, family: fonts.mono };
const NOTE_FONT = { size: 27, weight: 600, family: fonts.sans };
const CAPTION_FONT = { size: 38, weight: 600, family: fonts.sans };
const fontStr = (f) => `${f.weight} ${f.size}px ${f.family}`;

export const TAG_H = { clip: 48, badge: 54, note: 46, caption: 76 };
const NOTE_LINE = 34, CAPTION_LINE = 48;

// Split a long label into two lines, at the ' · ' (or else the space) that balances them best.
export function twoLines(str, font) {
  let best = null;
  for (const sep of [' · ', ' → ', ' ']) {
    let i = str.indexOf(sep);
    while (i > 0) {
      const a = str.slice(0, i), b = str.slice(i + sep.length);
      const wMax = Math.max(measure(a, font), measure(b, font));
      if (!best || wMax < best.w - 1) best = { lines: [a, sep === ' → ' ? '→ ' + b : b], w: wMax };
      i = str.indexOf(sep, i + 1);
    }
    if (best && sep === ' · ') break; // prefer the dot separator when there is one
  }
  return best ? best.lines : [str];
}
function linesFor(str, font, maxW) {
  return measure(str, font) > maxW ? twoLines(str, font) : [str];
}

// The screen's name: white paper, display type, ink.
export function clipTag(str) {
  const padX = 18;
  const wPx = Math.ceil(measure(str, fontStr(CLIP_FONT)) + padX * 2);
  return tag({ wPx, hPx: TAG_H.clip, edge: site.rule, edgeWidth: 2, draw: (ctx, w, h) => {
    text(ctx, str, padX, h / 2 + 1, { ...CLIP_FONT, color: site.ink, baseline: 'middle' });
  } });
}

// The speed badge: ink on paper, a fast-forward mark and the factor in mono. All badges share
// one width (wPx) so a change of factor is an in-place swap.
export function badgeWidth(strs) {
  return Math.ceil(Math.max(...strs.map((s) => measure(s, fontStr(BADGE_FONT)))) + 18 + 38 + 16);
}
export function badgeTag(str, wPx) {
  return tag({ wPx, hPx: TAG_H.badge, edge: site.ink, edgeWidth: 2.5, draw: (ctx, w, h) => {
    // fast-forward: two small ink triangles
    const cx = 18, cy = h / 2, th = 18, tw = 13;
    ctx.fillStyle = site.ink;
    for (const ox of [0, tw]) {
      ctx.beginPath();
      ctx.moveTo(cx + ox, cy - th / 2);
      ctx.lineTo(cx + ox + tw, cy);
      ctx.lineTo(cx + ox, cy + th / 2);
      ctx.closePath();
      ctx.fill();
    }
    const tw2 = measure(str, fontStr(BADGE_FONT));
    const x0 = 18 + 38; // after the mark
    text(ctx, str, x0 + (w - x0 - 16 - tw2) / 2, h / 2 + 1, { ...BADGE_FONT, color: site.ink, baseline: 'middle' });
  } });
}

// Fitz's note (what pickfit or Meta's model is doing): olive voice paper, cut corner, ink.
// Long notes go on two lines (maxW is the widest a line may be, in px).
export function noteTag(str, maxW = Infinity) {
  const padX = 18, cut = 12;
  const font = fontStr(NOTE_FONT);
  const lines = linesFor(str, font, maxW);
  const wPx = Math.ceil(Math.max(...lines.map((l) => measure(l, font))) + padX * 2 + cut * 0.6);
  const hPx = TAG_H.note + (lines.length - 1) * NOTE_LINE;
  return tag({ wPx, hPx, cutPx: cut, color: site.voice, edge: site.voiceEdge, edgeWidth: 2.5, draw: (ctx, w, h) => {
    lines.forEach((l, i) => text(ctx, l, padX, h / 2 + 1 + (i - (lines.length - 1) / 2) * NOTE_LINE, { ...NOTE_FONT, color: site.ink, baseline: 'middle' }));
  } });
}

// The English caption: a white paper card, centred, overlapping the screen's bottom edge.
export function captionTag(str, maxW = Infinity) {
  const padX = 32;
  const font = fontStr(CAPTION_FONT);
  const lines = linesFor(str, font, maxW);
  const wPx = Math.ceil(Math.max(...lines.map((l) => measure(l, font))) + padX * 2);
  const hPx = TAG_H.caption + (lines.length - 1) * CAPTION_LINE;
  return tag({ wPx, hPx, rPx: 8, edge: site.rule, edgeWidth: 2, draw: (ctx, w, h) => {
    lines.forEach((l, i) => text(ctx, l, w / 2, h / 2 + 1 + (i - (lines.length - 1) / 2) * CAPTION_LINE, { ...CAPTION_FONT, color: site.ink, align: 'center', baseline: 'middle' }));
  } });
}
