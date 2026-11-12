"""CastForge app: a local web page around castforge.py (characters, episodes, rendering, help).

    python castforge.py app            -> http://localhost:8765

Everything still happens through castforge.py and the Blender scripts; this file only gives them a screen.
Movies live in castforge/movies/<movie>/ with characters/, sets/ and one folder per episode (scene.json).
"""
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
import wave

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MOVIES = os.path.join(ROOT, "movies")
LIBRARY = os.path.join(ROOT, "library")
sys.path.insert(0, ROOT)
import castforge as cf  # noqa: E402
from core import config, schema  # noqa: E402
from core.buildings import (BUILDING_CATEGORIES, BUILDING_DESIGNS, default_asset_spec,
                            describe_buildings)  # noqa: E402
from core import schema  # noqa: E402

os.makedirs(MOVIES, exist_ok=True)
os.makedirs(LIBRARY, exist_ok=True)
app = FastAPI(title="CastForge")
NAME = re.compile(r"^[a-z0-9_]{1,40}$")
NOT_EPISODES = {"characters", "sets", "references", "motion"}
jobs = {}               # character builds: id -> {"name", "movie", "state", "log", "started"}
jobs_lock = threading.Lock()


@app.get("/api/schema")
def scene_schema():
    return schema.describe()


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


def library_media_url(path):
    rel = os.path.relpath(path, LIBRARY).replace(os.sep, "/")
    return f"/library-media/{rel}?t={int(os.path.getmtime(path))}"


def library_building_assets():
    assets = []
    for category, category_title in BUILDING_CATEGORIES.items():
        category_root = os.path.join(LIBRARY, category)
        if not os.path.isdir(category_root):
            continue
        for name in sorted(os.listdir(category_root)):
            if not NAME.fullmatch(name):
                continue
            folder = os.path.join(category_root, name)
            spec_path = os.path.join(folder, "building.json")
            if not os.path.isdir(folder) or not os.path.isfile(spec_path):
                continue
            try:
                with open(spec_path, encoding="utf-8") as spec_file:
                    spec = json.load(spec_file)
            except json.JSONDecodeError as exc:
                raise HTTPException(500, f"invalid library asset {name!r}: {exc.msg}") from exc
            except OSError as exc:
                raise HTTPException(500, f"could not read library asset {name!r}: {exc}") from exc
            blend_path = os.path.join(folder, f"{name}.blend")
            preview_path = os.path.join(folder, "preview.png")
            design = BUILDING_DESIGNS.get(spec.get("template"), {})
            assets.append({
                "name": name,
                "template": spec.get("template", ""),
                "family": spec.get("family", design.get("family", "building")),
                "category": category,
                "category_title": category_title,
                "title": design.get("title", spec.get("template", "")),
                "footprint": spec.get("footprint", []),
                "floors": spec.get("floors"),
                "size": spec.get("size", []),
                "asset": library_media_url(blend_path) if os.path.isfile(blend_path) else None,
                "preview": library_media_url(preview_path) if os.path.isfile(preview_path) else None,
            })
    return assets


def character_building():
    with jobs_lock:
        return any(j["state"] == "building" for j in jobs.values())


def gpu_busy():
    """What is using the GPU right now, or None."""
    owner = cf.render_lock_owner()
    if owner:
        return f"an episode render ({os.path.basename(owner)})"
    if character_building():
        with jobs_lock:
            kinds = {j.get("kind") for j in jobs.values() if j["state"] == "building"}
        if "set" in kinds:
            return "a 3D set build"
        if "prop" in kinds:
            return "a 3D prop build"
        if "library" in kinds:
            return "a library building build"
        return "a character build"
    return cf.build_owner()      # a build started from a terminal (the app's own builds are listed above)


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
            dirs[:] = sorted(name for name in dirs if name not in NOT_EPISODES and not name.startswith(".")
                             and not (name == "scenes" and "scene.json" in files))   # generated by the job
            if "scene.json" in files:
                rel = os.path.relpath(current, d)
                if rel != ".":
                    eps.append(rel.replace(os.sep, "/"))
        eps.sort()
        sets = []
        sdir = os.path.join(d, "sets")
        if os.path.isdir(sdir):
            for s in sorted(os.listdir(sdir)):
                sd = os.path.join(sdir, s)
                pics = [p for p in sorted(os.listdir(sd))
                        if p.lower().endswith((".png", ".jpg", ".jpeg")) and p.lower() != "set_preview.png"] \
                    if os.path.isdir(sd) else []
                if pics:
                    blueprint_path = os.path.join(sd, "set_blueprint.json")
                    try:
                        with open(blueprint_path, encoding="utf-8") as blueprint_file:
                            blueprint = json.load(blueprint_file)
                    except FileNotFoundError:
                        blueprint = {"description": "", "props": []}
                    except json.JSONDecodeError as exc:
                        raise HTTPException(500, f"invalid set blueprint for {s!r}: {exc.msg}") from exc
                    except OSError as exc:
                        raise HTTPException(500, f"could not read set blueprint for {s!r}: {exc}") from exc
                    try:
                        _, blueprint = validate_set_blueprint(m, s, blueprint)
                    except HTTPException as exc:
                        raise HTTPException(500, f"invalid set blueprint for {s!r}: {exc.detail}") from exc
                    asset = os.path.join(sd, "set.blend")
                    preview = os.path.join(sd, "set_preview.png")
                    sets.append({"name": s, "picture": media_url(os.path.join(sd, pics[0])),
                                 "path": f"../sets/{s}/{pics[0]}", "blueprint": blueprint,
                                 "asset": media_url(asset) if os.path.isfile(asset) else None,
                                 "preview": media_url(preview) if os.path.isfile(preview) else None})
        props = []
        pdir = os.path.join(d, "props")
        if os.path.isdir(pdir):
            for name in sorted(os.listdir(pdir)):
                prop_dir = os.path.join(pdir, name)
                spec_path = os.path.join(prop_dir, "prop.json")
                asset = os.path.join(prop_dir, f"{name}.blend")
                preview = os.path.join(prop_dir, "preview.png")
                if not os.path.isdir(prop_dir) or not os.path.isfile(spec_path):
                    continue
                try:
                    with open(spec_path, encoding="utf-8") as spec_file:
                        spec = json.load(spec_file)
                except FileNotFoundError:
                    continue
                except json.JSONDecodeError as exc:
                    raise HTTPException(500, f"invalid prop design for {name!r}: {exc.msg}") from exc
                except OSError as exc:
                    raise HTTPException(500, f"could not read prop design for {name!r}: {exc}") from exc
                props.append({"name": name, "make": spec.get("make", ""),
                              "asset": media_url(asset) if os.path.isfile(asset) else None,
                              "preview": media_url(preview) if os.path.isfile(preview) else None,
                              "picture": media_url(os.path.join(prop_dir, spec["image"]))
                              if isinstance(spec.get("image"), str)
                              and os.path.isfile(os.path.join(prop_dir, spec["image"])) else None,
                              "size": spec.get("size")})
        out.append({"name": m, "characters": chars, "episodes": eps, "sets": sets, "props": props})
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


# --- studio: where a movie stands, step by step (story, cast, sets, storyboard, render, finish) ----------
def episode_progress(folder):
    """What exists on disk for one episode folder: scenes written, missing characters, storyboard, renders."""
    try:
        spec = json.load(open(os.path.join(folder, "scene.json"), encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"scenes": 0, "broken": True}
    scenes = spec.get("scenes") if isinstance(spec.get("scenes"), list) else [spec]
    wanted = set()
    for entry in [spec.get("cast", {})] + [sc.get("cast", {}) for sc in scenes if isinstance(sc, dict)]:
        for c in (entry or {}).values():
            if isinstance(c, dict) and isinstance(c.get("character"), str):
                wanted.add(os.path.normpath(os.path.join(folder, c["character"])))
    out_dir = os.path.join(folder, "scenes")
    rendered = sum(os.path.isfile(os.path.join(out_dir, d, "shot.sha256"))
                   for d in (os.listdir(out_dir) if os.path.isdir(out_dir) else []))
    video = os.path.join(folder, "episode.mp4")
    spec_time = os.path.getmtime(os.path.join(folder, "scene.json"))
    return {"scenes": len(scenes), "rendered": min(rendered, len(scenes)),
            "missing": sorted(os.path.basename(c) for c in wanted if not os.path.isfile(c)),
            "storyboard": os.path.isfile(os.path.join(folder, "storyboard.jpg")),
            "film": os.path.isfile(video), "current": os.path.isfile(video) and os.path.getmtime(video) >= spec_time}


@app.get("/api/movie/progress")
def movie_progress(movie: str):
    d = movie_dir(movie)
    listed = next((m for m in movies() if m["name"] == movie), None) or {"episodes": [], "characters": [], "sets": []}
    eps = {e: episode_progress(os.path.join(d, *e.split("/"))) for e in listed["episodes"]}
    missing = sorted({c for e in eps.values() for c in e.get("missing", [])})
    scenes = sum(e["scenes"] for e in eps.values())
    rendered = sum(e.get("rendered", 0) for e in eps.values())
    boards = sum(e.get("storyboard", False) for e in eps.values())
    current = sum(e.get("current", False) for e in eps.values())
    stale = [n for n, e in eps.items() if e.get("film") and not e.get("current")]
    built = sum(1 for s_ in listed["sets"] if s_.get("asset"))

    def step(key, title, tab, done, total, detail, ok=None):
        state = "done" if (ok if ok is not None else total and done >= total) else ("started" if done else "todo")
        return {"key": key, "title": title, "tab": tab, "state": state, "detail": detail}

    steps = [
        step("story", "Story", "episodes", len(eps), 1, f"{len(eps)} episodes, {scenes} scenes"
             if eps else "Write the first episode (Gemini scene prompt)", ok=bool(scenes)),
        step("cast", "Cast", "characters", len(listed["characters"]), 1,
             f"missing: {', '.join(missing)}" if missing else f"{len(listed['characters'])} characters",
             ok=bool(listed["characters"]) and not missing),
        step("sets", "Sets", "sets", len(listed["sets"]), 1,
             f"{len(listed['sets'])} sets, {built} built in 3D" if listed["sets"] else "Add a set picture",
             ok=bool(listed["sets"])),
        step("storyboard", "Storyboard", "episodes", boards, len(eps), f"{boards} of {len(eps)} episodes boarded"),
        step("render", "Render", "episodes", rendered, scenes, f"{rendered} of {scenes} scenes rendered"),
        step("finish", "Film", "episodes", current, len(eps),
             f"{current} of {len(eps)} films up to date" + (f"; changed since render: {', '.join(stale)}" if stale else "")),
    ]
    return {"movie": movie, "steps": steps, "episodes": eps,
            "next": next((s_ for s_ in steps if s_["state"] != "done"), None)}


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
    downloads = [{"name": label, "url": media_url(os.path.join(d, f))}
                 for f, label in (("episode.mp4", "Video (MP4)"), ("episode.srt", "Subtitles (SRT)"),
                                  ("episode.vtt", "Subtitles (WebVTT)"), ("episode_chapters.txt", "YouTube chapters"),
                                  ("episode_poster.jpg", "Poster"))
                 if os.path.exists(os.path.join(d, f))]
    previews = []
    if os.path.isdir(sdir):
        for s in sorted(os.listdir(sdir)):
            glb, meta = os.path.join(sdir, s, "preview.glb"), os.path.join(sdir, s, "preview.json")
            if os.path.exists(glb) and os.path.exists(meta):
                previews.append({"name": s, "glb": media_url(glb), "meta": media_url(meta)})
    board = os.path.join(d, "storyboard.jpg")
    return {"scene": open(os.path.join(d, "scene.json"), encoding="utf-8").read(),
            "status": st["text"] if st else "not rendered yet", "rendering": bool(st and st["alive"]),
            "video": media_url(video) if os.path.exists(video) else None, "shots": shots,
            "storyboard": media_url(board) if os.path.exists(board) else None, "downloads": downloads,
            "previews": previews}


@app.post("/api/episode/save")
def save_episode(body: dict):
    d = episode_dir(body.get("movie"), body.get("episode"))
    text = body.get("scene", "")
    try:
        json.loads(text)
    except json.JSONDecodeError as e:
        line = text.splitlines()[e.lineno - 1].strip() if e.lineno - 1 < len(text.splitlines()) else ""
        raise HTTPException(400, f"not valid JSON at line {e.lineno}: {e.msg}  ->  {line}")
    path = os.path.join(d, "scene.json")
    if os.path.exists(path):           # every save keeps the previous version (the newest 50), so edits can be undone
        hist = os.path.join(d, ".history")
        os.makedirs(hist, exist_ok=True)
        shutil.copy2(path, os.path.join(hist, time.strftime("scene_%Y%m%d_%H%M%S.json")))
        for old in sorted(os.listdir(hist))[:-50]:
            os.remove(os.path.join(hist, old))
    open(path, "w", encoding="utf-8").write(text)
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
    if quality not in config.QUALITY:
        raise HTTPException(400, "unknown quality")
    busy = gpu_busy()
    if busy:
        raise HTTPException(409, f"the GPU is busy with {busy}; one GPU job at a time on this laptop")
    out, code = run_cli("check", d)
    if code != 0:
        raise HTTPException(400, "fix these first:\n" + out)
    command = "preview3d" if body.get("preview3d") else "storyboard" if body.get("storyboard") else "episode"
    out, code = run_cli(command, d, "--quality", quality)
    return {"ok": code == 0, "output": out}


@app.post("/api/episode/storyboard")
def storyboard_episode(body: dict):
    """One still per shot (about a minute per scene) before committing to a render."""
    return render_episode({**body, "storyboard": True, "quality": "draft"})


@app.post("/api/episode/preview3d")
def preview3d_episode(body: dict):
    """The scene editor's 3D view of every scene (builds the scenes, renders nothing: under a minute each)."""
    return render_episode({**body, "preview3d": True, "quality": "blocking"})


@app.post("/api/episode/stop")
def stop_episode(body: dict):
    d = episode_dir(body.get("movie"), body.get("episode"))
    return {"ok": True, "output": cf.stop_job(d)}


@app.post("/api/episode/finish")
def finish_episode(body: dict):
    """Titles, transitions, grade, subtitles and sound mastering again, without rendering (CPU, minutes)."""
    d = episode_dir(body.get("movie"), body.get("episode"))
    out, code = run_cli("finish", d, timeout=1800)
    if code != 0:
        raise HTTPException(400, out.splitlines()[-1] if out else "finishing failed")
    return {"ok": True, "output": out}


@app.get("/api/episode/log")
def episode_log(movie: str, episode: str, tail: int = 60):
    d = episode_dir(movie, episode)
    log_path = os.path.join(d, "render.log")
    if not os.path.exists(log_path):
        return {"log": ""}
    lines = open(log_path, encoding="utf-8", errors="ignore").read().splitlines()
    keep = [ln for ln in lines if ln.startswith("CF:") or "Error" in ln or "Traceback" in ln]
    return {"log": "\n".join(keep[-tail:])}


@app.post("/api/voice/preview")
def voice_preview(body: dict):
    """Hear a line with a voice before rendering (Kokoro on the CPU, so it works during a render)."""
    text, voice = (body.get("text") or "").strip(), body.get("voice") or "af_heart"
    if not text:
        raise HTTPException(400, "write the line first")
    if voice not in schema.VOICES:
        raise HTTPException(400, f"unknown voice {voice}")
    try:
        wav = cf.speak(text, voice, float(body.get("speed") or 1.0), body.get("fx") or "clean")
    except Exception as e:
        raise HTTPException(500, f"could not speak the line: {e}")
    return FileResponse(wav, media_type="audio/wav")


@app.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """The words in an uploaded recording (faster-whisper), so lip-sync gets its transcript."""
    import tempfile
    tmp = os.path.join(tempfile.gettempdir(), f"castforge_upload_{uuid.uuid4().hex[:8]}.wav")
    open(tmp, "wb").write(await file.read())
    try:
        r = subprocess.run([config.AI_PYTHON, os.path.join(ROOT, "generate", "transcribe.py"), tmp],
                           capture_output=True, text=True, timeout=300, encoding="utf-8", errors="replace")
    finally:
        os.remove(tmp)
    if r.returncode != 0:
        raise HTTPException(500, "transcription failed (is faster-whisper installed? python castforge.py doctor)")
    return {"text": r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""}


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
        jobs[job_id] = {"name": name, "movie": movie, "kind": "character", "state": "building",
                        "log": log_path, "started": time.time()}
    threading.Thread(target=run, daemon=True).start()
    return job_id


def start_set_build(movie, name, set_dir):
    log_path = os.path.join(set_dir, "set_build.log")
    job_id = f"{movie}/set/{name}/{int(time.time())}"

    def run():
        with open(log_path, "w", encoding="utf-8") as logf:
            result = subprocess.run([sys.executable, os.path.join(ROOT, "castforge.py"), "set-build", set_dir],
                                   stdout=logf, stderr=subprocess.STDOUT, cwd=ROOT)
        with jobs_lock:
            jobs[job_id]["state"] = "done" if result.returncode == 0 else "failed"

    with jobs_lock:
        jobs[job_id] = {"name": f"3D set: {name}", "movie": movie, "kind": "set",
                        "state": "building", "log": log_path, "started": time.time()}
    threading.Thread(target=run, daemon=True).start()
    return job_id


def start_prop_build(movie, name, prop_dir):
    log_path = os.path.join(prop_dir, "build.log")
    job_id = f"{movie}/prop/{name}/{int(time.time())}"

    def run():
        with open(log_path, "w", encoding="utf-8") as logf:
            result = subprocess.run([sys.executable, os.path.join(ROOT, "castforge.py"), "prop-build", prop_dir],
                                   stdout=logf, stderr=subprocess.STDOUT, cwd=ROOT)
        with jobs_lock:
            jobs[job_id]["state"] = "done" if result.returncode == 0 else "failed"

    with jobs_lock:
        jobs[job_id] = {"name": f"3D prop: {name}", "movie": movie, "kind": "prop",
                        "state": "building", "log": log_path, "started": time.time()}
    threading.Thread(target=run, daemon=True).start()
    return job_id


def validate_set_blueprint(movie, set_name, blueprint):
    set_dir = os.path.join(movie_dir(movie), "sets", set_name)
    if not os.path.isdir(set_dir):
        raise HTTPException(404, f"no set {set_name!r}")
    if not isinstance(blueprint, dict) or not isinstance(blueprint.get("props"), list):
        raise HTTPException(400, "set details must contain a props list")
    description = blueprint.get("description", "")
    if not isinstance(description, str) or len(description) > 2000:
        raise HTTPException(400, "set description must be text with at most 2000 characters")
    names = {entry for entry in os.listdir(os.path.join(movie_dir(movie), "sets"))
             if os.path.isdir(os.path.join(movie_dir(movie), "sets", entry))}
    if len(blueprint["props"]) > 100:
        raise HTTPException(400, "a set blueprint can contain at most 100 objects")
    props, identifiers = [], set()
    for index, prop in enumerate(blueprint["props"], 1):
        if not isinstance(prop, dict):
            raise HTTPException(400, f"set object {index} must be an object")
        object_id = prop.get("id")
        if not isinstance(object_id, str) or not NAME.fullmatch(object_id) or object_id in identifiers:
            raise HTTPException(400, f"set object {index} needs a unique id using letters, numbers and _")
        if not isinstance(prop.get("make"), str) or prop["make"] not in schema.PROP_TYPES:
            raise HTTPException(400, f"set object {object_id!r} has an unknown type")
        kind = prop["make"]
        position = prop.get("position", [0, 0])
        size = prop.get("size")
        if size is None:
            size = list(schema.PROP_TYPES[kind][0])
        rotation = prop.get("rotation", 0)
        if not schema._is_point(position) or not all(math.isfinite(value) for value in position):
            raise HTTPException(400, f"{object_id}: position must contain two finite numbers")
        if (not isinstance(size, list) or len(size) != 3
                or any(not isinstance(value, (int, float)) or isinstance(value, bool)
                       or not math.isfinite(value) or value <= 0 for value in size)):
            raise HTTPException(400, f"{object_id}: size must contain three positive finite numbers")
        if (not isinstance(rotation, (int, float)) or isinstance(rotation, bool)
                or not math.isfinite(rotation)):
            raise HTTPException(400, f"{object_id}: rotation must be a finite number")
        for field in ("picture_rect", "outside_rect"):
            rect = prop.get(field)
            if rect is not None and not schema._is_rect(rect):
                raise HTTPException(400, f"{object_id}: {field} must be [left, top, right, bottom] fractions")
        mask = prop.get("picture_mask")
        if mask is not None and (mask != f"masks/{object_id}.png"
                                 or not os.path.isfile(os.path.join(set_dir, "masks", f"{object_id}.png"))):
            raise HTTPException(400, f"{object_id}: picture_mask must be masks/{object_id}.png, saved with the region editor")
        if prop.get("outside_set") is not None:
            target = prop["outside_set"]
            if (kind != "door" or not isinstance(target, str) or target not in names
                    or not any(name.lower().endswith((".png", ".jpg", ".jpeg"))
                               and name.lower() != "set_preview.png"
                               for name in os.listdir(os.path.join(movie_dir(movie), "sets", target)))):
                raise HTTPException(400, f"{object_id}: linked outside set must name an existing set on a door")
        identifiers.add(object_id)
        props.append({**prop, "position": position, "size": size, "rotation": rotation})
    if not any(f.lower().endswith((".png", ".jpg", ".jpeg")) and f.lower() != "set_preview.png"
               for f in os.listdir(set_dir)):
        raise HTTPException(400, "add a background image to this set before building it")
    saved = {"version": 1, "description": description, "props": props}
    return set_dir, saved


def save_set_blueprint(set_dir, saved):
    blueprint_path = os.path.join(set_dir, "set_blueprint.json")
    temporary_path = blueprint_path + ".tmp"
    with open(temporary_path, "w", encoding="utf-8") as blueprint_file:
        json.dump(saved, blueprint_file, indent=1)
    os.replace(temporary_path, blueprint_path)


@app.post("/api/set/new")
async def new_set(movie: str = Form(...), name: str = Form(...), picture: UploadFile = File(...)):
    """A new set from one picture (uploaded, pasted or dropped in the app): sets/<name>/background.<ext>."""
    set_dir = os.path.join(movie_dir(safe(movie, "movie")), "sets", safe(name, "set"))
    if os.path.exists(set_dir):
        raise HTTPException(400, f"set {name!r} already exists")
    ext = os.path.splitext(picture.filename or "")[1].lower()
    if ext not in (".png", ".jpg", ".jpeg"):
        ext = ".png"
    content = await picture.read()
    if not content:
        raise HTTPException(400, "the picture is empty")
    os.makedirs(set_dir)
    open(os.path.join(set_dir, f"background{ext}"), "wb").write(content)
    return {"ok": True, "set": name}


@app.post("/api/set/blueprint")
def save_set(body: dict):
    movie, set_name = safe(body.get("movie"), "movie"), safe(body.get("set"), "set")
    set_dir, saved = validate_set_blueprint(movie, set_name, body.get("blueprint"))
    save_set_blueprint(set_dir, saved)
    return {"ok": True, "blueprint": saved}


def set_picture(set_dir):
    pics = sorted(p for p in os.listdir(set_dir)
                  if p.lower().endswith((".png", ".jpg", ".jpeg")) and p.lower() != "set_preview.png")
    if not pics:
        raise HTTPException(400, "this set has no picture")
    return os.path.join(set_dir, pics[0])


@app.post("/api/set/mask")
async def set_mask(movie: str = Form(...), set: str = Form(...), id: str = Form(...), mask: UploadFile = File(...)):
    """Save one object's region (drawn in the region editor) at the set picture's size; returns its box."""
    import numpy as np
    from core import set_masks
    set_dir = os.path.join(movie_dir(movie), "sets", safe(set, "set"))
    object_id = safe(id, "object id")
    size = Image.open(set_picture(set_dir)).size
    try:
        drawn = Image.open(io.BytesIO(await mask.read())).convert("L").resize(size, Image.NEAREST)
    except (UnidentifiedImageError, OSError):
        raise HTTPException(400, "the region must be a PNG picture")
    m = set_masks.quantize(np.array(drawn))
    os.makedirs(os.path.join(set_dir, "masks"), exist_ok=True)
    path = os.path.join(set_dir, "masks", f"{object_id}.png")
    Image.fromarray(m).save(path)
    return {"mask": f"masks/{object_id}.png", "url": media_url(path), "rect": set_masks.bbox(m)}


@app.post("/api/set/fill")
def set_fill(body: dict):
    """The object cut out with its hidden parts filled from its own colours (masks/<id>_filled.png)."""
    import numpy as np
    from core import set_masks
    set_dir = os.path.join(movie_dir(body.get("movie")), "sets", safe(body.get("set"), "set"))
    object_id = safe(body.get("id"), "object id")
    path = os.path.join(set_dir, "masks", f"{object_id}.png")
    if not os.path.isfile(path):
        raise HTTPException(400, "save this object's region first")
    m = set_masks.quantize(np.array(Image.open(path).convert("L")))
    rgb = np.array(Image.open(set_picture(set_dir)).convert("RGB").resize(m.shape[::-1]))
    out = os.path.join(set_dir, "masks", f"{object_id}_filled.png")
    Image.fromarray(set_masks.fill_hidden(rgb, m)).save(out)
    return {"url": media_url(out), "hidden": int((m == set_masks.HIDDEN).sum())}


@app.post("/api/set/build")
def build_set(body: dict):
    movie, set_name = safe(body.get("movie"), "movie"), safe(body.get("set"), "set")
    set_dir, saved = validate_set_blueprint(movie, set_name, body.get("blueprint"))
    busy = gpu_busy()
    if busy:
        raise HTTPException(409, f"the GPU is busy with {busy}; try again when it is done")
    save_set_blueprint(set_dir, saved)
    return {"job": start_set_build(movie, set_name, set_dir), "blueprint": saved}


def start_library_building(category, name, folder):
    log_path = os.path.join(folder, "build.log")
    job_id = f"library/{category}/{name}/{int(time.time())}"

    def run():
        with open(log_path, "w", encoding="utf-8") as logf:
            result = subprocess.run([sys.executable, os.path.join(ROOT, "castforge.py"),
                                     "building-build", folder], stdout=logf, stderr=subprocess.STDOUT, cwd=ROOT)
        with jobs_lock:
            jobs[job_id]["state"] = "done" if result.returncode == 0 else "failed"

    with jobs_lock:
        jobs[job_id] = {"name": f"Library asset: {name}", "movie": "", "kind": "library",
                        "category": category, "state": "building", "log": log_path, "started": time.time()}
    threading.Thread(target=run, daemon=True).start()
    return job_id


@app.get("/api/library/buildings")
def get_library_buildings():
    return {
        "categories": [{"id": category, "title": title} for category, title in BUILDING_CATEGORIES.items()],
        "templates": describe_buildings(),
        "assets": library_building_assets(),
    }


@app.post("/api/library/building")
@app.post("/api/library/asset")
def build_library_building(body: dict):
    template = body.get("template")
    if not isinstance(template, str) or template not in BUILDING_DESIGNS:
        raise HTTPException(400, "choose a supported starter building design")
    template_design = BUILDING_DESIGNS[template]
    name = safe(body.get("name"), "building name")
    family = template_design.get("family", "building")
    category = template_design.get("category", "buildings")

    def number(field):
        value = body.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            raise HTTPException(400, f"{field} must be a finite number")
        return float(value)

    width, depth = number("width"), number("depth")
    if width <= 0 or depth <= 0 or width > 100 or depth > 100:
        raise HTTPException(400, "asset width and depth must be between 0 and 100 metres")
    floors = body.get("floors", 1)
    if not isinstance(floors, int) or isinstance(floors, bool) or not 1 <= floors <= 10:
        raise HTTPException(400, "building floors must be a whole number from 1 to 10")
    height = number("height") if family != "building" else 0
    if family != "building" and (height <= 0 or height > 100):
        raise HTTPException(400, "asset height must be greater than 0 and at most 100 metres")
    wall_color, roof_color = body.get("wall_color"), body.get("roof_color")
    for field, color in (("wall_color", wall_color), ("roof_color", roof_color)):
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise HTTPException(400, f"{field} must be a six-digit hex color")
    busy = gpu_busy()
    if busy:
        raise HTTPException(409, f"the GPU is busy with {busy}; try again when it is done")
    folder = os.path.join(LIBRARY, category, name)
    if os.path.isfile(os.path.join(folder, f"{name}.blend")):
        raise HTTPException(409, f"a library building named {name!r} already exists")
    with jobs_lock:
        if any(job["kind"] == "library" and job["state"] == "building"
               and job.get("category") == category and job["name"] == f"Library asset: {name}"
               for job in jobs.values()):
            raise HTTPException(409, f"a library asset named {name!r} is already building")
    os.makedirs(folder, exist_ok=True)
    spec = default_asset_spec(template, name)
    spec.update({"footprint": [width, depth], "floors": floors, "size": [width, depth, height or 0],
                 "wall_color": wall_color.lower(), "roof_color": roof_color.lower()})
    temporary_spec = os.path.join(folder, "building.json.tmp")
    with open(temporary_spec, "w", encoding="utf-8") as spec_file:
        json.dump(spec, spec_file, indent=1)
    os.replace(temporary_spec, os.path.join(folder, "building.json"))
    return {"job": start_library_building(category, name, folder)}


@app.post("/api/prop/build")
async def build_prop(movie: str = Form(...), name: str = Form(...), make: str = Form(...),
                     width: float = Form(...), depth: float = Form(...), height: float = Form(...),
                     material: str = Form(...), color: str = Form(...), photo: UploadFile = File(...)):
    movie, name = safe(movie, "movie"), safe(name, "prop")
    if make not in schema.PROP_TYPES or not schema.PROP_TYPES[make][0]:
        raise HTTPException(400, f"unknown or unsupported prop type {make!r}")
    dimensions = (width, depth, height)
    if any(not math.isfinite(value) or value <= 0 or value > 50 for value in dimensions):
        raise HTTPException(400, "prop dimensions must be finite values between 0 and 50 metres")
    if material not in schema.MATERIALS:
        raise HTTPException(400, f"unknown material {material!r}")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise HTTPException(400, "prop color must be a six-digit hex color")
    content = await photo.read(20 * 1024 * 1024 + 1)
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(413, "reference images must be 20 MB or smaller")
    try:
        with Image.open(io.BytesIO(content)) as reference:
            reference.verify()
            extension = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}.get(reference.format)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(400, "upload a valid PNG, JPEG, or WEBP reference image") from exc
    if not extension:
        raise HTTPException(400, "upload a PNG, JPEG, or WEBP reference image")
    busy = gpu_busy()
    if busy:
        raise HTTPException(409, f"the GPU is busy with {busy}; try again when it is done")
    prop_dir = os.path.join(movie_dir(movie), "props", name)
    os.makedirs(prop_dir, exist_ok=True)
    image_name = f"reference{extension}"
    temporary_image = os.path.join(prop_dir, image_name + ".tmp")
    with open(temporary_image, "wb") as image_file:
        image_file.write(content)
    os.replace(temporary_image, os.path.join(prop_dir, image_name))
    spec_path = os.path.join(prop_dir, "prop.json")
    temporary_spec = spec_path + ".tmp"
    with open(temporary_spec, "w", encoding="utf-8") as spec_file:
        json.dump({"name": name, "make": make, "size": list(dimensions), "material": material,
                   "color": color.lower(), "image": image_name}, spec_file, indent=1)
    os.replace(temporary_spec, spec_path)
    return {"job": start_prop_build(movie, name, prop_dir)}


@app.post("/api/character/design")
def character_from_design(body: dict):
    movie, name = safe(body.get("movie"), "movie"), safe(body.get("name"))
    try:
        design = json.loads(body.get("design", ""))
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"the design is not valid JSON (line {e.lineno}: {e.msg})")
    problems = schema.check_design(design)
    if problems:
        raise HTTPException(400, "; ".join(problems))
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
                               photo: UploadFile = File(...), face_photo: UploadFile | None = File(None),
                               costume: str = Form("")):
    movie, name = safe(movie, "movie"), safe(name)
    if gender not in ("male", "female"):
        raise HTTPException(400, "gender must be male or female")
    if costume and costume not in schema.COSTUMES:
        raise HTTPException(400, f"no costume {costume!r} (choose {', '.join(schema.COSTUMES)})")
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
    # the design editor starts from this; a costume adds its pieces (the photo still gives face and colours)
    design = {"name": name, "gender": gender, "age": age, "height_cm": height_cm, "use_photo": True}
    for key, value in schema.COSTUMES.get(costume, {}).items():
        if not key.startswith("outfit.") and key != "build":
            design_set(design, key, value)
    dpath = os.path.join(movie_dir(movie), "characters", f"{name}.design.json")
    json.dump(design, open(dpath, "w", encoding="utf-8"), indent=1)
    return {"job": start_build(movie, name, args + ["--design", dpath])}


def design_set(design, key, value):
    *path, last = key.split(".")
    for part in path:
        design = design.setdefault(part, {})
    design[last] = value


def character_files(movie, name):
    """A character's folder, its body photo and its face photo (None when there is none)."""
    cdir = os.path.join(movie_dir(movie), "characters")

    def photo(stem):
        return next((p for ext in (".png", ".jpg", ".jpeg", ".webp")
                     if os.path.exists(p := os.path.join(cdir, "photos", stem + ext))), None)
    return cdir, photo(name), photo(f"{name}_face")


@app.get("/api/character")
def character(movie: str, name: str):
    """One character for the design editor: its design (photo colours filled in), photos, previews, last build."""
    name = safe(name)
    cdir, photo, face = character_files(movie, name)
    dpath, spath = os.path.join(cdir, f"{name}.design.json"), os.path.join(cdir, f"{name}.spec.json")
    if not any(os.path.exists(p) for p in (dpath, spath, os.path.join(cdir, f"{name}.blend"))):
        raise HTTPException(404, f"no character {name!r}")
    try:
        design = json.load(open(dpath, encoding="utf-8")) if os.path.exists(dpath) else {}
    except ValueError:
        design = {}
    if photo and os.path.exists(spath):
        spec = json.load(open(spath, encoding="utf-8"))
        cols = spec.get("colours") or {}
        for key, col in (("skin", "skin"), ("hair.color", "hair"), ("outfit.top", "top"),
                         ("outfit.bottom", "bottom"), ("outfit.shoes", "shoes")):
            if cols.get(col) and schema.design_get(design, key) in (None, ""):
                design_set(design, key, "#%02x%02x%02x" % tuple(int(c) for c in cols[col]))
        for key, value in (("outfit.garment", (spec.get("clothing") or {}).get("garment")),
                           ("outfit.sleeves", (spec.get("clothing") or {}).get("sleeves"))):
            if value and schema.design_get(design, key) in (None, ""):
                design_set(design, key, value)
    previews = {v: media_url(f) for v in ("front", "side", "back")
                if os.path.exists(f := os.path.join(cdir, f"{name}_preview", f"{v}.png"))}
    log = os.path.join(cdir, f"{name}.build.log")
    lines = [l[4:] for l in open(log, encoding="utf-8", errors="ignore").read().splitlines()
             if l.startswith("CF:") and "face shape" not in l] if os.path.exists(log) else []
    return {"name": name, "design": design, "photo": media_url(photo) if photo else None,
            "face": media_url(face) if face else None, "previews": previews, "log": lines[-14:]}


@app.post("/api/character/rebuild")
def character_rebuild(body: dict):
    """Rebuild a character from its edited design; with use_photo, the photo still gives face and body."""
    movie, name = safe(body.get("movie"), "movie"), safe(body.get("name"))
    design = body.get("design")
    problems = schema.check_design(design)
    if problems:
        raise HTTPException(400, "; ".join(problems))
    busy = gpu_busy()
    if busy:
        raise HTTPException(409, f"the GPU is busy with {busy}; try again when it is done")
    cdir, photo, face = character_files(movie, name)
    dpath = os.path.join(cdir, f"{name}.design.json")
    use_photo = bool(body.get("use_photo") and photo)
    json.dump({**design, "name": name, "use_photo": use_photo}, open(dpath, "w", encoding="utf-8"), indent=1)
    if use_photo:
        args = [photo, name, "--design", dpath] + (["--face-photo", face] if face else [])
    else:
        args = ["--design", dpath, name]
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
        out.append({"id": jid, "name": j["name"], "movie": j["movie"], "kind": j.get("kind", "character"),
                    "state": j["state"], "last": tail})
    return out


# --- help ----------------------------------------------------------------------------------------------
@app.get("/api/prompts")
def prompts():
    return {"scene": cf.gemini_prompt("scene"), "character": cf.gemini_prompt("character"), "help": cf.HELP}


@app.get("/api/gpu")
def gpu():
    return {"busy": gpu_busy()}


app.mount("/media", StaticFiles(directory=MOVIES), name="media")
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
app.mount("/library-media", StaticFiles(directory=LIBRARY), name="library-media")


UI = os.path.join(os.path.dirname(__file__), "ui")      # the React app, built from web/ (npm run build)
if os.path.isdir(os.path.join(UI, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(UI, "assets")), name="ui-assets")


@app.get("/")
def index():
    built = os.path.join(UI, "index.html")
    return FileResponse(built if os.path.exists(built) else os.path.join(os.path.dirname(__file__), "index.html"))


@app.get("/classic")
def classic():
    """The previous page, kept while the React app settles in."""
    return FileResponse(os.path.join(os.path.dirname(__file__), "index.html"))


@app.exception_handler(HTTPException)
def http_error(_req, exc):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
