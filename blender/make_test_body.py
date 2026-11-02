"""Build a stand-in humanoid mesh (A-pose, facing -Y, Z-up) for testing the rig stage.

Not a character: just a watertight body-shaped mesh until the image-to-3D stage
produces real ones.

    blender -b --factory-startup -P make_test_body.py -- --out test_body.obj
"""
import sys
import argparse
import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
args = ap.parse_args(argv)

bpy.ops.wm.read_factory_settings(use_empty=True)

# (name, position, skin radius)
joints = {
    "pelvis": ((0, 0, 1.00), 0.15),
    "spine":  ((0, 0, 1.22), 0.13),
    "chest":  ((0, 0, 1.42), 0.15),
    "neck":   ((0, 0, 1.56), 0.055),
    "head":   ((0, 0, 1.68), 0.10),
    "crown":  ((0, 0, 1.76), 0.07),
}
for s, x in (("L", 1), ("R", -1)):
    joints.update({
        f"shoulder.{s}": ((0.19 * x, 0, 1.45), 0.065),
        f"elbow.{s}":    ((0.40 * x, 0, 1.24), 0.045),
        f"wrist.{s}":    ((0.59 * x, 0, 1.05), 0.035),
        f"hand.{s}":     ((0.67 * x, 0, 0.97), 0.03),
        f"hip.{s}":      ((0.10 * x, 0, 0.95), 0.085),
        f"knee.{s}":     ((0.11 * x, 0, 0.52), 0.06),
        f"ankle.{s}":    ((0.12 * x, 0.02, 0.08), 0.045),
        f"toe.{s}":      ((0.12 * x, -0.14, 0.03), 0.04),
    })
edges = [("pelvis", "spine"), ("spine", "chest"), ("chest", "neck"),
         ("neck", "head"), ("head", "crown")]
for s in ("L", "R"):
    edges += [("chest", f"shoulder.{s}"), (f"shoulder.{s}", f"elbow.{s}"),
              (f"elbow.{s}", f"wrist.{s}"), (f"wrist.{s}", f"hand.{s}"),
              ("pelvis", f"hip.{s}"), (f"hip.{s}", f"knee.{s}"),
              (f"knee.{s}", f"ankle.{s}"), (f"ankle.{s}", f"toe.{s}")]

names = list(joints)
mesh = bpy.data.meshes.new("skeleton")
mesh.from_pydata([joints[n][0] for n in names],
                 [(names.index(a), names.index(b)) for a, b in edges], [])
obj = bpy.data.objects.new("TestBody", mesh)
bpy.context.scene.collection.objects.link(obj)

obj.modifiers.new("skin", "SKIN")
for n, sv in zip(names, mesh.skin_vertices[0].data):
    r = joints[n][1]
    sv.radius = (r, r * 0.85)
mesh.skin_vertices[0].data[names.index("pelvis")].use_root = True
sub = obj.modifiers.new("subsurf", "SUBSURF")
sub.levels = 2

deps = bpy.context.evaluated_depsgraph_get()
baked = bpy.data.meshes.new_from_object(obj.evaluated_get(deps))
body = bpy.data.objects.new("TestBody", baked)
bpy.context.scene.collection.objects.link(body)
bpy.data.objects.remove(obj)

for o in bpy.context.scene.objects:
    o.select_set(o is body)
bpy.ops.wm.obj_export(filepath=args.out, export_selected_objects=True,
                      export_materials=False)  # default Y-up, like PIFuHD's OBJ output
print(f"wrote {args.out}: {len(baked.vertices)} verts")
