from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat


DEFAULT_WEIGHTS = {
    "brightness": 0.25,
    "color_histogram": 0.30,
    "ssim": 0.25,
    "edge_texture": 0.20,
    "lpips": 0.0,
}

PLASTIC_MATERIAL_WEIGHTS = {
    "brightness_similarity": 0.25,
    "color_similarity": 0.30,
    "local_contrast_similarity": 0.15,
    "highlight_similarity": 0.15,
    "texture_similarity": 0.10,
    "ssim_similarity": 0.05,
}


def compare_images(
    reference_image,
    candidate_image,
    roi_mode="center",
    roi_box=None,
    roi_mask=None,
    resize=512,
    weights=None,
    score_profile="baseline",
):
    reference_path = Path(reference_image)
    candidate_path = Path(candidate_image)
    if not reference_path.exists():
        raise FileNotFoundError("Reference image not found: {0}".format(reference_path))
    if not candidate_path.exists():
        raise FileNotFoundError("Candidate image not found: {0}".format(candidate_path))
    mask_path = Path(roi_mask) if roi_mask is not None else None
    if roi_mode not in {"full", "center", "auto", "manual", "mask"}:
        raise ValueError("roi_mode must be one of: full, center, auto, manual, mask")
    if roi_mode == "manual" and roi_box is None:
        raise ValueError("roi_box is required when roi_mode is manual")
    if roi_mode != "manual" and roi_box is not None:
        raise ValueError("roi_box can only be used when roi_mode is manual")
    if roi_mode == "mask" and mask_path is None:
        raise ValueError("roi_mask is required when roi_mode is mask")
    if roi_mode != "mask" and mask_path is not None:
        raise ValueError("roi_mask can only be used when roi_mode is mask")
    if mask_path is not None and not mask_path.exists():
        raise FileNotFoundError("ROI mask not found: {0}".format(mask_path))
    if int(resize) < 8:
        raise ValueError("resize must be >= 8")
    if score_profile not in {"baseline", "plastic_material"}:
        raise ValueError("score_profile must be one of: baseline, plastic_material")

    notes = []
    if score_profile == "plastic_material":
        if roi_mode == "full":
            notes.append("plastic_material score should be used with clean material ROI; full-image scoring may be dominated by background.")
        elif roi_mode not in {"manual", "mask"}:
            notes.append("plastic_material score is designed for clean material ROI; manual ROI is strongly recommended.")
    ref_original = _open_rgb(reference_path)
    cand_original = _open_rgb(candidate_path)
    mask_info = None
    ref_mask_roi = None
    cand_mask_roi = None
    if roi_mode == "mask":
        mask_info = _prepare_mask_roi(mask_path, ref_original, cand_original)
        ref_roi_box = mask_info["reference_roi_box"]
        cand_roi_box = mask_info["candidate_roi_box"]
        ref_mask_roi = mask_info["reference_mask"].crop(ref_roi_box)
        cand_mask_roi = mask_info["candidate_mask"].crop(cand_roi_box)
    else:
        ref_roi_box = _select_roi(ref_original, roi_mode, notes, "reference", roi_box=roi_box)
        cand_roi_box = _select_roi(
            cand_original,
            roi_mode,
            notes,
            "candidate",
            roi_box=roi_box,
            source_size=ref_original.size,
        )

    ref_roi = ref_original.crop(ref_roi_box)
    cand_roi = cand_original.crop(cand_roi_box)
    comparison_size = (int(resize), int(resize))
    ref_cmp = ref_roi.resize(comparison_size, Image.BILINEAR)
    cand_cmp = cand_roi.resize(comparison_size, Image.BILINEAR)
    comparison_mask = None
    comparison_mask_count = None
    if roi_mode == "mask":
        ref_cmp_mask = ref_mask_roi.resize(comparison_size, Image.NEAREST)
        cand_cmp_mask = cand_mask_roi.resize(comparison_size, Image.NEAREST)
        comparison_mask = _intersect_masks(ref_cmp_mask, cand_cmp_mask)
        comparison_mask_count = _mask_pixel_count(comparison_mask)
        if comparison_mask_count <= 0:
            raise ValueError("ROI mask has no positive pixels after resizing/cropping.")

    if score_profile == "baseline":
        metric_values = {
            "brightness": _brightness_similarity(ref_cmp, cand_cmp, comparison_mask),
            "color_histogram": _color_histogram_similarity(ref_cmp, cand_cmp, mask=comparison_mask),
            "ssim": _global_ssim(ref_cmp, cand_cmp, comparison_mask),
            "edge_texture": _edge_texture_similarity(ref_cmp, cand_cmp, comparison_mask),
            "lpips": None,
        }
        normalized_weights = _normalize_weights(weights or DEFAULT_WEIGHTS)
        weighted_score = _weighted_score(metric_values, normalized_weights)
        components = dict(metric_values)
    else:
        metric_values = _plastic_material_components(ref_cmp, cand_cmp, comparison_mask)
        normalized_weights = _normalize_weights(weights or PLASTIC_MATERIAL_WEIGHTS, defaults=PLASTIC_MATERIAL_WEIGHTS)
        weighted_score = _weighted_score(metric_values, normalized_weights)
        components = dict(metric_values)
    return {
        "schema_version": "0.2",
        "metric_backend": "pillow_baseline",
        "score_profile": score_profile,
        "reference_image": str(reference_path),
        "candidate_image": str(candidate_path),
        "preprocessing": {
            "roi_mode": roi_mode,
            "resize": int(resize),
            "reference_original_size": list(ref_original.size),
            "candidate_original_size": list(cand_original.size),
            "reference_roi_box": list(ref_roi_box),
            "candidate_roi_box": list(cand_roi_box),
            "manual_roi_box_xywh": list(roi_box) if roi_box is not None else None,
            "roi_mask": str(mask_path) if mask_path else None,
            "reference_mask_pixel_count": mask_info["reference_mask_pixel_count"] if mask_info else None,
            "candidate_mask_pixel_count": mask_info["candidate_mask_pixel_count"] if mask_info else None,
            "comparison_mask_pixel_count": comparison_mask_count,
            "comparison_size": list(comparison_size),
        },
        "metrics": {key: _round_or_none(value) for key, value in metric_values.items()},
        "components": {key: _round_or_none(value) for key, value in components.items()},
        "weights": normalized_weights,
        "weighted_score": round(weighted_score, 6),
        "notes": notes,
    }


def mock_similarity_score(reference_image: Path, candidate_params: dict) -> dict:
    """Compatibility placeholder used by material_fitter until render candidates exist."""
    token = "{0}|{1}".format(reference_image.name, candidate_params).encode("utf-8")
    checksum = sum(token) % 1000
    brightness = 1.0 - abs((checksum % 100) - 50) / 100.0
    color_histogram = 1.0 - abs(((checksum // 3) % 100) - 50) / 110.0
    ssim = 0.55 + ((checksum // 7) % 35) / 100.0
    edge_texture = 0.50 + ((checksum // 11) % 30) / 100.0
    weighted = (
        0.25 * brightness
        + 0.25 * color_histogram
        + 0.30 * ssim
        + 0.20 * edge_texture
    )
    return {
        "brightness": round(brightness, 4),
        "color_histogram": round(color_histogram, 4),
        "ssim": round(ssim, 4),
        "edge_texture": round(edge_texture, 4),
        "lpips": None,
        "weighted_score": round(weighted, 4),
        "metric_backend": "mock",
    }


def _open_rgb(path):
    image = Image.open(str(path))
    image = ImageOps.exif_transpose(image)
    return image.convert("RGB")


def parse_roi_box(value):
    if value is None:
        return None
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
    else:
        parts = list(value)
    if len(parts) != 4:
        raise ValueError("roi_box must have four values: x,y,w,h")
    try:
        x, y, width, height = [int(round(float(part))) for part in parts]
    except Exception as exc:
        raise ValueError("roi_box values must be numeric: x,y,w,h") from exc
    if x < 0 or y < 0:
        raise ValueError("roi_box x and y must be >= 0")
    if width <= 0 or height <= 0:
        raise ValueError("roi_box width and height must be > 0")
    return (x, y, width, height)


def _select_roi(image, roi_mode, notes, label, roi_box=None, source_size=None):
    width, height = image.size
    if roi_mode == "full":
        return (0, 0, width, height)
    if roi_mode == "center":
        return _center_roi(width, height)
    if roi_mode == "manual":
        return _manual_roi(width, height, roi_box, source_size)
    auto = _auto_foreground_roi(image)
    if auto is None:
        notes.append("{0}_auto_roi_fallback_to_center".format(label))
        return _center_roi(width, height)
    return auto


def _center_roi(width, height):
    margin_x = int(round(width * 0.15))
    margin_y = int(round(height * 0.15))
    return (margin_x, margin_y, width - margin_x, height - margin_y)


def _manual_roi(width, height, roi_box, source_size=None):
    x, y, box_width, box_height = parse_roi_box(roi_box)
    if source_size is not None:
        source_width, source_height = source_size
        if source_width <= 0 or source_height <= 0:
            raise ValueError("source image size for manual ROI must be positive")
        scale_x = width / float(source_width)
        scale_y = height / float(source_height)
        x = int(round(x * scale_x))
        y = int(round(y * scale_y))
        box_width = int(round(box_width * scale_x))
        box_height = int(round(box_height * scale_y))
        box_width = max(1, box_width)
        box_height = max(1, box_height)
    right = x + box_width
    bottom = y + box_height
    if x >= width or y >= height or right > width or bottom > height:
        raise ValueError(
            "manual roi_box x,y,w,h is outside image bounds: "
            "{0},{1},{2},{3} for image size {4}x{5}".format(x, y, box_width, box_height, width, height)
        )
    return (x, y, right, bottom)


def _prepare_mask_roi(mask_path, ref_image, cand_image):
    mask = _open_mask(mask_path)
    if mask.size != ref_image.size:
        mask = mask.resize(ref_image.size, Image.NEAREST)
    ref_box = _mask_bbox(mask)
    if ref_box is None:
        raise ValueError("ROI mask has no positive pixels: {0}".format(mask_path))
    cand_mask = mask.resize(cand_image.size, Image.NEAREST)
    cand_box = _mask_bbox(cand_mask)
    if cand_box is None:
        raise ValueError("ROI mask has no positive pixels after resizing to candidate image.")
    return {
        "reference_mask": mask,
        "candidate_mask": cand_mask,
        "reference_roi_box": ref_box,
        "candidate_roi_box": cand_box,
        "reference_mask_pixel_count": _mask_pixel_count(mask),
        "candidate_mask_pixel_count": _mask_pixel_count(cand_mask),
    }


def _open_mask(mask_path):
    mask = Image.open(str(mask_path))
    mask = ImageOps.exif_transpose(mask)
    return mask.convert("L").point(lambda value: 255 if value > 0 else 0)


def _mask_bbox(mask):
    return mask.getbbox()


def _mask_pixel_count(mask):
    if mask is None:
        return None
    return sum(1 for value in mask.getdata() if value > 0)


def _intersect_masks(mask_a, mask_b):
    return ImageChops.multiply(mask_a.convert("L"), mask_b.convert("L")).point(lambda value: 255 if value > 0 else 0)


def _auto_foreground_roi(image):
    small = image.resize((128, 128), Image.BILINEAR)
    width, height = small.size
    corners = [
        small.getpixel((0, 0)),
        small.getpixel((width - 1, 0)),
        small.getpixel((0, height - 1)),
        small.getpixel((width - 1, height - 1)),
    ]
    bg = tuple(sum(pixel[channel] for pixel in corners) / 4.0 for channel in range(3))
    xs = []
    ys = []
    threshold = 24.0
    for y in range(height):
        for x in range(width):
            pixel = small.getpixel((x, y))
            diff = sum(abs(pixel[channel] - bg[channel]) for channel in range(3)) / 3.0
            if diff >= threshold:
                xs.append(x)
                ys.append(y)
    if len(xs) < width * height * 0.02:
        return None
    pad = 6
    min_x = max(0, min(xs) - pad)
    max_x = min(width - 1, max(xs) + pad)
    min_y = max(0, min(ys) - pad)
    max_y = min(height - 1, max(ys) + pad)
    scale_x = image.size[0] / float(width)
    scale_y = image.size[1] / float(height)
    box = (
        int(min_x * scale_x),
        int(min_y * scale_y),
        int((max_x + 1) * scale_x),
        int((max_y + 1) * scale_y),
    )
    if box[2] <= box[0] or box[3] <= box[1]:
        return None
    return box


def _brightness_similarity(ref, cand, mask=None):
    ref_mean = _masked_mean(_gray_values(ref, mask))
    cand_mean = _masked_mean(_gray_values(cand, mask))
    return _clamp01(1.0 - abs(ref_mean - cand_mean) / 255.0)


def _color_histogram_similarity(ref, cand, bins=32, mask=None):
    scores = []
    for channel in range(3):
        ref_hist = _channel_histogram(ref, channel, bins, mask)
        cand_hist = _channel_histogram(cand, channel, bins, mask)
        distance = sum(abs(a - b) for a, b in zip(ref_hist, cand_hist))
        scores.append(_clamp01(1.0 - 0.5 * distance))
    return sum(scores) / float(len(scores))


def _channel_histogram(image, channel, bins, mask=None):
    hist = [0] * bins
    pixels = _rgb_values(image, mask)
    bin_size = 256.0 / float(bins)
    for pixel in pixels:
        index = int(pixel[channel] / bin_size)
        if index >= bins:
            index = bins - 1
        hist[index] += 1
    total = float(len(pixels))
    if total <= 0:
        raise ValueError("ROI mask has no positive pixels for histogram calculation.")
    return [value / total for value in hist]


def _global_ssim(ref, cand, mask=None):
    ref_values = _gray_values(ref, mask)
    cand_values = _gray_values(cand, mask)
    count = float(len(ref_values))
    if count <= 1:
        return 0.0
    mu_x = sum(ref_values) / count
    mu_y = sum(cand_values) / count
    var_x = sum((value - mu_x) ** 2 for value in ref_values) / (count - 1.0)
    var_y = sum((value - mu_y) ** 2 for value in cand_values) / (count - 1.0)
    cov_xy = sum((x - mu_x) * (y - mu_y) for x, y in zip(ref_values, cand_values)) / (count - 1.0)
    c1 = (0.01 * 255.0) ** 2
    c2 = (0.03 * 255.0) ** 2
    denominator = ((mu_x ** 2 + mu_y ** 2 + c1) * (var_x + var_y + c2))
    if denominator == 0.0:
        return 1.0 if ref_values == cand_values else 0.0
    score = ((2.0 * mu_x * mu_y + c1) * (2.0 * cov_xy + c2)) / denominator
    return _clamp01(score)


def _edge_texture_similarity(ref, cand, mask=None):
    ref_edge = ref.convert("L").filter(ImageFilter.FIND_EDGES)
    cand_edge = cand.convert("L").filter(ImageFilter.FIND_EDGES)
    diff = ImageChops.difference(ref_edge, cand_edge)
    mean_diff = _masked_mean(_gray_values(diff, mask))
    return _clamp01(1.0 - mean_diff / 255.0)


def _plastic_material_components(ref, cand, mask=None):
    return {
        "brightness_similarity": _brightness_similarity(ref, cand, mask),
        "color_similarity": _mean_rgb_similarity(ref, cand, mask),
        "local_contrast_similarity": _local_contrast_similarity(ref, cand, mask),
        "highlight_similarity": _highlight_similarity(ref, cand, mask),
        "texture_similarity": _texture_similarity(ref, cand, mask),
        "ssim_similarity": _global_ssim(ref, cand, mask),
    }


def _mean_rgb_similarity(ref, cand, mask=None):
    ref_mean = _masked_rgb_mean(ref, mask)
    cand_mean = _masked_rgb_mean(cand, mask)
    distance = sum(abs(a - b) / 255.0 for a, b in zip(ref_mean[:3], cand_mean[:3])) / 3.0
    return _clamp01(1.0 - distance)


def _local_contrast_similarity(ref, cand, mask=None):
    ref_std = _masked_std(_gray_values(ref, mask)) / 128.0
    cand_std = _masked_std(_gray_values(cand, mask)) / 128.0
    return _clamp01(1.0 - min(1.0, abs(ref_std - cand_std)))


def _highlight_similarity(ref, cand, mask=None):
    ref_stats = _highlight_stats(ref, mask)
    cand_stats = _highlight_stats(cand, mask)
    ratio_similarity = _clamp01(1.0 - min(1.0, abs(ref_stats["ratio"] - cand_stats["ratio"]) / 0.25))
    intensity_similarity = _clamp01(1.0 - abs(ref_stats["intensity"] - cand_stats["intensity"]))
    return _clamp01(0.6 * ratio_similarity + 0.4 * intensity_similarity)


def _highlight_stats(image, mask=None):
    values = _gray_values(image, mask)
    if not values:
        return {"ratio": 0.0, "intensity": 0.0}
    sorted_values = sorted(values)
    percentile_index = int(round((len(sorted_values) - 1) * 0.90))
    threshold = max(220, sorted_values[percentile_index])
    highlight_values = [value for value in values if value >= threshold]
    if not highlight_values:
        return {"ratio": 0.0, "intensity": 0.0}
    return {
        "ratio": len(highlight_values) / float(len(values)),
        "intensity": (sum(highlight_values) / float(len(highlight_values))) / 255.0,
    }


def _texture_similarity(ref, cand, mask=None):
    ref_texture = _texture_stat(ref, mask)
    cand_texture = _texture_stat(cand, mask)
    return _clamp01(1.0 - min(1.0, abs(ref_texture - cand_texture) / 0.25))


def _texture_stat(image, mask=None):
    edge = image.convert("L").filter(ImageFilter.FIND_EDGES)
    return _masked_mean(_gray_values(edge, mask)) / 255.0


def _gray_values(image, mask=None):
    values = list(image.convert("L").getdata())
    if mask is None:
        return values
    mask_values = list(mask.convert("L").getdata())
    selected = [value for value, mask_value in zip(values, mask_values) if mask_value > 0]
    if not selected:
        raise ValueError("ROI mask has no positive pixels for metric calculation.")
    return selected


def _rgb_values(image, mask=None):
    pixels = list(image.convert("RGB").getdata())
    if mask is None:
        return pixels
    mask_values = list(mask.convert("L").getdata())
    selected = [pixel for pixel, mask_value in zip(pixels, mask_values) if mask_value > 0]
    if not selected:
        raise ValueError("ROI mask has no positive pixels for RGB metric calculation.")
    return selected


def _masked_mean(values):
    if not values:
        raise ValueError("Cannot compute mean for empty ROI.")
    return sum(values) / float(len(values))


def _masked_std(values):
    if not values:
        raise ValueError("Cannot compute standard deviation for empty ROI.")
    mean = _masked_mean(values)
    variance = sum((value - mean) ** 2 for value in values) / float(len(values))
    return variance ** 0.5


def _masked_rgb_mean(image, mask=None):
    pixels = _rgb_values(image, mask)
    count = float(len(pixels))
    return [sum(pixel[channel] for pixel in pixels) / count for channel in range(3)]


def _normalize_weights(weights, defaults=None):
    merged = dict(defaults or DEFAULT_WEIGHTS)
    merged.update(weights)
    active = {}
    for key, value in merged.items():
        if value is None:
            continue
        value = float(value)
        if value < 0.0:
            raise ValueError("Metric weights must be non-negative.")
        active[key] = value
    total = sum(active.values())
    if total <= 0.0:
        raise ValueError("At least one metric weight must be positive.")
    return {key: round(value / total, 6) for key, value in active.items()}


def _weighted_score(metrics, weights):
    score = 0.0
    used_weight = 0.0
    for key, weight in weights.items():
        value = metrics.get(key)
        if value is None:
            continue
        score += float(value) * float(weight)
        used_weight += float(weight)
    if used_weight <= 0.0:
        return 0.0
    return _clamp01(score / used_weight)


def _round_or_none(value):
    if value is None:
        return None
    return round(float(value), 6)


def _clamp01(value):
    return max(0.0, min(1.0, float(value)))
