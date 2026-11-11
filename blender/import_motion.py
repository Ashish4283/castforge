"""A motion clip from a Mixamo FBX or a CMU BVH -> motions/clips/<name>.blend (the skeleton and its action, as
imported) and <name>.json (bone map, hip height, and the track of hips, feet and facing that placement uses).

blender -b --factory-startup --python-exit-code 1 -P blender/import_motion.py -- SOURCE OUT_BLEND OUT_JSON
"""
import json
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
for p_ in (os.path.dirname(HERE), HERE):
    if p_ not in sys.path:
        sys.path.insert(0, p_)
import motion  # noqa: E402


def log(*a):
    print("CF:", *a, flush=True)


src, out_blend, out_json = sys.argv[sys.argv.index("--") + 1:][:3]
scene = bpy.context.scene
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
ext = os.path.splitext(src)[1].lower()
if ext == ".bvh":
    bpy.ops.import_anim.bvh(filepath=src, update_scene_fps=True, update_scene_duration=True, rotate_mode="NATIVE")
elif ext == ".fbx":
    scene.render.fps, scene.render.fps_base = 30, 1.0        # Mixamo's rate; the importer keys at scene frames
    bpy.ops.import_scene.fbx(filepath=src)
else:
    sys.exit(f"CF: ERROR use a Mixamo .fbx or a CMU .bvh file, not {ext or 'a file without extension'}")

arms = [o for o in scene.objects if o.type == "ARMATURE"]
if not arms:
    sys.exit("CF: ERROR the file has no skeleton")
arm = max(arms, key=lambda o: len(o.data.bones))
for o in list(scene.objects):                  # a Mixamo download "with skin" brings its mesh: not needed
    if o is not arm:
        bpy.data.objects.remove(o)
try:
    kind, bones = motion.bone_map([b.name for b in arm.data.bones])
except ValueError as e:
    sys.exit(f"CF: ERROR {e}")
action = arm.animation_data.action if arm.animation_data else None
if action is None:
    sys.exit("CF: ERROR the file has no animation")
name = os.path.splitext(os.path.basename(out_json))[0]
arm.name, action.name = "CF_Motion", name
fps = scene.render.fps / scene.render.fps_base
first, last = (int(round(v)) for v in action.frame_range)

mw = arm.matrix_world.copy()
rest = {part: mw @ arm.data.bones[b].head_local for part, b in bones.items()}
hip_height = rest["hips"].z - (rest["toe.L"].z + rest["toe.R"].z) / 2
if hip_height <= 0:
    sys.exit("CF: ERROR the skeleton's rest pose is not standing upright")

pb = arm.pose.bones
track = {"fps": motion.TRACK_FPS, "hips": [], "facing": [], "feet": {"L": [], "R": []}, "floor": []}
n = int((last - first) / fps * motion.TRACK_FPS) + 1
for i in range(n):
    f = first + i * fps / motion.TRACK_FPS
    scene.frame_set(int(f), subframe=f - int(f))
    at = {part: mw @ pb[b].head for part, b in bones.items()}
    track["hips"].append([round(v, 4) for v in at["hips"]])
    track["facing"].append(round(motion.facing_of(at["thigh.L"], at["thigh.R"]), 4))
    for side in ("L", "R"):
        ankle, toe = at[f"foot.{side}"], at[f"toe.{side}"]
        track["feet"][side].append([round(v, 4) for v in ankle]
                                   + [round(motion.heading_of(toe.x - ankle.x, toe.y - ankle.y), 4)])
    track["floor"].append(round(min(at["toe.L"].z, at["toe.R"].z), 4))

meta = {"name": name, "source": kind, "file": os.path.basename(src), "fps": fps, "frames": [first, last],
        "seconds": round((last - first) / fps, 3), "bones": bones, "hip_height": round(hip_height, 4), "track": track}
os.makedirs(os.path.dirname(os.path.abspath(out_json)), exist_ok=True)
json.dump(meta, open(out_json, "w", encoding="utf-8"), separators=(",", ":"))
scene.frame_set(first)
bpy.data.orphans_purge(do_recursive=True)      # the skin's materials and textures
bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out_blend), compress=True)
log(f"motion clip {name}: {kind} skeleton, {meta['seconds']:.1f} s at {fps:g} fps")
