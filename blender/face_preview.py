"""Render a front + three-quarter close-up of a built character's face.

    blender -b char.blend -P face_preview.py -- out_prefix
"""
import math
import sys

import bpy
import numpy as np

prefix = sys.argv[sys.argv.index("--") + 1]
body = bpy.data.objects["Body"]
deps = bpy.context.evaluated_depsgraph_get()
ev = body.evaluated_get(deps)
me = ev.to_mesh()
co = np.array([ev.matrix_world @ v.co for v in me.vertices])
ev.to_mesh_clear()
top = co[:, 2].max()
head = co[co[:, 2] > top - 0.25]
cx, zc = head[:, 0].mean(), top - 0.12

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = scene.render.resolution_y = 640
world = bpy.data.worlds.new("W"); scene.world = world; world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.85, 0.86, 0.88, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.7
sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
sun.data.energy = 2.5; sun.rotation_euler = (1.2, 0, 0.4)
scene.collection.objects.link(sun)
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
scene.collection.objects.link(cam); scene.camera = cam
cam.data.type = "ORTHO"; cam.data.ortho_scale = 0.32
for tag, ang in (("front", 0), ("three_quarter", 35)):
    a = math.radians(ang)
    cam.location = (cx + 2 * math.sin(a), -2 * math.cos(a), zc)
    cam.rotation_euler = (math.pi / 2, 0, a)
    scene.render.filepath = f"{prefix}_{tag}.png"
    bpy.ops.render.render(write_still=True)
print("CF: face previews", prefix)
