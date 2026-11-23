"""The body as the designer's live view sees it, and how a worn thing is pinned to it.

Shared by `preview_kit.py` (the body and its morphs) and `preview_wear.py` (hair, beard, clothes), because
the two must agree exactly about which vertices the body has.

How a garment follows the body: not by guesswork. A MakeHuman asset already carries, for every one of its
vertices, three body vertices, three weights and an offset measured against three spans of the body
(`.mhclo`). Rebuilding a garment is then a weighted sum plus that offset, scaled by how long those spans
are on THIS body - which is what MakeHuman itself does, so it comes out right to the micrometre on any
shape. The browser does the same arithmetic as the sliders move; see `wear_positions`.

The whole mesh is kept, helpers and all. The helpers are never drawn - they are the cages that fit clothes -
but a garment's offsets are measured against them, so they have to be there and they have to morph.
"""
import numpy as np


def body_parts(human):
    """(skin vertex ids, triangles of the skin) - triangles numbered into the WHOLE mesh.

    The "body" vertex group is the skin; everything else is helper geometry and is never drawn."""
    groups = {g.name: g.index for g in human.vertex_groups}
    members = {}
    for v in human.data.vertices:
        for g in v.groups:
            members.setdefault(g.group, []).append(v.index)
    body = np.array(sorted(members[groups["body"]]), dtype=np.int64)
    skin = set(body.tolist())
    tris = []
    for poly in human.data.polygons:
        vs = list(poly.vertices)
        if any(v not in skin for v in vs):
            continue
        for k in range(1, len(vs) - 1):                  # a fan: quads become two triangles
            tris.append([vs[0], vs[k], vs[k + 1]])
    return body, np.array(tris, dtype=np.uint32)


def shaped_coords(human, mask=None):
    """Where every vertex is right now, with the macros applied and NOTHING hidden.

    Every mask is turned off first, not just the helper one: putting a garment on adds another mask to the
    body for what that garment covers, and a hidden vertex is a missing vertex - which silently renumbers
    the mesh and sends every binding somewhere else. (`mask` is accepted and ignored, for old callers.)"""
    import bpy
    hidden = [m for m in human.modifiers if m.type == "MASK" and m.show_viewport]
    for m in hidden:
        m.show_viewport = False
    deps = bpy.context.evaluated_depsgraph_get()
    ev = human.evaluated_get(deps)
    me = ev.to_mesh()
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    ev.to_mesh_clear()
    for m in hidden:
        m.show_viewport = True
    if len(co) // 3 != len(human.data.vertices):         # never bind against a mesh that lost vertices
        raise RuntimeError(f"the body evaluated to {len(co) // 3} vertices, not {len(human.data.vertices)}")
    return co.reshape(-1, 3)


def to_view(points):
    """Blender's z-up turned into the app viewer's y-up. A proper rotation, so anything measured in one
    frame (a garment's offsets, say) stays true in the other."""
    out = np.asarray(points, dtype=np.float64)[:, [0, 2, 1]].astype(np.float32)
    out[:, 2] *= -1.0
    return out


def fit_scales(coords, x_scale, y_scale, z_scale):
    """The three spans a garment's offsets are measured against, on this body.

    MakeHuman names them x/y/z in its own axes; in Blender its y is up, so its y span measures Blender's z
    and its z span measures Blender's y. Getting this pair the wrong way round puts hats through heads."""
    def span(ref, axis):
        a, b, reference = ref
        return abs(float(coords[a][axis] - coords[b][axis])) / reference

    return np.array([span(x_scale, 0), span(z_scale, 1), span(y_scale, 2)])


def wear_positions(coords, verts, weights, offsets, scales):
    """Where a garment's vertices sit on a body of this shape - the same sum the browser does."""
    base = (coords[verts[:, 0]] * weights[:, 0:1] + coords[verts[:, 1]] * weights[:, 1:2]
            + coords[verts[:, 2]] * weights[:, 2:3])
    return base + offsets * scales


def joint_centres(human, coords):
    """{joint cube name: its centre} - MakeHuman's own joint markers, which is where a rig's bones go.

    Measured on `coords`, the body as it stands now: the joints move with the macros like everything else,
    so taking them from the base mesh puts a tall person's wrist in the wrong place."""
    out = {}
    for g in human.vertex_groups:
        if g.name.startswith("joint-"):
            out[g.name] = g.index
    members = {}
    for v in human.data.vertices:
        for g in v.groups:
            if g.group in out.values():
                members.setdefault(g.group, []).append(v.index)
    co = np.asarray(coords)
    return {name: tuple(co[members[idx]].mean(axis=0)) for name, idx in out.items() if members.get(idx)}


def hand_vertices(human, coords, skin):
    """The skin of both hands: everything past the wrist, towards the middle fingertip. Gloves cover this."""
    import costume
    joints = joint_centres(human, coords)
    out = set()
    for side in ("l", "r"):
        wrist = joints.get(f"joint-{side}-hand")          # MakeHuman's "hand" joint IS the wrist
        tip = joints.get(f"joint-{side}-finger-3-4") or joints.get(f"joint-{side}-finger-2-4")
        if wrist and tip:
            out |= costume.beyond(coords, skin, wrist, tip)
    return out
