# Coverage-First Readiness Report

Last updated: 2026-04-30

## Scope

This report records the first-pass generation coverage check for the final dataset target matrix. The first pass verified structural outputs only: RGB file, mask, YOLO label, per-image metadata, and dataset summary.

Important correction: the original structural pass did not check RGB content and allowed all-black images to pass. That is now treated as a failure. `run_sample_quality_checks` includes `rgb_not_blank` with luminance statistics.

Pipeline correction: the generic backend now uses an existing-scene-first policy. Existing `.blend` lights are reused and randomized around their original values. A generic camera/light setup is only used when the scene does not provide one. The earlier bbox main-plane proxy has been removed from the default path because it can create obvious non-product occlusion.

Visual realism, defect realism, correct final material, and final model/profile alignment were intentionally not used as acceptance gates in this pass.

## Backend

- Command family: `python defect_dataset_generator/app.py generate-target`
- Backend: `generic_main_plane`
- Script: `defect_dataset_generator/blender_scripts/render_generic_main_plane_defects.py`
- Placement policy: `front_back_main_planes_only`
- Render samples: `4`
- Readiness count: `3` images per target/defect pair
- Original structural output root: `defect_dataset_generator/outputs/dataset/coverage_readiness/`
- Fixed smoke output root: `defect_dataset_generator/outputs/dataset/coverage_smoke_fixed/`

## Black RGB Fix Verification

| Target | Defect | Output | Result |
| --- | --- | --- | --- |
| `p101040_blue` | `black_dot` | `coverage_smoke_fixed/p101040_blue_black_dot_v3` | visible blue main plane + defect; `rgb_not_blank=true` |
| `qc71336_black` | `foreign_material` | `coverage_smoke_fixed/qc71336_black_foreign_v1` | visible black model/main plane; `rgb_not_blank=true` |
| `p101040_blue` | `black_dot` | `coverage_existing_scene_fixed/p101040_blue` | proxy occluder removed; existing scene lights reused; `rgb_not_blank=true` |

## Existing-Scene Smoke Matrix

Output root: `defect_dataset_generator/outputs/dataset/coverage_existing_scene_smoke/`

| Target | Defect | Requested | Succeeded | Failed | RGB nonblank |
| --- | --- | ---: | ---: | ---: | --- |
| `p101040_blue` | `black_dot` | 1 | 1 | 0 | yes |
| `qc71336_black` | `foreign_material` | 1 | 1 | 0 | yes |
| `qc71336_black` | `splay` | 1 | 1 | 0 | yes |
| `qc71336_white` | `black_dot` | 1 | 1 | 0 | yes |
| `qc71336_white` | `foreign_material` | 1 | 1 | 0 | yes |
| `qc71336_gray` | `black_dot` | 1 | 1 | 0 | yes |
| `qc71336_gray` | `mixed_color_contamination` | 1 | 1 | 0 | yes |
| `qc7_5244_black` | `black_dot` | 1 | 1 | 0 | yes |
| `qc7_5244_black` | `foreign_material` | 1 | 1 | 0 | yes |
| `qc7_5244_black` | `splay` | 1 | 1 | 0 | yes |
| `qc7_5244_white` | `black_dot` | 1 | 1 | 0 | yes |
| `qc7_5244_white` | `mixed_color_contamination` | 1 | 1 | 0 | yes |
| `ql3_1052_black` | `foreign_material` | 1 | 1 | 0 | yes |
| `ql3_1052_black` | `splay` | 1 | 1 | 0 | yes |

## Coverage Matrix

| Target | Defect | Requested | Succeeded | Failed |
| --- | --- | ---: | ---: | ---: |
| `p101040_blue` | `black_dot` | 3 | 3 | 0 |
| `qc71336_black` | `foreign_material` | 3 | 3 | 0 |
| `qc71336_black` | `splay` | 3 | 3 | 0 |
| `qc71336_white` | `black_dot` | 3 | 3 | 0 |
| `qc71336_white` | `foreign_material` | 3 | 3 | 0 |
| `qc71336_gray` | `black_dot` | 3 | 3 | 0 |
| `qc71336_gray` | `mixed_color_contamination` | 3 | 3 | 0 |
| `qc7_5244_black` | `black_dot` | 3 | 3 | 0 |
| `qc7_5244_black` | `foreign_material` | 3 | 3 | 0 |
| `qc7_5244_black` | `splay` | 3 | 3 | 0 |
| `qc7_5244_white` | `black_dot` | 3 | 3 | 0 |
| `qc7_5244_white` | `mixed_color_contamination` | 3 | 3 | 0 |
| `ql3_1052_black` | `foreign_material` | 3 | 3 | 0 |
| `ql3_1052_black` | `splay` | 3 | 3 | 0 |

## Commands

Examples:

```powershell
python defect_dataset_generator\app.py list-targets
python defect_dataset_generator\app.py generate-target --target qc7_5244_black --count 3 --samples 4 --out defect_dataset_generator\outputs\dataset\coverage_readiness\qc7_5244_black
python defect_dataset_generator\app.py generate-target --target ql3_1052_black --defects foreign_material,splay --count 3 --samples 4 --out defect_dataset_generator\outputs\dataset\coverage_readiness\ql3_1052_black
```

## Known Caveats

- `generic_main_plane` is a fallback backend for coverage only. It uses simplified primitive defects and does not claim realistic defect appearance.
- The bbox-derived main-plane surface proxy is disabled in the default path because it can occlude the real model. If re-enabled later, it must be an explicit fallback with visual validation.
- QC7-5244 black/white intentionally use `assets/models/QC7-5236.stl` as the current QC7-5244 geometry asset. The STL has no accepted authored material, so target appearance must be constructed by the QC7-5244 material profile or reference/generic scripts before any realism claim.
- `sink_mark` is not part of the current 3k-5k target set; its dark-ellipse fallback remains excluded until a target-specific implementation exists.
- Domain randomization is recorded in generation plans, but the generic backend currently uses a fixed simple camera/light setup internally. Backend-level sampling should be wired next.
- The generated labels are structurally valid, but some fallback placements may be near image borders. This is acceptable for coverage-first smoke only and should be tightened before larger batches.

## Next Step

Use this coverage path to run `count=10` smoke batches per target/defect, then replace fallback backend behavior with the better existing specialized paths where available:

- `black_dot`: `reference_blend_blackdot_multi_model.py`
- QC71336 black `foreign_material` / `splay`: `reference_blend_qc71336_black_prebuilt_normal_debug.py`
- QC7-5244 white `mixed_color_contamination`: `reference_blend_qc75244_mixed_color_profile_debug.py`
