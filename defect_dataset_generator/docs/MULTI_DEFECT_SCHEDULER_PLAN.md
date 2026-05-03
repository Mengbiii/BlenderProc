# Multi-Defect Scheduler Plan

## Purpose

Prepare a thin Python-side planning layer for future multi-defect generation. This step does not render images and does not modify Blender defect appearance scripts.

The first goal is to make model placement rules, defect semantic constraints, and per-sample plans explicit and reproducible before any multi-defect Blender integration.

## Current Context

- `mixed_color_contamination` is the most profile-ready defect. It already has `MIXED_COLOR_MODEL_PROFILES`, `get_mixed_color_model_profile()`, and `choose_profile_placement()` in the mixed-color reference script.
- `foreign_material` and `splay` already have useful surface-candidate logic in the QC71336 black prebuilt script: `build_surface_candidate_info()`, `choose_surface_candidate()`, and `jitter_surface_point()`.
- `foreign_material` is a small attached mesh object.
- `splay` is a local streak/patch and must not return to global procedural material pollution.
- The new framework currently renders only black spot through a production wrapper. Other defect types still need staged integration.

## Model Profile

A model profile describes geometry and placement rules that should not live inside individual defect appearance functions.

Initial fields:

- `model_id`
- `blend_path_hint`
- `stl_path_hint`
- `camera_presets`
- `main_surface_zones`
- `exclusion_zones`
- `defect_allowed_zones`
- `zone_weights`
- `artifact_window`
- `fallback_window`
- `placement_offsets`
- `radius_x_factor`
- `radius_y_factor`
- `overlap_policy`

The first migrated profile is `qc7_5236`, derived from the current QC7-5236/QC7-5244 mixed-color profile.

## Defect Profile

A defect profile describes semantic constraints and expected placement behavior. It does not implement Blender materials or geometry.

Initial fields:

- `defect_type`
- `appearance_backend`
- `preferred_surface_type`
- `allowed_zones`
- `size_tiers`
- `default_size_tier_weights`
- `overlap_policy`
- `mask_area_limits_px`
- `bbox_size_limits_px`
- `notes`

Initial defect profiles:

- `mixed_color_contamination`
- `black_dot`
- `foreign_material`
- `splay`

## Camera Plan

The scheduler currently samples only named camera presets from the model profile. It does not move the Blender camera.

First supported preset:

- `baseline_front`

Future presets:

- `defect_front_mild_jitter`
- model-specific inspection angles
- stress-test camera presets

## Lightweight Visible Surface / Candidate Zone Plan

The first scheduler version intentionally does not compute true polygon visibility. It uses profile-level projected windows and allowed zones:

```text
model profile zones + defect allowed zones -> selected zone -> projected_xy
```

True mesh visibility, camera projection, and polygon area filtering should be added only after dry-run plans and single-defect backend integration are stable.

## Defect Plan

Each dry-run sample writes one JSON file:

```text
defect_plan_000000.json
```

The plan contains:

- `sample_id`
- `seed`
- `model_id`
- `camera_profile`
- `visible_surface_plan`
- `defects`

Each defect entry contains:

- `defect_id`
- `defect_type`
- `placement_zone`
- `projected_xy`
- `target_x_range`
- `target_y_range`
- `zone_window`
- `size_tier`
- `size_parameters`
- `radius_x_factor`
- `radius_y_factor`
- `overlap_policy`
- `appearance_backend`

## Future Instance Output Structure

When rendering is integrated, output should move toward:

```text
rgb/
mask_instances/
mask_combined/
overlay/
labels_yolo/
metadata/
dataset_summary.json
```

Per-image metadata should use an instance list:

```json
{
  "sample_id": 0,
  "camera_profile": "baseline_front",
  "defects": [
    {
      "defect_id": 0,
      "type": "splay",
      "mask_path": "mask_instances/000000_0.png",
      "bbox_xywh": [0.1, 0.2, 0.03, 0.01],
      "placement_zone": "center_safe",
      "projected_xy": [0.55, 0.62]
    }
  ]
}
```

YOLO labels should contain one row per visible defect instance.

## Staged Migration Path

### Phase 1: Profile Schema

Create Python profile modules and migrate QC7-5236 mixed-color profile values.

### Phase 2: Scheduler Dry Run

Add `python app.py plan-defects ...` to generate deterministic JSON plans without rendering.

### Phase 3: Mixed Color Single-Defect Backend

Let a copied mixed-color backend consume `defect_plan.json`. Keep single-defect only.

### Phase 4: Foreign Material / Splay Single-Defect Backend

Map scheduler placement plans to the existing surface-candidate logic. Do not unify Blender implementation styles.

### Phase 5: Unified Output Adapter

Adapt old output structures into instance masks, combined masks, per-image metadata, YOLO labels, and dataset summaries.

### Phase 6: Controlled Two-Defect Smoke

Start only with:

- `mixed_color_contamination + black_dot`
- `mixed_color_contamination + foreign_material`

Generate 5-10 images per combination, inspect RGB, masks, bboxes, and semantic confusion. Do not train until labels are stable.

## Limitations

- No BlenderProc rendering is called by the scheduler.
- No true polygon visible surface map is implemented yet.
- No existing stable defect rendering script is modified.
- Multi-defect rendering is schema-only at this stage.
- The scheduler does not guarantee RGB realism; it only prepares reproducible placement plans.

## Example

```powershell
python app.py plan-defects ^
  --model-profile qc7_5236 ^
  --defects mixed_color_contamination ^
  --mode single_defect ^
  --count 5 ^
  --seed 100 ^
  --out outputs\plans\mixed_color_scheduler_smoke
```

