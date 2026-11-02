import math

import pytest

from generate.set_props import floor_to_image, image_to_floor, picture_road_mesh, write_picture_road


SET = {
    "size": [1600, 900],
    "camera": {
        "height": 1.45,
        "lens": 18.0,
        "sensor": 36.0,
        "location": [0.0, 0.0, 1.45],
        "pitch": 0.0,
    },
}


def test_image_floor_projection_round_trips():
    original = (0.63, 0.78)

    floor = image_to_floor(*original, SET)

    assert floor_to_image(floor, SET) == pytest.approx(original)


def test_picture_road_mesh_is_a_textured_floor_strip():
    prop = {
        "id": "road",
        "screen_path": [[0.68, 0.61], [0.64, 0.78], [0.61, 0.96]],
        "width": 4.2,
    }

    vertices, uvs, faces, polygon = picture_road_mesh(prop, SET)

    assert len(vertices) == 6
    assert len(uvs) == 6
    assert len(faces) == 2
    assert len(polygon) == 6
    assert all(point[2] == 0.0 for point in vertices)
    assert all(math.isfinite(value) for point in polygon for value in point)


def test_write_picture_road_produces_an_obj(tmp_path):
    output = tmp_path / "props" / "road.obj"
    prop = {"id": "road", "screen_path": [[0.68, 0.61], [0.61, 0.96]], "width": 4.2}

    polygon = write_picture_road(prop, SET, str(output))

    contents = output.read_text(encoding="utf-8")
    assert contents.count("\nv ") == 4
    assert contents.count("\nvt ") == 4
    assert contents.count("\nf ") == 1
    assert len(polygon) == 4


@pytest.mark.parametrize("prop", [
    {"id": "road", "screen_path": [[0.5, 0.7]], "width": 4.0},
    {"id": "road", "screen_path": [[0.5, 0.7], [0.6, 0.8]], "width": 0.0},
    {"id": "road", "screen_path": [[0.5, 0.4], [0.6, 0.8]], "width": 4.0},
])
def test_invalid_picture_road_is_rejected(prop):
    with pytest.raises(ValueError):
        picture_road_mesh(prop, SET)
