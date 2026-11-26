"""A depth map for one picture, as a greyscale PNG (Depth Anything V2, local, free).

    python generate/depth_map.py picture.png depth.png

The realism pass hands this to a depth ControlNet so the room stays the room: without it, re-imagining
a still at a denoise high enough to look photographic also turns a wooden cabin into a stone barn, and
the wide shot and the close-up end up in different places.

The same model `depth_set.py` uses to build a set from a photograph, asked for only the picture part of
its answer. White is near, black is far - what the SDXL depth ControlNet was trained on.
"""
import os
import sys

import numpy as np
from PIL import Image


def depth_of(image, pipe=None):
    """A greyscale depth image the same size as `image`, white near and black far."""
    if pipe is None:
        import torch
        from transformers import pipeline
        pipe = pipeline("depth-estimation", model="depth-anything/Depth-Anything-V2-Small-hf",
                        device=0 if torch.cuda.is_available() else -1)
    said = pipe(image)["predicted_depth"].squeeze().cpu().numpy().astype(np.float32)
    low, high = float(said.min()), float(said.max())
    near = (said - low) / (high - low) if high - low > 1e-6 else np.zeros_like(said)
    out = Image.fromarray((near * 255).astype(np.uint8), mode="L")
    return out if out.size == image.size else out.resize(image.size, Image.BILINEAR)


def main(args):
    if len(args) < 2:
        raise SystemExit("usage: python generate/depth_map.py PICTURE OUT.png [MORE_PICTURE MORE_OUT ...]")
    import torch
    from transformers import pipeline
    pipe = pipeline("depth-estimation", model="depth-anything/Depth-Anything-V2-Small-hf",
                    device=0 if torch.cuda.is_available() else -1)
    for src, out in zip(args[0::2], args[1::2]):
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        depth_of(Image.open(src).convert("RGB"), pipe).save(out)
        print(f"CF: depth {os.path.basename(src)} -> {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
