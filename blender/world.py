"""Light and weather for a CastForge scene: lighting moods matched to the set picture, falling snow or rain, fog,
and the flicker of fire-lit props. scene_kit.py calls these; the mood presets live in core/schema.py (LIGHTING).

The set picture keeps its own lighting (it is drawn as it is, see scene_kit.image_material); these lights shape
the cast and the props, and the sun casts their shadows onto the set. In a dark picture the lights are dimmer
(auto exposure), so characters sit in the picture instead of glowing in front of it.
"""
import math

import bpy
from mathutils import Vector

from core import schema

REFERENCE = 0.35                     # mean picture luminance at which lights have their nominal strength
NOMINAL = {"key": 170.0, "rim": 140.0, "fill": 50.0}       # area light watts (v1's cinematic lights)
CLASSIC = {"key": (1.0, (1.0, 0.93, 0.85)), "rim": (1.0, (0.85, 0.92, 1.0)), "fill": (1.0, (0.95, 0.9, 0.85)),
           "world": (1.0, (1.0, 1.0, 1.0)), "sun": (3.0, (1.0, 0.95, 0.88))}


def picture_stats(img):
    """Mean luminance (of the stored sRGB values) and mean colour of a picture, from a sample of its pixels."""
    import numpy as np
    px = np.empty(len(img.pixels), np.float32)
    img.pixels.foreach_get(px)
    rgb = px.reshape(-1, 4)[::5, :3]
    return float((rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32)).mean()), [float(c) for c in rgb.mean(axis=0)]


def exposure(luminance):
    return min(max((luminance / REFERENCE) ** 0.8, 0.3), 1.4)


def mood(name, luminance, picture_rgb):
    """The scene's lights as numbers: {"key"|"rim"|"fill": (watts, colour), "world": (strength, colour),
    "sun": (strength, colour)}. "classic" is v1 (fixed strengths); everything else follows the picture."""
    tint = [c / max(max(picture_rgb), 1e-3) for c in picture_rgb]          # the picture's own colour cast
    preset = schema.LIGHTING.get(name) or CLASSIC
    scale = 1.0 if name == "classic" else exposure(luminance)
    out = {k: (NOMINAL[k] * preset[k][0] * scale, preset[k][1]) for k in NOMINAL}
    world_colour = [t * c for t, c in zip(tint, preset["world"][1])]
    out["world"] = (0.245 * preset["world"][0] * scale, world_colour)
    out["sun"] = (preset["sun"][0] * scale, preset["sun"][1])
    return out


def luminance(colour):
    return 0.2126 * colour[0] + 0.7152 * colour[1] + 0.0722 * colour[2]


def cinematic_lights(scene, centre, camera_location, receivers, m):
    """Film-style light on the cast: a big soft key from the camera side, a rim from behind, a low fill.
    Light linking keeps them off the set picture."""
    to_cam = Vector(camera_location) - centre
    to_cam.z = 0
    to_cam.normalize()
    side = to_cam.cross(Vector((0, 0, 1)))
    for name, offset, size in (("Key", to_cam * 3.0 + side * 2.0 + Vector((0, 0, 1.2)), 2.5),
                               ("Rim", -to_cam * 3.0 - side * 1.0 + Vector((0, 0, 1.6)), 2.0),
                               ("Fill", to_cam * 3.0 - side * 2.5 + Vector((0, 0, 0.3)), 3.0)):
        energy, colour = m[name.lower()]
        light = bpy.data.objects.new(name, bpy.data.lights.new(name, "AREA"))
        light.data.size, light.data.energy, light.data.color = size, energy, colour
        light.location = centre + offset
        light.rotation_euler = (centre - light.location).to_track_quat("-Z", "Y").to_euler()
        scene.collection.objects.link(light)
        light.light_linking.receiver_collection = receivers


def flicker(lights, frame_end, fps, rng):
    """Fire and candle light: energy keyed every two frames from a smooth sum of sines (random phases)."""
    for light in lights:
        base = light.data.energy
        phases = [rng.uniform(0, 2 * math.pi) for _ in range(3)]
        for f in range(1, frame_end + 1, 2):
            t = f / fps
            k = (1 + 0.16 * math.sin(2 * math.pi * 1.7 * t + phases[0]) + 0.09 * math.sin(2 * math.pi * 4.3 * t + phases[1])
                 + 0.05 * math.sin(2 * math.pi * 9.7 * t + phases[2]))
            light.data.energy = base * k
            light.data.keyframe_insert("energy", frame=f)
        light.data.energy = base


def _material(name, colour, emission, alpha=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*colour, 1)
    b.inputs["Roughness"].default_value = 0.6
    b.inputs["Emission Color"].default_value = (*colour, 1)
    b.inputs["Emission Strength"].default_value = emission
    if alpha < 1.0:
        b.inputs["Alpha"].default_value = alpha
        if hasattr(m, "surface_render_method"):
            m.surface_render_method = "DITHERED"
    return m


def add_fog(scene, amount, colour):
    """A thin world volume. Its range covers the far backdrop too, so no clear band shows behind the set."""
    nt = scene.world.node_tree
    vol = nt.nodes.new("ShaderNodeVolumePrincipled")
    vol.inputs["Density"].default_value = 0.004 + 0.035 * amount
    vol.inputs["Color"].default_value = (*colour, 1)
    vol.inputs["Anisotropy"].default_value = 0.3
    out = next(n for n in nt.nodes if n.type == "OUTPUT_WORLD")
    nt.links.new(vol.outputs[0], out.inputs["Volume"])
    e = scene.eevee
    e.volumetric_end = 150.0
    e.volumetric_tile_size = "8"
    e.volumetric_samples = 48


def weather(scene, cam, spec, frame_end, fps, fast, seed, fog_colour):
    """Falling snow or rain between the camera and the set, already falling at frame 1; optional fog.
    spec: "snow" | "rain" | {"type", "amount" 0..1, "wind" -1..1, "fog" 0..1}. Returns a log line or None."""
    if not spec:
        return None
    if isinstance(spec, str):
        spec = {"type": spec}
    kind = spec.get("type")
    amount = min(max(float(spec.get("amount", 0.5)), 0.0), 1.0)
    wind = min(max(float(spec.get("wind", 0.2)), -1.0), 1.0)
    fog = min(max(float(spec.get("fog", 0.0)), 0.0), 1.0)
    if fog:
        add_fog(scene, fog, fog_colour)
    if kind not in ("snow", "rain"):
        return f"fog {fog:.2f}" if fog else None
    snow = kind == "snow"
    forward = cam.matrix_world.to_3x3() @ Vector((0, 0, -1))
    forward.z = 0
    forward.normalize()
    top, speed = (5.0, 1.1) if snow else (6.0, 8.0)
    centre = Vector(cam.location) + forward * 7.0
    bpy.ops.mesh.primitive_plane_add(size=1, location=(centre.x, centre.y, top),
                                     rotation=(0, 0, math.atan2(forward.y, forward.x) - math.pi / 2))
    emitter = bpy.context.object
    emitter.name = f"Weather_{kind}"
    emitter.scale = (14, 14, 1)
    # the particle: a small flake, or a thin streak along X (rain particles turn their X along their motion)
    if snow:
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.008, location=(0, 0, -500))
        drop = bpy.context.object
        drop.data.materials.append(_material("snowflake", (0.95, 0.97, 1.0), 0.25))
    else:
        bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.0012, depth=0.22, location=(0, 0, -500),
                                            rotation=(0, math.pi / 2, 0))
        drop = bpy.context.object
        bpy.ops.object.transform_apply(rotation=True)
        drop.data.materials.append(_material("raindrop", (0.75, 0.8, 0.88), 0.15, alpha=0.45))
    drop.name = f"{kind}_drop"
    emitter.modifiers.new("weather", "PARTICLE_SYSTEM")
    psys = emitter.particle_systems[0]
    psys.seed = seed
    s = psys.settings
    life = int((top + 0.5) / speed * fps) + 2
    rate = (2200 if snow else 3500) * amount * (0.3 if fast else 1.0)          # particles per second
    s.count = max(1, min(int(rate * (frame_end + life) / fps), 60000))
    s.frame_start, s.frame_end, s.lifetime = -life, frame_end, life
    s.emit_from, s.use_emit_random, s.normal_factor = "FACE", True, 0.0
    s.object_align_factor = (wind * speed * (0.6 if snow else 0.15), 0.0, -speed)
    s.factor_random = 0.15 if snow else 0.05
    s.effector_weights.gravity = 0.0
    s.brownian_factor = 0.35 if snow else 0.0
    s.render_type, s.instance_object = "OBJECT", drop
    s.particle_size, s.size_random = 1.0, (0.6 if snow else 0.3)
    s.use_rotations = not snow
    if not snow:
        s.rotation_mode = "VEL"
    psys.point_cache.frame_start, psys.point_cache.frame_end = int(s.frame_start), int(frame_end)
    emitter.show_instancer_for_render = emitter.show_instancer_for_viewport = False
    return f"{kind}: {s.count} particles" + (f", fog {fog:.2f}" if fog else "")
