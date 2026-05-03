"""Compare real and synthetic black-dot bbox size distributions.

This is a lightweight diagnostic. It does not render images, train YOLO, or
modify datasets. It only reads YOLO labels and matching images.
"""

import argparse
import json
import statistics
from pathlib import Path
from typing import Optional

from PIL import Image


IMAGE_EXTS = [".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose real/synthetic black-dot bbox size gap.")
    parser.add_argument("--real-images", required=True)
    parser.add_argument("--real-labels", required=True)
    parser.add_argument("--default-synth", required=True)
    parser.add_argument("--fitted-synth", required=True)
    parser.add_argument("--backend-script", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--imgsz", type=int, default=1280)
    return parser.parse_args()


def find_image(image_dir: Path, stem: str) -> Optional[Path]:
    for ext in IMAGE_EXTS:
        candidate = image_dir / f"{stem}{ext}"
        if candidate.exists():
            return candidate
    return None


def read_yolo_labels(label_path: Path):
    rows = []
    if not label_path.exists():
        return rows
    text = label_path.read_text(encoding="utf-8").strip()
    if not text:
        return rows
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 5:
            continue
        class_id = int(float(parts[0]))
        x, y, w, h = [float(value) for value in parts[1:]]
        rows.append((class_id, x, y, w, h))
    return rows


def collect_yolo_dataset(image_dir: Path, label_dir: Path, source_name: str, imgsz: int) -> dict:
    samples = []
    missing_images = []
    invalid_rows = []
    for label_path in sorted(label_dir.glob("*.txt")):
        image_path = find_image(image_dir, label_path.stem)
        if image_path is None:
            missing_images.append(str(label_path))
            continue
        with Image.open(image_path) as image:
            width, height = image.size
        for row_index, row in enumerate(read_yolo_labels(label_path)):
            class_id, _x, _y, w, h = row
            if class_id != 0 or not all(0.0 <= value <= 1.0 for value in [w, h]):
                invalid_rows.append({"label": str(label_path), "row": row_index, "row_value": row})
                continue
            samples.append(
                {
                    "source": source_name,
                    "label": str(label_path),
                    "image": str(image_path),
                    "image_width": width,
                    "image_height": height,
                    "bbox_width_norm": w,
                    "bbox_height_norm": h,
                    "bbox_area_norm": w * h,
                    "bbox_width_original_px": w * width,
                    "bbox_height_original_px": h * height,
                    "bbox_area_original_px": w * h * width * height,
                    "bbox_width_at_imgsz": w * imgsz,
                    "bbox_height_at_imgsz": h * imgsz,
                    "bbox_area_at_imgsz": w * h * imgsz * imgsz,
                }
            )
    return {
        "source": source_name,
        "image_dir": str(image_dir),
        "label_dir": str(label_dir),
        "instance_count": len(samples),
        "missing_images": missing_images,
        "invalid_rows": invalid_rows,
        "samples": samples,
        "summary": summarize_samples(samples),
    }


def collect_framework_synth(root: Path, source_name: str, imgsz: int) -> dict:
    return collect_yolo_dataset(root / "rgb", root / "labels_yolo", source_name, imgsz)


def summarize(values) -> dict:
    if not values:
        return {"count": 0, "mean": None, "std": None, "min": None, "p25": None, "median": None, "p75": None, "max": None}
    values = sorted(values)
    return {
        "count": len(values),
        "mean": round(statistics.mean(values), 8),
        "std": round(statistics.pstdev(values), 8) if len(values) > 1 else 0.0,
        "min": round(values[0], 8),
        "p25": round(percentile(values, 0.25), 8),
        "median": round(percentile(values, 0.50), 8),
        "p75": round(percentile(values, 0.75), 8),
        "max": round(values[-1], 8),
    }


def percentile(sorted_values, q: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def summarize_samples(samples) -> dict:
    fields = [
        "bbox_width_norm",
        "bbox_height_norm",
        "bbox_area_norm",
        "bbox_width_original_px",
        "bbox_height_original_px",
        "bbox_area_original_px",
        "bbox_width_at_imgsz",
        "bbox_height_at_imgsz",
        "bbox_area_at_imgsz",
    ]
    return {field: summarize([float(sample[field]) for sample in samples]) for field in fields}


def extract_backend_size_notes(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    notes = {}
    for line in text.splitlines():
        stripped = line.strip()
        if '"QC71336_white"' in stripped:
            notes["model_profile_line"] = stripped
        if '"radius_scale": (0.0034, 0.0060)' in stripped:
            notes["qc71336_white_radius_scale"] = [0.0034, 0.0060]
        if '"depth_scale": (0.00110, 0.00210)' in stripped:
            notes["qc71336_white_depth_scale"] = [0.00110, 0.00210]
        if "black_dot_radius_min_scale" in stripped:
            notes["radius_override_cli_available"] = True
        if "black_dot_depth_min_scale" in stripped:
            notes["depth_override_cli_available"] = True
    return notes


def ratio_or_none(a, b):
    if a is None or b in (None, 0):
        return None
    return round(a / b, 6)


def compare_to_real(real: dict, other: dict) -> dict:
    real_summary = real["summary"]
    other_summary = other["summary"]
    comparisons = {}
    for field in ["bbox_width_at_imgsz", "bbox_height_at_imgsz", "bbox_area_at_imgsz", "bbox_area_norm"]:
        comparisons[field] = {
            "real_mean": real_summary[field]["mean"],
            "other_mean": other_summary[field]["mean"],
            "other_over_real_mean": ratio_or_none(other_summary[field]["mean"], real_summary[field]["mean"]),
            "real_median": real_summary[field]["median"],
            "other_median": other_summary[field]["median"],
            "other_over_real_median": ratio_or_none(other_summary[field]["median"], real_summary[field]["median"]),
        }
    return comparisons


def write_report(path: Path, payload: dict) -> None:
    real = payload["datasets"]["real_white"]
    default = payload["datasets"]["default_synth"]
    fitted = payload["datasets"]["fitted_synth"]
    lines = [
        "# Black-Spot Size Gap Diagnosis",
        "",
        "## Purpose",
        "",
        "Compare white real QC71336 black-dot YOLO label sizes with the existing default-material and fitted_v2 synthetic count20 datasets.",
        "",
        "This is a diagnostic image-label analysis only. It does not prove detection performance and does not modify datasets.",
        "",
        "## Inputs",
        "",
        f"- Real images: `{real['image_dir']}`",
        f"- Real labels: `{real['label_dir']}`",
        f"- Default synthetic labels: `{default['label_dir']}`",
        f"- Fitted synthetic labels: `{fitted['label_dir']}`",
        f"- Comparison imgsz: `{payload['imgsz']}`",
        "",
        "## Backend Size Controls",
        "",
        f"- QC71336 white radius scale: `{payload['backend_notes'].get('qc71336_white_radius_scale')}`",
        f"- QC71336 white depth scale: `{payload['backend_notes'].get('qc71336_white_depth_scale')}`",
        f"- Radius override CLI available: `{payload['backend_notes'].get('radius_override_cli_available', False)}`",
        f"- Depth override CLI available: `{payload['backend_notes'].get('depth_override_cli_available', False)}`",
        "",
        "## Instance Counts",
        "",
        "| Dataset | Instances | Missing images | Invalid rows |",
        "| --- | ---: | ---: | ---: |",
    ]
    for key, dataset in payload["datasets"].items():
        lines.append(
            f"| {key} | {dataset['instance_count']} | {len(dataset['missing_images'])} | {len(dataset['invalid_rows'])} |"
        )
    lines += [
        "",
        "## Size Summary At imgsz",
        "",
        "| Dataset | Width mean px | Width median px | Height mean px | Height median px | Area mean px^2 | Area median px^2 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key, dataset in payload["datasets"].items():
        summary = dataset["summary"]
        lines.append(
            "| {0} | {1} | {2} | {3} | {4} | {5} | {6} |".format(
                key,
                summary["bbox_width_at_imgsz"]["mean"],
                summary["bbox_width_at_imgsz"]["median"],
                summary["bbox_height_at_imgsz"]["mean"],
                summary["bbox_height_at_imgsz"]["median"],
                summary["bbox_area_at_imgsz"]["mean"],
                summary["bbox_area_at_imgsz"]["median"],
            )
        )
    lines += [
        "",
        "## Synthetic Over Real Ratios",
        "",
        "| Dataset | Width mean ratio | Height mean ratio | Area mean ratio | Width median ratio | Height median ratio | Area median ratio |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key in ["default_synth", "fitted_synth"]:
        comparison = payload["comparisons"][key]
        lines.append(
            "| {0} | {1} | {2} | {3} | {4} | {5} | {6} |".format(
                key,
                comparison["bbox_width_at_imgsz"]["other_over_real_mean"],
                comparison["bbox_height_at_imgsz"]["other_over_real_mean"],
                comparison["bbox_area_at_imgsz"]["other_over_real_mean"],
                comparison["bbox_width_at_imgsz"]["other_over_real_median"],
                comparison["bbox_height_at_imgsz"]["other_over_real_median"],
                comparison["bbox_area_at_imgsz"]["other_over_real_median"],
            )
        )
    lines += [
        "",
        "## Diagnosis",
        "",
        "- The black-dot backend uses a model-level radius scale range instead of a real-label-size-calibrated distribution.",
        "- The current synthetic label size is therefore controlled by geometry scale, camera projection, mask rendering, and visibility filtering, not by the white real bbox distribution.",
        "- If synthetic bboxes are substantially larger than real bboxes, the next step should be a small radius-scale calibration smoke test rather than more YOLO training.",
        "",
        "## Recommended Next Step",
        "",
        "Run a count=5 synthetic smoke render with reduced `--black_dot_radius_min_scale` and `--black_dot_radius_max_scale`, then re-run this diagnostic before using the data for training.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    real = collect_yolo_dataset(Path(args.real_images), Path(args.real_labels), "real_white", args.imgsz)
    default = collect_framework_synth(Path(args.default_synth), "default_synth", args.imgsz)
    fitted = collect_framework_synth(Path(args.fitted_synth), "fitted_synth", args.imgsz)

    payload = {
        "schema_version": "0.1",
        "diagnostic_type": "black_spot_size_gap",
        "imgsz": args.imgsz,
        "backend_script": str(Path(args.backend_script)),
        "backend_notes": extract_backend_size_notes(Path(args.backend_script)),
        "datasets": {
            "real_white": real,
            "default_synth": default,
            "fitted_synth": fitted,
        },
        "comparisons": {
            "default_synth": compare_to_real(real, default),
            "fitted_synth": compare_to_real(real, fitted),
        },
    }

    summary_path = out_dir / "black_spot_size_gap_summary.json"
    report_path = out_dir / "BLACK_SPOT_SIZE_GAP_DIAGNOSIS.md"
    summary_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    write_report(report_path, payload)
    print(json.dumps({"status": "completed", "summary": str(summary_path), "report": str(report_path)}, indent=2))


if __name__ == "__main__":
    main()
