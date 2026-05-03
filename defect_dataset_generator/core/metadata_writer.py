import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def write_dataset_summary(path: Path, generation_plan: Dict[str, Any]) -> None:
    rendered = generation_plan.get("status") in {"rendered", "partial"}
    dry_run = generation_plan.get("status") == "dry_run"
    export_state = "planned" if dry_run else rendered
    summary = {
        "schema_version": "0.1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": generation_plan.get("status", "unknown"),
        "count": generation_plan.get("count", 0),
        "total_requested": generation_plan.get("total_requested", generation_plan.get("count", 0)),
        "total_succeeded": generation_plan.get("total_succeeded", len(generation_plan.get("samples", []))),
        "total_failed": generation_plan.get("total_failed", len(generation_plan.get("failed_samples", []))),
        "backend_script": generation_plan.get("backend_script"),
        "model_profile": generation_plan.get("model_profile"),
        "seeds_used": generation_plan.get("seeds_used", []),
        "material_path": generation_plan.get("material_path"),
        "material_override_applied": generation_plan.get("material_override_applied", False),
        "failed_samples": generation_plan.get("failed_samples", []),
        "blend_file": generation_plan.get("blend_file"),
        "output_dir": generation_plan.get("output_dir"),
        "defect_types": [
            item["defect_type"]
            for item in generation_plan.get("defect_config", {}).get("defects", [])
        ],
        "exports": {
            "rgb": True,
            "masks": export_state,
            "yolo_labels": export_state,
            "per_image_metadata": export_state,
        },
    }
    write_json(path, summary)
