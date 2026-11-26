"""Turn a rendered CastForge episode into photoreal clips (pure, tested; no ffmpeg, no network).

CastForge renders a scene as a 3D picture: the staging is right, the acting is right, the timing is right,
and it looks like a 3D render. forgefilms can run Wan 2.2 image-to-video, which takes one still and a
sentence about what moves and gives back a few seconds of film. Pointing the second at the first is the
last arrow of the suite:

    graphic-novel  ->  castforge  ->  forgefilms
    the cast          the staging     the look

    python castforge.py real movies/santa_is_a_lie/act1

Two things make this worth writing down rather than typing prompts by hand.

**The cut is already there.** `shot.timeline.json` holds the shots the director cut: when each one starts,
whether it is wide or close, and who it is on. A camera shot is exactly what image-to-video wants - one
continuous take with no cut inside it - so the takes here are the director's, not a fixed slicing.

**The prompt is a fact, not a guess.** CastForge knows who is on screen, how old they are, what colour
their hair and their coat are, what the light is doing, whether it is snowing, and whether the person is
speaking aloud or thinking with their mouth shut. A person writing prompts has to remember all of that for
every shot and will quietly get one wrong; this reads it off the scene.

The hard limit is the model's, not ours: Wan 2.2's image-to-video was trained on 81 frames, which is 5.06
seconds at 16 fps. Ask for a minute in one pass and it drifts - the face changes, the coat changes colour,
the motion starts looping - so a take longer than that is split into windows, and each window after the
first starts from the last frame of the one before so the person does not change across the join.
"""
import json
import math
import os

from shared import handoff

try:                                    # the colour names the novel bridge already uses; one vocabulary
    from shared import cast as _cast
    HAIR_COLOURS = _cast.COLOURS
except Exception:                       # pragma: no cover - cast.py is beside this file
    HAIR_COLOURS = {}
# `cast.COLOURS` is a list of HAIR colours - it has no blue in it at all - so a navy coat came out
# "charcoal", which is the kind of quiet wrong word that makes a clip not match the shot before it.
# Clothes get the hair names plus the ones cloth actually comes in.
# "red" is in the hair list as an auburn brick; cloth red is a different red, and overriding it here is
# the point of a second table rather than a longer first one.
CLOTH_COLOURS = dict(HAIR_COLOURS, **{
    "red": "#c0272d",
    "navy": "#1f2a44", "blue": "#2f5ea8", "pale blue": "#9fc0e8", "teal": "#1f6f6b",
    "green": "#2f6d3a", "olive": "#6b6a3a", "mustard": "#c79a2e", "orange": "#d2762c",
    "maroon": "#5e1f26", "burgundy": "#4a1726", "pink": "#d98aa6", "purple": "#5b3b7a",
    "beige": "#d6c6a8", "khaki": "#9a8f68", "rust": "#9c4722",
})

FPS = 16              # Wan 2.2 i2v 14B runs at 16 fps (suite/forgefilms/scripts/wan_workflows.py FPS)
TRAINED = 81          # the frame count it was trained on: 5.06 s. Past this it drifts.
LEAST = 17            # ~1 s; a shorter window is not worth a pass of its own
STEP = 4              # Wan wants 4n+1 frames

# What a shot size is called in a photographed film. The names are core/schema.py SHOT_KINDS.
SHOT_WORDS = {
    "wide": "a wide shot", "medium": "a medium shot", "close": "a close-up",
    "two_shot": "a two shot", "over_shoulder": "an over-the-shoulder shot", "auto": "a medium shot",
}
# What the light is doing, in the words a photograph would use. The names are core/schema.py LIGHTING.
LIGHT_WORDS = {
    "auto": "", "classic": "",
    "day": "flat daylight", "golden_hour": "low golden evening sunlight",
    "overcast": "soft grey overcast light", "night": "night, dim cool light",
    "interior_warm": "warm indoor lamplight", "interior_cool": "cool indoor light",
    "candlelight": "candlelight, deep shadows", "moonlight": "moonlight, cold and blue",
    "noir": "hard single-source light, black shadows", "studio": "even studio light",
}
WEATHER_WORDS = {"snow": "snow falling", "rain": "rain falling"}
MOVE_WORDS = {
    "static": "the camera holds still", "push_in": "the camera pushes slowly in",
    "pull_out": "the camera pulls slowly back", "pan_left": "the camera pans slowly left",
    "pan_right": "the camera pans slowly right", "handheld": "a slight handheld drift",
}
DECADES = {2: "twenties", 3: "thirties", 4: "forties", 5: "fifties", 6: "sixties",
           7: "seventies", 8: "eighties", 9: "nineties"}
BUILD_WORDS = {"slim": "slim", "average": "", "athletic": "athletic", "heavy": "heavy-set", "muscular": "muscular"}


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# --- how long a window may be -------------------------------------------------------------------------
def frames_for(seconds, fps=FPS, cap=TRAINED):
    """The frame count Wan will accept for `seconds`: 4n+1, never past what it was trained on."""
    n = int(round(float(seconds) * fps)) + 1
    n = (n - 1) // STEP * STEP + 1
    return max(LEAST, min(cap, n))


def seconds_for(frames, fps=FPS):
    """The length to ask for so the frame count comes back out unchanged.

    forgefilms works the other way round - `frames = seconds * fps + 1`, snapped - so a shot list that
    says 4.9 s and a window that says 81 frames would disagree by a frame and the clip would not match
    the cut. Handing it the length of the frames we want keeps the two the same number."""
    return round((frames - 1) / fps, 4)


def takes(timeline):
    """One take per shot the director cut: when it starts, how long it holds, its size and who it is on.

    An image-to-video pass cannot contain a cut, so the camera's own cuts are the only honest boundaries.
    A render with no shot list at all (shots: "none") is one long take, which is still true."""
    duration = float(timeline.get("duration") or 0.0)
    cuts = sorted((s for s in (timeline.get("shots") or []) if isinstance(s, dict)),
                  key=lambda s: float(s.get("time") or 0.0))
    out = []
    for i, cut in enumerate(cuts):
        at = max(0.0, float(cut.get("time") or 0.0))
        until = float(cuts[i + 1].get("time") or 0.0) if i + 1 < len(cuts) else duration
        if until - at < 1.0 / FPS:
            continue                                   # a cut that lasts no frames is not a take
        out.append({"at": round(at, 3), "seconds": round(until - at, 3),
                    "kind": str(cut.get("kind") or "auto"), "on": [str(w) for w in (cut.get("on") or [])],
                    "move": str(cut.get("move") or "static"), "lens": cut.get("lens")})
    if not out and duration > 0:
        out = [{"at": 0.0, "seconds": round(duration, 3), "kind": "auto", "on": [],
                "move": "static", "lens": None}]
    return out


def windows(take, fps=FPS, cap=TRAINED):
    """A take cut into pieces the model can hold, split evenly rather than 5 s plus a stub.

    An even split is not tidiness: a 0.4 s tail is below what Wan will generate at all, and a window that
    short cannot be judged or re-rolled. Every window after the first carries on from the last frame of
    the one before, so nothing about the person changes across the join."""
    most = (cap - 1) / fps
    total = float(take["seconds"])
    pieces = max(1, math.ceil(round(total / most, 6)))
    each = total / pieces
    out, at = [], float(take["at"])
    for i in range(pieces):
        frames = frames_for(each, fps, cap)
        out.append({"at": round(at, 3), "seconds": seconds_for(frames, fps), "frames": frames,
                    "part": i + 1, "parts": pieces, "carries_on": i > 0})
        at += each
    return out


# --- what the camera is looking at ----------------------------------------------------------------------
GREY = 0.10            # chroma below this has no colour left in it worth naming


def _hsl(text):
    """(hue in degrees, chroma, lightness) for #rrggbb, or None if it is not a colour.

    Chroma - how far apart the brightest and darkest channels are - rather than HSL saturation, which
    runs away near white: #efefe9 has a saturation of 0.15 and is plainly white."""
    text = str(text or "").strip().lstrip("#")
    if len(text) != 6:
        return None
    try:
        r, g, b = (int(text[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return None
    high, low = max(r, g, b), min(r, g, b)
    light, span = (high + low) / 2, high - low
    if span < 1e-6:
        return 0.0, 0.0, light
    if high == r:
        hue = ((g - b) / span) % 6
    elif high == g:
        hue = (b - r) / span + 2
    else:
        hue = (r - g) / span + 4
    return hue * 60, span, light


def colour_word(value, among=None):
    """The nearest name for a hex colour, or None for anything else. `among` picks the list to use.

    Compared by hue first, not by how far apart the two are in plain RGB: a slate navy and a purple sit
    close together as numbers and are not the same colour to look at, and naming a coat purple when it is
    navy makes the clip disagree with the render it came from. Something with almost no colour in it is
    matched only against the other greys, by how light it is."""
    among = CLOTH_COLOURS if among is None else among
    want = _hsl(value)
    if want is None:
        return None
    hue, chroma, light = want
    best, best_gap = None, None
    for name, hexed in among.items():
        if name in ("gray", "blond"):                  # the same colour under a second spelling
            continue
        other = _hsl(hexed)
        if other is None:
            continue
        o_hue, o_chroma, o_light = other
        if (chroma < GREY) != (o_chroma < GREY):
            continue                                   # a grey is never the nearest thing to a red
        if chroma < GREY:
            gap = (light - o_light) ** 2
        else:
            turn = abs(hue - o_hue) % 360
            turn = min(turn, 360 - turn)
            gap = (turn / 180) ** 2 * 3 + (chroma - o_chroma) ** 2 + (light - o_light) ** 2 * 1.5
        if best_gap is None or gap < best_gap:
            best, best_gap = name, gap
    return best


def describe(design, name=None):
    """A person in the words a photograph would need: age, build, hair, beard, what they are wearing."""
    if not isinstance(design, dict):
        return name or "a person"
    sex = "woman" if str(design.get("gender")) == "female" else "man"
    try:
        age = int(design.get("age") or 0)
    except (TypeError, ValueError):
        age = 0
    build = BUILD_WORDS.get(str(design.get("build")), "")
    head = "a " + " ".join(w for w in (build, sex) if w)
    if age:
        head += f" of about {age}"          # an age reads better in a prompt than a decade or a pronoun
    looks = []
    hair = design.get("hair") if isinstance(design.get("hair"), dict) else {}
    hair_words = " ".join(w for w in (str(hair.get("length") or ""), str(hair.get("style") or ""),
                                      colour_word(hair.get("color"), HAIR_COLOURS) or "")
                          if w and w != "none")
    if hair_words:
        looks.append(f"{hair_words} hair")
    beard = str(design.get("beard") or "none")
    if beard not in ("none", ""):
        looks.append("a moustache" if beard == "moustache" else f"a {beard} beard")
    if looks:
        head += " with " + " and ".join(looks)
    outfit = design.get("outfit") if isinstance(design.get("outfit"), dict) else {}
    worn = []
    top, bottom = colour_word(outfit.get("top")), colour_word(outfit.get("bottom"))
    if top:
        worn.append(" ".join(w for w in ("a", top, str(outfit.get("style") or "").strip(), "top") if w))
    if bottom:
        worn.append(f"{bottom} {str(outfit.get('garment') or 'trousers')}")
    if worn:
        head += ", wearing " + " and ".join(worn)
    return head


def place(scene):
    """Where it is and what the light is doing, from the scene's own settings."""
    bits = []
    light = LIGHT_WORDS.get(str(scene.get("lighting") or "auto"), "")
    if light:
        bits.append(light)
    weather = scene.get("weather")
    kind = weather if isinstance(weather, str) else (weather or {}).get("type")
    if WEATHER_WORDS.get(kind):
        bits.append(WEATHER_WORDS[kind])
    return bits


def doing(lines, at, until):
    """What the people in the window are doing with their mouths, which is what gives a clip away.

    A `think` line is an inner voice: it is heard, and the mouth stays shut. Told to make someone speak
    over a thought, the model opens their mouth and the shot is unusable."""
    out, speaking, thinking = [], [], []
    for line in lines or []:
        start, end = float(line.get("start") or 0.0), float(line.get("end") or 0.0)
        if end <= at or start >= until:
            continue
        (thinking if str(line.get("kind")) == "think" else speaking).append(str(line.get("who") or "they"))
    for who in dict.fromkeys(speaking):
        out.append(f"{who} is speaking, lips moving")
    for who in dict.fromkeys(thinking):
        if who not in speaking:
            out.append(f"{who} is silent, thinking, mouth closed")
    return out


def lens_words(lens):
    """What a focal length does to a picture. Empty for the ordinary lenses, which need no saying."""
    try:
        mm = float(lens or 0)
    except (TypeError, ValueError):
        return ""
    if mm >= 85:
        return "shallow depth of field, the background softly out of focus"
    if 0 < mm <= 24:
        return "a wide lens, deep focus"
    return ""


def prompt(scene, designs, take, window, lines, present=()):
    """The sentence handed to image-to-video for one window, built from the scene rather than typed.

    A wide shot often has nobody in its `on` list - the director means "the room", not "an empty room" -
    so the people the scene actually holds are described anyway. Told nothing about them, the model is
    free to change their coat, or to remove them."""
    bits = [SHOT_WORDS.get(take["kind"], SHOT_WORDS["auto"])]
    people = take["on"] or [w for w in present]
    for who in people:
        bits.append(describe(designs.get(who), who))
    acts = doing(lines, window["at"], window["at"] + window["seconds"])
    bits.extend(acts)
    if not people and not acts:
        bits.append("nobody moves in frame")
    bits.extend(place(scene))
    bits.append(MOVE_WORDS.get(str(take.get("move") or "static"), MOVE_WORDS["static"]))
    lens = lens_words(take.get("lens"))
    if lens:
        bits.append(lens)
    if window["carries_on"]:
        bits.append("the shot continues without a cut")
    return ", ".join(b for b in bits if b)


# --- the whole episode -------------------------------------------------------------------------------
def plan(episode, read=_read, exists=os.path.exists):
    """Every window of every scene: where its still comes from, how long it runs, what it should look like.

    `read` and `exists` are passed in so this can be tested without a rendered episode to hand."""
    scene = read(os.path.join(episode, "scene.json"))
    timeline = read(os.path.join(episode, "episode.timeline.json"))
    designs = _designs(episode, scene, read, exists)
    rows, missing, res = [], [], None
    for n, sid in enumerate(handoff.order(timeline), start=1):
        folder = handoff.scene_folder(episode, n, sid)
        shot_timeline = os.path.join(folder, "shot.timeline.json")
        if not exists(shot_timeline):
            missing.append(sid)
            continue
        got = read(shot_timeline)
        res = res or (list(got.get("resolution") or []) or None)
        settings = _settings(scene, sid)
        for t, take in enumerate(takes(got), start=1):
            for window in windows(take):
                rows.append({
                    "id": f"{sid}_{t}" + (f"_{window['part']}" if window["parts"] > 1 else ""),
                    "scene": sid, "video": os.path.join(folder, "shot.mp4"),
                    "at": window["at"], "seconds": window["seconds"], "frames": window["frames"],
                    "carries_on": window["carries_on"], "kind": take["kind"], "on": take["on"],
                    "move": take["move"],
                    "motion": prompt(settings, designs, take, window, got.get("lines"),
                                     present=sorted(_present(scene, sid))),
                })
    return {"episode": episode, "title": str(scene.get("title") or os.path.basename(episode)),
            "shots": rows, "missing": missing, "fps": FPS, "res": res or [480, 270]}


def _present(scene, sid):
    """Who is in that scene: the episode cast plus whoever the scene itself adds."""
    names = set(scene.get("cast") or {})
    for part in (scene.get("scenes") or []):
        if isinstance(part, dict) and part.get("id") == sid:
            names |= set(part.get("cast") or {})
    return names


def _settings(scene, sid):
    """A scene's own settings with the episode's defaults under them."""
    out = {k: v for k, v in scene.items() if not isinstance(v, (list, dict)) or k in ("weather",)}
    for part in (scene.get("scenes") or []):
        if isinstance(part, dict) and part.get("id") == sid:
            out.update({k: v for k, v in part.items() if k not in ("script", "cast", "props", "scenes")})
    return out


def _designs(episode, scene, read, exists):
    """Every cast member's design, read from the film's characters folder."""
    out = {}
    for name, entry in (scene.get("cast") or {}).items():
        path = (entry or {}).get("character") if isinstance(entry, dict) else None
        if not isinstance(path, str):
            continue
        design = os.path.normpath(os.path.join(episode, path.replace(".blend", ".design.json")))
        if exists(design):
            try:
                out[name] = read(design)
            except (OSError, ValueError):
                pass                                   # a design we cannot read is a name we still know
    return out


def shot_list(plan_):
    """The SHOTS.json forgefilms' `wan_workflows.py` reads: id, still, seconds and the motion sentence."""
    return {"title": plan_["title"],
            "note": f"Made by castforge from {plan_['episode']}: one entry per image-to-video window.",
            "shots": [{"id": r["id"], "still": r["id"], "seconds": r["seconds"], "motion": r["motion"],
                       "place": r["scene"], "line": None}
                      for r in plan_["shots"]]}


def stills(plan_):
    """Which frame each window starts from: (the rendered shot, the second to grab, the still's name).

    Only the first window of a take belongs to the render. The rest carry on from the last frame of the
    clip before, which is the whole point of splitting on frames instead of on time."""
    return [(r["video"], r["at"], r["id"]) for r in plan_["shots"] if not r["carries_on"]]


def provisional(plan_):
    """The same, for the windows that would rather have the last frame of the clip before them.

    That frame does not exist until the first pass has run on a GPU, and a workflow cannot be built
    without a still at all - so every window gets one from the render, and `carried()` says which of
    them to replace afterwards. Starting a second window from the render again is not wrong, it just
    puts the photoreal look back to a 3D frame at the join instead of carrying it through."""
    return [(r["video"], r["at"], r["id"]) for r in plan_["shots"] if r["carries_on"]]


def carried(plan_):
    """(the window that continues, the window it continues from) for every join."""
    out, previous = [], None
    for row in plan_["shots"]:
        if row["carries_on"] and previous:
            out.append((row["id"], previous))
        previous = row["id"]
    return out


def check(plan_):
    """Plain-language problems with a plan, or an empty list."""
    bad = []
    if plan_["missing"]:
        bad.append("not rendered yet: " + ", ".join(plan_["missing"]) + " (render the episode first)")
    if not plan_["shots"]:
        bad.append("nothing to convert: this episode has no rendered shots")
    for row in plan_["shots"]:
        if row["frames"] > TRAINED:
            bad.append(f"{row['id']} asks for {row['frames']} frames; Wan 2.2 holds {TRAINED}")
        if not row["motion"]:
            bad.append(f"{row['id']} has no motion sentence")
    return bad


# --- the step before the clip: making the still itself real -----------------------------------------------
# Image-to-video ANIMATES the picture it is given; it does not restyle it. Hand it a 3D render and the clip
# is a moving 3D render - which is exactly what the first run showed: the wide shot gained real wood and
# cloth, and the close-up's face stayed computer-generated. So the render is made photographic FIRST, by a
# photoreal checkpoint running image-to-image over it, and the clip is made from that.
#
#   3D render  ->  still_graph (RealVisXL, image-to-image)  ->  a photograph  ->  Wan i2v  ->  a real clip
#
# The one number that matters is how far the image is allowed to move. Too little and the plastic look
# survives; too much and it is somebody else in a different room.
REAL_WORDS = ("photograph, real film still, natural skin with pores and fine lines, real woven fabric, "
              "individual hair strands, natural light falloff, shallow depth of field, 35mm film grain")
NOT_REAL = ("3d render, cgi, computer graphics, video game, unreal engine, blender, plastic skin, waxy "
            "skin, smooth plastic face, doll, mannequin, toy, clay, illustration, painting, cartoon, "
            "anime, text, watermark, extra fingers, deformed hands, deformed face")
REAL_CHECKPOINT = "RealVisXL_V5.0_Lightning_fp16.safetensors"
REAL_STEPS, REAL_CFG = 6, 1.8        # a Lightning checkpoint: few steps, almost no guidance
REAL_AREA = 1024 * 576               # what SDXL was trained near; a 480x270 render is far below it

# How far each kind of shot may be moved. This is the finding from the first run, written down: a wide
# shot has room to be re-imagined and badly needs it, while a face must stay the same person - and a face
# is where a render gives itself away. One number for the whole film would get one of the two wrong.
DENOISE = {"wide": 0.58, "medium": 0.5, "two_shot": 0.5, "over_shoulder": 0.46, "close": 0.42, "auto": 0.5}


def denoise_for(kind):
    """How far this shot may be moved away from the render it came from."""
    return DENOISE.get(str(kind), DENOISE["auto"])


def real_size(width, height, area=REAL_AREA, step=8):
    """The still's own shape at the size the photoreal model works at, both sides a multiple of `step`.

    A blocking render is 480x270. Asking a model trained near 1024x576 to make a photograph out of a
    thumbnail gives a thumbnail back; it has to be scaled up before it is re-imagined, not after."""
    width, height = max(1, int(width)), max(1, int(height))
    scale = (area / (width * height)) ** 0.5
    return max(step, int(width * scale) // step * step), max(step, int(height * scale) // step * step)


def still_prompt(scene, designs, take, present=()):
    """What the photograph shows. No motion words: a still does not move, and asking for movement in one
    is how a face ends up mid-blur."""
    bits = [SHOT_WORDS.get(take["kind"], SHOT_WORDS["auto"])]
    for who in (take["on"] or list(present)):
        bits.append(describe(designs.get(who), who))
    bits.extend(place(scene))
    lens = lens_words(take.get("lens"))
    if lens:
        bits.append(lens)
    bits.append(REAL_WORDS)
    return ", ".join(b for b in bits if b)


def still_graph(image, prompt, width, height, seed=1, denoise=0.5, checkpoint=REAL_CHECKPOINT,
                prefix="real/out", steps=REAL_STEPS, cfg=REAL_CFG, negative=NOT_REAL):
    """A ComfyUI graph that turns one rendered frame into a photograph of the same shot.

    Image-to-image, not text-to-image: the render IS the composition, the staging and the acting, and all
    of that is already right. Only the look is wrong."""
    return {
        "model": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
        "img": {"class_type": "LoadImage", "inputs": {"image": image}},
        "fit": {"class_type": "ImageScale", "inputs": {"image": ["img", 0], "width": int(width),
                                                       "height": int(height), "upscale_method": "lanczos",
                                                       "crop": "disabled"}},
        "lat": {"class_type": "VAEEncode", "inputs": {"pixels": ["fit", 0], "vae": ["model", 2]}},
        "pos": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["model", 1]}},
        "neg": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["model", 1]}},
        "ks": {"class_type": "KSampler",
               "inputs": {"model": ["model", 0], "seed": int(seed), "steps": int(steps), "cfg": float(cfg),
                          "sampler_name": "dpmpp_sde", "scheduler": "karras", "positive": ["pos", 0],
                          "negative": ["neg", 0], "latent_image": ["lat", 0], "denoise": float(denoise)}},
        "dec": {"class_type": "VAEDecode", "inputs": {"samples": ["ks", 0], "vae": ["model", 2]}},
        "save": {"class_type": "SaveImage", "inputs": {"images": ["dec", 0], "filename_prefix": prefix}},
    }


def real_stills(plan_, scene, designs, size=(480, 270), seed=1, carried=False):
    """One realism job per still: which file to re-imagine, with what words, and how far it may move.

    By default only the stills that come from the render: a window carrying on from the clip before it
    starts from a frame that is already a photograph, and running that through again would move it.
    `carried=True` includes them anyway, which is what a single pass needs - there is no previous clip
    yet, so those windows are holding a render frame too, and leaving them out would put a 3D frame in
    the middle of a photographed take."""
    takes = {r["id"]: r for r in plan_["shots"]}
    width, height = real_size(*size)
    out = []
    for video, at, name in (stills(plan_) + provisional(plan_) if carried else stills(plan_)):
        row = takes[name]
        take = {"kind": row["kind"], "on": row["on"], "move": row["move"], "lens": row.get("lens")}
        out.append({"id": name, "still": f"{name}.png", "width": width, "height": height,
                    "denoise": denoise_for(row["kind"]),
                    "prompt": still_prompt(_settings(scene, row["scene"]), designs, take,
                                           sorted(_present(scene, row["scene"]))),
                    "seed": seed, "at": at, "video": video})
    return out


def realism(episode, plan_=None, read=_read, exists=os.path.exists, seed=1, carried=True):
    """The realism jobs for a whole episode, with the scene, the cast and the render's size read for you."""
    plan_ = plan_ or plan(episode, read, exists)
    scene = read(os.path.join(episode, "scene.json"))
    return real_stills(plan_, scene, _designs(episode, scene, read, exists),
                       size=tuple(plan_.get("res") or (480, 270)), seed=seed, carried=carried)
