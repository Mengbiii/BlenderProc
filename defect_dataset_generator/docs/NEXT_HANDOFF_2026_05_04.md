# Next Handoff

Last updated: 2026-05-04

This is the latest short handoff for the next maintainer. Use it together with:

```text
defect_dataset_generator\docs\SYSTEM_USAGE_GUIDE.md
defect_dataset_generator\docs\BLACK_DOT_SINGLE_DEFECT_3K_5K_HANDOFF.md
defect_dataset_generator\docs\APPROVED_NON_BLACK_DEFECT_3K_FILLER_HANDOFF.md
examples\my_project\DEFECT_GENERATION_UI_GUIDE.md
examples\my_project\P101040_BLACKDOT_ROTATION_SAMPLING_CASE.md
```

## Current Goal

The project is a BlenderProc-based synthetic defect dataset generator for
plastic workpieces. The next work is to verify the updated docs, continue safe
3k-5k dataset construction, and keep checking RGB/mask quality manually.

## Current Important User Decisions

- Final dataset target is 3k-5k images.
- Model files should not be pushed to GitHub. The user will provide models by
  network disk.
- Black-dot-containing cooccurrence is not in the current generation plan.
- `ql3_1052_black` cooccurrence is cancelled.
- Single-defect mode in the UI must remain single-choice, not multi-select.
- UI preview should show only `rgb` and `masks`; overlay is not exposed.
- Material fitting/reverse material search is not the production material path.
  It remains a scoring/calibration aid.

## Current UI State

Files:

```text
examples\my_project\defect_generation_ui.py
E:\BlenderProject\BlenderProc\打开缺陷生成UI.bat
examples\my_project\DEFECT_GENERATION_UI_GUIDE.md
```

Verified behavior:

- UI opens through the `.bat` launcher.
- `Dry run` is enabled by default.
- Default output is date/type/time grouped:

```text
defect_dataset_generator\outputs\dataset\ui_runs_YYYYMMDD\dry_run\HHMMSS_mmm_target_mode_side
defect_dataset_generator\outputs\dataset\ui_runs_YYYYMMDD\render\HHMMSS_mmm_target_mode_side
```

- Single mode uses radio buttons for one defect.
- Cooccurrence mode only lists:

```text
qc71336_black: foreign_material+splay
qc7_5244_black: foreign_material+splay
```

- Preview mode values are only `rgb` and `masks`.

Suggested quick UI smoke:

```powershell
D:\Anaconda\envs\defect_eval\python.exe -m py_compile examples\my_project\defect_generation_ui.py
```

Then instantiate the UI without rendering and confirm command generation if
needed.

## Current Accepted Generation Scope

### Black-Dot Single

Use single-defect black-dot only:

```text
p101040_blue black_dot
qc71336_white black_dot
qc71336_gray black_dot
qc7_5244_white black_dot
qc7_5244_black black_dot
```

The user has accepted the previously disputed items for the current plan. Still
spot-check production blocks.

### Non-Black Single

```text
qc71336_black foreign_material front/back
qc71336_black splay front/back
qc71336_white foreign_material front/back
qc71336_gray mixed_color_contamination front/back
qc7_5244_black foreign_material front/back
qc7_5244_black splay front/back
qc7_5244_white mixed_color_contamination front/back
ql3_1052_black foreign_material front/side
ql3_1052_black splay front/side
```

### Non-Black Cooccurrence

```text
qc71336_black foreign_material,splay front/back
qc7_5244_black foreign_material,splay front/back
```

No other cooccurrence should be run without new user approval.

## Current Important Backend Routes

| Scope | Backend/script |
| --- | --- |
| Reference black-dot | `examples/my_project/reference_blend_blackdot_multi_model.py` |
| QC71336 black foreign/splay/cooccurrence | `examples/my_project/reference_blend_qc71336_black_prebuilt_normal_debug.py` |
| QC71336 white foreign material | `examples/my_project/reference_blend_qc71336_white_prebuilt_normal_debug.py` |
| QC75244/QC7-5244 white mixed color | `examples/my_project/reference_blend_qc75244_mixed_color_profile_debug.py` |
| Generic black/foreign/splay/mixed where routed | `defect_dataset_generator/blender_scripts/render_generic_main_plane_defects.py` |
| Persistent generic batch | `defect_dataset_generator/blender_scripts/render_persistent_generic_batch.py` |

Always verify `generation_plan.json` and `backend_run_log.json` after a dry run
or tiny render before running a large block.

## Production Commands

Use the two production handoff docs for exact command blocks:

```text
defect_dataset_generator\docs\BLACK_DOT_SINGLE_DEFECT_3K_5K_HANDOFF.md
defect_dataset_generator\docs\APPROVED_NON_BLACK_DEFECT_3K_FILLER_HANDOFF.md
```

Recommended workflow for each block:

1. Run `--dry-run`.
2. Inspect `generation_plan.json`.
3. Run a tiny smoke, usually `--count 1` or `--count 2 --samples 8`.
4. Open RGB and mask manually.
5. Confirm the defect is visible and mask-aligned.
6. Run production count with GPU rendering.
7. Spot-check outputs again.

## P101040 Rotation Sampling Case

Files:

```text
examples\my_project\run_p101040_blackdot_rotation_sampling_case.py
examples\my_project\P101040_BLACKDOT_ROTATION_SAMPLING_CASE.md
```

Verified output:

```text
examples\my_project\P101040_BLACKDOT_ROTATION_CASE_20260504_V3
```

Use it as technical demo evidence only. It is isolated from production
generation.

## Immediate Next Actions

1. Verify the updated docs against the current code.
2. Confirm the UI still opens from `打开缺陷生成UI.bat`.
3. Run one dry-run and one tiny real render through the UI.
4. Confirm `rgb` and `masks` preview load.
5. Continue dataset generation from accepted combinations only.

## Do Not Do

- Do not push model files.
- Do not delete user output folders.
- Do not re-enable arbitrary cooccurrence in the UI.
- Do not use `overlay` as a required UI preview output.
- Do not treat dry-run folders as failed render folders.
- Do not rely only on evaluation scripts; manually open RGB and mask samples.
