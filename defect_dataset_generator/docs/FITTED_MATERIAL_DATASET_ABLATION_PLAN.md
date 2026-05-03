# Fitted Material Dataset Ablation Plan

## Purpose

Create two small black-spot synthetic datasets that are controlled for all generation variables except material override. The goal is to prepare a training-oriented dataset ablation, not to train a detector yet.

This checks whether fitted visual material calibration produces a dataset that is plausibly more useful for later object-detection experiments.

## Controlled Variables

Both datasets use:

- Backend script: `examples/my_project/reference_blend_blackdot_multi_model.py`
- Model profile: `QC71336_white`
- Reference blend: `assets\models\moxing2.blend`
- Defect config: `defect_dataset_generator\config\black_spot_smoke.json`
- Count: `20`
- Samples: `16`
- Seed range: `500-519`
- Anchor side: `front`
- Same defect placement logic
- Same camera/light randomization logic
- Same label and mask adapter

## Changed Variable

Only material handling changes:

| Dataset | Material behavior |
| --- | --- |
| A: `default_material` | Backend default material, no `--apply-material` |
| B: `fitted_material` | Uses fitted visual calibration through `--apply-material` |

Fitted material:

```text
defect_dataset_generator\outputs\fitting\fit_plastic_mask_roi_20_v2\best_material.json
```

## Commands

Run from:

```powershell
cd E:\BlenderProject\BlenderProc
```

Dataset A:

```powershell
python defect_dataset_generator\app.py generate --blend assets\models\moxing2.blend --material defect_dataset_generator\outputs\fitting\fit_plastic_mask_roi_20_v2\best_material.json --defect-config defect_dataset_generator\config\black_spot_smoke.json --count 20 --out defect_dataset_generator\outputs\dataset\black_spot_ablation_train\default_material --backend-model QC71336_white --samples 16 --seed 500 --anchor-side front
```

Dataset B:

```powershell
python defect_dataset_generator\app.py generate --blend assets\models\moxing2.blend --material defect_dataset_generator\outputs\fitting\fit_plastic_mask_roi_20_v2\best_material.json --defect-config defect_dataset_generator\config\black_spot_smoke.json --count 20 --out defect_dataset_generator\outputs\dataset\black_spot_ablation_train\fitted_material --backend-model QC71336_white --samples 16 --seed 500 --anchor-side front --apply-material
```

## Expected Outputs

```text
outputs/dataset/black_spot_ablation_train/
  default_material/
    rgb/
    masks/
    labels_yolo/
    metadata/
    dataset_summary.json
    backend_run_log.json
    dataset_quality_report.json
    yolo_dataset/
  fitted_material/
    rgb/
    masks/
    labels_yolo/
    metadata/
    dataset_summary.json
    backend_run_log.json
    dataset_quality_report.json
    yolo_dataset/
  default_material_contact_sheet.jpg
  fitted_material_contact_sheet.jpg
  side_by_side_contact_sheet.jpg
```

## Quality Checks

For each dataset:

- total requested, succeeded, and failed
- seed list
- failed sample reasons
- RGB/mask/label/metadata existence
- YOLO label non-empty
- bbox values within `0-1`
- average bbox size
- bbox size min/max
- defect visibility proxy from mask area ratio and bbox area

## YOLO Split

If labels are valid, create:

```text
yolo_dataset/
  images/train/
  images/val/
  labels/train/
  labels/val/
  data.yaml
```

Split policy:

- deterministic sorted split
- 80% train
- 20% val
- class `0`: `black_spot`

## Later Training Connection

This step originally did not train YOLO. A follow-up GPU training smoke comparison has now been run and documented in:

```text
docs/FITTED_MATERIAL_GPU_TRAINING_ABLATION_RESULTS.md
```

The generated `yolo_dataset` folders are intended for controlled training comparisons:

- train on default-material synthetic dataset
- train on fitted-material synthetic dataset
- compare on the same manually labeled real validation set

The completed GPU smoke run compared the two arms on their tiny synthetic validation splits. A real manually labeled QC71336 validation set is still required before discussing real detector usefulness.
