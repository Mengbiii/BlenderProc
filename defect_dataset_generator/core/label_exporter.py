from pathlib import Path


def write_yolo_label(path: Path, class_id: int, bbox_xywh_normalized: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    values = " ".join(f"{value:.6f}" for value in bbox_xywh_normalized)
    path.write_text(f"{class_id} {values}\n", encoding="utf-8")
