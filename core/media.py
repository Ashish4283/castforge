"""ffmpeg helpers for the render stage: delivery encoding, loudness, and the dialogue voice chain.

Nothing here imports Blender, so the scene kit, the episode job and the tests all use the same settings.

Delivery norms (checked by tests/test_media.py on real files):
  video  H.264 yuv420p, BT.709 matrix/primaries/transfer, TV range, index at the start (fast start)
  audio  AAC 320 kbps, 48 kHz stereo; masters to an integrated loudness target with a peak ceiling
"""
import json
import math
import os
import re
import subprocess
import time

from core import config

BT709_TAGS = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"]


def to_bt709(pix_fmt="yuv420p"):
    """RGB frames (Blender's PNGs) to BT.709 video-range YUV. Without this ffmpeg converts with the BT.601 matrix
    and copies the PNG's sRGB tag, and players shift the colours. setparams tags the frames themselves: ffmpeg 9
    takes the stream's colour tags from the frames and ignores -color_primaries/-color_trc."""
    return (f"scale=out_color_matrix=bt709:out_range=tv,format={pix_fmt},"
            "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv")


def video_args(fast=False, codec="h264", crf=None):
    """Encoder settings: x264 (default) or 10-bit HEVC; fast=True for blocking/draft previews."""
    if codec == "hevc":
        return ["-c:v", "libx265", "-crf", str(crf or (24 if fast else 20)), "-preset", "fast" if fast else "medium",
                "-pix_fmt", "yuv420p10le", "-tag:v", "hvc1", *BT709_TAGS]
    return ["-c:v", "libx264", "-crf", str(crf or (20 if fast else 17)), "-preset", "veryfast" if fast else "slow",
            "-pix_fmt", "yuv420p", *BT709_TAGS]


AUDIO_ARGS = ["-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-ac", "2"]
CONTAINER_ARGS = ["-movflags", "+faststart"]


def run(cmd, tries=3, **kw):
    """Run ffmpeg/ffprobe; on failure raise with the tool's own last lines (plain enough to read).

    A failure with nothing to say is a transient one (a file another program has not finished releasing,
    a scanner holding it open): those are retried briefly, real errors are raised at once."""
    for attempt in range(1, tries + 1):
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
        if r.returncode == 0:
            return r
        tail = "\n".join((r.stderr or r.stdout).strip().splitlines()[-6:])
        if tail.strip() or attempt == tries:
            raise RuntimeError(f"{os.path.basename(cmd[0])} failed:\n{tail}")
        time.sleep(0.4 * attempt)
    raise RuntimeError(f"{os.path.basename(cmd[0])} failed")


def probe_duration(path):
    r = run([config.FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "json", path])
    return float(json.loads(r.stdout)["format"]["duration"])


# --- loudness ---------------------------------------------------------------------------------------
def measure_loudness(path, pre_filter=""):
    """Integrated loudness (LUFS) and true peak (dBTP) of a file, after an optional filter chain.
    Silence reports -inf loudness."""
    af = (pre_filter + "," if pre_filter else "") + "loudnorm=print_format=json"
    r = run([config.FFMPEG, "-hide_banner", "-nostats", "-i", path, "-af", af, "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    if not m:
        raise RuntimeError(f"could not measure the loudness of {path}")
    stats = json.loads(m.group(0))
    return float(stats["input_i"]), float(stats["input_tp"])


def gain_filter(measured_i, target=-16.0, peak=-1.5):
    """Constant gain to the loudness target, then a peak limiter half a dB under the ceiling (a constant gain
    keeps the mix's dynamics; the limiter only catches the few peaks the gain pushes too high). Silence is left
    as it is."""
    limit = 10 ** ((peak - 0.5) / 20)
    if not math.isfinite(measured_i) or measured_i < -70:
        return "aresample=48000"
    return (f"volume={target - measured_i:.2f}dB,"
            f"alimiter=limit={limit:.4f}:attack=5:release=50:level=0:latency=1,aresample=48000")


# --- dialogue ---------------------------------------------------------------------------------------
# Effects for spoken lines ("fx" on a say/think/narrate step, or "voice_fx" on a cast member). None of them
# changes timing, so lip-sync computed from the original recording still matches.
VOICE_FX = {
    "none": "",
    "clean": ("highpass=f=75,equalizer=f=250:t=q:w=1.0:g=-2,equalizer=f=3800:t=q:w=1.2:g=2.5,deesser=i=0.3,"
              "acompressor=threshold=-22dB:ratio=2.5:attack=8:release=120:makeup=2"),
    "radio": "highpass=f=280,lowpass=f=4200,acompressor=threshold=-20dB:ratio=3:attack=5:release=80,volume=1.3",
    "phone": ("highpass=f=320,lowpass=f=3400,acompressor=threshold=-24dB:ratio=4:attack=5:release=60,"
              "asoftclip=type=tanh:threshold=0.8"),
    "megaphone": ("highpass=f=550,lowpass=f=4500,equalizer=f=1800:t=q:w=1:g=6,"
                  "asoftclip=type=hard:threshold=0.5,volume=0.8"),
    "echo": "aecho=0.8:0.7:90|180|320:0.35|0.22|0.12",
    "robot": ("afftfilt=real='hypot(re,im)*sin(0)':imag='hypot(re,im)*cos(0)':win_size=512:overlap=0.75,"
              "highpass=f=90"),
}
LINE_LOUDNESS = -20.0        # every line is levelled to this, so performers and TTS voices sit together


def process_voice(src, fx="clean"):
    """The line as it will be heard: src through the fx chain, levelled to LINE_LOUDNESS, 48 kHz.
    Cached next to src (<src>.<fx>.wav) and rebuilt when src is newer."""
    if fx == "none" or fx not in VOICE_FX:
        return src
    out = f"{src}.{fx}.wav"
    if os.path.exists(out) and os.path.getmtime(out) >= os.path.getmtime(src):
        return out
    chain = VOICE_FX[fx]
    measured, _ = measure_loudness(src, chain)
    run([config.FFMPEG, "-v", "error", "-y", "-i", src,
         "-af", f"{chain},{gain_filter(measured, LINE_LOUDNESS, -3.0)}", "-c:a", "pcm_s16le", out])
    return out


def distance_gain(metres, drop_db=6.0, reach=8.0):
    """How loud a sound is when its source is `metres` from the camera (1.0 at the camera).

    Film sound is not physics: a sound `reach` metres away or further is `drop_db` quieter, and nothing
    fades to silence, so a door at the back of the room is still heard. One place for footsteps, effects
    and anything else placed in the room."""
    if metres is None:
        return 1.0
    far = min(max(float(metres), 0.0) / max(reach, 0.001), 1.0)
    return 10 ** (-drop_db * far / 20)
