"""Measure the skin tone of every installed MPFB skin texture (run once after installing packs).

    .venv/Scripts/python generate/index_assets.py
writes ../asset_index.json, read by blender/build_character.py.
"""
import glob
import json
import os

import numpy as np
from PIL import Image

MPFB_DATA = os.path.expandvars(r"%APPDATA%\Blender Foundation\Blender\5.2\extensions\.user\user_default\mpfb\data")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "asset_index.json")

skins = {}
for mhmat in glob.glob(os.path.join(MPFB_DATA, "skins", "*", "*.mhmat")):
    name = os.path.splitext(os.path.basename(mhmat))[0]
    tex = None
    for line in open(mhmat, encoding="utf-8", errors="ignore"):
        if line.startswith("diffuseTexture "):
            tex = os.path.join(os.path.dirname(mhmat), line.split(" ", 1)[1].strip())
    if not tex or not os.path.exists(tex):
        continue
    im = Image.open(tex).convert("RGB")
    im.thumbnail((256, 256))
    px = np.asarray(im).reshape(-1, 3).astype(float)
    lum = px.mean(axis=1)
    px = px[(lum > 25) & (lum < 245)]          # skip empty UV space and highlights
    skins[name] = {"mhmat": mhmat, "tone": [int(v) for v in np.median(px, axis=0)]}
    print(name, skins[name]["tone"])

eyes = {}
for mhmat in glob.glob(os.path.join(MPFB_DATA, "eyes", "materials", "*.mhmat")):
    name = os.path.splitext(os.path.basename(mhmat))[0]
    tex = os.path.join(os.path.dirname(mhmat), f"{name}_eye.png")
    if not os.path.exists(tex):
        continue
    im = np.asarray(Image.open(tex).convert("RGB")).astype(float)
    h, w = im.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    # each texture holds two eyeballs; the iris of the upper one is centred at (0.71, 0.29)
    r2 = ((xx - 0.71 * w) ** 2 + (yy - 0.29 * h) ** 2) / (w * w)
    px = im[(r2 > 0.035 ** 2) & (r2 < 0.09 ** 2)]   # ring between pupil and sclera
    eyes[name] = {"mhmat": mhmat, "iris": [int(v) for v in np.median(px, axis=0)]}
    print("eye", name, eyes[name]["iris"])

json.dump({"mpfb_data": MPFB_DATA, "skins": skins, "eyes": eyes}, open(OUT, "w"), indent=1)
print(f"{len(skins)} skins, {len(eyes)} eye colours -> {OUT}")
