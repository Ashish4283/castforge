import json
import shutil
import subprocess

import pytest

from core import config, finish, media

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is not installed")


def test_layout_overlaps_transitions():
    starts, total = finish.layout([2.0, 4.0, 3.0], [("dissolve", 1.0), ("cut", 0.0)])
    assert starts == [0.0, 1.0, 5.0]
    assert total == 8.0


def test_transition_prefers_the_scene_then_the_episode():
    assert finish.transition({}, {}) == ("cut", 0.0)
    assert finish.transition({}, {"transition": "dissolve"}) == ("dissolve", 1.0)
    assert finish.transition({"transition": "fade", "transition_seconds": 0.4}, {"transition": "dissolve"}) == \
        ("fade", 0.4)
    assert finish.transition({"transition": "explode"}, {}) == ("cut", 0.0)


def test_grade_filter_adds_vignette_and_grain():
    assert finish.grade_filter("neutral") == ""
    chain = finish.grade_filter("noir", vignette=0.5, grain=0.2)
    assert chain.startswith("hue=s=0") and "vignette=angle=0.525" in chain and "noise=alls=5" in chain


def test_poster_prefers_a_line_in_a_close_shot():
    tl = {"lines": [{"start": 1.0, "end": 3.0}], "shots": [{"time": 0.0, "kind": "wide"}, {"time": 1.5, "kind": "close"}]}
    assert finish.poster_time([tl], [10.0], 30.0) == 12.0
    assert finish.poster_time([{"lines": [], "shots": []}], [0.0], 30.0) == 10.0


def test_chapter_stamps():
    assert finish.chapter_stamp(0) == "0:00"
    assert finish.chapter_stamp(75.9) == "1:15"
    assert finish.chapter_stamp(3725) == "1:02:05"


def test_finish_rejects_an_episode_without_scenes(tmp_path):
    with pytest.raises(ValueError, match="without rendered scenes"):
        finish.finish(str(tmp_path), [], {}, log=lambda *a: None)


def make_shot(folder, seconds, freq, line):
    folder.mkdir(parents=True)
    subprocess.run([config.FFMPEG, "-v", "error", "-f", "lavfi", "-i", f"testsrc2=s=320x180:r=24:d={seconds}",
                    "-vf", media.to_bt709(), *media.video_args(fast=True), str(folder / "shot.mp4")], check=True)
    subprocess.run([config.FFMPEG, "-v", "error", "-f", "lavfi", "-i", f"sine=f={freq}:d={seconds},volume=0.1",
                    "-ac", "2", "-ar", "48000", "-c:a", "pcm_f32le", str(folder / "shot.wav")], check=True)
    (folder / "shot.timeline.json").write_text(json.dumps(
        {"version": 1, "fps": 24, "duration": seconds, "lines": [line],
         "shots": [{"time": 0.0, "kind": "close", "on": [line["who"]]}]}), encoding="utf-8")


@needs_ffmpeg
def test_finish_builds_a_deliverable_episode(tmp_path):
    make_shot(tmp_path / "scenes" / "01_cabin", 2.0, 330,
              {"start": 0.5, "end": 1.5, "who": "Arthur", "kind": "say", "text": "Forty winters."})
    make_shot(tmp_path / "scenes" / "02_street", 2.5, 440,
              {"start": 0.25, "end": 2.0, "who": "Noelle", "kind": "think", "text": "Santa is a lie."})
    scenes = [{"dir": str(tmp_path / "scenes" / "01_cabin"), "id": "cabin", "grade": "warm"},
              {"dir": str(tmp_path / "scenes" / "02_street"), "id": "street", "chapter": "Main Street",
               "transition": "dissolve"}]
    spec = {"title": {"text": "Santa is a Lie", "subtitle": "Act I", "seconds": 2.0},
            "credits": {"lines": ["Written by A. Jiwa"], "seconds": 3.0}, "cast": {"Arthur": {}, "Noelle": {}},
            "master": {"loudness": -16}, "vignette": 0.2}
    out = finish.finish(str(tmp_path), scenes, spec, quality="draft", log=lambda *a: None)

    expected = 2.0 + 2.0 + 2.5 + 3.0 - 0.6 - 1.0 - 0.6
    assert abs(media.probe_duration(out) - expected) < 0.1
    info = json.loads(subprocess.run([config.FFPROBE, "-v", "error", "-show_streams", "-show_chapters", "-of", "json",
                                      out], capture_output=True, text=True, check=True).stdout)
    kinds = {s["codec_type"]: s for s in info["streams"]}
    assert kinds["video"]["color_space"] == kinds["video"]["color_primaries"] == "bt709"
    assert kinds["audio"]["sample_rate"] == "48000" and kinds["audio"]["channels"] == 2
    assert kinds["subtitle"]["codec_name"] == "mov_text"
    starts = [round(float(c["start_time"]), 2) for c in info["chapters"]]
    assert starts == [0.0, 1.4, 2.4, 4.3]
    assert [c["tags"]["title"] for c in info["chapters"]] == ["Santa is a Lie", "Cabin", "Main Street", "Credits"]
    srt = (tmp_path / "episode.srt").read_text(encoding="utf-8")
    # the dissolve overlaps the scenes, so the first cue ends just before the second line starts (2.4 + 0.25)
    assert "00:00:01,900 --> 00:00:02,610\nForty winters." in srt
    assert "00:00:02,650 --> 00:00:04,400\n<i>Santa is a lie.</i>" in srt
    assert "<i>Santa is a lie.</i>" in srt
    assert (tmp_path / "episode_chapters.txt").read_text(encoding="utf-8") == \
        "0:00 Santa is a Lie\n0:01 Cabin\n0:02 Main Street\n0:04 Credits\n"
    assert (tmp_path / "episode_poster.jpg").stat().st_size > 1000
    level, _ = media.measure_loudness(out)
    assert abs(level - (-16.0)) < 0.5
    assert not (tmp_path / "finish_tmp").exists()


@needs_ffmpeg
def test_burnt_in_subtitles_and_plain_cuts(tmp_path):
    make_shot(tmp_path / "a", 1.5, 300, {"start": 0.2, "end": 1.2, "who": "A", "kind": "say", "text": "Hi."})
    make_shot(tmp_path / "b", 1.5, 500, {"start": 0.2, "end": 1.2, "who": "B", "kind": "say", "text": "Hello."})
    scenes = [{"dir": str(tmp_path / "a"), "id": "a"}, {"dir": str(tmp_path / "b"), "id": "b"}]
    out = finish.finish(str(tmp_path), scenes, {"subtitles": "burn", "master": {"fade_in": 0, "fade_out": 0}},
                        quality="draft", log=lambda *a: None)
    assert abs(media.probe_duration(out) - 3.0) < 0.1
    streams = json.loads(subprocess.run([config.FFPROBE, "-v", "error", "-show_streams", "-of", "json", out],
                                        capture_output=True, text=True, check=True).stdout)["streams"]
    types = [s["codec_type"] for s in streams]
    assert types[:2] == ["video", "audio"] and "subtitle" not in types      # burnt in, no text track
