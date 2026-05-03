# System Architecture

## System Overview

The system is a modular synthetic defect dataset generator for injection-molded plastic parts. It separates normal Python orchestration from BlenderProc scene code:

- `app.py` and `core/`: normal Python CLI, config, validation, planning, scoring, and export logic.
- `blender_scripts/`: BlenderProc-only scripts that load scenes, apply materials/defects, and render images.
- `config/`: default project settings, defect presets, and material search space.
- `outputs/`: default fitting and dataset output locations.

## Default Production Pipeline

```text
User Inputs
  model-color profile or imported .blend/.stl
  optional manual material profile
  defect preset + optional user overrides
        |
        v
Profile/File Management
  validate assets, model-color target, material source, supported defects
        |
        v
Clean Baseline
  render or inspect no-defect scene to confirm geometry/camera/profile alignment
        |
        v
Material Resolution
  default: embedded .blend material or manual material profile
  optional: fitted best_material.json
        |
        v
Defect Preset Resolution
  base defect preset + model-color constraints + explicit user overrides
  optional: defect realism/fitting optimization result
  default placement limited to front/back main planes
        |
        v
Domain Randomization
  default light camera background jitter, with user override hooks
        |
        v
Defect Generation
        |
        v
Batch Rendering through BlenderProc
        |
        v
Export
  RGB images, masks, YOLO labels, metadata, dataset_summary.json
```

## Optional Optimization Pipelines

Automatic material fitting is no longer a required production step. It is an optional calibration path used when embedded or manually prepared material profiles are not good enough.

```text
real reference images + clean model/profile
        |
        v
candidate material params -> render_candidate.py -> similarity scoring
        |
        v
best_material.json
        |
        v
optional promotion into material profile after human/visual acceptance
```

Defect realism optimization is also optional. The default production path uses stable defect presets plus explicit user parameters first, then later uses contact sheets and non-YOLO metrics to tune and promote better presets.

## Module Responsibilities

| Module | Responsibility |
| --- | --- |
| Input/File Management | Resolve Windows-compatible paths, validate images/models/configs, create output folders, inspect project structure. |
| Material Fitting | Generate material candidates, optionally call BlenderProc candidate rendering, score candidate renders against real images, rank candidates, and save visual material calibration outputs. |
| Candidate Rendering | Render deterministic clean material candidates through BlenderProc without defects or randomization, then write PNG and render metadata. |
| Similarity Metrics | Compute score profiles: `baseline` for generic image similarity and `plastic_material` for ROI-based visual material calibration using brightness, color, local contrast, highlight, texture, and low-weight SSIM. Supports full, center, auto, manual, and mask ROI. |
| Defect Generation | Normalize defect schema and apply defect-specific logic through BlenderProc helpers. |
| Defect Placement Policy | Default to front/back main-plane regions only; side walls, holes, complex edges, and bevel/transition areas require explicit opt-in after smoke validation. |
| Domain Randomization | Produce default light camera/background jitter and accept user-supplied fixed values or custom ranges. |
| Camera Randomization | Default to light domain randomization: angle roughly +/-5 to +/-15 degrees, slight distance change, and narrow focal length variation. |
| Lighting Randomization | Default to light domain randomization: strength +/-20%, slight direction change, mild area-size variation, and conservative brightness variation. |
| Background Randomization | Default to slight neutral color variation; profile or user config can fix or widen the range. |
| Batch Rendering | Run N render samples, retry failed samples, pass optional fitted material overrides to supported backends, and collect output paths and render parameters. |
| Export | Save labels, masks, metadata JSON, dataset summaries, quality reports, and small YOLO-ready split folders when validation labels are sound. |
| CLI / GUI | CLI is the first interface; GUI is planned only after backend stability. |

## Data Flow

1. CLI reads user paths and config.
2. File manager validates inputs and creates output directories.
3. Model-color profile resolves the intended geometry, appearance color, material source, supported defect types, and placement zones.
4. Clean baseline validation confirms that the model/profile renders the intended physical part before material or defect work proceeds.
5. Material resolution uses embedded `.blend` materials or a manual material profile by default. Fitted `best_material.json` is used only when explicitly requested or promoted.
6. Defect resolution uses base presets plus model-color constraints and explicit user overrides by default. Defect optimization outputs are optional preset updates.
7. Default defect placement is limited to the model's front/back main planes. Side walls, holes, bevels, and complex edges are excluded unless a profile or user config explicitly enables them.
8. Generate command normalizes defect config and prepares default domain randomization settings.
9. Default domain randomization applies conservative jitter: light strength +/-20%, slight light direction change, camera angle roughly +/-5 to +/-15 degrees, slight distance change, and slight neutral background color variation.
10. User-supplied fixed values or ranges can override camera, light, or background defaults through profile/config fields.
11. For the first production backend, `black_spot` / `black_dot` calls `examples/my_project/reference_blend_blackdot_multi_model.py` through the local BlenderProc CLI.
12. Supported black-spot runs may pass fitted visual material calibration with `--apply-material`; the backend receives `--material_json` and uses only `material_parameters`.
13. Controlled small batches run as repeated one-sample backend calls. Each sample gets a different seed and one retry.
14. The adapter maps the old backend layout (`mask/`) into the new framework layout (`masks/`) and writes per-image metadata.
15. Dataset validation can compute bbox statistics, mask visibility proxies, contact sheets, and optional YOLO 80/20 split folders.
16. Future BlenderProc backend scripts will consume plans directly and produce rendered images, masks, labels, and per-image metadata.

## Expected Input

```text
model-color profile or clean .blend/.stl model
embedded material, manual material profile, or optional best_material.json
defect preset JSON plus optional user overrides
domain randomization profile or explicit fixed values/ranges
```

## Expected Output

```text
outputs/fitting/
  candidate_materials/
  candidate_renders/
  candidate_metadata/
  best_material.json
  material_fit_candidates.json
  material_fitting_report.json
  best_preview_render.*

outputs/dataset/
  rgb/
  masks/
  labels_yolo/
  metadata/
  dataset_quality_report.json
  generation_plan.json
  dataset_summary.json
  yolo_dataset/
```

## Current Limitations

- Material fitting supports mock scoring, real scoring from `--candidate-dir`, and real automatic candidate rendering through `--render-candidates`.
- Automatic material candidate rendering has been validated on a small synthetic reference run and one real white plastic reference run.
- Real-reference material fitting is visual material calibration only; background, camera, crop, shadows, and texture mismatch can dominate the metric score.
- Defect parameters are excluded from material fitting outputs.
- The `plastic_material` score is deterministic and explainable, but validation shows it can still disagree with human judgment when candidate differences are subtle.
- First mask ROI validation used an approximate rectangular mask, not a true semantic material mask.
- Preview currently creates a plan, not an actual rendered PNG.
- Generate can render real `black_spot` / `black_dot` samples through the first production backend for controlled small batches; other defect modes still create plans only.
- Fitted visual material calibration can be applied to the black-spot backend for visual ablation runs, but scene calibration fields are not applied there yet.
- A count=20 training-oriented material ablation dataset has been generated and validated, but no detector training has been run yet.
- Defect generation is schema-only in the new framework; real defect application remains in existing scripts.
- Only YOLO export scaffolding exists; real bbox export depends on masks/render metadata.
- GUI is not implemented in the new framework.

## Future Improvements

- Extend the `reference_blend_blackdot_multi_model.py` wrapper across more model profiles and add cautious production batch limits.
- Validate fitted material overrides across more real references and model profiles before treating them as production defaults.
- Extract black-dot logic into reusable BlenderProc helpers.
- Validate material fitting against real reference photos and add optional LPIPS later.
- Add manual or mask-based material ROI support so real-photo scoring focuses on clean plastic regions.
- Add camera/profile alignment before treating fitted materials as production-ready.
- Add model/appearance profiles for P101040, QC71336, QC75244, and moxing1.
- Add controlled smoke tests for mixed color, foreign material, splay, and sink/dent.
- Add failed-render retry logic and dataset quality reports.
