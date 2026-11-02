import asyncio
import io
import json
import wave
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image

from app import server


def test_movies_lists_nested_scene_directories(tmp_path, monkeypatch):
    movie = tmp_path / "film"
    nested_scene = movie / "act1" / "scenes" / "01_opening"
    nested_scene.mkdir(parents=True)
    (nested_scene / "scene.json").write_text("{}", encoding="utf-8")
    (movie / "characters" / "example").mkdir(parents=True)
    (movie / "characters" / "example" / "scene.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(server, "MOVIES", str(tmp_path))

    assert server.movies()[0]["episodes"] == ["act1/scenes/01_opening"]


def test_movies_lists_set_blueprint_and_generated_assets(tmp_path, monkeypatch):
    set_dir = tmp_path / "film" / "sets" / "cabin"
    set_dir.mkdir(parents=True)
    (set_dir / "z_background.png").write_bytes(b"image")
    (set_dir / "set_blueprint.json").write_text(
        json.dumps({"description": "Warm cabin", "props": []}), encoding="utf-8")
    (set_dir / "set.blend").write_bytes(b"blend")
    (set_dir / "set_preview.png").write_bytes(b"preview")
    monkeypatch.setattr(server, "MOVIES", str(tmp_path))

    result = server.movies()[0]["sets"][0]

    assert result["blueprint"] == {"version": 1, "description": "Warm cabin", "props": []}
    assert result["picture"].startswith("/media/film/sets/cabin/z_background.png?")
    assert result["asset"].startswith("/media/film/sets/cabin/set.blend?")
    assert result["preview"].startswith("/media/film/sets/cabin/set_preview.png?")


def test_build_library_building_saves_design_and_lists_shared_asset(tmp_path, monkeypatch):
    library = tmp_path / "library"
    monkeypatch.setattr(server, "LIBRARY", str(library))
    monkeypatch.setattr(server, "gpu_busy", lambda: None)
    monkeypatch.setattr(server, "start_library_building",
                        lambda category, name, folder: f"library/{category}/{name}/1")

    catalog = server.get_library_buildings()
    assert {template["id"] for template in catalog["templates"]} >= {
        "hut", "house", "row_house", "shop", "big_store", "shopping_mall",
        "hospital", "station", "police_station", "castle", "wrestling_arena",
        "roman_arena", "fighting_arena", "disco_arena", "hotel", "restaurant",
        "diner", "jail", "garden", "oak_tree", "pine_tree", "palm_tree",
        "car", "jeep", "truck", "helicopter", "airplane", "straight_road",
        "curved_road", "crossroads", "t_junction",
    }
    assert {category["id"] for category in catalog["categories"]} == {
        "buildings", "arenas", "landscapes", "trees", "vehicles", "roads",
    }

    result = server.build_library_building({
        "template": "hut", "name": "santa_hut", "width": 6, "depth": 5, "floors": 1,
        "height": 0, "wall_color": "#98704c", "roof_color": "#49382d",
    })
    folder = library / "buildings" / "santa_hut"
    spec = json.loads((folder / "building.json").read_text(encoding="utf-8"))
    assert result == {"job": "library/buildings/santa_hut/1"}
    assert spec == {"name": "santa_hut", "template": "hut", "family": "building", "category": "buildings",
                    "footprint": [6.0, 5.0], "floors": 1, "size": [6.0, 5.0, 0],
                    "wall_color": "#98704c", "roof_color": "#49382d"}

    (folder / "santa_hut.blend").write_bytes(b"blend")
    (folder / "preview.png").write_bytes(b"preview")
    listed = server.get_library_buildings()["assets"][0]
    assert listed["name"] == "santa_hut"
    assert listed["title"] == "Hut"
    assert listed["category"] == "buildings"
    assert listed["asset"].startswith("/library-media/buildings/santa_hut/santa_hut.blend?")
    assert listed["preview"].startswith("/library-media/buildings/santa_hut/preview.png?")


@pytest.mark.parametrize(("body", "message"), [
    ({"template": "not_a_building", "name": "hut", "width": 5, "depth": 4,
      "floors": 1, "wall_color": "#ffffff", "roof_color": "#000000"}, "supported starter"),
    ({"template": "hut", "name": "hut", "width": 0, "depth": 4,
      "floors": 1, "wall_color": "#ffffff", "roof_color": "#000000"}, "width and depth"),
    ({"template": "hut", "name": "hut", "width": 5, "depth": 4,
      "floors": 1.5, "wall_color": "#ffffff", "roof_color": "#000000"}, "whole number"),
    ({"template": "hut", "name": "hut", "width": 5, "depth": 4,
      "floors": 1, "wall_color": "white", "roof_color": "#000000"}, "six-digit hex"),
    ({"template": "helicopter", "name": "heli", "width": 5, "depth": 4, "height": float("inf"),
      "floors": 1, "wall_color": "#ffffff", "roof_color": "#000000"}, "height must be a finite number"),
])
def test_build_library_building_rejects_invalid_input(tmp_path, monkeypatch, body, message):
    monkeypatch.setattr(server, "LIBRARY", str(tmp_path / "library"))
    monkeypatch.setattr(server, "gpu_busy", lambda: None)

    with pytest.raises(HTTPException) as exc:
        server.build_library_building(body)

    assert exc.value.status_code == 400
    assert message in exc.value.detail


def test_build_library_vehicle_uses_vehicle_catalog_category(tmp_path, monkeypatch):
    library = tmp_path / "library"
    monkeypatch.setattr(server, "LIBRARY", str(library))
    monkeypatch.setattr(server, "gpu_busy", lambda: None)
    monkeypatch.setattr(server, "start_library_building",
                        lambda category, name, folder: f"library/{category}/{name}/1")

    result = server.build_library_building({
        "template": "helicopter", "name": "rescue_heli", "width": 3.2, "depth": 10,
        "height": 3.5, "floors": 1, "wall_color": "#64715b", "roof_color": "#303739",
    })

    spec = json.loads((library / "vehicles" / "rescue_heli" / "building.json").read_text(encoding="utf-8"))
    assert result == {"job": "library/vehicles/rescue_heli/1"}
    assert spec["family"] == "vehicle"
    assert spec["category"] == "vehicles"
    assert spec["size"] == [3.2, 10.0, 3.5]


def test_build_prop_saves_reference_and_design_and_lists_asset(tmp_path, monkeypatch):
    movie_dir = tmp_path / "film"
    movie_dir.mkdir()
    monkeypatch.setattr(server, "MOVIES", str(tmp_path))
    monkeypatch.setattr(server, "gpu_busy", lambda: None)
    monkeypatch.setattr(server, "start_prop_build", lambda movie, name, prop_dir: "film/prop/radio/1")
    image = io.BytesIO()
    Image.new("RGB", (16, 16), "brown").save(image, format="PNG")
    image.seek(0)

    result = asyncio.run(server.build_prop(
        movie="film", name="radio", make="car_radio", width=0.3, depth=0.2, height=0.15,
        material="wood", color="#804020",
        photo=UploadFile(filename="radio.png", file=image),
    ))

    prop_dir = movie_dir / "props" / "radio"
    spec = json.loads((prop_dir / "prop.json").read_text(encoding="utf-8"))
    assert result == {"job": "film/prop/radio/1"}
    assert spec == {"name": "radio", "make": "car_radio", "size": [0.3, 0.2, 0.15],
                    "material": "wood", "color": "#804020", "image": "reference.png"}
    assert Image.open(prop_dir / "reference.png").size == (16, 16)

    (prop_dir / "radio.blend").write_bytes(b"blend")
    (prop_dir / "preview.png").write_bytes(b"preview")
    listed = server.movies()[0]["props"][0]
    assert listed["name"] == "radio"
    assert listed["asset"].startswith("/media/film/props/radio/radio.blend?")
    assert listed["preview"].startswith("/media/film/props/radio/preview.png?")
    assert listed["picture"].startswith("/media/film/props/radio/reference.png?")


@pytest.mark.parametrize(("make", "width", "material", "color", "photo", "message"), [
    ("not_a_prop", 0.3, "wood", "#804020", b"image", "unknown or unsupported prop type"),
    ("car_radio", float("nan"), "wood", "#804020", b"image", "dimensions must be finite"),
    ("car_radio", 0.3, "not_a_material", "#804020", b"image", "unknown material"),
    ("car_radio", 0.3, "wood", "brown", b"image", "six-digit hex"),
    ("car_radio", 0.3, "wood", "#804020", b"not an image", "valid PNG"),
])
def test_build_prop_rejects_invalid_input(tmp_path, monkeypatch, make, width, material, color, photo, message):
    (tmp_path / "film").mkdir()
    monkeypatch.setattr(server, "MOVIES", str(tmp_path))
    monkeypatch.setattr(server, "gpu_busy", lambda: None)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.build_prop(
            movie="film", name="radio", make=make, width=width, depth=0.2, height=0.15,
            material=material, color=color,
            photo=UploadFile(filename="reference.png", file=io.BytesIO(photo)),
        ))

    assert exc.value.status_code == 400
    assert message in exc.value.detail


def test_movies_reports_corrupt_set_blueprint(tmp_path, monkeypatch):
    set_dir = tmp_path / "film" / "sets" / "cabin"
    set_dir.mkdir(parents=True)
    (set_dir / "background.png").write_bytes(b"image")
    (set_dir / "set_blueprint.json").write_text("{", encoding="utf-8")
    monkeypatch.setattr(server, "MOVIES", str(tmp_path))

    with pytest.raises(HTTPException) as exc:
        server.movies()

    assert exc.value.status_code == 500
    assert "invalid set blueprint" in exc.value.detail


def test_set_blueprint_save_and_build_use_user_details(tmp_path, monkeypatch):
    sets_dir = tmp_path / "film" / "sets"
    cabin, outside = sets_dir / "cabin", sets_dir / "outside"
    cabin.mkdir(parents=True)
    outside.mkdir()
    (cabin / "background.png").write_bytes(b"image")
    (outside / "background.png").write_bytes(b"image")
    monkeypatch.setattr(server, "MOVIES", str(tmp_path))
    monkeypatch.setattr(server, "gpu_busy", lambda: None)
    monkeypatch.setattr(server, "start_set_build", lambda movie, name, set_dir: "film/set/cabin/1")
    body = {"movie": "film", "set": "cabin", "blueprint": {"description": "Cozy",
            "props": [{"id": "door_1", "make": "door", "picture_rect": [0.2, 0.1, 0.4, 0.8],
                       "outside_set": "outside"}]}}

    saved = server.save_set(body)
    built = server.build_set(body)

    assert saved["blueprint"]["props"][0]["size"] == list(server.schema.PROP_TYPES["door"][0])
    assert built["job"] == "film/set/cabin/1"
    assert json.loads((cabin / "set_blueprint.json").read_text(encoding="utf-8")) == saved["blueprint"]


@pytest.mark.parametrize("prop", [
    {"id": "door_1", "make": "not_a_prop"},
    {"id": "door_1", "make": "door", "size": [0, 0.1, 2]},
    {"id": "door_1", "make": "door", "picture_rect": [0.7, 0.1, 0.2, 0.8]},
    {"id": "door_1", "make": "door", "outside_set": ["outside"]},
])
def test_set_blueprint_rejects_invalid_details(tmp_path, monkeypatch, prop):
    set_dir = tmp_path / "film" / "sets" / "cabin"
    set_dir.mkdir(parents=True)
    (set_dir / "background.png").write_bytes(b"image")
    monkeypatch.setattr(server, "MOVIES", str(tmp_path))

    with pytest.raises(HTTPException) as exc:
        server.save_set({"movie": "film", "set": "cabin", "blueprint": {"props": [prop]}})

    assert exc.value.status_code == 400


def test_episode_dir_accepts_nested_scene_path(tmp_path, monkeypatch):
    scene_dir = tmp_path / "film" / "act1" / "scenes" / "01_opening"
    scene_dir.mkdir(parents=True)
    (scene_dir / "scene.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(server, "MOVIES", str(tmp_path))

    assert Path(server.episode_dir("film", "act1/scenes/01_opening")) == scene_dir


def test_episode_dir_rejects_traversal(tmp_path, monkeypatch):
    (tmp_path / "film").mkdir()
    monkeypatch.setattr(server, "MOVIES", str(tmp_path))

    with pytest.raises(HTTPException) as exc:
        server.episode_dir("film", "../outside")

    assert exc.value.status_code == 400


def test_voice_upload_saves_audio_and_transcript(tmp_path, monkeypatch):
    scene_dir = tmp_path / "film" / "episode"
    (scene_dir / "voices").mkdir(parents=True)
    scene_path = scene_dir / "scene.json"
    scene_path.write_text(json.dumps({
        "script": [{"who": "Maya", "do": "say", "text": "Draft line"}],
    }), encoding="utf-8")
    monkeypatch.setattr(server, "MOVIES", str(tmp_path))

    audio = io.BytesIO()
    with wave.open(audio, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b"\x00\x00" * 24)
    audio.seek(0)
    upload = UploadFile(filename="performance.wav", file=audio)

    result = asyncio.run(server.upload_episode_voice(
        movie="film", episode="episode", step=0,
        text="A performed line.", file=upload, scene_index=None,
    ))
    saved = json.loads(scene_path.read_text(encoding="utf-8"))

    assert saved["script"][0]["audio"].startswith("voices/uploaded_000_")
    assert saved["script"][0]["audio"].endswith(".wav")
    assert saved["script"][0]["text"] == "A performed line."
    assert (scene_dir / saved["script"][0]["audio"]).is_file()
    assert result["ok"] is True


def test_voice_upload_rejects_non_wav(tmp_path, monkeypatch):
    scene_dir = tmp_path / "film" / "episode"
    scene_dir.mkdir(parents=True)
    (scene_dir / "scene.json").write_text('{"script":[{"do":"say"}]}', encoding="utf-8")
    monkeypatch.setattr(server, "MOVIES", str(tmp_path))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.upload_episode_voice(
            movie="film", episode="episode", step=0, text="Line",
            file=UploadFile(filename="performance.mp3", file=io.BytesIO(b"audio")),
            scene_index=None,
        ))

    assert exc.value.status_code == 400


def test_voice_upload_updates_selected_episode_scene(tmp_path, monkeypatch):
    scene_dir = tmp_path / "film" / "episode"
    scene_dir.mkdir(parents=True)
    scene_path = scene_dir / "scene.json"
    scene_path.write_text(json.dumps({
        "scenes": [
            {"id": "first", "script": []},
            {"id": "second", "script": [{"who": "Maya", "do": "say", "text": "Draft"}]},
        ],
    }), encoding="utf-8")
    monkeypatch.setattr(server, "MOVIES", str(tmp_path))

    audio = io.BytesIO()
    with wave.open(audio, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b"\x00\x00" * 24)
    audio.seek(0)

    asyncio.run(server.upload_episode_voice(
        movie="film", episode="episode", step=0, text="Performed",
        file=UploadFile(filename="performance.wav", file=audio), scene_index=1,
    ))
    saved = json.loads(scene_path.read_text(encoding="utf-8"))

    assert saved["scenes"][0]["script"] == []
    assert saved["scenes"][1]["script"][0]["text"] == "Performed"


def test_episode_reports_storyboard_and_downloads(tmp_path, monkeypatch):
    d = tmp_path / "film" / "ep"
    d.mkdir(parents=True)
    (d / "scene.json").write_text("{}", encoding="utf-8")
    for f in ("episode.mp4", "episode.srt", "storyboard.jpg"):
        (d / f).write_bytes(b"x")
    monkeypatch.setattr(server, "MOVIES", str(tmp_path))
    result = server.episode("film", "ep")
    assert result["storyboard"].startswith("/media/film/ep/storyboard.jpg")
    assert [x["name"] for x in result["downloads"]] == ["Video (MP4)", "Subtitles (SRT)"]


def test_episode_log_keeps_progress_lines(tmp_path, monkeypatch):
    d = tmp_path / "film" / "ep"
    d.mkdir(parents=True)
    (d / "scene.json").write_text("{}", encoding="utf-8")
    (d / "render.log").write_text("noise\nCF: scene 1/1 x\nFra:1 Mem\nCF: video episode.mp4\n", encoding="utf-8")
    monkeypatch.setattr(server, "MOVIES", str(tmp_path))
    assert server.episode_log("film", "ep")["log"] == "CF: scene 1/1 x\nCF: video episode.mp4"


def test_voice_preview_rejects_unknown_voices():
    with pytest.raises(HTTPException) as exc:
        server.voice_preview({"text": "Hello", "voice": "nobody"})
    assert exc.value.status_code == 400


def test_generated_scene_folders_are_not_listed_as_episodes(tmp_path, monkeypatch):
    ep = tmp_path / "film" / "ep"
    (ep / "scenes" / "01_cabin").mkdir(parents=True)
    (ep / "scene.json").write_text("{}", encoding="utf-8")
    (ep / "scenes" / "01_cabin" / "scene.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(server, "MOVIES", str(tmp_path))
    assert server.movies()[0]["episodes"] == ["ep"]
