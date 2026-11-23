"""A set built once and used by many scenes: what a scene inherits and what it may change."""
import json
import os

import pytest

from core import sets


def make_set(tmp_path, props, image="background.png"):
    folder = tmp_path / "cabin"
    folder.mkdir()
    (folder / image).write_bytes(b"png")
    (folder / sets.BLUEPRINT).write_text(json.dumps({"version": 1, "description": "a cabin",
                                                     "props": props}), encoding="utf-8")
    return str(folder)


def test_a_set_folder_is_a_picture_and_a_blueprint(tmp_path):
    folder = make_set(tmp_path, [{"id": "table", "make": "table"}])
    assert sets.is_set_folder(folder)
    assert os.path.basename(sets.picture(folder)) == "background.png"
    assert not sets.is_set_folder(str(tmp_path))                 # a plain folder is not a set


def test_the_built_preview_is_never_mistaken_for_the_set_picture(tmp_path):
    folder = make_set(tmp_path, [])
    open(os.path.join(folder, "set_preview.png"), "wb").write(b"png")
    assert os.path.basename(sets.picture(folder)) == "background.png"


def test_a_broken_blueprint_leaves_the_scene_working(tmp_path):
    folder = make_set(tmp_path, [])
    open(os.path.join(folder, sets.BLUEPRINT), "w").write("{not json")
    assert sets.read_blueprint(folder)["props"] == []
    assert sets.read_blueprint(str(tmp_path / "nowhere"))["props"] == []


def test_a_scene_inherits_the_sets_objects(tmp_path):
    folder = make_set(tmp_path, [{"id": "table", "make": "table"}, {"id": "lamp", "make": "lantern"}])
    merged = sets.merge_props(sets.read_blueprint(folder)["props"], None)
    assert [p["id"] for p in merged] == ["table", "lamp"]
    assert all(p["from_set"] for p in merged)


def test_a_scene_can_move_a_set_object_without_redescribing_it():
    set_props = [{"id": "lamp", "make": "lantern", "position": [1.0, 0.0]}]
    merged = sets.merge_props(set_props, [{"id": "lamp", "position": [2.5, 1.0]}])
    assert len(merged) == 1                                      # moved in place, not added twice
    lamp = merged[0]
    assert lamp["make"] == "lantern" and lamp["position"] == [2.5, 1.0]
    assert lamp["from_set"] and lamp["edited"]


def test_the_scenes_own_props_come_after_the_sets():
    merged = sets.merge_props([{"id": "table", "make": "table"}], [{"id": "crate", "make": "box"}])
    assert [p["id"] for p in merged] == ["table", "crate"]
    assert merged[1].get("from_set") is None                     # a scene prop stays the scene's
    assert sets.merge_props(None, None) == []


def test_junk_entries_cannot_break_a_merge():
    merged = sets.merge_props([{"no_id": 1}, "nonsense", {"id": "ok", "make": "box"}], ["bad", {"id": "x"}])
    assert [p["id"] for p in merged] == ["ok", "x"]


def test_set_files_are_read_from_the_set_not_the_scene():
    [prop] = sets.resolve_paths([{"id": "stove", "file": "models/stove.blend"}], os.path.join("C", "cabin"))
    assert prop["file"] == os.path.join("C", "cabin", "models", "stove.blend")
    [kept] = sets.resolve_paths([{"id": "a", "file": os.path.abspath("x.blend")}], "C")
    assert kept["file"] == os.path.abspath("x.blend")            # an absolute path is left alone


def test_geometry_is_shared_by_every_scene_on_the_set(tmp_path):
    folder = make_set(tmp_path, [])
    assert sets.geometry_dir(folder).endswith(sets.GEOMETRY_DIR)
    assert sets.needs_geometry(folder, sets.picture(folder))      # nothing built yet
    os.makedirs(sets.geometry_dir(folder))
    for name in ("set.json", "set.obj"):
        open(os.path.join(sets.geometry_dir(folder), name), "w").write("{}")
    assert not sets.needs_geometry(folder, sets.picture(folder))


def test_a_set_can_carry_an_empty_version_of_its_picture(tmp_path):
    folder = tmp_path / "cabin"
    folder.mkdir()
    (folder / "cabin.png").write_bytes(b"x")
    (folder / "set_blueprint.json").write_text(json.dumps({"props": []}), encoding="utf-8")
    assert sets.empty_picture(str(folder)) is None             # until one is made
    (folder / sets.EMPTY).write_bytes(b"x")
    assert sets.empty_picture(str(folder)) == os.path.join(str(folder), sets.EMPTY)
    assert sets.picture(str(folder)) == os.path.join(str(folder), "cabin.png")   # the original is still there


def test_a_set_can_name_an_empty_version_made_elsewhere(tmp_path):
    folder = tmp_path / "cabin"
    folder.mkdir()
    (folder / "room.png").write_bytes(b"x")
    (folder / "cleared.png").write_bytes(b"x")
    blueprint = {"image": "room.png", "empty_image": "cleared.png", "props": []}
    (folder / "set_blueprint.json").write_text(json.dumps(blueprint), encoding="utf-8")
    assert sets.empty_picture(str(folder), blueprint) == os.path.join(str(folder), "cleared.png")


def _set_folder(tmp_path, props, empty=False, scene_image="room.png"):
    folder = tmp_path / "cabin"
    folder.mkdir(exist_ok=True)
    (folder / scene_image).write_bytes(b"x")
    if empty:
        (folder / sets.EMPTY).write_bytes(b"x")
    (folder / "set_blueprint.json").write_text(json.dumps({"props": props}), encoding="utf-8")
    return str(folder)


def test_a_scene_on_a_set_gets_its_picture_its_objects_and_a_line_to_log(tmp_path):
    folder = _set_folder(tmp_path, [{"id": "set_table", "make": "table", "position": [1, 0]}])
    background, props, note = sets.use_set(folder, {"props": [{"id": "own_barrel", "make": "barrel"}]})
    assert background == os.path.join(folder, "room.png")
    assert [p["id"] for p in props] == ["set_table", "own_barrel"]
    assert props[0]["from_set"] and "from_set" not in props[1]
    assert note == "set cabin: 1 object(s) from the set, 2 in all"


def test_a_scene_on_an_emptied_set_stands_in_the_empty_room(tmp_path):
    folder = _set_folder(tmp_path, [], empty=True)
    background, _, note = sets.use_set(folder, {})
    assert background == os.path.join(folder, sets.EMPTY) and "in the empty room" in note


def test_a_scene_keeps_a_background_of_its_own(tmp_path):
    folder = _set_folder(tmp_path, [], empty=True)
    background, _, note = sets.use_set(folder, {"background": "my_own.png"})
    assert background == "my_own.png" and "empty room" not in note


def test_a_set_without_a_picture_is_refused(tmp_path):
    folder = tmp_path / "empty_set"
    folder.mkdir()
    (folder / "set_blueprint.json").write_text(json.dumps({"props": []}), encoding="utf-8")
    with pytest.raises(ValueError):
        sets.use_set(str(folder), {})
