"""One-time: pin MediaPipe's 478 face landmarks to the MPFB base mesh (writes ../face_map.json).

Renders the default MPFB head from the front, finds the landmarks on the render with MediaPipe
(run in the project venv), and ray-casts each one onto the head. Every MPFB human shares the same
mesh, so the resulting (triangle, barycentric) pins work for any body/face shape.

    blender -b --factory-startup -P calibrate_face.py
"""
import importlib
import json
import os
import subprocess
import sys

import addon_utils
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
VENV_PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
WORK = os.path.join(ROOT, "test", "calib")
os.makedirs(WORK, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
MPFB = next(m.__name__ for m in addon_utils.modules() if m.__name__.endswith(".mpfb"))
addon_utils.enable(MPFB, default_set=True)
svc = lambda m, c: getattr(importlib.import_module(f"{MPFB}.services.{m}"), c)  # noqa: E731
HumanService, AssetService = svc("humanservice", "HumanService"), svc("assetservice", "AssetService")
index = json.load(open(os.path.join(ROOT, "asset_index.json")))

human = HumanService.create_human()
HumanService.set_character_skin(index["skins"]["young_caucasian_female"]["mhmat"], human, skin_type="ENHANCED_SSS")
for frag, sub, kind in (("high-poly/high-poly.mhclo", "eyes", "Eyes"),
                        ("eyebrow001/eyebrow001.mhclo", "eyebrows", "Eyebrows"),
                        ("eyelashes01/eyelashes01.mhclo", "eyelashes", "Eyelashes")):
    HumanService.add_mhclo_asset(AssetService.find_asset_absolute_path(frag, sub), human, asset_type=kind,
                                 subdiv_levels=0, material_type="MAKESKIN")

# base-index coordinates (mask off) and the body-only triangles
mask = human.modifiers.get("Hide helpers")
mask.show_viewport = False
deps = bpy.context.evaluated_depsgraph_get()
ev = human.evaluated_get(deps)
me = ev.to_mesh()
co = np.array([v.co[:] for v in me.vertices])
ev.to_mesh_clear()
mask.show_viewport = True
body = {v.index for v in human.data.vertices
        if any(g.group == human.vertex_groups["body"].index for g in v.groups)}
tris = []
for p in human.data.polygons:
    vs = list(p.vertices)
    if all(v in body for v in vs):
        for i in range(1, len(vs) - 1):
            tris.append((vs[0], vs[i], vs[i + 1]))
bvh = BVHTree.FromPolygons([Vector(c) for c in co], tris)

head = co[[v for v in body if co[v][2] > co[:, 2].max() - 0.26]]
cx, top = head[:, 0].mean(), head[:, 2].max()
scale, zc = 0.30, top - 0.13

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = scene.render.resolution_y = 1024
world = bpy.data.worlds.new("W"); scene.world = world; world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.9, 0.9, 0.9, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
sun.data.energy = 2.5; sun.rotation_euler = (1.35, 0, 0.15)
scene.collection.objects.link(sun)
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
scene.collection.objects.link(cam); scene.camera = cam
cam.data.type = "ORTHO"; cam.data.ortho_scale = scale
cam.location = (cx, -2.0, zc); cam.rotation_euler = (np.pi / 2, 0, 0)
render = os.path.join(WORK, "head_front.png")
scene.render.filepath = render
bpy.ops.render.render(write_still=True)

out_json = os.path.join(WORK, "head_landmarks.json")
r = subprocess.run([VENV_PY, os.path.join(ROOT, "generate", "face.py"), render, out_json],
                   capture_output=True, text=True)
lm = json.load(open(out_json))["landmarks"]
if lm is None:
    sys.exit("CF: FAILED no face found on the calibration render " + r.stdout + r.stderr)

pins = []
misses = 0
for u, v in lm:
    x = cx + (u / 1024 - 0.5) * scale
    z = zc + (0.5 - v / 1024) * scale
    loc, normal, ti, dist = bvh.ray_cast(Vector((x, -2.0, z)), Vector((0, 1, 0)))
    if ti is None:
        pins.append(None); misses += 1
        continue
    a, b, c = (Vector(co[i]) for i in tris[ti])
    # barycentric of loc in triangle abc
    v0, v1, v2 = b - a, c - a, loc - a
    d00, d01, d11, d20, d21 = v0.dot(v0), v0.dot(v1), v1.dot(v1), v2.dot(v0), v2.dot(v1)
    den = d00 * d11 - d01 * d01
    wb = (d11 * d20 - d01 * d21) / den
    wc = (d00 * d21 - d01 * d20) / den
    pins.append([list(tris[ti]), [1 - wb - wc, wb, wc]])
json.dump({"pins": pins, "render": render}, open(os.path.join(ROOT, "face_map.json"), "w"))
print(f"CF: pinned {478 - misses}/478 landmarks -> face_map.json")
