# P101040 / QC7-1336 / moxing1 Phase 2 + Phase 7 Schema Draft

This document is a planning artifact only.
It does not change the current rendering or training code.

---

## 1. Purpose

This draft defines a shared structure for:

1. `geometry profile`
2. `appearance profile`
3. `defect override layer`

The goal is not to make every product look the same.
The goal is to let different product lines reuse defect logic while preserving the real differences between:

- opaque matte-satin injection plastics
- blue semi-translucent injection plastics

---

## 2. Core Principles

### 2.1 Three-layer split

All future defect generation should be described by:

1. `geometry_profile`
   - where defects can appear
   - what geometric constraints apply
   - what spatial zones matter

2. `appearance_profile`
   - how the material family looks
   - how defects tend to appear on that material
   - what kinds of visibility cues are strong or weak

3. `defect_override`
   - per-defect adjustments for a given geometry + appearance pair
   - used when one defect behaves differently across materials

### 2.2 Shared defect semantics

Current mainline defect classes:

- `black_dot`
- `mixed_color_contamination`
- `foreign_material`
- `splay`

Secondary / non-mainline classes:

- `surface_contamination`
- `sink_mark`
- `scratch`
- `scuff_mark`

### 2.3 Material-family split must stay explicit

Two material families must remain first-class:

1. `opaque_matte_satin_plastic`
2. `semi_translucent_blue_plastic`

Do not flatten these into one generic "plastic" profile.

---

## 3. Geometry Profiles

### 3.1 `p101040_geometry`

Primary object line:

- `P101040`

Material family:

- `semi_translucent_blue_plastic`

Expected visible zones:

- `center_plane`
- `slope_band`
- `outer_band`
- optional structure zones around edges / holes

Main geometry notes:

- edge transmission is visually important
- defect readability depends on local transmission / haze / roughness
- center-plane defects and slope-band defects may require different visibility tuning

Recommended placement notes:

- `black_dot`: center-plane first, slope-band optional
- `mixed_color_contamination`: subtle center-plane or transition zones
- `foreign_material`: constrained, avoid looking like surface stickers
- `splay`: highly relevant on broad visible faces with directional flow cues

### 3.2 `qc7_1336_geometry`

Primary object line:

- `QC7-1336.stl`

Material family:

- `opaque_matte_satin_plastic`

Expected visible zones:

- broad main planes
- frame / ridge / local structure zones

Main geometry notes:

- visibility is driven more by brightness, hue drift, roughness drift, microtexture contrast
- transmission is not a primary cue

Recommended placement notes:

- `black_dot`: still possible, but cannot rely on transmission
- `mixed_color_contamination`: very suitable on broad flat regions
- `foreign_material`: strong candidate
- `splay`: useful if directional flow fields can be defined

### 3.3 `moxing1_geometry`

Primary object line:

- `moxing1_test.blend`

Material family:

- `opaque_matte_satin_plastic`

Current role:

- defect/material asset reference line
- not yet the most validated training-data mainline

Expected visible zones:

- center broad face
- border structure zones
- local textured zones

Recommended use:

- reference source for `mixed_color_contamination`
- reference source for `foreign_material`
- reference source for low-contrast surface abnormality language

---

## 4. Appearance Profiles

Each appearance profile should be defined by a shared schema.

### 4.1 Required fields

Each appearance profile should describe:

- `profile_name`
- `geometry_profile`
- `material_family`
- `base_color_family`
- `opacity_family`
- `roughness_family`
- `specular_family`
- `transmission_or_translucency_behavior`
- `micro_texture_behavior`
- `defect_visibility_notes`
- `preferred_defects`
- `risky_defects`

### 4.2 Suggested shape

```yaml
profile_name: p101040_blue_profile
geometry_profile: p101040_geometry
material_family: semi_translucent_blue_plastic
base_color_family:
  - cool blue
  - pale blue
  - smoky blue
opacity_family: semi_translucent
roughness_family:
  default_range: [medium_low, medium]
  notes: "center plane slightly smoother than diffuse matte opaque parts"
specular_family:
  default_range: [medium, medium_high]
transmission_or_translucency_behavior:
  enabled: true
  edge_transmission: strong
  center_transmission: moderate
micro_texture_behavior:
  center_plane: fine molded texture
  slope_band: slightly stronger surface response
  outer_band: stronger edge highlight and transmission
defect_visibility_notes:
  black_dot: "small internal dark points are valid but must remain embedded"
  mixed_color_contamination: "must stay subtle and not become dirty patch"
  foreign_material: "avoid sticker-like decals"
  splay: "haze and flow-like whitening are more realistic than opaque smears"
preferred_defects:
  - black_dot
  - splay
risky_defects:
  - foreign_material
```

---

## 5. Current Appearance Profile List

### 5.1 `p101040_geometry`

#### `p101040_blue_profile`

- material family: `semi_translucent_blue_plastic`
- status: primary real reference
- key traits:
  - edge transmission
  - strong highlight structure
  - blue hue varies with environment
  - defects are sensitive to haze / roughness / embedded feel

#### Reserved only

- `p101040_black_profile`
- `p101040_white_profile`

These remain placeholders unless stronger real-image support arrives.

### 5.2 `qc7_1336_geometry`

#### `qc7_8578_black_profile`

- material family: `opaque_matte_satin_plastic`
- key traits:
  - black body weakens dark-dot contrast
  - defects must often rely on roughness / brightness / halo, not just darkness

#### `qc7_1336_gray_profile`

- material family: `opaque_matte_satin_plastic`
- key traits:
  - likely the best neutral calibration surface for many defect classes

#### `qc8_8511_white_profile`

- material family: `opaque_matte_satin_plastic`
- key traits:
  - high visibility for dark particles
  - easy to overdo contamination and make it too dirty

### 5.3 `moxing1_geometry`

#### `moxing1_white_profile`

- material family: `opaque_matte_satin_plastic`
- key traits:
  - white/cream matte molded plastic
  - good for contamination and color-shift studies

#### `moxing1_black_profile`

- material family: `opaque_matte_satin_plastic`
- key traits:
  - black matte-satin molded plastic
  - useful for foreign-material contrast design

---

## 6. Defect Override Layer

### 6.1 Why it exists

The same defect class should not share identical parameters on all profiles.

Examples:

- `black_dot` on `p101040_blue_profile`
  - embedded
  - transmission-aware
  - subtle edge coupling patch

- `black_dot` on `qc7_8578_black_profile`
  - cannot rely only on deeper darkness
  - needs roughness/brightness/halo support

- `mixed_color_contamination` on `moxing1_white_profile`
  - soft hue/value drift
  - very low contrast

- `splay` on `p101040_blue_profile`
  - haze and flow-like transmission disturbance

### 6.2 Suggested override fields

Each defect override entry should support:

- `enabled`
- `placement_zones`
- `scale_family`
- `contrast_family`
- `roughness_delta_family`
- `halo_family`
- `edge_softness_family`
- `embedding_family`
- `label_policy_notes`
- `risk_notes`

### 6.3 Suggested shape

```yaml
defect_override:
  defect_type: black_dot
  geometry_profile: p101040_geometry
  appearance_profile: p101040_blue_profile
  enabled: true
  placement_zones:
    primary:
      - center_plane
    secondary:
      - slope_band
  scale_family:
    target: small_internal
    notes: "keep within realistic internal-particle range"
  contrast_family:
    target: low_to_medium
  roughness_delta_family:
    target: subtle
  halo_family:
    target: weak_local_coupling
  edge_softness_family:
    target: soft_internal
  embedding_family:
    target: embedded
  label_policy_notes:
    main_mask_only: true
    local_patch_in_mask: false
  risk_notes:
    - avoid decal-like look
    - avoid oversized opaque dirt-dot look
```

---

## 7. Phase 2 + Phase 7 Alignment

The category cleanup from Phase 2 and the profile structure from Phase 7 should line up like this:

| Main defect class | Typical material expression | Depends strongly on geometry? | Depends strongly on appearance? | Needs override layer? |
|---|---|---:|---:|---:|
| `black_dot` | embedded internal dark particle | yes | yes | yes |
| `mixed_color_contamination` | soft local hue/value drift | medium | yes | yes |
| `foreign_material` | surface or near-surface foreign speck / flake / fiber | medium | yes | yes |
| `splay` | directional haze / whitening / flow-like streak | yes | yes | yes |

### 7.1 Legacy mapping

The old project vocabulary should be translated like this:

| Legacy name | New canonical name | Meaning | Keep as public training class? |
|---|---|---|---:|
| `black_dot` | `black_dot` | embedded internal dark point | yes |
| `contamination` | `legacy_contamination` | old broad bucket, not a stable semantic class | no |
| `contamination` (soft hue drift usage) | `mixed_color_contamination` | local color drift / value drift / tone contamination | yes |
| `contamination` (particle / speck usage) | `foreign_material` | particle, flake, debris, micro speck | yes |
| `contamination` (dirty patch usage) | `surface_contamination` | surface dirt / stain / grime patch | no |
| `splay` | `splay` | flow-linked haze / whitening streak | yes |
| `sink_mark` | `sink_mark` | indentation / shrink mark | no |
| `local_contamination` around black dots | `black_dot_coupling_patch` | support artifact only, not a primary class | no |

### 7.2 Label policy implication

This alignment implies a stricter label policy:

1. the primary class label should track the main visible defect body
2. support artifacts should stay out of the class label unless explicitly promoted later
3. the same visual support artifact can exist in different classes without becoming a class itself

Examples:

- `black_dot`
  - main mask: embedded particle core
  - support artifact: weak coupling patch
- `mixed_color_contamination`
  - main mask: main soft contaminated region
  - no separate micro support layer by default
- `foreign_material`
  - main mask: foreign particle or local clump
  - optional support artifact only if clearly distinct
- `splay`
  - main mask: directional abnormality zone
  - avoid labeling only one tiny sub-spot within a longer flow streak

---

## 8. Recommended Metadata Schema

Each generated sample should eventually be able to record:

```yaml
geometry_profile: p101040_geometry
appearance_profile: p101040_blue_profile
material_family: semi_translucent_blue_plastic
render_profile: reference_scene
defect_type: black_dot
defect_family: embedded_internal
defect_override_id: p101040_blue_profile.black_dot.v1
label_policy:
  primary_mask_only: true
  support_artifacts_excluded: true
support_artifacts:
  - black_dot_coupling_patch
notes:
  visibility_risk: moderate
  training_risk: low
```

### 8.1 Suggested controlled vocabularies

`defect_family`
- `embedded_internal`
- `surface_material_shift`
- `surface_foreign_object`
- `flow_directional`
- `surface_relief_change`

`support_artifacts`
- `black_dot_coupling_patch`
- `soft_color_halo`
- `roughness_drift`
- `micro_brightness_shift`
- `none`

`material_family`
- `semi_translucent_blue_plastic`
- `opaque_matte_satin_plastic`

---

## 9. Validation Rules By Defect Type

### 9.1 `black_dot`

Should validate:

- embedded feel remains visible
- center body exists as the primary training label
- support patch does not dominate the annotation
- not decal-like
- not sticker-like

High-risk failures:

- looks like a surface ink mark
- support patch larger than the core signal
- label tracks patch instead of core

### 9.2 `mixed_color_contamination`

Should validate:

- soft local color drift is visible
- not confused with dirt or grime
- does not become a hard-edged patch
- contrast remains restrained

High-risk failures:

- looks like a stain
- too much alpha edge definition
- lighting-dependent visibility only

### 9.3 `foreign_material`

Should validate:

- reads as debris / particle / flake, not just a color patch
- can be isolated by mask without covering too much clean surface
- remains plausible on the target material family

High-risk failures:

- spray-paint look
- confusable with black_dot
- confusable with dirt patch

### 9.4 `splay`

Should validate:

- directional / flow-linked visual structure
- not just generic fog or blur
- broad enough to read as material-flow abnormality
- compatible with geometry flow fields

High-risk failures:

- random blurry patch
- mislabeled local bright spot
- no directional cue

---

## 10. File-Level Implementation Priorities

This section is still planning only.
It names likely future implementation touchpoints without changing them now.

### 10.1 First-layer schema entry points

- [E:\BlenderProject\BlenderProc\examples\my_project\generate_black_spot_multi_model.py](E:\BlenderProject\BlenderProc\examples\my_project\generate_black_spot_multi_model.py)
  - current `defect_types`
  - current class-id map
  - current broad `contamination` bucket
- [E:\BlenderProject\BlenderProc\examples\my_project\reference_blend_blue_blackdot_debug.py](E:\BlenderProject\BlenderProc\examples\my_project\reference_blend_blue_blackdot_debug.py)
  - current cleanest `black_dot` prototype line
  - current support-artifact separation logic

### 10.2 Audit and task-prep touchpoints

- [E:\BlenderProject\BlenderProc\examples\my_project\prepare_p101040_task_eval.py](E:\BlenderProject\BlenderProc\examples\my_project\prepare_p101040_task_eval.py)
- [E:\BlenderProject\BlenderProc\examples\my_project\prepare_p101040_synth_filtering_and_ablation.py](E:\BlenderProject\BlenderProc\examples\my_project\prepare_p101040_synth_filtering_and_ablation.py)
- [E:\BlenderProject\BlenderProc\examples\my_project\audit_reference_scene_50_roi_labels.py](E:\BlenderProject\BlenderProc\examples\my_project\audit_reference_scene_50_roi_labels.py)

These will need the new canonical class names once implementation starts.

---

## 11. Recommended Next Execution Order

To stay aligned with the handoff, the next steps should be:

1. finalize Phase 2 category cleanup language
2. finalize this Phase 7 schema draft
3. draft parameter-layer plans for:
   - `mixed_color_contamination`
   - `foreign_material`
   - `splay`
   - cross-appearance `black_dot`
4. only then choose which formal script to modify first

### 11.1 Suggested implementation priority

1. `mixed_color_contamination`
2. `foreign_material`
3. `splay`
4. broader `black_dot` cross-appearance calibration

Reason:

- current `black_dot` already has a usable embedded line
- current biggest semantic mess is still inside the broad old `contamination` bucket
- `mixed_color_contamination` and `foreign_material` are the highest-value split to clarify first

---

## 12. Bottom Line

This draft locks in the foundation:

- three geometry lines
- explicit appearance profiles
- four mainline defect classes
- a separate defect-override layer
- explicit support-artifact handling

The key policy decision is:

- keep `black_dot` on the embedded/internal route
- retire broad `contamination` as a formal public class
- split it into:
  - `mixed_color_contamination`
  - `foreign_material`
  - `surface_contamination` as a secondary helper class
- keep opaque and semi-translucent material families explicit in the schema

That gives us a stable base for the next planning step without touching formal code yet.
