// SentiLab Package view: the 3D renderer. An adapter that maps a RenderModel's original primitives (model.mjs: boxes,
// outlines, halos and the field) to scene objects of one pinned, locally served three.js build. It decides nothing:
// positions, sizes, colours and words all come from the model, its display boxes, the field texels and the caller.
//
// three.js r187 (web/public/vendor/three/0.187.0, MIT, files pinned by sha256 in VERSION.txt) is imported lazily, only
// when the 3D view is shown, so the 2D fallback never loads it. No add-ons (they need an import map, which the page's
// Content-Security-Policy can't host): the orbit camera below is our own. Labels are DOM text over the canvas, placed
// with the CSSOM, never drawn into the canvas. Frames are drawn only while something moves.
//
// World coordinates are the model's: mm, +z up toward the cooler (the camera's up vector is +z).
export const THREE_VERSION = "0.187.0";
const THREE_URL = new URL(`../../../vendor/three/${THREE_VERSION}/three.module.js`, import.meta.url).href;

export const GLIDE_MS = 900;
export const FADE_MS = 700;
export const FIT_MS = 650;
export const ORBIT_DEG_PER_S = 4;          // one turn in 90 s
const ELEV_MIN = 6, ELEV_MAX = 88;
export const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const clamp01 = (t) => Math.max(0, Math.min(1, t));
const lerp = (a, b, t) => a + (b - a) * t;

// Colours: the stack is muted so the map and the dies carry the picture. CPU and DRAM hues sit outside the heat ramp.
export const COLORS = Object.freeze({
  cpu: 0xc4a7f5, dram: 0x8fb8de, edge: 0xd6e2e5, halo: 0xf3e6c4, band: 0xf0937a, lattice: 0x9fb4bb,
  lid: 0xc9d6d9, ghost: 0x9fb4bb, accept: 0xe7c48f, overlap: 0xf0937a, stale: 0xe7c48f,
});
const LAYER_STYLE = Object.freeze({
  substrate: { color: 0x2c5a4c, opacity: 0.96, edge: 0.3 },
  c4: { color: 0x8c6f3e, opacity: 0.92, edge: 0.26 },
  interposer: { color: 0x5d6e7b, opacity: 0.96, edge: 0.34 },
  ubump: { color: 0xa8874d, opacity: 0.92, edge: 0.2 },
  chip: { color: 0x26323a, opacity: 0.98, edge: 0.22 },
  tim: { color: 0xc9d4da, opacity: 0.14, edge: 0.22 },
  spreader: { color: 0xd39a66, opacity: 0.09, edge: 0.32 },
  sink: { color: 0xb9c4ca, opacity: 0.05, edge: 0.24 },
  lab_substrate: { color: 0x1d3b35, opacity: 1, edge: 0.25 },
  lab_interposer: { color: 0x2b3944, opacity: 1, edge: 0.35 },
});

// WebGL2 is what this three.js build renders with. Probed on a throwaway canvas, whose context is released.
export function webgl2Available(doc = globalThis.document) {
  try {
    const c = doc.createElement("canvas");
    const gl = c.getContext("webgl2");
    if (!gl) return false;
    gl.getExtension("WEBGL_lose_context")?.loseContext();
    return true;
  } catch {
    return false;
  }
}

// canvas: the <canvas> to draw into. labels: a positioned element over it for DOM labels. leaders: an <svg> over it
// for leader lines. reduced: prefers-reduced-motion (no auto orbit, no glides, cuts instead of fades).
export async function createView3D({ canvas, labels, leaders, reduced = false, onContextLost = () => {} }) {
  const THREE = await import(THREE_URL);
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
  renderer.setClearColor(0x000000, 0);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(26, 1, 2, 4000);
  camera.up.set(0, 0, 1);
  scene.add(new THREE.HemisphereLight(0xe4eef2, 0x1a2429, 1.55));
  const sun = new THREE.DirectionalLight(0xffffff, 1.45);
  sun.position.set(-60, -90, 140);
  const rim = new THREE.DirectionalLight(0x9fc6d4, 0.5);
  rim.position.set(90, 70, 40);
  scene.add(sun, rim);

  const root = new THREE.Group();
  scene.add(root);
  const owned = new Set();                       // everything we create, for dispose()
  const own = (x) => { owned.add(x); return x; };
  const unitBox = own(new THREE.BoxGeometry(1, 1, 1));
  const unitEdges = own(new THREE.EdgesGeometry(unitBox));
  const unitPlane = own(new THREE.PlaneGeometry(1, 1));
  const rectLine = own(new THREE.BufferGeometry().setAttribute("position", new THREE.Float32BufferAttribute([
    -0.5, -0.5, 0, 0.5, -0.5, 0, 0.5, -0.5, 0, 0.5, 0.5, 0, 0.5, 0.5, 0, -0.5, 0.5, 0, -0.5, 0.5, 0, -0.5, -0.5, 0], 3)));
  // A die: the unit box with two draw groups, its four sides and bottom (lit, the die's colour) and its top (the field).
  const dieGeo = own(unitBox.clone());
  {
    const idx = Array.from(unitBox.index.array), face = (k) => idx.slice(k * 6, k * 6 + 6);
    dieGeo.setIndex([0, 1, 2, 3, 5, 4].flatMap(face));
    dieGeo.clearGroups();
    dieGeo.addGroup(0, 30, 0);
    dieGeo.addGroup(30, 6, 1);
  }

  // ── soft shadow under the package (decorative) ──
  const shadowTex = (() => {
    const c = document.createElement("canvas");
    c.width = c.height = 128;
    const g = c.getContext("2d");
    const grad = g.createRadialGradient(64, 64, 8, 64, 64, 64);
    grad.addColorStop(0, "rgba(0,0,0,0.6)");
    grad.addColorStop(0.55, "rgba(0,0,0,0.3)");
    grad.addColorStop(1, "rgba(0,0,0,0)");
    g.fillStyle = grad;
    g.fillRect(0, 0, 128, 128);
    return own(new THREE.CanvasTexture(c));
  })();
  const shadow = new THREE.Mesh(unitPlane, own(new THREE.MeshBasicMaterial({ map: shadowTex, transparent: true, depthWrite: false })));
  shadow.renderOrder = -1;
  root.add(shadow);

  // ── the field: two NEAREST textures cross-faded in one shader, sampled by WORLD x and y so the chip-layer sheet and
  //    every die top show the same grid cell at the same place. Unlit: the colours are the scale's, exactly. ──
  const makeTex = () => {
    const t = own(new THREE.DataTexture(new Uint8Array(64 * 64 * 4), 64, 64, THREE.RGBAFormat));
    t.magFilter = THREE.NearestFilter; t.minFilter = THREE.NearestFilter; t.generateMipmaps = false;
    t.needsUpdate = true;
    return t;
  };
  const texA = makeTex(), texB = makeTex();
  const U = { mapA: { value: texA }, mapB: { value: texB }, t: { value: 0 }, hasA: { value: 0 }, hasB: { value: 0 },
    origin: { value: new THREE.Vector2(0, 0) }, size: { value: 45 } };
  const FIELD_VS = "varying vec2 vXY;\nvoid main() { vec4 w = modelMatrix * vec4(position, 1.0); vXY = w.xy; gl_Position = projectionMatrix * viewMatrix * w; }";
  const FIELD_FS = "uniform sampler2D mapA; uniform sampler2D mapB; uniform float t; uniform float hasA; uniform float hasB;\n" +
    "uniform vec2 origin; uniform float size; uniform vec3 base; uniform float useBase;\nvarying vec2 vXY;\n" +
    "void main() {\n  vec2 uv = (vXY - origin) / size;\n  float wa = (1.0 - t) * hasA; float wb = t * hasB; float a = clamp(wa + wb, 0.0, 1.0);\n" +
    "  vec3 f = (texture2D(mapA, uv).rgb * wa + texture2D(mapB, uv).rgb * wb) / max(a, 0.0001);\n" +
    "  if (useBase < 0.5) { if (a < 0.003) discard; gl_FragColor = vec4(f, a); }\n  else gl_FragColor = vec4(mix(base, f, a), 1.0);\n}";
  const fieldMaterial = (base = null) => own(new THREE.ShaderMaterial({
    transparent: base === null, depthWrite: base !== null,
    uniforms: { ...U, base: { value: new THREE.Color(base ?? 0x000000) }, useBase: { value: base === null ? 0 : 1 } },
    vertexShader: FIELD_VS, fragmentShader: FIELD_FS,
  }));
  const sheet = new THREE.Mesh(unitPlane, fieldMaterial());
  sheet.renderOrder = 2;
  root.add(sheet);
  // "front" is the texture now showing (A or B); a new field goes to the other one and fades in.
  const F = { front: "A", has: { A: 0, B: 0 }, fadeStart: null, from: 0, to: 0, key: null };

  // ── pools ──
  const boxes = new Map();      // id -> { mesh, edges, mat, emat }
  const loops = new Map();      // id -> LineSegments (die-top outlines, halos, ghosts, outlines)
  function boxFor(id, style) {
    let b = boxes.get(id);
    if (!b) {
      const mat = own(new THREE.MeshStandardMaterial({ color: style.color, roughness: 0.62, metalness: 0.08, transparent: style.opacity < 1, opacity: style.opacity, depthWrite: style.opacity > 0.5 }));
      const emat = own(new THREE.LineBasicMaterial({ color: COLORS.edge, transparent: true, opacity: style.edge, depthWrite: false }));
      const mesh = new THREE.Mesh(unitBox, mat), edges = new THREE.LineSegments(unitEdges, emat);
      root.add(mesh, edges);
      b = { mesh, edges, mat, emat };
      boxes.set(id, b);
    }
    return b;
  }
  const dies3 = new Map();      // die id -> { mesh, side, top }
  function dieFor(id, kind) {
    let d = dies3.get(id);
    if (!d) {
      const color = kind === "CPU" ? COLORS.cpu : COLORS.dram;
      const side = own(new THREE.MeshStandardMaterial({ color, roughness: 0.45, metalness: 0.05 }));
      const top = fieldMaterial(new THREE.Color(color).multiplyScalar(0.92));
      const mesh = new THREE.Mesh(dieGeo, [side, top]);
      root.add(mesh);
      d = { mesh, side, top };
      dies3.set(id, d);
    }
    return d;
  }
  function placeBox(b, d, rotZ = 0) {
    const w = Math.max(1e-4, d.x1 - d.x0), h = Math.max(1e-4, d.y1 - d.y0), t = Math.max(1e-4, d.z1 - d.z0);
    for (const o of b.edges ? [b.mesh, b.edges] : [b.mesh]) {
      o.position.set((d.x0 + d.x1) / 2, (d.y0 + d.y1) / 2, (d.z0 + d.z1) / 2);
      o.scale.set(w, h, t);
      o.rotation.set(0, 0, rotZ);
    }
  }
  function loopFor(id, color, opacity, dashed = false) {
    let l = loops.get(id);
    if (!l) {
      const mat = own(dashed
        ? new THREE.LineDashedMaterial({ color, transparent: true, opacity, dashSize: 0.6, gapSize: 0.45, depthWrite: false })
        : new THREE.LineBasicMaterial({ color, transparent: true, opacity, depthWrite: false }));
      l = new THREE.LineSegments(dashed ? own(rectLine.clone()) : rectLine, mat);
      l.renderOrder = 3;
      root.add(l);
      loops.set(id, l);
    }
    return l;
  }
  function placeLoop(l, x0, y0, x1, y1, z, rotZ = 0) {
    l.position.set((x0 + x1) / 2, (y0 + y1) / 2, z);
    l.scale.set(Math.max(1e-4, x1 - x0), Math.max(1e-4, y1 - y0), 1);
    l.rotation.set(0, 0, rotZ);
    if (l.material.isLineDashedMaterial && (l.userData.sx !== l.scale.x || l.userData.sy !== l.scale.y)) {
      // Dashes in mm along the scaled rectangle: distances in world units, rewritten in place when the size changes.
      l.userData.sx = l.scale.x; l.userData.sy = l.scale.y;
      const pos = l.geometry.attributes.position;
      let attr = l.geometry.getAttribute("lineDistance");
      if (!attr) { attr = new THREE.Float32BufferAttribute(new Float32Array(pos.count), 1); l.geometry.setAttribute("lineDistance", attr); }
      for (let i = 0; i < pos.count; i += 2) {
        attr.array[i] = 0;
        attr.array[i + 1] = Math.hypot((pos.getX(i + 1) - pos.getX(i)) * l.scale.x, (pos.getY(i + 1) - pos.getY(i)) * l.scale.y);
      }
      attr.needsUpdate = true;
    }
  }
  function dropUnused(pool, keep) {
    for (const [id, o] of pool) {
      if (keep.has(id)) continue;
      if (o.edges) root.remove(o.mesh, o.edges);
      else if (o.mesh) root.remove(o.mesh);
      else root.remove(o);
      pool.delete(id);
    }
  }

  // ── overlays: the 0.5 mm edge band, the 0.5 mm centre lattice, die centres (one toggle). Built once at z = 0; the
  //    group follows the chip layer's display top. ──
  const overlay = new THREE.Group();
  overlay.visible = false;
  root.add(overlay);
  let overlayKey = null;
  const marks = new THREE.LineSegments(own(new THREE.BufferGeometry().setAttribute("position", new THREE.Float32BufferAttribute(new Float32Array(8 * 4 * 3), 3))),
    own(new THREE.LineBasicMaterial({ color: COLORS.halo, transparent: true, opacity: 0.95, depthWrite: false })));
  marks.renderOrder = 5;
  marks.frustumCulled = false;
  overlay.add(marks);
  function buildOverlay(model) {
    const key = `${model.case_id}:${model.frame.interposer_mm}:${model.overlays.edge_band_mm}:${model.overlays.lattice_mm}`;
    if (overlayKey === key) return;
    overlayKey = key;
    for (const o of [...overlay.children]) if (o !== marks) { overlay.remove(o); o.geometry?.dispose?.(); }
    const S0 = model.frame.interposer_mm, e = model.overlays.edge_band_mm, step = model.overlays.lattice_mm;
    const shape = new THREE.Shape([new THREE.Vector2(0, 0), new THREE.Vector2(S0, 0), new THREE.Vector2(S0, S0), new THREE.Vector2(0, S0)]);
    shape.holes.push(new THREE.Path([new THREE.Vector2(e, e), new THREE.Vector2(e, S0 - e), new THREE.Vector2(S0 - e, S0 - e), new THREE.Vector2(S0 - e, e)]));
    const band = new THREE.Mesh(new THREE.ShapeGeometry(shape), own(new THREE.MeshBasicMaterial({ color: COLORS.band, transparent: true, opacity: 0.5, depthWrite: false })));
    band.position.z = 0.03;
    band.renderOrder = 4;
    const minor = [], major = [];
    for (let k = 0; k <= Math.round(S0 / step); k += 1) {
      const v = k * step, list = k % 10 === 0 ? major : minor;
      list.push(v, 0, 0, v, S0, 0, 0, v, 0, S0, v, 0);
    }
    const lines = (pts, opacity) => {
      const l = new THREE.LineSegments(new THREE.BufferGeometry().setAttribute("position", new THREE.Float32BufferAttribute(pts, 3)),
        own(new THREE.LineBasicMaterial({ color: COLORS.lattice, transparent: true, opacity, depthWrite: false })));
      l.position.z = 0.05;
      l.renderOrder = 4;
      return l;
    };
    overlay.add(band, lines(minor, 0.12), lines(major, 0.34));
  }

  // ── DOM labels and leader lines ──
  const labelEls = new Map();   // key -> { el, text }
  function label(key, cls, parts) {
    let L = labelEls.get(key);
    if (!L) {
      const el = document.createElement("div");
      el.className = `l3 ${cls}`;
      labels.append(el);
      L = { el, text: null, cls };
      labelEls.set(key, L);
    }
    if (L.cls !== cls) { L.el.className = `l3 ${cls}`; L.cls = cls; }
    const sig = JSON.stringify(parts);
    if (L.text !== sig) {
      L.text = sig;
      L.el.replaceChildren(...parts.map(([tag, c, text]) => { const s = document.createElement(tag); if (c) s.className = c; s.textContent = text; return s; }));
      L.width = null;
    }
    return L;
  }
  function dropLabels(keep) { for (const [k, L] of labelEls) if (!keep.has(k)) { L.el.remove(); labelEls.delete(k); } }
  const leaderEls = new Map();
  function leaderFor(key) {
    let ln = leaderEls.get(key);
    if (!ln) {
      ln = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
      leaders.append(ln);
      leaderEls.set(key, ln);
    }
    return ln;
  }

  // ── camera: our own orbit around a target ──
  const HOME = Object.freeze({ az: -135, el: 34 });
  const cam = { az: HOME.az, el: HOME.el, dist: 160, target: new THREE.Vector3(22.5, 22.5, 0), fov: 26 };
  const camTween = { start: null, from: null, to: null };
  const view = { w: 1, h: 1, padL: 0, padT: 70, padB: 90 };
  let autoOrbit = false, lastT = null;
  function applyCamera() {
    const az = (cam.az * Math.PI) / 180, el = (cam.el * Math.PI) / 180;
    camera.position.set(
      cam.target.x + cam.dist * Math.cos(el) * Math.cos(az),
      cam.target.y + cam.dist * Math.cos(el) * Math.sin(az),
      cam.target.z + cam.dist * Math.sin(el));
    camera.lookAt(cam.target);
    camera.updateMatrixWorld();
  }

  // ── state ──
  const S = {
    model: null, display: null, kind: null, notScored: null, chipTop: 0, fillTop: 0, bounds: null, layerWords: new Map(),
    dies: new Map(),          // die id -> { kind, power, base: { w, h } (catalogue box), halo, from, to, start }
    lab: null,                // lab frame extras: { texts }
    raf: 0, disposed: false, frames: 0, last: { calls: 0, triangles: 0 }, fitted: false,
  };

  // A door model (kind "model"): stack, dies (gliding and turning from where they were), halos, overlays and the field.
  function setDoor(model, display, { field = null, animate = true, notScored = "not scored yet" } = {}) {
    const tween = animate && !reduced;
    const now = performance.now();
    const was = S.kind;
    S.kind = "model"; S.model = model; S.display = display; S.lab = null; S.notScored = field ? null : notScored;
    const chip = display.get("level:chip");
    S.chipTop = chip.z1; S.fillTop = chip.fill_z1 ?? chip.z1;
    const keep = new Set(), keepLoops = new Set();
    for (const b of model.boxes) {
      if (b.type !== "layer") continue;
      placeBox(boxFor(b.id, LAYER_STYLE[b.level]), display.get(b.id));
      keep.add(b.id);
    }
    // Dies: each keeps its catalogue box and turns about z; at rest a quarter turn is exactly the swapped footprint.
    const seen = new Set();
    for (const b of model.boxes) {
      if (b.type !== "die") continue;
      const id = b.die, to = { cx: b.cx, cy: b.cy, rot: b.rot_deg };
      const turned = b.rot_deg === 90 || b.rot_deg === 270;
      const base = { w: turned ? b.y1 - b.y0 : b.x1 - b.x0, h: turned ? b.x1 - b.x0 : b.y1 - b.y0 };
      const cur = S.dies.get(id);
      const from = tween && cur && was === "model" ? currentDie(cur, now) : to;
      const halo = model.halos.find((x) => x.die === id)?.halo_mm ?? 0;
      S.dies.set(id, { box: b.id, kind: b.kind, power: b.power_w, base, halo, from, to, start: now });
      dieFor(id, b.kind);
      seen.add(id);
      keepLoops.add(`top:${id}`); keepLoops.add(`halo:${id}`);
    }
    for (const [id, d] of dies3) if (!seen.has(id)) { root.remove(d.mesh); dies3.delete(id); S.dies.delete(id); }
    dropUnused(boxes, keep);
    dropUnused(loops, keepLoops);
    buildOverlay(model);
    U.origin.value.set(0, 0);
    U.size.value = model.frame.interposer_mm;
    setField(field, { animate: tween });
    S.bounds = boundsOf(display, model);
    if (!S.fitted) { fit({ animate: false }); S.fitted = true; }
    kick();
  }
  function currentDie(d, now) {
    const t = clamp01((now - d.start) / GLIDE_MS), e = easeInOut(t);
    return { cx: lerp(d.from.cx, d.to.cx, e), cy: lerp(d.from.cy, d.to.cy, e), rot: lerp(d.from.rot, d.to.rot, e) };
  }
  function boundsOf(display, model) {
    let x0 = Infinity, y0 = Infinity, z0 = Infinity, x1 = -Infinity, y1 = -Infinity, z1 = -Infinity;
    for (const b of model.boxes) {
      const d = display.get(b.id);
      if (!d) continue;
      x0 = Math.min(x0, d.x0); y0 = Math.min(y0, d.y0); z0 = Math.min(z0, d.z0);
      x1 = Math.max(x1, d.x1); y1 = Math.max(y1, d.y1); z1 = Math.max(z1, d.z1);
    }
    return { x0, y0, z0, x1, y1, z1 };
  }

  // Field: { texels (row 0 = y 0), key } or null for "not scored". A new field fades in over the old one (or over
  // nothing); null fades it out. Reduced motion cuts.
  function setField(f, { animate = true } = {}) {
    const key = f ? f.key ?? "field" : null;
    if (key === F.key) return;
    F.key = key;
    const back = F.front === "A" ? "B" : "A";
    if (f) { const tex = back === "A" ? texA : texB; tex.image.data.set(f.texels); tex.needsUpdate = true; }
    F.has[back] = f ? 1 : 0;
    U.hasA.value = F.has.A; U.hasB.value = F.has.B;
    F.from = F.front === "A" ? 0 : 1;
    F.to = back === "A" ? 0 : 1;
    F.front = back;
    if (animate) F.fadeStart = performance.now();
    else { F.fadeStart = null; U.t.value = F.to; }
    kick();
  }

  // A lab-run frame (kind "result"): the schematic stack and the chiplets in their verified colours, with the same words
  // on each as the 2D view, ghosts (where gliding chiplets came from), the accepted ring and the lid outline. The caller
  // animates (render.mjs TrackAnimation) and calls this once per frame.
  function setLab(model, { labels: texts = [], ghosts = [], accepted = false, pulse = null, lid = true, azimuthDeg = null } = {}) {
    S.kind = "result"; S.model = model; S.lab = { texts };
    S.display = new Map([...model.boxes, ...model.outlines].map((b) => [b.id, b]));
    S.notScored = null;
    const keep = new Set(), keepLoops = new Set();
    for (const b of model.boxes) {
      if (b.type === "layer") { placeBox(boxFor(b.id, LAYER_STYLE[b.level === "substrate" ? "lab_substrate" : "lab_interposer"]), b); keep.add(b.id); }
      else if (b.type === "chiplet") {
        const bx = boxFor(b.id, { color: 0x3b4c55, opacity: 1, edge: 0.6 });
        bx.mat.color.set(b.fill);
        bx.mat.opacity = b.alpha * (b.overlap ? 0.72 : 1);
        bx.mat.transparent = bx.mat.opacity < 1;
        bx.mat.depthWrite = bx.mat.opacity > 0.5;
        bx.emat.color.set(b.overlap ? COLORS.overlap : b.state === "stale" ? COLORS.stale : COLORS.edge);
        bx.emat.opacity = b.overlap || b.state === "stale" ? 0.95 : 0.5;
        placeBox(bx, b);
        keep.add(b.id);
      }
    }
    if (lid) {
      for (const o of model.outlines) {
        for (const z of ["lo", "hi"]) { const l = loopFor(`${o.id}:${z}`, COLORS.lid, 0.45, true); placeLoop(l, o.x0, o.y0, o.x1, o.y1, z === "lo" ? o.z0 : o.z1); keepLoops.add(`${o.id}:${z}`); }
      }
    }
    const inter = model.boxes.find((b) => b.id === "layer:interposer");
    ghosts.forEach((g, k) => { const l = loopFor(`ghost:${k}`, COLORS.ghost, 0.85, true); l.material.opacity = g.alpha; placeLoop(l, g.x, g.y, g.x + g.w, g.y + g.h, inter.z1 + 0.02); keepLoops.add(`ghost:${k}`); });
    if (accepted || pulse !== null) {
      const grow = pulse === null ? 0 : easeInOut(pulse) * 2.4;
      const l = loopFor("accept", COLORS.accept, 0.6);
      l.material.opacity = pulse === null ? 0.55 : 0.95 * (1 - pulse) + 0.1;
      placeLoop(l, inter.x0 - grow, inter.y0 - grow, inter.x1 + grow, inter.y1 + grow, inter.z1 + 0.01);
      keepLoops.add("accept");
    }
    dropUnused(boxes, keep);
    dropUnused(loops, keepLoops);
    for (const d of dies3.values()) root.remove(d.mesh);
    dies3.clear(); S.dies.clear();
    overlay.visible = false;
    setField(null, { animate: false });
    S.bounds = { ...model.bounds };
    // The lab view's azimuth (its rotate and orbit steps) wins whenever it moves; a drag holds until then.
    if (azimuthDeg !== null && azimuthDeg !== S.labAz) { cam.az = azimuthDeg + LAB_AZ_OFFSET; S.labAz = azimuthDeg; }
    if (!S.fitted || S.lastLabKey !== model.bounds.x0 + model.bounds.x1) { fit({ animate: false }); S.fitted = true; S.lastLabKey = model.bounds.x0 + model.bounds.x1; }
    kick();
  }
  // The 2D view's azimuth (render.mjs HOME_AZIMUTH -45: camera at the package's south-west) in this camera's terms.
  const LAB_AZ_OFFSET = -90;

  // ── fit: the distance at which the bounds' eight corners stay inside the free part of the canvas (right of the label
  //    column, clear of the title and caption) at every azimuth of an orbit, so orbiting never clips the package ──
  const tmp = new THREE.Vector3();
  function fitTarget() {
    const b = S.bounds;
    if (!b || !Number.isFinite(b.x0)) return null;
    const target = new THREE.Vector3((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2, (b.z0 + b.z1) / 2);
    const corners = [];
    for (const x of [b.x0, b.x1]) for (const y of [b.y0, b.y1]) for (const z of [b.z0, b.z1]) corners.push(new THREE.Vector3(x, y, z));
    const xMin = -1 + (2 * view.padL) / view.w + 0.04, xMax = 0.96;
    const yMax = 1 - (2 * view.padT) / view.h, yMin = -1 + (2 * view.padB) / view.h;
    const save = { az: cam.az, dist: cam.dist, target: cam.target.clone() };
    cam.target.copy(target);
    let worst = 0;
    for (let k = 0; k < 8; k += 1) {
      cam.az = save.az + k * 45;
      let lo = 1, hi = 6000;
      for (let it = 0; it < 26; it += 1) {
        cam.dist = (lo + hi) / 2;
        applyCamera();
        const ok = corners.every((c) => { tmp.copy(c).project(camera); return tmp.z < 1 && tmp.x >= xMin && tmp.x <= xMax && tmp.y >= yMin && tmp.y <= yMax; });
        if (ok) hi = cam.dist; else lo = cam.dist;
      }
      worst = Math.max(worst, hi);
    }
    cam.az = save.az; cam.dist = save.dist; cam.target.copy(save.target);
    applyCamera();
    return { target, dist: worst };
  }
  function fit({ animate = true } = {}) {
    const f = fitTarget();
    if (!f) return;
    if (!animate || reduced) { cam.target.copy(f.target); cam.dist = f.dist; camTween.start = null; }
    else { camTween.start = performance.now(); camTween.from = { target: cam.target.clone(), dist: cam.dist }; camTween.to = f; }
    kick();
  }

  // ── the frame ──
  function project(x, y, z) {
    tmp.set(x, y, z).project(camera);
    return { x: (tmp.x * 0.5 + 0.5) * view.w, y: (-tmp.y * 0.5 + 0.5) * view.h, behind: tmp.z > 1 };
  }
  function frame(now) {
    S.raf = 0;
    if (S.disposed) return;
    let busy = false;
    const dt = lastT === null ? 0 : Math.min(100, now - lastT);
    lastT = now;
    if (autoOrbit && !reduced && drag.pts.size === 0) { cam.az += (ORBIT_DEG_PER_S * dt) / 1000; busy = true; }
    if (camTween.start !== null) {
      const t = clamp01((now - camTween.start) / FIT_MS), e = easeInOut(t);
      cam.target.lerpVectors(camTween.from.target, camTween.to.target, e);
      cam.dist = lerp(camTween.from.dist, camTween.to.dist, e);
      if (t >= 1) camTween.start = null; else busy = true;
    }
    applyCamera();
    if (S.kind === "model") {
      const pos = marks.geometry.attributes.position;
      let k = 0;
      for (const [id, d] of S.dies) {
        if (clamp01((now - d.start) / GLIDE_MS) < 1) busy = true;
        const at = currentDie(d, now);
        const hw = d.base.w / 2, hh = d.base.h / 2, rot = (at.rot * Math.PI) / 180;
        placeBox(dies3.get(id), { x0: at.cx - hw, x1: at.cx + hw, y0: at.cy - hh, y1: at.cy + hh, z0: S.display.get(d.box).z0, z1: S.chipTop }, rot);
        placeLoop(loopFor(`top:${id}`, d.kind === "CPU" ? COLORS.cpu : COLORS.dram, 1), at.cx - hw, at.cy - hh, at.cx + hw, at.cy + hh, S.chipTop + 0.04, rot);
        const hl = loopFor(`halo:${id}`, COLORS.halo, 0.85, true);
        hl.visible = overlay.visible;
        placeLoop(hl, at.cx - hw - d.halo, at.cy - hh - d.halo, at.cx + hw + d.halo, at.cy + hh + d.halo, S.chipTop + 0.06, rot);
        const c = 0.7;
        for (const [ax, ay, bx, by] of [[-c, 0, c, 0], [0, -c, 0, c]]) {
          pos.setXYZ(k, at.cx + ax, at.cy + ay, S.chipTop - S.fillTop + 0.09); pos.setXYZ(k + 1, at.cx + bx, at.cy + by, S.chipTop - S.fillTop + 0.09);
          k += 2;
        }
      }
      pos.needsUpdate = true;
      if (F.fadeStart !== null) {
        const t = clamp01((now - F.fadeStart) / FADE_MS);
        U.t.value = lerp(F.from, F.to, easeInOut(t));
        if (t >= 1) F.fadeStart = null; else busy = true;
      }
      const S0 = S.model.frame.interposer_mm;
      sheet.visible = F.has.A + F.has.B > 0;
      sheet.position.set(S0 / 2, S0 / 2, S.fillTop + 0.02);
      sheet.scale.set(S0, S0, 1);
      overlay.position.z = S.fillTop;
    } else {
      sheet.visible = false;
    }
    if (S.bounds) {
      const b = S.bounds, pad = 0.24 * Math.max(b.x1 - b.x0, b.y1 - b.y0);
      shadow.position.set((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2, b.z0 - 0.05);
      shadow.scale.set(b.x1 - b.x0 + pad * 2, b.y1 - b.y0 + pad * 2, 1);
    }
    renderer.render(scene, camera);
    S.frames += 1;
    S.last = { calls: renderer.info.render.calls, triangles: renderer.info.render.triangles };
    placeLabels(now);
    if (busy || drag.pts.size > 0) kick();
  }
  const kick = () => { if (!S.raf && !S.disposed) S.raf = requestAnimationFrame(frame); };

  // ── labels: dies, layer callouts, the "not scored" note ──
  function put(el, p) {
    el.hidden = p.behind;
    el.style.transform = `translate(${Math.round(p.x)}px, ${Math.round(p.y)}px) translate(-50%, -50%)`;
  }
  function putRight(el, x, y) { el.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px) translate(-100%, -50%)`; }
  function placeLabels(now) {
    const keep = new Set(), keepLead = new Set();
    if (S.kind === "model") {
      for (const [id, d] of view.w < 560 ? [] : S.dies) {
        const at = currentDie(d, now);
        put(label(`die:${id}`, d.kind === "CPU" ? "die cpu" : "die dram", [["b", null, id], ["span", null, `${d.kind} ${d.power} W`]]).el, project(at.cx, at.cy, S.chipTop + 0.1));
        keep.add(`die:${id}`);
      }
      // Layer callouts: anchored at each layer's left-most corner at mid-height, stacked in a column at the left. Only
      // where the canvas keeps a label column (wide screens); smaller screens have the stack table in the panel.
      if (view.padL > 0) {
        const rows = [];
        for (const b of S.model.boxes) {
          if (b.type !== "layer" || !S.layerWords.has(b.level)) continue;
          const d = S.display.get(b.id), zm = (d.z0 + d.z1) / 2;
          const a = [[d.x0, d.y0], [d.x1, d.y0], [d.x1, d.y1], [d.x0, d.y1]].map(([x, y]) => project(x, y, zm)).reduce((m, q) => (q.x < m.x ? q : m));
          rows.push({ level: b.level, a });
        }
        rows.sort((p, q) => q.a.y - p.a.y);
        const gap = view.h < 600 ? 18 : 23;
        for (let k = 0; k < rows.length; k += 1) rows[k].y = k === 0 ? rows[k].a.y + 8 : Math.min(rows[k].a.y, rows[k - 1].y - gap);
        const els = rows.map((r) => label(`layer:${r.level}`, "layer", S.layerWords.get(r.level)));
        for (const L of els) if (L.width === null) L.width = L.el.offsetWidth;   // measured once per text
        const widest = Math.max(...els.map((L) => L.width));
        const colX = Math.max(widest + 10, Math.min(view.padL - 12, Math.min(...rows.map((r) => r.a.x)) - 40));
        for (const [k, r] of rows.entries()) {
          putRight(els[k].el, colX, r.y);
          leaderFor(`layer:${r.level}`).setAttribute("points", `${colX + 6},${r.y} ${Math.max(colX + 8, r.a.x - 16)},${r.y} ${r.a.x},${r.a.y}`);
          keep.add(`layer:${r.level}`); keepLead.add(`layer:${r.level}`);
        }
      }
      if (S.notScored && view.w >= 560) {
        // On the chip layer's corner nearest the viewer, just below it: it labels the layer and covers no die. Phones
        // show no 3D labels (the caption under the view says the same).
        const S0 = S.model.frame.interposer_mm;
        const p = [[0, 0], [S0, 0], [S0, S0], [0, S0]].map(([x, y]) => project(x, y, S.fillTop)).reduce((m, q) => (q.y > m.y ? q : m));
        const el = label("notScored", "note", [["span", null, S.notScored]]).el;
        el.hidden = p.behind;
        el.style.transform = `translate(${Math.round(p.x)}px, ${Math.round(p.y + 14)}px) translate(-50%, 0)`;
        keep.add("notScored");
      }
    } else if (S.kind === "result" && S.lab) {
      for (const t of S.lab.texts) {
        const L = label(`lab:${t.id}`, `die lab${t.alpha < 0.5 ? " dim" : ""}`, t.parts);
        put(L.el, project(t.x, t.y, t.z));
        keep.add(`lab:${t.id}`);
      }
    }
    dropLabels(keep);
    for (const [k, ln] of leaderEls) if (!keepLead.has(k)) { ln.remove(); leaderEls.delete(k); }
  }

  // ── input: drag to orbit, wheel or pinch to zoom, keys when the canvas has focus ──
  const drag = { pts: new Map(), pinch: null };
  const onUser = [];
  const userMoved = () => { for (const f of onUser) f(); };
  function orbitBy(daz, del) { cam.az += daz; cam.el = Math.max(ELEV_MIN, Math.min(ELEV_MAX, cam.el + del)); kick(); }
  function zoomBy(f) {
    const fitD = fitTarget()?.dist ?? cam.dist;
    cam.dist = Math.max(fitD * 0.3, Math.min(fitD * 3, cam.dist * f));
    kick();
  }
  canvas.addEventListener("pointerdown", (e) => {
    canvas.setPointerCapture(e.pointerId);
    drag.pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    camTween.start = null;
    userMoved();
    kick();
  });
  canvas.addEventListener("pointermove", (e) => {
    if (!drag.pts.has(e.pointerId)) return;
    const prev = drag.pts.get(e.pointerId);
    drag.pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (drag.pts.size === 1) orbitBy(-(e.clientX - prev.x) * 0.3, (e.clientY - prev.y) * 0.22);
    else if (drag.pts.size === 2) {
      const [a, b] = [...drag.pts.values()];
      const d = Math.hypot(a.x - b.x, a.y - b.y);
      if (drag.pinch) zoomBy(drag.pinch / Math.max(1, d));
      drag.pinch = d;
    }
  });
  const end = (e) => { drag.pts.delete(e.pointerId); if (drag.pts.size < 2) drag.pinch = null; kick(); };
  canvas.addEventListener("pointerup", end);
  canvas.addEventListener("pointercancel", end);
  canvas.addEventListener("wheel", (e) => { e.preventDefault(); userMoved(); zoomBy(Math.exp(e.deltaY * 0.0012)); }, { passive: false });
  canvas.addEventListener("keydown", (e) => {
    const k = e.key;
    if (k === "ArrowLeft" || k === "ArrowRight") { e.preventDefault(); userMoved(); orbitBy(k === "ArrowLeft" ? -10 : 10, 0); }
    else if (k === "ArrowUp" || k === "ArrowDown") { e.preventDefault(); userMoved(); orbitBy(0, k === "ArrowUp" ? 5 : -5); }
    else if (k === "+" || k === "=") { userMoved(); zoomBy(0.85); }
    else if (k === "-" || k === "_") { userMoved(); zoomBy(1 / 0.85); }
  });
  canvas.addEventListener("webglcontextlost", (e) => { e.preventDefault(); onContextLost(); });

  function resize() {
    const r = canvas.getBoundingClientRect();
    view.w = Math.max(1, Math.round(r.width)); view.h = Math.max(1, Math.round(r.height));
    // Pixel density: at most 2, and at most about 2.2 MP of drawing buffer (1 MP on a phone-sized canvas).
    const cap = view.w * view.h < 500000 ? 1e6 : 2.2e6;
    renderer.setPixelRatio(Math.min(2, globalThis.devicePixelRatio || 1, Math.sqrt(cap / (view.w * view.h))));
    renderer.setSize(view.w, view.h, false);
    view.padL = view.w >= 1100 ? 250 : view.w >= 860 ? 215 : 0;
    // The title sits top-left and the caption bottom-left, beside the package: only a thin margin is kept clear.
    view.padT = view.w >= 760 ? 34 : 12;
    view.padB = view.w >= 760 ? 30 : 12;
    // Shift the projection centre right by half the label column, so the package centres in the free area.
    if (view.padL > 0) camera.setViewOffset(view.w + view.padL, view.h, 0, 0, view.w, view.h); else camera.clearViewOffset();
    camera.aspect = (view.w + view.padL) / view.h;
    camera.updateProjectionMatrix();
    leaders.setAttribute("viewBox", `0 0 ${view.w} ${view.h}`);
    if (S.bounds) fit({ animate: false });
    kick();
  }

  const api = {
    setDoor, setLab, setField, fit, resize,
    setLayerWords(map) { S.layerWords = new Map(map); kick(); },
    setOverlay(on) { overlay.visible = Boolean(on); kick(); },
    setAutoOrbit(on) { autoOrbit = Boolean(on) && !reduced; lastT = null; kick(); },
    onUserMove(f) { onUser.push(f); },
    orbitBy, zoomBy,
    home() { cam.az = HOME.az; cam.el = HOME.el; fit({ animate: true }); },
    stats() {
      return { drawCalls: S.last.calls, triangles: S.last.triangles, frames: S.frames, geometries: renderer.info.memory.geometries,
        textures: renderer.info.memory.textures, programs: renderer.info.programs?.length ?? null,
        buffer: { w: renderer.domElement.width, h: renderer.domElement.height }, idle: !S.raf, three: THREE.REVISION };
    },
    requestRender: kick,
    dispose() {
      S.disposed = true;
      if (S.raf) cancelAnimationFrame(S.raf);
      for (const L of labelEls.values()) L.el.remove();
      for (const ln of leaderEls.values()) ln.remove();
      labelEls.clear(); leaderEls.clear();
      let geometries = 0, materials = 0, textures = 0;
      root.traverse((o) => { if (o.geometry && !owned.has(o.geometry)) { o.geometry.dispose(); geometries += 1; } });
      for (const x of owned) { x.dispose?.(); if (x.isBufferGeometry) geometries += 1; else if (x.isMaterial) materials += 1; else if (x.isTexture) textures += 1; }
      renderer.dispose();
      return { geometries, materials, textures };
    },
  };
  resize();
  applyCamera();
  return api;
}
