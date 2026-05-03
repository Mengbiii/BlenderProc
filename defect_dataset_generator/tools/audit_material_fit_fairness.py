import argparse
import json
import subprocess
import sys
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

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.similarity_metrics import compare_images  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Audit fitted materials under the same clean render and scoring conditions.")
    parser.add_argument("--real-reference", required=True)
    parser.add_argument("--roi-mask", required=True)
    parser.add_argument("--old-fitted", required=True)
    parser.add_argument("--v2-fitted", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--blend", default="assets/models/QC7-1336-white.blend")
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=384)
    parser.add_argument("--samples", type=int, default=16)
    args = parser.parse_args()

    real_reference = resolve_path(args.real_reference)
    roi_mask = resolve_path(args.roi_mask)
    old_fitted = resolve_path(args.old_fitted)
    v2_fitted = resolve_path(args.v2_fitted)
    out_dir = resolve_path(args.out)
    blend = resolve_path(args.blend)
    out_dir.mkdir(parents=True, exist_ok=True)

    for label, path in [
        ("real reference", real_reference),
        ("roi mask", roi_mask),
        ("old fitted material", old_fitted),
        ("v2 fitted material", v2_fitted),
        ("blend file", blend),
    ]:
        if not path.exists():
            raise FileNotFoundError("{0} not found: {1}".format(label, path))

    material_dir = out_dir / "materials"
    render_dir = out_dir / "renders"
    metadata_dir = out_dir / "metadata"
    log_dir = out_dir / "logs"
    for directory in [material_dir, render_dir, metadata_dir, log_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    conditions = [
        {
            "name": "backend_default",
            "label": "Backend default approximate",
            "material_json": material_dir / "backend_default_approx_material.json",
            "source_note": "Approximate default baseline based on render_candidate.py fallback material and scene defaults.",
            "payload": default_material_payload(args.width, args.height),
        },
        {
            "name": "old_fitted_v1",
            "label": "Old fitted v1",
            "material_json": material_dir / "old_fitted_v1_material.json",
            "source_note": "Copied from previous best_material.json and rendered under the same clean candidate renderer.",
            "payload": normalize_material_payload(read_json(old_fitted), "old_fitted_v1", args.width, args.height),
        },
        {
            "name": "new_fitted_v2",
            "label": "New fitted v2",
            "material_json": material_dir / "new_fitted_v2_material.json",
            "source_note": "Copied from V2 best_material.json and rendered under the same clean candidate renderer.",
            "payload": normalize_material_payload(read_json(v2_fitted), "new_fitted_v2", args.width, args.height),
        },
    ]

    for condition in conditions:
        write_json(condition["material_json"], condition["payload"])
        condition["render_path"] = render_dir / (condition["name"] + "_clean.png")
        condition["metadata_path"] = metadata_dir / (condition["name"] + "_clean_metadata.json")
        condition["render_log"] = log_dir / (condition["name"] + "_render_log.txt")
        render_condition(condition, blend, args.width, args.height, args.samples)
        condition.update(score_condition(condition, real_reference, roi_mask))

    real_stats = compute_roi_stats(open_rgb(real_reference), open_mask(roi_mask))
    default_result = next(item for item in conditions if item["name"] == "backend_default")
    for condition in conditions:
        condition["acceptance"] = acceptance(condition, default_result)

    summary = {
        "schema_version": "0.1",
        "audit_type": "material_fit_fairness_audit",
        "inputs": {
            "real_reference": str(real_reference),
            "roi_mask": str(roi_mask),
            "old_fitted": str(old_fitted),
            "v2_fitted": str(v2_fitted),
            "blend": str(blend),
            "width": args.width,
            "height": args.height,
            "samples": args.samples,
        },
        "outputs": {
            "summary_json": str(out_dir / "material_fit_fairness_summary.json"),
            "report": str(out_dir / "MATERIAL_FIT_FAIRNESS_AUDIT_REPORT.md"),
            "contact_sheet": str(out_dir / "material_fit_fairness_contact_sheet.jpg"),
        },
        "real_reference_roi": real_stats,
        "conditions": conditions_for_json(conditions),
        "best_condition": best_condition(conditions),
        "acceptance_rule": [
            "weighted_score > backend_default_score",
            "brightness_similarity >= backend_default_brightness_similarity",
            "color_similarity >= backend_default_color_similarity",
            "RGB mean absolute error <= backend_default RGB mean absolute error",
        ],
        "roi_caution": "ROI quality strongly affects this material-only score. Earlier broad ROIs may include logo/text, part edges, printed markings, and shadows. Use the cleanest available flat plastic ROI and keep reporting ROI sensitivity.",
    }
    write_json(out_dir / "material_fit_fairness_summary.json", summary)
    write_report(out_dir / "MATERIAL_FIT_FAIRNESS_AUDIT_REPORT.md", summary)
    make_contact_sheet(out_dir / "material_fit_fairness_contact_sheet.jpg", real_reference, roi_mask, conditions)
    print(json.dumps({"status": "completed", "out": str(out_dir)}, indent=2, ensure_ascii=False))


def resolve_path(value):
    path = Path(value)
    if path.is_absolute():
        return path
    first = path.parts[0].lower() if path.parts else ""
    if first in {"outputs", "config"}:
        return (PROJECT_ROOT / path).resolve()
    return (REPO_ROOT / path).resolve()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def default_material_payload(width, height):
    return {
        "schema_version": "0.2",
        "calibration_type": "fairness_audit_approx_backend_default",
        "material_parameters": {
            "base_color": [0.78, 0.80, 0.82, 1.0],
            "roughness": 0.5,
            "specular": 0.35,
            "subsurface": 0.0,
            "noise_scale": 48.0,
            "noise_strength": 0.0,
            "bump_strength": 0.0,
            "alpha": 1.0,
            "specular_ior_level": 0.35,
            "translucency": 0.0,
        },
        "scene_calibration": {
            "light_strength": 450.0,
            "exposure": 0.0,
            "camera_profile": "deterministic_ortho_front",
            "render_resolution": [width, height],
            "background_color": [0.78, 0.78, 0.78, 1.0],
        },
    }


def normalize_material_payload(source, label, width, height):
    material = dict(source.get("material_parameters", source))
    scene = dict(source.get("scene_calibration", {}))
    scene["camera_profile"] = "deterministic_ortho_front"
    scene["render_resolution"] = [width, height]
    return {
        "schema_version": "0.2",
        "calibration_type": "fairness_audit_" + label,
        "material_parameters": material,
        "scene_calibration": scene,
    }


def render_condition(condition, blend, width, height, samples):
    command = [
        sys.executable,
        str(REPO_ROOT / "cli.py"),
        "run",
        str(PROJECT_ROOT / "blender_scripts" / "render_candidate.py"),
        "--",
        "--blend",
        str(blend),
        "--material-json",
        str(condition["material_json"]),
        "--output",
        str(condition["render_path"]),
        "--metadata",
        str(condition["metadata_path"]),
        "--width",
        str(width),
        "--height",
        str(height),
        "--samples",
        str(samples),
    ]
    completed = subprocess.run(command, cwd=str(REPO_ROOT), universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    condition["command"] = command
    condition["render_returncode"] = completed.returncode
    condition["render_log"].write_text(completed.stdout or "", encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError("Render failed for {0}; see {1}".format(condition["name"], condition["render_log"]))
    if not condition["render_path"].exists():
        raise FileNotFoundError("Render command succeeded but image is missing: {0}".format(condition["render_path"]))


def score_condition(condition, real_reference, roi_mask):
    similarity = compare_images(
        reference_image=real_reference,
        candidate_image=condition["render_path"],
        roi_mode="mask",
        roi_mask=roi_mask,
        resize=512,
        score_profile="plastic_material",
    )
    image = open_rgb(condition["render_path"])
    mask = open_mask(roi_mask)
    if mask.size != image.size:
        mask = mask.resize(image.size, Image.NEAREST)
    stats = compute_roi_stats(image, mask)
    real_stats = compute_roi_stats(open_rgb(real_reference), open_mask(roi_mask))
    error = rgb_error(stats["mean_rgb"], real_stats["mean_rgb"])
    return {
        "score": similarity["weighted_score"],
        "components": similarity["components"],
        "roi_stats": stats,
        "rgb_error_vs_real": error,
    }


def open_rgb(path):
    return ImageOps.exif_transpose(Image.open(path)).convert("RGB")


def open_mask(path):
    return ImageOps.exif_transpose(Image.open(path)).convert("L").point(lambda p: 255 if p > 0 else 0)


def compute_roi_stats(image, mask):
    if mask.size != image.size:
        mask = mask.resize(image.size, Image.NEAREST)
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


def rgb_error(candidate_rgb, real_rgb):
    errors = [candidate_rgb[idx] - real_rgb[idx] for idx in range(3)]
    abs_errors = [abs(value) for value in errors]
    euclidean = sum(value * value for value in errors) ** 0.5
    return {
        "signed_error_rgb": [round(value, 6) for value in errors],
        "absolute_error_rgb": [round(value, 6) for value in abs_errors],
        "mean_absolute_error": round(sum(abs_errors) / 3.0, 6),
        "euclidean_error": round(euclidean, 6),
    }


def acceptance(condition, default_result):
    if condition["name"] == "backend_default":
        return {
            "passes": True,
            "reason": "Baseline condition; fitted acceptance is evaluated relative to this result.",
            "checks": {},
        }
    checks = {
        "weighted_score_gt_default": condition["score"] > default_result["score"],
        "brightness_similarity_ge_default": condition["components"]["brightness_similarity"] >= default_result["components"]["brightness_similarity"],
        "color_similarity_ge_default": condition["components"]["color_similarity"] >= default_result["components"]["color_similarity"],
        "rgb_mae_le_default": condition["rgb_error_vs_real"]["mean_absolute_error"] <= default_result["rgb_error_vs_real"]["mean_absolute_error"],
    }
    return {
        "passes": all(checks.values()),
        "checks": checks,
        "reason": "Passes all fitted-material acceptance checks." if all(checks.values()) else "Fails one or more fitted-material acceptance checks.",
    }


def conditions_for_json(conditions):
    rows = []
    for condition in conditions:
        rows.append({
            "name": condition["name"],
            "label": condition["label"],
            "source_note": condition["source_note"],
            "material_json": str(condition["material_json"]),
            "render_path": str(condition["render_path"]),
            "metadata_path": str(condition["metadata_path"]),
            "render_log": str(condition["render_log"]),
            "render_returncode": condition["render_returncode"],
            "score": condition["score"],
            "components": condition["components"],
            "roi_stats": condition["roi_stats"],
            "rgb_error_vs_real": condition["rgb_error_vs_real"],
            "material_parameters": condition["payload"]["material_parameters"],
            "scene_calibration": condition["payload"]["scene_calibration"],
            "acceptance": condition["acceptance"],
        })
    return rows


def best_condition(conditions):
    best = max(conditions, key=lambda item: item["score"])
    return {
        "name": best["name"],
        "label": best["label"],
        "score": best["score"],
    }


def write_report(path, summary):
    lines = [
        "# Material Fit Fairness Audit Report",
        "",
        "## Purpose",
        "",
        "This audit compares backend default, old fitted v1, and new fitted v2 materials under the same clean renderer, render size, camera profile, ROI mask, and plastic_material scoring profile. It does not run YOLO and does not generate defect datasets.",
        "",
        "## Render Conditions",
        "",
        "- Blend: `{0}`".format(summary["inputs"]["blend"]),
        "- Render size: `{0}x{1}`".format(summary["inputs"]["width"], summary["inputs"]["height"]),
        "- Samples: `{0}`".format(summary["inputs"]["samples"]),
        "- Score profile: `plastic_material`",
        "- ROI mask: `{0}`".format(summary["inputs"]["roi_mask"]),
        "",
        "## ROI Appearance And Score",
        "",
        result_table(summary),
        "",
        "## Acceptance Rule",
        "",
        "A fitted material is accepted only if:",
        "",
        "1. weighted_score > backend_default_score",
        "2. brightness_similarity >= backend_default_brightness_similarity",
        "3. color_similarity >= backend_default_color_similarity",
        "4. RGB mean absolute error <= backend_default RGB mean absolute error",
        "",
        acceptance_table(summary),
        "",
        "## Best Fair Score",
        "",
        "Best fair material score: `{0}` with score `{1}`.".format(summary["best_condition"]["label"], summary["best_condition"]["score"]),
        "",
        "## Baseline Note",
        "",
        "There is no explicit backend default material JSON in the fitting outputs. The backend default condition in this audit is an approximate default baseline using render_candidate.py fallback material and scene values: base_color [0.78, 0.80, 0.82, 1.0], roughness 0.5, specular 0.35, light_strength 450, exposure 0, background [0.78, 0.78, 0.78, 1.0].",
        "",
        "This approximate clean-render baseline is not numerically interchangeable with the earlier backend default score measured from black_spot batch images. Use this audit only for same-renderer clean material comparison.",
        "",
        "## ROI Caution",
        "",
        summary["roi_caution"],
        "",
        "## Limitations",
        "",
        "- This is a visual material fairness audit, not physical BRDF recovery.",
        "- The default baseline is approximate because no explicit backend default material JSON was available.",
        "- ROI quality strongly affects the result; keep reporting ROI sensitivity before final material claims.",
        "",
    ]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def result_table(summary):
    lines = [
        "| Condition | Score | Brightness sim | Color sim | Local contrast | Highlight | Texture | SSIM | Mean RGB | Brightness mean | RGB MAE | RGB Euclidean |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |",
    ]
    real = summary["real_reference_roi"]
    lines.append("| Real reference ROI |  |  |  |  |  |  |  | `{0}` | {1} |  |  |".format(real["mean_rgb"], real["brightness_mean"]))
    for condition in summary["conditions"]:
        comp = condition["components"]
        stats = condition["roi_stats"]
        err = condition["rgb_error_vs_real"]
        lines.append(
            "| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} | `{8}` | {9} | {10} | {11} |".format(
                condition["label"],
                condition["score"],
                comp["brightness_similarity"],
                comp["color_similarity"],
                comp["local_contrast_similarity"],
                comp["highlight_similarity"],
                comp["texture_similarity"],
                comp["ssim_similarity"],
                stats["mean_rgb"],
                stats["brightness_mean"],
                err["mean_absolute_error"],
                err["euclidean_error"],
            )
        )
    return "\n".join(lines)


def acceptance_table(summary):
    lines = ["| Condition | Passes | Reason |", "| --- | --- | --- |"]
    for condition in summary["conditions"]:
        if condition["name"] == "backend_default":
            continue
        lines.append("| {0} | {1} | {2} |".format(condition["label"], condition["acceptance"]["passes"], condition["acceptance"]["reason"]))
    return "\n".join(lines)


def make_contact_sheet(path, real_reference, roi_mask, conditions):
    real_image = open_rgb(real_reference)
    mask = open_mask(roi_mask)
    if mask.size != real_image.size:
        mask = mask.resize(real_image.size, Image.NEAREST)
    real_crop = real_image.crop(mask.getbbox())
    cells = [{"title": "Real reference ROI", "image": real_crop, "label": "mean RGB shown in report"}]
    for condition in conditions:
        stats = condition["roi_stats"]
        label = (
            "{0}\nscore {1}\nmean RGB {2}\nbrightness {3}\naccept {4}"
        ).format(
            condition["label"],
            condition["score"],
            stats["mean_rgb"],
            stats["brightness_mean"],
            condition["acceptance"]["passes"],
        )
        cells.append({"title": condition["label"], "image": open_rgb(condition["render_path"]), "label": label})
    cell_w, cell_h = 310, 220
    label_h = 78
    sheet = Image.new("RGB", (2 * cell_w, 2 * (cell_h + label_h) + 34), "white")
    draw = ImageDraw.Draw(sheet)
    font, small = load_fonts()
    draw.text((10, 8), "Material fit fairness audit", fill=(0, 0, 0), font=font)
    for index, cell in enumerate(cells):
        col = index % 2
        row = index // 2
        x = col * cell_w
        y = 34 + row * (cell_h + label_h)
        paste_thumbnail(sheet, cell["image"], x, y, cell_w, cell_h)
        draw.multiline_text((x + 6, y + cell_h + 4), cell["label"], fill=(20, 20, 20), font=small, spacing=2)
    sheet.save(path, quality=92)


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
