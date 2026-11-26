"""The third arrow: a rendered 3D shot becoming a photographed one (shared/real.py)."""
import json
import os

from shared import real, suite


# --- how long a window may be -----------------------------------------------------------------------
def test_a_window_never_asks_for_more_than_the_model_was_trained_on():
    for seconds in (0.1, 1, 4.9, 5, 5.1, 12, 60):
        n = real.frames_for(seconds)
        assert real.LEAST <= n <= real.TRAINED, seconds
        assert (n - 1) % 4 == 0, f"{seconds}s gave {n} frames, which is not 4n+1"


def test_five_seconds_is_the_eighty_one_frames_wan_was_trained_on():
    assert real.frames_for(5.0) == 81
    assert real.seconds_for(81) == 5.0


def test_the_length_we_ask_for_comes_back_as_the_frames_we_wanted():
    # forgefilms works the other way round; if the two disagree the clip is a frame off the cut
    for n in range(real.LEAST, real.TRAINED + 1, 4):
        assert real.frames_for(real.seconds_for(n)) == n


def test_a_long_take_is_split_evenly_rather_than_into_five_seconds_and_a_stub():
    got = real.windows({"at": 0.0, "seconds": 11.0, "kind": "wide", "on": []})
    assert len(got) == 3
    assert [w["part"] for w in got] == [1, 2, 3]
    assert all(abs(w["seconds"] - got[0]["seconds"]) < 0.1 for w in got), "a runt window cannot be judged"
    assert sum(w["seconds"] for w in got) >= 10.5


def test_a_short_take_is_left_whole():
    got = real.windows({"at": 2.5, "seconds": 3.2, "kind": "close", "on": ["Arthur"]})
    assert len(got) == 1 and got[0]["at"] == 2.5 and got[0]["carries_on"] is False


def test_every_window_after_the_first_carries_on_from_the_one_before():
    got = real.windows({"at": 0.0, "seconds": 14.0, "kind": "wide", "on": []})
    assert [w["carries_on"] for w in got] == [False, True, True]


# --- the director's cut is the take -------------------------------------------------------------------
def test_a_take_is_one_camera_shot_because_a_clip_cannot_contain_a_cut():
    timeline = {"duration": 10.0, "shots": [{"time": 0.0, "kind": "wide", "on": []},
                                            {"time": 4.0, "kind": "close", "on": ["Arthur"]}]}
    got = real.takes(timeline)
    assert [(t["at"], t["seconds"], t["kind"]) for t in got] == [(0.0, 4.0, "wide"), (4.0, 6.0, "close")]
    assert got[1]["on"] == ["Arthur"]


def test_a_scene_the_director_never_cut_is_one_long_take():
    assert real.takes({"duration": 7.5, "shots": []}) == [
        {"at": 0.0, "seconds": 7.5, "kind": "auto", "on": [], "move": "static", "lens": None}]


def test_a_take_carries_the_move_and_the_lens_the_director_chose():
    timeline = {"duration": 6.0, "shots": [{"time": 0.0, "kind": "wide", "move": "push_in", "lens": 100}]}
    take = real.takes(timeline)[0]
    assert take["move"] == "push_in" and take["lens"] == 100
    window = real.windows(take)[0]
    said = real.prompt({}, {}, take, window, [])
    assert "pushes slowly in" in said
    assert "shallow depth of field" in said


def test_a_render_from_before_the_move_was_written_down_still_works():
    take = real.takes({"duration": 3.0, "shots": [{"time": 0.0, "kind": "wide"}]})[0]
    assert take["move"] == "static" and take["lens"] is None
    assert "holds still" in real.prompt({}, {}, take, real.windows(take)[0], [])


def test_a_cut_the_director_replaced_instantly_is_not_a_take_of_its_own():
    # the wide lasts 0.01 s - less than one frame at 16 fps - so the close is what is actually on screen
    timeline = {"duration": 5.0, "shots": [{"time": 0.0, "kind": "wide"}, {"time": 0.01, "kind": "close"},
                                           {"time": 2.0, "kind": "medium"}]}
    got = real.takes(timeline)
    assert [t["kind"] for t in got] == ["close", "medium"]
    assert got[0]["at"] == 0.01, "the surviving take keeps its own start, not the dropped one's"


def test_shots_out_of_order_in_the_file_still_come_out_in_time_order():
    timeline = {"duration": 9.0, "shots": [{"time": 6.0, "kind": "close"}, {"time": 0.0, "kind": "wide"},
                                           {"time": 3.0, "kind": "medium"}]}
    assert [t["at"] for t in real.takes(timeline)] == [0.0, 3.0, 6.0]


# --- the prompt is read off the scene -----------------------------------------------------------------
ARTHUR = {"gender": "male", "age": 70, "build": "heavy", "beard": "full",
          "hair": {"length": "short", "style": "shaggy", "color": "#e8e4dc"},
          "outfit": {"garment": "trousers", "style": "work", "top": "#40506a", "bottom": "#c8102e"}}


def test_a_person_is_described_from_their_own_design_not_from_their_name():
    said = real.describe(ARTHUR, "Arthur")
    assert said == ("a heavy-set man of about 70 with short shaggy white hair and a full beard, "
                    "wearing a navy work top and red trousers")


def test_a_colour_becomes_the_nearest_name_the_suite_already_uses():
    assert real.colour_word("#efefe9") == "white"
    assert real.colour_word("#1b1a19") == "black"
    assert real.colour_word("not a colour") is None
    assert real.colour_word("#c9a96a") in ("blonde", "blond")


# Three colours the real cast caught, each of which had been named wrongly on the way here.
def test_a_slate_navy_coat_is_navy_and_not_purple():
    # they sit close together as plain RGB numbers and are not the same colour to look at
    assert real.colour_word("#40506a") == "navy"


def test_a_vivid_red_is_red_and_not_rust():
    # the suite's "red" is a HAIR red; cloth has a red of its own, which is why there are two lists
    assert real.colour_word("#c8102e") == "red"
    assert real.colour_word("#c8102e", real.HAIR_COLOURS) != "red"


def test_a_near_white_is_white_even_though_its_saturation_reads_high():
    # #efefe9 is 15% saturated in HSL and plainly white; chroma is what says so
    assert real.colour_word("#e8e4dc", real.HAIR_COLOURS) == "white"
    assert real.colour_word("#9a978f") == "grey"


def test_a_grey_is_never_offered_as_the_nearest_colour_to_a_colour():
    for hexed in ("#c8102e", "#2f6d3a", "#2f5ea8"):
        assert real.colour_word(hexed) not in ("white", "grey", "black", "charcoal", "silver"), hexed


def test_a_thought_keeps_the_mouth_shut_and_a_line_does_not():
    lines = [{"start": 1.0, "end": 3.0, "who": "Arthur", "kind": "think", "text": "..."},
             {"start": 4.0, "end": 6.0, "who": "Maya", "kind": "say", "text": "..."}]
    assert real.doing(lines, 0.0, 3.5) == ["Arthur is silent, thinking, mouth closed"]
    assert real.doing(lines, 3.5, 7.0) == ["Maya is speaking, lips moving"]
    assert real.doing(lines, 7.0, 9.0) == []


def test_someone_who_speaks_and_thinks_in_one_window_is_only_told_to_speak():
    lines = [{"start": 1.0, "end": 2.0, "who": "Arthur", "kind": "think"},
             {"start": 2.0, "end": 3.0, "who": "Arthur", "kind": "say"}]
    assert real.doing(lines, 0.0, 5.0) == ["Arthur is speaking, lips moving"]


def test_the_prompt_says_the_shot_the_person_the_light_and_the_weather():
    scene = {"lighting": "candlelight", "weather": {"type": "snow", "amount": 0.4}}
    take = {"at": 0.0, "seconds": 4.0, "kind": "close", "on": ["Arthur"]}
    window = {"at": 0.0, "seconds": 4.0, "frames": 65, "part": 1, "parts": 1, "carries_on": False}
    said = real.prompt(scene, {"Arthur": ARTHUR}, take, window, [])
    assert said.startswith("a close-up")
    assert "candlelight" in said and "snow falling" in said
    assert "the camera holds still" in said


def test_a_continued_window_says_so_so_the_model_does_not_start_a_new_shot():
    take = {"at": 0.0, "seconds": 9.0, "kind": "wide", "on": []}
    second = real.windows(take)[1]
    said = real.prompt({}, {}, take, second, [])
    assert "continues without a cut" in said


def test_an_empty_frame_is_still_described():
    take = {"at": 0.0, "seconds": 3.0, "kind": "wide", "on": []}
    window = {"at": 0.0, "seconds": 3.0, "frames": 49, "part": 1, "parts": 1, "carries_on": False}
    assert "nobody moves in frame" in real.prompt({}, {}, take, window, [])


def test_every_lighting_mood_and_shot_size_has_words_of_its_own():
    # a mood with no words would silently drop the light out of every prompt that uses it
    from core import schema
    for mood in schema.LIGHTING:
        assert mood in real.LIGHT_WORDS, mood
    for kind in schema.SHOT_KINDS:
        assert kind in real.SHOT_WORDS, kind
    for move in schema.CAMERA_MOVES:
        assert move in real.MOVE_WORDS, move
    for weather in schema.WEATHER:
        assert weather in real.WEATHER_WORDS, weather


# --- a whole episode ----------------------------------------------------------------------------------
EPISODE = os.path.join("movies", "film", "act1")
FILES = {
    os.path.join(EPISODE, "scene.json"): {
        "title": "A Film", "lighting": "night",
        "cast": {"Arthur": {"character": "../characters/arthur.blend"}},
        "scenes": [{"id": "cabin", "lighting": "candlelight"}, {"id": "street"}],
    },
    os.path.join(EPISODE, "episode.timeline.json"): {"scenes": [{"id": "cabin"}, {"id": "street"}]},
    os.path.join(EPISODE, "scenes", "01_cabin", "shot.timeline.json"): {
        "duration": 12.0, "lines": [{"start": 1.0, "end": 3.0, "who": "Arthur", "kind": "think"}],
        "shots": [{"time": 0.0, "kind": "wide", "on": []}, {"time": 4.0, "kind": "close", "on": ["Arthur"]}],
    },
    os.path.join(EPISODE, "scenes", "02_street", "shot.timeline.json"): {
        "duration": 3.0, "shots": [{"time": 0.0, "kind": "medium", "on": ["Arthur"]}],
    },
    os.path.normpath(os.path.join(EPISODE, "../characters/arthur.design.json")): ARTHUR,
}


def fake_plan(files=FILES):
    return real.plan(EPISODE, read=lambda p: files[os.path.normpath(p)],
                     exists=lambda p: os.path.normpath(p) in files)


def test_an_episode_becomes_one_window_per_piece_of_camera_shot():
    got = fake_plan()
    # cabin: a 4 s wide take, then an 8 s close take split in two; street: one 3 s take
    assert [r["id"] for r in got["shots"]] == ["cabin_1", "cabin_2_1", "cabin_2_2", "street_1"]
    assert got["missing"] == [] and real.check(got) == []


def test_each_scene_keeps_its_own_light_and_not_the_episodes():
    got = {r["id"]: r for r in fake_plan()["shots"]}
    assert "candlelight" in got["cabin_1"]["motion"]
    assert "night, dim cool light" in got["street_1"]["motion"]


def test_a_wide_shot_still_describes_whoever_is_standing_in_the_room():
    # the director puts nobody "on" a wide shot; told nothing, the model is free to change the man's
    # coat between the wide and the close, or to remove him
    got = {r["id"]: r for r in fake_plan()["shots"]}
    assert "heavy-set man" in got["cabin_2_1"]["motion"]
    assert "heavy-set man" in got["cabin_1"]["motion"]
    assert "nobody moves in frame" not in got["cabin_1"]["motion"]


def test_only_the_first_window_of_a_take_is_grabbed_from_the_render():
    got = fake_plan()
    assert [name for _v, _t, name in real.stills(got)] == ["cabin_1", "cabin_2_1", "street_1"]
    assert real.carried(got) == [("cabin_2_2", "cabin_2_1")]


def test_a_still_is_grabbed_at_the_second_the_take_starts():
    at = {name: t for _v, t, name in real.stills(fake_plan())}
    assert at["cabin_1"] == 0.0 and at["cabin_2_1"] == 4.0


def test_a_scene_that_was_never_rendered_is_named_rather_than_skipped_in_silence():
    files = {k: v for k, v in FILES.items() if "02_street" not in k}
    got = real.plan(EPISODE, read=lambda p: files[os.path.normpath(p)],
                    exists=lambda p: os.path.normpath(p) in files)
    assert got["missing"] == ["street"]
    assert any("render the episode first" in m for m in real.check(got))


def test_the_shot_list_is_the_shape_forgefilms_reads():
    listed = real.shot_list(fake_plan())
    assert listed["title"] == "A Film"
    for shot in listed["shots"]:
        assert set(shot) >= {"id", "still", "seconds", "motion"}
        assert shot["still"] == shot["id"]
        assert real.frames_for(shot["seconds"]) <= real.TRAINED


def test_the_frame_rate_is_the_one_forgefilms_actually_runs():
    # a cross-repo check, like the crossfade in test_handoff: if forgefilms changes its model or its
    # frame rate, the lengths written here stop matching the clips that come back
    script = os.path.join(suite.TOOLS["forgefilms"]["folder"], "scripts", "wan_workflows.py")
    if not os.path.exists(script):
        return
    said = open(script, encoding="utf-8").read()
    assert f"FPS = {real.FPS}" in said, "forgefilms runs image-to-video at a different frame rate now"
    assert "4n+1" in said


def test_the_plan_is_json_and_nothing_in_it_is_a_surprise():
    json.dumps(fake_plan())


def test_a_continued_window_still_gets_a_still_so_the_workflow_can_be_built_today():
    # forgefilms needs one still per clip; the one this window really wants does not exist until the
    # first pass has run on a GPU, so it gets the render's frame and a note saying what to replace
    got = fake_plan()
    must = {name for _v, _t, name in real.stills(got)}
    maybe = {name for _v, _t, name in real.provisional(got)}
    assert must | maybe == {r["id"] for r in got["shots"]}
    assert must & maybe == set()
    assert maybe == {"cabin_2_2"}
