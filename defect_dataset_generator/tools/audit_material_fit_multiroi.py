import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageStat

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.similarity_metrics import compare_images  # noqa: E402


COMPONENT_KEYS = [
    "brightness_similarity",
    "color_similarity",
    "local_contrast_similarity",
    "highlight_similarity",
    "texture_similarity",
    "ssim_similarity",
]


def main():
    parser = argparse.ArgumentParser(
        description="Audit material fitting candidates with multiple material ROIs."
    )
    parser.add_argument("--fit-dir", required=True, help="Material fitting output directory.")
    parser.add_argument("--roi-config", required=True, help="Multi-ROI audit config JSON.")
    parser.add_argument("--out", required=True, help="Audit output directory.")
    parser.add_argument("--top-k", type=int, default=10, help="Number of candidates to show in the contact sheet.")
    parser.add_argument("--resize", type=int, default=None, help="Override metric resize size.")
    args = parser.parse_args()

    fit_dir = _resolve_path(args.fit_dir)
    roi_config_path = _resolve_path(args.roi_config)
    out_dir = _resolve_path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    config = _load_json(roi_config_path)
    candidates_doc = _load_json(fit_dir / "material_fit_candidates.json")
    candidates = candidates_doc.get("candidates", [])
    if not candidates:
        raise ValueError("No candidates found in material_fit_candidates.json")

    reference_image = _resolve_path(config["reference_image"])
    resize = int(args.resize or config.get("resize", 512))
    score_profile = config.get("score_profile", "plastic_material")
    rois = _validate_rois(config.get("rois", []))

    roi_preview_path = out_dir / "material_audit_roi_preview.jpg"
    _write_roi_preview(reference_image, rois, roi_preview_path)

    rows = []
    failures = []
    for candidate in candidates:
        result = _score_candidate(candidate, reference_image, rois, resize, score_profile)
        if result["status"] != "success":
            failures.append(result)
        rows.append(result)

    successful = [row for row in rows if row["status"] == "success"]
    successful.sort(key=lambda item: item["multi_roi_weighted_score"], reverse=True)
    for rank, row in enumerate(successful, start=1):
        row["multi_roi_rank"] = rank

    per_candidate_csv = out_dir / "material_fit_audit_per_candidate.csv"
    _write_candidate_csv(rows, per_candidate_csv)

    top_rows = successful[: max(1, int(args.top_k))]
    contact_sheet_path = out_dir / "material_fit_audit_contact_sheet.jpg"
    _write_contact_sheet(reference_image, rois, top_rows, contact_sheet_path)

    summary = {
        "schema_version": "0.1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "fit_dir": str(fit_dir),
        "roi_config": str(roi_config_path),
        "reference_image": str(reference_image),
        "score_profile": score_profile,
        "resize": resize,
        "candidate_count": len(candidates),
        "successful_candidates": len(successful),
        "failed_candidates": len(failures),
        "roi_weights": {
            roi["roi_id"]: roi["normalized_weight"]
            for roi in rois
            if roi.get("include_in_material_score", True)
        },
        "top_candidates": [_compact_candidate(row) for row in top_rows],
        "original_best_candidate": _find_original_best(candidates),
        "multi_roi_best_candidate": _compact_candidate(successful[0]) if successful else None,
        "failure_reasons": failures[:10],
        "outputs": {
            "roi_preview": str(roi_preview_path),
            "per_candidate_csv": str(per_candidate_csv),
            "contact_sheet": str(contact_sheet_path),
        },
        "limitations": [
            "The current clean candidate renderer camera is not fully aligned with the real reference photo, so manual ROI boxes are only approximate after scaling.",
            "This audit diagnoses material/scene mismatch and candidate ranking stability; it is not physical BRDF recovery.",
            "Human visual review remains required before accepting a material as a generation default."
        ],
    }
    summary_path = out_dir / "material_fit_audit_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    report_path = out_dir / "MATERIAL_FIT_AUDIT_REPORT.md"
    _write_report(summary, rows, rois, report_path)

    print("Material fit multi-ROI audit complete.")
    print("Summary:", summary_path)
    print("Report:", report_path)
    print("Contact sheet:", contact_sheet_path)


def _resolve_path(path_value):
    path = Path(path_value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _load_json(path):
    if not path.exists():
        raise FileNotFoundError("File not found: {0}".format(path))
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_rois(rois):
    if not rois:
        raise ValueError("ROI config must contain at least one ROI.")
    included = [roi for roi in rois if roi.get("include_in_material_score", True)]
    total_weight = sum(float(roi.get("weight", 0.0)) for roi in included)
    if total_weight <= 0:
        raise ValueError("At least one included ROI must have a positive weight.")
    validated = []
    for roi in rois:
        box = roi.get("box_xywh")
        if not isinstance(box, list) or len(box) != 4:
            raise ValueError("ROI {0} must define box_xywh=[x,y,w,h].".format(roi.get("roi_id")))
        x, y, w, h = [int(v) for v in box]
        if x < 0 or y < 0 or w <= 0 or h <= 0:
            raise ValueError("ROI {0} has invalid box_xywh.".format(roi.get("roi_id")))
        copied = dict(roi)
        copied["box_xywh"] = [x, y, w, h]
        if copied.get("include_in_material_score", True):
            copied["normalized_weight"] = float(copied.get("weight", 0.0)) / total_weight
        else:
            copied["normalized_weight"] = 0.0
        validated.append(copied)
    return validated


def _score_candidate(candidate, reference_image, rois, resize, score_profile):
    candidate_id = candidate.get("candidate_id")
    render_path = _resolve_path(candidate.get("render_path", ""))
    if not render_path.exists():
        return {
            "candidate_id": candidate_id,
            "status": "failed",
            "failure_reason": "render_path_missing",
            "render_path": str(render_path),
        }

    roi_results = {}
    weighted = 0.0
    included_count = 0
    try:
        for roi in rois:
            comparison = compare_images(
                reference_image=reference_image,
                candidate_image=render_path,
                roi_mode="manual",
                roi_box=roi["box_xywh"],
                resize=resize,
                score_profile=score_profile,
            )
            stats = _roi_stats(reference_image, render_path, roi["box_xywh"])
            roi_result = {
                "weighted_score": comparison["weighted_score"],
                "components": comparison["components"],
                "reference_mean_rgb": stats["reference_mean_rgb"],
                "candidate_mean_rgb": stats["candidate_mean_rgb"],
                "reference_brightness": stats["reference_brightness"],
                "candidate_brightness": stats["candidate_brightness"],
                "included_in_material_score": bool(roi.get("include_in_material_score", True)),
                "normalized_weight": roi["normalized_weight"],
            }
            roi_results[roi["roi_id"]] = roi_result
            if roi.get("include_in_material_score", True):
                weighted += comparison["weighted_score"] * roi["normalized_weight"]
                included_count += 1
        component_means = _aggregate_components(roi_results, rois)
        return {
            "candidate_id": candidate_id,
            "status": "success",
            "original_rank": candidate.get("rank"),
            "original_mean_weighted_score": candidate.get("mean_weighted_score"),
            "multi_roi_weighted_score": round(weighted, 6),
            "included_roi_count": included_count,
            "render_path": str(render_path),
            "material_parameters": candidate.get("material_parameters") or candidate.get("sampled_material_parameters", {}),
            "scene_calibration": candidate.get("scene_calibration", {}),
            "roi_results": roi_results,
            "component_means": component_means,
        }
    except Exception as exc:
        return {
            "candidate_id": candidate_id,
            "status": "failed",
            "failure_reason": str(exc),
            "render_path": str(render_path),
        }


def _roi_stats(reference_image, candidate_image, roi_box):
    ref = ImageOps.exif_transpose(Image.open(reference_image)).convert("RGB")
    cand = ImageOps.exif_transpose(Image.open(candidate_image)).convert("RGB")
    ref_box = _xywh_to_ltrb(roi_box)
    cand_box = _scale_box(roi_box, ref.size, cand.size)
    ref_crop = ref.crop(ref_box)
    cand_crop = cand.crop(cand_box)
    ref_stat = ImageStat.Stat(ref_crop)
    cand_stat = ImageStat.Stat(cand_crop)
    ref_gray = ImageOps.grayscale(ref_crop)
    cand_gray = ImageOps.grayscale(cand_crop)
    return {
        "reference_mean_rgb": [round(v, 3) for v in ref_stat.mean],
        "candidate_mean_rgb": [round(v, 3) for v in cand_stat.mean],
        "reference_brightness": round(ImageStat.Stat(ref_gray).mean[0], 3),
        "candidate_brightness": round(ImageStat.Stat(cand_gray).mean[0], 3),
    }


def _aggregate_components(roi_results, rois):
    output = {}
    for key in COMPONENT_KEYS:
        total = 0.0
        used = 0.0
        for roi in rois:
            if not roi.get("include_in_material_score", True):
                continue
            value = roi_results[roi["roi_id"]]["components"].get(key)
            if value is None:
                continue
            total += float(value) * roi["normalized_weight"]
            used += roi["normalized_weight"]
        output[key] = round(total / used, 6) if used > 0 else None
    return output


def _write_candidate_csv(rows, path):
    fieldnames = [
        "candidate_id",
        "status",
        "original_rank",
        "original_mean_weighted_score",
        "multi_roi_rank",
        "multi_roi_weighted_score",
        "brightness_similarity",
        "color_similarity",
        "local_contrast_similarity",
        "highlight_similarity",
        "texture_similarity",
        "ssim_similarity",
        "base_color",
        "roughness",
        "specular",
        "noise_strength",
        "bump_strength",
        "failure_reason",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in sorted(rows, key=lambda item: item.get("candidate_id", 999999)):
            params = row.get("material_parameters", {})
            means = row.get("component_means", {})
            writer.writerow({
                "candidate_id": row.get("candidate_id"),
                "status": row.get("status"),
                "original_rank": row.get("original_rank"),
                "original_mean_weighted_score": row.get("original_mean_weighted_score"),
                "multi_roi_rank": row.get("multi_roi_rank"),
                "multi_roi_weighted_score": row.get("multi_roi_weighted_score"),
                "brightness_similarity": means.get("brightness_similarity"),
                "color_similarity": means.get("color_similarity"),
                "local_contrast_similarity": means.get("local_contrast_similarity"),
                "highlight_similarity": means.get("highlight_similarity"),
                "texture_similarity": means.get("texture_similarity"),
                "ssim_similarity": means.get("ssim_similarity"),
                "base_color": json.dumps(params.get("base_color")),
                "roughness": params.get("roughness"),
                "specular": params.get("specular") or params.get("specular_ior_level"),
                "noise_strength": params.get("noise_strength"),
                "bump_strength": params.get("bump_strength"),
                "failure_reason": row.get("failure_reason"),
            })


def _write_roi_preview(reference_image, rois, path):
    image = ImageOps.exif_transpose(Image.open(reference_image)).convert("RGB")
    draw = ImageDraw.Draw(image)
    colors = ["red", "lime", "cyan", "yellow", "magenta", "orange"]
    for index, roi in enumerate(rois):
        box = _xywh_to_ltrb(roi["box_xywh"])
        color = colors[index % len(colors)]
        draw.rectangle(box, outline=color, width=12)
        draw.text((box[0] + 8, box[1] + 8), roi["roi_id"], fill=color)
    image.thumbnail((1600, 1067), Image.LANCZOS)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, quality=92)


def _write_contact_sheet(reference_image, rois, top_rows, path):
    tile_w, tile_h = 360, 270
    label_h = 92
    cols = 3
    items = [{"kind": "reference", "path": str(reference_image), "label": "real reference"}] + top_rows
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tile_w, rows * (tile_h + label_h)), "white")
    draw = ImageDraw.Draw(sheet)
    for index, item in enumerate(items):
        x = (index % cols) * tile_w
        y = (index // cols) * (tile_h + label_h)
        if item.get("kind") == "reference":
            image = ImageOps.exif_transpose(Image.open(item["path"])).convert("RGB")
            label = "Real reference\nROI preview saved separately"
        else:
            image = ImageOps.exif_transpose(Image.open(item["render_path"])).convert("RGB")
            params = item.get("material_parameters", {})
            label = (
                "candidate {0} | audit {1:.6f}\n"
                "orig rank {2} | orig {3}\n"
                "base {4} rough {5} spec {6}\n"
                "noise {7} bump {8}"
            ).format(
                item.get("candidate_id"),
                item.get("multi_roi_weighted_score", 0.0),
                item.get("original_rank"),
                item.get("original_mean_weighted_score"),
                _short(params.get("base_color")),
                params.get("roughness"),
                params.get("specular") or params.get("specular_ior_level"),
                params.get("noise_strength"),
                params.get("bump_strength"),
            )
        image.thumbnail((tile_w, tile_h), Image.LANCZOS)
        px = x + (tile_w - image.width) // 2
        py = y + (tile_h - image.height) // 2
        sheet.paste(image, (px, py))
        draw.multiline_text((x + 8, y + tile_h + 6), label, fill="black", spacing=3)
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, quality=92)


def _write_report(summary, rows, rois, path):
    top = summary["top_candidates"]
    original = summary["original_best_candidate"]
    best = summary["multi_roi_best_candidate"]
    lines = [
        "# QC7-5244 Black Material Fit Multi-ROI Audit",
        "",
        "## Purpose",
        "This audit checks whether the current visually fitted material remains plausible beyond the original single clean-plastic ROI. It reuses existing clean candidate renders and does not run BlenderProc, YOLO, or any GPU-heavy task.",
        "",
        "## Important Interpretation",
        "The previous high score only showed that one ROI matched the current `plastic_material` metric. It did not prove whole-image realism. The current candidate renderer camera is also not fully aligned with the real reference photo, so this report is a diagnostic ranking and failure-analysis tool, not a final material acceptance certificate.",
        "",
        "## Inputs",
        "- Fit folder: `{0}`".format(summary["fit_dir"]),
        "- ROI config: `{0}`".format(summary["roi_config"]),
        "- Reference image: `{0}`".format(summary["reference_image"]),
        "- Score profile: `{0}`".format(summary["score_profile"]),
        "- Resize: `{0}`".format(summary["resize"]),
        "",
        "## ROI Set",
        "| ROI | Weight | Included | Reason |",
        "| --- | ---: | --- | --- |",
    ]
    for roi in rois:
        lines.append(
            "| {0} | {1:.3f} | {2} | {3} |".format(
                roi["roi_id"],
                roi["normalized_weight"],
                "yes" if roi.get("include_in_material_score", True) else "no",
                roi.get("reason", ""),
            )
        )
    lines.extend([
        "",
        "## Ranking Summary",
        "- Original single-ROI best candidate: `{0}` with score `{1}`.".format(
            original.get("candidate_id") if original else None,
            original.get("mean_weighted_score") if original else None,
        ),
        "- Multi-ROI best candidate: `{0}` with score `{1}`.".format(
            best.get("candidate_id") if best else None,
            best.get("multi_roi_weighted_score") if best else None,
        ),
        "",
        "## Top Candidates",
        "| Audit rank | Candidate | Multi-ROI score | Original rank | Original score | Brightness | Color | Contrast | Highlight | Texture | SSIM |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in top:
        means = row.get("component_means", {})
        lines.append(
            "| {rank} | {cid} | {score} | {orank} | {oscore} | {b} | {c} | {lc} | {h} | {t} | {s} |".format(
                rank=row.get("multi_roi_rank"),
                cid=row.get("candidate_id"),
                score=row.get("multi_roi_weighted_score"),
                orank=row.get("original_rank"),
                oscore=row.get("original_mean_weighted_score"),
                b=means.get("brightness_similarity"),
                c=means.get("color_similarity"),
                lc=means.get("local_contrast_similarity"),
                h=means.get("highlight_similarity"),
                t=means.get("texture_similarity"),
                s=means.get("ssim_similarity"),
            )
        )
    decision = _decision_text(original, best)
    lines.extend([
        "",
        "## Diagnostic Decision",
        decision,
        "",
        "## Outputs",
        "- ROI preview: `{0}`".format(summary["outputs"]["roi_preview"]),
        "- Candidate CSV: `{0}`".format(summary["outputs"]["per_candidate_csv"]),
        "- Contact sheet: `{0}`".format(summary["outputs"]["contact_sheet"]),
        "",
        "## Recommended Next Step",
        "Create a V2 search space that is brighter, slightly cooler blue-gray, and has stronger micro texture / soft highlight support, then run a new fitting pass only after reviewing this audit contact sheet.",
        "",
        "## Limitations",
    ])
    for item in summary["limitations"]:
        lines.append("- {0}".format(item))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _decision_text(original, best):
    if not original or not best:
        return "No successful audit ranking was produced."
    if original.get("candidate_id") == best.get("candidate_id"):
        return (
            "The original best candidate remains top under the current multi-ROI audit, "
            "but this still requires human visual acceptance because camera/scene alignment is weak."
        )
    return (
        "The multi-ROI audit changes the top candidate from `{0}` to `{1}`. "
        "This means the single-ROI fit was not stable enough to accept as the default material without further search-space revision."
    ).format(original.get("candidate_id"), best.get("candidate_id"))


def _find_original_best(candidates):
    successes = [c for c in candidates if c.get("status") == "success"]
    if not successes:
        return None
    return min(successes, key=lambda item: item.get("rank", 999999))


def _compact_candidate(row):
    if row is None:
        return None
    return {
        "candidate_id": row.get("candidate_id"),
        "status": row.get("status"),
        "original_rank": row.get("original_rank"),
        "original_mean_weighted_score": row.get("original_mean_weighted_score"),
        "multi_roi_rank": row.get("multi_roi_rank"),
        "multi_roi_weighted_score": row.get("multi_roi_weighted_score"),
        "component_means": row.get("component_means"),
        "material_parameters": row.get("material_parameters"),
        "scene_calibration": row.get("scene_calibration"),
        "render_path": row.get("render_path"),
    }


def _xywh_to_ltrb(box):
    x, y, w, h = [int(v) for v in box]
    return (x, y, x + w, y + h)


def _scale_box(box, source_size, target_size):
    x, y, w, h = [int(v) for v in box]
    sx = target_size[0] / float(source_size[0])
    sy = target_size[1] / float(source_size[1])
    return (
        int(round(x * sx)),
        int(round(y * sy)),
        int(round((x + w) * sx)),
        int(round((y + h) * sy)),
    )


def _short(value):
    if isinstance(value, list):
        return "[" + ",".join("{0:.3g}".format(float(v)) for v in value[:3]) + "]"
    return str(value)


if __name__ == "__main__":
    main()
