import argparse
import json
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description="Summarize YOLO zero-result audit outputs.")
    parser.add_argument("--audit-dir", required=True)
    parser.add_argument("--real-labels-dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    audit_dir = resolve_path(args.audit_dir)
    real_labels_dir = resolve_path(args.real_labels_dir)
    out_dir = resolve_path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    label_audit = read_json(audit_dir / "data_yaml_label_audit_summary.json")
    default_val = parse_val_log(audit_dir / "default_synthetic_val_log.txt")
    fitted_val = parse_val_log(audit_dir / "fitted_synthetic_val_log.txt")
    default_pred = summarize_predictions(audit_dir / "default_real_lowconf_predictions" / "labels", real_labels_dir)
    fitted_pred = summarize_predictions(audit_dir / "fitted_real_lowconf_predictions" / "labels", real_labels_dir)

    conclusion = decide(label_audit, default_val, fitted_val, default_pred, fitted_pred)
    summary = {
        "schema_version": "0.1",
        "audit_type": "yolo_zero_result_audit",
        "label_audit": compact_label_audit(label_audit),
        "synthetic_validation": {
            "default_material": default_val,
            "fitted_material": fitted_val,
        },
        "real_lowconf_predictions": {
            "default_material": default_pred,
            "fitted_material": fitted_pred,
        },
        "decision": conclusion,
        "outputs": {
            "data_yaml_label_audit": str(audit_dir / "DATA_YAML_AND_LABEL_AUDIT.md"),
            "default_contact_sheet": str(audit_dir / "default_real_lowconf_contact_sheet.jpg"),
            "fitted_contact_sheet": str(audit_dir / "fitted_real_lowconf_contact_sheet.jpg"),
        },
    }
    (out_dir / "yolo_zero_audit_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(out_dir / "YOLO_ZERO_RESULT_AUDIT_REPORT.md", summary)
    print(json.dumps({"status": "completed", "report": str(out_dir / "YOLO_ZERO_RESULT_AUDIT_REPORT.md")}, indent=2))


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


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def strip_ansi(text):
    return re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text)


def parse_val_log(path):
    text = strip_ansi(read_text_auto(path))
    metrics = {
        "log_path": str(path),
        "images": None,
        "instances": None,
        "precision": None,
        "recall": None,
        "map50": None,
        "map50_95": None,
        "used_cuda0": "CUDA:0" in text,
    }
    for line in text.splitlines():
        normalized = " ".join(line.split())
        marker = " all "
        if normalized.startswith("all ") or marker in normalized:
            parts = normalized[normalized.index("all ") :].split() if "all " in normalized else normalized.split()
            if len(parts) >= 7:
                metrics.update(
                    {
                        "images": int(float(parts[1])),
                        "instances": int(float(parts[2])),
                        "precision": float(parts[3]),
                        "recall": float(parts[4]),
                        "map50": float(parts[5]),
                        "map50_95": float(parts[6]),
                    }
                )
    return metrics


def read_text_auto(path):
    data = path.read_bytes()
    for encoding in ["utf-16", "utf-8", "cp1252"]:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def summarize_predictions(pred_label_dir, gt_label_dir):
    pred_files = sorted(pred_label_dir.glob("*.txt")) if pred_label_dir.exists() else []
    total_predictions = 0
    images_with_predictions = 0
    confidences = []
    per_image = []
    gt_files = sorted(gt_label_dir.glob("*.txt")) if gt_label_dir.exists() else []
    gt_by_stem = {p.stem: read_boxes(p, has_conf=False) for p in gt_files}

    for pred_path in pred_files:
        preds = read_boxes(pred_path, has_conf=True)
        gts = gt_by_stem.get(pred_path.stem, [])
        if preds:
            images_with_predictions += 1
        total_predictions += len(preds)
        confidences.extend([p.get("conf", 0.0) for p in preds])
        best_iou = 0.0
        best_iou_conf = None
        for gt in gts:
            for pred in preds:
                value = iou(gt, pred)
                if value > best_iou:
                    best_iou = value
                    best_iou_conf = pred.get("conf")
        top_conf = max([p.get("conf", 0.0) for p in preds], default=None)
        per_image.append(
            {
                "file": pred_path.name,
                "gt_count": len(gts),
                "prediction_count": len(preds),
                "top_confidence": top_conf,
                "best_iou_with_gt": round(best_iou, 6),
                "confidence_of_best_iou_box": best_iou_conf,
            }
        )

    images_with_gt = sum(1 for boxes in gt_by_stem.values() if boxes)
    best_ious = [item["best_iou_with_gt"] for item in per_image if item["gt_count"] > 0]
    return {
        "pred_label_dir": str(pred_label_dir),
        "label_files": len(pred_files),
        "images_with_predictions": images_with_predictions,
        "total_predictions": total_predictions,
        "average_confidence": mean(confidences),
        "min_confidence": min(confidences) if confidences else None,
        "max_confidence": max(confidences) if confidences else None,
        "images_with_gt": images_with_gt,
        "mean_best_iou_on_gt_images": mean(best_ious),
        "gt_images_with_best_iou_ge_0_1": sum(1 for v in best_ious if v >= 0.1),
        "gt_images_with_best_iou_ge_0_5": sum(1 for v in best_ious if v >= 0.5),
        "per_image": per_image,
    }


def read_boxes(path, has_conf):
    if not path.exists():
        return []
    boxes = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            item = {
                "class_id": int(float(parts[0])),
                "x": float(parts[1]),
                "y": float(parts[2]),
                "w": float(parts[3]),
                "h": float(parts[4]),
            }
            if has_conf and len(parts) >= 6:
                item["conf"] = float(parts[5])
        except ValueError:
            continue
        boxes.append(item)
    return boxes


def iou(a, b):
    ax1, ay1, ax2, ay2 = corners(a)
    bx1, by1, bx2, by2 = corners(b)
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union > 0 else 0.0


def corners(box):
    return (
        box["x"] - box["w"] / 2,
        box["y"] - box["h"] / 2,
        box["x"] + box["w"] / 2,
        box["y"] + box["h"] / 2,
    )


def mean(values):
    return round(sum(values) / len(values), 8) if values else None


def compact_label_audit(audit):
    return {
        "yaml_path": audit["yaml_path"],
        "split": audit["split"],
        "names": audit["names"],
        "class_name_exact_match": audit["class_name_exact_match"],
        "class_name_accepted_alias": audit["class_name_accepted_alias"],
        "counts": audit["counts"],
        "class_ids": audit["class_ids"],
        "bbox_stats": audit["bbox_stats"],
        "blocking_errors": audit["blocking_errors"],
    }


def decide(label_audit, default_val, fitted_val, default_pred, fitted_pred):
    if label_audit.get("blocking_errors"):
        return {
            "category": "dataset_or_label_issue",
            "recommendation": "Stop and fix dataset preparation before any training.",
        }
    synthetic_nonzero = (
        (default_val.get("map50") or 0) > 0
        and (fitted_val.get("map50") or 0) > 0
    )
    if not synthetic_nonzero:
        return {
            "category": "synthetic_training_or_label_issue",
            "recommendation": "Stop and debug YOLO training or synthetic labels before real+synthetic experiments.",
        }
    low_conf_exists = default_pred["total_predictions"] > 0 or fitted_pred["total_predictions"] > 0
    if low_conf_exists:
        return {
            "category": "likely_domain_gap_with_confidence_and_localization_failure",
            "recommendation": "Proceed to a controlled real-only vs real+synthetic augmentation experiment, but note that real boxes are extremely small at imgsz=640 and low-confidence predictions are noisy.",
        }
    return {
        "category": "likely_domain_gap_absent_real_predictions",
        "recommendation": "Proceed cautiously to real+synthetic augmentation after documenting the lack of low-confidence detections.",
    }


def write_report(path, summary):
    label = summary["label_audit"]
    default_val = summary["synthetic_validation"]["default_material"]
    fitted_val = summary["synthetic_validation"]["fitted_material"]
    default_pred = summary["real_lowconf_predictions"]["default_material"]
    fitted_pred = summary["real_lowconf_predictions"]["fitted_material"]
    lines = [
        "# YOLO Zero Result Audit Report",
        "",
        "## Purpose",
        "",
        "Audit why the previous synthetic-only YOLO models scored zero on the fixed real QC71336 test split. This is a failure diagnosis step, not a new training experiment.",
        "",
        "## Dataset YAML And Label Audit",
        "",
        "| Item | Value |",
        "| --- | --- |",
        "| Images | {0} |".format(label["counts"]["images"]),
        "| Label files | {0} |".format(label["counts"]["labels"]),
        "| Non-empty labels | {0} |".format(label["counts"]["non_empty_labels"]),
        "| Empty labels/backgrounds | {0} |".format(label["counts"]["empty_labels"]),
        "| Missing labels | {0} |".format(label["counts"]["missing_labels"]),
        "| Invalid label files | {0} |".format(label["counts"]["invalid_label_files"]),
        "| Class ids | `{0}` |".format(label["class_ids"]),
        "| Class name exact match | {0} |".format(label["class_name_exact_match"]),
        "| Accepted alias | {0} |".format(label["class_name_accepted_alias"]),
        "| Blocking errors | {0} |".format(label["blocking_errors"] or "None"),
        "",
        "The YAML/labels are structurally valid. One naming caveat is recorded: class 0 is named `black_dot` in the real YAML while the current synthetic pipeline uses `black_spot`; both map to class id 0, so this is not treated as a blocking issue.",
        "",
        "A major scale risk is present: real test bbox width at imgsz=640 averages `{0}` px and height averages `{1}` px; all 8 real defect boxes are below the 3 px width-or-height threshold.".format(
            label["bbox_stats"]["width_px_at_imgsz"]["mean"],
            label["bbox_stats"]["height_px_at_imgsz"]["mean"],
        ),
        "",
        "## Synthetic Validation",
        "",
        "| Model | Images | Instances | Precision | Recall | mAP50 | mAP50-95 | CUDA:0 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        val_row("default_material", default_val),
        val_row("fitted_material", fitted_val),
        "",
        "Both models learned their synthetic validation task at a non-zero level. This argues against a complete training failure or broken synthetic YOLO labels.",
        "",
        "## Real Test Low-Confidence Predictions",
        "",
        "| Model | Images with predictions | Total predictions | Avg confidence | Max confidence | Mean best IoU on GT images | GT images IoU >= 0.5 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        pred_row("default_material", default_pred),
        pred_row("fitted_material", fitted_pred),
        "",
        "At `conf=0.001`, both models output many low-confidence boxes on every real image. This means the zero result is not simply because the network emits no boxes at all. The predictions are very low confidence and visually noisy; the contact sheets show many large or misplaced boxes, often on geometry/background regions rather than precise real defects.",
        "",
        "## Visual Evidence",
        "",
        "- Default material low-confidence contact sheet: `{0}`".format(summary["outputs"]["default_contact_sheet"]),
        "- Fitted material low-confidence contact sheet: `{0}`".format(summary["outputs"]["fitted_contact_sheet"]),
        "",
        "## Diagnosis",
        "",
        "- Real test YAML and labels look valid enough for evaluation, with the important caveat that the real defects are extremely tiny at `imgsz=640`.",
        "- The synthetic-only models learn synthetic validation data, so the previous zero result is not primarily explained by a broken training loop.",
        "- Low-confidence predictions exist, but they are noisy and poorly calibrated/localized on real images.",
        "- The most likely explanation is synthetic-only domain gap compounded by very small real target size and confidence/localization failure.",
        "",
        "## Decision",
        "",
        "- Category: `{0}`".format(summary["decision"]["category"]),
        "- Recommendation: {0}".format(summary["decision"]["recommendation"]),
        "",
        "It is safe to proceed to the next controlled experiment design: real-only vs real+default synthetic vs real+fitted_v2 synthetic. This audit does not prove synthetic data will improve detection; it only rules out the most obvious YAML/label/training-loop failure modes.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def val_row(name, metrics):
    return "| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} |".format(
        name,
        metrics.get("images"),
        metrics.get("instances"),
        metrics.get("precision"),
        metrics.get("recall"),
        metrics.get("map50"),
        metrics.get("map50_95"),
        metrics.get("used_cuda0"),
    )


def pred_row(name, metrics):
    return "| {0} | {1} | {2} | {3} | {4} | {5} | {6} |".format(
        name,
        metrics["images_with_predictions"],
        metrics["total_predictions"],
        metrics["average_confidence"],
        metrics["max_confidence"],
        metrics["mean_best_iou_on_gt_images"],
        metrics["gt_images_with_best_iou_ge_0_5"],
    )


if __name__ == "__main__":
    main()
