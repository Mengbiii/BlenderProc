# Current Project Handoff

Last updated: 2026-05-04

This handoff is for the next maintenance session. The current project is a
BlenderProc-based synthetic defect dataset generator for plastic workpieces.
The immediate goal is now to continue safe 3k-5k dataset construction using
only user-accepted combinations, while preserving manual RGB/mask inspection as
the final acceptance gate.

For the newest usage-oriented handoff, also read:

```text
defect_dataset_generator/docs/SYSTEM_USAGE_GUIDE.md
defect_dataset_generator/docs/NEXT_HANDOFF_2026_05_04.md
```

## Current Priority

The current priority is:

1. Keep the existing target-specific scripts and profiles intact.
2. Continue 3k-5k dataset generation with GPU rendering.
3. Use only combinations manually accepted by the user.
4. Keep front/back at 1:1 for non-QL3 targets.
5. Keep front/side at 1:1 for QL3.
6. Inspect RGB and mask outputs after every block.
7. Use evaluation scripts only as support; do not replace manual inspection.

The user explicitly wants cautious changes. Many targets depend on specific scripts, material profiles, reference scenes, and model files. Do not replace a reference/specialized backend with a generic backend just for speed.

## Active Dataset Targets

The production target registry is:

```text
defect_dataset_generator/config/model_color_defect_targets.json
defect_dataset_generator/config/model_color_profiles.json
```

Active accepted combinations:

| Target | Active defects | Required sides | Current backend state |
| --- | --- | --- | --- |
| `p101040_blue` | `black_dot` | front/back where supported by command/profile | `reference_blackdot`; batch-optimized. Spot-check every production block. |
| `qc71336_black` | `foreign_material`, `splay`, `foreign_material+splay` | front/back | QC71336 black reference backend. Single defects and approved cooccurrence are connected to the dedicated reference script. |
| `qc71336_white` | `black_dot`, `foreign_material` | front/back | Black dot uses `reference_blackdot`; foreign material uses QC71336 white reference backend. User accepted the previously disputed foreign-material front/back cases. |
| `qc71336_gray` | `black_dot`, `mixed_color_contamination` | front/back | Black dot uses `reference_blackdot`; mixed color uses generic main-plane. User accepted mixed-color front/back after back-camera logic was corrected. |
| `qc7_5244_black` | `black_dot`, `foreign_material`, `splay`, `foreign_material+splay` | front/back | Generic main-plane with manual black material profile. User accepted black dot, foreign material, splay, and approved cooccurrence front/back. |
| `qc7_5244_white` | `black_dot`, `mixed_color_contamination` | front/back | Black dot uses `reference_blackdot`; mixed color uses specialized QC75244 mixed-color reference backend. User accepted black-dot back and mixed-color front/back. |
| `ql3_1052_black` | `foreign_material`, `splay` | front/side only | Generic main-plane using `QL3-black.blend`. User accepted defect appearance after placement bug was fixed. Cooccurrence is cancelled. |

Excluded:

| Defect | Reason |
| --- | --- |
| `sink_mark` | Intentionally excluded from the current 400-500 and later 3k-5k target set. Existing code is placeholder/fallback only. |

## Backend Routing

Main CLI:

```text
defect_dataset_generator/app.py
```

Production generation handoff docs:

```text
defect_dataset_generator/docs/BLACK_DOT_SINGLE_DEFECT_3K_5K_HANDOFF.md
defect_dataset_generator/docs/APPROVED_NON_BLACK_DEFECT_3K_FILLER_HANDOFF.md
defect_dataset_generator/docs/SYSTEM_USAGE_GUIDE.md
defect_dataset_generator/docs/NEXT_HANDOFF_2026_05_04.md
```

Primary commands:

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py list-targets
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target qc7_5244_black --defects black_dot --count 5 --samples 16 --seed 5501 --out defect_dataset_generator\outputs\dataset\smoke_YYYYMMDD
```

Routing summary:

| Target | Defect | Backend | Key script |
| --- | --- | --- | --- |
| `p101040_blue` | `black_dot` | `reference_blackdot` | `examples/my_project/reference_blend_blackdot_multi_model.py` |
| `qc71336_black` | `foreign_material` | `qc71336_black_reference` | `examples/my_project/reference_blend_qc71336_black_prebuilt_normal_debug.py` |
| `qc71336_black` | `splay` | `qc71336_black_reference` | `examples/my_project/reference_blend_qc71336_black_prebuilt_normal_debug.py` |
| `qc71336_black` | `foreign_material+splay` | `qc71336_black_reference_cooccurrence` | `examples/my_project/reference_blend_qc71336_black_prebuilt_normal_debug.py` |
| `qc71336_white` | `black_dot` | `reference_blackdot` | `examples/my_project/reference_blend_blackdot_multi_model.py` |
| `qc71336_white` | `foreign_material` | `qc71336_white_foreign_reference` | `examples/my_project/reference_blend_qc71336_white_prebuilt_normal_debug.py` |
| `qc71336_gray` | `black_dot` | `reference_blackdot` | `examples/my_project/reference_blend_blackdot_multi_model.py` |
| `qc71336_gray` | `mixed_color_contamination` | `generic_main_plane` | `defect_dataset_generator/blender_scripts/render_generic_main_plane_defects.py` |
| `qc7_5244_black` | `black_dot` | `generic_main_plane` | `defect_dataset_generator/blender_scripts/render_generic_main_plane_defects.py` |
| `qc7_5244_black` | `foreign_material` | `generic_main_plane` | `defect_dataset_generator/blender_scripts/render_generic_main_plane_defects.py` |
| `qc7_5244_black` | `splay` | `generic_main_plane` | `defect_dataset_generator/blender_scripts/render_generic_main_plane_defects.py` |
| `qc7_5244_white` | `black_dot` | `reference_blackdot` | `examples/my_project/reference_blend_blackdot_multi_model.py` |
| `qc7_5244_white` | `mixed_color_contamination` | `qc75244_mixed_color_reference` | `examples/my_project/reference_blend_qc75244_mixed_color_profile_debug.py` |
| `ql3_1052_black` | `foreign_material` | `generic_main_plane` | `defect_dataset_generator/blender_scripts/render_generic_main_plane_defects.py` |
| `ql3_1052_black` | `splay` | `generic_main_plane` | `defect_dataset_generator/blender_scripts/render_generic_main_plane_defects.py` |

## Recent Work Completed on 2026-05-02

### Side-controlled generation and camera follow

Side metadata and side-controlled placement were added or tightened for generation planning. The intent is:

- front/back cases are generated for all non-QL3 targets;
- QL3 uses front/side only;
- camera should follow the selected defect side so the defect is visible;
- when using a backside case, the model may be transformed rather than moving the whole environment.

Important caution: this area still needs visual verification. Earlier backside tests showed background occlusion and insufficient backside lighting in some images. Do not assume every side-controlled case is accepted until RGB/mask overlays are checked.

### Model transform control for backside capture

A model transform approach was introduced so backside capture can keep the camera/environment mostly unchanged and transform the model instead. The design goal is configurable transforms, not hard-coded 180 degrees:

- default backside behavior is a 180-degree flip;
- rotation angle and movement offsets should remain user-adjustable;
- this should be applied per target/profile only where it improves backside visibility.

This is a speed and stability direction, not fully accepted visual policy yet.

### Multi-defect co-occurrence generation

Same-scene multi-defect generation exists for generic-equivalent combinations. The important behavior:

- It creates multiple defect objects in one scene/image.
- It does not simply generate separate images per defect type.
- It uses the same generic defect creation logic as single-defect generation for generic defects.
- The output uses one merged mask and YOLO labels by default.

Current safe scope:

- `qc71336_black` can co-occur `foreign_material` and `splay` through the dedicated QC71336 black reference script. Use `generate-target-cooccurrence --target qc71336_black --defects foreign_material,splay`; it routes to `--defect_type foreign_material_splay`, not generic fallback.
- `qc7_5244_black` can co-occur `foreign_material` and `splay` through the generic backend.
- `ql3_1052_black` co-occurrence is cancelled for the current plan. Keep QL3 to single `foreign_material` and single `splay` front/side only.
- Black-dot-containing cooccurrence is not listed in the current plan and should not be run without new user approval.

Current caution:

- Mixed reference/specialized co-occurrence, for example `reference_blackdot + specialized_mixed_color`, is not fully converted into the persistent generic path. Keep those on existing scripts unless a specific adapter is implemented.

### Mask output policy optimization

Mask output is now configurable. Default production output should be:

- RGB;
- merged mask;
- YOLO label;
- metadata.

Class-specific masks should only be enabled for diagnosis by using `--render-class-masks` where supported. This is faster and avoids unnecessary per-class mask rendering in large runs.

Relevant files:

```text
defect_dataset_generator/blender_scripts/render_generic_main_plane_defects.py
defect_dataset_generator/blender_scripts/render_persistent_generic_batch.py
defect_dataset_generator/core/renderer.py
defect_dataset_generator/app.py
```

### Persistent generic batch renderer

A new persistent renderer exists:

```text
defect_dataset_generator/blender_scripts/render_persistent_generic_batch.py
```

CLI entry:

```text
defect_dataset_generator/app.py generate-target-persistent-batch
```

It loads the model/scene/material/camera/lights once, then loops through samples:

```text
start BlenderProc once
load model once
build base scene once
for each sample:
    clear/change defects
    update side/camera/seed
    render RGB/mask/label/metadata
exit
```

This is only for samples whose defect backend is `generic_main_plane`. The app intentionally rejects non-equivalent reference/specialized defects in this path.

### Reference black-dot batch optimization

`reference_blackdot` no longer needs one BlenderProc launch per image for count > 1. `run_reference_blackdot_backend` now uses one backend batch command with `--num count`, adapts all samples afterward, and runs per-sample quality checks.

Verified smoke:

```text
Output: defect_dataset_generator/outputs/dataset/blackdot_batch_opt_smoke_p101040_2
Target: p101040_blue
Defect: black_dot
Count: 2
Result: 2/2 quality checks passed
Renderer: GPU/OPTIX metadata observed
```

### Rehearsal generation plan optimization

The 400-500 image rehearsal runner now groups generic-equivalent blocks into persistent batches.

Tool:

```text
defect_dataset_generator/tools/run_rehearsal_generation_plan.py
```

New behavior:

- Generic-equivalent single/co-occurrence/normal samples can be grouped by `target + side`.
- Reference/specialized samples remain on existing commands.
- Use `--no-persistent-generic` to disable this optimization.

Plan-only comparison for a 500-image plan:

| Mode | Blocks | Total images |
| --- | ---: | ---: |
| legacy | 52 | 500 |
| persistent optimized | 36 | 500 |

In the optimized plan, 232 images were grouped into 13 persistent generic blocks.

Validated dry-run:

```text
Command: generate-target-persistent-batch
Target: qc7_5244_black
Side: front
Planned samples: 31
Included modes: single, cooccurrence, normal
Status: dry-run succeeded
```

## Current Defect Implementation Status

### `black_dot`

Status: implemented for active targets.

- `p101040_blue`, `qc71336_white`, `qc71336_gray`, and `qc7_5244_white` use `reference_blackdot`.
- `qc7_5244_black` uses generic main-plane black dot.
- `reference_blackdot` batch speed is improved.

Known issues:

- `qc7_5244_black black_dot` was previously too dark/too high contrast; it was made smaller/lighter and lighting was raised.
- `qc71336_gray black_dot` had oversized defects; parameters were reduced, but fresh evaluation is required.

### `foreign_material`

Status: implemented but target-dependent.

- `qc71336_black`: reference backend, size upper bound was reduced toward "large rice grain" scale.
- `qc71336_white`: reference backend.
- `qc7_5244_black`: generic main-plane. Front/back were manually accepted on 2026-05-03, including the `foreign_material+splay` cooccurrence samples.
- `ql3_1052_black`: generic main-plane. On 2026-05-03 the user accepted the defect appearance; a placement bug was fixed so explicit front/side requests now produce matching `anchor_side`, `camera_side`, and `main_plane_axis`.

Known issues:

- `qc71336_black foreign_material` previously had mask/RGB visibility mismatch in at least one sample.
- `ql3_1052_black foreign_material` previously ignored explicit front/side requests because the generic script forced this defect to side. This was fixed on 2026-05-03; front smoke now reports `anchor_side=front`, side smoke reports `anchor_side=side`.

### `splay`

Status: implemented. `qc71336_black` front/back is manually accepted after size limiting; other targets remain visually fragile.

- `qc71336_black`: reference backend. Desired appearance is a thin, light line/streak, not a large pale patch. On 2026-05-03 the user manually accepted the size-limited front/back samples even though the automatic `rgb_defect_bbox_visible` quality gate still failed; for this target/defect, manual RGB/mask inspection overrides that automatic visibility failure.
- `qc7_5244_black`: generic main-plane. Front/back were manually accepted on 2026-05-03, including the `foreign_material+splay` cooccurrence samples.
- `ql3_1052_black`: generic main-plane. On 2026-05-03 the user accepted the defect appearance; a placement bug was fixed so `splay` is not forced to front when `--anchor-sides side` is requested.

Known issues:

- `qc71336_black splay` previously regressed into a large pale blotch. The current size-limited version should stay as a fine scratch; do not increase its random length/width upper bounds without re-review.
- Automatic quality checks may mark accepted `qc71336_black splay` images as failed because RGB contrast is intentionally subtle. Keep RGB/mask contact-sheet review as the acceptance standard for this combination.
- `ql3_1052_black splay` previously ignored explicit side requests because the generic script forced this defect to front. This was fixed on 2026-05-03; front/side smoke images now show different faces and matching metadata.

### `qc71336_black foreign_material+splay` cooccurrence

Status: implemented and smoke-tested on 2026-05-03.

- Script: `examples/my_project/reference_blend_qc71336_black_prebuilt_normal_debug.py`
- App command: `python defect_dataset_generator/app.py generate-target-cooccurrence --target qc71336_black --defects foreign_material,splay --count N --out OUT --samples 16 --seed SEED --anchor-sides front` or `--anchor-sides back`.
- Internal script parameter: `--defect_type foreign_material_splay`.
- Output: one RGB, one merged mask, one YOLO txt with two rows (`1` for `foreign_material`, `2` for `splay`), and metadata containing both individual defect records.
- Smoke outputs:
  - Direct front/back visual review: `defect_dataset_generator/outputs/dataset/_user_review_qc71336_black_cooccurrence_20260503/`
  - App-entry smoke: `defect_dataset_generator/outputs/dataset/_user_review_qc71336_black_cooccurrence_app2_20260503/`
- Manual visual result: front/back RGB and mask both contain a point-like foreign material and a fine splay scratch. The 60px bbox crop sheet confirms the foreign material exists in RGB as well as mask.
- Important batching note: for strict 1:1 front/back ratio, run separate front and back batches with separate `--anchor-sides front` and `--anchor-sides back` commands, then merge outputs. A mixed `--anchor-sides front back` request does not guarantee exact alternation for this reference script.

### `mixed_color_contamination`

Status: connected; accepted for the currently reviewed targets listed below.

- `qc71336_gray`: generic main-plane. On 2026-05-03 the user manually accepted both front and back samples. The back sample previously rendered mostly background because `GENERIC_REFERENCE_BACKDROP` stayed between the back camera and model; `render_generic_main_plane_defects.py` now repositions the QC71336 gray reference backdrop behind the current camera side and records `view_transform.camera_side=back` for back captures. The accepted back sample may still fail `rgb_defect_bbox_visible`; manual RGB/mask review overrides that automatic visibility failure for this combination.
- `qc7_5244_white`: specialized QC75244 mixed-color reference backend. Front/back samples were manually accepted on 2026-05-03.

Known issues:

- `qc71336_gray mixed_color_contamination` once produced an all-white RGB with no mask defect in one image while other images were normal.
- `qc7_5244_white mixed_color_contamination` was too large and too yellow; after prior size/color changes, front/back smoke samples were manually accepted on 2026-05-03.

## Known Open Problems

1. Backside lighting may be insufficient.
   - Earlier backside evaluations showed darker images.
   - Need determine whether this is light position, model flip orientation, material response, or intensity.
   - Avoid blindly raising all lights; preserve accepted front-side appearance.

2. Background can occlude the model when backside transforms are used.
   - Some RGB images were blocked by the background plane.
   - Background placement must be side-aware or model-transform-aware.

3. Some generated images have no RGB output or no visible defect.
   - Check backend logs and metadata before rerunning large batches.
   - RGB/mask/YOLO/metadata structural checks should remain mandatory.

4. Mask/RGB alignment still needs stricter review.
   - Quality checks now include mask foreground statistics and RGB defect-bbox visibility, but visual overlays are still necessary.

5. Reference/specialized co-occurrence is not fully persistent-batch optimized.
   - Generic co-occurrence is available.
   - Mixed backend combinations should stay on old scripts until a target-specific adapter exists.
   - `ql3_1052_black` co-occurrence is explicitly out of scope for the current dataset plan.

6. Metrics are useful but not final proof of realism.
   - Current image/defect metrics can support comparison and tuning.
   - They should not replace manual review, especially for faint defects and ambiguous real labels.

## Real Dataset and Labeling State

Real dataset root:

```text
E:\BlenderProject\BlenderProc\塑料工件真实数据集
```

User's labeling policy:

- Real images are being manually sorted by model/color/defect type.
- Normal images are kept separately.
- Visible defects should receive coarse L1 boxes.
- Images with original image but no red-box/manual annotation are considered low-confidence samples.
- Ambiguous or incomplete defects may be marked/handled as:
  - `visibility=ambiguous`
  - `coverage=partial`
  - `confidence=low`

Existing reference script to study:

```text
examples/my_project/prepare_qc71336_real_labels_from_manual_bbox.py
```

Do not assume every real defect can be perfectly labeled. Some defects are faint, partial, or ambiguous even to humans.

## Evaluation Tools

Existing tools:

```text
defect_dataset_generator/tools/evaluate_synthetic_image_quality.py
defect_dataset_generator/tools/evaluate_defect_realism.py
defect_dataset_generator/tools/validate_smoke_pair.py
defect_dataset_generator/tools/validate_defect_plans.py
defect_dataset_generator/tools/audit_yolo_dataset_labels.py
```

Use these before detector training. YOLO is not the primary tuning metric at this stage.

Recommended evaluation order:

1. Structural validation:
   - RGB exists and is nonblank.
   - Mask exists and foreground is nonempty for defect images.
   - YOLO labels exist where expected.
   - Metadata records target, defects, side, seed, camera, light, material profile, and output paths.

2. RGB/mask/label overlay review:
   - Confirm the defect is actually on the model.
   - Confirm the mask aligns with visible RGB defect.
   - Confirm the label is roughly around the visible defect.

3. Image-quality metrics:
   - exposure/brightness;
   - contrast;
   - background/model visibility;
   - blur/noise/texture statistics;
   - real-vs-synthetic distribution comparison per target/color.

4. Defect-realism metrics:
   - bbox/mask size distribution;
   - local contrast;
   - color delta;
   - shape/elongation;
   - edge softness;
   - defect position distribution.

## Recommended Next Steps

### Step 1: Run small persistent generic smoke

Run one or two 20-30 image batches before the full 400-500 plan:

- `qc7_5244_black` persistent generic batch;
- `ql3_1052_black` persistent generic batch, single defects only, front/side only; do not include QL3 co-occurrence.

Check RGB/mask/YOLO/metadata and contact sheets.

### Step 2: Run reference black-dot speed smoke

Run 10-20 images for:

- `p101040_blue black_dot`;
- `qc71336_gray black_dot`;
- `qc71336_white black_dot`;
- `qc7_5244_white black_dot`.

Confirm the batch path still preserves original visual behavior.

### Step 3: Rebuild the 400-500 rehearsal plan

Use:

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\tools\run_rehearsal_generation_plan.py --out defect_dataset_generator\outputs\dataset\rehearsal_500_YYYYMMDD --samples 16 --plan-only
```

Then run a dry-run or limited block subset. If suspicious, compare with:

```powershell
--no-persistent-generic
```

### Step 4: Full 400-500 generation

Only after small smoke passes, run the 400-500 set. Make sure GPU rendering is used. Store logs and plan JSONs.

### Step 5: Evaluate and produce optimization table

For every target + defect:

- pass/fail structural validation;
- visual review notes;
- image quality metric summary;
- defect realism metric summary;
- next parameter action.

Do not do broad parameter rewrites. Apply small, target-specific fixes.

## Commands Worth Keeping

List targets:

```powershell
cd E:\BlenderProject\BlenderProc
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py list-targets
```

Validate plans:

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\tools\validate_defect_plans.py
```

Example single target generation:

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target qc7_5244_black --defects black_dot --count 10 --samples 16 --seed 5501 --out defect_dataset_generator\outputs\dataset\smoke_qc7_5244_black_blackdot_YYYYMMDD
```

Example persistent generic batch dry-run:

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target-persistent-batch --target qc7_5244_black --plan defect_dataset_generator\outputs\dataset\_planonly_rehearsal_persistent_opt\_persistent_batch_plans\qc7_5244_black__side_front.json --out defect_dataset_generator\outputs\dataset\_dryrun_persistent_qc7_front --samples 4 --dry-run
```

Example rehearsal plan:

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\tools\run_rehearsal_generation_plan.py --out defect_dataset_generator\outputs\dataset\rehearsal_500_YYYYMMDD --samples 16 --plan-only
```

## Do Not Do Next

- Do not launch the 3k-5k batch before the 400-500 pilot passes checks.
- Do not optimize by replacing reference/specialized backends with generic generation.
- Do not reintroduce `sink_mark`.
- Do not treat `QC75244_white` as a separate physical target; it is a historical backend key.
- Do not assume backside samples are correct until RGB/mask overlay review confirms them.
- Do not use YOLO training as the main quality proof at this stage.
