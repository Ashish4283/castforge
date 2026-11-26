import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared import handoff  # noqa: E402

EP = os.path.join("movies", "santa_is_a_lie", "act1")

TIMELINE = {"duration": 72.541667,
            "scenes": [{"id": "cabin_inside", "start": 0.0, "end": 44.875},
                       {"id": "to_the_truck", "start": 44.875, "end": 58.375},
                       {"id": "driving", "start": 58.375, "end": 72.541667}]}

SCENE = {"cast": {"Arthur": {"character": "../characters/arthur.blend", "voice": "bm_george"}},
         "scenes": [{"id": "cabin_inside", "ambience": "cabin_night"},
                    {"id": "to_the_truck", "ambience": "winter_wind"},
                    {"id": "driving"}]}

# What each scene's own shot.timeline.json says. Note the first is LONGER than its slot in the episode
# timeline: the shot files are untrimmed renders, which is exactly the trap this module exists to avoid.
SHOT_TIMELINES = {
    "cabin_inside": {"duration": 45.5, "fps": 24,
                     "lines": [{"start": 2.0, "end": 8.375, "who": "Arthur", "text": "Forty winters."},
                               {"start": 10.0, "end": 15.5, "who": "Arthur", "text": "Retired."}]},
    "to_the_truck": {"duration": 13.5, "lines": []},
    "driving": {"duration": 14.2, "lines": [{"start": 1.0, "end": 3.0, "who": "Arthur", "text": "Here we go."}]},
}


def fake_read(path):
    if path.endswith("episode.timeline.json"):
        return TIMELINE
    if path.endswith("scene.json") and "scenes" not in os.path.dirname(path):
        return SCENE
    for sid, got in SHOT_TIMELINES.items():
        if sid in path.replace("\\", "/"):
            return got
    raise AssertionError(f"nothing asked for {path}")


EVERYTHING = lambda _p: True            # noqa: E731 - a fully rendered episode
NOTHING = lambda _p: False              # noqa: E731 - nothing rendered yet


def rows():
    return handoff.shots(EP, TIMELINE, SCENE, read=fake_read, exists=EVERYTHING)


# --- the two silent traps ---------------------------------------------------------------------------

def test_a_scenes_length_comes_from_its_own_render_not_from_the_episode_timeline():
    """The episode timeline says where a scene SITS in the cut; the shot file is the untrimmed render.
    Taking the length from the timeline would cut 0.6 s off the end of the first scene."""
    first = rows()[0]
    assert first["seconds"] == 45.5
    slot = TIMELINE["scenes"][0]["end"] - TIMELINE["scenes"][0]["start"]
    assert first["seconds"] != slot, "the trap: these two numbers are not the same thing"


def test_the_finished_scene_sound_goes_in_as_a_bed_with_no_offset_and_no_voice_layer():
    """`shot.wav` is already mixed and already in time. A voice layer would duck the scene against itself."""
    one = handoff.picks(rows())["cabin_inside"]
    assert one["bed"].endswith("shot.wav") and one["bed_offset"] == 0.0
    assert "voice" not in one and "line_at" not in one
    assert one["video"].endswith("shot.mp4")


# --- shape ------------------------------------------------------------------------------------------

def test_every_rendered_scene_becomes_one_shot_in_cut_order():
    out = handoff.shot_list("act1", rows())
    assert [s["id"] for s in out["shots"]] == ["cabin_inside", "to_the_truck", "driving"]
    assert out["from"] == "castforge"
    for s in out["shots"]:
        assert s["motion"] is None and s["still"] is None, "a 3D render needs no image-to-video"


def test_a_scene_folder_is_numbered_the_way_castforge_numbers_it():
    assert handoff.scene_folder(EP, 1, "cabin_inside").endswith(os.path.join("scenes", "01_cabin_inside"))
    assert handoff.scene_folder(EP, 12, "x").endswith(os.path.join("scenes", "12_x"))


def test_the_cast_and_their_voices_come_across():
    out = handoff.shot_list("act1", rows(), cast=SCENE["cast"])
    assert out["cast"]["Arthur"]["voice"]["voice_id"] == "bm_george"


def test_a_scene_with_no_ambience_named_is_simply_not_a_place():
    out = handoff.shot_list("act1", rows())
    assert set(out["places"]) == {"cabin_inside", "to_the_truck"}


# --- timing -----------------------------------------------------------------------------------------

def test_each_crossfade_overlaps_two_shots_so_the_cut_is_shorter_than_its_parts():
    at = handoff.starts(rows())
    assert at[0] == 0.0
    assert at[1] == 45.5 - handoff.FADE
    assert at[2] == 45.5 + 13.5 - 2 * handoff.FADE


def test_captions_land_where_the_line_is_actually_spoken_in_the_finished_cut():
    vtt = handoff.captions(rows())
    assert vtt.startswith("WEBVTT")
    assert "00:00:02.000 --> 00:00:08.375" in vtt, "the first line is where the scene puts it"
    # "Here we go." is 1 s into the third scene, which starts at 45.5 + 13.5 - 1.0 = 58.0
    assert "00:00:59.000 --> 00:01:01.000" in vtt
    assert vtt.count("Arthur") == 0, "a caption is the words, not who said them"


def test_a_cut_with_no_lines_still_produces_a_valid_empty_vtt():
    quiet = [dict(r, lines=[]) for r in rows()]
    assert handoff.captions(quiet).strip() == "WEBVTT"


# --- what is not ready -----------------------------------------------------------------------------

def test_an_unrendered_scene_is_named_and_never_guessed_at():
    out = handoff.shots(EP, TIMELINE, SCENE, read=fake_read, exists=NOTHING)
    assert all(r["seconds"] is None for r in out)
    said = "\n".join(handoff.check(EP, out, exists=NOTHING))
    for sid in ("cabin_inside", "to_the_truck", "driving"):
        assert sid in said
    assert "shot.timeline.json" in said
    assert handoff.shot_list("act1", out)["shots"] == [], "a shot with no length is left out, not guessed"


def test_a_rendered_episode_has_nothing_to_complain_about():
    assert handoff.check(EP, rows(), exists=EVERYTHING) == []


def test_a_scene_rendered_but_silent_says_so_rather_than_failing():
    def no_sound(p):
        return not p.endswith("shot.wav")
    said = "\n".join(handoff.check(EP, rows(), exists=no_sound))
    assert "no sound" in said and "cut silent" in said


def test_a_folder_that_is_not_an_episode_says_what_is_missing_and_plans_nothing():
    got = handoff.plan(EP, read=fake_read, exists=NOTHING)
    assert got["shots"] is None and got["picks"] is None
    assert "scene.json" in got["problems"][0]


def test_a_whole_plan_names_the_film_and_the_episode_together():
    got = handoff.plan(EP, read=fake_read, exists=EVERYTHING)
    assert got["title"] == "santa_is_a_lie_act1", "two films can both have an episode called act1"
    assert got["problems"] == [] and len(got["shots"]["shots"]) == 3
    assert set(got["picks"]) == {"cabin_inside", "to_the_truck", "driving"}
    assert got["captions"].startswith("WEBVTT")


def test_the_crossfade_length_is_the_one_forgefilms_actually_uses():
    """If assemble.py ever changes FADE, every caption in every cut drifts. Fail here instead."""
    from shared import suite
    assemble = os.path.join(suite.TOOLS["forgefilms"]["folder"], "scripts", "assemble.py")
    if not os.path.exists(assemble):
        return                      # forgefilms is not installed on this machine; nothing to check
    with open(assemble, encoding="utf-8") as f:
        text = f.read()
    assert f"FADE = {handoff.FADE}" in text, "forgefilms changed its crossfade; shared/handoff.py must follow"
