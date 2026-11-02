"""Build a reusable Blender set from a background image and its image-guided blueprint."""
import argparse
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Euler, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument("--set-dir", required=True)
parser.add_argument("--geometry-dir", required=True)
parser.add_argument("--out", required=True)
args = parser.parse_args(argv)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for import_path in (ROOT, HERE):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)
from blender import props as prop_factory  # noqa: E402

with open(os.path.join(args.set_dir, "set_blueprint.json"), encoding="utf-8") as file:
    blueprint = json.load(file)
with open(os.path.join(args.geometry_dir, "set.json"), encoding="utf-8") as file:
    set_data = json.load(file)

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x, scene.render.resolution_y = set_data["size"]
scene.render.resolution_percentage = int(
    min(100, 960 / max(scene.render.resolution_x, scene.render.resolution_y) * 100))
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = False
scene.render.fps = 24
scene.render.image_settings.color_mode = "RGBA"
scene.render.filepath = os.path.join(args.set_dir, "set_preview.png")
scene.view_settings.view_transform = "AgX"

camera_data = bpy.data.cameras.new("SetCamera")
camera = bpy.data.objects.new("SetCamera", camera_data)
scene.collection.objects.link(camera)
scene.camera = camera
camera_data.lens = set_data["camera"]["lens"]
camera_data.sensor_width = set_data["camera"]["sensor"]
camera_data.sensor_fit = "HORIZONTAL"
camera_data.clip_end = 200
camera.location = set_data["camera"]["location"]
camera.rotation_euler = (math.pi / 2 - set_data["camera"].get("pitch", 0.0), 0, 0)
camera_rotation = camera.rotation_euler.to_matrix()
scene.world.color = (0.12, 0.12, 0.12)

light_data = bpy.data.lights.new("SetKey", "AREA")
light_data.energy = 1800
light_data.shape = "DISK"
light_data.size = 8
light = bpy.data.objects.new("SetKey", light_data)
scene.collection.objects.link(light)
light.location = (0, 2, 7)
light.rotation_euler = (0.25, 0, 0)

vertices, uvs, faces = [], [], []
with open(os.path.join(args.geometry_dir, "set.obj"), encoding="utf-8") as file:
    for line in file:
        if line.startswith("v "):
            vertices.append([float(value) for value in line.split()[1:4]])
        elif line.startswith("vt "):
            uvs.append([float(value) for value in line.split()[1:3]])
        elif line.startswith("f "):
            faces.append([tuple(int(index) - 1 for index in item.split("/")[:2])
                          for item in line.split()[1:]])
mesh = bpy.data.meshes.new("SetReliefMesh")
mesh.from_pydata(vertices, [], [[vertex for vertex, _ in face] for face in faces])
mesh.update()
uv_layer = mesh.uv_layers.new(name="UVMap")
for polygon, face in zip(mesh.polygons, faces):
    for loop_index, (_, uv_index) in zip(polygon.loop_indices, face):
        uv_layer.data[loop_index].uv = uvs[uv_index]
relief = bpy.data.objects.new("SetRelief", mesh)
scene.collection.objects.link(relief)
image_path = set_data["image"]
image = bpy.data.images.load(image_path, check_existing=True)
background = bpy.data.materials.new("SetBackground")
background.use_nodes = True
background.node_tree.nodes.clear()
texture = background.node_tree.nodes.new("ShaderNodeTexImage")
texture.image = image
texture.extension = "EXTEND"
coordinates = background.node_tree.nodes.new("ShaderNodeTexCoord")
emission = background.node_tree.nodes.new("ShaderNodeEmission")
output = background.node_tree.nodes.new("ShaderNodeOutputMaterial")
background.node_tree.links.new(coordinates.outputs["UV"], texture.inputs["Vector"])
background.node_tree.links.new(texture.outputs["Color"], emission.inputs["Color"])
background.node_tree.links.new(emission.outputs[0], output.inputs["Surface"])
relief.data.materials.clear()
relief.data.materials.append(background)
relief.visible_shadow = False

vertices, uvs = np.asarray(vertices), np.asarray(uvs)
if not len(vertices) or not len(uvs) or not len(faces):
    raise ValueError("depth set contains no textured mesh faces; regenerate the set geometry")
camera_location = Vector(camera.location)
image_width, image_height = set_data["size"]
lens, sensor = camera_data.lens, camera_data.sensor_width
origin = Vector((set_data["stage_origin"][0], set_data["stage_origin"][1], 0))


def image_ray(u, v):
    return Vector(((u - 0.5) * sensor / lens,
                   (0.5 - v) * sensor * image_height / (image_width * lens), -1.0))


def rect_geometry(rect, object_id):
    u0, v0, u1, v1 = rect
    selected = ((uvs[:, 0] >= u0) & (uvs[:, 0] <= u1)
                & (1 - uvs[:, 1] >= v0) & (1 - uvs[:, 1] <= v1))
    if not selected.any():
        centre_uv = np.array(((u0 + u1) / 2, 1 - (v0 + v1) / 2))
        selected[np.argmin(np.sum((uvs - centre_uv) ** 2, axis=1))] = True
        print(f"CF: WARNING {object_id}: no depth sample inside marked region; using the nearest sample")
    camera_space = (vertices[selected] - np.asarray(camera_location)) @ np.asarray(camera_rotation)
    distance = float(np.median(-camera_space[:, 2]))
    if distance <= 0:
        raise ValueError(f"{object_id}: image region is behind the set camera")
    lower_left = camera_location + camera_rotation @ (image_ray(u0, v1) * distance)
    lower_right = camera_location + camera_rotation @ (image_ray(u1, v1) * distance)
    upper_left = camera_location + camera_rotation @ (image_ray(u0, v0) * distance)
    centre = camera_location + camera_rotation @ (image_ray((u0 + u1) / 2, (v0 + v1) / 2) * distance)
    return centre, (lower_right - lower_left).length, (upper_left - lower_left).length


def linked_image(set_name):
    sibling = os.path.join(os.path.dirname(args.set_dir), set_name)
    images = sorted(name for name in os.listdir(sibling)
                    if name.lower().endswith((".png", ".jpg", ".jpeg"))
                    and name.lower() != "set_preview.png")
    if not images:
        raise ValueError(f"linked outside set {set_name!r} has no background image")
    return os.path.join(sibling, images[0])


roots = []
tops = {}
for index, source_prop in enumerate(blueprint.get("props", [])):
    prop = dict(source_prop)
    if prop.get("outside_set"):
        prop["outside_image"] = linked_image(prop["outside_set"])
    root, _, top = prop_factory.build(
        prop, index, lambda position: Vector((position[0], position[1], 0)) + origin, tops)
    tops[prop.get("id", root.name)] = top
    roots.append((root, prop))

for root, prop in roots:
    rect = prop.get("picture_rect")
    if not rect:
        continue
    centre, width, height = rect_geometry(rect, prop["id"])
    size = prop.get("size") or prop_factory.DEFAULT_SIZE[prop["make"]]
    if size[0] <= 0 or size[2] <= 0:
        raise ValueError(f"{prop['id']}: image-fitted objects need positive width and height")
    heading = math.radians(float(prop.get("picture_heading", 0)))
    orientation = (camera_rotation @ Euler((-math.pi / 2, 0, 0)).to_matrix()
                   @ Euler((0, 0, heading)).to_matrix())
    scale_x = width / size[0]
    root.rotation_euler = orientation.to_euler()
    root.scale = (scale_x, scale_x, height / size[2])
    root.location = centre - orientation @ Vector((0, 0, height / 2))
prop_factory.update_attached_doors()

door_rects = [prop["picture_rect"] for _, prop in roots
              if prop.get("make") == "door" and prop.get("picture_rect")]
if door_rects:
    import bmesh

    mesh = relief.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    uv_layer = bm.loops.layers.uv.active
    if uv_layer:
        for face in list(bm.faces):
            image_points = [(loop[uv_layer].uv.x, 1 - loop[uv_layer].uv.y) for loop in face.loops]
            if any(all(u0 <= u <= u1 and v0 <= v <= v1 for u, v in image_points)
                   for u0, v0, u1, v1 in door_rects):
                bm.faces.remove(face)
        bm.to_mesh(mesh)
    bm.free()
    mesh.update()

bpy.ops.file.pack_all()
bpy.context.view_layer.update()
os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=args.out, check_existing=False)
print(f"CF: 3D set saved to {args.out}")
