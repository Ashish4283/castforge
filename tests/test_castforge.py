import json
from pathlib import Path

import castforge
import pytest


def write_scene(folder: Path, scene: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "scene.json").write_text(json.dumps(scene), encoding="utf-8")


def test_missing_scene_reports_plain_error(tmp_path, capsys):
    assert castforge.check_scene(str(tmp_path)) == 1
    assert "ERROR: no scene.json" in capsys.readouterr().out


def test_invalid_json_reports_location(tmp_path, capsys):
    (tmp_path / "scene.json").write_text('{"background": }', encoding="utf-8")

    assert castforge.check_scene(str(tmp_path)) == 1
    assert "scene.json is not valid JSON at line 1" in capsys.readouterr().out


def test_valid_minimal_scene_passes(tmp_path, capsys):
    (tmp_path / "background.png").write_bytes(b"test")
    write_scene(tmp_path, {"background": "background.png", "cast": {}, "script": []})

    assert castforge.check_scene(str(tmp_path)) == 0
    assert capsys.readouterr().out.strip() == "scene.json looks good"


def test_missing_required_fields_are_reported(tmp_path, capsys):
    write_scene(tmp_path, {})

    assert castforge.check_scene(str(tmp_path)) == 3
    output = capsys.readouterr().out
    assert 'missing "background"' in output
    assert 'missing "cast"' in output
    assert 'missing "script"' in output


def test_render_start_uses_an_exclusive_lock_to_prevent_double_launch(tmp_path, monkeypatch):
    lock = tmp_path / ".render.lock"
    monkeypatch.setattr(castforge, "LOCK", str(lock))
    monkeypatch.setattr(castforge, "render_status", lambda folder: None)
    monkeypatch.setattr(castforge, "render_lock_owner", lambda: None)
    launches = []

    class Process:
        pid = 12345

    monkeypatch.setattr(castforge.subprocess, "Popen", lambda *args, **kwargs: launches.append(args) or Process())
    castforge.start_job(str(tmp_path), [], wait=False)

    assert lock.read_text(encoding="utf-8").splitlines() == ["12345", str(tmp_path)]
    with pytest.raises(SystemExit, match="another render is running"):
        castforge.start_job(str(tmp_path / "second"), [], wait=False)
    assert len(launches) == 1


def test_unknown_voice_is_reported(tmp_path, capsys):
    (tmp_path / "background.png").write_bytes(b"test")
    (tmp_path / "maya.blend").write_bytes(b"test")
    write_scene(tmp_path, {
        "background": "background.png",
        "cast": {"maya": {"character": "maya.blend", "voice": "not_a_voice"}},
        "script": [],
    })

    assert castforge.check_scene(str(tmp_path)) == 1
    assert "unknown voice not_a_voice" in capsys.readouterr().out


def test_say_requires_text_or_audio(tmp_path, capsys):
    (tmp_path / "background.png").write_bytes(b"test")
    (tmp_path / "maya.blend").write_bytes(b"test")
    write_scene(tmp_path, {
        "background": "background.png",
        "cast": {"maya": {"character": "maya.blend"}},
        "script": [{"who": "maya", "do": "say"}],
    })

    assert castforge.check_scene(str(tmp_path)) == 1
    assert 'say needs "text" or "audio"' in capsys.readouterr().out


def test_recorded_dialogue_does_not_require_a_tts_voice(tmp_path, capsys):
    (tmp_path / "background.png").write_bytes(b"test")
    (tmp_path / "maya.blend").write_bytes(b"test")
    (tmp_path / "line.wav").write_bytes(b"test")
    write_scene(tmp_path, {
        "background": "background.png",
        "cast": {"maya": {"character": "maya.blend"}},
        "script": [{"who": "maya", "do": "say", "audio": "line.wav", "text": "Hello."}],
    })

    assert castforge.check_scene(str(tmp_path)) == 0
    assert capsys.readouterr().out.strip() == "scene.json looks good"


def test_unknown_action_is_reported(tmp_path, capsys):
    (tmp_path / "background.png").write_bytes(b"test")
    write_scene(tmp_path, {
        "background": "background.png",
        "cast": {},
        "script": [{"do": "explode"}],
    })

    assert castforge.check_scene(str(tmp_path)) == 1
    assert "unknown action 'explode'" in capsys.readouterr().out


def test_open_action_requires_a_door_prop(tmp_path, capsys):
    (tmp_path / "background.png").write_bytes(b"test")
    (tmp_path / "arthur.blend").write_bytes(b"test")
    write_scene(tmp_path, {
        "background": "background.png",
        "cast": {"Arthur": {"character": "arthur.blend"}},
        "props": [{"id": "truck_door", "make": "door"}],
        "script": [{"who": "Arthur", "do": "open", "door": "truck_door"}],
    })

    assert castforge.check_scene(str(tmp_path)) == 0
    assert capsys.readouterr().out.strip() == "scene.json looks good"


def test_open_action_rejects_non_door_prop(tmp_path, capsys):
    (tmp_path / "background.png").write_bytes(b"test")
    (tmp_path / "arthur.blend").write_bytes(b"test")
    write_scene(tmp_path, {
        "background": "background.png",
        "cast": {"Arthur": {"character": "arthur.blend"}},
        "props": [{"id": "table", "make": "table"}],
        "script": [{"who": "Arthur", "do": "open", "door": "table"}],
    })

    assert castforge.check_scene(str(tmp_path)) == 1
    assert 'open needs "door"' in capsys.readouterr().out


def test_gemini_prompt_extracts_scene_prompt():
    prompt = castforge.gemini_prompt("scene")
    assert prompt.startswith("You write scene files for CastForge")
    assert "Scene idea: <WRITE YOUR IDEA HERE>" in prompt
