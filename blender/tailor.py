"""Wearables cut for the body they are going on: socks, shoes, a watch, cuffs, a tie, a scarf.

(pure, tested; no bpy - the same arithmetic runs in the build and in the live view)

The wardrobe ships about sixty MakeHuman assets and every one of them is one size, fitted to whatever body
wears it. That works for a coat. It does not work for the small things, and the small things are what makes
someone look dressed rather than draped: a sock has to end where the trouser ends, a watch has to be the
width of that wrist, a shoe has to be the length of that foot. There is no asset for any of it.

So these are MADE, like `costume.santa_cap` is - cut from the body's own measurements every time, which is
why they fit anybody at any height and need nothing exported, cached or fitted.

Everything here is measured from MakeHuman's own joint markers (`preview_mesh.joint_centres`, 43 of them,
carried in every preview kit), and - the point worth keeping - NO pattern here names a global axis. Up is
the way from this ankle to this knee; forward is the way from this ankle to this toe; across is what is
left. So the same function serves the build (z up) and the live view (y up) without a single swap, which is
exactly where the Santa cap needed two implementations and got the axes wrong twice.

Sizes are proportions of the body's own bones, never centimetres: an ankle is a fraction of its own shin,
so a child, a tall man and a heavy woman all get a sock that fits without anybody saying so.
"""
import math

SPAN = 14                 # points round a limb: enough to read as round, cheap enough to rebuild live
SQUARE = 4                # ...and four makes a strap or a case instead

# what can be cut, where its colour comes from, and what it is made of
WEARABLES = {
    "socks": ("costume.socks", "knit", "socks up the lower leg, cut for this ankle and calf"),
    "shoes_made": ("outfit.shoes", "leather", "shoes or boots the length of this foot"),
    "watch": ("costume.watch", "metal", "a watch on the wrist, the width of that wrist"),
    "wristband": ("costume.wristband", "leather", "a band or bracer round the forearm"),
    "tie": ("costume.tie", "cloth", "a tie knotted at the collar, hanging down the chest"),
    "scarf": ("costume.scarf", "knit", "a scarf round the neck with the ends hanging"),
}
SOCK_HEIGHTS = {"ankle": 0.12, "crew": 0.42, "knee": 0.95}
SHOE_STYLES = ("none", "shoe", "boot", "sneaker", "sandal", "heel")
SIDES = {"left": ("l",), "right": ("r",), "both": ("l", "r")}


# --- small vector arithmetic (no numpy: this runs inside Blender, in tests, and is ported to the browser)

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def _long(a):
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def _unit(a):
    n = _long(a)
    return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-9 else (0.0, 0.0, 0.0)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _mix(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _flat(point, plane, up):
    """`point` brought onto the plane through `plane`, perpendicular to `up`.

    This is how a sole is laid flat: the ankle brought down to the ground the foot is standing on, with no
    global axis anywhere in it - `up` is this leg's own."""
    return _sub(point, _mul(up, _dot(_sub(point, plane), up)))


def _frame(along, hint):
    """An axis and two perpendiculars to it, `hint` deciding which way round they lie.

    `hint` is a direction from the body itself (the way the foot points, the way the leg goes), never a
    global axis - that is what keeps every pattern here working in the build and in the viewer alike."""
    a = _unit(along)
    if a == (0.0, 0.0, 0.0):
        return (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
    side = _cross(hint, a)
    if _long(side) < 1e-6:                      # hint lies along the axis: anything perpendicular will do
        side = _cross((a[1], a[2], a[0]), a)
    side = _unit(side)
    return a, side, _cross(a, side)


# --- the one shape every wearable is made of ------------------------------------------------------------

def sweep(path, radii, hint=None, span=SPAN, squash=None):
    """Rings round a path: at each point, a ring held perpendicular to the way the path is going.

    This is the only shape in the file. A sock is a sweep up a leg, a watch strap is a short sweep round a
    wrist, a watch case is a four-point sweep (so: a box) along the back of the hand, a tie is a sweep
    squashed flat until it is a ribbon. One primitive, tested once.

    `radii` is one radius per point, `squash` an optional one-per-point ratio of the second axis to the
    first (0.4: half as thick as it is wide), and `hint` the body direction that decides which way round
    the ring is laid out: the first radius lies along `hint` x axis, the squashed one perpendicular to
    both. So `hint` must never be the way the path itself is going - that frame is undefined, and the
    fallback picks an arbitrary perpendicular, which is how a sole came out standing on its edge. Where a
    path turns a corner (a sock going over a foot and then up a leg) pass one hint per point."""
    if len(path) < 2:
        return []
    many = bool(hint) and isinstance(hint[0], (list, tuple))
    hints = list(hint) if many else [hint] * len(path)
    out = []
    for i, centre in enumerate(path):
        ahead = path[min(i + 1, len(path) - 1)]
        behind = path[max(i - 1, 0)]
        here = hints[min(i, len(hints) - 1)]
        if here is None:
            step = _sub(ahead, behind)
            here = (step[1], step[2], step[0])  # anything not along the path
        _a, side, other = _frame(_sub(ahead, behind), here)
        rx = radii[min(i, len(radii) - 1)]
        ry = rx * (squash[min(i, len(squash) - 1)] if squash else 1.0)
        ring = []
        for j in range(span):
            ang = 2.0 * math.pi * j / span
            ring.append(_add(centre, _add(_mul(side, rx * math.cos(ang)),
                                          _mul(other, ry * math.sin(ang)))))
        out.append(ring)
    return out


def piece(name, stuff, rings, shut=False, lid=False):
    """One lump of a wearable: its rings, what it is made of, and whether its ends are closed."""
    return {"name": name, "stuff": stuff, "rings": rings, "shut": shut, "lid": lid}


# --- measuring the body ---------------------------------------------------------------------------------

def leg(joints, side):
    """Ankle, instep, toe, knee and the shin's length for one leg; None when the body has no such joints.

    Two different "up"s come back and the difference matters. `up` is the SHIN's, which is what a sock
    wraps round. `stand` is the BODY's, which is what a shoe sits on: a sole lies on the floor, not
    perpendicular to a shin, and a shin leans - laying the sole out across it tips the shoe onto its edge
    and lifts the heel 2 cm up the leg. Both are measured on the body, so neither names a global axis."""
    want = {k: joints.get(f"joint-{side}-{k}") for k in ("ankle", "foot-1", "foot-2", "knee")}
    if any(v is None for v in want.values()):
        return None
    shin = _long(_sub(want["knee"], want["ankle"]))
    if shin < 1e-4:
        return None
    up = _unit(_sub(want["knee"], want["ankle"]))
    floor, pelvis = joints.get("joint-ground"), joints.get("joint-pelvis")
    stand = _unit(_sub(pelvis, floor)) if floor is not None and pelvis is not None else up
    return {"ankle": want["ankle"], "instep": want["foot-1"], "toe": want["foot-2"],
            "knee": want["knee"], "shin": shin, "up": up,
            "stand": stand if stand != (0.0, 0.0, 0.0) else up,
            "floor": floor if floor is not None else want["foot-1"],
            "across": _unit(_cross(_sub(want["foot-2"], want["ankle"]), up)),
            "forward": _unit(_sub(want["foot-2"], want["ankle"]))}


def arm(joints, side):
    """Wrist, elbow, the forearm's length and which way the back of the hand faces."""
    wrist, elbow = joints.get(f"joint-{side}-hand"), joints.get(f"joint-{side}-elbow")
    knuckle = joints.get(f"joint-{side}-hand-2") or joints.get(f"joint-{side}-hand-3")
    if wrist is None or elbow is None:
        return None
    fore = _long(_sub(elbow, wrist))
    if fore < 1e-4:
        return None
    # the arm hangs beside the body, so "away from the other wrist" is out, and that needs no global axis
    other = joints.get("joint-r-hand" if side == "l" else "joint-l-hand")
    out = _unit(_sub(wrist, other)) if other is not None else _unit(_sub(wrist, elbow))
    return {"wrist": wrist, "elbow": elbow, "fore": fore, "out": out,
             "along": _unit(_sub(elbow, wrist)),
             "hand": _unit(_sub(knuckle, wrist)) if knuckle is not None else _unit(_sub(wrist, elbow))}


def trunk(joints):
    """Neck, pelvis, the trunk's length, and the way the body faces (taken from the feet)."""
    neck, pelvis = joints.get("joint-neck"), joints.get("joint-pelvis")
    if neck is None or pelvis is None:
        return None
    tall = _long(_sub(neck, pelvis))
    if tall < 1e-4:
        return None
    ahead = None
    foot, ankle = joints.get("joint-l-foot-2"), joints.get("joint-l-ankle")
    if foot is not None and ankle is not None:
        up = _unit(_sub(neck, pelvis))
        flat = _sub(foot, ankle)
        # the part of "toes" that is not up or down: where the body is looking
        dot = flat[0] * up[0] + flat[1] * up[1] + flat[2] * up[2]
        ahead = _unit(_sub(flat, _mul(up, dot)))
    return {"neck": neck, "pelvis": pelvis, "tall": tall, "up": _unit(_sub(neck, pelvis)),
            "ahead": ahead or (0.0, 0.0, 0.0),
            "wide": _long(_sub(joints.get("joint-l-shoulder", neck),
                               joints.get("joint-r-shoulder", neck))) or tall * 0.45}


# --- the patterns ---------------------------------------------------------------------------------------

def sock(joints, side, height="crew", girth=1.0, over_foot=True):
    """A sock: over the foot, round the heel and up the leg as far as asked.

    An ankle is about a tenth of its own shin and a calf about a sixth, which is why this fits a child and
    a heavy man without being told. `height` is a name from SOCK_HEIGHTS, as a fraction of the shin."""
    low = leg(joints, side)
    if not low:
        return []
    shin, up, stand, floor = low["shin"], low["up"], low["stand"], low["floor"]
    rise = SOCK_HEIGHTS.get(height, SOCK_HEIGHTS["crew"]) * shin
    r_ankle, r_calf = shin * 0.115 * girth, shin * 0.155 * girth
    # how far up the calf this sock actually reaches, and how it narrows again towards the knee
    grown = min(1.0, rise / (shin * 0.55))
    r_top = r_ankle + (r_calf - r_ankle) * grown
    if rise > shin * 0.5:
        r_top *= max(0.76, 1.0 - (rise / shin - 0.5) * 0.5)
    path, radii, squash, hints = [], [], [], []
    if over_foot:
        # A foot stands ON the floor, and the joints that mark it are ON the sole - so a ring centred on
        # the instep marker has half of itself underground. Each ring is lifted by its own half-depth,
        # which is what puts the bottom of the sock exactly on the floor whatever size the foot is.
        ankle_flat = _flat(low["ankle"], floor, stand)
        for at, r, sq in ((_flat(_mix(low["toe"], low["instep"], -0.10), floor, stand),
                           shin * 0.062 * girth, 0.76),
                          (_flat(low["instep"], floor, stand), shin * 0.090 * girth, 0.90),
                          (_mix(_flat(low["instep"], floor, stand), ankle_flat, 0.8),
                           shin * 0.098 * girth, 0.95)):
            path.append(_add(at, _mul(stand, r * sq)))
            radii.append(r)
            squash.append(sq)                   # a foot is wider than it is deep
            hints.append(stand)                 # ...and the path runs along the foot here
    top = _add(low["ankle"], _mul(up, rise))
    path += [_add(low["ankle"], _mul(up, shin * 0.02)), _mix(low["ankle"], top, 0.55), top]
    radii += [r_ankle, r_ankle + (r_top - r_ankle) * 0.75, r_top]
    squash += [1.0, 1.0, 1.0]
    hints += [low["forward"]] * 3               # ...and up the leg here
    return [piece(f"sock_{side}", "knit", sweep(path, radii, hint=hints, squash=squash),
                  shut=over_foot)]


def shoe(joints, side, style="shoe", girth=1.0):
    """A shoe the length of this foot: a sole under it, an upper over it, and a shaft if it is a boot.

    The sole is what makes it read as footwear rather than a thick sock, and it has to lie on the GROUND -
    the plane the foot is standing on, which is the instep joint's own level, not the ankle's. Laying it
    out from the ankle puts the whole shoe 6 cm up the leg, which looks exactly like what it is."""
    low = leg(joints, side)
    if not low or style in ("none", None):
        return []
    shin, up = low["shin"], low["stand"]          # the BODY's up: a sole lies on the floor (see `leg`)
    along = _unit(_sub(low["toe"], low["instep"]))
    flat = _unit(_sub(along, _mul(up, _dot(along, up))))              # the way the foot points, levelled
    if flat == (0.0, 0.0, 0.0):
        flat = along
    ground = low["floor"]                         # the floor the body is standing on
    # A foot is longer than its toe joint - the joint is the ball and the shoe runs on over the toes -
    # but not by much. Measured on a built 1.80 m man: heel to toe is 28 cm, and reaching 0.22 of a shin
    # behind the ankle and 1.6 of the way past the instep made a 37 cm shoe. It looked like one.
    back = _add(_flat(low["ankle"], ground, up), _mul(flat, -shin * 0.135))
    front = _flat(_mix(low["instep"], low["toe"], 1.18), ground, up)
    wide = shin * (0.125 if style == "sneaker" else 0.112) * girth
    thin = 0.34 if style == "sneaker" else 0.28
    thick = wide * thin                           # half the sole's depth: it sits this far off the ground
    rise = shin * 0.085 if style == "heel" else 0.0
    out = []

    # Four rings, not three: a sole that narrows all the way from the ball to the tip is narrower than
    # the toes for the whole length of them, and they come out of the sides of the shoe. It stays full
    # width to nine tenths of the way along and only then rounds off.
    sole = [_add(back, _mul(up, thick + rise)),
            _add(_mix(back, front, 0.50), _mul(up, thick + rise * 0.35)),
            _add(_mix(back, front, 0.88), _mul(up, thick)),
            _add(front, _mul(up, thick))]
    out.append(piece(f"sole_{side}", "rubber",
                     sweep(sole, [wide * 0.96, wide * 1.08, wide * 1.00, wide * 0.66], hint=up,
                           squash=[thin, thin, thin, thin]),
                     shut=True, lid=True))
    if rise:                                      # a block from the raised back of the sole to the ground
        out.append(piece(f"heel_{side}", "leather",
                         sweep([_add(back, _mul(up, thick + rise * 0.6)), back],
                               [wide * 0.46, wide * 0.36], hint=flat, span=SQUARE,
                               squash=[0.62, 0.62]), lid=True))
    if style == "sandal":                         # two straps over the foot, no upper at all
        for t in (0.30, 0.68):
            at = _mix(_add(back, _mul(up, thick)), _add(front, _mul(up, thick)), t)
            out.append(piece(f"strap{int(t * 100)}_{side}", "leather",
                             sweep([at, _add(at, _mul(up, shin * 0.085 * (1.0 - t * 0.4)))],
                                   [wide * 0.94, wide * 0.78], hint=flat, span=SQUARE,
                                   squash=[0.20, 0.20]), lid=True))
        return out

    over = shin * 0.085                           # how high the top of the foot stands off the sole
    upper = [_add(_mix(back, front, 0.97), _mul(up, thick * 1.8)),
             _add(_mix(back, front, 0.86), _mul(up, over * 0.52)),
             _add(_flat(_mix(low["instep"], low["toe"], 0.5), ground, up), _mul(up, over * 0.78)),
             _add(_flat(low["instep"], ground, up), _mul(up, over)),
             _add(low["ankle"], _mul(low["up"], shin * 0.075))]
    # An ankle is about 0.105 of its own shin across (that is what a sock is cut to), so an opening any
    # narrower than that is inside the leg and the leg comes through it - which is exactly what it looked
    # like: bare skin between the trouser and the shoe.
    # a gentle run out to the toe: jumping the width in one segment creases the upper, and a crease on a
    # dark glossy shoe catches the key light as a hard grey band across the instep
    radii = [wide * 0.70, wide * 0.88, wide * 0.94, wide * 0.95, shin * 0.128 * girth]
    squash = [0.62, 0.74, 0.84, 0.96, 1.00]
    if style == "boot":                           # carry straight on up the leg
        upper.append(_add(low["ankle"], _mul(low["up"], shin * 0.58)))
        radii.append(shin * 0.142 * girth)        # a shaft, not a bell: a boot barely widens
        squash.append(1.0)
    hints = [up] * 5 + ([flat] if style == "boot" else [])       # over the foot, then up the leg
    out.append(piece(f"shoe_{side}", "leather", sweep(upper, radii, hint=hints, squash=squash), shut=True))
    return out


def watch(joints, side="l", girth=1.0, face=1.0):
    """A watch: a strap round the wrist and a case standing off the back of it.

    The strap is the wrist's own width - a sixth of the forearm - so it is never a bangle on a child."""
    up = arm(joints, side)
    if not up:
        return []
    fore, towards = up["fore"], up["along"]
    at = _add(up["wrist"], _mul(towards, fore * 0.13))
    r = fore * 0.165 * girth
    strap = sweep([_add(at, _mul(towards, -fore * 0.035)), _add(at, _mul(towards, fore * 0.035))],
                  [r, r], hint=up["out"], squash=[0.78, 0.78], span=SPAN)
    outward = up["out"]
    base = _add(at, _mul(outward, r * 0.72))
    case = sweep([base, _add(base, _mul(outward, fore * 0.030 * face))],
                 [fore * 0.105 * face, fore * 0.098 * face], hint=towards, span=SPAN, squash=[1.0, 1.0])
    return [piece(f"watch_strap_{side}", "leather", strap),
            piece(f"watch_case_{side}", "metal", case, lid=True)]


def wristband(joints, side="l", width=1.0, girth=1.0):
    """A band, bracer or sweatband round the forearm. `width` 1 is a cuff, 2.5 a bracer up the arm."""
    up = arm(joints, side)
    if not up:
        return []
    fore, towards = up["fore"], up["along"]
    at = _add(up["wrist"], _mul(towards, fore * 0.12))
    reach = fore * 0.085 * width
    r0, r1 = fore * 0.168 * girth, fore * 0.178 * girth
    return [piece(f"wristband_{side}", "leather",
                  sweep([at, _add(at, _mul(towards, reach))], [r0, r1], hint=up["out"]))]


def tie(joints, length=1.0, width=1.0, knot=1.0):
    """A tie: a knot at the collar and a blade hanging down the front of the chest.

    The blade is a sweep squashed until it is a ribbon, and it narrows to a point, which is the whole
    difference between a tie and a strip of cloth."""
    mid = trunk(joints)
    if not mid or mid["ahead"] == (0.0, 0.0, 0.0):
        return []
    tall, up, ahead = mid["tall"], mid["up"], mid["ahead"]
    collar = _add(_add(mid["neck"], _mul(up, -tall * 0.04)), _mul(ahead, mid["wide"] * 0.30))
    w = mid["wide"] * 0.085 * width
    out = [piece("tie_knot", "cloth",
                 sweep([_add(collar, _mul(up, tall * 0.035)), _add(collar, _mul(up, -tall * 0.02))],
                       [w * 0.85, w * 1.05], hint=ahead, squash=[0.55, 0.55]), shut=True, lid=True)]
    # From the collar to the belt is very nearly the whole trunk: measured on a built 1.80 m man, a drop
    # of 0.56 of it stopped 22 cm short and read as a bib.
    drop = tall * 0.92 * length
    blade, radii, squash = [], [], []
    for i in range(5):
        t = i / 4.0
        blade.append(_add(_add(collar, _mul(up, -tall * 0.02 - drop * t)),
                          _mul(ahead, -mid["wide"] * 0.012 * t)))       # follows the chest in
        radii.append(w * (1.0 + 0.18 * t) * (1.0 - 0.92 * max(0.0, t - 0.86) / 0.14))
        squash.append(0.34)
    out.append(piece("tie_blade", "cloth", sweep(blade, radii, hint=ahead, squash=squash), lid=True))
    return out


def scarf(joints, drop=1.0, girth=1.0):
    """A scarf: a loop round the neck and a tail hanging down the front."""
    mid = trunk(joints)
    if not mid:
        return []
    tall, up, ahead = mid["tall"], mid["up"], mid["ahead"]
    at = _add(mid["neck"], _mul(up, tall * 0.045))
    r = mid["wide"] * 0.195 * girth
    loop = sweep([_add(at, _mul(up, tall * 0.045)), at, _add(at, _mul(up, -tall * 0.045))],
                 [r * 0.94, r, r * 1.02], hint=ahead if ahead != (0.0, 0.0, 0.0) else up,
                 squash=[0.88, 0.88, 0.88])
    out = [piece("scarf_loop", "knit", loop)]
    if ahead != (0.0, 0.0, 0.0):
        hang = _add(_add(at, _mul(up, -tall * 0.04)), _mul(ahead, r * 0.78))
        tail = [hang, _add(hang, _mul(up, -tall * 0.28 * drop)), _add(hang, _mul(up, -tall * 0.55 * drop))]
        out.append(piece("scarf_tail", "knit",
                         sweep(tail, [r * 0.52, r * 0.46, r * 0.40], hint=ahead,
                               squash=[0.30, 0.30, 0.30]), lid=True))
    return out


# --- the one door the build and the live view both come through ----------------------------------------

def cut(what, joints, want=None):
    """Every piece of one generated wearable, measured on this body.

    `what` is a name from WEARABLES, `joints` MakeHuman's joint markers in whatever space the caller works
    in, and `want` the design's options for it. An empty list means this body has not got the joints to
    measure it on - never an error: a build must not fall over because a sock could not be cut."""
    w = want or {}
    sides = SIDES.get(w.get("side", "both"), ("l", "r"))
    girth = float(w.get("girth", 1.0) or 1.0)
    if what == "socks":
        return [p for s in ("l", "r")
                for p in sock(joints, s, w.get("height", "crew"), girth,
                              over_foot=bool(w.get("over_foot", True)))]
    if what == "shoes_made":
        return [p for s in ("l", "r") for p in shoe(joints, s, w.get("style", "shoe"), girth)]
    if what == "watch":
        return [p for s in sides for p in watch(joints, s, girth, float(w.get("face", 1.0) or 1.0))]
    if what == "wristband":
        return [p for s in sides
                for p in wristband(joints, s, float(w.get("width", 1.0) or 1.0), girth)]
    if what == "tie":
        return tie(joints, float(w.get("length", 1.0) or 1.0), float(w.get("width", 1.0) or 1.0))
    if what == "scarf":
        return scarf(joints, float(w.get("drop", 1.0) or 1.0), girth)
    return []


def asked_for(design):
    """[(what, want)] - the generated wearables a design calls for, in the order they go on.

    A colour is what asks for one: an empty `costume.watch` means no watch, exactly as an empty
    `costume.belt` means no belt. Shoes are the exception, because everybody wears shoes: they are asked
    for by style, and the colour only says what colour."""
    d = design or {}
    costume = d.get("costume") or {}
    outfit = d.get("outfit") or {}
    out = []
    if costume.get("socks"):
        out.append(("socks", {"colour": costume["socks"], "height": costume.get("sock_height", "crew"),
                              "over_foot": outfit.get("shoe_style", "none") in ("none", "sandal")}))
    if outfit.get("shoe_style") in SHOE_STYLES and outfit.get("shoe_style") not in ("none", None):
        out.append(("shoes_made", {"colour": outfit.get("shoes") or "#2b2118",
                                   "style": outfit["shoe_style"]}))
    if costume.get("tie"):
        out.append(("tie", {"colour": costume["tie"], "length": costume.get("tie_length", 1.0)}))
    if costume.get("scarf"):
        out.append(("scarf", {"colour": costume["scarf"]}))
    if costume.get("wristband"):
        out.append(("wristband", {"colour": costume["wristband"],
                                  "side": costume.get("wristband_side", "both"),
                                  "width": costume.get("wristband_width", 1.0)}))
    if costume.get("watch"):
        out.append(("watch", {"colour": costume["watch"], "side": costume.get("watch_side", "left")}))
    return out
