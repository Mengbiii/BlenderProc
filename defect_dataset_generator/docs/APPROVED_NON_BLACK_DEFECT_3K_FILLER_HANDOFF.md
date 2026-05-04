# Approved Non-Black Defect 3k Filler Generation Handoff

Last updated: 2026-05-04

This handoff is for the next maintenance session. Scope is the approved non-black-dot defect portion of the final 3k-5k synthetic dataset, plus the approved same-scene non-black cooccurrence blocks.

This document is a companion to:

```text
E:\BlenderProject\BlenderProc\defect_dataset_generator\docs\BLACK_DOT_SINGLE_DEFECT_3K_5K_HANDOFF.md
```

Do not change the black-dot single-defect counts that are already running. Use this plan to fill the remaining images needed to reach the 3k minimum line.

## Goal

Generate only combinations that the user has manually accepted as passing. Use
GPU rendering, keep domain randomization enabled, split front/back or front/side
in exact 1:1 blocks, and manually inspect RGB and mask outputs after every
block.

As of 2026-05-04, this document remains the active non-black filler plan. The UI
cooccurrence selector is intentionally limited to the two cooccurrence rows in
this document.

## Current Scope Rules

- Include only combinations listed in this document.
- Do not include `sink_mark`.
- Do not include `ql3_1052_black` cooccurrence.
- Do not invent mixed backend cooccurrence combinations.
- Run front/back or front/side as separate commands so side balance is exact.
- For QL3, use `front` and `side` only; QL3 has no back-side plan.
- For strict dataset accounting, treat this plan as a filler after black-dot generation finishes.

## Recommended Filler Size

This plan supplies `1780` non-black images:

| Section | Count |
| --- | ---: |
| Non-black single defects | 1300 |
| Approved non-black cooccurrence | 480 |
| Total filler | 1780 |

After the black-dot run finishes, compute:

```text
final_total = black_dot_completed_count + 1780
```

If `final_total < 3000`, add top-up images from the Top-Up Priority section below. If `final_total > 3000`, keep the extra samples unless the user explicitly requests exactly 3000; the allowed final dataset target is 3k-5k.

## Approved Single-Defect Allocation

| Target | Defect | Total | Side split | Backend | Script |
| --- | --- | ---: | --- | --- | --- |
| `qc71336_black` | `foreign_material` | 160 | 80 front / 80 back | `qc71336_black_reference` | `examples/my_project/reference_blend_qc71336_black_prebuilt_normal_debug.py` |
| `qc71336_black` | `splay` | 160 | 80 front / 80 back | `qc71336_black_reference` | `examples/my_project/reference_blend_qc71336_black_prebuilt_normal_debug.py` |
| `qc71336_white` | `foreign_material` | 180 | 90 front / 90 back | `qc71336_white_foreign_reference` | `examples/my_project/reference_blend_qc71336_white_prebuilt_normal_debug.py` |
| `qc71336_gray` | `mixed_color_contamination` | 160 | 80 front / 80 back | `generic_main_plane` | `defect_dataset_generator/blender_scripts/render_generic_main_plane_defects.py` |
| `qc7_5244_black` | `foreign_material` | 140 | 70 front / 70 back | `generic_main_plane` | `defect_dataset_generator/blender_scripts/render_generic_main_plane_defects.py` |
| `qc7_5244_black` | `splay` | 140 | 70 front / 70 back | `generic_main_plane` | `defect_dataset_generator/blender_scripts/render_generic_main_plane_defects.py` |
| `qc7_5244_white` | `mixed_color_contamination` | 160 | 80 front / 80 back | `qc75244_mixed_color_reference` | `examples/my_project/reference_blend_qc75244_mixed_color_profile_debug.py` |
| `ql3_1052_black` | `foreign_material` | 100 | 50 front / 50 side | `generic_main_plane` | `defect_dataset_generator/blender_scripts/render_generic_main_plane_defects.py` |
| `ql3_1052_black` | `splay` | 100 | 50 front / 50 side | `generic_main_plane` | `defect_dataset_generator/blender_scripts/render_generic_main_plane_defects.py` |

Single-defect subtotal: `1300`.

## Approved Cooccurrence Allocation

| Target | Defects | Total | Side split | Backend | Script |
| --- | --- | ---: | --- | --- | --- |
| `qc71336_black` | `foreign_material,splay` | 240 | 120 front / 120 back | `qc71336_black_reference_cooccurrence` | `examples/my_project/reference_blend_qc71336_black_prebuilt_normal_debug.py` |
| `qc7_5244_black` | `foreign_material,splay` | 240 | 120 front / 120 back | `generic_main_plane` | `defect_dataset_generator/blender_scripts/render_generic_main_plane_defects.py` |

Cooccurrence subtotal: `480`.

Do not run:

```text
ql3_1052_black foreign_material+splay cooccurrence
```

It is explicitly cancelled for the current dataset plan.

## Production Output Root

Use a root distinct from the black-dot output root:

```text
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\production_non_black_filler_YYYYMMDD
```

Recommended folder layout:

```text
...\single\<target>\<defect>\side_front
...\single\<target>\<defect>\side_back
...\single\<target>\<defect>\side_side
...\cooccurrence\<target>\<defect_combo>\side_front
...\cooccurrence\<target>\<defect_combo>\side_back
```

## Command Templates

Run from:

```powershell
cd E:\BlenderProject\BlenderProc
```

Use:

```powershell
D:\Anaconda\envs\defect_eval\python.exe
```

Use `--samples 24` for final production unless the user asks for speed over quality. Use `--samples 16` only for smoke or urgent top-up runs.

### Single-Defect Template

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target <target> --defects <defect> --count <count> --out E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\production_non_black_filler_YYYYMMDD\single\<target>\<defect>\side_<side> --samples 24 --seed <seed> --anchor-sides <side>
```

### Cooccurrence Template

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target-cooccurrence --target <target> --defects <defect_a>,<defect_b> --count <count> --out E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\production_non_black_filler_YYYYMMDD\cooccurrence\<target>\<defect_a>_<defect_b>\side_<side> --samples 24 --seed <seed> --anchor-sides <side>
```

For `qc71336_black foreign_material,splay`, verify that `generation_plan.json` routes to:

```text
examples/my_project/reference_blend_qc71336_black_prebuilt_normal_debug.py
--defect_type foreign_material_splay
```

For `qc7_5244_black foreign_material,splay`, verify that the generic backend output contains two defect records and two YOLO label rows.

## Exact Production Commands

Use non-overlapping seed ranges. The commands below are deliberately side-specific.

### `qc71336_black foreign_material`

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target qc71336_black --defects foreign_material --count 80 --out E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\production_non_black_filler_YYYYMMDD\single\qc71336_black\foreign_material\side_front --samples 24 --seed 71000 --anchor-sides front
```

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target qc71336_black --defects foreign_material --count 80 --out E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\production_non_black_filler_YYYYMMDD\single\qc71336_black\foreign_material\side_back --samples 24 --seed 71100 --anchor-sides back
```

### `qc71336_black splay`

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target qc71336_black --defects splay --count 80 --out E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\production_non_black_filler_YYYYMMDD\single\qc71336_black\splay\side_front --samples 24 --seed 71200 --anchor-sides front
```

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target qc71336_black --defects splay --count 80 --out E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\production_non_black_filler_YYYYMMDD\single\qc71336_black\splay\side_back --samples 24 --seed 71300 --anchor-sides back
```

### `qc71336_white foreign_material`

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target qc71336_white --defects foreign_material --count 90 --out E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\production_non_black_filler_YYYYMMDD\single\qc71336_white\foreign_material\side_front --samples 24 --seed 72000 --anchor-sides front
```

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target qc71336_white --defects foreign_material --count 90 --out E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\production_non_black_filler_YYYYMMDD\single\qc71336_white\foreign_material\side_back --samples 24 --seed 72100 --anchor-sides back
```

### `qc71336_gray mixed_color_contamination`

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target qc71336_gray --defects mixed_color_contamination --count 80 --out E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\production_non_black_filler_YYYYMMDD\single\qc71336_gray\mixed_color_contamination\side_front --samples 24 --seed 73000 --anchor-sides front
```

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target qc71336_gray --defects mixed_color_contamination --count 80 --out E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\production_non_black_filler_YYYYMMDD\single\qc71336_gray\mixed_color_contamination\side_back --samples 24 --seed 73100 --anchor-sides back
```

### `qc7_5244_black foreign_material`

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target qc7_5244_black --defects foreign_material --count 70 --out E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\production_non_black_filler_YYYYMMDD\single\qc7_5244_black\foreign_material\side_front --samples 24 --seed 74000 --anchor-sides front
```

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target qc7_5244_black --defects foreign_material --count 70 --out E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\production_non_black_filler_YYYYMMDD\single\qc7_5244_black\foreign_material\side_back --samples 24 --seed 74100 --anchor-sides back
```

### `qc7_5244_black splay`

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target qc7_5244_black --defects splay --count 70 --out E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\production_non_black_filler_YYYYMMDD\single\qc7_5244_black\splay\side_front --samples 24 --seed 74200 --anchor-sides front
```

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target qc7_5244_black --defects splay --count 70 --out E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\production_non_black_filler_YYYYMMDD\single\qc7_5244_black\splay\side_back --samples 24 --seed 74300 --anchor-sides back
```

### `qc7_5244_white mixed_color_contamination`

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target qc7_5244_white --defects mixed_color_contamination --count 80 --out E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\production_non_black_filler_YYYYMMDD\single\qc7_5244_white\mixed_color_contamination\side_front --samples 24 --seed 75000 --anchor-sides front
```

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target qc7_5244_white --defects mixed_color_contamination --count 80 --out E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\production_non_black_filler_YYYYMMDD\single\qc7_5244_white\mixed_color_contamination\side_back --samples 24 --seed 75100 --anchor-sides back
```

### `ql3_1052_black foreign_material`

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target ql3_1052_black --defects foreign_material --count 50 --out E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\production_non_black_filler_YYYYMMDD\single\ql3_1052_black\foreign_material\side_front --samples 24 --seed 76000 --anchor-sides front
```

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target ql3_1052_black --defects foreign_material --count 50 --out E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\production_non_black_filler_YYYYMMDD\single\ql3_1052_black\foreign_material\side_side --samples 24 --seed 76100 --anchor-sides side
```

### `ql3_1052_black splay`

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target ql3_1052_black --defects splay --count 50 --out E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\production_non_black_filler_YYYYMMDD\single\ql3_1052_black\splay\side_front --samples 24 --seed 76200 --anchor-sides front
```

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target ql3_1052_black --defects splay --count 50 --out E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\production_non_black_filler_YYYYMMDD\single\ql3_1052_black\splay\side_side --samples 24 --seed 76300 --anchor-sides side
```

### `qc71336_black foreign_material+splay`

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target-cooccurrence --target qc71336_black --defects foreign_material,splay --count 120 --out E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\production_non_black_filler_YYYYMMDD\cooccurrence\qc71336_black\foreign_material_splay\side_front --samples 24 --seed 77000 --anchor-sides front
```

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target-cooccurrence --target qc71336_black --defects foreign_material,splay --count 120 --out E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\production_non_black_filler_YYYYMMDD\cooccurrence\qc71336_black\foreign_material_splay\side_back --samples 24 --seed 77150 --anchor-sides back
```

### `qc7_5244_black foreign_material+splay`

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target-cooccurrence --target qc7_5244_black --defects foreign_material,splay --count 120 --out E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\production_non_black_filler_YYYYMMDD\cooccurrence\qc7_5244_black\foreign_material_splay\side_front --samples 24 --seed 77300 --anchor-sides front
```

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target-cooccurrence --target qc7_5244_black --defects foreign_material,splay --count 120 --out E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\production_non_black_filler_YYYYMMDD\cooccurrence\qc7_5244_black\foreign_material_splay\side_back --samples 24 --seed 77450 --anchor-sides back
```

## Preflight

Before the large command for each target/defect/side, run `--count 2 --samples 8` to the same type of folder under:

```text
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\non_black_preflight_YYYYMMDD
```

Inspect:

- `generation_plan.json`
- `backend_run_log.json`
- `metadata\000000.json`
- `rgb\000000.png`
- `masks\000000.png`
- `labels_yolo\000000.txt`

Confirm:

- Backend script matches this document.
- `anchor_side` and `requested_anchor_side` match the requested side.
- QL3 side samples report `anchor_side=side`, `camera_side=side`, and `main_plane_axis=y`.
- Every cooccurrence sample has two YOLO rows and metadata for both defects.
- GPU is enabled.
- Domain randomization is recorded.

## GPU Requirement

Every block must use GPU rendering. Stop if GPU is unavailable.

For generic backend samples, check:

```text
metadata\*.json
render_device_info.gpu_enabled = true
render_device_info.cycles_device = GPU
```

For reference or specialized backends, check `backend_run_log.json` and backend metadata for non-CPU Cycles device such as OPTIX or CUDA.

## Domain Randomization Requirement

In each `generation_plan.json`, confirm:

```json
"camera": {"mode": "randomized"}
"lighting": {"mode": "randomized"}
"background": {"mode": "randomized"}
```

If the plan does not record randomized camera/light/background, stop and inspect the backend before continuing.

## Manual RGB/Mask Inspection

Do not rely only on automatic checks.

For every block:

1. Build a contact sheet with RGB next to mask.
2. Include first, middle, last, and at least 8 random samples per 100 images.
3. Build bbox-crop previews for at least 8 random samples per 100 images.
4. Confirm RGB contains the defect on the plastic part.
5. Confirm mask foreground aligns with the RGB defect.
6. Confirm YOLO bbox encloses the same defect.
7. For cooccurrence, confirm both defects are visible in RGB and both are represented in mask/YOLO.

Known manual review outputs from prior accepted smoke runs:

```text
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\_user_review_qc71336_black_cooccurrence_20260503
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\_user_review_qc71336_gray_mixed_color_backfix2_20260503
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\_user_review_qc75244_black_smoke_20260503
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\_user_review_qc75244_white_mixed_ql3_single_20260503
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\_user_review_ql3_side_fix_20260503
```

## Top-Up Priority

If black-dot completion plus the 1780 filler images does not reach 3000, add images in this order, always keeping exact side balance:

| Priority | Combination | Add in chunks of |
| ---: | --- | ---: |
| 1 | `qc71336_white foreign_material` | 40 front + 40 back |
| 2 | `qc7_5244_white mixed_color_contamination` | 40 front + 40 back |
| 3 | `qc71336_black foreign_material` | 40 front + 40 back |
| 4 | `qc71336_black splay` | 40 front + 40 back |
| 5 | `qc7_5244_black foreign_material` | 40 front + 40 back |
| 6 | `qc7_5244_black splay` | 40 front + 40 back |
| 7 | `qc71336_black foreign_material+splay` | 40 front + 40 back |
| 8 | `qc7_5244_black foreign_material+splay` | 40 front + 40 back |
| 9 | `ql3_1052_black foreign_material` | 25 front + 25 side |
| 10 | `ql3_1052_black splay` | 25 front + 25 side |

Do not use QL3 cooccurrence as top-up.

## Stop Conditions

Stop and report if any of these occur:

- GPU is not used.
- Domain randomization is missing or disabled.
- `anchor_side` does not match the requested side.
- QL3 side output shows the front face or reports `main_plane_axis=z`.
- Back-side generation shows only background or hides the defect.
- RGB does not visibly contain the defect.
- Mask is empty or badly misaligned.
- Cooccurrence output has fewer YOLO rows than expected.
- More than 2 percent of a block fails manual inspection.

## Final Handoff Summary To Produce After Running

After generation, write a short summary containing:

- Output root.
- Per-block requested count, succeeded count, failed count.
- Total filler count.
- Combined total after adding black-dot count.
- GPU confirmation.
- Domain randomization confirmation.
- Links to contact sheets and bbox-crop sheets.
- Any manually rejected samples and whether they were removed from the accepted set.
