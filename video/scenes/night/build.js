// The night desk: a small clay diorama on the paper floor. Everything here is monochrome
// (paper-white clay and ink); the only colour of the night is the red of the disk-full bar,
// which is printed by draw.js.

import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { canvasTexture } from '../../kit/stage.js';
import { site, fonts } from '../../kit/tokens.js';

export const CLAY = '#EEEDE7';
export const CLAY_PERSON = '#E4E3DC';
export const BEZEL = '#2A2C28';

export function clay(color = CLAY, extra = {}) {
  return new THREE.MeshPhysicalMaterial({ color, roughness: 0.78, metalness: 0, sheen: 0.15, sheenRoughness: 0.8, sheenColor: new THREE.Color('#ffffff'), ...extra });
}

function mesh(geo, mat, { cast = true, receive = true } = {}) {
  const m = new THREE.Mesh(geo, mat);
  m.castShadow = cast;
  m.receiveShadow = receive;
  return m;
}

const rbox = (w, h, d, r = 0.02, seg = 3) => new RoundedBoxGeometry(w, h, d, seg, r);

// ---------------------------------------------------------------- desk and chair
export const DESK = { w: 4.3, d: 1.7, top: 1.2, t: 0.1 };

export function desk() {
  const g = new THREE.Group();
  const top = mesh(rbox(DESK.w, DESK.t, DESK.d, 0.03), clay());
  top.position.y = DESK.top - DESK.t / 2;
  g.add(top);
  const legGeo = rbox(0.09, DESK.top - DESK.t, 0.09, 0.02);
  for (const [sx, sz] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) {
    const leg = mesh(legGeo, clay());
    leg.position.set(sx * (DESK.w / 2 - 0.12), (DESK.top - DESK.t) / 2, sz * (DESK.d / 2 - 0.12));
    g.add(leg);
  }
  // a stretcher between the back legs, so it reads as a desk and not a table
  const bar = mesh(rbox(DESK.w - 0.3, 0.06, 0.05, 0.02), clay());
  bar.position.set(0, 0.35, -(DESK.d / 2 - 0.12));
  g.add(bar);
  return g;
}

export function chair() {
  const g = new THREE.Group();
  const seat = mesh(rbox(0.72, 0.08, 0.66, 0.03), clay());
  seat.position.y = 0.74;
  g.add(seat);
  const back = mesh(rbox(0.68, 0.62, 0.07, 0.03), clay());
  back.position.set(0, 1.1, 0.33);
  back.rotation.x = 0.1;
  g.add(back);
  const legGeo = new THREE.CylinderGeometry(0.03, 0.03, 0.72, 12);
  for (const [sx, sz] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) {
    const leg = mesh(legGeo, clay());
    leg.position.set(sx * 0.3, 0.36, sz * 0.27);
    g.add(leg);
  }
  return g;
}

// ---------------------------------------------------------------- laptop
// Group origin: the centre of the base's footprint on the desk. The lid hinges at the back.
export const LAP = { w: 1.5, d: 1.0, t: 0.055, h: 0.98, open: -0.26, sw: 1.36, sh: 0.8 };

export function laptop(screenTex) {
  const g = new THREE.Group();
  const base = mesh(rbox(LAP.w, LAP.t, LAP.d, 0.022), clay());
  base.position.y = LAP.t / 2;
  g.add(base);
  // keyboard and trackpad printed on the deck
  const kb = canvasTexture(600, 260, (ctx, w, h) => {
    ctx.fillStyle = '#E2E1DB'; ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = '#C9C8C1';
    const cols = 14, rows = 5, gx = 4, kw = (w - gx * (cols + 1)) / cols, kh = (h - gx * (rows + 1)) / rows;
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
      if (r === rows - 1 && c > 3 && c < 10) { if (c === 4) roundRect(ctx, gx + c * (kw + gx), gx + r * (kh + gx), kw * 6 + gx * 5, kh, 4); continue; }
      roundRect(ctx, gx + c * (kw + gx), gx + r * (kh + gx), kw, kh, 4);
    }
  });
  const keys = mesh(new THREE.PlaneGeometry(LAP.w * 0.84, LAP.d * 0.42), new THREE.MeshStandardMaterial({ map: kb, roughness: 0.8 }), { cast: false });
  keys.rotation.x = -Math.PI / 2;
  keys.position.set(0, LAP.t + 0.0015, -0.13);
  g.add(keys);
  const pad = mesh(rbox(0.46, 0.004, 0.27, 0.002, 1), new THREE.MeshStandardMaterial({ color: '#E3E2DC', roughness: 0.6 }), { cast: false });
  pad.position.set(0, LAP.t + 0.001, 0.29);
  g.add(pad);

  // the lid
  const hinge = new THREE.Group();
  hinge.position.set(0, LAP.t, -LAP.d / 2 + 0.02);
  hinge.rotation.x = LAP.open;
  g.add(hinge);
  const lid = mesh(rbox(LAP.w, LAP.h, 0.04, 0.022), clay());
  lid.position.set(0, LAP.h / 2, -0.02);
  hinge.add(lid);
  const bezel = mesh(rbox(LAP.w - 0.03, LAP.h - 0.03, 0.006, 0.016, 2), new THREE.MeshStandardMaterial({ color: BEZEL, roughness: 0.45 }), { cast: false });
  bezel.position.set(0, LAP.h / 2, 0.001);
  hinge.add(bezel);
  const screenMat = new THREE.MeshBasicMaterial({ map: screenTex, toneMapped: false });
  const screen = new THREE.Mesh(new THREE.PlaneGeometry(LAP.sw, LAP.sh), screenMat);
  screen.position.set(0, LAP.h / 2 + 0.03, 0.0052);
  hinge.add(screen);
  // the page the screen becomes at the end (exact paper colour, and it takes shadows)
  const page = new THREE.Mesh(new THREE.PlaneGeometry(LAP.sw, LAP.sh), new THREE.MeshBasicMaterial({ color: site.paper, transparent: true, opacity: 0, toneMapped: false }));
  page.position.copy(screen.position).add(new THREE.Vector3(0, 0, 0.0004));
  hinge.add(page);
  const catcher = new THREE.Mesh(new THREE.PlaneGeometry(LAP.sw, LAP.sh), new THREE.ShadowMaterial({ color: '#2b2a20', opacity: 0, transparent: true }));
  catcher.position.copy(screen.position).add(new THREE.Vector3(0, 0, 0.0008));
  catcher.receiveShadow = true;
  hinge.add(catcher);
  // a group in screen space: x right, y up, z out of the glass (things that pop out of the screen)
  const front = new THREE.Group();
  front.position.copy(screen.position);
  hinge.add(front);
  return { root: g, hinge, screen, page, catcher, front, lid };
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, r);
  ctx.fill();
}

// ---------------------------------------------------------------- lamp, mug, clock, bin
export function lamp() {
  const g = new THREE.Group();
  const base = mesh(new THREE.CylinderGeometry(0.21, 0.24, 0.06, 40), clay());
  base.position.y = 0.03;
  g.add(base);
  const armMat = clay();
  // lower arm leaning back, upper arm reaching forward over the desk
  const a = new THREE.Vector3(0, 0.05, 0), b = new THREE.Vector3(-0.05, 1.0, -0.12), c = new THREE.Vector3(-0.42, 1.38, 0.36);
  for (const [p, q] of [[a, b], [b, c]]) {
    const len = p.distanceTo(q);
    const arm = mesh(new THREE.CylinderGeometry(0.026, 0.026, len, 12), armMat);
    arm.position.copy(p).add(q).multiplyScalar(0.5);
    arm.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), q.clone().sub(p).normalize());
    g.add(arm);
  }
  for (const p of [b]) {
    const j = mesh(new THREE.SphereGeometry(0.045, 16, 12), armMat);
    j.position.copy(p);
    g.add(j);
  }
  // the shade: an open cone pointing down and forward
  const head = new THREE.Group();
  head.position.copy(c);
  g.add(head);
  const prof = [];
  for (let i = 0; i <= 12; i++) { const u = i / 12; prof.push(new THREE.Vector2(0.06 + 0.17 * Math.pow(u, 1.3), -0.3 * u)); }
  const shadeGeo = new THREE.LatheGeometry(prof, 40);
  const shade = mesh(shadeGeo, clay(CLAY, { side: THREE.DoubleSide }));
  const cap = mesh(new THREE.SphereGeometry(0.07, 20, 12, 0, Math.PI * 2, 0, Math.PI / 2), clay());
  cap.position.y = -0.005;
  const tilt = new THREE.Group(); // the scene aims it (its -y is the light's axis)
  tilt.add(shade, cap);
  head.add(tilt);
  const bulb = new THREE.Mesh(new THREE.SphereGeometry(0.06, 20, 14), new THREE.MeshBasicMaterial({ color: '#8d8b84', toneMapped: false }));
  bulb.position.y = -0.1;
  tilt.add(bulb);
  // where the light comes from, and where it points (in lamp space)
  const from = new THREE.Object3D(); from.position.y = -0.12; tilt.add(from);
  return { root: g, head, tilt, bulb, from };
}

export function mug() {
  const g = new THREE.Group();
  const prof = [
    new THREE.Vector2(0.0, 0.0), new THREE.Vector2(0.105, 0.0), new THREE.Vector2(0.12, 0.012), new THREE.Vector2(0.125, 0.25),
    new THREE.Vector2(0.105, 0.25), new THREE.Vector2(0.1, 0.03), new THREE.Vector2(0.0, 0.03),
  ];
  const body = mesh(new THREE.LatheGeometry(prof, 40), clay());
  g.add(body);
  const handle = mesh(new THREE.TorusGeometry(0.065, 0.018, 12, 24, Math.PI * 1.25), clay());
  handle.rotation.z = -Math.PI * 0.625 + Math.PI / 2;
  handle.position.set(0.13, 0.13, 0);
  handle.rotation.set(0, 0, -Math.PI * 0.62);
  g.add(handle);
  const tea = new THREE.Mesh(new THREE.CircleGeometry(0.1, 32), new THREE.MeshStandardMaterial({ color: '#4a4740', roughness: 0.3 }));
  tea.rotation.x = -Math.PI / 2;
  tea.position.y = 0.2;
  g.add(tea);
  return g;
}

// A desk clock: round, on two feet. setTime(hours24, minutes, seconds) turns the hands.
export function deskClock(R = 0.34) {
  const g = new THREE.Group();
  const body = mesh(new THREE.CylinderGeometry(R, R, 0.1, 64), clay());
  body.rotation.x = Math.PI / 2;
  g.add(body);
  const rim = mesh(new THREE.TorusGeometry(R, 0.03, 12, 64), clay());
  rim.position.z = 0.05;
  g.add(rim);
  const faceTex = canvasTexture(512, 512, (ctx, w) => {
    ctx.fillStyle = '#FBFBF8'; ctx.fillRect(0, 0, w, w);
    const c = w / 2;
    ctx.fillStyle = site.ink;
    for (let i = 0; i < 60; i++) {
      const a = (i / 60) * Math.PI * 2, big = i % 5 === 0;
      ctx.save(); ctx.translate(c, c); ctx.rotate(a);
      ctx.fillRect(-(big ? 5 : 2), -c + 18, big ? 10 : 4, big ? 34 : 16);
      ctx.restore();
    }
    ctx.font = `700 64px ${fonts.display}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    [[12, 0, -1], [3, 1, 0], [6, 0, 1], [9, -1, 0]].forEach(([n, x, y]) => ctx.fillText(String(n), c + x * (c - 108), c + y * (c - 104) + 4));
    ctx.font = `600 30px ${fonts.sans}`;
    ctx.fillStyle = site.ink3;
    ctx.fillText('PM', c, c + 92);
  });
  const face = new THREE.Mesh(new THREE.CircleGeometry(R - 0.012, 64), new THREE.MeshStandardMaterial({ map: faceTex, roughness: 0.85 }));
  face.position.z = 0.051;
  face.receiveShadow = true;
  g.add(face);
  const hand = (len, wid, z) => {
    const p = new THREE.Group();
    const m = mesh(rbox(wid, len, 0.012, wid * 0.45, 2), new THREE.MeshStandardMaterial({ color: site.ink, roughness: 0.5 }), { receive: false });
    m.position.y = len / 2 - 0.03;
    p.add(m);
    p.position.z = z;
    g.add(p);
    return p;
  };
  const hourH = hand(R * 0.55, 0.035, 0.062);
  const minH = hand(R * 0.82, 0.024, 0.075);
  const secH = hand(R * 0.86, 0.008, 0.086);
  const pin = mesh(new THREE.CylinderGeometry(0.022, 0.022, 0.03, 16), new THREE.MeshStandardMaterial({ color: site.ink }));
  pin.rotation.x = Math.PI / 2; pin.position.z = 0.085;
  g.add(pin);
  for (const s of [-1, 1]) {
    const foot = mesh(new THREE.SphereGeometry(0.05, 16, 12), clay());
    foot.scale.set(1, 0.6, 1.4);
    foot.position.set(s * R * 0.62, -R * 0.82, 0);
    g.add(foot);
  }
  const setTime = (minutesAfter7pm, seconds = 0) => {
    const totalMin = 19 * 60 + minutesAfter7pm;
    const h = totalMin / 60;
    hourH.rotation.z = -((h % 12) / 12) * Math.PI * 2;
    minH.rotation.z = -((totalMin % 60) / 60) * Math.PI * 2;
    secH.rotation.z = -(seconds / 60) * Math.PI * 2;
  };
  return { root: g, setTime, R };
}

export function bin() {
  const g = new THREE.Group();
  const prof = [new THREE.Vector2(0, 0), new THREE.Vector2(0.15, 0), new THREE.Vector2(0.19, 0.36), new THREE.Vector2(0.175, 0.36), new THREE.Vector2(0.138, 0.018), new THREE.Vector2(0, 0.018)];
  // a wastebasket: slotted sides, so it never reads as a second mug
  const ribs = canvasTexture(512, 128, (ctx, w, h) => {
    ctx.fillStyle = '#F2F1EC'; ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = '#9E9D96';
    for (let i = 0; i < 32; i++) ctx.fillRect(i * (w / 32) + 4, h * 0.14, 5, h * 0.66);
  });
  ribs.wrapS = THREE.RepeatWrapping;
  const body = mesh(new THREE.LatheGeometry(prof, 48), clay('#ffffff', { side: THREE.DoubleSide, map: ribs }));
  g.add(body);
  const rim = mesh(new THREE.TorusGeometry(0.183, 0.014, 10, 48), clay());
  rim.rotation.x = Math.PI / 2;
  rim.position.y = 0.36;
  g.add(rim);
  return g;
}

// ---------------------------------------------------------------- app icons and the dock
const GLYPHS = {
  broom(ctx, s) {
    ctx.lineWidth = s * 0.07; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.beginPath(); ctx.moveTo(s * 0.68, s * 0.2); ctx.lineTo(s * 0.48, s * 0.52); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(s * 0.36, s * 0.5); ctx.lineTo(s * 0.6, s * 0.62); ctx.lineTo(s * 0.5, s * 0.82); ctx.lineTo(s * 0.22, s * 0.7); ctx.closePath(); ctx.fill();
  },
  lens(ctx, s) {
    ctx.lineWidth = s * 0.08; ctx.lineCap = 'round';
    ctx.beginPath(); ctx.arc(s * 0.44, s * 0.44, s * 0.2, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(s * 0.59, s * 0.59); ctx.lineTo(s * 0.76, s * 0.76); ctx.stroke();
  },
  pie(ctx, s) {
    ctx.lineWidth = s * 0.07;
    ctx.beginPath(); ctx.arc(s * 0.5, s * 0.5, s * 0.27, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(s * 0.5, s * 0.5); ctx.arc(s * 0.5, s * 0.5, s * 0.27, -Math.PI / 2, Math.PI * 0.35); ctx.closePath(); ctx.fill();
  },
  bolt(ctx, s) {
    ctx.beginPath();
    ctx.moveTo(s * 0.56, s * 0.16); ctx.lineTo(s * 0.3, s * 0.56); ctx.lineTo(s * 0.48, s * 0.56); ctx.lineTo(s * 0.42, s * 0.86); ctx.lineTo(s * 0.7, s * 0.42); ctx.lineTo(s * 0.52, s * 0.42); ctx.closePath(); ctx.fill();
  },
};

export function appIcon(kind, size = 0.2) {
  const g = new THREE.Group();
  const block = mesh(rbox(size, size, size * 0.32, size * 0.22, 4), clay('#F4F3EE'));
  g.add(block);
  const tex = canvasTexture(256, 256, (ctx, s) => {
    ctx.clearRect(0, 0, s, s);
    ctx.fillStyle = site.ink; ctx.strokeStyle = site.ink;
    GLYPHS[kind](ctx, s);
  });
  const face = new THREE.Mesh(new THREE.PlaneGeometry(size * 0.92, size * 0.92), new THREE.MeshStandardMaterial({ map: tex, transparent: true, roughness: 0.8 }));
  face.position.z = size * 0.161;
  g.add(face);
  g.userData.mats = [block.material, face.material];
  return g;
}

export function dock(w = 1.0) {
  const m = mesh(rbox(w, 0.035, 0.3, 0.017), clay('#F2F1EC'));
  return m;
}

// ---------------------------------------------------------------- the person
// Faceless clay: a capsule body, a round head, simple arms. Root on the floor, facing -z.
export function person() {
  const mat = clay(CLAY_PERSON);
  const root = new THREE.Group();
  const hips = new THREE.Group();
  hips.position.y = 0.84;
  root.add(hips);
  // legs: thighs forward, shins down
  const legs = [];
  for (const s of [-1, 1]) {
    const thigh = mesh(new THREE.CapsuleGeometry(0.115, 0.42, 6, 16), mat);
    thigh.rotation.x = Math.PI / 2;
    thigh.position.set(s * 0.15, 0.0, -0.26);
    hips.add(thigh);
    const shin = mesh(new THREE.CapsuleGeometry(0.1, 0.56, 6, 16), mat);
    shin.position.set(s * 0.15, -0.42, -0.52);
    hips.add(shin);
    const shoe = mesh(new THREE.CapsuleGeometry(0.085, 0.14, 6, 16), mat);
    shoe.rotation.x = Math.PI / 2;
    shoe.position.set(s * 0.15, -0.79, -0.58);
    hips.add(shoe);
    legs.push(thigh, shin);
  }
  const spine = new THREE.Group();
  hips.add(spine);
  const torso = mesh(new THREE.CapsuleGeometry(0.27, 0.42, 8, 24), mat);
  torso.scale.set(1, 1, 0.78);
  torso.position.y = 0.42;
  spine.add(torso);
  const neckJ = new THREE.Group();
  neckJ.position.y = 0.86;
  spine.add(neckJ);
  const neck = mesh(new THREE.CylinderGeometry(0.075, 0.085, 0.14, 16), mat);
  neck.position.y = 0.04;
  neckJ.add(neck);
  const head = mesh(new THREE.SphereGeometry(0.25, 40, 28), mat);
  head.scale.set(0.95, 1.04, 0.98);
  head.position.y = 0.3;
  neckJ.add(head);
  const arm = (s) => {
    const shoulder = new THREE.Group();
    shoulder.position.set(s * 0.3, 0.74, 0);
    spine.add(shoulder);
    const ua = mesh(new THREE.CapsuleGeometry(0.075, 0.3, 6, 14), mat);
    ua.position.y = -0.2;
    shoulder.add(ua);
    const elbow = new THREE.Group();
    elbow.position.y = -0.4;
    shoulder.add(elbow);
    const fa = mesh(new THREE.CapsuleGeometry(0.068, 0.3, 6, 14), mat);
    fa.position.y = -0.19;
    elbow.add(fa);
    const hand = mesh(new THREE.SphereGeometry(0.075, 16, 12), mat);
    hand.scale.set(0.9, 1.1, 0.75);
    hand.position.y = -0.4;
    elbow.add(hand);
    return { shoulder, elbow };
  };
  const armL = arm(-1), armR = arm(1);
  return { root, hips, spine, neckJ, head, armL, armR, mat };
}

// ---------------------------------------------------------------- the time ruler
// A ribbon on the desk from 7 PM (the start clip) to now (the end tab). Its ticks are fixed to
// the hours; it grows to the right as the evening goes. Fitz later grabs the end tab and pulls
// it back, and the ribbon turns into his yellow tape (the colour floods from the end).
export const RULER = { hours: 5, perHour: 0.31, width: 0.085 };

export function rulerTexture() {
  const pxh = 520, W = pxh * RULER.hours, H = 140;
  return canvasTexture(W, H, (ctx) => {
    ctx.fillStyle = '#FFFFFF'; ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = site.ink;
    for (let m = 0; m <= RULER.hours * 60; m += 5) {
      const x = (m / 60) * pxh;
      const hour = m % 60 === 0, half = m % 30 === 0, q = m % 15 === 0;
      const len = hour ? 74 : half ? 50 : q ? 36 : 22;
      ctx.fillRect(x - (hour ? 3 : 1.5), 0, hour ? 6 : 3, len);
      if (hour && m < RULER.hours * 60) {
        const hr = 7 + m / 60;
        const label = hr === 7 ? '7 PM' : hr === 12 ? '12 AM' : String(hr);
        ctx.font = `700 46px ${fonts.display}`; ctx.textBaseline = 'alphabetic'; ctx.textAlign = 'left';
        ctx.fillText(label, x + 12, H - 18);
      }
    }
    ctx.fillRect(0, H - 5, W, 5);
  }, { scale: 1 });
}
