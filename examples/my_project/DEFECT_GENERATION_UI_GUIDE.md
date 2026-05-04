# Defect Generation UI Guide

Last updated: 2026-05-04

This document describes the first usable desktop UI for the defect dataset
generator.

## Entry Point

```text
E:\BlenderProject\BlenderProc\examples\my_project\defect_generation_ui.py
```

Run from the repository root:

```powershell
cd E:\BlenderProject\BlenderProc
D:\Anaconda\envs\defect_eval\python.exe examples\my_project\defect_generation_ui.py
```

Or double-click this launcher:

```text
E:\BlenderProject\BlenderProc\打开缺陷生成UI.bat
```

## What It Does

The UI is a safe wrapper around:

```text
E:\BlenderProject\BlenderProc\defect_dataset_generator\app.py
```

It reads target/defect options from:

```text
defect_dataset_generator\config\model_color_profiles.json
defect_dataset_generator\config\model_color_defect_targets.json
```

Supported command modes:

| UI mode | CLI command |
| --- | --- |
| Single | `generate-target` |
| Cooccurrence | `generate-target-cooccurrence` |
| Normal | `generate-target-normal` |

The UI can:

- select target, defect, side, count, samples, seed, and output folder;
- use a single-choice defect selector in `Single` mode, so count/side always
  apply to one exact defect;
- switch the interface language between Chinese and English;
- preview the exact command before running;
- run in dry-run mode;
- stream stdout/stderr into the log panel;
- stop a process started by the UI;
- open the output folder;
- load RGB and mask images from the output folder;
- count RGB, mask, label files, empty masks, and key run metadata files.

## Safety Defaults

- `Dry run only` is enabled by default. Dry run means the UI only writes/previews
  the generation plan and command. It does not launch Blender rendering and does
  not create real RGB/mask images.
- Default output is an isolated folder. The outer folder is grouped by date,
  then dry-run and real rendering outputs are separated, and each run receives
  a concrete time/task folder:

```text
defect_dataset_generator\outputs\dataset\ui_runs_YYYYMMDD\dry_run\HHMMSS_mmm_target_mode_side
defect_dataset_generator\outputs\dataset\ui_runs_YYYYMMDD\render\HHMMSS_mmm_target_mode_side
```

- When the output path has not been edited manually, the UI refreshes this path
  when target/mode/side/dry-run settings change, and refreshes the run timestamp
  once more when `Run` is clicked.
- The UI blocks `count > 20` unless `Allow count > 20 from UI` is checked.
- It does not alter production generation logic.
- It does not modify model/profile JSON files.
- It does not interrupt production renders unless the user starts a new run manually.

## Cooccurrence Options

The cooccurrence selector is intentionally restricted to combinations that have
already passed manual RGB/mask inspection. It is not a free defect multi-select.

Current approved same-scene combinations:

| Target | Approved combo | CLI defects |
| --- | --- | --- |
| `qc71336_black` | `foreign_material+splay` | `foreign_material,splay` |
| `qc7_5244_black` | `foreign_material+splay` | `foreign_material,splay` |

Black-dot-containing cooccurrence combinations are not listed here yet, because
the current 3-5k dataset handoff only uses approved single black-dot generation.
`ql3_1052_black` cooccurrence was explicitly removed from the current plan.

## Typical Smoke Workflow

1. Open the UI.
2. Select a known accepted target, for example `qc71336_white`.
3. Select mode `Single`.
4. Select defect `black_dot` or `foreign_material`.
5. Select side `front`.
6. Keep `count=1`, `samples=8` or `16`.
7. Keep `Dry run only` enabled and click `Run`.
8. Inspect the generated command/log.
9. Disable `Dry run only` only when the command is correct.
10. Run again, then use `Load Results` to preview `rgb` and `masks`.

## Technical Notes

This UI can be described as the system interaction layer. It exposes the
synthetic defect generation pipeline to non-command-line users and connects
profile selection, generation parameter configuration, command execution,
logging, and image/mask preview in one tool.

For technical screenshots, use the UI after loading a small run output so the
preview and summary panels are populated.
