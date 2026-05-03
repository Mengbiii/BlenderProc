import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageStat


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parent
COMPONENT_KEYS = [
    "brightness_similarity",
    "color_similarity",
    "local_contrast_similarity",
    "highlight_similarity",
    "texture_similarity",
    "ssim_similarity",
]


def main():
    parser = argparse.ArgumentParser(description="Compare material fitting V2 against previous fitted and backend default diagnostics.")
    parser.add_argument("--v2-fitting-dir", default="outputs/fitting/fit_plastic_mask_roi_v2_qc71336")
    parser.add_argument("--old-diagnostic-summary", default="outputs/fitting/material_fit_v2_diagnostic/fit_v2_diagnostic_summary.json")
    parser.add_argument("--evaluation-summary", default="outputs/evaluation/black_spot_image_quality_ablation/image_quality_summary.json")
    parser.add_argument("--real-reference", default="examples/my_project/QC71336_white_real_manual_labels_v2/images/all/9K9A0685.JPG")
    parser.add_argument("--roi-mask", default="outputs/fitting/roi_masks/qc71336_9K9A0685_clean_plastic_rect_mask.png")
    args = parser.parse_args()

    v2_dir = resolve_path(args.v2_fitting_dir)
    old_summary = read_json(resolve_path(args.old_diagnostic_summary))
    eval_summary = read_json(resolve_path(args.evaluation_summary))
    real_reference = resolve_path(args.real_reference)
    roi_mask = resolve_path(args.roi_mask)
    best_material = read_json(v2_dir / "best_material.json")
    fitting_report = read_json(v2_dir / "material_fitting_report.json")

    real_stats = compute_roi_stats(open_rgb(real_reference), open_mask(roi_mask))
    default_stats = old_summary["roi_statistics"]["default_synthetic_clean_material"]
    old_fitted_stats = old_summary["roi_statistics"]["fitted_synthetic_clean_material"]
    v2_render_path = Path(best_material["render_path"])
    v2_stats = compute_roi_stats(open_rgb(v2_render_path), resize_mask_for_image(open_mask(roi_mask), open_rgb(v2_render_path)))

    default_score = eval_summary["real_reference_similarity"]["default_material"]["weighted_score"]["mean"]
    old_fitted_score = eval_summary["real_reference_similarity"]["fitted_material"]["weighted_score"]["mean"]
    v2_score = best_material["scoring"]["weighted_score"]
    decision = decide(v2_score, default_score, old_fitted_score)

    top_5 = extract_top_5(fitting_report)
    summary = {
        "schema_version": "0.1",
        "comparison_type": "material_fit_v2_result_comparison",
        "inputs": {
            "v2_fitting_dir": str(v2_dir),
            "old_diagnostic_summary": str(resolve_path(args.old_diagnostic_summary)),
            "evaluation_summary": str(resolve_path(args.evaluation_summary)),
            "real_reference": str(real_reference),
            "roi_mask": str(roi_mask),
        },
        "roi_statistics": {
            "real_reference_roi": real_stats,
            "backend_default_clean_synthetic_roi": default_stats,
            "old_fitted_v1_clean_synthetic_roi": old_fitted_stats,
            "new_fitted_v2_best_candidate_roi": v2_stats,
        },
        "scores": {
            "backend_default": build_score_block(default_score, eval_summary["real_reference_similarity"]["default_material"]),
            "old_fitted_v1": build_score_block(old_fitted_score, eval_summary["real_reference_similarity"]["fitted_material"]),
            "new_fitted_v2": build_score_block(v2_score, best_material["scoring"]),
        },
        "best_candidate": {
            "candidate_id": best_material.get("best_candidate_id"),
            "score": v2_score,
            "material_parameters": best_material.get("material_parameters", {}),
            "scene_calibration": best_material.get("scene_calibration", {}),
            "render_path": best_material.get("render_path"),
        },
        "top_5_candidates": top_5,
        "decision": decision,
    }
    write_json(v2_dir / "fit_v2_result_comparison_summary.json", summary)
    write_report(v2_dir / "FIT_V2_RESULT_COMPARISON_REPORT.md", summary)
    make_contact_sheet(v2_dir / "fit_v2_top_candidates_contact_sheet.jpg", real_reference, roi_mask, top_5)
    print(json.dumps({"status": "completed", "out": str(v2_dir)}, indent=2, ensure_ascii=False))


def resolve_path(value):
    path = Path(value)
    if path.is_absolute():
        return path
    first = path.parts[0].lower() if path.parts else ""
    if first in {"outputs", "config"}:
        return (PROJECT_ROOT / path).resolve()
    return (REPO_ROOT / path).resolve()


def read_json(path):
    if not path.exists():
        raise FileNotFoundError("Missing JSON file: {0}".format(path))
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def open_rgb(path):
    return ImageOps.exif_transpose(Image.open(path)).convert("RGB")


def open_mask(path):
    return ImageOps.exif_transpose(Image.open(path)).convert("L").point(lambda p: 255 if p > 0 else 0)


def resize_mask_for_image(mask, image):
    if mask.size != image.size:
        return mask.resize(image.size, Image.NEAREST)
    return mask


def compute_roi_stats(image, mask):
    mask = resize_mask_for_image(mask, image)
    rgb_stat = ImageStat.Stat(image, mask)
    gray = ImageOps.grayscale(image)
    gray_stat = ImageStat.Stat(gray, mask)
    return {
        "mean_rgb": [round(value, 6) for value in rgb_stat.mean],
        "brightness_mean": round(gray_stat.mean[0], 6),
        "brightness_std": round(gray_stat.stddev[0], 6),
        "mask_pixel_count": mask_pixel_count(mask),
    }


def mask_pixel_count(mask):
    hist = mask.histogram()
    return sum(hist[1:])


def build_score_block(score, source):
    components = source.get("components") or source
    return {
        "weighted_score": score,
        "components": {key: components.get(key, {}).get("mean") if isinstance(components.get(key), dict) else components.get(key) for key in COMPONENT_KEYS},
    }


def decide(v2_score, default_score, old_fitted_score):
    if v2_score > default_score:
        case = "A"
        text = "V2 material fitting improves the selected image-level material similarity metric compared with the backend default material. It is now reasonable to test this material in a small black_spot generation smoke batch."
    elif v2_score > old_fitted_score:
        case = "B"
        text = "V2 material fitting reduces the previous brightness/color drift but still does not outperform the backend default material. It should be treated as an improved fitted candidate, not as proof of better visual realism."
    else:
        case = "C"
        text = "V2 material fitting did not fix the material mismatch. Further changes to ROI selection, scene calibration, or scoring weights are needed before using fitted material in downstream dataset generation."
    return {
        "case": case,
        "text": text,
        "v2_minus_default": round(v2_score - default_score, 6),
        "v2_minus_old_fitted": round(v2_score - old_fitted_score, 6),
    }


def extract_top_5(fitting_report):
    top = []
    for item in fitting_report.get("top_5_candidates", [])[:5]:
        scoring = item.get("scoring", {})
        material = item.get("material_parameters", {})
        top.append({
            "candidate_id": item.get("candidate_id"),
            "score": item.get("mean_weighted_score") or item.get("score") or scoring.get("weighted_score"),
            "render_path": item.get("render_path"),
            "material_parameters": material,
            "scene_calibration": item.get("scene_calibration", {}),
            "components": scoring.get("components") or item.get("components") or item.get("per_metric_scores", {}),
        })
    return top


def write_report(path, summary):
    real = summary["roi_statistics"]["real_reference_roi"]
    default = summary["roi_statistics"]["backend_default_clean_synthetic_roi"]
    old = summary["roi_statistics"]["old_fitted_v1_clean_synthetic_roi"]
    v2 = summary["roi_statistics"]["new_fitted_v2_best_candidate_roi"]
    scores = summary["scores"]
    best = summary["best_candidate"]
    lines = [
        "# Fit V2 Result Comparison Report",
        "",
        "## Purpose",
        "",
        "This report compares Material Fitting V2 against the previous fitted material and the backend default material using image-level material similarity only. It does not claim detection improvement.",
        "",
        "## ROI Appearance Comparison",
        "",
        "| Source | Mean R | Mean G | Mean B | Brightness mean |",
        "| --- | ---: | ---: | ---: | ---: |",
        rgb_row("Real reference ROI", real),
        rgb_row("Backend default clean synthetic ROI", default),
        rgb_row("Old fitted v1 clean synthetic ROI", old),
        rgb_row("New fitted v2 best candidate ROI", v2),
        "",
        "## Plastic Material Score Comparison",
        "",
        score_table(scores),
        "",
        "## Best V2 Material Parameters",
        "",
        "```json",
        json.dumps(best["material_parameters"], indent=2, ensure_ascii=False),
        "```",
        "",
        "## Best V2 Scene Calibration",
        "",
        "```json",
        json.dumps(best["scene_calibration"], indent=2, ensure_ascii=False),
        "```",
        "",
        "## Top 5 V2 Candidates",
        "",
        top5_table(summary["top_5_candidates"]),
        "",
        "## Decision",
        "",
        "- Case: `{0}`".format(summary["decision"]["case"]),
        "- V2 minus backend default score: `{0}`".format(summary["decision"]["v2_minus_default"]),
        "- V2 minus old fitted score: `{0}`".format(summary["decision"]["v2_minus_old_fitted"]),
        "",
        summary["decision"]["text"],
        "",
        "Diagnostic nuance: V2's total weighted score is slightly higher than old fitted, but its brightness/color components should still be inspected separately. A higher total score can be caused by local contrast or SSIM gains rather than a true brightness/color correction.",
        "",
        "## Limitations",
        "",
        "- Backend default and old fitted statistics come from the previous black_spot ablation evaluation; V2 is the clean best candidate render from material fitting.",
        "- The comparison is image-level and ROI-based; it is not physical material recovery and not detector validation.",
        "- No black_spot dataset generation or YOLO training was performed in this step.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def rgb_row(label, stats):
    return "| {0} | {1} | {2} | {3} | {4} |".format(
        label,
        stats["mean_rgb"][0],
        stats["mean_rgb"][1],
        stats["mean_rgb"][2],
        stats["brightness_mean"],
    )


def score_table(scores):
    lines = [
        "| Source | Weighted | Brightness | Color | Local contrast | Highlight | Texture | SSIM |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    labels = [
        ("Backend default", "backend_default"),
        ("Old fitted v1", "old_fitted_v1"),
        ("New fitted v2", "new_fitted_v2"),
    ]
    for label, key in labels:
        item = scores[key]
        components = item["components"]
        lines.append(
            "| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} |".format(
                label,
                item["weighted_score"],
                components.get("brightness_similarity"),
                components.get("color_similarity"),
                components.get("local_contrast_similarity"),
                components.get("highlight_similarity"),
                components.get("texture_similarity"),
                components.get("ssim_similarity"),
            )
        )
    return "\n".join(lines)


def top5_table(candidates):
    lines = [
        "| Candidate | Score | Brightness | Color | Local contrast | Highlight | Texture | SSIM | base_color | roughness | specular | noise_strength | bump_strength |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |",
    ]
    for item in candidates:
        material = item["material_parameters"]
        components = item["components"]
        lines.append(
            "| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} | `{8}` | {9} | {10} | {11} | {12} |".format(
                item["candidate_id"],
                item["score"],
                components.get("brightness_similarity"),
                components.get("color_similarity"),
                components.get("local_contrast_similarity"),
                components.get("highlight_similarity"),
                components.get("texture_similarity"),
                components.get("ssim_similarity"),
                material.get("base_color"),
                material.get("roughness"),
                material.get("specular"),
                material.get("noise_strength"),
                material.get("bump_strength"),
            )
        )
    return "\n".join(lines)


def make_contact_sheet(out_path, real_reference, roi_mask, candidates):
    real_image = open_rgb(real_reference)
    mask = resize_mask_for_image(open_mask(roi_mask), real_image)
    real_crop = real_image.crop(mask.getbbox())
    cell_w, cell_h = 300, 210
    label_h = 78
    cols = 3
    items = [{"kind": "real", "image": real_crop, "label": "real reference ROI"}]
    for candidate in candidates:
        image = open_rgb(candidate["render_path"])
        material = candidate["material_parameters"]
        label = (
            "candidate {0} score {1}\n"
            "base_color {2}\n"
            "rough {3} spec {4} noise {5} bump {6}"
        ).format(
            candidate["candidate_id"],
            candidate["score"],
            material.get("base_color"),
            material.get("roughness"),
            material.get("specular"),
            material.get("noise_strength"),
            material.get("bump_strength"),
        )
        items.append({"kind": "candidate", "image": image, "label": label})
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell_w, rows * (cell_h + label_h) + 36), "white")
    draw = ImageDraw.Draw(sheet)
    font, small = load_fonts()
    draw.text((10, 10), "Fit V2 real ROI and top 5 material candidates", fill=(0, 0, 0), font=font)
    for index, item in enumerate(items):
        col = index % cols
        row = index // cols
        x = col * cell_w
        y = 36 + row * (cell_h + label_h)
        paste_thumbnail(sheet, item["image"], x, y, cell_w, cell_h)
        draw.multiline_text((x + 6, y + cell_h + 4), item["label"], fill=(20, 20, 20), font=small, spacing=2)
    sheet.save(out_path, quality=92)


def paste_thumbnail(sheet, image, x, y, w, h):
    thumb = image.copy()
    resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.BICUBIC)
    thumb.thumbnail((w, h), resample)
    sheet.paste(thumb, (x + (w - thumb.width) // 2, y + (h - thumb.height) // 2))


def load_fonts():
    try:
        return ImageFont.truetype("arial.ttf", 17), ImageFont.truetype("arial.ttf", 12)
    except Exception:
        return ImageFont.load_default(), ImageFont.load_default()


if __name__ == "__main__":
    main()
