# Synthetic Defect Dataset Generator Usage Guide

Last updated: 2026-05-04

This guide is the current practical usage document for the BlenderProc-based
plastic-part defect dataset generator. It is written for the next operator or
Codex session that needs to verify the project and continue generation work.

## Project Root

```text
E:\BlenderProject\BlenderProc
```

Use the project Python environment:

```text
D:\Anaconda\envs\defect_eval\python.exe
```

Run commands from the project root:

```powershell
cd E:\BlenderProject\BlenderProc
```

## Main Interfaces

### Desktop UI

Double-click:

```text
E:\BlenderProject\BlenderProc\打开缺陷生成UI.bat
```

Direct Python entry:

```powershell
D:\Anaconda\envs\defect_eval\python.exe examples\my_project\defect_generation_ui.py
```

The UI is a safe wrapper around:

```text
defect_dataset_generator\app.py
```

Current UI behavior:

- Chinese/English language switch.
- `Single` mode uses a single-choice defect selector.
- `Cooccurrence` mode only offers manually accepted combinations.
- `Normal` mode creates no-defect samples.
- Preview supports `rgb` and `masks` only. Overlay is not exposed in the UI.
- `Dry run` is enabled by default.
- `Dry run` writes plans and commands only. It does not run Blender and does not
  create real RGB/mask images.
- UI output folders are grouped as:

```text
defect_dataset_generator\outputs\dataset\ui_runs_YYYYMMDD\dry_run\HHMMSS_mmm_target_mode_side
defect_dataset_generator\outputs\dataset\ui_runs_YYYYMMDD\render\HHMMSS_mmm_target_mode_side
```

### CLI

List registered targets:

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py list-targets
```

Single defect:

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target <target> --defects <defect> --count <count> --out <output_dir> --samples <samples> --seed <seed> --anchor-sides <front|back|side>
```

Same-scene approved cooccurrence:

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target-cooccurrence --target <target> --defects foreign_material,splay --count <count> --out <output_dir> --samples <samples> --seed <seed> --anchor-sides <front|back>
```

Normal samples:

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target-normal --target <target> --count <count> --out <output_dir> --samples <samples> --seed <seed> --anchor-sides <front|back|side>
```

Add `--dry-run` to any command when only the generation plan should be checked.

## Active Configuration Files

Target registry:

```text
defect_dataset_generator\config\model_color_profiles.json
defect_dataset_generator\config\model_color_defect_targets.json
```

Important presets and material files:

```text
defect_dataset_generator\config\black_dot_appearance_presets.json
defect_dataset_generator\config\qc7_5244_black_visual_material_candidate_v3.json
```

Important renderer/app files:

```text
defect_dataset_generator\app.py
defect_dataset_generator\core\renderer.py
defect_dataset_generator\blender_scripts\render_generic_main_plane_defects.py
defect_dataset_generator\blender_scripts\render_persistent_generic_batch.py
examples\my_project\reference_blend_blackdot_multi_model.py
examples\my_project\reference_blend_qc71336_black_prebuilt_normal_debug.py
examples\my_project\reference_blend_qc71336_white_prebuilt_normal_debug.py
examples\my_project\reference_blend_qc75244_mixed_color_profile_debug.py
```

Model files are not pushed to GitHub. They are supplied separately by network
disk. Before rendering, confirm that the needed paths exist under:

```text
assets\models\
```

## Current Accepted Generation Scope

Only use the combinations below for the current 3k-5k dataset plan.

### Single Black-Dot Defects

The user has accepted the active black-dot single-defect targets for the current
plan. Still spot-check every production block.

| Target | Defect | Required sides | Backend/script |
| --- | --- | --- | --- |
| `p101040_blue` | `black_dot` | front/back where supported by command/profile | `examples/my_project/reference_blend_blackdot_multi_model.py` |
| `qc71336_white` | `black_dot` | front/back | `examples/my_project/reference_blend_blackdot_multi_model.py` |
| `qc71336_gray` | `black_dot` | front/back | `examples/my_project/reference_blend_blackdot_multi_model.py` |
| `qc7_5244_white` | `black_dot` | front/back | `examples/my_project/reference_blend_blackdot_multi_model.py` |
| `qc7_5244_black` | `black_dot` | front/back | `defect_dataset_generator/blender_scripts/render_generic_main_plane_defects.py` |

### Approved Non-Black Single Defects

| Target | Defect | Required sides | Backend/script |
| --- | --- | --- | --- |
| `qc71336_black` | `foreign_material` | front/back | `examples/my_project/reference_blend_qc71336_black_prebuilt_normal_debug.py` |
| `qc71336_black` | `splay` | front/back | `examples/my_project/reference_blend_qc71336_black_prebuilt_normal_debug.py` |
| `qc71336_white` | `foreign_material` | front/back | `examples/my_project/reference_blend_qc71336_white_prebuilt_normal_debug.py` |
| `qc71336_gray` | `mixed_color_contamination` | front/back | `defect_dataset_generator/blender_scripts/render_generic_main_plane_defects.py` |
| `qc7_5244_black` | `foreign_material` | front/back | `defect_dataset_generator/blender_scripts/render_generic_main_plane_defects.py` |
| `qc7_5244_black` | `splay` | front/back | `defect_dataset_generator/blender_scripts/render_generic_main_plane_defects.py` |
| `qc7_5244_white` | `mixed_color_contamination` | front/back | `examples/my_project/reference_blend_qc75244_mixed_color_profile_debug.py` |
| `ql3_1052_black` | `foreign_material` | front/side | `defect_dataset_generator/blender_scripts/render_generic_main_plane_defects.py` |
| `ql3_1052_black` | `splay` | front/side | `defect_dataset_generator/blender_scripts/render_generic_main_plane_defects.py` |

### Approved Same-Scene Cooccurrence

Only these same-scene combinations are allowed in the UI and current plan:

| Target | Defects | Required sides | Backend/script |
| --- | --- | --- | --- |
| `qc71336_black` | `foreign_material,splay` | front/back | `examples/my_project/reference_blend_qc71336_black_prebuilt_normal_debug.py` |
| `qc7_5244_black` | `foreign_material,splay` | front/back | `defect_dataset_generator/blender_scripts/render_generic_main_plane_defects.py` |

Do not run:

```text
ql3_1052_black foreign_material+splay cooccurrence
```

Do not include black-dot-containing cooccurrence unless the user explicitly
reopens and accepts those combinations.

## Dataset Construction Policy

- Final target is 3k-5k synthetic samples.
- Black-dot single-defect generation is the primary current dataset portion.
- Non-black accepted defects fill the remaining images to reach at least 3k.
- Use GPU rendering.
- Keep domain randomization enabled for production unless debugging.
- Split front/back as 1:1 for non-QL3 targets.
- Split front/side as 1:1 for QL3.
- Run side-specific commands instead of mixing sides in one command when exact
  balance matters.
- Inspect RGB and mask after every block.

Recommended production docs:

```text
defect_dataset_generator\docs\BLACK_DOT_SINGLE_DEFECT_3K_5K_HANDOFF.md
defect_dataset_generator\docs\APPROVED_NON_BLACK_DEFECT_3K_FILLER_HANDOFF.md
```

## Required Output Check

After each render command, inspect:

```text
generation_plan.json
backend_run_log.json
dataset_summary.json
rgb\
masks\
labels_yolo\
metadata\
```

Acceptance checks:

- RGB image exists.
- Mask image exists.
- Mask is not empty.
- Visible RGB defect exists.
- RGB defect and mask location match.
- Side in metadata matches requested side.
- Defect is on the intended main plane.
- YOLO label exists when a defect should be labeled.
- `backend_run_log.json` does not report failed samples.
- GPU/OPTIX metadata should be present where the backend records renderer info.

If a dry-run folder is loaded, `rgb` and `masks` may be empty. That is expected.

## P101040 Rotation Sampling Case

Use this only as a technical demo case. It is isolated from production
generation.

Guide:

```text
examples\my_project\P101040_BLACKDOT_ROTATION_SAMPLING_CASE.md
```

Script:

```text
examples\my_project\run_p101040_blackdot_rotation_sampling_case.py
```

Verified output:

```text
examples\my_project\P101040_BLACKDOT_ROTATION_CASE_20260504_V3
```

Verified facts:

- 18 frames, angles 0 to 340 degrees.
- Step is 20 degrees.
- RGB/mask exist for every angle.
- Empty mask count is 0.
- Mask aligns with the black dot.

## Known Cautions

- Existing docs and JSON may contain old status text. Prefer this guide and
  `CURRENT_PROJECT_HANDOFF.md` after 2026-05-04 updates.
- Some older console output displays Chinese filenames as mojibake. The files
  themselves may still be valid UTF-8 or Windows filenames.
- Model files are intentionally not pushed to GitHub.
- Do not delete user-generated output folders.
- Do not replace specialized reference scripts with generic scripts just for
  speed.
- Material fitting/image-reverse material search is not the main production
  method. It is a scoring and calibration aid. Current production primarily
  uses manual material/environment/defect tuning plus scripted generation.
