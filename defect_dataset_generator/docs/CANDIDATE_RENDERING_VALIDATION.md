# Candidate Rendering Validation

## Purpose

Validate `blender_scripts/render_candidate.py` as a deterministic clean-render backend for material fitting candidate images.

This validation does not use defect rendering, camera randomization, light randomization, or batch defect generation.

## Backend Script

```text
defect_dataset_generator/blender_scripts/render_candidate.py
```

Executed through the local BlenderProc CLI:

```powershell
python E:\BlenderProject\BlenderProc\cli.py run E:\BlenderProject\BlenderProc\defect_dataset_generator\blender_scripts\render_candidate.py -- ...
```

## Test Blend

```text
E:\BlenderProject\BlenderProc\assets\models\moxing1_test.blend
```

Detected and rendered mesh:

```text
QC7-5236-000N301002ST0101
```

Excluded scene support objects included planes/background-like objects, so the candidate material was applied to the product mesh only.

## Test Parameter Sets

```text
outputs/fitting/render_candidate_test/materials/very_rough.json
outputs/fitting/render_candidate_test/materials/smooth.json
outputs/fitting/render_candidate_test/materials/bright_dark.json
```

### Very Rough

```json
{
  "roughness": 0.92,
  "specular": 0.18,
  "base_color": [0.72, 0.74, 0.76, 1.0]
}
```

### Smooth

```json
{
  "roughness": 0.18,
  "specular": 0.65,
  "base_color": [0.72, 0.74, 0.76, 1.0]
}
```

### Bright / Dark

```json
{
  "base_color": [0.35, 0.38, 0.42, 1.0],
  "roughness": 0.48,
  "specular": 0.35,
  "light_strength": 700.0,
  "exposure": 0.3
}
```

## Example Command

```powershell
python E:\BlenderProject\BlenderProc\cli.py run E:\BlenderProject\BlenderProc\defect_dataset_generator\blender_scripts\render_candidate.py -- --blend E:\BlenderProject\BlenderProc\assets\models\moxing1_test.blend --material-json E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\fitting\render_candidate_test\materials\very_rough.json --output E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\fitting\render_candidate_test\very_rough.png --metadata E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\fitting\render_candidate_test\very_rough_metadata.json --width 512 --height 384 --samples 8
```

The same command shape was used for `smooth.json` and `bright_dark.json`.

## Outputs

```text
outputs/fitting/render_candidate_test/
  very_rough.png
  very_rough_metadata.json
  smooth.png
  smooth_metadata.json
  bright_dark.png
  bright_dark_metadata.json
  materials/
    very_rough.json
    smooth.json
    bright_dark.json
```

All rendered images were readable PNG files:

| Output | Size | Mode | Status |
| --- | --- | --- | --- |
| `very_rough.png` | `512 x 384` | `RGBA` | success |
| `smooth.png` | `512 x 384` | `RGBA` | success |
| `bright_dark.png` | `512 x 384` | `RGBA` | success |

## Metadata Check

Each metadata file records:

- status;
- source blend;
- material JSON path;
- material parameters;
- render resolution and samples;
- deterministic orthographic camera;
- deterministic area light;
- neutral world background;
- rendered object names;
- warnings and failure reason.

For `very_rough` and `smooth`, camera and light positions were identical. This confirms stable scene setup when only material parameters change.

## Observations

- The backend successfully loads the `.blend`, selects the product mesh, applies candidate material, and renders without defects.
- Camera, world background, and geometry framing are deterministic.
- Direct Principled BSDF fields mapped without warnings on this test asset.
- `bright_dark` intentionally changes light strength and exposure because those fields are part of the candidate parameter schema. This is deterministic, but future material fitting should decide whether light/exposure belong in material fitting or scene calibration.

## Current Limitations

- Candidate rendering is not yet orchestrated from `core/material_fitter.py`.
- The renderer selects target mesh objects heuristically when `--target-object` is not supplied.
- Noise without bump is recorded but not applied in the baseline shader.
- The camera is deterministic and fitted from object bounds, not a hand-calibrated real camera yet.

## Validation Conclusion

`render_candidate.py` is ready as a deterministic clean-render backend prototype. The next implementation step is to let `material_fitter.py` generate candidate material JSON files, call this renderer per candidate, store renders under `outputs/fitting/<run_name>/candidate_renders/`, and reuse the existing real scoring path.
