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

BASELINE_VERSION = "qc75244_white_reference_baseline_v1"
BASELINE_SUMMARY = (
    "QC7-5244 white normal-part baseline in moxing1_test.blend with fixed reference camera, "
    "reference-scene lighting, and ultra-light two-zone matte-satin neutral white plastic."
)
PRIMARY_OBJECT_NAME = "QC7-5236-000N301002ST0101"
MIXED_COLOR_VERSION = "mixed_color_profiled_material_drift_v1"


MIXED_COLOR_MODEL_PROFILES = {
    "qc7-5236": {
        "description": "Front-facing QC7-5236/QC7-5244 large-main-plane mixed-color profile.",
        "debug_center": {
            "target_x": (0.715, 0.785),
            "target_y": (0.605, 0.645),
            "window": (0.680, 0.805, 0.595, 0.655),
            "placement_zone": "debug_center_right",
        },
        "zone_specs": {
            "upper_center": {
                "target_x": (0.610, 0.660),
                "target_y": (0.700, 0.748),
                "window": (0.575, 0.695, 0.675, 0.775),
            },
            "center_mid": {
                "target_x": (0.610, 0.690),
                "target_y": (0.655, 0.735),
                "window": (0.570, 0.730, 0.625, 0.765),
            },
            "center_right": {
                "target_x": (0.660, 0.735),
                "target_y": (0.630, 0.715),
                "window": (0.620, 0.775, 0.600, 0.745),
            },
            "lower_mid_right": {
                "target_x": (0.640, 0.720),
                "target_y": (0.590, 0.670),
                "window": (0.595, 0.760, 0.555, 0.705),
            },
            "mid_left": {
                "target_x": (0.535, 0.620),
                "target_y": (0.635, 0.730),
                "window": (0.500, 0.660, 0.600, 0.765),
            },
        },
        "zone_weights": [
            "center_mid",
            "center_mid",
            "center_mid",
            "lower_mid_right",
            "lower_mid_right",
            "mid_left",
            "mid_left",
            "center_right",
            "upper_center",
        ],
        "artifact_window": (0.86, 0.96, 0.74, 0.90),
        "fallback_window": (0.60, 0.84, 0.52, 0.78),
        "placement_offsets": {
            "upper_mid_right": (0.040, 0.015),
            "center_right": (0.050, -0.035),
            "center_mid": (-0.070, -0.145),
            "lower_mid_right": (0.015, -0.110),
            "upper_center": (-0.055, -0.070),
            "mid_left": (-0.115, -0.065),
            "debug_center_right": (-0.020, -0.055),
        },
        "radius_x_factor": (0.016, 0.032),
        "radius_y_factor": (0.0048, 0.0085),
        "use_projected_scoring": True,
        "apply_camera_plane_offsets": True,
    },
    "default_large_main_plane": {
        "description": "Generic fallback for large visible main-plane plastic parts; requires smoke validation.",
        "zone_specs": {
            "center": {
                "target_x": (0.44, 0.56),
                "target_y": (0.44, 0.56),
                "window": (0.34, 0.66, 0.34, 0.66),
            },
            "upper_center": {
                "target_x": (0.42, 0.58),
                "target_y": (0.58, 0.72),
                "window": (0.32, 0.68, 0.52, 0.78),
            },
            "lower_center": {
                "target_x": (0.42, 0.58),
                "target_y": (0.28, 0.42),
                "window": (0.32, 0.68, 0.22, 0.48),
            },
        },
        "zone_weights": ["center", "center", "upper_center", "lower_center"],
        "artifact_window": None,
        "fallback_window": (0.22, 0.78, 0.20, 0.80),
        "placement_offsets": {},
        "radius_x_factor": (0.015, 0.028),
        "radius_y_factor": (0.0027, 0.0060),
        "use_projected_scoring": True,
        "apply_camera_plane_offsets": False,
    },
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Render QC7-5244 white normal reference-scene images in moxing1_test.blend."
    )
    parser.add_argument("--blend", required=True)
    parser.add_argument("--stl", default=None)
    parser.add_argument("--output", required=True)
    parser.add_argument("--num", type=int, default=1)
    parser.add_argument("--start_index", type=int, default=0)
    parser.add_argument("--width", type=int, default=1536)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--samples", type=int, default=256)
    parser.add_argument("--validation_mode", action="store_true")
    parser.add_argument("--save_blend", action="store_true")
    parser.add_argument("--enable_mixed_color", action="store_true")
    parser.add_argument("--mixed_color_seed", type=int, default=43)
    parser.add_argument("--defect_count_max", type=int, default=1)
    parser.add_argument("--anchor_sides", nargs="+", choices=["front", "back"], default=["front"])
    parser.add_argument("--debug_mixed_color_strong", action="store_true")
    parser.add_argument("--debug_center_mixed_color", action="store_true")
    parser.add_argument("--debug_export_material_passes", action="store_true")
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


def find_principled(mat):
    for node in mat.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            return node
    raise RuntimeError(f"Principled BSDF not found in material {mat.name}")


def get_primary_object():
    obj = bpy.data.objects.get(PRIMARY_OBJECT_NAME)
    if obj is not None and obj.type == "MESH":
        return obj

    meshes = [candidate for candidate in bpy.data.objects if candidate.type == "MESH"]
    if not meshes:
        raise RuntimeError("No mesh objects found in blend scene.")

    def volume_score(candidate):
        _, _, dims = object_bbox_dims(candidate)
        return max(float(dims.x), 1e-6) * max(float(dims.y), 1e-6) * max(float(dims.z), 1e-6)

    meshes.sort(key=volume_score, reverse=True)
    return meshes[0]


def import_replacement_stl(stl_path, reference_obj):
    existing_names = {obj.name for obj in bpy.data.objects}
    bpy.ops.wm.stl_import(filepath=str(Path(stl_path).resolve()))
    imported_meshes = [
        obj for obj in bpy.data.objects
        if obj.name not in existing_names and obj.type == "MESH"
    ]
    if not imported_meshes:
        raise RuntimeError(f"Failed to import STL replacement from {stl_path}")

    imported_meshes.sort(key=lambda obj: len(obj.data.vertices), reverse=True)
    primary_obj = imported_meshes[0]
    primary_obj.name = f"{reference_obj.name}_{Path(stl_path).stem}"
    primary_obj.rotation_euler = reference_obj.rotation_euler.copy()
    primary_obj.scale = reference_obj.scale.copy()
    primary_obj.location = reference_obj.location.copy()
    bpy.context.view_layer.update()

    ref_bb_min, ref_bb_max, ref_dims = object_bbox_dims(reference_obj)
    _, _, imported_dims = object_bbox_dims(primary_obj)
    ref_max_dim = max(float(ref_dims.x), float(ref_dims.y), float(ref_dims.z), 1e-6)
    imported_max_dim = max(float(imported_dims.x), float(imported_dims.y), float(imported_dims.z), 1e-6)
    uniform_scale = ref_max_dim / imported_max_dim
    primary_obj.scale = Vector((
        primary_obj.scale.x * uniform_scale,
        primary_obj.scale.y * uniform_scale,
        primary_obj.scale.z * uniform_scale,
    ))
    bpy.context.view_layer.update()

    imp_bb_min, imp_bb_max, _ = object_bbox_dims(primary_obj)
    ref_center = (ref_bb_min + ref_bb_max) * 0.5
    imp_center = (imp_bb_min + imp_bb_max) * 0.5
    primary_obj.location += ref_center - imp_center
    bpy.context.view_layer.update()
    return primary_obj


def hide_non_primary_meshes(primary_obj):
    for obj in bpy.data.objects:
        if obj.type == "MESH" and obj.name != primary_obj.name:
            obj.hide_render = True
            obj.hide_viewport = True


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
    camera.data.lens = 80.0
    camera.data.sensor_width = 36.0
    camera.data.sensor_fit = "HORIZONTAL"
    camera.data.clip_start = 0.01
    camera.data.clip_end = 1000.0
    camera.data.shift_x = 0.0
    camera.data.shift_y = 0.06

    z_sign = 1.0 if side == "front" else -1.0
    location = center + Vector((0.02 * max_dim, -0.18 * max_dim, z_sign * 2.42 * max_dim))
    direction = center - location
    rot_quat = direction.to_track_quat("-Z", "Y")
    camera.location = location
    camera.rotation_euler = rot_quat.to_euler()
    camera.rotation_euler.rotate_axis("Z", math.radians(1.0 if side == "front" else -1.0))

    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    bpy.context.view_layer.update()
    return camera


def position_camera_for_anchor_side(camera, primary_obj, side="front"):
    bb_min, bb_max = world_bbox([primary_obj])
    center = (bb_min + bb_max) * 0.5
    span = bb_max - bb_min
    max_dim = max(float(abs(span.x)), float(abs(span.y)), float(abs(span.z)), 1e-3)
    z_sign = 1.0 if side == "front" else -1.0
    focus_target = center + Vector((0.0, 0.01 * max_dim, 0.0))
    location = center + Vector((0.02 * max_dim, -0.18 * max_dim, z_sign * 2.42 * max_dim))
    direction = focus_target - location
    camera.location = location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    camera.rotation_euler.rotate_axis("Z", math.radians(1.0 if side == "front" else -1.0))
    camera.data.shift_x = 0.0
    camera.data.shift_y = 0.06 if side == "front" else 0.035
    bpy.context.view_layer.update()
    return camera


def refine_camera_shift_for_defect(camera, scene, world_point, desired_x=0.50, desired_y=0.50, max_delta=0.14):
    projected = world_to_camera_view(scene, camera, world_point)
    origin_shift_x = float(camera.data.shift_x)
    origin_shift_y = float(camera.data.shift_y)
    camera.data.shift_x = max(-0.22, min(0.22, origin_shift_x + (float(projected.x) - desired_x) * 0.65))
    camera.data.shift_y = max(-0.22, min(0.22, origin_shift_y + (float(projected.y) - desired_y) * 0.65))
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


def apply_object_view_transform(primary_obj, defect_info, transform):
    rotation_deg = transform.get("rotation_degrees_xyz") or [0.0, 0.0, 0.0]
    translation = Vector(transform.get("translation_xyz") or [0.0, 0.0, 0.0])
    bb_min, bb_max = world_bbox([primary_obj])
    pivot = (bb_min + bb_max) * 0.5
    rotation = Matrix.Identity(4)
    rotation = Matrix.Rotation(math.radians(rotation_deg[2]), 4, "Z") @ rotation
    rotation = Matrix.Rotation(math.radians(rotation_deg[1]), 4, "Y") @ rotation
    rotation = Matrix.Rotation(math.radians(rotation_deg[0]), 4, "X") @ rotation
    matrix = Matrix.Translation(pivot + translation) @ rotation @ Matrix.Translation(-pivot)
    transform_objects = [primary_obj]
    for key in ("control_object", "mask_object", "object_name"):
        name = defect_info.get(key)
        obj = bpy.data.objects.get(name) if name else None
        if obj is not None and obj not in transform_objects:
            transform_objects.append(obj)
    for child_defect in defect_info.get("defects") or []:
        for key in ("control_object", "mask_object", "object_name"):
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


def apply_replacement_camera_tweak(camera, primary_obj, stl_path):
    stem = Path(stl_path).stem.lower()
    _, _, dims = object_bbox_dims(primary_obj)
    max_dim = max(float(dims.x), float(dims.y), float(dims.z), 1e-3)

    if stem == "qc7-5236":
        camera.location.x += 0.010 * max_dim
        camera.location.y += 0.018 * max_dim
        camera.location.z -= 0.020 * max_dim
        camera.rotation_euler.rotate_axis("Z", math.radians(-0.6))
    else:
        camera.location.z -= 0.015 * max_dim

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
            if any(device.type != "CPU" for device in cycles_pref.devices):
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


def tune_reference_lighting_for_white(base_energy_multiplier=1.0):
    scene = bpy.context.scene
    energy_scale_map = {
        "Area": 0.12,
        "Area.001": 0.07,
        "Area.002": 0.05,
        "Area.003": 1.04,
        "Area.004": 0.11,
    }
    warm_lights = {"Area.003"}
    cool_lights = {"Area", "Area.001", "Area.002", "Area.004"}

    for obj in bpy.data.objects:
        if obj.type != "LIGHT":
            continue
        light = obj.data
        scale = energy_scale_map.get(obj.name, 0.18)
        if getattr(light, "color", None) is not None:
            if obj.name in warm_lights:
                light.color = (1.0, 0.989, 0.975)
            elif obj.name in cool_lights:
                light.color = (0.97, 0.976, 0.988)
        base_energy = 2000.0 if light.type == "AREA" else 500.0
        light.energy = base_energy * scale * base_energy_multiplier
        if light.type == "AREA":
            light.shape = "RECTANGLE"
            if obj.name == "Area.003":
                light.size = 1.48
                light.size_y = 0.88
            else:
                light.size = 2.2
                light.size_y = 1.5

    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background is not None:
        background.inputs[0].default_value = (0.80, 0.804, 0.812, 1.0)
        background.inputs[1].default_value = 0.034

    scene.view_settings.look = "None"
    scene.view_settings.exposure = -0.31
    scene.render.film_transparent = False


def ensure_clean_reference_support(primary_obj, side="front"):
    bb_min, bb_max = world_bbox([primary_obj])
    center = (bb_min + bb_max) * 0.5
    span = bb_max - bb_min
    max_dim = max(float(abs(span.x)), float(abs(span.y)), float(abs(span.z)), 1e-3)

    floor = bpy.data.objects.get("QC75244_REFERENCE_FLOOR")
    if floor is None:
        bpy.ops.mesh.primitive_plane_add(size=2.0, location=(center.x, center.y, bb_min.z - 0.02 * max_dim))
        floor = bpy.context.active_object
        floor.name = "QC75244_REFERENCE_FLOOR"
    floor.scale = (1.65 * max_dim, 1.45 * max_dim, 1.0)
    floor_z = bb_min.z - 0.03 * max_dim if side == "front" else bb_max.z + 0.03 * max_dim
    floor.location = (center.x, center.y, floor_z)

    wall = bpy.data.objects.get("QC75244_REFERENCE_WALL")
    if wall is None:
        bpy.ops.mesh.primitive_plane_add(size=2.0, location=(center.x, center.y + 1.1 * max_dim, center.z + 0.65 * max_dim))
        wall = bpy.context.active_object
        wall.name = "QC75244_REFERENCE_WALL"
    wall.scale = (1.7 * max_dim, 1.15 * max_dim, 1.0)
    wall_z_offset = 0.62 * max_dim if side == "front" else -0.62 * max_dim
    wall.location = (center.x - 0.12 * max_dim, center.y + 1.00 * max_dim, center.z + wall_z_offset)
    wall.rotation_euler = (math.radians(86.0), 0.0, math.radians(180.0))

    floor_mat = bpy.data.materials.get("QC75244_REFERENCE_FLOOR_MAT")
    if floor_mat is None:
        floor_mat = bpy.data.materials.new("QC75244_REFERENCE_FLOOR_MAT")
        floor_mat.use_nodes = True
    floor_bsdf = find_principled(floor_mat)
    floor_bsdf.inputs["Base Color"].default_value = (0.85, 0.853, 0.858, 1.0)
    floor_bsdf.inputs["Roughness"].default_value = 0.86
    floor_spec_name = "Specular IOR Level" if "Specular IOR Level" in floor_bsdf.inputs else "Specular"
    floor_bsdf.inputs[floor_spec_name].default_value = 0.06

    wall_mat = bpy.data.materials.get("QC75244_REFERENCE_WALL_MAT")
    if wall_mat is None:
        wall_mat = bpy.data.materials.new("QC75244_REFERENCE_WALL_MAT")
        wall_mat.use_nodes = True
    wall_bsdf = find_principled(wall_mat)
    wall_bsdf.inputs["Base Color"].default_value = (0.30, 0.315, 0.335, 1.0)
    wall_bsdf.inputs["Roughness"].default_value = 0.95
    wall_spec_name = "Specular IOR Level" if "Specular IOR Level" in wall_bsdf.inputs else "Specular"
    wall_bsdf.inputs[wall_spec_name].default_value = 0.04

    floor.data.materials.clear()
    floor.data.materials.append(floor_mat)
    wall.data.materials.clear()
    wall.data.materials.append(wall_mat)
    floor.hide_render = False
    wall.hide_render = False
    bpy.context.view_layer.update()
    return {
        "side": side,
        "floor_location": [round(float(floor.location.x), 5), round(float(floor.location.y), 5), round(float(floor.location.z), 5)],
        "wall_location": [round(float(wall.location.x), 5), round(float(wall.location.y), 5), round(float(wall.location.z), 5)],
        "occlusion_policy": "floor_and_wall_placed_behind_model_relative_to_anchor_side_camera",
    }


def build_qc75244_white_material(
    material_name,
    base_color,
    roughness_value,
    specular_value,
    coat_weight,
    coat_roughness,
    bump_strength,
    roughness_mix_fac,
    roughness_floor,
):
    mat = bpy.data.materials.get(material_name)
    if mat is None:
        mat = bpy.data.materials.new(material_name)
        mat.use_nodes = True
    else:
        mat.use_nodes = True

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (700, 0)

    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.name = "QC75244_MAIN_BSDF"
    bsdf.location = (380, 0)
    bsdf.inputs["Roughness"].default_value = roughness_value
    spec_name = "Specular IOR Level" if "Specular IOR Level" in bsdf.inputs else "Specular"
    bsdf.inputs[spec_name].default_value = specular_value
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = coat_weight
        bsdf.inputs["Coat Roughness"].default_value = coat_roughness
    elif "Clearcoat" in bsdf.inputs:
        bsdf.inputs["Clearcoat"].default_value = coat_weight
        bsdf.inputs["Clearcoat Roughness"].default_value = coat_roughness

    base_color_rgb = nodes.new("ShaderNodeRGB")
    base_color_rgb.name = "QC75244_BASE_COLOR_RGB"
    base_color_rgb.location = (90, 260)
    base_color_rgb.outputs["Color"].default_value = base_color

    tex_coord = nodes.new("ShaderNodeTexCoord")
    tex_coord.location = (-900, -40)

    mapping = nodes.new("ShaderNodeMapping")
    mapping.location = (-700, -40)
    mapping.inputs["Scale"].default_value = (22.0, 22.0, 22.0)

    noise = nodes.new("ShaderNodeTexNoise")
    noise.location = (-500, 90)
    noise.inputs["Scale"].default_value = 10.0
    noise.inputs["Detail"].default_value = 3.9
    noise.inputs["Roughness"].default_value = 0.43

    fine_noise = nodes.new("ShaderNodeTexNoise")
    fine_noise.location = (-500, -180)
    fine_noise.inputs["Scale"].default_value = 44.0
    fine_noise.inputs["Detail"].default_value = 8.2
    fine_noise.inputs["Roughness"].default_value = 0.40

    bump = nodes.new("ShaderNodeBump")
    bump.location = (120, -170)
    bump.inputs["Strength"].default_value = bump_strength
    bump.inputs["Distance"].default_value = 0.02

    roughness_mix = nodes.new("ShaderNodeMixRGB")
    roughness_mix.name = "QC75244_BASE_ROUGHNESS_MIX"
    roughness_mix.location = (110, 120)
    roughness_mix.blend_type = "MIX"
    roughness_mix.inputs["Fac"].default_value = roughness_mix_fac
    roughness_mix.inputs[1].default_value = (roughness_floor, roughness_floor, roughness_floor, 1.0)

    links.new(base_color_rgb.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(tex_coord.outputs["Object"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    links.new(mapping.outputs["Vector"], fine_noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], roughness_mix.inputs[2])
    links.new(fine_noise.outputs["Fac"], bump.inputs["Height"])
    links.new(roughness_mix.outputs["Color"], bsdf.inputs["Roughness"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    return mat


def build_qc75244_two_zone_materials():
    main_plane_material = build_qc75244_white_material(
        material_name="QC75244_WHITE_MAIN_PLANE_MAT",
        base_color=(0.700, 0.706, 0.714, 1.0),
        roughness_value=0.570,
        specular_value=0.106,
        coat_weight=0.009,
        coat_roughness=0.10,
        bump_strength=0.014,
        roughness_mix_fac=0.27,
        roughness_floor=0.565,
    )
    edge_wall_material = build_qc75244_white_material(
        material_name="QC75244_WHITE_EDGE_WALL_MAT",
        base_color=(0.716, 0.722, 0.730, 1.0),
        roughness_value=0.540,
        specular_value=0.122,
        coat_weight=0.010,
        coat_roughness=0.09,
        bump_strength=0.016,
        roughness_mix_fac=0.30,
        roughness_floor=0.545,
    )
    return main_plane_material, edge_wall_material


def assign_white_material(primary_obj):
    main_plane_material, edge_wall_material = build_qc75244_two_zone_materials()
    mesh = primary_obj.data
    mesh.materials.clear()
    mesh.materials.append(main_plane_material)
    mesh.materials.append(edge_wall_material)

    bb_min = Vector((min(v[0] for v in primary_obj.bound_box), min(v[1] for v in primary_obj.bound_box), min(v[2] for v in primary_obj.bound_box)))
    bb_max = Vector((max(v[0] for v in primary_obj.bound_box), max(v[1] for v in primary_obj.bound_box), max(v[2] for v in primary_obj.bound_box)))
    span = bb_max - bb_min
    safe_span = Vector((max(float(span.x), 1e-6), max(float(span.y), 1e-6), max(float(span.z), 1e-6)))

    candidate_polygons = []
    main_count = 0
    edge_count = 0
    for poly in mesh.polygons:
        center = poly.center
        normal = poly.normal.normalized()
        x_ratio = (center.x - bb_min.x) / safe_span.x
        y_ratio = (center.y - bb_min.y) / safe_span.y
        z_ratio = (center.z - bb_min.z) / safe_span.z

        in_main_window = 0.16 <= x_ratio <= 0.84 and 0.15 <= y_ratio <= 0.87
        slightly_recessed = 0.40 <= z_ratio <= 0.86
        face_on_main_axis = abs(float(normal.z)) >= 0.72
        is_main_plane = in_main_window and face_on_main_axis and (slightly_recessed or normal.z <= -0.72)
        poly.material_index = 0 if is_main_plane else 1
        if is_main_plane:
            main_count += 1
            if 0.18 <= x_ratio <= 0.84 and 0.20 <= y_ratio <= 0.82 and face_on_main_axis:
                candidate_polygons.append(poly.index)
        else:
            edge_count += 1

    return {
        "main_plane_material": main_plane_material.name,
        "edge_wall_material": edge_wall_material.name,
        "main_face_count": main_count,
        "edge_face_count": edge_count,
        "mixed_color_candidate_polygons": candidate_polygons,
    }


def make_alpha_material(name, color, roughness, specular, alpha):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.blend_method = "BLEND"
    if hasattr(mat, "shadow_method"):
        try:
            mat.shadow_method = "NONE"
        except TypeError:
            mat.shadow_method = "HASHED"
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (500, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (200, 0)
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    spec_name = "Specular IOR Level" if "Specular IOR Level" in bsdf.inputs else "Specular"
    bsdf.inputs[spec_name].default_value = specular
    bsdf.inputs["Alpha"].default_value = alpha
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    return mat


def add_patch_surface_noise(mat, bump_strength, roughness_jitter):
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = find_principled(mat)

    tex_coord = nodes.new("ShaderNodeTexCoord")
    tex_coord.location = (-950, -120)
    mapping = nodes.new("ShaderNodeMapping")
    mapping.location = (-760, -120)
    mapping.inputs["Scale"].default_value = (
        random.uniform(3.8, 5.6),
        random.uniform(3.8, 5.6),
        random.uniform(3.8, 5.6),
    )
    noise = nodes.new("ShaderNodeTexNoise")
    noise.location = (-560, -20)
    noise.inputs["Scale"].default_value = random.uniform(2.2, 3.4)
    noise.inputs["Detail"].default_value = random.uniform(1.3, 2.1)
    noise.inputs["Roughness"].default_value = random.uniform(0.20, 0.32)
    bump = nodes.new("ShaderNodeBump")
    bump.location = (-60, -150)
    bump.inputs["Strength"].default_value = bump_strength
    bump.inputs["Distance"].default_value = 0.01
    rough_mix = nodes.new("ShaderNodeMixRGB")
    rough_mix.location = (-50, 80)
    rough_mix.blend_type = "MIX"
    rough_mix.inputs["Fac"].default_value = 0.18
    base_roughness = bsdf.inputs["Roughness"].default_value
    jittered = min(max(base_roughness + roughness_jitter, 0.0), 1.0)
    rough_mix.inputs[1].default_value = (base_roughness, base_roughness, base_roughness, 1.0)
    rough_mix.inputs[2].default_value = (jittered, jittered, jittered, 1.0)

    links.new(tex_coord.outputs["Object"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(noise.outputs["Color"], rough_mix.inputs["Color1"] if "Color1" in rough_mix.inputs else rough_mix.inputs[1])
    links.new(rough_mix.outputs["Color"], bsdf.inputs["Roughness"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def mixed_color_reference_materials():
    neutral_dirty_gray = (
        random.uniform(0.54, 0.61),
        random.uniform(0.545, 0.615),
        random.uniform(0.535, 0.605),
        1.0,
    )
    cool_dirty_gray = (
        random.uniform(0.52, 0.59),
        random.uniform(0.535, 0.605),
        random.uniform(0.54, 0.615),
        1.0,
    )
    soft_shadow_gray = (
        random.uniform(0.48, 0.56),
        random.uniform(0.49, 0.57),
        random.uniform(0.49, 0.57),
        1.0,
    )
    palettes = [
        neutral_dirty_gray,
        neutral_dirty_gray,
        cool_dirty_gray,
        soft_shadow_gray,
    ]
    return {
        "tone_rgba": random.choice(palettes),
        "mix_factor": random.uniform(0.46, 0.66),
        "roughness_delta": random.uniform(0.04, 0.11),
        "wave_scale": random.uniform(14.0, 24.0),
        "wave_distortion": random.uniform(7.0, 12.0),
        "wave_detail_scale": random.uniform(2.4, 4.2),
        "wave_phase": random.uniform(-0.35, 0.35),
        "distortion_noise_scale": random.uniform(5.5, 9.5),
        "distortion_noise_detail": random.uniform(2.8, 4.2),
        "distortion_vector_strength": random.uniform(0.26, 0.46),
        "envelope_softness": random.uniform(1.05, 1.38),
        "envelope_noise_scale": random.uniform(3.8, 7.2),
        "envelope_noise_detail": random.uniform(3.0, 4.6),
        "envelope_noise_mix": random.uniform(0.62, 0.92),
        "fine_noise_scale": random.uniform(34.0, 56.0),
        "fine_noise_detail": random.uniform(6.0, 9.0),
        "fine_noise_strength": random.uniform(0.18, 0.30),
        "break_noise_scale": random.uniform(3.4, 6.2),
        "break_noise_detail": random.uniform(3.0, 5.2),
        "break_low": random.uniform(0.44, 0.56),
        "break_high": random.uniform(0.62, 0.78),
        "break_floor": random.uniform(0.16, 0.32),
        "segment_frequency": random.choice([2.0, 2.5, 3.0]),
        "segment_phase": random.uniform(-3.14159, 3.14159),
        "segment_low": random.uniform(0.40, 0.52),
        "segment_high": random.uniform(0.62, 0.78),
        "segment_floor": random.uniform(0.14, 0.28),
        "mask_low": random.uniform(0.26, 0.36),
        "mask_high": random.uniform(0.42, 0.52),
        "mask_boost": random.uniform(2.1, 3.0),
        "directional_strength": random.uniform(0.85, 1.10),
        "focal_radius": random.uniform(0.13, 0.22),
        "focal_strength": random.uniform(0.28, 0.44),
        "rgb_visibility_boost": random.uniform(2.4, 3.4),
        "focal_rgb_boost": random.uniform(0.08, 0.18),
        "color_noise_strength": 0.01,
        "label_threshold": random.uniform(0.15, 0.22),
        "flow_direction_angle": random.uniform(-0.20, 0.14),
        "curve_strength": random.uniform(0.22, 0.42),
        "curve_frequency": random.uniform(4.2, 8.0),
        "curve_phase": random.uniform(-3.14159, 3.14159),
        "soft_low": random.uniform(0.12, 0.25),
        "soft_high": random.uniform(0.45, 0.60),
        "halo_weight": random.uniform(0.16, 0.30),
        "halo_mix_strength": random.uniform(0.08, 0.17),
        "width_noise_scale": random.uniform(1.6, 3.4),
        "width_noise_detail": random.uniform(3.8, 6.4),
        "width_noise_strength": random.uniform(0.42, 0.70),
        # Visibility calibration pass: let the low-frequency material drift dominate RGB,
        # while the directional streak remains a secondary detail layer.
        "soft_color_mask_weight": 0.82,
        "streak_detail_mask_weight": 0.26,
        "focal_mask_weight": 0.055,
        "label_rgb_mask_weight": 0.35,
        "soft_mix_strength": 0.86,
        "detail_mix_strength": random.uniform(0.12, 0.22),
    }


def get_mixed_color_model_profile(primary_obj):
    object_name = primary_obj.name.lower()
    for key, profile in MIXED_COLOR_MODEL_PROFILES.items():
        if key != "default_large_main_plane" and key in object_name:
            return key, profile
    return "default_large_main_plane", MIXED_COLOR_MODEL_PROFILES["default_large_main_plane"]


def choose_profile_placement(profile, debug_center_mixed_color=False):
    if debug_center_mixed_color and profile.get("debug_center"):
        debug_spec = profile["debug_center"]
        return (
            debug_spec["placement_zone"],
            random.uniform(*debug_spec["target_x"]),
            random.uniform(*debug_spec["target_y"]),
            debug_spec["window"],
        )

    zone_specs = profile["zone_specs"]
    zone_weights = profile.get("zone_weights") or list(zone_specs.keys())
    placement_zone = random.choice(zone_weights)
    spec = zone_specs[placement_zone]
    return (
        placement_zone,
        random.uniform(*spec["target_x"]),
        random.uniform(*spec["target_y"]),
        spec["window"],
    )


def create_mixed_color_control_object(world_point, tangent, bitangent, world_normal, radius_x, radius_y, name):
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_type = "PLAIN_AXES"
    obj.empty_display_size = max(radius_x, radius_y) * 0.35
    bpy.context.collection.objects.link(obj)

    rotation = Matrix((
        tangent.normalized(),
        bitangent.normalized(),
        world_normal.normalized(),
    )).transposed().to_4x4()
    rotation.translation = world_point
    obj.matrix_world = rotation
    obj.scale = Vector((max(radius_x, 1e-5), max(radius_y, 1e-5), max(radius_x, radius_y, 1e-5)))
    return obj


def cleanup_mixed_color_objects():
    to_remove = [obj for obj in bpy.data.objects if obj.name.startswith("QC75244_MIXED_COLOR_")]
    for obj in to_remove:
        mesh = getattr(obj, "data", None)
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh is not None and hasattr(mesh, "users") and mesh.users == 0:
            bpy.data.meshes.remove(mesh, do_unlink=True)


def cleanup_mixed_color_material_nodes(material):
    if material is None or material.node_tree is None:
        return
    nodes = material.node_tree.nodes
    to_remove = [node for node in nodes if node.name.startswith("QC75244_MIXED_")]
    for node in to_remove:
        nodes.remove(node)


def build_mixed_color_mask_nodes(tree, links, control_object, defect_params, prefix):
    nodes = tree.nodes

    tex_coord = nodes.new("ShaderNodeTexCoord")
    tex_coord.name = f"{prefix}_TEXCOORD"
    tex_coord.location = (-1000, 0)
    tex_coord.object = control_object

    mapping = nodes.new("ShaderNodeMapping")
    mapping.name = f"{prefix}_MAPPING"
    mapping.location = (-820, 0)
    mapping.inputs["Rotation"].default_value = (0.0, 0.0, defect_params["flow_direction_angle"])

    separate_xyz = nodes.new("ShaderNodeSeparateXYZ")
    separate_xyz.name = f"{prefix}_SEPARATE_XYZ"
    separate_xyz.location = (-620, 300)

    curve_freq = nodes.new("ShaderNodeMath")
    curve_freq.name = f"{prefix}_CURVE_FREQ"
    curve_freq.location = (-620, 455)
    curve_freq.operation = "MULTIPLY"
    curve_freq.inputs[1].default_value = defect_params["curve_frequency"]

    curve_phase = nodes.new("ShaderNodeMath")
    curve_phase.name = f"{prefix}_CURVE_PHASE"
    curve_phase.location = (-430, 455)
    curve_phase.operation = "ADD"
    curve_phase.inputs[1].default_value = defect_params["curve_phase"]

    curve_sine = nodes.new("ShaderNodeMath")
    curve_sine.name = f"{prefix}_CURVE_SINE"
    curve_sine.location = (-245, 455)
    curve_sine.operation = "SINE"

    curve_scale = nodes.new("ShaderNodeMath")
    curve_scale.name = f"{prefix}_CURVE_SCALE"
    curve_scale.location = (-60, 455)
    curve_scale.operation = "MULTIPLY"
    curve_scale.inputs[1].default_value = defect_params["curve_strength"]

    curved_y = nodes.new("ShaderNodeMath")
    curved_y.name = f"{prefix}_CURVED_Y"
    curved_y.location = (-245, 345)
    curved_y.operation = "ADD"

    abs_x = nodes.new("ShaderNodeMath")
    abs_x.name = f"{prefix}_ABS_X"
    abs_x.location = (-430, 335)
    abs_x.operation = "ABSOLUTE"

    abs_y = nodes.new("ShaderNodeMath")
    abs_y.name = f"{prefix}_ABS_Y"
    abs_y.location = (-430, 260)
    abs_y.operation = "ABSOLUTE"

    y_soften = nodes.new("ShaderNodeMath")
    y_soften.name = f"{prefix}_Y_SOFTEN"
    y_soften.location = (-245, 260)
    y_soften.operation = "MULTIPLY"
    y_soften.inputs[1].default_value = defect_params["envelope_softness"]

    width_noise = nodes.new("ShaderNodeTexNoise")
    width_noise.name = f"{prefix}_WIDTH_NOISE"
    width_noise.location = (-620, 610)
    width_noise.inputs["Scale"].default_value = defect_params["width_noise_scale"]
    width_noise.inputs["Detail"].default_value = defect_params["width_noise_detail"]
    width_noise.inputs["Roughness"].default_value = 0.48

    width_noise_center = nodes.new("ShaderNodeMath")
    width_noise_center.name = f"{prefix}_WIDTH_NOISE_CENTER"
    width_noise_center.location = (-430, 610)
    width_noise_center.operation = "SUBTRACT"
    width_noise_center.inputs[1].default_value = 0.5

    width_noise_scale = nodes.new("ShaderNodeMath")
    width_noise_scale.name = f"{prefix}_WIDTH_NOISE_SCALE"
    width_noise_scale.location = (-245, 610)
    width_noise_scale.operation = "MULTIPLY"
    width_noise_scale.inputs[1].default_value = defect_params["width_noise_strength"]

    width_factor = nodes.new("ShaderNodeMath")
    width_factor.name = f"{prefix}_WIDTH_FACTOR"
    width_factor.location = (-60, 610)
    width_factor.operation = "ADD"
    width_factor.inputs[0].default_value = 1.0
    width_factor.use_clamp = True

    y_width_modulated = nodes.new("ShaderNodeMath")
    y_width_modulated.name = f"{prefix}_Y_WIDTH_MODULATED"
    y_width_modulated.location = (-60, 345)
    y_width_modulated.operation = "MULTIPLY"

    combine_envelope = nodes.new("ShaderNodeCombineXYZ")
    combine_envelope.name = f"{prefix}_COMBINE_ENVELOPE"
    combine_envelope.location = (-45, 300)

    envelope_length = nodes.new("ShaderNodeVectorMath")
    envelope_length.name = f"{prefix}_ENVELOPE_LENGTH"
    envelope_length.location = (150, 300)
    envelope_length.operation = "LENGTH"

    envelope_map = nodes.new("ShaderNodeMapRange")
    envelope_map.name = f"{prefix}_ENVELOPE_MAP"
    envelope_map.location = (350, 300)
    envelope_map.clamp = True
    envelope_map.inputs["From Min"].default_value = 0.10
    envelope_map.inputs["From Max"].default_value = 1.02
    envelope_map.inputs["To Min"].default_value = 1.0
    envelope_map.inputs["To Max"].default_value = 0.0

    distortion_noise = nodes.new("ShaderNodeTexNoise")
    distortion_noise.name = f"{prefix}_DISTORTION_NOISE"
    distortion_noise.location = (-620, 120)
    distortion_noise.inputs["Scale"].default_value = defect_params["distortion_noise_scale"]
    distortion_noise.inputs["Detail"].default_value = defect_params["distortion_noise_detail"]
    distortion_noise.inputs["Roughness"].default_value = 0.46

    distortion_center = nodes.new("ShaderNodeVectorMath")
    distortion_center.name = f"{prefix}_DISTORTION_CENTER"
    distortion_center.location = (-430, 120)
    distortion_center.operation = "SUBTRACT"
    distortion_center.inputs[1].default_value = (0.5, 0.5, 0.5)

    distortion_scale = nodes.new("ShaderNodeVectorMath")
    distortion_scale.name = f"{prefix}_DISTORTION_SCALE"
    distortion_scale.location = (-245, 120)
    distortion_scale.operation = "SCALE"
    distortion_scale.inputs[3].default_value = defect_params["distortion_vector_strength"]

    distorted_vector = nodes.new("ShaderNodeVectorMath")
    distorted_vector.name = f"{prefix}_DISTORTED_VECTOR"
    distorted_vector.location = (-45, 120)
    distorted_vector.operation = "ADD"

    wave = nodes.new("ShaderNodeTexWave")
    wave.name = f"{prefix}_WAVE"
    wave.location = (160, 80)
    wave.wave_type = "BANDS"
    wave.bands_direction = "Y"
    wave.inputs["Scale"].default_value = defect_params["wave_scale"]
    wave.inputs["Distortion"].default_value = defect_params["wave_distortion"]
    wave.inputs["Detail Scale"].default_value = defect_params["wave_detail_scale"]
    wave.inputs["Detail Roughness"].default_value = 0.42
    wave.inputs["Phase Offset"].default_value = defect_params["wave_phase"]

    directional_ramp = nodes.new("ShaderNodeValToRGB")
    directional_ramp.name = f"{prefix}_DIRECTIONAL_RAMP"
    directional_ramp.location = (375, 80)
    directional_ramp.color_ramp.interpolation = "B_SPLINE"
    directional_ramp.color_ramp.elements[0].position = 0.41
    directional_ramp.color_ramp.elements[1].position = 0.60
    directional_ramp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    directional_ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)

    directional_bw = nodes.new("ShaderNodeRGBToBW")
    directional_bw.name = f"{prefix}_DIRECTIONAL_BW"
    directional_bw.location = (565, 80)

    envelope_noise = nodes.new("ShaderNodeTexNoise")
    envelope_noise.name = f"{prefix}_ENVELOPE_NOISE"
    envelope_noise.location = (160, 210)
    envelope_noise.inputs["Scale"].default_value = defect_params["envelope_noise_scale"]
    envelope_noise.inputs["Detail"].default_value = defect_params["envelope_noise_detail"]
    envelope_noise.inputs["Roughness"].default_value = 0.44

    envelope_noise_mix = nodes.new("ShaderNodeMath")
    envelope_noise_mix.name = f"{prefix}_ENVELOPE_NOISE_MIX"
    envelope_noise_mix.location = (350, 210)
    envelope_noise_mix.operation = "MULTIPLY"
    envelope_noise_mix.inputs[1].default_value = defect_params["envelope_noise_mix"]

    envelope_noise_add = nodes.new("ShaderNodeMath")
    envelope_noise_add.name = f"{prefix}_ENVELOPE_NOISE_ADD"
    envelope_noise_add.location = (540, 210)
    envelope_noise_add.operation = "ADD"
    envelope_noise_add.use_clamp = True
    envelope_noise_add.inputs[0].default_value = 0.85

    envelope_modulated = nodes.new("ShaderNodeMath")
    envelope_modulated.name = f"{prefix}_ENVELOPE_MODULATED"
    envelope_modulated.location = (740, 210)
    envelope_modulated.operation = "MULTIPLY"
    envelope_modulated.use_clamp = True

    soft_mask_scale = nodes.new("ShaderNodeMath")
    soft_mask_scale.name = f"{prefix}_SOFT_MASK_SCALE"
    soft_mask_scale.location = (930, 210)
    soft_mask_scale.operation = "MULTIPLY"
    soft_mask_scale.inputs[1].default_value = 1.18

    soft_ramp = nodes.new("ShaderNodeValToRGB")
    soft_ramp.name = f"{prefix}_SOFT_RAMP"
    soft_ramp.location = (1125, 210)
    soft_ramp.color_ramp.interpolation = "B_SPLINE"
    soft_ramp.color_ramp.elements[0].position = defect_params["soft_low"]
    soft_ramp.color_ramp.elements[1].position = defect_params["soft_high"]
    soft_ramp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    soft_ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)

    soft_bw = nodes.new("ShaderNodeRGBToBW")
    soft_bw.name = f"{prefix}_SOFT_BW"
    soft_bw.location = (1315, 210)

    halo_ramp = nodes.new("ShaderNodeValToRGB")
    halo_ramp.name = f"{prefix}_HALO_RAMP"
    halo_ramp.location = (1125, 330)
    halo_ramp.color_ramp.interpolation = "B_SPLINE"
    halo_ramp.color_ramp.elements[0].position = max(0.025, defect_params["soft_low"] * 0.28)
    halo_ramp.color_ramp.elements[1].position = max(0.24, defect_params["soft_high"] * 0.92)
    halo_ramp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    halo_ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)

    halo_bw = nodes.new("ShaderNodeRGBToBW")
    halo_bw.name = f"{prefix}_HALO_BW"
    halo_bw.location = (1315, 330)

    directional_enveloped = nodes.new("ShaderNodeMath")
    directional_enveloped.name = f"{prefix}_DIRECTIONAL_ENVELOPED"
    directional_enveloped.location = (740, 80)
    directional_enveloped.operation = "MULTIPLY"
    directional_enveloped.use_clamp = True

    fine_noise = nodes.new("ShaderNodeTexNoise")
    fine_noise.name = f"{prefix}_FINE_NOISE"
    fine_noise.location = (160, -90)
    fine_noise.inputs["Scale"].default_value = defect_params["fine_noise_scale"]
    fine_noise.inputs["Detail"].default_value = defect_params["fine_noise_detail"]
    fine_noise.inputs["Roughness"].default_value = 0.38

    fine_strength = nodes.new("ShaderNodeMath")
    fine_strength.name = f"{prefix}_FINE_STRENGTH"
    fine_strength.location = (350, -90)
    fine_strength.operation = "MULTIPLY"
    fine_strength.inputs[1].default_value = defect_params["fine_noise_strength"]

    fine_enveloped = nodes.new("ShaderNodeMath")
    fine_enveloped.name = f"{prefix}_FINE_ENVELOPED"
    fine_enveloped.location = (540, -20)
    fine_enveloped.operation = "MULTIPLY"
    fine_enveloped.use_clamp = True

    break_noise = nodes.new("ShaderNodeTexNoise")
    break_noise.name = f"{prefix}_BREAK_NOISE"
    break_noise.location = (350, -250)
    break_noise.inputs["Scale"].default_value = defect_params["break_noise_scale"]
    break_noise.inputs["Detail"].default_value = defect_params["break_noise_detail"]
    break_noise.inputs["Roughness"].default_value = 0.52

    break_ramp = nodes.new("ShaderNodeValToRGB")
    break_ramp.name = f"{prefix}_BREAK_RAMP"
    break_ramp.location = (555, -250)
    break_ramp.color_ramp.interpolation = "EASE"
    break_ramp.color_ramp.elements[0].position = defect_params["break_low"]
    break_ramp.color_ramp.elements[1].position = defect_params["break_high"]
    break_ramp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    break_ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)

    break_bw = nodes.new("ShaderNodeRGBToBW")
    break_bw.name = f"{prefix}_BREAK_BW"
    break_bw.location = (745, -250)

    break_amp = nodes.new("ShaderNodeMath")
    break_amp.name = f"{prefix}_BREAK_AMP"
    break_amp.location = (930, -250)
    break_amp.operation = "MULTIPLY"
    break_amp.inputs[1].default_value = max(0.0, 1.0 - defect_params["break_floor"])

    break_mask = nodes.new("ShaderNodeMath")
    break_mask.name = f"{prefix}_BREAK_MASK"
    break_mask.location = (1120, -250)
    break_mask.operation = "ADD"
    break_mask.use_clamp = True
    break_mask.inputs[0].default_value = defect_params["break_floor"]

    segment_freq = nodes.new("ShaderNodeMath")
    segment_freq.name = f"{prefix}_SEGMENT_FREQ"
    segment_freq.location = (-430, -395)
    segment_freq.operation = "MULTIPLY"
    segment_freq.inputs[1].default_value = defect_params["segment_frequency"]

    segment_phase = nodes.new("ShaderNodeMath")
    segment_phase.name = f"{prefix}_SEGMENT_PHASE"
    segment_phase.location = (-245, -395)
    segment_phase.operation = "ADD"
    segment_phase.inputs[1].default_value = defect_params["segment_phase"]

    segment_sine = nodes.new("ShaderNodeMath")
    segment_sine.name = f"{prefix}_SEGMENT_SINE"
    segment_sine.location = (-60, -395)
    segment_sine.operation = "SINE"

    segment_abs = nodes.new("ShaderNodeMath")
    segment_abs.name = f"{prefix}_SEGMENT_ABS"
    segment_abs.location = (130, -395)
    segment_abs.operation = "ABSOLUTE"

    segment_ramp = nodes.new("ShaderNodeValToRGB")
    segment_ramp.name = f"{prefix}_SEGMENT_RAMP"
    segment_ramp.location = (350, -395)
    segment_ramp.color_ramp.interpolation = "EASE"
    segment_ramp.color_ramp.elements[0].position = defect_params["segment_low"]
    segment_ramp.color_ramp.elements[1].position = defect_params["segment_high"]
    segment_ramp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    segment_ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)

    segment_bw = nodes.new("ShaderNodeRGBToBW")
    segment_bw.name = f"{prefix}_SEGMENT_BW"
    segment_bw.location = (540, -395)

    segment_amp = nodes.new("ShaderNodeMath")
    segment_amp.name = f"{prefix}_SEGMENT_AMP"
    segment_amp.location = (730, -395)
    segment_amp.operation = "MULTIPLY"
    segment_amp.inputs[1].default_value = max(0.0, 1.0 - defect_params["segment_floor"])

    segment_mask = nodes.new("ShaderNodeMath")
    segment_mask.name = f"{prefix}_SEGMENT_MASK"
    segment_mask.location = (930, -395)
    segment_mask.operation = "ADD"
    segment_mask.use_clamp = True
    segment_mask.inputs[0].default_value = defect_params["segment_floor"]

    combined_break_mask = nodes.new("ShaderNodeMath")
    combined_break_mask.name = f"{prefix}_COMBINED_BREAK_MASK"
    combined_break_mask.location = (1320, -315)
    combined_break_mask.operation = "MULTIPLY"
    combined_break_mask.use_clamp = True

    focal_xy = nodes.new("ShaderNodeCombineXYZ")
    focal_xy.name = f"{prefix}_FOCAL_XY"
    focal_xy.location = (145, 410)
    focal_xy.inputs["X"].default_value = 0.0
    focal_xy.inputs["Y"].default_value = 0.0
    focal_xy.inputs["Z"].default_value = 0.0

    focal_length = nodes.new("ShaderNodeVectorMath")
    focal_length.name = f"{prefix}_FOCAL_LENGTH"
    focal_length.location = (355, 410)
    focal_length.operation = "LENGTH"

    focal_map = nodes.new("ShaderNodeMapRange")
    focal_map.name = f"{prefix}_FOCAL_MAP"
    focal_map.location = (555, 410)
    focal_map.clamp = True
    focal_map.inputs["From Min"].default_value = 0.0
    focal_map.inputs["From Max"].default_value = defect_params["focal_radius"]
    focal_map.inputs["To Min"].default_value = 1.0
    focal_map.inputs["To Max"].default_value = 0.0

    focal_noise = nodes.new("ShaderNodeTexNoise")
    focal_noise.name = f"{prefix}_FOCAL_NOISE"
    focal_noise.location = (355, 500)
    focal_noise.inputs["Scale"].default_value = random.uniform(6.0, 12.0)
    focal_noise.inputs["Detail"].default_value = random.uniform(2.0, 3.6)
    focal_noise.inputs["Roughness"].default_value = 0.42

    focal_noise_mix = nodes.new("ShaderNodeMath")
    focal_noise_mix.name = f"{prefix}_FOCAL_NOISE_MIX"
    focal_noise_mix.location = (555, 500)
    focal_noise_mix.operation = "MULTIPLY"
    focal_noise_mix.inputs[1].default_value = 0.35

    focal_mask = nodes.new("ShaderNodeMath")
    focal_mask.name = f"{prefix}_FOCAL_MASK"
    focal_mask.location = (760, 455)
    focal_mask.operation = "MULTIPLY"
    focal_mask.use_clamp = True

    mask_boost = nodes.new("ShaderNodeMath")
    mask_boost.name = f"{prefix}_MASK_BOOST"
    mask_boost.location = (1120, -55)
    mask_boost.operation = "MULTIPLY"
    mask_boost.inputs[1].default_value = defect_params["mask_boost"]

    focal_strength = nodes.new("ShaderNodeMath")
    focal_strength.name = f"{prefix}_FOCAL_STRENGTH"
    focal_strength.location = (950, 455)
    focal_strength.operation = "MULTIPLY"
    focal_strength.inputs[1].default_value = defect_params["focal_strength"]

    base_mask_sum = nodes.new("ShaderNodeMath")
    base_mask_sum.name = f"{prefix}_BASE_MASK_SUM"
    base_mask_sum.location = (930, 120)
    base_mask_sum.operation = "ADD"
    base_mask_sum.use_clamp = True

    broken_base_mask = nodes.new("ShaderNodeMath")
    broken_base_mask.name = f"{prefix}_BROKEN_BASE_MASK"
    broken_base_mask.location = (1425, 35)
    broken_base_mask.operation = "MULTIPLY"
    broken_base_mask.use_clamp = True

    broken_soft_mask = nodes.new("ShaderNodeMath")
    broken_soft_mask.name = f"{prefix}_BROKEN_SOFT_MASK"
    broken_soft_mask.location = (1500, 245)
    broken_soft_mask.operation = "MULTIPLY"
    broken_soft_mask.use_clamp = True

    final_mask_sum = nodes.new("ShaderNodeMath")
    final_mask_sum.name = f"{prefix}_FINAL_MASK_SUM"
    final_mask_sum.location = (1310, 120)
    final_mask_sum.operation = "ADD"
    final_mask_sum.use_clamp = True

    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.name = f"{prefix}_RAMP"
    ramp.location = (1505, 120)
    ramp.color_ramp.interpolation = "B_SPLINE"
    ramp.color_ramp.elements[0].position = defect_params["mask_low"]
    ramp.color_ramp.elements[1].position = defect_params["mask_high"]
    ramp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)

    rgb_to_bw = nodes.new("ShaderNodeRGBToBW")
    rgb_to_bw.name = f"{prefix}_MASK_BW"
    rgb_to_bw.location = (1710, 120)

    streak_ramp = nodes.new("ShaderNodeValToRGB")
    streak_ramp.name = f"{prefix}_STREAK_RAMP"
    streak_ramp.location = (1125, 20)
    streak_ramp.color_ramp.interpolation = "B_SPLINE"
    streak_ramp.color_ramp.elements[0].position = min(0.50, defect_params["mask_low"] + 0.12)
    streak_ramp.color_ramp.elements[1].position = min(0.86, defect_params["mask_high"] + 0.20)
    streak_ramp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    streak_ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)

    streak_bw = nodes.new("ShaderNodeRGBToBW")
    streak_bw.name = f"{prefix}_STREAK_BW"
    streak_bw.location = (1315, 20)

    links.new(tex_coord.outputs["Object"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], separate_xyz.inputs["Vector"])
    links.new(mapping.outputs["Vector"], distortion_noise.inputs["Vector"])
    links.new(mapping.outputs["Vector"], envelope_noise.inputs["Vector"])
    links.new(mapping.outputs["Vector"], width_noise.inputs["Vector"])
    links.new(separate_xyz.outputs["X"], curve_freq.inputs[0])
    links.new(curve_freq.outputs["Value"], curve_phase.inputs[0])
    links.new(curve_phase.outputs["Value"], curve_sine.inputs[0])
    links.new(curve_sine.outputs["Value"], curve_scale.inputs[0])
    links.new(separate_xyz.outputs["Y"], curved_y.inputs[0])
    links.new(curve_scale.outputs["Value"], curved_y.inputs[1])
    links.new(separate_xyz.outputs["X"], abs_x.inputs[0])
    links.new(width_noise.outputs["Fac"], width_noise_center.inputs[0])
    links.new(width_noise_center.outputs["Value"], width_noise_scale.inputs[0])
    links.new(width_noise_scale.outputs["Value"], width_factor.inputs[1])
    links.new(curved_y.outputs["Value"], y_width_modulated.inputs[0])
    links.new(width_factor.outputs["Value"], y_width_modulated.inputs[1])
    links.new(y_width_modulated.outputs["Value"], abs_y.inputs[0])
    links.new(abs_x.outputs["Value"], combine_envelope.inputs["X"])
    links.new(abs_y.outputs["Value"], y_soften.inputs[0])
    links.new(y_soften.outputs["Value"], combine_envelope.inputs["Y"])
    links.new(combine_envelope.outputs["Vector"], envelope_length.inputs[0])
    links.new(envelope_length.outputs["Value"], envelope_map.inputs["Value"])
    links.new(abs_x.outputs["Value"], focal_xy.inputs["X"])
    links.new(abs_y.outputs["Value"], focal_xy.inputs["Y"])
    links.new(focal_xy.outputs["Vector"], focal_length.inputs[0])
    links.new(focal_length.outputs["Value"], focal_map.inputs["Value"])
    links.new(distortion_noise.outputs["Color"], distortion_center.inputs[0])
    links.new(distortion_center.outputs["Vector"], distortion_scale.inputs[0])
    links.new(mapping.outputs["Vector"], distorted_vector.inputs[0])
    links.new(distortion_scale.outputs["Vector"], distorted_vector.inputs[1])
    links.new(distorted_vector.outputs["Vector"], wave.inputs["Vector"])
    links.new(distorted_vector.outputs["Vector"], fine_noise.inputs["Vector"])
    links.new(distorted_vector.outputs["Vector"], focal_noise.inputs["Vector"])
    links.new(distorted_vector.outputs["Vector"], break_noise.inputs["Vector"])
    links.new(wave.outputs["Fac"], directional_ramp.inputs["Fac"])
    links.new(directional_ramp.outputs["Color"], directional_bw.inputs["Color"])
    links.new(envelope_noise.outputs["Fac"], envelope_noise_mix.inputs[0])
    links.new(envelope_noise_mix.outputs["Value"], envelope_noise_add.inputs[1])
    links.new(envelope_map.outputs["Result"], envelope_modulated.inputs[0])
    links.new(envelope_noise_add.outputs["Value"], envelope_modulated.inputs[1])
    links.new(envelope_modulated.outputs["Value"], soft_mask_scale.inputs[0])
    links.new(soft_mask_scale.outputs["Value"], soft_ramp.inputs["Fac"])
    links.new(soft_ramp.outputs["Color"], soft_bw.inputs["Color"])
    links.new(soft_mask_scale.outputs["Value"], halo_ramp.inputs["Fac"])
    links.new(halo_ramp.outputs["Color"], halo_bw.inputs["Color"])
    links.new(directional_bw.outputs["Val"], directional_enveloped.inputs[0])
    links.new(envelope_modulated.outputs["Value"], directional_enveloped.inputs[1])
    links.new(fine_noise.outputs["Fac"], fine_strength.inputs[0])
    links.new(fine_strength.outputs["Value"], fine_enveloped.inputs[0])
    links.new(envelope_modulated.outputs["Value"], fine_enveloped.inputs[1])
    links.new(break_noise.outputs["Fac"], break_ramp.inputs["Fac"])
    links.new(break_ramp.outputs["Color"], break_bw.inputs["Color"])
    links.new(break_bw.outputs["Val"], break_amp.inputs[0])
    links.new(break_amp.outputs["Value"], break_mask.inputs[1])
    links.new(separate_xyz.outputs["X"], segment_freq.inputs[0])
    links.new(segment_freq.outputs["Value"], segment_phase.inputs[0])
    links.new(segment_phase.outputs["Value"], segment_sine.inputs[0])
    links.new(segment_sine.outputs["Value"], segment_abs.inputs[0])
    links.new(segment_abs.outputs["Value"], segment_ramp.inputs["Fac"])
    links.new(segment_ramp.outputs["Color"], segment_bw.inputs["Color"])
    links.new(segment_bw.outputs["Val"], segment_amp.inputs[0])
    links.new(segment_amp.outputs["Value"], segment_mask.inputs[1])
    links.new(break_mask.outputs["Value"], combined_break_mask.inputs[0])
    links.new(segment_mask.outputs["Value"], combined_break_mask.inputs[1])
    links.new(focal_noise.outputs["Fac"], focal_noise_mix.inputs[0])
    links.new(focal_map.outputs["Result"], focal_mask.inputs[0])
    links.new(focal_noise_mix.outputs["Value"], focal_mask.inputs[1])
    links.new(directional_enveloped.outputs["Value"], base_mask_sum.inputs[0])
    links.new(fine_enveloped.outputs["Value"], base_mask_sum.inputs[1])
    links.new(base_mask_sum.outputs["Value"], broken_base_mask.inputs[0])
    links.new(combined_break_mask.outputs["Value"], broken_base_mask.inputs[1])
    links.new(broken_base_mask.outputs["Value"], mask_boost.inputs[0])
    links.new(focal_mask.outputs["Value"], focal_strength.inputs[0])
    links.new(mask_boost.outputs["Value"], final_mask_sum.inputs[0])
    links.new(focal_strength.outputs["Value"], final_mask_sum.inputs[1])
    links.new(broken_base_mask.outputs["Value"], streak_ramp.inputs["Fac"])
    links.new(streak_ramp.outputs["Color"], streak_bw.inputs["Color"])
    links.new(final_mask_sum.outputs["Value"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], rgb_to_bw.inputs["Color"])
    links.new(soft_bw.outputs["Val"], broken_soft_mask.inputs[0])
    links.new(combined_break_mask.outputs["Value"], broken_soft_mask.inputs[1])
    return (
        rgb_to_bw.outputs["Val"],
        ramp.outputs["Color"],
        directional_enveloped.outputs["Value"],
        focal_mask.outputs["Value"],
        broken_soft_mask.outputs["Value"],
        streak_bw.outputs["Val"],
        halo_bw.outputs["Val"],
    )


def apply_mixed_color_to_main_material(
    main_material,
    control_object,
    defect_params,
    debug_mixed_color_strong=False,
    cleanup_existing=True,
    node_prefix="QC75244_MIXED_MAT",
):
    tree = main_material.node_tree
    nodes = tree.nodes
    links = tree.links
    bsdf = find_principled(main_material)
    base_color_node = nodes["QC75244_BASE_COLOR_RGB"]
    base_roughness_mix = nodes["QC75244_BASE_ROUGHNESS_MIX"]
    if cleanup_existing:
        cleanup_mixed_color_material_nodes(main_material)
    base_color_source = (
        bsdf.inputs["Base Color"].links[0].from_socket
        if not cleanup_existing and bsdf.inputs["Base Color"].is_linked
        else base_color_node.outputs["Color"]
    )

    mask_socket, mask_color_socket, directional_socket, focal_socket, soft_mask_socket, streak_mask_socket, halo_mask_socket = build_mixed_color_mask_nodes(
        tree,
        links,
        control_object,
        defect_params,
        node_prefix,
    )

    defect_color = nodes.new("ShaderNodeRGB")
    defect_color.name = "QC75244_MIXED_DEFECT_COLOR"
    defect_color.location = (330, 320)
    tone = defect_params["tone_rgba"]
    noise_strength = defect_params.get("color_noise_strength", 0.01)
    jittered_tone = (
        min(1.0, max(0.0, tone[0] + random.uniform(-noise_strength, noise_strength))),
        min(1.0, max(0.0, tone[1] + random.uniform(-noise_strength * 0.9, noise_strength * 0.8))),
        min(1.0, max(0.0, tone[2] + random.uniform(-noise_strength * 1.2, noise_strength * 0.5))),
        tone[3],
    )

    base_rgb = tuple(float(v) for v in base_color_node.outputs["Color"].default_value[:3])
    soft_delta_modes = [
        # Real QC7-5244 mixed-color references read closer to black/dirty gray
        # material drift than yellow patching. Keep the tone relative to the
        # current white base so it remains internal to the plastic material.
        (
            random.uniform(-0.235, -0.165),
            random.uniform(-0.255, -0.180),
            random.uniform(-0.315, -0.225),
        ),
        (
            random.uniform(-0.300, -0.215),
            random.uniform(-0.295, -0.210),
            random.uniform(-0.315, -0.225),
        ),
        (
            random.uniform(-0.195, -0.135),
            random.uniform(-0.260, -0.185),
            random.uniform(-0.335, -0.245),
        ),
    ]
    raw_soft_delta = random.choice(soft_delta_modes)
    effective_soft_delta = (
        raw_soft_delta[0] + random.uniform(-noise_strength * 0.5, noise_strength * 0.3),
        raw_soft_delta[1] + random.uniform(-noise_strength * 0.5, noise_strength * 0.3),
        raw_soft_delta[2] + random.uniform(-noise_strength * 0.5, noise_strength * 0.3),
    )
    soft_tone_rgb = tuple(
        min(1.0, max(0.0, base_component + delta_component))
        for base_component, delta_component in zip(base_rgb, effective_soft_delta)
    )
    soft_tone = soft_tone_rgb + (1.0,)
    defect_color.outputs["Color"].default_value = soft_tone

    soft_defect_color = nodes.new("ShaderNodeRGB")
    soft_defect_color.name = "QC75244_MIXED_SOFT_DEFECT_COLOR"
    soft_defect_color.location = (330, 195)
    soft_defect_color.outputs["Color"].default_value = soft_tone

    streak_defect_color = nodes.new("ShaderNodeRGB")
    streak_defect_color.name = "QC75244_MIXED_STREAK_DEFECT_COLOR"
    streak_defect_color.location = (330, 445)
    streak_tone = (
        min(1.0, max(0.0, soft_tone_rgb[0] - random.uniform(0.010, 0.026))),
        min(1.0, max(0.0, soft_tone_rgb[1] - random.uniform(0.012, 0.030))),
        min(1.0, max(0.0, soft_tone_rgb[2] - random.uniform(0.018, 0.040))),
        1.0,
    )
    streak_defect_color.outputs["Color"].default_value = streak_tone

    mix_factor = defect_params["mix_factor"]
    applied_roughness_delta = defect_params["roughness_delta"]
    rgb_visibility_boost = defect_params["rgb_visibility_boost"]
    focal_rgb_boost = defect_params["focal_rgb_boost"]
    soft_weight = defect_params.get("soft_color_mask_weight", 0.65)
    streak_weight = defect_params.get("streak_detail_mask_weight", 0.35)
    focal_weight = defect_params.get("focal_mask_weight", 0.15)
    label_rgb_weight = defect_params.get("label_rgb_mask_weight", 0.0)
    halo_weight = defect_params.get("halo_weight", 0.0)
    soft_mix_scale = defect_params.get("soft_mix_strength", 0.65)
    detail_mix_scale = defect_params.get("detail_mix_strength", 0.28)
    halo_mix_scale = defect_params.get("halo_mix_strength", 0.0)
    if debug_mixed_color_strong:
        mix_factor = random.uniform(0.65, 0.80)
        applied_roughness_delta = random.uniform(0.18, 0.30)
        rgb_visibility_boost = random.uniform(2.5, 3.5)
        soft_mix_scale = random.uniform(0.68, 0.82)
        detail_mix_scale = random.uniform(0.24, 0.38)

    soft_mix_strength = nodes.new("ShaderNodeMath")
    soft_mix_strength.name = "QC75244_MIXED_SOFT_MIX_STRENGTH"
    soft_mix_strength.location = (980, 115)
    soft_mix_strength.operation = "MULTIPLY"
    soft_mix_strength.inputs[1].default_value = mix_factor * soft_mix_scale

    detail_mix_strength = nodes.new("ShaderNodeMath")
    detail_mix_strength.name = "QC75244_MIXED_DETAIL_MIX_STRENGTH"
    detail_mix_strength.location = (980, 10)
    detail_mix_strength.operation = "MULTIPLY"
    detail_mix_strength.inputs[1].default_value = mix_factor * detail_mix_scale

    soft_mask_weight = nodes.new("ShaderNodeMath")
    soft_mask_weight.name = "QC75244_MIXED_SOFT_MASK_WEIGHT"
    soft_mask_weight.location = (250, -40)
    soft_mask_weight.operation = "MULTIPLY"
    soft_mask_weight.inputs[1].default_value = soft_weight

    streak_mask_weight = nodes.new("ShaderNodeMath")
    streak_mask_weight.name = "QC75244_MIXED_STREAK_MASK_WEIGHT"
    streak_mask_weight.location = (250, 40)
    streak_mask_weight.operation = "MULTIPLY"
    streak_mask_weight.inputs[1].default_value = streak_weight

    focal_mask_weight = nodes.new("ShaderNodeMath")
    focal_mask_weight.name = "QC75244_MIXED_FOCAL_MASK_WEIGHT"
    focal_mask_weight.location = (250, 120)
    focal_mask_weight.operation = "MULTIPLY"
    focal_mask_weight.inputs[1].default_value = focal_weight * focal_rgb_boost

    label_mask_weight = nodes.new("ShaderNodeMath")
    label_mask_weight.name = "QC75244_MIXED_LABEL_MASK_RGB_WEIGHT"
    label_mask_weight.location = (250, 205)
    label_mask_weight.operation = "MULTIPLY"
    label_mask_weight.inputs[1].default_value = label_rgb_weight

    halo_mask_weight = nodes.new("ShaderNodeMath")
    halo_mask_weight.name = "QC75244_MIXED_HALO_MASK_WEIGHT"
    halo_mask_weight.location = (250, -125)
    halo_mask_weight.operation = "MULTIPLY"
    halo_mask_weight.inputs[1].default_value = halo_weight

    rgb_mask_sum_a = nodes.new("ShaderNodeMath")
    rgb_mask_sum_a.name = "QC75244_MIXED_RGB_MASK_SUM_A"
    rgb_mask_sum_a.location = (455, 0)
    rgb_mask_sum_a.operation = "ADD"
    rgb_mask_sum_a.use_clamp = True

    rgb_mask_sum_b = nodes.new("ShaderNodeMath")
    rgb_mask_sum_b.name = "QC75244_MIXED_RGB_MASK_SUM_B"
    rgb_mask_sum_b.location = (650, 55)
    rgb_mask_sum_b.operation = "ADD"
    rgb_mask_sum_b.use_clamp = True

    rgb_mask_sum_c = nodes.new("ShaderNodeMath")
    rgb_mask_sum_c.name = "QC75244_MIXED_RGB_MASK_SUM_C"
    rgb_mask_sum_c.location = (735, 125)
    rgb_mask_sum_c.operation = "ADD"
    rgb_mask_sum_c.use_clamp = True

    rgb_mask_sum_d = nodes.new("ShaderNodeMath")
    rgb_mask_sum_d.name = "QC75244_MIXED_RGB_MASK_SUM_D"
    rgb_mask_sum_d.location = (555, -55)
    rgb_mask_sum_d.operation = "ADD"
    rgb_mask_sum_d.use_clamp = True

    rgb_mask_boost = nodes.new("ShaderNodeMath")
    rgb_mask_boost.name = "QC75244_MIXED_RGB_MASK_BOOST"
    rgb_mask_boost.location = (820, 55)
    rgb_mask_boost.operation = "MULTIPLY"
    rgb_mask_boost.inputs[1].default_value = rgb_visibility_boost

    final_rgb_mask = nodes.new("ShaderNodeClamp")
    final_rgb_mask.name = "QC75244_MIXED_FINAL_RGB_MASK"
    final_rgb_mask.location = (980, 140)
    final_rgb_mask.inputs["Min"].default_value = 0.0
    final_rgb_mask.inputs["Max"].default_value = 1.0

    soft_color_mix = nodes.new("ShaderNodeMixRGB")
    soft_color_mix.name = "QC75244_MIXED_SOFT_COLOR_MIX"
    soft_color_mix.location = (1180, 230)
    soft_color_mix.blend_type = "MIX"

    halo_mix_strength = nodes.new("ShaderNodeMath")
    halo_mix_strength.name = "QC75244_MIXED_HALO_MIX_STRENGTH"
    halo_mix_strength.location = (980, 335)
    halo_mix_strength.operation = "MULTIPLY"
    halo_mix_strength.inputs[1].default_value = mix_factor * halo_mix_scale

    halo_color_mix = nodes.new("ShaderNodeMixRGB")
    halo_color_mix.name = "QC75244_MIXED_HALO_COLOR_MIX"
    halo_color_mix.location = (1280, 260)
    halo_color_mix.blend_type = "MIX"

    detail_mask_sum = nodes.new("ShaderNodeMath")
    detail_mask_sum.name = "QC75244_MIXED_DETAIL_MASK_SUM"
    detail_mask_sum.location = (650, 145)
    detail_mask_sum.operation = "ADD"
    detail_mask_sum.use_clamp = True

    detail_mask_boost = nodes.new("ShaderNodeMath")
    detail_mask_boost.name = "QC75244_MIXED_DETAIL_MASK_BOOST"
    detail_mask_boost.location = (820, 145)
    detail_mask_boost.operation = "MULTIPLY"
    detail_mask_boost.inputs[1].default_value = 1.0

    detail_rgb_mask = nodes.new("ShaderNodeClamp")
    detail_rgb_mask.name = "QC75244_MIXED_DETAIL_RGB_MASK"
    detail_rgb_mask.location = (980, 220)
    detail_rgb_mask.inputs["Min"].default_value = 0.0
    detail_rgb_mask.inputs["Max"].default_value = 1.0

    detail_color_mix = nodes.new("ShaderNodeMixRGB")
    detail_color_mix.name = "QC75244_MIXED_DETAIL_COLOR_MIX"
    detail_color_mix.location = (1385, 125)
    detail_color_mix.blend_type = "MIX"

    base_rough_bw = nodes.new("ShaderNodeRGBToBW")
    base_rough_bw.name = "QC75244_MIXED_BASE_ROUGH_BW"
    base_rough_bw.location = (340, -130)

    directional_strength = nodes.new("ShaderNodeMath")
    directional_strength.name = "QC75244_MIXED_DIRECTIONAL_STRENGTH"
    directional_strength.location = (340, -235)
    directional_strength.operation = "MULTIPLY"
    directional_strength.inputs[1].default_value = defect_params["directional_strength"]

    mask_strength = nodes.new("ShaderNodeMath")
    mask_strength.name = "QC75244_MIXED_MASK_STRENGTH"
    mask_strength.location = (340, -315)
    mask_strength.operation = "MULTIPLY"
    mask_strength.inputs[1].default_value = 0.35

    rough_variation = nodes.new("ShaderNodeMath")
    rough_variation.name = "QC75244_MIXED_ROUGH_VARIATION"
    rough_variation.location = (550, -245)
    rough_variation.operation = "ADD"
    rough_variation.use_clamp = True

    rough_boost = nodes.new("ShaderNodeMath")
    rough_boost.name = "QC75244_MIXED_ROUGH_BOOST"
    rough_boost.location = (755, -180)
    rough_boost.operation = "MULTIPLY"
    rough_boost.inputs[1].default_value = applied_roughness_delta

    rough_add = nodes.new("ShaderNodeMath")
    rough_add.name = "QC75244_MIXED_ROUGH_ADD"
    rough_add.location = (955, -115)
    rough_add.operation = "ADD"
    rough_add.use_clamp = True

    links.new(soft_mask_socket, soft_mask_weight.inputs[0])
    links.new(streak_mask_socket, streak_mask_weight.inputs[0])
    links.new(focal_socket, focal_mask_weight.inputs[0])
    links.new(halo_mask_socket, halo_mask_weight.inputs[0])
    links.new(soft_mask_weight.outputs["Value"], rgb_mask_sum_a.inputs[0])
    links.new(streak_mask_weight.outputs["Value"], rgb_mask_sum_a.inputs[1])
    links.new(rgb_mask_sum_a.outputs["Value"], rgb_mask_sum_d.inputs[0])
    links.new(halo_mask_weight.outputs["Value"], rgb_mask_sum_d.inputs[1])
    links.new(rgb_mask_sum_d.outputs["Value"], rgb_mask_sum_b.inputs[0])
    links.new(focal_mask_weight.outputs["Value"], rgb_mask_sum_b.inputs[1])
    links.new(mask_socket, label_mask_weight.inputs[0])
    links.new(rgb_mask_sum_b.outputs["Value"], rgb_mask_sum_c.inputs[0])
    links.new(label_mask_weight.outputs["Value"], rgb_mask_sum_c.inputs[1])
    links.new(rgb_mask_sum_c.outputs["Value"], rgb_mask_boost.inputs[0])
    links.new(rgb_mask_boost.outputs["Value"], final_rgb_mask.inputs["Value"])
    links.new(final_rgb_mask.outputs["Result"], soft_mix_strength.inputs[0])
    links.new(base_color_source, soft_color_mix.inputs[1])
    links.new(soft_defect_color.outputs["Color"], soft_color_mix.inputs[2])
    links.new(soft_mix_strength.outputs["Value"], soft_color_mix.inputs["Fac"])
    links.new(halo_mask_socket, halo_mix_strength.inputs[0])
    links.new(soft_color_mix.outputs["Color"], halo_color_mix.inputs[1])
    links.new(soft_defect_color.outputs["Color"], halo_color_mix.inputs[2])
    links.new(halo_mix_strength.outputs["Value"], halo_color_mix.inputs["Fac"])

    links.new(streak_mask_weight.outputs["Value"], detail_mask_sum.inputs[0])
    links.new(focal_mask_weight.outputs["Value"], detail_mask_sum.inputs[1])
    links.new(detail_mask_sum.outputs["Value"], detail_mask_boost.inputs[0])
    links.new(detail_mask_boost.outputs["Value"], detail_rgb_mask.inputs["Value"])
    links.new(detail_rgb_mask.outputs["Result"], detail_mix_strength.inputs[0])
    links.new(halo_color_mix.outputs["Color"], detail_color_mix.inputs[1])
    links.new(streak_defect_color.outputs["Color"], detail_color_mix.inputs[2])
    links.new(detail_mix_strength.outputs["Value"], detail_color_mix.inputs["Fac"])
    links.new(detail_color_mix.outputs["Color"], bsdf.inputs["Base Color"])

    links.new(base_roughness_mix.outputs["Color"], base_rough_bw.inputs["Color"])
    links.new(directional_socket, directional_strength.inputs[0])
    links.new(mask_socket, mask_strength.inputs[0])
    links.new(directional_strength.outputs["Value"], rough_variation.inputs[0])
    links.new(mask_strength.outputs["Value"], rough_variation.inputs[1])
    links.new(rough_variation.outputs["Value"], rough_boost.inputs[0])
    links.new(base_rough_bw.outputs["Val"], rough_add.inputs[0])
    links.new(rough_boost.outputs["Value"], rough_add.inputs[1])
    links.new(rough_add.outputs["Value"], bsdf.inputs["Roughness"])

    return {
        "mask_socket_name": mask_socket.name,
        "mask_color_socket_name": mask_color_socket.name,
        "tone_rgba_jittered": jittered_tone,
        "mix_factor_applied": mix_factor,
        "rgb_visibility_boost": rgb_visibility_boost,
        "effective_rgb_mix_factor": round(mix_factor * rgb_visibility_boost, 6),
        "roughness_delta_applied": applied_roughness_delta,
        "debug_mixed_color_strong": bool(debug_mixed_color_strong),
        "soft_color_mask_weight": soft_weight,
        "streak_detail_mask_weight": streak_weight,
        "focal_rgb_boost": focal_rgb_boost,
        "label_rgb_mask_weight": label_rgb_weight,
        "halo_weight": halo_weight,
        "soft_mix_strength": soft_mix_scale,
        "detail_mix_strength": detail_mix_scale,
        "halo_mix_strength": halo_mix_scale,
        "soft_tone_rgba": [round(v, 6) for v in soft_tone],
        "streak_tone_rgba": [round(v, 6) for v in streak_tone],
        "effective_color_delta": [
            round(
                max(
                    abs(float(base) - float(soft_component)),
                    abs(float(base) - float(streak_component)),
                )
                * mix_factor
                * min(
                    1.0,
                    soft_weight * soft_mix_scale
                    + streak_weight * detail_mix_scale
                    + halo_weight * halo_mix_scale
                    + focal_weight * 0.35
                    + label_rgb_weight * 0.65,
                ),
                6,
            )
            for base, soft_component, streak_component in zip(
                base_color_node.outputs["Color"].default_value[:3],
                soft_tone[:3],
                streak_tone[:3],
            )
        ],
        "raw_soft_delta": [round(v, 6) for v in raw_soft_delta],
        "effective_soft_delta": [round(v, 6) for v in effective_soft_delta],
        "final_rgb_mask_estimated_strength": round(
            min(1.0, soft_weight * 0.75 + streak_weight * 0.25 + halo_weight + focal_weight * 0.15 + label_rgb_weight * 0.65),
            6,
        ),
    }


def make_mixed_color_mask_material(control_object, defect_params, name="REFERENCE_MIXED_COLOR_MASK_MAT"):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    tree = mat.node_tree
    nodes = tree.nodes
    links = tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (380, 0)
    emission = nodes.new("ShaderNodeEmission")
    emission.location = (160, 0)
    emission.inputs["Strength"].default_value = 1.0

    _, mask_color_socket, _, _, _, _, _ = build_mixed_color_mask_nodes(
        tree,
        links,
        control_object,
        defect_params["material_mask_params"],
        "QC75244_MIXED_MASK",
    )
    links.new(mask_color_socket, emission.inputs["Color"])
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return mat


def make_black_mask_material(name="REFERENCE_MIXED_COLOR_BLACK_MASK_MAT"):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    tree = mat.node_tree
    nodes = tree.nodes
    links = tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (260, 0)
    emission = nodes.new("ShaderNodeEmission")
    emission.location = (40, 0)
    emission.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    emission.inputs["Strength"].default_value = 1.0
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return mat


def add_mixed_color_contamination(
    primary_obj,
    material_info,
    max_dim,
    camera=None,
    allowed_sides=None,
    debug_mixed_color_strong=False,
    debug_center_mixed_color=False,
    cleanup_material_nodes=True,
    material_node_prefix="QC75244_MIXED_MAT",
):
    candidate_polygons = material_info.get("mixed_color_candidate_polygons", [])
    if not candidate_polygons:
        raise RuntimeError("No candidate polygons found for mixed_color_contamination placement.")
    allowed_sides = set(allowed_sides or ["front"])

    mesh = primary_obj.data
    bb_min = Vector((min(v[0] for v in primary_obj.bound_box), min(v[1] for v in primary_obj.bound_box), min(v[2] for v in primary_obj.bound_box)))
    bb_max = Vector((max(v[0] for v in primary_obj.bound_box), max(v[1] for v in primary_obj.bound_box), max(v[2] for v in primary_obj.bound_box)))
    span = bb_max - bb_min

    scored_candidates = []
    fallback_candidates = []
    side_filtered_candidates = []
    profile_name, model_profile = get_mixed_color_model_profile(primary_obj)
    placement_zone, target_x, target_y, target_window = choose_profile_placement(
        model_profile,
        debug_center_mixed_color=debug_center_mixed_color,
    )
    artifact_window = model_profile.get("artifact_window")
    fallback_window = model_profile.get("fallback_window")
    placement_offsets = model_profile.get("placement_offsets", {})
    use_projected_scoring = bool(model_profile.get("use_projected_scoring", True))
    apply_camera_plane_offsets = bool(model_profile.get("apply_camera_plane_offsets", False))
    normal_matrix = primary_obj.matrix_world.to_3x3()
    for idx in candidate_polygons:
        candidate_poly = mesh.polygons[idx]
        candidate_world_normal = (normal_matrix @ candidate_poly.normal.normalized()).normalized()
        candidate_side = (
            "front"
            if candidate_world_normal.z >= 0.34
            else ("back" if candidate_world_normal.z <= -0.34 else None)
        )
        if candidate_side not in allowed_sides:
            continue
        side_filtered_candidates.append(idx)
        center = candidate_poly.center
        x_ratio = (center.x - bb_min.x) / max(float(span.x), 1e-6)
        y_ratio = (center.y - bb_min.y) / max(float(span.y), 1e-6)
        score_x = x_ratio
        score_y = y_ratio
        if camera is not None and use_projected_scoring:
            projected = world_to_camera_view(
                bpy.context.scene,
                camera,
                primary_obj.matrix_world @ center,
            )
            score_x = float(projected.x)
            score_y = float(projected.y)

        is_artifact_band = (
            artifact_window is not None
            and artifact_window[0] <= score_x <= artifact_window[1]
            and artifact_window[2] <= score_y <= artifact_window[3]
        )
        if is_artifact_band:
            continue
        if fallback_window is None or (
            fallback_window[0] <= score_x <= fallback_window[1]
            and fallback_window[2] <= score_y <= fallback_window[3]
        ):
            fallback_candidates.append(idx)
        if target_window[0] <= score_x <= target_window[1] and target_window[2] <= score_y <= target_window[3]:
            score = ((score_x - target_x) ** 2) + ((score_y - target_y) ** 2)
            scored_candidates.append((score, idx))

    if scored_candidates:
        scored_candidates.sort(key=lambda item: item[0])
        shortlist = [idx for _, idx in scored_candidates[: min(len(scored_candidates), 18)]]
        poly_index = random.choice(shortlist)
        anchor_band = "targeted_main_plane_band"
    else:
        placement_candidates = fallback_candidates or side_filtered_candidates
        if not placement_candidates:
            raise RuntimeError(
                f"No mixed_color_contamination placement candidates found for anchor_sides={sorted(allowed_sides)}."
            )
        poly_index = random.choice(placement_candidates)
        anchor_band = "fallback_main_plane_band"
        placement_zone = placement_zone or "fallback_main_plane"
    poly = mesh.polygons[poly_index]
    local_center = poly.center.copy()
    local_normal = poly.normal.normalized()

    world_point = primary_obj.matrix_world @ local_center
    world_normal = (normal_matrix @ local_normal).normalized()
    anchor_side = "front" if world_normal.z >= 0.34 else ("back" if world_normal.z <= -0.34 else "unknown")
    tangent = None
    bitangent = None

    if apply_camera_plane_offsets and camera is not None:
        camera_quat = camera.matrix_world.to_quaternion()
        tangent = (camera_quat @ Vector((1.0, 0.0, 0.0))) - world_normal * (camera_quat @ Vector((1.0, 0.0, 0.0))).dot(world_normal)
        bitangent = (camera_quat @ Vector((0.0, 1.0, 0.0))) - world_normal * (camera_quat @ Vector((0.0, 1.0, 0.0))).dot(world_normal)
        if tangent.length < 1e-6:
            tangent = world_normal.orthogonal()
        if bitangent.length < 1e-6:
            bitangent = world_normal.cross(tangent)
        tangent.normalize()
        bitangent.normalize()
        offset_u, offset_v = placement_offsets.get(placement_zone, (0.0, 0.0))
        world_point = world_point + tangent * (offset_u * max_dim) + bitangent * (offset_v * max_dim)

    radius_x_min, radius_x_max = model_profile.get("radius_x_factor", (0.045, 0.085))
    radius_y_min, radius_y_max = model_profile.get("radius_y_factor", (0.008, 0.018))
    radius_x = random.uniform(max_dim * radius_x_min, max_dim * radius_x_max)
    radius_y = random.uniform(max_dim * radius_y_min, max_dim * radius_y_max)
    if tangent is None or bitangent is None:
        tangent = world_normal.orthogonal().normalized()
        bitangent = world_normal.cross(tangent).normalized()

    defect_params = mixed_color_reference_materials()
    control = create_mixed_color_control_object(
        world_point,
        tangent,
        bitangent,
        world_normal,
        radius_x,
        radius_y,
        name=f"QC75244_MIXED_COLOR_CTRL_{random.randint(0, 999999)}",
    )
    main_material = bpy.data.materials[material_info["main_plane_material"]]
    applied_params = apply_mixed_color_to_main_material(
        main_material,
        control,
        defect_params,
        debug_mixed_color_strong=debug_mixed_color_strong,
        cleanup_existing=cleanup_material_nodes,
        node_prefix=material_node_prefix,
    )
    mixed_material_targets = [main_material.name]
    edge_material_name = material_info.get("edge_wall_material")
    if edge_material_name and edge_material_name in bpy.data.materials:
        # The QC7-5236 front-facing placement footprint can straddle the ultra-light
        # two-zone material boundary. Apply the same material-driven defect mask to
        # the edge/wall material too, so RGB visibility matches the exported mask.
        edge_material = bpy.data.materials[edge_material_name]
        apply_mixed_color_to_main_material(
            edge_material,
            control,
            defect_params,
            debug_mixed_color_strong=debug_mixed_color_strong,
            cleanup_existing=cleanup_material_nodes,
            node_prefix=material_node_prefix + "_EDGE",
        )
        mixed_material_targets.append(edge_material.name)
    control["defect_class"] = "mixed_color_contamination"
    control["appearance_mode"] = "white_low_contrast"
    control["shape_mode"] = "directional_streak_material_drift"

    local_x = (local_center.x - bb_min.x) / max(float(span.x), 1e-6)
    local_y = (local_center.y - bb_min.y) / max(float(span.y), 1e-6)
    projected_xy = None
    visible_after_follow = None
    if camera is not None:
        projected = world_to_camera_view(bpy.context.scene, camera, world_point)
        projected_xy = [round(float(projected.x), 4), round(float(projected.y), 4)]
        visible_after_follow = bool(projected.z > 0.0 and 0.08 <= projected.x <= 0.92 and 0.08 <= projected.y <= 0.92)

    return {
        "defect_type": "mixed_color_contamination",
        "appearance_mode": "white_low_contrast",
        "shape_mode": "directional_streak_material_drift",
        "mask_mode": "directional_streak_material_drift",
        "model_profile": profile_name,
        "control_object": control.name,
        "mixed_material_targets": mixed_material_targets,
        "anchor_polygon_index": poly_index,
        "anchor_band": anchor_band,
        "anchor_side": anchor_side,
        "allowed_anchor_sides": sorted(allowed_sides),
        "placement_zone": placement_zone,
        "local_xy": [round(local_x, 4), round(local_y, 4)],
        "projected_xy": projected_xy,
        "world_point": [round(world_point.x, 5), round(world_point.y, 5), round(world_point.z, 5)],
        "world_normal": [round(world_normal.x, 5), round(world_normal.y, 5), round(world_normal.z, 5)],
        "camera_follow": {
            "anchor_side": anchor_side,
            "projected_xy_after_follow": projected_xy,
            "visible_after_follow": visible_after_follow,
        },
        "flow_direction_angle": round(defect_params["flow_direction_angle"], 4),
        "radius_x": round(radius_x, 5),
        "radius_y": round(radius_y, 5),
        "aspect_ratio": round(radius_x / max(radius_y, 1e-6), 4),
        "tone_rgba": [round(v, 4) for v in defect_params["tone_rgba"]],
        "tone_rgba_jittered": [round(v, 4) for v in applied_params["tone_rgba_jittered"]],
        "final_tone_rgba": [round(v, 4) for v in applied_params["soft_tone_rgba"]],
        "streak_tone_rgba": [round(v, 4) for v in applied_params["streak_tone_rgba"]],
        "mix_factor": round(applied_params["mix_factor_applied"], 4),
        "rgb_visibility_boost": round(applied_params["rgb_visibility_boost"], 4),
        "effective_rgb_mix_factor": round(applied_params["effective_rgb_mix_factor"], 4),
        "roughness_delta": round(applied_params["roughness_delta_applied"], 4),
        "debug_mixed_color_strong": bool(applied_params["debug_mixed_color_strong"]),
        "debug_center_mixed_color": bool(debug_center_mixed_color),
        "mask_low": round(defect_params["mask_low"], 4),
        "mask_high": round(defect_params["mask_high"], 4),
        "label_threshold": round(defect_params["label_threshold"], 4),
        "final_rgb_mask_estimated_strength": applied_params["final_rgb_mask_estimated_strength"],
        "soft_color_mask_weight": round(applied_params["soft_color_mask_weight"], 4),
        "streak_detail_mask_weight": round(applied_params["streak_detail_mask_weight"], 4),
        "focal_rgb_boost": round(applied_params["focal_rgb_boost"], 4),
        "raw_soft_delta": [round(v, 6) for v in applied_params["raw_soft_delta"]],
        "effective_soft_delta": [round(v, 6) for v in applied_params["effective_soft_delta"]],
        "effective_color_delta": applied_params["effective_color_delta"],
        "material_mask_params": {
            key: (
                [round(v, 4) for v in value]
                if isinstance(value, tuple)
                else (round(value, 4) if isinstance(value, (int, float)) else value)
            )
            for key, value in defect_params.items()
        },
    }


def add_same_type_mixed_color_contaminations(
    primary_obj,
    material_info,
    max_dim,
    camera=None,
    allowed_sides=None,
    debug_mixed_color_strong=False,
    debug_center_mixed_color=False,
    max_count=1,
):
    defect_count = random.randint(1, max(1, int(max_count)))
    defects = []
    for instance_index in range(defect_count):
        defect = add_mixed_color_contamination(
            primary_obj,
            material_info,
            max_dim,
            camera=camera,
            allowed_sides=allowed_sides,
            debug_mixed_color_strong=debug_mixed_color_strong,
            debug_center_mixed_color=debug_center_mixed_color,
            cleanup_material_nodes=(instance_index == 0),
            material_node_prefix=f"QC75244_MIXED_MAT_{instance_index:02d}",
        )
        defect["instance_index"] = instance_index
        defects.append(defect)
    points = [Vector(item["world_point"]) for item in defects if item.get("world_point")]
    center = sum(points, Vector((0.0, 0.0, 0.0))) / max(1, len(points)) if points else None
    return {
        "defect_type": "mixed_color_contamination",
        "defect_type_internal": "mixed_color_contamination",
        "defect_type_canonical": "mixed_color_contamination",
        "appearance_mode": "white_low_contrast",
        "shape_mode": "directional_streak_material_drift",
        "mask_mode": "directional_streak_material_drift",
        "defect_types": ["mixed_color_contamination" for _ in defects],
        "defect_count": len(defects),
        "defect_count_max": int(max_count),
        "defects": defects,
        "anchor_side": defects[0].get("anchor_side", "front") if defects else "front",
        "world_point": [round(center.x, 5), round(center.y, 5), round(center.z, 5)] if center else None,
        "generation_mode": "same_type_multi_defect",
    }


def apply_validation_jitter(camera):
    camera.location.x += random.uniform(-0.015, 0.015)
    camera.location.y += random.uniform(-0.010, 0.010)
    camera.location.z += random.uniform(-0.010, 0.010)
    camera.rotation_euler.rotate_axis("Z", math.radians(random.uniform(-1.0, 1.0)))
    key = bpy.data.objects.get("Area.003")
    if key is not None and key.type == "LIGHT":
        key.data.energy *= random.uniform(0.97, 1.03)


def render_rgb(output_path):
    scene = bpy.context.scene
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.filepath = str(output_path)
    bpy.ops.render.render(write_still=True)


def bbox_to_yolo(scene, bbox):
    width = float(scene.render.resolution_x)
    height = float(scene.render.resolution_y)
    x, y, bw_px, bh_px = bbox["xywh"]
    xc = (x + bw_px * 0.5) / width
    yc = (y + bh_px * 0.5) / height
    bw = bw_px / width
    bh = bh_px / height
    return xc, yc, bw, bh


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
        overlay_pixels[base] = min(1.0, overlay_pixels[base] * 0.38 + 0.62)
        overlay_pixels[base + 1] = overlay_pixels[base + 1] * 0.42
        overlay_pixels[base + 2] = overlay_pixels[base + 2] * 0.42

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


def find_background_node(world):
    if world is None or not world.use_nodes or world.node_tree is None:
        return None
    for node in world.node_tree.nodes:
        if node.type == "BACKGROUND":
            return node
    return None


def render_mixed_color_binary_mask(mask_path, primary_obj, material_info, defect_info):
    scene = bpy.context.scene
    control = bpy.data.objects.get(defect_info["control_object"])
    if control is None:
        raise RuntimeError(f"Mixed-color control object not found for mask render: {defect_info['control_object']}")

    original_engine = scene.render.engine
    original_samples = int(getattr(scene.cycles, "samples", 1))
    original_adaptive = bool(getattr(scene.cycles, "use_adaptive_sampling", False))
    original_filepath = scene.render.filepath
    original_hide_render = {obj.name: bool(obj.hide_render) for obj in bpy.data.objects}
    original_materials = [mat for mat in primary_obj.data.materials]
    world = scene.world
    background = find_background_node(world)
    original_bg_color = None
    original_bg_strength = None
    if background is not None:
        original_bg_color = tuple(background.inputs["Color"].default_value)
        original_bg_strength = float(background.inputs["Strength"].default_value)

    mask_mat = make_mixed_color_mask_material(control, defect_info)
    black_mask_mat = make_black_mask_material()

    try:
        for obj in bpy.data.objects:
            if obj.type == "MESH":
                obj.hide_render = obj.name != primary_obj.name
        primary_obj.hide_render = False
        primary_obj.data.materials.clear()
        primary_obj.data.materials.append(mask_mat)
        primary_obj.data.materials.append(black_mask_mat)
        if background is not None:
            background.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
            background.inputs["Strength"].default_value = 1.0
        scene.render.engine = "CYCLES"
        scene.cycles.samples = 1
        scene.cycles.use_adaptive_sampling = False
        render_rgb(mask_path)
    finally:
        scene.render.engine = original_engine
        scene.cycles.samples = original_samples
        scene.cycles.use_adaptive_sampling = original_adaptive
        scene.render.filepath = original_filepath
        if background is not None and original_bg_color is not None and original_bg_strength is not None:
            background.inputs["Color"].default_value = original_bg_color
            background.inputs["Strength"].default_value = original_bg_strength
        primary_obj.data.materials.clear()
        for mat in original_materials:
            primary_obj.data.materials.append(mat)
        for obj in bpy.data.objects:
            if obj.name in original_hide_render:
                obj.hide_render = original_hide_render[obj.name]


def make_mixed_color_debug_pass_material(control_object, defect_info, pass_mode, name):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    tree = mat.node_tree
    nodes = tree.nodes
    links = tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (620, 0)
    emission = nodes.new("ShaderNodeEmission")
    emission.location = (400, 0)
    emission.inputs["Strength"].default_value = 1.0

    defect_params = defect_info["material_mask_params"]
    mask_socket, mask_color_socket, _, focal_socket, soft_mask_socket, streak_mask_socket, halo_mask_socket = build_mixed_color_mask_nodes(
        tree,
        links,
        control_object,
        defect_params,
        "QC75244_MIXED_DEBUG",
    )
    base_color = nodes.new("ShaderNodeRGB")
    base_color.location = (40, -160)
    base_color.outputs["Color"].default_value = (0.700, 0.706, 0.714, 1.0)

    defect_color = nodes.new("ShaderNodeRGB")
    defect_color.location = (40, 210)
    defect_color.outputs["Color"].default_value = tuple(defect_info["final_tone_rgba"])
    soft_defect_color = nodes.new("ShaderNodeRGB")
    soft_defect_color.location = (40, 100)
    tone = defect_info["final_tone_rgba"]
    soft_defect_color.outputs["Color"].default_value = (
        min(1.0, max(0.0, tone[0] * 1.01)),
        min(1.0, max(0.0, tone[1] * 1.01)),
        min(1.0, max(0.0, tone[2] * 0.98)),
        1.0,
    )
    streak_defect_color = nodes.new("ShaderNodeRGB")
    streak_defect_color.location = (40, 320)
    streak_defect_color.outputs["Color"].default_value = (
        min(1.0, max(0.0, tone[0] - 0.010)),
        min(1.0, max(0.0, tone[1] - 0.004)),
        min(1.0, max(0.0, tone[2] - 0.014)),
        1.0,
    )

    if pass_mode in {"rgb_mask_debug", "soft_color_mask_debug", "streak_mask_debug", "final_rgb_mask_debug"}:
        soft_weight = defect_info.get("soft_color_mask_weight", 0.65)
        streak_weight = defect_info.get("streak_detail_mask_weight", 0.35)
        focal_weight = defect_info.get("focal_rgb_boost", 0.15)
        halo_weight = defect_info.get("halo_weight", 0.0)
        rgb_visibility_boost = defect_info.get("rgb_visibility_boost", 1.0)

        soft_mul = nodes.new("ShaderNodeMath")
        soft_mul.location = (25, -40)
        soft_mul.operation = "MULTIPLY"
        soft_mul.inputs[1].default_value = soft_weight
        streak_mul = nodes.new("ShaderNodeMath")
        streak_mul.location = (25, 30)
        streak_mul.operation = "MULTIPLY"
        streak_mul.inputs[1].default_value = streak_weight
        focal_mul = nodes.new("ShaderNodeMath")
        focal_mul.location = (25, 100)
        focal_mul.operation = "MULTIPLY"
        focal_mul.inputs[1].default_value = focal_weight
        halo_mul = nodes.new("ShaderNodeMath")
        halo_mul.location = (25, -110)
        halo_mul.operation = "MULTIPLY"
        halo_mul.inputs[1].default_value = halo_weight
        sum_a = nodes.new("ShaderNodeMath")
        sum_a.location = (215, 0)
        sum_a.operation = "ADD"
        sum_a.use_clamp = True
        sum_b = nodes.new("ShaderNodeMath")
        sum_b.location = (405, 70)
        sum_b.operation = "ADD"
        sum_b.use_clamp = True
        boost = nodes.new("ShaderNodeMath")
        boost.location = (405, -35)
        boost.operation = "MULTIPLY"
        boost.inputs[1].default_value = rgb_visibility_boost
        clamp = nodes.new("ShaderNodeClamp")
        clamp.location = (595, 70)
        clamp.inputs["Min"].default_value = 0.0
        clamp.inputs["Max"].default_value = 1.0
        bw_to_rgb = nodes.new("ShaderNodeCombineRGB")
        bw_to_rgb.location = (780, 70)

        links.new(soft_mask_socket, soft_mul.inputs[0])
        links.new(streak_mask_socket, streak_mul.inputs[0])
        links.new(focal_socket, focal_mul.inputs[0])
        links.new(halo_mask_socket, halo_mul.inputs[0])
        links.new(soft_mul.outputs["Value"], sum_a.inputs[0])
        links.new(streak_mul.outputs["Value"], sum_a.inputs[1])
        links.new(sum_a.outputs["Value"], sum_b.inputs[0])
        links.new(halo_mul.outputs["Value"], sum_b.inputs[1])
        links.new(sum_b.outputs["Value"], boost.inputs[0])
        links.new(boost.outputs["Value"], clamp.inputs["Value"])
        if focal_weight > 0:
            # Keep the debug pass focused on the low-frequency halo/line shape;
            # focal contribution is visible in final RGB via the regular render.
            pass
        source_socket = clamp.outputs["Result"]
        if pass_mode == "soft_color_mask_debug":
            source_socket = soft_mul.outputs["Value"]
        elif pass_mode == "streak_mask_debug":
            source_socket = streak_mul.outputs["Value"]
        elif pass_mode == "final_rgb_mask_debug":
            source_socket = clamp.outputs["Result"]
        links.new(source_socket, bw_to_rgb.inputs["R"])
        links.new(source_socket, bw_to_rgb.inputs["G"])
        links.new(source_socket, bw_to_rgb.inputs["B"])
        links.new(bw_to_rgb.outputs["Image"], emission.inputs["Color"])
    else:
        soft_mul = nodes.new("ShaderNodeMath")
        soft_mul.location = (-155, -60)
        soft_mul.operation = "MULTIPLY"
        soft_mul.inputs[1].default_value = defect_info.get("soft_color_mask_weight", 0.65)
        streak_mul = nodes.new("ShaderNodeMath")
        streak_mul.location = (-155, 10)
        streak_mul.operation = "MULTIPLY"
        streak_mul.inputs[1].default_value = defect_info.get("streak_detail_mask_weight", 0.35)
        focal_mul = nodes.new("ShaderNodeMath")
        focal_mul.location = (-155, 80)
        focal_mul.operation = "MULTIPLY"
        focal_mul.inputs[1].default_value = defect_info.get("focal_rgb_boost", 0.15)
        sum_a = nodes.new("ShaderNodeMath")
        sum_a.location = (-5, -10)
        sum_a.operation = "ADD"
        sum_a.use_clamp = True
        sum_b = nodes.new("ShaderNodeMath")
        sum_b.location = (140, 55)
        sum_b.operation = "ADD"
        sum_b.use_clamp = True
        boost = nodes.new("ShaderNodeMath")
        boost.location = (140, -40)
        boost.operation = "MULTIPLY"
        boost.inputs[1].default_value = defect_info.get("rgb_visibility_boost", 1.0)
        clamp = nodes.new("ShaderNodeClamp")
        clamp.location = (315, 55)
        clamp.inputs["Min"].default_value = 0.0
        clamp.inputs["Max"].default_value = 1.0

        soft_mix = nodes.new("ShaderNodeMixRGB")
        soft_mix.location = (520, 60)
        soft_mix.blend_type = "MIX"
        soft_mix_mul = nodes.new("ShaderNodeMath")
        soft_mix_mul.location = (500, -40)
        soft_mix_mul.operation = "MULTIPLY"
        soft_mix_mul.inputs[1].default_value = defect_info.get("mix_factor", 0.5) * defect_info.get("soft_mix_strength", 0.65)

        detail_sum = nodes.new("ShaderNodeMath")
        detail_sum.location = (520, 170)
        detail_sum.operation = "ADD"
        detail_sum.use_clamp = True
        detail_boost = nodes.new("ShaderNodeMath")
        detail_boost.location = (690, 170)
        detail_boost.operation = "MULTIPLY"
        detail_boost.inputs[1].default_value = 1.0
        detail_clamp = nodes.new("ShaderNodeClamp")
        detail_clamp.location = (860, 170)
        detail_clamp.inputs["Min"].default_value = 0.0
        detail_clamp.inputs["Max"].default_value = 1.0
        detail_mix_mul = nodes.new("ShaderNodeMath")
        detail_mix_mul.location = (860, 55)
        detail_mix_mul.operation = "MULTIPLY"
        detail_mix_mul.inputs[1].default_value = defect_info.get("mix_factor", 0.5) * defect_info.get("detail_mix_strength", 0.28)
        detail_mix = nodes.new("ShaderNodeMixRGB")
        detail_mix.location = (1060, 60)
        detail_mix.blend_type = "MIX"

        links.new(soft_mask_socket, soft_mul.inputs[0])
        links.new(streak_mask_socket, streak_mul.inputs[0])
        links.new(focal_socket, focal_mul.inputs[0])
        links.new(soft_mul.outputs["Value"], sum_a.inputs[0])
        links.new(streak_mul.outputs["Value"], sum_a.inputs[1])
        links.new(sum_a.outputs["Value"], sum_b.inputs[0])
        links.new(focal_mul.outputs["Value"], sum_b.inputs[1])
        links.new(sum_b.outputs["Value"], boost.inputs[0])
        links.new(boost.outputs["Value"], clamp.inputs["Value"])
        links.new(clamp.outputs["Result"], soft_mix_mul.inputs[0])
        links.new(base_color.outputs["Color"], soft_mix.inputs[1])
        links.new(soft_defect_color.outputs["Color"], soft_mix.inputs[2])
        links.new(soft_mix_mul.outputs["Value"], soft_mix.inputs["Fac"])
        links.new(streak_mul.outputs["Value"], detail_sum.inputs[0])
        links.new(focal_mul.outputs["Value"], detail_sum.inputs[1])
        links.new(detail_sum.outputs["Value"], detail_boost.inputs[0])
        links.new(detail_boost.outputs["Value"], detail_clamp.inputs["Value"])
        links.new(detail_clamp.outputs["Result"], detail_mix_mul.inputs[0])
        links.new(soft_mix.outputs["Color"], detail_mix.inputs[1])
        links.new(streak_defect_color.outputs["Color"], detail_mix.inputs[2])
        links.new(detail_mix_mul.outputs["Value"], detail_mix.inputs["Fac"])

        if pass_mode == "base_color_before":
            links.new(base_color.outputs["Color"], emission.inputs["Color"])
        elif pass_mode == "base_color_after":
            links.new(detail_mix.outputs["Color"], emission.inputs["Color"])
        else:
            delta = nodes.new("ShaderNodeMixRGB")
            delta.location = (410, -110)
            delta.blend_type = "DIFFERENCE"
            delta.inputs["Fac"].default_value = 1.0
            brighten = nodes.new("ShaderNodeBrightContrast")
            brighten.location = (605, -110)
            brighten.inputs["Bright"].default_value = 0.0
            brighten.inputs["Contrast"].default_value = 3.0
            links.new(base_color.outputs["Color"], delta.inputs[1])
            links.new(detail_mix.outputs["Color"], delta.inputs[2])
            links.new(delta.outputs["Color"], brighten.inputs["Color"])
            links.new(brighten.outputs["Color"], emission.inputs["Color"])

    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return mat


def render_mixed_color_debug_passes(debug_dir, sample_id, primary_obj, defect_info):
    scene = bpy.context.scene
    control = bpy.data.objects.get(defect_info["control_object"])
    if control is None:
        raise RuntimeError(f"Mixed-color control object not found for debug pass render: {defect_info['control_object']}")

    original_engine = scene.render.engine
    original_samples = int(getattr(scene.cycles, "samples", 1))
    original_adaptive = bool(getattr(scene.cycles, "use_adaptive_sampling", False))
    original_filepath = scene.render.filepath
    original_hide_render = {obj.name: bool(obj.hide_render) for obj in bpy.data.objects}
    original_materials = [mat for mat in primary_obj.data.materials]
    world = scene.world
    background = find_background_node(world)
    original_bg_color = None
    original_bg_strength = None
    if background is not None:
        original_bg_color = tuple(background.inputs["Color"].default_value)
        original_bg_strength = float(background.inputs["Strength"].default_value)

    black_mask_mat = make_black_mask_material(name="REFERENCE_MIXED_COLOR_DEBUG_BLACK_MASK_MAT")
    pass_modes = [
        "rgb_mask_debug",
        "soft_color_mask_debug",
        "streak_mask_debug",
        "final_rgb_mask_debug",
        "base_color_before",
        "base_color_after",
        "base_color_delta",
    ]
    debug_outputs = {}
    try:
        for obj in bpy.data.objects:
            if obj.type == "MESH":
                obj.hide_render = obj.name != primary_obj.name
        primary_obj.hide_render = False
        if background is not None:
            background.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
            background.inputs["Strength"].default_value = 1.0
        scene.render.engine = "CYCLES"
        scene.cycles.samples = 1
        scene.cycles.use_adaptive_sampling = False

        for mode in pass_modes:
            pass_mat = make_mixed_color_debug_pass_material(
                control,
                defect_info,
                mode,
                f"REFERENCE_MIXED_COLOR_DEBUG_{mode.upper()}",
            )
            primary_obj.data.materials.clear()
            primary_obj.data.materials.append(pass_mat)
            primary_obj.data.materials.append(black_mask_mat)
            pass_path = debug_dir / f"{sample_id:06d}_{mode}.png"
            render_rgb(pass_path)
            debug_outputs[mode] = str(pass_path)
    finally:
        scene.render.engine = original_engine
        scene.cycles.samples = original_samples
        scene.cycles.use_adaptive_sampling = original_adaptive
        scene.render.filepath = original_filepath
        if background is not None and original_bg_color is not None and original_bg_strength is not None:
            background.inputs["Color"].default_value = original_bg_color
            background.inputs["Strength"].default_value = original_bg_strength
        primary_obj.data.materials.clear()
        for mat in original_materials:
            primary_obj.data.materials.append(mat)
        for obj in bpy.data.objects:
            if obj.name in original_hide_render:
                obj.hide_render = original_hide_render[obj.name]
    return debug_outputs


def load_binary_mask_from_image(mask_path, threshold=0.5):
    mask_image = bpy.data.images.load(str(mask_path), check_existing=False)
    width, height = mask_image.size
    pixels = list(mask_image.pixels[:])
    binary = build_binary_mask_pixels(pixels, width, height, threshold=threshold)
    bpy.data.images.remove(mask_image)
    save_binary_mask_image(mask_path, binary, width, height, "REFERENCE_MIXED_COLOR_MASK_EXPORT")
    return binary, width, height


def main():
    args = parse_args()
    output_dir = mkdir(args.output)
    rgb_dir = mkdir(output_dir / "rgb")
    mask_dir = mkdir(output_dir / "mask") if args.enable_mixed_color else None
    overlay_dir = mkdir(output_dir / "overlay") if args.enable_mixed_color else None
    yolo_dir = mkdir(output_dir / "labels_yolo") if args.enable_mixed_color else None
    debug_pass_dir = mkdir(output_dir / "debug_passes") if args.enable_mixed_color and args.debug_export_material_passes else None

    bproc.init()
    bpy.ops.wm.open_mainfile(filepath=str(Path(args.blend).resolve()))

    reference_primary = get_primary_object()
    if args.stl:
        primary_obj = import_replacement_stl(args.stl, reference_primary)
    else:
        primary_obj = reference_primary
    hide_non_primary_meshes(primary_obj)
    requested_sides = args.anchor_sides or ["front"]
    initial_side = requested_sides[0]
    ensure_clean_reference_support(primary_obj, initial_side)
    camera = ensure_camera_for_objects([primary_obj], args.width, args.height, initial_side)
    if args.stl:
        apply_replacement_camera_tweak(camera, primary_obj, args.stl)
    render_device_info = configure_cycles_gpu(args.samples)
    back_only = tuple(requested_sides) == ("back",)
    tune_reference_lighting_for_white(base_energy_multiplier=1.5 if back_only else 1.0)
    material_info = assign_white_material(primary_obj)
    bpy.context.view_layer.update()

    _, _, dims = object_bbox_dims(primary_obj)
    max_dim = max(float(dims.x), float(dims.y), float(dims.z))

    samples_meta = []
    for index in range(args.num):
        sample_id = args.start_index + index
        cleanup_mixed_color_objects()
        material_info = assign_white_material(primary_obj)
        if args.validation_mode:
            random.seed(1000 + sample_id)
            apply_validation_jitter(camera)
        if args.enable_mixed_color:
            random.seed(args.mixed_color_seed + sample_id)
            defect_count_max = max(1, int(args.defect_count_max or 1))
            if defect_count_max > 1:
                defect_info = add_same_type_mixed_color_contaminations(
                    primary_obj,
                    material_info,
                    max_dim,
                    camera=camera,
                    allowed_sides=requested_sides,
                    debug_mixed_color_strong=args.debug_mixed_color_strong,
                    debug_center_mixed_color=args.debug_center_mixed_color,
                    max_count=defect_count_max,
                )
            else:
                defect_info = add_mixed_color_contamination(
                    primary_obj,
                    material_info,
                    max_dim,
                    camera=camera,
                    allowed_sides=requested_sides,
                    debug_mixed_color_strong=args.debug_mixed_color_strong,
                    debug_center_mixed_color=args.debug_center_mixed_color,
                )
            defect_side = defect_info.get("anchor_side", initial_side)
            view_transform = build_object_view_transform(args, defect_info)
            camera_side = view_transform["camera_side"] if view_transform["enabled"] else defect_side
            position_camera_for_anchor_side(camera, primary_obj, camera_side)
            support_info = ensure_clean_reference_support(primary_obj, camera_side)
            if args.stl:
                apply_replacement_camera_tweak(camera, primary_obj, args.stl)
            if view_transform["enabled"]:
                apply_object_view_transform(primary_obj, defect_info, view_transform)
            if defect_info.get("world_point"):
                defect_center = Vector(defect_info["world_point"])
                if view_transform["enabled"]:
                    projected = world_to_camera_view(bpy.context.scene, camera, defect_center)
                else:
                    projected = refine_camera_shift_for_defect(camera, bpy.context.scene, defect_center)
                projected_xy = [round(float(projected.x), 4), round(float(projected.y), 4)]
                defect_info["projected_xy"] = projected_xy
                defect_info["camera_follow"] = {
                    "anchor_side": defect_side,
                    "camera_side": camera_side,
                    "projected_xy_after_follow": projected_xy,
                    "visible_after_follow": bool(
                        projected.z > 0.0 and 0.08 <= projected.x <= 0.92 and 0.08 <= projected.y <= 0.92
                    ),
                }
                defect_info["reference_support"] = support_info
                defect_info["view_transform"] = view_transform
        else:
            defect_info = None
        bpy.context.view_layer.update()

        rgb_path = rgb_dir / f"{sample_id:06d}.png"
        render_rgb(rgb_path)
        debug_material_passes = None
        if args.enable_mixed_color and defect_info is not None and debug_pass_dir is not None:
            debug_material_passes = render_mixed_color_debug_passes(
                debug_pass_dir,
                sample_id,
                primary_obj,
                defect_info,
            )
        label_info = None
        if args.enable_mixed_color and defect_info is not None:
            mask_path = mask_dir / f"{sample_id:06d}.png"
            overlay_path = overlay_dir / f"{sample_id:06d}.png"
            label_path = yolo_dir / f"{sample_id:06d}.txt"
            defects_for_label = defect_info.get("defects") or [defect_info]
            merged_binary = None
            mask_width = None
            mask_height = None
            defect_bboxes = []
            label_lines = []
            for instance_index, item in enumerate(defects_for_label):
                tmp_mask_path = mask_dir / f"{sample_id:06d}_mixed_{instance_index:02d}_tmp.png"
                render_mixed_color_binary_mask(tmp_mask_path, primary_obj, material_info, item)
                binary, mask_width, mask_height = load_binary_mask_from_image(
                    tmp_mask_path,
                    threshold=float(item.get("label_threshold", 0.2)),
                )
                if merged_binary is None:
                    merged_binary = [0 for _ in binary]
                merged_binary = [1 if a or b else 0 for a, b in zip(merged_binary, binary)]
                item_bbox = bbox_from_binary_mask(binary, mask_width, mask_height)
                if item_bbox is not None and item_bbox["xywh"][2] > 0 and item_bbox["xywh"][3] > 0:
                    yolo_bbox = bbox_to_yolo(bpy.context.scene, item_bbox)
                    label_lines.append(
                        f"3 {yolo_bbox[0]:.6f} {yolo_bbox[1]:.6f} {yolo_bbox[2]:.6f} {yolo_bbox[3]:.6f}"
                    )
                    defect_bboxes.append(
                        {
                            "defect_type": "mixed_color_contamination",
                            "class_id": 3,
                            "bbox": item_bbox,
                            "instance_index": item.get("instance_index", instance_index),
                        }
                    )
                    item["mask_area_pixels"] = int(item_bbox["area_pixels"])
                    item["bbox_xywh"] = item_bbox["xywh"]
                tmp_mask_path.unlink(missing_ok=True)
            if merged_binary is None:
                merged_binary = []
            save_binary_mask_image(mask_path, merged_binary, mask_width, mask_height, "REFERENCE_MIXED_COLOR_MASK_EXPORT")
            binary = merged_binary
            bbox = bbox_from_binary_mask(binary, mask_width, mask_height)
            save_mask_overlay(
                rgb_path,
                overlay_path,
                binary,
                mask_width,
                mask_height,
                bbox,
                "REFERENCE_MIXED_COLOR_OVERLAY_EXPORT",
            )
            label_text = "\n".join(label_lines)
            if label_text:
                label_text += "\n"
            label_path.write_text(label_text, encoding="utf-8")
            label_info = {
                "mask": str(mask_path.relative_to(output_dir)),
                "overlay": str(overlay_path.relative_to(output_dir)),
                "label_yolo": str(label_path.relative_to(output_dir)),
                "bbox": bbox,
                "defect_bboxes": defect_bboxes,
                "mask_width": mask_width,
                "mask_height": mask_height,
                "label_semantics": "Complete mixed-color patch footprint on the main plane, including the full soft area-like material non-uniformity region rather than only the deepest center.",
            }
            defect_info["mask_area_pixels"] = int(bbox["area_pixels"]) if bbox is not None else 0
            defect_info["bbox_xywh"] = bbox["xywh"] if bbox is not None else None

        samples_meta.append(
            {
                "sample_id": sample_id,
                "rgb_path": str(rgb_path),
                "baseline_version": BASELINE_VERSION,
                "baseline_summary": BASELINE_SUMMARY,
                "blend_path": str(Path(args.blend).resolve()),
                "primary_object_name": primary_obj.name,
                "material_info": material_info,
                "validation_mode": args.validation_mode,
                "mixed_color_contamination": defect_info,
                "lightweight_label": label_info,
                "debug_material_passes": debug_material_passes,
            }
        )

    metadata = {
        "baseline_version": BASELINE_VERSION,
        "baseline_summary": BASELINE_SUMMARY,
        "model_family": "QC7-5244",
        "reference_scene": "moxing1_test.blend",
        "primary_object_name": primary_obj.name,
        "white_material_strategy": "ultra-light two-zone matte-satin neutral white plastic",
        "real_reference_hint": "QC7-5244 normal images under 塑料工件真实数据集",
        "material_info": material_info,
        "mixed_color_version": MIXED_COLOR_VERSION if args.enable_mixed_color else None,
        "render_device_info": render_device_info,
        "notes": [
            f"Baseline locked as {BASELINE_VERSION}.",
            "This is a start-of-line normal-part reference implementation for moxing1_test.blend.",
            "The mixed_color_contamination path is a minimal reference-scene validation path only.",
            "Current mixed-color appearance is material-driven inside the main white plastic material rather than a floating transparent patch surface.",
            "Current mixed-color lightweight labels export the same procedural material defect mask as a complete area-like footprint, plus a mask-derived bbox, overlay image, and YOLO txt for location audit only.",
        ],
        "samples": samples_meta,
    }

    with (output_dir / "metadata.json").open("w", encoding="utf-8") as fp:
        json.dump(metadata, fp, indent=2, ensure_ascii=False)

    if args.save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=str(output_dir / "debug_scene.blend"))


if __name__ == "__main__":
    main()
