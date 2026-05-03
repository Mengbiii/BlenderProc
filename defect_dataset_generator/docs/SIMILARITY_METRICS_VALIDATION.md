# Similarity Metrics Validation

## Environment

- Metric backend: `pillow_baseline`
- ROI mode: `center`
- Resize: `512`
- Dependency path: Pillow only, no NumPy required

## Test Images

Base image:

```text
defect_dataset_generator/outputs/dataset/black_spot_batch5_validation/rgb/000000.png
```

Validation pairs:

| Case | Reference | Candidate | Expected |
| --- | --- | --- | --- |
| Good match | `rgb/000000.png` | `rgb/000000.png` | Highest score |
| Medium match | `rgb/000000.png` | `rgb/000001.png` | Middle score |
| Poor match | `rgb/000000.png` | `masks/000000.png` | Lowest score |

## Commands

Good match:

```powershell
python app.py compare-images --reference defect_dataset_generator\outputs\dataset\black_spot_batch5_validation\rgb\000000.png --candidate defect_dataset_generator\outputs\dataset\black_spot_batch5_validation\rgb\000000.png --roi center --resize 512 --out defect_dataset_generator\outputs\fitting\similarity_validation\good_match.json
```

Medium match:

```powershell
python app.py compare-images --reference defect_dataset_generator\outputs\dataset\black_spot_batch5_validation\rgb\000000.png --candidate defect_dataset_generator\outputs\dataset\black_spot_batch5_validation\rgb\000001.png --roi center --resize 512 --out defect_dataset_generator\outputs\fitting\similarity_validation\medium_match.json
```

Poor match:

```powershell
python app.py compare-images --reference defect_dataset_generator\outputs\dataset\black_spot_batch5_validation\rgb\000000.png --candidate defect_dataset_generator\outputs\dataset\black_spot_batch5_validation\masks\000000.png --roi center --resize 512 --out defect_dataset_generator\outputs\fitting\similarity_validation\poor_match.json
```

## Results

| Case | Brightness | Color histogram | SSIM | Edge/texture | Weighted score |
| --- | ---: | ---: | ---: | ---: | ---: |
| Good match | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| Medium match | 0.938626 | 0.592228 | 0.380403 | 0.990730 | 0.705572 |
| Poor match | 0.454022 | 0.000046 | 0.000265 | 0.989623 | 0.311510 |

Expected ordering passed:

```text
good_score > medium_score > poor_score
1.000000 > 0.705572 > 0.311510
```

## Observations

- Same-image comparison correctly returns perfect scores.
- Different black-spot renders from the same backend land in a medium range. This is expected because camera/lighting/defect position differ even though the material family is similar.
- RGB-vs-mask comparison produces a low weighted score, mainly due to color histogram and SSIM collapse.
- Edge/texture remains high for the poor pair because the binary mask is mostly flat background, so the average edge difference is small after resizing. This confirms edge/texture should remain a supporting metric, not the dominant material-fitting signal.

## Output Files

```text
defect_dataset_generator/outputs/fitting/similarity_validation/
  good_match.json
  medium_match.json
  poor_match.json
```

## Validation Conclusion

The first Pillow-based implementation is suitable as a stable baseline for material-fitting candidate ranking. It is deterministic, lightweight, and produces interpretable metric breakdowns. Future material fitting should start with `roi_mode=center`, then test `roi_mode=auto` after foreground detection is validated on real reference images.
