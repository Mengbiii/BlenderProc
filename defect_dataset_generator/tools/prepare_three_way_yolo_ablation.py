import argparse
import json
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


def main():
    parser = argparse.ArgumentParser(description="Prepare three-way real/synthetic YOLO ablation datasets.")
    parser.add_argument("--real-yaml", required=True)
    parser.add_argument("--default-synth", required=True)
    parser.add_argument("--fitted-synth", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--class-name", default="black_dot")
    args = parser.parse_args()

    real_yaml = resolve_path(args.real_yaml)
    default_synth = resolve_path(args.default_synth)
    fitted_synth = resolve_path(args.fitted_synth)
    out_root = resolve_path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    real_config = parse_simple_yaml(real_yaml)
    real_root = resolve_dataset_root(real_yaml, real_config)
    variants = [
        {
            "key": "A_real_only",
            "yaml": out_root / "A_real_only.yaml",
            "root": out_root / "A_real_only",
            "synthetic_train": None,
            "description": "real train only",
        },
        {
            "key": "B_real_plus_default_synthetic_count20",
            "yaml": out_root / "B_real_plus_default_synthetic_count20.yaml",
            "root": out_root / "B_real_plus_default_synthetic_count20",
            "synthetic_train": default_synth,
            "description": "real train plus default_material_count20 synthetic train",
        },
        {
            "key": "C_real_plus_fitted_v2_synthetic_count20",
            "yaml": out_root / "C_real_plus_fitted_v2_synthetic_count20.yaml",
            "root": out_root / "C_real_plus_fitted_v2_synthetic_count20",
            "synthetic_train": fitted_synth,
            "description": "real train plus fitted_v2_material_count20 synthetic train",
        },
    ]

    summary = {
        "schema_version": "0.1",
        "prep_type": "three_way_real_synthetic_ablation",
        "inputs": {
            "real_yaml": str(real_yaml),
            "real_root": str(real_root),
            "default_synthetic": str(default_synth),
            "fitted_synthetic": str(fitted_synth),
        },
        "class_name": args.class_name,
        "class_name_alias_note": "Real YAML used black_dot; synthetic datasets used black_spot. All labels remain class id 0. Prepared YAMLs use black_dot consistently.",
        "variants": {},
    }

    for variant in variants:
        prepare_variant(variant, real_root, real_config, args.class_name)
        audit = audit_variant(variant["root"], variant["synthetic_train"] is not None)
        summary["variants"][variant["key"]] = {
            "description": variant["description"],
            "yaml": str(variant["yaml"]),
            "root": str(variant["root"]),
            "audit": audit,
        }

    write_report(out_root / "THREE_WAY_DATASET_PREP_REPORT.md", summary)
    (out_root / "three_way_dataset_prep_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_training_commands(out_root.parent / "TRAINING_COMMANDS.md", variants)
    print(json.dumps({"status": "completed", "out": str(out_root)}, indent=2, ensure_ascii=False))


def resolve_path(value):
    path = Path(value)
    if path.is_absolute():
        return path
    if path.parts and path.parts[0] in {"outputs", "tools", "config", "core", "docs"}:
        return (PROJECT_ROOT / path).resolve()
    project_path = (PROJECT_ROOT / path).resolve()
    if project_path.exists():
        return project_path
    return (PROJECT_ROOT.parent / path).resolve()


def parse_simple_yaml(path):
    data = {"names": {}}
    in_names = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "names:":
            in_names = True
            continue
        if in_names and (raw.startswith(" ") or raw.startswith("\t")):
            key, value = stripped.split(":", 1)
            data["names"][int(key.strip())] = value.strip().strip("'\"")
            continue
        in_names = False
        if ":" in stripped:
            key, value = stripped.split(":", 1)
            data[key.strip()] = value.strip().strip("'\"")
    return data


def resolve_dataset_root(yaml_path, config):
    root = Path(config.get("path", ""))
    if root.is_absolute():
        return root
    return (yaml_path.parent / root).resolve()


def split_image_dir(root, split):
    return root / "images" / split


def split_label_dir(root, split):
    return root / "labels" / split


def prepare_variant(variant, real_root, real_config, class_name):
    root = variant["root"]
    if root.exists():
        shutil.rmtree(root)
    for split in ["train", "val", "test"]:
        (root / "images" / split).mkdir(parents=True, exist_ok=True)
        (root / "labels" / split).mkdir(parents=True, exist_ok=True)

    copy_real_split(real_root, "train", root, "train")
    copy_real_split(real_root, "val", root, "val")
    copy_real_split(real_root, "test", root, "test")
    if variant["synthetic_train"]:
        copy_synthetic_train(variant["synthetic_train"], root)

    write_yolo_yaml(variant["yaml"], root, class_name)


def copy_real_split(real_root, source_split, out_root, target_split):
    image_dir = split_image_dir(real_root, source_split)
    label_dir = split_label_dir(real_root, source_split)
    for image_path in sorted_images(image_dir):
        target_stem = "real_" + image_path.stem
        copy_pair(image_path, label_dir / (image_path.stem + ".txt"), out_root, target_split, target_stem)


def copy_synthetic_train(synth_root, out_root):
    image_dir = synth_root / "rgb"
    label_dir = synth_root / "labels_yolo"
    for image_path in sorted_images(image_dir):
        target_stem = "synth_" + image_path.stem
        copy_pair(image_path, label_dir / (image_path.stem + ".txt"), out_root, "train", target_stem)


def sorted_images(image_dir):
    return sorted([p for p in image_dir.glob("*") if p.suffix.lower() in IMAGE_EXTS])


def copy_pair(image_path, label_path, out_root, split, target_stem):
    target_image = out_root / "images" / split / (target_stem + image_path.suffix.lower())
    target_label = out_root / "labels" / split / (target_stem + ".txt")
    shutil.copy2(image_path, target_image)
    if label_path.exists():
        shutil.copy2(label_path, target_label)
    else:
        target_label.write_text("", encoding="utf-8")


def write_yolo_yaml(path, root, class_name):
    text = "\n".join(
        [
            "path: {0}".format(root),
            "train: images/train",
            "val: images/val",
            "test: images/test",
            "",
            "names:",
            "  0: {0}".format(class_name),
            "",
        ]
    )
    path.write_text(text, encoding="utf-8")


def audit_variant(root, expect_synthetic_train):
    result = {
        "root": str(root),
        "splits": {},
        "class_id_distribution": {},
        "missing_pairs": [],
        "invalid_labels": [],
        "synthetic_only_in_train": True,
        "passed": True,
    }
    for split in ["train", "val", "test"]:
        audit = audit_split(root, split)
        result["splits"][split] = audit
        for class_id, count in audit["class_id_distribution"].items():
            result["class_id_distribution"][class_id] = result["class_id_distribution"].get(class_id, 0) + count
        result["missing_pairs"].extend(audit["missing_pairs"])
        result["invalid_labels"].extend(audit["invalid_labels"])
        if split != "train" and audit["synthetic_image_count"] > 0:
            result["synthetic_only_in_train"] = False
    if expect_synthetic_train and result["splits"]["train"]["synthetic_image_count"] == 0:
        result["synthetic_only_in_train"] = False
    if result["missing_pairs"] or result["invalid_labels"] or not result["synthetic_only_in_train"]:
        result["passed"] = False
    return result


def audit_split(root, split):
    image_dir = root / "images" / split
    label_dir = root / "labels" / split
    image_files = sorted_images(image_dir)
    label_files = sorted(label_dir.glob("*.txt"))
    image_stems = {p.stem for p in image_files}
    label_stems = {p.stem for p in label_files}
    missing_pairs = []
    for stem in sorted(image_stems - label_stems):
        missing_pairs.append({"split": split, "stem": stem, "missing": "label"})
    for stem in sorted(label_stems - image_stems):
        missing_pairs.append({"split": split, "stem": stem, "missing": "image"})

    class_counts = {}
    invalid = []
    non_empty = 0
    empty = 0
    instances = 0
    areas = []
    widths_640 = []
    heights_640 = []
    widths_1280 = []
    heights_1280 = []
    for label_path in label_files:
        text = label_path.read_text(encoding="utf-8").strip()
        if not text:
            empty += 1
            continue
        non_empty += 1
        for lineno, line in enumerate(text.splitlines(), start=1):
            parts = line.split()
            if len(parts) != 5:
                invalid.append({"label": str(label_path), "line": lineno, "error": "expected 5 fields"})
                continue
            try:
                class_id = int(float(parts[0]))
                x, y, w, h = [float(v) for v in parts[1:]]
            except ValueError:
                invalid.append({"label": str(label_path), "line": lineno, "error": "non-numeric field"})
                continue
            if class_id != 0:
                invalid.append({"label": str(label_path), "line": lineno, "error": "class id is not 0"})
            if not all(0.0 <= v <= 1.0 for v in [x, y, w, h]):
                invalid.append({"label": str(label_path), "line": lineno, "error": "bbox outside 0-1"})
            instances += 1
            class_counts[str(class_id)] = class_counts.get(str(class_id), 0) + 1
            areas.append(w * h)
            widths_640.append(w * 640)
            heights_640.append(h * 640)
            widths_1280.append(w * 1280)
            heights_1280.append(h * 1280)

    return {
        "image_count": len(image_files),
        "label_count": len(label_files),
        "defect_image_count": non_empty,
        "background_empty_label_count": empty,
        "defect_instance_count": instances,
        "synthetic_image_count": sum(1 for p in image_files if p.stem.startswith("synth_")),
        "real_image_count": sum(1 for p in image_files if p.stem.startswith("real_")),
        "class_id_distribution": class_counts,
        "missing_pairs": missing_pairs,
        "invalid_labels": invalid,
        "bbox_stats": {
            "area_ratio": summarize(areas),
            "imgsz_640": {"width_px": summarize(widths_640), "height_px": summarize(heights_640)},
            "imgsz_1280": {"width_px": summarize(widths_1280), "height_px": summarize(heights_1280)},
        },
    }


def summarize(values):
    if not values:
        return {"mean": None, "min": None, "max": None}
    return {
        "mean": round(sum(values) / len(values), 8),
        "min": round(min(values), 8),
        "max": round(max(values), 8),
    }


def write_report(path, summary):
    lines = [
        "# Three-Way Dataset Preparation Report",
        "",
        "## Purpose",
        "",
        "Prepare controlled YOLO datasets for a three-way augmentation experiment: real-only, real plus default synthetic count20, and real plus fitted_v2 synthetic count20. No training is run in this step.",
        "",
        "## Inputs",
        "",
        "- Real YAML: `{0}`".format(summary["inputs"]["real_yaml"]),
        "- Default synthetic: `{0}`".format(summary["inputs"]["default_synthetic"]),
        "- Fitted V2 synthetic: `{0}`".format(summary["inputs"]["fitted_synthetic"]),
        "",
        "## Class Name Note",
        "",
        summary["class_name_alias_note"],
        "",
        "Prepared YAMLs use class id `0` with name `{0}`.".format(summary["class_name"]),
        "",
        "## Variant Summary",
        "",
        "| Variant | Train images | Val images | Test images | Train instances | Val instances | Test instances | Train backgrounds | Synthetic only train | Passed |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for key, item in summary["variants"].items():
        audit = item["audit"]
        train = audit["splits"]["train"]
        val = audit["splits"]["val"]
        test = audit["splits"]["test"]
        lines.append(
            "| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} | {8} | {9} |".format(
                key,
                train["image_count"],
                val["image_count"],
                test["image_count"],
                train["defect_instance_count"],
                val["defect_instance_count"],
                test["defect_instance_count"],
                train["background_empty_label_count"],
                audit["synthetic_only_in_train"],
                audit["passed"],
            )
        )
    lines += [
        "",
        "## BBox Size Statistics",
        "",
    ]
    for key, item in summary["variants"].items():
        lines += [
            "### {0}".format(key),
            "",
            "| Split | Width mean @640 | Height mean @640 | Width mean @1280 | Height mean @1280 | Area mean |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
        for split in ["train", "val", "test"]:
            stats = item["audit"]["splits"][split]["bbox_stats"]
            lines.append(
                "| {0} | {1} | {2} | {3} | {4} | {5} |".format(
                    split,
                    stats["imgsz_640"]["width_px"]["mean"],
                    stats["imgsz_640"]["height_px"]["mean"],
                    stats["imgsz_1280"]["width_px"]["mean"],
                    stats["imgsz_1280"]["height_px"]["mean"],
                    stats["area_ratio"]["mean"],
                )
            )
        lines.append("")
    lines += [
        "## Audit Notes",
        "",
        "- Synthetic images are added only to the training split for B and C.",
        "- Validation and test splits are identical real-image splits across A, B, and C.",
        "- This experiment tests real-data augmentation, not synthetic-only transfer.",
        "- Real defects are extremely small at `imgsz=640`; `imgsz=1280` is recommended to reduce tiny-object risk.",
        "- The fixed real test set has only 16 images and 8 defect instances, so results should be interpreted as preliminary trends, not statistically strong proof.",
        "- Fitted V2 had a higher ROI v3 material score in image-level evaluation, but also higher defect visibility proxy; detector changes may reflect both material difference and defect visibility difference.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_training_commands(path, variants):
    project = PROJECT_ROOT / "outputs" / "training" / "three_way_real_synthetic_ablation" / "runs"
    data_root = PROJECT_ROOT / "outputs" / "training" / "three_way_real_synthetic_ablation" / "data"
    lines = [
        "# Training And Validation Command Templates",
        "",
        "These commands are templates only. Do not run them during dataset preparation.",
        "",
        "## Caution Notes",
        "",
        "- This experiment tests real-data augmentation, not synthetic-only transfer.",
        "- Real defects are extremely small at `imgsz=640`; use `imgsz=1280` as the main setting.",
        "- The fixed real test set has only 16 images and 8 defect instances, so results are preliminary trends, not strong statistical proof.",
        "- Fitted V2 has higher image-level material score but also higher defect visibility proxy, so detector changes may reflect both material difference and defect visibility difference.",
        "- Recommended GPU setting for the 8 GB RTX 3070 Laptop GPU: start with `batch=1`; try `batch=2` only if memory is stable.",
        "",
        "## Main Training Commands: imgsz=1280",
        "",
    ]
    for variant in variants:
        name = variant["key"] + "_yolov8n_imgsz1280_seed0"
        lines += [
            "### {0}".format(variant["key"]),
            "",
            "```powershell",
            "$env:YOLO_CONFIG_DIR='E:\\BlenderProject\\Ultralytics'",
            "& 'D:\\Anaconda\\envs\\defect_eval\\Scripts\\yolo.exe' detect train model=E:\\BlenderProject\\yolov8n.pt data='{0}' epochs=100 imgsz=1280 batch=1 patience=20 project='{1}' name='{2}' seed=0 device=0 workers=0".format(data_root / (variant["key"] + ".yaml"), project, name),
            "```",
            "",
        ]
    lines += [
        "## Secondary Comparison Commands: imgsz=640",
        "",
    ]
    for variant in variants:
        name = variant["key"] + "_yolov8n_imgsz640_seed0"
        lines += [
            "### {0}".format(variant["key"]),
            "",
            "```powershell",
            "$env:YOLO_CONFIG_DIR='E:\\BlenderProject\\Ultralytics'",
            "& 'D:\\Anaconda\\envs\\defect_eval\\Scripts\\yolo.exe' detect train model=E:\\BlenderProject\\yolov8n.pt data='{0}' epochs=100 imgsz=640 batch=4 patience=20 project='{1}' name='{2}' seed=0 device=0 workers=0".format(data_root / (variant["key"] + ".yaml"), project, name),
            "```",
            "",
        ]
    lines += [
        "## Fixed Real Test Validation Templates",
        "",
    ]
    for variant in variants:
        run_name = variant["key"] + "_yolov8n_imgsz1280_seed0"
        lines += [
            "### {0}".format(variant["key"]),
            "",
            "```powershell",
            "$env:YOLO_CONFIG_DIR='E:\\BlenderProject\\Ultralytics'",
            "& 'D:\\Anaconda\\envs\\defect_eval\\Scripts\\yolo.exe' detect val model='{0}\\{1}\\weights\\best.pt' data='{2}' split=test imgsz=1280 batch=1 device=0 workers=0 project='{0}' name='{1}_real_test_val'".format(project, run_name, data_root / (variant["key"] + ".yaml")),
            "```",
            "",
        ]
    lines += [
        "## Low-Confidence Real Test Prediction Templates",
        "",
    ]
    for variant in variants:
        run_name = variant["key"] + "_yolov8n_imgsz1280_seed0"
        lines += [
            "### {0}".format(variant["key"]),
            "",
            "```powershell",
            "$env:YOLO_CONFIG_DIR='E:\\BlenderProject\\Ultralytics'",
            "& 'D:\\Anaconda\\envs\\defect_eval\\Scripts\\yolo.exe' detect predict model='{0}\\{1}\\weights\\best.pt' source='{2}\\{3}\\images\\test' imgsz=1280 conf=0.001 save=True save_txt=True save_conf=True device=0 workers=0 project='{0}' name='{1}_real_test_lowconf'".format(project, run_name, data_root, variant["key"]),
            "```",
            "",
        ]
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
