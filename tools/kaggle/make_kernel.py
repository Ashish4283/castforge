"""Build a Kaggle kernel from boot.py: one self-contained notebook, plus its metadata.

    python tools/kaggle/make_kernel.py                 # build it
    kaggle auth login                                  # once, on this machine
    kaggle kernels push -p tools/kaggle/kernel         # push AND run it
    kaggle kernels status ashishjiwa/castforge-gpu
    kaggle kernels output ashishjiwa/castforge-gpu -p tmp/swatches

Why self-contained rather than the notebook pulling from GitHub: with `kernels push` there is nothing
to keep in sync in the first place. The notebook is generated from `boot.py` every time, so there is
still exactly one source for the logic, and pushing it is a command rather than an upload.

And the metadata sets `enable_gpu` and `enable_internet`, which are the two switches that have cost the
most time in this whole exercise - off by default, easy to miss, and the failures they cause point
somewhere else entirely.
"""
import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
USER = os.environ.get("KAGGLE_USERNAME", "ashishjiwa")
# Two jobs, two kernels, because they want different inputs and different amounts of patience: cloth is
# a handful of 15-second squares, a clip is twenty minutes of one shot. Sharing a kernel would mean a
# cloth run waiting behind seventeen gigabytes of video models.
JOB = "clips" if "--job" in sys.argv and "clips" in sys.argv else "cloth"
SLUG = "castforge-clips" if JOB == "clips" else "castforge-gpu"
OUT = os.path.join(HERE, "kernel-clips" if JOB == "clips" else "kernel")
SHOTS = os.environ.get("CASTFORGE_SHOTS_DATASET", f"{USER}/castforge-shots")


def rows(src):
    """One entry a line, each ending in a newline, or the cell renders as one run-on blob."""
    out = src.strip("\n").split("\n")
    return [r + "\n" for r in out[:-1]] + out[-1:]


def code(src):
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": rows(src)}


def md(src):
    return {"cell_type": "markdown", "metadata": {}, "source": rows(src)}


boot = io.open(os.path.join(HERE, "boot.py"), encoding="utf-8").read()


def nothing_undefined(src):
    """Refuse to build if boot.py calls a name it never defines.

    This shipped once: an edit added `memory_now()` at two call sites and the script that was meant to
    add the function itself died on an assertion before writing. The notebook was valid Python, pushed
    cleanly, ran for twelve minutes on a rented GPU and then fell over on a NameError. Nothing but
    running it would have found that - so it is checked here instead, in a tenth of a second."""
    import ast
    import builtins

    tree = ast.parse(src)
    defined = {"__name__", "__file__"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            defined.add(node.id)
        elif isinstance(node, ast.arg):
            defined.add(node.arg)
        elif isinstance(node, ast.alias):
            defined.add((node.asname or node.name).split(".")[0])
        elif isinstance(node, ast.ExceptHandler) and node.name:
            defined.add(node.name)
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    missing = sorted(u for u in used - defined if not hasattr(builtins, u))
    if missing:
        raise SystemExit(f"boot.py uses names it never defines: {', '.join(missing)}")
    return len(used)


print("boot.py:", nothing_undefined(boot), "names, all of them defined")

cells = [
    md("""
# CastForge on a rented GPU

Generated from `tools/kaggle/boot.py` - do not edit here, edit that and push again:

```
python tools/kaggle/make_kernel.py
kaggle kernels push -p tools/kaggle/kernel
```

The GPU and internet switches are set by the metadata, not by hand.

The GPU's whole job is **one square picture of cloth**. Whether it tiles, its relief and its roughness
are all worked out on the laptop, where it is free, instant and the same every time - a rented GPU is
the flakiest part of any pipeline, so it does as little as possible.
"""),

    md("## The code (generated from boot.py)"),
    code(boot),

    md("""
## Set up: GPU, internet, ComfyUI, the checkpoint

First run fetches a 6.5 GB checkpoint. After that, attach it as a dataset (it says how) and this takes
seconds.
"""),
    code("place = setup()"),

    md("""
## Make the set

No tunnel: this runs headless, which is the thing Kaggle is good at. The swatches and a manifest land
in the output, and on the laptop:

```
kaggle kernels output %s/%s -p tmp/swatches
python generate/make_fabric.py --folder tmp/swatches/castforge/swatches
```
""" % (USER, SLUG)),
    code("batch(CLOTH, place)"),
]

if JOB == "clips":
    cells = [
        md("""
# CastForge: the shots, photographed

Generated from `tools/kaggle/boot.py` - do not edit here, edit that and push again:

```
python tools/kaggle/make_kernel.py --job clips
kaggle kernels push -p tools/kaggle/kernel-clips
```

Every decision about what a clip should contain was made on the laptop, by `shared/real.py`, which can
read the scene: who is on screen, what colour their coat is, what the light is doing, and whether a
person is speaking aloud or thinking with their mouth shut. This machine only has the GPU.

Wan 2.2 image-to-video, the **5B** model: the 14B pair is 28 GB and its fp8 buys nothing on a T4, which
has no fp8 at all. 81 frames is what it was trained on - 3.4 s at 24 fps - and the laptop has already
cut every shot to fit.
"""),
        md("## The code (generated from boot.py)"),
        code(boot),
        md("## Set up: GPU, internet, ComfyUI, Wan 2.2 and the photoreal checkpoint"),
        code("""place = check()
comfyui(place)
checkpoint("realvis_lightning", place)
wan(place)"""),
        md("""
## Make the stills real

The step the first run proved was missing. Image-to-video ANIMATES the picture it is given; it does not
restyle it, so a clip made straight from a 3D render is a moving 3D render - the wide shot gained real
wood and cloth and the close-up's face stayed computer-generated. RealVisXL runs image-to-image over each
still first, keeping the staging and the acting and replacing the look. A face is moved less than a room,
because a face has to stay the same person.
"""),
        code("make_real(place)"),
        md("""
## Make the clips

One clip per workflow in the attached dataset. They are encoded here, because eighty PNGs is a hundred
megabytes and the same clip is three. On the laptop:

```
kaggle kernels output %s/%s -p tmp/clips
```
""" % (USER, SLUG)),
        code("clips(place)"),
    ]

nb = {"nbformat": 4, "nbformat_minor": 0,
      "metadata": {"kernelspec": {"display_name": "Python 3", "name": "python3"},
                   "language_info": {"name": "python"}},
      "cells": cells}

os.makedirs(OUT, exist_ok=True)
book = os.path.join(OUT, SLUG + ".ipynb")
io.open(book, "w", encoding="utf-8", newline="\n").write(json.dumps(nb, indent=1))

# The two switches that have cost the most time here, set where they cannot be forgotten.
meta = {
    "id": f"{USER}/{SLUG}",
    "title": "CastForge Clips" if JOB == "clips" else "CastForge GPU",
    "code_file": SLUG + ".ipynb",
    "language": "python",
    "kernel_type": "notebook",
    "is_private": True,
    "enable_gpu": True,
    "enable_internet": True,
    "dataset_sources": [SHOTS] if JOB == "clips" else [],
    "competition_sources": [],
    "kernel_sources": [],
}
io.open(os.path.join(OUT, "kernel-metadata.json"), "w", encoding="utf-8",
        newline="\n").write(json.dumps(meta, indent=1))
print("wrote", book, len(cells), "cells")
print("      ", os.path.join(OUT, "kernel-metadata.json"), "- gpu on, internet on, private")

check = os.path.join(ROOT, "tools", "check_notebook.py")
raise SystemExit(subprocess.run([sys.executable, check, book]).returncode)
