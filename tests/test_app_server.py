import asyncio
import io
import json
import wave
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile

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
