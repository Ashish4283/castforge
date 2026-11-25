import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "blender"))
import costume as kit  # noqa: E402

from core import schema  # noqa: E402


def tube(rings=4, n=8, radius=0.2, step=0.1, z0=1.0):
    """An open cylinder: `rings` loops of `n` vertices, top at z0 going down."""
    co = [(radius * math.cos(2 * math.pi * i / n), radius * math.sin(2 * math.pi * i / n), z0 - r * step)
          for r in range(rings) for i in range(n)]
    faces = [(r * n + i, r * n + (i + 1) % n, (r + 1) * n + (i + 1) % n, (r + 1) * n + i)
             for r in range(rings - 1) for i in range(n)]
    return co, faces


def test_an_open_tube_has_two_openings_top_and_bottom():
    co, faces = tube()
    loops = kit.boundary_loops(faces)
    assert len(loops) == 2
    ops = kit.openings(co, loops)
    assert kit.centroid(co, ops["hem"])[2] < kit.centroid(co, ops["collar"])[2]
    assert ops["cuffs"] == []


def test_openings_far_from_the_centre_line_are_cuffs():
    co = {0: (0.5, 0, 0.9), 1: (0.55, 0, 0.9), 2: (0.5, 0.05, 0.9), 3: (0, 0, 1.0), 4: (0.1, 0, 1.0), 5: (0, 0.1, 1.0)}
    ops = kit.openings(co, [[0, 1, 2], [3, 4, 5]])
    assert ops["cuffs"] == [[0, 1, 2]] and ops["hem"] == [3, 4, 5] and "collar" not in ops


def test_band_measures_along_the_surface():
    co, faces = tube(rings=5, step=0.1)
    bottom = [v for v in range(len(co)) if co[v][2] < 0.65]
    near = kit.band(co, kit.edges_of(faces), bottom, 0.15)
    zs = sorted({round(co[v][2], 2) for v in near})
    assert zs == [0.6, 0.7]      # the bottom ring and the one 0.1 m above; 0.2 m is too far


def test_coat_rings_continue_the_hem_down_and_flare():
    hem = [(0.2, 0.0, 1.0), (0.0, 0.2, 1.0), (-0.2, 0.0, 1.0), (0.0, -0.2, 1.0)]
    rings = kit.hem_rings(hem, (0.0, 0.0), 0.2, 2, 0.1)
    assert [round(r[0][2], 3) for r in rings] == [0.9, 0.8]
    assert math.isclose(rings[-1][0][0], 0.22)
    faces = kit.ring_faces([0, 1, 2, 3], [[4, 5, 6, 7], [8, 9, 10, 11]])
    assert len(faces) == 8 and faces[0] == (0, 1, 5, 4)


def test_weights_blend_keep_the_strongest_and_sum_to_one():
    w = kit.mix_weights({"DEF-spine": 1.0}, {"DEF-thigh.L": 0.8, "DEF-shin.L": 0.2}, 0.5)
    assert math.isclose(sum(w.values()), 1.0)
    assert w["DEF-spine"] > w["DEF-thigh.L"] > w["DEF-shin.L"]
    assert len(kit.mix_weights({str(i): 1.0 for i in range(9)}, {}, 0.0)) == 4


def test_push_clear_only_moves_points_too_close():
    assert kit.push_clear((0, 0, 0.05), (0, 0, 0), (0, 0, 1), 0.03) == (0, 0, 0.05)
    assert kit.push_clear((0, 0, -0.01), (0, 0, 0), (0, 0, 1), 0.03) == (0, 0, 0.03)


def test_front_strip_and_faces_inside():
    co = {0: (0.0, -0.2, 1.0), 1: (0.0, 0.2, 1.0), 2: (0.3, -0.2, 1.0), 3: (0.01, -0.2, 0.5)}
    assert kit.front_strip(co, co, (0.0, 0.0), 0.05, (0.8, 1.2)) == {0}
    assert kit.faces_inside([(0, 1), (0, 3)], {0, 3}) == [1]


def test_the_santa_costume_is_a_valid_design():
    design = {"gender": "male", "age": 70, "height_cm": 176}
    for key, value in schema.COSTUMES["santa"].items():
        assert key in schema.CHARACTER
        node = design
        *path, last = key.split(".")
        for part in path:
            node = node.setdefault(part, {})
        node[last] = value
    assert schema.check_design(design) == []
    assert schema.design_get(design, "costume.trim") == "#f3efe8"


def test_design_problems_are_plain_language():
    problems = schema.check_design({"gender": "male", "age": "old", "hat": "crown", "costume": {"belt": "black"}})
    assert "the design needs 'height_cm'" in problems
    assert any("age" in p and "number" in p for p in problems)
    assert any("hat" in p and "santa" in p for p in problems)
    assert any("costume.belt" in p and "colour" in p for p in problems)


def test_the_back_arc_of_a_collar_is_where_a_cape_hangs():
    # a ring of 8 points around the neck; the body faces -y, so the back is +y
    co = {i: (math.cos(2 * math.pi * i / 8) * 0.1, math.sin(2 * math.pi * i / 8) * 0.1, 1.4) for i in range(8)}
    arc = kit.back_arc(co, list(range(8)), (0.0, 0.0), face=-1.0)
    assert arc and all(co[v][1] > 0 for v in arc)           # the face points -y, so a cape hangs off +y
    assert arc == [2, 3, 4] or arc == [1, 2, 3]             # the middle of the back run, not its edges
    assert kit.back_arc(co, [0], (0.0, 0.0), face=-1.0) == []


def test_cape_rings_fall_flare_and_drift_backwards():
    top = [(-0.2, 0.08, 1.4), (0.0, 0.1, 1.4), (0.2, 0.08, 1.4)]
    rings = kit.cape_rings(top, (0.0, 0.0), length=0.8, rings=4, flare=0.5, sway=0.1)
    assert len(rings) == 4 and len(rings[0]) == 3
    assert [round(r[1][2], 3) for r in rings] == [1.2, 1.0, 0.8, 0.6]        # falls evenly
    assert abs(rings[-1][0][0]) > abs(top[0][0])                             # spreads out at the hem
    assert rings[-1][1][1] > rings[0][1][1]                                  # drifts away from the body
    faces = kit.ring_faces([0, 1, 2], [[3, 4, 5]], closed=False)
    assert len(faces) == 2                                                   # an open strip, not a tube


def test_a_hood_covers_the_head_but_leaves_the_face_open():
    co = {"back": (0.0, 0.12, 1.6), "top": (0.0, 0.0, 1.7), "face": (0.0, -0.1, 1.6),
          "side": (0.11, -0.08, 1.6), "chest": (0.0, 0.0, 1.2)}
    covered = kit.hood_cut(co, list(co), (0.0, 0.0), face=-1.0, chin_z=1.45)
    assert "back" in covered and "top" in covered
    assert "face" not in covered                      # the opening
    assert "side" in covered                          # wide of the face: still covered
    assert "chest" not in covered                     # below the chin


def test_the_shoulder_line_runs_across_the_back_at_shoulder_height():
    # a slab of points: front and back, at shoulder height and below
    co = {}
    n = 0
    for x in (-0.2, -0.1, 0.0, 0.1, 0.2):
        for y in (-0.12, 0.12):
            for z in (1.45, 1.20):
                co[n] = (x, y, z)
                n += 1
    line = kit.shoulder_line(co, list(co), (0.0, 0.0), face=-1.0, z=1.45, band=0.06, count=5)
    assert len(line) == 5
    assert all(p[1] > 0 for p in line)                     # the back, not the chest
    assert all(abs(p[2] - 1.45) < 0.07 for p in line)      # shoulder height, not the waist
    assert [round(p[0], 2) for p in line] == [-0.2, -0.1, 0.0, 0.1, 0.2]   # left to right across the body
    assert kit.shoulder_line(co, list(co), (0.0, 0.0), face=-1.0, z=0.3) == []


def test_a_plate_keeps_a_solid_edge_instead_of_a_torn_one():
    faces = [(0, 1, 2, 3), (1, 4, 5, 2), (4, 6, 7, 5)]
    verts = {0, 1, 2, 3, 4, 5}                       # the third face has only half its corners
    assert kit.faces_inside(faces, verts) == [0, 1]
    assert kit.faces_mostly(faces, verts) == [0, 1, 2]
    assert kit.faces_mostly(faces, {0, 1}) == [0]          # two of four corners is enough, one is not
    assert kit.faces_mostly(faces, {6}) == []
    assert kit.faces_mostly(faces, set()) == []


def test_a_hood_is_a_shell_that_rises_from_the_collar_and_shuts_over_the_crown():
    rings = kit.hood_rings((0.0, 0.0), base_z=1.45, top_z=1.78, radius=0.1, rings=6, span=15)
    assert len(rings) == 6 and all(len(r) == 15 for r in rings)
    zs = [r[0][2] for r in rings]              # the front lip: no drape there
    assert zs == sorted(zs) and abs(zs[-1] - 1.78) < 1e-6            # climbs evenly to the crown
    steps = [b - a for a, b in zip(zs, zs[1:])]
    assert max(steps) - min(steps) < 0.015                           # evenly: no flat lid of stacked rings
    wide = [max(abs(p[0]) for p in r) for r in rings]                # half-width, free of the backward lean
    assert wide[0] > wide[-2] > wide[-1]                             # wide at the shoulders, narrow at the crown
    # the opening: wide across the face, shut by the time the shell reaches the crown
    gap = [math.dist(r[0], r[-1]) for r in rings]
    assert gap[0] > 0.1 and gap[-1] < 0.01 and gap == sorted(gap, reverse=True)
    assert rings[-1][0][1] > rings[0][0][1]                          # and the shell leans back as it rises
    mid = len(rings[0]) // 2                                         # the back of the bottom ring...
    assert rings[0][mid][2] < rings[0][0][2] - 0.03                  # ...drapes onto the shoulders
    assert rings[0][0][2] > 1.45 and rings[0][-1][2] > 1.45          # while both lips curve up, not down
    assert abs(rings[-1][mid][2] - rings[-1][0][2]) < 0.005          # the crown ring stays level


def test_a_hood_shell_joins_into_an_open_fronted_strip():
    rings = kit.hood_rings((0.0, 0.0), 1.45, 1.78, 0.1, rings=3, span=5)
    faces = kit.ring_faces([0, 1, 2, 3, 4], [[5, 6, 7, 8, 9], [10, 11, 12, 13, 14]], closed=False)
    assert len(faces) == 8                                           # 4 quads per row, no face across the front
    assert len(rings) == 3


def test_trim_bands_names_the_hem_and_collar_and_leaves_short_sleeves_alone():
    co, faces = tube(rings=6, step=0.05)                       # a sleeveless top: hem at 0.75, collar at 1.0
    bands = kit.trim_bands(co, faces)
    assert set(bands) == {"hem", "collar"}
    assert min(co[v][2] for v in bands["hem"]) == 0.75
    assert max(co[v][2] for v in bands["collar"]) == 1.0
    assert not bands["hem"] & bands["collar"]                   # 0.25 m apart: the bands cannot meet


def test_trim_bands_adds_the_cuffs_only_when_the_sleeves_are_long():
    co, faces = tube(rings=3, step=0.05)
    cuff = [(1.0 + 0.05 * i, 0.0, 0.9) for i in range(3)]       # a loose loop far out along the arm
    co = list(co) + cuff
    first = len(co) - 3
    faces = list(faces) + [(first, first + 1, first + 2)]
    assert "cuff" not in kit.trim_bands(co, faces, sleeves="short")
    assert kit.trim_bands(co, faces, sleeves="long")["cuff"] == {first, first + 1, first + 2}


def test_boot_bands_take_the_highest_opening_on_each_side():
    co, faces = tube(rings=4, step=0.05, z0=0.2)               # one "shoe", opening at the top
    bands = kit.boot_bands(co, faces)
    assert max(co[v][2] for v in bands["boot"]) == 0.2
    assert min(co[v][2] for v in bands["boot"]) >= 0.2 - kit.TRIM_WIDTHS["boot"]


def hat_with_a_bobble():
    """A cap: a tube for the head, and a little bobble hanging below it with a hole of its own.

    This is the shape that caught me out - the bobble's hole is the LOWEST boundary in the mesh, and
    anchoring the hat to it balloons the whole thing round the pompom."""
    co, faces = tube(rings=4, n=8, radius=0.1, step=0.05, z0=1.8)    # opening at 1.65, crown at 1.8
    first = len(co)
    bob = [(0.004 * math.cos(2 * math.pi * i / 6), 0.12 + 0.004 * math.sin(2 * math.pi * i / 6), 1.60)
           for i in range(6)]                                        # a 4 mm ring, hanging off the back
    bob += [(p[0], p[1], p[2] + 0.02) for p in bob]
    co = list(co) + bob
    faces = list(faces) + [(first + i, first + (i + 1) % 6, first + 6 + (i + 1) % 6, first + 6 + i)
                           for i in range(6)]
    return co, faces


def test_the_opening_is_the_ring_that_lies_on_the_head_not_the_lowest_or_the_widest():
    co, faces = hat_with_a_bobble()
    rim = kit.rim_of(co, faces, head_at(1.66))                       # a skull at the opening's height
    assert len(rim) == 8 and kit.centroid(co, rim)[2] == pytest.approx(1.65)
    assert min(co[v][2] for v in rim) > 1.59                          # not the bobble, which hangs lower


def head_at(z, radius=0.1, n=12):
    return [(radius * math.cos(2 * math.pi * i / n), radius * math.sin(2 * math.pi * i / n), z) for i in range(n)]


def test_a_bigger_hat_keeps_its_opening_exactly_where_it_was():
    co, faces = tube(rings=4, n=8, radius=0.1, step=0.05, z0=1.8)    # opening at 1.65, crown at 1.8
    rim = kit.rim_of(co, faces, head_at(1.66))
    assert kit.centroid(co, rim)[2] == pytest.approx(1.65)           # the one lying against the head
    big = kit.grow_hat(co, 1.5, rim)
    for v in rim:
        assert big[v] == pytest.approx(co[v], abs=1e-9)              # what grips the head does not move
    top = max(range(len(co)), key=lambda v: co[v][2])
    assert big[top][2] > co[top][2]                                  # and the crown is taller
    assert abs(big[top][0] - kit.centroid(co, rim)[0]) > abs(co[top][0] - kit.centroid(co, rim)[0])


def test_nothing_below_the_opening_moves():
    """The fur roll of a Santa cap hangs BELOW the ring the head goes through. If it grows, it flares."""
    co, faces = tube(rings=4, n=8, radius=0.1, step=0.05, z0=1.8)
    skirt = [(0.13 * math.cos(2 * math.pi * i / 8), 0.13 * math.sin(2 * math.pi * i / 8), 1.60)
             for i in range(8)]                                  # a roll hanging 5 cm below the opening
    first = len(co)
    co = list(co) + skirt
    hem = [24 + i for i in range(8)]                             # the tube's own bottom ring, at 1.65
    faces = list(faces) + [(hem[i], hem[(i + 1) % 8], first + (i + 1) % 8, first + i) for i in range(8)]
    rim = kit.rim_of(co, faces, head_at(1.66))
    big = kit.grow_hat(co, 1.5, rim)
    for v in range(first, len(co)):
        assert big[v] == pytest.approx(co[v], abs=1e-9)          # the roll is left exactly alone
    top = max(range(len(co)), key=lambda v: co[v][2])
    assert big[top][2] > co[top][2] + 0.05                       # while the crown grows


def test_a_tilted_hat_is_not_stretched_off_the_forehead():
    """A hat worn at an angle: growing it must leave the whole opening alone, high side included."""
    co, faces = tube(rings=3, n=8, radius=0.1, step=0.05, z0=1.8)
    co = [(x, y, z + 0.04 * y) for x, y, z in co]                    # tip it back
    rim = kit.rim_of(co, faces, head_at(1.72))
    big = kit.grow_hat(co, 1.4, rim)
    for v in rim:
        assert big[v] == pytest.approx(co[v], abs=1e-9)


def test_a_hat_left_at_its_own_size_is_untouched():
    co, faces = tube(rings=3, radius=0.1, step=0.05, z0=1.8)
    assert kit.grow_hat(co, 1.0, kit.rim_of(co, faces, head_at(1.71))) == [tuple(p) for p in co]


def test_a_part_is_measured_along_the_surface_not_through_the_air():
    """Two sleeves passing close to each other: clicking one must not select the other."""
    left, lf = tube(rings=3, n=8, radius=0.04, step=0.05, z0=1.2)
    right = [(x + 0.085, y, z) for x, y, z in left]              # 0.5 cm apart, never joined
    co = list(left) + right
    faces = list(lf) + [tuple(v + len(left) for v in f) for f in lf]
    part = kit.part_at(co, faces, co[0], 0.30)                   # a generous radius, from the left sleeve
    assert part and all(v < len(left) for v in part)             # nothing from the right one


def test_a_resized_part_stays_joined_where_it_meets_the_rest():
    co, faces = tube(rings=6, n=8, radius=0.1, step=0.05, z0=1.8)
    adj = kit.neighbours(faces)
    part = kit.band(co, kit.edges_of(faces), [v for v in range(len(co)) if co[v][2] == 1.8], 0.07)
    edge = kit.border_of(part, adj)
    big = kit.grow_part(co, part, 1.6, adj=adj)
    for v in range(len(co)):
        if v not in part:
            assert big[v] == pytest.approx(co[v], abs=1e-9)      # the rest of the mesh is untouched
    for v in edge:
        assert big[v] == pytest.approx(co[v], abs=1e-9)          # and the seam does not open
    deep = [v for v in part if co[v][2] == 1.8]                  # the far end of the part
    c = kit.centroid(co, edge)
    assert abs(big[deep[0]][0] - c[0]) > abs(co[deep[0]][0] - c[0]) * 1.4


def test_shrinking_a_part_is_the_same_rule_backwards():
    co, faces = tube(rings=6, n=8, radius=0.1, step=0.05, z0=1.8)
    adj = kit.neighbours(faces)
    part = kit.band(co, kit.edges_of(faces), [v for v in range(len(co)) if co[v][2] == 1.8], 0.07)
    small = kit.grow_part(co, part, 0.6, adj=adj)
    c = kit.centroid(co, kit.border_of(part, adj))
    deep = [v for v in part if co[v][2] == 1.8][0]
    assert abs(small[deep][0] - c[0]) < abs(co[deep][0] - c[0])


def a_cap():
    """A little cap: a tube closed over at the top, so its ONE opening is the ring that sits on the head.

    Closing it matters. An open tube has two boundary rings, and a part bounded at both ends is pinned at
    both ends - nothing in the middle can be slid or turned anywhere."""
    co, faces = tube(rings=5, n=8, radius=0.1, step=0.04, z0=1.8)
    co = list(co) + [(0.0, 0.0, 1.84)]               # a point over the crown
    tip = len(co) - 1
    faces = list(faces) + [(i, (i + 1) % 8, tip) for i in range(8)]
    adj = kit.neighbours(faces)
    part = set(range(len(co)))                       # the whole cap; its border is the opening
    return co, faces, adj, part


def test_a_part_can_be_slid_without_leaving_the_seam_behind():
    co, faces, adj, part = a_cap()
    moved = kit.shape_part(co, part, move=(0.05, 0, 0), faces=faces, adj=adj)
    opening = {v for loop in kit.boundary_loops(faces) for v in loop}
    for v in opening:
        assert moved[v] == pytest.approx(co[v], abs=1e-9)        # the opening stays on the head
    top = max(range(len(co)), key=lambda v: co[v][2])
    assert moved[top][0] - co[top][0] == pytest.approx(0.05, abs=1e-9)   # the crown slides the full way


def test_a_part_can_be_turned_about_where_it_joins_on():
    co, faces, adj, part = a_cap()
    turned = kit.shape_part(co, part, turn=(0, 40, 0), faces=faces, adj=adj)   # lean it sideways
    opening = {v for loop in kit.boundary_loops(faces) for v in loop}
    for v in opening:
        assert turned[v] == pytest.approx(co[v], abs=1e-9)
    top = max(range(len(co)), key=lambda v: co[v][2])
    assert abs(turned[top][0] - co[top][0]) > 0.05               # the point has swung over
    assert turned[top][2] < co[top][2]                           # and come down as it leaned


def test_asking_for_nothing_changes_nothing():
    co, faces, adj, part = a_cap()
    assert kit.shape_part(co, part, faces=faces, adj=adj) == [tuple(p) for p in co]


def ring_width(ring):
    """How wide a ring is about its own middle - not about the head, which it moves away from."""
    middle = [sum(p[i] for p in ring) / len(ring) for i in range(3)]
    return max(math.dist(p, middle) for p in ring)


def test_a_made_cap_starts_as_a_roll_round_the_head_it_is_going_on():
    rings, fur, tip = kit.santa_cap((0.0, 0.0), 1.60, 0.095, droop=0.0)
    opening = rings[0]
    assert all(abs(p[2] - 1.60) < 1e-9 for p in opening)             # the roll's bottom sits on the head
    assert 0.095 < ring_width(opening) < 0.095 * 1.25                # a little proud of it, as fur is
    assert tip[2] > 1.60 and abs(tip[0]) < 1e-9                      # straight up when it does not flop


def test_the_roll_keeps_its_width_and_the_cone_tapers_from_where_it_ends():
    rings, fur, _tip = kit.santa_cap((0.0, 0.0), 1.60, 0.1, droop=0.0, band=0.3)
    assert 1 < fur < len(rings)
    roll = [ring_width(r) for r in rings[:fur]]
    assert max(roll) - min(roll) < 0.01                              # the roll is a roll, not a dome
    assert ring_width(rings[fur]) < min(roll)                        # the cone starts just inside it...
    assert ring_width(rings[fur]) > min(roll) * 0.8                  # ...with no step between them
    assert ring_width(rings[-1]) < ring_width(rings[0]) / 5          # and comes to a point


def test_a_cap_flops_the_way_it_is_pointed():
    _r, _f, left = kit.santa_cap((0.0, 0.0), 1.6, 0.1, droop=0.8, towards=0)
    _r, _f, back = kit.santa_cap((0.0, 0.0), 1.6, 0.1, droop=0.8, towards=90)
    _r, _f, up = kit.santa_cap((0.0, 0.0), 1.6, 0.1, droop=0.0)
    assert left[0] > 0.1 and abs(left[1]) < 1e-9
    assert back[1] > 0.1 and abs(back[0]) < 1e-9
    assert up[2] > left[2]                                           # flopping costs it height


def test_more_fur_means_more_of_the_cap_is_fur():
    _r, thin, _t = kit.santa_cap((0, 0), 1.6, 0.1, band=0.15)
    _r, deep, _t = kit.santa_cap((0, 0), 1.6, 0.1, band=0.45)
    assert deep > thin


def test_a_bobble_is_a_ball_around_its_middle():
    rows = kit.ball((0.0, 0.0, 2.0), 0.05, rows=6, span=8)
    every = [p for row in rows for p in row]
    assert all(math.dist(p, (0, 0, 2.0)) <= 0.05 + 1e-9 for p in every)
    assert max(p[2] for p in every) > 2.0 and min(p[2] for p in every) < 2.0
