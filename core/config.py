"""Where CastForge's tools live, and the settings every part shares (CLI, web app, episode job, Blender scripts).

Plain Python with no third-party imports, so Blender's Python can import it as well. Paths can be overridden
with environment variables when a tool is installed somewhere else:

    CASTFORGE_BLENDER     blender.exe (default: Blender 5.2 in Program Files, else `blender` on PATH)
    CASTFORGE_AI_PYTHON   the Python with Kokoro, torch and transformers (default: `python` on PATH)
"""
import hashlib
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _blender():
    if os.environ.get("CASTFORGE_BLENDER"):
        return os.environ["CASTFORGE_BLENDER"]
    default = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
    if os.path.exists(default):
        return default
    return shutil.which("blender") or default


BLENDER = _blender()
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"
AI_PYTHON = os.environ.get("CASTFORGE_AI_PYTHON") or shutil.which("python") or "python"
VENV_PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
RHUBARB = os.path.join(ROOT, "tools", "Rhubarb-Lip-Sync-1.14.0-Windows", "rhubarb.exe")
SFX_DIR = os.path.join(ROOT, "sfx")
MOTIONS_DIR = os.path.join(ROOT, "motions", "clips")      # motion capture clips (motion.py)

# render quality: picture width (None = the scene's own "resolution"), EEVEE samples, cinematic look allowed,
# full detail (subdivision, ray tracing, motion blur). Timing, voices and lip-sync are the same at every level.
QUALITY = {
    "blocking": (480, 1, False, False),
    "draft": (640, 8, False, False),
    "standard": (960, 32, True, True),
    "final": (None, 64, True, True),
    "ultra": (1920, 128, True, True),
}
# 16:9 and wider only: the set is made from a 16:9 picture, so a narrower frame would show past its edges
ASPECTS = {"16:9": 16 / 9, "1.85:1": 1.85, "2.39:1": 2.39}


def resolution(quality, spec):
    """Picture size for a quality level and a scene: width from the quality, height from the scene's aspect."""
    width = QUALITY[quality][0]
    aspect = spec.get("aspect")
    if width is None:
        res = spec.get("resolution", [1280, 720])
        if not aspect:
            return int(res[0]), int(res[1])
        width = int(res[0])
    ratio = ASPECTS.get(aspect, 16 / 9)
    return width, int(round(width / ratio / 2)) * 2


# everything that changes a rendered scene; editing one of these files re-renders every scene once
RENDER_CODE = ["blender/scene_kit.py", "blender/props.py", "blender/acting.py", "blender/director.py",
               "blender/world.py", "blender/motion.py", "blender/motion_rig.py", "core/schema.py", "core/media.py",
               "core/config.py"]


def scene_files(scene):
    """Files a scene reads (background, characters, prop models, recorded lines): a rebuilt character or a new
    recording must re-render the scene even when scene.json did not change."""
    out = [scene.get("background")]
    out += [c.get("character") for c in scene.get("cast", {}).values()]
    out += [p.get("file") for p in scene.get("props", [])]
    out += [st.get("audio") for st in scene.get("script", [])]
    out += [os.path.join(MOTIONS_DIR, st["clip"] + ".json") for st in scene.get("script", [])
            if st.get("do") == "perform" and isinstance(st.get("clip"), str)]
    return [p for p in out if isinstance(p, str) and p]


def render_key(scene, quality, folder, finish_keys=()):
    """Fingerprint of everything that changes a scene's picture or its in-scene sound. Keys used only by the
    finishing stage (titles, transitions, grade...) are left out, so changing them never re-renders."""
    h = hashlib.sha256(json.dumps({k: v for k, v in scene.items() if k not in finish_keys},
                                  sort_keys=True).encode())
    h.update((quality or "").encode())
    for rel in RENDER_CODE:
        p = os.path.join(ROOT, rel)
        if os.path.exists(p):
            h.update(open(p, "rb").read())
    for f in scene_files(scene):
        p = f if os.path.isabs(f) else os.path.join(folder, f)
        if os.path.exists(p):
            st = os.stat(p)
            h.update(f"{os.path.normcase(os.path.abspath(p))}:{st.st_size}:{st.st_mtime_ns}".encode())
    return h.hexdigest()
