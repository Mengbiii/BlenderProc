# Material Scoring Validation

## Purpose

Compare the legacy `baseline` score with the new `plastic_material` score profile.

The goal is not to prove physical material accuracy. The goal is to check whether the new score is a more explainable visual material calibration score for ranking clean plastic material candidates.

## Validation Setup

Reference real image:

```text
E:\BlenderProject\BlenderProc\examples\my_project\QC71336_white_real_manual_labels_v2\images\all\9K9A0685.JPG
```

Manual ROI:

```text
1900,900,2200,1200
```

Validation output folder:

```text
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\fitting\material_scoring_validation
```

## Commands

Example plastic-material comparison:

```powershell
python app.py compare-images --reference examples\my_project\QC71336_white_real_manual_labels_v2\images\all\9K9A0685.JPG --candidate defect_dataset_generator\outputs\fitting\fit_plastic_score_test_02\candidate_renders\candidate_000002.png --roi manual --roi-box 1900,900,2200,1200 --resize 512 --score-profile plastic_material --out defect_dataset_generator\outputs\fitting\material_scoring_validation\real_reference_vs_top_candidate_plastic_material.json
```

Example fitting command:

```powershell
python app.py fit-material --real examples\my_project\QC71336_white_real_manual_labels_v2\images\all\9K9A0685.JPG --blend assets\models\QC7-1336-white.blend --out defect_dataset_generator\outputs\fitting\fit_plastic_score_test_02 --candidates 3 --scoring real --render-candidates --roi manual --roi-box 1900,900,2200,1200 --resize 512 --samples 16 --seed 100 --material-profile opaque_white_plastic --render-width 512 --render-height 384 --score-profile plastic_material
```

## Score Table

| Case | Human expectation | Baseline score | Plastic material score |
| --- | --- | ---: | ---: |
| same image pair | identical render, should score highest | 1.000000 | 1.000000 |
| medium candidate pair | same scene, subtle specular/material difference | 0.995786 | 0.999611 |
| poor candidate pair | same type of render but visibly cooler/brighter candidate | 0.972637 | 0.994366 |
| real reference vs top candidate | real clean plastic ROI against top plastic-material candidate | 0.574109 | 0.912317 |
| real reference vs worst candidate | real clean plastic ROI against visually weaker/cooler candidate | 0.578739 | 0.913376 |

## Component Example

For `real_reference_vs_top_candidate`, `plastic_material` produced:

```json
{
  "brightness_similarity": 0.899801,
  "color_similarity": 0.902906,
  "local_contrast_similarity": 0.996819,
  "highlight_similarity": 1.0,
  "texture_similarity": 0.952911,
  "ssim_similarity": 0.43362
}
```

This is more interpretable for technical reporting than the baseline score because each term corresponds to a material appearance cue.

## Observations

- Same-image sanity check passes for both profiles.
- `plastic_material` gives much higher real-reference scores because it is less dominated by histogram bin mismatch and low SSIM from structural/camera differences.
- `plastic_material` reports meaningful components: brightness, color, local contrast, highlight, texture, and low-weight SSIM.
- Full-image `plastic_material` comparisons emit the required warning because clean material ROI is recommended.
- In this validation set, `plastic_material` does not clearly distinguish the selected top candidate from the selected worst candidate. The worst candidate scored slightly higher (`0.913376` vs `0.912317`).

## Human-Judgment Match

The new score is better for technical explanation because it measures material-related cues directly. However, this validation does not prove better ranking across all candidates.

The top/worst mismatch is likely caused by:

- the selected ROI still includes shading and geometry effects;
- candidate renders differ only subtly in the first three tested candidates;
- highlight similarity saturates at `1.0` for these matte candidates;
- the current RGB mean color term is simple and may not capture perceptual warm/cool differences strongly enough;
- no material mask exists yet.

This mismatch should be reported rather than hidden.

## Limitations

- The method is not a physical BRDF recovery metric.
- It is a deterministic visual material calibration score for ranking rendered material candidates.
- It depends heavily on clean ROI selection.
- Mask ROI is now supported, but the first validation used an approximate rectangular mask rather than true semantic material segmentation.
- Highlight detection is approximate and exposure-dependent.
- Texture similarity uses simple edge statistics and cannot recover true molded microgeometry.
- The current color term is RGB-statistical, not CIELAB Delta E.

## Mask ROI Follow-Up

Mask ROI validation is documented in:

```text
docs/MATERIAL_MASK_ROI_VALIDATION.md
```

The 20-candidate manual ROI and mask ROI runs selected the same best candidate (`candidate_id=14`) and produced nearly identical score spreads:

```text
manual ROI score spread: 0.005642
mask ROI score spread:   0.005646
```

This confirms that mask ROI plumbing is working, but also shows that the approximate rectangular mask is not yet enough to create a strong perceptual separation.

## Suggested Technical Wording

Suggested wording:

> A visual material calibration score was introduced to rank rendered material candidates against real injection-molded plastic references. Unlike whole-image similarity, the score is computed within a clean material ROI and combines brightness, color tone, local contrast, highlight behavior, texture cues, and a low-weight structural similarity term. The metric is deterministic and lightweight, and is intended for practical visual candidate ranking rather than physical BRDF recovery.
