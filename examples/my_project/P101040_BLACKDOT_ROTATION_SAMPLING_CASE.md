# P101040 Blue Black-Dot Rotation Sampling Case

Last updated: 2026-05-04

This case is for technical demo evidence. It proves that the system can keep
the camera and lighting fixed while rotating/translating the product object
itself and rendering a black-dot sample after each fixed angular step.

## Interference Policy

The case is implemented as an isolated wrapper:

```text
E:\BlenderProject\BlenderProc\examples\my_project\run_p101040_blackdot_rotation_sampling_case.py
```

It does not modify:

```text
defect_dataset_generator\app.py
defect_dataset_generator\core\renderer.py
examples\my_project\reference_blend_blackdot_multi_model.py
```

It only calls the existing black-dot reference backend with these diagnostic
arguments:

```text
--object_transform_mode keep_camera
--object_transform_camera_side front
--object_rotate_deg RX RY RZ
--object_translate X Y Z
```

This keeps production 3k-5k generation behavior unchanged. The output root is
also independent from production dataset folders.

## Recommended Full Run

Run from the repository root:

```powershell
cd E:\BlenderProject\BlenderProc
```

Use the project Python environment:

```powershell
D:\Anaconda\envs\defect_eval\python.exe examples\my_project\run_p101040_blackdot_rotation_sampling_case.py --out E:\BlenderProject\BlenderProc\examples\my_project\P101040_BLACKDOT_ROTATION_CASE_20260504_V3 --step-deg 20 --rotation-axis z --translation-direction 1,0,0 --translation-distance 0.01 --samples 16 --seed 90504 --safe-anchor-local-x=-0.28,0.28 --safe-anchor-local-y=-0.28,0.28
```

Do not use `--allow-active-blender` while the 3k-5k dataset build is rendering
unless GPU contention is acceptable.

## Parameters

| Parameter | Meaning |
| --- | --- |
| `--step-deg 20` | Render one frame every 20 degrees. A 360-degree turn produces 18 frames: 0 to 340 degrees. |
| `--rotation-axis z` | Rotate the model around the world Z axis. This keeps the front face visible for a clear paper figure. |
| `--translation-direction 1,0,0` | Translate along the world X direction. |
| `--translation-distance 0.01` | Apply a fixed 0.01-unit object translation to every frame. Larger values can push the dot out of frame at some rotation angles. |
| `--samples 16` | Low-to-medium sample count suitable for a technical demonstration figure. Increase if needed. |
| `--seed 90504` | Fixed seed so the black-dot placement is stable across frames. |
| `--safe-anchor-local-x=-0.28,0.28` | Restrict the black-dot anchor to the central local-X band so all rotation angles keep the dot visible. |
| `--safe-anchor-local-y=-0.28,0.28` | Restrict the black-dot anchor to the central local-Y band so all rotation angles keep the dot visible. |

## Expected Output

```text
P101040_BLACKDOT_ROTATION_CASE_YYYYMMDD/
  rotation_case_plan.json
  rotation_case_summary.json
  P101040_blackdot_rotation_contact_sheet.jpg
  rgb/angle_000.png ... angle_340.png
  masks/angle_000.png ... angle_340.png
  overlay/angle_000.png ... angle_340.png
  labels_yolo/angle_000.txt ... angle_340.txt
  per_angle_runs/angle_000/...
```

The summary records the angle, rotation vector, translation vector, source
metadata, bbox, RGB path, mask path, overlay path, and YOLO label path for each
accepted frame.

## Smoke Result

A full 18-frame run was generated at:

```text
E:\BlenderProject\BlenderProc\examples\my_project\P101040_BLACKDOT_ROTATION_CASE_20260504_V3
```

Checked manually:

- Contact sheet contains 18 angles from 0 to 340 degrees.
- RGB/overlay contains a visible black dot in every frame.
- Mask count is 18/18.
- Empty mask count is 0.
- Mask foreground pixel range is 42 to 53 pixels.
- Mask position aligns with the visible dot.
- Metadata reports GPU rendering with OPTIX.
