"""Playing a motion clip on a CastForge character (Blender). The clip's skeleton is loaded beside the character,
placed where the character stands at its hip height, and the character's controls copy its rotations through
constraints that blend in and out. Face, eyes and lip-sync keep working while the body follows the clip, and
shot.blend keeps the constraints for hand fixes. The maths is in motion.py.
"""
import bpy
from bpy_extras import anim_utils
from mathutils import Matrix, Vector

import motion


def hip_height(act):
    """A character's hip height above its toes (metres), the scale a clip is played at."""
    return act.pb["torso"].bone.head_local.z - act.pb["toe_fk.L"].bone.head_local.z


def _collection():
    coll = bpy.data.collections.get("CF_motion")
    if coll is None:
        coll = bpy.data.collections.new("CF_motion")
        bpy.context.scene.collection.children.link(coll)
    return coll


def play(act, meta, t0, start, fps, speed, keys, travel=True, plant=None, holds=()):
    """Make `act` perform a clip from clip time t0, starting at scene frame `start`; keys: (frame, weight)
    blends (motion.fades). Call with the character's position and heading as they are when the clip starts."""
    coll = _collection()
    with bpy.data.libraries.load(meta["blend"], link=False) as (src, dst):
        dst.objects = list(src.objects)
    arm = next(o for o in dst.objects if o is not None and o.type == "ARMATURE")
    coll.objects.link(arm)
    n = sum(1 for o in coll.objects if o.type == "ARMATURE")
    arm.name = f"CF_clip_{act.id}_{n}"

    # time: the clip's keys move so clip time t0 plays at `start`, at the given speed
    ad = arm.animation_data
    bag = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
    for fc in bag.fcurves:
        count = len(fc.keyframe_points)
        for prop in ("co", "handle_left", "handle_right"):
            buf = [0.0] * (2 * count)
            fc.keyframe_points.foreach_get(prop, buf)
            buf[0::2] = [motion.clip_to_scene(x, meta, t0, start, fps, speed, holds) for x in buf[0::2]]
            fc.keyframe_points.foreach_set(prop, buf)
        fc.update()

    # place: the clip's hips at t0 over the character, facing its heading, at its hip height, toes on the floor
    track = meta["track"]
    i = motion.sample(track, t0)
    hx, hy, _ = track["hips"][i]
    # (matrix_basis: a just-appended object's matrix_world is not evaluated yet; Mixamo's holds scale and axes)
    arm.matrix_basis = (Matrix.Translation((act.pos.x, act.pos.y, 0.0))
                        @ Matrix.Rotation(act.heading - track["facing"][i], 4, "Z")
                        @ Matrix.Scale(hip_height(act) / meta["hip_height"], 4)
                        @ Matrix.Translation((-hx, -hy, -motion.floor(meta))) @ arm.matrix_basis)

    # helpers: one empty per body part, riding the clip's bone, turned so that at rest it matches the
    # character's control laid along the clip's bone; the control then copies the empty's world rotation
    arm.data.pose_position = "REST"
    bpy.context.view_layer.update()
    bones = meta["bones"]
    src_w = arm.matrix_world
    rig_w = Matrix.Translation(act.pos) @ Matrix.Rotation(act.heading, 4, "Z")

    def src_head(part):
        return src_w @ arm.data.bones[bones[part]].head_local

    def rig_head(control):
        return rig_w @ act.rig.data.bones[control].head_local

    turn = (motion.facing_of(src_head("thigh.L"), src_head("thigh.R"))
            - motion.facing_of(rig_head("thigh_fk.L"), rig_head("thigh_fk.R")))
    face = Matrix.Rotation(turn, 3, "Z")
    made = []
    for part, control in motion.CONTROLS.items():
        rest = (rig_w @ act.rig.data.bones[control].matrix_local).to_3x3()
        align = face
        if part not in motion.UPRIGHT:
            nxt = motion.next_part(part)
            s_dir = (src_head(nxt) if nxt else src_w @ arm.data.bones[bones[part]].tail_local) - src_head(part)
            t_dir = face @ rest.col[1]                        # a bone points along its own Y axis
            align = t_dir.rotation_difference(s_dir).to_matrix() @ face
        e = bpy.data.objects.new(f"{arm.name}_{part}", None)
        coll.objects.link(e)
        e.empty_display_size = 0.05
        e.parent, e.parent_type, e.parent_bone = arm, "BONE", bones[part]
        made.append((e, part, control, Matrix.LocRotScale(src_head(part), (align @ rest).to_quaternion(), None)))
    bpy.context.view_layer.update()
    for e, _, _, m in made:
        e.matrix_world = m
    arm.data.pose_position = "POSE"

    for e, part, control, _ in made:
        pb = act.pb[control]
        cons = [pb.constraints.new("COPY_ROTATION")]
        if part == "hips":
            cons.append(pb.constraints.new("COPY_LOCATION"))
            cons[-1].use_x = cons[-1].use_y = travel            # in place: the hips only rise and fall
        for c in cons:
            c.name = f"{arm.name} {c.type.lower()}"
            c.target = e
            c.owner_space = c.target_space = "WORLD"
            for f, w in keys:
                c.influence = w
                c.keyframe_insert("influence", frame=f)
    anchors = _anchors(act, start, fps, speed, keys, plant, holds) if travel and plant else {}
    for side in ("L", "R"):
        p = act.pb[f"thigh_parent.{side}"]
        wins = anchors.get(side, [])
        if not wins:
            for f, w in keys:                   # legs follow the clip (FK), then plant again (IK)
                p["IK_FK"] = w
                p.keyframe_insert('["IK_FK"]', frame=f)
            continue
        # this foot has planted stretches: IK (pinned) during them, the clip's FK between them
        def key_ikfk(f, w):
            p["IK_FK"] = w
            p.keyframe_insert('["IK_FK"]', frame=f)
        key_ikfk(keys[0][0], 0.0)
        pointer = keys[1][0]
        for fa, fb, _ in wins:
            if fa - pointer > 4:
                key_ikfk(pointer, 1.0)
                key_ikfk(fa - 2, 1.0)
            key_ikfk(fa, 0.0)
            key_ikfk(fb, 0.0)
            pointer = fb + 2
        if keys[2][0] - pointer > 4:
            key_ikfk(pointer, 1.0)
            key_ikfk(keys[2][0], 1.0)
        key_ikfk(keys[3][0], 0.0)
    return anchors


def _anchors(act, start, fps, speed, keys, plant, holds=()):
    """Where each planted stretch of the clip puts the character's own foot: {side: [(frame a, frame b,
    (x, y))]} in scene frames and world metres. The clip says when a foot is planted (motion.stance_windows);
    the anchor is the measured position at the start of the stretch, and the foot is pinned there by IK."""
    out = {}
    f0, f1 = keys[1][0], keys[2][0]
    for side, wins in plant.items():
        rows = []
        for wa, wb, _ in wins:
            fa = max(f0, int(round(start + motion.to_scene(wa, fps, speed, holds))))
            fb = min(f1, int(round(start + motion.to_scene(wb, fps, speed, holds))))
            if fb - fa < 5:
                continue
            bpy.context.scene.frame_set(fa)
            ev = act.rig.evaluated_get(bpy.context.evaluated_depsgraph_get())
            bone = ev.pose.bones.get(f"DEF-foot.{side}")
            if bone is None:
                continue
            w = ev.matrix_world @ bone.head
            rows.append((fa, fb, (w.x, w.y)))
        if rows:
            out[side] = rows
    return out
