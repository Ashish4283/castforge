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
ap.add_argument("--keep-frames", action="store_true", help="keep the rendered PNG frames after the MP4 is made")
ap.add_argument("--quality", help="blocking (default) | draft | standard | final; overrides scene.json")
args = ap.parse_args(argv)

HERE = os.path.dirname(os.path.abspath(__file__))
RHUBARB = os.path.join(HERE, "..", "tools", "Rhubarb-Lip-Sync-1.14.0-Windows", "rhubarb.exe")
SCENE_DIR = os.path.dirname(os.path.abspath(args.scene))
spec = json.load(open(args.scene))
FPS = spec.get("fps", 24)
rand = random.Random(spec.get("seed", 7))


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
        self.footfalls = []              # frames where a foot lands (footstep sounds)
        self.walk_frames = set()         # frames owned by a walk (no idle sway there)
        self.chest_yaw = {}              # frame -> chest counter-rotation while walking
        self.stresses = []               # times (s) of stressed syllables, for nods and brows
        self.seated = None               # the seat (props.SEATS entry) while sitting
        self.driving = []                # (start, end) frames with hands on a steering wheel
        self.thinking = []               # (start_s, end_s) of inner-voice thoughts (head lowers a little)
        self.seated_ranges = []          # [start, end] frames spent sitting (end None = to the end)
        self.sit_torso = Vector((0, 0, 0))
        self.head_yaw = [(1, 0.0)]       # (frame, yaw): head turns used while seated
        self.arm_q = self._relaxed_arms()

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
            self.feet[side] = self.pos + self.rot() @ Vector((sx * 0.12, rest.y, 0))
            self.foot_heading[side] = self.heading

    def stance(self, side, heading=None, centre=None):
        """Where a foot stands when the person stands still at centre facing heading."""
        rest = self.pb[f"foot_ik.{side}"].bone.head_local
        sx = 1 if side == "L" else -1
        return (self.pos if centre is None else centre) + self.rot(heading) @ Vector((sx * 0.12, rest.y, 0))

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
            out[side] = (ua_rest, r_ua, fa_rest, r_fix)
        return out

    def key_arms(self, frame, swing_l=0.0, swing_r=0.0, bend_l=0.0, bend_r=0.0):
        """Arms down and relaxed; swing forward(-)/back(+) at the shoulder, extra elbow bend forward."""
        for side, swing, bend in (("L", swing_l, bend_l), ("R", swing_r, bend_r)):
            ua_rest, r_ua, fa_rest, r_fix = self.arm_q[side]
            r = Matrix.Rotation(swing, 3, "X") @ r_ua
            fa = r.inverted() @ Matrix.Rotation(-bend, 3, "X") @ r_fix @ r     # relative to the upper arm
            for name, rest, rr in ((f"upper_arm_fk.{side}", ua_rest, r), (f"forearm_fk.{side}", fa_rest, fa)):
                p = self.pb[name]
                p.rotation_mode = "QUATERNION"
                p.rotation_quaternion = (rest.inverted() @ rr @ rest).to_quaternion()
                p.keyframe_insert("rotation_quaternion", frame=frame)
            self.key_muscle(f"upper_arm.{side}", max(0.0, bend - 0.12) * 0.7, frame)

    # relaxed hand: fingers curl a little more from index to little finger, thumb rests against them
    FINGER_CURL = {"index": 0.22, "middle": 0.3, "ring": 0.38, "pinky": 0.46}
    SEGMENT = {"01": 0.8, "02": 1.0, "03": 0.7}

    def key_fingers(self, frame, open_l=0.0, open_r=0.0):
        """Relaxed fingers; open_* (0..1) straightens them for an open, gesturing hand."""
        for side, op in (("L", open_l), ("R", open_r)):
            k = 1.0 - 0.75 * op
            for finger, curl in self.FINGER_CURL.items():
                for seg, w in self.SEGMENT.items():
                    p = self.pb.get(f"f_{finger}.{seg}.{side}")
                    if p:
                        p.rotation_mode = "XYZ"
                        p.rotation_euler = (curl * w * k, 0, 0)
                        p.keyframe_insert("rotation_euler", frame=frame)
            for seg, v in (("02", 0.25), ("03", 0.2)):
                p = self.pb.get(f"thumb.{seg}.{side}")
                if p:
                    p.rotation_mode = "XYZ"
                    p.rotation_euler = (v * k, 0, 0)
                    p.keyframe_insert("rotation_euler", frame=frame)

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
        self.key_offset("torso", Vector((sway, 0, -0.015 + bob)), frame)
        self.key_rot("torso", Matrix.Identity(3), frame)
        self.key_arms(frame, swing, -swing, 0.12, 0.12)
        self.key_muscle("thigh.L", 0.0, frame)
        self.key_muscle("thigh.R", 0.0, frame)

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
                                              -0.025 - 0.01 * math.sin(math.pi * u))), f)
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

    def walk(self, target, f0, waypoints=None):
        """Walk to target (world Vector) along waypoints (planned around obstacles), feet planted."""
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
        n_steps = max(2, math.ceil(dist / self.STEP) + 1)
        step_dist = dist / n_steps
        ts = step_dist / self.WALK_SPEED
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
            land = dist if k >= n_steps - 2 else min(dist, step_dist * (k + 1) + 0.35 * self.STEP)
            to_ = at(land)[0] + left_of(tangent(land)) * sx * self.FOOT_GAP
            steps.append((side, last[side], to_))
            last[side] = to_
        planted = {s: self.feet[s].copy() for s in ("L", "R")}
        planted_h = {s: self.foot_heading.get(s, self.heading) for s in ("L", "R")}

        def heading_at(dd):
            v = tangent(min(dist, dd))
            return math.atan2(v.x, -v.y)

        step_h = [heading_at(min(dist, step_dist * (k + 1) + 0.35 * self.STEP))
                  for k in range(n_steps)]
        for k in range(n_steps):
            self.footfalls.append(f0 + int(round(step_times[k + 1] * FPS)))
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
                                              -0.045 + 0.022 * math.sin(math.pi * u) * ramp)), f)
            # lean a little forward; pelvis turns with the swinging leg and drops on the swinging side
            self.key_rot("torso", Matrix.Rotation(0.07 * ramp, 3, "X")
                         @ Matrix.Rotation(0.08 * phase * ramp, 3, "Z")
                         @ Matrix.Rotation(0.035 * sw * math.sin(math.pi * u) * ramp, 3, "Y"), f)
            self.chest_yaw[f] = -0.11 * phase * ramp
            self.walk_frames.add(f)
            # arms swing from the shoulder and the elbow, a bit unevenly, never like a march
            amp = 0.24 * ramp
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


def heading_towards(a, b):
    d = b - a
    return math.atan2(d.x, -d.y)


# --- 3D set from the background image (default): relief mesh + walkable floor map ---------------------
SET = None
if spec.get("set", "3d") == "3d":
    import shutil
    set_dir = os.path.join(SCENE_DIR, "set")
    set_json = os.path.join(set_dir, "set.json")
    bg = path(spec["background"])
    if not os.path.exists(set_json) or os.path.getmtime(set_json) < os.path.getmtime(bg):
        cmd = [shutil.which("python"), os.path.join(HERE, "..", "generate", "depth_set.py"), bg, set_dir]
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
    else:
        raise ValueError(f"unsupported prop file {f}")
    new = [o for o in bpy.data.objects if o not in before]
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
    holder.location = (w_.x, w_.y, base - lowest)
    bpy.context.view_layer.update()
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


for n, prop in enumerate(spec.get("props", [])):
    if prop.get("make") == "picture_road":
        continue
    if "make" in prop:
        root, corners, top = prop_factory.build(prop, n, to_world, prop_tops)
    else:
        root, corners, top = load_prop_file(prop, n)
    if prop.get("picture_rect"):
        corners = None
    prop_tops[prop.get("id", root.name)] = top
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


fit_picture_doors()
entering = {}                      # cast id -> door id, for people whose first move is to enter
for st in spec["script"]:
    if st.get("do") == "enter" and st.get("who") not in entering:
        entering[st["who"]] = st["door"]

cast = {}
for cid, c in spec["cast"].items():
    act = Actor(cid, c["character"])
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
    cast[cid] = act
log("cast", {k: os.path.basename(v["character"]) for k, v in spec["cast"].items()})


# --- lip-sync --------------------------------------------------------------------------------------
RHUBARB_TO_VISEME = {"A": "viseme_PP", "B": "viseme_kk", "C": "viseme_E", "D": "viseme_aa", "E": "viseme_O",
                     "F": "viseme_U", "G": "viseme_FF", "H": "viseme_nn", "X": "viseme_sil"}
# Each speech sound = a lighter MakeHuman viseme + ARKit jaw/lip units. Real talking shows mostly the
# upper front teeth (about 4); the bare visemes drop the lower lip and hide the upper teeth instead.
UP = {"mouthUpperUpLeft": 1, "mouthUpperUpRight": 1}
DOWN = {"mouthLowerDownLeft": 1, "mouthLowerDownRight": 1}
STRETCH = {"mouthStretchLeft": 1, "mouthStretchRight": 1}
PRESS = {"mouthPressLeft": 1, "mouthPressRight": 1}


def pose(viseme, v, jaw=0.0, up=0.0, down=0.0, stretch=0.0, **extra):
    out = {viseme: v, "jawOpen": jaw}
    for group, w in ((UP, up), (DOWN, down), (STRETCH, stretch)):
        for k in group:
            out[k] = w
    out.update(extra)
    return out


MOUTH = {
    "viseme_aa": pose("viseme_aa", 0.4, jaw=0.30, up=0.30, down=0.18),
    "viseme_E": pose("viseme_E", 0.4, jaw=0.15, up=0.30, down=0.12, stretch=0.12),
    "viseme_I": pose("viseme_I", 0.4, jaw=0.10, up=0.28, stretch=0.18),
    "viseme_O": pose("viseme_O", 0.5, jaw=0.24, up=0.12, mouthFunnel=0.40),
    "viseme_U": pose("viseme_U", 0.6, jaw=0.08, mouthPucker=0.50),
    "viseme_PP": dict(pose("viseme_PP", 0.6), mouthClose=0.3, **{k: 0.3 for k in PRESS}),
    "viseme_FF": pose("viseme_FF", 0.6, up=0.22, mouthRollLower=0.30),
    "viseme_TH": pose("viseme_TH", 0.6, jaw=0.08, up=0.15),
    "viseme_DD": pose("viseme_DD", 0.5, jaw=0.10, up=0.22),
    "viseme_nn": pose("viseme_nn", 0.5, jaw=0.08, up=0.18),
    "viseme_kk": pose("viseme_kk", 0.5, jaw=0.12, up=0.20),
    "viseme_SS": pose("viseme_SS", 0.5, jaw=0.05, up=0.25, stretch=0.10),
    "viseme_RR": pose("viseme_RR", 0.5, jaw=0.10, up=0.15, mouthFunnel=0.20),
    "viseme_CH": pose("viseme_CH", 0.5, jaw=0.10, up=0.15, mouthFunnel=0.30),
    "viseme_sil": {},
}
MOUTH_KEYS = sorted({k for p in MOUTH.values() for k in p})


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
        return json.load(open(exact))["cues"]
    if not os.path.exists(RHUBARB):
        raise FileNotFoundError("lip-sync for audio files needs Rhubarb in tools/ (see README)")
    return [{"start": c["start"], "end": c["end"], "viseme": RHUBARB_TO_VISEME[c["value"]],
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
    if step["do"] in ("say", "think") and not step.get("audio"):
        voice = spec["cast"][step["who"]].get("voice")
        if not voice:
            raise ValueError(f"{step['who']} has a text line but no voice in the cast")
        step["audio"] = os.path.join(voice_dir, f"{n:03d}_{step['who']}.wav")
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
    subprocess.run([shutil.which("python"), os.path.join(HERE, "..", "generate", "tts.py"), jobs_file], check=True)
    for j in tts_jobs:
        open(j["stamp"], "w").write(j["src"])
    log(f"voiced {len(tts_jobs)} lines")

# --- script --------------------------------------------------------------------------------------
sounds = []                         # (path, frame, channel)
sfx_events = []                     # (name, frame, volume): one-shot effects from the sfx library
lines = []                          # (start_frame, end_frame, actor) for the automatic close-ups
moves = []                          # (actor, start_frame, end_frame) of walks, for the follow camera


def add_sfx(name, frame, volume=0.8):
    sfx_events.append((name, frame, volume))
cursor, last_start = 2, 2
for step in spec["script"]:
    start = last_start if step.get("with") == "previous" else cursor
    who = cast.get(step.get("who"))
    do = step["do"]
    if do == "walk":
        target = free_near(to_world(step["to"]))
        route = plan(who.pos, target)
        end = who.walk(target, start, route)
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
            add_sfx("door_bell", start + 2)
        add_sfx("door_open", start)
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
        add_sfx("door_close", close_f + int(0.7 * FPS))
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
        add_sfx(step.get("sound", "door_open"), end)
        outside = door["centre"] - door["front"] * 1.0
        end = who.walk(outside, end + int(0.6 * FPS), [door["centre"] + door["front"] * 0.2, door["centre"]])
        who.visible(start, True)
        who.visible(end, False)
        moves.append((who, start, end))
        close_f = end + int(0.3 * FPS)
        for f, ang in ((close_f, -1.75), (close_f + int(0.7 * FPS), 0.0)):
            hinge.rotation_euler = (0, 0, ang)
            hinge.keyframe_insert("rotation_euler", frame=f)
        add_sfx(step.get("close_sound", "door_close"), close_f + int(0.6 * FPS))
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
        add_sfx(step.get("sound", "door_open"), open_f)
        end = release_f + int(0.25 * FPS)
    elif do == "sit":
        seat = SEATS[step["on"]]
        stand_at = seat["centre"] + seat["front"] * 0.5
        approach = free_near(stand_at)
        end = who.walk(stand_at, start, plan(who.pos, approach) + ([approach] if approach != stand_at else []))
        end = who.face(seat["heading"], end)
        end = who.sit(seat, end)
        add_sfx("chair_sit", end - int(0.3 * FPS))
    elif do == "stand":
        end = who.stand(start)
    elif do == "sound":
        add_sfx(step["sfx"], start, step.get("volume", 0.8))
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
        import wave as _wave
        with _wave.open(wav) as w:
            dur = w.getnframes() / w.getframerate()
        lines.append((start, start + int(math.ceil(dur * FPS)), who, "think"))
        who.thinking.append((start / FPS, start / FPS + dur))
        sounds.append((wav, start, 2 + len(sounds) % 4))
        end = start + int(math.ceil((dur + step.get("pause", 0.6)) * FPS))
    elif do == "drive":
        end = start + int(step.get("seconds", 8.0) * FPS)
        who.driving.append((start, end))
    elif do == "say":
        wav = path(step["audio"])
        cues = viseme_cues(wav, step.get("text"))
        key_lipsync(who, cues, start)
        import wave as _wave
        with _wave.open(wav) as w:
            dur = max(cues[-1]["end"], w.getnframes() / w.getframerate())
        who.speaking.append((start / FPS, start / FPS + dur))
        last_s = -1.0
        for c in cues:                       # stressed syllables: clear open vowels, spaced out
            t = start / FPS + c["start"]
            if c["viseme"] in ("viseme_aa", "viseme_E", "viseme_O", "viseme_I") and c.get("weight", 1) >= 1 \
                    and c["end"] - c["start"] > 0.07 and t - last_s > 0.55:
                who.stresses.append(t)
                last_s = t
        lines.append((start, start + int(math.ceil(dur * FPS)), who, "say"))
        sounds.append((wav, start, 2 + len(sounds) % 4))
        end = start + int(math.ceil((dur + step.get("pause", 0.3)) * FPS))
    elif do == "wait":
        end = start + int(step.get("seconds", 1.0) * FPS)
    else:
        raise ValueError(f"unknown action {do}")
    log(f"{step.get('who', '-')}: {do} frames {start}-{end}")
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
    for f in range(1, scene.frame_end + 1, 2):
        t = f / FPS
        g = {"L": 0.0, "R": 0.0}
        for s, side, amp in gestures:
            g[side] = max(g[side], amp * bump((t - s) / 1.0))
        act.key_fingers(f, open_l=g["L"], open_r=g["R"])
        if f not in act.walk_frames:
            seated_now = any(r[0] <= f and (r[1] is None or f < r[1]) for r in act.seated_ranges)
            if any(a0 <= f <= a1 for a0, a1 in act.driving):
                steer = 0.05 * math.sin(2 * math.pi * t / 3.3 + seed) + 0.03 * math.sin(2 * math.pi * t / 1.3)
                act.key_arms(f, -0.85 + steer, -0.85 - steer, 0.75, 0.75)
                act.key_fingers(f, 0.0, 0.0)
            elif seated_now:   # hands on the thighs; a gesture lifts the forearm off the leg
                act.key_arms(f, -0.32 - 0.25 * g["L"], -0.32 - 0.25 * g["R"], 0.62 + 0.6 * g["L"], 0.62 + 0.6 * g["R"])
            else:
                sway = 0.015 * math.sin(2 * math.pi * t / 6.5 + seed)
                act.key_arms(f, sway - 0.35 * g["L"], -sway - 0.35 * g["R"], 0.12 + 0.8 * g["L"], 0.12 + 0.8 * g["R"])
        t = f / FPS
        ch.rotation_euler = (0.012 * math.sin(2 * math.pi * t / 4.2 + seed), 0, act.chest_yaw.get(f, 0.0))
        ch.keyframe_insert("rotation_euler", frame=f)
        talking = any(a <= t <= b for a, b in act.speaking)
        drift = 0.025 if talking else 0.012
        nod = sum(amp * bump((t - s) / dur) for s, amp, dur in nods)
        nod += sum(0.16 * smooth01((t - a0) / 1.2) * smooth01((b0 + 0.8 - t) / 1.2) for a0, b0 in act.thinking)
        yaw = turn_at(act.head_yaw, f)
        ch.rotation_euler = (ch.rotation_euler[0], 0, ch.rotation_euler[2] + 0.3 * yaw)
        ch.keyframe_insert("rotation_euler", frame=f)
        head.rotation_euler = (nod + drift * math.sin(2 * math.pi * t / 3.1 + seed),
                               0.7 * yaw + drift * 1.2 * math.sin(2 * math.pi * t / 4.7 + 2 * seed),
                               drift * 0.6 * math.sin(2 * math.pi * t / 5.9 + seed))
        head.keyframe_insert("rotation_euler", frame=f)
        seated = next((r for r in act.seated_ranges if r[0] <= f and (r[1] is None or f < r[1])), None)
        if seated and f not in act.walk_frames:
            act.key_offset("torso", seated[2] + Vector((0, 0, 0.003 * math.sin(2 * math.pi * t / 4.2 + seed))), f)
        elif not any(abs(f - w) <= 4 for w in (f - 4, f + 4) if w in act.walk_frames) and f not in act.walk_frames:
            # standing: slow weight shift from foot to foot (feet stay planted by IK)
            act.key_offset("torso", Vector((0.011 * math.sin(2 * math.pi * t / 6.5 + seed), 0,
                                            -0.015 - 0.004 * abs(math.sin(2 * math.pi * t / 6.5 + seed)))), f)
        if "browInnerUp" in act.keys:
            v = sum(0.35 * bump((t - s + 0.05) / 0.5) for s in brows)
            for name in ("browInnerUp", "browOuterUpLeft", "browOuterUpRight"):
                if name in act.keys:
                    act.keys[name].value = min(v, 0.5) * (1.0 if name == "browInnerUp" else 0.6)
                    act.keys[name].keyframe_insert("value", frame=f)
    t = rand.uniform(0.5, 2.0)
    while t * FPS < scene.frame_end:
        f = int(t * FPS)
        for name in ("eyeBlinkLeft", "eyeBlinkRight"):
            k = act.keys[name]
            for df, v in ((0, 0.0), (2, 1.0), (4, 0.0)):
                k.value = v
                k.keyframe_insert("value", frame=f + df)
        t += rand.uniform(2.0, 5.0)

# --- set: background image, floor that shows the same image but takes shadows, light, camera -------
bg_img = bpy.data.images.load(path(spec["background"]))


SUN_ENERGY, SUN_ELEV, SUN_AZ = 3.0, math.radians(50), math.radians(-25)
WORLD = 0.35
SUN_ROT = (math.pi / 2 - SUN_ELEV, 0, SUN_AZ)
TO_SUN = -(Euler(SUN_ROT).to_matrix() @ Vector((0, 0, -1)))       # unit vector towards the sun


def image_material(name, receive_shadow, coords="UV"):
    """Shows the background picture as it is (its own lighting), darkened only where a character's
    shadow falls: lit/expected-lit ratio, where expected = sun * max(0, n.L) / pi + world."""
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
        lit.inputs[1].default_value = SUN_ENERGY / math.pi
        lit.inputs[2].default_value = WORLD
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


# shots: the wide camera for movement; with "shots": "auto" (default) each spoken line cuts to a
# medium close-up of the speaker, seen between their facing direction and the main camera
def close_up(actor, n, frame):
    c = bpy.data.objects.new(f"CU_{actor.id}_{n}", bpy.data.cameras.new(f"CU_{actor.id}_{n}"))
    scene.collection.objects.link(c)
    # aim at where the head really is during the line (seated people sit lower)
    scene.frame_set(frame)
    head = actor.rig.matrix_world @ actor.pb["head"].head + Vector((0, 0, 0.06))
    facing = actor.rot() @ Vector((0, -1, 0))
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
    c.data.dof.use_dof = True
    c.data.dof.focus_distance = (head - Vector(c.location)).length
    c.data.dof.aperture_fstop = 1.8
    # frame the speaker on the side opposite their gaze, so they look into the shot
    fwd = (head - c.location).normalized()
    right = fwd.cross(Vector((0, 0, 1))).normalized()
    side = 1 if facing.dot(right) > 0 else -1
    target = head - Vector((0, 0, 0.05)) + right * side * 0.16
    c.rotation_euler = (target - c.location).to_track_quat("-Z", "Y").to_euler()
    return c


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


if spec.get("shots", "auto") != "auto":
    scene.timeline_markers.new("wide", frame=1).camera = cam
else:
    shots = [(1, cam)]
    for n, (f0, f1, actor, kind) in enumerate(lines):
        c = close_up(actor, n, f0 + 2)
        if kind == "think":
            # a slow push-in while we listen to the thought
            head = actor.rig.matrix_world @ actor.pb["head"].head
            start_loc = Vector(c.location)
            c.location = start_loc
            c.keyframe_insert("location", frame=f0)
            c.location = start_loc.lerp(head, 0.25)
            c.keyframe_insert("location", frame=f1 + 8)
            c.data.dof.focus_distance *= 0.87
        shots.append((f0, c))
        nxt = lines[n + 1][0] if n + 1 < len(lines) else None
        if nxt is None or nxt > f1 + FPS:          # a gap after the line: back to the wide shot
            shots.append((f1 + 4, cam))
    if SET and spec.get("shots", "auto") == "auto":
        for n, (actor, f0, f1) in enumerate(moves):
            if f1 - f0 < FPS:                      # very short moves stay on the current shot
                continue
            current = [c for f, c in sorted(shots, key=lambda x: x[0]) if f <= f1 + 12]
            back = current[-1] if current else cam
            shots = [x for x in shots if not (f0 <= x[0] <= f1 + 12)]
            shots += [(f0, follow(actor, f0, f1, n)), (f1 + 12, back if back.name.startswith("CU_") else cam)]
    for n, (f, c) in enumerate(sorted(shots, key=lambda x: x[0])):
        scene.timeline_markers.new(f"shot_{n}", frame=max(f, 1)).camera = c

if spec.get("vehicle"):
    for c in [o for o in scene.objects if o.type == "CAMERA"]:
        if not (c.animation_data and c.animation_data.action):
            c.keyframe_insert("rotation_euler", frame=1)
        for fc in getattr(c.animation_data.action, "fcurves", []):
            if fc.data_path == "rotation_euler":
                m = fc.modifiers.new("NOISE")
                m.scale, m.strength, m.phase = 10.0, 0.012, rand.uniform(0, 50)

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
sun.data.color = (1.0, 0.95, 0.88)
sun.rotation_euler = SUN_ROT
scene.collection.objects.link(sun)
world = bpy.data.worlds.new("World"); scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.95, 0.88, 0.8, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = WORLD

# --- sound -------------------------------------------------------------------------------------------
se = scene.sequence_editor_create()
strips = se.strips if hasattr(se, "strips") else se.sequences
SFX_DIR = os.path.join(HERE, "..", "sfx")


def bed_file(name):
    if os.path.exists(path(name)):
        return path(name)
    lib = json.load(open(os.path.join(SFX_DIR, "library.json"))).get("beds", {})
    if name not in lib:
        raise ValueError(f"no sound file or library bed called {name!r}")
    return os.path.join(SFX_DIR, lib[name][0])


def radio(src):
    """A copy of src that sounds like a small car radio (narrow band, a little compressed)."""
    import shutil as _sh
    out_ = os.path.join(SCENE_DIR, "radio_" + os.path.basename(src))
    if not os.path.exists(out_):
        subprocess.run([_sh.which("ffmpeg"), "-v", "error", "-y", "-i", src, "-af",
                        "highpass=f=280,lowpass=f=4200,acompressor=threshold=0.2:ratio=3,volume=1.3",
                        "-ac", "1", out_], check=True)
    return out_


def lay_bed(name, channel, volume):
    f = 1
    while f < scene.frame_end:
        s = strips.new_sound(f"bed_{channel}", name, channel, f)
        s.volume = volume
        f = s.frame_final_end


if spec.get("ambience"):
    lay_bed(bed_file(spec["ambience"]), 1, spec.get("ambience_volume", 0.5))
music = spec.get("music")
if music:
    m = music if isinstance(music, dict) else {"bed": music}
    src = bed_file(m["bed"])
    lay_bed(radio(src) if m.get("radio") else src, 10, m.get("volume", 0.35))
for wav, frame, ch in sounds:
    strips.new_sound(os.path.basename(wav), wav, ch, frame)

# footsteps: a different recorded step for every landing, on the scene's floor type
SFX = os.path.join(HERE, "..", "sfx")
if os.path.exists(os.path.join(SFX, "library.json")):
    steps_lib = json.load(open(os.path.join(SFX, "library.json")))["footsteps"].get(spec.get("floor", "wood"), [])
    n = 0
    for act in cast.values():
        for f in act.footfalls:
            if steps_lib:
                s = strips.new_sound("step", os.path.join(SFX, rand.choice(steps_lib)), 6 + n % 2, f)
                s.volume = spec.get("footstep_volume", 0.5) * rand.uniform(0.8, 1.0)
                n += 1
    log(f"footsteps: {n} on {spec.get('floor', 'wood')}")
    sfx_lib = json.load(open(os.path.join(SFX, "library.json"))).get("sfx", {})
    used = {}
    for k, (name, frame, vol) in enumerate(sfx_events):
        if sfx_lib.get(name):
            # takes are ranked best-first (generate/rank_sfx.py); repeats rotate so they don't sound copied
            take = sfx_lib[name][used.get(name, 0) % len(sfx_lib[name])]
            used[name] = used.get(name, 0) + 1
            s = strips.new_sound(name, os.path.join(SFX, take), 8 + k % 2, max(frame, 1))
            s.volume = vol
        else:
            log(f"WARNING no '{name}' sound in sfx/library.json (python generate/make_sfx_library.py sfx --oneshots)")

# --- render ------------------------------------------------------------------------------------------
scene.render.engine = "BLENDER_EEVEE"
# quality: blocking (default, ~1 min per minute of film) / draft / standard / final; same animation,
# timing and sound at every level, only the picture changes
QUALITY = args.quality or spec.get("quality", "blocking")
QUALITY_SETTINGS = {           # resolution, samples, cinematic look allowed, full detail
    "blocking": ((480, 270), 1, False, False),
    "draft": ((640, 360), 8, False, False),
    "standard": ((960, 540), 32, True, True),
    "final": (tuple(spec.get("resolution", [1280, 720])), 64, True, True),
}
if QUALITY not in QUALITY_SETTINGS:
    sys.exit(f"CF: FAILED unknown quality {QUALITY!r} (blocking, draft, standard, final)")
(res, samples, allow_look, full_detail) = QUALITY_SETTINGS[QUALITY]
scene.render.resolution_x, scene.render.resolution_y = res
scene.render.resolution_percentage = 100
LOOK = spec.get("look", "cinematic") if allow_look else "plain"
if hasattr(scene, "eevee"):
    scene.eevee.taa_render_samples = samples
if not full_detail:
    # fast: no subdivision smoothing, no ray tracing, no motion blur
    scene.render.use_simplify = True
    scene.render.simplify_subdivision_render = 0
    scene.eevee.use_raytracing = False
    scene.eevee.use_fast_gi = False
    scene.render.use_motion_blur = False
    # depth of field stays on: it is cheap and it hides the rough far edges of a set made from a picture
log(f"quality: {QUALITY} {res[0]}x{res[1]}, {samples} sample(s)")
if LOOK == "cinematic":
    # film-style light on the cast: a big soft key from the camera side, a cool rim from behind (where
    # the windows usually are), ambient tinted with the picture's own colours, ray-traced bounce light
    import numpy as np
    px = np.empty(len(bg_img.pixels), np.float32)
    bg_img.pixels.foreach_get(px)
    mean = px.reshape(-1, 4)[:, :3].mean(axis=0)
    world.node_tree.nodes["Background"].inputs[0].default_value = (*(mean / max(mean.max(), 1e-3)), 1)
    centre = sum((a.pos for a in cast.values()), Vector()) / max(len(cast), 1) + Vector((0, 0, 1.3))
    to_cam = (Vector(cam.location) - centre)
    to_cam.z = 0
    to_cam.normalize()
    side = to_cam.cross(Vector((0, 0, 1)))
    # these lights shape the cast and props only (light linking): the set keeps the picture's own
    # lighting plus the sun's character shadows
    receivers = bpy.data.collections.new("CF_lit_by_key")
    for a in cast.values():
        for o in a.rig.children_recursive:
            if o.type == "MESH":
                receivers.objects.link(o)
    for o in scene.objects:
        if o.parent and o.parent.name in prop_tops and o.type == "MESH":
            receivers.objects.link(o)
    for name, offset, size, energy, colour in (
            ("Key", to_cam * 3.0 + side * 2.0 + Vector((0, 0, 1.2)), 2.5, 170, (1.0, 0.93, 0.85)),
            ("Rim", -to_cam * 3.0 - side * 1.0 + Vector((0, 0, 1.6)), 2.0, 140, (0.85, 0.92, 1.0)),
            ("Fill", to_cam * 3.0 - side * 2.5 + Vector((0, 0, 0.3)), 3.0, 50, (0.95, 0.9, 0.85))):
        light = bpy.data.objects.new(name, bpy.data.lights.new(name, "AREA"))
        light.data.size, light.data.energy, light.data.color = size, energy, colour
        light.location = centre + offset
        light.rotation_euler = (centre - light.location).to_track_quat("-Z", "Y").to_euler()
        scene.collection.objects.link(light)
        light.light_linking.receiver_collection = receivers
    world.node_tree.nodes["Background"].inputs[1].default_value = WORLD * 0.7
    e = scene.eevee
    e.taa_render_samples = 64
    e.use_raytracing = True
    e.use_fast_gi = True
    e.shadow_ray_count, e.shadow_step_count = 2, 8
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 0.5
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
out = os.path.abspath(args.out)
os.makedirs(os.path.dirname(out), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.splitext(out)[0] + ".blend")
log("saved scene", os.path.splitext(out)[0] + ".blend", f"{scene.frame_end} frames")
if args.stills:
    for f in [int(x) for x in args.stills.split(",")]:
        scene.frame_set(f)
        scene.render.filepath = os.path.splitext(out)[0] + f"_f{f:04d}.png"
        bpy.ops.render.render(write_still=True)
    log("stills", args.stills)
else:
    # resumable: every frame is its own PNG; frames already on disk are skipped, so a stopped render
    # continues where it left off. The sound is mixed separately and both are joined by ffmpeg.
    import glob
    import shutil
    base = os.path.splitext(out)[0]
    frames_dir = base + "_frames"
    # frames are only reused for the same scene: a fingerprint of scene.json + the scripts that animate it
    import hashlib
    h = hashlib.sha256(open(args.scene, "rb").read())
    for src in ("scene_kit.py", "props.py"):
        h.update(open(os.path.join(HERE, src), "rb").read())
    h.update(QUALITY.encode())
    stamp_file = os.path.join(frames_dir, "scene.sha256")
    if os.path.isdir(frames_dir) and (not os.path.exists(stamp_file) or open(stamp_file).read() != h.hexdigest()):
        shutil.rmtree(frames_dir)
        log("scene changed since the last render: starting the frames over")
    os.makedirs(frames_dir, exist_ok=True)
    open(stamp_file, "w").write(h.hexdigest())
    for f in glob.glob(os.path.join(frames_dir, "*.png")):
        if os.path.getsize(f) == 0:              # placeholder of a frame that was interrupted
            os.remove(f)
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
    audio = base + "_mix.wav"
    bpy.ops.sound.mixdown(filepath=audio, container="WAV", codec="PCM", format="S16", mixrate=48000)
    ff = shutil.which("ffmpeg")
    if not ff:
        sys.exit("CF: FAILED ffmpeg not found (frames are in " + frames_dir + ")")
    grain = ["-vf", "noise=alls=5:allf=t"] if LOOK == "cinematic" else []
    # loudness: -16 LUFS (speech standard; YouTube plays at about -14)
    subprocess.run([ff, "-v", "error", "-y", "-framerate", str(FPS), "-start_number", str(scene.frame_start),
                    "-i", os.path.join(frames_dir, "%04d.png"), "-i", audio, *grain,
                    "-c:v", "libx264", "-crf", "17", "-preset", "slow", "-pix_fmt", "yuv420p",
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-shortest", out],
                   check=True)
    os.remove(audio)
    if not args.keep_frames:
        shutil.rmtree(frames_dir)
    log("video", out)
