"""Cast line-up: every character .blend in a folder, standing side by side, rendered front and back.

    blender -b -y -P lineup.py -- characters_folder out.png
"""
import glob
import math
import os
import sys

import bpy
from mathutils import Vector

folder, out = sys.argv[sys.argv.index("--") + 1:][:2]
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
files = sorted(glob.glob(os.path.join(folder, "*.blend")))
x = 0.0
names = []
for f in files:
    with bpy.data.libraries.load(f, link=False) as (src, dst):
        dst.objects = list(src.objects)
    objs = [o for o in dst.objects if o is not None]
    rig = next((o for o in objs if o.type == "ARMATURE" and o.name.startswith("CastForge_Rig")), None)
    if rig is None:
        continue
    for o in objs:
        if not o.name.startswith("WGT-") and (o.type != "ARMATURE" or o is rig):
            scene.collection.objects.link(o)
    rig.location.x = x
    names.append((os.path.splitext(os.path.basename(f))[0], x))
    x += 1.1
w = max(x - 1.1, 0.1)
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x, scene.render.resolution_y = 1800, 700
world = bpy.data.worlds.new("W"); scene.world = world; world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.82, 0.83, 0.85, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.7
for rot, e in (((0.9, 0, 0.4), 3.0), ((1.2, 0, 3.5), 1.5)):
    s = bpy.data.objects.new("S", bpy.data.lights.new("S", "SUN")); s.data.energy = e; s.rotation_euler = rot
    scene.collection.objects.link(s)
cam = bpy.data.objects.new("C", bpy.data.cameras.new("C")); scene.collection.objects.link(cam); scene.camera = cam
cam.data.type = "ORTHO"; cam.data.ortho_scale = max(w + 1.2, 2.2 * 1800 / 700 / 2.2)
for tag, ang in (("front", 0), ("back", 180)):
    a = math.radians(ang)
    cam.location = (w / 2 + 0, -8 * math.cos(a), 0.95)
    cam.rotation_euler = (math.pi / 2, 0, a)
    scene.render.filepath = out.replace(".png", f"_{tag}.png")
    bpy.ops.render.render(write_still=True)
print("LINEUP", names)
