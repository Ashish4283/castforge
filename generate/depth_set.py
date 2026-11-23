"""Turn a background image into a solid 3D set (free, local): Depth Anything V2 -> metric relief mesh +
walkable-floor map.

The image is seen through CastForge's set camera (level, 1.45 m high, 35 mm lens). Depth Anything gives
relative depth; the floor at the bottom of the picture fixes the scale (a level camera at a known height
sees the floor at a known distance in every image row). Every pixel then becomes a 3D point, the mesh is
cut where depth jumps (so a stool stands apart from the wall behind it), and everything standing on the
floor becomes an obstacle in a top-down map that walk paths route around.

    python generate/depth_set.py background.png out_dir
writes out_dir/set.obj (+ set.mtl), out_dir/set.json, out_dir/floor_map.png
"""
import json
import os
import sys

import numpy as np
from PIL import Image

CAM_H = 1.45                  # camera height (m)
LENS, SENSOR = 35.0, 36.0     # mm, horizontal sensor width (Blender default)
STEP = 4                      # mesh grid step (px)
CELL = 0.05                   # floor map cell (m)

img_path, out = sys.argv[1], sys.argv[2]
# --pitch DEG: the picture's camera looks down by DEG (known from e.g. a door: real doors are ~2 m tall);
# without it the camera is taken as level (searching tilt and lens together is ambiguous)
PITCH = float(sys.argv[sys.argv.index("--pitch") + 1]) * np.pi / 180 if "--pitch" in sys.argv else 0.0
os.makedirs(out, exist_ok=True)
img = Image.open(img_path).convert("RGB")
W, H = img.size

import torch  # noqa: E402
from transformers import pipeline  # noqa: E402

depth_pipe = pipeline("depth-estimation", model="depth-anything/Depth-Anything-V2-Small-hf",
                      device=0 if torch.cuda.is_available() else -1)
disp = depth_pipe(img)["predicted_depth"].squeeze().cpu().numpy().astype(np.float64)
if disp.shape != (H, W):
    disp = np.asarray(Image.fromarray(disp.astype(np.float32)).resize((W, H), Image.BILINEAR), np.float64)

cx, cy = W / 2, H / 2
uu, vv = np.meshgrid(np.arange(W) + 0.5, np.arange(H) + 0.5)


def calibrate(lens, pitch):
    """Floor calibration for one lens and camera tilt (pitch, radians, + = looking down): 1/T = a*disp + b,
    T = depth along the camera's view axis, fixed by the floor (a level-or-tilted camera at a known height
    sees the floor at a known depth in every pixel). Starts from the bottom rows' centre, then refits on
    every pixel that lands at floor height. Returns the fit and how flat the floor came out (a wrong lens
    or tilt bends or slopes a real floor)."""
    f_px = lens / SENSOR * W
    rx, rz = (uu - cx) / f_px, -(vv - cy) / f_px    # ray in camera space: (rx, 1, rz) = (right, forward, up)
    cp, sp = np.cos(pitch), np.sin(pitch)
    dy, dz = cp + rz * sp, -sp + rz * cp            # the ray in the world (camera tilted down by pitch)
    mask = (vv > H * 0.88) & (np.abs(uu - cx) < W * 0.3) & (dz < -0.02)
    for _ in range(4):
        tt = CAM_H / -dz[mask]
        A = np.stack([disp[mask], np.ones(mask.sum())], axis=1)
        (a, b), *_ = np.linalg.lstsq(A, 1.0 / tt, rcond=None)
        T = 1.0 / np.clip(a * disp + b, 1.0 / 60.0, None)
        Z = CAM_H + dz * T
        mask = (np.abs(Z) < 0.04) & (dz < -0.02)
    # flatness across the whole width of the lower picture, where interiors and streets are mostly floor
    low = (vv > H * 0.75)
    err = np.percentile(np.abs(Z[low]), 50)
    return err, lens, pitch, rx, dy, dz, T, Z, mask


if PITCH is not None:
    tries = [(lens, PITCH) for lens in (16, 18, 20, 24, 28, 35)]
else:
    tries = [(lens, np.radians(pd)) for lens in (16, 18, 20, 24, 28, 35) for pd in (0, 3, 6, 9)]
best = min((calibrate(*t) for t in tries), key=lambda r: r[0])
err, LENS, PITCH, rx, dy, dz, T, Z, mask = best
print(f"lens {LENS} mm, camera tilted down {np.degrees(PITCH):.1f} deg fits best (floor flatness {err * 100:.1f} cm)")
T = np.minimum(T, 40.0)
X, Y, Z = rx * T, dy * T, CAM_H + dz * T
floor_pixels = int(mask.sum())

# --- relief mesh: grid every STEP px, triangles cut across depth jumps ---------------------------
gy, gx = np.arange(0, H, STEP), np.arange(0, W, STEP)
gy = np.append(gy, H - 1) if gy[-1] != H - 1 else gy
gx = np.append(gx, W - 1) if gx[-1] != W - 1 else gx
GX, GY = np.meshgrid(gx, gy)
P = np.stack([X[GY, GX], Y[GY, GX], Z[GY, GX]], -1)
UV = np.stack([(GX + 0.5) / W, 1 - (GY + 0.5) / H], -1)
nr, nc = P.shape[:2]
idx = np.arange(nr * nc).reshape(nr, nc)
depth = P[..., 1]


def ok(*ids):
    d = depth.reshape(-1)[list(ids)]
    return d.max() / d.min() < 1.06 + 0.004 * d.min()     # allow more stretch far away


faces = []
for r in range(nr - 1):
    for c in range(nc - 1):
        a_, b_, c_, d_ = idx[r, c], idx[r, c + 1], idx[r + 1, c + 1], idx[r + 1, c]
        if ok(a_, b_, c_):
            faces.append((a_, c_, b_))
        if ok(a_, c_, d_):
            faces.append((a_, d_, c_))
with open(os.path.join(out, "set.obj"), "w") as fh:
    fh.write("mtllib set.mtl\nusemtl set\n")
    for p in P.reshape(-1, 3):
        fh.write(f"v {p[0]:.4f} {p[1]:.4f} {p[2]:.4f}\n")
    for t in UV.reshape(-1, 2):
        fh.write(f"vt {t[0]:.5f} {t[1]:.5f}\n")
    for f in faces:
        fh.write("f " + " ".join(f"{i + 1}/{i + 1}" for i in f) + "\n")
with open(os.path.join(out, "set.mtl"), "w") as fh:
    # relative to the .mtl: Blender reads an absolute map_Kd as relative to the .obj folder and then
    # cannot find the picture ("Cannot load image file: <obj folder>\\C:\\...")
    try:
        texture = os.path.relpath(os.path.abspath(img_path), os.path.abspath(out)).replace("\\", "/")
    except ValueError:                     # another drive: there is nothing relative to say
        texture = os.path.abspath(img_path)
    fh.write(f"newmtl set\nmap_Kd {texture}\n")

# --- floor map: cells seen as floor are walkable; anything 5 cm..1.9 m above the floor blocks ------
fl = mask & (Y < 25)
xs, ys = X[fl], Y[fl]
x0, x1 = np.percentile(xs, 0.5) - 0.5, np.percentile(xs, 99.5) + 0.5
y0, y1 = max(ys.min() - 0.2, 0.0), min(np.percentile(ys, 99.5) + 0.5, 25)
gw, gh = int((x1 - x0) / CELL) + 1, int((y1 - y0) / CELL) + 1
floor = np.zeros((gh, gw), bool)
block = np.zeros((gh, gw), bool)


def cells(xa, ya):
    i = ((ya - y0) / CELL).astype(int)
    j = ((xa - x0) / CELL).astype(int)
    k = (i >= 0) & (i < gh) & (j >= 0) & (j < gw)
    return i[k], j[k]


floor[cells(xs, ys)] = True
obst = (Z > 0.05) & (Z < 1.9) & (Y < 25)
block[cells(X[obst], Y[obst])] = True


def shift_or(m, di, dj):
    o = np.zeros_like(m)
    o[max(di, 0):m.shape[0] + min(di, 0), max(dj, 0):m.shape[1] + min(dj, 0)] = \
        m[max(-di, 0):m.shape[0] + min(-di, 0), max(-dj, 0):m.shape[1] + min(-dj, 0)]
    return o


def dilate(m, r):
    o = m.copy()
    for di in range(-r, r + 1):
        for dj in range(-r, r + 1):
            if di * di + dj * dj <= r * r:
                o |= shift_or(m, di, dj)
    return o


# far floor is sampled in stripes (one pixel row spans many cells): close the gaps between them
floor = ~dilate(~dilate(floor, 4), 4)
walk = floor & ~block
Image.fromarray((np.flipud(walk) * 200 + np.flipud(block) * 55).astype(np.uint8)).save(
    os.path.join(out, "floor_map.png"))

near_y = float(np.percentile(ys, 2))
meta = {
    "image": os.path.abspath(img_path), "size": [W, H],
    "camera": {"height": CAM_H, "lens": LENS, "sensor": SENSOR, "location": [0, 0, CAM_H], "pitch": float(PITCH)},
    "floor_pixels": floor_pixels,
    "grid": {"x0": float(x0), "y0": float(y0), "cell": CELL, "w": gw, "h": gh},
    "walkable": np.packbits(walk.reshape(-1)).tolist(),
    "stage_origin": [0.0, near_y + 1.2],          # stage (0, 0) = 1.2 m beyond the nearest visible floor
    "faces": len(faces),
}
json.dump(meta, open(os.path.join(out, "set.json"), "w"))
print(f"set: {len(faces)} triangles, floor fit on {floor_pixels} px, walkable {walk.sum() * CELL * CELL:.1f} m2, "
      f"stage origin y={meta['stage_origin'][1]:.2f} m")
