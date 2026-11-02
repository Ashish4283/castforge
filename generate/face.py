"""Face landmarks (MediaPipe Face Landmarker, 478 points) for CastForge, free on CPU.

Used by analyze_photo.py on the user's photo and, through the CLI below, by
blender/calibrate_face.py on a render of the MPFB head (Blender's Python has no MediaPipe).

    .venv/Scripts/python generate/face.py image.png out.json
"""
import json
import os
import sys

import mediapipe as mp
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "face_landmarker.task")

from face_ids import *  # noqa: F401,F403  (index sets shared with Blender)
from face_ids import FACE_OVAL, LEFT_IRIS, RIGHT_IRIS  # noqa: F401

_landmarker = None


def detect(rgb):
    """478 (x, y) pixel landmarks for the largest face in an RGB uint8 array, or None."""
    global _landmarker
    if _landmarker is None:
        v = mp.tasks.vision
        _landmarker = v.FaceLandmarker.create_from_options(v.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=MODEL), num_faces=1))
    h, w = rgb.shape[:2]
    res = _landmarker.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb)))
    if not res.face_landmarks:
        return None
    return np.array([[p.x * w, p.y * h] for p in res.face_landmarks[0]])


def detect_in_box(rgb, box, size=768):
    """Detect inside box (x0, y0, x1, y1), upscaled to `size` so small faces in full-body photos work."""
    from PIL import Image
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    H, W = rgb.shape[:2]
    x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)
    crop = Image.fromarray(rgb[y0:y1, x0:x1]).resize((size, size), Image.LANCZOS)
    pts = detect(np.asarray(crop))
    if pts is None:
        return None
    return pts * [(x1 - x0) / size, (y1 - y0) / size] + [x0, y0]


if __name__ == "__main__":
    from PIL import Image
    img = np.asarray(Image.open(sys.argv[1]).convert("RGB"))
    pts = detect(img)
    json.dump({"landmarks": None if pts is None else pts.tolist(), "size": [img.shape[1], img.shape[0]]},
              open(sys.argv[2], "w"))
    print("found" if pts is not None else "no face")
