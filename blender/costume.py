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


def rim_of(co, faces, body=(), least=8):
    """The hat's opening: the boundary loop that lies against the head.

    Not the lowest loop, and not the widest. A Santa cap's LOWEST boundary is the little hole at the tip
    of its bobble, four millimetres across and hanging below everything; anchoring a hat to that balloons
    it round the pompom. A fedora's WIDEST boundary is the outer edge of its brim, nowhere near the head.
    What the opening actually is, is the ring the head goes through - so it is found by asking which loop
    lies closest to the body. `body` is a sample of the body's vertices, in the same space as `co`; with
    none to go by, the widest loop is the best guess left. Loops of fewer than `least` vertices are
    ignored: they are bobble tips and lace holes, never an opening."""
    loops = [l for l in boundary_loops(faces) if len(l) >= least] or boundary_loops(faces)
    if not loops:
        return []
    if not len(body):
        return max(loops, key=lambda l: sum(math.dist(co[v], centroid(co, l)) for v in l) / len(l))
    return min(loops, key=lambda l: sum(min(math.dist(co[v], b) for b in body) for v in l) / len(l))


def loop_normal(co, loop, towards=None):
    """The normal of a boundary loop's own plane (Newell), pointing towards `towards` if that is given.

    A hat's opening is a tilted ring, so "up out of the opening" is not the world's up and cannot be
    faked with z."""
    n = [0.0, 0.0, 0.0]
    for a, b in zip(loop, loop[1:] + loop[:1]):
        pa, pb = co[a], co[b]
        n[0] += (pa[1] - pb[1]) * (pa[2] + pb[2])
        n[1] += (pa[2] - pb[2]) * (pa[0] + pb[0])
        n[2] += (pa[0] - pb[0]) * (pa[1] + pb[1])
    length = math.sqrt(sum(v * v for v in n)) or 1.0
    n = [v / length for v in n]
    if towards is not None:
        c = centroid(co, loop)
        if sum((towards[i] - c[i]) * n[i] for i in range(3)) < 0:
            n = [-v for v in n]
    return tuple(n)


def grow_hat(co, scale, rim=()):
    """A hat made bigger (or smaller) without disturbing the part that sits on the head.

    Only what is ABOVE the opening changes. The opening itself does not move, and neither does anything
    below it - the fur roll of a Santa cap hangs below the ring the head goes through, and letting it grow
    flares it outward and downward like a lampshade (measured: 318 of this cap's vertices are below the
    opening, and they moved up to 25 mm). Above the opening, everything grows away from its centre, in
    full at the crown and tapering to nothing as it comes back down to the ring.

    "Above" is measured along the opening's OWN normal, not the world's up: these hats are worn tilted.

    `co` is the hat's vertices (z up), `rim` its opening in loop order (`rim_of`); the answer is a new
    list in the same order."""
    if abs(scale - 1.0) < 1e-6 or not co:
        return [tuple(p) for p in co]
    rim = list(rim)
    if not rim:                                   # no opening to hold on by: grow it whole
        c = centroid(co, range(len(co)))
        return [tuple(c[i] + (p[i] - c[i]) * scale for i in range(3)) for p in co]
    c = centroid(co, rim)
    n = loop_normal(co, rim, centroid(co, range(len(co))))
    up = [sum((p[i] - c[i]) * n[i] for i in range(3)) for p in co]
    top = max(up) or 1.0
    out = []
    for p, h in zip(co, up):
        t = max(0.0, min(1.0, h / top))
        grow = 1.0 + (scale - 1.0) * (t * t * (3 - 2 * t))      # smooth: no crease at the opening
        out.append(tuple(c[i] + (p[i] - c[i]) * grow for i in range(3)))
    return out


# --- picking a part of a mesh and resizing it ------------------------------------------------------------
# The studio lets you click a part of anything worn - a sleeve, a crown, a boot - and make it bigger or
# smaller. A part is not a named thing in the asset: it is whatever lies within so many centimetres of
# where you clicked, measured ALONG the surface, so a click on a cuff does not leak onto the hand inside
# it. Resizing it has to leave it attached, which is the lesson the hat taught: grow away from the part's
# border, by the full amount deep inside it and by nothing at all at the edge.

def neighbours(faces):
    """{vertex: set of vertices sharing an edge with it}."""
    adj = defaultdict(set)
    for a, b in edges_of(faces):
        adj[a].add(b)
        adj[b].add(a)
    return adj


def part_at(co, faces, point, radius):
    """The vertices within `radius` metres of `point`, measured along the surface from the nearest vertex.

    Along the surface, not through the air: a sleeve's cuff is a centimetre from the wrist underneath it
    but a long way round the cloth, and a part you can click has to respect that."""
    if not co:
        return set()
    seed = min(range(len(co)), key=lambda v: math.dist(co[v], point))
    return band(co, edges_of(faces), [seed], radius)


def border_of(part, adj):
    """The vertices of `part` that touch something outside it - where it stays joined to the rest."""
    return {v for v in part if any(w not in part for w in adj.get(v, ()))}


def part_depth(co, part, adj, faces=None):
    """How deep inside `part` each of its vertices lies, walking in from the border along the surface.

    This is what lets a part be moved, turned or resized without tearing it off: whatever is done to the
    part is done in full where it is deepest and not at all at the border.

    When the part is the WHOLE object there is no border by adjacency - nothing is outside it - and what
    holds it on is its open boundary instead: a hat selected whole is still held by the ring the head goes
    through. That is the usual case for a hat, so it is not an edge case to skip."""
    edge = border_of(part, adj)
    if (not edge or edge == part) and faces:
        edge = {v for loop in boundary_loops(faces) for v in loop if v in part}
    if not edge or edge == part:
        return {}, []
    deep = {v: 0.0 for v in edge}
    heap = [(0.0, v) for v in edge]
    while heap:
        d, v = heapq.heappop(heap)
        if d > deep.get(v, math.inf):
            continue
        for w in adj.get(v, ()):
            if w not in part:
                continue
            nd = d + math.dist(co[v], co[w])
            if nd < deep.get(w, math.inf):
                deep[w] = nd
                heapq.heappush(heap, (nd, w))
    return deep, edge


def _turn(point, about, degrees):
    """`point` turned about the three axes through `about`, in degrees (x, y, z)."""
    x, y, z = (point[i] - about[i] for i in range(3))
    rx, ry, rz = (math.radians(d) for d in degrees)
    y, z = y * math.cos(rx) - z * math.sin(rx), y * math.sin(rx) + z * math.cos(rx)
    z, x = z * math.cos(ry) - x * math.sin(ry), z * math.sin(ry) + x * math.cos(ry)
    x, y = x * math.cos(rz) - y * math.sin(rz), x * math.sin(rz) + y * math.cos(rz)
    return (about[0] + x, about[1] + y, about[2] + z)


def shape_part(co, part, scale=1.0, move=(0.0, 0.0, 0.0), turn=(0.0, 0.0, 0.0), faces=None, adj=None):
    """`part` of a mesh resized, slid and turned - still joined to the rest of it.

    All three happen about the centre of the part's border, and all three fade to nothing at that border,
    so the seam never opens and nothing outside the part moves. A hat's border is the ring on the head, so
    turning the hat tips the cone over while the brim stays exactly where it sits.

    `move` is metres, `turn` is degrees about the x, y and z axes. Vertices outside `part` come back
    untouched."""
    part = set(part)
    still = abs(scale - 1.0) < 1e-6 and not any(move) and not any(turn)
    if still or not part:
        return [tuple(p) for p in co]
    adj = adj if adj is not None else neighbours(faces or [])
    deep, edge = part_depth(co, part, adj, faces)
    if not deep:
        return [tuple(p) for p in co]
    c = centroid(co, edge)
    far = max(deep.values()) or 1.0
    out = [tuple(p) for p in co]
    for v in part:
        t = min(1.0, deep.get(v, far) / far)
        ease = t * t * (3 - 2 * t)                              # smooth: no crease at the seam
        grow = 1.0 + (scale - 1.0) * ease
        p = tuple(c[i] + (co[v][i] - c[i]) * grow for i in range(3))
        if any(turn):
            p = _turn(p, c, tuple(d * ease for d in turn))
        out[v] = tuple(p[i] + move[i] * ease for i in range(3))
    return out


def grow_part(co, part, scale, faces=None, adj=None):
    """Resizing alone - `shape_part` with nothing else asked for."""
    return shape_part(co, part, scale=scale, faces=faces, adj=adj)


# --- a Santa cap made to fit, instead of an asset that never does -----------------------------------------
# The cap in the asset library is one size, worn tilted, with a thin band - a child's cap. A real one is a
# deep cone that curves over and flops sideways, a fur roll a third of its height, and a fat bobble at the
# tip. None of that can be got by scaling the asset, so the cap is built on the head it is going on: the
# opening is the head's own measured circle, so it can never bulge through the skull.

def cap_path(base, radius, height, droop=0.6, towards=0.0, rings=16):
    """The cap's spine: `rings` points from the opening up to the tip, bending over as it rises.

    `droop` is how far it flops (0 straight up, 1 right over), `towards` which way in degrees round the
    head (0 is the character's left). The bend is a parabola in the rise, so it leaves the head upright
    and curls more the further out it goes - which is how a soft cap hangs."""
    lean_x = math.cos(math.radians(towards))
    lean_y = math.sin(math.radians(towards))
    out = []
    for i in range(rings):
        t = i / (rings - 1)
        sideways = droop * height * 1.15 * t * t
        rise = height * t * (1.0 - 0.35 * droop * t)          # it rises less as it flops over
        out.append((base[0] + lean_x * sideways, base[1] + lean_y * sideways, base[2] + rise))
    return out


def cap_radius(t, radius, band=0.3, roll=0.22, tip=0.1):
    """How wide the cap is a fraction `t` of the way up: a fur roll, then a cone tapering to the tip."""
    if t <= band:
        swell = math.sin(math.pi * (t / band)) if band > 0 else 0.0
        return radius * (1.0 + roll * swell)
    rest = (t - band) / (1.0 - band)
    return radius * ((1.0 - rest) ** 0.75 * (1.0 - tip) + tip)


def santa_cap(centre, base_z, radius, height=None, droop=0.6, towards=0.0, band=0.3,
              rings=16, span=18, crown=None, squash=1.0):
    """A Santa cap built for one head: (rings of points, how many of them are fur, the tip).

    Two pieces, as a real cap is. A fur ROLL - a thick cylinder standing a little proud of the head,
    sitting on the forehead, not perched on the crown - and above it a cone that tapers and flops the way
    it is pointed. The cone starts at exactly the radius the roll ends at, so there is no step between
    them, and the whole thing is measured from the head it is going on, so it cannot bulge through.

    `centre` is the head's middle (x, y), `base_z` the bottom of the roll, `radius` the head's radius
    there. `band` is how much of the cap's height is fur.

    A head is NOT round: measured on a built character it is about 17 cm across and 21.6 cm front to
    back. A circular roll sized from the average of those two stands 3 cm clear of the temples and only
    7 mm clear at the front - a visible shelf beside the ears, which is what this was reported as. So
    `squash` (across / front-back, 1.0 being a round head) narrows the whole cap across the face. It is
    applied to the offset from the spine, not to the spine itself, so the roll becomes the ellipse the
    head actually is and the cone stays joined to it with no step."""
    height = height if height else radius * 3.0
    band = min(0.6, max(0.08, band))
    # How tall the fur is comes from the HEAD, not from the cap's length: a bigger cap has a longer cone,
    # not a deeper band. Measured against a real one, the roll is about 6 cm on a 9.8 cm head.
    roll_h = radius * 0.62 * (band / 0.3)
    roll_r = radius * 1.12                                # and how far it stands proud of the head
    in_roll = max(2, round(rings * band))
    lean_x, lean_y = math.cos(math.radians(towards)), math.sin(math.radians(towards))
    spine, widths = [], []
    for i in range(in_roll):                              # the roll: straight up, barely tapering
        t = i / max(1, in_roll - 1)
        spine.append((centre[0], centre[1], base_z + roll_h * t))
        widths.append(roll_r * (1.0 - 0.04 * t))
    rest_rings = rings - in_roll
    for i in range(rest_rings):                           # the cone: from the roll's top, over and down
        t = (i + 1) / rest_rings
        lean = droop * (height - roll_h) * 1.3 * t * t
        rise = (height - roll_h) * t * (1.0 - 0.35 * droop * t)
        spine.append((centre[0] + lean_x * lean, centre[1] + lean_y * lean, base_z + roll_h + rise))
        widths.append(radius * ((1.0 - t) ** 0.85 * 1.02 + 0.06))
    out = []
    for i, (point, wide) in enumerate(zip(spine, widths)):
        ahead = spine[min(i + 1, rings - 1)]
        behind = spine[max(i - 1, 0)]
        axis = [ahead[k] - behind[k] for k in range(3)]
        length = math.sqrt(sum(a * a for a in axis)) or 1.0
        axis = [a / length for a in axis]
        side = [-axis[1], axis[0], 0.0]
        if not any(side):
            side = [1.0, 0.0, 0.0]
        slen = math.sqrt(sum(a * a for a in side)) or 1.0
        side = [a / slen for a in side]
        other = [axis[1] * side[2] - axis[2] * side[1],
                 axis[2] * side[0] - axis[0] * side[2],
                 axis[0] * side[1] - axis[1] * side[0]]
        ring = []
        for a in (2 * math.pi * j / span for j in range(span)):
            off = [wide * (math.cos(a) * side[k] + math.sin(a) * other[k]) for k in range(3)]
            off[0] *= squash              # x is across the face in both the build and the live view
            ring.append(tuple(point[k] + off[k] for k in range(3)))
        out.append(ring)
    return out, in_roll, spine[-1]


def ball(centre, radius, rows=6, span=10):
    """A little sphere as rings, for the bobble on the end of a cap."""
    out = []
    for i in range(1, rows):
        phi = math.pi * i / rows
        r = radius * math.sin(phi)
        z = centre[2] + radius * math.cos(phi)
        out.append([(centre[0] + r * math.cos(2 * math.pi * j / span),
                     centre[1] + r * math.sin(2 * math.pi * j / span), z) for j in range(span)])
    return out
