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
OUT = os.path.join(HERE, "kernel")
USER = os.environ.get("KAGGLE_USERNAME", "ashishjiwa")
SLUG = "castforge-gpu"


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
    "title": "CastForge GPU",
    "code_file": SLUG + ".ipynb",
    "language": "python",
    "kernel_type": "notebook",
    "is_private": True,
    "enable_gpu": True,
    "enable_internet": True,
    "dataset_sources": [],
    "competition_sources": [],
    "kernel_sources": [],
}
io.open(os.path.join(OUT, "kernel-metadata.json"), "w", encoding="utf-8",
        newline="\n").write(json.dumps(meta, indent=1))
print("wrote", book, len(cells), "cells")
print("      ", os.path.join(OUT, "kernel-metadata.json"), "- gpu on, internet on, private")

check = os.path.join(ROOT, "tools", "check_notebook.py")
raise SystemExit(subprocess.run([sys.executable, check, book]).returncode)
