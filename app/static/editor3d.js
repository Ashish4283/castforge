// The scene editor: the open scene in 3D ("Build 3D preview" writes scenes/NN_id/preview.glb and preview.json).
// Play and scrub the timeline, orbit around, click a character or a step; drag where people start and where
// they walk to. Every edit goes into the scene (scene.json) through app.js (window.cf), so the next preview and
// the next render use it. Stage spots are [x, y] metres; glTF is Y-up (Blender x, y, z -> three x, z, -y).
import * as THREE from "three";
import {GLTFLoader} from "/static/vendor/three/examples/jsm/loaders/GLTFLoader.js";
import {OrbitControls} from "/static/vendor/three/examples/jsm/controls/OrbitControls.js";

const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const COLORS = ["#e0574d", "#4f9dde", "#5cc985", "#e5a54a", "#b07fe0", "#4fc6c0"];
const round = x => Math.round(x * 20) / 20;

let renderer, scene3, camera, controls, mixer = null, model = null, meta = null, loadedUrl = null;
let previews = [], frame = 1, playing = false, last = 0, dirty = false, dragging = null, selected = null;
const markers = new THREE.Group(), undo = [];
const ray = new THREE.Raycaster(), floor = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);

const toThree = p => new THREE.Vector3(p[0] + meta.origin[0], 0.01, -(p[1] + meta.origin[1]));
const toStage = v => [round(v.x - meta.origin[0]), round(-v.z - meta.origin[1])];
const colorOf = who => COLORS[Math.max(0, Object.keys(meta?.cast || {}).indexOf(who)) % COLORS.length];

// --- what the scene says now (the live scene, not the preview: edits show at once) ----------------------
function part() { return window.cf?.part(); }
function startOf(who) {
  const own = part()?.cast?.[who], top = window.cf?.model()?.cast?.[who];
  return own?.position || top?.position || meta?.cast?.[who]?.start || [0, 0];
}
function script() { return Array.isArray(part()?.script) ? part().script : []; }

// --- the viewport --------------------------------------------------------------------------------------------
function init() {
  const host = $("#viewport");
  renderer = new THREE.WebGLRenderer({antialias: true});
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  host.prepend(renderer.domElement);
  scene3 = new THREE.Scene();
  scene3.background = new THREE.Color(0x1b1a18);
  camera = new THREE.PerspectiveCamera(40, 16 / 9, 0.05, 300);
  camera.position.set(0, 1.8, 7);
  controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, 1, 0);
  scene3.add(new THREE.HemisphereLight(0xffffff, 0x4a443a, 2.4));
  const sun = new THREE.DirectionalLight(0xffffff, 1.8);
  sun.position.set(3, 6, 5);
  const grid = new THREE.GridHelper(30, 30, 0x5a5650, 0x34322e);
  grid.material.transparent = true;
  grid.material.opacity = 0.35;
  scene3.add(sun, grid, markers);
  new ResizeObserver(resize).observe(host);
  resize();
  host.addEventListener("pointerdown", down, true);     // before OrbitControls: a marker drag must not orbit
  addEventListener("pointermove", move);
  addEventListener("pointerup", up);
  renderer.setAnimationLoop(tick);
}
function resize() {
  const host = $("#viewport"), w = host.clientWidth, h = Math.round(w * 9 / 16);
  renderer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
function tick(now) {
  if (playing && meta) {
    frame += (now - last) / 1000 * meta.fps;
    if (frame >= meta.frames) { frame = meta.frames; playing = false; $("#play3d").textContent = "Play"; }
    seek(frame, false);
  }
  last = now;
  controls.update();
  renderer.render(scene3, camera);
}
function seek(f, stop = true) {
  if (!meta) return;
  if (stop && playing) { playing = false; $("#play3d").textContent = "Play"; }
  frame = Math.max(1, Math.min(meta.frames, f));
  mixer?.setTime((frame - 1) / meta.fps);
  $("#scrub3d").value = Math.round(frame);
  const t = (frame - 1) / meta.fps;
  const line = (meta.lines || []).find(l => l.start <= t && t <= l.end);
  $("#time3d").textContent = `${t.toFixed(1)} s · frame ${Math.round(frame)}` + (line ? ` · ${line.who}: “${line.text}”` : "");
  const head = $("#playhead");
  if (head) head.style.left = `${(frame - 1) / Math.max(1, meta.frames - 1) * 100}%`;
}

// --- loading a preview ---------------------------------------------------------------------------------------
async function load(p) {
  $("#empty3d").classList.toggle("hidden", !!p);
  if (!p) {                                   // this scene has no preview (yet)
    if (model) scene3.remove(model);
    model = meta = mixer = loadedUrl = null;
    markers.clear();
    return;
  }
  if (p.glb === loadedUrl) return;
  note("Loading the 3D scene…");
  try {
    const m = await (await fetch(p.meta)).json();
    const gltf = await new GLTFLoader().loadAsync(p.glb);
    if (model) scene3.remove(model);
    model = gltf.scene;
    const hasSet = !!model.getObjectByName("Set");
    model.traverse(o => {
      if (o.isSkinnedMesh) {
        o.frustumCulled = false;                       // moving bodies leave their bounds
        for (const m of [o.material].flat()) {         // MakeHuman materials come as blended: draw solid or cut out
          m.transparent = false; m.alphaTest = 0.5; m.depthWrite = true;
        }
      }
      if (hasSet && o.name === "Backdrop") o.visible = false;   // the far backdrop only matters to the film camera
    });
    scene3.add(model);
    meta = m;
    mixer = new THREE.AnimationMixer(model);
    gltf.animations.forEach(clip => mixer.clipAction(clip).play());
    loadedUrl = p.glb;
    $("#scrub3d").max = meta.frames;
    frameCamera();
    redraw();
    seek(1);
    note(stale() ? "The scene changed since this preview: Build 3D preview to see the new version." : "");
  } catch (e) { note("Could not load the 3D preview: " + e.message); }
}
function stale() {
  return script().length !== meta.steps.length || meta.steps.some((s, i) => script()[i]?.do !== s.do);
}
function frameCamera(top = false) {
  if (!meta) return;
  const spots = Object.keys(meta.cast).map(w => toThree(startOf(w)));
  const c = spots.reduce((a, v) => a.add(v), new THREE.Vector3()).multiplyScalar(1 / Math.max(1, spots.length));
  controls.target.set(c.x, top ? 0 : 1, c.z);
  camera.position.set(c.x, top ? 11 : 2.2, c.z + (top ? 0.01 : 6.5));
}

// --- markers: where each person starts (disc) and walks to (rings), joined in order ----------------------
function disc(color, inner, outer) {
  const g = inner ? new THREE.RingGeometry(inner, outer, 40) : new THREE.CircleGeometry(outer, 40);
  const m = new THREE.Mesh(g, new THREE.MeshBasicMaterial({color, transparent: true, opacity: 0.85, depthTest: false}));
  m.rotation.x = -Math.PI / 2;
  m.renderOrder = 2;
  return m;
}
function label(text, color) {
  const c = document.createElement("canvas"), g = c.getContext("2d");
  c.width = 256; c.height = 64;
  g.font = "600 34px system-ui, sans-serif"; g.fillStyle = color; g.textAlign = "center"; g.fillText(text, 128, 44);
  const s = new THREE.Sprite(new THREE.SpriteMaterial({map: new THREE.CanvasTexture(c), depthTest: false}));
  s.scale.set(1.0, 0.25, 1);
  s.renderOrder = 3;
  return s;
}
function redraw() {
  markers.clear();
  if (!meta) return;
  for (const who of Object.keys(meta.cast)) {
    const color = colorOf(who), path = [toThree(startOf(who))];
    const start = disc(color, 0, who === selected ? 0.26 : 0.2);
    start.position.copy(path[0]);
    start.userData = {kind: "start", who};
    const tag = label(who, color);
    tag.position.copy(path[0]).add(new THREE.Vector3(0, 2.15, 0));
    markers.add(start, tag);
    script().forEach((st, n) => {
      if (st.who !== who || !Array.isArray(st.to)) return;
      const ring = disc(color, 0.13, 0.2);
      ring.position.copy(toThree(st.to));
      ring.userData = {kind: "to", who, n};
      markers.add(ring);
      path.push(ring.position.clone());
    });
    if (path.length > 1) {
      const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(path),
        new THREE.LineDashedMaterial({color, dashSize: 0.15, gapSize: 0.1, depthTest: false}));
      line.computeLineDistances();
      line.renderOrder = 1;
      markers.add(line);
    }
  }
}

// --- dragging markers and picking characters ----------------------------------------------------------------
function pointer(e) {
  const r = renderer.domElement.getBoundingClientRect();
  ray.setFromCamera(new THREE.Vector2((e.clientX - r.left) / r.width * 2 - 1, -(e.clientY - r.top) / r.height * 2 + 1), camera);
}
function down(e) {
  if (!meta || e.button !== 0) return;
  pointer(e);
  const hit = ray.intersectObjects(markers.children.filter(m => m.userData.kind), false)[0];
  if (hit) {
    const {kind, who} = hit.object.userData, seat = (part()?.cast?.[who] || window.cf.model()?.cast?.[who])?.sit;
    if (kind === "start" && seat) {           // the seat decides where a seated person starts
      select(who);
      return note(`${who} starts seated on “${seat}”: move that seat in Set props, or remove the seat to place ${who} freely.`);
    }
    e.stopPropagation();
    controls.enabled = false;
    dragging = {marker: hit.object, from: hit.object.position.clone()};
    select(hit.object.userData.who, hit.object.userData.n);
    return;
  }
  const body = model && ray.intersectObject(model, true)[0];
  if (body) {
    let o = body.object;
    while (o && !Object.entries(meta.cast).some(([, c]) => c.rig === o.name)) o = o.parent;
    const who = o && Object.entries(meta.cast).find(([, c]) => c.rig === o.name)[0];
    if (who) select(who);
  }
}
function move(e) {
  if (!dragging) return;
  pointer(e);
  const p = new THREE.Vector3();
  if (ray.ray.intersectPlane(floor, p)) {
    dragging.marker.position.set(p.x, 0.01, p.z);
    const s = toStage(p);
    note(`${dragging.marker.userData.who}: ${dragging.marker.userData.kind === "start" ? "starts at" : "walks to"} [${s.join(", ")}]`);
  }
}
function up() {
  if (!dragging) return;
  const {marker, from} = dragging;
  dragging = null;
  controls.enabled = true;
  if (marker.position.distanceTo(from) < 0.02) return;
  const {kind, who, n} = marker.userData, spot = toStage(marker.position);
  const target = kind === "start" ? window.cf.castEntry(who) : script()[n];
  const key = kind === "start" ? "position" : "to";
  undo.push({target, key, value: target[key]});
  target[key] = spot;
  changed(`${who} ${kind === "start" ? "now starts at" : "now walks to"} [${spot.join(", ")}]. Save, then Build 3D preview to see the new movement.`);
}
function changed(text) {
  dirty = true;
  $("#save3d").disabled = false;
  $("#undo3d").disabled = !undo.length;
  window.cf.changed();
  redraw();
  note(text);
}
function select(who, n) {
  selected = who;
  redraw();
  document.querySelectorAll("#lanes .blk").forEach(b =>
    b.classList.toggle("on", (b.dataset.who || null) === who && (n === undefined || Number(b.dataset.n) === n)));
}

// --- the timeline: one lane per person (and one for the scene), a block per step ---------------------------
function timeline() {
  const lanes = $("#lanes");
  if (!meta) { lanes.innerHTML = ""; return; }
  const who = [...Object.keys(meta.cast), null];
  const span = Math.max(1, meta.frames - 1);
  lanes.innerHTML = who.map(w => `<div class="lane"><span class="who" style="color:${w ? colorOf(w) : "inherit"}">${esc(w || "scene")}</span><div class="track">` +
    meta.steps.filter(s => (s.who || null) === w).map(s => {
      const st = script()[s.n] || {}, what = st.clip || st.text || st.target || st.shot || st.sfx || "";
      return `<button class="blk" data-n="${s.n}" data-who="${esc(s.who || "")}" style="left:${(s.f0 - 1) / span * 100}%;width:${Math.max(0.6, (s.f1 - s.f0) / span * 100)}%;border-color:${w ? colorOf(w) : "var(--line)"}" title="${esc(`${s.do} ${what}`.trim())} · ${((s.f0 - 1) / meta.fps).toFixed(1)}–${((s.f1 - 1) / meta.fps).toFixed(1)} s">${esc(s.do)}</button>`;
    }).join("") + `</div></div>`).join("") + `<div class="heads"><i id="playhead"></i></div>`;
  seek(frame, false);
}
function stepClicked(b) {
  const s = meta.steps[Number(b.dataset.n)];
  seek(s.f0);
  select(s.who || null, s.n);
  const st = script()[s.n] || {};
  const detail = Object.entries(st).filter(([k]) => !["who", "do"].includes(k)).map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join(", ");
  note(`Step ${s.n + 1}: ${s.who ? s.who + " " : ""}${s.do}${detail ? " (" + detail + ")" : ""}. Change its details in “Actions and camera direction” below.`);
}

// for automated checks: is a preview loaded, the frame, and where a person's start disc is on screen
window.cf3d = {
  loaded: () => !!meta, frame: () => frame,
  screenOf: who => {
    const v = toThree(startOf(who)).project(camera), r = renderer.domElement.getBoundingClientRect();
    return [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height];
  },
};

// --- wiring ------------------------------------------------------------------------------------------------
function note(text) { $("#note3d").textContent = text; }
function current() { return previews[window.cf?.partIndex() ?? 0] || previews[0]; }
addEventListener("cf:episode", e => {       // app.js refreshes the open episode every few seconds
  previews = e.detail.previews || [];
  if ((current()?.glb || null) !== loadedUrl) load(current()).then(timeline);
});
(() => {                                    // modules run once the page is parsed
  init();
  $("#scenePart")?.addEventListener("change", () => load(current()).then(() => { redraw(); timeline(); }));
  $("#play3d").onclick = () => {
    if (!meta) return;
    if (frame >= meta.frames) seek(1);
    playing = !playing;
    $("#play3d").textContent = playing ? "Pause" : "Play";
  };
  $("#scrub3d").oninput = e => seek(Number(e.target.value));
  $("#front3d").onclick = () => frameCamera(false);
  $("#top3d").onclick = () => frameCamera(true);
  $("#lanes").onclick = e => {
    const b = e.target.closest(".blk");
    if (b) return stepClicked(b);
    const t = e.target.closest(".track");
    if (t) { const r = t.getBoundingClientRect(); seek(1 + (e.clientX - r.left) / r.width * (meta.frames - 1)); }
  };
  $("#undo3d").onclick = () => {
    const u = undo.pop();
    if (!u) return;
    if (u.value === undefined) delete u.target[u.key]; else u.target[u.key] = u.value;
    changed("Undone.");
  };
  $("#save3d").onclick = async () => {
    try { await window.cf.save(); dirty = false; $("#save3d").disabled = true; note("Saved. Build 3D preview to see the new movement."); }
    catch (e) { note(e.message); }
  };
  $("#build3d").onclick = async () => {
    try {
      await window.cf.save();
      dirty = false;
      $("#save3d").disabled = true;
      await window.cf.post("/api/episode/preview3d", {movie: window.cf.movie(), episode: window.cf.episode()});
      note("Building the 3D preview (about 20 seconds per scene)…");
    } catch (e) { note(e.message); }
  };
  addEventListener("keydown", e => {
    if ((e.ctrlKey || e.metaKey) && e.key === "z" && !e.target.closest("input, textarea, select") && undo.length) {
      e.preventDefault();
      $("#undo3d").click();
    }
  });
  addEventListener("beforeunload", e => { if (dirty) e.preventDefault(); });
})();
