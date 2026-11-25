"""CastForge build stage: character spec (from analyze_photo.py) -> rigged, dressed, lip-sync-ready .blend.

Free and local: a complete MPFB (MakeHuman) body, so the back, sides and hidden parts are a real
body model rather than guessed pixels. The photo drives body shape, skin tone, hair and clothing
colours; the user supplies what a photo can't settle (gender, age, height).

    blender -b --factory-startup -P build_character.py -- --spec spec.json --out char.blend
        --gender male|female --age 30 --height-cm 178 [--preview dir]

Rest pose is MakeHuman's A-pose. The rig is Rigify; face has Meta/Oculus visemes (lip-sync) and
ARKit face units as shape keys.
"""
import argparse
import colorsys
import importlib
import json
import os
import sys

import addon_utils
import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--spec", help="photo spec from analyze_photo.py")
ap.add_argument("--design", help="character design JSON (no photo): see docs/GEMINI_CHARACTER_PROMPT.md")
ap.add_argument("--out", required=True)
ap.add_argument("--gender", choices=["male", "female"])
ap.add_argument("--age", type=float)
ap.add_argument("--height-cm", type=float)
ap.add_argument("--preview")
ap.add_argument("--hair", help="MPFB hair asset name (overrides the automatic pick), or 'none'")
args = ap.parse_args(argv)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from core import appearance, config, rigging, wardrobe            # noqa: E402  every face and body shape, in one table
# body build presets for designed characters: MakeHuman weight / muscle / proportions
BUILDS = {"slim": (0.25, 0.4, 0.6), "average": (0.5, 0.5, 0.5), "athletic": (0.4, 0.75, 0.75),
          "heavy": (0.85, 0.45, 0.4), "muscular": (0.55, 0.95, 0.7)}
DESIGN = None
if args.design:
    DESIGN = json.load(open(args.design, encoding="utf-8"))

    def rgb(h):
        h = (h or "").lstrip("#")
        return [int(h[i:i + 2], 16) for i in (0, 2, 4)] if len(h) == 6 else None

    hair = DESIGN.get("hair", {})
    outfit = DESIGN.get("outfit", {})
    args.gender = args.gender or DESIGN.get("gender")
    args.age = args.age or float(DESIGN.get("age") or 0) or None
    args.height_cm = args.height_cm or float(DESIGN.get("height_cm") or 0) or None
    if hair.get("style") and hair["style"] != "auto":
        # a style the designer offers ("crew_cut") becomes its asset; anything else is taken as an asset
        # name already, which is how a design could ask for one before the styles had names
        args.hair = args.hair or appearance.HAIR_STYLES.get(hair["style"], hair["style"])
    colours = {"skin": rgb(DESIGN.get("skin")), "hair": rgb(hair.get("color")), "top": rgb(outfit.get("top")),
               "bottom": rgb(outfit.get("bottom")), "shoes": rgb(outfit.get("shoes"))}
    if args.spec:
        # a photo character with a design on top: the photo gives body, face and colours; the design adds
        # hat, beard, costume and replaces what it states (a colour, the garment, the hair length)
        spec = json.load(open(args.spec))
        spec["colours"].update({k: v for k, v in colours.items() if v})
        spec["clothing"].update({k: outfit[k] for k in ("garment", "sleeves") if outfit.get(k)})
        if hair.get("length"):
            spec["hair_length"] = hair["length"]
    else:
        spec = {"ratios": {}, "face": None, "colours": colours,
                "clothing": {"garment": outfit.get("garment", "trousers"), "sleeves": outfit.get("sleeves", "long")},
                "hair_length": hair.get("length", "short")}
elif args.spec:
    spec = json.load(open(args.spec))
else:
    sys.exit("give --spec (from a photo) or --design (a character design)")
if not (args.gender and args.age and args.height_cm):
    sys.exit("gender, age and height are needed (as options, or in the design)")
index = json.load(open(os.path.join(HERE, "..", "asset_index.json")))

bpy.ops.wm.read_factory_settings(use_empty=True)
addon_utils.enable("rigify", default_set=True)
MPFB = next(m.__name__ for m in addon_utils.modules() if m.__name__.endswith(".mpfb"))
addon_utils.enable(MPFB, default_set=True)


def svc(module, cls):
    return getattr(importlib.import_module(f"{MPFB}.services.{module}"), cls)


HumanService = svc("humanservice", "HumanService")
TargetService = svc("targetservice", "TargetService")
AssetService = svc("assetservice", "AssetService")
RigService = svc("rigservice", "RigService")
FaceService = svc("faceservice", "FaceService")
ObjectService = svc("objectservice", "ObjectService")
HumanObjectProperties = importlib.import_module(f"{MPFB}.entities.objectproperties").HumanObjectProperties


def log(*a):
    print("CF:", *a, flush=True)


# --- body -------------------------------------------------------------------------------------
def age_macro(years):
    """MakeHuman's age macro: 0 -> 1 y, 0.1875 -> 11 y, 0.5 -> 25 y, 1 -> 90 y."""
    pts = [(1, 0.0), (11, 0.1875), (25, 0.5), (90, 1.0)]
    years = min(max(years, 1), 90)
    for (y0, m0), (y1, m1) in zip(pts, pts[1:]):
        if years <= y1:
            return m0 + (m1 - m0) * (years - y0) / (y1 - y0)
    return 1.0


macros = TargetService.get_default_macro_info_dict()
macros["gender"] = 1.0 if args.gender == "male" else 0.0
macros["age"] = age_macro(args.age)
human = HumanService.create_human(macro_detail_dict=macros)
human.name = "Body"

groups = {g.name: g.index for g in human.vertex_groups}
members = {}
for v in human.data.vertices:
    for g in v.groups:
        members.setdefault(g.group, []).append(v.index)
JOINTS = ["joint-l-shoulder", "joint-r-shoulder", "joint-l-upper-leg", "joint-r-upper-leg",
          "joint-l-ankle", "joint-r-ankle"]
joint_idx = {j: np.array(members[groups[j]]) for j in JOINTS}
body_idx = np.array(members[groups["body"]])
mask_mod = human.modifiers.get("Hide helpers")


def coords():
    """Vertex positions with the current shape keys (helpers included)."""
    if mask_mod:
        mask_mod.show_viewport = False
    deps = bpy.context.evaluated_depsgraph_get()
    ev = human.evaluated_get(deps)
    me = ev.to_mesh()
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    ev.to_mesh_clear()
    if mask_mod:
        mask_mod.show_viewport = True
    return co.reshape(-1, 3)


def measure():
    co = coords()
    body = co[body_idx]
    h = body[:, 2].max() - body[:, 2].min()
    j = {k: co[i].mean(axis=0) for k, i in joint_idx.items()}
    sh_z = (j["joint-l-shoulder"][2] + j["joint-r-shoulder"][2]) / 2
    hip_z = (j["joint-l-upper-leg"][2] + j["joint-r-upper-leg"][2]) / 2
    hip_half = abs(j["joint-l-upper-leg"][0] - j["joint-r-upper-leg"][0]) / 2

    def slice_width(z):
        band = body[(abs(body[:, 2] - z) < 0.01 * h) & (abs(body[:, 0]) < 3.2 * hip_half)]
        return band[:, 0].max() - band[:, 0].min() if len(band) else None

    waist_z = sh_z + 0.62 * (hip_z - sh_z)
    return h, {
        "shoulder_width": abs(j["joint-l-shoulder"][0] - j["joint-r-shoulder"][0]) / h,
        "hip_width": 2 * hip_half / h,
        "leg_length": (hip_z - body[:, 2].min()) / h,
        "torso_length": (sh_z - hip_z) / h,
        "waist_silhouette": (slice_width(waist_z) or 0) / h,
        "hip_silhouette": (slice_width(hip_z) or 0) / h,
    }


def set_macros(**kw):
    for k, v in kw.items():
        HumanObjectProperties.set_value(k, float(v), entity_reference=human)
    TargetService.reapply_macro_details(human)


# photo ratios, corrected by the calibration of MediaPipe-on-renders vs model joints
target = dict(spec["ratios"])
calib_path = os.path.join(HERE, "..", "calibration.json")
calib = json.load(open(calib_path)) if os.path.exists(calib_path) else {}
for k, bias in calib.get("bias", {}).items():
    if target.get(k) is not None:
        target[k] -= bias
WEIGHTS = {"shoulder_width": 3.0, "hip_width": 2.0, "leg_length": 1.0, "torso_length": 1.0,
           "waist_silhouette": 2.0, "hip_silhouette": 2.0}


def error():
    _, m = measure()
    return sum(WEIGHTS[k] * ((m[k] - target[k]) / max(target[k], 1e-3)) ** 2
               for k in WEIGHTS if target.get(k) is not None)


best = (error(), {"weight": 0.5, "muscle": 0.5, "proportions": 0.5})
FIT = not DESIGN or bool(args.spec)     # a photo shapes the body; a design alone uses its build preset
if not FIT:
    wt, mu, pr = BUILDS.get(DESIGN.get("build", "average"), BUILDS["average"])
    best = (0.0, {"weight": wt, "muscle": mu, "proportions": pr})
for weight in ((0.15, 0.35, 0.5, 0.65, 0.85) if FIT else ()):
    for muscle in (0.25, 0.5, 0.75):
        for proportions in (0.0, 0.5, 1.0):
            set_macros(weight=weight, muscle=muscle, proportions=proportions)
            e = error()
            if e < best[0]:
                best = (e, {"weight": weight, "muscle": muscle, "proportions": proportions})
# refine around the best grid point
step = {"weight": 0.08, "muscle": 0.1, "proportions": 0.2}
for _ in range(2 if FIT else 0):
    for k in ("weight", "muscle", "proportions"):
        for d in (-step[k], step[k]):
            trial = dict(best[1]); trial[k] = min(max(trial[k] + d, 0.0), 1.0)
            set_macros(**trial)
            e = error()
            if e < best[0]:
                best = (e, trial)
        step[k] /= 2
set_macros(**best[1])
log("body fit", best[1], f"error {best[0]:.4f}")

# height: bisect MakeHuman's height macro to the requested stature
want = args.height_cm / 100
lo, hi = 0.0, 1.0
for _ in range(10):
    midv = (lo + hi) / 2
    set_macros(height=midv)
    h, _ = measure()
    lo, hi = (midv, hi) if h < want else (lo, midv)
h, final = measure()
log(f"height {h:.3f} m (asked {want:.3f})", {k: round(v, 3) for k, v in final.items()})
if abs(h - want) > 0.02:
    log("WARNING height outside MakeHuman's range for this age/gender; clamped")
lowest = ObjectService.get_lowest_point(human)
human.location.z -= lowest
bpy.ops.object.select_all(action="DESELECT")
human.select_set(True)
bpy.context.view_layer.objects.active = human
bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)
_co = coords()
hip_z = float(np.mean([_co[joint_idx[j]].mean(axis=0)[2] for j in ("joint-l-upper-leg", "joint-r-upper-leg")]))

# --- face likeness: fit MakeHuman face shapes to the photo's landmarks, then map the photo's ---
# --- face onto the head (see calibrate_face.py for how landmarks are pinned to the mesh) --------
sys.path.insert(0, os.path.join(HERE, "..", "generate"))
FACE = spec.get("face")
FACE_MAP = os.path.join(HERE, "..", "face_map.json")
face_texture = None            # (photo path, colour correction) for the skin shader, set below
if FACE and os.path.exists(FACE_MAP):
    import importlib.util
    _spec = importlib.util.spec_from_file_location("cf_face_ids", os.path.join(HERE, "..", "generate", "face_ids.py"))
    ids = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(ids)
    pins = json.load(open(FACE_MAP))["pins"]
    valid = [i for i, p in enumerate(pins) if p is not None]
    pin_v = np.array([pins[i][0] for i in valid])          # (n, 3) vertex ids
    pin_b = np.array([pins[i][1] for i in valid])          # (n, 3) barycentric
    Q = np.array(FACE["landmarks"])[valid] * [1, -1]       # photo points, y up
    fit_rows = np.array([k for k, i in enumerate(valid) if i in set(ids.FIT_POINTS)])

    def pinned(co):
        return (co[pin_v] * pin_b[..., None]).sum(axis=1)  # (n, 3)

    # the variables the fit solves for: one table, shared with the designer's sliders (core/appearance.py)
    VARS = appearance.photo_vars()

    basis = human.data.shape_keys.key_blocks["Basis"]
    columns, col_keys = [], []                              # one column per (variable, sign)
    used_vertices = np.unique(pin_v)
    for vname, plus, minus in VARS:
        for sign, tnames in ((1, plus), (-1, minus)):
            if not tnames:
                continue
            delta = np.zeros((len(valid), 3))
            keys_here = []
            for t in tnames:
                path = TargetService.target_full_path(t)
                if not path:
                    log("WARNING face target missing", t)
                    continue
                key = TargetService.load_target(human, path, weight=0.0, name=f"cf-{t}")
                keys_here.append(key)
                d = np.zeros((len(human.data.vertices), 3))
                for vi in used_vertices:
                    d[vi] = np.subtract(key.data[vi].co, basis.data[vi].co)
                delta += (d[pin_v] * pin_b[..., None]).sum(axis=1)
            if keys_here:
                columns.append(delta[:, [0, 2]])            # front view: x and z
                col_keys.append((vname, sign, keys_here))

    def similarity(src, dst):
        """Least-squares s, R, t with dst ~ s R src + t (2D Umeyama)."""
        ms, md = src.mean(0), dst.mean(0)
        a, b = src - ms, dst - md
        U, S, Vt = np.linalg.svd(b.T @ a)
        D = np.diag([1, np.sign(np.linalg.det(U @ Vt))])
        Rm = U @ D @ Vt
        s = np.trace(np.diag(S) @ D) / (a ** 2).sum()
        return s, Rm, md - s * Rm @ ms

    M0 = pinned(coords())[:, [0, 2]]
    A_full = np.stack([c.reshape(-1) for c in columns], axis=1)      # (2n, k)
    w = np.zeros(A_full.shape[1])
    rows2 = np.concatenate([2 * fit_rows, 2 * fit_rows + 1])
    for _ in range(3):
        M = M0 + (A_full @ w).reshape(-1, 2)
        s, Rm, t = similarity(M[fit_rows], Q[fit_rows])
        Qm = ((Q - t) @ Rm) / s                                       # photo points in model space
        A, b = A_full[rows2], (Qm - M0).reshape(-1)[rows2]
        lam = 0.02 * np.mean(np.diag(A.T @ A))
        L = np.linalg.eigvalsh(A.T @ A).max() + lam
        for _ in range(800):                                          # bounded ridge, projected gradient
            w = np.clip(w - (A.T @ (A @ w - b) + lam * w) / L, 0.0, 1.0)
    before = np.sqrt(((M0 - Qm)[fit_rows] ** 2).sum(1)).mean()
    M = M0 + (A_full @ w).reshape(-1, 2)
    after = np.sqrt(((M - Qm)[fit_rows] ** 2).sum(1)).mean()
    for (vname, sign, keys_here), val in zip(col_keys, w):
        for k in keys_here:
            if val < 0.02:
                human.shape_key_remove(k)
            else:
                k.value = float(val)
    shaped = {f"{n}{'+' if sg > 0 else '-'}": round(float(v), 2) for (n, sg, _), v in zip(col_keys, w) if v >= 0.02}
    log(f"face shape: landmark error {before * 1000:.1f} -> {after * 1000:.1f} mm", shaped)

    # photo -> head texture: every front-facing head vertex gets the photo position of its
    # projection, through the fitted similarity plus a thin-plate spline on all landmarks
    co_all = coords()
    M = pinned(co_all)[:, [0, 2]]
    s, Rm, t = similarity(M[fit_rows], Q[fit_rows])
    src = (s * M @ Rm.T) + t                                          # model landmarks in photo space

    def tps_fit(src, dst, reg=1e-3):
        n = len(src)
        d = np.sqrt(((src[:, None] - src[None]) ** 2).sum(-1))
        K = d ** 2 * np.log(d + 1e-9)
        P = np.hstack([np.ones((n, 1)), src])
        Lm = np.zeros((n + 3, n + 3))
        Lm[:n, :n] = K + reg * np.mean(np.abs(K)) * np.eye(n)
        Lm[:n, n:], Lm[n:, :n] = P, P.T
        coef = np.linalg.solve(Lm, np.vstack([dst, np.zeros((3, 2))]))
        return lambda x: (lambda d2: (d2 ** 2 * np.log(d2 + 1e-9)) @ coef[:n]
                          + np.hstack([np.ones((len(x), 1)), x]) @ coef[n:])(
            np.sqrt(((x[:, None] - src[None]) ** 2).sum(-1)))

    warp = tps_fit(src, Q)
    body_set = body_idx
    head_v = body_set[co_all[body_set, 2] > co_all[body_set, 2].max() - 0.32]
    p_photo = warp((s * co_all[head_v][:, [0, 2]] @ Rm.T) + t) * [1, -1]   # back to image y-down

    if mask_mod:
        mask_mod.show_viewport = False
    ev = human.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me_ev = ev.to_mesh()
    normals = np.array([me_ev.vertices[int(i)].normal[:] for i in head_v])
    ev.to_mesh_clear()
    if mask_mod:
        mask_mod.show_viewport = True

    L2 = np.array(FACE["landmarks"])

    def poly_signed_dist(pts, poly):
        """Distance to the polygon boundary, positive inside."""
        inside = np.zeros(len(pts), bool)
        dmin = np.full(len(pts), np.inf)
        for a, b in zip(poly, np.roll(poly, -1, axis=0)):
            cond = (a[1] > pts[:, 1]) != (b[1] > pts[:, 1])
            xint = a[0] + (pts[:, 1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1] + 1e-12)
            inside ^= cond & (pts[:, 0] < xint)
            ab = b - a
            tt = np.clip(((pts - a) @ ab) / (ab @ ab + 1e-12), 0, 1)
            dmin = np.minimum(dmin, np.linalg.norm(pts - (a + tt[:, None] * ab), axis=1))
        return np.where(inside, dmin, -dmin)

    def smooth(x, e0, e1):
        u = np.clip((x - e0) / (e1 - e0), 0, 1)
        return u * u * (3 - 2 * u)

    fw = np.ptp(L2[ids.FACE_OVAL, 0])
    oval = smooth(poly_signed_dist(p_photo, L2[ids.FACE_OVAL]), 0.0, 0.14 * fw)
    facing = smooth(-normals[:, 1], 0.25, 0.65)
    hole = np.zeros(len(head_v))
    for poly, grow in ((ids.LEFT_EYE, 0.035), (ids.RIGHT_EYE, 0.035), (ids.LIPS_INNER, 0.02)):
        hole = np.maximum(hole, smooth(poly_signed_dist(p_photo, L2[poly]), -grow * fw, 0.0))
    # the upper forehead in photos often carries stray hair: fade back to skin above the brows
    brow_y = L2[ids.LEFT_BROW + ids.RIGHT_BROW, 1].mean()
    span = max(brow_y - L2[10, 1], 1.0)
    forehead = 1 - smooth(brow_y - p_photo[:, 1], 0.35 * span, 0.75 * span)
    weight = oval * facing * (1 - hole) * forehead

    wvals = np.zeros(len(human.data.vertices))
    wvals[head_v] = weight
    attr = human.data.attributes.new("cf_face", "FLOAT", "POINT")
    attr.data.foreach_set("value", wvals)
    uv_layer = human.data.uv_layers.new(name="cf_photo", do_init=False)
    FW, FH = FACE["size"]
    vert_uv = np.zeros((len(human.data.vertices), 2))
    vert_uv[head_v] = np.stack([p_photo[:, 0] / FW, 1 - p_photo[:, 1] / FH], axis=1)
    loop_v = np.empty(len(human.data.loops), int)
    human.data.loops.foreach_get("vertex_index", loop_v)
    uv_layer.data.foreach_set("uv", vert_uv[loop_v].reshape(-1))
    human.data.uv_layers.active_index = 0                              # keep the skin UVs primary
    face_texture = FACE["image"]
    log(f"face texture: {int((weight > 0.5).sum())} head vertices from the photo (face {FACE['width_px']:.0f} px wide)")

# --- the design's own face and body sliders --------------------------------------------------
# Applied after the photo fit, so a photo character can still be adjusted by hand and a designed one is
# shaped entirely from here. A slider left at 0 names no target at all, so an untouched design changes
# nothing. Targets are loaded as shape keys at their weight, exactly as the fit loads its own.
designed = appearance.targets_for(DESIGN)
head_shape = appearance.head_shape_target(DESIGN)
if head_shape:
    designed[head_shape] = max(designed.get(head_shape, 0.0), 1.0)
if designed:
    applied, missing = {}, []
    for tname, weight in sorted(designed.items()):
        path = TargetService.target_full_path(tname)
        if not path:
            missing.append(tname)
            continue
        TargetService.load_target(human, path, weight=float(weight), name=f"cf-design-{tname}")
        applied[tname] = round(float(weight), 2)
    log(f"designed shape: {len(applied)} target(s)", applied)
    if missing:
        log("WARNING design targets missing", missing)

# --- rig (before assets, so every asset gets rigged as it is attached) -------------------------
HumanService.add_builtin_rig(human, "rigify.human_toes", import_weights=True)
human.use_shape_key_edit_mode = True


def asset(fragment, subdir, kind):
    path = AssetService.find_asset_absolute_path(fragment, subdir)
    if not path:
        log(f"WARNING missing asset {subdir}/{fragment}")
        return None
    before = set(bpy.data.objects)
    HumanService.add_mhclo_asset(path, human, asset_type=kind, subdiv_levels=1, material_type="MAKESKIN")
    new = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    return new[0] if new else None


# --- skin: closest tone among skins of the right gender and age band ---------------------------
def lab(rgb):
    c = np.array(rgb) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    xyz = c @ np.array([[0.4124, 0.2126, 0.0193], [0.3576, 0.7152, 0.1192], [0.1805, 0.0722, 0.9505]])
    xyz /= np.array([0.9505, 1.0, 1.089])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])


band = "young" if args.age < 35 else "middleage" if args.age < 60 else "old"
skin_tone = spec["colours"].get("skin")


def skin_ok(name):
    n = name.lower()
    gender_ok = ("female" in n) == (args.gender == "female")
    plain = not any(t in n for t in ("toon", "special_suit", "genitals", "makeup", "hairless", "uniform"))
    return gender_ok and plain and n.startswith((band, "young", "middleage", "old"))


cands = {k: v for k, v in index["skins"].items() if skin_ok(k)}
# never give children or young adults an elderly (wrinkled) skin, nor an old person a young one
banned = "old" if args.age < 50 else ("young" if args.age >= 62 else None)
pool = {k: v for k, v in cands.items() if not (banned and k.lower().startswith(banned))} or cands
if skin_tone:
    # nearest tone over every age; the right age band is preferred, but tone matters more
    target_lab = lab(skin_tone)
    skin_name = min(pool, key=lambda k: np.linalg.norm((lab(pool[k]["tone"]) - target_lab) * [1.5, 1, 1])
                    + (0 if k.lower().startswith(band) else 8))
else:
    skin_name = next((k for k in pool if k.lower().startswith(band)), next(iter(pool)))
HumanService.set_character_skin(pool[skin_name]["mhmat"], human, skin_type="ENHANCED_SSS")
log("skin", skin_name, pool[skin_name]["tone"], "photo", skin_tone)

# --- body parts ---------------------------------------------------------------------------------
PARTS = [p_ for p_ in ((DESIGN or {}).get("parts") or []) if isinstance(p_, dict)]


def resize_parts(obj, role):
    """Apply the design's resized parts to one object: what someone shaped in the studio by hand.

    A part is remembered as the point that was clicked, how far it reaches along the surface and how much
    bigger it should be - never as vertex numbers, because this mesh is not the one the studio drew (it is
    subdivided once more), so only a point in space means the same thing in both."""
    def asked(p_):
        return (abs(float(p_.get("scale", 1)) - 1) > 1e-6
                or any(p_.get("move") or ()) or any(p_.get("turn") or ()))

    mine = [p_ for p_ in PARTS if p_.get("on") == role and asked(p_)]
    if not obj or not mine:
        return
    sys.path.insert(0, HERE)
    import costume as _kit
    co = [tuple(v.co) for v in obj.data.vertices]
    faces = [tuple(f.vertices) for f in obj.data.polygons]
    adj = _kit.neighbours(faces)
    for spec in mine:
        at = tuple(float(x) for x in spec["at"])
        part = _kit.part_at(co, faces, at, float(spec.get("radius", 0.08)))
        if not part:
            log(f"WARNING a resized {role} part at {at} found nothing")
            continue
        co = _kit.shape_part(co, part, float(spec.get("scale", 1)),
                             tuple(float(x) for x in (spec.get("move") or (0, 0, 0))),
                             tuple(float(x) for x in (spec.get("turn") or (0, 0, 0))),
                             faces=faces, adj=adj)
        log(f"{role} part x{float(spec.get('scale', 1)):.2f} move {spec.get('move') or (0, 0, 0)} "
            f"turn {spec.get('turn') or (0, 0, 0)} over {len(part)} vertices")
    obj.data.vertices.foreach_set("co", [c for p_ in co for c in p_])
    obj.data.update()


# Parts resized by hand in the studio. The BODY is resized before anything is fitted to it, so the
# clothes follow it - which is the order the live view works in too.
resize_parts(human, "body")

eye_alt = None
iris = (FACE or {}).get("iris")
if DESIGN and DESIGN.get("eyes") in index.get("eyes", {}):
    iris = index["eyes"][DESIGN["eyes"]]["iris"]
if iris and index.get("eyes"):
    # nearest MakeHuman eye colour; lightness counts half (photo lighting varies)
    eye_name = min(index["eyes"], key=lambda k: np.linalg.norm(
        (lab(index["eyes"][k]["iris"]) - lab(iris)) * [0.5, 1, 1]))
    eyes_path = AssetService.find_asset_absolute_path("high-poly/high-poly.mhclo", "eyes")
    Mhclo = importlib.import_module(f"{MPFB}.entities.clothes.mhclo").Mhclo
    mh = Mhclo(); mh.load(eyes_path, only_metadata=True)
    eye_alt = {mh.uuid: AssetService.path_to_fragment(index["eyes"][eye_name]["mhmat"], asset_subdir="eyes")}
    log("eyes", eye_name, index["eyes"][eye_name]["iris"], "photo iris", iris)
if eye_alt:
    HumanService.add_mhclo_asset(AssetService.find_asset_absolute_path("high-poly/high-poly.mhclo", "eyes"), human,
                                 asset_type="Eyes", subdiv_levels=1, material_type="MAKESKIN",
                                 alternative_materials=eye_alt)
else:
    asset("high-poly/high-poly.mhclo", "eyes", "Eyes")
brow_style = appearance.EYEBROWS.get((DESIGN or {}).get("eyebrows"), "eyebrow001")
brows_obj = asset(f"{brow_style}/{brow_style}.mhclo", "eyebrows", "Eyebrows")
asset("eyelashes01/eyelashes01.mhclo", "eyelashes", "Eyelashes")
teeth_obj = asset("teeth_shape03/teeth_shape03.mhclo", "teeth", "Teeth")
# teeth sit in the mouth's shadow and render grey with black gaps ("zombie"); like film/game rigs,
# give them an ivory lift, a light gloss and a touch of self-illumination so they read as clean teeth
if teeth_obj:
    for slot in teeth_obj.material_slots:
        nt = slot.material.node_tree if slot.material else None
        bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None) if nt else None
        tex = nt.nodes.get("diffuseTexture") if nt else None
        if bsdf and tex:
            lift = nt.nodes.new("ShaderNodeMix"); lift.data_type = "RGBA"; lift.blend_type = "SCREEN"
            lift.inputs["Factor"].default_value = 0.35
            lift.inputs["B"].default_value = (0.95, 0.92, 0.86, 1)
            nt.links.new(tex.outputs["Color"], lift.inputs["A"])
            nt.links.new(lift.outputs["Result"], bsdf.inputs["Base Color"])
            nt.links.new(lift.outputs["Result"], bsdf.inputs["Emission Color"])
            bsdf.inputs["Emission Strength"].default_value = 0.12
            bsdf.inputs["Roughness"].default_value = 0.3
            bsdf.inputs["Coat Weight"].default_value = 0.4
asset("tongue01/tongue01.mhclo", "tongue", "Tongue")

HAIR = {("male", "short"): "short01", ("male", "medium"): "culturalibre_hair_05", ("male", "long"): "long01",
        ("female", "short"): "toigo_inverted_bob", ("female", "medium"): "toigo_blunt_bob",
        ("female", "long"): "long01"}
hair_obj = None
# a named style (translated above) wins over the length, which is only what a photo could tell
h_name = args.hair or (HAIR[(args.gender, spec["hair_length"])] if spec.get("hair_length", "none") != "none"
                       else "none")
_hat_asked = (DESIGN or {}).get("hat", "none")
# An asset hat is a solid shell and the hair would poke through it, so it is left off. A MADE cap is built
# on the head and sits ON the hair: the hair stays, and what is under the band is masked off below.
if _hat_asked != "none" and _hat_asked not in appearance.MADE_HATS:
    h_name = "none"
if h_name != "none":
    hair_obj = asset(f"{h_name}/{h_name}.mhclo", "hair", "Hair")
    log("hair", h_name)

# beards and hats (CC0 packs bodyparts05, hats01); a beard takes the hair colour
BEARDS = {"scruffy": ["wdg_scruffy_beard"], "long": ["rehmanpolanski_beard_viking"],
          "full": ["grinsegold_beard_sigmund_wip"], "faun": ["culturalibre_faun_beard"],
          "moustache": ["rehmanpolanski_moustache_viking"],
          "santa": ["rehmanpolanski_beard_viking", "rehmanpolanski_moustache_viking"]}
HATS = {"santa": "joepal_xmas_cap", "newsboy": "jujube_newsboy_cap", "fedora": "fedora01",
        "cloche": "aethelraed_unraed_cloche_hat", "flat_cap": "grinsegold_uncle_joshis_hat"}
beard_objs, hat_obj = [], None
beard = (DESIGN or {}).get("beard", "none")
if beard in BEARDS:
    beard_objs = [o for o in (asset(f"{b}/{b}.mhclo", "clothes", "Clothes") for b in BEARDS[beard]) if o]
    log("beard", beard)
# Pieces someone cut themselves (core/wardrobe.py): a slot may say "piece:my_long_coat", which means
# that asset with that person's edits applied. The edits name their place by VERTEX NUMBER, which is the
# same here as in the live view - the subdivision modifier leaves the base mesh and its numbering alone.
PIECES = wardrobe.load_all(config.LIBRARY_DIR)


def cut_edits(obj, piece, what):
    """Apply a saved piece's edits to the object just loaded from its base asset."""
    edits = [e for e in (piece.get("edits") or []) if isinstance(e, dict)]
    if not obj or not edits:
        return
    sys.path.insert(0, HERE)
    import costume as _kit
    co = [tuple(v.co) for v in obj.data.vertices]
    faces = [tuple(f.vertices) for f in obj.data.polygons]
    adj = _kit.neighbours(faces)
    for edit in edits:
        seed = int(edit.get("seed", -1))
        if not 0 <= seed < len(co):
            log(f"WARNING {what}: edit {seed} is not a vertex of this piece")
            continue
        part = _kit.band(co, _kit.edges_of(faces), [seed], float(edit.get("radius", 0.08)))
        co = _kit.shape_part(co, part, float(edit.get("scale", 1)),
                             tuple(float(x) for x in (edit.get("move") or (0, 0, 0))),
                             tuple(float(x) for x in (edit.get("turn") or (0, 0, 0))),
                             faces=faces, adj=adj)
    obj.data.vertices.foreach_set("co", [c for p_ in co for c in p_])
    obj.data.update()
    log(f"{what}: {piece.get('name')} ({len(edits)} edit(s))")


hat = (DESIGN or {}).get("hat", "none")
hat_piece = PIECES.get(wardrobe.named(hat) or "")
if hat_piece and hat_piece.get("role") == "hat":
    hat_obj = asset(f"{hat_piece['base']}/{hat_piece['base']}.mhclo", "clothes", "Clothes")
    cut_edits(hat_obj, hat_piece, "hat piece")
elif hat in HATS:
    hat_obj = asset(f"{HATS[hat]}/{HATS[hat]}.mhclo", "clothes", "Clothes")
    log("hat", hat)
    # These assets come in one size, and it is a small one - a Santa cap off the shelf is a child's. A hat
    # grows from its brim (blender/costume.py), so the opening keeps its grip on the head and only the
    # crown rises and widens. Done to the mesh itself, so the fit, the weights and the rig are untouched.
    hat_size = float((DESIGN or {}).get("hat_size") or 1.0)
    if hat_obj and abs(hat_size - 1.0) > 1e-6:
        sys.path.insert(0, HERE)
        import costume as _kit
        hat_co = [tuple(v.co) for v in hat_obj.data.vertices]
        hat_faces = [tuple(f.vertices) for f in hat_obj.data.polygons]
        skull = [tuple(v.co) for i, v in enumerate(human.data.vertices) if i % 7 == 0]   # the head,
        # sampled: rim_of asks which of the hat's rings lies against it (a bpy collection takes no
        # slice step, and this one is 19158 vertices long)
        rim = _kit.rim_of(hat_co, hat_faces, skull)   # the opening holds it on: that is what stays put
        grown = _kit.grow_hat(hat_co, hat_size, rim)
        hat_obj.data.vertices.foreach_set("co", [c for p_ in grown for c in p_])
        hat_obj.data.update()
        log(f"hat size x{hat_size:.2f}")
COSTUME = (DESIGN or {}).get("costume") or {}     # coat, trim, belt, buckle, gloves, boots (core/schema.py)

# plain garments (CC0 packs) whose textures recolour cleanly; picked from what the photo shows
clothing = spec.get("clothing", {"garment": "trousers", "sleeves": "long"})
# whole-body outfits: one mesh instead of a top and trousers (uniforms, suits, robes)
STYLES = {
    "suit": {"male": "male_casualsuit01", "female": "female_casualsuit01"},
    "formal": {"male": "male_elegantsuit01", "female": "female_elegantsuit01"},
    "work": {"male": "male_worksuit01", "female": "female_sportsuit01"},
    "robe": {"male": "mindfront_kimono", "female": "mindfront_kimono"},
    "tunic": {"male": "wdg_mycenaean_tunic", "female": "wdg_mycenaean_tunic"},
}
style = (DESIGN or {}).get("outfit", {}).get("style", "casual")
TOP = {("male", "short"): "elvs_crude_t-shirt_male", ("female", "short"): "joepal_crude_t-shirt_female",
       ("male", "long"): "toigo_fisherman_sweater", ("female", "long"): "toigo_fisherman_sweater"}
BOTTOM = {"trousers": "toigo_wool_pants", "shorts": "cortu_jeans_shorts", "skirt": "toigo_tiered_mini_skirt"}


def cloth(name):
    return asset(f"{name}/{name}.mhclo", "clothes", "Clothes")


top_obj = bottom_obj = dress_obj = None
if style in STYLES:
    one_piece = STYLES[style][args.gender]
    dress_obj = cloth(one_piece)
    worn = [one_piece]
elif clothing["garment"] == "dress":
    dress_obj = cloth("toigo_shift_dress")
    worn = ["toigo_shift_dress"]
else:
    top_name = TOP[(args.gender, clothing["sleeves"])]
    bottom_name = BOTTOM[clothing["garment"]]
    bottom_obj, top_obj = cloth(bottom_name), cloth(top_name)
    worn = [top_name, bottom_name]
# Footwear made for this foot replaces the library's: two pairs of shoes on one pair of feet is what
# "automatically picking, but not in a professional way" looks like.
_made_shoes = (DESIGN or {}).get("outfit", {}).get("shoe_style", "none") not in ("none", None)
shoes_name = None if _made_shoes else ("shoes03" if COSTUME.get("boots") else "shoes04")
shoes_obj = cloth(shoes_name) if shoes_name else None

# and the parts of what is worn, once each garment is on: the same shaping the studio showed
for _obj, _role in ((top_obj, "top"), (bottom_obj, "bottom"), (dress_obj, "outfit"),
                    (shoes_obj, "shoes"), (hat_obj, "hat")):
    resize_parts(_obj, _role)
log("wearing", worn + ([shoes_name] if shoes_name else ["shoes cut for this foot"]), clothing)

# layering: push each garment out along its (posed) normals so the outer layer always covers
# the inner one and the body never pokes through, also while animating
for obj, offset in ((bottom_obj, 0.003), (top_obj, 0.007), (dress_obj, 0.004)):
    if obj:
        d = obj.modifiers.new("cf_layer", "DISPLACE")
        d.strength = offset
        d.mid_level = 0.0

# hide the part of the trousers/skirt the top really covers: a bottom vertex goes only when the
# top lies over it and also over a point 2.5 cm lower, so there is always overlap at the hem
if top_obj and bottom_obj:
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    deps = bpy.context.evaluated_depsgraph_get()
    top_bvh = BVHTree.FromObject(top_obj, deps)
    to_top = top_obj.matrix_world.inverted()
    bm_w = bottom_obj.matrix_world
    nrm_w = bm_w.to_3x3().inverted().transposed()

    def top_over(p_world, n_world):
        origin = to_top @ (p_world - n_world * 0.01)
        direction = (to_top.to_3x3() @ n_world).normalized()
        hit = top_bvh.ray_cast(origin, direction, 0.08)
        return hit[0] is not None

    covered = []
    for v in bottom_obj.data.vertices:
        p = bm_w @ v.co
        n = (nrm_w @ v.normal).normalized()
        if top_over(p, n) and top_over(p - Vector((0, 0, 0.025)), n):
            covered.append(v.index)
    if covered:
        vg = bottom_obj.vertex_groups.new(name="cf_covered")
        vg.add(covered, 1.0, "REPLACE")
        m = bottom_obj.modifiers.new("cf_hide_covered", "MASK")
        m.vertex_group = "cf_covered"
        m.invert_vertex_group = True
    log(f"hid {len(covered)} bottom vertices covered by the top")


# --- recolour to the photo, keeping the texture's shading detail -------------------------------
def srgb_to_linear(rgb):
    c = np.array(rgb, float) / 255.0
    return np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)


def region_luminance(obj, img, face_filter=None):
    """Median luminance of the texture under the given faces' UVs (or the whole mesh)."""
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)
    lum_img = px[..., :3] @ np.array([0.2126, 0.7152, 0.0722])
    uv = obj.data.uv_layers.active.data
    me = obj.data
    loops = [li for p in me.polygons if face_filter is None or face_filter(p) for li in p.loop_indices]
    if not loops:
        return None
    uvs = np.array([uv[li].uv[:] for li in loops])
    x = np.clip((uvs[:, 0] % 1.0) * (w - 1), 0, w - 1).astype(int)
    y = np.clip((uvs[:, 1] % 1.0) * (h - 1), 0, h - 1).astype(int)
    return float(np.median(lum_img[y, x]))


def recolour(obj, colours, region_attr=None, face_filter=None):
    """Replace diffuse colour with photo colour x (texture luminance / region median luminance).

    colours: one RGB, or (rgb_for_attr_1, rgb_for_attr_0) when region_attr names a 0/1 point
    attribute splitting the mesh (e.g. top vs bottom of an outfit)."""
    for slot in obj.material_slots:
        m = slot.material
        if not m or not m.node_tree:
            continue
        nt = m.node_tree
        # some assets multiply by an ambient-occlusion map whose image is missing: that turns the
        # colour black (the "black beard"); skip that step
        ao, ao_tex = nt.nodes.get("aoMix"), nt.nodes.get("aomapTexture")
        if ao and ao_tex is not None and ao_tex.image is None:
            ao.inputs[0].default_value = 0.0
        tex = nt.nodes.get("diffuseTexture")
        if not tex or not tex.image or not tex.outputs["Color"].links:
            continue
        dests = [l.to_socket for l in tex.outputs["Color"].links]
        bw = nt.nodes.new("ShaderNodeRGBToBW")
        nt.links.new(tex.outputs["Color"], bw.inputs[0])

        def tinted(rgb, ffilter):
            med = region_luminance(obj, tex.image, ffilter) or 0.5
            div = nt.nodes.new("ShaderNodeMath"); div.operation = "DIVIDE"
            nt.links.new(bw.outputs[0], div.inputs[0]); div.inputs[1].default_value = max(med, 0.02)
            # detail = 1 + k * (lum/median - 1): full detail for dark colours, gentle for light ones
            light = float(np.dot(srgb_to_linear(rgb), [0.2126, 0.7152, 0.0722]))
            k = 1.0 - 0.75 * min(light / 0.6, 1.0)
            soft = nt.nodes.new("ShaderNodeMath"); soft.operation = "MULTIPLY_ADD"
            nt.links.new(div.outputs[0], soft.inputs[0]); soft.inputs[1].default_value = k
            soft.inputs[2].default_value = 1.0 - k
            div = soft
            mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MULTIPLY"
            mix.inputs["Factor"].default_value = 1.0
            mix.inputs["A"].default_value = (*srgb_to_linear(rgb), 1.0)
            nt.links.new(div.outputs[0], mix.inputs["B"])
            return mix.outputs["Result"]

        if region_attr:
            attr = obj.data.attributes[region_attr].data
            top = tinted(colours[0], lambda p: all(attr[v].value > 0.5 for v in p.vertices))
            bot = tinted(colours[1], lambda p: all(attr[v].value < 0.5 for v in p.vertices))
            a = nt.nodes.new("ShaderNodeAttribute"); a.attribute_name = region_attr
            sel = nt.nodes.new("ShaderNodeMix"); sel.data_type = "RGBA"
            nt.links.new(a.outputs["Fac"], sel.inputs["Factor"])
            nt.links.new(bot, sel.inputs["A"]); nt.links.new(top, sel.inputs["B"])
            out = sel.outputs["Result"]
        else:
            out = tinted(colours, None)
        for d in dests:
            nt.links.new(out, d)


cols = spec["colours"]
if hair_obj and cols.get("hair"):
    recolour(hair_obj, cols["hair"])
if brows_obj and cols.get("hair"):
    recolour(brows_obj, cols["hair"])
for beard_obj in beard_objs if cols.get("hair") else []:
    recolour(beard_obj, cols["hair"])
shoes_col = rgb(COSTUME["boots"]) if COSTUME.get("boots") else cols.get("shoes")
if shoes_obj and shoes_col:
    recolour(shoes_obj, shoes_col)
top_col = cols.get("top") or cols.get("bottom")
bottom_col = cols.get("bottom") or cols.get("top")
for obj, col in ((top_obj, top_col), (bottom_obj, bottom_col), (dress_obj, top_col)):
    if obj and col:
        recolour(obj, col)
log("recoloured", {k: v for k, v in cols.items() if v})


# skin: gentle per-channel gain from the chosen texture's tone toward the photo's (lighting in
# photos varies, so the gain is clamped; texture detail such as lips and freckles is kept)
if skin_tone:
    # half the correction (sqrt) and a narrow clamp: photo lighting is unknown
    ratio = srgb_to_linear(skin_tone) / np.maximum(srgb_to_linear(pool[skin_name]["tone"]), 1e-3)
    gain = np.clip(np.sqrt(ratio), 0.8, 1.25)
    group = next((n.node_tree for s in human.material_slots if s.material and s.material.node_tree
                  for n in s.material.node_tree.nodes if n.type == "GROUP"), None)
    tex = next((n for n in group.nodes if n.name.lower() == "diffusetexture"), None) if group else None
    if tex and tex.outputs["Color"].links:
        dests = [l.to_socket for l in tex.outputs["Color"].links]
        mix = group.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = 1.0
        mix.inputs["B"].default_value = (*gain, 1.0)
        group.links.new(tex.outputs["Color"], mix.inputs["A"])
        skin_out = mix.outputs["Result"]

        if face_texture:
            # the photo's face over the skin, weighted by cf_face; its colour is matched to the
            # body skin so there is no seam at the edge of the face
            photo = group.nodes.new("ShaderNodeTexImage")
            photo.image = bpy.data.images.load(face_texture, check_existing=True)
            photo.extension = "EXTEND"
            photo.interpolation = "Cubic"
            uvn = group.nodes.new("ShaderNodeUVMap"); uvn.uv_map = "cf_photo"
            group.links.new(uvn.outputs["UV"], photo.inputs["Vector"])
            body_lin = srgb_to_linear(pool[skin_name]["tone"]) * gain
            corr = np.clip(body_lin / np.maximum(srgb_to_linear(FACE["skin_tone"]), 1e-3), 0.5, 2.0)
            match = group.nodes.new("ShaderNodeMix"); match.data_type = "RGBA"; match.blend_type = "MULTIPLY"
            match.inputs["Factor"].default_value = 1.0
            match.inputs["B"].default_value = (*corr, 1.0)
            group.links.new(photo.outputs["Color"], match.inputs["A"])
            fac = group.nodes.new("ShaderNodeAttribute"); fac.attribute_name = "cf_face"
            blend = group.nodes.new("ShaderNodeMix"); blend.data_type = "RGBA"
            group.links.new(fac.outputs["Fac"], blend.inputs["Factor"])
            group.links.new(skin_out, blend.inputs["A"])
            group.links.new(match.outputs["Result"], blend.inputs["B"])
            skin_out = blend.outputs["Result"]
            log("face photo blended into skin, colour match", np.round(corr, 2))
        for d in dests:
            group.links.new(skin_out, d)
        log("skin gain", np.round(gain, 2))
    else:
        log("WARNING skin texture node not found; skin left untinted",
            [(n.type, n.name) for n in group.nodes] if group else None)

# --- face shapes for lip-sync and expressions --------------------------------------------------
FaceService.load_targets(human, load_microsoft_visemes=False, load_meta_visemes=True, load_arkit_faceunits=True)
keys = human.data.shape_keys.key_blocks
log("face shapes", sum(1 for k in keys if k.name.startswith("viseme_")), "visemes,",
    len(keys), "shape keys total")

# --- full rig -----------------------------------------------------------------------------------
meta = ObjectService.find_object_of_type_amongst_nearest_relatives(human, "Skeleton")
bpy.ops.object.select_all(action="DESELECT")
bpy.context.view_layer.objects.active = meta
meta.select_set(True)
rig = RigService.generate_rigify_rig(meta, meta_rig_action="hide")
if rig is None:
    sys.exit("CF: FAILED rigify generation")
rig.name = "CastForge_Rig"
root = rig
lowest = ObjectService.get_lowest_point(human)
root.location.z -= human.matrix_world.translation.z + human.matrix_world.to_scale().z * lowest
log("rig", rig.name, len(rig.pose.bones), "pose bones")

# --- costume: long coat, fur trim, belt, gloves, boot tops (after the rig: every piece copies the bone
# --- weights of the garment or skin it is made from; geometry maths in costume.py) ---------------------
# `COSTUME` is the hand-made layer; `made_wear` is what tailor.py cuts for this body. Footwear is asked
# for by `outfit.shoe_style`, which is NOT a costume key, so someone in made shoes and an ordinary shirt
# has to get in here too.
made_wear = bool((DESIGN or {}).get("outfit", {}).get("shoe_style", "none") not in ("none", None)
                 or any(((DESIGN or {}).get("costume") or {}).get(k) for k in
                        ("socks", "tie", "scarf", "watch", "wristband")))
if COSTUME or made_wear:
    import bmesh
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    from mathutils.kdtree import KDTree
    sys.path.insert(0, HERE)
    import costume as kit
    import tailor                     # socks, footwear and the small things, cut to this body
    bpy.context.view_layer.update()

    def lin(h):
        c = rgb(h) if isinstance(h, str) else h
        return tuple(float(x) for x in srgb_to_linear(c)) if c else None

    def material(name, colour, rough, metal=0.0, sheen=0.0, coat=0.0, fluff=0.0):
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        b = nt.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (*colour, 1)
        b.inputs["Roughness"].default_value = rough
        b.inputs["Metallic"].default_value = metal
        b.inputs["Sheen Weight"].default_value = sheen
        b.inputs["Sheen Tint"].default_value = (*(min(1.0, 0.25 + 1.5 * c) for c in colour), 1)   # velvet glows in its own colour
        b.inputs["Coat Weight"].default_value = coat
        if fluff:   # fur: a fine noise bump so the trim reads soft, not plastic
            noise = nt.nodes.new("ShaderNodeTexNoise")
            noise.inputs["Scale"].default_value = 420.0
            noise.inputs["Detail"].default_value = 8.0
            bump = nt.nodes.new("ShaderNodeBump")
            bump.inputs["Strength"].default_value = fluff
            bump.inputs["Distance"].default_value = 0.004
            nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
            nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
        return m

    def rest(obj):
        """Rest-pose vertex positions (shape keys mixed, no modifiers): local array and world tuples."""
        mods = [(m, m.show_viewport) for m in obj.modifiers]
        for m, _ in mods:
            m.show_viewport = False
        ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        me = ev.to_mesh()
        local = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", local)
        ev.to_mesh_clear()
        for m, shown in mods:
            m.show_viewport = shown
        local = local.reshape(-1, 3)
        mw = np.array(obj.matrix_world)
        world = local @ mw[:3, :3].T + mw[:3, 3]
        return local, [tuple(v) for v in world]

    def faces_of(obj):
        return [tuple(p.vertices) for p in obj.data.polygons]

    def dominant(obj):
        """Each vertex's strongest vertex-group name, lower case ('' when unweighted)."""
        names = {g.index: g.name.lower() for g in obj.vertex_groups}
        return [names.get(max(v.groups, key=lambda g: g.weight).group, "") if len(v.groups) else ""
                for v in obj.data.vertices]

    def piece(src, name, keep, mat, lift, thick):
        """A new rigged mesh from faces `keep` of `src`, `lift` m out along its normals, `thick` m thick."""
        o = src.copy()
        o.data = src.data.copy()
        o.name = name
        for c in src.users_collection:
            c.objects.link(o)
        for k in list(o.keys()):
            if k.lower().startswith("mpfb"):
                del o[k]
        if o.data.shape_keys:          # keep the shaped body, drop the face shapes
            local, _ = rest(src)
            o.shape_key_clear()
            o.data.vertices.foreach_set("co", local.ravel())
        bm = bmesh.new()
        bm.from_mesh(o.data)
        keep = set(keep)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep], context="FACES")
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
        bm.to_mesh(o.data)
        bm.free()
        for m in list(o.modifiers):
            if m.type not in ("ARMATURE", "SUBSURF", "DISPLACE"):
                o.modifiers.remove(m)
        o.data.materials.clear()
        o.data.materials.append(mat)
        o.data.polygons.foreach_set("material_index", [0] * len(o.data.polygons))
        if lift:
            d = o.modifiers.new("cf_lift", "DISPLACE")
            d.strength, d.mid_level = lift, 0.0
        if thick:
            sol = o.modifiers.new("cf_thick", "SOLIDIFY")
            sol.thickness, sol.offset, sol.use_rim = thick, 1.0, True
        return o

    def cut(o, keep):
        """Slice mesh `o` along the world planes in `keep` [(axis, lo, hi)...] and drop faces outside them;
        the new vertices on the cuts get interpolated bone weights and UVs."""
        mw = o.matrix_world
        inv = mw.inverted()
        bm = bmesh.new()
        bm.from_mesh(o.data)
        for axis, lo, hi in keep:
            for v in (lo, hi):
                point = [0.0, 0.0, 0.0]
                point[axis] = v
                normal = [0.0, 0.0, 0.0]
                normal[axis] = 1.0
                co_l = inv @ Vector(point)
                no_l = (inv.to_3x3().transposed().inverted() @ Vector(normal)).normalized()
                geom = list(bm.verts) + list(bm.edges) + list(bm.faces)
                bmesh.ops.bisect_plane(bm, geom=geom, plane_co=co_l, plane_no=no_l)
        drop = []
        for f in bm.faces:
            c = mw @ f.calc_center_median()
            if any(not (lo <= c[axis] <= hi) for axis, lo, hi in keep):
                drop.append(f)
        bmesh.ops.delete(bm, geom=drop, context="FACES")
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
        bm.to_mesh(o.data)
        bm.free()

    def head(bone):
        b = rig.data.bones.get(bone)
        return rig.matrix_world @ b.head_local if b else None

    centre_x = head("DEF-spine").x
    hip_z, knee_z = head("DEF-thigh.L").z, head("DEF-shin.L").z
    TORSO = ("spine", "pelvis", "thigh", "torso", "hips")
    made = []

    # the body surface without helpers: keeps the coat clear of the legs; its weights shape the coat's skirt
    _, body_w = rest(human)
    in_body = set(int(v) for v in body_idx)
    body_bvh = BVHTree.FromPolygons(body_w, [f for f in faces_of(human) if all(v in in_body for v in f)])
    body_kd = KDTree(len(in_body))
    for v in in_body:
        body_kd.insert(body_w[v], v)
    body_kd.balance()
    body_names = {g.index: g.name for g in human.vertex_groups}

    def body_weights(v):
        return {body_names[g.group]: g.weight for g in human.data.vertices[v].groups
                if body_names[g.group].startswith("DEF-")}

    def clear_of_body(p):
        hit, normal, _, _ = body_bvh.find_nearest(p)
        return kit.push_clear(p, tuple(hit), tuple(normal), 0.03) if hit is not None else p

    # long coat: continue the top's hem down to mid-thigh, flaring a little, weighted from hips toward legs
    if COSTUME.get("coat") == "long" and top_obj:
        _, co = rest(top_obj)
        hem = kit.openings(co, kit.boundary_loops(faces_of(top_obj)), centre_x).get("hem")
        length = (kit.centroid(co, hem)[2] - (hip_z - 0.55 * (hip_z - knee_z))) if hem else 0.0
        if length > 0.03:
            n_rings = max(2, round(length / 0.03))
            c = kit.centroid(co, hem)
            rings = [[clear_of_body(p) for p in ring]
                     for ring in kit.hem_rings([co[v] for v in hem], c[:2], length, n_rings, 0.12)]
            names = {g.index: g.name for g in top_obj.vertex_groups}
            hem_w = [{names[g.group]: g.weight for g in top_obj.data.vertices[v].groups} for v in hem]
            inv = np.linalg.inv(np.array(top_obj.matrix_world))
            bm = bmesh.new()
            bm.from_mesh(top_obj.data)
            bm.verts.ensure_lookup_table()
            uv = bm.loops.layers.uv.active
            deform = bm.verts.layers.deform.verify()

            def column(a, b):
                """UVs of the quads stacked above hem edge a-b: [((bottom a, bottom b), (top a, top b)), ...]."""
                va, vb = bm.verts[a], bm.verts[b]
                edge = bm.edges.get((va, vb))
                face, out = (edge.link_faces[0] if edge and edge.link_faces else None), []
                while face is not None and len(face.verts) == 4 and len(out) < n_rings:
                    loops = {l.vert: l for l in face.loops}
                    if va not in loops or vb not in loops:
                        break
                    la, lb = loops[va], loops[vb]
                    ua = la.link_loop_prev.vert if la.link_loop_next.vert == vb else la.link_loop_next.vert
                    ub = lb.link_loop_next.vert if lb.link_loop_prev.vert == va else lb.link_loop_prev.vert
                    out.append(((la[uv].uv.copy(), lb[uv].uv.copy()), (loops[ua][uv].uv.copy(), loops[ub][uv].uv.copy())))
                    top = bm.edges.get((ua, ub))
                    face = next((f for f in top.link_faces if f != face), None) if top else None
                    va, vb = ua, ub
                return out

            columns = [column(hem[i], hem[(i + 1) % len(hem)]) for i in range(len(hem))]
            rows = []
            for k, ring in enumerate(rings, 1):
                row = []
                for i, p in enumerate(ring):
                    nv = bm.verts.new((inv @ np.array([*p, 1.0]))[:3])
                    _, near, _ = body_kd.find(p)
                    for g, wt in kit.mix_weights(hem_w[i], body_weights(near), 0.2 + 0.5 * k / n_rings).items():
                        gi = top_obj.vertex_groups.get(g) or top_obj.vertex_groups.new(name=g)
                        nv[deform][gi.index] = wt
                    row.append(nv)
                rows.append(row)
            bm.verts.index_update()
            bm.verts.ensure_lookup_table()
            new_faces = []
            for n, f in enumerate(kit.ring_faces(hem, [[v.index for v in r] for r in rows])):
                try:
                    nf = bm.faces.new([bm.verts[i] for i in f])
                except ValueError:
                    continue
                nf.smooth = True
                col = columns[n % len(hem)]       # the coat below the hem mirrors the garment above it
                if col:
                    (ba, bb), (ta, tb) = col[(n // len(hem)) % len(col)]
                    for loop, value in zip(nf.loops, (ba, bb, tb, ta)):
                        loop[uv].uv = value
                new_faces.append(nf)
            bmesh.ops.recalc_face_normals(bm, faces=new_faces)
            bm.to_mesh(top_obj.data)
            bm.free()
            made.append(f"coat +{length:.2f} m")

    FABRICS = {"velvet": {"rough": 0.65, "sheen": 0.7, "fluff": 0.05}, "leather": {"rough": 0.4, "coat": 0.3},
               "cotton": {"rough": 0.85, "sheen": 0.25, "fluff": 0.03}}
    fabric = FABRICS.get(COSTUME.get("fabric"))
    for obj, col in ((top_obj, top_col), (bottom_obj, bottom_col), (dress_obj, top_col)) if fabric else ():
        if obj and col:
            obj.data.materials.clear()
            obj.data.materials.append(material(f"cf_{COSTUME['fabric']}", lin(col), **fabric))
            obj.data.polygons.foreach_set("material_index", [0] * len(obj.data.polygons))
            made.append(f"{COSTUME['fabric']} {obj.name}")

    trim = lin(COSTUME.get("trim"))
    garment = top_obj or dress_obj
    if trim and garment:
        _, co = rest(garment)
        fs = faces_of(garment)
        ops = kit.openings(co, kit.boundary_loops(fs), centre_x)
        keep = set().union(*kit.trim_bands(co, fs, centre_x, clothing.get("sleeves") or "short").values(),
                           set())
        if COSTUME.get("coat") == "long" and ops.get("hem") and ops.get("collar"):
            dom = dominant(garment)
            c = kit.centroid(co, ops["hem"])
            keep |= kit.front_strip(co, [v for v in range(len(co)) if any(t in dom[v] for t in TORSO)], c[:2],
                                    0.035, (c[2], kit.centroid(co, ops["collar"])[2]))
        piece(garment, "cf_trim", kit.faces_inside(fs, keep), material("cf_fur", trim, 0.95, sheen=1.0, fluff=0.5),
              0.004, 0.012)
        made.append("trim")

    belt = lin(COSTUME.get("belt"))
    if belt and garment:
        _, co = rest(garment)
        fs = faces_of(garment)
        dom = dominant(garment)
        belt_z = head("DEF-spine.001").z
        # the torso's faces around the belt line (not the hanging arms), then cut clean at the belt's edges
        torso_faces = [i for i, f in enumerate(fs)
                       if sum(any(t in dom[v] for t in TORSO) for v in f) * 2 > len(f)
                       and any(abs(co[v][2] - belt_z) < 0.08 for v in f)]
        b = piece(garment, "cf_belt", torso_faces, material("cf_belt", belt, 0.35, coat=0.3), 0.007, 0.009)
        cut(b, [(2, belt_z - 0.04, belt_z + 0.04)])
        buckle = lin(COSTUME.get("buckle"))
        if buckle:
            front_y = min(p[1] for p in co if abs(p[2] - belt_z) < 0.05)
            k = piece(garment, "cf_buckle", torso_faces, material("cf_buckle", buckle, 0.25, metal=1.0), 0.016, 0.01)
            cut(k, [(2, belt_z - 0.05, belt_z + 0.05), (0, centre_x - 0.055, centre_x + 0.055),
                    (1, front_y - 0.05, front_y + 0.08)])
        made.append(f"belt at {belt_z:.2f} m")

    # armour: plates lifted off the body and the garment, in metal
    armour = lin(COSTUME.get("armour"))
    if armour:
        plate = material("cf_armour", armour, 0.28, metal=1.0, coat=0.2)
        belt_z2 = head("DEF-spine.001").z
        shoulder_z2 = head("DEF-upper_arm.L").z
        if garment:
            _, co = rest(garment)
            fs = faces_of(garment)
            dom = dominant(garment)
            torso_f = [i for i, f_ in enumerate(fs)
                       if sum(any(t in dom[v] for t in TORSO) for v in f_) * 2 > len(f_)]
            breast = piece(garment, "cf_breastplate", torso_f, plate, 0.012, 0.011)
            cut(breast, [(2, belt_z2 + 0.02, shoulder_z2 + 0.05)])     # waist to the top of the shoulders
            made.append("breastplate")
        for side in ("L", "R"):
            shoulder = head(f"DEF-upper_arm.{side}")
            elbow = head(f"DEF-forearm.{side}")
            ankle = head(f"DEF-foot.{side}")
            knee = head(f"DEF-shin.{side}")
            names = {g.index: g.name.lower() for g in human.vertex_groups}
            low = side.lower()
            for tag, bones, lift_p in ((f"pauldron.{side}", (f"upper_arm.{low}",), 0.016),
                                       (f"bracer.{side}", (f"forearm.{low}",), 0.01),
                                       (f"greave.{side}", (f"shin.{low}",), 0.012)):
                verts = {v.index for v in human.data.vertices if v.index in in_body and
                         sum(g.weight for g in v.groups if any(b in names[g.group] for b in bones)) >= 0.35}
                if not verts:
                    continue
                p_obj = piece(human, f"cf_{tag}", kit.faces_mostly(faces_of(human), verts), plate, lift_p, 0.009)
                if tag.startswith("pauldron") and shoulder is not None and elbow is not None:
                    cut(p_obj, [(2, shoulder.z - 0.14, shoulder.z + 0.09)])      # the cap of the shoulder only
                elif tag.startswith("greave") and ankle is not None and knee is not None:
                    cut(p_obj, [(2, ankle.z + 0.04, knee.z - 0.03)])             # the shin, not the knee or foot
            made.append(f"armour {side}")

    # a hood: a cowl rising from the garment's collar, over the head, open at the face. A hood is not the
    # head's surface (copying head faces or banding the collar both read as a flat band): it is a shell of
    # its own, built from rings and taken off the garment as its own object, like the cape.
    hood = lin(COSTUME.get("hood"))
    if hood and garment:
        head_b = next((h for h in (head("DEF-spine.006"), head("head")) if h is not None), None)
        above = [body_w[v] for v in in_body if head_b is not None and body_w[v][2] > head_b.z + 0.02]
        if above and head("DEF-upper_arm.L") is not None:
            crown = max(p[2] for p in above)
            radius = max(abs(p[0] - centre_x) for p in above) + 0.03
            head_y = sum(p[1] for p in above) / len(above)
            base_z = head("DEF-upper_arm.L").z          # it sits on the shoulders, not round the neck
            rings = [[clear_of_body(p) for p in r] for r in
                     kit.hood_rings((centre_x, head_y), base_z, crown + 0.045, radius,
                                    rings=9, span=19, face=-1.0)]
            names = {g.index: g.name for g in garment.vertex_groups}
            bm = bmesh.new()
            bm.from_mesh(garment.data)
            bm.verts.ensure_lookup_table()
            uv = bm.loops.layers.uv.active
            deform = bm.verts.layers.deform.verify()
            inv = np.linalg.inv(np.array(garment.matrix_world))
            rows = []
            for r in rings:
                row = []
                for p in r:
                    nv = bm.verts.new((inv @ np.array([*p, 1.0]))[:3])
                    _, near, _ = body_kd.find(p)       # the head's own weights: the hood turns with the head
                    for g, wt in body_weights(near).items():
                        gi = garment.vertex_groups.get(g) or garment.vertex_groups.new(name=g)
                        nv[deform][gi.index] = wt
                    row.append(nv)
                rows.append(row)
            bm.verts.index_update()
            bm.verts.ensure_lookup_table()
            new_faces = []
            shell = kit.ring_faces([v.index for v in rows[0]],
                                   [[v.index for v in r] for r in rows[1:]], closed=False)
            for f in shell + [tuple(v.index for v in rows[-1])]:          # the strips, then a cap on top
                try:
                    nf = bm.faces.new([bm.verts[i] for i in f])
                except ValueError:
                    continue
                nf.smooth = True
                for loop in nf.loops:
                    loop[uv].uv = (0.5, 0.5)
                new_faces.append(nf)
            bmesh.ops.recalc_face_normals(bm, faces=new_faces)
            keep = {v.index for f_ in new_faces for v in f_.verts}
            bm.to_mesh(garment.data)
            bm.free()
            piece(garment, "cf_hood", kit.faces_inside(faces_of(garment), keep),
                  material("cf_hood", hood, 0.78, sheen=0.45), 0.0, 0.007)
            cut_faces = kit.faces_inside(faces_of(garment), keep)          # off the garment again
            bm = bmesh.new()
            bm.from_mesh(garment.data)
            bm.faces.ensure_lookup_table()
            bmesh.ops.delete(bm, geom=[bm.faces[i] for i in cut_faces], context="FACES")
            bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
            bm.to_mesh(garment.data)
            bm.free()
            made.append(f"hood to {crown + 0.04:.2f} m")
        else:
            log("no hood: no head bone or head vertices found")

    # A Santa cap made for THIS head. The library's cap is one size, thin-banded and worn tilted - a
    # child's cap - and scaling it never gets to the real thing: a deep fur roll, a cone that curves over
    # and flops, a fat bobble. So it is built on the head it is going on, taking the skull's own circle as
    # its opening, which means it cannot bulge through. The live view builds the same shape from the same
    # measurements, so what you shape in the studio is what gets built. Maths: costume.santa_cap.
    if (DESIGN or {}).get("hat") in appearance.MADE_HATS:
        want = (DESIGN or {}).get("cap") or {}
        head_bone = next((h for h in (head("DEF-spine.006"), head("head")) if h is not None), None)
        skull = [body_w[v] for v in in_body if head_bone is not None and body_w[v][2] > head_bone.z + 0.03]
        if not skull:
            log("no santa cap: no head vertices found")
        else:
            size = float((DESIGN or {}).get("hat_size") or 1.0)
            crown = max(p[2] for p in skull)
            # A Santa cap's fur band sits on the forehead and above the ears, about 8.5 cm below the
            # crown on a grown head. Measuring higher catches the ears and the opening comes out loose.
            sit = crown - 0.085
            around = [p for p in skull if abs(p[2] - sit) < 0.02] or skull
            # Halfway between the extremes, not the average of the vertices: a head is not evenly meshed
            # (the face carries far more vertices than the back of the skull), so an average sits forward
            # of the real centre and the far side then measures as twice the radius.
            low_x, high_x = min(p[0] for p in around), max(p[0] for p in around)
            low_y, high_y = min(p[1] for p in around), max(p[1] for p in around)
            cx, cy = (low_x + high_x) / 2, (low_y + high_y) / 2
            # the average of the two half-extents, not the larger: a head is longer than it is wide
            wide = ((high_x - low_x) + (high_y - low_y)) / 4 + 0.006
            rings, fur, tip = kit.santa_cap(
                (cx, cy), sit, wide, wide * 3.0 * size,
                droop=float(want.get("droop", 0.6)), towards=float(want.get("towards", 20.0)),
                band=float(want.get("band", 0.3)))
            bobble = float(want.get("bobble", 1.0))
            balls = kit.ball(tip, wide * 0.42 * bobble) if bobble > 0.05 else []

            bm = bmesh.new()
            FUR, CLOTH = 0, 1
            tagged = []                                # (face, which material) - fur band or velvet

            def tube(shape, slot_for, cap_top):
                """Join a stack of rings into a tube, one row at a time, and say what each face is made of."""
                rows = [[bm.verts.new(p) for p in ring] for ring in shape]
                span = len(shape[0])
                for r in range(len(rows) - 1):
                    upper, lower = rows[r], rows[r + 1]
                    for i in range(span):
                        j = (i + 1) % span
                        try:
                            face = bm.faces.new([upper[i], upper[j], lower[j], lower[i]])
                        except ValueError:
                            continue
                        face.smooth = True
                        tagged.append((face, slot_for(r)))
                if cap_top:
                    try:
                        lid = bm.faces.new(rows[-1])
                        lid.smooth = True
                        tagged.append((lid, slot_for(len(rows) - 1)))
                    except ValueError:
                        pass

            tube(rings, lambda r: FUR if r < fur else CLOTH, cap_top=not balls)
            if balls:
                tube(balls, lambda _r: FUR, cap_top=True)
            bmesh.ops.recalc_face_normals(bm, faces=[f for f, _slot in tagged])
            mesh = bpy.data.meshes.new("cf_santa_cap")
            bm.to_mesh(mesh)
            bm.free()

            cap_obj = bpy.data.objects.new("cf_santa_cap", mesh)
            for c in human.users_collection:
                c.objects.link(cap_obj)
            cap_obj.data.materials.append(material("cf_cap_fur", lin(COSTUME.get("trim") or "#f3efe8"),
                                                   0.95, sheen=1.0, fluff=0.5))
            cap_obj.data.materials.append(material("cf_cap", lin(want.get("colour") or "#c8102e"),
                                                   0.55, sheen=0.6))
            for poly, (_face, slot_of) in zip(cap_obj.data.polygons, tagged):
                poly.material_index = slot_of
            # a cap moves with the head and nothing else: one bone, full weight
            group = cap_obj.vertex_groups.new(name="DEF-spine.006")
            group.add([v.index for v in cap_obj.data.vertices], 1.0, "REPLACE")
            rigged = cap_obj.modifiers.new("cf_cap_rig", "ARMATURE")
            rigged.object = rig
            cap_obj.parent = rig
            solid = cap_obj.modifiers.new("cf_cap_thick", "SOLIDIFY")
            solid.thickness, solid.offset = 0.006, -1.0
            # A cap sits ON hair: hide the hair that is under the band and keep the rest, so sideburns
            # and the hair at the back still show. Only a mask, so nothing is lost.
            if hair_obj:
                _, hair_w = rest(hair_obj)
                under = [i for i, p_ in enumerate(hair_w) if p_[2] > sit + 0.012]
                if under:
                    vg = hair_obj.vertex_groups.new(name="cf_under_cap")
                    vg.add(under, 1.0, "REPLACE")
                    m = hair_obj.modifiers.new("cf_hide_under_cap", "MASK")
                    m.vertex_group, m.invert_vertex_group = "cf_under_cap", True
                    made.append(f"hair tucked under the cap ({len(under)} of {len(hair_w)})")
            made.append(f"santa cap ({len(rings)} rings, {fur} fur, head {wide * 100:.0f} cm)")

    # --- things cut for THIS body: socks, footwear, a tie, a scarf, a watch, a band ---------------------
    # The wardrobe has twenty-six garments and not one sock, tie or watch among them, and its two pairs of
    # shoes are one size. These are measured off the body's own joint markers every time (blender/tailor.py
    # explains the arithmetic), so they fit a child and a heavy man without anybody choosing a size. Each
    # vertex takes the bone weights of the body vertex nearest it, which is what makes a sock bend with
    # the ankle and keeps a watch on the wrist through a whole scene.
    asked = tailor.asked_for(DESIGN or {})
    if asked:
        import preview_mesh as _pm
        joints = _pm.joint_centres(human, body_w)
        STUFF = {"knit": (0.90, 0.0, 0.85, 0.0), "cloth": (0.72, 0.0, 0.45, 0.0),
                 "leather": (0.55, 0.0, 0.10, 0.06), "rubber": (0.88, 0.0, 0.00, 0.0),
                 "metal": (0.22, 0.95, 0.0, 0.35)}

        def wear_made(what, want):
            """One made wearable as its own object, rigged to whatever the body does at that point."""
            pieces = tailor.cut(what, joints, want)
            if not pieces:
                log(f"no {what}: this body has no joint markers to measure it on")
                return
            colour = lin(want.get("colour")) or (0.2, 0.2, 0.2)
            bm = bmesh.new()
            slots, tagged = [], []
            for part in pieces:
                if part["stuff"] not in slots:
                    slots.append(part["stuff"])
                slot = slots.index(part["stuff"])
                rows = [[bm.verts.new(p) for p in ring] for ring in part["rings"]]
                span = len(rows[0])
                for r in range(len(rows) - 1):
                    for i in range(span):
                        j = (i + 1) % span
                        try:
                            f = bm.faces.new([rows[r][i], rows[r][j], rows[r + 1][j], rows[r + 1][i]])
                        except ValueError:
                            continue
                        f.smooth = True
                        tagged.append((f, slot))
                for end, close in ((rows[0], part["shut"]), (rows[-1], part["lid"])):
                    if not close:
                        continue
                    try:
                        f = bm.faces.new(end)
                    except ValueError:
                        continue
                    f.smooth = True
                    tagged.append((f, slot))
            if not tagged:
                bm.free()
                return
            bmesh.ops.recalc_face_normals(bm, faces=[f for f, _s in tagged])
            mesh = bpy.data.meshes.new(f"cf_{what}")
            bm.to_mesh(mesh)
            bm.free()

            obj = bpy.data.objects.new(f"cf_{what}", mesh)
            for c in human.users_collection:
                c.objects.link(obj)
            for stuff in slots:
                rough, metal, sheen, coat = STUFF.get(stuff, STUFF["cloth"])
                # a sole is the same leather, darker: nobody wears a shoe whose sole matches its upper
                shade = colour if stuff != "rubber" else tuple(x * 0.35 for x in colour)
                obj.data.materials.append(material(f"cf_{what}_{stuff}", shade, rough, metal=metal,
                                                   sheen=sheen, coat=coat))
            for poly, (_f, slot) in zip(obj.data.polygons, tagged):
                poly.material_index = slot
            # a new object sits at the origin, so its mesh coordinates are already the world ones the
            # pattern was cut in - the same reason the Santa cap can be built straight from measurements
            groups, hold = {}, {}
            for v in obj.data.vertices:
                _, near, _ = body_kd.find(tuple(v.co))
                for bone, weight in rigging.keep_strongest(body_weights(near)).items():
                    hold.setdefault(bone, []).append((v.index, weight))
            for bone, members in hold.items():
                groups[bone] = obj.vertex_groups.new(name=bone)
                for index, weight in members:
                    groups[bone].add([index], weight, "REPLACE")
            rigged = obj.modifiers.new(f"cf_{what}_rig", "ARMATURE")
            rigged.object = rig
            obj.parent = rig
            made.append(f"{what} for this body ({len(pieces)} pieces, {len(mesh.vertices)} vertices, "
                        f"{len(hold)} bones)")

        for _what, _want in asked:
            wear_made(_what, _want)

    # a cape: a sheet hanging from the back of the collar to the knees, weighted to the chest so it swings
    cape = lin(COSTUME.get("cape"))
    if cape and garment:
        _, co = rest(garment)
        shoulder_z = head("DEF-upper_arm.L").z
        centre_y = head("DEF-spine.003").y
        line = kit.shoulder_line(co, range(len(co)), (centre_x, centre_y), face=-1.0,
                                 z=shoulder_z - 0.02, band=0.07, count=13)
        if len(line) >= 3:
            # the vertices the line came from carry the weights the cape's top edge inherits
            arc = [min(range(len(co)), key=lambda v, p=p: (co[v][0] - p[0]) ** 2 + (co[v][1] - p[1]) ** 2
                       + (co[v][2] - p[2]) ** 2) for p in line]
            c = (centre_x, centre_y, shoulder_z)
            drop = float(COSTUME.get("cape_length", 0.75)) * (c[2] - knee_z)
            n_rings = max(4, round(drop / 0.07))
            rows = kit.cape_rings(line, c[:2], drop, n_rings, flare=0.35, sway=0.14)
            rows = [[clear_of_body(p) for p in row] for row in rows]
            names = {g.index: g.name for g in garment.vertex_groups}
            top_w = [{names[g.group]: g.weight for g in garment.data.vertices[v].groups} for v in arc]
            bm = bmesh.new()
            bm.from_mesh(garment.data)
            bm.verts.ensure_lookup_table()
            uv = bm.loops.layers.uv.active
            deform = bm.verts.layers.deform.verify()
            inv = np.linalg.inv(np.array(garment.matrix_world))
            made_rows = []
            for k, row in enumerate(rows, 1):
                row_verts = []
                for i, p in enumerate(row):
                    nv = bm.verts.new((inv @ np.array([*p, 1.0]))[:3])
                    _, near, _ = body_kd.find(p)
                    # near the collar the cape follows the chest; lower down it hangs from the spine
                    w = kit.mix_weights(top_w[i], body_weights(near), 0.15 * k / len(rows))
                    for g, wt in w.items():
                        gi = garment.vertex_groups.get(g) or garment.vertex_groups.new(name=g)
                        nv[deform][gi.index] = wt
                    row_verts.append(nv)
                made_rows.append(row_verts)
            bm.verts.index_update()
            bm.verts.ensure_lookup_table()
            new_faces = []
            for f in kit.ring_faces(arc, [[v.index for v in r] for r in made_rows], closed=False):
                try:
                    nf = bm.faces.new([bm.verts[i] for i in f])
                except ValueError:
                    continue
                nf.smooth = True
                for loop in nf.loops:
                    loop[uv].uv = (0.5, 0.5)
                new_faces.append(nf)
            bmesh.ops.recalc_face_normals(bm, faces=new_faces)
            keep = {v.index for f_ in new_faces for v in f_.verts}
            bm.to_mesh(garment.data)
            bm.free()
            piece(garment, "cf_cape", kit.faces_inside(faces_of(garment), keep),
                  material("cf_cape", cape, 0.75, sheen=0.5), 0.0, 0.006)
            # the cape lives as its own object: take the faces back off the garment
            cut_faces = kit.faces_inside(faces_of(garment), keep)
            bm = bmesh.new()
            bm.from_mesh(garment.data)
            bm.faces.ensure_lookup_table()
            bmesh.ops.delete(bm, geom=[bm.faces[i] for i in cut_faces], context="FACES")
            bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
            bm.to_mesh(garment.data)
            bm.free()
            made.append(f"cape {drop:.2f} m")

    gloves = lin(COSTUME.get("gloves"))
    if gloves:
        HAND = ("hand", "palm", "thumb", "f_index", "f_middle", "f_ring", "f_pinky")
        names = {g.index: g.name.lower() for g in human.vertex_groups}
        verts = {v.index for v in human.data.vertices if v.index in in_body and
                 sum(g.weight for g in v.groups if any(h in names[g.group] for h in HAND)) >= 0.5}
        piece(human, "cf_gloves", kit.faces_inside(faces_of(human), verts),
              material("cf_gloves", gloves, 0.8, sheen=0.4), 0.0025, 0.0)
        made.append(f"gloves ({len(verts)} vertices)")

    if COSTUME.get("boots") and shoes_obj:
        _, co = rest(shoes_obj)
        fs = faces_of(shoes_obj)
        tops = kit.highest_per_side(co, kit.boundary_loops(fs), centre_x)
        top_z = min(kit.centroid(co, l)[2] for l in tops) if tops else None
        if trim and tops:
            keep = set().union(*kit.boot_bands(co, fs, centre_x).values(), set())
            piece(shoes_obj, "cf_boot_trim", kit.faces_inside(fs, keep),
                  material("cf_fur_boots", trim, 0.95, sheen=1.0, fluff=0.5), 0.006, 0.014)
        if bottom_obj and top_z is not None and clothing.get("garment") == "trousers":
            _, bco = rest(bottom_obj)     # trousers tucked into the boots
            tucked = [i for i, p in enumerate(bco) if p[2] < top_z - 0.015]
            if tucked:
                vg = bottom_obj.vertex_groups.new(name="cf_in_boots")
                vg.add(tucked, 1.0, "REPLACE")
                m = bottom_obj.modifiers.new("cf_hide_in_boots", "MASK")
                m.vertex_group, m.invert_vertex_group = "cf_in_boots", True
        made.append(f"boots (top {top_z:.2f} m)" if top_z is not None else "boots")
    log("costume", made)

# --- the rig, tidied -------------------------------------------------------------------------------------
# Automatic weighting leaves vertices pulled by eight or nine bones. No exporter keeps more than four, and
# the extra ones are noise that makes a shoulder or a jaw mushy when it moves. Keeping the strongest four
# and normalising is what `core/rigging.py` describes and `blender/rig_check.py` applies; the check then
# measures the result, so the two can never quietly disagree. It costs about five seconds.
sys.path.insert(0, HERE)
import rig_check as _rig                                   # noqa: E402

tidied = 0
for _mesh in [o for o in bpy.data.objects
              if o.type == "MESH" and any(m.type == "ARMATURE" for m in o.modifiers)]:
    tidied += _rig.tidy(_mesh)
log(f"rig tidied: {tidied} vertices were pulled by more than {rigging.MOST} bones")
_facts = _rig.look_over(rig, human)
for _line in rigging.problems(_facts):
    log("WARNING rig:", _line)
log("rig", rigging.verdict(_facts))
# kept beside the .blend so the app can say whether a character is fit to animate without opening Blender
json.dump({**_facts, "problems": rigging.problems(_facts), "verdict": rigging.verdict(_facts)},
          open(os.path.splitext(os.path.abspath(args.out))[0] + ".rig.json", "w", encoding="utf-8"), indent=1)

# self-contained: textures (skin, clothes, the face photo) go inside the .blend, so the character still
# works after it is copied into a movie folder
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.out))
log("saved", args.out)

# --- previews ------------------------------------------------------------------------------------
if args.preview:
    os.makedirs(args.preview, exist_ok=True)
    scene = bpy.context.scene
    for engine in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    scene.render.resolution_x, scene.render.resolution_y = 600, 1000
    world = bpy.data.worlds.new("W"); scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.8, 0.82, 0.85, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.6
    for rot, energy in (((0.9, 0, 0.5), 3.0), ((1.2, 0, 3.6), 1.5)):
        sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
        sun.data.energy = energy
        sun.rotation_euler = rot
        scene.collection.objects.link(sun)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = want * 1.15
    import math
    for tag, ang in (("front", 0), ("side", 90), ("back", 180)):
        a = math.radians(ang)
        cam.location = (6 * math.sin(a), -6 * math.cos(a), want / 2)
        cam.rotation_euler = (math.radians(90), 0, a)
        scene.render.filepath = os.path.join(os.path.abspath(args.preview), f"{tag}.png")
        bpy.ops.render.render(write_still=True)
    log("previews", args.preview)
