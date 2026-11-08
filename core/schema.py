"""The scene vocabulary: every action, parameter, preset and asset name CastForge understands, in one place.

`castforge.py check` validates scene.json with it, the web app builds its forms from it (/api/schema), the prop
factory takes sizes and materials from it, and tests check the Gemini prompt and the presets against it.
Plain Python, importable from Blender too.
"""
import json
import math
import os

from blender import acting
from core import config, finish, media

# --- names ------------------------------------------------------------------------------------------------
_LANG = {"a": "American English", "b": "British English", "h": "Hindi", "e": "Spanish", "f": "French",
         "i": "Italian", "p": "Portuguese (Brazil)"}
VOICES = {v: f"{_LANG[v[0]]}, {'female' if v[1] == 'f' else 'male'}" for v in """
    af_heart af_alloy af_aoede af_bella af_jessica af_kore af_nicole af_nova af_river af_sarah af_sky
    am_adam am_echo am_eric am_fenrir am_liam am_michael am_onyx am_puck am_santa
    bf_alice bf_emma bf_isabella bf_lily bm_daniel bm_fable bm_george bm_lewis
    hf_alpha hf_beta hm_omega hm_psi ef_dora em_alex em_santa ff_siwis if_sara im_nicola pf_dora pm_alex pm_santa
    """.split()}
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
def p(kind, help_, required=False, default=None, values=None):
    out = {"type": kind, "help": help_, "required": required}
    if default is not None:
        out["default"] = default
    if values is not None:
        out["values"] = list(values)
    return out


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
               "params": {"shot": p("enum", "shot size", True, values=SHOT_KINDS),
                          "on": p("cast_list", "who the shot is on"),
                          "move": p("enum", "camera move", default="static", values=CAMERA_MOVES),
                          "lens": p("number", "lens in mm (empty: chosen for the shot)"),
                          "seconds": p("number", "how long (empty: until the next camera step)")}},
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
    "music": p("bed", "music for the whole scene: a library bed or a file"),
    "lighting": p("enum", "lighting mood", default="auto", values=LIGHTING),
    "weather": p("weather", 'falling snow or rain, e.g. "snow" or {"type": "snow", "amount": 0.5, "fog": 0.2}'),
    "look": p("enum", "cinematic lights and effects (standard quality and above)", default="cinematic",
              values=["cinematic", "plain"]),
    "shots": p("enum", "how the camera cuts", default="auto", values=SHOTS_MODES),
    "aspect": p("enum", "picture shape", default="16:9", values=ASPECTS),
    "set": p("enum", "3D set from the picture, or a flat backdrop", default="3d", values=["3d", "flat"]),
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


def library():
    """The sound library's names: footstep floors, effects and beds."""
    path = os.path.join(config.SFX_DIR, "library.json")
    try:
        lib = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return {"footsteps": [], "sfx": [], "beds": []}
    return {k: sorted(lib.get(k, {})) for k in ("footsteps", "sfx", "beds")}


def describe():
    """Everything the web app needs to build its forms (served as /api/schema)."""
    return {"actions": ACTIONS, "with": WITH_PREVIOUS, "scene": SCENE_KEYS, "finish": FINISH_SETTINGS,
            "props": {k: {"size": v[0], "material": v[1], "blocks": v[2], "help": v[3]} for k, v in PROP_TYPES.items()},
            "materials": list(MATERIALS), "voices": VOICES, "floors": FLOORS, "expressions": EXPRESSIONS,
            "gestures": GESTURES, "postures": POSTURES, "paces": PACES, "voice_fx": VOICE_FX, "grades": GRADES,
            "transitions": TRANSITIONS, "lighting": list(LIGHTING), "weather": WEATHER, "shots": SHOT_KINDS,
            "moves": CAMERA_MOVES, "qualities": QUALITIES, "aspects": ASPECTS, "seats": SEAT_TYPES,
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


def check_parsed(folder, sc):
    errors, warnings = [], []
    if not isinstance(sc, dict):
        print("ERROR: scene must be a JSON object")
        return 1
    lib = library()
    for key in ("background", "cast", "script"):
        if key not in sc:
            errors.append(f'missing "{key}"')
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
            elif par["type"] in ("text", "audio", "bed", "door", "seat") and not isinstance(value, str):
                problems.append(f'"{key}" must be text')
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
