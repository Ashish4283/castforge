import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core import screening  # noqa: E402


def good(**over):
    """What a healthy move measures."""
    return {"missing": [], "frozen": [], "reach": 1.0, "stretch": 1.1, "rough_skin": 0.0,
            "moved": 0.3, **over}


def all_good(**per_move):
    out = {name: good() for name in screening.MOVES}
    for name, facts in per_move.items():
        out[name] = facts
    for name in ("speak", "express"):
        out[name] = {**out[name], "shapes": screening.MOVES[name]["shapes"][1]}
    return out


# --- what the test is of ---------------------------------------------------------------------------------

def test_every_move_says_what_it_is_for_in_plain_words():
    for name, move in screening.MOVES.items():
        assert move["title"] and move["why"], name
        assert move.get("needs") or move.get("shapes"), f"{name} measures nothing"


def test_the_moves_cover_what_a_scene_can_actually_ask_for():
    """Walking, running, jumping, the head, bending, wrists and fingers - the user's own list."""
    for asked in ("walk", "run", "jump", "turn_head", "bend", "wrist", "fingers"):
        assert asked in screening.MOVES


def test_the_controls_it_reaches_for_are_the_ones_a_scene_drives():
    """If this list and scene_kit.Actor ever disagree, the screen test checks a rig nobody uses."""
    bones = set(screening.every_bone())
    for driven in ("torso", "foot_ik.L", "foot_heel_ik.R", "thigh_parent.L", "upper_arm_fk.R",
                   "forearm_fk.L", "hand_fk.L", "hand_ik.R", "upper_arm_parent.L", "head", "neck",
                   "chest", "eye_common", "jaw_master", "f_index.01.L", "thumb.03.R"):
        assert driven in bones, driven
    assert len(screening.every_bone()) == len(set(screening.every_bone())), "a bone is listed twice"


# --- reading one move ------------------------------------------------------------------------------------

def test_a_healthy_move_has_nothing_to_say_about_it():
    assert screening.look("walk", good(slide=0.004)) == []


def test_a_missing_control_is_the_worst_thing_that_can_be_wrong():
    said = screening.look("fingers", good(missing=["f_index.01.L", "thumb.01.L"]))
    assert said and "nothing at all" in said[0]
    assert screening.bad("fingers", good(missing=["f_index.01.L"]))


def test_a_long_list_of_missing_controls_is_not_read_out_in_full():
    said = screening.look("fingers", good(missing=[f"f_index.0{i}.L" for i in range(1, 4)]
                                          + [f"thumb.0{i}.R" for i in range(1, 4)]))
    assert "and 2 more" in said[0]


def test_a_control_that_is_there_but_will_not_move_is_counted_apart_from_a_missing_one():
    """Same symptom in a shot, different cause, and the fix is different."""
    said = screening.look("wrist", good(frozen=["hand_fk.L"]))
    assert said and "locked or constrained" in said[0]
    assert screening.bad("wrist", good(frozen=["hand_fk.L"]))


def test_skin_that_pulls_out_of_shape_is_reported_before_the_joint_melts():
    soft = screening.look("arms", good(rough_skin=0.006, stretch=4.0))
    assert soft and "goes soft" in soft[0] and "0.60%" in soft[0]
    assert not screening.bad("arms", good(rough_skin=0.006)), "soft is not the same as unusable"
    melted = screening.look("arms", good(rough_skin=0.03, stretch=9.0))
    assert "the joint melts" in melted[0]
    assert screening.bad("arms", good(rough_skin=0.03))


def test_one_hot_edge_is_not_a_fault_because_every_armpit_has_one():
    """Measured over seven built characters, the worst edge in the arms pose runs 2.4x to 8.7x on
    characters that all look right. A limit anywhere in that range fails everybody or nobody."""
    assert screening.look("arms", good(stretch=8.5, rough_skin=0.001)) == []
    assert not screening.bad("arms", good(stretch=8.5, rough_skin=0.001))


def test_the_worst_edge_is_still_said_out_loud_when_the_surface_is_rough_too():
    said = screening.look("arms", good(rough_skin=0.006, stretch=4.0))
    assert "4.0x" in said[0], said


def test_a_move_that_does_not_get_all_the_way_is_noticed():
    assert screening.look("bend", good(reach=0.7))
    assert not screening.bad("bend", good(reach=0.7))
    assert screening.bad("bend", good(reach=0.3))


def test_a_short_reach_is_not_reported_twice_when_the_control_is_simply_missing():
    said = screening.look("wrist", good(missing=["hand_fk.L"], reach=0.0))
    assert len(said) == 1, said


def test_a_sliding_foot_is_only_looked_for_where_it_matters():
    assert screening.look("walk", good(slide=0.08))
    assert "skating" in screening.look("walk", good(slide=0.08))[0]
    assert screening.look("bend", good(slide=0.08)) == [], "a bend has no planted foot to slide"


def test_speaking_needs_all_fifteen_mouth_shapes():
    assert screening.look("speak", good(shapes=15)) == []
    said = screening.look("speak", good(shapes=9))
    assert said and "9 of the 15" in said[0]
    assert screening.bad("speak", good(shapes=9))


def test_a_move_nobody_has_heard_of_says_so():
    assert screening.look("moonwalk", good())


# --- the verdict -----------------------------------------------------------------------------------------

def test_a_character_that_can_do_everything_is_approved():
    out = screening.verdict(all_good())
    assert out["approved"] and out["failed"] == 0 and out["rough"] == 0
    assert "nothing tears" in out["line"]
    assert out["passed"] == len(screening.MOVES)


def test_a_rough_move_does_not_block_a_character():
    """Something that will look slightly wrong is the director's call, not this function's."""
    out = screening.verdict(all_good(arms=good(rough_skin=0.006)))
    assert out["approved"] and out["rough"] == 1 and out["failed"] == 0
    assert "with 1 rough" in out["line"] and "raise and swing the arms" in out["line"]


def test_a_torn_shoulder_keeps_a_character_off_the_film():
    out = screening.verdict(all_good(arms=good(rough_skin=0.04)))
    assert not out["approved"] and out["failed"] == 1
    assert "not ready" in out["line"]


def test_a_move_that_was_never_tested_is_not_a_pass():
    results = all_good()
    del results["jump"]
    out = screening.verdict(results)
    assert not out["approved"]
    row = [r for r in out["rows"] if r["move"] == "jump"][0]
    assert row["state"] == "untested"


def test_the_card_has_one_row_per_move_in_the_order_they_are_tested():
    rows = screening.card(all_good())
    assert [r["move"] for r in rows] == screening.ORDER
    assert all(r["state"] == "works" for r in rows)


def test_the_card_carries_the_numbers_so_a_person_can_see_how_close_it_was():
    rows = screening.card(all_good(walk=good(stretch=1.4, slide=0.009)))
    walk = [r for r in rows if r["move"] == "walk"][0]
    assert walk["stretch"] == 1.4 and walk["slide"] == 0.009 and walk["reach"] == 1.0


def test_the_worst_failures_are_named_in_the_verdict_and_the_rest_are_not_listed():
    bad_ones = {m: good(missing=["torso"]) for m in list(screening.ORDER)[:5]}
    out = screening.verdict(all_good(**bad_ones))
    assert out["failed"] == 5 and out["line"].count(",") >= 2 and "..." in out["line"]


# --- a control that turns and moves nothing --------------------------------------------------------------

def test_a_move_whose_controls_turn_but_move_no_body_is_a_failure():
    """The scene step runs, every number looks right, and the character stands there. Only measuring the
    SURFACE catches it - which is why `reach` on its own is not enough."""
    dead = good(reach=1.0, stretch=1.0, moved=0.0004)
    said = screening.look("arms", dead)
    assert said and "the body does not" in said[0]
    assert screening.bad("arms", dead)


def test_skin_that_moves_is_not_complained_about():
    assert screening.look("arms", good(moved=0.42)) == []


def test_a_dead_move_is_not_blamed_on_the_body_when_the_control_is_missing():
    said = screening.look("arms", good(missing=["upper_arm_fk.L"], moved=0.0))
    assert len(said) == 1 and "nothing at all" in said[0]


def test_it_says_where_the_skin_went_soft_not_just_how_much():
    """A number and a 3D coordinate is not something anybody can act on."""
    said = screening.look("arms", good(rough_skin=0.006, stretch=8.7,
                                       worst_near="joint-r-shoulder"))
    assert "at the right shoulder" in said[0], said
    assert screening.where("joint-spine-3") == "the belly"
    assert screening.where("joint-l-knee") == "the left knee"
    assert screening.where(None) is None
    assert screening.where("joint-made-up") == "made up"   # never a crash, never a raw marker name


def test_a_place_is_carried_on_the_card_too():
    rows = screening.card(all_good(arms=good(rough_skin=0.006, worst_near="joint-l-elbow")))
    arms = [r for r in rows if r["move"] == "arms"][0]
    assert arms["worst_near"] == "the left elbow"
