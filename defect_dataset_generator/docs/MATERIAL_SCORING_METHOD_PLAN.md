# Material Scoring Method Plan

## Purpose

Define a technical-report-friendly visual material calibration score for injection-molded plastic parts.

The score is used to rank rendered clean material candidates against real reference photos. It focuses on clean plastic material regions, not whole-image similarity and not defect appearance.

## Literature-Informed Basis

Material appearance is commonly described through multiple perceptual cues rather than a single full-image similarity value:

- Color and lightness describe diffuse material tone.
- Gloss and highlight behavior describe first-surface reflection and perceived shininess.
- Texture and local contrast describe surface roughness, grain, molded texture, haze, and matte variation.
- Structure metrics such as SSIM can be useful, but they are strongly affected by object pose, crop, background, and geometric layout.

Related material-appearance and gloss literature emphasizes color, gloss/shininess, texture, contrast, haze, and surface uniformity as separate appearance dimensions. BRDF-space metrics can be physically meaningful, but image-based metrics under controlled rendering are often used when the goal is perceptual or visual appearance matching. For this project, the practical target is deterministic visual candidate ranking, so a lightweight image-statistics score is appropriate.

## Why The Old Score Is Insufficient

The current baseline score combines brightness, color histogram, global SSIM approximation, and edge/texture over an ROI. It is useful as a generic image-similarity smoke test, but it is weak for material calibration because:

- SSIM and edge similarity can reward geometric structure and background alignment instead of plastic appearance.
- Whole-image or broad center ROI scoring can be dominated by background, shadows, logo/text, and object pose.
- Gloss/matte behavior is not explicitly measured.
- Local plastic surface variation is not separated from object edges.
- The score is hard to justify as a material-focused method in technical reporting.

## New Score Profile

Add:

```text
score_profile = plastic_material
```

Keep the existing method as:

```text
score_profile = baseline
```

## ROI Requirement

The `plastic_material` score must be computed only on ROI pixels.

Manual ROI is strongly recommended:

```powershell
--roi manual --roi-box x,y,w,h
```

If `plastic_material` is used with `--roi full`, the output must include this warning:

```text
plastic_material score should be used with clean material ROI; full-image scoring may be dominated by background.
```

If `plastic_material` is used with non-manual ROI, the output should still run but record a warning that clean material ROI is recommended.

## Metric Components

All components are normalized to `[0, 1]`. Higher means more visually similar.

### A. Brightness Similarity

Purpose: compare overall plastic lightness.

Use grayscale mean intensity:

```text
B_ref = mean(gray_ref) / 255
B_cand = mean(gray_cand) / 255
brightness_similarity = 1 - abs(B_ref - B_cand)
```

### B. Color Similarity

Purpose: compare warm/cool white tone and RGB balance.

Use mean RGB vectors normalized to `[0, 1]`:

```text
C_ref = mean_rgb(ref) / 255
C_cand = mean_rgb(cand) / 255
d = mean(abs(C_ref - C_cand))
color_similarity = 1 - d
```

This is Lab-like only in the sense that it compares low-dimensional color statistics rather than full spatial structure. A future upgrade can replace it with CIELAB Delta E.

### C. Local Contrast Similarity

Purpose: compare matte plastic variation and gentle surface unevenness.

Use grayscale standard deviation:

```text
S_ref = std(gray_ref) / 128
S_cand = std(gray_cand) / 128
local_contrast_similarity = 1 - min(1, abs(S_ref - S_cand))
```

### D. Highlight Similarity

Purpose: compare glossy/matte behavior.

Detect bright pixels inside the ROI using a percentile-based threshold:

```text
threshold = max(220, percentile(gray, 90))
highlight_mask = gray >= threshold
highlight_ratio = count(highlight_mask) / roi_pixel_count
highlight_intensity = mean(gray[highlight_mask]) / 255, or 0 if no highlight
```

Similarity:

```text
ratio_similarity = 1 - min(1, abs(ratio_ref - ratio_cand) / 0.25)
intensity_similarity = 1 - abs(intensity_ref - intensity_cand)
highlight_similarity = 0.6 * ratio_similarity + 0.4 * intensity_similarity
```

### E. Texture Similarity

Purpose: compare small-scale plastic surface cues without making texture dominant.

Use gradient magnitude or edge density:

```text
edge_ref = FIND_EDGES(gray_ref)
edge_cand = FIND_EDGES(gray_cand)
T_ref = mean(edge_ref) / 255
T_cand = mean(edge_cand) / 255
texture_similarity = 1 - min(1, abs(T_ref - T_cand) / 0.25)
```

### F. Optional SSIM

Purpose: retain a weak structural sanity term.

Use the existing global SSIM approximation:

```text
ssim_similarity = global_ssim(ref, cand)
```

It has low weight because SSIM mostly measures structure and alignment, not material.

## Formula

```text
material_score =
  0.25 * brightness_similarity
+ 0.30 * color_similarity
+ 0.15 * local_contrast_similarity
+ 0.15 * highlight_similarity
+ 0.10 * texture_similarity
+ 0.05 * ssim_similarity
```

Weights:

```json
{
  "brightness_similarity": 0.25,
  "color_similarity": 0.30,
  "local_contrast_similarity": 0.15,
  "highlight_similarity": 0.15,
  "texture_similarity": 0.10,
  "ssim_similarity": 0.05
}
```

## Output JSON

`compare-images` and material fitting reports should include:

```json
{
  "score_profile": "plastic_material",
  "weighted_score": 0.0,
  "components": {
    "brightness_similarity": 0.0,
    "color_similarity": 0.0,
    "local_contrast_similarity": 0.0,
    "highlight_similarity": 0.0,
    "texture_similarity": 0.0,
    "ssim_similarity": 0.0
  },
  "weights": {},
  "roi_mode": "manual",
  "roi_box": [x, y, w, h]
}
```

## Validation Strategy

Compare `baseline` and `plastic_material` on:

- same image pair
- medium candidate pair
- poor candidate pair
- real reference vs top candidate
- real reference vs worst candidate

Record whether `plastic_material` better matches human judgment. If it does not, document the mismatch.

## Limitations

- This score is not a physical BRDF recovery metric.
- It cannot separate material from illumination unless lighting and camera are controlled.
- Manual ROI quality strongly affects the result.
- The current color similarity is RGB-statistical, not full perceptual Delta E.
- Highlight statistics are approximate and depend on exposure.
- Texture statistics do not understand true molded micro-geometry.

## Suggested Technical Wording

Suggested wording:

> The proposed material calibration score is not intended to recover physically accurate BRDF parameters. Instead, it is a deterministic visual ranking metric for rendered material candidates. The score is computed within a clean plastic ROI and combines brightness, color tone, local contrast, highlight behavior, texture cues, and a low-weight structural similarity term. This design emphasizes appearance cues relevant to injection-molded plastic parts while reducing the influence of background and object-level geometry.

## Implementation Scope

- Add `--score-profile baseline|plastic_material`.
- Keep the old baseline score.
- Do not include defect parameters in material scoring.
- Keep camera pose deterministic.
- Keep the method lightweight and explainable.
