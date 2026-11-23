"""Export one worn thing - hair, a beard, eyebrows, eyes, a garment - pinned to the body for the live view.

The designer's live body is morphed in the browser, so anything worn has to follow it there too. Refitting
a garment needs Blender, so instead this writes out the binding MakeHuman already keeps in the asset: for
every garment vertex, three body vertices, three weights and an offset measured against three spans of the
body. The browser adds that up again against whatever shape the sliders have made - the same arithmetic
MakeHuman does, so the garment sits where it would sit if it had been fitted properly, to the micrometre.

It also writes `hides`: the body vertices this garment covers, which MakeHuman lists so the body underneath
can be left undrawn. That is what keeps a belly from coming through its own shirt.

    blender -b --factory-startup -P blender/preview_wear.py -- --asset short03 --folder hair --out DIR

Writes <out>/wear.json, <out>/wear.bin and, when the asset has one, <out>/tex.png.
"""
import argparse
import importlib
import json
import os
import sys
import time

import addon_utils
import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--asset", required=True, help="the MPFB asset name, e.g. short03")
ap.add_argument("--folder", required=True, help="where it lives: hair, eyebrows, eyes, clothes")
ap.add_argument("--out", required=True)
ap.add_argument("--texture-size", type=int, default=512)
args = ap.parse_args(argv)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import preview_mesh as pm                   # noqa: E402  the body both exporters share
from core import preview_kit                # noqa: E402  what counts as a finished export (its version)

MPFB = next(m.__name__ for m in addon_utils.modules() if m.__name__.endswith(".mpfb"))
addon_utils.enable(MPFB, default_set=True)


def svc(module, cls):
    return getattr(importlib.import_module(f"{MPFB}.services.{module}"), cls)


HumanService = svc("humanservice", "HumanService")
TargetService = svc("targetservice", "TargetService")
AssetService = svc("assetservice", "AssetService")
Mhclo = importlib.import_module(f"{MPFB}.entities.clothes.mhclo").Mhclo


def log(*a):
    print("CF:", *a, flush=True)


started = time.time()
# An ordinary body, only so the asset can be loaded and its mesh read. The binding written out below does
# not depend on this body at all, which is why one export serves every character.
human = HumanService.create_human(macro_detail_dict=TargetService.get_default_macro_info_dict())
human.name = "Body"

path = AssetService.find_asset_absolute_path(f"{args.asset}/{args.asset}.mhclo", args.folder)
if not path:
    raise SystemExit(f"CF: no such asset: {args.folder}/{args.asset}")
mhclo = Mhclo()
mhclo.load(path)

# read the body BEFORE anything is put on it: a garment adds a mask of its own to the body
coords = pm.shaped_coords(human)

before = set(bpy.data.objects)
kind = {"hair": "Hair", "eyebrows": "Eyebrows", "eyelashes": "Eyelashes",
        "eyes": "Eyes"}.get(args.folder, "Clothes")
HumanService.add_mhclo_asset(path, human, asset_type=kind, subdiv_levels=0, material_type="MAKESKIN")
worn = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
if not worn:
    raise SystemExit(f"CF: {args.asset} loaded nothing")
obj = worn[0]

deps = bpy.context.evaluated_depsgraph_get()
ev = obj.evaluated_get(deps)
me = ev.to_mesh()
n_v = len(me.vertices)

# --- the binding MakeHuman already keeps ----------------------------------------------------------------
verts = np.zeros((n_v, 3), dtype=np.uint32)
weights = np.zeros((n_v, 3), dtype=np.float32)
offsets = np.zeros((n_v, 3), dtype=np.float32)
loose = 0
for i in range(n_v):
    bound = mhclo.verts.get(i)
    if not bound:
        loose += 1
        continue
    verts[i] = bound["verts"]
    weights[i] = bound["weights"]
    offsets[i] = tuple(bound["offsets"])

# a check worth having: fit it here, and see that the binding lands in the same place
scales = pm.fit_scales(coords, mhclo.x_scale, mhclo.y_scale, mhclo.z_scale)
co = np.empty(n_v * 3)
me.vertices.foreach_get("co", co)
truth = co.reshape(-1, 3)
again = pm.wear_positions(coords, verts.astype(np.int64), weights.astype(np.float64),
                          offsets.astype(np.float64), scales)
err = float(np.abs(again - truth).max())
log(f"{args.asset}: {n_v} vertices bound, worst error {err * 1e6:.1f} microns"
    + (f", {loose} unbound" if loose else ""))

# --- the triangles, the texture, and what it hides -------------------------------------------------------
faces = []
for poly in me.polygons:
    vs = list(poly.vertices)
    for k in range(1, len(vs) - 1):
        faces.append([vs[0], vs[k], vs[k + 1]])
faces = np.array(faces, dtype=np.uint32)

uv = np.zeros((n_v, 2), dtype=np.float32)
if me.uv_layers:
    layer = me.uv_layers[0].data
    for poly in me.polygons:
        for loop in range(poly.loop_start, poly.loop_start + poly.loop_total):
            uv[me.loops[loop].vertex_index] = layer[loop].uv

hides = np.array(sorted(mhclo.delverts or []), dtype=np.uint32)   # body the garment covers

texture, median = None, 0.5
os.makedirs(args.out, exist_ok=True)
for mat in obj.data.materials:
    if not mat or not mat.use_nodes:
        continue
    for node in mat.node_tree.nodes:
        name = (node.image.filepath or node.image.name).lower() if node.type == "TEX_IMAGE" and node.image else ""
        if name and not any(w in name for w in ("norm", "bump", "spec", "rough", "disp")):
            image = node.image.copy()                   # the colours; never the bump or gloss maps
            if max(image.size) > args.texture_size:
                image.scale(args.texture_size, args.texture_size)
            image.file_format = "PNG"
            image.filepath_raw = os.path.join(args.out, "tex.png")
            image.save()
            texture = "tex.png"
            # The build does not multiply a colour by the texture - that turns a dark knit black. It uses
            # colour x (luminance / the texture's median luminance), so the weave shows as light and shade
            # around the colour asked for, whatever the cloth happens to be. The browser needs the median
            # to do the same, and it is measured here, once, on the pixels that are actually opaque.
            px = np.array(image.pixels[:], dtype=np.float32).reshape(-1, 4)
            lit = px[px[:, 3] > 0.5] if (px[:, 3] > 0.5).any() else px
            median = float(np.median(lit[:, :3] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)))
            break
    if texture:
        break
ev.to_mesh_clear()

# everything the browser reads is in the viewer's y-up space, the body included, so the offsets are
# turned now rather than there. The spans are then measured on view axes: x -> 0, y -> 1, z -> 2.
offsets_view = pm.to_view(offsets)
blobs = [("verts", verts.tobytes(), n_v), ("weights", weights.tobytes(), n_v),
         ("offsets", offsets_view.tobytes(), n_v), ("uv", uv.tobytes(), n_v),
         ("indices", faces.tobytes(), len(faces) * 3), ("hides", hides.tobytes(), len(hides))]
at, where = 0, {}
for name, blob, count in blobs:
    where[name] = {"at": at, "count": count}
    at += len(blob)
with open(os.path.join(args.out, "wear.bin"), "wb") as fh:
    for _name, blob, _count in blobs:
        fh.write(blob)
json.dump({"version": preview_kit.VERSION, "asset": args.asset, "folder": args.folder,
           "vertices": n_v, "triangles": len(faces), "texture": texture,
           "median": round(max(median, 0.02), 4),
           "x_scale": list(mhclo.x_scale), "y_scale": list(mhclo.y_scale), "z_scale": list(mhclo.z_scale),
           "error_microns": round(err * 1e6, 1), **where},
          open(os.path.join(args.out, "wear.json"), "w", encoding="utf-8"))
log(f"worn kit: {at / 1e6:.2f} MB, hides {len(hides)} body vertices, "
    f"{time.time() - started:.1f}s -> {args.out}")
