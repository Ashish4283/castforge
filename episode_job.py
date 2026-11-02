"""Render an episode scene by scene (started in the background by `castforge.py episode`).

An episode folder's scene.json is either one scene, or an episode with a cast list and several scenes:

    {"cast":   {"Noelle": {"character": "characters/noelle.blend", "voice": "af_bella"}, ...},
     "floor": "wood", "quality": "blocking",                      <- defaults for every scene
     "scenes": [
        {"id": "street", "background": "sets/street.png", "floor": "concrete",
         "cast": {"Noelle": {"position": [-1, 0.5]}, "Maya": {"position": [-2, 0.3]}},
         "props": [...], "script": [...]},
        {"id": "cabin", ...}]}

Each scene is rendered by its own Blender process (only its own characters and set are loaded, and all
memory is freed when it ends) into scenes/NN_id/shot.mp4. A scene that has not changed since its last
render is reused, so editing one scene re-renders only that scene. The shots are then joined into
episode.mp4 with one loudness pass. Every shot keeps its own .blend for hand edits or later AI passes.

    python episode_job.py EPISODE_FOLDER [--quality blocking|draft|standard|final] [--prepare]
    --prepare writes each scene's scene.json without rendering (for test frames)
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
CODE = [os.path.join(ROOT, "blender", f) for f in ("scene_kit.py", "props.py")]

folder = os.path.abspath(sys.argv[1])
quality = sys.argv[sys.argv.index("--quality") + 1] if "--quality" in sys.argv else None
spec = json.load(open(os.path.join(folder, "scene.json"), encoding="utf-8"))


def log(*a):
    print("CF:", *a, flush=True)


def blender_scene(scene_file, out):
    cmd = [BLENDER, "-b", "-y", "-P", CODE[0], "--", "--scene", scene_file, "--out", out]
    if quality:
        cmd += ["--quality", quality]
    return subprocess.run(cmd, stdout=sys.stdout, stderr=subprocess.STDOUT).returncode


if "scenes" not in spec:
    # a single scene: render it straight into episode.mp4
    sys.exit(blender_scene(os.path.join(folder, "scene.json"), os.path.join(folder, "episode.mp4")))


def absolute(p):
    return p if os.path.isabs(p) else os.path.normpath(os.path.join(folder, p))


library = spec.get("cast", {})
defaults = {k: v for k, v in spec.items() if k not in ("cast", "scenes")}
shots = []
n = len(spec["scenes"])
for i, sc in enumerate(spec["scenes"], 1):
    sid = f"{i:02d}_{sc.get('id', 'scene')}"
    d = os.path.join(folder, "scenes", sid)
    os.makedirs(d, exist_ok=True)
    scene = dict(defaults)
    scene.update({k: v for k, v in sc.items() if k != "cast"})
    scene["cast"] = {}
    for name, entry in sc.get("cast", {}).items():
        if name not in library and "character" not in entry:
            sys.exit(f"CF: FAILED scene {sid}: {name} is not in the episode cast")
        scene["cast"][name] = {**library.get(name, {}), **entry}
    # paths in the episode file are relative to the episode folder; the scene lives in a subfolder
    for key in ("background", "ambience"):
        # sound-library names (e.g. "cabin_night") stay as they are; only file paths are made absolute
        if scene.get(key) and (key == "background" or os.path.splitext(scene[key])[1]):
            scene[key] = absolute(scene[key])
    music = scene.get("music")
    if isinstance(music, dict) and os.path.splitext(music.get("bed", ""))[1]:
        music["bed"] = absolute(music["bed"])
    elif isinstance(music, str) and os.path.splitext(music)[1]:
        scene["music"] = absolute(music)
    for c in scene["cast"].values():
        c["character"] = absolute(c["character"])
    for p in scene.get("props", []):
        if p.get("file"):
            p["file"] = absolute(p["file"])
    for st in scene.get("script", []):
        if st.get("audio"):
            st["audio"] = absolute(st["audio"])
    scene_file = os.path.join(d, "scene.json")
    text = json.dumps(scene, indent=1)
    if not os.path.exists(scene_file) or open(scene_file, encoding="utf-8").read() != text:
        open(scene_file, "w", encoding="utf-8").write(text)

    if "--prepare" in sys.argv:          # only write the scene files (for test frames), render nothing
        log(f"prepared {scene_file}")
        continue
    h = hashlib.sha256(text.encode())
    for f in CODE:
        h.update(open(f, "rb").read())
    h.update((quality or "").encode())
    stamp = os.path.join(d, "shot.sha256")
    shot = os.path.join(d, "shot.mp4")
    log(f"scene {i}/{n} {sid}")
    if os.path.exists(shot) and os.path.exists(stamp) and open(stamp).read() == h.hexdigest():
        log(f"scene {sid} unchanged: reusing its shot")
    else:
        if blender_scene(scene_file, shot) != 0 or not os.path.exists(shot):
            sys.exit(f"CF: FAILED scene {sid} (see the lines above); run the episode again to retry from here")
        open(stamp, "w").write(h.hexdigest())
    shots.append(shot)

if "--prepare" in sys.argv:
    sys.exit(0)

# join the shots (same size, frame rate and codecs) and level the sound once over the whole episode
listing = os.path.join(folder, "scenes", "shots.txt")
with open(listing, "w", encoding="utf-8") as f:
    for s in shots:
        f.write(f"file '{s.replace(os.sep, '/')}'\n")
out = os.path.join(folder, "episode.mp4")
ff = shutil.which("ffmpeg")
r = subprocess.run([ff, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", listing, "-c:v", "copy",
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", out])
if r.returncode != 0:
    sys.exit("CF: FAILED joining the shots")
log("video", out)
