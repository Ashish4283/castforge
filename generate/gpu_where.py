"""Which place is usable right now, and running a job on it.

    python generate/gpu_where.py                       # both places, and which is in use
    python generate/gpu_where.py --use kaggle
    python generate/gpu_where.py --fabric "worn indigo denim" --kind denim --name worn_denim

The rules are in `core/gpu.py`, which is pure and tested. This gathers the facts those rules need - is
a port answering, are there credentials - and then does what they say.

A Kaggle job is pushed, run headless and fetched through the API: no browser stays open, no tunnel goes
stale, and nothing is typed into a chat. One job at a time, on purpose.
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "generate"))
from core import gpu  # noqa: E402

KEPT = os.path.join(ROOT, ".gpu.json")
KERNEL = "ashishjiwa/castforge-gpu"
KERNEL_DIR = os.path.join(ROOT, "tools", "kaggle", "kernel")


def log(*a):
    print("CF:", *a, flush=True)


# --- the facts core/gpu.py needs ------------------------------------------------------------------------

def answering(port=gpu.LOCAL_PORT, host="127.0.0.1"):
    with socket.socket() as s:
        s.settimeout(1.5)
        return s.connect_ex((host, port)) == 0


def local_vram():
    try:
        done = subprocess.run(["nvidia-smi", "--query-gpu=memory.total",
                               "--format=csv,noheader,nounits"],
                              capture_output=True, text=True, timeout=20)
        return int(done.stdout.strip().splitlines()[0]) / 1024
    except Exception:
        return None


def kaggle_ready():
    """(installed, signed in). Importing the module is what tells us, and it is noisy, so it is quiet."""
    try:
        import importlib
        importlib.import_module("kaggle")
        return True, True
    except ImportError:
        return False, False
    except Exception:
        return True, False          # installed, but it could not authenticate


def facts():
    cli, auth = kaggle_ready()
    return {"local_comfy": answering(), "local_vram": local_vram(),
            "kaggle_cli": cli, "kaggle_auth": auth}


def remembered():
    if os.path.exists(KEPT):
        try:
            return json.load(open(KEPT, encoding="utf-8")).get("place")
        except ValueError:
            pass
    return None


def remember(place, url=None):
    was = {}
    if os.path.exists(KEPT):
        try:
            was = json.load(open(KEPT, encoding="utf-8"))
        except ValueError:
            was = {}
    was["place"] = place
    if url:
        was["url"] = url
    json.dump(was, open(KEPT, "w", encoding="utf-8"), indent=1)
    return place


# --- doing the work -------------------------------------------------------------------------------------

def on_kaggle(jobs, minutes=75):
    """Push the kernel, wait for it, and bring the swatches home. Returns where they landed."""
    import make_fabric

    wanted = os.path.join(KERNEL_DIR, "wanted.json")
    json.dump([{"prompt": p, "kind": k, "name": n} for p, k, n in jobs],
              open(wanted, "w", encoding="utf-8"), indent=1)
    log(f"pushing {len(jobs)} job(s) to {KERNEL}")
    subprocess.run([sys.executable, "-m", "kaggle", "kernels", "push", "-p", KERNEL_DIR],
                   check=False)
    until = time.time() + minutes * 60
    state = "?"
    while time.time() < until:
        time.sleep(60)
        said = subprocess.run([sys.executable, "-m", "kaggle", "kernels", "status", KERNEL],
                              capture_output=True, text=True).stdout.upper()
        state = next((w for w in ("COMPLETE", "ERROR", "CANCEL", "RUNNING", "QUEUED") if w in said),
                     state)
        log(f"  {state}")
        if state in ("COMPLETE", "ERROR", "CANCEL"):
            break
    into = os.path.join(ROOT, "tmp", "swatches")
    os.makedirs(into, exist_ok=True)
    subprocess.run([sys.executable, "-m", "kaggle", "kernels", "output", KERNEL, "-p", into],
                   check=False)
    log(f"{state}; what came back is in {into}")
    return into


def on_local(jobs, url=None):
    """Make them on a ComfyUI running here, through the same client the tunnel uses."""
    url = url or f"http://127.0.0.1:{gpu.LOCAL_PORT}"
    for prompt, kind, name in jobs:
        subprocess.run([sys.executable, os.path.join(ROOT, "generate", "remote_gpu.py"),
                        "--url", url, "fabric", prompt, "--kind", kind, "--name", name], check=False)
    return os.path.join(ROOT, "library", "fabrics")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--use", choices=gpu.PLACES, help="remember where work should go")
    ap.add_argument("--fabric", help="a prompt: make one square of cloth")
    ap.add_argument("--kind", default="cotton")
    ap.add_argument("--name")
    ap.add_argument("--set", action="store_true", help="the whole set rather than one")
    a = ap.parse_args()

    seen = facts()
    place = a.use or remembered() or gpu.best(seen)
    if a.use:
        remember(a.use)

    if not (a.fabric or a.set):
        for row in gpu.describe(seen, place):
            log(row)
        log("")
        log(f"using: {place}   (change it with --use local|kaggle)")
        return

    problems = gpu.check(place, seen)
    if problems:
        for p in problems:
            log(p)
        sys.exit(1)

    if a.set:
        sys.path.insert(0, os.path.join(ROOT, "tools", "kaggle"))
        import boot
        jobs = list(boot.CLOTH)
    else:
        name = a.name or a.fabric.lower().replace(",", "").replace(" ", "_")[:40]
        jobs = [(a.fabric, a.kind, name)]

    log(f"{len(jobs)} job(s) on {place}")
    where = on_kaggle(jobs) if place == "kaggle" else on_local(jobs)
    log("done:", where)


if __name__ == "__main__":
    main()
