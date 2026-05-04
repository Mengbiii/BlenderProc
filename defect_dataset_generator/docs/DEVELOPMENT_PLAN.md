# Development Plan

## Priority Order

1. Project framework and CLI
2. File management and config schema
3. Model/color profile registry and clean geometry baseline checks
4. Profile/preset driven default generation path
5. Domain randomization defaults and user override hooks
6. Defect generation integration
7. Batch rendering
8. Label and metadata export
9. Optional material fitting/calibration
10. Optional defect realism optimization
11. Similarity metrics and visual reports
12. GUI prototype

## Current Flow Decision

The default production path should prioritize reliable generation across model-color targets and defect classes. Automatic material fitting and defect realism optimization are optional calibration modules, not required startup steps.

Default generation uses:

- embedded model material or manually prepared material profile;
- base defect presets plus explicit user overrides;
- model-color placement/camera/light constraints;
- defect placement limited to front/back main planes by default;
- light domain randomization enabled by default.

Optional optimization uses:

- material fitting to produce `best_material.json` only when requested;
- defect-realism evaluation or fitting to promote better defect presets after small smoke batches.

## 1. Input/File Management Module

- Goal: manage real images, model files, configs, and output folders safely on Windows.
- Input: image path/folder, `.blend` path, optional preset JSON, output folder.
- Output: validated paths and normalized config dictionaries.
- Current state: basic path resolution, reference image discovery, `.blend` validation, and project inspection are implemented.
- Next implementation tasks: add config schema validation, known model registry, output overwrite policy, and readable error messages.
- Risks: inconsistent historical naming such as `QC75236` vs `QC75244`; accidental use of large output folders as inputs.
- Priority: high.

## 2. Material Defaults and Optional Material Fitting

- Goal: use embedded or manually prepared material profiles by default, and search material parameters only as an optional calibration step.
- Input: reference images, clean `.blend`, material search space.
- Output: `best_material.json`, candidate scores, best preview render.
- Current state: mock scoring remains available, real scoring works through `--candidate-dir`, and `--scoring real --render-candidates` now calls BlenderProc candidate rendering, saves candidate material/render/metadata files, scores each render, ranks candidates, and writes `best_material.json` plus reports. Schema `0.2` separates `material_parameters`, `scene_calibration`, and `scoring`. The fitter supports `--score-profile baseline|plastic_material`, manual ROI, and mask ROI. A 20-candidate manual/mask ROI validation has been completed. QC7-5244 black material fitting is currently diagnostic only because the clean render profile still maps to a QC7-5236 STL pipeline.
- Next implementation tasks: add a material-source resolver with `embedded_in_blend`, `manual_profile`, and `fitted_best_material`; fix model/profile alignment before accepting any QC7-5244 material; replace approximate rectangular masks with true material masks; align candidate camera/profile with real reference photos; add model-profile target-object selection; and broaden validation of the plastic material score.
- Risks: render time can explode; translucent P101040 and opaque QC parts need different search spaces; background/camera mismatch can dominate metric scores and score spreads can remain small even after ROI improvements.
- Priority: high.

## 2b. Clean Model/Profile Baseline

- Goal: verify that a model-color profile imports the intended geometry and renders a structurally plausible clean part before material or defect work starts.
- Input: backend profile/model id, optional `.blend` path, render size/samples.
- Output: clean baseline PNG, saved debug `.blend`, metadata with imported source paths and object summaries.
- Current state: `blender_scripts/render_clean_import_baseline.py` exists. A no-defect/no-external-material render for `QC75244_white` was written to `outputs/dataset/qc7_5244_clean_import_baseline_no_defect/`. Metadata shows this profile currently imports `assets/models/QC7-5236.stl`, and the clean image already shows structural mismatch.
- Next implementation tasks: identify the correct QC7-5244 STL/blend assets, update or create a correct QC7-5244 model profile, rerun clean baseline, and only then resume material/defect tuning.
- Risks: historical names such as `QC75244`, `QC7-5244`, and `QC7-5236` can be confused; a material fit can appear successful while compensating for the wrong geometry or camera.
- Priority: urgent.

## 2a. Candidate Rendering Backend

- Goal: render deterministic clean candidate images for material fitting.
- Input: clean `.blend`, material parameter JSON, output image path, metadata path.
- Output: candidate PNG and render metadata JSON.
- Current state: `blender_scripts/render_candidate.py` is implemented, validated with very rough, smooth, and bright/dark parameter sets, and connected to `core/material_fitter.py` for small automatic candidate batches. Procedural Noise Texture + Bump is connected when `noise_strength` or `bump_strength` is positive.
- Next implementation tasks: validate bump visibility at target camera distance and validate target-object selection across more `.blend` files.
- Risks: automatic target-object selection may need model-profile configuration for complex scenes.
- Priority: high.

## 3. Similarity Metrics Module

- Goal: compare real and synthetic images using brightness, color, SSIM, edge/texture, and optional LPIPS.
- Input: real image and candidate render.
- Output: per-metric score and weighted score.
- Current state: Pillow baseline is implemented with brightness, color histogram, global SSIM approximation, edge/texture, ROI modes including manual ROI and mask ROI, CLI, JSON output, and validation. The `plastic_material` profile adds brightness, color, local contrast, highlight, texture, and low-weight SSIM components with technical reporting documentation.
- Next implementation tasks: validate true material-mask ROI behavior on more real reference photos, consider CIELAB Delta E, improve highlight discrimination, and keep LPIPS optional.
- Risks: comparing whole images can reward background instead of product material; ROI selection is essential; the current plastic score can still disagree with human judgment for subtle candidates.
- Priority: high.

## 4. Defect Generation Module

- Goal: provide a shared schema and backend hooks for black dot, mixed color, foreign material, splay, sink/dent, short shot, and flash where possible.
- Input: defect config JSON and model/material context.
- Output: BlenderProc defect objects/material changes plus masks and bbox metadata.
- Current state: schema normalization is in the new framework; the first production black-spot backend is connected through an adapter. The backend can optionally consume a fitted visual material JSON through `--apply-material` without changing defect geometry or labels. Black-dot appearance parameters are now preset-driven through `config/black_dot_appearance_presets.json` and `app.py generate --defect-preset`. For QC7-5244 black, clean baseline validation currently blocks further defect generation because the active profile appears to use the wrong STL.
- Next implementation tasks: first fix QC7-5244 model/profile alignment. Then make default generation use base defect presets plus explicit user overrides, with defect optimization treated as optional. Default placement should stay within front/back main-plane zones; side walls, holes, bevels, and complex edges require explicit opt-in after smoke validation. For already aligned targets, run count=3 to count=5 preset smoke renders per defect class, verify labels/masks/metadata, then scale in chunks.
- Risks: class boundaries can blur, especially mixed color vs foreign material vs splay.
- Priority: high.

## 4a. Defect Realism Evaluation Module

- Goal: evaluate generated defect appearance against real defect crops without YOLO.
- Input: real images/labels, synthetic dataset with `rgb/`, `masks/`, `labels_yolo/`, optional real dataset root scan.
- Output: `defect_realism_summary.json`, `defect_realism_per_sample.csv`, contact sheet, and Markdown report.
- Current state: `tools/evaluate_defect_realism.py` supports real dataset root scanning and a first `black_dot` crop-level adapter. QC71336 white black-dot real labels were prepared under `outputs/calibration/qc71336_white_blackdot_real_labels_v1`.
- Next implementation tasks: run a count=5 synthetic preset smoke; add real mask support for non-point defects; add mixed color, foreign material, and splay adapters.
- Risks: real bbox labels are localization hints, not true masks; metric proxies must be paired with visual contact sheets.
- Priority: high.

## 5. Domain Randomization Module

- Goal: enable conservative domain randomization by default while letting users fix or override exact values/ranges when needed.
- Input: mode, optional model-color profile defaults, optional user ranges or fixed values.
- Output: camera, light, and background randomization config recorded in generation plans and per-image metadata.
- Current state: simple config builders exist for camera and light; default ranges have been narrowed to light domain randomization. Background randomization config has been added.
- Default policy:
  - lighting strength jitter: +/-20%;
  - light direction jitter: slight change, currently +/-8 degrees;
  - camera angle jitter: roughly +/-5 to +/-15 degrees depending on axis;
  - camera distance jitter: slight change, currently +/-5%;
  - background: slight neutral RGB variation, currently +/-0.03 per channel.
- Next implementation tasks: pass sampled values into every BlenderProc backend, record final sampled values per image, and let model-color profiles override ranges for fragile targets.
- Risks: random views may hide defects or leave the product out of frame, so ranges should stay conservative until each profile has passed smoke validation.
- Priority: high.

## 6. Batch Rendering Module

- Goal: load calibrated material, apply defects, render N images, and save outputs.
- Input: `.blend`, material JSON, defect config, count, output folder.
- Output: RGB images, masks, labels, metadata, summary.
- Current state: `black_spot` / `black_dot` can call `examples/my_project/reference_blend_blackdot_multi_model.py` through the local BlenderProc CLI (`python cli.py run`) and adapt outputs into the new framework folders. Controlled count=1/count=5 runs are validated. Each sample uses a different seed and failed samples retry once. A count=20 training-oriented ablation dataset was generated for `QC71336_white` with identical seeds and identical bbox sequence for default vs fitted material batches. A first GPU YOLOv8n synthetic-only training comparison and fixed real QC71336 test validation have been completed; both synthetic-only models scored zero on real test.
- Next implementation tasks: run a real-only vs real+synthetic comparison on the fixed QC71336 real test split, validate the material override on more model presets, keep count small until visual output is stable, add clearer progress output, then decide a cautious upper bound for production batches.
- Risks: BlenderProc startup cost, GPU/CPU fallback, failed samples, and long-running batches.
- Priority: medium.

## 7. Export Module

- Goal: export YOLO labels, masks, per-image metadata, and dataset summary.
- Input: render metadata, masks, bbox coordinates.
- Output: `labels_yolo`, `masks`, `metadata`, `dataset_summary.json`.
- Current state: summary writer and YOLO label helper skeleton exist; the black-dot backend adapter copies RGB, mask, YOLO label, and per-image metadata into the new folder layout. Quality checks verify file readability, RGB/mask size alignment, non-empty labels, and YOLO bbox values in 0-1. The count=20 material ablation writes `dataset_quality_report.json`, contact sheets, and YOLO-ready 80/20 split folders.
- Next implementation tasks: validate class ID policy on more model profiles, add optional COCO export, and make aggregate summaries richer inside the framework rather than ad hoc validation scripts.
- Risks: support artifacts must not become training labels unless explicitly configured.
- Priority: medium.

## 8. GUI / CLI Module

- Goal: provide reliable command-line workflows first, then a GUI prototype later.
- Input: user commands and config files.
- Output: runnable workflows for inspect, material fitting, preview, and generation.
- Current state: CLI skeleton is implemented.
- Next implementation tasks: add `--dry-run`, backend render execution flags, and examples.
- Risks: GUI can distract from stabilizing the rendering backend.
- Priority: CLI high, GUI low.

## Example: Single Black-Spot Render Through The Real Backend

Run from:

```powershell
cd E:\BlenderProject\BlenderProc\defect_dataset_generator
```

Command:

```powershell
python app.py generate --blend assets\models\moxing2.blend --material defect_dataset_generator\outputs\fitting\smoke_fit\best_material.json --defect-config defect_dataset_generator\config\black_spot_smoke.json --count 1 --out defect_dataset_generator\outputs\dataset\real_black_spot_smoke --backend-model P101040_blue --samples 16 --seed 41 --anchor-side front
```

Expected adapted outputs:

```text
defect_dataset_generator/outputs/dataset/real_black_spot_smoke/
  rgb/000000.png
  masks/000000.png
  labels_yolo/000000.txt
  metadata/000000.json
  backend_metadata.json
  backend_run_log.json
  generation_plan.json
  dataset_summary.json
```

## Example: Controlled Count-5 Black-Spot Batch

```powershell
python app.py generate --blend assets\models\moxing2.blend --material defect_dataset_generator\outputs\fitting\smoke_fit\best_material.json --defect-config defect_dataset_generator\config\black_spot_smoke.json --count 5 --out defect_dataset_generator\outputs\dataset\black_spot_batch5_validation --backend-model P101040_blue --samples 16 --seed 41 --anchor-side front
```

The wrapper runs five one-sample backend calls with seeds `41, 42, 43, 44, 45`, retries each failed sample once, and writes `failed_samples` in `dataset_summary.json` if a sample still fails.

## Example: Count-5 Black-Spot Fitted-Material Ablation

Default backend material:

```powershell
python defect_dataset_generator\app.py generate --blend assets\models\moxing2.blend --material defect_dataset_generator\outputs\fitting\fit_plastic_mask_roi_20_v2\best_material.json --defect-config defect_dataset_generator\config\black_spot_smoke.json --count 5 --out defect_dataset_generator\outputs\dataset\material_ablation_black_spot\default_material --backend-model QC71336_white --samples 16 --seed 300 --anchor-side front
```

Fitted material override:

```powershell
python defect_dataset_generator\app.py generate --blend assets\models\moxing2.blend --material defect_dataset_generator\outputs\fitting\fit_plastic_mask_roi_20_v2\best_material.json --defect-config defect_dataset_generator\config\black_spot_smoke.json --count 5 --out defect_dataset_generator\outputs\dataset\material_ablation_black_spot\fitted_material --backend-model QC71336_white --samples 16 --seed 300 --anchor-side front --apply-material
```

Comparison outputs are written under:

```text
defect_dataset_generator/outputs/dataset/material_ablation_black_spot/
```

## Example: Count-20 Training-Oriented Material Dataset Ablation

Default backend material:

```powershell
python defect_dataset_generator\app.py generate --blend assets\models\moxing2.blend --material defect_dataset_generator\outputs\fitting\fit_plastic_mask_roi_20_v2\best_material.json --defect-config defect_dataset_generator\config\black_spot_smoke.json --count 20 --out defect_dataset_generator\outputs\dataset\black_spot_ablation_train\default_material --backend-model QC71336_white --samples 16 --seed 500 --anchor-side front
```

Fitted material override:

```powershell
python defect_dataset_generator\app.py generate --blend assets\models\moxing2.blend --material defect_dataset_generator\outputs\fitting\fit_plastic_mask_roi_20_v2\best_material.json --defect-config defect_dataset_generator\config\black_spot_smoke.json --count 20 --out defect_dataset_generator\outputs\dataset\black_spot_ablation_train\fitted_material --backend-model QC71336_white --samples 16 --seed 500 --anchor-side front --apply-material
```

The generated datasets include `dataset_quality_report.json`, contact sheets, and YOLO-ready 80/20 split folders. No training was run in this step.
