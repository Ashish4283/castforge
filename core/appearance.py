"""Every shape a character's face and body can be given, in one table.

A "variable" is one thing a person can change (jaw width, cheekbones, shoulders), moved by a slider from
-1 to +1. Each one names the MPFB morph targets it leans on: one list for the + side, one for the -, already
spread over both sides of the body where the feature is paired (eyes, cheeks, arms). 0 means "leave it".

The same table serves both ways of making a face:
  * a photo: `build_character.py` solves for the variables that best match the landmarks (it needs the
    targets as columns, hence `photo_vars`),
  * by hand: a design's `face.*` and `body.*` values are applied straight through `targets_for`.
Keeping one table means a slider added here is immediately something the photo fit can also reach for.

Pure Python, no Blender: `core/schema.py` builds the app's form from it and the tests check it.
"""

# --- the table ----------------------------------------------------------------------------------------------
# key -> (group, plus targets, minus targets, help). A name with "{s}" is paired: it becomes l-… and r-….
_PAIR = "{s}"


def _lr(target):
    return [f"l-{target}", f"r-{target}"]


def _var(base, plus=None, minus=None, pair=False):
    """The usual shape: one target for the + side and one for the -, optionally on both sides of the body."""
    p, m = plus or f"{base}-incr", minus or f"{base}-decr"
    return (_lr(p), _lr(m)) if pair else ([p], [m])


FACE = {
    # --- the shape of the head ---
    "head_width": ("Head", *_var("head-scale-horiz"), "narrow to wide across the skull"),
    "head_height": ("Head", *_var("head-scale-vert"), "short to long from crown to chin"),
    "head_depth": ("Head", *_var("head-scale-depth"), "flat to deep front to back"),
    "face_fat": ("Head", *_var("head-fat"), "lean to full in the face"),
    "forehead_height": ("Head", *_var("forehead-scale-vert"), "low to high forehead"),
    "brow_ridge": ("Head", ["forehead-trans-forward"], ["forehead-trans-backward"],
                   "how far the brow ridge stands out"),
    "temples": ("Head", *_var("forehead-temple"), "narrow to wide at the temples"),
    "neck_thickness": ("Head", *_var("neck-scale-horiz"), "thin to thick neck"),

    # --- jaw and chin ---
    "jaw_width": ("Jaw and chin", *_var("chin-width"), "narrow to wide jaw"),
    "jawline": ("Jaw and chin", *_var("chin-bones"), "soft to sharp along the jawbone"),
    "chin_height": ("Jaw and chin", *_var("chin-height"), "short to long chin"),
    "chin_forward": ("Jaw and chin", *_var("chin-prognathism"), "receding to jutting chin"),
    "chin_prominent": ("Jaw and chin", *_var("chin-prominent"), "flat to pointed chin"),
    "chin_cleft": ("Jaw and chin", *_var("chin-cleft"), "a dimple in the chin"),

    # --- cheeks ---
    "cheekbones": ("Cheeks", *_var("cheek-bones", pair=True), "flat to high, sharp cheekbones"),
    "cheek_fullness": ("Cheeks", *_var("cheek-volume", pair=True), "hollow to full cheeks"),
    "cheek_inner": ("Cheeks", *_var("cheek-inner", pair=True), "hollow to full beside the nose"),

    # --- eyes and brows ---
    "eye_size": ("Eyes and brows", *_var("eye-scale", pair=True), "small to large eyes"),
    "eye_spacing": ("Eyes and brows", _lr("eye-trans-out"), _lr("eye-trans-in"), "close set to wide set"),
    "eye_height": ("Eyes and brows", _lr("eye-trans-up"), _lr("eye-trans-down"), "low to high in the face"),
    "eye_opening": ("Eyes and brows", *_var("eye-height2", pair=True), "narrow to wide open"),
    "eye_tilt": ("Eyes and brows", _lr("eye-corner2-up"), _lr("eye-corner2-down"),
                 "the outer corner down or up"),
    "eye_depth": ("Eyes and brows", _lr("eye-push1-out"), _lr("eye-push1-in"), "deep set to prominent"),
    "eye_bags": ("Eyes and brows", *_var("eye-bag", pair=True), "smooth to heavy under the eye"),
    "eyefold": ("Eyes and brows", _lr("eye-eyefold-up"), _lr("eye-eyefold-down"), "the lid fold, low or high"),
    "brow_height": ("Eyes and brows", ["eyebrows-trans-up"], ["eyebrows-trans-down"], "low to high brows"),
    "brow_angle": ("Eyes and brows", ["eyebrows-angle-up"], ["eyebrows-angle-down"],
                   "the outer end down or up"),

    # --- nose ---
    "nose_width": ("Nose", *_var("nose-scale-horiz"), "narrow to wide nose"),
    "nose_length": ("Nose", *_var("nose-scale-vert"), "short to long nose"),
    "nose_depth": ("Nose", *_var("nose-scale-depth"), "how far it stands off the face"),
    "nose_bridge": ("Nose", *_var("nose-hump"), "a dip or a hump on the bridge"),
    "nose_curve": ("Nose", ["nose-curve-convex"], ["nose-curve-concave"], "the profile, scooped or arched"),
    "nostril_width": ("Nose", *_var("nose-nostrils-width"), "narrow to wide nostrils"),
    "nose_tip": ("Nose", ["nose-point-up"], ["nose-point-down"], "the tip, turned down or up"),
    "nose_tip_width": ("Nose", *_var("nose-point-width"), "a fine or a bulbous tip"),
    "nose_flaring": ("Nose", *_var("nose-flaring"), "how far the nostrils flare"),

    # --- mouth and lips ---
    "mouth_width": ("Mouth and lips", *_var("mouth-scale-horiz"), "small to wide mouth"),
    "lip_height": ("Mouth and lips", *_var("mouth-scale-vert"), "thin to tall between the lips"),
    "upper_lip": ("Mouth and lips", *_var("mouth-upperlip-volume"), "thin to full upper lip"),
    "lower_lip": ("Mouth and lips", *_var("mouth-lowerlip-volume"), "thin to full lower lip"),
    "lip_corners": ("Mouth and lips", ["mouth-angles-up"], ["mouth-angles-down"],
                    "the resting corners, down or up"),
    "cupids_bow": ("Mouth and lips", *_var("mouth-cupidsbow"), "a flat or a pronounced cupid's bow"),
    "philtrum": ("Mouth and lips", *_var("mouth-philtrum-volume"), "the groove above the lip"),
    "mouth_height": ("Mouth and lips", ["mouth-trans-up"], ["mouth-trans-down"], "low to high in the face"),
    "laugh_lines": ("Mouth and lips", ["mouth-laugh-lines-out"], ["mouth-laugh-lines-in"],
                    "the lines from nose to mouth"),

    # --- ears ---
    "ear_size": ("Ears", *_var("ear-scale", pair=True), "small to large ears"),
    "ear_stickout": ("Ears", *_var("ear-wing", pair=True), "flat to the head, or standing out"),
    "ear_lobes": ("Ears", *_var("ear-lobe", pair=True), "attached to hanging lobes"),
}

BODY = {
    "shoulders": ("Frame", *_var("measure-shoulder-dist"), "narrow to broad shoulders"),
    "chest": ("Frame", *_var("measure-bust-circ"), "the chest, round the fullest part"),
    "waist": ("Frame", *_var("measure-waist-circ"), "slim to thick at the waist"),
    "hips": ("Frame", *_var("measure-hips-circ"), "narrow to wide hips"),
    "neck": ("Frame", *_var("measure-neck-circ"), "a thin or a thick neck"),
    "torso_length": ("Frame", *_var("torso-scale-vert"), "short to long in the body"),
    "v_taper": ("Frame", *_var("torso-vshape"), "straight, or shoulders down to a narrow waist"),

    "chest_muscle": ("Muscle", *_var("torso-muscle-pectoral"), "the pectorals"),
    "back_muscle": ("Muscle", *_var("torso-muscle-dorsi"), "the lats, across the back"),
    "shoulder_muscle": ("Muscle", *_var("upperarm-shoulder-muscle", pair=True), "the deltoids"),
    "arm_muscle": ("Muscle", *_var("upperarm-muscle", pair=True), "the upper arms"),
    "forearm_muscle": ("Muscle", *_var("lowerarm-muscle", pair=True), "the forearms"),
    "leg_muscle": ("Muscle", *_var("upperleg-muscle", pair=True), "the thighs"),
    "calf_muscle": ("Muscle", *_var("lowerleg-muscle", pair=True), "the calves"),
    "abs": ("Muscle", *_var("stomach-tone"), "soft to a hard, defined stomach"),

    "belly": ("Weight", *_var("stomach-pregnant"), "flat to a round belly"),
    "arm_fat": ("Weight", *_var("upperarm-fat", pair=True), "the softness of the arms"),
    "leg_fat": ("Weight", *_var("upperleg-fat", pair=True), "the softness of the thighs"),
    "buttocks": ("Weight", *_var("buttocks-volume"), "flat to full"),
    "double_chin": ("Weight", *_var("neck-double"), "the softness under the jaw"),
}

# whole-head shapes: one target each, so they are a choice rather than a slider
HEAD_SHAPES = ["none", "oval", "round", "square", "rectangular", "triangular", "invertedtriangular", "diamond"]

# hair and eyebrows that are installed with the asset library (checked by tests against what the build names)
HAIR_STYLES = {
    "none": "none",          # "none" is a real answer: no hair at all, not "nothing chosen"
    "short": "short01", "crew_cut": "short03", "messy": "cortu_short_messy_hair", "afro": "afro01",
    "mid_length": "culturalibre_hair_05", "bangs": "cortu_straight_bangs", "shaggy": "cortu_shaggy_green_hair",
    "long": "long01", "long_loose": "o4saken_long01", "ponytail": "ponytail01", "bun": "rehmanpolanski_hair_bun_brown",
    "bob": "toigo_blunt_bob", "inverted_bob": "toigo_inverted_bob", "bobcut": "littleright_bobcut_hair",
    "braid": "braid01", "french_braid": "elvs_french_braid_variation", "double_braid": "elvs_double_mh_braid",
}
EYEBROWS = {f"style_{n}": f"eyebrow{n:03d}" for n in range(1, 13)}

RANGE = (-1.0, 1.0)


# --- using the table -----------------------------------------------------------------------------------------
def groups(table):
    """The variables of one table in order, grouped by the heading they belong under."""
    out = {}
    for key, (group, *_rest) in table.items():
        out.setdefault(group, []).append(key)
    return out


def clamp(value):
    """A slider value as a number between -1 and +1 (anything unreadable is 0: leave the feature alone)."""
    try:
        return min(max(float(value), RANGE[0]), RANGE[1])
    except (TypeError, ValueError):
        return 0.0


def targets_for(design):
    """{morph target: weight} for one design's face.* and body.* sliders.

    A positive value leans on the + targets, a negative one on the -, both by how far the slider went. A
    variable left at 0 (or missing, or not a number) names no target at all, so an untouched design asks for
    nothing and the body is whatever the build already made it."""
    out = {}
    for part, table in (("face", FACE), ("body", BODY)):
        asked = (design or {}).get(part) or {}
        if not isinstance(asked, dict):
            continue
        for key, (_group, plus, minus, _help) in table.items():
            value = clamp(asked.get(key))
            if not value:
                continue
            for name in (plus if value > 0 else minus):
                out[name] = out.get(name, 0.0) + abs(value)
    return out


def head_shape_target(design):
    """The one whole-head shape target a design asks for, or None."""
    shape = ((design or {}).get("face") or {}).get("head_shape")
    return f"head-{shape}" if shape and shape != "none" and shape in HEAD_SHAPES else None


def photo_vars():
    """The face variables the photo fit solves for: [(name, plus targets, minus targets)].

    Deliberately NOT the whole table above. The fit has one front-on photo to go on, so it only reaches for
    what that photo can actually show; widening it gives the solver freedom it cannot support and changes
    every face already built from a photo. Sliders a person sets by hand are applied on top of this, so the
    two can grow apart without either disturbing the other."""
    out = [(b, [f"{b}-incr"], [f"{b}-decr"]) for b in ("head-scale-horiz", "head-scale-vert", "head-fat")]
    out += [(s, [s], []) for s in ("head-oval", "head-round", "head-square", "head-triangular",
                                   "head-invertedtriangular", "head-diamond", "head-rectangular")]
    out += [(b, [f"{b}-incr"], [f"{b}-decr"]) for b in
            ("nose-scale-horiz", "nose-scale-vert", "nose-width1", "nose-width2", "nose-width3",
             "nose-nostrils-width", "nose-point-width", "nose-flaring", "mouth-scale-horiz",
             "mouth-scale-vert", "mouth-upperlip-height", "mouth-lowerlip-height", "mouth-upperlip-width",
             "mouth-lowerlip-width", "chin-width", "chin-height", "chin-bones", "forehead-scale-vert")]
    out += [("nose-trans-vert", ["nose-trans-up"], ["nose-trans-down"]),
            ("mouth-trans-vert", ["mouth-trans-up"], ["mouth-trans-down"]),
            ("mouth-angles", ["mouth-angles-up"], ["mouth-angles-down"]),
            ("eyebrows-trans-vert", ["eyebrows-trans-up"], ["eyebrows-trans-down"]),
            ("eyebrows-angle", ["eyebrows-angle-up"], ["eyebrows-angle-down"]),
            ("eye-scale", _lr("eye-scale-incr"), _lr("eye-scale-decr")),
            ("eye-trans-horiz", _lr("eye-trans-out"), _lr("eye-trans-in")),
            ("eye-trans-vert", _lr("eye-trans-up"), _lr("eye-trans-down")),
            ("eye-height2", _lr("eye-height2-incr"), _lr("eye-height2-decr")),
            ("eye-corner1", _lr("eye-corner1-up"), _lr("eye-corner1-down")),
            ("eye-corner2", _lr("eye-corner2-up"), _lr("eye-corner2-down")),
            ("cheek-bones", _lr("cheek-bones-incr"), _lr("cheek-bones-decr")),
            ("cheek-volume", _lr("cheek-volume-incr"), _lr("cheek-volume-decr"))]
    return out


def every_target():
    """Every target name the table can ask for: what a build (or a test) checks is really installed."""
    names = set()
    for table in (FACE, BODY):
        for _key, (_g, plus, minus, _h) in table.items():
            names |= set(plus) | set(minus)
    return names | {f"head-{s}" for s in HEAD_SHAPES if s != "none"}
