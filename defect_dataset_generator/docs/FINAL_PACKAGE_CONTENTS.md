# Final Package Contents

Last updated: 2026-05-06

This document defines the recommended final packaging scope for the synthetic
defect dataset project. Keep source code, model assets, and generated datasets
as separate packages.

## Package Split

Use three separate deliverables:

| Package | Purpose | Include large generated files |
| --- | --- | --- |
| Source code package | Reproduce and inspect the generator implementation | No |
| Model asset package | Provide required `.blend` and `.stl` model files | Yes, model files only |
| Dataset package | Provide the cleaned generated dataset | Yes, dataset files only |

## Source Code Package

Include the base project files needed to run the generator:

```text
blenderproc/
cli.py
setup.py
rerun.py
README.md
LICENSE
MANIFEST.in
```

Include the project-specific generator module:

```text
defect_dataset_generator/app.py
defect_dataset_generator/core/
defect_dataset_generator/blender_scripts/
defect_dataset_generator/config/
defect_dataset_generator/tools/
defect_dataset_generator/docs/
defect_dataset_generator/requirements.txt
```

Include the current UI and reference backend scripts:

```text
examples/my_project/defect_generation_ui.py
examples/my_project/reference_blend_blackdot_multi_model.py
examples/my_project/reference_blend_qc71336_black_prebuilt_normal_debug.py
examples/my_project/reference_blend_qc71336_white_prebuilt_normal_debug.py
examples/my_project/reference_blend_qc75244_mixed_color_profile_debug.py
examples/my_project/run_p101040_blackdot_rotation_sampling_case.py
examples/my_project/DEFECT_GENERATION_UI_GUIDE.md
examples/my_project/APPROVED_DEFECT_RENDERING_GUIDE.md
examples/my_project/BLACKDOT_MULTI_MODEL_RENDERING_GUIDE.md
examples/my_project/P101040_BLACKDOT_ROTATION_SAMPLING_CASE.md
examples/my_project/requirements_eval.txt
打开缺陷生成UI.bat
```

Current source behavior to preserve in the package:

- `generate-target --defect-count-max N` supports same-type multi-defect
  single generation for the accepted reference and generic routes.
- The desktop UI exposes `Max Defects` in single-defect mode and passes the
  same CLI option directly.
- QC7-5244 white mixed-color generation must use the material-driven reference
  backend script listed above.

## Model Asset Package

Package model files separately from source code:

```text
assets/models/moxing1_test.blend
assets/models/moxing2.blend
assets/models/P101040.stl
assets/models/QC7-1336.stl
assets/models/QC7-1336-white.blend
assets/models/QC7-1336-black.blend
assets/models/QC7-5236.stl
assets/models/QL3.stl
assets/models/QL3-black.blend
```

Do not include duplicate backup files unless they are explicitly needed for a
new validation run.

## Dataset Package

Use the cleaned dataset root:

```text
defect_dataset_generator/outputs/dataset/final_3k_5k_dataset_20260504/
```

Expected contents:

```text
images/
masks/
labels/
metadata/
manifest.csv
dataset_summary.json
README_DATASET.md
```

Current dataset count:

- Total samples: `3472`
- Defect samples: `2772`
- Normal samples: `700`

Auxiliary reports and quarantined intermediate files are stored outside the
clean dataset root:

```text
defect_dataset_generator/outputs/dataset/final_3k_5k_dataset_20260504_auxiliary_archive_20260505/
```

Do not include the auxiliary archive in the primary dataset package unless
review history is requested.

## Exclude From Final Source Package

Exclude generated outputs, local caches, local environment folders, and heavy
artifacts:

```text
.git/
.idea/
blender_bin/
blenderproc.egg-info/
__pycache__/
defect_dataset_generator/outputs/
examples/my_project/*_CASE*/
examples/my_project/*_RUN*/
examples/my_project/*_BATCH*/
examples/my_project/*_eval*/
examples/my_project/*real*_labels*/
examples/my_project/approved_defect_showcase_cases_20260503/
examples/my_project/blackdot_showcase_cases/
*.pt
```

Also exclude local real-image folders, training-result folders, contact sheets,
temporary audits, and one-off smoke output directories from the source package.

## Authorship And Dependency Note

The source package should distinguish between the underlying BlenderProc
framework and the project-specific generator work. The project-specific work is
the defect dataset generator module, product/defect configuration, rendering
backend adaptations, UI wrapper, batch generation workflow, annotation export,
normal-sample correction, and final dataset assembly workflow.
