"""What makes a rig fit to animate, as plain arithmetic (pure, tested; no bpy).

The rig itself is Rigify, generated in `blender/build_character.py`. This holds the two things about it
that are worth being exact and testable: how a vertex's bone weights should be tidied, and what counts as
a problem when a finished character is checked over (`blender/rig_check.py`, `castforge.py rig`).

Why tidy weights at all. A vertex pulled by nine bones is not a better vertex. Game and film rigs keep
four, because four is what every engine and exporter guarantees, because the extra ones are almost always
noise from automatic weighting, and because a vertex that is 0.02 attached to a far-off bone twitches when
that bone moves. Keeping the strongest four and sharing their weight back out to add up to one is what
Blender's own "Limit Total" and "Normalize All" do; this is that, written down so it can be tested.
"""

MOST = 4                  # bones that may pull one vertex
TINY = 0.005              # a weight below this is noise, not an attachment


def keep_strongest(weights, most=MOST, tiny=TINY):
    """{bone: weight} tidied: the strongest `most` kept, noise dropped, the rest sharing all of the pull.

    Ties are settled by name so the answer never depends on dictionary order. An empty answer means the
    vertex was not attached to anything worth keeping - the caller has to find it a home."""
    real = {b: float(w) for b, w in (weights or {}).items() if float(w) > tiny}
    if not real:
        return {}
    best = sorted(real.items(), key=lambda kv: (-kv[1], kv[0]))[:max(1, most)]
    total = sum(w for _b, w in best)
    return {b: w / total for b, w in best}


def strays(weights_by_vertex, tiny=TINY):
    """The vertices with nothing to hold them: they stay behind when the character moves."""
    return [v for v, w in weights_by_vertex.items()
            if not any(float(x) > tiny for x in (w or {}).values())]


def problems(facts):
    """Plain-language problems with a finished rig, worst first; empty when there is nothing to say.

    `facts` is what `blender/rig_check.py` measures. Everything here is a thing that shows up in a shot:
    a vertex left behind, a limb that cannot be posed, a mouth that cannot speak."""
    out = []
    missing = [b for b in facts.get("missing", [])]
    if missing:
        out.append(f"the rig has no {', '.join(missing)}: scenes that pose those will do nothing")
    if facts.get("unweighted"):
        out.append(f"{facts['unweighted']} skin vertices are attached to no bone at all - they stay behind "
                   f"when the character moves")
    over = facts.get("over_four", 0)
    if over:
        out.append(f"{over} vertices are pulled by more than {MOST} bones, which no exporter keeps and "
                   f"which makes the surface mushy where limbs meet the body")
    if facts.get("unnormalised"):
        out.append(f"{facts['unnormalised']} vertices have weights that do not add up to 1, so they move "
                   f"less (or more) than the bones that carry them")
    if facts.get("visemes", 0) < 15:
        out.append(f"only {facts.get('visemes', 0)} of the 15 visemes are there: lip-sync will be partial")
    # The metarig stays in the file on purpose - Rigify needs it to generate the rig again - so a second
    # armature is not a fault. It IS a trap: it sorts before the real rig by name, and a script that takes
    # the first armature it finds poses a skeleton nothing is attached to. Picking by bone count avoids it.
    return out


def verdict(facts):
    """One line for a person: is this character ready to animate?"""
    found = problems(facts)
    if not found:
        return f"ready: {facts.get('bones', 0)} bones, {facts.get('deform', 0)} of them deforming, " \
               f"{facts.get('visemes', 0)} visemes, every vertex attached to at most {MOST} bones"
    return f"{len(found)} thing(s) to fix: " + "; ".join(found)
