# Black Dot Single-Defect 3k-5k Generation Handoff

Last updated: 2026-05-04

This handoff is for the next maintenance session. Scope is **single-defect black-dot generation only**. Do not include any same-scene multi-defect/cooccurrence combinations in this pass.

## Goal

Generate the black-dot single-defect portion of the final 3k-5k synthetic dataset according to the current rehearsal-plan ratios, using GPU rendering, front/back 1:1 side balance, domain randomization enabled, and manual RGB/mask confirmation that every accepted sample truly contains a visible black dot.

## Source Ratio

The active rehearsal plan is:

```text
E:\BlenderProject\BlenderProc\defect_dataset_generator\config\3k_5k_rehearsal_generation_plan_v1.json
```

In the 500-image rehearsal plan, each black-dot single-defect target has count `28`.

Therefore per target:

| Final dataset size | Count per black-dot target | Front | Back |
| ---: | ---: | ---: | ---: |
| 3000 | 168 | 84 | 84 |
| 4000 | 224 | 112 | 112 |
| 5000 | 280 | 140 | 140 |

Use the row matching the final dataset size requested by the user. If the final size is between 3000 and 5000, scale from `count = final_total * 28 / 500`, round to an even number, then split 1:1 front/back.

## Black-Dot Single Targets

| Target | Defect | Backend | Current status | Action |
| --- | --- | --- | --- | --- |
| `p101040_blue` | `black_dot` | `reference_blackdot` | Accepted for current single-defect black-dot plan, but still needs production spot checks and realism calibration if time allows. | Generate only after smoke confirms RGB/mask visibility for the requested side. |
| `qc71336_white` | `black_dot` | `reference_blackdot` | Passed front/back visual checks. | Generate. |
| `qc71336_gray` | `black_dot` | `reference_blackdot` | Passed front/back visual checks. | Generate. |
| `qc7_5244_white` | `black_dot` | `reference_blackdot` | Front/back accepted by the user. | Generate, with production spot checks. |
| `qc7_5244_black` | `black_dot` | `generic_main_plane` | Front/back accepted by the user after review. | Generate, with production spot checks. |

`qc71336_black` and `ql3_1052_black` are not black-dot targets in the current profile registry.

## Actual Generation Flow By Combination

The high-level command is `defect_dataset_generator\app.py generate-target`, but the next maintainer must verify the actual backend command in each `generation_plan.json`. For reference-backed black dots, `app.py` resolves the backend in:

```text
E:\BlenderProject\BlenderProc\defect_dataset_generator\app.py
```

Key functions:

```text
_run_target_defect_backend
_blackdot_backend_model
_blackdot_defect_config
```

The actual black-dot reference script is:

```text
E:\BlenderProject\BlenderProc\examples\my_project\reference_blend_blackdot_multi_model.py
```

It is launched through:

```text
E:\BlenderProject\BlenderProc\cli.py run ...reference_blend_blackdot_multi_model.py -- ...
```

The command builder is:

```text
E:\BlenderProject\BlenderProc\defect_dataset_generator\core\renderer.py
function: _build_reference_blackdot_batch_command
```

### Reference-Backed Black-Dot Combos

For each row, first run `--dry-run` or a tiny `--count 2` smoke and confirm `generation_plan.json` contains the expected script, backend model key, side, blend file, and preset parameters.

| Target/side | app target | Actual script | Actual backend `--model` | Blend/model source | Preset name | Required anchor side |
| --- | --- | --- | --- | --- | --- | --- |
| P101040 blue front | `p101040_blue` | `examples/my_project/reference_blend_blackdot_multi_model.py` | `P101040_blue` | `assets/models/moxing2.blend`; profile also records `assets/models/P101040.stl` | `p101040_blue_current_backend_v1` | `front` |
| P101040 blue back | `p101040_blue` | same | `P101040_blue` | same | same | `back`, only after smoke proves visible and supported |
| QC71336 white front | `qc71336_white` | same | `QC71336_white` | `assets/models/moxing2.blend`; profile records `assets/models/QC7-1336-white.blend` and `assets/models/QC7-1336.stl` | `qc71336_white_legacy_sync_v1` | `front` |
| QC71336 white back | `qc71336_white` | same | `QC71336_white` | same | same | `back` |
| QC71336 gray front | `qc71336_gray` | same | `QC71336_gray` | `assets/models/moxing2.blend`; profile records `assets/models/QC7-1336-white.blend`, gray override material mode, and `assets/models/QC7-1336.stl` | `qc71336_gray_legacy_sync_v1` | `front` |
| QC71336 gray back | `qc71336_gray` | same | `QC71336_gray` | same | same | `back` |
| QC7-5244 white front | `qc7_5244_white` | same | `QC75244_white` | `assets/models/moxing1_test.blend`; profile records `assets/models/QC7-5236.stl` | `qc7_5244_white_current_backend_v1` | `front` |
| QC7-5244 white back | `qc7_5244_white` | same | `QC75244_white` | same | same | `back`, only after back smoke proves visible |

Important: `qc7_5244_white` maps to backend model key `QC75244_white` for historical compatibility. Do not replace it with `qc7_5244_white` or `QC7_5244_white` in the backend command.

### Generic Black-Dot Combo

`qc7_5244_black black_dot` is different:

| Target/side | app target | Actual script | Backend | Blend/model/material source | Required anchor side |
| --- | --- | --- | --- | --- | --- |
| QC7-5244 black front | `qc7_5244_black` | `defect_dataset_generator/blender_scripts/render_generic_main_plane_defects.py` | `generic_main_plane` | `assets/models/moxing1_test.blend`, `assets/models/QC7-5236.stl`, material profile `defect_dataset_generator/config/qc7_5244_black_visual_material_candidate_v3.json` | `front` |
| QC7-5244 black back | `qc7_5244_black` | same | same | same | `back` |

This combo was previously blocked for weak visibility, but the user later
accepted front/back. Still run a tiny smoke before large production and inspect
RGB/mask manually.

## Preset Parameters To Verify Before Running

The active preset file is:

```text
E:\BlenderProject\BlenderProc\defect_dataset_generator\config\black_dot_appearance_presets.json
```

Verify these parameters are present in `generation_plan.json` under `black_dot_appearance_preset`, and in the backend command as `--black_dot_*` flags:

| Target | Preset | radius min/max | depth min/max |
| --- | --- | --- | --- |
| `p101040_blue` | `p101040_blue_current_backend_v1` | `0.0038` / `0.0042` | `0.0059` / `0.0065` |
| `qc71336_white` | `qc71336_white_legacy_sync_v1` | `0.00171` / `0.00209` | `0.00063` / `0.00076` |
| `qc71336_gray` | `qc71336_gray_legacy_sync_v1` | `0.0018` / `0.0032` | `0.00078` / `0.00135` |
| `qc7_5244_white` | `qc7_5244_white_current_backend_v1` | `0.0018` / `0.0034` | `0.00055` / `0.00115` |

If the command lacks these flags, stop and inspect `_blackdot_defect_config()` before rendering.

## Preflight Checks Before Each Combination

Before launching a production-size block, perform all checks below:

1. Confirm target exists:

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py list-targets
```

2. Confirm model files exist for that target:

```text
assets/models/moxing2.blend
assets/models/moxing1_test.blend
assets/models/P101040.stl
assets/models/QC7-1336.stl
assets/models/QC7-1336-white.blend
assets/models/QC7-5236.stl
defect_dataset_generator/config/qc7_5244_black_visual_material_candidate_v3.json
```

Only the relevant files for the current target must exist, but check paths explicitly.

3. Run a tiny smoke for the exact target and side:

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target <target> --defects black_dot --count 2 --out E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\blackdot_preflight_YYYYMMDD\single\<target>\black_dot\side_<side> --samples 8 --seed <seed> --anchor-sides <side>
```

4. Inspect the resulting `generation_plan.json`:

- `backend_script` matches the expected script above.
- `backend_model` matches the expected backend model key for reference-backed targets.
- `anchor_side` or `anchor_sides` matches the requested side.
- `blend_file` or command `--blend` matches the expected blend source.
- black-dot radius/depth parameters match the expected preset.
- `total_succeeded` equals the smoke count.

5. Open the smoke RGB/mask pair or a contact sheet and confirm the black dot is visible and mask-aligned before running the large command.

## Required Output Root

Use a new production root. Example:

```text
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\production_blackdot_single_YYYYMMDD
```

Use one folder per target and side:

```text
...\single\<target>\black_dot\side_front
...\single\<target>\black_dot\side_back
```

## Command Template

Use the project root:

```powershell
cd E:\BlenderProject\BlenderProc
```

Use the Python environment available for this project:

```powershell
D:\Anaconda\envs\defect_eval\python.exe
```

Use `--samples 24` for the final 3k-5k run unless the user explicitly asks for another value.

### Reference Black-Dot Targets

Run front and back as separate commands so the side ratio is exactly 1:1.

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target <target> --defects black_dot --count <front_count> --out E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\production_blackdot_single_YYYYMMDD\single\<target>\black_dot\side_front --samples 24 --seed <front_seed> --anchor-sides front
```

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target <target> --defects black_dot --count <back_count> --out E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\production_blackdot_single_YYYYMMDD\single\<target>\black_dot\side_back --samples 24 --seed <back_seed> --anchor-sides back
```

Replace `<target>` with:

```text
p101040_blue
qc71336_white
qc71336_gray
qc7_5244_white
```

### QC7-5244 Black

Run a small smoke before production because this combo had earlier visibility
issues, even though it is now accepted:

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target qc7_5244_black --defects black_dot --count 8 --out E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\blackdot_fix_smoke_YYYYMMDD\single\qc7_5244_black\black_dot\side_front --samples 16 --seed 51000 --anchor-sides front
```

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target qc7_5244_black --defects black_dot --count 8 --out E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\blackdot_fix_smoke_YYYYMMDD\single\qc7_5244_black\black_dot\side_back --samples 16 --seed 51100 --anchor-sides back
```

Proceed to production only after the new smoke confirms visible, correctly
located black dots on both sides.

## Seed Allocation

Use deterministic, non-overlapping seed ranges. Suggested final-production seeds:

| Target | Front seed | Back seed |
| --- | ---: | ---: |
| `p101040_blue` | 61000 | 61100 |
| `qc71336_white` | 62000 | 62100 |
| `qc71336_gray` | 63000 | 63100 |
| `qc7_5244_white` | 64000 | 64100 |
| `qc7_5244_black` | 65000 | 65100 |

If count exceeds 100, these ranges are still safe because each command increments seeds internally from the base seed. Do not reuse the 26000 rehearsal seed range for final production.

## GPU Requirement

Generation must use GPU rendering.

After every command, inspect:

```text
generation_plan.json
backend_run_log.json
metadata/*.json
```

Acceptance:

- `generation_plan.json` status is `rendered` or `partial` with all failed samples reviewed and excluded.
- Generic backend metadata must show `render_device_info.gpu_enabled = true`.
- Reference backend logs/metadata must show Cycles GPU with a non-CPU backend such as OPTIX or CUDA.
- If GPU is unavailable, stop and report. Do not continue a large CPU render.

## Domain Randomization Requirement

Confirm domain randomization is enabled for every block.

In `generation_plan.json`, verify:

```json
"camera": {"mode": "randomized"}
"lighting": {"mode": "randomized"}
"background": {"mode": "randomized"}
```

Also spot-check per-sample metadata if present. Camera, light, and background should vary across samples. If all samples appear identical except for the black dot, stop and inspect the backend before continuing.

## RGB/Mask Quality Check

Do not rely only on the automatic quality checks. For every target and side:

1. Create a contact sheet containing RGB next to mask for at least first/middle/last samples and several random samples.
2. Open the contact sheet and inspect it visually.
3. Confirm every accepted RGB image has a visible black dot on the plastic part.
4. Confirm every accepted mask has foreground exactly where the black dot is.
5. Confirm YOLO label bbox encloses the same dot and is not empty.
6. Compare sampled RGBs with the real black-dot references in:

```text
E:\BlenderProject\BlenderProc\缺陷图片
```

Relevant references:

```text
P-101040系列蓝色-黑点.JPG
QC7-5236系列白色-黑点.JPG
QC8-8511系列白色-黑点.JPG
QC8-8511系列白色背面-黑点.JPG
```

For already labeled real black-dot calibration data, use:

```text
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\calibration\p101040_blue_blackdot_real_labels_v1
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\calibration\qc71336_white_blackdot_real_labels_v1
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\calibration\qc71336_gray_blackdot_real_labels_v1
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\calibration\qc7_5244_white_blackdot_real_labels_v1
```

## Stop Conditions

Stop immediately and report if any of these occur:

- GPU is not used.
- Domain randomization is not recorded as enabled.
- Back-side generation fails or produces dots outside the visible product area.
- RGB image does not visibly contain a black dot.
- Mask is empty or does not align with the dot.
- More than 2 percent of a block fails automatic or manual inspection.
- `qc7_5244_black black_dot` is still too tiny/weak after tuning.

## Current Known Good Starting Point

The most recent manually reviewed black-dot subset is:

```text
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\passed_subset_rehearsal_ratio_20260503
```

Manual audit sheet:

```text
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\passed_subset_rehearsal_ratio_20260503\passed_subset_audit_contact_sheet.jpg
```

Observed results:

```text
p101040_blue black_dot front: 27/28, visually generates but realism/visibility needs care.
qc71336_white black_dot front/back: 14/14 + 14/14, accepted.
qc71336_gray black_dot front/back: 14/14 + 14/14, accepted.
qc7_5244_white black_dot front: 14/14, accepted; back still needs re-test.
qc7_5244_black black_dot: not accepted yet.
```
