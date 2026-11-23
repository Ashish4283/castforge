"""CastForge scene kit: scene.json (background, sound, cast, script) -> animated, lip-synced MP4.

    blender -b -y -P scene_kit.py -- --scene scene.json --out episode.mp4 [--stills 1,60,120]

scene.json
    {"fps": 24, "resolution": [1280, 720],
     "background": "bg.png", "ambience": "room.wav", "ambience_volume": 0.5,
     "cast": {"maya": {"character": "maya.blend", "voice": "af_heart", "position": [-0.8, 0],
                       "facing": "camera"}, ...},
     "props": [{"file": "table.glb", "position": [0.3, 0.9], "rotation": 0, "scale": 1.0}],
     "floor": "wood",
     "script": [
        {"who": "tom", "do": "walk", "to": [0.7, 0]},
        {"who": "maya", "do": "face", "target": "tom", "with": "previous"},
        {"who": "maya", "do": "say", "audio": "line1.wav"},          # a voice file (e.g. from Gemini)
        {"who": "tom", "do": "say", "text": "Hi!"},                    # or text, spoken with tom's voice
        {"do": "wait", "seconds": 0.5}]}

Steps run one after another; "with": "previous" starts a step together with the one before.
Stage coordinates are metres: x to the right, y away from the camera. Positions/paths are on the floor.
Everything is keyed into one .blend (saved next to the video) so it can be opened and tweaked by hand.
The full vocabulary (acting, camera, sound, lighting and weather steps and settings) is in core/schema.py.

Writes <out> (picture + preview sound), <out>.wav (the scene's float stereo mix, mastered later by
core/finish.py), <out>.timeline.json (lines and shots, for subtitles and chapters) and <out>.blend.
--storyboard renders one small still per shot into <out dir>/storyboard/ instead of the scene.
"""
import argparse
import json
import math
import os
import random
import statistics
import subprocess
import sys

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--scene", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--stills", help="comma-separated frames to render as PNG instead of the video")
ap.add_argument("--storyboard", action="store_true", help="one still per shot instead of the video")
ap.add_argument("--preview3d", action="store_true",
                help="preview.glb + preview.json for the app's scene editor instead of the video")
ap.add_argument("--keep-frames", action="store_true", help="keep the rendered PNG frames after the MP4 is made")
ap.add_argument("--render-key", help="the scene's render key from episode_job.py (the same one guards the frames)")
ap.add_argument("--quality", help="blocking (default) | draft | standard | final | ultra; overrides scene.json")
args = ap.parse_args(argv)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p_ in (ROOT, HERE):
    if p_ not in sys.path:
        sys.path.insert(0, p_)
import acting  # noqa: E402
import director  # noqa: E402
import motion  # noqa: E402
import motion_rig  # noqa: E402
import world as world_kit  # noqa: E402
from core import config, media, schema, sets  # noqa: E402

RHUBARB = config.RHUBARB
SCENE_DIR = os.path.dirname(os.path.abspath(args.scene))
spec = json.load(open(args.scene, encoding="utf-8"))
FPS = spec.get("fps", 24)
rand = random.Random(spec.get("seed", 7))
QUALITY = "draft" if args.storyboard else (args.quality or spec.get("quality", "blocking"))
if QUALITY not in config.QUALITY:
    sys.exit(f"CF: FAILED unknown quality {QUALITY!r} ({', '.join(config.QUALITY)})")
FAST = QUALITY in ("blocking", "draft")


def path(p):
    return p if os.path.isabs(p) else os.path.join(SCENE_DIR, p)


def log(*a):
    print("CF:", *a, flush=True)


bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.fps = FPS
scene.render.resolution_x, scene.render.resolution_y = spec.get("resolution", [1280, 720])


def smooth01(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


# --- cast ------------------------------------------------------------------------------------------
class Actor:
    WALK_SPEED, STEP, FOOT_GAP = 1.1, 0.62, 0.10

    def __init__(self, cid, blend):
        with bpy.data.libraries.load(path(blend), link=False) as (src, dst):
            dst.objects = list(src.objects)
        coll = bpy.data.collections.new(cid)
        scene.collection.children.link(coll)
        hidden = bpy.data.collections.new(cid + "_widgets")
        scene.collection.children.link(hidden)
        hidden.hide_render = hidden.hide_viewport = True
        objs = [o for o in dst.objects if o is not None]
        for o in objs:
            (hidden if o.name.startswith("WGT-") else coll).objects.link(o)
        self.rig = next(o for o in objs if o.type == "ARMATURE" and o.name.startswith("CastForge_Rig"))
        for o in objs:
            if o.type == "ARMATURE" and o is not self.rig:
                o.hide_render = o.hide_viewport = True
        self.body = next(o for o in objs if o.type == "MESH" and o.data.shape_keys
                         and "viseme_aa" in o.data.shape_keys.key_blocks)
        self.keys = self.body.data.shape_keys.key_blocks
        self.muscle_keys = self._ensure_muscle_correctives()
        self.id = cid
        self.pb = self.rig.pose.bones
        for side in ("L", "R"):
            self.pb[f"thigh_parent.{side}"]["IK_FK"] = 0.0      # legs: IK (feet stay planted)
            self.pb[f"upper_arm_parent.{side}"]["IK_FK"] = 1.0  # arms: FK
        self.pos = Vector((0, 0, 0))
        self.heading = 0.0
        self.feet = {}                   # side -> world position of the planted foot
        self.foot_heading = {}           # side -> world direction each foot points (feet turn on their own)
        self.speaking = []               # (start_s, end_s) of lines, for head motion
        self.footfalls = []              # (frame, position) where a foot lands (footstep sounds)
        self.walk_frames = set()         # frames owned by a walk (no idle sway there)
        self.chest_yaw = {}              # frame -> chest counter-rotation while walking
        self.stresses = []               # times (s) of stressed syllables, for nods and brows
        self.seated = None               # the seat (props.SEATS entry) while sitting
        self.driving = []                # (start, end) frames with hands on a steering wheel
        self.holding = []                # [start frame, end frame or None, "L"/"R", prop root, shape, curl]
        self.clip_hands = []             # [start, end, shape, grip] hand shapes a motion clip needs
        self.wrist_keyed = {}            # side -> the wrist is away from neutral, so key it back on the way out
        self.thinking = []               # (start_s, end_s) of inner-voice thoughts (head lowers a little)
        self.seated_ranges = []          # [start, end] frames spent sitting (end None = to the end)
        self.sit_torso = Vector((0, 0, 0))
        self.head_yaw = [(1, 0.0)]       # (frame, yaw): head turns used while seated
        self.arm_q = self._relaxed_arms()
        self.expression = acting.Layer({}, blend=0.35)       # face (and body nudges) over time
        self.posture = acting.Layer({}, blend=0.8)           # chest/head pitch, shoulder lift, stance
        self.gestures = []               # (start_s, seconds, name, options, hand)
        self.looks = []                  # (start_s, end_s, target): head and eyes only
        self.gaze = True                 # eyes look at whoever matters
        self.voice_fx = "clean"
        self.turn_blinks = []            # frames: a blink as the head swings into a big turn
        self.stance_width = 1.0          # foot spacing (a confident stance is wider)

    def _ensure_muscle_correctives(self):
        """Create subtle, rig-weighted flex shapes when a character has the expected Rigify groups."""
        definitions = {
            "upper_arm.L": 0.008, "upper_arm.R": 0.008,
            "thigh.L": 0.012, "thigh.R": 0.012,
        }
        out = {}
        rig_to_body = self.body.matrix_world.inverted() @ self.rig.matrix_world
        for region, amplitude in definitions.items():
            group = self.body.vertex_groups.get(f"DEF-{region}")
            bone = self.rig.data.bones.get(f"DEF-{region}")
            if group is None or bone is None:
                log(f"WARNING {self.id}: no DEF-{region} weights/bone; muscle flex omitted")
                continue
            head = rig_to_body @ bone.head_local
            tail = rig_to_body @ bone.tail_local
            axis = tail - head
            length = axis.length
            if length < 1e-5:
                log(f"WARNING {self.id}: DEF-{region} has zero length; muscle flex omitted")
                continue
            axis.normalize()
            deltas = []
            for vertex in self.body.data.vertices:
                weight = next((membership.weight for membership in vertex.groups
                               if membership.group == group.index), 0.0)
                if weight <= 0.01:
                    continue
                distance = (vertex.co - head).dot(axis)
                if not 0.0 < distance < length:
                    continue
                radial = vertex.co - (head + axis * distance)
                if radial.length < 1e-5:
                    continue
                phase = distance / length
                profile = math.sin(math.pi * phase) ** 2
                deltas.append((vertex.index, radial.normalized() * amplitude * profile * weight))
            if len(deltas) < 8:
                log(f"WARNING {self.id}: too few DEF-{region} vertices for muscle flex; omitted")
                continue
            name = f"cf_muscle_{region.replace('.', '_')}"
            key = self.keys.get(name)
            if key is None:
                key = self.body.shape_key_add(name=name, from_mix=False)
                for index, delta in deltas:
                    key.data[index].co += delta
            out[region] = key
        return out

    def key_muscle(self, region, value, frame):
        key = self.muscle_keys.get(region)
        if key is not None:
            key.value = min(1.0, max(0.0, value))
            key.keyframe_insert("value", frame=frame)

    # rig-local <-> world
    def rot(self, heading=None):
        return Matrix.Rotation(self.heading if heading is None else heading, 3, "Z")

    def stand_feet(self):
        for side, sx in (("L", 1), ("R", -1)):
            rest = self.pb[f"foot_ik.{side}"].bone.head_local
            self.feet[side] = self.pos + self.rot() @ Vector((sx * 0.12 * self.stance_width, rest.y, 0))
            self.foot_heading[side] = self.heading

    def stance(self, side, heading=None, centre=None):
        """Where a foot stands when the person stands still at centre facing heading."""
        rest = self.pb[f"foot_ik.{side}"].bone.head_local
        sx = 1 if side == "L" else -1
        return (self.pos if centre is None else centre) + self.rot(heading) @ Vector((sx * 0.12 * self.stance_width, rest.y, 0))

    def _relaxed_arms(self):
        """Local rotations that bring the A-pose arms down to a relaxed stance."""
        out = {}
        for side, sx in (("L", 1), ("R", -1)):
            ua, fa = self.pb[f"upper_arm_fk.{side}"].bone, self.pb[f"forearm_fk.{side}"].bone
            ua_rest = ua.matrix_local.to_3x3()
            fa_rest = fa.matrix_local.to_3x3()
            d_ua = (ua.tail_local - ua.head_local).normalized()
            r_ua = d_ua.rotation_difference(Vector((sx * 0.12, 0.02, -1)).normalized()).to_matrix()
            d_fa = r_ua @ (fa.tail_local - fa.head_local).normalized()
            r_fix = d_fa.rotation_difference(Vector((sx * 0.05, -0.22, -1)).normalized()).to_matrix()
            out[side] = (ua_rest, r_ua, fa_rest, r_fix, d_ua)
        return out

    def key_arms(self, frame, swing_l=0.0, swing_r=0.0, bend_l=0.0, bend_r=0.0, raise_l=0.0, raise_r=0.0,
                 twist_l=0.0, twist_r=0.0, sides=("L", "R"), wrist_l=0.0, wrist_r=0.0):
        """Arms down and relaxed; swing forward(-)/back(+) at the shoulder, raise out to the side, twist the
        upper arm (+ turns the palm forward), extra elbow bend. The elbow hinge turns with the upper arm, so a
        raised, twisted arm bends upwards (a wave). Only the arms in `sides` are keyed."""
        for side, swing, bend, lift, twist, wrist in (("L", swing_l, bend_l, raise_l, twist_l, wrist_l),
                                                      ("R", swing_r, bend_r, raise_r, twist_r, wrist_r)):
            if side not in sides:
                continue
            # the wrist: + tips the fingers back and up, as when the palms meet in a clap. Only keyed when
            # a gesture asks for it (and once more at 0 on the way out), so motion clips keep their own hands.
            if wrist or self.wrist_keyed.get(side):
                p_h = self.pb.get(f"hand_fk.{side}")
                if p_h:
                    p_h.rotation_mode = "QUATERNION"
                    p_h.rotation_quaternion = Matrix.Rotation(wrist, 3, "X").to_quaternion()
                    p_h.keyframe_insert("rotation_quaternion", frame=frame)
                    self.wrist_keyed[side] = bool(wrist)
            ua_rest, r_ua, fa_rest, r_fix, d_ua = self.arm_q[side]
            sx = 1 if side == "L" else -1
            delta = Matrix.Rotation(swing, 3, "X") @ Matrix.Rotation(-sx * lift, 3, "Y")
            if twist:
                delta = Matrix.Rotation(sx * twist, 3, delta @ r_ua @ d_ua) @ delta
            r = delta @ r_ua
            forearm = Matrix.Rotation(-bend, 3, delta @ Vector((1, 0, 0))) @ delta @ r_fix @ r_ua
            fa = r.inverted() @ forearm                                    # relative to the upper arm
            for name, rest, rr in ((f"upper_arm_fk.{side}", ua_rest, r), (f"forearm_fk.{side}", fa_rest, fa)):
                p = self.pb[name]
                p.rotation_mode = "QUATERNION"
                p.rotation_quaternion = (rest.inverted() @ rr @ rest).to_quaternion()
                p.keyframe_insert("rotation_quaternion", frame=frame)
            self.key_muscle(f"upper_arm.{side}", max(0.0, bend - 0.12) * 0.7, frame)

    def key_fingers(self, frame, open_l=0.0, open_r=0.0, shape_l=None, shape_r=None, grip_l=0.0, grip_r=0.0,
                    curl_l=1.0, curl_r=1.0):
        """Relaxed fingers; open_* (0..1) straightens them for an open, gesturing hand; shape_* (point, fist,
        thumbs, flat, grip) curls them into a hand shape by grip_* (0..1). curl_* scales the closed shape, so
        a hand round a thick prop stops where the prop is instead of closing through it."""
        for side, op, shape, grip, cs in (("L", open_l, shape_l, grip_l, curl_l),
                                          ("R", open_r, shape_r, grip_r, curl_r)):
            curls, thumb = acting.finger_curls(op, shape, grip)
            if cs != 1.0:
                curls = {f: c * cs for f, c in curls.items()}
                thumb *= cs
            for finger, curl in curls.items():
                for seg, w in acting.SEGMENT.items():
                    p = self.pb.get(f"f_{finger}.{seg}.{side}")
                    if p:
                        p.rotation_mode = "XYZ"
                        p.rotation_euler = (curl * w, 0, 0)
                        p.keyframe_insert("rotation_euler", frame=frame)
            for seg, v in acting.THUMB.items():
                p = self.pb.get(f"thumb.{seg}.{side}")
                if p:
                    p.rotation_mode = "XYZ"
                    p.rotation_euler = (v * thumb, 0, 0)
                    p.keyframe_insert("rotation_euler", frame=frame)

    def key_shoulders(self, frame, lift_l=0.0, lift_r=0.0):
        """Shoulder lift (+ up, as in a shrug or tension; - dropped and relaxed)."""
        for side, lift in (("L", lift_l), ("R", lift_r)):
            if f"shoulder.{side}" in self.pb:
                sx = 1 if side == "L" else -1
                self.key_rot(f"shoulder.{side}", Matrix.Rotation(-sx * 0.25 * lift, 3, "Y"), frame)

    def key_rot(self, bone, rot_arm, frame):
        """Rotate a control by an armature-space rotation (3x3) about its own head."""
        p = self.pb[bone]
        rest = p.bone.matrix_local.to_3x3()
        p.rotation_mode = "QUATERNION"
        p.rotation_quaternion = (rest.inverted() @ rot_arm @ rest).to_quaternion()
        p.keyframe_insert("rotation_quaternion", frame=frame)

    def key_roll(self, frame, roll_l=0.0, roll_r=0.0):
        """Foot roll: + lifts the heel (push-off on the toes), - lifts the toes (heel strike)."""
        for side, roll in (("L", roll_l), ("R", roll_r)):
            p = self.pb[f"foot_heel_ik.{side}"]
            p.rotation_mode = "XYZ"
            p.rotation_euler = (roll, 0, 0)
            p.keyframe_insert("rotation_euler", frame=frame)

    def key_offset(self, bone, offset_arm, frame):
        """Translate a root-level control by an armature-space offset from its rest position."""
        p = self.pb[bone]
        p.location = p.bone.matrix_local.to_3x3().inverted() @ offset_arm
        p.keyframe_insert("location", frame=frame)

    def key_root(self, frame):
        self.rig.location = self.pos
        self.rig.rotation_euler = (0, 0, self.heading)
        self.rig.keyframe_insert("location", frame=frame)
        self.rig.keyframe_insert("rotation_euler", frame=frame)

    def key_feet(self, frame, lift=None):
        inv = self.rot().inverted()
        for side in ("L", "R"):
            rest = self.pb[f"foot_ik.{side}"].bone.head_local
            local = inv @ (self.feet[side] - self.pos)
            off = Vector((local.x - rest.x, local.y - rest.y, (lift or {}).get(side, 0.0)))
            self.key_offset(f"foot_ik.{side}", off, frame)
            yaw = (self.foot_heading.get(side, self.heading) - self.heading + math.pi) % (2 * math.pi) - math.pi
            self.key_rot(f"foot_ik.{side}", Matrix.Rotation(yaw, 3, "Z"), frame)

    def key_pose(self, frame, bob=0.0, sway=0.0, swing=0.0):
        self.key_root(frame)
        self.key_feet(frame)
        self.key_roll(frame)
        self.key_offset("torso", Vector((sway, 0, -0.015 + bob - self.pdrop(frame))), frame)
        self.key_rot("torso", Matrix.Identity(3), frame)
        self.key_arms(frame, swing, -swing, 0.12, 0.12)
        self.key_muscle("thigh.L", 0.0, frame)
        self.key_muscle("thigh.R", 0.0, frame)

    def pdrop(self, frame):
        """How far the posture sinks the hips at this frame (crouch), in metres."""
        return self.posture.at(frame / FPS).get("drop", 0.0)

    # actions ----------------------------------------------------------------------------------------
    def face(self, target_heading, f0, dur=0.45):
        d = (target_heading - self.heading + math.pi) % (2 * math.pi) - math.pi
        if self.seated:
            # sitting people turn head and shoulders, not the chair
            yaw = max(-1.0, min(1.0, d))
            self.head_yaw += [(f0, self.head_yaw[-1][1]), (f0 + int(dur * FPS), yaw)]
            return f0 + int(dur * FPS)
        if abs(d) < 0.05:
            return f0
        n = max(2, int(dur * FPS))
        # people look first, then turn: the head leads the body by a few frames
        lead = max(-0.6, min(0.6, d * 0.45))
        if abs(d) > 0.6:                           # a big turn: people blink as the head swings round
            self.turn_blinks.append(f0 + 1)
        self.head_yaw += [(f0 - 3, self.head_yaw[-1][1]), (f0 + n // 3, lead), (f0 + n + 4, 0.0)]
        h0, centre = self.heading, self.pos.copy()
        n = max(n, int((0.45 + 0.45 * abs(d) / math.pi) * FPS))      # bigger turns take longer
        h1 = h0 + d
        old_fwd, new_fwd = self.rot(h0) @ Vector((0, -1, 0)), self.rot(h1) @ Vector((0, -1, 0))
        left = self.rot(h0) @ Vector((1, 0, 0))
        lead = "L" if left.dot(new_fwd - old_fwd) > 0 else "R"
        trail = "R" if lead == "L" else "L"
        start = {sd: self.feet[sd].copy() for sd in ("L", "R")}
        start_h = {sd: self.foot_heading.get(sd, h0) for sd in ("L", "R")}
        goal = {sd: self.stance(sd, h1, centre) for sd in ("L", "R")}
        windows = {lead: (0.0, 0.55), trail: (0.4, 0.95)}
        lift_h = 0.03 + 0.04 * min(abs(d) / 1.5, 1.0)
        for i in range(n + 1):
            u = i / n
            self.heading = h0 + d * smooth01(u)
            lift = {}
            for sd, (wa, wb) in windows.items():
                v = min(max((u - wa) / (wb - wa), 0.0), 1.0)
                self.feet[sd] = start[sd].lerp(goal[sd], smooth01(v))
                dh = (h1 - start_h[sd] + math.pi) % (2 * math.pi) - math.pi
                self.foot_heading[sd] = start_h[sd] + dh * smooth01(v)
                lift[sd] = lift_h * math.sin(math.pi * v)
            f = f0 + i
            self.key_root(f)
            self.key_feet(f, lift)
            self.key_roll(f)
            # weight shifts onto the standing foot while the other one steps; knees soften a little
            stepping = lead if u < 0.5 else trail
            sx = 1 if stepping == "L" else -1
            self.key_offset("torso", Vector((-0.015 * sx * math.sin(math.pi * u * 2) ** 2, 0,
                                              -0.025 - 0.01 * math.sin(math.pi * u) - self.pdrop(f))), f)
            self.key_rot("torso", Matrix.Identity(3), f)
            self.key_arms(f, 0.0, 0.0, 0.12, 0.12)
            self.walk_frames.add(f)
        self.foot_heading = {sd: h1 for sd in ("L", "R")}
        return f0 + n

    def visible(self, frame, show):
        for o in self.rig.children_recursive:
            if o.type == "MESH":
                o.hide_render = o.hide_viewport = not show
                o.keyframe_insert("hide_render", frame=frame)
                o.keyframe_insert("hide_viewport", frame=frame)

    def sit_pose(self, seat):
        """Where the body goes when sitting on seat: root over the seat, pelvis lowered to it."""
        root = seat["centre"] + seat["front"] * 0.06
        drop = (seat["seat_h"] + 0.09) - self.pb["torso"].bone.head_local.z
        return root, Vector((0, 0, drop))

    def sit(self, seat, f0, dur=1.1, instant=False):
        """Turn the back to the seat and sit down: pelvis back and down, feet stay, hands to the thighs."""
        self.heading = seat["heading"]
        stand_at = seat["centre"] + seat["front"] * 0.5
        root, drop = self.sit_pose(seat)
        if instant:
            self.pos = stand_at
            self.stand_feet()
            for s in ("L", "R"):
                self.feet[s] += seat["front"] * 0.02
            self.pos, self.sit_torso = root, drop
            self.key_root(f0); self.key_feet(f0); self.key_roll(f0)
            self.key_offset("torso", drop, f0)
            self.key_rot("torso", Matrix.Rotation(-0.05, 3, "X"), f0)
            self.key_arms(f0, -0.32, -0.32, 0.62, 0.62)
            n = 0
        else:
            n = max(2, int(dur * FPS))
            start = self.pos.copy()
            for i in range(n + 1):
                u = smooth01(i / n)
                self.pos = start.lerp(root, u)
                f = f0 + i
                self.key_root(f)
                self.key_feet(f)
                self.key_offset("torso", drop * u, f)
                # lean forward while lowering, settle upright on the seat
                self.key_rot("torso", Matrix.Rotation(0.3 * math.sin(math.pi * u) - 0.05 * u, 3, "X"), f)
                self.key_arms(f, -0.5 * u, -0.5 * u, 0.12 + 0.93 * u, 0.12 + 0.93 * u)
                self.walk_frames.add(f)
            self.sit_torso = drop
        self.seated = seat
        self.seated_ranges.append([f0 + n, None, drop.copy()])
        return f0 + n

    def stand(self, f0, dur=1.0):
        if not self.seated:
            return f0
        seat = self.seated
        n = max(2, int(dur * FPS))
        start, target = self.pos.copy(), seat["centre"] + seat["front"] * 0.5
        self.seated_ranges[-1][1] = f0
        for i in range(n + 1):
            u = smooth01(i / n)
            self.pos = start.lerp(target, u)
            f = f0 + i
            self.key_root(f)
            self.key_feet(f)
            self.key_offset("torso", self.sit_torso * (1 - u) + Vector((0, 0, -0.015)) * u, f)
            self.key_rot("torso", Matrix.Rotation(0.3 * math.sin(math.pi * u) - 0.05 * (1 - u), 3, "X"), f)
            self.key_arms(f, -0.5 * (1 - u), -0.5 * (1 - u), 1.05 - 0.93 * u, 1.05 - 0.93 * u)
            self.walk_frames.add(f)
        self.seated = None
        self.sit_torso = Vector((0, 0, 0))
        self.head_yaw += [(f0, self.head_yaw[-1][1]), (f0 + n, 0.0)]
        return f0 + n

    def walk(self, target, f0, waypoints=None, pace="normal"):
        """Walk to target (world Vector) along waypoints (planned around obstacles), feet planted.
        pace (acting.PACES) sets speed, stride, arm swing and lean."""
        speed, stride, swing_k, lean = acting.PACES.get(pace, acting.PACES["normal"])
        if self.seated:
            f0 = self.stand(f0)
        pts = [self.pos.copy()] + [Vector(p) for p in (waypoints or [])] + [target.copy()]
        seg = [(pts[i + 1] - pts[i]).length for i in range(len(pts) - 1)]
        dist = sum(seg)
        if dist < 0.05:
            return f0

        def at(s):
            s = min(max(s, 0.0), dist)
            for i, L in enumerate(seg):
                if s <= L or i == len(seg) - 1:
                    d = (pts[i + 1] - pts[i]).normalized() if L > 1e-6 else Vector((0, -1, 0))
                    return pts[i] + d * min(s, L), d
                s -= L

        def tangent(s):     # direction smoothed over +-0.3 m, so corners become curves
            acc = Vector((0, 0, 0))
            for ds in (-0.3, -0.15, 0.0, 0.15, 0.3):
                acc += at(s + ds)[1]
            return acc.normalized()

        def left_of(d):
            return Vector((-d.y, d.x, 0))

        t0 = tangent(0.0)
        f0 = self.face(math.atan2(t0.x, -t0.y), f0)
        n_steps = max(2, math.ceil(dist / stride) + 1)
        step_dist = dist / n_steps
        ts = step_dist / speed
        durations = [
            ts * (1.0 + 0.25 * max(0.0, 1.0 - min(k, n_steps - 1 - k) / 2.0))
            for k in range(n_steps)
        ]
        step_times = [0.0]
        for duration in durations:
            step_times.append(step_times[-1] + duration)
        total = step_times[-1]

        # each step: which foot swings, from where, to where (feet land a little ahead of the body;
        # the last two steps bring both feet together at the target)
        steps, last = [], {s: self.feet[s].copy() for s in ("L", "R")}
        for k in range(n_steps):
            side = "R" if k % 2 == 0 else "L"
            sx = 1 if side == "L" else -1
            land = dist if k >= n_steps - 2 else min(dist, step_dist * (k + 1) + 0.35 * stride)
            to_ = at(land)[0] + left_of(tangent(land)) * sx * self.FOOT_GAP
            steps.append((side, last[side], to_))
            last[side] = to_
        planted = {s: self.feet[s].copy() for s in ("L", "R")}
        planted_h = {s: self.foot_heading.get(s, self.heading) for s in ("L", "R")}

        def heading_at(dd):
            v = tangent(min(dist, dd))
            return math.atan2(v.x, -v.y)

        step_h = [heading_at(min(dist, step_dist * (k + 1) + 0.35 * stride))
                  for k in range(n_steps)]
        for k in range(n_steps):
            self.footfalls.append((f0 + int(round(step_times[k + 1] * FPS)), steps[k][2].copy()))
        frames = int(round(total * FPS))
        current = 0
        for i in range(frames + 1):
            t = i / FPS
            k = next((index for index in range(n_steps) if t < step_times[index + 1]), n_steps - 1)
            u = min(max((t - step_times[k]) / durations[k], 0.0), 1.0)
            stride_phase = k + u
            while current < k:                       # steps finished since the last frame
                sd = steps[current][0]
                planted[sd] = steps[current][2]
                planted_h[sd] = step_h[current]
                current += 1
            side, a, b = steps[k]
            other = "L" if side == "R" else "R"
            self.feet = dict(planted)
            # the foot leaves late and fast: it stays back while the knee bends, then swings through
            self.feet[side] = a.lerp(b, smooth01((u - 0.08) / 0.84))
            self.foot_heading = dict(planted_h)
            dh = (step_h[k] - planted_h[side] + math.pi) % (2 * math.pi) - math.pi
            self.foot_heading[side] = planted_h[side] + dh * smooth01(u)
            # foot arc: the heel comes up behind (the knee bends), lowest clearance mid-swing
            lift = {side: 0.11 * math.sin(math.pi * min(u / 0.75, 1.0)) ** 1.5 * (1.0 - 0.35 * u)}
            s_now = step_dist * stride_phase
            self.pos = at(s_now)[0]
            dvec = tangent(s_now)
            h = math.atan2(dvec.x, -dvec.y)
            self.heading += (h - self.heading + math.pi) % (2 * math.pi) - math.pi   # no 360 jumps
            phase = math.sin(math.pi * stride_phase)                # +: left leg forward
            arm_phase = math.sin(math.pi * (stride_phase - 0.12))   # arms follow the legs a little late
            sw = 1 if side == "L" else -1
            ramp = smooth01(t / (0.6 * ts)) * smooth01((total - t) / (0.6 * ts))   # moves grow, then settle
            f = f0 + i
            self.key_root(f)
            self.key_feet(f, lift)
            # heel-toe: the swinging foot leaves on its toes and lands heel-first; the standing foot
            # flattens after landing and lifts its heel late in the step, ready to push off
            roll = {side: 0.5 * (1 - smooth01(u / 0.3)) - 0.3 * smooth01((u - 0.7) / 0.3)}
            roll[other] = -0.3 * (1 - smooth01(u / 0.2)) if k > 0 else 0.0
            roll[other] += 0.4 * smooth01((u - 0.6) / 0.4) if k < n_steps - 2 else 0.0
            self.key_roll(f, roll["L"], roll["R"])
            # body: rides over the standing leg (sway), lowest at heel strike, knees never locked
            self.key_offset("torso", Vector((-0.022 * sw * math.sin(math.pi * u) * ramp, 0,
                                              -0.045 + 0.022 * math.sin(math.pi * u) * ramp - self.pdrop(f))), f)
            # lean a little forward; pelvis turns with the swinging leg and drops on the swinging side
            self.key_rot("torso", Matrix.Rotation((0.07 + lean) * ramp, 3, "X")
                         @ Matrix.Rotation(0.08 * phase * ramp, 3, "Z")
                         @ Matrix.Rotation(0.035 * sw * math.sin(math.pi * u) * ramp, 3, "Y"), f)
            self.chest_yaw[f] = -0.11 * phase * ramp
            self.walk_frames.add(f)
            # arms swing from the shoulder and the elbow, a bit unevenly, never like a march
            amp = 0.24 * swing_k * ramp
            self.key_arms(f, -amp * arm_phase, amp * 0.9 * arm_phase,
                          0.2 + 0.28 * max(0.0, arm_phase) * ramp, 0.2 + 0.28 * max(0.0, -arm_phase) * ramp)
            self.key_muscle("thigh.L", ramp * (0.10 + 0.22 * max(0.0, phase)), f)
            self.key_muscle("thigh.R", ramp * (0.10 + 0.22 * max(0.0, -phase)), f)
        self.pos = target
        self.feet = dict(last)
        self.foot_heading = {sd: self.heading for sd in ("L", "R")}
        end = f0 + frames
        self.key_pose(end + 4)
        return end + 4


def cam_spot():
    """Where the main camera will stand (it is placed after the script): in front of the stage, at eye level."""
    if SET:
        return Vector(SET["camera"]["location"])
    return Vector((0, -4.0, 1.45))


def heading_towards(a, b):
    d = b - a
    return math.atan2(d.x, -d.y)


# --- a built set, when the scene names one: its picture, its depth and everything standing in it ------
SET_FOLDER = path(spec["set_folder"]) if spec.get("set_folder") else None
if SET_FOLDER:
    blueprint = sets.read_blueprint(SET_FOLDER)
    set_picture = sets.picture(SET_FOLDER, blueprint.get("image"))
    if not set_picture:
        raise ValueError(f"the set {spec['set_folder']} has no picture")
    # the empty version when the set has one: its furniture is 3D now, so the painted copies must go
    empty_picture = sets.empty_picture(SET_FOLDER, blueprint)
    spec.setdefault("background", empty_picture or set_picture)      # the scene may still name its own
    blueprint_props = sets.resolve_paths(blueprint["props"], SET_FOLDER)
    spec["props"] = sets.merge_props(blueprint_props, spec.get("props"))
    log(f"set {os.path.basename(SET_FOLDER)}: {len(blueprint_props)} object(s) from the set, "
        f"{len(spec['props'])} in all" + (", in the empty room" if empty_picture else ""))

# --- 3D set from the background image (default): relief mesh + walkable floor map ---------------------
SET = None
if spec.get("set", "3d") == "3d":
    import shutil
    # a built set keeps its depth beside the set, so every scene on that set reads the same geometry
    set_dir = sets.geometry_dir(SET_FOLDER) if SET_FOLDER else os.path.join(SCENE_DIR, "set")
    set_json = os.path.join(set_dir, "set.json")
    bg = path(spec["background"])
    if not os.path.exists(set_json) or os.path.getmtime(set_json) < os.path.getmtime(bg):
        cmd = [config.AI_PYTHON, os.path.join(ROOT, "generate", "depth_set.py"), bg, set_dir]
        if spec.get("set_pitch") is not None:
            cmd += ["--pitch", str(spec["set_pitch"])]
        subprocess.run(cmd, check=True)
    SET = json.load(open(set_json))
    import numpy as np
    G = SET["grid"]
    walkable = np.unpackbits(np.array(SET["walkable"], dtype=np.uint8))[:G["h"] * G["w"]] \
        .reshape(G["h"], G["w"]).astype(bool)

    def floor_free(clearance):
        r = int(round(clearance / G["cell"]))
        blocked = ~walkable
        grown = blocked.copy()
        for di in range(-r, r + 1):
            for dj in range(-r, r + 1):
                if di * di + dj * dj <= r * r:
                    sh = np.zeros_like(blocked)
                    sh[max(di, 0):G["h"] + min(di, 0), max(dj, 0):G["w"] + min(dj, 0)] = \
                        blocked[max(-di, 0):G["h"] + min(-di, 0), max(-dj, 0):G["w"] + min(-dj, 0)]
                    grown |= sh
        return ~grown

    FREE = floor_free(0.25)
    ORIGIN = Vector((SET["stage_origin"][0], SET["stage_origin"][1], 0))
    log(f"3D set: {SET['faces']} triangles, {FREE.sum() * G['cell'] ** 2:.1f} m2 free floor")


def to_world(p):
    return Vector((p[0], p[1], 0)) + (ORIGIN if SET else Vector((0, 0, 0)))


def cell_of(v):
    return int((v.y - G["y0"]) / G["cell"]), int((v.x - G["x0"]) / G["cell"])


def world_of(i, j):
    return Vector((G["x0"] + (j + 0.5) * G["cell"], G["y0"] + (i + 0.5) * G["cell"], 0))


def nearest_free(v, free):
    i0, j0 = cell_of(v)
    best, best_d = None, 1e9
    for i, j in zip(*np.nonzero(free)):
        d = (i - i0) ** 2 + (j - j0) ** 2
        if d < best_d:
            best, best_d = (i, j), d
    return world_of(*best)


def free_near(v):
    """The nearest free floor spot to v (v itself if it is free)."""
    if not SET:
        return v
    i, j = cell_of(v)
    if 0 <= i < FREE.shape[0] and 0 <= j < FREE.shape[1] and FREE[i, j]:
        return v
    return nearest_free(v, FREE)


def plan_on_floor(a, b, free):
    """Waypoints from a to b around obstacles (A* on the floor map, then straightened)."""
    import heapq
    s, g = cell_of(a), cell_of(b)
    H_, W_ = free.shape
    ok = lambda c: 0 <= c[0] < H_ and 0 <= c[1] < W_ and free[c]  # noqa: E731
    lead_in = []
    if not ok(s):
        out_ = nearest_free(a, free)
        lead_in, s = [out_], cell_of(out_)
    if not ok(s) or not ok(g):
        return None
    came, cost = {s: None}, {s: 0.0}
    q = [(0.0, s)]
    while q:
        _, c = heapq.heappop(q)
        if c == g:
            break
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            n = (c[0] + di, c[1] + dj)
            if ok(n):
                nc = cost[c] + math.hypot(di, dj)
                if nc < cost.get(n, 1e9):
                    cost[n], came[n] = nc, c
                    heapq.heappush(q, (nc + math.hypot(g[0] - n[0], g[1] - n[1]), n))
    if g not in came:
        return None
    cells_ = [g]
    while came[cells_[-1]] is not None:
        cells_.append(came[cells_[-1]])
    cells_.reverse()

    def clear(c0, c1):
        n = int(max(abs(c1[0] - c0[0]), abs(c1[1] - c0[1]))) + 1
        return all(ok((round(c0[0] + (c1[0] - c0[0]) * k / n), round(c0[1] + (c1[1] - c0[1]) * k / n)))
                   for k in range(n + 1))

    keep, i = list(lead_in), 0
    while i < len(cells_) - 1:                 # straighten: jump to the farthest cell in clear sight
        j = len(cells_) - 1
        while j > i + 1 and not clear(cells_[i], cells_[j]):
            j -= 1
        if j < len(cells_) - 1:
            keep.append(world_of(*cells_[j]))
        i = j
    return keep


def plan(a, b):
    if not SET:
        return []
    route = plan_on_floor(a, b, FREE)
    if route is not None:
        return route
    log("WARNING no path with 25 cm clearance; retrying with 15 cm clearance")
    route = plan_on_floor(a, b, floor_free(0.15))
    if route is not None:
        log("using 15 cm fallback path; check this route for tight clearance")
        return route
    log("WARNING no free path; walking straight")
    return []


# --- props: built from a description ("make") or loaded from a file ("file"); solid, walk-around --------
sys.path.insert(0, HERE)
import props as prop_factory  # noqa: E402

prop_tops = {}


SEATS_ = prop_factory.SEATS
PROP_ROOTS = {}                     # prop id -> (root object, its scene entry), for hold and carry


def find_part(objects, name, pid, key):
    """The object called name in a loaded model (Blender may have added .001 to the name)."""
    for o in objects:
        if o.name == name or o.name.rsplit(".", 1)[0] == name:
            return o
    raise ValueError(f'{pid}: "{key}": no object called {name!r} in the model '
                     f'(it has: {", ".join(sorted(o.name for o in objects))})')


def wheel_pivot(pid, part):
    """Put a modelled steering wheel on a pivot at its centre whose Y axis is the wheel's axle (its thinnest
    side), so a "drive" step can turn it and keep the hands on its rim."""
    bpy.context.view_layer.update()
    dims = part.dimensions
    axle = min(range(3), key=lambda i: dims[i])
    local_centre = sum((Vector(c) for c in part.bound_box), Vector()) / 8
    centre = part.matrix_world @ local_centre
    basis = part.matrix_world.to_3x3().normalized()
    y = basis.col[axle].normalized()
    z = basis.col[(axle + 2) % 3].normalized()
    x = y.cross(z).normalized()
    pivot = bpy.data.objects.new(f"{pid}_pivot", None)
    scene.collection.objects.link(pivot)
    world = part.matrix_world.copy()
    pivot.parent = part.parent
    bpy.context.view_layer.update()
    pivot.matrix_world = Matrix.Translation(centre) @ Matrix((x, y, x.cross(y))).transposed().to_4x4()
    part.parent = pivot
    bpy.context.view_layer.update()
    part.matrix_world = world
    prop_factory.STEERING_WHEELS[pid] = pivot


def load_prop_file(prop, n):
    f = path(prop["file"])
    before = set(bpy.data.objects)
    ext = os.path.splitext(f)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=f)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=f)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=f)
    elif ext == ".blend":
        with bpy.data.libraries.load(f, link=False) as (source, destination):
            asset = "CastForge Prop Asset" in source.collections
            if asset:
                destination.collections = ["CastForge Prop Asset"]
            else:                       # a model made by hand in Blender: take every object in the file
                destination.objects = list(source.objects)
        if asset:
            collection = destination.collections[0]
            scene.collection.children.link(collection)
        else:
            collection = bpy.data.collections.new(prop.get("id", f"model_{n}"))
            scene.collection.children.link(collection)
            for o in destination.objects:
                if o is None:
                    continue
                if o.type in ("CAMERA", "LIGHT"):     # the scene brings its own camera and light
                    bpy.data.objects.remove(o)
                else:
                    collection.objects.link(o)
    else:
        raise ValueError(f"unsupported prop file {f}; use .blend, .glb, .gltf, .obj or .fbx")
    new = ([o for o in collection.all_objects if o not in before]
           if ext == ".blend" else [o for o in bpy.data.objects if o not in before])
    holder = bpy.data.objects.new(prop.get("id", f"prop_{n}"), None)
    scene.collection.objects.link(holder)
    for o in new:
        if o.parent is None:
            o.parent = holder
        if o.type == "MESH" and len(o.data.polygons) > 50000:        # dense AI meshes: keep ~50k faces
            dec = o.modifiers.new("cf_decimate", "DECIMATE")
            dec.ratio = 50000 / len(o.data.polygons)
    holder.scale = (prop.get("scale", 1.0),) * 3
    holder.rotation_euler = (0, 0, math.radians(prop.get("rotation", 0)))
    bpy.context.view_layer.update()
    meshes = [o for o in new if o.type == "MESH"]
    pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    lowest = min(p_.z for p_ in pts)
    w_ = to_world(prop.get("position", [0, 0]))
    base = prop_tops.get(prop.get("on"), 0.0)
    holder.location = (w_.x, w_.y, base + float(prop.get("elevation", 0.0)) - lowest)
    bpy.context.view_layer.update()
    pid = holder.name
    if prop.get("wheel"):                  # an object in the model is a steering wheel the hands can hold
        wheel_pivot(pid, find_part(new, prop["wheel"], pid, "wheel"))
    if prop.get("seat"):                   # an object in the model is the seat: sit on its top, at its middle
        part = find_part(new, prop["seat"], pid, "seat")
        pts_ = [part.matrix_world @ Vector(c) for c in part.bound_box]
        a = math.radians(prop.get("rotation", 0))
        SEATS_[pid] = {"seat_h": max(p_.z for p_ in pts_), "depth": float(prop.get("seat_depth", 0.45)),
                       "centre": Vector((sum(p_.x for p_ in pts_) / 8, sum(p_.y for p_ in pts_) / 8, 0)),
                       "front": Vector((math.sin(a), -math.cos(a), 0)), "heading": a}
    pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    xs_, ys_ = [p_.x for p_ in pts], [p_.y for p_ in pts]
    corners = [Vector((x, y, 0)) for x in (min(xs_), max(xs_)) for y in (min(ys_), max(ys_))]
    return holder, (None if prop.get("on") else corners), max(p_.z for p_ in pts)


def block_footprint(corners):
    """Mark a prop's floor footprint as not walkable (the body margin is added by the clearance)."""
    global FREE
    if not SET or not corners:
        return
    xs_, ys_ = [c.x for c in corners], [c.y for c in corners]
    pad = int(round(0.25 / G["cell"]))
    i0, j0 = cell_of(Vector((min(xs_), min(ys_), 0)))
    i1, j1 = cell_of(Vector((max(xs_), max(ys_), 0)))
    FREE[max(i0 - pad, 0):max(i1 + pad + 1, 0), max(j0 - pad, 0):max(j1 + pad + 1, 0)] = False


def measure_prop(root):
    """How big a built prop really is [w, d, h] in metres, from its own meshes. A prop made by `make` carries
    no size in the scene file, and guessing one (a 30 cm cube) puts the hand through the middle of it."""
    meshes = [o for o in [root, *root.children_recursive] if o.type == "MESH" and len(o.data.vertices)]
    if not meshes:
        return [0.3, 0.3, 0.3]
    # in the prop's own frame, because the grip talks about the prop's local axes
    inv = root.matrix_world.inverted()
    pts = [inv @ o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    return [max(p_[i] for p_ in pts) - min(p_[i] for p_ in pts) for i in range(3)]


picture_props = []
for n, prop in enumerate(spec.get("props", [])):
    if prop.get("make") == "picture_road":
        continue
    prop = dict(prop)
    if prop.get("outside_image"):
        prop["outside_image"] = path(prop["outside_image"])
    if "make" in prop:
        root, corners, top = prop_factory.build(prop, n, to_world, prop_tops)
    else:
        root, corners, top = load_prop_file(prop, n)
    if prop.get("picture_rect") and prop.get("make") != "door":
        picture_props.append((root, prop))
    if prop.get("picture_rect"):
        corners = None
    prop_tops[prop.get("id", root.name)] = top
    PROP_ROOTS[prop.get("id", root.name)] = (root, prop)
    block_footprint(corners)
    log("prop", prop.get("make") or os.path.basename(prop["file"]), prop.get("position"),
        "on " + prop["on"] if prop.get("on") else "")

SEATS, DOORS = prop_factory.SEATS, prop_factory.DOORS


def fit_picture_doors():
    """Doors with "picture_rect" ([left, top, right, bottom], fractions of the picture) are moved and sized
    so that, seen from the set camera, they cover exactly the door in the picture."""
    rect_doors = {k: d for k, d in DOORS.items() if d.get("rect")}
    if not SET or not rect_doors:
        return
    import numpy as np
    verts, uvs = [], []
    for line in open(os.path.join(set_dir, "set.obj")):
        if line.startswith("v "):
            verts.append([float(x) for x in line.split()[1:4]])
        elif line.startswith("vt "):
            uvs.append([float(x) for x in line.split()[1:3]])
    verts, uvs = np.array(verts), np.array(uvs)
    c = SET["camera"]
    cam_loc = Vector(c["location"])
    cam_rot = Euler((math.pi / 2 - c.get("pitch", 0.0), 0, 0)).to_matrix()
    W_, H_ = SET["size"]
    local = (verts - np.array(cam_loc)) @ np.array(cam_rot)            # world -> camera space
    for did, door in rect_doors.items():
        u0, v0, u1, v1 = door["rect"]
        m = (uvs[:, 0] >= u0) & (uvs[:, 0] <= u1) & (1 - uvs[:, 1] >= v0) & (1 - uvs[:, 1] <= v1)
        if not m.any():
            log(f"WARNING door {did}: picture_rect covers no part of the set")
            continue
        dist = float(np.median(-local[m, 2]))

        def ray(u, v):
            d = Vector(((u - 0.5) * c["sensor"] / c["lens"], (0.5 - v) * c["sensor"] * H_ / W_ / c["lens"], -1.0))
            return cam_loc + cam_rot @ (d * dist)

        bl, br, tl = ray(u0, v1), ray(u1, v1), ray(u0, v0)
        width, height = (br - bl).length, (tl - bl).length
        across = (br - bl).normalized()
        heading = math.atan2(across.y, across.x)
        root = door["hinge"].parent
        root.location = (bl + br) / 2
        root.rotation_euler = (0, 0, heading)
        # a little larger than the hole, so no sliver of the hole shows around the closed door
        root.scale = (width * 1.05 / door["width"], 1.0, height * 1.03 / door["height"])
        door["centre"] = Vector((root.location.x, root.location.y, 0))
        door["heading"] = heading
        door["front"] = Matrix.Rotation(heading, 3, "Z") @ Vector((0, -1, 0))
        door["across"] = Matrix.Rotation(heading, 3, "Z") @ Vector((1, 0, 0))
        door["picture_width"] = width
        log(f"door {did}: fitted to the picture, {width:.2f} x {height:.2f} m, {dist:.1f} m from the camera")


def fit_picture_props():
    """Fit 3D prop roots to image rectangles while keeping their depth and geometry."""
    if not picture_props:
        return
    if SET:
        import numpy as np
        vertices, uvs = [], []
        for line in open(os.path.join(set_dir, "set.obj")):
            if line.startswith("v "):
                vertices.append([float(x) for x in line.split()[1:4]])
            elif line.startswith("vt "):
                uvs.append([float(x) for x in line.split()[1:3]])
        vertices, uvs = np.array(vertices), np.array(uvs)
        camera = SET["camera"]
        camera_location = Vector(camera["location"])
        camera_rotation = Euler((math.pi / 2 - camera.get("pitch", 0.0), 0, 0)).to_matrix()
        image_width, image_height = SET["size"]
        lens, sensor = camera["lens"], camera["sensor"]
    elif "cam" in globals() and spec.get("camera"):
        camera_location = Vector(cam.location)
        camera_rotation = cam.matrix_world.to_3x3()
        image_width, image_height = scene.render.resolution_x, scene.render.resolution_y
        lens, sensor = cam.data.lens, cam.data.sensor_width
    else:
        return

    def image_ray(u, v):
        return Vector(((u - 0.5) * sensor / lens,
                       (0.5 - v) * sensor * image_height / (image_width * lens), -1.0))

    for root, prop in picture_props:
        u0, v0, u1, v1 = prop["picture_rect"]
        if SET:
            selected = ((uvs[:, 0] >= u0) & (uvs[:, 0] <= u1)
                        & (1 - uvs[:, 1] >= v0) & (1 - uvs[:, 1] <= v1))
            if not selected.any():
                log(f"WARNING prop {root.name}: picture_rect covers no part of the set")
                continue
            distance = float(np.median(-((vertices[selected] - np.array(camera_location)) @
                                         np.array(camera_rotation))[..., 2]))
        else:
            distance = 5.0
        if distance <= 0:
            log(f"WARNING prop {root.name}: picture_rect is behind the set camera")
            continue
        bl = camera_location + camera_rotation @ (image_ray(u0, v1) * distance)
        br = camera_location + camera_rotation @ (image_ray(u1, v1) * distance)
        tl = camera_location + camera_rotation @ (image_ray(u0, v0) * distance)
        width, height = (br - bl).length, (tl - bl).length
        centre = camera_location + camera_rotation @ (image_ray((u0 + u1) / 2, (v0 + v1) / 2) * distance)
        original_size = prop.get("size") or schema.PROP_TYPES[prop["make"]][0]
        if not original_size or min(original_size[0], original_size[2]) <= 0:
            raise ValueError(f"{root.name}: picture-fitted props need a positive width and height")
        heading = math.radians(float(prop.get("picture_heading", 0.0)))
        orientation = (camera_rotation @ Euler((-math.pi / 2, 0, 0)).to_matrix()
                       @ Euler((0, 0, heading)).to_matrix())
        root.rotation_euler = orientation.to_euler()
        scale = width / original_size[0]
        root.scale = (scale, scale, height / original_size[2])
        root.location = centre - orientation @ Vector((0, 0, height / 2))
        log(f"prop {root.name}: fitted to picture rectangle ({width:.2f} x {height:.2f} m)")
    prop_factory.update_attached_doors()


fit_picture_doors()
fit_picture_props()
entering = {}                      # cast id -> door id, for people whose first move is to enter
for st in spec["script"]:
    if st.get("do") == "enter" and st.get("who") not in entering:
        entering[st["who"]] = st["door"]

def feeling(name, intensity=1.0):
    """An expression as one blendable dict: ARKit face weights plus body nudges (_chest, _head, _shoulders)."""
    if not name or name not in acting.EXPRESSIONS:
        return {}
    value = dict(acting.EXPRESSIONS[name])
    value.update({f"_{k}": v for k, v in acting.EXPRESSION_BODY.get(name, {}).items()})
    return acting.scaled(value, max(0.0, min(float(intensity), 1.0)))


cast = {}
for cid, c in spec["cast"].items():
    act = Actor(cid, c["character"])
    act.stance_width = acting.POSTURES.get(c.get("posture", "neutral"), {}).get("stance", 1.0)
    if cid in entering:
        door = DOORS[entering[cid]]
        act.pos = door["centre"] - door["front"] * 0.9           # outside, beyond the daylight in the doorway
    else:
        act.pos = free_near(to_world(c.get("position", [0, 0])))
    act.heading = 0.0 if c.get("facing", "camera") == "camera" else math.radians(float(c["facing"]))
    if cid in entering:
        act.heading = DOORS[entering[cid]]["heading"]          # facing into the room
    act.stand_feet()
    act.key_pose(1)
    if c.get("sit"):
        act.sit(SEATS[c["sit"]], 1, instant=True)               # already seated when the scene starts
    if cid in entering:
        act.visible(1, False)
    act.expression = acting.Layer(feeling(c.get("expression")), blend=0.35)
    act.posture = acting.Layer(acting.POSTURES.get(c.get("posture", "neutral"), {}), blend=0.8)
    act.gaze = spec.get("gaze", True) and c.get("gaze", True)
    act.voice_fx = c.get("voice_fx", "clean")
    cast[cid] = act
log("cast", {k: os.path.basename(v["character"]) for k, v in spec["cast"].items()})


# --- lip-sync --------------------------------------------------------------------------------------
MOUTH, MOUTH_KEYS = acting.MOUTH, acting.MOUTH_KEYS       # speech shapes (see acting.py)


def mouth_cues(wav, transcript=None):
    out = wav + ".rhubarb.json"
    if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(wav):
        cmd = [RHUBARB, "-f", "json", "-o", out, "--extendedShapes", "GHX"]
        if transcript:
            txt = wav + ".txt"
            open(txt, "w", encoding="utf-8").write(transcript)
            cmd += ["-d", txt]
        subprocess.run(cmd + [wav], check=True, capture_output=True)
    return json.load(open(out))["mouthCues"]


def viseme_cues(wav, transcript=None):
    """Mouth cues as {start, end, viseme, weight}: exact ones from our TTS if present, else Rhubarb."""
    exact = wav + ".visemes.json"
    if os.path.exists(exact):
        cues = json.load(open(exact))["cues"]
        if cues:
            return cues
        log(f"WARNING no phoneme timing for {os.path.basename(wav)}; lip-sync from the audio instead")
    if not os.path.exists(RHUBARB):
        raise FileNotFoundError("lip-sync for audio files needs Rhubarb in tools/ (see README)")
    return [{"start": c["start"], "end": c["end"], "viseme": acting.RHUBARB_TO_VISEME[c["value"]],
             "weight": 0.0 if c["value"] == "X" else 1.0} for c in mouth_cues(wav, transcript)]


def key_lipsync(actor, cues, start_frame, strength=1.0):
    """Key every viseme each frame from the cues, with a quick (about 1.5-frame) cross-fade."""
    end = start_frame + int(math.ceil(cues[-1]["end"] * FPS)) + 2
    keys = [k for k in MOUTH_KEYS if k in actor.keys]
    prev = {k: 0.0 for k in keys}
    for f in range(start_frame - 1, end + 1):
        t = (f - start_frame) / FPS
        target = {k: 0.0 for k in keys}
        for c in cues:
            if c["start"] <= t < c["end"]:
                w = strength * c.get("weight", 1.0)
                for k, v in MOUTH[c["viseme"]].items():
                    if k in target:
                        target[k] = max(target[k], v * w)
        for k in keys:
            val = 0.3 * prev[k] + 0.7 * target[k]
            actor.keys[k].value = val
            actor.keys[k].keyframe_insert("value", frame=f)
            prev[k] = val
    for k in keys:
        actor.keys[k].value = 0.0
        actor.keys[k].keyframe_insert("value", frame=end + 2)


# --- voices: lines given as text are spoken with the character's voice (Kokoro, local) ------------
tts_jobs = []
voice_dir = os.path.join(SCENE_DIR, "voices")
for n, step in enumerate(spec["script"]):
    if step["do"] in ("say", "think", "narrate") and not step.get("audio"):
        if step["do"] == "narrate":
            voice = step.get("voice") or (spec.get("narrator") or {}).get("voice")
            speaker = "narrator"
        else:
            voice, speaker = spec["cast"][step["who"]].get("voice"), step["who"]
        if not voice:
            raise ValueError(f"{speaker} has a text line but no voice")
        step["audio"] = os.path.join(voice_dir, f"{n:03d}_{speaker}.wav")
        stamp = step["audio"] + ".src"
        src = json.dumps([voice, step["text"], step.get("speed", 1.0)])
        if not (os.path.exists(step["audio"]) and os.path.exists(stamp) and open(stamp).read() == src):
            tts_jobs.append({"text": step["text"], "voice": voice, "out": step["audio"],
                             "speed": step.get("speed", 1.0), "stamp": stamp, "src": src})
if tts_jobs:
    import shutil
    os.makedirs(voice_dir, exist_ok=True)
    jobs_file = os.path.join(voice_dir, "jobs.json")
    json.dump(tts_jobs, open(jobs_file, "w", encoding="utf-8"))
    subprocess.run([config.AI_PYTHON, os.path.join(ROOT, "generate", "tts.py"), jobs_file], check=True)
    for j in tts_jobs:
        open(j["stamp"], "w").write(j["src"])
    log(f"voiced {len(tts_jobs)} lines")

# --- script --------------------------------------------------------------------------------------
sounds = []                         # (path, frame, channel, world position or None): dialogue
sfx_events = []                     # (name, frame, volume, world position or None): one-shot effects
lines = []                          # spoken lines: f0, f1, who, kind, text, expression (director, subtitles)
moves = []                          # (actor, start_frame, end_frame) of walks, for the follow camera
beats = []                          # (attacker, defender, start, end, contact frame) of strike steps


def run_perform(who, step, start):
    """Play a motion clip on `who` from scene frame `start` (the perform step, also used by strike);
    step may carry "_holds" [(clip seconds, frames)] hit-stops. Returns the end frame."""
    clip = motion.load(config.MOTIONS_DIR, step["clip"])
    if clip is None:
        raise ValueError(f"no motion clip {step['clip']!r} (python castforge.py motion list)")
    t0, t1 = motion.window(clip, step.get("from", 0.0), step.get("to"))
    speed, travel = float(step.get("speed", 1.0)), step.get("travel", True)
    holds = tuple(step.get("_holds") or ())
    end = start + motion.scene_frames(t0, t1, FPS, speed, holds)
    keys = motion.fades(start, end, round(float(step.get("blend", 0.3)) * FPS))
    who.key_pose(start)
    who.key_pose(keys[1][0])
    shape_c, grip_c = acting.clip_hands(step.get("hands") or step["clip"])
    if shape_c:
        who.clip_hands.append((start, end, shape_c, grip_c))
    plant = {s: motion.stance_windows(clip, s, t0, t1) for s in ("L", "R")} if travel else None
    anchors = motion_rig.play(who, clip, t0, start, FPS, speed, keys, travel, plant=plant, holds=holds)
    move, turn, feet = motion.ending(clip, t0, t1)
    size, pos0, heading0 = motion_rig.hip_height(who), (who.pos.x, who.pos.y), who.heading
    track = clip["track"]
    i0 = motion.sample(track, t0)
    spin = Matrix.Rotation(heading0 - track["facing"][i0], 3, "Z")
    ratio = size / clip["hip_height"]
    if travel:
        # bake the clip's real path into the root (for the follow camera and everyone's gaze), and
        # pin whichever foot the clip says is planted at its measured spot (no slide)
        hx0, hy0 = track["hips"][i0][0], track["hips"][i0][1]
        for f in range(keys[1][0], keys[2][0] - 1, 2):
            t = min(t1, t0 + motion.to_clip(f - start, FPS, speed, holds))
            j = motion.sample(track, t)
            d = spin @ Vector(((track["hips"][j][0] - hx0) * ratio,
                               (track["hips"][j][1] - hy0) * ratio, 0.0))
            who.pos = Vector((pos0[0] + d.x, pos0[1] + d.y, 0.0))
            who.heading = heading0 + motion.wrap(track["facing"][j] - track["facing"][i0])
            who.key_root(f)
            pinned = False
            for side, wins in anchors.items():
                hit = next((w_ for w_ in wins if w_[0] <= f <= w_[1]), None)
                if hit:
                    who.feet[side] = Vector((hit[2][0], hit[2][1], 0.0))
                    who.foot_heading[side] = who.heading
                    pinned = True
            if pinned:
                who.key_feet(f)
        who.pos = Vector((*motion.to_world(pos0, heading0, size, move), 0.0))
        moves.append((who, start, end))
    for side, (x, y, yaw) in feet.items():          # the base pose takes over where the clip's feet ended
        last = anchors.get(side, []) if travel else []
        if last and last[-1][1] >= keys[2][0] - 3:
            who.feet[side] = Vector((last[-1][2][0], last[-1][2][1], 0.0))   # still pinned at the end
        else:
            local = (x, y) if travel else (x - move[0], y - move[1])
            who.feet[side] = Vector((*motion.to_world(pos0, heading0, size, local), 0.0))
        who.foot_heading[side] = heading0 + yaw
    who.heading = heading0 + turn
    who.key_pose(keys[2][0])
    who.key_pose(end)
    return end


def run_duck(who, start, seconds=1.0, depth=0.32):
    """Duck down fast and come back up (the duck step, and the dodge reaction of strike)."""
    seconds = max(0.4, seconds)
    n = max(6, int(seconds * FPS))
    who.posture.overlay(start / FPS, (start + n) / FPS, {"head": 0.30, "chest": 0.18, "shoulders": 0.5})
    for i in range(n + 1):
        u = i / n
        prof = smooth01(u / 0.3) * smooth01((1 - u) / 0.35)
        who.key_offset("torso", Vector((0.0, 0.02 * prof,
                                        -0.015 - depth * prof - who.pdrop(start + i))), start + i)
        who.walk_frames.add(start + i)
    brace_f = start + int(0.3 * n)
    who.key_arms(start, 0.0, 0.0, 0.12, 0.12)
    who.key_arms(brace_f, 0.18, -0.18, 0.55, 0.55, 0.10, 0.10)
    who.key_arms(start + n, 0.0, 0.0, 0.12, 0.12)
    return start + n


music_cues = []                     # (frame, bed or None to stop, volume, fade seconds)
forced = []                         # camera steps: {"f0", "seconds", "shot", "on", "move", "lens"}


def add_sfx(name, frame, volume=0.8, where=None):
    sfx_events.append((name, frame, volume, where))


def wav_seconds(wav):
    import wave as _wave
    with _wave.open(wav) as w:
        return w.getnframes() / w.getframerate()


def heard(wav, fx):
    """The recording as it is heard: through its voice effect, levelled (core/media.py)."""
    try:
        return media.process_voice(wav, fx or "clean")
    except Exception as e:                       # a missing ffmpeg must not stop the scene
        log(f"WARNING voice effect {fx} failed ({e}); using the plain recording")
        return wav


def listener_of(actor):
    """Who a speaker talks to: the nearest other cast member, preferring someone in front of them."""
    best, best_score = None, 1e9
    for other in cast.values():
        if other is actor:
            continue
        d = other.pos - actor.pos
        ahead = (actor.rot() @ Vector((0, -1, 0))).dot(d.normalized()) if d.length > 1e-3 else 0.0
        score = d.length * (1.6 - ahead)
        if score < best_score:
            best, best_score = other, score
    return best


drives = []                         # (actor, start, end, wheel id, turn): hands on a steering wheel


def steering(t, turn=0.0):
    """Steering wheel angle at t seconds into a drive: small corrections, plus an optional steady turn."""
    return 0.08 * math.sin(2 * math.pi * t / 3.3) + 0.035 * math.sin(2 * math.pi * t / 1.3) + turn * smooth01(t / 1.5)


cursor, last_start = 2, 2
step_frames = []                    # (start, end) of every step, in script order (the scene editor's timeline)
for step in spec["script"]:
    start = last_start if step.get("with") == "previous" else cursor
    who = cast.get(step.get("who"))
    do = step["do"]
    if do == "walk":
        target = free_near(to_world(step["to"]))
        route = plan(who.pos, target)
        end = who.walk(target, start, route, step.get("pace", "normal"))
        moves.append((who, start, end))
        if route:
            log(f"{step['who']} routes around obstacles via {len(route)} waypoint(s)")
    elif do == "enter":
        # the door opens (bell rings), the person steps through, walks on, the door closes behind them
        door = DOORS[step["door"]]
        hinge, bell = door["hinge"], door["bell"]
        hinge.rotation_mode = "XYZ"
        open_f = int(0.7 * FPS)
        for f, ang in ((start, 0.0), (start + open_f, -1.75)):
            hinge.rotation_euler = (0, 0, ang)
            hinge.keyframe_insert("rotation_euler", frame=f)
        if bell:
            bell.rotation_mode = "XYZ"
            for i in range(0, int(2.5 * FPS), 2):              # a struck bell: fast swing dying away
                bell.rotation_euler = (0.45 * math.exp(-i / (0.7 * FPS)) * math.sin(i / FPS * 2 * math.pi * 2.2), 0, 0)
                bell.keyframe_insert("rotation_euler", frame=start + 2 + i)
            add_sfx("door_bell", start + 2, where=door["centre"])
        add_sfx("door_open", start, where=door["centre"])
        who.visible(start + 4, True)
        inside = door["centre"] + door["front"] * 0.8
        target = free_near(to_world(step["to"])) if step.get("to") else free_near(inside + door["front"] * 0.6)
        route = [door["centre"], inside] + plan(free_near(inside), target)
        end = who.walk(target, start + open_f - 4, route)
        moves.append((who, start, end))
        close_f = start + open_f + int(2.2 * FPS)
        for f, ang in ((close_f, -1.75), (close_f + int(0.8 * FPS), 0.0)):
            hinge.rotation_euler = (0, 0, ang)
            hinge.keyframe_insert("rotation_euler", frame=f)
        add_sfx("door_close", close_f + int(0.7 * FPS), where=door["centre"])
    elif do == "exit":
        door = DOORS[step["door"]]
        hinge = door["hinge"]
        hinge.rotation_mode = "XYZ"
        before = door["centre"] + door["front"] * 0.65
        end = who.walk(free_near(before), start, plan(who.pos, free_near(before)))
        end = who.face(door["heading"] + math.pi, end)              # face the door
        for f, ang in ((end, 0.0), (end + int(0.8 * FPS), -1.75)):   # he pulls it open
            hinge.rotation_euler = (0, 0, ang)
            hinge.keyframe_insert("rotation_euler", frame=f)
        add_sfx(step.get("sound", "door_open"), end, where=door["centre"])
        outside = door["centre"] - door["front"] * 1.0
        end = who.walk(outside, end + int(0.6 * FPS), [door["centre"] + door["front"] * 0.2, door["centre"]])
        who.visible(start, True)
        who.visible(end, False)
        moves.append((who, start, end))
        close_f = end + int(0.3 * FPS)
        for f, ang in ((close_f, -1.75), (close_f + int(0.7 * FPS), 0.0)):
            hinge.rotation_euler = (0, 0, ang)
            hinge.keyframe_insert("rotation_euler", frame=f)
        add_sfx(step.get("close_sound", "door_close"), close_f + int(0.6 * FPS), where=door["centre"])
        end = close_f + int(1.2 * FPS)
    elif do == "open":
        door_id = step["door"]
        if door_id not in DOORS:
            raise ValueError(f"open action refers to unknown door prop {door_id!r}")
        door = DOORS[door_id]
        hinge = door["hinge"]
        side_offset = float(step.get("side_offset", door.get("picture_width", 0.0) * 0.4))
        approach = door["centre"] + door["front"] * step.get("distance", 0.68)
        approach += door.get("across", Vector()) * side_offset
        end = who.walk(approach, start, plan(who.pos, approach))
        end = who.face(heading_towards(who.pos, door["centre"]), end)
        local_door = who.rot().inverted() @ (door["centre"] - who.pos)
        side = "L" if local_door.x >= 0 else "R"
        swing = -0.65
        bend = 0.35
        reach_f = end + int(0.35 * FPS)
        open_f = reach_f + int(0.25 * FPS)
        release_f = open_f + int(0.8 * FPS)
        for f, amount in ((end, 0.0), (reach_f, 1.0), (open_f + int(0.4 * FPS), 1.0),
                          (release_f, 0.0)):
            who.key_arms(f, swing * amount if side == "L" else 0.0,
                         swing * amount if side == "R" else 0.0,
                         0.12 + bend * amount if side == "L" else 0.12,
                         0.12 + bend * amount if side == "R" else 0.12)
        hinge.rotation_mode = "XYZ"
        angle = -float(step.get("angle", 1.25))
        hinge.rotation_euler = (0, 0, 0.0)
        hinge.keyframe_insert("rotation_euler", frame=open_f)
        hinge.rotation_euler = (0, 0, angle)
        hinge.keyframe_insert("rotation_euler", frame=open_f + int(0.55 * FPS))
        hinge.keyframe_insert("rotation_euler", frame=release_f)
        add_sfx(step.get("sound", "door_open"), open_f, where=door["centre"])
        end = release_f + int(0.25 * FPS)
    elif do == "sit":
        seat = SEATS[step["on"]]
        stand_at = seat["centre"] + seat["front"] * 0.5
        approach = free_near(stand_at)
        end = who.walk(stand_at, start, plan(who.pos, approach) + ([approach] if approach != stand_at else []))
        end = who.face(seat["heading"], end)
        end = who.sit(seat, end)
        add_sfx("chair_sit", end - int(0.3 * FPS), where=seat["centre"])
    elif do == "stand":
        end = who.stand(start)
    elif do == "sound":
        add_sfx(step["sfx"], start, step.get("volume", 0.8), who.pos.copy() if who else None)
        end = start + int(step.get("seconds", 0.0) * FPS)
    elif do == "face":
        tgt = step["target"]
        if tgt == "camera":
            h = 0.0
        elif isinstance(tgt, list):                       # a spot on the stage, e.g. [1.0, 3.4]
            h = heading_towards(who.pos, to_world(tgt))
        else:
            h = heading_towards(who.pos, cast[tgt].pos)
        end = who.face(h, start)
    elif do == "think":
        # an inner voice: we hear the thought, the mouth stays closed, the camera slowly moves in
        wav = path(step["audio"])
        dur = wav_seconds(wav)
        f1 = start + int(math.ceil(dur * FPS))
        lines.append({"f0": start, "f1": f1, "actor": who, "who": step["who"], "kind": "think",
                      "text": step.get("text", ""), "expression": step.get("expression"), "listener": None})
        who.thinking.append((start / FPS, start / FPS + dur))
        if step.get("expression") in acting.EXPRESSIONS:
            who.expression.overlay(start / FPS, f1 / FPS + 0.5, feeling(step["expression"], step.get("intensity", 1.0)))
        sounds.append((heard(wav, step.get("fx", who.voice_fx)), start, 2 + len(sounds) % 4, None))
        end = start + int(math.ceil((dur + step.get("pause", 0.6)) * FPS))
    elif do == "narrate":
        # a voice-over: no one on screen speaks it, the camera does not cut
        wav = path(step["audio"])
        dur = wav_seconds(wav)
        lines.append({"f0": start, "f1": start + int(math.ceil(dur * FPS)), "actor": None, "who": "Narrator",
                      "kind": "narrate", "text": step.get("text", ""), "expression": None, "listener": None})
        sounds.append((heard(wav, step.get("fx", "clean")), start, 2 + len(sounds) % 4, None))
        end = start + int(math.ceil((dur + step.get("pause", 0.4)) * FPS))
    elif do == "emote":
        t0 = start / FPS
        value = feeling(step["expression"], step.get("intensity", 1.0))
        if step.get("seconds"):
            who.expression.overlay(t0, t0 + float(step["seconds"]), value)
        else:
            who.expression.set(t0, value)
        end = start
    elif do == "posture":
        who.posture.set(start / FPS, acting.POSTURES.get(step["posture"], {}))
        end = start
    elif do == "gesture":
        name = step["type"]
        seconds = float(step.get("seconds") or acting.GESTURES[name][0])
        hand = "L" if step.get("hand") == "left" else "R"
        options = {}
        if step.get("target") is not None:
            tgt = step["target"]
            spot = cast[tgt] if isinstance(tgt, str) and tgt in cast else (cam_spot() if tgt == "camera" else to_world(tgt))
            rel = who.rot().inverted() @ ((spot.pos if isinstance(spot, Actor) else spot) - who.pos)   # +x: the character's left
            if not step.get("hand"):
                hand = "L" if rel.x > 0 else "R"
            options["azimuth"] = abs(math.atan2(rel.x, -rel.y))
            who.looks.append((start / FPS, start / FPS + seconds, spot))
        who.gestures.append((start / FPS, seconds, name, options, hand))
        end = start + int(round(seconds * FPS))
    elif do == "look":
        seconds = float(step.get("seconds", 1.5))
        tgt = step["target"]
        if tgt in ("left", "right", "up", "down"):
            spot = tgt
        else:
            spot = cast[tgt] if isinstance(tgt, str) and tgt in cast else (cam_spot() if tgt == "camera" else to_world(tgt))
        who.looks.append((start / FPS, start / FPS + seconds, spot))
        end = start + int(round(seconds * FPS))
    elif do == "music":
        music_cues.append((start, None if step.get("stop") else step.get("bed"), step.get("volume", 0.35),
                           step.get("fade", 1.5)))
        end = start
    elif do == "camera":
        forced.append({"f0": start, "seconds": step.get("seconds"), "shot": step["shot"], "on": step.get("on"),
                       "move": step.get("move"), "lens": step.get("lens")})
        end = start
    elif do == "drive":
        end = start + int(step.get("seconds", 8.0) * FPS)
        who.driving.append((start, end))
        wheels = prop_factory.STEERING_WHEELS
        wheel_id = step.get("wheel") or (next(iter(wheels)) if len(wheels) == 1 else None)
        if wheel_id in wheels:
            drives.append((who, start, end, wheel_id, math.radians(float(step.get("turn", 0.0)))))
    elif do == "say":
        wav = path(step["audio"])
        cues = viseme_cues(wav, step.get("text"))
        key_lipsync(who, cues, start)
        dur = max(cues[-1]["end"], wav_seconds(wav))
        who.speaking.append((start / FPS, start / FPS + dur))
        last_s = -1.0
        for c in cues:                       # stressed syllables: clear open vowels, spaced out
            t = start / FPS + c["start"]
            if c["viseme"] in ("viseme_aa", "viseme_E", "viseme_O", "viseme_I") and c.get("weight", 1) >= 1 \
                    and c["end"] - c["start"] > 0.07 and t - last_s > 0.55:
                who.stresses.append(t)
                last_s = t
        f1 = start + int(math.ceil(dur * FPS))
        heard_by = listener_of(who)
        lines.append({"f0": start, "f1": f1, "actor": who, "who": step["who"], "kind": "say",
                      "text": step.get("text", ""), "expression": step.get("expression"),
                      "listener": heard_by.id if heard_by else None})
        if step.get("expression") in acting.EXPRESSIONS:
            who.expression.overlay(start / FPS, f1 / FPS + 0.5, feeling(step["expression"], step.get("intensity", 1.0)))
        sounds.append((heard(wav, step.get("fx", who.voice_fx)), start, 2 + len(sounds) % 4, who.pos.copy()))
        end = start + int(math.ceil((dur + step.get("pause", 0.3)) * FPS))
    elif do == "perform":
        end = run_perform(who, step, start)
    elif do == "hold":
        pid = step["prop"]
        if pid not in PROP_ROOTS:
            raise ValueError(f"hold refers to unknown prop {pid!r}")
        prop_root, prop_data = PROP_ROOTS[pid]
        size_p = prop_data.get("size") or measure_prop(prop_root)
        grip = acting.carry_grip(size_p)
        side = "L" if step.get("hand") == "left" else "R"
        loc = prop_root.matrix_world.to_translation()
        flat = Vector((loc.x, loc.y, 0.0))
        end = start
        if (Vector((who.pos.x, who.pos.y, 0.0)) - flat).length > 0.75:
            stand = flat + (Vector((who.pos.x, who.pos.y, 0.0)) - flat).normalized() * 0.5
            end = who.walk(stand, start, plan(who.pos, stand))
        end = who.face(heading_towards(who.pos, flat), end)
        reach_f = end + int(0.3 * FPS)
        grab_f = reach_f + int(0.25 * FPS)
        sw, bd = (-0.95, 0.5)
        who.key_arms(end, 0.0, 0.0, 0.12, 0.12, sides=(side,))
        who.key_arms(reach_f, sw if side == "L" else 0.0, sw if side == "R" else 0.0,
                     bd if side == "L" else 0.12, bd if side == "R" else 0.12, sides=(side,))
        who.key_arms(grab_f + int(0.2 * FPS), -0.30 if side == "L" else 0.0, -0.30 if side == "R" else 0.0,
                     0.85 if side == "L" else 0.12, 0.85 if side == "R" else 0.12, sides=(side,))
        # a grip empty rides the hand bone; the prop's own axes line up with it (a stick lies across the palm)
        B = {0: Matrix.Identity(3), 1: Matrix.Rotation(-math.pi / 2, 3, "Z"),
             2: Matrix.Rotation(math.pi / 2, 3, "Y")}[grip["axis"]]
        axis_v = Vector((0.0, 0.0, 0.0))
        axis_v[grip["axis"]] = grip["along"]
        p_grab = axis_v + Vector((0.0, 0.0, grip["lift"]))
        e = bpy.data.objects.new(f"CF_grip_{who.id}_{pid}", None)
        e.empty_display_size = 0.05
        scene.collection.objects.link(e)
        e.parent = who.rig
        e.parent_type = "BONE"
        e.parent_bone = f"hand_fk.{side}"
        # A bone-parented child sits at the bone's tail (the knuckles), with +Y running out along the bone.
        # The palm is half a hand back from there, and the prop has to sit clear of the palm by half its own
        # thickness or it passes through the hand and into the wrist.
        palm = 0.45 * who.pb[f"hand_fk.{side}"].bone.length
        clear = grip.get("clear", 0.02)
        e.matrix_basis = Matrix.Translation(Vector((0.0, -palm, -clear)) - B @ p_grab) @ B.to_4x4()
        for kind_c, name_c in (("COPY_LOCATION", "CF_hold_loc"), ("COPY_ROTATION", "CF_hold_rot")):
            con = prop_root.constraints.new(kind_c)
            con.name = name_c
            con.target = e
            con.influence = 0.0
            con.keyframe_insert("influence", frame=reach_f)
            con.influence = 1.0
            con.keyframe_insert("influence", frame=grab_f)
        # hands close as far as the prop lets them: a handle is wrapped, a fat lantern is only held
        who.holding.append([grab_f, None, side, prop_root,
                            "grip" if grip["kind"] in ("stick", "hang") else "fist",
                            float(grip.get("curl", 1.0))])
        end = grab_f + int(0.25 * FPS)
    elif do == "release":
        want = {"left": "L", "right": "R"}.get(step.get("hand"))
        held = next((h for h in reversed(who.holding) if h[1] is None and (want is None or h[2] == want)), None)
        if held is None:
            raise ValueError(f"{step.get('who')} is not holding anything to release")
        prop_root, side = held[3], held[2]
        scene.frame_set(start)
        world = prop_root.evaluated_get(bpy.context.evaluated_depsgraph_get()).matrix_world.copy()
        held[1] = start
        loc_w, rot_w, _ = world.decompose()
        prop_root.rotation_mode = "XYZ"
        put_f = start + int(0.45 * FPS)
        prop_root.location = loc_w
        prop_root.rotation_euler = rot_w.to_euler("XYZ")
        prop_root.keyframe_insert("location", frame=start)
        prop_root.keyframe_insert("rotation_euler", frame=start)
        if step.get("to"):
            target = to_world(tuple(step["to"]))
            prop_root.location = Vector((loc_w.x + (target.x - loc_w.x) * 0.5,
                                         loc_w.y + (target.y - loc_w.y) * 0.5, max(loc_w.z * 0.7, 0.1)))
            prop_root.keyframe_insert("location", frame=(start + put_f) // 2)
            prop_root.location = Vector((target.x, target.y, 0.0))
            prop_root.rotation_euler = (0.0, 0.0, rot_w.to_euler("XYZ").z)
            prop_root.keyframe_insert("location", frame=put_f)
            prop_root.keyframe_insert("rotation_euler", frame=put_f)
        for con in prop_root.constraints:
            if con.name.startswith("CF_hold"):
                con.influence = 1.0
                con.keyframe_insert("influence", frame=start)
                con.influence = 0.0
                con.keyframe_insert("influence", frame=start + int(0.2 * FPS))
        who.key_arms(start, -0.30 if side == "L" else 0.0, -0.30 if side == "R" else 0.0,
                     0.85 if side == "L" else 0.12, 0.85 if side == "R" else 0.12, sides=(side,))
        who.key_arms(put_f + int(0.2 * FPS), 0.0, 0.0, 0.12, 0.12, sides=(side,))
        end = put_f + int(0.25 * FPS)
    elif do == "duck":
        end = run_duck(who, start, float(step.get("seconds", 1.0)), float(step.get("depth", 0.32)))
    elif do == "strike":
        target = step["target"]
        if not isinstance(target, str) or target not in cast:
            raise ValueError(f"strike target {target!r} is not in the cast")
        defender = cast[target]
        clip = motion.load(config.MOTIONS_DIR, step["clip"])
        if clip is None:
            raise ValueError(f"no motion clip {step['clip']!r} (python castforge.py motion list)")
        t0, t1 = motion.window(clip, step.get("from", 0.0), step.get("to"))
        speed = float(step.get("speed", 1.0))
        spacing = float(step.get("distance", 0.9))
        d_pos = Vector((defender.pos.x, defender.pos.y, 0.0))
        a_pos = Vector((who.pos.x, who.pos.y, 0.0))
        gap = (a_pos - d_pos).length
        end = start
        if gap > 0.05 and abs(gap - spacing) > 0.25:        # close in (or back off) to striking distance
            stand = d_pos + (a_pos - d_pos).normalized() * spacing
            end = who.walk(stand, start, plan(who.pos, stand))
        end = who.face(heading_towards(who.pos, d_pos), end)
        if step.get("square_up", True) and not defender.seated:
            defender.face(heading_towards(defender.pos, Vector((who.pos.x, who.pos.y, 0.0))), max(start, end - 8))
        hit_stop = max(0, int(step.get("hit_stop", 2)))
        contact = float(step.get("contact", 0.4 * (t1 - t0)))
        contact = max(0.05, min(contact, t1 - t0 - 0.05))
        clip_start = end
        end = run_perform(who, {"clip": step["clip"], "from": step.get("from", 0.0), "to": step.get("to"),
                                "speed": speed, "blend": float(step.get("blend", 0.25)),
                                "hands": step.get("hands") or "fist",   # a blow lands with a closed hand
                                "_holds": ((contact, hit_stop),) if hit_stop else ()}, clip_start)
        contact_f = clip_start + int(round(motion.to_scene(contact, FPS, speed)))
        react = step.get("react", "stagger")
        # the swing is heard before the blow; what the blow sounds like depends on how it is taken
        add_sfx(step.get("swing_sound", "whoosh"), max(start, contact_f - int(0.18 * FPS)),
                volume=0.5, where=a_pos)
        if react != "dodge":
            landed = {"block": "block", "stagger": "hit_hard"}.get(react, "hit")
            add_sfx(step.get("sound", landed), contact_f, where=(d_pos + a_pos) / 2)
        beats.append((who, defender, start, end, contact_f))
        r_end = contact_f
        if react == "stagger":
            away = d_pos - a_pos
            away = away.normalized() if away.length > 0.05 else Vector((0.0, 1.0, 0.0))
            defender.posture.overlay(contact_f / FPS, (contact_f + 20) / FPS,
                                     {"chest": -0.14, "head": -0.22, "shoulders": 0.6})
            defender.turn_blinks.append(contact_f + 1)
            r_end = defender.walk(free_near(d_pos + away * 0.55), contact_f + 2, pace="hurry")
        elif react == "dodge":
            r_end = run_duck(defender, max(start, contact_f - int(0.3 * FPS)), 0.9, 0.36)
        elif react == "block":
            defender.gestures.append(((contact_f - int(0.3 * FPS)) / FPS, 1.2, "block", {}, "R"))
            r_end = contact_f + int(0.9 * FPS)
        end = max(end, r_end)
        beats[-1] = (who, defender, start, end, contact_f)
    elif do == "wait":
        end = start + int(step.get("seconds", 1.0) * FPS)
    else:
        raise ValueError(f"unknown action {do}")
    log(f"{step.get('who', '-')}: {do} frames {start}-{end}")
    step_frames.append((start, end))
    last_start = start
    cursor = max(cursor, end)

scene.frame_start, scene.frame_end = 1, cursor + FPS

# --- life: breathing, blinks, head motion while talking -----------------------------------------
def turn_at(keys, f):
    """Value of a (frame, value) list at frame f, eased between keys."""
    prev = keys[0]
    for k in keys:
        if k[0] > f:
            span = max(k[0] - prev[0], 1)
            return prev[1] + (k[1] - prev[1]) * smooth01((f - prev[0]) / span)
        prev = k
    return prev[1]


def bump(x):
    """0 -> 1 -> 0 over x in [0, 1], smooth at both ends."""
    return math.sin(math.pi * x) ** 2 if 0.0 <= x <= 1.0 else 0.0


from bpy_extras import anim_utils  # noqa: E402

LOOK_DIRECTIONS = {"left": (0.5, 0.0), "right": (-0.5, 0.0), "up": (0.0, 0.35), "down": (0.0, -0.3)}
FACE_SHAPES = sorted({k for v in acting.EXPRESSIONS.values() for k in v if k != "eyelids"})
BROWS = {"browInnerUp": 1.0, "browOuterUpLeft": 0.6, "browOuterUpRight": 0.6}


def root_curves(act):
    """The rig root's location and heading F-curves, to know where someone is at any frame."""
    ad = act.rig.animation_data
    bag = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
    return [bag.fcurves.find("location", index=i) for i in range(3)], bag.fcurves.find("rotation_euler", index=2)


def eye_local(act):
    """Where the eyes are in the rig at rest (between the two eye bones)."""
    pts = [act.rig.data.bones[n].head_local for n in ("MCH-eye.L", "MCH-eye.R") if n in act.rig.data.bones]
    if pts:
        return sum(pts, Vector()) / len(pts)
    return act.pb["head"].bone.head_local + Vector((0, -0.08, 0.1))


for act in cast.values():
    act.curves = root_curves(act)
    act.eyes = eye_local(act)


def eye_world(act, f):
    """Where someone's eyes are at frame f (a seated person's eyes are lower)."""
    loc, rot = act.curves
    pos = Vector([c.evaluate(f) if c else 0.0 for c in loc])
    heading = rot.evaluate(f) if rot else act.heading
    seated = next((r for r in act.seated_ranges if r[0] <= f and (r[1] is None or f < r[1])), None)
    drop = seated[2] if seated else Vector((0, 0, 0))
    return pos + Matrix.Rotation(heading, 3, "Z") @ (act.eyes + drop), heading


def spot_of(target, f):
    """A look target as a point in the world (a person means their eyes)."""
    return eye_world(target, f)[0] if isinstance(target, Actor) else Vector(target)


def gesture_at(act, t):
    """(shoulder, elbow, hand weights, pose, hands, side) of the gesture at time t, or None. The elbow and hand
    follow the shoulder late and overshoot (acting.whip), so the gesture runs a moment past its end."""
    for t0, seconds, name, options, side in act.gestures:
        tr = t - t0
        if 0 <= tr <= seconds + acting.HAND_LAG + acting.SETTLE:
            _, hands, pose = acting.GESTURES[name]
            weights = (acting.gesture_weight(tr, seconds), acting.whip(tr, seconds, acting.ELBOW_LAG),
                       acting.whip(tr, seconds, acting.HAND_LAG))
            return weights, pose(min(tr, seconds) / seconds, min(tr, seconds), options), hands, side
    return None


for act in cast.values():
    ch = act.pb["chest"]
    ch.rotation_mode = "XYZ"
    head = act.pb["head"]
    head.rotation_mode = "XYZ"
    seed = rand.uniform(0, 2 * math.pi)
    # nods: the speaker nods on stressed syllables; a listener nods now and then while the other talks
    nods = [(s, 0.05, 0.35) for s in act.stresses]
    for other in cast.values():
        if other is not act:
            for a, b in other.speaking:
                for _ in range(1 if b - a < 3 else 2):
                    nods.append((rand.uniform(a + 0.5, max(a + 0.6, b - 0.6)), 0.06, 0.6))
    brows = [s for n, s in enumerate(act.stresses) if n % 2 == 0]
    act.head_yaw.sort(key=lambda k: k[0])
    # talking hands: on some stressed words one hand comes up, opens and goes back down
    gestures, hand = [], rand.choice("LR")
    for n, s in enumerate(act.stresses):
        if n % 2 == 1 and rand.random() < 0.75:
            gestures.append((s - 0.2, hand, rand.uniform(0.7, 1.0)))
            hand = "L" if hand == "R" else "R"
    # eyes: small saccades all the time; a speaker glances away now and then while thinking of the words
    saccades = acting.saccades(rand, 0.0, scene.frame_end / FPS)
    glances = [(s, rand.choice((-1, 1))) for s in act.stresses if rand.random() < 0.2]
    shapes = sorted({k for _, v in act.expression.keys for k in v} | {k for _, _, v in act.expression.overlays for k in v})
    face = [k for k in FACE_SHAPES if k in shapes and k in act.keys and k not in BROWS]
    droops = "eyelids" in shapes
    bows = [(t0, t0 + sec) for t0, sec, name, _, _ in act.gestures if "torso" in acting.GESTURES[name][2](0.5, 0, {})]
    eye_rest = act.pb.get("eye_common")
    tilt = rand.uniform(0.05, 0.1) * rand.choice((-1, 1))
    for f in range(1, scene.frame_end + 1, 2):
        t = f / FPS
        feel = act.expression.at(t)
        stance = act.posture.at(t)
        g = {"L": 0.0, "R": 0.0}
        for s, side, amp in gestures:
            g[side] = max(g[side], amp * bump((t - s) / 1.0))
        current = gesture_at(act, t)
        (weight, w_elbow, w_hand), pose, hands, gside = current if current else ((0.0, 0.0, 0.0), {}, "none", "R")
        moving = weight > 0 or abs(w_elbow) > 1e-3 or abs(w_hand) > 1e-3
        arm_sides = {"one": (gside,), "both": ("L", "R")}.get(hands, ()) if moving else ()
        arm = pose.get("arm", {})
        fingers = {"L": (g["L"], None, 0.0, 1.0), "R": (g["R"], None, 0.0, 1.0)}
        for side in arm_sides:
            side_arm = pose.get(f"arm_{side}", arm)
            fingers[side] = (g[side] + w_hand * (side_arm.get("open", 0.0) - g[side]), side_arm.get("hand"),
                             max(0.0, w_hand * side_arm.get("grip", 0.0)), 1.0)
        # a motion clip carries no finger movement, so a punch needs its fist made here
        for c0, c1, c_shape, c_grip in act.clip_hands:
            if c0 <= f <= c1:
                for s_ in "LR":
                    fingers[s_] = (0.0, c_shape, c_grip, 1.0)
        for h in act.holding:          # holding wins: the hand keeps its grip through a swing
            if h[0] <= f and (h[1] is None or f < h[1]):
                fingers[h[2]] = (0.0, h[4], 0.95, h[5])
        act.key_fingers(f, fingers["L"][0], fingers["R"][0], fingers["L"][1], fingers["R"][1],
                        fingers["L"][2], fingers["R"][2], fingers["L"][3], fingers["R"][3])
        seated_now = any(r[0] <= f and (r[1] is None or f < r[1]) for r in act.seated_ranges)
        if f not in act.walk_frames or arm_sides:
            if any(a0 <= f <= a1 for a0, a1 in act.driving):
                steer = 0.05 * math.sin(2 * math.pi * t / 3.3 + seed) + 0.03 * math.sin(2 * math.pi * t / 1.3)
                idle = {"L": (-0.85 + steer, 0.75), "R": (-0.85 - steer, 0.75)}
                act.key_fingers(f, 0.0, 0.0)
            elif seated_now:   # hands on the thighs; a gesture lifts the forearm off the leg
                idle = {s_: (-0.32 - 0.25 * g[s_], 0.62 + 0.6 * g[s_]) for s_ in "LR"}
            else:
                sway = 0.015 * math.sin(2 * math.pi * t / 6.5 + seed)
                idle = {"L": (sway - 0.35 * g["L"], 0.12 + 0.8 * g["L"]), "R": (-sway - 0.35 * g["R"], 0.12 + 0.8 * g["R"])}
            for h in act.holding:
                if h[0] <= f and (h[1] is None or f < h[1]):
                    idle[h[2]] = (-0.30, 0.85)
            v = {}
            for side in "LR":
                swing, bend = idle[side]
                arm = pose.get(f"arm_{side}", pose.get("arm", {}))     # a gesture may pose each hand apart
                w, we = (weight, w_elbow) if side in arm_sides else (0.0, 0.0)
                v[side] = (swing + w * (arm.get("swing", swing) - swing), bend + we * (arm.get("bend", bend) - bend),
                           w * arm.get("raise", 0.0), w * arm.get("twist", 0.0),
                           w_hand * arm.get("wrist", 0.0) if side in arm_sides else 0.0)
            walking = f in act.walk_frames
            act.key_arms(f, v["L"][0], v["R"][0], v["L"][1], v["R"][1], v["L"][2], v["R"][2], v["L"][3], v["R"][3],
                         sides=arm_sides if walking else ("L", "R"), wrist_l=v["L"][4], wrist_r=v["R"][4])
        lift = stance.get("shoulders", 0.0) + feel.get("_shoulders", 0.0) + weight * pose.get("shoulders", 0.0)
        act.key_shoulders(f, lift, lift)
        # head and eyes: an explicit look (or a point) turns the head; eyes find whoever matters
        heading = act.curves[1].evaluate(f) if act.curves[1] else act.heading
        look = next(((t0, t1, spot) for t0, t1, spot in act.looks if t0 <= t <= t1), None)
        look_yaw = look_up = 0.0
        if look:
            lw = acting.window(t, look[0], look[1], 0.3)
            if isinstance(look[2], str):
                look_yaw, look_up = (c * lw for c in LOOK_DIRECTIONS[look[2]])
            else:                                       # the head takes most of the turn, the eyes the rest
                eye, _ = eye_world(act, f)
                yaw_rel, up_rel = acting.bearing(eye, heading, spot_of(look[2], f))
                look_yaw = max(-1.0, min(1.0, 0.7 * yaw_rel)) * lw
                look_up = max(-0.4, min(0.4, 0.5 * up_rel)) * lw
        t = f / FPS
        breath = 0.012 * math.sin(2 * math.pi * t / 4.2 + seed)
        chest_pitch = breath + stance.get("chest", 0.0) + feel.get("_chest", 0.0) + weight * pose.get("chest", 0.0)
        talking = any(a <= t <= b for a, b in act.speaking)
        drift = 0.025 if talking else 0.012
        nod = sum(amp * bump((t - s) / dur) for s, amp, dur in nods)
        nod += sum(0.16 * smooth01((t - a0) / 1.2) * smooth01((b0 + 0.8 - t) / 1.2) for a0, b0 in act.thinking)
        yaw = turn_at(act.head_yaw, f)
        ch.rotation_euler = (chest_pitch, 0, act.chest_yaw.get(f, 0.0) + 0.3 * yaw)
        ch.keyframe_insert("rotation_euler", frame=f)
        gh = pose.get("head", {})
        head_yaw = 0.7 * yaw + look_yaw + weight * gh.get("yaw", 0.0)
        head.rotation_euler = (nod + drift * math.sin(2 * math.pi * t / 3.1 + seed) + stance.get("head", 0.0)
                               + feel.get("_head", 0.0) + weight * gh.get("pitch", 0.0) - look_up,
                               head_yaw + drift * 1.2 * math.sin(2 * math.pi * t / 4.7 + 2 * seed),
                               drift * 0.6 * math.sin(2 * math.pi * t / 5.9 + seed) + weight * gh.get("roll", 0.0))
        head.keyframe_insert("rotation_euler", frame=f)
        if eye_rest and act.gaze:
            target = None
            if look and not isinstance(look[2], str):
                target = look[2]
            elif look:
                target = LOOK_DIRECTIONS[look[2]]
            else:
                talker = next((o for o in cast.values() if o is not act and any(a <= t <= b for a, b in o.speaking)), None)
                if talker:
                    target = talker
                elif any(a <= t <= b for a, b in act.thinking):
                    target = (0.25, -0.3)                         # down and away, inward
                else:
                    target = listener_of(act) if len(cast) > 1 else None
            if isinstance(target, tuple):
                eye_yaw, eye_up = target
            elif target is not None:
                eye, _ = eye_world(act, f)
                eye_yaw, eye_up = acting.gaze_angles(eye, heading, 0.3 * yaw + head_yaw, spot_of(target, f))
            else:
                eye_yaw, eye_up = 0.0, 0.0
            for s, side in glances:
                gl = bump((t - s) / 0.7)
                eye_yaw, eye_up = eye_yaw + gl * side * 0.3, eye_up + gl * 0.12
            for s, dy, dp in saccades:
                if s <= t < s + 0.6:
                    eye_yaw, eye_up = eye_yaw + dy, eye_up + dp
            eye_yaw = max(-acting.EYE_YAW, min(acting.EYE_YAW, eye_yaw))
            eye_up = max(-acting.EYE_PITCH, min(acting.EYE_PITCH, eye_up))
            r = 0.08                                            # eye_common sits 8 cm in front of the eyes
            act.key_offset("eye_common", Vector((r * math.sin(eye_yaw) * math.cos(eye_up),
                                                 r * (1 - math.cos(eye_yaw) * math.cos(eye_up)),
                                                 r * math.sin(eye_up))), f)
        seated = next((r for r in act.seated_ranges if r[0] <= f and (r[1] is None or f < r[1])), None)
        if seated and f not in act.walk_frames:
            act.key_offset("torso", seated[2] + Vector((0, 0, 0.003 * math.sin(2 * math.pi * t / 4.2 + seed))), f)
        elif not any(abs(f - w) <= 4 for w in (f - 4, f + 4) if w in act.walk_frames) and f not in act.walk_frames:
            # standing: slow weight shift from foot to foot (feet stay planted by IK)
            act.key_offset("torso", Vector((0.011 * math.sin(2 * math.pi * t / 6.5 + seed), 0,
                                            -0.015 - 0.004 * abs(math.sin(2 * math.pi * t / 6.5 + seed))
                                            - stance.get("drop", 0.0))), f)
        if any(b0 - 2 / FPS <= t <= b1 + 2 / FPS for b0, b1 in bows) and f not in act.walk_frames:
            base = Matrix.Rotation(-0.05, 3, "X") if seated else Matrix.Identity(3)
            act.key_rot("torso", base @ Matrix.Rotation(weight * pose.get("torso", 0.0), 3, "X"), f)
        stress = sum(0.35 * bump((t - s + 0.05) / 0.5) for s in brows)
        for name, k in BROWS.items():
            if name in act.keys:
                act.keys[name].value = max(min(stress, 0.5) * k, feel.get(name, 0.0))
                act.keys[name].keyframe_insert("value", frame=f)
        feel = acting.asymmetric(feel, tilt)
        for name in face:
            act.keys[name].value = feel.get(name, 0.0)
            act.keys[name].keyframe_insert("value", frame=f)
    # blinks, merged with tired eyelids by taking the larger value
    t = rand.uniform(0.5, 2.0)
    blinks = []
    while t * FPS < scene.frame_end:
        f_ = int(t * FPS)
        if all(abs(f_ - b) > FPS for b in act.turn_blinks):
            blinks.append(f_)
        t += rand.uniform(2.0, 5.0)
    if droops:
        for f in range(1, scene.frame_end + 1):
            lid = act.expression.at(f / FPS).get("eyelids", 0.0)
            v = max([lid] + [1.0 - abs(f - b - 2) / 2 for b in blinks if b <= f <= b + 4])
            for name in ("eyeBlinkLeft", "eyeBlinkRight"):
                act.keys[name].value = v
                act.keys[name].keyframe_insert("value", frame=f)
    else:
        for f in blinks:
            for name in ("eyeBlinkLeft", "eyeBlinkRight"):
                k = act.keys[name]
                for df, v in ((0, 0.0), (2, 1.0), (4, 0.0)):
                    k.value = v
                    k.keyframe_insert("value", frame=f + df)

# --- hands on the wheel: the arms switch to IK and the hands hold the rim at ten to two, turning with it ---
def hold_wheel(act, f0, f1, wheel_id, turn):
    wheel = prop_factory.STEERING_WHEELS[wheel_id]
    wheel.rotation_mode = "XYZ"
    bpy.context.view_layer.update()
    rest = wheel.matrix_world.copy()
    size = max((max(c.dimensions) for c in wheel.children if c.type == "MESH"), default=0.4)
    grip = 0.45 * size                                   # the middle of the rim, not its outer edge
    scene.frame_set(f0)
    to_rig = act.rig.matrix_world.inverted()
    shoulders = {s_: act.rig.matrix_world @ act.pb[f"upper_arm_fk.{s_}"].bone.head_local for s_ in "LR"}
    blend = max(2, int(0.3 * FPS))
    for f in range(f0 - blend, f1 + blend + 1, 2):
        t = max(0, f - f0) / FPS
        angle = steering(t, turn) if f0 <= f <= f1 else 0.0
        wheel.rotation_euler = (0, angle, 0)
        wheel.keyframe_insert("rotation_euler", frame=f)
        spin = rest @ Matrix.Rotation(angle, 4, "Y")
        rim = [spin @ Vector((grip * math.sin(a), 0, grip * math.cos(a))) for a in (math.radians(-60), math.radians(60))]
        # each hand takes the grip point nearer its own shoulder
        near_l = (rim[0] - shoulders["L"]).length + (rim[1] - shoulders["R"]).length < \
            (rim[1] - shoulders["L"]).length + (rim[0] - shoulders["R"]).length
        hold = {"L": rim[0], "R": rim[1]} if near_l else {"L": rim[1], "R": rim[0]}
        ik = smooth01((f - (f0 - blend)) / blend) * smooth01((f1 + blend - f) / blend)
        scene.frame_set(f)                               # the hand controls' parents as they are at this frame
        for side in "LR":
            hand = act.pb[f"hand_ik.{side}"]
            m = hand.matrix.copy()
            m.translation = to_rig @ hold[side]          # armature space; Blender works out the parent space
            hand.matrix = m
            hand.keyframe_insert("location", frame=f)
            parent = act.pb[f"upper_arm_parent.{side}"]
            parent["IK_FK"] = 1.0 - ik                     # 0 = IK (hands on the wheel), 1 = FK
            parent.keyframe_insert('["IK_FK"]', frame=f)
            act.key_fingers(f, 0.0, 0.0, "fist", "fist", 0.8 * ik, 0.8 * ik)


for act, f0, f1, wheel_id, turn in drives:
    hold_wheel(act, f0, f1, wheel_id, turn)
    log(f"{act.id}: hands on {wheel_id} frames {f0}-{f1}")

# --- set: background image, floor that shows the same image but takes shadows, light, camera -------
bg_img = bpy.data.images.load(path(spec["background"]))
_, SAMPLES, ALLOW_LOOK, FULL_DETAIL = config.QUALITY[QUALITY]
LOOK = spec.get("look", "cinematic") if ALLOW_LOOK else "plain"
# the light is decided before any material: the set's shadow catcher must expect exactly this light
PICTURE_L, PICTURE_RGB = world_kit.picture_stats(bg_img)
MOOD = world_kit.mood(spec.get("lighting", "auto"), PICTURE_L, PICTURE_RGB)
SUN_ENERGY, SUN_COLOR = MOOD["sun"]
WORLD, WORLD_COLOR = MOOD["world"]
if LOOK != "cinematic":                 # no key/fill/rim light: a little more sky so previews read clearly
    WORLD /= 0.7
log(f"light: {spec.get('lighting', 'auto')}, picture brightness {PICTURE_L:.2f}, "
    f"exposure x{world_kit.exposure(PICTURE_L):.2f}")
SUN_ELEV, SUN_AZ = math.radians(50), math.radians(-25)
SUN_ROT = (math.pi / 2 - SUN_ELEV, 0, SUN_AZ)
TO_SUN = -(Euler(SUN_ROT).to_matrix() @ Vector((0, 0, -1)))       # unit vector towards the sun


def image_material(name, receive_shadow, coords="UV"):
    """Shows the background picture as it is (its own lighting), darkened only where a character's
    shadow falls: lit/expected-lit ratio, where expected = sun * max(0, n.L) / pi + world (each times the
    brightness of its colour). The diffuse is white, so where nothing casts a shadow the ratio is exactly 1."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = bg_img; tex.extension = "EXTEND"
    nt.links.new(coord.outputs[coords], tex.inputs["Vector"])
    emit = nt.nodes.new("ShaderNodeEmission")
    if receive_shadow:
        diff = nt.nodes.new("ShaderNodeBsdfDiffuse")
        diff.inputs["Color"].default_value = (1, 1, 1, 1)
        s2r = nt.nodes.new("ShaderNodeShaderToRGB")
        nt.links.new(diff.outputs[0], s2r.inputs[0])
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        dot = nt.nodes.new("ShaderNodeVectorMath"); dot.operation = "DOT_PRODUCT"
        nt.links.new(geo.outputs["Normal"], dot.inputs[0])
        dot.inputs[1].default_value = TO_SUN
        mx = nt.nodes.new("ShaderNodeMath"); mx.operation = "MAXIMUM"; mx.inputs[1].default_value = 0.0
        nt.links.new(dot.outputs["Value"], mx.inputs[0])
        lit = nt.nodes.new("ShaderNodeMath"); lit.operation = "MULTIPLY_ADD"
        nt.links.new(mx.outputs[0], lit.inputs[0])
        lit.inputs[1].default_value = SUN_ENERGY * world_kit.luminance(SUN_COLOR) / math.pi
        lit.inputs[2].default_value = WORLD * world_kit.luminance(WORLD_COLOR)
        bw = nt.nodes.new("ShaderNodeRGBToBW")
        nt.links.new(s2r.outputs["Color"], bw.inputs[0])
        ratio = nt.nodes.new("ShaderNodeMath"); ratio.operation = "DIVIDE"; ratio.use_clamp = True
        nt.links.new(bw.outputs[0], ratio.inputs[0])
        nt.links.new(lit.outputs[0], ratio.inputs[1])
        mul = nt.nodes.new("ShaderNodeMix"); mul.data_type = "RGBA"; mul.blend_type = "MULTIPLY"
        mul.inputs["Factor"].default_value = 1.0
        nt.links.new(tex.outputs["Color"], mul.inputs["A"])
        nt.links.new(ratio.outputs[0], mul.inputs["B"])
        nt.links.new(mul.outputs["Result"], emit.inputs["Color"])
    else:
        nt.links.new(tex.outputs["Color"], emit.inputs["Color"])
    nt.links.new(emit.outputs[0], out.inputs["Surface"])
    return m


cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
scene.collection.objects.link(cam); scene.camera = cam
if SET:
    # the camera the picture was "taken" with; the set is built around it
    cam.data.lens = SET["camera"]["lens"]
    cam.data.sensor_width = SET["camera"]["sensor"]
    cam.data.sensor_fit = "HORIZONTAL"
    cam.location = SET["camera"]["location"]
    cam.rotation_euler = (math.pi / 2 - SET["camera"].get("pitch", 0.0), 0, 0)
    bpy.context.view_layer.update()
    before = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=os.path.join(set_dir, "set.obj"), forward_axis="Y", up_axis="Z")
    relief = next(o for o in bpy.data.objects if o not in before)
    relief.name = "Set"
    relief.data.materials.clear()
    relief.data.materials.append(image_material("SetFromBackground", True, "UV"))
    relief.visible_shadow = False          # the picture already has its own shadows; it only receives ours
    for did, door in DOORS.items():
        if not door.get("rect"):
            continue
        u0, v0, u1, v1 = door["rect"]
        source_mesh = relief.data
        source_uv = source_mesh.uv_layers.active.data
        source_faces = []
        world_points = []
        for polygon in source_mesh.polygons:
            loop_ids = list(polygon.loop_indices)
            image_points = [(source_uv[i].uv.x, 1.0 - source_uv[i].uv.y) for i in loop_ids]
            if not all(u0 <= u <= u1 and v0 <= v <= v1 for u, v in image_points):
                continue
            coords = [relief.matrix_world @ source_mesh.vertices[source_mesh.loops[i].vertex_index].co
                      for i in loop_ids]
            source_faces.append(coords)
            world_points.extend(coords)
        if not source_faces:
            log(f"WARNING door {did}: picture rectangle did not produce a 3D panel")
            continue
        camera_matrix = cam.matrix_world
        camera_rotation = camera_matrix.to_3x3()
        camera_inverse = camera_matrix.inverted()
        image_width, image_height = SET["size"]
        distance = statistics.median(
            -(camera_inverse @ co).z for co in world_points
        )

        def image_ray(u, v):
            return Vector(((u - 0.5) * cam.data.sensor_width / cam.data.lens,
                           (0.5 - v) * cam.data.sensor_width * image_height
                           / (image_width * cam.data.lens), -1.0))

        centre_ray = image_ray((u0 + u1) / 2, (v0 + v1) / 2)
        camera_centre = cam.location + camera_rotation @ (centre_ray * distance)
        toward_camera = cam.location - camera_centre
        toward_camera.z = 0
        face_normals = []
        for coords in source_faces:
            if len(coords) >= 3:
                face_normal = (coords[1] - coords[0]).cross(coords[2] - coords[0])
                if face_normal.length > 1e-6:
                    face_normal.normalize()
                    if face_normal.dot(toward_camera) < 0:
                        face_normal.negate()
                    face_normals.append(face_normal)
        if not face_normals:
            log(f"WARNING door {did}: picture panel has no stable surface normal")
            continue
        normal = Vector(tuple(statistics.median(getattr(n, axis) for n in face_normals)
                              for axis in ("x", "y", "z")))
        normal.z = 0
        if normal.length < 1e-6:
            log(f"WARNING door {did}: picture panel has no horizontal surface normal")
            continue
        normal.normalize()
        front = Vector((normal.x, normal.y, 0))

        def on_panel(u, v):
            ray = camera_rotation @ image_ray(u, v)
            denominator = normal.dot(ray)
            if abs(denominator) < 1e-6:
                raise ValueError(f"picture door {did} is edge-on to the set camera")
            depth = normal.dot(camera_centre - cam.location) / denominator
            return cam.location + ray * depth

        try:
            corners = [on_panel(u0, v1), on_panel(u1, v1),
                       on_panel(u1, v0), on_panel(u0, v0)]
        except ValueError as exc:
            log(f"WARNING door {did}: {exc}")
            continue
        centre = sum(corners, Vector()) / len(corners)
        pivot = (corners[0] + corners[3]) / 2
        across = (corners[1] + corners[2] - corners[0] - corners[3]) / 2
        across.z = 0
        if across.length < 1e-6:
            log(f"WARNING door {did}: fitted panel has no usable width direction")
            continue
        across.normalize()
        picture_width = max((co - pivot).dot(across) for co in corners)
        panel_vertices = [co - pivot for co in corners]
        panel_order = [0, 1, 2, 3]
        if (corners[1] - corners[0]).cross(corners[2] - corners[1]).dot(normal) < 0:
            panel_order.reverse()
        panel_uvs = [(u0, 1.0 - v1), (u1, 1.0 - v1),
                     (u1, 1.0 - v0), (u0, 1.0 - v0)]

        root = door["hinge"].parent
        root.location = (0, 0, 0)
        root.rotation_euler = (0, 0, 0)
        root.scale = (1, 1, 1)
        door["hinge"].location = pivot
        door["hinge"].rotation_euler = (0, 0, 0)
        panel, knob = door["panel"]
        mesh = bpy.data.meshes.new(f"{did}_surface")
        mesh.from_pydata(panel_vertices, [], [panel_order])
        uv_layer = mesh.uv_layers.new(name="cf_picture")
        for loop_index, vertex_index in enumerate(panel_order):
            uv_layer.data[loop_index].uv = panel_uvs[vertex_index]
        mesh.uv_layers.active = uv_layer
        uv_layer.active_render = True
        panel.data = mesh
        panel.location = (0, 0, 0)
        panel.rotation_euler = (0, 0, 0)
        panel.scale = (1, 1, 1)
        panel.parent = door["hinge"]
        panel.matrix_parent_inverse = Matrix.Identity(4)
        panel.data.materials.clear()
        panel.data.materials.append(image_material(f"{did}_picture_face", True, "UV"))
        door["fitted_panel"] = True
        door["centre"] = Vector((centre.x, centre.y, centre.z))
        door["heading"] = math.atan2(front.x, -front.y)
        door["front"] = front
        door["across"] = across
        door["picture_width"] = picture_width
        knob.hide_render = True
        backing = bpy.data.objects.get(f"{did}_part3")
        for child in root.children_recursive:
            if child not in (panel, backing) and child.type == "MESH":
                child.hide_render = True
        if backing:
            backing_mesh = bpy.data.meshes.new(f"{did}_interior")
            backing_mesh.from_pydata([co - normal * 0.025 for co in corners], [], [panel_order])
            backing.data = backing_mesh
            backing.location = (0, 0, 0)
            backing.rotation_euler = (0, 0, 0)
            backing.scale = (1, 1, 1)
            backing.parent = root
            backing.matrix_parent_inverse = Matrix.Identity(4)
        log(f"door {did}: fitted a {picture_width:.2f} m relief-oriented panel from "
            f"{len(source_faces)} set faces")
    picture_road_polygons = []
    picture_roads = [p for p in spec.get("props", []) if p.get("make") == "picture_road"]
    if picture_roads:
        sys.path.insert(0, os.path.join(HERE, "..", "generate"))
        from set_props import write_picture_road
        for prop in picture_roads:
            road_path = os.path.join(set_dir, "props", f"{prop.get('id', 'picture_road')}.obj")
            polygon = write_picture_road(prop, SET, road_path)
            before = set(bpy.data.objects)
            bpy.ops.wm.obj_import(filepath=road_path, forward_axis="Y", up_axis="Z")
            road = next((o for o in bpy.data.objects if o not in before and o.type == "MESH"), None)
            if road is None:
                raise RuntimeError(f"picture road {prop.get('id', '?')} produced no mesh")
            road.name = prop.get("id", "picture_road")
            road.data.materials.clear()
            road.data.materials.append(image_material(f"{road.name}_picture", True, "UV"))
            picture_road_polygons.append((road.name, polygon))
            log(f"picture road {road.name}: {len(polygon)} footprint points, {prop['width']:.2f} m wide")
    # A picture-matched panel is fitted to the image rectangle and oriented from the relief surface.
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(relief.data)
    uv_layer = bm.loops.layers.uv.active
    to_cam = cam.matrix_world.inverted()
    bpy.context.view_layer.update()
    frame = [Vector(c) for c in cam.data.view_frame(scene=scene)]     # TR, BR, BL, TL at distance 1
    cut = 0
    for did, door in DOORS.items():
        doomed = []
        if door.get("rect"):
            u0, v0, u1, v1 = door["rect"]
            for face in bm.faces:
                if all(u0 <= l[uv_layer].uv.x <= u1 and v0 <= 1 - l[uv_layer].uv.y <= v1 for l in face.loops):
                    doomed.append(face)
        else:
            to_door = Matrix.Rotation(-door["heading"], 3, "Z")
            hw, hh = door["width"] / 2 + 0.02, door["height"]
            for face in bm.faces:
                inside = 0
                for v in face.verts:
                    p = to_door @ (relief.matrix_world @ v.co - door["centre"])
                    inside += (abs(p.x) < hw and -0.05 < p.y < 1.5 and -0.2 < p.z < hh)
                if inside == len(face.verts):
                    doomed.append(face)
        bmesh.ops.delete(bm, geom=doomed, context="FACES")
        cut += len(doomed)
    for road_id, polygon in picture_road_polygons:
        doomed = []
        for face in bm.faces:
            u = sum(loop[uv_layer].uv.x for loop in face.loops) / len(face.loops)
            v = 1.0 - sum(loop[uv_layer].uv.y for loop in face.loops) / len(face.loops)
            inside = False
            j = len(polygon) - 1
            for i, (x_i, y_i) in enumerate(polygon):
                x_j, y_j = polygon[j]
                if (y_i > v) != (y_j > v) and u < (x_j - x_i) * (v - y_i) / (y_j - y_i) + x_i:
                    inside = not inside
                j = i
            if inside:
                doomed.append(face)
        bmesh.ops.delete(bm, geom=doomed, context="FACES")
        log(f"picture road {road_id}: removed {len(doomed)} overlapping set faces")
    bm.to_mesh(relief.data)
    bm.free()
    if cut:
        log(f"cut {cut} set faces out of door openings")
    from bpy_extras.object_utils import world_to_camera_view
    bpy.context.view_layer.update()
    for did, door in DOORS.items():
        if not door.get("match"):
            continue
        panel, knob = door["panel"]
        knob.hide_render = True                       # the picture's door has its own handle
        if door.get("fitted_panel"):
            log(f"door {did}: using its camera-fitted panel")
            continue
        me = panel.data
        uv = me.uv_layers.new(name="cf_picture")
        for loop in me.loops:
            co = world_to_camera_view(scene, cam, panel.matrix_world @ me.vertices[loop.vertex_index].co)
            uv.data[loop.index].uv = (co.x, co.y)
        me.uv_layers.active = uv
        uv.active_render = True                       # the render uses this map, not the box's own
        panel.data.materials.clear()
        panel.data.materials.append(image_material(f"{did}_picture_face", True, "UV"))
        log(f"door {did}: face taken from the picture")
    # far fill for the few gaps behind objects that close-up cameras can see
    bpy.ops.mesh.primitive_plane_add(size=400, location=(0, 120, 20), rotation=(math.pi / 2, 0, 0))
    back = bpy.context.object; back.name = "Backdrop"
    back.data.materials.append(image_material("Backdrop", False, "Window"))
    back.visible_shadow = False
    cx, cy = 0.0, ORIGIN.y
else:
    xs = [a.pos.x for a in cast.values()] + [to_world(s["to"]).x for s in spec["script"] if s["do"] == "walk"]
    ys = [a.pos.y for a in cast.values()] + [to_world(s["to"]).y for s in spec["script"] if s["do"] == "walk"]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    half_w = (max(xs) - min(xs)) / 2 + 1.0
    cam.data.lens = 35
    dist = max(half_w / math.tan(math.atan(18 / 35)), 4.0)
    cam.location = (cx, cy - dist, 1.45)
    look = Vector((cx, cy, 1.05)) - Vector(cam.location)
    cam.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()
    if spec.get("camera"):
        # a fixed framing, e.g. inside a car: {"location": [x, y, z], "look_at": [x, y, z], "lens": 28}
        cs = spec["camera"]
        cam.location = to_world(cs["location"][:2]) + Vector((0, 0, cs["location"][2]))
        look = to_world(cs["look_at"][:2]) + Vector((0, 0, cs["look_at"][2])) - Vector(cam.location)
        cam.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()
        cam.data.lens = cs.get("lens", 35)
    if not SET:
        bpy.context.view_layer.update()
        fit_picture_props()


# shots: director.py decides which shot when; these build the cameras. A 3D set made from one picture only
# holds up near the picture's own viewpoint, so every camera stays close to it and frames by lens.
FRAMING = {"close": (0.55, 0.05, 1.8), "medium": (1.15, 0.32, 2.8)}     # frame height (m), aim drop, f-stop


def frame_by_lens(c, distance, height):
    """Pick the lens that makes `height` metres fill the frame at `distance` (horizontal sensor fit)."""
    sensor_v = c.data.sensor_width * scene.render.resolution_y / scene.render.resolution_x
    c.data.lens = max(24.0, min(135.0, sensor_v * distance / height))


def close_up(actor, n, frame, size="close"):
    c = bpy.data.objects.new(f"CU_{actor.id}_{n}", bpy.data.cameras.new(f"CU_{actor.id}_{n}"))
    scene.collection.objects.link(c)
    # aim at where the head really is during the line (seated people sit lower)
    scene.frame_set(frame)
    head = actor.rig.matrix_world @ actor.pb["head"].head + Vector((0, 0, 0.06))
    facing = actor.rig.matrix_world.to_3x3() @ Vector((0, -1, 0))
    facing.z = 0
    facing.normalize()
    to_main = (Vector(cam.location) - head)
    to_main.z = 0
    if SET:
        # a 3D set made from one picture only holds up near the picture's own viewpoint: move in from
        # the main camera towards the speaker (a little to the side they face), long lens, soft background.
        # Nobody may stand between the camera and the face: try other angles until the view is clear.
        c.data.lens = 85
        dist = to_main.length
        toward = to_main.normalized()
        lateral = facing - toward * facing.dot(toward)
        others = [o.rig.matrix_world.translation.copy() for o in cast.values() if o is not actor]

        def blocked(loc):
            seg = head - loc
            for o in others:
                # closest approach of the camera-to-face line to the other person's body (vertical axis)
                tt = max(0.0, min(1.0, (Vector((o.x, o.y, 0)) - Vector((loc.x, loc.y, 0))).dot(
                    Vector((seg.x, seg.y, 0))) / max(Vector((seg.x, seg.y, 0)).length_squared, 1e-6)))
                p_ = loc + seg * tt
                if 0.1 < tt < 0.9 and math.hypot(p_.x - o.x, p_.y - o.y) < 0.3:
                    return True
            return False

        side_dir = Vector((-toward.y, toward.x, 0))
        lat = lateral.normalized() if lateral.length > 1e-6 else side_dir
        # small moves only (the set smears far from the picture's viewpoint); preferred angle first
        cands = [lat * 1.0, lat * 0.6, side_dir * 0.0, lat * -0.4, lat * 1.4]
        loc = None
        for back in (min(2.4, 0.55 * dist), min(1.7, 0.42 * dist)):
            for off in cands:
                trial = head + toward * back + off + Vector((0, 0, 0.02))
                if not blocked(trial):
                    loc = trial
                    break
            if loc:
                break
        if loc is None:                         # crowded: accept an over-the-shoulder view
            loc = head + toward * min(2.4, 0.55 * dist) + lat * 1.0 + Vector((0, 0, 0.02))
        c.location = loc
    else:
        c.data.lens = 50
        d = (0.55 * facing + 0.45 * to_main.normalized()).normalized()
        c.location = head + d * 1.45 + Vector((0, 0, 0.02))
    height, drop, fstop = FRAMING[size]
    frame_by_lens(c, (head - Vector(c.location)).length, height)
    c.data.dof.use_dof = True
    c.data.dof.focus_distance = (head - Vector(c.location)).length
    c.data.dof.aperture_fstop = fstop
    # frame the speaker on the side opposite their gaze, so they look into the shot
    fwd = (head - c.location).normalized()
    right = fwd.cross(Vector((0, 0, 1))).normalized()
    side = 1 if facing.dot(right) > 0 else -1
    target = head - Vector((0, 0, drop)) + right * side * 0.16 * height / 0.55
    c.rotation_euler = (target - c.location).to_track_quat("-Z", "Y").to_euler()
    c["cf_subject"] = head
    return c


def two_shot(actors, n, frame):
    """Both speakers in one frame, from a little in front of the main camera."""
    c = bpy.data.objects.new(f"TWO_{n}", bpy.data.cameras.new(f"TWO_{n}"))
    scene.collection.objects.link(c)
    scene.frame_set(frame)
    heads = [a.rig.matrix_world @ a.pb["head"].head + Vector((0, 0, 0.06)) for a in actors]
    mid = sum(heads, Vector()) / len(heads)
    span = max((h.xy - g.xy).length for h in heads for g in heads)
    to_main = Vector(cam.location) - mid
    to_main.z = 0
    dist = to_main.length
    back = min(dist * 0.75, max(2.4, span * 1.8)) if SET else max(2.4, span * 1.8)
    c.location = mid + to_main.normalized() * back + Vector((0, 0, 0.04))
    d = (mid - Vector(c.location)).length
    c.data.lens = max(24.0, min(85.0, c.data.sensor_width * d / (span + 1.3)))
    c.data.dof.use_dof = True
    c.data.dof.focus_distance = d
    c.data.dof.aperture_fstop = 4.0
    c.rotation_euler = (mid - Vector((0, 0, 0.22)) - c.location).to_track_quat("-Z", "Y").to_euler()
    c["cf_subject"] = mid
    return c


def over_shoulder(speaker, listener, n, frame):
    """The speaker's face over the listener's shoulder; on a set made from a picture only when that angle
    stays within 25 degrees of the picture's own view (else a close-up)."""
    scene.frame_set(frame)
    face = speaker.rig.matrix_world @ speaker.pb["head"].head + Vector((0, 0, 0.06))
    shoulder = listener.rig.matrix_world @ listener.pb["head"].head + Vector((0, 0, -0.08))
    away = shoulder - face
    away.z = 0
    away.normalize()
    side = away.cross(Vector((0, 0, 1)))
    if side.dot(Vector(cam.location) - shoulder) < 0:
        side = -side
    loc = shoulder + away * 0.55 + side * 0.3 + Vector((0, 0, 0.06))
    from_main = face - Vector(cam.location)
    if SET and math.degrees((face - loc).angle(from_main)) > 25:
        return close_up(speaker, n, frame, "close")
    c = bpy.data.objects.new(f"OTS_{speaker.id}_{n}", bpy.data.cameras.new(f"OTS_{speaker.id}_{n}"))
    scene.collection.objects.link(c)
    c.location = loc
    frame_by_lens(c, (face - loc).length, 0.75)
    c.data.dof.use_dof = True
    c.data.dof.focus_distance = (face - loc).length
    c.data.dof.aperture_fstop = 2.2
    c.rotation_euler = (face - Vector((0, 0, 0.1)) - loc).to_track_quat("-Z", "Y").to_euler()
    c["cf_subject"] = face
    return c


def shake(c, strength=0.012, scale=10.0):
    """Handheld or vehicle shake: an F-curve noise modifier on the camera's rotation."""
    from bpy_extras import anim_utils
    if not (c.animation_data and c.animation_data.action):
        c.keyframe_insert("rotation_euler", frame=1)
    ad = c.animation_data
    bag = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
    for fc in bag.fcurves:
        if fc.data_path == "rotation_euler":
            m = fc.modifiers.new("NOISE")
            m.scale, m.strength, m.phase = scale, strength, rand.uniform(0, 50)


def camera_move(c, move, f0, f1):
    """push_in / pull_out (dolly 18 % towards the subject), pan_left / pan_right, handheld."""
    subject = Vector(c["cf_subject"]) if "cf_subject" in c else None
    if move in ("push_in", "pull_out") and subject is not None:
        near = Vector(c.location).lerp(subject, 0.18)
        a, b = (Vector(c.location), near) if move == "push_in" else (near, Vector(c.location))
        for f, loc in ((f0, a), (f1, b)):
            c.location = loc
            c.keyframe_insert("location", frame=f)
            c.data.dof.focus_distance = (subject - loc).length
            c.data.dof.keyframe_insert("focus_distance", frame=f)
    elif move in ("pan_left", "pan_right"):
        rot = c.rotation_euler.copy()
        for f, dz in ((f0, 0.0), (f1, 0.1 if move == "pan_left" else -0.1)):
            c.rotation_euler = (rot.x, rot.y, rot.z + dz)
            c.keyframe_insert("rotation_euler", frame=f)
    elif move == "handheld":
        shake(c, 0.006, 18.0)


def follow(actor, f0, f1, n):
    """Pan with a walking person. The camera stays exactly where the picture was taken and only turns
    (a longer lens inside the picture's own field of view), so the 3D set never smears."""
    c = bpy.data.objects.new(f"FOLLOW_{actor.id}_{n}", bpy.data.cameras.new(f"FOLLOW_{actor.id}_{n}"))
    scene.collection.objects.link(c)
    c.location = cam.location
    wide = cam.data.lens
    c.data.lens = min(wide * 1.8, 40.0)
    c.data.sensor_width, c.data.sensor_fit = cam.data.sensor_width, "HORIZONTAL"
    half_w = lambda lens: math.atan(c.data.sensor_width / 2 / lens)            # noqa: E731
    aspect = scene.render.resolution_y / scene.render.resolution_x
    half_h = lambda lens: math.atan(c.data.sensor_width * aspect / 2 / lens)   # noqa: E731
    max_yaw, max_pitch = half_w(wide) - half_w(c.data.lens), half_h(wide) - half_h(c.data.lens)
    yaw = pitch = None
    for f in range(f0 - 6, f1 + 13):
        scene.frame_set(f)
        aim = actor.rig.matrix_world @ actor.pb["torso"].head + Vector((0, 0, 0.25))
        d = aim - Vector(c.location)
        ty = max(-max_yaw, min(max_yaw, math.atan2(-d.x, d.y)))
        base = -SET["camera"].get("pitch", 0.0)
        tp = max(base - max_pitch, min(base + max_pitch, math.atan2(d.z, math.hypot(d.x, d.y))))
        # an operator follows a little late and smoothly
        yaw = ty if yaw is None else yaw + 0.18 * (ty - yaw)
        pitch = tp if pitch is None else pitch + 0.18 * (tp - pitch)
        c.rotation_euler = (math.pi / 2 + pitch, 0, yaw)
        c.keyframe_insert("rotation_euler", frame=f)
    return c


mode = spec.get("shots", "auto")
mode = mode if mode in ("auto", "classic") else "none"
plan = director.plan(
    [{k: ln[k] for k in ("f0", "f1", "who", "kind", "expression", "listener")} for ln in lines],
    [{"who": a.id, "f0": f0, "f1": f1} for a, f0, f1 in moves], forced, FPS, scene.frame_end, mode,
    follow=bool(SET), strong=acting.STRONG,
    beats=[{"who": a.id, "target": d.id, "f0": f0, "f1": f1, "contact": c} for a, d, f0, f1, c in beats])
shot_list = []                      # (frame, kind, on) for the timeline and the storyboard
for n, sh in enumerate(plan):
    f0 = sh["frame"]
    f1 = plan[n + 1]["frame"] if n + 1 < len(plan) else scene.frame_end
    who = [cast[w] for w in sh["on"] if w in cast]
    kind = sh["kind"]
    if kind in ("close", "medium") and who:
        c = close_up(who[0], n, f0 + 2, kind)
    elif kind == "two_shot" and len(who) >= 2:
        c = two_shot(who[:2], n, f0 + 2)
    elif kind == "two_shot" and who:
        c = close_up(who[0], n, f0 + 2, "medium")
    elif kind == "over_shoulder" and who:
        other = cast[sh["on"][1]] if len(sh["on"]) > 1 and sh["on"][1] in cast else listener_of(who[0])
        c = over_shoulder(who[0], other, n, f0 + 2) if other else close_up(who[0], n, f0 + 2)
    elif kind == "follow" and who and SET:
        c = follow(who[0], f0, max(f0 + 1, f1 - 12), n)
    elif sh["move"] != "static" or sh["lens"]:
        c = cam.copy()                                     # the wide view, moving on its own
        c.data = cam.data.copy()
        c.name = f"WIDE_{n}"
        scene.collection.objects.link(c)
        c["cf_subject"] = sum((a.pos for a in cast.values()), Vector()) / max(len(cast), 1) + Vector((0, 0, 1.3))
    else:
        c = cam
    if sh["lens"]:
        c.data.lens = float(sh["lens"])
    if sh["move"] != "static":
        camera_move(c, sh["move"], f0, f1)
    scene.timeline_markers.new(f"shot_{n}", frame=max(f0, 1)).camera = c
    shot_list.append((f0, kind, sh["on"]))
log(f"shots ({mode}): " + ", ".join(f"{k}{'/' + '+'.join(o) if o else ''}@{f}" for f, k, o in shot_list))

if spec.get("vehicle"):
    for c in [o for o in scene.objects if o.type == "CAMERA"]:
        shake(c)

if not SET:
    bpy.ops.mesh.primitive_plane_add(size=60, location=(cx, cy, 0))
    floor = bpy.context.object; floor.name = "Floor"
    floor.data.materials.append(image_material("FloorFromBackground", True, "Window"))
    bpy.ops.mesh.primitive_plane_add(size=80, location=(cx, cy + 5, 20), rotation=(math.pi / 2, 0, 0))
    back = bpy.context.object; back.name = "Backdrop"
    back.data.materials.append(image_material("Backdrop", False, "Window"))
    back.visible_shadow = False



sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
sun.data.energy = SUN_ENERGY
sun.data.color = SUN_COLOR
sun.rotation_euler = SUN_ROT
scene.collection.objects.link(sun)
world = bpy.data.worlds.new("World"); scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (*WORLD_COLOR, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = WORLD

# --- sound -------------------------------------------------------------------------------------------
se = scene.sequence_editor_create()
strips = se.strips if hasattr(se, "strips") else se.sequences
SFX_DIR = config.SFX_DIR
LIBRARY = json.load(open(os.path.join(SFX_DIR, "library.json"))) if os.path.exists(os.path.join(SFX_DIR, "library.json")) else {}
from bpy_extras.object_utils import world_to_camera_view  # noqa: E402


def bed_file(name):
    if os.path.exists(path(name)):
        return path(name)
    lib = LIBRARY.get("beds", {})
    if name not in lib:
        raise ValueError(f"no sound file or library bed called {name!r}")
    return os.path.join(SFX_DIR, lib[name][0])


def radio(src):
    """A copy of src that sounds like a small car radio (narrow band, a little compressed)."""
    out_ = os.path.join(SCENE_DIR, "radio_" + os.path.basename(src))
    if not os.path.exists(out_):
        subprocess.run([config.FFMPEG, "-v", "error", "-y", "-i", src, "-af", media.VOICE_FX["radio"], "-ac", "1", out_],
                       check=True)
    return out_


def pan_of(where, width):
    """Stereo position of a sound from where its source is in the wide shot (stable across cuts)."""
    if where is None:
        return 0.0
    x = world_to_camera_view(scene, cam, Vector((where[0], where[1], 1.0))).x
    return max(-0.8, min(0.8, 2.0 * (x - 0.5) * width))


# dialogue (and narration) intervals, merged when closer than 1.2 s: music and ambience dip under them
talk = []
for ln in sorted(lines, key=lambda x: x["f0"]):
    if talk and ln["f0"] - talk[-1][1] < 1.2 * FPS:
        talk[-1][1] = max(talk[-1][1], ln["f1"])
    else:
        talk.append([ln["f0"], ln["f1"]])
DUCK = spec.get("duck", True)


def lay_bed(name, channel, volume, start=1, stop=None, fade=0.0, duck_db=0.0):
    """Loop a bed from start to stop (or the end), fading in/out, dipping by duck_db under dialogue."""
    stop = stop or scene.frame_end
    pieces, f = [], start
    while f < stop:
        s = strips.new_sound(f"bed_{channel}", name, channel, f)
        if s.frame_final_end > stop:
            s.frame_final_end = stop
        pieces.append(s)
        f = s.frame_final_end
    gain = 10 ** (duck_db / 20) if DUCK and duck_db else 1.0
    keys = [(start, 0.0 if fade else 1.0), (start + int(fade * FPS), 1.0)] if fade else [(start, 1.0)]
    for a, b in talk if gain < 1 else []:
        if b < start or a > stop:
            continue
        keys += [(a - int(0.25 * FPS), 1.0), (a, gain), (b, gain), (b + int(0.6 * FPS), 1.0)]
    if stop < scene.frame_end:
        keys += [(stop - int(max(fade, 0.5) * FPS), 1.0), (stop, 0.0)]
    keys.sort()
    for s in pieces:
        for f, k in keys:
            s.volume = volume * k
            s.keyframe_insert("volume", frame=max(f, 1))


if spec.get("ambience"):
    lay_bed(bed_file(spec["ambience"]), 1, spec.get("ambience_volume", 0.5), duck_db=-4)
music = spec.get("music")
if music:
    m = music if isinstance(music, dict) else {"bed": music}
    src = bed_file(m["bed"])
    lay_bed(radio(src) if m.get("radio") else src, 10, m.get("volume", 0.35), duck_db=-9)
for n, (f, bed, volume, fade) in enumerate(music_cues):
    if bed:
        stop = next((g for g, b2, _, _ in music_cues[n + 1:] if g > f), None)
        lay_bed(bed_file(bed), 11 + n % 2, volume, start=f, stop=stop, fade=fade, duck_db=-9)
for wav, frame, ch, where in sounds:
    s = strips.new_sound(os.path.basename(wav), wav, ch, frame)
    s.pan = pan_of(where, 0.25)                     # dialogue stays near the centre, as in film mixes

# --- pose fixes: the last word on a bone (scene.json "fixes"), applied over everything above ----------
def apply_fixes(entries):
    """Turn body parts a little at given moments, on top of the finished animation: the user's hand-made
    corrections from the app's 3D editor. Each entry: who, at (seconds), part, rotate [x, y, z] degrees,
    optional seconds (hold) and fade."""
    done = 0
    for fix in entries:
        who = cast.get(fix.get("who"))
        part = acting.FIX_PARTS.get(fix.get("part"))
        if who is None or part is None or part not in who.pb:
            log(f"WARNING pose fix skipped (unknown character or body part): {fix}")
            continue
        turn = [math.radians(float(v)) for v in (fix.get("rotate") or [0, 0, 0])]
        if not any(turn):
            continue
        pb = who.pb[part]
        pb.rotation_mode = "QUATERNION"
        extra = (Matrix.Rotation(turn[0], 3, "X") @ Matrix.Rotation(turn[1], 3, "Y")
                 @ Matrix.Rotation(turn[2], 3, "Z"))
        keys = acting.fix_frames(fix, FPS, scene.frame_end)
        # read every base pose first: writing a key would otherwise change what the next frame reads back,
        # and the fix would pile onto itself
        base = []
        for f, w in keys:
            scene.frame_set(f)
            base.append((f, w, pb.rotation_quaternion.copy()))
        for f, w, q in base:
            turned = (q.to_matrix() @ extra).to_quaternion()
            pb.rotation_quaternion = q.slerp(turned, w)
            pb.keyframe_insert("rotation_quaternion", frame=f)
        if keys:
            done += 1
            log(f"pose fix: {fix.get('who')} {fix.get('part')} at {fix.get('at', 0)}s "
                f"({', '.join(str(round(v, 1)) for v in fix.get('rotate') or [])} deg, {len(keys)} keys)")
    if entries:
        log(f"pose fixes: {done} of {len(entries)} applied")


apply_fixes(spec.get("fixes") or [])

# footsteps: a different recorded step for every landing, on the scene's floor type, placed and faded by distance
steps_lib = LIBRARY.get("footsteps", {}).get(spec.get("floor", "wood"), [])
n = 0
for act in cast.values():
    for f, where in act.footfalls:
        if steps_lib:
            s = strips.new_sound("step", os.path.join(SFX_DIR, rand.choice(steps_lib)), 6 + n % 2, f)
            far = (Vector((where[0], where[1], 0)) - Vector((cam.location[0], cam.location[1], 0))).length
            s.volume = spec.get("footstep_volume", 0.5) * rand.uniform(0.8, 1.0) * 10 ** (-6 * min(far / 8, 1) / 20)
            s.pan = pan_of(where, 0.7)
            n += 1
log(f"footsteps: {n} on {spec.get('floor', 'wood')}")
sfx_lib = LIBRARY.get("sfx", {})
used = {}
for k, (name, frame, vol, where) in enumerate(sfx_events):
    if sfx_lib.get(name):
        # takes are ranked best-first (generate/rank_sfx.py); repeats rotate so they don't sound copied
        take = sfx_lib[name][used.get(name, 0) % len(sfx_lib[name])]
        used[name] = used.get(name, 0) + 1
        s = strips.new_sound(name, os.path.join(SFX_DIR, take), 8 + k % 2, max(frame, 1))
        s.volume = vol
        s.pan = pan_of(where, 0.7)
    else:
        log(f"WARNING no '{name}' sound in sfx/library.json (python generate/make_sfx_library.py sfx --missing)")

# --- light, weather, render settings -------------------------------------------------------------------
scene.render.engine = "BLENDER_EEVEE"
res = config.resolution(QUALITY, spec)
scene.render.resolution_x, scene.render.resolution_y = res
scene.render.resolution_percentage = 100
scene.eevee.taa_render_samples = SAMPLES
if not FULL_DETAIL:
    # fast: no subdivision smoothing, no ray tracing, no motion blur
    scene.render.use_simplify = True
    scene.render.simplify_subdivision_render = 0
    scene.eevee.use_raytracing = False
    scene.eevee.use_fast_gi = False
    scene.render.use_motion_blur = False
    # depth of field stays on: it is cheap and it hides the rough far edges of a set made from a picture
log(f"quality: {QUALITY} {res[0]}x{res[1]}, {SAMPLES} sample(s), look {LOOK}")
if LOOK == "cinematic":
    # film-style light on the cast and props only (light linking): the set keeps the picture's own light
    receivers = bpy.data.collections.new("CF_lit_by_key")
    for a in cast.values():
        for o in a.rig.children_recursive:
            if o.type == "MESH":
                receivers.objects.link(o)
    for o in scene.objects:
        if o.parent and o.parent.name in prop_tops and o.type == "MESH":
            receivers.objects.link(o)
    centre = sum((a.pos for a in cast.values()), Vector()) / max(len(cast), 1) + Vector((0, 0, 1.3))
    world_kit.cinematic_lights(scene, centre, cam.location, receivers, MOOD)
    e = scene.eevee
    e.use_raytracing = True
    e.use_fast_gi = True
    e.shadow_ray_count, e.shadow_step_count = 2, 8
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 0.5
# the picture is shown as it is (Standard); contrast and colour looks are applied in finishing (core/finish.py)
scene.view_settings.view_transform = "Standard"
scene.view_settings.look = "None"
weather_note = world_kit.weather(scene, cam, spec.get("weather"), scene.frame_end, FPS, FAST, spec.get("seed", 7),
                                 tuple(0.6 + 0.4 * c for c in WORLD_COLOR))
if weather_note:
    log("weather:", weather_note)
if prop_factory.FLAMES:
    world_kit.flicker(prop_factory.FLAMES, scene.frame_end, FPS, rand)

out = os.path.abspath(args.out)
base = os.path.splitext(out)[0]
os.makedirs(os.path.dirname(out), exist_ok=True)
timeline = {"version": 1, "id": spec.get("id", "scene"), "fps": FPS, "frames": scene.frame_end,
            "duration": scene.frame_end / FPS, "resolution": list(res), "quality": QUALITY,
            "lines": [{"start": (ln["f0"] - 1) / FPS, "end": (ln["f1"] - 1) / FPS, "who": ln["who"],
                       "kind": ln["kind"], "text": ln["text"]} for ln in lines],
            "shots": [{"time": (f - 1) / FPS, "kind": k, "on": on} for f, k, on in shot_list]}

if args.preview3d:
    # the scene as a light 3D file for the app's scene editor: cast with their baked motion (deform bones only,
    # no face shapes), set and props; every other frame. preview.json maps its timeline back to scene.json.
    def ever_shown(o):              # visible at some frame (someone who exits is keyed hidden at the end)
        if not o.hide_render:
            return True
        ad = o.animation_data
        bag = ad and ad.action and anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
        fc = bag and bag.fcurves.find("hide_render")
        return bool(fc) and any(k.co[1] < 0.5 for k in fc.keyframe_points)

    bpy.ops.object.select_all(action="DESELECT")
    motion_coll = bpy.data.collections.get("CF_motion")
    for o in scene.objects:
        if o.type in {"MESH", "ARMATURE"} and ever_shown(o) and not o.name.startswith("WGT-")                 and not (motion_coll and o.name in motion_coll.objects) and not any(
                    c.hide_render for c in o.users_collection):
            o.hide_viewport = False
            o.hide_set(False)
            o.select_set(True)
            for m in getattr(o, "modifiers", []):  # masks and cloth offsets apply; subdivision only weighs it down
                if m.type == "SUBSURF":
                    m.show_viewport = m.show_render = False
    glb = os.path.join(os.path.dirname(out), "preview.glb")
    bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True, export_animations=True,
                              export_animation_mode="SCENE", export_frame_step=2, export_def_bones=True,
                              export_morph=False, export_lights=False, export_cameras=False, export_apply=True)
    origin = to_world((0.0, 0.0))

    def start_spot(a):                  # where someone is on frame 1 (seated starts have no "position")
        x, y = (c.evaluate(1) if c else 0.0 for c in a.curves[0][:2])
        return [round(x - origin.x, 3), round(y - origin.y, 3)]

    json.dump({"fps": FPS, "frames": scene.frame_end, "origin": [origin.x, origin.y],
               "cast": {cid: {"start": start_spot(a), "rig": a.rig.name} for cid, a in cast.items()},
               "steps": [{"n": i, "who": st.get("who"), "do": st["do"], "f0": f0, "f1": f1,
                          **({"to": st["to"]} if isinstance(st.get("to"), list) else {})}
                         for i, (st, (f0, f1)) in enumerate(zip(spec["script"], step_frames))],
               "props": [{"id": pr["id"], "position": [round(float(v), 3) for v in pr.get("position", [0, 0])],
                          **{k: pr[k] for k in ("rotation", "on", "make", "from_set") if pr.get(k) is not None}}
                         for pr in spec.get("props", []) if isinstance(pr, dict) and pr.get("id")],
               "lines": timeline["lines"], "shots": timeline["shots"]},
              open(os.path.join(os.path.dirname(out), "preview.json"), "w", encoding="utf-8"), indent=1)
    log(f"3D preview: {os.path.getsize(glb) / 1e6:.1f} MB")
    sys.exit(0)

if args.storyboard:
    # one small still per shot, a little into it, with what is being said there
    board = os.path.join(os.path.dirname(out), "storyboard")
    os.makedirs(board, exist_ok=True)
    shots_meta = []
    for n, (f, kind, on) in enumerate(shot_list):
        nxt = shot_list[n + 1][0] if n + 1 < len(shot_list) else scene.frame_end
        at = min(f + 6, (f + nxt) // 2)
        scene.frame_set(at)
        scene.render.filepath = os.path.join(board, f"shot_{n + 1:02d}.png")
        bpy.ops.render.render(write_still=True)
        said = next((ln["text"] for ln in lines if ln["f0"] <= at <= ln["f1"]), "")
        shots_meta.append({"image": f"storyboard/shot_{n + 1:02d}.png", "time": (f - 1) / FPS, "kind": kind,
                           "on": on, "text": said})
    json.dump({"shots": shots_meta}, open(os.path.join(os.path.dirname(out), "storyboard.json"), "w",
                                          encoding="utf-8"), indent=1)
    log(f"storyboard: {len(shots_meta)} shots")
    sys.exit(0)

bpy.ops.wm.save_as_mainfile(filepath=base + ".blend")
log("saved scene", base + ".blend", f"{scene.frame_end} frames")
if args.stills:
    for f in [int(x) for x in args.stills.split(",")]:
        scene.frame_set(f)
        scene.render.filepath = base + f"_f{f:04d}.png"
        bpy.ops.render.render(write_still=True)
    log("stills", args.stills)
else:
    # resumable: every frame is its own PNG; frames already on disk are skipped, so a stopped render
    # continues where it left off. The sound is mixed separately and both are joined by ffmpeg.
    import glob
    import shutil
    frames_dir = base + "_frames"
    # frames are only reused for the same scene: the same render key as the episode job's shot cache
    key = args.render_key or config.render_key(spec, QUALITY, SCENE_DIR, schema.FINISH_KEYS)
    stamp_file = os.path.join(frames_dir, "scene.sha256")
    if os.path.isdir(frames_dir) and (not os.path.exists(stamp_file) or open(stamp_file).read() != key):
        shutil.rmtree(frames_dir)
        log("scene changed since the last render: starting the frames over")
    os.makedirs(frames_dir, exist_ok=True)
    open(stamp_file, "w").write(key)
    for f in glob.glob(os.path.join(frames_dir, "*.png")):
        if os.path.getsize(f) == 0:              # placeholder of a frame that was interrupted
            os.remove(f)
    finished = sorted(glob.glob(os.path.join(frames_dir, "*.png")))
    if finished:                                 # the newest frame may have been cut off by a stop
        os.remove(finished[-1])
    r = scene.render
    if hasattr(r.image_settings, "media_type"):
        r.image_settings.media_type = "IMAGE"
    r.image_settings.file_format = "PNG"
    r.use_overwrite = False
    r.use_placeholder = True
    r.filepath = os.path.join(frames_dir, "")
    total = scene.frame_end - scene.frame_start + 1
    done = len(glob.glob(os.path.join(frames_dir, "*.png")))
    log(f"render: {done}/{total} frames already done")
    bpy.ops.render.render(animation=True)
    # the scene's mix: stereo, 48 kHz, 32-bit float (nothing clips before mastering); kept for finishing
    audio = base + ".wav"
    bpy.ops.sound.mixdown(filepath=audio, container="WAV", codec="PCM", format="F32", channels="STEREO",
                          mixrate=48000)
    level, _ = media.measure_loudness(audio)
    media.run([config.FFMPEG, "-v", "error", "-y", "-framerate", str(FPS), "-start_number", str(scene.frame_start),
               "-i", os.path.join(frames_dir, "%04d.png"), "-i", audio, "-vf", media.to_bt709(),
               *media.video_args(FAST, crf=18 if FAST else 14), "-af", media.gain_filter(level, -16.0, -1.5),
               *media.AUDIO_ARGS, *media.CONTAINER_ARGS, "-shortest", out])
    json.dump(timeline, open(base + ".timeline.json", "w", encoding="utf-8"), indent=1)
    if not args.keep_frames:
        shutil.rmtree(frames_dir)
    log("shot", out)
