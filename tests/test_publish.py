import json
import subprocess

import pytest

from core import config, publish


def test_the_title_card_chapter_folds_into_the_first_scene():
    chapters = [(0.0, 4.0, "Santa is a Lie"), (4.0, 40.0, "Cabin"), (40.0, 80.0, "Shop"), (80.0, 120.0, "Road")]
    folded = publish.fold_chapters(chapters)
    assert folded == [(0.0, 40.0, "Cabin"), (40.0, 80.0, "Shop"), (80.0, 120.0, "Road")]


def test_short_credits_fold_into_the_previous_chapter_and_the_list_starts_at_zero():
    chapters = [(2.0, 30.0, "One"), (30.0, 60.0, "Two"), (60.0, 64.0, "Credits")]
    folded = publish.fold_chapters(chapters)
    assert folded == [(0.0, 30.0, "One"), (30.0, 64.0, "Two")]
    assert publish.fold_chapters([]) == []


def test_chapter_lines_read_back(tmp_path):
    folder = tmp_path
    (folder / "episode_chapters.txt").write_text("0:00 Cabin\n0:40 Shop\n1:20 Road\n", encoding="utf-8")
    rows = publish.read_chapters(str(folder))     # no episode.mp4: the last chapter gets a nominal end
    assert [r[0] for r in rows] == [0, 40, 80]
    assert rows[0][1] == 40 and rows[-1][2] == "Road"


def test_srt_end_reads_the_last_cue(tmp_path):
    srt = tmp_path / "episode.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:03,500\nHi\n\n2\n00:01:00,000 --> 00:01:02,250\nBye\n",
                   encoding="utf-8")
    assert publish.srt_end(str(srt)) == 62.25


@pytest.fixture(scope="module")
def film(tmp_path_factory):
    """A real 2-second episode.mp4 (h264 + aac) with a title and chapters, as finish() would leave it."""
    folder = tmp_path_factory.mktemp("episode")
    subprocess.run([config.FFMPEG, "-y", "-f", "lavfi", "-i", "color=c=darkred:s=640x360:r=24:d=2",
                    "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000:d=2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                    str(folder / "episode.mp4")], check=True, capture_output=True)
    (folder / "scene.json").write_text(json.dumps({"title": {"text": "Test Film"}}), encoding="utf-8")
    (folder / "episode_chapters.txt").write_text("0:00 One\n", encoding="utf-8")
    return folder


def test_check_episode_reports_in_plain_language(film):
    checks = dict((m.split(":")[0], (level, m)) for level, m in publish.check_episode(str(film)))
    assert checks["picture"][0] == "ok" and "640x360" in checks["picture"][1]
    assert checks["sound"][0] == "ok"
    assert "LUFS" in checks["loudness"][1]
    assert any("render at standard or final" in m for _, m in publish.check_episode(str(film)))


def test_package_writes_the_platform_files_and_masters_the_sound(film):
    lines = []
    problems = publish.package(str(film), "youtube", log=lambda *a: lines.append(" ".join(map(str, a))))
    assert problems == 0
    pub = film / "publish"
    assert (pub / "episode_youtube.mp4").exists() and (pub / "thumbnail.jpg").exists()
    assert (pub / "report.txt").exists()
    assert "Test Film" in (pub / "description.txt").read_text(encoding="utf-8")
    assert not (pub / "chapters.txt").exists()            # one chapter: YouTube needs three, so left out
    assert any("chapters: left out" in ln for ln in lines)
    from PIL import Image
    assert Image.open(pub / "thumbnail.jpg").size == (1280, 720)
    info = publish.probe(str(pub / "episode_youtube.mp4"))
    assert info["video"]["codec"] == "h264" and info["audio"]["codec"] == "aac"
    assert info["audio"]["rate"] == 48000


def test_missing_film_is_one_plain_problem(tmp_path):
    assert publish.package(str(tmp_path), log=lambda *a: None) == 1
    checks = publish.check_episode(str(tmp_path))
    assert checks == [("fix", "no episode.mp4 yet: render and finish the episode first")]
