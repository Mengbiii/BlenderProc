import argparse
import json
from pathlib import Path

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


def main():
    parser = argparse.ArgumentParser(description="Audit a YOLO dataset YAML split and labels.")
    parser.add_argument("--yaml", required=True, help="YOLO data.yaml path")
    parser.add_argument("--split", default="test", choices=["train", "val", "test"])
    parser.add_argument("--out", required=True, help="Output audit folder")
    parser.add_argument("--expected-class-name", default="black_spot")
    parser.add_argument("--imgsz", type=int, default=640)
    args = parser.parse_args()

    yaml_path = resolve_path(args.yaml)
    out_dir = resolve_path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    config = parse_simple_yaml(yaml_path)
    audit = audit_yolo_split(
        yaml_path=yaml_path,
        config=config,
        split=args.split,
        expected_class_name=args.expected_class_name,
        imgsz=args.imgsz,
    )

    (out_dir / "data_yaml_label_audit_summary.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_markdown(out_dir / "DATA_YAML_AND_LABEL_AUDIT.md", audit)
    print(json.dumps({"status": "completed", "out": str(out_dir), "blocking_errors": audit["blocking_errors"]}, indent=2))


def resolve_path(value):
    path = Path(value)
    if path.is_absolute():
        return path
    project_path = (PROJECT_ROOT / path).resolve()
    if project_path.exists():
        return project_path
    return (PROJECT_ROOT.parent / path).resolve()


def parse_simple_yaml(path):
    # Tiny parser for the simple YOLO YAML files used in this project.
    data = {"names": {}}
    in_names = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
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


def audit_yolo_split(yaml_path, config, split, expected_class_name, imgsz):
    dataset_root = resolve_dataset_root(yaml_path, config)
    split_value = config.get(split)
    split_dir = resolve_split_path(dataset_root, split_value)
    label_dir = image_dir_to_label_dir(split_dir)
    image_files = sorted([p for p in split_dir.glob("*") if p.suffix.lower() in IMAGE_EXTS]) if split_dir.exists() else []
    label_files = sorted(label_dir.glob("*.txt")) if label_dir.exists() else []

    names = config.get("names", {})
    expected_name_match = names.get(0) == expected_class_name
    acceptable_alias = names.get(0) in {expected_class_name, "black_dot"}

    sample_rows = []
    class_ids = {}
    invalid_labels = []
    missing_labels = []
    non_empty_labels = 0
    empty_labels = 0
    bbox_areas = []
    bbox_width_px = []
    bbox_height_px = []
    tiny_boxes = 0

    for image_path in image_files:
        label_path = label_dir / (image_path.stem + ".txt")
        row = {
            "image": str(image_path),
            "label": str(label_path),
            "label_exists": label_path.exists(),
            "label_empty": True,
            "errors": [],
            "boxes": [],
        }
        if not label_path.exists():
            missing_labels.append(str(label_path))
            row["errors"].append("missing label file")
            sample_rows.append(row)
            continue

        text = label_path.read_text(encoding="utf-8").strip()
        if not text:
            empty_labels += 1
            sample_rows.append(row)
            continue

        non_empty_labels += 1
        row["label_empty"] = False
        for lineno, line in enumerate(text.splitlines(), start=1):
            parts = line.split()
            if len(parts) != 5:
                error = "line {0}: expected 5 fields".format(lineno)
                row["errors"].append(error)
                invalid_labels.append({"label": str(label_path), "error": error})
                continue
            try:
                class_id = int(float(parts[0]))
                x, y, w, h = [float(v) for v in parts[1:]]
            except ValueError:
                error = "line {0}: non-numeric field".format(lineno)
                row["errors"].append(error)
                invalid_labels.append({"label": str(label_path), "error": error})
                continue
            class_ids[str(class_id)] = class_ids.get(str(class_id), 0) + 1
            if class_id != 0:
                row["errors"].append("line {0}: class id is not 0".format(lineno))
            if not all(0.0 <= v <= 1.0 for v in [x, y, w, h]):
                row["errors"].append("line {0}: bbox value outside 0-1".format(lineno))
            area = w * h
            width_px = w * imgsz
            height_px = h * imgsz
            if width_px < 3.0 or height_px < 3.0:
                tiny_boxes += 1
            bbox_areas.append(area)
            bbox_width_px.append(width_px)
            bbox_height_px.append(height_px)
            row["boxes"].append({"class_id": class_id, "x": x, "y": y, "w": w, "h": h, "area_ratio": area, "width_px_at_imgsz": width_px, "height_px_at_imgsz": height_px})
        if row["errors"]:
            invalid_labels.append({"label": str(label_path), "errors": row["errors"]})
        sample_rows.append(row)

    unmatched_labels = sorted(str(p) for p in label_files if not (split_dir / (p.stem + ".jpg")).exists() and not any((split_dir / (p.stem + ext)).exists() for ext in IMAGE_EXTS))
    blocking_errors = []
    if not yaml_path.exists():
        blocking_errors.append("YAML path does not exist")
    if not dataset_root.exists():
        blocking_errors.append("dataset root does not exist")
    if not split_dir.exists():
        blocking_errors.append("{0} image path does not exist".format(split))
    if not label_dir.exists():
        blocking_errors.append("{0} label path does not exist".format(split))
    if invalid_labels:
        blocking_errors.append("invalid labels found")
    if not acceptable_alias:
        blocking_errors.append("class 0 name is not black_spot or accepted alias black_dot")

    return {
        "schema_version": "0.1",
        "audit_type": "yolo_yaml_label_audit",
        "yaml_path": str(yaml_path),
        "dataset_root": str(dataset_root),
        "split": split,
        "image_dir": str(split_dir),
        "label_dir": str(label_dir),
        "names": names,
        "expected_class_name": expected_class_name,
        "class_name_exact_match": expected_name_match,
        "class_name_accepted_alias": acceptable_alias,
        "counts": {
            "images": len(image_files),
            "labels": len(label_files),
            "non_empty_labels": non_empty_labels,
            "empty_labels": empty_labels,
            "missing_labels": len(missing_labels),
            "unmatched_labels": len(unmatched_labels),
            "invalid_label_files": len(invalid_labels),
        },
        "class_ids": class_ids,
        "bbox_stats": summarize_bbox(bbox_areas, bbox_width_px, bbox_height_px, tiny_boxes),
        "missing_labels": missing_labels[:50],
        "unmatched_labels": unmatched_labels[:50],
        "invalid_labels": invalid_labels[:50],
        "blocking_errors": blocking_errors,
        "samples": sample_rows,
    }


def resolve_dataset_root(yaml_path, config):
    root = Path(config.get("path", ""))
    if root.is_absolute():
        return root
    return (yaml_path.parent / root).resolve()


def resolve_split_path(dataset_root, split_value):
    split_path = Path(split_value or "")
    if split_path.is_absolute():
        return split_path
    return (dataset_root / split_path).resolve()


def image_dir_to_label_dir(image_dir):
    parts = list(image_dir.parts)
    for i, part in enumerate(parts):
        if part == "images":
            parts[i] = "labels"
            return Path(*parts)
    return image_dir.parent.parent / "labels" / image_dir.name


def summarize(values):
    if not values:
        return {"mean": None, "min": None, "max": None}
    return {
        "mean": round(sum(values) / len(values), 8),
        "min": round(min(values), 8),
        "max": round(max(values), 8),
    }


def summarize_bbox(areas, widths, heights, tiny_boxes):
    return {
        "area_ratio": summarize(areas),
        "width_px_at_imgsz": summarize(widths),
        "height_px_at_imgsz": summarize(heights),
        "tiny_box_count_lt_3px_width_or_height": tiny_boxes,
    }


def write_markdown(path, audit):
    lines = [
        "# Data YAML And Label Audit",
        "",
        "## Inputs",
        "",
        "- YAML: `{0}`".format(audit["yaml_path"]),
        "- Split: `{0}`".format(audit["split"]),
        "- Image dir: `{0}`".format(audit["image_dir"]),
        "- Label dir: `{0}`".format(audit["label_dir"]),
        "",
        "## Class Configuration",
        "",
        "- names: `{0}`".format(audit["names"]),
        "- Expected class 0 name: `{0}`".format(audit["expected_class_name"]),
        "- Exact name match: `{0}`".format(audit["class_name_exact_match"]),
        "- Accepted alias match: `{0}`".format(audit["class_name_accepted_alias"]),
        "",
        "## Counts",
        "",
        "| Item | Count |",
        "| --- | ---: |",
    ]
    for key, value in audit["counts"].items():
        lines.append("| {0} | {1} |".format(key, value))
    stats = audit["bbox_stats"]
    lines += [
        "",
        "## BBox Statistics",
        "",
        "| Metric | Mean | Min | Max |",
        "| --- | ---: | ---: | ---: |",
        stat_row("area_ratio", stats["area_ratio"]),
        stat_row("width_px_at_imgsz", stats["width_px_at_imgsz"]),
        stat_row("height_px_at_imgsz", stats["height_px_at_imgsz"]),
        "",
        "- Tiny boxes at imgsz threshold: `{0}`".format(stats["tiny_box_count_lt_3px_width_or_height"]),
        "",
        "## Blocking Errors",
        "",
    ]
    if audit["blocking_errors"]:
        lines += ["- {0}".format(item) for item in audit["blocking_errors"]]
    else:
        lines.append("- None")
    lines += [
        "",
        "## Notes",
        "",
        "- `black_dot` is treated as an accepted alias for `black_spot`, but the naming mismatch is recorded.",
        "- This audit checks data validity only; it does not train or evaluate a detector.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def stat_row(name, values):
    return "| {0} | {1} | {2} | {3} |".format(name, values["mean"], values["min"], values["max"])


if __name__ == "__main__":
    main()
