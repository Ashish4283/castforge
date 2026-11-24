"""Pieces of clothing a person has cut to their own taste (pure, tested; no bpy).

The wardrobe ships one size of everything. A piece is one of those assets with a person's own edits kept
against it - a longer coat, a wider cuff, a cap that leans left - saved under a name and usable on any
character afterwards.

Why the edits live with the PIECE and not with the character: a garment is fitted to whatever body wears
it (MakeHuman's binding, see blender/preview_mesh.py), so an edit recorded against the garment is refitted
for free on every body. Cut a coat longer once and it is longer on everyone, each of them wearing it at
their own size.

An edit names its place by VERTEX NUMBER, not by a point in space. The asset's mesh is the same mesh every
time it is loaded - the live view loads it flat and the build loads it with a subdivision modifier on top,
which leaves the base vertices and their numbering alone - so a vertex number means exactly the same place
in both, on any body. A point in space would not: it moves with whoever is wearing it.
"""
import re

ROLES = ("hat", "outfit", "top", "bottom", "shoes", "hair", "beard")
MOST_EDITS = 24                      # a piece is a cut, not a sculpture; past this it wants its own asset
REACH = (0.01, 0.4)                  # metres along the surface
SCALE = (0.25, 3.0)
MOVE = 0.4                           # metres
TURN = 180.0                         # degrees


def piece_id(name):
    """A file-safe id from what someone typed. Empty when there is nothing usable in it."""
    out = re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")
    return out[:48]


def blank(name, base, folder, role):
    """A new piece, with nothing changed about it yet."""
    return {"id": piece_id(name), "name": (name or "").strip(), "base": base, "folder": folder,
            "role": role, "colour": None, "edits": []}


def check_edit(edit):
    """Plain-language problems with one edit (empty when it is fine)."""
    out = []
    if not isinstance(edit, dict):
        return ["an edit must be an object"]
    if not isinstance(edit.get("seed"), int) or isinstance(edit.get("seed"), bool) or edit["seed"] < 0:
        out.append("an edit needs 'seed': which vertex of the piece it is centred on")
    radius = edit.get("radius")
    if not isinstance(radius, (int, float)) or not REACH[0] <= radius <= REACH[1]:
        out.append(f"'radius' must be between {REACH[0]} and {REACH[1]} metres")
    scale = edit.get("scale", 1.0)
    if not isinstance(scale, (int, float)) or not SCALE[0] <= scale <= SCALE[1]:
        out.append(f"'scale' must be between {SCALE[0]} and {SCALE[1]}")
    for key, limit in (("move", MOVE), ("turn", TURN)):
        if key not in edit:
            continue
        value = edit[key]
        if not (isinstance(value, (list, tuple)) and len(value) == 3
                and all(isinstance(x, (int, float)) and abs(x) <= limit for x in value)):
            out.append(f"'{key}' must be three numbers, none bigger than {limit}")
    return out


def check(piece, known=None):
    """Plain-language problems with a whole piece (empty when it can be saved)."""
    if not isinstance(piece, dict):
        return ["a piece must be an object"]
    out = []
    if not piece_id(piece.get("name")):
        out.append("give the piece a name")
    if piece.get("role") not in ROLES:
        out.append(f"'role' must be one of {', '.join(ROLES)}")
    if not isinstance(piece.get("base"), str) or not piece["base"]:
        out.append("'base' must say which asset it is cut from")
    elif known is not None and piece["base"] not in known:
        out.append(f"{piece['base']!r} is not something this wardrobe has")
    colour = piece.get("colour")
    if colour is not None and not (isinstance(colour, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", colour)):
        out.append("'colour' must be a colour like #a3161a, or nothing at all")
    edits = piece.get("edits")
    if not isinstance(edits, list):
        out.append("'edits' must be a list")
    else:
        if len(edits) > MOST_EDITS:
            out.append(f"a piece may carry {MOST_EDITS} edits; this one has {len(edits)}")
        for i, edit in enumerate(edits[:MOST_EDITS], 1):
            out += [f"edit {i}: {problem}" for problem in check_edit(edit)]
    return out


def named(value):
    """The piece id in a design slot like "piece:long_coat", or None when the slot names a plain asset."""
    if isinstance(value, str) and value.startswith("piece:"):
        return piece_id(value[len("piece:"):]) or None
    return None


def slot(piece_or_id):
    """What to write into a design slot so it asks for this piece."""
    return f"piece:{piece_or_id['id'] if isinstance(piece_or_id, dict) else piece_id(piece_or_id)}"


def describe(piece):
    """One line for a person: what was done to it."""
    edits = piece.get("edits") or []
    if not edits:
        return "as it comes"
    bits = []
    for edit in edits:
        if abs(edit.get("scale", 1) - 1) > 1e-9:
            bits.append(f"x{edit['scale']:.2f}")
        if any(edit.get("move") or ()):
            bits.append("moved")
        if any(edit.get("turn") or ()):
            bits.append("turned")
    seen = []
    for bit in bits:                                   # keep the order, drop repeats
        if bit not in seen:
            seen.append(bit)
    return f"{len(edits)} edit{'s' if len(edits) != 1 else ''}: " + ", ".join(seen) if seen else "unchanged"


def load_all(root):
    """{id: piece} read from <root>/wardrobe/*.json - the one place both the app and the build read them.

    A file that will not parse is skipped rather than fatal: one bad piece must not stop a build."""
    import glob
    import json
    import os
    out = {}
    for path in sorted(glob.glob(os.path.join(root, "wardrobe", "*.json"))):
        try:
            piece = json.load(open(path, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(piece, dict) and piece.get("id"):
            out[piece["id"]] = piece
    return out
