# Image Realism Metrics Optimization Plan

## Goal

Evaluate whether synthetic defect images look like real inspection photos without using detector training metrics.

The evaluation is split into three layers:

- `scene_quality`: whole-image capture realism, including luma, contrast, highlight/dark ratios, and edge density.
- `material_context`: product/background appearance around the defect, including background luma and local variation.
- `defect_realism`: defect geometry and appearance, including size, elongation, contrast, visibility, edge softness, and type-specific metrics.

## Literature-Informed Metric Families

- No-reference IQA: NIQE, BRISQUE, and PIQE style natural-statistics checks for blur/noise/exposure artifacts.
- Reference or dataset-distribution metrics: brightness, color histogram, SSIM, local contrast, texture/edge statistics.
- Generative distribution metrics: FID/KID and precision/recall or density/coverage for large batches, used only as secondary distribution diagnostics.
- Defect-local metrics: mask/bbox size, defect-to-background contrast, edge softness, compactness, elongation, and defect-class-specific shape priors.

## Current Implementation Status

Implemented in `tools/evaluate_defect_realism.py`:

- Multi-defect support instead of `black_dot` only.
- Per-sample `scene_quality` metrics.
- Per-sample `defect_shape` metrics.
- Per-sample `defect_specific` metrics for:
  - `black_dot`
  - `foreign_material`
  - `splay`
  - `mixed_color_contamination`
- Real-reference distribution profile when real localized samples are available.
- Synthetic sample `pass/warn/fail` assessment using heuristics plus expanded real-distribution intervals.

Implemented in `core/real_dataset_profiles.py`:

- Support for both legacy mojibake folder keywords and current Chinese folder names.

## Next Engineering Steps

1. Add a real-label adapter for manually annotated real folders where YOLO labels do not yet exist.
2. Add product foreground masks or segmentation proxies so metrics can verify that defects lie on the model surface, not merely inside the image.
3. Add batch-level profile JSON files per `(model, color, defect_type)` under `config/realism_profiles/`.
4. Extend generation summaries with optional realism evaluation results after each batch.
5. Add hard fail gates for:
   - empty mask;
   - mask bbox outside product foreground;
   - defect visibility below minimum threshold;
   - size/elongation outside target profile;
   - splay direction or compactness inconsistent with real samples;
   - foreign material exceeding rice-grain scale.

## Guardrails

These metrics are diagnostic proxies. They do not prove physical accuracy and do not prove detector improvement. Contact sheets and human review remain the final visual acceptance loop.
