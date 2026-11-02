"""Pictures of every prop type: the app's prop catalogue, and a quick check of the props after a change.

    blender -b --factory-startup -P blender/catalog.py -- OUT_DIR [--types table,chair,...]

writes OUT_DIR/<type>.png (256 x 256, one prop each, three-quarter view on a neutral floor).
"""
import math
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from core import schema  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
out_dir = os.path.abspath(argv[0] if argv else "prop_catalog")
types = argv[argv.index("--types") + 1].split(",") if "--types" in argv else \
    [t for t in schema.PROP_TYPES if t not in ("picture_road", "seat")]
os.makedirs(out_dir, exist_ok=True)

for kind in types:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    import props                                         # fresh DOORS/SEATS/FLAMES for every picture
    for registry in (props.DOORS, props.SEATS):
        registry.clear()
    props.FLAMES.clear()
    scene = bpy.context.scene
    props.build({"id": kind, "make": kind, "position": [0, 0], "rotation": 25}, 0,
                lambda p: Vector((p[0], p[1], 0)), {})
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in scene.objects if o.type == "MESH" and not o.hide_render
           for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    centre, radius = (lo + hi) / 2, max((hi - lo).length / 2, 0.05)
    bpy.ops.mesh.primitive_plane_add(size=max(radius * 8, 2), location=(centre.x, centre.y, 0))
    floor = bpy.context.object
    m = bpy.data.materials.new("floor")
    m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.32, 0.31, 0.3, 1)
    floor.data.materials.append(m)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.lens = 50
    cam.location = centre + Vector((0.55, -1.0, 0.45)).normalized() * radius * 4.2
    cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(45), 0, math.radians(-30))
    scene.collection.objects.link(sun)
    world = bpy.data.worlds.new("w")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.6
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 16
    scene.render.resolution_x = scene.render.resolution_y = 256
    scene.view_settings.view_transform = "Standard"
    scene.render.filepath = os.path.join(out_dir, f"{kind}.png")
    bpy.ops.render.render(write_still=True)
    print("CF: catalogue", kind, flush=True)
