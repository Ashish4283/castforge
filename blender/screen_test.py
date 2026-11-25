"""Put a character through a screen test: can it actually do the things a scene will ask of it?

    blender -b --python-exit-code 1 -P blender/screen_test.py -- FILE.blend [--shots DIR] [--json OUT]

Every move in `core/screening.MOVES` is posed on the rig here, held, and measured; then the pose is taken
off again and the file is left exactly as it was found (nothing is ever saved). What the measurements
mean - and why each one is a thing you would otherwise discover halfway through a film - is in
`core/screening.py`, which is pure and tested. This file only poses and measures.

The expensive way to learn that a shoulder tears when the arm goes up is to render the shot. This takes
about twenty seconds and tells you before a single frame is spent.

With `--shots DIR` it also photographs the character in each pose, which is the half of a screen test a
person can actually judge: the numbers say the shoulder stretches 2.4x, the picture shows you what that
looks like.
"""
import argparse
import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from core import screening  # noqa: E402

TURN = math.radians


def log(*a):
    print("CF:", *a, flush=True)


# --- the poses ------------------------------------------------------------------------------------------
# Each move is a list of (bone, what to do). A rotation is radians about the bone's own axes; a shift is
# metres in the rig's space. These are deliberately BIG - a screen test asks for the extreme of what a
# scene will ever ask for, because that is where a rig gives out.

def _rot(x=0.0, y=0.0, z=0.0):
    """A turn about the bone's OWN axes - right for a hinge (an elbow, a knuckle) that knows its way."""
    return ("rot", (x, y, z))


def _turn(x=0.0, y=0.0, z=0.0):
    """A turn about the WORLD's axes, through the bone's own head: x tips forward, y rolls out to the
    side, z turns left and right.

    Which local axis of a bone is "yaw" is a question with no general answer - the head bone points up
    its own length, so its local Z is the twist and turning the head about it tipped the chin at the
    ceiling, and the two arms mirror, so the same local rotation raised one and lowered the other. Both
    were plain in the pictures. Asking in world terms means never having to know."""
    return ("turn", (x, y, z))


def _move(x=0.0, y=0.0, z=0.0):
    return ("move", (x, y, z))


POSES = {
    "stand": [],
    "walk": [("foot_ik.L", _move(y=-0.32)), ("foot_ik.R", _move(y=0.32)),
             ("torso", _move(z=-0.04)), ("thigh_parent.L", _rot()), ("thigh_parent.R", _rot())],
    "run": [("foot_ik.L", _move(y=-0.52, z=0.10)), ("foot_ik.R", _move(y=0.46, z=0.14)),
            ("torso", _move(z=-0.06))],
    "jump": [("foot_ik.L", _move(z=0.30)), ("foot_ik.R", _move(z=0.30)), ("torso", _move(z=0.18))],
    "crouch": [("torso", _move(z=-0.30))],
    # A bow: the fold is shared between the chest and the head, as a person shares it between their spine
    # and their neck. Forty degrees at the chest is a bow, not a jack-knife.
    "bend": [("chest", _turn(x=TURN(40))), ("head", _turn(x=TURN(-15)))],
    # Looking over a shoulder: about 45 degrees of it is the head and 20 the neck, which is as far as a
    # person goes without turning their shoulders too.
    "turn_head": [("head", _turn(z=TURN(45))), ("neck", _turn(z=TURN(20)))],
    "nod": [("head", _turn(x=TURN(30)))],
    "look": [("eye_common", _rot(z=TURN(22), x=TURN(12)))],
    # Both arms up and out to the side, and the elbows folded: the shape of a wave, a clap or a reach,
    # and the one pose that finds a shoulder painted onto too many bones.
    "arms": [("upper_arm_fk.L", _turn(y=TURN(-80))), ("upper_arm_fk.R", _turn(y=TURN(80))),
             ("forearm_fk.L", _rot(x=TURN(-70))), ("forearm_fk.R", _rot(x=TURN(-70)))],
    # The wrist is two axes and the thumb side mirrors (see the note in scene_kit.key_arms)
    "wrist": [("hand_fk.L", _rot(x=TURN(55), z=TURN(-20))), ("hand_fk.R", _rot(x=TURN(55), z=TURN(20)))],
    "fingers": [(f"f_{f}.{s}.{side}", _rot(x=TURN(62) * w))
                for f in screening.FINGERS for s, w in (("01", 0.8), ("02", 1.0), ("03", 0.7))
                for side in "LR"]
               + [(f"thumb.{s}.{side}", _rot(x=TURN(40)))
                  for s in ("02", "03") for side in "LR"],
    "grip": [(f"f_index.{s}.{side}", _rot(x=TURN(70))) for s in screening.SEGMENTS for side in "LR"]
            + [(f"thumb.{s}.{side}", _rot(x=TURN(45))) for s in ("02", "03") for side in "LR"],
    "speak": [],
    "express": [],
}


def skin_edges(body, step=3):
    """Edges with both ends in the skin, as (a, b) - helper cages and joint cubes are not skin.

    `step` samples them: a body carries about 38,000 edges and every fourth one says the same thing in a
    quarter of the time, which matters when fifteen poses are each measured."""
    group = next((g.index for g in body.vertex_groups if g.name == "body"), None)
    if group is None:
        inside = set(range(len(body.data.vertices)))
    else:
        inside = {v.index for v in body.data.vertices if any(g.group == group for g in v.groups)}
    return [tuple(e.vertices) for i, e in enumerate(body.data.edges)
            if i % step == 0 and e.vertices[0] in inside and e.vertices[1] in inside]


def only_the_rig(body):
    """Turn off every modifier but the armature, for as long as the measuring takes.

    Putting a garment on a body ADDS A MASK to it, and a masked vertex is a missing vertex: the evaluated
    mesh comes back with 10,070 vertices where the real one has 19,158, every index after the first
    hidden one means a different place, and the edges being measured point into nothing. The armature is
    the only modifier that matters here anyway - it is the one that does the deforming."""
    was = [(m, m.show_viewport) for m in body.modifiers]
    for m, _ in was:
        m.show_viewport = (m.type == "ARMATURE")
    return was


def mesh_now(body):
    """The body's vertices as the rig has left them - one value per vertex of the real mesh."""
    ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    out = [body.matrix_world @ v.co.copy() for v in me.vertices]
    ev.to_mesh_clear()
    return out


TINY_EDGE = 0.001        # a millimetre: below that an edge is noise, and its ratio is meaningless


def stretched(rest, posed, edges, rough=1.8):
    """How far skin is pulled out of shape, posed against at rest: (worst, where, what fraction is rough).

    The worst edge on its own is an extreme-value statistic over nine thousand edges, and one bad edge
    says nothing - an armpit always has one. What says something is how MUCH of the surface is pulled
    about: three edges over 1.8x is a crease, nine hundred is a melted shoulder. Both come back, and
    `core/screening.py` decides which matters.

    Edges under a millimetre at rest are skipped: the ratio of a 0.1 mm edge is arithmetic, not a surface
    anybody can see, and one of them is enough to make a sound rig look torn."""
    if len(rest) != len(posed):
        return None, None, None
    worst, where, bad_ones, counted = 1.0, None, 0, 0
    for a, b in edges:
        was = (rest[a] - rest[b]).length
        if was < TINY_EDGE:
            continue
        counted += 1
        now = (posed[a] - posed[b]).length / was
        if now > rough:
            bad_ones += 1
        if now > worst:
            worst, where = now, posed[a]
    return worst, where, (bad_ones / counted if counted else None)


def furthest(rest, posed):
    """How far the skin actually travelled. A move that moves no skin at all does nothing in a shot."""
    if len(rest) != len(posed):
        return None
    return max((p - r).length for r, p in zip(rest, posed))


def hold(rig, pose):
    """Put the rig in a pose; returns what was asked of each bone, and what it actually did.

    A bone that is simply not there is "missing". One that is there and did not move at all is "frozen" -
    a lock, or a constraint overriding it - which looks identical in a shot and is a different fix."""
    missing, frozen, reached = [], [], []
    before = {}
    for name, (_how, _what) in pose:
        bone = rig.pose.bones.get(name)
        if bone is None:
            if name not in missing:
                missing.append(name)
            continue
        before[name] = (rig.matrix_world @ bone.matrix).copy()
    for name, (how, what) in pose:
        bone = rig.pose.bones.get(name)
        if bone is None:
            continue
        if how == "rot":
            bone.rotation_mode = "XYZ"
            bone.rotation_euler = Vector(bone.rotation_euler) + Vector(what)
        elif how == "turn":
            at = bone.matrix.translation.copy()
            spin = Matrix.Identity(4)
            for axis, angle in zip("XYZ", what):
                if angle:
                    spin = Matrix.Rotation(angle, 4, axis) @ spin
            bone.matrix = Matrix.Translation(at) @ spin @ Matrix.Translation(-at) @ bone.matrix
        else:
            bone.location = bone.location + Vector(what)
    bpy.context.view_layer.update()
    for name, (how, what) in pose:
        bone = rig.pose.bones.get(name)
        if bone is None or name not in before:
            continue
        was = before[name]
        now = rig.matrix_world @ bone.matrix
        shifted = (now.translation - was.translation).length
        # The angle of the whole rotation, not the angle its DIRECTION swung through. A bone points along
        # its own length, so a twist about that length - which is exactly what turning a head is, since
        # the head bone points up - leaves its direction untouched, and a head that turned the whole way
        # measured as 18% of the way. This sees the twist.
        swung = (now.to_3x3() @ was.to_3x3().inverted()).to_quaternion().angle
        if how in ("rot", "turn"):
            asked = Vector(what).length
            if swung < 1e-3 and shifted < 1e-4:
                if name not in frozen:
                    frozen.append(name)
            elif asked > 1e-6:
                reached.append(min(1.0, swung / asked))
        else:
            asked = Vector(what).length
            if shifted < 1e-4:
                if name not in frozen:
                    frozen.append(name)
            elif asked > 1e-6:
                reached.append(min(1.0, shifted / asked))
    return {"missing": missing, "frozen": frozen,
            "reach": (sum(reached) / len(reached)) if reached else None}


def as_a_scene_does(rig):
    """Set the IK/FK switches the way `scene_kit.Actor` sets them before it poses anybody.

    A character file sits at Rigify's own defaults, where the arms are in IK. A scene puts the arms in FK
    and the legs in IK (scene_kit.Actor.__init__), and then drives upper_arm_fk, forearm_fk and hand_fk.
    Testing the file as it sits means turning controls nothing is listening to: every arm and wrist pose
    came back "the controls turn but the body does not", which was true of the test, not of the rig."""
    set_to = []
    for side in "LR":
        for name, value in ((f"thigh_parent.{side}", 0.0), (f"upper_arm_parent.{side}", 1.0)):
            bone = rig.pose.bones.get(name)
            if bone is not None:
                set_to.append((bone, bone.get("IK_FK")))
                bone["IK_FK"] = value
    bpy.context.view_layer.update()
    return set_to


def release(rig):
    """Back to the rest pose, every bone, so the next move is measured from the same place."""
    for bone in rig.pose.bones:
        bone.location = (0.0, 0.0, 0.0)
        bone.rotation_euler = (0.0, 0.0, 0.0)
        bone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        bone.scale = (1.0, 1.0, 1.0)
    bpy.context.view_layer.update()


def shapes_on(body, prefix):
    """How many face shapes of a kind this body carries (visemes, expressions)."""
    keys = body.data.shape_keys.key_blocks if body.data.shape_keys else []
    if prefix == "viseme":
        return sum(1 for k in keys if k.name.lower().startswith("viseme"))
    known = ("viseme", "basis")
    return sum(1 for k in keys if not k.name.lower().startswith(known))


def ik_error(rig):
    """How far each foot ended up from the target that was put there - why feet slide.

    A leg that cannot reach where the animation puts its foot leaves the foot somewhere else, and across
    a stride that difference is the skate."""
    worst = None
    for side in "LR":
        target = rig.pose.bones.get(f"foot_ik.{side}")
        foot = rig.pose.bones.get(f"DEF-foot.{side}") or rig.pose.bones.get(f"foot_fk.{side}")
        if target is None or foot is None:
            continue                            # None, not 0: "could not measure" is not "perfect"
        off = ((rig.matrix_world @ target.head) - (rig.matrix_world @ foot.head)).length
        worst = off if worst is None else max(worst, off)
    return worst


# --- photographing it -----------------------------------------------------------------------------------

def set_up_camera(tall):
    scene = bpy.context.scene
    for engine in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    scene.render.resolution_x, scene.render.resolution_y = 420, 680
    world = bpy.data.worlds.new("ScreenTest")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.09, 0.10, 0.13, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.7
    for rot, energy in (((0.9, 0, 0.6), 3.2), ((1.2, 0, 3.6), 1.4)):
        sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
        sun.data.energy = energy
        sun.rotation_euler = rot
        scene.collection.objects.link(sun)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = tall * 1.35
    a = math.radians(28)                       # three-quarters on: a pose reads better than straight on
    cam.location = (6 * math.sin(a), -6 * math.cos(a), tall * 0.52)
    cam.rotation_euler = (math.radians(90), 0, a)
    return cam


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--json", help="write the measurements here (default: <file>.screen.json)")
    ap.add_argument("--shots", help="photograph the character in each pose into this folder")
    args = ap.parse_args(argv)

    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(args.file))
    rigs = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if not rigs:
        raise SystemExit("CF: there is no rig in that file")
    rig = max(rigs, key=lambda o: len(o.data.bones))      # the metarig is left in the file on purpose
    skinned = [o for o in bpy.data.objects
               if o.type == "MESH" and any(m.type == "ARMATURE" for m in o.modifiers)]
    if not skinned:
        raise SystemExit("CF: nothing in that file is attached to the rig")
    body = max(skinned, key=lambda o: len(o.data.vertices))
    bpy.context.view_layer.objects.active = rig
    release(rig)
    switches = as_a_scene_does(rig)
    log(f"arms in FK and legs in IK, as a scene sets them ({len(switches)} switches)")

    edges = skin_edges(body)
    masks = only_the_rig(body)
    rest = mesh_now(body)
    if len(rest) != len(body.data.vertices):
        raise SystemExit(f"CF: the body evaluates to {len(rest)} vertices but has "
                         f"{len(body.data.vertices)}: something is still changing the mesh")
    tall = max(p.z for p in rest) - min(p.z for p in rest)
    log(f"{os.path.basename(args.file)}: {rig.name}, {len(rig.data.bones)} bones, "
        f"{len(rest)} vertices, {len(edges)} edges of skin measured, {tall:.2f} m tall")
    cam = set_up_camera(tall) if args.shots else None
    if args.shots:
        os.makedirs(args.shots, exist_ok=True)

    results = {}
    for name in screening.ORDER:
        move = screening.MOVES[name]
        pose = POSES.get(name, [])
        facts = hold(rig, pose) if pose else {"missing": [], "frozen": [], "reach": None}
        # a move with no pose of its own still needs its controls to be there
        for bone in move.get("needs", ()):
            if rig.pose.bones.get(bone) is None and bone not in facts["missing"]:
                facts["missing"].append(bone)
        if pose and move.get("surface", True):
            now = mesh_now(body)
            facts["stretch"], at, facts["rough_skin"] = stretched(rest, now, edges)
            facts["moved"] = furthest(rest, now)
            if at is not None:
                facts["worst_at"] = [round(float(x), 3) for x in at]
        if move.get("shapes"):
            facts["shapes"] = shapes_on(body, move["shapes"][0])
        if move.get("watch") == "slide":
            off = ik_error(rig)
            if off is not None:
                facts["slide"] = off
        if args.shots and pose:
            bpy.context.scene.render.filepath = os.path.join(os.path.abspath(args.shots), f"{name}.png")
            bpy.ops.render.render(write_still=True)
        release(rig)
        results[name] = facts
        said = screening.look(name, facts)
        mark = "x" if screening.bad(name, facts) else ("~" if said else "ok")
        log(f"  [{mark:>2}] {move['title']}"
            + (f" - stretch {facts['stretch']:.2f}" if facts.get("stretch") else "")
            + (f", reach {facts['reach'] * 100:.0f}%" if facts.get("reach") is not None else "")
            + (f" over {facts['rough_skin'] * 100:.2f}% of the skin" if facts.get("rough_skin") else "")
            + (f", moved {facts['moved'] * 100:.0f} cm" if facts.get("moved") is not None else "")
            + (f", foot off by {facts['slide'] * 100:.1f} cm" if facts.get("slide") is not None else ""))
        for line in said:
            log("       ", line)

    for m, shown in masks:                     # the file is left exactly as it was found
        m.show_viewport = shown
    for bone, was in switches:
        if was is None:
            del bone["IK_FK"]
        else:
            bone["IK_FK"] = was
    out = screening.verdict(results)
    log(out["line"])
    where = args.json or os.path.splitext(os.path.abspath(args.file))[0] + ".screen.json"
    json.dump({"file": os.path.basename(args.file), "bones": len(rig.data.bones),
               "height": round(tall, 3), "measured": results, **out,
               "shots": os.path.basename(args.shots) if args.shots else None},
              open(where, "w", encoding="utf-8"), indent=1)
    log("screen test", where)
    if cam:
        log("shots", args.shots)


if __name__ == "__main__":
    main()
