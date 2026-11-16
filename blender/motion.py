"""Motion clips (motion capture from Mixamo or CMU) as plain numbers: which source bone drives which CastForge
control, and where a clip's body starts, faces and ends on the floor. No Blender here: import_motion.py records a
clip, motion_rig.py plays it on a character, tests/test_motion.py checks the maths.

A clip is two files in motions/clips: <name>.blend (the source skeleton and its action, as imported) and
<name>.json: {"name", "source", "file", "fps", "frames": [first, last], "seconds", "bones": {part: bone name},
"hip_height", "track": {"fps", "hips": [[x, y, z]], "facing": [radians], "feet": {"L": [[x, y, z, yaw]], "R": ...},
"floor": [z]}}. Track positions are in the imported skeleton's world, in its own units (hip_height gives the scale).

Headings: 0 faces -Y (CastForge's front), + turns left (counter-clockwise seen from above).
"""
import glob
import json
import math
import os

# the body parts a clip drives, and the CastForge (Rigify) control each one moves
CONTROLS = {"hips": "torso", "chest": "chest", "neck": "neck", "head": "head"}
for _s in ("L", "R"):
    CONTROLS.update({f"shoulder.{_s}": f"shoulder.{_s}", f"upper_arm.{_s}": f"upper_arm_fk.{_s}",
                     f"forearm.{_s}": f"forearm_fk.{_s}", f"hand.{_s}": f"hand_fk.{_s}",
                     f"thigh.{_s}": f"thigh_fk.{_s}", f"shin.{_s}": f"shin_fk.{_s}", f"foot.{_s}": f"foot_fk.{_s}",
                     f"toe.{_s}": f"toe_fk.{_s}"})
# the trunk only turns with the body's facing; a limb part is also swung so it points along the clip's bone
UPRIGHT = {"hips", "chest", "neck", "head"}
_NEXT = {"shoulder": "upper_arm", "upper_arm": "forearm", "forearm": "hand", "thigh": "shin", "shin": "foot",
         "foot": "toe"}

# source skeletons: part -> bone name (a namespace such as "mixamorig:" is ignored). CMU = the cgspeed BVH release.
_LIMBS = {}
for _s, _w in (("L", "Left"), ("R", "Right")):
    _LIMBS.update({f"shoulder.{_s}": f"{_w}Shoulder", f"upper_arm.{_s}": f"{_w}Arm",
                   f"forearm.{_s}": f"{_w}ForeArm", f"hand.{_s}": f"{_w}Hand", f"thigh.{_s}": f"{_w}UpLeg",
                   f"shin.{_s}": f"{_w}Leg", f"foot.{_s}": f"{_w}Foot", f"toe.{_s}": f"{_w}ToeBase"})
SKELETONS = {
    "mixamo": {"hips": "Hips", "chest": "Spine2", "neck": "Neck", "head": "Head", **_LIMBS},
    "cmu": {"hips": "Hips", "chest": "Spine1", "neck": "Neck", "head": "Head", **_LIMBS},
}
TRACK_FPS = 30


def next_part(part):
    """The joint a limb part points at (upper_arm.L -> forearm.L); None for the trunk, hands and toes."""
    name, _, side = part.partition(".")
    return f"{_NEXT[name]}.{side}" if name in _NEXT else None


def bone_map(names):
    """Which skeleton a file uses, and {part: bone name as in the file}. Raises ValueError naming what is
    missing when it is neither a Mixamo nor a CMU skeleton."""
    bare = {n.rsplit(":", 1)[-1]: n for n in names}
    best = None
    for kind, parts in SKELETONS.items():
        missing = [b for b in parts.values() if b not in bare]
        if best is None or len(missing) < len(best[2]):
            best = (kind, parts, missing)
    kind, parts, missing = best
    if missing:
        raise ValueError(f"not a Mixamo or CMU skeleton (no bone {', '.join(missing[:6])})")
    return kind, {part: bare[b] for part, b in parts.items()}


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def heading_of(dx, dy):
    """The heading of a direction on the floor."""
    return math.atan2(dx, -dy)


def facing_of(left, right):
    """Which way a body faces, from its left and right hip joints [x, y, ...] (forward = lateral x up)."""
    return math.atan2(left[1] - right[1], left[0] - right[0])


def window(meta, start=0.0, end=None):
    """The part of a clip to play, in seconds from its first frame, kept inside the clip."""
    length = meta["seconds"]
    end = length if end is None else max(0.0, min(float(end), length))
    return max(0.0, min(float(start), end)), end


def sample(track, t):
    """The track entry nearest to clip time t (seconds)."""
    return max(0, min(len(track["hips"]) - 1, int(round(t * track["fps"]))))


def floor(meta):
    """Floor height under the clip: the lowest toes, ignoring the lowest 2 % (capture glitches)."""
    zs = sorted(meta["track"]["floor"])
    return zs[len(zs) // 50]


def scene_frames(t0, t1, fps, speed=1.0):
    """How many scene frames a clip window lasts at a speed (at least 2)."""
    return max(2, int(round((t1 - t0) / max(speed, 0.05) * fps)))


def clip_to_scene(frame, meta, t0, start, fps, speed=1.0):
    """The scene frame where a clip's own frame plays, when clip time t0 plays at scene frame `start`."""
    return start + ((frame - meta["frames"][0]) / meta["fps"] - t0) * fps / max(speed, 0.05)


def fades(start, end, blend):
    """(frame, weight) keys that blend a clip in at start and out at end; short clips get shorter blends."""
    b = max(1, min(int(blend), (end - start) // 2))
    return [(start, 0.0), (start + b, 1.0), (end - b, 1.0), (end, 0.0)]


# --- foot planting -------------------------------------------------------------------------------------
def stance_windows(meta, side, t0, t1, min_samples=4):
    """When the clip's foot is planted between t0 and t1: [(ta, tb, (x, y))] in the clip's own units.
    Planted means near the floor and nearly still; the anchor is the mean position of the middle of the
    stay, so heel-strike and push-off wobble do not move it."""
    track, hip = meta["track"], meta["hip_height"]
    feet, fps, floor_z = track["feet"][side], track["fps"], floor(meta)
    i0, i1 = sample(track, t0), sample(track, t1)
    runs, run = [], []
    for i in range(i0, i1 + 1):
        x, y, z = feet[i][:3]
        speed = 0.0
        if i > i0:
            px, py = feet[i - 1][:2]
            speed = math.hypot(x - px, y - py) * fps
        if (z - floor_z) < 0.09 * hip and speed < 0.6 * hip:
            run.append(i)
        elif run:
            runs.append(run)
            run = []
    if run:
        runs.append(run)
    out = []
    for run in runs:
        if len(run) < min_samples:
            continue
        mid = run[len(run) // 4: len(run) - len(run) // 4] or run
        ax = sum(feet[i][0] for i in mid) / len(mid)
        ay = sum(feet[i][1] for i in mid) / len(mid)
        out.append(((run[0] - i0) / fps, (run[-1] - i0) / fps, (ax, ay)))
    return out


def ending(meta, t0, t1):
    """What a clip window does to the body, in the body's own frame at t0 (it faces -Y there) and in hip
    heights: the hips' move (dx, dy), the turn (radians), and each foot's (x, y, heading) at t1."""
    tr, h = meta["track"], meta["hip_height"]
    a, b = sample(tr, t0), sample(tr, t1)
    f0 = tr["facing"][a]
    c, s = math.cos(-f0), math.sin(-f0)

    def local(p):
        x, y = p[0] - tr["hips"][a][0], p[1] - tr["hips"][a][1]
        return (c * x - s * y) / h, (s * x + c * y) / h

    feet = {side: (*local(tr["feet"][side][b]), wrap(tr["feet"][side][b][3] - f0)) for side in ("L", "R")}
    return local(tr["hips"][b]), wrap(tr["facing"][b] - f0), feet


def to_world(pos, heading, size, local):
    """A point in a body frame (see ending) for a character at pos [x, y] facing heading, `size` metres per hip
    height."""
    x, y = local[0] * size, local[1] * size
    c, s = math.cos(heading), math.sin(heading)
    return pos[0] + c * x - s * y, pos[1] + s * x + c * y


# --- the library ---------------------------------------------------------------------------------------------
def names(folder):
    """Clip names in a motion folder."""
    return sorted(os.path.basename(f)[:-5] for f in glob.glob(os.path.join(folder, "*.json")))


def load(folder, name):
    """A clip's metadata (with "blend", its skeleton file), or None when there is no such clip."""
    f = os.path.join(folder, name + ".json")
    if not os.path.isfile(f):
        return None
    meta = json.load(open(f, encoding="utf-8"))
    meta["blend"] = os.path.join(folder, name + ".blend")
    return meta
