# Defect Realism Evaluation Plan

## Purpose

Build a non-YOLO evaluation workflow for judging whether generated defects visually resemble real inspection photos.

This module is intended to guide rendering improvement before detector training. It is not a detector metric and it is not a physical realism proof.

## Scope

The architecture should support multiple defect classes:

- `black_dot`
- `mixed_color_contamination`
- `foreign_material`
- `splay`
- future geometric defects such as `sink_mark`

The first implemented adapter is `black_dot`, because it already has real labels, synthetic masks, YOLO labels, and visual audit history.

## Real Dataset Profile Layer

The reorganized real dataset root is:

`E:\BlenderProject\BlenderProc\塑料工件真实数据集`

Top-level folders now encode model and appearance:

| Folder example | Model | Appearance |
| --- | --- | --- |
| `P101040蓝色` | `P101040` | blue |
| `QC71336白色` | `QC71336` | white |
| `QC71336灰色` | `QC71336` | gray |
| `QC7-5244白色` | `QC7-5244` | white |
| `QL3-1052黑色` | `QL3-1052` | black |

Subfolders encode defect category by Chinese keywords:

| Keyword | Canonical defect type |
| --- | --- |
| `黑点` | `black_dot` |
| `混色` | `mixed_color_contamination` |
| `异物` | `foreign_material` |
| `料花` | `splay` |
| `正常` | `normal` |

Implementation file:

`core/real_dataset_profiles.py`

## Evaluation Inputs

For defect-level realism, the preferred input format is:

```text
real_images/
real_labels/
synthetic_dataset/
  rgb/
  masks/
  labels_yolo/
  metadata/
```

If the real dataset folder has not yet been converted to YOLO labels, the module can still scan and report model/color/defect-folder structure, but crop-based metrics require labels or another localization source.

## Common Metrics

These metrics are shared across defect types:

- image/label/mask integrity;
- defect crop extraction;
- defect/background brightness contrast;
- normalized visibility;
- edge softness proxy;
- defect area ratio;
- bbox area ratio;
- local background statistics;
- contact sheet for human visual review.

## Defect-Specific Metrics

### Black Dot

Focus:

- too dark vs real;
- too sharp / hard-edged;
- too particle-like or raised;
- too low/high contrast;
- context mismatch around edge/shadow/texture regions;
- mask and bbox stability.

### Mixed Color Contamination

Future focus:

- color drift relative to plastic surface;
- low-frequency footprint;
- soft boundary;
- whether it looks material-internal rather than pasted on top.

### Foreign Material

Future focus:

- objectness;
- contact/shadow relation;
- mask should cover the foreign object, not background response;
- avoid confusion with surface stain.

### Splay

Future focus:

- directional streak behavior;
- low-opacity material-flow look;
- not global texture pollution;
- local boundary softness.

## Output Schema

Summary JSON should use:

```json
{
  "schema_version": "0.1",
  "evaluation_type": "defect_realism",
  "defect_type": "black_dot",
  "real_dataset_profile": {},
  "synthetic_dataset_profile": {},
  "common_metrics": {},
  "defect_specific_metrics": {},
  "visual_outputs": {},
  "human_review_guidance": [],
  "limitations": []
}
```

## Reports

Each run should write:

- `defect_realism_summary.json`
- `defect_realism_per_sample.csv`
- `real_vs_synthetic_defect_crops.jpg`
- `DEFECT_REALISM_REPORT.md`

## Interpretation Guardrails

- Do not use these metrics as proof of detector improvement.
- Do not call the score physically accurate.
- Do not rely on bbox size alone.
- Use contact sheets and real crop inspection as the primary judgement loop.
- YOLO should remain paused until visual realism and dataset splits are ready.

## Immediate Next Step

Implement `tools/evaluate_defect_realism.py` with:

- real dataset root scanning;
- `black_dot` crop-level metrics;
- synthetic framework dataset support;
- contact sheet and markdown report export.

