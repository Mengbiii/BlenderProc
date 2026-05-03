# QC71336 Black-Dot Preset Calibration Workflow

## Scope

This workflow calibrates QC71336 black-dot appearance before any YOLO training.

The first pass targets:

- model: `QC71336`
- appearance: `white`
- defect: `black_dot`

The structure is designed so the same model with another color, or another model/color pair, can be added as a new preset entry later.

Important boundary:

- each model/color version must be evaluated independently;
- do not mix white, gray, and black real images in one comparison or training split;
- `mixed_color_contamination` is deferred from current comparison/training until a separate protocol is defined.

## Flow

```text
real annotated images
  -> real label preparation
  -> real defect crop statistics
  -> black-dot appearance preset
  -> small synthetic smoke render
  -> non-YOLO defect realism evaluation
  -> visual contact-sheet review
  -> best preset selection
  -> framework generate
```

## Real Data Preparation

Use:

`examples/my_project/prepare_qc71336_real_labels_from_manual_bbox.py`

Current output:

`defect_dataset_generator/outputs/calibration/qc71336_white_blackdot_real_labels_v1`

This output is for calibration and visual diagnosis. It should not be treated as a final training dataset unless separately audited.

## Presets

Preset file:

`defect_dataset_generator/config/black_dot_appearance_presets.json`

Preset IDs:

- `qc71336_white_legacy_sync_v1`
- `qc71336_white_smaller_soft_v1`
- `qc71336_gray_legacy_sync_v1`

Preset values are model/color specific. Do not apply a white preset to gray, black, or another model without a separate visual check.

## Framework Generate Integration

`app.py generate` supports:

- `--defect-preset`
- `--defect-preset-file`

For black-dot backends, the preset can pass:

- `black_dot_radius_min_scale`
- `black_dot_radius_max_scale`
- `black_dot_depth_min_scale`
- `black_dot_depth_max_scale`

The backend appearance implementation remains in `reference_blend_blackdot_multi_model.py`.

## Evaluation Tool

Use:

`tools/evaluate_defect_realism.py`

Current first adapter:

- `black_dot`

Outputs:

- `defect_realism_summary.json`
- `defect_realism_per_sample.csv`
- `real_vs_synthetic_defect_crops.jpg`
- `DEFECT_REALISM_REPORT.md`

## Metrics

Current common metrics:

- bbox area ratio
- mask area ratio if synthetic mask exists
- defect mean grayscale
- surrounding background mean grayscale
- defect-background contrast
- normalized visibility proxy
- defect darkness proxy
- edge softness proxy

These metrics are diagnostic proxies. They are not proof of physical realism or detector performance.

## Current Result

Initial smoke comparison:

`outputs/evaluation/defect_realism_black_dot_qc71336_white_smoke`

The run used 12 real crops and 1 synthetic crop. It proves the pipeline works, but it is not enough to finalize the preset.

## QC71336 Gray Migration

Gray black-dot migration output:

`outputs/calibration/qc71336_gray_blackdot_real_labels_v1`

Summary:

- output images: 50
- defect images: 28
- normal images: 22
- missing matches: 0

Gray smoke evaluation:

`outputs/evaluation/defect_realism_black_dot_qc71336_gray_smoke`

The first gray smoke result shows that the current synthetic gray black dot is much darker and more visible than the gray real crop statistics. This validates the need for color-specific presets and independent evaluation.

## Next Step

Render a `count=3` to `count=5` synthetic smoke set with `qc71336_white_legacy_sync_v1`, then rerun `evaluate_defect_realism.py`.

Do not resume YOLO until visual realism is acceptable.
