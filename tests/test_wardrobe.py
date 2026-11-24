import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core import wardrobe  # noqa: E402


def a_piece(**over):
    piece = wardrobe.blank("My long coat", "male_casualsuit01", "clothes", "outfit")
    piece["edits"] = [{"seed": 120, "radius": 0.08, "scale": 1.4}]
    piece.update(over)
    return piece


def test_a_name_becomes_a_file_safe_id():
    assert wardrobe.piece_id("My Long Coat!") == "my_long_coat"
    assert wardrobe.piece_id("  --  ") == ""
    assert len(wardrobe.piece_id("x" * 90)) == 48


def test_a_piece_someone_just_named_is_valid_and_unchanged():
    piece = wardrobe.blank("Santa cap, mine", "joepal_xmas_cap", "clothes", "hat")
    assert wardrobe.check(piece) == []
    assert piece["id"] == "santa_cap_mine" and piece["edits"] == []
    assert wardrobe.describe(piece) == "as it comes"


def test_a_piece_must_say_what_it_is_cut_from_and_where_it_is_worn():
    assert any("name" in p for p in wardrobe.check(a_piece(name=" ")))
    assert any("role" in p for p in wardrobe.check(a_piece(role="elbow")))
    assert any("base" in p for p in wardrobe.check(a_piece(base="")))
    assert any("wardrobe has" in p for p in wardrobe.check(a_piece(), known={"something_else"}))
    assert wardrobe.check(a_piece(), known={"male_casualsuit01"}) == []


def test_an_edit_is_held_to_sane_limits():
    assert wardrobe.check(a_piece(edits=[{"seed": 1, "radius": 9.0, "scale": 1.2}]))
    assert wardrobe.check(a_piece(edits=[{"seed": 1, "radius": 0.08, "scale": 99}]))
    assert wardrobe.check(a_piece(edits=[{"seed": -2, "radius": 0.08, "scale": 1.2}]))
    assert wardrobe.check(a_piece(edits=[{"seed": 1, "radius": 0.08, "move": [0, 0]}]))
    assert wardrobe.check(a_piece(edits=[{"seed": 1, "radius": 0.08, "turn": [0, 0, 400]}]))
    assert wardrobe.check(a_piece(edits=[{"seed": 1, "radius": 0.08, "scale": 1.2,
                                          "move": [0.1, 0, 0], "turn": [0, -20, 0]}])) == []


def test_a_seed_that_is_a_boolean_is_not_a_vertex():
    assert wardrobe.check(a_piece(edits=[{"seed": True, "radius": 0.08, "scale": 1.2}]))


def test_a_piece_cannot_grow_without_limit():
    many = [{"seed": i, "radius": 0.05, "scale": 1.1} for i in range(wardrobe.MOST_EDITS + 1)]
    assert any("edits" in p for p in wardrobe.check(a_piece(edits=many)))


def test_a_design_slot_says_which_piece_it_wants():
    piece = a_piece()
    assert wardrobe.slot(piece) == "piece:my_long_coat"
    assert wardrobe.named("piece:my_long_coat") == "my_long_coat"
    assert wardrobe.named("piece:My Long Coat") == "my_long_coat"   # tidied the same way
    assert wardrobe.named("santa") is None and wardrobe.named(None) is None
    assert wardrobe.named("piece:") is None


def test_a_colour_is_a_colour_or_nothing():
    assert wardrobe.check(a_piece(colour=None), known=None) == []
    assert wardrobe.check(a_piece(colour="#a3161a")) == []
    assert wardrobe.check(a_piece(colour="red"))


def test_what_was_done_to_a_piece_is_said_in_words():
    said = wardrobe.describe(a_piece(edits=[{"seed": 1, "radius": 0.08, "scale": 1.4},
                                            {"seed": 2, "radius": 0.05, "turn": [0, 30, 0]}]))
    assert "2 edits" in said and "x1.40" in said and "turned" in said
