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
    args.gender = args.gender or DESIGN["gender"]
    args.age = args.age or float(DESIGN["age"])
    args.height_cm = args.height_cm or float(DESIGN["height_cm"])
    if hair.get("style") and hair["style"] != "auto":
        args.hair = args.hair or hair["style"]
    spec = {"ratios": {}, "face": None,
            "colours": {"skin": rgb(DESIGN.get("skin")), "hair": rgb(hair.get("color")),
                        "top": rgb(outfit.get("top")), "bottom": rgb(outfit.get("bottom")),
                        "shoes": rgb(outfit.get("shoes"))},
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
if DESIGN:
    wt, mu, pr = BUILDS.get(DESIGN.get("build", "average"), BUILDS["average"])
    best = (0.0, {"weight": wt, "muscle": mu, "proportions": pr})
for weight in ((0.15, 0.35, 0.5, 0.65, 0.85) if not DESIGN else ()):
    for muscle in (0.25, 0.5, 0.75):
        for proportions in (0.0, 0.5, 1.0):
            set_macros(weight=weight, muscle=muscle, proportions=proportions)
            e = error()
            if e < best[0]:
                best = (e, {"weight": weight, "muscle": muscle, "proportions": proportions})
# refine around the best grid point
step = {"weight": 0.08, "muscle": 0.1, "proportions": 0.2}
for _ in range(2 if not DESIGN else 0):
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

    # face-shape variables: (name, [targets for +], [targets for -]); eyes/cheeks mirrored
    def lr(t):
        return [f"l-{t}", f"r-{t}"]
    VARS = [("head-scale-horiz", ["head-scale-horiz-incr"], ["head-scale-horiz-decr"]),
            ("head-scale-vert", ["head-scale-vert-incr"], ["head-scale-vert-decr"]),
            ("head-fat", ["head-fat-incr"], ["head-fat-decr"])]
    VARS += [(s, [s], []) for s in ("head-oval", "head-round", "head-square", "head-triangular",
                                    "head-invertedtriangular", "head-diamond", "head-rectangular")]
    for base in ("nose-scale-horiz", "nose-scale-vert", "nose-width1", "nose-width2", "nose-width3",
                 "nose-nostrils-width", "nose-point-width", "nose-flaring", "mouth-scale-horiz", "mouth-scale-vert",
                 "mouth-upperlip-height", "mouth-lowerlip-height", "mouth-upperlip-width", "mouth-lowerlip-width",
                 "chin-width", "chin-height", "chin-bones", "forehead-scale-vert"):
        VARS.append((base, [f"{base}-incr"], [f"{base}-decr"]))
    VARS += [("nose-trans-vert", ["nose-trans-up"], ["nose-trans-down"]),
             ("mouth-trans-vert", ["mouth-trans-up"], ["mouth-trans-down"]),
             ("mouth-angles", ["mouth-angles-up"], ["mouth-angles-down"]),
             ("eyebrows-trans-vert", ["eyebrows-trans-up"], ["eyebrows-trans-down"]),
             ("eyebrows-angle", ["eyebrows-angle-up"], ["eyebrows-angle-down"]),
             ("eye-scale", lr("eye-scale-incr"), lr("eye-scale-decr")),
             ("eye-trans-horiz", lr("eye-trans-out"), lr("eye-trans-in")),
             ("eye-trans-vert", lr("eye-trans-up"), lr("eye-trans-down")),
             ("eye-height2", lr("eye-height2-incr"), lr("eye-height2-decr")),
             ("eye-corner1", lr("eye-corner1-up"), lr("eye-corner1-down")),
             ("eye-corner2", lr("eye-corner2-up"), lr("eye-corner2-down")),
             ("cheek-bones", lr("cheek-bones-incr"), lr("cheek-bones-decr")),
             ("cheek-volume", lr("cheek-volume-incr"), lr("cheek-volume-decr"))]

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
brows_obj = asset("eyebrow001/eyebrow001.mhclo", "eyebrows", "Eyebrows")
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
h_name = args.hair or (HAIR[(args.gender, spec["hair_length"])] if spec.get("hair_length", "none") != "none"
                       else "none")
if (DESIGN or {}).get("hat", "none") != "none":
    h_name = "none"
if h_name != "none":
    hair_obj = asset(f"{h_name}/{h_name}.mhclo", "hair", "Hair")
    log("hair", h_name)

# beards and hats (CC0 packs bodyparts05, hats01); a beard takes the hair colour
BEARDS = {"scruffy": "wdg_scruffy_beard", "long": "rehmanpolanski_beard_viking", "full": "grinsegold_beard_sigmund_wip",
          "faun": "culturalibre_faun_beard", "moustache": "rehmanpolanski_moustache_viking"}
HATS = {"santa": "joepal_xmas_cap", "newsboy": "jujube_newsboy_cap"}
beard_obj = hat_obj = None
beard = (DESIGN or {}).get("beard", "none")
if beard in BEARDS:
    beard_obj = asset(f"{BEARDS[beard]}/{BEARDS[beard]}.mhclo", "clothes", "Clothes")
    log("beard", beard)
hat = (DESIGN or {}).get("hat", "none")
if hat in HATS:
    hat_obj = asset(f"{HATS[hat]}/{HATS[hat]}.mhclo", "clothes", "Clothes")
    log("hat", hat)

# plain garments (CC0 packs) whose textures recolour cleanly; picked from what the photo shows
clothing = spec.get("clothing", {"garment": "trousers", "sleeves": "long"})
TOP = {("male", "short"): "elvs_crude_t-shirt_male", ("female", "short"): "joepal_crude_t-shirt_female",
       ("male", "long"): "toigo_fisherman_sweater", ("female", "long"): "toigo_fisherman_sweater"}
BOTTOM = {"trousers": "toigo_wool_pants", "shorts": "cortu_jeans_shorts", "skirt": "toigo_tiered_mini_skirt"}


def cloth(name):
    return asset(f"{name}/{name}.mhclo", "clothes", "Clothes")


top_obj = bottom_obj = dress_obj = None
if clothing["garment"] == "dress":
    dress_obj = cloth("toigo_shift_dress")
    worn = ["toigo_shift_dress"]
else:
    top_name = TOP[(args.gender, clothing["sleeves"])]
    bottom_name = BOTTOM[clothing["garment"]]
    bottom_obj, top_obj = cloth(bottom_name), cloth(top_name)
    worn = [top_name, bottom_name]
shoes_obj = cloth("shoes04")
log("wearing", worn + ["shoes04"], clothing)

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
if beard_obj and cols.get("hair"):
    recolour(beard_obj, cols["hair"])
if shoes_obj and cols.get("shoes"):
    recolour(shoes_obj, cols["shoes"])
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
