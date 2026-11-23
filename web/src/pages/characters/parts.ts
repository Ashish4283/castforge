// Picking a part of a mesh and resizing it, in the browser: the other half of blender/costume.py's
// part_at / grow_part, which is where the rules are explained and tested.
//
// A part is not something the asset names. It is whatever lies within so many centimetres of where you
// clicked, measured ALONG the surface - a cuff is a centimetre from the wrist underneath it but a long
// way round the cloth, so a click on the cuff must not leak onto the hand. Resizing one has to leave it
// attached: everything grows away from the centre of the part's border, fully deep inside it and not at
// all at the border, so the seam never opens and nothing outside the part moves.

/** Who touches whom: for every vertex, the vertices sharing a triangle edge with it. Built once a mesh. */
export function adjacencyOf(indices: ArrayLike<number>, count: number): Uint32Array[] {
  const adj: number[][] = new Array(count);
  const join = (a: number, b: number) => {
    (adj[a] ||= []).push(b);
    (adj[b] ||= []).push(a);
  };
  for (let t = 0; t + 2 < indices.length; t += 3) {
    join(indices[t], indices[t + 1]);
    join(indices[t + 1], indices[t + 2]);
    join(indices[t + 2], indices[t]);
  }
  return adj.map(list => Uint32Array.from(list ? new Set(list) : []));
}

/** A tiny binary heap of (distance, vertex); a part is a few thousand vertices, so this is plenty. */
class Heap {
  private d: number[] = [];
  private v: number[] = [];
  get size() { return this.v.length; }
  push(dist: number, vert: number) {
    this.d.push(dist); this.v.push(vert);
    let i = this.v.length - 1;
    while (i > 0) {
      const p = (i - 1) >> 1;
      if (this.d[p] <= this.d[i]) break;
      this.swap(i, p); i = p;
    }
  }
  pop(): [number, number] {
    const top: [number, number] = [this.d[0], this.v[0]];
    const d = this.d.pop()!, v = this.v.pop()!;
    if (this.v.length) {
      this.d[0] = d; this.v[0] = v;
      let i = 0;
      for (;;) {
        const l = i * 2 + 1, r = l + 1;
        let small = i;
        if (l < this.v.length && this.d[l] < this.d[small]) small = l;
        if (r < this.v.length && this.d[r] < this.d[small]) small = r;
        if (small === i) break;
        this.swap(i, small); i = small;
      }
    }
    return top;
  }
  private swap(a: number, b: number) {
    [this.d[a], this.d[b]] = [this.d[b], this.d[a]];
    [this.v[a], this.v[b]] = [this.v[b], this.v[a]];
  }
}

const gap = (pos: Float32Array, a: number, b: number) =>
  Math.hypot(pos[a * 3] - pos[b * 3], pos[a * 3 + 1] - pos[b * 3 + 1], pos[a * 3 + 2] - pos[b * 3 + 2]);

/** Everything within `radius` metres of vertex `seed`, walking along the surface. */
export function spreadFrom(pos: Float32Array, adj: Uint32Array[], seed: number, radius: number): Set<number> {
  const seen = new Map<number, number>([[seed, 0]]);
  const heap = new Heap();
  heap.push(0, seed);
  while (heap.size) {
    const [d, v] = heap.pop();
    if (d > (seen.get(v) ?? Infinity)) continue;
    for (const w of adj[v] || []) {
      const nd = d + gap(pos, v, w);
      if (nd <= radius && nd < (seen.get(w) ?? Infinity)) { seen.set(w, nd); heap.push(nd, w); }
    }
  }
  return new Set(seen.keys());
}

/** The vertex nearest a point in space - where a click lands. */
export function nearestVertex(pos: Float32Array, point: [number, number, number], among?: Set<number>): number {
  let best = -1, far = Infinity;
  const look = among ? Array.from(among) : null;
  const n = look ? look.length : pos.length / 3;
  for (let k = 0; k < n; k++) {
    const i = look ? look[k] : k;
    const d = (pos[i * 3] - point[0]) ** 2 + (pos[i * 3 + 1] - point[1]) ** 2 + (pos[i * 3 + 2] - point[2]) ** 2;
    if (d < far) { far = d; best = i; }
  }
  return best;
}

/** The triangles whose three corners are all in `part` - what to draw when it is highlighted. */
export function facesInside(indices: ArrayLike<number>, part: Set<number>): number[] {
  const out: number[] = [];
  for (let t = 0; t + 2 < indices.length; t += 3) {
    const a = indices[t], b = indices[t + 1], c = indices[t + 2];
    if (part.has(a) && part.has(b) && part.has(c)) out.push(a, b, c);
  }
  return out;
}

/** Resize `part` in place, leaving it joined to the rest. Mirrors `costume.grow_part`. */
export function growPart(pos: Float32Array, part: Set<number>, scale: number, adj: Uint32Array[]) {
  if (Math.abs(scale - 1) < 1e-6 || !part.size) return;
  const border: number[] = [];
  for (const v of part) {
    for (const w of adj[v] || []) if (!part.has(w)) { border.push(v); break; }
  }
  if (!border.length || border.length === part.size) return;
  const c = [0, 0, 0];
  for (const v of border) for (let k = 0; k < 3; k++) c[k] += pos[v * 3 + k] / border.length;
  // how deep inside the part each vertex lies, walking in from the border and never leaving the part
  const deep = new Map<number, number>();
  const heap = new Heap();
  for (const v of border) { deep.set(v, 0); heap.push(0, v); }
  let far = 0;
  while (heap.size) {
    const [d, v] = heap.pop();
    if (d > (deep.get(v) ?? Infinity)) continue;
    if (d > far) far = d;
    for (const w of adj[v] || []) {
      if (!part.has(w)) continue;
      const nd = d + gap(pos, v, w);
      if (nd < (deep.get(w) ?? Infinity)) { deep.set(w, nd); heap.push(nd, w); }
    }
  }
  if (!far) return;
  for (const v of part) {
    const t = Math.min(1, (deep.get(v) ?? far) / far);
    const grow = 1 + (scale - 1) * (t * t * (3 - 2 * t));       // smooth: no crease at the seam
    for (let k = 0; k < 3; k++) pos[v * 3 + k] = c[k] + (pos[v * 3 + k] - c[k]) * grow;
  }
}
