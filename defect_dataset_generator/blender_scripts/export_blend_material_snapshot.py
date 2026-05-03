import blenderproc as bproc

import argparse
import json
import sys
from pathlib import Path

import bpy


def parse_args():
    parser = argparse.ArgumentParser(description="Export a lightweight snapshot of Principled material parameters from a .blend file.")
    parser.add_argument("--blend", required=True)
    parser.add_argument("--out", required=True)
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = argv[1:]
    return parser.parse_args(argv)


def main():
    args = parse_args()
    blend_path = Path(args.blend).resolve()
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not blend_path.exists():
        raise FileNotFoundError("Blend file not found: {0}".format(blend_path))

    bpy.ops.wm.open_mainfile(filepath=str(blend_path))
    materials = []
    for mat in bpy.data.materials:
        info = {
            "name": mat.name,
            "use_nodes": bool(mat.use_nodes),
            "diffuse_color": _to_json_value(getattr(mat, "diffuse_color", None)),
            "blend_method": getattr(mat, "blend_method", None),
            "surface_render_method": getattr(mat, "surface_render_method", None),
            "node_tree": None,
        }
        bsdf = _find_principled(mat)
        if bsdf is not None:
            info["principled_summary"] = {
                "base_color": _socket_value(bsdf, ["Base Color"]),
                "roughness": _socket_value(bsdf, ["Roughness"]),
                "specular": _socket_value(bsdf, ["Specular IOR Level", "Specular"]),
                "metallic": _socket_value(bsdf, ["Metallic"]),
                "alpha": _socket_value(bsdf, ["Alpha"]),
                "normal_linked": _is_linked(bsdf, ["Normal"]),
            }
        else:
            info["principled_summary"] = None
        if mat.use_nodes and mat.node_tree is not None:
            info["node_tree"] = _export_node_tree(mat)
        materials.append(info)

    objects = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        material_slots = []
        for index, slot in enumerate(obj.material_slots):
            material_slots.append({
                "slot_index": index,
                "slot_name": slot.name,
                "material": slot.material.name if slot.material is not None else None,
            })
        material_index_counts = {}
        if getattr(obj.data, "polygons", None) is not None:
            for poly in obj.data.polygons:
                key = str(int(poly.material_index))
                material_index_counts[key] = material_index_counts.get(key, 0) + 1
        objects.append({
            "name": obj.name,
            "mesh_name": obj.data.name if obj.data else None,
            "material_slots": material_slots,
            "material_index_counts": material_index_counts,
            "active_material": obj.active_material.name if obj.active_material else None,
            "object_color": _to_json_value(getattr(obj, "color", None)),
        })

    out = {
        "schema_version": "0.1",
        "blend_file": str(blend_path),
        "material_count": len(materials),
        "materials": materials,
        "mesh_objects": objects,
    }
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def _find_principled(mat):
    if not mat.use_nodes or mat.node_tree is None:
        return None
    for node in mat.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            return node
    return None


def _export_node_tree(mat):
    nodes = []
    links = []
    tree = mat.node_tree
    for node in tree.nodes:
        node_info = {
            "name": node.name,
            "label": node.label,
            "type": node.type,
            "bl_idname": node.bl_idname,
            "location": [float(node.location.x), float(node.location.y)],
            "inputs": {},
            "outputs": {},
            "extra": _node_extra(node),
        }
        for socket in node.inputs:
            node_info["inputs"][socket.name] = {
                "type": socket.type,
                "is_linked": bool(socket.is_linked),
                "default_value": _to_json_value(getattr(socket, "default_value", None)),
            }
        for socket in node.outputs:
            node_info["outputs"][socket.name] = {
                "type": socket.type,
                "is_linked": bool(socket.is_linked),
                "default_value": _to_json_value(getattr(socket, "default_value", None)),
            }
        nodes.append(node_info)
    for link in tree.links:
        links.append({
            "from_node": link.from_node.name,
            "from_socket": link.from_socket.name,
            "to_node": link.to_node.name,
            "to_socket": link.to_socket.name,
        })
    return {"nodes": nodes, "links": links}


def _node_extra(node):
    extra = {}
    if node.type == "TEX_IMAGE":
        image = getattr(node, "image", None)
        extra["image_name"] = image.name if image else None
        extra["image_filepath"] = bpy.path.abspath(image.filepath) if image and image.filepath else None
        extra["colorspace"] = image.colorspace_settings.name if image else None
        extra["extension"] = getattr(node, "extension", None)
        extra["projection"] = getattr(node, "projection", None)
    elif node.type == "TEX_NOISE":
        for name in ["Scale", "Detail", "Roughness", "Distortion"]:
            socket = node.inputs.get(name)
            extra[name.lower()] = _to_json_value(getattr(socket, "default_value", None)) if socket else None
    elif node.type == "BUMP":
        for name in ["Strength", "Distance", "Height"]:
            socket = node.inputs.get(name)
            extra[name.lower()] = _to_json_value(getattr(socket, "default_value", None)) if socket else None
    elif node.type == "VALTORGB":
        ramp = getattr(node, "color_ramp", None)
        if ramp:
            extra["interpolation"] = ramp.interpolation
            extra["elements"] = [
                {
                    "position": float(element.position),
                    "color": _to_json_value(element.color),
                }
                for element in ramp.elements
            ]
    elif node.type in {"MAPPING", "TEX_COORD", "BSDF_PRINCIPLED", "OUTPUT_MATERIAL"}:
        extra["note"] = "key_shader_node"
    return extra


def _socket_value(node, names):
    for name in names:
        socket = node.inputs.get(name)
        if socket is not None:
            value = socket.default_value
            try:
                return [float(v) for v in value]
            except TypeError:
                return float(value)
    return None


def _is_linked(node, names):
    for name in names:
        socket = node.inputs.get(name)
        if socket is not None:
            return bool(socket.is_linked)
    return None


def _to_json_value(value):
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    try:
        return [float(v) for v in value]
    except TypeError:
        return str(value)


if __name__ == "__main__":
    main()
