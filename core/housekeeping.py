"""What an episode is holding on disk, and what of it is safe to throw away (pure, tested).

A rendered episode is mostly not film. Of act1's 553 MB, 5 MB per scene is the picture you watch and
the rest is working material: Blender's own backup files, the scene files it saves beside them, and the
3D preview the app's editor loads. None of that is precious - but "rebuildable" is not one thing, and
treating it as one is how somebody loses an afternoon:

  * **spare**  - nothing has to be done to get it back, because nothing ever reads it. Blender writes a
    `.blend1` beside every save whether anyone wants it or not.
  * **cheap**  - a button brings it back. The 3D preview is about twenty seconds a scene.
  * **dear**   - only a full re-render brings it back. The scene files are in this group, and a sweep
    that quietly took them would cost hours of GPU.

So `sweep` takes how far to go, and nothing in the `dear` group goes without being asked for by name.
The film, its sound, the timings, the scene it was written from and the captions are never touched.
"""
import os

# (group, what it is called, how to spot it, what brings it back)
SPARE, CHEAP, DEAR = "spare", "cheap", "dear"
KINDS = (
    (SPARE, "Blender backups", ("*.blend1", "*.blend2"),
     "nothing reads them: Blender writes one beside every save"),
    (CHEAP, "3D previews", ("preview.glb", "preview.json"),
     "Build 3D preview, about 20 seconds a scene"),
    (CHEAP, "check renders", ("check/*",),
     "the Check button"),
    (DEAR, "scene files", ("*.blend",),
     "a full re-render of the episode"),
    (DEAR, "built sets", ("set/*",),
     "building the set again"),
)
# Never swept, at any depth: the film, the sound, what made them and what reads them back.
KEEP = ("scene.json", "shot.mp4", "shot.wav", "shot.timeline.json", "shot.sha256", "episode.mp4",
        "episode.timeline.json", "episode.srt", "episode.vtt", "episode_poster.jpg",
        "episode_chapters.txt", "render.log", "storyboard.jpg")
HOW_FAR = (SPARE, CHEAP, DEAR)


def _matches(rel, pattern):
    """Does this episode-relative path match one of the patterns above?"""
    name = rel.replace("\\", "/")
    if pattern.endswith("/*"):
        folder = pattern[:-2]
        return f"/{folder}/" in f"/{name}" or name.startswith(f"{folder}/")
    if pattern.startswith("*"):
        return name.rsplit("/", 1)[-1].endswith(pattern[1:])
    return name.rsplit("/", 1)[-1] == pattern


def group_of(rel):
    """(group, what it is called, what brings it back) for one file, or None when it is not sweepable."""
    if rel.replace("\\", "/").rsplit("/", 1)[-1] in KEEP:
        return None
    for group, called, patterns, back in KINDS:
        if any(_matches(rel, p) for p in patterns):
            return group, called, back
    return None


def survey(files):
    """What is here, by kind. `files` is (episode-relative path, bytes) for everything in the episode.

    Returns {"total", "kinds": [...], "spare", "cheap", "dear"} - the three being what a sweep at each
    depth would free, each INCLUDING the ones above it, because that is how the buttons work."""
    seen, total = {}, 0
    for rel, size in files:
        total += size
        found = group_of(rel)
        if not found:
            continue
        group, called, back = found
        row = seen.setdefault(called, {"group": group, "name": called, "back": back,
                                       "bytes": 0, "files": 0})
        row["bytes"] += size
        row["files"] += 1
    kinds = sorted(seen.values(), key=lambda r: -r["bytes"])
    at = {g: sum(r["bytes"] for r in kinds if r["group"] == g) for g in HOW_FAR}
    return {"total": total, "kinds": kinds, "spare": at[SPARE],
            "cheap": at[SPARE] + at[CHEAP], "dear": at[SPARE] + at[CHEAP] + at[DEAR]}


def sweep(files, how_far=SPARE):
    """Which files a sweep of this depth takes, and how many bytes that frees.

    A depth takes everything cheaper than itself as well: asking for the expensive clear-out and being
    left with the backup files would be a strange thing to have happen."""
    if how_far not in HOW_FAR:
        raise ValueError(f"how far is one of {', '.join(HOW_FAR)}, not {how_far!r}")
    allowed = set(HOW_FAR[:HOW_FAR.index(how_far) + 1])
    taken, freed = [], 0
    for rel, size in files:
        found = group_of(rel)
        if found and found[0] in allowed:
            taken.append(rel)
            freed += size
    return taken, freed


def listing(folder, walk=os.walk, size=os.path.getsize):
    """(episode-relative path, bytes) for everything under an episode folder."""
    out = []
    for root, _dirs, names in walk(folder):
        for name in names:
            full = os.path.join(root, name)
            try:
                out.append((os.path.relpath(full, folder), size(full)))
            except OSError:
                pass                         # a file that went away while we looked is not our business
    return out


def in_words(count):
    """A byte count a person can read."""
    size = float(count)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit in ("B", "KB") else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"
