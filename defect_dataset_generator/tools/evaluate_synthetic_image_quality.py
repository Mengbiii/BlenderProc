import argparse
import csv
import json
import math
import sys
from pathlib import Path
from statistics import mean, pstdev

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.similarity_metrics import (  # noqa: E402
    PLASTIC_MATERIAL_WEIGHTS,
    _intersect_masks,
    _normalize_weights,
    _plastic_material_components,
    _weighted_score,
    compare_images,
)


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
    parser = argparse.ArgumentParser(description="Evaluate synthetic image and defect quality without YOLO training.")
    parser.add_argument("--default-dataset", required=True)
    parser.add_argument("--fitted-dataset", required=True)
    parser.add_argument("--real-reference", required=True)
    parser.add_argument("--roi-mask", default=None)
    parser.add_argument("--out", required=True)
    parser.add_argument("--resize", type=int, default=512)
    args = parser.parse_args()

    default_dataset = resolve_path(args.default_dataset)
    fitted_dataset = resolve_path(args.fitted_dataset)
    real_reference = resolve_path(args.real_reference)
    roi_mask = resolve_path(args.roi_mask) if args.roi_mask else None
    out_dir = resolve_path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    for path, label in [
        (default_dataset, "default dataset"),
        (fitted_dataset, "fitted dataset"),
        (real_reference, "real reference"),
    ]:
        if not path.exists():
            raise FileNotFoundError("{0} not found: {1}".format(label, path))
    if roi_mask is not None and not roi_mask.exists():
        raise FileNotFoundError("ROI mask not found: {0}".format(roi_mask))

    default = evaluate_dataset(default_dataset, "default_material", real_reference, roi_mask, args.resize)
    fitted = evaluate_dataset(fitted_dataset, "fitted_material", real_reference, roi_mask, args.resize)
    controlled = compare_controlled_variables(default, fitted)

    per_sample_rows = build_per_sample_rows(default, fitted)
    write_csv(out_dir / "image_quality_per_sample.csv", per_sample_rows)

    summary = {
        "schema_version": "0.1",
        "evaluation_type": "black_spot_synthetic_image_quality_ablation",
        "inputs": {
            "default_dataset": str(default_dataset),
            "fitted_dataset": str(fitted_dataset),
            "real_reference": str(real_reference),
            "roi_mask": str(roi_mask) if roi_mask else None,
        },
        "outputs": {
            "image_quality_summary": str(out_dir / "image_quality_summary.json"),
            "per_sample_csv": str(out_dir / "image_quality_per_sample.csv"),
            "paired_diagnosis_csv": str(out_dir / "paired_default_fitted_diagnosis.csv"),
            "default_vs_fitted_contact_sheet": str(out_dir / "default_vs_fitted_contact_sheet.jpg"),
            "defect_crop_contact_sheet": str(out_dir / "defect_crop_contact_sheet.jpg"),
            "material_roi_diagnostic_contact_sheet": str(out_dir / "material_roi_diagnostic_contact_sheet.jpg"),
            "markdown_report": str(out_dir / "IMAGE_QUALITY_ABLATION_REPORT.md"),
            "diagnostic_report": str(out_dir / "IMAGE_QUALITY_DIAGNOSTIC_REPORT.md"),
        },
        "datasets": {
            "default_material": dataset_summary(default),
            "fitted_material": dataset_summary(fitted),
        },
        "controlled_variable_check": controlled,
        "real_reference_similarity": {
            "score_profile": "plastic_material",
            "roi_mode": "mask" if roi_mask else "center",
            "default_material": similarity_summary(default),
            "fitted_material": similarity_summary(fitted),
            "component_diagnosis": component_diagnosis(similarity_summary(default), similarity_summary(fitted)),
        },
        "defect_excluded_similarity": {
            "score_profile": "material_score_excluding_defect",
            "base_score_profile": "plastic_material",
            "roi_mode": "mask" if roi_mask else "center",
            "method": "candidate material ROI minus dilated defect mask; same comparison pixels are excluded from the reference ROI after resizing",
            "default_material": defect_excluded_similarity_summary(default),
            "fitted_material": defect_excluded_similarity_summary(fitted),
            "component_diagnosis": component_diagnosis(
                defect_excluded_similarity_summary(default)["scores"],
                defect_excluded_similarity_summary(fitted)["scores"],
            ),
        },
        "interpretation_guardrails": [
            "Metrics are diagnostic image-quality proxies, not proof of detector performance.",
            "Previous synthetic-only YOLO validation failed on the fixed real QC71336 test split.",
            "Use these diagnostics to guide rendering improvement before expensive retraining.",
        ],
    }
    paired_rows = build_paired_diagnosis_rows(default, fitted)
    write_csv(out_dir / "paired_default_fitted_diagnosis.csv", paired_rows)
    write_json(out_dir / "image_quality_summary.json", summary)
    make_default_vs_fitted_contact_sheet(default, fitted, out_dir / "default_vs_fitted_contact_sheet.jpg")
    make_defect_crop_contact_sheet(default, fitted, out_dir / "defect_crop_contact_sheet.jpg")
    make_material_roi_diagnostic_contact_sheet(default, fitted, real_reference, roi_mask, out_dir / "material_roi_diagnostic_contact_sheet.jpg")
    write_markdown_report(out_dir / "IMAGE_QUALITY_ABLATION_REPORT.md", summary)
    write_diagnostic_report(out_dir / "IMAGE_QUALITY_DIAGNOSTIC_REPORT.md", summary)
    print(json.dumps({"status": "completed", "out": str(out_dir)}, indent=2, ensure_ascii=False))


def resolve_path(value):
    path = Path(value)
    if path.is_absolute():
        return path
    candidate = (PROJECT_ROOT / path).resolve()
    if candidate.exists() or str(value).startswith("outputs"):
        return candidate
    return (REPO_ROOT / path).resolve()


def evaluate_dataset(dataset_dir, name, real_reference, roi_mask, resize):
    rgb_dir = dataset_dir / "rgb"
    mask_dir = dataset_dir / "masks"
    label_dir = dataset_dir / "labels_yolo"
    metadata_dir = dataset_dir / "metadata"
    for required in [rgb_dir, mask_dir, label_dir, metadata_dir]:
        if not required.exists():
            raise FileNotFoundError("Required dataset folder missing: {0}".format(required))

    rgb_files = sorted([p for p in rgb_dir.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS])
    mask_files = sorted([p for p in mask_dir.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS])
    label_files = sorted(label_dir.glob("*.txt"))
    sample_metadata_files = sorted([p for p in metadata_dir.glob("*.json") if p.stem.isdigit()])
    samples = []
    failed = []
    for rgb_path in rgb_files:
        sample_id = rgb_path.stem
        mask_path = mask_dir / (sample_id + ".png")
        label_path = label_dir / (sample_id + ".txt")
        metadata_path = metadata_dir / (sample_id + ".json")
        try:
            sample = evaluate_sample(
                sample_id,
                rgb_path,
                mask_path,
                label_path,
                metadata_path,
                real_reference,
                roi_mask,
                resize,
            )
            samples.append(sample)
            if not sample["integrity"]["passed"]:
                failed.append({"sample_id": sample_id, "errors": sample["integrity"]["errors"]})
        except Exception as exc:
            failed.append({"sample_id": sample_id, "errors": [str(exc)]})
    return {
        "name": name,
        "dataset_dir": str(dataset_dir),
        "counts": {
            "rgb": len(rgb_files),
            "masks": len(mask_files),
            "labels_yolo": len(label_files),
            "metadata": len(sample_metadata_files),
        },
        "samples": samples,
        "failed_samples": failed,
        "aggregates": aggregate_samples(samples),
    }


def evaluate_sample(sample_id, rgb_path, mask_path, label_path, metadata_path, real_reference, roi_mask, resize):
    errors = []
    exists = {
        "rgb": rgb_path.exists(),
        "mask": mask_path.exists(),
        "label_yolo": label_path.exists(),
        "metadata": metadata_path.exists(),
    }
    for key, present in exists.items():
        if not present:
            errors.append("Missing {0} file".format(key))
    image = open_rgb(rgb_path)
    mask = open_mask(mask_path) if mask_path.exists() else Image.new("L", image.size, 0)
    rgb_size = image.size
    mask_size = mask.size
    if rgb_size != mask_size:
        errors.append("RGB/mask size mismatch: {0} vs {1}".format(rgb_size, mask_size))

    label_text = label_path.read_text(encoding="utf-8").strip() if label_path.exists() else ""
    label_valid, yolo_bbox, label_errors = parse_yolo_label(label_text)
    errors.extend(label_errors)
    bbox_pixels = yolo_to_pixels(yolo_bbox, rgb_size) if yolo_bbox else None

    material_stats = compute_material_stats(image)
    defect_stats = compute_defect_stats(image, mask, bbox_pixels)
    similarity = compare_images(
        reference_image=real_reference,
        candidate_image=rgb_path,
        roi_mode="mask" if roi_mask else "center",
        roi_mask=roi_mask,
        resize=resize,
        score_profile="plastic_material",
    )
    defect_excluded_similarity = compare_material_excluding_defect(
        reference_image=real_reference,
        candidate_image=rgb_path,
        defect_mask=mask,
        bbox_pixels=bbox_pixels,
        roi_mask=roi_mask,
        resize=resize,
    )
    metadata = {}
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append("Metadata JSON decode error: {0}".format(exc))

    bbox_area_ratio = 0.0
    if yolo_bbox:
        bbox_area_ratio = float(yolo_bbox[2]) * float(yolo_bbox[3])
    mask_positive = defect_stats["defect_pixel_count"]
    mask_area_ratio = mask_positive / float(rgb_size[0] * rgb_size[1]) if rgb_size[0] and rgb_size[1] else 0.0
    return {
        "sample_id": sample_id,
        "paths": {
            "rgb": str(rgb_path),
            "mask": str(mask_path),
            "label_yolo": str(label_path),
            "metadata": str(metadata_path),
        },
        "seed": metadata.get("seed"),
        "integrity": {
            "exists": exists,
            "rgb_size": list(rgb_size),
            "mask_size": list(mask_size),
            "size_match": rgb_size == mask_size,
            "label_not_empty": bool(label_text),
            "label_bbox_in_0_1": label_valid,
            "passed": not errors,
            "errors": errors,
        },
        "yolo_bbox": yolo_bbox,
        "bbox_pixels_xyxy": list(bbox_pixels) if bbox_pixels else None,
        "bbox_area_ratio": bbox_area_ratio,
        "mask_area_ratio": mask_area_ratio,
        "material_appearance": material_stats,
        "defect_quality": defect_stats,
        "similarity": {
            "weighted_score": similarity["weighted_score"],
            "components": similarity["components"],
            "notes": similarity["notes"],
        },
        "defect_excluded_similarity": defect_excluded_similarity,
    }


def open_rgb(path):
    return ImageOps.exif_transpose(Image.open(path)).convert("RGB")


def open_mask(path):
    return Image.open(path).convert("L")


def parse_yolo_label(text):
    errors = []
    if not text:
        return False, None, ["YOLO label is empty"]
    line = text.splitlines()[0].strip()
    parts = line.split()
    if len(parts) != 5:
        return False, None, ["YOLO label must have 5 values, got {0}".format(len(parts))]
    try:
        values = [float(v) for v in parts[1:]]
    except ValueError:
        return False, None, ["YOLO bbox values are not numeric"]
    if any(v < 0.0 or v > 1.0 for v in values):
        errors.append("YOLO bbox value outside 0-1")
    return not errors, values, errors


def yolo_to_pixels(bbox, image_size):
    width, height = image_size
    cx, cy, bw, bh = bbox
    x1 = int(round((cx - bw / 2.0) * width))
    y1 = int(round((cy - bh / 2.0) * height))
    x2 = int(round((cx + bw / 2.0) * width))
    y2 = int(round((cy + bh / 2.0) * height))
    return clamp_box((x1, y1, x2, y2), image_size)


def clamp_box(box, image_size):
    width, height = image_size
    x1, y1, x2, y2 = box
    x1 = max(0, min(width - 1, x1))
    y1 = max(0, min(height - 1, y1))
    x2 = max(x1 + 1, min(width, x2))
    y2 = max(y1 + 1, min(height, y2))
    return (x1, y1, x2, y2)


def compute_material_stats(image):
    stat = ImageStat.Stat(image)
    gray = ImageOps.grayscale(image)
    gray_stat = ImageStat.Stat(gray)
    return {
        "mean_rgb": [round(v, 4) for v in stat.mean],
        "brightness_mean": round(gray_stat.mean[0], 4),
        "brightness_std": round(gray_stat.stddev[0], 4),
        "local_contrast": round(local_contrast(gray), 6),
        "highlight_ratio": round(pixel_ratio_above(gray, 235), 8),
        "texture_edge_density": round(edge_density(gray), 8),
    }


def compute_defect_stats(image, mask, bbox_pixels):
    gray = ImageOps.grayscale(image)
    if mask.size != gray.size:
        mask = mask.resize(gray.size, Image.NEAREST)
    positive_mask = mask.point(lambda p: 255 if p > 0 else 0)
    defect_count = mask_pixel_count(positive_mask)
    image_area = gray.size[0] * gray.size[1]
    if bbox_pixels is None:
        mask_box = positive_mask.getbbox()
        bbox_pixels = mask_box if mask_box is not None else (0, 0, 1, 1)
    x1, y1, x2, y2 = bbox_pixels
    expanded = expand_box(bbox_pixels, gray.size, factor=3.0, min_pad=18)
    bg_mask = ring_mask(gray.size, expanded, bbox_pixels, positive_mask)
    defect_mean = masked_mean(gray, positive_mask)
    background_mean = masked_mean(gray, bg_mask)
    raw_contrast = None
    normalized_contrast = None
    visibility_proxy = None
    if defect_mean is not None and background_mean is not None:
        raw_contrast = defect_mean - background_mean
        normalized_contrast = raw_contrast / 255.0
        visibility_proxy = abs(raw_contrast) / 255.0
    boundary = positive_mask.filter(ImageFilter.FIND_EDGES).point(lambda p: 255 if p > 0 else 0)
    boundary_pixels = mask_pixel_count(boundary)
    edges = gray.filter(ImageFilter.FIND_EDGES)
    boundary_edge_strength = masked_mean(edges, boundary)
    bbox_crop = gray.crop((x1, y1, x2, y2))
    bbox_edge_density = edge_density(bbox_crop)
    softness_proxy = None
    if boundary_edge_strength is not None:
        softness_proxy = 1.0 - min(1.0, boundary_edge_strength / 255.0)
    return {
        "defect_pixel_count": defect_count,
        "defect_area_ratio": round(defect_count / float(image_area), 8) if image_area else 0.0,
        "bbox_area_ratio": round(((x2 - x1) * (y2 - y1)) / float(image_area), 8) if image_area else 0.0,
        "defect_mean_grayscale": round_or_none(defect_mean, 4),
        "surrounding_background_mean_grayscale": round_or_none(background_mean, 4),
        "defect_background_contrast": round_or_none(raw_contrast, 4),
        "normalized_contrast": round_or_none(normalized_contrast, 6),
        "visibility_proxy": round_or_none(visibility_proxy, 6),
        "boundary_pixel_count": boundary_pixels,
        "boundary_edge_strength": round_or_none(boundary_edge_strength, 4),
        "bbox_edge_density": round(bbox_edge_density, 8),
        "edge_softness_proxy": round_or_none(softness_proxy, 6),
    }


def local_contrast(gray):
    blurred = gray.filter(ImageFilter.BoxBlur(5))
    diff = ImageChops.difference(gray, blurred)
    return ImageStat.Stat(diff).mean[0] / 255.0


def edge_density(gray):
    edges = gray.filter(ImageFilter.FIND_EDGES)
    return pixel_ratio_above(edges, 24)


def pixel_ratio_above(gray, threshold):
    hist = gray.histogram()
    total = sum(hist)
    if total <= 0:
        return 0.0
    return sum(hist[threshold + 1 :]) / float(total)


def mask_pixel_count(mask):
    hist = mask.histogram()
    return sum(hist[1:])


def masked_mean(gray, mask):
    if mask is None:
        return None
    count = mask_pixel_count(mask)
    if count <= 0:
        return None
    return ImageStat.Stat(gray, mask).mean[0]


def expand_box(box, image_size, factor=2.0, min_pad=10):
    x1, y1, x2, y2 = box
    width = x2 - x1
    height = y2 - y1
    pad_x = max(min_pad, int(round(width * (factor - 1.0))))
    pad_y = max(min_pad, int(round(height * (factor - 1.0))))
    return clamp_box((x1 - pad_x, y1 - pad_y, x2 + pad_x, y2 + pad_y), image_size)


def ring_mask(size, outer_box, inner_box, defect_mask):
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle(outer_box, fill=255)
    draw.rectangle(inner_box, fill=0)
    mask = ImageChops.subtract(mask, defect_mask)
    return mask.point(lambda p: 255 if p > 0 else 0)


def compare_material_excluding_defect(reference_image, candidate_image, defect_mask, bbox_pixels, roi_mask, resize):
    try:
        ref_original = open_rgb(Path(reference_image))
        cand_original = open_rgb(Path(candidate_image))
        ref_material_mask = prepare_material_roi_mask(ref_original, roi_mask)
        cand_material_mask = prepare_material_roi_mask(cand_original, roi_mask)
        if defect_mask.size != cand_original.size:
            defect_mask = defect_mask.resize(cand_original.size, Image.NEAREST)
        exclusion_mask = dilated_defect_exclusion_mask(defect_mask, bbox_pixels, cand_original.size)
        cand_clean_mask = ImageChops.subtract(cand_material_mask, exclusion_mask).point(lambda p: 255 if p > 0 else 0)
        ref_box = ref_material_mask.getbbox()
        cand_box = cand_material_mask.getbbox()
        if ref_box is None or cand_box is None:
            raise ValueError("Material ROI mask has no positive pixels.")
        comparison_size = (int(resize), int(resize))
        resample = getattr(getattr(Image, "Resampling", Image), "BILINEAR", Image.BILINEAR)
        ref_cmp = ref_original.crop(ref_box).resize(comparison_size, resample)
        cand_cmp = cand_original.crop(cand_box).resize(comparison_size, resample)
        ref_cmp_mask = ref_material_mask.crop(ref_box).resize(comparison_size, Image.NEAREST)
        cand_cmp_mask = cand_clean_mask.crop(cand_box).resize(comparison_size, Image.NEAREST)
        comparison_mask = _intersect_masks(ref_cmp_mask, cand_cmp_mask)
        comparison_mask_count = mask_pixel_count(comparison_mask)
        if comparison_mask_count <= 0:
            raise ValueError("No material ROI pixels remain after defect exclusion.")
        components = _plastic_material_components(ref_cmp, cand_cmp, comparison_mask)
        weights = _normalize_weights(PLASTIC_MATERIAL_WEIGHTS, defaults=PLASTIC_MATERIAL_WEIGHTS)
        weighted_score = _weighted_score(components, weights)
        return {
            "status": "success",
            "weighted_score": round(weighted_score, 6),
            "components": {key: round_or_none(value, 6) for key, value in components.items()},
            "weights": weights,
            "method": "material_roi_minus_dilated_defect_mask",
            "roi_mode": "mask" if roi_mask else "center",
            "reference_roi_box": list(ref_box),
            "candidate_roi_box": list(cand_box),
            "comparison_mask_pixel_count": comparison_mask_count,
            "excluded_candidate_pixel_count": mask_pixel_count(exclusion_mask),
            "valid_sample": True,
            "skip_reason": None,
        }
    except Exception as exc:
        return {
            "status": "skipped",
            "weighted_score": None,
            "components": {},
            "weights": dict(PLASTIC_MATERIAL_WEIGHTS),
            "method": "material_roi_minus_dilated_defect_mask",
            "roi_mode": "mask" if roi_mask else "center",
            "reference_roi_box": None,
            "candidate_roi_box": None,
            "comparison_mask_pixel_count": 0,
            "excluded_candidate_pixel_count": None,
            "valid_sample": False,
            "skip_reason": str(exc),
        }


def prepare_material_roi_mask(image, roi_mask):
    if roi_mask:
        mask = open_mask(Path(roi_mask))
        if mask.size != image.size:
            mask = mask.resize(image.size, Image.NEAREST)
        return mask.point(lambda p: 255 if p > 0 else 0)
    width, height = image.size
    box = (
        int(round(width * 0.15)),
        int(round(height * 0.15)),
        int(round(width * 0.85)),
        int(round(height * 0.85)),
    )
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rectangle(box, fill=255)
    return mask


def dilated_defect_exclusion_mask(defect_mask, bbox_pixels, image_size):
    positive = defect_mask.convert("L").point(lambda p: 255 if p > 0 else 0)
    if bbox_pixels is not None:
        box = expand_box(tuple(bbox_pixels), image_size, factor=4.0, min_pad=12)
        bbox_mask = Image.new("L", image_size, 0)
        ImageDraw.Draw(bbox_mask).rectangle(box, fill=255)
        positive = ImageChops.lighter(positive, bbox_mask)
    # MaxFilter is a lightweight binary dilation. The small odd kernel avoids
    # removing too much clean plastic around tiny black spots.
    return positive.filter(ImageFilter.MaxFilter(17)).point(lambda p: 255 if p > 0 else 0)


def make_excluded_area_preview(image, roi_mask, defect_mask, bbox_pixels):
    material_mask = prepare_material_roi_mask(image, roi_mask)
    exclusion = dilated_defect_exclusion_mask(defect_mask, bbox_pixels, image.size)
    clean_mask = ImageChops.subtract(material_mask, exclusion).point(lambda p: 255 if p > 0 else 0)
    preview = image.convert("RGB")
    dim = Image.blend(preview, Image.new("RGB", preview.size, (255, 255, 255)), 0.65)
    kept = Image.composite(preview, dim, clean_mask)
    overlay = Image.new("RGB", preview.size, (255, 60, 60))
    return Image.composite(overlay, kept, exclusion.point(lambda p: 120 if p > 0 else 0))


def aggregate_samples(samples):
    material_keys = [
        "brightness_mean",
        "brightness_std",
        "local_contrast",
        "highlight_ratio",
        "texture_edge_density",
    ]
    defect_keys = [
        "defect_pixel_count",
        "defect_area_ratio",
        "bbox_area_ratio",
        "defect_mean_grayscale",
        "surrounding_background_mean_grayscale",
        "defect_background_contrast",
        "normalized_contrast",
        "visibility_proxy",
        "boundary_edge_strength",
        "bbox_edge_density",
        "edge_softness_proxy",
    ]
    similarity_keys = ["weighted_score"] + COMPONENT_KEYS
    return {
        "material_appearance": aggregate_key_group(samples, "material_appearance", material_keys),
        "defect_quality": aggregate_key_group(samples, "defect_quality", defect_keys),
        "similarity": aggregate_similarity(samples, similarity_keys),
        "defect_excluded_similarity": aggregate_defect_excluded_similarity(samples, similarity_keys),
    }


def aggregate_key_group(samples, group, keys):
    return {key: summarize_values([nested_get(s, [group, key]) for s in samples]) for key in keys}


def aggregate_similarity(samples, keys):
    values = {"weighted_score": [nested_get(s, ["similarity", "weighted_score"]) for s in samples]}
    for key in COMPONENT_KEYS:
        values[key] = [nested_get(s, ["similarity", "components", key]) for s in samples]
    return {key: summarize_values(vals) for key, vals in values.items()}


def aggregate_defect_excluded_similarity(samples, keys):
    valid = [s for s in samples if nested_get(s, ["defect_excluded_similarity", "status"]) == "success"]
    values = {"weighted_score": [nested_get(s, ["defect_excluded_similarity", "weighted_score"]) for s in valid]}
    for key in COMPONENT_KEYS:
        values[key] = [nested_get(s, ["defect_excluded_similarity", "components", key]) for s in valid]
    return {key: summarize_values(vals) for key, vals in values.items()}


def summarize_values(values):
    cleaned = [float(v) for v in values if isinstance(v, (int, float)) and not math.isnan(float(v))]
    if not cleaned:
        return {"mean": None, "std": None, "min": None, "max": None}
    return {
        "mean": round(mean(cleaned), 6),
        "std": round(pstdev(cleaned), 6) if len(cleaned) > 1 else 0.0,
        "min": round(min(cleaned), 6),
        "max": round(max(cleaned), 6),
    }


def nested_get(data, keys):
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def compare_controlled_variables(default, fitted):
    default_ids = [s["sample_id"] for s in default["samples"]]
    fitted_ids = [s["sample_id"] for s in fitted["samples"]]
    matching_filenames = default_ids == fitted_ids
    bbox_differences = []
    fitted_by_id = {s["sample_id"]: s for s in fitted["samples"]}
    for sample in default["samples"]:
        other = fitted_by_id.get(sample["sample_id"])
        if other is None:
            bbox_differences.append({"sample_id": sample["sample_id"], "reason": "missing fitted sample"})
        elif sample.get("yolo_bbox") != other.get("yolo_bbox"):
            bbox_differences.append({
                "sample_id": sample["sample_id"],
                "default_bbox": sample.get("yolo_bbox"),
                "fitted_bbox": other.get("yolo_bbox"),
            })
    same_counts = default["counts"]["rgb"] == fitted["counts"]["rgb"] and default["counts"]["masks"] == fitted["counts"]["masks"] and default["counts"]["labels_yolo"] == fitted["counts"]["labels_yolo"]
    return {
        "matching_filenames": matching_filenames,
        "same_number_of_files": same_counts,
        "bbox_values_match": len(bbox_differences) == 0,
        "bbox_differences": bbox_differences,
        "only_material_changed_assessment": matching_filenames and same_counts and len(bbox_differences) == 0,
    }


def dataset_summary(dataset):
    passed = [s for s in dataset["samples"] if s["integrity"]["passed"]]
    return {
        "dataset_dir": dataset["dataset_dir"],
        "counts": dataset["counts"],
        "integrity_passed": len(passed),
        "integrity_failed": len(dataset["samples"]) - len(passed),
        "failed_samples": dataset["failed_samples"],
        "aggregates": dataset["aggregates"],
    }


def similarity_summary(dataset):
    return dataset["aggregates"]["similarity"]


def defect_excluded_similarity_summary(dataset):
    valid = [s for s in dataset["samples"] if nested_get(s, ["defect_excluded_similarity", "status"]) == "success"]
    skipped = [s for s in dataset["samples"] if nested_get(s, ["defect_excluded_similarity", "status"]) != "success"]
    return {
        "scores": dataset["aggregates"]["defect_excluded_similarity"],
        "valid_samples": len(valid),
        "skipped_samples": len(skipped),
        "skip_reasons": [
            {
                "sample_id": sample["sample_id"],
                "reason": nested_get(sample, ["defect_excluded_similarity", "skip_reason"]),
            }
            for sample in skipped
        ],
    }


def component_diagnosis(default_sim, fitted_sim):
    rows = []
    for key in ["weighted_score"] + COMPONENT_KEYS:
        default_mean = nested_get(default_sim, [key, "mean"])
        fitted_mean = nested_get(fitted_sim, [key, "mean"])
        if default_mean is None or fitted_mean is None:
            delta = None
            direction = "unavailable"
        else:
            delta = round(float(fitted_mean) - float(default_mean), 6)
            if delta > 0:
                direction = "fitted_higher"
            elif delta < 0:
                direction = "fitted_lower"
            else:
                direction = "equal"
        rows.append({
            "component": key,
            "default_mean": default_mean,
            "fitted_mean": fitted_mean,
            "fitted_minus_default": delta,
            "direction": direction,
        })
    worse = [row["component"] for row in rows if row["direction"] == "fitted_lower"]
    better = [row["component"] for row in rows if row["direction"] == "fitted_higher"]
    return {
        "components": rows,
        "fitted_lower_components": worse,
        "fitted_higher_components": better,
        "diagnostic_text": build_component_diagnostic_text(rows),
    }


def build_component_diagnostic_text(rows):
    lower = [row for row in rows if row["direction"] == "fitted_lower" and row["component"] != "weighted_score"]
    higher = [row for row in rows if row["direction"] == "fitted_higher" and row["component"] != "weighted_score"]
    lower_text = ", ".join("{0} ({1:+.6f})".format(row["component"], row["fitted_minus_default"]) for row in lower) or "none"
    higher_text = ", ".join("{0} ({1:+.6f})".format(row["component"], row["fitted_minus_default"]) for row in higher) or "none"
    score_row = next((row for row in rows if row["component"] == "weighted_score"), None)
    score_delta = score_row["fitted_minus_default"] if score_row else None
    return (
        "Fitted weighted score delta is {0}. Components lower for fitted: {1}. "
        "Components higher for fitted: {2}."
    ).format(score_delta, lower_text, higher_text)


def build_per_sample_rows(default, fitted):
    rows = []
    for dataset_name, dataset in [("default_material", default), ("fitted_material", fitted)]:
        for sample in dataset["samples"]:
            row = {
                "dataset": dataset_name,
                "sample_id": sample["sample_id"],
                "seed": sample.get("seed"),
                "integrity_passed": sample["integrity"]["passed"],
                "bbox_area_ratio": sample["bbox_area_ratio"],
                "mask_area_ratio": sample["mask_area_ratio"],
                "mean_rgb_r": sample["material_appearance"]["mean_rgb"][0],
                "mean_rgb_g": sample["material_appearance"]["mean_rgb"][1],
                "mean_rgb_b": sample["material_appearance"]["mean_rgb"][2],
                "brightness_mean": sample["material_appearance"]["brightness_mean"],
                "brightness_std": sample["material_appearance"]["brightness_std"],
                "local_contrast": sample["material_appearance"]["local_contrast"],
                "highlight_ratio": sample["material_appearance"]["highlight_ratio"],
                "texture_edge_density": sample["material_appearance"]["texture_edge_density"],
                "defect_pixel_count": sample["defect_quality"]["defect_pixel_count"],
                "defect_mean_grayscale": sample["defect_quality"]["defect_mean_grayscale"],
                "background_mean_grayscale": sample["defect_quality"]["surrounding_background_mean_grayscale"],
                "defect_background_contrast": sample["defect_quality"]["defect_background_contrast"],
                "visibility_proxy": sample["defect_quality"]["visibility_proxy"],
                "edge_softness_proxy": sample["defect_quality"]["edge_softness_proxy"],
                "plastic_material_score": sample["similarity"]["weighted_score"],
                "original_plastic_material_score": sample["similarity"]["weighted_score"],
                "defect_excluded_plastic_material_score": nested_get(sample, ["defect_excluded_similarity", "weighted_score"]),
                "defect_visibility_proxy": sample["defect_quality"]["visibility_proxy"],
                "defect_contrast": sample["defect_quality"]["defect_background_contrast"],
            }
            for key in COMPONENT_KEYS:
                row[key] = sample["similarity"]["components"].get(key)
                row["original_" + key] = sample["similarity"]["components"].get(key)
                row["defect_excluded_" + key] = nested_get(sample, ["defect_excluded_similarity", "components", key])
            rows.append(row)
    return rows


def build_paired_diagnosis_rows(default, fitted):
    rows = []
    fitted_by_id = {sample["sample_id"]: sample for sample in fitted["samples"]}
    for d_sample in default["samples"]:
        f_sample = fitted_by_id.get(d_sample["sample_id"])
        if f_sample is None:
            continue
        default_score = d_sample["similarity"]["weighted_score"]
        fitted_score = f_sample["similarity"]["weighted_score"]
        default_excluded = nested_get(d_sample, ["defect_excluded_similarity", "weighted_score"])
        fitted_excluded = nested_get(f_sample, ["defect_excluded_similarity", "weighted_score"])
        default_visibility = d_sample["defect_quality"]["visibility_proxy"]
        fitted_visibility = f_sample["defect_quality"]["visibility_proxy"]
        row = {
            "filename": d_sample["sample_id"] + ".png",
            "seed": d_sample.get("seed"),
            "default_score": default_score,
            "fitted_score": fitted_score,
            "fitted_minus_default": round_or_none(fitted_score - default_score, 6),
            "default_defect_excluded_score": default_excluded,
            "fitted_defect_excluded_score": fitted_excluded,
            "fitted_minus_default_defect_excluded": round_or_none(fitted_excluded - default_excluded, 6) if default_excluded is not None and fitted_excluded is not None else None,
            "default_visibility_proxy": default_visibility,
            "fitted_visibility_proxy": fitted_visibility,
            "visibility_delta": round_or_none(fitted_visibility - default_visibility, 6) if default_visibility is not None and fitted_visibility is not None else None,
            "default_bbox_area_ratio": d_sample["bbox_area_ratio"],
            "fitted_bbox_area_ratio": f_sample["bbox_area_ratio"],
            "default_mask_area_ratio": d_sample["mask_area_ratio"],
            "fitted_mask_area_ratio": f_sample["mask_area_ratio"],
        }
        for key in COMPONENT_KEYS:
            row["default_" + key] = d_sample["similarity"]["components"].get(key)
            row["fitted_" + key] = f_sample["similarity"]["components"].get(key)
            row["default_defect_excluded_" + key] = nested_get(d_sample, ["defect_excluded_similarity", "components", key])
            row["fitted_defect_excluded_" + key] = nested_get(f_sample, ["defect_excluded_similarity", "components", key])
        rows.append(row)
    return rows


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def make_default_vs_fitted_contact_sheet(default, fitted, out_path):
    fitted_by_id = {s["sample_id"]: s for s in fitted["samples"]}
    rows = []
    for sample in default["samples"]:
        other = fitted_by_id.get(sample["sample_id"])
        if other:
            rows.append((sample, other))
    cell_w, cell_h = 260, 170
    label_h = 36
    cols = 4
    sheet = Image.new("RGB", (cols * cell_w, len(rows) * (cell_h + label_h) + 40), "white")
    draw = ImageDraw.Draw(sheet)
    font, small = load_fonts()
    draw.text((10, 10), "default RGB | fitted RGB | default mask | fitted mask", fill=(0, 0, 0), font=font)
    for idx, (d_sample, f_sample) in enumerate(rows):
        y = 40 + idx * (cell_h + label_h)
        images = [
            open_rgb(Path(d_sample["paths"]["rgb"])),
            open_rgb(Path(f_sample["paths"]["rgb"])),
            open_mask(Path(d_sample["paths"]["mask"])).convert("RGB"),
            open_mask(Path(f_sample["paths"]["mask"])).convert("RGB"),
        ]
        labels = [
            "default {0} score {1:.3f}".format(d_sample["sample_id"], d_sample["similarity"]["weighted_score"]),
            "fitted {0} score {1:.3f}".format(f_sample["sample_id"], f_sample["similarity"]["weighted_score"]),
            "default mask",
            "fitted mask",
        ]
        for col, image in enumerate(images):
            paste_thumbnail(sheet, image, col * cell_w, y, cell_w, cell_h)
            draw.text((col * cell_w + 6, y + cell_h + 4), labels[col], fill=(20, 20, 20), font=small)
    sheet.save(out_path, quality=92)


def make_defect_crop_contact_sheet(default, fitted, out_path):
    fitted_by_id = {s["sample_id"]: s for s in fitted["samples"]}
    rows = []
    for sample in default["samples"]:
        other = fitted_by_id.get(sample["sample_id"])
        if other:
            rows.append((sample, other))
    cell_w, cell_h = 300, 160
    label_h = 30
    sheet = Image.new("RGB", (2 * cell_w, len(rows) * (cell_h + label_h) + 40), "white")
    draw = ImageDraw.Draw(sheet)
    font, small = load_fonts()
    draw.text((10, 10), "defect crops: default vs fitted", fill=(0, 0, 0), font=font)
    for idx, (d_sample, f_sample) in enumerate(rows):
        y = 40 + idx * (cell_h + label_h)
        for col, sample in enumerate([d_sample, f_sample]):
            image = open_rgb(Path(sample["paths"]["rgb"]))
            box = sample.get("bbox_pixels_xyxy")
            if box:
                crop_box = expand_box(tuple(box), image.size, factor=5.0, min_pad=45)
            else:
                crop_box = (0, 0, min(120, image.size[0]), min(120, image.size[1]))
            crop = image.crop(crop_box)
            paste_thumbnail(sheet, crop, col * cell_w, y, cell_w, cell_h)
            label = ("default" if col == 0 else "fitted") + " {0} contrast {1}".format(
                sample["sample_id"],
                sample["defect_quality"]["normalized_contrast"],
            )
            draw.text((col * cell_w + 6, y + cell_h + 4), label, fill=(20, 20, 20), font=small)
    sheet.save(out_path, quality=92)


def make_material_roi_diagnostic_contact_sheet(default, fitted, real_reference, roi_mask, out_path):
    fitted_by_id = {s["sample_id"]: s for s in fitted["samples"]}
    rows = []
    for sample in default["samples"]:
        other = fitted_by_id.get(sample["sample_id"])
        if other:
            rows.append((sample, other))
    ref_image = open_rgb(Path(real_reference))
    ref_preview = crop_reference_roi(ref_image, roi_mask)
    cell_w, cell_h = 220, 150
    label_h = 32
    cols = 7
    sheet = Image.new("RGB", (cols * cell_w, len(rows) * (cell_h + label_h) + 42), "white")
    draw = ImageDraw.Draw(sheet)
    font, small = load_fonts()
    draw.text(
        (10, 10),
        "real ROI | default RGB | fitted RGB | default mask overlay | fitted mask overlay | default clean ROI | fitted clean ROI",
        fill=(0, 0, 0),
        font=font,
    )
    for idx, (d_sample, f_sample) in enumerate(rows):
        y = 42 + idx * (cell_h + label_h)
        d_image = open_rgb(Path(d_sample["paths"]["rgb"]))
        f_image = open_rgb(Path(f_sample["paths"]["rgb"]))
        d_mask = open_mask(Path(d_sample["paths"]["mask"]))
        f_mask = open_mask(Path(f_sample["paths"]["mask"]))
        images = [
            ref_preview,
            d_image,
            f_image,
            overlay_mask(d_image, d_mask),
            overlay_mask(f_image, f_mask),
            make_excluded_area_preview(d_image, roi_mask, d_mask, d_sample.get("bbox_pixels_xyxy")),
            make_excluded_area_preview(f_image, roi_mask, f_mask, f_sample.get("bbox_pixels_xyxy")),
        ]
        labels = [
            "real ROI",
            "default {0}".format(d_sample["sample_id"]),
            "fitted {0}".format(f_sample["sample_id"]),
            "default defect",
            "fitted defect",
            "default material pixels",
            "fitted material pixels",
        ]
        for col, image in enumerate(images):
            paste_thumbnail(sheet, image, col * cell_w, y, cell_w, cell_h)
            draw.text((col * cell_w + 6, y + cell_h + 4), labels[col], fill=(20, 20, 20), font=small)
    sheet.save(out_path, quality=92)


def crop_reference_roi(image, roi_mask):
    if roi_mask:
        mask = open_mask(Path(roi_mask))
        if mask.size != image.size:
            mask = mask.resize(image.size, Image.NEAREST)
        box = mask.getbbox()
        if box:
            return image.crop(box)
    width, height = image.size
    return image.crop((int(width * 0.15), int(height * 0.15), int(width * 0.85), int(height * 0.85)))


def overlay_mask(image, mask):
    if mask.size != image.size:
        mask = mask.resize(image.size, Image.NEAREST)
    base = image.convert("RGB")
    color = Image.new("RGB", base.size, (255, 40, 40))
    alpha = mask.point(lambda p: 130 if p > 0 else 0)
    return Image.composite(color, base, alpha)


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


def write_markdown_report(path, summary):
    default = summary["datasets"]["default_material"]
    fitted = summary["datasets"]["fitted_material"]
    control = summary["controlled_variable_check"]
    default_sim = summary["real_reference_similarity"]["default_material"]
    fitted_sim = summary["real_reference_similarity"]["fitted_material"]
    default_excluded = summary["defect_excluded_similarity"]["default_material"]
    fitted_excluded = summary["defect_excluded_similarity"]["fitted_material"]
    lines = [
        "# Image Quality Ablation Report",
        "",
        "## Purpose",
        "",
        "This evaluation compares default-material and fitted-material synthetic black_spot datasets using image-level diagnostics only. It does not train or run YOLO.",
        "",
        "These image-level diagnostics are intended to guide rendering improvement before expensive YOLO retraining. Since synthetic-only training did not generalize to the fixed real test split, YOLO should be reserved for the next real-only vs real+synthetic augmentation experiment rather than used as the primary image-quality tuning metric.",
        "",
        "## Inputs",
        "",
        "- Default dataset: `{0}`".format(summary["inputs"]["default_dataset"]),
        "- Fitted dataset: `{0}`".format(summary["inputs"]["fitted_dataset"]),
        "- Real reference: `{0}`".format(summary["inputs"]["real_reference"]),
        "- ROI mask: `{0}`".format(summary["inputs"]["roi_mask"]),
        "",
        "## Outputs",
        "",
        "- Summary JSON: `{0}`".format(summary["outputs"]["image_quality_summary"]),
        "- Per-sample CSV: `{0}`".format(summary["outputs"]["per_sample_csv"]),
        "- Paired diagnosis CSV: `{0}`".format(summary["outputs"]["paired_diagnosis_csv"]),
        "- Default vs fitted sheet: `{0}`".format(summary["outputs"]["default_vs_fitted_contact_sheet"]),
        "- Defect crop sheet: `{0}`".format(summary["outputs"]["defect_crop_contact_sheet"]),
        "- Material ROI diagnostic sheet: `{0}`".format(summary["outputs"]["material_roi_diagnostic_contact_sheet"]),
        "",
        "## Dataset Counts",
        "",
        "| Dataset | RGB | Masks | Labels | Metadata | Integrity Failed |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        "| Default | {0} | {1} | {2} | {3} | {4} |".format(default["counts"]["rgb"], default["counts"]["masks"], default["counts"]["labels_yolo"], default["counts"]["metadata"], default["integrity_failed"]),
        "| Fitted | {0} | {1} | {2} | {3} | {4} |".format(fitted["counts"]["rgb"], fitted["counts"]["masks"], fitted["counts"]["labels_yolo"], fitted["counts"]["metadata"], fitted["integrity_failed"]),
        "",
        "## Controlled-Variable Verification",
        "",
        "| Check | Result |",
        "| --- | --- |",
        "| Matching filenames | {0} |".format(control["matching_filenames"]),
        "| Same number of files | {0} |".format(control["same_number_of_files"]),
        "| YOLO bbox values match | {0} |".format(control["bbox_values_match"]),
        "| Assessment: only material changed | {0} |".format(control["only_material_changed_assessment"]),
        "",
        "## Material Appearance Summary",
        "",
        material_table(default, fitted),
        "",
        "## Defect Quality Summary",
        "",
        defect_table(default, fitted),
        "",
        "## Real-Reference Similarity Summary",
        "",
        similarity_table(default_sim, fitted_sim),
        "",
        "Diagnostic: {0}".format(summary["real_reference_similarity"]["component_diagnosis"]["diagnostic_text"]),
        "",
        "## Defect-Excluded Material Similarity",
        "",
        "This score is separate from the original score. It excludes a dilated black_spot mask from the candidate material ROI before computing the same plastic_material components.",
        "",
        defect_excluded_similarity_table(default_excluded, fitted_excluded),
        "",
        "Diagnostic: {0}".format(summary["defect_excluded_similarity"]["component_diagnosis"]["diagnostic_text"]),
        "",
        "## Observations",
        "",
        "- The controlled-variable check confirms matching filenames and matching YOLO bbox values, so the comparison mainly isolates material appearance.",
        "- The fitted-material dataset is evaluated as a visual material calibration output, not as proof of detector improvement.",
        "- Defect visibility and contrast metrics are diagnostic proxies; they do not prove that a detector will learn real defects.",
        "- The contact sheets should be inspected for black spots that are too sharp, too dark, too small, or visually inconsistent with real contamination.",
        "",
        "## Limitations",
        "",
        "- Real-reference similarity compares full synthetic renders to one real reference image using a material ROI proxy; pose and scene mismatch still affect the score.",
        "- Defect-level metrics are based on masks and YOLO bboxes, not human perceptual judgments.",
        "- These diagnostics are not physical material recovery metrics and are not detection-performance metrics.",
        "- Previous synthetic-only YOLO validation scored zero on the fixed real QC71336 test split.",
        "",
        "## Recommended Next Step",
        "",
        "Use this report to choose rendering improvements, then run a controlled real-only vs real+synthetic augmentation experiment on the fixed QC71336 real test split.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def material_table(default, fitted):
    keys = ["brightness_mean", "brightness_std", "local_contrast", "highlight_ratio", "texture_edge_density"]
    lines = ["| Metric | Default mean | Fitted mean | Default std | Fitted std |", "| --- | ---: | ---: | ---: | ---: |"]
    for key in keys:
        d = default["aggregates"]["material_appearance"][key]
        f = fitted["aggregates"]["material_appearance"][key]
        lines.append("| {0} | {1} | {2} | {3} | {4} |".format(key, d["mean"], f["mean"], d["std"], f["std"]))
    return "\n".join(lines)


def defect_table(default, fitted):
    keys = ["defect_area_ratio", "bbox_area_ratio", "defect_background_contrast", "visibility_proxy", "boundary_edge_strength", "edge_softness_proxy"]
    lines = ["| Metric | Default mean | Fitted mean | Default min/max | Fitted min/max |", "| --- | ---: | ---: | --- | --- |"]
    for key in keys:
        d = default["aggregates"]["defect_quality"][key]
        f = fitted["aggregates"]["defect_quality"][key]
        lines.append("| {0} | {1} | {2} | {3}/{4} | {5}/{6} |".format(key, d["mean"], f["mean"], d["min"], d["max"], f["min"], f["max"]))
    return "\n".join(lines)


def similarity_table(default_sim, fitted_sim):
    keys = ["weighted_score"] + COMPONENT_KEYS
    lines = ["| Metric | Default mean | Fitted mean | Default std | Fitted std |", "| --- | ---: | ---: | ---: | ---: |"]
    for key in keys:
        d = default_sim[key]
        f = fitted_sim[key]
        lines.append("| {0} | {1} | {2} | {3} | {4} |".format(key, d["mean"], f["mean"], d["std"], f["std"]))
    return "\n".join(lines)


def defect_excluded_similarity_table(default_excluded, fitted_excluded):
    lines = [
        "| Metric | Default mean | Fitted mean | Default std | Fitted std |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for key in ["weighted_score"] + COMPONENT_KEYS:
        d = default_excluded["scores"][key]
        f = fitted_excluded["scores"][key]
        lines.append("| {0} | {1} | {2} | {3} | {4} |".format(key, d["mean"], f["mean"], d["std"], f["std"]))
    lines.extend([
        "| valid_samples | {0} | {1} |  |  |".format(default_excluded["valid_samples"], fitted_excluded["valid_samples"]),
        "| skipped_samples | {0} | {1} |  |  |".format(default_excluded["skipped_samples"], fitted_excluded["skipped_samples"]),
    ])
    return "\n".join(lines)


def write_diagnostic_report(path, summary):
    default = summary["datasets"]["default_material"]
    fitted = summary["datasets"]["fitted_material"]
    original_default = summary["real_reference_similarity"]["default_material"]
    original_fitted = summary["real_reference_similarity"]["fitted_material"]
    excluded_default = summary["defect_excluded_similarity"]["default_material"]
    excluded_fitted = summary["defect_excluded_similarity"]["fitted_material"]
    original_delta = round_or_none(original_fitted["weighted_score"]["mean"] - original_default["weighted_score"]["mean"], 6)
    excluded_delta = round_or_none(
        excluded_fitted["scores"]["weighted_score"]["mean"] - excluded_default["scores"]["weighted_score"]["mean"],
        6,
    )
    visibility_delta = round_or_none(
        fitted["aggregates"]["defect_quality"]["visibility_proxy"]["mean"] - default["aggregates"]["defect_quality"]["visibility_proxy"]["mean"],
        6,
    )
    if excluded_delta is not None and excluded_delta < 0:
        interpretation = (
            "The current fitted material does not improve the selected image-level similarity metric under this "
            "reference/ROI setup. The material fitting search space or scoring weights should be revised before "
            "using this fitted material as evidence of visual improvement."
        )
    elif excluded_delta is not None and excluded_delta > 0:
        interpretation = (
            "The fitted material appears to improve clean-material similarity when defect pixels are excluded, "
            "but it also increases black-spot visibility. This suggests that material and defect realism should "
            "be evaluated separately."
        )
    else:
        interpretation = (
            "The defect-excluded score does not show a clear difference between materials under this reference/ROI setup."
        )
    lines = [
        "# Image Quality Diagnostic Report",
        "",
        "## Purpose",
        "",
        "This diagnostic extends the non-YOLO image-quality ablation by separating original material similarity from defect-excluded material similarity. It is an image-level analysis only.",
        "",
        "## Previous Key Result",
        "",
        "- Original plastic_material mean score: default `{0}`, fitted `{1}`, fitted-minus-default `{2}`.".format(
            original_default["weighted_score"]["mean"],
            original_fitted["weighted_score"]["mean"],
            original_delta,
        ),
        "- Fitted material was brighter and had higher black_spot visibility, but it scored lower against the selected real reference ROI.",
        "",
        "## Component-Level Score Comparison",
        "",
        similarity_table(original_default, original_fitted),
        "",
        summary["real_reference_similarity"]["component_diagnosis"]["diagnostic_text"],
        "",
        "## Defect-Excluded Material Score Comparison",
        "",
        defect_excluded_similarity_table(excluded_default, excluded_fitted),
        "",
        summary["defect_excluded_similarity"]["component_diagnosis"]["diagnostic_text"],
        "",
        "## Defect Visibility Comparison",
        "",
        "| Metric | Default mean | Fitted mean | Fitted minus default |",
        "| --- | ---: | ---: | ---: |",
        "| visibility_proxy | {0} | {1} | {2} |".format(
            default["aggregates"]["defect_quality"]["visibility_proxy"]["mean"],
            fitted["aggregates"]["defect_quality"]["visibility_proxy"]["mean"],
            visibility_delta,
        ),
        "| defect_background_contrast | {0} | {1} | {2} |".format(
            default["aggregates"]["defect_quality"]["defect_background_contrast"]["mean"],
            fitted["aggregates"]["defect_quality"]["defect_background_contrast"]["mean"],
            round_or_none(
                fitted["aggregates"]["defect_quality"]["defect_background_contrast"]["mean"]
                - default["aggregates"]["defect_quality"]["defect_background_contrast"]["mean"],
                6,
            ),
        ),
        "",
        "## Visual Diagnostics",
        "",
        "- Default vs fitted contact sheet: `{0}`".format(summary["outputs"]["default_vs_fitted_contact_sheet"]),
        "- Defect crop contact sheet: `{0}`".format(summary["outputs"]["defect_crop_contact_sheet"]),
        "- Material ROI diagnostic contact sheet: `{0}`".format(summary["outputs"]["material_roi_diagnostic_contact_sheet"]),
        "",
        "## Cautious Interpretation",
        "",
        interpretation,
        "",
        "These metrics are diagnostic proxies. They do not prove real-world realism, physical material accuracy, or detection performance.",
        "",
        "## Recommended Next Action",
        "",
        "Inspect the material ROI diagnostic contact sheet and revise material calibration/search-space choices before using fitted-material renders as evidence of visual improvement. YOLO should remain reserved for the later real-only vs real+synthetic augmentation experiment.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def round_or_none(value, digits=6):
    if value is None:
        return None
    return round(float(value), digits)


if __name__ == "__main__":
    main()
