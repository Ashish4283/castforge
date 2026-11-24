"""Look a finished character's rig over and say whether it is fit to animate.

    blender -b --python-exit-code 1 -P blender/rig_check.py -- FILE.blend [--fix] [--json OUT]

Without `--fix` it only reports. With it, the two things that can be put right without rebuilding are put
right and the file is saved: skin vertices attached to no bone at all, and vertices pulled by more bones
than any exporter keeps (core/rigging.MOST). What it cannot fix - a missing control, missing visemes - it
says, because those come from the build.

The arithmetic is in `core/rigging.py`, which is pure and tested; this file only measures and applies.
"""
import argparse
import json
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from core import rigging  # noqa: E402

WANT = ["torso", "chest", "head", "neck", "hand_fk.L", "hand_fk.R", "hand_ik.L", "hand_ik.R",
        "upper_arm_parent.L", "upper_arm_parent.R", "foot_ik.L", "foot_ik.R",
        "thumb.01.L", "f_index.01.L", "DEF-spine.006", "jaw_master", "eye.L", "eye.R"]


def log(*a):
    print("CF:", *a, flush=True)


def deform_weights(obj):
    """{vertex: {bone: weight}} over the DEF- groups, for the SKIN only.

    The body mesh carries MakeHuman's helper geometry too - the cages that fit clothes, the joint cubes a
    rig is built from - and none of that is weighted or drawn. Counting it as unweighted skin reports
    sixteen faults that are not faults. The "body" vertex group is exactly the skin, as everywhere else."""
    names = {g.index: g.name for g in obj.vertex_groups}
    skin = next((g.index for g in obj.vertex_groups if g.name == "body"), None)
    out = {}
    for v in obj.data.vertices:
        if skin is not None and not any(g.group == skin for g in v.groups):
            continue
        out[v.index] = {names[g.group]: g.weight for g in v.groups
                        if names.get(g.group, "").startswith("DEF-") and g.weight > 0}
    return out


def look_over(rig, body):
    """Everything `core.rigging.problems` needs, measured on this file."""
    bones = {b.name for b in rig.data.bones}
    weights = deform_weights(body)
    over = sum(1 for w in weights.values() if len(rigging.keep_strongest(w)) < len([
        x for x in w.values() if x > rigging.TINY]))
    off = sum(1 for w in weights.values()
              if w and abs(sum(x for x in w.values() if x > rigging.TINY) - 1.0) > 0.01)
    keys = body.data.shape_keys.key_blocks if body.data.shape_keys else []
    return {
        "bones": len(bones),
        "deform": sum(1 for b in bones if b.startswith("DEF-")),
        "visemes": sum(1 for k in keys if k.name.lower().startswith("viseme")),
        "unweighted": len(rigging.strays(weights)),
        "over_four": over,
        "unnormalised": off,
        "missing": [b for b in WANT if b not in bones],
        "spare_armatures": sum(1 for o in bpy.data.objects if o.type == "ARMATURE" and o is not rig),
        "rig": rig.name,
        "body": body.name,
        "vertices": len(weights),
    }


def tidy(obj):
    """Keep the strongest few bones on every vertex and make the weights add up to one.

    Blender's own operators do this at C speed, and they do exactly what `core.rigging.keep_strongest`
    describes - which is the point of writing that function down: the audit measures against it, so if
    these two ever disagree the check says so instead of the character coming out mushy in a shot.

    "Clean" is checked on the skin, but the tidying is applied to the whole mesh: a helper vertex with
    nine tiny weights costs the same as a skin one."""
    import bpy as _bpy
    if _bpy.context.object and _bpy.context.object.mode != "OBJECT":
        _bpy.ops.object.mode_set(mode="OBJECT")
    for other in _bpy.context.selected_objects:
        other.select_set(False)
    obj.select_set(True)
    _bpy.context.view_layer.objects.active = obj
    before = sum(1 for w in deform_weights(obj).values()
                 if len([x for x in w.values() if x > rigging.TINY]) > rigging.MOST)
    _bpy.ops.object.vertex_group_limit_total(group_select_mode="BONE_DEFORM", limit=rigging.MOST)
    _bpy.ops.object.vertex_group_normalize_all(group_select_mode="BONE_DEFORM", lock_active=False)
    return before


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--fix", action="store_true", help="put right what can be put right, and save")
    ap.add_argument("--json", help="write the measurements here as well")
    args = ap.parse_args(argv)

    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(args.file))
    rigs = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if not rigs:
        raise SystemExit("CF: there is no rig in that file")
    rig = max(rigs, key=lambda o: len(o.data.bones))
    skinned = [o for o in bpy.data.objects
               if o.type == "MESH" and any(m.type == "ARMATURE" for m in o.modifiers)]
    if not skinned:
        raise SystemExit("CF: nothing in that file is attached to the rig")
    body = max(skinned, key=lambda o: len(o.data.vertices))

    facts = look_over(rig, body)
    log(f"{os.path.basename(args.file)}: {facts['rig']}, {facts['bones']} bones, "
        f"{facts['deform']} deforming, {facts['vertices']} skin vertices")
    if args.fix:
        for mesh in skinned:
            was = tidy(mesh)
            if was:
                log(f"{mesh.name}: {was} vertices were pulled by more than {rigging.MOST} bones")
        facts = look_over(rig, body)
        bpy.ops.wm.save_mainfile(filepath=os.path.abspath(args.file))
        log("saved")
    for line in rigging.problems(facts):
        log("PROBLEM", line)
    log(rigging.verdict(facts))
    report = {**facts, "problems": rigging.problems(facts), "verdict": rigging.verdict(facts)}
    json.dump(report, open(args.json or os.path.splitext(os.path.abspath(args.file))[0] + ".rig.json",
                           "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":        # imported by the build as well, for the same tidying
    main()
