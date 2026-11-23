import os

import pytest

from core import preview_kit


def test_only_the_body_underneath_decides_which_kit_is_needed():
    # the sliders, the colours and the clothes are all put on in the browser: they share one kit
    base = {"gender": "male", "age": 34, "build": "muscular", "height_cm": 188}
    key = preview_kit.key_for(base)
    for extra in ({"face": {"jaw_width": 1}}, {"body": {"shoulders": -1}}, {"skin": "#ffffff"},
                  {"costume": {"cape": "#ff0000"}}, {"hair": {"style": "afro"}}):
        assert preview_kit.key_for({**base, **extra}) == key


def test_ages_within_a_band_share_a_body():
    # a band is five years wide, so neighbours usually share one (31 and 29 do; 31 and 34 fall either side
    # of 32.5, which is the price of banding at all). What matters is that a year's difference is not a
    # new eight-second build every time, and that genuinely different ages are genuinely different bodies.
    same = preview_kit.key_for({"gender": "male", "age": 31})
    assert preview_kit.key_for({"gender": "male", "age": 29}) == same
    assert preview_kit.key_for({"gender": "male", "age": 30.4}) == same
    # and the same for stature: a centimetre either way is not a new body
    tall = preview_kit.key_for({"gender": "male", "height_cm": 186})
    assert preview_kit.key_for({"gender": "male", "height_cm": 184}) == tall
    assert preview_kit.key_for({"gender": "male", "height_cm": 160}) != tall
    assert preview_kit.key_for({"gender": "male", "age": 20}) != preview_kit.key_for({"gender": "male", "age": 60})
    assert len({preview_kit.key_for({"gender": "male", "age": a}) for a in range(16, 91)}) <= 16


def test_an_age_is_kept_inside_what_the_model_covers():
    assert preview_kit.band_age(2) == 15      # 16 rounded to the nearest band
    assert preview_kit.band_age(200) == 90
    assert preview_kit.band_age(None) == 30
    assert preview_kit.band_age("rubbish") == 30


def test_a_design_missing_its_basics_still_asks_for_something_sensible():
    assert preview_kit.key_for(None) == "female-30-average-170"
    assert preview_kit.key_for({"gender": "alien", "build": "enormous"}) == "female-30-average-170"


def test_a_key_reads_back_as_the_arguments_that_made_it():
    made = preview_kit.key_for({"gender": "male", "age": 44, "build": "heavy", "height_cm": 183})
    assert preview_kit.parts(made) == ("male", 45.0, "heavy", 185.0)


@pytest.mark.parametrize("bad", ["", None, "male", "male-30", "male-30-average", "../..-30-average-170",
                                 "male-30-average-170-extra", "male-thirty-average-170"])
def test_anything_that_is_not_a_kit_key_is_refused(bad, tmp_path):
    # the key becomes a folder name, so it must never be able to point somewhere else
    with pytest.raises(ValueError):
        preview_kit.folder_for(str(tmp_path), bad)


def test_a_kit_counts_as_ready_only_when_every_file_is_there(tmp_path):
    import json
    key = "male-30-average-175"
    folder = preview_kit.folder_for(str(tmp_path), key)
    assert not preview_kit.is_ready(str(tmp_path), key)
    os.makedirs(folder)
    for name in preview_kit.FILES:
        assert not preview_kit.is_ready(str(tmp_path), key)
        with open(os.path.join(folder, name), "w") as fh:
            json.dump({"version": preview_kit.VERSION}, fh) if name.endswith(".json") else fh.write("x")
    assert preview_kit.is_ready(str(tmp_path), key)


def test_an_empty_file_is_not_a_kit(tmp_path):
    # a Blender run that died half way leaves the files behind: they must not pass for a finished kit
    key = "female-25-slim-160"
    folder = preview_kit.folder_for(str(tmp_path), key)
    os.makedirs(folder)
    for name in preview_kit.FILES:
        open(os.path.join(folder, name), "w").close()
    assert not preview_kit.is_ready(str(tmp_path), key)


def test_a_kit_from_an_older_exporter_is_made_again(tmp_path):
    # kits live on disk for ever; without this a fixed exporter would keep serving the broken one's bodies
    import json
    key = "male-30-average-175"
    folder = preview_kit.folder_for(str(tmp_path), key)
    os.makedirs(folder)
    open(os.path.join(folder, "kit.bin"), "w").write("x")
    for version, ready in ((preview_kit.VERSION - 1, False), (preview_kit.VERSION, True)):
        json.dump({"version": version}, open(os.path.join(folder, "kit.json"), "w"))
        assert preview_kit.is_ready(str(tmp_path), key) is ready


def test_a_kit_whose_json_is_rubbish_is_made_again(tmp_path):
    key = "male-30-average-175"
    folder = preview_kit.folder_for(str(tmp_path), key)
    os.makedirs(folder)
    open(os.path.join(folder, "kit.bin"), "w").write("x")
    open(os.path.join(folder, "kit.json"), "w").write("half a fi")
    assert preview_kit.is_ready(str(tmp_path), key) is False
