import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from core import fabric  # noqa: E402


def woven(n=256, threads=16, seed=3):
    """A square of cloth that DOES tile: a weave whose period divides the picture exactly."""
    y, x = np.mgrid[0:n, 0:n]
    warp = np.sin(2 * math.pi * threads * x / n)
    weft = np.sin(2 * math.pi * threads * y / n)
    rng = np.random.default_rng(seed)
    a = 0.5 + 0.18 * warp * weft + 0.12 * warp + 0.04 * rng.standard_normal((n, n))
    a = np.clip(a, 0, 1)
    return np.stack([a * 0.45, a * 0.52, a * 0.78], axis=-1).astype(np.float32)


def seamed(n=256):
    """...and one that does NOT: a gradient, so the last column is nothing like the first."""
    y, x = np.mgrid[0:n, 0:n]
    a = (x / (n - 1)) * 0.8 + 0.1 + 0.02 * np.sin(2 * math.pi * 12 * y / n)
    return np.stack([a, a * 0.9, a * 0.8], axis=-1).astype(np.float32)


def flat(n=256, value=0.4):
    return np.full((n, n, 3), value, dtype=np.float32)


# --- does it tile? ---------------------------------------------------------------------------------------

def test_a_weave_that_wraps_measures_as_seamless():
    s = fabric.seam(woven())
    assert s["worst"] < 1.3, s
    assert fabric.tiles(woven())


def test_a_picture_with_a_seam_in_it_is_caught_and_the_number_says_how_bad():
    s = fabric.seam(seamed())
    assert s["across"] > 3.0, s
    assert s["across"] > s["down"], "the seam is across, and it should say so"
    assert not fabric.tiles(seamed())


def test_the_seam_measure_does_not_depend_on_how_busy_the_cloth_is():
    """A ratio against the picture's OWN grain, so a fine weave and a coarse one both read as seamless."""
    for threads in (8, 16, 48):
        assert fabric.seam(woven(threads=threads))["worst"] < 1.4, threads


def test_a_flat_colour_tiles_perfectly_and_is_still_not_cloth():
    assert fabric.tiles(flat())
    assert any("no weave" in p for p in fabric.check(flat(), "cotton"))


# --- the maps derived from it ----------------------------------------------------------------------------

def test_height_comes_out_of_the_light_and_dark_and_uses_the_whole_range():
    h = fabric.height(woven())
    assert h.shape == (256, 256)
    assert abs(h.min()) < 1e-5 and abs(h.max() - 1.0) < 1e-5


def test_a_flat_picture_has_no_relief_rather_than_a_divide_by_zero():
    h = fabric.height(flat())
    assert np.all(h == 0.0)


def test_a_normal_map_is_unit_length_everywhere_and_points_outwards():
    n = fabric.normals(fabric.height(woven()), 1.0)
    v = n * 2.0 - 1.0
    assert np.allclose(np.linalg.norm(v, axis=-1), 1.0, atol=1e-4)
    assert np.all(v[..., 2] > 0), "a surface normal never points into the cloth"


def test_a_flat_surface_gives_the_straight_up_normal():
    n = fabric.normals(np.zeros((32, 32), dtype=np.float32))
    assert np.allclose(n[..., 0], 0.5) and np.allclose(n[..., 1], 0.5)
    assert np.allclose(n[..., 2], 1.0)


def test_the_normal_map_wraps_so_a_tiling_picture_does_not_grow_a_seam_in_its_lighting():
    """Clamp at the edges instead of rolling and the LIGHTING seams even though the colour does not."""
    n = fabric.normals(fabric.height(woven()), 1.0)
    edge = float(np.mean(np.abs(n[:, 0] - n[:, -1])))
    inside = float(np.mean(np.abs(n[:, 1] - n[:, 2])))
    assert edge < inside * 3.0 + 0.02, (edge, inside)


def test_more_relief_tilts_the_surface_further():
    h = fabric.height(woven())
    gentle = fabric.normals(h, 0.2)[..., 2].mean()
    strong = fabric.normals(h, 1.5)[..., 2].mean()
    assert strong < gentle, "a stronger bump should tilt the normals away from straight up"


def test_roughness_sits_around_the_kind_and_varies_with_the_weave():
    for kind in ("silk", "cotton", "wool"):
        r = fabric.roughness(fabric.height(woven()), kind)
        assert abs(float(r.mean()) - fabric.LOOK[kind]["rough"]) < 0.06, kind
        assert float(r.std()) > 0.01, "roughness should follow the threads"
    assert fabric.roughness(fabric.height(woven()), "silk").mean() < \
        fabric.roughness(fabric.height(woven()), "wool").mean()


def test_roughness_never_leaves_the_legal_range():
    r = fabric.roughness(fabric.height(woven()), "silk", spread=5.0)
    assert float(r.min()) >= 0.02 - 1e-6 and float(r.max()) <= 1.0 + 1e-6


# --- the one call ----------------------------------------------------------------------------------------

def test_one_call_gives_everything_a_material_needs():
    got = fabric.maps_for(woven(), "denim")
    assert set(got) == {"height", "normal", "roughness", "look", "seam"}
    assert got["normal"].shape == (256, 256, 3)
    assert got["roughness"].shape == (256, 256)
    assert got["look"]["rough"] == fabric.LOOK["denim"]["rough"]


def test_every_kind_in_the_table_can_actually_be_made():
    for kind in fabric.KINDS:
        got = fabric.maps_for(woven(), kind)
        assert np.isfinite(got["normal"]).all() and np.isfinite(got["roughness"]).all(), kind


# --- what gets refused -----------------------------------------------------------------------------------

def test_a_swatch_is_checked_before_it_is_believed():
    assert fabric.check(woven(1024), "denim") == []
    assert any("does not tile" in p for p in fabric.check(seamed(1024), "denim"))
    assert any("too small" in p for p in fabric.check(woven(128), "denim"))
    assert any("not one of" in p for p in fabric.check(woven(1024), "chainmail"))
    assert any("square" in p for p in fabric.check(woven(512)[:256], "denim"))


def test_a_greyscale_or_broken_picture_is_refused_rather_than_crashing():
    assert fabric.check(np.zeros((256, 256), dtype=np.float32), "denim")


def test_it_says_in_words_what_the_cloth_is_like():
    said = fabric.describe("knit", fabric.seam(woven()))
    assert "knit" in said and "seam" not in said, said
    assert "seam" in fabric.describe("denim", fabric.seam(seamed()))


def test_a_tile_repeats_at_a_scale_a_person_reads_as_cloth():
    assert abs(fabric.tile_size(1024, 0.35) - 1 / 0.35) < 1e-6
    assert fabric.tile_size(1024, 0.0) > 0, "never a divide by zero"


# --- the rented GPU's own settings -----------------------------------------------------------------------

def test_a_lightning_checkpoint_is_not_run_at_a_full_models_settings():
    """Run a distilled model at 28 steps and CFG 5.5 and it comes out burnt - and six times slower,
    which on a free T4 is fifteen seconds a swatch against a minute and a half."""
    sys.path.insert(0, str(Path(__file__).parent.parent / "generate"))
    import remote_gpu

    quick, slow = ("RealVisXL_V5.0_Lightning_fp16.safetensors", "sd_xl_base_1.0.safetensors")
    assert remote_gpu.settings_for(quick)[0] < remote_gpu.settings_for(slow)[0]
    assert remote_gpu.settings_for(quick)[1] < remote_gpu.settings_for(slow)[1]
    for tag in ("lightning", "Turbo", "LCM", "hyper"):
        assert remote_gpu.settings_for(f"some_{tag}_model.safetensors")[0] <= 8, tag
    assert remote_gpu.settings_for(None)[0] == 28, "an unknown checkpoint gets the careful settings"
    assert remote_gpu.settings_for(quick, steps=12, cfg=3.0)[:2] == (12, 3.0), "the caller may insist"


def test_the_graph_carries_whatever_the_checkpoint_needs():
    sys.path.insert(0, str(Path(__file__).parent.parent / "generate"))
    import remote_gpu

    g = remote_gpu.tiling_graph("worn denim", "RealVisXL_V5.0_Lightning_fp16.safetensors")
    assert g["5"]["inputs"]["steps"] == 6 and g["5"]["inputs"]["sampler_name"] == "dpmpp_sde"
    assert all("class_type" in n and "inputs" in n for n in g.values())
    assert g["6"]["class_type"] == remote_gpu.SEAMLESS, "a swatch must be decoded seamlessly"
    assert remote_gpu.tiling_graph("x", "y", seamless=False)["6"]["class_type"] == "VAEDecode"
