import numpy as np

from core import set_masks


def test_quantize_and_box_include_hidden_parts():
    m = np.zeros((10, 20), np.uint8)
    m[2:4, 5:8] = 250
    m[4:6, 5:8] = 120          # the hidden part below
    q = set_masks.quantize(m)
    assert set(np.unique(q)) == {0, 128, 255}
    assert set_masks.bbox(q) == [0.25, 0.2, 0.4, 0.6]
    assert set_masks.bbox(np.zeros((4, 4), np.uint8)) is None


def test_hidden_parts_take_the_objects_own_colours_not_the_background():
    rgb = np.zeros((6, 6, 3), np.uint8)
    rgb[:, :] = (0, 0, 255)          # blue background (e.g. the table in front)
    rgb[0:3, 2:4] = (200, 30, 30)    # the red chair as seen
    m = np.zeros((6, 6), np.uint8)
    m[0:3, 2:4] = 255
    m[3:6, 2:4] = 128                # its legs behind the table
    out = set_masks.fill_hidden(rgb, m)
    assert out.shape == (6, 6, 4)
    assert tuple(out[5, 2, :3]) == (200, 30, 30) and out[5, 2, 3] == 255
    assert out[0, 0, 3] == 0         # outside the object is clear
