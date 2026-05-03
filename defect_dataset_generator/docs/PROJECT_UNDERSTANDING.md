# Project Understanding Report

## Current Project Shape

The repository is a BlenderProc source checkout with project-specific work under:

```text
examples/my_project/
assets/models/
```

The project memory files at repository root are important and should be read before changing generator behavior:

- `README_PROJECT_MEMORY.md`
- `PROJECT_STATUS.md`
- `CURRENT_BASELINES.md`
- `DEFECT_SCHEMA.md`
- `MODEL_AND_APPEARANCE_SCHEMA.md`
- `NEXT_TASKS.md`
- `DECISIONS.md`

## Important Existing Files

| File or folder | Current role |
| --- | --- |
| `examples/my_project/reference_blend_blackdot_multi_model.py` | Current stable black-dot handoff script. Supports several model/appearance cases, front/back placement, camera/light jitter, RGB/mask/overlay/YOLO/metadata, and optional debug `.blend`. |
| `examples/my_project/generate_black_spot_multi_model.py` | Large older/main experimental generator. Contains multi-model logic, defect schema/taxonomy bridge, COCO/YOLO-style outputs, and many black-dot/material experiment paths. Needs refactor before becoming the general framework backend. |
| `examples/my_project/reference_blend_blue_blackdot_debug.py` | Useful reference-scene prototype for embedded black-dot appearance and material/debug work. Experimental. |
| `examples/my_project/reference_blend_*_debug.py` | Reference-scene material/camera/debug renderers for specific objects and appearances. Useful for extracting calibration knowledge, not clean CLI modules yet. |
| `examples/my_project/generate_black_spot_v*.py`, `generate_voronoi_*`, `generate_single_*` | Historical black-dot generator variants. Useful as references, but superseded by the current handoff script for production black-dot work. |
| `examples/my_project/generate_injection_defects_dataset.py` | Earlier broad defect-generation attempt. Should be inspected before extracting any non-black-dot logic. |
| `examples/my_project/evaluate_*.py`, `audit_*.py`, `summarize_*.py` | Evaluation, ROI audit, and experiment-summary utilities. Not generation backends. |
| `examples/my_project/prepare_*.py`, `apply_*.py`, `refine_*.py` | Dataset and real-label preparation utilities. Useful for export/eval compatibility. |
| `examples/my_project/defect_gui_prototype.py` | Old GUI prototype. Useful as UI reference only; CLI is the current priority. |
| `assets/models/` | Local model assets. Includes `.blend` and `.stl` files. These should stay out of Git and be referenced by config or CLI arguments. |

## Usable Now

- Mature black-dot rendering: `reference_blend_blackdot_multi_model.py`.
- Stable memory/schema documentation for black-dot, material families, and target defect classes.
- Existing label/evaluation workflows for P101040 and QC71336 experiments.
- Real model assets are present locally under `assets/models`.

## Experimental or Debug-Only

- Most `reference_blend_*_debug.py` scripts are appearance/debug experiments.
- Many `output_*`, `FINAL_*`, `REFERENCE_*`, `SMOKE_*`, and `EVALUATION_*` folders are historical render/evaluation outputs.
- `mixed_color_contamination`, `foreign_material`, `splay`, and `sink_mark` have partial or smoke-test progress but are not yet production-clean.
- GUI work exists only as a prototype and should not be treated as the main user interface yet.

## Architecture Implication

The new framework should not rewrite the existing scripts directly. It should provide a clean CLI and module layout, then gradually wrap or extract stable logic from existing BlenderProc scripts into `blender_scripts/` and normal Python orchestration into `core/`.
