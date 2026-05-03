# Black Spot Backend Validation

## Purpose

This document records how to validate the first real production backend connected to the new framework:

```text
examples/my_project/reference_blend_blackdot_multi_model.py
```

The backend is used through the wrapper in `core/renderer.py`. The old backend script is not refactored; its outputs are adapted into the new dataset layout.

## Count-1 Command

Run from:

```powershell
cd E:\BlenderProject\BlenderProc\defect_dataset_generator
```

Command:

```powershell
python app.py generate --blend assets\models\moxing2.blend --material defect_dataset_generator\outputs\fitting\smoke_fit\best_material.json --defect-config defect_dataset_generator\config\black_spot_smoke.json --count 1 --out defect_dataset_generator\outputs\dataset\black_spot_count1_validation --backend-model P101040_blue --samples 16 --seed 41 --anchor-side front
```

Validated output:

```text
defect_dataset_generator/outputs/dataset/black_spot_count1_validation/
  rgb/000000.png
  masks/000000.png
  labels_yolo/000000.txt
  metadata/000000.json
  backend_metadata.json
  backend_run_log.json
  generation_plan.json
  dataset_summary.json
```

## Count-5 Command

```powershell
python app.py generate --blend assets\models\moxing2.blend --material defect_dataset_generator\outputs\fitting\smoke_fit\best_material.json --defect-config defect_dataset_generator\config\black_spot_smoke.json --count 5 --out defect_dataset_generator\outputs\dataset\black_spot_batch5_validation --backend-model P101040_blue --samples 16 --seed 41 --anchor-side front
```

The wrapper runs five one-sample backend calls with seeds:

```text
41, 42, 43, 44, 45
```

Each sample gets one retry if the backend call or adapter/quality check fails.

## Dry Run Command

```powershell
python app.py generate --blend assets\models\moxing2.blend --material defect_dataset_generator\outputs\fitting\smoke_fit\best_material.json --defect-config defect_dataset_generator\config\black_spot_smoke.json --count 5 --out defect_dataset_generator\outputs\dataset\black_spot_batch5_dry_run --backend-model P101040_blue --samples 16 --seed 41 --anchor-side front --dry-run
```

Dry run writes planned commands and output paths, but does not call BlenderProc.

## Expected Count-5 Output Tree

```text
black_spot_batch5_validation/
  rgb/
    000000.png
    000001.png
    000002.png
    000003.png
    000004.png
  masks/
    000000.png
    000001.png
    000002.png
    000003.png
    000004.png
  labels_yolo/
    000000.txt
    000001.txt
    000002.txt
    000003.txt
    000004.txt
  metadata/
    000000.json
    000001.json
    000002.json
    000003.json
    000004.json
  _backend/
    reference_blackdot/
      sample_000000/attempt_0/
      sample_000001/attempt_0/
      sample_000002/attempt_0/
      sample_000003/attempt_0/
      sample_000004/attempt_0/
  backend_run_log.json
  dataset_summary.json
  generation_plan.json
```

## Quality Checks

For each adapted sample, the wrapper checks:

- RGB file exists and has a valid PNG header.
- Mask file exists and has a valid PNG header.
- RGB image size matches mask image size.
- YOLO label file exists and is not empty.
- YOLO bbox values are all within 0-1.
- YOLO bbox matches the backend bbox computed from the exported mask.
- Per-image metadata exists.

The quality result is saved into each sample entry in `generation_plan.json`.

## Inspect Masks And Labels

Open or preview:

```text
rgb/000000.png
masks/000000.png
```

The mask should align with the black spot in the RGB image. The YOLO label should contain one line:

```text
class_id x_center y_center width height
```

All four bbox values should be normalized values between `0` and `1`.

## Common Failure Reasons

- Missing model assets under `assets/models/`.
- BlenderProc cannot find or launch Blender.
- GPU backend initialization fails and render falls back slowly.
- The old backend fails to place a visible defect after camera/light jitter.
- Backend writes `metadata.json` but no accepted samples.
- Adapter cannot find expected old backend files such as `rgb/000000.png`, `mask/000000.png`, or `labels_yolo/000000.txt`.
- YOLO label is empty or bbox values fall outside `0-1`.

If a sample fails, inspect:

```text
backend_run_log.json
dataset_summary.json
_backend/reference_blackdot/sample_XXXXXX/
```

`dataset_summary.json` records `failed_samples` after retry.
