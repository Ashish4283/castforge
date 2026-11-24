"""Which preview kit a design needs, and where it lives.

A kit (see `blender/preview_kit.py`) is the plain body plus every shape the sliders can morph it into, so
the designer can show a face changing as it is dragged instead of asking someone to agree to a four-minute
build sight unseen. The sliders themselves cost nothing to preview - they are applied in the browser - so a
kit only has to be made again when the body UNDERNEATH them changes: a different sex, a different build, or
enough of an age gap to matter. Age is banded for that reason: a kit per year would be 70 kits that look
the same.

Pure Python: the app asks `key_for` what it needs, `folder_for` where it goes, and `is_ready` whether it is
already there.
"""
import json
import os

AGE_BAND = 5          # years; a 31-year-old and a 29-year-old share a body
HEIGHT_BAND = 5       # centimetres; height is a real shape change in MakeHuman, not a scale, so it is here
GENDERS = ("male", "female")
BUILDS = ("slim", "average", "athletic", "heavy", "muscular")
FILES = ("kit.json", "kit.bin")
# Bumped whenever blender/preview_kit.py changes what it writes. Kits are cached on disk for ever, so
# without this a fixed exporter keeps serving the bodies the broken one made.
VERSION = 9


def band_age(age):
    """An age rounded to the band its body belongs to, inside the range MakeHuman actually models."""
    try:
        years = float(age)
    except (TypeError, ValueError):
        years = 30.0
    years = min(max(years, 16.0), 90.0)
    return int(round(years / AGE_BAND) * AGE_BAND)


def band_height(height_cm):
    """A height rounded to its band, inside the stature MakeHuman can actually reach."""
    try:
        cm = float(height_cm)
    except (TypeError, ValueError):
        cm = 170.0
    cm = min(max(cm, 140.0), 210.0)
    return int(round(cm / HEIGHT_BAND) * HEIGHT_BAND)


def key_for(design):
    """The kit one design needs: "<sex>-<age band>-<build>-<height band>". Designs that differ only in their
    sliders, their colours or their clothes share a kit, because none of those change the body underneath."""
    d = design or {}
    gender = d.get("gender") if d.get("gender") in GENDERS else "female"
    build = d.get("build") if d.get("build") in BUILDS else "average"
    return f"{gender}-{band_age(d.get('age'))}-{build}-{band_height(d.get('height_cm'))}"


def parts(key):
    """A kit key read back as the arguments the exporter wants: (gender, age, build, height cm)."""
    bits = (key or "").split("-")
    if len(bits) != 4:
        raise ValueError(f"{key!r} is not a preview kit")
    gender, age, build, height = bits
    if gender not in GENDERS or build not in BUILDS:
        raise ValueError(f"{key!r} is not a preview kit")
    return gender, float(age), build, float(height)


def folder_for(root, key):
    parts(key)                      # refuse anything that is not a kit key: this becomes a path
    return os.path.join(root, "preview_kits", key)


def is_ready(root, key):
    """True when that kit is on disk, complete, and was made by the exporter as it stands now."""
    folder = folder_for(root, key)
    if not all(os.path.isfile(os.path.join(folder, name)) and os.path.getsize(os.path.join(folder, name))
               for name in FILES):
        return False
    try:
        with open(os.path.join(folder, "kit.json"), encoding="utf-8") as fh:
            return json.load(fh).get("version") == VERSION
    except (OSError, ValueError):
        return False
