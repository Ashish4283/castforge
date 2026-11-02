"""CastForge prop factory: build solid 3D props from a short description (no model files needed).

    {"id": "t1", "make": "table", "shape": "round", "size": [0.8, 0.8, 0.75], "color": "#6b4423",
     "material": "wood", "position": [0.2, 0.9], "rotation": 0}
    {"id": "c1", "make": "cup", "on": "t1", "position": [0.25, 0.9], "color": "#ffffff", "material": "ceramic"}

size is [width, depth, height] in metres (each type has sensible defaults). Everything is built from
bevelled primitives so it renders well in EEVEE, and every prop reports its floor footprint so walks
route around it.
"""
import math
import random

import bpy
from mathutils import Vector

from core import schema

MATERIALS = schema.MATERIALS                    # roughness, metallic, transmission, sheen, coat
DEFAULT_SIZE = {k: v[0] for k, v in schema.PROP_TYPES.items() if v[0]}
DEFAULT_MATERIAL = {k: v[1] for k, v in schema.PROP_TYPES.items() if v[1]}
DOORS = {}       # id -> hinge, bell pivot, size (for the "enter" action)
SEATS = {}       # id -> seat height (for "sit"); position/facing are added once placed
STEERING_WHEELS = {}  # prop id -> animated steering pivot
FLAMES = []      # fire and candle lights, flickered by world.flicker once the scene length is known


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


def image_emission(name, filepath):
    image = bpy.data.images.load(filepath, check_existing=True)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.node_tree.nodes.clear()
    output = m.node_tree.nodes.new("ShaderNodeOutputMaterial")
    texture = m.node_tree.nodes.new("ShaderNodeTexImage")
    texture.image = image
    texture.extension = "EXTEND"
    emission = m.node_tree.nodes.new("ShaderNodeEmission")
    m.node_tree.links.new(texture.outputs["Color"], emission.inputs["Color"])
    m.node_tree.links.new(emission.outputs[0], output.inputs["Surface"])
    return m


def update_attached_doors():
    bpy.context.view_layer.update()
    for door in DOORS.values():
        root = door.get("attachment_root")
        if root is None:
            continue
        transform = root.matrix_world
        centre = transform @ door["local_centre"]
        front = transform.to_3x3() @ door["local_front"]
        across = transform.to_3x3() @ door["local_across"]
        front.z = across.z = 0
        front.normalize()
        across.normalize()
        door.update(centre=centre, front=front, across=across, heading=math.atan2(front.x, -front.y))


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

    def cone(self, r1, r2, h, loc, mat=None, verts=32, rot=(0, 0, 0)):
        bpy.ops.mesh.primitive_cone_add(radius1=r1, radius2=r2, depth=h, location=loc, vertices=verts, rotation=rot)
        o = bpy.context.object
        self._finish(o, 0, mat)
        bpy.ops.object.shade_smooth()
        return o

    def torus(self, major, minor, loc, mat=None, rot=(0, 0, 0)):
        bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, location=loc, rotation=rot)
        o = bpy.context.object
        self._finish(o, 0, mat)
        bpy.ops.object.shade_smooth()
        return o

    def plane(self, size, loc, mat=None, rot=(0, 0, 0)):
        bpy.ops.mesh.primitive_plane_add(size=1, location=loc, rotation=rot)
        o = bpy.context.object
        o.scale = (size[0], size[1], 1)
        self._finish(o, 0, mat)
        return o

    def light(self, name, loc, energy, colour, radius=0.05, flame=False):
        light = bpy.data.objects.new(name, bpy.data.lights.new(name, "POINT"))
        light.data.energy, light.data.color, light.data.shadow_soft_size = energy, colour, radius
        light.location = loc
        bpy.context.scene.collection.objects.link(light)
        self.parts.append(light)
        if flame:
            FLAMES.append(light)
        return light

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

    if kind in schema.SEAT_TYPES:
        seat_h = {"chair": min(0.46, h * 0.5), "sofa": 0.48, "armchair": 0.48}.get(kind, h)
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
        if p.get("outside_image"):
            outside.data.materials.clear()
            outside.data.materials.append(image_emission(f"{pid}_outside", p["outside_image"]))
            uv_layer = outside.data.uv_layers.active
            u0, v0, u1, v1 = p.get("outside_rect", (0.0, 0.0, 1.0, 1.0))
            for loop in outside.data.loops:
                co = outside.data.vertices[loop.vertex_index].co
                u = (co.x / w + 0.5) * (u1 - u0) + u0
                v = (co.z / h + 0.5) * (v1 - v0) + v0
                uv_layer.data[loop.index].uv = (u, 1.0 - v)
    elif kind == "pickup_truck":
        paint = material(f"{pid}_paint", hex_rgb(p.get("color", "#8d2527")), "metal")
        glass = material(f"{pid}_glass", hex_rgb("#607987"), "glass")
        rubber = material(f"{pid}_rubber", hex_rgb("#17191b"), "rubber")
        chrome = material(f"{pid}_chrome", hex_rgb("#aab0b2"), "metal")
        cabin = material(f"{pid}_cabin", hex_rgb("#24282a"), "leather")
        wheel_r = min(0.39, h * 0.22)
        wheel_z = wheel_r + 0.08
        cab_w, cab_len = w * 0.9, d * 0.36
        cab_front, cab_back = -d * 0.25, d * 0.11
        bed_len = d * 0.32

        B.box((w * 0.84, d * 0.82, 0.28), (0, 0, wheel_z + 0.08), bevel=0.05, mat=dark)
        B.box((w * 0.96, d * 0.30, 0.38), (0, -d * 0.34, wheel_z + 0.27), bevel=0.05, mat=paint)
        B.box((w * 0.92, d * 0.26, 0.39), (0, d * 0.34, wheel_z + 0.28), bevel=0.04, mat=paint)
        B.box((w * 0.82, bed_len, 0.06), (0, d * 0.34, wheel_z + 0.47), bevel=0.01, mat=dark)
        for sx in (-1, 1):
            B.box((0.07, bed_len, 0.48), (sx * w * 0.44, d * 0.34, wheel_z + 0.72), bevel=0.025, mat=paint)
            B.box((0.07, cab_len, 0.47), (sx * w * 0.45, (cab_front + cab_back) / 2, wheel_z + 0.78),
                  bevel=0.02, mat=paint)
        B.box((cab_w, cab_len, 0.14), (0, (cab_front + cab_back) / 2, wheel_z + 1.07), bevel=0.04, mat=paint)
        B.box((w * 0.88, 0.07, 0.46), (0, d * 0.34 + bed_len / 2, wheel_z + 0.72), bevel=0.02, mat=paint)
        B.box((w * 0.88, 0.07, 0.46), (0, d * 0.34 - bed_len / 2, wheel_z + 0.72), bevel=0.02, mat=paint)

        for side in (-1, 1):
            for axle_y in (-d * 0.31, d * 0.32):
                wheel_x = side * w * 0.47
                B.torus(wheel_r * 0.72, wheel_r * 0.25, (wheel_x, axle_y, wheel_z), mat=rubber,
                        rot=(0, math.pi / 2, 0))
                B.cyl(wheel_r * 0.43, 0.045, (wheel_x + side * 0.012, axle_y, wheel_z), mat=chrome,
                      rot=(0, math.pi / 2, 0))

        B.box((w * 0.68, 0.035, 0.19), (0, -d * 0.495, wheel_z + 0.25), bevel=0.015, mat=chrome)
        for sx in (-1, 1):
            B.box((w * 0.16, 0.025, 0.12), (sx * w * 0.33, -d * 0.50, wheel_z + 0.49), bevel=0.025,
                  mat=material(f"{pid}_headlight{sx}", hex_rgb("#e6d9a8"), "ceramic"))
            B.box((0.1, 0.04, 0.12), (sx * w * 0.35, d * 0.495, wheel_z + 0.48), bevel=0.015,
                  mat=material(f"{pid}_taillight{sx}", hex_rgb("#8d2023"), "plastic"))

        windshield = B.box((cab_w * 0.9, 0.035, 0.42), (0, cab_front - 0.01, wheel_z + 0.83), bevel=0.01, mat=glass,
                          rot=(-0.16, 0, 0))
        windshield.visible_shadow = False
        rear_glass = B.box((cab_w * 0.82, 0.025, 0.35), (0, cab_back + 0.01, wheel_z + 0.84), bevel=0.01, mat=glass)
        rear_glass.visible_shadow = False
        for sx in (-1, 1):
            side_window = B.box((0.018, cab_len * 0.73, 0.34), (sx * w * 0.449, (cab_front + cab_back) / 2,
                                                                    wheel_z + 0.83), bevel=0.006, mat=glass)
            side_window.visible_shadow = False

        # A visible cab is built behind the operable driver door, rather than a hollow photo cutout.
        B.box((cab_w * 0.92, 0.58, 0.16), (0, -0.02, wheel_z + 0.47), bevel=0.025, mat=cabin)
        for sx in (-1, 1):
            B.box((0.46, 0.42, 0.46), (sx * 0.43, 0.02, wheel_z + 0.78), bevel=0.05, mat=cabin)
            B.box((0.48, 0.11, 0.12), (sx * 0.43, -0.20, wheel_z + 0.98), bevel=0.04, mat=cabin)
        dashboard = material(f"{pid}_dashboard", hex_rgb("#292b2d"), "plastic")
        B.box((cab_w * 0.94, 0.23, 0.32), (0, cab_front + 0.10, wheel_z + 0.77), bevel=0.035, mat=dashboard)
        B.box((0.22, 0.02, 0.12), (0, cab_front + 0.055, wheel_z + 0.78), bevel=0.01,
              mat=material(f"{pid}_radio_screen", hex_rgb("#1a2930"), "plastic"))
        for knob_x in (-0.17, 0.17):
            B.cyl(0.025, 0.035, (knob_x, cab_front + 0.035, wheel_z + 0.78), mat=chrome, rot=(math.pi / 2, 0, 0))

        wheel_pivot = bpy.data.objects.new(f"{pid}_steering_pivot", None)
        bpy.context.scene.collection.objects.link(wheel_pivot)
        wheel_loc = (0.34, cab_front + 0.12, wheel_z + 0.96)
        wheel_pivot.location = wheel_loc
        wheel = B.torus(0.20, 0.027, wheel_loc, mat=cabin, rot=(math.pi / 2, 0, 0))
        hub = B.sphere(0.055, (wheel_loc[0], wheel_loc[1] - 0.02, wheel_loc[2]), mat=dashboard)
        spokes = [
            B.box((0.025, 0.025, 0.18), (wheel_loc[0], wheel_loc[1] - 0.015, wheel_loc[2])),
            B.box((0.16, 0.025, 0.025), (wheel_loc[0], wheel_loc[1] - 0.015, wheel_loc[2])),
        ]
        for part in [wheel, hub, *spokes]:
            part.location -= Vector(wheel_loc)
            part.parent = wheel_pivot
        B.parts.append(wheel_pivot)
        STEERING_WHEELS[pid] = wheel_pivot

        door_id = p.get("door_id")
        door_hinge = None
        if door_id:
            door_hinge = bpy.data.objects.new(f"{pid}_driver_hinge", None)
            bpy.context.scene.collection.objects.link(door_hinge)
            door_hinge.location = (w * 0.47, cab_front + 0.12, wheel_z + 0.47)
            door_parts = [
                B.box((0.055, cab_len * 0.58, 0.38), (w * 0.47, cab_front + cab_len * 0.38, wheel_z + 0.70),
                      bevel=0.018, mat=paint),
                B.box((0.025, cab_len * 0.49, 0.29), (w * 0.47, cab_front + cab_len * 0.38, wheel_z + 1.04),
                      bevel=0.008, mat=glass),
                B.box((0.035, 0.11, 0.025), (w * 0.49, cab_front + cab_len * 0.43, wheel_z + 0.77),
                      bevel=0.008, mat=chrome),
            ]
            for part in door_parts:
                part.location -= door_hinge.location
                part.parent = door_hinge
            B.parts.append(door_hinge)
            DOORS[door_id] = {
                "hinge": door_hinge, "bell": None, "width": cab_len * 0.58, "height": 0.67, "depth": 0.055,
                "panel": door_parts, "match": False, "rect": None,
                "owner_id": pid,
                "local_centre": Vector((w * 0.47, cab_front + cab_len * 0.38, wheel_z + 0.78)),
                "local_front": Vector((1, 0, 0)), "local_across": Vector((0, 1, 0)),
            }
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
    elif kind == "steering_wheel":
        leather = material(f"{pid}_leather", hex_rgb(p.get("color", "#202020")), "leather")
        hub_mat = material(f"{pid}_hub", hex_rgb("#34383a"), "plastic")
        pivot = bpy.data.objects.new(f"{pid}_pivot", None)
        bpy.context.scene.collection.objects.link(pivot)
        centre = (0, 0, h / 2)
        pivot.location = centre
        ring = B.torus(min(w, h) * 0.42, min(w, h) * 0.055, centre, mat=leather, rot=(math.pi / 2, 0, 0))
        hub = B.cyl(min(w, h) * 0.12, 0.045, (0, -0.02, h / 2), mat=hub_mat, rot=(math.pi / 2, 0, 0))
        spokes = [
            B.box((0.025, 0.025, h * 0.62), (0, 0, h / 2), bevel=0.006, mat=hub_mat),
            B.box((w * 0.55, 0.025, 0.025), (0, 0, h / 2), bevel=0.006, mat=hub_mat),
        ]
        for part in (ring, hub, *spokes):
            part.location -= Vector(centre)
            part.parent = pivot
        B.parts.append(pivot)
        STEERING_WHEELS[pid] = pivot
    elif kind == "car_radio":
        radio = material(f"{pid}_radio_body", hex_rgb(p.get("color", "#292d30")), "plastic")
        screen = material(f"{pid}_radio_screen", hex_rgb(p.get("screen_color", "#66817e")), "plastic")
        B.box((w, d, h), (0, 0, h / 2), bevel=0.018, mat=radio)
        B.box((w * 0.48, 0.012, h * 0.48), (0, -d / 2 - 0.006, h * 0.63), bevel=0.004,
              mat=material(f"{pid}_display", hex_rgb(p.get("screen_color", "#66817e")), "plastic"))
        for sx in (-1, 1):
            knob = B.cyl(h * 0.12, 0.025, (sx * w * 0.39, -d / 2 - 0.015, h * 0.62),
                         mat=material(f"{pid}_knob{sx}", hex_rgb("#94999a"), "metal"), rot=(math.pi / 2, 0, 0))
            knob.name = f"{pid}_knob{sx}"
        for i in range(5):
            B.box((w * 0.11, 0.018, h * 0.12), ((i - 2) * w * 0.14, -d / 2 - 0.012, h * 0.22),
                  bevel=0.003, mat=screen)
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
    elif build_more(kind, B, p, w, d, h, mat, dark, pid):
        pass
    else:   # "box" and anything unknown: a simple bevelled box so the scene still builds
        B.box((w, d, h), (0, 0, h / 2), bevel=0.02)

    root = bpy.data.objects.new(pid, None)
    bpy.context.scene.collection.objects.link(root)
    for o in B.parts:
        if o.parent is None:
            o.parent = root
    pos = stage_to_world(p.get("position", [0, 0]))
    hangs = 1.3 if kind == "picture_frame" else 0.0          # a picture hangs at eye level unless told otherwise
    base_z = tops.get(p.get("on"), 0.0) if p.get("on") else float(p.get("elevation", hangs))
    root.location = (pos.x, pos.y, base_z)
    root.rotation_euler = (0, 0, math.radians(p.get("rotation", 0)))
    a = math.radians(p.get("rotation", 0))
    front = Vector((math.sin(a), -math.cos(a), 0))          # the side people use (local -Y)
    if pid in SEATS:
        SEATS[pid].update(centre=Vector((pos.x, pos.y, 0)), front=front, heading=a)
    attached = [door for door in DOORS.values() if door.get("owner_id") == pid]
    for door in attached:
        door["attachment_root"] = root
    update_attached_doors()
    if pid in DOORS:
        door = DOORS[pid]
        if "local_centre" not in door:
            door.update(centre=Vector((pos.x, pos.y, 0)), front=front, heading=a)
    corners = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * w / 2, sy * d / 2
            corners.append(Vector((pos.x + x * math.cos(a) - y * math.sin(a), pos.y + x * math.sin(a) + y * math.cos(a), 0)))
    # things that stand on the floor block walking; a window hangs on a wall, a cup sits on something
    blocks = not p.get("on") and schema.PROP_TYPES.get(kind, (None, None, True))[2]
    return root, (corners if blocks else None), base_z + h


def glow(name, colour, strength):
    """A self-lit material: flames, fairy lights, screens."""
    m = material(name, colour, "plastic")
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Emission Color"].default_value = (*colour, 1)
    b.inputs["Emission Strength"].default_value = strength
    return m


BOOK_COLOURS = ["#7a2e2e", "#2e4a7a", "#3d6b3d", "#8a6d3b", "#5b3b6b", "#2f2f2f", "#a8834a"]
FLAME, FLAME_CORE = (1.0, 0.45, 0.08), (1.0, 0.78, 0.3)


def build_more(kind, B, p, w, d, h, mat, dark, pid):
    """The props added in v2 (same conventions as build: built around the origin, front towards -Y).
    Returns False for a type it does not know."""
    rng = random.Random(pid)                 # repeatable variety: book colours, ornaments
    if kind == "armchair":
        legs = 0.08
        B.box((w, d, 0.34), (0, 0, legs + 0.17), bevel=0.04)
        B.box((w, 0.18, h - legs - 0.3), (0, d / 2 - 0.09, legs + 0.3 + (h - legs - 0.3) / 2), bevel=0.05)
        for sx in (-1, 1):
            B.box((0.16, d, 0.6 - legs), (sx * (w / 2 - 0.08), 0, legs + (0.6 - legs) / 2), bevel=0.05)
            for sy in (-1, 1):
                B.cyl(0.025, legs, (sx * (w / 2 - 0.08), sy * (d / 2 - 0.08), legs / 2), mat=dark)
        B.box((w - 0.32, d - 0.22, 0.1), (0, -0.07, legs + 0.39), bevel=0.04)
    elif kind in ("christmas_tree", "pine_tree"):
        xmas = kind == "christmas_tree"
        green = material(f"{pid}_needles", hex_rgb(p.get("color", "#1f5130" if xmas else "#1d3b26")), "fabric")
        bark = material(f"{pid}_trunk", hex_rgb("#4a3020"), "wood")
        base = 0.3 if xmas else 0.6
        if xmas:
            B.cyl(w * 0.22, 0.2, (0, 0, 0.1), mat=material(f"{pid}_pot", hex_rgb("#7a2a1d"), "ceramic"))
        B.cyl(0.05 if xmas else 0.12, base + 0.1, (0, 0, (base + 0.1) / 2), mat=bark)
        tiers = 4 if xmas else 5
        foliage = h - base - (0.12 if xmas else 0.0)
        snow = material(f"{pid}_snow", (0.92, 0.94, 0.98), "snow") if p.get("snowy") else None
        cones = []
        for k in range(tiers):
            r = w / 2 * (1 - 0.8 * k / tiers)
            depth = foliage * 0.42
            z = base + k * foliage * (0.58 / (tiers - 1)) + depth / 2
            cones.append((r, depth, z))
            B.cone(r, 0.0, depth, (0, 0, z), mat=green)
            if snow:
                B.cone(r * 0.82, 0.0, depth * 0.55, (0, 0, z + depth * 0.25), mat=snow)
        if xmas:
            B.sphere(0.06, (0, 0, h - 0.06), mat=glow(f"{pid}_star", (1.0, 0.82, 0.35), 4.0))
            shades = [material(f"{pid}_ball{i}", hex_rgb(c), "metal")
                      for i, c in enumerate(("#b3261e", "#d4af37", "#2b5fa8", "#c0c0c0"))]
            bulb = glow(f"{pid}_bulb", (1.0, 0.85, 0.5), 12.0)
            for i in range(48):
                r, depth, z = cones[rng.randrange(tiers)]
                u = rng.uniform(0.1, 0.85)                    # height within the tier
                a = rng.uniform(0, 2 * math.pi)
                rr = r * (1 - u) + 0.01
                loc = (math.cos(a) * rr, math.sin(a) * rr, z - depth / 2 + u * depth)
                if i < 18:
                    B.sphere(0.035, loc, mat=shades[i % len(shades)])
                else:
                    B.sphere(0.012, loc, mat=bulb)
            B.light(f"{pid}_glow", (0, 0, h * 0.5), 15.0, (1.0, 0.8, 0.5), radius=0.4)
    elif kind == "fireplace":
        B.box((w, 0.12, h), (0, d / 2 - 0.06, h / 2), bevel=0.01)
        for sx in (-1, 1):
            B.box((0.28, d, h - 0.16), (sx * (w / 2 - 0.14), 0, (h - 0.16) / 2), bevel=0.01)
        B.box((w, d, 0.24), (0, 0, h - 0.16 - 0.12), bevel=0.01)
        B.box((w + 0.16, d + 0.12, 0.08), (0, -0.02, h - 0.04), mat=material(f"{pid}_mantel", hex_rgb("#4a3324"), "wood"))
        B.box((w + 0.2, d + 0.25, 0.06), (0, -0.08, 0.03))
        soot = material(f"{pid}_soot", (0.02, 0.018, 0.016), "stone")
        B.box((w - 0.56, 0.05, h - 0.42), (0, d / 2 - 0.14, (h - 0.42) / 2 + 0.06), bevel=0, mat=soot)
        logs = material(f"{pid}_logs", hex_rgb("#3b2516"), "wood")
        for x, z, a in ((-0.05, 0.12, 0.15), (0.06, 0.12, -0.2), (0.0, 0.2, 0.05)):
            B.cyl(0.05, w - 0.75, (x, 0.02, z), mat=logs, rot=(0, math.pi / 2, a))
        outer, core = glow(f"{pid}_flame", FLAME, 10.0), glow(f"{pid}_flame_core", FLAME_CORE, 14.0)
        for x, r, hh in ((-0.12, 0.09, 0.32), (0.0, 0.12, 0.42), (0.13, 0.08, 0.28)):
            B.cone(r, 0.0, hh, (x, 0.0, 0.2 + hh / 2), mat=outer)
            B.cone(r * 0.5, 0.0, hh * 0.6, (x, -0.02, 0.2 + hh * 0.3), mat=core)
        B.light(f"{pid}_fire", (0, -0.1, 0.45), 150.0, (1.0, 0.55, 0.25), radius=0.25, flame=True)
    elif kind == "lantern":
        metal = material(f"{pid}_metal", hex_rgb(p.get("color", "#2b2b2b")), "metal")
        B.cyl(w / 2, 0.03, (0, 0, 0.015), mat=metal)
        B.cyl(w / 2 * 0.8, h * 0.6, (0, 0, 0.03 + h * 0.3), mat=material(f"{pid}_glass", (0.9, 0.9, 0.85), "glass"))
        for a in range(4):
            ang = a * math.pi / 2 + math.pi / 4
            B.box((0.008, 0.008, h * 0.6), (math.cos(ang) * w * 0.4, math.sin(ang) * w * 0.4, 0.03 + h * 0.3),
                  bevel=0, mat=metal)
        B.cone(w / 2, w / 6, h * 0.2, (0, 0, 0.03 + h * 0.6 + h * 0.1), mat=metal)
        B.torus(w * 0.28, 0.006, (0, 0, h * 0.95), mat=metal, rot=(math.pi / 2, 0, 0))
        B.sphere(0.012, (0, 0, 0.03 + h * 0.25), mat=glow(f"{pid}_flame", FLAME_CORE, 25.0), scale=(1, 1, 2.4))
        B.light(f"{pid}_flame_light", (0, 0, 0.03 + h * 0.27), 20.0, (1.0, 0.62, 0.3), radius=0.02, flame=True)
    elif kind == "candle":
        B.cyl(w * 0.9, 0.012, (0, 0, 0.006), mat=material(f"{pid}_holder", hex_rgb("#b08d57"), "brass"))
        B.cyl(w / 2, h - 0.03, (0, 0, 0.012 + (h - 0.03) / 2),
              mat=material(f"{pid}_wax", hex_rgb(p.get("color", "#efe6d2")), "wax"))
        B.cyl(0.002, 0.012, (0, 0, h - 0.012), bevel=0, mat=dark)
        B.sphere(0.008, (0, 0, h + 0.012), mat=glow(f"{pid}_flame", FLAME_CORE, 30.0), scale=(1, 1, 2.5))
        B.light(f"{pid}_flame_light", (0, 0, h + 0.02), 4.0, (1.0, 0.6, 0.28), radius=0.01, flame=True)
    elif kind == "gift":
        wrap = material(f"{pid}_wrap", hex_rgb(p.get("color", "#b3261e")), "paper")
        ribbon = material(f"{pid}_ribbon", hex_rgb(p.get("ribbon", "#d4af37")), "plastic")
        B.box((w, d, h), (0, 0, h / 2), bevel=0.005, mat=wrap)
        B.box((w + 0.004, 0.04, h + 0.004), (0, 0, h / 2), bevel=0, mat=ribbon)
        B.box((0.04, d + 0.004, h + 0.004), (0, 0, h / 2), bevel=0, mat=ribbon)
        for a in (-0.5, 0.5):
            B.torus(0.05, 0.012, (0.04 * math.copysign(1, a), 0, h + 0.03), mat=ribbon, rot=(math.pi / 2, a, 0))
    elif kind == "sack":
        cloth = material(f"{pid}_cloth", hex_rgb(p.get("color", "#8b6b4a")), "fabric")
        B.sphere(1.0, (0, 0, h * 0.42), mat=cloth, scale=(w / 2, d / 2, h * 0.42))
        B.cyl(w * 0.12, 0.08, (0, 0, h * 0.86), mat=cloth)
        B.torus(w * 0.12, 0.012, (0, 0, h * 0.86), mat=material(f"{pid}_rope", hex_rgb("#c9a86a"), "fabric"))
        B.cone(w * 0.08, w * 0.2, 0.12, (0, 0, h * 0.95), mat=cloth)
    elif kind == "crowbar":
        steel = material(f"{pid}_steel", hex_rgb(p.get("color", "#2a2a2a")), "metal")
        r = 0.011
        B.cyl(r, d, (0, 0, r), mat=steel, rot=(math.pi / 2, 0, 0))
        B.cyl(r, 0.12, (0, d / 2 + 0.035, r + 0.045), mat=steel, rot=(math.pi / 2 - 0.9, 0, 0))
        B.box((0.03, 0.05, 0.008), (0, d / 2 + 0.06, r + 0.1), bevel=0, mat=steel, rot=(0.6, 0, 0))
        B.box((0.025, 0.05, 0.006), (0, -d / 2 - 0.02, r * 0.6), bevel=0, mat=steel, rot=(-0.2, 0, 0))
    elif kind == "cash_register":
        body = material(f"{pid}_body", hex_rgb(p.get("color", "#3a3d42")), "plastic")
        light_grey = material(f"{pid}_keys", (0.55, 0.55, 0.55), "plastic")
        B.box((w, d, 0.12), (0, 0, 0.06), bevel=0.01, mat=body)
        B.box((w * 0.9, 0.01, 0.06), (0, -d / 2, 0.06), bevel=0, mat=light_grey)
        B.box((w * 0.9, d * 0.5, 0.12), (0, d * 0.22, 0.18), bevel=0.01, mat=body)
        B.box((w * 0.8, d * 0.38, 0.03), (0, -d * 0.18, 0.14), bevel=0.004, mat=light_grey, rot=(0.35, 0, 0))
        B.cyl(0.015, 0.08, (0, d * 0.3, h - 0.04), mat=body)
        B.box((0.16, 0.03, 0.06), (0, d * 0.3, h), bevel=0.004, mat=body)
        B.box((0.13, 0.004, 0.04), (0, d * 0.3 - 0.016, h), bevel=0, mat=glow(f"{pid}_display", (0.3, 1.0, 0.45), 2.0))
    elif kind == "riser":
        B.box((w, d, h), (0, 0, h / 2), bevel=0.01)
        B.box((w - 0.04, d - 0.04, 0.01), (0, 0, h + 0.005), bevel=0,
              mat=material(f"{pid}_carpet", hex_rgb(p.get("carpet", "#7b1e22")), "fabric"))
        B.box((w * 0.4, 0.3, h * 0.5), (0, -d / 2 - 0.15, h * 0.25), bevel=0.01)
    elif kind == "rug":
        B.box((w, d, 0.008), (0, 0, 0.004), bevel=0,
              mat=material(f"{pid}_border", hex_rgb(p.get("border", "#3b2a20")), "fabric"))
        B.box((w - 0.16, d - 0.16, 0.01), (0, 0, 0.005), bevel=0,
              mat=material(f"{pid}_field", hex_rgb(p.get("color", "#7b2d26")), "fabric"))
    elif kind == "bookshelf":
        t = 0.025
        for sx in (-1, 1):
            B.box((t, d, h), (sx * (w / 2 - t / 2), 0, h / 2))
        B.box((w, 0.01, h), (0, d / 2 - 0.005, h / 2))
        boards = [0.05 + k * (h - 0.08) / 4 for k in range(5)]
        for z in boards:
            B.box((w - 2 * t, d, t), (0, 0, z))
        covers = [material(f"{pid}_book{i}", hex_rgb(c), "paper") for i, c in enumerate(BOOK_COLOURS)]
        for z0, z1 in zip(boards, boards[1:]):
            x = -w / 2 + t + 0.01
            while x < w / 2 - t - 0.05:
                bw = rng.uniform(0.02, 0.045)
                if rng.random() < 0.12:                      # a gap now and then
                    x += bw * 2
                    continue
                bh = min(rng.uniform(0.17, 0.26), z1 - z0 - t - 0.02)
                B.box((bw, d * 0.8, bh), (x + bw / 2, -0.01, z0 + t / 2 + bh / 2), bevel=0, mat=rng.choice(covers))
                x += bw + 0.002
    elif kind == "picture_frame":
        frame = material(f"{pid}_frame", hex_rgb(p.get("frame_color", "#8a6a3a")), "wood")
        for sx in (-1, 1):
            B.box((0.05, d, h), (sx * (w / 2 - 0.025), 0, h / 2), bevel=0.004, mat=frame)
        for z in (0.025, h - 0.025):
            B.box((w, d, 0.05), (0, 0, z), bevel=0.004, mat=frame)
        canvas = material(f"{pid}_canvas", hex_rgb(p.get("color2", "#5c7287")), "paper")
        if p.get("image"):
            nt = canvas.node_tree
            tex = nt.nodes.new("ShaderNodeTexImage")
            tex.image = bpy.data.images.load(p["image"])
            nt.links.new(tex.outputs["Color"], nt.nodes["Principled BSDF"].inputs["Base Color"])
        B.plane((w - 0.1, h - 0.1), (0, -d / 2 + 0.006, h / 2), mat=canvas, rot=(math.pi / 2, 0, 0))
    elif kind == "desk":
        B.box((w, d, 0.04), (0, 0, h - 0.02))
        ped = 0.4
        B.box((ped, d - 0.04, h - 0.04), (w / 2 - ped / 2, 0, (h - 0.04) / 2))
        handle = material(f"{pid}_handle", (0.7, 0.7, 0.7), "metal")
        for k in range(3):
            zc = 0.06 + (k + 0.5) * (h - 0.12) / 3
            B.box((ped - 0.04, 0.01, (h - 0.12) / 3 - 0.02), (w / 2 - ped / 2, -d / 2 + 0.015, zc), bevel=0.003)
            B.box((0.1, 0.015, 0.012), (w / 2 - ped / 2, -d / 2 + 0.005, zc + 0.03), bevel=0, mat=handle)
        for sy in (-1, 1):
            B.box((0.04, 0.04, h - 0.04), (-w / 2 + 0.03, sy * (d / 2 - 0.03), (h - 0.04) / 2))
    elif kind == "laptop":
        alu = material(f"{pid}_alu", hex_rgb(p.get("color", "#b8bcc2")), "metal")
        B.box((w, d, 0.018), (0, 0, 0.009), bevel=0.003, mat=alu)
        lean = math.radians(15)
        hinge = Vector((0, d / 2, 0.018))
        centre = hinge + Vector((0, math.sin(lean), math.cos(lean))) * (d / 2)
        B.box((w, 0.008, d), tuple(centre), bevel=0.002, mat=alu, rot=(-lean, 0, 0))
        normal = Vector((0, -math.cos(lean), math.sin(lean)))
        B.plane((w * 0.92, d * 0.88), tuple(centre + normal * 0.0045), mat=glow(f"{pid}_screen", (0.75, 0.85, 1.0), 1.5),
                rot=(math.pi / 2 - lean, 0, 0))
    elif kind == "phone":
        B.box((w, d, h), (0, 0, h / 2), bevel=0.004, mat=material(f"{pid}_case", (0.03, 0.03, 0.035), "plastic"))
        B.plane((w * 0.9, d * 0.92), (0, 0, h + 0.0005), mat=glow(f"{pid}_screen", (0.25, 0.35, 0.6), 0.6))
    elif kind == "bottle":
        glass = material(f"{pid}_glass", hex_rgb(p.get("color", "#2f5d3a")), "glass")
        B.cyl(w / 2, h * 0.62, (0, 0, h * 0.31), mat=glass)
        B.cone(w / 2, w * 0.16, h * 0.15, (0, 0, h * 0.62 + h * 0.075), mat=glass)
        B.cyl(w * 0.16, h * 0.2, (0, 0, h * 0.77 + h * 0.1), mat=glass)
        B.cyl(w * 0.18, h * 0.04, (0, 0, h * 0.98), mat=material(f"{pid}_cap", (0.6, 0.55, 0.45), "metal"))
    elif kind == "book":
        cover = material(f"{pid}_cover", hex_rgb(p.get("color", "#7a2e2e")), "paper")
        for z in (0.002, h - 0.002):
            B.box((w, d, 0.004), (0, 0, z), bevel=0, mat=cover)
        B.box((0.006, d, h), (-w / 2 + 0.003, 0, h / 2), bevel=0, mat=cover)
        B.box((w - 0.01, d - 0.008, h - 0.008), (0.002, 0, h / 2), bevel=0,
              mat=material(f"{pid}_pages", hex_rgb("#efe8d8"), "paper"))
    elif kind == "snowman":
        k = h / 1.6
        snow = material(f"{pid}_snow", (0.92, 0.94, 0.98), "snow")
        coal = material(f"{pid}_coal", (0.02, 0.02, 0.02), "stone")
        r1, r2, r3 = 0.4 * k, 0.29 * k, 0.2 * k
        z1 = r1 * 0.9
        z2 = z1 + r1 * 0.85 + r2 * 0.75
        z3 = z2 + r2 * 0.85 + r3 * 0.8
        for r, z in ((r1, z1), (r2, z2), (r3, z3)):
            B.sphere(r, (0, 0, z), mat=snow)
        for sx in (-1, 1):
            B.sphere(0.02 * k, (sx * 0.07 * k, -r3 * 0.9, z3 + 0.05 * k), mat=coal)
        B.cone(0.025 * k, 0.0, 0.12 * k, (0, -r3 - 0.05 * k, z3), rot=(math.pi / 2, 0, 0),
               mat=material(f"{pid}_carrot", hex_rgb("#e0701f"), "plastic"))
        for i in range(3):
            B.sphere(0.022 * k, (0, -r2 * 0.97, z2 - r2 * 0.45 + i * r2 * 0.35), mat=coal)
        B.torus(r2 * 0.72, 0.04 * k, (0, 0, z2 + r2 * 0.8),
                mat=material(f"{pid}_scarf", hex_rgb(p.get("color", "#b3261e")), "fabric"))
        B.cyl(0.17 * k, 0.015 * k, (0, 0, z3 + r3 * 0.85), mat=coal)
        B.cyl(0.11 * k, 0.18 * k, (0, 0, z3 + r3 * 0.85 + 0.09 * k), mat=coal)
        twig = material(f"{pid}_twig", hex_rgb("#4a3020"), "wood")
        for sx in (-1, 1):
            B.cyl(0.012 * k, 0.5 * k, (sx * (r2 + 0.18 * k), 0, z2 + 0.12 * k), mat=twig, rot=(0, sx * 1.05, 0))
    elif kind == "street_lamp":
        B.cyl(0.15, 0.3, (0, 0, 0.15), mat=dark)
        B.cyl(0.05, h - 0.3, (0, 0, 0.3 + (h - 0.3) / 2), mat=dark)
        B.box((0.28, 0.28, 0.32), (0, 0, h + 0.1), bevel=0.01, mat=glow(f"{pid}_lamp", (1.0, 0.85, 0.6), 4.0))
        B.cone(0.24, 0.03, 0.15, (0, 0, h + 0.33), mat=dark)
        B.light(f"{pid}_light", (0, 0, h + 0.05), 400.0, (1.0, 0.78, 0.5), radius=0.1)
    elif kind == "crate":
        B.box((w - 0.02, d - 0.02, h - 0.02), (0, 0, h / 2), bevel=0.005)
        beam = material(f"{pid}_beam", hex_rgb("#5c4027"), "wood")
        b = 0.05
        for sx in (-1, 1):
            for sy in (-1, 1):
                B.box((b, b, h), (sx * (w / 2 - b / 2), sy * (d / 2 - b / 2), h / 2), bevel=0.004, mat=beam)
            for z in (b / 2, h - b / 2):
                B.box((b, d, b), (sx * (w / 2 - b / 2), 0, z), bevel=0.004, mat=beam)
                B.box((w, b, b), (0, sx * (d / 2 - b / 2), z), bevel=0.004, mat=beam)
    elif kind == "barrel":
        B.cyl(w / 2 * 0.95, h, (0, 0, h / 2))
        hoop = material(f"{pid}_hoop", (0.15, 0.15, 0.16), "metal")
        for z in (h * 0.2, h * 0.8):
            B.torus(w / 2 * 0.96, 0.012, (0, 0, z), mat=hoop)
        B.cyl(w / 2 * 0.88, 0.01, (0, 0, h + 0.002), mat=material(f"{pid}_lid", hex_rgb("#4a3324"), "wood"))
    else:
        return False
    return True
