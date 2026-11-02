"""Check a built character really animates: pose rig controls + open the mouth on a viseme, render.

    blender -b char.blend -P pose_test.py -- --out posed.png
"""
import math
import sys

import bpy

out = sys.argv[sys.argv.index("--") + 1:][1]
rig = bpy.data.objects["CastForge_Rig"]
body = bpy.data.objects["Body"]
pb = rig.pose.bones
for b in pb:
    if "IK_FK" in b.keys():
        b["IK_FK"] = 1.0
POSE = {"upper_arm_fk.L": (0, 0, -1.2), "forearm_fk.L": (0, 0, -1.3), "upper_arm_fk.R": (0.9, 0, 0),
        "thigh_fk.R": (-1.0, 0, 0), "shin_fk.R": (1.4, 0, 0), "head": (0, 0.35, 0.15), "chest": (0, 0.2, 0)}
for name, rot in POSE.items():
    p = pb.get(name)
    if p is None:
        print("CF: missing control", name)
        continue
    p.rotation_mode = "XYZ"
    p.rotation_euler = rot
keys = body.data.shape_keys.key_blocks
keys["viseme_aa"].value = 1.0
keys["eyeBlinkLeft"].value = 1.0 if "eyeBlinkLeft" in keys else 0.0
bpy.context.view_layer.update()

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x, scene.render.resolution_y = 600, 1000
world = bpy.data.worlds.new("W"); scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.8, 0.82, 0.85, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.6
for rot, energy in (((0.9, 0, 0.5), 3.0), ((1.2, 0, 3.6), 1.5)):
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sun.data.energy = energy
    sun.rotation_euler = rot
    scene.collection.objects.link(sun)
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
scene.collection.objects.link(cam)
scene.camera = cam
cam.data.type = "ORTHO"
cam.location = (2.2, -4.2, 1.2)
cam.rotation_euler = (math.radians(85), 0, math.radians(28))
cam.data.ortho_scale = 2.1
scene.render.filepath = out
bpy.ops.render.render(write_still=True)

# close-up of the face for the viseme
cam.data.ortho_scale = 0.35
head_z = max((body.matrix_world @ v.co).z for v in body.data.vertices) - 0.12
cam.location = (0.6, -1.6, head_z + 0.05)
cam.rotation_euler = (math.radians(88), 0, math.radians(18))
scene.render.filepath = out.replace(".png", "_face.png")
bpy.ops.render.render(write_still=True)
print("CF: posed renders", out)
