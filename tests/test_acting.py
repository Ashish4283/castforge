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


def test_whip_lags_overshoots_and_settles():
    seconds = 2.0
    # starts after the shoulder
    assert acting.whip(0.05, seconds, acting.ELBOW_LAG) == 0.0 < acting.gesture_weight(0.05, seconds)
    # passes its mark after arriving, then settles back
    peak = max(acting.whip(i / 100, seconds, acting.ELBOW_LAG) for i in range(40, 100))
    assert peak > 1.02
    assert acting.whip(1.2, seconds, acting.ELBOW_LAG) == pytest.approx(1.0, abs=0.01)
    # lets go after the gesture ends and comes to rest
    end = seconds + acting.ELBOW_LAG + acting.SETTLE
    assert abs(acting.whip(end, seconds, acting.ELBOW_LAG)) < 0.01


def test_faces_are_not_mirror_perfect():
    w = acting.asymmetric({"mouthSmileLeft": 0.5, "mouthSmileRight": 0.5, "browInnerUp": 0.3}, 0.08)
    assert w["mouthSmileLeft"] > w["mouthSmileRight"] and w["browInnerUp"] == 0.3


def test_crouch_lowers_the_hips_and_mix_blends_the_drop():
    crouch = acting.POSTURES["crouch"]
    assert "drop" in acting.BODY_CHANNELS and crouch["drop"] > 0.3
    half = acting.mix(acting.POSTURES["neutral"], crouch, 0.5)
    assert abs(half["drop"] - crouch["drop"] / 2) < 1e-9
    assert abs(half["stance"] - (1.0 + crouch["stance"]) / 2) < 1e-9     # stance rests at 1, not 0


def test_clap_uses_both_hands_and_beats():
    seconds, hands, pose = acting.GESTURES["clap"]
    assert hands == "both" and seconds > 1.0
    flat = pose(0.5, 0.4, {})
    assert flat["arm"]["hand"] == "flat" and flat["arm"]["grip"] == 1.0  # fingers straight, not splayed
    bends = {round(pose(u, u * seconds, {})["arm"]["bend"], 3) for u in (0.1, 0.2, 0.3, 0.4, 0.5)}
    assert len(bends) > 1                                                # the hands meet and part


def test_clapping_hands_never_mirror_each_other_exactly():
    """Perfectly symmetric hands meet at the midline and interleave; one hand has to lead."""
    pose = acting.GESTURES["clap"][2]
    for t in (0.0, 0.19, 0.4):
        p = pose(t / 1.9, t, {})
        left, right = p["arm_L"], p["arm_R"]
        assert right["bend"] > left["bend"] and right["swing"] < left["swing"]
        assert right["raise"] > left["raise"]
        assert left["hand"] == right["hand"] == "flat"


def test_clap_closes_to_a_stop_without_crossing():
    pose = acting.GESTURES["clap"][2]
    bends = [pose(t / 1.9, t, {})["arm_R"]["bend"] for t in [i / 60 for i in range(60)]]
    assert max(bends) - min(bends) < 0.3                 # a bounded travel, so the palms cannot pass through
    assert min(bends) > 0.5                              # and the elbows never straighten out


def test_clap_bends_the_wrist():
    """Measured on the rig: without a wrist the fingers point across the chest, whatever the arm does."""
    p = acting.GESTURES["clap"][2](0.5, 0.4, {})
    assert abs(p["arm"]["wrist"]) > 0.2
    assert p["arm_L"]["wrist"] == p["arm_R"]["wrist"] == p["arm"]["wrist"]


def test_fingers_can_stop_short_of_a_closed_fist():
    tight, loose = acting.grip_curl(0.03), acting.grip_curl(0.22)
    assert tight == 1.0 and 0.25 <= loose < 0.6           # a thin handle is wrapped, a fat body only held
    assert acting.grip_curl(0.0) == 1.0
    assert "flat" in acting.HAND_SHAPES and "grip" in acting.HAND_SHAPES
    curls, thumb = acting.finger_curls(0.0, "grip", 1.0)
    assert thumb > acting.HAND_SHAPES["fist"][1]          # the thumb comes over the fingers to hold it


def test_clips_say_whether_the_hands_are_closed():
    assert acting.clip_hands("boxing_punch_right") == ("fist", 0.95)
    assert acting.clip_hands("sword_swing")[0] == "fist"
    assert acting.clip_hands("walk_forward") == (None, 0.0)
    assert acting.clip_hands("open_palm_slap") == (None, 0.0)            # a slap is not a punch
    assert acting.clip_hands("fist")[0] == "fist" and acting.clip_hands("open") == (None, 0.0)
    assert acting.clip_hands(None) == (None, 0.0)


def test_a_lantern_hangs_from_the_hand_instead_of_swallowing_it():
    """A lantern is too fat to close a fist round: the hand holds it near the top and stays clear of it."""
    lantern = acting.carry_grip([0.18, 0.18, 0.32])
    assert lantern["kind"] == "hang"
    assert lantern["along"] > 0.9 * 0.32 - 1e-9           # held at the top, not buried at mid-height
    assert lantern["clear"] > 0.5 * 0.18                  # outside the palm, so it cannot reach the wrist
    assert lantern["curl"] < 1.0                          # fingers stop on it
    cup = acting.carry_grip([0.08, 0.08, 0.1])
    assert cup["kind"] == "palm" and cup["clear"] < 0.06
    for size in ([0.18, 0.18, 0.32], [0.08, 0.08, 0.9], [1.2, 0.2, 0.04], [0.17, 0.24, 0.04]):
        g = acting.carry_grip(size)
        assert g["clear"] >= 0.012 and 0.25 <= g["curl"] <= 1.0          # every grip stays off the palm


def test_carry_grips_tell_sticks_from_handfuls():
    crowbar = acting.carry_grip([0.08, 0.08, 0.9])
    assert crowbar["kind"] == "stick" and crowbar["axis"] == 2 and 0.2 < crowbar["along"] < 0.35
    lantern = acting.carry_grip([0.25, 0.25, 0.42])
    assert lantern["kind"] == "hang" and abs(lantern["along"] - 0.92 * 0.42) < 1e-9
    plank = acting.carry_grip([1.2, 0.2, 0.04])
    assert plank["kind"] == "stick" and plank["axis"] == 0 and plank["lift"] == 0.02
    assert acting.can_carry([0.08, 0.08, 0.9]) and not acting.can_carry([1.5, 0.4, 0.4])
    assert not acting.can_carry([0.8, 0.7, 0.4])                         # too wide for one hand


def test_a_pose_fix_fades_in_and_out_around_its_moment():
    keys = acting.fix_frames({"at": 2.0, "seconds": 1.0, "fade": 0.5}, 24, 300)
    frames = [f for f, _ in keys]
    assert min(frames) >= 24 * 1.5 - 2 and max(frames) <= 24 * 3.5 + 2     # window = at - fade .. at+hold+fade
    middle = [w for f, w in keys if 24 * 2.1 <= f <= 24 * 2.9]
    assert middle and min(middle) > 0.99                                    # full strength while it holds
    assert keys[0][1] < 0.2 and keys[-1][1] < 0.2                           # eased at both ends
    assert all(0.0 <= w <= 1.0 for _, w in keys)


def test_a_momentary_fix_still_has_keys_and_never_runs_past_the_scene():
    keys = acting.fix_frames({"at": 1.0}, 24, 300)
    assert len(keys) >= 3 and max(w for _, w in keys) > 0.9
    assert acting.fix_frames({"at": 100.0}, 24, 300) == []                  # past the end: nothing
    short = acting.fix_frames({"at": 0.0, "fade": 0.5}, 24, 300)
    assert short and min(f for f, _ in short) >= 1                          # never before frame 1


def test_fix_parts_are_plain_names_mapped_to_rig_controls():
    assert acting.FIX_PARTS["head"] == "head" and acting.FIX_PARTS["hips"] == "torso"
    assert acting.FIX_PARTS["upper_arm.L"] == "upper_arm_fk.L"
    assert all("." not in p or p.endswith((".L", ".R")) for p in acting.FIX_PARTS)
