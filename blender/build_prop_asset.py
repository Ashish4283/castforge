"""Build an editable procedural prop with its uploaded image included as a Blender reference."""
import argparse
import json
import math
import os
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument("--spec", required=True)
parser.add_argument("--out", required=True)
parser.add_argument("--preview", required=True)
args = parser.parse_args(argv)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for import_path in (ROOT, HERE):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)
from blender import props as prop_factory  # noqa: E402

with open(args.spec, encoding="utf-8") as file:
    spec = json.load(file)
image_path = os.path.join(os.path.dirname(args.spec), spec["image"])
image = bpy.data.images.load(image_path, check_existing=True)

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 640
scene.render.resolution_y = 640
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = False
scene.render.filepath = args.preview
scene.render.fps = 24
scene.view_settings.view_transform = "AgX"
scene.render.image_settings.color_mode = "RGBA"
scene.world.color = (0.12, 0.12, 0.12)

model_collection = bpy.data.collections.new("CastForge Prop Asset")
scene.collection.children.link(model_collection)
reference_collection = bpy.data.collections.new("Reference Image (not rendered)")
scene.collection.children.link(reference_collection)
before = set(bpy.data.objects)
prop_factory.build(
    {"id": spec["name"], "make": spec["make"], "size": spec["size"], "material": spec["material"],
     "color": spec["color"], "position": [0, 0]},
    0, lambda position: Vector((position[0], position[1], 0)), {})
for obj in set(bpy.data.objects) - before:
    for collection in list(obj.users_collection):
        collection.objects.unlink(obj)
    model_collection.objects.link(obj)

width, depth, height = spec["size"]
image_aspect = image.size[0] / max(image.size[1], 1)
reference_height = max(height, width, depth) * 0.8
reference_width = reference_height * image_aspect
reference_x = width / 2 + reference_width / 2 + 0.3
image_material = bpy.data.materials.new("Uploaded Reference Image")
image_material.use_nodes = True
image_material.node_tree.nodes.clear()
texture = image_material.node_tree.nodes.new("ShaderNodeTexImage")
texture.image = image
emission = image_material.node_tree.nodes.new("ShaderNodeEmission")
output = image_material.node_tree.nodes.new("ShaderNodeOutputMaterial")
image_material.node_tree.links.new(texture.outputs["Color"], emission.inputs["Color"])
image_material.node_tree.links.new(emission.outputs[0], output.inputs["Surface"])
reference_mesh = bpy.data.meshes.new("Reference Image Plane")
reference_mesh.from_pydata(
    [(-reference_width / 2, 0, 0), (reference_width / 2, 0, 0),
     (reference_width / 2, 0, reference_height), (-reference_width / 2, 0, reference_height)],
    [], [(0, 1, 2, 3)])
reference_mesh.materials.append(image_material)
uv_layer = reference_mesh.uv_layers.new(name="UVMap")
for loop, uv in zip(uv_layer.data, ((0, 0), (1, 0), (1, 1), (0, 1))):
    loop.uv = uv
reference = bpy.data.objects.new("Uploaded Reference Image", reference_mesh)
reference_collection.objects.link(reference)
reference.location = (reference_x, 0, max(0, (height - reference_height) / 2))
reference.hide_render = True

ground_material = bpy.data.materials.new("Preview Ground")
ground_material.diffuse_color = (0.16, 0.17, 0.19, 1)
ground = bpy.data.meshes.new("Preview Ground Mesh")
ground.from_pydata([(-100, -100, 0), (100, -100, 0), (100, 100, 0), (-100, 100, 0)], [], [(0, 1, 2, 3)])
ground.materials.append(ground_material)
ground_object = bpy.data.objects.new("Preview Ground", ground)
scene.collection.objects.link(ground_object)
ground_object.location.z = -0.015

camera_data = bpy.data.cameras.new("Preview Camera")
camera = bpy.data.objects.new("Preview Camera", camera_data)
scene.collection.objects.link(camera)
scene.camera = camera
distance = max(width, depth, height, 1.0) * 3.2
camera.location = (distance * 0.75, -distance, max(height * 1.4, distance * 0.48))
target = Vector((0, 0, height / 2))
camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
camera_data.lens = 55
camera_data.clip_end = distance * 20

for name, location, energy, size in (
        ("Key", (distance, -distance, distance * 1.5), 1700, distance * 0.8),
        ("Fill", (-distance, -distance * 0.4, distance), 850, distance)):
    light_data = bpy.data.lights.new(name, "AREA")
    light_data.energy = energy
    light_data.shape = "DISK"
    light_data.size = size
    light = bpy.data.objects.new(name, light_data)
    scene.collection.objects.link(light)
    light.location = location
    light.rotation_euler = (target - light.location).to_track_quat("-Z", "Y").to_euler()

bpy.ops.file.pack_all()
bpy.context.view_layer.update()
os.makedirs(os.path.dirname(os.path.abspath(args.preview)), exist_ok=True)
bpy.ops.render.render(write_still=True)
os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=args.out, check_existing=False)
print(f"CF: 3D prop saved to {args.out}")
