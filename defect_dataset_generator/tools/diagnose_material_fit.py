import argparse
import csv
import json
from pathlib import Path
from statistics import mean, pstdev

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps, ImageStat


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parent
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp"}
COMPONENT_KEYS = [
    "brightness_similarity",
    "color_similarity",
    "local_contrast_similarity",
    "highlight_similarity",
    "texture_similarity",
    "ssim_similarity",
]


def main():
    parser = argparse.ArgumentParser(description="Diagnose material fitting drift and prepare a v2 search-space report.")
    parser.add_argument("--real-reference", default="examples/my_project/QC71336_white_real_manual_labels_v2/images/all/9K9A0685.JPG")
    parser.add_argument("--roi-mask", default="outputs/fitting/roi_masks/qc71336_9K9A0685_clean_plastic_rect_mask.png")
    parser.add_argument("--fitting-dir", default="outputs/fitting/fit_plastic_mask_roi_20_v2")
    parser.add_argument("--evaluation-summary", default="outputs/evaluation/black_spot_image_quality_ablation/image_quality_summary.json")
    parser.add_argument("--paired-csv", default="outputs/evaluation/black_spot_image_quality_ablation/paired_default_fitted_diagnosis.csv")
    parser.add_argument("--search-space", default="config/material_search_space_v2_qc71336_white.json")
    parser.add_argument("--out", default="outputs/fitting/material_fit_v2_diagnostic")
    args = parser.parse_args()

    real_reference = resolve_path(args.real_reference)
    roi_mask = resolve_path(args.roi_mask)
    fitting_dir = resolve_path(args.fitting_dir)
    evaluation_summary_path = resolve_path(args.evaluation_summary)
    paired_csv_path = resolve_path(args.paired_csv)
    search_space_path = resolve_path(args.search_space)
    out_dir = resolve_path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    best_material = read_json(fitting_dir / "best_material.json")
    evaluation_summary = read_json(evaluation_summary_path)
    fitting_report = read_json(fitting_dir / "material_fitting_report.json")
    search_space = read_json(search_space_path)
    paired_rows = read_csv(paired_csv_path)

    default_dataset = Path(evaluation_summary["inputs"]["default_dataset"])
    fitted_dataset = Path(evaluation_summary["inputs"]["fitted_dataset"])

    real_stats = compute_real_roi_stats(real_reference, roi_mask)
    default_stats = compute_dataset_clean_material_stats(default_dataset, roi_mask)
    fitted_stats = compute_dataset_clean_material_stats(fitted_dataset, roi_mask)
    drift = compute_channel_drift(real_stats, default_stats, fitted_stats)

    summary = {
        "schema_version": "0.1",
        "diagnostic_type": "material_fit_v2_search_space_diagnostic",
        "inputs": {
            "real_reference": str(real_reference),
            "roi_mask": str(roi_mask),
            "fitting_dir": str(fitting_dir),
            "evaluation_summary": str(evaluation_summary_path),
            "paired_csv": str(paired_csv_path),
            "search_space": str(search_space_path),
        },
        "current_best_material": extract_current_material(best_material),
        "roi_statistics": {
            "real_reference": real_stats,
            "default_synthetic_clean_material": default_stats,
            "fitted_synthetic_clean_material": fitted_stats,
            "channel_drift": drift,
        },
        "score_diagnosis": extract_score_diagnosis(evaluation_summary),
        "top_5_candidates": extract_top_candidates(fitting_report),
        "paired_score_delta_summary": summarize_paired_rows(paired_rows),
        "proposed_search_space": {
            "path": str(search_space_path),
            "profile_name": search_space.get("profile_name"),
            "purpose": search_space.get("purpose"),
            "material_parameters": search_space.get("material_parameters"),
            "scene_calibration": search_space.get("scene_calibration"),
        },
        "recommended_next_command": recommended_command(search_space_path),
    }
    write_json(out_dir / "fit_v2_diagnostic_summary.json", summary)
    write_report(out_dir / "FIT_V2_DIAGNOSTIC_REPORT.md", summary)
    print(json.dumps({"status": "completed", "out": str(out_dir)}, indent=2, ensure_ascii=False))


def resolve_path(value):
    path = Path(value)
    if path.is_absolute():
        return path
    project_candidate = (PROJECT_ROOT / path).resolve()
    if project_candidate.exists() or str(value).startswith(("outputs", "config")):
        return project_candidate
    return (REPO_ROOT / path).resolve()


def read_json(path):
    if not path.exists():
        raise FileNotFoundError("JSON file not found: {0}".format(path))
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_csv(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def open_rgb(path):
    return ImageOps.exif_transpose(Image.open(path)).convert("RGB")


def open_mask(path):
    return ImageOps.exif_transpose(Image.open(path)).convert("L").point(lambda p: 255 if p > 0 else 0)


def compute_real_roi_stats(real_reference, roi_mask):
    image = open_rgb(real_reference)
    mask = open_mask(roi_mask)
    if mask.size != image.size:
        mask = mask.resize(image.size, Image.NEAREST)
    return masked_rgb_stats(image, mask)


def compute_dataset_clean_material_stats(dataset_dir, roi_mask):
    rgb_dir = dataset_dir / "rgb"
    mask_dir = dataset_dir / "masks"
    rgb_files = sorted([p for p in rgb_dir.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS])
    if not rgb_files:
        raise FileNotFoundError("No RGB images found in {0}".format(rgb_dir))
    sample_stats = []
    for rgb_path in rgb_files:
        image = open_rgb(rgb_path)
        material_mask = open_mask(roi_mask)
        if material_mask.size != image.size:
            material_mask = material_mask.resize(image.size, Image.NEAREST)
        defect_path = mask_dir / (rgb_path.stem + ".png")
        if defect_path.exists():
            defect_mask = open_mask(defect_path)
            if defect_mask.size != image.size:
                defect_mask = defect_mask.resize(image.size, Image.NEAREST)
            exclusion = defect_mask.filter(ImageFilter.MaxFilter(17)).point(lambda p: 255 if p > 0 else 0)
            material_mask = ImageChops.subtract(material_mask, exclusion).point(lambda p: 255 if p > 0 else 0)
        sample_stats.append(masked_rgb_stats(image, material_mask))
    return summarize_rgb_stats(sample_stats)


def masked_rgb_stats(image, mask):
    count = mask_pixel_count(mask)
    if count <= 0:
        raise ValueError("Mask has no positive pixels.")
    rgb_stat = ImageStat.Stat(image, mask)
    gray = ImageOps.grayscale(image)
    gray_stat = ImageStat.Stat(gray, mask)
    return {
        "mean_rgb": [round(v, 6) for v in rgb_stat.mean],
        "brightness_mean": round(gray_stat.mean[0], 6),
        "brightness_std": round(gray_stat.stddev[0], 6),
        "mask_pixel_count": count,
    }


def mask_pixel_count(mask):
    hist = mask.histogram()
    return sum(hist[1:])


def summarize_rgb_stats(stats):
    return {
        "sample_count": len(stats),
        "mean_rgb": [round(mean([item["mean_rgb"][idx] for item in stats]), 6) for idx in range(3)],
        "std_rgb": [round(pstdev([item["mean_rgb"][idx] for item in stats]), 6) for idx in range(3)],
        "brightness_mean": round(mean([item["brightness_mean"] for item in stats]), 6),
        "brightness_std_across_samples": round(pstdev([item["brightness_mean"] for item in stats]), 6),
        "within_roi_brightness_std_mean": round(mean([item["brightness_std"] for item in stats]), 6),
        "mask_pixel_count_mean": round(mean([item["mask_pixel_count"] for item in stats]), 2),
    }


def compute_channel_drift(real_stats, default_stats, fitted_stats):
    channel_names = ["R", "G", "B"]
    real = real_stats["mean_rgb"]
    default = default_stats["mean_rgb"]
    fitted = fitted_stats["mean_rgb"]
    rows = []
    for idx, channel in enumerate(channel_names):
        default_error = default[idx] - real[idx]
        fitted_error = fitted[idx] - real[idx]
        rows.append({
            "channel": channel,
            "real": round(real[idx], 6),
            "default": round(default[idx], 6),
            "fitted": round(fitted[idx], 6),
            "default_minus_real": round(default_error, 6),
            "fitted_minus_real": round(fitted_error, 6),
            "fitted_minus_default": round(fitted[idx] - default[idx], 6),
            "absolute_error_change": round(abs(fitted_error) - abs(default_error), 6),
        })
    worst = max(rows, key=lambda item: item["absolute_error_change"])
    return {
        "channels": rows,
        "largest_fitted_error_increase_channel": worst["channel"],
        "diagnostic_text": (
            "Largest fitted-vs-default absolute color error increase is in channel {0} "
            "(change {1})."
        ).format(worst["channel"], worst["absolute_error_change"]),
    }


def extract_current_material(best_material):
    return {
        "base_color": best_material.get("material_parameters", {}).get("base_color"),
        "roughness": best_material.get("material_parameters", {}).get("roughness"),
        "specular": best_material.get("material_parameters", {}).get("specular"),
        "noise_scale": best_material.get("material_parameters", {}).get("noise_scale"),
        "noise_strength": best_material.get("material_parameters", {}).get("noise_strength"),
        "bump_strength": best_material.get("material_parameters", {}).get("bump_strength"),
        "scene_calibration": best_material.get("scene_calibration", {}),
        "scoring": best_material.get("scoring", {}),
    }


def extract_score_diagnosis(summary):
    original = summary["real_reference_similarity"]
    excluded = summary.get("defect_excluded_similarity", {})
    return {
        "original_default_weighted_score": original["default_material"]["weighted_score"]["mean"],
        "original_fitted_weighted_score": original["fitted_material"]["weighted_score"]["mean"],
        "original_component_diagnosis": original.get("component_diagnosis", {}).get("diagnostic_text"),
        "defect_excluded_default_weighted_score": excluded.get("default_material", {}).get("scores", {}).get("weighted_score", {}).get("mean"),
        "defect_excluded_fitted_weighted_score": excluded.get("fitted_material", {}).get("scores", {}).get("weighted_score", {}).get("mean"),
        "defect_excluded_component_diagnosis": excluded.get("component_diagnosis", {}).get("diagnostic_text"),
    }


def extract_top_candidates(fitting_report):
    candidates = []
    for item in fitting_report.get("top_5_candidates", []):
        scoring = item.get("scoring", {})
        components = scoring.get("components") or item.get("components") or item.get("per_metric_scores", {})
        candidates.append({
            "candidate_id": item.get("candidate_id"),
            "score": item.get("mean_weighted_score") or item.get("score") or scoring.get("weighted_score"),
            "components": {key: components.get(key) for key in COMPONENT_KEYS},
            "material_parameters": item.get("material_parameters", {}),
            "scene_calibration": item.get("scene_calibration", {}),
        })
    return candidates


def summarize_paired_rows(rows):
    def values(key):
        cleaned = []
        for row in rows:
            try:
                cleaned.append(float(row[key]))
            except Exception:
                pass
        return cleaned

    return {
        "row_count": len(rows),
        "fitted_minus_default_mean": summarize(values("fitted_minus_default")),
        "fitted_minus_default_defect_excluded_mean": summarize(values("fitted_minus_default_defect_excluded")),
        "visibility_delta_mean": summarize(values("visibility_delta")),
    }


def summarize(values):
    if not values:
        return None
    return {
        "mean": round(mean(values), 6),
        "std": round(pstdev(values), 6) if len(values) > 1 else 0.0,
        "min": round(min(values), 6),
        "max": round(max(values), 6),
    }


def recommended_command(search_space_path):
    rel_search = search_space_path
    try:
        rel_search = search_space_path.relative_to(PROJECT_ROOT)
    except Exception:
        pass
    return (
        "python app.py fit-material ^\n"
        "  --real examples\\my_project\\QC71336_white_real_manual_labels_v2\\images\\all\\9K9A0685.JPG ^\n"
        "  --blend assets\\models\\QC7-1336-white.blend ^\n"
        "  --out outputs\\fitting\\fit_plastic_mask_roi_v2_qc71336 ^\n"
        "  --candidates 50 ^\n"
        "  --scoring real ^\n"
        "  --render-candidates ^\n"
        "  --roi mask ^\n"
        "  --roi-mask outputs\\fitting\\roi_masks\\qc71336_9K9A0685_clean_plastic_rect_mask.png ^\n"
        "  --resize 512 ^\n"
        "  --samples 16 ^\n"
        "  --seed 300 ^\n"
        "  --material-profile opaque_white_plastic ^\n"
        "  --render-width 512 ^\n"
        "  --render-height 384 ^\n"
        "  --score-profile plastic_material ^\n"
        "  --material-search-space {0}"
    ).format(str(rel_search))


def write_report(path, summary):
    best = summary["current_best_material"]
    roi = summary["roi_statistics"]
    score = summary["score_diagnosis"]
    lines = [
        "# Fit V2 Diagnostic Report",
        "",
        "## Current Problem",
        "",
        "The fitted material from `fit_plastic_mask_roi_20_v2` did not improve the selected image-level material similarity metric. The loss remains after black_spot pixels are excluded, so the issue is more likely brightness/color drift than defect contamination.",
        "",
        "## Why Fitted Lost To Default",
        "",
        "- Original plastic_material score: default `{0}`, fitted `{1}`.".format(score["original_default_weighted_score"], score["original_fitted_weighted_score"]),
        "- Defect-excluded plastic_material score: default `{0}`, fitted `{1}`.".format(score["defect_excluded_default_weighted_score"], score["defect_excluded_fitted_weighted_score"]),
        "- Original component diagnosis: {0}".format(score["original_component_diagnosis"]),
        "- Defect-excluded component diagnosis: {0}".format(score["defect_excluded_component_diagnosis"]),
        "",
        "## ROI Mean RGB Diagnosis",
        "",
        "| Source | Mean R | Mean G | Mean B | Brightness mean |",
        "| --- | ---: | ---: | ---: | ---: |",
        "| Real reference ROI | {0} | {1} | {2} | {3} |".format(*roi["real_reference"]["mean_rgb"], roi["real_reference"]["brightness_mean"]),
        "| Default synthetic clean ROI | {0} | {1} | {2} | {3} |".format(*roi["default_synthetic_clean_material"]["mean_rgb"], roi["default_synthetic_clean_material"]["brightness_mean"]),
        "| Fitted synthetic clean ROI | {0} | {1} | {2} | {3} |".format(*roi["fitted_synthetic_clean_material"]["mean_rgb"], roi["fitted_synthetic_clean_material"]["brightness_mean"]),
        "",
        "Channel drift: {0}".format(roi["channel_drift"]["diagnostic_text"]),
        "",
        "| Channel | Real | Default | Fitted | Default-real | Fitted-real | Fitted-default | Abs error change |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in roi["channel_drift"]["channels"]:
        lines.append(
            "| {channel} | {real} | {default} | {fitted} | {default_minus_real} | {fitted_minus_real} | {fitted_minus_default} | {absolute_error_change} |".format(**row)
        )
    lines.extend([
        "",
        "## Current Best Material Parameters",
        "",
        "```json",
        json.dumps(best, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Current Top 5 Candidates",
        "",
        top_candidate_table(summary["top_5_candidates"]),
        "",
        "## Proposed Search Space V2",
        "",
        "- File: `{0}`".format(summary["proposed_search_space"]["path"]),
        "- Purpose: {0}".format(summary["proposed_search_space"]["purpose"]),
        "- Material parameters are stored under `material_parameters`.",
        "- Light strength, exposure, background color, camera profile, and render resolution are stored under `scene_calibration`.",
        "",
        "## Recommended Next Fit Command",
        "",
        "```powershell",
        summary["recommended_next_command"],
        "```",
        "",
        "## Limitations",
        "",
        "- This is visual material calibration, not physical material recovery.",
        "- The diagnosis uses one selected real reference image and one clean plastic ROI mask.",
        "- The proposed search space narrows color and brightness drift; it does not prove downstream detector improvement.",
        "- YOLO should not be used again as the immediate image-quality tuning metric.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def top_candidate_table(candidates):
    lines = [
        "| Candidate | Score | Brightness | Color | Local contrast | Highlight | Texture | SSIM | Material parameters | Scene calibration |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for item in candidates:
        components = item["components"]
        lines.append(
            "| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} | `{8}` | `{9}` |".format(
                item["candidate_id"],
                item["score"],
                components.get("brightness_similarity"),
                components.get("color_similarity"),
                components.get("local_contrast_similarity"),
                components.get("highlight_similarity"),
                components.get("texture_similarity"),
                components.get("ssim_similarity"),
                compact_json(item["material_parameters"]),
                compact_json(item["scene_calibration"]),
            )
        )
    return "\n".join(lines)


def compact_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main()
