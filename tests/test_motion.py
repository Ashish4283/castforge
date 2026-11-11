import json
import math

import pytest

from blender import motion
from core import config, schema
from tests.test_schema import scene


def test_mixamo_and_cmu_skeletons_are_recognised():
    mixamo = [f"mixamorig:{b}" for b in motion.SKELETONS["mixamo"].values()] + ["mixamorig:LeftHandIndex1"]
    kind, bones = motion.bone_map(mixamo)
    assert kind == "mixamo" and bones["upper_arm.L"] == "mixamorig:LeftArm" and bones["chest"] == "mixamorig:Spine2"
    kind, bones = motion.bone_map(list(motion.SKELETONS["cmu"].values()) + ["LowerBack", "LHipJoint"])
    assert kind == "cmu" and bones["chest"] == "Spine1" and set(bones) == set(motion.CONTROLS)
    with pytest.raises(ValueError, match="LeftUpLeg"):
        motion.bone_map([b for b in motion.SKELETONS["cmu"].values() if b != "LeftUpLeg"])


def test_headings_follow_the_castforge_convention():
    assert motion.facing_of([0.1, 0.0], [-0.1, 0.0]) == 0.0                 # left hip at +X: faces -Y
    assert math.isclose(motion.facing_of([0.0, 0.1], [0.0, -0.1]), math.pi / 2)   # turned left: faces +X
    assert math.isclose(motion.heading_of(1.0, 0.0), math.pi / 2) and motion.heading_of(0.0, -1.0) == 0.0
    assert motion.next_part("upper_arm.R") == "forearm.R" and motion.next_part("hand.L") is None


def test_windows_frames_and_blends():
    meta = {"seconds": 4.0, "fps": 120.0, "frames": [1, 481]}
    assert motion.window(meta, 1.0, 9.0) == (1.0, 4.0)
    assert motion.window(meta, 5.0) == (4.0, 4.0)
    assert motion.scene_frames(1.0, 3.0, 24, speed=2.0) == 24
    assert motion.clip_to_scene(121, meta, 0.5, 100, 24) == 112.0           # clip second 1.0 -> 0.5 s after start
    assert motion.fades(10, 40, 7) == [(10, 0.0), (17, 1.0), (33, 1.0), (40, 0.0)]
    assert motion.fades(10, 14, 7) == [(10, 0.0), (12, 1.0), (12, 1.0), (14, 0.0)]


def track(hips, facing, feet_l, feet_r, floor):
    return {"fps": 1, "hips": hips, "facing": facing, "feet": {"L": feet_l, "R": feet_r}, "floor": floor}


def test_ending_is_measured_in_the_body_frame_and_hip_heights():
    # facing +X (heading pi/2) at the start, two units forward and a quarter turn left; hip height 2
    meta = {"hip_height": 2.0, "track": track([[5, 5, 2], [7, 5, 2]], [math.pi / 2, math.pi],
                                              [[5, 5, 0, 0], [7, 5.2, 0, math.pi]],
                                              [[5, 5, 0, 0], [7, 4.8, 0, math.pi]], [0, 0])}
    move, turn, feet = motion.ending(meta, 0.0, 1.0)
    assert move[0] == pytest.approx(0.0, abs=1e-9) and move[1] == pytest.approx(-1.0)   # one hip height forward
    assert turn == pytest.approx(math.pi / 2)
    assert feet["L"][0] == pytest.approx(0.1) and feet["L"][2] == pytest.approx(math.pi / 2)
    # a character at (1, 2) facing +X, 0.9 m hips: one hip height forward is 0.9 m along +X
    assert motion.to_world((1.0, 2.0), math.pi / 2, 0.9, move) == pytest.approx((1.9, 2.0))


def test_floor_ignores_capture_glitches():
    meta = {"track": {"floor": [-3.0] + [0.5] * 99}}
    assert motion.floor(meta) == 0.5


def test_library_lists_and_loads_clips(tmp_path):
    (tmp_path / "jab.json").write_text(json.dumps({"seconds": 1.2}), encoding="utf-8")
    assert motion.names(str(tmp_path)) == ["jab"]
    assert motion.load(str(tmp_path), "jab")["blend"].endswith("jab.blend")
    assert motion.load(str(tmp_path), "nope") is None


def test_perform_needs_a_clip_from_the_library(tmp_path, capsys, monkeypatch):
    clips = tmp_path / "clips"
    clips.mkdir()
    (clips / "jab.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(config, "MOTIONS_DIR", str(clips))
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    ok = scene(tmp_path / "a", [{"who": "maya", "do": "perform", "clip": "jab", "to": 1.0, "travel": False}])
    assert schema.check_scene(ok) == 0
    bad = scene(tmp_path / "b", [{"who": "maya", "do": "perform", "clip": "uppercut"}])
    assert schema.check_scene(bad) == 1
    assert "no motion clip 'uppercut'" in capsys.readouterr().out
    assert config.scene_files({"script": [{"do": "perform", "clip": "jab"}]})[-1].endswith("jab.json")
