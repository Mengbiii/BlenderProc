# Mixed Color Plan Integration Notes

## Purpose

Prepare Phase 3 integration for `mixed_color_contamination` so a copied backend can consume scheduler dry-run plans.

This document is an interface note only. Do not modify the stable mixed-color rendering script in this step, and do not run BlenderProc while YOLO training is active.

## Source Backend

Stable/reference script:

```text
examples/my_project/reference_blend_qc75244_mixed_color_profile_debug.py
```

This backend should remain material-driven:

- Do not revert to a transparent patch object.
- Do not change RGB appearance logic.
- Do not change mask export semantics.
- Keep RGB, mask, overlay, bbox, and YOLO label tied to the same procedural footprint.

## Copied Backend Strategy

Create a copied integration script later, for example:

```text
examples/my_project/reference_blend_qc75244_mixed_color_plan_debug.py
```

The copied script should add:

```text
--defect-plan path\to\defect_plan_000000.json
--dry-run-plan-read
```

`--dry-run-plan-read` should:

- Load the plan.
- Validate `model_id`, `defect_type`, `camera_profile`, and `placement_zone`.
- Print/write metadata about how the plan would be consumed.
- Not render RGB.
- Not modify materials.
- Not call expensive GPU rendering.

## Plan Fields To Consume

The copied backend should read:

- `camera_profile`
- `defects[0].placement_zone`
- `defects[0].projected_xy`
- `defects[0].target_x_range`
- `defects[0].target_y_range`
- `defects[0].zone_window`
- `defects[0].size_tier`
- `defects[0].radius_x_factor`
- `defects[0].radius_y_factor`

First integration should support only:

```text
mode = single_defect
defect_type = mixed_color_contamination
```

## Mapping To Existing Placement Logic

The existing backend currently uses:

- `MIXED_COLOR_MODEL_PROFILES`
- `get_mixed_color_model_profile(primary_obj)`
- `choose_profile_placement(profile, debug_center_mixed_color=False)`

The copied backend should not remove these immediately. Instead, add a plan-driven branch:

```text
if args.defect_plan:
    placement_zone = plan["defects"][0]["placement_zone"]
    projected_xy = plan["defects"][0]["projected_xy"]
    radius_x_factor = plan["defects"][0]["radius_x_factor"]
    radius_y_factor = plan["defects"][0]["radius_y_factor"]
else:
    use existing choose_profile_placement(...)
```

The first plan-driven version may map `projected_xy` back into the existing profile plane coordinate assumptions. If exact projection is not available yet, preserve the existing profile placement helper and override only:

- selected zone
- target range
- radius factors

## Camera Handling

Read `camera_profile`, but do not necessarily move the camera yet.

First version:

- Accept `baseline_front`.
- Record `camera_profile` in metadata.
- Keep the existing reference camera setup unchanged.

Later versions can map named camera profiles to actual camera presets.

## Metadata

The copied backend should record:

- `defect_plan_path`
- `plan_schema_version`
- `sample_id`
- `seed`
- `camera_profile`
- `placement_zone`
- `projected_xy`
- `size_tier`
- `radius_x_factor`
- `radius_y_factor`
- `plan_consumed = true`

## First Render Test

After YOLO training is complete and GPU is available:

1. Run `--dry-run-plan-read` on one plan.
2. Run one count=1 render using a copied backend.
3. Inspect RGB, mask, overlay, YOLO label, and metadata.
4. Only then run count=3 or count=5 smoke.

## Not In Scope Yet

- True polygon visible surface map.
- Multi-defect rendering.
- Instance mask output.
- Rewriting mixed-color material nodes.
- Integrating foreign material or splay.

