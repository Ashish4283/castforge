"""The scene vocabulary: every action, parameter, preset and asset name CastForge understands, in one place.

`castforge.py check` validates scene.json with it, the web app builds its forms from it (/api/schema), the prop
factory takes sizes and materials from it, and tests check the Gemini prompt and the presets against it.
Plain Python, importable from Blender too.
"""
import json
import math
import os
import re

from blender import acting, motion, tailor
from core import appearance, config, finish, media, sets

# --- names ------------------------------------------------------------------------------------------------
_LANG = {"a": "American English", "b": "British English", "h": "Hindi", "e": "Spanish", "f": "French",
         "i": "Italian", "p": "Portuguese (Brazil)"}
_SHORT = {"a": "US", "b": "UK", "h": "HI", "e": "ES", "f": "FR", "i": "IT", "p": "BR"}
VOICES = {v: f"{_LANG[v[0]]}, {'female' if v[1] == 'f' else 'male'}" for v in """
    af_heart af_alloy af_aoede af_bella af_jessica af_kore af_nicole af_nova af_river af_sarah af_sky
    am_adam am_echo am_eric am_fenrir am_liam am_michael am_onyx am_puck am_santa
    bf_alice bf_emma bf_isabella bf_lily bm_daniel bm_fable bm_george bm_lewis
    hf_alpha hf_beta hm_omega hm_psi ef_dora em_alex em_santa ff_siwis if_sara im_nicola pf_dora pm_alex pm_santa
    """.split()}
# The same names taken apart, so the app can show 54 voices as a gallery you filter and listen to instead of
# a drop-down of codes. Nobody should have to know that "bf" means a British woman.
VOICE_FACTS = {v: {"language": _LANG[v[0]], "short": _SHORT[v[0]],
                   "gender": "female" if v[1] == "f" else "male", "person": v[3:]}
               for v in VOICES}
FLOORS = ["wood", "concrete", "carpet", "tile", "snow"]
EXPRESSIONS = list(acting.EXPRESSIONS)
GESTURES = list(acting.GESTURES)
POSTURES = list(acting.POSTURES)
PACES = list(acting.PACES)
VOICE_FX = list(media.VOICE_FX)
GRADES = list(finish.GRADES)
TRANSITIONS = list(finish.TRANSITIONS)
SHOT_KINDS = ["wide", "medium", "close", "two_shot", "over_shoulder", "auto"]
CAMERA_MOVES = ["static", "push_in", "pull_out", "pan_left", "pan_right", "handheld"]
SHOTS_MODES = ["auto", "classic", "none"]
SUBTITLES = ["soft", "burn", "off"]
QUALITIES = list(config.QUALITY)
ASPECTS = list(config.ASPECTS)
LOOK_DIRECTIONS = ["left", "right", "up", "down"]

# lighting moods: key/fill/rim (strength factor, colour), world strength factor and tint, sun (strength,
# colour). "auto" = v1's colours scaled to the picture's brightness; "classic" = v1's fixed light.
LIGHTING = {
    "auto": None,
    "classic": None,
    "day": dict(key=(1.0, (1.0, 0.95, 0.88)), fill=(1.0, (0.92, 0.95, 1.0)), rim=(0.9, (1.0, 0.97, 0.92)),
                world=(1.0, (1.0, 1.0, 1.0)), sun=(3.0, (1.0, 0.95, 0.88))),
    "golden_hour": dict(key=(1.0, (1.0, 0.78, 0.52)), fill=(0.7, (0.75, 0.82, 1.0)), rim=(1.3, (1.0, 0.7, 0.4)),
                        world=(0.9, (1.0, 0.85, 0.7)), sun=(3.5, (1.0, 0.72, 0.45))),
    "overcast": dict(key=(0.7, (0.95, 0.97, 1.0)), fill=(1.2, (0.95, 0.97, 1.0)), rim=(0.5, (0.95, 0.97, 1.0)),
                     world=(1.3, (0.92, 0.95, 1.0)), sun=(1.2, (0.95, 0.97, 1.0))),
    "night": dict(key=(0.45, (0.75, 0.82, 1.0)), fill=(0.3, (0.6, 0.7, 1.0)), rim=(0.8, (0.55, 0.7, 1.0)),
                  world=(0.45, (0.6, 0.7, 1.0)), sun=(0.6, (0.6, 0.72, 1.0))),
    "interior_warm": dict(key=(0.85, (1.0, 0.82, 0.62)), fill=(0.6, (1.0, 0.88, 0.75)), rim=(0.7, (1.0, 0.85, 0.7)),
                          world=(0.8, (1.0, 0.88, 0.75)), sun=(1.5, (1.0, 0.85, 0.65))),
    "interior_cool": dict(key=(0.85, (0.9, 0.95, 1.0)), fill=(0.7, (0.88, 0.93, 1.0)), rim=(0.7, (0.85, 0.92, 1.0)),
                          world=(0.9, (0.9, 0.95, 1.0)), sun=(1.5, (0.9, 0.95, 1.0))),
    "candlelight": dict(key=(0.55, (1.0, 0.62, 0.32)), fill=(0.2, (1.0, 0.7, 0.45)), rim=(0.4, (1.0, 0.6, 0.3)),
                        world=(0.35, (1.0, 0.75, 0.5)), sun=(0.5, (1.0, 0.65, 0.35))),
    "moonlight": dict(key=(0.35, (0.65, 0.75, 1.0)), fill=(0.15, (0.5, 0.6, 1.0)), rim=(1.0, (0.7, 0.8, 1.0)),
                      world=(0.35, (0.55, 0.65, 1.0)), sun=(0.8, (0.6, 0.7, 1.0))),
    "noir": dict(key=(1.1, (1.0, 1.0, 1.0)), fill=(0.1, (1.0, 1.0, 1.0)), rim=(1.4, (1.0, 1.0, 1.0)),
                 world=(0.4, (1.0, 1.0, 1.0)), sun=(2.0, (1.0, 1.0, 1.0))),
    "studio": dict(key=(1.2, (1.0, 1.0, 1.0)), fill=(1.0, (1.0, 1.0, 1.0)), rim=(1.2, (1.0, 1.0, 1.0)),
                   world=(1.0, (1.0, 1.0, 1.0)), sun=(2.5, (1.0, 1.0, 1.0))),
}
WEATHER = ["snow", "rain"]

# --- props --------------------------------------------------------------------------------------------------
# rendering of each material: roughness, metallic, transmission, sheen, coat
MATERIALS = {
    "wood": (0.55, 0.0, 0.0, 0.0, 0.1), "metal": (0.30, 1.0, 0.0, 0.0, 0.0), "fabric": (0.90, 0.0, 0.0, 0.6, 0.0),
    "leather": (0.45, 0.0, 0.0, 0.0, 0.3), "glass": (0.05, 0.0, 1.0, 0.0, 0.0), "plastic": (0.35, 0.0, 0.0, 0.0, 0.2),
    "ceramic": (0.20, 0.0, 0.0, 0.0, 0.6), "stone": (0.75, 0.0, 0.0, 0.0, 0.0), "paper": (0.80, 0.0, 0.0, 0.2, 0.0),
    "wax": (0.40, 0.0, 0.0, 0.3, 0.2), "snow": (0.85, 0.0, 0.0, 0.4, 0.0), "brass": (0.25, 1.0, 0.0, 0.0, 0.0),
    "rubber": (0.86, 0.0, 0.0, 0.0, 0.0), "brass": (0.25, 1.0, 0.0, 0.0, 0.0),
}
# type: (width, depth, height) in metres, default material, stands on the floor and blocks walking, what it is
PROP_TYPES = {
    "table": ((1.2, 0.7, 0.75), "wood", True, 'table; "shape": "round" for a round one'),
    "chair": ((0.45, 0.48, 0.9), "wood", True, "chair (a seat); its back is at +y"),
    "armchair": ((0.85, 0.85, 1.0), "fabric", True, "padded armchair (a seat)"),
    "stool": ((0.38, 0.38, 0.75), "wood", True, "stool (a seat)"),
    "bench": ((1.4, 0.4, 0.45), "wood", True, "bench (a seat)"),
    "sofa": ((1.9, 0.85, 0.85), "fabric", True, "sofa (a seat)"),
    "seat": ((0.45, 0.45, 0.46), "wood", True, "invisible seat where the picture already shows a chair or car seat"),
    "bed": ((1.6, 2.0, 0.55), "fabric", True, "bed with pillows"),
    "desk": ((1.2, 0.6, 0.75), "wood", True, "desk with drawers"),
    "counter": ((2.0, 0.6, 0.95), "wood", True, "shop or kitchen counter"),
    "shelf": ((0.9, 0.32, 1.8), "wood", True, "empty shelf"),
    "bookshelf": ((0.9, 0.32, 1.8), "wood", True, "shelf full of books"),
    "door": ((0.9, 0.06, 2.05), "wood", True, 'door people enter, exit and open; "bell": true for a shop bell'),
    "pickup_truck": ((2.0, 4.8, 1.9), "metal", True,
                     'procedural pickup with a cab, dashboard, steering wheel and optional "door_id"'),
    "steering_wheel": ((0.48, 0.08, 0.48), "leather", False,
                       '3D steering wheel; use "picture_rect" to fit it to a reference image'),
    "car_radio": ((0.38, 0.1, 0.2), "plastic", False,
                  '3D dashboard radio; use "picture_rect" to fit it to a reference image'),
    "wall": ((3.0, 0.12, 2.6), "stone", True, "plain wall"),
    "window": ((1.2, 0.08, 1.2), "glass", False, "window (hangs on a wall)"),
    "lamp": ((0.35, 0.35, 1.6), "metal", True, "floor lamp with warm light"),
    "street_lamp": ((0.3, 0.3, 3.6), "metal", True, "street lamp with light"),
    "lantern": ((0.18, 0.18, 0.32), "metal", False, "oil lantern with a flickering flame"),
    "candle": ((0.06, 0.06, 0.18), "wax", False, "candle with a flickering flame"),
    "fireplace": ((1.4, 0.5, 1.2), "stone", True, "fireplace with a burning fire and firelight"),
    "christmas_tree": ((1.1, 1.1, 2.0), "fabric", True, "decorated Christmas tree with fairy lights"),
    "pine_tree": ((2.2, 2.2, 5.0), "fabric", True, "tall pine tree"),
    "plant": ((0.45, 0.45, 1.0), "ceramic", True, "potted plant"),
    "snowman": ((0.8, 0.8, 1.6), "snow", True, "snowman with a hat and scarf"),
    "tv": ((1.1, 0.25, 1.2), "plastic", True, "television on a stand"),
    "box": ((0.5, 0.5, 0.5), "wood", True, "plain box"),
    "crate": ((0.6, 0.6, 0.6), "wood", True, "wooden crate"),
    "barrel": ((0.6, 0.6, 0.9), "wood", True, "wooden barrel"),
    "sack": ((0.6, 0.45, 0.8), "fabric", True, "full cloth sack (a toy sack)"),
    "riser": ((2.0, 1.5, 0.3), "wood", True, "low platform (a stage for Santa's chair)"),
    "rug": ((2.0, 1.4, 0.01), "fabric", False, "rug on the floor"),
    "picture_frame": ((0.6, 0.04, 0.45), "wood", False, 'framed picture; hang it with "elevation"'),
    "cup": ((0.08, 0.08, 0.1), "ceramic", False, "coffee cup"),
    "bottle": ((0.08, 0.08, 0.3), "glass", False, "bottle"),
    "book": ((0.17, 0.24, 0.04), "paper", False, "book"),
    "phone": ((0.075, 0.155, 0.009), "plastic", False, "smartphone"),
    "laptop": ((0.34, 0.24, 0.23), "metal", False, "open laptop"),
    "gift": ((0.35, 0.35, 0.3), "paper", False, "wrapped present with a ribbon"),
    "cash_register": ((0.42, 0.4, 0.3), "plastic", False, "cash register"),
    "crowbar": ((0.03, 0.75, 0.05), "metal", False, "crowbar lying down"),
    "santa_hat": ((0.3, 0.3, 0.32), "fabric", False, "Santa hat lying on its side"),
    "picture_road": (None, None, False, "road surface matched to a photographed street (screen_path, width)"),
}
SEAT_TYPES = ["chair", "armchair", "stool", "bench", "sofa", "seat"]

# --- actions -----------------------------------------------------------------------------------------------
def p(kind, help_, required=False, default=None, values=None, open_to=None):
    """One parameter. `open_to` marks an enum whose list is a STARTING POINT - something on the machine
    may add to it (a fabric made on a GPU), so a plain name is let through and the words say where
    those names come from."""
    out = {"type": kind, "help": help_, "required": required}
    if default is not None:
        out["default"] = default
    if values is not None:
        out["values"] = list(values)
    if open_to is not None:
        out["open_to"] = open_to
    return out


# --- what every number means -------------------------------------------------------------------------------
# A number on its own is a text box, and a text box tells you nothing: is "speed" 1 or 100? what is a sensible
# vignette? So every number a person can set declares the span it lives in - (lowest, highest, step, unit) -
# and the app draws a slider instead of asking them to guess. These are the bounds of the CONTROL, not of the
# format: a scene written by hand or by Gemini may still hold a number outside them and renders fine.
# Keyed by parameter name, because the names mean the same thing wherever they appear; where they do not,
# "action.param" wins over "param" (a clip's speed goes further than a speaking speed).
# tests/test_schema.py checks that EVERY number has one and that its default sits inside it, so a new
# parameter cannot appear in the app as a bare box.
RANGES = {
    "seconds": (0, 20, 0.1, "s"),
    "pause": (0, 3, 0.1, "s"),
    "speed": (0.5, 2, 0.05, "×"),
    "perform.speed": (0.25, 3, 0.05, "×"),
    "strike.speed": (0.25, 3, 0.05, "×"),
    "intensity": (0, 1, 0.05, ""),
    "volume": (0, 1, 0.05, ""),
    "fade": (0, 10, 0.1, "s"),
    "lens": (14, 200, 1, "mm"),
    "distance": (0.3, 3, 0.05, "m"),
    "hit_stop": (0, 8, 1, "frames"),
    "contact": (0, 5, 0.05, "s"),
    "depth": (0.1, 0.9, 0.02, "m"),
    "side_offset": (-1, 1, 0.05, "m"),
    "angle": (0, 3.14, 0.05, "rad"),
    "turn": (-45, 45, 1, "°"),
    "from": (0, 30, 0.05, "s"),
    "to": (0, 30, 0.05, "s"),
    "blend": (0, 1.5, 0.05, "s"),
    "ambience_volume": (0, 1, 0.05, ""),
    "ambience_width": (0, 0.5, 0.01, ""),
    "ambience_duck_db": (0, 24, 1, "dB"),
    "music_duck_db": (0, 24, 1, "dB"),
    "transition_seconds": (0, 5, 0.1, "s"),
    "vignette": (0, 1, 0.05, ""),
    "grain": (0, 1, 0.05, ""),
    "age": (16, 90, 1, "years"),
    "height_cm": (120, 215, 1, "cm"),
    "cap.droop": (0, 1, 0.05, ""),
    "cap.towards": (0, 360, 5, "°"),
    "cap.band": (0.1, 0.5, 0.01, ""),
    "cap.bobble": (0, 1.5, 0.05, ""),
    "hat_size": (0.7, 1.6, 0.02, ""),
    "costume.cape_length": (0.3, 1.2, 0.02, ""),
    "costume.tie_length": (0.7, 1.3, 0.02, ""),
    "costume.wristband_width": (1, 3, 0.1, ""),
}


def with_range(name, param, owner=None):
    """A copy of one parameter with its slider span filled in, when it is a number we have a span for."""
    if param.get("type") != "number":
        return param
    span = RANGES.get(f"{owner}.{name}") or RANGES.get(name)
    if not span:
        return param
    lo, hi, step, unit = span
    return dict(param, lo=lo, hi=hi, step=step, unit=unit)


def with_ranges(params, owner=None):
    """A table of parameters with every number's slider span filled in."""
    return {k: with_range(k, v, owner) for k, v in params.items()}


_LINE = {
    "text": p("text", "the words (spoken with the character's voice, and the transcript for lip-sync)"),
    "audio": p("audio", "a recorded line instead of the voice, e.g. voices/maya_001.wav (keep text as transcript)"),
    "expression": p("enum", "face while saying it", values=EXPRESSIONS),
    "fx": p("enum", "voice effect", values=VOICE_FX),
    "speed": p("number", "speaking speed of the generated voice", default=1.0),
    "pause": p("number", "seconds of silence after the line", default=0.3),
}
# who: the step belongs to a cast member
ACTIONS = {
    "walk": {"who": True, "help": "walk to a spot; people route around props",
             "params": {"to": p("point", "where to go, [x, y] in metres", True),
                        "pace": p("enum", "how fast", default="normal", values=PACES)}},
    "face": {"who": True, "help": "turn the body towards someone or something",
             "params": {"target": p("target", "a cast member, \"camera\" or a spot [x, y]", True)}},
    "look": {"who": True, "help": "turn head and eyes only, then look back",
             "params": {"target": p("look", "a cast member, camera, a spot [x, y], left, right, up or down", True),
                        "seconds": p("number", "how long", default=1.5)}},
    "say": {"who": True, "help": "speak a line (lip-synced)", "params": dict(_LINE)},
    "think": {"who": True, "help": "an inner voice: heard, mouth closed, camera moves in",
              "params": dict(_LINE, pause=p("number", "seconds of silence after the line", default=0.6))},
    "narrate": {"who": False, "help": "voice-over by a narrator nobody sees",
                "params": {**{k: v for k, v in _LINE.items() if k != "expression"},
                           "voice": p("voice", "narrator voice (else the episode's \"narrator\")", values=VOICES)}},
    "emote": {"who": True, "help": "change the face (stays until changed; with seconds, only for a while)",
              "params": {"expression": p("enum", "the feeling", True, values=EXPRESSIONS),
                         "intensity": p("number", "0..1", default=1.0),
                         "seconds": p("number", "only for this long (empty: until changed)")}},
    "gesture": {"who": True, "help": "a hand or head gesture",
                "params": {"type": p("enum", "which gesture", True, values=GESTURES),
                           "target": p("target", "for point: who or what to point at"),
                           "hand": p("enum", "which hand for one-hand gestures", values=["right", "left"]),
                           "seconds": p("number", "how long")}},
    "posture": {"who": True, "help": "change how someone stands or sits (stays until changed)",
                "params": {"posture": p("enum", "the posture", True, values=POSTURES)}},
    "hold": {"who": True, "help": "pick up a prop and carry it (walks and motion clips keep it in hand)",
             "params": {"prop": p("prop", "id of a small prop in this scene", True),
                        "hand": p("enum", "which hand", default="right", values=["right", "left"])}},
    "release": {"who": True, "help": "let go of the held prop",
                "params": {"to": p("point", "where to set it down [x, y]; leave out to let go in place"),
                           "hand": p("enum", "which hand lets go", values=["right", "left"])}},
    "strike": {"who": True, "help": "a fight beat: close to striking distance, land a motion-clip attack with an impact sound and a tiny hit-stop; the target reacts",
               "params": {"target": p("target", "who gets hit", True),
                          "clip": p("clip", "the attack motion clip", True),
                          "from": p("number", "clip start, seconds"),
                          "to": p("number", "clip end, seconds"),
                          "speed": p("number", "playback speed", default=1.0),
                          "contact": p("number", "seconds into the clip window where the blow lands (default: 40% in)"),
                          "react": p("enum", "how the target takes it", default="stagger",
                                     values=["stagger", "dodge", "block", "none"]),
                          "distance": p("number", "striking distance in metres", default=0.9),
                          "hit_stop": p("number", "frames the impact hangs (0: none)", default=2),
                          "hands": p("enum", "what the attacking hands do (default: a closed fist)",
                                     values=["fist", "open"]),
                          "sound": p("sfx", "impact sound (default: by reaction - hit_hard, block, hit)"),
                          "swing_sound": p("sfx", "the swing through the air", default="whoosh")}},
    "duck": {"who": True, "help": "duck down quickly and come back up (a dodge)",
             "params": {"seconds": p("number", "how long", default=1.0),
                        "depth": p("number", "how far down in metres", default=0.32)}},
    "enter": {"who": True, "help": "come in through a door and walk to a spot",
              "params": {"door": p("door", "id of a door prop", True), "to": p("point", "where to walk to")}},
    "exit": {"who": True, "help": "walk out through a door",
             "params": {"door": p("door", "id of a door prop", True), "sound": p("sfx", "door opening sound"),
                        "close_sound": p("sfx", "door closing sound")}},
    "open": {"who": True, "help": "walk to a door and open it",
             "params": {"door": p("door", "id of a door prop", True), "sound": p("sfx", "door sound"),
                        "side_offset": p("number", "metres towards the handle side"),
                        "angle": p("number", "how far it opens (radians)", default=1.25)}},
    "sit": {"who": True, "help": "sit down on a seat prop",
            "params": {"on": p("seat", "id of a chair, armchair, stool, bench, sofa or seat prop", True)}},
    "stand": {"who": True, "help": "stand up", "params": {}},
    "drive": {"who": True, "help": "hands on the steering wheel for a while",
              "params": {"seconds": p("number", "how long", default=8.0),
                         "wheel": p("text", "id of the steering_wheel (or pickup_truck) prop the hands hold"),
                         "turn": p("number", "steady steering angle in degrees (+ left)", default=0.0)}},
    "sound": {"who": False, "help": "play a sound effect",
              "params": {"sfx": p("sfx", "effect from the sound library", True),
                         "volume": p("number", "0..1", default=0.8),
                         "seconds": p("number", "wait this long before the next step", default=0.0)}},
    "music": {"who": False, "help": "start (or stop) music from here",
              "params": {"bed": p("bed", "music from the sound library or a file"),
                         "volume": p("number", "0..1", default=0.35), "fade": p("number", "fade seconds", default=1.5),
                         "stop": p("bool", "fade the music out instead")}},
    "camera": {"who": False, "help": "choose the shot from here (the director stops cutting until it ends)",
               "params": {"shot": p("enum", "how close the camera is: wide shows the room, close is a face", True,
                                    values=SHOT_KINDS),
                          "on": p("cast_list", "who the camera is pointed at (nobody: the room)"),
                          "move": p("enum", "where the camera goes while the shot runs; the middle of the pad holds it still",
                                    default="static", values=CAMERA_MOVES),
                          "lens": p("number", "lens in mm: 24 takes in the whole room, 85+ blurs the background "
                                              "(empty: chosen for the shot)"),
                          "seconds": p("number", "how long this shot holds (empty: until the next camera step)")}},
    "perform": {"who": True, "help": "play a motion-capture clip (Mixamo or CMU): a punch, a sword swing, a dance",
                "params": {"clip": p("clip", "name in the motion library (python castforge.py motion list)", True),
                           "from": p("number", "start this many seconds into the clip", default=0.0),
                           "to": p("number", "stop at this second of the clip (empty: its end)"),
                           "speed": p("number", "playback speed", default=1.0),
                           "blend": p("number", "seconds to blend into and out of the clip", default=0.3),
                           "travel": p("bool", "move across the floor with the clip (off: on the spot)",
                                       default=True),
                           "hands": p("enum", "what the hands do (clips carry no finger movement; guessed "
                                               "from the clip name when empty)",
                                      values=["fist", "open"])}},
    "wait": {"who": False, "help": "nothing happens for a while",
             "params": {"seconds": p("number", "how long", default=1.0)}},
}
WITH_PREVIOUS = p("enum", "start together with the step before", values=["previous"])

# scene settings (top level of a scene, or episode defaults)
SCENE_KEYS = {
    "background": p("image", "the set picture (empty place, no people)", True),
    "floor": p("enum", "footstep sound", default="wood", values=FLOORS),
    "ambience": p("bed", "background sound: a library bed or a WAV file"),
    "ambience_volume": p("number", "0..1", default=0.5),
    "ambience_width": p("number", "how wide the background sound sits, 0 centred to 0.5 wide", default=0.25),
    "ambience_duck_db": p("number", "how far the background dips under dialogue, in dB", default=4),
    "music_duck_db": p("number", "how far music dips under dialogue, in dB", default=9),
    "music": p("bed", "music for the whole scene: a library bed or a file"),
    "lighting": p("enum", "lighting mood", default="auto", values=LIGHTING),
    "weather": p("weather", 'falling snow or rain, e.g. "snow" or {"type": "snow", "amount": 0.5, "fog": 0.2}'),
    "look": p("enum", "cinematic lights and effects (standard quality and above)", default="cinematic",
              values=["cinematic", "plain"]),
    "shots": p("enum", "how the camera cuts", default="auto", values=SHOTS_MODES),
    "aspect": p("enum", "picture shape", default="16:9", values=ASPECTS),
    "set": p("enum", "3D set from the picture, or a flat backdrop", default="3d", values=["3d", "flat"]),
    "set_folder": p("set", "a built set folder to use (its picture, its depth and everything standing in "
                            "it come with it; the scene's own props are added on top)"),
    "duck": p("bool", "music and ambience dip under dialogue", default=True),
    "gaze": p("bool", "eyes look at whoever matters", default=True),
    "quality": p("enum", "default render quality", default="blocking", values=QUALITIES),
}
FINISH_KEYS = {"title", "credits", "transition", "transition_seconds", "grade", "vignette", "grain", "subtitles",
               "master", "poster", "chapter"}
FINISH_SETTINGS = {
    "transition": p("enum", "how this scene begins (episode: the default)", default="cut", values=TRANSITIONS),
    "transition_seconds": p("number", "transition length"),
    "grade": p("enum", "colour grade", default="neutral", values=GRADES),
    "vignette": p("number", "darker corners, 0..1", default=0.0),
    "grain": p("number", "film grain, 0..1 (cinematic look: 0.2)"),
    "subtitles": p("enum", "subtitle track", default="soft", values=SUBTITLES),
}


# --- character designs (<name>.design.json; blender/build_character.py builds them) -------------------------
# keys with a dot are nested: "hair.color" is design["hair"]["color"]
BODY_BUILDS = ["slim", "average", "athletic", "heavy", "muscular"]
BEARDS = ["none", "scruffy", "full", "long", "faun", "moustache", "santa"]
# The wardrobe itself is core/appearance.py; these names come from there so a hat added to the wardrobe
# turns up in the designer, the checker and the Gemini prompt without being listed again here.
HATS = ["none"] + sorted(appearance.HATS) + sorted(appearance.MADE_HATS)
EYES = ["brown", "brownlight", "green", "grey", "blue", "bluegreen", "deepblue", "lightblue", "ice"]
CHARACTER = {
    "gender": p("enum", "body type", required=True, values=["male", "female"]),
    "age": p("number", "years, 16-90", required=True),
    "height_cm": p("number", "height in centimetres", required=True),
    "build": p("enum", "body build", default="average", values=BODY_BUILDS),
    "skin": p("color", "skin tone"),
    "eyes": p("enum", "eye colour", values=EYES),
    "hair.length": p("enum", "hair length", default="short", values=["none", "short", "medium", "long"]),
    "hair.color": p("color", "hair colour (a beard takes it too)"),
    "beard": p("enum", "beard", default="none", values=BEARDS),
    "hat": p("enum", "hat (hides the hair). santa_made is built for this character's own head",
             default="none", values=HATS),
    "cap.droop": p("number", "how far a made cap flops over, 0 straight up to 1 right over", default=0.6),
    "cap.towards": p("number", "which way it flops, in degrees round the head (0 is their left, 90 behind)",
                     default=20.0),
    "cap.band": p("number", "how much of a made cap is fur, 0.15 a trim to 0.45 a deep roll", default=0.3),
    "cap.bobble": p("number", "the bobble on the end, 0 none to 1.5 enormous", default=1.0),
    "parts": p("parts", "parts of the body or of something worn, reshaped by hand: a list of "
                        "{on, at: [x, y, z], radius, scale, move: [x, y, z] metres, turn: [x, y, z] "
                        "degrees}. The studio writes these when you click a part and work on it; leave "
                        "the list out unless you mean to reshape something"),
    "hat_size": p("number", "how big the hat is, 0.7 small to 1.6 oversized (1 = as the asset comes)",
                  default=1.0),
    "outfit.style": p("enum", "whole-body outfit (a uniform, suit or robe) instead of a top and trousers",
                      default="casual", values=["casual", "suit", "formal", "work", "robe", "tunic"]),
    # a one-piece outfit has no separate top, so there is no hem for a long coat to continue
    "outfit.garment": p("enum", "below the waist (when the style is casual)", default="trousers",
                        values=["trousers", "shorts", "skirt", "dress"]),
    "outfit.sleeves": p("enum", "sleeves", default="long", values=["short", "long"]),
    "outfit.top": p("color", "top colour"),
    "outfit.bottom": p("color", "trousers / skirt colour"),
    "outfit.shoes": p("color", "shoe colour"),
    "costume.coat": p("enum", "long: the top becomes a coat down to mid-thigh", default="none", values=["none", "long"]),
    # An enum that GROWS. The four below are shader numbers and nothing else; a fabric made on a GPU
    # (library/fabrics, see generate/make_fabric.py) is a real surface with a weave, and is named here
    # directly. Those names are not known when this file is read, so the check lets a plain slug
    # through and the build says plainly when there is no such fabric on this machine.
    "costume.fabric": p("enum", "garment: its own knit/cloth texture; a plain velvet, leather or "
                                "cotton; or the name of a fabric made on a GPU",
                        default="garment", values=["garment", "velvet", "leather", "cotton"],
                        open_to="a fabric in library/fabrics"),
    "costume.trim": p("color", "fur trim on cuffs, hem, collar, front and boot tops (empty: none)"),
    "costume.belt": p("color", "belt at the waist (empty: none)"),
    "costume.buckle": p("color", "belt buckle"),
    "costume.gloves": p("color", "gloves (empty: bare hands)"),
    "costume.boots": p("color", "boots instead of shoes (empty: shoes)"),
    "costume.cape": p("color", "a cape hanging from the shoulders (empty: none)"),
    "costume.cape_length": p("number", "how far the cape falls, 0.3 short to 1.2 past the knees", default=0.75),
    "costume.armour": p("color", "metal plates: breastplate, shoulders, forearms, shins (empty: none)"),
    "costume.hood": p("color", "a hood over the head, open at the face (empty: none)"),
    # Worn things that are MADE for this body rather than fetched from the wardrobe (blender/tailor.py).
    # The wardrobe has twenty-six garments and not one sock, tie, scarf, watch or band among them, and its
    # two pairs of shoes are one size - so these are cut to the character's own ankle, wrist and chest
    # every time, which is why they fit anybody. A colour is what asks for one; footwear asks by style.
    "outfit.shoe_style": p("enum", "footwear made for this foot, instead of the library's one-size shoes",
                           default="none", values=list(tailor.SHOE_STYLES)),
    "costume.socks": p("color", "socks (empty: none)"),
    "costume.sock_height": p("enum", "how far the socks come up", default="crew",
                             values=list(tailor.SOCK_HEIGHTS)),
    "costume.tie": p("color", "a tie knotted at the collar (empty: none)"),
    "costume.tie_length": p("number", "how far the tie hangs, 0.7 short to 1.3 long", default=1.0),
    "costume.scarf": p("color", "a scarf round the neck (empty: none)"),
    "costume.watch": p("color", "a watch on the wrist (empty: none)"),
    "costume.watch_side": p("enum", "which wrist the watch is on", default="left",
                            values=list(tailor.SIDES)),
    "costume.wristband": p("color", "a band or bracer round the forearm (empty: none)"),
    "costume.wristband_side": p("enum", "which arm the band is on", default="both",
                                values=list(tailor.SIDES)),
    "costume.wristband_width": p("number", "1 a cuff, 3 a bracer up the forearm", default=1.0),
}
# Everything a person can shape themselves: the face and body sliders (core/appearance.py), the whole-head
# shape, and the hair and eyebrows they can pick. Built from that one table so a new slider needs no edit
# here, in the app, or in the checker - all three read CHARACTER.
CHARACTER["face.head_shape"] = p("enum", "the overall shape of the head", default="none",
                                 values=appearance.HEAD_SHAPES)
CHARACTER["hair.style"] = p("enum", "hair style (overrides the length; a hat still hides it)",
                            default="", values=[""] + list(appearance.HAIR_STYLES))
CHARACTER["eyebrows"] = p("enum", "eyebrow shape", default="style_1", values=list(appearance.EYEBROWS))
for _part, _table in (("face", appearance.FACE), ("body", appearance.BODY)):
    for _key, (_group, _plus, _minus, _help) in _table.items():
        CHARACTER[f"{_part}.{_key}"] = p("slider", _help, default=0.0)
SLIDER_RANGE = appearance.RANGE          # -1 .. +1, the same for every slider
FACE_GROUPS = appearance.groups(appearance.FACE)
BODY_GROUPS = appearance.groups(appearance.BODY)
# ready-made looks the app offers; each is a set of design keys (dotted, as above)
COSTUMES = {
    "knight": {"outfit.style": "work", "outfit.top": "#3b4150", "outfit.bottom": "#3b4150",
               "costume.armour": "#9aa3ad", "costume.cape": "#7c2230", "costume.cape_length": 0.9,
               "costume.belt": "#4a3524", "costume.buckle": "#c9a227", "costume.gloves": "#4a3524",
               "costume.boots": "#3a2a1c", "build": "muscular"},
    "wizard": {"outfit.style": "robe", "outfit.top": "#2f3566", "outfit.bottom": "#2f3566",
               "costume.cape": "#232a52", "costume.cape_length": 1.1,
               "costume.belt": "#6b5230", "beard": "long", "hair.color": "#d8d4cc",
               "costume.fabric": "cotton"},
    "soldier": {"outfit.style": "work", "outfit.top": "#4a5240", "outfit.bottom": "#4a5240",
                "costume.belt": "#2b2b2b", "costume.buckle": "#8a8f98", "costume.boots": "#241c14",
                "costume.gloves": "#2f2a22", "hat": "flat_cap", "build": "athletic"},
    "detective": {"outfit.style": "formal", "outfit.top": "#2a2b30", "outfit.bottom": "#2a2b30",
                  "costume.coat": "long", "costume.fabric": "leather", "hat": "fedora",
                  "costume.belt": "#1c1c1c", "outfit.shoes": "#1a1a1a"},
    "ranger": {"outfit.style": "work", "outfit.top": "#3c4a37", "outfit.bottom": "#2f3a2c",
               "costume.hood": "#36432f", "costume.cape": "#2e3828", "costume.cape_length": 0.7,
               "costume.fabric": "leather", "costume.belt": "#3a2a1c", "costume.buckle": "#8a8f98",
               "costume.gloves": "#3a2a1c", "costume.boots": "#2b2018", "build": "athletic"},
    "monk": {"outfit.style": "robe", "outfit.top": "#5a4632", "outfit.bottom": "#5a4632",
             "costume.hood": "#503d2c", "costume.fabric": "cotton", "costume.belt": "#8a6f4a",
             "hair.length": "none", "beard": "short"},
    "villager": {"outfit.style": "tunic", "outfit.top": "#7a6a4e", "outfit.bottom": "#5a4a36",
                 "costume.belt": "#4a3524", "costume.boots": "#3a2a1c"},
    "santa": {"hat": "santa", "hat_size": 1.35, "beard": "santa", "build": "heavy", "hair.color": "#eeeae4", "outfit.garment": "trousers",
              "outfit.sleeves": "long", "outfit.top": "#c8102e", "outfit.bottom": "#c8102e",   # the cap's own
              # red is #dc204c and it is never recoloured (a hat takes no tint), so the suit has to
              # be asked for in that neighbourhood or the two do not look like one costume
              "costume.coat": "long", "costume.fabric": "velvet", "costume.trim": "#f3efe8", "costume.belt": "#141414",
              "costume.buckle": "#c9a227", "costume.gloves": "#f3efe8", "costume.boots": "#141414"},
    # Everyday looks, each one COMPLETE: a suit with no shoes, no socks and no watch is not a look, it is
    # a garment. The wardrobe has nothing below the ankle but two pairs of shoes, so these ask for
    # footwear and accessories that are MADE for the body (blender/tailor.py, `outfit.shoe_style` and the
    # `costume.*` colours below) and so arrive at the right size on anybody.
    "business": {"outfit.style": "formal", "outfit.top": "#23262e", "outfit.bottom": "#23262e",
                 "outfit.shoe_style": "shoe", "outfit.shoes": "#17161a", "costume.socks": "#1b1d24",
                 "costume.sock_height": "crew", "costume.tie": "#8c1018", "costume.watch": "#c7ccd1"},
    "office": {"outfit.style": "suit", "outfit.top": "#3d4654", "outfit.bottom": "#2f3540",
               "outfit.shoe_style": "shoe", "outfit.shoes": "#3a2a1c", "costume.socks": "#2f3540",
               "costume.watch": "#b08d57"},
    "street": {"outfit.garment": "trousers", "outfit.sleeves": "short", "outfit.top": "#d8dde3",
               "outfit.bottom": "#36476b", "outfit.shoe_style": "sneaker", "outfit.shoes": "#f2f2f0",
               "costume.socks": "#ffffff", "costume.sock_height": "ankle", "costume.watch": "#2a2d33"},
    "sport": {"outfit.style": "work", "outfit.top": "#1f2a44", "outfit.bottom": "#1f2a44",
              "outfit.shoe_style": "sneaker", "outfit.shoes": "#e8482c", "costume.socks": "#ffffff",
              "costume.sock_height": "ankle", "costume.wristband": "#e8482c", "build": "athletic"},
    "winter": {"outfit.garment": "trousers", "outfit.sleeves": "long", "outfit.top": "#5c6b7a",
               "outfit.bottom": "#2f3540", "outfit.shoe_style": "boot", "outfit.shoes": "#3a2a1c",
               "costume.socks": "#8a7355", "costume.sock_height": "knee", "costume.scarf": "#a33a2e",
               "costume.gloves": "#4a3524"},
    "summer": {"outfit.garment": "shorts", "outfit.sleeves": "short", "outfit.top": "#f0e6c8",
               "outfit.bottom": "#c9a66b", "outfit.shoe_style": "sandal", "outfit.shoes": "#7a5a3a",
               "costume.watch": "#c7ccd1"},
}


def design_get(design, key):
    """A dotted design key's value (None when missing)."""
    for part in key.split("."):
        design = design.get(part) if isinstance(design, dict) else None
    return design


# Costume pieces that cannot be built together, and why. A design may ask for either; asking for both
# is asking for something that cannot exist, and the build used to carry on and quietly make one of them.
# `blender/build_character.py` reads ONE_PIECE from here, so the two can never disagree about which
# outfits have no separate top.
ONE_PIECE = ("suit", "formal", "work", "robe", "tunic")


def costume_clashes(design):
    """Pairs of things a design asks for that cannot both be built, with what to change."""
    if not isinstance(design, dict):
        return []
    outfit = design.get("outfit") if isinstance(design.get("outfit"), dict) else {}
    costume = design.get("costume") if isinstance(design.get("costume"), dict) else {}
    out = []
    style = outfit.get("style")
    if costume.get("coat") == "long" and style in ONE_PIECE:
        out.append(f'costume.coat "long" and outfit.style "{style}" cannot both be built: a long coat is '
                   f"made by continuing the top's hem downwards, and a one-piece outfit has no separate "
                   f"top. Drop one of the two.")
    shoe_style = outfit.get("shoe_style")
    if costume.get("boots") and shoe_style not in (None, "", "none"):
        out.append(f'costume.boots and outfit.shoe_style "{shoe_style}" cannot both be built: footwear '
                   f"made for this foot replaces the library's boots. Drop one of the two.")
    if costume.get("boots") and costume.get("socks"):
        out.append("costume.socks and costume.boots: socks are cut for the bare foot and come through a "
                   "library boot. The boot covers them anyway, so drop costume.socks.")
    return out


def check_design(design):
    """Plain-language problems in a character design (empty list: it can be built)."""
    if not isinstance(design, dict):
        return ["the design must be a JSON object"]
    problems = []
    for key, spec in CHARACTER.items():
        v = design_get(design, key)
        if v is None or v == "":
            if spec["required"]:
                problems.append(f"the design needs {key!r}")
        elif spec["type"] == "enum" and v not in spec["values"]:
            # Some enums grow: `open_to` says the list here is a starting point and anything that looks
            # like a name may be added by what is on the machine. Still checked, just not against a
            # list that cannot know about it.
            if spec.get("open_to") and isinstance(v, str) and re.fullmatch(r"[a-z0-9][a-z0-9_]{1,46}", v):
                pass
            else:
                problems.append(f"{key}: {v!r} is not one of {', '.join(spec['values'])}"
                                + (f" (or {spec['open_to']})" if spec.get("open_to") else ""))
        elif spec["type"] == "number" and not isinstance(v, (int, float)):
            problems.append(f"{key}: {v!r} must be a number")
        elif spec["type"] == "slider" and not (isinstance(v, (int, float)) and not isinstance(v, bool)
                                               and appearance.RANGE[0] <= v <= appearance.RANGE[1]):
            problems.append(f"{key}: {v!r} must be a number from {appearance.RANGE[0]} to {appearance.RANGE[1]}")
        elif spec["type"] == "parts":
            for item in (v if isinstance(v, list) else [v]):
                if not isinstance(item, dict):
                    problems.append("parts: each one must be an object")
                elif not (isinstance(item.get("at"), (list, tuple)) and len(item["at"]) == 3):
                    problems.append("parts: each one needs 'at': [x, y, z]")
                elif not all(isinstance(item.get(k), (int, float)) for k in ("radius", "scale")):
                    problems.append("parts: each one needs a number 'radius' and 'scale'")
                elif any(not (isinstance(item.get(k), (list, tuple)) and len(item[k]) == 3)
                         for k in ("move", "turn") if k in item):
                    problems.append("parts: 'move' and 'turn' are [x, y, z] when they are there at all")
                elif not isinstance(item.get("on"), str):
                    problems.append("parts: each one needs 'on' (body, hat, top, bottom, outfit, shoes)")
        elif spec["type"] == "color" and not (isinstance(v, str) and len(v.lstrip("#")) == 6
                                              and all(c in "0123456789abcdefABCDEF" for c in v.lstrip("#"))):
            problems.append(f"{key}: {v!r} must be a colour like #a3161a")
    return problems + costume_clashes(design)


def library_files():
    """The sound library index: {"sfx": {name: [files]}, "beds": ..., "footsteps": ...}, relative to SFX_DIR."""
    try:
        return json.load(open(os.path.join(config.SFX_DIR, "library.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def clip_facts():
    """Every motion clip with what a person needs to choose one: how long it is and where it came from.

    A clip picker that only lists names makes you load a clip to find out it is 16 seconds of samba.
    """
    out = []
    for name in motion.names(config.MOTIONS_DIR):
        facts = {"name": name, "seconds": None, "source": None, "fps": None}
        try:
            meta = json.load(open(os.path.join(config.MOTIONS_DIR, name + ".json"), encoding="utf-8"))
            facts.update(seconds=round(float(meta.get("seconds") or 0), 2) or None,
                         source=meta.get("source"), fps=round(float(meta.get("fps") or 0)) or None)
        except (OSError, ValueError, TypeError):
            pass                      # a clip we cannot read is still a clip you can name in a scene
        out.append(facts)
    return out


def library():
    """The library's names: footstep floors, sound effects and beds, and motion clips."""
    lib = library_files()
    return dict({k: sorted(lib.get(k, {})) for k in ("footsteps", "sfx", "beds")},
                clips=motion.names(config.MOTIONS_DIR))


def describe():
    """Everything the web app needs to build its forms (served as /api/schema)."""
    return {"actions": {name: dict(a, params=with_ranges(a["params"], name)) for name, a in ACTIONS.items()},
            "with": WITH_PREVIOUS, "scene": with_ranges(SCENE_KEYS), "finish": with_ranges(FINISH_SETTINGS),
            "props": {k: {"size": v[0], "material": v[1], "blocks": v[2], "help": v[3]} for k, v in PROP_TYPES.items()},
            "materials": list(MATERIALS), "voices": VOICES, "voice_facts": VOICE_FACTS,
            "floors": FLOORS, "expressions": EXPRESSIONS,
            "gestures": GESTURES, "postures": POSTURES, "paces": PACES, "voice_fx": VOICE_FX, "grades": GRADES,
            "transitions": TRANSITIONS, "lighting": list(LIGHTING), "lights": {k: v for k, v in LIGHTING.items() if v}, "weather": WEATHER, "shots": SHOT_KINDS,
            "moves": CAMERA_MOVES, "qualities": QUALITIES, "aspects": ASPECTS, "seats": SEAT_TYPES,
            "look_directions": LOOK_DIRECTIONS,
            "character": with_ranges(CHARACTER), "costumes": COSTUMES, "fix_parts": sorted(acting.FIX_PARTS),
            # the designer groups its sliders from these, so a new one appears in the app on its own
            "face_groups": FACE_GROUPS, "body_groups": BODY_GROUPS, "slider_range": list(SLIDER_RANGE),
            # which morph targets each slider leans on, so the live preview can shape the body in the
            # browser from the same table the build uses. One vocabulary, two places that read it.
            "slider_targets": {f"{part}.{key}": {"plus": plus, "minus": minus}
                               for part, table in (("face", appearance.FACE), ("body", appearance.BODY))
                               for key, (_g, plus, minus, _h) in table.items()},
            "head_shapes": {s_: f"head-{s_}" for s_ in appearance.HEAD_SHAPES if s_ != "none"},
            "library": library()}


# --- checking ----------------------------------------------------------------------------------------------
def check_scene(folder):
    """Plain-language problems in a scene folder's scene.json, printed; returns the number of errors."""
    f = os.path.join(folder, "scene.json")
    try:
        raw = open(f, encoding="utf-8").read()
    except OSError:
        print(f"ERROR: no scene.json in {folder}")
        return 1
    try:
        sc = json.loads(raw)
    except json.JSONDecodeError as e:
        line = raw.splitlines()[e.lineno - 1] if e.lineno - 1 < len(raw.splitlines()) else ""
        print(f"ERROR: scene.json is not valid JSON at line {e.lineno}: {e.msg}\n    {line.strip()}\n"
              "    (often a missing value, e.g. \"resolution\": [1280, 720], or a missing comma or bracket)")
        return 1
    if not isinstance(sc, dict):
        print("ERROR: scene.json must contain a JSON object")
        return 1
    if "scenes" in sc:
        # an episode: check every scene with the episode cast merged in
        lib = sc.get("cast", {})
        if not isinstance(lib, dict):
            print('ERROR: episode "cast" must be an object keyed by character name')
            return 1
        parts = sc["scenes"]
        if not isinstance(parts, list) or not parts:
            print('ERROR: episode "scenes" must be a non-empty list')
            return 1
        if any(not isinstance(value, dict) for value in lib.values()):
            print('ERROR: every episode cast member must have object settings')
            return 1
        defaults = {k: v for k, v in sc.items() if k not in ("cast", "scenes")}
        total = 0
        for i, part in enumerate(parts, 1):
            if not isinstance(part, dict):
                print(f"ERROR: scene {i} must be a JSON object")
                total += 1
                continue
            part_cast = part.get("cast", {})
            if not isinstance(part_cast, dict):
                print(f'ERROR: scene {i} "cast" must be an object keyed by character name')
                total += 1
                continue
            merged = dict(defaults)
            merged.update({k: v for k, v in part.items() if k != "cast"})
            merged_cast = {}
            for name, entry in part_cast.items():
                base = lib.get(name, {})
                if not isinstance(base, dict) or not isinstance(entry, dict):
                    print(f'ERROR: scene {i} cast member {name!r} must have object settings')
                    total += 1
                    continue
                merged_cast[name] = {**base, **entry}
            merged["cast"] = merged_cast
            print(f"--- scene {i} ({part.get('id', 'scene')})")
            total += check_parsed(folder, merged)
        return total
    return check_parsed(folder, sc)


def _is_point(v):
    return isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)


def _is_rect(v):
    return (isinstance(v, list) and len(v) == 4
            and all(isinstance(x, (int, float)) and not isinstance(x, bool) and 0 <= x <= 1 for x in v)
            and v[0] < v[2] and v[1] < v[3])


def _enum(value, values, what, problems):
    if value is not None and value not in values:
        problems.append(f"unknown {what} {value!r} (use {', '.join(map(str, values))})")


def check_fixes(sc, cast, problems, warnings):
    """Validate scene.json "fixes": hand-made pose corrections from the 3D editor."""
    entries = sc.get("fixes")
    if entries is None:
        return
    if not isinstance(entries, list):
        problems.append('"fixes" must be a list of pose fixes')
        return
    for n, fix in enumerate(entries, 1):
        if not isinstance(fix, dict):
            problems.append(f"pose fix {n} must be an object")
            continue
        if fix.get("who") not in cast:
            problems.append(f"pose fix {n}: {fix.get('who')!r} is not in the cast")
        if fix.get("part") not in acting.FIX_PARTS:
            problems.append(f"pose fix {n}: unknown body part {fix.get('part')!r} "
                            f"(use {', '.join(sorted(acting.FIX_PARTS))})")
        at = fix.get("at")
        if not isinstance(at, (int, float)) or isinstance(at, bool) or at < 0:
            problems.append(f'pose fix {n}: "at" must be a time in seconds')
        turn = fix.get("rotate")
        if (not isinstance(turn, list) or len(turn) != 3
                or any(not isinstance(v, (int, float)) or isinstance(v, bool) for v in turn)):
            problems.append(f'pose fix {n}: "rotate" must be [x, y, z] in degrees')
        elif max(abs(v) for v in turn) > 90:
            warnings.append(f"pose fix {n}: turning {fix.get('part')} by more than 90 degrees will look broken")
        for key in ("seconds", "fade"):
            if fix.get(key) is not None and (not isinstance(fix[key], (int, float)) or isinstance(fix[key], bool)
                                             or fix[key] < 0):
                problems.append(f'pose fix {n}: "{key}" must be a number of seconds')


def check_parsed(folder, sc):
    errors, warnings = [], []
    if not isinstance(sc, dict):
        print("ERROR: scene must be a JSON object")
        return 1
    lib = library()
    for key in ("background", "cast", "script"):
        if key not in sc and not (key == "background" and sc.get("set_folder")):
            errors.append(f'missing "{key}"')      # a built set brings its own picture
    if "cast" in sc and not isinstance(sc["cast"], dict):
        errors.append('"cast" must be an object keyed by character name')
    if not isinstance(sc.get("props", []), list):
        errors.append('"props" must be a list')
    if "script" in sc and not isinstance(sc["script"], list):
        errors.append('"script" must be a list')
    if "background" in sc and not isinstance(sc["background"], str):
        errors.append('"background" must be a file path')
    if errors:
        for e in errors:
            print("ERROR:", e)
        return len(errors)
    if sc.get("background") and not os.path.exists(os.path.join(folder, sc["background"])):
        errors.append(f"background image not found: {sc['background']}")
    if sc.get("set_folder"):
        if not isinstance(sc["set_folder"], str):
            errors.append('"set_folder" must be a folder path')
        else:
            sd = os.path.join(folder, sc["set_folder"])
            if not os.path.isdir(sd):
                errors.append(f"set folder not found: {sc['set_folder']}")
            elif not sets.is_set_folder(sd):
                errors.append(f"{sc['set_folder']} is not a built set yet: open it in Sets and save its "
                              "objects, then build it (python castforge.py set-build FOLDER)")
    for key in ("ambience", "music"):
        bed = sc.get(key)
        bed = bed.get("bed") if isinstance(bed, dict) else bed
        if bed is not None and not isinstance(bed, str):
            errors.append(f'"{key}" must be a sound-library name or file path')
            continue
        if bed and "." in os.path.basename(bed):
            if not os.path.exists(os.path.join(folder, bed)):
                warnings.append(f"{key} file not found: {bed} (remove the line or add the file)")
        elif bed and lib["beds"] and bed not in lib["beds"]:
            warnings.append(f"{key} {bed!r} is not in the sound library (python generate/make_sfx_library.py sfx --missing)")
    if sc.get("floor") and lib["footsteps"] and sc["floor"] not in lib["footsteps"]:
        warnings.append(f"no footstep sounds for floor {sc['floor']!r} (use {', '.join(lib['footsteps'])})")
    _enum(sc.get("lighting"), LIGHTING, "lighting", warnings)
    _enum(sc.get("shots"), SHOTS_MODES, "shots", warnings)
    _enum(sc.get("aspect"), ASPECTS, "aspect", errors)
    _enum(sc.get("grade"), GRADES, "grade", warnings)
    _enum(sc.get("transition"), TRANSITIONS, "transition", warnings)
    _enum(sc.get("subtitles"), SUBTITLES, "subtitles", warnings)
    weather = sc.get("weather")
    if weather:
        _enum(weather.get("type") if isinstance(weather, dict) else weather, WEATHER, "weather", warnings)
    cast = sc.get("cast", {})
    pos = {}
    props = {pr.get("id"): pr for pr in sc.get("props", []) if isinstance(pr, dict) and isinstance(pr.get("id"), str)}
    for name, c in cast.items():
        if not isinstance(name, str) or not isinstance(c, dict):
            errors.append(f"cast member {name!r} must have object settings")
            continue
        character = c.get("character", "")
        if not isinstance(character, str):
            errors.append(f"{name}: character must be a file path")
        elif not os.path.exists(os.path.join(folder, character)):
            errors.append(f"{name}: character file not found: {c.get('character')} (build it with: castforge.py character ...)")
        if c.get("voice") and (not isinstance(c["voice"], str) or c["voice"] not in VOICES):
            errors.append(f"{name}: unknown voice {c['voice']}")
        _enum(c.get("expression"), EXPRESSIONS, f"{name}: expression", errors)
        _enum(c.get("posture"), POSTURES, f"{name}: posture", errors)
        _enum(c.get("voice_fx"), VOICE_FX, f"{name}: voice_fx", errors)
        pos[name] = c.get("position", [0, 0])
        if c.get("sit"):
            seat = props.get(c["sit"] if isinstance(c["sit"], str) else None)
            if not seat:
                errors.append(f"{name}: sits on {c['sit']!r}, but there is no prop with that id")
            else:
                pos[name] = seat.get("position", pos[name])
    for pr in sc.get("props", []):
        if not isinstance(pr, dict):
            errors.append(f"prop {pr!r} must be an object")
            continue
        if "make" in pr and (not isinstance(pr["make"], str) or pr["make"] not in PROP_TYPES):
            warnings.append(f"prop {pr.get('id', '?')}: unknown type {pr['make']} (it will be built as a box)")
        if "file" in pr:
            if not isinstance(pr["file"], str) or not pr["file"]:
                errors.append(f'prop {pr.get("id", "?")}: "file" must be a model path')
            elif os.path.splitext(pr["file"])[1].lower() not in (".blend", ".glb", ".gltf", ".obj", ".fbx"):
                errors.append(f'prop {pr.get("id", "?")}: unsupported model file type {pr["file"]!r}')
            elif not os.path.isfile(os.path.join(folder, pr["file"])):
                errors.append(f'prop {pr.get("id", "?")}: model file not found: {pr["file"]}')
            for key in ("seat", "wheel"):
                if pr.get(key) is not None and not isinstance(pr[key], str):
                    errors.append(f'prop {pr.get("id", "?")}: "{key}" must be the name of an object in the model')
        if pr.get("material") and (not isinstance(pr["material"], str) or pr["material"] not in MATERIALS):
            warnings.append(f"prop {pr.get('id', '?')}: unknown material {pr['material']} (use {', '.join(MATERIALS)})")
        if pr.get("picture_rect") is not None and not _is_rect(pr["picture_rect"]):
            errors.append(f'prop {pr.get("id", "?")}: "picture_rect" must be [left, top, right, bottom] fractions')
        if pr.get("outside_rect") is not None and not _is_rect(pr["outside_rect"]):
            errors.append(f'prop {pr.get("id", "?")}: "outside_rect" must be [left, top, right, bottom] fractions')
        if pr.get("outside_image") is not None:
            if not isinstance(pr["outside_image"], str):
                errors.append(f'prop {pr.get("id", "?")}: "outside_image" must be a file path')
            elif not os.path.exists(os.path.join(folder, pr["outside_image"])):
                errors.append(f'prop {pr.get("id", "?")}: outside image not found: {pr["outside_image"]}')
        if pr.get("door_id") is not None and (
                pr.get("make") != "pickup_truck" or not isinstance(pr["door_id"], str) or not pr["door_id"]):
            errors.append(f'prop {pr.get("id", "?")}: "door_id" must be a non-empty id on a pickup_truck')
    door_ids = {pid for pid, prop in props.items() if prop.get("make") == "door"}
    for prop in sc.get("props", []):
        if isinstance(prop, dict) and prop.get("make") == "pickup_truck" and isinstance(prop.get("door_id"), str):
            door_ids.add(prop["door_id"])
    check_fixes(sc, cast, errors, warnings)
    narrator = sc.get("narrator")
    narrator = narrator.get("voice") if isinstance(narrator, dict) else None
    facing = {n: c.get("facing", "camera") for n, c in cast.items()}
    for n, st in enumerate(sc.get("script", []), 1):
        if not isinstance(st, dict):
            errors.append(f"step {n}: action must be a JSON object")
            continue
        do, who = st.get("do"), st.get("who")
        if not isinstance(do, str) or do not in ACTIONS:
            errors.append(f"step {n}: unknown action {do!r} (use {', '.join(ACTIONS)})")
            continue
        spec = ACTIONS[do]
        if spec["who"] and (not isinstance(who, str) or who not in cast):
            errors.append(f"step {n}: {who!r} is not in the cast")
            continue
        problems = []
        for key, par in spec["params"].items():
            value = st.get(key)
            if value is None:
                if par["required"]:
                    problems.append(f'{do} needs "{key}": {par["help"]}')
                continue
            if par["type"] == "enum":
                _enum(value, par["values"], key, problems)
            elif par["type"] == "point" and not _is_point(value):
                problems.append(f'"{key}" must be a spot [x, y] in metres')
            elif par["type"] == "number" and (not isinstance(value, (int, float)) or isinstance(value, bool)):
                problems.append(f'"{key}" must be a number')
            elif par["type"] == "voice" and (not isinstance(value, str) or value not in VOICES):
                problems.append(f"unknown voice {value}")
            elif par["type"] == "sfx" and not isinstance(value, str):
                problems.append(f'"{key}" must be text')
            elif par["type"] == "sfx" and lib["sfx"] and value not in lib["sfx"]:
                warnings.append(f"step {n}: no {value!r} sound in sfx/library.json "
                                "(python generate/make_sfx_library.py sfx --missing)")
            elif par["type"] == "clip" and (not isinstance(value, str) or value not in lib["clips"]):
                problems.append(f"no motion clip {value!r}: add it with python castforge.py motion add FILE "
                                "(or motion cmu SEARCH)")
            elif par["type"] in ("text", "audio", "bed", "door", "seat") and not isinstance(value, str):
                problems.append(f'"{key}" must be text')
            elif par["type"] == "prop":
                if not isinstance(value, str) or value not in props:
                    problems.append(f'"{key}" must be the id of a prop in this scene')
                else:
                    size = props[value].get("size") or (PROP_TYPES.get(props[value].get("make"), [None])[0])
                    if size and not acting.can_carry(list(size)):
                        warnings.append(f"step {n}: prop {value!r} looks too big to carry "
                                        f"({' x '.join(str(round(v, 2)) for v in size)} m)")
            elif par["type"] == "bool" and not isinstance(value, bool):
                problems.append(f'"{key}" must be true or false')
            elif par["type"] in ("target", "look") and not (
                    _is_point(value) or (isinstance(value, str) and
                    (value in cast or value == "camera" or (par["type"] == "look" and value in LOOK_DIRECTIONS)))):
                problems.append(f'"{key}" must be a cast member, "camera" or a spot [x, y]')
            elif par["type"] == "cast_list":
                names = [value] if isinstance(value, str) else value
                if not isinstance(names, list):
                    problems.append(f'"{key}" must be a cast member or a list of cast members')
                    continue
                for name in names:
                    if not isinstance(name, str) or name not in cast:
                        problems.append(f"{name!r} is not in the cast")
        errors += [f"step {n}: {msg}" for msg in problems]
        if do in ("walk", "enter", "exit"):
            if _is_point(st.get("to")):
                pos[who] = st["to"]
            facing[who] = None
            if do in ("enter", "exit") and st.get("door") not in door_ids:
                errors.append(f'step {n}: {do} needs "door": the id of a door prop')
        elif do == "open" and st.get("door") not in door_ids:
            errors.append(f'step {n}: open needs "door": the id of a door prop')
        elif do == "sit":
            seat = props.get(st.get("on") if isinstance(st.get("on"), str) else None, {})
            if seat.get("make") not in SEAT_TYPES and not seat.get("seat"):
                errors.append(f'step {n}: sit needs "on": the id of a chair, armchair, stool, bench, sofa or seat prop')
            else:
                pos[who] = seat.get("position", pos[who])
        elif do == "face":
            facing[who] = st.get("target")
        elif do == "gesture" and st.get("type") == "point" and st.get("target") is None:
            errors.append(f'step {n}: a point gesture needs "target"')
        elif do == "music" and not st.get("bed") and not st.get("stop"):
            errors.append(f'step {n}: music needs "bed" (or "stop": true)')
        elif do in ("say", "think", "narrate"):
            if not st.get("text") and not st.get("audio"):
                errors.append(f'step {n}: {do} needs "text" or "audio"')
            if st.get("audio") and not isinstance(st["audio"], str):
                errors.append(f"step {n}: audio must be a file path")
            elif st.get("audio") and not os.path.exists(os.path.join(folder, st["audio"])):
                errors.append(f"step {n}: audio file not found: {st['audio']}")
            if do == "narrate":
                if st.get("text") and not st.get("audio") and not (st.get("voice") or narrator):
                    errors.append(f'step {n}: narration needs a "voice" (or an episode "narrator": {{"voice": ...}})')
                continue
            if st.get("text") and not st.get("audio") and not cast[who].get("voice"):
                errors.append(f"step {n}: {who} speaks text but has no voice in the cast")
            if facing.get(who) == "camera" and len(cast) > 1:
                warnings.append(f"step {n}: {who} talks while facing the camera (add a face step first?)")
            for other, xy in pos.items():
                if other != who and _is_point(pos[who]) and _is_point(xy):
                    d = math.dist(pos[who], xy)
                    if d < 0.8:
                        warnings.append(f"step {n}: {who} is only {d:.1f} m from {other} (1.0-1.4 m looks natural)")
    for e in errors:
        print("ERROR:", e)
    for w in dict.fromkeys(warnings):
        print("warning:", w)
    if not errors:
        print("scene.json looks good" + (" (see warnings)" if warnings else ""))
    return len(errors)
