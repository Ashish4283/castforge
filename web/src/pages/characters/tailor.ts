// Socks, footwear, a tie, a scarf, a watch and a band, cut for the body wearing them - the browser's half
// of blender/tailor.py, where all of the arithmetic is explained and tested.
//
// This is a literal port, and it can be literal because no pattern over there names a global axis: up is
// the way from this ankle to this knee, forward is the way the foot points, across is what is left. The
// build has z up and this view has y up, and neither function cares. (The Santa cap needed two different
// implementations for exactly the want of that, and got the axes wrong twice.)
//
// Why a port at all rather than asking the server: these are re-cut every time the body changes, and the
// body changes on every drag of a slider. A round trip per frame is not a flick of a second.

export type Point = [number, number, number];
export interface Piece { name: string; stuff: string; rings: Point[][]; shut: boolean; lid: boolean; }
export type Joints = Record<string, Point>;

export const SPAN = 14;
export const SQUARE = 4;
export const SOCK_HEIGHTS: Record<string, number> = {ankle: 0.12, crew: 0.42, knee: 0.95};
// what a sock is drawn to under a trouser: an ankle sock ends BELOW the top of a shoe and so fills
// nothing, leaving bare skin between the shoe and the trouser (see blender/tailor.py)
export const COVERED = 0.26;
export const SHOE_STYLES = ["none", "shoe", "boot", "sneaker", "sandal", "heel"];
export const SIDES: Record<string, string[]> = {left: ["l"], right: ["r"], both: ["l", "r"]};
// whole-body outfits that put cloth down the leg, so a sock under them is not seen
export const LEGGED = ["suit", "formal", "work", "robe"];

const sub = (a: Point, b: Point): Point => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const add = (a: Point, b: Point): Point => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const mul = (a: Point, k: number): Point => [a[0] * k, a[1] * k, a[2] * k];
const long = (a: Point) => Math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2]);
const dot = (a: Point, b: Point) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a: Point, b: Point): Point =>
  [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const mix = (a: Point, b: Point, t: number): Point =>
  [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
const ZERO: Point = [0, 0, 0];
function unit(a: Point): Point {
  const n = long(a);
  return n > 1e-9 ? [a[0] / n, a[1] / n, a[2] / n] : ZERO;
}
const same = (a: Point, b: Point) => a[0] === b[0] && a[1] === b[1] && a[2] === b[2];

/** `point` brought onto the plane through `plane`, perpendicular to `up` - how a sole is laid flat. */
const flatten = (point: Point, plane: Point, up: Point): Point =>
  sub(point, mul(up, dot(sub(point, plane), up)));

function frame(along: Point, hint: Point): [Point, Point] {
  const a = unit(along);
  if (same(a, ZERO)) return [[1, 0, 0], [0, 1, 0]];
  let side = cross(hint, a);
  if (long(side) < 1e-6) side = cross([a[1], a[2], a[0]], a);
  side = unit(side);
  return [side, cross(a, side)];
}

/** Rings round a path, each held across the way the path is going. The only shape in the file. */
export function sweep(path: Point[], radii: number[], hint: Point | Point[] | null = null,
                      span = SPAN, squash: number[] | null = null): Point[][] {
  if (path.length < 2) return [];
  const many = Array.isArray(hint) && Array.isArray(hint[0]);
  const hints = (many ? hint : [hint]) as (Point | null)[];
  const out: Point[][] = [];
  for (let i = 0; i < path.length; i++) {
    const ahead = path[Math.min(i + 1, path.length - 1)];
    const behind = path[Math.max(i - 1, 0)];
    let here = hints[Math.min(i, hints.length - 1)];
    if (!here) {
      const step = sub(ahead, behind);
      here = [step[1], step[2], step[0]];
    }
    const [side, other] = frame(sub(ahead, behind), here);
    const rx = radii[Math.min(i, radii.length - 1)];
    const ry = rx * (squash ? squash[Math.min(i, squash.length - 1)] : 1);
    const ring: Point[] = [];
    for (let j = 0; j < span; j++) {
      const ang = (2 * Math.PI * j) / span;
      ring.push(add(path[i], add(mul(side, rx * Math.cos(ang)), mul(other, ry * Math.sin(ang)))));
    }
    out.push(ring);
  }
  return out;
}

const piece = (name: string, stuff: string, rings: Point[][], shut = false, lid = false): Piece =>
  ({name, stuff, rings, shut, lid});

// --- measuring the body ---------------------------------------------------------------------------------

function leg(joints: Joints, side: string) {
  const want = ["ankle", "foot-1", "foot-2", "knee"].map(k => joints[`joint-${side}-${k}`]);
  if (want.some(v => !v)) return null;
  const [ankle, instep, toe, knee] = want;
  const shin = long(sub(knee, ankle));
  if (shin < 1e-4) return null;
  const up = unit(sub(knee, ankle));
  const floor = joints["joint-ground"], pelvis = joints["joint-pelvis"];
  let stand = floor && pelvis ? unit(sub(pelvis, floor)) : up;
  if (same(stand, ZERO)) stand = up;
  return {ankle, instep, toe, knee, shin, up, stand, floor: floor || instep,
          forward: unit(sub(toe, ankle))};
}

function arm(joints: Joints, side: string) {
  const wrist = joints[`joint-${side}-hand`], elbow = joints[`joint-${side}-elbow`];
  if (!wrist || !elbow) return null;
  const fore = long(sub(elbow, wrist));
  if (fore < 1e-4) return null;
  const other = joints[side === "l" ? "joint-r-hand" : "joint-l-hand"];
  return {wrist, elbow, fore, along: unit(sub(elbow, wrist)),
          out: other ? unit(sub(wrist, other)) : unit(sub(wrist, elbow))};
}

function trunk(joints: Joints) {
  const neck = joints["joint-neck"], pelvis = joints["joint-pelvis"];
  if (!neck || !pelvis) return null;
  const tall = long(sub(neck, pelvis));
  if (tall < 1e-4) return null;
  const up = unit(sub(neck, pelvis));
  let ahead: Point = ZERO;
  const foot = joints["joint-l-foot-2"], ankle = joints["joint-l-ankle"];
  if (foot && ankle) {
    const level = sub(foot, ankle);
    ahead = unit(sub(level, mul(up, dot(level, up))));
  }
  const ls = joints["joint-l-shoulder"] || neck, rs = joints["joint-r-shoulder"] || neck;
  return {neck, pelvis, tall, up, ahead, wide: long(sub(ls, rs)) || tall * 0.45};
}

export type Sizes = Record<string, number>;

/** How far the body stands out around `centre`, measured across `axis`. `reach` keeps the far leg out. */
function girth(co: Float32Array, centre: Point, axis: Point, reach: number, near: number): number | null {
  let total = 0, n = 0;
  for (let i = 0; i + 2 < co.length; i += 3) {
    const away: Point = [co[i] - centre[0], co[i + 1] - centre[1], co[i + 2] - centre[2]];
    const along = dot(away, axis);
    if (Math.abs(along) > near) continue;
    const r = long(sub(away, mul(axis, along)));
    if (r > reach) continue;
    total += r; n++;
  }
  return n >= 8 ? total / n : null;
}

/** How far the body reaches either side of `centre` along `across` - mirrors `tailor.span`.
 *
 *  `girth` gives a mean radius, right for a leg and wrong for a foot: a foot is half as deep as it is
 *  wide, and a shoe cut to the mean of the two is narrower than the foot it is on. */
function span(co: Float32Array, centre: Point, axis: Point, across: Point,
              reach: number, near: number): number | null {
  let most = 0, n = 0;
  for (let i = 0; i + 2 < co.length; i += 3) {
    const away: Point = [co[i] - centre[0], co[i + 1] - centre[1], co[i + 2] - centre[2]];
    const along = dot(away, axis);
    if (Math.abs(along) > near) continue;
    if (long(sub(away, mul(axis, along))) > reach) continue;
    n++;
    most = Math.max(most, Math.abs(dot(away, across)));
  }
  return n >= 8 && most > 1e-4 ? most : null;
}

/** {place: radius} where the body can actually be measured - mirrors `tailor.measure`.
 *
 *  A proportion of a bone fits an ordinary leg. It does not fit a heavy one, and a sock wider than the
 *  trouser over it shows through the trouser. The mesh is right here, so measure it. */
export function measure(co: Float32Array | null, joints: Joints): Sizes {
  const out: Sizes = {};
  if (!co || !co.length) return out;
  for (const side of ["l", "r"]) {
    const low = leg(joints, side);
    if (low) {
      const {shin, up} = low;
      // thin at the ankle (finely meshed, and a wide slice there reaches the heel), wide at the calf
      // (coarse, and a thin slice falls between its rings) - see `tailor.measure`
      const places: [string, Point, number][] = [["ankle", add(low.ankle, mul(up, shin * 0.07)), 0.045],
                                                 ["calf", add(low.ankle, mul(up, shin * 0.40)), 0.12]];
      for (const [place, at, thick] of places) {
        // a wide slice: the leg mesh is coarse and a thin one falls between its rings (see
        // tailor.measure); a short reach is what keeps the far leg out of the answer
        const r = girth(co, at, up, shin * 0.25, shin * thick);
        if (r) out[`${place}_${side}`] = r;
      }
    }
    if (low) {
      // ...and the foot, which is not round: how wide and how deep it actually is, across its own length
      const {shin, stand} = low;
      const fwd = unit(sub(low.toe, low.instep));
      let level = unit(sub(fwd, mul(stand, dot(fwd, stand))));
      if (same(level, ZERO)) level = fwd;
      const sideways = unit(cross(stand, level));
      const at = mix(low.instep, low.toe, 0.25);
      const w = span(co, at, level, sideways, shin * 0.30, shin * 0.10);
      const t = span(co, at, level, stand, shin * 0.30, shin * 0.10);
      if (w) out[`foot_wide_${side}`] = w;
      if (t) out[`foot_tall_${side}`] = t;
    }
    const up2 = arm(joints, side);
    if (up2) {
      const r = girth(co, add(up2.wrist, mul(up2.along, up2.fore * 0.12)), up2.along,
                      up2.fore * 0.30, up2.fore * 0.12);
      if (r) out[`wrist_${side}`] = r;
    }
  }
  return out;
}

// --- the patterns ---------------------------------------------------------------------------------------

export function sock(joints: Joints, side: string, height = "crew", girth = 1, overFoot = true,
                     sizes: Sizes = {}): Piece[] {
  const low = leg(joints, side);
  if (!low) return [];
  const {shin, up, stand, floor} = low;
  const rise = (height === "covered" ? COVERED : SOCK_HEIGHTS[height] ?? SOCK_HEIGHTS.crew) * shin;
  // measured where it could be measured, a proportion of this leg's own shin where it could not
  const rAnkle = ((sizes[`ankle_${side}`] ?? shin * 0.092) + 0.0015) * girth;
  const rCalf = ((sizes[`calf_${side}`] ?? shin * 0.142) + 0.002) * girth;
  const grown = Math.min(1, rise / (shin * 0.55));
  let rTop = rAnkle + (rCalf - rAnkle) * grown;
  if (rise > shin * 0.5) rTop *= Math.max(0.76, 1 - (rise / shin - 0.5) * 0.5);
  const path: Point[] = [], radii: number[] = [], squash: number[] = [], hints: Point[] = [];
  if (overFoot) {
    const ankleFlat = flatten(low.ankle, floor, stand);
    const instepFlat = flatten(low.instep, floor, stand);
    const run: [Point, number, number][] = [
      [flatten(mix(low.toe, low.instep, -0.10), floor, stand), shin * 0.062 * girth, 0.76],
      [instepFlat, shin * 0.090 * girth, 0.90],
      [mix(instepFlat, ankleFlat, 0.8), shin * 0.098 * girth, 0.95]];
    for (const [at, r, sq] of run) {
      path.push(add(at, mul(stand, r * sq)));       // each ring lifted by its own half-depth: on the floor
      radii.push(r); squash.push(sq); hints.push(stand);
    }
  }
  const top = add(low.ankle, mul(up, rise));
  path.push(add(low.ankle, mul(up, shin * 0.02)), mix(low.ankle, top, 0.55), top);
  radii.push(rAnkle, rAnkle + (rTop - rAnkle) * 0.75, rTop);
  squash.push(1, 1, 1);
  hints.push(low.forward, low.forward, low.forward);
  return [piece(`sock_${side}`, "knit", sweep(path, radii, hints, SPAN, squash), overFoot)];
}

export function shoe(joints: Joints, side: string, style = "shoe", girth = 1,
                     sizes: Sizes = {}): Piece[] {
  const low = leg(joints, side);
  if (!low || style === "none") return [];
  const {shin} = low;
  const up = low.stand;                           // a sole lies on the floor, not across the shin
  const along = unit(sub(low.toe, low.instep));
  let flat = unit(sub(along, mul(up, dot(along, up))));
  if (same(flat, ZERO)) flat = along;
  const ground = low.floor;
  const back = add(flatten(low.ankle, ground, up), mul(flat, -shin * 0.135));
  const front = flatten(mix(low.instep, low.toe, 1.18), ground, up);
  const foot = sizes[`foot_wide_${side}`];
  // the foot's own half-width where it is widest, plus the thickness of a shoe round it
  let wide = ((foot ? foot + 0.006 : shin * 0.112)) * girth;
  if (style === "sneaker") wide *= 1.08;
  const thin = style === "sneaker" ? 0.34 : 0.28;
  const thick = wide * thin;
  const rise = style === "heel" ? shin * 0.085 : 0;
  const out: Piece[] = [];

  const sole: Point[] = [add(back, mul(up, thick + rise)),
                         add(mix(back, front, 0.50), mul(up, thick + rise * 0.35)),
                         add(mix(back, front, 0.88), mul(up, thick)),
                         add(front, mul(up, thick))];
  out.push(piece(`sole_${side}`, "rubber",
                 sweep(sole, [wide * 0.96, wide * 1.08, wide, wide * 0.66], up, SPAN,
                       [thin, thin, thin, thin]), true, true));
  if (rise) {
    out.push(piece(`heel_${side}`, "leather",
                   sweep([add(back, mul(up, thick + rise * 0.6)), back],
                         [wide * 0.46, wide * 0.36], flat, SQUARE, [0.62, 0.62]), false, true));
  }
  if (style === "sandal") {
    for (const t of [0.30, 0.68]) {
      const at = mix(add(back, mul(up, thick)), add(front, mul(up, thick)), t);
      out.push(piece(`strap${Math.round(t * 100)}_${side}`, "leather",
                     sweep([at, add(at, mul(up, shin * 0.085 * (1 - t * 0.4)))],
                           [wide * 0.94, wide * 0.78], flat, SQUARE, [0.20, 0.20]), false, true));
    }
    return out;
  }
  const over = shin * 0.085;
  const upper: Point[] = [add(mix(back, front, 0.97), mul(up, thick * 1.8)),
                          add(mix(back, front, 0.86), mul(up, over * 0.52)),
                          add(flatten(mix(low.instep, low.toe, 0.5), ground, up), mul(up, over * 0.78)),
                          add(flatten(low.instep, ground, up), mul(up, over)),
                          // a ring over the arch (without it the tube runs straight from instep to
                          // collar and the foot bulges out of its side halfway along), and the opening
                          // ...set BACK over the heel: a tube that stops at the ankle leaves the
                          // heel outside it, and then the heel is bare (see blender/tailor.py)
                          add(mix(flatten(low.instep, ground, up), back, 0.55),
                              mul(up, over * 1.15)),
                          add(add(low.ankle, mul(low.up, shin * 0.085)),
                              mul(flat, -shin * 0.095))];
  const mouth = ((sizes[`ankle_${side}`] ?? shin * 0.092)
                 + (style === "boot" ? 0.026 : 0.012)) * girth;
  const radii = [wide * 0.70, wide * 0.88, wide * 0.94, wide * 0.92, wide * 0.95, mouth];
  const squash = [0.62, 0.74, 0.84, 0.92, 0.98, 1.00];
  const hints: Point[] = [up, up, up, up, up, up];
  if (style === "boot") {
    // roomy: a boot is worn OVER the trouser, and a shaft cut close to the calf ends up inside a
    // trouser that clings, which puts triangles of boot through it all the way up (see blender/tailor.py)
    upper.push(add(low.ankle, mul(low.up, shin * 0.58)));
    radii.push(((sizes[`calf_${side}`] ?? shin * 0.142) + 0.030) * girth);
    squash.push(1);
    hints.push(flat);
  }
  out.push(piece(`shoe_${side}`, "leather", sweep(upper, radii, hints, SPAN, squash), true));
  return out;
}

export function watch(joints: Joints, side = "l", girth = 1, face = 1, sizes: Sizes = {}): Piece[] {
  const up = arm(joints, side);
  if (!up) return [];
  const {fore, along: towards} = up;
  const at = add(up.wrist, mul(towards, fore * 0.13));
  const r = ((sizes[`wrist_${side}`] ?? fore * 0.160) + 0.004) * girth;
  const strap = sweep([add(at, mul(towards, -fore * 0.035)), add(at, mul(towards, fore * 0.035))],
                      [r, r], up.out, SPAN, [0.78, 0.78]);
  const base = add(at, mul(up.out, r * 0.72));
  const box = sweep([base, add(base, mul(up.out, fore * 0.030 * face))],
                    [fore * 0.105 * face, fore * 0.098 * face], towards, SPAN, [1, 1]);
  return [piece(`watch_strap_${side}`, "leather", strap),
          piece(`watch_case_${side}`, "metal", box, false, true)];
}

export function wristband(joints: Joints, side = "l", width = 1, girth = 1,
                          sizes: Sizes = {}): Piece[] {
  const up = arm(joints, side);
  if (!up) return [];
  const {fore, along: towards} = up;
  const at = add(up.wrist, mul(towards, fore * 0.12));
  const seen = sizes[`wrist_${side}`] ?? fore * 0.160;
  return [piece(`wristband_${side}`, "leather",
                sweep([at, add(at, mul(towards, fore * 0.085 * width))],
                      [(seen + 0.005) * girth, (seen + 0.010) * girth], up.out))];
}

export function tie(joints: Joints, length = 1, width = 1): Piece[] {
  const mid = trunk(joints);
  if (!mid || same(mid.ahead, ZERO)) return [];
  const {tall, up, ahead} = mid;
  const collar = add(add(mid.neck, mul(up, -tall * 0.04)), mul(ahead, mid.wide * 0.30));
  const w = mid.wide * 0.085 * width;
  const out = [piece("tie_knot", "cloth",
                     sweep([add(collar, mul(up, tall * 0.035)), add(collar, mul(up, -tall * 0.02))],
                           [w * 0.85, w * 1.05], ahead, SPAN, [0.55, 0.55]), true, true)];
  const drop = tall * 0.92 * length;
  const blade: Point[] = [], radii: number[] = [], squash: number[] = [];
  for (let i = 0; i < 5; i++) {
    const t = i / 4;
    blade.push(add(add(collar, mul(up, -tall * 0.02 - drop * t)), mul(ahead, -mid.wide * 0.012 * t)));
    radii.push(w * (1 + 0.18 * t) * (1 - (0.92 * Math.max(0, t - 0.86)) / 0.14));
    squash.push(0.34);
  }
  out.push(piece("tie_blade", "cloth", sweep(blade, radii, ahead, SPAN, squash), false, true));
  return out;
}

export function scarf(joints: Joints, drop = 1, girth = 1): Piece[] {
  const mid = trunk(joints);
  if (!mid) return [];
  const {tall, up, ahead} = mid;
  const at = add(mid.neck, mul(up, tall * 0.045));
  const r = mid.wide * 0.195 * girth;
  const out = [piece("scarf_loop", "knit",
                     sweep([add(at, mul(up, tall * 0.045)), at, add(at, mul(up, -tall * 0.045))],
                           [r * 0.94, r, r * 1.02], same(ahead, ZERO) ? up : ahead, SPAN,
                           [0.88, 0.88, 0.88]))];
  if (!same(ahead, ZERO)) {
    const hang = add(add(at, mul(up, -tall * 0.04)), mul(ahead, r * 0.78));
    out.push(piece("scarf_tail", "knit",
                   sweep([hang, add(hang, mul(up, -tall * 0.28 * drop)),
                          add(hang, mul(up, -tall * 0.55 * drop))],
                         [r * 0.52, r * 0.46, r * 0.40], ahead, SPAN, [0.30, 0.30, 0.30]),
                   false, true));
  }
  return out;
}

// --- the one door ---------------------------------------------------------------------------------------

export interface Want { colour?: string; side?: string; height?: string; style?: string; girth?: number;
                        width?: number; length?: number; drop?: number; face?: number; over_foot?: boolean; }

export function cut(what: string, joints: Joints, want: Want = {}, sizes: Sizes = {}): Piece[] {
  const sides = SIDES[want.side || "both"] || ["l", "r"];
  const girth = want.girth || 1;
  if (what === "socks") {
    return ["l", "r"].flatMap(s =>
      sock(joints, s, want.height || "crew", girth, want.over_foot !== false, sizes));
  }
  if (what === "shoes_made") {
    return ["l", "r"].flatMap(s => shoe(joints, s, want.style || "shoe", girth, sizes));
  }
  if (what === "watch") return sides.flatMap(s => watch(joints, s, girth, want.face || 1, sizes));
  if (what === "wristband") {
    return sides.flatMap(s => wristband(joints, s, want.width || 1, girth, sizes));
  }
  if (what === "tie") return tie(joints, want.length || 1, want.width || 1);
  if (what === "scarf") return scarf(joints, want.drop || 1, girth);
  return [];
}

/** [what, want] for every made wearable a design calls for, in the order they go on.
 *
 *  Mirrors `tailor.asked_for`. A colour is what asks for one; footwear asks by style, because everybody
 *  wears shoes and the colour only says which colour. */
export function askedFor(design: any): [string, Want][] {
  const costume = (design && design.costume) || {};
  const outfit = (design && design.outfit) || {};
  const out: [string, Want][] = [];
  if (costume.socks) {
    // How far UP a sock is drawn is not how far up it is worn: with a trouser leg over it, the only part
    // anybody can see is between the trouser and the shoe, and drawing the rest shows through the
    // trouser. Bare legs get the whole sock. (Mirrors `tailor.asked_for`.)
    const bare = ["shorts", "skirt"].includes(outfit.garment)
                 && !LEGGED.includes(outfit.style);
    out.push(["socks", {colour: costume.socks,
                        height: bare ? (costume.sock_height || "crew") : "covered",
                        over_foot: ["none", undefined, null].includes(outfit.shoe_style)
                                   || outfit.shoe_style === "sandal"}]);
  }
  if (outfit.shoe_style && outfit.shoe_style !== "none") {
    out.push(["shoes_made", {colour: outfit.shoes || "#2b2118", style: outfit.shoe_style}]);
  }
  if (costume.tie) out.push(["tie", {colour: costume.tie, length: costume.tie_length || 1}]);
  if (costume.scarf) out.push(["scarf", {colour: costume.scarf}]);
  if (costume.wristband) {
    out.push(["wristband", {colour: costume.wristband, side: costume.wristband_side || "both",
                            width: costume.wristband_width || 1}]);
  }
  if (costume.watch) out.push(["watch", {colour: costume.watch, side: costume.watch_side || "left"}]);
  return out;
}

/** How a made thing catches the light: roughness, metalness and sheen, matching the build's table. */
export const STUFF: Record<string, [number, number, number]> = {
  knit: [0.90, 0, 0.85], cloth: [0.72, 0, 0.45], leather: [0.55, 0, 0.10],
  rubber: [0.88, 0, 0.00], metal: [0.22, 0.95, 0.00],
};
