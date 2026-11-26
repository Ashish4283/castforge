import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared import suite  # noqa: E402

EVERYTHING = lambda _p: True            # noqa: E731 - a machine where all of it is installed
NOTHING = lambda _p: False              # noqa: E731 - a fresh machine


def test_the_three_tools_are_named_with_a_port_and_a_folder_each():
    assert set(suite.TOOLS) == {"castforge", "forgefilms", "graphic-novel"}
    ports = [t["port"] for t in suite.TOOLS.values()]
    assert len(set(ports)) == 3, "two tools on one port would fight"
    for name, tool in suite.TOOLS.items():
        assert tool["does"] and os.path.isabs(tool["folder"]), name


def test_castforge_is_the_suites_own_home_and_the_others_sit_under_it():
    here = suite.TOOLS["castforge"]["folder"]
    for name in ("forgefilms", "graphic-novel"):
        assert suite.TOOLS[name]["folder"].startswith(here), name


# --- where things are, and being told otherwise -----------------------------------------------------

def test_the_model_library_can_be_moved_by_saying_so(monkeypatch):
    """One of these machines is a laptop and one is a rented GPU; the path cannot be a constant."""
    monkeypatch.setenv("CASTFORGE_MODELS", "/mnt/models")
    assert suite.models() == "/mnt/models"
    assert suite.models("checkpoints") == os.path.join("/mnt/models", "checkpoints")


def test_comfyui_and_its_url_can_be_moved_too(monkeypatch):
    monkeypatch.setenv("CASTFORGE_COMFYUI", "/opt/comfy")
    monkeypatch.setenv("CASTFORGE_COMFY_URL", "http://10.0.0.5:8188/")
    assert suite.comfyui() == "/opt/comfy"
    assert suite.comfy_url() == "http://10.0.0.5:8188", "a trailing slash doubles up in every request"


def test_the_shared_things_are_all_absolute_paths():
    for what, where in suite.shares().items():
        assert os.path.isabs(where), f"{what} is not an absolute path: {where}"


def test_the_gpu_rules_are_pointed_at_and_never_restated():
    """The local-or-rented decision lives in core/gpu.py. Two copies would disagree within a week."""
    places = suite.gpu_places()
    assert places["rules"].endswith(os.path.join("core", "gpu.py"))
    for key in ("facts", "client", "rented"):
        assert os.path.isabs(places[key]), key


def test_a_films_cast_can_be_asked_for_by_name():
    every = suite.characters()
    one = suite.characters("santa_is_a_lie")
    assert one.startswith(every) and one.endswith("characters")


# --- what is missing --------------------------------------------------------------------------------

def test_a_machine_with_everything_has_nothing_to_complain_about():
    assert suite.check(EVERYTHING) == []


def test_a_fresh_machine_says_what_is_missing_and_how_to_point_it_elsewhere():
    said = suite.check(NOTHING)
    whole = "\n".join(said)
    assert "CASTFORGE_MODELS" in whole and "CASTFORGE_COMFYUI" in whole
    assert "forgefilms" in whole and "graphic-novel" in whole


def test_a_model_library_missing_one_kind_names_that_kind():
    def all_but_loras(p):
        return not p.endswith("loras")
    said = "\n".join(suite.check(all_but_loras))
    assert "loras" in said and "extra_model_paths" in said


def test_it_reads_as_a_summary_a_person_can_act_on():
    whole = "\n".join(suite.describe(NOTHING))
    for name in suite.TOOLS:
        assert name in whole
    assert "not here" in whole and "!" in whole


def test_a_complete_machine_is_described_without_any_warnings():
    whole = "\n".join(suite.describe(EVERYTHING))
    assert "not here" not in whole and "missing" not in whole and "!" not in whole
