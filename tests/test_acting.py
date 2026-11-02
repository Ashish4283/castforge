import math
import random

import pytest

from blender import acting

# the 52 ARKit shapes every CastForge character has (checked on movies/santa_is_a_lie/characters/*.blend)
ARKIT = set("""browDownLeft browDownRight browInnerUp browOuterUpLeft browOuterUpRight cheekPuff cheekSquintLeft
cheekSquintRight eyeBlinkLeft eyeBlinkRight eyeLookDownLeft eyeLookDownRight eyeLookInLeft eyeLookInRight
eyeLookOutLeft eyeLookOutRight eyeLookUpLeft eyeLookUpRight eyeSquintLeft eyeSquintRight eyeWideLeft eyeWideRight
jawForward jawLeft jawOpen jawRight mouthClose mouthDimpleLeft mouthDimpleRight mouthFrownLeft mouthFrownRight
mouthFunnel mouthLeft mouthLowerDownLeft mouthLowerDownRight mouthPressLeft mouthPressRight mouthPucker mouthRight
mouthRollLower mouthRollUpper mouthShrugLower mouthShrugUpper mouthSmileLeft mouthSmileRight mouthStretchLeft
mouthStretchRight mouthUpperUpLeft mouthUpperUpRight noseSneerLeft noseSneerRight tongueOut""".split())


def test_expressions_never_fight_lip_sync():
    for name, weights in acting.EXPRESSIONS.items():
        assert not set(weights) & set(acting.MOUTH_KEYS), name


def test_expressions_only_use_shapes_the_characters_have():
    for name, weights in acting.EXPRESSIONS.items():
        assert set(weights) - {"eyelids"} <= ARKIT, name
        assert all(0.0 <= v <= 1.0 for v in weights.values()), name


def test_layer_holds_blends_and_returns_from_overlays():
    layer = acting.Layer({"a": 0.0}, blend=0.4)
    layer.set(2.0, {"a": 1.0})
    assert layer.at(1.9)["a"] == 0.0
    assert 0.0 < layer.at(2.2)["a"] < 1.0
    assert layer.at(2.5)["a"] == pytest.approx(1.0)
    layer.overlay(5.0, 7.0, {"a": 0.2})
    assert layer.at(6.0)["a"] == pytest.approx(0.2)
    assert layer.at(7.5)["a"] == pytest.approx(1.0)


def test_quick_changes_blend_from_where_they_are():
    layer = acting.Layer({"a": 0.0}, blend=1.0)
    layer.set(1.0, {"a": 1.0})
    layer.set(1.2, {"a": 0.0})        # changes its mind before the first blend finished
    values = [layer.at(1.0 + i * 0.01)["a"] for i in range(150)]
    assert max(abs(b - a) for a, b in zip(values, values[1:])) < 0.05


@pytest.mark.parametrize("name", sorted(acting.GESTURES))
def test_gestures_are_finite_and_ease_in_and_out(name):
    seconds, hands, pose = acting.GESTURES[name]
    assert hands in ("one", "both", "none")
    for i in range(41):
        u = i / 40
        values = pose(u, u * seconds, {"azimuth": 0.6})
        flat = [v for part in values.values() for v in (part.values() if isinstance(part, dict) else [part])
                if not isinstance(v, str)]
        assert all(math.isfinite(v) for v in flat)
    assert acting.gesture_weight(0.0, seconds) == 0.0
    assert acting.gesture_weight(seconds, seconds) == 0.0
    assert acting.gesture_weight(seconds / 2, seconds) == pytest.approx(1.0)


def test_hand_shapes():
    relaxed, thumb = acting.finger_curls()
    assert relaxed == acting.FINGER_CURL and thumb == 1.0
    pointing, _ = acting.finger_curls(shape="point", grip=1.0)
    assert pointing["index"] < 0.1 < 1.0 < pointing["middle"]
    _, thumbs_up = acting.finger_curls(shape="thumbs", grip=1.0)
    assert thumbs_up == 0.0


def test_gaze_angles_follow_the_heading_convention():
    eye = (0.0, 0.0, 1.6)
    assert acting.gaze_angles(eye, 0.0, 0.0, (0.0, -3.0, 1.6)) == pytest.approx((0.0, 0.0))
    yaw, up = acting.gaze_angles(eye, 0.0, 0.0, (1.0, -3.0, 1.6))      # to the character's left (+X)
    assert yaw > 0 and up == pytest.approx(0.0)
    yaw, up = acting.gaze_angles(eye, 0.0, 0.0, (0.0, -1.0, 0.6))      # a child below
    assert up < 0
    yaw, _ = acting.gaze_angles(eye, 0.0, 0.0, (5.0, 0.0, 1.6))        # far beyond what eyes can turn
    assert yaw == acting.EYE_YAW
    yaw, _ = acting.gaze_angles(eye, math.pi / 2, 0.0, (5.0, 0.0, 1.6))  # body already faces it
    assert yaw == pytest.approx(0.0, abs=1e-9)


def test_saccades_stay_inside_the_look():
    jumps = acting.saccades(random.Random(1), 2.0, 10.0)
    assert jumps and all(2.0 <= t < 10.0 for t, _, _ in jumps)


def test_postures_and_paces_are_complete():
    assert set(acting.POSTURES) >= {"neutral", "confident", "slumped", "tense"}
    for speed, step, swing, lean in acting.PACES.values():
        assert 0.5 < speed < 2.0 and 0.4 < step < 0.9 and swing > 0 and lean >= 0
