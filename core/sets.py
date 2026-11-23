"""Reusable sets: a set folder built once (picture, geometry, placed objects) and used by many scenes.

A set folder holds the picture, `set_blueprint.json` (what stands in the room and where), the depth
geometry under `.castforge_geometry/`, and the built `set.blend`. Before this, every scene derived its own
geometry from a picture and re-listed every table and chair; a scene can now name the set instead and
inherit both. No Blender here: scene_kit.py uses these values, and tests/test_sets.py checks them.
"""
import json
import os

GEOMETRY_DIR = ".castforge_geometry"
BLUEPRINT = "set_blueprint.json"
IMAGES = (".png", ".jpg", ".jpeg")


def is_set_folder(folder):
    """True when `folder` looks like a set: a picture and a blueprint beside it."""
    return bool(folder) and os.path.isfile(os.path.join(folder, BLUEPRINT)) and bool(picture(folder))


def picture(folder, named=None):
    """The set's background picture: the one the blueprint names, else the only/first image in the folder
    (the built preview never counts)."""
    if named:
        p = os.path.join(folder, named)
        return p if os.path.isfile(p) else None
    try:
        names = sorted(n for n in os.listdir(folder) if is_picture_name(n))
    except OSError:
        return None
    return os.path.join(folder, names[0]) if names else None


EMPTY = "empty_room.png"
NOT_PICTURES = ("set_preview.png", EMPTY)


def is_picture_name(name):
    """True when a file in a set folder is the set's own picture, and not something the app made from it
    (the build preview, or the empty version of the room). One place, so nothing picks up the wrong file."""
    return bool(name) and name.lower().endswith(IMAGES) and name.lower() not in NOT_PICTURES


def empty_picture(folder, blueprint=None):
    """The set's picture with its objects painted out, when it has one: what a scene should stand its 3D
    furniture in. A set whose objects were lifted into 3D keeps its original picture too (the objects are
    still painted on it), so a scene using the empty version does not see each table twice."""
    named = (blueprint or {}).get("empty_image") or EMPTY
    path = os.path.join(folder, named)
    return path if os.path.isfile(path) else None


def read_blueprint(folder):
    """The set's blueprint as a dict, or an empty one when it has none or it cannot be read."""
    try:
        with open(os.path.join(folder, BLUEPRINT), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {"version": 1, "description": "", "props": []}
    if not isinstance(data, dict):
        return {"version": 1, "description": "", "props": []}
    props = data.get("props")
    data["props"] = [p for p in props if isinstance(p, dict) and p.get("id")] if isinstance(props, list) else []
    return data


PATH_FIELDS = ("file", "picture_mask", "outside_image")


def resolve_paths(props, folder):
    """Set objects name their files relative to the SET folder; a scene reads paths relative to itself, so
    anchor them to the set before the scene ever sees them."""
    out = []
    for prop in props or []:
        prop = dict(prop)
        for field in PATH_FIELDS:
            value = prop.get(field)
            if isinstance(value, str) and value and not os.path.isabs(value):
                prop[field] = os.path.normpath(os.path.join(folder, value))
        out.append(prop)
    return out


def merge_props(set_props, scene_props):
    """The objects a scene ends up with: the set's own first, then the scene's.

    A scene prop with the same id as a set object replaces it in place (so a scene can move the set's
    lantern without re-describing it), and anything else the scene adds comes after. The set's objects are
    marked `from_set` so the editor can tell them apart and the scene file need not repeat them."""
    out, seen = [], {}
    for prop in set_props or []:
        if not isinstance(prop, dict) or not prop.get("id"):
            continue
        seen[prop["id"]] = len(out)
        out.append({**prop, "from_set": True})
    for prop in scene_props or []:
        if not isinstance(prop, dict):
            continue
        at = seen.get(prop.get("id"))
        if at is None:
            out.append(dict(prop))
        else:
            out[at] = {**out[at], **prop, "from_set": True, "edited": True}
    return out


def use_set(folder, scene):
    """What a scene standing on this set ends up with: (background, props, note).

    The whole decision in one tested place: the empty version of the picture when the set has one, else
    the picture itself (a scene that names its own background keeps it), the set's objects with the
    scene's own added after, and a line to log. Raises ValueError when the set has no picture at all."""
    blueprint = read_blueprint(folder)
    original = picture(folder, blueprint.get("image"))
    if not original:
        raise ValueError(f"the set {os.path.basename(folder)} has no picture")
    empty = empty_picture(folder, blueprint)
    background = scene.get("background") or empty or original
    from_set = resolve_paths(blueprint["props"], folder)
    props = merge_props(from_set, scene.get("props"))
    note = (f"set {os.path.basename(folder)}: {len(from_set)} object(s) from the set, {len(props)} in all"
            + (", in the empty room" if background == empty else ""))
    return background, props, note


def geometry_dir(folder):
    """Where the set's shared depth geometry lives (built once, used by every scene on this set)."""
    return os.path.join(folder, GEOMETRY_DIR)


def needs_geometry(folder, image_path):
    """True when the set's geometry is missing or older than its picture."""
    meta = os.path.join(geometry_dir(folder), "set.json")
    if not os.path.isfile(meta) or not os.path.isfile(os.path.join(geometry_dir(folder), "set.obj")):
        return True
    try:
        return os.path.getmtime(meta) < os.path.getmtime(image_path)
    except OSError:
        return True
