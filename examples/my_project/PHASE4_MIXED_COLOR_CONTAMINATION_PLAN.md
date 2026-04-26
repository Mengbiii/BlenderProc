# Phase 4 Mixed Color Contamination Plan

This document is planning only.
It does not modify formal rendering code.

---

## 1. Goal

Split `mixed_color_contamination` away from the old broad `contamination` bucket and define it as:

- local hue drift
- local value drift
- soft-edge material color contamination
- subtle molded-material inconsistency

It should **not** read as:

- dirt patch
- splash mark
- foreign debris
- embedded black particle

---

## 2. Visual Definition

### 2.1 Positive definition

`mixed_color_contamination` should look like:

- a local region where the material color has drifted
- a soft transition rather than a hard boundary
- low-to-moderate contrast against the base plastic
- a defect that still feels like the same material family

### 2.2 Negative definition

It should not look like:

- a decal
- a sticker
- a dirty stain
- a paint splatter
- a particle
- a black dot with a large halo

---

## 3. Asset References

Primary reference assets from `moxing1_test.blend`:

1. `Plane.003 + gradient`
   - strongest reference for soft color drift logic
2. `Plane.002 + Material.003`
   - useful reference for restrained local abnormality language
   - should be borrowed carefully so it does not drift into `surface_contamination`

Real-image reference direction:

- white / gray opaque parts:
  - local warm/cool drift
  - slight gray/cream contamination
- blue semi-translucent parts:
  - very restrained smoky blue / gray-blue / haze-like local drift

---

## 4. Geometry Applicability

### 4.1 `p101040_geometry`

Most suitable zones:

- `center_plane`
- broad transition zones between `center_plane` and `slope_band`

Use carefully on:

- `slope_band`

Avoid:

- very thin edge zones
- hole-adjacent microstructure
- outer transmission-heavy edges where the defect may read as a lighting artifact

### 4.2 `qc7_1336_geometry`

Most suitable zones:

- broad main planes
- visually calm matte zones

Use carefully on:

- local ridge transitions

### 4.3 `moxing1_geometry`

Most suitable zones:

- center broad face
- low-structure areas with stable shading

Use as:

- first reference implementation source
- not necessarily the first production training line

---

## 5. Appearance-Specific Behavior

### 5.1 Shared family rule

`mixed_color_contamination` is a `surface_material_shift` defect family.

That means its primary cues are:

- hue drift
- value drift
- slight roughness drift
- optional weak micro-brightness drift

It should not require:

- a hard alpha edge
- a raised particle body
- a separate object silhouette

### 5.2 `opaque_matte_satin_plastic`

Recommended expression:

- color drift can be a little more visible
- roughness drift can help
- edge softness should remain high

Suggested visual language:

- gray shift
- cream shift
- weak cool/warm contamination

### 5.3 `semi_translucent_blue_plastic`

Recommended expression:

- more restrained than opaque parts
- lean toward smoky blue / gray-blue / haze-like local drift
- very weak roughness shift
- avoid looking like grime

Suggested visual language:

- soft desaturation
- slight transmission damping
- weak haze drift

---

## 6. Proposed Parameter Layers

The parameter model should be split into:

1. geometry-related parameters
2. appearance-related parameters
3. per-defect override parameters

### 6.1 Geometry-related parameters

These should depend mainly on `geometry_profile`:

- allowed zones
- zone weights
- minimum distance from edges
- minimum distance from holes / cutouts
- patch aspect-ratio freedom
- allowed orientation range

### 6.2 Appearance-related parameters

These should depend mainly on `appearance_profile`:

- hue shift range
- value shift range
- saturation shift range
- alpha softness
- roughness drift range
- transmission damping allowance
- micro-noise amplitude

### 6.3 Defect-specific override parameters

These should belong specifically to `mixed_color_contamination`:

- patch family
  - `elliptic_soft`
  - `flow_soft`
  - `cloud_soft`
- edge falloff exponent
- center-to-edge contrast ratio
- internal noise strength
- optional directional bias

---

## 7. Recommended Parameter Schema

```yaml
defect_type: mixed_color_contamination
defect_family: surface_material_shift
geometry_profile: p101040_geometry
appearance_profile: p101040_blue_profile
placement:
  allowed_zones:
    - center_plane
    - center_to_slope_transition
  zone_weights:
    center_plane: 0.75
    center_to_slope_transition: 0.25
  min_edge_margin_norm: 0.08
  min_hole_margin_norm: 0.06
shape:
  patch_family: elliptic_soft
  radius_scale_range: [0.035, 0.090]
  aspect_ratio_range: [0.7, 1.5]
  rotation_free: true
appearance:
  hue_shift_range: [-0.02, 0.03]
  value_shift_range: [-0.05, 0.04]
  saturation_shift_range: [-0.10, 0.06]
  edge_alpha_range: [0.08, 0.22]
  center_alpha_range: [0.12, 0.28]
  roughness_add_range: [0.01, 0.05]
  transmission_shift_range: [-0.03, 0.00]
  micro_noise_strength_range: [0.002, 0.010]
label_policy:
  mask_mode: main_patch_only
  support_artifacts_excluded: true
risks:
  - may drift toward surface_contamination if value shift is too dark
  - may drift toward decal-like patch if edge falloff is too sharp
```

---

## 8. Appearance Recommendations By Profile

### 8.1 `moxing1_white_profile`

Recommended:

- warm-gray to cool-gray drift
- soft value shift
- very low saturation influence

Avoid:

- dirty brown stains
- hard local edges

### 8.2 `moxing1_black_profile`

Recommended:

- weak gray fog
- slightly cooler or warmer sheen drift
- roughness drift may matter more than hue drift

Avoid:

- relying only on darkness
- making it look like dust

### 8.3 `qc7_1336_gray_profile`

Recommended:

- use as a neutral calibration profile
- balanced value drift
- moderate roughness shift

### 8.4 `qc8_8511_white_profile`

Recommended:

- subtle cream/gray contamination
- very soft spread

Risk:

- easy to drift into visible dirt patch

### 8.5 `qc7_8578_black_profile`

Recommended:

- weak gray or low-sheen tone drift
- rely on slight roughness and brightness cues

Risk:

- too low contrast becomes invisible
- too high contrast becomes fake stain

### 8.6 `p101040_blue_profile`

Recommended:

- smoky blue / gray-blue / lightly desaturated local drift
- very soft boundary
- optional slight transmission damping

Risk:

- too much value drop becomes grime
- too much saturation change becomes fake painted patch

---

## 9. Boundary Rules Against Nearby Classes

### 9.1 vs `surface_contamination`

`mixed_color_contamination`:

- same material family feel
- softer and more internal-looking
- less dirty

`surface_contamination`:

- dirt / grime / stain reading
- stronger patch identity
- more likely to feel surface-borne

### 9.2 vs `foreign_material`

`mixed_color_contamination`:

- no discrete particle body
- no flake / fiber silhouette
- reads as material shift

`foreign_material`:

- discrete matter or local matter cluster
- may have sharper or object-like identity

### 9.3 vs `black_dot`

`mixed_color_contamination`:

- broader, softer, lower-contrast region
- no dense dark nucleus required

`black_dot`:

- compact main body
- embedded dark particle core

### 9.4 vs `splay`

`mixed_color_contamination`:

- local region
- no strong directional flow logic required

`splay`:

- directional / streak-like
- flow-linked expression required

---

## 10. Candidate Implementation Strategies

These are planning options only.

### Strategy A: patch-material route

Use:

- soft patch mask
- hue/value/roughness drift inside the patch

Pros:

- easy to parameterize
- easy to label

Risks:

- can look decal-like if edge softness is not handled carefully

### Strategy B: surface-response route

Use:

- local color drift
- weak roughness drift
- almost no explicit alpha patch boundary

Pros:

- more native-material feeling

Risks:

- may become too subtle or unstable under lighting changes

### Recommended order

Start with a hybrid:

- material-shift patch with very soft edge
- weak roughness drift
- optional micro-noise

This is the best compromise between:

- controllability
- label clarity
- realism

---

## 11. Validation Requirements

Before implementation is considered acceptable, it should satisfy:

1. does not look like dirt
2. does not look like a sticker
3. does not rely on a hard alpha boundary
4. still reads under more than one lighting state
5. can be labeled as a coherent region
6. remains distinct from `foreign_material`

### 11.1 Review checklist

- shape feels soft, not object-like
- boundary remains low-contrast
- center is not overly dark
- patch is not too large for the geometry zone
- does not collapse into near invisibility on dark profiles

---

## 12. Planned Deliverables For The Next Step

The next planning step should produce:

1. a parameter table by appearance profile
2. a zone recommendation table by geometry profile
3. a first implementation touchpoint list
4. a label-policy note for task-eval compatibility
5. a short risk matrix comparing:
   - `mixed_color_contamination`
   - `surface_contamination`
   - `foreign_material`

---

## 13. Bottom Line

`mixed_color_contamination` should become the first class split out of the old broad `contamination` bucket.

It is the best first target because:

- it already has visual reference assets
- it fits all three geometry lines
- it benefits strongly from the new geometry / appearance / defect schema
- it forces the category boundary to become cleaner for the rest of the roadmap
