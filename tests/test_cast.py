import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared import cast  # noqa: E402

NOVEL = os.path.join("suite", "graphic-novel")

# Two real characters out of the novel's own project.json, written by a person, not by a form.
MOSES = {"id": "char_0f6767f1", "name": "Moses", "tier": 1, "variant": "older", "trigger": "mosesfix",
         "appearance": "elderly man, long white beard, weathered face, coarse brown woollen robe "
                       "with hood, rope belt",
         "ref_images": ["char_0f6767f1/mosesfix_back_01.png", "char_0f6767f1/mosesfix_detail_03.png",
                        "char_0f6767f1/mosesfix_front_04.png", "char_0f6767f1/mosesfix_side_08.png",
                        "char_0f6767f1/mosesfix_three_quarter_11.png"]}

KALKI = {"id": "char_f597c1f5", "name": "Kalki", "tier": 1, "trigger": "kalki_hero",
         "appearance": "Photorealistic South Asian young man in his early 20s, athletic lean muscular "
                       "build, sharp jawline, intense focused dark eyes, short styled modern dark hair. "
                       "Wearing a sleek matte-charcoal technical compression suit.",
         "ref_images": ["char_f597c1f5/kalki_hero_three_quarter_26.png",
                        "char_f597c1f5/kalki_hero_back_35_00005_.png"]}

PROJECT = {"name": "Kalki is coming", "characters": [MOSES, KALKI]}
EVERYTHING = lambda _p: True            # noqa: E731


def read_project(_p):
    return PROJECT


# --- the turnaround ---------------------------------------------------------------------------------

def test_an_images_angle_is_read_from_its_name():
    assert cast.angle("char_x/mosesfix_three_quarter_11.png") == "three_quarter"
    assert cast.angle("char_x/mosesfix_front_04.png") == "front"
    assert cast.angle("char_x/kalki_hero_back_35_00005_.png") == "back"
    assert cast.angle("char_x/anything.png") is None


def test_three_quarter_is_never_mistaken_for_something_shorter():
    """'three_quarter' contains no other angle word, but the order of the table is what guarantees it."""
    assert cast.angle("a_three_quarter_front_1.png") == "three_quarter"


def test_the_figure_comes_from_a_front_shot_and_the_face_from_the_close_detail():
    body, face = cast.pick(MOSES["ref_images"])
    assert body.endswith("front_04.png")
    assert face.endswith("detail_03.png"), "a close detail is a better face than a full figure"


def test_a_character_with_no_front_shot_falls_back_to_the_three_quarter():
    body, face = cast.pick(KALKI["ref_images"])
    assert body.endswith("three_quarter_26.png") and face == body


def test_a_character_with_only_a_back_view_cannot_be_built():
    body, face = cast.pick(["x/a_back_01.png"])
    assert body is None and face is None


# --- reading what a person wrote --------------------------------------------------------------------

def test_it_reads_what_the_prose_plainly_says():
    design, said, missing = cast.read_appearance(MOSES["appearance"])
    assert design["gender"] == "male"
    assert design["age"] == 72, "elderly"
    assert design["beard"] == "long"
    assert design["hair"]["color"] == cast.COLOURS["white"]
    assert design["outfit"]["style"] == "robe"
    assert missing == ["build"], "the prose says nothing about his build, and that is reported"
    assert said, "it has to be able to show its working"


def test_a_colour_belongs_to_the_thing_it_sits_beside():
    """'long white beard, ... coarse brown woollen robe' - the robe must not make his beard brown."""
    design, _, _ = cast.read_appearance(MOSES["appearance"])
    assert design["hair"]["color"] == cast.COLOURS["white"]
    assert design["outfit"]["top"] == cast.COLOURS["brown"]


def test_a_hood_is_picked_up_as_a_hood():
    design, _, _ = cast.read_appearance(MOSES["appearance"])
    assert "hood" in design.get("costume", {})


def test_an_age_written_as_a_decade_is_understood():
    design, _, _ = cast.read_appearance(KALKI["appearance"])
    assert design["age"] == 22, "early 20s"
    assert design["build"] == "muscular"
    assert design["hair"]["length"] == "short"


def test_the_more_exact_phrase_wins_over_the_vaguer_one():
    """'young man in his early 20s' must be 22, not the 24 that a bare 'young' would give."""
    design, _, _ = cast.read_appearance("a young man in his early 20s")
    assert design["age"] == 22
    plain, _, _ = cast.read_appearance("a young man")
    assert plain["age"] == 24


def test_a_long_beard_is_not_merely_a_beard():
    assert cast.read_appearance("long white beard")[0]["beard"] == "long"
    assert cast.read_appearance("a full beard")[0]["beard"] == "full"
    assert cast.read_appearance("clean-shaven")[0]["beard"] == "none"


# --- three things the real cast caught that invented examples did not -------------------------------

def test_a_heavy_brow_is_a_face_and_not_a_heavy_build():
    """Hanuman: 'massive shoulders, heavy brow'. Reading 'heavy' as his figure made him fat in silence."""
    design, _, _ = cast.read_appearance("mature South Asian man with massive shoulders, heavy brow")
    assert design["build"] == "muscular", "the shoulders are what describe his figure"
    design2, _, _ = cast.read_appearance("a man of heavy build")
    assert design2["build"] == "heavy", "said about the body, it still counts"


def test_any_decade_is_read_not_only_the_ones_somebody_listed():
    """Vibhishana is 'in his early 50s', which a hand-written list of decades missed entirely."""
    assert cast.read_appearance("diplomat in his early 50s")[0]["age"] == 52
    assert cast.read_appearance("a woman in her late thirties")[0]["age"] == 38
    assert cast.read_appearance("in his 40s")[0]["age"] == 45


def test_a_war_horse_is_not_built_as_a_human_being():
    """Devadatta in the real novel is a cybernetic war-horse. MPFB makes human bodies; building one
    from this would produce something absurd without saying a word about it."""
    horse = {"name": "Devadatta", "ref_images": ["x/a_front_1.png"],
             "appearance": "majestic pure-white biomechanical cybernetic war-horse, muscular equine frame"}
    row = cast.one(horse, NOVEL)
    assert not row["person"] and not row["ready"]
    assert cast.command(row, "m") is None
    said = "\n".join(cast.check(NOVEL, [row], exists=EVERYTHING))
    assert "not a person" in said and "prop" in said


def test_a_man_nicknamed_after_an_animal_is_still_a_man():
    """Hanuman's face is described as an 'Italian Stallion' face. He is not a horse."""
    row = cast.one({"name": "Hanuman", "ref_images": ["x/a_front_1.png"],
                    "appearance": "mature man with a classically rugged 'Italian Stallion' face"}, NOVEL)
    assert row["person"] and row["ready"]


def test_prose_it_cannot_read_leaves_the_field_alone_rather_than_guessing():
    design, said, missing = cast.read_appearance("a figure wreathed in smoke")
    assert "beard" not in design and "build" not in design
    assert set(missing) == {"gender", "age", "build"}
    assert said == [], "nothing was read, and it does not pretend otherwise"


def test_empty_prose_does_not_fall_over():
    design, said, missing = cast.read_appearance("")
    assert design == {} and said == [] and len(missing) == 3


# --- one character, ready to build ------------------------------------------------------------------

def test_a_novel_character_becomes_a_castforge_character():
    row = cast.one(MOSES, NOVEL)
    assert row["name"] == "moses" and row["ready"]
    assert row["body"].endswith(os.path.join("refs", "char_0f6767f1", "mosesfix_front_04.png"))
    assert row["angles"] == ["back", "detail", "front", "side", "three_quarter"]


def test_the_whole_sentence_is_kept_so_nothing_is_lost_by_not_being_understood():
    row = cast.one(MOSES, NOVEL)
    assert row["design"]["from_novel"]["appearance"] == MOSES["appearance"]
    assert row["design"]["from_novel"]["trigger"] == "mosesfix", \
        "the trigger ties this build back to the LoRA the novel draws him with"


def test_every_assumption_is_declared_rather_than_buried():
    row = cast.one(MOSES, NOVEL)
    assert any("height" in a for a in row["assumed"])
    assert any("build" in a for a in row["assumed"]), "the prose did not say, so it must be flagged"
    assert row["design"]["height_cm"] == cast.HEIGHTS["male"]


def test_a_name_is_made_safe_for_a_folder():
    row = cast.one({"name": "Kripacharya the Master", "ref_images": ["a_front_1.png"]}, NOVEL)
    assert row["name"] == "kripacharya_the_master"


def test_a_character_already_built_says_so():
    assert cast.one(MOSES, NOVEL, movie_cast=["moses", "arthur"])["built"]
    assert not cast.one(MOSES, NOVEL, movie_cast=["arthur"])["built"]


# --- the command, and what is not ready -------------------------------------------------------------

def test_the_build_command_passes_the_figure_and_the_face_separately():
    said = cast.command(cast.one(MOSES, NOVEL), "santa_is_a_lie")
    assert "--face-photo" in said and "mosesfix_detail_03.png" in said
    assert "--design" in said and "moses.design.json" in said


def test_a_character_whose_only_photo_is_the_face_is_not_given_it_twice():
    said = cast.command(cast.one(KALKI, NOVEL), "kalki_is_coming")
    assert "--face-photo" not in said, "the same image twice tells CastForge nothing new"


def test_a_character_that_cannot_be_built_has_no_command_and_is_named():
    row = cast.one({"name": "Ghost", "ref_images": ["x/a_back_1.png"]}, NOVEL)
    assert cast.command(row, "m") is None
    said = "\n".join(cast.check(NOVEL, [row], exists=EVERYTHING))
    assert "Ghost" in said and "turnaround" in said


def test_the_whole_cast_comes_across_in_one_go():
    rows = cast.cast(NOVEL, read=read_project, exists=EVERYTHING)
    assert [r["name"] for r in rows] == ["moses", "kalki"]
    assert cast.check(NOVEL, rows, exists=EVERYTHING) == []
    assert cast.novel_name(NOVEL, read=read_project, exists=EVERYTHING) == "Kalki is coming"


def test_no_novel_installed_is_quiet_rather_than_an_error():
    assert cast.cast(NOVEL, read=read_project, exists=lambda _p: False) == []
    said = cast.check(NOVEL, [], exists=lambda _p: False)
    assert "design a cast first" in said[0]
