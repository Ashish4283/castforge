"""What an episode holds on disk, and what a sweep may take (core/housekeeping.py)."""
import pytest

from core import housekeeping as hk

# One scene of a real episode, with the sizes act1 actually has.
SCENE = [
    ("scenes/01_cabin/shot.mp4", 5_100_000),
    ("scenes/01_cabin/shot.wav", 17_000_000),
    ("scenes/01_cabin/shot.timeline.json", 4_000),
    ("scenes/01_cabin/scene.json", 5_000),
    ("scenes/01_cabin/shot.blend", 27_000_000),
    ("scenes/01_cabin/shot.blend1", 27_000_000),
    ("scenes/01_cabin/t.blend1", 27_000_000),
    ("scenes/01_cabin/episode.blend", 27_000_000),
    ("scenes/01_cabin/preview.glb", 30_000_000),
    ("scenes/01_cabin/preview.json", 18_000),
    ("scenes/01_cabin/set/set.obj", 4_000_000),
    ("episode.mp4", 6_700_000),
    ("check/check_01.png", 6_700_000),
    ("post/film.mp4", 22_000_000),
    ("real/cabin_1.mp4", 280_000),
]


def test_the_film_and_everything_that_made_it_are_never_swept():
    taken, _ = hk.sweep(SCENE, hk.DEAR)                 # the deepest sweep there is
    for safe in ("scenes/01_cabin/shot.mp4", "scenes/01_cabin/shot.wav", "scenes/01_cabin/scene.json",
                 "scenes/01_cabin/shot.timeline.json", "episode.mp4", "post/film.mp4",
                 "real/cabin_1.mp4"):
        assert safe not in taken, safe


def test_blender_backups_cost_nothing_to_lose_and_are_the_biggest_single_win():
    taken, freed = hk.sweep(SCENE, hk.SPARE)
    assert sorted(taken) == ["scenes/01_cabin/shot.blend1", "scenes/01_cabin/t.blend1"]
    assert freed == 54_000_000
    assert "scenes/01_cabin/shot.blend" not in taken, "a .blend is not a .blend1"


def test_a_deeper_sweep_takes_everything_shallower_as_well():
    spare, _ = hk.sweep(SCENE, hk.SPARE)
    cheap, _ = hk.sweep(SCENE, hk.CHEAP)
    dear, _ = hk.sweep(SCENE, hk.DEAR)
    assert set(spare) < set(cheap) < set(dear)
    assert "scenes/01_cabin/preview.glb" in cheap and "scenes/01_cabin/preview.glb" not in spare
    assert "scenes/01_cabin/shot.blend" in dear and "scenes/01_cabin/shot.blend" not in cheap


def test_the_scene_files_only_go_when_they_are_asked_for_by_name():
    # getting them back is a full re-render; a tidy-up must never take them by accident
    for how_far in (hk.SPARE, hk.CHEAP):
        taken, _ = hk.sweep(SCENE, how_far)
        assert "scenes/01_cabin/shot.blend" not in taken
        assert "scenes/01_cabin/episode.blend" not in taken


def test_a_survey_says_what_each_kind_costs_and_what_brings_it_back():
    got = hk.survey(SCENE)
    assert got["total"] == sum(size for _n, size in SCENE)
    by = {r["name"]: r for r in got["kinds"]}
    assert by["Blender backups"]["bytes"] == 54_000_000
    assert by["Blender backups"]["files"] == 2
    assert "nothing reads them" in by["Blender backups"]["back"]
    assert "re-render" in by["scene files"]["back"]
    assert got["kinds"] == sorted(got["kinds"], key=lambda r: -r["bytes"]), "biggest first"


def test_each_depth_says_what_it_would_free_including_the_ones_above_it():
    got = hk.survey(SCENE)
    assert got["spare"] == hk.sweep(SCENE, hk.SPARE)[1]
    assert got["cheap"] == hk.sweep(SCENE, hk.CHEAP)[1]
    assert got["dear"] == hk.sweep(SCENE, hk.DEAR)[1]
    assert got["spare"] < got["cheap"] < got["dear"] < got["total"]


def test_a_folder_pattern_takes_what_is_inside_it_and_nothing_that_merely_sounds_like_it():
    taken, _ = hk.sweep([("check/a.png", 1), ("checkpoint.txt", 1), ("scenes/01/set/set.obj", 1),
                         ("settings.json", 1)], hk.DEAR)
    assert sorted(taken) == ["check/a.png", "scenes/01/set/set.obj"]


def test_an_unknown_file_is_left_alone_rather_than_guessed_about():
    assert hk.group_of("something_nobody_listed.dat") is None
    assert hk.sweep([("something_nobody_listed.dat", 99)], hk.DEAR) == ([], 0)


def test_asking_for_a_depth_that_does_not_exist_says_so():
    with pytest.raises(ValueError, match="how far"):
        hk.sweep(SCENE, "everything")


def test_sizes_are_written_the_way_a_person_reads_them():
    assert hk.in_words(900) == "900 B"
    assert hk.in_words(54_000_000) == "51.5 MB"
    assert hk.in_words(1_900_000_000) == "1.8 GB"


def test_the_listing_is_relative_to_the_episode_and_survives_a_file_vanishing():
    tree = {"ep": (["scenes"], ["episode.mp4"]), "ep/scenes": ([], ["shot.mp4", "gone.tmp"])}

    def walk(folder):
        for root, (dirs, files) in tree.items():
            yield root.replace("/", "\\") if "\\" in folder else root, dirs, files

    def size(path):
        if path.endswith("gone.tmp"):
            raise OSError("it went away while we looked")
        return 10

    got = hk.listing("ep", walk=walk, size=size)
    assert ("episode.mp4", 10) in got
    assert all("gone.tmp" not in name for name, _s in got)
