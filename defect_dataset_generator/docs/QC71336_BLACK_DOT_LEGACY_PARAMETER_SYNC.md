# QC71336 Black-Dot Legacy Parameter Sync

## Purpose

Temporarily align the unified black-dot backend with the older QC71336 white prebuilt debug script:

`E:\BlenderProject\BlenderProc\examples\my_project\reference_blend_qc71336_white_prebuilt_normal_debug.py`

The visual audit showed that the current synthetic black dot looked too much like a crisp raised particle. The old script used a smaller, shallower, more conservative embedded-dot setup, so the unified backend was adjusted to use those legacy values for `QC71336_white`.

## Updated Backend

`E:\BlenderProject\BlenderProc\examples\my_project\reference_blend_blackdot_multi_model.py`

## Parameter Changes

### Size

Old script defaults:

```text
black_dot_radius_scale = 0.00190
black_dot_depth_scale = 0.00070
radius_jitter = 0.90 to 1.10
depth_jitter = 0.90 to 1.08
```

Unified backend equivalent:

```text
radius_scale = (0.00171, 0.00209)
depth_scale = (0.00063, 0.00076)
```

### Local Patch

The `QC71336_white` local contamination patch now follows the older script:

```text
patch_radius = radius * 1.12 to 1.26
wave_amplitude = 0.06
inner_radius = radius * 0.36 to 0.52
outer_radius = radius * 0.82 to 1.06
patch surface offset = radius * 0.004
```

Previously the unified backend allowed a much larger support patch:

```text
patch_radius = radius * 1.12 to 1.85
outer_radius up to radius * 1.30
patch surface offset = radius * 0.010
```

### Dot Mesh Shape

For `QC71336_white`, the irregular particle mesh now follows the old script ranges:

```text
local_radius = radius * 0.66 to 1.12
inner_radius = local_radius * 0.28 to 0.46
top_outer_scale = 0.38 to 0.76
bottom_xy_scale = 0.80 to 1.06
```

### Color

The black-dot material colors were already effectively aligned with the old script:

```text
center = (0.022, 0.020, 0.019, 1.0)
edge = (0.060, 0.056, 0.052, 1.0)
patch = (0.24, 0.235, 0.23, 1.0), alpha = 0.030
```

Therefore this sync mainly changes size, depth, patch extent, and local geometry perturbation.

## Scope

Only `QC71336_white` was changed.

Other profiles such as `P101040_blue`, `QC71336_gray`, and `QC75244_white` retain their existing settings.

## Validation

Syntax check passed:

```powershell
python -m py_compile E:\BlenderProject\BlenderProc\examples\my_project\reference_blend_blackdot_multi_model.py
```

No BlenderProc render was run in this step.

## Recommended Next Step

Run a count=5 smoke render only after GPU/render time is available, then regenerate the real-vs-synthetic crop contact sheet:

```text
outputs\evaluation\black_spot_visual_defect_audit\real_vs_synthetic_actual_defect_crops.jpg
```

The decision should be based on visual appearance first:

- lower particle-like sharpness;
- less raised-object impression;
- smaller local contamination footprint;
- still visible enough for mask and YOLO label export.

