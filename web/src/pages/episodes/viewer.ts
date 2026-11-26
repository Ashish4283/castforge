// The 3D scene viewer (three.js): the scene's preview.glb with its animation, plus markers for where each person
// starts (disc), walks to (rings) and props (squares; faint while they still stand where the set put them).
// Stage spots are [x, y] metres; glTF is Y-up (Blender x, y, z -> three x, z, -y).
import * as THREE from "three";
import {GLTFLoader} from "three/examples/jsm/loaders/GLTFLoader.js";
import {OrbitControls} from "three/examples/jsm/controls/OrbitControls.js";
import {Json, Preview} from "../../api";
import {COLORS} from "./SceneSetup";

/** One shot as the render will actually see it: the camera's own place, aim and lens, written down by
 *  scene_kit while it builds them. Nothing here is re-derived in the browser, so what the app shows
 *  through the lens is what comes out of the render rather than a second opinion about it. */
export interface Cam {
  n: number; f0: number; f1: number; kind: string; on: string[]; move: string; lens: number;
  fov: number;                              // vertical, degrees - three.js wants that one
  track: number[][];                        // [frame, x, y, z, dx, dy, dz], Blender axes, origin removed
}
export interface Meta {
  fps: number; frames: number; origin: [number, number];
  cast: Record<string, {start: [number, number]; rig: string}>;
  steps: {n: number; who?: string; do: string; f0: number; f1: number}[];
  props?: {id: string; position: [number, number]; rotation?: number; on?: string; make?: string; from_set?: boolean}[];
  lines?: {who: string; text: string; start: number; end: number}[];
  cameras?: Cam[];
  res?: [number, number];
}
export interface Hooks {
  start: (who: string) => [number, number];          // where the live scene says someone starts
  script: () => Json[];
  seat: (who: string) => string | undefined;
  frame: (frame: number, meta: Meta) => void;
  note: (text: string) => void;
  select: (who: string | null, n?: number) => void;
  drop: (kind: "start" | "to", who: string, n: number | undefined, spot: [number, number]) => void;
  props: () => {id: string; position: [number, number]; on?: string; make?: string; from_set?: boolean}[];
  dropProp: (id: string, spot: [number, number], fromSet: boolean) => void;
  playing: (on: boolean) => void;
}

const round = (x: number) => Math.round(x * 20) / 20;

export class SceneViewer {
  meta: Meta | null = null;
  frame = 1;
  private renderer: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(40, 16 / 9, 0.05, 300);
  private controls: OrbitControls;
  private mixer: THREE.AnimationMixer | null = null;
  private model: THREE.Object3D | null = null;
  private url: string | null = null;
  private markers = new THREE.Group();
  private ray = new THREE.Raycaster();
  private floor = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
  private isPlaying = false;
  private throughLens = false;                               // showing the render's own camera
  private scissored = false;                                 // ...and letterboxed to its shape
  private last = 0;
  private dragging: {marker: THREE.Object3D; from: THREE.Vector3} | null = null;
  private selected: string | null = null;
  private observer: ResizeObserver;
  private fixed = new Map<THREE.Bone, THREE.Quaternion>();   // bones held by a pose-fix preview
  private fixTurn = new THREE.Quaternion();                  // the turn that preview applies
  private sun!: THREE.DirectionalLight;
  private sky!: THREE.HemisphereLight;
  private rim!: THREE.DirectionalLight;

  constructor(private host: HTMLElement, private hooks: Hooks) {
    this.renderer = new THREE.WebGLRenderer({antialias: true});
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    host.prepend(this.renderer.domElement);
    this.scene.background = new THREE.Color(0x101318);
    this.camera.position.set(0, 1.8, 7);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.target.set(0, 1, 0);
    this.controls.enableDamping = true;
    const sun = new THREE.DirectionalLight(0xffffff, 1.8);
    sun.position.set(3, 6, 5);
    this.sun = sun;
    this.sky = new THREE.HemisphereLight(0xffffff, 0x3a3f4a, 2.4);
    this.rim = new THREE.DirectionalLight(0xffffff, 0.0);
    this.rim.position.set(-4, 3, -5);
    const grid = new THREE.GridHelper(30, 30, 0x3a4152, 0x232836);
    (grid.material as THREE.Material).transparent = true;
    (grid.material as THREE.Material).opacity = 0.6;
    this.scene.add(this.sky, sun, this.rim, grid, this.markers);
    this.observer = new ResizeObserver(() => this.resize());
    this.observer.observe(host);
    this.resize();
    host.addEventListener("pointerdown", this.down, true);      // before OrbitControls: a marker drag must not orbit
    addEventListener("pointermove", this.move);
    addEventListener("pointerup", this.up);
    this.renderer.setAnimationLoop(this.tick);
  }

  dispose() {
    this.renderer.setAnimationLoop(null);
    this.observer.disconnect();
    this.host.removeEventListener("pointerdown", this.down, true);
    removeEventListener("pointermove", this.move);
    removeEventListener("pointerup", this.up);
    this.controls.dispose();
    this.renderer.dispose();
    this.renderer.domElement.remove();
  }

  private resize() {
    const w = this.host.clientWidth, h = this.host.clientHeight || Math.round(w * 9 / 16);
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  private tick = (now: number) => {
    if (this.isPlaying && this.meta) {
      this.frame += (now - this.last) / 1000 * this.meta.fps;
      if (this.frame >= this.meta.frames) { this.frame = this.meta.frames; this.setPlaying(false); }
      this.seek(this.frame, false);
    }
    this.last = now;
    if (this.fixed.size) {                         // the clip drives the bones; the fix sits on top
      for (const [bone, rest] of this.fixed) {
        rest.copy(bone.quaternion);
        bone.quaternion.multiply(this.fixTurn);
      }
    }
    this.controls.update();
    // Through the lens, the picture is the render's shape, not the panel's: without the bars you are
    // judging a framing that will be cropped or padded when it is actually rendered.
    const w = this.renderer.domElement.clientWidth, h = this.renderer.domElement.clientHeight;
    const want = this.throughLens && this.meta?.res ? this.meta.res[0] / this.meta.res[1] : 0;
    if (want) {
      const box = w / h > want ? {w: h * want, h} : {w, h: w / want};
      this.renderer.setScissorTest(true);
      this.renderer.setScissor((w - box.w) / 2, (h - box.h) / 2, box.w, box.h);
      this.renderer.setViewport((w - box.w) / 2, (h - box.h) / 2, box.w, box.h);
      if (Math.abs(this.camera.aspect - want) > 1e-4) {
        this.camera.aspect = want;
        this.camera.updateProjectionMatrix();
      }
    } else if (this.scissored) {
      this.renderer.setScissorTest(false);
      this.renderer.setViewport(0, 0, w, h);
      this.resize();
    }
    this.scissored = !!want;
    this.renderer.render(this.scene, this.camera);
  };

  private setPlaying(on: boolean) {
    this.isPlaying = on;
    this.hooks.playing(on);
  }
  toggle() {
    if (!this.meta) return;
    if (this.frame >= this.meta.frames) this.seek(1);
    this.setPlaying(!this.isPlaying);
  }
  seek(f: number, stop = true) {
    if (!this.meta) return;
    if (stop && this.isPlaying) this.setPlaying(false);
    this.frame = Math.max(1, Math.min(this.meta.frames, f));
    this.mixer?.setTime((this.frame - 1) / this.meta.fps);
    if (this.throughLens) this.putCamera(this.frame);
    this.hooks.frame(this.frame, this.meta);
  }

  /** Which shot is on screen at a frame, and where its camera is by then. */
  shotAt(frame: number): Cam | null {
    const cams = this.meta?.cameras || [];
    let found: Cam | null = null;
    for (const c of cams) if (frame >= c.f0) found = c;
    return found || cams[0] || null;
  }

  /**
   * Look through the lens the render will use, instead of flying around beside it.
   *
   * The camera is not worked out again here: scene_kit writes down where it put each one, so this only
   * slides between the samples. A moving shot was walked every 8 frames; a still one has a single
   * sample and never moves.
   */
  lens(on: boolean) {
    this.throughLens = on && !!(this.meta?.cameras || []).length;
    this.controls.enabled = !this.throughLens;
    if (this.throughLens) this.putCamera(this.frame);
    else {
      this.camera.fov = 40;
      this.camera.updateProjectionMatrix();
      this.frameCamera(false);
    }
    return this.throughLens;
  }

  get lensOn() { return this.throughLens; }

  private putCamera(frame: number) {
    const cam = this.shotAt(frame);
    if (!cam || !cam.track.length || !this.meta) return;
    const t = cam.track;
    let i = 0;
    while (i < t.length - 1 && t[i + 1][0] <= frame) i++;
    const a = t[i], b = t[Math.min(i + 1, t.length - 1)];
    const k = b[0] > a[0] ? Math.min(1, Math.max(0, (frame - a[0]) / (b[0] - a[0]))) : 0;
    const at = (j: number) => a[j] + (b[j] - a[j]) * k;
    const [ox, oy] = this.meta.origin;
    this.camera.position.set(at(1) + ox, at(3), -(at(2) + oy));
    this.camera.lookAt(this.camera.position.clone().add(new THREE.Vector3(at(4), at(6), -at(5))));
    if (this.camera.fov !== cam.fov) {
      this.camera.fov = cam.fov;
      this.camera.updateProjectionMatrix();
    }
  }

  private toThree = (p: [number, number]) => new THREE.Vector3(p[0] + this.meta!.origin[0], 0.01, -(p[1] + this.meta!.origin[1]));
  private toStage = (v: THREE.Vector3): [number, number] => [round(v.x - this.meta!.origin[0]), round(-v.z - this.meta!.origin[1])];
  colorOf(who: string) {
    return COLORS[Math.max(0, Object.keys(this.meta?.cast || {}).indexOf(who)) % COLORS.length];
  }

  async load(p: Preview | null) {
    if (!p) {
      if (this.model) this.scene.remove(this.model);
      this.model = this.meta = this.mixer = this.url = null;
      this.markers.clear();
      return;
    }
    if (p.glb === this.url) return;
    this.hooks.note("Loading the 3D scene…");
    const meta: Meta = await (await fetch(p.meta)).json();
    const gltf = await new GLTFLoader().loadAsync(p.glb);
    if (this.model) this.scene.remove(this.model);
    this.model = gltf.scene;
    const hasSet = !!this.model.getObjectByName("Set");
    this.model.traverse(o => {
      if ((o as THREE.SkinnedMesh).isSkinnedMesh) {
        o.frustumCulled = false;                                 // moving bodies leave their bounds
        for (const m of [(o as THREE.Mesh).material].flat() as THREE.Material[]) {
          m.transparent = false; m.alphaTest = 0.5; m.depthWrite = true;   // MakeHuman materials come as blended
        }
      }
      if (hasSet && o.name === "Backdrop") o.visible = false;    // the far backdrop only matters to the film camera
    });
    this.scene.add(this.model);
    this.meta = meta;
    this.mixer = new THREE.AnimationMixer(this.model);
    gltf.animations.forEach(clip => this.mixer!.clipAction(clip).play());
    this.url = p.glb;
    this.frameCamera();
    this.redraw();
    this.seek(1);
    this.hooks.note(this.stale() ? "The scene changed since this preview: Build 3D preview to see the new version." : "");
  }

  stale() {
    const s = this.hooks.script();
    return !!this.meta && (s.length !== this.meta.steps.length || this.meta.steps.some((x, i) => s[i]?.do !== x.do));
  }

  /**
   * Swing the view round what it is looking at, and come closer or go further out.
   *
   * The mouse can already do this, but only if you know that dragging orbits and the wheel zooms. A stick
   * you hold is the same move without the lesson, and it is the only way to do it on a trackpad with no
   * wheel. `x` swings left and right, `y` lifts and drops the eye, both -1..1; `by` is one zoom notch.
   */
  orbit(x: number, y: number) {
    const eye = this.camera.position.clone().sub(this.controls.target);
    const radius = eye.length();
    const around = Math.atan2(eye.x, eye.z) - x * 0.035;
    // stop just short of straight up and straight down: at either pole the view flips over
    const up = Math.min(Math.PI - 0.08, Math.max(0.08, Math.acos(eye.y / radius) + y * 0.025));
    this.camera.position.set(
      this.controls.target.x + radius * Math.sin(up) * Math.sin(around),
      this.controls.target.y + radius * Math.cos(up),
      this.controls.target.z + radius * Math.sin(up) * Math.cos(around));
    this.camera.lookAt(this.controls.target);
  }

  zoom(by: number) {
    const eye = this.camera.position.clone().sub(this.controls.target);
    const want = Math.min(40, Math.max(0.8, eye.length() * (by > 0 ? 1.15 : 1 / 1.15)));
    this.camera.position.copy(this.controls.target).add(eye.setLength(want));
  }

  frameCamera(top = false) {
    if (!this.meta) return;
    const spots = Object.keys(this.meta.cast).map(w => this.toThree(this.hooks.start(w)));
    const c = spots.reduce((a, v) => a.add(v), new THREE.Vector3()).multiplyScalar(1 / Math.max(1, spots.length));
    this.controls.target.set(c.x, top ? 0 : 1, c.z);
    this.camera.position.set(c.x, top ? 11 : 2.2, c.z + (top ? 0.01 : 6.5));
  }

  private disc(color: string, inner: number, outer: number) {
    const g = inner ? new THREE.RingGeometry(inner, outer, 40) : new THREE.CircleGeometry(outer, 40);
    const m = new THREE.Mesh(g, new THREE.MeshBasicMaterial({color, transparent: true, opacity: 0.88, depthTest: false}));
    m.rotation.x = -Math.PI / 2;
    m.renderOrder = 2;
    return m;
  }
  private pad(color: string, fromSet: boolean) {
    const g = new THREE.RingGeometry(0.17, 0.23, 4);
    const m = new THREE.Mesh(g, new THREE.MeshBasicMaterial(
      {color, transparent: true, opacity: fromSet ? 0.5 : 0.95, depthTest: false}));
    m.rotation.x = -Math.PI / 2;
    m.renderOrder = 2;
    return m;
  }
  private label(text: string, color: string) {
    const c = document.createElement("canvas"), g = c.getContext("2d")!;
    c.width = 256; c.height = 64;
    g.font = "600 32px Inter, system-ui, sans-serif"; g.fillStyle = color; g.textAlign = "center"; g.fillText(text, 128, 44);
    const s = new THREE.Sprite(new THREE.SpriteMaterial({map: new THREE.CanvasTexture(c), depthTest: false}));
    s.scale.set(1.0, 0.25, 1);
    s.renderOrder = 3;
    return s;
  }

  redraw() {
    this.markers.clear();
    if (!this.meta) return;
    const script = this.hooks.script();
    for (const who of Object.keys(this.meta.cast)) {
      const color = this.colorOf(who), path = [this.toThree(this.hooks.start(who))];
      const start = this.disc(color, 0, who === this.selected ? 0.26 : 0.2);
      start.position.copy(path[0]);
      start.userData = {kind: "start", who};
      const tag = this.label(who, color);
      tag.position.copy(path[0]).add(new THREE.Vector3(0, 2.15, 0));
      this.markers.add(start, tag);
      script.forEach((st, n) => {
        if (st?.who !== who || !Array.isArray(st.to)) return;
        const ring = this.disc(color, 0.13, 0.2);
        ring.position.copy(this.toThree(st.to));
        ring.userData = {kind: "to", who, n};
        this.markers.add(ring);
        path.push(ring.position.clone());
      });
      if (path.length > 1) {
        const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(path),
          new THREE.LineDashedMaterial({color, dashSize: 0.15, gapSize: 0.1, depthTest: false}));
        line.computeLineDistances();
        line.renderOrder = 1;
        this.markers.add(line);
      }
    }
    this.drawProps();
  }

  /** Prop markers: a scene prop is solid, one that came with the set is faint until it is moved here. */
  private drawProps() {
    const live = new Map(this.hooks.props().map(pr => [pr.id, pr]));
    const all = [...(this.meta?.props || [])];
    for (const pr of live.values()) if (!all.some(x => x.id === pr.id)) all.push(pr as never);
    for (const built of all) {
      const pr = {...built, ...(live.get(built.id) || {})};
      if (!Array.isArray(pr.position) || pr.on) continue;        // one standing on another is placed by its host
      const color = pr.from_set ? "#8aa0c0" : "#d7b36a";
      const pad = this.pad(color, !!pr.from_set && !live.has(pr.id));
      pad.position.copy(this.toThree(pr.position as [number, number]));
      pad.position.y = 0.012;
      pad.userData = {kind: "prop", id: pr.id, fromSet: !!pr.from_set};
      const tag = this.label(pr.id, color);
      tag.position.copy(pad.position).add(new THREE.Vector3(0, 0.55, 0));
      tag.scale.set(0.7, 0.18, 1);
      this.markers.add(pad, tag);
    }
  }

  select(who: string | null) {
    this.selected = who;
    this.redraw();
  }

  // --- pose-fix preview: turn one bone of one character, so a fix can be seen while it is dialled in ------
  /** The deform bone a plain part name drives in the exported preview ("upper_arm.L" -> "DEF-upper_arm.L"). */
  private boneOf(who: string, part: string): THREE.Bone | null {
    const rig = this.meta?.cast[who]?.rig;
    const root = (rig && this.model?.getObjectByName(rig)) || this.model;
    if (!root) return null;
    const want = part === "hips" ? "spine" : part;
    const names = [`DEF-${want}`, want, `DEF-${want}.001`];
    for (const n of names) {
      const found = root.getObjectByName(n);
      if (found && (found as THREE.Bone).isBone) return found as THREE.Bone;
    }
    return null;
  }

  /** Show a fix on the preview model: `degrees` [x, y, z], or null to put the bone back. */
  previewFix(who: string | null, part: string | null, degrees: [number, number, number] | null) {
    for (const [bone, rest] of this.fixed) bone.quaternion.copy(rest);
    this.fixed.clear();
    if (!who || !part || !degrees || !degrees.some(d => d)) return;
    const bone = this.boneOf(who, part);
    if (!bone) return;
    const e = new THREE.Euler(...degrees.map(d => d * Math.PI / 180) as [number, number, number]);
    this.fixTurn.setFromEuler(e);
    this.fixed.set(bone, bone.quaternion.clone());
    bone.quaternion.multiply(this.fixTurn);
  }

  /** True when this character's body part exists in the preview (so the panel can say when it cannot show it). */
  canPreview(who: string, part: string) {
    return !!this.boneOf(who, part);
  }

  // --- the scene's own light, so the editor is not lit differently from the render --------------------------
  /** Light the preview the way the scene's lighting mood and weather will light the render (schema LIGHTING:
   * each entry is [strength, [r, g, b]]). `null` puts the plain editor light back. */
  setLook(preset: Record<string, [number, [number, number, number]]> | null, weather?: string) {
    const col = (c: [number, number, number]) => new THREE.Color(c[0], c[1], c[2]).convertSRGBToLinear();
    if (!preset) {
      this.sun.intensity = 1.8; this.sun.color.setHex(0xffffff);
      this.sky.intensity = 2.4; this.sky.color.setHex(0xffffff);
      this.rim.intensity = 0;
      this.scene.background = new THREE.Color(0x101318);
      return;
    }
    const [ks, kc] = preset.key || [1, [1, 1, 1]];
    const [fs, fc] = preset.fill || [1, [1, 1, 1]];
    const [rs, rc] = preset.rim || [1, [1, 1, 1]];
    const [ws, wc] = preset.world || [1, [1, 1, 1]];
    const dim = weather === "rain" ? 0.75 : weather === "snow" ? 0.9 : 1.0;
    this.sun.intensity = 1.8 * ks * dim;
    this.sun.color.copy(col(kc));
    this.sky.intensity = 1.6 * fs * dim + 0.5;              // never fully black: the editor must stay readable
    this.sky.color.copy(col(fc));
    this.rim.intensity = 0.9 * rs * dim;
    this.rim.color.copy(col(rc));
    const bg = col(wc).multiplyScalar(Math.min(1, 0.1 + 0.16 * ws));
    this.scene.background = bg;
  }

  private pointer(e: PointerEvent) {
    const r = this.renderer.domElement.getBoundingClientRect();
    this.ray.setFromCamera(new THREE.Vector2((e.clientX - r.left) / r.width * 2 - 1, -(e.clientY - r.top) / r.height * 2 + 1), this.camera);
  }
  private down = (e: PointerEvent) => {
    if (!this.meta || e.button !== 0) return;
    this.pointer(e);
    const hit = this.ray.intersectObjects(this.markers.children.filter(m => m.userData.kind), false)[0];
    if (hit) {
      const {kind, who, n} = hit.object.userData;
      if (kind === "prop") {
        e.stopPropagation();
        this.controls.enabled = false;
        this.dragging = {marker: hit.object, from: hit.object.position.clone()};
        return;
      }
      const seat = this.hooks.seat(who);
      if (kind === "start" && seat) {                 // the seat decides where a seated person starts
        this.select(who);
        this.hooks.select(who);
        this.hooks.note(`${who} starts seated on “${seat}”: move that seat in Set props, or remove the seat to place ${who} freely.`);
        return;
      }
      e.stopPropagation();
      this.controls.enabled = false;
      this.dragging = {marker: hit.object, from: hit.object.position.clone()};
      this.select(who);
      this.hooks.select(who, n);
      return;
    }
    const body = this.model && this.ray.intersectObject(this.model, true)[0];
    if (body) {
      let o: THREE.Object3D | null = body.object;
      const rigs = Object.entries(this.meta.cast);
      while (o && !rigs.some(([, c]) => c.rig === o!.name)) o = o.parent;
      const who = o && rigs.find(([, c]) => c.rig === o!.name)?.[0];
      if (who) { this.select(who); this.hooks.select(who); }
    }
  };
  private move = (e: PointerEvent) => {
    if (!this.dragging) return;
    this.pointer(e);
    const p = new THREE.Vector3();
    if (this.ray.ray.intersectPlane(this.floor, p)) {
      const {kind, who, id} = this.dragging.marker.userData;
      this.dragging.marker.position.set(p.x, kind === "prop" ? 0.012 : 0.01, p.z);
      this.hooks.note(kind === "prop" ? `${id}: [${this.toStage(p).join(", ")}]`
        : `${who}: ${kind === "start" ? "starts at" : "walks to"} [${this.toStage(p).join(", ")}]`);
    }
  };
  private up = () => {
    if (!this.dragging) return;
    const {marker, from} = this.dragging;
    this.dragging = null;
    this.controls.enabled = true;
    if (marker.position.distanceTo(from) < 0.02) return;
    const {kind, who, n, id, fromSet} = marker.userData;
    if (kind === "prop") return this.hooks.dropProp(id, this.toStage(marker.position), fromSet);
    this.hooks.drop(kind, who, n, this.toStage(marker.position));
  };

  screenOf(who: string): [number, number] {
    const v = this.toThree(this.hooks.start(who)).project(this.camera), r = this.renderer.domElement.getBoundingClientRect();
    return [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height];
  }
}
