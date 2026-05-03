# QC7-5244 Black Material Improvement Notes

## Current Problem

The first QC7-5244 black material fit reached a high single-ROI score, but human visual review found that the synthetic material still looked too dark, too uniform, and too matte. The real part is better described as deep cool gray injection-molded plastic with subtle surface texture and soft, broad highlights.

The v1 result should therefore be treated as a diagnostic baseline, not as an accepted generation default.

## What Was Added

- Multi-ROI audit config:
  `config/material_audit_rois_qc7_5244_black_v1.json`
- Multi-ROI audit tool:
  `tools/audit_material_fit_multiroi.py`
- V2 material search space:
  `config/material_search_space_qc7_5244_black_v2_cool_gray_texture.json`

## Audit Command

```powershell
python tools\audit_material_fit_multiroi.py ^
  --fit-dir outputs\fitting\fit_qc7_5244_black_material_v1 ^
  --roi-config config\material_audit_rois_qc7_5244_black_v1.json ^
  --out outputs\fitting\fit_qc7_5244_black_material_v1\material_fit_multiroi_audit_v1 ^
  --top-k 10
```

## Audit Outputs

- `outputs/fitting/fit_qc7_5244_black_material_v1/material_fit_multiroi_audit_v1/MATERIAL_FIT_AUDIT_REPORT.md`
- `outputs/fitting/fit_qc7_5244_black_material_v1/material_fit_multiroi_audit_v1/material_fit_audit_summary.json`
- `outputs/fitting/fit_qc7_5244_black_material_v1/material_fit_multiroi_audit_v1/material_fit_audit_contact_sheet.jpg`
- `outputs/fitting/fit_qc7_5244_black_material_v1/material_fit_multiroi_audit_v1/material_audit_roi_preview.jpg`

## Current Audit Result

Candidate 20 remains the top candidate under the current multi-ROI audit, but its score drops from the original single-ROI `0.955520` to the multi-ROI score around `0.888`. This supports the diagnosis that the single-ROI score was too optimistic and that camera/scene/material mismatch is still visible.

## Recommended V2 Fit Command

```powershell
python app.py fit-material ^
  --real "E:\BlenderProject\BlenderProc\塑料工件真实数据集\QC7-5244黑色\QC9-0852-正常\9K9A0793.JPG" ^
  --blend assets\models\moxing1_test.blend ^
  --out outputs\fitting\fit_qc7_5244_black_material_v2 ^
  --candidates 80 ^
  --scoring real ^
  --render-candidates ^
  --roi mask ^
  --roi-mask outputs\calibration\qc7_5244_black_material_reference\qc7_5244_black_9K9A0793_material_roi_v1.png ^
  --resize 512 ^
  --samples 16 ^
  --seed 75244 ^
  --material-profile opaque_black_plastic ^
  --render-width 512 ^
  --render-height 384 ^
  --score-profile plastic_material ^
  --material-search-space config\material_search_space_qc7_5244_black_v2_cool_gray_texture.json
```

After the V2 fit, run the multi-ROI audit again and inspect the contact sheet before accepting the material for defect generation.

## V2 Result

V2 was run with 60 candidates:

- Output folder: `outputs/fitting/fit_qc7_5244_black_material_v2`
- Best candidate: `0`
- Single-ROI score: `0.951552`
- Multi-ROI score: `0.878423`

For comparison, V1 candidate 20 had:

- Single-ROI score: `0.955520`
- Multi-ROI score: `0.888065`

Therefore V2 does not improve the current multi-ROI diagnostic score. It should not be promoted to the default generation material yet. The next improvement should focus on aligning the clean candidate render camera/scene with the real reference photo before continuing material fitting.

Comparison report:
`outputs/fitting/fit_qc7_5244_black_material_v2/FIT_V1_V2_MATERIAL_COMPARISON_REPORT.md`

## Clean Import Baseline Finding

A no-defect, no-external-material clean baseline was rendered to check whether the problem is caused by defect generation, material transfer, or the model/profile setup itself.

Script:

```text
blender_scripts/render_clean_import_baseline.py
```

Output:

```text
outputs/dataset/qc7_5244_clean_import_baseline_no_defect/
```

Important files:

```text
rgb/clean_import_baseline.png
metadata/clean_import_baseline.json
blend_debug/clean_import_baseline.blend
```

The metadata shows that the current historical `QC75244_white` backend profile imports:

```text
assets/models/QC7-5236.stl
```

The rendered object is named:

```text
QC7-5236-000N301002ST0101_QC7-5236
```

Current decision:

- `assets/models/QC7-5236.stl` is the geometry asset currently used for the QC7-5244 target.
- The STL does not contain an accepted authored material.
- QC7-5244 black appearance must therefore be built from the QC7-5244 material profile/script, currently `defect_dataset_generator/config/qc7_5244_black_visual_material_candidate_v3.json` for coverage smoke.
- The historical `QC75244_white` backend key is retained only for compatibility with older scripts and should not be treated as a separate physical model.

## Limitations

- The current candidate renderer camera does not match the real reference photo well enough for final whole-image realism judgment.
- `QC7-5236.stl` is explicitly documented as the current QC7-5244 geometry asset; material realism must come from the target profile/script rather than from the STL.
- The current shader supports base color, roughness, specular, noise-driven bump, lighting, exposure, and background. More advanced roughness noise or low-frequency color variation is planned but not active yet.
- This process is visual material calibration, not physical material recovery.
