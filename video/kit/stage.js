// The room every animated scene is shot in: a quiet paper floor, soft daylight, real shadows,
// ambient occlusion, and a frame clock that the renderer drives one frame at a time.
//
// A scene builds its objects and one paused GSAP timeline, then calls stage.run(update).
// Preview: open the page and it plays in real time (space pauses, arrow keys step, ?t=12 jumps).
// Render: render.mjs opens it with ?render, waits for window.__scene.ready, then calls seek(t)
// for every frame and screenshots the canvas.

import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { GTAOPass } from 'three/addons/postprocessing/GTAOPass.js';
import { BokehPass } from 'three/addons/postprocessing/BokehPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { site } from './tokens.js';

export const W = 1920;
export const H = 1080;
export const FPS = 30;

const params = new URLSearchParams(location.search);
export const RENDER = params.has('render');

export class Stage {
  constructor({ background = site.paper, ground = true, ao = true, dof = null, fov = 30, exposure = 1 } = {}) {
    const canvas = document.createElement('canvas');
    document.body.appendChild(canvas);
    Object.assign(document.body.style, { margin: 0, background: '#111', overflow: 'hidden' });
    Object.assign(canvas.style, { display: 'block', width: RENDER ? `${W}px` : '100vw', height: RENDER ? `${H}px` : `${(100 * H) / W}vw` });

    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
    renderer.setPixelRatio(1);
    renderer.setSize(W, H, false);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.NoToneMapping; // linear: the paper and the brand colours keep their hex values
    renderer.toneMappingExposure = exposure;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;
    this.renderer = renderer;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(background);
    const pmrem = new THREE.PMREMGenerator(renderer);
    scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environmentIntensity = 0.42;
    this.scene = scene;

    const camera = new THREE.PerspectiveCamera(fov, W / H, 0.05, 200);
    camera.position.set(0, 2.2, 7);
    this.camera = camera;
    this.target = new THREE.Vector3(0, 0.6, 0);

    // Daylight from the upper left, soft-edged shadows on the paper.
    const key = new THREE.DirectionalLight('#fffaf0', 1.55);
    key.position.set(-4, 7, 5);
    key.castShadow = true;
    key.shadow.mapSize.set(4096, 4096);
    key.shadow.radius = 7;
    key.shadow.bias = -0.0004;
    key.shadow.normalBias = 0.02;
    const sc = key.shadow.camera;
    sc.left = -9; sc.right = 9; sc.top = 9; sc.bottom = -9; sc.near = 0.5; sc.far = 40;
    scene.add(key, key.target);
    this.key = key;
    const fill = new THREE.DirectionalLight('#f3f6ff', 0.45);
    fill.position.set(5, 3, 4);
    scene.add(fill);
    this.fill = fill;

    if (ground) {
      // The paper keeps its exact colour (unlit); a shadow catcher on top takes the shadows.
      const floor = new THREE.Mesh(new THREE.PlaneGeometry(400, 400), new THREE.MeshBasicMaterial({ color: background }));
      floor.rotation.x = -Math.PI / 2;
      const catcher = new THREE.Mesh(new THREE.PlaneGeometry(400, 400), new THREE.ShadowMaterial({ color: '#2b2a20', opacity: 0.16 }));
      catcher.rotation.x = -Math.PI / 2;
      catcher.position.y = 0.0005;
      catcher.receiveShadow = true;
      scene.add(floor, catcher);
      this.floor = floor;
      this.catcher = catcher;
    }

    const rt = new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType, samples: 4 });
    const composer = new EffectComposer(renderer, rt);
    composer.setPixelRatio(1);
    composer.setSize(W, H);
    composer.addPass(new RenderPass(scene, camera));
    if (ao) {
      const gtao = new GTAOPass(scene, camera, W, H);
      gtao.updateGtaoMaterial({ radius: 0.35, distanceExponent: 1.4, thickness: 1, scale: 1, samples: 16 });
      gtao.updatePdMaterial({ lumaPhi: 10, depthPhi: 2, normalPhi: 3, radius: 6, rings: 2, samples: 16 });
      gtao.blendIntensity = 0.8;
      composer.addPass(gtao);
      this.gtao = gtao;
    }
    if (dof) {
      const bokeh = new BokehPass(scene, camera, { focus: dof.focus ?? 7, aperture: dof.aperture ?? 0.0012, maxblur: dof.maxblur ?? 0.006 });
      composer.addPass(bokeh);
      this.bokeh = bokeh;
    }
    composer.addPass(new OutputPass());
    this.composer = composer;

    const display = new FontFace('Bricolage Display', `url(${new URL('./bricolage-display.woff2', import.meta.url)})`, { weight: '400 800' });
    document.fonts.add(display);
    this.ready = Promise.all([display.load(), document.fonts.load('700 64px "Bricolage Grotesque"'), document.fonts.ready]);
  }

  add(...objs) { this.scene.add(...objs); return objs[0]; }

  lookAt(x, y, z) { this.target.set(x, y, z); }

  render() {
    this.camera.lookAt(this.target);
    if (this.bokeh) this.bokeh.uniforms.focus.value = this.camera.position.distanceTo(this.target);
    this.composer.render();
  }

  // update(t) poses everything for time t (seconds). duration is the scene's length.
  run({ duration, update }) {
    let playing = true;
    let t = Number(params.get('t') || 0);
    const frame = (time) => { update(time); this.render(); };
    window.__scene = {
      duration,
      fps: FPS,
      ready: this.ready.then(() => frame(0)),
      seek: async (time) => { frame(time); },
    };
    if (RENDER) return;
    const hud = document.createElement('div');
    Object.assign(hud.style, { position: 'fixed', left: '8px', bottom: '8px', font: '12px ui-monospace,monospace', color: '#ddd' });
    document.body.appendChild(hud);
    addEventListener('keydown', (e) => {
      if (e.code === 'Space') playing = !playing;
      if (e.code === 'ArrowRight') t = Math.min(duration, t + (e.shiftKey ? 1 : 1 / FPS));
      if (e.code === 'ArrowLeft') t = Math.max(0, t - (e.shiftKey ? 1 : 1 / FPS));
    });
    let last = performance.now();
    this.ready.then(() => {
      const loop = (now) => {
        if (playing) t = (t + (now - last) / 1000) % duration;
        last = now;
        frame(t);
        hud.textContent = `${t.toFixed(2)} / ${duration.toFixed(2)}s`;
        requestAnimationFrame(loop);
      };
      requestAnimationFrame(loop);
    });
  }
}

// A sharp canvas texture for words and drawings printed on paper.
export function canvasTexture(w, h, draw, { scale = 2 } = {}) {
  const c = document.createElement('canvas');
  c.width = w * scale;
  c.height = h * scale;
  const ctx = c.getContext('2d');
  ctx.scale(scale, scale);
  draw(ctx, w, h);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  tex.userData.redraw = (fn) => { ctx.clearRect(0, 0, w, h); fn(ctx, w, h); tex.needsUpdate = true; };
  return tex;
}
