# Material Fitting Real Reference Validation

## Goal

Validate that automatic material fitting can use a real white plastic reference photo, render material candidates through BlenderProc, score them with similarity metrics, and export ranked visually fitted material parameters.

This validation checks the pipeline mechanics and visual ranking behavior. It does not claim physical material accuracy.

## Command Used

Run from:

```powershell
cd E:\BlenderProject\BlenderProc\defect_dataset_generator
```

Command:

```powershell
python app.py fit-material --real examples\my_project\QC71336_white_real_manual_labels_v2\images\all\9K9A0685.JPG --blend assets\models\QC7-1336-white.blend --out defect_dataset_generator\outputs\fitting\fit_real_reference_test_01 --candidates 10 --scoring real --render-candidates --roi center --resize 512 --samples 16 --seed 100 --material-profile opaque_white_plastic
```

## Inputs

- Reference image:
  - `E:\BlenderProject\BlenderProc\examples\my_project\QC71336_white_real_manual_labels_v2\images\all\9K9A0685.JPG`
- Blend file:
  - `E:\BlenderProject\BlenderProc\assets\models\QC7-1336-white.blend`
- Candidate count:
  - `10`
- ROI mode:
  - `center`
- Resize:
  - `512`
- Render samples:
  - `16`
- Material profile:
  - `opaque_white_plastic`

The reference photo is a real white plastic part image with background, perspective, shadows, logo/text, and visible surface texture. `center` ROI was used because manual clean-region ROI is not supported yet.

## Output Validation

Output folder:

```text
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\fitting\fit_real_reference_test_01
```

Validated outputs:

```text
candidate_materials/          10 JSON files
candidate_renders/            10 PNG files
candidate_metadata/           10 metadata JSON files
best_material.json            exists
material_fit_candidates.json  exists and ranks candidates
material_fitting_report.json  exists and records success/failure counts
best_preview_render.json      exists and points to the best render
```

Run summary:

```text
requested candidates: 10
succeeded: 10
failed: 0
best candidate id: 6
best score: 0.503981
metric backend: pillow_baseline
```

## Top 5 Scores

| Rank | Candidate ID | Score | Base color | Roughness | Specular |
| --- | ---: | ---: | --- | ---: | ---: |
| 1 | 6 | 0.503981 | `[0.78, 0.80, 0.82, 1.0]` | 0.68 | 0.20 |
| 2 | 7 | 0.503957 | `[0.78, 0.80, 0.82, 1.0]` | 0.68 | 0.35 |
| 3 | 8 | 0.503949 | `[0.78, 0.80, 0.82, 1.0]` | 0.68 | 0.50 |
| 4 | 3 | 0.503821 | `[0.78, 0.80, 0.82, 1.0]` | 0.50 | 0.20 |
| 5 | 4 | 0.503771 | `[0.78, 0.80, 0.82, 1.0]` | 0.50 | 0.35 |

## Best Candidate Parameters

```json
{
  "base_color": [0.78, 0.80, 0.82, 1.0],
  "roughness": 0.68,
  "specular": 0.20,
  "alpha": 1.0
}
```

Best material export:

```text
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\fitting\fit_real_reference_test_01\best_material.json
```

Best render:

```text
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\fitting\fit_real_reference_test_01\candidate_renders\candidate_000006.png
```

## Visual Comparison

Contact sheet:

```text
E:\BlenderProject\BlenderProc\defect_dataset_generator\outputs\fitting\fit_real_reference_test_01\visual_comparison\fit_real_reference_contact_sheet.jpg
```

The comparison folder also contains copies of the real reference image, the top three renders, and the worst render.

## Observations

- Material color: the top-ranked candidates choose the neutral light gray-blue base color `[0.78, 0.80, 0.82, 1.0]`, which is plausible for the real white plastic reference, but still not a calibrated physical color.
- Brightness: the brightness metric is relatively high for the best candidate (`0.860249`), but the render background and reference photo background differ strongly.
- Roughness/highlight: the top three all use high roughness `0.68`, which visually makes sense for the matte plastic reference. Specular differences have very small score impact in this run.
- Texture/bump: the current material search does not truly reproduce the dotted/embossed texture visible in the real reference. The edge/texture score is high, but this appears influenced by broad image structure and preprocessing rather than true surface texture matching.
- Background influence: background, camera angle, crop, and object scale dominate the comparison. Color histogram and SSIM are low, showing that the current deterministic candidate camera does not match the real photo composition.
- Human visual judgment: Top1, Top2, and Top3 look nearly identical to a human. The metric ranking among them should be treated as weak evidence. The worst render is slightly brighter/cooler, but the gap is not visually dramatic.

## Limitations

- This is a visual fitting test, not a physically accurate material calibration.
- Manual clean-region ROI is not implemented yet, so the center ROI includes background, shadows, logo/text, and non-material geometry.
- The candidate camera and real photo camera are not aligned.
- The render resolution is currently fixed by the fitter at `512x384`; `--resize` only controls metric preprocessing.
- The search space is very small and does not include a true texture/bump pattern matching the real dotted plastic surface.
- LPIPS is not enabled.

## Next Actions

1. Add manual ROI support or a mask-based product/material ROI for real reference photos.
2. Add camera/profile alignment before trusting metric scores.
3. Expand the material search space with texture/bump controls that can represent dotted plastic.
4. Add a stricter validation set with multiple real clean white references.
5. Keep using contact sheets because metric ranking can disagree with human visual perception.
