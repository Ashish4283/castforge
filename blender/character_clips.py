"""Short clips of a built character: a turntable, and a walk cycle at its own pace.

    blender -b --python-exit-code 1 -P blender/character_clips.py -- FILE.blend OUT_DIR
            [--what turntable,walk] [--seconds 2.4] [--size 420x680]

Why these two. A still says what a character looks like; neither a person judging their own work nor
anybody buying it can tell from a still whether the rig holds together. The turntable shows the silhouette
from every side, and the walk shows the thing that goes wrong most often and most visibly.

The walk is NOT a stock cycle played back at a stock speed. It is this body's own: `core/gait.py` measures
the legs and the build and says how fast it walks, how long its step is and how many of them it takes a
second, and the cycle is keyed from those. A 1.28 m character comes out busy and short-stepping and a
heavy one comes out rolling, because that is what the arithmetic says, not because somebody animated it
that way.
"""
import argparse
import math
import os
import subprocess
import sys

import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from core import config, gait, media  # noqa: E402
import acting  # noqa: E402

FPS = 24


def log(*a):
    print("CF:", *a, flush=True)


def markers_of(body):
    """MakeHuman's joint markers on this body, on the evaluated (morphed) mesh."""
    was = [(m, m.show_viewport) for m in body.modifiers]
    for m, _ in was:
        m.show_viewport = (m.type == "ARMATURE")
    ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    mw = body.matrix_world
    co = [mw @ v.co for v in me.vertices]
    ev.to_mesh_clear()
    for m, shown in was:
        m.show_viewport = shown
    if len(co) != len(body.data.vertices):
        return {}, co
    named = {g.index: g.name for g in body.vertex_groups if g.name.startswith("joint-")}
    members = {}
    for v in body.data.vertices:
        for g in v.groups:
            if g.group in named:
                members.setdefault(g.group, []).append(v.index)
    out = {named[i]: tuple(sum(co[k][a] for k in ks) / len(ks) for a in range(3))
           for i, ks in members.items()}
    if co:
        out["joint-head-2"] = (0.0, 0.0, max(p.z for p in co))
    return out, co


def as_a_scene_does(rig):
    """Arms FK, legs IK - the switches `scene_kit.Actor` sets before it poses anybody."""
    for side in "LR":
        for name, value in ((f"thigh_parent.{side}", 0.0), (f"upper_arm_parent.{side}", 1.0)):
            bone = rig.pose.bones.get(name)
            if bone is not None:
                bone["IK_FK"] = value
    bpy.context.view_layer.update()


def rest(rig):
    for bone in rig.pose.bones:
        bone.location = (0.0, 0.0, 0.0)
        bone.rotation_euler = (0.0, 0.0, 0.0)
        bone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        bone.scale = (1.0, 1.0, 1.0)


def key_walk(rig, how, frames):
    """A walk cycle in place, keyed from this body's own numbers (`core.gait.walk_like`).

    In place: the feet swing fore and aft and the hips rise, fall and roll, but the character does not
    travel - which is what you want in a clip of a walk, and what every marketplace turntable does too.

    One cycle is two steps, so the whole thing repeats over `frames` and the last frame matches the
    first; played on a loop there is no jump."""
    step, swing, sway, bob = how["step"], how["swing"], how["sway"], how["bob"]
    lift = step * 0.26                                 # how high a swinging foot comes off the ground
    hips = rig.pose.bones.get("torso")
    feet = {s: rig.pose.bones.get(f"foot_ik.{s}") for s in "LR"}
    arms = {s: rig.pose.bones.get(f"upper_arm_fk.{s}") for s in "LR"}
    elbows = {s: rig.pose.bones.get(f"forearm_fk.{s}") for s in "LR"}
    for f in range(frames + 1):
        t = f / frames                                 # 0..1 over one whole cycle (two steps)
        turn = 2.0 * math.pi * t
        for side, phase in (("L", 0.0), ("R", math.pi)):
            foot = feet[side]
            if foot is None:
                continue
            a = turn + phase
            fore = math.sin(a) * step * 0.5
            # the foot is only off the ground on the swing half of its own cycle
            up = max(0.0, math.sin(a + math.pi / 2)) ** 1.6 * lift if math.cos(a) > 0 else 0.0
            foot.location = Vector((0.0, fore, up))
            foot.keyframe_insert("location", frame=f + 1)
            arm = arms[side]
            if arm is not None:                        # arms swing against the legs
                arm.rotation_mode = "XYZ"
                arm.rotation_euler = (-math.sin(a) * 0.42 * swing, 0.0, 0.0)
                arm.keyframe_insert("rotation_euler", frame=f + 1)
            elbow = elbows[side]
            if elbow is not None:
                elbow.rotation_mode = "XYZ"
                elbow.rotation_euler = (-(0.22 + 0.16 * max(0.0, math.sin(a))) * swing, 0.0, 0.0)
                elbow.keyframe_insert("rotation_euler", frame=f + 1)
        if hips is not None:
            # twice a cycle up and down, once a cycle side to side: the roll a heavy body does more of
            hips.location = Vector((math.sin(turn) * step * 0.055 * sway,
                                    0.0,
                                    -math.cos(2 * turn) * step * 0.035 * bob))
            hips.keyframe_insert("location", frame=f + 1)


def set_up(tall, size, backdrop=(0.07, 0.075, 0.09)):
    scene = bpy.context.scene
    for engine in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.fps = FPS
    scene.render.image_settings.file_format = "PNG"
    world = bpy.data.worlds.new("Clip")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (*backdrop, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.75
    for rot, energy in (((0.95, 0, 0.6), 3.4), ((1.15, 0, 3.7), 1.5), ((0.5, 0, 2.2), 0.8)):
        sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
        sun.data.energy = energy
        sun.rotation_euler = rot
        scene.collection.objects.link(sun)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = tall * 1.18
    return cam


def aim(cam, angle, tall):
    a = math.radians(angle)
    cam.location = (6 * math.sin(a), -6 * math.cos(a), tall * 0.52)
    cam.rotation_euler = (math.radians(90), 0, a)


def shoot(out_dir, name, frames):
    """Render frame by frame into a folder, then encode one MP4 through core.media."""
    shots = os.path.join(out_dir, f".{name}_frames")
    os.makedirs(shots, exist_ok=True)
    scene = bpy.context.scene
    for f in range(1, frames + 1):
        scene.frame_set(f)
        scene.render.filepath = os.path.join(shots, f"{f:04d}.png")
        bpy.ops.render.render(write_still=True)
    out = os.path.join(out_dir, f"{name}.mp4")
    media.run([config.FFMPEG, "-y", "-framerate", str(FPS), "-i", os.path.join(shots, "%04d.png"),
               *media.video_args(), "-pix_fmt", "yuv420p", out])
    for f in os.listdir(shots):
        os.remove(os.path.join(shots, f))
    os.rmdir(shots)
    return out


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("out")
    ap.add_argument("--what", default="turntable,walk")
    ap.add_argument("--seconds", type=float, default=2.4)
    ap.add_argument("--size", default="420x680")
    args = ap.parse_args(argv)
    want = [w.strip() for w in args.what.split(",") if w.strip()]
    size = tuple(int(x) for x in args.size.lower().split("x"))
    os.makedirs(os.path.abspath(args.out), exist_ok=True)

    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(args.file))
    rigs = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if not rigs:
        raise SystemExit("CF: there is no rig in that file")
    rig = max(rigs, key=lambda o: len(o.data.bones))
    skinned = [o for o in bpy.data.objects
               if o.type == "MESH" and any(m.type == "ARMATURE" for m in o.modifiers)]
    if not skinned:
        raise SystemExit("CF: nothing in that file is attached to the rig")
    body = max(skinned, key=lambda o: len(o.data.vertices))
    bpy.context.view_layer.objects.active = rig
    rest(rig)
    as_a_scene_does(rig)

    joints, co = markers_of(body)
    tall = (max(p.z for p in co) - min(p.z for p in co)) if co else 1.7
    shape = gait.shape_of(joints)
    how = gait.walk_like(shape, acting.PACES["normal"])
    log(f"{os.path.basename(args.file)}: {tall:.2f} m. {gait.describe(shape) if shape else 'unmeasured'}")

    cam = set_up(tall, size)
    made = {}

    if "turntable" in want:
        frames = max(12, int(round(args.seconds * FPS)))
        # Blender 5 has no `Action.fcurves`, so the way to choose how keys interpolate is to say so
        # BEFORE inserting them. A turntable wants linear or it eases into every frame and judders.
        bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
        rest(rig)
        for f in range(1, frames + 1):
            cam_angle = 360.0 * (f - 1) / frames
            aim(cam, cam_angle, tall)
            cam.keyframe_insert("location", frame=f)
            cam.keyframe_insert("rotation_euler", frame=f)
        bpy.context.scene.frame_start, bpy.context.scene.frame_end = 1, frames
        made["turntable"] = shoot(os.path.abspath(args.out), "turntable", frames)
        log(f"turntable: {frames} frames, {frames / FPS:.1f} s")
        cam.animation_data_clear()

    if "walk" in want:
        bpy.context.preferences.edit.keyframe_new_interpolation_type = "BEZIER"
        rest(rig)
        aim(cam, 28, tall)
        # one cycle is two steps, and the cadence says how long that takes on THIS body
        cycle = 2.0 / how["cadence"] if how["cadence"] > 0.1 else 1.1
        frames = max(10, int(round(cycle * FPS)))
        key_walk(rig, how, frames)
        bpy.context.scene.frame_start, bpy.context.scene.frame_end = 1, frames
        made["walk"] = shoot(os.path.abspath(args.out), "walk", frames)
        log(f"walk: {frames} frames, one cycle in {cycle:.2f} s "
            f"({how['cadence']:.2f} steps a second, {how['step'] * 100:.0f} cm a step)")

    for name, path in made.items():
        log("clip", name, path, f"{os.path.getsize(path) / 1024:.0f} kB")


if __name__ == "__main__":
    main()
