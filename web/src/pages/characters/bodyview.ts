// The designer's live body: the plain shape, morphed as the sliders move, with no build in the loop.
//
// A "kit" (blender/preview_kit.py) is the body mesh plus the vertices each morph target moves. Applying a
// slider is then a handful of adds over about 830 vertices, which is nothing - so the body changes under
// your hand instead of four minutes later.
//
// Turning it: drag anywhere to turn the body, or grab a ring - the green one round its feet spins it, the
// red one standing up beside it tips it. The wheel zooms. Nothing here changes the design; it only looks.
import * as THREE from "three";
import {adjacencyOf, facesInside, nearestVertex, openRings, shapePart, spreadFrom} from "./parts";

export interface Kit {
  version: number;
  vertices: number; triangles: number; height: number;
  positions: {at: number; count: number};
  indices: {at: number; count: number};
  floor?: number;
  shapes: Record<string, {at: number; count: number}>;
  regions?: Record<string, {at: number; count: number}>;   // body parts a costume covers (the hands)
  joints?: Record<string, [number, number, number]>;       // MakeHuman's joint markers, in this space
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
  regions?: {at: number; count: number};                   // one byte a vertex: which trim bands it is on
  band_bits?: Record<string, number>;
  rim?: {at: number; count: number};                       // a hat's opening, in loop order
}

/** A part of something worn (or of the body) that has been made bigger or smaller.
 *
 *  `at` is the point that was clicked, kept in the BUILD's space (z up, metres) so the build can find the
 *  same place on its own mesh - which is a different mesh, subdivided once more than this one, so a
 *  vertex number would mean nothing there. `radius` is how far the part reaches along the surface. */
export interface PartSpec {
  on: string;                        // the role it belongs to: "body", "hat", "top", "shoes"...
  at: [number, number, number];
  seed?: number;                     // the vertex it was centred on, for saving it against the PIECE
  radius: number;
  scale: number;
  move?: [number, number, number];   // metres, in the build's space (x across, y front-back, z up)
  turn?: [number, number, number];   // degrees about those same axes
}

/** How the view itself looks: the things a 3D tool is expected to let you change. */
export interface ViewLook {
  light: "studio" | "warm" | "cool" | "flat";
  background: "dark" | "grey" | "light";
  wireframe: boolean;
  turntable: boolean;
}

export const LIGHTS: Record<ViewLook["light"], {hemi: [number, number, number]; key: [number, number];
                                                 rim: [number, number]}> = {
  // [sky, ground, strength], [key colour, strength], [rim colour, strength]
  studio: {hemi: [0xffffff, 0x47506a, 2.1], key: [0xfff2e2, 2.4], rim: [0x9fc4ff, 1.5]},
  warm:   {hemi: [0xffe9cf, 0x4a3a2c, 1.7], key: [0xffd9a8, 3.0], rim: [0xff9b5c, 1.0]},
  cool:   {hemi: [0xdce9ff, 0x2a3346, 1.8], key: [0xd8e8ff, 2.2], rim: [0x6fa8ff, 1.9]},
  flat:   {hemi: [0xffffff, 0xdddddd, 3.4], key: [0xffffff, 0.7], rim: [0xffffff, 0.7]},
};

const BACKDROPS: Record<ViewLook["background"], number | null> = {
  dark: null, grey: 0x2b3240, light: 0xdfe3ea,
};

/** The costume, as the live view needs it: a colour for each piece, or nothing to leave the piece off. */
export interface CostumeLook {
  trim?: string | null; belt?: string | null; buckle?: string | null; gloves?: string | null;
  boots?: boolean | null; sleeves?: string | null;
}
export interface Worn { spec: WornSpec; bin: ArrayBuffer; colour?: string; texture?: THREE.Texture | null;
                        edits?: PieceEdit[] }

/** One edit a person made to a piece of clothing, kept against the PIECE rather than the character.
 *
 *  `seed` is a vertex number of the asset's own mesh, which means the same place whoever is wearing it -
 *  unlike a point in space, which moves with the body. See core/wardrobe.py. */
export interface PieceEdit {
  seed: number; radius: number; scale?: number;
  move?: [number, number, number]; turn?: [number, number, number];
}

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

/** Stand a piece off the surface it was taken from, the way the build's displace-and-solidify does.
 *
 *  Fur trim, a belt, a buckle and gloves are, in the build, copies of the garment's or the skin's own
 *  faces pushed out along their normals and given thickness. Here the same faces are drawn again, pushed
 *  out in the vertex shader - no new geometry, and it follows the body because it IS the body's vertices. */
function liftOffSurface(material: THREE.Material, metres: number) {
  // only for materials that are lit: `objectNormal` is declared by the normal chunk, which a
  // MeshBasicMaterial does not include. Those get a polygon offset instead.
  material.onBeforeCompile = shader => {
    shader.uniforms.cfLift = {value: metres};
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nuniform float cfLift;")
      .replace("#include <begin_vertex>",
               "#include <begin_vertex>\ntransformed += normalize( objectNormal ) * cfLift;");
  };
  material.needsUpdate = true;
}

/** Make a hat bigger without disturbing the part that sits on the head: the growth the build applies.
 *
 *  Mirrors `costume.grow_hat` (blender/costume.py, where it is explained and tested). Only what is ABOVE
 *  the opening changes: the opening does not move, and neither does anything below it - the fur roll of a
 *  Santa cap hangs below the ring the head goes through, and letting it grow flares it out like a
 *  lampshade. "Above" is measured along the opening's own normal, because these hats are worn tilted, so
 *  the world's up is not the hat's. `rim` is that opening in loop order; `pos` is changed in place. */
function growHat(pos: Float32Array, scale: number, rim: Uint32Array) {
  if (Math.abs(scale - 1) < 1e-6 || !pos.length || rim.length < 3) return;
  const c = [0, 0, 0];
  for (const v of rim) for (let k = 0; k < 3; k++) c[k] += pos[v * 3 + k] / rim.length;
  const n = [0, 0, 0];                                   // Newell: the plane of the opening itself
  for (let i = 0; i < rim.length; i++) {
    const a = rim[i] * 3, b = rim[(i + 1) % rim.length] * 3;
    n[0] += (pos[a + 1] - pos[b + 1]) * (pos[a + 2] + pos[b + 2]);
    n[1] += (pos[a + 2] - pos[b + 2]) * (pos[a] + pos[b]);
    n[2] += (pos[a] - pos[b]) * (pos[a + 1] + pos[b + 1]);
  }
  const len = Math.hypot(n[0], n[1], n[2]) || 1;
  for (let k = 0; k < 3; k++) n[k] /= len;
  const count = pos.length / 3;
  const middle = [0, 0, 0];
  for (let i = 0; i < count; i++) for (let k = 0; k < 3; k++) middle[k] += pos[i * 3 + k] / count;
  let away = 0;
  for (let k = 0; k < 3; k++) away += (middle[k] - c[k]) * n[k];
  if (away < 0) for (let k = 0; k < 3; k++) n[k] = -n[k];       // point it up out of the opening
  let top = 0;
  const up = new Float32Array(count);
  for (let i = 0; i < count; i++) {
    let h = 0;
    for (let k = 0; k < 3; k++) h += (pos[i * 3 + k] - c[k]) * n[k];
    up[i] = h;
    if (h > top) top = h;
  }
  if (top <= 0) return;
  for (let i = 0; i < count; i++) {
    const t = Math.max(0, Math.min(1, up[i] / top));
    const grow = 1 + (scale - 1) * (t * t * (3 - 2 * t));       // smooth: no crease at the opening
    for (let k = 0; k < 3; k++) pos[i * 3 + k] = c[k] + (pos[i * 3 + k] - c[k]) * grow;
  }
}

type Grab = null | "orbit" | "spin" | "tip" | "pan";

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
                    off: Float32Array; pos: Float32Array; hides: Uint32Array; scale: Float32Array;
                    rim: Uint32Array; adj: Uint32Array[] | null; faces: ArrayLike<number>}[] = [];
  private tris: Uint32Array | null = null;   // the body's triangles, which garments are pinned to
  private hands: Uint32Array = new Uint32Array(0);     // the skin a glove covers
  private joints: Record<string, [number, number, number]> = {};
  private costume: CostumeLook = {};
  private hatSize = 1;                                 // these assets come in one size, and it is small
  private parts: PartSpec[] = [];                      // parts made bigger or smaller, from the design
  private chosen: {spec: PartSpec; verts: Set<number>} | null = null;
  private glow: THREE.Mesh | null = null;              // what the chosen part looks like while it is chosen
  private hint: THREE.Mesh | null = null;              // what the slider under your hand actually moves
  private bodyAdj: Uint32Array[] | null = null;
  picking = false;                                     // a click picks a part instead of turning the body
  private look: ViewLook = {light: "studio", background: "dark", wireframe: false, turntable: false};
  private lamps: {hemi: THREE.HemisphereLight; key: THREE.DirectionalLight; rim: THREE.DirectionalLight};
  onPick: ((spec: PartSpec) => void) | null = null;
  floor = 0;
  private pieces: THREE.Mesh[] = [];                   // the costume drawn over the clothes
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
    this.renderer = new THREE.WebGLRenderer({canvas, antialias: true, alpha: true, preserveDrawingBuffer: true});
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.camera = new THREE.PerspectiveCamera(32, 1, 0.1, 100);
    const hemi = new THREE.HemisphereLight(0xffffff, 0x47506a, 2.1);
    const key = new THREE.DirectionalLight(0xfff2e2, 2.4); key.position.set(2.2, 3.4, 2.6);
    const rim = new THREE.DirectionalLight(0x9fc4ff, 1.5); rim.position.set(-2.6, 1.8, -2.2);
    this.lamps = {hemi, key, rim};
    this.scene.add(hemi, key, rim);
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
    this.hands = kit.regions?.hands?.count
      ? new Uint32Array(bin, kit.regions.hands.at, kit.regions.hands.count) : new Uint32Array(0);
    this.joints = kit.joints || {};
    this.floor = (kit as {floor?: number}).floor || 0;
    this.bodyAdj = null;
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
    if (this.parts.some(p_ => p_.on === "body")) {
      const skin = this.surface("body");
      if (skin) this.resizeParts("body", skin.pos, skin.adj, skin.indices);
    }
    const attr = this.mesh.geometry.getAttribute("position") as THREE.BufferAttribute;
    attr.needsUpdate = true;
    this.mesh.geometry.computeVertexNormals();
    this.dress();
    this.showChosen();
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
      // the piece's own cut first - it belongs to the garment and travels with it onto any body
      const cut = w.worn.edits || [];
      if (cut.length) {
        w.adj ||= adjacencyOf(w.faces, pos.length / 3);
        for (const edit of cut) {
          if (!(edit.seed >= 0 && edit.seed * 3 < pos.length)) continue;
          const move = edit.move || [0, 0, 0];
          const turn = edit.turn || [0, 0, 0];
          shapePart(pos, spreadFrom(pos, w.adj, edit.seed, edit.radius), w.adj, w.faces,
                    edit.scale ?? 1, [move[0], move[2], -move[1]], [turn[0], turn[2], -turn[1]]);
        }
      }
      if (w.worn.spec.role === "hat") growHat(pos, this.hatSize, w.rim);
      if (this.parts.some(p_ => p_.on === w.worn.spec.role)) {
        const faces = w.mesh.geometry.getIndex();
        if (faces) {
          const indices = faces.array as ArrayLike<number>;
          w.adj ||= adjacencyOf(indices, pos.length / 3);
          this.resizeParts(w.worn.spec.role, pos, w.adj, indices);
        }
      }
      const attr = w.mesh.geometry.getAttribute("position") as THREE.BufferAttribute;
      attr.needsUpdate = true;
      w.mesh.geometry.computeVertexNormals();
    }
  }

  /** How big the hat is: 1 is the asset as it comes, which for a Santa cap is a child's. */
  setHatSize(size: number) {
    this.hatSize = size > 0 ? size : 1;
    this.dress();
    this.buildCostume();
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
      try {
        this.wearOne(worn);
      } catch (e) {                      // one unreadable thing must not leave the character undressed
        console.warn("CastForge: could not put on", worn.spec.asset, e);
      }
    }
    this.dress();
    this.hideCovered();
    this.buildCostume();
    this.setLook({});                      // wireframe and the rest apply to whatever was just made
  }

  private wearOne(worn: Worn) {
    {
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
      // A hat's opening, in loop order: what holds it on, and what "above" is measured from. The export
      // marks it, but an export cached from an older version has no mark - so fall back to the mesh's own
      // widest open ring rather than silently refusing to grow the hat (which is what used to happen).
      let rim = spec.rim?.count ? new Uint32Array(bin, spec.rim.at, spec.rim.count) : new Uint32Array(0);
      if (!rim.length && spec.role === "hat") {
        const rings = openRings(faces);
        const widest = rings.sort((a, b) => b.length - a.length)[0];
        if (widest) rim = Uint32Array.from(widest);
      }
      this.wearing.push({worn, mesh, idx, weight, off, pos, hides, scale: new Float32Array(3), rim,
                         adj: null, faces});
    }
  }

  /** The costume over the clothes: fur trim, a belt and buckle, gloves, fur-topped boots.
   *
   *  The build makes these as geometry (blender/costume.py, after the rig). The live view cannot run that,
   *  but it does not have to: every one of those pieces is a REGION of a surface already here - a band
   *  round the garment's hem, cuffs and collar; a strip round the waist; the skin of the hands - so the
   *  same faces are drawn a second time in the piece's own colour, standing a little off the surface.
   *  The bands were measured along the surface when the garment was exported, so they are the same ones
   *  the build trims; the waist comes from MakeHuman's own joint markers, so it follows the sliders. */
  setCostume(look: CostumeLook) {
    this.costume = look || {};
    this.buildCostume();
  }

  private clearCostume() {
    for (const m of this.pieces) {
      this.scene.remove(m);
      m.geometry.dispose();
      (m.material as THREE.Material).dispose();
    }
    this.pieces = [];
  }

  /** Draw some of a surface again: `over` is the geometry whose vertices (and normals) are shared, so the
   *  piece moves with the body for free, and `faces` are the triangles kept. */
  private addPiece(over: THREE.BufferGeometry, faces: number[], colour: string,
                   lift: number, rough: number, metal = 0.0) {
    if (!faces.length) return;
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", over.getAttribute("position"));
    const normal = over.getAttribute("normal");
    if (normal) g.setAttribute("normal", normal);
    g.setIndex(new THREE.BufferAttribute(new Uint32Array(faces), 1));
    const mat = new THREE.MeshStandardMaterial({
      color: new THREE.Color(colour), roughness: rough, metalness: metal, side: THREE.DoubleSide});
    liftOffSurface(mat, lift);
    const mesh = new THREE.Mesh(g, mat);
    mesh.renderOrder = 2;
    this.scene.add(mesh);
    this.pieces.push(mesh);
  }

  private buildCostume() {
    this.clearCostume();
    const c = this.costume;
    if (!this.mesh) return;

    for (const w of this.wearing) {
      const {spec} = w.worn;
      const faces = w.mesh.geometry.getIndex();
      if (!faces || !spec.regions?.count) continue;
      const bits = new Uint8Array(w.worn.bin, spec.regions.at, spec.regions.count);
      const names = spec.band_bits || {hem: 1, collar: 2, cuff: 4, boot: 8};
      const want = (keys: string[]) => keys.reduce((n, k) => n | (names[k] || 0), 0);
      const pick = (mask: number) => {
        const out: number[] = [];
        for (let t = 0; t < faces.count; t += 3) {
          const a = faces.getX(t), b = faces.getX(t + 1), d = faces.getX(t + 2);
          if ((bits[a] & mask) && (bits[b] & mask) && (bits[d] & mask)) out.push(a, b, d);
        }
        return out;
      };
      const garment = spec.role === "top" || spec.role === "outfit" || spec.role === "dress";
      if (c.trim && garment) {
        const keys = c.sleeves === "long" ? ["hem", "collar", "cuff"] : ["hem", "collar"];
        this.addPiece(w.mesh.geometry, pick(want(keys)), c.trim, 0.014, 0.95);
      }
      if (c.trim && c.boots && spec.role === "shoes") {
        this.addPiece(w.mesh.geometry, pick(want(["boot"])), c.trim, 0.014, 0.95);
      }
      if ((c.belt || c.buckle) && garment) this.beltOn(w, !!c.belt, c.belt || "", c.buckle || "");
    }

    if (c.gloves && this.hands.length) {
      const hand = new Set<number>(Array.from(this.hands));
      const faces: number[] = [];
      for (let t = 0; this.tris && t < this.tris.length; t += 3) {
        const a = this.tris[t], b = this.tris[t + 1], d = this.tris[t + 2];
        if (hand.has(a) && hand.has(b) && hand.has(d)) faces.push(a, b, d);
      }
      this.addPiece(this.mesh.geometry, faces, c.gloves, 0.0025, 0.8);
    }
  }

  /** A belt round the waist of a garment, and the buckle at the front of it.
   *
   *  Not a band measured along the surface: a belt is a height, so it is cut from the live positions and
   *  moves up and down with the body. The waist is MakeHuman's spine-3 joint, and the shoulders say how
   *  wide the torso is, which keeps the belt off the arms hanging beside it. */
  private beltOn(w: {worn: Worn; mesh: THREE.Mesh; pos: Float32Array}, belt: boolean,
                 beltColour: string, buckleColour: string) {
    const waist = this.joints["joint-spine-3"];
    const shoulder = this.joints["joint-l-shoulder"];
    if (!waist) return;
    const y = waist[1], half = 0.042;
    const reach = (shoulder ? Math.abs(shoulder[0]) : 0.2) * 1.15;
    const faces = w.mesh.geometry.getIndex();
    if (!faces) return;
    const pos = w.pos;
    const band: number[] = [];
    const front: number[] = [];
    for (let t = 0; t < faces.count; t += 3) {
      const v = [faces.getX(t), faces.getX(t + 1), faces.getX(t + 2)];
      let cy = 0, cx = 0, cz = 0;
      for (const i of v) { cx += pos[i * 3] / 3; cy += pos[i * 3 + 1] / 3; cz += pos[i * 3 + 2] / 3; }
      if (Math.abs(cy - y) > half || Math.abs(cx) > reach) continue;
      band.push(v[0], v[1], v[2]);
      if (Math.abs(cx) < 0.055 && cz > 0) front.push(v[0], v[1], v[2]);     // the buckle: front centre
    }
    if (belt) this.addPiece(w.mesh.geometry, band, beltColour, 0.012, 0.35);
    if (buckleColour) this.addPiece(w.mesh.geometry, front, buckleColour, 0.024, 0.25, 1.0);
  }

  // --- parts you can pick and resize ------------------------------------------------------------------
  // A part is whatever lies within so many centimetres of where you clicked, measured along the surface
  // (parts.ts, mirroring costume.part_at). Resizing it grows it away from its own border, so it stays
  // joined on and nothing outside it moves - the rule the hat taught.

  /** Where a worn thing of this role lives, or the body itself. */
  private surface(role: string) {
    if (role === "body") {
      if (!this.work || !this.tris || !this.mesh) return null;
      this.bodyAdj ||= adjacencyOf(this.tris, this.work.length / 3);
      return {pos: this.work, adj: this.bodyAdj, indices: this.tris as ArrayLike<number>, mesh: this.mesh};
    }
    const w = this.wearing.find(x => x.worn.spec.role === role);
    if (!w) return null;
    const faces = w.mesh.geometry.getIndex();
    if (!faces) return null;
    const indices = faces.array as ArrayLike<number>;
    w.adj ||= adjacencyOf(indices, w.pos.length / 3);
    return {pos: w.pos, adj: w.adj, indices, mesh: w.mesh};
  }

  /** The build works in z-up metres off the floor; this view works in y-up with the feet at zero. */
  private toBuild(p: THREE.Vector3): [number, number, number] {
    return [p.x, -p.z, p.y + this.floor];
  }
  private fromBuild(at: [number, number, number]): [number, number, number] {
    return [at[0], at[2] - this.floor, -at[1]];
  }

  /** The parts the design asks for, each worked out again on the mesh as it stands now. */
  setParts(parts: PartSpec[]) {
    this.parts = parts || [];
    this.chosen = null;
    this.dress();
    this.buildCostume();
    this.showChosen();
  }

  /** Work out which vertices a part covers, on whatever it belongs to. */
  private vertsOf(spec: PartSpec): Set<number> {
    const face = this.surface(spec.on);
    if (!face) return new Set();
    const seed = nearestVertex(face.pos, this.fromBuild(spec.at));
    return seed < 0 ? new Set() : spreadFrom(face.pos, face.adj, seed, spec.radius);
  }

  /** Apply every shaped part to a surface that has just been rebuilt. */
  private resizeParts(role: string, pos: Float32Array, adj: Uint32Array[], indices: ArrayLike<number>) {
    for (const spec of this.parts) {
      if (spec.on !== role) continue;
      const move = spec.move || [0, 0, 0];
      const turn = spec.turn || [0, 0, 0];
      if (Math.abs(spec.scale - 1) < 1e-6 && !move.some(Boolean) && !turn.some(Boolean)) continue;
      const seed = nearestVertex(pos, this.fromBuild(spec.at));
      if (seed < 0) continue;
      // the design keeps metres and degrees in the BUILD's axes (z up); this view is y up
      shapePart(pos, spreadFrom(pos, adj, seed, spec.radius), adj, indices, spec.scale,
                [move[0], move[2], -move[1]], [turn[0], turn[2], -turn[1]]);
    }
  }

  /** Click on the body: which part did that land on? Hands the answer to whoever asked for it. */
  private pickAt(x: number, y: number, radius: number) {
    const ray = new THREE.Raycaster();
    const box = this.canvas.getBoundingClientRect();
    ray.setFromCamera(new THREE.Vector2(((x - box.left) / box.width) * 2 - 1,
                                        -((y - box.top) / box.height) * 2 + 1), this.camera);
    const targets = [...this.wearing.map(w => w.mesh), ...(this.mesh ? [this.mesh] : [])];
    const hit = ray.intersectObjects(targets, false)[0];
    if (!hit) return null;
    const role = hit.object === this.mesh ? "body"
      : this.wearing.find(w => w.mesh === hit.object)?.worn.spec.role || "body";
    // The point is what a body part needs (the body is this character's); the vertex number is what a
    // PIECE needs (the garment is the same mesh on everybody). Keep both, and let the saver choose.
    const face = this.surface(role);
    const seed = face ? nearestVertex(face.pos, [hit.point.x, hit.point.y, hit.point.z]) : -1;
    const spec: PartSpec = {on: role, at: this.toBuild(hit.point), radius, scale: 1,
                            ...(seed >= 0 ? {seed} : {})};
    this.choose(spec);
    return spec;
  }

  /** Show a part as chosen, and say how much of the thing it covers - 0 to 1.
   *
   *  The fraction matters: picking nearly a whole hat and doubling it is not a part at all, it is a
   *  different hat, and it will look like one. Saying so is kinder than letting it happen. */
  choose(spec: PartSpec | null): number {
    if (this.glow) {
      this.scene.remove(this.glow);
      this.glow.geometry.dispose();
      (this.glow.material as THREE.Material).dispose();
      this.glow = null;
    }
    this.chosen = spec ? {spec, verts: this.vertsOf(spec)} : null;
    this.showChosen();
    if (!this.chosen) return 0;
    const face = this.surface(this.chosen.spec.on);
    const whole = face ? face.pos.length / 3 : 0;
    return whole ? this.chosen.verts.size / whole : 0;
  }

  private showChosen() {
    if (this.glow) {
      this.scene.remove(this.glow);
      this.glow.geometry.dispose();
      (this.glow.material as THREE.Material).dispose();
      this.glow = null;
    }
    if (!this.chosen || !this.chosen.verts.size) return;
    const face = this.surface(this.chosen.spec.on);
    if (!face) return;
    const faces = facesInside(face.indices, this.chosen.verts);
    if (!faces.length) return;
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", face.mesh.geometry.getAttribute("position"));
    const normal = face.mesh.geometry.getAttribute("normal");
    if (normal) g.setAttribute("normal", normal);
    g.setIndex(new THREE.BufferAttribute(new Uint32Array(faces), 1));
    // a plain material has no normals to push along (`objectNormal` only exists where there is lighting),
    // so the highlight is lifted off the surface with a depth offset instead of in the shader
    const mat = new THREE.MeshBasicMaterial({color: 0x7cc7ff, transparent: true, opacity: 0.45,
                                             depthWrite: false, side: THREE.DoubleSide,
                                             polygonOffset: true, polygonOffsetFactor: -4,
                                             polygonOffsetUnits: -4});
    this.glow = new THREE.Mesh(g, mat);
    this.glow.renderOrder = 3;
    this.scene.add(this.glow);
  }

  // --- the view itself: light, backdrop, wireframe, turntable, a picture -------------------------------

  /** Change how the view looks. Nothing here touches the design; it only changes what you can see. */
  setLook(look: Partial<ViewLook>) {
    this.look = {...this.look, ...look};
    const lamp = LIGHTS[this.look.light] || LIGHTS.studio;
    this.lamps.hemi.color.setHex(lamp.hemi[0]);
    this.lamps.hemi.groundColor.setHex(lamp.hemi[1]);
    this.lamps.hemi.intensity = lamp.hemi[2];
    this.lamps.key.color.setHex(lamp.key[0]);
    this.lamps.key.intensity = lamp.key[1];
    this.lamps.rim.color.setHex(lamp.rim[0]);
    this.lamps.rim.intensity = lamp.rim[1];
    const back = BACKDROPS[this.look.background];
    this.scene.background = back === null ? null : new THREE.Color(back);
    for (const m of this.everyMaterial()) {
      if ((m as THREE.MeshStandardMaterial).wireframe !== undefined) {
        (m as THREE.MeshStandardMaterial).wireframe = this.look.wireframe;
      }
    }
  }

  private everyMaterial(): THREE.Material[] {
    const out: THREE.Material[] = [];
    for (const o of [this.mesh, ...this.wearing.map(w => w.mesh), ...this.pieces]) {
      if (o) out.push(...(Array.isArray(o.material) ? o.material : [o.material]));
    }
    return out;
  }

  /** A picture of the view as it stands, for keeping or sharing. */
  snapshot(): string {
    this.renderer.render(this.scene, this.camera);       // draw now, so the buffer is not an old frame
    return this.renderer.domElement.toDataURL("image/png");
  }

  /** Light up what a slider moves, while the hand is on it.
   *
   *  The kit already says which vertices each morph target touches - that is how the body is morphed at
   *  all - so showing it costs nothing, and it answers the question every slider raises: what IS this? */
  showTargets(names: string[] | null) {
    if (this.hint) {
      this.scene.remove(this.hint);
      this.hint.geometry.dispose();
      (this.hint.material as THREE.Material).dispose();
      this.hint = null;
    }
    if (!names || !names.length || !this.mesh || !this.tris) return;
    const moved = new Set<number>();
    for (const name of names) {
      const shape = this.shapes.get(name);
      if (shape) for (const v of shape.idx) moved.add(v);
    }
    if (!moved.size) return;
    const faces: number[] = [];
    for (let t = 0; t < this.tris.length; t += 3) {        // any triangle with a corner that moves
      const a = this.tris[t], b = this.tris[t + 1], c = this.tris[t + 2];
      if (moved.has(a) || moved.has(b) || moved.has(c)) faces.push(a, b, c);
    }
    if (!faces.length) return;
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", this.mesh.geometry.getAttribute("position"));
    const normal = this.mesh.geometry.getAttribute("normal");
    if (normal) g.setAttribute("normal", normal);
    g.setIndex(new THREE.BufferAttribute(new Uint32Array(faces), 1));
    this.hint = new THREE.Mesh(g, new THREE.MeshBasicMaterial({
      color: 0xffd36e, transparent: true, opacity: 0.4, depthWrite: false, side: THREE.DoubleSide,
      polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4}));
    this.hint.renderOrder = 4;
    this.scene.add(this.hint);
  }

  /** Show one thing on its own - a hat, a coat - with the body and everything else out of the way.
   *
   *  Cutting a piece is easier when nothing is in front of it, and it is the garment you are working on,
   *  not the character. `null` puts everyone back. */
  setSolo(role: string | null) {
    const show = (o: THREE.Mesh | null, on: boolean) => { if (o) o.visible = on; };
    show(this.mesh, !role || role === "body");
    for (const w of this.wearing) show(w.mesh, !role || w.worn.spec.role === role);
    for (const piece of this.pieces) piece.visible = !role;      // the costume belongs to the character
    this.rings.visible = !role && this.rings.visible;
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
      if (this.picking) {                         // choosing a part to resize: a click picks, not turns
        const got = this.pickAt(e.clientX, e.clientY, 0.08);
        if (got && this.onPick) this.onPick(got);
        return;
      }
      this.grab = e.button === 2 || e.button === 1 || e.shiftKey ? "pan" : this.pick(e);
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
      if (this.grab === "pan") {                                      // slide the view sideways and up
        const far = this.dist * 0.0016;
        const right = new THREE.Vector3().setFromMatrixColumn(this.camera.matrix, 0);
        const up = new THREE.Vector3().setFromMatrixColumn(this.camera.matrix, 1);
        this.wanted.target.addScaledVector(right, -dx * far).addScaledVector(up, dy * far);
        this.looking = "spot";
        return;
      }
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
      const was = this.wanted.dist;
      this.wanted.dist = Math.max(0.25, Math.min(6, was * (1 + Math.sign(e.deltaY) * 0.12)));
      // zoom towards what is under the pointer, not towards the middle of the screen: closing in on an
      // ear should keep the ear where it is, which is what every 3D tool does and what hands expect
      const towards = this.under(e.clientX, e.clientY);
      if (towards && this.wanted.dist < was) {
        this.wanted.target.lerp(towards, Math.min(0.5, 1 - this.wanted.dist / was));
        this.looking = "spot";
      }
    }, {passive: false});
    this.canvas.addEventListener("dblclick", e => this.lookAtPoint(e));
    this.canvas.addEventListener("contextmenu", e => e.preventDefault());   // right-drag pans instead
  }

  /** Whatever the pointer is over, in the scene - or nothing, if it is over the backdrop. */
  private under(x: number, y: number): THREE.Vector3 | null {
    const r = this.canvas.getBoundingClientRect();
    const ray = new THREE.Raycaster();
    ray.setFromCamera(new THREE.Vector2(((x - r.left) / r.width) * 2 - 1, -((y - r.top) / r.height) * 2 + 1),
                      this.camera);
    const hit = ray.intersectObjects([...this.wearing.map(w => w.mesh), ...(this.mesh ? [this.mesh] : [])],
                                     false)[0];
    return hit ? hit.point.clone() : null;
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
    if (this.look.turntable && !this.grab) this.yaw += 0.004;        // a slow turn, to look it over
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
