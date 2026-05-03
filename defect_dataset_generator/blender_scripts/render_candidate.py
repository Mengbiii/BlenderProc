import blenderproc as bproc

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def parse_args():
    parser = argparse.ArgumentParser(description="Deterministic clean material candidate renderer.")
    parser.add_argument("--blend", required=True)
    parser.add_argument("--material-json", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=768)
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--target-object", default=None)
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = argv[1:]
    return parser.parse_args(argv)


def main():
    args = parse_args()
    output_path = Path(args.output).resolve()
    metadata_path = Path(args.metadata).resolve()
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        material_params = load_material_params(args.material_json)
        blend_path = Path(args.blend).resolve()
        if not blend_path.exists():
            raise FileNotFoundError("Blend file not found: {0}".format(blend_path))

        bpy.ops.wm.open_mainfile(filepath=str(blend_path))
        warnings = []
        target_objects = find_target_mesh_objects(args.target_object)
        if not target_objects:
            raise RuntimeError("No mesh object found for candidate rendering.")

        material = create_candidate_material(material_params, warnings)
        for obj in target_objects:
            obj.data.materials.clear()
            obj.data.materials.append(material)

        bounds = compute_bounds(target_objects)
        camera = setup_camera(bounds)
        light = setup_light(bounds, material_params)
        setup_world(material_params)
        configure_render(args.width, args.height, args.samples, material_params)

        bpy.context.scene.render.filepath = str(output_path)
        bpy.ops.render.render(write_still=True)

        metadata = build_metadata(
            status="success",
            args=args,
            material_params=material_params,
            target_objects=target_objects,
            camera=camera,
            light=light,
            warnings=warnings,
            failure_reason=None,
        )
        write_json(metadata_path, metadata)
    except Exception as exc:
        metadata = {
            "schema_version": "0.1",
            "status": "failed",
            "blend_file": str(Path(args.blend).resolve()),
            "output_image": str(output_path),
            "material_json": str(Path(args.material_json).resolve()),
            "failure_reason": str(exc),
        }
        write_json(metadata_path, metadata)
        raise


def load_material_params(path):
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError("Material JSON not found: {0}".format(path))
    with path.open("r", encoding="utf-8") as f:
        params = json.load(f)
    material_params = params.get("material_parameters", params)
    scene_calibration = params.get("scene_calibration", params)
    return {
        "base_color": material_params.get("base_color", [0.78, 0.80, 0.82, 1.0]),
        "roughness": float(material_params.get("roughness", 0.5)),
        "specular": float(material_params.get("specular", material_params.get("specular_ior_level", 0.35))),
        "subsurface": float(material_params.get("subsurface", material_params.get("translucency", 0.0))),
        "noise_scale": float(material_params.get("noise_scale", 48.0)),
        "noise_strength": float(material_params.get("noise_strength", 0.0)),
        "bump_strength": float(material_params.get("bump_strength", 0.0)),
        "light_strength": float(scene_calibration.get("light_strength", 450.0)),
        "exposure": float(scene_calibration.get("exposure", 0.0)),
        "camera_profile": scene_calibration.get("camera_profile", "deterministic_ortho_front"),
        "background_color": scene_calibration.get("background_color", [0.78, 0.78, 0.78, 1.0]),
    }


def find_target_mesh_objects(target_name):
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if target_name:
        matches = [obj for obj in meshes if obj.name == target_name]
        if not matches:
            raise RuntimeError("Requested target object not found: {0}".format(target_name))
        return matches

    excluded = []
    selected = []
    for obj in meshes:
        name = obj.name.lower()
        if any(token in name for token in ["backdrop", "background", "floor", "plane", "table"]):
            excluded.append(obj.name)
            continue
        selected.append(obj)
    if selected:
        return selected
    return meshes


def create_candidate_material(params, warnings):
    mat = bpy.data.materials.new("CANDIDATE_MATERIAL")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None:
        warnings.append("Principled BSDF node missing; created material may not map parameters.")
        return mat

    set_input(bsdf, ["Base Color"], params["base_color"], warnings)
    set_input(bsdf, ["Roughness"], params["roughness"], warnings)
    set_input(bsdf, ["Specular IOR Level", "Specular"], params["specular"], warnings)
    set_input(bsdf, ["Subsurface Weight", "Subsurface"], params["subsurface"], warnings)

    if params["bump_strength"] > 0.0 or params["noise_strength"] > 0.0:
        normal_input = bsdf.inputs.get("Normal")
        if normal_input is None:
            warnings.append("Bump requested but Principled BSDF has no Normal input.")
        else:
            noise = nodes.new(type="ShaderNodeTexNoise")
            noise.inputs["Scale"].default_value = params["noise_scale"]
            noise.inputs["Detail"].default_value = 8.0
            noise.inputs["Roughness"].default_value = 0.55
            bump = nodes.new(type="ShaderNodeBump")
            bump.inputs["Strength"].default_value = max(params["bump_strength"], params["noise_strength"] * 0.5)
            bump.inputs["Distance"].default_value = max(0.003, params["noise_strength"] * 0.08)
            mat.node_tree.links.new(noise.outputs["Fac"], bump.inputs["Height"])
            mat.node_tree.links.new(bump.outputs["Normal"], normal_input)
    return mat


def set_input(node, names, value, warnings):
    for name in names:
        socket = node.inputs.get(name)
        if socket is not None:
            socket.default_value = value
            return
    warnings.append("Shader input not found: {0}".format("/".join(names)))


def compute_bounds(objects):
    points = []
    for obj in objects:
        for corner in obj.bound_box:
            points.append(obj.matrix_world @ Vector(corner))
    if not points:
        raise RuntimeError("Cannot compute bounds for empty object list.")
    min_v = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    max_v = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    center = (min_v + max_v) * 0.5
    size = max_v - min_v
    diag = max(size.length, 1.0)
    return {"min": min_v, "max": max_v, "center": center, "size": size, "diag": diag}


def setup_camera(bounds):
    bpy.ops.object.camera_add()
    camera = bpy.context.object
    center = bounds["center"]
    diag = bounds["diag"]
    camera.location = center + Vector((0.0, -diag * 1.9, diag * 0.55))
    look_at(camera, center)
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = max(bounds["size"].x, bounds["size"].z, bounds["size"].y * 0.55) * 1.35
    if camera.data.ortho_scale <= 0.0:
        camera.data.ortho_scale = diag
    bpy.context.scene.camera = camera
    return camera


def setup_light(bounds, params):
    bpy.ops.object.light_add(type="AREA")
    light = bpy.context.object
    center = bounds["center"]
    diag = bounds["diag"]
    light.location = center + Vector((0.0, -diag * 1.0, diag * 1.4))
    look_at(light, center)
    light.data.energy = params["light_strength"]
    light.data.size = max(diag * 1.8, 2.0)
    return light


def setup_world(params=None):
    params = params or {}
    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs["Color"].default_value = params.get("background_color", [0.78, 0.78, 0.78, 1.0])
        bg.inputs["Strength"].default_value = 0.8


def configure_render(width, height, samples, params):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = int(samples)
    scene.cycles.use_adaptive_sampling = False
    scene.render.resolution_x = int(width)
    scene.render.resolution_y = int(height)
    scene.render.film_transparent = False
    scene.view_settings.exposure = params["exposure"]
    scene.view_settings.gamma = 1.0
    scene.render.image_settings.file_format = "PNG"


def look_at(obj, target):
    direction = Vector(target) - obj.location
    if direction.length == 0:
        return
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def build_metadata(status, args, material_params, target_objects, camera, light, warnings, failure_reason):
    scene = bpy.context.scene
    return {
        "schema_version": "0.1",
        "status": status,
        "blend_file": str(Path(args.blend).resolve()),
        "output_image": str(Path(args.output).resolve()),
        "material_json": str(Path(args.material_json).resolve()),
        "material_parameters": material_params,
        "render": {
            "engine": scene.render.engine,
            "width": int(args.width),
            "height": int(args.height),
            "samples": int(args.samples),
            "exposure": material_params["exposure"],
            "camera_profile": material_params["camera_profile"],
        },
        "camera": {
            "type": camera.data.type,
            "location": list(camera.location),
            "rotation_euler": list(camera.rotation_euler),
            "ortho_scale": camera.data.ortho_scale,
        },
        "light": {
            "type": light.data.type,
            "location": list(light.location),
            "rotation_euler": list(light.rotation_euler),
            "strength": light.data.energy,
            "size": light.data.size,
        },
        "world": {
            "color": material_params["background_color"],
            "strength": 0.8,
        },
        "objects_rendered": [obj.name for obj in target_objects],
        "warnings": warnings,
        "failure_reason": failure_reason,
    }


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
