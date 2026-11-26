"""Stand ComfyUI up on a rented GPU, and make cloth with it.

This is the whole notebook, as a module. The notebook that runs it is three lines long and never
changes, so fixing something here needs no re-upload of anything: pull, and run it again.

Being a real .py file rather than strings inside notebook JSON also means it can be read, diffed and
tested like code - and that the escaping trap which bit the notebook five times (a newline inside a
cell's string literal splits the line and breaks the cell) simply cannot happen.

    import boot
    boot.setup()                      # GPU, internet, ComfyUI, the checkpoint
    boot.tunnel()                     # ...and an address the laptop can talk to
    boot.batch(boot.CLOTH)            # ...or make a whole set with no tunnel at all
"""
import json
import os
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request

COMFY_REPO = "https://github.com/comfyanonymous/ComfyUI"
NODE_PACKS = [
    "https://github.com/ltdrdata/ComfyUI-Manager",
    # Without this one a generated square has a hard join, and every repeat of it shows a seam.
    # The laptop refuses such a swatch, so there is no point running without it.
    "https://github.com/spinagon/ComfyUI-seamless-tiling",
    # Holds a re-imagined still to a face the character already has, so the same person survives the
    # cut. Without it the face nodes are missing and make_real() falls back to the plain graph.
    "https://github.com/cubiq/ComfyUI_IPAdapter_plus",
]
CHECKPOINTS = {
    "realvis_lightning": ("SG161222/RealVisXL_V5.0_Lightning",
                          "RealVisXL_V5.0_Lightning_fp16.safetensors", False),
    "sdxl_base": ("stabilityai/stable-diffusion-xl-base-1.0",
                  "sd_xl_base_1.0.safetensors", False),
    "flux_dev": ("black-forest-labs/FLUX.1-dev", "flux1-dev.safetensors", True),
}
CLOTH = [
    ("worn indigo denim, visible diagonal twill weave, cotton fibres", "denim", "worn_denim"),
    ("cream cable knit wool jumper, chunky braided stitches", "knit", "cable_knit"),
    ("deep red crushed velvet, soft pile, rich nap", "velvet", "red_velvet"),
    ("brown full grain leather, fine pebble texture", "leather", "brown_leather"),
    ("charcoal wool suiting, fine herringbone", "wool", "charcoal_wool"),
    ("white cotton shirting, plain weave, fine threads", "cotton", "white_cotton"),
]
PORT = 8188
URL = f"http://127.0.0.1:{PORT}"
_running = {}


def say(*a):
    print(*a, flush=True)


# --- where are we ---------------------------------------------------------------------------------------

def where():
    """{on, batch, work, keep, comfy} - which machine this is and where things go on it.

    Colab and Kaggle keep things in completely different places, and getting it wrong means fetching a
    6.9 GB checkpoint every session.

    And on Kaggle there is a second question: is this a person at a keyboard, or a committed run?
    EVERYTHING under /kaggle/working is saved as the run's output and has to be downloaded to be read.
    Put ComfyUI and a 6.9 GB model there on a headless run and the output is seven gigabytes of things
    nobody wants, for the sake of six pictures. So a committed run builds in /tmp, which is not saved,
    and writes only the swatches where they will be kept."""
    kaggle = os.path.isdir("/kaggle")
    colab = os.path.isdir("/content") and not kaggle
    batch = kaggle and os.environ.get("KAGGLE_KERNEL_RUN_TYPE", "").lower() == "batch"
    work = pathlib.Path("/kaggle/working" if kaggle else "/content" if colab else ".")
    scratch = pathlib.Path("/tmp/castforge") if batch else work
    return {"on": "kaggle" if kaggle else "colab" if colab else "somewhere else",
            "batch": batch, "work": work,
            # what is KEPT: on a committed run, only this is saved
            "keep": work / "castforge",
            # what is only needed while it runs
            "comfy": scratch / "ComfyUI", "scratch": scratch}


def check(place=None):
    """Stop now, with one line somebody can act on, if the GPU or the internet is missing."""
    place = place or where()
    say("running on:", place["on"], "(committed run)" if place.get("batch") else "")
    if place.get("batch"):
        say("building in /tmp; only the swatches will be saved as output")
    try:
        card = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                              capture_output=True, text=True).stdout.strip()
    except FileNotFoundError:
        card = ""
    if not card:
        raise SystemExit("No GPU. Kaggle: Settings > Accelerator > GPU T4 x2. "
                         "Colab: Runtime > Change runtime type > T4 GPU.")
    say("GPU:", card)
    try:
        socket.getaddrinfo("huggingface.co", 443)
    except socket.gaierror:
        raise SystemExit("No internet in this session, so nothing can be downloaded. "
                         "Kaggle: the panel on the RIGHT > Settings > Internet > On "
                         "(it needs a phone-verified account).")
    say("internet: on")
    return place


# --- getting the pieces ---------------------------------------------------------------------------------

def clone(url, into):
    """git clone, keeping git's own words. Not quiet, and it cannot sit there waiting for a password.

    A URL that 404s makes git ask for a username, which on a notebook looks exactly like nothing
    happening at all."""
    into = pathlib.Path(into)
    if (into / ".git").exists() and any(into.iterdir()):
        return True
    if into.exists():
        say("clearing a half-finished", into.name)
        shutil.rmtree(into, ignore_errors=True)
    air = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    try:
        done = subprocess.run(["git", "clone", "--depth", "1", url, str(into)],
                              capture_output=True, text=True, env=air, timeout=900)
    except subprocess.TimeoutExpired:
        say("git clone timed out:", url)
        return False
    if done.returncode:
        say("git could not clone", url)
        for row in (done.stderr or done.stdout or "").strip().splitlines()[-12:]:
            say("   ", row)
        return False
    return True


def pip(*args):
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *args], check=False)


def comfyui(place=None):
    """ComfyUI and its node packs, installed without disturbing the torch this machine already has."""
    place = place or where()
    comfy = place["comfy"]
    comfy.parent.mkdir(parents=True, exist_ok=True)
    needs = comfy / "requirements.txt"
    if not needs.exists() and (not clone(COMFY_REPO, comfy) or not needs.exists()):
        raise SystemExit("ComfyUI is not there - git's own reason is above")
    say("ComfyUI at", comfy)

    import torch
    say("torch already here:", torch.__version__, "cuda", torch.version.cuda)
    # Colab and Kaggle ship a torch built against their own CUDA. Letting pip pull its own over the top
    # is the usual reason ComfyUI then will not start, with an error far from the cause.
    skip = ("torch", "torchvision", "torchaudio")
    keep = []
    for line in needs.read_text().splitlines():
        bare = line.strip()
        if not bare or bare.startswith("#"):
            continue
        name = re.split(r"[=<>\[;]", bare)[0].strip().lower()
        if name not in skip:
            keep.append(bare)
    mine = comfy / "requirements.castforge.txt"
    mine.write_text(chr(10).join(keep))
    say(f"installing {len(keep)} requirements, leaving torch alone")
    pip("-r", str(mine))

    nodes = comfy / "custom_nodes"
    nodes.mkdir(parents=True, exist_ok=True)
    for url in NODE_PACKS:
        name = url.rstrip("/").split("/")[-1]
        say("node pack:", name, "ok" if clone(url, nodes / name) else "FAILED - see above")
    return comfy


def checkpoint(which="realvis_lightning", place=None):
    """Fetch the model once and keep it somewhere a dropped session cannot take it.

    Kaggle has no Drive and /kaggle/working is wiped unless you commit, so the right home there is a
    DATASET: this looks in /kaggle/input first and uses it with no download at all."""
    place = place or where()
    repo, filename, gated = CHECKPOINTS[which]
    kept = None
    if place["on"] == "kaggle":
        for found in pathlib.Path("/kaggle/input").glob("**/" + filename):
            kept = found
            say("attached as a Kaggle dataset:", found, "- nothing to download")
            break
    if kept is None:
        home = place["scratch"] if place.get("batch") else place["keep"]
        store = home / "models" / "checkpoints"
        store.mkdir(parents=True, exist_ok=True)
        kept = store / filename
    if not kept.exists():
        token = None
        if gated:
            try:
                from google.colab import userdata
                token = userdata.get("HF_TOKEN")
            except Exception:
                token = os.environ.get("HF_TOKEN")
            if not token:
                raise SystemExit(f"{repo} is gated: put a token in Colab's Secrets panel as HF_TOKEN, "
                                 f"or use realvis_lightning, which needs none.")
        say(f"first time: fetching {filename}. About 6.5 GB, and it happens once.")
        pip("huggingface_hub")
        from huggingface_hub import hf_hub_download
        try:
            hf_hub_download(repo_id=repo, filename=filename, token=token,
                            local_dir=str(kept.parent))
        except Exception as e:
            if "name resolution" in str(e) or "LocalEntryNotFound" in type(e).__name__:
                raise SystemExit("Could not reach huggingface.co: this session has no internet. "
                                 "Kaggle: the panel on the RIGHT > Settings > Internet > On.")
            raise
        if place["on"] == "kaggle":
            say("")
            say("DO THIS ONCE so it is never downloaded again:")
            say("  right panel > Output > New Dataset, call it castforge-models.")
            say("  After that: Add Input > Datasets > castforge-models.")
    else:
        say(f"already there: {kept.name} ({kept.stat().st_size / 2 ** 30:.1f} GB)")

    models = place["comfy"] / "models" / "checkpoints"
    models.mkdir(parents=True, exist_ok=True)
    link = models / filename
    if not link.exists():
        try:
            link.symlink_to(kept)
        except OSError:
            shutil.copy(kept, link)
    say("ComfyUI will load:", filename)
    return filename


def setup(which="realvis_lightning"):
    """Everything up to the point where ComfyUI can be started: one call."""
    place = check()
    comfyui(place)
    name = checkpoint(which, place)
    return {**place, "checkpoint": name}


# --- running it -----------------------------------------------------------------------------------------

def wanted_flags(lean=False):
    """Flags worth passing IF this ComfyUI has them. Only the ones there is evidence for.

    The crash that cost four attempts was not VRAM, not RAM and not the patch accumulating. It was a
    SEGMENTATION FAULT, and the log named the line:

        Fatal Python error: Segmentation fault
          comfy_aimdo/host_buffer.py:148 in __del__
          comfy/model_patcher.py:1974 in load
          comfy/model_management.py:844 in model_use_more_vram
          comfy/sd.py:1376 in decode

    ComfyUI's async offload keeps pinned host buffers, and freeing one while a model is being brought
    back for a VAE decode takes the process out at the C level. It always went on the SECOND swatch
    because that is the first time anything is reloaded. Turning that machinery off avoids the code
    path entirely, and costs a little speed rather than the whole run.

    `lean` is the fallback for coming back after a crash: --lowvram changes the memory path again, and
    is what got six swatches out of the first run once it had died once.
    """
    flags = ["--disable-async-offload", "--disable-pinned-memory"]
    if lean:
        flags.append("--lowvram")
    return flags


def supported_flags(place=None):
    """Every long option this ComfyUI actually accepts, read out of its own --help."""
    place = place or where()
    try:
        done = subprocess.run([sys.executable, "main.py", "--help"], cwd=str(place["comfy"]),
                              capture_output=True, text=True, timeout=120)
    except Exception:
        return set()
    return set(re.findall(r"--[a-z0-9][a-z0-9-]+", (done.stdout or "") + (done.stderr or "")))


def start(place=None, wait=480, lean=False):
    """Start ComfyUI and wait for it to answer. Prints its OWN words when it will not."""
    place = place or where()
    if _running.get("comfy") and _running["comfy"].poll() is None:
        say("ComfyUI is already running")
        return True
    # ...and ask the PORT as well, not just this module's memory of it. Re-running cell 1 reloads this
    # module, which empties `_running` - but the ComfyUI started by the previous run is still there and
    # still holding 8188. Without this, a second one is launched, fails to bind, and the old one answers
    # the health check anyway: it looks like it worked and leaves a process nobody is tracking.
    try:
        urllib.request.urlopen(URL + "/system_stats", timeout=3)
        say("ComfyUI is already up on", URL, "- using that one")
        return True
    except Exception:
        pass
    swatches = place["keep"] / "swatches"
    swatches.mkdir(parents=True, exist_ok=True)
    log = place["work"] / "comfy.log"
    _running["log"] = log
    # ComfyUI's own flags change between versions - --normalvram was there and then was not, and the
    # only sign is "unrecognized arguments" and a process that never starts. So ask it what it takes
    # before passing anything optional. An empty answer is fine: the defaults are sensible.
    extra = [flag for flag in wanted_flags(lean) if flag in supported_flags(place)]
    if extra:
        say("starting with", " ".join(extra))
    proc = subprocess.Popen([sys.executable, "main.py", "--listen", "127.0.0.1", *extra,
                             "--port", str(PORT), "--output-directory", str(swatches)],
                            cwd=str(place["comfy"]), stdout=open(log, "w"),
                            stderr=subprocess.STDOUT)
    _running["comfy"] = proc
    until = time.time() + wait
    spoke = time.time()
    while time.time() < until:
        time.sleep(2)
        if proc.poll() is not None:
            break
        if time.time() - spoke >= 30:      # starting is slow; silence while it does is not a fault
            spoke = time.time()
            say(f"    ... waiting for ComfyUI, {time.time() - (until - wait):.0f}s{memory_now()}")
        try:
            urllib.request.urlopen(URL + "/system_stats", timeout=3)
            say("ComfyUI is up." + memory_now())
            return True
        except Exception:
            pass
    say("ComfyUI did not start. The last of its own output:")
    say("-" * 70)
    said = pathlib.Path(log).read_text(errors="ignore").strip().splitlines()
    if not said:
        say("(it wrote nothing at all)")
    for row in said[-40:]:
        say(row)
    say("-" * 70)
    raise SystemExit("ComfyUI did not start - its reason is above")


def tunnel(place=None):
    """Open a door to it from outside, and print the one line the laptop needs."""
    place = place or where()
    start(place)
    where_cf = pathlib.Path("/usr/local/bin/cloudflared")
    if not where_cf.exists():
        subprocess.run(["wget", "-q", "-O", str(where_cf),
                        "https://github.com/cloudflare/cloudflared/releases/latest/download/"
                        "cloudflared-linux-amd64"], check=False)
        where_cf.chmod(0o755)
    door = subprocess.Popen(["cloudflared", "tunnel", "--url", URL, "--no-autoupdate"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    _running["tunnel"] = door
    pattern = re.compile(r"https://[-a-z0-9]+\.trycloudflare\.com")
    found = None
    for line in door.stdout:
        hit = pattern.search(line)
        if hit:
            found = hit.group(0)
            break
    threading.Thread(target=lambda: [None for _ in door.stdout], daemon=True).start()
    if not found:
        raise SystemExit("cloudflared did not give an address")
    say("")
    say("=" * 70)
    say("  Point the laptop at this:")
    say("")
    say(f"  python castforge.py gpu connect {found}")
    say("=" * 70)
    say("")
    return found


# --- making cloth without a tunnel -----------------------------------------------------------------------

def graph_for(prompt, checkpoint_name, seed=0, size=1024):
    """One square of cloth. Mirrors generate/remote_gpu.tiling_graph in the CastForge repo.

    All three tiling nodes matter and they do different jobs: the UNet has to GENERATE in a wrapping
    space, the VAE has to decode in one, and the decode itself has to be circular. Decode alone leaves
    the seam in, because the picture was never made to wrap. "Modify in place", not "Make a copy": a
    copy puts a second 6.5 GB model on a 15 GB card and the second swatch kills it."""
    quick = any(t in checkpoint_name.lower() for t in ("lightning", "turbo", "lcm", "hyper"))
    steps, cfg = (6, 1.8) if quick else (28, 5.5)
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint_name}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": prompt +
              ", seamless tileable texture, flat even lighting, straight on, fills the frame, "
              "photographic, fine detail"}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text":
              "seam, border, frame, text, watermark, person, hands, shadow, vignette"}},
        "4": {"class_type": "EmptyLatentImage",
              "inputs": {"width": size, "height": size, "batch_size": 1}},
        "8": {"class_type": "SeamlessTile",
              "inputs": {"model": ["1", 0], "tiling": "enable", "copy_model": "Modify in place"}},
        "9": {"class_type": "MakeCircularVAE",
              "inputs": {"vae": ["1", 2], "tiling": "enable", "copy_vae": "Modify in place"}},
        "5": {"class_type": "KSampler", "inputs": {
              "seed": seed, "steps": steps, "cfg": cfg,
              "sampler_name": "dpmpp_sde" if quick else "dpmpp_2m", "scheduler": "karras",
              "denoise": 1.0, "model": ["8", 0], "positive": ["2", 0], "negative": ["3", 0],
              "latent_image": ["4", 0]}},
        "6": {"class_type": "CircularVAEDecode",
              "inputs": {"samples": ["5", 0], "vae": ["9", 0], "tiling": "enable"}},
        "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": "cf", "images": ["6", 0]}},
    }


def unload():
    """Drop the cached checkpoint between swatches.

    ComfyUI keeps the loaded model between prompts, and SeamlessTile with "Modify in place" patches
    THAT CACHED OBJECT - so the second swatch runs on an already-patched model and before long the
    process dies. A few seconds of reloading each time, against having to restart everything."""
    try:
        body = json.dumps({"free_memory": True, "unload_models": True}).encode()
        req = urllib.request.Request(URL + "/free", data=body,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=60).read()
    except Exception:
        pass


def last_words(lines=30):
    """What ComfyUI said just before it went away. Usually the whole answer."""
    log = _running.get("log")
    if not log or not pathlib.Path(log).exists():
        return []
    return pathlib.Path(log).read_text(errors="ignore").strip().splitlines()[-lines:]


def memory_now():
    """RAM and VRAM as plain numbers. Evidence, rather than another theory about what filled up."""
    bits = []
    try:
        info = {}
        with open("/proc/meminfo") as fh:
            for row in fh:
                key, _, rest = row.partition(":")
                info[key] = float(rest.split()[0]) / 1024 / 1024          # GiB
        bits.append(f"RAM {info['MemTotal'] - info['MemAvailable']:.1f}/{info['MemTotal']:.0f}G")
    except Exception:
        pass
    try:
        done = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total",
                               "--format=csv,noheader,nounits"],
                              capture_output=True, text=True, timeout=15)
        used, total = done.stdout.strip().splitlines()[0].split(",")
        bits.append(f"VRAM {int(used) / 1024:.1f}/{int(total) / 1024:.0f}G")
    except Exception:
        pass
    return (" " + " ".join(bits)) if bits else ""


def queue_now():
    """" (loading the model)" or " (1 ahead)" - something to show it is alive and what it is at."""
    try:
        q = json.loads(urllib.request.urlopen(URL + "/queue", timeout=10).read())
        running, waiting = len(q.get("queue_running", [])), len(q.get("queue_pending", []))
        if running and not waiting:
            return " (running)"
        if waiting:
            return f" (running, {waiting} waiting)"
        return " (nothing queued - finishing up)"
    except Exception:
        return ""


class Bad(Exception):
    """ComfyUI refused the graph. Its own words name the node, which is the only useful thing here."""


class Gone(Exception):
    """ComfyUI stopped answering - it died rather than refused."""


def ask(graph, wait=900, tell=20):
    """Run one graph and come back with what it saved.

    Says how long it has been waiting, every `tell` seconds. A swatch takes fifteen seconds on a T4 and
    several minutes after a crash has put it into --lowvram, and in between those two numbers a silent
    cell is indistinguishable from a dead one. That is most of what "it is doing nothing" means.

    Raises `Gone` when ComfyUI stops answering: a connection refused mid-batch means the process died,
    and the reason is only ever in its own log."""
    body = json.dumps({"prompt": graph}).encode()
    req = urllib.request.Request(URL + "/prompt", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        pid = json.loads(urllib.request.urlopen(req, timeout=60).read())["prompt_id"]
    except urllib.error.URLError as e:
        raise Gone(str(e)) from None
    began = time.time()
    until = began + wait
    spoke = began
    while time.time() < until:
        time.sleep(2)
        if time.time() - spoke >= tell:
            spoke = time.time()
            say(f"    ... {time.time() - began:.0f}s{queue_now()}")
        try:
            hist = json.loads(urllib.request.urlopen(f"{URL}/history/{pid}", timeout=30).read())
        except urllib.error.URLError as e:
            raise Gone(str(e)) from None
        if pid in hist:
            for node in hist[pid].get("outputs", {}).values():
                for img in node.get("images", []):
                    return img
            return None
    return None


def batch(wanted=None, place=None, checkpoint_name=None):
    """Make a whole set with no tunnel at all - which is what Kaggle is good at.

    Save Version > Run All: headless for up to twelve hours, nothing to keep open, no address to go
    stale. The swatches and a manifest land in the output folder; download it and the laptop turns the
    lot into materials with `python generate/make_fabric.py --folder <that folder>`."""
    place = place or where()
    wanted = wanted or CLOTH
    checkpoint_name = checkpoint_name or CHECKPOINTS["realvis_lightning"][1]
    start(place)
    out = place["keep"] / "swatches"
    out.mkdir(parents=True, exist_ok=True)
    made = []
    for prompt, kind, name in wanted:
        target = out / f"{name}.png"
        if target.exists():
            say("already there:", target.name)
            made.append({"name": name, "kind": kind})
            continue
        say("making", name, "...")
        began = time.time()
        img = None
        for go in (1, 2):
            try:
                img = ask(graph_for(prompt, checkpoint_name))
                break
            except Gone as e:
                # ComfyUI died mid-batch. Show what it said, stand it back up, and carry on - losing
                # one fabric to a crash is a nuisance; losing the whole run to it is the difference
                # between a session that was worth having and one that was not.
                say(f"  ComfyUI went away ({e}). Its last words:")
                for row in last_words():
                    say("   ", row)
                if go == 2:
                    say("  giving up on", name)
                    break
                _running.pop("comfy", None)
                say("  starting it again, leaner this time...")
                try:
                    start(place, lean=True)
                except SystemExit:
                    say("  it will not come back; stopping here")
                    img = None
                    break
        if not img:
            say("  nothing came back")
            continue
        src = place["comfy"] / "output" / img.get("subfolder", "") / img["filename"]
        if not src.exists():
            src = out / img["filename"]
        if src.resolve() != target.resolve():
            shutil.copy(src, target)
        made.append({"name": name, "kind": kind})
        say(f"  ok ({time.time() - began:.0f}s)")
    (out / "manifest.json").write_text(json.dumps(made, indent=1))
    say("")
    say(f"{len(made)} swatches in {out}")
    say("Download that folder, then on the laptop:")
    say("    python generate/make_fabric.py --folder <the folder you downloaded>")
    return out


def alive(minutes=600):
    """Keep an interactive session from being reaped. Stop the cell when you are done."""
    try:
        for _ in range(minutes):
            say("alive", time.strftime("%H:%M:%S"), "- stop this cell when you have finished")
            time.sleep(60)
    except KeyboardInterrupt:
        say("stopped")


# --- clips: a rendered 3D shot, photographed ---------------------------------------------------------
# The models for Wan 2.2 image-to-video. The 5B is the one a 15 GB T4 can actually finish a clip with:
# the 14B pair is 28 GB of weights and its fp8 does nothing on a Turing card, which has no fp8 at all.
WAN = [
    ("diffusion_models", "split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors"),
    ("text_encoders", "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"),
    ("vae", "split_files/vae/wan2.2_vae.safetensors"),
]
WAN_REPO = "Comfy-Org/Wan_2.2_ComfyUI_Repackaged"


def wan(place=None):
    """Fetch the Wan 2.2 image-to-video models (17 GB) and put them where ComfyUI looks for them.

    Same rule as the checkpoint: a file already attached as a dataset is used where it lies. 17 GB is
    four minutes of Kaggle's bandwidth and most of a session's patience if it happens every run."""
    place = place or where()
    got = []
    for folder, path in WAN:
        filename = path.split("/")[-1]
        kept = None
        for found in pathlib.Path("/kaggle/input").glob("**/" + filename) if os.path.isdir("/kaggle/input") else []:
            kept, _ = found, say("attached already:", found.name)
            break
        if kept is None:
            home = (place["scratch"] if place.get("batch") else place["keep"]) / "models" / folder
            home.mkdir(parents=True, exist_ok=True)
            kept = home / filename
            if not kept.exists():
                say(f"fetching {filename} ...")
                pip("huggingface_hub")
                from huggingface_hub import hf_hub_download
                hf_hub_download(repo_id=WAN_REPO, filename=path, local_dir=str(home))
                kept = next(home.glob("**/" + filename))
            else:
                say(f"already there: {filename} ({kept.stat().st_size / 2 ** 30:.1f} GB)")
        where_comfy = place["comfy"] / "models" / folder
        where_comfy.mkdir(parents=True, exist_ok=True)
        link = where_comfy / filename
        if not link.exists():
            try:
                link.symlink_to(kept)
            except OSError:
                shutil.copy(kept, link)
        got.append(filename)
    say("ComfyUI will load:", ", ".join(got))
    return got


SHAPES = [("controlnet", "diffusion_pytorch_model.fp16.safetensors",
           "diffusers/controlnet-depth-sdxl-1.0", "controlnet-depth-sdxl.safetensors")]


def shapes(place=None):
    """Fetch the depth ControlNet (2.3 GB) that holds a re-imagined still to the shape of its render."""
    _fetch_models(SHAPES, place or where())
    say("shapes can be held now")


FACES = [
    ("ipadapter", "sdxl_models/ip-adapter-plus-face_sdxl_vit-h.safetensors", "h94/IP-Adapter", None),
    ("clip_vision", "models/image_encoder/model.safetensors", "h94/IP-Adapter",
     "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"),
]


def faces(place=None):
    """Fetch what is needed to hold a still to a face the character already has (about 3 GB)."""
    _fetch_models(FACES, place or where())
    say("faces can be held now")


def _fetch_models(wanted, place):
    """Fetch (folder, path-in-repo, repo, name-to-save-as) into ComfyUI's model folders, once."""
    for folder, path, repo, rename in wanted:
        want = rename or path.split("/")[-1]
        home = (place["scratch"] if place.get("batch") else place["keep"]) / "models" / folder
        home.mkdir(parents=True, exist_ok=True)
        kept = home / want
        if not kept.exists():
            found = next((f for f in pathlib.Path("/kaggle/input").glob("**/" + want)), None)                 if os.path.isdir("/kaggle/input") else None
            if found:
                kept = found
                say("attached already:", found.name)
            else:
                say(f"fetching {want} ...")
                pip("huggingface_hub")
                from huggingface_hub import hf_hub_download
                got = hf_hub_download(repo_id=repo, filename=path, local_dir=str(home))
                if rename:
                    shutil.move(got, kept)
                else:
                    kept = pathlib.Path(got)
        into = place["comfy"] / "models" / folder
        into.mkdir(parents=True, exist_ok=True)
        link = into / want
        if not link.exists():
            try:
                link.symlink_to(kept)
            except OSError:
                shutil.copy(kept, link)


def every(graph, wait=5400, tell=60):
    """Run one graph and come back with EVERY image it saved. A clip is eighty of them, not one."""
    body = json.dumps({"prompt": graph}).encode()
    req = urllib.request.Request(URL + "/prompt", data=body, headers={"Content-Type": "application/json"})
    try:
        pid = json.loads(urllib.request.urlopen(req, timeout=60).read())["prompt_id"]
    except urllib.error.HTTPError as e:
        # 400 means the graph is wrong, not that the server died; the body says which node and why
        said = ""
        try:
            problem = json.loads(e.read().decode("utf-8", "replace"))
            said = problem.get("error", {}).get("message", "")
            for node, why in (problem.get("node_errors") or {}).items():
                said += f" | {node}: " + "; ".join(x.get("message", "") for x in why.get("errors", []))
        except Exception:
            pass
        raise Bad(f"{e.code} {said}".strip()) from None
    except urllib.error.URLError as e:
        raise Gone(str(e)) from None
    began = spoke = time.time()
    while time.time() < began + wait:
        time.sleep(3)
        if time.time() - spoke >= tell:
            spoke = time.time()
            say(f"    ... {time.time() - began:.0f}s{queue_now()}")
        try:
            hist = json.loads(urllib.request.urlopen(f"{URL}/history/{pid}", timeout=30).read())
        except urllib.error.URLError as e:
            raise Gone(str(e)) from None
        if pid in hist:
            out = []
            for node in hist[pid].get("outputs", {}).values():
                out += node.get("images", [])
            return out
    return []


def clips(place=None, fps=24, only=None):
    """Run every workflow in the attached shot dataset and save a clip per workflow.

    The workflows and the stills are made on the laptop by `castforge.py real --gpu`, which knows what
    each shot should look like; this machine only has the GPU. Frames are encoded here rather than
    downloaded: eighty PNGs is a hundred megabytes, and the same clip is three."""
    place = place or where()
    inputs = pathlib.Path("/kaggle/input")
    found = sorted(inputs.glob("**/workflows/*.json")) if inputs.is_dir() else []
    if not found:
        # Kaggle usually unpacks an uploaded archive for you; when it has not, do it here rather than
        # fail after seventeen gigabytes have already been fetched.
        for zipped in (sorted(inputs.glob("**/*.zip")) if inputs.is_dir() else []):
            out_zip = place["scratch"] / "shots"
            say("unpacking", zipped.name)
            shutil.unpack_archive(str(zipped), str(out_zip))
            found = sorted(out_zip.glob("**/workflows/*.json"))
            if found:
                break
    if not found:
        raise SystemExit("No workflows attached. Add Input > Datasets > the one castforge pushed, "
                         "which holds workflows/ and inputs/.")
    stills = found[0].parent.parent / "inputs"
    into = place["comfy"] / "input"
    into.mkdir(parents=True, exist_ok=True)
    # A still that make_real() has already photographed is the one to animate; the render it came from
    # is only the fallback. The video workflow asks for a filename, not for which of the two it is.
    real = {p_.stem: p_ for p_ in (place["keep"] / "stills").glob("*.png")}
    swapped = 0
    for still in stills.glob("*.png"):
        better = next((f for stem, f in real.items() if stem in still.stem), None)
        shutil.copy(better or still, into / still.name)
        swapped += bool(better)
    say(f"{len(found)} workflows, {len(list(stills.glob('*.png')))} stills"
        + (f" ({swapped} of them photographed first)" if swapped else " (straight from the render)"))
    start(place)
    out = place["keep"] / "clips"
    out.mkdir(parents=True, exist_ok=True)
    made = []
    for n, path in enumerate(found, start=1):
        stem = path.stem
        if only and stem not in only:
            continue
        say(f"[{n}/{len(found)}] {stem}")
        began = time.time()
        try:
            images = every(json.loads(path.read_text(encoding="utf-8")))
        except Gone as e:
            say(f"  ComfyUI stopped answering: {e}")
            say(last_words(40))
            break
        if not images:
            say("  nothing came back; its log says why")
            say(last_words(25))
            continue
        # ComfyUI is started with --output-directory, so its pictures do NOT land under comfy/output.
        # Look where it was told to write as well, or the frames are there and the encode finds nothing.
        sub = images[0].get("subfolder") or ""
        folder = next((r / sub for r in (place["keep"] / "swatches", place["comfy"] / "output",
                                         place["scratch"]) if (r / sub).is_dir()), None)
        frames = sorted(folder.glob("*.png")) if folder else []
        if not frames:
            say(f"  {len(images)} frames were made but not found on disk; looked under {folder}")
            continue
        clip = out / f"{stem}.mp4"
        try:
            # A numbered pattern, not a glob: plenty of ffmpeg builds have no globbing compiled in at
            # all, and the error it gives ("Function not implemented") says nothing about why.
            digits = re.search(r"\d+", frames[0].name)
            first = int(digits.group(0))
            pattern = frames[0].name.replace(digits.group(0), f"%0{len(digits.group(0))}d", 1)
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", str(fps),
                            "-start_number", str(first), "-i", str(folder / pattern),
                            "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(clip)],
                           check=True)
        except (OSError, subprocess.CalledProcessError) as e:
            say(f"  could not encode here ({e}); keeping the frames instead")
            keep = out / stem
            keep.mkdir(exist_ok=True)
            for f in frames:
                shutil.copy(f, keep / f.name)
            clip = keep
        if frames:                                  # one frame beside the clip, to check the face
            shutil.copy(frames[len(frames) // 2], out / f"{stem}.png")
        made.append({"name": stem, "frames": len(frames), "seconds": round(time.time() - began, 1)})
        say(f"  {len(frames)} frames in {time.time() - began:.0f}s -> {clip.name}")
        for f in frames:
            f.unlink()                              # the next clip writes into the same place
    (out / "manifest.json").write_text(json.dumps(made, indent=1))
    say("")
    say(f"{len(made)} clips in {out}")
    say("On the laptop:  kaggle kernels output ashishjiwa/castforge-clips -p tmp/clips")
    return out


def make_real(place=None, only=None):
    """Turn every rendered still into a photograph, before anything is animated.

    Image-to-video animates the picture it is handed and does not restyle it, so a clip made straight
    from a 3D render is a moving 3D render. This is the step that was missing: RealVisXL runs
    image-to-image over each still, keeping the staging and the acting (which the render already got
    right) and replacing the look.

    The made photograph is written over the still the video workflow loads, so nothing downstream has to
    know this happened."""
    place = place or where()
    inputs = pathlib.Path("/kaggle/input")
    jobs = sorted(inputs.glob("**/realism/*.json")) if inputs.is_dir() else []
    if not jobs:
        unpacked = place["scratch"] / "shots"
        jobs = sorted(unpacked.glob("**/realism/*.json")) if unpacked.is_dir() else []
    if not jobs:
        say("no realism jobs attached: the clips will be made from the renders themselves")
        return []
    kept = place["keep"] / "stills"
    kept.mkdir(parents=True, exist_ok=True)
    say(f"{len(jobs)} stills to photograph")
    start(place)
    into = place["comfy"] / "input"
    into.mkdir(parents=True, exist_ok=True)
    # LoadImage reads from ComfyUI's own input folder, and this step runs BEFORE clips() fills it -
    # so it fills it. Without this every graph is refused with a 400 and nothing is photographed.
    staged = 0
    for where_ in {j.parent.parent / "inputs" for j in jobs}:
        for still in where_.glob("*.png") if where_.is_dir() else []:
            shutil.copy(still, into / still.name)
            staged += 1
    say(f"{staged} pictures staged for ComfyUI")
    made = []
    for n, path in enumerate(jobs, start=1):
        job = json.loads(path.read_text(encoding="utf-8"))
        if only and job["id"] not in only:
            continue
        say(f"[{n}/{len(jobs)}] {job['id']} (moving it {job['denoise']})")
        began = time.time()
        images = []
        tries = ((job.get("whole"), "with its face and its shape held"),
                 (job.get("graph"), "with its face held"),
                 (job.get("plain"), "on its own"))
        for graph, how in tries:
            if not graph:
                continue
            try:
                images = every(graph, wait=900, tell=60)
            except Bad as e:
                say(f"  refused {how}: {e}")
                continue                              # the plain graph is the next thing to try
            except Gone as e:
                say(f"  ComfyUI stopped answering: {e}")
                say(last_words(40))
                return made
            if images:
                if graph is not tries[0][0]:
                    say(f"  (fell back: {how})")
                break
            say(f"  nothing came back {how}; its log says why")
            say(last_words(15))
        if not images:
            say("  the still is left as the render made it")
            continue
        sub = images[0].get("subfolder") or ""
        folder = next((r / sub for r in (place["keep"] / "swatches", place["comfy"] / "output",
                                         place["scratch"]) if (r / sub).is_dir()), None)
        got = sorted(folder.glob("*.png")) if folder else []
        if not got:
            say(f"  made but not found on disk; looked under {folder}")
            continue
        shutil.copy(got[-1], kept / f"{job['id']}.png")
        # every input the video workflow might load for this shot now shows the photograph
        for target in into.glob(f"*{job['id']}*.png"):
            shutil.copy(got[-1], target)
        for f in got:
            f.unlink()
        made.append(job["id"])
        say(f"  ok ({time.time() - began:.0f}s)")
    say("")
    say(f"{len(made)} stills photographed; they are in {kept} and the clips will be made from them")
    return made
