# Phase 2 to Phase 7 Implementation Roadmap

This document is planning only.
It does not change formal rendering or training code.

It exists to turn the existing planning set into a practical execution order.

---

## 1. What Is Already Settled

The planning foundation now exists in these files:

- [E:\BlenderProject\BlenderProc\examples\my_project\PHASE2_PHASE7_SCHEMA_DRAFT.md](E:\BlenderProject\BlenderProc\examples\my_project\PHASE2_PHASE7_SCHEMA_DRAFT.md)
- [E:\BlenderProject\BlenderProc\examples\my_project\PHASE3_BLACK_DOT_CROSS_APPEARANCE_PLAN.md](E:\BlenderProject\BlenderProc\examples\my_project\PHASE3_BLACK_DOT_CROSS_APPEARANCE_PLAN.md)
- [E:\BlenderProject\BlenderProc\examples\my_project\PHASE4_MIXED_COLOR_CONTAMINATION_PLAN.md](E:\BlenderProject\BlenderProc\examples\my_project\PHASE4_MIXED_COLOR_CONTAMINATION_PLAN.md)
- [E:\BlenderProject\BlenderProc\examples\my_project\PHASE5_FOREIGN_MATERIAL_PLAN.md](E:\BlenderProject\BlenderProc\examples\my_project\PHASE5_FOREIGN_MATERIAL_PLAN.md)
- [E:\BlenderProject\BlenderProc\examples\my_project\PHASE6_SPLAY_PLAN.md](E:\BlenderProject\BlenderProc\examples\my_project\PHASE6_SPLAY_PLAN.md)

The core policy decisions are:

1. use a `geometry / appearance / defect override` split
2. keep `opaque_matte_satin_plastic` and `semi_translucent_blue_plastic` explicit
3. retire broad `contamination` as a public training class
4. use four mainline classes:
   - `black_dot`
   - `mixed_color_contamination`
   - `foreign_material`
   - `splay`
5. keep support artifacts outside the main class label by default

---

## 2. Recommended Build Order

### Step 1. Category cleanup entry layer

Goal:

- clean up naming and schema entry points
- do not yet rewrite every rendering function

Primary target:

- [E:\BlenderProject\BlenderProc\examples\my_project\generate_black_spot_multi_model.py](E:\BlenderProject\BlenderProc\examples\my_project\generate_black_spot_multi_model.py)

What to change first:

1. replace broad public vocabulary with canonical names
2. keep `legacy_contamination` as an internal compatibility bridge if needed
3. add metadata fields for:
   - `geometry_profile`
   - `appearance_profile`
   - `defect_family`
   - `support_artifacts`
   - `label_policy`

Why first:

- if names stay muddy, every later defect implementation inherits the same confusion

### Step 2. First new defect implementation: `mixed_color_contamination`

Goal:

- split the soft material-shift branch out of legacy contamination

Why first:

- highest-value semantic cleanup
- strong reference assets already exist
- lowest risk of colliding with the current embedded black-dot line

Primary implementation line:

- start on `opaque_matte_satin_plastic`
- likely easiest first pair:
  - `moxing1_geometry + moxing1_white_profile`
  - or `qc7_1336_geometry + qc7_1336_gray_profile`

Validation priority:

- looks like material drift, not dirt
- soft edge, no decal feel
- label region coherent

### Step 3. Second new defect implementation: `foreign_material`

Goal:

- split object-like foreign debris away from both `black_dot` and contamination

Why second:

- very important category boundary
- still easier than `splay`
- useful on black, gray, and white opaque parts

Primary implementation line:

- start on opaque parts first
- likely easiest first pair:
  - `moxing1_geometry + moxing1_white_profile`
  - or `qc7_1336_geometry + qc8_8511_white_profile`

Validation priority:

- object-like identity
- no splash feel
- distinct from `black_dot`

### Step 4. Third new defect implementation: `splay`

Goal:

- create a true directional flow-abnormality line

Why third:

- highest mechanism sensitivity
- easiest to fake accidentally
- depends most on a clean class system being in place first

Primary implementation line:

- start with:
  - `p101040_geometry + p101040_blue_profile`

Validation priority:

- directional cue is visible
- not blob-like
- not dirt-like
- not just a lighting artifact

### Step 5. Cross-appearance `black_dot` expansion

Goal:

- keep current canonical embedded route
- add appearance-aware overrides for opaque black/gray/white families

Why after the category split:

- current `black_dot` line already works best on `P101040`
- the bigger risk now is class confusion, not missing black-dot capability

Primary implementation order:

1. `qc7_1336_gray_profile`
2. `qc8_8511_white_profile`
3. `qc7_8578_black_profile`
4. `moxing1_white_profile`
5. `moxing1_black_profile`

---

## 3. File-Level Change Priority

### Tier A: schema / entry-point files

These should be touched earliest when implementation begins.

1. [E:\BlenderProject\BlenderProc\examples\my_project\generate_black_spot_multi_model.py](E:\BlenderProject\BlenderProc\examples\my_project\generate_black_spot_multi_model.py)
2. [E:\BlenderProject\BlenderProc\examples\my_project\reference_blend_blue_blackdot_debug.py](E:\BlenderProject\BlenderProc\examples\my_project\reference_blend_blue_blackdot_debug.py)

Why:

- first file controls the mainline generator vocabulary
- second file holds the cleanest current black-dot prototype logic

### Tier B: task-prep / audit files

These should be updated once canonical names and label policy are settled.

1. [E:\BlenderProject\BlenderProc\examples\my_project\prepare_p101040_task_eval.py](E:\BlenderProject\BlenderProc\examples\my_project\prepare_p101040_task_eval.py)
2. [E:\BlenderProject\BlenderProc\examples\my_project\prepare_p101040_synth_filtering_and_ablation.py](E:\BlenderProject\BlenderProc\examples\my_project\prepare_p101040_synth_filtering_and_ablation.py)
3. [E:\BlenderProject\BlenderProc\examples\my_project\audit_reference_scene_50_roi_labels.py](E:\BlenderProject\BlenderProc\examples\my_project\audit_reference_scene_50_roi_labels.py)
4. [E:\BlenderProject\BlenderProc\examples\my_project\evaluate_p101040_dataset_level.py](E:\BlenderProject\BlenderProc\examples\my_project\evaluate_p101040_dataset_level.py)

Why:

- class names and label rules have to stay consistent through generation, audit, and task-eval

### Tier C: reporting and summary scripts

These should be updated later, after canonical class names are already stable in the data path.

---

## 4. First-Pass Implementation Matrix

| Defect type | First geometry target | First appearance target | Why this pair first |
|---|---|---|---|
| `mixed_color_contamination` | `qc7_1336_geometry` or `moxing1_geometry` | `qc7_1336_gray_profile` or `moxing1_white_profile` | easiest to read subtle soft drift on opaque neutral surfaces |
| `foreign_material` | `moxing1_geometry` or `qc7_1336_geometry` | `moxing1_white_profile` or `qc8_8511_white_profile` | strongest visible separation from background without relying on transmission |
| `splay` | `p101040_geometry` | `p101040_blue_profile` | best chance to express haze / flow / transmission disturbance plausibly |
| `black_dot` cross-appearance | `qc7_1336_geometry` | `qc7_1336_gray_profile` | best neutral opaque calibration before black/white extremes |

---

## 5. Validation Ladder

Each implementation should pass through the same ladder.

### Level 1. Visual smoke

- 3 to 10 renders
- human inspection only
- no task training yet

Questions:

- does it look like the intended defect class?
- does it stay distinct from neighboring classes?
- does the main label region make sense?

### Level 2. ROI / label audit

- bbox and mask inspection
- real-image comparison
- class-boundary inspection

Questions:

- is the labeled region too loose / too tight?
- is support artifact leaking into the main class?
- is the synthetic appearance stable across samples?

### Level 3. Small candidate training set

- build a small candidate task-eval group
- run seed=0 only

Questions:

- does it help at all?
- does it collapse precision?
- does it learn the wrong visual cue?

### Level 4. 3-seed validation

- only for candidates that survive seed=0

Questions:

- does the gain persist?
- does stability hold?

---

## 6. Guardrails

### Do not do first

- do not rework every script at once
- do not rename every legacy artifact in one sweep
- do not build all four new classes in parallel
- do not push new classes into task training before ROI / label audit

### Do first

- tighten class language
- implement one class at a time
- keep label policy explicit
- preserve the current embedded `black_dot` line while the new classes are being introduced

---

## 7. Practical Next Action

If execution starts immediately after planning, the most practical next action is:

1. update the main generator's public class vocabulary and metadata schema
2. implement a first `mixed_color_contamination` prototype on an opaque profile
3. validate visually before touching task training

This is the lowest-risk way to move from planning into code while keeping the class system coherent.

---

## 8. Bottom Line

The best execution sequence is:

1. category/schema cleanup
2. `mixed_color_contamination`
3. `foreign_material`
4. `splay`
5. cross-appearance `black_dot`

That order protects the current working black-dot line while fixing the largest remaining semantic mess first.
