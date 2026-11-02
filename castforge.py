"""CastForge: photo -> 3D character -> animated, voiced episode. One command for every step.

    python castforge.py app                      open the CastForge app in your browser (http://localhost:8765)
    python castforge.py help                     how it works, step by step
    python castforge.py gemini-prompt [scene|character]   show a Gemini prompt and copy it to the clipboard
    python castforge.py character PHOTO NAME --gender female --age 30 --height-cm 168 [--face-photo FACE]
    python castforge.py character --design NAME.design.json NAME      (invented character, no photo)
    python castforge.py check SCENE_FOLDER       check SCENE_FOLDER/scene.json (e.g. from Gemini) before rendering
    python castforge.py episode SCENE_FOLDER     render SCENE_FOLDER/scene.json to SCENE_FOLDER/episode.mp4
                                                 (runs in the background; add --wait to wait for it;
                                                  --quality blocking|draft|standard|final, default blocking)
    python castforge.py status SCENE_FOLDER      render progress (frames done / total)
"""
import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
VENV_PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
PROMPT_DOCS = {"scene": os.path.join(ROOT, "docs", "GEMINI_SCENE_PROMPT.md"),
               "character": os.path.join(ROOT, "docs", "GEMINI_CHARACTER_PROMPT.md")}

HELP = """
CastForge - how to make an episode
==================================

1. Characters (once per person), two ways:
   a) From a photo:
      python castforge.py character photo.png maya --gender female --age 30 --height-cm 168 --face-photo face.png
      Photo: one person, head to toe, facing the camera, arms a little away from the body.
      Face photo (optional, recommended): a sharp, front-facing close-up of the same person.
      Only use people who agreed to it.
   b) Invented with Gemini (no photo):
      python castforge.py gemini-prompt character      (copied: paste into Gemini, describe the person)
      save Gemini's answer as maya.design.json, then
      python castforge.py character --design maya.design.json maya

2. The scene (with Gemini)
   python castforge.py gemini-prompt scene
   The prompt is copied to your clipboard. Paste it into Gemini, write your idea on the last line,
   and save Gemini's answer as scene.json in a new folder. Put in the same folder:
     background.png   (make it in Gemini: eye-level photo of the empty place, 16:9, no people)
     ambience.wav     (optional background sound)
     <name>.blend     (the characters from step 1; their names must match the cast in scene.json)
   Text dialogue uses Kokoro as a quick draft voice. For a final performance, put one WAV per line in
   voices/ and set both "audio": "voices/<line>.wav" and "text": "<exact transcript>" on the say step.
   The transcript guides lip-sync; review the voice and keep the same performer for each character.

3. Check and render
   python castforge.py check my_scene_folder        (finds mistakes in Gemini's scene.json)
   python castforge.py episode my_scene_folder        (starts the render in the background)
   python castforge.py status my_scene_folder         (progress; a long episode takes about 3 s per frame)
   Only one render at a time. If a render stops, run the episode command again: it continues.
   You get my_scene_folder/episode.mp4 (and episode.blend to adjust by hand in Blender).
"""


def gemini_prompt(kind="scene"):
    text = open(PROMPT_DOCS[kind], encoding="utf-8").read()
    m = re.search(r"```\n(.*?)```", text, re.S)
    return m.group(1).strip()


VOICES = {"af_heart", "af_bella", "af_nicole", "am_michael", "am_adam", "am_eric", "bf_emma", "bf_isabella",
          "bm_george", "bm_lewis", "hf_alpha", "hf_beta", "hm_omega", "hm_psi"}
ACTIONS = {"walk", "face", "say", "think", "drive", "wait", "enter", "exit", "open", "sit", "stand", "sound"}
PROP_TYPES = {"table", "chair", "stool", "bench", "sofa", "bed", "shelf", "counter", "door", "wall", "window", "lamp",
              "cup", "plant", "box", "tv", "seat", "santa_hat", "picture_road"}


def check_scene(folder):
    """Plain-language problems in a scene folder; returns the number of errors."""
    import json
    import math
    f = os.path.join(folder, "scene.json")
    errors, warnings = [], []
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
    if "scenes" in sc:
        # an episode: check every scene with the episode cast merged in
        library = sc.get("cast", {})
        defaults = {k: v for k, v in sc.items() if k not in ("cast", "scenes")}
        total = 0
        for i, part in enumerate(sc["scenes"], 1):
            merged = dict(defaults)
            merged.update({k: v for k, v in part.items() if k != "cast"})
            merged["cast"] = {n: {**library.get(n, {}), **e} for n, e in part.get("cast", {}).items()}
            print(f"--- scene {i} ({part.get('id', 'scene')})")
            total += check_parsed(folder, merged)
        return total
    return check_parsed(folder, sc)


def check_parsed(folder, sc):
    import math
    errors, warnings = [], []
    for key in ("background", "cast", "script"):
        if key not in sc:
            errors.append(f'missing "{key}"')
    if sc.get("background") and not os.path.exists(os.path.join(folder, sc["background"])):
        errors.append(f"background image not found: {sc['background']}")
    if sc.get("ambience") and "." in sc["ambience"] and not os.path.exists(os.path.join(folder, sc["ambience"])):
        warnings.append(f"ambience file not found: {sc['ambience']} (remove the line or add the file)")
    cast = sc.get("cast", {})
    pos = {}
    for name, c in cast.items():
        if not os.path.exists(os.path.join(folder, c.get("character", ""))):
            errors.append(f"{name}: character file not found: {c.get('character')} (build it with: castforge.py character ...)")
        if c.get("voice") and c["voice"] not in VOICES:
            errors.append(f"{name}: unknown voice {c['voice']}")
        pos[name] = c.get("position", [0, 0])
        if c.get("sit"):
            seat = next((p for p in sc.get("props", []) if p.get("id") == c["sit"]), None)
            if not seat:
                errors.append(f"{name}: sits on {c['sit']!r}, but there is no prop with that id")
            else:
                pos[name] = seat.get("position", pos[name])
    for p in sc.get("props", []):
        if "make" in p and p["make"] not in PROP_TYPES:
            warnings.append(f"prop {p.get('id', '?')}: unknown type {p['make']} (it will be built as a box)")
    facing = {n: c.get("facing", "camera") for n, c in cast.items()}
    for n, st in enumerate(sc.get("script", []), 1):
        do, who = st.get("do"), st.get("who")
        if do not in ACTIONS:
            errors.append(f"step {n}: unknown action {do!r} (use walk, face, say, wait, enter, sit, stand, sound)")
            continue
        if do not in ("wait", "sound") and who not in cast:
            errors.append(f"step {n}: {who!r} is not in the cast")
            continue
        prop_ids = {p.get("id"): p for p in sc.get("props", [])}
        if do in ("walk", "enter", "exit"):
            pos[who] = st.get("to", pos[who])
            facing[who] = None
            if do in ("enter", "exit") and prop_ids.get(st.get("door"), {}).get("make") != "door":
                errors.append(f"step {n}: enter needs \"door\": the id of a door prop")
        elif do == "open" and prop_ids.get(st.get("door"), {}).get("make") != "door":
            errors.append(f"step {n}: open needs \"door\": the id of a door prop")
        elif do == "sit":
            seat = prop_ids.get(st.get("on"), {})
            if seat.get("make") not in ("chair", "stool", "bench", "sofa", "seat"):
                errors.append(f"step {n}: sit needs \"on\": the id of a chair, stool, bench or sofa prop")
            else:
                pos[who] = seat.get("position", pos[who])
        elif do == "face":
            facing[who] = st.get("target")
        elif do in ("say", "think"):
            if not st.get("text") and not st.get("audio"):
                errors.append(f"step {n}: say needs \"text\" or \"audio\"")
            if st.get("text") and not st.get("audio") and not cast[who].get("voice"):
                errors.append(f"step {n}: {who} speaks text but has no voice in the cast")
            if st.get("audio") and not os.path.exists(os.path.join(folder, st["audio"])):
                errors.append(f"step {n}: audio file not found: {st['audio']}")
            if facing.get(who) == "camera" and len(cast) > 1:
                warnings.append(f"step {n}: {who} talks while facing the camera (add a face step first?)")
            for other, p in pos.items():
                if other != who:
                    d = math.dist(pos[who], p)
                    if d < 0.8:
                        warnings.append(f"step {n}: {who} is only {d:.1f} m from {other} (1.0-1.4 m looks natural)")
    for e in errors:
        print("ERROR:", e)
    for w in dict.fromkeys(warnings):
        print("warning:", w)
    if not errors:
        print("scene.json looks good" + (" (see warnings)" if warnings else ""))
    return len(errors)


LOCK = os.path.join(ROOT, ".render.lock")


def pid_alive(pid):
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def render_lock_owner():
    """Folder of the render that holds the lock, or None (a lock left by a dead render is cleared)."""
    if not os.path.exists(LOCK):
        return None
    pid, folder = open(LOCK).read().split("\n")[:2]
    if pid.strip().isdigit() and pid_alive(int(pid)):
        return folder
    os.remove(LOCK)
    return None


def render_status(folder):
    """Progress of the episode render in folder: frames done / total, still running, finished or stopped."""
    import glob
    import re
    log_path = os.path.join(folder, "render.log")
    if not os.path.exists(log_path):
        return None
    log = open(log_path, encoding="utf-8", errors="ignore").read()
    alive = render_lock_owner() == folder
    scenes = re.findall(r"CF: scene (\d+)/(\d+) (\S+)", log)
    where, frames_dir = "", os.path.join(folder, "episode_frames")
    if scenes:
        k, n, sid = scenes[-1]
        where = f"scene {k}/{n} ({sid}): "
        frames_dir = os.path.join(folder, "scenes", sid, "shot_frames")
        log_scene = log[log.rfind(f"CF: scene {k}/{n}"):]
    else:
        log_scene = log
    m = re.search(r"CF: saved scene .* (\d+) frames", log_scene)
    total = int(m.group(1)) if m else None
    done = len(glob.glob(os.path.join(frames_dir, "*.png")))
    if re.search(r"CF: video .*episode\.mp4", log):
        text = f"finished: {os.path.join(folder, 'episode.mp4')}"
    elif alive:
        text = where + (f"rendering: {done}/{total or '?'} frames" if total else "preparing the scene (voices, set, cast)")
    else:
        err = [l for l in log.splitlines() if "Error" in l or "FAILED" in l or "Traceback" in l]
        text = (where + f"stopped at {done}/{total or '?'} frames" + (f" ({err[-1].strip()})" if err else "")
                + "; run the episode command again to continue from there")
    return {"alive": alive, "text": text}


def main():
    ap = argparse.ArgumentParser(description="CastForge", add_help=False)
    ap.add_argument("command", nargs="?", default="help")
    ap.add_argument("args", nargs=argparse.REMAINDER)
    a = ap.parse_args()

    if a.command in ("help", "-h", "--help"):
        print(HELP)
    elif a.command == "gemini-prompt":
        kind = a.args[0] if a.args else "scene"
        if kind not in PROMPT_DOCS:
            sys.exit("choose: gemini-prompt scene   or   gemini-prompt character")
        prompt = gemini_prompt(kind)
        print(prompt)
        try:
            subprocess.run("clip", input=prompt.encode("utf-16-le"), check=True, shell=True)
            print("\n(copied to the clipboard: paste it into Gemini and write your idea on the last line)")
        except Exception:
            print("\n(copy the text above into Gemini)")
    elif a.command == "character":
        p = argparse.ArgumentParser(prog="castforge.py character")
        p.add_argument("photo", nargs="?")
        p.add_argument("name")
        p.add_argument("--design", help="character design JSON from Gemini (instead of a photo)")
        p.add_argument("--gender", choices=["male", "female"])
        p.add_argument("--age", type=float)
        p.add_argument("--height-cm", type=float)
        p.add_argument("--face-photo")
        p.add_argument("--hair")
        p.add_argument("--out-dir", default=".")
        c = p.parse_args(a.args)
        os.makedirs(c.out_dir, exist_ok=True)
        build = [BLENDER, "-b", "--factory-startup", "-P", os.path.join(ROOT, "blender", "build_character.py"), "--",
                 "--out", os.path.join(c.out_dir, f"{c.name}.blend"),
                 "--preview", os.path.join(c.out_dir, f"{c.name}_preview")]
        if c.design:
            build += ["--design", c.design]
        else:
            if not (c.photo and c.gender and c.age and c.height_cm):
                sys.exit("a photo character needs: PHOTO NAME --gender --age --height-cm")
            spec = os.path.join(c.out_dir, f"{c.name}.spec.json")
            cmd = [VENV_PY, os.path.join(ROOT, "generate", "analyze_photo.py"), c.photo, spec]
            if c.face_photo:
                cmd += ["--face-photo", c.face_photo]
            subprocess.run(cmd, check=True)
            build += ["--spec", spec]
        for flag, val in (("--gender", c.gender), ("--age", c.age), ("--height-cm", c.height_cm)):
            if val:
                build += [flag, str(val)]
        if c.hair:
            build += ["--hair", c.hair]
        subprocess.run(build, check=True)
        print(f"character ready: {os.path.join(c.out_dir, c.name + '.blend')} (previews in {c.name}_preview/)")
    elif a.command == "check":
        sys.exit(1 if check_scene(a.args[0] if a.args else ".") else 0)
    elif a.command == "episode":
        folder = os.path.abspath(a.args[0] if a.args and not a.args[0].startswith("--") else ".")
        wait = "--wait" in a.args
        quality = a.args[a.args.index("--quality") + 1] if "--quality" in a.args else None
        running = render_status(folder)
        if running and running["alive"]:
            print("already rendering this episode:", running["text"])
            print("(check again with: python castforge.py status", folder + ")")
            return
        other = render_lock_owner()
        if other:
            sys.exit(f"another render is running ({other}); one at a time, the GPU has only 4 GB. "
                     "Check it with: python castforge.py status <its folder>")
        log_path = os.path.join(folder, "render.log")
        cmd = [sys.executable, os.path.join(ROOT, "episode_job.py"), folder]
        if quality:
            cmd += ["--quality", quality]
        logf = open(log_path, "w", encoding="utf-8")
        flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0      # DETACHED_PROCESS | NEW_PROCESS_GROUP
        p = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             creationflags=flags, cwd=folder)
        open(LOCK, "w").write(f"{p.pid}\n{folder}\n")
        print(f"rendering in the background (pid {p.pid}); progress: python castforge.py status \"{folder}\"")
        print("it keeps going if this window or the calling tool closes; a stopped render resumes where it stopped")
        if wait:
            p.wait()
            print(render_status(folder)["text"])
    elif a.command == "app":
        import threading
        import webbrowser
        import uvicorn
        sys.path.insert(0, ROOT)
        threading.Timer(1.5, lambda: webbrowser.open("http://localhost:8765")).start()
        print("CastForge app: http://localhost:8765  (Ctrl+C to stop)")
        open(os.path.join(ROOT, ".app.pid"), "w").write(str(os.getpid()))
        uvicorn.run("app.server:app", host="127.0.0.1", port=8765, log_level="warning", app_dir=ROOT)
    elif a.command == "status":
        st = render_status(os.path.abspath(a.args[0] if a.args else "."))
        print(st["text"] if st else "no render has been started in this folder")
    else:
        print(f"unknown command '{a.command}'\n{HELP}")
        sys.exit(1)


if __name__ == "__main__":
    main()
