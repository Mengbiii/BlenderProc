# Phase 6 Splay Plan

This document is planning only.
It does not modify formal rendering code.

---

## 1. Goal

Define `splay` as a directional molding-flow defect rather than a generic surface patch.

`splay` should read as:

- haze
- whitening
- grayish flow disturbance
- subtle streaking
- flow-linked material abnormality

It should **not** read as:

- dirt
- splash
- decal
- broad mixed-color patch

---

## 2. Visual Definition

### 2.1 Positive definition

`splay` should look like:

- a directional abnormality
- flow-aware lightening / haze / desaturation
- elongated or banded, not blob-like
- integrated into the molded surface

### 2.2 Negative definition

It should not look like:

- a random blurry patch
- a stain
- a sticker
- a foreign particle field
- a single compact defect core

---

## 3. Physical / Process Interpretation

For planning purposes, `splay` should be treated as a defect family linked to:

- flow direction
- local molding instability
- gas / moisture / streak-like material disturbance

That means the rendered language should favor:

- directional spread
- subtle anisotropy
- low-to-moderate contrast
- roughness / haze / transmission disturbance

and should avoid:

- discrete object silhouettes
- radial splash patterns
- circular local spots

---

## 4. Asset References

The `.blend` assets are not direct `splay` assets.
They are only useful for borrowing:

- soft edge logic
- low-contrast abnormality language
- restrained roughness drift ideas

Do not directly reuse plane-patch look as final `splay`.

Reference interpretation from real images should drive this class more than the `.blend` planes.

---

## 5. Geometry Applicability

### 5.1 `p101040_geometry`

Strong candidate for first high-quality `splay` implementation.

Best zones:

- `center_plane`
- `slope_band` with directional alignment

Reason:

- semi-translucent blue plastic can express haze / transmission disturbance naturally
- broad visible surfaces make directional flow defects believable

Use carefully on:

- narrow outer band
- edge transmission-heavy borders where the effect may collapse into highlight variation

### 5.2 `qc7_1336_geometry`

Good candidate, but the visual strategy must rely more on:

- brightness drift
- desaturation
- roughness drift

Best zones:

- broad main planes
- flow-plausible structural lanes

### 5.3 `moxing1_geometry`

Useful more as a reference line than a first implementation target.

Best use:

- deriving low-contrast abnormality language
- not direct final expression

---

## 6. Appearance-Specific Behavior

### 6.1 Shared family rule

`splay` belongs to:

- `flow_directional`

Main cues:

- directionality
- haze / whitening / desaturation
- low-contrast surface/material disturbance

### 6.2 `opaque_matte_satin_plastic`

Recommended expression:

- gray-white or pale haze drift
- weak brightness increase
- restrained roughness shift
- no strong embedded feel

Best behavior:

- slightly cloudy
- slightly washed
- elongated along a plausible flow lane

### 6.3 `semi_translucent_blue_plastic`

Recommended expression:

- transmission damping
- localized haze
- slight whitening / desaturation
- subtle streak-like disturbance

Best behavior:

- looks like the blue material has locally gone cloudy
- not like surface dirt

Risk:

- too strong becomes contamination
- too weak disappears into lighting variation

---

## 7. Proposed Parameter Layers

The parameter model should be split into:

1. geometry flow placement parameters
2. appearance visibility parameters
3. defect-specific directional disturbance parameters

### 7.1 Geometry-related parameters

- allowed zones
- flow direction field or proxy direction
- streak length range
- streak width range
- branching allowance
- edge margin
- allowed curvature range

### 7.2 Appearance-related parameters

- haze strength
- brightness lift range
- desaturation range
- roughness drift range
- transmission damping range
- anisotropy hint strength

### 7.3 Defect-specific parameters

- streak family
  - `soft_lane`
  - `feather_streak`
  - `broken_flow_band`
- edge falloff
- internal modulation
- branch probability
- local banding probability

---

## 8. Recommended Parameter Schema

```yaml
defect_type: splay
defect_family: flow_directional
geometry_profile: p101040_geometry
appearance_profile: p101040_blue_profile
placement:
  allowed_zones:
    - center_plane
    - slope_band
  zone_weights:
    center_plane: 0.65
    slope_band: 0.35
  min_edge_margin_norm: 0.07
  follow_flow_direction: true
shape:
  streak_family: feather_streak
  length_scale_range: [0.10, 0.32]
  width_scale_range: [0.012, 0.060]
  branch_probability: [0.00, 0.18]
  fragment_probability: [0.05, 0.22]
appearance:
  brightness_shift_range: [0.01, 0.10]
  desaturation_shift_range: [0.04, 0.18]
  roughness_add_range: [0.01, 0.06]
  transmission_shift_range: [-0.08, -0.01]
  haze_strength_range: [0.02, 0.12]
  edge_alpha_range: [0.05, 0.18]
label_policy:
  mask_mode: main_streak_region
  support_artifacts_excluded: true
risks:
  - may drift toward mixed_color_contamination if directional cue is weak
  - may drift toward lighting artifact if too low contrast
  - may drift toward grime if too dark
```

---

## 9. Appearance Recommendations By Profile

### 9.1 `p101040_blue_profile`

Recommended:

- first target profile
- use haze + desaturation + transmission damping
- keep boundaries very soft

Avoid:

- hard white painted streak look
- broad dirty smear look

### 9.2 `qc7_1336_gray_profile`

Recommended:

- second-best calibration target
- use gray-white flow haze
- moderate roughness drift

### 9.3 `qc8_8511_white_profile`

Recommended:

- rely more on roughness / sheen change than strong brightness lift

Risk:

- can vanish if only brightness is used
- can look like dirt if too dark

### 9.4 `qc7_8578_black_profile`

Recommended:

- gray-white haze lane
- slight sheen mismatch

Risk:

- too faint becomes invisible
- too bright becomes fake paint streak

### 9.5 `moxing1_white_profile`

Recommended:

- use as a secondary opaque reference
- keep low contrast and elongated structure

### 9.6 `moxing1_black_profile`

Recommended:

- use only after black profile visibility rules are clearer
- likely needs stronger sheen / roughness cue

---

## 10. Boundary Rules Against Nearby Classes

### 10.1 vs `mixed_color_contamination`

`splay`:

- directional
- elongated
- flow-linked

`mixed_color_contamination`:

- local patch
- no strong directional logic required

### 10.2 vs `surface_contamination`

`splay`:

- material process abnormality
- internal-looking or molded-surface-consistent

`surface_contamination`:

- surface dirt / grime / stain
- less tied to flow structure

### 10.3 vs `foreign_material`

`splay`:

- no discrete object body
- no particle silhouette

`foreign_material`:

- matter-like object or fragment

### 10.4 vs `black_dot`

`splay`:

- broad directional region

`black_dot`:

- compact embedded point

---

## 11. Candidate Implementation Strategies

### Strategy A: soft directional patch field

Use:

- one or more soft elongated masks
- directional modulation
- brightness / haze / roughness response

Pros:

- easy to parameterize
- easy to keep low contrast

Risks:

- can become generic contamination if directionality is weak

### Strategy B: flow-lane material response

Use:

- no obvious patch edge
- procedural banded directional disturbance
- anisotropic-like material response hints

Pros:

- more physically plausible

Risks:

- harder to control
- harder to label cleanly

### Recommended order

Start with a hybrid:

- directional soft mask field
- internal modulation
- appearance-specific haze / roughness / transmission response

This gives the best balance between:

- realism
- controllability
- label clarity

---

## 12. Validation Requirements

Before implementation is accepted, it should satisfy:

1. reads as directional flow abnormality
2. does not look like dirt or contamination patch
3. stays plausible under more than one viewing angle
4. can be labeled as a coherent streak region
5. remains consistent with the target material family

### 12.1 Review checklist

- direction is visible
- contrast stays restrained
- boundary remains soft
- shape is not blob-like
- effect survives beyond one exact light angle

---

## 13. Planned Deliverables For The Next Step

The next planning step should produce:

1. a flow-direction proxy proposal by geometry line
2. an appearance table for haze / roughness / transmission behavior
3. a label-policy note for elongated defects
4. a risk matrix comparing:
   - `splay`
   - `mixed_color_contamination`
   - `surface_contamination`

---

## 14. Bottom Line

`splay` should remain a mainline class, but it needs stronger process-aware planning than the other classes.

It should be approached after:

- category cleanup
- `mixed_color_contamination` split
- `foreign_material` split

because it is the class most likely to drift into a fake graphics patch if its mechanism is not kept explicit.
