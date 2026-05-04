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


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
ASSET_MODEL_DIR = REPO_ROOT / "assets" / "models"
EXTERNAL_PLACEMENT_CONTROL = None

MODEL_PRESETS = {
    "P101040_blue": {
        "aliases": {"P101040", "p101040", "blue", "P101040_blue"},
        "family": "p101040",
        "blend": ASSET_MODEL_DIR / "moxing2.blend",
        "stl": ASSET_MODEL_DIR / "P101040.stl",
        "appearance_profile": "p101040_blue_profile",
        "material_family": "semi_translucent_blue_plastic",
        "radius_scale": (0.0038, 0.0042),
        "depth_scale": (0.0059, 0.0065),
        "samples": 256,
        "anchor_sides": ("front",),
        "camera_lens": 118.0,
        "camera_shift_y": 0.0,
        "camera_roll_deg": 90.0,
        "camera_front_offset": (0.0, -0.18, 2.65),
        "camera_back_offset": (0.0, -0.18, -2.65),
        "size_reference_axes": ("x", "z"),
    },
    "QC71336_white": {
        "aliases": {"QC71336", "QC71336_white", "qc71336", "qc71336_white", "white"},
        "family": "qc71336",
        "blend": ASSET_MODEL_DIR / "moxing2.blend",
        "model_blend": ASSET_MODEL_DIR / "QC7-1336-white.blend",
        "appearance_profile": "qc71336_white_prebuilt_profile",
        "material_family": "prebuilt_authored_white_plastic",
        "use_gray_override": False,
        "black_dot_style": "qc71336_white_prebuilt_legacy_v1",
        "radius_scale": (0.00171, 0.00209),
        "depth_scale": (0.00063, 0.00076),
        "samples": 256,
        "anchor_sides": ("front",),
        "camera_lens": 64.0,
        "camera_shift_y": -0.02,
    },
    "QC71336_gray": {
        "aliases": {"QC71336_gray", "qc71336_gray", "gray", "grey"},
        "family": "qc71336",
        "blend": ASSET_MODEL_DIR / "moxing2.blend",
        "model_blend": ASSET_MODEL_DIR / "QC7-1336-white.blend",
        "appearance_profile": "qc71336_gray_override_profile",
        "material_family": "qc71336_gray_override_plastic",
        "use_gray_override": True,
        "radius_scale": (0.0036, 0.0064),
        "depth_scale": (0.00120, 0.00224),
        "samples": 256,
        "anchor_sides": ("front",),
        "camera_lens": 66.0,
        "camera_shift_y": -0.02,
    },
    "QC75244_white": {
        "aliases": {"QC75244", "QC75244_white", "qc75244", "qc75244_white", "QC7-5244", "qc7-5244"},
        "family": "qc75244",
        "blend": ASSET_MODEL_DIR / "moxing1_test.blend",
        "stl": ASSET_MODEL_DIR / "QC7-5236.stl",
        "appearance_profile": "qc75244_white_reference_profile",
        "material_family": "ultra_light_matte_satin_white_plastic",
        "radius_scale": (0.0018, 0.0034),
        "depth_scale": (0.00055, 0.00115),
        "samples": 256,
        "anchor_sides": ("front",),
        "camera_lens": 78.0,
        "camera_shift_y": 0.025,
        "safe_anchor_windows": [
            {
                "name": "qc75244_main_flat_center",
                "local_x": (-0.36, 0.42),
                "local_y": (-0.34, 0.42),
                "local_z_abs_min": 0.66,
                "normal_z_min": 0.82
            }
        ],
    },
}


def canonical_model_name(name):
    for preset_name, preset in MODEL_PRESETS.items():
        if name == preset_name or name in preset["aliases"]:
            return preset_name
    choices = ", ".join(MODEL_PRESETS)
    raise ValueError(f"Unknown model '{name}'. Choose one of: {choices}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Unified reference-scene black-dot generator for P101040, QC71336, and QC75244."
    )
    parser.add_argument("--model", required=True, help="P101040_blue, QC71336_white, QC71336_gray, or QC75244_white.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--num", type=int, default=1)
    parser.add_argument("--start_index", type=int, default=0)
    parser.add_argument("--width", type=int, default=1536)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--samples", type=int, default=None)
    parser.add_argument("--seed", type=int, default=41)
    parser.add_argument("--blend", default=None, help="Override the reference-scene blend.")
    parser.add_argument("--stl", default=None, help="Override STL path for STL-backed presets.")
    parser.add_argument("--model_blend", default=None, help="Override appended model blend for QC71336 presets.")
    parser.add_argument("--material_json", "--material-json", default=None, help="Optional visual material calibration JSON for the main object material.")
    parser.add_argument("--anchor_sides", nargs="+", choices=["front", "back"], default=None)
    parser.add_argument("--black_dot_radius_min_scale", type=float, default=None)
    parser.add_argument("--black_dot_radius_max_scale", type=float, default=None)
    parser.add_argument("--black_dot_depth_min_scale", type=float, default=None)
    parser.add_argument("--black_dot_depth_max_scale", type=float, default=None)
    parser.add_argument("--camera_jitter_strength", type=float, default=1.0)
    parser.add_argument("--light_jitter_strength", type=float, default=1.0)
    parser.add_argument("--object_jitter_degrees", type=float, default=0.0)
    parser.add_argument("--object_transform_mode", choices=["none", "keep_camera"], default="none")
    parser.add_argument("--object_transform_camera_side", choices=["front", "back"], default="front")
    parser.add_argument("--object_rotate_deg", nargs=3, type=float, default=None, metavar=("RX", "RY", "RZ"))
    parser.add_argument("--object_translate", nargs=3, type=float, default=[0.0, 0.0, 0.0], metavar=("X", "Y", "Z"))
    parser.add_argument("--safe_anchor_local_x", nargs=2, type=float, default=None, metavar=("MIN", "MAX"))
    parser.add_argument("--safe_anchor_local_y", nargs=2, type=float, default=None, metavar=("MIN", "MAX"))
    parser.add_argument("--safe_anchor_local_z_abs_min", type=float, default=0.0)
    parser.add_argument("--safe_anchor_normal_z_min", type=float, default=0.0)
    parser.add_argument("--max_attempts_per_image", type=int, default=12)
    parser.add_argument("--save_blend", action="store_true")
    parser.add_argument("--save_blend_only_first", action="store_true", default=True)
    parser.add_argument("--keep_failed_blend", action="store_true")
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = argv[1:]
    args = parser.parse_args(argv)
    args.model = canonical_model_name(args.model)
    return args


def apply_cli_safe_anchor_window(args):
    global EXTERNAL_PLACEMENT_CONTROL
    if args.safe_anchor_local_x is None and args.safe_anchor_local_y is None:
        return
    x_range = args.safe_anchor_local_x or [-1.0, 1.0]
    y_range = args.safe_anchor_local_y or [-1.0, 1.0]
    EXTERNAL_PLACEMENT_CONTROL = {
        "safe_anchor_windows": [
            {
                "name": "cli_safe_anchor_window",
                "local_x": [float(x_range[0]), float(x_range[1])],
                "local_y": [float(y_range[0]), float(y_range[1])],
                "local_z_abs_min": float(args.safe_anchor_local_z_abs_min),
                "normal_z_min": float(args.safe_anchor_normal_z_min),
            }
        ]
    }


def mkdir(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_path(value, default_path):
    return Path(value).resolve() if value else Path(default_path).resolve()


def world_bbox(objects):
    corners = []
    for obj in objects:
        corners.extend([obj.matrix_world @ Vector(corner) for corner in obj.bound_box])
    mins = Vector((min(v.x for v in corners), min(v.y for v in corners), min(v.z for v in corners)))
    maxs = Vector((max(v.x for v in corners), max(v.y for v in corners), max(v.z for v in corners)))
    return mins, maxs


def bbox_to_yolo(scene, bbox):
    width = float(scene.render.resolution_x)
    height = float(scene.render.resolution_y)
    x, y, bw_px, bh_px = bbox["xywh"]
    xc = (x + bw_px * 0.5) / width
    yc = (y + bh_px * 0.5) / height
    bw = bw_px / width
    bh = bh_px / height
    return xc, yc, bw, bh


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


def get_mesh_objects():
    return [obj for obj in bpy.data.objects if obj.type == "MESH"]


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
    return dims_sorted[0] < 0.03 * dims_sorted[-1] and dims_sorted[1] > 0.40 * dims_sorted[-1]


def pick_primary_mesh_objects():
    candidates = [obj for obj in get_mesh_objects() if not is_background_like(obj)]
    if not candidates:
        candidates = get_mesh_objects()
    if not candidates:
        raise RuntimeError("No mesh objects found in the reference scene.")

    def score(obj):
        _, _, dims = object_bbox_dims(obj)
        volume = max(float(dims.x), 1e-6) * max(float(dims.y), 1e-6) * max(float(dims.z), 1e-6)
        return volume, len(obj.data.vertices)

    candidates.sort(key=score, reverse=True)
    top = score(candidates[0])[0]
    return [obj for obj in candidates if score(obj)[0] >= top * 0.15]


def find_principled(mat):
    if mat is None or not mat.use_nodes or mat.node_tree is None:
        return None
    for node in mat.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            return node
    return None


def set_principled_input(bsdf, names, value):
    for name in names if isinstance(names, (tuple, list)) else [names]:
        if name in bsdf.inputs:
            bsdf.inputs[name].default_value = value
            return True
    return False


def make_principled_material(name, base_color, roughness, specular, alpha=1.0):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = find_principled(mat)
    if bsdf is None:
        mat.node_tree.nodes.clear()
        output = mat.node_tree.nodes.new("ShaderNodeOutputMaterial")
        bsdf = mat.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
        mat.node_tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    set_principled_input(bsdf, "Base Color", base_color)
    set_principled_input(bsdf, "Roughness", roughness)
    set_principled_input(bsdf, ("Specular IOR Level", "Specular"), specular)
    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = alpha
    if alpha < 1.0:
        mat.blend_method = "BLEND"
        if hasattr(mat, "shadow_method"):
            try:
                mat.shadow_method = "NONE"
            except TypeError:
                mat.shadow_method = "HASHED"
        if hasattr(mat, "show_transparent_back"):
            mat.show_transparent_back = False
    return mat


def add_noise_bump(mat, scale=800.0, strength=0.001, distance=0.0008):
    bsdf = find_principled(mat)
    if bsdf is None:
        return
    tree = mat.node_tree
    texcoord = tree.nodes.new("ShaderNodeTexCoord")
    mapping = tree.nodes.new("ShaderNodeMapping")
    noise = tree.nodes.new("ShaderNodeTexNoise")
    bump = tree.nodes.new("ShaderNodeBump")
    mapping.inputs["Scale"].default_value = (scale, scale, scale)
    noise.inputs["Scale"].default_value = 1.0
    noise.inputs["Detail"].default_value = 9.0
    noise.inputs["Roughness"].default_value = 0.55
    bump.inputs["Strength"].default_value = strength
    bump.inputs["Distance"].default_value = distance
    tree.links.new(texcoord.outputs["Object"], mapping.inputs["Vector"])
    tree.links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    tree.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    tree.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


def load_external_material_parameters(material_json_path):
    if not material_json_path:
        return None
    path = Path(material_json_path)
    if not path.exists():
        raise FileNotFoundError(f"Material JSON not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    material_parameters = data.get("material_parameters", data)
    if not isinstance(material_parameters, dict):
        raise ValueError("Material JSON must contain an object under material_parameters or use the old flat schema.")
    return {
        "path": str(path),
        "schema_version": data.get("schema_version", "legacy_flat"),
        "calibration_type": data.get("calibration_type"),
        "material_parameters": material_parameters,
        "material_source": data.get("material_source"),
        "placement_control": data.get("placement_control"),
        "scene_calibration": data.get("scene_calibration", {}),
    }


def apply_external_visual_material(objects, material_json_path):
    global EXTERNAL_PLACEMENT_CONTROL
    calibration = load_external_material_parameters(material_json_path)
    if calibration is None:
        return None
    EXTERNAL_PLACEMENT_CONTROL = calibration.get("placement_control")
    material_source = calibration.get("material_source")
    if material_source:
        return apply_external_blend_material(objects, calibration, material_source)
    params = calibration["material_parameters"]
    base_color = params.get("base_color", (0.72, 0.72, 0.72, 1.0))
    if len(base_color) == 3:
        base_color = list(base_color) + [1.0]
    roughness = float(params.get("roughness", 0.55))
    specular = float(params.get("specular", params.get("specular_ior_level", 0.25)))
    alpha = float(params.get("alpha", 1.0))
    mat = make_principled_material(
        "UNIFIED_EXTERNAL_VISUAL_CALIBRATION_MAT",
        tuple(float(v) for v in base_color[:4]),
        roughness,
        specular,
        alpha=alpha,
    )
    bump_strength = float(params.get("bump_strength", 0.0) or 0.0)
    noise_strength = float(params.get("noise_strength", 0.0) or 0.0)
    if bump_strength > 0.0 or noise_strength > 0.0:
        noise_scale = float(params.get("noise_scale", 96.0) or 96.0)
        bump_distance = max(0.00035, min(0.006, noise_strength * 0.08 if noise_strength > 0 else 0.001))
        add_noise_bump(mat, scale=noise_scale, strength=max(bump_strength, noise_strength), distance=bump_distance)
    assigned_objects = []
    for obj in objects:
        if obj.type != "MESH":
            continue
        obj.data.materials.clear()
        obj.data.materials.append(mat)
        assigned_objects.append(obj.name)
    bpy.context.view_layer.update()
    return {
        "external_material_json": calibration["path"],
        "schema_version": calibration["schema_version"],
        "calibration_type": calibration["calibration_type"],
        "material_name": mat.name,
        "assigned_objects": assigned_objects,
        "material_parameters_used": {
            "base_color": tuple(float(v) for v in base_color[:4]),
            "roughness": roughness,
            "specular": specular,
            "alpha": alpha,
            "noise_scale": float(params.get("noise_scale", 96.0) or 96.0),
            "noise_strength": noise_strength,
            "bump_strength": bump_strength,
        },
        "scene_calibration_recorded_only": calibration.get("scene_calibration", {}),
        "scoring_fields_used_for_rendering": False,
    }


def apply_external_blend_material(objects, calibration, material_source):
    blend_path = Path(material_source.get("blend_path", ""))
    material_name = material_source.get("material_name")
    if not blend_path.exists():
        raise FileNotFoundError(f"Source material blend not found: {blend_path}")
    if not material_name:
        raise ValueError("material_source.material_name is required when using a blend material source.")

    before_names = set(bpy.data.materials.keys())
    directory = str(blend_path) + "\\Material\\"
    bpy.ops.wm.append(filename=material_name, directory=directory)
    appended = [mat for mat in bpy.data.materials if mat.name not in before_names]
    if appended:
        source_mat = appended[-1]
    else:
        source_mat = bpy.data.materials.get(material_name)
    if source_mat is None:
        raise RuntimeError(f"Could not append material '{material_name}' from {blend_path}")

    assigned_objects = []
    for obj in objects:
        if obj.type != "MESH":
            continue
        mat = source_mat.copy()
        mat.name = f"UNIFIED_EXTERNAL_BLEND_MAT_{obj.name[:32]}"
        adjust_external_blend_material_nodes(mat, material_source)
        obj.data.materials.clear()
        obj.data.materials.append(mat)
        assigned_objects.append(obj.name)
    bpy.context.view_layer.update()
    return {
        "external_material_json": calibration["path"],
        "schema_version": calibration["schema_version"],
        "calibration_type": calibration["calibration_type"],
        "material_source": {
            "blend_path": str(blend_path),
            "material_name": material_name,
            "source_material_name_after_append": source_mat.name,
        },
        "assigned_objects": assigned_objects,
        "material_parameters_used": calibration.get("material_parameters", {}),
        "scene_calibration_recorded_only": calibration.get("scene_calibration", {}),
        "scoring_fields_used_for_rendering": False,
    }


def adjust_external_blend_material_nodes(mat, material_source):
    if not mat or not mat.use_nodes or mat.node_tree is None:
        return
    tree = mat.node_tree
    disable_normal = bool(material_source.get("disable_normal_map", False))
    normal_strength_scale = material_source.get("normal_strength_scale")
    if disable_normal:
        for node in tree.nodes:
            if node.type == "BSDF_PRINCIPLED":
                normal_socket = node.inputs.get("Normal")
                if normal_socket is not None:
                    for link in list(normal_socket.links):
                        tree.links.remove(link)
    elif normal_strength_scale is not None:
        scale = float(normal_strength_scale)
        for node in tree.nodes:
            if node.type in {"NORMAL_MAP", "BUMP"}:
                strength = node.inputs.get("Strength")
                if strength is not None:
                    strength.default_value = float(strength.default_value) * scale

    texture_scale = material_source.get("texture_scale")
    if texture_scale is not None:
        scale = float(texture_scale)
        for node in tree.nodes:
            if node.type == "MAPPING":
                scale_socket = node.inputs.get("Scale")
                if scale_socket is not None:
                    try:
                        scale_socket.default_value[0] *= scale
                        scale_socket.default_value[1] *= scale
                        scale_socket.default_value[2] *= scale
                    except Exception:
                        pass


def render_still(path):
    bpy.context.scene.render.filepath = str(path)
    bpy.context.view_layer.update()
    bpy.ops.render.render(write_still=True)


def configure_cycles_gpu(samples):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.use_adaptive_sampling = True
    gpu_info = {
        "requested": True,
        "cycles_device": "CPU",
        "compute_device_type": None,
        "devices": [],
        "fallback": "cpu",
    }
    try:
        prefs = bpy.context.preferences
        cycles_pref = prefs.addons["cycles"].preferences
        selected_type = None
        selected_devices = []
        for device_type in ["OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"]:
            try:
                cycles_pref.compute_device_type = device_type
                cycles_pref.get_devices()
                selected_devices = list(cycles_pref.devices)
                if any(device.type != "CPU" for device in selected_devices):
                    selected_type = device_type
                    break
            except Exception:
                continue
        if selected_type:
            scene.cycles.device = "GPU"
            cycles_pref.compute_device_type = selected_type
            cycles_pref.get_devices()
            for device in cycles_pref.devices:
                device.use = device.type != "CPU"
            gpu_info["cycles_device"] = "GPU"
            gpu_info["compute_device_type"] = selected_type
            gpu_info["fallback"] = None
        else:
            scene.cycles.device = "CPU"
            for device in selected_devices:
                device.use = device.type == "CPU"
        gpu_info["devices"] = [
            {
                "name": getattr(device, "name", ""),
                "type": getattr(device, "type", ""),
                "use": bool(getattr(device, "use", False)),
            }
            for device in cycles_pref.devices
        ]
    except Exception as exc:
        try:
            scene.cycles.device = "CPU"
        except Exception:
            pass
        gpu_info["error"] = str(exc)
    return gpu_info


def ensure_camera_for_objects(objects, width, height, lens=82.0, shift_y=0.05):
    bb_min, bb_max = world_bbox(objects)
    center = (bb_min + bb_max) * 0.5
    span = bb_max - bb_min
    max_dim = max(float(abs(span.x)), float(abs(span.y)), float(abs(span.z)), 1e-3)
    camera = bpy.data.objects.get("UNIFIED_BLACK_DOT_CAMERA")
    if camera is None:
        camera_data = bpy.data.cameras.new("UNIFIED_BLACK_DOT_CAMERA")
        camera = bpy.data.objects.new("UNIFIED_BLACK_DOT_CAMERA", camera_data)
        bpy.context.scene.collection.objects.link(camera)
    scene = bpy.context.scene
    scene.camera = camera
    camera.data.type = "PERSP"
    camera.data.lens = lens
    camera.data.sensor_width = 36.0
    camera.data.sensor_fit = "HORIZONTAL"
    camera.data.clip_start = 0.01
    camera.data.clip_end = 1000.0
    camera.data.shift_x = 0.0
    camera.data.shift_y = shift_y
    location = center + Vector((0.0, -0.28 * max_dim, 2.60 * max_dim))
    direction = center - location
    camera.location = location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    bpy.context.view_layer.update()
    return camera


def ensure_background_support(base_color=(0.82, 0.825, 0.83, 1.0), roughness=0.84):
    existing = bpy.data.objects.get("UNIFIED_REFERENCE_BACKDROP")
    if existing is not None:
        return existing
    bpy.ops.mesh.primitive_plane_add(size=20.0, location=(0.0, 0.0, -0.15))
    plane = bpy.context.active_object
    plane.name = "UNIFIED_REFERENCE_BACKDROP"
    plane.scale = (2.5, 2.5, 1.0)
    mat = make_principled_material("UNIFIED_REFERENCE_BACKDROP_MAT", base_color, roughness, 0.06)
    plane.data.materials.clear()
    plane.data.materials.append(mat)
    bpy.context.view_layer.update()
    return plane


def import_stl(path):
    before = {obj.name for obj in bpy.data.objects}
    try:
        bpy.ops.wm.stl_import(filepath=str(path))
    except Exception:
        bpy.ops.import_mesh.stl(filepath=str(path))
    imported = [obj for obj in bpy.data.objects if obj.name not in before and obj.type == "MESH"]
    if not imported:
        raise RuntimeError(f"Failed to import STL: {path}")
    return imported


def append_blend_objects(path, object_keywords=()):
    path = Path(path)
    with bpy.data.libraries.load(str(path), link=False) as (data_from, data_to):
        data_to.objects = [name for name in data_from.objects if name]
    loaded = [obj for obj in data_to.objects if obj is not None]
    if not loaded:
        raise RuntimeError(f"No objects found in blend model: {path}")
    for obj in loaded:
        if obj.name not in bpy.context.scene.collection.objects:
            bpy.context.scene.collection.objects.link(obj)
    meshes = [obj for obj in loaded if obj.type == "MESH"]
    if object_keywords:
        filtered = [obj for obj in meshes if any(token in obj.name for token in object_keywords)]
        if filtered:
            keep = {obj.name for obj in filtered}
            for obj in meshes:
                if obj.name not in keep:
                    obj.hide_render = True
                    obj.hide_viewport = True
            meshes = filtered
    if not meshes:
        raise RuntimeError(f"No mesh objects appended from blend model: {path}")
    bpy.context.view_layer.update()
    return meshes


def fit_objects_to_reference(imported_objects, reference_objects, scale_factor=0.95):
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
    original_rotations = [obj.rotation_euler.copy() for obj in imported_objects]
    best_rotation = candidate_rotations[0]
    best_score = None
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
        xy_penalty = abs((src_xy[0] / max(src_xy[1], 1e-6)) - (ref_xy[0] / max(ref_xy[1], 1e-6)))
        score = thickness + 0.25 * xy_penalty
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
    scale = scale_factor * ref_max_dim / src_max_dim
    for obj in imported_objects:
        obj.scale = obj.scale * scale
    bpy.context.view_layer.update()
    src_min, src_max = world_bbox(imported_objects)
    src_center = (src_min + src_max) * 0.5
    offset = ref_center - src_center
    for obj in imported_objects:
        obj.location += offset
    bpy.context.view_layer.update()


def summarize_materials(objects):
    return {obj.name: [mat.name for mat in obj.data.materials if mat is not None] for obj in objects}


def tune_reference_lighting_for_blue():
    scene = bpy.context.scene
    for obj in bpy.data.objects:
        if obj.type != "LIGHT":
            continue
        if getattr(obj.data, "color", None) is not None:
            obj.data.color = (0.92, 0.97, 1.0)
        if hasattr(obj.data, "energy"):
            obj.data.energy = float(obj.data.energy) * 0.72
    world = scene.world
    if world and world.use_nodes and world.node_tree:
        bg = find_background_node(world)
        if bg is not None:
            bg.inputs["Color"].default_value = (0.93, 0.96, 1.0, 1.0)
            bg.inputs["Strength"].default_value = min(float(bg.inputs["Strength"].default_value), 0.24)
    bpy.context.view_layer.update()


def tune_reference_lighting_for_qc71336_white():
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
    for obj in bpy.data.objects:
        if obj.type != "LIGHT":
            continue
        scale = energy_scale_map.get(obj.name, 0.20)
        if getattr(obj.data, "color", None) is not None:
            obj.data.color = (1.0, 0.975, 0.944) if obj.name in warm_lights else (0.982, 0.965, 0.948)
        if hasattr(obj.data, "energy"):
            obj.data.energy = float(obj.data.energy) * scale
        if obj.data.type == "AREA":
            if hasattr(obj.data, "size"):
                obj.data.size = float(obj.data.size) * (0.75 if obj.name in warm_lights else 1.04)
            if hasattr(obj.data, "size_y"):
                obj.data.size_y = float(obj.data.size_y) * (0.75 if obj.name in warm_lights else 1.04)
    bg = find_background_node(scene.world)
    if bg is not None:
        bg.inputs["Color"].default_value = (0.705, 0.697, 0.686, 1.0)
        bg.inputs["Strength"].default_value = min(float(bg.inputs["Strength"].default_value), 0.014)
    scene.view_settings.exposure = -0.72
    try:
        scene.view_settings.look = "Medium High Contrast"
    except Exception:
        pass
    bpy.context.view_layer.update()


def tune_reference_lighting_for_qc75244_white(base_energy_multiplier=1.0):
    scene = bpy.context.scene
    energy_scale_map = {
        "Area": 0.12,
        "Area.001": 0.07,
        "Area.002": 0.05,
        "Area.003": 1.04,
        "Area.004": 0.11,
    }
    for obj in bpy.data.objects:
        if obj.type != "LIGHT":
            continue
        base_energy = 2000.0 if obj.data.type == "AREA" else 500.0
        obj.data.energy = base_energy * energy_scale_map.get(obj.name, 0.18) * base_energy_multiplier
        if getattr(obj.data, "color", None) is not None:
            obj.data.color = (1.0, 0.989, 0.975) if obj.name == "Area.003" else (0.97, 0.976, 0.988)
        if obj.data.type == "AREA":
            obj.data.shape = "RECTANGLE"
            if obj.name == "Area.003":
                obj.data.size = 1.48
                obj.data.size_y = 0.88
            else:
                obj.data.size = 2.2
                obj.data.size_y = 1.5
    if scene.world is None:
        scene.world = bpy.data.worlds.new("World")
    scene.world.use_nodes = True
    bg = find_background_node(scene.world)
    if bg is not None:
        bg.inputs["Color"].default_value = (0.80, 0.804, 0.812, 1.0)
        bg.inputs["Strength"].default_value = 0.034
    scene.view_settings.look = "None"
    scene.view_settings.exposure = -0.31


def duplicate_material(mat, new_name):
    new_mat = mat.copy()
    new_mat.name = new_name
    return new_mat


def hex_rgba(value):
    value = value.strip().lstrip("#")
    return (
        int(value[0:2], 16) / 255.0,
        int(value[2:4], 16) / 255.0,
        int(value[4:6], 16) / 255.0,
        1.0,
    )


def apply_reference_node_colors(mat, refraction_hex, translucent_hex):
    if not mat or not mat.use_nodes or not mat.node_tree:
        return
    refraction_rgba = hex_rgba(refraction_hex)
    translucent_rgba = hex_rgba(translucent_hex)
    for node in mat.node_tree.nodes:
        node_type = getattr(node, "type", "")
        node_name = getattr(node, "name", "").lower()
        if node_type == "BSDF_REFRACTION" or "refraction" in node_name:
            color_input = node.inputs.get("Color")
            if color_input is not None:
                color_input.default_value = refraction_rgba
        if node_type == "BSDF_TRANSLUCENT" or "translucent" in node_name:
            color_input = node.inputs.get("Color")
            if color_input is not None:
                color_input.default_value = translucent_rgba


def tint_material(mat, new_name, base_color, roughness, specular, transmission=0.0, coat=0.0):
    new_mat = duplicate_material(mat, new_name)
    bsdf = find_principled(new_mat)
    if bsdf is not None:
        set_principled_input(bsdf, "Base Color", base_color)
        set_principled_input(bsdf, "Roughness", roughness)
        set_principled_input(bsdf, ("Specular IOR Level", "Specular"), specular)
        set_principled_input(bsdf, ("Transmission Weight", "Transmission"), transmission)
        set_principled_input(bsdf, ("Coat Weight", "Clearcoat"), coat)
    return new_mat


def assign_bluer_material(objects, reference_objects):
    source_materials = []
    seen = set()
    for obj in reference_objects:
        for slot in obj.material_slots:
            if slot.material is not None and slot.material.name not in seen:
                source_materials.append(slot.material)
                seen.add(slot.material.name)
    if source_materials:
        source = next((mat for mat in source_materials if mat.name.lower() == "blue"), source_materials[0])
        center = tint_material(source, "UNIFIED_P101040_CENTER_PLANE", (0.24, 0.43, 0.72, 1.0), 0.21, 0.66, 0.40, 0.20)
        slope = tint_material(source, "UNIFIED_P101040_SLOPE_BAND", (0.20, 0.44, 0.78, 1.0), 0.11, 0.78, 0.48, 0.30)
        outer = tint_material(source, "UNIFIED_P101040_OUTER_BAND", (0.16, 0.41, 0.82, 1.0), 0.11, 0.78, 0.28, 0.30)
    else:
        center = make_principled_material("UNIFIED_P101040_CENTER_PLANE", (0.24, 0.43, 0.72, 1.0), 0.21, 0.66)
        slope = make_principled_material("UNIFIED_P101040_SLOPE_BAND", (0.20, 0.44, 0.78, 1.0), 0.16, 0.78)
        outer = make_principled_material("UNIFIED_P101040_OUTER_BAND", (0.16, 0.41, 0.82, 1.0), 0.14, 0.78)
    apply_reference_node_colors(center, "98B6FF", "1423FF")
    apply_reference_node_colors(slope, "98B6FF", "537AFF")
    apply_reference_node_colors(outer, "7DB9FF", "0045FF")
    add_noise_bump(center, scale=780.0, strength=0.0038, distance=0.0008)
    add_noise_bump(slope, scale=700.0, strength=0.0025, distance=0.0007)
    for obj in objects:
        mesh = obj.data
        mesh.materials.clear()
        mesh.materials.append(center)
        mesh.materials.append(slope)
        mesh.materials.append(outer)
        bb_min = Vector((min(v[0] for v in obj.bound_box), min(v[1] for v in obj.bound_box), min(v[2] for v in obj.bound_box)))
        bb_max = Vector((max(v[0] for v in obj.bound_box), max(v[1] for v in obj.bound_box), max(v[2] for v in obj.bound_box)))
        span = bb_max - bb_min
        for poly in mesh.polygons:
            x_ratio = (poly.center.x - bb_min.x) / max(float(span.x), 1e-6)
            y_ratio = (poly.center.y - bb_min.y) / max(float(span.y), 1e-6)
            if 0.22 <= x_ratio <= 0.78 and 0.22 <= y_ratio <= 0.78 and poly.normal.z > 0.45:
                poly.material_index = 0
            elif poly.normal.z > 0.20:
                poly.material_index = 1
            else:
                poly.material_index = 2
    return {"center": center.name, "slope": slope.name, "outer": outer.name}


def tune_prebuilt_white_materials(objects):
    tuned = {}
    for obj in objects:
        for mat in obj.data.materials:
            if mat is None or mat.name in tuned:
                continue
            bsdf = find_principled(mat)
            if bsdf is None:
                continue
            base = bsdf.inputs.get("Base Color")
            if base is not None:
                old = tuple(float(v) for v in base.default_value)
                base.default_value = (
                    min(old[0] * 0.60, 1.0),
                    min(old[1] * 0.585, 1.0),
                    min(old[2] * 0.57, 1.0),
                    old[3],
                )
            rough = bsdf.inputs.get("Roughness")
            if rough is not None:
                rough.default_value = min(float(rough.default_value) + 0.08, 0.92)
            spec_name = "Specular IOR Level" if "Specular IOR Level" in bsdf.inputs else "Specular"
            spec = bsdf.inputs.get(spec_name)
            if spec is not None:
                spec.default_value = float(spec.default_value) * 0.58
            tuned[mat.name] = {
                "base_color": tuple(float(v) for v in base.default_value) if base is not None else None,
                "roughness": float(rough.default_value) if rough is not None else None,
                "specular": float(spec.default_value) if spec is not None else None,
            }
    bpy.context.view_layer.update()
    return tuned


def build_qc71336_gray_material():
    mat = make_principled_material("UNIFIED_QC71336_GRAY_OVERRIDE", (0.445, 0.438, 0.432, 1.0), 0.76, 0.26)
    add_noise_bump(mat, scale=520.0, strength=0.0018, distance=0.0006)
    return mat


def apply_gray_override_material(objects):
    mat = build_qc71336_gray_material()
    for obj in objects:
        obj.data.materials.clear()
        obj.data.materials.append(mat)
    for obj in bpy.data.objects:
        if obj.type == "LIGHT" and hasattr(obj.data, "energy"):
            obj.data.energy = float(obj.data.energy) * 0.78
    bpy.context.scene.view_settings.exposure = float(bpy.context.scene.view_settings.exposure) - 0.24
    bpy.context.view_layer.update()
    return mat.name


def get_primary_object(name_hint="QC7-5236-000N301002ST0101"):
    obj = bpy.data.objects.get(name_hint)
    if obj is not None and obj.type == "MESH":
        return obj
    meshes = [obj for obj in bpy.data.objects if obj.type == "MESH" and not is_background_like(obj)]
    if not meshes:
        meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError("No mesh objects found.")
    meshes.sort(key=lambda obj: len(obj.data.vertices), reverse=True)
    return meshes[0]


def import_replacement_stl(stl_path, reference_obj):
    imported = import_stl(stl_path)
    imported.sort(key=lambda obj: len(obj.data.vertices), reverse=True)
    primary = imported[0]
    primary.name = f"{reference_obj.name}_{Path(stl_path).stem}"
    primary.rotation_euler = reference_obj.rotation_euler.copy()
    primary.scale = reference_obj.scale.copy()
    primary.location = reference_obj.location.copy()
    bpy.context.view_layer.update()
    ref_min, ref_max, ref_dims = object_bbox_dims(reference_obj)
    _, _, imp_dims = object_bbox_dims(primary)
    scale = max(float(ref_dims.x), float(ref_dims.y), float(ref_dims.z), 1e-6) / max(float(imp_dims.x), float(imp_dims.y), float(imp_dims.z), 1e-6)
    primary.scale = primary.scale * scale
    bpy.context.view_layer.update()
    imp_min, imp_max, _ = object_bbox_dims(primary)
    primary.location += ((ref_min + ref_max) * 0.5) - ((imp_min + imp_max) * 0.5)
    bpy.context.view_layer.update()
    return primary


def hide_non_primary_meshes(primary_obj):
    for obj in bpy.data.objects:
        if obj.type == "MESH" and obj.name != primary_obj.name:
            obj.hide_render = True
            obj.hide_viewport = True


def ensure_clean_reference_support(primary_obj):
    bb_min, bb_max = world_bbox([primary_obj])
    center = (bb_min + bb_max) * 0.5
    span = bb_max - bb_min
    max_dim = max(float(abs(span.x)), float(abs(span.y)), float(abs(span.z)), 1e-3)
    floor = bpy.data.objects.get("UNIFIED_QC75244_REFERENCE_FLOOR")
    if floor is None:
        bpy.ops.mesh.primitive_plane_add(size=2.0, location=(center.x, center.y, bb_min.z - 0.02 * max_dim))
        floor = bpy.context.active_object
        floor.name = "UNIFIED_QC75244_REFERENCE_FLOOR"
    floor.scale = (1.65 * max_dim, 1.45 * max_dim, 1.0)
    floor.location = (center.x, center.y, bb_min.z - 0.03 * max_dim)
    wall = bpy.data.objects.get("UNIFIED_QC75244_REFERENCE_WALL")
    if wall is None:
        bpy.ops.mesh.primitive_plane_add(size=2.0, location=(center.x, center.y + 1.1 * max_dim, center.z + 0.65 * max_dim))
        wall = bpy.context.active_object
        wall.name = "UNIFIED_QC75244_REFERENCE_WALL"
    wall.scale = (1.7 * max_dim, 1.15 * max_dim, 1.0)
    wall.location = (center.x - 0.12 * max_dim, center.y + 1.00 * max_dim, center.z + 0.62 * max_dim)
    wall.rotation_euler = (math.radians(86.0), 0.0, math.radians(180.0))
    floor.data.materials.clear()
    floor.data.materials.append(make_principled_material("UNIFIED_QC75244_FLOOR_MAT", (0.85, 0.853, 0.858, 1.0), 0.86, 0.06))
    wall.data.materials.clear()
    wall.data.materials.append(make_principled_material("UNIFIED_QC75244_WALL_MAT", (0.30, 0.315, 0.335, 1.0), 0.95, 0.04))


def assign_qc75244_white_material(primary_obj):
    main = make_principled_material("UNIFIED_QC75244_WHITE_MAIN", (0.700, 0.706, 0.714, 1.0), 0.570, 0.106)
    edge = make_principled_material("UNIFIED_QC75244_WHITE_EDGE", (0.716, 0.722, 0.730, 1.0), 0.540, 0.122)
    add_noise_bump(main, scale=44.0, strength=0.014, distance=0.02)
    add_noise_bump(edge, scale=44.0, strength=0.016, distance=0.02)
    mesh = primary_obj.data
    mesh.materials.clear()
    mesh.materials.append(main)
    mesh.materials.append(edge)
    bb_min = Vector((min(v[0] for v in primary_obj.bound_box), min(v[1] for v in primary_obj.bound_box), min(v[2] for v in primary_obj.bound_box)))
    bb_max = Vector((max(v[0] for v in primary_obj.bound_box), max(v[1] for v in primary_obj.bound_box), max(v[2] for v in primary_obj.bound_box)))
    span = bb_max - bb_min
    main_count = 0
    edge_count = 0
    for poly in mesh.polygons:
        x_ratio = (poly.center.x - bb_min.x) / max(float(span.x), 1e-6)
        y_ratio = (poly.center.y - bb_min.y) / max(float(span.y), 1e-6)
        z_ratio = (poly.center.z - bb_min.z) / max(float(span.z), 1e-6)
        is_main = 0.16 <= x_ratio <= 0.84 and 0.15 <= y_ratio <= 0.87 and 0.40 <= z_ratio <= 0.86 and poly.normal.z >= 0.72
        poly.material_index = 0 if is_main else 1
        main_count += int(is_main)
        edge_count += int(not is_main)
    return {"main_plane_material": main.name, "edge_wall_material": edge.name, "main_face_count": main_count, "edge_face_count": edge_count}


def find_background_node(world):
    if world is None or not world.use_nodes or world.node_tree is None:
        return None
    for node in world.node_tree.nodes:
        if node.type == "BACKGROUND":
            return node
    return None


def snapshot_scene_state(objects, camera):
    lights = []
    for obj in bpy.data.objects:
        if obj.type != "LIGHT":
            continue
        lights.append({
            "object": obj,
            "matrix": obj.matrix_world.copy(),
            "energy": float(getattr(obj.data, "energy", 0.0)),
            "color": tuple(getattr(obj.data, "color", (1.0, 1.0, 1.0))),
            "size": float(getattr(obj.data, "size", 0.0)) if hasattr(obj.data, "size") else None,
            "size_y": float(getattr(obj.data, "size_y", 0.0)) if hasattr(obj.data, "size_y") else None,
        })
    world = bpy.context.scene.world
    bg = find_background_node(world)
    return {
        "object_matrices": {obj.name: obj.matrix_world.copy() for obj in objects},
        "camera_matrix": camera.matrix_world.copy(),
        "camera_lens": float(camera.data.lens),
        "camera_shift_x": float(camera.data.shift_x),
        "camera_shift_y": float(camera.data.shift_y),
        "lights": lights,
        "exposure": float(bpy.context.scene.view_settings.exposure),
        "world_color": tuple(bg.inputs["Color"].default_value) if bg is not None else None,
        "world_strength": float(bg.inputs["Strength"].default_value) if bg is not None else None,
    }


def restore_scene_state(state, objects, camera):
    for obj in objects:
        matrix = state["object_matrices"].get(obj.name)
        if matrix is not None:
            obj.matrix_world = matrix.copy()
    camera.matrix_world = state["camera_matrix"].copy()
    camera.data.lens = state["camera_lens"]
    camera.data.shift_x = state["camera_shift_x"]
    camera.data.shift_y = state["camera_shift_y"]
    for item in state["lights"]:
        obj = item["object"]
        if obj.name not in bpy.data.objects:
            continue
        obj.matrix_world = item["matrix"].copy()
        if hasattr(obj.data, "energy"):
            obj.data.energy = item["energy"]
        if getattr(obj.data, "color", None) is not None:
            obj.data.color = item["color"]
        if item["size"] is not None and hasattr(obj.data, "size"):
            obj.data.size = item["size"]
        if item["size_y"] is not None and hasattr(obj.data, "size_y"):
            obj.data.size_y = item["size_y"]
    bpy.context.scene.view_settings.exposure = state["exposure"]
    bg = find_background_node(bpy.context.scene.world)
    if bg is not None and state["world_color"] is not None:
        bg.inputs["Color"].default_value = state["world_color"]
        bg.inputs["Strength"].default_value = state["world_strength"]
    bpy.context.view_layer.update()


def cleanup_black_dot_objects():
    for obj in list(bpy.data.objects):
        if (
            obj.name in {"UNIFIED_BLACK_DOT", "UNIFIED_BLACK_DOT_LOCAL"}
            or obj.name.startswith("UNIFIED_BLACK_DOT.")
            or obj.name.startswith("UNIFIED_BLACK_DOT_LOCAL.")
        ):
            bpy.data.objects.remove(obj, do_unlink=True)


def build_two_sided_camera_presets(objects, lens, shift_y, preset_config=None):
    preset_config = preset_config or {}
    bb_min, bb_max = world_bbox(objects)
    center = (bb_min + bb_max) * 0.5
    span = bb_max - bb_min
    max_dim = max(float(abs(span.x)), float(abs(span.y)), float(abs(span.z)), 1e-6)
    focus_target = center + Vector((0.0, 0.015 * max_dim, 0.0))
    roll_deg = float(preset_config.get("camera_roll_deg", 0.0))
    front_offset = preset_config.get("camera_front_offset", (-0.08, -0.42, 2.58))
    back_offset = preset_config.get("camera_back_offset", (0.08, -0.42, -2.58))

    def make_preset(name, offset, side_shift):
        offset_vec = Vector(offset) * max_dim
        location = center + offset_vec
        direction = focus_target - location
        rotation = direction.to_track_quat("-Z", "Y").to_euler()
        if roll_deg:
            rotation.rotate_axis("Z", math.radians(roll_deg))
        return {
            "name": name,
            "location": location,
            "rotation": rotation,
            "lens": lens,
            "shift_x": 0.0,
            "shift_y": side_shift,
        }

    return {
        "front": make_preset("front", front_offset, shift_y),
        "back": make_preset("back", back_offset, -shift_y * 0.45),
    }


def apply_camera_preset(camera, preset):
    camera.location = preset["location"].copy()
    camera.rotation_euler = preset["rotation"].copy()
    camera.data.lens = float(preset["lens"])
    camera.data.shift_x = float(preset.get("shift_x", 0.0))
    camera.data.shift_y = float(preset.get("shift_y", 0.0))
    bpy.context.view_layer.update()


def configure_support_for_view_side(objects, side):
    bb_min, bb_max = world_bbox(objects)
    span = bb_max - bb_min
    max_dim = max(float(abs(span.x)), float(abs(span.y)), float(abs(span.z)), 1e-6)
    if side == "back":
        support_z = bb_max.z + 0.05 * max_dim
    else:
        support_z = bb_min.z - 0.05 * max_dim
    for name in ("UNIFIED_REFERENCE_BACKDROP", "UNIFIED_QC75244_REFERENCE_FLOOR"):
        obj = bpy.data.objects.get(name)
        if obj is not None and obj.type == "MESH":
            obj.location.z = support_z
            obj.hide_render = False
            obj.hide_viewport = False
    wall = bpy.data.objects.get("UNIFIED_QC75244_REFERENCE_WALL")
    if wall is not None and side == "back":
        wall.hide_render = True
        wall.hide_viewport = True
    elif wall is not None:
        wall.hide_render = False
        wall.hide_viewport = False
    bpy.context.view_layer.update()


def build_object_view_transform(args, defect):
    enabled = args.object_transform_mode == "keep_camera"
    rotation = args.object_rotate_deg
    if rotation is None:
        rotation = [180.0, 0.0, 0.0] if enabled and defect.get("anchor_side") == "back" else [0.0, 0.0, 0.0]
    translation = [float(value) for value in (args.object_translate or [0.0, 0.0, 0.0])]
    return {
        "enabled": bool(enabled),
        "mode": args.object_transform_mode,
        "camera_moved_for_defect_side": False if enabled else None,
        "camera_side": args.object_transform_camera_side,
        "physical_anchor_side": defect.get("anchor_side"),
        "rotation_degrees_xyz": [float(value) for value in rotation],
        "translation_xyz": translation,
        "pivot_policy": "product_bbox_center",
        "environment_transform": "none",
        "default_backside_operation": bool(
            enabled
            and defect.get("anchor_side") == "back"
            and args.object_rotate_deg is None
            and all(abs(value) < 1e-9 for value in translation)
        ),
    }


def apply_object_view_transform(objects, defect, transform):
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
        name = defect.get(key)
        obj = bpy.data.objects.get(name) if name else None
        if obj is not None and obj not in transform_objects:
            transform_objects.append(obj)
    for obj in transform_objects:
        obj.matrix_world = matrix @ obj.matrix_world
    if defect.get("world_point"):
        world_point = matrix @ Vector(defect["world_point"])
        defect["world_point"] = [float(world_point.x), float(world_point.y), float(world_point.z)]
    if defect.get("world_normal"):
        world_normal = (matrix.to_3x3() @ Vector(defect["world_normal"])).normalized()
        defect["world_normal"] = [float(world_normal.x), float(world_normal.y), float(world_normal.z)]
    transform["pivot_world"] = [float(pivot.x), float(pivot.y), float(pivot.z)]
    transform["objects_transformed"] = [obj.name for obj in transform_objects]
    bpy.context.view_layer.update()


def refine_camera_shift_for_defect(camera, world_point, rng):
    scene = bpy.context.scene
    projected = world_to_camera_view(scene, camera, world_point)
    desired_x = max(0.28, min(0.72, 0.50 + rng.uniform(-0.10, 0.10)))
    desired_y = max(0.28, min(0.72, 0.50 + rng.uniform(-0.08, 0.08)))
    camera.data.shift_x += (float(projected.x) - desired_x) * 0.68
    camera.data.shift_y += (float(projected.y) - desired_y) * 0.68
    camera.data.shift_x = max(-0.22, min(0.22, camera.data.shift_x))
    camera.data.shift_y = max(-0.22, min(0.22, camera.data.shift_y))
    bpy.context.view_layer.update()
    return world_to_camera_view(scene, camera, world_point)


def apply_camera_jitter(camera, objects, side, world_point, rng, strength):
    if strength <= 0:
        return {"enabled": False}
    bb_min, bb_max = world_bbox(objects)
    span = bb_max - bb_min
    max_dim = max(float(abs(span.x)), float(abs(span.y)), float(abs(span.z)), 1e-6)
    side_sign = 1.0 if side == "front" else -1.0
    camera.location.x += rng.uniform(-0.040, 0.040) * max_dim * strength
    camera.location.y += rng.uniform(-0.040, 0.040) * max_dim * strength
    camera.location.z += rng.uniform(-0.055, 0.055) * max_dim * strength * side_sign
    camera.rotation_euler.rotate_axis("X", math.radians(rng.uniform(-1.8, 1.8) * strength))
    camera.rotation_euler.rotate_axis("Y", math.radians(rng.uniform(-1.2, 1.2) * strength))
    camera.rotation_euler.rotate_axis("Z", math.radians(rng.uniform(-2.4, 2.4) * strength))
    camera.data.lens += rng.uniform(-4.0, 3.0) * strength
    projected = refine_camera_shift_for_defect(camera, world_point, rng)
    return {
        "enabled": True,
        "defect_projected_xy": [float(projected.x), float(projected.y)],
        "camera_location": [float(v) for v in camera.location],
        "camera_rotation_euler": [float(v) for v in camera.rotation_euler],
        "lens": float(camera.data.lens),
        "shift_x": float(camera.data.shift_x),
        "shift_y": float(camera.data.shift_y),
    }


def apply_object_jitter(objects, rng, degrees):
    if degrees <= 0:
        return {"enabled": False}
    bb_min, bb_max = world_bbox(objects)
    center = (bb_min + bb_max) * 0.5
    rx = math.radians(rng.uniform(-degrees * 0.35, degrees * 0.35))
    ry = math.radians(rng.uniform(-degrees * 0.35, degrees * 0.35))
    rz = math.radians(rng.uniform(-degrees, degrees))
    rotation = Matrix.Rotation(rz, 4, "Z") @ Matrix.Rotation(ry, 4, "Y") @ Matrix.Rotation(rx, 4, "X")
    transform = Matrix.Translation(center) @ rotation @ Matrix.Translation(-center)
    for obj in objects:
        obj.matrix_world = transform @ obj.matrix_world
    bpy.context.view_layer.update()
    return {"enabled": True, "rotation_degrees": [math.degrees(rx), math.degrees(ry), math.degrees(rz)]}


def apply_light_jitter(state, rng, strength):
    if strength <= 0:
        return {"enabled": False, "lights": []}
    summary = []
    key_index = 0
    for idx, item in enumerate(state["lights"]):
        obj = item["object"]
        if obj.name not in bpy.data.objects:
            continue
        light = obj.data
        is_area = getattr(light, "type", "") == "AREA"
        key_bias = 1.0
        if is_area:
            key_bias = 1.0 + (0.14 if idx == key_index else -0.04) * rng.uniform(-1.0, 1.0) * strength
            obj.rotation_euler.rotate_axis("X", math.radians(rng.uniform(-2.2, 2.2) * strength))
            obj.rotation_euler.rotate_axis("Y", math.radians(rng.uniform(-2.2, 2.2) * strength))
            obj.rotation_euler.rotate_axis("Z", math.radians(rng.uniform(-3.0, 3.0) * strength))
            obj.location.x += rng.uniform(-0.025, 0.025) * strength
            obj.location.y += rng.uniform(-0.025, 0.025) * strength
            obj.location.z += rng.uniform(-0.018, 0.018) * strength
        energy_scale = max(0.55, 1.0 + rng.uniform(-0.18, 0.18) * strength) * key_bias
        if hasattr(light, "energy"):
            light.energy = item["energy"] * energy_scale
        if getattr(light, "color", None) is not None:
            cool = rng.uniform(-0.035, 0.035) * strength
            base = item["color"]
            light.color = (
                max(0.0, min(1.0, base[0] - cool * 0.40)),
                max(0.0, min(1.0, base[1] - cool * 0.12)),
                max(0.0, min(1.0, base[2] + cool * 0.55)),
            )
        summary.append({"name": obj.name, "energy_scale": float(energy_scale)})
    scene = bpy.context.scene
    scene.view_settings.exposure = state["exposure"] + rng.uniform(-0.10, 0.10) * strength
    bg = find_background_node(scene.world)
    if bg is not None and state["world_strength"] is not None:
        bg.inputs["Strength"].default_value = max(0.0, state["world_strength"] * (1.0 + rng.uniform(-0.18, 0.18) * strength))
    bpy.context.view_layer.update()
    return {"enabled": True, "lights": summary, "exposure": float(scene.view_settings.exposure)}


def setup_p101040(args, preset):
    blend_path = resolve_path(args.blend, preset["blend"])
    stl_path = resolve_path(args.stl, preset["stl"])
    bpy.ops.wm.open_mainfile(filepath=str(blend_path))
    ensure_background_support(base_color=(0.93, 0.94, 0.96, 1.0), roughness=0.78)
    tune_reference_lighting_for_blue()
    reference_objects = pick_primary_mesh_objects()
    ensure_camera_for_objects(reference_objects, args.width, args.height, lens=118.0, shift_y=0.0)
    for obj in reference_objects:
        obj.hide_render = True
        obj.hide_viewport = True
    imported = import_stl(stl_path)
    fit_objects_to_reference(imported, reference_objects)
    material_info = assign_bluer_material(imported, reference_objects)
    external_material_info = apply_external_visual_material(imported, args.material_json)
    if external_material_info is not None:
        material_info = {"default_material_info": material_info, "external_material_override": external_material_info}
    camera = ensure_camera_for_objects(imported, args.width, args.height, lens=preset["camera_lens"], shift_y=preset["camera_shift_y"])
    camera.data.lens = preset["camera_lens"]
    return {
        "objects": imported,
        "camera": camera,
        "source_paths": {"blend": str(blend_path), "stl": str(stl_path)},
        "material_info": material_info,
    }


def setup_qc71336(args, preset):
    blend_path = resolve_path(args.blend, preset["blend"])
    model_blend = resolve_path(args.model_blend, preset["model_blend"])
    bpy.ops.wm.open_mainfile(filepath=str(blend_path))
    ensure_background_support()
    tune_reference_lighting_for_qc71336_white()
    primary_objects = pick_primary_mesh_objects()
    ensure_camera_for_objects(primary_objects, args.width, args.height, lens=82.0, shift_y=0.085)
    for obj in primary_objects:
        obj.hide_render = True
        obj.hide_viewport = True
    imported = append_blend_objects(model_blend, object_keywords=("QC8-8511-000N301002ST0101",))
    fit_objects_to_reference(imported, primary_objects, scale_factor=1.0)
    original_materials = summarize_materials(imported)
    if preset.get("use_gray_override"):
        material_name = apply_gray_override_material(imported)
        material_info = {"gray_override_material": material_name}
    else:
        material_info = tune_prebuilt_white_materials(imported)
    external_material_info = apply_external_visual_material(imported, args.material_json)
    if external_material_info is not None:
        material_info = {"default_material_info": material_info, "external_material_override": external_material_info}
    camera = ensure_camera_for_objects(imported, args.width, args.height, lens=preset["camera_lens"], shift_y=preset["camera_shift_y"])
    camera.data.lens = preset["camera_lens"]
    return {
        "objects": imported,
        "camera": camera,
        "source_paths": {"blend": str(blend_path), "model_blend": str(model_blend)},
        "material_info": material_info,
        "original_materials": original_materials,
    }


def setup_qc75244(args, preset):
    blend_path = resolve_path(args.blend, preset["blend"])
    stl_path = resolve_path(args.stl, preset["stl"])
    bpy.ops.wm.open_mainfile(filepath=str(blend_path))
    reference_primary = get_primary_object()
    primary_obj = import_replacement_stl(stl_path, reference_primary) if stl_path.exists() else reference_primary
    hide_non_primary_meshes(primary_obj)
    ensure_clean_reference_support(primary_obj)
    camera = ensure_camera_for_objects([primary_obj], args.width, args.height, lens=preset["camera_lens"], shift_y=preset["camera_shift_y"])
    back_only = tuple(args.anchor_sides or ()) == ("back",)
    tune_reference_lighting_for_qc75244_white(base_energy_multiplier=1.5 if back_only else 1.0)
    material_info = assign_qc75244_white_material(primary_obj)
    external_material_info = apply_external_visual_material([primary_obj], args.material_json)
    if external_material_info is not None:
        material_info = {"default_material_info": material_info, "external_material_override": external_material_info}
    camera.data.lens = preset["camera_lens"]
    bpy.context.view_layer.update()
    return {
        "objects": [primary_obj],
        "camera": camera,
        "source_paths": {"blend": str(blend_path), "stl": str(stl_path)},
        "material_info": material_info,
    }


def configure_render(samples, width, height):
    scene = bpy.context.scene
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    return configure_cycles_gpu(samples)


def sample_anchor(objects, camera_presets, rng, allowed_sides, preset_config=None):
    preset_config = preset_config or {}
    placement_control = EXTERNAL_PLACEMENT_CONTROL or {}
    safe_windows = placement_control.get("safe_anchor_windows")
    if safe_windows is None and placement_control.get("use_preset_safe_anchor_windows"):
        safe_windows = preset_config.get("safe_anchor_windows")
    candidates = []
    for obj in objects:
        mesh = obj.data
        if not mesh.polygons:
            continue
        world_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        bb_min = Vector((min(v.x for v in world_corners), min(v.y for v in world_corners), min(v.z for v in world_corners)))
        bb_max = Vector((max(v.x for v in world_corners), max(v.y for v in world_corners), max(v.z for v in world_corners)))
        center = (bb_min + bb_max) * 0.5
        dims = bb_max - bb_min
        half_x = max(abs(float(dims.x)) * 0.5, 1e-6)
        half_y = max(abs(float(dims.y)) * 0.5, 1e-6)
        half_z = max(abs(float(dims.z)) * 0.5, 1e-6)
        areas = sorted(max(float(poly.area), 1e-10) for poly in mesh.polygons)
        area_floor = max(areas[min(len(areas) - 1, max(0, int(len(areas) * 0.22)))] * 0.55, areas[-1] * 0.00005)
        normal_matrix = obj.matrix_world.to_3x3()
        for poly in mesh.polygons:
            world_center = obj.matrix_world @ poly.center
            normal = (normal_matrix @ poly.normal).normalized()
            side = "front" if normal.z >= 0.62 else ("back" if normal.z <= -0.62 else None)
            if side not in allowed_sides:
                continue
            local_x = float(world_center.x - center.x) / half_x
            local_y = float(world_center.y - center.y) / half_y
            local_z = float(world_center.z - center.z) / half_z
            if abs(local_x) > 0.90 or abs(local_y) > 0.92:
                continue
            if safe_windows and not anchor_in_safe_window(local_x, local_y, local_z, normal, safe_windows):
                continue
            if max(float(poly.area), 1e-10) < area_floor:
                continue
            camera_location = camera_presets[side]["location"]
            view_alignment = float(normal.dot((camera_location - world_center).normalized()))
            if view_alignment < 0.20:
                continue
            center_score = max(0.0, 1.0 - (abs(local_x) * 0.58 + abs(local_y) * 0.40))
            z_score = min(1.0, abs(local_z))
            score = center_score * 1.35 + z_score * 0.42 + min(float(poly.area) / area_floor, 3.0) * 0.10 + rng.random() * 0.25
            candidates.append({
                "object": obj,
                "polygon_index": poly.index,
                "world_point": world_center,
                "world_normal": normal,
                "side": side,
                "score": score,
                "local_xyz": [local_x, local_y, local_z],
                "view_alignment": view_alignment,
                "poly_area": float(poly.area),
            })
    if not candidates:
        raise RuntimeError(f"No stable front/back anchor found for sides={allowed_sides}.")
    candidates.sort(key=lambda item: item["score"], reverse=True)
    shortlist = candidates[: min(48, len(candidates))]
    floor = shortlist[-1]["score"]
    weights = [max(item["score"] - floor + 0.02, 0.002) for item in shortlist]
    return rng.choices(shortlist, weights=weights, k=1)[0]


def anchor_in_safe_window(local_x, local_y, local_z, normal, safe_windows):
    for window in safe_windows:
        x_min, x_max = window.get("local_x", (-1.0, 1.0))
        y_min, y_max = window.get("local_y", (-1.0, 1.0))
        z_abs_min = float(window.get("local_z_abs_min", 0.0))
        normal_z_min = float(window.get("normal_z_min", 0.0))
        if not (float(x_min) <= local_x <= float(x_max)):
            continue
        if not (float(y_min) <= local_y <= float(y_max)):
            continue
        if abs(local_z) < z_abs_min:
            continue
        if abs(float(normal.z)) < normal_z_min:
            continue
        return True
    return False


def set_embedded_blend(mat, alpha):
    bsdf = find_principled(mat)
    if bsdf is not None and "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = alpha
    mat.blend_method = "BLEND"
    if hasattr(mat, "show_transparent_back"):
        mat.show_transparent_back = False


def build_black_dot_materials(model_name, rng):
    if model_name == "P101040_blue":
        dark = rng.uniform(0.012, 0.028)
        warmth = rng.uniform(0.001, 0.008)
        tone_variant = rng.choice(["charcoal", "brown_black", "blue_black"])
        if tone_variant == "brown_black":
            center_color = (dark + warmth * 1.2, dark * rng.uniform(0.76, 0.90), dark * rng.uniform(0.58, 0.74), 1.0)
        elif tone_variant == "blue_black":
            center_color = (dark + warmth * 0.5, dark * rng.uniform(0.70, 0.84), dark * rng.uniform(0.82, 1.02), 1.0)
        else:
            center_color = (dark + warmth, dark * rng.uniform(0.78, 0.92), dark * rng.uniform(0.68, 0.82), 1.0)
        edge_level = dark * rng.uniform(1.05, 1.35)
        edge_color = (edge_level + warmth, edge_level * 0.92, edge_level * 0.82, 1.0)
        local_color = (edge_level * 1.8 + warmth, edge_level * 1.4, edge_level * 1.1, 1.0)
        center = make_principled_material("UNIFIED_BLACK_DOT_CENTER", center_color, rng.uniform(0.80, 0.94), rng.uniform(0.00, 0.035))
        edge = make_principled_material("UNIFIED_BLACK_DOT_EDGE", edge_color, rng.uniform(0.76, 0.92), rng.uniform(0.00, 0.028))
        local = make_principled_material("UNIFIED_BLACK_DOT_LOCAL_PATCH_MAT", local_color, rng.uniform(0.78, 0.94), rng.uniform(0.01, 0.06), alpha=rng.uniform(0.006, 0.016))
        set_embedded_blend(center, rng.uniform(1.00, 1.22))
        set_embedded_blend(edge, rng.uniform(0.12, 0.20))
        add_noise_bump(center, scale=950.0, strength=0.0018, distance=0.0008)
        add_noise_bump(edge, scale=820.0, strength=0.0014, distance=0.0007)
        add_noise_bump(local, scale=95.0, strength=0.0060, distance=0.003)
        return center, edge, local
    center = make_principled_material("UNIFIED_BLACK_DOT_CENTER", (0.022, 0.020, 0.019, 1.0), 0.82, 0.018)
    edge = make_principled_material("UNIFIED_BLACK_DOT_EDGE", (0.060, 0.056, 0.052, 1.0), 0.86, 0.012)
    patch = make_principled_material("UNIFIED_BLACK_DOT_LOCAL_PATCH_MAT", (0.24, 0.235, 0.23, 1.0), 0.96, 0.0, alpha=0.030)
    add_noise_bump(center, scale=980.0, strength=0.0008, distance=0.0005)
    add_noise_bump(edge, scale=920.0, strength=0.00055, distance=0.00045)
    add_noise_bump(patch, scale=760.0, strength=0.00035, distance=0.00035)
    return center, edge, patch


def create_local_patch(model_name, world_point, world_normal, radius, mat, rng):
    vertex_count = rng.randint(20, 32) if model_name == "P101040_blue" else rng.randint(18, 26)
    squash_x = rng.uniform(0.78, 1.22) if model_name == "P101040_blue" else rng.uniform(0.84, 1.14)
    squash_y = rng.uniform(0.78, 1.22) if model_name == "P101040_blue" else rng.uniform(0.84, 1.14)
    z_inner = rng.uniform(0.0, radius * 0.002) if model_name == "P101040_blue" else 0.0
    verts = [(0.0, 0.0, z_inner)]
    inner_ring = []
    outer_ring = []
    wave_freq = rng.uniform(2.0, 3.6) if model_name == "QC71336_white" else rng.uniform(2.0, 4.0)
    wave_phase = rng.uniform(0.0, math.tau)
    for idx in range(vertex_count):
        angle = math.tau * idx / vertex_count
        wave_amplitude = 0.06 if model_name == "QC71336_white" else 0.10
        wave = 1.0 + wave_amplitude * math.sin(angle * wave_freq + wave_phase)
        if model_name == "QC71336_white":
            inner_radius = radius * rng.uniform(0.36, 0.52) * wave
            outer_radius = radius * rng.uniform(0.82, 1.06) * wave
        else:
            inner_radius = radius * rng.uniform(0.42, 0.62) * wave
            outer_radius = radius * rng.uniform(0.86, 1.30) * wave
        inner_ring.append(len(verts))
        verts.append((math.cos(angle) * inner_radius * squash_x, math.sin(angle) * inner_radius * squash_y, z_inner))
        outer_ring.append(len(verts))
        verts.append((math.cos(angle) * outer_radius * squash_x, math.sin(angle) * outer_radius * squash_y, 0.0))
    faces = []
    for idx in range(vertex_count):
        nxt = (idx + 1) % vertex_count
        faces.append((0, inner_ring[idx], inner_ring[nxt]))
        faces.append((inner_ring[idx], outer_ring[idx], outer_ring[nxt], inner_ring[nxt]))
    mesh = bpy.data.meshes.new("UNIFIED_BLACK_DOT_LOCAL_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    patch = bpy.data.objects.new("UNIFIED_BLACK_DOT_LOCAL", mesh)
    bpy.context.collection.objects.link(patch)
    patch_offset_factor = 0.004 if model_name == "QC71336_white" else 0.010
    patch.location = world_point + world_normal * max(radius * patch_offset_factor, 1e-5)
    patch.rotation_euler = world_normal.to_track_quat("Z", "Y").to_euler()
    patch.rotation_euler.rotate_axis("Z", rng.uniform(0.0, math.tau))
    patch.data.materials.append(mat)
    patch["category_id"] = 1
    patch["class_name"] = "local_contamination"
    return patch


def create_black_dot_mesh(model_name, radius, depth, rng):
    vertex_count = rng.randint(14, 26) if model_name == "P101040_blue" else rng.randint(11, 17)
    squash_x = rng.uniform(0.64, 1.28) if model_name == "P101040_blue" else rng.uniform(0.68, 1.26)
    squash_y = rng.uniform(0.64, 1.28) if model_name == "P101040_blue" else rng.uniform(0.70, 1.22)
    top_z = depth * (rng.uniform(0.18, 0.36) if model_name == "P101040_blue" else rng.uniform(0.16, 0.28))
    bottom_z = -depth * (rng.uniform(0.50, 0.76) if model_name == "P101040_blue" else rng.uniform(0.42, 0.62))
    wave_freq = rng.uniform(2.2, 5.2) if model_name == "QC71336_white" else rng.uniform(2.0, 5.2)
    wave_phase = rng.uniform(0.0, math.tau)
    verts = [(0.0, 0.0, top_z), (0.0, 0.0, bottom_z)]
    inner_ring = []
    top_ring = []
    bottom_ring = []
    for idx in range(vertex_count):
        angle = math.tau * idx / vertex_count
        wave = 1.0 + 0.12 * math.sin(angle * wave_freq + wave_phase)
        if model_name == "QC71336_white":
            local_radius = radius * rng.uniform(0.66, 1.12) * wave
        else:
            local_radius = radius * rng.uniform(0.62, 1.28) * wave
        x = math.cos(angle) * local_radius * squash_x
        y = math.sin(angle) * local_radius * squash_y
        inner_radius = local_radius * (rng.uniform(0.28, 0.46) if model_name == "QC71336_white" else rng.uniform(0.30, 0.50))
        inner_ring.append(len(verts))
        inner_top_scale = rng.uniform(0.82, 1.04) if model_name == "QC71336_white" else rng.uniform(0.84, 1.08)
        verts.append((math.cos(angle) * inner_radius * squash_x, math.sin(angle) * inner_radius * squash_y, top_z * inner_top_scale))
        top_ring.append(len(verts))
        top_outer_scale = rng.uniform(0.38, 0.76) if model_name == "QC71336_white" else rng.uniform(0.48, 0.88)
        verts.append((x, y, top_z * top_outer_scale))
        bottom_ring.append(len(verts))
        bottom_xy_scale = rng.uniform(0.80, 1.06) if model_name == "QC71336_white" else rng.uniform(0.76, 1.06)
        verts.append((x * bottom_xy_scale, y * bottom_xy_scale, bottom_z))
    faces = []
    material_indices = []
    for idx in range(vertex_count):
        nxt = (idx + 1) % vertex_count
        faces.append((0, inner_ring[idx], inner_ring[nxt]))
        material_indices.append(0)
        faces.append((inner_ring[idx], top_ring[idx], top_ring[nxt], inner_ring[nxt]))
        material_indices.append(1)
        faces.append((1, bottom_ring[nxt], bottom_ring[idx]))
        material_indices.append(1)
        faces.append((top_ring[idx], bottom_ring[idx], bottom_ring[nxt], top_ring[nxt]))
        material_indices.append(1)
    mesh = bpy.data.meshes.new("UNIFIED_BLACK_DOT_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    for poly, material_index in zip(mesh.polygons, material_indices):
        poly.material_index = material_index
    return mesh


def add_black_dot(model_name, objects, camera_presets, radius_range, depth_range, rng, allowed_sides,
                  preset_config=None):
    preset_config = preset_config or {}
    anchor = sample_anchor(objects, camera_presets, rng, allowed_sides, preset_config=preset_config)
    bb_min, bb_max = world_bbox(objects)
    dims = bb_max - bb_min
    axis_values = {"x": abs(float(dims.x)), "y": abs(float(dims.y)), "z": abs(float(dims.z))}
    reference_axes = preset_config.get("size_reference_axes")
    if reference_axes:
        size_ref = max(axis_values[axis] for axis in reference_axes)
    else:
        size_ref = max(axis_values.values())
    size_ref = max(size_ref, 1e-6)
    radius = size_ref * rng.uniform(radius_range[0], radius_range[1])
    depth = size_ref * rng.uniform(depth_range[0], depth_range[1])
    materials = build_black_dot_materials(model_name, rng)
    patch_radius = radius * (rng.uniform(1.12, 1.26) if model_name == "QC71336_white" else rng.uniform(1.12, 1.85))
    patch = create_local_patch(model_name, anchor["world_point"], anchor["world_normal"], patch_radius, materials[2], rng)
    mesh = create_black_dot_mesh(model_name, radius, depth, rng)
    dot = bpy.data.objects.new("UNIFIED_BLACK_DOT", mesh)
    bpy.context.collection.objects.link(dot)
    embed_offset = max(depth * 0.085, radius * 0.009) if model_name == "QC71336_white" else max(depth * 0.11, radius * 0.010)
    if model_name == "P101040_blue":
        embed_offset = max(depth * 0.20, radius * 0.016)
    dot.location = anchor["world_point"] - anchor["world_normal"] * embed_offset
    dot.rotation_euler = anchor["world_normal"].to_track_quat("Z", "Y").to_euler()
    dot.rotation_euler.rotate_axis("Z", rng.uniform(0.0, math.tau))
    dot.pass_index = 1
    patch.pass_index = 0
    dot.data.materials.append(materials[0])
    dot.data.materials.append(materials[1])
    dot["category_id"] = 2
    dot["class_name"] = "black_dot"
    dot["defect_type"] = "black_dot"
    dot["defect_type_canonical"] = "black_dot"
    patch["support_artifact_role"] = "black_dot_coupling_patch"
    bpy.context.view_layer.update()
    return {
        "dot_object": dot.name,
        "patch_object": patch.name,
        "radius": float(radius),
        "depth": float(depth),
        "world_point": [float(v) for v in anchor["world_point"]],
        "world_normal": [float(v) for v in anchor["world_normal"]],
        "anchor_side": anchor["side"],
        "anchor_polygon_index": int(anchor["polygon_index"]),
        "anchor_score": float(anchor["score"]),
        "anchor_local_xyz": anchor["local_xyz"],
        "anchor_view_alignment": float(anchor["view_alignment"]),
    }


def load_mask_binary(mask_path):
    image = bpy.data.images.load(str(mask_path), check_existing=False)
    try:
        width, height = image.size
        pixels = list(image.pixels[:])
        binary = build_binary_mask_pixels(pixels, width, height, threshold=0.5)
        bbox = bbox_from_binary_mask(binary, width, height)
        save_binary_mask_image(mask_path, binary, width, height, "UNIFIED_BLACK_DOT_MASK_EXPORT")
        return binary, bbox, width, height
    finally:
        bpy.data.images.remove(image)


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
        "xywh": [int(min_x), int(min_y), int(max_x - min_x + 1), int(max_y - min_y + 1)],
        "area_pixels": int(sum(binary)),
    }


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
    try:
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

            def set_pixel(x, y_top, color):
                if x < 0 or x >= width or y_top < 0 or y_top >= height:
                    return
                y_bottom = height - 1 - y_top
                base = (y_bottom * width + x) * 4
                overlay_pixels[base] = color[0]
                overlay_pixels[base + 1] = color[1]
                overlay_pixels[base + 2] = color[2]
                overlay_pixels[base + 3] = 1.0

            for x in range(min_x, max_x + 1):
                set_pixel(x, min_y, (0.1, 1.0, 0.1))
                set_pixel(x, max_y, (0.1, 1.0, 0.1))
            for y in range(min_y, max_y + 1):
                set_pixel(min_x, y, (0.1, 1.0, 0.1))
                set_pixel(max_x, y, (0.1, 1.0, 0.1))
        save_image_from_rgba_pixels(overlay_path, width, height, overlay_pixels, image_name)
    finally:
        bpy.data.images.remove(rgb_image)


def make_emission_mask_material(name="UNIFIED_BLACK_DOT_MASK_MAT"):
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.node_tree.nodes.clear()
    emission = mat.node_tree.nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    emission.inputs["Strength"].default_value = 1.0
    output = mat.node_tree.nodes.new("ShaderNodeOutputMaterial")
    mat.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return mat


def render_black_dot_binary_mask(mask_path, dot_object_name):
    scene = bpy.context.scene
    dot = bpy.data.objects.get(dot_object_name)
    if dot is None:
        raise RuntimeError(f"Black-dot object not found for mask render: {dot_object_name}")
    original_engine = scene.render.engine
    original_samples = int(getattr(scene.cycles, "samples", 1))
    original_adaptive = bool(getattr(scene.cycles, "use_adaptive_sampling", False))
    original_filepath = scene.render.filepath
    original_hide_render = {obj.name: bool(obj.hide_render) for obj in bpy.data.objects}
    original_materials = [mat for mat in dot.data.materials]
    bg = find_background_node(scene.world)
    original_bg_color = tuple(bg.inputs["Color"].default_value) if bg is not None else None
    original_bg_strength = float(bg.inputs["Strength"].default_value) if bg is not None else None
    try:
        for obj in bpy.data.objects:
            if obj.type == "MESH":
                obj.hide_render = obj.name == dot_object_name
        for obj in bpy.data.objects:
            if obj.type == "MESH":
                obj.hide_render = obj.name != dot_object_name
        dot.data.materials.clear()
        dot.data.materials.append(make_emission_mask_material())
        if bg is not None:
            bg.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
            bg.inputs["Strength"].default_value = 1.0
        scene.render.engine = "CYCLES"
        scene.cycles.samples = 1
        scene.cycles.use_adaptive_sampling = False
        render_still(mask_path)
    finally:
        scene.render.engine = original_engine
        scene.cycles.samples = original_samples
        scene.cycles.use_adaptive_sampling = original_adaptive
        scene.render.filepath = original_filepath
        if bg is not None and original_bg_color is not None:
            bg.inputs["Color"].default_value = original_bg_color
            bg.inputs["Strength"].default_value = original_bg_strength
        dot.data.materials.clear()
        for mat in original_materials:
            dot.data.materials.append(mat)
        for obj in bpy.data.objects:
            if obj.name in original_hide_render:
                obj.hide_render = original_hide_render[obj.name]
        bpy.context.view_layer.update()


def setup_model(args, preset):
    if args.model == "P101040_blue":
        return setup_p101040(args, preset)
    if args.model in {"QC71336_white", "QC71336_gray"}:
        return setup_qc71336(args, preset)
    if args.model == "QC75244_white":
        return setup_qc75244(args, preset)
    raise AssertionError(args.model)


def write_notes(output_dir, args, preset):
    lines = [
        "# Unified Reference Black-Dot Generation",
        "",
        f"- model: `{args.model}`",
        f"- num: `{args.num}`",
        f"- seed: `{args.seed}`",
        f"- anchor_sides: `{args.anchor_sides or preset['anchor_sides']}`",
        "- label policy: mask and YOLO bbox include the main black-dot object only; local patch is visual support.",
        "- camera, light, and optional object-pose jitter are sampled per accepted image.",
        "- by default only the first debug blend is saved when `--save_blend --save_blend_only_first` are used.",
    ]
    (output_dir / "notes.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    args = parse_args()
    apply_cli_safe_anchor_window(args)
    preset = MODEL_PRESETS[args.model]
    output_dir = mkdir(Path(args.output).resolve())
    rgb_dir = mkdir(output_dir / "rgb")
    mask_dir = mkdir(output_dir / "mask")
    overlay_dir = mkdir(output_dir / "overlay")
    label_dir = mkdir(output_dir / "labels_yolo")
    blend_dir = mkdir(output_dir / "blend_debug")

    samples = int(args.samples if args.samples is not None else preset["samples"])
    radius_range = (
        args.black_dot_radius_min_scale if args.black_dot_radius_min_scale is not None else preset["radius_scale"][0],
        args.black_dot_radius_max_scale if args.black_dot_radius_max_scale is not None else preset["radius_scale"][1],
    )
    depth_range = (
        args.black_dot_depth_min_scale if args.black_dot_depth_min_scale is not None else preset["depth_scale"][0],
        args.black_dot_depth_max_scale if args.black_dot_depth_max_scale is not None else preset["depth_scale"][1],
    )
    allowed_sides = tuple(args.anchor_sides or preset["anchor_sides"])

    setup = setup_model(args, preset)
    objects = setup["objects"]
    camera = setup["camera"]
    gpu_info = configure_render(samples, args.width, args.height)
    scene_state = snapshot_scene_state(objects, camera)
    metadata = {
        "script": str(Path(__file__).resolve()),
        "schema_version": "unified_reference_blackdot_v1",
        "model_name": args.model,
        "geometry_profile": args.model,
        "appearance_profile": preset["appearance_profile"],
        "material_family": preset["material_family"],
        "defect_type": "black_dot",
        "defect_type_internal": "black_dot",
        "defect_type_canonical": "black_dot",
        "defect_family": "embedded_internal",
        "support_artifacts": ["black_dot_coupling_patch"],
        "label_policy": "mask_main_defect_only",
        "source_paths": setup["source_paths"],
        "material_info": setup.get("material_info"),
        "render_width": args.width,
        "render_height": args.height,
        "cycles_samples": samples,
        "render_device": gpu_info,
        "radius_scale_range": radius_range,
        "depth_scale_range": depth_range,
        "anchor_sides": allowed_sides,
        "samples": [],
        "failures": [],
    }

    pack_error = None
    accepted = 0
    frame_index = args.start_index
    total_attempts = 0
    while accepted < args.num and total_attempts < args.num * max(1, args.max_attempts_per_image):
        total_attempts += 1
        image_index = frame_index
        rng = random.Random(args.seed + image_index * 1009 + total_attempts)
        restore_scene_state(scene_state, objects, camera)
        cleanup_black_dot_objects()
        object_jitter = apply_object_jitter(objects, rng, args.object_jitter_degrees)
        active_camera_presets = build_two_sided_camera_presets(
            objects,
            preset["camera_lens"],
            preset["camera_shift_y"],
            preset,
        )
        try:
            defect = add_black_dot(
                args.model,
                objects,
                active_camera_presets,
                radius_range,
                depth_range,
                rng,
                allowed_sides,
                preset,
            )
            view_transform = build_object_view_transform(args, defect)
            camera_side = view_transform["camera_side"] if view_transform["enabled"] else defect["anchor_side"]
            apply_camera_preset(camera, active_camera_presets[camera_side])
            configure_support_for_view_side(objects, camera_side)
            if view_transform["enabled"]:
                camera_jitter = {"enabled": False, "reason": "object_transform_keep_camera"}
                light_jitter = {"enabled": False, "reason": "object_transform_keep_camera"}
                apply_object_view_transform(objects, defect, view_transform)
            else:
                camera_jitter = apply_camera_jitter(
                    camera,
                    objects,
                    defect["anchor_side"],
                    Vector(defect["world_point"]),
                    rng,
                    args.camera_jitter_strength,
                )
                light_jitter = apply_light_jitter(scene_state, rng, args.light_jitter_strength)
            projected = world_to_camera_view(bpy.context.scene, camera, Vector(defect["world_point"]))
            if projected.z <= 0.0 or not (0.06 <= projected.x <= 0.94 and 0.06 <= projected.y <= 0.94):
                raise RuntimeError(f"defect outside camera frame after jitter: {[projected.x, projected.y, projected.z]}")

            rgb_path = rgb_dir / f"{image_index:06d}.png"
            mask_path = mask_dir / f"{image_index:06d}.png"
            overlay_path = overlay_dir / f"{image_index:06d}.png"
            label_path = label_dir / f"{image_index:06d}.txt"
            render_still(rgb_path)
            render_black_dot_binary_mask(mask_path, defect["dot_object"])
            binary, bbox, mask_width, mask_height = load_mask_binary(mask_path)
            if bbox is None or bbox["xywh"][2] <= 0 or bbox["xywh"][3] <= 0:
                raise RuntimeError("black dot mask is empty after render")
            save_mask_overlay(
                rgb_path,
                overlay_path,
                binary,
                mask_width,
                mask_height,
                bbox,
                "UNIFIED_BLACK_DOT_OVERLAY_EXPORT",
            )
            yolo = bbox_to_yolo(bpy.context.scene, bbox)
            label_text = f"0 {yolo[0]:.6f} {yolo[1]:.6f} {yolo[2]:.6f} {yolo[3]:.6f}\n"
            label_path.write_text(label_text, encoding="utf-8")

            blend_rel = None
            if args.save_blend and (not args.save_blend_only_first or accepted == 0):
                blend_path = blend_dir / f"{image_index:06d}_scene.blend"
                pack_error = save_blend_copy(blend_path)
                blend_rel = str(blend_path.relative_to(output_dir))

            metadata["samples"].append({
                "image_id": f"{image_index:06d}",
                "rgb": str(rgb_path.relative_to(output_dir)),
                "mask": str(mask_path.relative_to(output_dir)),
                "overlay": str(overlay_path.relative_to(output_dir)),
                "label_yolo": str(label_path.relative_to(output_dir)),
                "blend_file": blend_rel,
                "has_defect": True,
                "defect_type": "black_dot",
                "defect_type_internal": "black_dot",
                "defect_type_canonical": "black_dot",
                "defect_family": "embedded_internal",
                "support_artifacts": ["black_dot_coupling_patch"],
                "black_dot": defect,
                "bbox": bbox,
                "mask_width": mask_width,
                "mask_height": mask_height,
                "object_jitter": object_jitter,
                "camera_jitter": camera_jitter,
                "light_jitter": light_jitter,
                "view_transform": view_transform,
                "random_seed": args.seed + image_index * 1009 + total_attempts,
            })
            accepted += 1
            frame_index += 1
            print(f"[{accepted:04d}/{args.num:04d}] frame={image_index:06d} side={defect['anchor_side']} bbox={bbox['xywh'] if bbox else None}")
        except Exception as exc:
            metadata["failures"].append({
                "frame_index": image_index,
                "attempt": total_attempts,
                "error": str(exc),
            })
            if args.keep_failed_blend:
                fail_path = blend_dir / f"{image_index:06d}_failed_attempt_{total_attempts:03d}.blend"
                save_blend_copy(fail_path)
            frame_index += 1
            print(f"[skip {image_index:06d}] {exc}")

    metadata["num"] = len(metadata["samples"])
    metadata["total_attempts"] = total_attempts
    metadata["pack_error"] = pack_error
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    write_notes(output_dir, args, preset)
    print(f"Done. Accepted {accepted}/{args.num}. Output: {output_dir}")


if __name__ == "__main__":
    main()
