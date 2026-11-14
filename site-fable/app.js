/* The Map vs the Mountain (issue #60). Static page: Three.js 0.160.0 (vendored), data from site-fable/build.py.
   Every number on screen is read from data/*.js, which build.py writes from the task and result files. */
(() => {
'use strict';
const T3 = THREE;
const Q = new URLSearchParams(location.search);
const FX = Q.get('fx') !== '0';                       // ?fx=0: no bloom / film pass (slow machines)
const SPEED = parseFloat(Q.get('speed') || '1');      // ?speed=3: run the choreography faster (testing)
const IDX = window.MVM_INDEX || { tasks: [], sets: [] };
const $ = (s) => document.querySelector(s);
const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const num = (v) => Math.round(v).toLocaleString('en-US').replace(/,/g, ' ');
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const lerp = (a, b, k) => a + (b - a) * k;
const C = { paper: '#F3EEDF', ink: '#1E1B16', contour: '#9A5B2E', truth: '#2F7FC1', model: '#D2412C', you: '#D9A441', night: '#0E1116', dusk: '#C9A27A' };
const U = 0.01, EXAG = 1.6;                           // world units per meter; vertical exaggeration (docs/DESIGN.md)
const MISSION = {
  flood: { name: 'Flash flood', blurb: 'which camp the water reaches' },
  crossings: { name: 'Rescue carry', blurb: 'how many contour lines a trail crosses' },
  sunset: { name: 'Lost hiker', blurb: 'minutes to spare before sunset' },
};

// ------------------------------------------------------------------ easing and the timeline
function bezier(x1, y1, x2, y2) {
  return (t) => {
    let u = t;
    for (let i = 0; i < 8; i++) {
      const x = 3 * (1 - u) * (1 - u) * u * x1 + 3 * (1 - u) * u * u * x2 + u * u * u - t;
      const dx = 3 * (1 - u) * (1 - u) * x1 + 6 * (1 - u) * u * (x2 - x1) + 3 * u * u * (1 - x2);
      if (Math.abs(dx) < 1e-6) break;
      u = clamp(u - x / dx, 0, 1);
    }
    return 3 * (1 - u) * (1 - u) * u * y1 + 3 * (1 - u) * u * u * y2 + u * u * u;
  };
}
const ease = bezier(0.2, 0.7, 0.2, 1);                // the house easing
const glide = (t) => t * t * t * (t * (t * 6 - 15) + 10);   // camera moves start and end at rest
const linear = (t) => t;
const CANCEL = { cancelled: true };
let epoch = 0, now = performance.now() * SPEED;
const active = new Set();
function cancelAll() { epoch++; for (const a of active) a.rej(CANCEL); active.clear(); }
function tween(ms, fn, e = ease) {
  let item;
  const p = new Promise((res, rej) => { item = { t0: performance.now() * SPEED, ms, fn, e, res, rej }; active.add(item); });
  p.stop = () => { if (active.delete(item)) item.res(); };
  return p;
}
const wait = (ms) => tween(ms, () => {});
function gate() {                                     // a promise the UI resolves; cancelled with everything else
  let item;
  const p = new Promise((res, rej) => { item = { t0: Infinity, ms: 1, fn() {}, e: linear, res, rej }; active.add(item); });
  p.done = (v) => { if (active.delete(item)) item.res(v); };
  return p;
}
const alive = (my) => { if (my !== epoch) throw CANCEL; };

// ------------------------------------------------------------------ renderer, stage
const renderer = new T3.WebGLRenderer({ antialias: !FX, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.setClearColor(C.night);
$('#gl').appendChild(renderer.domElement);
const scene = new T3.Scene();
scene.fog = new T3.FogExp2(C.dusk, 0);
const camera = new T3.PerspectiveCamera(30, 1, 0.5, 6000);
const controls = new T3.OrbitControls(camera, renderer.domElement);
Object.assign(controls, { enabled: false, enableDamping: true, dampingFactor: 0.08, maxPolarAngle: 1.48, minDistance: 6, maxDistance: 160, zoomSpeed: 0.7, rotateSpeed: 0.6 });

let composer = null, finalPass = null;
if (FX) {
  composer = new T3.EffectComposer(renderer, new T3.WebGLRenderTarget(4, 4, { type: T3.HalfFloatType, samples: 4 }));
  composer.addPass(new T3.RenderPass(scene, camera));
  composer.addPass(new T3.UnrealBloomPass(new T3.Vector2(256, 256), 0.8, 0.75, 1.02));   // only the HDR paths are above 1
  finalPass = new T3.ShaderPass({
    uniforms: { tDiffuse: { value: null }, uFilm: { value: 0 }, uTime: { value: 0 } },
    vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
    fragmentShader: `
      uniform sampler2D tDiffuse; uniform float uFilm, uTime; varying vec2 vUv;
      vec3 aces(vec3 x){ return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0); }
      float hash(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
      vec3 toSRGB(vec3 c){ return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c)); }
      void main(){
        vec3 c = texture2D(tDiffuse, vUv).rgb;
        vec3 f = aces(c * 1.0);                                             // ACES filmic
        f *= mix(0.62, 1.0, smoothstep(0.92, 0.28, length(vUv - 0.5)));      // vignette
        vec3 o = toSRGB(mix(clamp(c, 0.0, 1.0), f, uFilm));                  // uFilm 0: the flat map, untouched
        o += (hash(gl_FragCoord.xy + fract(uTime) * vec2(37.0, 91.0)) - 0.5) * 0.028 * uFilm;   // fine grain
        gl_FragColor = vec4(o, 1.0);
      }`,
  });
  composer.addPass(finalPass);
}
const hdr = (hex, k = 1.3) => new T3.Color(hex).multiplyScalar(k);

// sky dome (dusk horizon to night, low sun in the west) and the dark table
const skyMat = new T3.ShaderMaterial({
  side: T3.BackSide, depthWrite: false, fog: false,
  uniforms: { uDusk: { value: 0 }, uLift: { value: 0 }, uHorizon: { value: new T3.Color(C.dusk) }, uNight: { value: new T3.Color(C.night) } },
  vertexShader: 'varying vec3 vDir; void main(){ vDir = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
  fragmentShader: `
    uniform float uDusk, uLift; uniform vec3 uHorizon, uNight; varying vec3 vDir;
    void main(){
      vec3 d = normalize(vDir);
      vec3 col = mix(uHorizon, vec3(0.085, 0.075, 0.115), smoothstep(-0.03, 0.2, d.y));   // dusk band, then violet, then night
      col = mix(col, uNight, smoothstep(0.1, 0.6, d.y));
      float s = max(dot(d, normalize(vec3(-1.0, 0.07, 0.2))), 0.0);
      col += vec3(1.0, 0.70, 0.42) * (pow(s, 90.0) * 1.1 + pow(s, 9.0) * 0.25) * (1.0 - uDusk);
      col = mix(col, uNight + col * 0.06, uDusk * 0.92);
      gl_FragColor = vec4(mix(uNight, col, uLift), 1.0);
      #include <colorspace_fragment>
    }`,
});
const sky = new T3.Mesh(new T3.SphereGeometry(3000, 48, 24), skyMat);
sky.renderOrder = -10; sky.frustumCulled = false;
scene.add(sky);
const ground = new T3.Mesh(new T3.PlaneGeometry(9000, 9000).rotateX(-Math.PI / 2), new T3.MeshBasicMaterial({ color: C.night }));
ground.position.y = -0.08;
scene.add(ground);

// ------------------------------------------------------------------ the look (one place that sets every uniform)
const look = { lift: 0, film: 0, dusk: 0 };
let world = null;
const duskCol = new T3.Color(), tmpCol = new T3.Color();
function applyLook() {
  const { lift, film, dusk } = look;
  skyMat.uniforms.uDusk.value = dusk; skyMat.uniforms.uLift.value = lift;
  duskCol.set(C.dusk).lerp(tmpCol.set(C.night), dusk * 0.92);
  scene.fog.color.copy(duskCol); scene.fog.density = 0.0021 * lift;
  if (finalPass) finalPass.uniforms.uFilm.value = film;
  if (!world) return;
  world.terrainMat.uniforms.uLift.value = lift; world.terrainMat.uniforms.uDusk.value = dusk; world.terrainMat.uniforms.uHaze.value.copy(duskCol);
  world.wallMat.uniforms.uLift.value = lift; world.wallMat.uniforms.uDusk.value = dusk;
  const s = lerp(1, 0.27, lift) * lerp(1, 0.3, dusk);
  world.sheetMat.color.setRGB(s, s * lerp(1, 0.96, lift), s * lerp(1, 0.9, lift));
}
function setLook(o) { Object.assign(look, o); applyLook(); }

// ------------------------------------------------------------------ the world: one task = sheet + terrain + walls
const tasks = {};
function loadTask(id) {
  if (tasks[id]) return Promise.resolve(tasks[id]);
  return new Promise((res, rej) => {
    window.MVM_TASK = (t) => { tasks[t.id] = t; res(t); };
    const s = document.createElement('script');
    s.src = `data/${id}.js`; s.onerror = () => rej(new Error('missing data/' + id + '.js (run site-fable/build.py)'));
    document.head.appendChild(s);
  });
}
function loadImage(src) { return new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = src; }); }

const TERRAIN_VS = `
  attribute float aH; attribute vec3 aN; uniform float uLift;
  varying vec2 vUv; varying vec3 vN; varying float vDepth;
  void main(){
    vUv = uv; vN = aN;
    vec4 mv = modelViewMatrix * vec4(position.x, aH * ${(U * EXAG).toFixed(5)} * uLift, position.z, 1.0);
    vDepth = -mv.z; gl_Position = projectionMatrix * mv;
  }`;
const TERRAIN_FS = `
  uniform sampler2D uMap; uniform float uLift, uDusk; uniform vec3 uHaze;
  varying vec2 vUv; varying vec3 vN; varying float vDepth;
  void main(){
    vec3 col = texture2D(uMap, vUv).rgb;                                   // the task image, exactly, when uLift = 0
    vec3 n = normalize(mix(vec3(0.0, 1.0, 0.0), vN, uLift));
    float hs = clamp(dot(n, vec3(-0.5, 0.7071, -0.5)) / 0.7071, 0.0, 1.5);  // Imhof: light from the north-west at 45 degrees
    col *= mix(1.0, 0.16 + 0.66 * hs, 0.9 * uLift);
    float sun = clamp(dot(n, normalize(vec3(-0.93, 0.28, 0.22))), 0.0, 1.0); // low golden sun in the west, cool fill
    col *= mix(vec3(1.0), mix(vec3(0.66, 0.76, 1.0), vec3(1.12, 0.96, 0.76), smoothstep(0.0, 0.8, sun)), 0.7 * uLift);
    col = mix(col, col * vec3(0.16, 0.2, 0.36), uDusk);
    col = mix(col, uHaze, (1.0 - exp(-pow(vDepth * 0.0085, 2.0))) * uLift * 0.85);
    gl_FragColor = vec4(min(col, vec3(1.0)), 1.0);
    #include <colorspace_fragment>
  }`;
const WALL_VS = `
  attribute float aH; attribute float aTop; attribute float aSide; uniform float uLift;
  varying float vM; varying float vSide;
  void main(){
    vM = aH * aTop; vSide = aSide;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position.x, aH * aTop * ${(U * EXAG).toFixed(5)} * uLift, position.z, 1.0);
  }`;
const WALL_FS = `
  uniform float uLift, uDusk, uIdx; varying float vM; varying float vSide;
  void main(){
    float d = abs(fract(vM / uIdx + 0.5) - 0.5) * uIdx;
    float line = 1.0 - smoothstep(0.0, fwidth(vM) * 1.4, d);               // a hairline at every index contour level
    vec3 col = mix(vec3(0.60, 0.55, 0.45), vec3(0.32, 0.17, 0.08), line * 0.85);
    col *= mix(0.42, 1.0, vSide);                                           // west and south faces catch the sun
    col = mix(col, col * vec3(0.16, 0.2, 0.36), uDusk);
    gl_FragColor = vec4(col, 1.0);
    #include <colorspace_fragment>
  }`;

async function buildWorld(task) {
  if (world) {
    scene.remove(world.group);
    world.group.traverse((o) => { if (o.geometry) o.geometry.dispose(); });
    world.tex.dispose();
    world = null;
  }
  const img = await loadImage(task.image.src);
  const tex = new T3.Texture(img);
  tex.colorSpace = T3.SRGBColorSpace; tex.anisotropy = renderer.capabilities.getMaxAnisotropy(); tex.needsUpdate = true;

  const { nx, ny } = task.mesh, [W, Hm] = task.extent_m;
  const raw = atob(task.mesh.z), Z = new Float32Array(nx * ny);
  for (let i = 0; i < nx * ny; i++) Z[i] = (raw.charCodeAt(2 * i) | (raw.charCodeAt(2 * i + 1) << 8)) / 10;
  const dx = W / (nx - 1), dy = Hm / (ny - 1);
  const [fl, ft, fr, fb] = task.image.frame, iw = task.image.w, ih = task.image.h;
  const elev = (x, y) => {                                                  // bilinear, meters; x east, y north
    const fx = clamp(x / dx, 0, nx - 1.001), fy = clamp(y / dy, 0, ny - 1.001), j = Math.floor(fx), i = Math.floor(fy), a = fx - j, b = fy - i;
    return Z[i * nx + j] * (1 - a) * (1 - b) + Z[i * nx + j + 1] * a * (1 - b) + Z[(i + 1) * nx + j] * (1 - a) * b + Z[(i + 1) * nx + j + 1] * a * b;
  };
  const wp = (x, y, off = 0) => new T3.Vector3((x - W / 2) * U, elev(x, y) * U * EXAG + off, -(y - Hm / 2) * U);

  // terrain
  const pos = new Float32Array(nx * ny * 3), uv = new Float32Array(nx * ny * 2), aH = new Float32Array(nx * ny), aN = new Float32Array(nx * ny * 3);
  for (let i = 0; i < ny; i++) for (let j = 0; j < nx; j++) {
    const k = i * nx + j, x = j * dx, y = i * dy;
    pos[3 * k] = (x - W / 2) * U; pos[3 * k + 2] = -(y - Hm / 2) * U;
    uv[2 * k] = (fl + (x / W) * (fr - fl)) / iw; uv[2 * k + 1] = 1 - (fb - (y / Hm) * (fb - ft)) / ih;
    aH[k] = Z[k];
    const zx = (Z[i * nx + Math.min(nx - 1, j + 1)] - Z[i * nx + Math.max(0, j - 1)]) / ((Math.min(nx - 1, j + 1) - Math.max(0, j - 1)) * dx);
    const zy = (Z[Math.min(ny - 1, i + 1) * nx + j] - Z[Math.max(0, i - 1) * nx + j]) / ((Math.min(ny - 1, i + 1) - Math.max(0, i - 1)) * dy);
    const n = new T3.Vector3(-zx * EXAG, 1, zy * EXAG).normalize();          // north is -z
    aN[3 * k] = n.x; aN[3 * k + 1] = n.y; aN[3 * k + 2] = n.z;
  }
  const index = new Uint32Array((nx - 1) * (ny - 1) * 6);
  let q = 0;
  for (let i = 0; i < ny - 1; i++) for (let j = 0; j < nx - 1; j++) {
    const a = i * nx + j, b = a + 1, c = a + nx, d = c + 1;
    index[q++] = a; index[q++] = b; index[q++] = c; index[q++] = b; index[q++] = d; index[q++] = c;
  }
  const tg = new T3.BufferGeometry();
  tg.setAttribute('position', new T3.BufferAttribute(pos, 3)); tg.setAttribute('uv', new T3.BufferAttribute(uv, 2));
  tg.setAttribute('aH', new T3.BufferAttribute(aH, 1)); tg.setAttribute('aN', new T3.BufferAttribute(aN, 3));
  tg.setIndex(new T3.BufferAttribute(index, 1));
  const terrainMat = new T3.ShaderMaterial({ vertexShader: TERRAIN_VS, fragmentShader: TERRAIN_FS, side: T3.DoubleSide,
    uniforms: { uMap: { value: tex }, uLift: { value: 0 }, uDusk: { value: 0 }, uHaze: { value: new T3.Color(C.dusk) } } });
  const terrain = new T3.Mesh(tg, terrainMat);
  terrain.frustumCulled = false;

  // the sides of the relief block
  const ring = [];
  for (let j = 0; j < nx; j++) ring.push([0, j, 1.0]);                      // south face
  for (let i = 0; i < ny; i++) ring.push([i, nx - 1, 0.45]);                // east
  for (let j = nx - 1; j >= 0; j--) ring.push([ny - 1, j, 0.55]);           // north
  for (let i = ny - 1; i >= 0; i--) ring.push([i, 0, 0.95]);                // west
  const wpPos = [], wH = [], wTop = [], wSide = [], wIdx = [];
  ring.forEach(([i, j, s], k) => {
    for (const top of [1, 0]) { wpPos.push((j * dx - W / 2) * U, 0, -(i * dy - Hm / 2) * U); wH.push(Z[i * nx + j]); wTop.push(top); wSide.push(s); }
    if (k) { const a = 2 * (k - 1); wIdx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
  });
  const wg = new T3.BufferGeometry();
  wg.setAttribute('position', new T3.Float32BufferAttribute(wpPos, 3)); wg.setAttribute('aH', new T3.Float32BufferAttribute(wH, 1));
  wg.setAttribute('aTop', new T3.Float32BufferAttribute(wTop, 1)); wg.setAttribute('aSide', new T3.Float32BufferAttribute(wSide, 1));
  wg.setIndex(wIdx);
  const wallMat = new T3.ShaderMaterial({ vertexShader: WALL_VS, fragmentShader: WALL_FS, side: T3.DoubleSide,
    uniforms: { uLift: { value: 0 }, uDusk: { value: 0 }, uIdx: { value: task.index_interval_m } } });
  const walls = new T3.Mesh(wg, wallMat);
  walls.frustumCulled = false;

  // the paper around the map frame: the same image, so the flat view is the task picture, collar and all
  const sc = (W * U) / (fr - fl);
  const X = (px) => (px - fl) * sc - (W * U) / 2, Zw = (py) => (py - ft) * sc - (Hm * U) / 2;
  const sp = [], su = [], si = [];
  for (const [x0, y0, x1, y1] of [[0, 0, iw, ft], [0, fb, iw, ih], [0, ft, fl, fb], [fr, ft, iw, fb]]) {
    const b = sp.length / 3;
    for (const [px, py] of [[x0, y0], [x1, y0], [x0, y1], [x1, y1]]) { sp.push(X(px), 0, Zw(py)); su.push(px / iw, 1 - py / ih); }
    si.push(b, b + 2, b + 1, b + 1, b + 2, b + 3);
  }
  const sg = new T3.BufferGeometry();
  sg.setAttribute('position', new T3.Float32BufferAttribute(sp, 3)); sg.setAttribute('uv', new T3.Float32BufferAttribute(su, 2)); sg.setIndex(si);
  const sheetMat = new T3.MeshBasicMaterial({ map: tex, fog: false, side: T3.DoubleSide });
  const sheetMesh = new T3.Mesh(sg, sheetMat);

  const group = new T3.Group(), fx = new T3.Group();
  group.add(sheetMesh, terrain, walls, fx);
  scene.add(group);
  let hmax = 0, summit = [W / 2, Hm / 2];
  for (let k = 0; k < Z.length; k++) if (Z[k] > hmax) { hmax = Z[k]; summit = [(k % nx) * dx, Math.floor(k / nx) * dy]; }
  world = { task, group, fx, tex, terrainMat, wallMat, sheetMat, elev, wp, W, Hm, hmax: hmax * U * EXAG, summit,
    sheet: { cx: (X(0) + X(iw)) / 2, cz: (Zw(0) + Zw(ih)) / 2, w: iw * sc, h: ih * sc } };
  applyLook();
}

// ------------------------------------------------------------------ camera
let vw = 1, vh = 1, portrait = false;
const cam = { tx: 0, ty: 0, tz: 0, theta: 0, phi: 0.0012, r: 60, sx: 0, sy: 0 };
let camMode = 'state';                                // 'state': cam drives the camera; 'free': intro flight or orbit controls
function panelPx() {
  const cs = getComputedStyle($('#panel'));
  return portrait ? { pw: 0, ph: parseFloat(cs.height) } : { pw: parseFloat(cs.width), ph: 0 };
}
function freeRect(withPanel = true) {                 // the part of the viewport the stage may use, in px
  const { pw, ph } = withPanel ? panelPx() : { pw: 0, ph: 0 };
  const top = portrait ? 50 : 66, bot = portrait ? 14 : 58, m = portrait ? 8 : 26;
  return { x: m, y: top, w: vw - pw - 2 * m, h: vh - ph - top - bot };
}
function shiftFor(r) { return { sx: -((r.x + r.w / 2) - vw / 2), sy: -((r.y + r.h / 2) - vh / 2) }; }
function topState() {                                 // straight down on the sheet, fitted to the free area
  const r = freeRect(), frameOnly = vw < 720, s = world.sheet;
  const w = frameOnly ? world.W * U : s.w, h = frameOnly ? world.Hm * U : s.h;
  const ppu = Math.min(r.w / w, r.h / h);
  const D = vh / (2 * Math.tan((camera.fov * Math.PI) / 360) * ppu);
  return { tx: frameOnly ? 0 : s.cx, ty: 0, tz: frameOnly ? 0 : s.cz, theta: 0, phi: 0.0012, r: D, ...shiftFor(r) };
}
function applyCam() {
  const sp = Math.sin(cam.phi);
  camera.position.set(cam.tx + cam.r * sp * Math.sin(cam.theta), cam.ty + cam.r * Math.cos(cam.phi), cam.tz + cam.r * sp * Math.cos(cam.theta));
  camera.up.set(0, 1, 0); camera.lookAt(cam.tx, cam.ty, cam.tz);
  applyShift(cam.sx, cam.sy);
}
function applyShift(sx, sy) {
  if (Math.abs(sx) + Math.abs(sy) < 0.5) { if (camera.view) camera.clearViewOffset(); } else camera.setViewOffset(vw, vh, sx, sy, vw, vh);
}
function readCam() {                                  // take over from the orbit controls
  const t = controls.target, o = camera.position.clone().sub(t), r = o.length();
  Object.assign(cam, { tx: t.x, ty: t.y, tz: t.z, r, phi: Math.acos(clamp(o.y / r, -1, 1)), theta: Math.atan2(o.x, o.z) });
}
function camTo(to, ms, e = glide) {
  if (controls.enabled) { readCam(); controls.enabled = false; }
  camMode = 'state';
  const from = { ...cam };
  let dth = (to.theta - from.theta) % (2 * Math.PI);
  if (dth > Math.PI) dth -= 2 * Math.PI; if (dth < -Math.PI) dth += 2 * Math.PI;
  return tween(ms, (k) => {
    for (const key of ['tx', 'ty', 'tz', 'phi', 'r', 'sx', 'sy']) cam[key] = lerp(from[key], to[key], k);
    cam.theta = from.theta + dth * k;
  }, e);
}
function freeOrbit() {
  controls.target.set(cam.tx, cam.ty, cam.tz); applyCam(); controls.update(); controls.enabled = true; camMode = 'free';
}
/** A three-quarter view that looks across a path from its lower, sunnier side. pts: [[x, y]] in map meters. */
function sideView(pts, insetTop = 0, insetBottom = 0) {
  const a = pts[0], b = pts[pts.length - 1];
  let cx = 0, cy = 0, cz = 0, ext = 0;
  for (const p of pts) { cx += p[0]; cy += p[1]; cz += world.elev(p[0], p[1]); }
  cx /= pts.length; cy /= pts.length; cz /= pts.length;
  for (const p of pts) ext = Math.max(ext, Math.hypot(p[0] - cx, p[1] - cy));
  const vx = b[0] - a[0], vy = b[1] - a[1], L = Math.hypot(vx, vy) || 1;
  let best = null;
  for (const s of [1, -1]) {
    const nxm = (-vy / L) * s, nym = (vx / L) * s;                          // a side of the path, in map coordinates
    let z = 0;
    for (const d of [300, 600, 900]) z += world.elev(clamp(cx + nxm * d, 0, world.W), clamp(cy + nym * d, 0, world.Hm));
    const score = z / 3 + nym * 70 + nxm * 25;                              // lower ground wins; a nudge for south and west (map text upright, sun behind)
    if (!best || score < best.score) best = { score, nxm, nym };
  }
  const r0 = freeRect(), full = r0.h;
  if (!portrait) { r0.y += insetTop; r0.h -= insetTop + insetBottom; }
  const back = Math.pow(full / r0.h, 0.8);                                  // step back when the HUD takes part of the stage
  const mid = 0.5;                                                          // aim between the path and the middle of the block
  return { tx: (cx - world.W / 2) * U * mid, ty: cz * U * EXAG * 0.5, tz: -(cy - world.Hm / 2) * U * mid, theta: Math.atan2(best.nxm, -best.nym),
    phi: 1.1, r: clamp(ext * U * 1.6 + 40, 46, 70) * back * (portrait ? 1.7 : 1), ...shiftFor(r0) };
}

// ------------------------------------------------------------------ things drawn on the mountain
const labels = [], dyn = [];
function clearFx() {
  if (world) { world.fx.traverse((o) => { if (o.geometry) o.geometry.dispose(); }); world.fx.clear(); }
  labels.splice(0).forEach((l) => l.e.remove());
  dyn.length = 0;
}
function label(pos, cls, html, lift = 135) {
  const e = el('div', 'lbl ' + cls, html);
  $('#labels').appendChild(e);
  const L = { e, pos, lift };
  labels.push(L);
  requestAnimationFrame(() => requestAnimationFrame(() => e.classList.add('on')));
  return L;
}
const basic = (color, extra) => new T3.MeshBasicMaterial({ color, fog: false, toneMapped: false, ...extra });
function pin(base, cls, html, color, h = 1.5) {
  const m = new T3.Mesh(new T3.CylinderGeometry(0.022, 0.022, h, 6), basic(hdr(color, 1.25)));
  m.position.copy(base).y += h / 2;
  const knob = new T3.Mesh(new T3.SphereGeometry(0.11, 14, 10), m.material);
  knob.position.copy(base).y += h;
  world.fx.add(m, knob);
  return label(knob.position.clone(), cls, html);
}
/** A path draped on the terrain, parametrised by map distance. xy: [[x, y]] meters. */
function makePath(xy, off) {
  const cum = [0];
  for (let i = 1; i < xy.length; i++) cum.push(cum[i - 1] + Math.hypot(xy[i][0] - xy[i - 1][0], xy[i][1] - xy[i - 1][1]));
  const len = cum[cum.length - 1];
  const xyAt = (f) => {
    const d = clamp(f, 0, 1) * len;
    let lo = 0, hi = cum.length - 1;
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (cum[m] <= d) lo = m; else hi = m; }
    const k = (d - cum[lo]) / Math.max(1e-6, cum[hi] - cum[lo]);
    return [lerp(xy[lo][0], xy[hi][0], k), lerp(xy[lo][1], xy[hi][1], k)];
  };
  const at = (f, o = off) => { const p = xyAt(f); return world.wp(p[0], p[1], o); };
  class Draped extends T3.Curve {
    getPoint(t, target = new T3.Vector3()) { return target.copy(at(t)); }
    getPointAt(t, target) { return this.getPoint(t, target); }
    getTangentAt(t, target = new T3.Vector3()) { return target.copy(at(Math.min(1, t + 0.002))).sub(at(Math.max(0, t - 0.002))).normalize(); }
  }
  return { len, at, xyAt, curve: new Draped() };
}
function tube(path, radius, color, xray = 0.2) {
  const segs = Math.max(24, Math.ceil(path.len / 7));
  const geo = new T3.TubeGeometry(path.curve, segs, radius, 6, false);
  geo.setDrawRange(0, 0);
  const mesh = new T3.Mesh(geo, basic(color));
  world.fx.add(mesh);
  if (xray) {                                                               // a faint copy seen through the ridges, so the line never vanishes
    const ghost = new T3.Mesh(geo, basic(color, { transparent: true, opacity: xray, depthTest: false, depthWrite: false }));
    ghost.renderOrder = 4; world.fx.add(ghost);
  }
  const halos = [[3.2, 0.2], [7, 0.08]].map(([k, op]) => {                  // a soft glow in the line's own colour
    const g = new T3.TubeGeometry(path.curve, segs, radius * k, 8, false);
    g.setDrawRange(0, 0);
    world.fx.add(new T3.Mesh(g, basic(color, { transparent: true, opacity: op, depthWrite: false, blending: T3.AdditiveBlending })));
    return g;
  });
  return { setFrac: (k) => { const n = Math.floor(clamp(k, 0, 1) * segs); geo.setDrawRange(0, n * 36); halos.forEach((g) => g.setDrawRange(0, n * 48)); } };
}
let dotTex = null;
function softDot() {
  if (dotTex) return dotTex;
  const c = document.createElement('canvas'); c.width = c.height = 64;
  const g = c.getContext('2d'), gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(0.35, 'rgba(255,255,255,.55)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = gr; g.fillRect(0, 0, 64, 64);
  return (dotTex = new T3.CanvasTexture(c));
}
function waterParticles(path, n = 220) {
  const pos = new Float32Array(n * 3), seed = [];
  for (let i = 0; i < n; i++) seed.push([Math.random(), (Math.random() - 0.5) * 16, 0.6 + Math.random() * 0.8, Math.random() * 0.1]);
  const geo = new T3.BufferGeometry();
  geo.setAttribute('position', new T3.BufferAttribute(pos, 3));
  const pts = new T3.Points(geo, new T3.PointsMaterial({ color: hdr(C.truth, 1.6), map: softDot(), size: 0.5, transparent: true,
    blending: T3.AdditiveBlending, depthWrite: false, fog: false, toneMapped: false }));
  pts.frustumCulled = false; world.fx.add(pts);
  const st = { frac: 0 };
  dyn.push((t) => {
    for (let i = 0; i < n; i++) {
      const [ph, lat, sp, up] = seed[i];
      const f = ((t * 0.00011 * sp + ph) % 1) * st.frac;
      const a = path.xyAt(f), b = path.xyAt(Math.min(1, f + 0.004));
      const L = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1, w = Math.sin(f * 40 + ph * 9) * lat;
      const p = world.wp(a[0] - ((b[1] - a[1]) / L) * w, a[1] + ((b[0] - a[0]) / L) * w, 0.1 + up);
      pos[3 * i] = p.x; pos[3 * i + 1] = p.y; pos[3 * i + 2] = p.z;
    }
    geo.attributes.position.needsUpdate = true;
  });
  return st;
}
function pulse(center, color, size = 1.3, ms = 1100, repeat = false) {
  const m = new T3.Mesh(new T3.RingGeometry(0.82, 1, 56).rotateX(-Math.PI / 2),
    basic(hdr(color, FX ? 2.4 : 1.1), { transparent: true, depthTest: false, depthWrite: false, blending: T3.AdditiveBlending, side: T3.DoubleSide }));
  m.position.copy(center).y += 0.05; m.renderOrder = 6; world.fx.add(m);
  const t0 = now;
  const fn = (t) => {
    let k = (t - t0) / ms;
    if (repeat) k = k % 1.35; else if (k >= 1) { world.fx.remove(m); m.geometry.dispose(); dyn.splice(dyn.indexOf(fn), 1); return; }
    const e = ease(clamp(k, 0, 1));
    m.scale.setScalar(0.15 + e * size); m.material.opacity = clamp(1 - k, 0, 1);
  };
  dyn.push(fn);
}
function bead(center, color, r = 0.085) {
  const m = new T3.Mesh(new T3.SphereGeometry(r, 12, 8), basic(color));
  m.position.copy(center); world.fx.add(m);
  return m;
}
function dotted(path, color, radius = 0.075, every = 34) {              // the AI's answer: a dotted straight line, not a route it claimed
  const n = Math.max(2, Math.floor(path.len / every));
  const im = new T3.InstancedMesh(new T3.SphereGeometry(radius, 10, 8), basic(color), n);
  const mtx = new T3.Matrix4();
  for (let i = 0; i < n; i++) { mtx.setPosition(path.at((i + 0.5) / n)); im.setMatrixAt(i, mtx); }
  im.count = 0; im.frustumCulled = false; world.fx.add(im);
  const x = new T3.InstancedMesh(im.geometry, basic(color, { transparent: true, opacity: 0.22, depthTest: false, depthWrite: false }), n);
  x.instanceMatrix = im.instanceMatrix; x.count = 0; x.renderOrder = 4; x.frustumCulled = false; world.fx.add(x);
  return { setFrac: (k) => { im.count = x.count = Math.round(clamp(k, 0, 1) * n); } };
}

// ------------------------------------------------------------------ HUD: counter, ruler, elevation profile
function hud(labelText, value, sub = '') {
  $('#hud-label').textContent = labelText; $('#hud-value').textContent = value; $('#hud-sub').textContent = sub; $('#hud').classList.add('on');
}
function hudOff() { $('#hud').classList.remove('on'); $('#profile').classList.remove('on'); $('#ruler').innerHTML = ''; }
/** A scale from lo to hi with ticks, a blue fill for the truth, and flags for what everyone said. */
function ruler({ lo, hi, step, major, fmt, flags }) {
  const R = $('#ruler'); R.innerHTML = '';
  const X = (v) => ((v - lo) / (hi - lo)) * 100;
  R.appendChild(el('div', 'axis'));
  const fill = el('div', 'fill'); R.appendChild(fill);
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) {
    const mj = Math.round(v) % major === 0, t = el('div', 'tick' + (mj ? ' major' : '')); t.style.left = X(v) + '%'; R.appendChild(t);
    if (mj) { const n = el('div', 'num', fmt(v)); n.style.left = X(v) + '%'; R.appendChild(n); }
  }
  const merged = [];
  for (const f of flags) {
    const m = merged.find((g) => g.cls === f.cls && Math.abs(g.v - f.v) < 1e-9);
    if (m) m.who += ' + ' + f.who; else merged.push({ ...f });
  }
  merged.sort((a, b) => a.v - b.v);
  let lastX = -99, level = 0;
  const made = merged.map((f) => {
    const x = clamp(X(f.v), 0, 100);
    level = x - lastX < 17 ? (level + 1) % 3 : 0; lastX = x;
    const e = el('div', 'flag ' + f.cls, `<span>${esc(f.who)}<b>${esc(f.text)}</b></span>`);
    e.style.left = x + '%'; e.style.setProperty('--h', 12 + level * 24 + 'px');
    if (f.hidden) e.style.visibility = 'hidden';
    R.appendChild(e);
    return { ...f, e };
  });
  return { set: (v) => { fill.style.width = clamp(X(v), 0, 100) + '%'; }, show: (cls) => made.filter((m) => m.cls === cls).forEach((m) => { m.e.style.visibility = 'visible'; }) };
}
function profile(task) {
  const P = $('#profile'), tr = task.truth, w = P.clientWidth - 30, h = P.clientHeight - 20, padL = 44, padT = 16, padB = 4;
  const zs = tr.profile.map((p) => p[1]), z0 = Math.min(...zs) - 8, z1 = Math.max(...zs) + 8, L = tr.length_m;
  const X = (a) => padL + (a / L) * (w - padL - 6), Y = (z) => padT + (1 - (z - z0) / (z1 - z0)) * (h - padT - padB);
  const d = tr.profile.map((p, i) => (i ? 'L' : 'M') + X(p[0]).toFixed(1) + ' ' + Y(p[1]).toFixed(1)).join('');
  let s = `<svg width="${w}" height="${h}"><text class="ttl" x="0" y="9">Elevation along the ${esc(task.trail_name)} · ${num(L)} m · contour lines every ${task.contour_interval_m} m</text>`;
  for (let lv = Math.ceil(z0 / task.contour_interval_m) * task.contour_interval_m; lv <= z1; lv += task.contour_interval_m) {
    const idx = lv % task.index_interval_m === 0;
    s += `<line x1="${padL}" x2="${w - 6}" y1="${Y(lv)}" y2="${Y(lv)}" stroke="rgba(243,238,223,${idx ? 0.42 : 0.16})" stroke-width="1"/>`;
    if (idx) s += `<text x="${padL - 6}" y="${Y(lv) + 3}" text-anchor="end">${lv} m</text>`;
  }
  s += `<path d="${d}" fill="none" stroke="rgba(243,238,223,.3)" stroke-width="1"/>`;
  s += `<clipPath id="pc"><rect id="pcr" x="0" y="0" width="0" height="${h}"/></clipPath><path d="${d}" fill="none" stroke="${C.truth}" stroke-width="2" clip-path="url(#pc)"/><g id="pdots"></g></svg>`;
  P.innerHTML = s; P.classList.add('on');
  const rect = P.querySelector('#pcr'), dots = P.querySelector('#pdots');
  return {
    set: (f) => rect.setAttribute('width', X(f * L)),
    dot: (c, solid) => {
      const z = c.level;
      dots.insertAdjacentHTML('beforeend', `<circle cx="${X(c.arc)}" cy="${Y(z)}" r="3.2" fill="${solid ? C.truth : C.night}" stroke="${C.truth}" stroke-width="1.2"/>`);
    },
  };
}

// ------------------------------------------------------------------ score keeping (this browser only)
const store = (() => { try { return JSON.parse(localStorage.getItem('mvm.v1') || '{}'); } catch (e) { return {}; } })();
function record(task, you, youRight) {
  store[task.id] = { you: you == null ? null : !!youRight, models: Object.fromEntries(task.models.map((m) => [m.name, m.correct])) };
  try { localStorage.setItem('mvm.v1', JSON.stringify(store)); } catch (e) { /* private mode */ }
  tally();
}
function tally() {
  const ids = Object.keys(store), names = [...new Set(IDX.tasks.flatMap((t) => t.models.map((m) => m.name)))];
  const yA = ids.filter((i) => store[i].you != null), yC = yA.filter((i) => store[i].you);
  let h = `<span class="you">YOU ${yC.length}/${yA.length}</span>`;
  for (const n of names) { const p = ids.filter((i) => n in store[i].models); h += `<span class="ai">${n} ${p.filter((i) => store[i].models[n]).length}/${p.length}</span>`; }
  $('#tally').innerHTML = h;
  document.querySelectorAll('#missions button').forEach((b) => b.classList.toggle('done', b.dataset.id in store));
}

// ------------------------------------------------------------------ the panel: question, then score card
const panel = $('#panel');
function showPanel(on) { document.body.classList.toggle('panel-on', on); }
const unit = (task) => (task.template === 'crossings' ? 'lines' : task.template === 'sunset' ? 'min' : '');
function shortQuestion(task) {
  const m = task.mission;
  if (task.template === 'flood') return `The dam at <b>D</b> has failed. Water runs straight downhill, crossing every contour line at a right angle. Which campsite, ${m.camps[0]} to ${m.camps[m.camps.length - 1]}, does it reach?`;
  if (task.template === 'crossings') return `A stretcher team carries a casualty along the ${esc(task.trail_name)} from <b>${m.from}</b> to <b>${m.to}</b>. How many contour lines does the trail cross? Count every crossing, index lines included.`;
  return `A lost hiker at <b>${m.from}</b> must reach the hut at <b>${m.to}</b> along the ${esc(task.trail_name)}. The box on the map gives the time now, sunset, and the walking time on the flat. Add ${m.minutes_per_uphill_contour} minutes for every contour line crossed going uphill. How many minutes before sunset does the hiker arrive? Negative if after dark.`;
}
/** The flat map and the question. Resolves with the player's answer (a string) or null. */
function play(task, i, ms) {
  const done = gate();
  const stepper = task.template !== 'flood';
  let val = task.template === 'crossings' ? 10 : 0;
  panel.innerHTML = `
    <div class="cap kicker"><span>Mission ${String(i + 1).padStart(2, '0')} / ${String(playlist.length).padStart(2, '0')}</span><span>${esc(task.area)}</span></div>
    <h2>${MISSION[task.template].name}</h2>
    <div class="q serif">${shortQuestion(task)}</div>
    <div class="rule"></div>
    ${stepper
      ? `<div class="stepper"><button data-d="-5">−5</button><button data-d="-1">−1</button><div class="val mono" id="val">${val}</div><button data-d="1">+1</button><button data-d="5">+5</button></div>
         <button class="lock" id="lock">Lock in ${unit(task)}</button>`
      : `<div class="answers">${task.mission.camps.map((c) => `<button data-a="${c}">${c}</button>`).join('')}</div>`}
    <div class="timer mono"><span id="tsec"></span><div class="bar"><i id="tbar"></i></div></div>
    <button class="link" id="fullq">The full question the models got ▸</button>
    <div class="fine" id="fine">${esc(task.question)}<br><br>Sent with the image at temperature 0, reasoning effort high.</div>
    <button class="link" id="skip">Skip to the reveal ▸</button>`;
  const timer = tween(ms, (k) => { $('#tsec').textContent = '0:' + String(Math.ceil((ms * (1 - k)) / 1000)).padStart(2, '0'); $('#tbar').style.width = (1 - k) * 100 + '%'; }, linear);
  const finish = (v) => { timer.stop(); keyHook = null; done.done(v); };
  timer.then(() => finish(null), () => {});
  panel.querySelectorAll('[data-a]').forEach((b) => (b.onclick = () => { b.classList.add('sel'); finish(b.dataset.a); }));
  const bump = (d) => { val = clamp(val + d, -99, 99); $('#val').textContent = val; };
  panel.querySelectorAll('[data-d]').forEach((b) => (b.onclick = () => bump(+b.dataset.d)));
  if (stepper) $('#lock').onclick = () => finish(String(val));
  $('#fullq').onclick = () => $('#fine').classList.toggle('on');
  $('#skip').onclick = () => finish(null);
  keyHook = (e) => {
    if (!stepper && /^[1-9]$/.test(e.key) && task.mission.camps[+e.key - 1]) finish(task.mission.camps[+e.key - 1]);
    else if (stepper && e.key === 'ArrowUp') bump(1); else if (stepper && e.key === 'ArrowDown') bump(-1);
    else if (stepper && e.key === 'Enter') finish(String(val)); else return false;
    return true;
  };
  showPanel(true);
  return done;
}
function scoreCard(task, you, note) {
  const u = unit(task), right = you != null && String(you) === String(task.answer);
  const row = (cls, who, mark, val) => `<div class="line ${cls}"><div class="who">${who}</div><div class="mark">${mark}</div><div class="val">${val}${u && val !== '—' ? `<small>${u}</small>` : ''}</div></div>`;
  panel.innerHTML = `
    <div class="cap kicker"><span>Score card</span><span>${esc(task.id)}</span></div>
    <h2>${MISSION[task.template].name}</h2>
    <div class="card">
      ${row('you', 'You', you == null ? '' : right ? '✓' : '✗', you == null ? '—' : esc(you))}
      ${row('truth', 'Computed', '', esc(task.answer))}
      ${task.models.map((m) => row('ai', esc(m.name), m.status !== 'ok' ? '' : m.correct ? '✓' : '✗', m.status === 'ok' ? esc(m.parsed) : '—')).join('')}
    </div>
    <div class="note serif">${note}</div>
    <div class="how">Computed from the elevation data by two independent solvers. Seed ${task.seed} · ${esc(task.generator_version)} · difficulty ${task.difficulty} · ${task.draws_discarded} unfair draw${task.draws_discarded === 1 ? '' : 's'} discarded first.</div>
    <div class="row"><button class="ghostbtn primary" id="next">Next mission →</button><button class="ghostbtn" id="again">Replay</button></div>
    ${task.models.map((m, k) => `<button class="link" data-r="${k}">Read ${esc(m.name)}'s reply ▸</button><div class="reply" id="reply${k}">${esc(m.reply)}</div>`).join('')}`;
  $('#next').onclick = () => go((cur + 1) % playlist.length);
  $('#again').onclick = () => go(cur);
  panel.querySelectorAll('[data-r]').forEach((b) => (b.onclick = () => $('#reply' + b.dataset.r).classList.toggle('on')));
  const lines = [...panel.querySelectorAll('.card .line')];
  return { reveal: async (k) => { lines[k] && lines[k].classList.add('on'); }, all: () => { lines.forEach((l) => l.classList.add('on')); record(task, you, right); }, note: () => panel.querySelector('.note').classList.add('on') };
}
const andList = (a) => (a.length < 2 ? a.join('') : a.slice(0, -1).join(', ') + ' and ' + a[a.length - 1]);

// ------------------------------------------------------------------ reveals
async function liftMountain(view) {
  hudOff();
  await Promise.all([tween(1500, (k) => setLook({ lift: k, film: k })), camTo(view, 2600)]);
}
async function revealFlood(task, you) {
  const P = Object.fromEntries(task.points.map((p) => [p.name, p])), dam = P.D, ans = task.answer;
  const route = makePath(task.truth.water_route, 0.1);
  const wrong = {};                                                          // camp -> the models that chose it
  for (const m of task.models) if (m.status === 'ok' && P[m.parsed]) (wrong[m.parsed] = wrong[m.parsed] || []).push(m);
  const distOf = Object.fromEntries(task.steps.camps.map((c) => [c.camp, c.distance_to_water_route_m]));
  const notes = Object.entries(wrong).map(([camp, ms]) => camp === ans
    ? `${andList(ms.map((m) => cap(m.name)))} followed the water to ${camp}.`
    : `${andList(ms.map((m) => cap(m.name)))} chose ${camp}, ${num(distOf[camp])} m from the water’s path.`);
  const card = scoreCard(task, you, `The water runs ${num(task.steps.water_route_length_m)} m from the dam and reaches ${ans}. ${notes.join(' ')}`);
  const framing = [...task.truth.water_route, ...Object.keys(wrong).map((c) => [P[c].x, P[c].y])];
  await liftMountain(sideView(framing, 70, 0));
  hud('Water path from the dam', '0 m', `dam at D · ${num(task.steps.dam_elev_m)} m`);
  label(world.wp(dam.x, dam.y, 0.9), 'plain', 'Dam D', 100);
  if (you && P[you]) { pin(world.wp(P[you].x, P[you].y), 'you', `You<b>${esc(you)}</b>`, C.you, 2.5); card.reveal(0); }
  await wait(500);
  const t = tube(route, 0.085, hdr(C.truth)), parts = waterParticles(route);
  await tween(4600, (k) => { t.setFrac(k); parts.frac = k; $('#hud-value').textContent = num(k * task.steps.water_route_length_m) + ' m'; }, (x) => x * x * (3 - 2 * x));
  const hit = world.wp(P[ans].x, P[ans].y);
  pulse(hit, C.truth, 1.5, 1500, true);
  pin(hit, 'truth', `${esc(ans)} floods`, C.truth, 1.9);
  $('#hud-sub').textContent = `reaches ${ans} · ${num(task.steps.camps.find((c) => c.camp === ans).elev_m)} m`;
  card.reveal(0); card.reveal(1);
  await wait(900);
  let row = 2;
  for (const [camp, ms] of Object.entries(wrong)) {
    const who = ms.map((m) => m.name).join(' + ');
    if (camp !== ans) {
      const line = dotted(makePath([[dam.x, dam.y], [P[camp].x, P[camp].y]], 0.14), hdr(C.model));
      await tween(900, (k) => line.setFrac(k), linear);
      pulse(world.wp(P[camp].x, P[camp].y), C.model, 1.1, 1200);
    }
    pin(world.wp(P[camp].x, P[camp].y), 'ai', `${esc(who)}<b>${esc(camp)} ${camp === ans ? '✓' : '✗'}</b>`, C.model, camp === ans ? 2.9 : 1.6);
    ms.forEach(() => card.reveal(row++));
    await wait(500);
  }
  card.all(); card.note();
}
const cap = (s) => s.charAt(0) + s.slice(1).toLowerCase();
const clockStr = (min) => `${String(Math.floor(min / 60)).padStart(2, '0')}:${String(Math.round(min) % 60).padStart(2, '0')}`;
async function revealTrail(task, you) {
  const tr = task.truth, m = task.mission, sunset = task.template === 'sunset', st = task.steps;
  const cross = tr.crossings, N = cross.length, up = cross.filter((c) => c.uphill).length;
  const said = task.models.filter((x) => x.status === 'ok' && x.parsed !== '' && !isNaN(+x.parsed));
  let note;
  if (!sunset) {
    note = `The trail crosses ${N} contour lines. ` + said.map((x) => `${cap(x.name)} counted ${x.parsed}`).join(', ') + '.';
  } else {
    const spare = +task.answer;
    note = `The hiker climbs ${up} contour line${up === 1 ? '' : 's'} and reaches the hut at ${st.arrival}, ${Math.abs(spare)} minute${Math.abs(spare) === 1 ? '' : 's'} ${spare < 0 ? 'after' : 'before'} sunset. ` +
      said.map((x) => `${cap(x.name)} said ${x.parsed}`).join(', ') + '.';
  }
  const card = scoreCard(task, you, note);
  await liftMountain(sideView(tr.route, 150, 150));
  const path = makePath(tr.route, 0.1);
  const P = Object.fromEntries(task.points.map((p) => [p.name, p]));
  label(world.wp(P[m.from].x, P[m.from].y, 0.7), 'plain', m.from, 100); label(world.wp(P[m.to].x, P[m.to].y, 0.7), 'plain', m.to, 100);
  const prof = profile(task);
  let R, daylight = 0;
  if (!sunset) {
    const flags = said.map((x) => ({ v: +x.parsed, cls: 'ai', who: x.name, text: x.parsed }));
    if (you != null) flags.push({ v: +you, cls: 'you', who: 'You', text: String(you) });
    const hi = Math.max(N, ...flags.map((f) => f.v)) + 1;
    R = ruler({ lo: 0, hi, step: 1, major: 5, fmt: (v) => String(v), flags });
    hud('Contour lines crossed', '00', `${esc(task.trail_name)} · ${m.from} to ${m.to}`);
  } else {
    daylight = m.sunset_min - m.now_min;
    const flags = said.map((x) => ({ v: daylight - +x.parsed, cls: 'ai', who: x.name, text: (+x.parsed >= 0 ? '+' : '') + x.parsed }));
    if (you != null) flags.push({ v: daylight - +you, cls: 'you', who: 'You', text: (+you >= 0 ? '+' : '') + you });
    flags.push({ v: daylight, cls: 'plain', who: 'Sunset', text: clockStr(m.sunset_min) });
    flags.push({ v: st.walking_minutes, cls: 'truth', who: 'Arrives', text: st.arrival, hidden: true });
    const lo = Math.min(0, ...flags.map((f) => f.v)), hi = Math.max(...flags.map((f) => f.v)) + 6;
    R = ruler({ lo, hi, step: 5, major: 15, fmt: (v) => clockStr(m.now_min + v), flags });
    hud('Clock on the trail', clockStr(m.now_min), `sunset ${clockStr(m.sunset_min)} · ${m.flat_walk_min} min on the flat`);
  }
  if (you != null) card.reveal(0);
  await wait(500);
  const t = tube(path, 0.07, hdr(C.truth)), walker = bead(path.at(0, 0.16), new T3.Color(0.55, 0.85, 1.0).multiplyScalar(FX ? 3.2 : 1), 0.15);
  let ci = 0, count = 0, ups = 0;
  const dur = clamp(N * 560, 6000, 11000);
  await tween(dur, (k) => {
    t.setFrac(k); walker.position.copy(path.at(k, 0.16)); prof.set(k);
    while (ci < N && cross[ci].arc / tr.length_m <= k) {
      const c = cross[ci++], at = world.wp(c.x, c.y, 0.12);
      count++;
      if (!sunset || c.uphill) { ups += c.uphill ? 1 : 0; pulse(at, C.truth, 0.9, 1000); bead(at, new T3.Color(0.45, 0.78, 1.0).multiplyScalar(FX ? 2.6 : 1)); prof.dot(c, true); }
      else { bead(at, hdr(C.truth, 0.5), 0.06); prof.dot(c, false); }
      if (!sunset) { $('#hud-value').textContent = String(count).padStart(2, '0'); $('#hud-sub').textContent = `line ${count} · the ${c.level} m contour`; R.set(count); }
    }
    if (sunset) {
      const mins = m.flat_walk_min * k + m.minutes_per_uphill_contour * ups;
      $('#hud-value').textContent = clockStr(m.now_min + mins);
      $('#hud-sub').textContent = `${ups} uphill line${ups === 1 ? '' : 's'} × ${m.minutes_per_uphill_contour} min · sunset ${clockStr(m.sunset_min)}`;
      R.set(mins); setLook({ dusk: clamp((mins - (daylight - 45)) / 45, 0, 1) * 0.9 });
    }
  }, linear);
  if (sunset) {
    R.show('truth');
    const spare = +task.answer;
    hud(spare < 0 ? 'Arrives after dark' : 'Arrives before sunset', st.arrival, `${Math.abs(spare)} min ${spare < 0 ? 'after' : 'before'} sunset at ${clockStr(m.sunset_min)}`);
  } else {
    $('#hud-sub').textContent = said.map((x) => `${x.name} said ${x.parsed}`).join(' · ');
  }
  pulse(path.at(1, 0.1), C.truth, 1.5, 1500, true);
  card.reveal(0); card.reveal(1);
  await wait(700);
  for (let k = 0; k < task.models.length; k++) { card.reveal(2 + k); await wait(450); }
  card.all(); card.note();
}

// ------------------------------------------------------------------ cold open
function say(text, on = true) { const c = $('#caption'); if (text != null) c.textContent = text; c.classList.toggle('on', on); }
async function introFlight() {
  const top = topState(), hm = world.hmax, D = top.r;
  const [sx, sy] = world.summit, S = world.wp(sx, sy);
  const pts = [
    [-27, Math.max(1.7, 0.2 * hm + 1.3), 14.5], [-13.5, 0.5 * hm + 1.5, 9], [-2, 0.9 * hm + 2.2, 13], [12, 1.05 * hm + 3.4, 12.5],
    [23, 1.3 * hm + 6.5, 3], [15, 1.5 * hm + 15, 15], [top.tx + 1.5, D * 0.74, top.tz + D * 0.4], [top.tx, D * Math.cos(top.phi), top.tz + D * Math.sin(top.phi)],
  ].map((p) => new T3.Vector3(...p));
  const flight = new T3.CatmullRomCurve3(pts, false, 'centripetal');
  const t0 = new T3.Vector3(S.x * 0.7, S.y * 0.75, S.z * 0.7), t1 = new T3.Vector3(0, hm * 0.25, 0), t2 = new T3.Vector3(top.tx, 0, top.tz);
  const target = new T3.Vector3(), p = new T3.Vector3();
  controls.enabled = false; camMode = 'free';
  setLook({ lift: 1, film: 1, dusk: 0 });
  document.body.classList.add('cine');
  const lock = $('#lockup');
  lock.className = '';
  tween(500, () => {}).then(() => lock.classList.add('in'), () => {});
  tween(4700, () => {}).then(() => lock.classList.add('part'), () => {});
  tween(6300, () => {}).then(() => { say('This is what the AI sees.'); document.body.classList.remove('cine'); }, () => {});
  await tween(8000, (_, k) => {
    const u = 1 - Math.pow(1 - k, 1.9);
    flight.getPoint(u, p);
    const inside = Math.abs(p.x) < 16 && Math.abs(p.z) < 12;
    if (inside) p.y = Math.max(p.y, world.elev(p.x / U + world.W / 2, -p.z / U + world.Hm / 2) * U * EXAG * look.lift + 1.3);
    const a = glide(clamp(u / 0.55, 0, 1)), b = glide(clamp((u - 0.5) / 0.42, 0, 1));
    target.copy(t0).lerp(t1, a).lerp(t2, b);
    camera.position.copy(p); camera.up.set(0, 1, 0); camera.lookAt(target);
    const flat = glide(clamp((k - 0.66) / 0.3, 0, 1));
    setLook({ lift: 1 - flat, film: 1 - flat });
    applyShift(top.sx * b, top.sy * b);
  }, linear);
  Object.assign(cam, top); camMode = 'state';
  setLook({ lift: 0, film: 0 });
  lock.className = '';
}

// ------------------------------------------------------------------ chapters (show mode): the factory and the results
const CHECKS = {
  schema: ['Schema', 'Every file follows the contract'],
  data_first: ['Data first', 'The data exists before the image; the image is drawn from it'],
  two_solvers: ['Two solvers', 'The answer is computed two independent ways, and they agree'],
  render_matches_data: ['Render matches data', 'Marks and labels read back from the picture match the data'],
  legibility: ['Legibility', 'No two labels overlap; nothing is hidden'],
  answer_not_in_question: ['Answer not in question', 'The question never gives the answer away'],
  reproducible: ['Reproducible', 'The same seed rebuilds the same image'],
};
async function chapterFactory() {
  const sets = IDX.sets.filter((s) => s.validation);
  if (!sets.length) return;
  const sum = (f) => sets.reduce((a, s) => a + f(s.validation), 0);
  const names = sets[0].validation.checks.map((c) => c.name);
  const discarded = IDX.tasks.reduce((a, t) => a + (t.draws_discarded || 0), 0);
  const ch = $('#chapter');
  ch.innerHTML = `<div class="sheet">
    <h1>The factory · seven checks</h1>
    <div class="lead serif">Every map is drawn from elevation data by code. Before a model sees it, it has to pass all seven.</div>
    <div class="frame">${names.map((n, i) => {
      const p = sum((v) => v.checks.find((c) => c.name === n).passed), f = sum((v) => v.checks.find((c) => c.name === n).failed);
      return `<div class="gate"><div class="n">${String(i + 1).padStart(2, '0')}</div><div class="name">${esc((CHECKS[n] || [n])[0])}</div><div class="what serif">${esc((CHECKS[n] || [, ''])[1])}</div><div class="cnt">${p} / ${p + f} ✓</div></div>`;
    }).join('')}</div>
    <div class="totals">
      <div><b>${sum((v) => v.attempted)}</b>maps generated</div>
      <div><b>${sum((v) => v.all_passed)}</b>passed all seven</div>
      <div><b>${discarded}</b>unfair draws the generator threw away<br>before the ${IDX.tasks.length} maps on this page</div>
    </div></div>`;
  ch.classList.add('on');
  const gates = [...ch.querySelectorAll('.gate')];
  await wait(1600);
  for (const g of gates) { g.classList.add('on'); await wait(950); }
  await wait(3200);
}
async function chapterResults() {
  const score = {};
  for (const s of IDX.sets) for (const [tpl, ms] of Object.entries(s.score || {})) for (const [k, v] of Object.entries(ms)) {
    const c = ((score[tpl] = score[tpl] || {})[k] = score[tpl][k] || { name: v.name, correct: 0, scored: 0 });
    c.correct += v.correct; c.scored += v.scored;
  }
  const tpls = Object.keys(MISSION).filter((t) => score[t]);
  if (!tpls.length) return;
  const cols = Object.keys(score[tpls[0]]);
  const run = (IDX.sets.find((s) => s.run) || {}).run;
  const ch = $('#chapter');
  ch.innerHTML = `<div class="sheet">
    <h1>The results · real runs</h1>
    <div class="lead serif">They read the map. They don’t trace it.</div>
    <div class="frame"><div class="res">
      <div class="h">Mission</div>${cols.map((c) => `<div class="h ai">${esc(score[tpls[0]][c].name)}</div>`).join('')}
      ${tpls.map((t) => `<div class="m">${MISSION[t].name}<small>${MISSION[t].blurb}</small></div>` +
        cols.map((c) => { const v = score[t][c] || { correct: 0, scored: 0 }; return `<div class="s">${v.correct}<small> / ${v.scored}</small><i data-w="${v.scored ? (100 * v.correct) / v.scored : 0}"></i></div>`; }).join('')).join('')}
    </div></div>
    <div class="how">${run ? `temperature ${run.temperature} · reasoning effort ${esc((run.reasoning || {}).effort || '')} · max_tokens ${run.max_tokens} · ` : ''}from ${IDX.sets.map((s) => esc(s.results)).filter(Boolean).join(', ')}</div>
  </div>`;
  ch.querySelector('.res').style.gridTemplateColumns = `1.3fr ${cols.map(() => '1fr').join(' ')}`;
  ch.classList.add('on');
  await wait(500);
  ch.querySelectorAll('.s i').forEach((b) => (b.style.width = b.dataset.w + '%'));
  await wait(9500);
}

// ------------------------------------------------------------------ flow
const playlist = (() => {                             // interleave the missions: flood, carry, hiker, flood, ...
  const by = {};
  for (const t of IDX.tasks) (by[t.template] = by[t.template] || []).push(t);
  const out = [], keys = Object.keys(MISSION).filter((k) => by[k]);
  for (let i = 0; keys.some((k) => by[k][i]); i++) for (const k of keys) if (by[k][i]) out.push(by[k][i]);
  return out;
})();
let cur = 0, showMode = false, keyHook = null;
function nav() {
  const n = $('#missions'); n.innerHTML = '';
  playlist.forEach((t, i) => {
    const b = el('button', i === cur ? 'on' : ''); b.dataset.id = t.id; b.title = `${MISSION[t.template].name} · ${t.area} · seed ${t.seed}`;
    b.onclick = () => go(i); n.appendChild(b);
  });
  tally();
}
const dms = (v, lon) => { const h = lon ? (v < 0 ? 'W' : 'E') : v < 0 ? 'S' : 'N'; v = Math.abs(v); const s = Math.round((v - Math.floor(v)) * 3600); return `${Math.floor(v)}°${String(Math.floor(s / 60)).padStart(2, '0')}'${String(s % 60).padStart(2, '0')}"${h}`; };
function collar(task) {
  const b = task.bounds;
  $('#quad').textContent = `${task.area} quadrangle · ${task.state} · elevation: USGS 3DEP`;
  $('#coords').innerHTML = `${dms(b.south, 0)} ${dms(b.west, 1)} — ${dms(b.north, 0)} ${dms(b.east, 1)}<br>${num(task.elev_min_m)} m to ${num(task.elev_max_m)} m · seed ${task.seed}`;
}
function resetStage() {
  clearFx(); hudOff(); say(null, false); showPanel(false);
  $('#chapter').classList.remove('on'); $('#lockup').className = ''; document.body.classList.remove('cine');
  controls.enabled = false; keyHook = null;
}
async function runTask(i, { intro = false, playMs = 60000 } = {}) {
  const my = epoch;
  cur = i; nav();
  const task = await loadTask(playlist[i].id); alive(my);
  if (!intro) { $('#fade').classList.add('on'); await wait(380); }
  resetStage();
  await buildWorld(task); alive(my);
  collar(task);
  if (intro) {
    $('#fade').classList.remove('on');
    await introFlight();
  } else {
    setLook({ lift: 0, film: 0, dusk: 0 });
    showPanel(true);
    Object.assign(cam, topState()); camMode = 'state';
    $('#fade').classList.remove('on');
  }
  const answering = play(task, i, playMs);
  tween(2600, () => {}).then(() => say(null, false), () => {});
  const you = await answering;
  say(null, false);
  await (task.template === 'flood' ? revealFlood(task, you) : revealTrail(task, you));
  freeOrbit();
}
function go(i, opts) {
  cancelAll(); showMode = false;
  runTask(i, opts).catch((e) => { if (e !== CANCEL) throw e; });
}
async function runShow() {                            // S: the 90-second tour for the pitch
  cancelAll(); showMode = true;
  const first = (tpl) => Math.max(0, playlist.findIndex((t) => t.template === tpl));
  try {
    await runTask(first('flood'), { intro: true, playMs: 10000 });
    await wait(5000);
    await runTask(first('crossings'), { playMs: 8000 });
    await wait(5000);
    $('#fade').classList.add('on'); await wait(400);
    resetStage(); $('#fade').classList.remove('on');
    await chapterFactory();
    await chapterResults();
    showMode = false;
    go(first('flood'), { intro: true });
  } catch (e) { if (e !== CANCEL) throw e; }
}
addEventListener('keydown', (e) => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  if (keyHook && keyHook(e)) { e.preventDefault(); return; }
  const k = e.key.toLowerCase();
  if (k === 's') runShow();
  else if (k === 'r') go(0, { intro: true });
  else if (k === 'f') { if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen().catch(() => {}); }
  else if (k === 'n' || k === 'arrowright') go((cur + 1) % playlist.length);
  else if (k === 'arrowleft') go((cur + playlist.length - 1) % playlist.length);
});

// ------------------------------------------------------------------ frame loop
function resize() {
  vw = window.innerWidth; vh = window.innerHeight; portrait = vw / vh < 1;
  document.body.classList.toggle('portrait', portrait);
  renderer.setSize(vw, vh);
  if (composer) { composer.setPixelRatio(renderer.getPixelRatio()); composer.setSize(vw, vh); }
  camera.aspect = vw / vh; camera.updateProjectionMatrix();
  if (world && camMode === 'state' && look.lift === 0) Object.assign(cam, topState());
  else if (world) { const s = shiftFor(freeRect()); cam.sx = s.sx; cam.sy = s.sy; if (camMode === 'free') applyShift(s.sx, s.sy); }
}
addEventListener('resize', resize);
const v3 = new T3.Vector3();
function frame() {
  requestAnimationFrame(frame);
  now = performance.now() * SPEED;
  for (const a of [...active]) {
    if (!active.has(a)) continue;
    const k = clamp((now - a.t0) / a.ms, 0, 1);
    a.fn(a.e(k), k);
    if (k >= 1 && active.delete(a)) a.res();
  }
  if (!world) return;
  if (controls.enabled) controls.update(); else if (camMode === 'state') applyCam();
  for (const d of [...dyn]) d(now);
  sky.position.copy(camera.position);
  camera.updateMatrixWorld();
  for (const L of labels) {
    v3.copy(L.pos).project(camera);
    L.e.style.display = v3.z > 1 ? 'none' : '';
    L.e.style.transform = `translate(${((v3.x * 0.5 + 0.5) * vw).toFixed(1)}px, ${((-v3.y * 0.5 + 0.5) * vh).toFixed(1)}px) translate(-50%, -${L.lift}%)`;
  }
  if (composer) { finalPass.uniforms.uTime.value = now * 0.001; composer.render(); } else renderer.render(scene, camera);
}

// ------------------------------------------------------------------ boot
async function boot() {
  document.body.classList.add('loading');
  resize(); frame();
  if (!playlist.length) { $('#load-note').textContent = 'No tasks found. Run: uv run python site-fable/build.py'; return; }
  const want = Q.get('task'), start = Math.max(0, playlist.findIndex((t) => t.id === want));
  const meta = playlist[start];
  const fonts = document.fonts ? document.fonts.ready : Promise.resolve();
  const counting = tween(1500, (k) => { $('#load-elev').textContent = num(k * meta.elev_max_m) + ' m'; $('#load-bar').style.width = k * 100 + '%'; });
  await Promise.all([loadTask(meta.id), fonts, counting]);
  $('#load-note').textContent = `${meta.area} · ${meta.state}`;
  await wait(350);
  nav();
  const p = Q.get('show') === '1' ? runShow() : runTask(start, { intro: Q.get('intro') !== '0', playMs: 60000 });
  $('#loader').classList.add('off'); document.body.classList.remove('loading');
  p.catch((e) => { if (e !== CANCEL) throw e; });
}
window.MVM = { go, runShow, look, cam, get world() { return world; } };
boot();
})();
