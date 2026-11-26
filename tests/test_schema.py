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


def test_a_resized_part_must_say_where_and_how_much():
    good = dict(SANTA := {"gender": "male", "age": 60, "height_cm": 175})
    good["parts"] = [{"on": "hat", "at": [0.0, 0.1, 1.7], "radius": 0.08, "scale": 1.3}]
    assert schema.check_design(good) == []
    for broken, says in (
        ({"on": "hat", "radius": 0.08, "scale": 1.3}, "at"),
        ({"on": "hat", "at": [0, 0, 1.7], "scale": 1.3}, "radius"),
        ({"at": [0, 0, 1.7], "radius": 0.08, "scale": 1.3}, "on"),
    ):
        bad = dict(SANTA, parts=[broken])
        assert any("parts" in m and says in m for m in schema.check_design(bad)), broken


# --- controls: every number is a slider, every voice is a face ---------------------------------------------
# The app is meant to be played, not filled in. That only holds if the schema says what each number means,
# so these tests fail the moment a parameter arrives without a span the app can draw.
def _numbers(table, owner=None):
    """Every (where, name, param) that a person sets as a number."""
    for name, param in table.items():
        if isinstance(param, dict) and param.get("type") == "number":
            yield (f"{owner}.{name}" if owner else name), name, param


def all_numbers():
    served = schema.describe()
    for name, action in served["actions"].items():
        yield from _numbers(action["params"], name)
    for key in ("scene", "finish", "character"):
        yield from _numbers(served[key], key)


def test_every_number_a_person_sets_has_a_slider_span():
    missing = [where for where, _n, p_ in all_numbers() if "lo" not in p_]
    assert missing == [], f"no range for {missing}: add it to schema.RANGES or the app shows a bare text box"


def test_each_span_runs_upwards_and_can_be_stepped():
    for where, _name, p_ in all_numbers():
        assert p_["lo"] < p_["hi"], where
        assert p_["step"] > 0, where
        assert (p_["hi"] - p_["lo"]) / p_["step"] >= 4, f"{where} has fewer than 5 stops: a useless slider"
        assert isinstance(p_["unit"], str), where


def test_a_default_always_sits_inside_its_own_span():
    for where, _name, p_ in all_numbers():
        if "default" in p_:
            assert p_["lo"] <= p_["default"] <= p_["hi"], f"{where} starts outside its slider"


def test_an_action_can_mean_its_own_thing_by_a_shared_name():
    # a speaking speed and a motion clip's speed are both "speed" and are not the same control
    served = schema.describe()
    assert served["actions"]["say"]["params"]["speed"]["lo"] == 0.5
    assert served["actions"]["perform"]["params"]["speed"]["lo"] == 0.25


def test_ranges_are_only_added_and_the_vocabulary_is_untouched():
    # with_ranges must not invent, drop or rename anything: the vocabulary is still the vocabulary
    served = schema.describe()
    for name, action in schema.ACTIONS.items():
        assert set(served["actions"][name]["params"]) == set(action["params"]), name
        for key, was in action["params"].items():
            now = served["actions"][name]["params"][key]
            assert all(now[k] == v for k, v in was.items()), f"{name}.{key} changed"
    assert set(served["scene"]) == set(schema.SCENE_KEYS)
    assert "lo" not in schema.ACTIONS["wait"]["params"]["seconds"], "the table itself must stay clean"


def test_every_voice_is_taken_apart_so_the_app_can_group_them():
    assert set(schema.VOICE_FACTS) == set(schema.VOICES)
    for name, facts in schema.VOICE_FACTS.items():
        assert schema.VOICES[name] == f"{facts['language']}, {facts['gender']}"
        assert facts["person"] == name[3:] and facts["person"]
        assert len(facts["short"]) == 2
    # the gallery groups by language, so each language must have at least one of them
    assert len({f["language"] for f in schema.VOICE_FACTS.values()}) == len(schema._LANG)
    assert {f["gender"] for f in schema.VOICE_FACTS.values()} == {"female", "male"}


def test_a_clip_tells_you_how_long_it_is_and_an_unreadable_one_is_still_listed(tmp_path, monkeypatch):
    import json as _json
    monkeypatch.setattr(schema.config, "MOTIONS_DIR", str(tmp_path))
    (tmp_path / "punch.json").write_text(_json.dumps({"seconds": 15.447, "source": "cmu", "fps": 120.0}), encoding="utf-8")
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    facts = {c["name"]: c for c in schema.clip_facts()}
    assert facts["punch"] == {"name": "punch", "seconds": 15.45, "source": "cmu", "fps": 120}
    assert facts["broken"]["seconds"] is None      # you can still name it in a scene


# --- things a design may ask for that cannot both be built --------------------------------------------
# santa_2 asked for a one-piece suit AND a long coat, and for sneakers AND boots. The build made one of
# each pair, reported "problems": [], and produced a red onesie. Refusing is right; refusing in silence
# is what made it a bug nobody could trace.
SANTA = {"gender": "male", "age": 70, "height_cm": 178,
         "outfit": {"style": "suit", "shoe_style": "sneaker"},
         "costume": {"coat": "long", "boots": "#141414"}}


def test_a_one_piece_outfit_and_a_long_coat_cannot_both_be_built():
    said = schema.costume_clashes(SANTA)
    assert any("coat" in m and "suit" in m for m in said)
    assert any("Drop one of the two" in m for m in said)


def test_made_footwear_and_library_boots_cannot_both_be_built():
    assert any("boots" in m and "shoe_style" in m for m in schema.costume_clashes(SANTA))


def test_the_design_check_itself_refuses_them():
    # it is not enough for a helper to know: check_design is what the app and the CLI call
    problems = schema.check_design(SANTA)
    assert len([p_ for p_ in problems if "cannot both be built" in p_]) == 2


def test_each_half_on_its_own_is_perfectly_fine():
    coat_only = {**SANTA, "outfit": {"shoe_style": "sneaker"}}
    assert not any("coat" in m for m in schema.costume_clashes(coat_only))
    boots_only = {**SANTA, "outfit": {"style": "casual"}, "costume": {"boots": "#141414"}}
    assert not any("coat" in m for m in schema.costume_clashes(boots_only))
    assert schema.costume_clashes({"outfit": {"style": "casual"}, "costume": {"coat": "long"}}) == []


def test_every_one_piece_style_is_one_the_vocabulary_knows():
    allowed = schema.CHARACTER["outfit.style"]["values"]
    for style in schema.ONE_PIECE:
        assert style in allowed, style
    assert "casual" not in schema.ONE_PIECE, "casual is a top and trousers; a coat can continue its hem"


def test_a_design_that_asks_for_nothing_impossible_says_nothing():
    assert schema.costume_clashes({"outfit": {"style": "casual"}, "costume": {"trim": "#fff"}}) == []
    assert schema.costume_clashes("not a design") == []


def test_the_one_piece_list_is_the_same_list_the_build_uses():
    # a style that is one piece here and two pieces in the build would let the clash back in
    import re as _re
    from pathlib import Path as _Path
    src = (_Path(__file__).parent.parent / "blender" / "build_character.py").read_text(encoding="utf-8")
    block = _re.search(r"^STYLES = \{(.*?)^\}", src, _re.S | _re.M)
    assert block, "STYLES is not where it was in build_character.py"
    built = set(_re.findall(r'^\s*"([a-z_]+)":', block.group(1), _re.M))
    assert built == set(schema.ONE_PIECE), f"build makes {built}, schema calls {set(schema.ONE_PIECE)} one piece"


def test_socks_and_library_boots_do_not_go_together_either():
    # socks are cut for the bare foot and come through a boot; the boot covers them anyway
    said = schema.costume_clashes({"costume": {"boots": "#141414", "socks": "#ffffff"}})
    assert any("socks" in m and "boot" in m for m in said)
    assert schema.costume_clashes({"costume": {"socks": "#ffffff"}}) == []


# --- a scene on a built set ---------------------------------------------------------------------------
# Picking a built set and then being told the scene cannot render because of a background nobody uses is
# the kind of thing that makes an app feel broken. scene_kit replaces `background` from the set before
# anything is rendered, so a leftover one is not an error; it is not used.
def _set_folder(tmp_path, name="cabin"):
    sd = tmp_path / "sets" / name
    sd.mkdir(parents=True)
    (sd / "background.png").write_bytes(b"picture")
    (sd / "set_blueprint.json").write_text("{}", encoding="utf-8")
    (sd / "set.blend").write_bytes(b"blend")
    return sd


def test_a_leftover_background_does_not_stop_a_scene_that_is_on_a_built_set(tmp_path, capsys):
    _set_folder(tmp_path)
    scene = tmp_path / "ep"
    scene.mkdir()
    (scene / "scene.json").write_text(json.dumps({
        "set_folder": "../sets/cabin", "background": "cabin.png", "cast": {}, "script": []}),
        encoding="utf-8")
    assert schema.check_scene(str(scene)) == 0
    said = capsys.readouterr().out
    assert "NOTE:" in said and "cabin.png" in said, "it must still say the background is being ignored"


def test_a_missing_background_with_no_set_is_still_an_error(tmp_path, capsys):
    scene = tmp_path / "ep"
    scene.mkdir()
    (scene / "scene.json").write_text(json.dumps({"background": "cabin.png", "cast": {}, "script": []}),
                                      encoding="utf-8")
    assert schema.check_scene(str(scene)) == 1
    assert "background image not found" in capsys.readouterr().out


def test_a_set_folder_that_was_never_built_is_still_an_error(tmp_path, capsys):
    (tmp_path / "sets" / "half").mkdir(parents=True)
    scene = tmp_path / "ep"
    scene.mkdir()
    (scene / "scene.json").write_text(json.dumps({
        "set_folder": "../sets/half", "background": "gone.png", "cast": {}, "script": []}),
        encoding="utf-8")
    assert schema.check_scene(str(scene)) > 0
    said = capsys.readouterr().out
    assert "not a built set yet" in said or "background image not found" in said
