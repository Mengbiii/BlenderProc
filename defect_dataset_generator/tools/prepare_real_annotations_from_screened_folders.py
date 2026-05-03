"""Prepare real-image annotation manifests from screened defect folders.

Folder policy:
- normal folders contain clean normal photos and need no bbox.
- defect folders with "带标注" contain manually red-boxed annotation photos.
- sibling defect folders without "带标注" contain clean originals.
- clean defect photos with no matching red-box annotation are low-confidence samples.
"""

import argparse
import csv
import json
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.real_dataset_profiles import (  # noqa: E402
    infer_defect_type_from_folder_name,
    parse_model_appearance_folder_name,
)


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".JPG", ".JPEG"}
ANNOTATION_MARKERS = ("带标注", "標注", "标注")
CLASS_MAP = {
    "black_dot": 0,
    "foreign_material": 1,
    "splay": 2,
    "mixed_color_contamination": 3,
}
SCHEMA_VERSION = "0.1"


def resolve_path(path_text):
    path = Path(path_text)
    if path.is_absolute():
        return path
    return (PROJECT_ROOT / path).resolve()


def ensure_dirs(root):
    for rel in [
        "images/high_conf",
        "labels_yolo/high_conf",
        "previews/high_conf",
        "manifests",
        "audits",
    ]:
        (root / rel).mkdir(parents=True, exist_ok=True)


def is_annotation_folder(path):
    return any(marker in path.name for marker in ANNOTATION_MARKERS)


def iter_images(folder):
    return sorted([p for p in folder.iterdir() if p.is_file() and p.suffix in IMAGE_EXTENSIONS])


def read_bgr(path):
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def detect_red_bboxes(image_path):
    bgr = read_bgr(image_path)
    if bgr is None:
        return [], {"reason": "image_read_failed"}
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    lower1 = np.array([0, 70, 70], dtype=np.uint8)
    upper1 = np.array([14, 255, 255], dtype=np.uint8)
    lower2 = np.array([164, 70, 70], dtype=np.uint8)
    upper2 = np.array([180, 255, 255], dtype=np.uint8)
    mask = cv2.inRange(hsv, lower1, upper1) | cv2.inRange(hsv, lower2, upper2)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = mask.shape[:2]
    image_area = float(w * h)
    candidates = []
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        contour_area = float(cv2.contourArea(contour))
        bbox_area = float(bw * bh)
        if contour_area < 8.0 or bw < 4 or bh < 4:
            continue
        if bbox_area > image_area * 0.30:
            continue
        rectangularity = contour_area / max(bbox_area, 1.0)
        edge_like = cv2.arcLength(contour, True) / max(np.sqrt(bbox_area), 1.0)
        if edge_like < 2.0:
            continue
        score = min(bbox_area, 12000.0) + min(edge_like, 30.0) * 40.0 - rectangularity * 180.0
        candidates.append(
            {
                "bbox_xyxy": [int(x), int(y), int(x + bw), int(y + bh)],
                "bbox_area": bbox_area,
                "contour_area": contour_area,
                "rectangularity": rectangularity,
                "edge_like": float(edge_like),
                "score": float(score),
            }
        )
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return merge_overlapping_boxes(candidates), {"image_size": [w, h], "raw_candidate_count": len(candidates)}


def merge_overlapping_boxes(candidates):
    merged = []
    for candidate in candidates:
        box = candidate["bbox_xyxy"]
        matched = False
        for existing in merged:
            if iou(box, existing["bbox_xyxy"]) > 0.25:
                existing["bbox_xyxy"] = union_box(box, existing["bbox_xyxy"])
                existing["score"] = max(existing["score"], candidate["score"])
                matched = True
                break
        if not matched:
            merged.append(dict(candidate))
    merged.sort(key=lambda item: item["score"], reverse=True)
    return merged


def iou(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    if inter <= 0:
        return 0.0
    area_a = max(1, ax1 - ax0) * max(1, ay1 - ay0)
    area_b = max(1, bx1 - bx0) * max(1, by1 - by0)
    return inter / float(area_a + area_b - inter)


def union_box(a, b):
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]


def bbox_to_yolo(class_id, bbox, width, height):
    x0, y0, x1, y1 = bbox
    bw = max(1.0, float(x1 - x0))
    bh = max(1.0, float(y1 - y0))
    cx = float(x0 + x1) / 2.0
    cy = float(y0 + y1) / 2.0
    return [class_id, cx / float(width), cy / float(height), bw / float(width), bh / float(height)]


def image_size(path):
    with Image.open(path) as image:
        return image.size


def save_preview(clean_path, boxes, out_path):
    image = Image.open(clean_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    for box in boxes:
        draw.rectangle(box, outline=(255, 0, 0), width=4)
    image.save(out_path, quality=92)


def normalize_model_id(model_id):
    return model_id.replace(" ", "").replace("_", "-")


def collect_folders(root):
    model_entries = []
    for model_dir in sorted([p for p in root.iterdir() if p.is_dir()]):
        profile = parse_model_appearance_folder_name(model_dir.name)
        model = normalize_model_id(profile["model_id"])
        color = profile["appearance_color"]
        child_entries = []
        for child in sorted([p for p in model_dir.iterdir() if p.is_dir()]):
            defect_type = infer_defect_type_from_folder_name(child.name)
            child_entries.append(
                {
                    "path": child,
                    "folder": child.name,
                    "defect_type": defect_type,
                    "is_annotation": is_annotation_folder(child),
                }
            )
        model_entries.append({"path": model_dir, "folder": model_dir.name, "model": model, "color": color, "children": child_entries})
    return model_entries


def build_clean_index(children):
    index = defaultdict(list)
    normal_images = []
    for child in children:
        if child["is_annotation"]:
            continue
        defect_type = child["defect_type"]
        for image_path in iter_images(child["path"]):
            record = {
                "path": image_path,
                "folder": child["folder"],
                "defect_type": defect_type,
            }
            if defect_type == "normal":
                normal_images.append(record)
            elif defect_type in CLASS_MAP:
                index[(defect_type, image_path.stem)].append(record)
    return index, normal_images


def collect_annotation_images(children):
    records = []
    for child in children:
        if not child["is_annotation"]:
            continue
        defect_type = child["defect_type"]
        if defect_type not in CLASS_MAP:
            continue
        for image_path in iter_images(child["path"]):
            records.append(
                {
                    "path": image_path,
                    "folder": child["folder"],
                    "defect_type": defect_type,
                }
            )
    return records


def make_sample_id(prefix, index):
    return "%s_%06d" % (prefix, index)


def write_csv(rows, path):
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def prepare(root, out_dir, copy_images=True, save_previews=True, allow_multiple_bboxes=False):
    ensure_dirs(out_dir)
    folder_profiles = collect_folders(root)
    high_rows = []
    low_rows = []
    normal_rows = []
    annotation_without_clean = []
    redbox_review = []
    used_clean_paths = set()
    sample_rows = []
    high_index = 0
    low_index = 0
    normal_index = 0

    for model_entry in folder_profiles:
        clean_index, normal_images = build_clean_index(model_entry["children"])
        annotation_images = collect_annotation_images(model_entry["children"])

        for normal in normal_images:
            normal_index += 1
            width, height = image_size(normal["path"])
            row = base_row(
                make_sample_id("normal", normal_index),
                model_entry,
                normal["folder"],
                normal["path"],
                "normal",
                width,
                height,
            )
            row.update(
                {
                    "split_role": "normal_material_reference",
                    "is_normal": "1",
                    "usable": "yes",
                    "view_quality": "unchecked",
                    "defect_visibility": "none",
                    "coverage": "none",
                    "confidence": "high",
                    "l1_status": "not_required",
                }
            )
            normal_rows.append(row)
            sample_rows.append(row)

        for ann in annotation_images:
            matches = clean_index.get((ann["defect_type"], ann["path"].stem), [])
            if not matches:
                annotation_without_clean.append(
                    {
                        "model": model_entry["model"],
                        "color": model_entry["color"],
                        "defect_type": ann["defect_type"],
                        "annotation_path": str(ann["path"]),
                        "annotation_folder": ann["folder"],
                    }
                )
                continue
            clean = matches[0]
            used_clean_paths.add(str(clean["path"]))
            high_index += 1
            sample_id = make_sample_id("l1", high_index)
            clean_width, clean_height = image_size(clean["path"])
            ann_width, ann_height = image_size(ann["path"])
            boxes, debug = detect_red_bboxes(ann["path"])
            selected_boxes = boxes if allow_multiple_bboxes else boxes[:1]
            scaled_boxes = []
            for item in selected_boxes:
                x0, y0, x1, y1 = item["bbox_xyxy"]
                scaled_boxes.append(
                    [
                        int(round(x0 * clean_width / float(ann_width))),
                        int(round(y0 * clean_height / float(ann_height))),
                        int(round(x1 * clean_width / float(ann_width))),
                        int(round(y1 * clean_height / float(ann_height))),
                    ]
                )

            label_path = out_dir / "labels_yolo" / "high_conf" / ("%s.txt" % sample_id)
            image_output_path = out_dir / "images" / "high_conf" / ("%s%s" % (sample_id, clean["path"].suffix))
            preview_path = out_dir / "previews" / "high_conf" / ("%s.jpg" % sample_id)
            class_id = CLASS_MAP[ann["defect_type"]]
            yolo_lines = []
            for box in scaled_boxes:
                yolo = bbox_to_yolo(class_id, box, clean_width, clean_height)
                yolo_lines.append("%d %.6f %.6f %.6f %.6f" % tuple(yolo))
            label_path.write_text("\n".join(yolo_lines) + ("\n" if yolo_lines else ""), encoding="utf-8")
            if save_previews:
                save_preview(clean["path"], scaled_boxes, preview_path)
            if copy_images:
                shutil.copy2(clean["path"], image_output_path)

            row = base_row(sample_id, model_entry, clean["folder"], clean["path"], ann["defect_type"], clean_width, clean_height)
            row.update(
                {
                    "split_role": "high_conf_l1",
                    "is_normal": "0",
                    "usable": "yes" if scaled_boxes else "needs_review",
                    "view_quality": "unchecked",
                    "defect_visibility": "clear",
                    "coverage": "rough_bbox",
                    "confidence": "high" if scaled_boxes else "medium",
                    "l1_status": "converted" if scaled_boxes else "redbox_not_detected",
                    "annotation_path": str(ann["path"]),
                    "annotation_folder": ann["folder"],
                    "bbox_count": len(scaled_boxes),
                    "label_path": str(label_path),
                    "image_output_path": str(image_output_path) if copy_images else "",
                    "preview_path": str(preview_path) if save_previews else "",
                }
            )
            high_rows.append(row)
            sample_rows.append(row)
            if len(scaled_boxes) != 1 or len(boxes) > len(selected_boxes):
                redbox_review.append(
                    {
                        "sample_id": sample_id,
                        "clean_path": str(clean["path"]),
                        "annotation_path": str(ann["path"]),
                        "defect_type": ann["defect_type"],
                        "bbox_count": len(scaled_boxes),
                        "raw_candidate_count": len(boxes),
                        "selection_policy": "all_candidates" if allow_multiple_bboxes else "best_candidate_only",
                        "debug": json.dumps(debug, ensure_ascii=False),
                        "raw_boxes": json.dumps([item["bbox_xyxy"] for item in boxes], ensure_ascii=False),
                        "boxes": json.dumps(scaled_boxes, ensure_ascii=False),
                    }
                )

        for (defect_type, _stem), clean_records in clean_index.items():
            for clean in clean_records:
                if str(clean["path"]) in used_clean_paths:
                    continue
                low_index += 1
                width, height = image_size(clean["path"])
                row = base_row(
                    make_sample_id("low", low_index),
                    model_entry,
                    clean["folder"],
                    clean["path"],
                    defect_type,
                    width,
                    height,
                )
                row.update(
                    {
                        "split_role": "low_conf_unlabeled",
                        "is_normal": "0",
                        "usable": "ignore_for_l1_metrics",
                        "view_quality": "unchecked",
                        "defect_visibility": "ambiguous",
                        "coverage": "partial",
                        "confidence": "low",
                        "l1_status": "no_annotation_image",
                    }
                )
                low_rows.append(row)
                sample_rows.append(row)

    write_outputs(out_dir, folder_profiles, sample_rows, high_rows, low_rows, normal_rows, annotation_without_clean, redbox_review)
    return summarize(sample_rows, high_rows, low_rows, normal_rows, annotation_without_clean, redbox_review)


def base_row(sample_id, model_entry, folder, image_path, defect_type, width, height):
    return {
        "sample_id": sample_id,
        "image_path": str(image_path),
        "relative_path": str(image_path.relative_to(model_entry["path"].parent)),
        "filename": image_path.name,
        "model": model_entry["model"],
        "model_folder": model_entry["folder"],
        "color": model_entry["color"],
        "defect_folder": folder,
        "defect_type": defect_type,
        "width": width,
        "height": height,
    }


def write_outputs(out_dir, folder_profiles, sample_rows, high_rows, low_rows, normal_rows, annotation_without_clean, redbox_review):
    write_csv(sample_rows, out_dir / "manifests" / "manifest_samples.csv")
    write_csv(high_rows, out_dir / "manifests" / "high_conf_l1_samples.csv")
    write_csv(low_rows, out_dir / "manifests" / "low_confidence_samples.csv")
    write_csv(normal_rows, out_dir / "manifests" / "normal_samples.csv")
    write_csv(annotation_without_clean, out_dir / "audits" / "annotation_without_clean_match.csv")
    write_csv(redbox_review, out_dir / "audits" / "redbox_detection_review.csv")
    (out_dir / "manifests" / "class_map.json").write_text(json.dumps(CLASS_MAP, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "manifests" / "folder_profiles.json").write_text(json.dumps(slim_folder_profiles(folder_profiles), ensure_ascii=False, indent=2), encoding="utf-8")


def slim_folder_profiles(folder_profiles):
    slim = []
    for profile in folder_profiles:
        slim.append(
            {
                "folder": profile["folder"],
                "model": profile["model"],
                "color": profile["color"],
                "children": [
                    {
                        "folder": child["folder"],
                        "defect_type": child["defect_type"],
                        "is_annotation": child["is_annotation"],
                    }
                    for child in profile["children"]
                ],
            }
        )
    return slim


def summarize(sample_rows, high_rows, low_rows, normal_rows, annotation_without_clean, redbox_review):
    by_role = Counter(row["split_role"] for row in sample_rows)
    by_defect = Counter(row["defect_type"] for row in sample_rows)
    high_by_defect = Counter(row["defect_type"] for row in high_rows)
    low_by_defect = Counter(row["defect_type"] for row in low_rows)
    normal_by_model = Counter("%s|%s" % (row["model"], row["color"]) for row in normal_rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "total_samples": len(sample_rows),
        "high_conf_l1_samples": len(high_rows),
        "low_conf_unlabeled_samples": len(low_rows),
        "normal_samples": len(normal_rows),
        "annotation_without_clean_match": len(annotation_without_clean),
        "redbox_review_samples": len(redbox_review),
        "by_role": dict(sorted(by_role.items())),
        "by_defect_type": dict(sorted(by_defect.items())),
        "high_conf_by_defect_type": dict(sorted(high_by_defect.items())),
        "low_conf_by_defect_type": dict(sorted(low_by_defect.items())),
        "normal_by_model_color": dict(sorted(normal_by_model.items())),
    }


def build_arg_parser():
    parser = argparse.ArgumentParser(description="Prepare real annotations from screened folders.")
    parser.add_argument("--real-root", required=True, help="Screened real dataset root.")
    parser.add_argument("--out-dir", required=True, help="Output annotation root.")
    parser.add_argument("--no-copy-images", action="store_true", help="Do not copy high-confidence clean images.")
    parser.add_argument("--no-previews", action="store_true", help="Do not write high-confidence bbox preview images.")
    parser.add_argument("--allow-multiple-bboxes", action="store_true", help="Write all red-box candidates instead of the best one.")
    return parser


def main():
    args = build_arg_parser().parse_args()
    root = resolve_path(args.real_root)
    out_dir = resolve_path(args.out_dir)
    summary = prepare(
        root,
        out_dir,
        copy_images=not args.no_copy_images,
        save_previews=not args.no_previews,
        allow_multiple_bboxes=args.allow_multiple_bboxes,
    )
    (out_dir / "manifests" / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
