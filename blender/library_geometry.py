"""Reusable procedural geometry for city-library assets outside the building facade family."""
import math

import bpy
from mathutils import Vector


def build_special(spec, template, scene, box, materials):
    family = template.get("family", "building")
    if family == "building":
        return False
    width, length, height = spec["size"]
    style = template["style"]
    wall = materials["wall"]
    roof = materials["roof"]
    glass = materials["glass"]
    trim = materials["trim"]
    accent = materials["accent"]
    white = materials["white"]
    dark = materials["dark"]
    asphalt = materials["asphalt"]
    paint = materials["paint"]
    green = materials["green"]
    foliage = materials["foliage"]
    trunk = materials["trunk"]

    def cylinder(name, radius, depth, location, material, vertices=24, rotation=(0, 0, 0)):
        bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth,
                                            location=location, rotation=rotation)
        obj = bpy.context.object
        obj.name = name
        obj.data.materials.append(material)
        bevel = obj.modifiers.new("Soft edges", "BEVEL")
        bevel.width = min(radius * 0.1, depth * 0.08)
        bevel.segments = 2
        obj.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
        return obj

    def sphere(name, scale, location, material):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=1, location=location)
        obj = bpy.context.object
        obj.name = name
        obj.scale = scale
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        obj.data.materials.append(material)
        bpy.ops.object.shade_smooth()
        return obj

    def torus(name, major, minor, location, material, scale=(1, 1, 1)):
        bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, major_segments=64,
                                         minor_segments=12, location=location)
        obj = bpy.context.object
        obj.name = name
        obj.scale = scale
        obj.data.materials.append(material)
        bpy.ops.object.shade_smooth()
        return obj

    def cone(name, radius, depth, location, material):
        bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=radius, radius2=0.05, depth=depth, location=location)
        obj = bpy.context.object
        obj.name = name
        obj.data.materials.append(material)
        return obj

    def tree_at(x, y, scale=1, kind="oak"):
        height_ = height if family == "tree" else 7.0
        trunk_height = height_ * 0.48 * scale
        trunk_radius = max(0.16, height_ * 0.035) * scale
        cylinder("Tree trunk", trunk_radius, trunk_height, (x, y, trunk_height / 2), trunk, 16)
        crown_height = height_ - trunk_height
        if kind == "pine":
            cone("Evergreen crown lower", height_ * 0.24 * scale, crown_height * 0.7,
                 (x, y, trunk_height + crown_height * 0.32), foliage)
            cone("Evergreen crown upper", height_ * 0.18 * scale, crown_height * 0.62,
                 (x, y, trunk_height + crown_height * 0.69), foliage)
        elif kind == "palm":
            crown_z = height_ * 0.88 * scale
            for index in range(8):
                angle = math.tau * index / 8
                end_x = x + math.cos(angle) * height_ * 0.35 * scale
                end_y = y + math.sin(angle) * height_ * 0.35 * scale
                frond = box("Palm frond", (height_ * 0.5 * scale, 0.12 * scale, 0.08 * scale),
                            ((x + end_x) / 2, (y + end_y) / 2, crown_z - height_ * 0.1 * scale),
                            foliage, 0.04 * scale)
                frond.rotation_euler[2] = angle
            sphere("Palm crown", (0.42 * scale, 0.42 * scale, 0.34 * scale),
                   (x, y, crown_z), foliage)
        else:
            sphere("Tree canopy", (height_ * 0.3 * scale, height_ * 0.3 * scale, crown_height * 0.42),
                   (x, y, trunk_height + crown_height * 0.53), foliage)

    def oval_ring(name, radius_x, radius_y, thickness, z, material):
        segments = 64
        inner_x = max(0.1, radius_x - thickness)
        inner_y = max(0.1, radius_y - thickness)
        vertices = []
        for ring_x, ring_y, ring_z in (
                (radius_x, radius_y, z), (radius_x, radius_y, z + thickness),
                (inner_x, inner_y, z + thickness), (inner_x, inner_y, z)):
            vertices.extend((ring_x * math.cos(math.tau * index / segments),
                             ring_y * math.sin(math.tau * index / segments), ring_z)
                            for index in range(segments))
        faces = []
        for index in range(segments):
            following = (index + 1) % segments
            faces.extend((
                (segments + index, segments + following, 2 * segments + following, 2 * segments + index),
                (index, following, segments + following, segments + index),
                (2 * segments + index, 2 * segments + following, 3 * segments + following,
                 3 * segments + index),
            ))
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(vertices, [], faces)
        mesh.materials.append(material)
        obj = bpy.data.objects.new(name, mesh)
        scene.collection.objects.link(obj)
        return obj

    def oval_tier(name, inner_x, inner_y, outer_x, outer_y, bottom_z, top_z, material):
        segments = 64
        vertices = []
        for radius_x, radius_y, z in (
                (outer_x, outer_y, bottom_z), (outer_x, outer_y, top_z),
                (inner_x, inner_y, top_z), (inner_x, inner_y, bottom_z)):
            vertices.extend((radius_x * math.cos(math.tau * index / segments),
                             radius_y * math.sin(math.tau * index / segments), z)
                            for index in range(segments))
        faces = []
        for index in range(segments):
            following = (index + 1) % segments
            faces.extend((
                (segments + index, segments + following, 2 * segments + following, 2 * segments + index),
                (index, following, segments + following, segments + index),
                (2 * segments + index, 2 * segments + following, 3 * segments + following,
                 3 * segments + index),
                (3 * segments + index, 3 * segments + following, following, index),
            ))
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(vertices, [], faces)
        mesh.materials.append(material)
        obj = bpy.data.objects.new(name, mesh)
        scene.collection.objects.link(obj)
        return obj

    if family == "tree":
        tree_at(0, 0, 1, style)
    elif family == "garden":
        box("Garden lawn", (width, length, 0.18), (0, 0, 0.09), green, 0.03)
        box("Cross path east-west", (width * 0.9, 2.0, 0.08), (0, 0, 0.19), trim, 0.015)
        box("Cross path north-south", (2.0, length * 0.82, 0.08), (0, 0, 0.2), trim, 0.015)
        cylinder("Fountain basin", 2.1, 0.34, (0, 0, 0.4), trim, 48)
        cylinder("Fountain water", 1.72, 0.08, (0, 0, 0.61), glass, 48)
        cylinder("Fountain pedestal", 0.38, 1.25, (0, 0, 1.25), wall, 24)
        sphere("Fountain finial", (0.3, 0.3, 0.42), (0, 0, 2.0), glass)
        for x in (-width * 0.37, width * 0.37):
            for y in (-length * 0.36, length * 0.36):
                tree_at(x, y, 0.7, "oak")
            box("Garden bench seat", (2.0, 0.52, 0.15), (x, 0, 0.65), trunk, 0.035)
            for y in (-0.2, 0.2):
                box("Garden bench leg", (0.12, 0.12, 0.58), (x, y, 0.35), dark, 0.015)
        for x in (-width * 0.29, width * 0.29):
            for y in (-length * 0.26, length * 0.26):
                cylinder("Flower bed", 1.2, 0.24, (x, y, 0.31), trunk, 24)
                for index in range(7):
                    angle = math.tau * index / 7
                    sphere("Flower", (0.18, 0.18, 0.22),
                           (x + math.cos(angle) * 0.68, y + math.sin(angle) * 0.68, 0.54),
                           accent if index % 2 else white)
    elif family == "arena":
        if style == "roman":
            cylinder("Arena sand floor", width * 0.27, 0.24, (0, 0, 0.12), materials["sand"], 64)
            for index in range(6):
                inner = 0.23 + index * 0.05
                outer = inner + 0.05
                base_z = 0.24 + index * 0.62
                oval_tier("Stone seating tier", width * inner, length * inner,
                          width * outer, length * outer, base_z, base_z + 0.58,
                          wall if index % 2 else trim)
            oval_ring("Outer arena wall", width * 0.58, length * 0.58, 0.55, 3.65, trim)
            for side in (-1, 1):
                for index in range(5):
                    x = (index - 2) * width * 0.16
                    cylinder("Amphitheatre column", 0.22, 4.0, (x, side * length * 0.49, 2.2), trim, 16)
        elif style == "stadium":
            box("Playing field", (width * 0.46, length * 0.34, 0.16), (0, 0, 0.08), green, 0.02)
            for index, (inner, outer, base_z, top_z, material) in enumerate((
                    ((0.21, 0.17), (0.39, 0.37), 0.22, 1.65, wall),
                    ((0.39, 0.37), (0.49, 0.47), 1.65, 3.2, accent),
                    ((0.49, 0.47), (0.57, 0.55), 3.2, 4.75, roof))):
                oval_tier(f"Stadium seating tier {index + 1}",
                          width * inner[0], length * inner[1],
                          width * outer[0], length * outer[1], base_z, top_z, material)
            for side in (-1, 1):
                x = side * width * 0.59
                box("Stadium floodlight tower", (0.45, 0.45, height * 0.8), (x, 0, height * 0.4), dark, 0.04)
                box("Stadium light bank", (2.2, 0.5, 0.55), (x, 0, height * 0.82), white, 0.04)
        elif style == "disco":
            box("Dance floor", (width * 0.48, length * 0.4, 0.18), (0, 0, 0.09), dark, 0.02)
            for index, material in enumerate((accent, materials["red"], materials["blue"], materials["gold"])):
                offset = index - 1.5
                box("Lit dance-floor strip", (width * 0.42, 0.16, 0.04),
                    (0, offset * 1.1, 0.21), material, 0)
            box("DJ stage", (width * 0.45, 2.2, 1.1), (0, length * 0.31, 0.55), wall, 0.04)
            box("DJ console", (width * 0.32, 0.55, 0.5), (0, length * 0.31 - 0.45, 1.3), dark, 0.04)
            sphere("Disco ball", (1.05, 1.05, 1.05), (0, 0, height * 0.8), materials["silver"])
            for index in range(8):
                angle = math.tau * index / 8
                x, y = math.cos(angle) * width * 0.45, math.sin(angle) * length * 0.4
                cylinder("Disco light column", 0.14, height * 0.65, (x, y, height * 0.325), accent, 12)
        else:
            box("Arena floor", (width * 0.32, length * 0.28, 0.32), (0, 0, 0.16), materials["mat"], 0.03)
            ring_width = min(width, length) * 0.26
            box("Arena platform", (ring_width, ring_width, 0.5), (0, 0, 0.4), dark, 0.04)
            box("Ring mat", (ring_width * 0.9, ring_width * 0.9, 0.12), (0, 0, 0.72), materials["mat"], 0.015)
            for x in (-ring_width * 0.43, ring_width * 0.43):
                for y in (-ring_width * 0.43, ring_width * 0.43):
                    cylinder("Arena ring post", 0.09, 2.3, (x, y, 1.86), materials["gold"], 16)
            for z in (1.25, 1.85, 2.45):
                for side in (-1, 1):
                    x = side * ring_width * 0.43
                    box("Ring rope", (0.07, ring_width * 0.86, 0.07), (x, 0, z), materials["red"], 0.025)
                    box("Ring rope", (ring_width * 0.86, 0.07, 0.07), (0, side * ring_width * 0.43, z),
                        materials["red"], 0.025)
            for tier in range(5):
                z = 0.48 + tier * 0.48
                radius = ring_width * (0.78 + tier * 0.2)
                for side in (-1, 1):
                    for seat_index in range(12):
                        x = (seat_index - 5.5) * radius * 0.13
                        for y in (-radius, radius):
                            box("Arena audience seat", (0.72, 0.62, 0.5), (x, y, z), materials["seat"], 0.03)
        if style in ("fighting", "wrestling"):
            for side in (-1, 1):
                box("Arena video screen", (width * 0.32, 0.38, 3.2),
                    (side * width * 0.32, length * 0.36, height * 0.7), materials["blue"], 0.05)
            for side in (-1, 1):
                box("Arena roof truss", (width * 0.85, 0.42, 0.42),
                    (0, side * length * 0.34, height * 0.94), dark, 0.03)
                for index in range(5):
                    x = (index - 2) * width * 0.18
                    cylinder("Arena spotlight", 0.25, 0.38, (x, side * length * 0.34, height * 0.88),
                             materials["gold"], 16)
    elif family == "vehicle":
        body_width = width * 0.82
        wheel_radius = max(0.25, min(width, length) * 0.105)
        wheel_z = wheel_radius
        wheel_x = width * 0.43
        front_y = -length * 0.32
        rear_y = length * 0.32
        if style in ("car", "jeep", "truck"):
            box("Vehicle chassis", (body_width, length * 0.9, height * 0.26),
                (0, 0, wheel_z + height * 0.17), dark, min(0.16, height * 0.06))
            for x in (-wheel_x, wheel_x):
                for y in (front_y, rear_y):
                    wheel = cylinder("Rubber tire", wheel_radius, 0.2, (x, y, wheel_z),
                                     materials["rubber"], 24, (0, math.pi / 2, 0))
                    cylinder("Wheel hub", wheel_radius * 0.48, 0.22, (x * 1.03, y, wheel_z),
                             materials["silver"], 20, (0, math.pi / 2, 0))
            if style == "truck":
                box("Truck cab", (body_width * 0.98, length * 0.28, height * 0.72),
                    (0, -length * 0.27, wheel_z + height * 0.47), wall, 0.16)
                box("Truck windshield", (body_width * 0.82, 0.06, height * 0.33),
                    (0, -length * 0.415, wheel_z + height * 0.56), glass, 0.025)
                box("Cargo body", (body_width * 0.95, length * 0.48, height * 0.48),
                    (0, length * 0.23, wheel_z + height * 0.36), accent, 0.09)
                for side in (-1, 1):
                    box("Truck cargo rail", (0.08, length * 0.47, height * 0.12),
                        (side * body_width * 0.47, length * 0.23, wheel_z + height * 0.67), trim, 0.02)
            else:
                body_length = length * (0.72 if style == "jeep" else 0.68)
                box("Vehicle body", (body_width, body_length, height * 0.38),
                    (0, 0, wheel_z + height * 0.26), wall, min(0.16, height * 0.06))
                cabin_length = length * (0.43 if style == "jeep" else 0.38)
                box("Vehicle cabin", (body_width * 0.72, cabin_length, height * 0.38),
                    (0, length * 0.04, wheel_z + height * 0.59), roof, min(0.12, height * 0.05))
                box("Front windshield", (body_width * 0.66, 0.07, height * 0.26),
                    (0, -length * 0.17, wheel_z + height * 0.61), glass, 0.02)
                box("Rear window", (body_width * 0.62, 0.07, height * 0.23),
                    (0, length * 0.23, wheel_z + height * 0.61), glass, 0.02)
                for x in (-body_width * 0.36, body_width * 0.36):
                    box("Side window", (0.055, cabin_length * 0.72, height * 0.2),
                        (x, length * 0.04, wheel_z + height * 0.62), glass, 0.015)
                for x in (-body_width * 0.32, body_width * 0.32):
                    sphere("Headlight", (0.16, 0.1, 0.11), (x, -length * 0.36, wheel_z + height * 0.38), white)
                    sphere("Tail light", (0.13, 0.09, 0.13), (x, length * 0.36, wheel_z + height * 0.38),
                           materials["red"])
                if style == "jeep":
                    for x in (-body_width * 0.36, body_width * 0.36):
                        for y in (-length * 0.17, length * 0.25):
                            cylinder("Jeep roll bar", 0.055, height * 0.65,
                                     (x, y, wheel_z + height * 0.68), dark, 12)
                    cylinder("Rear spare tire", wheel_radius * 0.82, 0.22,
                             (0, length * 0.49, wheel_z + height * 0.44), materials["rubber"],
                             24, (math.pi / 2, 0, 0))
        elif style == "helicopter":
            sphere("Helicopter fuselage", (width * 0.34, length * 0.23, height * 0.24),
                   (0, -length * 0.03, height * 0.52), wall)
            sphere("Helicopter cockpit", (width * 0.28, length * 0.13, height * 0.2),
                   (0, -length * 0.21, height * 0.56), glass)
            box("Helicopter tail boom", (width * 0.1, length * 0.48, height * 0.1),
                (0, length * 0.34, height * 0.56), roof, 0.08)
            sphere("Tail rotor hub", (0.18, 0.18, 0.18), (0, length * 0.58, height * 0.58), trim)
            for angle in (0, math.pi / 2):
                blade = box("Tail rotor blade", (width * 0.48, 0.08, 0.07),
                            (0, length * 0.58, height * 0.58), dark, 0.025)
                blade.rotation_euler[1] = angle
            cylinder("Main rotor mast", 0.12, height * 0.48, (0, -length * 0.02, height * 0.9), dark, 16)
            for angle in (0, math.pi / 2):
                blade = box("Main rotor blade", (width * 1.5, 0.22, 0.1),
                            (0, -length * 0.02, height * 1.13), dark, 0.045)
                blade.rotation_euler[2] = angle
            for x in (-width * 0.28, width * 0.28):
                for y in (-length * 0.18, length * 0.2):
                    cylinder("Helicopter landing skid", 0.07, length * 0.55,
                             (x, y, height * 0.17), dark, 12, (math.pi / 2, 0, 0))
        else:
            sphere("Aircraft fuselage", (width * 0.12, length * 0.49, height * 0.1),
                   (0, 0, height * 0.42), wall)
            box("Aircraft main wing", (width, length * 0.18, height * 0.055),
                (0, length * 0.03, height * 0.4), roof, 0.06)
            box("Aircraft tail plane", (width * 0.36, length * 0.08, height * 0.045),
                (0, length * 0.42, height * 0.45), roof, 0.04)
            box("Aircraft tail fin", (width * 0.06, length * 0.12, height * 0.28),
                (0, length * 0.42, height * 0.58), accent, 0.035)
            sphere("Aircraft cockpit", (width * 0.09, length * 0.08, height * 0.085),
                   (0, -length * 0.4, height * 0.46), glass)
            for side in (-1, 1):
                for index in range(5):
                    y = -length * 0.2 + index * length * 0.09
                    sphere("Aircraft cabin window", (0.045, 0.18, 0.08),
                           (side * width * 0.115, y, height * 0.48), glass)
                for y in (-length * 0.28, length * 0.2):
                    cylinder("Aircraft engine", width * 0.07, length * 0.22,
                             (side * width * 0.27, y, height * 0.32), dark, 24, (math.pi / 2, 0, 0))
                for y in (-length * 0.34, length * 0.31):
                    cylinder("Aircraft landing gear", 0.08, height * 0.27,
                             (side * width * 0.27, y, height * 0.16), dark, 12)
    elif family == "street":
        # street furniture: small pieces that dress a street between the buildings
        if style == "fence":
            posts = max(2, int(round(width / 1.6)) + 1)
            for index in range(posts):
                x = -width / 2 + width * index / (posts - 1)
                box("Fence post", (0.12, 0.12, height), (x, 0, height / 2), trunk, 0.01)
            for rail_z in (height * 0.38, height * 0.78):
                box("Fence rail", (width, 0.06, 0.14), (0, 0, rail_z), wall, 0.01)
        elif style == "shelter":
            leg = 0.1
            for sx in (-1, 1):
                for sy in (-1, 1):
                    box("Shelter post", (leg, leg, height),
                        (sx * (width / 2 - leg), sy * (length / 2 - leg), height / 2), dark, 0.01)
            box("Shelter roof", (width, length + 0.3, 0.12), (0, 0, height + 0.06), roof, 0.02)
            box("Shelter back", (width, 0.06, height * 0.78),
                (0, length / 2 - 0.05, height * 0.39 + 0.1), glass, 0.01)
            for sx in (-1, 1):                                          # a side panel each end
                box("Shelter side", (0.06, length, height * 0.7),
                    (sx * (width / 2 - 0.05), 0, height * 0.35 + 0.1), glass, 0.01)
            box("Shelter bench", (width * 0.8, 0.34, 0.08), (0, length * 0.18, 0.46), trim, 0.02)
            for sx in (-1, 1):
                box("Bench leg", (0.08, 0.3, 0.42), (sx * width * 0.32, length * 0.18, 0.21), dark, 0.01)
        elif style == "billboard":
            leg_h = height * 0.45
            for sx in (-1, 1):
                box("Billboard leg", (0.18, 0.18, leg_h), (sx * width * 0.3, 0, leg_h / 2), dark, 0.01)
            board_h = height - leg_h
            box("Billboard frame", (width, 0.16, board_h), (0, 0, leg_h + board_h / 2), wall, 0.02)
            box("Billboard face", (width * 0.96, 0.06, board_h * 0.9),
                (0, -0.1, leg_h + board_h / 2), white, 0.01)
        elif style == "fountain":
            radius = min(width, length) / 2
            cylinder("Fountain basin", radius, 0.55, (0, 0, 0.275), wall, 32)
            cylinder("Fountain water", radius * 0.86, 0.1, (0, 0, 0.5), glass, 32)
            cylinder("Fountain pedestal", radius * 0.3, height * 0.45, (0, 0, 0.55 + height * 0.22), wall, 24)
            cylinder("Fountain upper bowl", radius * 0.45, 0.16,
                     (0, 0, 0.55 + height * 0.45), wall, 24)
            sphere("Fountain finial", (radius * 0.12, radius * 0.12, radius * 0.12),
                   (0, 0, 0.72 + height * 0.45), accent)
    elif family == "road":
        sidewalk = 1.8
        road_width = width * 0.55
        road_length = length * 0.82
        box("Road verge", (width, length, 0.16), (0, 0, 0.08), green, 0.01)
        if style == "straight":
            box("Asphalt road", (road_width, road_length, 0.08), (0, 0, 0.2), asphalt, 0)
            for side in (-1, 1):
                x = side * (road_width / 2 + sidewalk / 2)
                box("Sidewalk", (sidewalk, road_length, 0.12), (x, 0, 0.22), trim, 0.02)
            lane_y = -road_length * 0.45
            while lane_y < road_length * 0.45:
                box("Dashed lane marking", (0.16, 1.8, 0.025), (0, lane_y, 0.255), paint, 0)
                lane_y += 3.6
        elif style == "curve":
            road_width = min(width, length) * 0.3
            radius = min(width, length) * 0.25
            center_x, center_y = radius, -radius
            vertical_length = max(0.1, length / 2 - radius)
            horizontal_length = max(0.1, width / 2 - radius)
            box("Curved road vertical approach", (road_width, vertical_length + road_width, 0.08),
                (0, -length / 2 + (vertical_length + road_width) / 2, 0.2), asphalt, 0)
            box("Curved road horizontal exit", (horizontal_length + road_width, road_width, 0.08),
                (width / 2 - (horizontal_length + road_width) / 2, 0, 0.2), asphalt, 0)

            def curved_strip(name, center_radius, strip_width, material, z):
                segments = 32
                outer_radius = center_radius + strip_width / 2
                inner_radius = max(0.1, center_radius - strip_width / 2)
                angles = [math.pi - index * math.pi / (2 * segments) for index in range(segments + 1)]
                vertices = [
                    (center_x + outer_radius * math.cos(angle), center_y + outer_radius * math.sin(angle), z)
                    for angle in angles
                ]
                vertices.extend(
                    (center_x + inner_radius * math.cos(angle), center_y + inner_radius * math.sin(angle), z)
                    for angle in reversed(angles)
                )
                mesh = bpy.data.meshes.new(name)
                mesh.from_pydata(vertices, [], [tuple(range(len(vertices)))])
                mesh.materials.append(material)
                obj = bpy.data.objects.new(name, mesh)
                scene.collection.objects.link(obj)
                return obj

            curved_strip("Curved asphalt", radius, road_width, asphalt, 0.24)
            for side in (-1, 1):
                path_radius = radius + side * (road_width / 2 + sidewalk / 2)
                curved_strip("Curved sidewalk", path_radius, sidewalk, trim, 0.28)
                box("Approach sidewalk", (sidewalk, vertical_length + 1.0, 0.12),
                    (side * (road_width / 2 + sidewalk / 2), -length / 2 + vertical_length / 2, 0.22),
                    trim, 0.02)
                box("Exit sidewalk", (horizontal_length + 1.0, sidewalk, 0.12),
                    (radius + horizontal_length / 2, side * (road_width / 2 + sidewalk / 2), 0.22),
                    trim, 0.02)
            for index in range(9):
                angle = math.pi - (index + 0.5) * math.pi / 9
                dash = box("Curved lane marking", (0.16, 1.5, 0.025),
                           (center_x + radius * math.cos(angle),
                            center_y + radius * math.sin(angle), 0.27), paint, 0)
                dash.rotation_euler[2] = angle - math.pi / 2
        else:
            # Junction modules are assembled from two conventional street runs.
            horizontal_length = width * 0.9
            vertical_length = length * 0.9
            box("Horizontal asphalt", (horizontal_length, road_width, 0.08), (0, 0, 0.2), asphalt, 0)
            if style != "t_junction":
                box("Vertical asphalt", (road_width, vertical_length, 0.08), (0, 0, 0.2), asphalt, 0)
            for side in (-1, 1):
                box("Horizontal sidewalk", (horizontal_length, sidewalk, 0.12),
                    (0, side * (road_width / 2 + sidewalk / 2), 0.22), trim, 0.02)
                if style != "t_junction" or side == 1:
                    box("Vertical sidewalk", (sidewalk, vertical_length, 0.12),
                        (side * (road_width / 2 + sidewalk / 2), 0, 0.22), trim, 0.02)
            for index in range(5):
                offset = (index - 2) * 1.2
                box("Intersection lane marking", (0.18, 2.0, 0.025), (offset, 0, 0.255), paint, 0)
                box("Intersection lane marking", (2.0, 0.18, 0.025), (0, offset, 0.255), paint, 0)
    return True
