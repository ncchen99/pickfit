// The real recordings, playing on floating screens in the paper room.
//
//   part 'main'   (48.0 s, cut 38.0–86.0): D_web, E_tool, E_vm, F_install, G_mango, G_report
//   part 'agents' (19.8 s, cut 90.2–110.0): H_cli, H_gut
//
// Screens stand on a gentle arc a little above the paper floor, each tilted back to face the
// camera so the recording is seen square-on and sampled close to 1:1. The camera holds on the
// active screen with a very slow drift, glides to the next screen at each clip boundary
// (0.7 s, centred on the boundary, with motion blur), and pushes in gently where the next clip
// plays on the same screen. A clip marked "flyin-from-player" (E_vm) is the video playing in the
// previous screen's player: the camera pushes toward the player, the new recording crossfades in
// inside it, then lifts off as its own screen while the old screen falls back behind it.
// Tags (screen name, speed badge, Fitz's notes, English captions) come from edit/edl.json, read
// fresh at load. part 'main' opens on the night scene's last frame, dissolving into the website.
//
// Frames are loaded per seek: window.__scene.seek is replaced by an async version that waits
// for the frame images to decode before posing and rendering.

import * as THREE from 'three';
import { gsap } from 'gsap';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { FullScreenQuad } from 'three/addons/postprocessing/Pass.js';
import { Stage, W, H } from '../../kit/stage.js';
import { screenPanel } from '../../kit/props.js';
import { ease } from '../../kit/tokens.js';
import { PPU, TAG_H, clipTag, badgeTag, badgeWidth, noteTag, captionTag } from './tags.js';
import { frameUrl, load, peek } from './frames.js';

const FPS = 30;

const PARTS = {
  main: {
    offset: 38.0, duration: 48.0,
    arc: [['D_web', 'E_tool'], ['F_install', 'G_report'], ['G_mango']],
    fill: { D_web: 0.84, E_tool: 0.86, F_install: 0.85, G_mango: 0.88, G_report: 0.85 },
    // E_vm comes out of E_tool's video player (its rect in E_tool's last frame, 0..1 from top-left)
    emerge: { E_vm: { rect: [0.0854, 0.376, 0.428, 0.561], fillH: 0.82 } },
    open: { fill: 1.01, dur: 1.7, ease: ease.io, tagsAt: 1.15 }, // pull back from the request card
    intro: { image: 'night-last.png', dur: 0.3 }, // the night scene's last frame dissolves away
  },
  agents: {
    offset: 90.2, duration: 19.8,
    arc: [['H_cli'], ['H_gut']],
    fill: { H_cli: 0.85, H_gut: 0.85 },
    emerge: {},
    open: { fill: 0.835, dur: 1.6, ease: ease.out, yaw: -0.01, tagsAt: 0.2 }, // short settle
  },
};

// Room geometry (world units; an arc screen's face is SW wide).
const SW = 3.2;
const BEZEL = 0.024;
const FLOAT = 0.32; // bezel bottom above the floor
const PITCH = THREE.MathUtils.degToRad(9); // camera looks down this much; screens tilt back to match
const R = 16; // arc radius; the arc's centre is in front of the screens
const GAP = 0.95;
const GLIDE = 0.7;
const PUSH = 1.1;
const BUMP = 0.3; // pull-back in the middle of a glide (fraction of distance)
const FLYIN = [0.45, 0.55]; // fly-in from a player: starts this long before the boundary, ends after
const LIFT = 0.6; // the emerging screen comes this far off the old one
const RECEDE = 2.0; // and the old screen falls back this far behind it (along the final view axis)
const SHRINK = 0.5; // while shrinking to this, so it ends hidden behind the new screen
const DRIFT_YAW = THREE.MathUtils.degToRad(1.3);
const DRIFT_PITCH = THREE.MathUtils.degToRad(0.55);
const SHUTTER = 0.4 / FPS; // 144° shutter for the motion blur during moves
const MARGIN_PX = { side: 18, top: 4, below: 8 }; // tag placement on a screen, in on-screen px

const clamp01 = (v) => Math.min(1, Math.max(0, v));
const lerp = (a, b, u) => a + (b - a) * u;
const easeOut = gsap.parseEase(ease.out);
const easeIO = gsap.parseEase(ease.io);
const span = (u, a, b) => clamp01((u - a) / (b - a));

export async function start(partName) {
  const part = PARTS[partName];
  if (!part) throw new Error(`unknown part ${partName}`);

  const stage = new Stage({ ao: false, dof: null, fov: 30 });
  const { renderer, scene, camera } = stage;
  renderer.localClippingEnabled = true;
  // Daylight more from the front than the kit's default, so each screen's soft shadow falls
  // behind it (seen through the gap under the screen) and not across its neighbours.
  stage.key.position.set(-1.6, 7.5, 6);
  stage.key.shadow.radius = 10;
  await stage.ready;

  // ---- clips, from the edit decision list --------------------------------------------------
  const edl = await (await fetch(new URL('../../edit/edl.json', import.meta.url), { cache: 'no-store' })).json();
  const byId = Object.fromEntries(edl.clips.map((c) => [c.id, c]));
  const clips = [];
  const makeClip = (id, pi) => {
    const c = byId[id];
    if (!c) throw new Error(`clip ${id} missing from edl.json`);
    const dur = c.pieces.reduce((s, p) => s + p.dur, 0);
    const clip = { id, label: c.label, events: c.events || [], transition: c.transition || null, start: c.at - part.offset, dur, n: Math.round(dur * FPS), panel: pi };
    clip.end = clip.start + dur;
    clips.push(clip);
    return clip;
  };
  const panels = part.arc.map((ids, pi) => ({ index: pi, kind: 'arc', clips: ids.map((id) => makeClip(id, pi)) }));
  for (const id of Object.keys(part.emerge)) {
    const pi = panels.length;
    panels.push({ index: pi, kind: 'emerge', clips: [makeClip(id, pi)], cfg: part.emerge[id] });
  }
  clips.sort((a, b) => a.start - b.start);
  for (const c of edl.clips) {
    const t = c.at - part.offset;
    if (t >= 0 && t < part.duration && !clips.find((k) => k.id === c.id)) console.warn(`clip ${c.id} is in this part's window but not placed`);
  }
  for (const c of clips) if (c.transition === 'flyin-from-player' && !part.emerge[c.id]) console.warn(`clip ${c.id}: fly-in not configured`);
  // frame sizes from the first image of each clip
  await Promise.all(clips.map(async (c) => {
    const img = await load(frameUrl(c.id, 1));
    c.iw = img.naturalWidth; c.ih = img.naturalHeight;
  }));

  const frameOf = (clip, t) => Math.min(clip.n - 1, Math.max(0, Math.floor((t - clip.start) * FPS + 1e-4))) + 1;
  // Which of a screen's clips it shows at t: it changes clip halfway between them (off-screen).
  const clipOn = (panel, t) => {
    const cs = panel.clips;
    for (let k = cs.length - 1; k > 0; k--) if (t >= (cs[k - 1].end + cs[k].start) / 2) return cs[k];
    return cs[0];
  };

  const tanV = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
  const tanH = tanV * camera.aspect;
  const distFor = (fill) => SW / (fill * 2 * tanH); // arc screen framed at fill x frame width

  // ---- the screens ---------------------------------------------------------------------------
  const maxAniso = renderer.capabilities.getMaxAnisotropy();
  const STEP = (SW + 2 * BEZEL + GAP) / R;
  const nArc = part.arc.length;
  function buildPanel(p, w, h, bezel) {
    p.w = w; p.h = h; p.bezel = bezel;
    const grp = screenPanel({ w, h, bezel, depth: 0.04 * (bezel / BEZEL) });
    grp.rotation.order = 'YXZ';
    const tex = new THREE.Texture();
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.generateMipmaps = false;
    tex.minFilter = THREE.LinearFilter;
    tex.magFilter = THREE.LinearFilter;
    tex.anisotropy = maxAniso;
    const back = grp.children[0];
    back.material.roughness = 0.85;
    back.material.envMapIntensity = 0.3; // a dark bezel, not a grey frame
    const face = grp.userData.face;
    face.material.map = tex;
    face.material.needsUpdate = true;
    p.grp = grp; p.tex = tex; p.back = back; p.face = face; p.shown = null;
    scene.add(grp);
  }
  function clipPlanes(p) {
    p.grp.updateMatrixWorld(true);
    const hw = p.w / 2 + p.bezel, hh = p.h / 2 + p.bezel;
    p.clip = [
      new THREE.Plane(new THREE.Vector3(1, 0, 0), hw), new THREE.Plane(new THREE.Vector3(-1, 0, 0), hw),
      new THREE.Plane(new THREE.Vector3(0, 1, 0), hh), new THREE.Plane(new THREE.Vector3(0, -1, 0), hh),
    ].map((pl) => pl.applyMatrix4(p.grp.matrixWorld));
  }
  for (const p of panels.filter((q) => q.kind === 'arc')) {
    const c0 = p.clips[0];
    for (const c of p.clips) if (c.iw / c.ih !== c0.iw / c0.ih) console.warn(`clips on one screen differ in size: ${c.id}`);
    buildPanel(p, SW, SW * c0.ih / c0.iw, BEZEL);
    p.yaw = (p.index - (nArc - 1) / 2) * STEP;
    p.grp.rotation.set(-PITCH, -p.yaw, 0);
    p.grp.position.set(R * Math.sin(p.yaw), FLOAT + BEZEL + p.h / 2, R - R * Math.cos(p.yaw));
    p.home = p.grp.position.clone();
    p.centre = p.home.clone();
    p.ppu = (part.fill[c0.id] * W) / SW; // on-screen px per world unit when framed
    p.normal = new THREE.Vector3(0, 0, 1).applyQuaternion(p.grp.quaternion);
    clipPlanes(p);
  }
  // A screen that emerges from the player of the screen before it.
  for (const p of panels.filter((q) => q.kind === 'emerge')) {
    const c = p.clips[0];
    const prev = clips[clips.indexOf(c) - 1];
    const host = panels[prev.panel];
    const [rx, ry, rw, rh] = p.cfg.rect;
    const w = rw * host.w, h = rh * host.h;
    if (Math.abs(w / h - c.iw / c.ih) > 0.02) console.warn(`${c.id}: player rect aspect ${(w / h).toFixed(3)} vs frames ${(c.iw / c.ih).toFixed(3)}`);
    p.host = host;
    p.d = h / (p.cfg.fillH * 2 * tanV); // framed by height
    p.ppu = (p.cfg.fillH * H) / h;
    buildPanel(p, w, h, BEZEL * (host.ppu / p.ppu));
    p.local = new THREE.Vector3((rx + rw / 2 - 0.5) * host.w, (0.5 - ry - rh / 2) * host.h, 0); // rect centre on the host face
    p.yaw = host.yaw;
    p.grp.rotation.copy(host.grp.rotation);
    p.hostMatrix = host.grp.matrixWorld.clone();
    p.centre = p.local.clone().setZ(LIFT).applyMatrix4(p.hostMatrix);
    p.grp.position.copy(p.centre);
    // where the old screen goes: straight back behind the new one, as seen from the final camera
    const camF = new THREE.Vector3(-Math.sin(p.yaw) * Math.cos(PITCH), Math.sin(PITCH), Math.cos(p.yaw) * Math.cos(PITCH)).multiplyScalar(p.d).add(p.centre);
    const axis = p.centre.clone().sub(camF).normalize();
    p.hostTo = camF.clone().addScaledVector(axis, p.d + RECEDE);
    clipPlanes(p);
    // the face is drawn into a pre-scaled canvas so it is sampled near 1:1 when framed
    const sw = Math.min(1, (1.07 * p.ppu * w) / c.iw);
    if (sw < 0.8) {
      p.canvas = document.createElement('canvas');
      p.canvas.width = Math.round(c.iw * sw);
      p.canvas.height = Math.round(c.ih * sw);
      p.ctx = p.canvas.getContext('2d');
      p.ctx.imageSmoothingEnabled = true;
      p.ctx.imageSmoothingQuality = 'high';
    }
  }

  // ---- camera moves --------------------------------------------------------------------------
  const holdD = (p, c) => (p.kind === 'emerge' ? p.d : distFor(part.fill[c.id]));
  const moves = [];
  const first = clips[0];
  const o = part.open;
  const P0 = panels[first.panel];
  moves.push({ kind: 'open', t0: 0, t1: o.dur, a: { p: P0, d: distFor(o.fill), yaw: o.yaw || 0 }, b: { p: P0, d: holdD(P0, first) }, ease: gsap.parseEase(o.ease), bump: 0 });
  for (let k = 1; k < clips.length; k++) {
    const a = clips[k - 1], b = clips[k];
    const pa = panels[a.panel], pb = panels[b.panel];
    const tb = b.start;
    const A = { p: pa, d: holdD(pa, a) }, B = { p: pb, d: holdD(pb, b) };
    if (pb.kind === 'emerge' && pb.host === pa) {
      // the camera pushes toward the player in the first 3/4; the new screen then lifts off to meet it
      moves.push({ kind: 'flyin', t0: tb - FLYIN[0], t1: tb + FLYIN[1], a: A, b: B, ease: (u) => easeIO(span(u, 0, 0.75)), bump: 0, to: b, emerge: pb });
    } else if (a.panel === b.panel) {
      moves.push({ kind: 'push', t0: tb - PUSH / 2, t1: tb + PUSH / 2, a: A, b: B, ease: easeIO, bump: 0, to: b });
    } else {
      moves.push({ kind: 'glide', t0: tb - GLIDE / 2, t1: tb + GLIDE / 2, a: A, b: B, ease: easeIO, bump: BUMP, to: b });
    }
  }
  const flyins = moves.filter((m) => m.kind === 'flyin');

  // Tags stay inside the frame: on a glide or fly-in, the outgoing screen's tags are gone by the
  // time the camera has really started to move; the incoming screen's tags appear as it lands.
  const LEAVE = 0.1;
  const transitions = moves.filter((m) => m.kind === 'glide' || m.kind === 'flyin');
  const landT = (c) => { const m = transitions.find((x) => x.to === c); return m ? m.t1 - 0.12 : -Infinity; };
  const leaveCut = (pi, t) => {
    for (const m of transitions) if (m.a.p.index === pi && m.t0 + LEAVE > t) return m.t0 + LEAVE;
    return Infinity;
  };
  const window_ = (c, e) => {
    const t0 = Math.max(c.start + e.t, landT(c) + (e.kind === 'badge' ? 0.06 : 0.1));
    const t1 = Math.min(c.start + e.t + e.dur, leaveCut(c.panel, t0));
    return [t0, t1];
  };

  const T = new THREE.Vector3(), P = new THREE.Vector3(), nrm = new THREE.Vector3();
  function camState(t) {
    let m = null;
    for (const mv of moves) if (t >= mv.t0) m = mv;
    if (!m) m = moves[0];
    const u = clamp01((t - m.t0) / (m.t1 - m.t0));
    const e = m.ease(u);
    const A = m.a, B = m.b;
    T.lerpVectors(A.p.centre, B.p.centre, e);
    const yaw = lerp(A.p.yaw + (A.yaw || 0), B.p.yaw + (B.yaw || 0), e);
    const d = lerp(A.d, B.d, e) * (1 + m.bump * (0.5 - 0.5 * Math.cos(2 * Math.PI * u)));
    const moving = (m.kind === 'glide' || m.kind === 'flyin') && u > 0 && u < 1;
    return { yaw, d, moving, u, m };
  }
  function poseCamera(t) {
    const s = camState(t);
    // a very slow orbit round the framed point: starts flat-on at t = 0
    const yaw = s.yaw + DRIFT_YAW * Math.sin((2 * Math.PI * t) / 21);
    const pitch = PITCH + DRIFT_PITCH * Math.sin((2 * Math.PI * t) / 15);
    nrm.set(-Math.sin(yaw) * Math.cos(pitch), Math.sin(pitch), Math.cos(yaw) * Math.cos(pitch));
    P.copy(T).addScaledVector(nrm, s.d);
    camera.position.copy(P);
    camera.up.set(0, 1, 0);
    camera.lookAt(T);
    return s;
  }

  // The fly-in: crossfade inside the player, then lift off while the old screen falls back.
  const tmp = new THREE.Vector3();
  function setOpacity(mat, a) {
    mat.transparent = a < 0.999;
    mat.opacity = a;
    mat.depthWrite = a >= 0.999;
  }
  function poseScreens(t) {
    for (const m of flyins) {
      const p = m.emerge, host = m.a.p;
      const u = clamp01((t - m.t0) / (m.t1 - m.t0));
      const before = t < m.t0;
      const fade = span(u, 0.05, 0.45); // the new recording appears inside the player
      const g = easeIO(span(u, 0.35, 1)); // then lifts off as its own screen
      const back = easeIO(span(u, 0.35, 1)); // and the old screen falls back
      p.grp.visible = !before;
      setOpacity(p.face.material, fade);
      const bez = span(u, 0.35, 0.55);
      p.back.visible = bez > 0.002;
      setOpacity(p.back.material, bez);
      p.back.castShadow = bez > 0.5;
      p.grp.position.copy(tmp.copy(p.local).setZ(0.004 + (LIFT - 0.004) * g).applyMatrix4(p.hostMatrix));
      host.grp.position.lerpVectors(host.home, p.hostTo, back);
      host.grp.scale.setScalar(lerp(1, SHRINK, back));
      // once hidden behind the new screen, the old one leaves the room (no later shot sees it)
      host.grp.visible = t < m.t1;
    }
  }

  // ---- tags -----------------------------------------------------------------------------------
  const tags = []; // { obj, panel, x, y (local, centre), inT, outT, hold }
  const ENTER = 0.5, EXIT = 0.22, RISE_PX = 14;
  const tagsAt = o.tagsAt;
  const lastT = part.duration;
  function place(obj, panel, x, y, inT, outT) {
    obj.userData.setClip(panel.clip);
    panel.grp.add(obj);
    inT = Math.max(inT, panel.index === first.panel ? tagsAt : 0);
    outT = Math.min(outT, leaveCut(panel.index, inT));
    const rec = { obj, panel, x, y, inT, outT, hold: outT >= lastT - 1e-3 };
    tags.push(rec);
    return rec;
  }
  for (const p of panels) {
    const px = (v) => v / p.ppu;
    const k = PPU / p.ppu; // tag world size for this screen
    const top = p.h / 2 + p.bezel, bot = -p.h / 2 - p.bezel;
    const screenPx = p.w * p.ppu;
    // the screen's name: a sticker on the top-left corner, over the bezel
    p.clips.forEach((c, i) => {
      const g = clipTag(c.label);
      const w = g.userData.w * k, h = g.userData.h * k;
      const next = p.clips[i + 1];
      const outT = next ? (next.start === c.end ? c.end : (c.end + next.start) / 2) : Infinity;
      const inT = c === first ? tagsAt : landT(c) > -Infinity ? landT(c) : c.start + 0.04;
      place(g, p, -p.w / 2 + px(MARGIN_PX.side) + w / 2, top + px(MARGIN_PX.top) - h / 2, inT, outT);
    });
    // speed badges, top-right: consecutive badges on this screen are one tag whose factor swaps
    const badges = p.clips.flatMap((c) => c.events.filter((e) => e.kind === 'badge')
      .map((e) => { const [t0, t1] = window_(c, e); return { t0, t1, text: e.text }; }))
      .filter((b) => b.t1 > b.t0)
      .sort((a, b) => a.t0 - b.t0);
    const runs = [];
    for (const b of badges) {
      const r = runs[runs.length - 1];
      if (r && b.t0 <= r.t1 + 0.05) { r.segs.push(b); r.t1 = Math.max(r.t1, b.t1); } else runs.push({ t0: b.t0, t1: b.t1, segs: [b] });
    }
    p.badgeRuns = runs;
    p.badgeTexts = [...new Set(badges.map((b) => b.text))];
    // notes (bottom-left) and captions (bottom, centred); a caption shown with a note moves right
    // of it, and long ones go on two lines
    const evs = p.clips.flatMap((c) => c.events.filter((e) => e.kind === 'label' || e.kind === 'caption')
      .map((e) => { const [inT, outT] = window_(c, e); return { e, inT, outT }; }));
    const noteMax = Math.min(820, screenPx * 0.62);
    for (const v of evs.filter((x) => x.e.kind === 'label')) {
      v.g = noteTag(v.e.text, noteMax);
      v.wPx = v.g.userData.w * PPU;
      v.x0 = MARGIN_PX.side;
    }
    for (const v of evs.filter((x) => x.e.kind === 'caption')) {
      const notes = evs.filter((x) => x.e.kind === 'label' && x.inT < v.outT && v.inT < x.outT);
      const left = Math.max(MARGIN_PX.side, ...notes.map((n) => n.x0 + n.wPx + 28));
      let g = captionTag(v.e.text, screenPx - 2 * MARGIN_PX.side);
      let wPx = g.userData.w * PPU;
      if (screenPx / 2 - wPx / 2 < left && left + wPx > screenPx - MARGIN_PX.side) {
        g = captionTag(v.e.text, screenPx - MARGIN_PX.side - left); // two lines beside the note
        wPx = g.userData.w * PPU;
      }
      v.g = g; v.wPx = wPx;
      v.x0 = Math.max(screenPx / 2 - wPx / 2, left);
    }
    for (const v of evs) {
      const w = v.g.userData.w * k, h = v.g.userData.h * k;
      place(v.g, p, -p.w / 2 + px(v.x0) + w / 2, bot - px(MARGIN_PX.below) + h / 2, v.inT, v.outT);
    }
  }
  // badges: one width for the whole part so swaps happen in place
  const allBadgeTexts = [...new Set(panels.flatMap((p) => p.badgeTexts))];
  const bw = allBadgeTexts.length ? badgeWidth(allBadgeTexts) : 0;
  for (const p of panels) {
    const px = (v) => v / p.ppu;
    const k = PPU / p.ppu;
    const top = p.h / 2 + p.bezel;
    p.badgeTags = {};
    for (const str of p.badgeTexts) {
      const g = badgeTag(str, bw);
      const w = g.userData.w * k;
      g.userData.setClip(p.clip);
      g.position.set(p.w / 2 - px(MARGIN_PX.side) - w / 2, 0, 0);
      p.grp.add(g);
      p.badgeTags[str] = g;
    }
    p.badgeY = top + px(MARGIN_PX.top) - (TAG_H.badge / PPU) * k / 2;
    for (const r of p.badgeRuns) {
      if (p.index === first.panel) r.t0 = Math.max(r.t0, tagsAt + 0.12);
      r.hold = r.t1 >= lastT - 1e-3;
    }
  }

  // Entrance (short rise + fade, ease.out) and exit (fade) for a tag shown from inT to outT.
  function tagAlpha(t, inT, outT, hold) {
    if (t < inT || (!hold && t >= outT)) return { a: 0, p: 0 };
    const p = easeOut(clamp01((t - inT) / ENTER));
    const q = hold ? 0 : clamp01((t - (outT - EXIT)) / EXIT);
    return { a: p * (1 - q), p };
  }
  function poseTags(t) {
    for (const r of tags) {
      const { a, p } = tagAlpha(t, r.inT, r.outT, r.hold);
      const k = PPU / r.panel.ppu;
      r.obj.userData.setAlpha(a);
      r.obj.position.set(r.x, r.y - (RISE_PX / r.panel.ppu) * (1 - p), 0);
      r.obj.scale.setScalar(k * (0.96 + 0.04 * p));
    }
    for (const p of panels) {
      const k = PPU / p.ppu;
      let active = null, st = { a: 0, p: 0 };
      for (const r of p.badgeRuns) {
        if (t >= r.t0 && (r.hold || t < r.t1)) {
          st = tagAlpha(t, r.t0, r.t1, r.hold);
          let seg = r.segs[0];
          for (const s of r.segs) if (t >= s.t0) seg = s;
          active = seg.text;
        }
      }
      for (const [str, g] of Object.entries(p.badgeTags)) {
        g.userData.setAlpha(str === active ? st.a : 0);
        g.position.y = p.badgeY - (RISE_PX / p.ppu) * (1 - st.p);
        g.scale.setScalar(k * (0.96 + 0.04 * st.p));
      }
    }
  }

  // ---- frames ---------------------------------------------------------------------------------
  const urlsAt = (t) => panels.map((p) => { const c = clipOn(p, t); return frameUrl(c.id, frameOf(c, t)); });
  function setTextures(t, wait) {
    panels.forEach((p) => {
      const c = clipOn(p, t);
      const url = frameUrl(c.id, frameOf(c, t));
      if (p.shown === url) return;
      const img = peek(url);
      if (!img) { if (!wait) load(url); return; }
      if (p.canvas) {
        p.ctx.drawImage(img, 0, 0, p.canvas.width, p.canvas.height);
        p.tex.image = p.canvas;
      } else {
        p.tex.image = img;
      }
      p.tex.needsUpdate = true;
      p.shown = url;
    });
  }

  // ---- rendering with motion blur during moves ----------------------------------------------
  const sampleRT = new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType, samples: 4 });
  const accRT = new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType });
  const quadVS = 'varying vec2 vUv; void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }';
  const accMat = new THREE.ShaderMaterial({
    uniforms: { tex: { value: sampleRT.texture }, w: { value: 1 } },
    vertexShader: quadVS,
    fragmentShader: 'uniform sampler2D tex; uniform float w; varying vec2 vUv; void main() { gl_FragColor = vec4(texture2D(tex, vUv).rgb * w, w); }',
    blending: THREE.CustomBlending, blendEquation: THREE.AddEquation, blendSrc: THREE.OneFactor, blendDst: THREE.OneFactor,
    blendSrcAlpha: THREE.OneFactor, blendDstAlpha: THREE.OneFactor,
    depthTest: false, depthWrite: false,
  });
  const accQuad = new FullScreenQuad(accMat);
  // the opening dissolve: the previous scene's last frame over everything, fading out
  let intro = null;
  if (part.intro) {
    const img = new Image();
    img.src = new URL(`./${part.intro.image}`, import.meta.url).href;
    await img.decode();
    const tex = new THREE.Texture(img);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.generateMipmaps = false;
    tex.minFilter = THREE.LinearFilter;
    tex.needsUpdate = true;
    const mat = new THREE.ShaderMaterial({
      uniforms: { tex: { value: tex }, a: { value: 1 } },
      vertexShader: quadVS,
      fragmentShader: 'uniform sampler2D tex; uniform float a; varying vec2 vUv; void main() { gl_FragColor = vec4(texture2D(tex, vUv).rgb, a); }',
      blending: THREE.CustomBlending, blendEquation: THREE.AddEquation, blendSrc: THREE.SrcAlphaFactor, blendDst: THREE.OneMinusSrcAlphaFactor,
      blendSrcAlpha: THREE.ZeroFactor, blendDstAlpha: THREE.OneFactor,
      depthTest: false, depthWrite: false,
    });
    intro = { quad: new FullScreenQuad(mat), mat, dur: part.intro.dur };
  }
  const output = new OutputPass();
  output.renderToScreen = true;
  const dEase = (u) => (u < 0.5 ? 12 * u * u : 12 * (1 - u) * (1 - u)); // power3.inOut slope

  function poseAll(t) { poseCamera(t); poseScreens(t); poseTags(t); }
  function samplesAt(t) {
    const s = camState(t);
    if (!s.moving) return 1;
    const max = s.m.kind === 'flyin' ? 12 : 18;
    return Math.max(1, Math.min(max, Math.round(1 + (max - 1) * dEase(s.u) / 3)));
  }
  function renderAt(t) {
    const n = samplesAt(t);
    renderer.setRenderTarget(accRT);
    renderer.setClearColor(0x000000, 0);
    renderer.clear();
    for (let k = 0; k < n; k++) {
      poseAll(n === 1 ? t : t + SHUTTER * ((k + 0.5) / n - 0.5));
      renderer.autoClear = true;
      renderer.setRenderTarget(sampleRT);
      renderer.render(scene, camera);
      renderer.autoClear = false;
      accMat.uniforms.w.value = 1 / n;
      renderer.setRenderTarget(accRT);
      accQuad.render(renderer);
    }
    if (intro && t < intro.dur) {
      intro.mat.uniforms.a.value = 1 - t / intro.dur; // linear dissolve
      intro.quad.render(renderer);
    }
    renderer.autoClear = true;
    poseAll(t);
    output.render(renderer, null, accRT);
  }

  let current = 0;
  const update = (t) => {
    current = t;
    setTextures(t, false);
    poseAll(t);
  };
  stage.render = () => renderAt(current);

  stage.run({ duration: part.duration, update });

  // Async seek: wait for this frame's images, then pose and render; prefetch the next frames.
  async function seek(t) {
    await Promise.all(urlsAt(t).map(load));
    current = t;
    setTextures(t, true);
    renderAt(t);
    for (const k of [1, 2, 3]) urlsAt(t + k / FPS).forEach((u) => load(u));
  }
  window.__scene.seek = seek;
  // For checking: on-screen boxes (px) of the tags visible at t.
  const corner = new THREE.Vector3();
  window.__scene.tagBoxes = (t) => {
    poseAll(t);
    scene.updateMatrixWorld(true);
    const out = [];
    const objs = [...tags.map((r) => r.obj), ...panels.flatMap((p) => Object.values(p.badgeTags))];
    for (const g of objs) {
      if (!g.visible) continue;
      const { w, h, card } = g.userData;
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (const [sx, sy] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) {
        corner.set((sx * w) / 2, (sy * h) / 2, 0).applyMatrix4(card.matrixWorld).project(camera);
        const X = ((corner.x + 1) / 2) * W, Y = ((1 - corner.y) / 2) * H;
        x0 = Math.min(x0, X); x1 = Math.max(x1, X); y0 = Math.min(y0, Y); y1 = Math.max(y1, Y);
      }
      out.push({ x0, y0, x1, y1, margin: Math.min(x0, y0, W - x1, H - y1) });
    }
    return out;
  };
  window.__scene.ready = seek(0);
}
