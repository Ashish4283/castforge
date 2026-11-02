"""CastForge photo stage: one full-body front photo -> character spec JSON (free, CPU only).

Reads body proportions from MediaPipe pose landmarks and the person's silhouette, and
colours (skin, hair, top, bottom, shoes) from MediaPipe's hair/skin/clothes segmenter.
The Blender build stage fits an MPFB body to these numbers, so the back of the body,
the hidden sides and the clothing all come from a complete 3D model, not from guessing
pixels.

    .venv/Scripts/python generate/analyze_photo.py photo.png spec.json [--debug debug.png] [--face-photo selfie.jpg]

--face-photo: an optional close-up of the same person's face, used for face shape and texture
(a face in a full-body photo is often only ~50 px wide).
"""
import argparse
import json
import os
import sys

import mediapipe as mp
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(HERE, "..", "models")

# selfie_multiclass_256x256 categories
BG, HAIR, BODY_SKIN, FACE_SKIN, CLOTHES, OTHER = range(6)
# pose landmark ids
NOSE, L_SH, R_SH, L_EL, R_EL, L_WR, R_WR = 0, 11, 12, 13, 14, 15, 16
L_HIP, R_HIP, L_KN, R_KN, L_AN, R_AN, L_HEEL, R_HEEL, L_FT, R_FT = 23, 24, 25, 26, 27, 28, 29, 30, 31, 32

ap = argparse.ArgumentParser()
ap.add_argument("photo")
ap.add_argument("out")
ap.add_argument("--debug", help="write an overlay PNG showing what was measured")
ap.add_argument("--face-photo", help="optional close-up of the face for likeness")
args = ap.parse_args()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import face as facemod  # noqa: E402

img = Image.open(args.photo)
if img.mode in ("RGBA", "LA", "P"):
    rgba = img.convert("RGBA")
    flat = Image.new("RGB", rgba.size, "white")
    flat.paste(rgba, mask=rgba.split()[3])
    img = flat
rgb = np.asarray(img.convert("RGB"))
H, W = rgb.shape[:2]
mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))

vision = mp.tasks.vision
pose = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
    base_options=mp.tasks.BaseOptions(model_asset_path=os.path.join(MODELS, "pose_landmarker_heavy.task")),
    num_poses=2))
res = pose.detect(mp_img)
if not res.pose_landmarks:
    sys.exit("no person found in the photo")
if len(res.pose_landmarks) > 1:
    sys.exit("more than one person in the photo; use a photo of one person")
lm = res.pose_landmarks[0]
P = np.array([[p.x * W, p.y * H] for p in lm])
vis = np.array([p.visibility for p in lm])

problems = []
for name, ids in (("feet", (L_AN, R_AN, L_HEEL, R_HEEL)), ("hips", (L_HIP, R_HIP)), ("shoulders", (L_SH, R_SH))):
    if vis[list(ids)].min() < 0.5:
        problems.append(f"{name} not clearly visible: use a full-body photo, head to toe")
# facing the camera: the person's left shoulder appears on the image's right
if P[L_SH, 0] <= P[R_SH, 0]:
    problems.append("person seems to face away from the camera: use a front-facing photo")

seg = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
    base_options=mp.tasks.BaseOptions(model_asset_path=os.path.join(MODELS, "selfie_multiclass_256x256.tflite")),
    output_category_mask=True))
cat = seg.segment(mp_img).category_mask.numpy_view().copy().reshape(H, W)
person = cat != BG

rows = np.where(person.any(axis=1))[0]
if not len(rows):
    sys.exit("could not separate the person from the background")
top = rows[0]
bottom = max(P[[L_HEEL, R_HEEL, L_FT, R_FT], 1].max(), rows[-1] if rows[-1] < H - 1 else 0)
height_px = bottom - top
if height_px < 0.5 * H:
    problems.append("person is small in the frame: crop closer for better measurements")


def mid(a, b):
    return (P[a] + P[b]) / 2


def torso_width_at(y):
    """Width of the person's own torso at row y, ignoring arms hanging beside it."""
    y = int(round(y))
    row = person[y]
    cx = int(round(mid(L_HIP, R_HIP)[0]))
    if not row[cx]:
        return None
    left = cx
    while left > 0 and row[left - 1]:
        left -= 1
    right = cx
    while right < W - 1 and row[right + 1]:
        right += 1
    # arms pressed to the body merge into this run; then the torso width is unknowable
    arm_l = min(P[L_EL, 0], P[L_WR, 0])
    arm_r = max(P[R_EL, 0], P[R_WR, 0])
    if left <= arm_r or right >= arm_l:
        return None
    return right - left


sh_y = mid(L_SH, R_SH)[1]
hip_y = mid(L_HIP, R_HIP)[1]
waist_y = sh_y + 0.62 * (hip_y - sh_y)
waist_w = torso_width_at(waist_y)
hip_w = torso_width_at(hip_y)

ratios = {
    "shoulder_width": float(np.linalg.norm(P[L_SH] - P[R_SH]) / height_px),
    "hip_width": float(np.linalg.norm(P[L_HIP] - P[R_HIP]) / height_px),
    "leg_length": float((bottom - hip_y) / height_px),
    "torso_length": float((hip_y - sh_y) / height_px),
    "head_to_shoulder": float((sh_y - top) / height_px),
    "waist_silhouette": float(waist_w / height_px) if waist_w else None,
    "hip_silhouette": float(hip_w / height_px) if hip_w else None,
}


def colour(mask, name):
    px = rgb[mask]
    if len(px) < 50:
        return None
    return [int(v) for v in np.median(px, axis=0)]


ys = np.arange(H)[:, None].repeat(W, axis=1)
ankle_y = P[[L_AN, R_AN], 1].mean()
colours = {
    "skin": colour((cat == FACE_SKIN) | (cat == BODY_SKIN), "skin"),
    "hair": colour(cat == HAIR, "hair"),
    "top": colour((cat == CLOTHES) & (ys < hip_y), "top"),
    "bottom": colour((cat == CLOTHES) & (ys >= hip_y) & (ys < ankle_y), "bottom"),
    "shoes": colour(person & (ys >= ankle_y) & (cat != BODY_SKIN), "shoes"),
}


def skin_along(a, b, radius):
    """Fraction of skin among person pixels sampled along the limb segment a->b."""
    skin = total = 0
    for t in np.linspace(0.2, 0.8, 13):
        x, y = P[a] + t * (P[b] - P[a])
        x0, x1 = int(max(x - radius, 0)), int(min(x + radius, W - 1))
        y0, y1 = int(max(y - radius, 0)), int(min(y + radius, H - 1))
        patch = cat[y0:y1 + 1, x0:x1 + 1]
        skin += np.isin(patch, (BODY_SKIN, FACE_SKIN)).sum()
        total += (patch != BG).sum()
    return float(skin / total) if total else 0.0


r = max(2, int(0.012 * height_px))
skin_parts = {
    "forearms": (skin_along(L_EL, L_WR, r) + skin_along(R_EL, R_WR, r)) / 2,
    "thighs": (skin_along(L_HIP, L_KN, r) + skin_along(R_HIP, R_KN, r)) / 2,
    "shins": (skin_along(L_KN, L_AN, r) + skin_along(R_KN, R_AN, r)) / 2,
}


def similar(c1, c2):
    return c1 is not None and c2 is not None and np.linalg.norm(np.subtract(c1, c2)) < 40


if skin_parts["shins"] < 0.5:
    garment = "trousers"
elif skin_parts["thighs"] > 0.5:
    garment = "dress" if similar(colours["top"], colours["bottom"]) else "shorts"
else:
    garment = "dress" if similar(colours["top"], colours["bottom"]) else "skirt"
clothing = {"garment": garment, "sleeves": "short" if skin_parts["forearms"] > 0.5 else "long",
            "skin_fraction": {k: round(v, 2) for k, v in skin_parts.items()}}

hair_rows = np.where((cat == HAIR).any(axis=1))[0]
hair_length = "none"
if len(hair_rows):
    reach = (hair_rows[-1] - top) / height_px
    hair_length = "short" if reach < 0.13 else "medium" if reach < 0.2 else "long"



def load_rgb(path):
    im = Image.open(path)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        flat = Image.new("RGB", im.size, "white")
        flat.paste(im, mask=im.split()[3])
        im = flat
    return np.asarray(im.convert("RGB"))


# --- face: landmarks for shape fitting and texture -------------------------------------------
face = None
if args.face_photo:
    face_rgb = load_rgb(args.face_photo)
    face_pts = facemod.detect(face_rgb)
    face_src = os.path.abspath(args.face_photo)
else:
    face_rgb = rgb
    ears = P[[7, 8]]
    c = P[NOSE]
    half = max(1.3 * np.linalg.norm(ears[0] - ears[1]), 0.09 * height_px)
    face_pts = facemod.detect_in_box(rgb, (c[0] - half, c[1] - 1.15 * half, c[0] + half, c[1] + 0.85 * half))
    face_src = os.path.abspath(args.photo)
if face_pts is None:
    problems.append("no face found: use a photo where the face is clearly visible (or add --face-photo)")
else:
    fh, fw = face_rgb.shape[:2]
    face_w = float(np.ptp(face_pts[facemod.FACE_OVAL, 0]))
    if face_w < 80:
        problems.append(f"face is only {face_w:.0f} px wide: likeness will be soft; add a face close-up")

    def iris_colour(ids):
        cx, cy = face_pts[ids[0]]
        r = max(1.0, np.linalg.norm(face_pts[ids[1]] - face_pts[ids[0]]) * 0.6)
        yy, xx = np.mgrid[0:fh, 0:fw]
        m = (xx - cx) ** 2 + (yy - cy) ** 2 < r ** 2
        return [int(v) for v in np.median(face_rgb[m], axis=0)] if m.sum() > 3 else None

    if face_rgb is rgb:
        face_seg = cat
    else:
        face_seg = seg.segment(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(face_rgb))) \
            .category_mask.numpy_view().copy().reshape(fh, fw)
    face_skin = face_rgb[face_seg == FACE_SKIN]
    face = {
        "image": face_src,
        "size": [int(fw), int(fh)],
        "landmarks": [[round(float(x), 2), round(float(y), 2)] for x, y in face_pts],
        "width_px": round(face_w, 1),
        "skin_tone": [int(v) for v in np.median(face_skin, axis=0)] if len(face_skin) > 50 else colours["skin"],
        "iris": iris_colour(facemod.LEFT_IRIS) or iris_colour(facemod.RIGHT_IRIS),
    }

spec = {
    "photo": os.path.abspath(args.photo),
    "face": face,
    "image_size": [W, H],
    "height_px": float(height_px),
    "ratios": ratios,
    "colours": colours,
    "clothing": clothing,
    "hair_length": hair_length,
    "problems": problems,
}
with open(args.out, "w") as f:
    json.dump(spec, f, indent=2)
print(json.dumps(spec, indent=2))

if args.debug:
    over = Image.fromarray(rgb).convert("RGB")
    tint = np.zeros((H, W, 3), np.uint8)
    for c, col in ((HAIR, (255, 0, 0)), (BODY_SKIN, (255, 200, 0)), (FACE_SKIN, (255, 255, 0)),
                   (CLOTHES, (0, 120, 255)), (OTHER, (0, 255, 0))):
        tint[cat == c] = col
    over = Image.blend(over, Image.fromarray(tint), 0.35)
    d = ImageDraw.Draw(over)
    for i in (L_SH, R_SH, L_EL, R_EL, L_WR, R_WR, L_HIP, R_HIP, L_KN, R_KN, L_AN, R_AN):
        x, y = P[i]
        d.ellipse([x - 5, y - 5, x + 5, y + 5], fill=(255, 0, 255))
    for y, col in ((top, "red"), (bottom, "red"), (waist_y, "cyan"), (hip_y, "cyan")):
        d.line([(0, y), (W, y)], fill=col, width=2)
    over.save(args.debug)
