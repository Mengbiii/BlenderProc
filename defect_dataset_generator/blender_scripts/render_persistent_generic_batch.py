import blenderproc as bproc

import argparse
import json
import random
import shutil
import sys
from pathlib import Path

import bpy

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import render_generic_main_plane_defects as generic


def parse_args():
    parser = argparse.ArgumentParser(description="Persistent generic target renderer.")
    parser.add_argument("--target", required=True)
    parser.add_argument("--plan", required=True, help="Batch plan JSON with a samples list.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--blend", default=None)
    parser.add_argument("--model_blend", default=None)
    parser.add_argument("--stl", default=None)
    parser.add_argument("--material_profile", default=None)
    parser.add_argument("--width", type=int, default=1536)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--seed", type=int, default=100)
    parser.add_argument("--force_generic_camera", action="store_true")
    parser.add_argument("--force_generic_lighting", action="store_true")
    parser.add_argument("--preserve_materials", action="store_true")
    parser.add_argument(
        "--render_class_masks",
        action="store_true",
        help="Diagnostic mode: render one mask per defect class for cooccurrence samples.",
    )
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = argv[1:]
    return parser.parse_args(argv)


def main():
    args = parse_args()
    output_dir = Path(args.output).resolve()
    plan = load_json(Path(args.plan).resolve())
    sample_specs = list(plan.get("samples", []))
    if not sample_specs:
        raise ValueError("Persistent batch plan must contain a non-empty samples list.")

    for dirname in ["rgb", "mask", "masks", "labels_yolo", "metadata"]:
        generic.mkdir(output_dir / dirname)
    if args.render_class_masks:
        generic.mkdir(output_dir / "masks_by_class")

    bproc.init()
    defaults = generic.load_defaults()
    random.seed(args.seed)
    product = generic.load_scene_model(args)
    material_profile = generic.load_material_profile(args.material_profile)
    generic.ensure_material(
        product,
        args.target,
        defaults,
        preserve_existing=args.preserve_materials,
        material_profile=material_profile,
    )
    scene_profile = generic.inspect_scene_profile(args)
    camera = generic.setup_camera(product, args.width, args.height, scene_profile)
    generic.setup_lighting(product, camera, args.target)
    render_device_info = generic.configure_render(args.width, args.height, args.samples)

    product_initial_matrix = product.matrix_world.copy()
    samples = []
    for ordinal, spec in enumerate(sample_specs):
        sample = render_one_sample(
            args=args,
            defaults=defaults,
            output_dir=output_dir,
            product=product,
            product_initial_matrix=product_initial_matrix,
            camera=camera,
            scene_profile=scene_profile,
            spec=spec,
            ordinal=ordinal,
        )
        samples.append(sample)

    product.matrix_world = product_initial_matrix.copy()
    bpy.context.view_layer.update()
    metadata = {
        "schema_version": "persistent_generic_batch_v0.1",
        "script": str(Path(__file__).resolve()),
        "target": args.target,
        "generation_mode": "persistent_generic_batch",
        "batch_plan": str(Path(args.plan).resolve()),
        "sample_count": len(samples),
        "product_bbox": generic.product_bbox_metadata(product),
        "scene_profile": scene_profile,
        "source_paths": {"blend": args.blend, "stl": args.stl, "model_blend": args.model_blend},
        "render_width": args.width,
        "render_height": args.height,
        "cycles_samples": args.samples,
        "render_device_info": render_device_info,
        "seed": args.seed,
        "defect_generation_logic": {
            "backend": "persistent_generic_batch",
            "shared_single_generic_function": "render_generic_main_plane_defects.create_defect",
            "reference_backends_supported": False,
        },
        "mask_output_policy": {
            "merged_mask": True,
            "class_masks": bool(args.render_class_masks),
            "class_masks_default": False,
        },
        "samples": samples,
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")


def render_one_sample(args, defaults, output_dir, product, product_initial_matrix, camera, scene_profile, spec, ordinal):
    sample_id = int(spec.get("index", ordinal))
    mode = spec.get("mode", "single")
    defects = list(spec.get("defects", []))
    side = spec.get("side")
    if side is None:
        anchor_sides = spec.get("anchor_sides") or ["front"]
    elif isinstance(side, str):
        anchor_sides = [side]
    else:
        anchor_sides = list(side)
    seed = int(spec.get("seed", int(args.seed) + sample_id))
    rng = random.Random(seed)

    product.matrix_world = product_initial_matrix.copy()
    bpy.context.view_layer.update()
    generic.cleanup_defects()

    local_args = make_local_args(args, spec, sample_id, anchor_sides)

    rgb_path = output_dir / "rgb" / f"{sample_id:06d}.png"
    mask_path = output_dir / "mask" / f"{sample_id:06d}.png"
    mask_alias_path = output_dir / "masks" / f"{sample_id:06d}.png"
    label_path = output_dir / "labels_yolo" / f"{sample_id:06d}.txt"
    metadata_path = output_dir / "metadata" / f"{sample_id:06d}.json"

    if mode == "normal":
        sample = render_normal_sample(
            args=local_args,
            output_dir=output_dir,
            product=product,
            camera=camera,
            scene_profile=scene_profile,
            rng=rng,
            sample_id=sample_id,
            rgb_path=rgb_path,
            mask_path=mask_path,
            mask_alias_path=mask_alias_path,
            label_path=label_path,
            metadata_path=metadata_path,
            seed=seed,
        )
    elif mode == "cooccurrence" or len(defects) > 1:
        sample = render_cooccurrence_sample(
            args=local_args,
            defaults=defaults,
            output_dir=output_dir,
            product=product,
            camera=camera,
            scene_profile=scene_profile,
            rng=rng,
            sample_id=sample_id,
            defects=defects,
            rgb_path=rgb_path,
            mask_path=mask_path,
            mask_alias_path=mask_alias_path,
            label_path=label_path,
            metadata_path=metadata_path,
            seed=seed,
        )
    else:
        if not defects:
            raise ValueError("Single sample {0} is missing defects.".format(sample_id))
        sample = render_single_sample(
            args=local_args,
            defaults=defaults,
            output_dir=output_dir,
            product=product,
            camera=camera,
            scene_profile=scene_profile,
            rng=rng,
            sample_id=sample_id,
            defect_type=defects[0],
            rgb_path=rgb_path,
            mask_path=mask_path,
            mask_alias_path=mask_alias_path,
            label_path=label_path,
            metadata_path=metadata_path,
            seed=seed,
        )
    metadata_path.write_text(json.dumps(sample, indent=2, ensure_ascii=False), encoding="utf-8")
    return sample


def render_normal_sample(args, output_dir, product, camera, scene_profile, rng, sample_id, rgb_path, mask_path, mask_alias_path, label_path, metadata_path, seed):
    camera_side = generic.cooccurrence_camera_side(args)
    if not scene_profile["uses_existing_camera"]:
        generic.position_camera_for_side(camera, product, camera_side, args.target)
        generic.apply_camera_domain_randomization(camera, product, camera_side, args.target, rng)
    generic.ensure_camera_backdrop(product, camera, args.target)
    generic.setup_lighting(product, camera, args.target)
    generic.render_rgb(rgb_path)
    generic.write_empty_mask(mask_path, args.width, args.height)
    shutil.copyfile(mask_path, mask_alias_path)
    label_path.write_text("", encoding="utf-8")
    return {
        "image_id": sample_id,
        "rgb": str(rgb_path.relative_to(output_dir)),
        "mask": str(mask_alias_path.relative_to(output_dir)),
        "label_yolo": str(label_path.relative_to(output_dir)),
        "metadata": str(metadata_path.relative_to(output_dir)),
        "defects": [],
        "defect_types": [],
        "is_normal": True,
        "anchor_side": camera_side,
        "generation_mode": "normal",
        "persistent_backend": True,
        "seed": seed,
    }


def render_single_sample(args, defaults, output_dir, product, camera, scene_profile, rng, sample_id, defect_type, rgb_path, mask_path, mask_alias_path, label_path, metadata_path, seed):
    defect = generic.create_defect(product, args.target, defect_type, rng, args.anchor_sides, defaults)
    view_transform = generic.build_object_view_transform(args, defect)
    camera_side = view_transform["camera_side"] if view_transform["enabled"] else defect["anchor_side"]
    if not scene_profile["uses_existing_camera"]:
        generic.position_camera_for_side(camera, product, camera_side, args.target)
        if not view_transform["enabled"]:
            generic.apply_camera_domain_randomization(camera, product, camera_side, args.target, rng)
    generic.ensure_camera_backdrop(product, camera, args.target)
    generic.setup_lighting(product, camera, args.target)
    if view_transform["enabled"]:
        generic.apply_object_view_transform(product, defect, view_transform)
    generic.render_rgb(rgb_path)
    bbox = generic.bbox_from_object(camera, defect, args.width, args.height)
    generic.render_mask(mask_path, product, defect)
    shutil.copyfile(mask_path, mask_alias_path)
    generic.write_yolo_label(label_path, defect_type, bbox, args.width, args.height)
    return {
        "image_id": sample_id,
        "rgb": str(rgb_path.relative_to(output_dir)),
        "mask": str(mask_alias_path.relative_to(output_dir)),
        "label_yolo": str(label_path.relative_to(output_dir)),
        "metadata": str(metadata_path.relative_to(output_dir)),
        "defect_type": defect_type,
        "defect_type_canonical": defect_type,
        "defect_types": [defect_type],
        "defects": [{"defect_type": defect_type, "class_id": generic.DEFECT_CLASS_IDS[defect_type], "bbox": bbox}],
        "bbox": bbox,
        "anchor_side": defect.get("anchor_side"),
        "main_plane_axis": defect.get("main_plane_axis"),
        "placement_policy": defect.get("placement_policy"),
        "view_transform": view_transform,
        "generation_mode": "single",
        "persistent_backend": True,
        "seed": seed,
    }


def render_cooccurrence_sample(args, defaults, output_dir, product, camera, scene_profile, rng, sample_id, defects, rgb_path, mask_path, mask_alias_path, label_path, metadata_path, seed):
    if len(defects) < 2:
        raise ValueError("Cooccurrence sample {0} requires at least two defects.".format(sample_id))
    camera_side = generic.cooccurrence_camera_side(args)
    if not scene_profile["uses_existing_camera"]:
        generic.position_camera_for_side(camera, product, camera_side, args.target)
        if args.object_transform_mode == "none":
            generic.apply_camera_domain_randomization(camera, product, camera_side, args.target, rng)
    generic.ensure_camera_backdrop(product, camera, args.target)
    generic.setup_lighting(product, camera, args.target)

    records = generic.create_cooccurrence_defects(product, args, list(dict.fromkeys(defects)), rng, defaults, camera)
    view_transform = generic.build_object_view_transform(args, {"anchor_side": camera_side})
    if view_transform["enabled"]:
        generic.apply_object_view_transform_to_defects(product, [record["object"] for record in records], view_transform)
        for record in records:
            record["bbox"] = generic.bbox_from_object(camera, record["object"], args.width, args.height)

    generic.render_rgb(rgb_path)
    generic.render_mask_for_defects(mask_path, [record["object"] for record in records])
    shutil.copyfile(mask_path, mask_alias_path)
    sample_defects = []
    for record in records:
        if args.render_class_masks:
            class_mask_path = output_dir / "masks_by_class" / f"{sample_id:06d}_{record['defect_type']}.png"
            generic.render_mask_for_defects(class_mask_path, [record["object"]])
            record["mask_by_class"] = str(class_mask_path.relative_to(output_dir))
        sample_defects.append(
            {
                "defect_type": record["defect_type"],
                "class_id": generic.DEFECT_CLASS_IDS[record["defect_type"]],
                "bbox": record["bbox"],
                "anchor_side": record["object"].get("anchor_side"),
                "main_plane_axis": record["object"].get("main_plane_axis"),
                "placement_policy": record["object"].get("placement_policy"),
                "mask_by_class": record.get("mask_by_class"),
                "placement_warning": record.get("placement_warning"),
            }
        )
    generic.write_yolo_labels(label_path, records, args.width, args.height)
    return {
        "image_id": sample_id,
        "rgb": str(rgb_path.relative_to(output_dir)),
        "mask": str(mask_alias_path.relative_to(output_dir)),
        "label_yolo": str(label_path.relative_to(output_dir)),
        "metadata": str(metadata_path.relative_to(output_dir)),
        "defects": sample_defects,
        "defect_types": [record["defect_type"] for record in records],
        "anchor_side": camera_side,
        "view_transform": view_transform,
        "generation_mode": "multi_defect_cooccurrence",
        "persistent_backend": True,
        "seed": seed,
    }


def make_local_args(args, spec, sample_id, anchor_sides):
    return argparse.Namespace(
        target=args.target,
        width=args.width,
        height=args.height,
        samples=args.samples,
        seed=int(spec.get("seed", int(args.seed) + sample_id)),
        anchor_sides=anchor_sides,
        cooccurrence_iou_threshold=float(spec.get("cooccurrence_iou_threshold", 0.15)),
        cooccurrence_min_center_distance_px=float(spec.get("cooccurrence_min_center_distance_px", 0.0)),
        cooccurrence_max_attempts_per_defect=int(spec.get("cooccurrence_max_attempts_per_defect", 24)),
        object_transform_mode=spec.get("object_transform_mode", "none"),
        object_transform_camera_side=spec.get("object_transform_camera_side", anchor_sides[0] if anchor_sides else "front"),
        object_rotate_deg=spec.get("object_rotate_deg"),
        object_translate=spec.get("object_translate", [0.0, 0.0, 0.0]),
        render_class_masks=bool(getattr(args, "render_class_masks", False)),
    )


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    main()
