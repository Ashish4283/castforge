// A Santa cap built for the head it is going on - the browser's half of costume.santa_cap.
//
// The library's cap is one size, thin-banded and worn tilted. This one takes the skull's own circle as
// its opening, so it cannot bulge through the head, and it flops the way you point it. The build makes
// the same shape from the same measurements (blender/build_character.py, anchor "Santa cap made for THIS
// head"), so what you shape here is what gets built.
//
// Everything here is in the viewer's space: y is up, and the head has already been morphed by the
// sliders, so the cap is re-made whenever the body changes - which is what keeps it fitting.

export interface CapWants {
  droop: number;        // 0 straight up, 1 right over
  towards: number;      // degrees round the head: 0 their left, 90 behind
  band: number;         // how much of it is fur
  bobble: number;       // 0 none, 1 ordinary, 1.5 enormous
  size: number;         // the whole cap, bigger or smaller
  cloth: string;        // the velvet
  fur: string;          // the roll and the bobble
}

export const CAP_DEFAULT: CapWants = {
  droop: 0.6, towards: 20, band: 0.3, bobble: 1, size: 1, cloth: "#c8102e", fur: "#f3efe8",
};

/** The head this cap has to fit: where the roll sits, how wide it is there, and where the crown is.
 *
 *  Measured on the body as it stands now (`pos`), over the vertices above `neckY` - so a wider head gets
 *  a wider cap without anybody having to say so. */
export function headAt(pos: Float32Array, skin: ArrayLike<number>, neckY: number) {
  let crown = -Infinity;
  const above: number[] = [];
  const seen = new Set<number>();
  for (let i = 0; i < skin.length; i++) {
    const v = skin[i];
    if (seen.has(v)) continue;
    seen.add(v);
    const y = pos[v * 3 + 1];
    if (y <= neckY) continue;
    above.push(v);
    if (y > crown) crown = y;
  }
  if (!above.length) return null;
  // A Santa cap's fur roll sits on the forehead and above the ears, about 8.5 cm below the crown on a
  // grown head. Measuring higher catches the ears and the opening comes out loose.
  const sit = crown - 0.085;
  const round = above.filter(v => Math.abs(pos[v * 3 + 1] - sit) < 0.02);
  const ring = round.length ? round : above;
  // The middle comes from the band's EXTENT, not from the average of its vertices. A head is not evenly
  // meshed - the face carries far more vertices than the back of the skull - so an average sits forward
  // of the real centre, and the far side then measures as twice the radius. (It did: 0.140 m for a head
  // of 0.07.) BOTH half-extents are kept: a head is about 17 cm across and 21.6 cm front to back, so a
  // cap sized from one circle between the two stands 3 cm clear of the temples (see costume.santa_cap).
  let lowX = Infinity, highX = -Infinity, lowZ = Infinity, highZ = -Infinity;
  for (const v of ring) {
    lowX = Math.min(lowX, pos[v * 3]); highX = Math.max(highX, pos[v * 3]);
    lowZ = Math.min(lowZ, pos[v * 3 + 2]); highZ = Math.max(highZ, pos[v * 3 + 2]);
  }
  const longR = (highZ - lowZ) / 2 + 0.006;          // front to back
  const acrossR = (highX - lowX) / 2 + 0.006;        // ear to ear
  return {cx: (lowX + highX) / 2, cz: (lowZ + highZ) / 2, sit,
          // the cone's length still comes from the average, so a cap is no longer than it ever was
          wide: (longR + acrossR) / 2, longR, squash: acrossR / longR, crown};
}

/** The cap as rings of points, how many of those rings are fur, and the tip (for the bobble).
 *
 *  Mirrors `costume.santa_cap`, where the shape is explained: a fur ROLL standing a little proud of the
 *  head, then a cone from exactly where the roll ends, tapering and flopping the way it is pointed. */
export function capRings(head: {cx: number; cz: number; sit: number; wide: number; longR?: number; squash?: number}, want: CapWants,
                         rings = 16, span = 18) {
  const height = head.wide * 3.0 * want.size;
  const band = Math.min(0.6, Math.max(0.08, want.band));
  // the fur's depth comes from the HEAD, not the cap's length: a bigger cap has a longer cone, not a
  // deeper band (see costume.santa_cap)
  const rollH = head.wide * 0.62 * (band / 0.3);
  const longR = head.longR ?? head.wide;              // front to back; `wide` is the average
  const squash = head.squash ?? 1;                    // across / front-back, 1 being a round head
  const rollR = longR * 1.12;
  const inRoll = Math.max(2, Math.round(rings * band));
  const leanX = Math.cos((want.towards * Math.PI) / 180);
  const leanZ = Math.sin((want.towards * Math.PI) / 180);
  const spine: [number, number, number][] = [];
  const widths: number[] = [];
  for (let i = 0; i < inRoll; i++) {
    const t = i / Math.max(1, inRoll - 1);
    spine.push([head.cx, head.sit + rollH * t, head.cz]);
    widths.push(rollR * (1 - 0.04 * t));
  }
  const left = rings - inRoll;
  for (let i = 0; i < left; i++) {
    const t = (i + 1) / left;
    const lean = want.droop * (height - rollH) * 1.3 * t * t;
    const rise = (height - rollH) * t * (1 - 0.35 * want.droop * t);
    spine.push([head.cx + leanX * lean, head.sit + rollH + rise, head.cz + leanZ * lean]);
    widths.push(longR * ((1 - t) ** 0.85 * 1.02 + 0.06));
  }
  const out: [number, number, number][][] = [];
  for (let i = 0; i < rings; i++) {
    const ahead = spine[Math.min(i + 1, rings - 1)];
    const behind = spine[Math.max(i - 1, 0)];
    const axis = [ahead[0] - behind[0], ahead[1] - behind[1], ahead[2] - behind[2]];
    const len = Math.hypot(axis[0], axis[1], axis[2]) || 1;
    const a = [axis[0] / len, axis[1] / len, axis[2] / len];
    let side = [-a[1], a[0], 0];
    if (!side[0] && !side[1] && !side[2]) side = [1, 0, 0];
    const slen = Math.hypot(side[0], side[1], side[2]) || 1;
    side = [side[0] / slen, side[1] / slen, side[2] / slen];
    const other = [a[1] * side[2] - a[2] * side[1], a[2] * side[0] - a[0] * side[2],
                   a[0] * side[1] - a[1] * side[0]];
    const ring: [number, number, number][] = [];
    for (let j = 0; j < span; j++) {
      const ang = (2 * Math.PI * j) / span;
      // x is across the face here as it is in the build, so that is the axis the squash applies to
      ring.push([spine[i][0] + widths[i] * (Math.cos(ang) * side[0] + Math.sin(ang) * other[0]) * squash,
                 spine[i][1] + widths[i] * (Math.cos(ang) * side[1] + Math.sin(ang) * other[1]),
                 spine[i][2] + widths[i] * (Math.cos(ang) * side[2] + Math.sin(ang) * other[2])]);
    }
    out.push(ring);
  }
  return {rings: out, fur: inRoll, tip: spine[rings - 1]};
}

/** A little sphere as rings, for the bobble. */
export function ballRings(centre: [number, number, number], radius: number, rows = 6, span = 10) {
  const out: [number, number, number][][] = [];
  for (let i = 1; i < rows; i++) {
    const phi = (Math.PI * i) / rows;
    const r = radius * Math.sin(phi);
    const y = centre[1] + radius * Math.cos(phi);
    out.push(Array.from({length: span}, (_x, j): [number, number, number] =>
      [centre[0] + r * Math.cos((2 * Math.PI * j) / span), y,
       centre[2] + r * Math.sin((2 * Math.PI * j) / span)]));
  }
  return out;
}

/** Turn stacks of rings into positions and triangles, and say which triangles are fur. */
export function capMesh(head: {cx: number; cz: number; sit: number; wide: number; longR?: number; squash?: number}, want: CapWants) {
  const {rings, fur, tip} = capRings(head, want);
  const balls = want.bobble > 0.05 ? ballRings(tip, head.wide * 0.42 * want.bobble) : [];
  const points: number[] = [];
  const cloth: number[] = [];
  const fluff: number[] = [];
  const add = (p: [number, number, number]) => { points.push(p[0], p[1], p[2]); return points.length / 3 - 1; };

  const tube = (shape: [number, number, number][][], isFur: (row: number) => boolean, lid: boolean) => {
    const rows = shape.map(ring => ring.map(add));
    const span = shape[0].length;
    for (let r = 0; r < rows.length - 1; r++) {
      const into = isFur(r) ? fluff : cloth;
      for (let i = 0; i < span; i++) {
        const j = (i + 1) % span;
        into.push(rows[r][i], rows[r][j], rows[r + 1][j]);
        into.push(rows[r][i], rows[r + 1][j], rows[r + 1][i]);
      }
    }
    if (lid) {
      const last = rows[rows.length - 1];
      const into = isFur(rows.length - 1) ? fluff : cloth;
      for (let i = 1; i + 1 < last.length; i++) into.push(last[0], last[i], last[i + 1]);
    }
  };

  tube(rings, r => r < fur, !balls.length);
  if (balls.length) tube(balls, () => true, true);
  return {points: new Float32Array(points), cloth: new Uint32Array(cloth), fur: new Uint32Array(fluff)};
}
