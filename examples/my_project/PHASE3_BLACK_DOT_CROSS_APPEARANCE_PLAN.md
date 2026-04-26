# Phase 3 Black Dot Cross-Appearance Plan

This document is planning only.
It does not modify formal rendering code.

---

## 1. Goal

Keep the current embedded `black_dot` route as the canonical foundation, then expand it into a cross-appearance defect plan that can support:

- `p101040_blue_profile`
- `qc7_8578_black_profile`
- `qc7_1336_gray_profile`
- `qc8_8511_white_profile`
- `moxing1_white_profile`
- `moxing1_black_profile`

without collapsing into:

- decal-like dots
- surface dirt dots
- oversized opaque blobs
- generic particle patches that should belong to `foreign_material`

---

## 2. Current Foundation

The current strongest prototype line is:

- embedded irregular `black_dot`
- main defect body separated from support patch
- mask derived from the main defect body
- patch treated as support artifact, not the primary label

This should remain the canonical design policy.

What changes across appearance profiles should be:

- visibility strategy
- embedded depth and coupling behavior
- center / edge / patch relationship
- local brightness / roughness / halo strategy

What should not change:

- `black_dot` stays an embedded/internal class
- the main label should track the main visible defect body
- the support patch should remain secondary

---

## 3. Core Class Definition

### 3.1 Positive definition

`black_dot` should read as:

- a compact dark embedded particle
- a small internal defect body
- localized internal abnormality
- not merely painted on top of the surface

### 3.2 Negative definition

It should not read as:

- a surface sticker
- an ink mark
- a splash
- a broad dirty patch
- a free-surface flake that belongs to `foreign_material`

---

## 4. Parameter Split

The cross-appearance plan should split parameters into:

1. geometry-related parameters
2. appearance-related parameters
3. black-dot-specific override parameters

### 4.1 Geometry-related parameters

These should depend mainly on `geometry_profile`:

- valid placement zones
- zone weighting
- edge margin
- hole margin
- acceptable local surface orientation
- local scale reference
- preferred defect families by zone

### 4.2 Appearance-related parameters

These should depend mainly on `appearance_profile`:

- center darkness strategy
- edge visibility strategy
- required local contrast
- coupling patch strength
- roughness drift range
- transmission / translucency dependence
- halo allowance

### 4.3 Defect-specific parameters

These belong specifically to `black_dot`:

- radius scale
- embedded depth
- core irregularity
- edge softness
- coupling patch radius
- coupling patch alpha
- local material response strength

---

## 5. Geometry Applicability

### 5.1 `p101040_geometry`

Most suitable zones:

- `center_plane`
- controlled `slope_band`

Important notes:

- semi-translucent blue plastic makes embedded behavior believable
- edge transmission can easily overpower small defect visibility
- `black_dot` should stay compact and internal

### 5.2 `qc7_1336_geometry`

Most suitable zones:

- broad matte planes
- visually calm zones

Important notes:

- cannot rely on transmission cues
- visibility must come more from brightness / roughness / edge response

### 5.3 `moxing1_geometry`

Most suitable zones:

- broad central faces
- restrained low-structure areas

Important notes:

- this line is useful for opaque tuning references
- black and white variants should diverge strongly in visibility strategy

---

## 6. Appearance-Specific Behavior

### 6.1 Shared family rule

`black_dot` belongs to:

- `embedded_internal`

The shared invariants are:

- compact central body
- embedded or coupled-to-material visual logic
- support patch, if used, remains weaker than the core

### 6.2 `p101040_blue_profile`

Recommended expression:

- embedded irregular particle
- weak local coupling patch
- transmission-aware visibility
- subtle center/edge layering

Recommended cues:

- internal darkness
- mild coupling patch
- slight local transmission damping

Risks:

- looks like decal if too flat
- looks like dirt if patch dominates
- disappears if too deep or too soft

### 6.3 `qc8_8511_white_profile`

Recommended expression:

- compact dark point
- very restrained support patch
- easy contrast, so avoid oversizing

Recommended cues:

- central darkness can be stronger
- halo/coupling patch should stay weak

Risks:

- becomes too obvious too quickly
- can drift toward `foreign_material_particle`

### 6.4 `qc7_1336_gray_profile`

Recommended expression:

- neutral calibration target
- balanced center darkness and edge response
- moderate support patch

Recommended cues:

- center darkness
- local roughness response
- slight brightness halo if needed

### 6.5 `qc7_8578_black_profile`

Recommended expression:

- cannot rely only on deeper black
- must use local brightness / roughness / sheen difference
- support patch may matter more than on white parts

Recommended cues:

- roughness drift
- weak brightness lift around the embedded core
- mild edge response

Risks:

- disappears if only darkness is used
- becomes fake if halo is too strong

### 6.6 `moxing1_white_profile`

Recommended expression:

- similar to white opaque family
- compact dark point
- low support patch

### 6.7 `moxing1_black_profile`

Recommended expression:

- similar to black opaque family
- more reliance on local material response

---

## 7. Recommended Parameter Schema

```yaml
defect_type: black_dot
defect_family: embedded_internal
geometry_profile: p101040_geometry
appearance_profile: p101040_blue_profile
placement:
  allowed_zones:
    - center_plane
    - slope_band
  zone_weights:
    center_plane: 0.78
    slope_band: 0.22
  min_edge_margin_norm: 0.08
  min_hole_margin_norm: 0.06
shape:
  radius_scale_range: [0.003, 0.006]
  irregularity_range: [medium, high]
  embedded_depth_range: [shallow, medium]
appearance:
  core_darkness_strategy: transmission_aware
  center_alpha_range: [0.70, 0.95]
  edge_alpha_range: [0.08, 0.24]
  edge_level_ratio_range: [1.05, 1.55]
  local_patch_enabled: true
  local_patch_radius_scale_range: [1.1, 1.8]
  local_patch_alpha_range: [0.01, 0.08]
  roughness_add_range: [0.01, 0.08]
  transmission_shift_range: [-0.05, 0.00]
label_policy:
  mask_mode: main_core_only
  support_patch_excluded: true
risks:
  - too embedded becomes unreadable
  - too shallow becomes decal-like
  - too much patch becomes contamination-like
```

---

## 8. Appearance Guidance Table

| Appearance profile | Main visibility cue | Core size tendency | Patch tendency | Primary risk |
|---|---|---|---|---|
| `p101040_blue_profile` | embedded darkness + transmission damping | small to medium | weak | disappears or becomes dirty patch |
| `qc8_8511_white_profile` | dark contrast | small | very weak | too obvious / too large |
| `qc7_1336_gray_profile` | balanced darkness + roughness cue | small to medium | weak to medium | generic dark speck |
| `qc7_8578_black_profile` | roughness + brightness / sheen cue | small | medium | vanishes if only darkened |
| `moxing1_white_profile` | dark contrast | small | weak | drifts toward debris |
| `moxing1_black_profile` | roughness + brightness cue | small | medium | drifts toward artificial halo |

---

## 9. Boundary Rules Against Nearby Classes

### 9.1 vs `foreign_material`

`black_dot`:

- more embedded
- more internal
- more compact core identity

`foreign_material`:

- more object-like
- may sit nearer the surface
- may be flake/fiber-like

### 9.2 vs `mixed_color_contamination`

`black_dot`:

- nucleus-driven
- compact central body

`mixed_color_contamination`:

- patch-driven
- no compact dark core required

### 9.3 vs `surface_contamination`

`black_dot`:

- embedded point defect

`surface_contamination`:

- stain / dirt / grime reading

### 9.4 support patch rule

The support patch around some `black_dot` variants:

- is a support artifact
- is not a training class
- should not dominate the annotation

---

## 10. Candidate Implementation Strategies

### Strategy A: current canonical route

Use:

- irregular embedded particle core
- weak local coupling patch
- main-core-only mask

Pros:

- already validated on `P101040`
- class semantics are clear

Risks:

- may become too subtle
- may need profile-specific visibility tuning

### Strategy B: opaque-profile adaptation

Use:

- same core logic
- weaker transmission dependence
- stronger local material response

Pros:

- preserves shared class identity

Risks:

- black opaque variants may collapse unless brightness/roughness support is tuned carefully

### Recommended order

Keep one shared canonical route, then tune by appearance override.

Do not create completely separate `black_dot` families per product line.

---

## 11. Validation Requirements

Before implementation is accepted, it should satisfy:

1. still reads as embedded/internal
2. main label follows the core, not the support patch
3. remains visually distinct from `foreign_material`
4. remains plausible on both opaque and semi-translucent profiles
5. does not depend on a single lighting/view setup

### 11.1 Review checklist

- compact core is readable
- embedded feel survives
- support patch stays secondary
- no decal-like edge
- no oversized dirty halo

---

## 12. Planned Deliverables For The Next Step

The next planning step should produce:

1. a cross-appearance parameter table
2. a geometry-zone recommendation table
3. a list of current reusable black-dot functions
4. a list of parameters that should move into appearance overrides
5. a risk matrix comparing:
   - `black_dot`
   - `foreign_material`
   - `mixed_color_contamination`

---

## 13. Bottom Line

`black_dot` should not be redesigned from scratch.

It already has a usable canonical route.

The real next step is:

- preserve the embedded/internal class identity
- move visibility behavior into appearance-aware overrides
- keep the core/patch label boundary stable across all appearance profiles
