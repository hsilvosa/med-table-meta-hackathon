"""Blender scene generator: boxes with a Data Matrix label on a table, photographed like a phone from a given height.

  "C:/Program Files/Blender Foundation/Blender 4.5/blender.exe" --background --python scripts/blender_scene.py -- \
      OUT_DIR LABELS_DIR --scenes 6 --camera-height 0.45 --seed 1 --width 4000 --height-px 3000 --glossy 0.25

LABELS_DIR comes from scripts/make_label_textures.py. For each scene it writes OUT_DIR/scene_<i>.png and, at the end,
OUT_DIR/truth.json {scene file: [element strings that are visible by construction]}.
Boxes are 12 x 7 x 4 cm with a 12 mm code (plus quiet zone) on the top face, random pose, one area light (the glossy
surface gives glare). The camera is a phone-like lens (about 71 degrees across) looking down from --camera-height
metres, with a random tilt of up to 20 degrees. Synthetic stress test only: it shows how pixels per module, tilt and
glare affect decoding, not how real printed codes on curved cardboard behave. Pure bpy: no third-party modules needed.
"""

import json
import math
import random
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
out_dir, labels_dir = Path(argv[0]).resolve(), Path(argv[1]).resolve()
opts = dict(zip(argv[2::2], argv[3::2]))
scenes, cam_height, seed = int(opts.get("--scenes", 4)), float(opts.get("--camera-height", 0.45)), int(opts.get("--seed", 1))
res_x, res_y = int(opts.get("--width", 4000)), int(opts.get("--height-px", 3000))
glossy = float(opts.get("--glossy", 0.25))
rng = random.Random(seed)
out_dir.mkdir(parents=True, exist_ok=True)
labels = json.loads((labels_dir / "labels.json").read_text(encoding="utf-8"))
label_files = sorted(labels)


def engine_name() -> str:
    names = {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
    return "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in names else "BLENDER_EEVEE"


def material(name, color=None, image=None, roughness=0.6):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = roughness
    if image:
        tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(str(image))
        tex.interpolation = "Closest"
        mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    else:
        bsdf.inputs["Base Color"].default_value = color
    return mat


def render_scene(index: int, files: list[str]) -> list[str]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = engine_name()
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = res_x, res_y, 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "Standard"
    scene.world = bpy.data.worlds.new("world")
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes["Background"]
    background.inputs[0].default_value, background.inputs[1].default_value = (0.8, 0.8, 0.8, 1), 0.25

    bpy.ops.mesh.primitive_plane_add(size=1.4, location=(0, 0, 0))
    bpy.context.active_object.data.materials.append(material("wood", (0.45, 0.3, 0.18, 1), roughness=0.7))
    placed = []
    for k, name in enumerate(files):
        for _ in range(60):  # rejection sampling so boxes do not overlap
            x, y, rot = rng.uniform(-0.2, 0.2), rng.uniform(-0.13, 0.13), rng.uniform(0, 2 * math.pi)
            if all(math.hypot(x - px, y - py) > 0.14 for px, py in placed):
                break
        placed.append((x, y))
        bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, 0.02))
        box = bpy.context.active_object
        box.scale, box.rotation_euler[2] = (0.12, 0.07, 0.04), rot
        box.data.materials.append(material(f"card{k}", (rng.uniform(0.75, 0.95), rng.uniform(0.75, 0.95), rng.uniform(0.7, 0.95), 1), roughness=glossy))
        bpy.ops.mesh.primitive_plane_add(size=0.012 * (1 + 8 / 22), location=(x, y, 0.0402))  # 12 mm code plus quiet zone
        tag = bpy.context.active_object
        tag.rotation_euler[2] = rot
        tag.data.materials.append(material(f"label{k}", image=labels_dir / name, roughness=glossy))

    light = bpy.data.objects.new("light", bpy.data.lights.new("l", "AREA"))
    light.data.energy, light.data.size = rng.uniform(2, 6), 0.3
    light.location = (rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), rng.uniform(0.4, 0.7))
    bpy.context.collection.objects.link(light)
    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens, cam_data.sensor_width = 6.9, 9.8
    cam = bpy.data.objects.new("cam", cam_data)
    bpy.context.collection.objects.link(cam)
    tilt = math.radians(rng.uniform(0, 20))
    cam.location = (rng.uniform(-0.03, 0.03), rng.uniform(-0.03, 0.03) - math.sin(tilt) * cam_height * 0.5, cam_height)
    cam.rotation_euler = (tilt, 0, rng.uniform(-0.3, 0.3))
    scene.camera = cam
    scene.render.filepath = str(out_dir / f"scene_{index}.png")
    bpy.ops.render.render(write_still=True)
    visible = []  # only labels whose centre falls inside the frame (with a 3% margin) count as photographed
    for (x, y), name in zip(placed, files):
        u, v, _ = world_to_camera_view(scene, cam, Vector((x, y, 0.0402)))
        if 0.03 < u < 0.97 and 0.03 < v < 0.97:
            visible.append(labels[name])
    return visible


truth = {}
for i in range(scenes):
    chosen = rng.sample(label_files, rng.randint(5, 7))
    truth[f"scene_{i}.png"] = render_scene(i, chosen)
    print(f"scene {i} done", flush=True)
(out_dir / "truth.json").write_text(json.dumps(truth, indent=1), encoding="utf-8")
