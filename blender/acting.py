"""How CastForge characters act, as plain numbers: mouth shapes for speech, facial expressions, postures,
gestures, hand shapes, walk paces and eye movements. No Blender here: scene_kit.py turns these values into
keyframes, and tests/test_acting.py checks them.

Conventions (CastForge rigs, checked on rendered stills):
  pitch    + leans the chest/torso forward and tips the head down
  yaw      + turns the head to the character's left
  roll     + tilts the head towards the character's right shoulder
  swing    arm at the shoulder: - forward, + back
  raise    arm out to the side (abduction), 0 = hanging
  bend     elbow, 0 = straight
  twist    upper arm about its own axis, + = palm turns forward/up
  shoulder + lifts the shoulder (shrug, tension), - drops it
  open     0 = relaxed hand, 1 = open flat hand; a "hand" shape (point, fist, thumbs) is mixed in by "grip"
"""
import math

# --- speech ------------------------------------------------------------------------------------------
RHUBARB_TO_VISEME = {"A": "viseme_PP", "B": "viseme_kk", "C": "viseme_E", "D": "viseme_aa", "E": "viseme_O",
                     "F": "viseme_U", "G": "viseme_FF", "H": "viseme_nn", "X": "viseme_sil"}
# Each speech sound = a lighter MakeHuman viseme + ARKit jaw/lip units. Real talking shows mostly the
# upper front teeth (about 4); the bare visemes drop the lower lip and hide the upper teeth instead.
UP = ("mouthUpperUpLeft", "mouthUpperUpRight")
DOWN = ("mouthLowerDownLeft", "mouthLowerDownRight")
STRETCH = ("mouthStretchLeft", "mouthStretchRight")
PRESS = ("mouthPressLeft", "mouthPressRight")


def mouth_pose(viseme, v, jaw=0.0, up=0.0, down=0.0, stretch=0.0, **extra):
    out = {viseme: v, "jawOpen": jaw}
    for group, w in ((UP, up), (DOWN, down), (STRETCH, stretch)):
        for k in group:
            out[k] = w
    out.update(extra)
    return out


MOUTH = {
    "viseme_aa": mouth_pose("viseme_aa", 0.4, jaw=0.30, up=0.30, down=0.18),
    "viseme_E": mouth_pose("viseme_E", 0.4, jaw=0.15, up=0.30, down=0.12, stretch=0.12),
    "viseme_I": mouth_pose("viseme_I", 0.4, jaw=0.10, up=0.28, stretch=0.18),
    "viseme_O": mouth_pose("viseme_O", 0.5, jaw=0.24, up=0.12, mouthFunnel=0.40),
    "viseme_U": mouth_pose("viseme_U", 0.6, jaw=0.08, mouthPucker=0.50),
    "viseme_PP": dict(mouth_pose("viseme_PP", 0.6), mouthClose=0.3, **{k: 0.3 for k in PRESS}),
    "viseme_FF": mouth_pose("viseme_FF", 0.6, up=0.22, mouthRollLower=0.30),
    "viseme_TH": mouth_pose("viseme_TH", 0.6, jaw=0.08, up=0.15),
    "viseme_DD": mouth_pose("viseme_DD", 0.5, jaw=0.10, up=0.22),
    "viseme_nn": mouth_pose("viseme_nn", 0.5, jaw=0.08, up=0.18),
    "viseme_kk": mouth_pose("viseme_kk", 0.5, jaw=0.12, up=0.20),
    "viseme_SS": mouth_pose("viseme_SS", 0.5, jaw=0.05, up=0.25, stretch=0.10),
    "viseme_RR": mouth_pose("viseme_RR", 0.5, jaw=0.10, up=0.15, mouthFunnel=0.20),
    "viseme_CH": mouth_pose("viseme_CH", 0.5, jaw=0.10, up=0.15, mouthFunnel=0.30),
    "viseme_sil": {},
}
MOUTH_KEYS = sorted({k for p in MOUTH.values() for k in p})
STRESSED = ("viseme_aa", "viseme_E", "viseme_O", "viseme_I")       # open vowels: where nods and brows land


# --- faces ----------------------------------------------------------------------------------------------
def _sym(**kw):
    """browDown=0.5 -> browDownLeft and browDownRight at 0.5."""
    return {f"{k}{side}": v for k, v in kw.items() for side in ("Left", "Right")}


# ARKit face shapes only; never a shape lip-sync drives (MOUTH_KEYS), so speech and emotion add up.
# "eyelids" is not a shape: it lowers the upper lids (merged with blinks by taking the larger value).
EXPRESSIONS = {
    "neutral": {},
    "smile": _sym(mouthSmile=0.38, cheekSquint=0.18, eyeSquint=0.08),
    "happy": {**_sym(mouthSmile=0.62, cheekSquint=0.40, eyeSquint=0.22, mouthDimple=0.15), "browInnerUp": 0.12},
    "sad": {**_sym(mouthFrown=0.50, browDown=0.10, eyeSquint=0.10), "browInnerUp": 0.65, "mouthShrugLower": 0.25},
    "angry": {**_sym(browDown=0.75, noseSneer=0.35, eyeSquint=0.35, mouthFrown=0.20), "jawForward": 0.12},
    "surprised": {**_sym(browOuterUp=0.70, eyeWide=0.60), "browInnerUp": 0.80},
    "scared": {**_sym(browOuterUp=0.35, eyeWide=0.75, mouthFrown=0.25), "browInnerUp": 0.85},
    "disgusted": {**_sym(noseSneer=0.60, browDown=0.35, cheekSquint=0.30, mouthFrown=0.15), "mouthShrugUpper": 0.35},
    "worried": {**_sym(mouthFrown=0.22, eyeSquint=0.06), "browInnerUp": 0.55},
    "thinking": {"browDownLeft": 0.30, "browOuterUpRight": 0.35, "eyeSquintLeft": 0.15, "mouthLeft": 0.15,
                 "mouthShrugUpper": 0.10},
    "skeptical": {"browOuterUpLeft": 0.55, "browDownRight": 0.40, "eyeSquintRight": 0.25, "mouthSmileLeft": 0.10,
                  "mouthLeft": 0.10},
    "determined": {**_sym(browDown=0.45, eyeSquint=0.20), "jawForward": 0.08, "mouthShrugLower": 0.20},
    "tired": {**_sym(eyeSquint=0.15), "browInnerUp": 0.15, "eyelids": 0.38},
    "smug": {"mouthSmileLeft": 0.45, "mouthSmileRight": 0.12, "browOuterUpLeft": 0.25, "eyeSquintRight": 0.20,
             "eyeSquintLeft": 0.10},
}
# how an emotion carries into the body: chest/head pitch and shoulder lift (added to the posture)
EXPRESSION_BODY = {
    "happy": {"head": -0.03}, "sad": {"chest": 0.06, "head": 0.10}, "angry": {"chest": -0.02, "head": 0.05},
    "surprised": {"chest": -0.02, "head": -0.06}, "scared": {"head": 0.03, "shoulders": 0.40},
    "worried": {"head": 0.04, "shoulders": 0.15}, "thinking": {"head": 0.03}, "determined": {"chest": -0.03},
    "tired": {"chest": 0.05, "head": 0.07}, "smug": {"head": -0.04},
}
# strong feelings: the director moves in closer on these lines
STRONG = {"sad", "angry", "surprised", "scared", "disgusted", "worried", "determined"}

POSTURES = {
    "neutral": {},
    "confident": {"chest": -0.06, "head": -0.03, "shoulders": -0.25, "stance": 1.25},
    "proud": {"chest": -0.10, "head": -0.07, "shoulders": -0.30, "stance": 1.20},
    "relaxed": {"chest": 0.03, "head": 0.02, "shoulders": -0.10, "stance": 1.10},
    "slumped": {"chest": 0.16, "head": 0.14, "shoulders": 0.10, "stance": 0.90},
    "tense": {"chest": 0.02, "head": 0.03, "shoulders": 0.55, "stance": 1.00},
    "tired": {"chest": 0.10, "head": 0.10, "shoulders": 0.05, "stance": 0.95},
}
BODY_CHANNELS = ("chest", "head", "shoulders", "stance")


def mix(a, b, w):
    """a*(1-w) + b*w for two {name: value} dicts (a missing name counts as 0; "stance" as 1)."""
    out = {}
    for k in set(a) | set(b):
        rest = 1.0 if k == "stance" else 0.0
        out[k] = a.get(k, rest) * (1 - w) + b.get(k, rest) * w
    return out


def scaled(preset, intensity):
    return {k: v * intensity for k, v in preset.items()}


# --- easing ------------------------------------------------------------------------------------------------
def smooth01(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def window(t, t0, t1, fade):
    """0 outside [t0, t1], 1 inside, eased over `fade` seconds at both ends."""
    if t <= t0 or t >= t1:
        return 0.0
    fade = max(min(fade, (t1 - t0) / 2), 1e-6)
    return smooth01((t - t0) / fade) * smooth01((t1 - t) / fade)


class Layer:
    """A value that changes over time: a baseline that blends to each new setting, plus temporary overlays
    (a line said angrily, a three-second smile) that fade in and out on top of it. Values are dicts."""

    def __init__(self, value=None, blend=0.35):
        self.keys = [(-1e9, dict(value or {}))]      # (time, value) baseline changes
        self.overlays = []                            # (t0, t1, value)
        self.blend = blend

    def set(self, t, value):
        self.keys.append((t, dict(value)))
        self.keys.sort(key=lambda k: k[0])

    def overlay(self, t0, t1, value):
        self.overlays.append((t0, t1, dict(value)))

    def base(self, t):
        # each change blends from wherever the previous blend had got to, so quick changes never jump
        start, t_start, target = self.keys[0][1], self.keys[0][0], self.keys[0][1]
        for tk, vk in self.keys[1:]:
            if tk > t:
                break
            start = mix(start, target, smooth01((tk - t_start) / self.blend))
            t_start, target = tk, vk
        return mix(start, target, smooth01((t - t_start) / self.blend))

    def at(self, t):
        v = self.base(t)
        for t0, t1, ov in self.overlays:
            w = window(t, t0, t1, self.blend)
            if w > 0:
                v = mix(v, ov, w)
        return v


# --- hands -------------------------------------------------------------------------------------------------
# relaxed hand: fingers curl a little more from index to little finger, thumb rests against them
FINGER_CURL = {"index": 0.22, "middle": 0.30, "ring": 0.38, "pinky": 0.46}
SEGMENT = {"01": 0.8, "02": 1.0, "03": 0.7}
THUMB = {"02": 0.25, "03": 0.20}
HAND_SHAPES = {     # per-finger curl (radians at the middle segment) and thumb factor
    "point": ({"index": 0.02, "middle": 1.35, "ring": 1.40, "pinky": 1.45}, 0.6),
    "fist": ({"index": 1.35, "middle": 1.40, "ring": 1.45, "pinky": 1.50}, 1.6),
    "thumbs": ({"index": 1.35, "middle": 1.40, "ring": 1.45, "pinky": 1.50}, 0.0),
}


def finger_curls(open_=0.0, shape=None, grip=0.0):
    """{finger: curl} and the thumb factor for a hand: relaxed -> open by `open_`, then towards a named shape
    by `grip` (0..1)."""
    k = 1.0 - 0.75 * open_
    curls = {f: c * k for f, c in FINGER_CURL.items()}
    thumb = k
    if shape in HAND_SHAPES and grip > 0:
        target, t_thumb = HAND_SHAPES[shape]
        curls = {f: c * (1 - grip) + target[f] * grip for f, c in curls.items()}
        thumb = thumb * (1 - grip) + t_thumb * grip
    return curls, thumb


# --- gestures ----------------------------------------------------------------------------------------------
# Each gesture: seconds (default length), hands ("one", "both" or "none") and pose(u, t, p) -> what it moves:
#   {"arm": {...arm channels for the gesturing hand(s)}, "head": {"pitch", "yaw", "roll"}, "chest": pitch,
#    "torso": pitch, "shoulders": lift}
# u runs 0..1 over the gesture, t is seconds since it started, p holds options (e.g. "azimuth" for point).
# Arm channels are targets (the idle arm blends towards them); head/chest/torso/shoulders are added.
def _wave(u, t, p):
    return {"arm": {"swing": -0.20, "raise": 1.30, "twist": 1.20, "bend": 1.50 + 0.25 * math.sin(2 * math.pi * 2.2 * t),
                    "open": 1.0}, "head": {"pitch": -0.03}}


def _raise_hand(u, t, p):
    return {"arm": {"swing": -2.75, "raise": 0.20, "bend": 0.15, "twist": 0.30, "open": 1.0}, "head": {"pitch": -0.05}}


def _point(u, t, p):
    a = min(max(p.get("azimuth", 0.0), 0.0), 1.4)      # 0 = ahead, + = out towards the pointing arm's side
    return {"arm": {"swing": -1.30 * math.cos(a), "raise": 1.30 * math.sin(a) + 0.10, "bend": 0.08, "twist": 0.0,
                    "hand": "point", "grip": 1.0}}


def _shrug(u, t, p):
    return {"arm": {"swing": -0.35, "raise": 0.35, "bend": 1.35, "twist": -0.90, "open": 1.0},
            "shoulders": 0.55, "head": {"roll": 0.10, "pitch": -0.04}}


def _nod(u, t, p):
    return {"head": {"pitch": 0.16 * math.sin(math.pi * 2 * u) ** 2}}


def _shake_head(u, t, p):
    return {"head": {"yaw": 0.30 * math.sin(2 * math.pi * 1.5 * u)}}


def _hands_on_hips(u, t, p):
    return {"arm": {"swing": 0.30, "raise": 0.80, "bend": 2.00, "twist": 0.70, "hand": "fist", "grip": 0.4},
            "shoulders": -0.10, "chest": -0.03}


def _beckon(u, t, p):
    return {"arm": {"swing": -0.85, "raise": 0.25, "bend": 1.40, "twist": 1.30,
                    "open": 0.5 + 0.5 * math.cos(2 * math.pi * 2.2 * t)}}


def _bow(u, t, p):
    return {"torso": 0.40, "head": {"pitch": 0.20}}


def _look_around(u, t, p):
    return {"head": {"yaw": 0.65 * math.sin(2 * math.pi * u)}}


def _thumbs_up(u, t, p):
    return {"arm": {"swing": -0.80, "raise": 0.20, "bend": 1.45, "twist": 1.40, "hand": "thumbs", "grip": 1.0}}


def _cheer(u, t, p):
    return {"arm": {"swing": -2.55, "raise": 0.55, "bend": 0.30 + 0.25 * math.sin(2 * math.pi * 2.0 * t),
                    "hand": "fist", "grip": 1.0}, "head": {"pitch": -0.08}, "chest": -0.04}


GESTURES = {
    "wave": (2.0, "one", _wave),
    "raise_hand": (2.0, "one", _raise_hand),
    "point": (1.8, "one", _point),
    "shrug": (1.3, "both", _shrug),
    "nod": (1.0, "none", _nod),
    "shake_head": (1.2, "none", _shake_head),
    "hands_on_hips": (3.0, "both", _hands_on_hips),
    "beckon": (1.8, "one", _beckon),
    "bow": (1.6, "none", _bow),
    "look_around": (2.6, "none", _look_around),
    "thumbs_up": (1.8, "one", _thumbs_up),
    "cheer": (1.6, "both", _cheer),
}


def gesture_weight(t, seconds):
    """How much of the gesture shows t seconds in: eases in and out over a quarter (at most 0.45 s) each."""
    return window(t, 0.0, seconds, min(0.45, 0.25 * seconds))


# overlapping action: energy travels down the arm, so the elbow and then the hand start a little later than the
# shoulder, pass their mark and settle (a damped spring), instead of every joint stopping on the same frame
ELBOW_LAG, HAND_LAG, OVERSHOOT, SETTLE = 0.08, 0.14, 0.10, 0.4


def whip(t, seconds, lag, overshoot=OVERSHOOT):
    """Weight of a joint further down the arm: the gesture weight `lag` seconds late, with a damped overshoot
    after it arrives and after it lets go. Runs until seconds + lag + SETTLE."""
    w = gesture_weight(t - lag, seconds)
    fade = min(0.45, 0.25 * seconds)
    for edge, sign in ((lag + fade, 1.0), (lag + seconds, -1.0)):
        dt = t - edge
        if dt > 0:
            w += sign * overshoot * math.exp(-dt / 0.1) * math.sin(math.pi * dt / 0.15)
    return w


def asymmetric(weights, tilt):
    """A face is never mirror-perfect: Left shapes a little stronger, Right a little weaker (tilt ~ 0.05..0.1)."""
    return {k: v * (1 + tilt) if k.endswith("Left") else v * (1 - tilt) if k.endswith("Right") else v
            for k, v in weights.items()}


# --- walking -----------------------------------------------------------------------------------------------
# pace: speed (m/s), step length (m), arm swing scale, extra forward lean (rad)
PACES = {"stroll": (0.8, 0.55, 0.7, 0.0), "normal": (1.1, 0.62, 1.0, 0.0),
         "brisk": (1.4, 0.70, 1.2, 0.02), "hurry": (1.7, 0.78, 1.4, 0.05)}


# --- eyes --------------------------------------------------------------------------------------------------
EYE_YAW, EYE_PITCH = 0.6, 0.4                 # how far eyes turn before the head has to


def bearing(eye, heading, target):
    """(yaw, up) from `eye` (x, y, z) to `target` for a body facing `heading` (0 = the camera, -Y; + turns
    left): yaw + = to the character's left, up + = above eye level. Not clamped."""
    dx, dy, dz = target[0] - eye[0], target[1] - eye[1], target[2] - eye[2]
    world_yaw = math.atan2(dx, -dy)              # same convention as scene_kit headings
    yaw = (world_yaw - heading + math.pi) % (2 * math.pi) - math.pi
    return yaw, math.atan2(dz, math.hypot(dx, dy))


def gaze_angles(eye, heading, head_yaw, target):
    """Eye (yaw, up) relative to a head turned by head_yaw, looking at `target`; clamped to what eyes can do."""
    yaw, up = bearing(eye, heading + head_yaw, target)
    return max(-EYE_YAW, min(EYE_YAW, yaw)), max(-EYE_PITCH, min(EYE_PITCH, up))


def saccades(rng, t0, t1, every=(0.6, 2.0), size=0.05):
    """Small, quick eye jumps while looking at something: [(time, dyaw, dpitch)]."""
    out, t = [], t0 + rng.uniform(*every) / 2
    while t < t1:
        out.append((t, rng.uniform(-size, size), rng.uniform(-size, size) * 0.6))
        t += rng.uniform(*every)
    return out
