// Fitz in clay: the mascot of brand/mascot/build.py, rebuilt as a 3D model for the video.
// Same proportions (an egg body, a small tuft, a tail cocked up behind, a tiny diamond beak
// centred under the eyes, the tape band around the neck) and the same palette, with the
// mascot's ink outline kept as an inverted hull so it still reads as the drawn Fitz.
//
// Units: 1 = 100 units of the mascot's 200-unit canvas. x3 = (x - 100) / 100,
// y3 = (186 - y) / 100 (the body's bottom is y3 = 0), z points out of the face.

import * as THREE from 'three';
import { mergeVertices } from 'three/addons/utils/BufferGeometryUtils.js';
import { fitz as C } from './tokens.js';

const DEPTH = 0.88; // body depth relative to its width
const LIFT = 0.05; // the body stands on its feet

const v2 = (x, y) => new THREE.Vector2((x - 100) / 100, (186 - y) / 100);
function cubic(p0, p1, p2, p3, n) {
  const out = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n, a = (1 - t) ** 3, b = 3 * t * (1 - t) ** 2, c = 3 * t * t * (1 - t), d = t ** 3;
    out.push(new THREE.Vector2(a * p0.x + b * p1.x + c * p2.x + d * p3.x, a * p0.y + b * p1.y + c * p2.y + d * p3.y));
  }
  return out;
}

// The right half of BODY_PATH, bottom to top, as (radius, height).
const profile = [
  ...cubic(v2(100, 186), v2(136, 186), v2(163, 166), v2(163, 136), 40),
  ...cubic(v2(163, 136), v2(163, 98), v2(136, 62), v2(100, 62), 40).slice(1),
].map((p) => new THREE.Vector2(Math.max(p.x, 0.0001), p.y));
const TOP = profile[profile.length - 1].y;

function radiusAt(y) {
  for (let i = 0; i < profile.length - 1; i++) {
    const a = profile[i], b = profile[i + 1];
    if ((y >= a.y && y <= b.y) || (y <= a.y && y >= b.y)) {
      const t = (y - a.y) / (b.y - a.y || 1);
      return a.x + (b.x - a.x) * t;
    }
  }
  return 0;
}

// A point on the body's surface seen from the front, and its outward normal.
function surface(x, y, side = 1) {
  const r = radiusAt(y);
  const z = DEPTH * Math.sqrt(Math.max(0, r * r - x * x)) * side;
  const dy = 0.01;
  const dr = (radiusAt(y + dy) - radiusAt(y - dy)) / (2 * dy);
  const n = new THREE.Vector3(x / (r || 1), -dr, z / (DEPTH * DEPTH * (r || 1))).normalize();
  return { p: new THREE.Vector3(x, y, z), n };
}

function clay(color, extra = {}) {
  return new THREE.MeshPhysicalMaterial({ color, roughness: 0.72, metalness: 0, sheen: 0.12, sheenRoughness: 0.8, sheenColor: new THREE.Color('#ffffff'), ...extra });
}

// Ink outline: the back faces pushed out along smooth normals.
function outline(mesh, thickness) {
  const src = new THREE.BufferGeometry();
  src.setAttribute('position', mesh.geometry.attributes.position.clone());
  if (mesh.geometry.index) src.setIndex(mesh.geometry.index.clone());
  const g = mergeVertices(src, 1e-4);
  g.computeVertexNormals();
  const m = new THREE.MeshBasicMaterial({ color: C.ink, side: THREE.BackSide });
  m.onBeforeCompile = (s) => {
    s.uniforms.thick = { value: thickness };
    s.vertexShader = 'uniform float thick;\n' + s.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\ntransformed += normalize(normal) * thick;');
  };
  const hull = new THREE.Mesh(g, m);
  hull.castShadow = false;
  hull.userData.isOutline = true;
  mesh.add(hull);
  return hull;
}

function bodyMesh() {
  const geo = new THREE.LatheGeometry(profile, 96);
  geo.scale(1, 1, 1);
  const pos = geo.attributes.position;
  for (let i = 0; i < pos.count; i++) pos.setZ(i, pos.getZ(i) * DEPTH);
  geo.computeVertexNormals();
  const mat = clay(C.body);
  // Cap, belly and blush are painted by position so their edges stay crisp at any size.
  mat.onBeforeCompile = (s) => {
    s.uniforms.cCap = { value: new THREE.Color(C.cap) };
    s.uniforms.cBelly = { value: new THREE.Color(C.belly) };
    s.uniforms.cBlush = { value: new THREE.Color(C.blush) };
    s.vertexShader = 'varying vec3 vObj;\n' + s.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\nvObj = position;');
    s.fragmentShader = 'varying vec3 vObj;\nuniform vec3 cCap; uniform vec3 cBelly; uniform vec3 cBlush;\n' + s.fragmentShader.replace(
      '#include <color_fragment>',
      `#include <color_fragment>
      {
        float ax = abs(vObj.x);
        float ang = abs(atan(vObj.x, vObj.z / ${DEPTH.toFixed(3)}));
        float frontB = ax < 0.2 ? 0.76 + 0.14 * smoothstep(0.0, 0.2, ax) : 0.90 - 0.22 * smoothstep(0.2, 0.7, ax);
        float capB = mix(frontB, 0.80, smoothstep(1.2, 2.2, ang));
        float aa = fwidth(vObj.y) * 1.2;
        float cap = smoothstep(capB - aa, capB + aa, vObj.y);
        vec2 b = vec2(vObj.x / 0.46, (vObj.y - 0.13) / 0.26);
        float bd = length(b);
        float belly = (1.0 - smoothstep(1.0 - fwidth(bd) * 1.5, 1.0 + fwidth(bd) * 1.5, bd)) * step(0.0, vObj.z);
        vec2 bl = vec2((ax - 0.41) / 0.07, (vObj.y - 0.53) / 0.038);
        float blush = (1.0 - smoothstep(0.8, 1.05, length(bl))) * step(0.0, vObj.z) * 0.55;
        vec3 col = diffuseColor.rgb;
        col = mix(col, cBelly, belly);
        col = mix(col, cBlush, blush * (1.0 - cap));
        col = mix(col, cCap, cap);
        diffuseColor.rgb = col;
      }`,
    );
  };
  const mesh = new THREE.Mesh(geo, mat);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  outline(mesh, 0.022);
  return mesh;
}

function extrudePath(points2d, depth, color, ink = 0.014, bevel = 0.018) {
  const shape = new THREE.Shape(points2d);
  const geo = new THREE.ExtrudeGeometry(shape, { depth, bevelEnabled: true, bevelThickness: bevel, bevelSize: bevel * 0.8, bevelSegments: 4, curveSegments: 32 });
  geo.translate(0, 0, -depth / 2);
  const mesh = new THREE.Mesh(geo, clay(color));
  mesh.castShadow = true;
  outline(mesh, ink);
  return mesh;
}

function pathPoints(segments) {
  // segments: array of cubic [p0, p1, p2, p3] in SVG units
  const pts = [];
  for (const s of segments) pts.push(...cubic(...s.map(([x, y]) => v2(x, y)), 18).slice(pts.length ? 1 : 0));
  return pts;
}

function tail() {
  const pts = [
    v2(70, 104), v2(42, 122),
    ...cubic(v2(42, 122), v2(33, 107), v2(22, 90), v2(15, 73), 16).slice(1),
    ...cubic(v2(15, 73), v2(10, 58), v2(10, 58), v2(22, 53.5), 10).slice(1),
    ...cubic(v2(22, 53.5), v2(34, 49.5), v2(34, 49.5), v2(38.5, 63), 10).slice(1),
    ...cubic(v2(38.5, 63), v2(43, 78), v2(55, 92), v2(70, 104), 16).slice(1),
  ];
  const m = extrudePath(pts, 0.04, C.tail, 0.016, 0.022);
  m.position.set(0.04, 0, -0.36);
  m.rotation.set(-0.12, 0.55, 0);
  return m;
}

function tuft() {
  const pts = pathPoints([
    [[93, 67], [86, 57], [90, 44], [104, 41]],
    [[104, 41], [99, 49], [103, 57], [111, 65]],
  ]);
  const m = extrudePath(pts, 0.05, C.cap, 0.014, 0.016);
  m.position.set(0, -0.02, 0.02);
  return m;
}

function wing(side) {
  const g = new THREE.SphereGeometry(1, 32, 24);
  g.scale(0.085, 0.165, 0.05);
  // a teardrop: narrower at the top
  const p = g.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const y = p.getY(i);
    const k = 1 - 0.35 * Math.max(0, y / 0.165);
    p.setX(i, p.getX(i) * k);
  }
  g.computeVertexNormals();
  const m = new THREE.Mesh(g, clay(C.wing));
  m.castShadow = true;
  outline(m, 0.014);
  const s = surface(0.56 * side, 0.32, 1);
  m.position.copy(s.p).addScaledVector(s.n, 0.02);
  m.position.z -= 0.06;
  m.rotation.set(0, side * 1.05, -side * 0.12);
  return m;
}

function eye(side, k = 1) {
  const g = new THREE.SphereGeometry(1, 32, 20);
  g.scale(0.068 * k, 0.083, 0.03);
  const m = new THREE.Mesh(g, new THREE.MeshPhysicalMaterial({ color: C.ink, roughness: 0.25, clearcoat: 0.6, clearcoatRoughness: 0.2 }));
  const s = surface(0.28 * side, 0.68, 1);
  m.position.copy(s.p).addScaledVector(s.n, -0.006);
  m.lookAt(m.position.clone().add(s.n));
  const hi = new THREE.Mesh(new THREE.SphereGeometry(0.02, 16, 12), new THREE.MeshBasicMaterial({ color: C.white }));
  hi.position.set(0.022, 0.03, 0.022);
  m.add(hi);
  return m;
}

function beak() {
  const g = new THREE.OctahedronGeometry(1, 0);
  g.scale(0.066, 0.068, 0.075);
  const pos = g.attributes.position;
  const colors = [];
  const top = new THREE.Color(C.beakTop), low = new THREE.Color(C.beak);
  for (let f = 0; f < pos.count; f += 3) {
    let up = false;
    for (let j = 0; j < 3; j++) if (pos.getY(f + j) > 0.01) up = true;
    for (let j = 0; j < 3; j++) colors.push(...(up ? top : low).toArray());
  }
  g.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
  g.computeVertexNormals();
  const m = new THREE.Mesh(g, clay('#ffffff', { vertexColors: true, roughness: 0.5 }));
  m.castShadow = true;
  outline(m, 0.011);
  const s = surface(0, 0.62, 1);
  m.position.copy(s.p).addScaledVector(s.n, 0.01);
  return m;
}

// The tape band: a ribbon that hugs the body, sagging at the front as in the drawing.
function tapeTexture() {
  const c = document.createElement('canvas');
  c.width = 4096; c.height = 128;
  const x = c.getContext('2d');
  x.fillStyle = C.tape; x.fillRect(0, 0, c.width, c.height);
  x.fillStyle = C.ink;
  for (let i = 0; i < 160; i++) {
    const px = (i / 160) * c.width;
    const long = i % 5 === 0;
    x.fillRect(px, 0, 6, long ? 52 : 30);
  }
  x.fillRect(0, 0, c.width, 12); x.fillRect(0, c.height - 12, c.width, 12);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; t.wrapS = THREE.RepeatWrapping;
  return t;
}

function bandCentre(theta) {
  return 0.487 - 0.12 * Math.pow(Math.max(0, Math.cos(theta)), 1.2);
}

function tapeBand() {
  const segs = 160, rows = 4, half = 0.054, off = 0.016;
  const pos = [], uv = [], idx = [];
  for (let i = 0; i <= segs; i++) {
    const th = (i / segs) * Math.PI * 2;
    const yc = bandCentre(th);
    for (let j = 0; j <= rows; j++) {
      const y = yc - half + (2 * half * j) / rows;
      const r = radiusAt(y) + off;
      pos.push(r * Math.sin(th), y, DEPTH * r * Math.cos(th));
      uv.push(i / segs, j / rows);
    }
  }
  for (let i = 0; i < segs; i++) for (let j = 0; j < rows; j++) {
    const a = i * (rows + 1) + j, b = a + rows + 1;
    idx.push(a, b, a + 1, b, b + 1, a + 1);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  g.setIndex(idx);
  g.computeVertexNormals();
  const m = new THREE.Mesh(g, new THREE.MeshPhysicalMaterial({ map: tapeTexture(), roughness: 0.45, sheen: 0.3, side: THREE.DoubleSide }));
  m.castShadow = true;
  return m;
}

function tapeEnd() {
  const grp = new THREE.Group();
  const strip = new THREE.Mesh(new THREE.BoxGeometry(0.075, 0.17, 0.014), new THREE.MeshPhysicalMaterial({ color: C.tape, roughness: 0.45 }));
  strip.position.y = -0.085;
  strip.castShadow = true;
  outline(strip, 0.01);
  const tab = new THREE.Mesh(new THREE.BoxGeometry(0.085, 0.04, 0.022), new THREE.MeshPhysicalMaterial({ color: C.metal, roughness: 0.3, metalness: 0.6 }));
  tab.position.y = -0.185;
  outline(tab, 0.01);
  grp.add(strip, tab);
  const s = surface(0.13, 0.33, 1);
  grp.position.copy(s.p).addScaledVector(s.n, 0.03);
  grp.rotation.set(-0.12, 0.12, 0.05);
  return grp;
}

function feet() {
  const grp = new THREE.Group();
  const mat = new THREE.MeshStandardMaterial({ color: C.ink, roughness: 0.5 });
  for (const side of [-1, 1]) {
    const leg = new THREE.Mesh(new THREE.CapsuleGeometry(0.016, 0.06, 4, 10), mat);
    leg.position.set(0.13 * side, 0.03, 0.12);
    const toe = new THREE.Mesh(new THREE.CapsuleGeometry(0.014, 0.07, 4, 10), mat);
    toe.rotation.x = Math.PI / 2;
    toe.position.set(0.13 * side, 0.012, 0.16);
    leg.castShadow = toe.castShadow = true;
    grp.add(leg, toe);
  }
  return grp;
}

// The stitched leaf Fitz holds out when it recommends something. He holds it by the narrow end
// (the leaf starts at the beak, -x, and widens outward).
export function leaf() {
  const pts = [];
  for (let i = 0; i <= 40; i++) {
    const t = (i / 40) * Math.PI * 2;
    pts.push(new THREE.Vector2(Math.cos(t) * 0.26, Math.sin(t) * 0.1 * (1 + 0.4 * Math.cos(t))));
  }
  const m = extrudePath(pts, 0.012, C.leaf, 0.01, 0.006);
  const rib = new THREE.Mesh(new THREE.BoxGeometry(0.46, 0.012, 0.03), new THREE.MeshStandardMaterial({ color: C.leafDark }));
  m.add(rib);
  for (let i = -2; i <= 2; i++) {
    const st = new THREE.Mesh(new THREE.BoxGeometry(0.012, 0.06, 0.03), new THREE.MeshStandardMaterial({ color: C.belly }));
    st.position.set(i * 0.075, 0.03, 0);
    st.rotation.z = 0.5;
    m.add(st);
  }
  m.position.x = 0.27;
  const g = new THREE.Group();
  g.add(m);
  return g;
}

export const BEAK_TIP = surface(0, 0.62, 1).p.clone().add(new THREE.Vector3(0, LIFT, 0.08));

export function createFitz() {
  const root = new THREE.Group(); // place and turn this
  const bird = new THREE.Group(); // hops and squashes inside root
  root.add(bird);
  const body = bodyMesh();
  const parts = {
    body,
    tail: tail(),
    tuft: tuft(),
    wings: [wing(-1), wing(1)],
    eyes: [eye(-1), eye(1)],
    beak: beak(),
    tape: tapeBand(),
    tapeEnd: tapeEnd(),
    feet: feet(),
  };
  const torso = new THREE.Group();
  torso.position.y = LIFT;
  torso.add(body, parts.tail, parts.tuft, ...parts.wings, ...parts.eyes, parts.beak, parts.tape, parts.tapeEnd);
  bird.add(torso, parts.feet);
  const hold = new THREE.Group(); // things held in the beak: turns with the head
  hold.position.copy(BEAK_TIP).sub(new THREE.Vector3(0, LIFT, 0));
  torso.add(hold);

  const api = {
    root, bird, torso, parts, hold,
    height: TOP + LIFT,
    blink(v) { for (const e of parts.eyes) e.scale.y = Math.max(0.08, 1 - v); },
    flap(v) {
      parts.wings[0].rotation.z = 0.12 + v * 0.9;
      parts.wings[1].rotation.z = -0.12 - v * 0.9;
    },
    // squash and stretch around the feet: s > 1 stretches up
    squash(s) { torso.scale.set(1 / Math.sqrt(s), s, 1 / Math.sqrt(s)); },
    // turn the head three-quarters (the whole egg turns: Fitz has no neck)
    turn(v) { torso.rotation.y = v * 0.62; },
  };
  return api;
}
