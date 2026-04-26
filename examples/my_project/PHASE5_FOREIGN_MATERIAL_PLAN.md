# Phase 5 Foreign Material Plan

This document is planning only.
It does not modify formal rendering code.

---

## 1. Goal

Split `foreign_material` into a clear independent defect line that is distinct from:

- `black_dot`
- `mixed_color_contamination`
- `surface_contamination`

`foreign_material` should represent:

- a particle
- a flake
- a small chip
- a small fiber-like or debris-like inclusion / attachment

depending on geometry line and appearance profile.

---

## 2. Visual Definition

### 2.1 Positive definition

`foreign_material` should read as:

- discrete matter
- localized non-native material
- a small object-like or clump-like abnormality
- visually separate enough to feel like foreign debris

### 2.2 Negative definition

It should not read as:

- a pure internal dark point with no matter identity
- a soft color drift patch
- a dirt stain spread over a broad area
- a spray-paint splatter

---

## 3. Internal Subfamilies

For planning purposes, `foreign_material` should be treated as two subfamilies:

1. `foreign_material_particle`
   - compact particle
   - small speck / chip / bead / crumb
2. `foreign_material_fiber_or_flake`
   - thin flake
   - short fiber
   - elongated micro-fragment

These should stay under one public class at first,
but the subfamily distinction should exist in metadata and parameter design.

---

## 4. Asset References

Primary `.blend` inspiration:

- `Plane.001 + Material.002`

This should be treated as:

- reference for local object-like contamination language
- not a template to copy literally

What must be removed from the reference look:

- splash feel
- spray feel
- exaggerated radial scatter feel

What should be kept:

- object-like locality
- visible discrete foreign-body identity
- ability to separate mask cleanly

---

## 5. Geometry Applicability

### 5.1 `p101040_geometry`

Best candidate zones:

- `center_plane`
- `slope_band` in controlled cases

Use with caution:

- high-transmission edge zones
- narrow outer structures

Reason:

- foreign material on `P101040` must avoid turning into a surface sticker or decal
- on semi-translucent blue plastic, it should still feel coupled to the object, not pasted on

### 5.2 `qc7_1336_geometry`

Best candidate zones:

- broad matte planes
- moderate-visibility structure zones

More freedom than on `P101040`:

- opaque surface makes particle-like foreign material easier to sell visually

### 5.3 `moxing1_geometry`

Best candidate zones:

- broad central regions
- lightly structured surface bands

Recommended use:

- early prototype source for patch/object hybrid language
- especially strong reference line for white and black opaque parts

---

## 6. Appearance-Specific Behavior

### 6.1 Shared family rule

`foreign_material` belongs to:

- `surface_foreign_object`

Main cues:

- discrete object identity
- edge contrast or specular mismatch
- slight local coupling with the base material

### 6.2 `opaque_matte_satin_plastic`

Recommended expression:

- particle can sit closer to the surface visually
- contrast can rely on brightness, color shift, roughness mismatch
- may allow slightly clearer silhouette than `P101040`

White profile suggestions:

- gray-brown, tan, dark speck, gray chip

Gray profile suggestions:

- dark gray, brown-gray, slightly reflective micro debris

Black profile suggestions:

- light gray, off-white, pale flake, slightly reflective debris

### 6.3 `semi_translucent_blue_plastic`

Recommended expression:

- smaller and more restrained than on opaque parts
- should avoid looking like a pasted stain
- may use local coupling or weak sub-surface interaction cues

Good candidates:

- dark speck
- pale chip
- grayish micro fragment

Avoid:

- flat black sticker look
- high-opacity decal feel

---

## 7. Proposed Parameter Layers

The parameter system should be split into:

1. geometry placement parameters
2. appearance behavior parameters
3. defect-specific object/patch parameters

### 7.1 Geometry-related parameters

- allowed zones
- zone weights
- edge margin
- hole margin
- maximum tilt / normal deviation
- allowed aspect range

### 7.2 Appearance-related parameters

- brightness offset range
- hue bias options
- roughness mismatch range
- specular mismatch range
- translucency / transmission coupling allowance
- halo allowance

### 7.3 Defect-specific parameters

- subfamily
  - `particle`
  - `fiber_or_flake`
- size range
- elongation range
- silhouette irregularity range
- edge softness range
- local coupling patch enable / disable
- local coupling patch strength

---

## 8. Recommended Parameter Schema

```yaml
defect_type: foreign_material
defect_family: surface_foreign_object
geometry_profile: qc7_1336_geometry
appearance_profile: qc8_8511_white_profile
placement:
  allowed_zones:
    - broad_main_plane
    - moderate_structure_zone
  zone_weights:
    broad_main_plane: 0.7
    moderate_structure_zone: 0.3
  min_edge_margin_norm: 0.06
  min_hole_margin_norm: 0.05
shape:
  subfamily_weights:
    particle: 0.7
    fiber_or_flake: 0.3
  size_scale_range: [0.004, 0.016]
  aspect_ratio_range: [0.6, 3.5]
  silhouette_irregularity_range: [low, medium_high]
appearance:
  brightness_shift_range: [-0.30, 0.25]
  hue_family:
    - gray
    - tan
    - brown_gray
  roughness_add_range: [0.00, 0.08]
  specular_add_range: [0.00, 0.06]
  edge_alpha_range: [0.18, 0.60]
  local_coupling_patch:
    enabled: true
    alpha_range: [0.02, 0.10]
    radius_scale_range: [1.1, 1.8]
label_policy:
  mask_mode: main_object_only
  coupling_patch_excluded: true
risks:
  - may drift toward splash if many fragments are grouped
  - may drift toward black_dot if too compact and too embedded
  - may drift toward contamination if patch dominates the object
```

---

## 9. Appearance Recommendations By Profile

### 9.1 `moxing1_white_profile`

Recommended:

- gray or light brown particle
- occasional thin flake
- modest silhouette clarity

Avoid:

- dirty stain look
- too many clustered specks

### 9.2 `moxing1_black_profile`

Recommended:

- light gray or pale flake
- slightly reflective micro debris

Avoid:

- dark particle with no contrast
- high-opacity painted blob

### 9.3 `qc7_1336_gray_profile`

Recommended:

- balanced neutral particles
- good calibration profile for early tuning

### 9.4 `qc8_8511_white_profile`

Recommended:

- strongest candidate for initial realism checks
- many foreign-material colors can be visually plausible here

Risk:

- easy to overstate and create obvious dirt/stain semantics

### 9.5 `qc7_8578_black_profile`

Recommended:

- prioritize lighter debris
- use reflectance mismatch as an extra cue

Risk:

- dark debris disappears
- overcompensation creates fake bright sticker-like particles

### 9.6 `p101040_blue_profile`

Recommended:

- very small restrained particle or flake
- optional weak coupling patch
- avoid hard-edged high-opacity look

Risk:

- quickly collapses into `black_dot`
- quickly looks like pasted decal if too flat

---

## 10. Boundary Rules Against Nearby Classes

### 10.1 vs `black_dot`

`foreign_material`:

- object-like
- can be more surface-near
- can be non-black and non-circular
- can have flake or fiber identity

`black_dot`:

- embedded internal dark point
- compact nucleus
- more internal than object-like

### 10.2 vs `mixed_color_contamination`

`foreign_material`:

- discrete object or clump
- sharper semantic identity

`mixed_color_contamination`:

- no discrete object
- material drift only

### 10.3 vs `surface_contamination`

`foreign_material`:

- one object or a small object-like cluster
- bounded identity

`surface_contamination`:

- stain / grime / broader surface patch

### 10.4 vs `black_dot_coupling_patch`

The coupling patch used around some `black_dot` variants:

- is not a foreign-material class
- must remain secondary support only

---

## 11. Candidate Implementation Strategies

### Strategy A: single-object dominant

Use:

- one main particle / flake object
- optional weak coupling patch

Pros:

- clean label
- easiest class boundary

Risks:

- can become too synthetic if the silhouette is oversimplified

### Strategy B: object + surface-response hybrid

Use:

- one object-like defect body
- plus slight local material disturbance

Pros:

- stronger realism
- especially useful for `P101040`

Risks:

- support patch can overgrow and contaminate class definition

### Recommended order

Start with Strategy B, but constrain it:

- one primary object-like body
- one weak local coupling response
- no clusters
- no splash patterns

---

## 12. Validation Requirements

Before implementation is accepted, it should satisfy:

1. reads as discrete foreign matter
2. does not read as spray or splatter
3. does not collapse into `black_dot`
4. mask can isolate the main object cleanly
5. support patch does not dominate the annotation
6. remains plausible under more than one appearance profile

### 12.1 Review checklist

- object identity is present
- object count remains controlled
- silhouette is not too perfect
- patch is secondary
- color/material mismatch is plausible

---

## 13. Planned Deliverables For The Next Step

The next planning step should produce:

1. a parameter table by appearance profile
2. a subfamily guide:
   - `particle`
   - `fiber_or_flake`
3. a geometry placement guide
4. a label-policy note for task-eval compatibility
5. a risk matrix comparing:
   - `foreign_material`
   - `black_dot`
   - `mixed_color_contamination`

---

## 14. Bottom Line

`foreign_material` should become the second major class split out of the old broad `contamination` bucket.

It is worth doing early because:

- it has strong visual distinction from `mixed_color_contamination`
- it is important on opaque black / white / gray products
- it forces a clean boundary against `black_dot`
- it benefits directly from the new geometry / appearance / defect schema
