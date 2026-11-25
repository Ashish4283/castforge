import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core import gait  # noqa: E402

NORMAL = (1.1, 0.62, 1.0, 0.0)          # acting.PACES["normal"], the walk as it was tuned


def body(tall=1.70, leg_share=0.52, hips=None, head=0.155):
    """A body's joint markers, in the viewer's space (y up), at whatever size and build is asked for."""
    leg = tall * leg_share
    hips = hips if hips is not None else leg * gait.HIPS_REF
    return {
        "joint-ground": (0.0, 0.0, 0.0),
        "joint-l-upper-leg": (hips / 2, leg, 0.02),
        "joint-r-upper-leg": (-hips / 2, leg, 0.02),
        "joint-neck": (0.0, tall * (1 - head), 0.0),
        "joint-head-2": (0.0, tall, 0.0),
    }


ADULT = body()                                              # 1.70 m, average build
TALL = body(tall=1.95)
ELF = body(tall=1.05)                                       # a small ADULT: Santa's helper
HEAVY = body(hips=0.52 * 1.70 * gait.HIPS_REF * 1.16)       # same height, much wider hips
SLIM = body(hips=0.52 * 1.70 * gait.HIPS_REF * 0.87)
THIN = body(hips=0.52 * 1.70 * gait.HIPS_REF * 0.78)
TODDLER = body(tall=0.86, leg_share=0.41, head=0.25)        # short legs AND a big head
KID = body(tall=1.25, leg_share=0.47, head=0.20)


def walk(b):
    return gait.walk_like(gait.shape_of(b), NORMAL)


# --- measuring the body ----------------------------------------------------------------------------------

def test_a_body_is_measured_off_its_own_markers():
    s = gait.shape_of(ADULT)
    assert abs(s["tall"] - 1.70) < 1e-6
    assert abs(s["leg"] - 0.884) < 1e-3
    assert abs(s["bulk"] - 1.0) < 1e-6, "an average build should measure as average"
    assert s["childish"] < 1e-9


def test_it_does_not_care_which_axis_is_up():
    """The build has z up and the live view has y up, and both hand it the same markers."""
    turned = {k: (v[0], -v[2], v[1]) for k, v in ADULT.items()}
    a, b = gait.shape_of(ADULT), gait.shape_of(turned)
    for key in ("tall", "leg", "hips", "head_share"):
        assert abs(a[key] - b[key]) < 1e-9, key


def test_a_body_without_markers_gets_the_walk_as_it_comes_rather_than_an_error():
    assert gait.shape_of({}) is None
    plain = gait.walk_like(None, NORMAL)
    assert plain["speed"] == 1.1 and plain["step"] == 0.62


# --- size: the one that is pure physics ------------------------------------------------------------------

def test_an_ordinary_adult_walks_exactly_as_the_studio_already_tuned_it():
    """Nothing regresses: only bodies that are NOT the reference get anything different."""
    w = walk(ADULT)
    assert abs(w["speed"] - 1.1) < 0.02 and abs(w["step"] - 0.62) < 0.02
    assert abs(w["swing"] - 1.0) < 0.02 and abs(w["sway"] - 1.0) < 0.02


def test_a_step_can_never_be_longer_than_the_leg_that_swings_it():
    """The bug this is all for: at a fixed 0.62 m, an elf's step is longer than its own leg."""
    for b in (ADULT, TALL, ELF, TODDLER, KID, HEAVY, SLIM, THIN):
        s, w = gait.shape_of(b), walk(b)
        assert w["step"] < s["leg"], f"a step of {w['step']:.2f} m on a leg of {s['leg']:.2f} m"
    assert NORMAL[1] > gait.shape_of(ELF)["leg"], "the old fixed step really was impossible for an elf"


def test_half_the_leg_is_not_half_the_speed_but_the_square_root_of_it():
    """Dynamic similarity: two bodies walk alike when v^2/(gL) matches, so v goes with sqrt(L)."""
    half = body(tall=0.85)
    big, small = walk(ADULT), walk(half)
    assert abs(small["speed"] / big["speed"] - math.sqrt(0.5)) < 0.02
    assert abs(small["step"] / big["step"] - 0.5) < 0.02


def test_froude_numbers_match_across_every_size_which_is_what_makes_them_look_alike():
    def froude(b):
        s, w = gait.shape_of(b), walk(b)
        return w["speed"] ** 2 / (gait.G * s["leg"])
    base = froude(ADULT)
    for b in (TALL, ELF, body(tall=1.40), body(tall=2.40)):
        assert abs(froude(b) - base) < 1e-9, "a size change must not change how the walk reads"


def test_small_bodies_scurry_and_big_ones_plod():
    rate = {name: walk(b)["cadence"] for name, b in
            (("elf", ELF), ("adult", ADULT), ("tall", TALL))}
    assert rate["elf"] > rate["adult"] > rate["tall"]
    assert abs(rate["elf"] / rate["adult"] - 1 / math.sqrt(1.05 / 1.70)) < 0.02


def test_an_elf_is_a_small_adult_and_not_a_child():
    """Santa's helpers are the test of this: small, grown-up proportions, so no toddler's waddle."""
    s = gait.shape_of(ELF)
    assert s["childish"] < 1e-9
    assert walk(ELF)["guard"] < 1e-9 and abs(walk(ELF)["sway"] - 1.0) < 0.02


# --- weight: not a size change ---------------------------------------------------------------------------

def test_a_heavy_body_takes_a_shorter_step_from_a_wider_stance_and_rolls_more():
    heavy, slim = walk(HEAVY), walk(SLIM)
    assert heavy["step"] < slim["step"], "a belly meets the thigh sooner"
    assert heavy["gap"] > slim["gap"], "a heavy body puts its feet further apart"
    assert heavy["sway"] > slim["sway"], "and has to move further over the planted foot"
    assert heavy["swing"] < slim["swing"], "the arms are pushed out and swing less"
    assert heavy["speed"] < slim["speed"]
    assert heavy["double"] > slim["double"], "more of the cycle with both feet down"


def test_weight_is_told_from_the_hips_not_from_the_height():
    """A tall slim body and a short slim body must both come out slim."""
    for tall in (1.30, 1.70, 2.10):
        slim = gait.shape_of(body(tall=tall, hips=tall * 0.52 * gait.HIPS_REF * 0.87))
        assert abs(slim["bulk"] - 0.87) < 1e-6, tall


def test_a_thin_body_is_the_same_rule_carried_further():
    thin, slim, adult = walk(THIN), walk(SLIM), walk(ADULT)
    assert thin["gap"] < slim["gap"] < adult["gap"]
    assert thin["swing"] > slim["swing"] > adult["swing"]
    assert thin["sway"] < slim["sway"] < adult["sway"]


def test_a_heavy_body_leans_forward_a_little_and_bobs_less():
    assert walk(HEAVY)["lean"] > walk(SLIM)["lean"]
    assert walk(HEAVY)["bob"] < walk(SLIM)["bob"]


# --- children: not a weight change either ----------------------------------------------------------------

def test_a_childs_head_is_what_says_it_is_a_child():
    assert gait.shape_of(TODDLER)["childish"] > 0.9
    assert 0.3 < gait.shape_of(KID)["childish"] < 0.8
    assert gait.shape_of(ADULT)["childish"] < 1e-9


def test_a_toddler_waddles_where_a_small_adult_merely_hurries():
    """Both are small. Only one has its weight up in its head."""
    tot, elf = walk(TODDLER), walk(ELF)
    assert tot["sway"] > elf["sway"] * 1.5, "a toddler rolls and an elf does not"
    assert tot["guard"] > 0.8 and elf["guard"] < 1e-9, "the arms are carried high"
    assert tot["gap"] / gait.shape_of(TODDLER)["leg"] > elf["gap"] / gait.shape_of(ELF)["leg"]
    assert tot["step"] / gait.shape_of(TODDLER)["leg"] < elf["step"] / gait.shape_of(ELF)["leg"]


def test_a_child_is_between_a_toddler_and_a_grown_person():
    tot, kid, adult = walk(TODDLER), walk(KID), walk(ADULT)
    assert tot["sway"] > kid["sway"] > adult["sway"]
    assert tot["guard"] > kid["guard"] > adult["guard"]


# --- what it tells a person ------------------------------------------------------------------------------

def test_it_says_in_words_what_about_the_body_changed_the_walk():
    assert "ordinary adult" in gait.describe(gait.shape_of(ADULT))
    assert "heavy" in gait.describe(gait.shape_of(HEAVY))
    assert "slim" in gait.describe(gait.shape_of(SLIM))
    assert "child" in gait.describe(gait.shape_of(TODDLER))
    assert "step rate" in gait.describe(gait.shape_of(ELF))


def test_every_number_that_comes_back_is_usable():
    for b in (ADULT, TALL, ELF, TODDLER, KID, HEAVY, SLIM, THIN):
        w = walk(b)
        assert w["speed"] > 0.1 and w["step"] > 0.05 and w["cadence"] > 0.3
        assert 0.02 < w["gap"] < 0.30
        assert 0.18 <= w["double"] <= 0.46
        assert 0.1 < w["swing"] < 3.0 and 0.3 < w["sway"] < 4.0 and w["bob"] > 0.2


def test_a_faster_pace_is_still_faster_on_every_body():
    import itertools
    paces = [(0.8, 0.55, 0.7, 0.0), (1.1, 0.62, 1.0, 0.0), (1.4, 0.70, 1.2, 0.02), (1.7, 0.78, 1.4, 0.05)]
    for b in (ELF, TODDLER, HEAVY, TALL):
        got = [gait.walk_like(gait.shape_of(b), p)["speed"] for p in paces]
        assert all(x < y for x, y in itertools.pairwise(got)), b


def test_an_average_build_is_not_called_heavy():
    """Calibrated on nine built characters: hip-to-leg runs 0.211 slim to 0.255 heavy, and setting the
    reference at the slim end called every character in the film heavy."""
    for b in (ADULT, body(hips=0.52 * 1.70 * gait.HIPS_REF * 1.04)):
        assert "heavy" not in gait.describe(gait.shape_of(b))
    assert "heavy" in gait.describe(gait.shape_of(body(hips=0.52 * 1.70 * gait.HIPS_REF * 1.12)))
