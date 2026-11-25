import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "blender"))

import tailor  # noqa: E402

# A real body's joints, lifted from a preview kit (female, 1.65 m) and in the VIEWER's space: y is up.
# Any space will do, which is most of the point - see test_a_pattern_does_not_care_which_axis_is_up.
BODY = {
    "joint-ground": (0.0, 0.006, 0.0),
    "joint-l-ankle": (0.17, 0.07, 0.009), "joint-r-ankle": (-0.17, 0.07, 0.009),
    "joint-l-foot-1": (0.174, 0.01, 0.117), "joint-r-foot-1": (-0.174, 0.01, 0.117),
    "joint-l-foot-2": (0.177, 0.017, 0.194), "joint-r-foot-2": (-0.177, 0.017, 0.194),
    "joint-l-knee": (0.135, 0.446, 0.045), "joint-r-knee": (-0.135, 0.446, 0.045),
    "joint-l-hand": (0.434, 1.011, 0.178), "joint-r-hand": (-0.434, 1.011, 0.178),
    "joint-l-hand-2": (0.454, 0.982, 0.193), "joint-r-hand-2": (-0.454, 0.982, 0.193),
    "joint-l-elbow": (0.318, 1.127, 0.017), "joint-r-elbow": (-0.318, 1.127, 0.017),
    "joint-l-shoulder": (0.149, 1.315, 0.017), "joint-r-shoulder": (-0.149, 1.315, 0.017),
    "joint-neck": (0.0, 1.397, 0.003), "joint-pelvis": (0.0, 0.907, 0.018),
    "joint-head": (0.0, 1.5, 0.033),
}
SHIN = math.dist(BODY["joint-l-knee"], BODY["joint-l-ankle"])


def taller(body, by=1.25):
    """The same body, scaled - what a 2 m character's joints look like."""
    return {k: tuple(x * by for x in v) for k, v in body.items()}


def every_point(pieces):
    return [p for piece in pieces for ring in piece["rings"] for p in ring]


def reach(pieces):
    """How big the thing is: the longest distance between any two of its points."""
    pts = every_point(pieces)
    return max(math.dist(a, b) for a in pts for b in pts) if len(pts) > 1 else 0.0


# --- the one shape -------------------------------------------------------------------------------------

def test_a_sweep_lays_each_ring_across_the_way_the_path_is_going():
    path = [(0, 0, 0), (0, 1, 0), (0, 2, 0)]
    rings = tailor.sweep(path, [0.1, 0.1, 0.1], hint=(0, 0, 1), span=8)
    assert len(rings) == 3 and all(len(r) == 8 for r in rings)
    for ring, centre in zip(rings, path):
        assert all(abs(math.dist(p, centre) - 0.1) < 1e-9 for p in ring)
        assert all(abs(p[1] - centre[1]) < 1e-9 for p in ring)      # flat across the path


def test_a_sweep_can_be_squashed_into_a_strap():
    rings = tailor.sweep([(0, 0, 0), (0, 1, 0)], [0.2, 0.2], hint=(0, 0, 1), span=4, squash=[0.1, 0.1])
    wide = max(p[0] for p in rings[0]) - min(p[0] for p in rings[0])
    thick = max(p[2] for p in rings[0]) - min(p[2] for p in rings[0])
    assert wide > thick * 8


def test_a_sweep_of_one_point_is_nothing_rather_than_a_crash():
    assert tailor.sweep([(0, 0, 0)], [0.1]) == []


# --- what makes this different from an asset ------------------------------------------------------------

def test_a_pattern_does_not_care_which_axis_is_up():
    """The build has z up and the live view has y up. Measuring every direction off the body itself means
    one implementation serves both - which is where the Santa cap needed two and got the axes wrong."""
    # a quarter turn about x, which takes y up to z up. Not a y<->z SWAP: that is a reflection, and a
    # reflection flips the winding of every ring (the shape is the same, the faces point inwards).
    turn = lambda v: (v[0], -v[2], v[1])                                      # noqa: E731
    swapped = {k: turn(v) for k, v in BODY.items()}
    for what in ("socks", "shoes_made", "watch", "wristband", "tie", "scarf"):
        here = every_point(tailor.cut(what, BODY, {"colour": "#fff", "style": "boot"}))
        there = every_point(tailor.cut(what, swapped, {"colour": "#fff", "style": "boot"}))
        assert here and len(here) == len(there), what
        for a, b in zip(here, there):
            assert math.dist(turn(a), b) < 1e-9, what


def test_a_bigger_body_gets_a_bigger_sock_without_being_told():
    small = tailor.sock(BODY, "l")
    big = tailor.sock(taller(BODY, 1.25), "l")
    assert 1.24 < reach(big) / reach(small) < 1.26


def test_a_sock_fits_the_ankle_it_is_cut_for_and_stops_below_the_knee():
    pieces = tailor.sock(BODY, "l", "crew")
    assert len(pieces) == 1 and pieces[0]["stuff"] == "knit" and pieces[0]["shut"]
    top = max(p[1] for p in every_point(pieces))
    assert BODY["joint-l-ankle"][1] < top < BODY["joint-l-knee"][1]
    ankle_ring = [p for p in every_point(pieces) if abs(p[1] - 0.08) < 0.01]
    assert ankle_ring, "nothing at ankle height"
    wide = max(math.dist(a, b) for a in ankle_ring for b in ankle_ring)
    assert 0.06 < wide < 0.11, f"an ankle that is {wide * 100:.0f} cm across is not an ankle"


def test_sock_heights_are_what_they_say():
    tops = {h: max(p[1] for p in every_point(tailor.sock(BODY, "l", h))) for h in tailor.SOCK_HEIGHTS}
    assert tops["ankle"] < tops["crew"] < tops["knee"] <= BODY["joint-l-knee"][1] + 0.01


def test_a_sock_worn_under_a_shoe_leaves_the_foot_out_of_it():
    bare = tailor.sock(BODY, "l", over_foot=True)
    under = tailor.sock(BODY, "l", over_foot=False)
    assert max(p[2] for p in every_point(bare)) > max(p[2] for p in every_point(under)) + 0.1


# --- footwear -------------------------------------------------------------------------------------------

def test_a_shoe_has_a_sole_under_the_foot_and_runs_past_the_toe():
    pieces = tailor.shoe(BODY, "l", "shoe")
    assert [p["name"] for p in pieces] == ["sole_l", "shoe_l"]
    sole = [p for p in pieces if p["name"] == "sole_l"][0]
    sole_pts = [p for ring in sole["rings"] for p in ring]
    assert min(p[1] for p in sole_pts) < BODY["joint-l-foot-1"][1], "the sole is not under the foot"
    assert max(p[1] for p in sole_pts) < BODY["joint-l-ankle"][1], "the sole is up the leg, not on the floor"
    assert max(p[2] for p in sole_pts) > BODY["joint-l-foot-2"][2], "the shoe stops at the ball of the foot"
    assert sole["stuff"] == "rubber" and sole["shut"] and sole["lid"]


def test_a_boot_climbs_the_leg_and_a_shoe_does_not():
    shoe_top = max(p[1] for p in every_point(tailor.shoe(BODY, "l", "shoe")))
    boot_top = max(p[1] for p in every_point(tailor.shoe(BODY, "l", "boot")))
    assert boot_top > shoe_top + SHIN * 0.3
    assert boot_top < BODY["joint-l-knee"][1]


def test_a_heel_stands_under_the_back_of_the_shoe_and_a_sandal_is_two_straps():
    heel = tailor.shoe(BODY, "l", "heel")
    assert any(p["name"] == "heel_l" for p in heel)
    block = [p for p in heel if p["name"] == "heel_l"][0]
    floor = BODY["joint-l-foot-1"][1]
    assert min(q[1] for ring in block["rings"] for q in ring) < floor + 0.01, "the heel misses the ground"
    sole = [p for p in heel if p["name"] == "sole_l"][0]
    assert sole["rings"][0][0][1] > sole["rings"][-1][0][1], "a heel does not raise the back of the sole"
    sandal = tailor.shoe(BODY, "l", "sandal")
    assert sum(1 for p in sandal if p["name"].startswith("strap")) == 2
    assert not any(p["name"] == "shoe_l" for p in sandal), "a sandal has no upper"


def test_no_footwear_is_asked_for_by_name():
    assert tailor.shoe(BODY, "l", "none") == []


# --- what is worn on an arm -----------------------------------------------------------------------------

def test_a_watch_case_stands_off_the_back_of_the_wrist_away_from_the_body():
    pieces = tailor.watch(BODY, "l")
    assert [p["name"] for p in pieces] == ["watch_strap_l", "watch_case_l"]
    case = [p for p in pieces if p["name"].endswith("case_l")][0]
    strap = [p for p in pieces if p["name"].endswith("strap_l")][0]
    out_case = max(p[0] for ring in case["rings"] for p in ring)
    out_strap = max(p[0] for ring in strap["rings"] for p in ring)
    assert out_case > out_strap, "the case is inside the strap"
    assert case["stuff"] == "metal" and strap["stuff"] == "leather"
    right = tailor.watch(BODY, "r")
    assert min(p[0] for p in every_point(right)) < -0.4, "the right watch is not on the right wrist"


def test_a_watch_is_the_width_of_that_wrist():
    pts = every_point(tailor.watch(BODY, "l", girth=1.0))
    across = max(math.dist(a, b) for a in pts for b in pts)
    assert 0.05 < across < 0.12, f"{across * 100:.0f} cm is a bangle, not a watch"


def test_a_bracer_is_a_wider_wristband():
    along = lambda w: math.dist(w[0]["rings"][0][0], w[0]["rings"][-1][0])     # noqa: E731
    assert along(tailor.wristband(BODY, "l", width=3.0)) > along(
        tailor.wristband(BODY, "l", width=1.0)) * 2.5


# --- what is worn on the trunk --------------------------------------------------------------------------

def test_a_tie_hangs_down_the_front_of_the_chest_and_narrows_to_a_point():
    pieces = tailor.tie(BODY)
    assert [p["name"] for p in pieces] == ["tie_knot", "tie_blade"]
    blade = [p for p in pieces if p["name"] == "tie_blade"][0]
    knot_y = max(p[1] for ring in pieces[0]["rings"] for p in ring)
    assert knot_y < BODY["joint-neck"][1] + 0.01, "the knot is above the collar"
    tip, start = blade["rings"][-1], blade["rings"][0]
    assert min(p[1] for p in tip) < BODY["joint-pelvis"][1] + 0.3
    assert all(p[2] > 0.05 for p in start), "the tie is not on the front of the body"
    span = lambda ring: max(math.dist(a, b) for a in ring for b in ring)   # noqa: E731
    assert span(tip) < span(start) * 0.6, "the tie does not narrow"


def test_a_longer_tie_hangs_lower():
    low = min(p[1] for p in every_point(tailor.tie(BODY, length=0.6)))
    lower = min(p[1] for p in every_point(tailor.tie(BODY, length=1.3)))
    assert lower < low - 0.1


def test_a_scarf_loops_the_neck_and_its_tail_hangs_in_front():
    pieces = tailor.scarf(BODY)
    assert [p["name"] for p in pieces] == ["scarf_loop", "scarf_tail"]
    loop = [p for ring in pieces[0]["rings"] for p in ring]
    assert all(abs(p[1] - BODY["joint-neck"][1]) < 0.12 for p in loop)
    tail = [p for ring in pieces[1]["rings"] for p in ring]
    assert min(p[1] for p in tail) < BODY["joint-neck"][1] - 0.2
    assert sum(p[2] for p in tail) / len(tail) > 0.05, "the tail hangs down the back"


# --- the one door -------------------------------------------------------------------------------------

def test_a_body_without_the_joints_gets_nothing_rather_than_an_error():
    assert tailor.cut("socks", {}, {}) == []
    assert tailor.cut("watch", {"joint-l-hand": (0, 1, 0)}, {}) == []
    assert tailor.cut("socks", {"joint-l-ankle": (0, 0, 0), "joint-l-knee": (0, 0, 0),
                               "joint-l-foot-1": (0, 0, 0), "joint-l-foot-2": (0, 0, 0)}, {}) == []


def test_an_unknown_wearable_is_not_invented():
    assert tailor.cut("cravat", BODY, {}) == []


def test_socks_and_shoes_are_cut_for_both_feet_and_a_watch_for_the_wrist_asked_for():
    assert len(tailor.cut("socks", BODY, {})) == 2
    assert len(tailor.cut("shoes_made", BODY, {"style": "boot"})) == 4       # sole + upper, twice
    assert len(tailor.cut("watch", BODY, {"side": "left"})) == 2            # strap + case, one wrist
    assert len(tailor.cut("watch", BODY, {"side": "both"})) == 4
    assert len(tailor.cut("wristband", BODY, {"side": "right"})) == 1


def test_every_wearable_in_the_table_can_actually_be_cut():
    for what in tailor.WEARABLES:
        want = {"style": "shoe"} if what == "shoes_made" else {}
        assert tailor.cut(what, BODY, want), what


# --- what a design asks for -----------------------------------------------------------------------------

def test_a_colour_is_what_asks_for_an_accessory():
    assert tailor.asked_for({}) == []
    asked = dict(tailor.asked_for({"costume": {"watch": "#c0c0c0", "tie": "#8c1018"}}))
    assert set(asked) == {"watch", "tie"} and asked["watch"]["colour"] == "#c0c0c0"


def test_footwear_is_asked_for_by_style_not_by_colour():
    asked = dict(tailor.asked_for({"outfit": {"shoe_style": "boot", "shoes": "#1a1a1a"}}))
    assert asked["shoes_made"]["style"] == "boot" and asked["shoes_made"]["colour"] == "#1a1a1a"
    assert "shoes_made" not in dict(tailor.asked_for({"outfit": {"shoes": "#1a1a1a"}}))


def test_socks_leave_the_foot_out_when_a_made_shoe_is_going_over_them():
    bare = dict(tailor.asked_for({"costume": {"socks": "#fff"}}))
    shod = dict(tailor.asked_for({"costume": {"socks": "#fff"}, "outfit": {"shoe_style": "shoe"}}))
    assert bare["socks"]["over_foot"] and not shod["socks"]["over_foot"]


def test_things_go_on_in_the_order_they_are_worn():
    design = {"costume": {"socks": "#fff", "watch": "#ccc", "tie": "#111", "scarf": "#333",
                          "wristband": "#444"},
              "outfit": {"shoe_style": "shoe"}}
    assert [w for w, _ in tailor.asked_for(design)] == [
        "socks", "shoes_made", "tie", "scarf", "wristband", "watch"]


# --- it has to be the size of the body, not merely attached to it ---------------------------------------

def test_a_shoe_is_a_shoes_length_not_a_clown_shoe():
    """It was 0.37 m on a 0.28 m foot once, and that is exactly what it looked like.

    Measured against the ankle-to-toe span, which is the one bit of the foot the body actually marks;
    heel to toe tip is about 1.3 of it, and a shoe is a little longer again."""
    for body in (BODY, taller(BODY, 1.25), taller(BODY, 0.8)):
        span = math.dist(body["joint-l-ankle"], body["joint-l-foot-2"])
        for style in ("shoe", "boot", "sneaker", "sandal", "heel"):
            sole = [p for p in tailor.shoe(body, "l", style) if p["name"] == "sole_l"][0]
            long = reach([sole]) / span
            assert 1.15 < long < 1.55, f"{style}: a sole {long:.2f} times the ankle-to-toe span"


def test_a_shoes_opening_clears_the_ankle_it_is_cut_for():
    """Narrower than the ankle and the leg comes through it: bare skin between trouser and shoe."""
    shoe = [p for p in tailor.shoe(BODY, "l", "shoe") if p["name"] == "shoe_l"][0]
    top = shoe["rings"][-1]
    across = max(math.dist(a, b) for a in top for b in top) / 2
    sock = tailor.sock(BODY, "l")[0]
    ankle_ring = sock["rings"][3]                      # the first ring up the leg
    needs = max(math.dist(a, b) for a in ankle_ring for b in ankle_ring) / 2
    assert across > needs, f"opening {across * 100:.1f} cm round an ankle of {needs * 100:.1f} cm"


def test_a_tie_reaches_the_belt():
    """A tie that stops at the sternum reads as a bib. It did."""
    low = min(p[1] for p in every_point(tailor.tie(BODY)))
    waist = BODY["joint-pelvis"][1]
    assert abs(low - waist) < 0.09, f"the tie ends at {low:.3f}, the waist is at {waist:.3f}"
