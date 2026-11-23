import json
import shutil
import struct
import subprocess

import pytest

from core import config, media

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is not installed")


def probe(path, entries):
    out = subprocess.run([config.FFPROBE, "-v", "error", "-show_entries", entries, "-of", "json", path],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def top_level_atoms(path):
    atoms, pos = [], 0
    with open(path, "rb") as f:
        data = f.read()
    while pos + 8 <= len(data):
        size, name = struct.unpack(">I4s", data[pos:pos + 8])
        atoms.append(name.decode("latin-1"))
        pos += size if size else len(data)
    return atoms


def test_video_args_tag_bt709():
    args = media.video_args()
    for flag in ("-colorspace", "-color_primaries", "-color_trc"):
        assert args[args.index(flag) + 1] == "bt709"
    assert args[args.index("-pix_fmt") + 1] == "yuv420p"
    assert media.video_args(codec="hevc")[media.video_args(codec="hevc").index("-pix_fmt") + 1] == "yuv420p10le"


def test_gain_filter_leaves_silence_alone_and_lifts_quiet_audio():
    assert media.gain_filter(float("-inf")) == "aresample=48000"
    assert media.gain_filter(-20.0, target=-16.0).startswith("volume=4.00dB,alimiter=")
    assert "level=0" in media.gain_filter(-20.0)          # the limiter must not re-level the mix


@needs_ffmpeg
@pytest.mark.parametrize("colour, channel", [("red", 0), ("lime", 1)])
def test_encoded_colours_survive_the_round_trip(tmp_path, colour, channel):
    src = tmp_path / "frame.png"
    subprocess.run([config.FFMPEG, "-v", "error", "-f", "lavfi", "-i", f"color=c={colour}:s=64x64:d=0.1",
                    "-frames:v", "1", str(src)], check=True)
    out = tmp_path / "clip.mp4"
    subprocess.run([config.FFMPEG, "-v", "error", "-y", "-loop", "1", "-t", "0.5", "-framerate", "24", "-i", str(src),
                    "-vf", media.to_bt709(), *media.video_args(fast=True), *media.CONTAINER_ARGS, str(out)],
                   check=True)
    stream = probe(str(out), "stream=color_space,color_primaries,color_transfer")["streams"][0]
    assert stream == {"color_space": "bt709", "color_primaries": "bt709", "color_transfer": "bt709"}
    assert top_level_atoms(str(out)).index("moov") < top_level_atoms(str(out)).index("mdat")
    rgb = subprocess.run([config.FFMPEG, "-v", "error", "-i", str(out), "-frames:v", "1", "-vf", "crop=8:8",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    pixel = rgb[:3]
    assert pixel[channel] > 240
    assert all(v < 14 for i, v in enumerate(pixel) if i != channel)


@needs_ffmpeg
def test_gain_filter_reaches_the_loudness_target(tmp_path):
    quiet = tmp_path / "quiet.wav"
    subprocess.run([config.FFMPEG, "-v", "error", "-f", "lavfi", "-i", "sine=f=440:d=6,volume=0.05",
                    "-ar", "48000", str(quiet)], check=True)
    measured, _ = media.measure_loudness(str(quiet))
    assert measured < -25
    out = tmp_path / "loud.wav"
    subprocess.run([config.FFMPEG, "-v", "error", "-y", "-i", str(quiet), "-af", media.gain_filter(measured, -16.0),
                    str(out)], check=True)
    level, peak = media.measure_loudness(str(out))
    assert abs(level - (-16.0)) < 0.5
    assert peak <= -1.0


@needs_ffmpeg
def test_process_voice_levels_a_line_and_keeps_its_length(tmp_path):
    line = tmp_path / "line.wav"
    subprocess.run([config.FFMPEG, "-v", "error", "-f", "lavfi", "-i",
                    "anoisesrc=d=2.0:c=pink:a=0.05,highpass=f=200,lowpass=f=5000", "-ar", "24000", str(line)],
                   check=True)
    out = media.process_voice(str(line), "clean")
    assert out.endswith(".clean.wav")
    assert abs(media.probe_duration(out) - media.probe_duration(str(line))) < 0.05
    level, _ = media.measure_loudness(out)
    assert abs(level - media.LINE_LOUDNESS) < 1.0
    assert media.process_voice(str(line), "none") == str(line)


def test_a_silent_failure_is_retried_but_a_real_error_is_not(monkeypatch):
    import subprocess as sp
    calls = []

    class R:
        def __init__(self, code, err):
            self.returncode, self.stderr, self.stdout = code, err, ""

    def fake(cmd, **kw):
        calls.append(cmd)
        return R(1, "") if len(calls) < 3 else R(0, "")

    monkeypatch.setattr(sp, "run", fake)
    monkeypatch.setattr(media.time, "sleep", lambda s: None)
    assert media.run(["ffprobe", "x"]).returncode == 0        # two silent failures, then it works
    assert len(calls) == 3

    calls.clear()
    monkeypatch.setattr(sp, "run", lambda cmd, **kw: (calls.append(cmd), R(1, "No such file or directory"))[1])
    with pytest.raises(RuntimeError, match="No such file"):
        media.run(["ffprobe", "y"])
    assert len(calls) == 1                                     # a real error is reported at once


def test_a_sound_gets_quieter_with_distance_but_never_disappears():
    assert media.distance_gain(0) == 1.0
    assert media.distance_gain(None) == 1.0                       # no place: no falloff
    near, far = media.distance_gain(2), media.distance_gain(8)
    assert 0.5 < near < 1.0 and near > far
    assert abs(far - 10 ** (-6 / 20)) < 1e-9                      # the full drop at the far end
    assert media.distance_gain(40) == far                         # and no further: it is still audible
