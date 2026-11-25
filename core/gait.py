"""How a body's own size and build change the way it walks (pure, tested; no bpy).

`acting.PACES` gives one speed and one step length for everybody: 1.1 m/s and 0.62 m. That is a tuned,
good-looking walk for a grown person of about 1.70 m, and it is wrong for anybody else. An elf a metre
tall takes a step LONGER THAN ITS OWN LEG, which no leg can do: the foot has to be dragged or the
character skates. A toddler walks like a scale model of a man. A heavy man walks like a slim one.

None of that has to be animated by hand. Walking is a pendulum problem and the answers come out of the
body's own measurements:

  How fast.     Two bodies of different size walk the same way when their Froude numbers match -
                Fr = v^2 / (g x L), L being the leg. Matching Fr means v is proportional to the SQUARE
                ROOT of leg length. Half the leg, 0.71 of the speed, not half.
  How long a step. A step is a fraction of the leg that swings it, so it scales straight with leg length.
                Half the leg, half the step.
  How often.    Cadence is speed over step: sqrt(L)/L = 1/sqrt(L). Half the leg, 1.41x the step rate.
                This is why small things scurry and big things plod, and it is not a stylistic choice.
  How wide.     The feet go down either side of the hips, so the stance is half the hip width - which is
                the one measurement that separates a heavy body from a slim one at the same height.

And what WEIGHT does, which is not a size change at all. A heavy body has to move its middle further over
the stance foot to stay balanced, so: a wider stance, a shorter step (the thigh meets the belly sooner),
more side-to-side sway, less arm swing (the arms are pushed out and are heavier), and more of the cycle
with both feet down, because that is the stable part of it.

And what being a CHILD does, which is not a weight change either. A toddler's head is a quarter of its
length where an adult's is a seventh, so its middle is much higher up: wide stance, short steps for its
legs, high cadence, a lot of sway, and the arms carried high. Measured as the share of the body above the
neck, which tells a child from a small adult - an elf is a small adult and walks like one.

Everything here is a ratio against a reference body, and the reference is the one the studio's existing
numbers were tuned on. So an ordinary 1.70 m character walks exactly as it did before; only bodies that
are NOT that get anything different.
"""
import math

G = 9.81
# The body `acting.PACES` was tuned against: an ordinary adult of about 1.70 m. Measured on this project's
# own preview kits, where leg length is a steady 0.52 of height on every build.
LEG_REF = 0.88            # metres, hip to floor
# hip width per metre of leg, on an average adult build. Measured on nine characters this project has
# built: 0.211 on the slimmest, 0.255 on the heaviest, and this in the middle. Set it at the slim end and
# every character in the film comes out "heavy", which is what happened.
HIPS_REF = 0.228
HEAD_ADULT = 0.155        # share of the body above the neck on a grown person
HEAD_BABY = 0.250         # ...and on a toddler, whose head is a quarter of it
LEG_SHARE = 0.52          # leg as a share of height, when there is nothing better to go on

# How far each thing bends as a body gets heavier (per 1.0 of `bulk` above average). Negative shortens.
BULK = {"step": -0.80, "speed": -0.60, "swing": -1.20, "sway": 2.00, "gap": 0.60, "double": 0.90}
# ...and as it gets more childish (per 1.0 of `childish`, 0 a grown person, 1 a toddler).
CHILD = {"step": -0.30, "speed": -0.15, "swing": -0.25, "sway": 1.40, "gap": 0.55, "double": 0.50,
         "guard": 1.00}


def clamp(x, low=0.0, high=1.0):
    return low if x < low else high if x > high else x


def shape_of(joints, height=None):
    """What a body is, from its own joint markers: {tall, leg, hips, head_share, bulk, childish}.

    `joints` is `preview_mesh.joint_centres` in any space with the body standing up - the same markers
    the tailor measures against. `height` is the character's height when it is already known; otherwise
    it is taken from the markers. Returns None when the body has not got the markers to measure."""
    want = ("joint-ground", "joint-l-upper-leg", "joint-r-upper-leg", "joint-neck")
    if any(joints.get(k) is None for k in want):
        return None
    # whichever axis the body stands up: the one the ground and the neck differ most along
    ground, neck = joints["joint-ground"], joints["joint-neck"]
    up = max(range(3), key=lambda i: abs(neck[i] - ground[i]))
    across = max((i for i in range(3) if i != up),
                 key=lambda i: abs(joints["joint-l-upper-leg"][i] - joints["joint-r-upper-leg"][i]))
    hip_l, hip_r = joints["joint-l-upper-leg"], joints["joint-r-upper-leg"]
    leg = abs((hip_l[up] + hip_r[up]) / 2 - ground[up])
    hips = abs(hip_l[across] - hip_r[across])
    if leg < 1e-3 or hips < 1e-4:
        return None
    crown = joints.get("joint-head-2") or joints.get("joint-head")
    tall = float(height) if height else (abs(crown[up] - ground[up]) if crown else leg / LEG_SHARE)
    if tall < 1e-3:
        tall = leg / LEG_SHARE
    # A child is not a small adult, and the head is what says so: a quarter of a toddler is above the
    # neck, a seventh of a grown person is. An elf is a small adult and must come out as one.
    head_share = abs(crown[up] - neck[up]) / tall if crown else HEAD_ADULT
    childish = clamp((head_share - HEAD_ADULT) / (HEAD_BABY - HEAD_ADULT))
    # Weight, as the hips measure it: hip width RELATIVE to leg length, so a tall slim body and a short
    # slim body both come out slim. 1.0 is an average build.
    bulk = (hips / leg) / HIPS_REF
    return {"tall": tall, "leg": leg, "hips": hips, "head_share": head_share,
            "childish": childish, "bulk": bulk}


def bend(table, amount, keys=None):
    """{key: multiplier} - how much each thing changes for `amount` of whatever the table describes."""
    return {k: 1.0 + v * amount for k, v in table.items() if keys is None or k in keys}


def walk_like(shape, pace=(1.1, 0.62, 1.0, 0.0)):
    """How THIS body walks at that pace: speed, step, cadence, stance, swing, lean, sway, bob, double.

    `pace` is a row of `acting.PACES` - (speed m/s, step m, arm swing, extra lean) - which is the walk as
    tuned on the reference body. Everything here is that row scaled by what this body actually is, so a
    body of reference size and average build comes back with the row unchanged.

        speed    metres a second
        step     metres from one footfall to the next on the same side's opposite foot
        cadence  steps a second (speed / step), which is what makes small bodies look busy
        gap      how far each foot goes from the centre line
        swing    arm swing, as a multiple of the pace's own
        lean     radians of extra forward lean
        sway     side-to-side movement of the hips, as a multiple of the ordinary
        bob      up and down, as a multiple of the ordinary
        double   the share of the cycle with both feet on the ground (0.2 running, 0.35 plodding)
        guard    how high the arms are carried (0 by the sides, 1 a toddler's high guard)
    """
    speed, step, swing, lean = pace
    if not shape:
        return {"speed": speed, "step": step, "cadence": speed / step if step else 0.0,
                "gap": 0.10, "swing": swing, "lean": lean, "sway": 1.0, "bob": 1.0,
                "double": 0.28, "guard": 0.0, "why": "no measurements: the walk as it comes"}
    leg, bulk, kid = shape["leg"], shape["bulk"], shape["childish"]
    size = leg / LEG_REF
    heavy = bulk - 1.0
    b, c = bend(BULK, heavy), bend(CHILD, kid)

    # dynamic similarity: speed with the square root of the leg, step straight with it
    out_speed = speed * math.sqrt(size) * max(0.25, b["speed"]) * max(0.4, c["speed"])
    out_step = step * size * max(0.25, b["step"]) * max(0.3, c["step"])
    out_gap = (shape["hips"] / 2.0) * b["gap"] * c["gap"]
    return {
        "speed": out_speed,
        "step": out_step,
        "cadence": out_speed / out_step if out_step > 1e-6 else 0.0,
        "gap": out_gap,
        "swing": swing * max(0.1, b["swing"]) * max(0.2, c["swing"]),
        "lean": lean + 0.03 * max(0.0, heavy),      # a heavy body carries its weight forward a little
        "sway": max(0.4, b["sway"]) * max(0.5, c["sway"]),
        "bob": max(0.4, 1.0 - 0.5 * heavy) * size ** 0.5,
        "double": clamp(0.28 * b["double"] * c["double"], 0.18, 0.46),
        "guard": clamp(c["guard"] - 1.0),
        "why": describe(shape),
    }


def describe(shape):
    """One line for a person: what about this body changes the way it walks."""
    if not shape:
        return "no measurements"
    bits = []
    size = shape["leg"] / LEG_REF
    if size < 0.92:
        bits.append(f"legs {size * 100:.0f}% of an adult's, so shorter steps and {1 / math.sqrt(size):.2f}x"
                    f" the step rate")
    elif size > 1.08:
        bits.append(f"legs {size * 100:.0f}% of an adult's, so longer, slower steps")
    if shape["bulk"] > 1.10:
        bits.append("heavy: a wider stance, a shorter step and more roll")
    elif shape["bulk"] < 0.94:
        bits.append("slim: a narrow stance and a free arm swing")
    if shape["childish"] > 0.3:
        bits.append(f"child's proportions (head {shape['head_share'] * 100:.0f}% of the body): wide, "
                    f"busy steps and the arms carried high")
    return "; ".join(bits) or "an ordinary adult build: the walk as it was tuned"
