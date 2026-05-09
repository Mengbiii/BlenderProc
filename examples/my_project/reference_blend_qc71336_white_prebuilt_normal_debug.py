import blenderproc as bproc
import argparse
import json
import math
import random
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

BASELINE_VERSION = "qc71336_white_prebuilt_reference_baseline_v2"
BASELINE_SUMMARY = (
    "QC7-1336 white prebuilt-material normal-part baseline in moxing2.blend with a cleaned direct-model workflow, "
    "a more front-facing camera angle, and the manually authored materials from QC7-1336-white.blend."
)
BLACK_DOT_VERSION = "qc71336_white_prebuilt_black_dot_v1"
FOREIGN_MATERIAL_VERSION = "qc71336_white_prebuilt_foreign_material_v3"
MODEL_OBJECT_KEYWORDS = ("QC8-8511-000N301002ST0101",)
FOREIGN_MATERIAL_VISIBLE_RADIUS_FLOOR = 0.0058
FOREIGN_MATERIAL_VISIBLE_RADIUS_CEILING = 0.0088
GRAY_BASE_RGBA = (0.445, 0.438, 0.432, 1.0)
GRAY_SUBSURFACE_RGBA = (0.382, 0.376, 0.372, 1.0)
WHITE_REAL_DOMAIN_COLOR_SCALE = (0.95, 0.94, 0.93)
WHITE_TEXTURED_PROFILE = {
    "fine_noise_scale": 300.0,
    "fine_noise_detail": 14.0,
    "fine_noise_roughness": 0.66,
    "bump_strength": 0.0120,
    "bump_distance": 0.0040,
    "roughness_low": 0.68,
    "roughness_high": 0.98,
    "base_low": (0.500, 0.510, 0.495, 1.0),
    "base_high": (0.705, 0.715, 0.695, 1.0),
    "broad_noise_scale": 28.0,
    "broad_noise_detail": 8.0,
    "broad_bump_strength": 0.0020,
    "broad_bump_distance": 0.0080,
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Render one QC7-1336 white prebuilt-material normal reference-scene image in moxing2.blend."
    )
    parser.add_argument("--blend", required=True)
    parser.add_argument("--model_blend", default=r"E:\BlenderProject\BlenderProc\assets\models\QC7-1336-white.blend")
    parser.add_argument("--output", required=True)
    parser.add_argument("--num", type=int, default=1)
    parser.add_argument("--start_index", type=int, default=0)
    parser.add_argument("--width", type=int, default=1536)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--samples", type=int, default=256)
    parser.add_argument("--save_blend", action="store_true")
    parser.add_argument("--use_gray_override", action="store_true")
    parser.add_argument(
        "--disable_white_texture_enhancement",
        action="store_true",
        help="Keep the previous white prebuilt material tuning without adding texture-driven roughness/bump nodes.",
    )
    parser.add_argument("--enable_black_dot", action="store_true")
    parser.add_argument("--black_dot_seed", type=int, default=23)
    parser.add_argument("--black_dot_radius_scale", type=float, default=0.00190)
    parser.add_argument("--black_dot_depth_scale", type=float, default=0.00070)
    parser.add_argument("--enable_foreign_material", action="store_true")
    parser.add_argument("--foreign_material_seed", type=int, default=23)
    parser.add_argument("--foreign_material_radius_scale", type=float, default=0.0)
    parser.add_argument("--foreign_material_depth_scale", type=float, default=0.0)
    parser.add_argument("--defect_count_min", type=int, default=1)
    parser.add_argument("--defect_count_max", type=int, default=1)
    parser.add_argument("--anchor_sides", nargs="+", choices=["front", "back"], default=["front"])
    parser.add_argument("--object_transform_mode", choices=["none", "keep_camera"], default="none")
    parser.add_argument("--object_transform_camera_side", choices=["front", "back"], default="front")
    parser.add_argument("--object_rotate_deg", nargs=3, type=float, default=None, metavar=("RX", "RY", "RZ"))
    parser.add_argument("--object_translate", nargs=3, type=float, default=[0.0, 0.0, 0.0], metavar=("X", "Y", "Z"))
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = argv[1:]
    return parser.parse_args(argv)


def mkdir(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def bbox_to_yolo(scene, bbox):
    width = float(scene.render.resolution_x)
    height = float(scene.render.resolution_y)
    x, y, bw_px, bh_px = bbox["xywh"]
    xc = (x + bw_px * 0.5) / width
    yc = (y + bh_px * 0.5) / height
    bw = bw_px / width
    bh = bh_px / height
    return xc, yc, bw, bh


def get_mesh_objects():
    return [obj for obj in bpy.data.objects if obj.type == "MESH"]


def world_bbox(objects):
    corners = []
    for obj in objects:
        corners.extend([obj.matrix_world @ Vector(corner) for corner in obj.bound_box])
    mins = Vector((min(v.x for v in corners), min(v.y for v in corners), min(v.z for v in corners)))
    maxs = Vector((max(v.x for v in corners), max(v.y for v in corners), max(v.z for v in corners)))
    return mins, maxs


def object_bbox_dims(obj):
    bb_min, bb_max = world_bbox([obj])
    return bb_min, bb_max, bb_max - bb_min


def is_background_like(obj):
    name = obj.name.lower()
    if any(token in name for token in ["plane", "floor", "table", "background", "backdrop", "wall"]):
        return True
    _, _, dims = object_bbox_dims(obj)
    dims_sorted = sorted([abs(dims.x), abs(dims.y), abs(dims.z)])
    if dims_sorted[-1] <= 0:
        return False
    return dims_sorted[0] < 0.03 * dims_sorted[-1] and dims_sorted[1] > 0.4 * dims_sorted[-1]


def pick_primary_mesh_objects():
    meshes = get_mesh_objects()
    candidates = [obj for obj in meshes if not is_background_like(obj)]
    if not candidates:
        return meshes

    def score(obj):
        _, _, dims = object_bbox_dims(obj)
        volume = max(float(dims.x), 1e-6) * max(float(dims.y), 1e-6) * max(float(dims.z), 1e-6)
        return (volume, len(obj.data.vertices))

    candidates.sort(key=score, reverse=True)
    top_score = score(candidates[0])[0]
    return [obj for obj in candidates if score(obj)[0] >= top_score * 0.15]


def ensure_camera_for_objects(objects, width, height):
    bb_min, bb_max = world_bbox(objects)
    center = (bb_min + bb_max) * 0.5
    span = bb_max - bb_min
    max_dim = max(float(abs(span.x)), float(abs(span.y)), float(abs(span.z)), 1e-3)

    camera = bpy.data.objects.get("REFERENCE_DEBUG_CAMERA")
    if camera is None:
        cam_data = bpy.data.cameras.new("REFERENCE_DEBUG_CAMERA")
        camera = bpy.data.objects.new("REFERENCE_DEBUG_CAMERA", cam_data)
        bpy.context.scene.collection.objects.link(camera)

    scene = bpy.context.scene
    scene.camera = camera
    camera.data.type = "PERSP"
    camera.data.lens = 82.0
    camera.data.sensor_width = 36.0
    camera.data.sensor_fit = "HORIZONTAL"
    camera.data.clip_start = 0.01
    camera.data.clip_end = 1000.0
    camera.data.shift_x = 0.0
    camera.data.shift_y = 0.085

    location = center + Vector((0.0, -0.16 * max_dim, 2.72 * max_dim))
    direction = center - location
    rot_quat = direction.to_track_quat("-Z", "Y")
    camera.location = location
    camera.rotation_euler = rot_quat.to_euler()

    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    bpy.context.view_layer.update()
    return camera


def configure_cycles_gpu(samples):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.device = "GPU"

    prefs = bpy.context.preferences
    cycles_pref = prefs.addons["cycles"].preferences
    device_types = ["OPTIX", "CUDA"]
    selected_type = None
    for device_type in device_types:
        try:
            cycles_pref.compute_device_type = device_type
            cycles_pref.get_devices()
            if any(d.type != "CPU" for d in cycles_pref.devices):
                selected_type = device_type
                break
        except Exception:
            continue

    if selected_type is None:
        try:
            cycles_pref.get_devices()
        except Exception:
            pass

    enabled_devices = []
    for device in cycles_pref.devices:
        use = device.type != "CPU"
        device.use = use
        if use:
            enabled_devices.append({"name": device.name, "type": device.type})

    return {
        "render_engine": scene.render.engine,
        "cycles_device": scene.cycles.device,
        "compute_device_type": selected_type or str(getattr(cycles_pref, "compute_device_type", "UNKNOWN")),
        "enabled_devices": enabled_devices,
    }


def ensure_background_support():
    existing = bpy.data.objects.get("REFERENCE_DEBUG_BACKDROP")
    if existing is not None:
        return existing
    bpy.ops.mesh.primitive_plane_add(size=20.0, location=(0.0, 0.0, -0.15))
    plane = bpy.context.active_object
    plane.name = "REFERENCE_DEBUG_BACKDROP"
    plane.scale = (2.5, 2.5, 1.0)
    mat = bpy.data.materials.new("REFERENCE_DEBUG_BACKDROP_MAT")
    mat.use_nodes = True
    bsdf = find_principled(mat)
    bsdf.inputs["Base Color"].default_value = (0.82, 0.825, 0.83, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.84
    spec_name = "Specular IOR Level" if "Specular IOR Level" in bsdf.inputs else "Specular"
    bsdf.inputs[spec_name].default_value = 0.08
    plane.data.materials.clear()
    plane.data.materials.append(mat)
    bpy.context.view_layer.update()
    return plane


def tune_reference_lighting_for_white():
    scene = bpy.context.scene
    energy_scale_map = {
        "Area": 0.065,
        "Area.001": 0.060,
        "Area.002": 0.055,
        "Area.003": 0.24,
        "Area.004": 0.045,
        "Area.005": 0.115,
    }
    warm_lights = {"Area.003", "Area.005"}
    cool_lights = {"Area", "Area.001", "Area.002", "Area.004"}

    for obj in bpy.data.objects:
        if obj.type != "LIGHT":
            continue
        light = obj.data
        scale = energy_scale_map.get(obj.name, 0.22)
        if getattr(light, "color", None) is not None:
            if obj.name in warm_lights:
                light.color = (1.0, 0.975, 0.944)
            elif obj.name in cool_lights:
                light.color = (0.982, 0.965, 0.948)
            else:
                light.color = (0.992, 0.975, 0.956)
        if hasattr(light, "energy") and light.energy is not None:
            light.energy = float(light.energy) * scale
        if light.type == "AREA":
            if obj.name in warm_lights:
                if hasattr(light, "size"):
                    light.size = float(light.size) * 0.75
                if hasattr(light, "size_y"):
                    light.size_y = float(light.size_y) * 0.75
            else:
                if hasattr(light, "size"):
                    light.size = float(light.size) * 1.04
                if hasattr(light, "size_y"):
                    light.size_y = float(light.size_y) * 1.04

    world = scene.world
    if world and world.use_nodes and world.node_tree:
        for node in world.node_tree.nodes:
            if node.type == "BACKGROUND":
                color_input = node.inputs.get("Color")
                strength_input = node.inputs.get("Strength")
                if color_input is not None:
                    color_input.default_value = (0.705, 0.697, 0.686, 1.0)
                if strength_input is not None:
                    strength_input.default_value = min(float(strength_input.default_value), 0.008)
    scene.view_settings.exposure = -0.72
    try:
        scene.view_settings.look = "Medium High Contrast"
    except Exception:
        try:
            scene.view_settings.look = "Medium Contrast"
        except Exception:
            pass
    bpy.context.view_layer.update()


def import_stl(path):
    before = {obj.name for obj in bpy.data.objects}
    try:
        bpy.ops.wm.stl_import(filepath=str(path))
    except Exception:
        bpy.ops.import_mesh.stl(filepath=str(path))
    after = [obj for obj in bpy.data.objects if obj.name not in before and obj.type == "MESH"]
    if not after:
        raise RuntimeError(f"Failed to import STL: {path}")
    return after


def append_blend_objects(path):
    path = Path(path)
    before_names = set(bpy.data.objects.keys())
    with bpy.data.libraries.load(str(path), link=False) as (data_from, data_to):
        data_to.objects = [name for name in data_from.objects if name]

    loaded_objects = [obj for obj in data_to.objects if obj is not None]
    if not loaded_objects:
        raise RuntimeError(f"No objects found in blend model: {path}")

    scene_collection = bpy.context.scene.collection
    for obj in loaded_objects:
        if obj.name not in scene_collection.objects:
            scene_collection.objects.link(obj)

    mesh_objects = [obj for obj in loaded_objects if obj.type == "MESH"]
    filtered_mesh_objects = [
        obj for obj in mesh_objects
        if any(keyword in obj.name for keyword in MODEL_OBJECT_KEYWORDS)
    ]
    if filtered_mesh_objects:
        keep_names = {obj.name for obj in filtered_mesh_objects}
        for obj in loaded_objects:
            if obj.type == "MESH" and obj.name not in keep_names:
                obj.hide_render = True
                obj.hide_viewport = True
        mesh_objects = filtered_mesh_objects
    if not mesh_objects:
        new_names = [name for name in bpy.data.objects.keys() if name not in before_names]
        raise RuntimeError(f"No mesh objects appended from blend model: {path}. Loaded objects: {new_names}")

    bpy.context.view_layer.update()
    return mesh_objects


def summarize_existing_materials(imported_objects):
    summary = {}
    for obj in imported_objects:
        mat_names = [mat.name for mat in obj.data.materials if mat is not None]
        summary[obj.name] = mat_names
    return summary


def tune_prebuilt_white_materials_for_real_domain(imported_objects):
    tuned = {}
    for obj in imported_objects:
        if obj.type != "MESH":
            continue
        for mat in obj.data.materials:
            if mat is None or mat.name in tuned:
                continue
            bsdf = find_principled(mat)
            if bsdf is None:
                continue

            base_input = bsdf.inputs.get("Base Color")
            if base_input is not None:
                old = tuple(float(v) for v in base_input.default_value)
                new_color = (
                    min(old[0] * WHITE_REAL_DOMAIN_COLOR_SCALE[0], 1.0),
                    min(old[1] * WHITE_REAL_DOMAIN_COLOR_SCALE[1], 1.0),
                    min(old[2] * WHITE_REAL_DOMAIN_COLOR_SCALE[2], 1.0),
                    old[3],
                )
                base_input.default_value = new_color
            else:
                old = None
                new_color = None

            roughness_input = bsdf.inputs.get("Roughness")
            if roughness_input is not None:
                roughness_input.default_value = min(float(roughness_input.default_value) + 0.12, 0.96)

            spec_name = "Specular IOR Level" if "Specular IOR Level" in bsdf.inputs else "Specular"
            spec_input = bsdf.inputs.get(spec_name)
            if spec_input is not None:
                spec_input.default_value = float(spec_input.default_value) * 0.58

            tuned[mat.name] = {
                "old_base_color": old,
                "new_base_color": tuple(float(v) for v in new_color) if new_color is not None else None,
                "roughness": float(roughness_input.default_value) if roughness_input is not None else None,
                "specular": float(spec_input.default_value) if spec_input is not None else None,
            }
    bpy.context.view_layer.update()
    return tuned


def clear_socket_links(tree, socket):
    for link in list(socket.links):
        tree.links.remove(link)


def enhance_prebuilt_white_materials_with_texture(imported_objects):
    enhanced = {}
    profile = WHITE_TEXTURED_PROFILE
    for obj in imported_objects:
        if obj.type != "MESH":
            continue
        for mat in obj.data.materials:
            if mat is None or mat.name in enhanced:
                continue
            if not mat.use_nodes or mat.node_tree is None:
                continue
            bsdf = find_principled(mat)
            if bsdf is None:
                continue

            tree = mat.node_tree
            nodes = tree.nodes
            links = tree.links

            base_input = bsdf.inputs.get("Base Color")
            roughness_input = bsdf.inputs.get("Roughness")
            normal_input = bsdf.inputs.get("Normal")
            if base_input is None or roughness_input is None or normal_input is None:
                continue

            spec_name = "Specular IOR Level" if "Specular IOR Level" in bsdf.inputs else "Specular"
            spec_input = bsdf.inputs.get(spec_name)
            if spec_input is not None:
                spec_input.default_value = min(float(spec_input.default_value), 0.18)

            clear_socket_links(tree, base_input)
            clear_socket_links(tree, roughness_input)
            clear_socket_links(tree, normal_input)

            texcoord = nodes.new("ShaderNodeTexCoord")
            texcoord.label = "WHITE_TEXTURE_OBJECT_COORDS"
            fine_mapping = nodes.new("ShaderNodeMapping")
            fine_mapping.label = "WHITE_TEXTURE_FINE_MAPPING"
            fine_noise = nodes.new("ShaderNodeTexNoise")
            fine_noise.label = "WHITE_TEXTURE_FINE_GRAIN_NOISE"
            rough_ramp = nodes.new("ShaderNodeValToRGB")
            rough_ramp.label = "WHITE_TEXTURE_ROUGHNESS_VARIATION"
            base_ramp = nodes.new("ShaderNodeValToRGB")
            base_ramp.label = "WHITE_TEXTURE_SUBTLE_COLOR_VARIATION"
            fine_bump = nodes.new("ShaderNodeBump")
            fine_bump.label = "WHITE_TEXTURE_FINE_GRAIN_BUMP"

            broad_mapping = nodes.new("ShaderNodeMapping")
            broad_mapping.label = "WHITE_TEXTURE_BROAD_MAPPING"
            broad_noise = nodes.new("ShaderNodeTexNoise")
            broad_noise.label = "WHITE_TEXTURE_BROAD_MOLD_FLOW_NOISE"
            broad_bump = nodes.new("ShaderNodeBump")
            broad_bump.label = "WHITE_TEXTURE_BROAD_MOLD_FLOW_BUMP"

            fine_mapping.inputs["Scale"].default_value = (
                profile["fine_noise_scale"],
                profile["fine_noise_scale"],
                profile["fine_noise_scale"],
            )
            fine_noise.inputs["Scale"].default_value = 1.0
            fine_noise.inputs["Detail"].default_value = profile["fine_noise_detail"]
            fine_noise.inputs["Roughness"].default_value = profile["fine_noise_roughness"]

            rough_ramp.color_ramp.elements[0].position = 0.24
            rough_ramp.color_ramp.elements[0].color = (
                profile["roughness_low"],
                profile["roughness_low"],
                profile["roughness_low"],
                1.0,
            )
            rough_ramp.color_ramp.elements[1].position = 0.82
            rough_ramp.color_ramp.elements[1].color = (
                profile["roughness_high"],
                profile["roughness_high"],
                profile["roughness_high"],
                1.0,
            )

            base_ramp.color_ramp.elements[0].position = 0.18
            base_ramp.color_ramp.elements[0].color = profile["base_low"]
            base_ramp.color_ramp.elements[1].position = 0.86
            base_ramp.color_ramp.elements[1].color = profile["base_high"]

            fine_bump.inputs["Strength"].default_value = profile["bump_strength"]
            fine_bump.inputs["Distance"].default_value = profile["bump_distance"]

            broad_mapping.inputs["Scale"].default_value = (
                profile["broad_noise_scale"],
                profile["broad_noise_scale"],
                profile["broad_noise_scale"],
            )
            broad_noise.inputs["Scale"].default_value = 1.0
            broad_noise.inputs["Detail"].default_value = profile["broad_noise_detail"]
            broad_noise.inputs["Roughness"].default_value = 0.55
            broad_bump.inputs["Strength"].default_value = profile["broad_bump_strength"]
            broad_bump.inputs["Distance"].default_value = profile["broad_bump_distance"]

            links.new(texcoord.outputs["Object"], fine_mapping.inputs["Vector"])
            links.new(fine_mapping.outputs["Vector"], fine_noise.inputs["Vector"])
            links.new(fine_noise.outputs["Fac"], rough_ramp.inputs["Fac"])
            links.new(fine_noise.outputs["Fac"], base_ramp.inputs["Fac"])
            links.new(rough_ramp.outputs["Color"], roughness_input)
            links.new(base_ramp.outputs["Color"], base_input)

            links.new(texcoord.outputs["Object"], broad_mapping.inputs["Vector"])
            links.new(broad_mapping.outputs["Vector"], broad_noise.inputs["Vector"])
            links.new(broad_noise.outputs["Fac"], broad_bump.inputs["Height"])
            links.new(broad_bump.outputs["Normal"], fine_bump.inputs["Normal"])
            links.new(fine_noise.outputs["Fac"], fine_bump.inputs["Height"])
            links.new(fine_bump.outputs["Normal"], normal_input)

            mat["qc71336_white_texture_profile"] = json.dumps(profile, ensure_ascii=False)
            enhanced[mat.name] = {
                "base_color_range": [list(profile["base_low"]), list(profile["base_high"])],
                "roughness_range": [profile["roughness_low"], profile["roughness_high"]],
                "fine_noise_scale": profile["fine_noise_scale"],
                "bump_strength": profile["bump_strength"],
                "bump_distance": profile["bump_distance"],
                "broad_noise_scale": profile["broad_noise_scale"],
                "broad_bump_strength": profile["broad_bump_strength"],
                "specular": float(spec_input.default_value) if spec_input is not None else None,
            }
    bpy.context.view_layer.update()
    return enhanced


def build_qc71336_gray_override_material():
    mat = bpy.data.materials.get("QC71336_GRAY_OVERRIDE")
    if mat is None:
        mat = bpy.data.materials.new("QC71336_GRAY_OVERRIDE")
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()

    output = tree.nodes.new("ShaderNodeOutputMaterial")
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    texcoord = tree.nodes.new("ShaderNodeTexCoord")
    mapping = tree.nodes.new("ShaderNodeMapping")
    noise = tree.nodes.new("ShaderNodeTexNoise")
    ramp = tree.nodes.new("ShaderNodeValToRGB")
    bump = tree.nodes.new("ShaderNodeBump")

    bsdf.inputs["Base Color"].default_value = GRAY_BASE_RGBA
    subsurface_name = "Subsurface Weight" if "Subsurface Weight" in bsdf.inputs else "Subsurface"
    bsdf.inputs[subsurface_name].default_value = 0.014
    if "Subsurface Radius" in bsdf.inputs:
        bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.9, 0.75)
    if "Subsurface Color" in bsdf.inputs:
        bsdf.inputs["Subsurface Color"].default_value = GRAY_SUBSURFACE_RGBA
    bsdf.inputs["Roughness"].default_value = 0.76
    bsdf.inputs["IOR"].default_value = 1.47
    spec_name = "Specular IOR Level" if "Specular IOR Level" in bsdf.inputs else "Specular"
    bsdf.inputs[spec_name].default_value = 0.26

    mapping.inputs["Scale"].default_value = (520.0, 520.0, 520.0)
    noise.inputs["Scale"].default_value = 1.0
    noise.inputs["Detail"].default_value = 10.0
    noise.inputs["Roughness"].default_value = 0.52
    ramp.color_ramp.elements[0].position = 0.38
    ramp.color_ramp.elements[0].color = (0.50, 0.492, 0.486, 1.0)
    ramp.color_ramp.elements[1].position = 0.62
    ramp.color_ramp.elements[1].color = (0.65, 0.642, 0.636, 1.0)
    bump.inputs["Strength"].default_value = 0.0018
    bump.inputs["Distance"].default_value = 0.0006

    tree.links.new(texcoord.outputs["Object"], mapping.inputs["Vector"])
    tree.links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    tree.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    tree.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    tree.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    tree.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    return mat


def apply_gray_override_material(imported_objects):
    gray_mat = build_qc71336_gray_override_material()
    for obj in imported_objects:
        if obj.type != "MESH":
            continue
        obj.data.materials.clear()
        obj.data.materials.append(gray_mat)
    bpy.context.view_layer.update()
    return gray_mat.name


def tune_reference_lighting_for_gray_override():
    scene = bpy.context.scene
    key_light_names = {"Area.003", "Area.005"}
    fill_light_names = {"Area", "Area.001", "Area.002", "Area.004"}

    for obj in bpy.data.objects:
        if obj.type != "LIGHT":
            continue
        light = obj.data
        if obj.name in key_light_names and hasattr(light, "energy") and light.energy is not None:
            light.energy = float(light.energy) * 0.72
        elif obj.name in fill_light_names and hasattr(light, "energy") and light.energy is not None:
            light.energy = float(light.energy) * 0.82

    backdrop = bpy.data.objects.get("REFERENCE_DEBUG_BACKDROP")
    if backdrop and backdrop.type == "MESH" and backdrop.data.materials:
        backdrop_mat = backdrop.data.materials[0]
        backdrop_bsdf = find_principled(backdrop_mat)
        if backdrop_bsdf is not None:
            backdrop_bsdf.inputs["Base Color"].default_value = (0.62, 0.612, 0.602, 1.0)
            backdrop_bsdf.inputs["Roughness"].default_value = 0.88

    world = scene.world
    if world and world.use_nodes and world.node_tree:
        for node in world.node_tree.nodes:
            if node.type == "BACKGROUND":
                color_input = node.inputs.get("Color")
                strength_input = node.inputs.get("Strength")
                if color_input is not None:
                    color_input.default_value = (0.66, 0.652, 0.642, 1.0)
                if strength_input is not None:
                    strength_input.default_value = min(float(strength_input.default_value), 0.018)

    scene.view_settings.exposure = float(scene.view_settings.exposure) - 0.24
    bpy.context.view_layer.update()


def fit_objects_to_reference(imported_objects, reference_objects):
    candidate_rotations = [
        (0.0, 0.0, 0.0),
        (math.radians(90.0), 0.0, 0.0),
        (math.radians(-90.0), 0.0, 0.0),
        (0.0, math.radians(90.0), 0.0),
        (0.0, math.radians(-90.0), 0.0),
        (math.radians(180.0), 0.0, 0.0),
    ]

    ref_min, ref_max = world_bbox(reference_objects)
    ref_dims = ref_max - ref_min
    ref_xy = sorted([abs(float(ref_dims.x)), abs(float(ref_dims.y))], reverse=True)

    best_rotation = candidate_rotations[0]
    best_score = None
    original_rotations = [obj.rotation_euler.copy() for obj in imported_objects]
    for rotation in candidate_rotations:
        for obj, original in zip(imported_objects, original_rotations):
            obj.rotation_euler = original.copy()
            obj.rotation_euler.rotate_axis("X", rotation[0])
            obj.rotation_euler.rotate_axis("Y", rotation[1])
            obj.rotation_euler.rotate_axis("Z", rotation[2])
        bpy.context.view_layer.update()
        src_min, src_max = world_bbox(imported_objects)
        src_dims = src_max - src_min
        src_xy = sorted([abs(float(src_dims.x)), abs(float(src_dims.y))], reverse=True)
        thickness = abs(float(src_dims.z))
        xy_ratio_penalty = abs((src_xy[0] / max(src_xy[1], 1e-6)) - (ref_xy[0] / max(ref_xy[1], 1e-6)))
        score = thickness + 0.25 * xy_ratio_penalty
        if best_score is None or score < best_score:
            best_score = score
            best_rotation = rotation

    for obj, original in zip(imported_objects, original_rotations):
        obj.rotation_euler = original.copy()
        obj.rotation_euler.rotate_axis("X", best_rotation[0])
        obj.rotation_euler.rotate_axis("Y", best_rotation[1])
        obj.rotation_euler.rotate_axis("Z", best_rotation[2])
    bpy.context.view_layer.update()

    ref_min, ref_max = world_bbox(reference_objects)
    src_min, src_max = world_bbox(imported_objects)
    ref_center = (ref_min + ref_max) * 0.5
    src_center = (src_min + src_max) * 0.5
    ref_dims = ref_max - ref_min
    src_dims = src_max - src_min
    ref_max_dim = max(float(abs(ref_dims.x)), float(abs(ref_dims.y)), float(abs(ref_dims.z)), 1e-6)
    src_max_dim = max(float(abs(src_dims.x)), float(abs(src_dims.y)), float(abs(src_dims.z)), 1e-6)
    scale = 0.95 * ref_max_dim / src_max_dim

    for obj in imported_objects:
        obj.scale = obj.scale * scale
    bpy.context.view_layer.update()

    src_min, src_max = world_bbox(imported_objects)
    src_center = (src_min + src_max) * 0.5
    offset = ref_center - src_center
    for obj in imported_objects:
        obj.location += offset
    bpy.context.view_layer.update()


def find_principled(mat):
    if not mat or not mat.use_nodes or not mat.node_tree:
        return None
    for node in mat.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            return node
    return None


def add_subtle_roughness_variation(mat, bump_strength=0.0022, scale=620.0):
    if not mat or not mat.use_nodes or not mat.node_tree:
        return
    tree = mat.node_tree
    bsdf = find_principled(mat)
    if bsdf is None:
        return

    texcoord = tree.nodes.new("ShaderNodeTexCoord")
    mapping = tree.nodes.new("ShaderNodeMapping")
    noise = tree.nodes.new("ShaderNodeTexNoise")
    ramp = tree.nodes.new("ShaderNodeValToRGB")
    rough_base = tree.nodes.new("ShaderNodeValue")
    rough_mix = tree.nodes.new("ShaderNodeMath")
    bump = tree.nodes.new("ShaderNodeBump")

    mapping.inputs["Scale"].default_value = (scale, scale, scale)
    noise.inputs["Scale"].default_value = 1.0
    noise.inputs["Detail"].default_value = 9.0
    noise.inputs["Roughness"].default_value = 0.58
    ramp.color_ramp.elements[0].position = 0.40
    ramp.color_ramp.elements[0].color = (0.88, 0.88, 0.88, 1.0)
    ramp.color_ramp.elements[1].position = 0.60
    ramp.color_ramp.elements[1].color = (1.06, 1.06, 1.06, 1.0)
    rough_base.outputs[0].default_value = bsdf.inputs["Roughness"].default_value
    rough_mix.operation = "MULTIPLY"
    bump.inputs["Strength"].default_value = bump_strength
    bump.inputs["Distance"].default_value = 0.0007

    tree.links.new(texcoord.outputs["Object"], mapping.inputs["Vector"])
    tree.links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    tree.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    tree.links.new(rough_base.outputs["Value"], rough_mix.inputs[0])
    tree.links.new(ramp.outputs["Color"], rough_mix.inputs[1])
    tree.links.new(rough_mix.outputs["Value"], bsdf.inputs["Roughness"])
    tree.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    tree.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


def project_point_visibility_check(scene, camera, world_point, margin=0.10):
    projected = world_to_camera_view(scene, camera, world_point)
    return (
        projected.z > 0.0
        and margin <= projected.x <= (1.0 - margin)
        and margin <= projected.y <= (1.0 - margin)
    )


def make_principled_material(name, base_color, roughness, specular):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = find_principled(mat)
    if bsdf is None:
        raise RuntimeError(f"Principled BSDF node not found for material: {name}")
    bsdf.inputs["Base Color"].default_value = base_color
    bsdf.inputs["Roughness"].default_value = roughness
    spec_name = "Specular IOR Level" if "Specular IOR Level" in bsdf.inputs else "Specular"
    bsdf.inputs[spec_name].default_value = specular
    return mat


def ensure_input_default(bsdf, input_name, value):
    socket = bsdf.inputs.get(input_name)
    if socket is not None:
        socket.default_value = value


def make_alpha_material(name, base_color, roughness, specular, alpha):
    mat = make_principled_material(name, base_color, roughness, specular)
    bsdf = find_principled(mat)
    if bsdf is not None and "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = alpha
    mat.blend_method = "BLEND"
    mat.shadow_method = "NONE"
    if hasattr(mat, "show_transparent_back"):
        mat.show_transparent_back = False
    return mat


def build_white_black_dot_materials():
    center = make_principled_material(
        "REFERENCE_QC71336_BLACK_DOT_CENTER",
        (0.022, 0.020, 0.019, 1.0),
        0.82,
        0.018,
    )
    edge = make_principled_material(
        "REFERENCE_QC71336_BLACK_DOT_EDGE",
        (0.060, 0.056, 0.052, 1.0),
        0.86,
        0.012,
    )
    patch = make_alpha_material(
        "REFERENCE_QC71336_BLACK_DOT_LOCAL_PATCH",
        (0.24, 0.235, 0.23, 1.0),
        0.96,
        0.0,
        0.030,
    )
    add_subtle_roughness_variation(center, bump_strength=0.0008, scale=980.0)
    add_subtle_roughness_variation(edge, bump_strength=0.00055, scale=920.0)
    add_subtle_roughness_variation(patch, bump_strength=0.00035, scale=760.0)
    return center, edge, patch


def make_white_foreign_material_mat(name, rng):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = find_principled(mat)
    if bsdf is None:
        raise RuntimeError("Principled BSDF node not found for foreign-material defect.")

    base_color = rng.choice(
        [
            (0.36, 0.32, 0.24, 1.0),
            (0.42, 0.37, 0.27, 1.0),
            (0.30, 0.28, 0.23, 1.0),
            (0.48, 0.44, 0.34, 1.0),
        ]
    )
    roughness = rng.uniform(0.58, 0.80)
    ensure_input_default(bsdf, "Metallic", 0.0)
    bsdf.inputs["Base Color"].default_value = base_color
    bsdf.inputs["Roughness"].default_value = roughness
    spec_name = "Specular IOR Level" if "Specular IOR Level" in bsdf.inputs else "Specular"
    ensure_input_default(bsdf, spec_name, rng.uniform(0.015, 0.050))

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    noise = nodes.new("ShaderNodeTexNoise")
    noise.location = (-520, -140)
    noise.inputs["Scale"].default_value = rng.uniform(90.0, 150.0)
    noise.inputs["Detail"].default_value = rng.uniform(4.0, 8.0)
    noise.inputs["Roughness"].default_value = 0.52

    color_ramp = nodes.new("ShaderNodeValToRGB")
    color_ramp.location = (-300, -140)
    color_ramp.color_ramp.interpolation = "B_SPLINE"
    color_ramp.color_ramp.elements[0].position = 0.38
    color_ramp.color_ramp.elements[1].position = 0.68
    low = tuple(max(0.0, channel - rng.uniform(0.035, 0.070)) for channel in base_color[:3])
    high = tuple(min(1.0, channel + rng.uniform(0.010, 0.030)) for channel in base_color[:3])
    color_ramp.color_ramp.elements[0].color = (low[0], low[1], low[2], 1.0)
    color_ramp.color_ramp.elements[1].color = (high[0], high[1], high[2], 1.0)

    rough_mult = nodes.new("ShaderNodeMath")
    rough_mult.operation = "MULTIPLY"
    rough_mult.location = (-300, -320)
    rough_mult.inputs[1].default_value = rng.uniform(0.08, 0.16)

    rough_add = nodes.new("ShaderNodeMath")
    rough_add.operation = "ADD"
    rough_add.use_clamp = True
    rough_add.location = (-90, -320)
    rough_add.inputs[0].default_value = roughness

    bump = nodes.new("ShaderNodeBump")
    bump.location = (-80, -500)
    bump.inputs["Strength"].default_value = rng.uniform(0.002, 0.006)
    bump.inputs["Distance"].default_value = 0.004

    links.new(noise.outputs["Fac"], color_ramp.inputs["Fac"])
    links.new(color_ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(noise.outputs["Fac"], rough_mult.inputs[0])
    links.new(rough_mult.outputs["Value"], rough_add.inputs[1])
    links.new(rough_add.outputs["Value"], bsdf.inputs["Roughness"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat, "tan_gray_particle"


def create_irregular_flat_foreign_mesh(name, radius, rng):
    vertex_count = rng.randint(7, 11)
    verts = [(0.0, 0.0, rng.uniform(0.00, 0.08) * radius)]
    top_ring = []
    bottom_ring = []
    phase = rng.uniform(0.0, math.tau)
    if rng.random() < 0.28:
        stretch_x = rng.uniform(1.45, 2.65)
        stretch_y = rng.uniform(0.20, 0.58)
    else:
        stretch_x = rng.uniform(0.70, 1.75)
        stretch_y = rng.uniform(0.34, 1.08)
    thickness = rng.uniform(0.10, 0.24) * radius
    for i in range(vertex_count):
        angle = math.tau * i / vertex_count + rng.uniform(-0.12, 0.12)
        edge = radius * rng.uniform(0.62, 1.10) * (1.0 + 0.10 * math.sin(angle * 2.0 + phase))
        x = math.cos(angle) * edge * stretch_x
        y = math.sin(angle) * edge * stretch_y
        top_ring.append(len(verts))
        verts.append((x, y, thickness * rng.uniform(0.20, 0.95)))
        bottom_ring.append(len(verts))
        verts.append((x * rng.uniform(0.88, 1.04), y * rng.uniform(0.88, 1.04), -thickness * 0.22))
    faces = []
    for i in range(vertex_count):
        j = (i + 1) % vertex_count
        faces.append((0, top_ring[i], top_ring[j]))
        faces.append((top_ring[i], bottom_ring[i], bottom_ring[j], top_ring[j]))
    faces.append(tuple(reversed(bottom_ring)))
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    for poly in mesh.polygons:
        poly.use_smooth = True
    return mesh


def create_irregular_particle_mesh(name, radius, depth, rng):
    vertex_count = rng.randint(11, 17)
    squash_x = rng.uniform(0.68, 1.26)
    squash_y = rng.uniform(0.70, 1.22)
    top_z = depth * rng.uniform(0.16, 0.28)
    bottom_z = -depth * rng.uniform(0.42, 0.62)
    wave_freq = rng.uniform(2.2, 5.2)
    wave_phase = rng.uniform(0.0, math.tau)
    verts = [(0.0, 0.0, top_z), (0.0, 0.0, bottom_z)]
    inner_ring = []
    top_ring = []
    bottom_ring = []
    for i in range(vertex_count):
        angle = math.tau * i / vertex_count
        wave = 1.0 + 0.12 * math.sin(angle * wave_freq + wave_phase)
        local_radius = radius * rng.uniform(0.66, 1.12) * wave
        x = math.cos(angle) * local_radius * squash_x
        y = math.sin(angle) * local_radius * squash_y
        inner_radius = local_radius * rng.uniform(0.28, 0.46)
        inner_ring.append(len(verts))
        verts.append(
            (
                math.cos(angle) * inner_radius * squash_x,
                math.sin(angle) * inner_radius * squash_y,
                top_z * rng.uniform(0.82, 1.04),
            )
        )
        top_ring.append(len(verts))
        verts.append((x, y, top_z * rng.uniform(0.38, 0.76)))
        bottom_ring.append(len(verts))
        verts.append((x * rng.uniform(0.80, 1.06), y * rng.uniform(0.80, 1.06), bottom_z))
    faces = []
    material_indices = []
    for i in range(vertex_count):
        j = (i + 1) % vertex_count
        faces.append((0, inner_ring[i], inner_ring[j]))
        material_indices.append(0)
        faces.append((inner_ring[i], top_ring[i], top_ring[j], inner_ring[j]))
        material_indices.append(1)
        faces.append((1, bottom_ring[j], bottom_ring[i]))
        material_indices.append(1)
        faces.append((top_ring[i], bottom_ring[i], bottom_ring[j], top_ring[j]))
        material_indices.append(1)
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    for polygon, material_index in zip(mesh.polygons, material_indices):
        polygon.material_index = material_index
    return mesh


def create_surface_contamination_patch(world_point, world_normal, radius, mat, name, rng):
    vertex_count = rng.randint(18, 26)
    squash_x = rng.uniform(0.84, 1.14)
    squash_y = rng.uniform(0.84, 1.14)
    verts = [(0.0, 0.0, 0.0)]
    inner_ring = []
    outer_ring = []
    wave_freq = rng.uniform(2.0, 3.6)
    wave_phase = rng.uniform(0.0, math.tau)
    for i in range(vertex_count):
        angle = math.tau * i / vertex_count
        wave = 1.0 + 0.06 * math.sin(angle * wave_freq + wave_phase)
        inner_radius = radius * rng.uniform(0.36, 0.52) * wave
        outer_radius = radius * rng.uniform(0.82, 1.06) * wave
        inner_ring.append(len(verts))
        verts.append((math.cos(angle) * inner_radius * squash_x, math.sin(angle) * inner_radius * squash_y, 0.0))
        outer_ring.append(len(verts))
        verts.append((math.cos(angle) * outer_radius * squash_x, math.sin(angle) * outer_radius * squash_y, 0.0))
    faces = []
    for i in range(vertex_count):
        j = (i + 1) % vertex_count
        faces.append((0, inner_ring[i], inner_ring[j]))
        faces.append((inner_ring[i], outer_ring[i], outer_ring[j], inner_ring[j]))
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    patch = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(patch)
    patch.location = world_point + world_normal * max(radius * 0.004, 1e-5)
    patch.rotation_euler = world_normal.to_track_quat("Z", "Y").to_euler()
    patch.rotation_euler.rotate_axis("Z", rng.uniform(0.0, math.tau))
    patch.data.materials.append(mat)
    return patch


def clear_reference_black_dot_objects():
    exact_names = {
        "REFERENCE_QC71336_BLACK_DOT",
        "REFERENCE_QC71336_BLACK_DOT_LOCAL_PATCH",
        "REFERENCE_QC71336_FOREIGN_MATERIAL",
    }
    prefixes = (
        "REFERENCE_QC71336_BLACK_DOT.",
        "REFERENCE_QC71336_BLACK_DOT_LOCAL_PATCH.",
        "REFERENCE_QC71336_FOREIGN_MATERIAL.",
    )
    for obj in list(bpy.data.objects):
        if obj.name in exact_names or obj.name.startswith(prefixes):
            bpy.data.objects.remove(obj, do_unlink=True)


def polygon_neighbor_map(mesh):
    edge_to_polys = {}
    for poly in mesh.polygons:
        for edge_key in poly.edge_keys:
            edge_to_polys.setdefault(edge_key, []).append(poly.index)
    neighbor_map = {poly.index: set() for poly in mesh.polygons}
    for poly_indices in edge_to_polys.values():
        if len(poly_indices) < 2:
            continue
        for poly_index in poly_indices:
            neighbor_map[poly_index].update(other for other in poly_indices if other != poly_index)
    return neighbor_map


def build_two_sided_camera_presets(imported_objects):
    bb_min, bb_max = world_bbox(imported_objects)
    center = (bb_min + bb_max) * 0.5
    span = bb_max - bb_min
    max_dim = max(float(abs(span.x)), float(abs(span.y)), float(abs(span.z)), 1e-6)
    focus_target = center + Vector((0.0, 0.02 * max_dim, 0.0))

    def make_preset(name, offset, shift_y):
        location = center + offset
        direction = focus_target - location
        rotation = direction.to_track_quat("-Z", "Y").to_euler()
        return {
            "name": name,
            "location": location,
            "rotation": rotation,
            "shift_x": 0.0,
            "shift_y": shift_y,
        }

    return {
        "front_face": make_preset("front_face", Vector((0.0, -0.16 * max_dim, 2.72 * max_dim)), 0.082),
        "back_face": make_preset("back_face", Vector((0.0, -0.16 * max_dim, -2.78 * max_dim)), 0.020),
    }


def look_at_object(obj, target, track="-Z", up="Y"):
    direction = target - obj.location
    if direction.length <= 1e-8:
        return
    obj.rotation_euler = direction.to_track_quat(track, up).to_euler()


def tune_white_oblique_camera_and_lighting(imported_objects, camera, camera_presets):
    bb_min, bb_max = world_bbox(imported_objects)
    center = (bb_min + bb_max) * 0.5
    span = bb_max - bb_min
    max_dim = max(float(abs(span.x)), float(abs(span.y)), float(abs(span.z)), 1e-6)
    focus_target = center + Vector((0.02 * max_dim, 0.01 * max_dim, 0.0))

    front_location = center + Vector((-0.42 * max_dim, -1.08 * max_dim, 2.36 * max_dim))
    front_rotation = (focus_target - front_location).to_track_quat("-Z", "Y").to_euler()
    camera_presets["front_face"] = {
        "name": "front_face_oblique_real_white",
        "location": front_location,
        "rotation": front_rotation,
        "shift_x": 0.012,
        "shift_y": -0.035,
    }
    camera.data.lens = 64.0
    camera.data.sensor_width = 36.0
    apply_camera_preset(camera, camera_presets["front_face"])

    key = bpy.data.objects.get("Area.003")
    if key and key.type == "LIGHT":
        key.location = center + Vector((-0.18 * max_dim, -1.34 * max_dim, 2.05 * max_dim))
        look_at_object(key, center + Vector((0.0, 0.0, 0.03 * max_dim)))
        key.data.energy = 58.0
        if hasattr(key.data, "size"):
            key.data.size = max(float(key.data.size), 2.15 * max_dim)
        if hasattr(key.data, "size_y"):
            key.data.size_y = max(float(key.data.size_y), 1.55 * max_dim)
        if getattr(key.data, "color", None) is not None:
            key.data.color = (1.0, 0.978, 0.946)

    front_fill = bpy.data.objects.get("Area.005")
    if front_fill and front_fill.type == "LIGHT":
        front_fill.location = center + Vector((0.52 * max_dim, -1.00 * max_dim, 1.55 * max_dim))
        look_at_object(front_fill, center)
        front_fill.data.energy = 18.0
        if hasattr(front_fill.data, "size"):
            front_fill.data.size = max(float(front_fill.data.size), 2.8 * max_dim)
        if getattr(front_fill.data, "color", None) is not None:
            front_fill.data.color = (0.985, 0.972, 0.955)

    for name in ("Area", "Area.001", "Area.002", "Area.004"):
        fill = bpy.data.objects.get(name)
        if fill and fill.type == "LIGHT" and hasattr(fill.data, "energy"):
            fill.data.energy = float(fill.data.energy) * 0.46

    world = bpy.context.scene.world
    if world and world.use_nodes and world.node_tree:
        for node in world.node_tree.nodes:
            if node.type == "BACKGROUND":
                color_input = node.inputs.get("Color")
                strength_input = node.inputs.get("Strength")
                if color_input is not None:
                    color_input.default_value = (0.62, 0.612, 0.602, 1.0)
                if strength_input is not None:
                    strength_input.default_value = min(float(strength_input.default_value), 0.0035)

    bpy.context.scene.view_settings.exposure = -0.76
    bpy.context.view_layer.update()


def apply_camera_preset(camera, preset):
    camera.location = preset["location"].copy()
    camera.rotation_euler = preset["rotation"].copy()
    camera.data.shift_x = float(preset.get("shift_x", 0.0))
    camera.data.shift_y = float(preset.get("shift_y", 0.0))
    bpy.context.view_layer.update()


def configure_backdrop_for_anchor_band(anchor_band):
    backdrop = bpy.data.objects.get("REFERENCE_DEBUG_BACKDROP")
    if backdrop is None:
        return None
    mesh_objects = [
        obj
        for obj in bpy.data.objects
        if obj.type == "MESH"
        and obj.name != "REFERENCE_DEBUG_BACKDROP"
        and not obj.name.startswith("REFERENCE_QC71336_FOREIGN_MATERIAL")
        and not obj.name.startswith("REFERENCE_BLACK_DOT")
    ]
    if mesh_objects:
        bb_min, bb_max = world_bbox(mesh_objects)
        center = (bb_min + bb_max) * 0.5
        span = bb_max - bb_min
        max_dim = max(float(abs(span.x)), float(abs(span.y)), float(abs(span.z)), 1e-3)
        z_sign = 1.0 if anchor_band == "front_face" else -1.0
        backdrop.location = (center.x, center.y, center.z - z_sign * 0.42 * max_dim)
        backdrop.rotation_euler = (0.0, 0.0, 0.0)
        backdrop.scale = (2.8 * max_dim, 2.8 * max_dim, 1.0)
    backdrop.hide_render = False
    backdrop.hide_viewport = False
    bpy.context.view_layer.update()
    return {
        "anchor_band": anchor_band,
        "visible": True,
        "location": [round(float(backdrop.location.x), 5), round(float(backdrop.location.y), 5), round(float(backdrop.location.z), 5)],
        "occlusion_policy": "placed_behind_model_relative_to_anchor_band_camera",
    }


def clamp(value, lower, upper):
    return max(lower, min(upper, value))


def refine_camera_shift_for_defect(camera, scene, defect_center, desired_x, desired_y, max_delta=0.036):
    projected = world_to_camera_view(scene, camera, defect_center)
    origin_shift_x = float(camera.data.shift_x)
    origin_shift_y = float(camera.data.shift_y)
    for _ in range(3):
        if projected.z <= 0.0:
            break
        current_error = abs(float(projected.x - desired_x)) + abs(float(projected.y - desired_y))
        if current_error <= 0.020:
            break
        base_shift_x = float(camera.data.shift_x)
        base_shift_y = float(camera.data.shift_y)
        step = max(0.006, min(0.018, current_error * 0.12))
        candidate_shifts = [
            (base_shift_x, base_shift_y),
            (base_shift_x + step, base_shift_y),
            (base_shift_x - step, base_shift_y),
            (base_shift_x, base_shift_y + step),
            (base_shift_x, base_shift_y - step),
            (base_shift_x + step * 0.55, base_shift_y + step * 0.55),
            (base_shift_x - step * 0.55, base_shift_y - step * 0.55),
            (base_shift_x + step * 0.55, base_shift_y - step * 0.55),
            (base_shift_x - step * 0.55, base_shift_y + step * 0.55),
        ]
        best_shift = (base_shift_x, base_shift_y)
        best_projected = projected
        best_error = current_error
        for shift_x, shift_y in candidate_shifts:
            limited_shift_x = clamp(shift_x, origin_shift_x - max_delta, origin_shift_x + max_delta)
            limited_shift_y = clamp(shift_y, origin_shift_y - max_delta, origin_shift_y + max_delta)
            camera.data.shift_x = limited_shift_x
            camera.data.shift_y = limited_shift_y
            bpy.context.view_layer.update()
            candidate_projected = world_to_camera_view(scene, camera, defect_center)
            if candidate_projected.z <= 0.0:
                continue
            candidate_error = abs(float(candidate_projected.x - desired_x)) + abs(float(candidate_projected.y - desired_y))
            if candidate_error < best_error:
                best_error = candidate_error
                best_shift = (shift_x, shift_y)
                best_projected = candidate_projected
        camera.data.shift_x = best_shift[0]
        camera.data.shift_y = best_shift[1]
        bpy.context.view_layer.update()
        projected = best_projected
    return projected


def build_object_view_transform(args, defect_info):
    enabled = args.object_transform_mode == "keep_camera"
    rotation = args.object_rotate_deg
    if rotation is None:
        rotation = [180.0, 0.0, 0.0] if enabled and defect_info.get("anchor_side") == "back" else [0.0, 0.0, 0.0]
    translation = [float(value) for value in (args.object_translate or [0.0, 0.0, 0.0])]
    return {
        "enabled": bool(enabled),
        "mode": args.object_transform_mode,
        "camera_moved_for_defect_side": False if enabled else None,
        "camera_side": args.object_transform_camera_side,
        "physical_anchor_side": defect_info.get("anchor_side"),
        "rotation_degrees_xyz": [float(value) for value in rotation],
        "translation_xyz": translation,
        "pivot_policy": "product_bbox_center",
        "environment_transform": "none",
        "default_backside_operation": bool(
            enabled
            and defect_info.get("anchor_side") == "back"
            and args.object_rotate_deg is None
            and all(abs(value) < 1e-9 for value in translation)
        ),
    }


def apply_object_view_transform(objects, defect_info, transform):
    rotation_deg = transform.get("rotation_degrees_xyz") or [0.0, 0.0, 0.0]
    translation = Vector(transform.get("translation_xyz") or [0.0, 0.0, 0.0])
    bb_min, bb_max = world_bbox(objects)
    pivot = (bb_min + bb_max) * 0.5
    rotation = Matrix.Identity(4)
    rotation = Matrix.Rotation(math.radians(rotation_deg[2]), 4, "Z") @ rotation
    rotation = Matrix.Rotation(math.radians(rotation_deg[1]), 4, "Y") @ rotation
    rotation = Matrix.Rotation(math.radians(rotation_deg[0]), 4, "X") @ rotation
    matrix = Matrix.Translation(pivot + translation) @ rotation @ Matrix.Translation(-pivot)
    transform_objects = list(objects)
    for key in ("dot_object", "patch_object", "foreign_object", "mask_object"):
        name = defect_info.get(key)
        obj = bpy.data.objects.get(name) if name else None
        if obj is not None and obj not in transform_objects:
            transform_objects.append(obj)
    for name in defect_info.get("mask_objects") or []:
        obj = bpy.data.objects.get(name) if name else None
        if obj is not None and obj not in transform_objects:
            transform_objects.append(obj)
    for child_defect in defect_info.get("defects") or []:
        for key in ("dot_object", "patch_object", "foreign_object", "mask_object"):
            name = child_defect.get(key)
            obj = bpy.data.objects.get(name) if name else None
            if obj is not None and obj not in transform_objects:
                transform_objects.append(obj)
    for obj in transform_objects:
        obj.matrix_world = matrix @ obj.matrix_world
    if defect_info.get("world_point"):
        world_point = matrix @ Vector(defect_info["world_point"])
        defect_info["world_point"] = [float(world_point.x), float(world_point.y), float(world_point.z)]
    if defect_info.get("world_normal"):
        world_normal = (matrix.to_3x3() @ Vector(defect_info["world_normal"])).normalized()
        defect_info["world_normal"] = [float(world_normal.x), float(world_normal.y), float(world_normal.z)]
    transform["pivot_world"] = [float(pivot.x), float(pivot.y), float(pivot.z)]
    transform["objects_transformed"] = [obj.name for obj in transform_objects]
    bpy.context.view_layer.update()


def sample_black_dot_anchor(imported_objects, scene, camera, camera_presets, rng, allowed_sides=None, main_plane_only=False):
    allowed_bands = set()
    for side in allowed_sides or ["front"]:
        allowed_bands.add("front_face" if side == "front" else "back_face")
    target_projected_x = rng.uniform(0.20, 0.80)
    target_projected_y = rng.uniform(0.22, 0.80)
    target_local_x = rng.uniform(-0.70, 0.70)
    target_local_y = rng.uniform(-0.68, 0.68)
    target_z_ratio = rng.uniform(0.10, 0.90)
    preferred_anchor_band = "front_face" if "front_face" in allowed_bands else "back_face"
    candidate_pools = {
        "front_face": [],
        "back_face": [],
    }
    front_camera_location = camera_presets["front_face"]["location"]
    back_camera_location = camera_presets["back_face"]["location"]
    for obj in imported_objects:
        mesh = obj.data
        if not mesh.polygons:
            continue
        neighbor_map = polygon_neighbor_map(mesh)
        polygon_areas = sorted(max(float(poly.area), 1e-10) for poly in mesh.polygons)
        max_area = polygon_areas[-1]
        lower_area = polygon_areas[min(len(polygon_areas) - 1, max(int(len(polygon_areas) * 0.18), 0))]
        area_floor = max(lower_area * 0.55, max_area * 0.00006, 1e-8)
        tip_area_floor = max(lower_area * 1.05, max_area * 0.00018, 1e-8)
        bb_world = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        min_corner = Vector(
            (min(v.x for v in bb_world), min(v.y for v in bb_world), min(v.z for v in bb_world))
        )
        max_corner = Vector(
            (max(v.x for v in bb_world), max(v.y for v in bb_world), max(v.z for v in bb_world))
        )
        center = (min_corner + max_corner) * 0.5
        dims = max_corner - min_corner
        half_x = max(float(abs(dims.x)) * 0.5, 1e-6)
        half_y = max(float(abs(dims.y)) * 0.5, 1e-6)
        half_z = max(float(abs(dims.z)) * 0.5, 1e-6)
        z_span = max(float(abs(dims.z)), 1e-6)
        normal_matrix = obj.matrix_world.to_3x3()
        for poly in mesh.polygons:
            world_center = obj.matrix_world @ poly.center
            world_normal = (normal_matrix @ poly.normal).normalized()
            planar_score = abs(float(world_normal.z))
            x_ratio = abs(float(world_center.x - center.x)) / half_x
            y_ratio = abs(float(world_center.y - center.y)) / half_y
            local_x = float(world_center.x - center.x) / half_x
            local_y = float(world_center.y - center.y) / half_y
            local_z = float(world_center.z - center.z) / half_z
            z_ratio = float(world_center.z - min_corner.z) / z_span
            poly_area = max(float(poly.area), 1e-10)
            front_view_alignment = float(world_normal.dot((front_camera_location - world_center).normalized()))
            back_view_alignment = float(world_normal.dot((back_camera_location - world_center).normalized()))
            projected_front = world_to_camera_view(scene, camera, world_center)
            if x_ratio > 0.97 or y_ratio > 0.97:
                continue
            neighbor_indices = neighbor_map.get(poly.index, set())
            if neighbor_indices:
                neighbor_alignment = []
                for neighbor_index in neighbor_indices:
                    neighbor_poly = mesh.polygons[neighbor_index]
                    neighbor_normal = (normal_matrix @ neighbor_poly.normal).normalized()
                    neighbor_alignment.append(max(-1.0, min(1.0, float(world_normal.dot(neighbor_normal)))))
                local_planarity = sum(neighbor_alignment) / max(len(neighbor_alignment), 1)
            else:
                local_planarity = 1.0
            if poly_area < area_floor:
                continue
            bump_tip_like = poly_area < tip_area_floor and local_planarity > 0.94 and abs(local_z) > 0.10
            if bump_tip_like:
                continue
            face_alignment = float(world_normal.z)
            front_face_like = face_alignment >= 0.72 and local_z >= 0.18 and planar_score >= 0.72
            back_face_like = face_alignment <= -0.72 and local_z <= -0.18 and planar_score >= 0.72
            if not (front_face_like or back_face_like):
                continue
            main_plane_ok = (
                local_planarity >= 0.55
                and x_ratio <= 0.80
                and y_ratio <= 0.94
                and abs(local_x) <= 0.82
                and abs(local_y) <= 0.95
            )
            local_score = (
                max(0.0, 1.0 - abs(local_x - target_local_x) / 1.10)
                + max(0.0, 1.0 - abs(local_y - target_local_y) / 1.10)
                + max(0.0, 1.0 - abs(z_ratio - target_z_ratio) / 0.90)
            )
            area_score = min(poly_area / max(area_floor, 1e-8), 3.0)
            score = (
                local_planarity * 1.55
                + local_score * 0.72
                + min(planar_score, 0.92) * 0.40
                + area_score * 0.12
                + rng.uniform(0.0, 0.30)
            )
            front_visible_primary = (
                projected_front.z > 0.0
                and -0.08 <= projected_front.x <= 1.08
                and -0.08 <= projected_front.y <= 1.08
                and project_point_visibility_check(scene, camera, world_center, margin=0.05)
            )
            if (
                "front_face" in allowed_bands
                and front_face_like
                and front_visible_primary
                and local_planarity >= 0.28
                and (not main_plane_only or main_plane_ok)
            ):
                projected_score_front = (
                    max(0.0, 1.0 - abs(projected_front.x - target_projected_x) / 0.44)
                    + max(0.0, 1.0 - abs(projected_front.y - target_projected_y) / 0.40)
                )
                front_candidate = {
                    "score": score + projected_score_front * 0.95 + max(front_view_alignment, -0.35) * 0.55,
                    "object": obj,
                    "polygon_index": poly.index,
                    "world_center": world_center,
                    "world_normal": world_normal,
                    "planar_score": planar_score,
                    "local_planarity": local_planarity,
                    "view_alignment": front_view_alignment,
                    "poly_area": poly_area,
                    "local_x": local_x,
                    "local_y": local_y,
                    "local_z": local_z,
                    "z_ratio": z_ratio,
                    "projected_xy": [float(projected_front.x), float(projected_front.y)],
                    "x_ratio": x_ratio,
                    "y_ratio": y_ratio,
                    "target_projected_xy": [target_projected_x, target_projected_y],
                    "target_local_xy": [target_local_x, target_local_y],
                    "target_z_ratio": target_z_ratio,
                    "anchor_band": "front_face",
                }
                candidate_pools["front_face"].append(front_candidate)
            if (
                "back_face" in allowed_bands
                and back_face_like
                and local_planarity >= 0.28
                and back_view_alignment >= 0.20
                and (not main_plane_only or main_plane_ok)
            ):
                mirrored_x = 0.5 + (-local_x * 0.32)
                mirrored_y = 0.52 + (local_y * 0.30)
                projected_score_back = (
                    max(0.0, 1.0 - abs(mirrored_x - target_projected_x) / 0.46)
                    + max(0.0, 1.0 - abs(mirrored_y - target_projected_y) / 0.42)
                )
                back_candidate = {
                    "score": score + projected_score_back * 0.82 + max(back_view_alignment, -0.20) * 0.62,
                    "object": obj,
                    "polygon_index": poly.index,
                    "world_center": world_center,
                    "world_normal": world_normal,
                    "planar_score": planar_score,
                    "local_planarity": local_planarity,
                    "view_alignment": back_view_alignment,
                    "poly_area": poly_area,
                    "local_x": local_x,
                    "local_y": local_y,
                    "local_z": local_z,
                    "z_ratio": z_ratio,
                    "projected_xy": [float(mirrored_x), float(mirrored_y)],
                    "x_ratio": x_ratio,
                    "y_ratio": y_ratio,
                    "target_projected_xy": [target_projected_x, target_projected_y],
                    "target_local_xy": [target_local_x, target_local_y],
                    "target_z_ratio": target_z_ratio,
                    "anchor_band": "back_face",
                }
                candidate_pools["back_face"].append(back_candidate)

    available_pools = [(name, pool) for name, pool in candidate_pools.items() if pool]
    if not available_pools:
        raise RuntimeError("Could not find a stable black-dot anchor on the QC7-1336 front/back major faces.")

    pool_names = [name for name, _ in available_pools]
    if preferred_anchor_band in pool_names:
        chosen_band = preferred_anchor_band
    else:
        fallback_weights = {"front_face": 1.0 if "front_face" in allowed_bands else 0.0, "back_face": 1.0 if "back_face" in allowed_bands else 0.0}
        pool_weights = [fallback_weights.get(name, 0.10) for name in pool_names]
        chosen_band = rng.choices(pool_names, weights=pool_weights, k=1)[0]
    chosen_pool = dict(available_pools)[chosen_band]
    chosen_pool.sort(key=lambda item: item["score"], reverse=True)
    shortlist_cap = 40 if chosen_band == "front_face" else 32
    shortlisted = chosen_pool[: min(shortlist_cap, len(chosen_pool))]
    floor_score = shortlisted[-1]["score"]
    weights = [max(item["score"] - floor_score + 0.025, 0.003) for item in shortlisted]
    return rng.choices(shortlisted, weights=weights, k=1)[0]


def apply_black_dot_tracking_view(camera, camera_presets, defect_info):
    scene = bpy.context.scene
    defect_center = Vector(defect_info["world_point"])
    band = defect_info.get("anchor_band", "front_face")
    preset = camera_presets.get(band, camera_presets["front_face"])
    apply_camera_preset(camera, preset)
    backdrop_info = configure_backdrop_for_anchor_band(band)
    initial_projected = world_to_camera_view(scene, camera, defect_center)
    if defect_info.get("center_tracking"):
        desired_x = 0.50
        desired_y = 0.50
    else:
        desired_x = clamp(float(initial_projected.x), 0.30, 0.70)
        desired_y = clamp(float(initial_projected.y), 0.28, 0.72)
    projected = refine_camera_shift_for_defect(camera, scene, defect_center, desired_x, desired_y)
    return {
        "anchor_band": band,
        "camera_preset": preset["name"],
        "camera_location": [float(camera.location.x), float(camera.location.y), float(camera.location.z)],
        "camera_rotation_euler": [
            float(camera.rotation_euler.x),
            float(camera.rotation_euler.y),
            float(camera.rotation_euler.z),
        ],
        "defect_projected_xy": [float(projected.x), float(projected.y)],
        "visible_after_follow": bool(projected.z > 0.0 and 0.08 <= projected.x <= 0.92 and 0.08 <= projected.y <= 0.92),
        "tracking_target": defect_info["world_point"],
        "backdrop": backdrop_info,
    }


def apply_black_dot_tracking_lighting(base_light_state, base_exposure, defect_info):
    restore_light_state(base_light_state)
    scene = bpy.context.scene
    band = defect_info.get("anchor_band", "front_face")
    band_scales = {
        "front_face": (1.00, 1.00, 0.00),
        "back_face": (1.08, 1.05, 0.03),
    }
    key_scale, fill_scale, exposure_add = band_scales.get(band, (1.0, 1.0, 0.0))
    for obj in bpy.data.objects:
        if obj.type != "LIGHT" or obj.name not in base_light_state:
            continue
        light = obj.data
        base_energy = base_light_state[obj.name]["energy"]
        if obj.name == "Area.003":
            light.energy = base_energy * key_scale
        elif obj.name == "Area.005":
            light.energy = base_energy * ((key_scale + fill_scale) * 0.5)
        else:
            light.energy = base_energy * fill_scale
    scene.view_settings.exposure = base_exposure + exposure_add
    bpy.context.view_layer.update()


def add_black_dot(imported_objects, scene, camera, camera_presets, image_offset, seed, radius_scale, depth_scale, allowed_sides=None):
    clear_reference_black_dot_objects()
    rng = random.Random(seed + image_offset)
    anchor = sample_black_dot_anchor(imported_objects, scene, camera, camera_presets, rng, allowed_sides)
    anchor_obj = anchor["object"]
    poly_index = anchor["polygon_index"]
    world_point = anchor["world_center"]
    world_normal = anchor["world_normal"]
    bb_min, bb_max = world_bbox(imported_objects)
    dims = bb_max - bb_min
    max_dim = max(float(abs(dims.x)), float(abs(dims.y)), float(abs(dims.z)), 1e-6)
    radius_jitter = rng.uniform(0.90, 1.10)
    depth_jitter = rng.uniform(0.90, 1.08)
    radius = max_dim * radius_scale * radius_jitter
    depth = max_dim * depth_scale * depth_jitter

    center_mat, edge_mat, patch_mat = build_white_black_dot_materials()
    patch_radius_jitter = rng.uniform(1.12, 1.26)
    patch_radius = radius * patch_radius_jitter
    patch = create_surface_contamination_patch(
        world_point,
        world_normal,
        patch_radius,
        patch_mat,
        "REFERENCE_QC71336_BLACK_DOT_LOCAL_PATCH",
        rng,
    )
    mesh_seed = seed + image_offset
    mesh = create_irregular_particle_mesh("REFERENCE_QC71336_BLACK_DOT", radius, depth, rng)
    dot = bpy.data.objects.new("REFERENCE_QC71336_BLACK_DOT", mesh)
    bpy.context.collection.objects.link(dot)
    dot.location = world_point - world_normal * max(depth * 0.085, radius * 0.009)
    dot.rotation_euler = world_normal.to_track_quat("Z", "Y").to_euler()
    dot_spin = rng.uniform(0.0, math.tau)
    dot.rotation_euler.rotate_axis("Z", dot_spin)
    dot.pass_index = 1
    patch.pass_index = 0
    dot.data.materials.append(center_mat)
    dot.data.materials.append(edge_mat)
    bpy.context.view_layer.update()
    return {
        "dot_object": dot.name,
        "patch_object": patch.name,
        "anchor_polygon_index": poly_index,
        "anchor_side": "front" if anchor["anchor_band"] == "front_face" else "back",
        "radius": radius,
        "depth": depth,
        "world_point": [float(world_point.x), float(world_point.y), float(world_point.z)],
        "world_normal": [float(world_normal.x), float(world_normal.y), float(world_normal.z)],
        "anchor_band": anchor["anchor_band"],
        "anchor_score": anchor["score"],
        "anchor_planar_score": anchor["planar_score"],
        "anchor_local_planarity": anchor["local_planarity"],
        "anchor_view_alignment": anchor["view_alignment"],
        "anchor_local_xy": [anchor["local_x"], anchor["local_y"]],
        "anchor_projected_xy": anchor["projected_xy"],
        "anchor_xy_ratio": [anchor["x_ratio"], anchor["y_ratio"]],
        "radius_jitter": radius_jitter,
        "depth_jitter": depth_jitter,
        "patch_radius": patch_radius,
        "patch_radius_jitter": patch_radius_jitter,
        "dot_spin_radians": dot_spin,
        "seed": mesh_seed,
    }


def add_foreign_material(
    imported_objects,
    scene,
    camera,
    camera_presets,
    image_offset,
    seed,
    radius_scale,
    depth_scale,
    allowed_sides=None,
    clear_existing=True,
    force_stable_particle=False,
):
    if clear_existing:
        clear_reference_black_dot_objects()
    rng = random.Random(seed + image_offset)
    anchor = sample_black_dot_anchor(
        imported_objects,
        scene,
        camera,
        camera_presets,
        rng,
        allowed_sides,
        main_plane_only=True,
    )
    poly_index = anchor["polygon_index"]
    world_point = anchor["world_center"]
    world_normal = anchor["world_normal"]
    bb_min, bb_max = world_bbox(imported_objects)
    dims = bb_max - bb_min
    center = (bb_min + bb_max) * 0.5
    half_x = max(float(abs(dims.x)) * 0.5, 1e-6)
    half_y = max(float(abs(dims.y)) * 0.5, 1e-6)
    max_dim = max(float(abs(dims.x)), float(abs(dims.y)), float(abs(dims.z)), 1e-6)
    back_main_plane_override = anchor["anchor_band"] == "back_face"
    use_particle_shape = back_main_plane_override or force_stable_particle
    if back_main_plane_override:
        local_x_override = rng.uniform(-0.24, 0.24)
        local_y_override = rng.uniform(-0.24, 0.24)
        world_point = Vector(
            (
                float(center.x + local_x_override * half_x),
                float(center.y + local_y_override * half_y),
                float(world_point.z),
            )
        )
        world_normal = Vector((0.0, 0.0, -1.0))
        anchor["local_x"] = local_x_override
        anchor["local_y"] = local_y_override
        anchor["x_ratio"] = abs(local_x_override)
        anchor["y_ratio"] = abs(local_y_override)
    size_tier = rng.choices(
        ["tiny", "normal"],
        weights=[35, 65],
        k=1,
    )[0]
    if radius_scale and radius_scale > 0.0:
        radius = max_dim * radius_scale * rng.uniform(0.86, 1.22)
    elif size_tier == "tiny":
        radius = rng.uniform(max_dim * 0.00070, max_dim * 0.00115)
    else:
        radius = rng.uniform(max_dim * 0.00105, max_dim * 0.00175)
    if force_stable_particle:
        radius = max(radius, FOREIGN_MATERIAL_VISIBLE_RADIUS_FLOOR * 1.18)
    radius = min(max(radius, FOREIGN_MATERIAL_VISIBLE_RADIUS_FLOOR), FOREIGN_MATERIAL_VISIBLE_RADIUS_CEILING)
    depth = radius * rng.uniform(0.10, 0.24)

    mesh_seed = seed + image_offset
    if use_particle_shape:
        bpy.ops.mesh.primitive_ico_sphere_add(
            subdivisions=1,
            radius=radius,
            location=world_point + world_normal * radius * rng.uniform(0.30, 0.48),
        )
        particle = bpy.context.object
        particle.name = "REFERENCE_QC71336_FOREIGN_MATERIAL"
        particle.data.name = f"{particle.name}_MESH"
    else:
        mesh = create_irregular_flat_foreign_mesh("REFERENCE_QC71336_FOREIGN_MATERIAL", radius, rng)
        particle = bpy.data.objects.new("REFERENCE_QC71336_FOREIGN_MATERIAL", mesh)
        bpy.context.collection.objects.link(particle)
        particle.location = world_point + world_normal * radius * rng.uniform(0.09, 0.18)
    particle.rotation_euler = world_normal.to_track_quat("Z", "Y").to_euler()
    particle_spin = rng.uniform(0.0, math.tau)
    particle.rotation_euler.rotate_axis("Z", particle_spin)
    if use_particle_shape:
        particle.scale = (
            particle.scale.x * rng.uniform(0.86, 1.18),
            particle.scale.y * rng.uniform(0.86, 1.18),
            particle.scale.z * rng.uniform(0.86, 1.18),
        )
    else:
        particle.scale = (
            particle.scale.x * rng.uniform(0.70, 1.85),
            particle.scale.y * rng.uniform(0.35, 1.10),
            particle.scale.z * rng.uniform(0.08, 0.22),
        )
    particle.pass_index = 1
    for poly in particle.data.polygons:
        poly.use_smooth = True
    mat, subtype = make_white_foreign_material_mat(f"{particle.name}_MAT", rng)
    particle.data.materials.clear()
    particle.data.materials.append(mat)
    bpy.context.view_layer.update()
    return {
        "defect_type": "foreign_material",
        "defect_type_internal": "foreign_material",
        "defect_type_canonical": "foreign_material",
        "subtype": subtype,
        "shape": "ico_particle" if use_particle_shape else "irregular_flat_chip",
        "dot_object": particle.name,
        "foreign_object": particle.name,
        "anchor_polygon_index": poly_index,
        "anchor_side": "front" if anchor["anchor_band"] == "front_face" else "back",
        "radius": radius,
        "depth": depth,
        "radius_floor": FOREIGN_MATERIAL_VISIBLE_RADIUS_FLOOR,
        "radius_ceiling": FOREIGN_MATERIAL_VISIBLE_RADIUS_CEILING,
        "size_tier": size_tier,
        "world_point": [float(world_point.x), float(world_point.y), float(world_point.z)],
        "world_normal": [float(world_normal.x), float(world_normal.y), float(world_normal.z)],
        "anchor_band": anchor["anchor_band"],
        "anchor_score": anchor["score"],
        "anchor_planar_score": anchor["planar_score"],
        "anchor_local_planarity": anchor["local_planarity"],
        "anchor_view_alignment": anchor["view_alignment"],
        "anchor_local_xy": [anchor["local_x"], anchor["local_y"]],
        "anchor_projected_xy": anchor["projected_xy"],
        "anchor_xy_ratio": [anchor["x_ratio"], anchor["y_ratio"]],
        "particle_spin_radians": particle_spin,
        "material_version": FOREIGN_MATERIAL_VERSION,
        "center_tracking": anchor["anchor_band"] == "back_face",
        "seed": mesh_seed,
    }


def add_same_type_foreign_materials(
    imported_objects,
    scene,
    camera,
    camera_presets,
    image_offset,
    seed,
    radius_scale,
    depth_scale,
    allowed_sides,
    min_count,
    max_count,
):
    min_count = max(1, int(min_count))
    max_count = max(1, int(max_count))
    if min_count > max_count:
        raise ValueError("min_count cannot be greater than max_count")
    defect_count = random.Random(seed + image_offset).randint(min_count, max_count)
    clear_reference_black_dot_objects()
    defects = []
    for instance_index in range(defect_count):
        defect = add_foreign_material(
            imported_objects,
            scene,
            camera,
            camera_presets,
            image_offset + instance_index * 10000,
            seed + instance_index * 100000,
            radius_scale,
            depth_scale,
            allowed_sides,
            clear_existing=False,
            force_stable_particle=True,
        )
        defect["instance_index"] = instance_index
        defects.append(defect)
    points = [Vector(item["world_point"]) for item in defects if item.get("world_point")]
    center = sum(points, Vector((0.0, 0.0, 0.0))) / max(1, len(points)) if points else None
    return {
        "defect_type": "foreign_material",
        "defect_type_internal": "foreign_material",
        "defect_type_canonical": "foreign_material",
        "defect_types": ["foreign_material" for _ in defects],
        "defect_count": len(defects),
        "defect_count_min": int(min_count),
        "defect_count_max": int(max_count),
        "defects": defects,
        "mask_objects": [item["dot_object"] for item in defects if item.get("dot_object")],
        "dot_object": defects[0].get("dot_object") if defects else None,
        "anchor_side": defects[0].get("anchor_side", "front") if defects else "front",
        "world_point": [float(center.x), float(center.y), float(center.z)] if center else None,
        "generation_mode": "same_type_multi_defect",
    }


def build_qc71336_white_material(
    name,
    base_color,
    roughness,
    specular,
    coat_weight,
    coat_roughness,
    bump_strength,
    variation_scale,
):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = find_principled(mat)
    if bsdf is None:
        raise RuntimeError("Principled BSDF node not found for QC7-1336 white material.")
    bsdf.inputs["Base Color"].default_value = base_color
    bsdf.inputs["Roughness"].default_value = roughness
    spec_name = "Specular IOR Level" if "Specular IOR Level" in bsdf.inputs else "Specular"
    bsdf.inputs[spec_name].default_value = specular
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = coat_weight
    elif "Clearcoat" in bsdf.inputs:
        bsdf.inputs["Clearcoat"].default_value = coat_weight
    if "Coat Roughness" in bsdf.inputs:
        bsdf.inputs["Coat Roughness"].default_value = coat_roughness
    elif "Clearcoat Roughness" in bsdf.inputs:
        bsdf.inputs["Clearcoat Roughness"].default_value = coat_roughness
    add_subtle_roughness_variation(mat, bump_strength=bump_strength, scale=variation_scale)
    return mat


def build_qc71336_two_zone_materials():
    main_plane_mat = build_qc71336_white_material(
        name="REFERENCE_QC71336_WHITE_MAIN_PLANE",
        base_color=(0.688, 0.693, 0.683, 1.0),
        roughness=0.690,
        specular=0.104,
        coat_weight=0.015,
        coat_roughness=0.430,
        bump_strength=0.00110,
        variation_scale=930.0,
    )
    edge_wall_mat = build_qc71336_white_material(
        name="REFERENCE_QC71336_WHITE_EDGE_WALL",
        base_color=(0.713, 0.718, 0.708, 1.0),
        roughness=0.630,
        specular=0.129,
        coat_weight=0.020,
        coat_roughness=0.370,
        bump_strength=0.00118,
        variation_scale=870.0,
    )
    return main_plane_mat, edge_wall_mat


def assign_qc71336_white_material(imported_objects):
    main_plane_mat, edge_wall_mat = build_qc71336_two_zone_materials()
    for obj in imported_objects:
        mesh = obj.data
        mesh.materials.clear()
        mesh.materials.append(main_plane_mat)
        mesh.materials.append(edge_wall_mat)

        bb_world = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        min_corner = Vector(
            (min(v.x for v in bb_world), min(v.y for v in bb_world), min(v.z for v in bb_world))
        )
        max_corner = Vector(
            (max(v.x for v in bb_world), max(v.y for v in bb_world), max(v.z for v in bb_world))
        )
        center = (min_corner + max_corner) * 0.5
        dims = max_corner - min_corner
        half_x = max(float(abs(dims.x)) * 0.5, 1e-6)
        half_y = max(float(abs(dims.y)) * 0.5, 1e-6)

        for poly in mesh.polygons:
            world_center = obj.matrix_world @ poly.center
            world_normal = (obj.matrix_world.to_3x3() @ poly.normal).normalized()
            x_ratio = abs(float(world_center.x - center.x)) / half_x
            y_ratio = abs(float(world_center.y - center.y)) / half_y
            planar_score = abs(float(world_normal.z))
            in_main_window = x_ratio < 0.62 and y_ratio < 0.47
            is_main_plane_region = planar_score > 0.40 and in_main_window
            poly.material_index = 0 if is_main_plane_region else 1
    bpy.context.view_layer.update()
    return {
        "main_plane_material": main_plane_mat.name,
        "edge_wall_material": edge_wall_mat.name,
    }


def render_still(path):
    scene = bpy.context.scene
    scene.render.filepath = str(path)
    bpy.context.view_layer.update()
    bpy.ops.render.render(write_still=True)


def ensure_black_dot_label_nodes():
    scene = bpy.context.scene
    view_layer = bpy.context.view_layer
    view_layer.use_pass_object_index = True
    scene.use_nodes = True
    tree = scene.node_tree
    nodes = tree.nodes
    links = tree.links

    render_layers = nodes.get("REFERENCE_LABEL_RENDER_LAYERS")
    if render_layers is None:
        render_layers = nodes.new("CompositorNodeRLayers")
        render_layers.name = "REFERENCE_LABEL_RENDER_LAYERS"
        render_layers.label = "REFERENCE_LABEL_RENDER_LAYERS"

    id_mask = nodes.get("REFERENCE_BLACK_DOT_ID_MASK")
    if id_mask is None:
        id_mask = nodes.new("CompositorNodeIDMask")
        id_mask.name = "REFERENCE_BLACK_DOT_ID_MASK"
        id_mask.label = "REFERENCE_BLACK_DOT_ID_MASK"
    id_mask.index = 1
    id_mask.use_antialiasing = True

    viewer = nodes.get("REFERENCE_BLACK_DOT_MASK_VIEWER")
    if viewer is None:
        viewer = nodes.new("CompositorNodeViewer")
        viewer.name = "REFERENCE_BLACK_DOT_MASK_VIEWER"
        viewer.label = "REFERENCE_BLACK_DOT_MASK_VIEWER"
    viewer.use_alpha = True

    composite = nodes.get("Composite")
    if composite is None:
        composite = nodes.new("CompositorNodeComposite")

    def ensure_link(output_socket, input_socket):
        for link in links:
            if link.from_socket == output_socket and link.to_socket == input_socket:
                return
        links.new(output_socket, input_socket)

    index_output = render_layers.outputs.get("IndexOB")
    if index_output is None:
        for socket in render_layers.outputs:
            if "Index" in socket.name:
                index_output = socket
                break
    if index_output is None:
        available = ", ".join(socket.name for socket in render_layers.outputs)
        raise RuntimeError(f"Could not find object-index render pass output. Available outputs: {available}")

    ensure_link(render_layers.outputs["Image"], composite.inputs["Image"])
    ensure_link(index_output, id_mask.inputs["ID value"])
    ensure_link(id_mask.outputs["Alpha"], viewer.inputs["Image"])
    return viewer


def build_binary_mask_pixels(mask_values, width, height, threshold=0.5):
    binary = [0] * (width * height)
    for idx in range(width * height):
        if mask_values[idx * 4] >= threshold:
            binary[idx] = 1
    return binary


def bbox_from_binary_mask(binary, width, height):
    xs = []
    ys = []
    for idx, value in enumerate(binary):
        if value <= 0:
            continue
        x = idx % width
        y_bottom = idx // width
        y = height - 1 - y_bottom
        xs.append(x)
        ys.append(y)
    if not xs:
        return None
    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)
    return {
        "xyxy": [int(min_x), int(min_y), int(max_x), int(max_y)],
        "xywh": [
            int(min_x),
            int(min_y),
            int(max_x - min_x + 1),
            int(max_y - min_y + 1),
        ],
        "area_pixels": int(sum(binary)),
    }


def save_image_from_rgba_pixels(path, width, height, rgba_pixels, image_name):
    existing = bpy.data.images.get(image_name)
    if existing is not None:
        bpy.data.images.remove(existing)
    image = bpy.data.images.new(image_name, width=width, height=height, alpha=True, float_buffer=False)
    image.file_format = "PNG"
    image.pixels = rgba_pixels
    image.filepath_raw = str(path)
    image.save()
    bpy.data.images.remove(image)


def save_binary_mask_image(path, binary, width, height, image_name):
    rgba = [0.0] * (width * height * 4)
    for idx, value in enumerate(binary):
        base = idx * 4
        val = 1.0 if value else 0.0
        rgba[base] = val
        rgba[base + 1] = val
        rgba[base + 2] = val
        rgba[base + 3] = 1.0
    save_image_from_rgba_pixels(path, width, height, rgba, image_name)


def save_mask_overlay(rgb_path, overlay_path, binary, width, height, bbox, image_name):
    rgb_image = bpy.data.images.load(str(rgb_path), check_existing=False)
    rgb_pixels = list(rgb_image.pixels[:])
    overlay_pixels = rgb_pixels[:]

    for idx, value in enumerate(binary):
        if value <= 0:
            continue
        base = idx * 4
        overlay_pixels[base] = min(1.0, overlay_pixels[base] * 0.35 + 0.65)
        overlay_pixels[base + 1] = overlay_pixels[base + 1] * 0.35
        overlay_pixels[base + 2] = overlay_pixels[base + 2] * 0.35

    if bbox is not None:
        min_x, min_y, max_x, max_y = bbox["xyxy"]

        def set_overlay_pixel(x, y_top, color):
            if x < 0 or x >= width or y_top < 0 or y_top >= height:
                return
            y_bottom = height - 1 - y_top
            base = (y_bottom * width + x) * 4
            overlay_pixels[base] = color[0]
            overlay_pixels[base + 1] = color[1]
            overlay_pixels[base + 2] = color[2]
            overlay_pixels[base + 3] = 1.0

        for x in range(min_x, max_x + 1):
            set_overlay_pixel(x, min_y, (0.1, 1.0, 0.1))
            set_overlay_pixel(x, max_y, (0.1, 1.0, 0.1))
        for y in range(min_y, max_y + 1):
            set_overlay_pixel(min_x, y, (0.1, 1.0, 0.1))
            set_overlay_pixel(max_x, y, (0.1, 1.0, 0.1))

    save_image_from_rgba_pixels(overlay_path, width, height, overlay_pixels, image_name)
    bpy.data.images.remove(rgb_image)


def export_black_dot_label_artifacts(mask_path, overlay_path):
    viewer_image = bpy.data.images.get("Viewer Node")
    if viewer_image is None:
        raise RuntimeError("Viewer Node image not available for black-dot lightweight labels.")
    width, height = viewer_image.size
    mask_values = list(viewer_image.pixels[:])
    binary = build_binary_mask_pixels(mask_values, width, height, threshold=0.5)
    bbox = bbox_from_binary_mask(binary, width, height)
    save_binary_mask_image(mask_path, binary, width, height, "REFERENCE_BLACK_DOT_MASK_EXPORT")
    return {
        "binary": binary,
        "bbox": bbox,
        "width": width,
        "height": height,
    }


def find_background_node(world):
    if world is None or not world.use_nodes or world.node_tree is None:
        return None
    for node in world.node_tree.nodes:
        if node.type == "BACKGROUND":
            return node
    return None


def make_emission_mask_material(name="REFERENCE_BLACK_DOT_MASK_MAT"):
    existing = bpy.data.materials.get(name)
    if existing is not None:
        return existing
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    emission = tree.nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    emission.inputs["Strength"].default_value = 1.0
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return mat


def render_objects_binary_mask(mask_path, object_names):
    scene = bpy.context.scene
    object_names = list(object_names)
    targets = [bpy.data.objects.get(name) for name in object_names]
    if any(obj is None for obj in targets):
        missing = [name for name, obj in zip(object_names, targets) if obj is None]
        raise RuntimeError(f"Defect object not found for mask render: {missing}")

    original_engine = scene.render.engine
    original_samples = int(getattr(scene.cycles, "samples", 1))
    original_adaptive = bool(getattr(scene.cycles, "use_adaptive_sampling", False))
    original_filepath = scene.render.filepath
    original_hide_render = {obj.name: bool(obj.hide_render) for obj in bpy.data.objects}
    original_target_materials = {obj.name: [mat for mat in obj.data.materials] for obj in targets}
    world = scene.world
    background = find_background_node(world)
    original_bg_color = None
    original_bg_strength = None
    if background is not None:
        original_bg_color = tuple(background.inputs["Color"].default_value)
        original_bg_strength = float(background.inputs["Strength"].default_value)

    mask_mat = make_emission_mask_material()

    try:
        for obj in bpy.data.objects:
            if obj.type == "MESH":
                obj.hide_render = obj.name not in object_names
        for obj in targets:
            obj.hide_render = False
            obj.data.materials.clear()
            obj.data.materials.append(mask_mat)
        if background is not None:
            background.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
            background.inputs["Strength"].default_value = 1.0
        scene.render.engine = "CYCLES"
        scene.cycles.samples = 1
        scene.cycles.use_adaptive_sampling = False
        render_still(mask_path)
    finally:
        scene.render.engine = original_engine
        scene.cycles.samples = original_samples
        scene.cycles.use_adaptive_sampling = original_adaptive
        scene.render.filepath = original_filepath
        if background is not None and original_bg_color is not None and original_bg_strength is not None:
            background.inputs["Color"].default_value = original_bg_color
            background.inputs["Strength"].default_value = original_bg_strength
        for obj in targets:
            obj.data.materials.clear()
            for mat in original_target_materials.get(obj.name, []):
                obj.data.materials.append(mat)
        for obj in bpy.data.objects:
            if obj.name in original_hide_render:
                obj.hide_render = original_hide_render[obj.name]
        bpy.context.view_layer.update()


def render_black_dot_binary_mask(mask_path, dot_object_name):
    render_objects_binary_mask(mask_path, [dot_object_name])


def load_binary_mask_from_image(mask_path, threshold=0.5):
    mask_image = bpy.data.images.load(str(mask_path), check_existing=False)
    width, height = mask_image.size
    pixels = list(mask_image.pixels[:])
    binary = build_binary_mask_pixels(pixels, width, height, threshold=threshold)
    bpy.data.images.remove(mask_image)
    return binary, width, height


def safe_pack_all():
    try:
        bpy.ops.file.pack_all()
        return None
    except Exception as exc:
        return str(exc)


def save_blend_copy(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pack_error = safe_pack_all()
    bpy.context.view_layer.update()
    bpy.ops.wm.save_as_mainfile(filepath=str(path), copy=True)
    return pack_error


def capture_light_summary():
    lights = []
    for obj in bpy.data.objects:
        if obj.type != "LIGHT":
            continue
        lights.append(
            {
                "name": obj.name,
                "type": obj.data.type,
                "energy": float(getattr(obj.data, "energy", 0.0)),
                "color": tuple(float(v) for v in getattr(obj.data, "color", (1.0, 1.0, 1.0))),
            }
        )
    return lights


def snapshot_light_state():
    state = {}
    for obj in bpy.data.objects:
        if obj.type != "LIGHT":
            continue
        light = obj.data
        state[obj.name] = {
            "energy": float(getattr(light, "energy", 0.0)),
            "color": tuple(float(v) for v in getattr(light, "color", (1.0, 1.0, 1.0))),
            "size": float(getattr(light, "size", 0.0)) if hasattr(light, "size") else None,
            "size_y": float(getattr(light, "size_y", 0.0)) if hasattr(light, "size_y") else None,
        }
    return state


def restore_light_state(state):
    for obj in bpy.data.objects:
        if obj.type != "LIGHT" or obj.name not in state:
            continue
        light = obj.data
        light_state = state[obj.name]
        if hasattr(light, "energy") and light_state["energy"] is not None:
            light.energy = light_state["energy"]
        if getattr(light, "color", None) is not None and light_state["color"] is not None:
            light.color = light_state["color"]
        if hasattr(light, "size") and light_state["size"] is not None:
            light.size = light_state["size"]
        if hasattr(light, "size_y") and light_state["size_y"] is not None:
            light.size_y = light_state["size_y"]


def apply_validation_variation(camera, base_camera_location, base_camera_rotation, base_light_state, image_offset):
    restore_light_state(base_light_state)

    camera_shifts = [
        (0.0, 0.0, 0.0, 0.0),
        (0.004, -0.006, 0.008, -0.35),
        (-0.005, 0.004, -0.006, 0.28),
        (0.006, 0.003, -0.003, -0.22),
        (-0.004, -0.004, 0.005, 0.18),
    ]
    key_fill_scales = [
        (1.00, 1.00),
        (1.02, 0.98),
        (0.99, 1.01),
        (1.01, 0.99),
        (0.985, 1.015),
    ]

    shift = camera_shifts[image_offset % len(camera_shifts)]
    camera.location = base_camera_location + Vector(shift[:3])
    camera.rotation_euler = base_camera_rotation.copy()
    camera.rotation_euler.rotate_axis("Z", math.radians(shift[3]))

    key_scale, fill_scale = key_fill_scales[image_offset % len(key_fill_scales)]
    for obj in bpy.data.objects:
        if obj.type != "LIGHT" or obj.name not in base_light_state:
            continue
        light = obj.data
        base_energy = base_light_state[obj.name]["energy"]
        if obj.name == "Area.003":
            light.energy = base_energy * key_scale
        elif obj.name == "Area.005":
            light.energy = base_energy * ((key_scale + fill_scale) * 0.5)
        else:
            light.energy = base_energy * fill_scale
    bpy.context.view_layer.update()


def main():
    args = parse_args()
    if args.enable_black_dot and args.enable_foreign_material:
        raise ValueError("--enable_black_dot and --enable_foreign_material are mutually exclusive.")
    output_dir = mkdir(Path(args.output).resolve())
    rgb_dir = mkdir(output_dir / "rgb")
    mask_dir = mkdir(output_dir / "mask")
    overlay_dir = mkdir(output_dir / "overlay")
    yolo_dir = mkdir(output_dir / "labels_yolo")
    blend_dir = mkdir(output_dir / "blend_debug")

    bpy.ops.wm.open_mainfile(filepath=str(Path(args.blend).resolve()))
    ensure_background_support()
    tune_reference_lighting_for_white()

    primary_objects = pick_primary_mesh_objects()
    ensure_camera_for_objects(primary_objects, args.width, args.height)
    gpu_info = configure_cycles_gpu(args.samples)

    for obj in primary_objects:
        obj.hide_render = True
        obj.hide_viewport = True

    imported = append_blend_objects(Path(args.model_blend).resolve())
    fit_objects_to_reference(imported, primary_objects)
    original_materials = summarize_existing_materials(imported)
    white_real_domain_material_tuning = None
    white_texture_material_enhancement = None
    gray_override_material = None
    if args.use_gray_override:
        gray_override_material = apply_gray_override_material(imported)
        tune_reference_lighting_for_gray_override()
    else:
        white_real_domain_material_tuning = tune_prebuilt_white_materials_for_real_domain(imported)
        if not args.disable_white_texture_enhancement:
            white_texture_material_enhancement = enhance_prebuilt_white_materials_with_texture(imported)
    assigned_materials = summarize_existing_materials(imported)
    camera = ensure_camera_for_objects(imported, args.width, args.height)
    camera_presets = build_two_sided_camera_presets(imported)
    if not args.use_gray_override:
        tune_white_oblique_camera_and_lighting(imported, camera, camera_presets)
    apply_camera_preset(camera, camera_presets["front_face"])
    base_light_state = snapshot_light_state()
    base_exposure = float(bpy.context.scene.view_settings.exposure)

    samples = []
    pack_error = None
    for image_offset in range(args.num):
        image_index = args.start_index + image_offset
        restore_light_state(base_light_state)
        bpy.context.scene.view_settings.exposure = base_exposure
        initial_band = "front_face" if (args.anchor_sides or ["front"])[0] == "front" else "back_face"
        apply_camera_preset(camera, camera_presets[initial_band])
        defect_info = None
        defect_type = "none"
        if args.enable_black_dot:
            defect_type = "black_dot"
            defect_info = add_black_dot(
                imported,
                bpy.context.scene,
                camera,
                camera_presets,
                image_offset,
                args.black_dot_seed,
                args.black_dot_radius_scale,
                args.black_dot_depth_scale,
                args.anchor_sides,
            )
        elif args.enable_foreign_material:
            defect_type = "foreign_material"
            defect_count_min = max(1, int(args.defect_count_min or 1))
            defect_count_max = max(1, int(args.defect_count_max or 1))
            if defect_count_min > defect_count_max:
                raise ValueError("--defect_count_min cannot be greater than --defect_count_max")
            if defect_count_max > 1:
                defect_info = add_same_type_foreign_materials(
                    imported,
                    bpy.context.scene,
                    camera,
                    camera_presets,
                    image_offset,
                    args.foreign_material_seed,
                    args.foreign_material_radius_scale,
                    args.foreign_material_depth_scale,
                    args.anchor_sides,
                    defect_count_min,
                    defect_count_max,
                )
            else:
                defect_info = add_foreign_material(
                    imported,
                    bpy.context.scene,
                    camera,
                    camera_presets,
                    image_offset,
                    args.foreign_material_seed,
                    args.foreign_material_radius_scale,
                    args.foreign_material_depth_scale,
                    args.anchor_sides,
                )
        if defect_info is not None:
            view_transform = build_object_view_transform(args, defect_info)
            if view_transform["enabled"]:
                camera_band = "front_face" if view_transform["camera_side"] == "front" else "back_face"
                apply_camera_preset(camera, camera_presets[camera_band])
                configure_backdrop_for_anchor_band(camera_band)
                apply_object_view_transform(imported, defect_info, view_transform)
                projected = world_to_camera_view(bpy.context.scene, camera, Vector(defect_info["world_point"]))
                tracking_camera = {
                    "enabled": False,
                    "reason": "object_transform_keep_camera",
                    "defect_projected_xy": [float(projected.x), float(projected.y)],
                    "visible_after_follow": bool(projected.z > 0.0 and 0.08 <= projected.x <= 0.92 and 0.08 <= projected.y <= 0.92),
                }
            else:
                tracking_camera = apply_black_dot_tracking_view(camera, camera_presets, defect_info)
                apply_black_dot_tracking_lighting(base_light_state, base_exposure, defect_info)
            defect_info["camera_tracking"] = tracking_camera
            defect_info["camera_follow"] = {
                "anchor_side": defect_info.get("anchor_side", "front"),
                "camera_side": view_transform["camera_side"] if view_transform["enabled"] else defect_info.get("anchor_side", "front"),
                "projected_xy_after_follow": [
                    round(float(tracking_camera["defect_projected_xy"][0]), 5),
                    round(float(tracking_camera["defect_projected_xy"][1]), 5),
                ],
                "visible_after_follow": bool(tracking_camera.get("visible_after_follow", False)),
            }
            defect_info["view_transform"] = view_transform
        else:
            clear_reference_black_dot_objects()
        render_path = rgb_dir / f"{image_index:06d}.png"
        render_still(render_path)
        label_info = None
        if defect_info is not None:
            mask_path = mask_dir / f"{image_index:06d}.png"
            overlay_path = overlay_dir / f"{image_index:06d}.png"
            label_path = yolo_dir / f"{image_index:06d}.txt"
            mask_objects = defect_info.get("mask_objects") or [defect_info["dot_object"]]
            render_objects_binary_mask(mask_path, mask_objects)
            binary, mask_width, mask_height = load_binary_mask_from_image(mask_path, threshold=0.5)
            bbox = bbox_from_binary_mask(binary, mask_width, mask_height)
            save_mask_overlay(
                render_path,
                overlay_path,
                binary,
                mask_width,
                mask_height,
                bbox,
                "REFERENCE_DEFECT_OVERLAY_EXPORT",
            )
            label_text = ""
            defect_bboxes = []
            if defect_info.get("defects"):
                class_id = 1 if defect_type == "foreign_material" else 0
                for item in defect_info.get("defects", []):
                    object_name = item.get("dot_object")
                    if not object_name:
                        continue
                    tmp_mask_path = mask_dir / f"{image_index:06d}_{defect_type}_{item.get('instance_index', 0):02d}_tmp.png"
                    render_objects_binary_mask(tmp_mask_path, [object_name])
                    tmp_binary, tmp_width, tmp_height = load_binary_mask_from_image(tmp_mask_path, threshold=0.5)
                    tmp_bbox = bbox_from_binary_mask(tmp_binary, tmp_width, tmp_height)
                    if tmp_bbox is not None and tmp_bbox["xywh"][2] > 0 and tmp_bbox["xywh"][3] > 0:
                        yolo_bbox = bbox_to_yolo(bpy.context.scene, tmp_bbox)
                        label_text += (
                            f"{class_id} {yolo_bbox[0]:.6f} {yolo_bbox[1]:.6f} "
                            f"{yolo_bbox[2]:.6f} {yolo_bbox[3]:.6f}\n"
                        )
                        defect_bboxes.append(
                            {
                                "defect_type": defect_type,
                                "class_id": class_id,
                                "bbox": tmp_bbox,
                                "instance_index": item.get("instance_index"),
                            }
                        )
                    tmp_mask_path.unlink(missing_ok=True)
            elif bbox is not None and bbox["xywh"][2] > 0 and bbox["xywh"][3] > 0:
                yolo_bbox = bbox_to_yolo(bpy.context.scene, bbox)
                class_id = 1 if defect_type == "foreign_material" else 0
                label_text = f"{class_id} {yolo_bbox[0]:.6f} {yolo_bbox[1]:.6f} {yolo_bbox[2]:.6f} {yolo_bbox[3]:.6f}\n"
            label_path.write_text(label_text, encoding="utf-8")
            label_info = {
                "mask": str(mask_path.relative_to(output_dir)),
                "overlay": str(overlay_path.relative_to(output_dir)),
                "label_yolo": str(label_path.relative_to(output_dir)),
                "bbox": bbox,
                "defect_bboxes": defect_bboxes,
                "mask_width": mask_width,
                "mask_height": mask_height,
            }

        blend_rel = None
        if args.save_blend and image_index == args.start_index:
            blend_path = blend_dir / f"{image_index:06d}_scene.blend"
            pack_error = save_blend_copy(blend_path)
            blend_rel = str(blend_path.relative_to(output_dir))

        samples.append(
            {
                "image_id": f"{image_index:06d}",
                "rgb": str(render_path.relative_to(output_dir)),
                "schema_version": "reference_normal_debug_v1",
                "baseline_version": BASELINE_VERSION,
                "task_type": f"reference_scene_{defect_type}_validation" if defect_info is not None else "reference_scene_normal_part_validation",
                "model_name": "QC7-1336",
                "geometry_profile": "qc7_1336_geometry",
                "appearance_profile": (
                    "qc71336_gray_override_profile"
                    if args.use_gray_override
                    else "qc71336_white_textured_prebuilt_profile"
                    if not args.disable_white_texture_enhancement
                    else "qc71336_white_prebuilt_profile"
                ),
                "material_family": (
                    "qc71336_gray_override_plastic"
                    if args.use_gray_override
                    else "prebuilt_authored_white_plastic_textured"
                    if not args.disable_white_texture_enhancement
                    else "prebuilt_authored_white_plastic"
                ),
                "defect_type": defect_type,
                "defect_type_internal": defect_type if defect_info is not None else None,
                "defect_type_canonical": defect_type if defect_info is not None else None,
                "has_defect": defect_info is not None,
                "reference_scene": str(Path(args.blend).resolve()),
                "model_blend": str(Path(args.model_blend).resolve()),
                "camera_name": camera.name,
                "camera_location": [float(camera.location.x), float(camera.location.y), float(camera.location.z)],
                "camera_rotation_euler": [
                    float(camera.rotation_euler.x),
                    float(camera.rotation_euler.y),
                    float(camera.rotation_euler.z),
                ],
                "original_materials": original_materials,
                "assigned_materials": assigned_materials,
                "gray_override_enabled": bool(args.use_gray_override),
                "gray_override_material": gray_override_material,
                "white_real_domain_material_tuning": white_real_domain_material_tuning,
                "white_texture_material_enhancement": white_texture_material_enhancement,
                "black_dot_version": BLACK_DOT_VERSION if args.enable_black_dot else None,
                "foreign_material_version": FOREIGN_MATERIAL_VERSION if args.enable_foreign_material else None,
                "black_dot": defect_info if args.enable_black_dot else None,
                "foreign_material": defect_info if args.enable_foreign_material else None,
                "lightweight_label": label_info,
                "blend_file": blend_rel,
            }
        )

    metadata = {
        "script": str(Path(__file__).resolve()),
        "schema_version": "reference_normal_debug_v1",
        "baseline_version": BASELINE_VERSION,
        "baseline_summary": BASELINE_SUMMARY,
        "task_type": (
            "reference_scene_foreign_material_validation"
            if args.enable_foreign_material
            else "reference_scene_black_dot_validation"
            if args.enable_black_dot
            else "reference_scene_normal_part_validation"
        ),
        "reference_scene": str(Path(args.blend).resolve()),
        "model_blend": str(Path(args.model_blend).resolve()),
        "model_name": "QC7-1336",
        "geometry_profile": "qc7_1336_geometry",
        "appearance_profile": (
            "qc71336_gray_override_profile"
            if args.use_gray_override
            else "qc71336_white_textured_prebuilt_profile"
            if not args.disable_white_texture_enhancement
            else "qc71336_white_prebuilt_profile"
        ),
        "material_family": (
            "qc71336_gray_override_plastic"
            if args.use_gray_override
            else "prebuilt_authored_white_plastic_textured"
            if not args.disable_white_texture_enhancement
            else "prebuilt_authored_white_plastic"
        ),
        "defect_type": "foreign_material" if args.enable_foreign_material else "black_dot" if args.enable_black_dot else "none",
        "defect_type_internal": "foreign_material" if args.enable_foreign_material else "black_dot" if args.enable_black_dot else None,
        "defect_type_canonical": "foreign_material" if args.enable_foreign_material else "black_dot" if args.enable_black_dot else None,
        "black_dot_version": BLACK_DOT_VERSION if args.enable_black_dot else None,
        "foreign_material_version": FOREIGN_MATERIAL_VERSION if args.enable_foreign_material else None,
        "render_width": args.width,
        "render_height": args.height,
        "cycles_samples": args.samples,
        "enable_black_dot": args.enable_black_dot,
        "enable_foreign_material": args.enable_foreign_material,
        "defect_count_min": max(1, int(args.defect_count_min or 1)),
        "defect_count_max": max(1, int(args.defect_count_max or 1)),
        "gpu_info": gpu_info,
        "lighting": capture_light_summary(),
        "white_real_domain_material_tuning": white_real_domain_material_tuning,
        "white_texture_material_enhancement": white_texture_material_enhancement,
        "white_texture_enhancement_enabled": bool(not args.disable_white_texture_enhancement and not args.use_gray_override),
        "gray_real_domain_tuning": bool(args.use_gray_override),
        "pack_error": pack_error,
        "samples": samples,
        "notes": [
            f"Baseline locked as {BASELINE_VERSION}.",
            BASELINE_SUMMARY,
            "Uses the manually authored materials embedded in QC7-1336-white.blend, then adds a procedural white texture enhancement layer unless disabled.",
            "Only objects whose names contain QC8-8511-000N301002ST0101 are kept for rendering from the appended model blend.",
            "Camera was pulled back slightly to preserve more of the part silhouette in-frame.",
            "White prebuilt mode applies a real-domain material and lighting correction to reduce the previous over-bright studio-render look.",
            "White textured mode adds procedural roughness, fine bump, and mild grey-white color variation to improve molded-plastic roughness readability.",
            "Gray override now targets the darker, slightly warm-gray appearance seen in the QC7-1336 real reference photos.",
            "When enabled, black-dot mode adds one main embedded dot plus a subtle local contamination patch; RGB keeps both while mask/bbox/YOLO target the main dot only.",
        ],
    }
    metadata_path = output_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
