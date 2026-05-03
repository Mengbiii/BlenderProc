import argparse
import json
from pathlib import Path

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description="Validate paired black_spot smoke datasets.")
    parser.add_argument("--default-dataset", required=True)
    parser.add_argument("--fitted-dataset", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    default_dir = resolve_path(args.default_dataset)
    fitted_dir = resolve_path(args.fitted_dataset)
    out_dir = resolve_path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    default = validate_dataset(default_dir, default_dir.name)
    fitted = validate_dataset(fitted_dir, fitted_dir.name)
    controlled = compare_pair(default, fitted)
    report = {
        "schema_version": "0.1",
        "validation_type": "black_spot_pair_validation",
        "default_dataset": default,
        "fitted_dataset": fitted,
        "controlled_variables": controlled,
    }
    (out_dir / "smoke_dataset_validation_summary.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_markdown(out_dir / "SMOKE_DATASET_VALIDATION_REPORT.md", report)
    print(json.dumps({"status": "completed", "out": str(out_dir)}, indent=2, ensure_ascii=False))


def resolve_path(value):
    path = Path(value)
    if path.is_absolute():
        return path
    return (PROJECT_ROOT / path).resolve()


def validate_dataset(dataset_dir, name):
    rgb_dir = dataset_dir / "rgb"
    mask_dir = dataset_dir / "masks"
    label_dir = dataset_dir / "labels_yolo"
    metadata_dir = dataset_dir / "metadata"
    summary = read_json(dataset_dir / "dataset_summary.json")
    rgb_files = sorted(rgb_dir.glob("*.png"))
    mask_files = sorted(mask_dir.glob("*.png"))
    label_files = sorted(label_dir.glob("*.txt"))
    metadata_files = sorted([p for p in metadata_dir.glob("*.json") if p.stem.isdigit()])
    failed = []
    sample_checks = []
    for rgb_path in rgb_files:
        sid = rgb_path.stem
        mask_path = mask_dir / (sid + ".png")
        label_path = label_dir / (sid + ".txt")
        metadata_path = metadata_dir / (sid + ".json")
        errors = []
        if not mask_path.exists():
            errors.append("missing mask")
        if not label_path.exists():
            errors.append("missing label")
        if not metadata_path.exists():
            errors.append("missing metadata")
        rgb_size = None
        mask_size = None
        try:
            rgb_size = Image.open(rgb_path).size
        except Exception as exc:
            errors.append("rgb unreadable: {0}".format(exc))
        if mask_path.exists():
            try:
                mask_size = Image.open(mask_path).size
            except Exception as exc:
                errors.append("mask unreadable: {0}".format(exc))
        if rgb_size and mask_size and rgb_size != mask_size:
            errors.append("rgb/mask size mismatch")
        label_text = label_path.read_text(encoding="utf-8").strip() if label_path.exists() else ""
        if not label_text:
            errors.append("empty label")
        bbox_ok = validate_yolo_label(label_text)
        if not bbox_ok:
            errors.append("bbox outside 0-1 or malformed")
        metadata = read_json(metadata_path) if metadata_path.exists() else {}
        item = {
            "sample_id": sid,
            "seed": metadata.get("seed"),
            "label": label_text,
            "passed": not errors,
            "errors": errors,
        }
        sample_checks.append(item)
        if errors:
            failed.append(item)
    return {
        "name": name,
        "dataset_dir": str(dataset_dir),
        "counts": {
            "rgb": len(rgb_files),
            "masks": len(mask_files),
            "labels": len(label_files),
            "metadata": len(metadata_files),
        },
        "dataset_summary": {
            "total_requested": summary.get("total_requested"),
            "total_succeeded": summary.get("total_succeeded"),
            "total_failed": summary.get("total_failed"),
            "seeds_used": summary.get("seeds_used"),
            "backend_script": summary.get("backend_script"),
            "backend_model": summary.get("backend_model"),
            "anchor_side": summary.get("anchor_side"),
            "samples": summary.get("samples"),
            "material_override_applied": summary.get("material_override_applied"),
        },
        "failed_samples_count": len(failed),
        "failed_samples": failed,
        "sample_checks": sample_checks,
    }


def validate_yolo_label(text):
    if not text:
        return False
    parts = text.splitlines()[0].split()
    if len(parts) != 5:
        return False
    try:
        values = [float(v) for v in parts[1:]]
    except ValueError:
        return False
    return all(0.0 <= value <= 1.0 for value in values)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def compare_pair(default, fitted):
    default_ids = [item["sample_id"] for item in default["sample_checks"]]
    fitted_ids = [item["sample_id"] for item in fitted["sample_checks"]]
    default_by_id = {item["sample_id"]: item for item in default["sample_checks"]}
    fitted_by_id = {item["sample_id"]: item for item in fitted["sample_checks"]}
    bbox_differences = []
    seed_differences = []
    for sid in default_ids:
        other = fitted_by_id.get(sid)
        if other is None:
            bbox_differences.append({"sample_id": sid, "reason": "missing fitted sample"})
            continue
        if default_by_id[sid]["label"] != other["label"]:
            bbox_differences.append({"sample_id": sid, "default_label": default_by_id[sid]["label"], "fitted_label": other["label"]})
        if default_by_id[sid]["seed"] != other["seed"]:
            seed_differences.append({"sample_id": sid, "default_seed": default_by_id[sid]["seed"], "fitted_seed": other["seed"]})
    return {
        "matching_filenames": default_ids == fitted_ids,
        "same_counts": default["counts"] == fitted["counts"],
        "same_seeds": len(seed_differences) == 0,
        "same_yolo_labels": len(bbox_differences) == 0,
        "seed_differences": seed_differences,
        "bbox_differences": bbox_differences,
        "only_material_expected_to_differ": default_ids == fitted_ids and default["counts"] == fitted["counts"] and len(seed_differences) == 0 and len(bbox_differences) == 0,
    }


def write_markdown(path, report):
    default = report["default_dataset"]
    fitted = report["fitted_dataset"]
    controlled = report["controlled_variables"]
    requested = default["dataset_summary"].get("total_requested") or default["counts"]["rgb"]
    lines = [
        "# Black Spot Pair Dataset Validation Report",
        "",
        "## Purpose",
        "",
        "Validate paired count={0} black_spot datasets before any larger generation or YOLO training.".format(requested),
        "",
        "## Dataset Counts",
        "",
        "| Dataset | RGB | Masks | Labels | Metadata | Failed samples | Backend failed |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        count_row(default),
        count_row(fitted),
        "",
        "## Controlled Variables",
        "",
        "| Check | Result |",
        "| --- | --- |",
        "| Matching filenames | {0} |".format(controlled["matching_filenames"]),
        "| Same counts | {0} |".format(controlled["same_counts"]),
        "| Same seeds | {0} |".format(controlled["same_seeds"]),
        "| Same YOLO labels / bbox values | {0} |".format(controlled["same_yolo_labels"]),
        "| Only material expected to differ | {0} |".format(controlled["only_material_expected_to_differ"]),
        "",
        "## Notes",
        "",
        "- This validation checks file integrity, label format, bbox range, RGB/mask size match, seed matching, and paired label matching.",
        "- It does not evaluate detector performance.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def count_row(dataset):
    return "| {0} | {1} | {2} | {3} | {4} | {5} | {6} |".format(
        dataset["name"],
        dataset["counts"]["rgb"],
        dataset["counts"]["masks"],
        dataset["counts"]["labels"],
        dataset["counts"]["metadata"],
        dataset["failed_samples_count"],
        dataset["dataset_summary"]["total_failed"],
    )


if __name__ == "__main__":
    main()
