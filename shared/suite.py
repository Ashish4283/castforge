"""Where everything the suite shares actually lives (pure, tested; no bpy, no network).

Three tools make art for the same films and kept discovering the same things separately:

    castforge       photo or design -> rigged 3D character -> rendered, voiced episode  (port 8765)
    forgefilms      clips, parallax, sound, assembly                                    (port 8600)
    graphic-novel   dataset, LoRA training, panels                                      (port 8700)

They already agreed on more than anybody planned: all three talk to the same ComfyUI on 8188, and the
models were already pooled by hand into one folder outside every project. This states the rest of it in
one place, so a path is written down once rather than guessed at in three apps.

Nothing here copies or moves anything. It answers "where is it", says what is missing in plain language,
and leaves the files where they are - a 22 GB model library has no business being inside a git
checkout, and the two things that genuinely belong to a project (its own code, its own output) stay
with the project.

Every path can be overridden by an environment variable, because one of these machines is a laptop,
one is a rented GPU and one is somebody's son's PC:

    CASTFORGE_MODELS     the shared model library        (default C:/AI-Models)
    CASTFORGE_COMFYUI    the ComfyUI install             (default C:/ComfyUI)
    CASTFORGE_COMFY_URL  where a running ComfyUI answers (default http://127.0.0.1:8188)
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # the castforge checkout: the suite's own home

# The other tools in the suite, as they sit under `suite/`. The port is how a person reaches each one;
# the folder is where its code is. A tool that is not installed is simply absent, never an error.
TOOLS = {
    "castforge": {"folder": ROOT, "port": 8765,
                  "does": "photo or design -> rigged 3D character -> rendered, voiced episode"},
    "forgefilms": {"folder": os.path.join(ROOT, "suite", "forgefilms"), "port": 8600,
                   "does": "clips, parallax, sound and assembly"},
    "graphic-novel": {"folder": os.path.join(ROOT, "suite", "graphic-novel"), "port": 8700,
                      "does": "dataset, LoRA training and panels"},
}

# What the models folder is expected to hold. ComfyUI's own `extra_model_paths.yaml` already names
# these, which is why they are spelled exactly as it spells them.
MODEL_KINDS = ("checkpoints", "loras", "controlnet", "clip_vision", "vae", "upscale_models",
               "embeddings", "ipadapter")

DEFAULT_MODELS = r"C:/AI-Models"
DEFAULT_COMFYUI = r"C:/ComfyUI"
DEFAULT_COMFY_URL = "http://127.0.0.1:8188"


def models(kind=None):
    """The shared model library, or one kind inside it. 22 GB, downloaded once, used by everything."""
    base = os.environ.get("CASTFORGE_MODELS", DEFAULT_MODELS)
    return os.path.join(base, kind) if kind else base


def comfyui():
    """Where ComfyUI is installed."""
    return os.environ.get("CASTFORGE_COMFYUI", DEFAULT_COMFYUI)


def comfy_url():
    """Where a running ComfyUI answers. All three tools have always used this one."""
    return os.environ.get("CASTFORGE_COMFY_URL", DEFAULT_COMFY_URL).rstrip("/")


def fabrics():
    """Cloth made on a GPU and turned into a material here: albedo, relief, roughness, and a seam score.

    CastForge dresses a 3D costume in it; a panel or a still can use the same square, which is the
    point of sharing it - the same velvet in a render and in a drawing."""
    return os.path.join(ROOT, "library", "fabrics")


def characters(movie=None):
    """Built characters. A film's cast, or every film's.

    Each one carries its design (face, body, costume), what its rig can do (`.rig.json`), what it can
    act (`.screen.json`) and how its body moves (gait). That is reference the other two tools have no
    way to work out for themselves."""
    films = os.path.join(ROOT, "movies")
    if movie:
        return os.path.join(films, movie, "characters")
    return films


def gpu_places():
    """The local-or-rented rules, which live in `core/gpu.py` and are NOT restated here.

    CastForge already works out whether a ComfyUI is answering, whether the card is big enough and
    whether Kaggle is signed in, and the facts are gathered by `generate/gpu_where.py`. Any tool in
    the suite gets the same two buttons by calling these rather than writing its own."""
    return {"rules": os.path.join(ROOT, "core", "gpu.py"),
            "facts": os.path.join(ROOT, "generate", "gpu_where.py"),
            "client": os.path.join(ROOT, "generate", "remote_gpu.py"),
            "rented": os.path.join(ROOT, "tools", "kaggle")}


def shares():
    """{what: where} - everything the suite holds in common, for a person or a check."""
    return {"models": models(), "comfyui": comfyui(), "fabrics": fabrics(),
            "characters": characters(), "gpu rules": gpu_places()["rules"]}


def check(exists=os.path.exists):
    """Plain-language problems with the shared layer; empty when there is nothing to say.

    `exists` is passed in so this can be tested without a 22 GB model library to hand."""
    out = []
    if not exists(models()):
        out.append(f"the shared model library is not at {models()} - "
                   "set CASTFORGE_MODELS to wherever it is")
    else:
        missing = [k for k in MODEL_KINDS if not exists(models(k))]
        if missing:
            out.append(f"the model library has no {', '.join(missing)} folder - "
                       "ComfyUI's extra_model_paths.yaml expects them")
    if not exists(comfyui()):
        out.append(f"ComfyUI is not at {comfyui()} - set CASTFORGE_COMFYUI to wherever it is")
    for name, tool in TOOLS.items():
        if name != "castforge" and not exists(tool["folder"]):
            out.append(f"{name} is not at {tool['folder']} - it is part of the suite and absent")
    return out


def describe(exists=os.path.exists):
    """A few lines for a person: what is in the suite, what it shares, and what is missing."""
    rows = ["the suite:"]
    for name, tool in TOOLS.items():
        there = "" if exists(tool["folder"]) else "   (not here)"
        rows.append(f"  {name:14s} :{tool['port']}  {tool['does']}{there}")
    rows.append("")
    rows.append("shared by all of them:")
    for what, where in shares().items():
        there = "" if exists(where) else "   (missing)"
        rows.append(f"  {what:12s} {where}{there}")
    problems = check(exists)
    if problems:
        rows.append("")
        for p in problems:
            rows.append(f"  ! {p}")
    return rows
