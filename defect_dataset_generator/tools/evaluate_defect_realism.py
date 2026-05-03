"""Lightweight non-YOLO defect realism diagnostics.

This tool compares localized real defect crops with synthetic defect crops.
Labels are used only as crop/localization hints. The metrics are diagnostic
image-quality proxies, not detector performance evidence.
"""

import argparse
import csv
import json
import math
import statistics
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageStat


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.real_dataset_profiles import scan_real_dataset_root  # noqa: E402


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}
SCHEMA_VERSION = "0.2"
MASK_FOREGROUND_THRESHOLD = 10


def resolve_path(path_text):
    path = Path(path_text)
    if path.is_absolute():
        return path
    return (PROJECT_ROOT / path).resolve()


def ensure_dir(path):
    path.mkdir(parents=True, exist_ok=True)
    return path


def image_resize_filter():
    if hasattr(Image, "Resampling"):
        return Image.Resampling.LANCZOS
    return Image.LANCZOS


def resize_for_metrics(image, max_side=960):
    width, height = image.size
    side = max(width, height)
    if side <= max_side:
        return image
    scale = max_side / float(side)
    new_size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    return image.resize(new_size, image_resize_filter())


def clamp(value, low, high):
    return max(low, min(high, value))


def read_yolo_labels(label_path):
    labels = []
    if not label_path or not label_path.exists():
        return labels
    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split()
        if len(parts) < 5:
            continue
        try:
            class_id = int(float(parts[0]))
            x, y, w, h = [float(v) for v in parts[1:5]]
        except ValueError:
            continue
        labels.append(
            {
                "class_id": class_id,
                "x": x,
                "y": y,
                "w": w,
                "h": h,
                "valid": all(0.0 <= v <= 1.0 for v in [x, y, w, h]) and w > 0 and h > 0,
                "raw": line.strip(),
            }
        )
    return labels


def bbox_norm_to_pixels(label, width, height):
    cx = label["x"] * width
    cy = label["y"] * height
    bw = label["w"] * width
    bh = label["h"] * height
    x0 = int(round(cx - bw / 2.0))
    y0 = int(round(cy - bh / 2.0))
    x1 = int(round(cx + bw / 2.0))
    y1 = int(round(cy + bh / 2.0))
    return (
        clamp(x0, 0, width - 1),
        clamp(y0, 0, height - 1),
        clamp(max(x1, x0 + 1), 1, width),
        clamp(max(y1, y0 + 1), 1, height),
    )


def expand_box(box, margin, width, height):
    x0, y0, x1, y1 = box
    return (
        clamp(x0 - margin, 0, width - 1),
        clamp(y0 - margin, 0, height - 1),
        clamp(x1 + margin, 1, width),
        clamp(y1 + margin, 1, height),
    )


def crop_box_around_bbox(label, width, height, min_crop=160, scale=8.0):
    bbox = bbox_norm_to_pixels(label, width, height)
    x0, y0, x1, y1 = bbox
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    crop_size = int(max(min_crop, (x1 - x0) * scale, (y1 - y0) * scale))
    crop_size = min(crop_size, width, height)
    left = int(round(cx - crop_size / 2.0))
    top = int(round(cy - crop_size / 2.0))
    left = clamp(left, 0, max(0, width - crop_size))
    top = clamp(top, 0, max(0, height - crop_size))
    return (left, top, left + crop_size, top + crop_size), bbox


def iter_image_label_pairs(image_dir, label_dir, max_samples=None, only_non_empty=True):
    image_dir = Path(image_dir)
    label_dir = Path(label_dir)
    pairs = []
    for image_path in sorted(image_dir.iterdir()):
        if not image_path.is_file() or image_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        label_path = label_dir / (image_path.stem + ".txt")
        labels = read_yolo_labels(label_path)
        if only_non_empty and not labels:
            continue
        pairs.append((image_path, label_path, labels))
        if max_samples and len(pairs) >= max_samples:
            break
    return pairs


def iter_manifest_label_pairs(manifest_path, defect_type=None, model=None, color=None, max_samples=None):
    pairs = []
    manifest_path = Path(manifest_path)
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if defect_type and row.get("defect_type") != defect_type:
                continue
            if model and row.get("model") != model:
                continue
            if color and row.get("color") != color:
                continue
            image_path = Path(row.get("image_path", ""))
            label_path = Path(row.get("label_path", ""))
            if not image_path.exists() or not label_path.exists():
                continue
            labels = read_yolo_labels(label_path)
            if not labels:
                continue
            pairs.append((image_path, label_path, labels))
            if max_samples and len(pairs) >= max_samples:
                break
    return pairs


def iter_synthetic_pairs(dataset_dir, max_samples=None):
    dataset_dir = Path(dataset_dir)
    rgb_dir = dataset_dir / "rgb"
    label_dir = dataset_dir / "labels_yolo"
    mask_dir = dataset_dir / "masks"
    pairs = []
    if not rgb_dir.exists():
        return pairs
    for image_path in sorted(rgb_dir.iterdir()):
        if not image_path.is_file() or image_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        label_path = label_dir / (image_path.stem + ".txt")
        mask_path = mask_dir / (image_path.stem + ".png")
        labels = read_yolo_labels(label_path)
        if not labels:
            continue
        pairs.append((image_path, label_path, mask_path if mask_path.exists() else None, labels))
        if max_samples and len(pairs) >= max_samples:
            break
    return pairs


def grayscale_values(image):
    gray = ImageOps.grayscale(image)
    return list(gray.getdata())


def mean_or_none(values):
    if not values:
        return None
    return float(sum(values)) / float(len(values))


def std_or_none(values):
    if len(values) < 2:
        return 0.0 if values else None
    return float(statistics.pstdev(values))


def rect_values(gray, box):
    x0, y0, x1, y1 = box
    width = max(1, x1 - x0)
    height = max(1, y1 - y0)
    if width * height > 250000:
        step = int(math.ceil(math.sqrt((width * height) / 250000.0)))
        pix = gray.load()
        values = []
        for y in range(y0, y1, step):
            for x in range(x0, x1, step):
                values.append(pix[x, y])
        return values
    return list(gray.crop(box).getdata())


def rect_values_full_loop(gray, box):
    x0, y0, x1, y1 = box
    values = []
    pix = gray.load()
    for y in range(y0, y1):
        for x in range(x0, x1):
            values.append(pix[x, y])
    return values


def rect_ring_values(gray, inner_box, outer_box):
    ix0, iy0, ix1, iy1 = inner_box
    ox0, oy0, ox1, oy1 = outer_box
    outer_area = max(1, ox1 - ox0) * max(1, oy1 - oy0)
    step = 1
    if outer_area > 300000:
        step = int(math.ceil(math.sqrt(outer_area / 300000.0)))
    values = []
    pix = gray.load()
    for y in range(oy0, oy1, step):
        for x in range(ox0, ox1, step):
            if ix0 <= x < ix1 and iy0 <= y < iy1:
                continue
            values.append(pix[x, y])
    return values


def mask_values(gray, mask):
    if mask.size != gray.size:
        mask = mask.resize(gray.size, Image.NEAREST)
    gpix = gray.load()
    mask_gray = ImageOps.grayscale(mask)
    threshold = foreground_threshold(mask_gray)
    mpix = mask_gray.load()
    values = []
    width, height = gray.size
    for y in range(height):
        for x in range(width):
            if mpix[x, y] > threshold:
                values.append(gpix[x, y])
    return values


def foreground_threshold(mask):
    extrema = ImageOps.grayscale(mask).getextrema()
    if extrema[1] <= 1:
        return 0
    return MASK_FOREGROUND_THRESHOLD


def mask_bbox(mask):
    gray = ImageOps.grayscale(mask)
    threshold = foreground_threshold(gray)
    return gray.point(lambda p: 255 if p > threshold else 0).getbbox()


def box_area(box):
    x0, y0, x1, y1 = box
    return max(0, x1 - x0) * max(0, y1 - y0)


def boxes_intersect(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return ax0 < bx1 and ax1 > bx0 and ay0 < by1 and ay1 > by0


def mask_bbox_plausibility(mask_box, label_box, image_size, defect_type):
    """Reject masks whose bbox is clearly whole-image, huge, or off-label."""
    width, height = image_size
    image_area = max(1, width * height)
    mask_area = box_area(mask_box)
    label_area = max(1, box_area(label_box))
    max_image_ratio_by_type = {
        "black_dot": 0.02,
        "foreign_material": 0.04,
        "splay": 0.08,
        "mixed_color_contamination": 0.18,
    }
    max_bbox_ratio_by_type = {
        "black_dot": 25.0,
        "foreign_material": 30.0,
        "splay": 80.0,
        "mixed_color_contamination": 140.0,
    }
    max_image_ratio = max_image_ratio_by_type.get(defect_type, 0.08)
    max_bbox_ratio = max_bbox_ratio_by_type.get(defect_type, 60.0)
    image_ratio = mask_area / float(image_area)
    bbox_ratio = mask_area / float(label_area)
    if image_ratio > max_image_ratio:
        return False, "mask bbox covers %.3f of image; expected <= %.3f for %s" % (
            image_ratio,
            max_image_ratio,
            defect_type,
        )
    if bbox_ratio > max_bbox_ratio:
        return False, "mask bbox is %.1fx larger than label bbox" % bbox_ratio
    expansion = int(max(mask_box[2] - mask_box[0], mask_box[3] - mask_box[1], label_box[2] - label_box[0], label_box[3] - label_box[1]) * 0.5)
    label_context = expand_box(label_box, max(8, expansion), width, height)
    if not boxes_intersect(mask_box, label_context):
        return False, "mask bbox does not intersect expanded label bbox"
    return True, ""


def pixel_ratio_above(gray, threshold):
    hist = gray.histogram()
    total = sum(hist)
    if total <= 0:
        return 0.0
    return sum(hist[threshold + 1 :]) / float(total)


def edge_density(gray, threshold=24):
    edges = gray.filter(ImageFilter.FIND_EDGES)
    return pixel_ratio_above(edges, threshold)


def local_contrast(gray):
    blurred = gray.filter(ImageFilter.BoxBlur(5))
    diff = ImageChops_difference(gray, blurred)
    return ImageStat.Stat(diff).mean[0] / 255.0


def ImageChops_difference(a, b):
    # Local wrapper avoids importing ImageChops into older report code paths.
    from PIL import ImageChops

    return ImageChops.difference(a, b)


def compute_scene_metrics(image):
    gray = ImageOps.grayscale(resize_for_metrics(image))
    stat = ImageStat.Stat(gray)
    return {
        "scene_luma_mean": float(stat.mean[0]),
        "scene_luma_std": float(stat.stddev[0]),
        "scene_dark_ratio": pixel_ratio_above(ImageOps.invert(gray), 220),
        "scene_highlight_ratio": pixel_ratio_above(gray, 235),
        "scene_edge_density": edge_density(gray),
        "scene_local_contrast": local_contrast(gray),
    }


def compute_shape_metrics(defect_box, mask_pixel_count):
    x0, y0, x1, y1 = defect_box
    width = max(1, x1 - x0)
    height = max(1, y1 - y0)
    area = width * height
    short_side = max(1, min(width, height))
    long_side = max(width, height)
    aspect = width / float(height)
    elongation = long_side / float(short_side)
    compactness = mask_pixel_count / float(area) if mask_pixel_count else None
    return {
        "bbox_width_px": width,
        "bbox_height_px": height,
        "bbox_area_px": area,
        "bbox_aspect_ratio_px": aspect,
        "bbox_elongation_px": elongation,
        "mask_bbox_compactness": compactness,
        "vertical_elongation_ratio": height / float(width),
        "horizontal_elongation_ratio": width / float(height),
    }


def compute_defect_specific_metrics(defect_type, shape, contrast, visibility, edge_softness):
    compactness = shape.get("mask_bbox_compactness")
    elongation = shape.get("bbox_elongation_px") or 0.0
    vertical = shape.get("vertical_elongation_ratio") or 0.0
    horizontal = shape.get("horizontal_elongation_ratio") or 0.0
    metrics = {
        "defect_type": defect_type,
        "shape_compactness": compactness,
        "absolute_contrast": None if contrast is None else abs(float(contrast)),
        "visibility_proxy": visibility,
        "edge_softness_proxy": edge_softness,
    }
    if defect_type == "black_dot":
        metrics.update(
            {
                "roundness_proxy": min(shape["bbox_width_px"], shape["bbox_height_px"])
                / float(max(shape["bbox_width_px"], shape["bbox_height_px"])),
                "dark_defect_expected": True,
            }
        )
    elif defect_type == "foreign_material":
        metrics.update(
            {
                "rice_grain_size_px": shape["bbox_area_px"],
                "rice_grain_elongation": elongation,
                "attached_particle_proxy": compactness,
            }
        )
    elif defect_type == "splay":
        metrics.update(
            {
                "directional_streak_elongation": elongation,
                "vertical_streak_proxy": vertical,
                "horizontal_streak_proxy": horizontal,
                "low_contrast_flow_proxy": None if visibility is None else 1.0 - min(1.0, visibility / 0.25),
            }
        )
    elif defect_type == "mixed_color_contamination":
        metrics.update(
            {
                "soft_patch_compactness": compactness,
                "low_frequency_patch_proxy": None if edge_softness is None else edge_softness,
            }
        )
    return metrics


def gradient_mean(gray, box):
    x0, y0, x1, y1 = box
    if x1 - x0 < 2 or y1 - y0 < 2:
        return 0.0
    pix = gray.load()
    total = 0.0
    count = 0
    for y in range(y0, y1 - 1):
        for x in range(x0, x1 - 1):
            total += abs(float(pix[x + 1, y]) - float(pix[x, y]))
            total += abs(float(pix[x, y + 1]) - float(pix[x, y]))
            count += 2
    if count == 0:
        return 0.0
    return total / float(count)


def evaluate_local_defect(image_path, labels, source, defect_type="black_dot", mask_path=None):
    image = Image.open(image_path).convert("RGB")
    width, height = image.size
    label = labels[0]
    crop_box, bbox_px = crop_box_around_bbox(label, width, height)
    gray = ImageOps.grayscale(image)

    synthetic_mask_used = False
    mask_bbox_rejected = False
    mask_bbox_reject_reason = ""
    defect_box = bbox_px
    defect_values = []
    mask_pixel_count = 0
    mask_area_ratio = None
    if mask_path:
        mask = Image.open(mask_path).convert("L")
        if mask.size != image.size:
            mask = mask.resize(image.size, Image.NEAREST)
        mb = mask_bbox(mask)
        if mb:
            raw_mask_values = mask_values(gray, mask)
            mask_pixel_count = len(raw_mask_values)
            mask_area_ratio = mask_pixel_count / float(width * height)
            plausible, reason = mask_bbox_plausibility(mb, bbox_px, (width, height), defect_type)
            if plausible:
                defect_box = mb
                defect_values = raw_mask_values
                synthetic_mask_used = True
            else:
                mask_bbox_rejected = True
                mask_bbox_reject_reason = reason

    if not defect_values:
        defect_values = rect_values(gray, bbox_px)

    margin = max(8, int(max(bbox_px[2] - bbox_px[0], bbox_px[3] - bbox_px[1]) * 3))
    outer = expand_box(defect_box, margin, width, height)
    background_values = rect_ring_values(gray, defect_box, outer)
    defect_mean = mean_or_none(defect_values)
    background_mean = mean_or_none(background_values)
    defect_std = std_or_none(defect_values)
    background_std = std_or_none(background_values)
    if defect_mean is None or background_mean is None:
        contrast = None
        normalized_visibility = None
    else:
        contrast = float(background_mean - defect_mean)
        normalized_visibility = abs(contrast) / 255.0

    bbox_area_ratio = label["w"] * label["h"]

    edge_margin = max(2, int(max(defect_box[2] - defect_box[0], defect_box[3] - defect_box[1]) * 0.5))
    edge_box = expand_box(defect_box, edge_margin, width, height)
    edge_softness_proxy = gradient_mean(gray, edge_box) / 255.0
    scene_metrics = compute_scene_metrics(image)
    shape_metrics = compute_shape_metrics(defect_box, mask_pixel_count if synthetic_mask_used else len(defect_values))
    defect_specific = compute_defect_specific_metrics(
        defect_type,
        shape_metrics,
        contrast,
        normalized_visibility,
        edge_softness_proxy,
    )

    crop = image.crop(crop_box)
    draw = ImageDraw.Draw(crop)
    dx = crop_box[0]
    dy = crop_box[1]
    bx0, by0, bx1, by1 = bbox_px
    draw.rectangle((bx0 - dx, by0 - dy, bx1 - dx, by1 - dy), outline=(255, 0, 0), width=2)
    if synthetic_mask_used:
        mx0, my0, mx1, my1 = defect_box
        draw.rectangle((mx0 - dx, my0 - dy, mx1 - dx, my1 - dy), outline=(255, 255, 0), width=1)

    return {
        "source": source,
        "filename": image_path.name,
        "image_path": str(image_path),
        "label_path": "",
        "mask_path": str(mask_path) if mask_path else "",
        "width": width,
        "height": height,
        "bbox_x": label["x"],
        "bbox_y": label["y"],
        "bbox_w": label["w"],
        "bbox_h": label["h"],
        "bbox_area_ratio": bbox_area_ratio,
        "mask_area_ratio": mask_area_ratio,
        "defect_mean_gray": defect_mean,
        "defect_gray_std": defect_std,
        "background_mean_gray": background_mean,
        "background_gray_std": background_std,
        "defect_background_contrast": contrast,
        "normalized_visibility_proxy": normalized_visibility,
        "defect_darkness_proxy": None if defect_mean is None else 1.0 - defect_mean / 255.0,
        "edge_softness_proxy": edge_softness_proxy,
        "scene_quality": scene_metrics,
        "defect_shape": shape_metrics,
        "defect_specific": defect_specific,
        "mask_used": synthetic_mask_used,
        "mask_bbox_rejected": mask_bbox_rejected,
        "mask_bbox_reject_reason": mask_bbox_reject_reason,
        "crop": crop,
    }


def aggregate_metrics(rows):
    fields = [
        "bbox_area_ratio",
        "mask_area_ratio",
        "defect_mean_gray",
        "defect_gray_std",
        "background_mean_gray",
        "background_gray_std",
        "defect_background_contrast",
        "normalized_visibility_proxy",
        "defect_darkness_proxy",
        "edge_softness_proxy",
    ]
    result = {"count": len(rows)}
    for field in fields:
        values = [r[field] for r in rows if r.get(field) is not None]
        if not values:
            result[field] = {"mean": None, "std": None, "min": None, "max": None}
            continue
        result[field] = {
            "mean": float(sum(values)) / float(len(values)),
            "std": float(statistics.pstdev(values)) if len(values) > 1 else 0.0,
            "min": float(min(values)),
            "max": float(max(values)),
        }
    result["scene_quality"] = aggregate_nested_metrics(
        rows,
        "scene_quality",
        [
            "scene_luma_mean",
            "scene_luma_std",
            "scene_dark_ratio",
            "scene_highlight_ratio",
            "scene_edge_density",
            "scene_local_contrast",
        ],
    )
    result["defect_shape"] = aggregate_nested_metrics(
        rows,
        "defect_shape",
        [
            "bbox_width_px",
            "bbox_height_px",
            "bbox_area_px",
            "bbox_aspect_ratio_px",
            "bbox_elongation_px",
            "mask_bbox_compactness",
            "vertical_elongation_ratio",
            "horizontal_elongation_ratio",
        ],
    )
    result["defect_specific"] = aggregate_nested_metrics(
        rows,
        "defect_specific",
        [
            "shape_compactness",
            "absolute_contrast",
            "visibility_proxy",
            "edge_softness_proxy",
            "roundness_proxy",
            "rice_grain_size_px",
            "rice_grain_elongation",
            "attached_particle_proxy",
            "directional_streak_elongation",
            "vertical_streak_proxy",
            "horizontal_streak_proxy",
            "low_contrast_flow_proxy",
            "soft_patch_compactness",
            "low_frequency_patch_proxy",
        ],
    )
    return result


def aggregate_nested_metrics(rows, group_name, fields):
    result = {}
    for field in fields:
        values = []
        for row in rows:
            group = row.get(group_name) or {}
            value = group.get(field)
            if isinstance(value, (int, float)) and not math.isnan(float(value)):
                values.append(float(value))
        result[field] = summarize_distribution(values)
    return result


def summarize_distribution(values):
    if not values:
        return {"mean": None, "std": None, "min": None, "p05": None, "p50": None, "p95": None, "max": None}
    ordered = sorted(values)
    return {
        "mean": float(sum(ordered)) / float(len(ordered)),
        "std": float(statistics.pstdev(ordered)) if len(ordered) > 1 else 0.0,
        "min": float(ordered[0]),
        "p05": percentile(ordered, 0.05),
        "p50": percentile(ordered, 0.50),
        "p95": percentile(ordered, 0.95),
        "max": float(ordered[-1]),
    }


def percentile(sorted_values, fraction):
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = (len(sorted_values) - 1) * float(fraction)
    low = int(math.floor(pos))
    high = int(math.ceil(pos))
    if low == high:
        return float(sorted_values[low])
    weight = pos - low
    return float(sorted_values[low] * (1.0 - weight) + sorted_values[high] * weight)


def write_csv(rows, out_path):
    fieldnames = [
        "source",
        "filename",
        "image_path",
        "mask_path",
        "width",
        "height",
        "bbox_x",
        "bbox_y",
        "bbox_w",
        "bbox_h",
        "bbox_area_ratio",
        "mask_area_ratio",
        "defect_mean_gray",
        "defect_gray_std",
        "background_mean_gray",
        "background_gray_std",
        "defect_background_contrast",
        "normalized_visibility_proxy",
        "defect_darkness_proxy",
        "edge_softness_proxy",
        "scene_luma_mean",
        "scene_luma_std",
        "scene_dark_ratio",
        "scene_highlight_ratio",
        "scene_edge_density",
        "scene_local_contrast",
        "bbox_width_px",
        "bbox_height_px",
        "bbox_area_px",
        "bbox_aspect_ratio_px",
        "bbox_elongation_px",
        "mask_bbox_compactness",
        "vertical_elongation_ratio",
        "horizontal_elongation_ratio",
        "shape_compactness",
        "absolute_contrast",
        "roundness_proxy",
        "rice_grain_size_px",
        "rice_grain_elongation",
        "attached_particle_proxy",
        "directional_streak_elongation",
        "vertical_streak_proxy",
        "horizontal_streak_proxy",
        "low_contrast_flow_proxy",
        "soft_patch_compactness",
        "low_frequency_patch_proxy",
        "mask_used",
        "mask_bbox_rejected",
        "mask_bbox_reject_reason",
    ]
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            flat = dict(row)
            flat.update(row.get("scene_quality") or {})
            flat.update(row.get("defect_shape") or {})
            flat.update(row.get("defect_specific") or {})
            writer.writerow({key: flat.get(key, "") for key in fieldnames})


def make_contact_sheet(real_rows, synthetic_rows, out_path, max_rows=12):
    thumb = 220
    title_h = 36
    gap = 12
    rows = min(max_rows, max(len(real_rows), len(synthetic_rows)))
    if rows == 0:
        return None
    width = thumb * 2 + gap * 3
    height = rows * (thumb + title_h + gap) + gap
    canvas = Image.new("RGB", (width, height), (245, 245, 245))
    draw = ImageDraw.Draw(canvas)
    for i in range(rows):
        y = gap + i * (thumb + title_h + gap)
        for col, group, title in [
            (0, real_rows, "real"),
            (1, synthetic_rows, "synthetic"),
        ]:
            x = gap + col * (thumb + gap)
            if not group:
                continue
            row = group[i % len(group)]
            crop = row["crop"].copy()
            crop.thumbnail((thumb, thumb), image_resize_filter())
            tile = Image.new("RGB", (thumb, thumb), (255, 255, 255))
            tile.paste(crop, ((thumb - crop.size[0]) // 2, (thumb - crop.size[1]) // 2))
            canvas.paste(tile, (x, y + title_h))
            text = "%s %s vis=%.3f" % (
                title,
                row["filename"],
                row["normalized_visibility_proxy"] or 0.0,
            )
            draw.text((x, y), text[:34], fill=(20, 20, 20))
    canvas.save(out_path, quality=92)
    return out_path


REAL_DISTRIBUTION_FIELDS = [
    ("scene_quality", "scene_luma_mean"),
    ("scene_quality", "scene_luma_std"),
    ("scene_quality", "scene_edge_density"),
    ("scene_quality", "scene_local_contrast"),
    ("defect_shape", "bbox_area_px"),
    ("defect_shape", "bbox_elongation_px"),
    ("defect_shape", "mask_bbox_compactness"),
    ("defect_specific", "absolute_contrast"),
    ("defect_specific", "visibility_proxy"),
    ("defect_specific", "edge_softness_proxy"),
    ("defect_specific", "roundness_proxy"),
    ("defect_specific", "rice_grain_size_px"),
    ("defect_specific", "directional_streak_elongation"),
    ("defect_specific", "vertical_streak_proxy"),
    ("defect_specific", "low_contrast_flow_proxy"),
]


def build_real_distribution_profile(real_rows):
    profile = {"count": len(real_rows), "metrics": {}}
    for group, field in REAL_DISTRIBUTION_FIELDS:
        values = []
        for row in real_rows:
            value = (row.get(group) or {}).get(field)
            if isinstance(value, (int, float)) and not math.isnan(float(value)):
                values.append(float(value))
        if values:
            profile["metrics"]["%s.%s" % (group, field)] = summarize_distribution(values)
    return profile


def assess_synthetic_samples(synthetic_rows, real_profile, defect_type):
    sample_assessments = []
    status_counts = {"pass": 0, "warn": 0, "fail": 0}
    for row in synthetic_rows:
        findings = []
        status = "pass"
        if row.get("mask_area_ratio") in (None, 0):
            findings.append({"severity": "fail", "metric": "mask_area_ratio", "reason": "synthetic mask is empty"})
        if row.get("mask_bbox_rejected"):
            findings.append(
                {
                    "severity": "warn",
                    "metric": "mask_bbox",
                    "reason": row.get("mask_bbox_reject_reason") or "synthetic mask bbox was rejected",
                }
            )
        if row.get("normalized_visibility_proxy") is not None and row["normalized_visibility_proxy"] < 0.004:
            findings.append({"severity": "warn", "metric": "normalized_visibility_proxy", "reason": "defect may be too subtle in RGB"})
        shape = row.get("defect_shape") or {}
        specific = row.get("defect_specific") or {}
        if defect_type == "splay":
            if specific.get("directional_streak_elongation") is not None and specific["directional_streak_elongation"] < 2.0:
                findings.append({"severity": "warn", "metric": "directional_streak_elongation", "reason": "splay is not directional enough"})
        elif defect_type == "foreign_material":
            if shape.get("bbox_area_px") is not None and shape["bbox_area_px"] > 2500:
                findings.append({"severity": "warn", "metric": "bbox_area_px", "reason": "foreign material may exceed rice-grain scale"})
        elif defect_type == "black_dot":
            if specific.get("roundness_proxy") is not None and specific["roundness_proxy"] < 0.25:
                findings.append({"severity": "warn", "metric": "roundness_proxy", "reason": "black dot is highly elongated"})

        distribution_findings = compare_row_to_real_distribution(row, real_profile)
        findings.extend(distribution_findings)
        if any(item["severity"] == "fail" for item in findings):
            status = "fail"
        elif any(item["severity"] == "warn" for item in findings):
            status = "warn"
        status_counts[status] += 1
        sample_assessments.append(
            {
                "filename": row.get("filename"),
                "status": status,
                "findings": findings,
            }
        )
    return {
        "status_counts": status_counts,
        "samples": sample_assessments,
    }


def compare_row_to_real_distribution(row, real_profile):
    findings = []
    metrics = (real_profile or {}).get("metrics") or {}
    if not metrics:
        return findings
    for group, field in REAL_DISTRIBUTION_FIELDS:
        profile_key = "%s.%s" % (group, field)
        dist = metrics.get(profile_key)
        if not dist or dist.get("p05") is None or dist.get("p95") is None:
            continue
        value = (row.get(group) or {}).get(field)
        if not isinstance(value, (int, float)):
            continue
        low, high = expanded_interval(dist["p05"], dist["p95"], dist["std"])
        if value < low or value > high:
            findings.append(
                {
                    "severity": "warn",
                    "metric": profile_key,
                    "value": float(value),
                    "expected_low": low,
                    "expected_high": high,
                    "reason": "outside expanded real-reference distribution",
                }
            )
    return findings


def expanded_interval(p05, p95, std):
    spread = max(float(p95) - float(p05), float(std or 0.0), 1e-6)
    return float(p05) - spread * 0.35, float(p95) + spread * 0.35


def write_report(out_path, args, summary):
    real = summary.get("real_metrics", {})
    synth = summary.get("synthetic_metrics", {})
    lines = []
    lines.append("# Defect Realism Evaluation Report")
    lines.append("")
    lines.append("## Purpose")
    lines.append("")
    lines.append(
        "This report checks image-level and defect-level realism proxies only. It does not run YOLO and does not prove detector improvement."
    )
    lines.append("")
    lines.append("## Inputs")
    lines.append("")
    lines.append("- Defect type: `%s`" % args.defect_type)
    if args.real_images:
        lines.append("- Real images: `%s`" % args.real_images)
    if args.real_labels:
        lines.append("- Real labels: `%s`" % args.real_labels)
    if args.real_manifest:
        lines.append("- Real manifest: `%s`" % args.real_manifest)
    if getattr(args, "real_model", None):
        lines.append("- Real model filter: `%s`" % args.real_model)
    if getattr(args, "real_color", None):
        lines.append("- Real color filter: `%s`" % args.real_color)
    if args.synthetic_dataset:
        lines.append("- Synthetic dataset: `%s`" % args.synthetic_dataset)
    if args.scan_real_root:
        lines.append("- Real dataset root scan: `%s`" % args.scan_real_root)
    lines.append("")
    lines.append("## Counts")
    lines.append("")
    lines.append("| Source | evaluated defect crops |")
    lines.append("| --- | ---: |")
    lines.append("| real | %s |" % real.get("count", 0))
    lines.append("| synthetic | %s |" % synth.get("count", 0))
    lines.append("")
    lines.append("## Key Metrics")
    lines.append("")
    lines.append("| Metric | Real mean | Synthetic mean |")
    lines.append("| --- | ---: | ---: |")
    for key in [
        "bbox_area_ratio",
        "mask_area_ratio",
        "defect_mean_gray",
        "background_mean_gray",
        "defect_background_contrast",
        "normalized_visibility_proxy",
        "defect_darkness_proxy",
        "edge_softness_proxy",
    ]:
        rv = real.get(key, {}).get("mean")
        sv = synth.get(key, {}).get("mean")
        lines.append("| `%s` | %s | %s |" % (key, fmt_num(rv), fmt_num(sv)))
    lines.append("")
    lines.append("## Three-Layer Realism Proxies")
    lines.append("")
    lines.append("| Layer | Metric | Real mean | Synthetic mean |")
    lines.append("| --- | --- | ---: | ---: |")
    for group, field in [
        ("scene_quality", "scene_luma_mean"),
        ("scene_quality", "scene_edge_density"),
        ("scene_quality", "scene_local_contrast"),
        ("defect_shape", "bbox_area_px"),
        ("defect_shape", "bbox_elongation_px"),
        ("defect_specific", "absolute_contrast"),
        ("defect_specific", "visibility_proxy"),
        ("defect_specific", "edge_softness_proxy"),
    ]:
        rv = ((real.get(group) or {}).get(field) or {}).get("mean")
        sv = ((synth.get(group) or {}).get(field) or {}).get("mean")
        lines.append("| `%s` | `%s` | %s | %s |" % (group, field, fmt_num(rv), fmt_num(sv)))
    assessment = summary.get("synthetic_assessment", {})
    if assessment:
        counts = assessment.get("status_counts", {})
        lines.append("")
        lines.append("## Synthetic Assessment")
        lines.append("")
        lines.append("- Pass: `%s`" % counts.get("pass", 0))
        lines.append("- Warn: `%s`" % counts.get("warn", 0))
        lines.append("- Fail: `%s`" % counts.get("fail", 0))
        for sample in assessment.get("samples", [])[:8]:
            if sample.get("findings"):
                reasons = "; ".join(item.get("reason", "") for item in sample["findings"][:3])
                lines.append("- `%s`: `%s` - %s" % (sample.get("filename"), sample.get("status"), reasons))
    lines.append("")
    lines.append("## Initial Diagnosis")
    lines.append("")
    lines.append("- Labels are used for localization/cropping only; visual crop review remains required.")
    lines.append("- For black dots, useful warning signs are excessive darkness, overly hard edges, unrealistic size, and poor local background context.")
    lines.append("- For foreign material, useful warning signs are over-large particles, unrealistic elongation, and weak contact context.")
    lines.append("- For splay, useful warning signs are low directionality, excessive contrast, or mask/RGB mismatch.")
    lines.append("")
    lines.append("## Visual Output")
    lines.append("")
    lines.append("- Contact sheet: `%s`" % summary.get("visual_outputs", {}).get("contact_sheet", ""))
    lines.append("")
    lines.append("## Limitations")
    lines.append("")
    lines.append("- This is not a physical realism metric.")
    lines.append("- This is not proof of detection performance.")
    lines.append("- Real labels may be loose bounding boxes, so crop metrics should be interpreted together with actual images.")
    lines.append("- Distribution checks need enough localized real samples to be stable.")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def fmt_num(value):
    if value is None:
        return "-"
    return "%.6f" % value


def run_scan_only(args, out_dir):
    profile = scan_real_dataset_root(resolve_path(args.scan_real_root))
    summary = {
        "schema_version": SCHEMA_VERSION,
        "evaluation_type": "real_dataset_profile_scan",
        "real_dataset_profile": profile,
    }
    (out_dir / "real_dataset_profile_manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def evaluate(args):
    out_dir = ensure_dir(resolve_path(args.out))
    real_rows = []
    synthetic_rows = []
    real_dataset_profile = None

    if args.scan_real_root:
        real_dataset_profile = scan_real_dataset_root(resolve_path(args.scan_real_root))
        (out_dir / "real_dataset_profile_manifest.json").write_text(
            json.dumps(real_dataset_profile, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if args.real_manifest:
        real_pairs = iter_manifest_label_pairs(
            resolve_path(args.real_manifest),
            defect_type=args.defect_type,
            model=args.real_model,
            color=args.real_color,
            max_samples=args.max_samples,
        )
        for image_path, label_path, labels in real_pairs:
            row = evaluate_local_defect(image_path, labels, "real", defect_type=args.defect_type)
            row["label_path"] = str(label_path)
            real_rows.append(row)

    if args.real_images and args.real_labels:
        real_pairs = iter_image_label_pairs(
            resolve_path(args.real_images),
            resolve_path(args.real_labels),
            max_samples=args.max_samples,
            only_non_empty=True,
        )
        for image_path, label_path, labels in real_pairs:
            row = evaluate_local_defect(image_path, labels, "real", defect_type=args.defect_type)
            row["label_path"] = str(label_path)
            real_rows.append(row)

    if args.synthetic_dataset:
        synth_pairs = iter_synthetic_pairs(resolve_path(args.synthetic_dataset), max_samples=args.max_samples)
        for image_path, label_path, mask_path, labels in synth_pairs:
            row = evaluate_local_defect(image_path, labels, "synthetic", defect_type=args.defect_type, mask_path=mask_path)
            row["label_path"] = str(label_path)
            synthetic_rows.append(row)

    all_rows = real_rows + synthetic_rows
    write_csv(all_rows, out_dir / "defect_realism_per_sample.csv")
    contact_sheet = make_contact_sheet(real_rows, synthetic_rows, out_dir / "real_vs_synthetic_defect_crops.jpg")
    real_distribution_profile = build_real_distribution_profile(real_rows)
    synthetic_assessment = assess_synthetic_samples(synthetic_rows, real_distribution_profile, args.defect_type)

    summary = {
        "schema_version": SCHEMA_VERSION,
        "evaluation_type": "defect_realism",
        "defect_type": args.defect_type,
        "real_dataset_profile": real_dataset_profile,
        "inputs": {
            "real_images": str(resolve_path(args.real_images)) if args.real_images else None,
            "real_labels": str(resolve_path(args.real_labels)) if args.real_labels else None,
            "real_manifest": str(resolve_path(args.real_manifest)) if args.real_manifest else None,
            "real_model": args.real_model,
            "real_color": args.real_color,
            "synthetic_dataset": str(resolve_path(args.synthetic_dataset)) if args.synthetic_dataset else None,
            "scan_real_root": str(resolve_path(args.scan_real_root)) if args.scan_real_root else None,
        },
        "real_metrics": aggregate_metrics(real_rows),
        "synthetic_metrics": aggregate_metrics(synthetic_rows),
        "real_distribution_profile": real_distribution_profile,
        "synthetic_assessment": synthetic_assessment,
        "visual_outputs": {
            "contact_sheet": str(contact_sheet) if contact_sheet else None,
        },
        "limitations": [
            "Diagnostic image-level proxies only; no YOLO is run.",
            "Labels are used as crop hints, not as a substitute for visual inspection.",
            "Distribution checks need enough real localized samples to be stable.",
        ],
    }
    (out_dir / "defect_realism_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_report(out_dir / "DEFECT_REALISM_REPORT.md", args, summary)
    return summary


def build_arg_parser():
    parser = argparse.ArgumentParser(description="Evaluate synthetic defect realism without YOLO.")
    parser.add_argument("--scan-real-root", default=None, help="Optional reorganized real dataset root to scan.")
    parser.add_argument("--defect-type", default="black_dot", help="Canonical defect type. First adapter: black_dot.")
    parser.add_argument("--real-manifest", default=None, help="CSV with image_path, label_path, and defect_type columns.")
    parser.add_argument("--real-model", default=None, help="Optional model filter for --real-manifest.")
    parser.add_argument("--real-color", default=None, help="Optional color filter for --real-manifest.")
    parser.add_argument("--real-images", default=None, help="Real image folder.")
    parser.add_argument("--real-labels", default=None, help="YOLO label folder for real images.")
    parser.add_argument("--synthetic-dataset", default=None, help="Synthetic dataset folder with rgb/masks/labels_yolo.")
    parser.add_argument("--max-samples", type=int, default=12, help="Maximum defect samples per source.")
    parser.add_argument("--out", required=True, help="Output folder.")
    return parser


def main():
    parser = build_arg_parser()
    args = parser.parse_args()
    out_dir = ensure_dir(resolve_path(args.out))
    if args.scan_real_root and not (args.real_images or args.synthetic_dataset):
        run_scan_only(args, out_dir)
        print("Wrote real dataset profile scan to %s" % out_dir)
        return
    summary = evaluate(args)
    print("Wrote defect realism evaluation to %s" % out_dir)
    print("Real crops: %s" % summary["real_metrics"]["count"])
    print("Synthetic crops: %s" % summary["synthetic_metrics"]["count"])


if __name__ == "__main__":
    main()
