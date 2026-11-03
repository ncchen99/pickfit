// The real recordings, playing on floating screens in the paper room.
//
//   part 'main'   (48.0 s, cut 38.0–86.0): D_web, E_tool, F_install, G_mango, G_report
//   part 'agents' (19.8 s, cut 90.2–110.0): H_cli, H_gut
//
// Screens stand on a gentle arc a little above the paper floor, each tilted back to face the
// camera so the recording is seen square-on and sampled close to 1:1. The camera holds on the
// active screen with a very slow drift, glides to the next screen at each clip boundary
// (0.7 s, centred on the boundary, with motion blur), and pushes in gently where the next clip
// plays on the same screen. Tags (screen name, speed badge, Fitz's notes, English captions) come
// from edit/edl.json, read fresh at load.
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
const params = new URLSearchParams(location.search);

const PARTS = {
  main: {
    offset: 38.0, duration: 48.0,
    panels: [['D_web', 'E_tool'], ['F_install', 'G_report'], ['G_mango']],
    fill: { D_web: 0.87, E_tool: 0.9, F_install: 0.89, G_mango: 0.92, G_report: 0.89 },
    open: { fill: 1.01, dur: 1.7, ease: ease.io, tagsAt: 1.05 }, // pull back from the request card
  },
  agents: {
    offset: 90.2, duration: 19.8,
    panels: [['H_cli'], ['H_gut']],
    fill: { H_cli: 0.89, H_gut: 0.89 },
    open: { fill: 0.865, dur: 1.6, ease: ease.out, yaw: -0.01, tagsAt: 0.2 }, // short settle
  },
};

// Room geometry (world units; a screen face is SW wide).
const SW = 3.2;
const BEZEL = 0.024;
const FLOAT = 0.32; // bezel bottom above the floor
const PITCH = THREE.MathUtils.degToRad(9); // camera looks down this much; screens tilt back to match
const R = 16; // arc radius; the arc's centre is in front of the screens
const GAP = 0.95;
const GLIDE = 0.7;
const PUSH = 1.1;
const BUMP = 0.3; // pull-back in the middle of a glide (fraction of distance)
const DRIFT_YAW = THREE.MathUtils.degToRad(1.3);
const DRIFT_PITCH = THREE.MathUtils.degToRad(0.55);
const SHUTTER = 0.4 / FPS; // 144° shutter for the motion blur during glides

const clamp01 = (v) => Math.min(1, Math.max(0, v));
const lerp = (a, b, u) => a + (b - a) * u;
const easeOut = gsap.parseEase(ease.out);

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
  const panels = part.panels.map((ids, pi) => ({ index: pi, clips: ids.map((id) => {
    const c = byId[id];
    if (!c) throw new Error(`clip ${id} missing from edl.json`);
    const dur = c.pieces.reduce((s, p) => s + p.dur, 0);
    const clip = { id, label: c.label, events: c.events || [], start: c.at - part.offset, dur, n: Math.round(dur * FPS), panel: pi };
    clip.end = clip.start + dur;
    clips.push(clip);
    return clip;
  }) }));
  clips.sort((a, b) => a.start - b.start);
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

  // ---- the screens on their arc ------------------------------------------------------------
  const maxAniso = renderer.capabilities.getMaxAnisotropy();
  const MIP = params.get('mip') === '1';
  const STEP = (SW + 2 * BEZEL + GAP) / R;
  for (const p of panels) {
    const c0 = p.clips[0];
    for (const c of p.clips) if (c.iw / c.ih !== c0.iw / c0.ih) console.warn(`clips on one screen differ in size: ${c.id}`);
    p.w = SW;
    p.h = SW * c0.ih / c0.iw;
    p.theta = (p.index - (panels.length - 1) / 2) * STEP;
    p.yc = FLOAT + BEZEL + p.h / 2;
    const grp = screenPanel({ w: p.w, h: p.h, bezel: BEZEL, depth: 0.04 });
    grp.rotation.order = 'YXZ';
    grp.rotation.set(-PITCH, -p.theta, 0);
    grp.position.set(R * Math.sin(p.theta), p.yc, R - R * Math.cos(p.theta));
    const tex = new THREE.Texture();
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.generateMipmaps = MIP;
    tex.minFilter = MIP ? THREE.LinearMipmapLinearFilter : THREE.LinearFilter;
    tex.magFilter = THREE.LinearFilter;
    tex.anisotropy = maxAniso;
    const back = grp.children[0];
    back.material.roughness = 0.85;
    back.material.envMapIntensity = 0.3; // a dark bezel, not a grey frame
    const face = grp.userData.face;
    face.material.map = tex;
    face.material.needsUpdate = true;
    p.grp = grp;
    p.tex = tex;
    p.shown = null;
    scene.add(grp);
    grp.updateMatrixWorld(true);
    // planes that keep tag shadows on the screen (bezel included)
    const hw = p.w / 2 + BEZEL, hh = p.h / 2 + BEZEL;
    p.clip = [
      new THREE.Plane(new THREE.Vector3(1, 0, 0), hw), new THREE.Plane(new THREE.Vector3(-1, 0, 0), hw),
      new THREE.Plane(new THREE.Vector3(0, 1, 0), hh), new THREE.Plane(new THREE.Vector3(0, -1, 0), hh),
    ].map((pl) => pl.applyMatrix4(grp.matrixWorld));
  }

  // ---- camera shots --------------------------------------------------------------------------
  const tanH = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * camera.aspect;
  const distFor = (fill) => SW / (fill * 2 * tanH);
  const pose = (pi, fill, extra = {}) => ({ pi, d: distFor(fill), ...extra });
  const moves = [];
  const first = clips[0];
  const o = part.open;
  moves.push({ t0: 0, t1: o.dur, a: pose(first.panel, o.fill, { yaw: o.yaw || 0 }), b: pose(first.panel, part.fill[first.id]), ease: gsap.parseEase(o.ease), bump: 0, blur: false });
  for (let k = 1; k < clips.length; k++) {
    const a = clips[k - 1], b = clips[k];
    const tb = b.start;
    if (a.panel === b.panel) {
      moves.push({ t0: tb - PUSH / 2, t1: tb + PUSH / 2, a: pose(a.panel, part.fill[a.id]), b: pose(b.panel, part.fill[b.id]), ease: gsap.parseEase(ease.io), bump: 0, blur: false });
    } else {
      moves.push({ t0: tb - GLIDE / 2, t1: tb + GLIDE / 2, a: pose(a.panel, part.fill[a.id]), b: pose(b.panel, part.fill[b.id]), ease: gsap.parseEase(ease.io), bump: BUMP, blur: true });
    }
  }
  // Glides: tags on the outgoing screen ride out of frame with it (they fade once off-screen);
  // the incoming screen's tags appear as the camera lands, so no more than three show at once.
  const glideAt = new Set(moves.filter((m) => m.blur).map((m) => m.t0 + GLIDE / 2));
  const landT = (c) => (glideAt.has(c.start) ? c.start + GLIDE / 2 - 0.12 : -Infinity);
  const leaveT = (c) => (glideAt.has(c.end) ? c.end + GLIDE / 2 : null);
  // time window of an event on its screen
  const window_ = (c, e) => {
    let t0 = Math.max(c.start + e.t, landT(c) + (e.kind === 'badge' ? 0.06 : 0.1));
    let t1 = c.start + e.t + e.dur;
    if (leaveT(c) !== null && e.t + e.dur >= c.dur - 0.01) t1 = leaveT(c);
    return [t0, t1];
  };

  const T = new THREE.Vector3(), P = new THREE.Vector3(), up = new THREE.Vector3(), nrm = new THREE.Vector3();
  function camState(t) {
    let m = null;
    for (const mv of moves) if (t >= mv.t0) m = mv;
    if (!m) m = moves[0];
    const u = clamp01((t - m.t0) / (m.t1 - m.t0));
    const e = m.ease(u);
    const A = m.a, B = m.b;
    const pa = panels[A.pi], pb = panels[B.pi];
    const theta = lerp(pa.theta, pb.theta, e);
    const yc = lerp(pa.yc, pb.yc, e);
    const d = lerp(A.d, B.d, e) * (1 + m.bump * (0.5 - 0.5 * Math.cos(2 * Math.PI * u)));
    const yawOff = lerp(A.yaw || 0, B.yaw || 0, e);
    return { theta, yc, d, yawOff, moving: m.blur && u > 0 && u < 1, u, m };
  }
  function poseCamera(t) {
    const s = camState(t);
    T.set(R * Math.sin(s.theta), s.yc, R - R * Math.cos(s.theta));
    // a very slow orbit round the framed point: starts flat-on at t = 0
    const yaw = s.theta + s.yawOff + DRIFT_YAW * Math.sin((2 * Math.PI * t) / 21);
    const pitch = PITCH + DRIFT_PITCH * Math.sin((2 * Math.PI * t) / 15);
    nrm.set(-Math.sin(yaw) * Math.cos(pitch), Math.sin(pitch), Math.cos(yaw) * Math.cos(pitch));
    P.copy(T).addScaledVector(nrm, s.d);
    camera.position.copy(P);
    camera.up.set(0, 1, 0);
    camera.lookAt(T);
    return s;
  }

  // ---- tags -----------------------------------------------------------------------------------
  const tags = []; // { obj, panel, x, y (local, centre), inT, outT, hold }
  const ENTER = 0.5, EXIT = 0.22, RISE = 14 / PPU;
  const px = (v) => v / PPU;
  const tagsAt = o.tagsAt;
  const lastT = part.duration;
  function place(obj, panel, x, y, inT, outT) {
    obj.userData.setClip(panel.clip);
    panel.grp.add(obj);
    const rec = { obj, panel, x, y, inT: Math.max(inT, panel.index === first.panel ? tagsAt : 0), outT, hold: outT >= lastT - 1e-3 };
    tags.push(rec);
    return rec;
  }
  for (const p of panels) {
    const top = p.h / 2 + BEZEL, bot = -p.h / 2;
    // the screen's name, top-left corner, a little above the bezel
    p.clips.forEach((c, k) => {
      const g = clipTag(c.label);
      const { w, h } = g.userData;
      const next = p.clips[k + 1];
      const outT = next ? (next.start === c.end ? c.end : (c.end + next.start) / 2) : Infinity;
      const inT = c === first ? tagsAt : glideAt.has(c.start) ? landT(c) : c.start + 0.04;
      place(g, p, -p.w / 2 + px(22) + w / 2, top + px(12) - h / 2, inT, outT);
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
    for (const c of p.clips) {
      for (const e of c.events) {
        if (e.kind !== 'label' && e.kind !== 'caption') continue;
        const [inT, outT] = window_(c, e);
        if (e.kind === 'label') {
          const g = noteTag(e.text);
          const { w, h } = g.userData;
          place(g, p, -p.w / 2 + px(22) + w / 2, bot + px(12) - h / 2, inT, outT);
        } else {
          const g = captionTag(e.text);
          const { h } = g.userData;
          place(g, p, 0, bot + px(44) - h / 2, inT, outT);
        }
      }
    }
  }
  // badges: one width for the whole part so swaps happen in place
  const allBadgeTexts = [...new Set(panels.flatMap((p) => p.badgeTexts))];
  const bw = allBadgeTexts.length ? badgeWidth(allBadgeTexts) : 0;
  for (const p of panels) {
    const top = p.h / 2 + BEZEL;
    p.badgeTags = {};
    for (const str of p.badgeTexts) {
      const g = badgeTag(str, bw);
      const { w, h } = g.userData;
      g.userData.setClip(p.clip);
      g.position.set(p.w / 2 - px(22) - w / 2, top + px(12) - h / 2, 0);
      p.grp.add(g);
      p.badgeTags[str] = g;
    }
    p.badgeY = top + px(12) - TAG_H.badge / PPU / 2;
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
      r.obj.userData.setAlpha(a);
      r.obj.position.set(r.x, r.y - RISE * (1 - p), 0);
      r.obj.scale.setScalar(0.96 + 0.04 * p);
    }
    for (const p of panels) {
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
        const on = str === active;
        g.userData.setAlpha(on ? st.a : 0);
        const gy = p.badgeY - RISE * (1 - st.p);
        g.position.y = gy;
        g.scale.setScalar(0.96 + 0.04 * st.p);
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
      p.tex.image = img;
      p.tex.needsUpdate = true;
      p.shown = url;
    });
  }

  // ---- rendering with motion blur during glides --------------------------------------------
  const sampleRT = new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType, samples: 4 });
  const accRT = new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType });
  const accMat = new THREE.ShaderMaterial({
    uniforms: { tex: { value: sampleRT.texture }, w: { value: 1 } },
    vertexShader: 'varying vec2 vUv; void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }',
    fragmentShader: 'uniform sampler2D tex; uniform float w; varying vec2 vUv; void main() { gl_FragColor = vec4(texture2D(tex, vUv).rgb * w, w); }',
    blending: THREE.CustomBlending, blendEquation: THREE.AddEquation, blendSrc: THREE.OneFactor, blendDst: THREE.OneFactor,
    blendSrcAlpha: THREE.OneFactor, blendDstAlpha: THREE.OneFactor,
    depthTest: false, depthWrite: false,
  });
  const accQuad = new FullScreenQuad(accMat);
  const output = new OutputPass();
  output.renderToScreen = true;
  const dEase = (u) => (u < 0.5 ? 12 * u * u : 12 * (1 - u) * (1 - u)); // power3.inOut slope

  function poseAll(t) { poseCamera(t); poseTags(t); }
  function samplesAt(t) {
    const s = camState(t);
    if (!s.moving) return 1;
    return Math.max(1, Math.min(18, Math.round(1 + 17 * dEase(s.u) / 3)));
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
  window.__scene.ready = seek(0);
}
