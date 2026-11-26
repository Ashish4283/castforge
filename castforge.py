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
    python castforge.py rig NAME [MOVIE_FOLDER] [--fix]   is that character fit to animate? (--fix tidies it)
    python castforge.py screen NAME [MOVIE_FOLDER] [--shots]  a screen test: can it walk, run, bend, grip?
    python castforge.py gpu where | use local|kaggle | make "worn denim" --kind denim | make --set
    python castforge.py gpu connect URL | status | fabric "..."   (a ComfyUI you already have an address for)
    python castforge.py suite                    the other tools beside this one, and what they share
    python castforge.py post FOLDER [--run]      hand that rendered episode to forgefilms for post
                                                 (--run does the post too: one film, graded, -16 LUFS, captioned)
    python castforge.py real FOLDER [--run]      the same shots, photographed: one image-to-video clip per
                                                 camera shot, each prompt read off the scene itself
                      FOLDER --gpu [IDS...]      ...and run it on the rented GPU
                      FOLDER --fetch             bring the clips home, into <episode>/real/ (the app shows them)
    python castforge.py doctor                   check that every tool CastForge needs is installed
"""
import argparse
import atexit
import glob
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import zipfile


def safe_name(text):
    """A name safe to use as a file name."""
    return re.sub(r"[^a-z0-9_]+", "_", str(text).lower()).strip("_") or "x"

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from core import config, publish  # noqa: E402
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
   For streaming platforms: python castforge.py publish my_scene_folder   (default --platform youtube)
   It checks the film (loudness, chapters, subtitles, picture) and writes publish/: the video at the
   platform's loudness, a 1280x720 thumbnail, chapters.txt, description.txt and report.txt.
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


def port_free(port):
    """True when nothing is listening on the port (the app can bind it)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
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


BUILD_LOCK = os.path.join(ROOT, ".build.lock")


def build_owner():
    """What GPU build is running (e.g. "a character build (maya)"), or None; a stale lock is cleared."""
    if not os.path.exists(BUILD_LOCK):
        return None
    try:
        pid, what = open(BUILD_LOCK, encoding="utf-8").read().split("\n")[:2]
        if pid.strip().isdigit() and pid_alive(int(pid)):
            return what.strip() or "a build"
    except (OSError, ValueError):
        pass
    try:
        os.remove(BUILD_LOCK)
    except OSError:
        pass
    return None


def claim_build(what):
    """Take the GPU for one build (character, set, prop, building): exits with a plain message when the GPU
    is already working. The lock is removed when this process ends."""
    owner = render_lock_owner()
    if owner:
        sys.exit(f"the GPU is rendering {owner}; one GPU job at a time on this laptop. "
                 "Wait for it, or stop it with: python castforge.py stop <its folder>")
    busy = build_owner()
    if busy:
        sys.exit(f"the GPU is busy with {busy}; one GPU job at a time on this laptop")
    try:
        with open(BUILD_LOCK, "x", encoding="utf-8") as lock:
            lock.write(f"{os.getpid()}\n{what}\n")
    except FileExistsError:
        sys.exit(f"the GPU is busy with {build_owner() or 'another build'}; one GPU job at a time")

    def release():
        try:
            if open(BUILD_LOCK, encoding="utf-8").readline().strip() == str(os.getpid()):
                os.remove(BUILD_LOCK)
        except OSError:
            pass
    atexit.register(release)


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
        try:
            fresh = time.time() - os.path.getmtime(log_path) < 8
        except OSError:
            fresh = False
        if fresh and not err:                   # the job just ended: its final lines are still landing
            text = where + "wrapping up: writing the result"
        else:
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
    building = build_owner()
    if building:
        sys.exit(f"the GPU is busy with {building}; start the render when it is done")
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
        claim_build(f"a character build ({c.name})")
        os.makedirs(c.out_dir, exist_ok=True)
        # --python-exit-code 1 or Blender reports SUCCESS after the script has crashed. That is how a
        # build that died rendering the previews still said "character ready", and the only sign was a
        # hat missing from a picture.
        build = [BLENDER, "-b", "--factory-startup", "--python-exit-code", "1",
                 "-P", os.path.join(ROOT, "blender", "build_character.py"), "--",
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
        claim_build(f"a 3D set build ({os.path.basename(set_dir)})")
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
        claim_build(f"a 3D prop build ({prop_spec.get('name', os.path.basename(prop_dir))})")
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
        claim_build(f"a building build ({name})")
        subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "-P",
                        os.path.join(ROOT, "blender", "build_building_asset.py"), "--",
                        "--spec", spec_path, "--out", os.path.join(building_dir, f"{name}.blend"),
                        "--preview", os.path.join(building_dir, "preview.png")], check=True)
        print(f"3D building ready: {os.path.join(building_dir, name + '.blend')}")
    elif a.command == "library-build":
        claim_build("the library starter builds")
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
    elif a.command == "suite":
        # What else is installed beside CastForge, and what all of it shares. Rules in shared/suite.py.
        sys.path.insert(0, ROOT)
        from shared import suite
        for row in suite.describe():
            print(row)
        sys.exit(1 if suite.check() else 0)
    elif a.command == "cast":
        # The step before `character`: the graphic novel is where a cast is designed and its faces are
        # locked. This shows that cast in the shape CastForge builds from. shared/cast.py is the whole
        # translation; building is still the ordinary `character` command.
        sys.path.insert(0, ROOT)
        from shared import cast as novel_cast
        from shared import suite
        gn = suite.TOOLS["graphic-novel"]["folder"]
        movie = a.args[1] if len(a.args) > 1 else None
        built = []
        if movie:
            cdir = os.path.join(ROOT, "movies", movie, "characters")
            built = [f[:-6] for f in os.listdir(cdir)] if os.path.isdir(cdir) else []
            built = [b for b in built if not b.endswith(".design")]
        rows = novel_cast.cast(gn, movie_cast=built)
        problems = novel_cast.check(gn, rows)
        title = novel_cast.novel_name(gn)
        print(f'the cast of "{title}"' if title else "the novel's cast")
        want = a.args[0].lower() if a.args else None
        for row in rows:
            if want and want not in (row["name"], (row["novel_name"] or "").lower()):
                continue
            mark = "built" if row["built"] else ("ready" if row["ready"] else "not ready")
            print(f"\n  {row['novel_name']:16s} [{mark}]  views: {', '.join(row['angles']) or 'none'}")
            for said in row["read"]:
                print(f"      read   {said}")
            for said in row["assumed"]:
                print(f"      guess  {said}")
            line = novel_cast.command(row, movie or "<movie>")
            if line:
                print(f"      build  {line}")
        for p in problems:
            print(f"\n! {p}")
        if not movie:
            print("\nadd a movie to see which of them are already built: "
                  "python castforge.py cast [NAME] MOVIE")
        sys.exit(0)
    elif a.command == "post":
        # The step after `episode`: hand the rendered, voiced scenes to forgefilms for post. The contract
        # between the two shapes is the only thing here; it lives in shared/handoff.py.
        if not a.args:
            sys.exit("usage: python castforge.py post EPISODE_FOLDER")
        sys.path.insert(0, ROOT)
        from shared import handoff, suite
        folder = a.args[0]
        if not os.path.isdir(folder):
            sys.exit(f"{folder} is not a folder")
        ff = suite.TOOLS["forgefilms"]["folder"]
        if not os.path.isdir(ff):
            sys.exit(f"forgefilms is not installed at {ff} - it is the tool that does the post")
        paths, problems = handoff.write(folder)
        for p in problems:
            print(f"! {p}")
        if not paths:
            sys.exit(1)
        got = handoff.plan(folder)
        print(f"{len(got['shots']['shots'])} scenes ready for post:")
        for key, path in paths.items():
            print(f"  {key:9s} {path}")
        out = os.path.join("out", got["title"])
        if "--run" not in a.args:
            print("\nnow run the post in forgefilms (or add --run to do it here):")
            print(f'  cd "{ff}"')
            print(f'  python scripts/assemble.py "{paths["shots"]}" "{paths["picks"]}" {out}')
            sys.exit(1 if problems else 0)
        print(f"\nrunning the post in forgefilms -> {os.path.join(ff, out)}")
        run = subprocess.run([sys.executable, os.path.join("scripts", "assemble.py"),
                              paths["shots"], paths["picks"], out], cwd=ff)
        if run.returncode:
            sys.exit("the post failed; the lines above say why")
        # forgefilms captions the voice layer it placed itself, and this cut has none: the voices are
        # already inside each scene's finished sound. So its .vtt comes out empty and ours - which has
        # the real per-line times, shifted by the crossfades - takes its place beside the film.
        made = os.path.join(ff, out, f"{got['title']}.vtt")
        shutil.copyfile(paths["captions"], made)
        film = os.path.join(ff, out, f"{got['title']}.mp4")
        # ...and bring it home. A film finished in another tool's out/ folder is a film nobody can find:
        # it belongs beside the episode it was cut from, where the app looks.
        home = os.path.join(folder, "post")
        os.makedirs(home, exist_ok=True)
        for src, as_ in ((film, "film.mp4"), (made, "film.vtt")):
            if os.path.isfile(src):
                shutil.copyfile(src, os.path.join(home, as_))
        print(f"\nfilm      {os.path.join(home, 'film.mp4')}")
        print(f"captions  {os.path.join(home, 'film.vtt')}  "
              f"({got['captions'].count(' --> ')} lines, from the scenes themselves)")
        print(f"          (also left in forgefilms at {os.path.join(ff, out)})")
        print("\nIt is in the app: open the episode and look at the Output tab.")
        sys.exit(1 if problems else 0)
    elif a.command == "real":
        # The step after `post`: the rendered 3D shots, photographed. Every decision about what a clip
        # should contain is read off the scene by shared/real.py; this grabs the stills and hands the
        # list to forgefilms, which owns the Wan 2.2 workflows.
        if not a.args:
            sys.exit("usage: python castforge.py real EPISODE_FOLDER [--run]")
        sys.path.insert(0, ROOT)
        from core import config, media
        from shared import real, suite
        folder = a.args[0]
        if not os.path.isdir(folder):
            sys.exit(f"{folder} is not a folder")
        ff = suite.TOOLS["forgefilms"]["folder"]
        if not os.path.isdir(ff):
            sys.exit(f"forgefilms is not installed at {ff} - it owns the image-to-video workflows")
        if "--fetch" in a.args:
            # Bring the clips home. They belong BESIDE the episode they came from - in <episode>/real/ -
            # not in a scratch folder the app knows nothing about, which is where they were landing.
            import tempfile
            user = os.environ.get("KAGGLE_USERNAME") or "ashishjiwa"
            into = os.path.join(folder, "real")
            os.makedirs(into, exist_ok=True)
            # --from FOLDER files a run you already downloaded; otherwise the finished run is fetched
            said = [a.args[i + 1] for i, x in enumerate(a.args) if x == "--from" and i + 1 < len(a.args)]
            if said:
                tmp, borrowed = os.path.abspath(said[0]), True
                if not os.path.isdir(tmp):
                    sys.exit(f"{tmp} is not a folder")
                print(f"filing what is already in {tmp} ...")
            else:
                tmp, borrowed = tempfile.mkdtemp(prefix="castforge_clips_"), False
                print(f"fetching {user}/castforge-clips ...")
                if subprocess.run(["kaggle", "kernels", "output", f"{user}/castforge-clips", "-p", tmp],
                                  capture_output=True, text=True).returncode:
                    sys.exit("could not fetch the run; is it finished? kaggle kernels status "
                             f"{user}/castforge-clips")
            brought = []
            for root, _dirs, files in os.walk(tmp):
                for f in files:
                    src, where = os.path.join(root, f), os.path.basename(root)
                    if f.endswith(".mp4"):
                        shutil.copyfile(src, os.path.join(into, re.sub(r"-5b-\d+$|-fast-\d+$|-full-\d+$",
                                                                       "", f[:-4]) + ".mp4"))
                        brought.append(f)
                    elif where == "stills" and f.endswith(".png"):
                        shutil.copyfile(src, os.path.join(into, f[:-4] + ".still.png"))
            # frames, if a run could not encode them where it ran
            for root, dirs, _files in os.walk(tmp):
                for d_ in dirs:
                    frames = sorted(glob.glob(os.path.join(root, d_, "*.png")))
                    clean = re.sub(r"-5b-\d+$|-fast-\d+$|-full-\d+$", "", d_)
                    made = os.path.join(into, clean + ".mp4")
                    if len(frames) > 8 and not os.path.isfile(made):
                        digits = re.search(r"\d+", os.path.basename(frames[0]))
                        pattern = os.path.basename(frames[0]).replace(
                            digits.group(0), f"%0{len(digits.group(0))}d", 1)
                        media.run([config.FFMPEG, "-y", "-v", "error", "-framerate", "24",
                                   "-start_number", digits.group(0), "-i",
                                   os.path.join(root, d_, pattern), "-c:v", "libx264", "-crf", "18",
                                   "-pix_fmt", "yuv420p", made])
                        brought.append(clean + ".mp4 (encoded here)")
            if not borrowed:
                shutil.rmtree(tmp, ignore_errors=True)
            if not brought:
                sys.exit("that run brought nothing back; its log says why:\n"
                         f"  kaggle kernels output {user}/castforge-clips -p tmp/clips")
            print(f"\n{len(brought)} files into {into}")
            for b in brought:
                print(f"  {b}")
            print("\nThey are in the app now: open the episode and look at the Output tab.")
            sys.exit(0)
        got = real.plan(folder)
        for problem in real.check(got):
            print(f"! {problem}")
        if not got["shots"]:
            sys.exit(1)
        movies = os.path.abspath(os.path.join(ROOT, "movies"))
        full = os.path.abspath(folder)
        name = (os.path.relpath(full, movies).replace(os.sep, "_")
                if full.startswith(movies + os.sep) else os.path.basename(full))
        stills_dir = os.path.join(ff, "stills", name)
        os.makedirs(stills_dir, exist_ok=True)
        grabs, later = real.stills(got), real.provisional(got)
        print(f"{len(got['shots'])} clips ({sum(r['seconds'] for r in got['shots']):.0f} s in all, "
              f"at {got['fps']} fps) from {len(grabs)} stills"
              + (f" plus {len(later)} that the first pass will replace" if later else "") + ":")
        for video, at, still in grabs + later:
            out = os.path.join(stills_dir, f"{still}.png")
            if not os.path.isfile(video):
                print(f"! {still}: {video} is not there - render the episode first")
                continue
            media.run([config.FFMPEG, "-y", "-v", "error", "-ss", f"{at:.3f}", "-i", video,
                       "-frames:v", "1", out])
        shots = os.path.join(ff, "shots", f"{name}.real.json")
        with open(shots, "w", encoding="utf-8") as f:
            json.dump(real.shot_list(got), f, indent=1)
        for row in got["shots"][:4]:
            print(f"  {row['id']:<24} {row['seconds']}s {row['frames']:>3}f  {row['motion'][:86]}...")
        if len(got["shots"]) > 4:
            print(f"  ... and {len(got['shots']) - 4} more")
        print(f"\nstills    {stills_dir}")
        print(f"shot list {shots}")
        if later:
            print(f"\nAfter the first pass, replace these {len(later)} stills with the last frame of the")
            print("clip before them and run those workflows again: that is what keeps the face, the coat")
            print("and the light from resetting at the join.")
            for carries, from_ in real.carried(got):
                print(f"  {carries}.png  <-  last frame of {from_}")
        out_dir = os.path.join("out", f"{name}-real")
        if "--gpu" in a.args:
            # Run it on the rented GPU: the shots go up as a Kaggle dataset, the kernel that reads them
            # is pushed, and Kaggle runs it headless. The 5B model and a smaller frame are not a
            # compromise about quality so much as about the card - a 15 GB T4 has no fp8 at all, so the
            # 14B pair's fp8 weights buy nothing and its 28 GB does not fit.
            only = [x for x in a.args[1:] if not x.startswith("--")]
            mode = "5b"
            area = next((a.args[i + 1] for i, x in enumerate(a.args) if x == "--area"), "480000")
            stage = os.path.join(ROOT, "tools", "kaggle", "shots")
            build = os.path.join(stage, "_build")
            shutil.rmtree(stage, ignore_errors=True)
            os.makedirs(build, exist_ok=True)
            cmd = [sys.executable, os.path.join("scripts", "wan_workflows.py"),
                   os.path.join("shots", f"{name}.real.json"), os.path.join("stills", name),
                   os.path.relpath(build, ff), "--mode", mode, "--area", area]
            if only:
                cmd += ["--only"] + only
            if subprocess.run(cmd, cwd=ff).returncode:
                sys.exit("the workflows could not be built; the lines above say why")
            for part in ("workflows", "inputs"):
                shutil.move(os.path.join(build, part), os.path.join(stage, part))
            shutil.rmtree(build, ignore_errors=True)
            made = len(os.listdir(os.path.join(stage, "workflows")))
            # The step before the clip: the render is made photographic first, or the clip is a moving
            # 3D render. A still that carries on from the clip before it is already a photograph.
            if "--no-realism" not in a.args:
                jobs = os.path.join(stage, "realism")
                os.makedirs(jobs, exist_ok=True)
                wanted = {w.split("-")[0] for w in os.listdir(os.path.join(stage, "workflows"))}
                # The same face in every shot: the character's OWN front render is already that
                # person, so there is nothing to train - it just has to travel with the job.
                faces, chars = {}, os.path.join(os.path.dirname(folder.rstrip("/\\")), "characters")
                for row in got["shots"]:
                    for who in row["on"]:
                        front = os.path.join(chars, f"{who}_preview", "front.png")
                        if who not in faces and os.path.isfile(front):
                            faces[who] = f"face_{safe_name(who)}.png"
                            shutil.copyfile(front, os.path.join(stage, "inputs", faces[who]))
                for job in real.realism(folder, got):
                    if (only and job["id"] not in only) or job["id"] not in wanted:
                        continue
                    row = next(r for r in got["shots"] if r["id"] == job["id"])
                    face = next((faces[w] for w in row["on"] if w in faces), None)
                    plain = real.still_graph(f"ff_{job['id']}_{job['still']}", job["prompt"],
                                             job["width"], job["height"], seed=job["seed"],
                                             denoise=job["denoise"], prefix=f"real/{job['id']}")
                    held = real.with_face(plain, face, real.face_hold(row["kind"]))
                    with open(os.path.join(jobs, f"{job['id']}.json"), "w", encoding="utf-8") as f:
                        # both graphs: the GPU falls back to the plain one if the face nodes are missing
                        json.dump({"id": job["id"], "denoise": job["denoise"], "face": face,
                                   "graph": held, "plain": plain}, f, indent=1)
                shots_real = len(os.listdir(jobs))
                print(f"  {shots_real} stills will be photographed first "
                      f"({real.REAL_CHECKPOINT.split('_')[0]}, moved "
                      f"{min(real.DENOISE.values())}-{max(real.DENOISE.values())} by shot size)")
                if faces:
                    print(f"  holding {len(faces)} face{'s' if len(faces) > 1 else ''} to their own "
                          f"front render: {', '.join(sorted(faces))}")
            if not made:
                sys.exit(f"no workflows were built for {only or 'this episode'}")
            user = os.environ.get("KAGGLE_USERNAME") or "ashishjiwa"
            # One archive, not two folders: the Kaggle CLI silently SKIPS folders unless you pass
            # --dir-mode, and `--dir-mode zip` makes one zip per folder, which loses the folder names
            # the kernel looks for. A single zip of the whole lot keeps the paths intact either way.
            bundle = os.path.join(stage, "castforge-shots.zip")
            parts = [p_ for p_ in ("workflows", "inputs", "realism") if os.path.isdir(os.path.join(stage, p_))]
            with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as z:
                for part in parts:
                    for fn in sorted(os.listdir(os.path.join(stage, part))):
                        z.write(os.path.join(stage, part, fn), f"{part}/{fn}")
            for part in parts:
                shutil.rmtree(os.path.join(stage, part), ignore_errors=True)
            with open(os.path.join(stage, "dataset-metadata.json"), "w", encoding="utf-8") as f:
                json.dump({"title": "CastForge shots", "id": f"{user}/castforge-shots",
                           "licenses": [{"name": "CC0-1.0"}]}, f, indent=1)
            print(f"\n{made} clips going to the rented GPU ({mode}, {area} pixels a frame), "
                  f"{os.path.getsize(bundle) / 1e6:.1f} MB.")
            listed = subprocess.run(["kaggle", "datasets", "list", "--mine", "-s", "castforge-shots"],
                                    capture_output=True, text=True)
            first = "castforge-shots" not in (listed.stdout or "")
            # No -u: a dataset is PRIVATE unless you ask otherwise, and these are stills from the film.
            push = (["kaggle", "datasets", "create", "-p", stage] if first else
                    ["kaggle", "datasets", "version", "-p", stage, "-m", f"{name}: {made} shots",
                     "--delete-old-versions"])
            # The CLI prints its failures and exits 0 anyway, so the words are what has to be read.
            said = subprocess.run(push, capture_output=True, text=True)
            print((said.stdout or "") + (said.stderr or ""), end="")
            if said.returncode or "error" in ((said.stdout or "") + (said.stderr or "")).lower():
                sys.exit("the shots could not be uploaded; the lines above say why")
            if subprocess.run([sys.executable, os.path.join(ROOT, "tools", "kaggle", "make_kernel.py"),
                               "--job", "clips"]).returncode:
                sys.exit("the kernel could not be built")
            print("\nwaiting for Kaggle to finish taking the dataset in...")
            for _ in range(30):
                time.sleep(10)
                status = subprocess.run(["kaggle", "datasets", "status", f"{user}/castforge-shots"],
                                        capture_output=True, text=True).stdout.strip()
                print(f"  {status or 'no answer yet'}")
                if "ready" in status.lower():
                    break
            kernel = os.path.join(ROOT, "tools", "kaggle", "kernel-clips")
            if subprocess.run(["kaggle", "kernels", "push", "-p", kernel]).returncode:
                sys.exit("the kernel could not be pushed; the lines above say why")
            print(f"\nIt is running on Kaggle now ({user}/castforge-clips). It has to fetch 17 GB of")
            print("Wan 2.2 first, so the first run is the slow one. To follow it and fetch the clips:")
            print(f"  kaggle kernels status {user}/castforge-clips")
            print(f"  kaggle kernels output {user}/castforge-clips -p tmp/clips")
            sys.exit(0)
        if "--run" not in a.args:
            print("\nnow build the image-to-video workflows (or add --run to do it here):")
            print(f'  cd "{ff}"')
            print(f'  python scripts/wan_workflows.py "shots/{name}.real.json" "stills/{name}" {out_dir}')
            sys.exit(0)
        print(f"\nbuilding the workflows -> {os.path.join(ff, out_dir)}")
        run = subprocess.run([sys.executable, os.path.join("scripts", "wan_workflows.py"),
                              os.path.join("shots", f"{name}.real.json"),
                              os.path.join("stills", name), out_dir], cwd=ff)
        if run.returncode:
            sys.exit("the workflows could not be built; the lines above say why")
        print("\nThese run on a GPU with ComfyUI and the Wan 2.2 models, not on this laptop:")
        print(f"  {os.path.join(ff, out_dir, 'workflows')}  (one per clip, with its still in inputs/)")
        sys.exit(0)
    elif a.command == "rig":
        # Look a built character's rig over, and optionally put right what can be put right without a
        # rebuild. Takes a name inside a movie folder, or a path to a .blend.
        if not a.args:
            sys.exit("usage: python castforge.py rig NAME|FILE.blend [MOVIE] [--fix]")
        want = a.args[0]
        path = want if want.lower().endswith(".blend") else None
        if not path:
            folder = next((x for x in a.args[1:] if not x.startswith("--")), os.path.abspath("."))
            here = [os.path.join(folder, "characters", f"{want}.blend"),
                    os.path.join(folder, f"{want}.blend")]
            path = next((x for x in here if os.path.exists(x)), here[0])
        if not os.path.exists(path):
            sys.exit(f"no such character file: {path}")
        cmd = [config.BLENDER, "-b", "--python-exit-code", "1",
               "-P", os.path.join(ROOT, "blender", "rig_check.py"), "--", path]
        if "--fix" in a.args:
            cmd.append("--fix")
        sys.exit(subprocess.run(cmd).returncode)
    elif a.command == "screen":
        # A screen test: put a built character through every move a scene can ask for and say whether it
        # is fit to put in a film. Nothing is saved - the file is left exactly as it was found.
        if not a.args:
            sys.exit("usage: python castforge.py screen NAME|FILE.blend [MOVIE] [--shots]")
        want = a.args[0]
        path = want if want.lower().endswith(".blend") else None
        if not path:
            folder = next((x for x in a.args[1:] if not x.startswith("--")), os.path.abspath("."))
            here = [os.path.join(folder, "characters", f"{want}.blend"),
                    os.path.join(folder, f"{want}.blend")]
            path = next((x for x in here if os.path.exists(x)), here[0])
        if not os.path.exists(path):
            sys.exit(f"no such character file: {path}")
        cmd = [config.BLENDER, "-b", "--python-exit-code", "1",
               "-P", os.path.join(ROOT, "blender", "screen_test.py"), "--", path]
        if "--shots" in a.args:
            cmd += ["--shots", os.path.splitext(path)[0] + "_screen"]
        sys.exit(subprocess.run(cmd).returncode)
    elif a.command == "gpu":
        # The rented GPU: a ComfyUI somewhere else (a Colab or Kaggle notebook behind a cloudflared
        # tunnel, the gpubox instance, or one on this machine). Its address is remembered here so it is
        # pasted ONCE - a tunnel gets a new address every time the notebook is started, and retyping it
        # into every command is how the wrong one ends up being used.
        import urllib.error
        sys.path.insert(0, os.path.join(ROOT, "generate"))
        import remote_gpu
        kept = os.path.join(ROOT, ".gpu.json")

        def remember(url=None):
            if url:
                json.dump({"url": url.rstrip("/"), "when": time.strftime("%Y-%m-%d %H:%M")},
                          open(kept, "w", encoding="utf-8"))
                return url.rstrip("/")
            if os.path.exists(kept):
                try:
                    return json.load(open(kept, encoding="utf-8")).get("url")
                except ValueError:
                    return None
            return None

        what = a.args[0] if a.args else "where"
        if what in ("where", "use"):
            # Two places: this laptop, or a rented GPU. core/gpu.py decides what the facts mean;
            # generate/gpu_where.py gathers them and does what it says.
            cmd = [sys.executable, os.path.join(ROOT, "generate", "gpu_where.py")]
            if what == "use":
                if len(a.args) < 2:
                    sys.exit("usage: python castforge.py gpu use local|kaggle")
                cmd += ["--use", a.args[1]]
            sys.exit(subprocess.run(cmd).returncode)
        if what == "make":
            cmd = [sys.executable, os.path.join(ROOT, "generate", "gpu_where.py")]
            if "--set" in a.args:
                cmd.append("--set")
            else:
                rest_args = [x for x in a.args[1:] if not x.startswith("--")]
                if not rest_args:
                    sys.exit('usage: python castforge.py gpu make "worn denim" --kind denim | --set')
                cmd += ["--fabric", rest_args[0]]
                for flag in ("--kind", "--name"):
                    if flag in a.args:
                        cmd += [flag, a.args[a.args.index(flag) + 1]]
            sys.exit(subprocess.run(cmd).returncode)
        rest = a.args[1:]
        if what == "connect":
            if not rest:
                sys.exit("usage: python castforge.py gpu connect https://xxxx.trycloudflare.com")
            url = remember(rest[0])
        else:
            url = next((x for x in rest if x.startswith("http")), None) or remember()
        if not url:
            sys.exit("no GPU connected yet: python castforge.py gpu connect <URL from the notebook>")

        if what in ("connect", "status"):
            try:
                seen = remote_gpu.ping(url)
            except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as e:
                print(f"CF: {url} does not answer ({e}).")
                if "502" in str(e):
                    print("CF: a 502 means the tunnel is alive but ComfyUI behind it is not - it "
                          "almost always ran out of VRAM. Re-run the notebook to restart it.")
                else:
                    print("CF: cell 5 of the notebook has to be running, and a tunnel gets a NEW "
                          "address every time it is started.")
                sys.exit(1)
            print(f"CF: connected to {url}")
            print(f"CF: {seen['devices']}, {seen['nodes']} node types, "
                  f"seamless tiling {'installed' if seen['seamless'] else 'NOT installed'}")
            print(f"CF: checkpoints: {', '.join(seen['checkpoints'][:6]) or 'none'}")
            if not seen["seamless"]:
                print("CF: cell 3 of the notebook did not finish - run it again, or every swatch will "
                      "have a seam in it")
            return
        if what == "fabric":
            if not rest:
                sys.exit('usage: python castforge.py gpu fabric "worn indigo denim" --kind denim')
            sys.exit(subprocess.run([sys.executable,
                                     os.path.join(ROOT, "generate", "remote_gpu.py"),
                                     "--url", url, "fabric", *rest]).returncode)
        sys.exit(f"gpu: connect | status | fabric  (not {what!r})")
    elif a.command == "doctor":
        sys.exit(1 if doctor() else 0)
    elif a.command == "app":
        import threading
        import webbrowser
        import uvicorn
        if not port_free(8765):
            print("CastForge is already running: http://localhost:8765 (stop it with STOP_CASTFORGE.bat)")
            webbrowser.open("http://localhost:8765")
            sys.exit(0)
        pid_file = os.path.join(ROOT, ".app.pid")
        open(pid_file, "w").write(str(os.getpid()))

        def forget_pid():
            try:
                if open(pid_file, encoding="utf-8").read().strip() == str(os.getpid()):
                    os.remove(pid_file)
            except OSError:
                pass
        atexit.register(forget_pid)
        threading.Timer(1.5, lambda: webbrowser.open("http://localhost:8765")).start()
        print("CastForge app: http://localhost:8765  (Ctrl+C to stop)")
        uvicorn.run("app.server:app", host="127.0.0.1", port=8765, log_level="warning", app_dir=ROOT)
    elif a.command == "publish":
        p = argparse.ArgumentParser(prog="castforge.py publish")
        p.add_argument("folder")
        p.add_argument("--platform", default="youtube", choices=sorted(publish.PLATFORMS))
        c = p.parse_args(a.args)
        folder = os.path.abspath(c.folder)
        if not os.path.isfile(os.path.join(folder, "scene.json")):
            sys.exit(f"no scene.json in {folder}")
        sys.exit(1 if publish.package(folder, c.platform) else 0)
    elif a.command == "status":
        st = render_status(folder_arg())
        print(st["text"] if st else "no render has been started in this folder")
    else:
        print(f"unknown command '{a.command}'\n{HELP}")
        sys.exit(1)


if __name__ == "__main__":
    main()
