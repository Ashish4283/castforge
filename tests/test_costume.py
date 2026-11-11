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
