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

/** The vertices that hold a part on: the ones touching something outside it, or - when the part IS the
 *  whole object - the open boundary it hangs from, like the ring of a hat that the head goes through. */
function holdingOn(part: Set<number>, adj: Uint32Array[], indices: ArrayLike<number>): number[] {
  const border: number[] = [];
  for (const v of part) {
    for (const w of adj[v] || []) if (!part.has(w)) { border.push(v); break; }
  }
  if (border.length && border.length !== part.size) return border;
  const used = new Map<string, number>();                 // an edge used by one face is an open edge
  for (let t = 0; t + 2 < indices.length; t += 3) {
    for (const [a, b] of [[indices[t], indices[t + 1]], [indices[t + 1], indices[t + 2]],
                          [indices[t + 2], indices[t]]]) {
      const key = a < b ? `${a}:${b}` : `${b}:${a}`;
      used.set(key, (used.get(key) || 0) + 1);
    }
  }
  const open = new Set<number>();
  for (const [key, n] of used) {
    if (n !== 1) continue;
    const [a, b] = key.split(":").map(Number);
    if (part.has(a)) open.add(a);
    if (part.has(b)) open.add(b);
  }
  return [...open];
}

/** Resize, slide and turn `part`, leaving it joined to the rest. Mirrors `costume.shape_part`.
 *
 *  All three happen about the centre of what holds the part on, and all three fade to nothing there, so
 *  the seam never opens and nothing outside the part moves. `move` is metres in this view's own space
 *  (y up), `turn` is degrees about x, y and z. */
export function shapePart(pos: Float32Array, part: Set<number>, adj: Uint32Array[],
                          indices: ArrayLike<number>,
                          scale = 1, move: [number, number, number] = [0, 0, 0],
                          turn: [number, number, number] = [0, 0, 0]) {
  const still = Math.abs(scale - 1) < 1e-6 && !move.some(Boolean) && !turn.some(Boolean);
  if (still || !part.size) return;
  const border = holdingOn(part, adj, indices);
  if (!border.length || border.length === part.size) return;
  const c = [0, 0, 0];
  for (const v of border) for (let k = 0; k < 3; k++) c[k] += pos[v * 3 + k] / border.length;
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
    const ease = t * t * (3 - 2 * t);                     // smooth: no crease at the seam
    const grow = 1 + (scale - 1) * ease;
    let x = c[0] + (pos[v * 3] - c[0]) * grow;
    let y = c[1] + (pos[v * 3 + 1] - c[1]) * grow;
    let z = c[2] + (pos[v * 3 + 2] - c[2]) * grow;
    if (turn.some(Boolean)) {
      const [rx, ry, rz] = turn.map(d => (d * ease * Math.PI) / 180);
      let dx = x - c[0], dy = y - c[1], dz = z - c[2];
      [dy, dz] = [dy * Math.cos(rx) - dz * Math.sin(rx), dy * Math.sin(rx) + dz * Math.cos(rx)];
      [dz, dx] = [dz * Math.cos(ry) - dx * Math.sin(ry), dz * Math.sin(ry) + dx * Math.cos(ry)];
      [dx, dy] = [dx * Math.cos(rz) - dy * Math.sin(rz), dx * Math.sin(rz) + dy * Math.cos(rz)];
      x = c[0] + dx; y = c[1] + dy; z = c[2] + dz;
    }
    pos[v * 3] = x + move[0] * ease;
    pos[v * 3 + 1] = y + move[1] * ease;
    pos[v * 3 + 2] = z + move[2] * ease;
  }
}

/** Resizing alone, kept for callers that only want that. */
export function growPart(pos: Float32Array, part: Set<number>, scale: number, adj: Uint32Array[],
                         indices: ArrayLike<number>) {
  shapePart(pos, part, adj, indices, scale);
}


/** The open boundary rings of a mesh: the edges used by a single triangle, chained into loops.
 *
 *  The export marks a hat's opening, but the viewer must not DEPEND on that: a cached export from an
 *  older version has no opening in it, and then a hat silently refuses to grow - which is exactly what
 *  happened. With this, the worst case is picking a slightly different ring, not doing nothing at all. */
export function openRings(indices: ArrayLike<number>): number[][] {
  const used = new Map<string, number>();
  for (let t = 0; t + 2 < indices.length; t += 3) {
    for (const [a, b] of [[indices[t], indices[t + 1]], [indices[t + 1], indices[t + 2]],
                          [indices[t + 2], indices[t]]]) {
      const key = a < b ? `${a}:${b}` : `${b}:${a}`;
      used.set(key, (used.get(key) || 0) + 1);
    }
  }
  const next = new Map<number, number[]>();
  for (const [key, n] of used) {
    if (n !== 1) continue;
    const [a, b] = key.split(":").map(Number);
    (next.get(a) || next.set(a, []).get(a)!).push(b);
    (next.get(b) || next.set(b, []).get(b)!).push(a);
  }
  const seen = new Set<number>();
  const rings: number[][] = [];
  for (const start of [...next.keys()].sort((x, y) => x - y)) {
    if (seen.has(start)) continue;
    const ring = [start];
    seen.add(start);
    let prev = -1, here = start;
    for (;;) {
      const step = (next.get(here) || []).find(v => v !== prev && !seen.has(v));
      if (step === undefined) break;
      ring.push(step);
      seen.add(step);
      prev = here;
      here = step;
    }
    if (ring.length >= 3) rings.push(ring);
  }
  return rings;
}
