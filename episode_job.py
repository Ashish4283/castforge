"""Render an episode scene by scene, then finish it (started in the background by `castforge.py episode`).

An episode folder's scene.json is either one scene, or an episode with a cast list and several scenes:

    {"cast":   {"Noelle": {"character": "characters/noelle.blend", "voice": "af_bella"}, ...},
     "floor": "wood", "quality": "blocking",                      <- defaults for every scene
     "title": {"text": "Santa is a Lie"}, "transition": "fade",   <- finishing (see core/finish.py)
     "scenes": [
        {"id": "street", "background": "sets/street.png", "floor": "concrete",
         "cast": {"Noelle": {"position": [-1, 0.5]}, "Maya": {"position": [-2, 0.3]}},
         "props": [...], "script": [...]},
        {"id": "cabin", ...}]}

A single scene is treated as an episode with one scene. Each scene is rendered by its own Blender process (only
its own characters and set are loaded, and all memory is freed when it ends) into scenes/NN_id/: shot.mp4,
shot.wav (its sound mix), shot.timeline.json (its lines and shots) and shot.blend. A scene renders again only
when its render key changes: the scene without its finishing settings, the quality, the render code, and the
files it reads (core/config.render_key). Then core/finish.py turns the shots into episode.mp4 with titles,
transitions, grade, subtitles, chapters, a poster and mastered sound.

    python episode_job.py FOLDER [--quality blocking|draft|standard|final|ultra]
                                 [--storyboard] [--finish-only] [--prepare]
    --storyboard   one still per shot -> scenes/NN_id/storyboard.jpg and FOLDER/storyboard.jpg (no render)
    --finish-only  redo only the finishing (the shots must be up to date)
    --prepare      write each scene's scene.json without rendering (for test frames)
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from core import config, finish, storyboard  # noqa: E402
from core.schema import FINISH_KEYS  # noqa: E402

folder = os.path.abspath(sys.argv[1])
quality = sys.argv[sys.argv.index("--quality") + 1] if "--quality" in sys.argv else None
STORYBOARD, FINISH_ONLY = "--storyboard" in sys.argv, "--finish-only" in sys.argv
spec = json.load(open(os.path.join(folder, "scene.json"), encoding="utf-8"))


def log(*a):
    print("CF:", *a, flush=True)


def absolute(p):
    return p if os.path.isabs(p) else os.path.normpath(os.path.join(folder, p))


def is_file(name):
    """Sound-library names (e.g. "cabin_night") stay as they are; only file paths are made absolute."""
    return bool(name) and bool(os.path.splitext(name)[1])


def expand():
    """[(scene id, scene folder, scene dict with absolute paths)] in film order."""
    if "scenes" in spec:
        library = spec.get("cast", {})
        defaults = {k: v for k, v in spec.items() if k not in ("cast", "scenes")}
        parts = spec["scenes"]
    else:
        library, defaults, parts = {}, {}, [spec]
    out = []
    for i, sc in enumerate(parts, 1):
        sid = f"{i:02d}_{sc.get('id', 'scene')}"
        scene = dict(defaults)
        scene.update({k: v for k, v in sc.items() if k != "cast"})
        scene["cast"] = {}
        for name, entry in sc.get("cast", {}).items():
            if name not in library and "character" not in entry:
                sys.exit(f"CF: FAILED scene {sid}: {name} is not in the episode cast")
            scene["cast"][name] = {**library.get(name, {}), **entry}
        # paths in the episode file are relative to the episode folder; the scene lives in a subfolder
        if scene.get("background"):
            scene["background"] = absolute(scene["background"])
        if is_file(scene.get("ambience")):
            scene["ambience"] = absolute(scene["ambience"])
        music = scene.get("music")
        if isinstance(music, dict) and is_file(music.get("bed")):
            music["bed"] = absolute(music["bed"])
        elif isinstance(music, str) and is_file(music):
            scene["music"] = absolute(music)
        for c in scene["cast"].values():
            c["character"] = absolute(c["character"])
        for p in scene.get("props", []):
            if p.get("file"):
                p["file"] = absolute(p["file"])
        for st in scene.get("script", []):
            if st.get("audio"):
                st["audio"] = absolute(st["audio"])
            if st.get("do") == "music" and is_file(st.get("bed")):
                st["bed"] = absolute(st["bed"])
        out.append((sid, os.path.join(folder, "scenes", sid), scene))
    return out


def blender_scene(scene_file, out, extra=(), key=None):
    cmd = [config.BLENDER, "-b", "-y", "--python-exit-code", "1", "-P", os.path.join(ROOT, "blender", "scene_kit.py"), "--",
           "--scene", scene_file, "--out", out, *extra, *(["--render-key", key] if key else [])]
    if quality:
        cmd += ["--quality", quality]
    return subprocess.run(cmd, stdout=sys.stdout, stderr=subprocess.STDOUT).returncode


def shot_quality(d):
    try:
        return json.load(open(os.path.join(d, "shot.timeline.json"), encoding="utf-8")).get("quality")
    except (OSError, ValueError):
        return None


scenes = expand()
if not scenes:
    sys.exit('CF: FAILED episode "scenes" must contain at least one scene')
n = len(scenes)
done = []
for i, (sid, d, scene) in enumerate(scenes, 1):
    os.makedirs(d, exist_ok=True)
    scene_file = os.path.join(d, "scene.json")
    text = json.dumps(scene, indent=1)
    if not os.path.exists(scene_file) or open(scene_file, encoding="utf-8").read() != text:
        open(scene_file, "w", encoding="utf-8").write(text)
    if "--prepare" in sys.argv:          # only write the scene files (for test frames), render nothing
        log(f"prepared {scene_file}")
        continue
    q = quality or scene.get("quality", "blocking")
    if FINISH_ONLY:
        q = shot_quality(d) or q
    key = config.render_key(scene, q, d, FINISH_KEYS)
    stamp, shot = os.path.join(d, "shot.sha256"), os.path.join(d, "shot.mp4")
    log(f"scene {i}/{n} {sid}")
    if STORYBOARD:
        if blender_scene(scene_file, shot, ["--storyboard"]) != 0:
            sys.exit(f"CF: FAILED storyboard of scene {sid} (see the lines above)")
        storyboard.contact_sheet([(f"{i}. {sid[3:].replace('_', ' ').title()}", storyboard.scene_tiles(d))],
                                 os.path.join(d, "storyboard.jpg"))
    else:
        outputs = [shot, os.path.join(d, "shot.wav"), os.path.join(d, "shot.timeline.json")]
        fresh = all(os.path.exists(f) for f in outputs + [stamp]) and open(stamp).read() == key
        if FINISH_ONLY and not fresh:
            sys.exit(f"CF: FAILED scene {sid} changed since it was rendered (or was never rendered): "
                     "render the episode first")
        if fresh:
            log(f"scene {sid} unchanged: reusing its shot")
        else:
            if blender_scene(scene_file, shot, key=key) != 0 or not all(os.path.exists(f) for f in outputs):
                sys.exit(f"CF: FAILED scene {sid} (see the lines above); run the episode again to retry from here")
            open(stamp, "w").write(key)
    done.append((sid, d, scene))

if "--prepare" in sys.argv:
    sys.exit(0)
if STORYBOARD:
    sections = [(f"{k}. {sid[3:].replace('_', ' ').title()}", storyboard.scene_tiles(d))
                for k, (sid, d, _) in enumerate(done, 1)]
    storyboard.contact_sheet(sections, os.path.join(folder, "storyboard.jpg"))
    log("storyboard ready", os.path.join(folder, "storyboard.jpg"))
    sys.exit(0)

log("finishing")
finishing = {k: v for k, v in spec.items() if k in FINISH_KEYS}
finishing["cast"] = spec.get("cast", {})
parts = spec["scenes"] if "scenes" in spec else [spec]
info = []
for (sid, d, scene), part in zip(done, parts):
    entry = {"dir": d, "id": sid[3:]}
    entry.update({k: part[k] for k in ("chapter", "transition", "transition_seconds", "grade", "vignette", "grain")
                  if k in part and "scenes" in spec})
    if scene.get("look", "cinematic") == "cinematic" and "grain" not in entry and "grain" not in finishing:
        entry["grain"] = 0.2 if (shot_quality(d) or "blocking") not in ("blocking", "draft") else 0.0
    info.append(entry)
try:
    finish.finish(folder, info, finishing, shot_quality(done[0][1]) or quality or "blocking", log=log)
except Exception as e:                     # a plain line for `status`; the details stay in render.log
    import traceback
    traceback.print_exc()
    sys.exit(f"CF: FAILED finishing the episode: {e}")
