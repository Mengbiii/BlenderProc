# Visual Material Calibration Schema

## Purpose

Visual material calibration estimates render parameters that make a clean synthetic plastic part look closer to real reference photos under the current deterministic scene setup.

This is not physical material recovery. The output is a practical visual calibration artifact for synthetic dataset generation.

## Boundary

The calibration output separates three concepts:

1. Material parameters
2. Scene calibration parameters
3. Scoring metadata

Defect parameters are excluded from this stage.

## best_material.json Schema

```json
{
  "schema_version": "0.2",
  "calibration_type": "visual_material_calibration",
  "material_parameters": {
    "base_color": [0.78, 0.8, 0.82, 1.0],
    "roughness": 0.35,
    "specular": 0.5,
    "specular_ior_level": 0.5,
    "subsurface": 0.0,
    "translucency": 0.0,
    "noise_scale": 48.0,
    "noise_strength": 0.0,
    "bump_strength": 0.0
  },
  "scene_calibration": {
    "light_strength": 450.0,
    "exposure": 0.0,
    "camera_profile": "deterministic_ortho_front",
    "render_resolution": [512, 384],
    "background_color": [0.78, 0.78, 0.78, 1.0]
  },
  "scoring": {
    "metric_backend": "pillow_baseline",
    "roi_mode": "manual",
    "roi_box": [1900, 900, 2200, 1200],
    "resize": 512,
    "weighted_score": 0.574109
  }
}
```

## Material Parameters

These fields describe the plastic appearance assigned to the rendered object:

- `base_color`: RGBA material color.
- `roughness`: surface roughness used by the Principled BSDF.
- `specular` / `specular_ior_level`: specular response. Both are recorded for Blender version compatibility.
- `subsurface` / `translucency`: translucency-like term when the shader supports it.
- `noise_scale`: procedural noise scale used for bump/noise effects.
- `noise_strength`: reserved visual noise strength.
- `bump_strength`: procedural bump strength.

## Scene Calibration Parameters

These fields describe deterministic scene settings used during visual calibration:

- `light_strength`: area light energy.
- `exposure`: view transform exposure.
- `camera_profile`: named deterministic camera setup. Camera pose is not randomly searched in this stage.
- `render_resolution`: candidate render width and height.
- `background_color`: world/background color.

If `light_strength` or `exposure` are searched later, they must remain under `scene_calibration`, not under `material_parameters`.

## Scoring Metadata

Scoring fields describe how the visual comparison was made:

- `metric_backend`: current backend is `pillow_baseline`.
- `roi_mode`: `full`, `center`, `auto`, or `manual`.
- `roi_box`: manual ROI as `[x, y, w, h]` in reference image pixels, present only for manual ROI.
- `resize`: comparison resize.
- `weighted_score`: final weighted similarity score.

Manual ROI uses the given reference-image rectangle directly. Candidate renders use the same relative rectangle scaled to the candidate image size.

## Candidate Entries

Each entry in `material_fit_candidates.json` also separates:

- `material_parameters`
- `scene_calibration`
- `scoring`
- `render_status`
- `rank`

Legacy fields such as `params`, `score`, and `mean_weighted_score` may remain temporarily for compatibility, but new code should prefer the separated schema.

## Defect Parameters Excluded

Defect parameters are not part of material fitting:

- defect type
- defect size
- defect count
- defect position
- defect opacity
- defect color
- masks and YOLO labels

Those belong to the defect generation stage and must not be mixed into `best_material.json`.

## Why This Is Visual Calibration

The process compares rendered images against real photos. Scores can be affected by:

- camera angle and crop
- background color
- shadows and exposure
- unmodeled texture
- real photo noise and lens effects
- ROI quality

Because these factors are not a controlled physical measurement, the output should be described as visually calibrated or visually fitted, not physically accurate.
