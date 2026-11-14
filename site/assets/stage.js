/* The 3D stage: "The map vs the mountain".
   The task's elevation grid becomes a mesh; the exact map frame the models saw is draped on it. The camera can sit
   exactly top-down so the 3D scene matches the 2D map pixel for pixel, then the map lifts into the mountain and the
   truth is animated on it (blue), with the models' answers as red ghosts. three.js is pinned in the page's import map. */
(function () {
  "use strict";
  const TRUTH = 0x2f7fc1, TRUTH_GLOW = 0x7fc0ff, MODEL = 0xd2412c, MODEL_GLOW = 0xff7a5c, SUN = 0xffd2a1;
  const NIGHT = 0x0e1116;
  const Ww = 100, EX = 1.6;                          // world width of the map; vertical exaggeration

  // cubic-bezier(0.2, 0.7, 0.2, 1), solved for x by Newton steps
  function bezier(x1, y1, x2, y2) {
    const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
    const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
    const sx = (t) => ((ax * t + bx) * t + cx) * t, sy = (t) => ((ay * t + by) * t + cy) * t;
    const dx = (t) => (3 * ax * t + 2 * bx) * t + cx;
    return (x) => {
      if (x <= 0) return 0;
      if (x >= 1) return 1;
      let t = x;
      for (let i = 0; i < 8; i++) { const e = sx(t) - x, d = dx(t); if (Math.abs(e) < 1e-5 || !d) break; t -= e / d; }
      return sy(Math.min(1, Math.max(0, t)));
    };
  }
  const EASE = bezier(0.2, 0.7, 0.2, 1);
  const INOUT = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function decodeGrid(g) {
    const bin = atob(g.data), n = g.cols * g.rows, out = new Float32Array(n);
    const span = (g.zmax - g.zmin) / 65535;
    for (let i = 0; i < n; i++) out[i] = g.zmin + (bin.charCodeAt(2 * i) | (bin.charCodeAt(2 * i + 1) << 8)) * span;
    return out;
  }

  async function create(host, task, opts) {
    opts = opts || {};
    const THREE = await import("three");
    const { OrbitControls } = await import("three/addons/controls/OrbitControls.js");

    const g = task.grid, cols = g.cols, rows = g.rows;
    const [Wm, Hm] = task.extent_m;
    const Hw = (Ww * Hm) / Wm, mpu = Wm / Ww;
    const Zm = decodeGrid(g);
    const H = new Float32Array(Zm.length);
    for (let i = 0; i < Zm.length; i++) H[i] = ((Zm[i] - g.zmin) / mpu) * EX;
    const units = (m) => (m / mpu) * EX;            // meters of height -> world units
    let morph = 0;

    // ---------------------------------------------------------------- renderer, scene, camera
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;
    renderer.setClearColor(NIGHT, 0);
    host.prepend(renderer.domElement);
    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x2b2622, 0);
    const camera = new THREE.PerspectiveCamera(35, 1, 0.5, 3000);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enabled = false;
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.maxPolarAngle = Math.PI * 0.47;
    controls.minDistance = 25;
    controls.maxDistance = 320;
    controls.autoRotateSpeed = 0.45;
    controls.addEventListener("start", () => { controls.autoRotate = false; });

    // dusk sky: a big inverted sphere with a vertical gradient (fog-free), only visible once the stage is lit
    const skyGeo = new THREE.SphereGeometry(1400, 32, 16);
    const skyMat = new THREE.ShaderMaterial({
      side: THREE.BackSide, depthWrite: false, fog: false, transparent: true,
      uniforms: { top: { value: new THREE.Color(NIGHT) }, horizon: { value: new THREE.Color(0xc9a27a) },
                  opacity: { value: 0 } },
      vertexShader: "varying vec3 vP; void main(){ vP = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }",
      fragmentShader: "uniform vec3 top; uniform vec3 horizon; uniform float opacity; varying vec3 vP;" +
        "void main(){ float y = vP.y - 0.02; float glow = exp(-abs(y) * (y > 0.0 ? 7.0 : 14.0));" +
        " vec3 c = mix(top, horizon, glow * 0.85); gl_FragColor = vec4(c, opacity); }",
    });
    const sky = new THREE.Mesh(skyGeo, skyMat);
    scene.add(sky);

    const hemi = new THREE.HemisphereLight(0xfff1de, 0x4a3524, 0);
    scene.add(hemi);
    const sun = new THREE.DirectionalLight(SUN, 0);
    sun.position.set(-90, 38, 12);                  // low, from the west
    scene.add(sun);

    // ---------------------------------------------------------------- terrain
    const geo = new THREE.PlaneGeometry(Ww, Hw, cols - 1, rows - 1);
    geo.rotateX(-Math.PI / 2);                       // row 0 of the grid = north = -z
    const pos = geo.attributes.position;
    // Imhof-style hillshade: light from the north-west, 45 degrees up, multiplied into the map at about 35%
    const shade = new Float32Array(cols * rows * 3);
    const dxm = Wm / (cols - 1), dym = Hm / (rows - 1);
    const L = [-Math.SQRT1_2 * Math.SQRT1_2, Math.SQRT1_2 * Math.SQRT1_2, Math.SQRT1_2];
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const i = r * cols + c;
        const zl = Zm[r * cols + Math.max(0, c - 1)], zr = Zm[r * cols + Math.min(cols - 1, c + 1)];
        const zn = Zm[Math.max(0, r - 1) * cols + c], zs = Zm[Math.min(rows - 1, r + 1) * cols + c];
        const gx = ((zr - zl) / (2 * dxm)) * 2.0, gy = ((zn - zs) / (2 * dym)) * 2.0;   // x east, y north
        const n = Math.hypot(gx, gy, 1);
        const lit = (-gx * L[0] - gy * L[1] + L[2]) / n;
        const v = 1 - 0.42 * (1 - Math.min(1.2, Math.max(0, lit / L[2])));
        shade[3 * i] = v; shade[3 * i + 1] = v; shade[3 * i + 2] = v * 0.98;
      }
    }
    geo.setAttribute("color", new THREE.BufferAttribute(shade, 3));

    const tex = await new Promise((resolve, reject) =>
      new THREE.TextureLoader().load(task.texture_data || task.texture, resolve, undefined,
        () => reject(new Error("texture failed to load"))));
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
    tex.generateMipmaps = true;
    tex.minFilter = THREE.LinearMipmapLinearFilter;
    // flat (morph 0): the texture is shown as is, through the emissive channel, so the top-down view equals the
    // 2D map; lifted (morph 1): lit by the low sun, the sky and the hillshade
    const mat = new THREE.MeshStandardMaterial({ map: tex, emissiveMap: tex, emissive: 0xffffff, emissiveIntensity: 1,
                                                 vertexColors: true, roughness: 0.93, metalness: 0 });
    mat.toneMapped = false;
    const terrain = new THREE.Mesh(geo, mat);
    scene.add(terrain);

    // skirt: earth-coloured walls around the block, so the lifted terrain reads as a relief model
    const edge = [];
    for (let c = 0; c < cols; c++) edge.push(c);
    for (let r = 1; r < rows; r++) edge.push(r * cols + cols - 1);
    for (let c = cols - 2; c >= 0; c--) edge.push((rows - 1) * cols + c);
    for (let r = rows - 2; r > 0; r--) edge.push(r * cols);
    edge.push(0);
    const skPos = new Float32Array(edge.length * 2 * 3), skIdx = [];
    for (let k = 0; k < edge.length; k++) {
      const vi = edge[k];
      for (const j of [0, 1]) {
        skPos[(2 * k + j) * 3] = pos.getX(vi);
        skPos[(2 * k + j) * 3 + 2] = pos.getZ(vi);
      }
      if (k < edge.length - 1) skIdx.push(2 * k, 2 * k + 1, 2 * k + 2, 2 * k + 1, 2 * k + 3, 2 * k + 2);
    }
    const skGeo = new THREE.BufferGeometry();
    skGeo.setAttribute("position", new THREE.BufferAttribute(skPos, 3));
    skGeo.setIndex(skIdx);
    const skirt = new THREE.Mesh(skGeo, new THREE.MeshStandardMaterial({ color: 0x3b2d22, roughness: 1, side: THREE.DoubleSide }));
    scene.add(skirt);

    function setMorph(m) {
      morph = m;
      for (let i = 0; i < H.length; i++) pos.setY(i, H[i] * m);
      pos.needsUpdate = true;
      geo.computeVertexNormals();
      const base = -4 * m - 0.02;
      for (let k = 0; k < edge.length; k++) {
        skPos[2 * k * 3 + 1] = H[edge[k]] * m;
        skPos[(2 * k + 1) * 3 + 1] = base;
      }
      skGeo.attributes.position.needsUpdate = true;
      skGeo.computeVertexNormals();
      skirt.visible = m > 0.01;
      // light follows the lift
      const lit = Math.min(1, m * 1.4);
      mat.emissiveIntensity = 1 - lit * 0.86;
      hemi.intensity = 0.95 * lit;
      sun.intensity = 2.2 * lit * sunLevel;
      skyMat.uniforms.opacity.value = lit;
      scene.fog.density = 0.0034 * lit;
    }
    let sunLevel = 1;
    setMorph(0);
    geo.computeBoundingSphere();

    // ---------------------------------------------------------------- coordinates
    const wx = (gx) => -Ww / 2 + (gx / (cols - 1)) * Ww;
    const wz = (gy) => -Hw / 2 + (gy / (rows - 1)) * Hw;
    function hAt(gx, gy) { return hRaw(gx, gy) * morph; }
    function hRaw(gx, gy) {
      const c = Math.min(cols - 1.001, Math.max(0, gx)), r = Math.min(rows - 1.001, Math.max(0, gy));
      const c0 = Math.floor(c), r0 = Math.floor(r), fc = c - c0, fr = r - r0;
      const i = r0 * cols + c0;
      return (H[i] * (1 - fc) * (1 - fr) + H[i + 1] * fc * (1 - fr) + H[i + cols] * (1 - fc) * fr + H[i + cols + 1] * fc * fr);
    }
    const at = (p, off) => new THREE.Vector3(wx(p[0]), hAt(p[0], p[1]) + (off || 0), wz(p[1]));

    // ---------------------------------------------------------------- labels (DOM, projected every frame)
    const labelLayer = host.querySelector(".labels");
    const labels = [];
    function label(text, p3, cls) {
      const e = document.createElement("div");
      e.className = "lbl " + (cls || "");
      e.textContent = text;
      labelLayer.appendChild(e);
      const L = { e, p: p3 };
      labels.push(L);
      return L;
    }
    function clearLabels() { labels.splice(0).forEach((l) => l.e.remove()); }
    const v3 = new THREE.Vector3();
    function placeLabels() {
      const w = host.clientWidth, h = host.clientHeight;
      for (const l of labels) {
        v3.copy(typeof l.p === "function" ? l.p() : l.p).project(camera);
        const vis = v3.z < 1 && Math.abs(v3.x) < 1.1 && Math.abs(v3.y) < 1.1 && !l.hidden;
        l.e.style.display = vis ? "" : "none";
        if (vis) {
          const hw = (l.e.offsetWidth || 0) / 2 + 4;
          l.e.style.left = Math.min(w - hw, Math.max(hw, ((v3.x + 1) / 2) * w)) + "px";
          l.e.style.top = ((1 - v3.y) / 2) * h + "px";
        }
      }
    }

    // ---------------------------------------------------------------- tweens and the loop
    const tweens = [];
    function tween(ms, fn, ease) {
      return new Promise((resolve) => tweens.push({ t0: performance.now(), ms, fn, ease: ease || EASE, resolve }));
    }
    const tickers = new Set();
    let running = true, last = performance.now();
    function frame(now) {
      if (!running) return;
      requestAnimationFrame(frame);
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      for (let i = tweens.length - 1; i >= 0; i--) {
        const tw = tweens[i], p = Math.min(1, (now - tw.t0) / tw.ms);
        tw.fn(tw.ease(p), p);
        if (p >= 1) { tweens.splice(i, 1); tw.resolve(); }
      }
      for (const f of tickers) f(dt, now / 1000);
      if (controls.enabled) controls.update();
      sky.position.copy(camera.position);
      renderer.render(scene, camera);
      placeLabels();
    }

    function resize() {
      const w = host.clientWidth, h = host.clientHeight;
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      if (pose === "top" && opts.frameRect) applyTop();
    }
    const ro = new ResizeObserver(resize);
    ro.observe(host);

    // ---------------------------------------------------------------- camera poses
    let pose = "free";
    function topPose() {
      const cw = host.clientWidth, ch = host.clientHeight, R = opts.frameRect();
      const k = (Hw * ch) / (2 * (R.y1 - R.y0)), a = cw / ch;
      const cx = -Ww / 2 - k * a * ((2 * R.x0) / cw - 1);
      const cz = k * (1 - (2 * R.y0) / ch) - Hw / 2;
      const d = k / Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
      return { p: new THREE.Vector3(cx, d, cz), q: new THREE.Quaternion().setFromEuler(new THREE.Euler(-Math.PI / 2, 0, 0)) };
    }
    function applyTop() { const t = topPose(); camera.position.copy(t.p); camera.quaternion.copy(t.q); }
    function lookPose(p, target) {
      const o = new THREE.PerspectiveCamera();
      o.position.copy(p);
      o.up.set(0, 1, 0);
      o.lookAt(target);
      return { p: p.clone(), q: o.quaternion.clone() };
    }
    function flyTo(to, ms, ease) {
      const p0 = camera.position.clone(), q0 = camera.quaternion.clone();
      return tween(ms, (e) => { camera.position.lerpVectors(p0, to.p, e); camera.quaternion.slerpQuaternions(q0, to.q, e); }, ease);
    }
    function actionBox() {                           // the part of the map the truth plays out on, in world units
      const pts = [];
      for (const p of (task.scene.points || [])) pts.push(p.g);
      for (const p of (task.scene.paths || [])) for (let i = 0; i < p.pts.length; i += 4) pts.push(p.pts[i]);
      if (!pts.length) return { c: new THREE.Vector3(0, 0, 0), w: Ww, d: Hw };
      let x0 = Infinity, x1 = -Infinity, z0 = Infinity, z1 = -Infinity, hs = 0;
      for (const p of pts) {
        const x = wx(p[0]), z = wz(p[1]);
        x0 = Math.min(x0, x); x1 = Math.max(x1, x); z0 = Math.min(z0, z); z1 = Math.max(z1, z);
        hs += hRaw(p[0], p[1]);
      }
      const w = Math.max(38, (x1 - x0) * 1.35), d = Math.max(30, (z1 - z0) * 1.35);
      return { c: new THREE.Vector3((x0 + x1) / 2, (hs / pts.length) * 0.8, (z0 + z1) / 2), w: Math.min(w, Ww * 1.05), d: Math.min(d, Hw * 1.1) };
    }
    function obliquePose(box) {
      const a = host.clientWidth / Math.max(1, host.clientHeight);
      const portrait = a < 0.9;
      const fit = Math.max(box.w / Math.min(a, 1.7), box.d * 1.25) * (portrait ? 0.5 : 0.62);
      const R = fit / Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
      const polar = THREE.MathUtils.degToRad(portrait ? 36 : 52), az = THREE.MathUtils.degToRad(-14);
      const t = box.c;
      const p = new THREE.Vector3(t.x + R * Math.sin(polar) * Math.sin(az), t.y + R * Math.cos(polar),
                                  t.z + R * Math.sin(polar) * Math.cos(az));
      return lookPose(p, t);
    }

    // ---------------------------------------------------------------- drawing helpers
    const dot = (() => {
      const c = document.createElement("canvas");
      c.width = c.height = 64;
      const x = c.getContext("2d"), gr = x.createRadialGradient(32, 32, 0, 32, 32, 32);
      gr.addColorStop(0, "rgba(255,255,255,1)"); gr.addColorStop(0.35, "rgba(255,255,255,0.85)"); gr.addColorStop(1, "rgba(255,255,255,0)");
      x.fillStyle = gr; x.fillRect(0, 0, 64, 64);
      const t = new THREE.CanvasTexture(c);
      t.colorSpace = THREE.SRGBColorSpace;
      return t;
    })();
    const overlay = new THREE.Group();
    scene.add(overlay);

    function curveOf(gpts, off, step) {
      const pts = [];
      const st = step || 1;
      for (let i = 0; i < gpts.length; i += st) pts.push(at(gpts[i], off));
      if ((gpts.length - 1) % st) pts.push(at(gpts[gpts.length - 1], off));
      return new THREE.CatmullRomCurve3(pts, false, "centripetal");
    }
    function drape(a, b, n) {                        // a straight line on the map, draped on the terrain
      const out = [];
      for (let i = 0; i <= n; i++) out.push([a[0] + ((b[0] - a[0]) * i) / n, a[1] + ((b[1] - a[1]) * i) / n]);
      return out;
    }
    function tube(curve, radius, color, opacity, glow) {
      const segs = Math.min(1200, Math.max(60, Math.round(curve.getLength() * 3)));
      const tg = new THREE.TubeGeometry(curve, segs, radius, 8, false);
      const m = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: opacity == null ? 1 : opacity,
                                              depthWrite: !glow, blending: glow ? THREE.AdditiveBlending : THREE.NormalBlending });
      m.toneMapped = false;
      const mesh = new THREE.Mesh(tg, m);
      const total = tg.index.count;
      mesh.reveal = (p) => tg.setDrawRange(0, Math.floor((total * Math.max(0, Math.min(1, p))) / 6) * 6);
      mesh.reveal(0);
      overlay.add(mesh);
      return mesh;
    }
    function glowLine(curve, color, glowColor, r) {
      const core = tube(curve, r || 0.2, color, 1, false);
      const halo = tube(curve, (r || 0.2) * 3.2, glowColor, 0.22, true);
      return { reveal: (p) => { core.reveal(p); halo.reveal(p); }, core, halo };
    }
    function flow(curve, color, count, size, opacity, speed) {
      const n = count, geom = new THREE.BufferGeometry(), arr = new Float32Array(n * 3);
      geom.setAttribute("position", new THREE.BufferAttribute(arr, 3));
      const m = new THREE.PointsMaterial({ color, size, map: dot, transparent: true, opacity, depthWrite: false,
                                           blending: THREE.AdditiveBlending, sizeAttenuation: true });
      m.toneMapped = false;
      const pts = new THREE.Points(geom, m);
      overlay.add(pts);
      const phase = Float32Array.from({ length: n }, () => Math.random());
      const jit = Float32Array.from({ length: n * 2 }, () => (Math.random() - 0.5) * 0.9);
      const len = curve.getLength();
      const f = { head: 0, pts };
      const tmp = new THREE.Vector3();
      const tick = (dt, t) => {
        for (let i = 0; i < n; i++) {
          let u = (phase[i] + (t * speed) / len) % 1;
          u = u * Math.max(0.0001, f.head);
          curve.getPointAt(u, tmp);
          arr[3 * i] = tmp.x + jit[2 * i] * 0.6;
          arr[3 * i + 1] = tmp.y + 0.15 + Math.abs(jit[2 * i + 1]) * 0.4;
          arr[3 * i + 2] = tmp.z + jit[2 * i + 1] * 0.6;
        }
        geom.attributes.position.needsUpdate = true;
      };
      tickers.add(tick);
      f.stop = () => tickers.delete(tick);
      return f;
    }
    function ring(p3, color, r0, r1, ms, loop) {
      const rg = new THREE.RingGeometry(0.75, 1, 48);
      rg.rotateX(-Math.PI / 2);
      const m = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.9, depthWrite: false, side: THREE.DoubleSide });
      m.toneMapped = false;
      const mesh = new THREE.Mesh(rg, m);
      mesh.position.copy(p3).add(new THREE.Vector3(0, 0.25, 0));
      overlay.add(mesh);
      const run = () => tween(ms, (e) => { const s = r0 + (r1 - r0) * e; mesh.scale.set(s, s, s); m.opacity = 0.95 * (1 - e); }, (x) => x)
        .then(() => (loop && running ? run() : mesh.removeFromParent()));
      run();
      return mesh;
    }
    function post(p3, color, hgt) {                  // a thin vertical marker (a person, a spotter)
      const m = new THREE.MeshBasicMaterial({ color });
      m.toneMapped = false;
      const c = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.18, hgt, 8), m);
      c.position.copy(p3).add(new THREE.Vector3(0, hgt / 2, 0));
      overlay.add(c);
      return c;
    }
    function arcFractions(curve, gpts) {             // where along a curve each grid point sits (0..1)
      const N = 600, samples = curve.getSpacedPoints(N);
      return gpts.map((gp) => {
        const q = at(gp, 0.3);
        let best = 0, bd = Infinity;
        for (let i = 0; i <= N; i++) {
          const d = (samples[i].x - q.x) ** 2 + (samples[i].z - q.z) ** 2;
          if (d < bd) { bd = d; best = i; }
        }
        return best / N;
      });
    }

    // ---------------------------------------------------------------- the truth, per template
    const S = task.scene || {};
    const byName = {};
    for (const p of S.points || []) byName[p.name] = p;
    const hud = host.querySelector(".hud");
    function hudSet(html) { if (hud) { hud.innerHTML = html; hud.classList.add("on"); } }

    function modelPicks(you) {                       // {answer value: [who, ...]} for the models' (and your) answers
      const out = {};
      for (const k of ["haiku", "luna"]) {
        const m = (task.models || {})[k];
        if (!m || m.parsed == null || m.parsed === "") continue;
        (out[String(m.parsed).toUpperCase()] = out[String(m.parsed).toUpperCase()] || []).push(k === "haiku" ? "Haiku" : "Luna");
      }
      return out;
    }

    const pointLabels = {};
    function addPointLabels() {
      for (const p of S.points || []) {
        pointLabels[p.name] = label(p.name, () => at(p.g, 0.6), "small");
      }
    }

    async function animFlood(you) {
      const water = (S.paths || []).find((p) => p.role === "water");
      const dam = (S.points || []).find((p) => p.role === "dam");
      if (!water || !dam) return animGeneric();
      const truthName = String(S.target || task.answer);
      const curve = curveOf(water.pts, 0.35, 1);
      const line = glowLine(curve, TRUTH, TRUTH_GLOW, 0.32);
      const fl = flow(curve, 0x9fd4ff, 700, 1.1, 0.95, 9);
      ring(at(dam.g), TRUTH_GLOW, 1, 5, 1600, true);
      hudSet(`<div class="sub">The water's path</div><div class="big truth">${truthName}</div>`);
      const len = curve.getLength(), ms = Math.min(7000, Math.max(3200, len * 45));
      // the models' wrong answers flow as red ghosts, straight down toward the camp they named
      const picks = modelPicks(you);
      const ghosts = [];
      for (const [camp, who] of Object.entries(picks)) {
        const c = byName[camp] || byName[camp.toUpperCase()];
        if (!c || camp === truthName.toUpperCase()) continue;
        const gc = curveOf(drape(dam.g, c.g, 80), 0.45, 1);
        const gl = tube(gc, 0.16, MODEL, 0.6, false);
        const gf = flow(gc, MODEL_GLOW, 260, 0.9, 0.6, 7);
        ghosts.push({ gl, gf, c, who });
      }
      await tween(ms, (e) => {
        line.reveal(e); fl.head = e;
        for (const g of ghosts) { g.gl.reveal(Math.min(1, e * 1.15)); g.gf.head = Math.min(1, e * 1.15); }
      }, INOUT);
      const tgt = byName[truthName];
      if (tgt) {
        ring(at(tgt.g), TRUTH_GLOW, 1, 7, 1400, true);
        if (pointLabels[truthName]) pointLabels[truthName].e.className = "lbl truth";
      }
      for (const g of ghosts) {
        ring(at(g.c.g), MODEL_GLOW, 1, 4, 1800, true);
        const L = pointLabels[g.c.name];
        if (L) { L.e.className = "lbl model"; L.e.textContent = `${g.c.name} · ${g.who.join(" + ")}`; }
      }
      const said = Object.entries(picks).map(([a, w]) => `<span class="said ${a === truthName.toUpperCase() ? "ok" : ""}">${w.join(" + ")}: ${a}</span>`).join("");
      hudSet(`<div class="sub">The water reaches</div><div class="big truth">${truthName}</div>${said}`);
    }

    async function animTrail(you) {
      const trail = (S.paths || []).find((p) => p.role === "trail");
      if (!trail) return animGeneric();
      const sunset = S.kind === "sunset" && S.sun && S.sun.now_min != null;
      const curve = curveOf(trail.pts, 0.35, 1);
      const line = glowLine(curve, TRUTH, TRUTH_GLOW, 0.2);
      const cr = S.crossings || [];
      const fr = arcFractions(curve, cr.map((c) => c.g));
      const counted = cr.map((c) => (sunset ? !!c.uphill : true));
      const total = counted.filter(Boolean).length;
      let shown = 0;
      const fired = new Array(cr.length).fill(false);
      const m = task.models || {};
      const said = ["haiku", "luna"].filter((k) => m[k]).map((k) =>
        `<span class="said ${m[k].correct ? "ok" : ""}">${k === "haiku" ? "Haiku" : "Luna"} said ${BTA.fmtAnswer(task, m[k].parsed)}</span>`).join("");
      let hiker = null;
      const clock = (mins) => { mins = Math.round(mins); const h = Math.floor(mins / 60) % 24, mm = ((mins % 60) + 60) % 60; return `${h}:${String(mm).padStart(2, "0")}`; };
      const sun0 = sun.color.clone(), dusk = new THREE.Color(0xff8a4c), night = new THREE.Color(0x4466aa);
      if (sunset) {
        hiker = new THREE.Mesh(new THREE.SphereGeometry(0.55, 16, 12), new THREE.MeshBasicMaterial({ color: 0xffffff }));
        hiker.material.toneMapped = false;
        overlay.add(hiker);
        label("Hiker", () => hiker.position.clone().add(new THREE.Vector3(0, 1.2, 0)), "small");
      }
      const per = sunset ? S.sun.minutes_per_uphill_contour || 4 : 0;
      const draw = (e) => {
        line.reveal(e);
        for (let i = 0; i < cr.length; i++) {
          if (!fired[i] && e >= fr[i]) {
            fired[i] = true;
            if (counted[i]) shown++;
            ring(at(cr[i].g, 0.2), counted[i] ? TRUTH_GLOW : 0x8a8a8a, 0.6, counted[i] ? 3.4 : 2, 900, false);
          }
        }
        let html;
        if (sunset) {
          const t = S.sun.now_min + S.sun.flat_walk_min * e + per * shown;
          const left = S.sun.sunset_min - t;
          const cp = curve.getPointAt(Math.min(1, e));
          hiker.position.copy(cp).add(new THREE.Vector3(0, 0.6, 0));
          // the sun sets as the hiker walks: golden -> orange -> night
          const f = Math.max(-0.4, Math.min(1, left / 60));
          if (f > 0) sun.color.copy(dusk).lerp(sun0, f); else sun.color.copy(dusk).lerp(night, Math.min(1, -f / 0.4));
          sunLevel = f > 0 ? 0.35 + 0.65 * f : 0.35 * (1 + f / 0.4) + 0.06;
          sun.intensity = 2.2 * sunLevel;
          hemi.intensity = 0.95 * (f > 0 ? 0.55 + 0.45 * f : 0.4);
          mat.emissiveIntensity = 0.14 * (f > 0 ? 0.4 + 0.6 * f : 0.25);
          sun.position.set(-90, 8 + 30 * Math.max(0, f), 12);
          skyMat.uniforms.horizon.value.set(f > 0 ? 0xc9a27a : 0x3a3550);
          html = `<div class="sub">Clock · sunset ${clock(S.sun.sunset_min)}</div><div class="big ${left >= 0 ? "truth" : ""}">${clock(t)}</div>` +
                 `<div class="sub">Uphill lines ${shown} · +${per * shown} min</div>`;
        } else {
          html = `<div class="sub">Contour lines crossed</div><div class="big truth">${shown}</div>`;
        }
        hudSet(html + said);
      };
      const ms = Math.min(9000, Math.max(4500, cr.length * 420));
      await tween(ms, draw, (x) => x);
      if (sunset) {
        const arr = S.sun.now_min + (S.sun.walking_min != null ? S.sun.walking_min : S.sun.flat_walk_min + per * total);
        const spare = S.sun.sunset_min - arr;
        hudSet(`<div class="sub">Arrives ${clock(arr)} · sunset ${clock(S.sun.sunset_min)}</div>` +
               `<div class="big truth">${spare > 0 ? "+" : ""}${spare} min</div>` +
               `<div class="sub">${spare >= 0 ? "before sunset" : "after dark"}</div>${said}`);
      } else {
        hudSet(`<div class="sub">Contour lines crossed</div><div class="big truth">${total}</div>${said}`);
      }
    }

    async function animLos() {
      const L = S.los;
      const a = byName[L.from], b = byName[L.to];
      if (!a || !b) return animGeneric();
      const pa = at(a.g, units(L.eye_m || 2) + 0.05), pb = at(b.g, units(L.target_m || 2) + 0.05);
      post(at(a.g), 0xf3eedf, Math.max(0.6, units(L.eye_m || 2)) + 0.6);
      post(at(b.g), 0xf3eedf, Math.max(0.6, units(L.target_m || 2)) + 0.6);
      // find where the sight line first goes under the ground (the same rule the question states)
      const N = 500;
      let block = null;
      for (let i = 1; i < N; i++) {
        const t = i / N, gx = a.g[0] + (b.g[0] - a.g[0]) * t, gy = a.g[1] + (b.g[1] - a.g[1]) * t;
        const ly = pa.y + (pb.y - pa.y) * t;
        if (hAt(gx, gy) > ly) { block = t; break; }
      }
      const visible = L.visible;
      const tEnd = visible || block == null ? 1 : block;
      const mk = (t0, t1) => new THREE.LineCurve3(pa.clone().lerp(pb, t0), pa.clone().lerp(pb, t1));
      const seen = glowLine(mk(0, tEnd), TRUTH, TRUTH_GLOW, 0.16);
      let hidden = null;
      if (tEnd < 1) hidden = tube(mk(tEnd, 1), 0.08, 0x9a9a9a, 0.6, false);
      const st = task.steps || {};
      await tween(2600, (e) => { const f = e / tEnd; seen.reveal(Math.min(1, f)); if (hidden) hidden.reveal(Math.max(0, (e - tEnd) / (1 - tEnd))); }, INOUT);
      if (!visible && tEnd < 1) {
        const bp = pa.clone().lerp(pb, tEnd);
        ring(bp, TRUTH_GLOW, 1, 6, 1500, true);
        label("Ridge blocks the view", bp.clone().add(new THREE.Vector3(0, 1.4, 0)), "truth");
      }
      const said = ["haiku", "luna"].filter((k) => task.models[k]).map((k) =>
        `<span class="said ${task.models[k].correct ? "ok" : ""}">${k === "haiku" ? "Haiku" : "Luna"}: ${String(task.models[k].parsed).toLowerCase()}</span>`).join("");
      const clr = st.min_clearance_m != null ? `<div class="sub">Closest clearance ${st.min_clearance_m} m</div>` : "";
      hudSet(`<div class="sub">Can R see H?</div><div class="big truth">${visible ? "YES" : "NO"}</div>${clr}${said}`);
    }

    async function animFire() {
      if (S.fire_elev_m != null) {
        const lim = units(S.fire_elev_m - 40 - g.zmin);
        const pl = new THREE.Mesh(new THREE.PlaneGeometry(Ww, Hw), new THREE.MeshBasicMaterial({ color: 0xf3eedf, transparent: true, opacity: 0, depthWrite: false, side: THREE.DoubleSide }));
        pl.rotateX(-Math.PI / 2);
        pl.position.y = lim;
        overlay.add(pl);
        tween(1200, (e) => { pl.material.opacity = 0.22 * e; });
      }
      const ans = String(task.answer).toUpperCase();
      const safe = new Set(ans === "BOTH" ? ["A", "B"] : ans === "NEITHER" ? [] : [ans]);
      const lines = [];
      for (const p of S.paths || []) {
        if (!p.role.startsWith("option_")) continue;
        const pts = [];
        for (let i = 0; i < p.pts.length - 1; i++) pts.push(...drape(p.pts[i], p.pts[i + 1], 20).slice(0, -1));
        pts.push(p.pts[p.pts.length - 1]);
        const c = curveOf(pts, 0.35, 1);
        lines.push(safe.has(p.name) ? glowLine(c, TRUTH, TRUTH_GLOW, 0.2) : tube(c, 0.12, 0xb8b0a0, 0.85, false));
        label(`Trail ${p.name}${safe.has(p.name) ? " · safe" : ""}`, c.getPointAt(0.5).add(new THREE.Vector3(0, 1.2, 0)), safe.has(p.name) ? "truth" : "small");
      }
      await tween(3200, (e) => lines.forEach((l) => l.reveal(e)), INOUT);
      const said = ["haiku", "luna"].filter((k) => task.models[k]).map((k) =>
        `<span class="said ${task.models[k].correct ? "ok" : ""}">${k === "haiku" ? "Haiku" : "Luna"}: ${task.models[k].parsed}</span>`).join("");
      hudSet(`<div class="sub">Safe trail</div><div class="big truth">${String(task.answer).toUpperCase()}</div>${said}`);
    }

    async function animGeneric() {
      const lines = (S.paths || []).filter((p) => p.pts.length > 1).map((p) => glowLine(curveOf(p.pts, 0.35, 1), TRUTH, TRUTH_GLOW, 0.18));
      await tween(3000, (e) => lines.forEach((l) => l.reveal(e)), INOUT);
      hudSet(`<div class="sub">Answer</div><div class="big truth">${task.answer}</div>`);
    }

    // ---------------------------------------------------------------- public API
    const api = {
      THREE, renderer, scene, camera, controls,
      get morph() { return morph; },
      resize,
      showTop() { pose = "top"; controls.enabled = false; applyTop(); setMorph(0); },
      async lift(ms) {
        pose = "free";
        const box = actionBox(), target = box.c;
        const to = obliquePose(box);
        const p0 = camera.position.clone(), q0 = camera.quaternion.clone();
        await tween(ms || 1800, (e) => {
          setMorph(e);
          camera.position.lerpVectors(p0, to.p, e);
          camera.quaternion.slerpQuaternions(q0, to.q, e);
        }, INOUT);
        controls.target.copy(target);
      },
      async reveal(you) {
        await this.lift(1800);
        addPointLabels();
        const k = S.kind;
        try {
          if (k === "flood") await animFlood(you);
          else if (k === "crossings" || k === "sunset") await animTrail(you);
          else if (k === "los" && S.los) await animLos(you);
          else if (k === "fire") await animFire(you);
          else await animGeneric(you);
        } catch (e) { console.warn("reveal animation:", e); }
        controls.enabled = true;
        controls.autoRotate = !matchMedia("(prefers-reduced-motion: reduce)").matches;
      },
      // the projector intro: fly low over the terrain, then come down exactly onto the 2D map and flatten it
      async intro(hooks) {
        hooks = hooks || {};
        pose = "free";
        setMorph(1);
        let top = 0, tc = 0, tr = 0;
        for (let r = 2; r < rows - 2; r++) for (let c = 2; c < cols - 2; c++) if (H[r * cols + c] > top) { top = H[r * cols + c]; tc = c; tr = r; }
        const summit = new THREE.Vector3(wx(tc), top, wz(tr));
        const center = new THREE.Vector3(0, top * 0.35, 0);
        const side = summit.x > 0 ? -1 : 1;
        const path = new THREE.CatmullRomCurve3([
          new THREE.Vector3(side * Ww * 0.75, top * 0.55 + 10, Hw * 0.85),
          new THREE.Vector3(side * Ww * 0.30, top * 0.8 + 12, Hw * 0.55),
          new THREE.Vector3(summit.x - side * 24, top + 16, summit.z + 34),
          new THREE.Vector3(summit.x + side * 30, top + 34, summit.z + 60),
          new THREE.Vector3(side * -12, top + 85, Hw * 1.05),
        ], false, "catmullrom", 0.5);
        const look = new THREE.CatmullRomCurve3([
          new THREE.Vector3(side * Ww * 0.1, top * 0.3, -Hw * 0.1), summit.clone().add(new THREE.Vector3(0, 0, -6)),
          summit.clone(), center.clone().add(new THREE.Vector3(0, 0, 4)), center.clone(),
        ], false, "catmullrom", 0.5);
        const o = new THREE.PerspectiveCamera();
        const ms = hooks.ms || 8000;
        if (hooks.onStart) hooks.onStart();
        await tween(ms, (e, raw) => {
          const u = Math.min(1, Math.max(0, e));
          path.getPoint(u, o.position);
          o.lookAt(look.getPoint(Math.min(1, u * 1.05)));
          camera.position.copy(o.position);
          camera.quaternion.copy(o.quaternion);
          if (hooks.onProgress) hooks.onProgress(raw);
        }, (x) => INOUT(x) * 0.85 + x * 0.15);
        if (hooks.onDescend) hooks.onDescend();
        const t = topPose();
        const p0 = camera.position.clone(), q0 = camera.quaternion.clone();
        await tween(3200, (e) => {
          camera.position.lerpVectors(p0, t.p, e);
          camera.quaternion.slerpQuaternions(q0, t.q, e);
          setMorph(1 - Math.max(0, (e - 0.35) / 0.65));
        }, INOUT);
        pose = "top";
        applyTop();
        setMorph(0);
      },
      dispose() { running = false; ro.disconnect(); renderer.dispose(); renderer.domElement.remove(); clearLabels(); },
    };
    resize();
    requestAnimationFrame(frame);
    return api;
  }

  window.BTAStage = { create, sleep, EASE };
})();
