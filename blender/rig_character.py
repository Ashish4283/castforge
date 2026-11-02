"""CastForge rig stage: body mesh in -> Rigify-rigged, skinned .blend out.

Assumes a single standing humanoid in T- or A-pose, Z-up, facing -Y
(character's left on +X). Use --face-plus-y for meshes that come in backwards.

    blender -b --factory-startup -P rig_character.py -- --mesh body.obj --out body_rigged.blend [--preview out_dir]

Steps: import -> normalize to --height metres, feet on the floor -> add the Rigify
human metarig (face bones stripped; lip-sync will use shape keys) -> fit it to the
mesh (uniform scale, then swing each arm onto the mesh's hand tip and each leg onto
the mesh's foot) -> generate the control rig -> bind with automatic weights ->
key a short test motion and optionally render rest/posed previews.
"""
import os
import sys
import argparse
import addon_utils
import bpy
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--mesh", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--height", type=float, default=1.75)
ap.add_argument("--face-plus-y", action="store_true")
ap.add_argument("--preview", help="directory for rest/posed preview PNGs")
args = ap.parse_args(argv)


def fail(msg):
    print(f"RIG FAILED: {msg}")
    sys.exit(1)


def select_only(*objs, active=None):
    bpy.ops.object.mode_set(mode="OBJECT") if bpy.context.object and bpy.context.object.mode != "OBJECT" else None
    for o in bpy.context.view_layer.objects:
        o.select_set(o in objs)
    bpy.context.view_layer.objects.active = active or objs[-1]


bpy.ops.wm.read_factory_settings(use_empty=True)
addon_utils.enable("rigify", default_set=True)

# --- import -------------------------------------------------------------------
ext = os.path.splitext(args.mesh)[1].lower()
if ext == ".obj":
    bpy.ops.wm.obj_import(filepath=args.mesh)
elif ext in (".glb", ".gltf"):
    bpy.ops.import_scene.gltf(filepath=args.mesh)
elif ext == ".fbx":
    bpy.ops.import_scene.fbx(filepath=args.mesh)
else:
    fail(f"unsupported mesh type {ext}")

meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
if not meshes:
    fail("no mesh in file")
for o in bpy.context.scene.objects:
    if o.type != "MESH":
        bpy.data.objects.remove(o)
select_only(*meshes)
if len(meshes) > 1:
    bpy.ops.object.join()
body = bpy.context.view_layer.objects.active
body.name = "Body"
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

# --- normalize ----------------------------------------------------------------
verts = [v.co.copy() for v in body.data.vertices]
lo = Vector((min(v.x for v in verts), min(v.y for v in verts), min(v.z for v in verts)))
hi = Vector((max(v.x for v in verts), max(v.y for v in verts), max(v.z for v in verts)))
s = args.height / (hi.z - lo.z)
norm = Matrix.Scale(s, 4) @ Matrix.Translation(Vector((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z)))
if args.face_plus_y:
    norm = Matrix.Rotation(3.14159265, 4, "Z") @ norm
body.data.transform(norm)
body.data.update()
verts = [v.co.copy() for v in body.data.vertices]
H = args.height

# landmarks: hand tip = farthest-out vertex above the knees on each side;
# foot = centroid of the floor-level vertices on each side
def hand_tip(sign):
    cand = [v for v in verts if v.z > 0.4 * H and v.x * sign > 0]
    return max(cand, key=lambda v: v.x * sign)

def foot_center(sign):
    cand = [v for v in verts if v.z < 0.06 * H and v.x * sign > 0]
    if not cand:
        fail("no floor-level vertices: is the mesh standing?")
    return sum(cand, Vector()) / len(cand)

# --- metarig ------------------------------------------------------------------
bpy.ops.object.armature_human_metarig_add()
meta = bpy.context.view_layer.objects.active
meta.name = "metarig"
select_only(meta)
bpy.ops.object.mode_set(mode="EDIT")
eb = meta.data.edit_bones

def descendants(bone):
    out = [bone]
    for c in bone.children:
        out += descendants(c)
    return out

# strip face rig; head stays
head = eb["spine.006"]
for b in descendants(head)[1:]:
    eb.remove(b)

top = max(b.tail.z for b in eb)
for b in eb:
    b.transform(Matrix.Scale(H / top, 4), scale=True, roll=True)

def swing(root_name, tip_point, target, plane_only=False):
    """Rotate+scale the chain under root_name about its head so tip_point lands on target."""
    root = eb[root_name]
    pivot = root.head.copy()
    d0 = tip_point - pivot
    d1 = target - pivot
    if plane_only:
        d1.y = d0.y
    m = (Matrix.Translation(pivot) @ d0.rotation_difference(d1).to_matrix().to_4x4()
         @ Matrix.Scale(d1.length / d0.length, 4) @ Matrix.Translation(-pivot))
    for b in descendants(root):
        b.transform(m, scale=True, roll=True)

for side, sign in (("L", 1), ("R", -1)):
    swing(f"upper_arm.{side}", eb[f"f_middle.03.{side}"].tail.copy(), hand_tip(sign))
    ankle = eb[f"foot.{side}"].head.copy()
    f = foot_center(sign)
    swing(f"thigh.{side}", ankle, Vector((f.x, ankle.y, ankle.z)), plane_only=True)

bpy.ops.object.mode_set(mode="OBJECT")

# --- generate -----------------------------------------------------------------
before = set(bpy.data.objects)
select_only(meta)
bpy.ops.pose.rigify_generate()
rig = next((o for o in bpy.data.objects if o not in before and o.type == "ARMATURE"), None)
if rig is None:
    fail("rigify_generate produced no armature")
rig.name = "CastForge_Rig"
meta.hide_set(True)
meta.hide_render = True

# --- bind ---------------------------------------------------------------------
select_only(body, rig, active=rig)
bpy.ops.object.parent_set(type="ARMATURE_AUTO")
groups = {g.index for g in body.vertex_groups}
unweighted = sum(1 for v in body.data.vertices
                 if not any(g.group in groups and g.weight > 1e-4 for g in v.groups))
print(f"bind: {len(body.vertex_groups)} groups, {unweighted}/{len(body.data.vertices)} verts unweighted")
if unweighted > 0.01 * len(body.data.vertices):
    fail("automatic weights left >1% of vertices unbound (mesh likely non-manifold or self-intersecting)")

# --- test motion --------------------------------------------------------------
pb = rig.pose.bones
for b in pb:
    if "IK_FK" in b.keys():
        b["IK_FK"] = 1.0   # FK so rotations below drive the limbs
scene = bpy.context.scene
scene.frame_start, scene.frame_end = 1, 48

def key(frame, poses):
    for name, euler in poses.items():
        p = pb.get(name)
        if p is None:
            print(f"warn: control {name} not found")
            continue
        p.rotation_mode = "XYZ"
        p.rotation_euler = euler
        p.keyframe_insert("rotation_euler", frame=frame)

rest = {n: (0, 0, 0) for n in ("upper_arm_fk.L", "forearm_fk.L", "upper_arm_fk.R",
                               "thigh_fk.R", "shin_fk.R", "head", "chest")}
wave = {"upper_arm_fk.L": (0, 0, 1.4), "forearm_fk.L": (0, 0, 1.2),
        "upper_arm_fk.R": (0.6, 0, 0), "thigh_fk.R": (-0.9, 0, 0), "shin_fk.R": (1.3, 0, 0),
        "head": (0, 0, 0.4), "chest": (0, 0, 0.25)}
key(1, rest); key(24, wave); key(48, rest)

bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.out))
print(f"saved {args.out}")

# --- previews -----------------------------------------------------------------
if args.preview:
    os.makedirs(args.preview, exist_ok=True)
    cam = bpy.data.objects.new("PreviewCam", bpy.data.cameras.new("PreviewCam"))
    scene.collection.objects.link(cam)
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = H * 1.25
    cam.location = (0, -6, H / 2)
    cam.rotation_euler = (1.5708, 0, 0)
    scene.camera = cam
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = scene.render.resolution_y = 768
    rig.hide_render = True
    for frame, tag in ((1, "rest"), (24, "posed")):
        scene.frame_set(frame)
        scene.render.filepath = os.path.join(os.path.abspath(args.preview), f"{tag}.png")
        bpy.ops.render.render(write_still=True)
    print(f"previews in {args.preview}")
