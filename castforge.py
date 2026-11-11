"""CastForge: photo -> 3D character -> animated, voiced, finished episode. One command for every step.

    python castforge.py app                      open the CastForge app in your browser (http://localhost:8765)
    python castforge.py help                     how it works, step by step
    python castforge.py gemini-prompt [scene|character]   show a Gemini prompt and copy it to the clipboard
    python castforge.py character PHOTO NAME --gender female --age 30 --height-cm 168 [--face-photo FACE]
    python castforge.py character --design NAME.design.json NAME      (invented character, no photo)
    python castforge.py check FOLDER             check FOLDER/scene.json (e.g. from Gemini) before rendering
    python castforge.py storyboard FOLDER        one still per shot -> FOLDER/storyboard.jpg (a minute per scene)
    python castforge.py episode FOLDER           render FOLDER/scene.json and finish it to FOLDER/episode.mp4
                                                 (runs in the background; add --wait to wait for it;
                                                  --quality blocking|draft|standard|final|ultra, default blocking)
    python castforge.py status FOLDER            render progress (frames done / total)
    python castforge.py stop FOLDER              stop that render (finished frames are kept; episode resumes)
    python castforge.py finish FOLDER            redo titles, transitions, grade, subtitles and sound mastering only
    python castforge.py voice "TEXT" --voice am_santa [--speed 0.9] [--fx phone]   hear a line (CPU)
    python castforge.py transcribe FILE.wav      the words in a recording (for lip-sync transcripts)
    python castforge.py library-build [--refresh] build missing (or refresh unchanged) city-library starters
    python castforge.py doctor                   check that every tool CastForge needs is installed
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from core import config  # noqa: E402
from core.buildings import BUILDING_DESIGNS, default_asset_spec  # noqa: E402
from core.schema import check_scene  # noqa: E402,F401  (castforge.check_scene is used by the app and tests)

BLENDER, VENV_PY = config.BLENDER, config.VENV_PY
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

2. The scene (with Gemini, or in the app's scene editor)
   python castforge.py gemini-prompt scene
   The prompt is copied to your clipboard. Paste it into Gemini, write your idea on the last line,
   and save Gemini's answer as scene.json in a new folder. Put in the same folder:
     background.png   (make it in Gemini: eye-level photo of the empty place, 16:9, no people)
     ambience.wav     (optional background sound)
     <name>.blend     (the characters from step 1; their names must match the cast in scene.json)
   Characters can act: "expression" on a line, emote / gesture / posture / look steps, walk "pace".
   Text dialogue uses Kokoro voices; hear one first with: python castforge.py voice "Hello" --voice af_heart
   For a final performance, put one WAV per line in voices/ and set both "audio" and "text" on the step.

   Motion capture: "perform" plays a clip from the motion library (a punch, a sword swing, a dance):
   python castforge.py motion cmu punch                   (search the free CMU library)
   python castforge.py motion cmu 02_05 --name punch      (download and add a CMU take)
   python castforge.py motion add Jab.fbx --name jab      (a Mixamo download: FBX, 30 fps, without skin)
   python castforge.py motion list

3. Check, preview, render
   python castforge.py check my_scene_folder         (finds mistakes in scene.json)
   python castforge.py storyboard my_scene_folder    (one still per shot: check staging and camera first)
   python castforge.py episode my_scene_folder       (renders in the background, then finishes the film)
   python castforge.py status my_scene_folder        (progress; stop with: python castforge.py stop ...)
   Only one render at a time. If a render stops, run the episode command again: it continues.

4. Finish and publish
   Titles, credits, transitions, colour grade, subtitles and loudness are applied after the render.
   Change them in scene.json (or the app's Publish panel), then: python castforge.py finish my_scene_folder
   You get episode.mp4, episode.srt/.vtt (subtitles), episode_chapters.txt and episode_poster.jpg.
   Each scene's Blender file is in scenes/NN_<id>/shot.blend for hand edits.
"""


def gemini_prompt(kind="scene"):
    text = open(PROMPT_DOCS[kind], encoding="utf-8").read()
    m = re.search(r"```\n(.*?)```", text, re.S)
    return m.group(1).strip()


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


def _lock():
    """(pid, folder) of the render holding the lock, or None; a lock left by a dead or half-written render is
    cleared."""
    if not os.path.exists(LOCK):
        return None
    try:
        pid, folder = open(LOCK, encoding="utf-8").read().split("\n")[:2]
        if pid.strip().isdigit() and pid_alive(int(pid)):
            return int(pid), folder
    except (OSError, ValueError):
        pass
    try:
        os.remove(LOCK)
    except OSError:
        pass
    return None


def render_lock_owner():
    """Folder of the render that holds the lock, or None."""
    held = _lock()
    return held[1] if held else None


def render_status(folder):
    """Progress of the job in folder: storyboard, frames done / total, finishing, finished or stopped."""
    log_path = os.path.join(folder, "render.log")
    if not os.path.exists(log_path):
        return None
    log = open(log_path, encoding="utf-8", errors="ignore").read()
    alive = os.path.normcase(render_lock_owner() or "") == os.path.normcase(folder)
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
    elif re.search(r"CF: 3D preview ready", log):
        text = "3D preview ready"
    elif re.search(r"CF: storyboard ready", log):
        text = f"storyboard ready: {os.path.join(folder, 'storyboard.jpg')}"
    elif "CF: stopped by the user" in log and not alive:
        text = where + f"stopped at {done}/{total or '?'} frames; run the episode command again to continue"
    elif alive:
        if "CF: finishing" in log:
            text = "finishing: titles, transitions, subtitles and sound"
        elif "CF: 3D preview" in log:
            text = where + "3D preview: building the scene"
        elif "CF: storyboard" in log:
            text = where + "storyboard: building the scene and its shots"
        else:
            text = where + (f"rendering: {done}/{total} frames" if total else "preparing the scene (voices, set, cast)")
    else:
        err = [ln for ln in log.splitlines() if "Error" in ln or "FAILED" in ln or "Traceback" in ln]
        text = (where + f"stopped at {done}/{total or '?'} frames" + (f" ({err[-1].strip()})" if err else "")
                + "; run the episode command again to continue from there")
    return {"alive": alive, "text": text, "done": done, "total": total}


def start_job(folder, extra, wait=False):
    """Start episode_job.py on folder in the background (GPU work: one at a time)."""
    running = render_status(folder)
    if running and running["alive"]:
        print("already working on this folder:", running["text"])
        print("(check again with: python castforge.py status", folder + ")")
        return None
    other = render_lock_owner()
    if other:
        sys.exit(f"another render is running ({other}); one at a time, the GPU has only 4 GB. "
                 "Check it with: python castforge.py status <its folder>")
    try:
        with open(LOCK, "x", encoding="utf-8") as lock:
            lock.write(f"{os.getpid()}\n{folder}\n")
    except FileExistsError:
        other = render_lock_owner()
        if other:
            sys.exit(f"another render is running ({other}); one at a time, the GPU has only 4 GB. "
                     "Check it with: python castforge.py status <its folder>")
        try:
            with open(LOCK, "x", encoding="utf-8") as lock:
                lock.write(f"{os.getpid()}\n{folder}\n")
        except FileExistsError:
            other = render_lock_owner()
            sys.exit(f"another render is running ({other or 'starting'}); one render at a time")
    flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0      # DETACHED_PROCESS | NEW_PROCESS_GROUP
    logf, p = None, None
    lock_tmp = f"{LOCK}.{os.getpid()}.tmp"
    try:
        logf = open(os.path.join(folder, "render.log"), "w", encoding="utf-8")
        p = subprocess.Popen([sys.executable, os.path.join(ROOT, "episode_job.py"), folder, *extra], stdout=logf,
                             stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=flags, cwd=folder)
        with open(lock_tmp, "w", encoding="utf-8") as lock:
            lock.write(f"{p.pid}\n{folder}\n")
        os.replace(lock_tmp, LOCK)
    except Exception:
        if p is not None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
            else:
                p.terminate()
        try:
            os.remove(lock_tmp)
        except OSError:
            pass
        try:
            with open(LOCK, encoding="utf-8") as lock:
                reserved_pid = lock.readline().strip()
            if reserved_pid == str(os.getpid()):
                os.remove(LOCK)
        except OSError:
            pass
        raise
    finally:
        if logf:
            logf.close()
    print(f"working in the background (pid {p.pid}); progress: python castforge.py status \"{folder}\"")
    print("it keeps going if this window or the calling tool closes; a stopped render resumes where it stopped")
    if wait:
        p.wait()
        print(render_status(folder)["text"])
    return p.pid


def stop_job(folder):
    held = _lock()
    if not held:
        return "nothing is rendering"
    pid, owner = held
    if os.path.normcase(owner) != os.path.normcase(folder):
        return f"the running render is for {owner}, not this folder"
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        import signal
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    try:
        os.remove(LOCK)
    except OSError:
        pass
    with open(os.path.join(folder, "render.log"), "a", encoding="utf-8") as f:
        f.write("\nCF: stopped by the user\n")
    return "stopped; finished frames are kept, and the episode command continues from there"


# --- motion clips ------------------------------------------------------------------------------------------
CMU_MIRROR = "https://raw.githubusercontent.com/sfd158/cmu-mocap/master/"    # the cgspeed BVH release of CMU
CMU_DIR = os.path.join(ROOT, "motions", "sources", "cmu")


def motion_add(src, name=None):
    """Import a Mixamo FBX or CMU BVH into the motion library (motions/clips); True when it worked."""
    if not os.path.isfile(src):
        print(f"file not found: {src}")
        return False
    name = name or re.sub(r"[^a-z0-9_]+", "_", os.path.splitext(os.path.basename(src))[0].lower()).strip("_")
    out = os.path.join(config.MOTIONS_DIR, name)
    os.makedirs(config.MOTIONS_DIR, exist_ok=True)
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "-P",
                        os.path.join(ROOT, "blender", "import_motion.py"), "--", os.path.abspath(src),
                        out + ".blend", out + ".json"], capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    for line in r.stdout.splitlines():
        if line.startswith("CF:"):
            print(line[4:])
    if r.returncode:
        print(f"could not import {src} (details: blender -b -P blender/import_motion.py -- FILE OUT.blend OUT.json)")
    return r.returncode == 0


def motion_cmu(what, name=None):
    """A CMU take by number (02_05) is downloaded and imported; other words search the CMU index."""
    import urllib.request
    os.makedirs(CMU_DIR, exist_ok=True)
    if re.fullmatch(r"\d{2,3}_\d{2}", what):
        subject = what.split("_")[0].zfill(3)
        dest = os.path.join(CMU_DIR, what + ".bvh")
        if not os.path.exists(dest):
            print(f"downloading CMU take {what}...")
            urllib.request.urlretrieve(f"{CMU_MIRROR}data/{subject}/{what}.bvh", dest)
        return motion_add(dest, name or f"cmu_{what}")
    index = os.path.join(CMU_DIR, "index.txt")
    if not os.path.exists(index):
        urllib.request.urlretrieve(CMU_MIRROR + "cmu-mocap-index-text.txt", index)
    hits = [ln.strip() for ln in open(index, encoding="utf-8", errors="replace")
            if re.match(r"\d+_\d+\t", ln) and what.lower() in ln.lower()]
    print("\n".join(hits[:40]) or f"no CMU take mentions {what!r}")
    if hits:
        print("import one with: python castforge.py motion cmu 02_05 --name punch")
    return bool(hits)


def speak(text, voice, speed=1.0, fx="clean", out=None):
    """A spoken line as a WAV (Kokoro on the CPU, so it works while a render uses the GPU)."""
    import hashlib
    import json
    from core import media
    key = hashlib.sha1(json.dumps([text, voice, speed]).encode()).hexdigest()[:16]
    out = out or os.path.join(tempfile.gettempdir(), "castforge_voice", f"{voice}_{key}.wav")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    if os.path.exists(out):
        return media.process_voice(out, fx)
    jobs = out + ".jobs.json"
    json.dump([{"text": text, "voice": voice, "out": out, "speed": speed}], open(jobs, "w", encoding="utf-8"))
    r = subprocess.run([config.AI_PYTHON, os.path.join(ROOT, "generate", "tts.py"), jobs, "--device", "cpu"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    os.remove(jobs)
    if r.returncode != 0 or not os.path.exists(out):
        raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout) else "TTS failed")
    return media.process_voice(out, fx)


def doctor():
    """Check every tool and file CastForge needs; print a plain fix for each problem. Returns the problem count."""
    problems = []

    def report(ok, what, fix=""):
        print(("  ok       " if ok else "  PROBLEM  ") + what + ("" if ok else f"\n           fix: {fix}"))
        if not ok:
            problems.append(what)

    def run(cmd):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace")
            return r.returncode, (r.stdout + r.stderr).strip()
        except (OSError, subprocess.TimeoutExpired) as e:
            return 1, str(e)

    print("CastForge doctor\n")
    code, out = run([config.BLENDER, "--version"])
    report(code == 0, f"Blender: {out.splitlines()[0] if code == 0 else config.BLENDER}",
           "install Blender 5.2, or set CASTFORGE_BLENDER to blender.exe")
    mpfb = glob.glob(os.path.join(os.environ.get("APPDATA", ""), "Blender Foundation", "Blender", "*", "extensions",
                                  "*", "mpfb*"))
    report(bool(mpfb), "MPFB (MakeHuman for Blender) extension", "install MPFB 2 from extensions.blender.org")
    code, out = run([config.FFMPEG, "-hide_banner", "-filters"])
    report(code == 0 and " subtitles " in out and " loudnorm " in out, "ffmpeg with libass and loudnorm",
           "install a full ffmpeg build (winget install Gyan.FFmpeg) and put it on PATH")
    report(os.path.exists(config.FFPROBE) or bool(run([config.FFPROBE, "-version"])[0] == 0), "ffprobe",
           "it comes with ffmpeg; put it on PATH")
    report(os.path.exists(config.RHUBARB), "Rhubarb Lip Sync (lip-sync for recorded lines)",
           "unzip Rhubarb-Lip-Sync-1.14.0-Windows into tools/")
    code, out = run([config.AI_PYTHON, "-c", "import kokoro, torch, transformers, soundfile; "
                     "print('cuda' if torch.cuda.is_available() else 'cpu')"])
    report(code == 0, f"AI Python ({config.AI_PYTHON}): Kokoro, torch, transformers" + (f", {out}" if code == 0 else ""),
           "pip install kokoro torch transformers soundfile (or set CASTFORGE_AI_PYTHON)")
    code, _ = run([config.AI_PYTHON, "-c", "import faster_whisper"])
    report(code == 0, "faster-whisper (automatic transcripts, optional)", "pip install faster-whisper")
    code, _ = run([config.VENV_PY, "-c", "import mediapipe"])
    report(code == 0, ".venv with MediaPipe (photo characters)", "python -m venv .venv && .venv\\Scripts\\pip install mediapipe numpy pillow")
    for model in ("pose_landmarker_heavy.task", "selfie_multiclass_256x256.tflite", "face_landmarker.task"):
        report(os.path.exists(os.path.join(ROOT, "models", model)), f"model {model}", "download it from Google MediaPipe into models/")
    report(os.path.exists(os.path.join(ROOT, "asset_index.json")), "asset_index.json (skin tones)",
           ".venv\\Scripts\\python generate/index_assets.py")
    lib = os.path.join(config.SFX_DIR, "library.json")
    missing = []
    if os.path.exists(lib):
        import json
        data = json.load(open(lib, encoding="utf-8"))
        for group in data.values():
            for files in group.values():
                missing += [f for f in files if not os.path.exists(os.path.join(config.SFX_DIR, f))]
    report(os.path.exists(lib) and not missing, f"sound library ({len(missing)} missing files)" if missing else "sound library",
           "python generate/make_sfx_library.py sfx --missing")
    code, out = run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])
    report(code == 0, f"GPU: {out}" if code == 0 else "NVIDIA GPU", "update the NVIDIA driver")
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
        report(True, "web app packages (fastapi, uvicorn)")
    except ImportError:
        report(False, "web app packages (fastapi, uvicorn)", f"{sys.executable} -m pip install fastapi uvicorn python-multipart")
    print("\n" + ("Everything CastForge needs is here." if not problems else f"{len(problems)} problem(s) to fix."))
    return len(problems)


def main():
    ap = argparse.ArgumentParser(description="CastForge", add_help=False)
    ap.add_argument("command", nargs="?", default="help")
    ap.add_argument("args", nargs=argparse.REMAINDER)
    a = ap.parse_args()

    def folder_arg():
        return os.path.abspath(a.args[0] if a.args and not a.args[0].startswith("--") else ".")

    def option(name, default=None):
        return a.args[a.args.index(name) + 1] if name in a.args else default

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
        design = json.load(open(c.design, encoding="utf-8")) if c.design else {}
        c.gender = c.gender or design.get("gender")
        c.age = c.age or design.get("age")
        c.height_cm = c.height_cm or design.get("height_cm")
        if not (c.photo or c.design):
            sys.exit("give a PHOTO or --design DESIGN.json (or both: the design then adds a costume to the photo)")
        if c.design:
            build += ["--design", c.design]
        if c.photo:
            if not (c.gender and c.age and c.height_cm):
                sys.exit("a photo character needs: PHOTO NAME --gender --age --height-cm (or a design that has them)")
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
    elif a.command == "set-build":
        if not a.args:
            sys.exit("usage: python castforge.py set-build SET_FOLDER")
        set_dir = os.path.abspath(a.args[0])
        if not os.path.isdir(set_dir):
            sys.exit(f"set folder not found: {set_dir}")
        blueprint_path = os.path.join(set_dir, "set_blueprint.json")
        if not os.path.isfile(blueprint_path):
            sys.exit(f"set blueprint not found: {blueprint_path}")
        with open(blueprint_path, encoding="utf-8") as blueprint_file:
            blueprint = json.load(blueprint_file)
        images = sorted(name for name in os.listdir(set_dir)
                        if name.lower().endswith((".png", ".jpg", ".jpeg"))
                        and name.lower() != "set_preview.png")
        image = blueprint.get("image")
        image_path = os.path.join(set_dir, image) if image else (
            os.path.join(set_dir, images[0]) if images else None)
        if not image_path or not os.path.isfile(image_path):
            sys.exit("set background image not found; add an image to the set folder")
        geometry_dir = os.path.join(set_dir, ".castforge_geometry")
        metadata_path = os.path.join(geometry_dir, "set.json")
        rebuild = not os.path.isfile(metadata_path) or not os.path.isfile(os.path.join(geometry_dir, "set.obj"))
        if not rebuild:
            with open(metadata_path, encoding="utf-8") as metadata_file:
                metadata = json.load(metadata_file)
            rebuild = (os.path.normcase(metadata.get("image", "")) != os.path.normcase(os.path.abspath(image_path))
                       or os.path.getmtime(metadata_path) < os.path.getmtime(image_path))
        if rebuild:
            subprocess.run([config.AI_PYTHON, os.path.join(ROOT, "generate", "depth_set.py"),
                            image_path, geometry_dir], check=True)
        subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "-P",
                        os.path.join(ROOT, "blender", "build_set.py"), "--",
                        "--set-dir", set_dir, "--geometry-dir", geometry_dir,
                        "--out", os.path.join(set_dir, "set.blend")], check=True)
        print(f"3D set ready: {os.path.join(set_dir, 'set.blend')}")
    elif a.command == "prop-build":
        if not a.args:
            sys.exit("usage: python castforge.py prop-build PROP_FOLDER")
        prop_dir = os.path.abspath(a.args[0])
        spec_path = os.path.join(prop_dir, "prop.json")
        if not os.path.isfile(spec_path):
            sys.exit(f"prop design not found: {spec_path}")
        with open(spec_path, encoding="utf-8") as spec_file:
            prop_spec = json.load(spec_file)
        image_path = os.path.join(prop_dir, prop_spec.get("image", ""))
        if not os.path.isfile(image_path):
            sys.exit(f"prop reference image not found: {image_path}")
        subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "-P",
                        os.path.join(ROOT, "blender", "build_prop_asset.py"), "--",
                        "--spec", spec_path, "--out", os.path.join(prop_dir, f"{prop_spec['name']}.blend"),
                        "--preview", os.path.join(prop_dir, "preview.png")], check=True)
        print(f"3D prop ready: {os.path.join(prop_dir, prop_spec['name'] + '.blend')}")
    elif a.command == "building-build":
        if not a.args:
            sys.exit("usage: python castforge.py building-build BUILDING_FOLDER")
        building_dir = os.path.abspath(a.args[0])
        spec_path = os.path.join(building_dir, "building.json")
        if not os.path.isfile(spec_path):
            sys.exit(f"building design not found: {spec_path}")
        with open(spec_path, encoding="utf-8") as spec_file:
            building_spec = json.load(spec_file)
        name = building_spec.get("name")
        if not isinstance(name, str) or not name:
            sys.exit(f"building design has no valid name: {spec_path}")
        subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "-P",
                        os.path.join(ROOT, "blender", "build_building_asset.py"), "--",
                        "--spec", spec_path, "--out", os.path.join(building_dir, f"{name}.blend"),
                        "--preview", os.path.join(building_dir, "preview.png")], check=True)
        print(f"3D building ready: {os.path.join(building_dir, name + '.blend')}")
    elif a.command == "library-build":
        refresh = "--refresh" in a.args
        built = skipped = 0
        for template_id in BUILDING_DESIGNS:
            spec = default_asset_spec(template_id)
            asset_dir = os.path.join(ROOT, "library", spec["category"], template_id)
            spec_path = os.path.join(asset_dir, "building.json")
            blend_path = os.path.join(asset_dir, f"{template_id}.blend")
            if os.path.exists(spec_path) or os.path.exists(blend_path):
                existing_spec = None
                if os.path.isfile(spec_path):
                    with open(spec_path, encoding="utf-8") as spec_file:
                        existing_spec = json.load(spec_file)
                if not refresh or existing_spec != spec:
                    print(f"Keeping existing library asset: {os.path.relpath(asset_dir, ROOT)}")
                    skipped += 1
                    continue
            os.makedirs(asset_dir, exist_ok=True)
            if not os.path.isfile(spec_path):
                with open(spec_path, "w", encoding="utf-8") as spec_file:
                    json.dump(spec, spec_file, indent=1)
            subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "-P",
                            os.path.join(ROOT, "blender", "build_building_asset.py"), "--",
                            "--spec", spec_path, "--out", blend_path,
                            "--preview", os.path.join(asset_dir, "preview.png")], check=True)
            print(f"Reusable asset ready: {os.path.relpath(blend_path, ROOT)}")
            built += 1
        print(f"Library starter build complete: {built} built, {skipped} kept.")
    elif a.command == "motion":
        sub, rest = (a.args[0] if a.args else "list"), a.args[1:]
        if sub == "add" and rest:
            sys.exit(0 if motion_add(rest[0], option("--name")) else 1)
        elif sub == "cmu" and rest:
            sys.exit(0 if motion_cmu(rest[0], option("--name")) else 1)
        elif sub == "list":
            from blender import motion
            for n in motion.names(config.MOTIONS_DIR):
                m = motion.load(config.MOTIONS_DIR, n)
                print(f"{n:24} {m['seconds']:6.1f} s  {m['source']:6}  {m['file']}")
        else:
            sys.exit("usage: python castforge.py motion add FILE [--name NAME] | motion cmu SEARCH|TAKE [--name NAME]"
                     " | motion list")
    elif a.command == "check":
        sys.exit(1 if check_scene(a.args[0] if a.args else ".") else 0)
    elif a.command in ("episode", "storyboard", "preview3d"):
        quality = option("--quality")
        if quality and quality not in config.QUALITY:
            sys.exit(f"unknown quality {quality!r}; choose {', '.join(config.QUALITY)}")
        extra = (["--quality", quality] if quality else []) + ([f"--{a.command}"] if a.command != "episode" else [])
        start_job(folder_arg(), extra, wait="--wait" in a.args)
    elif a.command == "finish":
        folder = folder_arg()
        if os.path.normcase(render_lock_owner() or "") == os.path.normcase(folder):
            sys.exit("this episode is rendering; it is finished automatically when the render ends")
        sys.exit(subprocess.run([sys.executable, os.path.join(ROOT, "episode_job.py"), folder, "--finish-only",
                                 *(["--quality", option("--quality")] if option("--quality") else [])]).returncode)
    elif a.command == "stop":
        print(stop_job(folder_arg()))
    elif a.command == "voice":
        if not a.args or a.args[0].startswith("--"):
            sys.exit('usage: python castforge.py voice "TEXT" --voice af_heart [--speed 1.0] [--fx clean] [--out f.wav]')
        print(speak(a.args[0], option("--voice", "af_heart"), float(option("--speed", 1.0)), option("--fx", "clean"),
                    option("--out")))
    elif a.command == "transcribe":
        if not a.args:
            sys.exit("usage: python castforge.py transcribe FILE.wav")
        sys.exit(subprocess.run([config.AI_PYTHON, os.path.join(ROOT, "generate", "transcribe.py"), a.args[0]]).returncode)
    elif a.command == "doctor":
        sys.exit(1 if doctor() else 0)
    elif a.command == "app":
        import threading
        import webbrowser
        import uvicorn
        threading.Timer(1.5, lambda: webbrowser.open("http://localhost:8765")).start()
        print("CastForge app: http://localhost:8765  (Ctrl+C to stop)")
        open(os.path.join(ROOT, ".app.pid"), "w").write(str(os.getpid()))
        uvicorn.run("app.server:app", host="127.0.0.1", port=8765, log_level="warning", app_dir=ROOT)
    elif a.command == "status":
        st = render_status(folder_arg())
        print(st["text"] if st else "no render has been started in this folder")
    else:
        print(f"unknown command '{a.command}'\n{HELP}")
        sys.exit(1)


if __name__ == "__main__":
    main()
