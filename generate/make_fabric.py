"""Turn a generated square of cloth into a material CastForge can put on a garment.

    python generate/make_fabric.py SWATCH.png --kind denim --name worn_denim [--scale 0.35]
    python generate/make_fabric.py --list
    python generate/make_fabric.py --demo              # make one without a GPU, to prove the chain

The GPU's whole job is the first argument: one square picture of cloth. Everything after it happens here,
on the laptop, in a few hundred milliseconds and identically every time - the relief, the roughness, and
the check that the thing actually tiles. `core/fabric.py` explains why that split, and holds the
arithmetic.

A fabric is a folder under `library/fabrics/<name>/`:

    albedo.png     the colour, as generated
    normal.png     the relief, derived
    rough.png      where it shines, derived
    fabric.json    kind, scale, how well it tiles, when and how it was made

`build_character` reads them by name: `costume.fabric` naming a generated fabric puts it on the garment
instead of a flat colour.
"""
import argparse
import datetime
import json
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core import fabric as kit  # noqa: E402

HOME = os.path.join(ROOT, "library", "fabrics")


def log(*a):
    print("CF:", *a, flush=True)


def read(path):
    """A picture as an (h, w, 3) float array in 0..1."""
    from PIL import Image
    im = Image.open(path).convert("RGB")
    return np.asarray(im, dtype=np.float32) / 255.0


def write(path, a):
    """A float array in 0..1 out as an 8-bit PNG."""
    from PIL import Image
    arr = np.clip(np.asarray(a, dtype=np.float32), 0.0, 1.0)
    if arr.ndim == 2:
        arr = np.stack([arr] * 3, axis=-1)
    Image.fromarray((arr * 255.0 + 0.5).astype(np.uint8)).save(path)


def demo_swatch(n=1024, seed=7):
    """A square of twill woven in code: no GPU, and it tiles by construction.

    This exists so the whole chain - swatch to material to a character wearing it - can be proved before
    a single rented GPU minute is spent on it. Prove the pipe with cheap water."""
    y, x = np.mgrid[0:n, 0:n]
    rng = np.random.default_rng(seed)
    threads = 64
    # a twill runs diagonally, and the period has to divide the picture or it will not wrap
    diag = np.sin(2 * math.pi * threads * (x + y) / n)
    warp = np.sin(2 * math.pi * threads * x / n)
    weft = np.sin(2 * math.pi * threads * y / n)
    weave = 0.55 + 0.16 * diag + 0.07 * warp * weft
    # slub: the thick and thin of a real yarn, low frequency, also wrapping
    slub = 0.06 * np.sin(2 * math.pi * 3 * x / n + 1.2) * np.sin(2 * math.pi * 2 * y / n)
    grain = 0.035 * rng.standard_normal((n, n))
    v = np.clip(weave + slub + grain, 0.05, 1.0)
    return np.stack([v * 0.30, v * 0.38, v * 0.62], axis=-1).astype(np.float32)


def make(swatch, kind, name, scale=0.35, where=HOME, source="hand"):
    """Write one fabric folder. Returns (path, report) or raises ValueError if the swatch is no good."""
    problems = kit.check(swatch, kind)
    if problems:
        raise ValueError("; ".join(problems))
    maps = kit.maps_for(swatch, kind)
    folder = os.path.join(where, name)
    os.makedirs(folder, exist_ok=True)
    write(os.path.join(folder, "albedo.png"), swatch)
    write(os.path.join(folder, "normal.png"), maps["normal"])
    write(os.path.join(folder, "rough.png"), maps["roughness"])
    report = {
        "name": name, "kind": kind, "scale": float(scale),
        "size": int(swatch.shape[0]), "source": source,
        "seam": {k: round(float(v), 3) for k, v in maps["seam"].items()},
        "look": maps["look"],
        "made": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    json.dump(report, open(os.path.join(folder, "fabric.json"), "w", encoding="utf-8"), indent=1)
    return folder, report


def load_all(where=HOME):
    """{name: report} for every fabric on this machine - what the studio can offer."""
    out = {}
    if not os.path.isdir(where):
        return out
    for name in sorted(os.listdir(where)):
        meta = os.path.join(where, name, "fabric.json")
        if not os.path.exists(meta):
            continue
        try:
            report = json.load(open(meta, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if all(os.path.exists(os.path.join(where, name, f"{p}.png"))
               for p in ("albedo", "normal", "rough")):
            out[report.get("name", name)] = {**report, "folder": os.path.join(where, name)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("swatch", nargs="?")
    ap.add_argument("--kind", default="cotton", choices=list(kit.KINDS))
    ap.add_argument("--name")
    ap.add_argument("--scale", type=float, default=0.35,
                    help="how much cloth, in metres, the square stands for")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--demo", action="store_true", help="weave one in code, with no GPU at all")
    ap.add_argument("--where", default=HOME)
    a = ap.parse_args()

    if a.list:
        have = load_all(a.where)
        if not have:
            log(f"no fabrics yet in {a.where}")
        for name, r in have.items():
            log(f"{name:22s} {kit.describe(r['kind'], r['seam'])}  "
                f"{r['size']}px over {r['scale']:.2f} m, from {r['source']}")
        return

    if a.demo:
        name = a.name or "demo_denim"
        folder, report = make(demo_swatch(), "denim", name, a.scale, a.where, source="woven in code")
        log(f"{name}: {kit.describe('denim', report['seam'])}")
        log("wrote", folder)
        return

    if not a.swatch:
        sys.exit("give a SWATCH.png, or --demo, or --list")
    swatch = read(a.swatch)
    name = a.name or os.path.splitext(os.path.basename(a.swatch))[0].lower().replace(" ", "_")
    try:
        folder, report = make(swatch, a.kind, name, a.scale, a.where,
                              source=os.path.basename(a.swatch))
    except ValueError as e:
        sys.exit(f"CF: that swatch cannot be used: {e}")
    log(f"{name}: {kit.describe(a.kind, report['seam'])}")
    log("wrote", folder)


if __name__ == "__main__":
    main()
