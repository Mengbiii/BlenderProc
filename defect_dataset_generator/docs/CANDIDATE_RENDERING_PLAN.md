# Candidate Rendering Plan

## 1. Goal

Create a stable clean-render backend for material fitting. The renderer should load a clean `.blend`, apply one material parameter set, render one deterministic image, and write render metadata.

This module exists only for material fitting candidate images. It must not apply defects or randomization.

## 2. Constraints

- No defects.
- Fixed deterministic camera.
- Fixed deterministic light.
- Fixed deterministic world background.
- Deterministic output for the same input `.blend` and material JSON.
- Keep BlenderProc-specific logic inside `blender_scripts/render_candidate.py`.
- Keep normal Python orchestration in `core/material_fitter.py` or future wrappers.
- Do not reuse black-spot defect rendering logic here.

## 3. Input Schema

Command-line inputs:

```text
--blend <path_to_clean_blend>
--material-json <path_to_material_json>
--output <path_to_rendered_png>
--metadata <path_to_metadata_json>
--width <int, default 1024>
--height <int, default 768>
--samples <int, default 32>
--target-object <optional object name>
```

Material JSON input:

```json
{
  "base_color": [0.78, 0.80, 0.82, 1.0],
  "roughness": 0.5,
  "specular": 0.35,
  "subsurface": 0.0,
  "noise_strength": 0.0,
  "bump_strength": 0.0,
  "light_strength": 450.0,
  "exposure": 0.0
}
```

Missing optional material fields use safe defaults.

## 4. Output Schema

Rendered image:

```text
<output>.png
```

Metadata JSON:

```json
{
  "schema_version": "0.1",
  "status": "success",
  "blend_file": "path",
  "output_image": "path",
  "material_parameters": {},
  "render": {
    "engine": "CYCLES",
    "width": 1024,
    "height": 768,
    "samples": 32,
    "exposure": 0.0
  },
  "camera": {
    "type": "ORTHO",
    "location": [],
    "rotation_euler": [],
    "ortho_scale": 1.0
  },
  "light": {
    "type": "AREA",
    "location": [],
    "strength": 450.0,
    "size": 4.0
  },
  "world": {
    "color": [0.78, 0.78, 0.78],
    "strength": 0.8
  },
  "objects_rendered": [],
  "warnings": []
}
```

On failure, write metadata with:

```json
{
  "status": "failed",
  "failure_reason": "..."
}
```

## 5. Material Parameter Mapping

| Parameter | Mapping |
| --- | --- |
| `base_color` | Principled BSDF `Base Color`. |
| `roughness` | Principled BSDF `Roughness`. |
| `specular` | Principled BSDF `Specular IOR Level` if available, else `Specular` if available. |
| `subsurface` | Principled BSDF `Subsurface Weight` if available, else `Subsurface` if available. |
| `noise_strength` | Optional procedural noise influence reserved for future use; baseline records value but does not build complex shader networks. |
| `bump_strength` | Optional bump node strength if a normal input is available; baseline records value and may skip if shader input is unavailable. |
| `light_strength` | Area light energy. |
| `exposure` | Scene view exposure. |

The first implementation should set the direct Principled inputs robustly and record warnings for missing shader inputs instead of failing.

## 6. Rendering Configuration

Default configuration:

```text
resolution: 1024 x 768
samples: 32
engine: CYCLES
camera: deterministic orthographic camera fitted to object bounds
light: deterministic area light above/front of object bounds
world background: neutral gray
view transform: Filmic if available, look None, exposure from material params, gamma 1
```

Camera fitting rule:

1. Compute world-space bounds of target mesh objects.
2. Compute center and diagonal size.
3. Place orthographic camera at a deterministic front/top angle relative to the bounds.
4. Aim camera at the bounds center.
5. Set orthographic scale to cover the larger object dimension with a small margin.

This is deterministic for the same loaded model and avoids random camera placement.

## 7. Failure Handling

Handle and report:

- Missing `.blend` file.
- No mesh object found.
- Requested `--target-object` not found.
- Shader input missing: warn and continue if non-critical.
- Render failure: write failed metadata and exit nonzero.
- Output directory cannot be created: fail with reason.

## 8. Integration

Future `core/material_fitter.py` integration:

1. Generate material candidates.
2. For each candidate, write `candidate_XXXXXX_material.json`.
3. Call:

```powershell
python cli.py run defect_dataset_generator/blender_scripts/render_candidate.py -- --blend <blend> --material-json <candidate_json> --output <candidate_png> --metadata <candidate_metadata>
```

4. Store renders in:

```text
outputs/fitting/<run_name>/candidate_renders/
  candidate_000000.png
  candidate_000000_metadata.json
```

5. Score those renders using the existing real material fitting path.

For now, material fitting can continue to use `--candidate-dir` until this backend is wired into the fitter orchestration.
