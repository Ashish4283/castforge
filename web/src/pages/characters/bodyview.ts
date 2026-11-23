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

export interface WornSpec {                  // one thing being worn, as the server hands it over
  role: string; asset: string; tint: string | null;
  vertices: number; triangles: number; texture: string | null; median: number;
  x_scale: [number, number, number]; y_scale: [number, number, number]; z_scale: [number, number, number];
  verts: {at: number; count: number}; weights: {at: number; count: number};
  offsets: {at: number; count: number}; uv: {at: number; count: number};
  indices: {at: number; count: number}; hides: {at: number; count: number};
}
export interface Worn { spec: WornSpec; bin: ArrayBuffer; colour?: string; texture?: THREE.Texture | null }

/** Colour a garment the way the build colours it.
 *
 *  Not colour x texture - that turns a dark knit black, which is what the live view used to do. The build
 *  uses colour x (luminance / the texture's median luminance), so the weave reads as light and shade
 *  AROUND the colour asked for; and it keeps less of that contrast for pale colours, or white cloth comes
 *  out grey. `median` is measured when the garment is exported (blender/preview_wear.py). */
function tintLikeTheBuild(material: THREE.MeshStandardMaterial, median: number) {
  const linear = material.color.clone().convertSRGBToLinear();
  const light = 0.2126 * linear.r + 0.7152 * linear.g + 0.0722 * linear.b;
  const keep = 1 - 0.75 * Math.min(light / 0.6, 1);
  material.onBeforeCompile = shader => {
    shader.uniforms.cfMedian = {value: Math.max(median, 0.02)};
    shader.uniforms.cfKeep = {value: keep};
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>",
               ["#include <common>", "uniform float cfMedian;", "uniform float cfKeep;"].join("\n"))
      .replace("#include <map_fragment>", [
        "#ifdef USE_MAP",
        "  vec4 cfTexel = texture2D( map, vMapUv );",
        "  float cfLum = dot( cfTexel.rgb, vec3( 0.2126, 0.7152, 0.0722 ) );",
        "  float cfDetail = cfKeep * ( cfLum / cfMedian ) + ( 1.0 - cfKeep );",
        "  diffuseColor.rgb *= cfDetail;",
        "  diffuseColor.a *= cfTexel.a;",
        "#endif",
      ].join("\n"));
  };
  material.needsUpdate = true;
}

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
  private wearing: {worn: Worn; mesh: THREE.Mesh; idx: Uint32Array; weight: Float32Array;
                    off: Float32Array; pos: Float32Array; hides: Uint32Array; scale: Float32Array}[] = [];
  private tris: Uint32Array | null = null;   // the body's triangles, which garments are pinned to
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
  private looking: "whole" | "face" | "body" | "spot" = "whole";   // what was last asked for
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
    this.tris = indices;
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
    this.dress();
    // keep looking at whatever was being edited: a new body (a different age or build) must not throw the
    // camera back out to the whole figure in the middle of someone shaping a nose
    if (this.looking !== "spot") this.frame(this.looking);
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
    this.dress();
  }

  /** Put everything worn back on the body as it stands now: the browser's half of preview_mesh.py.
   *
   *  A garment vertex is "this far off that body triangle", so it is simply worked out again from the
   *  triangle's new corners. The offset along the triangle's normal is held to at least the layer's own
   *  thickness, which is what keeps cloth outside the body however the sliders push it about. */
  private dress() {
    const body = this.work;
    if (!body) return;
    for (const w of this.wearing) {
      const {idx, weight, off, pos, scale} = w;
      // the three spans this garment's offsets were measured against, measured on THIS body
      const span = (ref: [number, number, number], axis: number) =>
        Math.abs(body[ref[0] * 3 + axis] - body[ref[1] * 3 + axis]) / ref[2];
      scale[0] = span(w.worn.spec.x_scale, 0);
      scale[1] = span(w.worn.spec.y_scale, 1);
      scale[2] = span(w.worn.spec.z_scale, 2);
      for (let i = 0; i < pos.length / 3; i++) {
        const a = idx[i * 3] * 3, b = idx[i * 3 + 1] * 3, c = idx[i * 3 + 2] * 3;
        const wa = weight[i * 3], wb = weight[i * 3 + 1], wc = weight[i * 3 + 2];
        for (let k = 0; k < 3; k++) {
          pos[i * 3 + k] = body[a + k] * wa + body[b + k] * wb + body[c + k] * wc
                           + off[i * 3 + k] * scale[k];
        }
      }
      const attr = w.mesh.geometry.getAttribute("position") as THREE.BufferAttribute;
      attr.needsUpdate = true;
      w.mesh.geometry.computeVertexNormals();
    }
  }

  /** Leave the skin undrawn where a garment covers it.
   *
   *  MakeHuman lists, with each garment, the body vertices it hides. Dropping those triangles is what
   *  keeps a belly from coming through its own shirt however far a slider pushes it out - and it is what
   *  the build does too, so the live view and the render agree. */
  private hideCovered() {
    if (!this.mesh || !this.tris) return;
    const hidden = new Set<number>();
    for (const w of this.wearing) for (const v of w.hides) hidden.add(v);
    const keep: number[] = [];
    for (let t = 0; t < this.tris.length; t += 3) {
      if (hidden.has(this.tris[t]) || hidden.has(this.tris[t + 1]) || hidden.has(this.tris[t + 2])) continue;
      keep.push(this.tris[t], this.tris[t + 1], this.tris[t + 2]);
    }
    this.mesh.geometry.setIndex(new THREE.BufferAttribute(new Uint32Array(keep), 1));
    this.mesh.geometry.computeVertexNormals();
  }

  /** The skin's colour, as the design has it (left alone when it says nothing). */
  setSkin(colour?: string) {
    const mat = this.mesh?.material as THREE.MeshStandardMaterial | undefined;
    if (mat) mat.color.set(colour || "#d8b49a");
  }

  /** Dress the body: everything the design puts on, each pinned to the body's own triangles. */
  setWearing(items: Worn[]) {
    for (const w of this.wearing) {
      this.scene.remove(w.mesh);
      w.mesh.geometry.dispose();
      (w.mesh.material as THREE.Material).dispose();
    }
    this.wearing = [];
    for (const worn of items) {
      const {spec, bin} = worn;
      const n = spec.vertices;
      const idx = new Uint32Array(bin, spec.verts.at, n * 3);
      const weight = new Float32Array(bin, spec.weights.at, n * 3);
      const off = new Float32Array(bin, spec.offsets.at, n * 3);
      const uv = new Float32Array(bin, spec.uv.at, n * 2);
      const faces = new Uint32Array(bin, spec.indices.at, spec.indices.count);
      const hides = spec.hides.count ? new Uint32Array(bin, spec.hides.at, spec.hides.count) : new Uint32Array(0);
      const pos = new Float32Array(n * 3);
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
      g.setAttribute("uv", new THREE.BufferAttribute(uv, 2));
      g.setIndex(new THREE.BufferAttribute(faces, 1));
      const hairy = spec.role === "hair" || spec.role === "beard" || spec.role === "eyebrows";
      const mat = new THREE.MeshStandardMaterial({
        color: new THREE.Color(worn.colour || "#ffffff"),
        map: worn.texture || null,
        roughness: hairy ? 0.9 : 0.72,
        metalness: 0,
        transparent: hairy,                        // hair and brows are cut-out textures
        alphaTest: hairy ? 0.35 : 0,
        side: hairy ? THREE.DoubleSide : THREE.FrontSide,
      });
      if (worn.colour && worn.texture) tintLikeTheBuild(mat, spec.median ?? 0.5);
      const mesh = new THREE.Mesh(g, mat);
      mesh.renderOrder = 1;
      this.scene.add(mesh);
      this.wearing.push({worn, mesh, idx, weight, off, pos, hides, scale: new Float32Array(3)});
    }
    this.dress();
    this.hideCovered();
  }

  /** Look at the whole person, or close in on what is being edited. */
  frame(what: "whole" | "face" | "body") {
    const h = this.height;
    this.looking = what;
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

  // --- turning it ---  // --- turning it ------------------------------------------------------------------------------------
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
    this.canvas.addEventListener("dblclick", e => this.lookAtPoint(e));
  }

  /** Double-click anywhere on the body to put that part in the middle and move in close; miss, and it
   *  goes back to the whole figure. The quickest way back to a head you have lost. */
  private lookAtPoint(e: MouseEvent) {
    if (!this.mesh) return;
    const r = this.canvas.getBoundingClientRect();
    const p = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1,
                                -((e.clientY - r.top) / r.height) * 2 + 1);
    const ray = new THREE.Raycaster();
    ray.setFromCamera(p, this.camera);
    const hit = ray.intersectObject(this.mesh, false)[0];
    if (!hit) { this.frame("whole"); return; }
    this.looking = "spot";
    this.wanted.target.copy(hit.point);
    this.wanted.dist = Math.max(0.3, this.height * 0.4);
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
    for (const w of this.wearing) { w.mesh.geometry.dispose(); (w.mesh.material as THREE.Material).dispose(); }
    cancelAnimationFrame(this.raf);
    this.mesh?.geometry.dispose();
    this.renderer.dispose();
  }
}
