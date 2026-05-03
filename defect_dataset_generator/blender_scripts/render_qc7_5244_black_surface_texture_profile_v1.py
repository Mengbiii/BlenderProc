import blenderproc as bproc

import argparse
import json
import math
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

FOREIGN_MATERIAL_VISIBLE_RADIUS_FLOOR = 0.0115


DEFECT_CLASS_IDS = {
    "black_dot": 0,
    "foreign_material": 1,
    "splay": 2,
    "mixed_color_contamination": 3,
    "sink_mark": 4,
}

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = SCRIPT_ROOT / "config" / "generation_defaults_registry.json"
FORCE_GENERIC_CAMERA_KEY = "generic_force_camera"


def parse_args():
    parser = argparse.ArgumentParser(description="Generic first-pass main-plane defect renderer.")
    parser.add_argument("--blend", default=None)
    parser.add_argument("--model_blend", default=None)
    parser.add_argument("--stl", default=None)
    parser.add_argument("--output", required=True)
    parser.add_argument("--num", type=int, default=1)
    parser.add_argument("--start_index", type=int, default=0)
    parser.add_argument("--width", type=int, default=1536)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--seed", type=int, default=100)
    parser.add_argument("--target", required=True)
    parser.add_argument("--defect_type", required=True, choices=sorted(DEFECT_CLASS_IDS))
    parser.add_argument("--anchor_sides", nargs="+", choices=["front", "back", "side"], default=["front", "back"])
    parser.add_argument("--force_generic_camera", action="store_true")
    parser.add_argument("--force_generic_lighting", action="store_true")
    parser.add_argument("--preserve_materials", action="store_true")
    parser.add_argument("--material_profile", default=None)
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = argv[1:]
    return parser.parse_args(argv)


def main():
    args = parse_args()
    defaults = load_defaults()
    random.seed(args.seed)
    output_dir = Path(args.output).resolve()
    rgb_dir = mkdir(output_dir / "rgb")
    mask_dir = mkdir(output_dir / "mask")
    label_dir = mkdir(output_dir / "labels_yolo")

    bproc.init()
    product = load_scene_model(args)
    material_profile = load_material_profile(args.material_profile)
    ensure_material(product, args.target, defaults, preserve_existing=args.preserve_materials, material_profile=material_profile)
    if is_qc7_5244_black_target(args.target) and material_profile and material_profile.get("profile_name") == "qc7_5244_black_surface_texture_profile_v1":
        add_qc7_ribbed_border_surface_proxies(product, material_profile)
    scene_profile = inspect_scene_profile(args)
    camera = setup_camera(product, args.width, args.height, scene_profile)
    setup_lighting(product, camera, args.target)
    configure_render(args.width, args.height, args.samples)

    samples = []
    for local_index in range(args.num):
        sample_id = args.start_index + local_index
        rng = random.Random(args.seed + sample_id)
        cleanup_defects()
        defect = create_defect(product, args.target, args.defect_type, rng, args.anchor_sides, defaults)
        if not scene_profile["uses_existing_camera"]:
            position_camera_for_side(camera, product, defect["anchor_side"], args.target)
            apply_camera_domain_randomization(camera, product, defect["anchor_side"], args.target, rng)
        ensure_camera_backdrop(product, camera, args.target)
        setup_lighting(product, camera, args.target)
        rgb_path = rgb_dir / f"{sample_id:06d}.png"
        mask_path = mask_dir / f"{sample_id:06d}.png"
        label_path = label_dir / f"{sample_id:06d}.txt"
        render_rgb(rgb_path)
        bbox = bbox_from_object(camera, defect, args.width, args.height)
        render_mask(mask_path, product, defect)
        write_yolo_label(label_path, args.defect_type, bbox, args.width, args.height)
        samples.append(
            {
                "image_id": sample_id,
                "rgb": str(rgb_path.relative_to(output_dir)),
                "mask": str(mask_path.relative_to(output_dir)),
                "label_yolo": str(label_path.relative_to(output_dir)),
                "defect_type": args.defect_type,
                "defect_type_canonical": args.defect_type,
                "bbox": bbox,
                "anchor_side": defect.get("anchor_side"),
                "main_plane_axis": defect.get("main_plane_axis"),
                "placement_policy": defect.get("placement_policy"),
                "generic_backend": True,
                "quality_goal": "coverage_first_not_visual_realism",
                "seed": args.seed + sample_id,
            }
        )

    metadata = {
        "schema_version": "generic_main_plane_v0.1",
        "script": str(Path(__file__).resolve()),
        "target": args.target,
        "defect_type": args.defect_type,
        "placement_policy": placement_policy_for_target(args.target),
        "main_plane_axis_policy": main_plane_axis_policy_for_target(args.target),
        "product_bbox": product_bbox_metadata(product),
        "scene_profile": scene_profile,
        "source_paths": {"blend": args.blend, "stl": args.stl},
        "render_width": args.width,
        "render_height": args.height,
        "cycles_samples": args.samples,
        "seed": args.seed,
        "samples": samples,
        "notes": [
            "This fallback backend is for first-pass generation coverage only.",
            "Defects are simplified primitives placed on configured planar safe windows.",
        ],
        "defaults_registry": str(DEFAULTS_PATH),
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")


def mkdir(path):
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_defaults():
    if DEFAULTS_PATH.exists():
        with DEFAULTS_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_material_profile(path_value):
    if not path_value:
        return None
    path = Path(path_value).resolve()
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_scene_model(args):
    reference_objects = []
    if args.blend:
        blend_path = Path(args.blend).resolve()
        if blend_path.exists():
            bpy.ops.wm.open_mainfile(filepath=str(blend_path))
            if args.force_generic_camera:
                bpy.context.scene[FORCE_GENERIC_CAMERA_KEY] = True
            if is_qc71336_gray_target(args.target):
                ensure_background_support()
                tune_qc71336_gray_reference_lighting()
                reference_objects = pick_reference_mesh_objects()
    if args.model_blend:
        model_blend_path = Path(args.model_blend).resolve()
        if model_blend_path.exists():
            imported = append_blend_objects(model_blend_path, object_keywords=("QC8-8511-000N301002ST0101",))
            if reference_objects:
                fit_objects_to_reference(imported, reference_objects, scale_factor=1.0)
                for obj in reference_objects:
                    obj.hide_render = True
                    obj.hide_viewport = True
            imported.sort(key=lambda obj: len(obj.data.vertices), reverse=True)
            primary = imported[0]
            primary.name = f"GENERIC_TARGET_{args.target}"
            hide_other_meshes(primary)
            if is_qc71336_gray_target(args.target):
                apply_qc71336_gray_override_material(primary)
            return primary
    if args.stl:
        stl_path = Path(args.stl).resolve()
        if stl_path.exists():
            before = {obj.name for obj in bpy.data.objects}
            try:
                bpy.ops.wm.stl_import(filepath=str(stl_path))
            except Exception:
                bpy.ops.import_mesh.stl(filepath=str(stl_path))
            imported = [obj for obj in bpy.data.objects if obj.name not in before and obj.type == "MESH"]
            if imported:
                imported.sort(key=lambda obj: len(obj.data.vertices), reverse=True)
                primary = imported[0]
                primary.name = f"GENERIC_TARGET_{args.target}"
                hide_other_meshes(primary)
                center_object(primary)
                bpy.context.scene[FORCE_GENERIC_CAMERA_KEY] = True
                return primary
    meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError("No mesh model found from blend or stl input.")
    meshes.sort(key=lambda obj: len(obj.data.vertices), reverse=True)
    primary = meshes[0]
    hide_other_meshes(primary)
    center_object(primary)
    return primary


def hide_other_meshes(primary):
    for obj in bpy.data.objects:
        if obj.type == "MESH" and obj != primary and obj.name != "GENERIC_REFERENCE_BACKDROP":
            obj.hide_render = True
            obj.hide_viewport = True


def inspect_scene_profile(args):
    force_generic_camera = bool(bpy.context.scene.get(FORCE_GENERIC_CAMERA_KEY, False))
    existing_camera = bpy.context.scene.camera
    existing_lights = [
        obj
        for obj in bpy.data.objects
        if obj.type == "LIGHT" and not obj.name.startswith("GENERIC_") and not args.force_generic_lighting
    ]
    return {
        "uses_existing_camera": (
            not force_generic_camera and existing_camera is not None and not existing_camera.name.startswith("GENERIC_")
        ),
        "existing_camera": existing_camera.name if existing_camera is not None else None,
        "force_generic_camera": force_generic_camera,
        "force_generic_lighting": bool(args.force_generic_lighting),
        "uses_existing_lights": bool(existing_lights),
        "existing_lights": [obj.name for obj in existing_lights],
        "fallback_policy": "reuse_existing_scene_first_else_generic_camera_light; imported STL forces generic camera",
    }


def center_object(obj):
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    min_v, max_v = world_bbox(obj)
    center = (min_v + max_v) * 0.5
    obj.location -= center
    obj.select_set(False)


def pick_reference_mesh_objects():
    candidates = [obj for obj in bpy.data.objects if obj.type == "MESH" and not is_background_like(obj)]
    if not candidates:
        candidates = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    if not candidates:
        return []
    candidates.sort(key=lambda obj: (bbox_volume(obj), len(obj.data.vertices)), reverse=True)
    top_volume = max(bbox_volume(candidates[0]), 1e-9)
    return [obj for obj in candidates if bbox_volume(obj) >= top_volume * 0.15]


def bbox_volume(obj):
    min_v, max_v = world_bbox(obj)
    dims = max_v - min_v
    return max(float(abs(dims.x)), 1e-6) * max(float(abs(dims.y)), 1e-6) * max(float(abs(dims.z)), 1e-6)


def is_background_like(obj):
    name = obj.name.lower()
    return any(token in name for token in ("background", "backdrop", "floor", "plane", "wall"))


def world_bbox_many(objects):
    mins = []
    maxs = []
    for obj in objects:
        min_v, max_v = world_bbox(obj)
        mins.append(min_v)
        maxs.append(max_v)
    return (
        Vector((min(v.x for v in mins), min(v.y for v in mins), min(v.z for v in mins))),
        Vector((max(v.x for v in maxs), max(v.y for v in maxs), max(v.z for v in maxs))),
    )


def append_blend_objects(path, object_keywords=()):
    with bpy.data.libraries.load(str(path), link=False) as (data_from, data_to):
        data_to.objects = [name for name in data_from.objects if name]
    loaded = [obj for obj in data_to.objects if obj is not None]
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


def fit_objects_to_reference(imported_objects, reference_objects, scale_factor=1.0):
    if not imported_objects or not reference_objects:
        return
    ref_min, ref_max = world_bbox_many(reference_objects)
    src_min, src_max = world_bbox_many(imported_objects)
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
    src_min, src_max = world_bbox_many(imported_objects)
    src_center = (src_min + src_max) * 0.5
    offset = ref_center - src_center
    for obj in imported_objects:
        obj.location += offset
    bpy.context.view_layer.update()


def ensure_background_support():
    if bpy.data.objects.get("GENERIC_REFERENCE_BACKDROP") is not None:
        return
    bpy.ops.mesh.primitive_plane_add(size=20.0, location=(0.0, 0.0, -0.15))
    plane = bpy.context.active_object
    plane.name = "GENERIC_REFERENCE_BACKDROP"
    mat = make_basic_principled_material("GENERIC_REFERENCE_BACKDROP_MAT", (0.82, 0.825, 0.83, 1.0), 0.84, 0.06)
    plane.data.materials.append(mat)
    bpy.context.view_layer.update()


def ensure_camera_backdrop(product, camera, target):
    if not (is_qc7_5244_target(target) or is_ql3_target(target)):
        return
    for obj in list(bpy.data.objects):
        if obj.name.startswith("GENERIC_CAMERA_BACKDROP"):
            bpy.data.objects.remove(obj, do_unlink=True)
    min_v, max_v = world_bbox(product)
    center = (min_v + max_v) * 0.5
    dims = max_v - min_v
    max_dim = max(float(dims.x), float(dims.y), float(dims.z), 1.0)
    view_dir = (center - camera.location).normalized()
    location = center + view_dir * max_dim * 0.62
    bpy.ops.mesh.primitive_plane_add(size=max_dim * 3.2, location=location)
    plane = bpy.context.active_object
    plane.name = "GENERIC_CAMERA_BACKDROP"
    plane.rotation_euler = (-view_dir).to_track_quat("Z", "Y").to_euler()
    if is_qc7_5244_target(target):
        color = (0.74, 0.745, 0.748, 1.0)
        roughness = 0.92
    else:
        color = (0.76, 0.765, 0.768, 1.0)
        roughness = 0.90
    mat = make_basic_principled_material("GENERIC_CAMERA_BACKDROP_MAT", color, roughness, 0.035)
    plane.data.materials.append(mat)
    bpy.context.view_layer.update()


def find_principled(mat):
    if mat is None or not mat.use_nodes or mat.node_tree is None:
        return None
    return next((node for node in mat.node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None)


def set_principled_input(bsdf, names, value):
    for name in names if isinstance(names, (tuple, list)) else [names]:
        if name in bsdf.inputs:
            bsdf.inputs[name].default_value = value
            return True
    return False


def make_basic_principled_material(name, base_color, roughness, specular, alpha=1.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
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
    set_principled_input(bsdf, "Alpha", alpha)
    return mat


def add_noise_bump(mat, scale=520.0, strength=0.0018, distance=0.0006):
    bsdf = find_principled(mat)
    if bsdf is None:
        return
    tree = mat.node_tree
    noise = tree.nodes.new("ShaderNodeTexNoise")
    bump = tree.nodes.new("ShaderNodeBump")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 9.0
    noise.inputs["Roughness"].default_value = 0.55
    bump.inputs["Strength"].default_value = strength
    bump.inputs["Distance"].default_value = distance
    tree.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    tree.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


def find_background_node(world):
    if world is None or not world.use_nodes or world.node_tree is None:
        return None
    return world.node_tree.nodes.get("Background")


def apply_qc71336_gray_override_material(obj):
    mat = make_basic_principled_material("GENERIC_QC71336_GRAY_OVERRIDE", (0.445, 0.438, 0.432, 1.0), 0.76, 0.26)
    add_noise_bump(mat, scale=520.0, strength=0.0018, distance=0.0006)
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    bpy.context.view_layer.update()


def ensure_material(obj, target, defaults, preserve_existing=False, material_profile=None):
    if preserve_existing and obj.data.materials:
        return
    if is_qc7_5244_black_target(target) and material_profile and material_profile.get("profile_name") == "qc7_5244_black_surface_texture_profile_v1":
        apply_qc7_5244_black_surface_texture_profile_v1(obj, material_profile)
        return
    color = (0.58, 0.60, 0.62, 1.0)
    target_lower = target.lower()
    material_defaults = defaults.get("material_defaults", {})
    profile_params = (material_profile or {}).get("material_parameters", {})
    if profile_params:
        params = profile_params
        color = tuple(params.get("base_color", color))
    elif "blue" in target_lower:
        params = material_defaults.get("generic_blue_plastic", {}).get("material_parameters", {})
        color = tuple(params.get("base_color", color))
    elif "black" in target_lower:
        params = material_defaults.get("generic_black_plastic", {}).get("material_parameters", {})
        color = tuple(params.get("base_color", (0.035, 0.038, 0.042, 1.0)))
    elif "white" in target_lower:
        params = material_defaults.get("generic_white_plastic", {}).get("material_parameters", {})
        color = tuple(params.get("base_color", (0.72, 0.74, 0.76, 1.0)))
    else:
        params = material_defaults.get("generic_gray_plastic", {}).get("material_parameters", {})
        color = tuple(params.get("base_color", color))
    mat = bpy.data.materials.new("GENERIC_PRODUCT_MAT")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    roughness = float(params.get("roughness", 0.62))
    if is_qc7_5244_target(target):
        roughness = max(roughness, 0.78)
    bsdf.inputs["Roughness"].default_value = roughness
    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = float(params.get("alpha", 1.0))
    if "Specular IOR Level" in bsdf.inputs:
        specular_value = float(params.get("specular_ior_level", params.get("specular", 0.36)))
        if is_qc7_5244_target(target):
            specular_value = min(specular_value, 0.22)
        bsdf.inputs["Specular IOR Level"].default_value = specular_value
    elif "Specular" in bsdf.inputs:
        specular_value = float(params.get("specular", 0.36))
        if is_qc7_5244_target(target):
            specular_value = min(specular_value, 0.22)
        bsdf.inputs["Specular"].default_value = specular_value
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def apply_qc7_5244_black_surface_texture_profile_v1(obj, material_profile):
    regions = material_profile.get("surface_regions", {})
    main_profile = regions.get("main_fine_matte_plastic", {})
    rib_profile = regions.get("ribbed_border_plastic", {})
    gloss_profile = regions.get("semi_gloss_structural_plastic", {})
    shadow_profile = regions.get("deep_shadow_inner_parts", {})

    main_mat = make_qc7_surface_material("QC7_5244_MAIN_FINE_MATTE_V1", main_profile, fallback_color=(0.070, 0.078, 0.090, 1.0))
    rib_mat = make_qc7_ribbed_material("QC7_5244_RIBBED_BORDER_V1", rib_profile, fallback_color=(0.045, 0.052, 0.062, 1.0))
    gloss_mat = make_qc7_surface_material("QC7_5244_SEMI_GLOSS_STRUCTURE_V1", gloss_profile, fallback_color=(0.058, 0.064, 0.074, 1.0))
    shadow_mat = make_qc7_surface_material("QC7_5244_DEEP_SHADOW_V1", shadow_profile, fallback_color=(0.026, 0.030, 0.036, 1.0))

    obj.data.materials.clear()
    for mat in (main_mat, rib_mat, gloss_mat, shadow_mat):
        obj.data.materials.append(mat)
    assign_qc7_surface_texture_regions(obj)
    bpy.context.view_layer.update()


def make_qc7_surface_material(name, region_profile, fallback_color):
    tex = region_profile.get("procedural_texture", {})
    base_color = tuple(region_profile.get("base_color", fallback_color))
    roughness = float(region_profile.get("roughness", 0.76))
    specular = float(region_profile.get("specular_ior_level", 0.22))
    mat = make_basic_principled_material(name, base_color, roughness, specular)
    add_noise_color_variation(
        mat,
        base_color,
        scale=float(tex.get("noise_scale", 150.0)),
        strength=float(tex.get("color_variation_strength", 0.012)),
    )
    add_noise_bump(
        mat,
        scale=float(tex.get("noise_scale", 150.0)),
        strength=float(tex.get("bump_strength", 0.008)),
        distance=float(tex.get("bump_distance", 0.012)),
    )
    return mat


def make_qc7_ribbed_material(name, region_profile, fallback_color):
    base_color = tuple(region_profile.get("base_color", fallback_color))
    roughness = float(region_profile.get("roughness", 0.72))
    specular = float(region_profile.get("specular_ior_level", 0.18))
    tex = region_profile.get("procedural_texture", {})
    mat = make_basic_principled_material(name, base_color, roughness, specular)
    tree = mat.node_tree
    bsdf = find_principled(mat)
    if bsdf is None:
        return mat
    wave_primary = tree.nodes.new("ShaderNodeTexWave")
    wave_primary.inputs["Scale"].default_value = float(tex.get("primary_wave_scale", 110.0))
    wave_primary.inputs["Distortion"].default_value = 4.0
    wave_secondary = tree.nodes.new("ShaderNodeTexWave")
    wave_secondary.inputs["Scale"].default_value = float(tex.get("secondary_wave_scale", 22.0))
    wave_secondary.inputs["Distortion"].default_value = 1.5
    mix = tree.nodes.new("ShaderNodeMix")
    mix.data_type = "FLOAT"
    mix.factor_mode = "UNIFORM"
    mix.inputs["Factor"].default_value = float(tex.get("grid_mix_strength", 0.28))
    bump = tree.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = float(tex.get("primary_bump_strength", 0.034))
    bump.inputs["Distance"].default_value = float(tex.get("bump_distance", 0.028))
    tree.links.new(wave_primary.outputs["Color"], mix.inputs[6])
    tree.links.new(wave_secondary.outputs["Color"], mix.inputs[7])
    tree.links.new(mix.outputs[1], bump.inputs["Height"])
    tree.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    color_ramp = tree.nodes.new("ShaderNodeValToRGB")
    color_ramp.color_ramp.elements[0].position = 0.35
    color_ramp.color_ramp.elements[0].color = darken_color(base_color, 0.72)
    color_ramp.color_ramp.elements[1].position = 1.0
    color_ramp.color_ramp.elements[1].color = lighten_color(base_color, 1.55)
    tree.links.new(mix.outputs[1], color_ramp.inputs["Fac"])
    tree.links.new(color_ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def add_noise_color_variation(mat, base_color, scale, strength):
    tree = mat.node_tree
    bsdf = find_principled(mat)
    if bsdf is None:
        return
    noise = tree.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 14.0
    noise.inputs["Roughness"].default_value = 0.62
    ramp = tree.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.18
    ramp.color_ramp.elements[0].color = darken_color(base_color, 1.0 - strength)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = lighten_color(base_color, 1.0 + strength)
    tree.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    tree.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])


def darken_color(color, factor):
    return tuple(min(max(component * factor, 0.0), 1.0) if index < 3 else component for index, component in enumerate(color))


def lighten_color(color, factor):
    return tuple(min(max(component * factor, 0.0), 1.0) if index < 3 else component for index, component in enumerate(color))


def assign_qc7_surface_texture_regions(obj):
    min_v, max_v = world_bbox(obj)
    dims = max_v - min_v
    if min(abs(float(dims.x)), abs(float(dims.y)), abs(float(dims.z))) <= 0.0:
        return
    # Use the broadest two axes as the visible panel coordinates. This is an
    # isolated material experiment, so approximate bbox windows are enough.
    axis_values = [abs(float(dims.x)), abs(float(dims.y)), abs(float(dims.z))]
    panel_axes = sorted(range(3), key=lambda index: axis_values[index], reverse=True)[:2]
    depth_axis = [index for index in range(3) if index not in panel_axes][0]
    min_values = [float(min_v.x), float(min_v.y), float(min_v.z)]
    max_values = [float(max_v.x), float(max_v.y), float(max_v.z)]

    for poly in obj.data.polygons:
        center = obj.matrix_world @ poly.center
        coords = [float(center.x), float(center.y), float(center.z)]
        u = normalized_axis_value(coords[panel_axes[0]], min_values[panel_axes[0]], max_values[panel_axes[0]])
        v = normalized_axis_value(coords[panel_axes[1]], min_values[panel_axes[1]], max_values[panel_axes[1]])
        depth = normalized_axis_value(coords[depth_axis], min_values[depth_axis], max_values[depth_axis])

        border = u < 0.14 or u > 0.88 or v < 0.12 or v > 0.88
        deep_cavity = depth < 0.12 or depth > 0.88
        semi_gloss_structure = (0.33 < u < 0.75 and 0.18 < v < 0.78 and not border)
        if border:
            poly.material_index = 1
        elif deep_cavity:
            poly.material_index = 3
        elif semi_gloss_structure:
            poly.material_index = 2
        else:
            poly.material_index = 0


def add_qc7_ribbed_border_surface_proxies(obj, material_profile):
    existing = [item for item in bpy.data.objects if item.name.startswith("GENERIC_SURFACE_PROXY_QC7_RIBBED_")]
    for item in existing:
        bpy.data.objects.remove(item, do_unlink=True)

    regions = material_profile.get("surface_regions", {})
    rib_profile = regions.get("ribbed_border_plastic", {})
    rib_mat_vertical = make_qc7_ribbed_material(
        "QC7_5244_RIBBED_PROXY_VERTICAL_V1",
        rib_profile,
        fallback_color=(0.040, 0.046, 0.055, 1.0),
    )
    rib_mat_horizontal = make_qc7_ribbed_material(
        "QC7_5244_RIBBED_PROXY_HORIZONTAL_V1",
        rib_profile,
        fallback_color=(0.040, 0.046, 0.055, 1.0),
    )
    rib_line_mat = make_basic_principled_material(
        "QC7_5244_RIBBED_PROXY_LINE_V1",
        (0.078, 0.086, 0.096, 1.0),
        0.74,
        0.18,
    )

    min_v, max_v = world_bbox(obj)
    dims = max_v - min_v
    values = [abs(float(dims.x)), abs(float(dims.y)), abs(float(dims.z))]
    normal_axis = min(range(3), key=lambda index: values[index])
    plane_axes = [index for index in range(3) if index != normal_axis]
    max_dim = max(values)
    offset = max_dim * 0.0025
    for side_name, sign in (("front", -1.0), ("back", 1.0)):
        normal_value = (axis_component(max_v, normal_axis) if sign > 0 else axis_component(min_v, normal_axis)) + sign * offset
        add_qc7_surface_proxy_band(
            obj,
            "GENERIC_SURFACE_PROXY_QC7_RIBBED_{0}_LEFT".format(side_name),
            min_v,
            max_v,
            normal_axis,
            plane_axes,
            normal_value,
            u_range=(0.018, 0.105),
            v_range=(0.05, 0.94),
            material=rib_mat_vertical,
            line_material=rib_line_mat,
        )
        add_qc7_surface_proxy_band(
            obj,
            "GENERIC_SURFACE_PROXY_QC7_RIBBED_{0}_TOP".format(side_name),
            min_v,
            max_v,
            normal_axis,
            plane_axes,
            normal_value,
            u_range=(0.10, 0.94),
            v_range=(0.885, 0.970),
            material=rib_mat_horizontal,
            line_material=rib_line_mat,
        )
        add_qc7_surface_proxy_band(
            obj,
            "GENERIC_SURFACE_PROXY_QC7_RIBBED_{0}_BOTTOM".format(side_name),
            min_v,
            max_v,
            normal_axis,
            plane_axes,
            normal_value,
            u_range=(0.13, 0.95),
            v_range=(0.025, 0.110),
            material=rib_mat_horizontal,
            line_material=rib_line_mat,
        )


def add_qc7_surface_proxy_band(obj, name, min_v, max_v, normal_axis, plane_axes, normal_value, u_range, v_range, material, line_material):
    u0 = interpolate_axis(min_v, max_v, plane_axes[0], u_range[0])
    u1 = interpolate_axis(min_v, max_v, plane_axes[0], u_range[1])
    v0 = interpolate_axis(min_v, max_v, plane_axes[1], v_range[0])
    v1 = interpolate_axis(min_v, max_v, plane_axes[1], v_range[1])
    width = abs(u1 - u0)
    height = abs(v1 - v0)
    long_axis_vertical = height > width
    if long_axis_vertical:
        stripe_count = 22
        stripe_width = width / 58.0
        for index in range(stripe_count):
            center_u = u0 + width * (index + 0.55) / stripe_count
            make_qc7_proxy_quad(
                name + "_VLINE_{0:02d}".format(index),
                normal_axis,
                plane_axes,
                normal_value,
                center_u - stripe_width * 0.5,
                center_u + stripe_width * 0.5,
                v0,
                v1,
                line_material,
            )
        cross_count = 18
        cross_height = height / 110.0
        for index in range(cross_count):
            center_v = v0 + height * (index + 0.5) / cross_count
            make_qc7_proxy_quad(
                name + "_HLINE_{0:02d}".format(index),
                normal_axis,
                plane_axes,
                normal_value,
                u0,
                u1,
                center_v - cross_height * 0.5,
                center_v + cross_height * 0.5,
                material,
            )
    else:
        stripe_count = 48
        stripe_width = width / 160.0
        for index in range(stripe_count):
            center_u = u0 + width * (index + 0.5) / stripe_count
            make_qc7_proxy_quad(
                name + "_VGRID_{0:02d}".format(index),
                normal_axis,
                plane_axes,
                normal_value,
                center_u - stripe_width * 0.5,
                center_u + stripe_width * 0.5,
                v0,
                v1,
                line_material,
            )
        row_count = 5
        row_height = height / 38.0
        for index in range(row_count):
            center_v = v0 + height * (index + 0.5) / row_count
            make_qc7_proxy_quad(
                name + "_HGRID_{0:02d}".format(index),
                normal_axis,
                plane_axes,
                normal_value,
                u0,
                u1,
                center_v - row_height * 0.5,
                center_v + row_height * 0.5,
                material,
            )


def make_qc7_proxy_quad(name, normal_axis, plane_axes, normal_value, u0, u1, v0, v1, material):
    coords = []
    for u, v in ((u0, v0), (u1, v0), (u1, v1), (u0, v1)):
        values = [0.0, 0.0, 0.0]
        values[normal_axis] = normal_value
        values[plane_axes[0]] = u
        values[plane_axes[1]] = v
        coords.append(tuple(values))
    mesh = bpy.data.meshes.new(name + "_MESH")
    mesh.from_pydata(coords, [], [(0, 1, 2, 3)])
    mesh.update()
    proxy = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(proxy)
    proxy.data.materials.append(material)
    proxy["surface_texture_proxy"] = True
    proxy["do_not_label_as_defect"] = True
    return proxy


def axis_component(vec, axis):
    return [float(vec.x), float(vec.y), float(vec.z)][axis]


def interpolate_axis(min_v, max_v, axis, normalized):
    return axis_component(min_v, axis) + (axis_component(max_v, axis) - axis_component(min_v, axis)) * normalized


def normalized_axis_value(value, min_value, max_value):
    span = max(max_value - min_value, 1e-8)
    return min(max((value - min_value) / span, 0.0), 1.0)


def setup_camera(obj, width, height, scene_profile):
    existing_camera = bpy.context.scene.camera
    if scene_profile["uses_existing_camera"] and existing_camera is not None:
        bpy.context.scene.render.resolution_x = width
        bpy.context.scene.render.resolution_y = height
        return existing_camera
    cam_data = bpy.data.cameras.new("GENERIC_CAMERA")
    cam = bpy.data.objects.new("GENERIC_CAMERA", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.data.lens = 70
    cam.data.type = "ORTHO"
    bpy.context.scene.camera = cam
    bpy.context.scene.render.resolution_x = width
    bpy.context.scene.render.resolution_y = height
    position_camera_for_side(cam, obj, "front")
    return cam


def position_camera_for_side(camera, obj, side, target=""):
    if is_qc71336_gray_target(target):
        position_qc71336_gray_reference_camera(camera, obj, side)
        return
    min_v, max_v = world_bbox(obj)
    frame = placement_frame_for_target(min_v, max_v, target, side)
    dims = max_v - min_v
    max_dim = max(float(dims.x), float(dims.y), float(dims.z), 1.0)
    view_center = placement_window_center(min_v, max_v, frame)
    normal = axis_unit(frame["normal_axis"], frame["normal_sign"])
    camera.location = view_center + normal * max_dim * 2.2
    look_at(camera, view_center)
    camera.data.ortho_scale = max(frame["plane_dims"][0], frame["plane_dims"][1], 1.0) * 1.25


def position_qc71336_gray_reference_camera(camera, obj, side):
    min_v, max_v = world_bbox(obj)
    center = (min_v + max_v) * 0.5
    span = max_v - min_v
    max_dim = max(float(abs(span.x)), float(abs(span.y)), float(abs(span.z)), 1e-3)
    focus_target = center + Vector((0.0, 0.015 * max_dim, 0.0))
    offset = Vector((-0.08, -0.42, 2.58) if side == "front" else (0.08, -0.42, -2.58)) * max_dim
    camera.location = center + offset
    camera.rotation_euler = (focus_target - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "PERSP"
    camera.data.lens = 66.0
    camera.data.sensor_width = 36.0
    camera.data.sensor_fit = "HORIZONTAL"
    camera.data.clip_start = 0.01
    camera.data.clip_end = 1000.0
    camera.data.shift_x = 0.0
    camera.data.shift_y = -0.02 if side == "front" else 0.009
    bpy.context.view_layer.update()


def apply_camera_domain_randomization(camera, obj, side, target, rng):
    if not is_qc71336_gray_target(target):
        return {"enabled": False}
    min_v, max_v = world_bbox(obj)
    span = max_v - min_v
    max_dim = max(float(abs(span.x)), float(abs(span.y)), float(abs(span.z)), 1e-3)
    side_sign = 1.0 if side == "front" else -1.0
    camera.location.x += rng.uniform(-0.040, 0.040) * max_dim
    camera.location.y += rng.uniform(-0.040, 0.040) * max_dim
    camera.location.z += rng.uniform(-0.055, 0.055) * max_dim * side_sign
    camera.rotation_euler.rotate_axis("X", math.radians(rng.uniform(-1.8, 1.8)))
    camera.rotation_euler.rotate_axis("Y", math.radians(rng.uniform(-1.2, 1.2)))
    camera.rotation_euler.rotate_axis("Z", math.radians(rng.uniform(-2.4, 2.4)))
    camera.data.lens = max(40.0, camera.data.lens + rng.uniform(-4.0, 3.0))
    camera.data.shift_x = max(-0.08, min(0.08, camera.data.shift_x + rng.uniform(-0.012, 0.012)))
    camera.data.shift_y = max(-0.08, min(0.08, camera.data.shift_y + rng.uniform(-0.012, 0.012)))
    bpy.context.view_layer.update()
    return {"enabled": True}


def setup_lighting(obj, camera=None, target=""):
    min_v, max_v = world_bbox(obj)
    dims = max_v - min_v
    center = (min_v + max_v) * 0.5
    max_dim = max(float(dims.x), float(dims.y), float(dims.z), 1.0)
    existing_lights = [light for light in bpy.data.objects if light.type == "LIGHT" and not light.name.startswith("GENERIC_")]
    if existing_lights:
        if is_qc71336_gray_target(target):
            tune_qc71336_gray_reference_lighting()
        randomize_existing_lights(existing_lights, target)
    for light in list(bpy.data.objects):
        if light.type == "LIGHT" and light.name.startswith("GENERIC_"):
            bpy.data.objects.remove(light, do_unlink=True)
    if existing_lights:
        configure_world_background(target)
        return
    if camera is not None:
        direction = (camera.location - center).normalized()
        key_location = center + direction * max_dim * 1.2 + Vector((0.0, 0.0, max_dim * 0.5))
    else:
        key_location = Vector((max_dim * 0.25, -max_dim * 1.3, max_dim * 1.2))
    if is_qc7_5244_black_target(target):
        key_energy, fill_energy, key_size = 2503, 473, max_dim * 1.75
    elif is_qc7_5244_white_target(target):
        key_energy, fill_energy, key_size = 980, 210, max_dim * 1.70
    elif is_ql3_target(target):
        key_energy, fill_energy, key_size = 950, 210, max_dim * 1.55
    else:
        key_energy, fill_energy, key_size = 1400, 500, max_dim * 1.4
    add_area_light("GENERIC_KEY_LIGHT", key_location, key_energy, key_size)
    add_area_light("GENERIC_FILL_LIGHT", center + Vector((-max_dim * 0.8, max_dim * 0.6, max_dim * 0.9)), fill_energy, max_dim * 2.2)
    configure_world_background(target)


def tune_qc71336_gray_reference_lighting():
    scene = bpy.context.scene
    energy_map = {
        "Area": 0.533,
        "Area.001": 0.492,
        "Area.002": 0.451,
        "Area.003": 5.184,
        "Area.004": 0.369,
        "Area.005": 2.484,
        "Area.006": 30.0,
        "Area.007": 10.0,
        "Area.008": 30.0,
        "Area.009": 10.0,
        "Area.010": 10.0,
        "Area.011": 10.0,
    }
    warm_lights = {"Area.003", "Area.005"}
    for obj in bpy.data.objects:
        if obj.type != "LIGHT":
            continue
        if "generic_base_energy" in obj.data:
            continue
        if getattr(obj.data, "color", None) is not None:
            obj.data.color = (1.0, 0.975, 0.944) if obj.name in warm_lights else (0.982, 0.965, 0.948)
        if hasattr(obj.data, "energy"):
            obj.data.energy = float(energy_map.get(obj.name, obj.data.energy))
        if obj.data.type == "AREA":
            size_scale = 0.75 if obj.name in warm_lights else 1.04
            if hasattr(obj.data, "size"):
                obj.data.size = float(obj.data.size) * size_scale
            if hasattr(obj.data, "size_y"):
                obj.data.size_y = float(obj.data.size_y) * size_scale
    bg = find_background_node(scene.world)
    if bg is not None:
        bg.inputs["Color"].default_value = (0.705, 0.697, 0.686, 1.0)
        bg.inputs["Strength"].default_value = min(float(bg.inputs["Strength"].default_value), 0.014)
    scene.view_settings.exposure = -0.96
    try:
        scene.view_settings.look = "Medium High Contrast"
    except Exception:
        pass
    bpy.context.view_layer.update()


def randomize_existing_lights(lights, target=""):
    for light in lights:
        if "generic_base_rotation" not in light:
            light["generic_base_rotation"] = [float(value) for value in light.rotation_euler]
        base_rotation = light["generic_base_rotation"]
        light.rotation_euler = tuple(base_rotation)
        if hasattr(light.data, "energy"):
            if "generic_base_energy" not in light.data:
                light.data["generic_base_energy"] = float(light.data.energy)
            base_energy = float(light.data["generic_base_energy"])
            light.data.energy = base_energy * random.uniform(0.8, 1.2)
        jitter = 3.0 if is_qc71336_gray_target(target) else 8.0
        light.rotation_euler.rotate_axis("X", math.radians(random.uniform(-jitter, jitter)))
        light.rotation_euler.rotate_axis("Y", math.radians(random.uniform(-jitter, jitter)))
        if is_qc71336_gray_target(target):
            light.rotation_euler.rotate_axis("Z", math.radians(random.uniform(-3.0, 3.0)))
    if is_qc71336_gray_target(target):
        bpy.context.scene.view_settings.exposure = -0.96 + random.uniform(-0.10, 0.10)


def configure_world_background(target=""):
    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background is not None:
        if is_qc71336_gray_target(target):
            background.inputs["Color"].default_value = (0.705, 0.697, 0.686, 1.0)
            background.inputs["Strength"].default_value = 0.014 * random.uniform(0.82, 1.18)
            world.color = (0.705, 0.697, 0.686)
        elif is_qc7_5244_black_target(target):
            background.inputs["Color"].default_value = (0.72, 0.72, 0.72, 1.0)
            background.inputs["Strength"].default_value = 0.94
            world.color = (0.72, 0.72, 0.72)
        elif is_qc7_5244_white_target(target) or is_ql3_target(target):
            background.inputs["Color"].default_value = (0.76, 0.76, 0.76, 1.0)
            background.inputs["Strength"].default_value = 0.36
            world.color = (0.76, 0.76, 0.76)
        else:
            background.inputs["Color"].default_value = (0.78, 0.78, 0.78, 1.0)
            background.inputs["Strength"].default_value = 0.8
            world.color = (0.78, 0.78, 0.78)


def add_area_light(name, location, energy, size):
    light_data = bpy.data.lights.new(name, type="AREA")
    light = bpy.data.objects.new(name, light_data)
    bpy.context.collection.objects.link(light)
    light.location = location
    light.data.energy = energy
    light.data.size = size
    return light


def configure_render(width, height, samples):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1


def create_defect(product, target, defect_type, rng, sides, defaults):
    defect_defaults = defaults.get("defect_defaults", {}).get(defect_type, {})
    min_v, max_v = world_bbox(product)
    dims = max_v - min_v
    max_dim = max(float(dims.x), float(dims.y), float(dims.z), 1.0)
    side = rng.choice(sides or ["front"])
    if is_ql3_target(target) and defect_type == "splay":
        side = "front"
    if is_qc71336_gray_target(target) and defect_type == "mixed_color_contamination":
        side = "front"
    frame = placement_frame_for_target(min_v, max_v, target, side)
    if is_ql3_target(target) and defect_type == "splay":
        frame["normalized_ranges"] = {
            frame["plane_axes"][0]: (0.34, 0.58),
            frame["plane_axes"][1]: (0.74, 0.92),
        }
    coords = [0.0, 0.0, 0.0]
    normal_axis = frame["normal_axis"]
    plane_a, plane_b = frame["plane_axes"]
    sign = frame["normal_sign"]
    if is_qc71336_gray_target(target) and defect_type == "mixed_color_contamination":
        surface_offset = max_dim * 0.0007
    elif is_ql3_target(target) or is_qc71336_white_target(target) or is_qc71336_gray_target(target) or is_qc7_5244_black_target(target):
        surface_offset = max_dim * 0.004
    else:
        surface_offset = max_dim * 0.020
    coords[normal_axis] = (
        min_v[normal_axis] - surface_offset
        if sign < 0
        else max_v[normal_axis] + surface_offset
    )
    ranges = frame["normalized_ranges"]
    coords[plane_a] = rng.uniform(
        min_v[plane_a] + dims[plane_a] * ranges[plane_a][0],
        min_v[plane_a] + dims[plane_a] * ranges[plane_a][1],
    )
    coords[plane_b] = rng.uniform(
        min_v[plane_b] + dims[plane_b] * ranges[plane_b][0],
        min_v[plane_b] + dims[plane_b] * ranges[plane_b][1],
    )
    size_range = defect_defaults.get("size_factor_range", [0.012, 0.035])
    radius = max_dim * rng.uniform(float(size_range[0]), float(size_range[1]))
    if is_qc71336_gray_target(target) and defect_type == "black_dot":
        radius = max_dim * rng.uniform(0.0020, 0.0038)
    if is_qc7_5244_black_target(target):
        if defect_type == "black_dot":
            radius = max_dim * rng.uniform(0.0022, 0.0039)
        elif defect_type == "foreign_material":
            radius = max_dim * rng.uniform(0.0014, 0.0028)
        elif defect_type == "splay":
            radius = max_dim * rng.uniform(0.0045, 0.0085)
    if defect_type == "splay":
        if is_ql3_target(target):
            obj = add_ql3_splay_defect("GENERIC_DEFECT_SPLAY", max_dim, rng)
        elif is_qc7_5244_black_target(target):
            obj = add_qc7_black_splay_defect("GENERIC_DEFECT_SPLAY", max_dim, rng)
        else:
            obj = add_splay_streak_defect(
                "GENERIC_DEFECT_SPLAY",
                radius * float(defect_defaults.get("width_multiplier", 4.0)),
                radius * float(defect_defaults.get("height_multiplier", 0.9)),
                rng,
            )
    elif defect_type == "mixed_color_contamination":
        if is_qc71336_gray_target(target):
            obj = add_qc71336_gray_soft_spiral_mixed_color_defect("GENERIC_DEFECT_MIXED_COLOR", max_dim, rng)
        else:
            obj = add_plane_defect(
                "GENERIC_DEFECT_MIXED_COLOR",
                radius * float(defect_defaults.get("width_multiplier", 3.0)),
                radius * float(defect_defaults.get("height_multiplier", 1.8)),
            )
    elif defect_type == "foreign_material":
        if is_ql3_target(target):
            obj = add_ql3_foreign_chip_defect("GENERIC_DEFECT_FOREIGN", max_dim, rng, side)
        elif is_qc71336_white_target(target):
            obj = add_qc71336_white_foreign_particle_defect("GENERIC_DEFECT_FOREIGN", max_dim, rng)
        elif is_qc7_5244_black_target(target):
            obj = add_qc7_black_foreign_particles("GENERIC_DEFECT_FOREIGN", max_dim, rng)
        else:
            obj = add_irregular_chip_defect(
                "GENERIC_DEFECT_FOREIGN",
                radius * float(defect_defaults.get("width_multiplier", 1.3)),
                radius * float(defect_defaults.get("height_multiplier", 1.1)),
                rng,
            )
    elif defect_type == "sink_mark":
        obj = add_plane_defect(
            "GENERIC_DEFECT_SINK",
            radius * float(defect_defaults.get("width_multiplier", 2.2)),
            radius * float(defect_defaults.get("height_multiplier", 1.5)),
        )
    else:
        if is_qc7_5244_black_target(target):
            obj = add_qc7_black_dot_smudge("GENERIC_DEFECT_BLACK_DOT", radius, rng)
        else:
            obj = add_disk_defect("GENERIC_DEFECT_BLACK_DOT", radius)
    obj.location = Vector(coords)
    align_plane_to_normal(obj, axis_unit(normal_axis, sign))
    if is_qc7_5244_black_target(target) and defect_type == "splay":
        obj.rotation_euler.rotate_axis("Z", math.pi * 0.5 + rng.uniform(-0.18, 0.18))
    obj["anchor_side"] = side
    obj["main_plane_axis"] = ["x", "y", "z"][normal_axis]
    obj["placement_policy"] = frame["placement_policy"]
    obj["defect_type"] = defect_type
    if is_qc7_5244_black_target(target) and defect_type == "black_dot":
        halo_material = make_qc7_black_dot_material("GENERIC_BLACK_DOT_HALO_MAT", (0.092, 0.088, 0.078, 1.0), 0.88)
        core_material = make_qc7_black_dot_material("GENERIC_BLACK_DOT_CORE_MAT", (0.045, 0.040, 0.034, 1.0), 0.86)
        for mesh_obj in defect_mesh_objects(obj):
            mesh_obj.data.materials.append(core_material if mesh_obj.name.endswith("_CORE") else halo_material)
    elif is_qc71336_gray_target(target) and defect_type == "mixed_color_contamination":
        materials = make_qc71336_gray_mixed_color_materials()
        for mesh_obj in defect_mesh_objects(obj):
            if mesh_obj.name.endswith("_BASE"):
                mesh_obj.data.materials.append(materials["center"])
                mesh_obj.data.materials.append(materials["mid"])
                mesh_obj.data.materials.append(materials["edge"])
            elif mesh_obj.name.endswith("_MID"):
                mesh_obj.data.materials.append(materials["mid"])
            elif mesh_obj.name.endswith("_CENTER"):
                mesh_obj.data.materials.append(materials["center"])
            else:
                mesh_obj.data.materials.append(materials["edge"])
            mesh_obj.visible_shadow = False
    else:
        defect_material = make_defect_material(defect_type, defect_defaults, product, target)
        for mesh_obj in defect_mesh_objects(obj):
            mesh_obj.data.materials.append(defect_material)
    return obj


def ensure_surface_proxy(product, target, defaults, side):
    for obj in list(bpy.data.objects):
        if obj.name.startswith("GENERIC_SURFACE_PROXY"):
            bpy.data.objects.remove(obj, do_unlink=True)
    min_v, max_v = world_bbox(product)
    dims = max_v - min_v
    frame = main_plane_frame(min_v, max_v)
    normal_axis = frame["normal_axis"]
    plane_a, plane_b = frame["plane_axes"]
    sign = -1.0 if side == "front" else 1.0
    max_dim = max(float(dims.x), float(dims.y), float(dims.z), 1.0)
    normal_coord = (
        min_v[normal_axis] - max_dim * 0.002
        if side == "front"
        else max_v[normal_axis] + max_dim * 0.002
    )
    margin_a = dims[plane_a] * 0.03
    margin_b = dims[plane_b] * 0.03
    corners = []
    for a, b in [
        (min_v[plane_a] + margin_a, min_v[plane_b] + margin_b),
        (max_v[plane_a] - margin_a, min_v[plane_b] + margin_b),
        (max_v[plane_a] - margin_a, max_v[plane_b] - margin_b),
        (min_v[plane_a] + margin_a, max_v[plane_b] - margin_b),
    ]:
        coords = [0.0, 0.0, 0.0]
        coords[normal_axis] = normal_coord
        coords[plane_a] = a
        coords[plane_b] = b
        corners.append(tuple(coords))
    face = (0, 1, 2, 3) if sign < 0 else (3, 2, 1, 0)
    mesh = bpy.data.meshes.new("GENERIC_SURFACE_PROXY_MESH")
    mesh.from_pydata(corners, [], [face])
    mesh.update()
    proxy = bpy.data.objects.new("GENERIC_SURFACE_PROXY", mesh)
    bpy.context.collection.objects.link(proxy)
    if product.data.materials:
        proxy.data.materials.append(product.data.materials[0])
    else:
        ensure_material(proxy, target, defaults)
    return proxy


def add_disk_defect(name, radius, vertices=32):
    mesh = bpy.data.meshes.new(name + "_MESH")
    verts = [(0.0, 0.0, 0.0)]
    for index in range(vertices):
        angle = math.tau * index / vertices
        verts.append((math.cos(angle) * radius, math.sin(angle) * radius, 0.0))
    faces = [(0,) + tuple(range(1, vertices + 1))]
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def add_plane_defect(name, width, height):
    mesh = bpy.data.meshes.new(name + "_MESH")
    verts = [(-width / 2, -height / 2, 0), (width / 2, -height / 2, 0), (width / 2, height / 2, 0), (-width / 2, height / 2, 0)]
    mesh.from_pydata(verts, [], [(0, 1, 2, 3)])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def add_irregular_chip_defect(name, width, height, rng):
    mesh = bpy.data.meshes.new(name + "_MESH")
    vertex_count = rng.randint(7, 11)
    verts = [(0.0, 0.0, 0.0)]
    outer = []
    for index in range(vertex_count):
        angle = math.tau * index / vertex_count + rng.uniform(-0.15, 0.15)
        radius = rng.uniform(0.62, 1.08)
        x = math.cos(angle) * width * 0.5 * radius
        y = math.sin(angle) * height * 0.5 * radius
        outer.append(len(verts))
        verts.append((x, y, rng.uniform(-0.015, 0.035) * min(width, height)))
    faces = []
    for index in range(vertex_count):
        faces.append((0, outer[index], outer[(index + 1) % vertex_count]))
        faces.append((0, outer[(index + 1) % vertex_count], outer[index]))
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.rotation_euler.rotate_axis("Z", rng.uniform(0.0, math.tau))
    return obj


def add_qc7_black_dot_smudge(name, radius, rng):
    parent = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(parent)
    parent["defect_group"] = True
    halo = add_irregular_flat_blob(name + "_HALO", radius * rng.uniform(1.28, 1.62), rng, stretch_y_range=(0.46, 0.78))
    core = add_irregular_flat_blob(name + "_CORE", radius * rng.uniform(0.54, 0.78), rng, stretch_y_range=(0.38, 0.68))
    halo.parent = parent
    core.parent = parent
    core.location = (rng.uniform(-0.12, 0.12) * radius, rng.uniform(-0.08, 0.08) * radius, max(radius * 0.001, 0.00001))
    parent.rotation_euler.rotate_axis("Z", rng.uniform(0.0, math.tau))
    return parent


def add_irregular_flat_blob(name, radius, rng, stretch_y_range=(0.38, 0.72)):
    mesh = bpy.data.meshes.new(name + "_MESH")
    vertex_count = rng.randint(11, 17)
    verts = [(0.0, 0.0, 0.0)]
    outer = []
    stretch_x = rng.uniform(0.86, 1.28)
    stretch_y = rng.uniform(float(stretch_y_range[0]), float(stretch_y_range[1]))
    phase = rng.uniform(0.0, math.tau)
    for index in range(vertex_count):
        angle = math.tau * index / vertex_count + rng.uniform(-0.11, 0.11)
        radial = radius * rng.uniform(0.44, 1.08) * (1.0 + 0.12 * math.sin(angle * 2.0 + phase))
        outer.append(len(verts))
        verts.append((math.cos(angle) * radial * stretch_x, math.sin(angle) * radial * stretch_y, 0.0))
    faces = []
    for index in range(vertex_count):
        faces.append((0, outer[index], outer[(index + 1) % vertex_count]))
        faces.append((0, outer[(index + 1) % vertex_count], outer[index]))
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def add_qc7_black_foreign_particles(name, max_dim, rng):
    parent = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(parent)
    parent["defect_group"] = True
    particle_count = 2
    separation = max_dim * rng.uniform(0.0048, 0.0095)
    angle = rng.uniform(0.0, math.tau)
    for particle_index in range(particle_count):
        radius = max_dim * rng.uniform(0.0018, 0.0036)
        obj = add_irregular_chip_defect(
            f"{name}_{particle_index:02d}",
            radius * rng.uniform(1.15, 2.00),
            radius * rng.uniform(0.75, 1.35),
            rng,
        )
        obj.parent = parent
        signed = -0.5 if particle_index == 0 else 0.5
        obj.location = (
            math.cos(angle) * separation * signed + rng.uniform(-0.20, 0.20) * separation,
            math.sin(angle) * separation * signed + rng.uniform(-0.20, 0.20) * separation,
            0.0,
        )
        obj.scale.z *= rng.uniform(0.20, 0.42)
    parent.rotation_euler.rotate_axis("Z", rng.uniform(0.0, math.tau))
    return parent


def add_ql3_foreign_chip_defect(name, max_dim, rng, anchor_side="front"):
    parent = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(parent)
    parent["defect_group"] = True
    particle_count = rng.randint(32, 62)
    if anchor_side == "front":
        region_width = max_dim * rng.uniform(0.045, 0.075)
        region_height = max_dim * rng.uniform(0.145, 0.235)
    else:
        region_width = max_dim * rng.uniform(0.050, 0.090)
        region_height = max_dim * rng.uniform(0.090, 0.155)
    min_distance = max_dim * rng.uniform(0.0022, 0.0048)
    centers = []
    attempts = 0
    while len(centers) < particle_count and attempts < particle_count * 80:
        attempts += 1
        if anchor_side == "front":
            lane = rng.choice([-0.33, 0.0, 0.28])
            x = rng.gauss(lane * region_width, region_width * 0.11)
            y = rng.uniform(-0.5, 0.5) * region_height
            if rng.random() < 0.22:
                x += rng.uniform(-0.5, 0.5) * region_width
        else:
            if rng.random() < 0.62:
                x = rng.gauss(0.0, region_width * 0.20)
                y = rng.uniform(-0.5, 0.5) * region_height
            else:
                x = rng.uniform(-0.5, 0.5) * region_width
                y = rng.uniform(-0.5, 0.5) * region_height
        x = max(-region_width * 0.5, min(region_width * 0.5, x))
        y = max(-region_height * 0.5, min(region_height * 0.5, y))
        if all((x - px) * (x - px) + (y - py) * (y - py) >= min_distance * min_distance for px, py in centers):
            centers.append((x, y))
    while len(centers) < particle_count:
        centers.append((rng.uniform(-0.5, 0.5) * region_width, rng.uniform(-0.5, 0.5) * region_height))

    for particle_index, (center_x, center_y) in enumerate(centers):
        mesh = bpy.data.meshes.new(f"{name}_{particle_index:02d}_MESH")
        verts = []
        faces = []
        size_tier = rng.choices(["dust", "tiny", "normal"], weights=[64, 30, 6], k=1)[0]
        if size_tier == "tiny":
            radius = rng.uniform(max_dim * 0.00015, max_dim * 0.00032)
        elif size_tier == "normal":
            radius = rng.uniform(max_dim * 0.00028, max_dim * 0.00048)
        else:
            radius = rng.uniform(max_dim * 0.00007, max_dim * 0.00018)
        vertex_count = rng.randint(7, 11)
        verts.append((0.0, 0.0, rng.uniform(0.00, 0.08) * radius))
        top_ring = []
        bottom_ring = []
        phase = rng.uniform(0.0, math.tau)
        if rng.random() < 0.20:
            stretch_x = rng.uniform(1.10, 1.70)
            stretch_y = rng.uniform(0.35, 0.70)
        else:
            stretch_x = rng.uniform(0.72, 1.18)
            stretch_y = rng.uniform(0.68, 1.12)
        thickness = rng.uniform(0.05, 0.14) * radius
        chip_spin = rng.uniform(0.0, math.tau)
        for vertex_index in range(vertex_count):
            angle = math.tau * vertex_index / vertex_count + rng.uniform(-0.12, 0.12)
            edge = radius * rng.uniform(0.62, 1.10) * (1.0 + 0.10 * math.sin(angle * 2.0 + phase))
            local_x = math.cos(angle) * edge * stretch_x
            local_y = math.sin(angle) * edge * stretch_y
            x = math.cos(chip_spin) * local_x - math.sin(chip_spin) * local_y
            y = math.sin(chip_spin) * local_x + math.cos(chip_spin) * local_y
            top_ring.append(len(verts))
            verts.append((x, y, thickness * rng.uniform(0.20, 0.95)))
            bottom_ring.append(len(verts))
            verts.append((x * rng.uniform(0.88, 1.04), y * rng.uniform(0.88, 1.04), -thickness * 0.22))
        for vertex_index in range(vertex_count):
            next_index = (vertex_index + 1) % vertex_count
            faces.append((0, top_ring[vertex_index], top_ring[next_index]))
            faces.append((top_ring[vertex_index], bottom_ring[vertex_index], bottom_ring[next_index], top_ring[next_index]))
        faces.append(tuple(reversed(bottom_ring)))
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        for poly in mesh.polygons:
            poly.use_smooth = True
        obj = bpy.data.objects.new(f"{name}_{particle_index:02d}", mesh)
        bpy.context.collection.objects.link(obj)
        obj.parent = parent
        obj.location = (center_x, center_y, 0.0)
        obj.scale = (
            rng.uniform(0.92, 1.05),
            rng.uniform(0.92, 1.05),
            rng.uniform(0.08, 0.22),
        )
        obj.rotation_euler.rotate_axis("Z", rng.uniform(0.0, math.tau))
    if anchor_side != "front":
        parent.rotation_euler.rotate_axis("Z", rng.uniform(-0.35, 0.35))
    return parent


def add_qc71336_white_foreign_particle_defect(name, max_dim, rng):
    mesh = bpy.data.meshes.new(name + "_MESH")
    radius = max_dim * rng.uniform(0.0080, 0.0135)
    depth = radius * rng.uniform(0.24, 0.46)
    vertex_count = rng.randint(10, 16)
    verts = [(0.0, 0.0, depth * rng.uniform(0.12, 0.24))]
    bottom = []
    top = []
    for index in range(vertex_count):
        angle = math.tau * index / vertex_count + rng.uniform(-0.10, 0.10)
        radial = radius * rng.uniform(0.58, 1.12)
        squash_x = rng.uniform(0.72, 1.22)
        squash_y = rng.uniform(0.58, 1.05)
        x = math.cos(angle) * radial * squash_x
        y = math.sin(angle) * radial * squash_y
        bottom.append(len(verts))
        verts.append((x, y, 0.0))
        top.append(len(verts))
        verts.append((x * rng.uniform(0.82, 0.98), y * rng.uniform(0.82, 0.98), depth * rng.uniform(0.15, 0.34)))
    faces = []
    for index in range(vertex_count):
        next_index = (index + 1) % vertex_count
        faces.append((bottom[index], bottom[next_index], top[next_index], top[index]))
        faces.append((top[index], top[next_index], 0))
        faces.append((bottom[next_index], bottom[index], top[index], top[next_index]))
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.scale.y *= rng.uniform(0.50, 0.82)
    obj.rotation_euler.rotate_axis("Z", rng.uniform(-0.85, 0.85))
    return obj


def add_splay_streak_defect(name, length, width, rng):
    mesh = bpy.data.meshes.new(name + "_MESH")
    verts = []
    faces = []
    strip_count = rng.randint(2, 4)
    segments = 14
    for strip_index in range(strip_count):
        start = len(verts)
        y_offset = rng.uniform(-0.7, 0.7) * width
        local_length = length * rng.uniform(0.72, 1.05)
        local_width = width * rng.uniform(0.18, 0.42)
        curve = rng.uniform(-0.35, 0.35) * width
        for i in range(segments):
            t = i / (segments - 1)
            x = (t * 2.0 - 1.0) * local_length * 0.5
            center_y = y_offset + math.sin((t - 0.5) * math.pi) * curve
            taper = max(0.06, 1.0 - abs(t * 2.0 - 1.0) ** 1.8)
            half_width = local_width * taper * rng.uniform(0.65, 1.15)
            jitter = rng.uniform(-0.10, 0.10) * width
            verts.append((x, center_y - half_width + jitter, 0.0))
            verts.append((x, center_y + half_width + jitter, 0.0))
        for i in range(segments - 1):
            if 0.28 <= i / (segments - 1) <= 0.72 or rng.random() > 0.18:
                a = start + i * 2
                faces.append((a, a + 1, a + 3, a + 2))
                faces.append((a, a + 2, a + 3, a + 1))
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.rotation_euler.rotate_axis("Z", rng.uniform(-0.65, 0.65))
    return obj


def add_ql3_splay_defect(name, max_dim, rng):
    mesh = bpy.data.meshes.new(name + "_MESH")
    verts = []
    faces = []
    length = max_dim * rng.uniform(0.030, 0.058)
    width = max_dim * rng.uniform(0.009, 0.018)
    strip_count = rng.randint(8, 16)
    segments = rng.randint(14, 20)
    for strip_index in range(strip_count):
        start = len(verts)
        y_offset = rng.uniform(-0.62, 0.62) * width
        local_length = length * rng.uniform(0.18, 0.82)
        local_width = max_dim * rng.uniform(0.00014, 0.00045)
        curve = rng.uniform(-0.42, 0.42) * width
        x_bias = rng.uniform(-0.24, 0.24) * length
        break_a = rng.uniform(0.18, 0.40)
        break_b = rng.uniform(0.62, 0.86)
        wiggle_phase = rng.uniform(0.0, math.tau)
        for i in range(segments):
            t = i / (segments - 1)
            x = x_bias + (t * 2.0 - 1.0) * local_length * 0.5
            center_y = (
                y_offset
                + math.sin(t * math.pi * rng.uniform(0.75, 1.35)) * curve
                + math.sin(t * math.tau * rng.uniform(1.0, 2.4) + wiggle_phase) * width * 0.035
            )
            taper = max(0.12, 1.0 - abs(t * 2.0 - 1.0) ** 1.6)
            half_width = local_width * taper * rng.uniform(0.72, 1.28)
            verts.append((x, center_y - half_width, 0.0))
            verts.append((x, center_y + half_width, 0.0))
        for i in range(segments - 1):
            t = i / (segments - 1)
            if (break_a < t < break_a + 0.08 and rng.random() < 0.70) or (break_b < t < break_b + 0.06 and rng.random() < 0.55):
                continue
            if rng.random() > 0.24:
                a = start + i * 2
                faces.append((a, a + 1, a + 3, a + 2))
                faces.append((a, a + 2, a + 3, a + 1))
    center = (rng.uniform(-0.12, 0.18) * length, rng.uniform(-0.18, 0.22) * width)
    petal_count = rng.randint(5, 9)
    petal_radius = max_dim * rng.uniform(0.0022, 0.0046)
    start = len(verts)
    verts.append((center[0], center[1], 0.0))
    for index in range(petal_count * 2):
        angle = math.tau * index / (petal_count * 2) + rng.uniform(-0.18, 0.18)
        radius = petal_radius * rng.uniform(0.22, 0.88)
        verts.append((center[0] + math.cos(angle) * radius, center[1] + math.sin(angle) * radius * rng.uniform(0.36, 0.70), 0.0))
    for index in range(petal_count * 2):
        if rng.random() < 0.20:
            continue
        a = start + 1 + index
        b = start + 1 + ((index + 1) % (petal_count * 2))
        faces.append((start, a, b))
        faces.append((start, b, a))
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.rotation_euler.rotate_axis("Z", rng.uniform(-0.75, 0.75))
    return obj


def add_qc7_black_splay_defect(name, max_dim, rng):
    mesh = bpy.data.meshes.new(name + "_MESH")
    verts = []
    faces = []
    length = max_dim * rng.uniform(0.036, 0.070)
    width = max_dim * rng.uniform(0.0060, 0.0105)
    strip_count = rng.randint(12, 22)
    segments = rng.randint(18, 26)
    for strip_index in range(strip_count):
        start = len(verts)
        local_length = length * rng.uniform(0.58, 1.02)
        local_width = max_dim * rng.uniform(0.00007, 0.00022)
        y_offset = rng.uniform(-0.34, 0.34) * width
        x_offset = rng.uniform(-0.10, 0.10) * length
        curve = rng.uniform(-0.12, 0.12) * width
        for i in range(segments):
            t = i / (segments - 1)
            x = x_offset + (t * 2.0 - 1.0) * local_length * 0.5
            center_y = y_offset + math.sin((t - 0.5) * math.pi) * curve
            taper = max(0.10, 1.0 - abs(t * 2.0 - 1.0) ** 1.7)
            half_width = local_width * taper * rng.uniform(0.70, 1.12)
            verts.append((x, center_y - half_width, 0.0))
            verts.append((x, center_y + half_width, 0.0))
        for i in range(segments - 1):
            if rng.random() < 0.08:
                continue
            a = start + i * 2
            faces.append((a, a + 1, a + 3, a + 2))
            faces.append((a, a + 2, a + 3, a + 1))
    patch_radius = max_dim * rng.uniform(0.0010, 0.0022)
    start = len(verts)
    verts.append((rng.uniform(-0.10, 0.12) * length, rng.uniform(-0.18, 0.18) * width, 0.0))
    petal_count = rng.randint(6, 10)
    for index in range(petal_count):
        angle = math.tau * index / petal_count + rng.uniform(-0.18, 0.18)
        radial = patch_radius * rng.uniform(0.18, 0.95)
        verts.append((verts[start][0] + math.cos(angle) * radial, verts[start][1] + math.sin(angle) * radial * rng.uniform(0.40, 0.80), 0.0))
    for index in range(petal_count):
        if rng.random() < 0.15:
            continue
        faces.append((start, start + 1 + index, start + 1 + ((index + 1) % petal_count)))
        faces.append((start, start + 1 + ((index + 1) % petal_count), start + 1 + index))
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.rotation_euler.rotate_axis("Z", math.pi * 0.5 + rng.uniform(-0.18, 0.18))
    return obj


def add_qc71336_gray_soft_spiral_mixed_color_defect(name, max_dim, rng):
    parent = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(parent)
    parent["defect_group"] = True

    base = add_soft_irregular_mixed_color_patch(
        f"{name}_BASE",
        max_dim * rng.uniform(0.115, 0.175),
        max_dim * rng.uniform(0.080, 0.125),
        rng,
    )
    base.parent = parent
    base.location = (
        rng.uniform(-0.018, 0.018) * max_dim,
        rng.uniform(-0.016, 0.018) * max_dim,
        0.0,
    )
    base.rotation_euler.rotate_axis("Z", rng.uniform(-0.26, 0.26))

    arc_count = rng.randint(2, 4)
    for arc_index in range(arc_count):
        radius_x = max_dim * rng.uniform(0.060, 0.105)
        radius_y = max_dim * rng.uniform(0.088, 0.150)
        center_offset = (
            rng.uniform(-0.030, 0.035) * max_dim,
            rng.uniform(-0.020, 0.028) * max_dim,
            (arc_index + 1) * max_dim * 0.000012,
        )
        edge_arc = add_segmented_arc_stain(
            f"{name}_ARC_{arc_index:02d}_EDGE",
            radius_x,
            radius_y,
            max_dim * rng.uniform(0.0080, 0.0130),
            rng,
            segment_count=rng.randint(1, 3),
            soften=True,
        )
        edge_arc.parent = parent
        edge_arc.location = center_offset
        edge_arc.rotation_euler.rotate_axis("Z", rng.uniform(-0.38, 0.38))

        if rng.random() < 0.72:
            mid_arc = add_segmented_arc_stain(
                f"{name}_ARC_{arc_index:02d}_MID",
                radius_x * rng.uniform(0.96, 1.03),
                radius_y * rng.uniform(0.96, 1.03),
                max_dim * rng.uniform(0.0032, 0.0060),
                rng,
                segment_count=rng.randint(1, 2),
                soften=True,
            )
            mid_arc.parent = parent
            mid_arc.location = (
                center_offset[0] + rng.uniform(-0.006, 0.006) * max_dim,
                center_offset[1] + rng.uniform(-0.006, 0.006) * max_dim,
                center_offset[2] + max_dim * 0.000010,
            )
            mid_arc.rotation_euler = edge_arc.rotation_euler

    if rng.random() < 0.55:
        center = add_segmented_arc_stain(
            f"{name}_CENTER",
            max_dim * rng.uniform(0.045, 0.070),
            max_dim * rng.uniform(0.062, 0.094),
            max_dim * rng.uniform(0.0010, 0.0020),
            rng,
            segment_count=rng.randint(1, 2),
            soften=True,
        )
        center.parent = parent
        center.location = (
            rng.uniform(-0.010, 0.012) * max_dim,
            rng.uniform(-0.008, 0.012) * max_dim,
            max_dim * 0.000080,
        )
        center.rotation_euler.rotate_axis("Z", rng.uniform(-0.20, 0.20))

    parent.rotation_euler.rotate_axis("Z", rng.uniform(-0.10, 0.10))
    return parent


def add_soft_irregular_mixed_color_patch(name, radius_x, radius_y, rng):
    mesh = bpy.data.meshes.new(name + "_MESH")
    vertex_count = rng.randint(30, 44)
    verts = [(0.0, 0.0, 0.0)]
    inner_ring = []
    mid_ring = []
    outer_ring = []
    wave_freq = rng.uniform(1.4, 3.2)
    wave_phase = rng.uniform(0.0, math.tau)
    directional_phase = rng.uniform(0.0, math.tau)
    for index in range(vertex_count):
        angle = math.tau * index / vertex_count
        wave = 1.0 + 0.060 * math.sin(angle * wave_freq + wave_phase)
        drift = 1.0 + 0.090 * math.cos(angle - directional_phase)
        outer_noise = 1.0 + rng.uniform(-0.055, 0.065)
        inner_ring.append(len(verts))
        verts.append((math.cos(angle) * radius_x * rng.uniform(0.30, 0.45) * wave, math.sin(angle) * radius_y * rng.uniform(0.30, 0.46) * wave, 0.0))
        mid_ring.append(len(verts))
        verts.append((math.cos(angle) * radius_x * rng.uniform(0.58, 0.76) * wave * drift, math.sin(angle) * radius_y * rng.uniform(0.56, 0.78) * wave, 0.0))
        outer_ring.append(len(verts))
        verts.append((math.cos(angle) * radius_x * rng.uniform(0.94, 1.13) * wave * outer_noise, math.sin(angle) * radius_y * rng.uniform(0.88, 1.10) * wave * outer_noise, 0.0))
    faces = []
    material_indices = []
    for index in range(vertex_count):
        nxt = (index + 1) % vertex_count
        faces.append((0, inner_ring[index], inner_ring[nxt]))
        material_indices.append(0)
        faces.append((inner_ring[index], mid_ring[index], mid_ring[nxt], inner_ring[nxt]))
        material_indices.append(1)
        faces.append((mid_ring[index], outer_ring[index], outer_ring[nxt], mid_ring[nxt]))
        material_indices.append(2)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    for polygon, material_index in zip(mesh.polygons, material_indices):
        polygon.material_index = material_index
        polygon.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def add_segmented_arc_stain(name, radius_x, radius_y, width, rng, segment_count=2, soften=False):
    mesh = bpy.data.meshes.new(name + "_MESH")
    verts = []
    faces = []
    base_angle = rng.uniform(-0.28, 0.28) * math.pi
    direction = -1.0 if rng.random() < 0.5 else 1.0
    arc_span = rng.uniform(0.84, 1.35) * math.pi if soften else rng.uniform(0.95, 1.55) * math.pi
    cursor = 0.0
    for segment_index in range(segment_count):
        gap = rng.uniform(0.10, 0.24) * arc_span if segment_index > 0 else 0.0
        segment_span = rng.uniform(0.18, 0.38) * arc_span if soften else rng.uniform(0.12, 0.26) * arc_span
        start_t = cursor + gap
        end_t = min(arc_span, start_t + segment_span)
        cursor = end_t
        if end_t <= start_t:
            continue
        start = len(verts)
        local_segments = max(12, int(42 * (end_t - start_t) / arc_span))
        for index in range(local_segments + 1):
            t = index / max(local_segments, 1)
            angle = base_angle + direction * (start_t + (end_t - start_t) * t)
            wobble = 1.0 + (rng.uniform(-0.025, 0.030) if soften else rng.uniform(-0.038, 0.044))
            x = math.cos(angle) * radius_x * wobble
            y = math.sin(angle) * radius_y * wobble
            tangent_angle = angle + direction * math.pi * 0.5
            nx = math.cos(tangent_angle + math.pi * 0.5)
            ny = math.sin(tangent_angle + math.pi * 0.5)
            taper = max(0.24, math.sin(math.pi * max(0.02, min(0.98, t))) ** 0.55)
            half_width = width * taper * rng.uniform(0.78, 1.22) if soften else width * taper * rng.uniform(0.62, 1.45)
            verts.append((x + nx * half_width, y + ny * half_width, 0.0))
            verts.append((x - nx * half_width, y - ny * half_width, 0.0))
        for index in range(local_segments):
            a = start + index * 2
            faces.append((a, a + 1, a + 3, a + 2))
            faces.append((a, a + 2, a + 3, a + 1))
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def add_spiral_stain_ribbon(name, radius, width, rng, turns=1.1):
    mesh = bpy.data.meshes.new(name + "_MESH")
    verts = []
    faces = []
    segments = rng.randint(38, 58)
    handedness = -1.0 if rng.random() < 0.5 else 1.0
    phase = rng.uniform(0.0, math.tau)
    center_bias_x = rng.uniform(-0.10, 0.12) * radius
    center_bias_y = rng.uniform(-0.08, 0.08) * radius
    for index in range(segments):
        t = index / (segments - 1)
        angle = phase + handedness * (0.20 + t * turns * math.tau)
        local_radius = radius * (0.10 + 0.90 * t) * (1.0 + 0.07 * math.sin(t * math.tau * 2.0 + phase))
        x = center_bias_x + math.cos(angle) * local_radius
        y = center_bias_y + math.sin(angle) * local_radius
        tangent_angle = angle + handedness * math.pi * 0.5
        taper = max(0.18, 1.0 - abs(t - 0.52) ** 1.5 * 1.75)
        half_width = width * taper * rng.uniform(0.70, 1.25)
        nx = math.cos(tangent_angle + math.pi * 0.5)
        ny = math.sin(tangent_angle + math.pi * 0.5)
        jitter = rng.uniform(-0.18, 0.18) * width
        verts.append((x + nx * (half_width + jitter), y + ny * (half_width + jitter), 0.0))
        verts.append((x - nx * (half_width - jitter), y - ny * (half_width - jitter), 0.0))
    for index in range(segments - 1):
        if rng.random() < 0.10:
            continue
        a = index * 2
        faces.append((a, a + 1, a + 3, a + 2))
        faces.append((a, a + 2, a + 3, a + 1))
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def add_soft_ellipse_blob(name, width, height, rng, vertices=72):
    mesh = bpy.data.meshes.new(name + "_MESH")
    verts = []
    for index in range(vertices):
        angle = math.tau * index / vertices
        edge = 1.0 + rng.uniform(-0.045, 0.045)
        verts.append((math.cos(angle) * width * 0.5 * edge, math.sin(angle) * height * 0.5 * edge, 0.0))
    mesh.from_pydata(verts, [], [tuple(range(vertices))])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def make_defect_material(defect_type, defect_defaults=None, product=None, target=""):
    defect_defaults = defect_defaults or {}
    product_is_dark = False
    if product is not None and product.data.materials:
        product_is_dark = material_average_value(product.data.materials[0]) < 0.28
    product_is_dark = product_is_dark or ("black" in str(target).lower())
    colors = {
        "black_dot": (0.005, 0.004, 0.003, 1.0),
        "foreign_material": (0.64, 0.66, 0.64, 1.0) if product_is_dark else (0.02, 0.018, 0.014, 1.0),
        "splay": (0.82, 0.84, 0.82, 1.0),
        "mixed_color_contamination": (0.36, 0.34, 0.31, 1.0),
        "sink_mark": (0.18, 0.18, 0.18, 1.0),
    }
    mat = bpy.data.materials.new("GENERIC_" + defect_type.upper() + "_MAT")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    material = defect_defaults.get("material", {})
    base_color = colors.get(defect_type, colors["black_dot"])
    if is_qc71336_white_target(target) and defect_type == "foreign_material":
        base_color = (0.38, 0.34, 0.26, 1.0)
    elif is_ql3_target(target) and defect_type == "foreign_material":
        base_color = (0.66, 0.65, 0.57, 1.0)
    elif is_ql3_target(target) and defect_type == "splay":
        base_color = (0.82, 0.84, 0.80, 1.0)
    elif is_qc7_5244_black_target(target) and defect_type == "black_dot":
        base_color = (0.0015, 0.0012, 0.0010, 1.0)
    elif is_qc7_5244_black_target(target) and defect_type == "foreign_material":
        base_color = (0.70, 0.67, 0.55, 1.0)
    elif is_qc7_5244_black_target(target) and defect_type == "splay":
        base_color = (0.42, 0.43, 0.40, 1.0)
    elif is_qc71336_gray_target(target) and defect_type == "mixed_color_contamination":
        base_color = (0.34, 0.35, 0.33, 1.0)
    elif not (product_is_dark and defect_type == "foreign_material"):
        base_color = material.get("base_color", base_color)
    bsdf.inputs["Base Color"].default_value = base_color
    bsdf.inputs["Roughness"].default_value = float(material.get("roughness", 0.72))
    if defect_type == "splay" and "Alpha" in bsdf.inputs:
        if is_ql3_target(target):
            alpha = 0.66
        elif is_qc7_5244_black_target(target):
            alpha = 0.30
        else:
            alpha = 0.38
        bsdf.inputs["Alpha"].default_value = alpha
        mat.blend_method = "BLEND"
        mat.shadow_method = "HASHED"
    if defect_type == "mixed_color_contamination" and is_qc71336_gray_target(target) and "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = 0.22
        mat.blend_method = "BLEND"
        mat.shadow_method = "HASHED"
    if hasattr(mat, "surface_render_method") and defect_type == "splay":
        mat.surface_render_method = "BLENDED"
    if hasattr(mat, "surface_render_method") and defect_type == "mixed_color_contamination" and is_qc71336_gray_target(target):
        mat.surface_render_method = "BLENDED"
    return mat


def make_qc7_black_dot_material(name, base_color, roughness):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = base_color
    bsdf.inputs["Roughness"].default_value = roughness
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.24
    elif "Specular" in bsdf.inputs:
        bsdf.inputs["Specular"].default_value = 0.24
    return mat


def make_translucent_defect_material(name, base_color, alpha, roughness):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = base_color
    bsdf.inputs["Roughness"].default_value = roughness
    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = alpha
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.08
    elif "Specular" in bsdf.inputs:
        bsdf.inputs["Specular"].default_value = 0.08
    mat.blend_method = "BLEND"
    mat.shadow_method = "HASHED"
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "BLENDED"
    return mat


def make_qc71336_gray_mixed_color_materials():
    center = make_translucent_defect_material(
        "GENERIC_QC71336_GRAY_MIXED_CENTER_MAT",
        (0.325, 0.330, 0.320, 1.0),
        0.085,
        0.94,
    )
    mid = make_translucent_defect_material(
        "GENERIC_QC71336_GRAY_MIXED_MID_MAT",
        (0.360, 0.358, 0.342, 1.0),
        0.052,
        0.96,
    )
    edge = make_translucent_defect_material(
        "GENERIC_QC71336_GRAY_MIXED_EDGE_MAT",
        (0.405, 0.398, 0.380, 1.0),
        0.024,
        0.98,
    )
    return {
        "center": center,
        "mid": mid,
        "edge": edge,
    }


def material_average_value(mat):
    if mat is None or not mat.use_nodes:
        return 0.5
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        return 0.5
    color = bsdf.inputs["Base Color"].default_value
    return float(color[0] + color[1] + color[2]) / 3.0


def cleanup_defects():
    for obj in list(bpy.data.objects):
        if obj.name.startswith("GENERIC_SURFACE_PROXY_QC7_RIBBED_"):
            continue
        if obj.name.startswith("GENERIC_DEFECT_") or obj.name.startswith("GENERIC_SURFACE_PROXY"):
            bpy.data.objects.remove(obj, do_unlink=True)


def defect_mesh_objects(defect):
    if defect.type == "MESH":
        return [defect]
    return [obj for obj in bpy.data.objects if obj.type == "MESH" and obj.parent == defect]


def render_rgb(path):
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def render_mask(path, product, defect):
    original = [(obj, list(obj.data.materials)) for obj in bpy.data.objects if obj.type == "MESH"]
    black = make_emission_material("GENERIC_MASK_BLACK", (0, 0, 0, 1))
    white = make_emission_material("GENERIC_MASK_WHITE", (1, 1, 1, 1))
    defect_objects = set(defect_mesh_objects(defect))
    for obj, _ in original:
        obj.data.materials.clear()
        obj.data.materials.append(white if obj in defect_objects else black)
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    for obj, mats in original:
        obj.data.materials.clear()
        for mat in mats:
            obj.data.materials.append(mat)


def make_emission_material(name, color):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = color
    emission.inputs["Strength"].default_value = 1.0
    mat.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return mat


def bbox_from_object(camera, obj, width, height):
    scene = bpy.context.scene
    coords = []
    for mesh_obj in defect_mesh_objects(obj):
        for corner in mesh_obj.bound_box:
            co = mesh_obj.matrix_world @ Vector(corner)
            projected = world_to_camera_view(scene, camera, co)
            coords.append((projected.x, 1.0 - projected.y))
    if not coords:
        coords.append((0.5, 0.5))
    xs = [min(max(x, 0.0), 1.0) for x, _ in coords]
    ys = [min(max(y, 0.0), 1.0) for _, y in coords]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    px = min(max(0, int(round(x0 * width))), width - 1)
    py = min(max(0, int(round(y0 * height))), height - 1)
    pw = max(1, int(round((x1 - x0) * width)))
    ph = max(1, int(round((y1 - y0) * height)))
    pw = min(pw, width - px)
    ph = min(ph, height - py)
    return {
        "xywh": [px, py, pw, ph],
        "xyxy": [px, py, px + pw, py + ph],
        "area_pixels": int(pw * ph),
    }


def write_yolo_label(path, defect_type, bbox, width, height):
    x, y, w, h = bbox["xywh"]
    cls = DEFECT_CLASS_IDS.get(defect_type, 0)
    values = [
        cls,
        (x + w / 2.0) / float(width),
        (y + h / 2.0) / float(height),
        w / float(width),
        h / float(height),
    ]
    path.write_text("{0} {1:.8f} {2:.8f} {3:.8f} {4:.8f}\n".format(*values), encoding="utf-8")


def world_bbox(obj):
    coords = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    min_v = Vector((min(v.x for v in coords), min(v.y for v in coords), min(v.z for v in coords)))
    max_v = Vector((max(v.x for v in coords), max(v.y for v in coords), max(v.z for v in coords)))
    return min_v, max_v


def main_plane_frame(min_v, max_v):
    dims = max_v - min_v
    values = [float(dims.x), float(dims.y), float(dims.z)]
    normal_axis = min(range(3), key=lambda index: values[index])
    plane_axes = [index for index in range(3) if index != normal_axis]
    return {
        "normal_axis": normal_axis,
        "plane_axes": plane_axes,
        "plane_dims": [values[index] for index in plane_axes],
    }


def is_ql3_target(target):
    return "ql3" in str(target).lower()


def is_qc71336_white_target(target):
    target_lower = str(target).lower()
    return "qc71336" in target_lower and "white" in target_lower


def is_qc71336_gray_target(target):
    target_lower = str(target).lower()
    return "qc71336" in target_lower and "gray" in target_lower


def is_qc7_5244_black_target(target):
    target_lower = str(target).lower()
    return "qc7_5244" in target_lower and "black" in target_lower


def is_qc7_5244_white_target(target):
    target_lower = str(target).lower()
    return "qc7_5244" in target_lower and "white" in target_lower


def is_qc7_5244_target(target):
    target_lower = str(target).lower()
    return "qc7_5244" in target_lower


def placement_policy_for_target(target):
    if is_ql3_target(target):
        return "ql3_front_and_side_flat_planes_only_no_back"
    return "front_back_main_planes_only"


def main_plane_axis_policy_for_target(target):
    if is_ql3_target(target):
        return "ql3_fixed_front_z_plane_and_side_x_plane_with_flat_safe_windows"
    return "bbox_shortest_axis_as_front_back_normal"


def placement_frame_for_target(min_v, max_v, target, side):
    if is_ql3_target(target):
        return ql3_placement_frame(min_v, max_v, side)
    frame = main_plane_frame(min_v, max_v)
    if is_qc71336_gray_target(target):
        sign = 1.0 if side == "front" else -1.0
    else:
        sign = -1.0 if side == "front" else 1.0
    if is_qc71336_white_target(target):
        ranges = {
            frame["plane_axes"][0]: (0.32, 0.68),
            frame["plane_axes"][1]: (0.52, 0.78),
        }
    elif is_qc71336_gray_target(target):
        ranges = {
            frame["plane_axes"][0]: (0.36, 0.64),
            frame["plane_axes"][1]: (0.56, 0.76),
        }
    else:
        ranges = {}
        for index in frame["plane_axes"]:
            ranges[index] = (0.28, 0.72) if index == frame["plane_axes"][0] else (0.35, 0.65)
    frame["normal_sign"] = sign
    frame["normalized_ranges"] = ranges
    frame["placement_policy"] = placement_policy_for_target(target)
    return frame


def ql3_placement_frame(min_v, max_v, side):
    dims = max_v - min_v
    values = [float(dims.x), float(dims.y), float(dims.z)]
    if side == "side":
        normal_axis = 1
        plane_axes = [0, 2]
        ranges = {
            0: (0.20, 0.90),
            2: (0.18, 0.82),
        }
        sign = 1.0
    else:
        normal_axis = 2
        plane_axes = [0, 1]
        ranges = {
            0: (0.10, 0.36),
            1: (0.66, 0.94),
        }
        sign = -1.0
    return {
        "normal_axis": normal_axis,
        "normal_sign": sign,
        "plane_axes": plane_axes,
        "plane_dims": [values[index] for index in plane_axes],
        "normalized_ranges": ranges,
        "placement_policy": placement_policy_for_target("ql3"),
    }


def placement_window_center(min_v, max_v, frame):
    dims = max_v - min_v
    center = (min_v + max_v) * 0.5
    coords = [float(center.x), float(center.y), float(center.z)]
    for axis, value_range in frame["normalized_ranges"].items():
        coords[axis] = float(min_v[axis] + dims[axis] * ((value_range[0] + value_range[1]) * 0.5))
    normal_axis = frame["normal_axis"]
    coords[normal_axis] = float((min_v[normal_axis] + max_v[normal_axis]) * 0.5)
    return Vector(coords)


def axis_unit(axis_index, sign=1.0):
    values = [0.0, 0.0, 0.0]
    values[axis_index] = sign
    return Vector(values)


def align_plane_to_normal(obj, normal):
    up = "Y"
    if abs(float(normal.normalized().dot(Vector((0.0, 1.0, 0.0))))) > 0.95:
        up = "X"
    obj.rotation_euler = normal.to_track_quat("Z", up).to_euler()


def product_bbox_metadata(obj):
    min_v, max_v = world_bbox(obj)
    dims = max_v - min_v
    frame = main_plane_frame(min_v, max_v)
    return {
        "min": [float(min_v.x), float(min_v.y), float(min_v.z)],
        "max": [float(max_v.x), float(max_v.y), float(max_v.z)],
        "dims": [float(dims.x), float(dims.y), float(dims.z)],
        "main_plane_axis": ["x", "y", "z"][frame["normal_axis"]],
    }


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


if __name__ == "__main__":
    main()
