"""Little pictures of everything a character can wear, so the studio offers looks instead of a dropdown.

One Blender session does the lot: the body is built once, then each asset is put on, photographed and taken
off again. A hair style or a beard is shot close on the head; clothes and shoes are shot head to foot.

    blender -b --factory-startup -P blender/preview_thumbs.py -- --out DIR [--only hair]

Writes <out>/<folder>-<asset>.png, skipping any that are already there, and prints one CF: line per picture
so the app can follow along.
"""
import argparse
import importlib
import math
import os
import sys
import time

import addon_utils
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--only", default="", help="just one kind: hair, beard, eyebrows, outfit, shoes, hat")
ap.add_argument("--size", type=int, default=256)
ap.add_argument("--redo", action="store_true", help="take them again even if they are there")
args = ap.parse_args(argv)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from core import appearance                 # noqa: E402  the wardrobe these are pictures of

MPFB = next(m.__name__ for m in addon_utils.modules() if m.__name__.endswith(".mpfb"))
addon_utils.enable(MPFB, default_set=True)


def svc(module, cls):
    return getattr(importlib.import_module(f"{MPFB}.services.{module}"), cls)


HumanService = svc("humanservice", "HumanService")
TargetService = svc("targetservice", "TargetService")
AssetService = svc("assetservice", "AssetService")


def log(*a):
    print("CF:", *a, flush=True)


# --- everything worth a picture, and how close to stand ------------------------------------------------
def catalogue():
    """[(kind, folder, asset, framing)] - every look the studio can offer, each shot the right way."""
    out = []
    for style, asset in appearance.HAIR_STYLES.items():
        if asset and asset != "none":
            out.append(("hair", "hair", asset, "head"))
    for asset in appearance.EYEBROWS.values():
        out.append(("eyebrows", "eyebrows", asset, "face"))
    for pieces in appearance.BEARDS.values():
        for asset in pieces:
            out.append(("beard", "clothes", asset, "head"))
    for asset in appearance.HATS.values():
        out.append(("hat", "clothes", asset, "head"))
    for per_sex in appearance.OUTFITS.values():
        for asset in per_sex.values():
            out.append(("outfit", "clothes", asset, "whole"))
    for asset in list(appearance.TOPS.values()) + list(appearance.BOTTOMS.values()) + [appearance.DRESS]:
        out.append(("outfit", "clothes", asset, "whole"))
    for asset in (appearance.SHOES, appearance.BOOTS):
        out.append(("shoes", "clothes", asset, "feet"))
    seen, unique = set(), []
    for item in out:
        if item[2] not in seen:
            seen.add(item[2])
            unique.append(item)
    return unique


os.makedirs(args.out, exist_ok=True)
wanted = [c for c in catalogue() if not args.only or c[0] == args.only]
todo = [c for c in wanted
        if args.redo or not os.path.isfile(os.path.join(args.out, f"{c[1]}-{c[2]}.png"))]
log(f"thumbnails: {len(todo)} to take of {len(wanted)}")
if not todo:
    log("thumbnails: nothing to do")
    sys.exit(0)

for startup_object in list(bpy.data.objects):      # the factory file's cube would stand in every picture
    bpy.data.objects.remove(startup_object, do_unlink=True)

macros = TargetService.get_default_macro_info_dict()
macros["gender"], macros["age"] = 0.5, 0.5
human = HumanService.create_human(macro_detail_dict=macros)
human.name = "Body"
for mod in human.modifiers:                        # the helpers must be hidden in renders, not just views
    if mod.type == "MASK":
        mod.show_render = True
for mat in human.data.materials:
    if mat and mat.use_nodes:
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (0.74, 0.60, 0.52, 1)
            bsdf.inputs["Roughness"].default_value = 0.78

# measured on the skin, not on the helper cages, which stand taller than the person
groups = {g.name: g.index for g in human.vertex_groups}
skin = {g.group for g in human.data.vertices[0].groups} and groups["body"]
zs = [v.co.z for v in human.data.vertices if any(g.group == skin for g in v.groups)]
low, high = min(zs), max(zs)
head = high - 0.12

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = scene.render.resolution_y = args.size
scene.render.film_transparent = True
scene.view_settings.view_transform = "Standard"
cam_data = bpy.data.cameras.new("CF_CAM")
cam = bpy.data.objects.new("CF_CAM", cam_data)
bpy.context.collection.objects.link(cam)
scene.camera = cam

for where, energy in (((1.7, -2.4, 2.4), 420), ((-2.2, -1.6, 1.4), 200), ((0, 2.2, 2.0), 260)):
    light = bpy.data.lights.new("CF_L", "POINT")
    light.energy = energy
    obj = bpy.data.objects.new("CF_L", light)
    bpy.context.collection.objects.link(obj)
    obj.location = where

# where to look, how far back to stand, and through which lens. A long lens flatters a face; a whole
# figure needs a wider one or it will not fit on the picture at any sane distance.
FRAMING = {"face": (head + 0.02, 0.45, 85), "head": (head - 0.03, 0.70, 70),
           "whole": ((low + high) / 2, 2.9, 50), "feet": (low + 0.12, 0.85, 60)}


def aim(at_z, distance, lens):
    cam_data.lens = lens
    cam.location = Vector((distance * 0.42, -distance, at_z + distance * 0.10))
    cam.rotation_euler = (Vector((0, 0, at_z)) - cam.location).to_track_quat("-Z", "Y").to_euler()


started = time.time()
done = 0
for kind, folder, asset, framing in todo:
    path = AssetService.find_asset_absolute_path(f"{asset}/{asset}.mhclo", folder)
    if not path:
        log(f"WARNING no such asset: {folder}/{asset}")
        continue
    before = set(bpy.data.objects)
    had_mods = {m.name for m in human.modifiers}      # so only what this asset adds is taken off again
    try:
        HumanService.add_mhclo_asset(path, human, asset_type={"hair": "Hair", "eyebrows": "Eyebrows"}
                                     .get(folder, "Clothes"), subdiv_levels=0, material_type="MAKESKIN")
    except Exception as exc:                       # one bad asset must not cost the whole run
        log(f"WARNING {asset} would not load: {exc}")
        continue
    fresh = [o for o in bpy.data.objects if o not in before]
    aim(*FRAMING[framing])
    scene.render.filepath = os.path.join(args.out, f"{folder}-{asset}.png")
    bpy.ops.render.render(write_still=True)
    log(f"thumbnail {kind} {asset}")
    done += 1
    for o in fresh:                                # take it off again before the next one
        bpy.data.objects.remove(o, do_unlink=True)
    for mod in list(human.modifiers):              # and with it the mask it put on the body
        if mod.name not in had_mods:                 # NEVER the body's own helper mask: without it the
            human.modifiers.remove(mod)              # cages render as a white slab across the picture

log(f"thumbnails: {done} taken in {time.time() - started:.1f}s -> {args.out}")
