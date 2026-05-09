# Current Project Handoff

Last updated: 2026-05-09

This handoff is for the next maintenance session. The current project is a
BlenderProc-based synthetic defect dataset generator for plastic workpieces.
The immediate goal is now to continue safe 3k-5k dataset construction using
only user-accepted combinations, while preserving manual RGB/mask inspection as
the final acceptance gate.

For the newest usage-oriented handoff, also read:

```text
defect_dataset_generator/docs/SYSTEM_USAGE_GUIDE.md
defect_dataset_generator/docs/NEXT_HANDOFF_2026_05_04.md
defect_dataset_generator/docs/FINAL_PACKAGE_CONTENTS.md
```

## 2026-05-09 QC71336 Gray Material And Mixed-Color Handoff

The latest active work focused on `qc71336_gray`, especially the gray material
and `mixed_color_contamination` appearance. The main edited script is:

```text
defect_dataset_generator/blender_scripts/render_qc71336_gray_defects.py
```

Current routing expectations:

- `qc71336_gray` single `black_dot` still uses
  `examples/my_project/reference_blend_blackdot_multi_model.py`.
- `qc71336_gray` single `mixed_color_contamination` uses
  `defect_dataset_generator/blender_scripts/render_qc71336_gray_defects.py`.
- `qc71336_gray` same-scene `black_dot + mixed_color_contamination` also uses
  `render_qc71336_gray_defects.py`.
- The dedicated script validates the target name as `qc71336_gray`; commands
  using `qc71336-grey` fail validation.

Gray material status:

- `render_qc71336_gray_defects.py` now applies a target-specific textured gray
  override through `QC71336_GRAY_TEXTURED_PROFILE`.
- The material is intentionally cool light gray, high roughness, low specular,
  with fine noise/bump and broader low-frequency variation to mimic the real
  QC71336 gray surface.
- The reference real gray image used in the latest discussion is the normal
  QC71336 gray real photo named `9K9A0362.JPG` under the real-data
  `QC71336 gray / normal` folder.

Mixed-color defect status:

- The accepted direction is a very subtle material-color residue on the smooth
  central gray panel, not the dotted/pebbled outer texture field.
- `create_defect()` now routes `qc71336_gray + mixed_color_contamination`
  through `sample_qc71336_gray_smooth_panel_anchor(...)`, instead of the generic
  normalized bbox placement window. This sampler records `smooth_panel_anchor`,
  `anchor_polygon_index`, `anchor_local_xyz`, `world_point`, and
  `world_normal` in metadata.
- The current procedural style is
  `thin_interrupted_spiral_with_local_haze`: several long, thin, open arc
  segments arranged as an interrupted spiral. It should read as smooth faint
  injection-molding flow residue, not as a closed ring, scratch, black stain, or
  chunky decal.
- The line geometry is built with `add_feathered_arc_stain(...)`. Recent tuning
  reduced random jitter and width noise so arcs are smoother, with only slight
  diffusion at the edge.
- The previous standalone large mixed-color patch is no longer used as an
  isolated blob. Instead, faint `CLOUD_ARC` support meshes wrap each arc
  locally as a cloudy base. These support meshes are visible in RGB but tagged
  with `support_artifact_role`, so `defect_mesh_objects()` excludes them from
  mask and bbox calculations unless explicitly requested.
- `make_qc71336_gray_mixed_color_materials()` is now intentionally very low
  contrast. Current alpha values are:
  `haze=0.018`, `haze_outer=0.006`, `mist=0.030`, `outer=0.064`,
  `mid=0.118`, `core=0.185`.
- A small normal-direction lift is applied for QC71336 gray mixed-color decals
  so RGB renders do not lose them to coplanar depth sorting.
- `--debug_anchor_overlay` can save an RGB overlay with the bbox and procedural
  anchor point for placement debugging.

Latest validation command:

```text
D:/Anaconda/envs/defect_eval/python.exe -m py_compile E:/BlenderProject/BlenderProc/defect_dataset_generator/blender_scripts/render_qc71336_gray_defects.py
```

Latest visual check output:

```text
examples/my_project/QC71336_GRAY_MIXEDCOLOR_THIN_SPIRAL_LOCAL_HAZE_V20/rgb/000000.png
examples/my_project/QC71336_GRAY_MIXEDCOLOR_THIN_SPIRAL_LOCAL_HAZE_V20/rgb/000001.png
examples/my_project/QC71336_GRAY_MIXEDCOLOR_THIN_SPIRAL_LOCAL_HAZE_V20/mask/000000.png
examples/my_project/QC71336_GRAY_MIXEDCOLOR_THIN_SPIRAL_LOCAL_HAZE_V20/mask/000001.png
```

Interpretation of the latest preview:

- The accepted geometry is the V20 family: thin, long, interrupted spiral arcs
  on the smooth panel with local haze. After V20, contrast was lowered further
  and arc jitter was smoothed, but no placement or mask/bbox logic was changed.
- The final target is intentionally subtle; the user wants low-contrast
  gray-on-gray mixed-color flow residue. Do not raise visibility by making the
  line black or thick.
- If further tuning is needed, first adjust arc scale/count/alpha in
  `add_qc71336_gray_soft_spiral_mixed_color_defect()` and
  `make_qc71336_gray_mixed_color_materials()`. Avoid changing placement policy,
  black-dot routing, or mask support filtering unless the user explicitly asks.

Other touched files in the working tree:

```text
examples/my_project/reference_blend_blackdot_multi_model.py
examples/my_project/reference_blend_qc71336_white_prebuilt_normal_debug.py
```

The user said changes to `reference_blend_blackdot_multi_model.py` are okay
because QC71336 gray black-dot generation still uses that route. Do not revert
these files blindly; inspect the diff and preserve user/session changes.

## 2026-05-07 Dedicated Script Routing Update

Two target-specific renderer scripts are now available and routed through the
main CLI for their supported targets:

```text
defect_dataset_generator/blender_scripts/render_qc71336_gray_defects.py
defect_dataset_generator/blender_scripts/render_qc75244_black_defects.py
```

Routing summary:

- `qc71336_gray` single `black_dot` uses
  `examples/my_project/reference_blend_blackdot_multi_model.py`; single
  `mixed_color_contamination` uses `render_qc71336_gray_defects.py`.
- `qc71336_gray` same-scene `black_dot + mixed_color_contamination` now uses
  `render_qc71336_gray_defects.py`.
- `qc7_5244_black` single `black_dot`, `foreign_material`, and `splay` now use
  `render_qc75244_black_defects.py`.
- `qc7_5244_black` same-scene combinations now use
  `render_qc75244_black_defects.py`.

The desktop UI cooccurrence dropdown now exposes:

- `qc71336_gray`: `black_dot + mixed_color_contamination`;
- `qc7_5244_black`: `black_dot + foreign_material`,
  `black_dot + splay`, `foreign_material + splay`, and
  `black_dot + foreign_material + splay`.

QC71336 gray note: the single black-dot route was returned to the reference
black-dot script. The same-scene gray script keeps internal black-dot support
only for `black_dot + mixed_color_contamination`; that path now samples the
black-dot anchor from the real mesh surface and embeds it along the surface
normal. Its support plane follows the reference front/back tabletop placement,
so the part and defect no longer appear detached from the table in the latest
smoke sample.

The previous generic routes are still present for other targets. Push and
release steps should be handled separately after local verification.

## 2026-05-07 Same-Type Multi-Defect Supplement Dataset

A standalone supplement dataset has been assembled for images that contain
multiple defects of the same type in one image. This dataset is intentionally
kept separate from the cleaned 3k-5k main dataset and should be treated as an
optional supplement package.

Supplement dataset root:

```text
defect_dataset_generator/outputs/dataset/same_type_multi_defect_supplement_dataset_20260507/
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

Selection and audit policy:

- only samples with at least two YOLO label rows were copied;
- `_backend` directories were excluded;
- every copied sample has matching RGB, mask, label, and metadata files;
- label files contain 2 to 3 same-type defect instances;
- the supplement is not merged into
  `final_3k_5k_dataset_20260504/`.

Final supplement audit:

- Total samples: `470`
- RGB files: `470`
- Mask files: `470`
- Label files: `470`
- Metadata files: `470`
- Empty or single-instance labels: `0`
- Missing paired files: `0`

Source roots:

```text
defect_dataset_generator/outputs/dataset/same_type_multi_defect_supplement_30_each_20260506/
defect_dataset_generator/outputs/dataset/same_type_multi_defect_balanced_30_total_20260506/
defect_dataset_generator/outputs/dataset/same_type_multi_defect_topup_small_batches_20260507/
```

Per-combination accepted multi-instance counts:

| Combination | Count |
| --- | ---: |
| `p101040_blue_black_dot` | 60 |
| `qc71336_black_foreign_material` | 34 |
| `qc71336_black_splay` | 30 |
| `qc71336_gray_black_dot` | 30 |
| `qc71336_gray_mixed_color_contamination` | 30 |
| `qc71336_white_black_dot` | 45 |
| `qc71336_white_foreign_material` | 31 |
| `qc7_5244_black_black_dot` | 30 |
| `qc7_5244_black_foreign_material` | 30 |
| `qc7_5244_black_splay` | 30 |
| `qc7_5244_white_black_dot` | 30 |
| `qc7_5244_white_mixed_color_contamination` | 30 |
| `ql3_1052_black_foreign_material` | 30 |
| `ql3_1052_black_splay` | 30 |

## 2026-05-06 Packaging Update

The final packaging scope is now documented in:

```text
defect_dataset_generator/docs/FINAL_PACKAGE_CONTENTS.md
```

Package source code, model assets, and the cleaned dataset as separate
deliverables. The source package should include the generator code,
configuration, UI, reference backend scripts, and documentation. Model files
under `assets/models/` should be packaged separately. Generated outputs under
`defect_dataset_generator/outputs/` should not be included in the source
package.

The cleaned dataset root is:

```text
defect_dataset_generator/outputs/dataset/final_3k_5k_dataset_20260504/
```

The dataset root now contains only `images/`, `masks/`, `labels/`,
`metadata/`, `manifest.csv`, `dataset_summary.json`, and `README_DATASET.md`.
Auxiliary reports and quarantined intermediate files were moved to the sibling
archive directory.

## 2026-05-06 Same-Type Multi-Defect Update

Single-defect production backends now support multiple same-type defects per
image. Use `generate-target --defect-count-max N` to sample a random instance
count from `1` to `N` per rendered image. The default remains `1`.

Current supported backend coverage:

- reference black-dot targets;
- generic main-plane single-defect targets;
- QC71336 black prebuilt `foreign_material` and `splay`;
- QC71336 white prebuilt `foreign_material`;
- QC7-5244 white mixed-color reference backend.

Output policy:

- merged mask contains all visible same-type instances;
- YOLO label file contains one row per visible instance;
- metadata records `defect_count` and per-instance bbox/placement fields;
- default behavior remains a single instance per image because
  `--defect-count-max` defaults to `1`;
- the desktop UI now exposes a main `Max Defects` control in single-defect
  mode and passes it directly as `--defect-count-max`.

QC7-5244 white mixed-color correction:

- The mixed-color multi-defect route must use
  `reference_blend_qc75244_mixed_color_profile_debug.py`.
- The invalid smoke output that used a generic rectangular patch fallback
  should not be used for review:
  `defect_dataset_generator/outputs/smoke/same_type_batch5_all_combos_20260506/qc7_5244_white_mixed_color/`.
- The corrected smoke output is:
  `defect_dataset_generator/outputs/smoke/qc75244_mixed_reference_batch5_visible_fix_20260506/`.

## 2026-05-05 Normal Dataset Update

The final 3k-5k dataset assembly was corrected after the earlier normal images
were found to be too regular and visually inconsistent with accepted defect
images. The old normal rows were removed from the final dataset manifest and
quarantined, then a new 700-image normal set was generated and appended.

Current final dataset state:

- Final dataset root: `defect_dataset_generator/outputs/dataset/final_3k_5k_dataset_20260504`
- Final manifest row count: `3472`
- Defect rows: `2772`
- Normal rows: `700`
- Normal target/side allocation: `7` targets x `2` sides x `50` images
- Regenerated normal source root: `defect_dataset_generator/outputs/dataset/production_normal_flip_20260505`
- Visual check sheet: `normal_regenerated_front_back_contact_sheet_20260505.jpg`

Normal rendering policy now follows the accepted tabletop style:

- P101040 normal images use the same reference black-dot scene path as
  `p101040_blue black_dot`, but with defect creation disabled.
- Other normal images use the generic main-plane path with a neutral tabletop
  background, constrained tabletop camera sampling, and domain randomization.
- Back-side normal images are produced by flipping the product object while
  keeping the camera/background style front-facing, not by orbiting the camera
  behind the object.
- QL3 normal material is forced back to a dark rough plastic appearance and
  should not render as a shiny silver surface.
- Normal labels are intentionally empty and normal masks are fully black.

Do not commit generated dataset files from `defect_dataset_generator/outputs/`.
They are ignored by Git and should remain artifact/output data.

## Current Priority

The current priority is:

1. Keep the existing target-specific scripts and profiles intact.
2. Continue 3k-5k dataset generation with GPU rendering.
3. Use only combinations manually accepted by the user.
4. Keep front/back at 1:1 for non-QL3 targets.
5. Keep front/side at 1:1 for QL3.
6. Inspect RGB and mask outputs after every block.
7. Use evaluation scripts only as support; do not replace manual inspection.

The user explicitly wants cautious changes. Many targets depend on specific scripts, material profiles, reference scenes, and model files. Do not replace a reference/specialized backend with a generic backend just for speed.

## Active Dataset Targets

The production target registry is:

```text
defect_dataset_generator/config/model_color_defect_targets.json
defect_dataset_generator/config/model_color_profiles.json
```

Active accepted combinations:

| Target | Active defects | Required sides | Current backend state |
| --- | --- | --- | --- |
| `p101040_blue` | `black_dot` | front/back where supported by command/profile | `reference_blackdot`; batch-optimized. Spot-check every production block. |
| `qc71336_black` | `foreign_material`, `splay`, `foreign_material+splay` | front/back | QC71336 black reference backend. Single defects and approved cooccurrence are connected to the dedicated reference script. |
| `qc71336_white` | `black_dot`, `foreign_material` | front/back | Black dot uses `reference_blackdot`; foreign material uses QC71336 white reference backend. User accepted the previously disputed foreign-material front/back cases. |
| `qc71336_gray` | `black_dot`, `mixed_color_contamination`, `black_dot+mixed_color_contamination` | front/back | Single black dot uses `reference_blackdot`; mixed color and same-scene black-dot+mixed-color use the dedicated gray script. The same-scene black dot now uses reference-style mesh-surface anchoring and tabletop support. |
| `qc7_5244_black` | `black_dot`, `foreign_material`, `splay`, approved same-scene combinations | front/back | Dedicated QC7-5244 black script with manual black material profile. Approved same-scene combinations are black_dot+foreign_material, black_dot+splay, foreign_material+splay, and black_dot+foreign_material+splay. |
| `qc7_5244_white` | `black_dot`, `mixed_color_contamination` | front/back | Black dot uses `reference_blackdot`; mixed color uses specialized QC75244 mixed-color reference backend. User accepted black-dot back and mixed-color front/back. |
| `ql3_1052_black` | `foreign_material`, `splay` | front/side only | Generic main-plane using `QL3-black.blend`. User accepted defect appearance after placement bug was fixed. Cooccurrence is cancelled. |

Excluded:

| Defect | Reason |
| --- | --- |
| `sink_mark` | Intentionally excluded from the current 400-500 and later 3k-5k target set. Existing code is placeholder/fallback only. |

## Backend Routing

Main CLI:

```text
defect_dataset_generator/app.py
```

Production generation handoff docs:

```text
defect_dataset_generator/docs/BLACK_DOT_SINGLE_DEFECT_3K_5K_HANDOFF.md
defect_dataset_generator/docs/APPROVED_NON_BLACK_DEFECT_3K_FILLER_HANDOFF.md
defect_dataset_generator/docs/SYSTEM_USAGE_GUIDE.md
defect_dataset_generator/docs/NEXT_HANDOFF_2026_05_04.md
```

Primary commands:

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py list-targets
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target qc7_5244_black --defects black_dot --count 5 --samples 16 --seed 5501 --out defect_dataset_generator\outputs\dataset\smoke_YYYYMMDD
```

Routing summary:

| Target | Defect | Backend | Key script |
| --- | --- | --- | --- |
| `p101040_blue` | `black_dot` | `reference_blackdot` | `examples/my_project/reference_blend_blackdot_multi_model.py` |
| `qc71336_black` | `foreign_material` | `qc71336_black_reference` | `examples/my_project/reference_blend_qc71336_black_prebuilt_normal_debug.py` |
| `qc71336_black` | `splay` | `qc71336_black_reference` | `examples/my_project/reference_blend_qc71336_black_prebuilt_normal_debug.py` |
| `qc71336_black` | `foreign_material+splay` | `qc71336_black_reference_cooccurrence` | `examples/my_project/reference_blend_qc71336_black_prebuilt_normal_debug.py` |
| `qc71336_white` | `black_dot` | `reference_blackdot` | `examples/my_project/reference_blend_blackdot_multi_model.py` |
| `qc71336_white` | `foreign_material` | `qc71336_white_foreign_reference` | `examples/my_project/reference_blend_qc71336_white_prebuilt_normal_debug.py` |
| `qc71336_gray` | `black_dot` | `reference_blackdot` | `examples/my_project/reference_blend_blackdot_multi_model.py` |
| `qc71336_gray` | `mixed_color_contamination` | `qc71336_gray_dedicated` | `defect_dataset_generator/blender_scripts/render_qc71336_gray_defects.py` |
| `qc71336_gray` | `black_dot+mixed_color_contamination` | `qc71336_gray_dedicated_cooccurrence` | `defect_dataset_generator/blender_scripts/render_qc71336_gray_defects.py` |
| `qc7_5244_black` | `black_dot` | `qc75244_black_dedicated` | `defect_dataset_generator/blender_scripts/render_qc75244_black_defects.py` |
| `qc7_5244_black` | `foreign_material` | `qc75244_black_dedicated` | `defect_dataset_generator/blender_scripts/render_qc75244_black_defects.py` |
| `qc7_5244_black` | `splay` | `qc75244_black_dedicated` | `defect_dataset_generator/blender_scripts/render_qc75244_black_defects.py` |
| `qc7_5244_white` | `black_dot` | `reference_blackdot` | `examples/my_project/reference_blend_blackdot_multi_model.py` |
| `qc7_5244_white` | `mixed_color_contamination` | `qc75244_mixed_color_reference` | `examples/my_project/reference_blend_qc75244_mixed_color_profile_debug.py` |
| `ql3_1052_black` | `foreign_material` | `generic_main_plane` | `defect_dataset_generator/blender_scripts/render_generic_main_plane_defects.py` |
| `ql3_1052_black` | `splay` | `generic_main_plane` | `defect_dataset_generator/blender_scripts/render_generic_main_plane_defects.py` |

## Recent Work Completed on 2026-05-02

### Side-controlled generation and camera follow

Side metadata and side-controlled placement were added or tightened for generation planning. The intent is:

- front/back cases are generated for all non-QL3 targets;
- QL3 uses front/side only;
- camera should follow the selected defect side so the defect is visible;
- when using a backside case, the model may be transformed rather than moving the whole environment.

Important caution: this area still needs visual verification. Earlier backside tests showed background occlusion and insufficient backside lighting in some images. Do not assume every side-controlled case is accepted until RGB/mask overlays are checked.

### Model transform control for backside capture

A model transform approach was introduced so backside capture can keep the camera/environment mostly unchanged and transform the model instead. The design goal is configurable transforms, not hard-coded 180 degrees:

- default backside behavior is a 180-degree flip;
- rotation angle and movement offsets should remain user-adjustable;
- this should be applied per target/profile only where it improves backside visibility.

This is a speed and stability direction, not fully accepted visual policy yet.

### Multi-defect co-occurrence generation

Same-scene multi-defect generation exists for generic-equivalent combinations. The important behavior:

- It creates multiple defect objects in one scene/image.
- It does not simply generate separate images per defect type.
- It uses the same generic defect creation logic as single-defect generation for generic defects.
- The output uses one merged mask and YOLO labels by default.

Current safe scope:

- `qc71336_black` can co-occur `foreign_material` and `splay` through the dedicated QC71336 black reference script. Use `generate-target-cooccurrence --target qc71336_black --defects foreign_material,splay`; it routes to `--defect_type foreign_material_splay`, not generic fallback.
- `qc71336_gray` can co-occur `black_dot` and
  `mixed_color_contamination` through the dedicated gray script. The black dot
  in this path uses reference-style mesh-surface anchoring rather than
  bbox-plane placement.
- `qc7_5244_black` can co-occur `black_dot`, `foreign_material`, and `splay`
  through the dedicated QC7-5244 black script. Approved combinations are
  `black_dot+foreign_material`, `black_dot+splay`, `foreign_material+splay`,
  and `black_dot+foreign_material+splay`.
- `ql3_1052_black` co-occurrence is cancelled for the current plan. Keep QL3 to single `foreign_material` and single `splay` front/side only.
- Only run black-dot-containing cooccurrence for the approved rows above.

Current caution:

- Mixed reference/specialized co-occurrence, for example `reference_blackdot + specialized_mixed_color`, is not fully converted into the persistent generic path. Keep those on existing scripts unless a specific adapter is implemented.

### Mask output policy optimization

Mask output is now configurable. Default production output should be:

- RGB;
- merged mask;
- YOLO label;
- metadata.

Class-specific masks should only be enabled for diagnosis by using `--render-class-masks` where supported. This is faster and avoids unnecessary per-class mask rendering in large runs.

Relevant files:

```text
defect_dataset_generator/blender_scripts/render_generic_main_plane_defects.py
defect_dataset_generator/blender_scripts/render_persistent_generic_batch.py
defect_dataset_generator/core/renderer.py
defect_dataset_generator/app.py
```

### Persistent generic batch renderer

A new persistent renderer exists:

```text
defect_dataset_generator/blender_scripts/render_persistent_generic_batch.py
```

CLI entry:

```text
defect_dataset_generator/app.py generate-target-persistent-batch
```

It loads the model/scene/material/camera/lights once, then loops through samples:

```text
start BlenderProc once
load model once
build base scene once
for each sample:
    clear/change defects
    update side/camera/seed
    render RGB/mask/label/metadata
exit
```

This is only for samples whose defect backend is `generic_main_plane`. The app intentionally rejects non-equivalent reference/specialized defects in this path.

### Reference black-dot batch optimization

`reference_blackdot` no longer needs one BlenderProc launch per image for count > 1. `run_reference_blackdot_backend` now uses one backend batch command with `--num count`, adapts all samples afterward, and runs per-sample quality checks.

Verified smoke:

```text
Output: defect_dataset_generator/outputs/dataset/blackdot_batch_opt_smoke_p101040_2
Target: p101040_blue
Defect: black_dot
Count: 2
Result: 2/2 quality checks passed
Renderer: GPU/OPTIX metadata observed
```

### Rehearsal generation plan optimization

The 400-500 image rehearsal runner now groups generic-equivalent blocks into persistent batches.

Tool:

```text
defect_dataset_generator/tools/run_rehearsal_generation_plan.py
```

New behavior:

- Generic-equivalent single/co-occurrence/normal samples can be grouped by `target + side`.
- Reference/specialized samples remain on existing commands.
- Use `--no-persistent-generic` to disable this optimization.

Plan-only comparison for a 500-image plan:

| Mode | Blocks | Total images |
| --- | ---: | ---: |
| legacy | 52 | 500 |
| persistent optimized | 36 | 500 |

In the optimized plan, 232 images were grouped into 13 persistent generic blocks.

Validated dry-run:

```text
Command: generate-target-persistent-batch
Target: qc7_5244_black
Side: front
Planned samples: 31
Included modes: single, cooccurrence, normal
Status: dry-run succeeded
```

## Current Defect Implementation Status

### `black_dot`

Status: implemented for active targets.

- `p101040_blue`, `qc71336_white`, `qc71336_gray`, and `qc7_5244_white` use `reference_blackdot`.
- `qc7_5244_black` uses generic main-plane black dot.
- `reference_blackdot` batch speed is improved.

Known issues:

- `qc7_5244_black black_dot` was previously too dark/too high contrast; it was made smaller/lighter and lighting was raised.
- `qc71336_gray black_dot` single generation uses `reference_blackdot`. In
  same-scene gray generation, black-dot placement was corrected to use the
  reference-style surface anchor and embedded placement.

### `foreign_material`

Status: implemented but target-dependent.

- `qc71336_black`: reference backend, size upper bound was reduced toward "large rice grain" scale.
- `qc71336_white`: reference backend.
- `qc7_5244_black`: generic main-plane. Front/back were manually accepted on 2026-05-03, including the `foreign_material+splay` cooccurrence samples.
- `ql3_1052_black`: generic main-plane. On 2026-05-03 the user accepted the defect appearance; a placement bug was fixed so explicit front/side requests now produce matching `anchor_side`, `camera_side`, and `main_plane_axis`.

Known issues:

- `qc71336_black foreign_material` previously had mask/RGB visibility mismatch in at least one sample.
- `ql3_1052_black foreign_material` previously ignored explicit front/side requests because the generic script forced this defect to side. This was fixed on 2026-05-03; front smoke now reports `anchor_side=front`, side smoke reports `anchor_side=side`.

### `splay`

Status: implemented. `qc71336_black` front/back is manually accepted after size limiting; other targets remain visually fragile.

- `qc71336_black`: reference backend. Desired appearance is a thin, light line/streak, not a large pale patch. On 2026-05-03 the user manually accepted the size-limited front/back samples even though the automatic `rgb_defect_bbox_visible` quality gate still failed; for this target/defect, manual RGB/mask inspection overrides that automatic visibility failure.
- `qc7_5244_black`: generic main-plane. Front/back were manually accepted on 2026-05-03, including the `foreign_material+splay` cooccurrence samples.
- `ql3_1052_black`: generic main-plane. On 2026-05-03 the user accepted the defect appearance; a placement bug was fixed so `splay` is not forced to front when `--anchor-sides side` is requested.

Known issues:

- `qc71336_black splay` previously regressed into a large pale blotch. The current size-limited version should stay as a fine scratch; do not increase its random length/width upper bounds without re-review.
- Automatic quality checks may mark accepted `qc71336_black splay` images as failed because RGB contrast is intentionally subtle. Keep RGB/mask contact-sheet review as the acceptance standard for this combination.
- `ql3_1052_black splay` previously ignored explicit side requests because the generic script forced this defect to front. This was fixed on 2026-05-03; front/side smoke images now show different faces and matching metadata.

### `qc71336_black foreign_material+splay` cooccurrence

Status: implemented and smoke-tested on 2026-05-03.

- Script: `examples/my_project/reference_blend_qc71336_black_prebuilt_normal_debug.py`
- App command: `python defect_dataset_generator/app.py generate-target-cooccurrence --target qc71336_black --defects foreign_material,splay --count N --out OUT --samples 16 --seed SEED --anchor-sides front` or `--anchor-sides back`.
- Internal script parameter: `--defect_type foreign_material_splay`.
- Output: one RGB, one merged mask, one YOLO txt with two rows (`1` for `foreign_material`, `2` for `splay`), and metadata containing both individual defect records.
- Smoke outputs:
  - Direct front/back visual review: `defect_dataset_generator/outputs/dataset/_user_review_qc71336_black_cooccurrence_20260503/`
  - App-entry smoke: `defect_dataset_generator/outputs/dataset/_user_review_qc71336_black_cooccurrence_app2_20260503/`
- Manual visual result: front/back RGB and mask both contain a point-like foreign material and a fine splay scratch. The 60px bbox crop sheet confirms the foreign material exists in RGB as well as mask.
- Important batching note: for strict 1:1 front/back ratio, run separate front and back batches with separate `--anchor-sides front` and `--anchor-sides back` commands, then merge outputs. A mixed `--anchor-sides front back` request does not guarantee exact alternation for this reference script.

### `mixed_color_contamination`

Status: connected; accepted for the currently reviewed targets listed below.

- `qc71336_gray`: dedicated gray script. Single mixed-color and same-scene
  black-dot+mixed-color routes use `render_qc71336_gray_defects.py`; the
  same-scene route now uses reference-style tabletop support and surface
  anchoring for the black dot.
- `qc7_5244_white`: specialized QC75244 mixed-color reference backend. Front/back samples were manually accepted on 2026-05-03.

Known issues:

- `qc71336_gray mixed_color_contamination` once produced an all-white RGB with no mask defect in one image while other images were normal.
- `qc7_5244_white mixed_color_contamination` was too large and too yellow; after prior size/color changes, front/back smoke samples were manually accepted on 2026-05-03.

## Known Open Problems

1. Backside lighting may be insufficient.
   - Earlier backside evaluations showed darker images.
   - Need determine whether this is light position, model flip orientation, material response, or intensity.
   - Avoid blindly raising all lights; preserve accepted front-side appearance.

2. Background can occlude the model when backside transforms are used.
   - Some RGB images were blocked by the background plane.
   - Background placement must be side-aware or model-transform-aware.

3. Some generated images have no RGB output or no visible defect.
   - Check backend logs and metadata before rerunning large batches.
   - RGB/mask/YOLO/metadata structural checks should remain mandatory.

4. Mask/RGB alignment still needs stricter review.
   - Quality checks now include mask foreground statistics and RGB defect-bbox visibility, but visual overlays are still necessary.

5. Reference/specialized co-occurrence is not fully persistent-batch optimized.
   - Generic co-occurrence is available.
   - Mixed backend combinations should stay on old scripts until a target-specific adapter exists.
   - `ql3_1052_black` co-occurrence is explicitly out of scope for the current dataset plan.

6. Metrics are useful but not final proof of realism.
   - Current image/defect metrics can support comparison and tuning.
   - They should not replace manual review, especially for faint defects and ambiguous real labels.

## Real Dataset and Labeling State

Real dataset root:

```text
E:\BlenderProject\BlenderProc\塑料工件真实数据集
```

User's labeling policy:

- Real images are being manually sorted by model/color/defect type.
- Normal images are kept separately.
- Visible defects should receive coarse L1 boxes.
- Images with original image but no red-box/manual annotation are considered low-confidence samples.
- Ambiguous or incomplete defects may be marked/handled as:
  - `visibility=ambiguous`
  - `coverage=partial`
  - `confidence=low`

Existing reference script to study:

```text
examples/my_project/prepare_qc71336_real_labels_from_manual_bbox.py
```

Do not assume every real defect can be perfectly labeled. Some defects are faint, partial, or ambiguous even to humans.

## Evaluation Tools

Existing tools:

```text
defect_dataset_generator/tools/evaluate_synthetic_image_quality.py
defect_dataset_generator/tools/evaluate_defect_realism.py
defect_dataset_generator/tools/validate_smoke_pair.py
defect_dataset_generator/tools/validate_defect_plans.py
defect_dataset_generator/tools/audit_yolo_dataset_labels.py
```

Use these before detector training. YOLO is not the primary tuning metric at this stage.

Recommended evaluation order:

1. Structural validation:
   - RGB exists and is nonblank.
   - Mask exists and foreground is nonempty for defect images.
   - YOLO labels exist where expected.
   - Metadata records target, defects, side, seed, camera, light, material profile, and output paths.

2. RGB/mask/label overlay review:
   - Confirm the defect is actually on the model.
   - Confirm the mask aligns with visible RGB defect.
   - Confirm the label is roughly around the visible defect.

3. Image-quality metrics:
   - exposure/brightness;
   - contrast;
   - background/model visibility;
   - blur/noise/texture statistics;
   - real-vs-synthetic distribution comparison per target/color.

4. Defect-realism metrics:
   - bbox/mask size distribution;
   - local contrast;
   - color delta;
   - shape/elongation;
   - edge softness;
   - defect position distribution.

## Recommended Next Steps

### Step 1: Run small persistent generic smoke

Run one or two 20-30 image batches before the full 400-500 plan:

- `qc7_5244_black` persistent generic batch;
- `ql3_1052_black` persistent generic batch, single defects only, front/side only; do not include QL3 co-occurrence.

Check RGB/mask/YOLO/metadata and contact sheets.

### Step 2: Run reference black-dot speed smoke

Run 10-20 images for:

- `p101040_blue black_dot`;
- `qc71336_gray black_dot`;
- `qc71336_white black_dot`;
- `qc7_5244_white black_dot`.

Confirm the batch path still preserves original visual behavior.

### Step 3: Rebuild the 400-500 rehearsal plan

Use:

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\tools\run_rehearsal_generation_plan.py --out defect_dataset_generator\outputs\dataset\rehearsal_500_YYYYMMDD --samples 16 --plan-only
```

Then run a dry-run or limited block subset. If suspicious, compare with:

```powershell
--no-persistent-generic
```

### Step 4: Full 400-500 generation

Only after small smoke passes, run the 400-500 set. Make sure GPU rendering is used. Store logs and plan JSONs.

### Step 5: Evaluate and produce optimization table

For every target + defect:

- pass/fail structural validation;
- visual review notes;
- image quality metric summary;
- defect realism metric summary;
- next parameter action.

Do not do broad parameter rewrites. Apply small, target-specific fixes.

## Commands Worth Keeping

List targets:

```powershell
cd E:\BlenderProject\BlenderProc
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py list-targets
```

Validate plans:

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\tools\validate_defect_plans.py
```

Example single target generation:

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target --target qc7_5244_black --defects black_dot --count 10 --samples 16 --seed 5501 --out defect_dataset_generator\outputs\dataset\smoke_qc7_5244_black_blackdot_YYYYMMDD
```

Example persistent generic batch dry-run:

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\app.py generate-target-persistent-batch --target qc7_5244_black --plan defect_dataset_generator\outputs\dataset\_planonly_rehearsal_persistent_opt\_persistent_batch_plans\qc7_5244_black__side_front.json --out defect_dataset_generator\outputs\dataset\_dryrun_persistent_qc7_front --samples 4 --dry-run
```

Example rehearsal plan:

```powershell
D:\Anaconda\envs\defect_eval\python.exe defect_dataset_generator\tools\run_rehearsal_generation_plan.py --out defect_dataset_generator\outputs\dataset\rehearsal_500_YYYYMMDD --samples 16 --plan-only
```

## Do Not Do Next

- Do not launch the 3k-5k batch before the 400-500 pilot passes checks.
- Do not optimize by replacing reference/specialized backends with generic generation.
- Do not reintroduce `sink_mark`.
- Do not treat `QC75244_white` as a separate physical target; it is a historical backend key.
- Do not assume backside samples are correct until RGB/mask overlay review confirms them.
- Do not use YOLO training as the main quality proof at this stage.
