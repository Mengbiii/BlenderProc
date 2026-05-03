# Similarity Metrics Plan

## 1. Goal Definition

Build a stable image-comparison module for material fitting. The module should compare a real reference image and a rendered candidate image, then return interpretable per-metric scores plus one weighted score.

The first implementation must be lightweight and runnable in the current project environment. It uses Pillow and the Python standard library only. LPIPS is planned as an optional future metric and must not be required for the baseline path.

## 2. Input / Output Specification

### Inputs

- `reference_image`: real reference image path.
- `candidate_image`: rendered candidate image path.
- `roi_mode`: one of:
  - `full`
  - `center`
  - `auto`
- `resize`: comparison size in pixels for the longest side or square normalization. Default: `512`.
- optional `weights`: metric weights.

### Outputs

- Per-metric score in the range `0.0` to `1.0`, where higher means more similar.
- Weighted overall score in the range `0.0` to `1.0`.
- Preprocessing metadata.
- ROI metadata.
- Optional failure fields if an image cannot be read or compared.

## 3. Metric Definitions And Formulas

All baseline metrics operate after RGB conversion, ROI extraction, and resizing.

### Brightness Similarity

Convert RGB to luma:

```text
Y = 0.299R + 0.587G + 0.114B
```

Let `mean_ref` and `mean_cand` be the mean luma values in `[0, 255]`.

```text
brightness_similarity = 1 - abs(mean_ref - mean_cand) / 255
```

Clamp to `[0, 1]`.

### Color Histogram Similarity

Build per-channel RGB histograms with `32` bins per channel. Normalize each histogram so it sums to `1`.

For each channel:

```text
channel_similarity = 1 - 0.5 * sum(abs(hist_ref[i] - hist_cand[i]))
```

Average over the three channels:

```text
color_histogram_similarity = mean(R_sim, G_sim, B_sim)
```

### Global SSIM Approximation

Use grayscale luma and compute global statistics:

```text
SSIM = ((2 * mu_x * mu_y + C1) * (2 * cov_xy + C2)) /
       ((mu_x^2 + mu_y^2 + C1) * (var_x + var_y + C2))
```

Constants:

```text
C1 = (0.01 * 255)^2
C2 = (0.03 * 255)^2
```

Clamp the final result to `[0, 1]`.

This is not a full windowed SSIM implementation, but is deterministic, dependency-light, and good enough for early material-fitting ranking.

### Edge / Texture Similarity

Compute edge maps using Pillow's `FIND_EDGES` filter on grayscale images. Compare mean absolute edge difference:

```text
edge_texture_similarity = 1 - mean(abs(edge_ref - edge_cand)) / 255
```

Clamp to `[0, 1]`.

### Optional LPIPS

LPIPS is not part of the first implementation. Future behavior:

- If LPIPS is installed and enabled, compute perceptual distance.
- Convert distance to similarity with a bounded transform.
- If LPIPS is unavailable, record `lpips: null`.

## 4. Image Preprocessing Rules

1. Open images with Pillow.
2. Apply EXIF orientation if available.
3. Convert to RGB.
4. Extract ROI according to `roi_mode`.
5. Resize both images to the same comparison size.
6. Use bilinear interpolation for metric inputs.
7. Keep all computations deterministic.

Default resize rule:

```text
resize both ROI images to resize x resize
```

This avoids shape mismatch and keeps runtime predictable.

## 5. ROI Strategy And Reasoning

Material fitting should not overfit to unrelated background. However, early renders may not have reliable masks. Therefore the first implementation supports three ROI modes:

| ROI mode | Behavior | Use case |
| --- | --- | --- |
| `full` | Compare the whole image. | Debugging and simple screenshots. |
| `center` | Compare the central 70% crop. | Product usually centered; avoids borders/background. |
| `auto` | Estimate foreground by detecting pixels sufficiently different from corner-background color. If detection fails, fall back to `center`. | Early material fitting without masks. |

Default: `center`.

Reasoning:

- `full` can overvalue table/background similarity.
- `center` is robust for this project because rendered parts are usually centered.
- `auto` is useful later, but should be conservative because transparent/white plastic can blend into the background.

## 6. Weighting Strategy

Default weights:

```text
brightness: 0.25
color_histogram: 0.30
ssim: 0.25
edge_texture: 0.20
lpips: 0.00
```

Rationale:

- Color and brightness are critical for material fitting.
- SSIM provides global structure sanity.
- Edge/texture prevents overly smooth material candidates from ranking too high.
- LPIPS is reserved for a future optional path.

Weights are normalized before scoring.

## 7. Validation Strategy

Validate on at least three image pairs:

1. Good match: same image compared with itself.
2. Medium match: two different renders from the same backend/model.
3. Poor match: RGB render compared against a binary mask or visually unrelated image.

Expected ordering:

```text
good_score > medium_score > poor_score
```

Also validate:

- output JSON contains all expected fields;
- metrics are in `[0, 1]`;
- CLI returns a nonzero error only for invalid inputs;
- ROI metadata is recorded.

## 8. Integration With Material Fitting

`core/material_fitter.py` should later replace mock scoring with:

```python
compare_images(reference_image, candidate_render, roi_mode="center")
```

Material fitting should save:

- candidate material parameters;
- candidate render path;
- per-reference metric result;
- mean weighted score;
- selected best material.

For multiple reference images, average weighted scores across references and keep all per-reference metric details.

## 9. Output JSON Schema

```json
{
  "schema_version": "0.1",
  "metric_backend": "pillow_baseline",
  "reference_image": "path/to/reference.png",
  "candidate_image": "path/to/candidate.png",
  "preprocessing": {
    "roi_mode": "center",
    "resize": 512,
    "reference_original_size": [1536, 1024],
    "candidate_original_size": [1536, 1024],
    "reference_roi_box": [230, 154, 1305, 870],
    "candidate_roi_box": [230, 154, 1305, 870],
    "comparison_size": [512, 512]
  },
  "metrics": {
    "brightness": 0.98,
    "color_histogram": 0.93,
    "ssim": 0.91,
    "edge_texture": 0.88,
    "lpips": null
  },
  "weights": {
    "brightness": 0.25,
    "color_histogram": 0.30,
    "ssim": 0.25,
    "edge_texture": 0.20,
    "lpips": 0.0
  },
  "weighted_score": 0.93,
  "notes": []
}
```
