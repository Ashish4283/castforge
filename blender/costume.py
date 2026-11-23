"""Costume geometry (pure, no bpy; tested): garment openings, trim bands, coat extension, weight mixing.

build_character.py turns these into meshes: fur trim on a garment's cuffs/hem/collar/front, a belt band,
a coat that continues the top's hem down to mid-thigh. Coordinates are world metres in rest pose
(character faces -Y, z up)."""
import heapq
import math
from collections import defaultdict


def boundary_loops(faces):
    """Open edges of a mesh (used by one face) chained into loops of vertex indices, in walk order."""
    count = defaultdict(int)
    for f in faces:
        for a, b in zip(f, f[1:] + f[:1]):
            count[(min(a, b), max(a, b))] += 1
    nxt = defaultdict(list)
    for (a, b), n in count.items():
        if n == 1:
            nxt[a].append(b)
            nxt[b].append(a)
    loops, seen = [], set()
    for start in sorted(nxt):
        if start in seen:
            continue
        loop, prev, cur = [start], None, start
        seen.add(start)
        while True:
            step = next((v for v in nxt[cur] if v != prev and v not in seen), None)
            if step is None:
                break
            loop.append(step)
            seen.add(step)
            prev, cur = cur, step
        if len(loop) >= 3:
            loops.append(loop)
    return loops


def centroid(co, verts):
    n = len(verts)
    return tuple(sum(co[v][i] for v in verts) / n for i in range(3))


def openings(co, loops, centre_x=0.0, arm=0.15):
    """Name a top's openings: {"hem": loop, "collar": loop, "cuffs": [loops]} (missing ones are left out).

    Torso openings sit near the body's centre line; the lowest is the hem, the highest the collar. Openings
    further out than `arm` metres are the sleeve cuffs."""
    torso = [l for l in loops if abs(centroid(co, l)[0] - centre_x) < arm]
    out = {"cuffs": [l for l in loops if abs(centroid(co, l)[0] - centre_x) >= arm]}
    if torso:
        out["hem"] = min(torso, key=lambda l: centroid(co, l)[2])
        if len(torso) > 1:
            out["collar"] = max(torso, key=lambda l: centroid(co, l)[2])
    return out


def lowest_per_side(co, loops, centre_x=0.0):
    """The lowest opening on each side (trouser legs), or the highest when `loops` are shoe openings."""
    sides = {}
    for l in loops:
        c = centroid(co, l)
        side = "L" if c[0] > centre_x else "R"
        if side not in sides or c[2] < centroid(co, sides[side])[2]:
            sides[side] = l
    return list(sides.values())


def highest_per_side(co, loops, centre_x=0.0):
    sides = {}
    for l in loops:
        c = centroid(co, l)
        side = "L" if c[0] > centre_x else "R"
        if side not in sides or c[2] > centroid(co, sides[side])[2]:
            sides[side] = l
    return list(sides.values())


def edges_of(faces):
    out = set()
    for f in faces:
        for a, b in zip(f, f[1:] + f[:1]):
            out.add((min(a, b), max(a, b)))
    return out


def band(co, edges, seeds, width):
    """Vertices within `width` metres of the seed vertices, measured along the surface (Dijkstra)."""
    adj = defaultdict(list)
    for a, b in edges:
        d = math.dist(co[a], co[b])
        adj[a].append((b, d))
        adj[b].append((a, d))
    dist = {s: 0.0 for s in seeds}
    heap = [(0.0, s) for s in seeds]
    while heap:
        d, v = heapq.heappop(heap)
        if d > dist.get(v, math.inf):
            continue
        for w, step in adj[v]:
            nd = d + step
            if nd <= width and nd < dist.get(w, math.inf):
                dist[w] = nd
                heapq.heappush(heap, (nd, w))
    return set(dist)


def front_strip(co, verts, centre, half_width, z_range):
    """Vertices on the front centre line (the coat's closing), between z_range[0] and z_range[1]."""
    cx, cy = centre
    lo, hi = z_range
    return {v for v in verts if abs(co[v][0] - cx) < half_width and co[v][1] < cy and lo <= co[v][2] <= hi}


def z_band(co, verts, z, half_height):
    return {v for v in verts if abs(co[v][2] - z) <= half_height}


def faces_inside(faces, verts):
    """Indices of faces whose corners are all in `verts`."""
    return [i for i, f in enumerate(faces) if all(v in verts for v in f)]


def faces_mostly(faces, verts, fraction=0.5):
    """Indices of faces with at least `fraction` of their corners in `verts`. A plate selected this way has
    a solid edge: picking only whole faces leaves a torn, moth-eaten boundary."""
    out = []
    for i, f in enumerate(faces):
        hit = sum(1 for v in f if v in verts)
        if f and hit >= max(1, int(round(len(f) * fraction))):
            out.append(i)
    return out


def hem_rings(hem, centre, length, rings, flare):
    """New vertex rings that continue a hem downward: ring k (1..rings) lies length*k/rings lower and
    flares out from the centre line by (1 + flare * k/rings). `hem` is a list of (x, y, z)."""
    cx, cy = centre
    out = []
    for k in range(1, rings + 1):
        t = k / rings
        s = 1.0 + flare * t
        out.append([(cx + (x - cx) * s, cy + (y - cy) * s, z - length * t) for x, y, z in hem])
    return out


def ring_faces(first, rings, closed=True):
    """Quads joining a loop of vertex indices `first` to the rings below it (lists of vertex indices)."""
    rows = [first] + rings
    n = len(first)
    faces = []
    for upper, lower in zip(rows, rows[1:]):
        for i in range(n if closed else n - 1):
            j = (i + 1) % n
            faces.append((upper[i], upper[j], lower[j], lower[i]))
    return faces


def back_arc(co, loop, centre, face=-1.0, span=0.62):
    """The back part of a neck loop, in walk order from one shoulder round to the other: where a cape hangs
    from. `face` is the sign of y the face points along (-1 in CastForge, so the back is +y)."""
    cx, cy = centre
    picked = [v for v in loop if (co[v][1] - cy) * face < 0]
    if not picked:
        return []
    # keep the widest run: a loop can cross the centre line more than once
    runs, run = [], []
    for v in loop + loop[:1]:
        if v in picked:
            run.append(v)
        elif run:
            runs.append(run)
            run = []
    if run:
        runs.append(run)
    best = max(runs, key=len) if runs else []
    keep = max(3, int(round(len(best) * span)))
    drop = max(0, (len(best) - keep) // 2)
    return best[drop:drop + keep]


def shoulder_line(co, verts, centre, face=-1.0, z=0.0, band=0.07, count=13):
    """A line of points straight across the back at height z, left shoulder to right: where a cape hangs
    from. Picks the backmost vertex in each of `count` columns, so the line follows the body's shape."""
    cx, cy = centre
    picked = [v for v in verts if abs(co[v][2] - z) <= band and (co[v][1] - cy) * face < 0]
    if not picked:
        return []
    xs = [co[v][0] for v in picked]
    lo, hi = min(xs), max(xs)
    if hi - lo < 1e-6:
        return [co[picked[0]]]
    out = []
    for k in range(count):
        a_x = lo + (hi - lo) * k / (count - 1)
        column = [v for v in picked if abs(co[v][0] - a_x) <= (hi - lo) / (count - 1)]
        if not column:
            continue
        # the nearest column, and of those the vertex furthest round the back
        v = min(column, key=lambda v_: (round(abs(co[v_][0] - a_x), 4), (co[v_][1] - cy) * face))
        if not out or co[v] != out[-1]:
            out.append(co[v])
    return out


def cape_rings(top, centre, length, rings, flare=0.55, sway=0.10, lift=0.0):
    """Rings for a cape hanging from `top` (a strip of points across the shoulders): each ring falls lower,
    spreads out from the centre line (flare) and drifts backwards (sway, along the cape's own side of the
    body), so it hangs clear of the legs instead of through them."""
    cx, cy = centre
    out = []
    back = 1.0 if (sum(p[1] for p in top) / len(top)) >= cy else -1.0
    for k in range(1, rings + 1):
        t = k / rings
        s = 1.0 + flare * t
        drift = sway * t * t * back            # the hem swings out further than the shoulders
        ring = []
        for x, y, z in top:
            ring.append((cx + (x - cx) * s, cy + (y - cy) * s + drift, z - length * t + lift * t))
        out.append(ring)
    return out


def hood_cut(co, verts, centre, face=-1.0, chin_z=0.0, open_at=0.03, half_width=0.085):
    """The head vertices a hood covers: everything above the chin except the face itself. `face` is the sign
    of y the face points along; `open_at` is how far forward the opening starts (bigger: more face showing)."""
    cx, cy = centre
    out = set()
    for v in verts:
        x, y, z = co[v]
        if z < chin_z:
            continue
        if (y - cy) * face > open_at and abs(x - cx) < half_width:     # the face opening
            continue
        out.add(v)
    return out


def mix_weights(a, b, t, keep=4):
    """Blend two {group: weight} dicts (t=0: all a, t=1: all b), keep the strongest `keep`, normalise."""
    out = defaultdict(float)
    for g, w in a.items():
        out[g] += (1.0 - t) * w
    for g, w in b.items():
        out[g] += t * w
    top = sorted(out.items(), key=lambda kv: -kv[1])[:keep]
    total = sum(w for _, w in top) or 1.0
    return {g: w / total for g, w in top if w > 0}


def push_clear(point, surface, normal, clearance):
    """Move `point` out along `normal` so it is at least `clearance` in front of the surface point."""
    d = sum((p - s) * n for p, s, n in zip(point, surface, normal))
    if d >= clearance:
        return tuple(point)
    return tuple(p + (clearance - d) * n for p, n in zip(point, normal))


def hood_rings(centre, base_z, top_z, radius, rings=8, span=17, opening=1.45, flare=1.45,
               dome=0.45, back=0.05, sag=0.07, rise=0.13, face=-1.0):
    """Rings for a hood: a cowl that sits on the shoulders, rises round the head, domes over the crown and
    stays open at the face.

    Three earlier tries copied head faces or banded the collar and all read as a flat band, because a hood
    is not the head's surface: it is a shell of its own. Ring k (1..rings) is spaced evenly in height from
    `base_z` (the shoulders) to `top_z` (just over the crown) and carries `span` points walked round the
    back from one lip of the face opening to the other. Below `dome` (a fraction of that height, about the
    middle of the head) the shell draws in from `flare` times `radius` down at the shoulders to `radius`;
    above it the radius follows a dome, so the crown is round and not a flat lid. The opening narrows to
    nothing by the crown, and the whole shell leans `back` metres away from the face as it rises. The last
    ring is small: cap it with one face.

    Returns a list of `rings` lists of `span` (x, y, z) points, each ring in the same walk order."""
    cx, cy = centre
    out = []
    for k in range(1, rings + 1):
        t = k / rings
        z = base_z + (top_z - base_z) * t
        if t <= dome:
            r = radius * (flare + (1.0 - flare) * t / dome)
        else:
            u = (t - dome) / (1.0 - dome)
            r = radius * math.sqrt(max(0.05, 1.0 - u * u))
        half = opening * (1.0 - t) ** 1.4                                  # shut by the crown
        y0 = cy - face * back * t                                          # leans away from the face
        ring = []
        for i in range(span):
            s = i / (span - 1)
            a = half + (2 * math.pi - 2 * half) * s                        # from one lip round to the other
            drape = sag * (1.0 - t) * (1.0 - math.cos(a)) / 2.0            # the back falls onto the shoulders
            lip = max(0.0, 1.0 - min(s, 1.0 - s) / 0.3)                    # ...the open edge curves up instead
            ring.append((cx + r * math.sin(a), y0 + face * r * math.cos(a),
                         z - drape + rise * (1.0 - t) * lip))
        out.append(ring)
    return out


# Fur trim is a band round each opening, and the build and the live view must choose the same vertices or
# the preview trims a different coat from the one that gets built. One place, used by both.
TRIM_WIDTHS = {"hem": 0.075, "collar": 0.04, "cuff": 0.055, "boot": 0.05}


def trim_bands(co, faces, centre_x=0.0, sleeves="short"):
    """{"hem": verts, "collar": verts, "cuff": verts} - the bands fur trim covers on a top or a dress.

    Cuffs only count when the sleeves are long: trimming a short sleeve puts fur round the biceps."""
    edges = edges_of(faces)
    ops = openings(co, boundary_loops(faces), centre_x)
    out = {}
    for name in ("hem", "collar"):
        if ops.get(name):
            out[name] = band(co, edges, ops[name], TRIM_WIDTHS[name])
    cuffs = ops.get("cuffs") or [] if sleeves == "long" else []
    if cuffs:
        out["cuff"] = set().union(*(band(co, edges, c, TRIM_WIDTHS["cuff"]) for c in cuffs))
    return out


def boot_bands(co, faces, centre_x=0.0):
    """The band round the top of each shoe - where a boot's fur cuff goes."""
    tops = highest_per_side(co, boundary_loops(faces), centre_x)
    if not tops:
        return {}
    edges = edges_of(faces)
    return {"boot": set().union(*(band(co, edges, t, TRIM_WIDTHS["boot"]) for t in tops))}


def beyond(co, verts, origin, towards, reach=1.6):
    """Those of `verts` past the plane through `origin` facing `towards`, and within `reach` of `origin`
    measured in lengths of origin-to-towards.

    How a glove is cut: everything past the wrist, towards the fingertips. The base MakeHuman body has no
    "hand" vertex group - only `body`, helpers and the joint cubes a rig is built from - so a region like
    this is found from two joints, not from a name. The reach matters: a plane alone runs on across the
    whole body and a glove swallows the far leg."""
    axis = [towards[i] - origin[i] for i in range(3)]
    length = math.sqrt(sum(a * a for a in axis)) or 1.0
    axis = [a / length for a in axis]
    at = sum(origin[i] * axis[i] for i in range(3))
    far = reach * length
    return {v for v in verts
            if sum(co[v][i] * axis[i] for i in range(3)) >= at and math.dist(co[v], origin) <= far}


def rim_of(co, faces):
    """The hat's opening: the boundary loop whose centre is lowest - the edge that grips the head."""
    loops = boundary_loops(faces)
    return min(loops, key=lambda l: centroid(co, l)[2]) if loops else []


def grow_hat(co, scale, rim=()):
    """A hat made bigger (or smaller) without lifting it off the head.

    `rim` is its opening (`rim_of`), and that is what holds it on: those vertices do not move at all.
    Everything else grows away from the opening's centre, by the full `scale` where it is furthest from
    the opening - the crown - and by less as it comes back down to the brim.

    The two obvious ways both fail, and both look wrong on a Santa cap: scaling the whole hat lifts the
    brim clear of the skull on every side, and scaling about a horizontal plane through the lowest vertex
    stretches the front of the brim up off the forehead, because these hats are worn at an angle.

    `co` is the hat's vertices (z up); the answer is a new list in the same order."""
    if abs(scale - 1.0) < 1e-6 or not co:
        return [tuple(p) for p in co]
    rim = list(rim)
    if not rim:                                   # no opening to hold on by: grow it whole
        c = centroid(co, range(len(co)))
        return [tuple(c[i] + (p[i] - c[i]) * scale for i in range(3)) for p in co]
    c = centroid(co, rim)
    edge = [co[v] for v in rim]
    away = [min(math.dist(p, e) for e in edge) for p in co]
    far = max(away) or 1.0
    out = []
    for p, d in zip(co, away):
        t = d / far
        grow = 1.0 + (scale - 1.0) * (t * t * (3 - 2 * t))      # smooth: no crease where it meets the brim
        out.append(tuple(c[i] + (p[i] - c[i]) * grow for i in range(3)))
    return out
