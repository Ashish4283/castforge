"""Generate camera-matched geometry from marked regions of a background set.

Picture-road props are described in scene.json with normalized image-space points:

    {"id": "snow_road", "make": "picture_road",
     "screen_path": [[0.68, 0.62], [0.65, 0.72], [0.62, 0.84], [0.61, 0.96]],
     "width": 4.0}

The generated OBJ is a floor-plane strip with UVs into the original set image. Its
screen-space footprint can be removed from the set relief to avoid overlapping faces.
"""
import json
import math
import os


def _camera_values(set_data):
    camera = set_data["camera"]
    width, height = set_data["size"]
    lens, sensor = camera["lens"], camera["sensor"]
    pitch = camera.get("pitch", 0.0)
    if lens <= 0 or sensor <= 0 or width <= 0 or height <= 0:
        raise ValueError("set camera lens, sensor and image dimensions must be positive")
    return camera, width, height, lens, sensor, math.sin(pitch), math.cos(pitch)


def image_to_floor(u, v, set_data):
    """Project normalized top-origin image coordinates onto the set's z=0 floor."""
    camera, width, height, lens, sensor, sin_pitch, cos_pitch = _camera_values(set_data)
    if not 0 <= u <= 1 or not 0 <= v <= 1:
        raise ValueError(f"screen point {(u, v)} must be inside the background image")
    vertical_ray = (0.5 - v) * sensor * height / (width * lens)
    denominator = sin_pitch - vertical_ray * cos_pitch
    if denominator <= 1e-6:
        raise ValueError(f"screen point {(u, v)} does not intersect the floor in front of the camera")
    distance = camera["height"] / denominator
    x_ray = (u - 0.5) * sensor / lens
    origin = camera.get("location", [0.0, 0.0, camera["height"]])
    return (
        origin[0] + x_ray * distance,
        origin[1] + (cos_pitch + vertical_ray * sin_pitch) * distance,
        0.0,
    )


def floor_to_image(point, set_data):
    """Project a floor point back to normalized image UVs (top-origin)."""
    camera, width, height, lens, sensor, sin_pitch, cos_pitch = _camera_values(set_data)
    origin = camera.get("location", [0.0, 0.0, camera["height"]])
    dx, dy, dz = point[0] - origin[0], point[1] - origin[1], -camera["height"]
    local_y = dy * sin_pitch + dz * cos_pitch
    local_z = -dy * cos_pitch + dz * sin_pitch
    if local_z >= -1e-6:
        raise ValueError("floor point is behind the set camera")
    return (
        0.5 + dx / -local_z * lens / sensor,
        0.5 - local_y / -local_z * lens * width / (sensor * height),
    )


def picture_road_mesh(prop, set_data):
    """Return world-space strip vertices, image UVs, quad faces and its image-space polygon."""
    screen_path = prop.get("screen_path")
    width = float(prop.get("width", 0.0))
    if not isinstance(screen_path, list) or len(screen_path) < 2:
        raise ValueError(f"{prop.get('id', 'picture road')}: screen_path needs at least two points")
    if width <= 0:
        raise ValueError(f"{prop.get('id', 'picture road')}: width must be positive")
    centers = [image_to_floor(float(p[0]), float(p[1]), set_data) for p in screen_path]
    vertices = []
    for i, center in enumerate(centers):
        before = centers[max(0, i - 1)]
        after = centers[min(len(centers) - 1, i + 1)]
        dx, dy = after[0] - before[0], after[1] - before[1]
        length = math.hypot(dx, dy)
        if length < 1e-5:
            raise ValueError(f"{prop.get('id', 'picture road')}: adjacent screen_path points overlap")
        side_x, side_y = -dy / length * width / 2, dx / length * width / 2
        vertices.extend(((center[0] + side_x, center[1] + side_y, 0.0),
                         (center[0] - side_x, center[1] - side_y, 0.0)))
    uvs = [floor_to_image(vertex, set_data) for vertex in vertices]
    faces = [(2 * i + 1, 2 * i + 2, 2 * i + 4, 2 * i + 3)
             for i in range(len(centers) - 1)]
    polygon = [uvs[2 * i] for i in range(len(centers))]
    polygon.extend(uvs[2 * i + 1] for i in range(len(centers) - 1, -1, -1))
    return vertices, uvs, faces, polygon


def write_picture_road(prop, set_data, output_path):
    """Write a Wavefront OBJ road strip and return its normalized image-space footprint."""
    vertices, uvs, faces, polygon = picture_road_mesh(prop, set_data)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as obj:
        obj.write(f"o {prop.get('id', 'picture_road')}\n")
        for x, y, z in vertices:
            obj.write(f"v {x:.7f} {y:.7f} {z:.7f}\n")
        for u, v in uvs:
            obj.write(f"vt {u:.7f} {1.0 - v:.7f}\n")
        for face in faces:
            refs = " ".join(f"{i}/{i}" for i in face)
            obj.write(f"f {refs}\n")
    return polygon


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate a camera-matched floor prop from scene.json")
    parser.add_argument("--set", required=True, help="generated set.json from depth_set.py")
    parser.add_argument("--scene", required=True, help="scene.json containing a picture_road prop")
    parser.add_argument("--id", required=True, help="picture_road prop id")
    parser.add_argument("--out", required=True, help="output OBJ path")
    args = parser.parse_args()
    set_data = json.load(open(args.set, encoding="utf-8"))
    scene_data = json.load(open(args.scene, encoding="utf-8"))
    prop = next((p for p in scene_data.get("props", [])
                 if p.get("id") == args.id and p.get("make") == "picture_road"), None)
    if prop is None:
        parser.error(f"scene has no picture_road prop with id {args.id!r}")
    polygon = write_picture_road(prop, set_data, args.out)
    print(f"wrote {len(polygon)}-corner picture road {args.id} to {args.out}")


if __name__ == "__main__":
    main()
