import pytest

from core import appearance, schema


def test_every_variable_names_targets_on_both_sides():
    for part, table in (("face", appearance.FACE), ("body", appearance.BODY)):
        for key, (group, plus, minus, help_) in table.items():
            assert group and help_, f"{part}.{key} needs a group and a help line"
            assert plus and minus, f"{part}.{key} must move both ways"
            assert len(plus) == len(minus), f"{part}.{key}: the two sides must match"
            for name in plus + minus:
                assert not name.startswith("{"), name


def test_paired_features_move_both_sides_of_the_body():
    # a cheekbone or an arm is two targets, one per side; a nose or a waist is one
    for key in ("cheekbones", "eye_size", "ear_size"):
        plus = appearance.FACE[key][1]
        assert sorted(plus) == sorted([f"l-{plus[0][2:]}", f"r-{plus[0][2:]}"]), key
    assert len(appearance.FACE["nose_width"][1]) == 1
    assert len(appearance.BODY["arm_muscle"][1]) == 2
    assert len(appearance.BODY["waist"][1]) == 1


def test_an_untouched_design_asks_for_nothing():
    for design in (None, {}, {"face": {}}, {"face": {"jaw_width": 0}}, {"body": None},
                   {"face": {"jaw_width": None}}, {"face": "not a dict"}):
        assert appearance.targets_for(design) == {}


def test_a_slider_picks_the_side_it_leans():
    wide = appearance.targets_for({"face": {"jaw_width": 1.0}})
    narrow = appearance.targets_for({"face": {"jaw_width": -1.0}})
    assert wide == {"chin-width-incr": 1.0}
    assert narrow == {"chin-width-decr": 1.0}
    assert set(wide) & set(narrow) == set()


def test_how_far_the_slider_went_is_the_weight():
    assert appearance.targets_for({"body": {"shoulders": 0.4}}) == {"measure-shoulder-dist-incr": 0.4}
    assert appearance.targets_for({"body": {"shoulders": -0.25}}) == {"measure-shoulder-dist-decr": 0.25}


def test_a_slider_cannot_be_pushed_past_its_ends():
    assert appearance.targets_for({"face": {"jaw_width": 7}}) == {"chin-width-incr": 1.0}
    assert appearance.targets_for({"face": {"jaw_width": -7}}) == {"chin-width-decr": 1.0}
    assert appearance.clamp("rubbish") == 0.0


def test_a_paired_slider_moves_both_sides_by_the_same_amount():
    got = appearance.targets_for({"body": {"arm_muscle": 0.8}})
    assert got == {"l-upperarm-muscle-incr": 0.8, "r-upperarm-muscle-incr": 0.8}


def test_face_and_body_are_asked_for_together():
    got = appearance.targets_for({"face": {"nose_width": 0.5}, "body": {"waist": -0.5}})
    assert got == {"nose-scale-horiz-incr": 0.5, "measure-waist-circ-decr": 0.5}


def test_the_head_shape_is_a_choice_not_a_slider():
    assert appearance.head_shape_target({"face": {"head_shape": "square"}}) == "head-square"
    for design in ({}, {"face": {"head_shape": "none"}}, {"face": {"head_shape": "potato"}}):
        assert appearance.head_shape_target(design) is None


def test_the_photo_fit_keeps_its_own_narrower_list():
    # widening the fit changes every face already built from a photo, so the two lists stay apart
    names = [n for n, _, _ in appearance.photo_vars()]
    assert len(names) == 41 and len(set(names)) == 41
    assert "ear_size" not in names and "eye_depth" not in names
    for _name, plus, minus in appearance.photo_vars():
        assert plus, "a fit variable must have a + side"


def test_the_whole_head_shapes_are_offered_to_the_photo_fit_too():
    names = [n for n, _, _ in appearance.photo_vars()]
    for shape in appearance.HEAD_SHAPES:
        if shape != "none":
            assert f"head-{shape}" in names, shape


def test_groups_keep_the_order_the_table_was_written_in():
    groups = appearance.groups(appearance.FACE)
    assert list(groups) == ["Head", "Jaw and chin", "Cheeks", "Eyes and brows", "Nose", "Mouth and lips", "Ears"]
    assert "jaw_width" in groups["Jaw and chin"]
    assert sum(len(v) for v in groups.values()) == len(appearance.FACE)


# --- the design vocabulary the app and the checker read ---------------------------------------------------

def test_every_slider_is_a_design_key():
    for part, table in (("face", appearance.FACE), ("body", appearance.BODY)):
        for key in table:
            assert schema.CHARACTER[f"{part}.{key}"]["type"] == "slider", key


def test_a_slider_outside_its_range_is_refused():
    base = {"gender": "male", "age": 30, "height_cm": 180}
    assert schema.check_design({**base, "face": {"jaw_width": 0.5}}) == []
    assert schema.check_design({**base, "face": {"jaw_width": 2}})
    assert schema.check_design({**base, "body": {"shoulders": "wide"}})
    assert schema.check_design({**base, "face": {"jaw_width": True}})     # a flag is not a slider


def test_hair_styles_and_eyebrows_are_offered_as_choices():
    assert schema.CHARACTER["hair.style"]["values"][0] == ""        # empty: keep the length
    for style in appearance.HAIR_STYLES:
        assert style in schema.CHARACTER["hair.style"]["values"]
    assert len(appearance.EYEBROWS) == 12
    assert schema.CHARACTER["eyebrows"]["values"] == list(appearance.EYEBROWS)


def test_the_old_designs_still_build():
    # every new key is optional: a design written before any of this existed must still pass
    old = {"gender": "female", "age": 30, "height_cm": 168, "build": "average", "skin": "#e0b89a",
           "hair": {"length": "medium", "color": "#3b2a20"}, "beard": "none", "hat": "none"}
    assert schema.check_design(old) == []
    assert appearance.targets_for(old) == {}


@pytest.mark.parametrize("part", ["face", "body"])
def test_no_variable_asks_for_the_same_target_both_ways(part):
    table = appearance.FACE if part == "face" else appearance.BODY
    for key, (_g, plus, minus, _h) in table.items():
        assert not set(plus) & set(minus), key


def test_every_hair_style_names_an_asset():
    # the build looks a style up and uses whatever comes back as the asset name, so none may be empty
    for style, asset in appearance.HAIR_STYLES.items():
        assert isinstance(asset, str) and asset, style
    # "none" is an answer, not a missing one: it must survive the lookup as the build's own word for bald
    assert appearance.HAIR_STYLES["none"] == "none"
    # a design that names a raw MPFB asset still works: the lookup falls back to what it was given
    assert appearance.HAIR_STYLES.get("ponytail01", "ponytail01") == "ponytail01"


def test_everything_the_wardrobe_can_offer_can_also_be_exported():
    # the studio offers looks from these tables and the live view exports them by name; a name the
    # exporter refuses would be a tile that silently does nothing
    known = appearance.known_assets()
    for table in (appearance.HAIR_STYLES, appearance.EYEBROWS, appearance.HATS, appearance.TOPS,
                  appearance.BOTTOMS):
        for value in table.values():
            if value and value != "none":
                assert value in known, value
    for pieces in appearance.BEARDS.values():
        for asset in pieces:
            assert asset in known, asset
    for per_sex in appearance.OUTFITS.values():
        for asset in per_sex.values():
            assert asset in known, asset
    assert appearance.DRESS in known and appearance.SHOES in known and appearance.BOOTS in known


def test_a_design_only_ever_wears_things_that_can_be_exported():
    known = appearance.known_assets()
    for design in ({"gender": "male", "beard": "santa", "hat": "santa"},
                   {"gender": "female", "outfit": {"style": "robe"}},
                   {"gender": "female", "outfit": {"garment": "dress"}},
                   {"gender": "male", "hair": {"style": "afro"}, "costume": {"boots": "#000000"}},
                   {}, None):
        for item in appearance.wearables(design):
            assert item["asset"] in known, item


def test_a_hat_takes_the_hair_off():
    # the build leaves the hair off under a hat, and the live view must agree or they show different people
    worn = {w["role"] for w in appearance.wearables({"gender": "male", "hat": "fedora",
                                                     "hair": {"style": "afro"}})}
    assert "hat" in worn and "hair" not in worn
    bare = {w["role"] for w in appearance.wearables({"gender": "male", "hair": {"style": "afro"}})}
    assert "hair" in bare and "hat" not in bare
