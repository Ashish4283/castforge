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


def test_an_object_is_painted_out_of_the_picture_leaving_an_empty_room():
    rgb = np.zeros((20, 20, 3), np.uint8)
    rgb[:, :] = (40, 90, 160)                       # a plain wall
    rgb[6:14, 6:14] = (200, 30, 30)                 # a red thing standing in front of it
    mask = np.zeros((20, 20), np.uint8)
    mask[6:14, 6:14] = set_masks.VISIBLE
    empty = set_masks.patch_background(rgb, mask)
    assert empty.shape == rgb.shape
    patched = empty[6:14, 6:14].astype(int)
    assert abs(patched[:, :, 0].mean() - 40) < 12   # the red is gone, the wall grew in over it
    assert abs(patched[:, :, 2].mean() - 160) < 12
    assert (empty[0, 0] == rgb[0, 0]).all()         # and nothing outside the mask was touched


def test_painting_out_takes_the_hidden_parts_and_several_objects_too():
    rgb = np.full((12, 12, 3), 100, np.uint8)
    rgb[2:5, 2:5] = 250
    rgb[8:11, 8:11] = 10
    a, b = np.zeros((12, 12), np.uint8), np.zeros((12, 12), np.uint8)
    a[2:5, 2:5] = set_masks.VISIBLE
    b[8:11, 8:11] = set_masks.HIDDEN                # a part marked as hidden counts as the object as well
    empty = set_masks.patch_background(rgb, [a, b])
    assert abs(int(empty[3, 3].mean()) - 100) < 12 and abs(int(empty[9, 9].mean()) - 100) < 12
