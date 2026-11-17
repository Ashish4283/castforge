import math
import sys
from pathlib import Path

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
