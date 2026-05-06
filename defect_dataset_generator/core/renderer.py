from pathlib import Path
import struct
import json
import shutil
import subprocess
from typing import Any, Dict

from core.background_randomizer import build_background_settings
from core.camera_randomizer import build_camera_settings
from core.defect_generator import normalize_defect_config
from core.light_randomizer import build_light_settings
from core.metadata_writer import write_dataset_summary, write_json


def build_preview_plan(blend_path: Path, material: Dict[str, Any], output_image: Path) -> Dict[str, Any]:
    output_image.parent.mkdir(parents=True, exist_ok=True)
    return {
        "status": "render_not_started",
        "backend": "BlenderProc wrapper placeholder",
        "blend_file": str(blend_path),
        "output_image": str(output_image),
        "material_parameters": material.get("material_parameters", material),
        "camera": build_camera_settings("fixed"),
        "lighting": build_light_settings("fixed"),
        "background": build_background_settings("fixed"),
        "next_backend_script": "blender_scripts/render_candidate.py",
    }


def build_generation_plan(
    blend_path: Path,
    material: Dict[str, Any],
    defect_config: Dict[str, Any],
    count: int,
    output_dir: Path,
) -> Dict[str, Any]:
    if count < 1:
        raise ValueError("--count must be >= 1")
    normalized_defects = normalize_defect_config(defect_config)
    samples = []
    for index in range(count):
        samples.append(
            {
                "index": index,
                "rgb": str(output_dir / "rgb" / f"{index:06d}.png"),
                "mask": str(output_dir / "masks" / f"{index:06d}.png"),
                "label_yolo": str(output_dir / "labels_yolo" / f"{index:06d}.txt"),
                "metadata": str(output_dir / "metadata" / f"{index:06d}.json"),
                "status": "planned_only",
            }
        )
    for dirname in ["rgb", "masks", "labels_yolo", "metadata"]:
        (output_dir / dirname).mkdir(parents=True, exist_ok=True)
    return {
        "status": "planned_only",
        "backend": "BlenderProc wrapper placeholder",
        "blend_file": str(blend_path),
        "output_dir": str(output_dir),
        "count": count,
        "material_parameters": material.get("material_parameters", material),
        "defect_config": normalized_defects,
        "camera": build_camera_settings(defect_config.get("camera_mode", "randomized")),
        "lighting": build_light_settings(defect_config.get("lighting_mode", "randomized")),
        "background": build_background_settings(defect_config.get("background_mode", "randomized")),
        "samples": samples,
        "next_backend_script": "blender_scripts/render_dataset.py",
    }


def run_reference_blackdot_backend(
    project_root,
    python_executable,
    blend_path,
    material,
    defect_config,
    count,
    output_dir,
    material_path=None,
    apply_material=False,
    backend_model="P101040_blue",
    samples=32,
    seed=41,
    anchor_side="front",
    object_transform_mode="none",
    object_transform_camera_side="front",
    object_rotate_deg=None,
    object_translate=None,
    defect_count_max=1,
    dry_run=False,
):
    if count < 1:
        raise ValueError("--count must be >= 1")
    if int(defect_count_max or 1) < 1:
        raise ValueError("--defect-count-max must be >= 1")
    normalized_defects = normalize_defect_config(defect_config)
    backend_defect_config = _blackdot_only_defect_config(normalized_defects)
    backend_script = project_root / "examples" / "my_project" / "reference_blend_blackdot_multi_model.py"
    blenderproc_cli = project_root / "cli.py"
    raw_output_dir = output_dir / "_backend" / "reference_blackdot"
    raw_output_dir.mkdir(parents=True, exist_ok=True)
    _ensure_framework_output_dirs(output_dir)

    log = {
        "backend_script": str(backend_script),
        "output_folder": str(raw_output_dir),
        "framework_output_folder": str(output_dir),
        "material_path": str(material_path) if material_path else None,
        "material_override_applied": bool(apply_material and material_path),
        "files_produced": [],
        "runs": [],
        "failure_reason": None,
        "execution_mode": "python cli.py run, using the local BlenderProc CLI entry point",
    }

    planned_samples = []
    successful_samples = []
    failed_samples = []
    seeds_used = [int(seed) + sample_index for sample_index in range(count)]
    batch_raw_dir = raw_output_dir / "batch_000000"
    batch_command = _build_reference_blackdot_command(
        python_executable=python_executable,
        blenderproc_cli=blenderproc_cli,
        backend_script=backend_script,
        backend_model=backend_model,
        raw_output_dir=batch_raw_dir,
        count=count,
        samples=samples,
        seed=seed,
        anchor_side=anchor_side,
        blend_path=blend_path,
        material_path=material_path if apply_material else None,
        defect_config=backend_defect_config,
        object_transform_mode=object_transform_mode,
        object_transform_camera_side=object_transform_camera_side,
        object_rotate_deg=object_rotate_deg,
        object_translate=object_translate,
        defect_count_max=defect_count_max,
    )
    commands = [batch_command]
    for sample_index in range(count):
        final_paths = _framework_sample_paths(output_dir, sample_index)
        planned_samples.append(
            {
                "index": sample_index,
                "seed": seeds_used[sample_index],
                "rgb": str(final_paths["rgb"]),
                "mask": str(final_paths["mask"]),
                "label_yolo": str(final_paths["label_yolo"]),
                "metadata": str(final_paths["metadata"]),
                "status": "planned_only" if dry_run else "pending",
                "backend_command": batch_command,
            }
        )

    if dry_run:
        plan = _build_backend_plan(
            status="dry_run",
            backend_script=backend_script,
            commands=commands,
            blend_path=blend_path,
            output_dir=output_dir,
            raw_output_dir=raw_output_dir,
            count=count,
            material=material,
            material_path=material_path,
            apply_material=apply_material,
            defect_config=backend_defect_config,
            source_defect_config=defect_config,
            samples=planned_samples,
            failed_samples=[],
            backend_model=backend_model,
            anchor_side=anchor_side,
            seeds_used=seeds_used,
            backend_log=output_dir / "backend_run_log.json",
        )
        plan["total_succeeded"] = 0
        plan["total_failed"] = 0
        plan["total_planned"] = count
        log["commands"] = commands
        log["dry_run"] = True
        write_json(output_dir / "backend_run_log.json", log)
        write_json(output_dir / "generation_plan.json", plan)
        write_dataset_summary(output_dir / "dataset_summary.json", plan)
        return plan

    try:
        run_record = {
            "mode": "batch",
            "sample_count": count,
            "seed": seed,
            "command": batch_command,
            "raw_output_dir": str(batch_raw_dir),
        }
        completed = subprocess.run(
            batch_command,
            cwd=str(project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )
        run_record["returncode"] = completed.returncode
        run_record["stdout"] = completed.stdout
        log["runs"].append(run_record)
        if completed.returncode != 0:
            raise RuntimeError("batch backend returned {0}".format(completed.returncode))

        adapter_result = adapt_reference_blackdot_outputs(
            raw_output_dir=batch_raw_dir,
            framework_output_dir=output_dir,
            start_index=0,
            backend_model=backend_model,
            anchor_side=anchor_side,
            seed=seed,
            material_path=material_path,
            apply_material=apply_material,
        )
        log["files_produced"].extend(adapter_result["files_produced"])
        sample_by_index = {int(sample["index"]): sample for sample in adapter_result["samples"]}
        for sample_index in range(count):
            sample = sample_by_index.get(sample_index)
            if sample is None:
                failed_samples.append(
                    {
                        "index": sample_index,
                        "seed": seeds_used[sample_index],
                        "attempts": 1,
                        "errors": ["batch backend did not produce this sample"],
                    }
                )
                continue
            try:
                if len(sample.get("defects", [])) > 1:
                    quality = run_cooccurrence_quality_checks(sample, len(sample.get("defects", [])))
                else:
                    quality = run_sample_quality_checks(sample)
                sample["quality_checks"] = quality
                successful_samples.append(sample)
            except Exception as exc:
                failed_samples.append(
                    {
                        "index": sample_index,
                        "seed": sample.get("seed", seeds_used[sample_index]),
                        "attempts": 1,
                        "errors": [str(exc)],
                    }
                )

        status = "rendered" if not failed_samples else ("partial" if successful_samples else "failed")
        log["failure_reason"] = None if not failed_samples else "One or more samples failed after batch quality checks."
        write_json(output_dir / "backend_run_log.json", log)
        plan = _build_backend_plan(
            status=status,
            backend_script=backend_script,
            commands=commands,
            blend_path=blend_path,
            output_dir=output_dir,
            raw_output_dir=raw_output_dir,
            count=count,
            material=material,
            material_path=material_path,
            apply_material=apply_material,
            defect_config=backend_defect_config,
            source_defect_config=defect_config,
            samples=successful_samples,
            failed_samples=failed_samples,
            backend_model=backend_model,
            anchor_side=anchor_side,
            seeds_used=seeds_used,
            backend_log=output_dir / "backend_run_log.json",
        )
        write_json(output_dir / "generation_plan.json", plan)
        write_dataset_summary(output_dir / "dataset_summary.json", plan)
        return plan
    except Exception as exc:
        log["failure_reason"] = str(exc)
        write_json(output_dir / "backend_run_log.json", log)
        return _failed_backend_plan(output_dir, backend_script, commands, log, backend_defect_config)


def run_generic_main_plane_backend(
    project_root,
    python_executable,
    target_profile,
    defect_type,
    count,
    output_dir,
    samples=32,
    seed=100,
    anchor_sides=None,
    object_transform_mode="none",
    object_transform_camera_side="front",
    object_rotate_deg=None,
    object_translate=None,
    defect_parameter_overrides=None,
    defect_count_max=1,
    dry_run=False,
):
    if count < 1:
        raise ValueError("--count must be >= 1")
    if int(defect_count_max or 1) < 1:
        raise ValueError("--defect-count-max must be >= 1")
    anchor_sides = anchor_sides or target_profile.get("default_anchor_sides") or ["front", "back"]
    backend_script = project_root / "defect_dataset_generator" / "blender_scripts" / "render_generic_main_plane_defects.py"
    blenderproc_cli = project_root / "cli.py"
    raw_output_dir = output_dir / "_backend" / "generic_main_plane"
    raw_output_dir.mkdir(parents=True, exist_ok=True)
    _ensure_framework_output_dirs(output_dir)
    command = [
        str(python_executable),
        str(blenderproc_cli),
        "run",
        str(backend_script),
        "--",
        "--target",
        target_profile["target_id"],
        "--defect_type",
        defect_type,
        "--output",
        str(raw_output_dir),
        "--num",
        str(count),
        "--start_index",
        "0",
        "--samples",
        str(samples),
        "--seed",
        str(seed),
        "--anchor_sides",
    ]
    command.extend(anchor_sides)
    if object_transform_mode != "none":
        command.extend(["--object_transform_mode", object_transform_mode])
        command.extend(["--object_transform_camera_side", object_transform_camera_side])
        if object_rotate_deg is not None:
            command.extend(["--object_rotate_deg", *[str(value) for value in object_rotate_deg]])
        if object_translate is not None:
            command.extend(["--object_translate", *[str(value) for value in object_translate]])
    model_blend_path = _profile_path(project_root, target_profile.get("model_blend_path"))
    blend_path = _profile_path(project_root, target_profile.get("blend_path"))
    stl_path = None if model_blend_path else _profile_path(project_root, target_profile.get("stl_path"))
    if blend_path:
        command.extend(["--blend", str(blend_path)])
    if model_blend_path:
        command.extend(["--model_blend", str(model_blend_path)])
    if stl_path:
        command.extend(["--stl", str(stl_path)])
    if target_profile.get("force_generic_camera"):
        command.append("--force_generic_camera")
    if target_profile.get("force_generic_lighting"):
        command.append("--force_generic_lighting")
    material_mode = (target_profile.get("material_source") or {}).get("mode", "")
    if "embedded" in material_mode or "reference_override" in material_mode:
        command.append("--preserve_materials")
    material_profile_path = _profile_path(project_root, (target_profile.get("material_source") or {}).get("path"))
    if material_profile_path:
        command.extend(["--material_profile", str(material_profile_path)])
    defect_params_path = _write_defect_parameter_overrides(raw_output_dir, defect_parameter_overrides)
    if defect_params_path:
        command.extend(["--defect_params_json", str(defect_params_path)])
    if int(defect_count_max or 1) > 1:
        command.extend(["--defect_count_max", str(int(defect_count_max))])

    log = {
        "backend_script": str(backend_script),
        "output_folder": str(raw_output_dir),
        "framework_output_folder": str(output_dir),
        "target_profile": target_profile,
        "defect_type": defect_type,
        "object_transform_mode": object_transform_mode,
        "object_transform_camera_side": object_transform_camera_side,
        "object_rotate_deg": object_rotate_deg,
        "object_translate": object_translate,
        "defect_parameter_overrides": defect_parameter_overrides or {},
        "defect_count_max": int(defect_count_max or 1),
        "command": command,
        "dry_run": bool(dry_run),
        "failure_reason": None,
    }
    if dry_run:
        plan = _build_generic_backend_plan(
            status="dry_run",
            backend_script=backend_script,
            command=command,
            output_dir=output_dir,
            raw_output_dir=raw_output_dir,
            target_profile=target_profile,
            defect_type=defect_type,
            count=count,
            samples=[],
            failed_samples=[],
            seed=seed,
            anchor_sides=anchor_sides,
            samples_requested=samples,
        )
        write_json(output_dir / "backend_run_log.json", log)
        write_json(output_dir / "generation_plan.json", plan)
        write_dataset_summary(output_dir / "dataset_summary.json", plan)
        return plan

    completed = subprocess.run(
        command,
        cwd=str(project_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    log["returncode"] = completed.returncode
    log["stdout"] = completed.stdout
    if completed.returncode != 0:
        log["failure_reason"] = "generic backend returned {0}".format(completed.returncode)
        write_json(output_dir / "backend_run_log.json", log)
        plan = _build_generic_backend_plan(
            status="failed",
            backend_script=backend_script,
            command=command,
            output_dir=output_dir,
            raw_output_dir=raw_output_dir,
            target_profile=target_profile,
            defect_type=defect_type,
            count=count,
            samples=[],
            failed_samples=[{"index": None, "seed": seed, "errors": [log["failure_reason"]]}],
            seed=seed,
            anchor_sides=anchor_sides,
            samples_requested=samples,
        )
        write_json(output_dir / "generation_plan.json", plan)
        write_dataset_summary(output_dir / "dataset_summary.json", plan)
        return plan

    _binarize_mask_outputs(raw_output_dir, threshold=10)
    adapter_result = adapt_reference_blackdot_outputs(
        raw_output_dir=raw_output_dir,
        framework_output_dir=output_dir,
        start_index=0,
        backend_model=target_profile["target_id"],
        anchor_side=",".join(anchor_sides),
        seed=seed,
        material_path=None,
        apply_material=False,
    )
    successful_samples = []
    failed_samples = []
    for sample in adapter_result["samples"]:
        try:
            expected_defect_count = len(sample.get("defects") or [])
            if expected_defect_count > 1:
                quality = run_cooccurrence_quality_checks(sample, expected_defect_count)
            else:
                quality = run_sample_quality_checks(sample)
            sample["quality_checks"] = quality
            successful_samples.append(sample)
        except Exception as exc:
            failed_samples.append(
                {
                    "index": sample.get("index"),
                    "seed": sample.get("seed"),
                    "attempts": 1,
                    "errors": [str(exc)],
                }
            )
    log["files_produced"] = adapter_result["files_produced"]
    status = "rendered" if not failed_samples else ("partial" if successful_samples else "failed")
    log["failure_reason"] = None if not failed_samples else "One or more samples failed after backend quality checks."
    write_json(output_dir / "backend_run_log.json", log)
    plan = _build_generic_backend_plan(
        status=status,
        backend_script=backend_script,
        command=command,
        output_dir=output_dir,
        raw_output_dir=raw_output_dir,
        target_profile=target_profile,
        defect_type=defect_type,
        count=count,
        samples=successful_samples,
        failed_samples=failed_samples,
        seed=seed,
        anchor_sides=anchor_sides,
        samples_requested=samples,
    )
    write_json(output_dir / "generation_plan.json", plan)
    write_dataset_summary(output_dir / "dataset_summary.json", plan)
    return plan


def run_generic_cooccurrence_backend(
    project_root,
    python_executable,
    target_profile,
    defect_types,
    count,
    output_dir,
    samples=32,
    seed=100,
    anchor_sides=None,
    object_transform_mode="none",
    object_transform_camera_side="front",
    object_rotate_deg=None,
    object_translate=None,
    defect_parameter_overrides=None,
    render_class_masks=False,
    dry_run=False,
):
    if count < 1:
        raise ValueError("--count must be >= 1")
    if not defect_types:
        raise ValueError("--defects must include at least one defect type")
    anchor_sides = anchor_sides or target_profile.get("default_anchor_sides") or ["front", "back"]
    backend_script = project_root / "defect_dataset_generator" / "blender_scripts" / "render_generic_main_plane_defects.py"
    blenderproc_cli = project_root / "cli.py"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dirs = ["rgb", "masks", "mask", "labels_yolo", "metadata"]
    if render_class_masks:
        output_dirs.append("masks_by_class")
    for dirname in output_dirs:
        (output_dir / dirname).mkdir(parents=True, exist_ok=True)

    command = [
        str(python_executable),
        str(blenderproc_cli),
        "run",
        str(backend_script),
        "--",
        "--target",
        target_profile["target_id"],
        "--defect_type",
        defect_types[0],
        "--cooccurrence_defects",
    ]
    command.extend(defect_types)
    command.extend(
        [
            "--output",
            str(output_dir),
            "--num",
            str(count),
            "--start_index",
            "0",
            "--samples",
            str(samples),
            "--seed",
            str(seed),
            "--anchor_sides",
        ]
    )
    command.extend(anchor_sides)
    _append_object_transform_args(command, object_transform_mode, object_transform_camera_side, object_rotate_deg, object_translate)
    if render_class_masks:
        command.append("--render_class_masks")

    model_blend_path = _profile_path(project_root, target_profile.get("model_blend_path"))
    blend_path = _profile_path(project_root, target_profile.get("blend_path"))
    stl_path = None if model_blend_path else _profile_path(project_root, target_profile.get("stl_path"))
    if blend_path:
        command.extend(["--blend", str(blend_path)])
    if model_blend_path:
        command.extend(["--model_blend", str(model_blend_path)])
    if stl_path:
        command.extend(["--stl", str(stl_path)])
    command.append("--force_generic_camera")
    if target_profile.get("force_generic_lighting"):
        command.append("--force_generic_lighting")
    material_mode = (target_profile.get("material_source") or {}).get("mode", "")
    if "embedded" in material_mode or "reference_override" in material_mode:
        command.append("--preserve_materials")
    material_profile_path = _profile_path(project_root, (target_profile.get("material_source") or {}).get("path"))
    if material_profile_path:
        command.extend(["--material_profile", str(material_profile_path)])
    defect_params_path = _write_defect_parameter_overrides(output_dir, defect_parameter_overrides)
    if defect_params_path:
        command.extend(["--defect_params_json", str(defect_params_path)])

    planned_samples = []
    for index in range(count):
        paths = _framework_sample_paths(output_dir, index)
        planned_samples.append(
            {
                "index": index,
                "seed": int(seed) + index,
                "rgb": str(paths["rgb"]),
                "mask": str(paths["mask"]),
                "label_yolo": str(paths["label_yolo"]),
                "metadata": str(paths["metadata"]),
                "defect_types": defect_types,
                "status": "planned_only" if dry_run else "pending",
            }
        )

    log = {
        "backend_script": str(backend_script),
        "output_folder": str(output_dir),
        "target_profile": target_profile,
        "defect_types": defect_types,
        "defect_generation_logic": {
            "backend": "generic_main_plane_cooccurrence",
            "shared_single_generic_function": "render_generic_main_plane_defects.create_defect",
            "position_resampling_only": True,
            "note": "Each defect object is created by the same generic create_defect() used by generic single-defect generation; cooccurrence only repeats sampling to avoid excessive overlap.",
        },
        "object_transform_mode": object_transform_mode,
        "object_transform_camera_side": object_transform_camera_side,
        "object_rotate_deg": object_rotate_deg,
        "object_translate": object_translate,
        "defect_parameter_overrides": defect_parameter_overrides or {},
        "mask_output_policy": {
            "merged_mask": True,
            "class_masks": bool(render_class_masks),
            "class_masks_default": False,
        },
        "command": command,
        "dry_run": bool(dry_run),
        "failure_reason": None,
    }
    if dry_run:
        plan = _build_generic_cooccurrence_plan(
            status="dry_run",
            backend_script=backend_script,
            command=command,
            output_dir=output_dir,
            target_profile=target_profile,
            defect_types=defect_types,
            count=count,
            samples=planned_samples,
            failed_samples=[],
            seed=seed,
            anchor_sides=anchor_sides,
            samples_requested=samples,
        )
        write_json(output_dir / "backend_run_log.json", log)
        write_json(output_dir / "generation_plan.json", plan)
        write_dataset_summary(output_dir / "dataset_summary.json", plan)
        return plan

    completed = subprocess.run(
        command,
        cwd=str(project_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    log["returncode"] = completed.returncode
    log["stdout"] = completed.stdout
    if completed.returncode != 0:
        log["failure_reason"] = "generic cooccurrence backend returned {0}".format(completed.returncode)
        write_json(output_dir / "backend_run_log.json", log)
        plan = _build_generic_cooccurrence_plan(
            status="failed",
            backend_script=backend_script,
            command=command,
            output_dir=output_dir,
            target_profile=target_profile,
            defect_types=defect_types,
            count=count,
            samples=[],
            failed_samples=[{"index": None, "seed": seed, "errors": [log["failure_reason"]]}],
            seed=seed,
            anchor_sides=anchor_sides,
            samples_requested=samples,
        )
        write_json(output_dir / "generation_plan.json", plan)
        write_dataset_summary(output_dir / "dataset_summary.json", plan)
        return plan

    metadata_path = output_dir / "metadata.json"
    _binarize_mask_outputs(output_dir)
    backend_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    successful_samples = []
    failed_samples = []
    for sample in backend_metadata.get("samples", []):
        sample_index = int(sample.get("image_id", len(successful_samples)))
        absolute_sample = {
            "index": sample_index,
            "seed": sample.get("seed"),
            "rgb": str(output_dir / sample["rgb"]),
            "mask": str(output_dir / sample["mask"]),
            "label_yolo": str(output_dir / sample["label_yolo"]),
            "metadata": str(output_dir / sample["metadata"]),
            "defect_types": sample.get("defect_types", defect_types),
            "defects": sample.get("defects", []),
            "status": "rendered",
        }
        try:
            absolute_sample["quality_checks"] = run_cooccurrence_quality_checks(absolute_sample, len(defect_types))
            successful_samples.append(absolute_sample)
        except Exception as exc:
            failed_samples.append({"index": sample_index, "seed": sample.get("seed"), "errors": [str(exc)]})
    log["files_produced"] = [
        str(path)
        for dirname in output_dirs
        for path in sorted((output_dir / dirname).glob("*"))
    ]
    write_json(output_dir / "backend_run_log.json", log)
    plan = _build_generic_cooccurrence_plan(
        status="rendered" if not failed_samples else "rendered_with_failures",
        backend_script=backend_script,
        command=command,
        output_dir=output_dir,
        target_profile=target_profile,
        defect_types=defect_types,
        count=count,
        samples=successful_samples,
        failed_samples=failed_samples,
        seed=seed,
        anchor_sides=anchor_sides,
        samples_requested=samples,
    )
    write_json(output_dir / "generation_plan.json", plan)
    write_dataset_summary(output_dir / "dataset_summary.json", plan)
    return plan


def run_generic_normal_backend(
    project_root,
    python_executable,
    target_profile,
    count,
    output_dir,
    samples=32,
    seed=100,
    anchor_sides=None,
    object_transform_mode="none",
    object_transform_camera_side="front",
    object_rotate_deg=None,
    object_translate=None,
    dry_run=False,
):
    if count < 1:
        raise ValueError("--count must be >= 1")
    anchor_sides = anchor_sides or target_profile.get("default_anchor_sides") or ["front"]
    if str(target_profile.get("target_id", "")).lower() == "p101040_blue":
        return run_reference_blackdot_normal_backend(
            project_root=project_root,
            python_executable=python_executable,
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
    backend_script = project_root / "defect_dataset_generator" / "blender_scripts" / "render_generic_main_plane_defects.py"
    blenderproc_cli = project_root / "cli.py"
    output_dir.mkdir(parents=True, exist_ok=True)
    for dirname in ["rgb", "masks", "mask", "labels_yolo", "metadata"]:
        (output_dir / dirname).mkdir(parents=True, exist_ok=True)
    command = [
        str(python_executable),
        str(blenderproc_cli),
        "run",
        str(backend_script),
        "--",
        "--target",
        target_profile["target_id"],
        "--defect_type",
        "black_dot",
        "--normal_mode",
        "--output",
        str(output_dir),
        "--num",
        str(count),
        "--start_index",
        "0",
        "--samples",
        str(samples),
        "--seed",
        str(seed),
        "--anchor_sides",
    ]
    command.extend(anchor_sides)
    _append_object_transform_args(command, object_transform_mode, object_transform_camera_side, object_rotate_deg, object_translate)
    model_blend_path = _profile_path(project_root, target_profile.get("model_blend_path"))
    blend_path = _profile_path(project_root, target_profile.get("blend_path"))
    stl_path = None if model_blend_path else _profile_path(project_root, target_profile.get("stl_path"))
    if blend_path:
        command.extend(["--blend", str(blend_path)])
    if model_blend_path:
        command.extend(["--model_blend", str(model_blend_path)])
    if stl_path:
        command.extend(["--stl", str(stl_path)])
    command.append("--force_generic_camera")
    if target_profile.get("force_generic_lighting"):
        command.append("--force_generic_lighting")
    material_mode = (target_profile.get("material_source") or {}).get("mode", "")
    if "embedded" in material_mode or "reference_override" in material_mode:
        command.append("--preserve_materials")
    material_profile_path = _profile_path(project_root, (target_profile.get("material_source") or {}).get("path"))
    if material_profile_path:
        command.extend(["--material_profile", str(material_profile_path)])

    log = {
        "backend_script": str(backend_script),
        "output_folder": str(output_dir),
        "target_profile": target_profile,
        "generation_mode": "normal",
        "command": command,
        "dry_run": bool(dry_run),
        "failure_reason": None,
    }
    if dry_run:
        plan = _build_generic_normal_plan(
            status="dry_run",
            backend_script=backend_script,
            command=command,
            output_dir=output_dir,
            target_profile=target_profile,
            count=count,
            samples=[],
            failed_samples=[],
            seed=seed,
            anchor_sides=anchor_sides,
            samples_requested=samples,
        )
        write_json(output_dir / "backend_run_log.json", log)
        write_json(output_dir / "generation_plan.json", plan)
        write_dataset_summary(output_dir / "dataset_summary.json", plan)
        return plan

    completed = subprocess.run(
        command,
        cwd=str(project_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    log["returncode"] = completed.returncode
    log["stdout"] = completed.stdout
    if completed.returncode != 0:
        log["failure_reason"] = "generic normal backend returned {0}".format(completed.returncode)
        write_json(output_dir / "backend_run_log.json", log)
        plan = _build_generic_normal_plan(
            status="failed",
            backend_script=backend_script,
            command=command,
            output_dir=output_dir,
            target_profile=target_profile,
            count=count,
            samples=[],
            failed_samples=[{"index": None, "seed": seed, "errors": [log["failure_reason"]]}],
            seed=seed,
            anchor_sides=anchor_sides,
            samples_requested=samples,
        )
        write_json(output_dir / "generation_plan.json", plan)
        write_dataset_summary(output_dir / "dataset_summary.json", plan)
        return plan

    backend_metadata = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
    successful_samples = []
    failed_samples = []
    for sample in backend_metadata.get("samples", []):
        sample_index = int(sample.get("image_id", len(successful_samples)))
        absolute_sample = {
            "index": sample_index,
            "seed": sample.get("seed"),
            "rgb": str(output_dir / sample["rgb"]),
            "mask": str(output_dir / sample["mask"]),
            "label_yolo": str(output_dir / sample["label_yolo"]),
            "metadata": str(output_dir / sample["metadata"]),
            "defect_types": [],
            "defects": [],
            "is_normal": True,
            "status": "rendered",
        }
        try:
            absolute_sample["quality_checks"] = run_normal_quality_checks(absolute_sample)
            successful_samples.append(absolute_sample)
        except Exception as exc:
            failed_samples.append({"index": sample_index, "seed": sample.get("seed"), "errors": [str(exc)]})
    log["files_produced"] = [
        str(path)
        for dirname in ["rgb", "masks", "labels_yolo", "metadata"]
        for path in sorted((output_dir / dirname).glob("*"))
    ]
    write_json(output_dir / "backend_run_log.json", log)
    plan = _build_generic_normal_plan(
        status="rendered" if not failed_samples else "rendered_with_failures",
        backend_script=backend_script,
        command=command,
        output_dir=output_dir,
        target_profile=target_profile,
        count=count,
        samples=successful_samples,
        failed_samples=failed_samples,
        seed=seed,
        anchor_sides=anchor_sides,
        samples_requested=samples,
    )
    write_json(output_dir / "generation_plan.json", plan)
    write_dataset_summary(output_dir / "dataset_summary.json", plan)
    return plan


def run_reference_blackdot_normal_backend(
    project_root,
    python_executable,
    target_profile,
    count,
    output_dir,
    samples=32,
    seed=100,
    anchor_sides=None,
    object_transform_mode="none",
    object_transform_camera_side="front",
    object_rotate_deg=None,
    object_translate=None,
    dry_run=False,
):
    anchor_sides = anchor_sides or ["front"]
    anchor_side = anchor_sides[0]
    if anchor_side == "back" and object_transform_mode == "none":
        object_transform_mode = "keep_camera"
        object_transform_camera_side = "front"
    backend_script = project_root / "examples" / "my_project" / "reference_blend_blackdot_multi_model.py"
    blenderproc_cli = project_root / "cli.py"
    raw_output_dir = output_dir / "_backend" / "reference_blackdot_normal"
    raw_output_dir.mkdir(parents=True, exist_ok=True)
    _ensure_framework_output_dirs(output_dir)
    blend_path = _profile_path(project_root, target_profile.get("blend_path"))
    command = _build_reference_blackdot_command(
        python_executable=python_executable,
        blenderproc_cli=blenderproc_cli,
        backend_script=backend_script,
        backend_model="P101040_blue",
        raw_output_dir=raw_output_dir,
        count=count,
        samples=samples,
        seed=seed,
        anchor_side=anchor_side,
        blend_path=blend_path,
        defect_config={},
        object_transform_mode=object_transform_mode,
        object_transform_camera_side=object_transform_camera_side,
        object_rotate_deg=object_rotate_deg,
        object_translate=object_translate,
        normal_mode=True,
    )
    log = {
        "backend_script": str(backend_script),
        "output_folder": str(raw_output_dir),
        "framework_output_folder": str(output_dir),
        "generation_mode": "normal",
        "command": command,
        "dry_run": bool(dry_run),
        "failure_reason": None,
    }
    if dry_run:
        plan = _build_generic_normal_plan(
            status="dry_run",
            backend_script=backend_script,
            command=command,
            output_dir=output_dir,
            target_profile=target_profile,
            count=count,
            samples=[],
            failed_samples=[],
            seed=seed,
            anchor_sides=anchor_sides,
            samples_requested=samples,
        )
        plan["backend"] = "reference_blackdot_normal"
        plan["raw_backend_output_dir"] = str(raw_output_dir)
        write_json(output_dir / "backend_run_log.json", log)
        write_json(output_dir / "generation_plan.json", plan)
        write_dataset_summary(output_dir / "dataset_summary.json", plan)
        return plan

    completed = subprocess.run(command, cwd=str(project_root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    log["returncode"] = completed.returncode
    log["stdout"] = completed.stdout
    if completed.returncode != 0:
        log["failure_reason"] = "reference black-dot normal backend returned {0}".format(completed.returncode)
        write_json(output_dir / "backend_run_log.json", log)
        plan = _build_generic_normal_plan(
            status="failed",
            backend_script=backend_script,
            command=command,
            output_dir=output_dir,
            target_profile=target_profile,
            count=count,
            samples=[],
            failed_samples=[{"index": None, "seed": seed, "errors": [log["failure_reason"]]}],
            seed=seed,
            anchor_sides=anchor_sides,
            samples_requested=samples,
        )
        plan["backend"] = "reference_blackdot_normal"
        plan["raw_backend_output_dir"] = str(raw_output_dir)
        write_json(output_dir / "generation_plan.json", plan)
        write_dataset_summary(output_dir / "dataset_summary.json", plan)
        return plan

    adapter_result = adapt_reference_blackdot_outputs(
        raw_output_dir=raw_output_dir,
        framework_output_dir=output_dir,
        start_index=0,
        backend_model="P101040_blue",
        anchor_side=anchor_side,
        seed=seed,
    )
    successful_samples = []
    failed_samples = []
    for sample in adapter_result["samples"]:
        sample["is_normal"] = True
        sample["defect_types"] = []
        sample["defects"] = []
        sample["defect_type"] = None
        try:
            sample["quality_checks"] = run_normal_quality_checks(sample)
            successful_samples.append(sample)
        except Exception as exc:
            failed_samples.append({"index": sample.get("index"), "seed": sample.get("seed"), "errors": [str(exc)]})
    log["files_produced"] = adapter_result["files_produced"]
    log["failure_reason"] = None if not failed_samples else "One or more normal samples failed quality checks."
    write_json(output_dir / "backend_run_log.json", log)
    plan = _build_generic_normal_plan(
        status="rendered" if not failed_samples else "rendered_with_failures",
        backend_script=backend_script,
        command=command,
        output_dir=output_dir,
        target_profile=target_profile,
        count=count,
        samples=successful_samples,
        failed_samples=failed_samples,
        seed=seed,
        anchor_sides=anchor_sides,
        samples_requested=samples,
    )
    plan["backend"] = "reference_blackdot_normal"
    plan["raw_backend_output_dir"] = str(raw_output_dir)
    write_json(output_dir / "generation_plan.json", plan)
    write_dataset_summary(output_dir / "dataset_summary.json", plan)
    return plan


def run_persistent_generic_batch_backend(
    project_root,
    python_executable,
    target_profile,
    batch_plan,
    output_dir,
    samples=32,
    seed=100,
    render_class_masks=False,
    dry_run=False,
):
    sample_specs = list(batch_plan.get("samples", []))
    if not sample_specs:
        raise ValueError("Persistent batch plan must contain a non-empty samples list.")
    backend_script = project_root / "defect_dataset_generator" / "blender_scripts" / "render_persistent_generic_batch.py"
    blenderproc_cli = project_root / "cli.py"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dirs = ["rgb", "masks", "mask", "labels_yolo", "metadata"]
    if render_class_masks:
        output_dirs.append("masks_by_class")
    for dirname in output_dirs:
        (output_dir / dirname).mkdir(parents=True, exist_ok=True)

    plan_path = output_dir / "persistent_batch_plan.json"
    write_json(plan_path, batch_plan)

    command = [
        str(python_executable),
        str(blenderproc_cli),
        "run",
        str(backend_script),
        "--",
        "--target",
        target_profile["target_id"],
        "--plan",
        str(plan_path),
        "--output",
        str(output_dir),
        "--samples",
        str(samples),
        "--seed",
        str(seed),
    ]
    model_blend_path = _profile_path(project_root, target_profile.get("model_blend_path"))
    blend_path = _profile_path(project_root, target_profile.get("blend_path"))
    stl_path = None if model_blend_path else _profile_path(project_root, target_profile.get("stl_path"))
    if blend_path:
        command.extend(["--blend", str(blend_path)])
    if model_blend_path:
        command.extend(["--model_blend", str(model_blend_path)])
    if stl_path:
        command.extend(["--stl", str(stl_path)])
    command.append("--force_generic_camera")
    if target_profile.get("force_generic_lighting"):
        command.append("--force_generic_lighting")
    material_mode = (target_profile.get("material_source") or {}).get("mode", "")
    if "embedded" in material_mode or "reference_override" in material_mode:
        command.append("--preserve_materials")
    material_profile_path = _profile_path(project_root, (target_profile.get("material_source") or {}).get("path"))
    if material_profile_path:
        command.extend(["--material_profile", str(material_profile_path)])
    if render_class_masks:
        command.append("--render_class_masks")

    planned_samples = _persistent_planned_samples(output_dir, sample_specs, seed)
    log = {
        "backend_script": str(backend_script),
        "output_folder": str(output_dir),
        "target_profile": target_profile,
        "sample_count": len(sample_specs),
        "command": command,
        "dry_run": bool(dry_run),
        "failure_reason": None,
        "defect_generation_logic": {
            "backend": "persistent_generic_batch",
            "shared_single_generic_function": "render_generic_main_plane_defects.create_defect",
            "reference_backends_supported": False,
        },
        "mask_output_policy": {
            "merged_mask": True,
            "class_masks": bool(render_class_masks),
            "class_masks_default": False,
        },
    }
    if dry_run:
        plan = _build_persistent_generic_batch_plan(
            status="dry_run",
            backend_script=backend_script,
            command=command,
            output_dir=output_dir,
            target_profile=target_profile,
            samples=planned_samples,
            failed_samples=[],
            seed=seed,
            render_samples=samples,
        )
        write_json(output_dir / "backend_run_log.json", log)
        write_json(output_dir / "generation_plan.json", plan)
        write_dataset_summary(output_dir / "dataset_summary.json", plan)
        return plan

    completed = subprocess.run(
        command,
        cwd=str(project_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    log["returncode"] = completed.returncode
    log["stdout"] = completed.stdout
    if completed.returncode != 0:
        log["failure_reason"] = "persistent generic backend returned {0}".format(completed.returncode)
        write_json(output_dir / "backend_run_log.json", log)
        plan = _build_persistent_generic_batch_plan(
            status="failed",
            backend_script=backend_script,
            command=command,
            output_dir=output_dir,
            target_profile=target_profile,
            samples=[],
            failed_samples=[{"index": None, "seed": seed, "errors": [log["failure_reason"]]}],
            seed=seed,
            render_samples=samples,
        )
        write_json(output_dir / "generation_plan.json", plan)
        write_dataset_summary(output_dir / "dataset_summary.json", plan)
        return plan

    metadata_path = output_dir / "metadata.json"
    backend_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    successful_samples = []
    failed_samples = []
    for sample in backend_metadata.get("samples", []):
        sample_index = int(sample.get("image_id", len(successful_samples)))
        absolute_sample = {
            "index": sample_index,
            "seed": sample.get("seed"),
            "rgb": str(output_dir / sample["rgb"]),
            "mask": str(output_dir / sample["mask"]),
            "label_yolo": str(output_dir / sample["label_yolo"]),
            "metadata": str(output_dir / sample["metadata"]),
            "defect_types": sample.get("defect_types", []),
            "defects": sample.get("defects", []),
            "is_normal": bool(sample.get("is_normal", False)),
            "status": "rendered",
        }
        try:
            if absolute_sample["is_normal"]:
                absolute_sample["quality_checks"] = run_normal_quality_checks(absolute_sample)
            elif len(absolute_sample["defect_types"]) > 1:
                absolute_sample["quality_checks"] = run_cooccurrence_quality_checks(
                    absolute_sample,
                    len(absolute_sample["defect_types"]),
                )
            else:
                absolute_sample["bbox"] = sample.get("bbox") or (absolute_sample["defects"][0].get("bbox") if absolute_sample["defects"] else None)
                absolute_sample["quality_checks"] = run_sample_quality_checks(absolute_sample)
            successful_samples.append(absolute_sample)
        except Exception as exc:
            failed_samples.append({"index": sample_index, "seed": sample.get("seed"), "errors": [str(exc)]})
    log["files_produced"] = [
        str(path)
        for dirname in output_dirs
        for path in sorted((output_dir / dirname).glob("*"))
    ]
    write_json(output_dir / "backend_run_log.json", log)
    plan = _build_persistent_generic_batch_plan(
        status="rendered" if not failed_samples else "rendered_with_failures",
        backend_script=backend_script,
        command=command,
        output_dir=output_dir,
        target_profile=target_profile,
        samples=successful_samples,
        failed_samples=failed_samples,
        seed=seed,
        render_samples=samples,
    )
    write_json(output_dir / "generation_plan.json", plan)
    write_dataset_summary(output_dir / "dataset_summary.json", plan)
    return plan


def run_qc71336_black_reference_backend(
    project_root,
    python_executable,
    target_profile,
    defect_type,
    count,
    output_dir,
    samples=32,
    seed=100,
    anchor_sides=None,
    object_transform_mode="none",
    object_transform_camera_side="front",
    object_rotate_deg=None,
    object_translate=None,
    defect_parameter_overrides=None,
    defect_count_max=1,
    dry_run=False,
):
    if int(defect_count_max or 1) < 1:
        raise ValueError("--defect-count-max must be >= 1")
    anchor_sides = anchor_sides or target_profile.get("default_anchor_sides") or ["front"]
    backend_script = project_root / "examples" / "my_project" / "reference_blend_qc71336_black_prebuilt_normal_debug.py"
    blenderproc_cli = project_root / "cli.py"
    raw_output_dir = output_dir / "_backend" / "qc71336_black_reference"
    raw_output_dir.mkdir(parents=True, exist_ok=True)
    _ensure_framework_output_dirs(output_dir)
    command = [
        str(python_executable),
        str(blenderproc_cli),
        "run",
        str(backend_script),
        "--",
        "--blend",
        str(_profile_path(project_root, target_profile.get("blend_path"))),
        "--model_blend",
        str(_profile_path(project_root, target_profile.get("model_blend_path"))),
        "--output",
        str(raw_output_dir),
        "--num",
        str(count),
        "--start_index",
        "0",
        "--samples",
        str(samples),
        "--defect_type",
        defect_type,
        "--defect_seed",
        str(seed),
        "--anchor_sides",
    ]
    command.extend(anchor_sides)
    if int(defect_count_max or 1) > 1:
        command.extend(["--defect_count_max", str(int(defect_count_max))])
    _append_object_transform_args(command, object_transform_mode, object_transform_camera_side, object_rotate_deg, object_translate)
    return _run_reference_style_backend(
        backend_name="qc71336_black_prebuilt_normal",
        backend_script=backend_script,
        command=command,
        project_root=project_root,
        raw_output_dir=raw_output_dir,
        output_dir=output_dir,
        target_profile=target_profile,
        defect_type=defect_type,
        count=count,
        seed=seed,
        samples=samples,
        anchor_sides=anchor_sides,
        dry_run=dry_run,
    )


def run_qc71336_white_foreign_reference_backend(
    project_root,
    python_executable,
    target_profile,
    count,
    output_dir,
    samples=32,
    seed=100,
    anchor_sides=None,
    object_transform_mode="none",
    object_transform_camera_side="front",
    object_rotate_deg=None,
    object_translate=None,
    defect_parameter_overrides=None,
    defect_count_max=1,
    dry_run=False,
):
    if int(defect_count_max or 1) < 1:
        raise ValueError("--defect-count-max must be >= 1")
    anchor_sides = anchor_sides or target_profile.get("default_anchor_sides") or ["front"]
    backend_script = project_root / "examples" / "my_project" / "reference_blend_qc71336_white_prebuilt_normal_debug.py"
    blenderproc_cli = project_root / "cli.py"
    raw_output_dir = output_dir / "_backend" / "qc71336_white_foreign_reference"
    raw_output_dir.mkdir(parents=True, exist_ok=True)
    _ensure_framework_output_dirs(output_dir)
    command = [
        str(python_executable),
        str(blenderproc_cli),
        "run",
        str(backend_script),
        "--",
        "--blend",
        str(_profile_path(project_root, target_profile.get("blend_path"))),
        "--model_blend",
        str(_profile_path(project_root, target_profile.get("model_blend_path"))),
        "--output",
        str(raw_output_dir),
        "--num",
        str(count),
        "--start_index",
        "0",
        "--samples",
        str(samples),
        "--enable_foreign_material",
        "--foreign_material_seed",
        str(seed),
        "--anchor_sides",
    ]
    command.extend(anchor_sides)
    if int(defect_count_max or 1) > 1:
        command.extend(["--defect_count_max", str(int(defect_count_max))])
    if defect_parameter_overrides:
        if "foreign_material_radius_scale" in defect_parameter_overrides:
            command.extend(["--foreign_material_radius_scale", str(defect_parameter_overrides["foreign_material_radius_scale"])])
        if "foreign_material_depth_scale" in defect_parameter_overrides:
            command.extend(["--foreign_material_depth_scale", str(defect_parameter_overrides["foreign_material_depth_scale"])])
    _append_object_transform_args(command, object_transform_mode, object_transform_camera_side, object_rotate_deg, object_translate)
    return _run_reference_style_backend(
        backend_name="qc71336_white_foreign_reference",
        backend_script=backend_script,
        command=command,
        project_root=project_root,
        raw_output_dir=raw_output_dir,
        output_dir=output_dir,
        target_profile=target_profile,
        defect_type="foreign_material",
        count=count,
        seed=seed,
        samples=samples,
        anchor_sides=anchor_sides,
        dry_run=dry_run,
    )


def run_qc75244_mixed_color_reference_backend(
    project_root,
    python_executable,
    target_profile,
    count,
    output_dir,
    samples=32,
    seed=100,
    anchor_sides=None,
    object_transform_mode="none",
    object_transform_camera_side="front",
    object_rotate_deg=None,
    object_translate=None,
    defect_count_max=1,
    dry_run=False,
):
    if int(defect_count_max or 1) < 1:
        raise ValueError("--defect-count-max must be >= 1")
    anchor_sides = anchor_sides or target_profile.get("default_anchor_sides") or ["front"]
    backend_script = project_root / "examples" / "my_project" / "reference_blend_qc75244_mixed_color_profile_debug.py"
    blenderproc_cli = project_root / "cli.py"
    raw_output_dir = output_dir / "_backend" / "qc75244_mixed_color_reference"
    raw_output_dir.mkdir(parents=True, exist_ok=True)
    _ensure_framework_output_dirs(output_dir)
    command = [
        str(python_executable),
        str(blenderproc_cli),
        "run",
        str(backend_script),
        "--",
        "--blend",
        str(_profile_path(project_root, target_profile.get("blend_path"))),
        "--stl",
        str(_profile_path(project_root, target_profile.get("stl_path"))),
        "--output",
        str(raw_output_dir),
        "--num",
        str(count),
        "--start_index",
        "0",
        "--samples",
        str(samples),
        "--enable_mixed_color",
        "--mixed_color_seed",
        str(seed),
        "--anchor_sides",
    ]
    command.extend(anchor_sides)
    if int(defect_count_max or 1) > 1:
        command.extend(["--defect_count_max", str(int(defect_count_max))])
    _append_object_transform_args(command, object_transform_mode, object_transform_camera_side, object_rotate_deg, object_translate)
    return _run_reference_style_backend(
        backend_name="qc75244_mixed_color_profile",
        backend_script=backend_script,
        command=command,
        project_root=project_root,
        raw_output_dir=raw_output_dir,
        output_dir=output_dir,
        target_profile=target_profile,
        defect_type="mixed_color_contamination",
        count=count,
        seed=seed,
        samples=samples,
        anchor_sides=anchor_sides,
        dry_run=dry_run,
    )


def _write_defect_parameter_overrides(output_dir, defect_parameter_overrides):
    if not defect_parameter_overrides:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "validated_defect_parameter_overrides.json"
    write_json(
        path,
        {
            "schema_version": "validated_defect_parameter_overrides_v1",
            "defects": defect_parameter_overrides,
        },
    )
    return path


def _run_reference_style_backend(
    backend_name,
    backend_script,
    command,
    project_root,
    raw_output_dir,
    output_dir,
    target_profile,
    defect_type,
    count,
    seed,
    samples,
    anchor_sides,
    dry_run=False,
):
    log = {
        "backend_name": backend_name,
        "backend_script": str(backend_script),
        "output_folder": str(raw_output_dir),
        "framework_output_folder": str(output_dir),
        "target_profile": target_profile,
        "defect_type": defect_type,
        "command": command,
        "dry_run": bool(dry_run),
        "failure_reason": None,
    }
    if dry_run:
        plan = _build_generic_backend_plan(
            status="dry_run",
            backend_script=backend_script,
            command=command,
            output_dir=output_dir,
            raw_output_dir=raw_output_dir,
            target_profile=target_profile,
            defect_type=defect_type,
            count=count,
            samples=[],
            failed_samples=[],
            seed=seed,
            anchor_sides=anchor_sides,
            samples_requested=samples,
            backend_name=backend_name,
        )
        write_json(output_dir / "backend_run_log.json", log)
        write_json(output_dir / "generation_plan.json", plan)
        write_dataset_summary(output_dir / "dataset_summary.json", plan)
        return plan
    completed = subprocess.run(
        command,
        cwd=str(project_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    log["returncode"] = completed.returncode
    log["stdout"] = completed.stdout
    if completed.returncode != 0:
        log["failure_reason"] = "{0} backend returned {1}".format(backend_name, completed.returncode)
        write_json(output_dir / "backend_run_log.json", log)
        plan = _build_generic_backend_plan(
            status="failed",
            backend_script=backend_script,
            command=command,
            output_dir=output_dir,
            raw_output_dir=raw_output_dir,
            target_profile=target_profile,
            defect_type=defect_type,
            count=count,
            samples=[],
            failed_samples=[{"index": None, "seed": seed, "errors": [log["failure_reason"]]}],
            seed=seed,
            anchor_sides=anchor_sides,
            samples_requested=samples,
            backend_name=backend_name,
        )
        write_json(output_dir / "generation_plan.json", plan)
        write_dataset_summary(output_dir / "dataset_summary.json", plan)
        return plan
    try:
        _binarize_mask_outputs(raw_output_dir, threshold=10)
        adapter_result = adapt_reference_blackdot_outputs(
            raw_output_dir=raw_output_dir,
            framework_output_dir=output_dir,
            start_index=0,
            backend_model=target_profile["target_id"],
            anchor_side=",".join(anchor_sides),
            seed=seed,
            material_path=None,
            apply_material=False,
            defect_type_override=defect_type,
        )
        successful_samples = []
        failed_samples = []
        sample_by_index = {int(sample["index"]): sample for sample in adapter_result["samples"]}
        for sample_index in range(count):
            sample = sample_by_index.get(sample_index)
            if sample is None:
                failed_samples.append(
                    {
                        "index": sample_index,
                        "seed": int(seed) + sample_index,
                        "attempts": 1,
                        "errors": ["backend did not produce this sample"],
                    }
                )
                continue
            try:
                expected_defect_count = len(sample.get("defects") or [])
                if expected_defect_count > 1:
                    quality = run_cooccurrence_quality_checks(sample, expected_defect_count)
                elif defect_type == "foreign_material_splay":
                    quality = run_cooccurrence_quality_checks(sample, 2)
                else:
                    quality = run_sample_quality_checks(sample)
                sample["quality_checks"] = quality
                successful_samples.append(sample)
            except Exception as sample_exc:
                failed_samples.append(
                    {
                        "index": sample_index,
                        "seed": sample.get("seed", int(seed) + sample_index),
                        "attempts": 1,
                        "errors": [str(sample_exc)],
                    }
                )
        log["files_produced"] = adapter_result["files_produced"]
        status = "rendered" if not failed_samples else ("partial" if successful_samples else "failed")
        log["failure_reason"] = None if not failed_samples else "One or more samples failed after backend quality checks."
        plan = _build_generic_backend_plan(
            status=status,
            backend_script=backend_script,
            command=command,
            output_dir=output_dir,
            raw_output_dir=raw_output_dir,
            target_profile=target_profile,
            defect_type=defect_type,
            count=count,
            samples=successful_samples,
            failed_samples=failed_samples,
            seed=seed,
            anchor_sides=anchor_sides,
            samples_requested=samples,
            backend_name=backend_name,
        )
    except Exception as exc:
        log["failure_reason"] = str(exc)
        plan = _build_generic_backend_plan(
            status="failed",
            backend_script=backend_script,
            command=command,
            output_dir=output_dir,
            raw_output_dir=raw_output_dir,
            target_profile=target_profile,
            defect_type=defect_type,
            count=count,
            samples=[],
            failed_samples=[{"index": None, "seed": seed, "errors": [str(exc)]}],
            seed=seed,
            anchor_sides=anchor_sides,
            samples_requested=samples,
            backend_name=backend_name,
        )
    write_json(output_dir / "backend_run_log.json", log)
    write_json(output_dir / "generation_plan.json", plan)
    write_dataset_summary(output_dir / "dataset_summary.json", plan)
    return plan


def adapt_reference_blackdot_outputs(
    raw_output_dir,
    framework_output_dir,
    start_index=0,
    backend_model=None,
    anchor_side=None,
    seed=None,
    material_path=None,
    apply_material=False,
    defect_type_override=None,
):
    raw_metadata_path = raw_output_dir / "metadata.json"
    if not raw_metadata_path.exists():
        raise FileNotFoundError("Backend metadata.json was not produced: {0}".format(raw_metadata_path))

    with raw_metadata_path.open("r", encoding="utf-8") as f:
        raw_metadata = json.load(f)

    samples = raw_metadata.get("samples", [])
    if not samples:
        raise RuntimeError("Backend produced metadata.json but no accepted samples.")

    files_produced = []
    adapted_samples = []
    for local_index, sample in enumerate(samples):
        new_index = start_index + local_index
        sample_seed = sample.get("random_seed", sample.get("seed", int(seed) + local_index if seed is not None else None))
        sample_anchor_side = _sample_anchor_side(sample) or anchor_side
        image_id = "{0:06d}".format(new_index)
        paths = _framework_sample_paths(framework_output_dir, new_index)
        rgb_dst = paths["rgb"]
        mask_dst = paths["mask"]
        label_dst = paths["label_yolo"]
        metadata_dst = paths["metadata"]

        sample_paths = _sample_output_paths(sample)
        _copy_if_exists(raw_output_dir / sample_paths["rgb"], rgb_dst, files_produced)
        _copy_if_exists(raw_output_dir / sample_paths["mask"], mask_dst, files_produced)
        _copy_if_exists(raw_output_dir / sample_paths["label_yolo"], label_dst, files_produced)
        fallback_bbox = _fallback_bbox_for_reference_sample(sample, label_dst, rgb_dst, defect_type_override or raw_metadata.get("defect_type"))
        _ensure_mask_from_labels_if_empty(mask_dst, label_dst, rgb_dst)

        sample_defects = _sample_defects(sample)
        sample_bbox = fallback_bbox or _sample_bbox(sample)
        if sample_bbox is None and len(sample_defects) == 1:
            sample_bbox = sample_defects[0].get("bbox")
        per_image_metadata = {
            "schema_version": "0.1",
            "source_backend": "reference_blend_blackdot_multi_model.py",
            "is_normal": bool(sample.get("is_normal", raw_metadata.get("is_normal", False))),
            "seed": sample_seed,
            "backend_model": backend_model or raw_metadata.get("model_name"),
            "anchor_side": sample_anchor_side,
            "requested_anchor_side": anchor_side,
            "defect_type": defect_type_override or raw_metadata.get("defect_type", sample.get("defect_type")),
            "output_paths": {
                "rgb": str(rgb_dst),
                "mask": str(mask_dst),
                "label_yolo": str(label_dst),
                "metadata": str(metadata_dst),
            },
            "raw_backend_output_dir": str(raw_output_dir),
            "raw_sample": sample,
            "defects": sample_defects,
            "material_override": {
                "applied": bool(apply_material and material_path),
                "material_path": str(material_path) if material_path else None,
                "backend_material_info": raw_metadata.get("material_info"),
            },
            "raw_metadata_summary": {
                "model_name": raw_metadata.get("model_name"),
                "appearance_profile": raw_metadata.get("appearance_profile"),
                "material_family": raw_metadata.get("material_family"),
                "defect_type": defect_type_override or raw_metadata.get("defect_type"),
                "render_width": raw_metadata.get("render_width"),
                "render_height": raw_metadata.get("render_height"),
                "cycles_samples": raw_metadata.get("cycles_samples"),
                "gpu_info": raw_metadata.get("gpu_info"),
                "render_device_info": raw_metadata.get("render_device_info"),
                "material_info": raw_metadata.get("material_info"),
                "seed": seed,
                "sample_seed": sample_seed,
                "anchor_side": sample_anchor_side,
                "requested_anchor_side": anchor_side,
            },
            "label_fallback": fallback_bbox,
        }
        write_json(metadata_dst, per_image_metadata)
        files_produced.append(str(metadata_dst))

        adapted_samples.append(
            {
                "index": new_index,
                "rgb": str(rgb_dst),
                "mask": str(mask_dst),
                "label_yolo": str(label_dst),
                "metadata": str(metadata_dst),
                "status": "rendered",
                "seed": sample_seed,
                "backend_model": backend_model or raw_metadata.get("model_name"),
                "is_normal": bool(sample.get("is_normal", raw_metadata.get("is_normal", False))),
                "anchor_side": sample_anchor_side,
                "requested_anchor_side": anchor_side,
                "defect_type": sample.get(
                    "defect_type_canonical",
                    sample.get("defect_type", defect_type_override or raw_metadata.get("defect_type")),
                ),
                "defect_types": sample.get("defect_types", []),
                "defects": sample_defects,
                "backend_image_id": sample.get("image_id", sample.get("sample_id")),
                "bbox": sample_bbox,
            }
        )

    backend_metadata_dst = framework_output_dir / "backend_metadata.json"
    if len(samples) == 1 and start_index == 0:
        shutil.copy2(str(raw_metadata_path), str(backend_metadata_dst))
        files_produced.append(str(backend_metadata_dst))
    else:
        per_sample_backend_metadata = framework_output_dir / "metadata" / ("{0:06d}_backend_metadata.json".format(start_index))
        shutil.copy2(str(raw_metadata_path), str(per_sample_backend_metadata))
        files_produced.append(str(per_sample_backend_metadata))
    return {"samples": adapted_samples, "files_produced": files_produced}


def _sample_output_paths(sample):
    label_info = sample.get("lightweight_label") or {}
    paths = {
        "rgb": sample.get("rgb") or sample.get("rgb_path"),
        "mask": sample.get("mask") or label_info.get("mask"),
        "label_yolo": sample.get("label_yolo") or label_info.get("label_yolo"),
    }
    missing = [name for name, value in paths.items() if not value]
    if missing:
        raise KeyError("Backend sample missing output path(s): {0}".format(", ".join(missing)))
    return paths


def _sample_bbox(sample):
    label_info = sample.get("lightweight_label") or {}
    return sample.get("bbox") or label_info.get("bbox")


def _sample_defects(sample):
    label_info = sample.get("lightweight_label") or {}
    bboxes = label_info.get("defect_bboxes") or []
    defects = []
    for item in bboxes:
        if not isinstance(item, dict):
            continue
        defect_type = item.get("defect_type") or sample.get("defect_type_canonical") or sample.get("defect_type")
        defects.append(
            {
                "defect_type": defect_type,
                "class_id": item.get("class_id", _defect_class_id(defect_type)),
                "bbox": item.get("bbox"),
                "instance_index": item.get("instance_index"),
            }
        )
    if defects:
        return defects
    direct = sample.get("defects")
    if isinstance(direct, list) and direct:
        return direct
    defect_info = _reference_defect_info(sample)
    nested = defect_info.get("defects") if isinstance(defect_info, dict) else None
    if isinstance(nested, list) and nested:
        return nested
    return []


def _fallback_bbox_for_reference_sample(sample, label_path, rgb_path, defect_type):
    label_text = label_path.read_text(encoding="utf-8").strip() if label_path.exists() else ""
    if label_text:
        return None
    bbox = _sample_bbox(sample)
    if bbox is None:
        bbox = _defect_projection_fallback_bbox(sample, rgb_path)
    if bbox is None:
        return None
    image_size = _png_size(rgb_path)
    if image_size is None:
        return None
    width, height = image_size
    label_class = _defect_class_id(defect_type or sample.get("defect_type_canonical") or sample.get("defect_type"))
    x, y, w, h = bbox["xywh"]
    xc = (float(x) + float(w) * 0.5) / float(width)
    yc = (float(y) + float(h) * 0.5) / float(height)
    bw = float(w) / float(width)
    bh = float(h) / float(height)
    label_path.write_text(
        "{0} {1:.8f} {2:.8f} {3:.8f} {4:.8f}\n".format(label_class, xc, yc, bw, bh),
        encoding="utf-8",
    )
    return bbox


def _ensure_mask_from_labels_if_empty(mask_path, label_path, rgb_path):
    stats = _png_mask_foreground_stats(mask_path)
    if stats is not None and stats.get("foreground_pixels", 0) > 0:
        return False
    label_text = label_path.read_text(encoding="utf-8").strip() if label_path.exists() else ""
    if not label_text:
        return False
    image_size = _png_size(rgb_path)
    if image_size is None:
        return False
    try:
        from PIL import Image, ImageDraw

        width, height = image_size
        mask = Image.new("L", (int(width), int(height)), 0)
        draw = ImageDraw.Draw(mask)
        for line in label_text.splitlines():
            parts = line.strip().split()
            if len(parts) < 5:
                continue
            _, xc, yc, bw, bh = parts[:5]
            xc = float(xc) * width
            yc = float(yc) * height
            bw = max(1.0, float(bw) * width)
            bh = max(1.0, float(bh) * height)
            x0 = max(0, int(round(xc - bw * 0.5)))
            y0 = max(0, int(round(yc - bh * 0.5)))
            x1 = min(int(width) - 1, int(round(xc + bw * 0.5)))
            y1 = min(int(height) - 1, int(round(yc + bh * 0.5)))
            draw.rectangle([x0, y0, x1, y1], fill=255)
        mask.save(mask_path)
        return True
    except Exception:
        return False


def _defect_projection_fallback_bbox(sample, rgb_path):
    image_size = _png_size(rgb_path)
    if image_size is None:
        return None
    width, height = image_size
    defect_info = _reference_defect_info(sample)
    projected = None
    camera_follow = defect_info.get("camera_follow") if isinstance(defect_info, dict) else None
    if isinstance(camera_follow, dict):
        projected = camera_follow.get("projected_xy_after_follow")
    if not projected and isinstance(defect_info, dict):
        projected = defect_info.get("projected_xy")
    if not projected or len(projected) < 2:
        return None
    px = min(max(float(projected[0]), 0.0), 1.0)
    py = min(max(float(projected[1]), 0.0), 1.0)
    radius = float(defect_info.get("radius", 0.0) or defect_info.get("radius_floor", 0.0) or 0.0) if isinstance(defect_info, dict) else 0.0
    box_w = max(8, min(48, int(round(width * max(0.004, radius * 0.55)))))
    box_h = max(6, min(40, int(round(height * max(0.004, radius * 0.45)))))
    x = min(max(0, int(round(px * width - box_w * 0.5))), max(0, width - box_w))
    y = min(max(0, int(round(py * height - box_h * 0.5))), max(0, height - box_h))
    return {
        "xywh": [x, y, box_w, box_h],
        "xyxy": [x, y, x + box_w, y + box_h],
        "area_pixels": int(box_w * box_h),
        "source": "projected_defect_fallback",
    }


def _reference_defect_info(sample):
    for key in ("defect", "black_dot", "foreign_material", "mixed_color_contamination", "splay"):
        value = sample.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _defect_class_id(defect_type):
    class_ids = {
        "black_dot": 0,
        "black_spot": 0,
        "foreign_material": 1,
        "splay": 2,
        "mixed_color_contamination": 3,
        "sink_mark": 4,
    }
    return class_ids.get(str(defect_type or "").lower(), 0)


def run_sample_quality_checks(sample):
    rgb_path = Path(sample["rgb"])
    mask_path = Path(sample["mask"])
    label_path = Path(sample["label_yolo"])
    metadata_path = Path(sample["metadata"])
    checks = {
        "rgb_exists": rgb_path.exists(),
        "mask_exists": mask_path.exists(),
        "label_exists": label_path.exists(),
        "metadata_exists": metadata_path.exists(),
        "rgb_readable": False,
        "mask_readable": False,
        "mask_not_empty": False,
        "rgb_not_blank": False,
        "image_size_matches_mask": False,
        "label_bbox_in_0_1": False,
        "label_matches_backend_bbox": False,
        "label_not_empty": False,
        "rgb_not_overexposed": False,
        "rgb_not_background_only": False,
        "label_bbox_area_reasonable": False,
        "rgb_defect_bbox_visible": False,
    }
    rgb_size = _png_size(rgb_path)
    mask_size = _png_size(mask_path)
    rgb_stats = _png_luma_stats(rgb_path)
    mask_stats = _png_luma_stats(mask_path)
    mask_foreground_stats = _png_mask_foreground_stats(mask_path)
    checks["rgb_readable"] = rgb_size is not None
    checks["mask_readable"] = mask_size is not None
    checks["mask_not_empty"] = mask_foreground_stats is not None and mask_foreground_stats["foreground_pixels"] > 0
    checks["rgb_luma_stats"] = rgb_stats
    checks["rgb_exposure_stats"] = _png_exposure_stats(rgb_path)
    checks["mask_foreground_stats"] = mask_foreground_stats
    checks["rgb_not_blank"] = (
        rgb_stats is not None
        and rgb_stats["max"] >= 8
        and (rgb_stats["max"] - rgb_stats["min"]) >= 3
        and rgb_stats["mean"] >= 2.0
    )
    checks["rgb_not_overexposed"] = _rgb_not_overexposed(checks["rgb_exposure_stats"])
    checks["rgb_not_background_only"] = _rgb_not_background_only(checks["rgb_exposure_stats"])
    background_override = _allow_manual_background_visibility_override(sample)
    checks["rgb_not_background_only_manual_override"] = bool(
        background_override and not checks["rgb_not_background_only"]
    )
    if checks["rgb_not_background_only_manual_override"]:
        checks["manual_background_override_reason"] = background_override
    checks["image_size_matches_mask"] = rgb_size is not None and rgb_size == mask_size
    if label_path.exists():
        label_text = label_path.read_text(encoding="utf-8").strip()
        checks["label_not_empty"] = bool(label_text)
        checks["label_bbox_in_0_1"] = _yolo_label_in_range(label_text)
        checks["label_matches_backend_bbox"] = _label_matches_backend_bbox(
            label_text,
            sample.get("bbox"),
            rgb_size,
        )
        checks["label_bbox_area_reasonable"] = _label_bbox_area_reasonable(label_text)
    checks["rgb_defect_bbox_visible"] = _rgb_defect_bbox_visible(rgb_path, sample.get("bbox"))
    visibility_override = _allow_manual_rgb_visibility_override(sample)
    checks["rgb_defect_bbox_visible_manual_override"] = bool(
        visibility_override and not checks["rgb_defect_bbox_visible"]
    )
    if checks["rgb_defect_bbox_visible_manual_override"]:
        checks["manual_override_reason"] = visibility_override
    required_checks = [
        "rgb_exists",
        "mask_exists",
        "label_exists",
        "metadata_exists",
        "rgb_readable",
        "mask_readable",
        "mask_not_empty",
        "rgb_not_blank",
        "image_size_matches_mask",
        "label_bbox_in_0_1",
        "label_matches_backend_bbox",
        "label_not_empty",
        "rgb_not_overexposed",
        "rgb_not_background_only",
        "label_bbox_area_reasonable",
        "rgb_defect_bbox_visible",
    ]
    checks["passed"] = all(
        checks[key]
        for key in required_checks
        if (
            (key != "rgb_defect_bbox_visible" or not checks["rgb_defect_bbox_visible_manual_override"])
            and (key != "rgb_not_background_only" or not checks["rgb_not_background_only_manual_override"])
        )
    )
    if not checks["passed"]:
        raise RuntimeError("Quality checks failed for sample {0}: {1}".format(sample.get("index"), checks))
    return checks


def _allow_manual_rgb_visibility_override(sample):
    target = str(sample.get("backend_model") or sample.get("target") or "").lower()
    defect_type = str(sample.get("defect_type") or "").lower()
    accepted_subtle_combinations = {
        ("qc71336_black", "splay"): "manual RGB/mask review is the acceptance standard for subtle QC71336 black splay",
        ("qc71336_white", "foreign_material"): "manual RGB/mask review is the acceptance standard for accepted QC71336 white foreign material",
        ("qc71336_gray", "mixed_color_contamination"): "manual RGB/mask review is the acceptance standard for subtle QC71336 gray mixed color",
        ("qc7_5244_black", "black_dot"): "manual RGB/mask review is the acceptance standard for subtle QC7-5244 black black-dot",
        ("qc7_5244_black", "splay"): "manual RGB/mask review is the acceptance standard for subtle QC7-5244 black splay",
        ("qc7_5244_white", "mixed_color_contamination"): "manual RGB/mask review is the acceptance standard for accepted QC7-5244 white mixed color",
        ("ql3_1052_black", "foreign_material"): "manual RGB/mask review is the acceptance standard for sparse QL3 foreign material",
        ("ql3_1052_black", "splay"): "manual RGB/mask review is the acceptance standard for subtle QL3 splay",
    }
    return accepted_subtle_combinations.get((target, defect_type))


def _allow_manual_background_visibility_override(sample):
    target = str(sample.get("backend_model") or sample.get("target") or "").lower()
    defect_type = str(sample.get("defect_type") or "").lower()
    accepted_low_edge_combinations = {
        ("ql3_1052_black", "foreign_material"): "manual RGB/mask review is the acceptance standard for low-edge QL3 side views",
        ("ql3_1052_black", "splay"): "manual RGB/mask review is the acceptance standard for low-edge QL3 side views",
        ("qc7_5244_white", "mixed_color_contamination"): "manual RGB/mask review is the acceptance standard for low-edge QC7-5244 white mixed color",
    }
    return accepted_low_edge_combinations.get((target, defect_type))


def run_cooccurrence_quality_checks(sample, expected_defect_count):
    rgb_path = Path(sample["rgb"])
    mask_path = Path(sample["mask"])
    label_path = Path(sample["label_yolo"])
    metadata_path = Path(sample["metadata"])
    checks = {
        "rgb_exists": rgb_path.exists(),
        "mask_exists": mask_path.exists(),
        "label_exists": label_path.exists(),
        "metadata_exists": metadata_path.exists(),
        "rgb_readable": False,
        "mask_readable": False,
        "mask_not_empty": False,
        "rgb_not_blank": False,
        "image_size_matches_mask": False,
        "label_not_empty": False,
        "label_bbox_in_0_1": False,
        "label_line_count_matches_defects": False,
        "metadata_defect_count_matches": False,
        "rgb_not_overexposed": False,
        "rgb_not_background_only": False,
        "label_bbox_area_reasonable": False,
    }
    rgb_size = _png_size(rgb_path)
    mask_size = _png_size(mask_path)
    rgb_stats = _png_luma_stats(rgb_path)
    mask_stats = _png_luma_stats(mask_path)
    mask_foreground_stats = _png_mask_foreground_stats(mask_path)
    checks["rgb_readable"] = rgb_size is not None
    checks["mask_readable"] = mask_size is not None
    checks["mask_not_empty"] = mask_foreground_stats is not None and mask_foreground_stats["foreground_pixels"] > 0
    checks["rgb_luma_stats"] = rgb_stats
    checks["rgb_exposure_stats"] = _png_exposure_stats(rgb_path)
    checks["mask_foreground_stats"] = mask_foreground_stats
    checks["rgb_not_blank"] = (
        rgb_stats is not None
        and rgb_stats["max"] >= 8
        and (rgb_stats["max"] - rgb_stats["min"]) >= 3
        and rgb_stats["mean"] >= 2.0
    )
    checks["rgb_not_overexposed"] = _rgb_not_overexposed(checks["rgb_exposure_stats"])
    checks["rgb_not_background_only"] = _rgb_not_background_only(checks["rgb_exposure_stats"])
    background_override = _allow_manual_background_visibility_override(sample)
    checks["rgb_not_background_only_manual_override"] = bool(
        background_override and not checks["rgb_not_background_only"]
    )
    if checks["rgb_not_background_only_manual_override"]:
        checks["manual_background_override_reason"] = background_override
    checks["image_size_matches_mask"] = rgb_size is not None and rgb_size == mask_size
    if label_path.exists():
        label_text = label_path.read_text(encoding="utf-8").strip()
        label_lines = [line for line in label_text.splitlines() if line.strip()]
        checks["label_not_empty"] = bool(label_lines)
        checks["label_bbox_in_0_1"] = _yolo_label_in_range(label_text)
        checks["label_line_count_matches_defects"] = len(label_lines) == expected_defect_count
        checks["label_bbox_area_reasonable"] = _label_bbox_area_reasonable(label_text)
    checks["metadata_defect_count_matches"] = len(sample.get("defects", [])) == expected_defect_count
    required_checks = [
        "rgb_exists",
        "mask_exists",
        "label_exists",
        "metadata_exists",
        "rgb_readable",
        "mask_readable",
        "mask_not_empty",
        "rgb_not_blank",
        "image_size_matches_mask",
        "label_not_empty",
        "label_bbox_in_0_1",
        "label_line_count_matches_defects",
        "metadata_defect_count_matches",
        "rgb_not_overexposed",
        "rgb_not_background_only",
        "label_bbox_area_reasonable",
    ]
    checks["passed"] = all(
        checks[key]
        for key in required_checks
        if key != "rgb_not_background_only" or not checks["rgb_not_background_only_manual_override"]
    )
    if not checks["passed"]:
        raise RuntimeError("Cooccurrence quality checks failed for sample {0}: {1}".format(sample.get("index"), checks))
    return checks


def run_normal_quality_checks(sample):
    rgb_path = Path(sample["rgb"])
    mask_path = Path(sample["mask"])
    label_path = Path(sample["label_yolo"])
    metadata_path = Path(sample["metadata"])
    checks = {
        "rgb_exists": rgb_path.exists(),
        "mask_exists": mask_path.exists(),
        "label_exists": label_path.exists(),
        "metadata_exists": metadata_path.exists(),
        "rgb_readable": False,
        "mask_readable": False,
        "mask_empty": False,
        "rgb_not_blank": False,
        "image_size_matches_mask": False,
        "label_empty": False,
    }
    rgb_size = _png_size(rgb_path)
    mask_size = _png_size(mask_path)
    rgb_stats = _png_luma_stats(rgb_path)
    mask_stats = _png_luma_stats(mask_path)
    checks["rgb_readable"] = rgb_size is not None
    checks["mask_readable"] = mask_size is not None
    checks["mask_empty"] = mask_stats is not None and mask_stats["max"] == 0
    checks["rgb_luma_stats"] = rgb_stats
    checks["rgb_not_blank"] = (
        rgb_stats is not None
        and rgb_stats["max"] >= 8
        and (rgb_stats["max"] - rgb_stats["min"]) >= 3
        and rgb_stats["mean"] >= 2.0
    )
    checks["image_size_matches_mask"] = rgb_size is not None and rgb_size == mask_size
    checks["label_empty"] = label_path.exists() and label_path.read_text(encoding="utf-8").strip() == ""
    checks["passed"] = all(value for key, value in checks.items() if key not in {"rgb_luma_stats"})
    if not checks["passed"]:
        raise RuntimeError("Normal quality checks failed for sample {0}: {1}".format(sample.get("index"), checks))
    return checks


def _png_luma_stats(path):
    if not path.exists():
        return None
    try:
        from PIL import Image, ImageStat

        with Image.open(path) as image:
            gray = image.convert("L")
            extrema = gray.getextrema()
            stats = ImageStat.Stat(gray)
            return {
                "mean": float(stats.mean[0]),
                "min": int(extrema[0]),
                "max": int(extrema[1]),
            }
    except Exception:
        return None


def _png_exposure_stats(path):
    if not path.exists():
        return None
    try:
        from PIL import Image, ImageFilter, ImageStat

        with Image.open(path) as image:
            gray = image.convert("L")
            extrema = gray.getextrema()
            stats = ImageStat.Stat(gray)
            hist = gray.histogram()
            total = float(gray.size[0] * gray.size[1])
            edge = gray.filter(ImageFilter.FIND_EDGES)
            edge_stats = ImageStat.Stat(edge)
            return {
                "mean": float(stats.mean[0]),
                "min": int(extrema[0]),
                "max": int(extrema[1]),
                "range": int(extrema[1] - extrema[0]),
                "stddev": float(stats.stddev[0]),
                "edge_mean": float(edge_stats.mean[0]),
                "sat250_fraction": float(sum(hist[250:]) / total),
                "dark5_fraction": float(sum(hist[:5]) / total),
            }
    except Exception:
        return None


def _png_mask_foreground_stats(path, threshold=127):
    if not path.exists():
        return None
    try:
        from PIL import Image

        with Image.open(path) as image:
            gray = image.convert("L")
            hist = gray.histogram()
            foreground_pixels = int(sum(hist[threshold + 1 :]))
            total_pixels = int(gray.size[0] * gray.size[1])
            return {
                "threshold": int(threshold),
                "foreground_pixels": foreground_pixels,
                "total_pixels": total_pixels,
                "foreground_fraction": float(foreground_pixels / total_pixels) if total_pixels else 0.0,
            }
    except Exception:
        return None


def _binarize_mask_outputs(output_dir, threshold=127):
    try:
        from PIL import Image
    except Exception:
        return
    for dirname in ["mask", "masks", "masks_by_class"]:
        mask_dir = Path(output_dir) / dirname
        if not mask_dir.exists():
            continue
        for mask_path in mask_dir.glob("*.png"):
            try:
                with Image.open(mask_path) as image:
                    gray = image.convert("L")
                    binary = gray.point(lambda value: 255 if value > threshold else 0, mode="L")
                    binary.save(mask_path)
            except Exception:
                continue


def _rgb_defect_bbox_visible(rgb_path, bbox, min_mean_delta=3.0):
    if not rgb_path.exists() or not bbox:
        return False
    xyxy = bbox.get("xyxy") if isinstance(bbox, dict) else None
    if not xyxy or len(xyxy) != 4:
        return False
    try:
        from PIL import Image, ImageStat

        with Image.open(rgb_path) as image:
            gray = image.convert("L")
            width, height = gray.size
            x0 = max(0, min(width - 1, int(xyxy[0])))
            y0 = max(0, min(height - 1, int(xyxy[1])))
            x1 = max(x0 + 1, min(width, int(xyxy[2])))
            y1 = max(y0 + 1, min(height, int(xyxy[3])))
            pad = max(12, min(40, int(max(x1 - x0, y1 - y0) * 3)))
            outer_box = (
                max(0, x0 - pad),
                max(0, y0 - pad),
                min(width, x1 + pad),
                min(height, y1 + pad),
            )
            inner_stats = ImageStat.Stat(gray.crop((x0, y0, x1, y1)))
            outer_stats = ImageStat.Stat(gray.crop(outer_box))
            mean_delta = abs(float(inner_stats.mean[0]) - float(outer_stats.mean[0]))
            return mean_delta >= min_mean_delta
    except Exception:
        return False


def _rgb_not_overexposed(stats):
    if stats is None:
        return False
    if stats["mean"] >= 224.0:
        return False
    if stats["sat250_fraction"] >= 0.18:
        return False
    return True


def _rgb_not_background_only(stats):
    if stats is None:
        return False
    if stats["range"] < 18:
        return False
    if stats.get("edge_mean", 0.0) < 2.2:
        return False
    return True


def _label_bbox_area_reasonable(label_text, max_fraction=0.075):
    if not label_text:
        return False
    for line in label_text.splitlines():
        parts = line.strip().split()
        if len(parts) != 5:
            return False
        try:
            width = float(parts[3])
            height = float(parts[4])
        except ValueError:
            return False
        if width <= 0.0 or height <= 0.0:
            return False
        if width * height > max_fraction:
            return False
    return True
    try:
        from PIL import Image, ImageFilter, ImageStat

        with Image.open(path) as image:
            gray = image.convert("L")
            extrema = gray.getextrema()
            stats = ImageStat.Stat(gray)
            return {
                "mean": float(stats.mean[0]),
                "min": int(extrema[0]),
                "max": int(extrema[1]),
            }
    except Exception:
        return None


def _ensure_framework_output_dirs(output_dir):
    for dirname in ["rgb", "masks", "labels_yolo", "metadata"]:
        (output_dir / dirname).mkdir(parents=True, exist_ok=True)


def _framework_sample_paths(output_dir, index):
    image_id = "{0:06d}".format(index)
    return {
        "rgb": output_dir / "rgb" / (image_id + ".png"),
        "mask": output_dir / "masks" / (image_id + ".png"),
        "label_yolo": output_dir / "labels_yolo" / (image_id + ".txt"),
        "metadata": output_dir / "metadata" / (image_id + ".json"),
    }


def _build_reference_blackdot_command(
    python_executable,
    blenderproc_cli,
    backend_script,
    backend_model,
    raw_output_dir,
    count,
    samples,
    seed,
    anchor_side,
    blend_path,
    material_path=None,
    defect_config=None,
    object_transform_mode="none",
    object_transform_camera_side="front",
    object_rotate_deg=None,
    object_translate=None,
    normal_mode=False,
    defect_count_max=1,
):
    command = [
        str(python_executable),
        str(blenderproc_cli),
        "run",
        str(backend_script),
        "--",
        "--model",
        backend_model,
        "--output",
        str(raw_output_dir),
        "--num",
        str(count),
        "--start_index",
        "0",
        "--samples",
        str(samples),
        "--seed",
        str(seed),
        "--anchor_sides",
        anchor_side,
    ]
    if blend_path is not None:
        command.extend(["--blend", str(blend_path)])
    if material_path is not None:
        command.extend(["--material_json", str(material_path)])
    if normal_mode:
        command.append("--normal_mode")
    elif int(defect_count_max or 1) > 1:
        command.extend(["--black_dot_max_count", str(int(defect_count_max))])
    _append_object_transform_args(command, object_transform_mode, object_transform_camera_side, object_rotate_deg, object_translate)
    backend_params = _extract_blackdot_backend_parameters(defect_config or {})
    mapping = {
        "black_dot_radius_min_scale": "--black_dot_radius_min_scale",
        "black_dot_radius_max_scale": "--black_dot_radius_max_scale",
        "black_dot_depth_min_scale": "--black_dot_depth_min_scale",
        "black_dot_depth_max_scale": "--black_dot_depth_max_scale",
        "black_dot_max_count": "--black_dot_max_count",
    }
    for key, flag in mapping.items():
        if key in backend_params and backend_params[key] is not None:
            value = int(backend_params[key]) if key == "black_dot_max_count" else backend_params[key]
            command.extend([flag, str(value)])
    return command


def _append_object_transform_args(command, mode, camera_side, rotate_deg, translate):
    if mode == "none":
        return
    command.extend(["--object_transform_mode", mode])
    command.extend(["--object_transform_camera_side", camera_side])
    if rotate_deg is not None:
        command.extend(["--object_rotate_deg", *[str(value) for value in rotate_deg]])
    if translate is not None:
        command.extend(["--object_translate", *[str(value) for value in translate]])


def _build_backend_plan(
    status,
    backend_script,
    commands,
    blend_path,
    output_dir,
    raw_output_dir,
    count,
    material,
    material_path,
    apply_material,
    defect_config,
    source_defect_config,
    samples,
    failed_samples,
    backend_model,
    anchor_side,
    seeds_used,
    backend_log,
):
    return {
        "status": status,
        "backend": "reference_blend_blackdot_multi_model.py",
        "backend_script": str(backend_script),
        "commands": commands,
        "blend_file": str(blend_path),
        "output_dir": str(output_dir),
        "raw_backend_output_dir": str(raw_output_dir),
        "count": count,
        "total_requested": count,
        "total_succeeded": len(samples),
        "total_failed": len(failed_samples),
        "failed_samples": failed_samples,
        "model_profile": backend_model,
        "backend_model": backend_model,
        "anchor_side": anchor_side,
        "seeds_used": seeds_used,
        "material_path": str(material_path) if material_path else None,
        "material_override_applied": bool(apply_material and material_path),
        "material_parameters": material.get("material_parameters", material),
        "defect_config": defect_config,
        "source_defect_config": source_defect_config,
        "camera": build_camera_settings(source_defect_config.get("camera_mode", "randomized")),
        "lighting": build_light_settings(source_defect_config.get("lighting_mode", "randomized")),
        "background": build_background_settings(source_defect_config.get("background_mode", "randomized")),
        "samples": samples,
        "backend_log": str(backend_log),
    }


def _build_generic_backend_plan(
    status,
    backend_script,
    command,
    output_dir,
    raw_output_dir,
    target_profile,
    defect_type,
    count,
    samples,
    failed_samples,
    seed,
    anchor_sides,
    samples_requested,
    backend_name="generic_main_plane",
):
    is_reference_backend = backend_name != "generic_main_plane"
    defect_generation_logic = (
        {
            "backend": backend_name,
            "reference_script": str(backend_script),
            "uses_reference_defect_functions": True,
        }
        if is_reference_backend
        else {
            "backend": "generic_main_plane",
            "shared_single_generic_function": "render_generic_main_plane_defects.create_defect",
        }
    )
    return {
        "status": status,
        "backend": backend_name,
        "backend_script": str(backend_script),
        "commands": [command],
        "output_dir": str(output_dir),
        "raw_backend_output_dir": str(raw_output_dir),
        "count": count,
        "total_requested": count,
        "total_succeeded": len(samples),
        "total_failed": len(failed_samples),
        "failed_samples": failed_samples,
        "target_profile": target_profile,
        "model_profile": target_profile.get("target_id"),
        "defect_type": defect_type,
        "anchor_sides": anchor_sides,
        "seeds_used": [int(seed) + index for index in range(count)],
        "render_samples": samples_requested,
        "placement_policy": target_profile.get("placement_policy", "front_back_main_planes_only"),
        "material_source": target_profile.get("material_source"),
        "defect_generation_logic": defect_generation_logic,
        "camera": build_camera_settings("randomized"),
        "lighting": build_light_settings("randomized"),
        "background": build_background_settings("randomized"),
        "samples": samples,
        "backend_log": str(output_dir / "backend_run_log.json"),
        "quality_goal": "coverage_first_not_visual_realism",
    }


def _build_generic_cooccurrence_plan(
    status,
    backend_script,
    command,
    output_dir,
    target_profile,
    defect_types,
    count,
    samples,
    failed_samples,
    seed,
    anchor_sides,
    samples_requested,
):
    return {
        "status": status,
        "backend": "generic_main_plane_cooccurrence",
        "backend_script": str(backend_script),
        "commands": [command],
        "output_dir": str(output_dir),
        "raw_backend_output_dir": str(output_dir),
        "count": count,
        "total_requested": count,
        "total_succeeded": len(samples),
        "total_failed": len(failed_samples),
        "failed_samples": failed_samples,
        "target_profile": target_profile,
        "model_profile": target_profile.get("target_id"),
        "defect_types": defect_types,
        "anchor_sides": anchor_sides,
        "seeds_used": [int(seed) + index for index in range(count)],
        "render_samples": samples_requested,
        "placement_policy": target_profile.get("placement_policy", "front_back_main_planes_only"),
        "material_source": target_profile.get("material_source"),
        "defect_generation_logic": {
            "backend": "generic_main_plane_cooccurrence",
            "shared_single_generic_function": "render_generic_main_plane_defects.create_defect",
            "position_resampling_only": True,
        },
        "camera": build_camera_settings("randomized"),
        "lighting": build_light_settings("randomized"),
        "background": build_background_settings("randomized"),
        "samples": samples,
        "backend_log": str(output_dir / "backend_run_log.json"),
        "generation_mode": "multi_defect_cooccurrence",
        "quality_goal": "cooccurrence_proof_first_not_visual_realism",
    }


def _build_generic_normal_plan(
    status,
    backend_script,
    command,
    output_dir,
    target_profile,
    count,
    samples,
    failed_samples,
    seed,
    anchor_sides,
    samples_requested,
):
    return {
        "status": status,
        "backend": "generic_main_plane_normal",
        "backend_script": str(backend_script),
        "commands": [command],
        "output_dir": str(output_dir),
        "raw_backend_output_dir": str(output_dir),
        "count": count,
        "total_requested": count,
        "total_succeeded": len(samples),
        "total_failed": len(failed_samples),
        "failed_samples": failed_samples,
        "target_profile": target_profile,
        "model_profile": target_profile.get("target_id"),
        "defect_types": [],
        "is_normal": True,
        "anchor_sides": anchor_sides,
        "seeds_used": [int(seed) + index for index in range(count)],
        "render_samples": samples_requested,
        "placement_policy": target_profile.get("placement_policy", "front_back_main_planes_only"),
        "material_source": target_profile.get("material_source"),
        "camera": build_camera_settings("randomized"),
        "lighting": build_light_settings("randomized"),
        "background": build_background_settings("randomized"),
        "samples": samples,
        "backend_log": str(output_dir / "backend_run_log.json"),
        "generation_mode": "normal",
        "quality_goal": "normal_negative_samples",
    }


def _persistent_planned_samples(output_dir, sample_specs, seed):
    planned = []
    for ordinal, spec in enumerate(sample_specs):
        sample_index = int(spec.get("index", ordinal))
        paths = _framework_sample_paths(output_dir, sample_index)
        planned.append(
            {
                "index": sample_index,
                "seed": int(spec.get("seed", int(seed) + sample_index)),
                "mode": spec.get("mode", "single"),
                "defect_types": list(spec.get("defects", [])),
                "rgb": str(paths["rgb"]),
                "mask": str(paths["mask"]),
                "label_yolo": str(paths["label_yolo"]),
                "metadata": str(paths["metadata"]),
                "status": "planned_only",
            }
        )
    return planned


def _build_persistent_generic_batch_plan(
    status,
    backend_script,
    command,
    output_dir,
    target_profile,
    samples,
    failed_samples,
    seed,
    render_samples,
):
    return {
        "status": status,
        "backend": "persistent_generic_batch",
        "backend_script": str(backend_script),
        "commands": [command],
        "output_dir": str(output_dir),
        "raw_backend_output_dir": str(output_dir),
        "count": len(samples) + len(failed_samples),
        "total_requested": len(samples) + len(failed_samples),
        "total_succeeded": len(samples),
        "total_failed": len(failed_samples),
        "failed_samples": failed_samples,
        "target_profile": target_profile,
        "model_profile": target_profile.get("target_id"),
        "seed": seed,
        "render_samples": render_samples,
        "placement_policy": target_profile.get("placement_policy", "front_back_main_planes_only"),
        "material_source": target_profile.get("material_source"),
        "defect_generation_logic": {
            "backend": "persistent_generic_batch",
            "shared_single_generic_function": "render_generic_main_plane_defects.create_defect",
            "reference_backends_supported": False,
        },
        "samples": samples,
        "backend_log": str(output_dir / "backend_run_log.json"),
        "generation_mode": "persistent_generic_batch",
        "quality_goal": "persistent_batch_efficiency_with_generic_backend_equivalence",
    }


def _copy_if_exists(src, dst, files_produced):
    if not src.exists():
        raise FileNotFoundError("Expected backend output missing: {0}".format(src))
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(dst))
    files_produced.append(str(dst))


def _failed_backend_plan(output_dir, backend_script, command, log, normalized_defects):
    plan = {
        "status": "failed",
        "backend": "reference_blend_blackdot_multi_model.py",
        "backend_script": str(backend_script),
        "commands": command,
        "output_dir": str(output_dir),
        "total_requested": 0,
        "total_succeeded": 0,
        "total_failed": 0,
        "failed_samples": [],
        "defect_config": normalized_defects,
        "failure_reason": log.get("failure_reason"),
        "backend_log": str(output_dir / "backend_run_log.json"),
        "samples": [],
    }
    write_json(output_dir / "generation_plan.json", plan)
    write_dataset_summary(output_dir / "dataset_summary.json", plan)
    return plan


def _png_size(path):
    if not path.exists():
        return None
    with path.open("rb") as f:
        header = f.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", header[16:24])


def _yolo_label_in_range(label_text):
    if not label_text:
        return False
    for line in label_text.splitlines():
        parts = line.strip().split()
        if len(parts) != 5:
            return False
        try:
            values = [float(value) for value in parts[1:]]
        except ValueError:
            return False
        if any(value < 0.0 or value > 1.0 for value in values):
            return False
    return True


def _label_matches_backend_bbox(label_text, bbox, image_size):
    if not label_text or not bbox or image_size is None:
        return False
    first_line = label_text.splitlines()[0].strip().split()
    if len(first_line) != 5:
        return False
    try:
        label_values = [float(value) for value in first_line[1:]]
    except ValueError:
        return False
    width, height = image_size
    x, y, w, h = bbox.get("xywh", [None, None, None, None])
    if None in [x, y, w, h] or width <= 0 or height <= 0:
        return False
    expected = [
        (float(x) + float(w) / 2.0) / float(width),
        (float(y) + float(h) / 2.0) / float(height),
        float(w) / float(width),
        float(h) / float(height),
    ]
    return all(abs(a - b) <= 1e-5 for a, b in zip(label_values, expected))


def _sample_anchor_side(sample):
    if sample.get("anchor_side"):
        return sample.get("anchor_side")
    for defect_info in sample.get("defects", []) or []:
        if isinstance(defect_info, dict) and defect_info.get("anchor_side"):
            return defect_info.get("anchor_side")
    for key in ("black_dot", "foreign_material", "mixed_color_contamination", "splay"):
        defect_info = sample.get(key)
        if isinstance(defect_info, dict) and defect_info.get("anchor_side"):
            return defect_info.get("anchor_side")
    return None


def _blackdot_only_defect_config(normalized_defects):
    blackdot_items = [
        item
        for item in normalized_defects.get("defects", [])
        if item.get("defect_type") == "black_dot"
    ]
    if not blackdot_items:
        raise ValueError("Reference black-dot backend requires a black_spot or black_dot defect.")
    return {
        "schema_version": normalized_defects.get("schema_version", "0.1"),
        "mode": normalized_defects.get("mode", "randomized"),
        "position_mode": normalized_defects.get("position_mode", "random_visible_surface"),
        "defects": blackdot_items[:1],
        "black_dot_appearance_preset": normalized_defects.get("black_dot_appearance_preset"),
        "backend_note": "Only black_spot/black_dot is passed to the first production backend.",
    }


def _extract_blackdot_backend_parameters(defect_config):
    preset = defect_config.get("black_dot_appearance_preset") or {}
    params = dict(preset.get("backend_parameters") or {})
    backend_params = defect_config.get("backend_parameters") or {}
    params.update(backend_params)
    return params


def _profile_path(project_root, value):
    if not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    return (project_root / path).resolve()
