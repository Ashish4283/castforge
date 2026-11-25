"""Turning one generated picture of cloth into a material a character can wear (pure, tested; no bpy).

A diffusion model on a rented GPU is good at exactly one thing here: making a square of cloth that looks
like cloth - worn denim, cream cable knit, black velvet. It is not good at the rest, and the rest is most
of the work:

  Does it TILE?        A square that does not wrap is useless: put it on a trouser leg and there is a
                       hard seam every repeat. This has to be measured, not hoped for, because a
                       generator will happily hand back a beautiful square with a seam in it.
  Where is the relief? Cloth is not flat. A knit has loops, denim has a twill ridge. That comes from a
                       normal map, and a normal map can be derived from the picture - the light and dark
                       of a weave IS its height, near enough, and deriving it costs nothing and is the
                       same every time.
  How does it shine?   Roughness varies across real cloth: the raised threads catch light, the gaps do
                       not. Also derivable.

So the GPU makes ONE image and this makes the other three, on the laptop, in milliseconds. That is worth
saying plainly: the expensive, flaky, rented part of the job is as small as it can be, and everything
downstream of it is deterministic and testable.
"""
import math

KINDS = ("denim", "knit", "velvet", "leather", "cotton", "wool", "silk", "canvas", "fur")
# What each kind is like under light, before the picture's own detail is laid over it. These are the
# numbers `build_character.FABRICS` already used, kept so a generated fabric and a plain one agree.
LOOK = {
    "denim": {"rough": 0.82, "sheen": 0.15, "bump": 0.55},
    "knit": {"rough": 0.90, "sheen": 0.45, "bump": 1.00},
    "velvet": {"rough": 0.65, "sheen": 0.70, "bump": 0.30},
    "leather": {"rough": 0.40, "sheen": 0.05, "bump": 0.40, "coat": 0.30},
    "cotton": {"rough": 0.85, "sheen": 0.25, "bump": 0.45},
    "wool": {"rough": 0.92, "sheen": 0.40, "bump": 0.85},
    "silk": {"rough": 0.25, "sheen": 0.85, "bump": 0.15},
    "canvas": {"rough": 0.88, "sheen": 0.10, "bump": 0.70},
    "fur": {"rough": 0.95, "sheen": 1.00, "bump": 1.20},
}
SEAM_OK = 1.6        # how much worse the wrap may be than the picture's own grain before it is a seam


def _lum(rgb):
    """Perceived brightness of an (h, w, 3) array in 0..1, as an (h, w) array. numpy in, numpy out."""
    import numpy as np
    a = np.asarray(rgb, dtype=np.float32)
    if a.ndim == 2:
        return a
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def seam(rgb):
    """How badly this picture fails to tile: {across, down, worst} where 1.0 is seamless.

    Measured as the difference ACROSS THE WRAP (the last column against the first) over the difference
    between ordinary neighbouring columns inside the picture. A seamless tile wraps no worse than it
    joins anywhere else, so the ratio sits near 1. A picture with a seam in it comes back at 3, 10, 40 -
    and the number says how bad, which a yes/no never would."""
    import numpy as np
    a = _lum(rgb)
    h, w = a.shape
    if h < 4 or w < 4:
        return {"across": 0.0, "down": 0.0, "worst": 0.0}
    inside_x = float(np.mean(np.abs(a[:, 1:] - a[:, :-1])))
    inside_y = float(np.mean(np.abs(a[1:, :] - a[:-1, :])))
    wrap_x = float(np.mean(np.abs(a[:, 0] - a[:, -1])))
    wrap_y = float(np.mean(np.abs(a[0, :] - a[-1, :])))
    across = wrap_x / inside_x if inside_x > 1e-6 else (0.0 if wrap_x < 1e-6 else 99.0)
    down = wrap_y / inside_y if inside_y > 1e-6 else (0.0 if wrap_y < 1e-6 else 99.0)
    return {"across": across, "down": down, "worst": max(across, down)}


def tiles(rgb, limit=SEAM_OK):
    """True when this picture can be repeated without a visible join."""
    return seam(rgb)["worst"] <= limit


def blur(a, radius=1):
    """A cheap box blur that WRAPS, so it never invents an edge a tiling picture does not have."""
    import numpy as np
    out = np.asarray(a, dtype=np.float32)
    for _ in range(max(0, int(radius))):
        out = (out
               + np.roll(out, 1, 0) + np.roll(out, -1, 0)
               + np.roll(out, 1, 1) + np.roll(out, -1, 1)) / 5.0
    return out


def height(rgb, soften=1):
    """The cloth's relief, 0..1, from how light and dark it is. Light threads stand proud.

    This is an approximation and an honest one: it is exactly true of a woven surface lit flatly, which
    is what a generated swatch is, and it is wrong wherever the picture's brightness is colour rather
    than shape (a printed pattern). Which is why `bump` per kind exists - a print gets a gentle one."""
    import numpy as np
    a = blur(_lum(rgb), soften)
    lo, hi = float(a.min()), float(a.max())
    return (a - lo) / (hi - lo) if hi - lo > 1e-6 else np.zeros_like(a)


def normals(hmap, strength=1.0):
    """A tangent-space normal map in 0..1 RGB from a height map, wrapping at every edge.

    The slope of the height in x and y IS the surface's tilt; the blue channel is what is left over of a
    unit vector. Rolling rather than clamping at the edges is what keeps a tiling height map's normal
    map tiling too - clamp it and a seam appears in the lighting that was not in the picture."""
    import numpy as np
    h = np.asarray(hmap, dtype=np.float32)
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5 * strength * 8.0
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5 * strength * 8.0
    nz = np.ones_like(h)
    length = np.sqrt(dx * dx + dy * dy + nz * nz)
    return np.stack([(-dx / length) * 0.5 + 0.5,
                     (-dy / length) * 0.5 + 0.5,
                     (nz / length) * 0.5 + 0.5], axis=-1).astype(np.float32)


def roughness(hmap, kind="cotton", spread=0.18):
    """Roughness across the cloth: the raised threads catch light, the gaps between them do not."""
    import numpy as np
    base = LOOK.get(kind, LOOK["cotton"])["rough"]
    h = np.asarray(hmap, dtype=np.float32)
    return np.clip(base - (h - 0.5) * 2.0 * spread, 0.02, 1.0).astype(np.float32)


def maps_for(rgb, kind="cotton"):
    """{height, normal, roughness} for one swatch of cloth, plus how well it tiles and what it is like.

    One call, so a caller never has to remember the order or the per-kind strength."""
    look = LOOK.get(kind, LOOK["cotton"])
    h = height(rgb)
    return {"height": h,
            "normal": normals(h, look.get("bump", 0.5)),
            "roughness": roughness(h, kind),
            "look": look,
            "seam": seam(rgb)}


def check(rgb, kind="cotton", limit=SEAM_OK):
    """Plain-language problems with a swatch; empty when it can be used as a material."""
    import numpy as np
    out = []
    a = np.asarray(rgb, dtype=np.float32)
    if a.ndim != 3 or a.shape[2] < 3:
        return ["a swatch must be a colour picture"]
    h, w = a.shape[:2]
    if h != w:
        out.append(f"a tile must be square; this is {w} x {h}")
    if h < 256:
        out.append(f"{w} x {h} is too small to put on a garment; 1024 or more")
    if kind not in KINDS:
        out.append(f"{kind!r} is not one of {', '.join(KINDS)}")
    bad = seam(rgb)
    if bad["worst"] > limit:
        which = "across" if bad["across"] >= bad["down"] else "down"
        out.append(f"it does not tile {which}: the join is {bad['worst']:.1f}x worse than the cloth's own "
                   f"grain, so there will be a seam every repeat")
    spread = float(np.std(_lum(a)))
    if spread < 0.02:
        out.append("it is flat colour, not cloth: there is no weave in it to light")
    return out


def tile_size(width, metres=0.35):
    """How many times a swatch repeats over a garment, given what width of cloth it represents.

    A 1024-pixel square standing for 35 cm of cloth is about 3 repeats per metre, which is the scale
    somebody reads as fabric rather than as wallpaper."""
    return 1.0 / max(0.02, float(metres)) if width else 1.0


def describe(kind, seam_now):
    """One line for a person."""
    look = LOOK.get(kind, LOOK["cotton"])
    how = ("seamless" if seam_now["worst"] <= 1.2 else
           "tiles well" if seam_now["worst"] <= SEAM_OK else
           f"has a seam ({seam_now['worst']:.1f}x)")
    return (f"{kind}: roughness {look['rough']:.2f}, sheen {look.get('sheen', 0):.2f}, "
            f"relief {look.get('bump', 0):.2f} - {how}")
