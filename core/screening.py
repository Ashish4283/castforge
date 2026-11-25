"""Can this character act? A screen test for a rig, before anybody spends a film on it.

(pure, tested; no bpy - `blender/screen_test.py` does the posing and measuring, this says what it means)

`core/rigging.py` already asks whether a rig is sound: are the bones there, is every vertex attached, is
anything pulled by nine bones at once. That is a health check. It does not ask the question that actually
matters, which is whether this person can DO the things a scene will ask of them - walk, run, jump, turn
their head, bend, work their wrists and fingers - without the surface tearing.

Finding that out in the middle of a film is the expensive way. A shot is rendered, the shoulder looks
melted, and the character is rebuilt and every shot it appears in is rendered again. So it is asked here,
once, in a few seconds: every move in the scene vocabulary (`core/schema.ACTIONS`, `acting.GESTURES`) is
posed on the rig headlessly and measured, and the character is either an approved actor or it is not.

What is measured, and why each one is a thing you would otherwise see in a shot:

  missing   a control the move needs is not in the rig. The scene step runs and does nothing at all.
  frozen    the control is there but would not move when it was asked to - a lock or a constraint.
            Same symptom, different cause, and the fix is different, so they are counted apart.
  reach     how far the move actually got, as a fraction of what was asked. Short of 1 means something
            is holding it back: a limit, a parent, a solver that will not converge.
  stretch   the worst any ONE edge of skin was pulled out of shape, and `rough_skin`, how much of the
            surface was pulled about at all. Together they catch bad weighting: a shoulder painted onto
            too many bones does not tear at rest, it tears when the arm goes up. Judge by the fraction -
            every armpit has one hot edge. The note on the limits below says what the numbers look like.
  moved     how far the skin actually travelled. A control can turn perfectly and still move nothing,
            if what it drives is not what the skin is attached to - and then the scene step runs, the
            numbers all look right, and the character stands there. Only a measurement of the SURFACE
            catches that, which is why reach alone is not enough.
  slide     for a walk: how far a foot that should be planted on the ground drifted. A sliding foot is
            the single most obvious tell that a character was not animated properly.
"""

# Where a surface stops looking like skin.
MOVED_OK = 0.01           # metres of skin movement below which a move did not really happen
#
# Not the WORST edge. Measured across seven characters this pipeline has built, the worst edge in the arms
# pose runs from 2.4x to 8.7x and sits at 3.7x in the middle - every armpit has one hot edge, and a limit
# anywhere in that range either fails everybody or nobody. What tells characters apart is how MUCH of the
# surface is pulled about: the fraction of skin edges stretched past 1.8x, which is 0.00% for most moves
# on most of them, about 0.20% at the shoulders, and - on the one character that was visibly worse than
# the rest - 0.40% at the shoulders and 0.13% on a simple nod, where everybody else is at zero.
#
# So these are set just above the spread of characters that look right, and the worst edge is reported
# beside them as context rather than used as the gate.
ROUGH_SKIN = 0.0035       # fraction of the skin pulled past 1.8x before a joint starts to look soft
TORN_SKIN = 0.012         # ...and before it is a melted joint rather than a crease
STRETCH_SHOW = 2.5        # a worst edge past this is worth saying out loud, though it is not the gate
REACH_OK = 0.90           # a move that only gets nine tenths of the way is still the move
REACH_BAD = 0.60
SLIDE_OK = 0.015          # metres a planted foot may drift over a step and still read as planted
FINGERS = ("index", "middle", "ring", "pinky")
SEGMENTS = ("01", "02", "03")


def _both(name):
    return [f"{name}.L", f"{name}.R"]


_HANDS = [f"f_{f}.{s}.{side}" for f in FINGERS for s in SEGMENTS for side in "LR"]
_THUMBS = [f"thumb.{s}.{side}" for s in SEGMENTS for side in "LR"]

# Every move a scene can ask for, what it needs to do it with, and what goes wrong in a shot when it
# cannot. The bone names are the ones `scene_kit.Actor` actually drives - if this list and that code ever
# disagree, the screen test is checking a rig nobody uses.
MOVES = {
    "stand": {
        "title": "Stand still",
        "why": "every shot starts and ends here; if the rest pose is wrong, everything built on it is",
        "needs": ["torso"] + _both("foot_ik") + _both("upper_arm_parent"),
    },
    "walk": {
        "title": "Walk",
        "why": "the commonest thing anybody does on screen, and a foot that slides gives it away at once",
        "needs": ["torso"] + _both("foot_ik") + _both("foot_heel_ik") + _both("thigh_parent"),
        "watch": "slide",
    },
    "run": {
        "title": "Run",
        "why": "a longer stride and a deeper lean than a walk, which is where a hip gives out if it will",
        "needs": ["torso"] + _both("foot_ik") + _both("thigh_parent"),
        "watch": "slide",
    },
    "jump": {
        "title": "Jump",
        "why": "both feet leave the ground and land again: the one move that tests the hips under load",
        "needs": ["torso"] + _both("foot_ik") + _both("thigh_parent"),
    },
    "crouch": {
        "title": "Crouch and stand up",
        "why": "ducking, sitting, picking something up and the 'drop' posture are all this move",
        "needs": ["torso"] + _both("thigh_parent") + _both("foot_ik"),
    },
    "bend": {
        "title": "Bend at the waist",
        "why": "bowing, reaching for the floor, leaning over a table; it folds the whole torso",
        "needs": ["torso", "chest", "head"],
    },
    "turn_head": {
        "title": "Turn the head",
        "why": "looking at whoever is speaking. A neck that tears here tears in every conversation",
        "needs": ["head", "neck", "chest"],
    },
    "nod": {
        "title": "Nod and shake",
        "why": "yes and no, and the small movements the life loop puts under every line of dialogue",
        "needs": ["head", "neck"],
    },
    "look": {
        "title": "Move the eyes",
        "why": "gaze is what makes someone look alive rather than embalmed",
        "needs": ["eye_common"] + _both("eye"),
        "surface": False,              # the eyes are their own meshes; the face barely moves with them
    },
    "arms": {
        "title": "Raise and swing the arms",
        "why": "every gesture there is - waving, pointing, clapping, reaching - is built on this",
        "needs": _both("upper_arm_fk") + _both("forearm_fk") + _both("upper_arm_parent"),
    },
    "wrist": {
        "title": "Work the wrists",
        "why": "a hand that cannot turn at the wrist makes every gesture read as a mannequin's",
        "needs": _both("hand_fk") + _both("hand_ik"),
    },
    "fingers": {
        "title": "Open and close the fingers",
        "why": "holding a prop, making a fist, pointing. A hand that cannot close cannot carry anything",
        "needs": _HANDS + _THUMBS,
    },
    "grip": {
        "title": "Grip something",
        "why": "a prop is held by the fingers closing round it; without this it floats in the palm",
        "needs": [f"f_index.{s}.{side}" for s in SEGMENTS for side in "LR"]
                 + [f"thumb.{s}.{side}" for s in SEGMENTS for side in "LR"],
    },
    "speak": {
        "title": "Speak",
        "why": "fifteen mouth shapes; short of them, lip-sync is partial and it shows on every word",
        "needs": ["jaw_master"],
        "shapes": ("viseme", 15),
        "surface": False,              # a viseme is a shape key, not a bone moving the body
    },
    "express": {
        "title": "Change expression",
        "why": "a face that cannot change is a face nobody believes",
        "shapes": ("expr", 6),
        "surface": False,
    },
}
ORDER = list(MOVES)


def every_bone():
    """Every control the screen test will reach for, deduplicated - what a rig has to carry."""
    out = []
    for move in MOVES.values():
        for bone in move.get("needs", ()):
            if bone not in out:
                out.append(bone)
    return out


# What a joint marker is called when you are telling somebody where their character went soft. A number
# and a 3D coordinate is not something anybody can act on; "the right shoulder" is.
PLACES = {
    "joint-l-shoulder": "the left shoulder", "joint-r-shoulder": "the right shoulder",
    "joint-l-clavicle": "the left collarbone", "joint-r-clavicle": "the right collarbone",
    "joint-l-scapula": "the left shoulder blade", "joint-r-scapula": "the right shoulder blade",
    "joint-l-elbow": "the left elbow", "joint-r-elbow": "the right elbow",
    "joint-l-hand": "the left wrist", "joint-r-hand": "the right wrist",
    "joint-l-knee": "the left knee", "joint-r-knee": "the right knee",
    "joint-l-ankle": "the left ankle", "joint-r-ankle": "the right ankle",
    "joint-l-upper-leg": "the left hip", "joint-r-upper-leg": "the right hip",
    "joint-neck": "the neck", "joint-head": "the head", "joint-head-2": "the crown",
    "joint-jaw": "the jaw", "joint-pelvis": "the waist",
    "joint-spine-1": "the chest", "joint-spine-2": "the midriff", "joint-spine-3": "the belly",
    "joint-ground": "the feet",
}


def where(marker):
    """A place a person can look at, from a joint marker's name."""
    if not marker:
        return None
    return PLACES.get(marker) or marker.replace("joint-", "").replace("-", " ")


def look(name, facts):
    """Plain-language problems with one move; empty when the character can do it.

    `facts` is what `blender/screen_test.py` measured while it held the pose."""
    move = MOVES.get(name)
    if not move:
        return [f"{name!r} is not a move this screen test knows"]
    out = []
    missing = list(facts.get("missing") or ())
    if missing:
        shown = ", ".join(missing[:4]) + (f" and {len(missing) - 4} more" if len(missing) > 4 else "")
        out.append(f"no {shown}: a scene that asks for this will do nothing at all")
    frozen = list(facts.get("frozen") or ())
    if frozen:
        shown = ", ".join(frozen[:4]) + (f" and {len(frozen) - 4} more" if len(frozen) > 4 else "")
        out.append(f"{shown} would not move when asked - something is locked or constrained")
    want, got = move.get("shapes"), facts.get("shapes")
    if want and got is not None and got < want[1]:
        out.append(f"only {got} of the {want[1]} face shapes this needs are there")
    reach = facts.get("reach")
    if reach is not None and not missing and reach < REACH_OK:
        out.append(f"it only gets {reach * 100:.0f}% of the way: something is holding it back")
    moved = facts.get("moved")
    if moved is not None and not missing and not frozen and moved < MOVED_OK:
        out.append(f"the controls turn but the body does not: only {moved * 1000:.0f} mm of skin moves, "
                   f"so a scene asking for this would look like nothing happened")
    rough = facts.get("rough_skin")
    stretch = facts.get("stretch")
    if rough is not None and rough > ROUGH_SKIN:
        worst = f", the worst of it {stretch:.1f}x" if stretch and stretch > STRETCH_SHOW else ""
        spot = where(facts.get("worst_near"))
        at = f" at {spot}" if spot else ""
        out.append(f"{rough * 100:.2f}% of the skin is pulled out of shape doing this{worst}{at}"
                   f"{' - the joint melts' if rough > TORN_SKIN else ' - it goes soft where it bends'}")
    slide = facts.get("slide")
    if move.get("watch") == "slide" and slide is not None and slide > SLIDE_OK:
        out.append(f"the planted foot drifts {slide * 100:.1f} cm: it will look like skating")
    return out


def bad(name, facts):
    """True when a move fails outright rather than merely wanting work.

    The line between the two is whether a shot would be unusable or only disappointing: a missing control
    or a torn surface is unusable; a wrist that reaches 80% of the way is not."""
    move = MOVES.get(name) or {}
    if facts.get("missing") or facts.get("frozen"):
        return True
    want, got = move.get("shapes"), facts.get("shapes")
    if want and got is not None and got < want[1]:
        return True
    if (facts.get("rough_skin") or 0) > TORN_SKIN:
        return True
    if facts.get("reach") is not None and facts["reach"] < REACH_BAD:
        return True
    if facts.get("moved") is not None and facts["moved"] < MOVED_OK:
        return True
    return False


def card(results):
    """One row per move, in the order they are tested: what it is, whether it passed, and why not.

    `results` is {move: facts}. A move that was not tested at all is reported as such rather than
    quietly passing - a screen test that skips the hard half is not a screen test."""
    out = []
    for name in ORDER:
        move = MOVES[name]
        facts = results.get(name)
        if facts is None:
            out.append({"move": name, "title": move["title"], "why": move["why"],
                        "state": "untested", "problems": ["this move was not tested"]})
            continue
        problems = look(name, facts)
        state = "failed" if bad(name, facts) else ("works" if not problems else "rough")
        out.append({"move": name, "title": move["title"], "why": move["why"], "state": state,
                    "problems": problems, "stretch": facts.get("stretch"),
                    "worst_near": where(facts.get("worst_near")),
                    "rough_skin": facts.get("rough_skin"), "reach": facts.get("reach"),
                    "moved": facts.get("moved"), "slide": facts.get("slide")})
    return out


def verdict(results):
    """{approved, line, passed, rough, failed} - is this character fit to put in a film?

    Approved means every move works. "Rough" moves do not block it: they are things that will look
    slightly wrong, and whether that matters is the director's call, not this function's."""
    rows = card(results)
    failed = [r for r in rows if r["state"] in ("failed", "untested")]
    rough = [r for r in rows if r["state"] == "rough"]
    passed = [r for r in rows if r["state"] == "works"]
    if failed:
        worst = ", ".join(r["title"].lower() for r in failed[:3])
        line = (f"not ready: {len(failed)} of {len(rows)} moves fail ({worst}"
                f"{', ...' if len(failed) > 3 else ''})")
    elif rough:
        line = (f"approved, with {len(rough)} rough: "
                + ", ".join(r["title"].lower() for r in rough[:3])
                + (", ..." if len(rough) > 3 else ""))
    else:
        line = f"approved: all {len(rows)} moves work, and nothing tears doing any of them"
    return {"approved": not failed, "line": line, "passed": len(passed),
            "rough": len(rough), "failed": len(failed), "rows": rows}
