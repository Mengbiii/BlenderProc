import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.defect_profiles import get_defect_profile, normalize_defect_type
from core.model_profiles import get_model_profile


def main():
    parser = argparse.ArgumentParser(description="Validate scheduler dry-run defect plans without rendering.")
    parser.add_argument("--plans", required=True, help="Folder containing defect_plan_*.json files.")
    parser.add_argument("--model-profile", required=True, help="Expected model profile id.")
    parser.add_argument("--out", default=None, help="Optional JSON validation report path.")
    args = parser.parse_args()

    plans_dir = resolve_path(args.plans)
    model_profile = get_model_profile(args.model_profile)
    result = validate_plan_folder(plans_dir, model_profile)
    if args.out:
        out_path = resolve_path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["passed"] else 1


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


def validate_plan_folder(plans_dir, model_profile):
    errors = []
    plan_files = sorted([path for path in plans_dir.glob("defect_plan_*.json") if path.stem.replace("defect_plan_", "").isdigit()])
    if not plan_files:
        errors.append("No defect_plan_*.json files found in {0}".format(plans_dir))
    known_zones = set(model_profile.get("main_surface_zones", {}).keys())
    known_cameras = {preset.get("name") for preset in model_profile.get("camera_presets", [])}
    defect_type_counts = {}
    zone_counts = {}
    camera_counts = {}
    size_tier_counts = {}

    for plan_path in plan_files:
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append("{0}: invalid JSON: {1}".format(plan_path.name, exc))
            continue
        for key in ["plan_schema_version", "sample_id", "seed", "model_id", "camera_profile", "defects"]:
            if key not in plan:
                errors.append("{0}: missing top-level field {1}".format(plan_path.name, key))
        if plan.get("model_id") != model_profile.get("model_id"):
            errors.append("{0}: model_id {1} does not match expected {2}".format(plan_path.name, plan.get("model_id"), model_profile.get("model_id")))
        camera_profile = plan.get("camera_profile")
        camera_counts[camera_profile] = camera_counts.get(camera_profile, 0) + 1
        if camera_profile not in known_cameras:
            errors.append("{0}: unknown camera_profile {1}".format(plan_path.name, camera_profile))
        for defect in plan.get("defects", []):
            for key in ["defect_id", "defect_type", "placement_zone", "size_tier", "overlap_policy"]:
                if key not in defect:
                    errors.append("{0}: defect missing {1}".format(plan_path.name, key))
            if "projected_xy" not in defect and ("target_x_range" not in defect or "target_y_range" not in defect):
                errors.append("{0}: defect missing projected_xy or target ranges".format(plan_path.name))
            zone = defect.get("placement_zone")
            zone_counts[zone] = zone_counts.get(zone, 0) + 1
            if zone not in known_zones:
                errors.append("{0}: placement_zone {1} not in model profile".format(plan_path.name, zone))
            defect_type = normalize_defect_type(defect.get("defect_type"))
            defect_type_counts[defect_type] = defect_type_counts.get(defect_type, 0) + 1
            try:
                defect_profile = get_defect_profile(defect_type)
            except Exception as exc:
                errors.append("{0}: invalid defect_type {1}: {2}".format(plan_path.name, defect_type, exc))
                continue
            size_tier = defect.get("size_tier")
            size_tier_counts[size_tier] = size_tier_counts.get(size_tier, 0) + 1
            if size_tier not in defect_profile.get("size_tiers", {}):
                errors.append("{0}: size_tier {1} not valid for {2}".format(plan_path.name, size_tier, defect_type))

    return {
        "schema_version": "0.1",
        "validation_type": "defect_plan_folder_validation",
        "plans_dir": str(plans_dir),
        "model_id": model_profile.get("model_id"),
        "plan_file_count": len(plan_files),
        "camera_profile_distribution": camera_counts,
        "placement_zone_distribution": zone_counts,
        "defect_type_distribution": defect_type_counts,
        "size_tier_distribution": size_tier_counts,
        "rendering_invoked": False,
        "passed": not errors,
        "errors": errors,
    }


if __name__ == "__main__":
    raise SystemExit(main())
