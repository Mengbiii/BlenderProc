"""Build an image-level manifest for the real plastic-part defect dataset."""

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.real_dataset_profiles import (  # noqa: E402
    infer_defect_type_from_folder_name,
    parse_model_appearance_folder_name,
)


PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".JPG", ".JPEG"}
SCHEMA_VERSION = "0.1"


def resolve_path(path_text):
    path = Path(path_text)
    if path.is_absolute():
        return path
    return (PROJECT_ROOT / path).resolve()


def ensure_dir(path):
    path.mkdir(parents=True, exist_ok=True)
    return path


def image_size(path):
    try:
        with Image.open(path) as image:
            return image.size
    except Exception:
        return None, None


def iter_photo_files(root):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in PHOTO_EXTENSIONS:
            continue
        if "标注" in path.name:
            continue
        yield path


def normalize_model_id(model_id):
    return model_id.replace(" ", "").replace("_", "-")


def build_rows(root):
    rows = []
    for image_path in iter_photo_files(root):
        rel_parts = image_path.relative_to(root).parts
        if len(rel_parts) < 3:
            model_folder = rel_parts[0] if rel_parts else ""
            defect_folder = ""
        else:
            model_folder = rel_parts[0]
            defect_folder = rel_parts[1]
        profile = parse_model_appearance_folder_name(model_folder)
        model_id = normalize_model_id(profile["model_id"])
        color = profile["appearance_color"]
        defect_type = infer_defect_type_from_folder_name(defect_folder)
        is_normal = defect_type == "normal"
        width, height = image_size(image_path)
        parse_confidence = "high"
        parse_notes = []
        if color == "unknown":
            parse_confidence = "low"
            parse_notes.append("unknown_color")
        if defect_type == "unknown":
            parse_confidence = "low"
            parse_notes.append("unknown_defect_type")
        if width is None or height is None:
            parse_confidence = "low"
            parse_notes.append("image_open_failed")

        rows.append(
            {
                "sample_id": "real_%06d" % (len(rows) + 1),
                "image_path": str(image_path),
                "relative_path": str(image_path.relative_to(root)),
                "filename": image_path.name,
                "model": model_id,
                "model_folder": model_folder,
                "color": color,
                "defect_folder": defect_folder,
                "defect_type": defect_type,
                "is_normal": "1" if is_normal else "0",
                "usable": "pending_review",
                "view_quality": "unchecked",
                "defect_visibility": "none" if is_normal else "needs_l1_bbox",
                "confidence": parse_confidence,
                "width": width or "",
                "height": height or "",
                "needs_l1_bbox": "0" if is_normal else "1",
                "l1_status": "not_required" if is_normal else "pending",
                "source_root": str(root),
                "parse_notes": ";".join(parse_notes),
            }
        )
    return rows


def write_csv(rows, path):
    fieldnames = [
        "sample_id",
        "image_path",
        "relative_path",
        "filename",
        "model",
        "model_folder",
        "color",
        "defect_folder",
        "defect_type",
        "is_normal",
        "usable",
        "view_quality",
        "defect_visibility",
        "confidence",
        "width",
        "height",
        "needs_l1_bbox",
        "l1_status",
        "source_root",
        "parse_notes",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows):
    by_model_color = Counter((row["model"], row["color"]) for row in rows)
    by_defect = Counter(row["defect_type"] for row in rows)
    by_model_defect = Counter((row["model"], row["color"], row["defect_type"]) for row in rows)
    low_confidence = [row for row in rows if row["confidence"] != "high"]
    l1_pending = [row for row in rows if row["needs_l1_bbox"] == "1"]
    nested = defaultdict(dict)
    for (model, color, defect_type), count in sorted(by_model_defect.items()):
        nested["%s|%s" % (model, color)][defect_type] = count
    return {
        "schema_version": SCHEMA_VERSION,
        "total_photos": len(rows),
        "l1_pending_photos": len(l1_pending),
        "normal_photos": by_defect.get("normal", 0),
        "low_confidence_rows": len(low_confidence),
        "by_defect_type": dict(sorted(by_defect.items())),
        "by_model_color": {"%s|%s" % key: value for key, value in sorted(by_model_color.items())},
        "by_model_color_defect": dict(sorted(nested.items())),
    }


def write_l1_queue(rows, path):
    queue_rows = [row for row in rows if row["needs_l1_bbox"] == "1"]
    write_csv(queue_rows, path)


def build_arg_parser():
    parser = argparse.ArgumentParser(description="Build L0 manifest for the real defect dataset.")
    parser.add_argument("--real-root", required=True, help="Real dataset root.")
    parser.add_argument("--out-dir", required=True, help="Output directory.")
    return parser


def main():
    args = build_arg_parser().parse_args()
    root = resolve_path(args.real_root)
    out_dir = ensure_dir(resolve_path(args.out_dir))
    rows = build_rows(root)
    write_csv(rows, out_dir / "manifest_l0.csv")
    write_l1_queue(rows, out_dir / "l1_bbox_queue.csv")
    summary = summarize(rows)
    (out_dir / "manifest_l0_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("Wrote %s rows to %s" % (len(rows), out_dir / "manifest_l0.csv"))
    print("L1 bbox queue: %s rows" % summary["l1_pending_photos"])
    print("Low-confidence rows: %s" % summary["low_confidence_rows"])


if __name__ == "__main__":
    main()
