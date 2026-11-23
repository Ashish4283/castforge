import json
from pathlib import Path

import pytest

from core import config, schema

TYPES = {"point", "number", "text", "audio", "enum", "target", "look", "voice", "door", "seat", "sfx", "bed", "bool",
         "clip", "cast_list", "prop"}


def test_every_parameter_has_a_known_type_and_help():
    for name, action in schema.ACTIONS.items():
        assert action["help"], name
        for key, par in action["params"].items():
            assert par["type"] in TYPES, (name, key)
            assert par["help"], (name, key)
            if par["type"] == "enum":
                assert par["values"], (name, key)


def test_props_have_sizes_and_known_materials():
    for name, (size, material, blocks, help_) in schema.PROP_TYPES.items():
        assert help_
        if name != "picture_road":
            assert len(size) == 3 and all(v > 0 for v in size), name
            assert material in schema.MATERIALS, name
    assert set(schema.SEAT_TYPES) <= set(schema.PROP_TYPES)


def test_vehicle_can_expose_an_openable_driver_door(tmp_path, capsys):
    folder = scene(tmp_path, [{"who": "maya", "do": "open", "door": "truck_driver"}],
                   props=[{"id": "truck", "make": "pickup_truck", "door_id": "truck_driver",
                           "picture_rect": [0.2, 0.3, 0.7, 0.8]}])
    assert schema.check_scene(folder) == 0
    assert "looks good" in capsys.readouterr().out
    described = schema.describe()["props"]
    assert {"pickup_truck", "steering_wheel", "car_radio"} <= set(described)


def test_a_model_prop_can_be_sat_on_once_it_names_its_seat(tmp_path, capsys):
    (tmp_path / "cab.blend").write_bytes(b"")
    steps = [{"who": "maya", "do": "sit", "on": "cab"}, {"who": "maya", "do": "drive", "wheel": "cab"}]
    folder = scene(tmp_path, steps, props=[{"id": "cab", "file": "cab.blend", "seat": "Seat", "wheel": "Wheel"}])
    assert schema.check_scene(folder) == 0
    folder = scene(tmp_path, steps, props=[{"id": "cab", "file": "cab.blend"}])
    assert schema.check_scene(folder) >= 1
    assert "sit needs" in capsys.readouterr().out


def test_picture_rect_and_doorway_environment_are_validated(tmp_path, capsys):
    folder = scene(tmp_path, [], props=[{"id": "door", "make": "door", "outside_image": "missing.png",
                                         "outside_rect": [0.8, 0.2, 0.1, 0.9],
                                         "picture_rect": [0.2, 0.3, 0.7, 0.8]}])
    assert schema.check_scene(folder) >= 2
    output = capsys.readouterr().out
    assert "outside image not found" in output
    assert '"outside_rect" must be' in output


def test_description_for_the_app_is_json():
    described = json.loads(json.dumps(schema.describe()))
    assert "walk" in described["actions"] and "voices" in described


def test_reusable_prop_asset_path_is_valid_from_nested_scene(tmp_path, capsys):
    movie = tmp_path / "film"
    episode = movie / "act1" / "scenes" / "01_opening"
    prop = movie / "props" / "santa_radio"
    episode.mkdir(parents=True)
    prop.mkdir(parents=True)
    (episode / "background.png").write_bytes(b"image")
    (prop / "santa_radio.blend").write_bytes(b"blend")
    (episode / "scene.json").write_text(json.dumps({
        "background": "background.png", "cast": {},
        "props": [{"id": "santa_radio", "file": "../../../props/santa_radio/santa_radio.blend",
                   "position": [0, 0], "scale": 1}],
        "script": [],
    }), encoding="utf-8")

    assert schema.check_scene(str(episode)) == 0
    assert "looks good" in capsys.readouterr().out


def test_shared_library_building_path_is_valid_from_nested_scene(tmp_path, capsys):
    movie_root = tmp_path / "movies" / "film"
    episode = movie_root / "act1" / "scenes" / "01_opening"
    building = tmp_path / "library" / "buildings" / "hut"
    episode.mkdir(parents=True)
    building.mkdir(parents=True)
    (episode / "background.png").write_bytes(b"image")
    (building / "hut.blend").write_bytes(b"blend")
    (episode / "scene.json").write_text(json.dumps({
        "background": "background.png", "cast": {},
        "props": [{"id": "building_hut", "file": "../../../../../library/buildings/hut/hut.blend",
                   "position": [0, 0], "scale": 1}],
        "script": [],
    }), encoding="utf-8")

    assert schema.check_scene(str(episode)) == 0
    assert "looks good" in capsys.readouterr().out


def scene(tmp_path, script, **extra):
    (tmp_path / "background.png").write_bytes(b"x")
    (tmp_path / "maya.blend").write_bytes(b"x")
    (tmp_path / "tom.blend").write_bytes(b"x")
    data = {"background": "background.png",
            "cast": {"maya": {"character": "maya.blend", "voice": "af_heart", "position": [-0.6, 0.5]},
                     "tom": {"character": "tom.blend", "voice": "am_santa", "position": [0.6, 0.5]}},
            "script": script, **extra}
    (tmp_path / "scene.json").write_text(json.dumps(data), encoding="utf-8")
    return str(tmp_path)


def test_new_actions_pass_when_used_correctly(tmp_path, capsys):
    folder = scene(tmp_path, [
        {"who": "maya", "do": "face", "target": "tom"},
        {"who": "maya", "do": "say", "text": "Hi!", "expression": "happy", "fx": "phone"},
        {"who": "tom", "do": "emote", "expression": "surprised", "seconds": 2},
        {"who": "tom", "do": "gesture", "type": "point", "target": "maya"},
        {"who": "tom", "do": "posture", "posture": "confident"},
        {"who": "tom", "do": "look", "target": "left"},
        {"who": "tom", "do": "walk", "to": [1.5, 1.0], "pace": "hurry"},
        {"do": "narrate", "text": "And so it began.", "voice": "bm_lewis"},
        {"do": "camera", "shot": "two_shot", "on": ["maya", "tom"], "move": "push_in", "seconds": 3},
        {"do": "music", "stop": True},
        {"do": "wait"},
    ])
    assert schema.check_scene(folder) == 0
    assert "looks good" in capsys.readouterr().out


@pytest.mark.parametrize("step, message", [
    ({"who": "maya", "do": "emote", "expression": "furious"}, "unknown expression 'furious'"),
    ({"who": "maya", "do": "gesture", "type": "point"}, 'a point gesture needs "target"'),
    ({"who": "maya", "do": "gesture"}, 'gesture needs "type"'),
    ({"who": "maya", "do": "walk", "to": [1, 0], "pace": "sprint"}, "unknown pace 'sprint'"),
    ({"who": "maya", "do": "walk", "to": "door"}, '"to" must be a spot [x, y]'),
    ({"do": "narrate", "text": "Once upon a time."}, 'narration needs a "voice"'),
    ({"do": "camera", "shot": "close", "on": "santa"}, "'santa' is not in the cast"),
    ({"do": "music"}, 'music needs "bed"'),
    ({"who": "maya", "do": "look", "target": "sideways"}, '"target" must be a cast member'),
])
def test_mistakes_in_new_actions_are_reported(tmp_path, capsys, step, message):
    assert schema.check_scene(scene(tmp_path, [step])) >= 1
    assert message in capsys.readouterr().out


def test_episode_narrator_voice_is_enough(tmp_path, capsys):
    folder = scene(tmp_path, [{"do": "narrate", "text": "Once."}], narrator={"voice": "bm_fable"})
    assert schema.check_scene(folder) == 0


def test_empty_episode_is_rejected_before_render(tmp_path, capsys):
    (tmp_path / "scene.json").write_text(json.dumps({"cast": {}, "scenes": []}), encoding="utf-8")
    assert schema.check_scene(str(tmp_path)) == 1
    assert 'episode "scenes" must be a non-empty list' in capsys.readouterr().out


@pytest.mark.parametrize("step", [
    {"who": "maya", "do": "face", "target": {"name": "tom"}},
    {"do": "camera", "shot": "close", "on": {"maya": True}},
    {"who": "maya", "do": "face", "target": ["maya"]},
    {"who": "maya", "do": ["walk"]},
    {"do": "music", "bed": {"name": "cabin"}},
    {"who": "maya", "do": "wait", "seconds": True},
])
def test_malformed_action_values_are_reported_instead_of_crashing(tmp_path, capsys, step):
    assert schema.check_scene(scene(tmp_path, [step])) >= 1
    assert "ERROR:" in capsys.readouterr().out


def test_non_object_scene_and_action_are_reported(tmp_path, capsys):
    (tmp_path / "scene.json").write_text(json.dumps([]), encoding="utf-8")
    assert schema.check_scene(str(tmp_path)) == 1
    assert "scene.json must contain a JSON object" in capsys.readouterr().out

    folder = scene(tmp_path, ["walk"])
    assert schema.check_scene(folder) >= 1
    assert "action must be a JSON object" in capsys.readouterr().out


def test_unknown_scene_settings_are_flagged(tmp_path, capsys):
    folder = scene(tmp_path, [], lighting="disco", aspect="3:1", weather={"type": "hail"})
    assert schema.check_scene(folder) == 1               # the aspect is an error, the rest warnings
    out = capsys.readouterr().out
    assert "unknown lighting 'disco'" in out and "unknown aspect '3:1'" in out and "unknown weather 'hail'" in out


def test_gemini_scene_prompt_teaches_every_action_and_prop():
    prompt = (Path(__file__).parent.parent / "docs" / "GEMINI_SCENE_PROMPT.md").read_text(encoding="utf-8")
    for action in schema.ACTIONS:
        assert f'"do": "{action}"' in prompt, action
    for prop in schema.PROP_TYPES:
        if prop not in ("seat", "picture_road"):
            assert prop in prompt, prop
    for key in schema.SCENE_KEYS:                  # a new scene setting must be taught here too
        assert key in prompt, key


def test_finishing_settings_never_change_the_render_key(tmp_path):
    from core import config
    base = {"background": "bg.png", "cast": {}, "script": [{"do": "wait"}]}
    finished = dict(base, title={"text": "T"}, grade="noir", transition="dissolve", master={"loudness": -14})
    assert config.render_key(base, "draft", str(tmp_path), schema.FINISH_KEYS) == \
        config.render_key(finished, "draft", str(tmp_path), schema.FINISH_KEYS)
    assert config.render_key(dict(base, lighting="night"), "draft", str(tmp_path), schema.FINISH_KEYS) != \
        config.render_key(base, "draft", str(tmp_path), schema.FINISH_KEYS)


def test_hold_needs_a_real_prop_and_warns_when_it_is_too_big(tmp_path, capsys):
    scene = {"background": "bg.png", "floor": "wood",
             "cast": {"Arthur": {"character": "arthur.blend", "position": [0, 0]}},
             "props": [{"id": "lantern", "make": "box", "position": [1, 0], "size": [0.2, 0.2, 0.4]},
                       {"id": "crate", "make": "box", "position": [2, 0], "size": [1.0, 0.9, 0.9]}],
             "script": [{"who": "Arthur", "do": "hold", "prop": "lantern"},
                        {"who": "Arthur", "do": "release", "to": [1.5, 0.5]},
                        {"who": "Arthur", "do": "duck", "seconds": 0.8},
                        {"who": "Arthur", "do": "hold", "prop": "crate"},
                        {"who": "Arthur", "do": "hold", "prop": "ghost"}]}
    (tmp_path / "bg.png").write_bytes(b"x")
    (tmp_path / "arthur.blend").write_bytes(b"x")
    (tmp_path / "scene.json").write_text(json.dumps(scene), encoding="utf-8")
    assert schema.check_scene(str(tmp_path)) == 1
    out = capsys.readouterr().out
    assert '"prop" must be the id of a prop in this scene' in out
    assert "looks too big to carry" in out and "1.0 x 0.9 x 0.9" in out


def test_strike_needs_a_cast_target_and_a_known_clip(tmp_path, capsys):
    scene = {"background": "bg.png", "floor": "wood",
             "cast": {"Arthur": {"character": "a.blend", "position": [0, 0]},
                      "Thief": {"character": "a.blend", "position": [1.2, 0]}},
             "props": [], "script": [{"who": "Arthur", "do": "strike", "target": "Ghost", "clip": "punch"}]}
    (tmp_path / "bg.png").write_bytes(b"x")
    (tmp_path / "a.blend").write_bytes(b"x")
    (tmp_path / "scene.json").write_text(json.dumps(scene), encoding="utf-8")
    assert schema.check_scene(str(tmp_path)) >= 1
    out = capsys.readouterr().out
    assert '"target" must be a cast member' in out


def test_pose_fixes_are_checked_in_plain_language(tmp_path, capsys):
    scene = {"background": "bg.png", "floor": "wood",
             "cast": {"Arthur": {"character": "a.blend", "position": [0, 0]}},
             "props": [], "script": [{"do": "wait", "seconds": 1}],
             "fixes": [{"who": "Arthur", "part": "head", "at": 1.5, "rotate": [0, 0, 12]},
                       {"who": "Ghost", "part": "head", "at": 1.0, "rotate": [0, 0, 5]},
                       {"who": "Arthur", "part": "elbow", "at": 1.0, "rotate": [0, 0, 5]},
                       {"who": "Arthur", "part": "head", "at": -1, "rotate": "a lot"},
                       {"who": "Arthur", "part": "head", "at": 2.0, "rotate": [0, 0, 140]}]}
    (tmp_path / "bg.png").write_bytes(b"x")
    (tmp_path / "a.blend").write_bytes(b"x")
    (tmp_path / "scene.json").write_text(json.dumps(scene), encoding="utf-8")
    assert schema.check_scene(str(tmp_path)) == 4
    out = capsys.readouterr().out
    assert "'Ghost' is not in the cast" in out
    assert "unknown body part 'elbow'" in out
    assert '"at" must be a time in seconds' in out and '"rotate" must be [x, y, z] in degrees' in out
    assert "more than 90 degrees will look broken" in out        # a warning, not an error


def test_a_pose_fix_changes_the_render_key(tmp_path):
    base = {"background": "bg.png", "cast": {}, "script": []}
    fixed = {**base, "fixes": [{"who": "Arthur", "part": "head", "at": 1.0, "rotate": [0, 0, 10]}]}
    key = config.render_key(base, "blocking", str(tmp_path), schema.FINISH_KEYS)
    assert key != config.render_key(fixed, "blocking", str(tmp_path), schema.FINISH_KEYS)


def test_the_gemini_character_prompt_teaches_every_design_key():
    prompt = (Path(__file__).parent.parent / "docs" / "GEMINI_CHARACTER_PROMPT.md").read_text(encoding="utf-8")
    for key in schema.CHARACTER:
        assert key.split(".")[-1] in prompt, key       # a new look (a hood, a cape) must be taught here too
