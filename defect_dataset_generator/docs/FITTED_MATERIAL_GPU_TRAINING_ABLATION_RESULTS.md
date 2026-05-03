# Fitted Material GPU Training Ablation Results

## Purpose

Compare two small YOLOv8 black-spot training arms:

- default backend material
- fitted visual material override

This is a first training-oriented smoke comparison. It is not yet a real-domain conclusion.

## Existing Script References

The training command style follows the existing pilot notes in:

- `examples/my_project/PILOT_EXPERIMENT_COMMANDS_MANUAL.md`
- `examples/my_project/QC71336_PILOT_EXPERIMENT_COMMANDS_FRONTONLY.md`

The main changes are:

- force `device=0`
- use CUDA PyTorch
- use the two ablation `data.yaml` files under `defect_dataset_generator/outputs/dataset/black_spot_ablation_train`

## GPU Setup

Initial check showed `defect_eval` had CPU-only PyTorch:

```text
torch 2.11.0+cpu
cuda_available False
```

CUDA PyTorch was installed into:

```text
D:\Anaconda\envs\defect_eval
```

Verified GPU environment:

```text
Ultralytics 8.4.41
Python 3.10.20
torch 2.11.0+cu128
CUDA:0 NVIDIA GeForce RTX 3070 Laptop GPU, 8192MiB
```

## Datasets

Default material:

```text
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\black_spot_ablation_train\default_material\yolo_dataset\data.yaml
```

Fitted material:

```text
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\black_spot_ablation_train\fitted_material\yolo_dataset\data.yaml
```

Each dataset:

- 16 train images
- 4 validation images
- one class: `black_spot`
- same seeds and same bbox sequence

## Commands

Default material:

```powershell
$env:YOLO_CONFIG_DIR='E:\BlenderProject\Ultralytics'
& D:\Anaconda\envs\defect_eval\Scripts\yolo.exe detect train model=E:\BlenderProject\yolov8n.pt data=E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\black_spot_ablation_train\default_material\yolo_dataset\data.yaml epochs=100 imgsz=640 batch=4 patience=20 project=E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\training\black_spot_material_ablation_gpu name=default_material_yolov8n_gpu_seed0 seed=0 device=0 workers=0
```

Fitted material:

```powershell
$env:YOLO_CONFIG_DIR='E:\BlenderProject\Ultralytics'
& D:\Anaconda\envs\defect_eval\Scripts\yolo.exe detect train model=E:\BlenderProject\yolov8n.pt data=E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\dataset\black_spot_ablation_train\fitted_material\yolo_dataset\data.yaml epochs=100 imgsz=640 batch=4 patience=20 project=E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\training\black_spot_material_ablation_gpu name=fitted_material_yolov8n_gpu_seed0 seed=0 device=0 workers=0
```

## Outputs

```text
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\training\black_spot_material_ablation_gpu\
  default_material_yolov8n_gpu_seed0\
  fitted_material_yolov8n_gpu_seed0\
  validation\
    default_material_best_val\
    fitted_material_best_val\
  training_ablation_summary.json
```

## Explicit Best-Weight Validation

Both models were validated with their `best.pt` weights on their own held-out synthetic validation split.

| Arm | Precision | Recall | mAP50 | mAP50-95 |
| --- | ---: | ---: | ---: | ---: |
| Default material | 0.927 | 0.750 | 0.745 | 0.156 |
| Fitted material | 1.000 | 0.661 | 0.745 | 0.107 |

## Initial Interpretation

- Both runs used GPU successfully.
- mAP50 is tied at `0.745`.
- Default material has higher recall and higher mAP50-95 on this synthetic validation split.
- Fitted material has higher precision but lower recall and lower localization score.
- This does not prove default material is better for real inspection images.

## Limitations

- The dataset is extremely small: 16 train and 4 val images per arm.
- Validation is synthetic, not real-domain.
- Only one training seed was used.
- The validation split is generated from the same synthetic process as training, so it cannot measure real-domain usefulness.
- A failed non-escalated first attempt created an unused partial output directory named `default_material_yolov8n_seed0`.

## Next Step

The next meaningful experiment is to evaluate both trained models on the same manually labeled real QC71336 test set. Only then can we discuss whether fitted visual material improves detector usefulness.

## Real-Test Follow-Up

This follow-up has been completed and documented in:

```text
docs/FITTED_MATERIAL_REAL_TEST_VALIDATION_RESULTS.md
```

Both synthetic-only models scored `0` on the fixed real QC71336 test split:

| Model | Precision | Recall | mAP50 | mAP50-95 |
| --- | ---: | ---: | ---: | ---: |
| Default material best.pt | 0.000 | 0.000 | 0.000 | 0.000 |
| Fitted material best.pt | 0.000 | 0.000 | 0.000 | 0.000 |

The result indicates a strong remaining domain gap. The next useful comparison should be real-only vs real+synthetic, not synthetic-only vs synthetic-only.
