from datetime import datetime
import json
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional

from core.file_manager import IMAGE_SUFFIXES
from core.metadata_writer import write_json
from core.similarity_metrics import DEFAULT_WEIGHTS, PLASTIC_MATERIAL_WEIGHTS, compare_images, mock_similarity_score, parse_roi_box


MATERIAL_KEYS = [
    "base_color",
    "roughness",
    "specular",
    "specular_ior_level",
    "subsurface",
    "translucency",
    "noise_scale",
    "noise_strength",
    "bump_strength",
    "alpha",
]
SCENE_KEYS = [
    "light_strength",
    "exposure",
    "camera_profile",
    "render_resolution",
    "background_color",
]
DEFAULT_MATERIAL_PARAMETERS = {
    "base_color": [0.78, 0.80, 0.82, 1.0],
    "roughness": 0.5,
    "specular": 0.35,
    "subsurface": 0.0,
    "noise_scale": 48.0,
    "noise_strength": 0.0,
    "bump_strength": 0.0,
}
DEFAULT_SCENE_CALIBRATION = {
    "light_strength": 450.0,
    "exposure": 0.0,
    "camera_profile": "deterministic_ortho_front",
    "render_resolution": [512, 384],
    "background_color": [0.78, 0.78, 0.78, 1.0],
}


def fit_material(
    reference_images: List[Path],
    blend_file: Path,
    output_dir: Path,
    search_space: Dict[str, Any],
    candidates_limit: Optional[int] = None,
    roi_mode: str = "center",
    resize: int = 512,
    scoring: str = "mock",
    candidate_dir: Optional[Path] = None,
    render_candidates: bool = False,
    project_root: Optional[Path] = None,
    python_executable: Optional[Path] = None,
    samples: int = 16,
    seed: int = 100,
    material_profile: str = "opaque_white_plastic",
    roi_box: Optional[Any] = None,
    roi_mask: Optional[Path] = None,
    render_width: int = 512,
    render_height: int = 384,
    score_profile: str = "baseline",
) -> Dict[str, Any]:
    if scoring not in {"mock", "real"}:
        raise ValueError("scoring must be 'mock' or 'real'")
    if render_candidates and scoring != "real":
        raise ValueError("--render-candidates requires --scoring real")
    parsed_roi_box = parse_roi_box(roi_box) if roi_box is not None else None
    if roi_mode == "manual" and parsed_roi_box is None:
        raise ValueError("--roi-box is required when --roi manual")
    if roi_mode != "manual" and parsed_roi_box is not None:
        raise ValueError("--roi-box can only be used with --roi manual")
    if roi_mode == "mask" and roi_mask is None:
        raise ValueError("--roi-mask is required when --roi mask")
    if roi_mode != "mask" and roi_mask is not None:
        raise ValueError("--roi-mask can only be used with --roi mask")
    if roi_mask is not None and not Path(roi_mask).exists():
        raise FileNotFoundError("ROI mask not found: {0}".format(roi_mask))
    if int(render_width) < 8 or int(render_height) < 8:
        raise ValueError("--render-width and --render-height must be >= 8")
    if score_profile not in {"baseline", "plastic_material"}:
        raise ValueError("--score-profile must be one of: baseline, plastic_material")
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates = generate_candidate_materials(search_space)
    if candidates_limit is not None:
        candidates = _select_candidate_subset(candidates, max(0, int(candidates_limit)))
    if not candidates:
        raise ValueError("No material candidates available.")

    candidate_images = []
    warnings = []
    render_commands = []
    command_settings = {
        "candidates_limit": candidates_limit,
        "roi_mode": roi_mode,
        "roi_box": list(parsed_roi_box) if parsed_roi_box else None,
        "roi_mask": str(roi_mask) if roi_mask else None,
        "resize": resize,
        "scoring": scoring,
        "candidate_dir": str(candidate_dir) if candidate_dir else None,
        "render_candidates": render_candidates,
        "samples": samples,
        "seed": seed,
        "material_profile": material_profile,
        "render_width": int(render_width),
        "render_height": int(render_height),
        "score_profile": score_profile,
    }
    if scoring == "real":
        if render_candidates:
            if project_root is None or python_executable is None:
                raise ValueError("project_root and python_executable are required when render_candidates=True.")
            render_result = render_candidate_images(
                candidates=candidates,
                blend_file=blend_file,
                output_dir=output_dir,
                project_root=project_root,
                python_executable=python_executable,
                samples=samples,
                seed=seed,
                material_profile=material_profile,
                render_width=int(render_width),
                render_height=int(render_height),
            )
            candidate_images = render_result["candidate_images"]
            render_commands = render_result["commands"]
            warnings.extend(render_result["warnings"])
        else:
            if candidate_dir is None:
                raise ValueError("--candidate-dir is required when --scoring real unless --render-candidates is used.")
            candidate_images = discover_candidate_images(candidate_dir)
            if not candidate_images:
                raise FileNotFoundError("No candidate images found in: {0}".format(candidate_dir))
            if len(candidate_images) < len(candidates):
                warnings.append(
                    "candidate_dir has {0} images for {1} material candidates; remaining candidates are skipped.".format(
                        len(candidate_images), len(candidates)
                    )
                )
            if len(candidate_images) > len(candidates):
                warnings.append(
                    "candidate_dir has {0} images for {1} material candidates; extra images are ignored.".format(
                        len(candidate_images), len(candidates)
                    )
                )

    scored = []
    for index, params in enumerate(candidates):
        render_path = candidate_images[index] if scoring == "real" and index < len(candidate_images) else None
        if scoring == "real" and render_path is None:
            if render_candidates:
                scored.append(
                    _failed_candidate(
                        index,
                        params,
                        reference_images,
                        render_path,
                        "candidate_render_failed_or_missing",
                        material_json_path=_candidate_material_path(output_dir, index),
                        metadata_path=_candidate_metadata_path(output_dir, index),
                        render_status=_read_render_status(_candidate_metadata_path(output_dir, index)),
                    )
                )
            else:
                scored.append(_skipped_candidate(index, params, reference_images, "missing_candidate_render"))
            continue
        try:
            entry = _score_candidate(
                candidate_id=index,
                params=params,
                reference_images=reference_images,
                render_path=render_path,
                roi_mode=roi_mode,
                roi_box=parsed_roi_box,
                roi_mask=roi_mask,
                resize=resize,
                scoring=scoring,
                material_json_path=_candidate_material_path(output_dir, index) if render_candidates else None,
                metadata_path=_candidate_metadata_path(output_dir, index) if render_candidates else None,
                render_status=_read_render_status(_candidate_metadata_path(output_dir, index)) if render_candidates else ("available" if render_path else None),
                render_width=int(render_width),
                render_height=int(render_height),
                score_profile=score_profile,
            )
        except Exception as exc:
            entry = _failed_candidate(
                index,
                params,
                reference_images,
                render_path,
                str(exc),
                material_json_path=_candidate_material_path(output_dir, index) if render_candidates else None,
                metadata_path=_candidate_metadata_path(output_dir, index) if render_candidates else None,
                render_status=_read_render_status(_candidate_metadata_path(output_dir, index)) if render_candidates else None,
            )
        scored.append(entry)

    successful = [item for item in scored if item["status"] == "success"]
    ranked = sorted(successful, key=lambda item: item["score"], reverse=True)
    for rank, item in enumerate(ranked, start=1):
        item["rank"] = rank
    for item in scored:
        if item["status"] != "success":
            item["rank"] = None

    best = ranked[0] if ranked else None
    now = datetime.now().isoformat(timespec="seconds")
    candidate_export = {
        "schema_version": "0.2",
        "created_at": now,
        "calibration_type": "visual_material_calibration",
        "scoring": scoring,
        "score_profile": score_profile,
        "metric_backend": "mock" if scoring == "mock" else "pillow_baseline",
        "roi_mode": roi_mode,
        "roi_box": list(parsed_roi_box) if parsed_roi_box else None,
        "roi_mask": str(roi_mask) if roi_mask else None,
        "resize": resize,
        "reference_images": [str(p) for p in reference_images],
        "candidate_dir": str(candidate_dir) if candidate_dir else None,
        "render_candidates": render_candidates,
        "render_commands": render_commands,
        "candidates": scored,
    }
    write_json(output_dir / "material_fit_candidates.json", candidate_export)

    best_material = _build_best_material_export(
        best=best,
        blend_file=blend_file,
        reference_images=reference_images,
        scoring=scoring,
        score_profile=score_profile,
        roi_mode=roi_mode,
        resize=resize,
        roi_box=parsed_roi_box,
        roi_mask=roi_mask,
        created_at=now,
        warnings=warnings,
    )
    write_json(output_dir / "best_material.json", best_material)

    report = {
        "schema_version": "0.2",
        "created_at": now,
        "calibration_type": "visual_material_calibration",
        "scoring": scoring,
        "score_profile": score_profile,
        "metric_backend": "mock" if scoring == "mock" else "pillow_baseline",
        "roi_mode": roi_mode,
        "roi_box": list(parsed_roi_box) if parsed_roi_box else None,
        "roi_mask": str(roi_mask) if roi_mask else None,
        "resize": resize,
        "number_of_candidates": len(scored),
        "total_candidates_requested": len(scored),
        "number_succeeded": len(successful),
        "succeeded": len(successful),
        "number_failed": len([item for item in scored if item["status"] == "failed"]),
        "failed": len([item for item in scored if item["status"] == "failed"]),
        "number_skipped": len([item for item in scored if item["status"] == "skipped"]),
        "best_candidate_id": best["candidate_id"] if best else None,
        "top_5_candidates": ranked[:5],
        "scoring_weights": _weights_for_profile(score_profile),
        "command_settings": command_settings,
        "render_commands": render_commands,
        "warnings": warnings,
    }
    write_json(output_dir / "material_fitting_report.json", report)
    write_json(
        output_dir / "best_preview_render.json",
        {
            "status": "available" if best and best.get("render_path") else "not_available",
            "best_candidate_id": best["candidate_id"] if best else None,
            "render_path": best.get("render_path") if best else None,
            "notes": "Best preview is the highest-ranked candidate render when available.",
        },
    )
    return {
        "best_material": str(output_dir / "best_material.json"),
        "candidate_report": str(output_dir / "material_fit_candidates.json"),
        "material_fitting_report": str(output_dir / "material_fitting_report.json"),
        "best_preview": str(output_dir / "best_preview_render.json"),
        "score": best["score"] if best else None,
        "best_candidate_id": best["candidate_id"] if best else None,
        "scoring": scoring,
    }


def discover_candidate_images(candidate_dir: Path) -> List[Path]:
    if not candidate_dir.exists():
        raise FileNotFoundError("Candidate directory not found: {0}".format(candidate_dir))
    if not candidate_dir.is_dir():
        raise ValueError("candidate_dir must be a folder: {0}".format(candidate_dir))
    return sorted(
        p for p in candidate_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    )


def render_candidate_images(
    candidates,
    blend_file,
    output_dir,
    project_root,
    python_executable,
    samples,
    seed,
    material_profile,
    render_width,
    render_height,
):
    material_dir = output_dir / "candidate_materials"
    render_dir = output_dir / "candidate_renders"
    metadata_dir = output_dir / "candidate_metadata"
    for path in [material_dir, render_dir, metadata_dir]:
        path.mkdir(parents=True, exist_ok=True)

    script_path = project_root / "defect_dataset_generator" / "blender_scripts" / "render_candidate.py"
    blenderproc_cli = project_root / "cli.py"
    candidate_images = []
    commands = []
    warnings = []
    for index, params in enumerate(candidates):
        material_json_path = _candidate_material_path(output_dir, index)
        render_path = _candidate_render_path(output_dir, index)
        metadata_path = _candidate_metadata_path(output_dir, index)
        material_params = _material_parameters(params)
        scene_calibration = _scene_calibration(params, render_width, render_height)
        material_payload = {
            "schema_version": "0.2",
            "calibration_type": "visual_material_calibration_candidate",
            "candidate_id": index,
            "seed": int(seed) + index,
            "material_profile": material_profile,
            "material_parameters": material_params,
            "scene_calibration": scene_calibration,
        }
        material_json_path.write_text(json.dumps(material_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        command = [
            str(python_executable),
            str(blenderproc_cli),
            "run",
            str(script_path),
            "--",
            "--blend",
            str(blend_file),
            "--material-json",
            str(material_json_path),
            "--output",
            str(render_path),
            "--metadata",
            str(metadata_path),
            "--width",
            str(render_width),
            "--height",
            str(render_height),
            "--samples",
            str(samples),
        ]
        commands.append(command)
        completed = subprocess.run(
            command,
            cwd=str(project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )
        render_log_path = metadata_dir / "candidate_{0:06d}_render_log.txt".format(index)
        render_log_path.write_text(completed.stdout, encoding="utf-8")
        if completed.returncode != 0:
            warnings.append("candidate_{0:06d} render failed with return code {1}".format(index, completed.returncode))
            candidate_images.append(None)
            if not metadata_path.exists():
                write_json(
                    metadata_path,
                    {
                        "schema_version": "0.1",
                        "status": "failed",
                        "candidate_id": index,
                        "failure_reason": "render_candidate.py returned {0}".format(completed.returncode),
                        "render_log": str(render_log_path),
                    },
                )
            continue
        if not render_path.exists():
            warnings.append("candidate_{0:06d} render command succeeded but image is missing.".format(index))
            candidate_images.append(None)
            continue
        candidate_images.append(render_path)
    return {"candidate_images": candidate_images, "commands": commands, "warnings": warnings}


def generate_candidate_materials(search_space: Dict[str, Any]) -> List[Dict[str, Any]]:
    material_space = search_space.get("material_parameters", search_space)
    scene_space = search_space.get("scene_calibration", search_space)
    base_colors = material_space.get("base_color", [[0.8, 0.8, 0.8, 1.0]])
    roughness_values = material_space.get("roughness", [0.45])
    specular_values = material_space.get("specular", [0.35])
    alpha_values = material_space.get("alpha", [1.0])
    subsurface_values = material_space.get("subsurface", [0.0])
    noise_scale_values = material_space.get("noise_scale", [48.0])
    noise_strength_values = material_space.get("noise_strength", [0.0])
    bump_strength_values = material_space.get("bump_strength", [0.0])
    light_strength_values = scene_space.get("light_strength", [450.0])
    exposure_values = scene_space.get("exposure", [0.0])
    background_color_values = scene_space.get("background_color", [[0.78, 0.78, 0.78, 1.0]])
    candidates = []
    for base_color in base_colors:
        for roughness in roughness_values:
            for specular in specular_values:
                for alpha in alpha_values:
                    for subsurface in subsurface_values:
                        for noise_scale in noise_scale_values:
                            for noise_strength in noise_strength_values:
                                for bump_strength in bump_strength_values:
                                    for light_strength in light_strength_values:
                                        for exposure in exposure_values:
                                            for background_color in background_color_values:
                                                candidates.append(
                                                    {
                                                        "base_color": base_color,
                                                        "roughness": roughness,
                                                        "specular": specular,
                                                        "alpha": alpha,
                                                        "subsurface": subsurface,
                                                        "noise_scale": noise_scale,
                                                        "noise_strength": noise_strength,
                                                        "bump_strength": bump_strength,
                                                        "light_strength": light_strength,
                                                        "exposure": exposure,
                                                        "background_color": background_color,
                                                    }
                                                )
    return candidates


def _select_candidate_subset(candidates, limit):
    if limit <= 0:
        return []
    if limit >= len(candidates):
        return candidates
    if limit == 1:
        return [candidates[0]]
    indexes = []
    last = len(candidates) - 1
    for step in range(limit):
        index = int(round(step * last / float(limit - 1)))
        if index not in indexes:
            indexes.append(index)
    cursor = 0
    while len(indexes) < limit and cursor < len(candidates):
        if cursor not in indexes:
            indexes.append(cursor)
        cursor += 1
    return [candidates[index] for index in indexes[:limit]]


def _score_candidate(
    candidate_id,
    params,
    reference_images,
    render_path,
    roi_mode,
    roi_box,
    roi_mask,
    resize,
    scoring,
    material_json_path=None,
    metadata_path=None,
    render_status=None,
    render_width=512,
    render_height=384,
    score_profile="baseline",
):
    per_reference = []
    per_metric_scores = {}
    material_parameters = _material_parameters(params)
    scene_calibration = _scene_calibration(params, render_width, render_height)
    if scoring == "mock":
        for ref in reference_images:
            metrics = mock_similarity_score(ref, params)
            per_reference.append(
                {
                    "reference_image": str(ref),
                    "render_path": str(render_path) if render_path else None,
                    "weighted_score": metrics["weighted_score"],
                    "metrics": {
                        "brightness": metrics["brightness"],
                        "color_histogram": metrics["color_histogram"],
                        "ssim": metrics["ssim"],
                        "edge_texture": metrics["edge_texture"],
                        "lpips": metrics["lpips"],
                    },
                    "metric_backend": metrics["metric_backend"],
                }
            )
    else:
        for ref in reference_images:
            result = compare_images(
                reference_image=ref,
                candidate_image=render_path,
                roi_mode=roi_mode,
                roi_box=roi_box,
                roi_mask=roi_mask,
                resize=resize,
                score_profile=score_profile,
            )
            per_reference.append(
                {
                    "reference_image": str(ref),
                    "render_path": str(render_path),
                    "weighted_score": result["weighted_score"],
                    "metrics": result["metrics"],
                    "components": result.get("components", result["metrics"]),
                    "metric_backend": result["metric_backend"],
                    "score_profile": result["score_profile"],
                    "preprocessing": result["preprocessing"],
                }
            )
    score = sum(item["weighted_score"] for item in per_reference) / float(len(per_reference))
    metric_names = _metric_names_for_profile(score_profile)
    for name in metric_names:
        values = [
            item.get("components", item["metrics"]).get(name)
            for item in per_reference
            if item.get("components", item["metrics"]).get(name) is not None
        ]
        per_metric_scores[name] = round(sum(values) / float(len(values)), 6) if values else None
    mask_metadata = _extract_mask_metadata(per_reference)
    scoring_payload = {
        "metric_backend": "mock" if scoring == "mock" else "pillow_baseline",
        "score_profile": score_profile,
        "roi_mode": roi_mode,
        "roi_box": list(roi_box) if roi_box else None,
        "roi_mask": str(roi_mask) if roi_mask else None,
        **mask_metadata,
        "resize": int(resize),
        "weighted_score": round(score, 6),
        "components": per_metric_scores,
        "per_metric_scores": per_metric_scores,
        "weights": _weights_for_profile(score_profile),
        "per_reference_similarity": per_reference,
    }
    return {
        "candidate_id": candidate_id,
        "schema_version": "0.2",
        "calibration_type": "visual_material_calibration_candidate",
        "material_parameters": material_parameters,
        "scene_calibration": scene_calibration,
        "scoring": scoring_payload,
        "params": params,
        "sampled_material_parameters": params,
        "material_json_path": str(material_json_path) if material_json_path else None,
        "render_path": str(render_path) if render_path else None,
        "metadata_path": str(metadata_path) if metadata_path else None,
        "render_status": render_status,
        "score": round(score, 6),
        "mean_weighted_score": round(score, 6),
        "per_metric_scores": per_metric_scores,
        "components": per_metric_scores,
        "reference_images_used": [str(p) for p in reference_images],
        "per_reference_similarity": per_reference,
        "status": "success",
        "rank": None,
    }


def _skipped_candidate(candidate_id, params, reference_images, reason):
    return {
        "candidate_id": candidate_id,
        "schema_version": "0.2",
        "calibration_type": "visual_material_calibration_candidate",
        "material_parameters": _material_parameters(params),
        "scene_calibration": _scene_calibration(params, 512, 384),
        "scoring": {
            "weighted_score": None,
            "per_metric_scores": {},
            "per_reference_similarity": [],
        },
        "params": params,
        "sampled_material_parameters": params,
        "material_json_path": None,
        "render_path": None,
        "metadata_path": None,
        "render_status": "skipped",
        "score": None,
        "mean_weighted_score": None,
        "per_metric_scores": {},
        "reference_images_used": [str(p) for p in reference_images],
        "per_reference_similarity": [],
        "status": "skipped",
        "failure_reason": reason,
        "rank": None,
    }


def _failed_candidate(candidate_id, params, reference_images, render_path, reason, material_json_path=None, metadata_path=None, render_status=None):
    return {
        "candidate_id": candidate_id,
        "schema_version": "0.2",
        "calibration_type": "visual_material_calibration_candidate",
        "material_parameters": _material_parameters(params),
        "scene_calibration": _scene_calibration(params, 512, 384),
        "scoring": {
            "weighted_score": None,
            "per_metric_scores": {},
            "per_reference_similarity": [],
        },
        "params": params,
        "sampled_material_parameters": params,
        "material_json_path": str(material_json_path) if material_json_path else None,
        "render_path": str(render_path) if render_path else None,
        "metadata_path": str(metadata_path) if metadata_path else None,
        "render_status": render_status or "failed",
        "score": None,
        "mean_weighted_score": None,
        "per_metric_scores": {},
        "reference_images_used": [str(p) for p in reference_images],
        "per_reference_similarity": [],
        "status": "failed",
        "failure_reason": reason,
        "rank": None,
    }


def _build_best_material_export(best, blend_file, reference_images, scoring, score_profile, roi_mode, resize, roi_box, roi_mask, created_at, warnings):
    if best is None:
        return {
            "schema_version": "0.2",
            "calibration_type": "visual_material_calibration",
            "created_at": created_at,
            "status": "failed",
            "blend_file": str(blend_file),
            "reference_images": [str(p) for p in reference_images],
            "notes": ["No successful candidate was scored."] + warnings,
        }
    return {
        "schema_version": "0.2",
        "calibration_type": "visual_material_calibration",
        "created_at": created_at,
        "status": "success",
        "blend_file": str(blend_file),
        "reference_images": [str(p) for p in reference_images],
        "best_candidate_id": best["candidate_id"],
        "best_candidate_rank": best["rank"],
        "material_parameters": best["material_parameters"],
        "scene_calibration": best["scene_calibration"],
        "scoring": {
            "metric_backend": "mock" if scoring == "mock" else "pillow_baseline",
            "score_profile": score_profile,
            "roi_mode": roi_mode,
            "roi_box": list(roi_box) if roi_box else None,
            "roi_mask": str(roi_mask) if roi_mask else None,
            "reference_mask_pixel_count": best.get("scoring", {}).get("reference_mask_pixel_count"),
            "candidate_mask_pixel_count": best.get("scoring", {}).get("candidate_mask_pixel_count"),
            "comparison_mask_pixel_count": best.get("scoring", {}).get("comparison_mask_pixel_count"),
            "resize": int(resize),
            "weighted_score": best["score"],
            "components": best.get("components", best.get("per_metric_scores", {})),
            "per_metric_scores": best.get("per_metric_scores", {}),
            "weights": _weights_for_profile(score_profile),
        },
        "best_score": best["score"],
        "metric_backend": "mock" if scoring == "mock" else "pillow_baseline",
        "score_profile": score_profile,
        "scoring_mode": scoring,
        "roi_mode": roi_mode,
        "resize": resize,
        "render_path": best.get("render_path"),
        "per_metric_scores": best.get("per_metric_scores", {}),
        "notes": warnings + _best_material_notes(scoring, best),
    }


def _material_parameters(params):
    material = dict(DEFAULT_MATERIAL_PARAMETERS)
    for key in MATERIAL_KEYS:
        if key in params:
            material[key] = params[key]
    if "specular_ior_level" not in material and "specular" in material:
        material["specular_ior_level"] = material["specular"]
    if "translucency" not in material and "subsurface" in material:
        material["translucency"] = material["subsurface"]
    return material


def _scene_calibration(params, render_width, render_height):
    scene = dict(DEFAULT_SCENE_CALIBRATION)
    for key in SCENE_KEYS:
        if key in params:
            scene[key] = params[key]
    scene["render_resolution"] = [int(render_width), int(render_height)]
    return scene


def _best_material_notes(scoring, best):
    if scoring == "mock":
        return ["Mock scoring is for quick flow tests only."]
    if best.get("metadata_path"):
        return ["Candidate was rendered automatically by render_candidate.py."]
    return ["Candidate rendering was not used; real scoring used --candidate-dir."]


def _metric_names_for_profile(score_profile):
    if score_profile == "plastic_material":
        return [
            "brightness_similarity",
            "color_similarity",
            "local_contrast_similarity",
            "highlight_similarity",
            "texture_similarity",
            "ssim_similarity",
        ]
    return ["brightness", "color_histogram", "ssim", "edge_texture", "lpips"]


def _weights_for_profile(score_profile):
    if score_profile == "plastic_material":
        return dict(PLASTIC_MATERIAL_WEIGHTS)
    return dict(DEFAULT_WEIGHTS)


def _extract_mask_metadata(per_reference):
    for item in per_reference:
        preprocessing = item.get("preprocessing", {})
        if preprocessing.get("roi_mode") == "mask":
            return {
                "reference_mask_pixel_count": preprocessing.get("reference_mask_pixel_count"),
                "candidate_mask_pixel_count": preprocessing.get("candidate_mask_pixel_count"),
                "comparison_mask_pixel_count": preprocessing.get("comparison_mask_pixel_count"),
            }
    return {
        "reference_mask_pixel_count": None,
        "candidate_mask_pixel_count": None,
        "comparison_mask_pixel_count": None,
    }


def _candidate_material_path(output_dir, index):
    return output_dir / "candidate_materials" / "candidate_{0:06d}.json".format(index)


def _candidate_render_path(output_dir, index):
    return output_dir / "candidate_renders" / "candidate_{0:06d}.png".format(index)


def _candidate_metadata_path(output_dir, index):
    return output_dir / "candidate_metadata" / "candidate_{0:06d}.json".format(index)


def _read_render_status(metadata_path):
    if metadata_path is None or not metadata_path.exists():
        return "missing_metadata"
    try:
        with metadata_path.open("r", encoding="utf-8") as f:
            metadata = json.load(f)
        return metadata.get("status", "unknown")
    except Exception:
        return "metadata_unreadable"
