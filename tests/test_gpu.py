import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core import gpu  # noqa: E402

NOTHING = {"local_comfy": False, "local_vram": 4.0, "kaggle_cli": False, "kaggle_auth": False}
KAGGLE = {**NOTHING, "kaggle_cli": True, "kaggle_auth": True}
SMALL_LOCAL = {**KAGGLE, "local_comfy": True, "local_vram": 4.0}
BIG_LOCAL = {**KAGGLE, "local_comfy": True, "local_vram": 24.0}


def test_there_are_exactly_two_places_and_both_are_described():
    for place in gpu.PLACES:
        said = gpu.look(NOTHING)[place]
        assert said["why"] and said["how"], place


# --- what is wrong, and what to do about it --------------------------------------------------------------

def test_a_laptop_with_no_comfyui_says_so_and_says_what_to_do():
    said = gpu.look(NOTHING)["local"]
    assert not said["ready"] and str(gpu.LOCAL_PORT) in said["why"]
    assert "kaggle" in said["how"]


def test_not_signed_in_to_kaggle_gives_the_exact_command():
    said = gpu.look({**NOTHING, "kaggle_cli": True})["kaggle"]
    assert not said["ready"] and "kaggle auth login" in said["how"]
    assert "nothing is typed here" in said["how"], "a person should know no secret is being asked for"


def test_the_kaggle_package_missing_is_told_apart_from_not_being_signed_in():
    no_pkg = gpu.look(NOTHING)["kaggle"]
    no_auth = gpu.look({**NOTHING, "kaggle_cli": True})["kaggle"]
    assert "pip install" in no_pkg["how"] and "pip install" not in no_auth["how"]


def test_a_small_card_is_usable_and_said_to_be_tight():
    said = gpu.look(SMALL_LOCAL)["local"]
    assert said["ready"], "a small card still works; it is just slow"
    assert "tight" in said["why"] and "slow" in said["how"]


def test_a_big_card_is_simply_ready():
    said = gpu.look(BIG_LOCAL)["local"]
    assert said["ready"] and "tight" not in said["why"]


# --- choosing ---------------------------------------------------------------------------------------------

def test_a_capable_local_card_is_preferred_because_it_costs_nothing():
    assert gpu.best(BIG_LOCAL) == "local"


def test_a_tight_local_card_loses_to_a_rented_one():
    """4 GB will run SDXL and take minutes doing it. 15 GB is there for free."""
    assert gpu.best(SMALL_LOCAL) == "kaggle"


def test_kaggle_is_used_when_there_is_nothing_here():
    assert gpu.best(KAGGLE) == "kaggle"


def test_with_nothing_at_all_it_still_names_somewhere_rather_than_failing():
    assert gpu.best(NOTHING) in gpu.PLACES
    assert gpu.best({}) in gpu.PLACES


def test_a_tight_local_card_is_still_used_when_kaggle_is_not_signed_in():
    assert gpu.best({**SMALL_LOCAL, "kaggle_auth": False}) == "local"


# --- using one --------------------------------------------------------------------------------------------

def test_a_place_that_is_ready_has_nothing_to_say_against_it():
    assert gpu.check("kaggle", KAGGLE) == []
    assert gpu.check("local", BIG_LOCAL) == []


def test_a_place_that_is_not_ready_says_why_and_how_in_one_line():
    said = gpu.check("kaggle", NOTHING)
    assert len(said) == 1 and "pip install" in said[0]


def test_somewhere_that_does_not_exist_is_refused():
    assert gpu.check("the-cloud", KAGGLE)


def test_it_reads_as_a_menu_with_the_chosen_one_marked():
    rows = gpu.describe(SMALL_LOCAL, chosen="kaggle")
    whole = "\n".join(rows)
    assert "local" in whole and "kaggle" in whole
    assert [r for r in rows if r.startswith(">")][0].lstrip("> ").startswith("kaggle")
    assert "not ready" not in whole, "both are usable here"


def test_the_menu_tells_you_how_to_fix_whatever_is_not_ready():
    whole = "\n".join(gpu.describe(NOTHING))
    assert "not ready" in whole and "pip install" in whole
