"""Build a reusable exterior building asset from a starter design."""
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from core.buildings import BUILDING_DESIGNS  # noqa: E402
from blender.library_geometry import build_special  # noqa: E402

with open(args.spec, encoding="utf-8") as file:
    spec = json.load(file)
template = BUILDING_DESIGNS[spec["template"]]
family = template.get("family", "building")
width, depth = spec["footprint"]
floors = spec["floors"]
asset_width, asset_depth, asset_height = spec["size"]
floor_height = 2.8
body_height = floor_height * floors if family == "building" else asset_height
roof_height = max(0.8, min(width, depth) * 0.22) if template["style"] in ("cabin", "residential") else 0.45


def hex_color(value):
    channels = [int(value[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    return tuple(channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
                 for channel in channels)


def make_material(name, color, roughness=0.78, metallic=0.0):
    material = bpy.data.materials.new(name)
    material.diffuse_color = (*color, 1)
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    return material


wall = make_material("Facade", hex_color(spec["wall_color"]))
roof = make_material("Roof", hex_color(spec["roof_color"]), 0.62)
trim = make_material("Light trim", (0.78, 0.73, 0.64))
glass = make_material("Window glass", (0.055, 0.16, 0.22), 0.22, 0.25)
door_material = make_material("Entry door", (0.16, 0.11, 0.08), 0.68)
accent = make_material("Building accent", (0.12, 0.23, 0.36), 0.6)
white = make_material("Sign and civic markings", (0.91, 0.89, 0.79), 0.65)
red = make_material("Medical marking", (0.72, 0.06, 0.045), 0.55)
dark = make_material("Dark trim", (0.035, 0.045, 0.055), 0.78)
asphalt = make_material("Asphalt", hex_color(spec["wall_color"]), 0.9)
paint = make_material("Road paint", hex_color(spec["roof_color"]), 0.72)
green = make_material("Grass", hex_color(spec["wall_color"]), 0.92)
foliage = make_material("Tree foliage", hex_color(spec["roof_color"]), 0.9)
trunk = make_material("Tree bark", hex_color(spec["wall_color"]), 0.92)
sand = make_material("Arena sand", (0.55, 0.39, 0.21), 0.92)
gold = make_material("Metallic gold", (0.55, 0.32, 0.07), 0.3, 0.72)
blue = make_material("Screen blue", (0.035, 0.16, 0.55), 0.25, 0.15)
silver = make_material("Metallic silver", (0.48, 0.52, 0.56), 0.25, 0.75)
rubber = make_material("Tire rubber", (0.025, 0.03, 0.034), 0.92)
seat_material = make_material("Audience seats", (0.55, 0.12, 0.08), 0.72)

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 640
scene.render.resolution_y = 640
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = False
scene.render.filepath = args.preview
scene.view_settings.view_transform = "AgX"
scene.world.color = (0.12, 0.12, 0.12)

model_collection = bpy.data.collections.new("CastForge Prop Asset")
scene.collection.children.link(model_collection)
before = set(bpy.data.objects)


def box(name, size, location, material, bevel=0.035):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    if bevel:
        modifier = obj.modifiers.new("Soft architectural edges", "BEVEL")
        modifier.width = min(bevel, min(size) * 0.16)
        modifier.segments = 2
        obj.modifiers.new("Weighted corner normals", "WEIGHTED_NORMAL")
    return obj


def text(name, body, location, size, material):
    curve = bpy.data.curves.new(name, "FONT")
    curve.body = body.replace("_", " ").upper()
    curve.size = size
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    obj = bpy.data.objects.new(name, curve)
    scene.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (math.radians(90), 0, 0)
    curve.materials.append(material)
    return obj


def gable_roof():
    half_width = width / 2 + 0.28
    half_depth = depth / 2 + 0.3
    vertices = [
        (-half_width, -half_depth, body_height), (half_width, -half_depth, body_height),
        (0, -half_depth, body_height + roof_height),
        (-half_width, half_depth, body_height), (half_width, half_depth, body_height),
        (0, half_depth, body_height + roof_height),
    ]
    mesh = bpy.data.meshes.new("Pitched roof mesh")
    mesh.from_pydata(vertices, [], [(0, 2, 5, 3), (2, 1, 4, 5), (0, 1, 2), (3, 5, 4)])
    mesh.materials.append(roof)
    obj = bpy.data.objects.new("Pitched roof", mesh)
    scene.collection.objects.link(obj)
    return obj


front_y = -depth / 2 - 0.06
box("Foundation", (width + 0.25, depth + 0.25, 0.24), (0, 0, 0.12), trim)
box("Building mass", (width, depth, body_height), (0, 0, 0.24 + body_height / 2), wall)
building_top = 0.24 + body_height

door_width = min(1.25, width * 0.16)
door_height = min(2.2, floor_height * 0.82)
box("Entry door", (door_width, 0.12, door_height), (0, front_y, 0.24 + door_height / 2), door_material, 0.02)
for side in (-1, 1):
    box("Door jamb", (0.08, 0.16, door_height + 0.1),
        (side * (door_width / 2 + 0.06), front_y - 0.015, 0.24 + door_height / 2), trim, 0.01)
box("Door lintel", (door_width + 0.2, 0.16, 0.09),
    (0, front_y - 0.015, 0.24 + door_height + 0.06), trim, 0.01)
box("Entry step", (door_width + 0.55, 0.55, 0.14), (0, front_y - 0.24, 0.07), trim, 0.025)

style = template["style"]
if family != "building":
    for obj in set(bpy.data.objects) - before:
        bpy.data.objects.remove(obj, do_unlink=True)
    build_special(spec, template, scene, box, {
        "wall": wall, "roof": roof, "trim": trim, "glass": glass, "accent": accent,
        "white": white, "dark": dark, "asphalt": asphalt, "paint": paint, "green": green,
        "foliage": foliage, "trunk": trunk, "sand": sand, "gold": gold, "blue": blue,
        "silver": silver, "rubber": rubber, "seat": seat_material, "red": red, "mat": wall,
    })
elif style in ("cabin", "residential"):
    gable_roof()
elif family == "building":
    box("Flat roof and parapet", (width + 0.35, depth + 0.35, 0.34),
        (0, 0, building_top + 0.17), roof, 0.045)

bay_count = min(8, max(2, int(width // (3.0 if width > 10 else 2.2))))
window_width = min(1.55, width / (bay_count + 1) * 0.62)
window_height = 1.1 if floors == 1 else 1.35
front_levels = range(floors)
if style in ("shop", "retail", "mall", "station", "diner"):
    front_levels = range(1, floors)
for floor in front_levels:
    center_z = 0.24 + floor * floor_height + floor_height * 0.59
    for bay in range(bay_count):
        x = (bay - (bay_count - 1) / 2) * (width * 0.78 / max(bay_count - 1, 1))
        if floor == 0 and abs(x) < door_width * 0.78:
            continue
        box("Glazed window", (window_width, 0.055, window_height), (x, front_y - 0.07, center_z), glass, 0.012)
        for side in (-1, 1):
            box("Window frame", (0.055, 0.09, window_height + 0.12),
                (x + side * (window_width / 2 + 0.035), front_y - 0.105, center_z), trim, 0.01)
        for edge in (-1, 1):
            box("Window frame", (window_width + 0.12, 0.09, 0.055),
                (x, front_y - 0.105, center_z + edge * (window_height / 2 + 0.035)), trim, 0.01)
        if style in ("row", "residential", "hospital", "police", "hotel", "jail"):
            box("Window mullion", (0.035, 0.1, window_height),
                (x, front_y - 0.13, center_z), trim, 0.008)

if style in ("shop", "retail", "mall", "station", "restaurant", "diner"):
    ground_bays = max(2, min(8, int(width // 3)))
    glass_width = width * 0.72 / ground_bays
    for bay in range(ground_bays):
        x = (bay - (ground_bays - 1) / 2) * width * 0.72 / ground_bays
        if abs(x) > door_width * 0.85:
            box("Storefront glass", (glass_width * 0.82, 0.055, 1.8),
                (x, front_y - 0.08, 1.24), glass, 0.012)
    sign_z = min(body_height - 0.28, 2.45)
    box("Sign band", (width * 0.74, 0.12, 0.48), (0, front_y - 0.12, sign_z), accent, 0.025)
    text("Store sign", spec["name"], (0, front_y - 0.19, sign_z), min(0.32, width / 18), white)

if style in ("shop", "retail", "mall", "station", "police", "hotel", "restaurant", "diner"):
    canopy_width = width * (0.68 if style == "shop" else 0.88)
    box("Entry canopy", (canopy_width, 1.15, 0.16),
        (0, front_y - 0.53, 2.55), accent if style == "police" else roof, 0.025)
    for x in (-canopy_width * 0.42, canopy_width * 0.42):
        box("Canopy support", (0.12, 0.12, 2.4), (x, front_y - 0.95, 1.2), trim, 0.015)

if style in ("hotel", "restaurant", "diner"):
    sign_z = min(body_height - 0.32, 2.9)
    box("Venue sign band", (width * 0.62, 0.12, 0.48), (0, front_y - 0.14, sign_z), accent, 0.025)
    text("Venue sign", spec["name"], (0, front_y - 0.22, sign_z), min(0.36, width / 18), white)
if style == "jail":
    for floor in range(floors):
        center_z = 0.24 + floor * floor_height + floor_height * 0.59
        for bay in range(bay_count):
            x = (bay - (bay_count - 1) / 2) * (width * 0.78 / max(bay_count - 1, 1))
            if floor == 0 and abs(x) < door_width * 0.78:
                continue
            for bar_index in range(5):
                bar_x = x + (bar_index - 2) * window_width * 0.16
                box("Jail window bar", (0.035, 0.1, window_height + 0.04),
                    (bar_x, front_y - 0.18, center_z), dark, 0.008)
if family == "building" and style == "hotel":
    for side in (-1, 1):
        box("Hotel entrance column", (0.25, 0.32, 2.65),
            (side * width * 0.12, front_y - 0.3, 1.32), trim, 0.035)

if style == "hospital":
    cross_z = min(body_height - 0.45, 3.1)
    box("Hospital cross vertical", (0.18, 0.16, 0.9), (0, front_y - 0.23, cross_z), red, 0.015)
    box("Hospital cross horizontal", (0.72, 0.16, 0.18), (0, front_y - 0.25, cross_z), red, 0.015)
if style == "police":
    box("Police entry stripe", (width * 0.88, 0.14, 0.22), (0, front_y - 0.14, 2.85), accent, 0.01)
    text("Police sign", "POLICE", (0, front_y - 0.23, min(body_height - 0.5, 3.6)), 0.48, white)
if style == "castle":
    tower_radius = max(0.55, min(width, depth) * 0.055)
    for x in (-width / 2 + tower_radius, width / 2 - tower_radius):
        for y in (-depth / 2 + tower_radius, depth / 2 - tower_radius):
            bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=tower_radius, depth=body_height + 0.7,
                                                location=(x, y, (body_height + 0.7) / 2 + 0.24))
            tower = bpy.context.object
            tower.name = "Castle corner tower"
            tower.data.materials.append(wall)
            bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=tower_radius * 1.12, radius2=0.08,
                                            depth=0.75, location=(x, y, body_height + 0.24 + body_height + 0.36))
            bpy.context.object.name = "Castle tower roof"
            bpy.context.object.data.materials.append(roof)
    crenel_width = max(0.35, width / 18)
    count = max(6, int(width / (crenel_width * 1.8)))
    for index in range(count):
        x = (index - (count - 1) / 2) * width / count
        box("Crenellation", (crenel_width, 0.38, 0.42), (x, front_y, building_top + 0.36), wall, 0.015)

model_objects = set(bpy.data.objects) - before
for obj in model_objects:
    for collection in list(obj.users_collection):
        collection.objects.unlink(obj)
    model_collection.objects.link(obj)

ground_material = make_material("Preview ground", (0.16, 0.17, 0.19))
ground_mesh = bpy.data.meshes.new("Preview ground mesh")
ground_mesh.from_pydata([(-100, -100, 0), (100, -100, 0), (100, 100, 0), (-100, 100, 0)], [], [(0, 1, 2, 3)])
ground_mesh.materials.append(ground_material)
ground_object = bpy.data.objects.new("Preview ground", ground_mesh)
scene.collection.objects.link(ground_object)
ground_object.location.z = -0.015

distance = max(width, depth, body_height, 1.0) * 2.5
target = Vector((0, 0, (building_top + roof_height) / 2))
camera_data = bpy.data.cameras.new("Preview camera")
camera = bpy.data.objects.new("Preview camera", camera_data)
scene.collection.objects.link(camera)
scene.camera = camera
camera.location = (distance * 0.85, -distance, max(body_height * 1.2, distance * 0.65))
camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
camera_data.lens = 68 if family == "arena" else 55
camera_data.clip_end = distance * 20
light_scale = max((distance / 3) ** 2, 1)
for name, location, energy, size in (
        ("Key", (distance, -distance, distance * 1.4), 2200 * light_scale, distance * 0.7),
        ("Fill", (-distance, -distance * 0.5, distance), 1200 * light_scale, distance)):
    light_data = bpy.data.lights.new(name, "AREA")
    light_data.energy, light_data.shape, light_data.size = energy, "DISK", size
    light = bpy.data.objects.new(name, light_data)
    scene.collection.objects.link(light)
    light.location = location
    light.rotation_euler = (target - light.location).to_track_quat("-Z", "Y").to_euler()

bpy.context.view_layer.update()
os.makedirs(os.path.dirname(os.path.abspath(args.preview)), exist_ok=True)
bpy.ops.render.render(write_still=True)
os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=args.out, check_existing=False)
print(f"CF: 3D building saved to {args.out}")
