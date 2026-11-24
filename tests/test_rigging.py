import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core import rigging  # noqa: E402


def test_the_strongest_four_are_kept_and_share_all_of_the_pull():
    got = rigging.keep_strongest({"a": 0.5, "b": 0.3, "c": 0.1, "d": 0.06, "e": 0.04})
    assert set(got) == {"a", "b", "c", "d"}
    assert sum(got.values()) == 1
    assert got["a"] > got["b"] > got["c"] > got["d"]


def test_noise_weights_are_dropped_before_counting():
    got = rigging.keep_strongest({"a": 0.9, "b": 0.001, "c": 0.002})
    assert got == {"a": 1.0}                 # two hairs of weight are not attachments


def test_a_vertex_already_tidy_is_left_as_it_was():
    got = rigging.keep_strongest({"a": 0.6, "b": 0.4})
    assert got == {"a": 0.6, "b": 0.4}


def test_weights_are_normalised_even_when_they_were_short():
    got = rigging.keep_strongest({"a": 0.2, "b": 0.1})
    assert sum(got.values()) == 1 and got["a"] == 2 * got["b"]


def test_ties_are_settled_by_name_so_the_answer_never_wobbles():
    a = rigging.keep_strongest({"z": 0.25, "y": 0.25, "x": 0.25, "w": 0.25, "v": 0.25})
    b = rigging.keep_strongest({"v": 0.25, "w": 0.25, "x": 0.25, "y": 0.25, "z": 0.25})
    assert a == b and set(a) == {"v", "w", "x", "y"}


def test_a_vertex_with_nothing_but_noise_is_reported_as_a_stray():
    assert rigging.strays({1: {"a": 0.9}, 2: {"a": 0.001}, 3: {}}) == [2, 3]


def test_a_clean_rig_has_nothing_to_say_about_it():
    facts = {"bones": 1090, "deform": 209, "visemes": 15, "unweighted": 0, "over_four": 0,
             "unnormalised": 0, "missing": [], "spare_armatures": 0}
    assert rigging.problems(facts) == []
    assert rigging.verdict(facts).startswith("ready")


def test_every_defect_is_said_in_words_a_person_can_act_on():
    facts = {"bones": 900, "deform": 200, "visemes": 9, "unweighted": 16, "over_four": 2958,
             "unnormalised": 3, "missing": ["hand_ik.L"], "spare_armatures": 1}
    said = " ".join(rigging.problems(facts))
    for expect in ("hand_ik.L", "16", "2958", "9 of the 15"):
        assert expect in said, expect
    assert rigging.verdict(facts).startswith("5 thing(s)")


def test_a_spare_armature_is_not_a_fault():
    """Rigify keeps the metarig on purpose, to be able to generate the rig again."""
    clean = {"bones": 1090, "deform": 209, "visemes": 15, "unweighted": 0, "over_four": 0,
             "unnormalised": 0, "missing": [], "spare_armatures": 1}
    assert rigging.problems(clean) == []
