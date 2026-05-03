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

BASELINE_VERSION = "qc71336_black_prebuilt_reference_baseline_v2"
BASELINE_SUMMARY = (
    "QC7-1336 black prebuilt-material normal-part baseline in moxing2.blend with a cleaned direct-model workflow, "
    "a more front-facing camera angle, and the manually authored materials from QC7-1336-black.blend."
)
FOREIGN_MATERIAL_VERSION = "qc71336_black_prebuilt_foreign_material_v3"
SPLAY_VERSION = "qc71336_black_prebuilt_splay_v1"
MODEL_OBJECT_KEYWORDS = ("QC8-8511-000N301002ST0101",)
FOREIGN_MATERIAL_VISIBLE_RADIUS_FLOOR = 0.0072
FOREIGN_MATERIAL_BACK_VISIBLE_RADIUS_FLOOR = 0.0145
SPLAY_VISIBLE_LENGTH_FLOOR = 0.0380
SPLAY_VISIBLE_WIDTH_FLOOR = 0.0022
SPLAY_VISIBLE_ALPHA_FLOOR = 0.0920
SPLAY_VISIBLE_HALO_ALPHA_FLOOR = 0.0520
SPLAY_DIRECTIONAL_RADIUS_X_FLOOR = 0.444968
SPLAY_DIRECTIONAL_RADIUS_Y_FLOOR = 0.024609
SPLAY_DIRECTIONAL_BRIGHT_TINT_FLOOR = 0.0520


def parse_args():
    parser = argparse.ArgumentParser(
        description="Render one QC7-1336 black prebuilt-material normal reference-scene image in moxing2.blend."
    )
    parser.add_argument("--blend", required=True)
    parser.add_argument("--model_blend", default=r"E:\BlenderProject\BlenderProc\assets\models\QC7-1336-black.blend")
    parser.add_argument("--output", required=True)
    parser.add_argument("--num", type=int, default=1)
    parser.add_argument("--start_index", type=int, default=0)
    parser.add_argument("--width", type=int, default=1536)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--samples", type=int, default=256)
    parser.add_argument("--save_blend", action="store_true")
    parser.add_argument(
        "--defect_type",
        choices=["foreign_material", "splay", "foreign_material_splay"],
        required=True,
        help="Reference-scene defect type to generate.",
    )
    parser.add_argument("--defect_seed", type=int, default=23)
    parser.add_argument("--anchor_sides", nargs="+", choices=["front", "back"], default=["front"])
    parser.add_argument("--debug_splay_strong", action="store_true")
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


def ensure_camera_for_objects(objects, width, height, side="front"):
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

    position_camera_for_anchor_side(camera, objects, side)

    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    bpy.context.view_layer.update()
    return camera


def position_camera_for_anchor_side(camera, objects, side="front"):
    bb_min, bb_max = world_bbox(objects)
    center = (bb_min + bb_max) * 0.5
    span = bb_max - bb_min
    max_dim = max(float(abs(span.x)), float(abs(span.y)), float(abs(span.z)), 1e-3)
    z_sign = 1.0 if side == "front" else -1.0
    focus_target = center + Vector((0.0, 0.015 * max_dim, 0.0))
    location = center + Vector((0.0, -0.15 * max_dim, z_sign * 2.58 * max_dim))
    direction = focus_target - location
    camera.location = location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    camera.data.shift_x = 0.0
    camera.data.shift_y = 0.085 if side == "front" else 0.038
    bpy.context.view_layer.update()


def refine_camera_shift_for_defect(camera, scene, world_point, desired_x=0.50, desired_y=0.50, max_delta=0.16):
    projected = world_to_camera_view(scene, camera, world_point)
    origin_shift_x = float(camera.data.shift_x)
    origin_shift_y = float(camera.data.shift_y)
    camera.data.shift_x = max(-0.22, min(0.22, origin_shift_x + (float(projected.x) - desired_x) * 0.68))
    camera.data.shift_y = max(-0.22, min(0.22, origin_shift_y + (float(projected.y) - desired_y) * 0.68))
    if abs(camera.data.shift_x - origin_shift_x) > max_delta:
        camera.data.shift_x = origin_shift_x + max_delta * (1 if camera.data.shift_x > origin_shift_x else -1)
    if abs(camera.data.shift_y - origin_shift_y) > max_delta:
        camera.data.shift_y = origin_shift_y + max_delta * (1 if camera.data.shift_y > origin_shift_y else -1)
    bpy.context.view_layer.update()
    return world_to_camera_view(scene, camera, world_point)


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
    for key in ("control_object", "object_name", "mask_object", "foreign_object"):
        name = defect_info.get(key)
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


def configure_backdrop_for_anchor_side(objects, side="front"):
    backdrop = ensure_background_support()
    bb_min, bb_max = world_bbox(objects)
    center = (bb_min + bb_max) * 0.5
    span = bb_max - bb_min
    max_dim = max(float(abs(span.x)), float(abs(span.y)), float(abs(span.z)), 1e-3)
    z_sign = 1.0 if side == "front" else -1.0
    backdrop.location = (center.x, center.y, center.z - z_sign * 0.42 * max_dim)
    backdrop.rotation_euler = (0.0, 0.0, 0.0)
    backdrop.scale = (2.8 * max_dim, 2.8 * max_dim, 1.0)
    backdrop.hide_render = False
    backdrop.hide_viewport = False
    bpy.context.view_layer.update()
    return {
        "side": side,
        "location": [round(float(backdrop.location.x), 5), round(float(backdrop.location.y), 5), round(float(backdrop.location.z), 5)],
        "scale": [round(float(backdrop.scale.x), 5), round(float(backdrop.scale.y), 5), round(float(backdrop.scale.z), 5)],
        "occlusion_policy": "placed_behind_model_relative_to_anchor_side_camera",
    }


def tune_reference_lighting_for_white():
    scene = bpy.context.scene
    energy_scale_map = {
        "Area": 0.12,
        "Area.001": 0.11,
        "Area.002": 0.10,
        "Area.003": 0.52,
        "Area.004": 0.08,
        "Area.005": 0.24,
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
                light.color = (1.0, 0.988, 0.972)
            elif obj.name in cool_lights:
                light.color = (0.965, 0.972, 0.985)
            else:
                light.color = (0.982, 0.982, 0.978)
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
                    color_input.default_value = (0.87, 0.872, 0.876, 1.0)
                if strength_input is not None:
                    strength_input.default_value = min(float(strength_input.default_value), 0.035)
    scene.view_settings.exposure = -0.12
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
    for name in ["REFERENCE_QC71336_BLACK_DOT", "REFERENCE_QC71336_BLACK_DOT_LOCAL_PATCH"]:
        obj = bpy.data.objects.get(name)
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)


def sample_black_dot_anchor(imported_objects, scene, camera, rng):
    target_projected_x = rng.uniform(0.4702, 0.4758)
    target_projected_y = rng.uniform(0.4206, 0.4249)
    target_local_x = rng.uniform(0.172, 0.232)
    target_local_y = rng.uniform(-0.060, -0.010)
    preferred_candidates = []
    fallback_candidates = []
    for obj in imported_objects:
        mesh = obj.data
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
            if poly.material_index != 0:
                continue
            world_center = obj.matrix_world @ poly.center
            world_normal = (obj.matrix_world.to_3x3() @ poly.normal).normalized()
            projected = world_to_camera_view(scene, camera, world_center)
            planar_score = abs(float(world_normal.z))
            x_ratio = abs(float(world_center.x - center.x)) / half_x
            y_ratio = abs(float(world_center.y - center.y)) / half_y
            local_x = float(world_center.x - center.x) / half_x
            local_y = float(world_center.y - center.y) / half_y
            if planar_score < 0.48 or x_ratio > 0.52 or y_ratio > 0.34:
                continue
            if not project_point_visibility_check(scene, camera, world_center, margin=0.18):
                continue
            if not (0.455 <= projected.x <= 0.490 and 0.416 <= projected.y <= 0.432):
                continue
            score = (
                planar_score * 1.7
                + (1.0 - abs(local_x - target_local_x) / 0.080) * 1.15
                + (1.0 - abs(local_y - target_local_y) / 0.070) * 0.90
                + (1.0 - abs(projected.x - target_projected_x) / 0.010) * 1.35
                + (1.0 - abs(projected.y - target_projected_y) / 0.010) * 1.00
            )
            candidate = {
                "score": score,
                "object": obj,
                "polygon_index": poly.index,
                "world_center": world_center,
                "world_normal": world_normal,
                "planar_score": planar_score,
                "local_x": local_x,
                "local_y": local_y,
                "projected_xy": [float(projected.x), float(projected.y)],
                "x_ratio": x_ratio,
                "y_ratio": y_ratio,
                "target_projected_xy": [target_projected_x, target_projected_y],
                "target_local_xy": [target_local_x, target_local_y],
            }
            if (
                planar_score >= 0.992
                and x_ratio <= 0.24
                and y_ratio <= 0.11
                and 0.165 <= local_x <= 0.240
                and -0.068 <= local_y <= 0.008
                and 0.469 <= projected.x <= 0.477
                and 0.419 <= projected.y <= 0.4265
            ):
                candidate["anchor_band"] = "preferred"
                preferred_candidates.append(candidate)
            else:
                candidate["anchor_band"] = "fallback"
                fallback_candidates.append(candidate)
    candidates = preferred_candidates or fallback_candidates
    if not candidates:
        raise RuntimeError("Could not find a stable black-dot anchor on QC7-1336 main-plane region.")
    candidates.sort(key=lambda item: item["score"], reverse=True)
    shortlist_cap = 18 if preferred_candidates else 12
    shortlisted = candidates[: min(shortlist_cap, len(candidates))]
    weights = [max(item["score"] - shortlisted[-1]["score"] + 0.015, 0.002) for item in shortlisted]
    return rng.choices(shortlisted, weights=weights, k=1)[0]


def add_black_dot(imported_objects, scene, camera, image_offset, seed, radius_scale, depth_scale):
    clear_reference_black_dot_objects()
    rng = random.Random(seed + image_offset)
    anchor = sample_black_dot_anchor(imported_objects, scene, camera, rng)
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
        "radius": radius,
        "depth": depth,
        "world_point": [float(world_point.x), float(world_point.y), float(world_point.z)],
        "anchor_band": anchor["anchor_band"],
        "anchor_score": anchor["score"],
        "anchor_planar_score": anchor["planar_score"],
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


def clear_reference_generated_defect_objects():
    prefixes = (
        "REFERENCE_QC71336_BLACK_DOT",
        "REFERENCE_FOREIGN_MATERIAL_",
        "REFERENCE_SPLAY_",
    )
    for obj in list(bpy.data.objects):
        if any(obj.name.startswith(prefix) for prefix in prefixes):
            bpy.data.objects.remove(obj, do_unlink=True)


def capture_object_material_templates(imported_objects):
    templates = {}
    for obj in imported_objects:
        templates[obj.name] = [mat for mat in obj.data.materials]
    return templates


def restore_object_materials(imported_objects, material_templates):
    copy_cache = {}
    for obj in imported_objects:
        obj.data.materials.clear()
        for template in material_templates.get(obj.name, []):
            if template is None:
                continue
            key = template.name_full
            copied = copy_cache.get(key)
            if copied is None:
                copied = template.copy()
                copied.name = f"{template.name}_REFCOPY"
                copy_cache[key] = copied
            obj.data.materials.append(copied)
    bpy.context.view_layer.update()
    return copy_cache


def iter_materials_from_objects(imported_objects):
    seen = set()
    materials = []
    for obj in imported_objects:
        for mat in obj.data.materials:
            if mat is None or mat.name_full in seen:
                continue
            seen.add(mat.name_full)
            materials.append(mat)
    return materials


def boost_qc71336_main_plane_roughness(imported_objects, delta=0.065, cap=0.94):
    tuned = {}
    for mat in iter_materials_from_objects(imported_objects):
        if not mat.use_nodes or mat.node_tree is None:
            continue
        bsdf = find_principled(mat)
        if bsdf is None:
            continue
        roughness_input = bsdf.inputs.get("Roughness")
        if roughness_input is None:
            continue
        old_value = float(roughness_input.default_value)
        new_value = min(old_value + delta, cap)
        roughness_input.default_value = new_value
        tuned[mat.name] = {"old_roughness": old_value, "new_roughness": new_value}
    bpy.context.view_layer.update()
    return tuned


def build_surface_candidate_info(imported_objects, scene, camera, allowed_sides=None):
    allowed_sides = set(allowed_sides or ["front"])
    candidates = []
    for obj in imported_objects:
        mesh = obj.data
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
            side = "front" if float(world_normal.z) >= 0.34 else ("back" if float(world_normal.z) <= -0.34 else None)
            if side not in allowed_sides:
                continue
            planar_score = abs(float(world_normal.z))
            local_x = float(world_center.x - center.x) / half_x
            local_y = float(world_center.y - center.y) / half_y
            x_ratio = abs(float(world_center.x - center.x)) / half_x
            y_ratio = abs(float(world_center.y - center.y)) / half_y
            if planar_score < 0.34 or x_ratio > 0.54 or y_ratio > 0.34:
                continue
            if not project_point_visibility_check(scene, camera, world_center, margin=0.14):
                continue
            projected = world_to_camera_view(scene, camera, world_center)
            if projected.x < 0.24 or projected.x > 0.76 or projected.y < 0.22 or projected.y > 0.78:
                continue

            placement_zone = "central_safe"
            zone_penalty = 0.0
            if x_ratio > 0.42 or y_ratio > 0.27:
                placement_zone = "edge_risk"
                zone_penalty += 0.50
            elif x_ratio > 0.33 or y_ratio > 0.21:
                placement_zone = "near_edge"
                zone_penalty += 0.22

            if y_ratio < 0.09 and abs(local_x) > 0.30:
                placement_zone = "clip_or_hole_risk"
                zone_penalty += 0.72
            elif local_y < -0.10 and abs(local_x) > 0.26:
                placement_zone = "hook_transition_risk"
                zone_penalty += 0.46

            center_bias = 1.0 - min(abs(projected.x - 0.5) / 0.24, 1.0)
            vertical_bias = 1.0 - min(abs(projected.y - 0.47) / 0.20, 1.0)
            score = (
                planar_score * 1.55
                + (1.0 - x_ratio) * 1.00
                + (1.0 - y_ratio) * 0.95
                + center_bias * 0.64
                + vertical_bias * 0.48
                - zone_penalty
            )
            candidates.append(
                {
                    "object": obj,
                    "polygon_index": poly.index,
                    "world_point": world_center,
                    "world_normal": world_normal,
                    "anchor_side": side,
                    "planar_score": planar_score,
                    "local_xy": [local_x, local_y],
                    "x_ratio": x_ratio,
                    "y_ratio": y_ratio,
                    "projected_xy": [float(projected.x), float(projected.y)],
                    "placement_zone": placement_zone,
                    "score": score,
                }
            )
    if not candidates:
        raise RuntimeError("Could not find visible main-surface candidates for reference defects.")
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return {
        "surface_candidates": candidates,
        "allowed_sides": sorted(allowed_sides),
    }


def choose_surface_candidate(material_info, rng, allow_near_edge=True):
    candidates = material_info.get("surface_candidates", [])
    if not candidates:
        raise RuntimeError("No candidate polygons available for defect placement.")
    central_safe = [item for item in candidates if item.get("placement_zone") == "central_safe"]
    near_edge = [item for item in candidates if item.get("placement_zone") == "near_edge"]
    safe_pool = [
        item
        for item in candidates
        if item.get("placement_zone") not in {"clip_or_hole_risk", "hook_transition_risk", "edge_risk"}
    ]

    if not allow_near_edge and central_safe:
        shortlist = central_safe[: min(180, len(central_safe))]
    elif central_safe and (rng.random() < 0.72 or not near_edge):
        shortlist = central_safe[: min(160, len(central_safe))]
    elif near_edge:
        shortlist = near_edge[: min(96, len(near_edge))]
    elif safe_pool:
        shortlist = safe_pool[: min(160, len(safe_pool))]
    else:
        shortlist = candidates[: min(96, len(candidates))]

    random_pool = central_safe if not allow_near_edge and central_safe else safe_pool
    if random_pool and rng.random() < 0.58:
        sample_count = min(220, len(random_pool))
        shortlist = rng.sample(random_pool, sample_count)
        return rng.choice(shortlist)

    min_score = min(item["score"] for item in shortlist)
    temperature = rng.uniform(0.42, 0.82)
    weights = [max(item["score"] - min_score + 0.045, 0.008) ** temperature for item in shortlist]
    return rng.choices(shortlist, weights=weights, k=1)[0]


def jitter_surface_point(world_point, world_normal, max_dim, rng, min_factor, max_factor):
    tangent = world_normal.orthogonal().normalized()
    bitangent = world_normal.cross(tangent).normalized()
    jitter_radius = max_dim * rng.uniform(min_factor, max_factor)
    jitter_angle = rng.uniform(0.0, math.tau)
    offset = tangent * math.cos(jitter_angle) * jitter_radius + bitangent * math.sin(jitter_angle) * jitter_radius
    return world_point + offset, jitter_radius


def ensure_input_default(node, socket_name, value):
    socket = node.inputs.get(socket_name)
    if socket is not None and not socket.is_linked:
        socket.default_value = value


def make_value_node(tree, value, location, label):
    node = tree.nodes.new("ShaderNodeValue")
    node.location = location
    node.label = label
    node.outputs["Value"].default_value = value
    return node


def make_rgb_node(tree, color, location, label):
    node = tree.nodes.new("ShaderNodeRGB")
    node.location = location
    node.label = label
    node.outputs["Color"].default_value = color
    return node


def get_socket_or_value_node(tree, socket, default_value, location, label):
    if socket.is_linked:
        return socket.links[0].from_socket
    if isinstance(default_value, tuple):
        return make_rgb_node(tree, default_value, location, label).outputs["Color"]
    return make_value_node(tree, default_value, location, label).outputs["Value"]


def create_reference_control_object(world_point, tangent, bitangent, world_normal, name):
    empty = bpy.data.objects.new(name, None)
    empty.empty_display_type = "SPHERE"
    empty.empty_display_size = 0.01
    matrix = world_normal.to_track_quat("Z", "Y").to_matrix().to_4x4()
    matrix.translation = world_point
    empty.matrix_world = matrix
    bpy.context.scene.collection.objects.link(empty)
    return empty


def create_directional_mask_patch(world_point, tangent, bitangent, world_normal, radius_x, radius_y, name):
    verts = []
    faces = []
    segments = 14
    for i in range(segments):
        t = i / (segments - 1)
        x = (t * 2.0 - 1.0) * radius_x
        # A short spindle support better matches the visible splay patch than a plain rectangle.
        profile = max(0.08, 1.0 - abs(t * 2.0 - 1.0) ** 1.55)
        y_extent = radius_y * profile
        verts.append((x, -y_extent, 0.0))
        verts.append((x, y_extent, 0.0))
    for i in range(segments - 1):
        a = i * 2
        b = a + 1
        c = a + 3
        d = a + 2
        faces.append((a, b, c, d))
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    patch = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(patch)
    patch.location = world_point + world_normal * max(radius_y * 0.003, 1e-5)
    patch.rotation_euler = world_normal.to_track_quat("Z", "Y").to_euler()
    patch.rotation_euler.rotate_axis("Z", math.atan2(tangent.y, tangent.x))
    return patch


def make_splay_streak_material(name, rng, strong=False, role="core", appearance_scale=1.0):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    mat.blend_method = "BLEND"
    mat.shadow_method = "HASHED"
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "BLENDED"
    bsdf = find_principled(mat)
    if bsdf is None:
        raise RuntimeError("Principled BSDF node not found for splay streak material.")

    if role == "halo":
        if strong:
            alpha = rng.uniform(0.070, 0.115)
            base = rng.uniform(0.27, 0.35)
            roughness = rng.uniform(0.86, 0.96)
            bump_strength = rng.uniform(0.0008, 0.0022)
        else:
            alpha = rng.uniform(0.035, 0.070)
            base = rng.uniform(0.23, 0.31)
            roughness = rng.uniform(0.88, 0.98)
            bump_strength = rng.uniform(0.0004, 0.0014)
    elif strong:
        alpha = rng.uniform(0.080, 0.135)
        base = rng.uniform(0.30, 0.39)
        roughness = rng.uniform(0.88, 0.96)
        bump_strength = rng.uniform(0.0018, 0.0048)
    else:
        alpha = rng.uniform(0.055, 0.095)
        base = rng.uniform(0.27, 0.35)
        roughness = rng.uniform(0.89, 0.97)
        bump_strength = rng.uniform(0.0010, 0.0028)

    alpha_floor = SPLAY_VISIBLE_HALO_ALPHA_FLOOR if role == "halo" else SPLAY_VISIBLE_ALPHA_FLOOR
    alpha = min(max(alpha * appearance_scale, alpha_floor), 0.30)
    base = min(max(base + (appearance_scale - 1.0) * 0.024, 0.20), 0.42)
    bump_strength = min(max(bump_strength * (0.85 + 0.25 * appearance_scale), 0.0003), 0.006)

    bsdf.inputs["Base Color"].default_value = (base, base + rng.uniform(0.002, 0.010), base + rng.uniform(0.004, 0.014), 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    spec_name = "Specular IOR Level" if "Specular IOR Level" in bsdf.inputs else "Specular"
    ensure_input_default(bsdf, spec_name, rng.uniform(0.010, 0.030) if role == "halo" else rng.uniform(0.015, 0.045))
    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = alpha

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    noise = nodes.new("ShaderNodeTexNoise")
    noise.location = (-520, -120)
    noise.inputs["Scale"].default_value = rng.uniform(18.0, 36.0) if role == "halo" else rng.uniform(35.0, 70.0)
    noise.inputs["Detail"].default_value = rng.uniform(2.0, 4.5) if role == "halo" else rng.uniform(4.0, 8.0)
    noise.inputs["Roughness"].default_value = 0.48 if role == "halo" else 0.56

    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.location = (-300, -120)
    ramp.color_ramp.interpolation = "B_SPLINE"
    ramp.color_ramp.elements[0].position = 0.08 if role == "halo" else 0.18
    ramp.color_ramp.elements[1].position = 0.96 if role == "halo" else 0.88
    ramp.color_ramp.elements[0].color = (base * 0.72, base * 0.72, base * 0.74, alpha)
    ramp.color_ramp.elements[1].color = (min(base * 1.04, 0.62), min(base * 1.06, 0.64), min(base * 1.08, 0.66), alpha)

    bump = nodes.new("ShaderNodeBump")
    bump.location = (-80, -360)
    bump.inputs["Strength"].default_value = bump_strength
    bump.inputs["Distance"].default_value = 0.003 if role == "halo" else 0.006

    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    prefix = "halo_" if role == "halo" else ""
    return mat, {f"{prefix}alpha": round(alpha, 4), f"{prefix}base_value": round(base, 4), f"{prefix}roughness": round(roughness, 4)}


def create_splay_streak_patch(world_point, tangent, bitangent, world_normal, length, width, name, rng, strong=False):
    segments = 20
    verts = []
    faces = []
    face_materials = []

    def add_strip(length_scale, width_scale, material_index, z_offset, gap_probability, jitter_scale, taper_power):
        start_index = len(verts)
        curve = rng.uniform(-0.22, 0.22) * width * width_scale
        for i in range(segments):
            t = i / (segments - 1)
            x = (t * 2.0 - 1.0) * length * length_scale * 0.5
            center_y = math.sin((t - 0.5) * math.pi) * curve + rng.uniform(-jitter_scale, jitter_scale) * width
            taper = max(0.02, 1.0 - abs(t * 2.0 - 1.0) ** taper_power)
            half_width = width * width_scale * taper * rng.uniform(0.45, 0.88)
            verts.append((x, center_y - half_width, z_offset))
            verts.append((x, center_y + half_width, z_offset))
        for i in range(segments - 1):
            t_mid = (i + 0.5) / (segments - 1)
            keep_center = 0.30 <= t_mid <= 0.70
            if keep_center or rng.random() > gap_probability:
                a = start_index + i * 2
                b = a + 1
                c = a + 3
                d = a + 2
                faces.append((a, b, c, d))
                face_materials.append(material_index)

    add_strip(
        length_scale=rng.uniform(0.82, 0.98),
        width_scale=rng.uniform(2.1, 3.0),
        material_index=1,
        z_offset=0.0,
        gap_probability=0.08 if strong else 0.14,
        jitter_scale=0.16,
        taper_power=1.7,
    )
    add_strip(
        length_scale=rng.uniform(0.78, 0.94),
        width_scale=1.0,
        material_index=0,
        z_offset=max(width * 0.006, 1e-6),
        gap_probability=0.18 if strong else 0.28,
        jitter_scale=0.10,
        taper_power=2.4,
    )
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    for poly, material_index in zip(mesh.polygons, face_materials):
        poly.material_index = material_index
    patch = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(patch)
    patch.location = world_point + world_normal * max(width * 0.018, 2e-5)
    patch.rotation_euler = world_normal.to_track_quat("Z", "Y").to_euler()
    patch.rotation_euler.rotate_axis("Z", math.atan2(tangent.y, tangent.x))
    return patch


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


def make_foreign_material_mat(name, rng, high_contrast=False):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    mat.surface_render_method = "BLENDED"
    bsdf = find_principled(mat)
    if bsdf is None:
        raise RuntimeError("Principled BSDF node not found for foreign-material defect.")

    defect_subtype = rng.choices(
        ["white_particle", "gray_particle", "semi_transparent", "metallic"],
        weights=[72, 28, 0, 0] if high_contrast else [24, 60, 12, 4],
        k=1,
    )[0]
    ensure_input_default(bsdf, "Metallic", 0.0)
    if defect_subtype == "white_particle":
        base_color = (
            rng.uniform(0.66, 0.78),
            rng.uniform(0.65, 0.77),
            rng.uniform(0.60, 0.72),
            1.0,
        )
        roughness = rng.uniform(0.66, 0.84)
    elif defect_subtype == "gray_particle":
        value = rng.uniform(0.68, 0.82) if high_contrast else rng.uniform(0.52, 0.68)
        base_color = (value, value, value, 1.0)
        roughness = rng.uniform(0.58, 0.82)
    elif defect_subtype == "semi_transparent":
        base_color = (0.64, 0.67, 0.68, 1.0)
        roughness = rng.uniform(0.40, 0.58)
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = rng.uniform(0.64, 0.84)
        mat.blend_method = "BLEND"
        mat.shadow_method = "HASHED"
    else:
        base_color = (0.46, 0.46, 0.45, 1.0)
        ensure_input_default(bsdf, "Metallic", rng.uniform(0.18, 0.38))
        roughness = rng.uniform(0.50, 0.68)
    bsdf.inputs["Base Color"].default_value = base_color
    bsdf.inputs["Roughness"].default_value = roughness
    spec_name = "Specular IOR Level" if "Specular IOR Level" in bsdf.inputs else "Specular"
    ensure_input_default(bsdf, spec_name, rng.uniform(0.015, 0.055))

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
    low = max(0.0, base_color[0] - rng.uniform(0.06, 0.10))
    high = min(1.0, base_color[0] + rng.uniform(0.04, 0.09))
    if high_contrast:
        low = max(low, 0.62)
        high = max(high, 0.80)
    color_ramp.color_ramp.elements[0].color = (low, low, low, 1.0)
    color_ramp.color_ramp.elements[1].color = (high, high, high, 1.0)

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
    return mat, defect_subtype


def add_foreign_material(imported_objects, material_info, max_dim, image_offset, seed):
    rng = random.Random(seed + image_offset)
    candidate = choose_surface_candidate(material_info, rng, allow_near_edge=False)
    primary_obj = candidate["object"]
    world_point = candidate["world_point"]
    world_normal = candidate["world_normal"]
    world_point, placement_jitter_radius = jitter_surface_point(world_point, world_normal, max_dim, rng, 0.0005, 0.0045)
    debug_large = bool(material_info.get("foreign_material_debug", False))
    size_tier = rng.choices(
        ["tiny", "normal", "large_debug"],
        weights=[35, 65, 1 if debug_large else 0],
        k=1,
    )[0]
    if size_tier == "tiny":
        radius = rng.uniform(max_dim * 0.00055, max_dim * 0.00095)
    elif size_tier == "normal":
        radius = rng.uniform(max_dim * 0.00085, max_dim * 0.00135)
    else:
        radius = rng.uniform(max_dim * 0.00105, max_dim * 0.00155)
    visible_radius_floor = (
        FOREIGN_MATERIAL_BACK_VISIBLE_RADIUS_FLOOR
        if candidate.get("anchor_side", "front") == "back"
        else FOREIGN_MATERIAL_VISIBLE_RADIUS_FLOOR
    )
    radius = max(radius, visible_radius_floor)
    if candidate.get("anchor_side", "front") == "back":
        shape = "ico"
    else:
        shape = rng.choices(
            ["irregular_flat_chip", "ico", "flattened_chip", "sphere"],
            weights=[60, 16, 24, 0],
            k=1,
        )[0]

    if shape == "irregular_flat_chip":
        mesh = create_irregular_flat_foreign_mesh(f"REFERENCE_FOREIGN_MATERIAL_{image_offset:04d}", radius, rng)
        obj = bpy.data.objects.new(f"REFERENCE_FOREIGN_MATERIAL_{image_offset:04d}", mesh)
        bpy.context.collection.objects.link(obj)
        obj.location = world_point + world_normal * radius * 0.08
    elif shape == "sphere":
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=8,
            ring_count=4,
            radius=radius,
            location=world_point + world_normal * radius * 0.22,
        )
        obj = bpy.context.object
    elif shape == "ico":
        bpy.ops.mesh.primitive_ico_sphere_add(
            subdivisions=1,
            radius=radius,
            location=world_point + world_normal * radius * 0.22,
        )
        obj = bpy.context.object
    else:
        bpy.ops.mesh.primitive_cube_add(
            size=radius * 2.0,
            location=world_point + world_normal * radius * 0.15,
        )
        obj = bpy.context.object
        obj.scale = (
            rng.uniform(0.8, 1.8),
            rng.uniform(0.4, 1.2),
            rng.uniform(0.12, 0.35),
        )

    if candidate.get("anchor_side", "front") == "back":
        obj.scale = (
            obj.scale.x * rng.uniform(0.90, 1.32),
            obj.scale.y * rng.uniform(0.72, 1.08),
            obj.scale.z * rng.uniform(0.10, 0.24),
        )
    else:
        obj.scale = (
            obj.scale.x * rng.uniform(0.70, 1.35),
            obj.scale.y * rng.uniform(0.35, 0.92),
            obj.scale.z * rng.uniform(0.08, 0.22),
        )
    obj.scale.x *= rng.uniform(0.92, 1.05)
    obj.scale.y *= rng.uniform(0.92, 1.05)

    obj.name = f"REFERENCE_FOREIGN_MATERIAL_{image_offset:04d}"
    obj.rotation_euler = world_normal.to_track_quat("Z", "Y").to_euler()
    obj.rotation_euler.rotate_axis("Z", rng.uniform(0.0, math.tau))
    if candidate.get("anchor_side", "front") == "back":
        embed_factor = rng.uniform(0.34, 0.52)
    else:
        embed_factor = rng.uniform(0.09, 0.18)
    obj.location = world_point + world_normal * radius * embed_factor
    obj.pass_index = 1
    for poly in obj.data.polygons:
        poly.use_smooth = True

    mat, subtype = make_foreign_material_mat(
        f"{obj.name}_MAT",
        rng,
        high_contrast=candidate.get("anchor_side", "front") == "back",
    )
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    if hasattr(obj, "visible_shadow"):
        obj.visible_shadow = True
    bpy.context.view_layer.update()
    return {
        "defect_type": "foreign_material",
        "defect_type_internal": "foreign_material",
        "defect_type_canonical": "foreign_material",
        "subtype": subtype,
        "shape": shape,
        "size_tier": size_tier,
        "target_object": primary_obj.name,
        "object_name": obj.name,
        "mask_object": obj.name,
        "anchor_polygon_index": candidate["polygon_index"],
        "anchor_side": candidate.get("anchor_side", "front"),
        "world_point": [round(world_point.x, 5), round(world_point.y, 5), round(world_point.z, 5)],
        "world_normal": [round(world_normal.x, 5), round(world_normal.y, 5), round(world_normal.z, 5)],
        "radius": round(radius, 6),
        "radius_floor": visible_radius_floor,
        "embed_factor": round(embed_factor, 6),
        "placement_jitter_radius": round(placement_jitter_radius, 6),
        "placement_zone": candidate["placement_zone"],
        "local_xy": [round(candidate["local_xy"][0], 5), round(candidate["local_xy"][1], 5)],
        "projected_xy": candidate["projected_xy"],
        "anchor_planar_score": candidate["planar_score"],
        "anchor_xy_ratio": [candidate["x_ratio"], candidate["y_ratio"]],
        "version": FOREIGN_MATERIAL_VERSION,
    }


def splay_reference_params(rng, strong=False):
    params = {
        "flow_angle": rng.uniform(-0.35, 0.35),
        "wave_scale": rng.uniform(22.0, 42.0),
        "wave_distortion": rng.uniform(1.8, 4.8),
        "noise_scale": rng.uniform(34.0, 64.0),
        "mask_low": rng.uniform(0.66, 0.76),
        "mask_high": rng.uniform(0.80, 0.88),
        "break_low": rng.uniform(0.58, 0.68),
        "break_high": rng.uniform(0.72, 0.86),
        "local_low": rng.uniform(0.18, 0.26),
        "local_high": rng.uniform(0.46, 0.60),
        "roughness_delta": rng.uniform(0.08, 0.17),
        "specular_delta": rng.uniform(-0.028, 0.008),
        "bump_strength": rng.uniform(0.0012, 0.0038),
        "bright_tint": rng.uniform(0.012, 0.026),
        "micro_scale": rng.uniform(55.0, 90.0),
        "micro_strength": rng.uniform(0.12, 0.22),
    }
    if strong:
        params["mask_low"] = max(0.42, params["mask_low"] - 0.18)
        params["mask_high"] = max(params["mask_low"] + 0.08, params["mask_high"] - 0.16)
        params["break_low"] = max(0.38, params["break_low"] - 0.12)
        params["break_high"] = max(params["break_low"] + 0.10, params["break_high"] - 0.10)
        params["local_low"] = max(0.05, params["local_low"] - 0.10)
        params["local_high"] = max(params["local_low"] + 0.24, params["local_high"] - 0.06)
        params["roughness_delta"] *= 4.2
        params["bump_strength"] *= 3.6
        params["bright_tint"] = max(params["bright_tint"] * 6.0, 0.075)
        params["specular_delta"] = min(params["specular_delta"] - 0.08, -0.06)
        params["micro_strength"] = min(params["micro_strength"] * 2.6, 0.60)
    return params


def apply_splay_to_material(main_material, control_object, params, rng):
    if not main_material.use_nodes or main_material.node_tree is None:
        return None
    tree = main_material.node_tree
    nodes = tree.nodes
    links = tree.links
    bsdf = find_principled(main_material)
    if bsdf is None:
        return None

    tex_coord = nodes.new("ShaderNodeTexCoord")
    tex_coord.object = control_object
    tex_coord.location = (-1200, -260)

    mapping = nodes.new("ShaderNodeMapping")
    mapping.location = (-980, -260)
    mapping.inputs["Rotation"].default_value = (0.0, 0.0, params["flow_angle"])
    mapping.inputs["Scale"].default_value = (1.0, 6.2, 1.0)

    wave = nodes.new("ShaderNodeTexWave")
    wave.location = (-760, -180)
    wave.wave_type = "BANDS"
    wave.bands_direction = "X"
    wave.inputs["Scale"].default_value = params["wave_scale"]
    wave.inputs["Distortion"].default_value = params["wave_distortion"]
    ensure_input_default(wave, "Detail Scale", 0.0)

    noise = nodes.new("ShaderNodeTexNoise")
    noise.location = (-760, -410)
    noise.inputs["Scale"].default_value = params["noise_scale"]
    noise.inputs["Detail"].default_value = 10.0
    noise.inputs["Roughness"].default_value = 0.48

    break_noise = nodes.new("ShaderNodeTexNoise")
    break_noise.location = (-760, -620)
    break_noise.inputs["Scale"].default_value = params["noise_scale"] * 0.75
    break_noise.inputs["Detail"].default_value = 5.0
    break_noise.inputs["Roughness"].default_value = 0.42

    micro_wave = nodes.new("ShaderNodeTexWave")
    micro_wave.location = (-760, -820)
    micro_wave.wave_type = "BANDS"
    micro_wave.bands_direction = "X"
    micro_wave.inputs["Scale"].default_value = params["micro_scale"]
    micro_wave.inputs["Distortion"].default_value = rng.uniform(0.6, 1.6)
    ensure_input_default(micro_wave, "Detail Scale", 0.0)

    gradient = nodes.new("ShaderNodeTexGradient")
    gradient.location = (-760, 40)
    gradient.gradient_type = "QUADRATIC_SPHERE"

    local_ramp = nodes.new("ShaderNodeValToRGB")
    local_ramp.location = (-510, 20)
    local_ramp.color_ramp.interpolation = "EASE"
    local_ramp.color_ramp.elements[0].position = params["local_low"]
    local_ramp.color_ramp.elements[1].position = params["local_high"]
    local_ramp.color_ramp.elements[0].color = (1.0, 1.0, 1.0, 1.0)
    local_ramp.color_ramp.elements[1].color = (0.0, 0.0, 0.0, 1.0)

    local_to_value = nodes.new("ShaderNodeRGBToBW")
    local_to_value.location = (-250, 20)

    mask_mult = nodes.new("ShaderNodeMath")
    mask_mult.operation = "MULTIPLY"
    mask_mult.location = (-480, -280)

    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.location = (-240, -280)
    ramp.color_ramp.interpolation = "EASE"
    ramp.color_ramp.elements[0].position = params["mask_low"]
    ramp.color_ramp.elements[1].position = params["mask_high"]
    ramp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)

    break_ramp = nodes.new("ShaderNodeValToRGB")
    break_ramp.location = (-510, -560)
    break_ramp.color_ramp.interpolation = "B_SPLINE"
    break_ramp.color_ramp.elements[0].position = params["break_low"]
    break_ramp.color_ramp.elements[1].position = params["break_high"]
    break_ramp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    break_ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)

    break_to_value = nodes.new("ShaderNodeRGBToBW")
    break_to_value.location = (-250, -560)

    mask_break_mult = nodes.new("ShaderNodeMath")
    mask_break_mult.operation = "MULTIPLY"
    mask_break_mult.location = (-240, -360)

    micro_mix = nodes.new("ShaderNodeMixRGB")
    micro_mix.blend_type = "MULTIPLY"
    micro_mix.location = (-240, -720)
    micro_mix.inputs["Fac"].default_value = params["micro_strength"]

    micro_to_value = nodes.new("ShaderNodeRGBToBW")
    micro_to_value.location = (-20, -720)

    local_mix_mult = nodes.new("ShaderNodeMath")
    local_mix_mult.operation = "MULTIPLY"
    local_mix_mult.location = (-20, -360)

    mask_to_value = nodes.new("NodeReroute")
    mask_to_value.location = (10, -300)

    base_roughness_source = get_socket_or_value_node(
        tree,
        bsdf.inputs["Roughness"],
        float(bsdf.inputs["Roughness"].default_value),
        (-240, -70),
        "REFERENCE_SPLAY_BASE_ROUGHNESS",
    )
    rough_boost = nodes.new("ShaderNodeMath")
    rough_boost.operation = "MULTIPLY"
    rough_boost.inputs[1].default_value = params["roughness_delta"]
    rough_boost.location = (180, -250)

    rough_add = nodes.new("ShaderNodeMath")
    rough_add.operation = "ADD"
    rough_add.use_clamp = True
    rough_add.location = (390, -170)

    bump = nodes.new("ShaderNodeBump")
    bump.location = (420, -420)
    bump.inputs["Strength"].default_value = params["bump_strength"]
    bump.inputs["Distance"].default_value = 0.010

    base_color_socket = get_socket_or_value_node(
        tree,
        bsdf.inputs["Base Color"],
        tuple(bsdf.inputs["Base Color"].default_value),
        (-210, 120),
        "REFERENCE_SPLAY_BASE_COLOR",
    )
    color_mix = nodes.new("ShaderNodeMixRGB")
    color_mix.blend_type = "SCREEN"
    color_mix.location = (410, 80)
    color_mix.inputs[2].default_value = (0.69, 0.71, 0.72, 1.0)

    color_fac = nodes.new("ShaderNodeMath")
    color_fac.operation = "MULTIPLY"
    color_fac.inputs[1].default_value = params["bright_tint"]
    color_fac.location = (220, 80)

    spec_name = "Specular IOR Level" if "Specular IOR Level" in bsdf.inputs else "Specular"
    base_spec_socket = get_socket_or_value_node(
        tree,
        bsdf.inputs[spec_name],
        float(bsdf.inputs[spec_name].default_value),
        (-170, 320),
        "REFERENCE_SPLAY_BASE_SPECULAR",
    )
    spec_delta = nodes.new("ShaderNodeMath")
    spec_delta.operation = "MULTIPLY"
    spec_delta.inputs[1].default_value = params["specular_delta"]
    spec_delta.location = (180, 260)

    spec_add = nodes.new("ShaderNodeMath")
    spec_add.operation = "ADD"
    spec_add.use_clamp = True
    spec_add.location = (390, 260)

    original_normal_socket = bsdf.inputs["Normal"].links[0].from_socket if bsdf.inputs["Normal"].is_linked else None

    links.new(tex_coord.outputs["Object"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], wave.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    links.new(mapping.outputs["Vector"], break_noise.inputs["Vector"])
    links.new(mapping.outputs["Vector"], micro_wave.inputs["Vector"])
    links.new(mapping.outputs["Vector"], gradient.inputs["Vector"])
    links.new(gradient.outputs["Fac"], local_ramp.inputs["Fac"])
    links.new(local_ramp.outputs["Color"], local_to_value.inputs["Color"])
    links.new(wave.outputs["Color"], mask_mult.inputs[0])
    links.new(noise.outputs["Fac"], mask_mult.inputs[1])
    links.new(mask_mult.outputs["Value"], ramp.inputs["Fac"])
    links.new(break_noise.outputs["Fac"], break_ramp.inputs["Fac"])
    links.new(break_ramp.outputs["Color"], break_to_value.inputs["Color"])
    links.new(ramp.outputs["Alpha"], mask_break_mult.inputs[0])
    links.new(break_to_value.outputs["Val"], mask_break_mult.inputs[1])
    links.new(mask_break_mult.outputs["Value"], micro_mix.inputs["Color1"])
    links.new(micro_wave.outputs["Color"], micro_mix.inputs["Color2"])
    links.new(micro_mix.outputs["Color"], micro_to_value.inputs["Color"])
    links.new(micro_to_value.outputs["Val"], local_mix_mult.inputs[0])
    links.new(local_to_value.outputs["Val"], local_mix_mult.inputs[1])
    links.new(local_mix_mult.outputs["Value"], mask_to_value.inputs[0])
    links.new(mask_to_value.outputs[0], rough_boost.inputs[0])
    links.new(base_roughness_source, rough_add.inputs[0])
    links.new(rough_boost.outputs["Value"], rough_add.inputs[1])
    links.new(rough_add.outputs["Value"], bsdf.inputs["Roughness"])
    links.new(mask_to_value.outputs[0], bump.inputs["Height"])
    if original_normal_socket is not None:
        links.new(original_normal_socket, bump.inputs["Normal"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(mask_to_value.outputs[0], color_fac.inputs[0])
    links.new(color_fac.outputs["Value"], color_mix.inputs["Fac"])
    links.new(base_color_socket, color_mix.inputs[1])
    links.new(color_mix.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(base_spec_socket, spec_add.inputs[0])
    links.new(mask_to_value.outputs[0], spec_delta.inputs[0])
    links.new(spec_delta.outputs["Value"], spec_add.inputs[1])
    links.new(spec_add.outputs["Value"], bsdf.inputs[spec_name])
    return {
        "mask_mode": "localized_directional_splay",
        "flow_angle": round(params["flow_angle"], 4),
        "wave_scale": round(params["wave_scale"], 4),
        "roughness_delta": round(params["roughness_delta"], 4),
        "specular_delta": round(params["specular_delta"], 4),
        "bright_tint": round(params["bright_tint"], 4),
    }


def add_splay(imported_objects, material_info, max_dim, image_offset, seed, strong=False):
    rng = random.Random(seed + image_offset)
    candidate = choose_surface_candidate(material_info, rng)
    primary_obj = candidate["object"]
    world_point = candidate["world_point"]
    world_normal = candidate["world_normal"]
    world_point, placement_jitter_radius = jitter_surface_point(world_point, world_normal, max_dim, rng, 0.0020, 0.0100)
    slope_sign = 1.0 if rng.random() < 0.82 else -1.0
    preferred_tangent = Vector((1.0, slope_sign * rng.uniform(0.30, 0.82), 0.0))
    tangent = (preferred_tangent - world_normal * preferred_tangent.dot(world_normal)).normalized()
    if tangent.length < 1e-5:
        tangent = world_normal.orthogonal().normalized()
    bitangent = world_normal.cross(tangent).normalized()

    main_material = next((mat for mat in primary_obj.data.materials if mat is not None), None)
    use_material_driven_splay = False
    if main_material is not None and use_material_driven_splay:
        radius_x = max(rng.uniform(max_dim * 0.19, max_dim * 0.28), SPLAY_DIRECTIONAL_RADIUS_X_FLOOR)
        radius_y = max(
            rng.uniform(max_dim * 0.010, max_dim * 0.032),
            SPLAY_DIRECTIONAL_RADIUS_Y_FLOOR,
        )
        aspect_ratio = max(radius_x / max(radius_y, 1e-6), 1.0)
        control = create_reference_control_object(
            world_point,
            tangent,
            bitangent,
            world_normal,
            name=f"REFERENCE_SPLAY_CTRL_{image_offset:04d}",
        )
        mask_patch = create_directional_mask_patch(
            world_point,
            tangent,
            bitangent,
            world_normal,
            radius_x,
            radius_y,
            name=f"REFERENCE_SPLAY_MASK_{image_offset:04d}",
        )
        mask_patch.pass_index = 1
        mask_patch.hide_render = True
        params = splay_reference_params(rng, strong=strong)
        params["bright_tint"] = max(params["bright_tint"], SPLAY_DIRECTIONAL_BRIGHT_TINT_FLOOR)
        mat_info = apply_splay_to_material(main_material, control, params, rng)
        if mat_info is not None:
            bpy.context.view_layer.update()
            return {
                "defect_type": "splay",
                "defect_type_internal": "splay",
                "defect_type_canonical": "splay",
                "control_object": control.name,
                "mask_object": mask_patch.name,
                "appearance_mode": "silver_flow_streak",
                "shape_mode": "directional_thin_streak",
                "anchor_polygon_index": candidate["polygon_index"],
                "world_point": [round(world_point.x, 5), round(world_point.y, 5), round(world_point.z, 5)],
                "world_normal": [round(world_normal.x, 5), round(world_normal.y, 5), round(world_normal.z, 5)],
                "radius_x": round(radius_x, 6),
                "radius_y": round(radius_y, 6),
                "radius_x_floor": SPLAY_DIRECTIONAL_RADIUS_X_FLOOR,
                "radius_y_floor": SPLAY_DIRECTIONAL_RADIUS_Y_FLOOR,
                "aspect_ratio": round(aspect_ratio, 4),
                "placement_jitter_radius": round(placement_jitter_radius, 6),
                "placement_zone": candidate["placement_zone"],
                "local_xy": [round(candidate["local_xy"][0], 5), round(candidate["local_xy"][1], 5)],
                "debug_splay_strong": bool(strong),
                "projected_xy": candidate["projected_xy"],
                "anchor_planar_score": candidate["planar_score"],
                "anchor_xy_ratio": [candidate["x_ratio"], candidate["y_ratio"]],
                "version": SPLAY_VERSION,
                "materials_touched": [main_material.name],
                "material": main_material.name,
                **mat_info,
            }

    appearance_tier = rng.choices(["faint", "normal", "visible"], weights=[18, 52, 30], k=1)[0]
    appearance_scale = {"faint": 0.78, "normal": 1.0, "visible": 1.24}[appearance_tier]
    if strong:
        appearance_tier = "debug_strong"
        appearance_scale = max(appearance_scale, 1.38)
    size_tier = rng.choices(["short", "normal", "long"], weights=[25, 52, 23], k=1)[0]
    if size_tier == "short":
        length = rng.uniform(max_dim * 0.030, max_dim * 0.044)
        width = rng.uniform(max_dim * 0.0013, max_dim * 0.0023)
    elif size_tier == "normal":
        length = rng.uniform(max_dim * 0.038, max_dim * 0.056)
        width = rng.uniform(max_dim * 0.0017, max_dim * 0.0028)
    else:
        length = rng.uniform(max_dim * 0.050, max_dim * 0.070)
        width = rng.uniform(max_dim * 0.0020, max_dim * 0.0032)
    if strong:
        width *= 1.08
    length = max(length, SPLAY_VISIBLE_LENGTH_FLOOR)
    width = max(width, SPLAY_VISIBLE_WIDTH_FLOOR)
    if length / max(width * 2.0, 1e-6) < 5.2:
        width = length / (2.0 * rng.uniform(5.2, 7.6))
    aspect_ratio = max(length / max(width * 2.0, 1e-6), 1.0)

    control = create_reference_control_object(
        world_point,
        tangent,
        bitangent,
        world_normal,
        name=f"REFERENCE_SPLAY_CTRL_{image_offset:04d}",
    )
    streak_patch = create_splay_streak_patch(
        world_point,
        tangent,
        bitangent,
        world_normal,
        length,
        width,
        name=f"REFERENCE_SPLAY_STREAK_{image_offset:04d}",
        rng=rng,
        strong=strong,
    )
    streak_mat, mat_info = make_splay_streak_material(
        f"{streak_patch.name}_MAT", rng, strong=strong, role="core", appearance_scale=appearance_scale
    )
    halo_mat, halo_info = make_splay_streak_material(
        f"{streak_patch.name}_HALO_MAT", rng, strong=strong, role="halo", appearance_scale=appearance_scale
    )
    streak_patch.data.materials.append(streak_mat)
    streak_patch.data.materials.append(halo_mat)
    streak_patch.pass_index = 1

    bpy.context.view_layer.update()
    return {
        "defect_type": "splay",
        "defect_type_internal": "splay",
        "defect_type_canonical": "splay",
        "control_object": control.name,
        "object_name": streak_patch.name,
        "mask_object": streak_patch.name,
        "appearance_mode": "short_silver_gray_streak_patch",
        "appearance_tier": appearance_tier,
        "shape_mode": "localized_oblique_streak",
        "anchor_polygon_index": candidate["polygon_index"],
        "anchor_side": candidate.get("anchor_side", "front"),
        "world_point": [round(world_point.x, 5), round(world_point.y, 5), round(world_point.z, 5)],
        "world_normal": [round(world_normal.x, 5), round(world_normal.y, 5), round(world_normal.z, 5)],
        "length": round(length, 6),
        "width": round(width, 6),
        "length_floor": SPLAY_VISIBLE_LENGTH_FLOOR,
        "width_floor": SPLAY_VISIBLE_WIDTH_FLOOR,
        "size_tier": size_tier,
        "radius_x": round(length * 0.5, 6),
        "radius_y": round(width, 6),
        "aspect_ratio": round(aspect_ratio, 4),
        "placement_jitter_radius": round(placement_jitter_radius, 6),
        "placement_zone": candidate["placement_zone"],
        "local_xy": [round(candidate["local_xy"][0], 5), round(candidate["local_xy"][1], 5)],
        "debug_splay_strong": bool(strong),
        "projected_xy": candidate["projected_xy"],
        "anchor_planar_score": candidate["planar_score"],
        "anchor_xy_ratio": [candidate["x_ratio"], candidate["y_ratio"]],
        "version": SPLAY_VERSION,
        "materials_touched": [],
        "mask_mode": "visible_streak_patch",
        "flow_angle": round(math.atan2(tangent.y, tangent.x), 4),
        **mat_info,
        **halo_info,
    }


def add_foreign_material_splay_cooccurrence(imported_objects, material_info, max_dim, image_offset, seed, strong=False):
    foreign = add_foreign_material(imported_objects, material_info, max_dim, image_offset, seed)
    splay = add_splay(imported_objects, material_info, max_dim, image_offset, seed + 100000, strong=strong)
    world_points = [
        Vector(item["world_point"])
        for item in (foreign, splay)
        if item and item.get("world_point")
    ]
    if world_points:
        center = sum(world_points, Vector((0.0, 0.0, 0.0))) / len(world_points)
    else:
        center = Vector(foreign.get("world_point", (0.0, 0.0, 0.0)))
    anchor_side = foreign.get("anchor_side") or splay.get("anchor_side") or "front"
    return {
        "defect_type": "foreign_material_splay",
        "defect_type_internal": "foreign_material_splay",
        "defect_type_canonical": "foreign_material_splay",
        "defect_types": ["foreign_material", "splay"],
        "defects": [foreign, splay],
        "mask_objects": [foreign["mask_object"], splay["mask_object"]],
        "anchor_side": anchor_side,
        "world_point": [round(center.x, 5), round(center.y, 5), round(center.z, 5)],
        "world_normal": foreign.get("world_normal"),
        "version": {
            "foreign_material": FOREIGN_MATERIAL_VERSION,
            "splay": SPLAY_VERSION,
        },
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
        roughness=0.622,
        specular=0.104,
        coat_weight=0.015,
        coat_roughness=0.345,
        bump_strength=0.00110,
        variation_scale=930.0,
    )
    edge_wall_mat = build_qc71336_white_material(
        name="REFERENCE_QC71336_WHITE_EDGE_WALL",
        base_color=(0.713, 0.718, 0.708, 1.0),
        roughness=0.562,
        specular=0.129,
        coat_weight=0.020,
        coat_roughness=0.295,
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


def render_object_binary_mask(mask_path, object_names):
    scene = bpy.context.scene
    targets = []
    for object_name in object_names:
        obj = bpy.data.objects.get(object_name)
        if obj is None:
            raise RuntimeError(f"Mask target object not found: {object_name}")
        targets.append(obj)

    original_engine = scene.render.engine
    original_samples = int(getattr(scene.cycles, "samples", 1))
    original_adaptive = bool(getattr(scene.cycles, "use_adaptive_sampling", False))
    original_filepath = scene.render.filepath
    original_hide_render = {obj.name: bool(obj.hide_render) for obj in bpy.data.objects}
    original_materials = {obj.name: [mat for mat in obj.data.materials] for obj in targets}
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
                obj.hide_render = obj.name not in {target.name for target in targets}
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
            for mat in original_materials.get(obj.name, []):
                obj.data.materials.append(mat)
        for obj in bpy.data.objects:
            if obj.name in original_hide_render:
                obj.hide_render = original_hide_render[obj.name]
        bpy.context.view_layer.update()


def render_black_dot_binary_mask(mask_path, dot_object_name):
    render_object_binary_mask(mask_path, [dot_object_name])


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
    requested_sides = args.anchor_sides or ["front"]
    initial_side = requested_sides[0]
    ensure_camera_for_objects(primary_objects, args.width, args.height, initial_side)
    gpu_info = configure_cycles_gpu(args.samples)

    for obj in primary_objects:
        obj.hide_render = True
        obj.hide_viewport = True

    imported = append_blend_objects(Path(args.model_blend).resolve())
    fit_objects_to_reference(imported, primary_objects)
    main_plane_roughness_tuning = boost_qc71336_main_plane_roughness(imported)
    material_templates = capture_object_material_templates(imported)
    assigned_materials = summarize_existing_materials(imported)
    camera = ensure_camera_for_objects(imported, args.width, args.height, initial_side)
    surface_info = build_surface_candidate_info(imported, bpy.context.scene, camera, requested_sides)
    bb_min, bb_max = world_bbox(imported)
    dims = bb_max - bb_min
    max_dim = max(float(abs(dims.x)), float(abs(dims.y)), float(abs(dims.z)), 1e-6)

    samples = []
    pack_error = None
    for image_offset in range(args.num):
        image_index = args.start_index + image_offset
        clear_reference_generated_defect_objects()
        restore_object_materials(imported, material_templates)
        defect_info = None
        if args.defect_type == "foreign_material":
            defect_info = add_foreign_material(imported, surface_info, max_dim, image_offset, args.defect_seed)
        elif args.defect_type == "splay":
            defect_info = add_splay(
                imported,
                surface_info,
                max_dim,
                image_offset,
                args.defect_seed,
                strong=args.debug_splay_strong,
            )
        elif args.defect_type == "foreign_material_splay":
            defect_info = add_foreign_material_splay_cooccurrence(
                imported,
                surface_info,
                max_dim,
                image_offset,
                args.defect_seed,
                strong=args.debug_splay_strong,
            )
        else:
            raise RuntimeError(f"Unsupported defect type: {args.defect_type}")
        defect_side = defect_info.get("anchor_side", initial_side) if defect_info else initial_side
        view_transform = build_object_view_transform(args, defect_info)
        camera_side = view_transform["camera_side"] if view_transform["enabled"] else defect_side
        position_camera_for_anchor_side(camera, imported, camera_side)
        backdrop_info = configure_backdrop_for_anchor_side(imported, camera_side)
        if view_transform["enabled"]:
            apply_object_view_transform(imported, defect_info, view_transform)
        if defect_info and defect_info.get("world_point"):
            defect_center = Vector(defect_info["world_point"])
            if view_transform["enabled"]:
                projected = world_to_camera_view(bpy.context.scene, camera, defect_center)
            else:
                projected = refine_camera_shift_for_defect(camera, bpy.context.scene, defect_center)
            defect_info["camera_follow"] = {
                "anchor_side": defect_side,
                "camera_side": camera_side,
                "projected_xy_after_follow": [round(float(projected.x), 5), round(float(projected.y), 5)],
                "visible_after_follow": bool(
                    projected.z > 0.0 and 0.08 <= projected.x <= 0.92 and 0.08 <= projected.y <= 0.92
                ),
            }
            defect_info["backdrop"] = backdrop_info
            defect_info["view_transform"] = view_transform
        render_path = rgb_dir / f"{image_index:06d}.png"
        render_still(render_path)
        label_info = None
        label_rel = None
        mask_objects = []
        if defect_info:
            mask_objects = defect_info.get("mask_objects") or []
            if not mask_objects and defect_info.get("mask_object"):
                mask_objects = [defect_info["mask_object"]]
        if mask_objects:
            mask_path = mask_dir / f"{image_index:06d}.png"
            overlay_path = overlay_dir / f"{image_index:06d}.png"
            label_path = yolo_dir / f"{image_index:06d}.txt"
            render_object_binary_mask(mask_path, mask_objects)
            binary, mask_width, mask_height = load_binary_mask_from_image(mask_path, threshold=0.5)
            bbox = bbox_from_binary_mask(binary, mask_width, mask_height)
            save_mask_overlay(
                render_path,
                overlay_path,
                binary,
                mask_width,
                mask_height,
                bbox,
                "REFERENCE_BLACK_DOT_OVERLAY_EXPORT",
            )
            label_text = ""
            defect_bboxes = []
            if args.defect_type == "foreign_material_splay":
                class_ids = {"foreign_material": 1, "splay": 2}
                for defect_item in defect_info.get("defects", []):
                    defect_mask_object = defect_item.get("mask_object")
                    defect_name = defect_item.get("defect_type_canonical", defect_item.get("defect_type"))
                    if not defect_mask_object or defect_name not in class_ids:
                        continue
                    tmp_mask_path = mask_dir / f"{image_index:06d}_{defect_name}_tmp.png"
                    render_object_binary_mask(tmp_mask_path, [defect_mask_object])
                    tmp_binary, tmp_width, tmp_height = load_binary_mask_from_image(tmp_mask_path, threshold=0.5)
                    tmp_bbox = bbox_from_binary_mask(tmp_binary, tmp_width, tmp_height)
                    if tmp_bbox is not None and tmp_bbox["xywh"][2] > 0 and tmp_bbox["xywh"][3] > 0:
                        yolo_bbox = bbox_to_yolo(bpy.context.scene, tmp_bbox)
                        class_id = class_ids[defect_name]
                        label_text += (
                            f"{class_id} {yolo_bbox[0]:.6f} {yolo_bbox[1]:.6f} "
                            f"{yolo_bbox[2]:.6f} {yolo_bbox[3]:.6f}\n"
                        )
                        defect_bboxes.append(
                            {
                                "defect_type": defect_name,
                                "class_id": class_id,
                                "bbox": tmp_bbox,
                            }
                        )
                    tmp_mask_path.unlink(missing_ok=True)
            elif bbox is not None and bbox["xywh"][2] > 0 and bbox["xywh"][3] > 0:
                yolo_bbox = bbox_to_yolo(bpy.context.scene, bbox)
                label_text = f"0 {yolo_bbox[0]:.6f} {yolo_bbox[1]:.6f} {yolo_bbox[2]:.6f} {yolo_bbox[3]:.6f}\n"
            label_path.write_text(label_text, encoding="utf-8")
            label_rel = str(label_path.relative_to(output_dir))
            bbox_area_pixels = bbox["xywh"][2] * bbox["xywh"][3] if bbox is not None else 0
            label_info = {
                "mask": str(mask_path.relative_to(output_dir)),
                "overlay": str(overlay_path.relative_to(output_dir)),
                "label_yolo": label_rel,
                "bbox": bbox,
                "bbox_area_pixels": bbox_area_pixels,
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
                "task_type": f"reference_scene_{args.defect_type}_validation",
                "model_name": "QC7-1336",
                "geometry_profile": "qc7_1336_geometry",
                "appearance_profile": "qc71336_black_prebuilt_profile",
                "material_family": "prebuilt_authored_black_plastic",
                "defect_type": defect_info["defect_type"] if defect_info else "none",
                "defect_type_internal": defect_info["defect_type_internal"] if defect_info else None,
                "defect_type_canonical": defect_info["defect_type_canonical"] if defect_info else None,
                "has_defect": bool(defect_info),
                "reference_scene": str(Path(args.blend).resolve()),
                "model_blend": str(Path(args.model_blend).resolve()),
                "camera_name": camera.name,
                "camera_location": [float(camera.location.x), float(camera.location.y), float(camera.location.z)],
                "camera_rotation_euler": [
                    float(camera.rotation_euler.x),
                    float(camera.rotation_euler.y),
                    float(camera.rotation_euler.z),
                ],
                "foreign_material_version": FOREIGN_MATERIAL_VERSION if "foreign_material" in args.defect_type else None,
                "splay_version": SPLAY_VERSION if "splay" in args.defect_type else None,
                "defect": defect_info,
                "lightweight_label": label_info,
        "assigned_materials": assigned_materials,
        "main_plane_roughness_tuning": main_plane_roughness_tuning,
                "blend_file": blend_rel,
            }
        )

    metadata = {
        "script": str(Path(__file__).resolve()),
        "schema_version": "reference_normal_debug_v1",
        "baseline_version": BASELINE_VERSION,
        "baseline_summary": BASELINE_SUMMARY,
        "task_type": f"reference_scene_{args.defect_type}_validation",
        "reference_scene": str(Path(args.blend).resolve()),
        "model_blend": str(Path(args.model_blend).resolve()),
        "model_name": "QC7-1336",
        "geometry_profile": "qc7_1336_geometry",
        "appearance_profile": "qc71336_black_prebuilt_profile",
        "material_family": "prebuilt_authored_black_plastic",
        "defect_type": args.defect_type,
        "defect_type_internal": args.defect_type,
        "defect_type_canonical": args.defect_type,
        "foreign_material_version": FOREIGN_MATERIAL_VERSION if "foreign_material" in args.defect_type else None,
        "splay_version": SPLAY_VERSION if "splay" in args.defect_type else None,
        "render_width": args.width,
        "render_height": args.height,
        "cycles_samples": args.samples,
        "defect_seed": args.defect_seed,
        "debug_splay_strong": bool(args.debug_splay_strong),
        "gpu_info": gpu_info,
        "lighting": capture_light_summary(),
        "pack_error": pack_error,
        "samples": samples,
        "notes": [
            f"Baseline locked as {BASELINE_VERSION}.",
            BASELINE_SUMMARY,
            "Uses the manually authored materials embedded in QC7-1336-black.blend and intentionally skips script-side material reassignment.",
            "Only objects whose names contain QC8-8511-000N301002ST0101 are kept for rendering from the appended model blend.",
            "Camera was pulled back slightly to preserve more of the part silhouette in-frame.",
            "This reference script is now focused on foreign-material particles and splay streaks only.",
            "Foreign material is rendered as a small attached geometry object with its own material, while splay is rendered by modifying the underlying material response and exporting a separate mask helper patch.",
        ],
    }
    metadata_path = output_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
