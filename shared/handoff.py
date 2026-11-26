"""Hand a finished CastForge episode to forgefilms for post (pure, tested; no ffmpeg, no network).

CastForge stops at a rendered, voiced episode: `movies/<movie>/<episode>/episode.mp4`, and beside it one
folder per scene holding `shot.mp4` (the picture) and `shot.wav` (that scene's finished sound). forgefilms
starts at a shot list and does the post: colour, crossfades, loudness to -16 LUFS, captions, and whatever
ambience or effects a scene still wants. The two were written years apart and share no code, so this is
the contract between them - the only file that knows both shapes.

    python castforge.py post movies/santa_is_a_lie/act1

writes three files forgefilms already understands (`assemble.py SHOTS PICKS OUT`) plus the captions:

    shots.json     title, places, cast, and one shot per scene with its length and its lines
    picks.json     which file is the picture and which is the sound, per shot
    captions.vtt   the real line times, shifted by the crossfades, which a premixed bed cannot give back

Two rules this encodes, because getting either wrong is silent and ruins a cut:

  * A scene's length comes from its own `shot.timeline.json`, never from the episode timeline. The episode
    timeline's scene boundaries are where scenes sit in the final cut; the shot files are the untrimmed
    renders, and a shot list that lies about length cuts frames off the end of every scene.
  * CastForge's `shot.wav` is already mixed and already in time with the picture. It goes in as the
    ambience bed, with no voice layer and no offset, so nothing re-times it. forgefilms' ducking only
    works on a voice it placed itself; asking it to duck a finished mix would pump the whole scene.
"""
import json
import os

FADE = 0.5                   # forgefilms crossfades shots by this much; it must match assemble.py
SCENE_DIR = "{n:02d}_{id}"   # how castforge names a scene folder under <episode>/scenes/


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def scene_folder(episode, n, scene_id):
    """Where scene number `n` (1-based) of this episode was rendered."""
    return os.path.join(episode, "scenes", SCENE_DIR.format(n=n, id=scene_id))


def order(timeline):
    """The scene ids in the order they are cut, from `episode.timeline.json`."""
    return [str(s["id"]) for s in timeline.get("scenes", [])]


def shots(episode, timeline, scene, read=_read, exists=os.path.exists):
    """One forgefilms shot per CastForge scene: id, length, lines, and where its files are.

    `read` and `exists` are passed in so this can be tested without a rendered episode to hand."""
    want = {s.get("id"): s for s in scene.get("scenes", [])}
    out = []
    for n, sid in enumerate(order(timeline), start=1):
        folder = scene_folder(episode, n, sid)
        shot_timeline = os.path.join(folder, "shot.timeline.json")
        row = {"id": sid, "folder": folder,
               "video": os.path.join(folder, "shot.mp4"),
               "sound": os.path.join(folder, "shot.wav"),
               "seconds": None, "lines": [], "ambience": (want.get(sid) or {}).get("ambience")}
        if exists(shot_timeline):
            got = read(shot_timeline)
            row["seconds"] = float(got.get("duration") or 0.0)
            row["lines"] = [{"start": float(ln["start"]), "end": float(ln["end"]),
                             "who": ln.get("who"), "text": ln.get("text") or ""}
                            for ln in got.get("lines", []) if ln.get("text")]
        out.append(row)
    return out


def starts(rows):
    """When each shot begins in the finished cut. Every crossfade overlaps two shots, so the cut is
    FADE shorter per join - a caption written against raw lengths drifts half a second per scene."""
    at, out = 0.0, []
    for row in rows:
        out.append(at)
        at += (row["seconds"] or 0.0) - FADE
    return out


def shot_list(title, rows, cast=None, places=None):
    """The `shots.json` forgefilms reads. Shots with no rendered length are left out, not guessed at."""
    ready = [r for r in rows if r["seconds"]]
    return {"title": title,
            "from": "castforge",
            "note": "3D render, already voiced. Post only: no image-to-video, and the sound is final.",
            "cast": {who: {"name": who, "voice": {"engine": "kokoro", "voice_id": it.get("voice")}}
                     for who, it in (cast or {}).items()},
            "places": {r["id"]: {"ambience": r["ambience"]} for r in ready if r["ambience"]},
            "shots": [{"id": r["id"], "seconds": round(r["seconds"], 3), "place": r["id"],
                       "still": None, "motion": None,
                       "lines": r["lines"]} for r in ready]}


def picks(rows):
    """The `picks.json` forgefilms reads: the picture and the sound for each shot.

    The scene's finished audio goes in as `bed` with no offset. There is deliberately no `voice` entry:
    the voices are already inside that file, in time with the picture, and a second voice layer would
    duck the scene against itself."""
    return {r["id"]: {"video": r["video"], "bed": r["sound"], "bed_offset": 0.0}
            for r in rows if r["seconds"]}


def captions(rows):
    """A WEBVTT of the real line times, shifted into the finished cut. Lines are text, not timing:
    `shot.wav` is one premixed file, so this is the only place the per-line times survive."""
    def stamp(x):
        return f"{int(x // 3600):02d}:{int(x % 3600 // 60):02d}:{x % 60:06.3f}"
    ready = [r for r in rows if r["seconds"]]
    lines, k = ["WEBVTT", ""], 0
    for row, at in zip(ready, starts(ready)):
        for ln in row["lines"]:
            k += 1
            lines += [str(k), f"{stamp(at + ln['start'])} --> {stamp(at + ln['end'])}", ln["text"], ""]
    return "\n".join(lines)


def check(episode, rows, exists=os.path.exists):
    """Plain-language reasons this episode is not ready for post; empty when it is."""
    out = []
    if not rows:
        out.append(f"{episode} has no scenes - render it first: python castforge.py episode {episode}")
    for row in rows:
        if not row["seconds"]:
            out.append(f"scene {row['id']} has not been rendered - {row['folder']} has no shot.timeline.json")
        elif not exists(row["video"]):
            out.append(f"scene {row['id']} has a length but no picture at {row['video']}")
        elif not exists(row["sound"]):
            out.append(f"scene {row['id']} has no sound at {row['sound']} - it will be cut silent")
    return out


def plan(episode, read=_read, exists=os.path.exists):
    """Everything forgefilms needs for this episode, worked out but not yet written anywhere.

    Returns {title, rows, shots, picks, captions, problems}. A caller writes it; this stays pure."""
    episode = os.path.abspath(episode)
    title = f"{os.path.basename(os.path.dirname(episode))}_{os.path.basename(episode)}"
    timeline_path = os.path.join(episode, "episode.timeline.json")
    scene_path = os.path.join(episode, "scene.json")
    if not exists(timeline_path) or not exists(scene_path):
        return {"title": title, "rows": [], "shots": None, "picks": None, "captions": None,
                "problems": [f"{episode} is not a finished episode - "
                             "it needs scene.json and episode.timeline.json"]}
    timeline, scene = read(timeline_path), read(scene_path)
    rows = shots(episode, timeline, scene, read=read, exists=exists)
    return {"title": title, "rows": rows,
            "shots": shot_list(title, rows, cast=scene.get("cast")),
            "picks": picks(rows), "captions": captions(rows),
            "problems": check(episode, rows, exists=exists)}


def write(episode, into=None):
    """Write the plan into forgefilms' own `shots/` folder and say what to run. Returns (paths, problems)."""
    from shared import suite
    into = into or os.path.join(suite.TOOLS["forgefilms"]["folder"], "shots")
    got = plan(episode)
    if got["shots"] is None:
        return {}, got["problems"]
    os.makedirs(into, exist_ok=True)
    paths = {"shots": os.path.join(into, f"{got['title']}.json"),
             "picks": os.path.join(into, f"{got['title']}.picks.json"),
             "captions": os.path.join(into, f"{got['title']}.vtt")}
    for key in ("shots", "picks"):
        with open(paths[key], "w", encoding="utf-8") as f:
            json.dump(got[key], f, indent=1)
    with open(paths["captions"], "w", encoding="utf-8") as f:
        f.write(got["captions"])
    return paths, got["problems"]
