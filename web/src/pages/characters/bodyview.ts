// The designer's live body: the plain shape, morphed as the sliders move, with no build in the loop.
//
// A "kit" (blender/preview_kit.py) is the body mesh plus the vertices each morph target moves. Applying a
// slider is then a handful of adds over about 830 vertices, which is nothing - so the body changes under
// your hand instead of four minutes later.
//
// Turning it: drag anywhere to turn the body, or grab a ring - the green one round its feet spins it, the
// red one standing up beside it tips it. The wheel zooms. Nothing here changes the design; it only looks.
import * as THREE from "three";

export interface Kit {
  version: number;
  vertices: number; triangles: number; height: number;
  positions: {at: number; count: number};
  indices: {at: number; count: number};
  shapes: Record<string, {at: number; count: number}>;
}

export const RING_SPIN = "#49c96d";          // green: turn it round, left and right
export const RING_TIP = "#e4564a";           // red: tip it up and down

type Grab = null | "orbit" | "spin" | "tip";

export class BodyView {
  private renderer: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private camera: THREE.PerspectiveCamera;
  private mesh: THREE.Mesh | null = null;
  private base: Float32Array | null = null;           // the body with every slider in the middle
  private work: Float32Array | null = null;           // what is drawn: base + whatever is asked for
  private shapes = new Map<string, {idx: Uint32Array; d: Float32Array}>();
  private rings = new THREE.Group();
  private spinRing!: THREE.Mesh;
  private tipRing!: THREE.Mesh;

  private yaw = 0.5; private pitch = 0.08; private dist = 3.4;
  private target = new THREE.Vector3(0, 0.95, 0);
  private wanted = {dist: 3.4, target: new THREE.Vector3(0, 0.95, 0)};
  private grab: Grab = null;
  private last = {x: 0, y: 0};
  private hover: Grab = null;
  private raf = 0;
  private alive = true;
  height = 1.8;

  constructor(private canvas: HTMLCanvasElement) {
    this.renderer = new THREE.WebGLRenderer({canvas, antialias: true, alpha: true});
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.camera = new THREE.PerspectiveCamera(32, 1, 0.1, 100);
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x47506a, 2.1));
    const key = new THREE.DirectionalLight(0xfff2e2, 2.4); key.position.set(2.2, 3.4, 2.6);
    const rim = new THREE.DirectionalLight(0x9fc4ff, 1.5); rim.position.set(-2.6, 1.8, -2.2);
    this.scene.add(key, rim);
    this.makeRings();
    this.scene.add(this.rings);
    this.bind();
    this.resize();
    this.tick();
  }

  // --- the two rings you can grab --------------------------------------------------------------------
  private makeRings() {
    const ring = (colour: string, radius: number) => {
      const m = new THREE.Mesh(
        new THREE.TorusGeometry(radius, 0.012, 10, 96),
        new THREE.MeshBasicMaterial({color: colour, transparent: true, opacity: 0.55, depthWrite: false}));
      m.renderOrder = 2;
      return m;
    };
    this.spinRing = ring(RING_SPIN, 0.78);            // lies on the floor: turning it spins the body
    this.spinRing.rotation.x = Math.PI / 2;
    this.tipRing = ring(RING_TIP, 0.78);              // stands up at the side: turning it tips the body
    this.tipRing.rotation.y = Math.PI / 2;
    this.tipRing.position.y = 0.95;
    this.rings.add(this.spinRing, this.tipRing);
  }

  private setRingLook() {
    for (const [m, base] of [[this.spinRing, "spin"], [this.tipRing, "tip"]] as const) {
      const live = this.grab === base || (!this.grab && this.hover === base);
      (m.material as THREE.MeshBasicMaterial).opacity = live ? 1 : 0.5;
      m.scale.setScalar(live ? 1.05 : 1);
    }
    this.canvas.style.cursor = this.grab ? "grabbing" : this.hover ? "grab" : "move";
  }

  // --- loading a kit ---------------------------------------------------------------------------------
  async load(kit: Kit, bin: ArrayBuffer) {
    const positions = new Float32Array(bin, kit.positions.at, kit.positions.count * 3);
    const indices = new Uint32Array(bin, kit.indices.at, kit.indices.count);
    this.shapes.clear();
    for (const [name, where] of Object.entries(kit.shapes)) {
      const idx = new Uint32Array(bin, where.at, where.count);
      this.shapes.set(name, {idx, d: new Float32Array(bin, where.at + where.count * 4, where.count * 3)});
    }
    this.base = positions;
    this.work = new Float32Array(positions);          // a copy: the base is never written to
    this.height = kit.height || 1.8;

    if (this.mesh) {
      this.mesh.geometry.dispose();
      this.scene.remove(this.mesh);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(this.work, 3));
    g.setIndex(new THREE.BufferAttribute(indices, 1));
    g.computeVertexNormals();
    this.mesh = new THREE.Mesh(g, new THREE.MeshStandardMaterial({
      color: 0xd8b49a, roughness: 0.72, metalness: 0.0, flatShading: false}));
    this.scene.add(this.mesh);
    this.rings.position.y = 0;
    this.spinRing.scale.setScalar(1);
    this.tipRing.position.y = this.height * 0.52;
    this.frame("whole");
  }

  /** Put the sliders on the body. `targets` is {morph target: weight}, exactly what the build applies. */
  apply(targets: Record<string, number>) {
    if (!this.base || !this.work || !this.mesh) return;
    this.work.set(this.base);
    for (const [name, weight] of Object.entries(targets)) {
      const shape = this.shapes.get(name);
      if (!shape || !weight) continue;
      const {idx, d} = shape;
      for (let i = 0; i < idx.length; i++) {
        const v = idx[i] * 3, k = i * 3;
        this.work[v] += d[k] * weight;
        this.work[v + 1] += d[k + 1] * weight;
        this.work[v + 2] += d[k + 2] * weight;
      }
    }
    const attr = this.mesh.geometry.getAttribute("position") as THREE.BufferAttribute;
    attr.needsUpdate = true;
    this.mesh.geometry.computeVertexNormals();
  }

  /** Look at the whole person, or close in on what is being edited. */
  frame(what: "whole" | "face" | "body") {
    const h = this.height;
    if (what === "face") {
      this.wanted.target.set(0, h * 0.92, 0);
      this.wanted.dist = h * 0.42;
    } else if (what === "body") {
      this.wanted.target.set(0, h * 0.58, 0);
      this.wanted.dist = h * 1.25;
    } else {
      this.wanted.target.set(0, h * 0.53, 0);
      this.wanted.dist = h * 1.9;
    }
  }

  /** Front, side, back or three-quarter, eased to rather than snapped. */
  turnTo(view: "front" | "side" | "back" | "three_quarter") {
    this.yaw = {front: 0, side: Math.PI / 2, back: Math.PI, three_quarter: 0.7}[view];
    this.pitch = 0.08;
  }

  showRings(on: boolean) { this.rings.visible = on; }

  // --- turning it ------------------------------------------------------------------------------------
  private pick(e: PointerEvent): Grab {
    if (!this.rings.visible) return "orbit";
    const r = this.canvas.getBoundingClientRect();
    const p = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1,
                                -((e.clientY - r.top) / r.height) * 2 + 1);
    const ray = new THREE.Raycaster();
    ray.params.Line = {threshold: 0.06};
    ray.setFromCamera(p, this.camera);
    const hit = ray.intersectObjects([this.spinRing, this.tipRing], false)[0];
    if (!hit) return "orbit";
    return hit.object === this.spinRing ? "spin" : "tip";
  }

  private bind() {
    this.canvas.addEventListener("pointerdown", e => {
      this.grab = this.pick(e);
      this.last = {x: e.clientX, y: e.clientY};
      this.canvas.setPointerCapture(e.pointerId);
      this.setRingLook();
    });
    this.canvas.addEventListener("pointermove", e => {
      if (!this.grab) {
        const over = this.pick(e);
        if (over !== this.hover) { this.hover = over === "orbit" ? null : over; this.setRingLook(); }
        return;
      }
      const dx = e.clientX - this.last.x, dy = e.clientY - this.last.y;
      this.last = {x: e.clientX, y: e.clientY};
      if (this.grab !== "tip") this.yaw -= dx * 0.01;                 // orbit and the green ring turn it
      if (this.grab !== "spin") this.pitch = Math.max(-0.9, Math.min(1.1, this.pitch + dy * 0.006));
    });
    const stop = (e: PointerEvent) => {
      if (!this.grab) return;
      this.grab = null;
      try { this.canvas.releasePointerCapture(e.pointerId); } catch { /* already gone */ }
      this.setRingLook();
    };
    this.canvas.addEventListener("pointerup", stop);
    this.canvas.addEventListener("pointercancel", stop);
    this.canvas.addEventListener("pointerleave", () => { if (!this.grab) { this.hover = null; this.setRingLook(); } });
    this.canvas.addEventListener("wheel", e => {
      e.preventDefault();
      this.wanted.dist = Math.max(0.35, Math.min(6, this.wanted.dist * (1 + Math.sign(e.deltaY) * 0.12)));
    }, {passive: false});
    this.canvas.addEventListener("dblclick", () => this.frame("whole"));
  }

  resize() {
    const w = this.canvas.clientWidth || 1, h = this.canvas.clientHeight || 1;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  private tick = () => {
    if (!this.alive) return;
    this.raf = requestAnimationFrame(this.tick);
    this.dist += (this.wanted.dist - this.dist) * 0.18;              // ease, so nothing jumps
    this.target.lerp(this.wanted.target, 0.18);
    const cp = Math.cos(this.pitch);
    this.camera.position.set(this.target.x + this.dist * cp * Math.sin(this.yaw),
                             this.target.y + this.dist * Math.sin(this.pitch),
                             this.target.z + this.dist * cp * Math.cos(this.yaw));
    this.camera.lookAt(this.target);
    this.rings.position.y = 0;
    this.spinRing.position.y = 0.01;
    this.renderer.render(this.scene, this.camera);
  };

  dispose() {
    this.alive = false;
    cancelAnimationFrame(this.raf);
    this.mesh?.geometry.dispose();
    this.renderer.dispose();
  }
}
