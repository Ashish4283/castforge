from blender import acting, director

FPS = 24


def line(who, t0, t1, kind="say", expression=None, listener=None):
    return {"who": who, "f0": int(t0 * FPS), "f1": int(t1 * FPS), "kind": kind, "expression": expression,
            "listener": listener}


def kinds(shots):
    return [(s["kind"], s["on"]) for s in shots]


def test_opens_wide_and_establishes_before_the_first_cut():
    shots = director.plan([line("maya", 0.2, 3.0)], fps=FPS, end=200)
    assert shots[0] == director.shot(1, "wide")
    assert shots[1]["frame"] >= 1 + director.ESTABLISH * FPS


def test_first_line_is_medium_then_close():
    shots = director.plan([line("maya", 3, 5), line("tom", 7, 9), line("maya", 11, 13)], fps=FPS, end=400)
    talking = [(k, on) for k, on in kinds(shots) if on]
    assert talking == [("medium", ["maya"]), ("medium", ["tom"]), ("close", ["maya"])]


def test_rapid_exchange_holds_a_two_shot():
    lines = [line("maya", 3.0, 3.8), line("tom", 4.0, 4.9), line("maya", 5.1, 6.0), line("tom", 6.2, 7.0)]
    shots = director.plan(lines, fps=FPS, end=300)
    assert kinds(shots) == [("wide", []), ("two_shot", ["maya", "tom"]), ("wide", [])]


def test_long_line_gets_one_reaction_cutaway():
    shots = director.plan([line("arthur", 3, 11, listener="manager")], fps=FPS, end=400)
    assert kinds(shots)[1:4] == [("medium", ["arthur"]), ("close", ["manager"]), ("medium", ["arthur"])]


def test_strong_feelings_and_thoughts_push_in():
    shots = director.plan([line("maya", 3, 5, expression="angry"), line("maya", 8, 10, kind="think")],
                          fps=FPS, end=400, strong=acting.STRONG)
    assert [s["move"] for s in shots if s["on"]] == ["push_in", "push_in"]


def test_narration_never_cuts():
    shots = director.plan([line(None, 0.5, 6, kind="narrate")], fps=FPS, end=200)
    assert kinds(shots) == [("wide", [])]


def test_pause_returns_to_wide_and_no_shot_is_too_short():
    lines = [line("maya", 3, 5), line("tom", 5.3, 7), line("maya", 9.5, 11)]
    shots = director.plan(lines, fps=FPS, end=400)
    assert ("wide", []) in kinds(shots)[2:]
    gaps = [b["frame"] - a["frame"] for a, b in zip(shots, shots[1:])]
    assert min(gaps) >= director.MIN_SHOT * FPS


def test_walks_follow_the_walker_and_resume():
    shots = director.plan([line("maya", 3, 5)], moves=[{"who": "tom", "f0": 150, "f1": 220}], fps=FPS, end=400)
    follow = [s for s in shots if s["kind"] == "follow"]
    assert follow and follow[0]["on"] == ["tom"] and follow[0]["frame"] == 150
    assert shots[-1]["frame"] == 232


def test_camera_step_overrides_then_hands_back():
    lines = [line("maya", 3, 5), line("tom", 6, 8)]
    forced = [{"f0": 100, "seconds": 2.0, "shot": "close", "on": "maya", "move": "handheld"}]
    shots = director.plan(lines, forced=forced, fps=FPS, end=400)
    f = next(s for s in shots if s["forced"])
    assert (f["frame"], f["kind"], f["on"], f["move"]) == (100, "close", ["maya"], "handheld")
    assert not any(100 < s["frame"] < 148 for s in shots)
    assert any(s["frame"] == 148 for s in shots)


def test_classic_mode_is_a_close_up_per_line():
    shots = director.plan([line("maya", 0.2, 2), line("tom", 2.3, 4)], fps=FPS, end=200, mode="classic")
    assert kinds(shots) == [("wide", []), ("close", ["maya"]), ("close", ["tom"]), ("wide", [])]


def test_none_mode_stays_wide():
    assert kinds(director.plan([line("maya", 3, 5)], fps=FPS, end=200, mode="none")) == [("wide", [])]
