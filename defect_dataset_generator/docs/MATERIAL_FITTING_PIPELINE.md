# Material Fitting Pipeline

## Purpose

The material fitting pipeline ranks candidate material parameters by comparing clean candidate renders against real reference images. The current implementation supports two real-scoring paths:

- Automatic candidate rendering through `--scoring real --render-candidates`.
- Existing candidate image scoring through `--scoring real --candidate-dir`.

Automatic rendering is now the main path for closing the material fitting loop. `--candidate-dir` remains useful for debugging, recovery, and rescoring previously rendered images.

## Inputs

- Real reference image or folder:
  - `--real reference_images`
- Clean source `.blend` model:
  - `--blend assets\models\moxing2.blend`
- Output fitting run folder:
  - `--out defect_dataset_generator\outputs\fitting\fit_test_01`
- Candidate count limit:
  - `--candidates 20`
- ROI mode:
  - `--roi center`
  - `--roi manual --roi-box x,y,w,h`
  - `--roi mask --roi-mask mask.png`
- Comparison resize:
  - `--resize 512`
- Scoring mode:
  - `--scoring mock`
  - `--scoring real`
- Score profile:
  - `--score-profile baseline`
  - `--score-profile plastic_material`
- Rendered candidate image folder for real scoring:
  - `--candidate-dir folder_with_rendered_candidates`
- Automatic candidate rendering:
  - `--render-candidates`
- Blender render samples for automatic candidates:
  - `--samples 16`
- Candidate render size:
  - `--render-width 512 --render-height 384`
- Deterministic candidate seed base:
  - `--seed 100`
- Material profile tag recorded in candidate material JSON:
  - `--material-profile opaque_white_plastic`

## Outputs

Each fitting run writes:

```text
outputs/fitting/<run_name>/
  candidate_materials/
    candidate_000000.json
  candidate_renders/
    candidate_000000.png
  candidate_metadata/
    candidate_000000.json
    candidate_000000_render_log.txt
  material_fit_candidates.json
  best_material.json        schema_version 0.2
  material_fitting_report.json
  best_preview_render.json
```

## Command Examples

Mock scoring for quick flow checks:

```powershell
python app.py fit-material --real defect_dataset_generator\outputs\dataset\black_spot_batch5_validation\rgb\000000.png --blend assets\models\moxing2.blend --out defect_dataset_generator\outputs\fitting\fit_mock_test_01 --candidates 5 --scoring mock
```

Real scoring with an existing candidate image folder:

```powershell
python app.py fit-material --real defect_dataset_generator\outputs\dataset\black_spot_batch5_validation\rgb\000000.png --blend assets\models\moxing2.blend --out defect_dataset_generator\outputs\fitting\fit_real_candidate_dir_test_01 --candidates 5 --roi center --resize 512 --scoring real --candidate-dir defect_dataset_generator\outputs\dataset\black_spot_batch5_validation\rgb
```

Real scoring with automatic BlenderProc candidate rendering:

```powershell
python app.py fit-material --real defect_dataset_generator\outputs\fitting\render_candidate_test\very_rough.png --blend assets\models\moxing1_test.blend --out defect_dataset_generator\outputs\fitting\fit_render_candidates_test_01 --candidates 3 --scoring real --render-candidates --roi center --resize 512 --samples 8 --seed 100 --material-profile opaque_white_plastic
```

Real scoring with manual ROI and explicit render resolution:

```powershell
python app.py fit-material --real examples\my_project\QC71336_white_real_manual_labels_v2\images\all\9K9A0685.JPG --blend assets\models\QC7-1336-white.blend --out defect_dataset_generator\outputs\fitting\fit_manual_roi_schema_test_03 --candidates 3 --scoring real --render-candidates --roi manual --roi-box 1900,900,2200,1200 --resize 512 --samples 16 --seed 100 --material-profile opaque_white_plastic --render-width 512 --render-height 384
```

Plastic material score profile:

```powershell
python app.py fit-material --real examples\my_project\QC71336_white_real_manual_labels_v2\images\all\9K9A0685.JPG --blend assets\models\QC7-1336-white.blend --out defect_dataset_generator\outputs\fitting\fit_plastic_score_test_02 --candidates 3 --scoring real --render-candidates --roi manual --roi-box 1900,900,2200,1200 --resize 512 --samples 16 --seed 100 --material-profile opaque_white_plastic --render-width 512 --render-height 384 --score-profile plastic_material
```

## How Similarity Metrics Are Used

For each material candidate:

1. The candidate receives sampled material parameters from `config/material_search_space.json`.
2. With `--render-candidates`, the fitter writes `candidate_materials/candidate_000000.json` and calls `blender_scripts/render_candidate.py` through the local BlenderProc CLI.
3. The backend writes `candidate_renders/candidate_000000.png` and `candidate_metadata/candidate_000000.json`.
4. With `--candidate-dir`, the candidate is instead paired with an existing image by sorted filename order.
5. Each candidate image is compared with every reference image using `core/similarity_metrics.py`.
6. Per-reference `weighted_score` values are averaged.
7. Candidates are sorted by mean weighted score.
8. The highest-ranked candidate is written to `best_material.json`.

Current real metric backend:

```text
pillow_baseline
```

Score profiles:

- `baseline`: legacy generic image similarity with brightness, color histogram, SSIM, and edge/texture.
- `plastic_material`: technical-report-friendly visual material calibration score focused on ROI brightness, color tone, local contrast, highlight behavior, texture, and low-weight SSIM.

Mask ROI:

- `--roi mask` uses only pixels where `--roi-mask` is positive.
- If the mask and image sizes differ, the mask is resized consistently.
- Scoring metadata records `roi_mask`, `reference_mask_pixel_count`, `candidate_mask_pixel_count`, and `comparison_mask_pixel_count`.

Metrics:

- brightness
- color histogram
- global SSIM approximation
- edge/texture
- optional future LPIPS, currently `null`

Default scoring weights:

```text
brightness: 0.25
color_histogram: 0.30
ssim: 0.25
edge_texture: 0.20
lpips: 0.00
```

Plastic material weights:

```text
brightness_similarity: 0.25
color_similarity: 0.30
local_contrast_similarity: 0.15
highlight_similarity: 0.15
texture_similarity: 0.10
ssim_similarity: 0.05
```

## Candidate JSON Structure

`best_material.json` now uses schema `0.2` and separates visual calibration fields:

```json
{
  "schema_version": "0.2",
  "calibration_type": "visual_material_calibration",
  "material_parameters": {},
  "scene_calibration": {},
  "scoring": {}
}
```

## Use In Black-Spot Rendering

Schema `0.2` visual material calibration can now be passed to the first production black-spot backend with `--apply-material`:

```powershell
python defect_dataset_generator\app.py generate --blend assets\models\moxing2.blend --material defect_dataset_generator\outputs\fitting\fit_plastic_mask_roi_20_v2\best_material.json --defect-config defect_dataset_generator\config\black_spot_smoke.json --count 5 --out defect_dataset_generator\outputs\dataset\material_ablation_black_spot\fitted_material --backend-model QC71336_white --samples 16 --seed 300 --anchor-side front --apply-material
```

The backend uses only `material_parameters` for rendering. `scene_calibration` is currently recorded but not applied by `reference_blend_blackdot_multi_model.py`, and `scoring` fields are never used for rendering.

The default-material comparison command omits `--apply-material`, so the backend keeps its existing material behavior while using the same seeds and defect configuration.

`material_fit_candidates.json` records one entry per candidate. New code should prefer the separated fields:

```json
{
  "candidate_id": 0,
  "material_parameters": {},
  "scene_calibration": {},
  "scoring": {},
  "render_status": "success",
  "rank": 1,
  "params": {},
  "sampled_material_parameters": {},
  "material_json_path": "candidate_materials/candidate_000000.json",
  "render_path": "candidate.png",
  "metadata_path": "candidate_metadata/candidate_000000.json",
  "render_status": "success",
  "score": 0.93,
  "mean_weighted_score": 0.93,
  "per_metric_scores": {},
  "reference_images_used": [],
  "per_reference_similarity": [],
  "status": "success",
  "rank": 1
}
```

`status` can be:

- `success`
- `failed`
- `skipped`

## Current Limitations

- Automatic BlenderProc clean candidate rendering is connected and validated on a small 3-candidate run.
- In `real` mode, candidate images are assigned to material candidates by sorted filename order.
- Candidate render resolution is configurable through `--render-width` and `--render-height`; `--resize` controls similarity preprocessing.
- Manual ROI is interpreted as `x,y,w,h` in reference image pixels. Candidate renders use the same relative rectangle scaled to candidate image size.
- The current baseline uses global SSIM approximation, not full windowed SSIM.
- ROI defaults to `center`; `auto` should be validated on real reference photos before relying on it.
- LPIPS is not implemented yet and remains optional.
- Fitted material has been visually compared in a count-5 `black_spot` ablation run. This is appearance validation only and does not imply detector training improvement.

## Validation: Automatic Candidate Rendering

Validated command:

```powershell
python app.py fit-material --real defect_dataset_generator\outputs\fitting\render_candidate_test\very_rough.png --blend assets\models\moxing1_test.blend --out defect_dataset_generator\outputs\fitting\fit_render_candidates_test_01 --candidates 3 --scoring real --render-candidates --roi center --resize 512 --samples 8 --seed 100 --material-profile opaque_white_plastic
```

Observed output tree:

```text
defect_dataset_generator/outputs/fitting/fit_render_candidates_test_01/
  candidate_materials/
    candidate_000000.json
    candidate_000001.json
    candidate_000002.json
  candidate_renders/
    candidate_000000.png
    candidate_000001.png
    candidate_000002.png
  candidate_metadata/
    candidate_000000.json
    candidate_000000_render_log.txt
    candidate_000001.json
    candidate_000001_render_log.txt
    candidate_000002.json
    candidate_000002_render_log.txt
  best_material.json
  best_preview_render.json
  material_fit_candidates.json
  material_fitting_report.json
```

Validation result:

- 3 candidate material JSON files were created.
- 3 candidate PNG renders were created.
- 3 candidate metadata JSON files were created.
- `best_material.json` was created.
- `material_fit_candidates.json` ranked all 3 candidates.
- Best candidate in this run: `candidate_id=1`, score `0.974773`.

## Validation: Real Reference Photo

A real white plastic reference validation is documented in:

```text
docs/MATERIAL_FITTING_REAL_REFERENCE_VALIDATION.md
```

Validated command:

```powershell
python app.py fit-material --real examples\my_project\QC71336_white_real_manual_labels_v2\images\all\9K9A0685.JPG --blend assets\models\QC7-1336-white.blend --out defect_dataset_generator\outputs\fitting\fit_real_reference_test_01 --candidates 10 --scoring real --render-candidates --roi center --resize 512 --samples 16 --seed 100 --material-profile opaque_white_plastic
```

Observed result:

- 10 candidate material JSON files were created.
- 10 candidate PNG renders were created.
- 10 candidate metadata JSON files were created.
- `best_material.json`, `material_fit_candidates.json`, `material_fitting_report.json`, and `best_preview_render.json` were created.
- Best candidate: `candidate_id=6`, score `0.503981`.
- Contact sheet:
  - `outputs/fitting/fit_real_reference_test_01/visual_comparison/fit_real_reference_contact_sheet.jpg`

Important observation: the pipeline is working, but the real-photo score is modest because camera, crop, background, shadows, logo/text, and surface texture differ from the deterministic render. Treat the result as visually fitted, not physically accurate.

## Validation: Manual ROI Schema 0.2

Validated command:

```powershell
python app.py fit-material --real examples\my_project\QC71336_white_real_manual_labels_v2\images\all\9K9A0685.JPG --blend assets\models\QC7-1336-white.blend --out defect_dataset_generator\outputs\fitting\fit_manual_roi_schema_test_03 --candidates 3 --scoring real --render-candidates --roi manual --roi-box 1900,900,2200,1200 --resize 512 --samples 16 --seed 100 --material-profile opaque_white_plastic --render-width 512 --render-height 384
```

Observed result:

- `best_material.json` uses `schema_version: 0.2`.
- `material_parameters`, `scene_calibration`, and `scoring` are separated.
- Manual ROI is recorded as `[1900, 900, 2200, 1200]`.
- Render resolution is recorded as `[512, 384]`.
- No defect parameters are included in material calibration fields.
- Best candidate: `candidate_id=2`, score `0.574109`.

## Validation: Plastic Material Score

Plan:

```text
docs/MATERIAL_SCORING_METHOD_PLAN.md
```

Validation:

```text
docs/MATERIAL_SCORING_VALIDATION.md
```

Observed result from the 3-candidate fitting run:

- `score_profile: plastic_material`
- Best candidate: `candidate_id=2`
- Weighted score: `0.912317`
- The score is more explainable than the baseline, but validation showed it can still disagree with human judgment when candidate differences are subtle.

## Validation: Mask ROI

Mask ROI validation is documented in:

```text
docs/MATERIAL_MASK_ROI_VALIDATION.md
```

Validated command:

```powershell
python app.py fit-material --real examples\my_project\QC71336_white_real_manual_labels_v2\images\all\9K9A0685.JPG --blend assets\models\QC7-1336-white.blend --out defect_dataset_generator\outputs\fitting\fit_plastic_mask_roi_20_v2 --candidates 20 --scoring real --render-candidates --roi mask --roi-mask defect_dataset_generator\outputs\fitting\roi_masks\qc71336_9K9A0685_clean_plastic_rect_mask.png --resize 512 --samples 16 --seed 240 --material-profile opaque_white_plastic --render-width 512 --render-height 384 --score-profile plastic_material
```

Observed result:

- 20 candidates succeeded, 0 failed.
- Best candidate: `candidate_id=14`.
- Best score: `0.912231`.
- Mask pixel counts were recorded in scoring metadata.
- Manual ROI and mask ROI produced nearly identical rankings because the validation mask was an approximate rectangle matching the manual ROI.

## Next Step

Improve the automatic render path:

1. Add manual/material ROI support for real references.
2. Add camera/profile alignment before scoring.
3. Add render resolution options to the CLI.
4. Add model-profile driven target-object selection.
5. Keep `--candidate-dir` as a debug and recovery mode.
