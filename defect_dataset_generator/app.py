import argparse
import json
import sys
from pathlib import Path

from core.file_manager import (
    collect_project_inspection,
    ensure_output_dir,
    load_json_file,
    resolve_path,
    validate_blend_file,
    validate_reference_images,
)
from core.defect_scheduler import check_seed_reproducibility, make_plans, write_defect_plans, zones_are_valid
from core.defect_presets import apply_black_dot_preset_to_config, load_defect_preset
from core.material_fitter import fit_material
from core.metadata_writer import write_dataset_summary, write_json
from core.model_color_profiles import get_model_color_profile, list_model_color_profiles
from core.renderer import build_generation_plan, build_preview_plan
from core.renderer import (
    run_generic_cooccurrence_backend,
    run_generic_main_plane_backend,
    run_generic_normal_backend,
    run_persistent_generic_batch_backend,
    run_qc71336_black_reference_backend,
    run_qc71336_white_foreign_reference_backend,
    run_qc75244_mixed_color_reference_backend,
    run_reference_blackdot_backend,
)
from core.similarity_metrics import compare_images, parse_roi_box


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = Path(__file__).resolve().parent


def resolve_cli_path(path_value, default_base=PROJECT_ROOT):
    path = Path(path_value)
    if path.is_absolute():
        return path.resolve()
    first = path.parts[0].lower() if path.parts else ""
    if first in {"outputs", "config"}:
        return (APP_ROOT / path).resolve()
    return (default_base / path).resolve()


def cmd_inspect(args: argparse.Namespace) -> int:
    report = collect_project_inspection(PROJECT_ROOT)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def cmd_fit_material(args: argparse.Namespace) -> int:
    real_path = resolve_cli_path(args.real)
    blend_path = validate_blend_file(resolve_cli_path(args.blend))
    out_dir = ensure_output_dir(resolve_cli_path(args.out))
    refs = validate_reference_images(real_path)

    search_space_path = resolve_cli_path(args.material_search_space) if args.material_search_space else APP_ROOT / "config" / "material_search_space.json"
    search_space = load_json_file(search_space_path)
    candidate_dir = resolve_cli_path(args.candidate_dir) if args.candidate_dir else None
    result = fit_material(
        reference_images=refs,
        blend_file=blend_path,
        output_dir=out_dir,
        search_space=search_space,
        candidates_limit=args.candidates,
        roi_mode=args.roi,
        roi_box=args.roi_box,
        roi_mask=resolve_cli_path(args.roi_mask) if args.roi_mask else None,
        resize=args.resize,
        scoring=args.scoring,
        candidate_dir=candidate_dir,
        render_candidates=args.render_candidates,
        project_root=PROJECT_ROOT,
        python_executable=Path(sys.executable),
        samples=args.samples,
        seed=args.seed,
        material_profile=args.material_profile,
        render_width=args.render_width,
        render_height=args.render_height,
        score_profile=args.score_profile,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_preview(args: argparse.Namespace) -> int:
    blend_path = validate_blend_file(resolve_cli_path(args.blend))
    material_path = resolve_cli_path(args.material)
    material = load_json_file(material_path)
    out_path = resolve_cli_path(args.out)
    plan = build_preview_plan(blend_path=blend_path, material=material, output_image=out_path)
    write_json(out_path.with_suffix(out_path.suffix + ".plan.json"), plan)
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    blend_path = validate_blend_file(resolve_cli_path(args.blend))
    material_path = resolve_cli_path(args.material)
    defect_config_path = resolve_cli_path(args.defect_config)
    out_dir = ensure_output_dir(resolve_cli_path(args.out))

    material = load_json_file(material_path)
    defect_config = load_json_file(defect_config_path)
    if args.defect_preset:
        preset_file = resolve_cli_path(args.defect_preset_file)
        preset = load_defect_preset(preset_file, args.defect_preset)
        defect_config = apply_black_dot_preset_to_config(defect_config, preset)
    if _uses_black_spot_backend(defect_config):
        plan = run_reference_blackdot_backend(
            project_root=PROJECT_ROOT,
            python_executable=Path(sys.executable),
            blend_path=blend_path,
            material=material,
            material_path=material_path,
            apply_material=args.apply_material,
            defect_config=defect_config,
            count=args.count,
            output_dir=out_dir,
            backend_model=args.backend_model,
            samples=args.samples,
            seed=args.seed,
            anchor_side=args.anchor_side,
            dry_run=args.dry_run,
        )
    else:
        plan = build_generation_plan(
            blend_path=blend_path,
            material=material,
            defect_config=defect_config,
            count=args.count,
            output_dir=out_dir,
        )
    write_json(out_dir / "generation_plan.json", plan)
    write_dataset_summary(out_dir / "dataset_summary.json", plan)
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    return 0


def cmd_compare_images(args: argparse.Namespace) -> int:
    reference_path = resolve_cli_path(args.reference)
    candidate_path = resolve_cli_path(args.candidate)
    result = compare_images(
        reference_image=reference_path,
        candidate_image=candidate_path,
        roi_mode=args.roi,
        roi_box=parse_roi_box(args.roi_box) if args.roi_box else None,
        roi_mask=resolve_cli_path(args.roi_mask) if args.roi_mask else None,
        resize=args.resize,
        score_profile=args.score_profile,
    )
    if args.out:
        out_path = resolve_cli_path(args.out)
        write_json(out_path, result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_plan_defects(args: argparse.Namespace) -> int:
    out_dir = ensure_output_dir(resolve_cli_path(args.out))
    defect_types = [item.strip() for item in args.defects.split(",") if item.strip()]
    if not defect_types and args.mode != "normal":
        raise ValueError("--defects must include at least one defect type unless --mode normal is used.")
    model_profile, defect_profiles, plans, validation = make_plans(
        model_id=args.model_profile,
        defect_types=defect_types,
        mode=args.mode,
        count=args.count,
        seed=args.seed,
        camera_profile=args.camera_profile,
    )
    same_seed_reproducible = check_seed_reproducibility(
        model_id=args.model_profile,
        defect_types=defect_types,
        mode=args.mode,
        count=args.count,
        seed=args.seed,
        camera_profile=args.camera_profile,
    )
    zones_valid = zones_are_valid(plans, model_profile)
    context = {
        "seed": args.seed,
        "mode": args.mode,
        "requested_defect_types": defect_types,
        "schema_validation_passed": validation["passed"],
        "same_seed_reproducible": same_seed_reproducible,
        "zones_valid": zones_valid,
    }
    summary = write_defect_plans(plans, out_dir, context=context)
    result = {
        "plan_schema_version": "0.1",
        "status": "planned",
        "rendering_invoked": False,
        "out_dir": str(out_dir),
        "model_id": model_profile["model_id"],
        "defects": [profile["defect_type"] for profile in defect_profiles],
        "mode": args.mode,
        "count": args.count,
        "seed": args.seed,
        "camera_profile": args.camera_profile,
        "schema_validation": validation,
        "same_seed_reproducible": same_seed_reproducible,
        "zones_valid": zones_valid,
        "summary": summary,
    }
    write_json(out_dir / "plan_defects_result.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_generate_target(args: argparse.Namespace) -> int:
    target_profile = get_model_color_profile(args.target)
    requested_defects = [item.strip() for item in args.defects.split(",") if item.strip()]
    if not requested_defects:
        requested_defects = list(target_profile.get("supported_defects", []))
    unsupported = [item for item in requested_defects if item not in target_profile.get("supported_defects", [])]
    if unsupported:
        raise ValueError(
            "Target {0} does not list these defects as supported: {1}. Supported: {2}".format(
                args.target,
                unsupported,
                target_profile.get("supported_defects", []),
            )
        )
    out_dir = ensure_output_dir(resolve_cli_path(args.out))
    plans = []
    for index, defect_type in enumerate(requested_defects):
        defect_out = out_dir / defect_type if len(requested_defects) > 1 else out_dir
        sample_seed = args.seed + index * 1000
        plan = _run_target_defect_backend(
            target_profile=target_profile,
            defect_type=defect_type,
            count=args.count,
            output_dir=defect_out,
            samples=args.samples,
            seed=sample_seed,
            anchor_sides=args.anchor_sides,
            object_transform_mode=args.object_transform_mode,
            object_transform_camera_side=args.object_transform_camera_side,
            object_rotate_deg=args.object_rotate_deg,
            object_translate=args.object_translate,
            dry_run=args.dry_run,
        )
        plans.append(plan)
    result = {
        "schema_version": "0.1",
        "status": "planned" if args.dry_run else "rendered_or_attempted",
        "generation_mode": "target_profile_generic_first_pass",
        "target": args.target,
        "target_profile": target_profile,
        "requested_defects": requested_defects,
        "count_per_defect": args.count,
        "output_dir": str(out_dir),
        "quality_goal": "coverage_first_not_visual_realism",
        "plans": plans,
    }
    write_json(out_dir / "target_generation_summary.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_generate_target_cooccurrence(args: argparse.Namespace) -> int:
    target_profile = get_model_color_profile(args.target)
    requested_defects = [item.strip() for item in args.defects.split(",") if item.strip()]
    if len(requested_defects) < 2:
        raise ValueError("--defects must contain at least two comma-separated defect types for cooccurrence generation.")
    unsupported = [item for item in requested_defects if item not in target_profile.get("supported_defects", [])]
    if unsupported:
        raise ValueError(
            "Target {0} does not list these defects as supported: {1}. Supported: {2}".format(
                args.target,
                unsupported,
                target_profile.get("supported_defects", []),
            )
        )
    backend_equivalence = _cooccurrence_backend_equivalence(target_profile, requested_defects)
    if not backend_equivalence["uses_same_single_defect_logic"] and not args.allow_generic_fallback:
        raise ValueError(
            "Cooccurrence generation would not use the same defect backend as single-defect generation for: {0}. "
            "These single-defect backends are reference/specialized, while current cooccurrence is generic-only. "
            "Use --allow-generic-fallback only for diagnostics, not production.".format(
                backend_equivalence["non_equivalent_defects"]
            )
        )
    out_dir = ensure_output_dir(resolve_cli_path(args.out))
    if backend_equivalence["cooccurrence_backend"] == "qc71336_black_reference_cooccurrence":
        plan = run_qc71336_black_reference_backend(
            project_root=PROJECT_ROOT,
            python_executable=Path(sys.executable),
            target_profile=target_profile,
            defect_type="foreign_material_splay",
            count=args.count,
            output_dir=out_dir,
            samples=args.samples,
            seed=args.seed,
            anchor_sides=args.anchor_sides,
            object_transform_mode=args.object_transform_mode,
            object_transform_camera_side=args.object_transform_camera_side,
            object_rotate_deg=args.object_rotate_deg,
            object_translate=args.object_translate,
            dry_run=args.dry_run,
        )
    else:
        plan = run_generic_cooccurrence_backend(
            project_root=PROJECT_ROOT,
            python_executable=Path(sys.executable),
            target_profile=target_profile,
            defect_types=requested_defects,
            count=args.count,
            output_dir=out_dir,
            samples=args.samples,
            seed=args.seed,
            anchor_sides=args.anchor_sides,
            object_transform_mode=args.object_transform_mode,
            object_transform_camera_side=args.object_transform_camera_side,
            object_rotate_deg=args.object_rotate_deg,
            object_translate=args.object_translate,
            render_class_masks=args.render_class_masks,
            dry_run=args.dry_run,
        )
    result = {
        "schema_version": "0.1",
        "status": "planned" if args.dry_run else "rendered_or_attempted",
        "generation_mode": "multi_defect_cooccurrence",
        "target": args.target,
        "target_profile": target_profile,
        "requested_defects": requested_defects,
        "backend_equivalence": backend_equivalence,
        "count": args.count,
        "output_dir": str(out_dir),
        "quality_goal": "cooccurrence_proof_first_not_visual_realism",
        "plan": plan,
    }
    write_json(out_dir / "target_cooccurrence_generation_summary.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_generate_target_normal(args: argparse.Namespace) -> int:
    target_profile = get_model_color_profile(args.target)
    out_dir = ensure_output_dir(resolve_cli_path(args.out))
    plan = run_generic_normal_backend(
        project_root=PROJECT_ROOT,
        python_executable=Path(sys.executable),
        target_profile=target_profile,
        count=args.count,
        output_dir=out_dir,
        samples=args.samples,
        seed=args.seed,
        anchor_sides=args.anchor_sides,
        object_transform_mode=args.object_transform_mode,
        object_transform_camera_side=args.object_transform_camera_side,
        object_rotate_deg=args.object_rotate_deg,
        object_translate=args.object_translate,
        dry_run=args.dry_run,
    )
    result = {
        "schema_version": "0.1",
        "status": "planned" if args.dry_run else "rendered_or_attempted",
        "generation_mode": "normal",
        "target": args.target,
        "target_profile": target_profile,
        "count": args.count,
        "output_dir": str(out_dir),
        "quality_goal": "normal_negative_samples",
        "plan": plan,
    }
    write_json(out_dir / "target_normal_generation_summary.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_generate_target_persistent_batch(args: argparse.Namespace) -> int:
    target_profile = get_model_color_profile(args.target)
    batch_plan = load_json_file(resolve_cli_path(args.plan))
    samples = list(batch_plan.get("samples", []))
    if not samples:
        raise ValueError("--plan must contain a non-empty samples list.")
    equivalence = _persistent_batch_backend_equivalence(target_profile, samples)
    if not equivalence["uses_same_single_defect_logic"]:
        raise ValueError(
            "Persistent generic batch only supports samples whose single-defect backend is generic_main_plane. "
            "Non-equivalent samples: {0}".format(equivalence["non_equivalent_samples"])
        )
    out_dir = ensure_output_dir(resolve_cli_path(args.out))
    normalized_plan = {
        "schema_version": batch_plan.get("schema_version", "persistent_batch_plan_v0.1"),
        "target": args.target,
        "samples": samples,
        "backend_equivalence": equivalence,
    }
    plan = run_persistent_generic_batch_backend(
        project_root=PROJECT_ROOT,
        python_executable=Path(sys.executable),
        target_profile=target_profile,
        batch_plan=normalized_plan,
        output_dir=out_dir,
        samples=args.samples,
        seed=args.seed,
        render_class_masks=args.render_class_masks,
        dry_run=args.dry_run,
    )
    result = {
        "schema_version": "0.1",
        "status": "planned" if args.dry_run else "rendered_or_attempted",
        "generation_mode": "persistent_generic_batch",
        "target": args.target,
        "target_profile": target_profile,
        "backend_equivalence": equivalence,
        "sample_count": len(samples),
        "output_dir": str(out_dir),
        "quality_goal": "persistent_batch_efficiency_with_generic_backend_equivalence",
        "plan": plan,
    }
    write_json(out_dir / "target_persistent_batch_summary.json", result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def _run_target_defect_backend(
    target_profile,
    defect_type,
    count,
    output_dir,
    samples,
    seed,
    anchor_sides,
    object_transform_mode,
    object_transform_camera_side,
    object_rotate_deg,
    object_translate,
    dry_run,
):
    target_id = target_profile["target_id"]
    backend_name = _target_defect_backend_name(target_profile, defect_type)
    if defect_type == "black_dot":
        backend_model = _blackdot_backend_model(target_id)
        if backend_model is not None:
            return run_reference_blackdot_backend(
                project_root=PROJECT_ROOT,
                python_executable=Path(sys.executable),
                blend_path=resolve_cli_path(target_profile["blend_path"]),
                material={},
                defect_config=_blackdot_defect_config(target_id),
                count=count,
                output_dir=output_dir,
                material_path=None,
                apply_material=False,
                backend_model=backend_model,
                samples=samples,
                seed=seed,
                anchor_side=(anchor_sides or target_profile.get("default_anchor_sides") or ["front"])[0],
                object_transform_mode=object_transform_mode,
                object_transform_camera_side=object_transform_camera_side,
                object_rotate_deg=object_rotate_deg,
                object_translate=object_translate,
                dry_run=dry_run,
            )
    if backend_name == "qc71336_black_reference":
        return run_qc71336_black_reference_backend(
            project_root=PROJECT_ROOT,
            python_executable=Path(sys.executable),
            target_profile=target_profile,
            defect_type=defect_type,
            count=count,
            output_dir=output_dir,
            samples=samples,
            seed=seed,
            anchor_sides=anchor_sides,
            object_transform_mode=object_transform_mode,
            object_transform_camera_side=object_transform_camera_side,
            object_rotate_deg=object_rotate_deg,
            object_translate=object_translate,
            dry_run=dry_run,
        )
    if backend_name == "qc71336_white_foreign_reference":
        return run_qc71336_white_foreign_reference_backend(
            project_root=PROJECT_ROOT,
            python_executable=Path(sys.executable),
            target_profile=target_profile,
            count=count,
            output_dir=output_dir,
            samples=samples,
            seed=seed,
            anchor_sides=anchor_sides,
            object_transform_mode=object_transform_mode,
            object_transform_camera_side=object_transform_camera_side,
            object_rotate_deg=object_rotate_deg,
            object_translate=object_translate,
            dry_run=dry_run,
        )
    if backend_name == "qc75244_mixed_color_reference":
        return run_qc75244_mixed_color_reference_backend(
            project_root=PROJECT_ROOT,
            python_executable=Path(sys.executable),
            target_profile=target_profile,
            count=count,
            output_dir=output_dir,
            samples=samples,
            seed=seed,
            anchor_sides=anchor_sides,
            object_transform_mode=object_transform_mode,
            object_transform_camera_side=object_transform_camera_side,
            object_rotate_deg=object_rotate_deg,
            object_translate=object_translate,
            dry_run=dry_run,
        )
    return run_generic_main_plane_backend(
        project_root=PROJECT_ROOT,
        python_executable=Path(sys.executable),
        target_profile=target_profile,
        defect_type=defect_type,
        count=count,
        output_dir=output_dir,
        samples=samples,
        seed=seed,
        anchor_sides=anchor_sides,
        object_transform_mode=object_transform_mode,
        object_transform_camera_side=object_transform_camera_side,
        object_rotate_deg=object_rotate_deg,
        object_translate=object_translate,
        dry_run=dry_run,
    )


def _cooccurrence_backend_equivalence(target_profile, defect_types):
    backend_by_defect = {defect_type: _target_defect_backend_name(target_profile, defect_type) for defect_type in defect_types}
    target_id = target_profile.get("target_id")
    if target_id == "qc71336_black" and set(defect_types) == {"foreign_material", "splay"}:
        return {
            "cooccurrence_backend": "qc71336_black_reference_cooccurrence",
            "single_backend_by_defect": backend_by_defect,
            "uses_shared_generic_create_defect": False,
            "uses_same_single_defect_logic": True,
            "non_equivalent_defects": [],
            "notes": [
                "QC71336 black foreign_material+splay cooccurrence uses the dedicated reference script path.",
                "The same reference functions as the accepted single-defect QC71336 black foreign_material and splay paths are used in one scene.",
            ],
        }
    non_equivalent = [
        defect_type
        for defect_type, backend_name in backend_by_defect.items()
        if backend_name != "generic_main_plane"
    ]
    return {
        "cooccurrence_backend": "generic_main_plane_cooccurrence",
        "single_backend_by_defect": backend_by_defect,
        "uses_shared_generic_create_defect": True,
        "uses_same_single_defect_logic": not non_equivalent,
        "non_equivalent_defects": non_equivalent,
        "notes": [
            "Generic single-defect and generic cooccurrence both call render_generic_main_plane_defects.create_defect().",
            "Reference/specialized single-defect backends are not yet available as same-scene cooccurrence backends.",
        ],
    }


def _persistent_batch_backend_equivalence(target_profile, samples):
    non_equivalent = []
    backend_by_sample = []
    supported_defects = set(target_profile.get("supported_defects", []))
    for ordinal, sample in enumerate(samples):
        mode = sample.get("mode", "single")
        defects = list(sample.get("defects", []))
        if mode == "normal":
            backend_by_sample.append({"index": sample.get("index", ordinal), "mode": mode, "defect_backends": {}})
            continue
        unsupported = [defect for defect in defects if defect not in supported_defects]
        if unsupported:
            raise ValueError(
                "Sample {0} requests unsupported defects for target {1}: {2}".format(
                    sample.get("index", ordinal),
                    target_profile["target_id"],
                    unsupported,
                )
            )
        defect_backends = {defect: _target_defect_backend_name(target_profile, defect) for defect in defects}
        backend_by_sample.append({"index": sample.get("index", ordinal), "mode": mode, "defect_backends": defect_backends})
        bad = {defect: backend for defect, backend in defect_backends.items() if backend != "generic_main_plane"}
        if bad:
            non_equivalent.append({"index": sample.get("index", ordinal), "mode": mode, "defect_backends": bad})
    return {
        "persistent_backend": "persistent_generic_batch",
        "sample_backend_summary": backend_by_sample,
        "uses_shared_generic_create_defect": True,
        "uses_same_single_defect_logic": not non_equivalent,
        "non_equivalent_samples": non_equivalent,
        "notes": [
            "This persistent renderer only batches samples whose single-defect backend is generic_main_plane.",
            "Reference/specialized profiles must stay on their existing scripts until a target-specific persistent adapter is implemented.",
        ],
    }


def _target_defect_backend_name(target_profile, defect_type):
    target_id = target_profile["target_id"]
    if defect_type == "black_dot" and _blackdot_backend_model(target_id) is not None:
        return "reference_blackdot"
    if target_id == "qc71336_black" and defect_type in {"foreign_material", "splay"}:
        return "qc71336_black_reference"
    if target_id == "qc71336_white" and defect_type == "foreign_material":
        return "qc71336_white_foreign_reference"
    if target_id == "qc7_5244_white" and defect_type == "mixed_color_contamination":
        return "qc75244_mixed_color_reference"
    return "generic_main_plane"


def _blackdot_backend_model(target_id):
    return {
        "p101040_blue": "P101040_blue",
        "qc71336_white": "QC71336_white",
        "qc71336_gray": "QC71336_gray",
        "qc7_5244_white": "QC75244_white",
    }.get(target_id)


def _blackdot_defect_config(target_id):
    preset_path = APP_ROOT / "config" / "black_dot_appearance_presets.json"
    preset_by_target = {
        "p101040_blue": "p101040_blue_current_backend_v1",
        "qc71336_white": "qc71336_white_legacy_sync_v1",
        "qc71336_gray": "qc71336_gray_legacy_sync_v1",
        "qc7_5244_white": "qc7_5244_white_current_backend_v1",
    }
    config = {"defects": [{"type": "black_dot"}]}
    preset_name = preset_by_target.get(target_id)
    if not preset_name or not preset_path.exists():
        return config
    preset_data = load_json_file(preset_path)
    preset = preset_data.get("presets", {}).get(preset_name, {})
    params = preset.get("backend_parameters", {})
    config["defects"][0].update(params)
    config["defects"][0]["preset_name"] = preset_name
    config["black_dot_appearance_preset"] = {
        "name": preset_name,
        "backend_parameters": params,
        "source_file": str(preset_path),
    }
    return config


def cmd_list_targets(args: argparse.Namespace) -> int:
    result = {"schema_version": "0.1", "targets": list_model_color_profiles()}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def _uses_black_spot_backend(defect_config: dict) -> bool:
    for item in defect_config.get("defects", []):
        if item.get("type") in {"black_spot", "black_dot"}:
            return True
    return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Synthetic defect dataset generator framework."
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    inspect_parser = subparsers.add_parser("inspect", help="Inspect project structure.")
    inspect_parser.set_defaults(func=cmd_inspect)

    fit_parser = subparsers.add_parser("fit-material", help="Fit material parameters.")
    fit_parser.add_argument("--real", required=True, help="Reference image or folder.")
    fit_parser.add_argument("--blend", required=True, help="Clean source .blend model.")
    fit_parser.add_argument("--out", required=True, help="Output directory.")
    fit_parser.add_argument("--candidates", type=int, default=None, help="Limit number of material candidates.")
    fit_parser.add_argument("--roi", choices=["full", "center", "auto", "manual", "mask"], default="center", help="ROI mode for real scoring.")
    fit_parser.add_argument("--roi-box", default=None, help="Manual ROI as x,y,w,h in reference image pixels. Requires --roi manual.")
    fit_parser.add_argument("--roi-mask", default=None, help="Mask image path for --roi mask. Positive pixels define material ROI.")
    fit_parser.add_argument("--resize", type=int, default=512, help="Comparison resize for real scoring.")
    fit_parser.add_argument("--scoring", choices=["mock", "real"], default="mock", help="Scoring mode.")
    fit_parser.add_argument("--candidate-dir", default=None, help="Folder with rendered candidate images for real scoring.")
    fit_parser.add_argument("--render-candidates", action="store_true", help="Render material candidates before real scoring.")
    fit_parser.add_argument("--samples", type=int, default=16, help="Cycles samples for candidate rendering.")
    fit_parser.add_argument("--seed", type=int, default=100, help="Reserved deterministic seed recorded for fitting runs.")
    fit_parser.add_argument("--material-profile", default="opaque_white_plastic", help="Material profile name recorded in candidate JSON.")
    fit_parser.add_argument("--render-width", type=int, default=512, help="Candidate render width in pixels.")
    fit_parser.add_argument("--render-height", type=int, default=384, help="Candidate render height in pixels.")
    fit_parser.add_argument("--score-profile", choices=["baseline", "plastic_material"], default="baseline", help="Similarity score profile.")
    fit_parser.add_argument("--material-search-space", default=None, help="Optional material search-space JSON. Defaults to config/material_search_space.json.")
    fit_parser.set_defaults(func=cmd_fit_material)

    preview_parser = subparsers.add_parser("preview", help="Prepare one preview render.")
    preview_parser.add_argument("--blend", required=True, help="Clean source .blend model.")
    preview_parser.add_argument("--material", required=True, help="best_material.json.")
    preview_parser.add_argument("--out", required=True, help="Preview output image path.")
    preview_parser.set_defaults(func=cmd_preview)

    generate_parser = subparsers.add_parser("generate", help="Prepare batch generation.")
    generate_parser.add_argument("--blend", required=True, help="Clean source .blend model.")
    generate_parser.add_argument("--material", required=True, help="best_material.json.")
    generate_parser.add_argument("--defect-config", required=True, help="Defect config JSON.")
    generate_parser.add_argument("--count", type=int, required=True, help="Number of images.")
    generate_parser.add_argument("--out", required=True, help="Output dataset directory.")
    generate_parser.add_argument(
        "--backend-model",
        default="P101040_blue",
        help="Model preset for reference_blend_blackdot_multi_model.py.",
    )
    generate_parser.add_argument("--samples", type=int, default=32, help="Cycles samples for real backend smoke runs.")
    generate_parser.add_argument("--seed", type=int, default=41, help="Seed for backend render.")
    generate_parser.add_argument("--dry-run", action="store_true", help="Write backend plans without running BlenderProc.")
    generate_parser.add_argument("--defect-preset", default=None, help="Optional defect appearance preset id.")
    generate_parser.add_argument(
        "--defect-preset-file",
        default="config/black_dot_appearance_presets.json",
        help="Preset JSON file used by --defect-preset.",
    )
    generate_parser.add_argument("--apply-material", action="store_true", help="Pass --material JSON into supported real backends as an object material override.")
    generate_parser.add_argument(
        "--anchor-side",
        choices=["front", "back"],
        default="front",
        help="Anchor side for the first black_spot/black_dot backend.",
    )
    generate_parser.set_defaults(func=cmd_generate)

    compare_parser = subparsers.add_parser("compare-images", help="Compare two images with material-fitting metrics.")
    compare_parser.add_argument("--reference", required=True, help="Reference image path.")
    compare_parser.add_argument("--candidate", required=True, help="Candidate image path.")
    compare_parser.add_argument("--roi", choices=["full", "center", "auto", "manual", "mask"], default="center", help="ROI mode.")
    compare_parser.add_argument("--roi-box", default=None, help="Manual ROI as x,y,w,h in reference image pixels. Requires --roi manual.")
    compare_parser.add_argument("--roi-mask", default=None, help="Mask image path for --roi mask. Positive pixels define material ROI.")
    compare_parser.add_argument("--resize", type=int, default=512, help="Comparison resize in pixels.")
    compare_parser.add_argument("--score-profile", choices=["baseline", "plastic_material"], default="baseline", help="Similarity score profile.")
    compare_parser.add_argument("--out", default=None, help="Optional output JSON path.")
    compare_parser.set_defaults(func=cmd_compare_images)

    plan_parser = subparsers.add_parser("plan-defects", help="Dry-run profile-based defect scheduling without rendering.")
    plan_parser.add_argument("--model-profile", required=True, help="Model profile id, e.g. qc7_5236.")
    plan_parser.add_argument("--defects", required=True, help="Comma-separated defect types, e.g. mixed_color_contamination.")
    plan_parser.add_argument("--mode", choices=["normal", "single_defect", "two_defect_controlled"], default="single_defect")
    plan_parser.add_argument("--count", type=int, required=True, help="Number of dry-run plans.")
    plan_parser.add_argument("--seed", type=int, default=100, help="Deterministic scheduler seed.")
    plan_parser.add_argument("--camera-profile", default=None, help="Optional fixed camera profile. If omitted, scheduler samples deterministically.")
    plan_parser.add_argument("--out", required=True, help="Output folder for defect_plan_*.json files.")
    plan_parser.set_defaults(func=cmd_plan_defects)

    targets_parser = subparsers.add_parser("list-targets", help="List model-color target profiles.")
    targets_parser.set_defaults(func=cmd_list_targets)

    target_generate_parser = subparsers.add_parser(
        "generate-target",
        help="First-pass model-color target generation using coverage-first generic backends.",
    )
    target_generate_parser.add_argument("--target", required=True, help="Target profile id, e.g. qc71336_white.")
    target_generate_parser.add_argument(
        "--defects",
        default="",
        help="Comma-separated defects. Defaults to all supported defects for the target.",
    )
    target_generate_parser.add_argument("--count", type=int, required=True, help="Number of images per defect type.")
    target_generate_parser.add_argument("--out", required=True, help="Output dataset directory.")
    target_generate_parser.add_argument("--samples", type=int, default=32, help="Cycles samples for first-pass renders.")
    target_generate_parser.add_argument("--seed", type=int, default=100, help="Base seed for generation.")
    target_generate_parser.add_argument("--dry-run", action="store_true", help="Write plans without running BlenderProc.")
    target_generate_parser.add_argument(
        "--anchor-sides",
        nargs="+",
        choices=["front", "back", "side"],
        default=None,
        help="Allowed main-plane sides for first-pass placement.",
    )
    target_generate_parser.add_argument(
        "--object-transform-mode",
        choices=["none", "keep_camera"],
        default="none",
        help="Diagnostic mode for generic backend: transform product+defect while camera/lights/environment stay fixed.",
    )
    target_generate_parser.add_argument(
        "--object-transform-camera-side",
        choices=["front", "back", "side"],
        default="front",
        help="Camera side used before --object-transform-mode keep_camera applies object rotation/translation.",
    )
    target_generate_parser.add_argument(
        "--object-rotate-deg",
        nargs=3,
        type=float,
        default=None,
        metavar=("RX", "RY", "RZ"),
        help="World-axis object rotation in degrees. Default for back keep-camera diagnostics is 180 0 0.",
    )
    target_generate_parser.add_argument(
        "--object-translate",
        nargs=3,
        type=float,
        default=[0.0, 0.0, 0.0],
        metavar=("X", "Y", "Z"),
        help="World-space object translation after rotation; camera/lights/background are unchanged.",
    )
    target_generate_parser.set_defaults(func=cmd_generate_target)

    target_cooccurrence_parser = subparsers.add_parser(
        "generate-target-cooccurrence",
        help="Generate images where multiple defect types coexist on one target instance.",
    )
    target_cooccurrence_parser.add_argument("--target", required=True, help="Target profile id, e.g. qc7_5244_black.")
    target_cooccurrence_parser.add_argument(
        "--defects",
        required=True,
        help="Comma-separated defect types to place in the same rendered image.",
    )
    target_cooccurrence_parser.add_argument("--count", type=int, required=True, help="Number of cooccurrence images.")
    target_cooccurrence_parser.add_argument("--out", required=True, help="Output dataset directory.")
    target_cooccurrence_parser.add_argument("--samples", type=int, default=32, help="Cycles samples for renders.")
    target_cooccurrence_parser.add_argument("--seed", type=int, default=100, help="Base seed for generation.")
    target_cooccurrence_parser.add_argument("--dry-run", action="store_true", help="Write plans without running BlenderProc.")
    target_cooccurrence_parser.add_argument(
        "--allow-generic-fallback",
        action="store_true",
        help="Allow diagnostic cooccurrence when single-defect generation uses reference/specialized backends.",
    )
    target_cooccurrence_parser.add_argument(
        "--anchor-sides",
        nargs="+",
        choices=["front", "back", "side"],
        default=None,
        help="Allowed main-plane sides. Use a single side when proving all defects are visible in one view.",
    )
    target_cooccurrence_parser.add_argument(
        "--object-transform-mode",
        choices=["none", "keep_camera"],
        default="none",
        help="Diagnostic mode: transform product+defects while camera/lights/environment stay fixed.",
    )
    target_cooccurrence_parser.add_argument(
        "--object-transform-camera-side",
        choices=["front", "back", "side"],
        default="front",
        help="Camera side used before --object-transform-mode keep_camera applies object rotation/translation.",
    )
    target_cooccurrence_parser.add_argument(
        "--object-rotate-deg",
        nargs=3,
        type=float,
        default=None,
        metavar=("RX", "RY", "RZ"),
        help="World-axis object rotation in degrees. Default for back keep-camera diagnostics is 180 0 0.",
    )
    target_cooccurrence_parser.add_argument(
        "--object-translate",
        nargs=3,
        type=float,
        default=[0.0, 0.0, 0.0],
        metavar=("X", "Y", "Z"),
        help="World-space object translation after rotation; camera/lights/background are unchanged.",
    )
    target_cooccurrence_parser.add_argument(
        "--render-class-masks",
        action="store_true",
        help="Diagnostic mode: also render one mask per defect class. Default is RGB + merged mask + YOLO label only.",
    )
    target_cooccurrence_parser.set_defaults(func=cmd_generate_target_cooccurrence)

    target_normal_parser = subparsers.add_parser(
        "generate-target-normal",
        help="Generate normal/no-defect images for a model-color target.",
    )
    target_normal_parser.add_argument("--target", required=True, help="Target profile id, e.g. qc7_5244_black.")
    target_normal_parser.add_argument("--count", type=int, required=True, help="Number of normal images.")
    target_normal_parser.add_argument("--out", required=True, help="Output dataset directory.")
    target_normal_parser.add_argument("--samples", type=int, default=32, help="Cycles samples for renders.")
    target_normal_parser.add_argument("--seed", type=int, default=100, help="Base seed for generation.")
    target_normal_parser.add_argument("--dry-run", action="store_true", help="Write plans without running BlenderProc.")
    target_normal_parser.add_argument(
        "--anchor-sides",
        nargs="+",
        choices=["front", "back", "side"],
        default=None,
        help="Allowed sides for normal-image camera placement.",
    )
    target_normal_parser.add_argument(
        "--object-transform-mode",
        choices=["none", "keep_camera"],
        default="none",
        help="Diagnostic mode: transform product while camera/lights/environment stay fixed.",
    )
    target_normal_parser.add_argument(
        "--object-transform-camera-side",
        choices=["front", "back", "side"],
        default="front",
        help="Camera side used before --object-transform-mode keep_camera applies object rotation/translation.",
    )
    target_normal_parser.add_argument(
        "--object-rotate-deg",
        nargs=3,
        type=float,
        default=None,
        metavar=("RX", "RY", "RZ"),
        help="World-axis object rotation in degrees.",
    )
    target_normal_parser.add_argument(
        "--object-translate",
        nargs=3,
        type=float,
        default=[0.0, 0.0, 0.0],
        metavar=("X", "Y", "Z"),
        help="World-space object translation after rotation; camera/lights/background are unchanged.",
    )
    target_normal_parser.set_defaults(func=cmd_generate_target_normal)

    target_persistent_parser = subparsers.add_parser(
        "generate-target-persistent-batch",
        help="Run a generic-equivalent mixed sample plan inside one BlenderProc process.",
    )
    target_persistent_parser.add_argument("--target", required=True, help="Target profile id, e.g. qc7_5244_black.")
    target_persistent_parser.add_argument(
        "--plan",
        required=True,
        help="Persistent batch plan JSON. Samples may be normal, single, or cooccurrence.",
    )
    target_persistent_parser.add_argument("--out", required=True, help="Output dataset directory.")
    target_persistent_parser.add_argument("--samples", type=int, default=32, help="Cycles samples for renders.")
    target_persistent_parser.add_argument("--seed", type=int, default=100, help="Base seed recorded for the persistent run.")
    target_persistent_parser.add_argument(
        "--render-class-masks",
        action="store_true",
        help="Diagnostic mode: also render one mask per defect class. Default is RGB + merged mask + YOLO label only.",
    )
    target_persistent_parser.add_argument("--dry-run", action="store_true", help="Write plans without running BlenderProc.")
    target_persistent_parser.set_defaults(func=cmd_generate_target_persistent_batch)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
