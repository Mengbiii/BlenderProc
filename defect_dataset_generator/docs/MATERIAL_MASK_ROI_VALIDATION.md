# Material Mask ROI Validation

## Purpose

Validate material-mask ROI scoring for visual material calibration and compare it against manual ROI on a broader 20-candidate material search.

This validation is for stronger visual material calibration. It is not physical inverse rendering or BRDF recovery.

## Reference

Real white plastic reference:

```text
E:\BlenderProject\BlenderProc\examples\my_project\QC71336_white_real_manual_labels_v2\images\all\9K9A0685.JPG
```

Blend file:

```text
E:\BlenderProject\BlenderProc\assets\models\QC7-1336-white.blend
```

## ROI Inputs

Manual ROI:

```text
1900,900,2200,1200
```

Mask ROI:

```text
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\fitting\roi_masks\qc71336_9K9A0685_clean_plastic_rect_mask.png
```

The mask used here is an approximate rectangular clean-plastic mask created from the manual ROI region. It validates the mask ROI pipeline, but it is not a precise semantic material segmentation.

## Commands

Manual ROI run:

```powershell
python app.py fit-material --real examples\my_project\QC71336_white_real_manual_labels_v2\images\all\9K9A0685.JPG --blend assets\models\QC7-1336-white.blend --out defect_dataset_generator\outputs\fitting\fit_plastic_manual_roi_20 --candidates 20 --scoring real --render-candidates --roi manual --roi-box 1900,900,2200,1200 --resize 512 --samples 16 --seed 200 --material-profile opaque_white_plastic --render-width 512 --render-height 384 --score-profile plastic_material
```

Mask ROI run:

```powershell
python app.py fit-material --real examples\my_project\QC71336_white_real_manual_labels_v2\images\all\9K9A0685.JPG --blend assets\models\QC7-1336-white.blend --out defect_dataset_generator\outputs\fitting\fit_plastic_mask_roi_20 --candidates 20 --scoring real --render-candidates --roi mask --roi-mask defect_dataset_generator\outputs\fitting\roi_masks\qc71336_9K9A0685_clean_plastic_rect_mask.png --resize 512 --samples 16 --seed 220 --material-profile opaque_white_plastic --render-width 512 --render-height 384 --score-profile plastic_material
```

## Output Folders

Manual ROI:

```text
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\fitting\fit_plastic_manual_roi_20
```

Mask ROI:

```text
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\fitting\fit_plastic_mask_roi_20_v2
```

Contact sheets:

```text
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\fitting\fit_plastic_manual_roi_20\top_bottom_contact_sheet.jpg
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\fitting\fit_plastic_mask_roi_20_v2\top_bottom_contact_sheet.jpg
```

## Mask Metadata

The mask ROI smoke test recorded:

```text
reference_mask_pixel_count: 2643401
candidate_mask_pixel_count: 25956
comparison_mask_pixel_count: 262144
```

The scoring metadata records:

- `roi_mode: mask`
- `roi_mask`
- `reference_mask_pixel_count`
- `candidate_mask_pixel_count`
- `comparison_mask_pixel_count`

## Candidate Count

Both runs used:

```text
candidates requested: 20
succeeded: 20
failed: 0
score_profile: plastic_material
```

## Manual ROI Top 5

| Rank | Candidate ID | Score | Base color | Roughness | Specular | Noise scale | Noise strength | Bump strength |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 14 | 0.912196 | `[0.76, 0.80, 0.86, 1.0]` | 0.32 | 0.35 | 96.0 | 0.015 | 0.025 |
| 2 | 13 | 0.912010 | `[0.76, 0.80, 0.86, 1.0]` | 0.32 | 0.18 | 48.0 | 0.015 | 0.0 |
| 3 | 16 | 0.911500 | `[0.76, 0.80, 0.86, 1.0]` | 0.55 | 0.35 | 96.0 | 0.0 | 0.01 |
| 4 | 8 | 0.911190 | `[0.84, 0.85, 0.84, 1.0]` | 0.32 | 0.55 | 48.0 | 0.0 | 0.01 |
| 5 | 15 | 0.911177 | `[0.76, 0.80, 0.86, 1.0]` | 0.55 | 0.18 | 18.0 | 0.035 | 0.025 |

## Manual ROI Bottom 5

| Rank | Candidate ID | Score | Base color | Roughness | Specular | Noise scale | Noise strength | Bump strength |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 20 | 5 | 0.906554 | `[0.92, 0.89, 0.82, 1.0]` | 0.78 | 0.35 | 18.0 | 0.015 | 0.0 |
| 19 | 6 | 0.906645 | `[0.92, 0.89, 0.82, 1.0]` | 0.78 | 0.55 | 48.0 | 0.015 | 0.025 |
| 18 | 3 | 0.907538 | `[0.92, 0.89, 0.82, 1.0]` | 0.55 | 0.35 | 18.0 | 0.035 | 0.01 |
| 17 | 4 | 0.907789 | `[0.92, 0.89, 0.82, 1.0]` | 0.55 | 0.55 | 96.0 | 0.0 | 0.0 |
| 16 | 11 | 0.908112 | `[0.84, 0.85, 0.84, 1.0]` | 0.78 | 0.18 | 48.0 | 0.035 | 0.01 |

Manual ROI score spread:

```text
0.005642
```

## Mask ROI Top 5

| Rank | Candidate ID | Score | Base color | Roughness | Specular | Noise scale | Noise strength | Bump strength |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 14 | 0.912231 | `[0.76, 0.80, 0.86, 1.0]` | 0.32 | 0.35 | 96.0 | 0.015 | 0.025 |
| 2 | 13 | 0.912046 | `[0.76, 0.80, 0.86, 1.0]` | 0.32 | 0.18 | 48.0 | 0.015 | 0.0 |
| 3 | 16 | 0.911531 | `[0.76, 0.80, 0.86, 1.0]` | 0.55 | 0.35 | 96.0 | 0.0 | 0.01 |
| 4 | 8 | 0.911221 | `[0.84, 0.85, 0.84, 1.0]` | 0.32 | 0.55 | 48.0 | 0.0 | 0.01 |
| 5 | 15 | 0.911208 | `[0.76, 0.80, 0.86, 1.0]` | 0.55 | 0.18 | 18.0 | 0.035 | 0.025 |

## Mask ROI Bottom 5

| Rank | Candidate ID | Score | Base color | Roughness | Specular | Noise scale | Noise strength | Bump strength |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 20 | 5 | 0.906585 | `[0.92, 0.89, 0.82, 1.0]` | 0.78 | 0.35 | 18.0 | 0.015 | 0.0 |
| 19 | 6 | 0.906676 | `[0.92, 0.89, 0.82, 1.0]` | 0.78 | 0.55 | 48.0 | 0.015 | 0.025 |
| 18 | 3 | 0.907569 | `[0.92, 0.89, 0.82, 1.0]` | 0.55 | 0.35 | 18.0 | 0.035 | 0.01 |
| 17 | 4 | 0.907820 | `[0.92, 0.89, 0.82, 1.0]` | 0.55 | 0.55 | 96.0 | 0.0 | 0.0 |
| 16 | 11 | 0.908143 | `[0.84, 0.85, 0.84, 1.0]` | 0.78 | 0.18 | 48.0 | 0.035 | 0.01 |

Mask ROI score spread:

```text
0.005646
```

## Human Visual Judgment

The top-ranked candidates are slightly cooler and closer to the real reference's cool white tone than the warm-white bottom candidates. This broadly matches human judgment.

However, the score spread is very small. The top and bottom candidates remain visually similar in the contact sheet because:

- the deterministic camera/lighting compresses material differences;
- the current candidate set still covers a narrow white-plastic range;
- highlight similarity saturates at `1.0` for these matte candidates;
- the approximate rectangular mask is essentially equivalent to the manual ROI.

The metric ranking is therefore directionally reasonable but not yet a strong perceptual separation.

## Limitations

- The mask used here is approximate, not a true material segmentation.
- Scores are visual calibration scores, not physical material accuracy.
- Mask ROI and manual ROI produced nearly identical rankings because the mask matches the manual rectangular region.
- The procedural bump is subtle and may not be visibly separable at the current camera distance and resolution.
- Broader validation should use real material masks, multiple reference photos, and more diverse candidate renders.

## Next Actions

1. Add or import true material masks for clean plastic regions.
2. Validate on more white-plastic references.
3. Consider a candidate contact-sheet review step before accepting fitted parameters.
4. Improve highlight discrimination so matte/gloss differences do not saturate.
5. Evaluate whether CIELAB Delta E improves warm/cool white ranking.
