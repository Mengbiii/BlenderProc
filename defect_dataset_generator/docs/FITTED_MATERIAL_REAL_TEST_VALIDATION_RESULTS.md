# Fitted Material Real-Test Validation Results

## Purpose

Validate the two synthetic-only YOLOv8n models on the same fixed real manually labeled QC71336 test split.

This directly follows the previous GPU training ablation:

- default backend material model
- fitted visual material model

## Real Test Dataset

YAML:

```text
E:\BlenderProject\BlenderProc\examples\my_project\QC71336_task_eval_prep_frontonly_v1\yolo_A_real_only_mixed.yaml
```

Split:

```text
test
```

Dataset properties from `prep_summary.json`:

- real-only fixed test split
- 16 test images
- 8 labeled defect instances
- 8 background images
- 8 white-part test images
- 8 gray-part test images

## Commands

Default-material model:

```powershell
$env:YOLO_CONFIG_DIR='E:\BlenderProject\Ultralytics'
& D:\Anaconda\envs\defect_eval\Scripts\yolo.exe detect val model=E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\training\black_spot_material_ablation_gpu\default_material_yolov8n_gpu_seed0\weights\best.pt data=E:\BlenderProject\BlenderProc\examples\my_project\QC71336_task_eval_prep_frontonly_v1\yolo_A_real_only_mixed.yaml split=test imgsz=640 batch=4 project=E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\training\black_spot_material_ablation_gpu\real_test_validation name=default_material_best_real_test device=0 workers=0
```

Fitted-material model:

```powershell
$env:YOLO_CONFIG_DIR='E:\BlenderProject\Ultralytics'
& D:\Anaconda\envs\defect_eval\Scripts\yolo.exe detect val model=E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\training\black_spot_material_ablation_gpu\fitted_material_yolov8n_gpu_seed0\weights\best.pt data=E:\BlenderProject\BlenderProc\examples\my_project\QC71336_task_eval_prep_frontonly_v1\yolo_A_real_only_mixed.yaml split=test imgsz=640 batch=4 project=E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\training\black_spot_material_ablation_gpu\real_test_validation name=fitted_material_best_real_test device=0 workers=0
```

Both commands ran on:

```text
CUDA:0 NVIDIA GeForce RTX 3070 Laptop GPU
```

## Results

| Model | Precision | Recall | mAP50 | mAP50-95 |
| --- | ---: | ---: | ---: | ---: |
| Default material best.pt | 0.000 | 0.000 | 0.000 | 0.000 |
| Fitted material best.pt | 0.000 | 0.000 | 0.000 | 0.000 |

Output folders:

```text
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\training\black_spot_material_ablation_gpu\real_test_validation\default_material_best_real_test
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\training\black_spot_material_ablation_gpu\real_test_validation\fitted_material_best_real_test
```

Summary JSON:

```text
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\training\black_spot_material_ablation_gpu\real_test_validation_summary.json
```

## Interpretation

Both synthetic-only models failed on the fixed real QC71336 test split.

The fitted visual material did not improve real-domain test performance in this small setup. This should not be interpreted as proof that visual material calibration is useless. The stronger reading is:

- count `20` synthetic-only training is too small
- synthetic defects are still domain-gapped from real defects
- real images include texture, lighting, part pose, and defect appearance differences not covered by the current synthetic batch
- material calibration alone is not enough without defect realism and domain coverage

## Next Actions

Recommended next experiments:

1. Train real-only baseline on the existing QC71336 real train split.
2. Train real + default-material synthetic.
3. Train real + fitted-material synthetic.
4. Evaluate all three on the same fixed real test split.
5. Increase synthetic diversity only after real + synthetic baseline is established.
