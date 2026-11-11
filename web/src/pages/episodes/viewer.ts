// The 3D scene viewer (three.js): the scene's preview.glb with its animation, plus markers for where each person
// starts (disc) and walks to (rings). Stage spots are [x, y] metres; glTF is Y-up (Blender x, y, z -> three x, z, -y).
import * as THREE from "three";
import {GLTFLoader} from "three/examples/jsm/loaders/GLTFLoader.js";
import {OrbitControls} from "three/examples/jsm/controls/OrbitControls.js";
import {Json, Preview} from "../../api";
import {COLORS} from "./SceneSetup";

export interface Meta {
  fps: number; frames: number; origin: [number, number];
  cast: Record<string, {start: [number, number]; rig: string}>;
  steps: {n: number; who?: string; do: string; f0: number; f1: number}[];
  lines?: {who: string; text: string; start: number; end: number}[];
}
export interface Hooks {
  start: (who: string) => [number, number];          // where the live scene says someone starts
  script: () => Json[];
  seat: (who: string) => string | undefined;
  frame: (frame: number, meta: Meta) => void;
  note: (text: string) => void;
  select: (who: string | null, n?: number) => void;
  drop: (kind: "start" | "to", who: string, n: number | undefined, spot: [number, number]) => void;
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
  private last = 0;
  private dragging: {marker: THREE.Object3D; from: THREE.Vector3} | null = null;
  private selected: string | null = null;
  private observer: ResizeObserver;

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
    const grid = new THREE.GridHelper(30, 30, 0x3a4152, 0x232836);
    (grid.material as THREE.Material).transparent = true;
    (grid.material as THREE.Material).opacity = 0.6;
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x3a3f4a, 2.4), sun, grid, this.markers);
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
    this.controls.update();
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
    this.hooks.frame(this.frame, this.meta);
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
  }

  select(who: string | null) {
    this.selected = who;
    this.redraw();
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
      this.dragging.marker.position.set(p.x, 0.01, p.z);
      const {kind, who} = this.dragging.marker.userData;
      this.hooks.note(`${who}: ${kind === "start" ? "starts at" : "walks to"} [${this.toStage(p).join(", ")}]`);
    }
  };
  private up = () => {
    if (!this.dragging) return;
    const {marker, from} = this.dragging;
    this.dragging = null;
    this.controls.enabled = true;
    if (marker.position.distanceTo(from) < 0.02) return;
    const {kind, who, n} = marker.userData;
    this.hooks.drop(kind, who, n, this.toStage(marker.position));
  };

  screenOf(who: string): [number, number] {
    const v = this.toThree(this.hooks.start(who)).project(this.camera), r = this.renderer.domElement.getBoundingClientRect();
    return [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height];
  }
}
