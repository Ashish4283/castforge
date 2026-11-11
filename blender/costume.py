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
