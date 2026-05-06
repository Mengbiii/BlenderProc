# Synthetic Defect Dataset Generator Usage Guide

Last updated: 2026-05-06

This guide is the current practical usage document for the BlenderProc-based
plastic-part defect dataset generator. It is written for the next operator or
maintenance session that needs to verify the project and continue generation
work.

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

## Final Packaging

The recommended final package split is documented in:

```text
defect_dataset_generator\docs\FINAL_PACKAGE_CONTENTS.md
```

Use separate packages for:

- source code;
- model assets;
- generated dataset.

Do not mix generated outputs or model assets into the source code package.
The cleaned dataset root is:

```text
defect_dataset_generator\outputs\dataset\final_3k_5k_dataset_20260504
```

It should contain only:

```text
images\
masks\
labels\
metadata\
manifest.csv
dataset_summary.json
README_DATASET.md
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
- The defect parameter panel adapts to the selected target and defect.
- Editable defect parameters are loaded from the current preset/profile files.
- UI parameter edits are limited to whitelisted numeric fields such as size
  range, size scale, width/height multiplier, roughness, or supported reference
  backend radius/depth scales.
- The UI does not allow changing defect generation scripts, backend type,
  placement logic, or arbitrary command text.
- The backend validates the UI parameter JSON again before rendering.
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

For supported single-defect generation, `--defect-count-max` can be used to
sample multiple same-type defects in one image. For example, the command below
samples a random black-dot count from `1` to `3` for every rendered image:

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target p101040_blue --defects black_dot --count 10 --out <output_dir> --samples 24 --seed <seed> --anchor-sides front --defect-count-max 3
```

The merged mask contains all visible instances. The YOLO label file contains
one row per visible instance, and metadata records the sampled `defect_count`
plus per-instance bbox and placement information.

Supported same-type multi-defect routes currently include reference black-dot
targets, generic main-plane single-defect targets, QC71336 prebuilt
foreign-material/splay routes, and QC7-5244 white mixed-color reference
generation.

In the desktop UI, single-defect mode exposes `Max Defects` in the main numeric
control row. Set it to `3` to generate `1..3` defects per image. This main
control passes `--defect-count-max` directly. The per-defect parameter panel may
also expose `max count`; those custom parameters only apply when `Use custom
parameters` is enabled and are intended for fine-grained overrides.

For QC7-5244 white mixed-color, the valid multi-defect backend is the
material-driven reference script, not the generic main-plane fallback:

```text
examples\my_project\reference_blend_qc75244_mixed_color_profile_debug.py
```

Optional UI-style parameter override:

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target qc7_5244_black --defects foreign_material --count 1 --out <output_dir> --samples 16 --seed 90001 --anchor-sides front --defect-params-json <output_dir>\ui_defect_params.json
```

Same-scene approved cooccurrence:

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target-cooccurrence --target <target> --defects foreign_material,splay --count <count> --out <output_dir> --samples <samples> --seed <seed> --anchor-sides <front|back>
```

Normal samples:

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target-normal --target <target> --count <count> --out <output_dir> --samples <samples> --seed <seed> --anchor-sides <front|back|side>
```

Current normal rendering behavior:

- P101040 normal samples route through the reference black-dot scene with
  normal mode enabled, so the camera, lighting, and tabletop background match
  the accepted P101040 black-dot style while defect creation is skipped.
- Other normal samples route through the generic main-plane renderer with the
  same tabletop-style background policy.
- For back-side normal samples, the product object is flipped by 180 degrees and
  the camera remains in the front tabletop style. Do not interpret normal back
  as a camera orbit behind the product.
- Domain randomization remains active for normal samples: lighting, camera
  jitter, and neutral background variation are sampled per image.
- Normal labels are empty and normal masks are all black by design.
- Generated normal outputs belong under `defect_dataset_generator\outputs\` and
  should not be committed to Git.

Add `--dry-run` to any command when only the generation plan should be checked.

Parameter override JSON format:

```json
{
  "schema_version": "ui_defect_params_v1",
  "target": "qc7_5244_black",
  "mode": "single",
  "defects": {
    "foreign_material": {
      "size_factor_min": 0.0014,
      "size_factor_max": 0.0028,
      "size_scale": 1.0,
      "width_multiplier": 1.3,
      "height_multiplier": 1.1,
      "roughness": 0.72
    }
  }
}
```

The accepted keys depend on the selected backend. Invalid keys or values are
rejected before BlenderProc starts.

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
defect_dataset_generator\core\defect_parameter_overrides.py
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
