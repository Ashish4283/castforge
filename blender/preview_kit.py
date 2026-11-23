"""Export a "preview kit": the body mesh plus every shape it can be morphed into, for the designer.

The character designer has 68 sliders and a build takes about four minutes, which is no way to design a
face: you cannot agree to something you have not seen. This writes out the plain body once (no rig, no
clothes, no textures - about seven seconds) together with the vertices each morph target moves, so the app
can show the shape changing as a slider moves, with no Blender in the loop at all.

A kit is only the SHAPE. Hair, beard, clothes, skin and the face photo are not in it: those still come from
a build. Run with:
    blender -b --factory-startup -P blender/preview_kit.py -- --gender male --age 34 --build muscular --out DIR

Writes <out>/kit.json (what is in the file, and where) and <out>/kit.bin (the numbers, packed end to end).
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
ap.add_argument("--gender", choices=["male", "female"], required=True)
ap.add_argument("--age", type=float, default=30.0)
ap.add_argument("--build", default="average")
ap.add_argument("--height-cm", type=float, default=170.0)
ap.add_argument("--out", required=True)
args = ap.parse_args(argv)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import preview_mesh as pm              # noqa: E402  the body numbering this shares with preview_wear.py
from core import appearance            # noqa: E402  the same table the designer and the build use
from core import preview_kit           # noqa: E402  what counts as a finished kit (its version)

MPFB = next(m.__name__ for m in addon_utils.modules() if m.__name__.endswith(".mpfb"))
addon_utils.enable(MPFB, default_set=True)


def svc(module, cls):
    return getattr(importlib.import_module(f"{MPFB}.services.{module}"), cls)


HumanService = svc("humanservice", "HumanService")
TargetService = svc("targetservice", "TargetService")
HumanObjectProperties = importlib.import_module(f"{MPFB}.entities.objectproperties").HumanObjectProperties


def log(*a):
    print("CF:", *a, flush=True)


# the same age curve and build presets the real build uses, so the preview is the body it will make
def age_macro(years):
    pts = [(1, 0.0), (11, 0.1875), (25, 0.5), (90, 1.0)]
    years = min(max(years, 1), 90)
    for (y0, m0), (y1, m1) in zip(pts, pts[1:]):
        if years <= y1:
            return m0 + (m1 - m0) * (years - y0) / (y1 - y0)
    return 1.0


BUILDS = {"slim": (0.25, 0.4, 0.6), "average": (0.5, 0.5, 0.5), "athletic": (0.4, 0.75, 0.75),
          "heavy": (0.85, 0.45, 0.4), "muscular": (0.55, 0.95, 0.7)}

started = time.time()
macros = TargetService.get_default_macro_info_dict()
macros["gender"] = 1.0 if args.gender == "male" else 0.0
macros["age"] = age_macro(args.age)
human = HumanService.create_human(macro_detail_dict=macros)
weight, muscle, proportions = BUILDS.get(args.build, BUILDS["average"])
for key, value in (("weight", weight), ("muscle", muscle), ("proportions", proportions)):
    HumanObjectProperties.set_value(key, float(value), entity_reference=human)
TargetService.reapply_macro_details(human)


def set_macro(**kw):
    for key_, value_ in kw.items():
        HumanObjectProperties.set_value(key_, float(value_), entity_reference=human)
    TargetService.reapply_macro_details(human)


# MakeHuman's mesh carries helper geometry (the cages that fit clothes) which stands taller than the person.
# The build measures the "body" vertex group alone, and so must this, or every preview comes out short.
BODY_IDX, TRIS = pm.body_parts(human)
_mask = human.modifiers.get("Hide helpers")


def body_height():
    """How tall the person stands right now, measured the way the build measures it."""
    z = pm.shaped_coords(human, _mask)[BODY_IDX][:, 2]
    return float(z.max() - z.min())


# Height in MakeHuman is a shape, not a scale: a tall person is a different body, not a bigger one. The
# build bisects the macro to reach the stature it was asked for, and so must this, or the preview shows
# proportions the build will not make.
want = args.height_cm / 100
lo, hi = 0.0, 1.0
for _ in range(10):
    mid = (lo + hi) / 2
    set_macro(height=mid)
    lo, hi = (mid, hi) if body_height() < want else (lo, mid)
log(f"height {body_height():.3f} m (asked {want:.3f})")

# --- the body, without MakeHuman's helper geometry ----------------------------------------------------------
# The mesh carries helper vertices (the cages that fit clothes); they are not the person and must not be
# drawn. The "body" vertex group is exactly the skin, so the kit keeps those vertices and the faces that
# lie entirely within them, renumbered from zero.
# The WHOLE mesh is exported, helpers included: a garment's offsets are measured against helper vertices
# (preview_mesh.fit_scales), so they have to travel with the body and morph with it. Only the skin's
# triangles are drawn, so the helpers are never seen.
body = BODY_IDX

# Two different meshes matter here, and mixing them up gives a preview that ignores age, build and height:
#   * "shaped" is the body as it stands now, with the macros applied - that is what gets drawn;
#   * "basis" is MakeHuman's untouched base mesh, which is what every morph target is a delta FROM.
# So positions come from the first and deltas from the second, and the deltas stay right whatever the
# macros are, because that is how MakeHuman applies them too: additively, on top.
basis = human.data.shape_keys.key_blocks["Basis"]
base = np.empty(len(human.data.vertices) * 3, dtype=np.float64)
basis.data.foreach_get("co", base)
base = base.reshape(-1, 3)


shaped = pm.shaped_coords(human, _mask)

tris = TRIS                                   # the skin's triangles, numbered into the whole mesh

# Blender is z-up and the app's viewer is y-up, so the kit is written the way it will be drawn
verts = pm.to_view(shaped)                                # every vertex, helpers and all
floor = float(verts[body][:, 1].min())                    # the floor is where the FEET are, not a cage
verts[:, 1] -= floor
log(f"mesh {len(verts)} vertices ({len(body)} of them skin), {len(tris)} triangles")

# --- the body's own regions a costume covers ----------------------------------------------------------------
# Gloves, in the build, are the hand's own faces lifted 2.5 mm off the skin. The live view draws those same
# faces again in the glove's colour, which reads the same without new geometry. The hand is found from
# MakeHuman's joint markers (there is no "hand" vertex group), on this body, so it follows the sliders.
hands = sorted(pm.hand_vertices(human, shaped, set(body.tolist())))
# MakeHuman's joint markers, in the viewer's own space and off the floor: where a rig's bones would go,
# which is how the live view knows a waist from a shoulder without having a rig at all.
joints = {name: [round(float(x), 4) for x in (p[0], p[2] - floor, -p[1])]
          for name, p in pm.joint_centres(human, shaped).items()
          if not (name.startswith("joint-l-finger") or name.startswith("joint-r-finger")
                  or "eye" in name or "toe" in name)}
regions = {"hands": {"at": 0, "count": len(hands)}}        # "at" is filled in once the offsets are known
hand_idx = np.array(hands, dtype=np.uint32)
log(f"hands: {len(hands)} vertices")

# --- what every slider does to it ---------------------------------------------------------------------------
blobs = [verts.tobytes(), tris.tobytes(), hand_idx.tobytes()]
regions["hands"]["at"] = len(blobs[0]) + len(blobs[1])
offset = sum(len(b) for b in blobs)
shapes = {}
missing = []
for name in sorted(appearance.every_target()):
    path = TargetService.target_full_path(name)
    if not path:
        missing.append(name)
        continue
    key = TargetService.load_target(human, path, weight=0.0, name=f"kit-{name}")
    co = np.empty(len(human.data.vertices) * 3, dtype=np.float64)
    key.data.foreach_get("co", co)
    delta = co.reshape(-1, 3) - base                       # over the whole mesh: the helpers move too
    moved = np.nonzero(np.abs(delta).max(axis=1) > 1e-6)[0]
    human.shape_key_remove(key)
    if not len(moved):
        continue
    d = pm.to_view(delta[moved])
    idx = moved.astype(np.uint32)
    shapes[name] = {"at": offset, "count": int(len(moved))}
    blobs += [idx.tobytes(), d.tobytes()]
    offset += idx.nbytes + d.nbytes

os.makedirs(args.out, exist_ok=True)
with open(os.path.join(args.out, "kit.bin"), "wb") as fh:
    for b in blobs:
        fh.write(b)
json.dump({"version": preview_kit.VERSION, "gender": args.gender, "age": args.age, "build": args.build,
           "height_cm": args.height_cm,
           "vertices": len(verts), "triangles": len(tris), "skin": len(body),
           "positions": {"at": 0, "count": len(verts)},
           "indices": {"at": len(blobs[0]), "count": len(tris) * 3},
           "height": round(float(verts[:, 1].max()), 4), "floor": round(floor, 4),
           "regions": regions, "joints": joints,
           "shapes": shapes},
          open(os.path.join(args.out, "kit.json"), "w", encoding="utf-8"))
log(f"preview kit: {len(shapes)} shapes, {offset / 1e6:.2f} MB, {time.time() - started:.1f}s -> {args.out}")
if missing:
    log("WARNING targets missing from the kit", missing)
