"""Ask a ComfyUI somewhere else to make something, and bring it home.

    python generate/remote_gpu.py --url https://xxxx.trycloudflare.com ping
    python generate/remote_gpu.py --url ... fabric "worn blue denim, flat lit, top down" \
        --kind denim --name worn_denim
    python generate/remote_gpu.py --url ... run my_workflow.json --out tmp/

"Somewhere else" is any ComfyUI that answers over HTTP: a Colab notebook behind a cloudflared tunnel, a
Kaggle session, the gpubox instance, or one running on this laptop. The protocol is the same for all of
them - POST a graph to /prompt, poll /history, GET the pictures from /view - so the same client serves
every one and nothing here knows or cares which it is talking to.

Why this is a THIN client, deliberately. A rented GPU is the flakiest part of the whole pipeline: the
session drops, the tunnel changes address, the free tier runs out. So it does as little as possible -
fetch one picture - and everything that can be done on the laptop is done on the laptop, where it is
free, instant and the same every time. What comes back is checked before it is believed
(`core.fabric.check`): a swatch with a seam in it is refused here rather than discovered on a character.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core import fabric as kit  # noqa: E402

TIMEOUT = 20
# The three nodes ComfyUI-seamless-tiling adds. All three matter and they do different jobs: the UNet
# has to generate in a wrapping space (SeamlessTile), the VAE has to decode in one (MakeCircularVAE),
# and the decode itself has to be circular. Decode alone leaves the seam in - the picture was never
# made to wrap in the first place.
SEAMLESS = "CircularVAEDecode"
TILE_MODEL, TILE_VAE = "SeamlessTile", "MakeCircularVAE"


def log(*a):
    print("CF:", *a, flush=True)


def call(url, path, data=None, raw=False, timeout=TIMEOUT):
    """GET or POST against a ComfyUI. Returns parsed JSON, or raw bytes when `raw`."""
    full = url.rstrip("/") + path
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(full, data=body,
                                 headers={"Content-Type": "application/json"} if body else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            blob = r.read()
    except urllib.error.HTTPError as e:
        # ComfyUI puts WHY it refused a graph in the body of the 400. Letting the bare status through
        # leaves you guessing at which node it disliked, which is no way to debug a remote machine.
        detail = ""
        try:
            said = json.loads(e.read() or b"{}")
            detail = said.get("error", {}).get("message") or said.get("error") or ""
            for node, why in (said.get("node_errors") or {}).items():
                detail += f" | node {node}: {json.dumps(why)[:300]}"
        except Exception:
            pass
        raise RuntimeError(f"{e.code} from {path}: {detail or e.reason}") from None
    return blob if raw else json.loads(blob or b"{}")


def ping(url):
    """What this ComfyUI is and what it can do. Raises if it cannot be reached at all."""
    stats = call(url, "/system_stats")
    nodes = call(url, "/object_info", timeout=60)
    devices = ", ".join(f"{d.get('name', '?')} ({d.get('vram_total', 0) / 2**30:.0f} GB)"
                        for d in stats.get("devices", []))
    return {"devices": devices or "none reported", "nodes": len(nodes),
            "seamless": any(SEAMLESS in n or "Seamless" in n for n in nodes),
            "checkpoints": (nodes.get("CheckpointLoaderSimple", {})
                            .get("input", {}).get("required", {})
                            .get("ckpt_name", [[]])[0])}


def unload(url):
    """Make ComfyUI drop the model it is holding, between one swatch and the next.

    Two reasons, and the second is the one that was killing it. ComfyUI keeps the loaded checkpoint
    cached between prompts, and `SeamlessTile` with "Modify in place" PATCHES THAT CACHED OBJECT - so
    the second swatch runs on an already-patched model, the third on a twice-patched one, and the
    process dies with nothing to show for it but a 502 from the tunnel. Unloading means every swatch
    starts from a clean checkpoint. It costs a few seconds of reloading, which is nothing next to
    re-running the whole notebook."""
    try:
        call(url, "/free", {"free_memory": True, "unload_models": True}, timeout=60)
        return True
    except Exception:
        return False


def submit(url, graph, wait=600):
    """Run a graph and come back with [(name, subfolder, type)] of whatever it saved."""
    who = str(uuid.uuid4())
    pid = call(url, "/prompt", {"prompt": graph, "client_id": who})["prompt_id"]
    log(f"queued {pid[:8]}")
    until = time.time() + wait
    while time.time() < until:
        time.sleep(2)
        hist = call(url, f"/history/{pid}")
        if pid not in hist:
            continue
        done = hist[pid]
        status = (done.get("status") or {}).get("status_str", "")
        if status == "error":
            raise RuntimeError(f"the graph failed on the GPU: "
                               f"{json.dumps(done.get('status'))[:400]}")
        out = [(i["filename"], i.get("subfolder", ""), i.get("type", "output"))
               for node in done.get("outputs", {}).values() for i in node.get("images", [])]
        if out:
            return out
        if status:
            return []
    raise TimeoutError(f"nothing came back in {wait} s - the session may have dropped")


def fetch(url, item, into):
    """Bring one picture home."""
    name, subfolder, kind = item
    q = urllib.parse.urlencode({"filename": name, "subfolder": subfolder, "type": kind})
    blob = call(url, f"/view?{q}", raw=True, timeout=120)
    os.makedirs(into, exist_ok=True)
    path = os.path.join(into, name)
    open(path, "wb").write(blob)
    return path


# A "Lightning" or "Turbo" checkpoint is distilled to work in a handful of steps at almost no guidance.
# Run one at SDXL base's 28 steps and CFG 5.5 and it comes out burnt and over-contrasted - and six times
# slower, which on a free T4 is the difference between fifteen seconds a swatch and a minute and a half.
FAST = ("lightning", "turbo", "lcm", "hyper")


def settings_for(checkpoint, steps=None, cfg=None):
    """(steps, cfg, sampler, scheduler) suited to the checkpoint, unless the caller insists."""
    quick = any(tag in (checkpoint or "").lower() for tag in FAST)
    if quick:
        return (steps or 6, cfg if cfg is not None else 1.8, "dpmpp_sde", "karras")
    return (steps or 28, cfg if cfg is not None else 5.5, "dpmpp_2m", "karras")


def tiling_graph(prompt, checkpoint, size=1024, steps=None, cfg=None, seed=0, seamless=True,
                 negative="seam, border, frame, text, watermark, person, hands, shadow, vignette"):
    """A ComfyUI graph for one square of cloth, lit flat and straight on.

    "Flat lit, straight on" matters more than it sounds: a swatch with a light falling across it bakes
    that light into every garment it is ever put on, and no amount of relief fixes it. The prompt says
    so and the negative says so."""
    steps, cfg, sampler, schedule = settings_for(checkpoint, steps, cfg)
    graph = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
        "2": {"class_type": "CLIPTextEncode",
              "inputs": {"text": f"{prompt}, seamless tileable texture, flat even lighting, "
                                 f"straight on, fills the frame, photographic, fine detail",
                         "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage",
              "inputs": {"width": size, "height": size, "batch_size": 1}},
        "5": {"class_type": "KSampler",
              "inputs": {"seed": seed, "steps": steps, "cfg": cfg, "sampler_name": sampler,
                         "scheduler": schedule, "denoise": 1.0,
                         "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
                         "latent_image": ["4", 0]}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": "castforge_fabric",
                                                    "images": ["6", 0]}},
    }
    if seamless:
        # "Modify in place", NOT "Make a copy". A copy puts a second 6.5 GB SDXL on the card, and a
        # free T4 has 15 GB: the first swatch fits, the second kills ComfyUI and the tunnel starts
        # answering 502. Nothing is lost by modifying in place - every job sent here wants tiling.
        graph["8"] = {"class_type": TILE_MODEL,
                      "inputs": {"model": ["1", 0], "tiling": "enable",
                                 "copy_model": "Modify in place"}}
        graph["9"] = {"class_type": TILE_VAE,
                      "inputs": {"vae": ["1", 2], "tiling": "enable",
                                 "copy_vae": "Modify in place"}}
        graph["5"]["inputs"]["model"] = ["8", 0]          # sample in a wrapping space...
        graph["6"] = {"class_type": SEAMLESS,
                      "inputs": {"samples": ["5", 0], "vae": ["9", 0], "tiling": "enable"}}
    return graph


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("CASTFORGE_COMFY", "http://127.0.0.1:8188"))
    sub = ap.add_subparsers(dest="job", required=True)
    sub.add_parser("ping")
    f = sub.add_parser("fabric")
    f.add_argument("prompt")
    f.add_argument("--kind", default="cotton", choices=list(kit.KINDS))
    f.add_argument("--name")
    f.add_argument("--checkpoint", default="RealVisXL_V5.0_Lightning_fp16.safetensors",
                   help="whatever the notebook said it would load")
    f.add_argument("--size", type=int, default=1024)
    f.add_argument("--steps", type=int, default=None,
                   help="left alone: a Lightning checkpoint gets 6, an ordinary one 28")
    f.add_argument("--seed", type=int, default=0)
    f.add_argument("--scale", type=float, default=0.35)
    f.add_argument("--tries", type=int, default=3, help="how many seeds to try for one that tiles")
    f.add_argument("--keep-untiled", action="store_true", help="save it even if it has a seam")
    r = sub.add_parser("run")
    r.add_argument("graph")
    r.add_argument("--out", default="tmp")
    a = ap.parse_args()

    if a.job == "ping":
        try:
            what = ping(a.url)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            sys.exit(f"CF: cannot reach a ComfyUI at {a.url}: {e}")
        log(f"{a.url}: {what['devices']}, {what['nodes']} node types, "
            f"seamless tiling {'installed' if what['seamless'] else 'NOT installed'}")
        log(f"checkpoints: {', '.join(what['checkpoints'][:6]) or 'none'}")
        return

    if a.job == "run":
        graph = json.load(open(a.graph, encoding="utf-8"))
        for item in submit(a.url, graph):
            log("fetched", fetch(a.url, item, a.out))
        return

    # fabric: ask for a square, bring it home, and refuse it if it does not tile
    import numpy as np
    from PIL import Image
    name = a.name or a.prompt.lower().replace(",", "").replace(" ", "_")[:40]
    into = os.path.join(ROOT, "tmp", "swatches")
    best = None
    for attempt in range(max(1, a.tries)):
        seed = a.seed + attempt * 1013
        chosen = settings_for(a.checkpoint, a.steps)
        log(f"asking for {a.kind}: {a.prompt!r} (seed {seed}, {chosen[0]} steps, cfg {chosen[1]})")
        unload(a.url)                      # a clean checkpoint for every swatch: see `unload`
        got = submit(a.url, tiling_graph(a.prompt, a.checkpoint, a.size, a.steps, seed=seed))
        if not got:
            log("the graph saved nothing")
            continue
        path = fetch(a.url, got[0], into)
        swatch = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0
        how = kit.seam(swatch)
        log(f"  {os.path.basename(path)}: {kit.describe(a.kind, how)}")
        if best is None or how["worst"] < best[1]["worst"]:
            best = (swatch, how, path)
        if how["worst"] <= kit.SEAM_OK:
            break
    if best is None:
        sys.exit("CF: nothing came back")
    swatch, how, path = best
    if how["worst"] > kit.SEAM_OK and not a.keep_untiled:
        sys.exit(f"CF: the best of {a.tries} still has a seam ({how['worst']:.1f}x). Install the "
                 f"seamless tiling node in the notebook, or pass --keep-untiled to save it anyway. "
                 f"The swatch is at {path}")
    sys.path.insert(0, os.path.join(ROOT, "generate"))
    import make_fabric
    folder, report = make_fabric.make(swatch, a.kind, name, a.scale, source=f"{a.url} / {a.checkpoint}")
    log(f"{name}: {kit.describe(a.kind, report['seam'])}")
    log("wrote", folder)


if __name__ == "__main__":
    main()
