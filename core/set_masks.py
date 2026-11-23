"""Object masks on set pictures (pure numpy; tested).

A mask is a greyscale picture the size of the set picture: 255 = the object as seen, 128 = a part of the object
hidden behind something else (marked by the user), 0 = not the object. sets/<set>/masks/<id>.png."""
import numpy as np

VISIBLE, HIDDEN = 255, 128


def quantize(mask):
    """Any greyscale -> exactly 0 / 128 / 255 (resizing and PNG tools blur the values)."""
    m = np.asarray(mask)
    return np.where(m > 191, VISIBLE, np.where(m > 63, HIDDEN, 0)).astype(np.uint8)


def bbox(mask):
    """[left, top, right, bottom] fractions around the whole object (hidden parts included), or None."""
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return None
    h, w = mask.shape
    return [round(xs.min() / w, 4), round(ys.min() / h, 4), round((xs.max() + 1) / w, 4), round((ys.max() + 1) / h, 4)]


def fill_hidden(rgb, mask, max_steps=400):
    """The object cut out (RGBA), its hidden parts painted by growing the colours of its visible parts inward,
    so a chair leg behind a table continues in the chair's own colours. Pixels outside the object are clear."""
    rgb = np.asarray(rgb, dtype=np.float32)[..., :3]
    known = mask == VISIBLE
    todo = mask == HIDDEN
    out = np.where(known[..., None], rgb, 0.0)
    for _ in range(max_steps):
        if not todo.any():
            break
        total = np.zeros_like(out)
        count = np.zeros(known.shape, np.float32)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
            k = np.roll(known, (dy, dx), (0, 1))
            total += np.roll(out, (dy, dx), (0, 1)) * k[..., None]
            count += k
        grow = todo & (count > 0)
        if not grow.any():
            break
        out[grow] = total[grow] / count[grow][:, None]
        known = known | grow
        todo = todo & ~grow
    alpha = np.where(mask > 0, 255, 0).astype(np.uint8)
    return np.dstack([np.clip(out, 0, 255).astype(np.uint8), alpha])


def patch_background(rgb, masks, max_steps=600, soften=2):
    """The picture with the masked objects taken out of it: an empty room.

    `masks` is one mask or a list of them (the same ones the region editor saves). Every pixel any mask
    claims is repainted by growing the surrounding wall and floor colours inward, so a table lifted into 3D
    does not stay painted on the set picture behind its own 3D copy. `soften` passes of a 3x3 average over
    the patched pixels only keep the fill from reading as streaks; the rest of the picture is untouched."""
    rgb = np.asarray(rgb, dtype=np.float32)[..., :3]
    if isinstance(masks, np.ndarray) and masks.ndim == 2:
        masks = [masks]
    hole = np.zeros(rgb.shape[:2], bool)
    for m in masks:
        hole |= np.asarray(m) > 0
    out = rgb.copy()
    known = ~hole
    todo = hole.copy()
    for _ in range(max_steps):
        if not todo.any():
            break
        total = np.zeros_like(out)
        count = np.zeros(known.shape, np.float32)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
            k = np.roll(known, (dy, dx), (0, 1))
            total += np.roll(out, (dy, dx), (0, 1)) * k[..., None]
            count += k
        grow = todo & (count > 0)
        if not grow.any():
            break
        out[grow] = total[grow] / count[grow][:, None]
        known = known | grow
        todo = todo & ~grow
    for _ in range(max(0, soften)):
        blur = np.zeros_like(out)
        for dy, dx in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)):
            blur += np.roll(out, (dy, dx), (0, 1))
        out[hole] = (blur / 5.0)[hole]
    return np.clip(out, 0, 255).astype(np.uint8)
