"""Write the Colab/Kaggle notebook for CastForge's ComfyUI worker."""
import io
import json
import os
import sys

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "docs", "colab", "castforge_comfyui.ipynb")


def lines(src):
    """A cell's source the way a notebook stores it: one entry a line, EACH ENDING IN A NEWLINE.

    Without them every line runs into the next when the notebook is opened - the heading joins the
    paragraph under it, bullets become one sentence, and code becomes a single unparseable line. It is
    invisible in the JSON unless you know to look, and Colab shows it immediately."""
    rows = src.strip("\n").split("\n")
    return [r + "\n" for r in rows[:-1]] + rows[-1:]


def code(src):
    return {"cell_type": "code", "metadata": {}, "execution_count": None,
            "outputs": [], "source": lines(src)}


def md(src):
    return {"cell_type": "markdown", "metadata": {}, "source": lines(src)}


TUNNEL_RE = 'r"https://[-a-z0-9]+' + chr(92) + '.trycloudflare' + chr(92) + '.com"'

cells = [
    md("""
# CastForge - ComfyUI on a rented GPU

One notebook, **Colab or Kaggle**, that stands ComfyUI up and hands your laptop a URL to talk to.

**Before you run anything, turn the GPU on.** Colab gives you a CPU-only machine by default, and
nothing here works on one.

- **Colab** - in the menu bar at the top: **Runtime > Change runtime type**. A box opens with
  "Hardware accelerator". Pick **T4 GPU**, then **Save**. (That is where "Tesla T4" comes from - it is
  the name of the card, and cell 1 prints it once the GPU is actually attached.)
- **Kaggle** - in the panel on the **right**: **Settings > Accelerator > GPU T4 x2** or P100, and
  **Settings > Internet > On**. The internet switch is off by default and nothing can be downloaded
  without it; it needs a phone-verified Kaggle account. Cell 1 stops and tells you if it is off.

Then **Runtime > Run all** in the menu, and leave the tab open. You do not have to run the cells one
at a time or understand any of them; the first run takes about ten minutes because it fetches a
checkpoint, and every run after that is about two.

Somewhere near the bottom it will print a `https://....trycloudflare.com` address in a box. **That one
line is the only thing you need.** Give it to the laptop:

```
python castforge.py gpu connect https://xxxx.trycloudflare.com
python castforge.py gpu fabric "worn indigo denim, visible twill" --kind denim --name worn_denim
```

The address is remembered after `connect`, so it is pasted once and not again. A tunnel gets a NEW
address every time the notebook is started, so run `connect` again whenever you restart it.

The laptop refuses a swatch with a seam in it, so you find that out here rather than on a character.
"""),

    md("## 1 - Where are we, and is the GPU actually on?"),
    code("""
import os, pathlib, subprocess, sys

ON_KAGGLE = os.path.isdir("/kaggle")
ON_COLAB = os.path.isdir("/content") and not ON_KAGGLE
WORK = pathlib.Path("/kaggle/working" if ON_KAGGLE else "/content")
KEEP = None                      # somewhere a dropped session cannot take with it

print("running on:", "Kaggle" if ON_KAGGLE else "Colab" if ON_COLAB else "something else")
try:
    out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                         capture_output=True, text=True).stdout.strip()
except FileNotFoundError:
    out = ""
if not out:
    raise SystemExit("No GPU. Turn the accelerator on first - see the note at the top.")
print("GPU:", out)

# And internet, which is OFF by default on Kaggle. Without it this notebook dies sixty lines deep in a
# Hugging Face traceback saying "Temporary failure in name resolution", which tells you nothing about
# where the switch is. Better to say so here, in one line, before anything has been attempted.
import socket

try:
    socket.getaddrinfo("huggingface.co", 443)
    print("internet: on")
except socket.gaierror:
    print("No internet in this session, so nothing can be downloaded.")
    if ON_KAGGLE:
        print("  Kaggle: the panel on the RIGHT > Settings > Internet > On.")
        print("  It needs a phone-verified Kaggle account.")
    else:
        print("  Colab: unusual. Try Runtime > Disconnect and delete runtime.")
    raise SystemExit("no internet")
"""),

    md("""
## 2 - Somewhere the work survives a dropped session

Free sessions end: 90 minutes idle on Colab, twelve hours at the outside. Anything written only to the
instance dies with it. On Colab that means Drive; on Kaggle, `/kaggle/working`, which is kept when you
commit the notebook.
"""),
    code("""
if ON_COLAB:
    from google.colab import drive
    drive.mount("/content/drive")
    KEEP = pathlib.Path("/content/drive/MyDrive/castforge")
else:
    KEEP = WORK / "castforge"
(KEEP / "swatches").mkdir(parents=True, exist_ok=True)
print("keeping finished work in", KEEP)
"""),

    md("## 3 - ComfyUI, the Manager, and the one node that makes a texture tile"),
    code("""
import shutil

COMFY = WORK / "ComfyUI"
NEEDS = COMFY / "requirements.txt"


# git clone with its own words kept: not a ! magic, and not -q. Both throw away the one thing worth
# having when it goes wrong. "Check the internet switch" is a guess; "destination path already exists
# and is not an empty directory" is an instruction.
def clone(url, into):
    if (into / ".git").exists() and any(into.iterdir()):
        return True
    if into.exists():
        print("clearing a half-finished", into.name)
        shutil.rmtree(into, ignore_errors=True)
    # GIT_TERMINAL_PROMPT=0 or git sits there asking for a username when a URL 404s, which on a
    # notebook looks exactly like nothing happening at all. And a timeout, so a stalled network is a
    # message rather than a cell that never finishes.
    air = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    try:
        done = subprocess.run(["git", "clone", "--depth", "1", url, str(into)],
                              capture_output=True, text=True, env=air, timeout=600)
    except subprocess.TimeoutExpired:
        print("git clone timed out after 10 minutes:", url)
        return False
    if done.returncode:
        print("git could not clone", url)
        for row in (done.stderr or done.stdout or "").strip().splitlines()[-12:]:
            print("   ", row)
        return False
    return True


# A folder that exists but has no requirements.txt in it is the wreck of an interrupted clone, and
# skipping it because the folder exists is how this cell came to fail on a missing file.
if not NEEDS.exists():
    if not clone("https://github.com/comfyanonymous/ComfyUI", COMFY) or not NEEDS.exists():
        raise SystemExit("ComfyUI is not there - git's own reason is printed above")
print("ComfyUI at", COMFY)

# Install what ComfyUI needs, but LEAVE TORCH ALONE. Colab and Kaggle both ship a torch already built
# against their own CUDA, and letting pip pull its own over the top is the usual reason ComfyUI then
# will not start at all - with an error that turns up far from the cause.
import torch as _t
print("torch already here:", _t.__version__, "cuda", _t.version.cuda)

SKIP = ("torch", "torchvision", "torchaudio")
keep = []
for line in NEEDS.read_text().splitlines():        # absolute path: never rely on the cwd
    bare = line.strip()
    if not bare or bare.startswith("#"):
        continue
    name = bare.split("=")[0].split(">")[0].split("<")[0].split("[")[0].strip().lower()
    if name not in SKIP:
        keep.append(bare)
MINE = COMFY / "requirements.castforge.txt"
MINE.write_text(chr(10).join(keep))      # chr(10), not an escape: see tools/make_colab_notebook.py
print("installing %d requirements, leaving torch alone" % len(keep))
!pip install -q -r {MINE}

NODES = COMFY / "custom_nodes"
NODES.mkdir(parents=True, exist_ok=True)


def grab(url):
    name = url.rstrip("/").split("/")[-1]
    ok = clone(url, NODES / name)
    print("node pack:", name, "ok" if ok else "FAILED - see above")
    return ok

grab("https://github.com/ltdrdata/ComfyUI-Manager")
# Without this one, a generated square has a hard join and every repeat of it shows a seam.
# remote_gpu.py refuses such a swatch, so do not skip it.
grab("https://github.com/spinagon/ComfyUI-seamless-tiling")
"""),

    md("""
## 4 - A checkpoint, downloaded ONCE and kept on Drive

Nothing is pre-installed on a Colab machine: every session starts empty. So the checkpoint is
downloaded into **Drive**, not into the session, and every run after the first one just links to it.
One 6.5 GB download, ever.

The default is **RealVisXL V5.0 Lightning** - the same checkpoint `comfyui-graphic-novel` already uses,
which is the point of picking it. It is photoreal, which is what cloth needs, and it is a Lightning
model: **6 steps instead of 28**, so a swatch takes about fifteen seconds on a free T4 rather than a
minute and a half. It is not gated, so no token is needed for it.

A gated model (FLUX.1-dev) needs a Hugging Face token. Put it in Colab's **Secrets** panel - the key
icon in the left margin - named `HF_TOKEN`, with "Notebook access" on. Never paste a token into a cell:
anything typed into a cell is saved in the notebook and goes wherever the notebook goes.

### On Kaggle, do this once and never download it again

Kaggle has no Drive, and `/kaggle/working` is wiped unless you commit. The Kaggle way is a **dataset**,
which is mounted read-only and is simply *there* - no download, no wait:

1. Run this cell once as it is. It downloads the checkpoint to `/kaggle/working`.
2. In the right-hand panel: **Output > New Dataset** - call it `castforge-models`.
3. From then on, in any notebook: **Add Input > Datasets > castforge-models**.

The cell finds it at `/kaggle/input/...` by itself after that, and cell 4 takes about a second.
"""),
    code("""
CHECKPOINTS = {
    # name on disk: (repo, file inside it, needs a token?)
    "realvis_lightning": ("SG161222/RealVisXL_V5.0_Lightning",
                          "RealVisXL_V5.0_Lightning_fp16.safetensors", False),
    "sdxl_base": ("stabilityai/stable-diffusion-xl-base-1.0",
                  "sd_xl_base_1.0.safetensors", False),
    "flux_dev": ("black-forest-labs/FLUX.1-dev", "flux1-dev.safetensors", True),
}
WANT = "realvis_lightning"        # change this if you want a different one

repo, filename, gated = CHECKPOINTS[WANT]

# Where a 6.5 GB checkpoint lives so it is fetched ONCE and not once a session. The two machines keep
# things in completely different places and getting this wrong means downloading it every time:
#
#   Colab    Google Drive. Mounted in cell 2, survives everything.
#   Kaggle   there is no Drive. /kaggle/working is wiped unless you commit the notebook, so the right
#            home is a DATASET: attach it once from the right-hand panel and it appears, already there,
#            at /kaggle/input/<name>/ with nothing to download at all. See the note under this cell.
kept = None
if ON_KAGGLE:
    for found in pathlib.Path("/kaggle/input").glob("**/" + filename):
        kept = found
        print("attached as a Kaggle dataset:", found, "- nothing to download")
        break
if kept is None:
    STORE = KEEP / "models" / "checkpoints"
    STORE.mkdir(parents=True, exist_ok=True)
    kept = STORE / filename

token = None
if gated:
    try:
        from google.colab import userdata
        token = userdata.get("HF_TOKEN")
    except Exception:
        token = os.environ.get("HF_TOKEN")
    if not token:
        raise SystemExit("%s is gated. Put a token in the Secrets panel (key icon) as HF_TOKEN, "
                         "with Notebook access on." % repo)

HOME = "Drive" if ON_COLAB else "/kaggle/working"
if kept.exists():
    print("already there: %s (%.1f GB) - nothing to download" % (kept.name,
                                                                 kept.stat().st_size / 2 ** 30))
else:
    print("first time: fetching %s into %s. About 6.5 GB, and it happens once." % (filename, HOME))
    !pip install -q huggingface_hub
    from huggingface_hub import hf_hub_download
    try:
        got = hf_hub_download(repo_id=repo, filename=filename, token=token,
                              local_dir=str(kept.parent))
    except Exception as e:
        if "name resolution" in str(e) or "LocalEntryNotFound" in type(e).__name__:
            print("Could not reach huggingface.co: this session has no internet.")
            print("  Kaggle: the panel on the RIGHT > Settings > Internet > On."
                  if ON_KAGGLE else "  Colab: Runtime > Disconnect and delete runtime, then retry.")
            raise SystemExit("no internet")
        raise
    print("fetched to", got)
    if ON_KAGGLE:
        print()
        print("DO THIS ONCE so it is never downloaded again:")
        print("  right panel > Output > New Dataset, call it castforge-models.")
        print("  After that: Add Input > Datasets > castforge-models, and this cell takes a second.")

MODELS = COMFY / "models" / "checkpoints"
MODELS.mkdir(parents=True, exist_ok=True)
link = MODELS / filename
if not link.exists():
    link.symlink_to(kept)          # ComfyUI reads it straight off Drive
print("ComfyUI will load:", filename)
print("tell the laptop:  --checkpoint", filename)
"""),

    md("""
## 5 - Start it, and open a door to it

`cloudflared` needs no account and no signup, and the address it prints works from your laptop straight
away. It is a NEW address every time you run this cell - paste the new one into `--url`.
"""),
    code("""
import re, threading, time, urllib.request

if not pathlib.Path("/usr/local/bin/cloudflared").exists():
    !wget -q -O /usr/local/bin/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
    !chmod +x /usr/local/bin/cloudflared

(KEEP / "swatches").mkdir(parents=True, exist_ok=True)
LOG = WORK / "comfy.log"
# Its output goes to a FILE, not to /dev/null. When it fails to start, the reason is in there - and
# throwing that away leaves the notebook able to say only "it did not start", which helps nobody.
comfy = subprocess.Popen([sys.executable, "main.py", "--listen", "127.0.0.1", "--port", "8188",
                          "--output-directory", str(KEEP / "swatches")],
                         cwd=str(COMFY), stdout=open(LOG, "w"), stderr=subprocess.STDOUT)

up = False
for _ in range(120):
    time.sleep(2)
    if comfy.poll() is not None:           # it exited: no point waiting another three minutes
        break
    try:
        urllib.request.urlopen("http://127.0.0.1:8188/system_stats", timeout=3)
        up = True
        break
    except Exception:
        pass

if not up:
    print("ComfyUI did not start. The last of its own output:")
    print("-" * 70)
    said = open(LOG).read().strip().splitlines()
    if not said:
        print("(it wrote nothing at all)")
    for line in said[-40:]:
        print(line)
    print("-" * 70)
    print("The whole log is at", LOG)
    raise SystemExit("ComfyUI did not start - its reason is printed above")
print("ComfyUI is up")

tunnel = subprocess.Popen(["cloudflared", "tunnel", "--url", "http://127.0.0.1:8188",
                           "--no-autoupdate"],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
for line in tunnel.stdout:
    found = re.search(TUNNEL, line)
    if found:
        print()
        print("=" * 70)
        print("  Point the laptop at this:")
        print()
        print("  python generate/remote_gpu.py --url %s ping" % found.group(0))
        print("=" * 70)
        print()
        break
threading.Thread(target=lambda: [None for _ in tunnel.stdout], daemon=True).start()
"""),

    md("""
## 5b - Or: make a whole set at once, with no tunnel

A tunnel is right when somebody is working interactively at the other end. It is the wrong shape for
Kaggle, where the strength is **Save Version > Run All**: the notebook runs headless for up to twelve
hours, nothing has to stay open, and no address can go stale.

So: list what you want, run this, and the swatches land in the output folder. Download them afterwards
(`/kaggle/working/castforge/swatches`, or the Drive folder on Colab) and the laptop turns the lot into
materials in one go:

```
python generate/make_fabric.py --folder path/to/swatches
```

Skip this cell if you are using the tunnel.
"""),
    code("""
WANTED = [
    # prompt,                                                           kind,      name
    ("worn indigo denim, visible diagonal twill weave, cotton fibres",  "denim",   "worn_denim"),
    ("cream cable knit wool jumper, chunky braided stitches",           "knit",    "cable_knit"),
    ("deep red crushed velvet, soft pile, rich nap",                    "velvet",  "red_velvet"),
    ("brown full grain leather, fine pebble texture",                   "leather", "brown_leather"),
    ("charcoal wool suiting, fine herringbone",                         "wool",    "charcoal_wool"),
    ("white cotton shirting, plain weave, fine threads",                "cotton",  "white_cotton"),
]

import json, urllib.request, time, shutil

OUT = KEEP / "swatches"
OUT.mkdir(parents=True, exist_ok=True)


def graph_for(prompt, seed=0, size=1024):
    \"\"\"Mirrors generate/remote_gpu.tiling_graph - the model AND the VAE have to wrap, not just the
    decode, and 'Modify in place' keeps a second 6.5 GB copy off a 15 GB card.\"\"\"
    quick = any(t in filename.lower() for t in ("lightning", "turbo", "lcm", "hyper"))
    steps, cfg = (6, 1.8) if quick else (28, 5.5)
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": filename}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1],
              "text": prompt + ", seamless tileable texture, flat even lighting, straight on, "
                               "fills the frame, photographic, fine detail"}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1],
              "text": "seam, border, frame, text, watermark, person, hands, shadow, vignette"}},
        "4": {"class_type": "EmptyLatentImage",
              "inputs": {"width": size, "height": size, "batch_size": 1}},
        "8": {"class_type": "SeamlessTile", "inputs": {"model": ["1", 0], "tiling": "enable",
                                                       "copy_model": "Modify in place"}},
        "9": {"class_type": "MakeCircularVAE", "inputs": {"vae": ["1", 2], "tiling": "enable",
                                                          "copy_vae": "Modify in place"}},
        "5": {"class_type": "KSampler", "inputs": {
              "seed": seed, "steps": steps, "cfg": cfg,
              "sampler_name": "dpmpp_sde" if quick else "dpmpp_2m", "scheduler": "karras",
              "denoise": 1.0, "model": ["8", 0], "positive": ["2", 0], "negative": ["3", 0],
              "latent_image": ["4", 0]}},
        "6": {"class_type": "CircularVAEDecode",
              "inputs": {"samples": ["5", 0], "vae": ["9", 0], "tiling": "enable"}},
        "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": "cf", "images": ["6", 0]}},
    }


def ask(graph, wait=600):
    body = json.dumps({"prompt": graph}).encode()
    req = urllib.request.Request("http://127.0.0.1:8188/prompt", data=body,
                                 headers={"Content-Type": "application/json"})
    pid = json.loads(urllib.request.urlopen(req, timeout=60).read())["prompt_id"]
    until = time.time() + wait
    while time.time() < until:
        time.sleep(2)
        hist = json.loads(urllib.request.urlopen(
            "http://127.0.0.1:8188/history/" + pid, timeout=30).read())
        if pid in hist:
            for node in hist[pid].get("outputs", {}).values():
                for img in node.get("images", []):
                    return img
            return None
    return None


made = []
for prompt, kind, name in WANTED:
    target = OUT / (name + ".png")
    if target.exists():
        print("already there:", target.name)
        made.append((name, kind))
        continue
    print("making", name, "...", end=" ", flush=True)
    img = ask(graph_for(prompt))
    if not img:
        print("nothing came back")
        continue
    src = COMFY / "output" / img.get("subfolder", "") / img["filename"]
    if not src.exists():
        src = (KEEP / "swatches" / img["filename"])
    shutil.copy(src, target)
    made.append((name, kind))
    print("ok")

(OUT / "manifest.json").write_text(json.dumps(
    [{"name": n, "kind": k} for n, k in made], indent=1))
print()
print("%d swatches in %s" % (len(made), OUT))
print("download that folder, then on the laptop:")
print("    python generate/make_fabric.py --folder <the folder you downloaded>")
"""),

    md("""
## 6 - Keep the session alive while you work

A free session with nothing happening in the browser is a session about to end. Run this and leave the
tab open; stop it when you are finished.
"""),
    code("""
import datetime, time

# No carriage return anywhere in here. A notebook keeps its source as JSON, and a real CR inside a
# line splits that line when the file is read back, which breaks the whole cell.
try:
    while True:
        print("alive", datetime.datetime.now().strftime("%H:%M:%S"),
              "- stop this cell when you have finished", flush=True)
        time.sleep(300)
except KeyboardInterrupt:
    print("stopped")
"""),

    md("""
---
### When it goes wrong

| what you see | what it means |
|---|---|
| `seamless tiling NOT installed` from `ping` | cell 3 did not finish - run it again |
| `the best of 3 still has a seam` | the node is installed but not being used: check `CircularVAEDecode` is in what `ping` lists |
| the address stops answering | the session dropped. Re-run cell 5 and use the NEW address |
| `cannot reach a ComfyUI` | cell 5 is not running, or you pasted the old address |
| `No internet in this session` | Kaggle: right panel > Settings > Internet > On |
| `Temporary failure in name resolution` | the same thing, seen from inside a download |
| a 502 from the tunnel | the tunnel is alive but ComfyUI died, almost always out of VRAM. Run the notebook again |
| `ComfyUI did not start` | its own output is printed right underneath. The usual cause is a custom node that will not import - delete its folder under `ComfyUI/custom_nodes` and run cell 5 again |
| `is gated` in cell 4 | put a Hugging Face token in the Secrets panel (key icon) as `HF_TOKEN`, Notebook access on - or leave `WANT` on `realvis_lightning`, which needs none |
| cell 4 downloads again every session | Drive did not mount. Run cell 2 and click through the popup |

Finished swatches are kept in `castforge/swatches` on Drive (Colab) or `/kaggle/working/castforge/swatches`
(Kaggle), so a dropped session never loses one that was already made.
"""),
]

# the regex for the tunnel address, injected rather than written inline so no escaping is lost
for c in cells:
    if c["cell_type"] == "code":
        c["source"] = [ln.replace("re.search(TUNNEL, line)",
                                  "re.search(" + TUNNEL_RE + ", line)") for ln in c["source"]]

nb = {"nbformat": 4, "nbformat_minor": 0,
      "metadata": {"accelerator": "GPU",
                   "colab": {"provenance": [], "gpuType": "T4"},
                   "kernelspec": {"display_name": "Python 3", "name": "python3"},
                   "language_info": {"name": "python"}},
      "cells": cells}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
io.open(OUT, "w", encoding="utf-8", newline="\n").write(json.dumps(nb, indent=1))
print("wrote", OUT, len(cells), "cells")

# Check it here rather than hoping somebody remembers to. The trap this catches - a real newline inside
# a cell's string literal, which splits the line and breaks the cell - has got in four times, because
# this generator's own sources are plain triple-quoted strings and a "\n" written in one becomes an
# actual newline in the output.
import subprocess as _sp

_check = os.path.join(os.path.dirname(os.path.abspath(__file__)), "check_notebook.py")
raise SystemExit(_sp.run([sys.executable, _check, OUT]).returncode)
