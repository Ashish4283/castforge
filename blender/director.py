"""Which shot when: CastForge's automatic director. It turns a scene's spoken lines, walks and explicit camera
steps into a shot list; scene_kit.py builds a camera for each shot. No Blender here, so tests/test_director.py
checks the rules on made-up scenes.

"shots": "auto" (default)
  1. The scene opens on the wide shot and holds it for at least ESTABLISH seconds.
  2. A speaker's first line is a medium shot (waist up), their later lines close-ups. Thoughts, strong feelings
     and long lines push in slowly.
  3. A rapid exchange (short lines, quick turns between two people) holds one two-shot instead of cutting on
     every line.
  4. A long line with someone listening gets one reaction cutaway to the listener, then goes back.
  5. No shot shorter than MIN_SHOT; narration never cuts; walks follow the walker.
  6. After more than WIDE_GAP seconds without dialogue, back to the wide shot.
Fight beats (strike steps) get their own coverage: a wide two-shot so the blow reads in space, a tight
shot on the contact frame, then a reaction shot of whoever was hit. Cuts run faster than in dialogue.
"shots": "classic" is v1: a close-up on every line, back to wide after a pause, walks followed.
A {"do": "camera"} step overrides either for its duration.

Inputs (frames): lines [{"f0", "f1", "who", "kind": say|think|narrate, "expression", "listener"}] in script
order; moves [{"who", "f0", "f1"}]; beats [{"who", "target", "f0", "f1", "contact"}] fight beats;
forced [{"f0", "seconds" or None, "shot", "on", "move", "lens"}].
Output: [{"frame", "kind", "on": [names], "move", "lens", "forced"}] sorted by frame, the first at frame 1.
"""
ESTABLISH, MIN_SHOT, RAPID_LINE, RAPID_GAP = 2.0, 1.0, 1.5, 1.0
REACTION_LINE, REACTION_LEN, WIDE_GAP, PUSH_LINE = 5.0, 1.2, 1.0, 6.0
# fights: cuts are allowed to run faster, and each beat gets wind-up / contact / reaction
FIGHT_MIN_SHOT, FIGHT_LEAD, FIGHT_REACTION = 0.5, 0.5, 0.7


def shot(frame, kind, on=(), move="static", lens=None, forced=False):
    return {"frame": int(frame), "kind": kind, "on": list(on), "move": move, "lens": lens, "forced": forced}


def _rapid(a, b, fps):
    short = (a["f1"] - a["f0"]) <= RAPID_LINE * fps and (b["f1"] - b["f0"]) <= RAPID_LINE * fps
    return short and a["who"] != b["who"] and b["f0"] - a["f1"] < RAPID_GAP * fps


def _dialogue(lines, fps, strong):
    est = 1 + int(round(ESTABLISH * fps))
    out, seen = [], set()
    talk = [ln for ln in lines if ln["kind"] != "narrate" and ln.get("who")]
    i = 0
    while i < len(talk):
        j = i
        while j + 1 < len(talk) and _rapid(talk[j], talk[j + 1], fps):
            j += 1
        run = talk[i:j + 1]
        speakers = list(dict.fromkeys(ln["who"] for ln in run))
        if len(run) >= 2 and len(speakers) >= 2:
            out.append(shot(max(run[0]["f0"], est), "two_shot", speakers[:2]))
            seen.update(speakers)
        else:
            ln = run[0]
            dur = (ln["f1"] - ln["f0"]) / fps
            kind = "close" if ln["who"] in seen or ln["kind"] == "think" else "medium"
            seen.add(ln["who"])
            push = ln["kind"] == "think" or ln.get("expression") in strong or dur > PUSH_LINE
            start = max(ln["f0"], est)
            if start < ln["f1"]:
                out.append(shot(start, kind, [ln["who"]], "push_in" if push else "static"))
            if dur > REACTION_LINE and ln.get("listener") and ln["kind"] == "say":
                cut = ln["f0"] + int(round((dur / 2 - REACTION_LEN / 2) * fps))
                if cut > start + MIN_SHOT * fps:
                    out.append(shot(cut, "close", [ln["listener"]]))
                    out.append(shot(cut + int(round(REACTION_LEN * fps)), kind, [ln["who"]]))
        end = run[-1]["f1"]
        i = j + 1
        if i >= len(talk) or talk[i]["f0"] - end > WIDE_GAP * fps:
            out.append(shot(end + 4, "wide"))
    return out


def _classic(lines, fps):
    out = []
    talk = [ln for ln in lines if ln["kind"] != "narrate" and ln.get("who")]
    for n, ln in enumerate(talk):
        out.append(shot(ln["f0"], "close", [ln["who"]], "push_in" if ln["kind"] == "think" else "static"))
        nxt = talk[n + 1]["f0"] if n + 1 < len(talk) else None
        if nxt is None or nxt > ln["f1"] + fps:
            out.append(shot(ln["f1"] + 4, "wide"))
    return out


def active(shots, frame):
    """The shot showing at frame (shots sorted)."""
    cur = shots[0]
    for s in shots:
        if s["frame"] > frame:
            break
        cur = s
    return cur


def _replace(shots, f0, f1, new):
    """Put `new` over [f0, f1): drop what starts inside, resume what would have been showing at f1."""
    shots = sorted(shots, key=lambda s: s["frame"])
    resume = dict(active(shots, f1), frame=f1)
    kept = [s for s in shots if not (f0 <= s["frame"] < f1)]
    return sorted(kept + [new, resume], key=lambda s: s["frame"])


def _fight(beats, fps):
    """Coverage for fight beats: the swing reads in a two-shot, the blow lands tight, the hit registers on
    the one who took it. Beats close together share the wide, so a flurry does not cut on every frame."""
    out, prev_end = [], None
    for b in sorted(beats, key=lambda x: x["f0"]):
        pair = [b["who"], b["target"]]
        lead = int(round(FIGHT_LEAD * fps))
        wide_at = max(1, b["contact"] - lead)
        if prev_end is None or wide_at - prev_end > fps:          # a fresh exchange: re-establish the space
            out.append(shot(max(1, b["f0"]), "two_shot", pair))
        out.append(shot(wide_at, "medium", pair, move="push_in"))
        out.append(shot(b["contact"], "close", [b["target"]]))
        out.append(shot(b["contact"] + int(round(FIGHT_REACTION * fps)), "two_shot", pair))
        prev_end = b["f1"]
    return out


def plan(lines, moves=(), forced=(), fps=24, end=None, mode="auto", follow=True, strong=(), beats=()):
    """strong: expressions that make the director move in (acting.STRONG); beats: fight beats."""
    shots = [shot(1, "wide")]
    if mode == "auto":
        shots += _dialogue(lines, fps, strong)
    elif mode == "classic":
        shots += _classic(lines, fps)
    shots.sort(key=lambda s: s["frame"])
    if follow:
        for m in moves:
            if m["f1"] - m["f0"] >= fps:          # very short moves stay on the current shot
                shots = _replace(shots, m["f0"], m["f1"] + 12, shot(m["f0"], "follow", [m["who"]]))
    for b in sorted(beats, key=lambda x: x["f0"]):               # a fight overrides follow and dialogue
        shots = _replace(shots, b["f0"], b["f1"], shot(b["f0"], "two_shot", [b["who"], b["target"]]))
    if beats and mode != "classic":
        shots += _fight(beats, fps)
        shots.sort(key=lambda s: s["frame"])
    forced = sorted(forced, key=lambda c: c["f0"])
    for n, c in enumerate(forced):
        nxt = forced[n + 1]["f0"] if n + 1 < len(forced) else None
        f1 = c["f0"] + int(round(c["seconds"] * fps)) if c.get("seconds") else (nxt or end or c["f0"] + 10 ** 9)
        if nxt is not None:
            f1 = min(f1, nxt)
        if c["shot"] == "auto":
            continue
        on = c.get("on") or []
        on = [on] if isinstance(on, str) else list(on)
        shots = _replace(shots, c["f0"], f1, shot(c["f0"], c["shot"], on, c.get("move") or "static",
                                                  c.get("lens"), forced=True))
    floor = MIN_SHOT if mode == "auto" else 0.0
    return _tidy(shots, fps, end, floor, [(b["f0"], b["f1"]) for b in beats], FIGHT_MIN_SHOT)


def _tidy(shots, fps, end, min_shot, fight_spans=(), fight_min=0.0):
    """Drop shots past the end, too-short shots (never a forced one) and repeats of the shot already showing.
    Inside a fight span, cuts may run as short as fight_min."""
    out = []
    for s in sorted(shots, key=lambda s: s["frame"]):
        if end is not None and s["frame"] >= end:
            continue
        s = dict(s, frame=max(1, s["frame"]))
        floor = fight_min if any(a <= s["frame"] <= b for a, b in fight_spans) else min_shot
        while out and s["frame"] - out[-1]["frame"] < floor * fps:
            prev = out[-1]
            if prev["frame"] == 1 or prev["forced"]:
                if not s["forced"]:
                    s = None
                break
            out.pop()                              # the earlier shot was too short: the new one wins
        if s is None:
            continue
        if out and all(out[-1][k] == s[k] for k in ("kind", "on", "move", "lens")):
            continue
        out.append(s)
    return out
