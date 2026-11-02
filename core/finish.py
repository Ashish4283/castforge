"""Finishing: rendered scenes -> the delivered episode, without touching Blender.

Titles and scrolling credits, transitions between scenes, a colour grade per scene, subtitles (a selectable track
or burnt in), chapters, a poster frame and loudness mastering. It reads each scene's shot.mp4 (picture),
shot.wav (the scene's float stereo mix) and shot.timeline.json (its lines and shots), so changing any of these
settings takes minutes instead of a new render.

Writes in the episode folder: episode.mp4, episode.srt, episode.vtt, episode_chapters.txt, episode_poster.jpg
and episode.timeline.json (where every scene starts, for the app).
"""
import json
import os

from core import config, media, subtitles

# colour grades, applied to one scene's frames (filters work on the decoded BT.709 picture)
GRADES = {
    "neutral": "",
    "warm": "colorbalance=rs=0.04:bs=-0.04:rm=0.03:bm=-0.03:rh=0.02:bh=-0.02,eq=saturation=1.06",
    "cool": "colorbalance=rs=-0.03:bs=0.05:rm=-0.02:bm=0.03,eq=saturation=0.97",
    "teal_orange": "colorbalance=rs=-0.06:gs=0.01:bs=0.07:rh=0.06:gh=0.01:bh=-0.07,eq=saturation=1.08:contrast=1.04",
    "night": "colorbalance=rs=-0.05:bs=0.08:rm=-0.04:bm=0.05,eq=brightness=-0.04:saturation=0.8:contrast=1.05",
    "noir": "hue=s=0,eq=contrast=1.25:brightness=-0.02",
    "vintage": "curves=preset=vintage,eq=saturation=0.85",
    "bleach": "eq=saturation=0.55:contrast=1.18",
    "dream": "gblur=sigma=1.2,eq=brightness=0.03:saturation=1.12:gamma=1.05",
}
# transition name -> ffmpeg xfade transition (cut joins without one)
TRANSITIONS = {"cut": None, "fade": "fadeblack", "fade_white": "fadewhite", "dissolve": "fade",
               "wipe_left": "wipeleft", "wipe_right": "wiperight", "slide_left": "slideleft",
               "slide_right": "slideright", "circle_open": "circleopen", "circle_close": "circleclose",
               "pixelize": "pixelize", "radial": "radial", "zoom_in": "zoomin"}
CARD_JOIN = ("fade", 0.6)          # how title and credits cards join the film


def grade_filter(grade="neutral", vignette=0.0, grain=0.0):
    parts = [GRADES.get(grade or "neutral", "")]
    if vignette:
        parts.append(f"vignette=angle={0.25 + 0.55 * min(max(vignette, 0.0), 1.0):.3f}")
    if grain:
        parts.append(f"noise=alls={int(round(25 * min(max(grain, 0.0), 1.0)))}:allf=t")
    return ",".join(p for p in parts if p)


def transition(scene, episode):
    """(kind, seconds) for the join into `scene`: its own setting, else the episode's, else a cut."""
    kind = scene.get("transition") or episode.get("transition") or "cut"
    if kind not in TRANSITIONS:
        kind = "cut"
    seconds = scene.get("transition_seconds") or episode.get("transition_seconds") or (
        1.0 if kind == "dissolve" else 0.6)
    return kind, (0.0 if kind == "cut" else float(seconds))


def layout(durations, joins):
    """Start of every segment in the finished film and its total length. joins[i] is the (kind, seconds) of
    the join before segment i+1; a transition overlaps the two segments by its length."""
    starts, t = [], 0.0
    for i, d in enumerate(durations):
        if i:
            t -= joins[i - 1][1]
        starts.append(t)
        t += d
    return starts, t


def episode_lines(timelines, starts):
    return [dict(ln, start=ln["start"] + s, end=ln["end"] + s)
            for tl, s in zip(timelines, starts) for ln in tl.get("lines", [])]


def poster_time(timelines, starts, total):
    """Middle of the first line seen in a medium or close shot; else a third of the way in."""
    for tl, s in zip(timelines, starts):
        shots = tl.get("shots", [])
        for ln in tl.get("lines", []):
            mid = (ln["start"] + ln["end"]) / 2
            showing = [sh for sh in shots if sh["time"] <= mid]
            if showing and showing[-1]["kind"] in ("medium", "close"):
                return s + mid
    return total / 3


def chapter_stamp(t):
    t = int(t)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


# --- cards -------------------------------------------------------------------------------------------------
def _font(size, bold=False):
    from PIL import ImageFont
    names = (["georgiab.ttf", "segoeuib.ttf", "arialbd.ttf"] if bold else ["georgia.ttf", "segoeui.ttf", "arial.ttf"])
    for n in names:
        for d in ("", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")):
            try:
                return ImageFont.truetype(os.path.join(d, n) if d else n, size)
            except OSError:
                pass
    return ImageFont.load_default(size=size)


def title_card(path, size, title, subtitle=""):
    from PIL import Image, ImageDraw
    w, h = size
    im = Image.new("RGB", size, (0, 0, 0))
    d = ImageDraw.Draw(im)
    big, small = _font(max(h // 9, 12), True), _font(max(h // 24, 10))
    d.text((w / 2, h * 0.46), title, font=big, fill=(240, 236, 228), anchor="ms")
    if subtitle:
        d.line([(w * 0.42, h * 0.52), (w * 0.58, h * 0.52)], fill=(150, 140, 125), width=max(h // 360, 1))
        d.text((w / 2, h * 0.585), subtitle, font=small, fill=(190, 184, 172), anchor="ms")
    im.save(path)


def credits_card(path, width, height, rows):
    """A tall picture of the credits (rows: (text, "head" | "line" | "gap")), scrolled over black."""
    from PIL import Image, ImageDraw
    head, line = _font(max(height // 20, 12), True), _font(max(height // 26, 10))
    step = max(height // 16, 14)
    tall = height + step * (len(rows) + 2) + height
    im = Image.new("RGB", (width, tall), (0, 0, 0))
    d = ImageDraw.Draw(im)
    y = height
    for text, kind in rows:
        if kind != "gap":
            d.text((width / 2, y), text, font=head if kind == "head" else line,
                   fill=(240, 236, 228) if kind == "head" else (200, 194, 182), anchor="ms")
        y += step
    im.save(path)
    return tall


def credit_rows(credits, cast_names):
    rows = []
    for ln in credits.get("lines", []):
        rows += [(ln, "line")]
    if credits.get("cast", True) and cast_names:
        rows += [("", "gap"), ("Cast", "head")] + [(n.replace("_", " ").title(), "line") for n in cast_names]
    rows += [("", "gap"), ("Made with CastForge", "line")]
    return rows


def _bed(name):
    """A library bed name or a file path -> a sound file (None if missing)."""
    if not name:
        return None
    if os.path.exists(name):
        return name
    try:
        lib = json.load(open(os.path.join(config.SFX_DIR, "library.json"), encoding="utf-8")).get("beds", {})
    except (OSError, ValueError):
        return None
    return os.path.join(config.SFX_DIR, lib[name][0]) if lib.get(name) else None


# --- the episode -------------------------------------------------------------------------------------------
def finish(folder, scenes, spec, quality="standard", log=print):
    """scenes: [{"dir", "id", "chapter", "transition", "transition_seconds", "grade", "vignette", "grain"}] in
    order, each dir holding shot.mp4, shot.wav and shot.timeline.json. spec: the episode's finishing settings."""
    if not scenes:
        raise ValueError("cannot finish an episode without rendered scenes")
    fast = quality in ("blocking", "draft")
    fps = None
    timelines, durations = [], []
    for sc in scenes:
        tl_path = os.path.join(sc["dir"], "shot.timeline.json")
        tl = json.load(open(tl_path, encoding="utf-8")) if os.path.exists(tl_path) else {"lines": [], "shots": []}
        timelines.append(tl)
        durations.append(media.probe_duration(os.path.join(sc["dir"], "shot.mp4")))
        fps = fps or tl.get("fps")
    fps = fps or 24
    size = _video_size(os.path.join(scenes[0]["dir"], "shot.mp4"))
    work = os.path.join(folder, "finish_tmp")
    os.makedirs(work, exist_ok=True)

    segments = []                                      # (kind, path, seconds, scene) in film order
    title = spec.get("title")
    if isinstance(title, str):
        title = {"text": title}
    if title and title.get("text"):
        card = os.path.join(work, "title.png")
        title_card(card, size, title["text"], title.get("subtitle", ""))
        segments.append(("card", card, float(title.get("seconds", 4.0)), {"music": title.get("music")}))
    for sc, d in zip(scenes, durations):
        segments.append(("shot", sc["dir"], d, sc))
    credits = spec.get("credits")
    if credits:
        credits = credits if isinstance(credits, dict) else {}
        cast_names = list(spec.get("cast", {}))
        rows = credit_rows(credits, cast_names)
        card = os.path.join(work, "credits.png")
        tall = credits_card(card, size[0], size[1], rows)
        seconds = float(credits.get("seconds", max(6.0, 0.9 * len(rows))))
        segments.append(("credits", card, seconds, {"tall": tall, "music": credits.get("music")}))

    joins = []
    for i in range(1, len(segments)):
        a, b = segments[i - 1], segments[i]
        joins.append(transition(b[3], spec) if a[0] == b[0] == "shot" else CARD_JOIN)
    starts, total = layout([s[2] for s in segments], joins)
    shot_starts = [st for st, s in zip(starts, segments) if s[0] == "shot"]
    master = spec.get("master", {})
    fade_in, fade_out = float(master.get("fade_in", 0.5)), float(master.get("fade_out", 1.0))
    log(f"finishing: {len(scenes)} scene(s), {total:.1f} s")

    # 1. the sound: every segment's audio joined like the picture, into one float mix
    mix = os.path.join(work, "episode_mix.wav")
    inputs, chains = [], []
    for n, (kind, path, seconds, extra) in enumerate(segments):
        if kind == "shot":
            inputs += ["-i", os.path.join(path, "shot.wav")]
            src = f"[{len(inputs) // 2 - 1}:a]"
        elif _bed(extra.get("music")):
            inputs += ["-i", _bed(extra["music"])]
            src = f"[{len(inputs) // 2 - 1}:a]"
        else:
            chains.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{seconds:.4f}[s{n}]")
            src = f"[s{n}]"
        fade = f",afade=t=out:st={max(seconds - 1.5, 0):.4f}:d=1.5" if kind != "shot" else ""
        chains.append(f"{src}aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
                      f"apad,atrim=0:{seconds:.4f},asetpts=N/SR/TB{fade}[a{n}]")
    acc = "[a0]"
    for n, (kind, sec) in enumerate(joins, 1):
        out = f"[am{n}]"
        chains.append(f"{acc}[a{n}]" + ("concat=n=2:v=0:a=1" if kind == "cut" else
                                        f"acrossfade=d={sec:.4f}:c1=tri:c2=tri") + out)
        acc = out
    edge = []
    if fade_in:
        edge.append(f"afade=t=in:st=0:d={fade_in:.3f}")
    if fade_out:
        edge.append(f"afade=t=out:st={max(total - fade_out, 0):.4f}:d={fade_out:.3f}")
    chains.append(f"{acc}{','.join(edge) or 'anull'}[aout]")
    media.run([config.FFMPEG, "-v", "error", "-y", *inputs, "-filter_complex", ";".join(chains),
               "-map", "[aout]", "-c:a", "pcm_f32le", mix])
    loudness, _ = media.measure_loudness(mix)
    target, peak = float(master.get("loudness", -16.0)), float(master.get("true_peak", -1.5))
    log(f"sound: {loudness:.1f} LUFS -> {target:.1f} LUFS")

    # 2. subtitles, chapters
    lines = episode_lines(timelines, shot_starts)
    srt, vtt = os.path.join(folder, "episode.srt"), os.path.join(folder, "episode.vtt")
    open(srt, "w", encoding="utf-8").write(subtitles.to_srt(lines))
    open(vtt, "w", encoding="utf-8").write(subtitles.to_vtt(lines))
    # chapters cover the whole film from 0:00 (players and YouTube expect that): titles, scenes, credits
    chapters, shot_n = [], 0
    for (kind, _, seconds, extra), st in zip(segments, starts):
        if kind == "card":
            name = title["text"]
        elif kind == "credits":
            name = "Credits"
        else:
            sc = scenes[shot_n]
            shot_n += 1
            name = sc.get("chapter") or sc["id"].replace("_", " ").title()
        chapters.append((st, st + seconds, name))
    meta = os.path.join(work, "chapters.txt")
    with open(meta, "w", encoding="utf-8") as f:
        f.write(";FFMETADATA1\n")
        for a, b, name in chapters:
            f.write(f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={int(a * 1000)}\nEND={int(b * 1000)}\ntitle={name}\n")
    open(os.path.join(folder, "episode_chapters.txt"), "w", encoding="utf-8").write(
        "".join(f"{chapter_stamp(a)} {name}\n" for a, _, name in chapters))

    # 3. the picture, then picture + mastered sound + subtitles + chapters in one encode
    w, h = size
    inputs, chains = [], []
    for n, (kind, path, seconds, extra) in enumerate(segments):
        if kind == "shot":
            inputs += ["-i", os.path.join(path, "shot.mp4")]
            look = grade_filter(extra.get("grade") or spec.get("grade"), extra.get("vignette", spec.get("vignette", 0)),
                                extra.get("grain", spec.get("grain", 0)))
            chains.append(f"[{_count(inputs) - 1}:v]trim=duration={seconds:.4f},setpts=PTS-STARTPTS,fps={fps},"
                          f"{look + ',' if look else ''}{media.to_bt709()},setsar=1,settb=AVTB[v{n}]")
        elif kind == "card":
            inputs += ["-loop", "1", "-framerate", str(fps), "-t", f"{seconds:.4f}", "-i", path]
            chains.append(f"[{_count(inputs) - 1}:v]scale={w}:{h},fps={fps},{media.to_bt709()},setsar=1,"
                          f"settb=AVTB[v{n}]")
        else:
            inputs += ["-loop", "1", "-framerate", str(fps), "-t", f"{seconds:.4f}", "-i", path]
            speed = (extra["tall"] - h) / seconds
            chains.append(f"color=c=black:s={w}x{h}:r={fps}:d={seconds:.4f}[bg{n}];"
                          f"[bg{n}][{_count(inputs) - 1}:v]overlay=x=0:y=-t*{speed:.3f}:shortest=1,"
                          f"{media.to_bt709()},setsar=1,settb=AVTB[v{n}]")
    seg_len = [s[2] for s in segments]
    acc, acc_len = "[v0]", seg_len[0]
    for n, (kind, sec) in enumerate(joins, 1):
        out = f"[vm{n}]"
        if kind == "cut":
            chains.append(f"{acc}[v{n}]concat=n=2:v=1:a=0{out}")
        else:
            chains.append(f"{acc}[v{n}]xfade=transition={TRANSITIONS[kind]}:duration={sec:.4f}:"
                          f"offset={acc_len - sec:.4f}{out}")
        acc, acc_len = out, acc_len + seg_len[n] - sec
    edge = []
    if fade_in:
        edge.append(f"fade=t=in:st=0:d={fade_in:.3f}")
    if fade_out:
        edge.append(f"fade=t=out:st={max(total - fade_out, 0):.4f}:d={fade_out:.3f}")
    burn = spec.get("subtitles", "soft") == "burn" and lines
    if burn:          # run from the episode folder, so the path needs no drive-letter escaping
        edge.append("subtitles=episode.srt:force_style='FontName=Segoe UI,FontSize=20,Outline=1.2,Shadow=0,"
                    "MarginV=28'")
    chains.append(f"{acc}{','.join(edge) or 'null'}[vout]")
    mix_in = _count(inputs)
    inputs += ["-i", mix]
    chains.append(f"[{mix_in}:a]{media.gain_filter(loudness, target, peak)}[aout]")
    maps = ["-map", "[vout]", "-map", "[aout]"]
    if spec.get("subtitles", "soft") == "soft" and lines:
        inputs += ["-i", srt]
        maps += ["-map", f"{_count(inputs) - 1}:s", "-c:s", "mov_text", "-metadata:s:s:0", "language=eng"]
    inputs += ["-f", "ffmetadata", "-i", meta]
    maps += ["-map_metadata", str(_count(inputs) - 1), "-map_chapters", str(_count(inputs) - 1)]
    out = os.path.join(folder, "episode.mp4")
    tmp = os.path.join(work, "episode.mp4")
    codec = master.get("codec", "h264")
    media.run([config.FFMPEG, "-v", "error", "-y", *inputs, "-filter_complex", ";".join(chains), *maps,
               *media.video_args(fast, codec), *media.AUDIO_ARGS, *media.CONTAINER_ARGS, tmp], cwd=folder)
    os.replace(tmp, out)

    # 4. poster and the episode's own timeline
    poster = spec.get("poster") or {}
    at = poster.get("time", poster_time(timelines, shot_starts, total))
    jpg = os.path.join(folder, "episode_poster.jpg")
    media.run([config.FFMPEG, "-v", "error", "-y", "-ss", f"{min(at, total - 0.1):.3f}", "-i", out, "-frames:v", "1",
               "-q:v", "2", jpg])
    if title and title.get("text"):
        _poster_title(jpg, title["text"])
    json.dump({"duration": total, "scenes": [{"id": sc["id"], "start": st, "end": st + d}
                                             for sc, st, d in zip(scenes, shot_starts, durations)]},
              open(os.path.join(folder, "episode.timeline.json"), "w", encoding="utf-8"), indent=1)
    for f in os.listdir(work):
        os.remove(os.path.join(work, f))
    os.rmdir(work)
    log("video", out)
    return out


def _count(inputs):
    return inputs.count("-i")


def _video_size(path):
    r = media.run([config.FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                   "-of", "json", path])
    s = json.loads(r.stdout)["streams"][0]
    return int(s["width"]), int(s["height"])


def _poster_title(jpg, text):
    from PIL import Image, ImageDraw
    im = Image.open(jpg).convert("RGB")
    w, h = im.size
    shade = Image.new("L", (1, h))
    for y in range(h):
        shade.putpixel((0, y), int(200 * max(0.0, (y / h - 0.55) / 0.45)))
    im.paste((0, 0, 0), (0, 0, w, h), shade.resize((w, h)))
    ImageDraw.Draw(im).text((w / 2, h * 0.9), text, font=_font(max(h // 10, 12), True), fill=(245, 240, 230),
                            anchor="ms")
    im.save(jpg, quality=92)
