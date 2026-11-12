"""Publish kit: turn a finished episode into a platform-ready package, and say plainly what would fail.

    python castforge.py publish FOLDER [--platform youtube]

Writes FOLDER/publish/: the video (sound re-mastered to the platform's loudness if needed; the picture is
never re-encoded), thumbnail.jpg, chapters.txt, description.txt, the subtitles, and report.txt with every
check. Chapter rules (YouTube): the list starts at 0:00, every chapter is at least 10 s, and there are at
least 3; shorter ones (the title card) are folded into their neighbour."""
import json
import os
import re
import shutil

from core import config, media

PLATFORMS = {
    "youtube": {"loudness": -14.0, "true_peak": -1.0, "tolerance": 1.0, "min_chapter": 10.0, "min_chapters": 3,
                "thumbnail": (1280, 720), "video": {"h264"}, "audio": {"aac"}, "pix_fmt": "yuv420p",
                "max_height": 2160},
}


def fold_chapters(chapters, min_len=10.0):
    """[(start, end, name)] with every chapter at least min_len long: a short chapter is folded into the next
    one (a short last chapter into the previous). The first chapter always starts at 0.0."""
    folded = []
    for start, end, name in chapters:
        if folded and folded[-1][1] - folded[-1][0] < min_len:
            folded[-1] = [folded[-1][0], end, name]          # a short chapter (the title card) gives its
        else:                                                # place to the next one
            folded.append([start, end, name])
    if len(folded) > 1 and folded[-1][1] - folded[-1][0] < min_len:
        folded[-2][1] = folded[-1][1]                        # a short tail (credits) joins the previous
        folded.pop()
    if folded:
        folded[0][0] = 0.0
    return [tuple(ch) for ch in folded]


def chapter_lines(chapters):
    from core.finish import chapter_stamp
    return "".join(f"{chapter_stamp(a)} {name}\n" for a, _, name in chapters)


def probe(path):
    """The streams that matter for delivery: codec, pixel format, size, fps, duration, audio codec and rate."""
    r = media.run([config.FFPROBE, "-v", "error", "-show_streams", "-show_format", "-of", "json", path])
    info = json.loads(r.stdout)
    out = {"duration": float(info["format"]["duration"])}
    for st in info["streams"]:
        if st["codec_type"] == "video" and "video" not in out:
            num, den = (st.get("avg_frame_rate") or "0/1").split("/")
            out["video"] = {"codec": st["codec_name"], "pix_fmt": st.get("pix_fmt"),
                            "width": st["width"], "height": st["height"],
                            "fps": (float(num) / float(den)) if float(den) else 0.0}
        if st["codec_type"] == "audio" and "audio" not in out:
            out["audio"] = {"codec": st["codec_name"], "rate": int(st.get("sample_rate", 0))}
    return out


def srt_end(path):
    """The last subtitle's end time in seconds (0.0 for no cues)."""
    stamps = re.findall(r"--> (\d+):(\d\d):(\d\d)[,.](\d\d\d)", open(path, encoding="utf-8").read())
    if not stamps:
        return 0.0
    h, m, s, ms = stamps[-1]
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def check_episode(folder, platform="youtube"):
    """[(level, message)] for the finished episode: level is "ok", "note" or "fix"."""
    rules = PLATFORMS[platform]
    out = []
    video = os.path.join(folder, "episode.mp4")
    if not os.path.exists(video):
        return [("fix", "no episode.mp4 yet: render and finish the episode first")]
    info = probe(video)
    v, a = info.get("video"), info.get("audio")
    if not v or not a:
        return [("fix", "episode.mp4 is missing a video or audio stream: finish the episode again")]
    out.append(("ok" if v["codec"] in rules["video"] and v["pix_fmt"] == rules["pix_fmt"] else "fix",
                f"picture: {v['codec']} {v['pix_fmt']} {v['width']}x{v['height']} {v['fps']:.3g} fps"))
    if v["height"] < 480:
        out.append(("note", f"the picture is {v['height']}p (a blocking/draft render): render at standard or "
                            "final quality before publishing for real"))
    if a["codec"] not in rules["audio"]:
        out.append(("fix", f"sound: {a['codec']} (needs {', '.join(sorted(rules['audio']))})"))
    elif a["rate"] not in (44100, 48000):
        out.append(("note", f"sound: {a['codec']} {a['rate']} Hz (unusual rate; the publish package "
                            "resamples to 48 kHz)"))
    else:
        out.append(("ok", f"sound: {a['codec']} {a['rate']} Hz"))
    loud, peak = media.measure_loudness(video)
    good = abs(loud - rules["loudness"]) <= rules["tolerance"] and peak <= rules["true_peak"] + 0.2
    out.append(("ok" if good else "note",
                f"loudness: {loud:.1f} LUFS, peak {peak:.1f} dBTP (platform target {rules['loudness']:.0f} LUFS; "
                + ("fine)" if good else "the publish package re-masters the sound)")))
    srt = os.path.join(folder, "episode.srt")
    if os.path.exists(srt):
        last = srt_end(srt)
        out.append(("ok" if last <= info["duration"] + 0.5 else "fix",
                    f"subtitles: last cue ends {last:.1f} s into a {info['duration']:.1f} s film"))
    else:
        out.append(("note", "no episode.srt (finish the episode to get subtitles)"))
    chapters = read_chapters(folder)
    if not chapters:
        out.append(("note", "no chapters (finish the episode to get them)"))
    else:
        folded = fold_chapters(chapters, rules["min_chapter"])
        short = [name for a, b, name in folded if b - a < rules["min_chapter"]]
        if len(folded) < rules["min_chapters"]:
            out.append(("note", f"only {len(folded)} chapters at least {rules['min_chapter']:.0f} s long: "
                                f"{platform} needs {rules['min_chapters']}, so the package leaves chapters out"))
        elif short:
            out.append(("fix", f"chapters shorter than {rules['min_chapter']:.0f} s: {', '.join(short)}"))
        else:
            out.append(("ok", f"chapters: {len(folded)}, all at least {rules['min_chapter']:.0f} s, starting at 0:00"))
    return out


def read_chapters(folder):
    """[(start, end, name)] from episode_chapters.txt (end = next start; the film's end for the last)."""
    path = os.path.join(folder, "episode_chapters.txt")
    if not os.path.exists(path):
        return []
    rows = []
    for line in open(path, encoding="utf-8").read().splitlines():
        m = re.match(r"(?:(\d+):)?(\d+):(\d\d) (.+)", line.strip())
        if m:
            h, mnt, sec, name = m.groups()
            rows.append([int(h or 0) * 3600 + int(mnt) * 60 + int(sec), None, name])
    try:
        total = probe(os.path.join(folder, "episode.mp4"))["duration"]
    except Exception:
        total = rows[-1][0] + 60 if rows else 0
    for i, row in enumerate(rows):
        row[1] = rows[i + 1][0] if i + 1 < len(rows) else total
    return [tuple(r) for r in rows]


def thumbnail(folder, size, out):
    """1280x720 JPEG from the poster (or a frame of the film), scaled to cover and centre-cropped."""
    from PIL import Image
    src = os.path.join(folder, "episode_poster.jpg")
    if not os.path.exists(src):
        video = os.path.join(folder, "episode.mp4")
        at = probe(video)["duration"] * 0.4
        src = out + ".frame.jpg"
        media.run([config.FFMPEG, "-y", "-ss", f"{at:.2f}", "-i", video, "-frames:v", "1", "-q:v", "2", src],
                  check=True)
    img = Image.open(src).convert("RGB")
    scale = max(size[0] / img.width, size[1] / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left, top = (img.width - size[0]) // 2, (img.height - size[1]) // 2
    img.crop((left, top, left + size[0], top + size[1])).save(out, quality=92)
    if src.endswith(".frame.jpg"):
        os.remove(src)


def package(folder, platform="youtube", log=print):
    """Write FOLDER/publish/ for the platform. Returns the number of problems that still need fixing."""
    rules = PLATFORMS[platform]
    checks = check_episode(folder, platform)
    out_dir = os.path.join(folder, "publish")
    os.makedirs(out_dir, exist_ok=True)
    video = os.path.join(folder, "episode.mp4")
    problems = [m for level, m in checks if level == "fix"]
    if not os.path.exists(video):
        log("FIX  " + problems[0])
        return 1

    loud, peak = media.measure_loudness(video)
    out_video = os.path.join(out_dir, f"episode_{platform}.mp4")
    rate = probe(video).get("audio", {}).get("rate", 48000)
    if abs(loud - rules["loudness"]) <= rules["tolerance"] and peak <= rules["true_peak"] + 0.2 \
            and rate in (44100, 48000):
        shutil.copyfile(video, out_video)
        log(f"video: sound already at {loud:.1f} LUFS, copied as it is")
    else:
        # only the sound is re-encoded; the picture is copied bit for bit
        media.run([config.FFMPEG, "-y", "-i", video, "-map", "0", "-c:v", "copy", "-c:s", "copy",
                   "-af", media.gain_filter(loud, rules["loudness"], rules["true_peak"]),
                   "-ar", "48000", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out_video],
                  check=True)
        log(f"video: sound re-mastered {loud:.1f} -> {rules['loudness']:.0f} LUFS (picture untouched)")

    thumbnail(folder, rules["thumbnail"], os.path.join(out_dir, "thumbnail.jpg"))
    log(f"thumbnail: {rules['thumbnail'][0]}x{rules['thumbnail'][1]} thumbnail.jpg")

    chapters = fold_chapters(read_chapters(folder), rules["min_chapter"])
    description = []
    scene = json.load(open(os.path.join(folder, "scene.json"), encoding="utf-8")) if \
        os.path.exists(os.path.join(folder, "scene.json")) else {}
    title = scene.get("title")
    title_text = title.get("text") if isinstance(title, dict) else (title or "")
    if title_text:
        description.append(title_text + "\n")
    if len(chapters) >= rules["min_chapters"]:
        open(os.path.join(out_dir, "chapters.txt"), "w", encoding="utf-8").write(chapter_lines(chapters))
        description.append("Chapters:\n" + chapter_lines(chapters))
        log(f"chapters: {len(chapters)} (all at least {rules['min_chapter']:.0f} s)")
    else:
        for stale in (os.path.join(out_dir, "chapters.txt"),):
            if os.path.exists(stale):
                os.remove(stale)
        log(f"chapters: left out ({platform} needs {rules['min_chapters']} of at least "
            f"{rules['min_chapter']:.0f} s; this film has {len(chapters)})")
    open(os.path.join(out_dir, "description.txt"), "w", encoding="utf-8").write("\n".join(description) or title_text)
    for sub in ("episode.srt", "episode.vtt"):
        if os.path.exists(os.path.join(folder, sub)):
            shutil.copyfile(os.path.join(folder, sub), os.path.join(out_dir, sub))

    report = [("FIX " if level == "fix" else "ok  " if level == "ok" else "note") + "  " + message
              for level, message in checks]
    open(os.path.join(out_dir, "report.txt"), "w", encoding="utf-8").write("\n".join(report) + "\n")
    for line in report:
        log(line)
    log(f"publish package: {out_dir}" + ("" if not problems else f"  ({len(problems)} to fix)"))
    return len(problems)
