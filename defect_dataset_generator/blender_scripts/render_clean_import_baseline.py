import blenderproc as bproc

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy


def parse_args():
    parser = argparse.ArgumentParser(description="Render a clean imported model baseline without defects or material override.")
    parser.add_argument("--backend-script", required=True)
    parser.add_argument("--model", default="QC75244_white")
    parser.add_argument("--blend", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--width", type=int, default=1536)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--samples", type=int, default=16)
    parser.add_argument("--save-blend", default=None)
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = argv[1:]
    return parser.parse_args(argv)


def main():
    args = parse_args()
    backend = _load_backend(Path(args.backend_script))
    model_name = backend.canonical_model_name(args.model)
    preset = backend.MODEL_PRESETS[model_name]
    output_path = Path(args.output).resolve()
    metadata_path = Path(args.metadata).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    backend_args = SimpleNamespace(
        model=model_name,
        blend=str(Path(args.blend).resolve()),
        stl=None,
        model_blend=None,
        material_json=None,
        width=int(args.width),
        height=int(args.height),
        samples=int(args.samples),
    )
    setup = backend.setup_model(backend_args, preset)
    objects = setup["objects"]
    camera = setup["camera"]
    gpu_info = backend.configure_render(args.samples, args.width, args.height)
    backend.render_still(output_path)

    blend_path = None
    if args.save_blend:
        blend_path = Path(args.save_blend).resolve()
        blend_path.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

    metadata = {
        "schema_version": "0.1",
        "purpose": "clean_import_baseline_no_defect_no_material_override",
        "backend_script": str(Path(args.backend_script).resolve()),
        "model": model_name,
        "source_paths": setup.get("source_paths"),
        "material_info": setup.get("material_info"),
        "render_device": gpu_info,
        "render": {
            "width": int(args.width),
            "height": int(args.height),
            "samples": int(args.samples),
        },
        "objects": [_object_summary(obj) for obj in objects],
        "camera": {
            "name": camera.name,
            "lens": float(camera.data.lens),
            "location": [float(v) for v in camera.location],
            "rotation_euler": [float(v) for v in camera.rotation_euler],
            "shift_x": float(camera.data.shift_x),
            "shift_y": float(camera.data.shift_y),
        },
        "output_image": str(output_path),
        "saved_blend": str(blend_path) if blend_path else None,
        "notes": [
            "No black-dot object was created.",
            "No external material JSON was applied.",
            "This checks the baseline imported geometry and scene setup only."
        ],
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_backend(path):
    path = path.resolve()
    spec = importlib.util.spec_from_file_location("reference_blend_blackdot_multi_model", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _object_summary(obj):
    mat_names = [slot.material.name if slot.material is not None else None for slot in obj.material_slots]
    return {
        "name": obj.name,
        "type": obj.type,
        "mesh": obj.data.name if getattr(obj, "data", None) else None,
        "vertex_count": len(obj.data.vertices) if obj.type == "MESH" else None,
        "polygon_count": len(obj.data.polygons) if obj.type == "MESH" else None,
        "materials": mat_names,
        "location": [float(v) for v in obj.location],
        "rotation_euler": [float(v) for v in obj.rotation_euler],
        "scale": [float(v) for v in obj.scale],
    }


if __name__ == "__main__":
    main()
