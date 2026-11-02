"""CastForge prop factory: build solid 3D props from a short description (no model files needed).

    {"id": "t1", "make": "table", "shape": "round", "size": [0.8, 0.8, 0.75], "color": "#6b4423",
     "material": "wood", "position": [0.2, 0.9], "rotation": 0}
    {"id": "c1", "make": "cup", "on": "t1", "position": [0.25, 0.9], "color": "#ffffff", "material": "ceramic"}

size is [width, depth, height] in metres (each type has sensible defaults). Everything is built from
bevelled primitives so it renders well in EEVEE, and every prop reports its floor footprint so walks
route around it.
"""
import math

import bpy
from mathutils import Vector

MATERIALS = {
    #            roughness metallic transmission sheen  coat
    "wood":     (0.55, 0.0, 0.0, 0.0, 0.1),
    "metal":    (0.30, 1.0, 0.0, 0.0, 0.0),
    "fabric":   (0.90, 0.0, 0.0, 0.6, 0.0),
    "leather":  (0.45, 0.0, 0.0, 0.0, 0.3),
    "glass":    (0.05, 0.0, 1.0, 0.0, 0.0),
    "plastic":  (0.35, 0.0, 0.0, 0.0, 0.2),
    "ceramic":  (0.20, 0.0, 0.0, 0.0, 0.6),
    "stone":    (0.75, 0.0, 0.0, 0.0, 0.0),
}
DEFAULT_SIZE = {
    "table": (1.2, 0.7, 0.75), "chair": (0.45, 0.48, 0.9), "stool": (0.38, 0.38, 0.75),
    "sofa": (1.9, 0.85, 0.85), "bed": (1.6, 2.0, 0.55), "shelf": (0.9, 0.32, 1.8),
    "counter": (2.0, 0.6, 0.95), "door": (0.9, 0.06, 2.05), "wall": (3.0, 0.12, 2.6),
    "window": (1.2, 0.08, 1.2), "lamp": (0.35, 0.35, 1.6), "cup": (0.08, 0.08, 0.1),
    "plant": (0.45, 0.45, 1.0), "box": (0.5, 0.5, 0.5), "tv": (1.1, 0.25, 1.2), "bench": (1.4, 0.4, 0.45),
    "seat": (0.45, 0.45, 0.46), "santa_hat": (0.3, 0.3, 0.32),
}
DOORS = {}       # id -> hinge, bell pivot, size (for the "enter" action)
SEATS = {}       # id -> seat height (for "sit"); position/facing are added once placed
DEFAULT_MATERIAL = {"sofa": "fabric", "bed": "fabric", "cup": "ceramic", "window": "glass", "lamp": "metal",
                    "tv": "plastic", "wall": "stone", "plant": "ceramic"}


def hex_rgb(h, default=(0.5, 0.5, 0.5)):
    try:
        h = h.lstrip("#")
        srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb)
    except Exception:
        return default


def material(name, color, kind):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    rough, metal, trans, sheen, coat = MATERIALS.get(kind, MATERIALS["wood"])
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Transmission Weight"].default_value = trans
    b.inputs["Sheen Weight"].default_value = sheen
    b.inputs["Coat Weight"].default_value = coat
    if kind == "glass":
        b.inputs["Alpha"].default_value = 0.35
        m.surface_render_method = "BLENDED" if hasattr(m, "surface_render_method") else None
    return m


class Builder:
    def __init__(self, pid, mat):
        self.parts, self.pid, self.mat = [], pid, mat

    def box(self, size, loc, bevel=0.01, mat=None, rot=(0, 0, 0)):
        bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
        o = bpy.context.object
        o.scale = size
        bpy.ops.object.transform_apply(scale=True)
        self._finish(o, bevel, mat)
        return o

    def cyl(self, r, h, loc, bevel=0.005, mat=None, verts=32, rot=(0, 0, 0)):
        bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, location=loc, vertices=verts, rotation=rot)
        o = bpy.context.object
        self._finish(o, bevel, mat)
        return o

    def sphere(self, r, loc, mat=None, scale=(1, 1, 1)):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc, segments=24, ring_count=12)
        o = bpy.context.object
        o.scale = scale
        self._finish(o, 0, mat)
        bpy.ops.object.shade_smooth()
        return o

    def _finish(self, o, bevel, mat):
        if bevel:
            m = o.modifiers.new("bevel", "BEVEL")
            m.width, m.segments = bevel, 2
            o.modifiers.new("wn", "WEIGHTED_NORMAL")
        o.data.materials.append(mat or self.mat)
        o.name = f"{self.pid}_part{len(self.parts)}"
        self.parts.append(o)


def build(p, n, stage_to_world, tops):
    """Create one prop; returns (root object, footprint corners in world XY or None, top height).
    tops maps prop id -> top height, for "on"."""
    kind = p["make"]
    pid = p.get("id", f"prop{n}")
    w, d, h = p.get("size") or DEFAULT_SIZE.get(kind, (0.5, 0.5, 0.5))
    mat_kind = p.get("material") or DEFAULT_MATERIAL.get(kind, "wood")
    mat = material(f"{pid}_mat", hex_rgb(p.get("color", "#7a5230")), mat_kind)
    dark = material(f"{pid}_dark", (0.03, 0.03, 0.03), "metal")
    B = Builder(pid, mat)
    leg = min(w, d) * 0.06 + 0.015

    if kind in ("chair", "stool", "bench", "sofa", "seat"):
        seat_h = {"chair": min(0.46, h * 0.5), "sofa": 0.48}.get(kind, h)
        SEATS[pid] = {"seat_h": seat_h, "depth": d}

    if kind == "table":
        if p.get("shape") == "round":
            B.cyl(w / 2, 0.04, (0, 0, h - 0.02))
            B.cyl(0.04, h - 0.06, (0, 0, (h - 0.04) / 2))
            B.cyl(w * 0.28, 0.03, (0, 0, 0.015))
        else:
            B.box((w, d, 0.04), (0, 0, h - 0.02))
            for sx in (-1, 1):
                for sy in (-1, 1):
                    B.box((leg, leg, h - 0.04), (sx * (w / 2 - leg), sy * (d / 2 - leg), (h - 0.04) / 2))
    elif kind in ("chair", "stool", "bench"):
        if kind == "stool" and p.get("shape", "round") == "round":
            B.cyl(w / 2, 0.05, (0, 0, seat_h - 0.025))
        else:
            B.box((w, d, 0.05), (0, 0, seat_h - 0.025))
        for sx in (-1, 1):
            for sy in (-1, 1):
                B.box((leg * 0.8, leg * 0.8, seat_h - 0.05), (sx * (w / 2 - leg), sy * (d / 2 - leg), (seat_h - 0.05) / 2))
        if kind == "stool" and seat_h > 0.6:
            B.box((w - 2 * leg, leg * 0.6, leg * 0.6), (0, -(d / 2 - leg), seat_h * 0.35))   # foot rest
        if kind == "chair":
            B.box((w, 0.04, h - seat_h), (0, d / 2 - 0.02, seat_h + (h - seat_h) / 2))
    elif kind == "seat":
        # invisible: for sitting where the picture already shows a chair or a car seat
        o = B.box((w, d, h), (0, 0, h / 2), bevel=0)
        o.hide_render = True
        o.visible_shadow = False
    elif kind == "santa_hat":
        # built upright (white fur brim, red cone, white pompom), then laid on its side as if dropped
        red = material(f"{pid}_red", hex_rgb(p.get("color", "#a3161a")), "fabric")
        fur = material(f"{pid}_fur", (0.92, 0.92, 0.9), "fabric")
        pivot = bpy.data.objects.new(f"{pid}_pivot", None)
        bpy.context.scene.collection.objects.link(pivot)
        hat_parts = []
        bpy.ops.mesh.primitive_torus_add(major_radius=w * 0.42, minor_radius=w * 0.1, location=(0, 0, w * 0.1))
        B._finish(bpy.context.object, 0, fur); bpy.ops.object.shade_smooth(); hat_parts.append(B.parts[-1])
        bpy.ops.mesh.primitive_cone_add(radius1=w * 0.42, radius2=0.012, depth=h, location=(0, 0, w * 0.1 + h / 2),
                                        vertices=32)
        B._finish(bpy.context.object, 0.005, red); bpy.ops.object.shade_smooth(); hat_parts.append(B.parts[-1])
        hat_parts.append(B.sphere(w * 0.12, (0, 0, w * 0.1 + h + 0.01), mat=fur))
        for o in hat_parts:
            o.parent = pivot
        # lying down: rest on the brim's side, tip pointing sideways and a little up
        pivot.rotation_euler = (math.radians(78), 0, 0)
        pivot.location = (0, 0, w * 0.5)
        B.parts.append(pivot)
    elif kind == "sofa":
        B.box((w, d, 0.42), (0, 0, 0.21), bevel=0.04)
        B.box((w, 0.2, h - 0.42), (0, d / 2 - 0.1, 0.42 + (h - 0.42) / 2), bevel=0.05)
        for sx in (-1, 1):
            B.box((0.18, d, 0.62), (sx * (w / 2 - 0.09), 0, 0.31), bevel=0.05)
        for i in range(2):
            B.box(((w - 0.36) / 2 - 0.02, d - 0.25, 0.14), ((i - 0.5) * (w - 0.36) / 2, -0.08, 0.49), bevel=0.05)
    elif kind == "bed":
        B.box((w + 0.06, d + 0.06, 0.3), (0, 0, 0.15), bevel=0.02)
        B.box((w, d, 0.22), (0, 0, 0.41), bevel=0.06, mat=material(f"{pid}_sheet", (0.9, 0.9, 0.88), "fabric"))
        B.box((w + 0.06, 0.08, 1.0), (0, d / 2 + 0.04, 0.5), bevel=0.02)
        for sx in (-1, 1):
            B.box((w * 0.4, 0.4, 0.12), (sx * w * 0.24, d / 2 - 0.3, 0.57), bevel=0.05,
                  mat=material(f"{pid}_pillow", (0.95, 0.95, 0.95), "fabric"))
    elif kind == "shelf":
        t = 0.025
        for sx in (-1, 1):
            B.box((t, d, h), (sx * (w / 2 - t / 2), 0, h / 2))
        B.box((w, 0.01, h), (0, d / 2 - 0.005, h / 2))
        for k in range(5):
            B.box((w - 2 * t, d, t), (0, 0, 0.05 + k * (h - 0.08) / 4))
    elif kind == "counter":
        B.box((w, d, h - 0.04), (0, 0, (h - 0.04) / 2))
        B.box((w + 0.04, d + 0.04, 0.04), (0, 0, h - 0.02), mat=material(f"{pid}_top", (0.8, 0.8, 0.78), "stone"))
    elif kind == "door":
        # frame; the panel and knob turn on a hinge at the left edge; daylight shows through the
        # doorway when it opens; optional shop bell above it (on the room side, -Y)
        # "match_picture": the door in the set picture is re-used as this door's face (frame from the picture)
        match = bool(p.get("match_picture"))
        frame = [] if match else [B.box((w + 0.12, d + 0.02, 0.06), (0, 0, h + 0.03))]
        reveal = 0.35                     # wall thickness: the doorway is a short passage
        side_col = (0.05, 0.035, 0.025) if match else (0.35, 0.3, 0.27)   # inside of the doorway
        for sx in (-1, 1):
            if not match:
                frame.append(B.box((0.06, d + 0.02, h), (sx * (w / 2 + 0.03), 0, h / 2)))
            B.box((0.04, reveal, h), (sx * (w / 2 + 0.02), d / 2 + reveal / 2, h / 2), bevel=0,
                  mat=material(f"{pid}_reveal{sx}", side_col, "wood" if match else "stone"))
        B.box((w, reveal, 0.04), (0, d / 2 + reveal / 2, h + 0.02), bevel=0,
              mat=material(f"{pid}_lintel", side_col, "wood" if match else "stone"))
        outside = B.box((w, 0.01, h), (0, d / 2 + reveal, h / 2), bevel=0)
        sky = bpy.data.materials.new(f"{pid}_daylight")
        sky.use_nodes = True
        em = sky.node_tree.nodes.new("ShaderNodeEmission")
        # what shows through the open doorway: daylight by default, or e.g. "outside": "#1c2a44" for night
        em.inputs["Color"].default_value = (*hex_rgb(p["outside"]), 1) if p.get("outside") else (0.85, 0.9, 1.0, 1)
        em.inputs["Strength"].default_value = p.get("outside_strength", 1.6 if not p.get("outside") else 1.0)
        sky.node_tree.links.new(em.outputs[0], sky.node_tree.nodes["Material Output"].inputs["Surface"])
        outside.data.materials[0] = sky
        # looks like daylight but does not light the room (that made a white patch on the floor)
        outside.visible_diffuse = outside.visible_glossy = outside.visible_shadow = False
        hinge = bpy.data.objects.new(f"{pid}_hinge", None)
        bpy.context.scene.collection.objects.link(hinge)
        hinge.location = (-w / 2, 0, 0)
        B.parts.append(hinge)
        panel = B.box((w, d * 0.7, h), (0, 0, h / 2))
        knob = B.sphere(0.03, (w / 2 - 0.08, -d / 2 - 0.03, h * 0.48),
                        mat=material(f"{pid}_knob", (0.8, 0.7, 0.4), "metal"))
        for o in (panel, knob):
            o.location -= hinge.location
            o.parent = hinge
        bell_pivot = None
        if p.get("bell"):
            brass = material(f"{pid}_brass", (0.75, 0.55, 0.2), "metal")
            B.box((0.02, 0.12, 0.02), (w / 2 - 0.2, -d / 2 - 0.06, h + 0.0), mat=brass)
            bell_pivot = bpy.data.objects.new(f"{pid}_bell_pivot", None)
            bpy.context.scene.collection.objects.link(bell_pivot)
            bell_pivot.location = (w / 2 - 0.2, -d / 2 - 0.11, h - 0.01)
            B.parts.append(bell_pivot)
            bpy.ops.mesh.primitive_cone_add(radius1=0.035, radius2=0.012, depth=0.05, location=(0, 0, -0.035))
            bell = bpy.context.object
            B._finish(bell, 0.003, brass)
            bell.parent = bell_pivot
        DOORS[pid] = {"hinge": hinge, "bell": bell_pivot, "width": w, "height": h, "depth": d,
                      "panel": [panel, knob], "match": match, "rect": p.get("picture_rect")}
    elif kind == "wall":
        B.box((w, d, h), (0, 0, h / 2), bevel=0.0)
    elif kind == "window":
        sill = p.get("sill", 0.9)
        frame = material(f"{pid}_frame", hex_rgb(p.get("frame_color", "#f2f2f2")), "wood")
        for sx in (-1, 1):
            B.box((0.06, d, h), (sx * (w / 2 - 0.03), 0, sill + h / 2), mat=frame)
        for z in (sill + 0.03, sill + h - 0.03):
            B.box((w, d, 0.06), (0, 0, z), mat=frame)
        B.box((w - 0.12, 0.01, h - 0.12), (0, 0, sill + h / 2), bevel=0.0)
    elif kind == "lamp":
        B.cyl(0.14, 0.03, (0, 0, 0.015), mat=dark)
        B.cyl(0.015, h - 0.3, (0, 0, (h - 0.3) / 2), mat=dark)
        shade = B.cyl(w / 2, 0.3, (0, 0, h - 0.15), mat=material(f"{pid}_shade", (0.95, 0.9, 0.8), "fabric"))
        light = bpy.data.objects.new(f"{pid}_light", bpy.data.lights.new(f"{pid}_light", "POINT"))
        light.data.energy, light.data.color, light.data.shadow_soft_size = 60, (1.0, 0.85, 0.65), 0.1
        light.location = (0, 0, h - 0.2)
        bpy.context.scene.collection.objects.link(light)
        B.parts.append(light)
    elif kind == "cup":
        B.cyl(w / 2, h, (0, 0, h / 2), verts=24)
        B.cyl(w / 2 - 0.004, 0.005, (0, 0, h - 0.004), bevel=0, mat=material(f"{pid}_coffee", (0.12, 0.06, 0.03), "plastic"))
        bpy.ops.mesh.primitive_torus_add(major_radius=h * 0.28, minor_radius=0.006, location=(w / 2 + h * 0.18, 0, h * 0.55),
                                         rotation=(math.pi / 2, 0, 0))
        o = bpy.context.object
        B._finish(o, 0, None)
    elif kind == "plant":
        B.cyl(w * 0.3, h * 0.3, (0, 0, h * 0.15), mat=mat)
        green = material(f"{pid}_leaves", (0.08, 0.25, 0.06), "plastic")
        for k in range(7):
            a = k * 2.4
            r = w * 0.18 * (k % 3) / 2
            B.sphere(w * 0.22, (math.cos(a) * r, math.sin(a) * r, h * (0.5 + 0.07 * k)), mat=green,
                     scale=(1, 1, 0.8))
    elif kind == "tv":
        B.box((w * 0.5, d, 0.5), (0, 0, 0.25), mat=mat)
        B.box((w, 0.05, w * 0.58), (0, 0, 0.5 + w * 0.29 + 0.05), mat=dark)
    else:   # "box" and anything unknown: a simple bevelled box so the scene still builds
        B.box((w, d, h), (0, 0, h / 2), bevel=0.02)

    root = bpy.data.objects.new(pid, None)
    bpy.context.scene.collection.objects.link(root)
    for o in B.parts:
        if o.parent is None:
            o.parent = root
    pos = stage_to_world(p.get("position", [0, 0]))
    base_z = tops.get(p.get("on"), 0.0) if p.get("on") else float(p.get("elevation", 0.0))
    root.location = (pos.x, pos.y, base_z)
    root.rotation_euler = (0, 0, math.radians(p.get("rotation", 0)))
    a = math.radians(p.get("rotation", 0))
    front = Vector((math.sin(a), -math.cos(a), 0))          # the side people use (local -Y)
    if pid in SEATS:
        SEATS[pid].update(centre=Vector((pos.x, pos.y, 0)), front=front, heading=a)
    if pid in DOORS:
        DOORS[pid].update(centre=Vector((pos.x, pos.y, 0)), front=front, heading=a)
    corners = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * w / 2, sy * d / 2
            corners.append(Vector((pos.x + x * math.cos(a) - y * math.sin(a), pos.y + x * math.sin(a) + y * math.cos(a), 0)))
    # things that stand on the floor block walking; a window hangs on a wall, a cup sits on something
    blocks = not p.get("on") and kind not in ("window", "cup", "santa_hat")
    return root, (corners if blocks else None), base_z + h
