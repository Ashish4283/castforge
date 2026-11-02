"""CastForge app: a local web page around castforge.py (characters, episodes, rendering, help).

    python castforge.py app            -> http://localhost:8765

Everything still happens through castforge.py and the Blender scripts; this file only gives them a screen.
Movies live in castforge/movies/<movie>/ with characters/, sets/ and one folder per episode (scene.json).
"""
import io
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
import wave

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MOVIES = os.path.join(ROOT, "movies")
sys.path.insert(0, ROOT)
import castforge as cf  # noqa: E402

os.makedirs(MOVIES, exist_ok=True)
app = FastAPI(title="CastForge")
NAME = re.compile(r"^[a-z0-9_]{1,40}$")
NOT_EPISODES = {"characters", "sets", "references", "motion"}
jobs = {}               # character builds: id -> {"name", "movie", "state", "log", "started"}
jobs_lock = threading.Lock()


def safe(name, what="name"):
    name = (name or "").strip().lower().replace(" ", "_").replace("-", "_")
    if not NAME.match(name):
        raise HTTPException(400, f"{what} may use letters, numbers and _ only (got {name!r})")
    return name


def movie_dir(movie):
    d = os.path.join(MOVIES, safe(movie, "movie"))
    if not os.path.isdir(d):
        raise HTTPException(404, f"no movie {movie!r}")
    return d


def episode_dir(movie, ep):
    root = movie_dir(movie)
    parts = ep.split("/") if isinstance(ep, str) else []
    if not parts or any(not NAME.fullmatch(part) for part in parts):
        raise HTTPException(400, f"invalid episode path {ep!r}")
    d = os.path.join(root, *parts)
    if not os.path.isfile(os.path.join(d, "scene.json")):
        raise HTTPException(404, f"no episode {ep!r}")
    return d


def media_url(path):
    rel = os.path.relpath(path, MOVIES).replace(os.sep, "/")
    return f"/media/{rel}?t={int(os.path.getmtime(path))}"


def character_building():
    with jobs_lock:
        return any(j["state"] == "building" for j in jobs.values())


def gpu_busy():
    """What is using the GPU right now, or None."""
    owner = cf.render_lock_owner()
    if owner:
        return f"an episode render ({os.path.basename(owner)})"
    if character_building():
        return "a character build"
    return None


# --- movies ----------------------------------------------------------------------------------------
@app.get("/api/movies")
def movies():
    out = []
    for m in sorted(os.listdir(MOVIES)):
        d = os.path.join(MOVIES, m)
        if not os.path.isdir(d):
            continue
        chars = []
        cdir = os.path.join(d, "characters")
        if os.path.isdir(cdir):
            for f in sorted(os.listdir(cdir)):
                if f.endswith(".blend"):
                    n = f[:-6]
                    prev = os.path.join(cdir, f"{n}_preview", "front.png")
                    chars.append({"name": n, "preview": media_url(prev) if os.path.exists(prev) else None,
                                  "design": os.path.exists(os.path.join(cdir, f"{n}.design.json"))})
        eps = []
        for current, dirs, files in os.walk(d):
            dirs[:] = sorted(name for name in dirs if name not in NOT_EPISODES
                             and not name.startswith("."))
            if "scene.json" in files:
                rel = os.path.relpath(current, d)
                if rel != ".":
                    eps.append(rel.replace(os.sep, "/"))
        eps.sort()
        sets = []
        sdir = os.path.join(d, "sets")
        if os.path.isdir(sdir):
            for s in sorted(os.listdir(sdir)):
                pics = [p for p in sorted(os.listdir(os.path.join(sdir, s)))
                        if p.lower().endswith((".png", ".jpg", ".jpeg"))] if os.path.isdir(os.path.join(sdir, s)) else []
                if pics:
                    sets.append({"name": s, "picture": media_url(os.path.join(sdir, s, pics[0])),
                                 "path": f"../sets/{s}/{pics[0]}"})
        out.append({"name": m, "characters": chars, "episodes": eps, "sets": sets})
    return out


@app.post("/api/movie/new")
def new_movie(body: dict):
    m = safe(body.get("name"), "movie")
    d = os.path.join(MOVIES, m)
    if os.path.exists(d):
        raise HTTPException(400, f"movie {m!r} already exists")
    for sub in ("characters", "sets"):
        os.makedirs(os.path.join(d, sub))
    return {"ok": True, "movie": m}


# --- episodes ----------------------------------------------------------------------------------------
TEMPLATE = {
    "cast": {},
    "scenes": [{"id": "first_scene", "background": "../sets/<set>/background.png", "floor": "wood",
                "cast": {}, "props": [], "script": [{"do": "wait", "seconds": 1.0}]}],
}


@app.post("/api/episode/new")
def new_episode(body: dict):
    d = os.path.join(movie_dir(body.get("movie")), safe(body.get("episode"), "episode"))
    if os.path.exists(d):
        raise HTTPException(400, "that episode already exists")
    os.makedirs(d)
    json.dump(TEMPLATE, open(os.path.join(d, "scene.json"), "w", encoding="utf-8"), indent=1)
    return {"ok": True}


@app.get("/api/episode")
def episode(movie: str, episode: str):
    d = episode_dir(movie, episode)
    st = cf.render_status(d)
    video = os.path.join(d, "episode.mp4")
    shots = []
    sdir = os.path.join(d, "scenes")
    if os.path.isdir(sdir):
        for s in sorted(os.listdir(sdir)):
            shot = os.path.join(sdir, s, "shot.mp4")
            if os.path.exists(shot):
                shots.append({"name": s, "video": media_url(shot)})
    return {"scene": open(os.path.join(d, "scene.json"), encoding="utf-8").read(),
            "status": st["text"] if st else "not rendered yet", "rendering": bool(st and st["alive"]),
            "video": media_url(video) if os.path.exists(video) else None, "shots": shots}


@app.post("/api/episode/save")
def save_episode(body: dict):
    d = episode_dir(body.get("movie"), body.get("episode"))
    text = body.get("scene", "")
    try:
        json.loads(text)
    except json.JSONDecodeError as e:
        line = text.splitlines()[e.lineno - 1].strip() if e.lineno - 1 < len(text.splitlines()) else ""
        raise HTTPException(400, f"not valid JSON at line {e.lineno}: {e.msg}  ->  {line}")
    open(os.path.join(d, "scene.json"), "w", encoding="utf-8").write(text)
    return {"ok": True}


@app.post("/api/episode/voice")
async def upload_episode_voice(movie: str = Form(...), episode: str = Form(...), step: int = Form(...),
                               text: str = Form(...), file: UploadFile = File(...),
                               scene_index: int | None = Form(None)):
    d = episode_dir(movie, episode)
    if os.path.splitext(file.filename or "")[1].lower() != ".wav":
        raise HTTPException(400, "voice recordings must be WAV files")
    content = await file.read()
    try:
        with wave.open(io.BytesIO(content), "rb") as wav:
            if wav.getnframes() == 0:
                raise HTTPException(400, "the WAV file contains no audio")
    except (wave.Error, EOFError) as exc:
        raise HTTPException(400, f"invalid WAV file: {exc}") from exc

    scene_path = os.path.join(d, "scene.json")
    with open(scene_path, encoding="utf-8") as scene_file:
        scene = json.load(scene_file)
    if scene_index is None:
        target_scene = scene
    else:
        scenes = scene.get("scenes")
        if not isinstance(scenes, list) or not 0 <= scene_index < len(scenes):
            raise HTTPException(400, "scene no longer exists; reload the movie and try again")
        target_scene = scenes[scene_index]
    script = target_scene.get("script") if isinstance(target_scene, dict) else None
    if not isinstance(script, list) or not 0 <= step < len(script):
        raise HTTPException(400, "dialogue line no longer exists; reload the scene and try again")
    line = script[step]
    if not isinstance(line, dict) or line.get("do") not in ("say", "think"):
        raise HTTPException(400, "voice files can only be attached to dialogue or thought lines")
    if not text.strip():
        raise HTTPException(400, "enter the exact spoken words to support lip-sync")

    voice_dir = os.path.join(d, "voices")
    os.makedirs(voice_dir, exist_ok=True)
    filename = f"uploaded_{step:03d}_{uuid.uuid4().hex[:8]}.wav"
    audio_path = os.path.join(voice_dir, filename)
    with open(audio_path, "wb") as audio_file:
        audio_file.write(content)
    line["audio"] = os.path.join("voices", filename).replace(os.sep, "/")
    line["text"] = text.strip()
    with open(scene_path, "w", encoding="utf-8") as scene_file:
        json.dump(scene, scene_file, indent=1)
    return {"ok": True, "scene": json.dumps(scene, indent=1)}


def run_cli(*args, timeout=120):
    r = subprocess.run([sys.executable, os.path.join(ROOT, "castforge.py"), *args],
                       capture_output=True, text=True, timeout=timeout, cwd=ROOT)
    return (r.stdout + r.stderr).strip(), r.returncode


@app.post("/api/episode/check")
def check_episode(body: dict):
    d = episode_dir(body.get("movie"), body.get("episode"))
    out, code = run_cli("check", d)
    return {"ok": code == 0, "output": out}


@app.post("/api/episode/render")
def render_episode(body: dict):
    d = episode_dir(body.get("movie"), body.get("episode"))
    quality = body.get("quality", "blocking")
    if quality not in ("blocking", "draft", "standard", "final"):
        raise HTTPException(400, "unknown quality")
    busy = gpu_busy()
    if busy:
        raise HTTPException(409, f"the GPU is busy with {busy}; one GPU job at a time on this laptop")
    out, code = run_cli("check", d)
    if code != 0:
        raise HTTPException(400, "fix these first:\n" + out)
    out, code = run_cli("episode", d, "--quality", quality)
    return {"ok": code == 0, "output": out}


# --- characters --------------------------------------------------------------------------------------
def start_build(movie, name, args):
    cdir = os.path.join(movie_dir(movie), "characters")
    log_path = os.path.join(cdir, f"{name}.build.log")
    job_id = f"{movie}/{name}/{int(time.time())}"

    def run():
        with open(log_path, "w", encoding="utf-8") as logf:
            r = subprocess.run([sys.executable, os.path.join(ROOT, "castforge.py"), "character", *args,
                                "--out-dir", cdir], stdout=logf, stderr=subprocess.STDOUT, cwd=ROOT)
        with jobs_lock:
            jobs[job_id]["state"] = "done" if r.returncode == 0 else "failed"

    with jobs_lock:
        jobs[job_id] = {"name": name, "movie": movie, "state": "building", "log": log_path, "started": time.time()}
    threading.Thread(target=run, daemon=True).start()
    return job_id


@app.post("/api/character/design")
def character_from_design(body: dict):
    movie, name = safe(body.get("movie"), "movie"), safe(body.get("name"))
    try:
        design = json.loads(body.get("design", ""))
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"the design is not valid JSON (line {e.lineno}: {e.msg})")
    for key in ("gender", "age", "height_cm"):
        if key not in design:
            raise HTTPException(400, f"the design needs {key!r}")
    busy = gpu_busy()
    if busy:
        raise HTTPException(409, f"the GPU is busy with {busy}; try again when it is done")
    cdir = os.path.join(movie_dir(movie), "characters")
    path = os.path.join(cdir, f"{name}.design.json")
    json.dump(design, open(path, "w", encoding="utf-8"), indent=1)
    return {"job": start_build(movie, name, ["--design", path, name])}


@app.post("/api/character/photo")
async def character_from_photo(movie: str = Form(...), name: str = Form(...), gender: str = Form(...),
                               age: float = Form(...), height_cm: float = Form(...),
                               photo: UploadFile = File(...), face_photo: UploadFile | None = File(None)):
    movie, name = safe(movie, "movie"), safe(name)
    if gender not in ("male", "female"):
        raise HTTPException(400, "gender must be male or female")
    busy = gpu_busy()
    if busy:
        raise HTTPException(409, f"the GPU is busy with {busy}; try again when it is done")
    cdir = os.path.join(movie_dir(movie), "characters", "photos")
    os.makedirs(cdir, exist_ok=True)
    ext = os.path.splitext(photo.filename or "")[1].lower() or ".png"
    p = os.path.join(cdir, f"{name}{ext}")
    open(p, "wb").write(await photo.read())
    args = [p, name, "--gender", gender, "--age", str(age), "--height-cm", str(height_cm)]
    if face_photo is not None and face_photo.filename:
        fext = os.path.splitext(face_photo.filename)[1].lower() or ".png"
        fp = os.path.join(cdir, f"{name}_face{fext}")
        open(fp, "wb").write(await face_photo.read())
        args += ["--face-photo", fp]
    return {"job": start_build(movie, name, args)}


@app.get("/api/jobs")
def list_jobs():
    with jobs_lock:
        items = list(jobs.items())
    out = []
    for jid, j in sorted(items, key=lambda x: -x[1]["started"]):
        tail = ""
        if os.path.exists(j["log"]):
            lines = [l for l in open(j["log"], encoding="utf-8", errors="ignore").read().splitlines()
                     if l.startswith("CF:") or "Error" in l or "ERROR" in l or "ready" in l]
            tail = lines[-1] if lines else ""
        out.append({"id": jid, "name": j["name"], "movie": j["movie"], "state": j["state"], "last": tail})
    return out


# --- help ----------------------------------------------------------------------------------------------
@app.get("/api/prompts")
def prompts():
    return {"scene": cf.gemini_prompt("scene"), "character": cf.gemini_prompt("character"), "help": cf.HELP}


@app.get("/api/gpu")
def gpu():
    return {"busy": gpu_busy()}


app.mount("/media", StaticFiles(directory=MOVIES), name="media")


@app.get("/")
def index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "index.html"))


@app.exception_handler(HTTPException)
def http_error(_req, exc):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
