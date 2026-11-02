"""Subtitles from the spoken lines of an episode: SRT (players, YouTube) and WebVTT (the browser).

A line is {"start": s, "end": s, "text": "...", "kind": "say" | "think" | "narrate"}, times in seconds of the
finished episode. Thoughts and narration are set in italics. Long lines are wrapped at 42 characters, two rows
per cue; a line that needs more rows is split into consecutive cues, its time shared by length.
"""
import textwrap

WIDTH, ROWS, MIN_SECONDS, GAP = 42, 2, 0.8, 0.04


def stamp(t, sep):
    ms = int(round(max(t, 0.0) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def cues(lines):
    """Timed cues (start, end, rows, italic), in order, never overlapping and on screen long enough to read."""
    out = []
    for line in sorted((l for l in lines if (l.get("text") or "").strip()), key=lambda l: l["start"]):
        rows = textwrap.wrap(" ".join(line["text"].split()), WIDTH)
        groups = [rows[i:i + ROWS] for i in range(0, len(rows), ROWS)]
        total = sum(len(" ".join(g)) for g in groups)
        t = line["start"]
        for g in groups:
            share = (line["end"] - line["start"]) * len(" ".join(g)) / total
            out.append([t, t + share, g, line.get("kind") in ("think", "narrate")])
            t += share
    for i, c in enumerate(out):
        c[1] = max(c[1], c[0] + MIN_SECONDS)
        if i + 1 < len(out):
            c[1] = min(c[1], out[i + 1][0] - GAP)
    return [tuple(c) for c in out if c[1] > c[0]]


def _text(rows, italic):
    body = "\n".join(rows)
    return f"<i>{body}</i>" if italic else body


def to_srt(lines):
    return "".join(f"{n}\n{stamp(a, ',')} --> {stamp(b, ',')}\n{_text(rows, it)}\n\n"
                   for n, (a, b, rows, it) in enumerate(cues(lines), 1))


def to_vtt(lines):
    return "WEBVTT\n\n" + "".join(f"{stamp(a, '.')} --> {stamp(b, '.')}\n{_text(rows, it)}\n\n"
                                  for a, b, rows, it in cues(lines))
